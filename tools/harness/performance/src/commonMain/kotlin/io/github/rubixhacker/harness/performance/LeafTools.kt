package io.github.rubixhacker.harness.performance

import io.github.rubixhacker.harness.contract.CanonicalJson
import io.github.rubixhacker.harness.contract.StrictJson
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put

/**
 * The two pure parsers behind `measure.host_identity`.
 *
 * The identity itself is read from the running host, but the way a CPU model and a memory total
 * are lifted out of procfs text is deterministic and worth pinning: a receipt that records a
 * different `ram_kib` is a different receipt.
 */
object HostIdentityParsing {
    /** `next((line.split(":", 1)[1].strip() for line in cpuinfo.splitlines() if line.startswith("model name")), None)`. */
    fun cpuModel(cpuinfo: String?): String? {
        if (cpuinfo == null) return null
        for (line in cpuinfo.split("\n")) {
            if (line.startsWith("model name")) {
                val separator = line.indexOf(':')
                if (separator < 0) continue
                return line.substring(separator + 1).trim()
            }
        }
        return null
    }

    /** `int(next(line.split()[1] for line in meminfo.splitlines() if line.startswith("MemTotal:"), None))`. */
    fun memTotalKib(meminfo: String?): Long? {
        if (meminfo == null) return null
        for (line in meminfo.split("\n")) {
            if (!line.startsWith("MemTotal:")) continue
            val fields = line.split(Regex("\\s+")).filter { it.isNotEmpty() }
            if (fields.size < 2) continue
            return fields[1].toLongOrNull()
        }
        return null
    }
}

/**
 * `tools/performance/warmup_probe.py`: a single scenario with a long warm-up, reported as 30
 * second window medians. The report is evidence that a warm-up converges; it qualifies nothing.
 */
object WarmupProbe {
    const val QUALIFICATION: String = "warmup_probe_only"

    /** `not 120 <= warmup_seconds <= 600` — the check `main` performs before doing any work. */
    fun requireWarmupSeconds(seconds: Int) {
        if (seconds < 120 || seconds > 600) {
            throw IllegalArgumentException("warm-up must be between 120 and 600 seconds")
        }
    }

    /** `args.variant not in {item["variant"] for item in manifest()["scenarios"] if item["family"] == args.family}`. */
    fun requireVariant(policy: JsonObject, family: String, variant: String) {
        val variants = policy.getValue("scenarios").jsonArray
            .map { it.jsonObject }
            .filter { it.str("family") == family }
            .map { it.str("variant") }
            .toSet()
        if (variant !in variants) throw IllegalArgumentException("variant is absent from manifest")
    }

    /**
     * `json.loads(MANIFEST_FILE.read_text()) != manifest()` — the checked-in manifest must still
     * be exactly what the generator emits.
     */
    fun requireCheckedInManifest(manifestBytes: ByteArray) {
        val checkedIn = StrictJson.load(manifestBytes.decodeToString()).jsonObject
        if (checkedIn != PerformanceManifest.manifest()) {
            throw IllegalArgumentException("checked-in manifest differs from generator")
        }
    }

    /**
     * `warmup_window_medians_ns`: the median elapsed step time of every 30 second window,
     * including a final window that is shorter than the others.
     */
    fun windowMedians(warmup: List<Map<String, String?>>, hz: Int): List<PythonNumber> {
        val window = 30 * hz
        val medians = mutableListOf<PythonNumber>()
        var start = 0
        while (start < warmup.size) {
            val slice = (start until minOf(start + window, warmup.size)).map { warmup[it].channel("elapsed_ns") }
            medians.add(PythonNumber.medianOf(slice))
            start += window
        }
        return medians
    }

    /** The `warmup-probe.json` the command writes, given the measured run and its inputs. */
    fun buildReport(
        baselineJarSha256: String,
        manifestSha256: String,
        harnessSha256: String,
        host: JsonObject,
        result: JsonObject,
        warmup: List<Map<String, String?>>,
        measured: List<Map<String, String?>>,
        family: String,
        variant: String,
        bodyCount: Int,
        hz: Int,
    ): JsonObject = buildJsonObject {
        put("schema", 1)
        put("qualification", QUALIFICATION)
        put("baseline_jar_sha256", baselineJarSha256)
        put("manifest_sha256", manifestSha256)
        put("harness_sha256", harnessSha256)
        put("host", host)
        put("result", result)
        put("warmup_window_medians_ns", JsonArray(windowMedians(warmup, hz).map { it.toJson() }))
        put("warmup_status", Analyze.warmupStatus(warmup, hz))
        put("activity_status", Analyze.activityStatus(measured, family, variant, bodyCount, hz))
    }
}

/**
 * `tools/performance/calibrate.py`: six unchanged-baseline trials, paired, reported as a noise
 * bound. The report calibrates the method; it does not qualify a candidate.
 */
