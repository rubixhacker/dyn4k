package io.github.rubixhacker.harness.qualification

import io.github.rubixhacker.harness.contract.Qualification
import io.github.rubixhacker.harness.contract.StrictJson
import java.io.IOException
import java.nio.charset.StandardCharsets
import java.nio.file.DirectoryStream
import java.nio.file.Files
import java.nio.file.LinkOption
import java.nio.file.NoSuchFileException
import java.nio.file.Path
import java.nio.file.StandardCopyOption
import java.nio.file.StandardOpenOption
import java.nio.file.attribute.BasicFileAttributes
import java.nio.file.attribute.FileTime
import java.nio.file.attribute.PosixFilePermission
import java.security.MessageDigest
import java.util.UUID
import java.util.concurrent.TimeUnit
import javax.xml.parsers.DocumentBuilderFactory
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import org.w3c.dom.Element

/** A test report that is not well-formed XML. Stands in for `xml.etree.ElementTree.ParseError`. */
class HostedXmlError(message: String, cause: Throwable? = null) : IllegalArgumentException(message, cause)

/**
 * The file-system half of `full_hosted.py`: the report readers, the process receipt, the Safari
 * diagnostic suite, the staging and content audits, the receipt verifier, and the generated
 * product inventories.
 *
 * The reference opens directories with `dir_fd`-relative `os.open`. A JVM path has no descriptor,
 * so every component is checked with `NOFOLLOW_LINKS` before it is used; a swap between a check and
 * the operation it protects is not detectable here. See the port report for each such check.
 */
object FullHostedRuntime {
    private const val MAX_FAILED_SOURCE_XML_FILES = 512
    private const val MAX_FAILED_SOURCE_XML_ENTRIES = 1024
    private const val MAX_FAILED_SOURCE_XML_BYTES = 32 * 1024 * 1024
    private const val MAX_FAILED_SOURCE_XML_TOTAL = 64 * 1024 * 1024
    private const val HASH_BUDGET = 256L * 1024 * 1024
    private const val INVENTORY_LIMIT = 128
    private const val DIAGNOSTIC_MAX_MESSAGE_BYTES = 72 * 262144
    private const val DIAGNOSTIC_MAX_ROW_BYTES = 262144

    /** `time.time_ns()`: the wall clock in nanoseconds, as the reference records it. */
    internal fun nowNs(): Long {
        val instant = java.time.Instant.now()
        return instant.epochSecond * 1_000_000_000L + instant.nano
    }

    /** `candidate_checkout`: the checkout this process runs in. */
    fun candidateCheckout(): Path = Path.of("").toAbsolutePath().normalize()

    /** `load_corpus`: the committed manifest, its reviewed map, and the source-derived corpus. */
    fun loadCorpus(repository: Path, candidateSha: String): JsonObject {
        CleanRequire.require(repository, candidateSha)
        val manifest = StrictJson.load(
            FullHosted.committedInput(repository, candidateSha, FullHosted.MANIFEST)
                .toString(StandardCharsets.UTF_8),
        ) as? JsonObject ?: throw IllegalArgumentException("reviewed corpus manifest is not an object")
        val mapping = CorpusTsv.read(FullHosted.committedInput(repository, candidateSha, FullHosted.MAPPING))
        FullHosted.committedInput(repository, candidateSha, FullHosted.PAIRS)
        val problems = CorpusVerification.candidateInputProblems(
            repository,
            candidateSha,
            manifest,
            mapping,
            repository.resolve(FullHosted.MANIFEST),
            repository.resolve(FullHosted.MAPPING),
            checkCheckout = false,
        )
        if (problems.isNotEmpty()) {
            throw IllegalArgumentException("reviewed corpus input differs: " + problems.joinToString("; "))
        }
        val derived = FullCorpus.makeManifest(
            CorpusFiles.scanSources(repository),
            mapping,
            production = true,
            sourceFiles = CorpusFiles.scanTestTree(repository),
        )
        if (derived != manifest) {
            throw IllegalArgumentException("source-derived corpus differs from candidate")
        }
        val counts = manifest["counts"] as? JsonObject
        if (Py.truthy(manifest["unresolved"]) ||
            Py.truthy(counts?.get("unresolved_mappings"))
        ) {
            throw IllegalArgumentException("reviewed corpus has unresolved mappings")
        }
        return manifest
    }

    /** `read_reports`: one module's XML reports, verified against the reviewed case inventory. */
    fun readReports(
        paths: List<Path>,
        expected: Set<Pair<String, String>>,
        target: String,
        startedNs: Long,
        finishedNs: Long,
        safariVersion: String? = null,
    ): HostedReportCheck {
        if (paths.isEmpty()) throw IllegalArgumentException("required XML reports are missing")
        val seen = LinkedHashMap<Pair<String, String>, Int>()
        val reports = mutableListOf<JsonObject>()
        var diagnosticSuites = 0
        for (path in paths) {
            val modified = mtimeNs(path)
            if (modified < startedNs || modified > finishedNs) {
                throw IllegalArgumentException("stale or post-invocation XML: $path")
            }
            val raw = Files.readAllBytes(path)
            val suite = parseXml(raw, path.toString())
            if (suite.tagName != "testsuite") {
                throw IllegalArgumentException("invalid XML suite: $path")
            }
            val duration = FullHostedRules.pythonFloat(suite.getAttribute("time").ifEmpty { "nan" })
            if (duration == null || !duration.isFinite()) {
                throw IllegalArgumentException("invalid XML suite duration: $path")
            }
            val cases = successors(suite, "testcase")
            if (target == "jsSafari" &&
                Pair(FullHosted.SAFARI_DIAGNOSTIC_CLASS, "capsuleSlice") in expected
            ) {
                if (cases.any {
                        it.getAttribute("classname") ==
                            "jsBrowserTest.${FullHosted.SAFARI_DIAGNOSTIC_CLASS}"
                    }
                ) {
                    diagnosticSuites++
                    checkSafariDiagnosticSuite(suite)
                } else if (successors(suite, "system-out").any {
                        (it.textContent ?: "").contains("DYN4K_COLLISION_DIAGNOSTIC")
                    }
                ) {
                    throw IllegalArgumentException(
                        "Safari diagnostic output is outside its case suite",
                    )
                }
            }
            val actual = linkedMapOf(
                "tests" to cases.size.toLong(),
                "failures" to cases.count { firstChild(it, "failure") != null }.toLong(),
                "errors" to cases.count { firstChild(it, "error") != null }.toLong(),
                "skipped" to cases.count { firstChild(it, "skipped") != null }.toLong(),
            )
            for ((key, count) in actual) {
                val attribute = suite.getAttribute(key)
                if (attribute.isEmpty() || attribute.toLongOrNull() != count) {
                    throw IllegalArgumentException("XML $key count differs: $path")
                }
            }
            if (actual["failures"] != 0L || actual["errors"] != 0L || actual["skipped"] != 0L) {
                throw IllegalArgumentException("failed, errored, or skipped XML case: $path")
            }
            for (case in cases) {
                val classname = case.getAttribute("classname")
                val name = case.getAttribute("name")
                if (classname.isEmpty() || name.isEmpty()) {
                    throw IllegalArgumentException("case identity is absent: $path")
                }
                val caseDuration = FullHostedRules.pythonFloat(
                    case.getAttribute("time").ifEmpty { "nan" },
                )
                if (caseDuration == null || !caseDuration.isFinite() ||
                    firstChild(case, "ignored") != null
                ) {
                    throw IllegalArgumentException("ignored or invalid case duration: $path")
                }
                val identity: Pair<String, String>
                if (target == "jsSafari") {
                    if (!classname.startsWith("jsBrowserTest.")) {
                        throw IllegalArgumentException("wrong Safari test target")
                    }
                    val match = Regex("(.+)\\[js, browser, Safari[^]]+\\]").matchEntire(name)
                        ?: throw IllegalArgumentException("Safari browser identity is absent")
                    if (!safariVersion.isNullOrEmpty() && "Safari$safariVersion," !in name) {
                        throw IllegalArgumentException("Safari browser version differs from runtime")
                    }
                    identity = classname.removePrefix("jsBrowserTest.") to match.groupValues[1]
                } else {
                    val prefix = "${target}Test."
                    val suffix = "[$target]"
                    if (!classname.startsWith(prefix) || !name.endsWith(suffix)) {
                        throw IllegalArgumentException("wrong native test target")
                    }
                    identity = classname.removePrefix(prefix) to name.removeSuffix(suffix)
                }
                seen[identity] = (seen[identity] ?: 0) + 1
            }
            reports.add(
                buildJsonObject {
                    put("path", JsonPrimitive(path.toString()))
                    put("sha256", JsonPrimitive(FullHosted.sha256(path)))
                    put("modified_ns", JsonPrimitive(modified))
                    put("cases", JsonPrimitive(cases.size))
                },
            )
        }
        if (seen.keys != expected || seen.values.any { it != 1 }) {
            val missing = (expected - seen.keys).sortedWith(identityOrder).take(3)
            val extra = (seen.keys - expected).sortedWith(identityOrder).take(3)
            throw IllegalArgumentException(
                "missing, extra, or duplicate cases: missing=${tupleRepr(missing)}; " +
                    "extra=${tupleRepr(extra)}",
            )
        }
        if (target == "jsSafari" &&
            Pair(FullHosted.SAFARI_DIAGNOSTIC_CLASS, "capsuleSlice") in expected &&
            diagnosticSuites != 1
        ) {
            throw IllegalArgumentException("Safari diagnostic case suite is absent or duplicated")
        }
        return HostedReportCheck(
            expected = expected.size,
            executed = seen.values.sum(),
            caseIds = seen.keys.sortedWith(identityOrder).map { "${it.first}#${it.second}" },
            reports = reports,
        )
    }

    /**
     * `check_safari_diagnostic_suite`: the twelve reviewed steps of one fixture, with every field
     * of every row validated and the whole 72 row inventory bound to the reviewed identities.
     */
    fun checkSafariDiagnosticSuite(suite: Element) {
        val expectedMethods = FullHosted.SAFARI_DIAGNOSTIC_CASES.keys
        val cases = successors(suite, "testcase")
        val diagnosticCases = cases.filter {
            it.getAttribute("classname") == "jsBrowserTest.${FullHosted.SAFARI_DIAGNOSTIC_CLASS}"
        }
        val observedMethods = diagnosticCases.map { it.getAttribute("name").substringBefore("[") }.toSet()
        if (observedMethods != expectedMethods || diagnosticCases.size != expectedMethods.size) {
            throw IllegalArgumentException("Safari diagnostic case identities differ")
        }
        val outputNodes = descendants(suite, "system-out")
        if (outputNodes.size != 1 || outputNodes[0] !== firstChild(suite, "system-out")) {
            throw IllegalArgumentException("Safari diagnostic output is outside its case suite")
        }
        val output = outputNodes[0].textContent ?: ""
        if (output.isEmpty() ||
            output.toByteArray(StandardCharsets.UTF_8).size > DIAGNOSTIC_MAX_MESSAGE_BYTES
        ) {
            throw IllegalArgumentException(
                "Safari diagnostic output is absent or exceeds the message bound",
            )
        }
        val rows = FullHostedRules.splitLinesKeepingEnds(output)
        if (rows.size != 72) {
            throw IllegalArgumentException("Safari diagnostic row count differs: ${rows.size}")
        }
        val expectedRows = FullHosted.safariDiagnosticIdentities()
        val observed = mutableSetOf<List<Any>>()
        for (row in rows) {
            if (!row.startsWith("[log] DYN4K_COLLISION_DIAGNOSTIC\tv2\t") ||
                !row.endsWith("\n") ||
                row.toByteArray(StandardCharsets.UTF_8).size > DIAGNOSTIC_MAX_ROW_BYTES
            ) {
                throw IllegalArgumentException(
                    "Safari diagnostic row is missing, truncated, or malformed",
                )
            }
            val fields = row.removePrefix("[log] ").removeSuffix("\n").split("\t")
            if (fields.take(2) != listOf("DYN4K_COLLISION_DIAGNOSTIC", "v2")) {
                throw IllegalArgumentException("Safari diagnostic version differs")
            }
            val pairs = fields.drop(2).map { it.split('=', limit = 2) }
            if (pairs.any { it.size != 2 }) {
                throw IllegalArgumentException("Safari diagnostic field is incomplete")
            }
            val values = LinkedHashMap<String, String>()
            for (pair in pairs) values[pair[0]] = pair[1]
            val step: Int
            val count: String
            val points: Int
            try {
                step = values.getValue("step").toIntOrNull()
                    ?: throw NumberFormatException()
                count = values.getValue("manifold.count")
                points = if (count == "na") 0 else count.toIntOrNull() ?: throw NumberFormatException()
            } catch (error: Exception) {
                throw IllegalArgumentException(
                    "Safari diagnostic step or manifold count is invalid",
                    error,
                )
            }
            if (points < 0 || points > 2 || step.toString() != values["step"] ||
                (count != "na" && points.toString() != count)
            ) {
                throw IllegalArgumentException("Safari diagnostic step or manifold count is invalid")
            }
            val satKeys = if (values["sat.replay.hit"] == "false") {
                FullHostedRules.SAFARI_DIAGNOSTIC_SAT_KEYS.take(5)
            } else {
                FullHostedRules.SAFARI_DIAGNOSTIC_SAT_KEYS
            }
            val keys = FullHostedRules.SAFARI_DIAGNOSTIC_PREFIX_KEYS +
                FullHostedRules.SAFARI_DIAGNOSTIC_TRACE_KEYS +
                (if (values["algorithm"] == "sat") satKeys else emptyList()) +
                FullHostedRules.SAFARI_DIAGNOSTIC_EPA_KEYS +
                (0 until points).flatMap { index ->
                    listOf("position", "depth", "id").map { "manifold.point.$index.$it" }
                }
            val emptyAllowed = setOf(
                "a.foci.world", "b.foci.world", "a.axes.withB", "b.axes.withA",
                "epa.replay.simplex", "epa.iteration.records",
            )
            if (pairs.map { it[0] } != keys ||
                pairs.any { (key, value) -> value.isEmpty() && key !in emptyAllowed } ||
                values["provider"] != "dyn4k" ||
                values["hit"] !in setOf("true", "false") ||
                values["epa.replay.depthMatchesResult"] !in setOf("true", "false", "na")
            ) {
                throw IllegalArgumentException("Safari diagnostic row fields are incomplete or changed")
            }
            for (index in 0 until points) {
                if (!Regex("(?:distance|indexed:\\d+:\\d+:\\d+:(?:true|false))")
                        .matches(values.getValue("manifold.point.$index.id"))
                ) {
                    throw IllegalArgumentException(
                        "Safari diagnostic manifold point identity is truncated",
                    )
                }
            }
            val identity = listOf<Any>(
                values.getValue("fixture"),
                values.getValue("method"),
                values.getValue("phase"),
                values.getValue("order"),
                step,
                values.getValue("algorithm"),
            )
            if (identity !in expectedRows || identity in observed) {
                throw IllegalArgumentException(
                    "Safari diagnostic row identity is missing, extra, or duplicate",
                )
            }
            val phaseFieldsDiffer = if (step < 4) {
                values["booleanHit"] !in setOf("true", "false") ||
                    values["clipped"] != "na" || count != "na"
            } else {
                values["booleanHit"] != "na" ||
                    values["clipped"] !in setOf("true", "false") || count == "na"
            }
            if (phaseFieldsDiffer) {
                throw IllegalArgumentException("Safari diagnostic phase fields differ")
            }
            FullHostedRules.safariV2CheckValues(values, step, points)
            observed.add(identity)
        }
        if (observed != expectedRows) {
            throw IllegalArgumentException("Safari diagnostic rows are incomplete")
        }
    }

