package io.github.rubixhacker.harness.baseline

import de.infix.testBalloon.framework.core.testSuite
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

/**
 * The two literals the port must reproduce byte for byte: the JUnit runner source `execute` writes,
 * and the `subprocess.CalledProcessError` message a failed command raises.
 *
 * Both are recorded from `verify.py`, so a change to either is visible here rather than in a run
 * summary that merely looks plausible.
 */
val HarnessLiteralCases by testSuite {
    test("the JUnit runner source is the Python literal") {
        assertEquals(Vectors.harness.str("report_harness"), REPORT_HARNESS)
    }

    test("a failed command raises the Python CalledProcessError message") {
        val failure = assertFailsWith<CommandFailure> {
            requireRunSucceeding(listOf("sh", "-c", "exit 3"))
        }
        assertEquals(
            "Command '['sh', '-c', 'exit 3']' returned non-zero exit status 3.",
            failure.message,
        )
        assertEquals(listOf("sh", "-c", "exit 3"), failure.command)
        assertEquals(3, failure.exitCode)
    }

    test("a successful command returns its captured streams") {
        val output = seams.requireRun(listOf("sh", "-c", "printf 'out'; printf 'err' 1>&2"))
        assertEquals(0, output.exitCode)
        assertEquals("out", output.stdoutText())
        assertEquals("err", output.stderrText())
    }

    test("text mode decodes the universal newlines subprocess.run uses") {
        val output = seams.run(listOf("sh", "-c", "printf 'a\\r\\nb\\rc'"), null)
        assertEquals("a\nb\nc", output.stdoutText())
    }

    test("the tool refuses a source path that is not a git checkout") {
        withCase { root ->
            val plain = root.resolve("plain")
            makeDirectories(plain)
            val error = assertFailsWith<IllegalArgumentException> {
                pinnedGit(seams, plain, listOf("status"))
            }
            assertEquals("source path is not a Git checkout: $plain", error.message)
            assertTrue(error.message!!.endsWith("plain"))
        }
    }
}

private fun requireRunSucceeding(command: List<String>) = seams.requireRun(command)
