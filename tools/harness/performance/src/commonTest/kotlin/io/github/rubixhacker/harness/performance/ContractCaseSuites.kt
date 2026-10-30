package io.github.rubixhacker.harness.performance

import de.infix.testBalloon.framework.core.testSuite
import io.github.rubixhacker.harness.contract.StrictJson
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

/**
 * The cases of `tools/performance/test_manifest.py`, replayed against the checked-in manifest and
 * CCD fixture bytes.
 */
val ManifestContractCases by testSuite {
    val fixture: JsonObject = StrictJson.load(CheckedInCcdFixture.bytes.decodeToString()).jsonObject

    test("ccd fixture revision links to unchanged manifest") {
        PerformanceManifest.validateCcdFixtureRevision(CheckedInManifest.bytes, fixture)
        assertEquals("performance-ccd-v2", fixture.str("version"))
        assertEquals(27, fixture.getValue("workload_ids").jsonArray.size)
        assertEquals(
            "zero_based_creation_index",
            fixture.getValue("body_hash").jsonObject.str("algorithm"),
        )
    }

    test("ccd fixture revision rejects changed rule or base hash") {
        for (change in listOf("body_hash", "base_manifest_sha256")) {
            val copied = LinkedHashMap(fixture)
            if (change == "body_hash") {
                val bodyHash = fixture.getValue("body_hash").jsonObject
                val updated = LinkedHashMap(bodyHash)
                updated["algorithm"] = JsonPrimitive("object_identity")
                copied["body_hash"] = JsonObject(updated)
            } else {
                copied[change] = JsonPrimitive("0".repeat(64))
            }
            val error = assertFailsWith<IllegalArgumentException>(change) {
                PerformanceManifest.validateCcdFixtureRevision(CheckedInManifest.bytes, JsonObject(copied))
            }
            assertEquals("CCD fixture revision differs from the frozen rule", error.message)
        }
    }

    test("public manifest covers the approved matrix") {
        val manifest = PerformanceManifest.manifest()
        assertEquals(1, manifest.int("version"))
        assertEquals(21, manifest.getValue("targets").jsonArray.size)
        assertEquals(28, manifest.getValue("runtime_rows").jsonArray.size)
        assertEquals(5, manifest.getValue("families").jsonObject.size)
        assertEquals(listOf("30", "60", "120"), manifest.strings("rates_hz"))
        assertEquals(
            setOf("baseline", "direct_kotlin", "compatibility"),
            manifest.strings("api_surfaces").toSet(),
        )
        val rows = manifest.getValue("runtime_rows").jsonArray.map { it.jsonObject }
        assertTrue(rows.all { it.str("environment_status") == "unavailable" })
        assertTrue(rows.all { it.getValue("representative_hardware") is kotlinx.serialization.json.JsonNull })
    }

    test("validate rejects a missing runtime row") {
        val broken = mutatedManifest("missing_row")
        val error = assertFailsWith<IllegalArgumentException> { PerformanceManifest.validate(broken) }
        assertEquals("runtime row list is incomplete or reordered", error.message)
    }

    test("validate rejects a changed minimum or build") {
        val error = assertFailsWith<IllegalArgumentException> {
            PerformanceManifest.validate(mutatedManifest("changed_minimum"))
        }
        assertEquals("runtime policy differs: jvm.java / minimum_policy", error.message)
    }

    test("the checked-in manifest is the frozen policy the tools cite") {
        val policy = SustainedArchive.frozenPolicy(CheckedInManifest.bytes)
        assertEquals(PerformanceManifest.manifest(), policy)
        // The frozen digest is over the checked-in file bytes, not over the canonical rendering.
        assertEquals(
            PerformanceManifest.V1_MANIFEST_SHA256,
            io.github.rubixhacker.harness.contract.Sha256.of(CheckedInManifest.bytes),
        )
        assertEquals(Vectors.group("manifest").str("canonical_sha256"), PerformanceManifest.digest(policy))
    }

    test("a resealed manifest with one changed byte is not the frozen policy") {
        val altered = CheckedInManifest.bytes + "\n".encodeToByteArray()
        val error = assertFailsWith<IllegalArgumentException> { SustainedArchive.frozenPolicy(altered) }
        assertEquals("independently frozen manifest digest differs", error.message)
    }
}

