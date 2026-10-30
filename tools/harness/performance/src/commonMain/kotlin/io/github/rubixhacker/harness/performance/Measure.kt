package io.github.rubixhacker.harness.performance

import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/** `tools/performance/measure.py`: the raw step protocol, its validation, and its summaries. */
object Measure {
    /** The channels every measured step carries. */
    val stepFields: List<String> = listOf(
        "step", "elapsed_ns", "mutation_ns", "lateness_ns", "allocation_bytes",
        "heap_used_bytes", "rss_bytes", "rss_delta_bytes", "body_count", "joint_count",
        "awake_count", "linear_speed_sum_m_per_s", "angular_speed_sum_rad_per_s",
        "contact_begins", "contact_ends", "toi_events", "broadphase_candidates",
        "active_contact_pairs", "active_contact_points",
    )

    /** The pilot workloads, in the approved order. */
    val pilot: List<Pair<String, String>> = listOf(
        "separated" to "default",
        "pile" to "default",
        "joint" to "mixed_all_types",
        "ccd" to "default",
        "lifecycle" to "wake",
        "lifecycle" to "replace",
    )

    /** `measure.balanced_orders`: every API occupies each run position once. */
    fun balancedOrders(): List<List<String>> = listOf(
        listOf("baseline", "direct_kotlin", "compatibility"),
        listOf("direct_kotlin", "compatibility", "baseline"),
        listOf("compatibility", "baseline", "direct_kotlin"),
    )

    /**
     * `measure.validate_csv`: rejects a raw step table that is incomplete, reordered, or carries
     * an impossible channel value. Returns the rows on success.
     */
    fun validateCsv(
        table: CsvTable,
        family: String,
        variant: String,
        size: String,
        hz: Int,
        steps: Int,
        mode: String,
    ): List<Map<String, String?>> {
        val header = table.fieldNames ?: emptyList()
        if (!header.containsAll(stepFields)) throw IllegalArgumentException("raw CSV lacks required channels")
        val rows = table.rows
        if (rows.size != steps || rows.map { it.channel("step") } != (0 until steps).map { it.toLong() }) {
            throw IllegalArgumentException("missing or reordered raw step samples")
        }
        val count = PerformanceManifest.sizes.getValue(family).getValue(size)
        val static = when (family) {
            "pile", "lifecycle" -> 1
            "ccd" -> 2
            "joint" -> count
            else -> 0
        }
        if (rows.any { it.channel("body_count") != (count + static).toLong() }) {
            throw IllegalArgumentException("body count changed unexpectedly")
        }
        if (rows.any { it.channel("elapsed_ns") <= 0 }) {
            throw IllegalArgumentException("nonpositive elapsed step time")
        }
        for (row in rows) {
            val elapsed = row.channel("elapsed_ns")
            val mutation = row.channel("mutation_ns")
            if (mutation < 0 || mutation > elapsed) throw IllegalArgumentException("invalid mutation_ns")
            if (row.channel("lateness_ns") < 0) throw IllegalArgumentException("invalid lateness_ns")
            val allocated = row.channel("allocation_bytes")
            if (allocated < 0 && (mode != "timing" || allocated != -1L)) {
                throw IllegalArgumentException("invalid allocation_bytes")
            }
            if (mode == "timing" && allocated != -1L) {
                throw IllegalArgumentException("timing allocation_bytes sentinel differs")
            }
            if (row.channel("heap_used_bytes") < 0 || row.channel("rss_bytes") < 0) {
                throw IllegalArgumentException("invalid heap_used_bytes or rss_bytes")
            }
            if (row.channel("awake_count") < 0 || row.channel("awake_count") > count) {
                throw IllegalArgumentException("invalid awake_count")
            }
            for (field in listOf("contact_begins", "contact_ends", "toi_events")) {
                if (row.channel(field) < 0) throw IllegalArgumentException("invalid $field")
            }
            val sampled = row.channel("step") % hz == 0L || row.channel("step") == (steps - 1).toLong()
            for (field in listOf("broadphase_candidates", "active_contact_pairs", "active_contact_points")) {
                val value = row.channel(field)
                if ((sampled && value < 0) || (!sampled && value != -1L)) {
                    throw IllegalArgumentException("invalid $field")
                }
            }
        }
        for (field in listOf("contact_begins", "contact_ends", "toi_events")) {
            for (index in 1 until rows.size) {
                if (rows[index].channel(field) < rows[index - 1].channel(field)) {
                    throw IllegalArgumentException("nonmonotonic $field")
                }
            }
        }
        for (row in rows) {
            for (field in listOf("linear_speed_sum_m_per_s", "angular_speed_sum_rad_per_s")) {
                val value = row.floatChannel(field)
                if (!value.isFinite() || value < 0) throw IllegalArgumentException("invalid activity speed")
            }
        }
        val joints = when (family) {
            "joint" -> count
            "lifecycle" -> (count + 9) / 10
            else -> 0
        }
        if (rows.any { it.channel("joint_count") != joints.toLong() }) {
            throw IllegalArgumentException("joint topology changed")
        }
        return rows
    }

