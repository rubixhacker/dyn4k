package io.github.rubixhacker.harness.qualification

import io.github.rubixhacker.harness.contract.Qualification
import io.github.rubixhacker.harness.contract.Sha256
import io.github.rubixhacker.harness.contract.StrictJson
import java.io.IOException
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.LinkOption
import java.nio.file.NoSuchFileException
import java.nio.file.Path
import java.nio.file.StandardCopyOption
import java.util.concurrent.TimeUnit
import javax.xml.parsers.DocumentBuilderFactory
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import org.w3c.dom.Element

/** The staged publication a bundle was captured from: its GAV set, files, hashes, and contract. */
class CapturedStaging(
    val gav: MutableList<String>,
    val files: MutableList<JsonObject>,
    val hashes: MutableMap<String, JsonObject>,
    val contentContract: JsonElement,
)

/**
 * The file-system half of `tools/qualification/artifact.py`: the hosted receipt verifier, the
 * staged publication capture, the two bundle builders, the Ubuntu runtime observation, and the
 * bundle verifier.
 *
 * Every message is recorded evidence: `verification.json` quotes it, and a reworded check
 * invalidates the bundles that recorded the previous wording.
 */
object ArtifactCapture {
    /** `artifact.verify_full_hosted`: verify a hosted receipt directory or transport archive. */
    fun verifyFullHosted(bundleInput: Path, candidateSha: String, repository: Path): JsonObject {
        if (Files.isDirectory(bundleInput)) {
            val receiptPath = bundleInput.resolve("receipt.json")
            val result = StrictJson.load(Fs.readText(receiptPath))
            if (result !is JsonObject) {
                throw IllegalArgumentException("full hosted receipt must be an object")
            }
            if (Py.str(result["candidate_sha"]) != candidateSha) {
                throw IllegalArgumentException("full hosted candidate differs from requested source")
            }
            FullHosted.verifyRawFiles(bundleInput, result, candidateRepository = repository)
            val verified = LinkedHashMap<String, JsonElement>(result)
            verified["_verified_receipt_sha256"] = JsonPrimitive(CorpusFiles.digest(receiptPath))
            return JsonObject(verified)
        }
        if (!Files.isRegularFile(bundleInput) || !bundleInput.fileName.toString().endsWith(".tar")) {
            throw IllegalArgumentException("full hosted bundle must be a directory or transport tar")
        }
        val result = FullHosted.verifyTransportArchive(
            bundleInput,
            candidateSha,
            candidateRepository = repository,
        )
        val members = readTarMembers(bundleInput)
        val receipt = members.firstOrNull { it.name == "receipt.json" }
            ?: throw IllegalArgumentException("full hosted transport receipt is missing")
        val verified = LinkedHashMap<String, JsonElement>(result)
        verified["_verified_receipt_sha256"] = JsonPrimitive(Sha256.of(receipt.bytes))
        verified["_verified_transport_sha256"] = JsonPrimitive(CorpusFiles.digest(bundleInput))
        return JsonObject(verified)
    }

    /**
     * `qualify.validate_hosted_probe`: one hosted probe must be the frozen, executed suite of its
     * target, and must name the staged binaries of the candidate.
     */
    fun validateHostedProbe(
        probe: JsonObject?,
        candidateSha: String,
        manifest: JsonObject,
        repository: Path? = null,
    ): JsonObject {
        if (probe == null || Py.str(probe["candidate_sha"]) != candidateSha) {
            throw IllegalArgumentException("hosted probe candidate SHA differs from report")
        }
        val target = Py.str(probe["target"])
        if (target == null || target !in Hosted.TARGETS) {
            throw IllegalArgumentException("hosted probe target is invalid")
        }
        val status = Py.str(probe["status"])
        if (status !in setOf("PROBE_PASSED", "PROBE_FAILED", "UNAVAILABLE", "NOT_RUN")) {
            throw IllegalArgumentException("hosted probe status is invalid")
        }
        if (status != "PROBE_PASSED") {
            val reason = Py.str(probe["reason"])
            if (reason == null || reason.trim().isEmpty()) {
                throw IllegalArgumentException(
                    "hosted probe failure or unavailability needs a reason",
                )
            }
            return probe
        }
        if (Hosted.runtimeStatus(target, probe["runtime"]).status != "READY") {
            throw IllegalArgumentException("hosted probe runtime identity is invalid")
        }
        val groups = linkedMapOf<String, JsonObject>()
        for (item in manifest["groups"] as? JsonArray ?: JsonArray(emptyList())) {
            val group = item as? JsonObject ?: continue
            Py.str(group["id"])?.let { groups[it] = group }
        }
        val selections = linkedMapOf<String, List<String>>()
        selections["consumer_probe"] = listOf("consumer-$target")
        if (target != "jsSafari") {
            selections["source_probe"] = listOf("core-$target", target)
        }
        for ((key, ids) in selections) {
            if (ids.any { it !in groups }) {
                throw IllegalArgumentException("hosted probe frozen report group is missing")
            }
            val selected = selectedManifest(manifest, ids)
            val observed = probe[key] as? JsonObject
            val expected = ids.sumOf { ProbeManifest.expectedCases(manifest, groups.getValue(it)).size }
            if (observed == null ||
                Py.str(observed["candidate_sha"]) != candidateSha ||
                Py.str(observed["manifest_sha256"]) != FullCorpus.canonicalDigest(selected) ||
                Py.str(observed["status"]) != "PROBE_PASSED" ||
                !Py.equalsInt(observed["expected"], expected.toLong()) ||
                !Py.equalsInt(observed["executed"], expected.toLong()) ||
                !Py.equalsInt(observed["failures"], 0L) ||
                !Py.equalsInt(observed["errors"], 0L) ||
                !Py.equalsInt(observed["skipped"], 0L) ||
                !Py.isInt(observed["reported"]) ||
                Py.int(observed["reported"]) < expected ||
                !Py.equalsInt(observed["exit_code"], 0L)
            ) {
                throw IllegalArgumentException("hosted $key differs from frozen executed suite")
            }
            ProbeManifest.validateAccounting(observed, selected, ids)
        }
        val hashes = probe["artifact_hashes"] as? JsonObject
        if (hashes == null || hashes.keys != Qualification.modules.toSet() ||
            hashes.values.any { !Py.SHA64.matches(Py.str(it) ?: "") }
        ) {
            throw IllegalArgumentException("hosted target needs both staged binary hashes")
        }
        if (repository != null) {
            val staging = repository.resolve("build/staging-repository")
            val artifactTarget = if (target == "jsSafari") "js" else target
            if (HostedHost.targetHashes(staging, artifactTarget) != hashes) {
                throw IllegalArgumentException("hosted binary hashes differ from staged candidate")
            }
        }
        return probe
    }

