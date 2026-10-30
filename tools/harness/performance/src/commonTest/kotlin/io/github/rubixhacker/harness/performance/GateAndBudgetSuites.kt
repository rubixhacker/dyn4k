package io.github.rubixhacker.harness.performance

import de.infix.testBalloon.framework.core.testSuite
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.put
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith

/**
 * The parts of the sustained gate, budget comparison, and short-window analysis that the
 * recorded vectors do not reach, because they need a fully approved gate that no archive in
 * this repository carries.
 */
val SustainedGateRejectionCases by testSuite {
    test("a policy without an approved gate cannot be used") {
        val error = assertFailsWith<IllegalArgumentException> {
            SustainedArchive.approvedGate(PerformanceManifest.manifest())
        }
        assertEquals(
            "unpassed policy: approved sustained harness, noise, and stress decisions are absent",
            error.message,
        )
    }

    test("a gate without noise controls is rejected before its harnesses are read") {
        val policy = PerformanceManifest.manifest()
        val gated = JsonObject(LinkedHashMap(policy).apply { put("sustained_gate", buildJsonObject { }) })
        val error = assertFailsWith<IllegalArgumentException> { SustainedArchive.approvedGate(gated) }
        assertEquals(
            "unpassed policy: frozen comparison control map or noise limits are absent",
            error.message,
        )
    }

    test("a gate with complete maps but no harnesses is rejected") {
        val policy = PerformanceManifest.manifest()
        val keys = SustainedArchive.comparisonControlKeys(policy)
        val rows = policy.objects("runtime_rows").map { it.str("id") }
        val gated = JsonObject(
            LinkedHashMap(policy).apply {
                put(
                    "sustained_gate",
                    buildJsonObject {
                        put(
                            "noise_controls",
                            buildJsonObject { for (id in rows) put(id, buildJsonObject { }) },
                        )
                        put(
                            "comparison_controls",
                            buildJsonObject {
                                for (key in keys) put(key, JsonPrimitive(key.split("|")[1]))
                            },
                        )
                        put(
                            "noise_upper_ratio_max",
                            buildJsonObject { for (key in keys) put(key, JsonPrimitive(1.05)) },
                        )
                        put("harnesses", buildJsonObject { })
                        put("stress_limits", buildJsonObject { })
                    },
                )
            },
        )
        val error = assertFailsWith<IllegalArgumentException> { SustainedArchive.approvedGate(gated) }
        assertEquals(
            "unpassed policy: approved noise or stress ceiling is absent or invalid",
            error.message,
        )
    }

    test("a gate whose comparison controls miss a key is rejected") {
        val policy = PerformanceManifest.manifest()
        val gated = JsonObject(
            LinkedHashMap(policy).apply {
                put(
                    "sustained_gate",
                    buildJsonObject {
                        put("noise_controls", buildJsonObject { })
                        put("comparison_controls", buildJsonObject { })
                        put("noise_upper_ratio_max", buildJsonObject { })
                        put("harnesses", buildJsonObject { })
                        put("stress_limits", buildJsonObject { })
                    },
                )
            },
        )
        val error = assertFailsWith<IllegalArgumentException> { SustainedArchive.approvedGate(gated) }
        assertEquals(
            "unpassed policy: frozen comparison control map or noise limits are absent",
            error.message,
        )
    }
}

val BudgetComparisonCases by testSuite {
    fun series(count: Int, value: Long) =
        List(count) { mapOf<String, String?>("elapsed_ns" to value.toString()) }

    test("a comparison needs exactly 600 simulated seconds per run") {
        val error = assertFailsWith<IllegalArgumentException> {
            Analyze.comparePair(series(600 * 60 - 1, 1000), series(600 * 60, 1000), 60, "median", 1.10)
        }
        assertEquals("full comparison requires exactly 600 simulated seconds per run", error.message)
    }

    test("a comparison reports both windows and its ratio verdict") {
        val baseline = List(600 * 60) { mapOf<String, String?>("elapsed_ns" to (1000 + it % 17).toString()) }
        val candidate = List(600 * 60) { mapOf<String, String?>("elapsed_ns" to (1000 + it % 17).toString()) }
        val output = Analyze.comparePair(baseline, candidate, 60, "median", 1.10)
        assertEquals(setOf("full", "final_minute"), output.keys)
        assertEquals("within_limit", output.getValue("full").str("ratio_result"))
        assertEquals(1.0, output.getValue("final_minute").number("upper_95"))
    }

    test("a zero allocation baseline against zero allocation passes") {
        val windows = SustainedArchive.upperWithin(
            series(60, 0),
            series(60, 0),
            60,
            "total",
            1.05,
            "zero baseline",
            200,
        )
        assertEquals(
            listOf("full", "final_minute"),
            windows.map { it.first },
        )
        assertEquals(true, windows.all { it.second.zeroBaseline && it.second.upper95 == 1.0 })
    }

    test("a zero allocation baseline against positive allocation fails closed") {
        val error = assertFailsWith<IllegalArgumentException> {
            SustainedArchive.upperWithin(
                series(60, 0),
                series(60, 5),
                60,
                "total",
                1.05,
                "zero baseline",
                200,
            )
        }
        assertEquals("zero baseline full positive allocation against zero baseline", error.message)
    }

    test("a ratio above its limit is refused") {
        val doubled = series(30 * 60, 2000)
        val error = assertFailsWith<IllegalArgumentException> {
            SustainedArchive.upperWithin(series(30 * 60, 1000), doubled, 60, "total", 1.05, "shim", 200)
        }
        assertEquals("shim full 95% upper bound exceeds 1.05", error.message)
    }
}

