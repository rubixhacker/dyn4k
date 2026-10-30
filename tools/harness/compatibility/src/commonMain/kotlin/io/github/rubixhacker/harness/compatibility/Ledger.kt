package io.github.rubixhacker.harness.compatibility

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/**
 * The ledger assembly and module-obligation checks of `tools/compatibility/ledger.py`.
 *
 * Ported: `require_baseline_test_inputs`, `declaration_inventory`, `generate`,
 * `unbound_candidate_report`, and `candidate_source_binding` (in `LedgerHost`).
 *
 * Not ported: `tracked_files`, `tracked_paths`, `tracked_sha`, `reference`, `check_evidence`,
 * `validate_module`, `validate`, and `main`. They replay git objects, the pinned baseline JAR, the
 * baseline inventory, and every review receipt.
 */
object Ledger {
    const val MODULE_SOURCE = "src/main/java/module-info.java"

    val FIXTURE_SHA256 = mapOf(
        "module-info.java" to "acc256154b37acb90c2abc9113404f585edec3e900697dfd4ef56267240ea0ce",
        "example/Main.java" to "2cd5a3ad610ccd7e1de179eefdf69d19196391438ee423e8f3eeac6c8abf391f",
    )

    val REQUIRED_KINDS: Map<String, List<String>> = linkedMapOf(
        "production" to listOf("implementation"),
        "tests" to listOf("java-test"),
        "declarations" to listOf("java-signature", "common-portable"),
    )

    val MODULE_KINDS = listOf("module-descriptor", "named-module-consumer", "java8-classpath")

    /** One declaration the ledger records, with the source file that owns it. */
    data class DeclaredSource(
        val sourceFile: String,
        val signature: String,
        val flags: List<String>?,
    )

    /** Checks the baseline run's test input hashes against the pinned test and resource files. */
    fun requireBaselineTestInputs(
        observed: JsonElement?,
        tests: Map<String, String>,
        resources: Map<String, String>,
    ) {
        val expected = tests + resources
        val actual = observed.objectOrNull()?.mapValues { it.value.textOrNull().orEmpty() }.orEmpty()
        if (observed?.objectOrNull() == null || actual != expected) {
            val missing = sortedByCodePoint(expected.keys - actual.keys)
            val extra = sortedByCodePoint(actual.keys - expected.keys)
            val changed = sortedByCodePoint(expected.keys.intersect(actual.keys).filter { expected[it] != actual[it] })
            throw IllegalArgumentException(
                "baseline test input hashes differ: missing=${pythonList(missing)}, " +
                    "extra=${pythonList(extra)}, changed=${pythonList(changed)}",
            )
        }
    }

    /**
     * Builds the declaration map the ledger keys on, reading each type's strict `javap` surface and
     * verbose class-file inventory.
     */
    fun declarationInventory(
        signatures: Map<String, String>,
        verboseSignatures: Map<String, String>,
        production: Map<String, String>,
        oracle: SurfaceOracle = BaselineOracle,
    ): Map<String, DeclaredSource> {
        val result = linkedMapOf<String, DeclaredSource>()
        for (name in sortedByCodePoint(signatures.keys)) {
            val text = signatures.getValue(name)
            val (header, members) = ExecutionProbe.declarations(
                text,
                verboseSignatures.getValue(name),
                oracle,
            )
            val compiled = COMPILED.find(text)
                ?: throw IllegalArgumentException("source owner missing: $name")
            val packagePath = name.substringBeforeLast(".").replace(".", "/")
            val sourceFile = "src/main/java/$packagePath/${compiled.groupValues[1]}"
            if (sourceFile !in production) {
                throw IllegalArgumentException("source owner absent: $name: $sourceFile")
            }
            result["$name|type"] = DeclaredSource(sourceFile, header, null)
            for ((key, member) in members) {
                val declarationKey = "$name|${key.first}|${key.second}"
                if (declarationKey in result) {
                    throw IllegalArgumentException("duplicate declaration: $declarationKey")
                }
                result[declarationKey] = DeclaredSource(sourceFile, member.signature, member.flags)
            }
        }
        return result
    }