    /** `{**manifest, "groups": [...]}` with the groups replaced in their original position. */
    private fun selectedManifest(manifest: JsonObject, ids: List<String>): JsonObject {
        val declared = manifest["groups"] as? JsonArray ?: JsonArray(emptyList())
        val filtered = JsonArray(
            declared.filter { item -> Py.str((item as? JsonObject)?.get("id")) in ids },
        )
        val selected = LinkedHashMap<String, JsonElement>()
        for ((key, value) in manifest) {
            selected[key] = if (key == "groups") filtered else value
        }
        return JsonObject(selected)
    }

    /**
     * `artifact.capture_staging`: copy the staged publication into the bundle and audit it.
     *
     * The audit is the publication contract, so a partial staging tree fails here rather than in
     * the bundle verifier.
     */
    fun captureStaging(
        repository: Path,
        destination: Path,
        targets: List<String>,
        candidateSha: String,
    ): CapturedStaging {
        val staging = repository.resolve("build/staging-repository")
        val sourceLicense = repository.resolve("LICENSE.md")
        if (!Files.isRegularFile(sourceLicense)) {
            throw IllegalArgumentException("repository license is missing")
        }
        Files.copy(
            sourceLicense,
            destination.resolve("LICENSE.md"),
            StandardCopyOption.COPY_ATTRIBUTES,
            StandardCopyOption.REPLACE_EXISTING,
        )
        val gav = mutableListOf<String>()
        val files = mutableListOf<JsonObject>()
        val hashes = LinkedHashMap<String, JsonObject>()
        val names = mutableSetOf<String>()
        names.addAll(Qualification.modules)
        for (module in Qualification.modules) {
            for (target in targets) names.add(Qualification.targetPublicationName(module, target))
        }
        val metadataNames = mutableSetOf<String>()
        for (module in Qualification.modules) {
            for (target in targets) {
                if (Qualification.isAppleTarget(target)) {
                    metadataNames.add(Qualification.targetPublicationName(module, target))
                }
            }
        }
        for (name in names.sortedWith(CanonicalText::compare)) {
            val base = staging.resolve(Qualification.GROUP.replace(".", "/"))
                .resolve(name).resolve(Qualification.VERSION)
            val suffixes = mutableListOf(
                ".pom", ".module", "-sources.jar", "-javadoc.jar", "-license.md",
            )
            if (name in Qualification.modules) suffixes.add(".jar")
            if (name in metadataNames) suffixes.add("-metadata.jar")
            for (suffix in suffixes) {
                val source = base.resolve("$name-${Qualification.VERSION}$suffix")
                if (!Files.isRegularFile(source, LinkOption.NOFOLLOW_LINKS) ||
                    Files.isSymbolicLink(source)
                ) {
                    throw IllegalArgumentException("staged GAV descriptor missing: $name$suffix")
                }
                if (suffix == ".pom") {
                    val root = parseXml(source, namespaceAware = true)
                    for ((key, expected) in listOf(
                        "groupId" to Qualification.GROUP,
                        "artifactId" to name,
                        "version" to Qualification.VERSION,
                    )) {
                        if (childText(root, key) != expected) {
                            throw IllegalArgumentException("staged GAV differs in $name $key")
                        }
                    }
                } else if (suffix == ".module") {
                    val metadata = StrictJson.load(Fs.readText(source))
                    val component = (metadata as? JsonObject)?.get("component") as? JsonObject
                    if (metadata !is JsonObject || component == null ||
                        Py.str(component["version"]) != Qualification.VERSION
                    ) {
                        throw IllegalArgumentException(
                            "staged Gradle metadata version differs in $name",
                        )
                    }
                }
                val targetPath = destination.resolve("staged").resolve(
                    staging.relativize(source).toString().replace('\\', '/'),
                )
                targetPath.parent?.let { Files.createDirectories(it) }
                Files.copy(
                    source,
                    targetPath,
                    StandardCopyOption.COPY_ATTRIBUTES,
                    StandardCopyOption.REPLACE_EXISTING,
                )
                files.add(
                    buildJsonObject {
                        put(
                            "path",
                            JsonPrimitive(
                                ArtifactBundle.portablePath(
                                    destination.relativize(targetPath).toString().replace('\\', '/'),
                                ),
                            ),
                        )
                        put("sha256", JsonPrimitive(CorpusFiles.digest(targetPath)))
                    },
                )
                val sidecar = source.resolveSibling(source.fileName.toString() + ".sha256")
                if (!Files.isRegularFile(sidecar) ||
                    Fs.readText(sidecar).trim().lowercase() != CorpusFiles.digest(source)
                ) {
                    throw IllegalArgumentException("staged checksum differs: ${source.fileName}")
                }
                val sidecarPath = destination.resolve("staged").resolve(
                    staging.relativize(sidecar).toString().replace('\\', '/'),
                )
                Files.copy(
                    sidecar,
                    sidecarPath,
                    StandardCopyOption.COPY_ATTRIBUTES,
                    StandardCopyOption.REPLACE_EXISTING,
                )
                files.add(
                    buildJsonObject {
                        put(
                            "path",
                            JsonPrimitive(
                                ArtifactBundle.portablePath(
                                    destination.relativize(sidecarPath).toString().replace('\\', '/'),
                                ),
                            ),
                        )
                        put("sha256", JsonPrimitive(CorpusFiles.digest(sidecarPath)))
                    },
                )
            }
            gav.add("${Qualification.GROUP}:$name:${Qualification.VERSION}")
        }
        for (target in targets) {
            val targetHashes = LinkedHashMap<String, JsonElement>()
            for (module in Qualification.modules) {
                val binary = staging.resolve(Qualification.targetBinaryPath(module, target))
                val sidecar = binary.resolveSibling(binary.fileName.toString() + ".sha256")
                if (!Files.isRegularFile(binary) || !Files.isRegularFile(sidecar) ||
                    Files.isSymbolicLink(sidecar)
                ) {
                    throw IllegalArgumentException(
                        "staged binary or checksum missing: $module $target",
                    )
                }
                val actual = CorpusFiles.digest(binary)
                if (Fs.readText(sidecar).trim().lowercase() != actual) {
                    throw IllegalArgumentException(
                        "staged binary checksum differs: $module $target",
                    )
                }
                val binaryPath = destination.resolve("staged").resolve(
                    staging.relativize(binary).toString().replace('\\', '/'),
                )
                binaryPath.parent?.let { Files.createDirectories(it) }
                Files.copy(
                    binary,
                    binaryPath,
                    StandardCopyOption.COPY_ATTRIBUTES,
                    StandardCopyOption.REPLACE_EXISTING,
                )
                files.add(
                    buildJsonObject {
                        put(
                            "path",
                            JsonPrimitive(
                                ArtifactBundle.portablePath(
                                    destination.relativize(binaryPath).toString().replace('\\', '/'),
                                ),
                            ),
                        )
                        put("sha256", JsonPrimitive(CorpusFiles.digest(binaryPath)))
                    },
                )
                val targetPath = destination.resolve("staged").resolve(
                    staging.relativize(sidecar).toString().replace('\\', '/'),
                )
                targetPath.parent?.let { Files.createDirectories(it) }
                Files.copy(
                    sidecar,
                    targetPath,
                    StandardCopyOption.COPY_ATTRIBUTES,
                    StandardCopyOption.REPLACE_EXISTING,
                )
                files.add(
                    buildJsonObject {
                        put(
                            "path",
                            JsonPrimitive(
                                ArtifactBundle.portablePath(
                                    destination.relativize(targetPath).toString().replace('\\', '/'),
                                ),
                            ),
                        )
                        put("sha256", JsonPrimitive(CorpusFiles.digest(targetPath)))
                    },
                )
                targetHashes[module] = JsonPrimitive(actual)
            }
            hashes[target] = JsonObject(targetHashes)
        }
        val audit = StagingAudit.audit(staging, candidateSha, targets, sourceLicense)
        if (Py.str(audit["status"]) != "PASSED") {
            val errors = (audit["errors"] as? JsonArray ?: JsonArray(emptyList()))
                .mapNotNull { Py.str(it) }
            throw IllegalArgumentException(
                "staged publication is partial or invalid: " + errors.joinToString("; "),
            )
        }
        return CapturedStaging(gav, files, hashes, audit["content_contract"] ?: JsonNull)
    }

