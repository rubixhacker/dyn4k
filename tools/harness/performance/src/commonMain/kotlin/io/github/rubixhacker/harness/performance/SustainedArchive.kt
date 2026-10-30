package io.github.rubixhacker.harness.performance

import io.github.rubixhacker.harness.contract.CanonicalJson
import io.github.rubixhacker.harness.contract.Sha256
import io.github.rubixhacker.harness.contract.StrictJson
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import okio.ByteString.Companion.encodeUtf8
import okio.ByteString.Companion.toByteString

/** `tools/performance/sustained_archive.py`: the sustained-archive contract and its key sets. */
object SustainedArchive {
    val modes: List<String> = listOf("timing", "allocation", "memory")
    val routes: List<String> = listOf("baseline", "direct_kotlin", "compatibility")

    val stepFields: List<String> = Measure.stepFields
    val memoryFields: List<String> = listOf(
        "phase", "step", "managed_bytes", "native_bytes", "wasm_linear_bytes",
        "attributed_workload_bytes",
    )
    val resourceFields: List<String> = listOf(
        "phase", "step", "heap_used_bytes", "rss_bytes", "allocation_bytes",
    )
    val clockFields: List<String> = listOf("step", "begin_ns", "end_ns")
    val warmupClockFields: List<String> = listOf("warmup_step", "begin_ns", "end_ns")
    val plateauFields: List<String> = listOf(
        "cycle", "heap_after_collection_bytes", "rss_after_collection_bytes", "collection_count",
        "managed_bytes", "native_bytes", "wasm_linear_bytes", "attributed_workload_bytes",
        "reserved_runtime_bytes",
    )
    val stressMonitorFields: List<String> = listOf("elapsed_ns", "rss_bytes", "action")

    val processImageMethods: Map<String, String> = mapOf(
        "Linux" to "os_procfs",
        "Darwin" to "macos_libproc",
        "Windows" to "windows_query_image",
    )

    const val FROZEN_MANIFEST_SHA256: String =
        "18cca97bbf1fc939eda669efe2344bbfe06c416a735ca8cc5184d5ba2519176a"

    /** `sustained_archive.canonical`: Python's sorted, compact, NaN-free JSON as UTF-8 bytes. */
    fun canonical(value: JsonElement): ByteArray = CanonicalJson.render(value).encodeToByteArray()

    /** `sustained_archive.signature`: HMAC-SHA256 over the canonical record without its signature. */
    fun signature(index: JsonObject, key: ByteArray): String {
        val unsigned = buildJsonObject {
            for ((name, value) in index) if (name != "signature") put(name, value)
        }
        return CanonicalJson.render(unsigned).encodeUtf8().hmacSha256(key.toByteString()).hex()
    }

    /**
     * `sustained_archive.frozen_policy`: the checked-in manifest must hash to the independently
     * frozen digest, validate, and equal the generator's output.
     */
    fun frozenPolicy(manifestBytes: ByteArray): JsonObject {
        if (Sha256.of(manifestBytes) != FROZEN_MANIFEST_SHA256) {
            throw IllegalArgumentException("independently frozen manifest digest differs")
        }
        val generated = PerformanceManifest.manifest()
        val checkedIn = StrictJson.load(manifestBytes.decodeToString()).jsonObject
        PerformanceManifest.validate(generated)
        PerformanceManifest.validate(checkedIn)
        if (generated != checkedIn) {
            throw IllegalArgumentException("checked-in performance manifest differs from generator")
        }
        return generated
    }

    /** A sustained key: the runtime row, scenario, mode, and repeat, plus the noise side. */
    fun keyText(vararg parts: Any?): String = parts.joinToString("|")

