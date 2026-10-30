package io.github.rubixhacker.harness.performance

import de.infix.testBalloon.framework.core.testSuite
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNull

private object Leaves {
    val root: JsonObject = Json.parseToJsonElement(LeafVectors.json).jsonObject

    fun group(name: String): JsonObject = root.getValue(name).jsonObject
}

private fun JsonObject.text(key: String): String = getValue(key).jsonPrimitive.content

private fun JsonObject.whole(key: String): Long = getValue(key).jsonPrimitive.content.toLong()


private fun JsonObject.items(key: String): List<JsonObject> = getValue(key).jsonArray.map { it.jsonObject }

private fun JsonObject.values(key: String): List<String> = getValue(key).jsonArray.map { it.jsonPrimitive.content }

private fun elapsedRows(values: List<Long>): List<Map<String, String?>> =
    values.map { mapOf<String, String?>("elapsed_ns" to it.toString()) }

/** Asserts a CLI-level validation message, and that `argparse` exited 2 for it. */
private fun assertMessage(recorded: JsonObject, expected: String, block: () -> Unit) {
    val error = assertFailsWith<IllegalArgumentException> { block() }
    assertEquals(expected, error.message)
    assertEquals(2, recorded.int("exit_code"))
    assertEquals(true, recorded.text("stderr").contains("error: $expected"))
}

/** `warmup_probe.py`: argument checks, window medians, and the report it writes. */
val WarmupProbeCases by testSuite {
    val recorded = Leaves.group("warmup_probe")
    val warmupCsv = recorded.text("warmup_csv")
    val measuredCsv = recorded.text("measured_csv")

    test("the report reproduces the recorded warmup-probe.json") {
        val report = WarmupProbe.buildReport(
            baselineJarSha256 = recorded.text("baseline_jar_sha256"),
            manifestSha256 = recorded.text("manifest_sha256"),
            harnessSha256 = recorded.text("harness_sha256"),
            host = recorded.getValue("host").jsonObject,
            result = recorded.getValue("result").jsonObject,
            warmup = Csv.parse(warmupCsv).rows,
            measured = Csv.parse(measuredCsv).rows,
            family = recorded.text("family"),
            variant = recorded.text("variant"),
            bodyCount = recorded.int("body_count"),
            hz = recorded.int("hz"),
        )
        assertEquals(
            recorded.getValue("report").canonicalText(),
            report.canonicalText(),
        )
    }

    test("the stdout summary reproduces the recorded summary") {
        val report = recorded.getValue("report").jsonObject
        val summary = buildJsonObject {
            put("warmup_status", report.getValue("warmup_status"))
            put("activity_status", report.getValue("activity_status"))
        }
        assertEquals(recorded.getValue("stdout").canonicalText(), summary.canonicalText())
    }

    test("window medians keep Python's int and float distinction") {
        val medians = WarmupProbe.windowMedians(Csv.parse(warmupCsv).rows, recorded.int("hz"))
        val expected = recorded.getValue("report").jsonObject.getValue("warmup_window_medians_ns")
            .jsonArray.map { it.jsonPrimitive.content }
        assertEquals(expected, medians.map { it.toJson().content })
        // The full windows have an even sample count, so Python reports a float; the short
        // trailing window has an odd count, so it reports an int.
        assertEquals(PythonNumber.Floating::class, medians.first()::class)
        assertEquals(PythonNumber.Integer::class, medians.last()::class)
    }

    test("a window sequence shorter than one window still reports its median") {
        val rows = elapsedRows(listOf(4L, 1L, 3L, 2L))
        val medians = WarmupProbe.windowMedians(rows, 60)
        assertEquals(listOf("2.5"), medians.map { it.toJson().content })
    }

    test("the warm-up window is rejected outside 120 to 600 seconds") {
        val recordedCases = Leaves.group("warmup_probe_arguments")
        for (name in listOf("too_short", "too_long")) {
            val seconds = if (name == "too_short") 119 else 601
            assertMessage(recordedCases.getValue(name).jsonObject, "warm-up must be between 120 and 600 seconds") {
                WarmupProbe.requireWarmupSeconds(seconds)
            }
        }
        WarmupProbe.requireWarmupSeconds(120)
        WarmupProbe.requireWarmupSeconds(600)
    }

    test("a variant outside the frozen family is rejected") {
        val recordedCase = Leaves.group("warmup_probe_arguments").getValue("unknown_variant").jsonObject
        assertMessage(recordedCase, "variant is absent from manifest") {
            WarmupProbe.requireVariant(PerformanceManifest.manifest(), "pile", "nope")
        }
        WarmupProbe.requireVariant(PerformanceManifest.manifest(), "pile", "default")
    }

    test("a checked-in manifest that differs from the generator is rejected") {
        val error = assertFailsWith<IllegalArgumentException> {
            WarmupProbe.requireCheckedInManifest("{}\n".encodeToByteArray())
        }
        assertEquals("checked-in manifest differs from generator", error.message)
    }

    test("the checked-in manifest is accepted unchanged") {
        WarmupProbe.requireCheckedInManifest(CheckedInManifest.bytes)
    }
}