    /**
     * `artifact.stage_hosted`: assemble and verify one hosted bundle from a probe and its raw XML.
     *
     * The reference writes `verification.json` in a `finally` block, so a failing route still
     * leaves a record of why it failed.
     */
    fun stageHosted(
        repository: Path,
        manifest: JsonObject,
        candidateSha: String,
        target: String?,
        probePath: Path,
        matrixPath: Path?,
        destination: Path,
    ): JsonObject {
        // `destination.mkdir(parents=True, exist_ok=False)`: missing parents are created, an
        // existing destination is a `FileExistsError`.
        if (Files.exists(destination)) {
            throw java.nio.file.FileAlreadyExistsException(destination.toString())
        }
        Files.createDirectories(destination)
        Files.createDirectory(destination.resolve("json"))
        val result = initialResult(candidateSha, target ?: "")
        val problems = mutableListOf<String>()
        val reportFiles = mutableListOf<JsonObject>()
        var nonpassStatus: String? = null
        try {
            val probe = ArtifactBundle.copyJson(probePath, destination)
            val matrix = if (matrixPath != null) {
                ArtifactBundle.copyJson(matrixPath, destination)
            } else {
                buildJsonObject { put("candidate_sha", JsonPrimitive(candidateSha)) }
            }
            if (Py.str(matrix["candidate_sha"]) != candidateSha) {
                throw IllegalArgumentException("matrix candidate SHA differs from bundle")
            }
            if (Py.str(probe["candidate_sha"]) != candidateSha) {
                throw IllegalArgumentException("hosted candidate SHA differs from bundle")
            }
            if (Py.str(probe["target"]) != target) {
                throw IllegalArgumentException("hosted target differs from bundle")
            }
            if (Py.str(probe["status"]) != "PROBE_PASSED") {
                val status = Py.str(probe["status"])
                nonpassStatus = status
                if (status !in setOf("PROBE_FAILED", "UNAVAILABLE", "NOT_RUN")) {
                    throw IllegalArgumentException("hosted probe status is invalid")
                }
                result["reason"] = probe["reason"] ?: JsonPrimitive("hosted probe did not pass")
                return JsonObject(result)
            }
            validateHostedProbe(probe, candidateSha, manifest, repository)
            val artifactTarget = if (target == "jsSafari") "js" else target!!
            val captured = captureStaging(
                repository,
                destination,
                listOf(artifactTarget),
                candidateSha,
            )
            result["gav"] = JsonArray(captured.gav.map { JsonPrimitive(it) })
            result["staged_files"] = JsonArray(captured.files)
            result["staged_content_contract"] = captured.contentContract
            if ("stage_receipt_sha256" in probe || "stage_audit_sha256" in probe) {
                if (!Py.truthy(probe["stage_receipt_sha256"]) ||
                    !Py.truthy(probe["stage_audit_sha256"])
                ) {
                    throw IllegalArgumentException(
                        "hosted staging receipt and audit must both be present",
                    )
                }
                val stageDir = repository.resolve("build/staging-repository")
                    .resolve(".qualification").resolve(target!!)
                for ((filename, expected) in listOf(
                    "receipt.json" to Py.str(probe["stage_receipt_sha256"]),
                    "audit.json" to Py.str(probe["stage_audit_sha256"]),
                    "stage.log" to null,
                )) {
                    val source = stageDir.resolve(filename)
                    if (!Files.isRegularFile(source) || Files.isSymbolicLink(source)) {
                        throw IllegalArgumentException("hosted staging $filename is missing")
                    }
                    if (expected != null && CorpusFiles.digest(source) != expected) {
                        throw IllegalArgumentException("hosted staging $filename bytes differ")
                    }
                    val destinationPath = destination.resolve("staged/.qualification")
                        .resolve(target!!).resolve(filename)
                    destinationPath.parent?.let { Files.createDirectories(it) }
                    Files.copy(
                        source,
                        destinationPath,
                        StandardCopyOption.COPY_ATTRIBUTES,
                        StandardCopyOption.REPLACE_EXISTING,
                    )
                    captured.files.add(
                        buildJsonObject {
                            put(
                                "path",
                                JsonPrimitive(
                                    ArtifactBundle.portablePath(
                                        destination.relativize(destinationPath)
                                            .toString().replace('\\', '/'),
                                    ),
                                ),
                            )
                            put("sha256", JsonPrimitive(CorpusFiles.digest(destinationPath)))
                        },
                    )
                }
                result["staged_files"] = JsonArray(captured.files)
            }
            if (captured.hashes[artifactTarget] != probe["artifact_hashes"]) {
                throw IllegalArgumentException(
                    "staged GAV binary hashes differ from hosted observation",
                )
            }
            val groups = manifestGroups(manifest)
            val selections = linkedMapOf<String, List<String>>()
            selections["consumer_probe"] = listOf("consumer-$target")
            if (target != "jsSafari") {
                selections["source_probe"] = listOf("core-$target", target)
            }
            var expectedTotal = 0L
            var executedTotal = 0L
            var reportedTotal = 0L
            val groupCounts = LinkedHashMap<String, JsonElement>()
            val reportedCounts = LinkedHashMap<String, JsonElement>()
            for ((key, ids) in selections) {
                val suffix = if (key == "source_probe") "source" else "consumer"
                val stem = probePath.fileName.toString().substringBeforeLast('.')
                val sidecar = probePath.resolveSibling("$stem-$suffix.json")
                if (ArtifactBundle.copyJson(sidecar, destination) != probe[key]) {
                    problems.add("$suffix JSON differs from hosted result")
                }
                val observed = probe[key] as? JsonObject
                    ?: throw IllegalArgumentException("hosted $key is missing")
                val (started, finished) = ArtifactBundle.checkProbe(
                    observed, manifest, groups, ids, candidateSha,
                )
                val declaredGroups = declaredGroups(observed)
                for (groupId in ids) {
                    val group = groups.getValue(groupId)
                    val expected = ProbeManifest.expectedCases(manifest, group)
                    expectedTotal += expected.size
                    val counts = ArtifactBundle.collectGroup(
                        repository, destination, manifest, group, started, finished, reportFiles,
                    )
                    val declared = declaredGroups.getValue(groupId)
                    if (!Py.equalsInt(counts["selected"], Py.int(declared["executed"])) ||
                        !Py.equalsInt(counts["reported"], Py.int(declared["reported"]))
                    ) {
                        throw IllegalArgumentException(
                            "raw report counts differ from probe: $groupId",
                        )
                    }
                    val selected = Py.int(counts["selected"]!!)
                    val reported = Py.int(counts["reported"]!!)
                    groupCounts[groupId] = JsonPrimitive(selected)
                    reportedCounts[groupId] = JsonPrimitive(reported)
                    executedTotal += selected
                    reportedTotal += reported
                }
            }
            result["expected"] = JsonPrimitive(expectedTotal)
            result["executed"] = JsonPrimitive(executedTotal)
            result["reported"] = JsonPrimitive(reportedTotal)
            result["groups"] = JsonObject(groupCounts)
            result["reported_groups"] = JsonObject(reportedCounts)
            if (executedTotal != expectedTotal) {
                problems.add("raw executed count differs from frozen manifest")
            }
            result["runtime"] = probe["runtime"] ?: JsonNull
            result["artifact_hashes"] = probe["artifact_hashes"] ?: JsonNull
        } catch (error: Exception) {
            if (!isReferenceFailure(error)) throw error
            problems.add(error.message ?: error.toString())
        } finally {
            result["files"] = JsonArray(reportFiles)
            if (nonpassStatus == null || problems.isNotEmpty()) {
                result["status"] = JsonPrimitive(if (problems.isEmpty()) "PROBE_PASSED" else "PROBE_FAILED")
                result["reason"] = JsonPrimitive(
                    if (problems.isEmpty()) "raw XML matches frozen cases"
                    else problems.joinToString("; "),
                )
            } else {
                result["status"] = JsonPrimitive(nonpassStatus!!)
            }
            val text = PyJson.render(JsonObject(result)) + "\n"
            Files.write(
                destination.resolve("verification.json"),
                text.toByteArray(StandardCharsets.UTF_8),
            )
        }
        return JsonObject(result)
    }

