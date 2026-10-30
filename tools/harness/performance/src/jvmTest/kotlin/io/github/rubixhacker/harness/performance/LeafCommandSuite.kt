package io.github.rubixhacker.harness.performance

import de.infix.testBalloon.framework.core.testSuite
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import java.io.ByteArrayOutputStream
import java.io.File
import java.io.PrintStream
import java.nio.file.Files
import kotlin.test.assertEquals
import kotlin.test.assertTrue

private class Recorded {
    private val root: JsonObject = Json.parseToJsonElement(LeafVectors.json).jsonObject

    fun group(name: String): JsonObject = root.getValue(name).jsonObject

    fun text(name: String, key: String): String = group(name).getValue(key).jsonPrimitive.content

    /** One recorded argument-error case: `exit_code`, `stderr`, and the `error:` message. */
    fun failedInvocation(name: String, label: String): JsonObject =
        group(name).getValue(label).jsonObject
}

private class RunResult(val code: Int, val stdout: String, val stderr: String)

/** Runs a ported command and captures what it wrote, without letting it exit the test JVM. */
private fun runCli(command: PortedCommand, vararg args: String): RunResult {
    val out = ByteArrayOutputStream()
    val err = ByteArrayOutputStream()
    val code = PrintStream(out, true, "UTF-8").use { stdout ->
        PrintStream(err, true, "UTF-8").use { stderr ->
            command.run(arrayOf(*args), stdout, stderr)
        }
    }
    return RunResult(code, out.toString("UTF-8"), err.toString("UTF-8"))
}

/**
 * The argument contract of the three leaf commands: which options exist, which are required, the
 * order `argparse` reports failures in, the exact `error:` text, and the exit code.
 *
 * The expected text is the recorded stderr of the Python command, which is why the assertions
 * compare whole lines rather than substrings.
 */