    /** `run_command`: run one command in a directory and record its receipt. */
    fun runCommand(
        command: List<String>,
        cwd: Path,
        destination: Path,
        invocationId: String? = null,
    ): JsonObject {
        val started = nowNs()
        val builder = ProcessBuilder(command).directory(cwd.toFile())
        if (!invocationId.isNullOrEmpty()) {
            builder.environment()["DYN4K_QUALIFICATION_INVOCATION"] = invocationId
        }
        val process = builder.start()
        process.outputStream.close()
        val stdout = process.inputStream.use { it.readBytes() }
        val stderr = process.errorStream.use { it.readBytes() }
        val exitCode = process.waitFor()
        Files.createDirectories(destination)
        Files.write(destination.resolve("stdout.txt"), stdout)
        Files.write(destination.resolve("stderr.txt"), stderr)
        val finished = nowNs()
        return buildJsonObject {
            put("command", JsonArray(command.map { JsonPrimitive(it) }))
            put("pid", JsonPrimitive(process.pid()))
            put("exit_code", JsonPrimitive(exitCode))
            put("invocation_id", invocationId?.let { JsonPrimitive(it) } ?: JsonNull)
            put("started_ns", JsonPrimitive(started))
            put("finished_ns", JsonPrimitive(finished))
            put("stdout_sha256", JsonPrimitive(FullHosted.sha256(destination.resolve("stdout.txt"))))
            put("stderr_sha256", JsonPrimitive(FullHosted.sha256(destination.resolve("stderr.txt"))))
        }
    }

    /** `verify_process`: the archived process receipt and both of its logs. */
    fun verifyProcess(
        output: Path,
        folder: Path,
        process: JsonObject?,
        invocation: String?,
        requiredTask: String? = null,
    ) {
        if (process == null ||
            Py.str(process["invocation_id"]) != invocation ||
            !Py.equalsInt(process["exit_code"], 0L) ||
            !Py.isInt(process["pid"]) || Py.int(process["pid"]) <= 0 ||
            !Py.isInt(process["started_ns"]) || !Py.isInt(process["finished_ns"]) ||
            Py.int(process["started_ns"]) <= 0 ||
            Py.int(process["finished_ns"]) < Py.int(process["started_ns"])
        ) {
            throw IllegalArgumentException(
                "archived process exit, identity, or timestamps differ",
            )
        }
        val command = (process["command"] as? JsonArray)?.mapNotNull { Py.str(it) }
        if (command == null || (requiredTask != null && requiredTask !in command)) {
            throw IllegalArgumentException("archived process command lacks required task")
        }
        val started = Py.int(process["started_ns"])
        val finished = Py.int(process["finished_ns"])
        for (stream in listOf("stdout", "stderr")) {
            val name = relativeToPosix(folder.resolve("$stream.txt"), output)
            val log = FullHosted.archivedFile(output, name)
            if (FullHosted.sha256(log) != Py.str(process["${stream}_sha256"])) {
                throw IllegalArgumentException("archived process log differs from receipt")
            }
            val modified = mtimeNs(log)
            if (modified < started || modified > finished) {
                throw IllegalArgumentException(
                    "archived process log timestamp differs from invocation",
                )
            }
        }
        if ("BUILD SUCCESSFUL" !in String(
                Files.readAllBytes(folder.resolve("stdout.txt")),
                StandardCharsets.UTF_8,
            )
        ) {
            throw IllegalArgumentException("archived process did not complete successfully")
        }
    }

    /**
     * `verify_staging`: the staged GAV inventory, the POM and metadata contracts, and the staged
     * binary hashes of one target publication.
     */
    fun verifyStaging(output: Path, receipt: JsonObject) {
        val target = Py.str(receipt["target"]) ?: ""
        val artifactTarget = if (target == "jsSafari") "js" else target
        val expectedNames = mutableSetOf<String>()
        expectedNames.addAll(Qualification.modules)
        for (module in Qualification.modules) {
            expectedNames.add(Qualification.targetPublicationName(module, artifactTarget))
        }
        val stagedGav = (receipt["staged_gav"] as? JsonArray)?.mapNotNull { Py.str(it) } ?: emptyList()
        val expectedGav = expectedNames.map { "${Qualification.GROUP}:$it:${Qualification.VERSION}" }
        if (stagedGav.toSet() != expectedGav.toSet()) {
            throw IllegalArgumentException("staged GAV inventory differs")
        }
        val expectedPaths = mutableSetOf<String>()
        val namespace = "http://maven.apache.org/POM/4.0.0"
        for (name in expectedNames) {
            val base = Path.of("staged")
                .resolve(Qualification.GROUP.replace(".", "/"))
                .resolve(name)
                .resolve(Qualification.VERSION)
            val suffixes = mutableListOf(
                ".pom", ".module", "-sources.jar", "-javadoc.jar", "-license.md",
            )
            if (name in Qualification.modules) suffixes.add(".jar")
            if (Qualification.isAppleTarget(artifactTarget) && name !in Qualification.modules) {
                suffixes.add("-metadata.jar")
            }
            for (suffix in suffixes) {
                val relative = (base.resolve("$name-${Qualification.VERSION}$suffix"))
                    .toString().replace('\\', '/')
                expectedPaths.add(relative)
                expectedPaths.add("$relative.sha256")
            }
            for (suffix in listOf(".pom", ".module")) {
                val relative = (base.resolve("$name-${Qualification.VERSION}$suffix"))
                    .toString().replace('\\', '/')
                val path = FullHosted.archivedFile(output, relative)
                if (suffix == ".pom") {
                    val root = parseXml(Files.readAllBytes(path), relative, namespaceAware = true)
                    for ((key, value) in listOf(
                        "groupId" to Qualification.GROUP,
                        "artifactId" to name,
                        "version" to Qualification.VERSION,
                    )) {
                        if (findText(root, namespace, key) != value) {
                            throw IllegalArgumentException("staged POM identity differs")
                        }
                    }
                    val dependencies = mutableSetOf<List<String?>>()
                    for (dependency in findPath(root, namespace, listOf("dependencies", "dependency"))) {
                        dependencies.add(
                            listOf(
                                findText(dependency, namespace, "groupId"),
                                findText(dependency, namespace, "artifactId"),
                                findText(dependency, namespace, "version"),
                            ),
                        )
                    }
                    if (name.startsWith("dyn4k-") && !name.startsWith("dyn4k-core")) {
                        val core = name.replaceFirst("dyn4k", "dyn4k-core")
                        if (listOf(Qualification.GROUP, core, Qualification.VERSION) !in dependencies) {
                            throw IllegalArgumentException("staged target POM lacks core dependency")
                        }
                    }
                    if (name == "dyn4k" &&
                        listOf(Qualification.GROUP, "dyn4k-core", Qualification.VERSION) !in dependencies
                    ) {
                        throw IllegalArgumentException("staged root POM lacks core dependency")
                    }
                } else {
                    val metadata = StrictJson.load(Files.readString(path)) as? JsonObject
                        ?: throw IllegalArgumentException("staged Gradle metadata identity differs")
                    val component = metadata["component"] as? JsonObject ?: JsonObject(emptyMap())
                    val rootName = if (name in Qualification.modules) {
                        name
                    } else if (name.startsWith("dyn4k-core-")) {
                        "dyn4k-core"
                    } else {
                        "dyn4k"
                    }
                    for ((key, value) in listOf(
                        "group" to Qualification.GROUP,
                        "module" to rootName,
                        "version" to Qualification.VERSION,
                    )) {
                        if (Py.str(component[key]) != value) {
                            throw IllegalArgumentException("staged Gradle metadata identity differs")
                        }
                    }
                    if (name !in Qualification.modules &&
                        Py.str(component["url"]) !=
                        "../../$rootName/${Qualification.VERSION}/$rootName-${Qualification.VERSION}.module"
                    ) {
                        throw IllegalArgumentException("staged target metadata root link differs")
                    }
                    if (name in Qualification.modules) {
                        val targetName = Qualification.targetPublicationName(name, artifactTarget)
                        val matches = (metadata["variants"] as? JsonArray ?: JsonArray(emptyList()))
                            .mapNotNull { (it as? JsonObject)?.get("available-at") as? JsonObject }
                            .filter { Py.str(it["module"]) == targetName }
                        val expectedLink = linkedMapOf<String, JsonElement>(
                            "group" to JsonPrimitive(Qualification.GROUP),
                            "module" to JsonPrimitive(targetName),
                            "version" to JsonPrimitive(Qualification.VERSION),
                            "url" to JsonPrimitive(
                                "../../$targetName/${Qualification.VERSION}/" +
                                    "$targetName-${Qualification.VERSION}.module",
                            ),
                        )
                        if (matches.isEmpty() || matches.any { it != JsonObject(expectedLink) }) {
                            throw IllegalArgumentException("staged root metadata lacks target mapping")
                        }
                    }
                }
            }
        }
        val hashes = receipt["artifact_hashes"] as? JsonObject ?: JsonObject(emptyMap())
        if (hashes.keys != Qualification.modules.toSet()) {
            throw IllegalArgumentException("staged artifact hash inventory differs")
        }
        for (module in Qualification.modules) {
            val relative = Path.of("staged")
                .resolve(Qualification.targetBinaryPath(module, artifactTarget))
                .toString().replace('\\', '/')
            val binary = FullHosted.archivedFile(output, relative)
            val sidecar = FullHosted.archivedFile(output, "$relative.sha256")
            expectedPaths.add(relative)
            expectedPaths.add("$relative.sha256")
            if (FullHosted.sha256(binary) != Py.str(hashes[module]) ||
                Files.readString(sidecar).trim().lowercase() != Py.str(hashes[module])
            ) {
                throw IllegalArgumentException("archived staged artifact differs from receipt")
            }
        }
        val staged = (receipt["files"] as? JsonArray ?: JsonArray(emptyList()))
            .mapNotNull { (it as? JsonObject)?.let { item -> Py.str(item["path"]) } }
            .filter { it.startsWith("staged/") }
            .toSet()
        if (staged != expectedPaths) {
            throw IllegalArgumentException("staged artifact archive inventory differs")
        }
    }

    /**
     * `verify_staged_content`: the archived staged publication must be the audited checkout, and
     * the archived Dokka tree must be the generated one.
     */
    fun verifyStagedContent(output: Path, receipt: JsonObject, repository: Path) {
        val contract = receipt["staged_content_contract"] as? JsonObject
            ?: throw IllegalArgumentException("staged publication content contract is absent")
        if (!Files.exists(repository.resolve(".git"))) {
            throw IllegalArgumentException("staged publication candidate Git checkout is absent")
        }
        val candidateSha = Py.str(receipt["candidate_sha"]) ?: ""
        val candidateSources: Map<String, Map<String, String>>
        val licenseBytes: ByteArray
        try {
            candidateSources = CandidateSource.contract(repository, candidateSha)
            licenseBytes = FullHosted.committedInput(repository, candidateSha, "LICENSE.md")
        } catch (error: Exception) {
            throw IllegalArgumentException(
                "staged publication candidate source is unavailable",
                error,
            )
        }
        val contractSources = contract["sources"] as? JsonObject
        if (contractSources == null ||
            contractSources != sourcesJson(candidateSources)
        ) {
            throw IllegalArgumentException("staged sources differ from exact candidate")
        }
        val licensePath = FullHosted.archivedFile(output, "LICENSE.md")
        if (!Files.readAllBytes(licensePath).contentEquals(licenseBytes)) {
            throw IllegalArgumentException("staged license differs from exact candidate")
        }
        val docs = contract["api_docs_sha256"] as? JsonObject
        if (docs == null || docs.keys != Qualification.modules.toSet()) {
            throw IllegalArgumentException("staged API documentation contract is invalid")
        }
        val provenance = receipt["dokka_provenance"] as? JsonObject
        val stage = receipt["stage"] as? JsonObject
        val provenanceKeys = setOf(
            "schema", "candidate_sha", "source_tree_sha256", "stage_stdout_sha256", "modules",
        )
        val modulesProvenance = provenance?.get("modules") as? JsonObject
        if (provenance == null || provenance.keys != provenanceKeys ||
            !Py.equalsInt(provenance["schema"], 1L) ||
            Py.str(provenance["candidate_sha"]) != candidateSha ||
            provenance["source_tree_sha256"] != receipt["source_tree_sha256"] ||
            stage == null ||
            provenance["stage_stdout_sha256"] != stage["stdout_sha256"] ||
            modulesProvenance == null ||
            modulesProvenance.keys != Qualification.modules.toSet()
        ) {
            throw IllegalArgumentException(
                "archived Dokka provenance differs from candidate or staging process",
            )
        }
        val expectedDokka = mutableSetOf<String>()
        val stageStarted = Py.int(stage["started_ns"] ?: JsonPrimitive(0))
        val stageFinished = Py.int(stage["finished_ns"] ?: JsonPrimitive(0))
        for (module in Qualification.modules) {
            val name = "$module-${Qualification.VERSION}-javadoc.jar"
            val relative = (Path.of("staged")
                .resolve(Qualification.GROUP.replace(".", "/"))
                .resolve(module)
                .resolve(Qualification.VERSION)
                .resolve(name)).toString().replace('\\', '/')
            val jar = FullHosted.archivedFile(output, relative)
            val entries = modulesProvenance!![module] as? JsonObject
            if (entries == null || entries.isEmpty()) {
                throw IllegalArgumentException("archived Dokka file inventory is absent")
            }
            for ((entryName, digestElement) in entries) {
                val path = FullHosted.relativePath(entryName)
                val digest = Py.str(digestElement)
                if (path.toString().replace('\\', '/') != entryName ||
                    digest == null || !Py.SHA64.matches(digest)
                ) {
                    throw IllegalArgumentException("archived Dokka file identity is invalid")
                }
                val archiveName = "dokka/$module/$entryName"
                expectedDokka.add(archiveName)
                val archived = FullHosted.archivedFile(output, archiveName)
                if (FullHosted.sha256(archived) != digest) {
                    throw IllegalArgumentException("archived Dokka file differs from provenance")
                }
                val modified = mtimeNs(archived)
                if (modified < stageStarted || modified > stageFinished) {
                    throw IllegalArgumentException("archived Dokka file predates staging invocation")
                }
            }
            ArchiveContract.validateGeneratedDocs(jar, output.resolve("dokka").resolve(module), licenseBytes)
            if (FullHosted.sha256(jar) != Py.str(docs[module])) {
                throw IllegalArgumentException(
                    "staged API documentation differs from audited checkout",
                )
            }
        }
        val actualDokka = (receipt["files"] as? JsonArray ?: JsonArray(emptyList()))
            .mapNotNull { (it as? JsonObject)?.let { item -> Py.str(item["path"]) } }
            .filter { it.startsWith("dokka/") }
            .toSet()
        if (actualDokka != expectedDokka) {
            throw IllegalArgumentException("archived Dokka file inventory differs")
        }
        val target = if (Py.str(receipt["target"]) == "jsSafari") "js" else Py.str(receipt["target"])!!
        val audit = StagingAudit.audit(
            output.resolve("staged"),
            candidateSha,
            listOf(target),
            licensePath,
            contentContract = contract,
        )
        if (Py.str(audit["status"]) != "PASSED" || audit["content_contract"] != contract) {
            val errors = (audit["errors"] as? JsonArray ?: JsonArray(emptyList()))
                .mapNotNull { Py.str(it) }
            throw IllegalArgumentException(
                "archived staged publication differs from content audit: " +
                    errors.joinToString("; "),
            )
        }
    }