object Calibrate {
    const val QUALIFICATION: String = "method_calibration_only"

    /** `warmup_seconds < 120 or measurement_seconds < 30`. */
    fun requireDurations(warmupSeconds: Int, measurementSeconds: Int) {
        if (warmupSeconds < 120 || measurementSeconds < 30) {
            throw IllegalArgumentException("calibration needs at least 120 warm-up and 30 measured seconds")
        }
    }

    /** `args.variant not in {s["variant"] for s in manifest()["scenarios"] if s["family"] == family}`. */
    fun requireVariant(policy: JsonObject, family: String, variant: String) {
        val variants = policy.getValue("scenarios").jsonArray
            .map { it.jsonObject }
            .filter { it.str("family") == family }
            .map { it.str("variant") }
            .toSet()
        if (variant !in variants) throw IllegalArgumentException("variant is absent from the manifest")
    }

    /**
     * `noise_bound`: how far the two-sided 95% interval edges of the unchanged-baseline pairs
     * stray from 1.0, per metric. This is the number later budgets are read against.
     */
    fun noiseBound(pairs: List<JsonObject>): JsonObject = buildJsonObject {
        for (metric in listOf("median", "p99", "total")) {
            // `max(abs(pair[metric][edge] - 1.0) for pair in pairs for edge in (lower_95, upper_95))`
            val worst = pairs.maxOf { pair ->
                val interval = pair.getValue(metric).jsonObject
                maxOf(
                    kotlin.math.abs(decimal(interval, "lower_95") - 1.0),
                    kotlin.math.abs(decimal(interval, "upper_95") - 1.0),
                )
            }
            put(metric, worst)
        }
    }

    /**
     * One paired entry of `unchanged_baseline_pairs`: the two raw streams and the three
     * intervals that relate them.
     */
    fun pair(
        a: String,
        b: String,
        left: List<Map<String, String?>>,
        right: List<Map<String, String?>>,
        hz: Int,
    ): JsonObject = buildJsonObject {
        put("a", a)
        put("b", b)
        for (metric in listOf("median", "p99", "total")) {
            put(metric, Analyze.bootstrapRatio(left, right, hz, metric).toJson())
        }
    }

    /** The `calibration.json` the command writes. */
    fun buildReport(
        sourceCommit: String,
        baselineJarSha256: String,
        manifestSha256: String,
        harnessSha256: String,
        host: JsonObject,
        family: String,
        variant: String,
        size: String,
        hz: Int,
        warmupStatus: List<String>,
        activityStatus: List<String>,
        trials: List<JsonObject>,
        pairs: List<JsonObject>,
    ): JsonObject = buildJsonObject {
        put("schema", 1)
        put("qualification", QUALIFICATION)
        put("source_commit", sourceCommit)
        put("baseline_jar_sha256", baselineJarSha256)
        put("manifest_sha256", manifestSha256)
        put("harness_sha256", harnessSha256)
        put("host", host)
        put(
            "scenario",
            buildJsonObject {
                put("family", family)
                put("variant", variant)
                put("size", size)
                put("hz", hz)
            },
        )
        put("warmup_status", JsonArray(warmupStatus.map { JsonPrimitive(it) }))
        put("activity_status", JsonArray(activityStatus.map { JsonPrimitive(it) }))
        put("trials", JsonArray(trials))
        put("unchanged_baseline_pairs", JsonArray(pairs))
        put("noise_bound", noiseBound(pairs))
    }
}

/**
 * `tools/performance/ccd_route_trace.py`: the CCD fixture identity and the per-step state of the
 * three staged routes, compared channel by channel.
 */
object CcdRouteTrace {
    const val PURPOSE: String =
        "CCD fixture and staged-route diagnostic; performance qualification unpassed"
    const val FIXTURE_HASH_SCHEME: String =
        "Per fixture, hashCode equals zero-based creation index; two walls then 25 bullet circles"
    const val WARMUP_STEPS: Int = 60
    const val MEASURED_STEPS: Int = 120
    val routes: List<String> = listOf("baseline", "direct_kotlin", "compatibility")
    val comparisonPairs: List<Pair<String, String>> = listOf(
        "direct_kotlin" to "compatibility",
        "baseline" to "direct_kotlin",
        "baseline" to "compatibility",
    )

    /** `ccd_route_trace.rows`: a raw step table read as records. */
    fun rows(text: String): List<Map<String, String?>> = Csv.parse(text).rows

