package io.github.rubixhacker.harness.qualification

import io.github.rubixhacker.harness.contract.Qualification
import io.github.rubixhacker.harness.contract.Sha256
import io.github.rubixhacker.harness.contract.StrictJson
import java.io.IOException
import java.net.URI
import java.net.http.HttpClient
import java.net.http.HttpRequest
import java.net.http.HttpResponse
import java.nio.charset.StandardCharsets
import java.nio.file.FileAlreadyExistsException
import java.nio.file.Files
import java.nio.file.LinkOption
import java.nio.file.NoSuchFileException
import java.nio.file.Path
import java.nio.file.StandardCopyOption
import java.nio.file.attribute.BasicFileAttributes
import java.security.MessageDigest
import java.time.Duration
import java.util.concurrent.TimeUnit
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import org.apache.commons.compress.archivers.tar.TarArchiveEntry
import org.apache.commons.compress.archivers.tar.TarArchiveInputStream
import org.apache.commons.compress.archivers.zip.ZipFile

/**
 * The file-system and process half of `tools/qualification/collection.py`: the anchored reads, the
 * producer inventory, the transport extraction, the collection ledger, the cross-run source index,
 * the signed external audit ingestion, and the GitHub artifact download.
 *
 * The reference reaches for `dir_fd`-relative `os.open` on POSIX and for `CreateFileW`/
 * `NtCreateFile` handles on Windows. A JVM path has no descriptor, so every component is checked
 * with `NOFOLLOW_LINKS` and the identity is re-read before and after the operation; the Windows
 * reparse-point handle paths are not ported and fail closed. See the port report for each gap.
 */
/**
 * The operations `collection.py` lets its tests interpose on.
 *
 * An open class rather than an interface, so a subclass that overrides only `directoryNames` still
 * reaches its own enumeration through the inherited `inventory`.
 */
open class CollectionIo {
    /** `_directory_names`: the names one directory enumeration returns. */
    open fun directoryNames(anchor: Path): List<String> =
        Files.newDirectoryStream(anchor).use { stream ->
            stream.map { it.fileName.toString() }.toList()
        }

    /** `digest`: the bytes of one anchored regular file. */
    open fun digest(path: Path, limit: Long?): String = CollectionRuntime.hashFile(path, limit)

    /** `_copy_regular`: freeze one regular file with a byte bound. */
    open fun copyRegular(
        source: Path,
        destination: Path,
        limit: Long,
        preflight: Boolean,
    ): Long = CollectionRuntime.copyFile(source, destination, limit, preflight)

    /** `_file_inventory`: one directory's files and digests, through this instance's enumeration. */
    open fun inventory(root: Path): JsonObject = CollectionRuntime.inventoryTree(root, this)

    /** `subprocess.run` of the signed adapter. */
    open fun runAdapter(command: List<String>, cwd: Path): AdapterRun {
        val process = ProcessBuilder(command).directory(cwd.toFile()).start()
        val stdout = process.inputStream.use { it.readBytes() }
        val stderr = process.errorStream.use { it.readBytes() }
        return AdapterRun(process.waitFor(), stdout, stderr)
    }

    /** `MAX_SOURCE_BYTES`: the pinned source byte cap. */
    open val maxSourceBytes: Long get() = 10L * 1024 * 1024 * 1024

    /** `MAX_EXPANDED_BYTES`: the pinned expanded byte cap. */
    open val maxExpandedBytes: Long get() = 20L * 1024 * 1024 * 1024

    /** `MAX_MEMBERS`: the pinned member count cap. */
    open val maxMembers: Int get() = 200_000

    companion object {
        val default: CollectionIo = CollectionIo()
    }
}

/** One finished adapter run: its exit status and both streams. */
class AdapterRun(val exitCode: Int, val stdout: ByteArray, val stderr: ByteArray)

object CollectionRuntime {
    private const val MAX_SOURCE_BYTES = 10L * 1024 * 1024 * 1024
    private const val MAX_EXPANDED_BYTES = 20L * 1024 * 1024 * 1024
    private const val MAX_MEMBERS = 200_000

    /** `digest`: the bytes of one regular file, with a byte bound and identity pin. */
    fun digest(
        path: Path,
        limit: Long? = null,
        expected: Pair<Any?, Any?>? = null,
        io: CollectionIo = CollectionIo.default,
    ): String = io.digest(path, limit)

    /** The real byte digest of one anchored regular file. */
    internal fun hashFile(
        path: Path,
        limit: Long? = null,
        expected: Pair<Any?, Any?>? = null,
    ): String {
        val before = readProtected(path, expected)
        val hashed = MessageDigest.getInstance("SHA-256")
        var total = 0L
        Files.newInputStream(path, LinkOption.NOFOLLOW_LINKS).use { stream ->
            val buffer = ByteArray(1024 * 1024)
            while (true) {
                val read = stream.read(buffer)
                if (read <= 0) break
                total += read
                if (limit != null && total > limit) {
                    throw IllegalArgumentException("source file exceeds byte bound")
                }
                hashed.update(buffer, 0, read)
            }
        }
        afterRead(path, before)
        return hashed.digest().joinToString("") { "%02x".format(it) }
    }

    /** `source_tree`: the tree of the exact candidate, and the checkout must be that commit. */
    fun sourceTree(repository: Path, candidateSha: String): String {
        if (!CollectionRules.SHA40.matches(candidateSha)) {
            throw IllegalArgumentException("candidate SHA must be a full Git commit")
        }
        val process = ProcessBuilder(
            "git", "--no-replace-objects", "-C", repository.toString(), "rev-parse",
            "HEAD", "$candidateSha^{tree}",
        ).start()
        val output = process.inputStream.use { it.readBytes() }.decodeToString()
        val error = process.errorStream.use { it.readBytes() }
        if (process.waitFor() != 0) {
            throw IllegalArgumentException(
                "candidate tree is unavailable: " + error.decodeToString().trim(),
            )
        }
        val lines = output.trim().split('\n')
        val head = lines.getOrNull(0) ?: ""
        val tree = lines.getOrNull(1) ?: ""
        if (head != candidateSha || !CollectionRules.SHA40.matches(tree)) {
            throw IllegalArgumentException("collector checkout differs from exact candidate")
        }
        return tree
    }

    /** `files_in`: every raw artifact file and its digest. */
    fun filesIn(root: Path, io: CollectionIo = CollectionIo.default): JsonObject {
        if (Files.isSymbolicLink(root) || !Files.isDirectory(root)) {
            throw IllegalArgumentException("artifact root is missing or symbolic")
        }
        val inventory = io.inventory(root)
        val files = LinkedHashMap<String, JsonElement>()
        for ((name, record) in inventory) {
            files[name] = (record as JsonObject)["sha256"] ?: JsonNull
        }
        return JsonObject(files)
    }

    /** `_file_inventory`: one directory's files, size and digest, sorted by path. */
    fun fileInventory(root: Path, io: CollectionIo = CollectionIo.default): JsonObject = io.inventory(root)

    /** The real directory inventory. */
    internal fun inventoryTree(root: Path, io: CollectionIo): JsonObject {
        val info = attributes(root)
        if (info.isSymbolicLink || !info.isDirectory) {
            throw IllegalArgumentException("source directory is missing or symbolic")
        }
        val files = LinkedHashMap<String, JsonElement>()
        var count = 0
        var total = 0L

        fun visit(anchor: Path, prefix: String) {
            val names = mutableListOf<String>()
            val seen = mutableSetOf<String>()
            try {
                for (name in io.directoryNames(anchor)) {
                    names.add(name)
                    if (!seen.add(name)) {
                        throw IllegalArgumentException("duplicate source directory member")
                    }
                }
            } catch (error: NoSuchFileException) {
                throw IllegalArgumentException("source directory is missing or symbolic")
            }
            for (name in names) {
                val relative = if (prefix.isEmpty()) name else "$prefix/$name"
                CollectionRules.filePathName(relative)
                count++
                if (count > io.maxMembers) {
                    throw IllegalArgumentException("source directory exceeds transport bounds")
                }
                val child = anchor.resolve(name)
                val childInfo = attributes(child)
                if (childInfo.isSymbolicLink) {
                    throw IllegalArgumentException("symbolic source member")
                }
                if (childInfo.isDirectory) {
                    visit(child, relative)
                } else if (!childInfo.isRegularFile) {
                    throw IllegalArgumentException("nonregular source member")
                } else {
                    total += childInfo.size()
                    if (total > io.maxExpandedBytes) {
                        throw IllegalArgumentException("source directory exceeds transport bounds")
                    }
                    val hashed = MessageDigest.getInstance("SHA-256")
                    var read = 0L
                    Files.newInputStream(child, LinkOption.NOFOLLOW_LINKS).use { stream ->
                        val buffer = ByteArray(1024 * 1024)
                        while (true) {
                            val countRead = stream.read(buffer)
                            if (countRead <= 0) break
                            read += countRead
                            if (read > childInfo.size() || read > io.maxExpandedBytes) {
                                throw IllegalArgumentException(
                                    "source directory changed while inventoried",
                                )
                            }
                            hashed.update(buffer, 0, countRead)
                        }
                    }
                    if (read != childInfo.size()) {
                        throw IllegalArgumentException("source directory changed while inventoried")
                    }
                    files[relative] = buildJsonObject {
                        put("size", JsonPrimitive(childInfo.size()))
                        put("sha256", JsonPrimitive(hashed.digest().joinToString("") { "%02x".format(it) }))
                    }
                }
            }
        }

        visit(root, "")
        return CollectionRules.sortedInventory(files)
    }

