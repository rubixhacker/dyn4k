package io.github.rubixhacker.harness.qualification

import io.github.rubixhacker.harness.contract.StrictJson
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.StandardCopyOption
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
import org.w3c.dom.Node

/**
 * `full_corpus.py` verification: the twelve report groups, the environment and artifact
 * bindings, the reviewed source inventory, the Node observations, and the archive receipts.
 *
 * Every problem string is recorded evidence: a reworded check invalidates the receipt that
 * quoted it.
 */
object CorpusVerification {
    /** `node_observation_problems`: the live Node observations of one run. */
    fun nodeObservationProblems(
        repository: Path,
        evidenceRoot: Path,
        binding: JsonObject,
        started: Long?,
        finished: Long?,
    ): List<String> {
        if (Py.equalsInt(binding["schema"] ?: JsonPrimitive(1), 1)) return emptyList()
        if (!Py.equalsInt(binding["schema"], 2)) return listOf("unknown common corpus binding schema")
        val resolvedRepository = repository.toAbsolutePath().normalize()
        val resolvedEvidence = evidenceRoot.toAbsolutePath().normalize()
        val recordedRoot = Py.str(binding["capture_root"])
        if (recordedRoot == null || !recordedRoot.startsWith("/") ||
            Path.of(recordedRoot).normalize().toString() != recordedRoot
        ) {
            return listOf("Node capture source root is absent or invalid")
        }
        val captureRoot = Path.of(recordedRoot)
        val observations = binding["node_observations"] as? JsonArray
            ?: return listOf("actual Node process observations are absent")
        val problems = mutableListOf<String>()
        if (Py.str(binding["observation_platform"]) != "linux") {
            problems.add("actual Node process observation is unsupported on this host")
        }
        if (Py.truthy(binding["node_observation_errors"])) {
            problems.add("Node process observation failed during capture")
        }
        val probe = resolvedRepository.resolve(FullCorpus.NODE_PROBE_PATH)
        if (!Files.isRegularFile(probe) ||
            Py.str(binding["node_probe_sha256"]) != CorpusFiles.digest(probe)
        ) {
            problems.add("Node startup probe source hash differs")
        }
        val directory = if (resolvedEvidence != resolvedRepository) {
            resolvedEvidence.resolve("node-observations")
        } else {
            Path.of(Py.str(binding["node_observation_dir"]) ?: "")
        }
        if (!Files.isDirectory(directory) || Files.isSymbolicLink(directory)) {
            return problems + "Node observation raw directory is absent or linked"
        }
        val seenGroups = mutableSetOf<String>()
        val seenProcesses = mutableSetOf<Triple<String?, Long, Long>>()
        val expectedFiles = mutableSetOf<String>()
        for (element in observations) {
            try {
                val row = element as? JsonObject ?: throw IllegalArgumentException("Node observation is not an object")
                val groupId = Py.str(row["group_id"])
                if (groupId == null || groupId !in FullCorpus.NODE_GROUPS || groupId in seenGroups) {
                    throw IllegalArgumentException("missing, wrong, or duplicate Node group")
                }
                seenGroups.add(groupId)
                val pid = Py.int(row["pid"])
                val startTicks = Py.int(row["start_ticks"])
                if (pid <= 0 || startTicks <= 0 ||
                    Triple(Py.str(row["boot_id"]), pid, startTicks) in seenProcesses
                ) {
                    throw IllegalArgumentException("duplicate or invalid Node process identity")
                }
                seenProcesses.add(Triple(Py.str(row["boot_id"]), pid, startTicks))
                if (started == null || finished == null ||
                    !(started <= Py.int(row["observed_ns"]) && Py.int(row["observed_ns"]) <= finished)
                ) {
                    throw IllegalArgumentException("stale Node process observation")
                }
                if (Py.str(row["task"]) != FullCorpus.nodeTask(groupId)) {
                    throw IllegalArgumentException("Node task differs from group")
                }
                if (FullCorpus.nodeCaptureRoot(row) != captureRoot.toString()) {
                    throw IllegalArgumentException("Node command differs from recorded capture root")
                }
                val selection = FullCorpus.nodeGroupForArgv(captureRoot.toString(), strings(row["argv"]))
                if (selection == null || selection.first != groupId) {
                    throw IllegalArgumentException("Node command differs from selected group")
                }
                val relativePayload = captureRoot.relativize(Path.of(selection.second))
                    .toString().replace('\\', '/')
                if (Py.str(row["payload_path"]) != relativePayload) {
                    throw IllegalArgumentException("Node payload path differs from command")
                }
                val evidencePayload = resolvedEvidence.resolve(relativePayload)
                if (!Files.isRegularFile(evidencePayload) || Files.isSymbolicLink(evidencePayload) ||
                    CorpusFiles.digest(evidencePayload) != Py.str(row["payload_sha256"])
                ) {
                    throw IllegalArgumentException("archived Node test payload bytes differ")
                }
                val candidatePayload = resolvedRepository.resolve(relativePayload)
                if (!Files.isRegularFile(candidatePayload) || Files.isSymbolicLink(candidatePayload) ||
                    CorpusFiles.digest(candidatePayload) != Py.str(row["payload_sha256"])
                ) {
                    throw IllegalArgumentException("candidate Node test payload bytes differ")
                }
                val payloadModified = Files.getLastModifiedTime(evidencePayload).to(TimeUnit.NANOSECONDS)
                if (payloadModified < started || payloadModified > finished) {
                    throw IllegalArgumentException("Node test payload is outside invocation window")
                }
                val loader = FullCorpus.nodeLaunchLoader(captureRoot.toString(), strings(row["argv"]))
                val loaderPath = loader?.let {
                    captureRoot.relativize(Path.of(it)).toString().replace('\\', '/')
                }
                if (Py.str(row["launch_loader_path"]) != loaderPath) {
                    throw IllegalArgumentException("Node launch loader differs from command")
                }
                if (loader != null) {
                    for (root in listOf(resolvedEvidence, resolvedRepository)) {
                        val candidateLoader = root.resolve(loaderPath!!)
                        if (!Files.isRegularFile(candidateLoader) || Files.isSymbolicLink(candidateLoader) ||
                            CorpusFiles.digest(candidateLoader) != Py.str(row["launch_loader_sha256"])
                        ) {
                            throw IllegalArgumentException("Node launch loader bytes differ")
                        }
                    }
                }
                if (loader == null && Py.str(row["launch_loader_sha256"]) != null) {
                    throw IllegalArgumentException("unexpected Node launch loader hash")
                }
                val reports = (binding["reports"] as? JsonObject)?.get(groupId)
                if (Py.str(row["report_sha256"]) != FullCorpus.canonicalDigest(reports ?: JsonNull)) {
                    throw IllegalArgumentException("Node group raw report binding differs")
                }
                val ancestry = row["ancestry"] as? JsonArray
                    ?: throw IllegalArgumentException("Node process is outside observed Gradle ancestry")
                val ancestryIsValid = ancestry.isNotEmpty() && ancestry.size <= 32 &&
                    Py.int((ancestry.first() as JsonObject)["pid"]) == pid &&
                    Py.int((ancestry.first() as JsonObject)["start_ticks"]) == startTicks &&
                    Py.int((ancestry.last() as JsonObject)["pid"]) == Py.int(binding["gradle_pid"]) &&
                    (Py.str(binding["gradle_start_ticks"]) == null ||
                        Py.int((ancestry.last() as JsonObject)["start_ticks"]) == Py.int(binding["gradle_start_ticks"])) &&
                    ancestry.zipWithNext().all { (first, second) ->
                        Py.int((first as JsonObject)["parent_pid"]) == Py.int((second as JsonObject)["pid"])
                    }
                if (!ancestryIsValid) {
                    throw IllegalArgumentException("Node process is outside observed Gradle ancestry")
                }
                val requestName = Py.str(row["request_name"]) ?: ""
                val nonce = Py.str(row["nonce"]) ?: ""
                if (requestName != "$pid-$nonce.json" || !Regex("[0-9a-f]{32}").matches(nonce)) {
                    throw IllegalArgumentException("Node request name or nonce differs")
                }
                val ackName = requestName.removeSuffix(".json") + ".ack"
                expectedFiles.add(requestName)
                expectedFiles.add(ackName)
                val requestFile = directory.resolve(requestName)
                val ackFile = directory.resolve(ackName)
                if (Files.isSymbolicLink(requestFile) || Files.isSymbolicLink(ackFile) ||
                    CorpusFiles.digest(requestFile) != Py.str(row["request_sha256"]) ||
                    Files.readString(ackFile) != nonce ||
                    CorpusFiles.digest(ackFile) != Py.str(row["ack_sha256"])
                ) {
                    throw IllegalArgumentException("Node startup request or acknowledgement differs")
                }
                val requestModified = Files.getLastModifiedTime(requestFile).to(TimeUnit.NANOSECONDS)
                val ackModified = Files.getLastModifiedTime(ackFile).to(TimeUnit.NANOSECONDS)
                if (requestModified < started || requestModified > finished ||
                    ackModified < started || ackModified > finished
                ) {
                    throw IllegalArgumentException("Node startup request or acknowledgement is stale")
                }
                val request = StrictJson.load(Files.readString(requestFile))
                val expectedRequest = buildJsonObject {
                    put("pid", JsonPrimitive(pid))
                    put("nonce", JsonPrimitive(nonce))
                    put("argv", row.getValue("requested_argv"))
                    put("execPath", row.getValue("requested_exec_path"))
                    put("version", row.getValue("version"))
                }
                if (request != expectedRequest) {
                    throw IllegalArgumentException("Node startup request differs from live observation")
                }
                val requestedArgv = strings(row["requested_argv"])
                val liveArgv = strings(row["argv"])
                if (requestedArgv.drop(1) !=
                    FullCorpus.nodeProcessArgv(captureRoot.toString(), liveArgv).drop(1) ||
                    Path.of(requestedArgv.first()).toAbsolutePath() != Path.of(liveArgv.first()).toAbsolutePath() ||
                    Path.of(Py.str(row["requested_exec_path"])!!).toAbsolutePath() !=
                    Path.of(Py.str(row["executable_path"])!!).toAbsolutePath()
                ) {
                    throw IllegalArgumentException("Node request command or executable differs")
                }
                val executable = Path.of(Py.str(row["executable_path"])!!)
                if (!Files.isRegularFile(executable) || Files.isSymbolicLink(executable) ||
                    CorpusFiles.digest(executable) != Py.str(row["executable_sha256"])
                ) {
                    throw IllegalArgumentException("observed Node executable bytes changed")
                }
                val builder = ProcessBuilder(executable.toString(), "--version")
                builder.environment().remove("NODE_OPTIONS")
                builder.environment().remove("DYN4K_NODE_OBSERVATION_DIR")
                val process = builder.start()
                val stdout = process.inputStream.use { it.readBytes() }
                process.errorStream.close()
                process.waitFor(3, TimeUnit.SECONDS)
                val version = stdout.toString(StandardCharsets.UTF_8).trim()
                if (Py.str(row["version"]) != version) {
                    throw IllegalArgumentException("observed Node version differs from executable")
                }
                if (CorpusFiles.digest(executable) != Py.str(row["executable_sha256"])) {
                    throw IllegalArgumentException("observed Node executable changed during replay")
                }
            } catch (error: Exception) {
                problems.add("Node process binding differs: ${error.message}")
            }
        }
        if (seenGroups != FullCorpus.NODE_GROUPS) {
            problems.add(
                "actual Node process groups missing: " +
                    Py.listRepr((FullCorpus.NODE_GROUPS - seenGroups).sortedWith(CanonicalText::compare)),
            )
        }
        val names = Files.newDirectoryStream(directory).use { stream ->
            stream.map { it.fileName.toString() }.toSet()
        }
        if (names != expectedFiles) problems.add("Node observation raw file inventory differs")
        return problems
    }