    /** The initial `verification.json` shape both bundle builders start from. */
    private fun initialResult(candidateSha: String, route: String): LinkedHashMap<String, JsonElement> =
        linkedMapOf(
            "candidate_sha" to JsonPrimitive(candidateSha),
            "route" to JsonPrimitive(route),
            "status" to JsonPrimitive("PROBE_FAILED"),
            "reason" to JsonPrimitive("raw evidence is incomplete"),
            "expected" to JsonPrimitive(0),
            "executed" to JsonPrimitive(0),
            "reported" to JsonPrimitive(0),
            "groups" to JsonObject(emptyMap()),
            "reported_groups" to JsonObject(emptyMap()),
            "files" to JsonArray(emptyList()),
        )

    /** The reference's caught failure set: `KeyError, OSError, TypeError, ValueError, ParseError`. */
    private fun isReferenceFailure(error: Exception): Boolean = when (error) {
        is IllegalArgumentException, is IOException, is NoSuchElementException,
        is ClassCastException, is HostedXmlError, is org.xml.sax.SAXException -> true
        else -> false
    }

    /** `{group["id"]: group for group in manifest["groups"]}`. */
    private fun manifestGroups(manifest: JsonObject): Map<String, JsonObject> {
        val groups = LinkedHashMap<String, JsonObject>()
        for (item in manifest["groups"] as? JsonArray ?: JsonArray(emptyList())) {
            val group = item as? JsonObject ?: continue
            Py.str(group["id"])?.let { groups[it] = group }
        }
        return groups
    }

    /** `{item["id"]: item for item in probe["groups"]}`. */
    private fun declaredGroups(probe: JsonObject): Map<String, JsonObject> {
        val groups = LinkedHashMap<String, JsonObject>()
        for (item in probe["groups"] as? JsonArray ?: JsonArray(emptyList())) {
            val group = item as? JsonObject ?: continue
            Py.str(group["id"])?.let { groups[it] = group }
        }
        return groups
    }