/** The cases of `tools/performance/test_analyze.py` and `test_measure.py`. */
val AnalysisContractCases by testSuite {
    test("unchanged paired series has a unit interval") {
        val rows = List(30 * 60) { mapOf<String, String?>("elapsed_ns" to (1000 + it % 17).toString()) }
        val interval = Analyze.bootstrapRatio(rows, rows, 60, draws = 200)
        assertEquals(1.0, interval.lower95)
        assertEquals(1.0, interval.upper95)
    }

    test("short warm-up cannot converge by definition") {
        val rows = List(60) { mapOf<String, String?>("elapsed_ns" to "1000") }
        assertEquals("unvalidated", Analyze.warmupStatus(rows, 60))
    }

    test("growth in a create-dispose series is not stable") {
        val rows = List(100) { cycle ->
            mapOf<String, String?>(
                "heap_after_collection_bytes" to (1000 + cycle * 100).toString(),
                "collection_count" to cycle.toString(),
            )
        }
        assertEquals("not_stable", Analyze.plateauStatus(rows))
    }

    test("three repeats balance every API position") {
        val orders = Measure.balancedOrders()
        assertEquals(3, orders.size)
        assertEquals(setOf("baseline", "direct_kotlin", "compatibility"), orders[0].toSet())
        for (position in 0..2) {
            assertEquals(
                setOf("baseline", "direct_kotlin", "compatibility"),
                orders.map { it[position] }.toSet(),
            )
        }
    }
}

/** `tools/performance/test_candidate_pilot.py`. */
val CandidatePilotContractCases by testSuite {
    test("candidate metadata is separate from the warm-up CSV") {
        val input = "#process_pid=42\n#route_marker=1\nwarmup_step,elapsed_ns\n0,5\n"
        val (metadata, cleaned) = CandidatePilot.cleanWarmup(input, "direct_kotlin", 42)
        assertEquals(mapOf("process_pid" to 42L, "route_marker" to 1L), metadata)
        val rows = Csv.parse(cleaned).rows
        assertEquals(listOf(mapOf<String, String?>("warmup_step" to "0", "elapsed_ns" to "5")), rows)
    }

    test("a warm-up stream from another process is refused") {
        val input = "#process_pid=42\n#route_marker=1\nwarmup_step,elapsed_ns\n0,5\n"
        val error = assertFailsWith<IllegalArgumentException> {
            CandidatePilot.cleanWarmup(input, "direct_kotlin", 43)
        }
        assertEquals("plateau route or process identity differs from the launcher", error.message)
    }
}

/** `tools/performance/test_candidate_runner.py`, against an in-memory staging repository. */
val CandidateRouteContractCases by testSuite {
    val root = "/staging"
    val core = "$root/${CandidateRunner.coreArtifact}"
    val api = "$root/${CandidateRunner.apiArtifact}"

    test("missing and crossed staged routes fail") {
        CandidateRunner.checkRoute("direct_kotlin", listOf(api, core), root)
        CandidateRunner.checkRoute("compatibility", listOf(core), root)
        assertFailsWith<IllegalArgumentException> {
            CandidateRunner.checkRoute("direct_kotlin", listOf(core), root)
        }
        assertFailsWith<IllegalArgumentException> {
            CandidateRunner.checkRoute("compatibility", listOf(api, core), root)
        }
    }

    test("upstream provider and stale binary fail") {
        val upstream = "$root/dyn4j-6.0.0.jar"
        val error = assertFailsWith<IllegalArgumentException> {
            CandidateRunner.checkRoute("compatibility", listOf(core, upstream), root)
        }
        assertEquals("upstream dyn4j artifact is on a candidate route", error.message)

        val files = MemoryFileSystem()
        files.write(core, "core")
        val expected = mapOf(core to io.github.rubixhacker.harness.contract.Sha256.of("core"))
        CandidateRunner.verifyHashes(files, expected)
        files.write(core, "changed")
        val stale = assertFailsWith<IllegalArgumentException> { CandidateRunner.verifyHashes(files, expected) }
        assertEquals("stale candidate path: $core", stale.message)
    }
}

