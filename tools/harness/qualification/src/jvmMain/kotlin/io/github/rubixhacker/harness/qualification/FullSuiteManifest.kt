package io.github.rubixhacker.harness.qualification

import io.github.rubixhacker.harness.contract.Qualification
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.Path
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject

/**
 * `full_suite_manifest.py`: the frozen complete-port suite derived from the reviewed corpus.
 *
 * The manifest names every case, area, lane, and independent gate, and its bindings pin the
 * corpus, the map, the reviewed pairs, and the upstream revision.
 */
object FullSuiteManifest {
    const val MANIFEST_PATH = "tools/qualification/full-suite-manifest.json"
    const val CORPUS_PATH = "tools/qualification/full-common-corpus.json"

    val AREA_IDS = listOf("geometry", "collision", "dynamics", "joints", "compatibility")

    val LANE_GATES = listOf(
        "staged-artifacts", "staged-consumer", "numerical-parity", "physical-correctness",
    )
    val JVM_GATES = listOf("unchanged-java-corpus", "java-source-compatibility", "duplicate-provider")
    val GLOBAL_GATES = listOf(
        "migration-journeys", "performance-resource", "publication-contract", "independent-review",
    )

    val GATE_DESCRIPTIONS = linkedMapOf(
        "staged-artifacts" to
            "Both staged target binaries, metadata, sources, documentation, licenses, and hashes match the candidate.",
        "staged-consumer" to
            "An external consumer resolves both staged modules and executes the selected target runtime and configuration.",
        "numerical-parity" to
            "Frozen baseline comparisons pass with the approved metrics and limits on this lane.",
        "physical-correctness" to
            "Independent physical checks pass or retain explicit failed dispositions on this lane.",
        "unchanged-java-corpus" to
            "All applicable unchanged baseline Java tests execute on the JVM candidate.",
        "java-source-compatibility" to
            "Unchanged Java consumers compile and run with the compatibility API and shared state.",
        "duplicate-provider" to
            "The staged consumer rejects simultaneous dyn4j and dyn4k-core providers.",
        "migration-journeys" to
            "The pinned unchanged sample collection compiles and completes each required observed journey.",
        "performance-resource" to
            "Approved sustained timing, allocation, and memory probes pass on validated reference environments.",
        "publication-contract" to
            "All target publications pass the staged artifact and checksum audit.",
        "independent-review" to "Separate standards and spec reviews resolve actionable findings.",
    )

    val GATE_SOURCES = linkedMapOf(
        "staged-artifacts" to listOf("tools/qualification/artifact.py"),
        "staged-consumer" to listOf(
            "consumers/qualification/portable/src/commonTest/kotlin/qualification/StagedGeometryTest.kt",
        ),
        "numerical-parity" to listOf("tools/numerical/fixtures.json"),
        "physical-correctness" to listOf("tools/numerical/weld-pulley-physical-manifest.json"),
        "unchanged-java-corpus" to listOf(FullCorpus.MAP_PATH),
        "java-source-compatibility" to listOf(
            "consumers/qualification/src/main/java/qualification/JavaMigration.java",
        ),
        "duplicate-provider" to listOf("tools/qualification/qualify.py"),
        "migration-journeys" to listOf("tools/migration/journeys.py"),
        "performance-resource" to listOf("docs/research/performance-manifest-v1.json"),
        "publication-contract" to listOf("tools/qualification/artifact.py"),
        "independent-review" to listOf("docs/agents/writing.md", "docs/specs/complete-port.md"),
    )