val LeafCommandArgumentCases by testSuite {
    val recorded = Recorded()

    fun usageOf(recorded: String): List<String> =
        recorded.lines().dropLastWhile { it.isEmpty() }.dropLast(1)

    /** The single `error:` line `argparse` prints, which always names the program. */
    fun errorLine(program: String, recordedCase: JsonObject, key: String = "message"): String =
        "$program: error: ${recordedCase.getValue(key).jsonPrimitive.content}"

    test("an empty argument list reports every required option") {
        val result = runCli(WarmupProbeCli)
        assertEquals(2, result.code)
        assertEquals("", result.stdout)
        val lines = result.stderr.lines().filter { it.isNotEmpty() }
        assertEquals(
            "warmup_probe.py: error: the following arguments are required: " +
                "--output, --family, --variant, --size, --hz",
            lines.last(),
        )
        assertEquals(usageOf(recorded.failedInvocation("warmup_probe_arguments", "too_short")
            .getValue("stderr").jsonPrimitive.content).size + 1, lines.size)
    }

    test("a supplied option is dropped from the required list") {
        val result = runCli(WarmupProbeCli, "--output", "/tmp/dyn4k-cli-out")
        assertEquals(2, result.code)
        assertTrue(
            result.stderr.contains(
                "error: the following arguments are required: --family, --variant, --size, --hz",
            ),
            result.stderr,
        )
    }

    test("the usage block and error line match the recorded stderr byte for byte") {
        // The same invocation the reference recorded: a warm-up below the approved floor.
        val recordedCase = recorded.failedInvocation("calibrate_arguments", "short_warmup")
        val result = runCli(
            CalibrateCli,
            "--output", "/tmp/dyn4k-cli-out", "--family", "pile", "--variant", "default",
            "--size", "small", "--hz", "60", "--warmup-seconds", "10",
        )
        assertEquals(recordedCase.getValue("exit_code").jsonPrimitive.content.toInt(), result.code)
        assertEquals(recordedCase.getValue("stderr").jsonPrimitive.content, result.stderr)
    }

    test("the warm-up usage block matches the recorded block line for line") {
        val recordedCase = recorded.failedInvocation("warmup_probe_arguments", "too_short")
        val expectedLines = usageOf(recordedCase.getValue("stderr").jsonPrimitive.content)
        val observed = runCli(WarmupProbeCli).stderr.lines().dropLastWhile { it.isEmpty() }
        assertEquals(expectedLines, observed.dropLast(1))
        assertEquals(
            "warmup_probe.py: error: the following arguments are required: " +
                "--output, --family, --variant, --size, --hz",
            observed.last(),
        )
    }

    test("an unknown family is an invalid choice, not a semantic error") {
        val result = runCli(
            WarmupProbeCli,
            "--output", "/tmp/dyn4k-cli-out",
            "--family", "nope",
            "--variant", "default",
            "--size", "small",
            "--hz", "60",
        )
        assertEquals(2, result.code)
        assertTrue(
            result.stderr.contains(
                "warmup_probe.py: error: argument --family: invalid choice: 'nope' " +
                    "(choose from 'separated', 'pile', 'joint', 'ccd', 'lifecycle')",
            ),
            result.stderr,
        )
    }

    test("an out-of-range rate is an invalid choice and an unparsable one an invalid int") {
        val choice = runCli(
            CalibrateCli,
            "--output", "/tmp/dyn4k-cli-out", "--family", "pile", "--variant", "default",
            "--size", "small", "--hz", "45",
        )
        assertEquals(2, choice.code)
        assertTrue(
            choice.stderr.contains(
                "calibrate.py: error: argument --hz: invalid choice: '45' " +
                    "(choose from '30', '60', '120')",
            ),
            choice.stderr,
        )
        val integer = runCli(
            CalibrateCli,
            "--output", "/tmp/dyn4k-cli-out", "--family", "pile", "--variant", "default",
            "--size", "small", "--hz", "x",
        )
        assertEquals(2, integer.code)
        assertTrue(
            integer.stderr.contains("calibrate.py: error: argument --hz: invalid int value: 'x'"),
            integer.stderr,
        )
    }

    test("an out-of-range size is an invalid choice") {
        val result = runCli(
            WarmupProbeCli,
            "--output", "/tmp/dyn4k-cli-out", "--family", "pile", "--variant", "default",
            "--size", "large", "--hz", "60",
        )
        assertEquals(2, result.code)
        assertTrue(
            result.stderr.contains(
                "error: argument --size: invalid choice: 'large' (choose from 'small', 'medium')",
            ),
            result.stderr,
        )
    }

    test("an option without a value reports the missing argument") {
        val result = runCli(WarmupProbeCli, "--output")
        assertEquals(2, result.code)
        assertTrue(
            result.stderr.contains("error: argument --output: expected one argument"),
            result.stderr,
        )
    }

    test("an unknown option is reported only after the required options are satisfied") {
        val result = runCli(
            WarmupProbeCli,
            "--output", "/tmp/dyn4k-cli-out", "--family", "pile", "--variant", "default",
            "--size", "small", "--hz", "60", "--nope",
        )
        assertEquals(2, result.code)
        assertTrue(
            result.stderr.contains("error: unrecognized arguments: --nope"),
            result.stderr,
        )
    }

    test("--name=value is accepted for every option") {
        val result = runCli(
            WarmupProbeCli,
            "--output=/tmp/dyn4k-cli-out",
            "--family=pile",
            "--variant=default",
            "--size=small",
            "--hz=60",
            "--warmup-seconds=119",
        )
        // Parsing succeeded; the semantic warm-up floor is what rejects it.
        assertEquals(2, result.code)
        assertTrue(
            result.stderr.contains("error: warm-up must be between 120 and 600 seconds"),
            result.stderr,
        )
    }

    test("the warm-up floor and ceiling are semantic errors with the recorded text") {
        for ((name, seconds) in listOf("too_short" to "119", "too_long" to "601")) {
            val recordedCase = recorded.group("warmup_probe_arguments").getValue(name).jsonObject
            val result = runCli(
                WarmupProbeCli,
                "--output", "/tmp/dyn4k-cli-out", "--family", "pile", "--variant", "default",
                "--size", "small", "--hz", "60", "--warmup-seconds", seconds,
            )
            assertEquals(recordedCase.getValue("exit_code").jsonPrimitive.content.toInt(), result.code)
            assertEquals(errorLine("warmup_probe.py", recordedCase), lastError(result.stderr))
        }
    }

    test("a variant outside the frozen family is a semantic error") {
        val warmupCase = recorded.group("warmup_probe_arguments").getValue("unknown_variant").jsonObject
        val warmupResult = runCli(
            WarmupProbeCli,
            "--output", "/tmp/dyn4k-cli-out", "--family", "pile", "--variant", "nope",
            "--size", "small", "--hz", "60",
        )
        assertEquals(2, warmupResult.code)
        assertEquals(errorLine("warmup_probe.py", warmupCase), lastError(warmupResult.stderr))

        val calibrateCase = recorded.group("calibrate_arguments").getValue("unknown_variant").jsonObject
        val calibrateResult = runCli(
            CalibrateCli,
            "--output", "/tmp/dyn4k-cli-out", "--family", "pile", "--variant", "nope",
            "--size", "small", "--hz", "60",
        )
        assertEquals(2, calibrateResult.code)
        assertEquals(errorLine("calibrate.py", calibrateCase), lastError(calibrateResult.stderr))
    }

    test("calibration durations below the approved floor are semantic errors") {
        for (arguments in listOf(
            arrayOf("--warmup-seconds", "10"),
            arrayOf("--measurement-seconds", "29"),
        )) {
            val result = runCli(
                CalibrateCli,
                "--output", "/tmp/dyn4k-cli-out", "--family", "pile", "--variant", "default",
                "--size", "small", "--hz", "60", *arguments,
            )
            assertEquals(2, result.code)
            assertEquals(
                errorLine(
                    "calibrate.py",
                    recorded.failedInvocation("calibrate_arguments", "short_warmup"),
                ),
                lastError(result.stderr),
            )
        }
    }

    test("the trace command requires all four options") {
        val result = runCli(CcdRouteTraceCli)
        assertEquals(2, result.code)
        assertEquals(
            "ccd_route_trace.py: error: the following arguments are required: " +
                "--output, --java, --javac, --jar",
            lastError(result.stderr),
        )
    }

    test("a baseline jar that is not the pinned artifact exits 1 with a ValueError") {
        val directory = Files.createTempDirectory("dyn4k-cli-jar-").toFile()
        val jar = File(directory, "dyn4j-6.0.0.jar")
        jar.writeText("not the pinned baseline")
        val result = runCli(
            CcdRouteTraceCli,
            "--output", File(directory, "out").absolutePath,
            "--java", "java",
            "--javac", "javac",
            "--jar", jar.absolutePath,
        )
        assertEquals(1, result.code)
        assertEquals("", result.stdout)
        assertEquals("ValueError: baseline JAR differs from the pinned artifact", result.stderr.trim())
    }
}