    /** `checked_tar`: extract a producer archive, honouring its recorded nanosecond timestamps. */
    fun checkedTar(path: Path, destination: Path): Path {
        Files.createDirectory(destination)
        val seen = mutableSetOf<String>()
        Files.newInputStream(path).use { stream ->
            TarArchiveInputStream(stream).use { archive ->
                while (true) {
                    val item = archive.nextEntry ?: break
                    val name = item.name.removePrefix("./")
                    if (name.isEmpty() || name == ".") continue
                    CollectionRules.filePathName(name)
                    if (!seen.add(name) || !(item.isFile || item.isDirectory)) {
                        throw IllegalArgumentException("archive has duplicate or nonregular members")
                    }
                    val target = destination.resolve(name)
                    if (item.isDirectory) {
                        Files.createDirectories(target)
                        continue
                    }
                    target.parent?.let { Files.createDirectories(it) }
                    Files.newOutputStream(target).use { output ->
                        val buffer = ByteArray(1024 * 1024)
                        while (true) {
                            val read = archive.read(buffer)
                            if (read <= 0) break
                            output.write(buffer, 0, read)
                        }
                    }
                    val stamp = item.extraPaxHeaders["dyn4k.mtime_ns"]
                    if (stamp != null) {
                        if (stamp.isEmpty() || !stamp.all { it in '0'..'9' }) {
                            throw IllegalArgumentException("archive timestamp is invalid")
                        }
                        Files.setLastModifiedTime(
                            target,
                            java.nio.file.attribute.FileTime.from(
                                stamp.toLong(),
                                TimeUnit.NANOSECONDS,
                            ),
                        )
                    }
                }
            }
        }
        return destination
    }

    /** `checked_sidecar`: the archive and its `SHA-256  name` sidecar. */
    fun checkedSidecar(root: Path, stem: String): Path {
        val archive = root.resolve(stem)
        val sidecar = root.resolve(stem.removeSuffix(".tar.gz") + ".sha256")
        if (!Files.isRegularFile(archive) || !Files.isRegularFile(sidecar)) {
            throw IllegalArgumentException("archive or SHA-256 sidecar is missing")
        }
        val recorded = Fs.readText(sidecar).trim().split(Regex("\\s+"))
        if (recorded.size != 2 || !CollectionRules.SHA64.matches(recorded[0]) ||
            Path.of(recorded[1]).fileName.toString() != stem
        ) {
            throw IllegalArgumentException("archive SHA-256 sidecar is malformed")
        }
        if (digest(archive) != recorded[0]) {
            throw IllegalArgumentException("archive bytes differ from SHA-256 sidecar")
        }
        return archive
    }

    /** `inspect_artifact`: verify one producer artifact and classify its route. */
    fun inspectArtifact(
        route: String,
        root: Path,
        candidateSha: String,
        tree: String,
        extracted: Path,
        repository: Path,
        upstream: Path? = null,
    ): String {
        if (route == "full-ci" || route == "full-common") {
            val stem = "$route-$candidateSha.tar.gz"
            val archive = checkedSidecar(root, stem)
            val members = root.resolve("$route-$candidateSha.members")
            if (!Files.isRegularFile(members)) {
                throw IllegalArgumentException("$route archive member list is missing")
            }
            val declared = Fs.readText(members).lines().filter { it.isNotEmpty() }
                .map { it.trimEnd('/') }
            val actual = mutableListOf<String>()
            Files.newInputStream(archive).use { stream ->
                TarArchiveInputStream(stream).use { packed ->
                    while (true) {
                        val entry = packed.nextEntry ?: break
                        actual.add(entry.name.trimEnd('/'))
                    }
                }
            }
            if (declared != actual) {
                throw IllegalArgumentException("$route archive member list differs")
            }
            val unpacked = checkedTar(archive, extracted.resolve(route))
            val manifest = if (route == "full-ci") {
                unpacked.resolve("full-ci/lane-manifest.json")
            } else {
                unpacked.resolve("archive-index.json")
            }
            val data = StrictJson.load(Fs.readText(manifest)) as? JsonObject
                ?: throw IllegalArgumentException("$route manifest is not an object")
            if (Py.str(data["candidate_sha"]) != candidateSha) {
                throw IllegalArgumentException("$route source candidate differs")
            }
            if (route == "full-ci") {
                // `full_ci.verify_archive` lives in the compatibility port, which this module does
                // not depend on; a real full-ci bundle therefore fails closed.
                throw IllegalArgumentException(
                    "full-ci raw archive verification is not available in this module: " +
                        "run the compatibility port over ${unpacked.resolve("full-ci")}",
                )
            }
            val result = CorpusReports.verifyArchive(
                unpacked,
                repository,
                candidateSha,
                upstream,
                requireCheckout = true,
            )
            if (Py.str(result["status"]) != "PASSED") {
                throw IllegalArgumentException("full common raw archive does not verify")
            }
            return "PRODUCER_VERIFIED"
        }
        if (route.startsWith("full-hosted-")) {
            val target = route.removePrefix("full-hosted-")
            val archives = Files.newDirectoryStream(root).use { stream ->
                stream.filter { it.fileName.toString().endsWith(".tar") }.toList()
            }
            if (archives.size != 1) {
                throw IllegalArgumentException("full hosted transport archive is missing or duplicated")
            }
            val receipt = FullHosted.verifyTransportArchive(
                archives[0],
                candidateSha,
                target,
                repository,
            )
            if (Py.str(receipt["candidate_sha"]) != candidateSha) {
                throw IllegalArgumentException("full hosted source candidate differs")
            }
            return "PRODUCER_VERIFIED"
        }
        if (route == "duplicate-provider") {
            val receipt = StrictJson.load(Fs.readText(root.resolve("receipt.json"))) as? JsonObject
                ?: throw IllegalArgumentException("duplicate provider receipt is not an object")
            if (Py.str(receipt["candidate_sha"]) != candidateSha ||
                Py.str(receipt["source_tree"]) != tree
            ) {
                throw IllegalArgumentException("duplicate provider source identity differs")
            }
            IndependentGates.inventory(root, receipt)
            if (Py.str(receipt["status"]) == "PASSED") {
                val exitCode = ((receipt["process"] as? JsonObject)?.get("exit_code"))
                if (Py.equalsInt(exitCode, 0L)) {
                    throw IllegalArgumentException("forged provider success lacks failing exit")
                }
                return "PRODUCER_VERIFIED"
            }
            return "FAILED"
        }
        if (route.startsWith("publication-")) {
            val bundles = Files.newDirectoryStream(root).use { stream ->
                stream.filter { it.fileName.toString().endsWith("-publication") }.toList()
            }
            if (bundles.size != 1) {
                throw IllegalArgumentException("publication bundle is missing or duplicated")
            }
            PublicationBundle.verify(
                bundles[0],
                candidateSha,
                digest(bundles[0].resolve("manifest.json")),
            )
            return "PRODUCER_VERIFIED"
        }
        if (route.startsWith("qualification-")) {
            val manifest = StrictJson.load(
                Fs.readText(repository.resolve("tools/qualification/foundation-probes.json")),
            ) as? JsonObject
                ?: throw IllegalArgumentException("foundation probe manifest is not an object")
            ArtifactCapture.verifyBundle(root, manifest, candidateSha)
            return "PRODUCER_VERIFIED"
        }
        val identity = root.resolve("identity.txt")
        if (Files.isRegularFile(identity) &&
            "sha=$candidateSha" !in Fs.readText(identity).lines()
        ) {
            throw IllegalArgumentException("failed-route diagnostic source SHA differs")
        }
        return "RETAINED_UNVERIFIED"
    }

    /** `_transport_format`: the producer format adapter, or the retained-raw verdict. */
    fun transportFormat(
        normalized: Path,
        bindings: List<JsonObject>,
        candidateSha: String,
        manifest: JsonObject,
    ): String {
        val stage = normalized.resolve("build/stage-receipt.json")
        val capture = normalized.resolve("captures/compatibility/result.json")
        if (!Files.isRegularFile(stage) || !Files.isRegularFile(capture)) {
            return "unsupported producer format; raw bytes retained without a gate adapter"
        }
        val stageReceipt = strictJson(stage)
        val result = strictJson(capture)
        if (Py.str(stageReceipt["candidate_sha"]) != candidateSha ||
            Py.str(result["source_sha"]) != candidateSha ||
            Py.str(result["format"]) != "portable-mobile-capture-v1"
        ) {
            throw IllegalArgumentException("mobile capture source identity differs")
        }
        val target = Py.str(result["target"])
        val targets = (stageReceipt["targets"] as? JsonArray)?.mapNotNull { Py.str(it) } ?: emptyList()
        val lanes = manifest["lanes"] as? JsonObject ?: JsonObject(emptyMap())
        val laneTargets = lanes.values.mapNotNull { (it as? JsonObject)?.let { lane -> Py.str(lane["target"]) } }
        if (target !in targets || target !in laneTargets) {
            throw IllegalArgumentException("mobile capture target identity differs")
        }
        for (binding in bindings) {
            val lane = Py.str(binding["lane"])
            val expected = if (lane == null) {
                Py.str(binding["target"])
            } else {
                Py.str((lanes[lane] as? JsonObject)?.get("target"))
            }
            if (expected != null && expected != target) {
                throw IllegalArgumentException("bound lane or target differs from mobile capture")
            }
        }
        return "portable-mobile-capture-v1 source and target bound; " +
            "no complete independent gate adapter or signed audit"
    }