    /** `area_for`: the reviewed area one corpus case belongs to. */
    fun areaFor(case: JsonObject): String {
        if (Py.str(case["module"]) == "dyn4k") return "compatibility"
        val name = (Py.str(case["classname"]) ?: "").removePrefix("org.dyn4j.")
        if (".joint." in name || "Joint" in name) return "joints"
        if (name.startsWith("collision.") || name.startsWith("coverage.collision.") ||
            "CollisionWorld" in name
        ) {
            return "collision"
        }
        if (name.startsWith("dynamics.") || name.startsWith("world.") ||
            name.startsWith("coverage.dynamics.") || name.startsWith("coverage.world.") ||
            name.startsWith("coverage.simulation.")
        ) {
            return "dynamics"
        }
        if (name.startsWith("geometry.") || name.startsWith("coverage.geometry.")) return "geometry"
        val originals = (case["originals"] as? JsonArray)?.mapNotNull { Py.str(it) } ?: emptyList()
        if (name.startsWith("coverage.Upstream") && originals.isNotEmpty() &&
            originals.all { it.startsWith("org.dyn4j.geometry.") }
        ) {
            return "geometry"
        }
        if (name.startsWith("coverage.") || name.startsWith("UpstreamAVLTree")) return "compatibility"
        throw IllegalArgumentException("unclassified corpus case: $name")
    }

    /** `read_corpus`: the tracked production corpus must reproduce the working tree and map. */
    fun readCorpus(repository: Path): Pair<JsonObject, JsonObject> {
        val raw = Files.readAllBytes(repository.resolve(CORPUS_PATH))
        val corpus = StrictJsonLike.parse(raw) as JsonObject
        if (Py.str(corpus["kind"]) != "full-common-corpus" || Py.str(corpus["policy"]) != "production") {
            throw IllegalArgumentException("production common corpus is required")
        }
        val counts = corpus["counts"] as? JsonObject ?: JsonObject(emptyMap())
        val expectedCounts = listOf(
            "total_methods" to 2526L, "mapped_original_methods" to 2253L,
            "mapped_original_identities" to 2353L,
            "related_supplemental_methods" to 5L,
            "jvm_only_original_identities" to 32L,
            "supplemental_methods" to 270L,
            "platform_only_methods" to 3L, "unresolved_mappings" to 0L,
        )
        if (expectedCounts.any { (key, value) -> !Py.equalsInt(counts[key], value) }) {
            throw IllegalArgumentException("frozen common corpus counts differ")
        }
        val sourceFiles = (corpus["source_files"] as? JsonArray)?.mapNotNull { it as? JsonObject } ?: emptyList()
        val scannedFiles = CorpusFiles.scanTestTree(repository)
        if (sourceFiles.size != 202 || sourceFiles != scannedFiles) {
            throw IllegalArgumentException("common test source hash differs")
        }
        val scanned = CorpusFiles.scanSources(repository)
        val indexed = LinkedHashMap<Triple<String, String, String>, CorpusCase>()
        for (case in scanned) indexed[Triple(case.module, case.classname, case.method)] = case
        val cases = corpus["cases"] as? JsonArray ?: JsonArray(emptyList())
        if (indexed.size != 2526 || cases.size != 2526) {
            throw IllegalArgumentException("common test source inventory differs")
        }
        for (element in cases) {
            val case = element as JsonObject
            val key = Triple(
                Py.str(case["module"])!!, Py.str(case["classname"])!!, Py.str(case["method"])!!,
            )
            val observed = indexed[key]
                ?: throw IllegalArgumentException("common test source identity differs: $key")
            for (field in listOf("source_set", "path", "sha256", "line", "hosts")) {
                val want = case[field]
                val got = when (field) {
                    "source_set" -> JsonPrimitive(observed.sourceSet)
                    "path" -> JsonPrimitive(observed.path)
                    "sha256" -> JsonPrimitive(observed.sha256)
                    "line" -> JsonPrimitive(observed.line)
                    else -> JsonArray(observed.hosts.map { JsonPrimitive(it) })
                }
                if (want != got) throw IllegalArgumentException("common test source identity differs: $key")
            }
        }
        if (FullCorpus.sourceTreeDigest(scannedFiles) != Py.str(corpus["source_tree_sha256"])) {
            throw IllegalArgumentException("common test source tree differs")
        }
        val mapRaw = Files.readAllBytes(repository.resolve(FullCorpus.MAP_PATH))
        val mapRows = CorpusTsv.read(mapRaw)
        if (JsonArray(mapRows) != corpus["original_mappings"] || mapRows.size != 2385) {
            throw IllegalArgumentException("reviewed original map differs")
        }
        val pairRaw = Files.readAllBytes(repository.resolve(FullCorpus.PAIR_PATH))
        if (CorpusFiles.digest(pairRaw) != FullCorpus.REVIEWED_PAIRS_SHA256 ||
            !pairRaw.contentEquals(FullCorpus.pairedBytes(mapRows))
        ) {
            throw IllegalArgumentException("independently reviewed pair map differs")
        }
        val jvmOnly = (corpus["jvm_only"] as? JsonArray)?.mapNotNull { it as? JsonObject } ?: emptyList()
        val mappedJvmOnly = mapRows.filter { Py.str(it["disposition"]) == "JVM_ONLY" }
            .mapNotNull { Py.str(it["original"]) }.toSet()
        if (jvmOnly.size != 32 ||
            jvmOnly.mapNotNull { Py.str(it["original"]) }.toSet() != mappedJvmOnly
        ) {
            throw IllegalArgumentException("JVM-only original dispositions differ")
        }
        if (FullCorpus.makeManifest(scanned, mapRows, production = true, sourceFiles = scannedFiles) != corpus) {
            throw IllegalArgumentException("common corpus case or original disposition differs")
        }
        val bindings = buildJsonObject {
            put("corpus_sha256", JsonPrimitive(CorpusFiles.digest(raw)))
            put("source_tree_sha256", JsonPrimitive(Py.str(corpus["source_tree_sha256"])!!))
            put("original_map_sha256", JsonPrimitive(CorpusFiles.digest(mapRaw)))
            put("reviewed_pairs_sha256", JsonPrimitive(CorpusFiles.digest(pairRaw)))
            put("original_revision", JsonPrimitive(FullCorpus.ORIGINAL_REVISION))
        }
        return corpus to bindings
    }

