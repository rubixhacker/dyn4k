package io.github.rubixhacker.harness.performance

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put

/** `tools/performance/analyze_candidates.py`: pilot indexes and short-window intervals. */
object AnalyzeCandidates {
    /**
     * `analyze_candidates.summarize_pilot`: one entry per workload and repeat, keyed by family,
     * variant, size, rate, mode, and repeat, holding each route's observation.
     */
    fun summarizePilot(evidence: JsonObject): JsonObject {
        val grouped = sortedMapOf<String, MutableMap<String, JsonObject>>()
        val results = evidence["results"]?.let { it as? JsonArray } ?: JsonArray(emptyList())
        for (element in results) {
            val item = element.jsonObject
            val raw = item.str("raw")
            val repeat = raw.substringAfterLast('r').substringBefore('.')
            val key = listOf(
                item.str("family"),
                item.str("variant"),
                item.str("size"),
                "${item.int("hz")}hz",
                item.str("mode"),
                "repeat$repeat",
            ).joinToString(".")
            grouped.getOrPut(key) { linkedMapOf() }[item.str("api")] = buildJsonObject {
                put("median_step_ns", item.getValue("median_step_ns"))
                put("p99_step_ns", item.getValue("p99_step_ns"))
                put("total_allocation_bytes", item.getValue("total_allocation_bytes"))
                put("peak_rss_delta_bytes_diagnostic", item.getValue("peak_rss_delta_bytes"))
                put("activity", item.getValue("activity_status"))
                put("warmup", item.getValue("warmup_status"))
                put("process_pid", item.getValue("process_pid"))
                put("state_checksum_sha256", item.getValue("state_checksum_sha256"))
            }
        }
        return buildJsonObject {
            for ((key, routes) in grouped) {
                put(
                    key,
                    buildJsonObject { for ((api, record) in routes) put(api, record) },
                )
            }
        }
    }

    /**
     * `analyze_candidates.exploratory_intervals`: median, p99, and total intervals for the two
     * candidate routes against the unchanged baseline, plus the shim against direct Kotlin.
     * [samples] resolves a recorded raw file name to its parsed rows.
     */
    fun exploratoryIntervals(
        evidence: JsonObject,
        samples: (String) -> List<Map<String, String?>>,
    ): JsonObject {
        data class GroupKey(val family: String, val variant: String, val size: String, val hz: Int)

        val grouped = linkedMapOf<GroupKey, MutableMap<String, JsonObject>>()
        val results = evidence["results"]?.let { it as? JsonArray } ?: JsonArray(emptyList())
        for (element in results) {
            val item = element.jsonObject
            val mode = item["mode"]
            if (mode == null || mode == JsonNull || mode.jsonPrimitive.content != "timing") continue
            val key = GroupKey(
                item.str("family"),
                item.str("variant"),
                item.str("size"),
                item.int("hz"),
            )
            grouped.getOrPut(key) { linkedMapOf() }[item.str("api")] = item
        }
        val output = buildJsonObject {
            for ((key, routes) in grouped) {
                if (routes.keys != setOf("baseline", "direct_kotlin", "compatibility")) continue
                val case = listOf(key.family, key.variant, key.size, "${key.hz}hz").joinToString(".")
                put(
                    case,
                    buildJsonObject {
                        val baseline = samples(routes.getValue("baseline").str("raw"))
                        for (api in listOf("direct_kotlin", "compatibility")) {
                            val candidate = samples(routes.getValue(api).str("raw"))
                            put(
                                api,
                                buildJsonObject {
                                    for (metric in listOf("median", "p99", "total")) {
                                        put(metric, Analyze.bootstrapRatio(baseline, candidate, key.hz, metric).toJson())
                                    }
                                    put("activity", routes.getValue(api).getValue("activity_status"))
                                    put("warmup", routes.getValue(api).getValue("warmup_status"))
                                    put("qualification", "unpassed_short_warmup_and_uncalibrated_host")
                                },
                            )
                        }
                        val direct = samples(routes.getValue("direct_kotlin").str("raw"))
                        val shim = samples(routes.getValue("compatibility").str("raw"))
                        put(
                            "compatibility_vs_direct",
                            buildJsonObject {
                                for (metric in listOf("median", "p99", "total")) {
                                    put(metric, Analyze.bootstrapRatio(direct, shim, key.hz, metric).toJson())
                                }
                                put("qualification", "unpassed_short_warmup_and_uncalibrated_host")
                            },
                        )
                    },
                )
            }
        }
        return output
    }
}