    /** `sustained_archive.required_measurements`: every non-stress gate case for every runtime row. */
    fun requiredMeasurements(policy: JsonObject): Set<String> {
        val output = linkedSetOf<String>()
        val scenarios = policy.getValue("scenarios").jsonArray.map { it.jsonObject }
            .filter { it.str("size") != "stress" }
        val repetitions = 1..policy.getValue("sustained").jsonObject.int("fresh_process_repetitions")
        for (row in policy.getValue("runtime_rows").jsonArray.map { it.jsonObject }) {
            for (scenario in scenarios) {
                if (scenario.str("api") != "baseline" || row.str("id") == "jvm.java") {
                    for (mode in modes) for (repeat in repetitions) {
                        output.add(keyText(row.str("id"), scenario.str("id"), mode, repeat))
                    }
                }
            }
        }
        return output
    }

    /** `sustained_archive.required_reports`: the stress-size cases report once, not per repeat. */
    fun requiredReports(policy: JsonObject): Set<String> {
        val output = linkedSetOf<String>()
        for (row in policy.getValue("runtime_rows").jsonArray.map { it.jsonObject }) {
            for (scenario in policy.getValue("scenarios").jsonArray.map { it.jsonObject }) {
                if (scenario.str("size") != "stress") continue
                if (scenario.str("api") != "baseline" || row.str("id") == "jvm.java") {
                    for (mode in modes) {
                        output.add(keyText(row.str("id"), scenario.str("id"), mode, 1))
                    }
                }
            }
        }
        return output
    }

    /** `sustained_archive.required_noise`: three baseline pairs per workload, both sides each. */
    fun requiredNoise(policy: JsonObject): Set<String> {
        val output = linkedSetOf<String>()
        for (row in policy.getValue("runtime_rows").jsonArray.map { it.jsonObject }) {
            val rowId = row.str("id")
            for (scenario in policy.getValue("scenarios").jsonArray.map { it.jsonObject }) {
                if (scenario.str("size") == "stress" || scenario.str("api") != "baseline") continue
                val stem = scenario.str("id").substringBeforeLast('.')
                val scenarioId = stem + (if (rowId == "jvm.java") ".baseline" else ".direct_kotlin")
                for (mode in modes) for (repeat in 1..3) for (side in listOf("a", "b")) {
                    output.add(keyText(rowId, scenarioId, mode, repeat, side))
                }
            }
        }
        return output
    }

    /** `sustained_archive.required_plateaus`: one plateau series per runtime row and workload. */
    fun requiredPlateaus(policy: JsonObject): Set<String> {
        val output = linkedSetOf<String>()
        for (row in policy.getValue("runtime_rows").jsonArray.map { it.jsonObject }) {
            for (scenario in policy.getValue("scenarios").jsonArray.map { it.jsonObject }) {
                if (scenario.str("size") == "stress") continue
                if (scenario.str("api") != "baseline" || row.str("id") == "jvm.java") {
                    output.add(keyText(row.str("id"), scenario.str("id")))
                }
            }
        }
        return output
    }

    /**
     * `sustained_archive.comparison_control_keys`: every budget or control comparison the archive
     * must carry, named `comparison|row|scenario|mode|metric|window`.
     */
    fun comparisonControlKeys(policy: JsonObject): Set<String> {
        val output = linkedSetOf<String>()
        val scenarios = policy.getValue("scenarios").jsonArray.map { it.jsonObject }
        for (row in policy.getValue("runtime_rows").jsonArray.map { it.jsonObject }) {
            val rowId = row.str("id")
            val assignment = row.getValue("size_assignment").jsonObject
            for (scenario in scenarios) {
                if (scenario.str("size") == "stress" || scenario.str("api") == "baseline") continue
                val scenarioId = scenario.str("id")
                val comparisons = mutableListOf<String>()
                if (rowId == "jvm.java") comparisons.add("jvm_vs_dyn4j")
                if (scenario.str("api") == "compatibility") comparisons.add("shim_vs_direct")
                if (assignment.getValue(scenario.str("size")).jsonPrimitive.content != "report_only") {
                    for (window in listOf("full", "final_minute")) {
                        output.add(keyText("absolute_timing", rowId, scenarioId, "timing", "p99", window))
                        output.add(
                            keyText(
                                "absolute_memory", rowId, scenarioId, "memory",
                                "attributed_workload_peak_bytes", window,
                            ),
                        )
                    }
                }
                for (comparison in comparisons) {
                    for ((mode, metrics) in listOf(
                        "timing" to listOf("median", "p99", "total"),
                        "allocation" to listOf("total"),
                        "memory" to listOf("retained_heap_world_alive_bytes"),
                    )) {
                        val windows = if (mode == "memory") listOf("full") else listOf("full", "final_minute")
                        for (metric in metrics) for (window in windows) {
                            output.add(keyText(comparison, rowId, scenarioId, mode, metric, window))
                        }
                    }
                    output.add(
                        keyText(comparison, rowId, scenarioId, "allocation", "construction_allocated_bytes", "full"),
                    )
                }
            }
        }
        return output
    }