    /** `require_test_tasks`: the Gradle console lines that prove the tasks actually ran. */
    fun requireTestTasks(
        process: JsonObject,
        folder: Path,
        target: String,
        configuration: String,
        modules: List<String>,
    ) {
        val output = String(
            Files.readAllBytes(folder.resolve("stdout.txt")),
            StandardCharsets.UTF_8,
        )
        if (Py.truthy(process["exit_code"]) || "BUILD SUCCESSFUL" !in output) {
            throw IllegalArgumentException("Gradle test invocation did not succeed")
        }
        for (module in modules) {
            val task = if (module.isNotEmpty()) {
                ":$module:${FullHosted.SOURCE_TASK.getValue(target)}"
            } else {
                ":${FullHosted.SOURCE_TASK.getValue(target)}"
            }
            if (Regex("^> Task ${Regex.escape(task)}$", RegexOption.MULTILINE).find(output) == null) {
                throw IllegalArgumentException("Gradle did not execute $task")
            }
            if (target in FullHosted.NATIVE) {
                val mode = if (configuration == "optimized-opt") "Release" else "Debug"
                val link = "link${mode}Test${target.replaceFirstChar { it.uppercase() }}"
                val linkTask = if (module.isNotEmpty()) ":$module:$link" else ":$link"
                if (Regex("^> Task ${Regex.escape(linkTask)}$", RegexOption.MULTILINE)
                        .find(output) == null
                ) {
                    throw IllegalArgumentException("Gradle did not link the $mode test binary")
                }
            } else if (configuration == "production") {
                if ("jsTestTestProductionExecutableCompileSync" !in output) {
                    throw IllegalArgumentException(
                        "production Safari test executable was not built",
                    )
                }
            }
        }
    }

    /** `canonical_safari_json`: the archived input must be the committed JSON object. */
    fun canonicalSafariJson(
        repository: Path,
        candidateSha: String,
        output: Path,
        relative: String,
    ): JsonObject {
        val source = FullHosted.committedInput(repository, candidateSha, relative)
        val archived = FullHosted.archivedFile(output, "inputs/$relative")
        if (Files.size(archived) != source.size.toLong() ||
            !Files.readAllBytes(archived).contentEquals(source)
        ) {
            throw IllegalArgumentException("archived Safari source input differs: $relative")
        }
        val value = StrictJson.load(source.toString(StandardCharsets.UTF_8))
        if (value !is JsonObject) {
            throw IllegalArgumentException("Safari source inventory is not an object: $relative")
        }
        return value
    }

    /** `safari_file_observation`: one path observed without following a link. */
    fun safariFileObservation(path: Path, anchor: Path, maxHashBytes: Long? = null): JsonObject {
        val record = linkedMapOf<String, JsonElement>(
            "path" to JsonPrimitive(path.toString()),
            "status" to JsonPrimitive("MISSING"),
            "hash_status" to JsonPrimitive("NOT_HASHED"),
        )
        val parts = relativeParts(path, anchor)
        if (parts == null) {
            record["status"] = JsonPrimitive("UNSAFE")
            return JsonObject(record)
        }
        var current = anchor
        var last: BasicFileAttributes? = null
        for (index in 0..parts.size) {
            if (index > 0) current = current.resolve(parts[index - 1])
            val attributes = try {
                Files.readAttributes(current, BasicFileAttributes::class.java, LinkOption.NOFOLLOW_LINKS)
            } catch (error: NoSuchFileException) {
                return JsonObject(record)
            } catch (error: IOException) {
                record["status"] = JsonPrimitive("ERROR")
                return JsonObject(record)
            }
            last = attributes
            if (attributes.isSymbolicLink) {
                record["status"] = JsonPrimitive("UNSAFE")
                return JsonObject(record)
            }
            if (index < parts.size && !attributes.isDirectory) {
                record["status"] = JsonPrimitive("UNSAFE")
                return JsonObject(record)
            }
        }
        val identity = last!!
        if (!identity.isRegularFile) {
            record["status"] = JsonPrimitive("OTHER")
            return JsonObject(record)
        }
        record["status"] = JsonPrimitive("REGULAR")
        record["size"] = JsonPrimitive(identity.size())
        record["modified_ns"] = JsonPrimitive(identity.lastModifiedTime().to(TimeUnit.NANOSECONDS))
        if (maxHashBytes != null && identity.size() > maxHashBytes) {
            record["hash_status"] = JsonPrimitive("TOO_LARGE")
            return JsonObject(record)
        }
        val digest: String
        val after: BasicFileAttributes
        try {
            digest = FullHosted.sha256(path)
            after = Files.readAttributes(path, BasicFileAttributes::class.java, LinkOption.NOFOLLOW_LINKS)
        } catch (error: IOException) {
            record["status"] = JsonPrimitive("ERROR")
            record["hash_status"] = JsonPrimitive("NOT_HASHED")
            return JsonObject(record)
        }
        if (identityTuple(identity) != identityTuple(after)) {
            record["status"] = JsonPrimitive("CHANGED")
            record["hash_status"] = JsonPrimitive("NOT_HASHED")
            return JsonObject(record)
        }
        record["hash_status"] = JsonPrimitive("HASHED")
        record["sha256"] = JsonPrimitive(digest)
        return JsonObject(record)
    }

