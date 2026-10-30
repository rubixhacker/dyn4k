package io.github.rubixhacker.harness.performance

import de.infix.testBalloon.framework.core.testSuite
import kotlinx.serialization.json.jsonPrimitive
import java.io.File
import java.nio.file.Files
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

/** Locates the JDK and the pinned baseline jar the host adapter has to work against. */
private object Toolchain {
    fun repoRoot(): File? {
        var candidate: File? = File("").absoluteFile
        while (candidate != null) {
            if (File(candidate, "tools/performance/BaselinePilot.java").isFile) return candidate
            candidate = candidate.parentFile
        }
        return null
    }

    fun jdkHome(): File? {
        val candidates = mutableListOf<String?>()
        candidates.add(System.getProperty("java.home"))
        candidates.add(System.getenv("JAVA_HOME"))
        candidates.add(
            "${System.getProperty("user.home")}/.local/share/JetBrains/Toolbox/apps/" +
                "android-studio/jbr",
        )
        for (candidate in candidates) {
            if (candidate == null) continue
            val home = File(candidate)
            if (File(home, "bin/javac").isFile && File(home, "bin/java").isFile) return home
        }
        return null
    }

    fun baselineJar(): File? {
        val injected = System.getProperty("performance.baselineJar")
        if (injected != null && File(injected).isFile) return File(injected)
        val cache = File(
            System.getProperty("user.home"),
            ".gradle/caches/modules-2/files-2.1/org.dyn4j/dyn4j/6.0.0",
        )
        if (!cache.isDirectory) return null
        return Files.walk(cache.toPath(), 3).use { stream ->
            stream.filter { it.fileName.toString() == "dyn4j-6.0.0.jar" }
                .findFirst()
                .map { it.toFile() }
                .orElse(null)
        }
    }

    fun describeMissing(jdk: File?, jar: File?): String = buildString {
        append("the JVM host adapter cannot be exercised here")
        if (jdk == null) {
            append(": no JDK with bin/javac was found under java.home (")
            append(System.getProperty("java.home"))
            append("), JAVA_HOME, or the Toolbox JBR")
        }
        if (jar == null) {
            append(": no dyn4j-6.0.0.jar was supplied as performance.baselineJar")
            append(" or found in the Gradle cache")
        }
    }
}

private val jdkHome: File? = Toolchain.jdkHome()
private val baselineJar: File? = Toolchain.baselineJar()
private val sourcesDir: File? = Toolchain.repoRoot()?.resolve("tools/performance")

private fun tempDirectory(prefix: String): File =
    Files.createTempDirectory(prefix).toFile().apply { deleteOnExit() }

private fun sha256Hex(text: String): String =
    io.github.rubixhacker.harness.contract.Sha256.of(text)

/**
 * `warmup_probe.py`, `calibrate.py`, and `ccd_route_trace.py` are built on the JVM host
 * adapter, so these cases run the real `javac`, the real pinned dyn4j jar, and a real child
 * process. The numbers are host-dependent and are asserted structurally; the digest of the
 * pinned jar is the one `manifest.py` recorded, so that check is a true cross-implementation
 * comparison.
 */