    /**
     * `sustained_archive.noise_limit_lookup`: per-row, per-workload, per-mode noise ceilings,
     * collapsed to the tightest limit each assignment implies.
     */
    fun noiseLimitLookup(policy: JsonObject): Map<List<String>, Double> {
        val result = linkedMapOf<List<String>, Double>()
        val gate = policy.getValue("sustained_gate").jsonObject
        for ((assignment, limitElement) in gate.getValue("noise_upper_ratio_max").jsonObject) {
            val parts = assignment.split("|")
            val limit = numberOrNull(limitElement)
                ?: throw IllegalArgumentException("noise limit is not a number: $assignment")
            val key = listOf(parts[1], parts[2].substringBeforeLast('.'), parts[3], parts[4], parts[5])
            val existing = result[key]
            result[key] = if (existing == null) limit else minOf(existing, limit)
        }
        return result
    }

    /**
     * `sustained_archive.approved_gate`: nothing qualifies until an independently approved gate
     * fixes each runtime row's harness, noise control, and stress ceiling.
     */
    fun approvedGate(policy: JsonObject): JsonObject {
        val gateElement = policy["sustained_gate"]
        if (gateElement !is JsonObject) {
            throw IllegalArgumentException(
                "unpassed policy: approved sustained harness, noise, and stress decisions are absent",
            )
        }
        val gate = gateElement
        val rows = policy.getValue("runtime_rows").jsonArray.map { it.jsonObject.str("id") }.toSet()
        val controlKeys = comparisonControlKeys(policy)
        val controls = gate["noise_controls"] as? JsonObject
        val assignments = gate["comparison_controls"] as? JsonObject
        val limits = gate["noise_upper_ratio_max"] as? JsonObject
        val mapsValid = controls != null && controls.keys == rows &&
            assignments != null && assignments.keys == controlKeys &&
            limits != null && limits.keys == controlKeys &&
            controlKeys.all { key ->
                assignments[key]?.jsonPrimitive?.content == key.split("|")[1]
            } &&
            controlKeys.all { key ->
                val limit = numberOrNull(limits.getValue(key))
                limit != null && limit.isFinite() && limit >= 1.0
            }
        if (!mapsValid) {
            throw IllegalArgumentException(
                "unpassed policy: frozen comparison control map or noise limits are absent",
            )
        }
        val stressLimits = gate["stress_limits"] as? JsonObject
        val harnesses = gate["harnesses"] as? JsonObject
        val stressValid = harnesses != null && harnesses.keys == rows &&
            stressLimits != null && stressLimits.keys == rows &&
            stressLimits.entries.all { (rowId, element) ->
                val limit = element as? JsonObject ?: return@all false
                limit.keys == setOf(
                    "row_id", "wall_stop_ns", "wall_max_ns", "rss_stop_bytes", "rss_max_bytes",
                    "rss_metric_kind", "reference_overhead_sha256", "monitor_validation_sha256",
                    "host_capacity_sha256",
                ) &&
                    limit["row_id"]?.jsonPrimitive?.content == rowId &&
                    limit["rss_metric_kind"]?.jsonPrimitive?.content in
                    setOf("peak_rss_bytes", "peak_working_set_bytes") &&
                    listOf("wall_stop_ns", "wall_max_ns", "rss_stop_bytes", "rss_max_bytes").all { name ->
                        val value = limit[name]?.jsonPrimitive?.content?.toLongOrNull()
                        value != null && value > 0
                    } &&
                    limit.longOf("wall_stop_ns") < limit.longOf("wall_max_ns") &&
                    limit.longOf("rss_stop_bytes") < limit.longOf("rss_max_bytes") &&
                    listOf(
                        "reference_overhead_sha256", "monitor_validation_sha256",
                        "host_capacity_sha256",
                    ).all { name ->
                        val value = limit[name]
                        value is JsonPrimitive && value.isString && value.content.length == 64 &&
                            value.content.all { it in "0123456789abcdef" }
                    }
            }
        if (!stressValid) {
            throw IllegalArgumentException(
                "unpassed policy: approved noise or stress ceiling is absent or invalid",
            )
        }
        val fixtureHash = Sha256.of(
            canonical(
                buildJsonObject {
                    put("fixture", policy.getValue("fixture"))
                    put("joint_parameters", policy.getValue("joint_parameters"))
                },
            ),
        )
        for ((rowId, harnessElement) in harnesses) {
            val harness = harnessElement as? JsonObject
                ?: throw IllegalArgumentException("unpassed policy: approved harness or fixture differs: $rowId")
            val prefix = harness["command_prefix"] as? JsonArray
            val ambient = harness["environment"] as? JsonObject
            val prefixParts = prefix?.map { (it as? JsonPrimitive)?.takeIf { part -> part.isString }?.content }
            val harnessValid = harness["sha256"]?.let { (it as? JsonPrimitive)?.isString == true && it.content.length == 64 } == true &&
                harness["adapter_sha256"]?.let { (it as? JsonPrimitive)?.isString == true && it.content.length == 64 } == true &&
                harness["fixture_sha256"]?.jsonPrimitive?.content == fixtureHash &&
                prefixParts != null && prefixParts.isNotEmpty() && prefixParts[0] == "{runtime}" &&
                ambient != null &&
                ambient.all { (name, value) ->
                    name.isNotEmpty() && !name.startsWith("DYN4K_") &&
                        (value as? JsonPrimitive)?.isString == true
                } &&
                prefixParts.all { it != null && it.isNotEmpty() } &&
                listOf("harness", "adapter").all { name ->
                    prefixParts.any { it != null && it.contains("{$name}") }
                } &&
                (
                    rowId != "jvm.java" ||
                        (
                            harness["sidecar_protocol"]?.jsonPrimitive?.content in setOf("jvm-v2", "legacy-v1") &&
                                prefixParts.contains("-cp") &&
                                listOf("baseline", "core", "kotlin").all { name ->
                                    prefixParts.any { it != null && it.contains("{$name}") }
                                }
                            )
                    )
            if (!harnessValid) {
                throw IllegalArgumentException("unpassed policy: approved harness or fixture differs: $rowId")
            }
            val control = controls.getValue(rowId).jsonObject
            val expectedKind = if (rowId == "jvm.java") "dyn4j_6_0_0" else "same_target_port"
            val row = policy.getValue("runtime_rows").jsonArray.map { it.jsonObject }
                .first { it.str("id") == rowId }
            val artifacts = control["artifact_sha256"] as? JsonObject
            val controlValid = control["kind"]?.jsonPrimitive?.content == expectedKind &&
                control["optimized_build"]?.jsonPrimitive?.content == row.str("optimized_build") &&
                control["source_commit"]?.let { (it as? JsonPrimitive)?.isString == true && it.content.length == 40 } == true &&
                artifacts != null && artifacts.keys == setOf("core", "kotlin") &&
                artifacts["core"]?.let { (it as? JsonPrimitive)?.isString == true && it.content.length == 64 } == true &&
                (
                    if (rowId == "jvm.java") {
                        artifacts["kotlin"]?.jsonPrimitive?.content ==
                            PerformanceManifest.BASELINE_JAR_SHA256 &&
                            artifacts["core"]?.jsonPrimitive?.content ==
                            PerformanceManifest.BASELINE_JAR_SHA256
                    } else {
                        artifacts["kotlin"]?.let {
                            (it as? JsonPrimitive)?.isString == true && it.content.length == 64
                        } == true
                    }
                    ) &&
                control["harness_sha256"]?.jsonPrimitive?.content == harness["sha256"]?.jsonPrimitive?.content &&
                control["adapter_sha256"]?.jsonPrimitive?.content == harness["adapter_sha256"]?.jsonPrimitive?.content &&
                control["runtime_sha256"]?.let { (it as? JsonPrimitive)?.isString == true && it.content.length == 64 } == true &&
                control["probe_sha256"]?.let { (it as? JsonPrimitive)?.isString == true && it.content.length == 64 } == true &&
                (
                    rowId == "jvm.java" ||
                        control["build_receipt_sha256"]?.let {
                            (it as? JsonPrimitive)?.isString == true && it.content.length == 64
                        } == true
                    )
            if (!controlValid) {
                throw IllegalArgumentException(
                    "unpassed policy: independently frozen noise control differs: $rowId",
                )
            }
        }
        return gate
    }