/** `calibrate.py`: argument checks, the paired intervals, and the noise bound. */
val CalibrateCases by testSuite {
    val recorded = Leaves.group("calibrate")
    val report = recorded.getValue("report").jsonObject

    test("the report reproduces the recorded calibration.json") {
        val rebuilt = Calibrate.buildReport(
            sourceCommit = recorded.text("source_commit"),
            baselineJarSha256 = recorded.text("baseline_jar_sha256"),
            manifestSha256 = recorded.text("manifest_sha256"),
            harnessSha256 = recorded.text("harness_sha256"),
            host = recorded.getValue("host").jsonObject,
            family = recorded.text("family"),
            variant = recorded.text("variant"),
            size = recorded.text("size"),
            hz = recorded.int("hz"),
            warmupStatus = recorded.values("warmup_status"),
            activityStatus = recorded.values("activity_status"),
            trials = recorded.items("trials"),
            pairs = recorded.items("pairs"),
        )
        assertEquals(report.canonicalText(), rebuilt.canonicalText())
    }

    test("the noise bound reproduces the recorded bound") {
        assertEquals(
            recorded.getValue("noise_bound").canonicalText(),
            Calibrate.noiseBound(recorded.items("pairs")).canonicalText(),
        )
    }

    test("a pair of unchanged series reproduces the recorded intervals") {
        val first = Leaves.group("calibrate_first_pair")
        val pair = Calibrate.pair(
            a = first.text("a"),
            b = first.text("b"),
            left = elapsedRows(first.getValue("left").jsonArray.map { it.jsonPrimitive.content.toLong() }),
            right = elapsedRows(first.getValue("right").jsonArray.map { it.jsonPrimitive.content.toLong() }),
            hz = first.int("hz"),
        )
        assertEquals(first.getValue("recorded").canonicalText(), pair.canonicalText())
    }

    test("the report carries six trials and three pairs") {
        assertEquals(6, report.getValue("trials").jsonArray.size)
        assertEquals(3, report.getValue("unchanged_baseline_pairs").jsonArray.size)
        assertEquals("method_calibration_only", report.text("qualification"))
        assertEquals(
            listOf("median", "p99", "total"),
            report.getValue("noise_bound").jsonObject.keys.toList(),
        )
    }

    test("calibration durations below the approved floor are rejected") {
        val recordedCases = Leaves.group("calibrate_arguments")
        for ((name, seconds) in listOf("short_warmup" to 119, "short_measurement" to 30)) {
            val recordedCase = recordedCases.getValue(name).jsonObject
            assertMessage(
                recordedCase,
                "calibration needs at least 120 warm-up and 30 measured seconds",
            ) {
                if (name == "short_warmup") {
                    Calibrate.requireDurations(10, 30)
                } else {
                    Calibrate.requireDurations(120, 29)
                }
            }
            assertEquals(true, seconds > 0)
        }
        Calibrate.requireDurations(120, 30)
    }

    test("a variant outside the frozen family is rejected") {
        val recordedCase = Leaves.group("calibrate_arguments").getValue("unknown_variant").jsonObject
        assertMessage(recordedCase, "variant is absent from the manifest") {
            Calibrate.requireVariant(PerformanceManifest.manifest(), "pile", "nope")
        }
        Calibrate.requireVariant(PerformanceManifest.manifest(), "pile", "default")
    }
}