    /** `test_products`: the one test executable of a configuration, and its Karma input. */
    fun testProducts(
        project: Path,
        target: String,
        configuration: String,
        process: JsonObject,
        safariInput: String? = null,
        name: String? = null,
        pathTarget: String = target,
    ): MutableMap<String, JsonElement> {
        var root: Path
        var expectedProduct: Path? = null
        var selectedInput: Path? = null
        var buildRoot: Path? = null
        val products: List<Path>
        if (target in FullHosted.NATIVE) {
            val binaryMode = if (configuration == "optimized-opt") "releaseTest" else "debugTest"
            root = project.resolve("build/bin").resolve(target).resolve(binaryMode)
            products = listDirectory(root).filter { path ->
                Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS) &&
                    (path.fileName.toString().endsWith(".kexe") ||
                        path.fileName.toString().endsWith(".exe"))
            }
        } else if (target == "jsSafari") {
            val selection = FullHostedRules.safariProductPaths(project.toString(), configuration, name!!)
            expectedProduct = Path.of(selection.expected)
            selectedInput = Path.of(selection.karmaInput)
            buildRoot = Path.of(selection.buildRoot)
            if (safariInput != selection.karmaInput) {
                throw IllegalArgumentException("Safari Karma input differs from validated config")
            }
            root = expectedProduct.parent
            if (Py.str(safariFileObservation(expectedProduct, project, 0)["status"]) == "UNSAFE") {
                throw IllegalArgumentException("Safari compiler product path is unsafe")
            }
            val found = mutableListOf<Path>()
            try {
                Files.newDirectoryStream(root).use { stream ->
                    for (entry in stream) {
                        val entryName = entry.fileName.toString()
                        if (!entryName.endsWith("-test.js")) continue
                        if (entryName == "kotlin-kotlin-test.js") {
                            val helper = safariFileObservation(root.resolve(entryName), project, 0)
                            if (Py.str(helper["status"]) != "REGULAR") {
                                throw IllegalArgumentException(
                                    "Safari Kotlin test runtime helper is unsafe",
                                )
                            }
                            continue
                        }
                        found.add(root.resolve(entryName))
                        if (found.size == 2) break
                    }
                }
            } catch (error: NoSuchFileException) {
                // The directory is absent: no product was produced.
            } catch (error: java.nio.file.NotDirectoryException) {
                // The path is a file: no product layout exists.
            } catch (error: IOException) {
                throw IllegalArgumentException("Safari compiler product directory is unavailable")
            }
            products = found
        } else {
            throw IllegalArgumentException(
                "exactly one $configuration test executable is required: $target",
            )
        }
        if (products.size != 1 || (target == "jsSafari" && products[0] != expectedProduct)) {
            throw IllegalArgumentException(
                "exactly one $configuration test executable is required: $root",
            )
        }
        val product = products[0]
        val started = Py.int(process["started_ns"] ?: JsonPrimitive(0))
        val finished = Py.int(process["finished_ns"] ?: JsonPrimitive(0))
        if (target == "jsSafari") {
            val compiler = safariFileObservation(product, project)
            val karma = safariFileObservation(selectedInput!!, buildRoot!!)
            for ((label, observed) in listOf("compiler" to compiler, "Karma" to karma)) {
                if (Py.str(observed["status"]) != "REGULAR" ||
                    Py.str(observed["hash_status"]) != "HASHED" ||
                    Py.int(observed["size"] ?: JsonPrimitive(0)) <= 0
                ) {
                    throw IllegalArgumentException(
                        "Safari $label input is missing, unsafe, or changed",
                    )
                }
                val modified = Py.int(observed["modified_ns"] ?: JsonPrimitive(0))
                if (modified < started || modified > finished) {
                    throw IllegalArgumentException("Safari $label input predates invocation")
                }
            }
            if (Py.int(compiler["size"]!!) != Py.int(karma["size"]!!) ||
                Py.str(compiler["sha256"]) != Py.str(karma["sha256"])
            ) {
                throw IllegalArgumentException("Safari compiler and Karma input bytes differ")
            }
            return linkedMapOf(
                "path" to JsonPrimitive(product.toString()),
                "sha256" to compiler.getValue("sha256"),
                "size" to compiler.getValue("size"),
                "modified_ns" to compiler.getValue("modified_ns"),
                "karma_input" to karma,
            )
        }
        val metadata = Files.readAttributes(product, BasicFileAttributes::class.java)
        val modified = metadata.lastModifiedTime().to(TimeUnit.NANOSECONDS)
        if (modified < started || modified > finished) {
            throw IllegalArgumentException("test executable predates invocation")
        }
        return linkedMapOf(
            "path" to JsonPrimitive(product.toString()),
            "sha256" to JsonPrimitive(FullHosted.sha256(product)),
            "size" to JsonPrimitive(metadata.size()),
            "modified_ns" to JsonPrimitive(modified),
        )
    }

    /** `safari_product_inventory`: bounded observations of both Safari product layouts. */
    fun safariProductInventory(project: Path, configuration: String, name: String): JsonObject {
        val selection = FullHostedRules.safariProductPaths(project.toString(), configuration, name)
        val expected = Path.of(selection.expected)
        val karmaInput = Path.of(selection.karmaInput)
        val buildRoot = Path.of(selection.buildRoot)
        val karmaPackage = Path.of(selection.karmaPackage)
        val packageName = karmaPackage.fileName.toString()
        val roots = LinkedHashMap<String, JsonElement>()
        roots["compiler"] = inspect(project, project.resolve("build/compileSync/js/test"))
        roots["karma_package"] = inspect(buildRoot, karmaPackage)
        if (buildRoot != project) {
            roots["root_compiler"] = inspect(buildRoot, buildRoot.resolve("build/compileSync/js/test"))
            roots["module_package"] = inspect(project, project.resolve("build/js/packages").resolve(packageName))
        }
        return buildJsonObject {
            put("expected", JsonPrimitive(expected.toString()))
            put("karma_input", JsonPrimitive(karmaInput.toString()))
            put(
                "observations",
                buildJsonObject {
                    put("expected", safariFileObservation(expected, project, HASH_BUDGET))
                    put("karma_input", safariFileObservation(karmaInput, buildRoot, HASH_BUDGET))
                },
            )
            put("roots", JsonObject(roots))
        }
    }

    /**
     * `inspect`: the bounded inventory of one Safari product root.
     *
     * `hash_budget` is shared across the whole walk, and the entry list stops at 128; the retained
     * subset of a crowded directory is the sorted order of the first `remaining + 1` entries the
     * file system returned, exactly as the reference slices `os.scandir`.
     */
    private fun inspect(base: Path, root: Path): JsonObject {
        val entries = mutableListOf<JsonObject>()
        val record = linkedMapOf<String, JsonElement>(
            "base" to JsonPrimitive(base.toString()),
            "root" to JsonPrimitive(root.toString()),
            "present" to JsonPrimitive(false),
            "unsafe_symlink" to JsonPrimitive(false),
            "entries" to JsonArray(entries),
            "truncated" to JsonPrimitive(false),
        )
        val parts = relativeParts(root, base) ?: return JsonObject(record)
        var current = base
        for (part in parts) {
            current = current.resolve(part)
            val attributes = try {
                Files.readAttributes(current, BasicFileAttributes::class.java, LinkOption.NOFOLLOW_LINKS)
            } catch (error: NoSuchFileException) {
                return JsonObject(record)
            } catch (error: IOException) {
                return JsonObject(record)
            }
            if (attributes.isSymbolicLink) {
                record["unsafe_symlink"] = JsonPrimitive(true)
                return JsonObject(record)
            }
            if (!attributes.isDirectory) return JsonObject(record)
        }
        record["present"] = JsonPrimitive(true)
        var budget = HASH_BUDGET
        var truncated = false

        fun scan(directory: Path) {
            val remaining = INVENTORY_LIMIT - entries.size
            val children = mutableListOf<Path>()
            if (Files.isDirectory(directory)) {
                try {
                    Files.newDirectoryStream(directory).use { stream ->
                        for (entry in stream) {
                            if (children.size >= remaining + 1) break
                            children.add(entry)
                        }
                    }
                } catch (error: IOException) {
                    // An unreadable directory is observed as empty, as `os.scandir` failure is.
                }
            }
            val overflow = children.size > remaining
            val ordered = children.take(remaining).sortedWith { left, right ->
                CanonicalText.compare(left.toString(), right.toString())
            }
            for ((index, path) in ordered.withIndex()) {
                val attributes = try {
                    Files.readAttributes(path, BasicFileAttributes::class.java, LinkOption.NOFOLLOW_LINKS)
                } catch (error: IOException) {
                    continue
                }
                val kind = kindOf(attributes)
                val entry = linkedMapOf<String, JsonElement>(
                    "path" to JsonPrimitive(relativeToPosix(path, base)),
                    "kind" to JsonPrimitive(kind),
                    "size" to JsonPrimitive(attributes.size()),
                    "mode" to JsonPrimitive(modeOf(path, attributes)),
                    "modified_ns" to JsonPrimitive(attributes.lastModifiedTime().to(TimeUnit.NANOSECONDS)),
                )
                if (kind == "file" && attributes.size() <= budget) {
                    entry["sha256"] = JsonPrimitive(FullHosted.sha256(path))
                    budget -= attributes.size()
                }
                entries.add(JsonObject(entry))
                if (kind == "directory") {
                    scan(path)
                    if (truncated) return
                }
                if (entries.size == INVENTORY_LIMIT && (overflow || index + 1 < children.size)) {
                    truncated = true
                    return
                }
            }
            if (overflow) truncated = true
        }

        scan(root)
        record["truncated"] = JsonPrimitive(truncated)
        return JsonObject(record)
    }

    /** `product_inventory`: the bounded inventory one failed product selection retains. */
    fun productInventory(
        project: Path,
        target: String,
        configuration: String? = null,
        name: String? = null,
    ): JsonObject {
        if (target == "jsSafari") {
            return safariProductInventory(project, configuration!!, name!!)
        }
        val root = project.resolve("build/bin")
        val entries = mutableListOf<JsonObject>()
        val result = linkedMapOf<String, JsonElement>(
            "root" to JsonPrimitive(root.toString()),
            "requested_target" to JsonPrimitive(root.resolve(target).toString()),
            "present" to JsonPrimitive(Files.isDirectory(root) && !Files.isSymbolicLink(root)),
            "entries" to JsonArray(entries),
            "truncated" to JsonPrimitive(false),
        )
        if (!Files.isDirectory(root) || Files.isSymbolicLink(root)) return JsonObject(result)
        var budget = HASH_BUDGET
        var truncated = false

        fun scan(directory: Path) {
            val children = listDirectory(directory)
            val ordered = if (directory == root) {
                children.sortedWith { left, right ->
                    val leftNamed = left.fileName.toString() != target
                    val rightNamed = right.fileName.toString() != target
                    when {
                        leftNamed != rightNamed -> if (leftNamed) 1 else -1
                        else -> CanonicalText.compare(left.fileName.toString(), right.fileName.toString())
                    }
                }
            } else {
                children.sortedWith { left, right ->
                    CanonicalText.compare(left.fileName.toString(), right.fileName.toString())
                }
            }
            for (path in ordered) {
                if (entries.size == INVENTORY_LIMIT) {
                    truncated = true
                    return
                }
                val attributes = Files.readAttributes(path, BasicFileAttributes::class.java, LinkOption.NOFOLLOW_LINKS)
                val kind = kindOf(attributes)
                val entry = linkedMapOf<String, JsonElement>(
                    "path" to JsonPrimitive(relativeToPosix(path, project)),
                    "kind" to JsonPrimitive(kind),
                    "size" to JsonPrimitive(attributes.size()),
                    "mode" to JsonPrimitive(modeOf(path, attributes)),
                    "modified_ns" to JsonPrimitive(attributes.lastModifiedTime().to(TimeUnit.NANOSECONDS)),
                )
                if (kind == "file" && attributes.size() <= budget) {
                    entry["sha256"] = JsonPrimitive(FullHosted.sha256(path))
                    budget -= attributes.size()
                }
                entries.add(JsonObject(entry))
                if (kind == "directory") {
                    scan(path)
                    if (truncated) return
                }
            }
        }

        scan(root)
        result["truncated"] = JsonPrimitive(truncated)
        return JsonObject(result)
    }

    /**
     * `collect_test_products`: select each project's product, or retain the bounded inventory and
     * fail with its path and digest.
     */
    fun collectTestProducts(
        projects: Map<String, Path>,
        target: String,
        configuration: String,
        process: JsonObject,
        diagnostic: Path,
        archiveRoot: Path,
        safariInputs: Map<String, String>? = null,
    ): MutableMap<String, MutableMap<String, JsonElement>> {
        val products = LinkedHashMap<String, MutableMap<String, JsonElement>>()
        val errors = mutableListOf<String>()
        for ((name, project) in projects) {
            try {
                products[name] = testProducts(
                    project,
                    target,
                    configuration,
                    process,
                    safariInputs?.get(name),
                    name,
                )
            } catch (error: IllegalArgumentException) {
                errors.add("$name: ${error.message}")
            }
        }
        if (errors.isNotEmpty()) {
            diagnostic.parent?.let { Files.createDirectories(it) }
            val record = buildJsonObject {
                put("schema", JsonPrimitive(1))
                put("target", JsonPrimitive(target))
                put("configuration", JsonPrimitive(configuration))
                put("invocation_id", process["invocation_id"] ?: JsonNull)
                put("started_ns", process["started_ns"] ?: JsonNull)
                put("finished_ns", process["finished_ns"] ?: JsonNull)
                put("exit_code", process["exit_code"] ?: JsonNull)
                put(
                    "projects",
                    buildJsonObject {
                        for ((name, project) in projects) {
                            put(name, productInventory(project, target, configuration, name))
                        }
                    },
                )
            }
            Files.write(
                diagnostic,
                (PyJson.renderSorted(record) + "\n").toByteArray(StandardCharsets.UTF_8),
            )
            val relative = relativeToPosix(diagnostic, archiveRoot)
            throw IllegalArgumentException(
                errors.joinToString("; ") +
                    "; product inventory $relative SHA-256 ${FullHosted.sha256(diagnostic)}",
            )
        }
        return products
    }

    /** `archive_test_product`: archive the selected executable and, for Safari, its Karma input. */
    fun archiveTestProduct(
        product: MutableMap<String, JsonElement>,
        output: Path,
        configuration: String,
        name: String,
        target: String,
    ) {
        val productPath = Py.str(product["path"])!!
        val archiveName = "$configuration/executables/$name/${pathName(productPath, target)}"
        val copied = FullHosted.archiveCopy(Path.of(productPath), output, archiveName)
        for (key in listOf("sha256", "size", "modified_ns")) {
            if (copied[key] != product[key]) {
                throw IllegalArgumentException("test executable changed after observation")
            }
        }
        product["archive_path"] = JsonPrimitive(archiveName)
        if (target == "jsSafari") {
            @Suppress("UNCHECKED_CAST")
            val selected = product["karma_input"] as MutableMap<String, JsonElement>
            val inputPath = Py.str(selected["path"])!!
            val inputName = "$configuration/karma-inputs/$name/${pathName(inputPath, target)}"
            val inputCopy = FullHosted.archiveCopy(Path.of(inputPath), output, inputName)
            for (key in listOf("sha256", "size", "modified_ns")) {
                if (inputCopy[key] != selected[key]) {
                    throw IllegalArgumentException("Safari Karma input changed after observation")
                }
            }
            selected["archive_path"] = JsonPrimitive(inputName)
        }
    }

    /** `capture_safari_config`: archive one generated Karma configuration and its identity. */
    fun captureSafariConfig(
        repository: Path,
        candidateSha: String,
        project: String,
        configuration: String,
        process: JsonObject,
        output: Path,
        archiveName: String,
    ): JsonObject {
        val relative = SafariReporter.configRelative(project)
        val source = repository.resolve(relative)
        val generated = try {
            SafariReporterHost.readGeneratedConfig(repository, Path.of(relative))
        } catch (error: IOException) {
            throw IllegalArgumentException(
                "Safari generated Karma config is absent or unsafe: $relative",
                error,
            )
        }
        val modified = generated.identity.modifiedNanos
        val started = Py.int(process["started_ns"] ?: JsonPrimitive(0))
        val finished = Py.int(process["finished_ns"] ?: JsonPrimitive(0))
        if (modified < started || modified > finished) {
            throw IllegalArgumentException("Safari generated Karma config is stale: $relative")
        }
        val destination = FullHosted.relativePath(archiveName).fold(output) { base, part -> base.resolve(part) }
        destination.parent?.let { Files.createDirectories(it) }
        Files.newOutputStream(destination, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE)
            .use { it.write(generated.data) }
        Files.setLastModifiedTime(destination, FileTime.from(modified, TimeUnit.NANOSECONDS))
        val fragment = SafariReporterHost.committedFragment(repository, candidateSha)
        SafariReporter.validateConfig(
            generated.data,
            fragment,
            repository.toString(),
            project,
            configuration,
        )
        // `os.fstat` reports `st_dev`/`st_ino` of the generated configuration itself; the JVM file
        // key is opaque, so both are read from the unix view of the same path.
        val device = unixNumber(source, "unix:dev")
        val inode = unixNumber(source, "unix:ino")
        return buildJsonObject {
            put("path", JsonPrimitive(archiveName))
            put("sha256", JsonPrimitive(FullHosted.sha256(destination)))
            put("size", JsonPrimitive(generated.data.size))
            put("modified_ns", JsonPrimitive(mtimeNs(destination)))
            put("source_path", JsonPrimitive(source.toString()))
            put("project", JsonPrimitive(SafariReporter.canonicalProject(project)))
            put("configuration", JsonPrimitive(configuration))
            put("source_device", JsonPrimitive(device))
            put("source_inode", JsonPrimitive(inode))
            put("input_path", JsonPrimitive(FullHostedRules.safariConfigInput(generated.data)))
        }
    }

    /**
     * `verify_safari_reporter_archive`: the staged reporter runs, the generated configurations, and
     * their archive members must all be the committed ones.
     */
    fun verifySafariReporterArchive(
        output: Path,
        receipt: JsonObject,
        lane: JsonObject,
        candidateRepository: Path,
        repositoryRoot: Path,
    ) {
        val fragment = FullHosted.committedInput(
            candidateRepository,
            Py.str(receipt["candidate_sha"])!!,
            SafariReporter.SOURCE,
        )
        val expectedSha = io.github.rubixhacker.harness.contract.Sha256.of(fragment)
        val stages = lane["safari_reporter_stage"] as? JsonObject
        val configs = lane["safari_karma_configs"] as? JsonObject
        if (stages == null || stages.keys != setOf("source", "consumer") ||
            configs == null || configs.keys != setOf("dyn4k-core", "dyn4k", "consumer")
        ) {
            throw IllegalArgumentException(
                "Safari reporter stage or generated config inventory is absent",
            )
        }
        val expectedProjects = linkedMapOf(
            "source" to linkedMapOf("dyn4k-core" to "CLEAN", "dyn4k" to "CLEAN"),
            "consumer" to linkedMapOf(SafariReporter.CONSUMER to "CLEAN"),
        )
        for ((phase, expected) in expectedProjects) {
            val state = stages[phase] as? JsonObject
            val projects = state?.get("projects") as? JsonObject
            if (state == null || Py.str(state["status"]) != "CLEAN" ||
                Py.str(state["source_sha256"]) != expectedSha ||
                projects != JsonObject(expected.mapValues { JsonPrimitive(it.value) }) ||
                (state["forensic"] as? JsonArray)?.isEmpty() != true ||
                Py.truthy(state["leftovers"])
            ) {
                throw IllegalArgumentException(
                    "Safari reporter staging differs from committed source",
                )
            }
        }
        val expectedArchive = mutableSetOf<String>()
        val configuration = Py.str(lane["configuration"])!!
        for ((name, project) in listOf(
            "dyn4k-core" to "dyn4k-core",
            "dyn4k" to "dyn4k",
            "consumer" to SafariReporter.CONSUMER,
        )) {
            val record = configs[name] as? JsonObject
            val expectedPath = "$configuration/karma-config/$name/karma.conf.js"
            val expectedSource = repositoryRoot.resolve(SafariReporter.configRelative(project))
            val process = if (name == "consumer") {
                lane["consumer_process"] as? JsonObject
            } else {
                lane["source_process"] as? JsonObject
            }
            if (record == null ||
                Py.str(record["path"]) != expectedPath ||
                Py.str(record["source_path"]) != expectedSource.toString() ||
                Py.str(record["project"]) != SafariReporter.canonicalProject(project) ||
                Py.str(record["configuration"]) != configuration ||
                !Py.isInt(record["source_device"]) || Py.int(record["source_device"]) < 0 ||
                !Py.isInt(record["source_inode"]) || Py.int(record["source_inode"]) <= 0
            ) {
                throw IllegalArgumentException("Safari generated config identity differs")
            }
            val raw = FullHosted.archivedFile(output, expectedPath)
            val modified = mtimeNs(raw)
            if (Py.str(record["sha256"]) != FullHosted.sha256(raw) ||
                Py.int(record["size"] ?: JsonPrimitive(0)) != Files.size(raw) ||
                Py.int(record["modified_ns"] ?: JsonPrimitive(0)) != modified ||
                process == null ||
                modified < Py.int(process["started_ns"] ?: JsonPrimitive(0)) ||
                modified > Py.int(process["finished_ns"] ?: JsonPrimitive(0))
            ) {
                throw IllegalArgumentException(
                    "Safari generated config bytes or process window differ",
                )
            }
            SafariReporter.validateConfig(
                Files.readAllBytes(raw),
                fragment,
                repositoryRoot.toString(),
                project,
                configuration,
            )
            if (Py.str(record["input_path"]) != FullHostedRules.safariConfigInput(Files.readAllBytes(raw))) {
                throw IllegalArgumentException("Safari generated config input path differs")
            }
            expectedArchive.add(expectedPath)
        }
        val actual = (receipt["files"] as? JsonArray ?: JsonArray(emptyList()))
            .mapNotNull { (it as? JsonObject)?.let { item -> Py.str(item["path"]) } }
            .filter { it.startsWith("$configuration/karma-config/") }
            .toSet()
        if (actual != expectedArchive) {
            throw IllegalArgumentException(
                "extra or missing Safari generated config archive member",
            )
        }
    }

    /** `parse_graph`: the resolved consumer graph, bound to the staged bytes and the cache. */
    fun parseGraph(
        folder: Path,
        process: JsonObject,
        target: String,
        hashes: JsonObject,
        staging: String,
        expectedHome: String,
        stagedRoot: Path? = null,
    ): JsonObject {
        if (Py.truthy(process["exit_code"])) {
            throw IllegalArgumentException("external consumer graph resolution failed")
        }
        val lines = String(Files.readAllBytes(folder.resolve("stdout.txt")), StandardCharsets.UTF_8)
            .split('\n')
            .filter { it.startsWith("DYN4K_RESOLVED_GRAPH=") }
            .map { it.removePrefix("DYN4K_RESOLVED_GRAPH=") }
        if (lines.size != 1) {
            throw IllegalArgumentException(
                "external consumer graph observation is absent or duplicate",
            )
        }
        val graph = StrictJson.load(lines[0]) as? JsonObject
            ?: throw IllegalArgumentException("external consumer graph observation is invalid")
        val expectedConfig = if (target == "jsSafari") "jsCompileClasspath" else "${target}CompileKlibraries"
        if (Py.str(graph["configuration"]) != expectedConfig) {
            throw IllegalArgumentException("external consumer graph configuration differs")
        }
        val reportedHome = Py.str(graph["gradle_user_home"])
        if (reportedHome.isNullOrEmpty()) {
            throw IllegalArgumentException("Gradle user home observation is absent")
        }
        if (FullHosted.originalPath(target, reportedHome) != FullHosted.originalPath(target, expectedHome)) {
            throw IllegalArgumentException("Gradle user home differs from receipt")
        }
        val artifactTarget = if (target == "jsSafari") "js" else target
        val required = Qualification.modules.map {
            "${Qualification.GROUP}:${Qualification.targetPublicationName(it, artifactTarget)}:" +
                Qualification.VERSION
        }.toSet()
        val artifacts = (graph["artifacts"] as? JsonArray)?.map { it as? JsonObject }
        if (artifacts == null || artifacts.any { it == null }) {
            throw IllegalArgumentException("external consumer graph artifacts are invalid")
        }
        val components = (graph["components"] as? JsonArray)?.mapNotNull { Py.str(it) }
        if (components == null || components.size != graph["components"]!!.let { (it as JsonArray).size } ||
            components.size != components.toSet().size
        ) {
            throw IllegalArgumentException("external consumer dependency graph is invalid")
        }
        for (item in artifacts) {
            val path = FullHosted.originalPath(target, Py.str(item!!["file"]))
            if (pathName(path, target) != Py.str(item["name"]) ||
                !Py.isInt(item["size"]) || Py.int(item["size"]) <= 0 ||
                !Py.SHA64.matches(Py.str(item["sha256"]) ?: "")
            ) {
                throw IllegalArgumentException(
                    "external consumer graph artifact identity is invalid",
                )
            }
        }
        val stagedPrefix = "${Qualification.GROUP}:"
        val artifactComponents = artifacts.map { Py.str(it!!["component"]) }
        if (!artifactComponents.toSet().containsAll(required)) {
            throw IllegalArgumentException(
                "external consumer graph lacks staged target components",
            )
        }
        val stagedArtifacts = artifactComponents.filter { it != null && it.startsWith(stagedPrefix) }
        if (stagedArtifacts.groupingBy { it }.eachCount() != required.associateWith { 1 }) {
            throw IllegalArgumentException(
                "external consumer graph has extra or duplicate staged target artifacts",
            )
        }
        val rootComponents = Qualification.modules.map {
            "${Qualification.GROUP}:$it:${Qualification.VERSION}"
        }.toSet()
        if (components.filter { it.startsWith(stagedPrefix) }.toSet() != required + rootComponents) {
            throw IllegalArgumentException(
                "external consumer dependency graph lacks or adds staged targets",
            )
        }
        val gradleHome = FullHosted.originalPath(target, Py.str(graph["gradle_user_home"]))
        for (module in Qualification.modules) {
            val name = Qualification.targetPublicationName(module, artifactTarget)
            val matches = artifacts.filter {
                Py.str(it!!["component"]) == "${Qualification.GROUP}:$name:${Qualification.VERSION}"
            }
            if (matches.isEmpty()) {
                throw IllegalArgumentException(
                    "external consumer resolved artifact differs from staging",
                )
            }
            val expectedFile = joinOriginal(
                target,
                FullHosted.originalPath(target, staging),
                Qualification.targetBinaryPath(module, artifactTarget),
            )
            val resolvedFile = FullHosted.originalPath(target, Py.str(matches[0]!!["file"]))
            val stagedBinary = (stagedRoot ?: Path.of(staging))
                .resolve(Qualification.targetBinaryPath(module, artifactTarget))
            if (!Files.isRegularFile(stagedBinary, LinkOption.NOFOLLOW_LINKS) ||
                Files.isSymbolicLink(stagedBinary) ||
                FullHosted.sha256(stagedBinary) != Py.str(hashes[module])
            ) {
                throw IllegalArgumentException("staged target bytes differ from graph input")
            }
            val cacheDigest = sha1(Files.readAllBytes(stagedBinary))
            val cacheDigests = setOf(cacheDigest, cacheDigest.trimStart('0').ifEmpty { "0" })
            val cachedFiles = cacheDigests.map { digest ->
                joinOriginal(
                    target,
                    gradleHome,
                    "caches/modules-2/files-2.1/${Qualification.GROUP}/$name/" +
                        "${Qualification.VERSION}/$digest/${pathName(resolvedFile, target)}",
                )
            }.toSet()
            if (resolvedFile != expectedFile) {
                val cacheParts = pathSegments(target, resolvedFile)
                if (cacheParts.size < 8 ||
                    cacheParts.subList(cacheParts.size - 8, cacheParts.size - 2) !=
                    listOf("caches", "modules-2", "files-2.1", Qualification.GROUP, name, Qualification.VERSION)
                ) {
                    throw IllegalArgumentException(
                        "external consumer resolved artifact differs from staging",
                    )
                }
                if (!pathSegments(target, resolvedFile).let { parts ->
                        parts.size >= pathSegments(target, gradleHome).size &&
                            parts.subList(0, pathSegments(target, gradleHome).size) ==
                            pathSegments(target, gradleHome)
                    }
                ) {
                    throw IllegalArgumentException("Gradle user home differs from resolved cache root")
                }
                if (cacheParts[cacheParts.size - 2] !in cacheDigests) {
                    throw IllegalArgumentException("Gradle cache digest differs from staged bytes")
                }
            }
            if (matches.size != 1 ||
                Py.str(matches[0]!!["sha256"]) != Py.str(hashes[module]) ||
                (resolvedFile != expectedFile && resolvedFile !in cachedFiles)
            ) {
                throw IllegalArgumentException(
                    "external consumer resolved artifact differs from staging",
                )
            }
        }
        return graph
    }

    /**
     * `retain_failed_safari_source_xml`: keep the unverified source reports of a failed Safari lane.
     *
     * The reference publishes the retained tree with `rename` inside an open parent directory.
     * The JVM has no descriptor-relative rename, so the parent identity is re-checked before and
     * after publication instead.
     */
    fun retainFailedSafariSourceXml(
        repository: Path,
        destination: Path,
        process: JsonObject,
        validationError: Throwable,
    ): JsonObject {
        val startedElement = process["started_ns"]
        val finishedElement = process["finished_ns"]
        val command = (process["command"] as? JsonArray)?.mapNotNull { Py.str(it) }
        val invocation = Py.str(process["invocation_id"]) ?: ""
        val required = setOf("--rerun-tasks", ":dyn4k-core:jsBrowserTest", ":dyn4k:jsBrowserTest")
        if (!Py.isInt(startedElement) || !Py.isInt(finishedElement) ||
            Py.int(startedElement) <= 0 ||
            Py.int(finishedElement) < Py.int(startedElement) ||
            !Py.isInt(process["pid"]) || Py.int(process["pid"]) <= 0 ||
            !Py.equalsInt(process["exit_code"], 0L) ||
            !Regex("[0-9a-f]{32}").matches(invocation) ||
            command == null || !command.toSet().containsAll(required) ||
            "-PqualificationInvocationId=$invocation" !in command
        ) {
            throw IllegalArgumentException(
                "failed Safari source XML has no completed source process anchor",
            )
        }
        val started = Py.int(startedElement)
        val finished = Py.int(finishedElement)
        if (DefaultHostEnvironment.isWindows()) {
            throw UnsupportedOperationException(
                "failed Safari source XML retention is not supported on this host: the Windows " +
                    "locked-directory scan (safari_windows_file.LockedDirectory) is not ported",
            )
        }
        val snapshots = mutableListOf<FailedSourceXmlSnapshot>()
        var total = 0L
        for (module in Qualification.modules) {
            val relative = Path.of(module).resolve("build/test-results/jsBrowserTest")
            val directory = SafariReporterHost.openDirectoryNoFollow(repository, relative)
            val names = mutableListOf<String>()
            var count = 0
            try {
                Files.newDirectoryStream(directory).use { stream ->
                    for (entry in stream) {
                        count++
                        if (count > MAX_FAILED_SOURCE_XML_ENTRIES) {
                            throw IllegalArgumentException(
                                "failed Safari source XML directory is crowded",
                            )
                        }
                        val entryName = entry.fileName.toString()
                        if (entryName.startsWith("TEST-") && entryName.endsWith(".xml")) {
                            FullHosted.relativePath("diagnostic/source-xml/$module/$entryName")
                            names.add(entryName)
                            if (names.size > MAX_FAILED_SOURCE_XML_FILES) {
                                throw IllegalArgumentException(
                                    "failed Safari source XML count exceeds bound",
                                )
                            }
                        }
                    }
                }
            } catch (error: NoSuchFileException) {
                throw IllegalArgumentException("failed Safari source XML is absent")
            } catch (error: IOException) {
                throw IllegalArgumentException("failed Safari source XML is absent")
            }
            if (names.isEmpty()) throw IllegalArgumentException("failed Safari source XML is absent")
            for (name in names.sortedWith(CanonicalText::compare)) {
                val path = directory.resolve(name)
                val before = try {
                    Files.readAttributes(path, BasicFileAttributes::class.java, LinkOption.NOFOLLOW_LINKS)
                } catch (error: IOException) {
                    throw IllegalArgumentException(
                        "failed Safari source XML is unsafe, oversized, or stale",
                    )
                }
                val modified = before.lastModifiedTime().to(TimeUnit.NANOSECONDS)
                if (!before.isRegularFile || before.size() > MAX_FAILED_SOURCE_XML_BYTES ||
                    modified < started || modified > finished
                ) {
                    throw IllegalArgumentException(
                        "failed Safari source XML is unsafe, oversized, or stale",
                    )
                }
                total += before.size()
                if (total > MAX_FAILED_SOURCE_XML_TOTAL) {
                    throw IllegalArgumentException("failed Safari source XML total exceeds bound")
                }
                val raw = try {
                    Files.readAllBytes(path)
                } catch (error: IOException) {
                    throw IllegalArgumentException("failed Safari source XML changed while reading")
                }
                val after = try {
                    Files.readAttributes(path, BasicFileAttributes::class.java, LinkOption.NOFOLLOW_LINKS)
                } catch (error: IOException) {
                    throw IllegalArgumentException("failed Safari source XML changed while reading")
                }
                if (raw.size.toLong() != before.size() || identityTuple(before) != identityTuple(after)) {
                    throw IllegalArgumentException("failed Safari source XML changed while reading")
                }
                snapshots.add(
                    FailedSourceXmlSnapshot(
                        module,
                        name,
                        raw,
                        modified,
                        unixNumber(path, "unix:dev"),
                        unixNumber(path, "unix:ino"),
                    ),
                )
            }
        }
        val reports = snapshots.map { snapshot ->
            buildJsonObject {
                put("module", JsonPrimitive(snapshot.module))
                put("path", JsonPrimitive("diagnostic/source-xml/${snapshot.module}/${snapshot.name}"))
                put(
                    "source_path",
                    JsonPrimitive(
                        repository.resolve(snapshot.module)
                            .resolve("build/test-results/jsBrowserTest")
                            .resolve(snapshot.name).toString(),
                    ),
                )
                put("sha256", JsonPrimitive(io.github.rubixhacker.harness.contract.Sha256.of(snapshot.raw)))
                put("size", JsonPrimitive(snapshot.raw.size))
                put("modified_ns", JsonPrimitive(snapshot.modifiedNs))
                put("source_device", JsonPrimitive(snapshot.device))
                put("source_inode", JsonPrimitive(snapshot.inode))
            }
        }
        publishFailedSourceXml(destination, snapshots)
        return buildJsonObject {
            put("status", JsonPrimitive("UNVERIFIED"))
            put("validation_error", JsonPrimitive(validationError.message ?: validationError.toString()))
            put("source_pid", process["pid"] ?: JsonNull)
            put("invocation_id", JsonPrimitive(invocation))
            put("source_started_ns", JsonPrimitive(started))
            put("source_finished_ns", JsonPrimitive(finished))
            put("reports", JsonArray(reports))
        }
    }

    private fun publishFailedSourceXml(destination: Path, snapshots: List<FailedSourceXmlSnapshot>) {
        if (!destination.isAbsolute) {
            throw IllegalArgumentException(
                "failed Safari source XML destination is not absolute",
            )
        }
        val anchor = destination.root
        val relative = anchor.relativize(destination.toAbsolutePath().normalize())
        val parentRelative = relative.resolve("diagnostic")
        try {
            Files.createDirectory(
                SafariReporterHost.openDirectoryNoFollow(anchor, relative).resolve("diagnostic"),
            )
        } catch (error: java.nio.file.FileAlreadyExistsException) {
            // The diagnostic directory already exists; the reference tolerates that.
        }
        val parent = SafariReporterHost.openDirectoryNoFollow(anchor, parentRelative)
        val identity = SafariReporterHost.identityOf(parent)
        val temporary = parent.resolve(".source-xml-${UUID.randomUUID().toString().replace("-", "")}")
        var created = false
        try {
            val existing = try {
                Files.readAttributes(
                    parent.resolve("source-xml"),
                    BasicFileAttributes::class.java,
                    LinkOption.NOFOLLOW_LINKS,
                )
                true
            } catch (error: IOException) {
                false
            }
            if (existing) {
                throw IllegalArgumentException(
                    "failed Safari source XML diagnostic path already exists",
                )
            }
            Files.createDirectory(temporary)
            created = true
            for (snapshot in snapshots) {
                val moduleDirectory = temporary.resolve(snapshot.module)
                if (!Files.exists(moduleDirectory)) Files.createDirectory(moduleDirectory)
                val target = moduleDirectory.resolve(snapshot.name)
                Files.newOutputStream(target, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE)
                    .use { it.write(snapshot.raw) }
                Files.setLastModifiedTime(
                    target,
                    FileTime.from(snapshot.modifiedNs, TimeUnit.NANOSECONDS),
                )
            }
            if (!SafariReporterHost.sameDirectory(anchor, parentRelative, identity)) {
                throw IllegalArgumentException("failed Safari source XML diagnostic parent changed")
            }
            Files.move(temporary, parent.resolve("source-xml"))
            created = false
            if (!SafariReporterHost.sameDirectory(anchor, parentRelative, identity)) {
                throw IllegalArgumentException("failed Safari source XML diagnostic parent changed")
            }
        } finally {
            if (created) {
                Files.walk(temporary).use { walk ->
                    walk.sorted(Comparator.reverseOrder()).forEach { Files.deleteIfExists(it) }
                }
            }
        }
    }

    /** `copy_reports`: verify and archive every module's source XML reports. */
    fun copyReports(
        repository: Path,
        target: String,
        destination: Path,
        process: JsonObject,
        expected: JsonObject,
        safariVersion: String? = null,
        diagnostic: MutableMap<String, JsonElement>? = null,
    ): List<JsonObject> {
        val reports = mutableListOf<JsonObject>()
        for (module in Qualification.modules) {
            val directory = repository.resolve(module)
                .resolve("build/test-results")
                .resolve(FullHosted.SOURCE_TASK.getValue(target))
            val paths = listDirectory(directory)
                .filter { it.fileName.toString().startsWith("TEST-") && it.fileName.toString().endsWith(".xml") }
                .sortedWith { left, right -> CanonicalText.compare(left.toString(), right.toString()) }
            val moduleCases = FullHosted.expectedCases(expected, module)
            val checked = try {
                readReports(
                    paths,
                    moduleCases,
                    target,
                    Py.int(process["started_ns"] ?: JsonPrimitive(0)),
                    Py.int(process["finished_ns"] ?: JsonPrimitive(0)),
                    safariVersion,
                )
            } catch (error: IllegalArgumentException) {
                if (target == "jsSafari" && diagnostic != null) {
                    try {
                        diagnostic["source_xml_diagnostic"] =
                            retainFailedSafariSourceXml(repository, destination, process, error)
                    } catch (retention: Exception) {
                        diagnostic["source_xml_diagnostic"] = buildJsonObject {
                            put("status", JsonPrimitive("UNAVAILABLE"))
                            put("reason", JsonPrimitive(retention.message ?: retention.toString()))
                            put("validation_error", JsonPrimitive(error.message ?: error.toString()))
                        }
                    }
                }
                throw error
            }
            for ((index, path) in paths.withIndex()) {
                val relative = "xml/$module/${path.fileName}"
                val to = fullHostedResolve(destination, relative)
                to.parent?.let { Files.createDirectories(it) }
                Files.copy(path, to, StandardCopyOption.COPY_ATTRIBUTES, StandardCopyOption.REPLACE_EXISTING)
                checked.reports[index] = JsonObject(
                    checked.reports[index] + ("path" to JsonPrimitive(relative)),
                )
            }
            reports.add(checked.toJson(module))
        }
        return reports
    }

    /** `save` one lane list entry: the reference stores the report list as `{"module": ..., ...}`. */
    private fun fullHostedResolve(base: Path, relative: String): Path =
        relative.split('/').fold(base) { current, part -> current.resolve(part) }

    /** `capture_consumer`: the staged consumer probe reports and their archive members. */
    fun captureConsumer(
        repository: Path,
        target: String,
        destination: Path,
        process: JsonObject,
    ): HostedReportCheck {
        val manifest = StrictJson.load(
            Files.readString(repository.resolve("tools/qualification/foundation-probes.json")),
        ) as? JsonObject ?: throw IllegalArgumentException("foundation probe manifest is not an object")
        val group = (manifest["groups"] as? JsonArray ?: JsonArray(emptyList()))
            .mapNotNull { it as? JsonObject }
            .firstOrNull { Py.str(it["id"]) == "consumer-$target" }
            ?: throw IllegalArgumentException("frozen hosted probe group is missing: consumer-$target")
        val paths = glob(repository, Py.str(group["report_pattern"])!!)
        val expected = ProbeManifest.expectedCases(manifest, group)
            .map { it.classname to it.name }
            .toSet()
        if (paths.isEmpty()) throw IllegalArgumentException("staged consumer XML is missing")
        val checked = readConsumerReports(paths, expected, process)
        for (index in checked.reports.indices) {
            val path = paths[index]
            val relative = "xml/consumer/${path.fileName}"
            val to = destination.resolve(relative)
            to.parent?.let { Files.createDirectories(it) }
            Files.copy(path, to, StandardCopyOption.COPY_ATTRIBUTES, StandardCopyOption.REPLACE_EXISTING)
            checked.reports[index] = JsonObject(checked.reports[index] + ("path" to JsonPrimitive(relative)))
        }
        return checked
    }

    /** `read_consumer_reports`: the staged consumer probe reports, verified against the manifest. */
    fun readConsumerReports(
        paths: List<Path>,
        expected: Set<Pair<String, String>>,
        process: JsonObject,
    ): HostedReportCheck {
        if (paths.isEmpty()) throw IllegalArgumentException("staged consumer XML is missing")
        val seen = LinkedHashMap<Pair<String, String>, Int>()
        val result = mutableListOf<JsonObject>()
        val started = Py.int(process["started_ns"] ?: JsonPrimitive(0))
        val finished = Py.int(process["finished_ns"] ?: JsonPrimitive(0))
        for (path in paths) {
            val modified = mtimeNs(path)
            if (modified < started || modified > finished) {
                throw IllegalArgumentException("staged consumer XML is stale")
            }
            val suite = try {
                parseXml(Files.readAllBytes(path), path.toString())
            } catch (error: HostedXmlError) {
                throw IllegalArgumentException("staged consumer XML suite is invalid")
            }
            if (suite.tagName != "testsuite") {
                throw IllegalArgumentException("staged consumer XML suite is invalid")
            }
            val duration = FullHostedRules.pythonFloat(suite.getAttribute("time").ifEmpty { "nan" })
            if (duration == null || !duration.isFinite()) {
                throw IllegalArgumentException("staged consumer XML suite is invalid")
            }
            val cases = successors(suite, "testcase")
            val counts = linkedMapOf(
                "tests" to cases.size.toLong(),
                "failures" to cases.count { firstChild(it, "failure") != null }.toLong(),
                "errors" to cases.count { firstChild(it, "error") != null }.toLong(),
                "skipped" to cases.count { firstChild(it, "skipped") != null }.toLong(),
            )
            for ((key, actual) in counts) {
                val attribute = suite.getAttribute(key)
                if (attribute.isEmpty() || attribute.toLongOrNull() != actual ||
                    (key != "tests" && actual != 0L)
                ) {
                    throw IllegalArgumentException("staged consumer XML is partial or failed")
                }
            }
            for (case in cases) {
                val caseDuration = FullHostedRules.pythonFloat(
                    case.getAttribute("time").ifEmpty { "nan" },
                )
                if (case.getAttribute("classname").isEmpty() ||
                    case.getAttribute("name").isEmpty() ||
                    caseDuration == null || !caseDuration.isFinite() ||
                    firstChild(case, "ignored") != null
                ) {
                    throw IllegalArgumentException("staged consumer case is invalid or ignored")
                }
                val identity = case.getAttribute("classname") to case.getAttribute("name")
                seen[identity] = (seen[identity] ?: 0) + 1
            }
            result.add(
                buildJsonObject {
                    put("path", JsonPrimitive(path.toString()))
                    put("sha256", JsonPrimitive(FullHosted.sha256(path)))
                    put("modified_ns", JsonPrimitive(modified))
                },
            )
        }
        if (seen.keys != expected || seen.values.any { it != 1 }) {
            throw IllegalArgumentException(
                "staged consumer cases are missing, extra, or duplicate",
            )
        }
        return HostedReportCheck(
            expected = expected.size,
            executed = seen.values.sum(),
            caseIds = seen.keys.sortedWith(identityOrder).map { "${it.first}#${it.second}" },
            reports = result,
        )
    }

    /** `capture_dokka_output`: archive the generated Dokka tree and record its provenance. */
    fun captureDokkaOutput(repository: Path, output: Path, receipt: MutableMap<String, JsonElement>) {
        val modules = linkedMapOf<String, JsonElement>()
        for (module in Qualification.modules) {
            val generated = repository.resolve(module).resolve("build/dokka/html")
            if (!Files.isDirectory(generated) || Files.isSymbolicLink(generated)) {
                throw IllegalArgumentException(
                    "$module: generated Dokka output is missing or unsafe",
                )
            }
            val entries = linkedMapOf<String, JsonElement>()
            val paths = Files.walk(generated).use { walk -> walk.toList() }
                .sortedWith { left, right -> CanonicalText.compare(left.toString(), right.toString()) }
            for (source in paths) {
                if (Files.isSymbolicLink(source)) {
                    throw IllegalArgumentException(
                        "$module: generated Dokka output has a symbolic link",
                    )
                }
                if (!Files.isRegularFile(source)) continue
                val relative = relativeToPosix(source, generated)
                FullHosted.relativePath(relative)
                val copied = FullHosted.archiveCopy(source, output, "dokka/$module/$relative")
                entries[relative] = copied.getValue("sha256")
            }
            if (entries.isEmpty()) {
                throw IllegalArgumentException("$module: generated Dokka output is empty")
            }
            val jar = FullHosted.archivedFile(
                output,
                "staged/${Qualification.GROUP.replace(".", "/")}/$module/" +
                    "${Qualification.VERSION}/$module-${Qualification.VERSION}-javadoc.jar",
            )
            ArchiveContract.validateGeneratedDocs(
                jar,
                output.resolve("dokka").resolve(module),
                FullHosted.committedInput(
                    repository,
                    Py.str(receipt["candidate_sha"])!!,
                    "LICENSE.md",
                ),
            )
            modules[module] = JsonObject(entries)
        }
        receipt["dokka_provenance"] = buildJsonObject {
            put("schema", JsonPrimitive(1))
            put("candidate_sha", receipt.getValue("candidate_sha"))
            put("source_tree_sha256", receipt.getValue("source_tree_sha256"))
            put(
                "stage_stdout_sha256",
                (receipt["stage"] as JsonObject).getValue("stdout_sha256"),
            )
            put("modules", JsonObject(modules))
        }
    }

    /**
     * `verify_raw_files`: the receipt of a completed hosted full-corpus run, verified member by
     * member against the candidate checkout and the archive.
     *
     * Every check either returns the receipt unchanged or throws with the reference message; a
     * partial verification is never reported as a pass.
     */
    fun verifyRawFiles(
        output: Path,
        receipt: JsonObject,
        manifestInput: JsonObject? = null,
        consumerManifestInput: JsonObject? = null,
        candidateRepository: Path? = null,
    ): JsonObject {
        val repository = candidateRepository ?: candidateCheckout()
        val target = Py.str(receipt["target"])
        if (target == null || target !in Hosted.TARGETS ||
            Py.str(receipt["status"]) != "FULL_COMMON_PASSED" ||
            !Py.equalsInt(receipt["schema"], 2L) ||
            Py.str(receipt["kind"]) != "hosted-full-common-corpus" ||
            !Py.SHA40.matches(Py.str(receipt["candidate_sha"]) ?: "")
        ) {
            throw IllegalArgumentException("full hosted receipt is not a completed target")
        }
        val lanes = receipt["configurations"] as? JsonArray
        if (lanes == null || lanes.any { it !is JsonObject } ||
            lanes.map { Py.str((it as JsonObject)["configuration"]) } !=
            FullHosted.CONFIGS.getValue(target!!)
        ) {
            throw IllegalArgumentException(
                "both required configurations are absent, duplicated, or unordered",
            )
        }
        if (target == "jsSafari") {
            if ("source_xml_diagnostic" in receipt ||
                lanes.any { "source_xml_diagnostic" in (it as JsonObject) }
            ) {
                throw IllegalArgumentException(
                    "passed Safari receipt contains failed source XML diagnostic metadata",
                )
            }
            val files = receipt["files"] as? JsonArray
            if (files != null && files.any { element ->
                    val path = Py.str((element as? JsonObject)?.get("path"))
                    if (path == null) {
                        false
                    } else {
                        posixParts(path).take(2) in setOf(
                            listOf("development", "diagnostic"),
                            listOf("production", "diagnostic"),
                            listOf("diagnostic", "source-xml"),
                        )
                    }
                }
            ) {
                throw IllegalArgumentException(
                    "passed Safari receipt contains failed source XML diagnostic member",
                )
            }
        }
        val gradleUserHome = Py.str(receipt["gradle_user_home"])
        if (gradleUserHome.isNullOrEmpty()) {
            throw IllegalArgumentException("Gradle user home receipt is absent")
        }
        if (FullHosted.originalPath(target, gradleUserHome) !=
            FullHosted.expectedGradleHome(target, receipt)
        ) {
            throw IllegalArgumentException("Gradle user home differs from runner environment")
        }
        val candidateSha = Py.str(receipt["candidate_sha"])!!
        var manifest = manifestInput
        var consumerManifest = consumerManifestInput
        if (target == "jsSafari") {
            val canonicalManifest = canonicalSafariJson(repository, candidateSha, output, FullHosted.MANIFEST)
            val canonicalConsumer = canonicalSafariJson(
                repository,
                candidateSha,
                output,
                "tools/qualification/foundation-probes.json",
            )
            if (manifest == null) manifest = loadCorpus(repository, candidateSha)
            if (consumerManifest == null) consumerManifest = canonicalConsumer
            val supplied = listOf(
                Triple(manifest, canonicalManifest, "source"),
                Triple(consumerManifest, canonicalConsumer, "consumer"),
            )
            for ((given, canonical, label) in supplied) {
                val matching = given == canonical &&
                    FullHosted.canonicalHash(given) == FullHosted.canonicalHash(canonical)
                if (!matching) {
                    throw IllegalArgumentException(
                        "parsed $label manifest differs from Safari candidate source",
                    )
                }
            }
            manifest = canonicalManifest
            consumerManifest = canonicalConsumer
        } else {
            if (manifest == null) manifest = loadCorpus(repository, candidateSha)
            if (consumerManifest == null) {
                consumerManifest = StrictJson.load(
                    Files.readString(repository.resolve("tools/qualification/foundation-probes.json")),
                ) as? JsonObject
                    ?: throw IllegalArgumentException("foundation probe manifest is not an object")
            }
        }
        val corpus = manifest!!
        val consumer = consumerManifest!!
        if (Py.str(receipt["manifest_sha256"]) != FullHosted.canonicalHash(corpus) ||
            receipt["source_tree_sha256"] != corpus["source_tree_sha256"] ||
            Py.str(receipt["map_sha256"]) != FullHosted.sha256(repository.resolve(FullHosted.MAPPING)) ||
            Py.str(receipt["reviewed_pairs_sha256"]) !=
            FullHosted.sha256(repository.resolve(FullHosted.PAIRS))
        ) {
            throw IllegalArgumentException("source or manifest hash differs")
        }
        for (module in Qualification.modules) FullHosted.expectedCases(corpus, module)
        val observedRuntime = receipt["runtime"] as? JsonObject
        if (Hosted.runtimeStatus(target, observedRuntime).status != "READY") {
            throw IllegalArgumentException("runner or runtime identity differs")
        }
        FullHosted.requirePinnedToolchain(observedRuntime)
        val runtime = observedRuntime!!
        val simulatorFamily = Hosted.NATIVE_TARGETS[target]?.simulator
        if (simulatorFamily != null) {
            val selected = receipt["selected_simulator"]
            val simulatorList = ((runtime["simulators"] as? JsonObject)?.get(simulatorFamily) as? JsonArray)
                ?.toList() ?: emptyList()
            if (selected !is JsonObject ||
                simulatorList.none { it == selected } ||
                !Regex("[0-9A-Fa-f-]{36}").matches(Py.str(selected["udid"]) ?: "")
            ) {
                throw IllegalArgumentException(
                    "selected simulator is not bound to runtime observation",
                )
            }
        }
        for (key in listOf(
            "github_run_id", "github_job", "runner_name", "runner_os", "runner_arch",
            "archive_root",
        )) {
            if (!Py.truthy(receipt[key])) {
                throw IllegalArgumentException("GitHub runner identity is absent")
            }
        }
        val originalRoot = FullHosted.originalPath(target, Py.str(receipt["archive_root"]))
        val stagingRoot = FullHosted.originalPath(target, Py.str(receipt["staging_repository"]))
        val repositoryRoot = FullHosted.originalPath(target, Py.str(receipt["repository_root"]))
        val wrapper = joinOriginal(
            target,
            repositoryRoot,
            if (target == "mingwX64") "gradlew.bat" else "gradlew",
        )
        val consumerRoot = joinOriginal(target, repositoryRoot, "consumers/qualification/portable")
        if (stagingRoot != joinOriginal(target, repositoryRoot, "build/staging-repository")) {
            throw IllegalArgumentException("staging repository path differs from checkout")
        }
        val system = Py.str(runtime["system"]) ?: ""
        val expectedOs = if (system == "Windows") "Windows" else "macOS"
        val expectedArch = if ((Py.str(runtime["machine"]) ?: "").lowercase() == "arm64") "ARM64" else "X64"
        if (Py.str(receipt["runner_os"]) != expectedOs ||
            Py.str(receipt["runner_arch"]) != expectedArch
        ) {
            throw IllegalArgumentException("GitHub runner OS or architecture differs")
        }
        FullHosted.verifyInventory(output, receipt["files"] as? JsonArray)
        verifyStaging(output, receipt)
        verifyStagedContent(output, receipt, candidateRepository ?: candidateCheckout())
        val stage = receipt["stage"] as? JsonObject
            ?: throw IllegalArgumentException("staging process is absent")
        verifyProcess(
            output,
            output.resolve("stage"),
            stage,
            null,
            ":dyn4k-core:publishKotlinMultiplatformPublicationToStagingRepository",
        )
        val stageCommand = (stage["command"] as? JsonArray)?.map { Py.str(it) }
        if (stageCommand == null || stageCommand.isEmpty() || stageCommand[0] == null ||
            FullHosted.originalPath(target, stageCommand[0]) != wrapper ||
            "--rerun-tasks" !in stageCommand
        ) {
            throw IllegalArgumentException("staging wrapper differs from checkout")
        }
        if (target == "jsSafari") {
            FullHostedRules.verifySafariModeArguments(stageCommand, "stage")
        }
        val stageStarted = Py.int(stage["started_ns"] ?: JsonPrimitive(0))
        val stageFinished = Py.int(stage["finished_ns"] ?: JsonPrimitive(0))
        for (element in receipt["files"] as JsonArray) {
            val item = element as JsonObject
            val path = Py.str(item["path"]) ?: continue
            if (path.startsWith("staged/") &&
                !(stageStarted <= Py.int(item["modified_ns"] ?: JsonPrimitive(0)) &&
                    Py.int(item["modified_ns"] ?: JsonPrimitive(0)) <= stageFinished)
            ) {
                throw IllegalArgumentException("staged publication predates staging invocation")
            }
        }
        val artifactTarget = if (target == "jsSafari") "js" else target
        for (module in Qualification.modules) {
            for (task in listOf(
                ":$module:publishKotlinMultiplatformPublicationToStagingRepository",
                ":$module:publish${artifactTarget.replaceFirstChar { it.uppercase() }}PublicationToStagingRepository",
            )) {
                if (task !in stageCommand) {
                    throw IllegalArgumentException("staging command lacks root or target publication")
                }
            }
        }
        for (path in FullHosted.INPUTS) {
            val archived = FullHosted.archivedFile(output, "inputs/$path")
            val expected = if (target == "jsSafari") {
                io.github.rubixhacker.harness.contract.Sha256.of(
                    FullHosted.committedInput(repository, candidateSha, path),
                )
            } else {
                FullHosted.sha256(repository.resolve(path))
            }
            if (FullHosted.sha256(archived) != expected) {
                throw IllegalArgumentException("archived source input differs")
            }
        }
        val expectedInputs = FullHosted.INPUTS.map { "inputs/$it" }.toSet()
        val archivedInputs = (receipt["files"] as JsonArray)
            .mapNotNull { (it as? JsonObject)?.let { item -> Py.str(item["path"]) } }
            .filter { it.startsWith("inputs/") }
            .toSet()
        if (archivedInputs != expectedInputs) {
            throw IllegalArgumentException("archived source input inventory differs")
        }
        val sourceFiles = (corpus["source_files"] as JsonArray).map { it as JsonObject }
        for (source in sourceFiles) {
            val name = Py.str(source["path"])!!
            val path = FullHosted.archivedFile(output, "sources/$name")
            if (FullHosted.sha256(path) != Py.str(source["sha256"])) {
                throw IllegalArgumentException("archived source file differs from reviewed corpus")
            }
        }
        val expectedSourcePaths = sourceFiles.map { "sources/${Py.str(it["path"])}" }.toSet()
        val archivedSources = (receipt["files"] as JsonArray)
            .mapNotNull { (it as? JsonObject)?.let { item -> Py.str(item["path"]) } }
            .filter { it.startsWith("sources/") }
            .toSet()
        if (archivedSources != expectedSourcePaths) {
            throw IllegalArgumentException("archived source inventory differs")
        }
        val group = (consumer["groups"] as JsonArray)
            .mapNotNull { it as? JsonObject }
            .firstOrNull { Py.str(it["id"]) == "consumer-$target" }
            ?: throw IllegalArgumentException("frozen hosted probe group is missing: consumer-$target")
        val expectedConsumer = ProbeManifest.expectedCases(consumer, group)
            .map { it.classname to it.name }
            .toSet()
        val seenInvocations = mutableSetOf<String>()
        val expectedXml = mutableSetOf<String>()
        val expectedExecutables = mutableSetOf<String>()
        val expectedKarmaInputs = mutableSetOf<String>()
        val expectedResolved = mutableSetOf<String>()
        val safariVersion = Py.str(runtime["safari_version"])
        for (laneElement in lanes) {
            val lane = laneElement as JsonObject
            if (Py.str(lane["status"]) != "FULL_COMMON_PASSED") {
                throw IllegalArgumentException("configuration is incomplete")
            }
            val config = Py.str(lane["configuration"])!!
            val invocation = Py.str(lane["invocation_id"])
            if (invocation == null || !Py.INVOCATION.matches(invocation) ||
                invocation in seenInvocations
            ) {
                throw IllegalArgumentException("configuration invocation is absent or duplicate")
            }
            seenInvocations.add(invocation)
            if (simulatorFamily != null &&
                Py.str(lane["simulator_udid"]) !=
                Py.str((receipt["selected_simulator"] as JsonObject)["udid"])
            ) {
                throw IllegalArgumentException(
                    "configuration simulator differs from runtime observation",
                )
            }
            val folder = output.resolve(config)
            val graphScriptPath = FullHosted.archivedFile(
                output,
                "$config/qualification-graph.init.gradle",
            )
            if (Files.readString(graphScriptPath) != FullHostedRules.graphScript(target)) {
                throw IllegalArgumentException("consumer graph task script differs")
            }
            val sourceScriptPath = FullHosted.archivedFile(
                output,
                "$config/qualification.init.gradle",
            )
            val simulator = Py.str(((receipt["selected_simulator"] as? JsonObject))?.get("udid"))
            if (Files.readString(sourceScriptPath) !=
                FullHostedRules.initScript(target, config, simulator)
            ) {
                throw IllegalArgumentException("source test task script differs")
            }
            val sourceTask = FullHosted.SOURCE_TASK.getValue(target)
            for ((processName, task) in listOf(
                "source" to ":dyn4k-core:$sourceTask",
                "consumer" to sourceTask,
                "graph" to "qualificationResolvedGraph",
            )) {
                val process = lane["${processName}_process"] as? JsonObject
                verifyProcess(output, folder.resolve(processName), process, invocation, task)
                val command = (process!!["command"] as JsonArray).map { Py.str(it) }
                if (command.isEmpty() || command[0] == null ||
                    FullHosted.originalPath(target, command[0]) != wrapper
                ) {
                    throw IllegalArgumentException("process wrapper differs from checkout")
                }
                if ("-PqualificationInvocationId=$invocation" !in command) {
                    throw IllegalArgumentException("process command lacks bound invocation")
                }
                if (processName in setOf("consumer", "graph") &&
                    "-PqualificationRepository=${Py.str(receipt["staging_repository"])}" !in command
                ) {
                    throw IllegalArgumentException(
                        "external consumer repository provenance is absent",
                    )
                }
                if (processName in setOf("consumer", "graph") &&
                    ("-p" !in command || consumerRoot !in command)
                ) {
                    throw IllegalArgumentException("external consumer project invocation is absent")
                }
                if (processName in setOf("source", "consumer") && "--rerun-tasks" !in command) {
                    throw IllegalArgumentException("test process did not force execution")
                }
                if (processName in setOf("source", "graph") ||
                    (target == "jsSafari" && processName == "consumer")
                ) {
                    val script = when {
                        processName == "source" -> sourceScriptPath
                        processName == "consumer" -> sourceScriptPath
                        else -> graphScriptPath
                    }
                    val original = joinOriginal(
                        target,
                        originalRoot,
                        relativeToPosix(script, output),
                    )
                    if ("--init-script" !in command || original !in command) {
                        throw IllegalArgumentException("test or graph init script is unbound")
                    }
                }
                if (processName == "source" && ":dyn4k:$sourceTask" !in command) {
                    throw IllegalArgumentException("facade source test task is absent")
                }
                if (target == "jsSafari") {
                    FullHostedRules.verifySafariModeArguments(command, processName, config)
                }
            }
            val sourceProcess = lane["source_process"] as JsonObject
            val consumerProcess = lane["consumer_process"] as JsonObject
            val graphProcess = lane["graph_process"] as JsonObject
            if (target == "jsSafari") {
                verifySafariReporterArchive(output, receipt, lane, repository, Path.of(repositoryRoot))
            }
            if (!(stageFinished <= Py.int(sourceProcess["started_ns"] ?: JsonPrimitive(0)) &&
                    Py.int(sourceProcess["started_ns"] ?: JsonPrimitive(0)) <=
                    Py.int(sourceProcess["finished_ns"] ?: JsonPrimitive(0)) &&
                    Py.int(sourceProcess["finished_ns"] ?: JsonPrimitive(0)) <=
                    Py.int(consumerProcess["started_ns"] ?: JsonPrimitive(0)) &&
                    Py.int(consumerProcess["started_ns"] ?: JsonPrimitive(0)) <=
                    Py.int(consumerProcess["finished_ns"] ?: JsonPrimitive(0)) &&
                    Py.int(consumerProcess["finished_ns"] ?: JsonPrimitive(0)) <=
                    Py.int(graphProcess["started_ns"] ?: JsonPrimitive(0)))
            ) {
                throw IllegalArgumentException(
                    "archived process order differs from staged test invocation",
                )
            }
            requireTestTasks(sourceProcess, folder.resolve("source"), target, config, Qualification.modules)
            requireTestTasks(consumerProcess, folder.resolve("consumer"), target, config, listOf(""))
            val sourceGroups = lane["source"] as? JsonArray
            if (sourceGroups == null ||
                sourceGroups.mapNotNull { (it as? JsonObject)?.let { item -> Py.str(item["module"]) } } !=
                Qualification.modules ||
                sourceGroups.any { it !is JsonObject }
            ) {
                throw IllegalArgumentException("both core and facade source groups are required")
            }
            for (groupElement in sourceGroups) {
                val item = groupElement as JsonObject
                val module = Py.str(item["module"])!!
                val paths = reportPaths(output, config, item)
                val checked = readReports(
                    paths,
                    FullHosted.expectedCases(corpus, module),
                    target,
                    Py.int(sourceProcess["started_ns"] ?: JsonPrimitive(0)),
                    Py.int(sourceProcess["finished_ns"] ?: JsonPrimitive(0)),
                    safariVersion,
                )
                for (index in checked.reports.indices) {
                    val relative = relativeToPosix(
                        Path.of(Py.str(checked.reports[index]["path"])!!),
                        folder,
                    )
                    checked.reports[index] = JsonObject(
                        checked.reports[index] + ("path" to JsonPrimitive(relative)),
                    )
                    expectedXml.add("$config/$relative")
                }
                FullHostedRules.verifyReportGroup(item, checked, listOf("xml", module))
            }
            val consumerGroup = lane["consumer"] as? JsonObject
                ?: throw IllegalArgumentException("staged consumer case group is absent")
            val consumerPaths = reportPaths(output, config, consumerGroup)
            val consumerChecked = readConsumerReports(consumerPaths, expectedConsumer, consumerProcess)
            for (index in consumerChecked.reports.indices) {
                val relative = relativeToPosix(
                    Path.of(Py.str(consumerChecked.reports[index]["path"])!!),
                    folder,
                )
                consumerChecked.reports[index] = JsonObject(
                    consumerChecked.reports[index] + ("path" to JsonPrimitive(relative)),
                )
                expectedXml.add("$config/$relative")
            }
            FullHostedRules.verifyReportGroup(consumerGroup, consumerChecked, listOf("xml", "consumer"))
            val sourceExecutables = lane["source_executables"] as? JsonObject
            if (sourceExecutables == null || sourceExecutables.keys != Qualification.modules.toSet()) {
                throw IllegalArgumentException("source test executable inventory differs")
            }
            val consumerExecutable = lane["consumer_executable"] as? JsonObject
                ?: throw IllegalArgumentException("consumer test executable inventory differs")
            val products = sourceExecutables.map { (name, value) -> name to value as JsonObject } +
                listOf("consumer" to consumerExecutable)
            for ((name, product) in products) {
                val archivePath = Py.str(product["archive_path"])!!
                val path = FullHosted.archivedFile(output, archivePath)
                expectedExecutables.add(archivePath)
                if (relativeToPosix(path.parent, output) != "$config/executables/$name") {
                    throw IllegalArgumentException("test executable archive path differs")
                }
                val project = if (name == "consumer") {
                    consumerRoot
                } else {
                    joinOriginal(target, repositoryRoot, name)
                }
                var expectedProduct: String? = null
                var selectedInput: String? = null
                val expectedParent: String
                if (target in FullHosted.NATIVE) {
                    val mode = if (config == "optimized-opt") "releaseTest" else "debugTest"
                    expectedParent = joinOriginal(
                        target,
                        joinOriginal(target, project, "build/bin/$target"),
                        mode,
                    )
                } else {
                    val selection = FullHostedRules.safariProductPaths(project, config, name)
                    expectedProduct = selection.expected
                    selectedInput = selection.karmaInput
                    expectedParent = FullHostedRules.posixParent(selection.expected)
                }
                val executable = FullHosted.originalPath(target, Py.str(product["path"]))
                if (FullHostedRules.posixParent(executable) != expectedParent ||
                    pathName(executable, target) != path.fileName.toString()
                ) {
                    throw IllegalArgumentException(
                        "test executable target or configuration path differs",
                    )
                }
                if (target == "jsSafari" && executable != expectedProduct) {
                    throw IllegalArgumentException(
                        "Safari compiler executable differs from configured product",
                    )
                }
                if (FullHosted.sha256(path) != Py.str(product["sha256"]) ||
                    Files.size(path) != Py.int(product["size"] ?: JsonPrimitive(0)) ||
                    mtimeNs(path) != Py.int(product["modified_ns"] ?: JsonPrimitive(0)) ||
                    Py.int(product["size"] ?: JsonPrimitive(0)) <= 0
                ) {
                    throw IllegalArgumentException("archived test executable differs")
                }
                val process = if (name == "consumer") consumerProcess else sourceProcess
                val productModified = Py.int(product["modified_ns"] ?: JsonPrimitive(0))
                if (productModified < Py.int(process["started_ns"] ?: JsonPrimitive(0)) ||
                    productModified > Py.int(process["finished_ns"] ?: JsonPrimitive(0))
                ) {
                    throw IllegalArgumentException("test executable predates invocation")
                }
                if (target == "jsSafari") {
                    val selected = product["karma_input"] as? JsonObject
                    val configInput = Py.str(
                        ((lane["safari_karma_configs"] as JsonObject)[name] as JsonObject)["input_path"],
                    )
                    if (selected == null || configInput != selectedInput ||
                        Py.str(selected["path"]) != configInput ||
                        Py.str(selected["status"]) != "REGULAR" ||
                        Py.str(selected["hash_status"]) != "HASHED"
                    ) {
                        throw IllegalArgumentException(
                            "Safari Karma input differs from validated config",
                        )
                    }
                    val selectedPath = FullHosted.originalPath(target, Py.str(selected["path"]))
                    val inputArchive = "$config/karma-inputs/$name/${pathName(selectedPath, target)}"
                    if (Py.str(selected["archive_path"]) != inputArchive) {
                        throw IllegalArgumentException("Safari Karma input archive path differs")
                    }
                    val selectedBytes = FullHosted.archivedFile(output, inputArchive)
                    expectedKarmaInputs.add(inputArchive)
                    if (FullHosted.sha256(selectedBytes) != Py.str(selected["sha256"]) ||
                        Files.size(selectedBytes) != Py.int(selected["size"] ?: JsonPrimitive(0)) ||
                        mtimeNs(selectedBytes) != Py.int(selected["modified_ns"] ?: JsonPrimitive(0)) ||
                        Py.int(selected["size"] ?: JsonPrimitive(0)) !=
                        Py.int(product["size"] ?: JsonPrimitive(0)) ||
                        Py.str(selected["sha256"]) != Py.str(product["sha256"]) ||
                        !(Py.int(process["started_ns"] ?: JsonPrimitive(0)) <=
                            Py.int(selected["modified_ns"] ?: JsonPrimitive(0)) &&
                            Py.int(selected["modified_ns"] ?: JsonPrimitive(0)) <=
                            Py.int(process["finished_ns"] ?: JsonPrimitive(0)))
                    ) {
                        throw IllegalArgumentException(
                            "Safari Karma input bytes or freshness differ",
                        )
                    }
                }
            }
            val graph = parseGraph(
                folder.resolve("graph"),
                graphProcess,
                target,
                receipt["artifact_hashes"] as JsonObject,
                Py.str(receipt["staging_repository"])!!,
                expectedHome = Py.str(receipt["gradle_user_home"])!!,
                stagedRoot = output.resolve("staged"),
            )
            if (graph != lane["consumer_graph"]) {
                throw IllegalArgumentException(
                    "external consumer graph differs from archived observation",
                )
            }
            val archivedGraph = lane["resolved_artifacts"] as? JsonArray
            val graphArtifacts = (graph["artifacts"] as JsonArray).map { it as JsonObject }
            if (archivedGraph == null || archivedGraph.size != graphArtifacts.size) {
                throw IllegalArgumentException(
                    "resolved dependency artifact archive is incomplete",
                )
            }
            for ((index, pair) in graphArtifacts.zip(archivedGraph).withIndex()) {
                val (item, archivedElement) = pair
                val archived = archivedElement as? JsonObject
                    ?: throw IllegalArgumentException(
                        "resolved dependency artifact provenance differs",
                    )
                val expectedName =
                    "$config/resolved-artifacts/${index.toString().padStart(3, '0')}-${Py.str(item["name"])}"
                if (Py.str(archived["archive_path"]) != expectedName ||
                    listOf("component", "file", "name", "size", "sha256")
                        .any { archived[it] != item[it] }
                ) {
                    throw IllegalArgumentException(
                        "resolved dependency artifact provenance differs",
                    )
                }
                val resolved = FullHosted.archivedFile(output, expectedName)
                if (FullHosted.sha256(resolved) != Py.str(item["sha256"]) ||
                    Files.size(resolved) != Py.int(item["size"] ?: JsonPrimitive(0))
                ) {
                    throw IllegalArgumentException("resolved dependency artifact bytes differ")
                }
                expectedResolved.add(expectedName)
            }
        }
        val archivedXml = (receipt["files"] as JsonArray)
            .mapNotNull { (it as? JsonObject)?.let { item -> Py.str(item["path"]) } }
            .filter { "/xml/" in it }
            .toSet()
        val archivedExecutables = (receipt["files"] as JsonArray)
            .mapNotNull { (it as? JsonObject)?.let { item -> Py.str(item["path"]) } }
            .filter { "/executables/" in it }
            .toSet()
        val archivedKarmaInputs = (receipt["files"] as JsonArray)
            .mapNotNull { (it as? JsonObject)?.let { item -> Py.str(item["path"]) } }
            .filter { "/karma-inputs/" in it }
            .toSet()
        val archivedResolved = (receipt["files"] as JsonArray)
            .mapNotNull { (it as? JsonObject)?.let { item -> Py.str(item["path"]) } }
            .filter { "/resolved-artifacts/" in it }
            .toSet()
        if (archivedXml != expectedXml || archivedExecutables != expectedExecutables ||
            archivedKarmaInputs != expectedKarmaInputs || archivedResolved != expectedResolved
        ) {
            throw IllegalArgumentException(
                "extra or missing XML, executable, Karma input, or resolved artifact archive member",
            )
        }
        return receipt
    }

    private fun reportPaths(output: Path, config: String, group: JsonObject): List<Path> =
        (group["reports"] as JsonArray).map { element ->
            val path = Py.str((element as JsonObject)["path"])!!
            FullHosted.archivedFile(output, "$config/$path")
        }

    private fun posixParts(path: String): List<String> = path.split('/').filter { it.isNotEmpty() }

    // ------------------------------------------------------------------------------------
    // Shared helpers
    // ------------------------------------------------------------------------------------

    private val identityOrder = Comparator<Pair<String, String>> { left, right ->
        var comparison = CanonicalText.compare(left.first, right.first)
        if (comparison == 0) comparison = CanonicalText.compare(left.second, right.second)
        comparison
    }

    private fun tupleRepr(values: List<Pair<String, String>>): String =
        values.joinToString(", ", prefix = "[", postfix = "]") { pair ->
            "(" + Py.quote(pair.first) + ", " + Py.quote(pair.second) + ")"
        }

    private fun sourcesJson(sources: Map<String, Map<String, String>>): JsonObject =
        JsonObject(
            sources.mapValues { (_, entries) ->
                JsonObject(entries.mapValues { JsonPrimitive(it.value) })
            },
        )

    private fun parseXml(bytes: ByteArray, label: String, namespaceAware: Boolean = false): Element {
        val factory = DocumentBuilderFactory.newInstance()
        factory.isNamespaceAware = namespaceAware
        factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true)
        val builder = try {
            factory.newDocumentBuilder()
        } catch (error: Exception) {
            throw HostedXmlError("XML parser is unavailable: $label", error)
        }
        builder.setErrorHandler(object : org.xml.sax.ErrorHandler {
            override fun warning(exception: org.xml.sax.SAXParseException) = Unit
            override fun error(exception: org.xml.sax.SAXParseException) = throw exception
            override fun fatalError(exception: org.xml.sax.SAXParseException) = throw exception
        })
        return try {
            builder.parse(bytes.inputStream()).documentElement
        } catch (error: org.xml.sax.SAXException) {
            throw HostedXmlError("invalid XML suite: $label", error)
        } catch (error: IOException) {
            throw HostedXmlError("invalid XML suite: $label", error)
        }
    }

    private fun successors(root: Element, tag: String): List<Element> {
        val result = mutableListOf<Element>()
        val children = root.childNodes
        for (index in 0 until children.length) {
            val node = children.item(index)
            if (node is Element && node.tagName == tag) result.add(node)
        }
        return result
    }

    private fun descendants(root: Element, tag: String): List<Element> {
        val nodes = root.getElementsByTagName(tag)
        val result = mutableListOf<Element>()
        for (index in 0 until nodes.length) {
            (nodes.item(index) as? Element)?.let { result.add(it) }
        }
        return result
    }

    private fun firstChild(root: Element, tag: String): Element? = successors(root, tag).firstOrNull()

    private fun findText(root: Element, namespace: String, name: String): String? =
        successors(root, name).firstOrNull()?.textContent

    private fun findPath(root: Element, namespace: String, path: List<String>): List<Element> {
        var current = listOf(root)
        for (name in path) {
            val next = mutableListOf<Element>()
            for (element in current) next.addAll(successors(element, name))
            current = next
        }
        return current
    }

    private fun mtimeNs(path: Path): Long =
        Files.getLastModifiedTime(path).to(TimeUnit.NANOSECONDS)

    private fun unixNumber(path: Path, attribute: String): Long {
        val value = try {
            Files.getAttribute(path, attribute, LinkOption.NOFOLLOW_LINKS)
        } catch (error: Exception) {
            return 0L
        }
        return when (value) {
            is Long -> value
            is Int -> value.toLong()
            else -> 0L
        }
    }

    private fun identityTuple(attributes: BasicFileAttributes): List<Any?> {
        val changed = try {
            attributes.fileKey()
        } catch (error: Exception) {
            null
        }
        return listOf(
            attributes.fileKey(),
            attributes.size(),
            attributes.lastModifiedTime().to(TimeUnit.NANOSECONDS),
            changed,
        )
    }

    private fun kindOf(attributes: BasicFileAttributes): String = when {
        attributes.isSymbolicLink -> "symlink"
        attributes.isRegularFile -> "file"
        attributes.isDirectory -> "directory"
        else -> "other"
    }

    private fun modeOf(path: Path, attributes: BasicFileAttributes): Int {
        if (attributes.isSymbolicLink) return 0x1FF
        return try {
            var mode = 0
            for (permission in Files.getPosixFilePermissions(path, LinkOption.NOFOLLOW_LINKS)) {
                mode = mode or when (permission) {
                    PosixFilePermission.OWNER_READ -> 0x100
                    PosixFilePermission.OWNER_WRITE -> 0x80
                    PosixFilePermission.OWNER_EXECUTE -> 0x40
                    PosixFilePermission.GROUP_READ -> 0x20
                    PosixFilePermission.GROUP_WRITE -> 0x10
                    PosixFilePermission.GROUP_EXECUTE -> 0x8
                    PosixFilePermission.OTHERS_READ -> 0x4
                    PosixFilePermission.OTHERS_WRITE -> 0x2
                    PosixFilePermission.OTHERS_EXECUTE -> 0x1
                }
            }
            mode
        } catch (error: Exception) {
            0
        }
    }

    private fun listDirectory(directory: Path): List<Path> {
        if (!Files.isDirectory(directory)) return emptyList()
        return try {
            Files.newDirectoryStream(directory).use { stream -> stream.toList() }
        } catch (error: IOException) {
            emptyList()
        }
    }

    private fun relativeParts(path: Path, anchor: Path): List<String>? {
        val normalizedPath = path.toAbsolutePath().normalize()
        val normalizedAnchor = anchor.toAbsolutePath().normalize()
        if (!normalizedPath.startsWith(normalizedAnchor)) return null
        return normalizedAnchor.relativize(normalizedPath).toString()
            .split('/').filter { it.isNotEmpty() && it != "." }
    }

    private fun relativeToPosix(path: Path, base: Path): String {
        val normalizedPath = path.toAbsolutePath().normalize()
        val normalizedBase = base.toAbsolutePath().normalize()
        if (!normalizedPath.startsWith(normalizedBase)) {
            throw IllegalArgumentException(
                "$path is not in the subpath of $base OR one path is relative and the other is absolute.",
            )
        }
        return normalizedBase.relativize(normalizedPath).toString().replace('\\', '/')
    }

    private fun pathName(path: String, target: String): String {
        val separators = if (target == "mingwX64") listOf('/', '\\') else listOf('/')
        var index = -1
        for (separator in separators) {
            val found = path.lastIndexOf(separator)
            if (found > index) index = found
        }
        return if (index < 0) path else path.substring(index + 1)
    }

    private fun pathSegments(target: String, path: String): List<String> {
        val parts = if (target == "mingwX64") path.split('/', '\\') else path.split('/')
        return parts.filter { it.isNotEmpty() }
    }

    private fun joinOriginal(target: String, base: String, relative: String): String {
        val separator = if (target == "mingwX64") "\\" else "/"
        val normalized = relative.replace('/', if (target == "mingwX64") '\\' else '/')
        return if (base.endsWith("/") || base.endsWith("\\")) {
            base.trimEnd('/', '\\') + separator + normalized.trimStart(separator[0])
        } else {
            base + separator + normalized
        }
    }

    private fun sha1(bytes: ByteArray): String =
        MessageDigest.getInstance("SHA-1").digest(bytes)
            .joinToString("") { "%02x".format(it) }

    private fun glob(repository: Path, pattern: String): List<Path> {
        val segments = pattern.split('/').filter { it.isNotEmpty() }
        var current = listOf(repository)
        for ((index, segment) in segments.withIndex()) {
            val last = index == segments.size - 1
            val next = mutableListOf<Path>()
            for (base in current) {
                if (segment.contains('*') || segment.contains('?')) {
                    val regex = Regex(
                        segment.map {
                            when (it) {
                                '*' -> ".*"
                                '?' -> "."
                                else -> Regex.escape(it.toString())
                            }
                        }.joinToString(""),
                    )
                    for (child in listDirectory(base)) {
                        if (regex.matches(child.fileName.toString())) next.add(child)
                    }
                } else if (last) {
                    val child = base.resolve(segment)
                    if (Files.exists(child)) next.add(child)
                } else {
                    val child = base.resolve(segment)
                    if (Files.isDirectory(child)) next.add(child)
                }
            }
            current = next
        }
        return current.sortedWith { left, right -> CanonicalText.compare(left.toString(), right.toString()) }
    }
}

/** `qualify.require_clean_checkout` through the shared host module. */
internal object CleanRequire {
    fun require(repository: Path, candidateSha: String) {
        io.github.rubixhacker.harness.host.CleanCheckout.require(repository.toFile(), candidateSha)
    }
}

/** One source XML report retained from a failed Safari lane, with its observed identity. */
private class FailedSourceXmlSnapshot(
    val module: String,
    val name: String,
    val raw: ByteArray,
    val modifiedNs: Long,
    val device: Long,
    val inode: Long,
)
