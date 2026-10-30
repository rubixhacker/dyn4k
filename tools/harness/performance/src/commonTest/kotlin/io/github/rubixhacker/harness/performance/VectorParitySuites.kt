package io.github.rubixhacker.harness.performance

import de.infix.testBalloon.framework.core.testSuite
import io.github.rubixhacker.harness.contract.CanonicalJson
import io.github.rubixhacker.harness.contract.Sha256
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith

/** Shorthands over the recorded vector payload. */
internal object Vectors {
    val root: JsonObject = Json.parseToJsonElement(PerformanceVectors.json).jsonObject

    fun group(name: String): JsonObject = root.getValue(name).jsonObject

    fun objects(element: JsonElement): List<JsonObject> = element.jsonArray.map { it.jsonObject }

    fun strings(element: JsonElement): List<String> = element.jsonArray.map { it.jsonPrimitive.content }

    fun lists(element: JsonElement): List<List<String>> =
        element.jsonArray.map { list -> list.jsonArray.map { it.jsonPrimitive.content } }
}

internal fun JsonObject.str(key: String): String = getValue(key).jsonPrimitive.content

internal fun JsonObject.int(key: String): Int = getValue(key).jsonPrimitive.int

internal fun JsonObject.bool(key: String): Boolean = getValue(key).jsonPrimitive.boolean

internal fun JsonObject.number(key: String): Double = getValue(key).jsonPrimitive.content.toDouble()

internal fun JsonObject.objects(key: String): List<JsonObject> = Vectors.objects(getValue(key))

internal fun JsonObject.strings(key: String): List<String> = Vectors.strings(getValue(key))

internal fun JsonElement.canonicalText(): String = CanonicalJson.render(this)

internal fun hexBytes(hex: String): ByteArray = ByteArray(hex.length / 2) {
    hex.substring(it * 2, it * 2 + 2).toInt(16).toByte()
}

internal fun expandRuns(runs: JsonElement): List<Long> {
    val output = mutableListOf<Long>()
    for (entry in runs.jsonArray.map { it.jsonArray }) {
        val value = entry[0].jsonPrimitive.content.toLong()
        repeat(entry[1].jsonPrimitive.int) { output.add(value) }
    }
    return output
}

/** Asserts that a call is rejected with exactly the recorded Python message. */
internal fun assertRejected(recorded: JsonObject, block: () -> Unit) {
    if (recorded.getValue("ok").jsonPrimitive.boolean) {
        block()
        return
    }
    val error = assertFailsWith<IllegalArgumentException> { block() }
    assertEquals(recorded.str("error"), error.message)
}

/** Asserts that a call is rejected and that the message starts with [prefix]. */
internal fun assertRejectedWith(recorded: JsonObject, prefix: String, block: () -> Unit) {
    val error = assertFailsWith<IllegalArgumentException> { block() }
    val message = error.message ?: ""
    assertEquals(true, message.startsWith(prefix), "expected a message starting with '$prefix', got '$message'")
    assertEquals(recorded.getValue("ok").jsonPrimitive.boolean, false)
}

private const val RUNTIME_ROWS = "runtime_rows"

/** Rebuilds one of the recorded manifest mutations so `validate` can be replayed on it. */
internal fun mutatedManifest(name: String): JsonObject {
    val base = PerformanceManifest.manifest()

    fun JsonArray.withoutLast(): JsonArray = JsonArray(dropLast(1))

    fun JsonArray.replaceAt(index: Int, value: JsonElement): JsonArray {
        val copy = toMutableList()
        copy[index] = value
        return JsonArray(copy)
    }

    fun JsonObject.with(key: String, value: JsonElement): JsonObject {
        val copy = LinkedHashMap(this)
        copy[key] = value
        return JsonObject(copy)
    }

    fun JsonObject.row(index: Int, field: String, value: JsonElement): JsonObject {
        val rows = getValue(RUNTIME_ROWS).jsonArray
        val updated = rows[index].jsonObject.with(field, value)
        return with(RUNTIME_ROWS, rows.replaceAt(index, updated))
    }

    return when (name) {
        "generated" -> base
        "missing_row" -> base.with(RUNTIME_ROWS, base.getValue(RUNTIME_ROWS).jsonArray.withoutLast())
        "changed_minimum" -> base.row(0, "minimum_policy", JsonPrimitive("Java 11"))
        "changed_scenarios" -> base.with("scenarios", base.getValue("scenarios").jsonArray.withoutLast())
        "version" -> base.with("version", JsonPrimitive(2))
        "reordered_rows" -> base.with(
            RUNTIME_ROWS,
            JsonArray(base.getValue(RUNTIME_ROWS).jsonArray.reversed()),
        )
        "changed_budget" -> {
            val budgets = base.getValue("budgets").jsonObject
            val jvm = budgets.getValue("jvm_vs_baseline").jsonObject
            base.with(
                "budgets",
                budgets.with("jvm_vs_baseline", jvm.with("median_ratio_max", JsonPrimitive(2.0))),
            )
        }
        "unknown_environment" -> base.row(0, "environment_status", JsonPrimitive("provisional"))
        "available_without_identity" -> base.row(0, "environment_status", JsonPrimitive("available"))
        "available_with_identity" -> base
            .row(0, "environment_status", JsonPrimitive("available"))
            .row(0, "representative_hardware", JsonPrimitive("host"))
            .row(0, "runtime_version", JsonPrimitive("1.0"))
            .row(0, "abi", JsonPrimitive("x"))
        "changed_targets" -> base.with("targets", base.getValue("targets").jsonArray.withoutLast())
        else -> throw IllegalArgumentException("unknown manifest mutation: $name")
    }
}