val ExploratoryIntervalCases by testSuite {
    fun timingEvidence(): JsonObject = buildJsonObject {
        put(
            "results",
            JsonArray(
                listOf("baseline", "direct_kotlin", "compatibility").map { api ->
                    buildJsonObject {
                        put("family", "separated")
                        put("variant", "default")
                        put("size", "small")
                        put("hz", 60)
                        put("mode", "timing")
                        put("api", api)
                        put("raw", "separated.default.small.60hz.$api.timing.r1.csv")
                        put("activity_status", "valid")
                        put("warmup_status", "converged")
                    }
                },
            ),
        )
    }

    test("a timing group yields three metrics, two routes, and the shim comparison") {
        val output = AnalyzeCandidates.exploratoryIntervals(timingEvidence()) { name ->
            val base = if (name.contains("compatibility")) 1100 else 1000
            List(30 * 60) { mapOf<String, String?>("elapsed_ns" to (base + it % 17).toString()) }
        }
        assertEquals(setOf("separated.default.small.60hz"), output.keys)
        val case = output.getValue("separated.default.small.60hz")
        assertEquals(
            setOf("direct_kotlin", "compatibility", "compatibility_vs_direct"),
            case.jsonObject.keys,
        )
        assertEquals(
            setOf("median", "p99", "total", "activity", "warmup", "qualification"),
            case.jsonObject.getValue("direct_kotlin").jsonObject.keys,
        )
        assertEquals(
            "unpassed_short_warmup_and_uncalibrated_host",
            case.jsonObject.getValue("compatibility_vs_direct").jsonObject
                .getValue("qualification").let { (it as JsonPrimitive).content },
        )
    }

    test("a group missing a route is skipped") {
        val evidence = buildJsonObject {
            put(
                "results",
                JsonArray(
                    listOf(
                        buildJsonObject {
                            put("family", "separated")
                            put("variant", "default")
                            put("size", "small")
                            put("hz", 60)
                            put("mode", "timing")
                            put("api", "baseline")
                            put("raw", "separated.default.small.60hz.baseline.timing.r1.csv")
                        },
                    ),
                ),
            )
        }
        assertEquals(0, AnalyzeCandidates.exploratoryIntervals(evidence) { emptyList() }.size)
    }

    test("a non-timing group is skipped") {
        val evidence = buildJsonObject {
            put(
                "results",
                JsonArray(
                    listOf(
                        buildJsonObject {
                            put("family", "separated")
                            put("variant", "default")
                            put("size", "small")
                            put("hz", 60)
                            put("mode", "allocation")
                            put("api", "baseline")
                            put("raw", "separated.default.small.60hz.baseline.allocation.r1.csv")
                        },
                    ),
                ),
            )
        }
        assertEquals(0, AnalyzeCandidates.exploratoryIntervals(evidence) { emptyList() }.size)
    }
}

val ManifestPolicyDerivationCases by testSuite {
    test("the minimum policy is per target and runtime") {
        assertEquals("Java 8", PerformanceManifest.minimumPolicy("jvm", "java"))
        assertEquals("Android API 21", PerformanceManifest.minimumPolicy("androidNativeArm64", "android_arm64"))
        assertEquals("Safari 18.2", PerformanceManifest.minimumPolicy("js", "safari"))
        assertEquals(
            "Wasmtime 37.0.0 with -W gc=y -W exceptions=y -W function-references=y",
            PerformanceManifest.minimumPolicy("wasmWasi", "wasmtime"),
        )
        assertEquals("watchOS 26", PerformanceManifest.minimumPolicy("watchosDeviceArm64", "watchos_lp64_device"))
        assertEquals("watchOS 8", PerformanceManifest.minimumPolicy("watchosArm64", "watchos_ilp32_device"))
        assertEquals(
            "no minimum policy for wasmJsExtra",
            assertFailsWith<IllegalArgumentException> {
                PerformanceManifest.minimumPolicy("wasmJsExtra", "node")
            }.message,
        )
    }

    test("tvOS and watchOS report their medium size instead of gating it") {
        assertEquals(
            mapOf("small" to "absolute", "medium" to "report_only", "stress" to "report_only"),
            PerformanceManifest.gates("tvosArm64", "tvos_device"),
        )
        assertEquals(
            mapOf("small" to "absolute", "medium" to "absolute", "stress" to "report_only"),
            PerformanceManifest.gates("jvm", "java"),
        )
    }

    test("the build configurations name the pinned optimization") {
        assertEquals("default Kotlin bytecode optimization", PerformanceManifest.buildConfig("jvm"))
        assertEquals("Kotlin -Xno-optimize", PerformanceManifest.developmentConfig("jvm"))
        assertEquals(
            "PRODUCTION linked output; Binaryen optimized for Wasm",
            PerformanceManifest.buildConfig("wasmWasi"),
        )
        assertEquals("Kotlin/Native -g", PerformanceManifest.developmentConfig("linuxX64"))
    }

    test("every target appears at least once in the runtime rows") {
        val rows = PerformanceManifest.runtimeRows()
        assertEquals(21, rows.map { it.str("target") }.toSet().size)
        assertEquals(28, rows.size)
        assertEquals(rows.size, rows.map { it.str("id") }.toSet().size)
    }

    test("the scenario ids are unique and carry the declared rate and api") {
        val scenarios = PerformanceManifest.scenarios()
        assertEquals(scenarios.size, scenarios.map { it.str("id") }.toSet().size)
        for (scenario in scenarios) {
            assertEquals("${scenario.int("rate_hz")}hz", scenario.str("id").split(".")[3])
            assertEquals(scenario.str("api"), scenario.str("id").substringAfterLast('.'))
        }
    }
}

internal fun JsonElement.asString(): String = (this as JsonPrimitive).content
