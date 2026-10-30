package io.github.rubixhacker.harness.qualification

import io.github.rubixhacker.harness.contract.Qualification
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

/**
 * The pure half of `tools/qualification/collection.py`: the artifact route table, the source index
 * object rules, the inventory digest, the unsigned 112-lane input map, and the candidate manifest
 * inputs.
 *
 * Every constant and message here is recorded evidence: a bundle quotes the reason a route was
 * rejected, so a reworded check invalidates the receipts that recorded it.
 */
object CollectionRules {
    val SHA40 = Regex("[0-9a-f]{40}")
    val SHA64 = Regex("[0-9a-f]{64}")

    /** `REQUIRED`: the producer routes a complete collection must carry. */
    val REQUIRED = listOf("full-ci", "full-common", "publication-ubuntu", "duplicate-provider")

    val SOURCE_ID = Regex("[A-Za-z0-9][A-Za-z0-9_-]{0,63}")

    const val MAX_SOURCE_BYTES = 10L * 1024 * 1024 * 1024
    const val MAX_EXPANDED_BYTES = 20L * 1024 * 1024 * 1024
    const val MAX_MEMBERS = 200_000

    /** The exact 112 lanes the approved suite manifest must declare. */
    const val REQUIRED_LANES = 112

    /**
     * `artifact_route`: the producer route of one downloaded artifact name.
     *
     * A name that carries *some* candidate SHA is an unrecognized artifact; a name with no SHA at
     * all belongs to no exact candidate.
     */
    fun artifactRoute(name: String, candidateSha: String): String {
        val routes = linkedMapOf(
            "full-ci-$candidateSha" to "full-ci",
            "full-common-$candidateSha" to "full-common",
            "publication-$candidateSha-ubuntu" to "publication-ubuntu",
            "publication-$candidateSha-macos" to "publication-macos",
            "publication-$candidateSha-windows" to "publication-windows",
            "duplicate-provider-$candidateSha" to "duplicate-provider",
            "qualification-$candidateSha" to "qualification-ubuntu",
        )
        routes[name]?.let { return it }
        for ((prefix, route) in listOf(
            "qualification-full-" to "full-hosted-",
            "qualification-" to "qualification-",
            "windows-failure-raw-" to "windows-failure-raw-",
        )) {
            val match = Regex(Regex.escape(prefix) + "([0-9a-f]{40})-(.+)").matchEntire(name)
            if (match != null) {
                if (match.groupValues[1] != candidateSha) {
                    throw IllegalArgumentException("artifact belongs to another candidate: $name")
                }
                return route + match.groupValues[2]
            }
        }
        if (Regex("[0-9a-f]{40}").containsMatchIn(name)) {
            throw IllegalArgumentException("unrecognized candidate artifact: $name")
        }
        throw IllegalArgumentException("artifact has no exact candidate SHA: $name")
    }

    /** `_keys`: one object with exactly the required keys plus the allowed optional ones. */
    fun keys(value: JsonElement?, required: Collection<String>, optional: Collection<String> = emptyList()) {
        if (value !is JsonObject || !value.keys.containsAll(required) ||
            (value.keys - required.toSet() - optional.toSet()).isNotEmpty()
        ) {
            throw IllegalArgumentException("source index object keys are invalid")
        }
    }