val ManifestVectorParity by testSuite {
    val recorded = Vectors.group("manifest")

    test("the generated policy matches the recorded canonical digest") {
        assertEquals(recorded.str("canonical_sha256"), PerformanceManifest.digest())
    }

    test("the generated policy matches the recorded shape") {
        val policy = PerformanceManifest.manifest()
        assertEquals(recorded.int("version"), policy.int("version"))
        assertEquals(recorded.int("target_count"), policy.getValue("targets").jsonArray.size)
        assertEquals(recorded.strings("targets"), policy.strings("targets"))
        assertEquals(recorded.int("runtime_row_count"), PerformanceManifest.runtimeRows().size)
        assertEquals(recorded.int("family_count"), PerformanceManifest.sizes.size)
        assertEquals(recorded.strings("rates_hz"), policy.strings("rates_hz"))
        assertEquals(recorded.strings("api_surfaces"), policy.strings("api_surfaces"))
        assertEquals(recorded.int("scenario_count"), PerformanceManifest.scenarios().size)
    }

    test("the runtime row ids and scenario ids match the recorded digests") {
        assertEquals(
            recorded.str("runtime_row_ids_sha256"),
            Sha256.of(PerformanceManifest.runtimeRows().joinToString("\n") { it.str("id") }),
        )
        assertEquals(
            recorded.str("scenario_ids_sha256"),
            Sha256.of(PerformanceManifest.scenarios().joinToString("\n") { it.str("id") }),
        )
    }

    test("the first and last runtime rows match the recorded rows") {
        val rows = PerformanceManifest.runtimeRows()
        assertEquals(recorded.getValue("first_row"), rows.first())
        assertEquals(recorded.getValue("last_row"), rows.last())
    }

    test("every recorded section hashes to its recorded digest") {
        val policy = PerformanceManifest.manifest()
        assertEquals(recorded.str("budgets_sha256"), Sha256.of(policy.getValue("budgets").canonicalText()))
        assertEquals(recorded.str("sustained_sha256"), Sha256.of(policy.getValue("sustained").canonicalText()))
        assertEquals(
            recorded.str("measurement_method_sha256"),
            Sha256.of(policy.getValue("measurement_method").canonicalText()),
        )
        assertEquals(recorded.str("fixture_sha256"), Sha256.of(policy.getValue("fixture").canonicalText()))
        assertEquals(recorded.str("families_sha256"), Sha256.of(policy.getValue("families").canonicalText()))
        assertEquals(recorded.str("joint_modes_sha256"), Sha256.of(policy.getValue("joint_modes").canonicalText()))
        assertEquals(
            recorded.str("joint_parameters_sha256"),
            Sha256.of(policy.getValue("joint_parameters").canonicalText()),
        )
    }

    test("the ccd fixture revision matches the recorded revision") {
        assertEquals(Vectors.group("ccd_fixture_revision"), PerformanceManifest.ccdFixtureRevision())
        assertEquals(
            Vectors.root.getValue("ccd_fixture_revision_sha256").jsonPrimitive.content,
            Sha256.of(PerformanceManifest.ccdFixtureRevision().canonicalText()),
        )
    }

    test("validate accepts the generated policy and rejects every recorded mutation") {
        for ((name, recordedCase) in Vectors.group("validate_manifest")) {
            assertRejected(recordedCase.jsonObject) { PerformanceManifest.validate(mutatedManifest(name)) }
        }
    }
}

