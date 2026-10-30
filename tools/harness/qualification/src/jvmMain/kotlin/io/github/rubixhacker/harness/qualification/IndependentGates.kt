package io.github.rubixhacker.harness.qualification

import io.github.rubixhacker.harness.contract.Sha256
import io.github.rubixhacker.harness.contract.StrictJson
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.LinkOption
import java.nio.file.Path
import java.util.concurrent.TimeUnit
import javax.xml.parsers.DocumentBuilderFactory
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import org.w3c.dom.Element
import org.w3c.dom.Node

/**
 * `independent_gates.py`, first slice: the shared receipt primitives and the staged publication,
 * staged consumer, duplicate provider, and external unavailability gates.
 *
 * The numerical, physical, migration, performance, independent-review, and signed consumer
 * verifiers are not ported yet; `evaluate_gate` dispatches to all of them, so it arrives with the
 * last of them. The prospective binding closure lives in [GatesProspective].
 */
object IndependentGates {
    const val APPROVED_MANIFEST_SHA256 = "9aa2f50dd3c38129a70f4ed042f2b7ae5a90d4234def40d70520aad13f36b3fc"
    const val APPROVED_MANIFEST_REVISION = "2f5eb2d40df2d8549bb45f137e9f6b2c258e6ada"
    const val MANIFEST_PATH = "tools/qualification/full-suite-manifest.json"

    val SHA40 = Regex("[0-9a-f]{40}")
    val SHA64 = Regex("[0-9a-f]{64}")

    val LANE_GATES = setOf(
        "staged-artifacts", "staged-consumer", "numerical-parity",
        "physical-correctness", "unchanged-java-corpus",
        "java-source-compatibility", "duplicate-provider",
    )
    val GLOBAL_GATES = setOf(
        "migration-journeys", "performance-resource", "publication-contract", "independent-review",
    )
    val PRODUCER_SCOPED_GATES = setOf(
        "unchanged-java-corpus", "java-source-compatibility",
        "migration-journeys", "performance-resource", "independent-review",
    )

    val PRODUCER_MANIFEST_PATHS = linkedMapOf(
        "unchanged-java-corpus" to listOf("full-ci/lane-manifest.json"),
        "java-source-compatibility" to listOf("full-ci/lane-manifest.json"),
        "migration-journeys" to listOf("evidence/summary.json"),
        "performance-resource" to listOf("evidence/candidate-identity-at-pilot.json"),
        "independent-review" to listOf("standards.json", "spec.json"),
    )

    /** `full_klib_consumer.LOCAL_LANES`: the lanes whose consumer report is local. */
    val LOCAL_KLIB_LANES: Set<String> = buildSet {
        for (version in listOf("minimum", "current")) {
            for (mode in listOf("debug-g", "optimized-opt")) {
                add("linuxX64:Linux x64:$version:$mode")
            }
            for (mode in listOf("development", "production")) {
                add("js:Node.js:$version:$mode")
            }
        }
    }

    private val MODULES = listOf("dyn4k-core", "dyn4k")

    fun digest(value: JsonElement): String = Sha256.ofCanonical(value)

    /** `load_approved_manifest`: the tracked suite at its approved revision. */
    fun loadApprovedManifest(repository: Path): JsonObject {
        val raw = gitShow(repository, APPROVED_MANIFEST_REVISION, MANIFEST_PATH)
        val manifest = StrictJson.load(raw.toString(StandardCharsets.UTF_8))
        if (digest(manifest) != APPROVED_MANIFEST_SHA256) {
            throw IllegalArgumentException("approved complete-suite manifest changed")
        }
        return manifest as JsonObject
    }

    /** `_result`: one gate verdict with its recorded extras. */
    fun result(
        gate: String,
        status: String,
        reason: String,
        details: Map<String, JsonElement> = emptyMap(),
    ): JsonObject {
        val values = LinkedHashMap<String, JsonElement>()
        values["gate"] = JsonPrimitive(gate)
        values["status"] = JsonPrimitive(status)
        values["reason"] = JsonPrimitive(reason)
        values.putAll(details)
        return JsonObject(values)
    }

    /** `_json`: strict, finite JSON of one raw archive file. */
    fun json(path: Path): JsonElement {
        val value = StrictObjectJson.parse(Files.readString(path))
        if (!StrictJson.isFinite(value)) {
            throw IllegalArgumentException("non-finite raw JSON observation: $path")
        }
        return value
    }