    /**
     * `sustained_archive.command_prefix`: expands the approved command template with the staged
     * artifact paths for one runtime row.
     */
    fun commandPrefix(
        policy: JsonObject,
        rowId: String,
        tokens: Map<String, String>,
    ): List<String> {
        val prefix = policy.getValue("sustained_gate").jsonObject
            .getValue("harnesses").jsonObject
            .getValue(rowId).jsonObject
            .getValue("command_prefix").jsonArray
        return prefix.map { part ->
            var text = part.jsonPrimitive.content
            for ((name, value) in tokens) {
                if ("{$name}" in text) text = text.replace("{$name}", value)
            }
            if (Regex("\\{[^}]*\\}").containsMatchIn(text)) {
                throw IllegalArgumentException("approved complete command template is invalid")
            }
            text
        }
    }

    /** `sustained_archive.capture_key`: the identity a captured run is filed under. */
    fun captureKey(item: JsonObject): List<String> = when (val kind = item.str("kind")) {
        "measure", "report" ->
            listOf(item.str("row_id"), item.str("scenario_id"), item.str("mode"), item.long("repeat").toString())
        "noise" ->
            listOf(
                item.str("row_id"), item.str("scenario_id"), item.str("mode"),
                item.long("repeat").toString(), item.str("side"),
            )
        "plateau" -> listOf(item.str("row_id"), item.str("scenario_id"))
        else -> throw IllegalArgumentException("unknown capture kind")
    }