val AnalyzeVectorParity by testSuite {
    test("percentile matches the recorded elements") {
        val recorded = Vectors.group("percentile")
        val values = recorded.strings("values").map { it.toLong() }
        for ((fraction, expected) in recorded.getValue("results").jsonObject) {
            val parsed = fraction.toDoubleOrNull() ?: continue
            assertEquals(
                expected.jsonPrimitive.content.toLong(),
                Analyze.percentile(values, parsed),
                fraction,
            )
        }
    }

    test("warm-up status matches the recorded series") {
        for ((name, element) in Vectors.group("warmup_status")) {
            val recorded = element.jsonObject
            val rows = expandRuns(recorded.getValue("runs"))
            assertEquals(recorded.int("length"), rows.size, "$name length")
            val table = rows.map { mapOf<String, String?>("elapsed_ns" to it.toString()) }
            assertEquals(
                recorded.str("status"),
                Analyze.warmupStatus(table, recorded.int("hz")),
                name,
            )
        }
    }

    test("activity status matches the recorded scenes") {
        val group = Vectors.group("activity_status")
        val fields = group.strings("fields")
        for (recorded in group.objects("cases")) {
            val row = fields.zip(recorded.strings("row")).toMap<String, String?>()
            val rows = List(recorded.int("row_count")) { row }
            assertEquals(
                recorded.str("status"),
                Analyze.activityStatus(
                    rows,
                    recorded.str("family"),
                    recorded.str("variant"),
                    recorded.int("count"),
                    recorded.int("hz"),
                ),
                recorded.str("name"),
            )
        }
    }

    test("bootstrap intervals reproduce the recorded draws") {
        for (recorded in Vectors.root.objects("bootstrap_ratio")) {
            val rowsA = expandRuns(recorded.getValue("a"))
                .map { mapOf<String, String?>("elapsed_ns" to it.toString()) }
            val rowsB = expandRuns(recorded.getValue("b"))
                .map { mapOf<String, String?>("elapsed_ns" to it.toString()) }
            assertEquals(recorded.int("length"), rowsA.size)
            val interval = Analyze.bootstrapRatio(
                rowsA,
                rowsB,
                recorded.int("hz"),
                recorded.str("metric"),
                recorded.int("draws"),
                recorded.getValue("seed").jsonPrimitive.content.toLong(),
            )
            val expected = recorded.getValue("result").jsonObject
            assertEquals(expected.number("lower_95"), interval.lower95, "${recorded.str("name")} lower")
            assertEquals(expected.number("upper_95"), interval.upper95, "${recorded.str("name")} upper")
            assertEquals(expected.int("draws"), interval.draws)
            assertEquals(expected.int("block_seconds"), interval.blockSeconds)
        }
    }

    test("bootstrap rejects the recorded invalid series") {
        fun series(count: Int, base: Int, modulo: Int = 17) =
            List(count) { mapOf<String, String?>("elapsed_ns" to (base + it % modulo).toString()) }

        val cases = Vectors.group("bootstrap_errors")
        assertRejected(cases.getValue("short").jsonObject) {
            Analyze.bootstrapRatio(series(30, 1), series(30, 1), 60)
        }
        assertRejected(cases.getValue("unequal").jsonObject) {
            Analyze.bootstrapRatio(series(31 * 60, 1), series(31 * 60, 2), 60)
        }
        assertRejected(cases.getValue("partial_block").jsonObject) {
            Analyze.bootstrapRatio(series(30 * 60 + 1, 1), series(30 * 60 + 1, 1), 60)
        }
        assertRejected(cases.getValue("unknown_metric").jsonObject) {
            Analyze.bootstrapRatio(series(30 * 60, 1), series(30 * 60, 1), 60, metric = "nope")
        }
        assertRejected(cases.getValue("nonpositive").jsonObject) {
            Analyze.bootstrapRatio(series(30 * 60, 0), series(30 * 60, 1), 60)
        }
    }

    test("plateau status matches the recorded cycles") {
        for ((name, element) in Vectors.group("plateau_status")) {
            val recorded = element.jsonObject
            val heap = recorded.strings("heap")
            val collections = recorded.strings("collections")
            val rows = heap.indices.map {
                mapOf<String, String?>(
                    "heap_after_collection_bytes" to heap[it],
                    "collection_count" to collections[it],
                )
            }
            assertEquals(recorded.str("status"), Analyze.plateauStatus(rows), name)
        }
    }
}

val MeasureVectorParity by testSuite {
    test("the balanced run orders match the recorded orders") {
        assertEquals(
            Vectors.lists(Vectors.root.getValue("balanced_orders")),
            Measure.balancedOrders(),
        )
    }

    test("the pilot workload list matches the recorded list") {
        assertEquals(Vectors.lists(Vectors.root.getValue("pilot")), Measure.pilot.map { listOf(it.first, it.second) })
    }
}