    /** `artifact_binding_problems`: the build outputs a report claims to have produced. */
    fun artifactBindingProblems(
        repository: Path,
        binding: JsonObject,
        started: Long?,
        finished: Long?,
        strictPaths: Boolean,
        checkMtime: Boolean = true,
    ): List<String> {
        val artifacts = binding["artifacts"] as? JsonArray
        if (artifacts == null || artifacts.isEmpty()) return listOf("candidate artifact binding is absent")
        val problems = mutableListOf<String>()
        val modules = mutableSetOf<String>()
        val names = mutableSetOf<String>()
        for (element in artifacts) {
            try {
                val item = element as? JsonObject ?: throw IllegalArgumentException("invalid artifact entry")
                val module = Py.str(item["module"]) ?: throw IllegalArgumentException("invalid artifact module")
                val name = Py.str(item["path"]) ?: throw IllegalArgumentException("invalid artifact path")
                val bound = Py.str(item["sha256"])
                val path = Path.of(name)
                if (module !in FullCorpus.MODULES || path.isAbsolute ||
                    ".." in name.split('/')
                ) {
                    throw IllegalArgumentException("invalid artifact path or module")
                }
                if (strictPaths) {
                    val parts = name.split('/')
                    if (parts.size < 2 || parts[0] != module || parts[1] != "build") {
                        throw IllegalArgumentException("candidate artifact is outside module build output")
                    }
                }
                if (name in names) throw IllegalArgumentException("duplicate candidate artifact")
                names.add(name)
                val source = repository.resolve(path)
                if (CorpusFiles.digest(source) != bound) {
                    throw IllegalArgumentException("candidate artifact SHA-256 differs")
                }
                if (checkMtime && started != null && finished != null) {
                    val modified = Files.getLastModifiedTime(source).to(TimeUnit.NANOSECONDS)
                    if (modified < started || modified > finished) {
                        throw IllegalArgumentException("candidate artifact is outside invocation window")
                    }
                }
                modules.add(module)
            } catch (error: Exception) {
                problems.add("candidate artifact binding differs: ${error.message}")
            }
        }
        if (modules != FullCorpus.MODULES.toSet()) {
            problems.add("candidate artifacts are required for both modules")
        }
        return problems
    }