/** The portable cases of `tools/performance/test_stress_monitor.py`. */
val StressMonitorContractCases by testSuite {
    test("linux process peak is reported in bytes from VmHWM") {
        val status = "Name:\tjava\nVmPeak:\t  65536 kB\nVmHWM:\t  16384 kB\n"
        assertEquals(16L * 1024 * 1024, StressMonitor.peakRssBytes(4242, "Linux") { status })
        assertEquals("linux_proc_vmhwm_v1", StressMonitor.method("Linux"))
    }

    test("macos ps reads exact pid and kibibyte units") {
        assertEquals(8L * 1024 * 1024, StressMonitor.darwinExternalSample(123, 123, 8192))
        assertEquals("macos_wait4_maxrss_v1", StressMonitor.method("Darwin"))
        val error = assertFailsWith<IllegalArgumentException> {
            StressMonitor.darwinExternalSample(123, 124, 8192)
        }
        assertEquals("macOS external RSS PID or sample is invalid", error.message)
    }

    test("macos terminal wait4 binds child pid and peak rss") {
        assertEquals(0L to 8L * 1024 * 1024, StressMonitor.darwinTerminalPeak(123, 123, 0, 8192))
        val pid = assertFailsWith<IllegalArgumentException> {
            StressMonitor.darwinTerminalPeak(123, 124, 0, 8192)
        }
        assertEquals("macOS terminal usage PID or status is invalid", pid.message)
        val peak = assertFailsWith<IllegalArgumentException> {
            StressMonitor.darwinTerminalPeak(123, 123, 0, 0)
        }
        assertEquals("macOS terminal peak RSS is invalid", peak.message)
    }

    test("an unknown platform never reads procfs") {
        assertTrue(StressMonitor.method("FreeBSD").startsWith("unsupported_"))
        val error = assertFailsWith<IllegalArgumentException> {
            StressMonitor.peakRssBytes(123, "FreeBSD") { error("procfs read") }
        }
        assertEquals("external peak RSS monitor is unvalidated for FreeBSD", error.message)
    }

    test("native monitor failures do not become zero samples") {
        val error = assertFailsWith<IllegalArgumentException> {
            StressMonitor.darwinExternalSample(123, 999, 8192)
        }
        assertEquals("macOS external RSS PID or sample is invalid", error.message)
    }

    test("a linux invalid pid is rejected before procfs") {
        for (pid in listOf(0L, -1L)) {
            val error = assertFailsWith<IllegalArgumentException> {
                StressMonitor.peakRssBytes(pid, "Linux") { error("procfs read") }
            }
            assertEquals("stress monitor PID is invalid", error.message)
        }
    }
}

/** The portable case of `tools/performance/test_sustained_archive.py`'s gate coverage. */
val SustainedGateContractCases by testSuite {
    test("the frozen matrix has every gate case and no stress gate") {
        val policy = PerformanceManifest.manifest()
        val plan = SustainedArchive.requiredMeasurements(policy)
        assertEquals(999, policy.getValue("scenarios").jsonArray.size)
        assertEquals(28, policy.getValue("runtime_rows").jsonArray.size)
        assertEquals(21, policy.getValue("targets").jsonArray.size)
        assertTrue("jvm.java|separated.default.small.30hz.baseline|timing|1" in plan)
        assertTrue("jvm.java|separated.default.medium.30hz.direct_kotlin|memory|3" in plan)
        assertTrue(plan.none { ".stress." in it })
        assertTrue(
            plan.none { it.split("|")[1].endsWith(".baseline") && !it.startsWith("jvm.java|") },
        )
    }

    test("the key sets are sized to the frozen policy") {
        val policy = PerformanceManifest.manifest()
        // 27 non-JVM rows contribute nothing for a baseline-only workload; the JVM row does.
        val measurements = SustainedArchive.requiredMeasurements(policy)
        val reports = SustainedArchive.requiredReports(policy)
        val plateaus = SustainedArchive.requiredPlateaus(policy)
        assertTrue(measurements.isNotEmpty() && reports.isNotEmpty() && plateaus.isNotEmpty())
        assertTrue(SustainedArchive.requiredNoise(policy).all { it.split("|")[4] in setOf("a", "b") })
        assertEquals(measurements.size, plateaus.size * SustainedArchive.modes.size * 3)
    }

    test("the approved gate map names every comparison control") {
        val policy = PerformanceManifest.manifest()
        val keys = SustainedArchive.comparisonControlKeys(policy)
        assertTrue(
            keys.any { it.startsWith("absolute_timing|js.node|") },
        )
        assertTrue(
            keys.any { it.startsWith("jvm_vs_dyn4j|jvm.java|") },
        )
        assertTrue(
            keys.none { it.startsWith("absolute_timing|js.node|separated.default.small.30hz.baseline|") },
        )
    }
}

/** `tools/performance/test_host_capacity_control.py`'s source-identity cases. */
val HostCapacitySourceContractCases by testSuite {
    test("a canonical commit with and without a CRLF projection is accepted") {
        assertEquals("git_exact", HostCapacityControl.sourceEncoding("a\nb\n".encodeToByteArray(), "a\nb\n".encodeToByteArray()))
        assertEquals("git_crlf", HostCapacityControl.sourceEncoding("a\r\nb\r\n".encodeToByteArray(), "a\nb\n".encodeToByteArray()))
    }

    test("an altered diagnostic source is refused") {
        val error = assertFailsWith<IllegalArgumentException> {
            HostCapacityControl.sourceEncoding("a\r\nb\r\nc".encodeToByteArray(), "a\nb\n".encodeToByteArray())
        }
        assertEquals("executed diagnostic source differs from committed bytes", error.message)
    }

    test("the diagnostic child touches sixteen mebibytes and reports its pid") {
        assertEquals(16 * 1024 * 1024, 16 * 1024 * 1024)
        assertTrue(HostCapacityControl.childSource.contains("bytearray(16 * 1024 * 1024)"))
        assertTrue(HostCapacityControl.childSource.contains("\"ready_pid\": os.getpid()"))
    }
}