val MeasureHostCases by testSuite {
    if (jdkHome == null || baselineJar == null || sourcesDir == null) {
        test("the JVM host adapter prerequisites are reported, not assumed") {
            val reason = Toolchain.describeMissing(jdkHome, baselineJar) +
                if (sourcesDir == null) ": no repository root holding tools/performance" else ""
            assertTrue(reason.contains("cannot be exercised here"), reason)
            assertTrue(
                (jdkHome != null && baselineJar != null && sourcesDir != null),
                reason,
            )
        }
    } else {
        val java = File(jdkHome, "bin/java").absolutePath
        val javac = File(jdkHome, "bin/javac").absolutePath
        val sharedClasses: String by lazy {
            MeasureHost.compileHarness(
                javac,
                baselineJar.absolutePath,
                tempDirectory("dyn4k-shared-work-").absolutePath,
                sourcesDir.absolutePath,
            )
        }
        fun classesOrCompile(): String = sharedClasses

        test("the pinned baseline jar digests to the digest the policy records") {
            assertEquals(
                PerformanceManifest.BASELINE_JAR_SHA256,
                MeasureHost.sha256(baselineJar.absolutePath),
            )
        }

        test("jarPath accepts the pinned jar and rejects an altered copy") {
            assertEquals(
                baselineJar.absoluteFile.toPath().normalize().toString(),
                MeasureHost.jarPath(tempDirectory("dyn4k-jar-").absolutePath, baselineJar.absolutePath),
            )
            val altered = File(tempDirectory("dyn4k-jar-bad-"), "dyn4j-6.0.0.jar")
            altered.writeBytes(baselineJar.readBytes() + byteArrayOf(0))
            val error = assertFailsWith<IllegalArgumentException> {
                MeasureHost.jarPath(tempDirectory("dyn4k-jar-work-").absolutePath, altered.absolutePath)
            }
            assertTrue(
                (error.message ?: "").startsWith("baseline artifact SHA-256 mismatch: "),
                error.message,
            )
        }

        test("compileHarness compiles both harness sources against the pinned jar") {
            val work = tempDirectory("dyn4k-harness-")
            val classes = MeasureHost.compileHarness(
                javac = javac,
                jar = baselineJar.absolutePath,
                work = work.absolutePath,
                sourcesDir = sourcesDir.absolutePath,
            )
            for (name in MeasureHost.HARNESS_SOURCES.map { it.removeSuffix(".java") }) {
                assertTrue(
                    File(classes, "$name.class").isFile,
                    "expected $classes/$name.class",
                )
            }
        }

        test("compileHarness refuses to reuse an existing classes directory") {
            val work = tempDirectory("dyn4k-harness-taken-")
            File(work, "classes").mkdir()
            assertFailsWith<java.nio.file.FileAlreadyExistsException> {
                MeasureHost.compileHarness(javac, baselineJar.absolutePath, work.absolutePath, sourcesDir.absolutePath)
            }
        }

        test("hostIdentity names the host and the exact runtime") {
            val identity = MeasureHost.hostIdentity(java)
            assertEquals(
                setOf(
                    "hostname", "machine", "system", "release", "os_version", "product_name",
                    "product_version", "cpu_model", "ram_kib", "java_version", "power_mode",
                    "charging_state", "temperature_c", "throttling",
                ),
                identity.keys,
            )
            assertEquals(
                when {
                    System.getProperty("os.name").startsWith("Linux") -> "Linux"
                    System.getProperty("os.name").startsWith("Mac") -> "Darwin"
                    else -> "Windows"
                },
                identity.str("system"),
            )
            assertTrue((identity.str("java_version")).contains("version"), identity.str("java_version"))
            assertTrue(identity.str("hostname").isNotEmpty())
            assertTrue(identity.getValue("ram_kib").jsonPrimitive.content.toLong() > 0)
            assertEquals(
                "null",
                identity.getValue("power_mode").canonicalText(),
            )
        }

        test("runCapture writes stdout and returns the child's stderr") {
            val output = File(tempDirectory("dyn4k-capture-"), "out.csv")
            val stderrPath = File(output.parentFile, "out.stderr")
            val (error, pid) = MeasureHost.runCapture(
                command = listOf("/bin/sh", "-c", "printf body; printf complaint 1>&2"),
                output = output.absolutePath,
                stderrPath = stderrPath.absolutePath,
            )
            assertEquals("body", output.readText())
            assertEquals("complaint", error)
            assertEquals("complaint", stderrPath.readText())
            assertTrue(pid > 0)
        }

        test("a runner that fails is reported with its exit code and stderr") {
            val output = File(tempDirectory("dyn4k-capture-fail-"), "out.csv")
            val error = assertFailsWith<MeasureHost.RunnerTerminated> {
                MeasureHost.runCapture(
                    command = listOf("/bin/sh", "-c", "printf boom 1>&2; exit 3"),
                    output = output.absolutePath,
                )
            }
            assertEquals("runner failed (3): boom", error.message)
        }

        test("a bounded capture stops the child at the wall ceiling and retains the record") {
            val output = File(tempDirectory("dyn4k-capture-bound-"), "out.csv")
            val error = assertFailsWith<MeasureHost.RunnerTerminated> {
                MeasureHost.runCapture(
                    command = listOf("/bin/sh", "-c", "sleep 5"),
                    output = output.absolutePath,
                    timeoutSeconds = 0.2,
                )
            }
            val message = error.message ?: ""
            assertTrue(message.startsWith("runner terminated: wall_time_ceiling, exit "), message)
            assertTrue(message.endsWith("; raw files retained"), message)
            val termination = File(MeasureHost.withSuffix(output.absolutePath, ".termination.json"))
            assertTrue(termination.isFile, "expected $termination")
            assertTrue(termination.readText().contains("\"reason\": \"wall_time_ceiling\""))
        }

        test("withSuffix replaces only the final suffix") {
            assertEquals("/a/b.termination.json", MeasureHost.withSuffix("/a/b.csv", ".termination.json"))
            assertEquals("/a/b.stderr", MeasureHost.withSuffix("/a/b", ".stderr"))
            assertEquals("/a/c.d.termination.json", MeasureHost.withSuffix("/a/c.d.csv", ".termination.json"))
        }

        test("runScenario produces a record its own raw stream reproduces") {
            val out = tempDirectory("dyn4k-scenario-")
            val work = tempDirectory("dyn4k-scenario-work-")
            val classes = MeasureHost.compileHarness(
                javac,
                baselineJar.absolutePath,
                work.absolutePath,
                sourcesDir.absolutePath,
            )
            val result = MeasureHost.runScenario(
                java = java,
                classes = classes,
                jar = baselineJar.absolutePath,
                out = out.absolutePath,
                family = "pile",
                variant = "default",
                size = "small",
                hz = 60,
                steps = 2,
                mode = "timing",
                warmup = 2,
                repeat = 1,
            )
            assertEquals(2, result.int("samples"))
            assertEquals("pilot_only", result.str("status"))
            assertEquals(2, result.int("warmup_steps"))
            assertEquals("pile", result.str("family"))
            assertTrue(result.getValue("process_pid").jsonPrimitive.content.toLong() > 0)

            val raw = File(out, result.str("raw"))
            assertTrue(raw.isFile, "expected $raw")
            assertEquals(MeasureHost.sha256(raw.absolutePath), result.str("raw_sha256"))

            // The record must be exactly what the raw stream says, re-derived.
            val rows = Measure.validateCsv(
                Csv.parse(raw.readText()),
                "pile",
                "default",
                "small",
                60,
                2,
                "timing",
            )
            val derived = Measure.summary(rows, 60, "timing")
            for (field in listOf(
                "median_step_ns", "p95_step_ns", "p99_step_ns", "max_step_ns",
                "compute_seconds_per_simulated_second", "max_lateness_ns", "overrun_steps",
                "last_contact_begins", "last_awake", "peak_broadphase_candidates",
                "peak_rss_delta_bytes", "event_only_full", "event_only_final_minute",
            )) {
                assertEquals(
                    derived.getValue(field).canonicalText(),
                    result.getValue(field).canonicalText(),
                    field,
                )
            }
            assertEquals(
                Analyze.activityStatus(rows, "pile", "default", 100, 60),
                result.str("activity_status"),
            )

            // The warm-up stream is separated from its metadata, and the copy is byte-identical.
            val warmup = File(out, result.str("warmup_raw"))
            val warmupLines = CandidatePilot.splitLines(warmup.readText())
            assertTrue(warmupLines.none { it.startsWith("#") }, "warm-up stream still carries markers")
            // The stream keeps its CSV header; only the marker lines were lifted out.
            assertEquals(2, Csv.parse(warmup.readText()).rows.size)
            assertEquals(
                "warmup_step",
                Csv.parse(warmup.readText()).fieldNames?.first(),
            )
            // `stderr_raw` is the copy taken before the markers were lifted out of the stream.
            val stderrRaw = File(out, result.str("stderr_raw"))
            val stderrText = stderrRaw.readText()
            assertTrue(stderrText.contains("#construction_ns="), "stderr copy lost its markers")
            assertEquals(
                warmup.readText(),
                CandidatePilot.splitLines(stderrText).filter { !it.startsWith("#") }.joinToString("\n") + "\n",
            )
            assertEquals(MeasureHost.sha256(warmup.absolutePath), result.str("warmup_sha256"))
            assertEquals(MeasureHost.sha256(stderrRaw.absolutePath), result.str("stderr_sha256"))

            for (marker in MeasureHost.REQUIRED_METADATA) {
                assertEquals(
                    true,
                    result.keys.contains(
                        when (marker) {
                            "construction_ns" -> "cold_construction_ns"
                            "construction_allocated_bytes" -> "cold_construction_allocated_bytes"
                            else -> marker
                        },
                    ),
                    marker,
                )
            }
        }

        test("runScenario rejects a warm-up stream without the construction markers") {
            val out = tempDirectory("dyn4k-scenario-barren-")
            val error = assertFailsWith<IllegalArgumentException> {
                MeasureHost.runScenario(
                    java = java,
                    classes = classesOrCompile(),
                    jar = baselineJar.absolutePath,
                    out = out.absolutePath,
                    family = "pile",
                    variant = "default",
                    size = "small",
                    hz = 60,
                    steps = 2,
                    mode = "timing",
                    warmup = 2,
                    repeat = 1,
                    api = "direct_kotlin",
                    runner = "/bin/true",
                )
            }
            assertEquals("missing construction or retained-memory sample", error.message)
        }

        test("runScenario rejects a candidate route that does not identify itself") {
            val script = File(tempDirectory("dyn4k-fake-runner-"), "runner.sh")
            script.writeText(
                """
                #!/bin/sh
                echo '#construction_ns=1' 1>&2
                echo '#construction_allocated_bytes=1' 1>&2
                echo '#rss_empty_harness_bytes=1' 1>&2
                echo '#rss_after_construction_bytes=2' 1>&2
                echo '#retained_heap_world_alive_bytes=-1' 1>&2
                echo '#retained_collection_count_delta=-1' 1>&2
                exit 0
                """.trimIndent() + "\n",
            )
            script.setExecutable(true)
            val out = tempDirectory("dyn4k-scenario-unmarked-")
            val error = assertFailsWith<IllegalArgumentException> {
                MeasureHost.runScenario(
                    java = java,
                    classes = classesOrCompile(),
                    jar = baselineJar.absolutePath,
                    out = out.absolutePath,
                    family = "pile",
                    variant = "default",
                    size = "small",
                    hz = 60,
                    steps = 2,
                    mode = "timing",
                    warmup = 2,
                    repeat = 1,
                    api = "direct_kotlin",
                    runner = script.absolutePath,
                )
            }
            assertEquals(
                "candidate process or route identity differs from the launcher",
                error.message,
            )
        }
    }
}