/** `ccd_route_trace.py`: first differences, fixture identity rules, and the result record. */
val CcdRouteTraceCases by testSuite {
    val constants = Leaves.group("ccd_constants")

    /** The trace the Python fixture generator wrote: all channels zero except three. */
    fun trace(count: Int, mutation: Pair<Int, Pair<String, String>>? = null): List<Map<String, String?>> =
        List(count) { step ->
            val row = LinkedHashMap<String, String?>()
            for (field in CandidatePilot.stateFields) row[field] = "0"
            row["body_count"] = "25"
            row["awake_count"] = "95"
            row["linear_speed_sum_m_per_s"] = "25"
            if (mutation != null && mutation.first == step) row[mutation.second.first] = mutation.second.second
            row
        }

    test("the constants match the recorded constants") {
        assertEquals(constants.text("purpose"), CcdRouteTrace.PURPOSE)
        assertEquals(constants.text("fixture_hash_scheme"), CcdRouteTrace.FIXTURE_HASH_SCHEME)
        assertEquals(constants.int("warmup_steps"), CcdRouteTrace.WARMUP_STEPS)
        assertEquals(constants.int("measured_steps"), CcdRouteTrace.MEASURED_STEPS)
        assertEquals(constants.values("routes"), CcdRouteTrace.routes)
        assertEquals(constants.values("state_fields"), CandidatePilot.stateFields)
        assertEquals(
            constants.getValue("workloads").jsonObject.mapValues { it.value.jsonPrimitive.content },
            CcdRouteTrace.routes.associateWith { "ccd.default.small.60hz.$it" },
        )
        assertEquals(
            PerformanceManifest.BASELINE_JAR_SHA256,
            constants.text("pinned_baseline_sha256"),
        )
        assertEquals(
            listOf(
                "direct_kotlin" to "compatibility",
                "baseline" to "direct_kotlin",
                "baseline" to "compatibility",
            ),
            CcdRouteTrace.comparisonPairs,
        )
    }

    test("the first difference matches every recorded case") {
        for (case in Leaves.root.items("first_difference")) {
            val left = case.getValue("left").jsonArray.map { it.jsonObject.rowMap() }
            val right = case.getValue("right").jsonArray.map { it.jsonObject.rowMap() }
            val expected = case.getValue("result")
            val observed = CcdRouteTrace.firstDifference(left, right)
            val observedJson = observed ?: JsonNull
            assertEquals(
                expected.canonicalText(),
                observedJson.canonicalText(),
                case.text("name"),
            )
        }
    }

    test("identical traces have no first difference") {
        assertNull(CcdRouteTrace.firstDifference(trace(4), trace(4)))
    }

    test("a shorter trace reports the row count, not a channel") {
        val difference = CcdRouteTrace.firstDifference(trace(4), trace(3))
        assertEquals("row_count", difference!!.text("channel"))
        assertEquals(3, difference.int("step"))
        assertEquals("4", difference.getValue("left").jsonPrimitive.content)
        assertEquals("3", difference.getValue("right").jsonPrimitive.content)
    }

    test("records are read with the recorded channel names") {
        val recorded = Leaves.group("ccd_agreeing").getValue("result").jsonObject
        val identity = recorded.getValue("identity").jsonObject.getValue("baseline").jsonObject
        val timing = recorded.getValue("timing").jsonObject.getValue("baseline").jsonObject
        assertEquals("baseline.fixture-identity.csv", identity.text("raw"))
        assertEquals(27, identity.int("rows"))
        assertEquals(
            "ccd.default.small.60hz.baseline.timing.r1.csv",
            timing.text("raw"),
        )
        assertEquals(CandidatePilot.stateFields.size, constants.values("state_fields").size)
    }

    test("the agreeing run reproduces the recorded result.json") {
        val recorded = Leaves.group("ccd_agreeing").getValue("result").jsonObject
        val traces = CcdRouteTrace.routes.associateWith { trace(120) }
        val rebuilt = CcdRouteTrace.buildResult(
            sourceCommit = recorded.text("source_commit"),
            candidateIdentitySha256 = recorded.text("candidate_identity_sha256"),
            baselineJarSha256 = recorded.text("baseline_jar_sha256"),
            manifestSha256 = recorded.text("manifest_sha256"),
            traceToolSha256 = recorded.text("trace_tool_sha256"),
            host = recorded.getValue("host").jsonObject,
            identity = recorded.getValue("identity").jsonObject,
            timing = recorded.getValue("timing").jsonObject,
            comparisons = CcdRouteTrace.comparisons(traces),
        )
        assertEquals(recorded.canonicalText(), rebuilt.canonicalText())
    }

    test("the differing run reproduces the recorded comparisons and exit message") {
        val recorded = Leaves.group("ccd_differing").getValue("result").jsonObject
        val traces = CcdRouteTrace.routes.associateWith { trace(120) }.toMutableMap()
        traces["compatibility"] = trace(120, mutation = 7 to ("awake_count" to "1"))
        val comparisons = CcdRouteTrace.comparisons(traces)
        assertEquals(
            recorded.getValue("comparisons").canonicalText(),
            comparisons.canonicalText(),
        )
        val error = assertFailsWith<IllegalStateException> { CcdRouteTrace.requireStagedRoutesAgree(comparisons) }
        assertEquals(
            Leaves.group("ccd_differing").text("exit_message"),
            error.message,
        )
    }

    test("the row-count run reproduces the recorded comparisons") {
        val recorded = Leaves.group("ccd_row_count").getValue("result").jsonObject
        val traces = CcdRouteTrace.routes.associateWith { trace(120) }.toMutableMap()
        traces["compatibility"] = trace(119)
        assertEquals(
            recorded.getValue("comparisons").canonicalText(),
            CcdRouteTrace.comparisons(traces).canonicalText(),
        )
    }

    test("agreeing comparisons pass the staged-route check") {
        CcdRouteTrace.requireStagedRoutesAgree(
            CcdRouteTrace.comparisons(CcdRouteTrace.routes.associateWith { trace(120) }),
        )
    }

    test("the stdout summary reproduces the recorded summary") {
        val stdout = Leaves.group("ccd_agreeing").getValue("stdout").jsonObject
        val comparisons = CcdRouteTrace.comparisons(CcdRouteTrace.routes.associateWith { trace(120) })
        assertEquals(
            stdout.getValue("comparisons").canonicalText(),
            comparisons.canonicalText(),
        )
        assertEquals("unpassed", stdout.text("qualification"))
    }

    test("a creation hash list that is not the zero-based index is rejected") {
        val bad = Leaves.group("ccd_bad_hash")
        val identityRows = List(27) { index ->
            mapOf<String, String?>("hash_code" to (index + 1).toString())
        }
        val error = assertFailsWith<IllegalArgumentException> {
            CcdRouteTrace.requireCreationHashes("baseline", identityRows)
        }
        assertEquals(bad.text("failure"), error.message)
        CcdRouteTrace.requireCreationHashes(
            "baseline",
            List(27) { index -> mapOf<String, String?>("hash_code" to index.toString()) },
        )
    }

    test("a short creation list is rejected") {
        val short = Leaves.group("ccd_short_identity")
        val error = assertFailsWith<IllegalArgumentException> {
            CcdRouteTrace.requireCreationHashes(
                "baseline",
                List(26) { index -> mapOf<String, String?>("hash_code" to index.toString()) },
            )
        }
        assertEquals(short.text("failure"), error.message)
    }

    test("initial identities that differ between routes are rejected") {
        val divergent = Leaves.group("ccd_divergent_identity")
        val same = List(27) { index ->
            mapOf<String, String?>(
                "creation_index" to index.toString(),
                "hash_code" to index.toString(),
                "world_center_x" to (if (index == 0) "-10.0" else "10.0"),
                "world_center_y" to "0.5",
                "bullet" to (index >= 2).toString(),
            )
        }
        val differing = same.mapIndexed { index, row ->
            if (index == 0) row + ("world_center_y" to "0.6") else row
        }
        val error = assertFailsWith<IllegalArgumentException> {
            CcdRouteTrace.requireSameInitialIdentities(
                mapOf(
                    "baseline" to same,
                    "direct_kotlin" to same,
                    "compatibility" to differing,
                ),
            )
        }
        assertEquals(divergent.text("failure"), error.message)
        CcdRouteTrace.requireSameInitialIdentities(
            mapOf("baseline" to same, "direct_kotlin" to same, "compatibility" to same),
        )
    }

    test("a baseline jar that is not the pinned artifact is rejected") {
        val error = assertFailsWith<IllegalArgumentException> {
            CcdRouteTrace.requirePinnedBaseline("0".repeat(64))
        }
        assertEquals("baseline JAR differs from the pinned artifact", error.message)
        CcdRouteTrace.requirePinnedBaseline(PerformanceManifest.BASELINE_JAR_SHA256)
    }

    test("an identity entry carries the recorded keys") {
        val entry = CcdRouteTrace.identityEntry(
            raw = "baseline.fixture-identity.csv",
            sha256 = "a".repeat(64),
            stderrRaw = "baseline.fixture-identity.stderr.raw",
            stderrSha256 = "b".repeat(64),
            processPid = 101,
            rowCount = 27,
        )
        val recorded = Leaves.group("ccd_agreeing").getValue("result").jsonObject
            .getValue("identity").jsonObject.getValue("baseline").jsonObject
        assertEquals(recorded.keys, entry.keys)
        assertEquals(recorded.text("raw"), entry.text("raw"))
        assertEquals(recorded.whole("process_pid"), entry.whole("process_pid"))
    }
}