    /** `sustained_archive.allocation_rows`: presents allocation bytes as an elapsed-time series. */
    fun allocationRows(rows: List<Map<String, String?>>): List<Map<String, String?>> =
        rows.map { mapOf("elapsed_ns" to it.required("allocation_bytes")) }

    /**
     * `sustained_archive.upper_within`: proves a budget comparison's 95% upper bound clears its
     * limit, in both the full run and the final minute.
     */
    fun upperWithin(
        first: List<Map<String, String?>>,
        second: List<Map<String, String?>>,
        hz: Int,
        metric: String,
        limit: Double,
        label: String,
        draws: Int,
    ): List<Pair<String, BootstrapInterval>> {
        val output = mutableListOf<Pair<String, BootstrapInterval>>()
        for ((window, a, b) in listOf(
            Triple("full", first, second),
            Triple("final_minute", first.takeLast(60 * hz), second.takeLast(60 * hz)),
        )) {
            val result = if (metric == "total" && a.all { it.channel("elapsed_ns") == 0L }) {
                if (!b.all { it.channel("elapsed_ns") == 0L }) {
                    throw IllegalArgumentException("$label $window positive allocation against zero baseline")
                }
                BootstrapInterval(1.0, 1.0, draws, 1, zeroBaseline = true)
            } else {
                Analyze.bootstrapRatio(a, b, hz, metric, draws)
            }
            if (result.upper95 > limit) {
                throw IllegalArgumentException("$label $window 95% upper bound exceeds $limit")
            }
            output.add(window to result)
        }
        return output
    }

    /** A channel that the surrounding checks have already proven to be a positive integer. */
    private fun JsonObject.longOf(name: String): Long = getValue(name).jsonPrimitive.content.toLong()
}