    /** `collect`: the 112-lane collection ledger over the downloaded producer artifacts. */
    fun collect(
        repository: Path,
        candidateSha: String,
        artifacts: List<Pair<String, String>>,
        output: Path,
        upstream: Path? = null,
        sourceIndex: Path? = null,
        repositoryName: String = "rubixhacker/dyn4k",
        runId: Long? = null,
        runAttempt: Long? = null,
        githubToken: String? = null,
        artifactsDir: Path? = null,
        inspect: ((String, Path, String, String, Path, Path, Path?) -> String)? = null,
        io: CollectionIo = CollectionIo.default,
    ): JsonObject {
        val tree = sourceTree(repository, candidateSha)
        val manifest = IndependentGates.loadApprovedManifest(repository)
        val lanes = manifest["lanes"] as? JsonObject ?: JsonObject(emptyMap())
        if (lanes.size != CollectionRules.REQUIRED_LANES) {
            throw IllegalArgumentException("approved lane inventory is incomplete")
        }
        if (Files.exists(output)) throw FileAlreadyExistsException(output.toString())
        Files.createDirectories(output)
        val extracted = output.resolve("extracted")
        Files.createDirectory(extracted)
        val rows = mutableListOf<JsonObject>()
        val seen = mutableSetOf<String>()
        var stagedAudit: JsonObject? = null
        val inspected = inspect ?: { route, root, sha, sourceTree, extract, repo, source ->
            inspectArtifact(route, root, sha, sourceTree, extract, repo, source)
        }
        for ((name, rootText) in artifacts) {
            val root = Path.of(rootText)
            val row = LinkedHashMap<String, JsonElement>()
            row["name"] = JsonPrimitive(name)
            row["route"] = JsonNull
            row["status"] = JsonPrimitive("FAILED")
            try {
                row["files"] = filesIn(root, io)
                val route = CollectionRules.artifactRoute(name, candidateSha)
                row["route"] = JsonPrimitive(route)
                if (!seen.add(route)) {
                    throw IllegalArgumentException("duplicate producer artifact route: $route")
                }
                row["status"] = JsonPrimitive(
                    inspected(route, root, candidateSha, tree, extracted, repository, upstream),
                )
                if (route == "publication-ubuntu" && Py.str(row["status"]) == "PRODUCER_VERIFIED") {
                    val bundle = Files.newDirectoryStream(root).use { stream ->
                        stream.filter { it.fileName.toString().endsWith("-publication") }.toList()
                    }.firstOrNull()
                        ?: throw IllegalArgumentException("publication bundle is missing")
                    stagedAudit = StrictJson.load(
                        Fs.readText(bundle.resolve("artifact-audit.json")),
                    ) as? JsonObject
                        ?: throw IllegalArgumentException("staged audit is not an object")
                }
            } catch (error: Exception) {
                if (!isCaught(error)) throw error
                row["reason"] = JsonPrimitive(error.message ?: error.toString())
            }
            rows.add(JsonObject(row))
        }
        val missing = (CollectionRules.REQUIRED.toSet() - seen).sortedWith(CanonicalText::compare)
        var crossRun: JsonObject? = null
        if (sourceIndex != null) {
            try {
                val directory = artifactsDir ?: artifacts.firstOrNull()?.second?.let { Path.of(it).parent }
                    ?: output.parent.resolve("absent-artifacts")
                crossRun = snapshotSourceIndex(
                    sourceIndex,
                    candidateSha,
                    tree,
                    manifest,
                    directory,
                    output,
                    repositoryName,
                    runId,
                    runAttempt,
                    githubToken,
                    io,
                )
            } catch (error: Exception) {
                if (!isCaught(error)) throw error
                val failed = LinkedHashMap<String, JsonElement>()
                failed["schema"] = JsonPrimitive(1)
                failed["candidate_sha"] = JsonPrimitive(candidateSha)
                failed["status"] = JsonPrimitive("FAILED")
                failed["reason"] = JsonPrimitive(error.message ?: error.toString())
                try {
                    val rejected = safeSourcePath(sourceIndex)
                    if (Files.isRegularFile(rejected)) {
                        val bytes = anchoredRead(rejected)
                        Files.write(output.resolve("source-index.rejected"), bytes)
                        failed["rejected_index_sha256"] =
                            JsonPrimitive(digest(output.resolve("source-index.rejected")))
                    }
                } catch (secondary: Exception) {
                    if (!isCaught(secondary)) throw secondary
                }
                crossRun = JsonObject(failed)
            }
        }
        val inputs = CollectionRules.unsignedInputs(
            manifest,
            artifacts.map { it.first to Path.of(it.second).toAbsolutePath().normalize().toString() },
            rows,
        )
        Fs.writeText(output.resolve("assembly-inputs.json"), PyJson.render(inputs) + "\n")
        val targetHashes: JsonObject = if (stagedAudit != null) {
            Fs.writeText(output.resolve("staged-audit.json"), PyJson.render(stagedAudit) + "\n")
            CollectionRules.targetBinaryHashes(
                stagedAudit["artifacts"] as? JsonArray ?: JsonArray(emptyList()),
            )
        } else {
            JsonObject(emptyMap())
        }
        val laneInputs = LinkedHashMap<String, JsonElement>()
        for ((laneId, element) in lanes) {
            val lane = element as? JsonObject ?: continue
            laneInputs[laneId] = CollectionRules.candidateLaneInput(
                laneId,
                lane,
                candidateSha,
                targetHashes.keys.associateWith { target ->
                    targetHashes[target] as? JsonObject ?: JsonObject(emptyMap())
                },
            )
        }
        val candidateInputs = buildJsonObject {
            put("schema", JsonPrimitive(1))
            put("candidate_sha", JsonPrimitive(candidateSha))
            put("suite_manifest_sha256", JsonPrimitive(IndependentGates.digest(manifest)))
            put(
                "audit_manifest_sha256",
                stagedAudit?.let { JsonPrimitive(FullCorpus.canonicalDigest(it)) } ?: JsonNull,
            )
            put("status", JsonPrimitive("INCOMPLETE"))
            put("lanes", JsonObject(laneInputs))
        }
        Fs.writeText(
            output.resolve("candidate-manifest-inputs.json"),
            PyJson.render(candidateInputs) + "\n",
        )
        val report = LinkedHashMap<String, JsonElement>()
        report["schema"] = JsonPrimitive(1)
        report["candidate_sha"] = JsonPrimitive(candidateSha)
        report["source_tree"] = JsonPrimitive(tree)
        report["required_lanes"] = JsonPrimitive(CollectionRules.REQUIRED_LANES)
        report["artifacts"] = JsonArray(rows)
        report["missing_artifacts"] = JsonArray(missing.map { JsonPrimitive(it) })
        report["independent_signature"] = JsonPrimitive("MISSING")
        val failed = rows.any { Py.str(it["status"]) == "FAILED" } ||
            (crossRun != null && Py.str(crossRun["status"]) == "FAILED")
        report["status"] = JsonPrimitive(if (failed) "FAILED" else "NOT_RUN")
        report["reason"] = JsonPrimitive(
            "signed external audit and complete gate routes are absent",
        )
        if (crossRun != null) report["cross_run"] = crossRun
        report["external_inputs_required"] = JsonArray(
            listOf(
                "all 112 exact-source common gate archives and runtime identities",
                "independently audited archive digests and 21-target artifact hashes",
                "complete candidate manifest bound to a verified staged audit",
                "exact staged repository bytes available to the public qualifier",
                "detached Ed25519 audit signature and pinned trusted public-key fingerprint",
            ).map { JsonPrimitive(it) },
        )
        val value = JsonObject(report)
        Fs.writeText(output.resolve("collection.json"), PyJson.render(value) + "\n")
        return value
    }

    /** `verify_collection`: every recorded byte still matches the supplied artifacts. */
    fun verifyCollection(
        repository: Path,
        candidateSha: String,
        artifacts: List<Pair<String, String>>,
        output: Path,
        io: CollectionIo = CollectionIo.default,
    ): Boolean {
        val report = StrictJson.load(Fs.readText(output.resolve("collection.json"))) as? JsonObject
            ?: throw IllegalArgumentException("collection report is not an object")
        if (Py.str(report["candidate_sha"]) != candidateSha ||
            Py.str(report["source_tree"]) != sourceTree(repository, candidateSha) ||
            !Py.equalsInt(report["required_lanes"], CollectionRules.REQUIRED_LANES.toLong())
        ) {
            throw IllegalArgumentException("collected source identity differs")
        }
        val rows = report["artifacts"] as? JsonArray
        if (rows == null || rows.size != artifacts.size ||
            rows.map { Py.str((it as JsonObject)["name"]) } != artifacts.map { it.first }
        ) {
            throw IllegalArgumentException("collected producer artifact set differs")
        }
        for ((index, element) in rows.withIndex()) {
            val row = element as JsonObject
            val root = Path.of(artifacts[index].second)
            val files = row["files"]
            if (files != null && files !is JsonNull && filesIn(root, io) != files) {
                throw IllegalArgumentException(
                    "collected raw artifact bytes differ: ${Py.str(row["name"])}",
                )
            }
        }
        val inputs = StrictJson.load(
            Fs.readText(output.resolve("assembly-inputs.json")),
        )
        val approved = IndependentGates.loadApprovedManifest(repository)
        val expected = CollectionRules.unsignedInputs(
            approved,
            artifacts.map { it.first to Path.of(it.second).toAbsolutePath().normalize().toString() },
            rows.map { it as JsonObject },
        )
        if (inputs != expected) {
            throw IllegalArgumentException("unsigned 112-lane input map differs")
        }
        val crossRun = report["cross_run"] as? JsonObject
        if (crossRun != null) {
            if ("sources" in crossRun) {
                verifySourceSnapshot(output, candidateSha, Py.str(report["source_tree"])!!, io)
                if (strictJson(output.resolve("cross-run-ledger.json")) != crossRun) {
                    throw IllegalArgumentException("cross-run source ledger differs from collection")
                }
            } else if ("rejected_index_sha256" in crossRun) {
                if (digest(output.resolve("source-index.rejected")) !=
                    Py.str(crossRun["rejected_index_sha256"])
                ) {
                    throw IllegalArgumentException("rejected source index bytes differ")
                }
            }
        }
        return true
    }

