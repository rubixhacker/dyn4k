package io.github.rubixhacker.harness.qualification

import io.github.rubixhacker.harness.contract.MatrixCase
import io.github.rubixhacker.harness.contract.MatrixRow
import io.github.rubixhacker.harness.contract.Qualification
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/**
 * `qualify.full_hosted_lane`: the scoped complete-lane record of one verified hosted receipt.
 *
 * The receipt's two configurations must select the *current* lanes of exactly one runtime family,
 * must carry the reviewed common case counts (2,465 core and 58 facade) and three staged consumer
 * cases, and must agree with the tracked complete suite when one is supplied.
 */
object FullHostedLane {
    private const val REVIEWED_CORE_CASES = 2465
    private const val REVIEWED_FACADE_CASES = 58
    private const val CONSUMER_CASES = 3

    fun of(
        receipt: JsonObject,
        receiptSha256: String,
        suiteManifest: JsonElement? = null,
    ): JsonObject {
        val receiptTarget = Py.str(receipt["target"])
            ?: throw IllegalArgumentException("full hosted receipt target is missing")
        val target = if (receiptTarget == "jsSafari") "js" else receiptTarget
        val matches = Qualification.matrix().filter { row ->
            row.target == target && (if (target == "js") row.runtime == "Safari" else true)
        }
        if (matches.size != 1) {
            throw IllegalArgumentException("full hosted target does not select one runtime family")
        }
        val family = matches[0]
        val runtime = receipt["runtime"] as? JsonObject
            ?: throw IllegalArgumentException("full hosted receipt runtime is missing")
        val version: String = when {
            receiptTarget == "mingwX64" -> {
                val value = Py.str(runtime["os_version"]) ?: ""
                if (!value.startsWith("10.0.26100")) {
                    throw IllegalArgumentException("full hosted Windows Server runtime differs")
                }
                value
            }
            receiptTarget == "jsSafari" -> Py.str(runtime["safari_version"]) ?: ""
            "Simulator" in receiptTarget || receiptTarget == "iosX64" -> {
                val selected = receipt["selected_simulator"] as? JsonObject
                if (selected == null || !Py.truthy(selected["udid"])) {
                    throw IllegalArgumentException("full hosted simulator observation is missing")
                }
                val simulatorFamily = Hosted.NATIVE_TARGETS[receiptTarget]?.simulator
                    ?: throw IllegalArgumentException(
                        "full hosted target does not select one runtime family",
                    )
                val declared = ((runtime["simulators"] as? JsonObject)?.get(simulatorFamily) as? JsonArray)
                    ?.toList() ?: emptyList()
                val configurations = receipt["configurations"] as? JsonArray ?: JsonArray(emptyList())
                if (declared.none { it == selected } ||
                    configurations.any {
                        Py.str((it as? JsonObject)?.get("simulator_udid")) != Py.str(selected["udid"])
                    }
                ) {
                    throw IllegalArgumentException(
                        "full hosted executed simulator differs from selected device",
                    )
                }
                val value = Py.str(selected["runtime"]) ?: ""
                if (value.isEmpty()) {
                    throw IllegalArgumentException("full hosted simulator runtime is missing")
                }
                value
            }
            else -> Py.str(runtime["os_version"]) ?: ""
        }
        if (version.isEmpty()) {
            throw IllegalArgumentException("full hosted runtime version is missing")
        }
        val cases = Qualification.expand(listOf(MatrixRow(family.target, family.runtime, family.minimum, family.kind)))
        val current = LinkedHashMap<String, String>()
        for (case in cases) {
            if (case.version == "current") current[case.configuration] = case.id
        }
        val configurations = (receipt["configurations"] as? JsonArray)?.map { it as JsonObject }
            ?: throw IllegalArgumentException("full hosted receipt configurations are missing")
        val ids = configurations.map { config ->
            current[Py.str(config["configuration"]) ?: ""]
                ?: throw IllegalArgumentException(
                    "full hosted configurations do not select distinct lanes",
                )
        }
        if (ids.toSet().size != 2) {
            throw IllegalArgumentException("full hosted configurations do not select distinct lanes")
        }
        val observedCases = mutableListOf<JsonElement>()
        for ((index, config) in configurations.withIndex()) {
            val laneId = ids[index]
            val source = config["source"] as? JsonArray
                ?: throw IllegalArgumentException(
                    "full hosted reviewed common or consumer case count differs",
                )
            val common = LinkedHashMap<String, JsonElement>()
            val counts = LinkedHashMap<String, Int>()
            for (element in source) {
                val group = element as? JsonObject ?: continue
                val module = Py.str(group["module"]) ?: continue
                common[module] = group["case_ids"] ?: JsonArray(emptyList())
                counts[module] = (group["case_ids"] as? JsonArray)?.size ?: 0
            }
            val consumerCases = ((config["consumer"] as? JsonObject)?.get("case_ids") as? JsonArray)
                ?.size ?: 0
            if (common.keys != Qualification.modules.toSet() ||
                counts["dyn4k-core"] != REVIEWED_CORE_CASES ||
                counts["dyn4k"] != REVIEWED_FACADE_CASES ||
                consumerCases != CONSUMER_CASES
            ) {
                throw IllegalArgumentException(
                    "full hosted reviewed common or consumer case count differs",
                )
            }
            val suiteIds = mutableListOf<String>()
            for ((module, caseIds) in common) {
                for (caseId in caseIds as JsonArray) {
                    Py.str(caseId)?.let { suiteIds.add("$module:$it") }
                }
            }
            suiteIds.sortWith(CanonicalText::compare)
            if (suiteManifest != null &&
                suiteIds != CompleteSuite.cases(suiteManifest, laneId).sortedWith(CanonicalText::compare)
            ) {
                throw IllegalArgumentException(
                    "full hosted common cases differ from selected complete suite lane",
                )
            }
            observedCases.add(
                JsonObject(
                    linkedMapOf(
                        "lane_id" to JsonPrimitive(laneId),
                        "configuration" to (config["configuration"] ?: JsonNull),
                        "common_case_ids" to JsonObject(common),
                        "suite_case_ids" to JsonArray(suiteIds.map { JsonPrimitive(it) }),
                        "consumer_case_ids" to (consumerCasesFor(config) ?: JsonArray(emptyList())),
                        "complete_lane_status" to JsonPrimitive("NOT_RUN"),
                    ),
                ),
            )
        }
        val identity = FullCorpus.canonicalDigest(
            kotlinx.serialization.json.buildJsonObject {
                put("runtime", runtime)
                put("runner_os", receipt["runner_os"] ?: JsonNull)
                put("runner_arch", receipt["runner_arch"] ?: JsonNull)
                put("runner_name", receipt["runner_name"] ?: JsonNull)
                put("selected_simulator", receipt["selected_simulator"] ?: JsonNull)
            },
        )
        return JsonObject(
            linkedMapOf(
                "target" to JsonPrimitive(target),
                "runtime" to JsonPrimitive(family.runtime),
                "runtime_version" to JsonPrimitive(version),
                "version" to JsonPrimitive("current"),
                "runtime_identity" to JsonPrimitive(identity),
                "configuration_lanes" to JsonArray(ids.map { JsonPrimitive(it) }),
                "observed_cases" to JsonArray(observedCases),
                "manifest_sha256" to (receipt["manifest_sha256"] ?: JsonNull),
                "source_tree_sha256" to (receipt["source_tree_sha256"] ?: JsonNull),
                "map_sha256" to (receipt["map_sha256"] ?: JsonNull),
                "reviewed_pairs_sha256" to (receipt["reviewed_pairs_sha256"] ?: JsonNull),
                "artifact_hashes" to (receipt["artifact_hashes"] ?: JsonNull),
                "receipt_sha256" to JsonPrimitive(receiptSha256),
                "status" to JsonPrimitive("FULL_COMMON_PASSED"),
                "reason" to JsonPrimitive(
                    "reviewed common corpus and bounded staged consumer only",
                ),
            ),
        )
    }

    private fun consumerCasesFor(config: JsonObject): JsonElement? =
        (config["consumer"] as? JsonObject)?.get("case_ids")
}