    private fun eventSummary(values: List<Long>, tailRequired: Int): JsonObject {
        if (values.isEmpty()) {
            return buildJsonObject {
                put("count", 0)
                put("median_ns", JsonNull)
                put("p99_ns", JsonNull)
                put("max_ns", JsonNull)
                put("tail_status", "no_events")
            }
        }
        val sufficient = values.size >= tailRequired
        return buildJsonObject {
            put("count", values.size)
            put("median_ns", values[(values.size - 1) / 2])
            put("p99_ns", if (sufficient) JsonPrimitive(values[ceilIndex(values.size)]) else JsonNull)
            put("max_ns", values.last())
            put("tail_status", if (sufficient) "estimated" else "insufficient_samples")
        }
    }

    /** `math.ceil(0.99 * len) - 1`, which is the index the event tail reports. */
    private fun ceilIndex(length: Int): Int = kotlin.math.ceil(0.99 * length).toInt() - 1

    /** `measure.summary`: the descriptive statistics an evidence record carries per run. */
    fun summary(rows: List<Map<String, String?>>, hz: Int, mode: String): JsonObject {
        val times = rows.map { it.channel("elapsed_ns") }.sorted()
        fun percentile(percent: Int): Long = PerformanceStatistics.wholePercentile(times, percent)
        val eventTimes = rows.filter { it.channel("mutation_ns") > 0 }
            .map { it.channel("elapsed_ns") }.sorted()
        val finalEvents = if (rows.size >= 60 * hz) {
            rows.takeLast(60 * hz).filter { it.channel("mutation_ns") > 0 }
                .map { it.channel("elapsed_ns") }.sorted()
        } else {
            emptyList()
        }
        return buildJsonObject {
            put("samples", rows.size)
            put("median_step_ns", percentile(50))
            put("p95_step_ns", percentile(95))
            put("p99_step_ns", percentile(99))
            put("max_step_ns", times.last())
            put(
                "compute_seconds_per_simulated_second",
                times.sum().toDouble() / 1e9 / (times.size.toDouble() / hz),
            )
            put(
                "total_allocation_bytes",
                if (mode != "timing") JsonPrimitive(rows.sumOf { it.channel("allocation_bytes") }) else JsonNull,
            )
            put("max_lateness_ns", rows.maxOf { it.channel("lateness_ns") })
            put("overrun_steps", rows.count { it.channel("elapsed_ns") > 1e9 / hz })
            put("last_contact_begins", rows.last().channel("contact_begins"))
            put("last_contact_ends", rows.last().channel("contact_ends"))
            put("last_toi_events", rows.last().channel("toi_events"))
            put("last_awake", rows.last().channel("awake_count"))
            put("last_linear_speed_sum_m_per_s", rows.last().floatChannel("linear_speed_sum_m_per_s"))
            put("last_angular_speed_sum_rad_per_s", rows.last().floatChannel("angular_speed_sum_rad_per_s"))
            put("peak_broadphase_candidates", rows.maxOf { it.channel("broadphase_candidates") })
            put("peak_active_contact_pairs", rows.maxOf { it.channel("active_contact_pairs") })
            put("peak_active_contact_points", rows.maxOf { it.channel("active_contact_points") })
            put("peak_rss_delta_bytes", rows.maxOf { it.channel("rss_delta_bytes") })
            put("event_only_full", eventSummary(eventTimes, 100))
            put("event_only_final_minute", eventSummary(finalEvents, 100))
        }
    }

    /**
     * `sustained_archive.step_summary`. Median is an integer for an odd sample count and a float
     * otherwise, which is how Python's `statistics.median` reports it.
     */
    fun stepSummary(rows: List<Map<String, String?>>, mode: String, hz: Int): JsonObject {
        val times = rows.map { it.channel("elapsed_ns") }.sorted()
        val eventSummaries = summary(rows, hz, mode)
        val median: JsonElementValue = if (PerformanceStatistics.medianIsInteger(times)) {
            JsonElementValue.Integer(PerformanceStatistics.medianOfLongs(times).toLong())
        } else {
            JsonElementValue.Floating(PerformanceStatistics.medianOfLongs(times))
        }
        return buildJsonObject {
            put("samples", rows.size)
            put("median_ns", median.toJsonPrimitive())
            put("p99_ns", times[kotlin.math.ceil(times.size * 0.99).toInt() - 1])
            put("total_ns", times.sum())
            put(
                "allocation_bytes",
                if (mode == "timing") JsonNull else JsonPrimitive(rows.sumOf { it.channel("allocation_bytes") }),
            )
            put("peak_rss_delta_bytes", rows.maxOf { it.channel("rss_delta_bytes") })
            put("event_only_full", eventSummaries.getValue("event_only_full"))
            put("event_only_final_minute", eventSummaries.getValue("event_only_final_minute"))
        }
    }

    /** A JSON number that keeps Python's distinction between an `int` and a `float`. */
    sealed interface JsonElementValue {
        fun toJsonPrimitive(): JsonPrimitive

        data class Integer(val value: Long) : JsonElementValue {
            override fun toJsonPrimitive(): JsonPrimitive = JsonPrimitive(value)
        }

        data class Floating(val value: Double) : JsonElementValue {
            override fun toJsonPrimitive(): JsonPrimitive = JsonPrimitive(value)
        }
    }
}
