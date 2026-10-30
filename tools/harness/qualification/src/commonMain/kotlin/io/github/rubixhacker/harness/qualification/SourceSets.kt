package io.github.rubixhacker.harness.qualification

import io.github.rubixhacker.harness.contract.Qualification
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject

/** Staged target binary hashes of one audit, as `qualify.target_binary_hashes` reads them. */
object TargetBinaryHashes {
    /**
     * Returns, for every matrix target, the recorded SHA-256 of each module's target binary.
     *
     * A target whose binary was not audited maps to null; the lane evidence check treats that as
     * a difference, not as absence of a field.
     */
    fun of(artifacts: JsonElement?): Map<String, Map<String, String?>> {
        val audited = mutableMapOf<String, String?>()
        if (artifacts is JsonArray) {
            for (item in artifacts) {
                if (item is JsonObject) {
                    val path = Py.str(item["path"]) ?: continue
                    audited[path] = Py.str(item["sha256"])
                }
            }
        }
        val result = LinkedHashMap<String, Map<String, String?>>()
        for (row in Qualification.matrix()) {
            val modules = LinkedHashMap<String, String?>()
            for (module in Qualification.modules) {
                modules[module] = audited[Qualification.targetBinaryPath(module, row.target)]
            }
            result[row.target] = modules
        }
        return result
    }
}

/** Source sets of `qualify.source_sets_for_publication`. */
object SourceSets {
    private val platformTargets = setOf("jvm", "android", "js", "wasmJs", "wasmWasi")

    private val platformNames = mapOf(
        "jvm" to "jvmMain",
        "android" to "androidMain",
        "js" to "jsMain",
        "wasmJs" to "wasmJsMain",
        "wasmWasi" to "wasmWasiMain",
    )

    /** Returns the source sets whose files belong in one publication's sources archive. */
    fun forPublication(module: String, target: String?): Set<String> {
        if (module == "dyn4k") return setOf("commonMain")
        val platform = if (target == null || target !in platformTargets) {
            "nativeMain"
        } else {
            platformNames.getValue(target)
        }
        return setOf("commonMain", platform)
    }
}