private fun lastError(stderr: String): String = stderr.trim().lines().last()

/**
 * The summaries and report files the commands write must be byte-identical to the recorded
 * Python output: `json.dumps` with default separators for the summary, and
 * `json.dumps(..., indent=2, sort_keys=True)` plus a newline for the report.
 */
val LeafCommandOutputCases by testSuite {
    val recorded = Recorded()

    test("the warm-up probe summary matches the recorded print") {
        val report = recorded.group("warmup_probe").getValue("report").jsonObject
        val line = WarmupProbeCli.summaryText(report.str("warmup_status"), report.str("activity_status"))
        assertEquals(recorded.text("warmup_probe", "stdout_text"), "$line\n")
    }

    test("the warm-up probe report file matches the recorded file") {
        val report = recorded.group("warmup_probe").getValue("report").jsonObject
        assertEquals(
            recorded.text("warmup_probe", "report_text"),
            PythonJson.renderIndented(report, sortKeys = true) + "\n",
        )
    }

    test("the calibration summary matches the recorded print") {
        val group = recorded.group("calibrate")
        val report = group.getValue("report").jsonObject
        val output = group.getValue("stdout").jsonObject.str("output")
        assertEquals(
            group.getValue("stdout_text").jsonPrimitive.content,
            CalibrateCli.summaryText(output, report) + "\n",
        )
    }

    test("the calibration report file matches the recorded file") {
        val report = recorded.group("calibrate").getValue("report").jsonObject
        assertEquals(
            recorded.text("calibrate", "report_text"),
            PythonJson.renderIndented(report, sortKeys = true) + "\n",
        )
    }

    test("the trace summary matches the recorded print") {
        val group = recorded.group("ccd_agreeing")
        val result = group.getValue("result").jsonObject
        val output = group.getValue("stdout").jsonObject.str("output")
        assertEquals(
            group.getValue("stdout_text").jsonPrimitive.content,
            CcdRouteTraceCli.summaryText(output, result.getValue("comparisons").jsonObject) + "\n",
        )
    }

    test("the trace result file matches the recorded file") {
        val result = recorded.group("ccd_agreeing").getValue("result").jsonObject
        assertEquals(
            recorded.text("ccd_agreeing", "result_text"),
            PythonJson.renderIndented(result, sortKeys = true) + "\n",
        )
    }

    test("the indented renderer nests two spaces per level") {
        val value = Json.parseToJsonElement("""{"a":{"b":[1,2]},"c":[]}""")
        assertEquals(
            "{\n  \"a\": {\n    \"b\": [\n      1,\n      2\n    ]\n  },\n  \"c\": []\n}",
            PythonJson.renderIndented(value),
        )
    }
}