    /** `snapshot_source_index`: freeze and normalize every cross-run source. */
    fun snapshotSourceIndex(
        indexPath: Path,
        candidateSha: String,
        tree: String,
        manifest: JsonObject,
        artifactsDir: Path,
        output: Path,
        repositoryName: String = "rubixhacker/dyn4k",
        runId: Long? = null,
        runAttempt: Long? = null,
        githubToken: String? = null,
        io: CollectionIo = CollectionIo.default,
    ): JsonObject {
        val originalIndex = anchoredRead(indexPath)
        val index = strictJsonBytes(originalIndex)
        CollectionRules.validateIndex(
            index,
            candidateSha,
            tree,
            manifest,
            repositoryName,
            runId,
            runAttempt,
            githubToken == null,
            ::safeSourcePathText,
            IndependentGates.GLOBAL_GATES,
        )
        Files.write(output.resolve("source-index.json"), originalIndex)
        Files.createDirectories(output.resolve("raw/sources"))
        Files.createDirectory(output.resolve("normalized"))
        val rows = mutableListOf<JsonObject>()
        val sources = index["sources"] as JsonArray
        for (element in sources) {
            val source = element as JsonObject
            val sourceId = Py.str(source["id"])!!
            val origin = source["origin"] as JsonObject
            val pin = source["transport"] as JsonObject
            val folder = output.resolve("raw/sources").resolve(sourceId)
            Files.createDirectory(folder)
            val row = LinkedHashMap<String, JsonElement>()
            row["id"] = JsonPrimitive(sourceId)
            row["origin"] = origin
            row["transport"] = pin
            row["status"] = JsonPrimitive("FAILED")
            try {
                val kind = Py.str(origin["kind"])
                val sourcePath = when (kind) {
                    "local" -> safeSourcePathText(Py.str(origin["path"]) ?: "")
                    "same_run" -> safeSourcePath(artifactsDir.resolve(Py.str(origin["name"])!!))
                    else -> null
                }
                if (sourcePath != null &&
                    (isWithin(sourcePath, output) || isWithin(output, sourcePath))
                ) {
                    throw IllegalArgumentException(
                        "source and collection output cannot contain each other",
                    )
                }
                val normalized: Path
                if (Py.str(pin["format"]) == "directory") {
                    if (sourcePath == null) throw IllegalArgumentException("GitHub Actions source must be a ZIP")
                    val identity = pathIdentity(sourcePath)
                    val before = io.inventory(sourcePath)
                    val frozen = folder.resolve("original-directory")
                    copyDirectory(sourcePath, frozen, io)
                    val after = io.inventory(sourcePath)
                    val copied = io.inventory(frozen)
                    row["raw_inventory"] = copied
                    if (identity != pathIdentity(sourcePath) || before != after || before != copied) {
                        throw IllegalArgumentException("source directory changed while copied")
                    }
                    if (copied != pin["files"] || CollectionRules.inventoryDigest(copied) !=
                        Py.str(pin["inventory_sha256"])
                    ) {
                        throw IllegalArgumentException("source directory byte inventory differs")
                    }
                    normalized = frozen
                } else {
                    val frozen = folder.resolve("original")
                    if (sourcePath == null) {
                        row["api"] = githubArtifact(
                            origin,
                            candidateSha,
                            githubToken ?: "",
                            frozen,
                            Py.int(pin["size"] ?: JsonPrimitive(0)),
                        )
                    } else {
                        if (!Files.isRegularFile(sourcePath)) {
                            throw IllegalArgumentException("source archive is missing")
                        }
                        if (Files.size(sourcePath) > io.maxSourceBytes) {
                            throw IllegalArgumentException("source archive exceeds byte bound")
                        }
                        val before = Triple(
                            pathIdentity(sourcePath),
                            Files.size(sourcePath),
                            io.digest(sourcePath, MAX_SOURCE_BYTES),
                        )
                        io.copyRegular(sourcePath, frozen, MAX_SOURCE_BYTES, true)
                        val after = Triple(
                            pathIdentity(sourcePath),
                            Files.size(sourcePath),
                            io.digest(sourcePath, MAX_SOURCE_BYTES),
                        )
                        if (before != after) {
                            throw IllegalArgumentException("source archive changed while copied")
                        }
                    }
                    row["raw_size"] = JsonPrimitive(Files.size(frozen))
                    row["raw_sha256"] = JsonPrimitive(io.digest(frozen, MAX_SOURCE_BYTES))
                    if (!Py.equalsInt(row["raw_size"], Py.int(pin["size"] ?: JsonPrimitive(0))) ||
                        Py.str(row["raw_sha256"]) != Py.str(pin["sha256"])
                    ) {
                        throw IllegalArgumentException("source archive bytes differ from exact pin")
                    }
                    normalized = output.resolve("normalized").resolve(sourceId)
                    row["normalized_inventory"] = extractTransport(
                        frozen,
                        Py.str(pin["format"])!!,
                        normalized,
                        io,
                    )
                }
                val bindings = (index["bindings"] as JsonArray).map { it as JsonObject }
                    .filter { Py.str(it["source_id"]) == sourceId }
                val reasons = mutableListOf<String>()
                for (binding in bindings) {
                    val memberRoot = Py.str(binding["member_root"])
                    val root = if (memberRoot != null) {
                        memberRoot.split('/').fold(normalized) { base, part -> base.resolve(part) }
                    } else {
                        normalized
                    }
                    if (!Files.isDirectory(root)) {
                        throw IllegalArgumentException("bound member root is missing")
                    }
                    reasons.add(transportFormat(root, listOf(binding), candidateSha, manifest))
                }
                row["reason"] = JsonPrimitive(
                    reasons.toSet().sortedWith(CanonicalText::compare).joinToString("; "),
                )
                row["status"] = JsonPrimitive("NOT_RUN")
            } catch (error: Exception) {
                if (!isCaught(error)) throw error
                row["reason"] = JsonPrimitive(error.message ?: error.toString())
                val incomplete = output.resolve("normalized").resolve(sourceId)
                if (Files.isDirectory(incomplete) && "normalized_inventory" !in row) {
                    deleteRecursively(incomplete)
                }
                val partial = folder.resolve("original")
                if (Files.isRegularFile(partial)) {
                    row["raw_size"] = JsonPrimitive(Files.size(partial))
                    row["raw_sha256"] = JsonPrimitive(io.digest(partial, MAX_SOURCE_BYTES))
                }
                val partialDirectory = folder.resolve("original-directory")
                if (Files.isDirectory(partialDirectory)) {
                    try {
                        row["raw_inventory"] = io.inventory(partialDirectory)
                    } catch (error2: IllegalArgumentException) {
                        deleteRecursively(partialDirectory)
                        row["raw_inventory"] = JsonNull
                    }
                }
            }
            rows.add(JsonObject(row))
        }
        val ledger = LinkedHashMap<String, JsonElement>()
        ledger["schema"] = JsonPrimitive(1)
        ledger["candidate_sha"] = JsonPrimitive(candidateSha)
        ledger["source_tree"] = JsonPrimitive(tree)
        ledger["index_sha256"] = JsonPrimitive(Sha256.of(originalIndex))
        ledger["sources"] = JsonArray(rows)
        ledger["status"] = JsonPrimitive(
            if (rows.any { Py.str(it["status"]) == "FAILED" }) "FAILED" else "NOT_RUN",
        )
        val value = JsonObject(ledger)
        Fs.writeText(output.resolve("cross-run-ledger.json"), PyJson.render(value) + "\n")
        return value
    }

