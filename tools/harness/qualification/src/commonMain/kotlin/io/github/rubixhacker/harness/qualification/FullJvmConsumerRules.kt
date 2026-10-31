package io.github.rubixhacker.harness.qualification

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/**
 * `full_jvm_consumer.py`'s pure half: the lane table, the approved-contract shape, and the four
 * named input files.
 *
 * The inventory, the mode-publication replay, the Gradle process, and the report comparison are in
 * `FullJvmConsumer` on the JVM side.
 */
object FullJvmConsumerRules {
    val SOURCE_ROOTS: List<String> = listOf(
        "dyn4k-core/src/commonTest/kotlin", "dyn4k-core/src/jvmTest/kotlin",
        "dyn4k/src/commonTest/kotlin", "dyn4k/src/jvmTest/kotlin", "dyn4k/src/jvmTest/java",
    )

    const val CONSUMER = "consumers/qualification/portable/full-jvm"
    const val LANE_SCRIPT = "lane-script"
    const val DEFAULT_LANE = "jvm:Java:current:default"

    /** `LANES`: version × configuration, in the reference's order. */
    val LANES: List<String> = buildList {
        for (version in listOf("minimum", "current")) {
            for (configuration in listOf("no-optimize", "default")) {
                add("jvm:Java:$version:$configuration")
            }
        }
    }

    /** `lane_parts`: `(version, configuration)`. */
    fun laneParts(lane: String): Pair<String, String> {
        if (lane !in LANES) {
            throw IllegalArgumentException("unsupported full JVM lane: $lane")
        }
        val parts = lane.split(":")
        return parts[2] to parts[3]
    }

    /** `LANE_SCRIPT` bytes: the qualification project must be the consumer. */
    val LANE_SCRIPT_BYTES: ByteArray =
        ("gradle.settingsEvaluated { settings ->\n" +
            "  if (settings.rootProject.name != 'dyn4k-full-staged-jvm-consumer') {\n" +
            "    throw new GradleException('qualification project differs')\n" +
            "  }\n" +
            "}\n").toByteArray(Charsets.UTF_8)

    /**
     * `input_bytes`: the inventory, both case tables, and the lane script.
     *
     * [cases] are the approved contract cases; [sources] maps every tracked test source to its
     * committed digest.
     */
    fun inputBytes(
        cases: List<JsonObject>,
        sources: Map<String, String>,
        lane: String,
    ): Map<String, ByteArray> {
        laneParts(lane)
        val byModule = linkedMapOf<String, List<JsonObject>>()
        for (module in FullStagedConsumerRules.MODULES) {
            byModule[module] = cases.filter { Py.str(it["module"]) == module }
                .sortedWith { left, right -> CanonicalText.compare(Py.str(left["id"])!!, Py.str(right["id"])!!) }
        }
        fun table(module: String): ByteArray = buildString {
            for (item in byModule.getValue(module)) {
                append(Py.str(item["id"])).append('\t')
                    .append(Py.str(item["classname"])).append('\t')
                    .append(Py.str(item["method"])).append('\n')
            }
        }.toByteArray(Charsets.UTF_8)
        val inventory = buildString {
            for ((path, digest) in sources.toSortedMap(Comparator(CanonicalText::compare))) {
                append(path).append('\t').append(digest).append('\n')
            }
        }.toByteArray(Charsets.UTF_8)
        return linkedMapOf(
            "source-inventory.tsv" to inventory,
            "core-cases.tsv" to table("dyn4k-core"),
            "facade-cases.tsv" to table("dyn4k"),
            LANE_SCRIPT to LANE_SCRIPT_BYTES,
        )
    }

    /** The approved JVM contract shape: 2,526 cases, 2,465 core and 61 facade. */
    fun requireContract(contract: JsonObject) {
        val cases = (contract["cases"] as? JsonArray)?.map { it as JsonObject } ?: emptyList()
        val identities = cases.mapNotNull { Py.str(it["id"]) }
        if (cases.size != 2526 || identities.toSet().size != 2526 ||
            cases.count { Py.str(it["module"]) == "dyn4k-core" } != 2465 ||
            cases.count { Py.str(it["module"]) == "dyn4k" } != 61
        ) {
            throw IllegalArgumentException("approved JVM selected case contract differs")
        }
    }

    /** `selected_contract`'s digest inputs, so the caller can record them. */
    fun contractDigest(contract: JsonObject): String =
        io.github.rubixhacker.harness.contract.Sha256.ofCanonical(contract)

    /** `compiler_modes.jvm_flags`: the recorded JVM compiler flags of one mode. */
    fun jvmFlags(mode: String): List<String> = when (mode) {
        "default" -> emptyList()
        "no-optimize" -> listOf("-Xno-optimize")
        else -> throw IllegalArgumentException("unknown JVM compiler mode: $mode")
    }
}

/**
 * The pinned mode-publication replay the JVM consumer needs.
 *
 * `full_jvm_consumer.mode_publication` calls `compiler_modes.replay(...)` and
 * `compiler_modes.jvm_flags(...)` on a producing checkout. `JvmModePublication.PythonModeReplay`
 * already shells out to `compiler_modes.py`; this interface names exactly the two reachable
 * functions so the caller can supply the ported replay.
 */
interface JvmModeReplay {
    /** `compiler_modes.replay(publication, candidate, "jvm", configuration)`. */
    fun replay(publication: java.nio.file.Path, candidate: String, configuration: String): JsonObject

    /** `compiler_modes.jvm_flags(configuration)`: the exact recorded flag list. */
    fun jvmFlags(configuration: String): JsonArray
}