    /**
     * `artifact.ubuntu_runtime`: the Ubuntu runner identity a bundle records.
     *
     * `platform.freedesktop_os_release()` reads `/etc/os-release`, then `/usr/lib/os-release`;
     * [release] is the seam a test supplies instead.
     */
    fun ubuntuRuntime(
        host: HostEnvironment = DefaultHostEnvironment,
        release: (() -> Map<String, String>)? = null,
    ): JsonObject {
        val values = (release ?: ::freedesktopOsRelease).invoke()
        return buildJsonObject {
            put("system", JsonPrimitive(host.system()))
            put("machine", JsonPrimitive(host.machine()))
            put(
                "kernel_release",
                JsonPrimitive(host.run(listOf("uname", "-r")).stdout.trim()),
            )
            put("distribution", JsonPrimitive(values["ID"] ?: ""))
            put("os_version", JsonPrimitive(values["VERSION_ID"] ?: ""))
            put("runner_image_os", JsonPrimitive(host.environment("ImageOS") ?: ""))
            put("runner_image_version", JsonPrimitive(host.environment("ImageVersion") ?: ""))
            put("github_actions", JsonPrimitive(host.environment("GITHUB_ACTIONS") == "true"))
            put(
                "java_version",
                JsonPrimitive(
                    HostedHost.toolVersion(listOf("java", "-version"), Regex("version \"([^\"]+)\""), host),
                ),
            )
        }
    }

    /** `platform.freedesktop_os_release()`: `/etc/os-release`, then `/usr/lib/os-release`. */
    private fun freedesktopOsRelease(): Map<String, String> {
        for (candidate in listOf("/etc/os-release", "/usr/lib/os-release")) {
            val path = Path.of(candidate)
            if (!Files.isRegularFile(path)) continue
            return ArtifactRules.parseOsRelease(Fs.readText(path).lines())
        }
        throw IOException("[Errno 2] No such file or directory: '/etc/os-release'")
    }

    /**
     * `artifact.stage_ubuntu`: assemble and verify the Ubuntu bundle from its probe evidence.
     *
     * [runtime] is a seam for the reference's `ubuntu_runtime()` call; production passes null.
     */
    fun stageUbuntu(
        repository: Path,
        manifest: JsonObject,
        candidateSha: String,
        evidenceDir: Path,
        destination: Path,
        runtime: JsonObject? = null,
        host: HostEnvironment = DefaultHostEnvironment,
    ): JsonObject {
        // `destination.mkdir(parents=True, exist_ok=False)`: missing parents are created, an
        // existing destination is a `FileExistsError`.
        if (Files.exists(destination)) {
            throw java.nio.file.FileAlreadyExistsException(destination.toString())
        }
        Files.createDirectories(destination)
        Files.createDirectory(destination.resolve("json"))
        val result = initialResult(candidateSha, "ubuntu-host")
        val problems = mutableListOf<String>()
        val reportFiles = mutableListOf<JsonObject>()
        try {
            val observed = runtime ?: ubuntuRuntime(host)
            result["runtime"] = observed
            ArtifactRules.checkUbuntuRuntime(observed)
            val groups = manifestGroups(manifest)
            val groupCounts = LinkedHashMap<String, JsonElement>()
            val reportedCounts = LinkedHashMap<String, JsonElement>()
            var expectedTotal = 0L
            var executedTotal = 0L
            var reportedTotal = 0L
            for ((name, ids) in ArtifactRules.UBUNTU_PROBES) {
                val probe = ArtifactBundle.copyJson(evidenceDir.resolve(name), destination)
                val (started, finished) = ArtifactBundle.checkProbe(
                    probe, manifest, groups, ids, candidateSha,
                )
                val declared = declaredGroups(probe)
                for (groupId in ids) {
                    val group = groups.getValue(groupId)
                    expectedTotal += ProbeManifest.expectedCases(manifest, group).size
                    val counts = ArtifactBundle.collectGroup(
                        repository,
                        destination,
                        manifest,
                        group,
                        started,
                        finished,
                        reportFiles,
                    )
                    val declaredGroup = declared.getValue(groupId)
                    if (!Py.equalsInt(counts["selected"], Py.int(declaredGroup["executed"])) ||
                        !Py.equalsInt(counts["reported"], Py.int(declaredGroup["reported"]))
                    ) {
                        throw IllegalArgumentException(
                            "raw report counts differ from probe: $groupId",
                        )
                    }
                    val selected = Py.int(counts["selected"]!!)
                    val reported = Py.int(counts["reported"]!!)
                    groupCounts[groupId] = JsonPrimitive(selected)
                    reportedCounts[groupId] = JsonPrimitive(reported)
                    executedTotal += selected
                    reportedTotal += reported
                }
            }
            result["expected"] = JsonPrimitive(expectedTotal)
            result["executed"] = JsonPrimitive(executedTotal)
            result["reported"] = JsonPrimitive(reportedTotal)
            result["groups"] = JsonObject(groupCounts)
            result["reported_groups"] = JsonObject(reportedCounts)
            val captured = captureStaging(
                repository,
                destination,
                listOf("jvm", "linuxX64", "js", "wasmJs", "wasmWasi", "android"),
                candidateSha,
            )
            result["gav"] = JsonArray(captured.gav.map { JsonPrimitive(it) })
            result["staged_files"] = JsonArray(captured.files)
            result["artifact_hashes"] = JsonObject(captured.hashes)
            result["staged_content_contract"] = captured.contentContract
            for (name in listOf("artifact-audit.json", "runtime-matrix.json")) {
                val data = ArtifactBundle.copyJson(evidenceDir.resolve(name), destination)
                if (Py.str(data["candidate_sha"]) != candidateSha) {
                    throw IllegalArgumentException("$name candidate SHA differs from bundle")
                }
            }
            val provider = evidenceDir.resolve("provider.log")
            if (!Files.isRegularFile(provider) || Files.isSymbolicLink(provider) ||
                Files.size(provider) == 0L
            ) {
                throw IllegalArgumentException("duplicate-provider diagnosis log is missing")
            }
            Files.copy(
                provider,
                destination.resolve("provider.log"),
                StandardCopyOption.COPY_ATTRIBUTES,
                StandardCopyOption.REPLACE_EXISTING,
            )
            if (executedTotal != expectedTotal) {
                throw IllegalArgumentException("raw executed count differs from frozen manifest")
            }
        } catch (error: Exception) {
            if (!isReferenceFailure(error)) throw error
            problems.add(error.message ?: error.toString())
        }
        result["files"] = JsonArray(reportFiles)
        result["status"] = JsonPrimitive(if (problems.isEmpty()) "PROBE_PASSED" else "PROBE_FAILED")
        result["reason"] = JsonPrimitive(
            if (problems.isEmpty()) "raw XML matches frozen cases"
            else problems.joinToString("; "),
        )
        val text = PyJson.render(JsonObject(result)) + "\n"
        Files.write(destination.resolve("verification.json"), text.toByteArray(StandardCharsets.UTF_8))
        return JsonObject(result)
    }