    /** `verify_source_snapshot`: the frozen cross-run index, ledger, and raw sources. */
    fun verifySourceSnapshot(
        output: Path,
        candidateSha: String,
        tree: String,
        io: CollectionIo = CollectionIo.default,
    ): Boolean {
        if (Files.isSymbolicLink(output.resolve("source-index.json")) ||
            Files.isSymbolicLink(output.resolve("cross-run-ledger.json"))
        ) {
            throw IllegalArgumentException("frozen source index or ledger is symbolic")
        }
        val ledger = strictJson(output.resolve("cross-run-ledger.json"))
        val indexBytes = anchoredRead(output.resolve("source-index.json"))
        val index = strictJsonBytes(indexBytes)
        val sources = index["sources"] as JsonArray
        val ledgerSources = ledger["sources"] as JsonArray
        if (Py.str(ledger["candidate_sha"]) != candidateSha ||
            Py.str(ledger["source_tree"]) != tree ||
            Sha256.of(indexBytes) != Py.str(ledger["index_sha256"]) ||
            sources.map { Py.str((it as JsonObject)["id"]) } !=
            ledgerSources.map { Py.str((it as JsonObject)["id"]) }
        ) {
            throw IllegalArgumentException("frozen cross-run source index or ledger differs")
        }
        if (Files.isSymbolicLink(output.resolve("raw/sources"))) {
            throw IllegalArgumentException("frozen source set is symbolic")
        }
        val folders = Files.newDirectoryStream(output.resolve("raw/sources")).use { stream ->
            stream.map { it.fileName.toString() }.toSet()
        }
        if (folders != sources.mapNotNull { Py.str((it as JsonObject)["id"]) }.toSet()) {
            throw IllegalArgumentException("frozen source set differs")
        }
        for ((index_pos, sourceElement) in sources.withIndex()) {
            val source = sourceElement as JsonObject
            val row = ledgerSources[index_pos] as JsonObject
            val folder = output.resolve("raw/sources").resolve(Py.str(source["id"])!!)
            if (Files.isSymbolicLink(folder) || !Files.isDirectory(folder)) {
                throw IllegalArgumentException("frozen source folder is missing or symbolic")
            }
            val pin = source["transport"] as JsonObject
            if (Py.str(pin["format"]) == "directory") {
                val path = folder.resolve("original-directory")
                val recorded = row["raw_inventory"]
                val expected = if (recorded is JsonObject) setOf("original-directory") else emptySet()
                if (children(folder) != expected) {
                    throw IllegalArgumentException("frozen source has missing or unrecorded files")
                }
                if (expected.isNotEmpty() && io.inventory(path) != recorded) {
                    throw IllegalArgumentException("frozen source directory bytes differ")
                }
                if (Py.str(row["status"]) == "NOT_RUN" &&
                    (expected.isEmpty() || recorded != pin["files"])
                ) {
                    throw IllegalArgumentException("frozen source directory differs from pin")
                }
            } else {
                val path = folder.resolve("original")
                val recorded = "raw_size" in row && "raw_sha256" in row
                if (("raw_size" in row) != ("raw_sha256" in row)) {
                    throw IllegalArgumentException("frozen source archive ledger is incomplete")
                }
                val expected = if (recorded) setOf("original") else emptySet()
                if (children(folder) != expected) {
                    throw IllegalArgumentException("frozen source has missing or unrecorded files")
                }
                if (recorded && (Files.isSymbolicLink(path) || !Files.isRegularFile(path) ||
                        !Py.equalsInt(row["raw_size"], Files.size(path)) ||
                        io.digest(path, MAX_SOURCE_BYTES) != Py.str(row["raw_sha256"]))
                ) {
                    throw IllegalArgumentException("frozen source archive bytes differ")
                }
                if (Py.str(row["status"]) == "NOT_RUN" &&
                    (!recorded || !Py.equalsInt(row["raw_size"], Py.int(pin["size"] ?: JsonPrimitive(0))) ||
                        Py.str(row["raw_sha256"]) != Py.str(pin["sha256"]))
                ) {
                    throw IllegalArgumentException("frozen source archive differs from pin")
                }
                val normalized = output.resolve("normalized").resolve(Py.str(source["id"])!!)
                val normalizedInventory = row["normalized_inventory"]
                if (normalizedInventory != null && normalizedInventory !is JsonNull &&
                    io.inventory(normalized) != normalizedInventory
                ) {
                    throw IllegalArgumentException("normalized source archive bytes differ")
                }
            }
        }
        return true
    }

    /**
     * `ingest_external`: verify the signed external audit inputs and run the recording adapter.
     *
     * The reference shells out to `qualify.py record`; this port does the same, because the gate
     * adapter is still the Python command.
     */
    fun ingestExternal(
        repository: Path,
        candidateSha: String,
        artifacts: List<Pair<String, String>>,
        output: Path,
        auditInputs: Path,
        trustedKeySha256: String? = null,
        independentPerformanceKey: Path? = null,
        performanceKeySha256: String? = null,
        python: String = "python3",
        io: CollectionIo = CollectionIo.default,
    ): JsonObject {
        verifyCollection(repository, candidateSha, artifacts, output, io)
        val names = listOf(
            "archive-map.json", "audit.json", "audit.sig", "public.pem",
            "candidate-manifest.json", "staged-audit.json", "evidence.json",
        )
        val missing = names.filter { !Files.isRegularFile(auditInputs.resolve(it)) }.toMutableList()
        if (!CollectionRules.SHA64.matches(trustedKeySha256 ?: "")) {
            missing.add("externally pinned trusted Ed25519 key SHA-256")
        }
        if (!Files.isDirectory(repository.resolve("build/staging-repository"))) {
            missing.add("verified staged repository bytes at build/staging-repository")
        }
        if (independentPerformanceKey != null) {
            if (!CollectionRules.SHA64.matches(performanceKeySha256 ?: "")) {
                missing.add("externally pinned performance key SHA-256")
            } else if (!Files.isRegularFile(safeSourcePath(independentPerformanceKey))) {
                missing.add("independently supplied performance key")
            }
        }
        val result = LinkedHashMap<String, JsonElement>()
        result["candidate_sha"] = JsonPrimitive(candidateSha)
        result["status"] = JsonPrimitive("NOT_RUN")
        result["missing_external_inputs"] = JsonArray(missing.map { JsonPrimitive(it) })
        if (missing.isNotEmpty()) {
            Fs.writeText(
                output.resolve("audit-ingestion.json"),
                PyJson.render(JsonObject(result)) + "\n",
            )
            return JsonObject(result)
        }
        val stable = output.resolve("external-inputs")
        Files.createDirectory(stable)
        val originalHashes = names.associateWith { io.digest(auditInputs.resolve(it), null) }
        for (name in names) {
            Files.copy(
                auditInputs.resolve(name),
                stable.resolve(name),
                StandardCopyOption.REPLACE_EXISTING,
            )
            if (io.digest(stable.resolve(name), null) != originalHashes[name]) {
                throw IllegalArgumentException("external audit input changed while copied: $name")
            }
        }
        val supplied = strictJson(stable.resolve("archive-map.json"))
        val approved = IndependentGates.loadApprovedManifest(repository)
        if (!Py.equalsInt(supplied["schema"], 1L) ||
            Py.str(supplied["candidate_sha"]) != candidateSha
        ) {
            throw IllegalArgumentException(
                "external signed archive map lacks exact 112-lane source binding",
            )
        }
        val snapshot = snapshotExternalReferences(supplied, approved, stable, io)
        val snapshotMap = snapshot.first
        val snapshots = snapshot.second
        val snapshotMapSha256 = io.digest(snapshotMap, null)
        var performanceCopy: Path? = null
        if (independentPerformanceKey != null) {
            val key = safeSourcePath(independentPerformanceKey)
            if (isWithin(key, auditInputs) || isWithin(key, output) ||
                artifacts.any { isWithin(key, Path.of(it.second)) }
            ) {
                throw IllegalArgumentException("performance key must come from outside producer inputs")
            }
            performanceCopy = stable.resolve("independent-performance-key.pem")
            io.copyRegular(key, performanceCopy, MAX_SOURCE_BYTES, true)
            if (io.digest(key, null) != performanceKeySha256 ||
                io.digest(performanceCopy, null) != performanceKeySha256
            ) {
                throw IllegalArgumentException("independent performance key bytes differ from external pin")
            }
        }
        for (name in listOf("candidate-manifest.json", "staged-audit.json")) {
            if (Py.str((strictJson(stable.resolve(name)) as JsonObject)["candidate_sha"]) != candidateSha) {
                throw IllegalArgumentException("external $name belongs to another candidate")
            }
        }
        if (Files.exists(output.resolve("signed-runtime-matrix.json"))) {
            throw IllegalArgumentException("signed adapter result already exists")
        }
        val command = mutableListOf(
            python, repoFile(repository, "tools/qualification/qualify.py"), "record",
            "--candidate-sha", candidateSha,
            "--evidence", stable.resolve("evidence.json").toString(),
            "--audit", stable.resolve("staged-audit.json").toString(),
            "--candidate-manifest", stable.resolve("candidate-manifest.json").toString(),
            "--independent-archives", snapshotMap.toString(),
            "--independent-audit", stable.resolve("audit.json").toString(),
            "--independent-audit-signature", stable.resolve("audit.sig").toString(),
            "--trusted-audit-public-key", stable.resolve("public.pem").toString(),
            "--trusted-audit-key-sha256", trustedKeySha256 ?: "",
            "--output", output.resolve("signed-runtime-matrix.json").toString(),
        )
        if (performanceCopy != null) {
            command.add("--independent-performance-key")
            command.add(performanceCopy.toString())
        }
        val run = io.runAdapter(command, repository)
        val stdout = run.stdout
        val stderr = run.stderr
        val exit = run.exitCode
        for (name in names) {
            if (io.digest(auditInputs.resolve(name), null) != originalHashes[name] ||
                io.digest(stable.resolve(name), null) != originalHashes[name]
            ) {
                throw IllegalArgumentException("external audit input changed during verification")
            }
        }
        if (io.digest(snapshotMap, null) != snapshotMapSha256) {
            throw IllegalArgumentException("frozen external archive map changed during verification")
        }
        verifyCollection(repository, candidateSha, artifacts, output, io)
        verifyExternalReferences(snapshots, io)
        if (performanceCopy != null && io.digest(performanceCopy, null) != performanceKeySha256) {
            throw IllegalArgumentException("frozen independent performance key bytes differ")
        }
        Files.write(output.resolve("signed-adapter.stdout"), stdout)
        Files.write(output.resolve("signed-adapter.stderr"), stderr)
        result["status"] = JsonPrimitive(
            if (exit != 0 && !Files.isRegularFile(output.resolve("signed-runtime-matrix.json"))) {
                "FAILED"
            } else {
                "NOT_RUN"
            },
        )
        result["adapter_exit"] = JsonPrimitive(exit)
        result["missing_external_inputs"] = JsonArray(emptyList())
        result["trusted_key_sha256"] = trustedKeySha256?.let { JsonPrimitive(it) } ?: JsonNull
        result["input_sha256"] = JsonObject(originalHashes.mapValues { JsonPrimitive(it.value) })
        result["referenced_snapshots"] = JsonObject(snapshots.mapValues { (_, value) -> value })
        result["performance_key_sha256"] = performanceKeySha256?.let { JsonPrimitive(it) } ?: JsonNull
        if (Files.isRegularFile(output.resolve("signed-runtime-matrix.json"))) {
            val matrix = strictJson(output.resolve("signed-runtime-matrix.json"))
            if (Py.str(matrix["candidate_sha"]) != candidateSha ||
                !Py.equalsInt(matrix["total"], CollectionRules.REQUIRED_LANES.toLong())
            ) {
                throw IllegalArgumentException("signed adapter returned an incomplete candidate matrix")
            }
            val counts = matrix["counts"] ?: JsonNull
            result["counts"] = counts
            if (exit == 0 && Py.equalsInt((counts as? JsonObject)?.get("PASSED"), 112L)) {
                result["status"] = JsonPrimitive("PASSED")
            } else if (Py.truthy((counts as? JsonObject)?.get("FAILED"))) {
                result["status"] = JsonPrimitive("FAILED")
            }
        }
        val value = JsonObject(result)
        Fs.writeText(output.resolve("audit-ingestion.json"), PyJson.render(value) + "\n")
        return value
    }

