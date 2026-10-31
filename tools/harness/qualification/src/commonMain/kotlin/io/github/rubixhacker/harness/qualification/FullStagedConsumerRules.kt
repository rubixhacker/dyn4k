package io.github.rubixhacker.harness.qualification

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/** One bounded class contract: its case identities, source path, and source digest. */
data class StagedClassContract(
    val ids: Set<String>,
    val source: String,
    val sourceHash: String,
)

/**
 * `full_staged_consumer.py`'s pure half: the bounded class contract and the staged graph line.
 *
 * The archive, XML, process, and inventory work is in `FullStagedConsumer` on the JVM side.
 */
object FullStagedConsumerRules {
    const val CLASS = "org.dyn4j.geometry.Vector2NormalizationParityTest"
    const val LANE = "jvm:Java:current:default"
    const val VERSION = "0.1.0-alpha.1"
    const val GROUP = "io.github.rubixhacker"

    val MODULES: List<String> = listOf("dyn4k-core", "dyn4k")

    /** The one approved original source of the bounded class. */
    const val SOURCE =
        "dyn4k-core/src/commonTest/kotlin/org/dyn4j/geometry/Vector2NormalizationParityTest.kt"

    /**
     * `class_contract`: the approved cases of one class, its single source path, and that source's
     * committed digest.
     */
    fun classContract(
        selected: JsonArray,
        classname: String,
    ): StagedClassContract {
        val cases = selected.mapNotNull { it as? JsonObject }
            .filter { Py.str(it["classname"]) == classname }
        val identities = cases.mapNotNull { Py.str(it["id"]) }
        if (cases.isEmpty() || identities.toSet().size != identities.size) {
            throw IllegalArgumentException("original class cases are missing or duplicated")
        }
        val sources = cases.map { item ->
            val source = item["source"] as? JsonObject
            (Py.str(source?.get("path")) ?: "") to (Py.str(source?.get("sha256")) ?: "")
        }.toSet()
        if (sources.size != 1) {
            throw IllegalArgumentException("original class source identity differs")
        }
        val (source, sourceHash) = sources.single()
        if (source != SOURCE || !Py.SHA64.matches(sourceHash) ||
            cases.any {
                Py.str(it["module"]) != "dyn4k-core" ||
                    Py.str(it["id"]) != "dyn4k-core:$classname#${Py.str(it["method"])}"
            }
        ) {
            throw IllegalArgumentException("original class is outside the bounded staged route")
        }
        return StagedClassContract(identities.toSet(), source, sourceHash)
    }

    /** `graph_from_output`: exactly one `DYN4K_FULL_SUITE_GRAPH=` line, parsed strictly. */
    fun graphFromOutput(output: String): JsonObject {
        val prefix = "DYN4K_FULL_SUITE_GRAPH="
        val lines = output.lines().filter { it.startsWith(prefix) }.map { it.removePrefix(prefix) }
        if (lines.size != 1) {
            throw IllegalArgumentException(
                "external staged graph observation is missing or duplicate",
            )
        }
        return StrictObjectJson.parse(lines[0]) as? JsonObject
            ?: throw IllegalArgumentException(
                "external staged graph observation is missing or duplicate",
            )
    }

    /** `staged_binary`: one staged JVM artifact path. */
    fun stagedBinaryName(module: String): String = "$module-jvm-$VERSION.jar"

    /** `sorted(item["id"] ...)` over a consumer contract's cases. */
    fun caseIds(contract: JsonObject): List<String> =
        (contract["cases"] as JsonArray).mapNotNull { Py.str((it as JsonObject)["id"]) }.sorted()
}