    /** `archived_environment_problems`: the archived tool identities of a downloaded bundle. */
    fun archivedEnvironmentProblems(repository: Path, environment: JsonElement?, requireCheckout: Boolean): List<String> {
        if (environment !is JsonObject) return listOf("candidate environment receipt is absent")
        if (!requireCheckout) return emptyList()
        val problems = mutableListOf<String>()
        val wrappers = environment["gradle_wrapper"] as? JsonObject ?: JsonObject(emptyMap())
        for (relative in listOf(
            "gradlew", "gradle/wrapper/gradle-wrapper.jar", "gradle/wrapper/gradle-wrapper.properties",
        )) {
            val path = repository.resolve(relative)
            if (!Files.isRegularFile(path) || Py.str(wrappers[relative]) != CorpusFiles.digest(path)) {
                problems.add("candidate Gradle wrapper hash differs: $relative")
            }
        }
        for (name in listOf("java", "node")) {
            val executables = environment["executables"] as? JsonObject
            val identity = executables?.get(name) as? JsonObject
            if (identity == null ||
                !Py.SHA64.matches(Py.str(identity["sha256"]) ?: "") ||
                !Py.equalsInt(identity["exit_code"], 0) ||
                !Py.truthy(identity["version"])
            ) {
                problems.add("candidate $name identity receipt is invalid")
            }
        }
        return problems
    }