/** The pure procfs parsers `measure.host_identity` runs over `/proc/cpuinfo` and `/proc/meminfo`. */
val HostIdentityParsingCases by testSuite {
    test("the recorded parser cases reproduce") {
        val cases = Leaves.group("host_identity").items("cases")
        for (case in cases) {
            val inputElement = case["input"]
            val input = if (inputElement == null || inputElement is JsonNull) {
                null
            } else {
                inputElement.jsonPrimitive.content
            }
            val name = case.text("name")
            val observed = if (name.startsWith("cpu_model")) {
                HostIdentityParsing.cpuModel(input)?.let { JsonPrimitive(it).canonicalText() } ?: "null"
            } else {
                HostIdentityParsing.memTotalKib(input)?.let { JsonPrimitive(it).canonicalText() } ?: "null"
            }
            assertEquals(case.getValue("result").canonicalText(), observed, name)
        }
    }

    test("the first matching procfs line wins") {
        val cpuinfo = "processor\t: 0\nmodel name\t: First CPU\nmodel name\t: Second CPU\n"
        assertEquals("First CPU", HostIdentityParsing.cpuModel(cpuinfo))
        val meminfo = "MemTotal:  100 kB\nMemTotal:  200 kB\n"
        assertEquals(100L, HostIdentityParsing.memTotalKib(meminfo))
    }

    test("a procfs stream without the named line yields nothing") {
        assertNull(HostIdentityParsing.cpuModel("processor\t: 0\n"))
        assertNull(HostIdentityParsing.memTotalKib("MemFree: 1024 kB\n"))
        assertNull(HostIdentityParsing.cpuModel(null))
        assertNull(HostIdentityParsing.memTotalKib(null))
    }
}

private fun JsonObject.rowMap(): Map<String, String?> =
    entries.filter { it.key != Csv.REST_KEY }.associate { it.key to it.value.jsonPrimitive.content }