    /** `build_manifest`: the reviewed complete-port suite. */
    fun buildManifest(repository: Path): JsonObject {
        val (corpus, bindings) = readCorpus(repository)
        for (paths in GATE_SOURCES.values) {
            for (path in paths) {
                if (!Files.isRegularFile(repository.resolve(path))) {
                    throw IllegalArgumentException("independent gate source is absent")
                }
            }
        }
        val cases = mutableListOf<JsonObject>()
        for (element in corpus["cases"] as JsonArray) {
            val source = element as JsonObject
            val scope = if (Py.str(source["source_set"]) == "commonTest") "portable" else "jvm-only"
            cases.add(
                buildJsonObject {
                    put(
                        "id",
                        JsonPrimitive(
                            "${Py.str(source["module"])}:${Py.str(source["classname"])}#${Py.str(source["method"])}",
                        ),
                    )
                    put("module", source.getValue("module"))
                    put("classname", source.getValue("classname"))
                    put("method", source.getValue("method"))
                    put("area", JsonPrimitive(areaFor(source)))
                    put("scope", JsonPrimitive(scope))
                    put("kind", source.getValue("kind"))
                    put(
                        "source",
                        buildJsonObject {
                            for (key in listOf("path", "sha256", "line")) {
                                put(key, source.getValue(key))
                            }
                        },
                    )
                    put("originals", source.getValue("originals"))
                },
            )
        }
        cases.sortWith { left, right -> CanonicalText.compare(Py.str(left["id"])!!, Py.str(right["id"])!!) }
        val targets = LinkedHashMap<String, JsonObject>()
        for (row in Qualification.matrix()) {
            targets[row.target] = buildJsonObject {
                put(
                    "case_scopes",
                    JsonArray(
                        (if (row.target == "jvm") listOf("portable", "jvm-only") else listOf("portable"))
                            .map { JsonPrimitive(it) },
                    ),
                )
            }
        }
        val lanes = LinkedHashMap<String, JsonObject>()
        for (lane in Qualification.expand()) {
            lanes[lane.id] = buildJsonObject {
                put("target", JsonPrimitive(lane.target))
                put("runtime", JsonPrimitive(lane.runtime))
                put("version", JsonPrimitive(lane.version))
                put("configuration", JsonPrimitive(lane.configuration))
                put("case_scopes", targets.getValue(lane.target).getValue("case_scopes"))
                put(
                    "required_gates",
                    JsonArray(
                        (LANE_GATES + (if (lane.target == "jvm") JVM_GATES else emptyList()))
                            .map { JsonPrimitive(it) },
                    ),
                )
            }
        }
        val gates = buildJsonObject {
            for ((name, requirement) in GATE_DESCRIPTIONS) {
                put(
                    name,
                    buildJsonObject {
                        put("requirement", JsonPrimitive(requirement))
                        put(
                            "evidence_sources",
                            JsonArray((GATE_SOURCES[name] ?: emptyList()).map { JsonPrimitive(it) }),
                        )
                    },
                )
            }
        }
        return buildJsonObject {
            put("schema", JsonPrimitive(1))
            put("kind", JsonPrimitive("complete-port"))
            put("id", JsonPrimitive("full-common-0681a8cd"))
            put("areas", JsonArray(AREA_IDS.map { JsonPrimitive(it) }))
            put("bindings", bindings)
            put("cases", JsonArray(cases))
            put("targets", JsonObject(targets))
            put("lanes", JsonObject(lanes))
            put("independent_gates", gates)
            put("global_gates", JsonArray(GLOBAL_GATES.map { JsonPrimitive(it) }))
            put(
                "counts",
                buildJsonObject {
                    put("portable_methods", JsonPrimitive(2523))
                    put("jvm_only_facade_methods", JsonPrimitive(3))
                    put("mapped_original_identities", JsonPrimitive(2353))
                    put("body_related_supplements", JsonPrimitive(5))
                    put("jvm_only_original_dispositions", JsonPrimitive(32))
                },
            )
        }
    }