val ValidateCsvVectorParity by testSuite {
    test("validate_csv reproduces every recorded verdict") {
        val group = Vectors.group("validate_csv")
        assertEquals(group.strings("fields"), Measure.stepFields)
        for (case in group.getValue("cases").jsonObject.values.map { it.jsonObject }) {
            val args = case.strings("args")
            assertRejected(case.getValue("result").jsonObject) {
                Measure.validateCsv(
                    Csv.parse(case.str("text")),
                    args[0],
                    args[1],
                    args[2],
                    args[3].toInt(),
                    args[4].toInt(),
                    args[5],
                )
            }
        }
    }
}

val SummaryVectorParity by testSuite {
    test("summary and step_summary reproduce every recorded run") {
        val group = Vectors.group("summary")
        assertEquals(group.strings("fields"), Measure.stepFields)
        for (case in group.objects("cases")) {
            val table = Csv.parse(case.str("text"))
            val hz = case.int("hz")
            val mode = case.str("mode")
            // Compare canonical text so a float's shortest rendering does not decide the verdict.
            assertEquals(
                case.getValue("result").canonicalText(),
                Measure.summary(table.rows, hz, mode).canonicalText(),
                "${case.str("name")} summary",
            )
            assertEquals(
                case.getValue("step_summary").canonicalText(),
                Measure.stepSummary(table.rows, mode, hz).canonicalText(),
                "${case.str("name")} step_summary",
            )
        }
    }
}

val CandidateRunnerVectorParity by testSuite {
    test("read_paths parses the recorded classpath table") {
        val recorded = Vectors.group("read_paths")
        assertEquals(
            recorded.getValue("result").jsonObject.mapValues { Vectors.strings(it.value) },
            CandidateRunner.readPaths(recorded.str("text")),
        )
    }

    test("read_paths rejects the recorded malformed tables") {
        for ((name, element) in Vectors.group("read_paths_errors")) {
            val recorded = element.jsonObject
            assertRejected(recorded.getValue("result").jsonObject) {
                CandidateRunner.readPaths(recorded.str("text"))
            }
            assertEquals(true, name.isNotEmpty())
        }
    }

    test("check_route reproduces the recorded route verdicts") {
        val recorded = Vectors.group("check_route")
        val root = recorded.str("staging_root")
        val core = recorded.str("core")
        val api = recorded.str("api")
        val cases = recorded.getValue("cases").jsonObject
        val inputs = mapOf(
            "direct_ok" to ("direct_kotlin" to listOf(api, core)),
            "direct_missing_core" to ("direct_kotlin" to listOf(core)),
            "direct_duplicate_core" to ("direct_kotlin" to listOf(core, core, api)),
            "compatibility_ok" to ("compatibility" to listOf(core)),
            "compatibility_crossed" to ("compatibility" to listOf(api, core)),
            "unknown_route" to ("baseline" to listOf(core)),
            "outside_staging" to ("compatibility" to listOf(core, "/elsewhere/core.jar")),
            "upstream" to ("compatibility" to listOf(core, "$root/dyn4j-6.0.0.jar")),
        )
        for ((name, verdict) in cases) {
            val (route, paths) = inputs.getValue(name)
            assertRejected(verdict.jsonObject) { CandidateRunner.checkRoute(route, paths, root) }
        }
    }

    test("verify_hashes reproduces the recorded stale and missing verdicts") {
        val recorded = Vectors.group("verify_hashes")
        val files = MemoryFileSystem()
        val core = "${Vectors.group("check_route").str("staging_root")}/${CandidateRunner.coreArtifact}"
        files.write(core, "core bytes")
        val expected = mapOf(core to Sha256.of("core bytes"))
        assertRejected(recorded.getValue("fresh").jsonObject) { CandidateRunner.verifyHashes(files, expected) }
        files.write(core, "changed")
        assertRejectedWith(recorded.getValue("stale").jsonObject, "stale candidate path: ") {
            CandidateRunner.verifyHashes(files, expected)
        }
        val absent = "${Vectors.group("check_route").str("staging_root")}/absent.jar"
        assertRejectedWith(recorded.getValue("missing").jsonObject, "missing candidate path: ") {
            CandidateRunner.verifyHashes(files, mapOf(absent to "0".repeat(64)))
        }
    }

    test("hash_path digests a directory from its entries") {
        val files = MemoryFileSystem()
        files.write("/b/one", "1")
        files.write("/b/sub/two", "2")
        val digest = Sha256Stream().apply {
            update("one".encodeToByteArray())
            update(hexBytes(Sha256.of("1")))
            update("sub/two".encodeToByteArray())
            update(hexBytes(Sha256.of("2")))
        }.hexDigest()
        assertEquals(digest, CandidateRunner.hashPath(files, "/b"))
    }

}