    /**
     * `artifact.verify_bundle`: re-derive every count, digest, and contract of a bundle.
     *
     * The raw XML is re-read into a scratch directory against the recorded file times, so a bundle
     * whose `verification.json` disagrees with its own bytes is rejected.
     */
    fun verifyBundle(
        bundle: Path,
        manifest: JsonObject,
        candidateSha: String,
        requireMatrix: Boolean = true,
    ): JsonObject {
        val summary = StrictJson.load(Fs.readText(bundle.resolve("verification.json")))
        if (summary !is JsonObject) {
            throw IllegalArgumentException("bundle verification JSON is not an object")
        }
        if (Py.str(summary["candidate_sha"]) != candidateSha) {
            throw IllegalArgumentException("bundle candidate SHA differs from requested candidate")
        }
        if (Py.str(summary["status"]) != "PROBE_PASSED") {
            throw IllegalArgumentException(
                Py.str(summary["reason"]) ?: "bundle did not pass",
            )
        }
        val route = Py.str(summary["route"])
        val selections: Map<String, List<String>>
        val top: JsonObject?
        if (route == "ubuntu-host") {
            ArtifactRules.checkUbuntuRuntime(summary["runtime"] as? JsonObject)
            selections = ArtifactRules.UBUNTU_PROBES
            top = null
        } else {
            if (route == null || route !in Hosted.TARGETS) {
                throw IllegalArgumentException("unknown bundle route")
            }
            val name = "hosted-$route"
            val hostedTop = StrictJson.load(Fs.readText(bundle.resolve("json").resolve("$name.json")))
                as? JsonObject
                ?: throw IllegalArgumentException("hosted probe report is not an object")
            validateHostedProbe(hostedTop, candidateSha, manifest)
            if (Py.str(hostedTop["status"]) != "PROBE_PASSED") {
                throw IllegalArgumentException(
                    "hosted top status is ${Py.str(hostedTop["status"])}, not PROBE_PASSED",
                )
            }
            if (summary["runtime"] != hostedTop["runtime"]) {
                throw IllegalArgumentException("bundle runtime differs from hosted observation")
            }
            val chosen = linkedMapOf<String, List<String>>()
            chosen["$name-consumer.json"] = listOf("consumer-$route")
            if (route != "jsSafari") {
                chosen["$name-source.json"] = listOf("core-$route", route)
            }
            selections = chosen
            top = hostedTop
        }
        val groups = manifestGroups(manifest)
        val found = LinkedHashMap<String, Long>()
        val foundReported = LinkedHashMap<String, Long>()
        val files = mutableListOf<JsonObject>()
        val recorded = summary["files"] as? JsonArray
        if (recorded == null || recorded.isEmpty() || recorded.any { it !is JsonObject }) {
            throw IllegalArgumentException("bundle raw file inventory is missing")
        }
        val normalizedRecorded = recorded.map { element ->
            val item = element as JsonObject
            JsonObject(item + ("path" to JsonPrimitive(ArtifactBundle.portablePath(Py.str(item["path"])))))
        }
        val recordedTimes = LinkedHashMap<String, Long?>()
        for (item in normalizedRecorded) {
            val path = Py.str(item["path"])!!
            val time = item["mtime_ns"]
            recordedTimes[path] = if (Py.isInt(time)) Py.int(time) else null
        }
        if (recordedTimes.size != recorded.size) {
            throw IllegalArgumentException("bundle raw file inventory has duplicate paths")
        }
        val scratch = Files.createTempDirectory("artifact-bundle")
        try {
            for ((name, ids) in selections) {
                val probe = StrictJson.load(Fs.readText(bundle.resolve("json").resolve(name)))
                    as? JsonObject
                    ?: throw IllegalArgumentException("bundled probe report is not an object")
                if (route != "ubuntu-host") {
                    val role = if (name.endsWith("-consumer.json")) "consumer_probe" else "source_probe"
                    if (probe != top!![role]) {
                        throw IllegalArgumentException(
                            "bundled $role differs from hosted observation",
                        )
                    }
                }
                val (started, finished) = ArtifactBundle.checkProbe(
                    probe, manifest, groups, ids, candidateSha,
                )
                val declared = declaredGroups(probe)
                for (groupId in ids) {
                    val counts = ArtifactBundle.collectGroup(
                        bundle.resolve("xml"),
                        scratch,
                        manifest,
                        groups.getValue(groupId),
                        started,
                        finished,
                        files,
                        recordedTimes.filterValues { it != null }.mapValues { it.value!! },
                    )
                    val declaredGroup = declared.getValue(groupId)
                    if (!Py.equalsInt(counts["selected"], Py.int(declaredGroup["executed"])) ||
                        !Py.equalsInt(counts["reported"], Py.int(declaredGroup["reported"]))
                    ) {
                        throw IllegalArgumentException(
                            "bundled report counts differ from probe: $groupId",
                        )
                    }
                    found[groupId] = Py.int(counts["selected"]!!)
                    foundReported[groupId] = Py.int(counts["reported"]!!)
                }
            }
        } finally {
            Files.walk(scratch).use { walk ->
                walk.sorted(Comparator.reverseOrder()).forEach { Files.deleteIfExists(it) }
            }
        }
        if (found.mapValues { JsonPrimitive(it.value) } != (summary["groups"] as? JsonObject) ||
            found.values.sum() != Py.int(summary["executed"] ?: JsonPrimitive(0)) ||
            foundReported.mapValues { JsonPrimitive(it.value) } !=
            (summary["reported_groups"] as? JsonObject) ||
            foundReported.values.sum() != Py.int(summary["reported"] ?: JsonPrimitive(0))
        ) {
            throw IllegalArgumentException("bundle counts differ from raw XML")
        }
        if (Py.int(summary["expected"] ?: JsonPrimitive(0)) != found.values.sum()) {
            throw IllegalArgumentException("bundle expected count differs from frozen cases")
        }
        val byPath = { list: List<JsonObject> ->
            list.sortedWith { left, right ->
                CanonicalText.compare(Py.str(left["path"]) ?: "", Py.str(right["path"]) ?: "")
            }
        }
        if (byPath(files) != byPath(normalizedRecorded)) {
            throw IllegalArgumentException("bundle XML hashes differ from verification")
        }
        val actualPaths = collectFiles(bundle, ".xml", "xml/")
        if (actualPaths != files.mapNotNull { Py.str(it["path"]) }.toSet()) {
            throw IllegalArgumentException("bundle contains unlisted XML")
        }
        val stagedFilesElement = summary["staged_files"] as? JsonArray
        if (stagedFilesElement == null || stagedFilesElement.isEmpty()) {
            throw IllegalArgumentException("staged GAV provenance is missing")
        }
        if (stagedFilesElement.any { it !is JsonObject }) {
            throw IllegalArgumentException("staged GAV provenance is invalid")
        }
        val stagedFiles = stagedFilesElement.map { element ->
            val item = element as JsonObject
            JsonObject(item + ("path" to JsonPrimitive(ArtifactBundle.portablePath(Py.str(item["path"])))))
        }
        if (stagedFiles.map { Py.str(it["path"]) }.toSet().size != stagedFiles.size) {
            throw IllegalArgumentException("staged GAV provenance has duplicate paths")
        }
        for (item in stagedFiles) {
            val path = bundle.resolve(Py.str(item["path"])!!)
            if (!Files.isRegularFile(path) || Files.isSymbolicLink(path) ||
                CorpusFiles.digest(path) != Py.str(item["sha256"])
            ) {
                throw IllegalArgumentException("staged GAV descriptor or checksum differs from bundle")
            }
        }
        val stagedPaths = collectFiles(bundle, null, "staged/")
        if (stagedPaths != stagedFiles.mapNotNull { Py.str(it["path"]) }.toSet()) {
            throw IllegalArgumentException("bundle contains unlisted staged provenance")
        }
        val names = mutableListOf<String>()
        for (item in stagedFiles) {
            val path = bundle.resolve(Py.str(item["path"])!!)
            if (!path.fileName.toString().endsWith(".pom")) continue
            val name = path.parent.parent.fileName.toString()
            val root = parseXml(path, namespaceAware = true)
            if (childText(root, "groupId") != Qualification.GROUP ||
                childText(root, "artifactId") != name ||
                childText(root, "version") != Qualification.VERSION
            ) {
                throw IllegalArgumentException("bundled staged GAV identity differs")
            }
            names.add("${Qualification.GROUP}:$name:${Qualification.VERSION}")
        }
        val declaredGav = (summary["gav"] as? JsonArray ?: JsonArray(emptyList()))
            .mapNotNull { Py.str(it) }
        if (names.sortedWith(CanonicalText::compare) != declaredGav.sortedWith(CanonicalText::compare)) {
            throw IllegalArgumentException("bundled staged GAV set differs")
        }
        val targets = if (route == "ubuntu-host") {
            listOf("jvm", "linuxX64", "js", "wasmJs", "wasmWasi", "android")
        } else {
            listOf(if (route == "jsSafari") "js" else route!!)
        }
        val licenseFile = bundle.resolve("LICENSE.md")
        if (!Files.isRegularFile(licenseFile) || Files.isSymbolicLink(licenseFile)) {
            throw IllegalArgumentException("bundle source license is missing")
        }
        val stagedAudit = StagingAudit.audit(
            bundle.resolve("staged"),
            candidateSha,
            targets,
            licenseFile,
            contentContract = summary["staged_content_contract"],
        )
        if (Py.str(stagedAudit["status"]) != "PASSED") {
            val errors = (stagedAudit["errors"] as? JsonArray ?: JsonArray(emptyList()))
                .mapNotNull { Py.str(it) }
            throw IllegalArgumentException(
                "bundled staged publication is partial or invalid: " + errors.joinToString("; "),
            )
        }
        if (route != "ubuntu-host" &&
            ("stage_receipt_sha256" in top!! || "stage_audit_sha256" in top)
        ) {
            if (!Py.truthy(top["stage_receipt_sha256"]) || !Py.truthy(top["stage_audit_sha256"])) {
                throw IllegalArgumentException("bundled hosted stage identity is incomplete")
            }
            val stageDir = bundle.resolve("staged/.qualification").resolve(route!!)
            val receiptPath = stageDir.resolve("receipt.json")
            val auditPath = stageDir.resolve("audit.json")
            val consolePath = stageDir.resolve("stage.log")
            if (!Files.isRegularFile(receiptPath) ||
                CorpusFiles.digest(receiptPath) != Py.str(top["stage_receipt_sha256"]) ||
                !Files.isRegularFile(auditPath) ||
                CorpusFiles.digest(auditPath) != Py.str(top["stage_audit_sha256"])
            ) {
                throw IllegalArgumentException("bundled hosted stage receipt or audit bytes differ")
            }
            val verified = StagingAudit.audit(
                bundle.resolve("staged"),
                candidateSha,
                targets,
                licenseFile,
                receiptPath,
                consolePath,
                contentContract = summary["staged_content_contract"],
            )
            if (verified != StrictJson.load(Fs.readText(auditPath)) ||
                Py.str(verified["status"]) != "PASSED"
            ) {
                throw IllegalArgumentException(
                    "bundled hosted stage task outcome or artifact audit differs",
                )
            }
        }
        val observedHashes = LinkedHashMap<String, JsonObject>()
        for (target in targets) {
            val perModule = LinkedHashMap<String, JsonElement>()
            for (module in Qualification.modules) {
                val relative = Qualification.targetBinaryPath(module, target) + ".sha256"
                val sidecar = bundle.resolve("staged").resolve(relative)
                val digest = Fs.readText(sidecar).trim().lowercase()
                if (!Py.SHA64.matches(digest)) {
                    throw IllegalArgumentException("bundled staged binary checksum is invalid")
                }
                val binary = bundle.resolve("staged")
                    .resolve(Qualification.targetBinaryPath(module, target))
                if (!Files.isRegularFile(binary) || Files.isSymbolicLink(binary) ||
                    CorpusFiles.digest(binary) != digest
                ) {
                    throw IllegalArgumentException(
                        "bundled staged binary checksum differs or binary is missing: " +
                            "$module $target",
                    )
                }
                perModule[module] = JsonPrimitive(digest)
            }
            observedHashes[target] = JsonObject(perModule)
        }
        val expectedHashes: JsonElement = if (route == "ubuntu-host") {
            summary["artifact_hashes"] ?: JsonNull
        } else {
            buildJsonObject { put(targets[0], summary["artifact_hashes"] ?: JsonNull) }
        }
        if (JsonObject(observedHashes) != expectedHashes) {
            throw IllegalArgumentException("bundled staged binary hashes differ")
        }
        val matrixName = if (route == "ubuntu-host") "runtime-matrix.json" else "matrix-$route.json"
        val matrixPath = bundle.resolve("json").resolve(matrixName)
        if (Files.isRegularFile(matrixPath)) {
            val matrix = StrictJson.load(Fs.readText(matrixPath)) as? JsonObject
                ?: throw IllegalArgumentException("bundle runtime matrix is invalid")
            val expectedLanes = Qualification.expand().map { it.id }.toSet()
            if (expectedLanes.size != 112 ||
                Py.str(matrix["candidate_sha"]) != candidateSha ||
                Py.int(matrix["total"] ?: JsonPrimitive(0)) != expectedLanes.size.toLong()
            ) {
                throw IllegalArgumentException("bundle runtime matrix candidate or size differs")
            }
            val lanes = matrix["lanes"] as? JsonArray
            if (lanes == null || lanes.size != expectedLanes.size) {
                throw IllegalArgumentException("bundle matrix lane set is incomplete")
            }
            if (lanes.any { it !is JsonObject || Py.str((it as JsonObject)["id"]) == null }) {
                throw IllegalArgumentException("bundle matrix lane identity is invalid")
            }
            val laneIds = lanes.mapNotNull { Py.str((it as JsonObject)["id"]) }
            if (laneIds.toSet().size != laneIds.size || laneIds.toSet() != expectedLanes) {
                throw IllegalArgumentException(
                    "bundle matrix lane IDs are missing, duplicate, or unknown",
                )
            }
            val statuses = listOf("PASSED", "FAILED", "UNAVAILABLE", "NOT_RUN")
            if (lanes.any { Py.str((it as JsonObject)["status"]) !in statuses }) {
                throw IllegalArgumentException("bundle matrix lane status is invalid")
            }
            val counted = linkedMapOf<String, Long>()
            for (status in statuses) {
                counted[status] = lanes.count { Py.str((it as JsonObject)["status"]) == status }.toLong()
            }
            val declared = matrix["counts"] as? JsonObject
            if (declared == null || declared.keys != statuses.toSet() ||
                declared.values.any { !Py.isInt(it) } ||
                declared != JsonObject(counted.mapValues { JsonPrimitive(it.value) })
            ) {
                throw IllegalArgumentException("bundle matrix counts differ from lane records")
            }
            if (route != "ubuntu-host") {
                val bounded = matrix["bounded_hosted_probes"] ?: JsonArray(emptyList())
                if (bounded != JsonArray(listOf(top!!))) {
                    throw IllegalArgumentException(
                        "bundle matrix bounded observation differs from hosted probe",
                    )
                }
            }
        } else if (requireMatrix) {
            throw IllegalArgumentException("bundle runtime matrix is missing")
        }
        return summary
    }