    /** `validate_manifest`: the tracked manifest must be exactly the derived one. */
    fun validateManifest(manifest: JsonElement?, repository: Path): Boolean {
        if (manifest !is JsonObject) {
            throw IllegalArgumentException("complete suite manifest must be an object")
        }
        val expected = buildManifest(repository)
        if (manifest != expected) {
            throw IllegalArgumentException(
                "complete suite differs from reviewed cases, lanes, bindings, or gates",
            )
        }
        val cases = manifest["cases"] as? JsonArray ?: JsonArray(emptyList())
        val identities = cases.map { Py.str((it as JsonObject)["id"]) }
        if (identities.size != identities.toSet().size) {
            throw IllegalArgumentException("duplicate complete suite case")
        }
        val areas = (manifest["areas"] as? JsonArray)?.mapNotNull { Py.str(it) }?.toSet() ?: emptySet()
        val caseAreas = cases.mapNotNull { Py.str((it as JsonObject)["area"]) }.toSet()
        if (areas != caseAreas) throw IllegalArgumentException("complete suite area is empty")
        return true
    }

    /** `select_lane`: the case identities and gates one lane must run. */
    fun selectLane(manifest: JsonObject, laneId: String?, repository: Path): JsonObject {
        validateManifest(manifest, repository)
        val lanes = manifest["lanes"] as? JsonObject ?: JsonObject(emptyMap())
        if (laneId == null || laneId !in lanes) {
            throw IllegalArgumentException("unknown required lane: $laneId")
        }
        val lane = lanes.getValue(laneId) as JsonObject
        val scopes = (lane["case_scopes"] as? JsonArray)?.mapNotNull { Py.str(it) } ?: emptyList()
        val selected = (manifest["cases"] as JsonArray).mapNotNull { element ->
            val case = element as JsonObject
            if (Py.str(case["scope"]) in scopes) Py.str(case["id"]) else null
        }
        if (selected.isEmpty() || selected.size != selected.toSet().size) {
            throw IllegalArgumentException("empty or duplicate selected suite")
        }
        return buildJsonObject {
            put("lane_id", JsonPrimitive(laneId))
            put("case_ids", JsonArray(selected.map { JsonPrimitive(it) }))
            put("required_gates", lane.getValue("required_gates"))
            put("global_gates", manifest.getValue("global_gates"))
        }
    }

    /** The corpus JSON is read strictly: a repeated key would change what the manifest binds. */
    private object StrictJsonLike {
        fun parse(raw: ByteArray): JsonElement =
            StrictObjectJson.parse(raw.toString(StandardCharsets.UTF_8))
    }
}