    /** `_snapshot_external_references`: freeze every externally referenced archive. */
    fun snapshotExternalReferences(
        archiveMap: JsonObject,
        approved: JsonObject,
        stable: Path,
        io: CollectionIo = CollectionIo.default,
    ): Pair<Path, Map<String, JsonElement>> {
        val lanes = approved["lanes"] as? JsonObject ?: JsonObject(emptyMap())
        val mapLanes = archiveMap["lanes"] as? JsonObject
        if (!Py.equalsInt(archiveMap["schema"], 1L) || mapLanes == null ||
            mapLanes.keys != lanes.keys
        ) {
            throw IllegalArgumentException(
                "external signed archive map lacks exact 112-lane source binding",
            )
        }
        val references = stable.resolve("references")
        Files.createDirectory(references)
        val rewritten = LinkedHashMap<String, JsonElement>()
        rewritten["schema"] = JsonPrimitive(1)
        rewritten["candidate_sha"] = archiveMap["candidate_sha"] ?: JsonNull
        val rewrittenLanes = LinkedHashMap<String, JsonElement>()
        val snapshots = LinkedHashMap<String, JsonElement>()
        for ((laneId, element) in mapLanes) {
            val archives = element as? JsonObject
                ?: throw IllegalArgumentException("external lane archive map is invalid")
            val lane = lanes[laneId] as? JsonObject
            val allowed = mutableSetOf<String>()
            (lane?.get("required_gates") as? JsonArray)?.mapNotNullTo(allowed) { Py.str(it) }
            allowed.addAll(IndependentGates.GLOBAL_GATES)
            if ((archives.keys - allowed).isNotEmpty()) {
                throw IllegalArgumentException("external archive map names an unapproved gate")
            }
            val laneMap = LinkedHashMap<String, JsonElement>()
            for ((gate, selected) in archives) {
                val source = safeSourcePathText(Py.str(selected) ?: "")
                if (!Files.exists(source)) {
                    throw IllegalArgumentException("external referenced archive is missing")
                }
                if (isWithin(source, stable) || isWithin(stable, source)) {
                    throw IllegalArgumentException(
                        "external archive and snapshot cannot contain each other",
                    )
                }
                val resolved = source.toAbsolutePath().normalize().toString()
                if (resolved !in snapshots) {
                    val frozen = references.resolve(snapshots.size.toString())
                    val identity: JsonObject
                    if (Files.isDirectory(source)) {
                        val identityBefore = pathIdentity(source)
                        val before = io.inventory(source)
                        copyDirectory(source, frozen, io)
                        val after = io.inventory(source)
                        val copied = io.inventory(frozen)
                        if (identityBefore != pathIdentity(source) || before != after ||
                            before != copied
                        ) {
                            throw IllegalArgumentException("external archive directory changed while copied")
                        }
                        identity = buildJsonObject {
                            put("kind", JsonPrimitive("directory"))
                            put("files", copied)
                            put("inventory_sha256", JsonPrimitive(CollectionRules.inventoryDigest(copied)))
                        }
                    } else if (Files.isRegularFile(source)) {
                        if (Files.size(source) > io.maxSourceBytes) {
                            throw IllegalArgumentException("external archive exceeds byte bound")
                        }
                        val before = Triple(
                            pathIdentity(source),
                            Files.size(source),
                            io.digest(source, MAX_SOURCE_BYTES),
                        )
                        io.copyRegular(source, frozen, MAX_SOURCE_BYTES, true)
                        val after = Triple(
                            pathIdentity(source),
                            Files.size(source),
                            io.digest(source, MAX_SOURCE_BYTES),
                        )
                        if (before != after ||
                            before.second != Files.size(frozen) ||
                            before.third != io.digest(frozen, MAX_SOURCE_BYTES)
                        ) {
                            throw IllegalArgumentException("external archive changed while copied")
                        }
                        identity = buildJsonObject {
                            put("kind", JsonPrimitive("file"))
                            put("size", JsonPrimitive(before.second))
                            put("sha256", JsonPrimitive(before.third))
                        }
                    } else {
                        throw IllegalArgumentException("external archive is nonregular")
                    }
                    snapshots[resolved] = buildJsonObject {
                        put("frozen", JsonPrimitive(frozen.toString()))
                        put("identity", identity)
                    }
                }
                laneMap[gate] = JsonPrimitive(
                    ((snapshots[resolved] as JsonObject)["frozen"] as JsonPrimitive).content,
                )
            }
            rewrittenLanes[laneId] = JsonObject(laneMap)
        }
        rewritten["lanes"] = JsonObject(rewrittenLanes)
        val snapshotMap = stable.resolve("archive-map.snapshot.json")
        Fs.writeText(snapshotMap, PyJson.render(JsonObject(rewritten)) + "\n")
        return snapshotMap to snapshots
    }

    /** `_verify_external_references`: the frozen external archives still hold their bytes. */
    fun verifyExternalReferences(
        snapshots: Map<String, JsonElement>,
        io: CollectionIo = CollectionIo.default,
    ) {
        for (element in snapshots.values) {
            val item = element as JsonObject
            val path = Path.of(Py.str(item["frozen"])!!)
            val identity = item["identity"] as JsonObject
            if (Py.str(identity["kind"]) == "file") {
                if (!Files.isRegularFile(path) || Files.isSymbolicLink(path) ||
                    !Py.equalsInt(identity["size"], Files.size(path)) ||
                    io.digest(path, null) != Py.str(identity["sha256"])
                ) {
                    throw IllegalArgumentException("frozen external archive file bytes differ")
                }
            } else if (io.inventory(path) != identity["files"] ||
                CollectionRules.inventoryDigest(io.inventory(path)) !=
                Py.str(identity["inventory_sha256"])
            ) {
                throw IllegalArgumentException("frozen external archive directory bytes differ")
            }
        }
    }

    // ------------------------------------------------------------------------------------
    // Transport extraction, copying, and the anchored reads
    // ------------------------------------------------------------------------------------

