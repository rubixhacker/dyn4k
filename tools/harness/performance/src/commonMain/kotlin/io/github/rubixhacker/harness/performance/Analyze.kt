package io.github.rubixhacker.harness.performance

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import kotlin.math.abs

/** A two-sided 95% block-bootstrap ratio interval, as `analyze.bootstrap_ratio` reports it. */
data class BootstrapInterval(
    val lower95: Double,
    val upper95: Double,
    val draws: Int,
    val blockSeconds: Int,
    val zeroBaseline: Boolean = false,
) {
    fun toJson(): JsonObject = buildJsonObject {
        put("lower_95", lower95)
        put("upper_95", upper95)
        put("draws", draws)
        if (zeroBaseline) put("zero_baseline", true) else put("block_seconds", blockSeconds)
    }
}

/** `tools/performance/analyze.py`: activity, warm-up, plateau, and bootstrap analysis. */
object Analyze {
    /** `analyze.samples`: parses a raw sample file and rejects an empty one. */
    fun samples(path: String, text: String): List<Map<String, String?>> {
        val rows = Csv.parse(text).rows
        if (rows.isEmpty()) throw IllegalArgumentException("empty sample file: $path")
        return rows
    }

    /** `analyze.percentile`. */
    fun percentile(values: List<Long>, fraction: Double): Long =
        PerformanceStatistics.percentile(values, fraction)

    /**
     * `analyze.warmup_status`: converged when the last three 30-second window medians are each
     * within 5% of their own median.
     */
    fun warmupStatus(rows: List<Map<String, String?>>, hz: Int): String {
        val window = 30 * hz
        if (rows.size < 4 * window) return "unvalidated"
        val medians = mutableListOf<Double>()
        var start = 0
        while (start <= rows.size - window) {
            val slice = (start until start + window).map { rows[it].channel("elapsed_ns") }
            medians.add(PerformanceStatistics.medianOfLongs(slice))
            start += window
        }
        val latest = medians.takeLast(3)
        val center = PerformanceStatistics.median(latest)
        if (center <= 0.0) return "invalid"
        val spread = latest.maxOf { abs(it / center - 1.0) }
        return if (spread <= 0.05) "converged" else "not_converged"
    }

    /**
     * `analyze.activity_status`: proves that a scene actually simulated the workload it claims.
     */
    fun activityStatus(
        rows: List<Map<String, String?>>,
        family: String,
        variant: String,
        count: Int,
        hz: Int,
    ): String {
        val first = rows.first()
        val last = rows.last()
        val contacts = last.channel("contact_begins") - first.channel("contact_begins")
        val toi = last.channel("toi_events") - first.channel("toi_events")
        val awake = last.channel("awake_count")
        val peakPairs = rows.maxOf { it.channel("active_contact_pairs") }
        val peakPoints = rows.maxOf { it.channel("active_contact_points") }
        when (family) {
            "separated" -> {
                val valid = contacts == 0L &&
                    awake >= PerformanceStatistics.ceilFraction(0.9, count) &&
                    last.floatChannel("linear_speed_sum_m_per_s") >= 0.6 * count
                return if (valid) "valid" else "invalid"
            }
            "pile" -> return if (contacts > 0 && peakPairs > 0 && peakPoints > 0) "valid" else "invalid"
            "joint" -> {
                val valid = awake >= PerformanceStatistics.ceilFraction(0.8, count) &&
                    last.channel("joint_count") == count.toLong() &&
                    last.floatChannel("angular_speed_sum_rad_per_s") > 0.01
                return if (valid) "valid" else "invalid"
            }
            "ccd" -> return if (toi > 0 && contacts > 0 && peakPairs > 0) "valid" else "invalid"
            "lifecycle" -> {
                if (variant == "settle") {
                    val valid = rows.size >= 30 * hz &&
                        awake <= PerformanceStatistics.floorFraction(0.2, count)
                    return if (valid) "valid" else "unvalidated"
                }
                if (variant == "wake") {
                    val valid = rows.size >= 30 * hz && awake > 0 && contacts > 0
                    return if (valid) "valid" else "unvalidated"
                }
                if (variant == "replace") {
                    val valid = rows.size >= 2 * hz && contacts > 0
                    return if (valid) "valid" else "unvalidated"
                }
            }
        }
        return "invalid"
    }