    /** Builds the unpinned ledger from the pinned reference inventory. */
    fun generate(expected: JsonObject): JsonObject {
        val production = expected.objectOrNull("production")!!.mapValues { it.value.textOrNull().orEmpty() }
        val tests = expected.objectOrNull("tests")!!.mapValues { it.value.textOrNull().orEmpty() }
        val declarations = expected.objectOrNull("declarations")!!
        val module = expected.objectOrNull("module")!!
        val values = linkedMapOf<String, JsonElement>(
            "schema_version" to JsonPrimitive(1),
            "baseline" to moduleOf(expected, "baseline"),
            "baseline_test_counts" to (expected["baseline_test_counts"] ?: JsonNull),
            "module" to JsonObject(
                module.toMutableMap().apply {
                    put("candidate", JsonNull)
                    put("evidence", JsonArray(mutableListOf()))
                },
            ),
            "production" to JsonArray(
                production.map { (path, digest) ->
                    buildJsonObjectLedger(
                        "id" to JsonPrimitive(path),
                        "sha256" to JsonPrimitive(digest),
                        "owner_type" to JsonPrimitive(
                            path.removePrefix("src/main/java/").removeSuffix(".java").replace('/', '.'),
                        ),
                    )
                },
            ),
            "tests" to JsonArray(
                tests.map { (path, digest) ->
                    buildJsonObjectLedger(
                        "id" to JsonPrimitive(path),
                        "sha256" to JsonPrimitive(digest),
                        "owner_type" to JsonPrimitive(
                            path.removePrefix("src/test/java/").removeSuffix(".java").replace('/', '.'),
                        ),
                    )
                },
            ),
            "declarations" to JsonArray(
                declarations.entries.map { (key, value) ->
                    val tuple = value as JsonArray
                    val flags = tuple.getOrNull(2)
                    val pairs = mutableListOf<Pair<String, JsonElement>>(
                        "id" to JsonPrimitive(key),
                        "source_file" to JsonPrimitive(tuple[0].textOrNull().orEmpty()),
                        "signature" to JsonPrimitive(tuple[1].textOrNull().orEmpty()),
                    )
                    if (flags != null && flags !is JsonNull) pairs.add("flags" to flags)
                    JsonObject(linkedMapOf(*pairs.toTypedArray()))
                },
            ),
        )
        // The per-section candidate and evidence fields are appended in the Python key order.
        for (section in listOf("production", "tests", "declarations")) {
            val entries = values.getValue(section) as JsonArray
            values[section] = JsonArray(
                entries.map { element ->
                    JsonObject(
                        element.objectOrNull()!!.toMutableMap().apply {
                            put("candidate", JsonNull)
                            put("evidence", JsonArray(mutableListOf()))
                        },
                    )
                },
            )
        }
        return JsonObject(values)
    }

    /** The unpassed report `validate` returns when the requested revision is not the recorded one. */
    fun unboundCandidateReport(
        expected: JsonObject,
        source: JsonObject,
        requestedRevision: String,
        scope: String,
        reason: String,
    ): JsonObject {
        val status = if (scope == "historical") "historical-unpassed" else "invalid-unpassed"
        val obligations = mutableListOf<JsonObject>()
        for ((section, kinds) in REQUIRED_KINDS) {
            val ids = expected.objectOrNull(section)?.keys ?: emptySet()
            for (key in ids) {
                for (kind in kinds) {
                    obligations.add(obligation(section, key, kind, status, reason))
                }
            }
        }
        for (kind in MODULE_KINDS) {
            obligations.add(obligation("module", "module-info.java", kind, status, reason))
        }
        val byKind = linkedMapOf<String, JsonElement>()
        for (item in obligations) {
            val kind = item.textOrNull("kind").orEmpty()
            val bucket = linkedMapOf<String, JsonElement>()
            val existing = byKind[kind].objectOrNull()
            if (existing != null) {
                bucket.putAll(existing)
            } else {
                bucket["total"] = JsonPrimitive(0)
                bucket["passed"] = JsonPrimitive(0)
                bucket["unpassed"] = JsonPrimitive(0)
            }
            bucket["total"] = JsonPrimitive(bucket.getValue("total").integerOrNull()!! + 1)
            bucket["unpassed"] = JsonPrimitive(bucket.getValue("unpassed").integerOrNull()!! + 1)
            byKind[kind] = JsonObject(bucket)
        }
        val counts = linkedMapOf<String, JsonElement>(
            "production" to JsonPrimitive(expected.objectOrNull("production")?.size ?: 0),
            "tests" to JsonPrimitive(expected.objectOrNull("tests")?.size ?: 0),
            "declarations" to JsonPrimitive(expected.objectOrNull("declarations")?.size ?: 0),
            "module" to JsonPrimitive(1),
        )
        return JsonObject(
            linkedMapOf(
                "passed" to JsonPrimitive(false),
                "invalid" to JsonArray(listOf(JsonPrimitive(reason))),
                "gaps" to JsonArray(listOf(JsonPrimitive(reason))),
                "source_scope" to JsonPrimitive(status),
                "candidate_source_revision" to (source["revision"] ?: JsonNull),
                "requested_candidate_revision" to JsonPrimitive(requestedRevision),
                "governing_summary" to JsonNull,
                "obligation_counts" to JsonObject(
                    linkedMapOf(
                        "total" to JsonPrimitive(obligations.size),
                        "passed" to JsonPrimitive(0),
                        "unpassed" to JsonPrimitive(obligations.size),
                        "by_kind" to JsonObject(byKind),
                    ),
                ),
                "unpassed_obligations" to JsonArray(obligations),
                "missing_counterparts" to JsonNull,
                "counts" to JsonObject(counts),
            ),
        )
    }

    /** Renders a list the way Python prints it, e.g. `['a', 'b']`. */
    private fun pythonList(values: List<String>): String =
        "[" + values.joinToString(", ") { "'" + it.replace("\\", "\\\\").replace("'", "\\'") + "'" } + "]"

    private val COMPILED = Regex("""^Compiled from "([^"/]+\.java)"""", RegexOption.MULTILINE)

    private fun moduleOf(expected: JsonObject, key: String): JsonElement =
        expected[key] ?: JsonNull

    private fun obligation(
        section: String,
        id: String,
        kind: String,
        status: String,
        reason: String,
    ): JsonObject = JsonObject(
        linkedMapOf(
            "section" to JsonPrimitive(section),
            "id" to JsonPrimitive(id),
            "kind" to JsonPrimitive(kind),
            "status" to JsonPrimitive(status),
            "reason" to JsonPrimitive(reason),
        ),
    )

    private fun buildJsonObjectLedger(vararg pairs: Pair<String, JsonElement>): JsonObject =
        JsonObject(linkedMapOf(*pairs))
}