    /**
     * `ccd_route_trace.first_difference`: the first state channel that differs between two
     * traces, the row count when only the lengths differ, and `null` when the traces agree.
     */
    fun firstDifference(
        left: List<Map<String, String?>>,
        right: List<Map<String, String?>>,
    ): JsonObject? {
        for (step in 0 until minOf(left.size, right.size)) {
            val before = left[step]
            val after = right[step]
            for (field in CandidatePilot.stateFields) {
                if (before.required(field) != after.required(field)) {
                    return buildJsonObject {
                        put("step", step)
                        put("channel", field)
                        put("left", before.required(field))
                        put("right", after.required(field))
                    }
                }
            }
        }
        if (left.size != right.size) {
            return buildJsonObject {
                put("step", minOf(left.size, right.size))
                put("channel", "row_count")
                put("left", left.size)
                put("right", right.size)
            }
        }
        return null
    }

    /** `sha256(baseline) != manifest()["baseline_jar_sha256"]`. */
    fun requirePinnedBaseline(actualSha256: String) {
        if (actualSha256 != PerformanceManifest.BASELINE_JAR_SHA256) {
            throw IllegalArgumentException("baseline JAR differs from the pinned artifact")
        }
    }

    /** `len(values) != 27 or [int(row["hash_code"]) for row in values] != list(range(27))`. */
    fun requireCreationHashes(route: String, values: List<Map<String, String?>>) {
        val hashes = values.map { it.channel("hash_code") }
        if (values.size != 27 || hashes != (0L until 27L).toList()) {
            throw IllegalArgumentException("CCD fixture creation hashes differ: $route")
        }
    }

    /** `len({json.dumps(value, sort_keys=True) for value in identities.values()}) != 1`. */
    fun requireSameInitialIdentities(identities: Map<String, List<Map<String, String?>>>) {
        val canonical = identities.values.map { rows ->
            CanonicalJson.render(JsonArray(rows.map { row -> jsonObjectOf(row) }))
        }.toSet()
        if (canonical.size != 1) {
            throw IllegalArgumentException("CCD fixture initial identities differ")
        }
    }

    /** The `comparisons` section: for each pair, the first difference and the channels examined. */
    fun comparisons(traces: Map<String, List<Map<String, String?>>>): JsonObject = buildJsonObject {
        for ((left, right) in comparisonPairs) {
            put(
                "${left}_vs_$right",
                buildJsonObject {
                    put(
                        "first_difference",
                        firstDifference(traces.getValue(left), traces.getValue(right)) ?: JsonNull,
                    )
                    put(
                        "recorded_channels",
                        JsonArray(CandidatePilot.stateFields.map { JsonPrimitive(it) }),
                    )
                },
            )
        }
    }

    /**
     * The `SystemExit` the command performs when the two staged candidate routes disagree. The
     * CLI layer turns this into its exit code; the message is the one the reference prints.
     */
    fun requireStagedRoutesAgree(comparisons: JsonObject) {
        val difference = comparisons.getValue("direct_kotlin_vs_compatibility")
            .jsonObject["first_difference"]
        if (difference != null && difference is JsonObject) {
            throw IllegalStateException("staged candidate CCD routes differ")
        }
    }

    /** The `result.json` skeleton the command writes before it fills the measured sections. */
    fun buildResult(
        sourceCommit: String,
        candidateIdentitySha256: String,
        baselineJarSha256: String,
        manifestSha256: String,
        traceToolSha256: String,
        host: JsonObject,
        identity: JsonObject,
        timing: JsonObject,
        comparisons: JsonObject,
    ): JsonObject = buildJsonObject {
        put("schema", 1)
        put("purpose", PURPOSE)
        put("source_commit", sourceCommit)
        put("candidate_identity_sha256", candidateIdentitySha256)
        put("baseline_jar_sha256", baselineJarSha256)
        put("manifest_sha256", manifestSha256)
        put("trace_tool_sha256", traceToolSha256)
        put("fixture_hash_scheme", FIXTURE_HASH_SCHEME)
        put(
            "workloads",
            buildJsonObject { for (route in routes) put(route, "ccd.default.small.60hz.$route") },
        )
        put("warmup_steps", WARMUP_STEPS)
        put("measured_steps", MEASURED_STEPS)
        put("host", host)
        put("identity", identity)
        put("timing", timing)
        put("comparisons", comparisons)
        put("qualification", "unpassed")
    }

    /** One `identity` entry per route. */
    fun identityEntry(
        raw: String,
        sha256: String,
        stderrRaw: String,
        stderrSha256: String,
        processPid: Long,
        rowCount: Int,
    ): JsonObject = buildJsonObject {
        put("raw", raw)
        put("sha256", sha256)
        put("stderr_raw", stderrRaw)
        put("stderr_sha256", stderrSha256)
        put("process_pid", processPid)
        put("rows", rowCount)
    }

    private fun jsonObjectOf(row: Map<String, String?>): JsonObject = buildJsonObject {
        for ((key, value) in row) if (key != Csv.REST_KEY) put(key, value)
    }
}

/** Reads a JSON number as a double, as `json.loads` then a Python float comparison reads it. */
private fun decimal(value: JsonObject, key: String): Double =
    value.getValue(key).jsonPrimitive.content.toDouble()