val CandidatePilotVectorParity by testSuite {
    test("state checksum matches the recorded digest") {
        val recorded = Vectors.group("state_checksum")
        assertEquals(recorded.strings("fields"), CandidatePilot.stateFields)
        assertEquals(recorded.str("sha256"), CandidatePilot.stateChecksum(recorded.str("text")))
    }

    test("clean_warmup splits metadata and body exactly as recorded") {
        val recorded = Vectors.group("clean_warmup")
        val input = recorded.str("input")
        val cases = recorded.getValue("cases").jsonObject
        for ((name, element) in cases) {
            val entry = element.jsonObject
            if (entry.bool("ok")) {
                val (metadata, text) = CandidatePilot.cleanWarmup(
                    input,
                    when (name) {
                        "baseline_ok", "marker_on_baseline" -> "baseline"
                        "wrong_marker_route" -> "compatibility"
                        else -> "direct_kotlin"
                    },
                    if (name == "baseline_ok") 7L else 42L,
                )
                assertEquals(entry.getValue("metadata").jsonObject.mapValues { it.value.jsonPrimitive.content.toLong() }, metadata)
                assertEquals(entry.str("text"), text)
            } else {
                val api = if (name == "wrong_marker_route") "compatibility" else "direct_kotlin"
                val pid = if (name == "wrong_pid") 43L else 42L
                assertRejected(entry) { CandidatePilot.cleanWarmup(input, api, pid) }
            }
        }
    }

    test("select_scenarios resolves the recorded workload names") {
        for ((name, element) in Vectors.group("select_scenarios")) {
            val entry = element.jsonObject
            val names = entry.strings("names")
            if ("error" in entry) {
                assertRejected(JsonObject(mapOf("ok" to JsonPrimitive(false), "error" to entry.getValue("error")))) {
                    CandidatePilot.selectScenarios(names)
                }
            } else {
                assertEquals(
                    Vectors.lists(entry.getValue("value")),
                    CandidatePilot.selectScenarios(names).map { listOf(it.first, it.second) },
                    name,
                )
            }
        }
    }
}

val AnalyzeCandidatesVectorParity by testSuite {
    test("summarize_pilot reproduces the recorded pilot index") {
        val recorded = Vectors.group("summarize_pilot")
        assertEquals(
            recorded.getValue("result").jsonObject,
            AnalyzeCandidates.summarizePilot(recorded.getValue("evidence").jsonObject),
        )
    }
}

val StressMonitorVectorParity by testSuite {
    test("the monitor method names match the recorded table") {
        for ((system, element) in Vectors.group("stress_monitor_method")) {
            assertEquals(element.jsonPrimitive.content, StressMonitor.method(system), system)
        }
    }

    test("an invalid PID is rejected before procfs is read") {
        val recorded = Vectors.group("stress_monitor_errors")
        for (element in recorded.objects("invalid_pids")) {
            for (pid in listOf(0L, -1L)) {
                assertRejected(element) { StressMonitor.peakRssBytes(pid, "Linux") { error("procfs read") } }
            }
        }
    }

    test("an unknown platform never reads procfs") {
        assertRejected(Vectors.group("stress_monitor_errors").getValue("unknown_system").jsonObject) {
            StressMonitor.peakRssBytes(123, "FreeBSD") { error("procfs read") }
        }
    }

    test("a VmHWM sample is read in kibibytes and invalid readings are rejected") {
        val status = "Name:\tjava\nVmHWM:\t   8192 kB\nVmRSS:\t   4096 kB\n"
        assertEquals(8L * 1024 * 1024, StressMonitor.peakRssBytes(123, "Linux") { status })
        val rejected = assertFailsWith<IllegalArgumentException> {
            StressMonitor.peakRssBytes(123, "Linux") { "Name:\tjava\nVmHWM:\t   0 kB\n" }
        }
        assertEquals("Linux VmHWM reading is invalid", rejected.message)
        val missing = assertFailsWith<IllegalArgumentException> {
            StressMonitor.peakRssBytes(123, "Linux") { "Name:\tjava\n" }
        }
        assertEquals("Linux VmHWM reading is invalid", missing.message)
    }
}