    /** `_extract_transport`: unpack a ZIP or TAR producer transport and inventory the result. */
    fun extractTransport(
        packed: Path,
        format: String,
        destination: Path,
        io: CollectionIo = CollectionIo.default,
    ): JsonObject {
        Files.createDirectory(destination)
        val seen = mutableSetOf<String>()
        var total = 0L
        if (format == "zip") {
            ZipFile.builder().setPath(packed).get().use { archive ->
                val members = archive.entries.toList()
                if (members.size > io.maxMembers) {
                    throw IllegalArgumentException("ZIP member count exceeds bound")
                }
                for (member in members) {
                    val name = member.name.trimEnd('/')
                    CollectionRules.filePathName(name)
                    if (!seen.add(name)) {
                        throw IllegalArgumentException("duplicate archive member")
                    }
                    val mode = (member.unixMode and 0xF000)
                    val isDirectory = member.isDirectory
                    val expected = if (isDirectory) 0x4000 else 0x8000
                    if (mode != 0 && mode != expected) {
                        throw IllegalArgumentException("nonregular ZIP member")
                    }
                    total += member.size
                    if (total > io.maxExpandedBytes) {
                        throw IllegalArgumentException("ZIP expanded bytes exceed bound")
                    }
                    val target = destination.resolve(name)
                    if (isDirectory) {
                        Files.createDirectories(target)
                    } else {
                        target.parent?.let { Files.createDirectories(it) }
                        archive.getInputStream(member).use { input ->
                            Files.newOutputStream(target).use { input.copyTo(it) }
                        }
                        if (Files.size(target) != member.size) {
                            throw IllegalArgumentException("ZIP member byte count differs")
                        }
                    }
                }
            }
        } else {
            Files.newInputStream(packed).use { stream ->
                TarArchiveInputStream(stream).use { archive ->
                    while (true) {
                        val member: TarArchiveEntry = archive.nextEntry ?: break
                        val name = member.name.trimEnd('/')
                        CollectionRules.filePathName(name)
                        if (!seen.add(name)) {
                            throw IllegalArgumentException("duplicate archive member")
                        }
                        if (seen.size > io.maxMembers || !(member.isFile || member.isDirectory)) {
                            throw IllegalArgumentException("nonregular or excessive TAR member")
                        }
                        total += member.size
                        if (total > io.maxExpandedBytes) {
                            throw IllegalArgumentException("TAR expanded bytes exceed bound")
                        }
                        val target = destination.resolve(name)
                        if (member.isDirectory) {
                            Files.createDirectories(target)
                        } else {
                            target.parent?.let { Files.createDirectories(it) }
                            Files.newOutputStream(target).use { output ->
                                archive.copyTo(output, 1024 * 1024)
                            }
                            if (Files.size(target) != member.size) {
                                throw IllegalArgumentException("TAR member byte count differs")
                            }
                        }
                    }
                }
            }
        }
        return io.inventory(destination)
    }

    /** `_copy_regular`: freeze one regular source file with a byte bound. */
    fun copyRegular(
        source: Path,
        destination: Path,
        limit: Long = MAX_SOURCE_BYTES,
        preflight: Boolean = true,
        expected: Pair<Any?, Any?>? = null,
        io: CollectionIo = CollectionIo.default,
    ): Long = io.copyRegular(source, destination, limit, preflight)

    /** The real bounded copy of one anchored regular file. */
    internal fun copyFile(
        source: Path,
        destination: Path,
        limit: Long = MAX_SOURCE_BYTES,
        preflight: Boolean = true,
        expected: Pair<Any?, Any?>? = null,
    ): Long {
        val before = readProtected(source, expected)
        val info = attributes(source)
        if (!info.isRegularFile) {
            throw IllegalArgumentException("source file is not regular")
        }
        if (preflight && info.size() > limit) {
            throw IllegalArgumentException("source file exceeds byte bound")
        }
        var total = 0L
        Files.newOutputStream(destination).use { frozen ->
            Files.newInputStream(source, LinkOption.NOFOLLOW_LINKS).use { stream ->
                val buffer = ByteArray(1024 * 1024)
                while (true) {
                    val want = minOf(1024 * 1024L, limit - total + 1).toInt()
                    if (want <= 0) break
                    val read = stream.read(buffer, 0, want)
                    if (read <= 0) break
                    val remaining = limit - total
                    if (read > remaining) {
                        frozen.write(buffer, 0, remaining.toInt())
                        throw IllegalArgumentException("source file exceeds byte bound while copied")
                    }
                    frozen.write(buffer, 0, read)
                    total += read
                }
            }
        }
        if (total != info.size()) {
            throw IllegalArgumentException("source file changed size while copied")
        }
        afterRead(source, before)
        return total
    }

    /** `_copy_directory`: freeze one source directory, byte for byte. */
    fun copyDirectory(
        source: Path,
        destination: Path,
        io: CollectionIo = CollectionIo.default,
    ) {
        val info = attributes(source)
        if (info.isSymbolicLink || !info.isDirectory) {
            throw IllegalArgumentException("source directory is missing or symbolic")
        }
        if (Files.exists(destination)) throw FileAlreadyExistsException(destination.toString())
        Files.createDirectories(destination)
        var count = 0
        var total = 0L

        fun visit(anchor: Path, frozen: Path, prefix: String) {
            val names = io.directoryNames(anchor)
            val seen = mutableSetOf<String>()
            for (name in names) {
                val relative = if (prefix.isEmpty()) name else "$prefix/$name"
                CollectionRules.filePathName(relative)
                if (!seen.add(name)) {
                    throw IllegalArgumentException("duplicate source directory member")
                }
                count++
                if (count > io.maxMembers) {
                    throw IllegalArgumentException("source directory exceeds transport bounds")
                }
                val child = anchor.resolve(name)
                val childInfo = attributes(child)
                if (childInfo.isSymbolicLink) {
                    throw IllegalArgumentException("symbolic source member")
                }
                val target = frozen.resolve(name)
                if (childInfo.isDirectory) {
                    Files.createDirectory(target)
                    visit(child, target, relative)
                } else if (!childInfo.isRegularFile) {
                    throw IllegalArgumentException("nonregular source member")
                } else {
                    try {
                        total += io.copyRegular(
                            child,
                            target,
                            io.maxExpandedBytes - total,
                            false,
                        )
                    } catch (error: IllegalArgumentException) {
                        if ("exceeds byte bound" in (error.message ?: "")) {
                            throw IllegalArgumentException(
                                "source directory exceeds transport bounds while copied",
                            )
                        }
                        throw error
                    }
                }
            }
        }

        visit(source, destination, "")
    }

    /** `_read_anchored`: one bounded read that must not change under the caller. */
    fun anchoredRead(path: Path): ByteArray {
        val before = readProtected(path, null)
        val data = Files.newInputStream(path, LinkOption.NOFOLLOW_LINKS).use { stream ->
            val buffer = ByteArray(1024 * 1024)
            val out = java.io.ByteArrayOutputStream()
            var total = 0L
            while (true) {
                val read = stream.read(buffer)
                if (read <= 0) break
                total += read
                if (total > MAX_SOURCE_BYTES) {
                    throw IllegalArgumentException("source file exceeds byte bound")
                }
                out.write(buffer, 0, read)
            }
            out.toByteArray()
        }
        afterRead(path, before)
        return data
    }

    /** `_strict_json`: one strict JSON object read through the anchored path. */
    fun strictJson(path: Path): JsonObject = strictJsonBytes(anchoredRead(path))

    /** `_strict_json_bytes`: strict JSON with duplicate keys and non-finite constants rejected. */
    fun strictJsonBytes(data: ByteArray): JsonObject {
        val text = data.toString(StandardCharsets.UTF_8)
        rejectDuplicateKeys(text)
        val value = try {
            StrictJson.load(text)
        } catch (error: IllegalArgumentException) {
            throw IllegalArgumentException("invalid JSON: ${error.message}")
        }
        if (value !is JsonObject) {
            throw IllegalArgumentException("source index object keys are invalid")
        }
        return value
    }

    /** `independent_gates._strict_object`: one object may not declare a key twice. */
    private fun rejectDuplicateKeys(text: String) {
        var index = 0
        val stack = ArrayDeque<MutableSet<String>>()
        var expectKey = false
        while (index < text.length) {
            when (val char = text[index]) {
                '"' -> {
                    var end = index + 1
                    val value = StringBuilder()
                    while (end < text.length) {
                        val current = text[end]
                        if (current == '\\') {
                            end += 2
                            continue
                        }
                        if (current == '"') break
                        value.append(current)
                        end++
                    }
                    if (expectKey && stack.isNotEmpty()) {
                        if (!stack.last().add(value.toString())) {
                            throw IllegalArgumentException("duplicate JSON key: $value")
                        }
                    }
                    expectKey = false
                    index = end + 1
                }
                '{' -> {
                    stack.addLast(mutableSetOf())
                    expectKey = true
                    index++
                }
                '}' -> {
                    if (stack.isNotEmpty()) stack.removeLast()
                    expectKey = false
                    index++
                }
                '[' -> {
                    stack.addLast(mutableSetOf())
                    expectKey = false
                    index++
                }
                ']' -> {
                    if (stack.isNotEmpty()) stack.removeLast()
                    expectKey = false
                    index++
                }
                ',' -> {
                    expectKey = stack.isNotEmpty()
                    index++
                }
                ':' -> {
                    expectKey = false
                    index++
                }
                else -> index++
            }
        }
    }

    /** `_safe_source_path`: an absolute path that is not, and is not under, a symbolic link. */
    fun safeSourcePath(path: Path): Path {
        if (!path.isAbsolute) {
            throw IllegalArgumentException("local source path must be absolute")
        }
        var current: Path? = path
        val checked = mutableListOf<Path>()
        while (current != null) {
            checked.add(current)
            current = current.parent
        }
        for (part in checked) {
            if (!Files.exists(part, LinkOption.NOFOLLOW_LINKS)) continue
            if (Files.isSymbolicLink(part)) {
                throw IllegalArgumentException("symbolic source path is forbidden")
            }
        }
        return path
    }

    fun safeSourcePathText(text: String): Path = safeSourcePath(Path.of(text))

    /** `_path_identity`: the `(st_dev, st_ino)` pair of one non-symbolic path. */
    fun pathIdentity(path: Path): Pair<Any?, Any?> {
        safeSourcePath(path.toAbsolutePath())
        val attributes = attributes(path)
        if (attributes.isSymbolicLink) {
            throw IllegalArgumentException("symbolic source path is forbidden")
        }
        return attributes.fileKey() to filesDeviceInode(path)
    }