    /**
     * `analyze.bootstrap_ratio`: the 95% block-bootstrap interval of a paired ratio, with one
     * second blocks and CPython's seeded draw sequence.
     */
    fun bootstrapRatio(
        a: List<Map<String, String?>>,
        b: List<Map<String, String?>>,
        hz: Int,
        metric: String = "median",
        draws: Int = 2000,
        seed: Long = 17017,
    ): BootstrapInterval {
        if (a.size != b.size || a.size < 30 * hz) {
            throw IllegalArgumentException(
                "paired baseline series need at least 30 seconds and equal step counts",
            )
        }
        val blocksA = a.chunked(hz).map { block -> block.map { it.channel("elapsed_ns") } }
        val blocksB = b.chunked(hz).map { block -> block.map { it.channel("elapsed_ns") } }
        if (blocksA.any { it.size != hz } || blocksB.any { it.size != hz }) {
            throw IllegalArgumentException("partial time block")
        }
        val random = PythonRandom(seed)
        val ratios = mutableListOf<Double>()
        repeat(draws) {
            val picks = blocksA.indices.map { random.randRange(blocksA.size) }
            val aa = picks.flatMap { blocksA[it] }
            val bb = picks.flatMap { blocksB[it] }
            val numerator: Double
            val denominator: Double
            when (metric) {
                "median" -> {
                    numerator = PerformanceStatistics.medianOfLongs(bb)
                    denominator = PerformanceStatistics.medianOfLongs(aa)
                }
                "p99" -> {
                    numerator = PerformanceStatistics.percentile(bb, 0.99).toDouble()
                    denominator = PerformanceStatistics.percentile(aa, 0.99).toDouble()
                }
                "total" -> {
                    numerator = bb.sum().toDouble()
                    denominator = aa.sum().toDouble()
                }
                else -> throw IllegalArgumentException("unknown metric")
            }
            if (denominator <= 0.0) throw IllegalArgumentException("nonpositive baseline")
            ratios.add(numerator / denominator)
        }
        return BootstrapInterval(
            lower95 = PerformanceStatistics.percentile(ratios, 0.025),
            upper95 = PerformanceStatistics.percentile(ratios, 0.975),
            draws = draws,
            blockSeconds = 1,
        )
    }

    /**
     * `sustained_archive.scalar_interval`: a three-process bootstrap of a scalar ratio, used for
     * retained-heap and construction-allocation comparisons.
     */
    fun scalarInterval(first: List<Long>, second: List<Long>, draws: Int): BootstrapInterval {
        if (first.size != 3 || second.size != 3 || (first + second).any { it < 0 }) {
            throw IllegalArgumentException("scalar comparison needs three nonnegative matched processes")
        }
        if (first.all { it == 0L }) {
            if (!second.all { it == 0L }) {
                throw IllegalArgumentException("positive allocation against zero baseline")
            }
            return BootstrapInterval(1.0, 1.0, draws, 1, zeroBaseline = true)
        }
        val random = PythonRandom(17017)
        val ratios = mutableListOf<Double>()
        repeat(draws) {
            val picks = listOf(random.randRange(3), random.randRange(3), random.randRange(3))
            val numerator = picks.sumOf { second[it] }
            val denominator = picks.sumOf { first[it] }
            if (denominator <= 0L) throw IllegalArgumentException("scalar baseline resample has zero denominator")
            ratios.add(numerator.toDouble() / denominator.toDouble())
        }
        return BootstrapInterval(
            lower95 = PerformanceStatistics.percentile(ratios, 0.025),
            upper95 = PerformanceStatistics.percentile(ratios, 0.975),
            draws = draws,
            blockSeconds = 1,
        )
    }

    /** `analyze.plateau_status`: live heap must stop growing across the create/dispose cycles. */
    fun plateauStatus(rows: List<Map<String, String?>>): String {
        if (rows.size != 100) return "invalid"
        val heap = rows.map { it.channel("heap_after_collection_bytes") }
        val collections = rows.map { it.channel("collection_count") }
        if (heap.any { it < 0 } || collections.last() <= collections.first()) return "invalid"
        val early = PerformanceStatistics.medianOfLongs(heap.subList(20, 40))
        val late = PerformanceStatistics.medianOfLongs(heap.subList(80, 100))
        return if (early > 0.0 && abs(late / early - 1.0) <= 0.05) "stable" else "not_stable"
    }

    /**
     * `analyze.compare_pair`: the full-run and final-minute interval for one baseline/candidate
     * pair. A run short of 600 simulated seconds cannot be compared.
     */
    fun comparePair(
        baseline: List<Map<String, String?>>,
        candidate: List<Map<String, String?>>,
        hz: Int,
        metric: String,
        limit: Double,
    ): Map<String, JsonObject> {
        if (baseline.size != 600 * hz || candidate.size != 600 * hz) {
            throw IllegalArgumentException(
                "full comparison requires exactly 600 simulated seconds per run",
            )
        }
        val output = linkedMapOf<String, JsonObject>()
        for ((label, first, second) in listOf(
            Triple("full", baseline, candidate),
            Triple("final_minute", baseline.takeLast(60 * hz), candidate.takeLast(60 * hz)),
        )) {
            val interval = bootstrapRatio(first, second, hz, metric)
            output[label] = buildJsonObject {
                put("lower_95", interval.lower95)
                put("upper_95", interval.upper95)
                put("draws", interval.draws)
                put("block_seconds", interval.blockSeconds)
                put("limit", limit)
                put(
                    "ratio_result",
                    if (interval.upper95 <= limit) "within_limit" else "inconclusive_or_exceeds_limit",
                )
                put("qualification", "unpassed_without_activity_warmup_memory_and_environment_checks")
            }
        }
        return output
    }
}