val SustainedArchiveVectorParity by testSuite {
    val policy = PerformanceManifest.manifest()

    test("the required key sets match the recorded digests") {
        val recorded = Vectors.group("required")
        fun Set<String>.digest() = Sha256.of(sorted().joinToString("\n"))

        val measurements = SustainedArchive.requiredMeasurements(policy)
        assertEquals(recorded.int("measurement_count"), measurements.size)
        assertEquals(recorded.str("measurement_sha256"), measurements.digest())
        assertEquals(
            recorded.strings("measurement_samples"),
            measurements.sorted().let { it.take(2) + it.takeLast(2) },
        )

        val reports = SustainedArchive.requiredReports(policy)
        assertEquals(recorded.int("report_count"), reports.size)
        assertEquals(recorded.str("report_sha256"), reports.digest())
        assertEquals(
            recorded.strings("report_samples"),
            reports.sorted().let { it.take(2) + it.takeLast(2) },
        )

        val noise = SustainedArchive.requiredNoise(policy)
        assertEquals(recorded.int("noise_count"), noise.size)
        assertEquals(recorded.str("noise_sha256"), noise.digest())
        assertEquals(
            recorded.strings("noise_samples"),
            noise.sorted().let { it.take(2) + it.takeLast(2) },
        )

        val plateaus = SustainedArchive.requiredPlateaus(policy)
        assertEquals(recorded.int("plateau_count"), plateaus.size)
        assertEquals(recorded.str("plateau_sha256"), plateaus.digest())
        assertEquals(
            recorded.strings("plateau_samples"),
            plateaus.sorted().let { it.take(2) + it.takeLast(2) },
        )

        val controls = SustainedArchive.comparisonControlKeys(policy)
        assertEquals(recorded.int("control_count"), controls.size)
        assertEquals(recorded.str("control_sha256"), Sha256.of(controls.sorted().joinToString("\n")))
        assertEquals(
            recorded.strings("control_samples").sorted(),
            (controls.sorted().take(3) + controls.sorted().takeLast(3)).sorted(),
        )
    }

    test("the noise limit lookup keeps the tightest limit per workload") {
        val recorded = Vectors.group("noise_limit_lookup")
        val keys = SustainedArchive.comparisonControlKeys(policy).sorted()
        val limits = keys.mapIndexed { index, key -> key to JsonPrimitive(if (index % 2 == 0) 1.10 else 1.05) }.toMap()
        val lookup = SustainedArchive.noiseLimitLookup(
            JsonObject(mapOf("sustained_gate" to JsonObject(mapOf("noise_upper_ratio_max" to JsonObject(limits))))),
        )
        assertEquals(recorded.int("entry_count"), lookup.size)
        assertEquals(
            recorded.str("sha256"),
            Sha256.of(lookup.entries.sortedBy { it.key.joinToString("|") }
                .joinToString("\n") { "${it.key.joinToString("|")}=${it.value}" }),
        )
        for (sample in recorded.objects("samples")) {
            assertEquals(sample.number("limit"), lookup.getValue(sample.strings("key")))
        }
    }

    test("the command template expands to the recorded argv") {
        val recorded = Vectors.group("command_prefix")
        val tokens = recorded.getValue("tokens").jsonObject.mapValues { it.value.jsonPrimitive.content }
        val policyWithHarness = JsonObject(
            mapOf(
                "sustained_gate" to JsonObject(
                    mapOf(
                        "harnesses" to JsonObject(
                            mapOf(
                                "jvm.java" to JsonObject(
                                    mapOf(
                                        "command_prefix" to JsonArray(
                                            recorded.strings("template").map { JsonPrimitive(it) },
                                        ),
                                    ),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        )
        assertEquals(
            recorded.strings("result"),
            SustainedArchive.commandPrefix(policyWithHarness, "jvm.java", tokens),
        )
        val broken = JsonObject(
            mapOf(
                "sustained_gate" to JsonObject(
                    mapOf(
                        "harnesses" to JsonObject(
                            mapOf(
                                "jvm.java" to JsonObject(
                                    mapOf(
                                        "command_prefix" to JsonArray(
                                            recorded.strings("missing_token_template").map { JsonPrimitive(it) },
                                        ),
                                    ),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        )
        val error = assertFailsWith<IllegalArgumentException> {
            SustainedArchive.commandPrefix(broken, "jvm.java", tokens)
        }
        assertEquals("approved complete command template is invalid", error.message)
    }

    test("the record signature matches the recorded HMAC") {
        val recorded = Vectors.group("signature")
        val key = recorded.str("key").encodeToByteArray()
        assertEquals(recorded.str("signature"), SustainedArchive.signature(recorded.getValue("record").jsonObject, key))
        assertEquals(
            recorded.str("unsigned_signature"),
            SustainedArchive.signature(JsonObject(mapOf("a" to JsonPrimitive(1))), key),
        )
    }

    test("scalar intervals reproduce the recorded three-process draws") {
        for (recorded in Vectors.root.objects("scalar_interval")) {
            val interval = Analyze.scalarInterval(
                recorded.strings("first").map { it.toLong() },
                recorded.strings("second").map { it.toLong() },
                recorded.int("draws"),
            )
            val expected = recorded.getValue("result").jsonObject
            assertEquals(expected.number("lower_95"), interval.lower95, recorded.str("name"))
            assertEquals(expected.number("upper_95"), interval.upper95, recorded.str("name"))
        }
    }

    test("scalar intervals reject the recorded invalid inputs") {
        val recorded = Vectors.group("scalar_interval_errors")
        assertRejected(recorded.getValue("length").jsonObject) {
            Analyze.scalarInterval(listOf(1, 2), listOf(1, 2), 10)
        }
        assertRejected(recorded.getValue("negative").jsonObject) {
            Analyze.scalarInterval(listOf(1, -2, 3), listOf(1, 2, 3), 10)
        }
        assertRejected(recorded.getValue("zero_baseline_positive").jsonObject) {
            Analyze.scalarInterval(listOf(0, 0, 0), listOf(1, 2, 3), 10)
        }
    }

    test("capture keys match the recorded identities") {
        for (recorded in Vectors.root.objects("capture_key")) {
            assertEquals(recorded.strings("key"), SustainedArchive.captureKey(recorded.getValue("item").jsonObject))
        }
        assertRejected(Vectors.group("capture_key_unknown").jsonObject) {
            SustainedArchive.captureKey(JsonObject(mapOf("kind" to JsonPrimitive("nonsense"))))
        }
    }

    test("allocation rows present allocation bytes as an elapsed series") {
        val recorded = Vectors.group("allocation_rows")
        val input = recorded.objects("input").map { row ->
            row.mapValues { it.value.jsonPrimitive.content } as Map<String, String?>
        }
        val expected = recorded.objects("result").map { it.mapValues { value -> value.value.jsonPrimitive.content } }
        assertEquals(expected, SustainedArchive.allocationRows(input))
    }

    test("frozenPolicy rejects bytes that do not hash to the independently frozen digest") {
        val error = assertFailsWith<IllegalArgumentException> {
            SustainedArchive.frozenPolicy("{}\n".encodeToByteArray())
        }
        assertEquals("independently frozen manifest digest differs", error.message)
    }
}

val HostCapacityVectorParity by testSuite {
    test("the receipt fields match the recorded field set") {
        assertEquals(Vectors.group("host_capacity").strings("fields").toSet(), HostCapacityControl.fields)
    }

    test("the diagnostic child source matches the recorded source") {
        val recorded = Vectors.group("host_capacity")
        assertEquals(recorded.str("child_source"), HostCapacityControl.childSource)
        assertEquals(recorded.str("child_source_sha256"), Sha256.of(HostCapacityControl.childSource))
        assertEquals(recorded.int("child_source_lines"), CandidatePilot.splitLines(HostCapacityControl.childSource).size)
    }

    test("the receipt signature matches the recorded HMAC") {
        val recorded = Vectors.group("host_capacity")
        val key = "key-material-32-bytes-long-000000".encodeToByteArray()
        assertEquals(
            recorded.str("signature"),
            HostCapacityControl.signature(
                JsonObject(mapOf("pid" to JsonPrimitive(1), "status" to JsonPrimitive("observed"))),
                key,
            ),
        )
    }

    test("source encoding distinguishes exact, CRLF-projected, and altered bytes") {
        val recorded = Vectors.group("host_capacity")
        assertEquals("git_exact", HostCapacityControl.sourceEncoding("abc\n".encodeToByteArray(), "abc\n".encodeToByteArray()))
        assertEquals(recorded.str("encoding_crlf"), HostCapacityControl.sourceEncoding(
            "abc\r\ndef\r\n".encodeToByteArray(),
            "abc\ndef\n".encodeToByteArray(),
        ))
        assertRejected(recorded.getValue("encoding_differs").jsonObject) {
            HostCapacityControl.sourceEncoding("zzz\n".encodeToByteArray(), "abc\n".encodeToByteArray())
        }
        assertRejected(recorded.getValue("encoding_crlf_committed_has_crlf").jsonObject) {
            HostCapacityControl.sourceEncoding("abc\r\ndef\n".encodeToByteArray(), "a\r\nb\n".encodeToByteArray())
        }
    }
}

val ReferenceStudyVectorParity by testSuite {
    val recorded = Vectors.group("reference_study")

    test("the frozen constants match the recorded constants") {
        assertEquals(recorded.str("source_commit"), ReferenceStudy.SOURCE_COMMIT)
        assertEquals(recorded.str("version"), ReferenceStudy.VERSION)
        assertEquals(recorded.str("legacy_version"), ReferenceStudy.LEGACY_VERSION)
        assertEquals(recorded.strings("phases"), ReferenceStudy.phases)
        assertEquals(recorded.strings("identity_files"), ReferenceStudy.identityFiles)
        assertEquals(recorded.strings("raw_files"), ReferenceStudy.rawFiles)
        assertEquals(recorded.strings("v3_raw_files"), ReferenceStudy.v3RawFiles)
        assertEquals(Vectors.lists(recorded.getValue("pair_order")), ReferenceStudy.pairOrder)
        assertEquals(
            recorded.getValue("control_routes").jsonObject.mapValues { it.value.jsonPrimitive.content },
            ReferenceStudy.controlRoutes,
        )
        assertEquals(recorded.strings("control_keys").toSet(), ReferenceStudy.controlKeys)
        assertEquals(recorded.strings("capture_identity_keys").toSet(), ReferenceStudy.captureIdentityKeys)
    }

    test("the versioned sidecar and capture key sets match the recorded sets") {
        assertEquals(recorded.strings("capture_keys_v3").toSet(), ReferenceStudy.captureKeys(ReferenceStudy.VERSION))
        assertEquals(
            recorded.strings("capture_keys_v2").toSet(),
            ReferenceStudy.captureKeys(ReferenceStudy.LEGACY_VERSION),
        )
        assertEquals(recorded.strings("raw_files_v3"), ReferenceStudy.rawFilesFor(ReferenceStudy.VERSION))
        assertEquals(recorded.strings("raw_files_v2"), ReferenceStudy.rawFilesFor(ReferenceStudy.LEGACY_VERSION))
        assertRejected(recorded.getValue("raw_files_unknown").jsonObject) {
            ReferenceStudy.rawFilesFor("reference-study-v9")
        }
    }

    test("absolute source paths match the recorded verdicts") {
        val cases = recorded.getValue("absolute_paths").jsonObject
        for ((path, expected) in cases) {
            // Python's `and` chain returns the falsy operand, so an empty path records as "".
            val flag = expected.jsonPrimitive.content == "true"
            assertEquals(flag, ReferenceStudy.absoluteSourcePath(path), path)
        }
    }

    test("controls_for matches the recorded assignment map") {
        val keys = SustainedArchive.comparisonControlKeys(PerformanceManifest.manifest()).sorted()
        assertEquals(recorded.int("controls_for_count"), keys.size)
        assertEquals(
            recorded.str("controls_for_sha256"),
            Sha256.of(
                keys.joinToString("\n") { key ->
                    val controls = JsonArray(ReferenceStudy.controlsFor(key).map { JsonPrimitive(it) })
                    "$key=${controls.canonicalText()}"
                },
            ),
        )
        for ((key, expected) in recorded.getValue("controls_for_samples").jsonObject) {
            assertEquals(expected.jsonArray.map { it.jsonPrimitive.content }, ReferenceStudy.controlsFor(key))
        }
        val errors = recorded.getValue("controls_for_errors").jsonObject
        assertRejected(errors.getValue("jvm_outside_jvm").jsonObject) {
            ReferenceStudy.controlsFor("jvm_vs_dyn4j|js.node|x|timing|median|full")
        }
        assertRejected(errors.getValue("unknown").jsonObject) {
            ReferenceStudy.controlsFor("nonsense|js.node|x|timing|median|full")
        }
    }

    test("a duplicate JSON key is refused at every depth") {
        val cases = recorded.getValue("unique_object").jsonObject
        assertEquals(true, cases.getValue("unique").jsonObject.getValue("result").jsonObject.bool("ok"))
        for (name in listOf("duplicate", "nested_duplicate")) {
            val entry = cases.getValue(name).jsonObject.getValue("result").jsonObject
            val error = assertFailsWith<IllegalArgumentException> {
                ReferenceStudy.uniqueObject(
                    listOf("a" to JsonPrimitive(1), "a" to JsonPrimitive(2)),
                )
            }
            assertEquals("duplicate JSON key", error.message)
            assertEquals(entry.str("error"), error.message)
        }
    }
}