    /** `_github_request`: one GitHub API call, with no redirects on the API endpoint. */
    fun githubRequest(
        url: String,
        token: String,
        destination: Path? = null,
        limit: Long? = null,
        client: HttpClient = defaultClient(),
        opener: (HttpRequest) -> HttpResponse<ByteArray> = { request ->
            client.send(request, HttpResponse.BodyHandlers.ofByteArray())
        },
    ): Pair<JsonElement?, Long> {
        val request = HttpRequest.newBuilder(URI.create(url))
            .timeout(Duration.ofSeconds(60))
            .header("Accept", "application/vnd.github+json")
            .header("Authorization", "Bearer $token")
            .header("X-GitHub-Api-Version", "2022-11-28")
            .GET()
            .build()
        val response = opener(request)
        if (response.statusCode() in 300..399) {
            if (destination == null) {
                throw IllegalArgumentException(
                    "GitHub artifact API returned HTTP ${response.statusCode()}",
                )
            }
            val location = response.headers().firstValue("Location").orElse("")
            val parsed = runCatching { URI.create(location) }.getOrNull()
            if (parsed == null || parsed.scheme != "https" || parsed.host.isNullOrEmpty()) {
                throw IllegalArgumentException("GitHub artifact redirect is not HTTPS")
            }
            val redirected = opener(
                HttpRequest.newBuilder(parsed).timeout(Duration.ofSeconds(60)).GET().build(),
            )
            if (redirected.statusCode() !in 200..299) {
                throw IllegalArgumentException(
                    "GitHub artifact API returned HTTP ${redirected.statusCode()}",
                )
            }
            var size = 0L
            Files.newOutputStream(destination).use { output ->
                val body = redirected.body()
                for (offset in body.indices step (1024 * 1024)) {
                    val end = minOf(offset + 1024 * 1024, body.size)
                    size += end - offset
                    if (limit != null && size > limit) {
                        throw IllegalArgumentException(
                            "GitHub artifact download exceeds pinned byte limit",
                        )
                    }
                    output.write(body, offset, end - offset)
                }
            }
            return null to size
        }
        if (response.statusCode() !in 200..299) {
            throw IllegalArgumentException("GitHub artifact API returned HTTP ${response.statusCode()}")
        }
        val body = response.body()
        if (destination == null) {
            return StrictJson.load(body.toString(StandardCharsets.UTF_8)) to 0L
        }
        var size = 0L
        Files.newOutputStream(destination).use { output ->
            for (offset in body.indices step (1024 * 1024)) {
                val end = minOf(offset + 1024 * 1024, body.size)
                size += end - offset
                if (limit != null && size > limit) {
                    throw IllegalArgumentException("GitHub artifact download exceeds pinned byte limit")
                }
                output.write(body, offset, end - offset)
            }
        }
        return null to size
    }

    /** `_github_artifact`: download one pinned GitHub Actions artifact ZIP. */
    fun githubArtifact(
        origin: JsonObject,
        candidateSha: String,
        token: String,
        destination: Path,
        expectedSize: Long,
        opener: ((HttpRequest) -> HttpResponse<ByteArray>)? = null,
    ): JsonObject {
        if (token.isEmpty()) throw IllegalArgumentException("GitHub Actions token is unavailable")
        val repository = Py.str(origin["repository"])!!
        val base = "https://api.github.com/repos/$repository/actions"
        val send = opener ?: { request -> defaultClient().send(request, HttpResponse.BodyHandlers.ofByteArray()) }
        val runId = Py.int(origin["run_id"]!!)
        val artifactId = Py.int(origin["artifact_id"]!!)
        val run = githubRequest("$base/runs/$runId", token, opener = send).first as? JsonObject
            ?: throw IllegalArgumentException("GitHub run observation is not an object")
        val artifact = githubRequest("$base/artifacts/$artifactId", token, opener = send).first
            as? JsonObject
            ?: throw IllegalArgumentException("GitHub artifact observation is not an object")
        val workflowRun = artifact["workflow_run"] as? JsonObject ?: JsonObject(emptyMap())
        val runRepository = run["repository"] as? JsonObject ?: JsonObject(emptyMap())
        if (!Py.equalsInt(run["id"], runId) ||
            Py.str(run["head_sha"]) != candidateSha ||
            !Py.equalsInt(run["run_attempt"], Py.int(origin["run_attempt"]!!)) ||
            (Py.str(run["path"]) ?: "").substringBefore('@') != Py.str(origin["workflow"]) ||
            Py.str(runRepository["full_name"]) != repository ||
            !Py.equalsInt(artifact["id"], artifactId) ||
            Py.str(artifact["name"]) != Py.str(origin["name"]) ||
            Py.truthy(artifact["expired"]) ||
            !Py.equalsInt(workflowRun["id"], runId) ||
            Py.str(workflowRun["head_sha"]) != candidateSha ||
            workflowRun["repository_id"] != runRepository["id"]
        ) {
            throw IllegalArgumentException("GitHub run or artifact source identity differs")
        }
        if (!Py.equalsInt(origin["run_attempt"], 1L)) {
            throw IllegalArgumentException("artifact API does not prove rerun attempt ownership")
        }
        if (!Py.equalsInt(artifact["size_in_bytes"], Py.int(origin["api_size_in_bytes"]!!)) ||
            Py.int(artifact["size_in_bytes"]!!) > MAX_SOURCE_BYTES
        ) {
            throw IllegalArgumentException("GitHub artifact API byte size differs")
        }
        githubRequest(
            "$base/artifacts/$artifactId/zip",
            token,
            destination,
            expectedSize,
            opener = send,
        )
        return buildJsonObject {
            put("run_id", JsonPrimitive(runId))
            put("run_attempt", run["run_attempt"] ?: JsonNull)
            put("artifact_id", JsonPrimitive(artifactId))
            put("name", artifact["name"] ?: JsonNull)
            put("head_sha", run["head_sha"] ?: JsonNull)
            put("workflow", origin["workflow"] ?: JsonNull)
            put("api_size_in_bytes", artifact["size_in_bytes"] ?: JsonNull)
        }
    }

    // ------------------------------------------------------------------------------------
    // Shared helpers
    // ------------------------------------------------------------------------------------

    private class Protected(
        val attributes: BasicFileAttributes,
        val deviceInode: Pair<Any?, Any?>,
        val modifiedNs: Long,
    )

    /** `_anchored_open`'s pre-checks: non-symbolic, regular, and matching the expected identity. */
    private fun readProtected(path: Path, expected: Pair<Any?, Any?>?): Protected {
        safeSourcePath(path)
        val attributes = attributes(path)
        if (attributes.isSymbolicLink || !attributes.isRegularFile) {
            throw IllegalArgumentException("source path is symbolic or has wrong file type")
        }
        val identity = attributes.fileKey() to filesDeviceInode(path)
        if (expected != null && expected.first != identity) {
            throw IllegalArgumentException("source path changed before it was opened")
        }
        return Protected(attributes, identity, attributes.lastModifiedTime().to(TimeUnit.NANOSECONDS))
    }

    /** `_anchored_open`'s closing checks: the path and its bytes did not change. */
    private fun afterRead(path: Path, before: Protected) {
        safeSourcePath(path)
        val after = attributes(path)
        if (after.isSymbolicLink ||
            (after.fileKey() to filesDeviceInode(path)) != before.deviceInode ||
            after.size() != before.attributes.size()
        ) {
            throw IllegalArgumentException("source path changed while read")
        }
    }

    private fun attributes(path: Path): BasicFileAttributes = try {
        Files.readAttributes(path, BasicFileAttributes::class.java, LinkOption.NOFOLLOW_LINKS)
    } catch (error: NoSuchFileException) {
        throw IllegalArgumentException("[Errno 2] No such file or directory: '$path'")
    } catch (error: IOException) {
        throw IllegalArgumentException(error.message ?: "source path is unavailable")
    }

    private fun filesDeviceInode(path: Path): Pair<Any?, Any?> {
        val device = try {
            Files.getAttribute(path, "unix:dev", LinkOption.NOFOLLOW_LINKS)
        } catch (error: Exception) {
            null
        }
        val inode = try {
            Files.getAttribute(path, "unix:ino", LinkOption.NOFOLLOW_LINKS)
        } catch (error: Exception) {
            null
        }
        return device to inode
    }

    private fun children(folder: Path): Set<String> = Files.newDirectoryStream(folder).use { stream ->
        stream.map { it.fileName.toString() }.toSet()
    }

    private fun isWithin(path: Path, root: Path): Boolean =
        path.toAbsolutePath().normalize().startsWith(root.toAbsolutePath().normalize())

    private fun repoFile(repository: Path, relative: String): String =
        repository.resolve(relative).toString()

    private fun deleteRecursively(root: Path) {
        if (!Files.exists(root)) return
        Files.walk(root).use { stream ->
            stream.sorted(Comparator.reverseOrder()).forEach { Files.deleteIfExists(it) }
        }
    }

    private fun defaultClient(): HttpClient = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NEVER)
        .connectTimeout(Duration.ofSeconds(60))
        .build()

    /** The reference's caught failure set: `OSError, ValueError, TypeError, KeyError, ...`. */
    private fun isCaught(error: Exception): Boolean = when (error) {
        is IllegalArgumentException, is IOException, is java.io.UncheckedIOException,
        is NoSuchElementException, is ClassCastException, is InterruptedException -> true
        else -> false
    }
}