    /**
     * Every file under `bundle/prefix`, as bundle-relative POSIX paths.
     *
     * `suffix` filters the member name; `prefix` is the directory the reference walks (and whose
     * name is kept in the returned path).
     */
    private fun collectFiles(bundle: Path, suffix: String?, prefix: String): Set<String> {
        val root = bundle.resolve(prefix.removeSuffix("/"))
        if (!Files.isDirectory(root)) return emptySet()
        val paths = mutableSetOf<String>()
        Files.walk(root).use { stream ->
            for (path in stream) {
                if (!Files.isRegularFile(path)) continue
                if (suffix != null && !path.fileName.toString().endsWith(suffix)) continue
                paths.add(bundle.relativize(path).toString().replace('\\', '/'))
            }
        }
        return paths
    }

    /** One transport archive member: its names and bytes. */
    class TarMember(val name: String, val bytes: ByteArray)

    /** Reads every member of a transport archive, so the receipt bytes can be re-digested. */
    fun readTarMembers(archive: Path): List<TarMember> {
        val members = mutableListOf<TarMember>()
        Files.newInputStream(archive).use { stream ->
            org.apache.commons.compress.archivers.tar.TarArchiveInputStream(stream).use { packed ->
                while (true) {
                    val entry = packed.nextEntry ?: break
                    members.add(TarMember(entry.name, packed.readBytes()))
                }
            }
        }
        return members
    }

    /** Parses one XML document; the POM contract needs namespace-aware element names. */
    private fun parseXml(path: Path, namespaceAware: Boolean = false): Element {
        val factory = DocumentBuilderFactory.newInstance()
        factory.isNamespaceAware = namespaceAware
        factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true)
        val builder = factory.newDocumentBuilder()
        builder.setErrorHandler(
            object : org.xml.sax.ErrorHandler {
                override fun warning(exception: org.xml.sax.SAXParseException) = Unit
                override fun error(exception: org.xml.sax.SAXParseException) = throw exception
                override fun fatalError(exception: org.xml.sax.SAXParseException) = throw exception
            },
        )
        return builder.parse(path.toFile()).documentElement
    }

    /** `root.findtext(name)`: the text of the first direct child with that name. */
    private fun childText(root: Element, name: String): String? {
        val children = root.childNodes
        for (index in 0 until children.length) {
            val node = children.item(index)
            if (node is Element && node.tagName == name) return node.textContent
        }
        return null
    }
}