    /**
     * `independent_gates._file_path_name`: one archive member name that cannot escape.
     *
     * The message is the reference's, because a collection reason quotes it.
     */
    fun filePathName(relative: String?) {
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

    /** `_positive`: a JSON integer greater than zero, excluding booleans and floats. */
    fun positive(value: JsonElement?): Boolean = Py.isInt(value) && Py.int(value) > 0

    /** `_inventory_digest`: the canonical digest of one file inventory. */
    fun inventoryDigest(files: JsonObject): String = FullCorpus.canonicalDigest(files)

    /** `_file_inventory` key order: sorted by path. */
    fun sortedInventory(files: Map<String, JsonElement>): JsonObject = JsonObject(
        files.entries.sortedWith { left, right -> CanonicalText.compare(left.key, right.key) }
            .associateTo(LinkedHashMap()) { it.key to it.value },
    )

    /** `unsigned_inputs`: every approved lane, with the duplicate-provider archive where it ran. */
    fun unsignedInputs(
        manifest: JsonObject,
        artifacts: List<Pair<String, String>>,
        rows: List<JsonObject>,
    ): JsonObject {
        val lanes = manifest["lanes"] as? JsonObject ?: JsonObject(emptyMap())
        val inputs = LinkedHashMap<String, JsonElement>()
        for (lane in lanes.keys) {
            inputs[lane] = buildJsonObject { put("archives", buildJsonObject { }) }
        }
        for ((artifact, row) in artifacts.zip(rows)) {
            if (Py.str(row["route"]) != "duplicate-provider") continue
            val root = artifact.second
            if (root.isEmpty()) continue
            val archive = buildJsonObject { put("duplicate-provider", JsonPrimitive(root)) }
            inputs["jvm:Java:current:default"] = buildJsonObject { put("archives", archive) }
        }
        return JsonObject(inputs)
    }

    /**
     * `candidate_lane_input`: one lane of the candidate manifest inputs.
     *
     * The JVM lane carries no binary hashes and names its compiler-mode publication, because the
     * two JVM configurations share one pair of binaries.
     */
    fun candidateLaneInput(
        laneId: String,
        lane: JsonObject,
        candidateSha: String,
        hashes: Map<String, JsonObject>,
    ): JsonObject {
        val target = Py.str(lane["target"]) ?: ""
        val selected = LinkedHashMap<String, JsonElement>()
        selected["target"] = JsonPrimitive(target)
        selected["artifact_hashes"] = hashes[target] ?: JsonNull
        selected["runtime_identity"] = JsonNull
        if (target == "jvm") {
            selected["artifact_hashes"] = JsonNull
            selected["jvm_mode_publication"] = buildJsonObject {
                put("candidate_sha", JsonPrimitive(candidateSha))
                put("lane", JsonPrimitive(laneId))
                put("mode", lane["configuration"] ?: JsonNull)
                put("source", JsonPrimitive("compiler_modes.replay"))
                put("source_checkout", JsonNull)
                put("publication_archive", JsonNull)
                put("archive_digest", JsonNull)
                put("artifact_hashes", JsonNull)
            }
        }
        return JsonObject(selected)
    }

    /**
     * `_validate_index`: the frozen cross-run source index.
     *
     * `validateSourcePath` is `_safe_source_path`: a local origin must be an absolute, non-symbolic
     * path, which only the host can answer.
     */
    fun validateIndex(
        index: JsonObject,
        candidateSha: String,
        tree: String,
        manifest: JsonObject,
        repositoryName: String,
        runId: Long?,
        runAttempt: Long?,
        allowLocal: Boolean,
        validateSourcePath: (String) -> Unit,
        globalGates: Set<String> = emptySet(),
    ) {
        keys(index, listOf("schema", "candidate_sha", "source_tree", "sources", "bindings"))
        if (!Py.equalsInt(index["schema"], 1L) || !Py.isInt(index["schema"]) ||
            Py.str(index["candidate_sha"]) != candidateSha ||
            Py.str(index["source_tree"]) != tree
        ) {
            throw IllegalArgumentException("source index candidate or tree differs")
        }
        val sources = index["sources"] as? JsonArray
        val bindingsList = index["bindings"] as? JsonArray
        if (sources == null || bindingsList == null) {
            throw IllegalArgumentException("source index lists are invalid")
        }
        val ids = mutableSetOf<String>()
        val artifacts = mutableSetOf<Long>()
        val bindings = mutableSetOf<Pair<String?, String?>>()
        val lanes = manifest["lanes"] as? JsonObject ?: JsonObject(emptyMap())
        for (element in sources) {
            val source = element as? JsonObject
                ?: throw IllegalArgumentException("source index object keys are invalid")
            keys(source, listOf("id", "origin", "transport"))
            val sourceId = Py.str(source["id"])
            if (sourceId == null || !SOURCE_ID.matches(sourceId) || !ids.add(sourceId)) {
                throw IllegalArgumentException("source index has duplicate or unsafe source ID")
            }
            val origin = source["origin"] as? JsonObject
                ?: throw IllegalArgumentException("source origin is invalid")
            val kind = Py.str(origin["kind"])
            when (kind) {
                "local" -> {
                    if (!allowLocal) {
                        throw IllegalArgumentException(
                            "workflow token cannot read arbitrary local source paths",
                        )
                    }
                    keys(origin, listOf("kind", "path"))
                    validateSourcePath(Py.str(origin["path"]) ?: "")
                }
                "same_run", "github_actions" -> {
                    val common = listOf(
                        "kind", "repository", "workflow", "run_id", "run_attempt",
                        "name", "head_sha",
                    )
                    keys(
                        origin,
                        common + if (kind == "github_actions") {
                            listOf("artifact_id", "api_size_in_bytes")
                        } else {
                            emptyList()
                        },
                    )
                    if (Py.str(origin["repository"]) != repositoryName ||
                        Py.str(origin["workflow"]) != ".github/workflows/qualification.yml" ||
                        Py.str(origin["head_sha"]) != candidateSha ||
                        !positive(origin["run_id"]) || !positive(origin["run_attempt"]) ||
                        (Py.str(origin["name"]) ?: "").isEmpty()
                    ) {
                        throw IllegalArgumentException(
                            "source run, workflow, head, or artifact name differs",
                        )
                    }
                    if (kind == "same_run") {
                        if (!Py.equalsInt(origin["run_id"], runId ?: -1) ||
                            !Py.equalsInt(origin["run_attempt"], runAttempt ?: -1)
                        ) {
                            throw IllegalArgumentException("same-run source identity differs")
                        }
                        if (!Py.equalsInt(origin["run_attempt"], 1L)) {
                            throw IllegalArgumentException(
                                "same-run artifact lacks rerun attempt ownership proof",
                            )
                        }
                        artifactRoute(Py.str(origin["name"])!!, candidateSha)
                    } else {
                        val artifactId = origin["artifact_id"]
                        if (!positive(artifactId) || !artifacts.add(Py.int(artifactId)) ||
                            !positive(origin["api_size_in_bytes"])
                        ) {
                            throw IllegalArgumentException("duplicate or invalid GitHub artifact ID")
                        }
                    }
                }
                else -> throw IllegalArgumentException("source origin kind is invalid")
            }
            val transport = source["transport"] as? JsonObject
                ?: throw IllegalArgumentException("source index object keys are invalid")
            keys(
                transport,
                listOf("format"),
                listOf("size", "sha256", "files", "inventory_sha256"),
            )
            when (val format = Py.str(transport["format"])) {
                "directory" -> {
                    keys(transport, listOf("format", "files", "inventory_sha256"))
                    val files = transport["files"] as? JsonObject
                    if (files == null || files.isEmpty() || files.size > MAX_MEMBERS) {
                        throw IllegalArgumentException("source directory inventory is invalid")
                    }
                    var total = 0L
                    for ((path, element) in files) {
                        filePathName(path)
                        val record = element as? JsonObject
                            ?: throw IllegalArgumentException(
                                "source index object keys are invalid",
                            )
                        keys(record, listOf("size", "sha256"))
                        if (!Py.isInt(record["size"]) || Py.int(record["size"]) < 0 ||
                            !SHA64.matches(Py.str(record["sha256"]) ?: "")
                        ) {
                            throw IllegalArgumentException(
                                "source directory file pin is invalid",
                            )
                        }
                        total += Py.int(record["size"])
                    }
                    if (total > MAX_EXPANDED_BYTES ||
                        Py.str(transport["inventory_sha256"]) != inventoryDigest(files)
                    ) {
                        throw IllegalArgumentException(
                            "source directory inventory digest differs",
                        )
                    }
                }
                "zip", "tar", "tar.gz" -> {
                    keys(transport, listOf("format", "size", "sha256"))
                    if (!positive(transport["size"]) ||
                        Py.int(transport["size"]) > MAX_SOURCE_BYTES ||
                        !SHA64.matches(Py.str(transport["sha256"]) ?: "")
                    ) {
                        throw IllegalArgumentException("source archive byte pin is invalid")
                    }
                }
                else -> throw IllegalArgumentException("source transport format is invalid")
            }
            if (kind == "github_actions" && Py.str(transport["format"]) != "zip") {
                throw IllegalArgumentException("GitHub Actions artifact transport must be ZIP")
            }
        }
        for (element in bindingsList) {
            val binding = element as? JsonObject
                ?: throw IllegalArgumentException("source index object keys are invalid")
            keys(binding, listOf("source_id", "gate", "lane"), listOf("member_root", "target"))
            val sourceId = Py.str(binding["source_id"])
            val gate = Py.str(binding["gate"])
            val lane = Py.str(binding["lane"])
            if (sourceId !in ids) {
                throw IllegalArgumentException("binding names an absent source")
            }
            if (lane == null) {
                if (gate == null || gate !in globalGates) {
                    throw IllegalArgumentException("global binding gate is not approved")
                }
                val target = binding["target"]
                if (target != null && target !is JsonNull) {
                    val targets = lanes.values.mapNotNull { (it as? JsonObject)?.let { lane -> Py.str(lane["target"]) } }
                    if (Py.str(target) !in targets) {
                        throw IllegalArgumentException("global binding target is not approved")
                    }
                }
            } else if (lane !in lanes || gate == null ||
                gate !in requiredGates(lanes[lane])
            ) {
                throw IllegalArgumentException("lane or gate binding is not approved")
            } else if ("target" in binding &&
                Py.str(binding["target"]) != Py.str((lanes[lane] as JsonObject)["target"])
            ) {
                throw IllegalArgumentException("lane binding target differs from approved target")
            }
            if (!bindings.add(lane to gate)) {
                throw IllegalArgumentException("duplicate lane or global gate binding")
            }
            if ("member_root" in binding) {
                filePathName(Py.str(binding["member_root"]))
            }
        }
        val boundIds = bindingsList.mapNotNull { Py.str((it as JsonObject)["source_id"]) }.toSet()
        if (ids != boundIds) {
            throw IllegalArgumentException("source index has unbound source")
        }
    }

    /** `manifest["lanes"][lane]["required_gates"]` as a list of gate names. */
    private fun requiredGates(lane: JsonElement?): List<String> {
        val declared = (lane as? JsonObject)?.get("required_gates") as? JsonArray ?: return emptyList()
        return declared.mapNotNull { Py.str(it) }
    }

    /** `qualify.target_binary_hashes`: every target's two binary digests, from an audit. */
    fun targetBinaryHashes(artifacts: JsonArray): JsonObject {
        val audited = LinkedHashMap<String, String?>()
        for (element in artifacts) {
            val item = element as? JsonObject ?: continue
            audited[Py.str(item["path"]) ?: ""] = Py.str(item["sha256"])
        }
        val result = LinkedHashMap<String, JsonElement>()
        for (row in Qualification.matrix()) {
            val perModule = LinkedHashMap<String, JsonElement>()
            for (module in Qualification.modules) {
                val digest = audited[Qualification.targetBinaryPath(module, row.target)]
                perModule[module] = digest?.let { JsonPrimitive(it) } ?: JsonNull
            }
            result[row.target] = JsonObject(perModule)
        }
        return JsonObject(result)
    }
}
