package io.github.rubixhacker.harness.qualification

import io.github.rubixhacker.harness.contract.Qualification
import io.github.rubixhacker.harness.contract.Sha256
import io.github.rubixhacker.harness.contract.StrictJson
import java.nio.file.Path
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/**
 * `qualify.validate_complete_suite_bindings`.
 *
 * The frozen complete suite is only usable when it still names exactly the reviewed corpus: the
 * same cases, scopes, originals, per-case source positions, 112 lane identities, and independent
 * gates, and when its own digest equals the independently reviewed seal.
 */
object SuiteBindings {
    /** Mirrors `full_corpus.MANIFEST_PATH`. */
    const val MANIFEST_PATH = "tools/qualification/full-common-corpus.json"

    /** Mirrors `full_corpus.MAP_PATH`. */
    const val MAP_PATH = "tools/qualification/full-common-original-map.tsv"

    /** Mirrors `full_corpus.PAIR_PATH`. */
    const val PAIR_PATH = "tools/qualification/full-common-reviewed-pairs.tsv"

    /** Mirrors `full_corpus.ORIGINAL_REVISION`. */
    const val ORIGINAL_REVISION = "058bf6d982a0fb89b54050f929f6ea9dae53b714"

    /** Mirrors `qualify.APPROVED_COMPLETE_SUITE_SHA256`. */
    const val APPROVED_COMPLETE_SUITE_SHA256 =
        "9aa2f50dd3c38129a70f4ed042f2b7ae5a90d4234def40d70520aad13f36b3fc"

    fun validate(suiteManifest: JsonElement?, repository: Path) {
        val manifest = suiteManifest as? JsonObject
        if (manifest == null ||
            Py.str(manifest["kind"]) != "complete-port" ||
            !Py.equalsInt(manifest["schema"], 1)
        ) {
            throw IllegalArgumentException("complete suite manifest identity is invalid")
        }
        val corpus = StrictJson.load(Fs.readText(repository.resolve(MANIFEST_PATH))) as JsonObject
        val expected = JsonObject(
            linkedMapOf(
                "corpus_sha256" to JsonPrimitive(Fs.digest(repository.resolve(MANIFEST_PATH))),
                "source_tree_sha256" to (corpus["source_tree_sha256"] ?: throw KeyNotFoundException()),
                "original_map_sha256" to JsonPrimitive(Fs.digest(repository.resolve(MAP_PATH))),
                "reviewed_pairs_sha256" to JsonPrimitive(Fs.digest(repository.resolve(PAIR_PATH))),
                "original_revision" to JsonPrimitive(ORIGINAL_REVISION),
            ),
        )
        val bindings = manifest["bindings"]
        if (bindings !is JsonObject || bindings != expected) {
            throw IllegalArgumentException("complete suite reviewed corpus binding differs")
        }
        if (Py.str(corpus["policy"]) != "production" || Py.truthy(corpus["unresolved"])) {
            throw IllegalArgumentException("complete suite reviewed corpus is unresolved")
        }

        val cases = manifest["cases"]
        val corpusCases = corpus["cases"]
        if (cases !is JsonArray || corpusCases !is JsonArray || cases.size != corpusCases.size) {
            throw IllegalArgumentException("complete suite case inventory differs from reviewed corpus")
        }
        val byId = LinkedHashMap<String?, JsonObject>()
        for (item in cases) if (item is JsonObject) byId[Py.str(item["id"])] = item
        if (byId.size != cases.size) {
            throw IllegalArgumentException("complete suite has duplicate case identities")
        }
        for (sourceElement in corpusCases) {
            val source = sourceElement as? JsonObject ?: throw KeyNotFoundException()
            val module = source["module"] ?: throw KeyNotFoundException()
            val classname = source["classname"] ?: throw KeyNotFoundException()
            val method = source["method"] ?: throw KeyNotFoundException()
            val identity = "${Py.str(module)}:${Py.str(classname)}#${Py.str(method)}"
            val item = byId[identity]
            val scope = if (Py.str(source["source_set"]) == "commonTest") "portable" else "jvm-only"
            val expectedSource = JsonObject(
                linkedMapOf(
                    "path" to (source["path"] ?: throw KeyNotFoundException()),
                    "sha256" to (source["sha256"] ?: throw KeyNotFoundException()),
                    "line" to (source["line"] ?: throw KeyNotFoundException()),
                ),
            )
            if (item == null ||
                Py.str(item["scope"]) != scope ||
                item["module"] != module ||
                item["classname"] != classname ||
                item["method"] != method ||
                item["kind"] != source["kind"] ||
                item["originals"] != source["originals"] ||
                item["source"] != expectedSource
            ) {
                throw IllegalArgumentException("complete suite case differs from reviewed corpus: $identity")
            }
        }

        val counts = manifest["counts"] as? JsonObject
        val portable = cases.count { Py.str((it as? JsonObject)?.get("scope")) == "portable" }
        val jvmOnly = cases.count { Py.str((it as? JsonObject)?.get("scope")) == "jvm-only" }
        if (portable != 2523 ||
            jvmOnly != 3 ||
            !Py.equalsInt(counts?.get("portable_methods"), 2523) ||
            !Py.equalsInt(counts?.get("jvm_only_facade_methods"), 3)
        ) {
            throw IllegalArgumentException("complete suite reviewed method counts differ")
        }

        val lanes = manifest["lanes"]
        val expectedLanes = Qualification.expand(Qualification.matrix())
        if (lanes !is JsonObject || lanes.keys != expectedLanes.map { it.id }.toSet()) {
            throw IllegalArgumentException("complete suite 112 lane identities differ")
        }
        val independent = manifest["independent_gates"]
        val globalGates = manifest["global_gates"]
        if (independent !is JsonObject || independent.isEmpty() ||
            globalGates !is JsonArray || globalGates.isEmpty() ||
            globalGates.size != globalGates.toSet().size ||
            !globalGates.all { Py.str(it) != null } ||
            !independent.keys.containsAll(globalGates.map { Py.str(it)!! })
        ) {
            throw IllegalArgumentException("complete suite independent gate inventory is invalid")
        }

        for (case in expectedLanes) {
            val lane = lanes[case.id] as? JsonObject
            val requiredScopes = if (case.target == "jvm") listOf("portable", "jvm-only") else listOf("portable")
            val scopes = (lane?.get("case_scopes") as? JsonArray)?.map { Py.str(it) }
            val gates = (lane?.get("required_gates") as? JsonArray)?.map { Py.str(it) }
            if (lane == null ||
                Py.str(lane["target"]) != case.target ||
                Py.str(lane["runtime"]) != case.runtime ||
                Py.str(lane["version"]) != case.version ||
                Py.str(lane["configuration"]) != case.configuration ||
                scopes != requiredScopes ||
                gates == null ||
                gates.isEmpty() ||
                gates.any { it == null } ||
                gates.toSet().size != gates.size ||
                !independent.keys.containsAll(gates.map { it!! })
            ) {
                throw IllegalArgumentException("complete suite lane contract differs: ${case.id}")
            }
            CompleteSuite.cases(manifest, case.id)
        }
        if (Sha256.ofCanonical(manifest) != APPROVED_COMPLETE_SUITE_SHA256) {
            throw IllegalArgumentException("complete suite differs from independently reviewed manifest")
        }
    }
}

/** Stands in for Python's `KeyError` on a required corpus field. */
class KeyNotFoundException : Exception("required manifest field is missing")