    /** `_file_path`: one safe, regular, unlinked archive member. */
    fun filePath(root: Path, relative: String?): Path {
        checkPathName(relative)
        val path = relative!!.split('/').fold(root) { base, part -> base.resolve(part) }
        if (!Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS) || Files.isSymbolicLink(path)) {
            throw IllegalArgumentException("raw archive file is missing or symbolic: $relative")
        }
        return path
    }

    /** `_file_path_name`: the reference's archive member name contract, without a file read. */
    fun filePathName(relative: String?) = checkPathName(relative)

    /** `_file_path_name`. */
    private fun checkPathName(relative: String?) {
        if (relative.isNullOrEmpty() ||
            "\\" in relative ||
            "\n" in relative ||
            "\r" in relative ||
            relative.split('/').any { it in setOf("", ".", "..") } ||
            ":" in relative.split('/').first()
        ) {
            throw IllegalArgumentException("unsafe archive path: $relative")
        }
    }

    /** `_strict_json_line`: one strict JSON line of a browser launch record. */
    fun strictJsonLine(raw: String): JsonElement {
        val value = try {
            StrictObjectJson.parse(raw)
        } catch (error: ObservationError) {
            // Python's decoder accepts these constants and the hook rejects them by name.
            val constant = listOf("-Infinity", "Infinity", "NaN").firstOrNull { it in raw }
            if (constant != null) {
                throw IllegalArgumentException("non-finite browser launch value: $constant")
            }
            throw error
        }
        if (!StrictJson.isFinite(value)) {
            throw IllegalArgumentException("non-finite browser launch value")
        }
        return value
    }

    /** `_archive_paths`: every scanned archive file. */
    fun archivePaths(root: Path): Set<String> = ArchiveScan.scan(root).keys

    /** `_inventory`: the receipt must inventory exactly the archive it seals. */
    /**
     * `independent_gates._bounded_bundle`: verify a bounded raw bundle against the lane.
     *
     * The frozen probe manifest is read from the candidate commit, never the checkout, and the
     * bundle's route selects which artifact-hash map the independent audit must match.
     */
    fun boundedBundle(
        root: Path,
        candidateSha: String,
        lane: JsonObject,
        expectedArtifactHashes: JsonElement?,
        repository: Path,
    ): JsonObject {
        val manifestBytes = gitShow(repository, candidateSha, "tools/qualification/foundation-probes.json")
        val manifest = StrictJson.load(manifestBytes.toString(StandardCharsets.UTF_8)) as? JsonObject
            ?: throw IllegalArgumentException("foundation probe manifest is not an object")
        val summary = ArtifactCapture.verifyBundle(root, manifest, candidateSha)
        val route = Py.str(summary["route"]) ?: ""
        val target = if (route == "jsSafari") "js" else route
        val hashes = summary["artifact_hashes"] as? JsonObject
            ?: throw IllegalArgumentException("bounded archive hashes are missing")
        if (target != Py.str(lane["target"]) && route != "ubuntu-host") {
            throw IllegalArgumentException("bounded archive target differs from selected lane")
        }
        val observed: JsonElement? = if (route == "ubuntu-host") {
            hashes[Py.str(lane["target"]) ?: ""]
        } else {
            hashes[target]
        }
        if (observed != expectedArtifactHashes) {
            throw IllegalArgumentException("bounded archive artifacts differ from independent audit")
        }
        return summary
    }

    fun inventory(root: Path, receipt: JsonObject): String {
        val files = receipt["files"] as? JsonArray
        if (files == null || files.isEmpty()) throw IllegalArgumentException("raw file inventory is missing")
        val process = receipt["process"] as? JsonObject
            ?: throw IllegalArgumentException("raw process receipt is missing")
        val started = if (Py.isInt(process["started_ns"])) Py.int(process["started_ns"]) else null
        val finished = if (Py.isInt(process["finished_ns"])) Py.int(process["finished_ns"]) else null
        if (started == null || finished == null || started <= 0 || finished < started) {
            throw IllegalArgumentException("raw process execution window is invalid")
        }
        val seen = mutableSetOf<String>()
        for (element in files) {
            val item = element as? JsonObject
                ?: throw IllegalArgumentException("raw file inventory entry is invalid")
            val relative = Py.str(item["path"])
            if (relative == "receipt.json") throw IllegalArgumentException("receipt cannot inventory itself")
            val path = filePath(root, relative)
            if (!seen.add(relative!!)) throw IllegalArgumentException("duplicate archive path: $relative")
            if (!SHA64.matches(Py.str(item["sha256"]) ?: "") ||
                Files.readAllBytes(path).let { CorpusFiles.digest(it) } != Py.str(item["sha256"])
            ) {
                throw IllegalArgumentException("raw file hash differs: $relative")
            }
            val mtime = if (Py.isInt(item["mtime_ns"])) Py.int(item["mtime_ns"]) else null
            if (mtime == null || mtime < started || mtime > finished) {
                throw IllegalArgumentException("raw file timestamp differs from execution: $relative")
            }
            if (Files.getLastModifiedTime(path).to(TimeUnit.NANOSECONDS) != mtime) {
                throw IllegalArgumentException("raw file filesystem timestamp differs: $relative")
            }
        }
        if (archivePaths(root) != seen + "receipt.json") {
            throw IllegalArgumentException("archive has unlisted, missing, or duplicate files")
        }
        val sorted = JsonArray(files.sortedWith { left, right ->
            CanonicalText.compare(Py.str((left as JsonObject)["path"])!!, Py.str((right as JsonObject)["path"])!!)
        })
        return digest(
            buildJsonObject {
                put("receipt", receipt)
                put("files", sorted)
            },
        )
    }

    /** `consumer_contract`: the approved staged consumer case contract of one lane. */
    fun consumerContract(manifest: JsonObject, laneId: String): JsonObject {
        val lane = (manifest["lanes"] as? JsonObject)?.get(laneId) as? JsonObject
            ?: throw IllegalArgumentException("approved staged consumer lane is missing")
        val scopes = (lane["case_scopes"] as? JsonArray)?.mapNotNull { Py.str(it) }?.toSet() ?: emptySet()
        val cases = (manifest["cases"] as? JsonArray)?.mapNotNull { it as? JsonObject }
            ?.filter { Py.str(it["scope"]) in scopes } ?: emptyList()
        val identities = cases.mapNotNull { Py.str(it["id"]) }
        if (cases.isEmpty() || identities.toSet().size != identities.size) {
            throw IllegalArgumentException("approved staged consumer case contract is empty or duplicated")
        }
        return buildJsonObject {
            put("target", lane.getValue("target"))
            put("runtime", lane.getValue("runtime"))
            put("version", lane.getValue("version"))
            put("configuration", lane.getValue("configuration"))
            put("cases", JsonArray(cases))
        }
    }

    /** `_source_binding`: the local and committed bytes of every approved source. */
    fun sourceBinding(
        repository: Path,
        candidateSha: String,
        approvedPaths: Map<String, String>,
        label: String,
        localApproved: Map<String, String>? = null,
        gate: GateSource = GateGit,
    ): Map<String, String> {
        val local = localApproved ?: approvedPaths
        for ((relative, approved) in approvedPaths) {
            val localBytes = gate.read(gate.sourceRoot().resolve(relative))
            val committed = gate.show(repository, candidateSha, relative)
            if (CorpusFiles.digest(localBytes) != local[relative] ||
                CorpusFiles.digest(committed) != approved
            ) {
                throw IllegalArgumentException("$label blob differs: $relative")
            }
        }
        return approvedPaths
    }

    /** `_producer_scope`: the independently pinned producing artifact and runtime scope. */
    fun producerScope(gate: String, candidateSha: String, scopes: JsonElement?): JsonObject {
        val scope = (scopes as? JsonObject)?.get(gate) as? JsonObject
        val required = setOf(
            "candidate_sha", "target", "runtime", "runtime_identity", "artifact_hashes",
        )
        val extra = if (gate == "performance-resource") {
            setOf("producer_manifest_hashes", "verifier_sha256", "policy_sha256")
        } else {
            setOf("producer_manifest_hashes")
        }
        if (scope == null || !scope.keys.containsAll(required) ||
            (scope.keys - required - extra).isNotEmpty()
        ) {
            throw IllegalArgumentException("$gate independent producing artifact/runtime scope is missing")
        }
        if ("producer_manifest_hashes" !in scope) {
            throw IllegalArgumentException("$gate independently pinned producer manifest is missing")
        }
        if (Py.str(scope["candidate_sha"]) != candidateSha) {
            throw IllegalArgumentException("$gate producing source commit differs from exact candidate")
        }
        val expectedTarget = if (gate == "independent-review") "source" else "jvm"
        val expectedRuntime = if (gate == "independent-review") "codex" else "Java"
        if (Py.str(scope["target"]) != expectedTarget || Py.str(scope["runtime"]) != expectedRuntime ||
            Py.str(scope["runtime_identity"]).isNullOrEmpty()
        ) {
            throw IllegalArgumentException("$gate producing target or runtime identity differs")
        }
        val hashes = scope["artifact_hashes"]
        val requiredHashes = when (gate) {
            "independent-review" -> emptySet()
            "migration-journeys" -> setOf("dyn4k-core")
            else -> MODULES.toSet()
        }
        if (hashes !is JsonObject || hashes.keys != requiredHashes ||
            hashes.values.any { !SHA64.matches(Py.str(it) ?: "") }
        ) {
            throw IllegalArgumentException("$gate producing artifact hashes are incomplete")
        }
        val manifests = scope["producer_manifest_hashes"]
        val acceptedPaths = if (gate == "performance-resource") {
            setOf(
                (PRODUCER_MANIFEST_PATHS.getValue(gate)).toSet(),
                setOf("evidence/archive.json"),
            )
        } else {
            setOf(PRODUCER_MANIFEST_PATHS.getValue(gate).toSet())
        }
        if (manifests !is JsonObject || manifests.keys.toSet() !in acceptedPaths ||
            manifests.values.any { !SHA64.matches(Py.str(it) ?: "") }
        ) {
            throw IllegalArgumentException("$gate independently pinned producer manifest is missing")
        }
        if (gate == "performance-resource" && "evidence/archive.json" in manifests) {
            if (listOf("verifier_sha256", "policy_sha256").any {
                    !SHA64.matches(Py.str(scope[it]) ?: "")
                }
            ) {
                throw IllegalArgumentException("sustained performance verifier or approved policy pin is missing")
            }
        } else if ((scope.keys - required - setOf("producer_manifest_hashes")).isNotEmpty()) {
            throw IllegalArgumentException("$gate unexpected producing verifier scope")
        }
        return scope
    }

    /** `_producer_manifest_contract`: the pinned producer manifest names the exact candidate. */
    fun producerManifestContract(root: Path, gate: String, scope: JsonObject, candidateSha: String) {
        val manifests = scope["producer_manifest_hashes"] as JsonObject
        for ((relative, expected) in manifests) {
            val manifestFile = filePath(root, relative)
            if (CorpusFiles.digest(manifestFile) != Py.str(expected)) {
                throw IllegalArgumentException("$gate producer manifest differs from independent audit: $relative")
            }
            val manifest = json(manifestFile) as? JsonObject
                ?: throw IllegalArgumentException("$gate producer manifest is not an object: $relative")
            val sourceField = when (gate) {
                "migration-journeys" -> "candidate_commit"
                "performance-resource" -> "source_commit"
                else -> "candidate_sha"
            }
            if (Py.str(manifest[sourceField]) != candidateSha) {
                throw IllegalArgumentException("$gate producer manifest source differs from exact candidate")
            }
            when (gate) {
                "unchanged-java-corpus", "java-source-compatibility" -> {
                    if (Py.str(manifest["status"]) != "PASSED" ||
                        (manifest["files"] as? JsonObject)?.size != 24
                    ) {
                        throw IllegalArgumentException("reviewed full_ci producer manifest is incomplete")
                    }
                }
                "migration-journeys" -> {
                    if (!Py.equalsInt(manifest["expected_cases"], 10) ||
                        !Py.equalsInt(manifest["passed_cases"], 10) ||
                        !Py.equalsInt(manifest["failed_cases"], 0) ||
                        !Py.equalsInt(manifest["unavailable_cases"], 0)
                    ) {
                        throw IllegalArgumentException("migration producer manifest omits ten journeys")
                    }
                }
                "independent-review" -> {
                    val stem = Path.of(relative).fileName.toString().substringBeforeLast('.')
                    if (Py.str(manifest["review_kind"]) != stem) {
                        throw IllegalArgumentException("independent review producer manifest kind differs")
                    }
                }
            }
        }
    }

    /** `_binding`: the raw receipt must name this candidate, lane, and toolchain. */
    fun binding(
        root: Path,
        receipt: JsonObject,
        candidateSha: String,
        laneId: String,
        lane: JsonObject,
        repository: Path,
        expectedArtifactHashes: Map<String, String>?,
        expectedRuntimeIdentity: String?,
        gate: String,
        expectedProducerScopes: JsonElement?,
    ): JsonObject {
        val klibSchema = gate == "staged-consumer" && Py.equalsInt(receipt["schema"], 2) &&
            laneId in LOCAL_KLIB_LANES
        if ((!Py.equalsInt(receipt["schema"], 1) && !klibSchema) ||
            Py.str(receipt["candidate_sha"]) != candidateSha
        ) {
            throw IllegalArgumentException("raw candidate SHA differs")
        }
        val sourceTree = git(
            repository, "rev-parse", "$candidateSha^{tree}",
        ).trim()
        if (Py.str(receipt["source_tree"]) != sourceTree) {
            throw IllegalArgumentException("raw Git source tree differs from exact candidate")
        }
        if (gate !in GLOBAL_GATES || receipt["lane"] != null) {
            if (Py.str(receipt["lane"]) != laneId) throw IllegalArgumentException("raw lane differs")
            for (key in listOf("target", "runtime", "version", "configuration")) {
                if (receipt[key] != lane[key]) {
                    throw IllegalArgumentException("raw $key differs from selected lane")
                }
            }
            if (gate !in PRODUCER_SCOPED_GATES &&
                (expectedRuntimeIdentity.isNullOrEmpty() ||
                    Py.str(receipt["runtime_identity"]) != expectedRuntimeIdentity)
            ) {
                throw IllegalArgumentException("raw runtime identity differs from independent selection")
            }
        }
        val selectedHashes: Map<String, String>
        if (gate in PRODUCER_SCOPED_GATES) {
            val scope = producerScope(gate, candidateSha, expectedProducerScopes)
            if (receipt["producer_scope"] != scope ||
                Py.str(receipt["runtime_identity"]) != Py.str(scope["runtime_identity"])
            ) {
                throw IllegalArgumentException(
                    "raw producing artifact/runtime scope differs from independent selection",
                )
            }
            producerManifestContract(root, gate, scope, candidateSha)
            selectedHashes = (scope["artifact_hashes"] as JsonObject)
                .mapValues { (_, value) -> Py.str(value)!! }
        } else {
            if (expectedArtifactHashes == null ||
                expectedArtifactHashes.keys != MODULES.toSet() ||
                expectedArtifactHashes.values.any { !SHA64.matches(it) }
            ) {
                throw IllegalArgumentException("independently audited target binary hashes are missing")
            }
            selectedHashes = expectedArtifactHashes
        }
        val declared = receipt["artifact_hashes"] as? JsonObject
        if (declared == null ||
            declared.keys != selectedHashes.keys ||
            selectedHashes.any { (module, value) -> Py.str(declared[module]) != value }
        ) {
            throw IllegalArgumentException("raw artifact hashes differ from independent staging audit")
        }
        val process = receipt["process"] as? JsonObject
            ?: throw IllegalArgumentException("raw command or exit code is missing")
        val command = process["command"] as? JsonArray
        if (command == null || command.isEmpty() ||
            command.any { Py.str(it).isNullOrEmpty() } ||
            !Py.isInt(process["exit_code"])
        ) {
            throw IllegalArgumentException("raw command or exit code is missing")
        }
        for (key in listOf("stdout", "stderr")) {
            if (key in process) filePath(root, Py.str(process[key]))
        }
        return process
    }

    /** `_process_proof`: the recorded process output must show the exact lane execution. */
    fun processProof(root: Path, process: JsonObject, gate: String, laneId: String, receipt: JsonObject? = null): String {
        val command = (process["command"] as JsonArray).mapNotNull { Py.str(it) }
        val executable = Path.of(command.first()).fileName.toString().lowercase()
        val allowed = setOf(
            "gradlew", "gradle", "adb", "xcrun", "node", "wasmtime",
            "podman", "python", "python3", "java", "javac", "codex",
        )
        if (executable !in allowed) {
            throw IllegalArgumentException("raw $gate command has no recognized execution launcher")
        }
        if (executable in setOf("python", "python3") &&
            command.drop(1).none { it.endsWith(".py") || it.endsWith(".sh") }
        ) {
            throw IllegalArgumentException("raw $gate Python command lacks an executable verifier")
        }
        if (gate in setOf("staged-consumer", "duplicate-provider", "staged-artifacts", "publication-contract")) {
            if (executable !in setOf("gradlew", "gradle", "adb", "xcrun", "node", "wasmtime", "podman")) {
                throw IllegalArgumentException(
                    "raw $gate command does not launch a consumer or staging task",
                )
            }
            if ("stdout" !in process) {
                throw IllegalArgumentException("raw $gate process output is missing")
            }
            val output = Files.readString(filePath(root, Py.str(process["stdout"])))
            val klibV2 = gate == "staged-consumer" && receipt != null &&
                Py.equalsInt(receipt["schema"], 2) && laneId in command &&
                laneId in LOCAL_KLIB_LANES
            val marker = "QUALIFICATION_LANE=$laneId"
            val lines = output.lines()
            val laneSeen = if (klibV2) {
                lines.any { it == marker || it.endsWith(" [QUIET] [system.out] $marker") || it == "[QUIET] [system.out] $marker" }
            } else {
                marker in lines
            }
            if (!laneSeen) {
                throw IllegalArgumentException("raw $gate output lacks exact lane execution marker")
            }
            if (executable in setOf("gradlew", "gradle")) {
                val taskPattern = if (klibV2) {
                    Regex("(?m)^(?:[^\\n]+ )?\\[LIFECYCLE\\] \\[[^\\]\\n]+\\] > Task :[^\\s]+$")
                } else {
                    Regex("(?m)^> Task :[^\\s]+")
                }
                if (!taskPattern.containsMatchIn(output)) {
                    throw IllegalArgumentException("raw $gate Gradle task output is absent")
                }
                val expected = if (!Py.equalsInt(process["exit_code"], 0)) "BUILD FAILED" else "BUILD SUCCESSFUL"
                if (expected !in output) {
                    throw IllegalArgumentException("raw $gate Gradle outcome is absent")
                }
            } else if ("QUALIFICATION_PROCESS_EXIT=${Py.int(process["exit_code"])}" !in lines) {
                throw IllegalArgumentException("raw $gate runtime exit marker is absent")
            }
        }
        return executable
    }

    /** `_process_file_binding`: the output must print the digest of the named input. */
    fun processFileBinding(root: Path, process: JsonObject, relative: String?, label: String) {
        val path = filePath(root, relative)
        val marker = "QUALIFICATION_${label}_SHA256=${CorpusFiles.digest(path)}"
        val output = Files.readString(filePath(root, Py.str(process["stdout"])))
        if (output.lines().none { it == marker || it.endsWith(" $marker") }) {
            throw IllegalArgumentException("raw process output does not bind $relative")
        }
    }

    /** `_duplicate_provider`: the consumer must reject both providers with a failing task. */
    fun duplicateProvider(root: Path, receipt: JsonObject, process: JsonObject): String {
        val graphPath = filePath(root, Py.str(receipt["provider_graph"]))
        processFileBinding(root, process, Py.str(receipt["provider_graph"]), "PROVIDER_GRAPH")
        val graph = Files.readString(graphPath)
        val duplicate = try {
            io.github.rubixhacker.harness.contract.Qualification.checkProviders(graph)
            null
        } catch (error: IllegalArgumentException) {
            error
        }
        if (duplicate == null) {
            throw IllegalArgumentException("both provider coordinates are absent from raw graph")
        }
        val stderr = if ("stderr" in process) {
            Files.readString(filePath(root, Py.str(process["stderr"])))
        } else {
            null
        }
        if ("duplicate org.dyn4j provider" !in (duplicate.message ?: "") ||
            Py.equalsInt(process["exit_code"], 0) ||
            stderr == null ||
            "duplicate org.dyn4j provider" !in stderr
        ) {
            throw IllegalArgumentException("duplicate provider diagnostic or failure is absent")
        }
        val command = (process["command"] as JsonArray).mapNotNull { Py.str(it) }
        if (command.drop(1).none { "dependenc" in it.lowercase() || "provider" in it.lowercase() }) {
            throw IllegalArgumentException("raw command does not run provider dependency diagnosis")
        }
        val task = command.last().split(':').last()
        val output = Files.readString(filePath(root, Py.str(process["stdout"])))
        if (output.lines().none { it.startsWith("> Task :") && it.split(':').last().split(' ').first() == task }) {
            throw IllegalArgumentException("raw provider task output differs from executed command")
        }
        return "raw provider graph, command output, and failing diagnostic agree"
    }

    /** `_external_unavailable`: a recorded unavailability observation, bound to the lane. */
    fun externalUnavailable(receipt: JsonObject, candidateSha: String, laneId: String, gate: String): JsonObject {
        val reason = Py.str(receipt["reason"])
        if (!Py.equalsInt(receipt["schema"], 1) ||
            Py.str(receipt["candidate_sha"]) != candidateSha ||
            (gate !in GLOBAL_GATES && Py.str(receipt["lane"]) != laneId) ||
            (receipt["lane"] != null && Py.str(receipt["lane"]) != laneId) ||
            reason.isNullOrBlank() ||
            Py.str(receipt["observed_by"]).isNullOrBlank() ||
            !Py.isInt(receipt["observed_at_ns"]) || Py.int(receipt["observed_at_ns"]) <= 0
        ) {
            throw IllegalArgumentException("external unavailability observation is incomplete or misbound")
        }
        return result(
            gate, "UNAVAILABLE", reason,
            mapOf("observation_sha256" to JsonPrimitive(digest(receipt))),
        )
    }

    /** `_validated_all_target_hashes`: all 21 targets, both modules, valid digests. */
    fun validatedAllTargetHashes(hashes: JsonElement?): JsonObject {
        val targets = io.github.rubixhacker.harness.contract.Qualification.matrixTargets()
        val value = hashes as? JsonObject
            ?: throw IllegalArgumentException("independently audited 21-target binary hash map is incomplete")
        val valid = value.keys == targets && value.values.all { entry ->
            entry is JsonObject && entry.keys == MODULES.toSet() &&
                entry.values.all { SHA64.matches(Py.str(it) ?: "") }
        }
        if (!valid) {
            throw IllegalArgumentException("independently audited 21-target binary hash map is incomplete")
        }
        return value
    }

    /** `_gate_artifact_hashes`: which audited hashes one gate compares against. */
    fun gateArtifactHashes(
        gate: String,
        lane: JsonObject,
        laneHashes: Map<String, String>,
        allTargetHashes: JsonElement?,
    ): Map<String, String> {
        if (Py.str(lane["target"]) == "jvm" &&
            gate in setOf("staged-artifacts", "publication-contract")
        ) {
            if (allTargetHashes == null) {
                throw IllegalArgumentException("independently audited 21-target binary hash map is missing")
            }
            val selected = validatedAllTargetHashes(allTargetHashes).getValue("jvm") as JsonObject
            return selected.mapValues { (_, value) -> Py.str(value)!! }
        }
        return laneHashes
    }

    /** `_staged_publication`: the whole staged repository must pass the publication audit. */
    fun stagedPublication(
        root: Path,
        candidateSha: String,
        lane: JsonObject,
        expectedArtifactHashes: Map<String, String>,
        repository: Path,
        expectedAllTargetHashes: JsonElement? = null,
    ): String {
        val staging = root.resolve("staged")
        if (!Files.isDirectory(staging) || Files.isSymbolicLink(staging)) {
            throw IllegalArgumentException("full staged repository is missing")
        }
        val audit = StagingAudit.audit(staging, candidateSha)
        if (Py.str(audit["status"]) != "PASSED") {
            val errors = (audit["errors"] as JsonArray).take(4).joinToString("; ") { Py.str(it) ?: "" }
            throw IllegalArgumentException("full staged publication audit failed: $errors")
        }
        val license = gitShow(repository, candidateSha, "LICENSE.md")
        for (element in audit["artifacts"] as JsonArray) {
            val item = element as JsonObject
            val path = staging.resolve(Py.str(item["path"])!!)
            val name = path.fileName.toString()
            if ("license" in name.lowercase() && name.endsWith(".md")) {
                if (!Files.readAllBytes(path).contentEquals(license)) {
                    throw IllegalArgumentException(
                        "staged license differs from exact candidate: ${Py.str(item["path"])}",
                    )
                }
            } else if (name.endsWith(".jar") && "sources" !in name && "javadoc" !in name) {
                ArchiveContract.open(path) { archive ->
                    val manifest = archive.getEntry("META-INF/LICENSE.md")
                        ?: throw IllegalArgumentException(
                            "embedded license differs from exact candidate: ${Py.str(item["path"])}",
                        )
                    val bytes = archive.getInputStream(manifest).use { it.readBytes() }
                    if (!bytes.contentEquals(license)) {
                        throw IllegalArgumentException(
                            "embedded license differs from exact candidate: ${Py.str(item["path"])}",
                        )
                    }
                }
            }
        }
        val selected: Map<String, Map<String, String>>
        if (expectedAllTargetHashes != null) {
            val all = validatedAllTargetHashes(expectedAllTargetHashes)
            val target = Py.str(lane["target"])!!
            val declared = (all[target] as JsonObject).mapValues { (_, value) -> Py.str(value)!! }
            if (declared != expectedArtifactHashes) {
                throw IllegalArgumentException("selected target hashes differ from all-target audit")
            }
            selected = all.mapValues { (_, value) ->
                (value as JsonObject).mapValues { (_, sha) -> Py.str(sha)!! }
            }
        } else {
            selected = mapOf(Py.str(lane["target"])!! to expectedArtifactHashes)
        }
        for ((target, hashes) in selected) {
            for (module in MODULES) {
                val binary = staging.resolve(
                    io.github.rubixhacker.harness.contract.Qualification.targetBinaryPath(module, target),
                )
                if (!Files.isRegularFile(binary, LinkOption.NOFOLLOW_LINKS) || Files.isSymbolicLink(binary)) {
                    throw IllegalArgumentException("staged target binary is missing: $target/$module")
                }
                if (CorpusFiles.digest(binary) != hashes[module]) {
                    throw IllegalArgumentException(
                        "staged target binary differs from independent audit: $target/$module",
                    )
                }
            }
        }
        return "full staged audit verified ${(audit["artifacts"] as JsonArray).size} publication files"
    }

    /**
     * `_staged_consumer`: the external consumer must run this lane's exact cases against the
     * audited binaries. Returns the reason and whether the full-suite contract (not the frozen
     * foundation probe) was used.
     */
    fun stagedConsumer(
        root: Path,
        receipt: JsonObject,
        candidateSha: String,
        laneId: String,
        lane: JsonObject,
        expectedArtifactHashes: Map<String, String>,
        repository: Path,
        process: JsonObject,
        manifest: JsonObject,
    ): Pair<String, Boolean> {
        val target = Py.str(lane["target"])!!
        val suffix = when (target) {
            "js" -> "jsNode"
            "wasmJs" -> "wasmJsNode"
            "wasmWasi" -> "wasmWasiNode"
            else -> target
        }
        val groupId = "consumer-$suffix"
        val foundation = StrictJson.load(
            gitShow(repository, candidateSha, "tools/qualification/foundation-probes.json")
                .toString(StandardCharsets.UTF_8),
        ) as JsonObject
        val group = (foundation["groups"] as JsonArray).mapNotNull { it as? JsonObject }
            .firstOrNull { Py.str(it["id"]) == groupId }
        val runtimes = setOf(
            "Java", "Node.js", "Linux x64", "macOS ARM64", "Windows x64",
            "iOS simulator ARM64", "iOS simulator x64", "tvOS simulator ARM64",
            "watchOS simulator ARM64",
        )
        val foundationRoute = Py.str(receipt["consumer_group"]) != "full-suite" && group != null &&
            Py.str(lane["runtime"]) in runtimes
        val expected = mutableSetOf<JsonElement>()
        if (foundationRoute) {
            if (Py.str(receipt["consumer_group"]) != groupId) {
                throw IllegalArgumentException("frozen staged consumer group differs")
            }
            val task = Path.of(Py.str(group!!["report_pattern"])!!).parent.fileName.toString()
            val command = (process["command"] as JsonArray).mapNotNull { Py.str(it) }
            if (command.drop(1).none { it.endsWith(":$task") || it == task }) {
                throw IllegalArgumentException("raw command does not execute exact consumer task")
            }
            val output = Files.readString(filePath(root, Py.str(process["stdout"])))
            if (output.lines().none { line ->
                    line.startsWith("> Task :") && line.split(':').last().split(' ').first() == task
                }
            ) {
                throw IllegalArgumentException("raw consumer task output differs from executed command")
            }
            for (case in ProbeManifest.expectedCases(foundation, group)) {
                expected.add(JsonArray(listOf(JsonPrimitive(case.classname), JsonPrimitive(case.name))))
            }
        } else {
            val contract = consumerContract(manifest, laneId)
            val command = (process["command"] as JsonArray).mapNotNull { Py.str(it) }
            if (Py.str(receipt["consumer_group"]) != "full-suite" ||
                Py.str(receipt["consumer_contract_sha256"]) != digest(contract) ||
                laneId !in command
            ) {
                throw IllegalArgumentException(
                    "full staged consumer command or approved lane contract differs",
                )
            }
            for (element in contract["cases"] as JsonArray) {
                expected.add(JsonPrimitive(Py.str((element as JsonObject)["id"])!!))
            }
        }
        val graph = Files.readString(filePath(root, Py.str(receipt["provider_graph"])))
        processFileBinding(root, process, Py.str(receipt["provider_graph"]), "PROVIDER_GRAPH")
        val providers = Regex("io\\.github\\.rubixhacker:([^:\\s]+):").findAll(graph)
            .map { it.groupValues[1] }.toSet()
        val expectedProviders = MODULES.map {
            io.github.rubixhacker.harness.contract.Qualification.targetPublicationName(it, target)
        }.toSet()
        if ("org.dyn4j:dyn4j" in graph || !providers.containsAll(expectedProviders)) {
            throw IllegalArgumentException("external consumer provider graph is incomplete or duplicated")
        }
        val binaries = receipt["resolved_artifacts"] as? JsonObject
        if (binaries == null || binaries.keys != MODULES.toSet()) {
            throw IllegalArgumentException("both resolved external consumer binaries are required")
        }
        for (module in MODULES) {
            val relative = Py.str(binaries[module])!!
            processFileBinding(root, process, relative, "RESOLVED_" + module.uppercase().replace("-", "_"))
            if (CorpusFiles.digest(filePath(root, relative)) != expectedArtifactHashes[module]) {
                throw IllegalArgumentException("resolved external consumer artifact differs: $module")
            }
        }
        val reports = receipt["consumer_xml"] as? JsonArray
        if (reports == null || reports.isEmpty() ||
            reports.mapNotNull { Py.str(it) }.toSet().size != reports.size
        ) {
            throw IllegalArgumentException("raw staged consumer XML report paths are missing or duplicate")
        }
        val observed = mutableListOf<JsonElement>()
        for (element in reports) {
            val relative = Py.str(element)!!
            processFileBinding(root, process, relative, "CONSUMER_XML")
            val suite = suiteOf(Files.readAllBytes(filePath(root, relative)))
            if (suite.tagName != "testsuite") {
                throw IllegalArgumentException("raw staged consumer XML root is not testsuite")
            }
            val cases = elementsNamed(suite, "testcase")
            val counts = linkedMapOf(
                "failures" to cases.count { childNamed(it, "failure") != null }.toLong(),
                "errors" to cases.count { childNamed(it, "error") != null }.toLong(),
                "skipped" to cases.count { childNamed(it, "skipped") != null }.toLong(),
            )
            counts["tests"] = cases.size.toLong()
            val suiteTime = suite.getAttribute("time").ifEmpty { "nan" }.toDoubleOrNull()
            if (counts.any { (name, count) ->
                    suite.getAttribute(name).isEmpty() ||
                        suite.getAttribute(name).toLongOrNull() != count
                } ||
                counts.filterKeys { it != "tests" }.values.any { it != 0L } ||
                suiteTime == null || suiteTime.isNaN() || suiteTime < 0 ||
                suiteTime == Double.POSITIVE_INFINITY
            ) {
                throw IllegalArgumentException("staged consumer XML counts or outcomes differ")
            }
            for (case in cases) {
                val caseTime = case.getAttribute("time").ifEmpty { "nan" }.toDoubleOrNull()
                if (caseTime == null || caseTime.isNaN() || caseTime < 0 ||
                    caseTime == Double.POSITIVE_INFINITY
                ) {
                    throw IllegalArgumentException("staged consumer XML case identity or time is invalid")
                }
                if (foundationRoute) {
                    val classname = case.getAttribute("classname")
                    val name = case.getAttribute("name")
                    if (classname.isEmpty() || name.isEmpty()) {
                        throw IllegalArgumentException("staged consumer XML case identity or time is invalid")
                    }
                    observed.add(JsonArray(listOf(JsonPrimitive(classname), JsonPrimitive(name))))
                } else {
                    val id = case.getAttribute("id")
                    if (id.isEmpty()) {
                        throw IllegalArgumentException("staged consumer XML case identity or time is invalid")
                    }
                    observed.add(JsonPrimitive(id))
                }
            }
        }
        if (observed.size != observed.toSet().size || observed.toSet() != expected) {
            throw IllegalArgumentException(
                "staged consumer case identities or counts differ from frozen manifest",
            )
        }
        return "${observed.size} raw external consumer cases and both resolved artifacts verified" to
            !foundationRoute
    }

    private fun gitShow(repository: Path, revision: String, path: String): ByteArray {
        val process = ProcessBuilder(
            "git", "--no-replace-objects", "-C", repository.toString(), "show", "$revision:$path",
        ).start()
        val output = process.inputStream.use { it.readBytes() }
        process.errorStream.close()
        if (process.waitFor() != 0) {
            throw IllegalArgumentException("committed input is unavailable: $path")
        }
        return output
    }

    private fun git(repository: Path, vararg arguments: String): String {
        val process = ProcessBuilder(
            listOf("git", "--no-replace-objects", "-C", repository.toString()) + arguments,
        ).start()
        val output = process.inputStream.use { it.readBytes() }
        process.errorStream.close()
        if (process.waitFor() != 0) throw IllegalArgumentException("git failed")
        return output.toString(StandardCharsets.UTF_8)
    }

    private fun suiteOf(raw: ByteArray): Element {
        val factory = DocumentBuilderFactory.newInstance()
        factory.isNamespaceAware = false
        val builder = factory.newDocumentBuilder()
        builder.setErrorHandler(
            object : org.xml.sax.ErrorHandler {
                override fun warning(exception: org.xml.sax.SAXParseException) = Unit
                override fun error(exception: org.xml.sax.SAXParseException) = throw exception
                override fun fatalError(exception: org.xml.sax.SAXParseException) = throw exception
            },
        )
        return builder.parse(raw.inputStream()).documentElement
    }

    private fun elementsNamed(root: Element, name: String): List<Element> {
        val nodes = root.getElementsByTagName(name)
        return (0 until nodes.length).map { nodes.item(it) as Element }
    }

    private fun childNamed(element: Element, name: String): Element? {
        var node: Node? = element.firstChild
        while (node != null) {
            if (node.nodeType == Node.ELEMENT_NODE && (node as Element).tagName == name) return node
            node = node.nextSibling
        }
        return null
    }
}