    /** `candidate_input_problems`: the manifest, map, and reviewed pairs must be committed. */
    fun candidateInputProblems(
        repository: Path,
        candidateSha: String,
        manifest: JsonObject,
        mapping: List<JsonObject>,
        manifestPath: Path? = null,
        mappingPath: Path? = null,
        checkCheckout: Boolean = true,
    ): List<String> {
        val problems = if (checkCheckout) {
            CorpusFiles.candidateCheckoutProblems(repository, candidateSha).toMutableList()
        } else {
            mutableListOf()
        }
        val paths = listOf(
            FullCorpus.MANIFEST_PATH to manifestPath,
            FullCorpus.MAP_PATH to mappingPath,
        )
        for ((relative, suppliedPath) in paths) {
            val canonical = repository.resolve(relative)
            val supplied = suppliedPath ?: canonical
            if (supplied.toAbsolutePath().normalize() != canonical.toAbsolutePath().normalize()) {
                problems.add("untracked or alternate candidate input: $supplied")
            }
            try {
                val committed = CorpusFiles.committedBytes(repository, candidateSha, relative)
                if (!Files.readAllBytes(supplied).contentEquals(committed) ||
                    !Files.readAllBytes(canonical).contentEquals(committed)
                ) {
                    problems.add("candidate commit bytes differ: $relative")
                }
                val parsed: JsonElement = if (relative == FullCorpus.MANIFEST_PATH) {
                    StrictJson.load(committed.toString(StandardCharsets.UTF_8))
                } else {
                    JsonArray(CorpusTsv.read(committed))
                }
                val expected = if (relative == FullCorpus.MANIFEST_PATH) {
                    manifest
                } else {
                    JsonArray(mapping)
                }
                if (parsed != expected) problems.add("candidate commit content differs: $relative")
            } catch (error: Exception) {
                problems.add("candidate commit input unavailable: $relative: ${error.message}")
            }
        }
        try {
            val auditedRows: List<JsonObject>
            if (candidateSha == FullCorpus.REVIEWED_MAP_COMMIT) {
                val reviewed = CorpusFiles.committedBytes(
                    repository, FullCorpus.REVIEWED_MAP_COMMIT, FullCorpus.MAP_PATH,
                )
                if (CorpusFiles.digest(reviewed) != FullCorpus.REVIEWED_MAP_SHA256) {
                    problems.add("independently reviewed pair map hash differs")
                }
                auditedRows = CorpusTsv.read(reviewed)
            } else {
                val reviewed = CorpusFiles.committedBytes(repository, candidateSha, FullCorpus.PAIR_PATH)
                if (!reviewed.contentEquals(Files.readAllBytes(repository.resolve(FullCorpus.PAIR_PATH)))) {
                    problems.add("candidate commit bytes differ: " + FullCorpus.PAIR_PATH)
                }
                if (CorpusFiles.digest(reviewed) != FullCorpus.REVIEWED_PAIRS_SHA256) {
                    problems.add("independently reviewed pair map hash differs")
                }
                auditedRows = CorpusTsv.read(reviewed)
            }
            val audited = LinkedHashMap<String?, JsonObject>()
            for (row in auditedRows) audited[Py.str(row["original"])] = row
            val actual = LinkedHashMap<String?, JsonObject>()
            for (row in FullCorpus.pairedRows(mapping)) actual[Py.str(row["original"])] = row
            if (audited.size != auditedRows.size || actual.size != mapping.size) {
                problems.add("duplicate original identity in reviewed pair map")
            }
            val originals = (audited.keys + actual.keys).filterNotNull()
                .sortedWith(CanonicalText::compare)
            for (original in originals) {
                if (audited[original] != actual[original]) {
                    problems.add("reviewed pair differs: $original")
                }
            }
        } catch (error: Exception) {
            problems.add("independently reviewed pair map unavailable: ${error.message}")
        }
        return problems
    }

    private fun strings(value: JsonElement?): List<String> =
        (value as? JsonArray)?.map { Py.str(it) ?: "" } ?: emptyList()
}
