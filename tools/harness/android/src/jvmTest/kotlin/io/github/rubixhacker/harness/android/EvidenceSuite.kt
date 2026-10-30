package io.github.rubixhacker.harness.android

import de.infix.testBalloon.framework.core.testSuite
import java.nio.file.Files
import java.nio.file.Path
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * `tools/android-runtime/test_evidence.py`.
 *
 * The instrumentation transcript parser and lane validator decide whether an installed run produced
 * usable evidence, so every rejection path is exercised here as well as by the golden vectors.
 */
val InstrumentationEvidenceContract by testSuite {
    test("api21 candidate uses an exact short testfile argument") {
        val portable = (0 until 171).map {
            "org.dyn4j.coverage.LongPortableCase" + it.toString().padStart(3, '0') + "Test"
        }
        val prepared = buildJsonObject {
            put(
                "portable_classes",
                kotlinx.serialization.json.JsonArray(portable.map { JsonPrimitive(it) }),
            )
        }
        withTempDirectory { directory ->
            val selection = LaneHost.instrumentationFilter(prepared, "candidate", "debug", "21", directory)
            assertEquals(173, selection.classes.size)
            assertEquals(
                listOf("-e", "testFile", "/data/local/tmp/dyn4k-candidate-debug-classes.txt"),
                selection.arguments,
            )
            val written = Path.of(selection.selectionPath!!)
            assertEquals(selection.classes, pySplitLines(written.toFile().readText()))
            assertTrue(Files.size(written) > 4096)
            val newer = LaneHost.instrumentationFilter(prepared, "candidate", "debug", "37", directory)
            assertEquals(listOf("-e", "class", selection.classes.joinToString(",")), newer.arguments)
            assertNull(newer.selectionPath)
            val baseline = LaneHost.instrumentationFilter(prepared, "baseline", "debug", "21", directory)
            assertEquals(
                listOf("-e", "class", baseline.classes.joinToString(",")),
                baseline.arguments,
            )
            assertNull(baseline.selectionPath)
        }
    }

    test("installed APK hash rejects wrong device bytes") {
        withTempDirectory { directory ->
            val apk = directory.resolve("installed-base.apk")
            apk.toFile().writeBytes("device APK".encodeToByteArray())
            val digest = sha256("device APK".encodeToByteArray())
            assertEquals(digest, LaneHost.verifyInstalledApk(apk, digest).textOrNull("sha256"))
            apk.toFile().writeBytes("forged APK".encodeToByteArray())
            val failure = assertFailsWith<IllegalArgumentException> {
                LaneHost.verifyInstalledApk(apk, digest)
            }
            assertTrue(failure.message!!.contains("installed APK differs"))
        }
    }

    test("accepts distinct executed consumer and portable cases") {
        val raw = """
            INSTRUMENTATION_STATUS: class=ConsumerJourneyTest
            INSTRUMENTATION_STATUS: test=worldAndCallbacks
            INSTRUMENTATION_STATUS_CODE: 1
            INSTRUMENTATION_STATUS: class=ConsumerJourneyTest
            INSTRUMENTATION_STATUS: test=worldAndCallbacks
            INSTRUMENTATION_STATUS_CODE: 0
            INSTRUMENTATION_STATUS: dyn4k_case=org.dyn4j.world.WorldResultTest#resultIsMutable
            INSTRUMENTATION_STATUS: dyn4k_status=PASSED
            INSTRUMENTATION_STATUS_CODE: 0
            INSTRUMENTATION_STATUS: class=PortableSuiteTest
            INSTRUMENTATION_STATUS: test=allPortableCases
            INSTRUMENTATION_STATUS_CODE: 0
            INSTRUMENTATION_RESULT: stream=
            OK (2 tests)
            INSTRUMENTATION_CODE: -1

        """.trimIndent() + "\n"
        val result = Evidence.parseInstrumentation(raw)
        assertEquals(2, result.instrumentation.passed)
        assertEquals(1, result.portable.passed)
        Evidence.validateLane(
            result,
            setOf("org.dyn4j.world.WorldResultTest#resultIsMutable"),
            setOf("ConsumerJourneyTest#worldAndCallbacks", "PortableSuiteTest#allPortableCases"),
            0,
        )
    }

    test("rejects missing portable case") {
        val raw =
            "INSTRUMENTATION_STATUS: class=Suite\nINSTRUMENTATION_STATUS: test=passes\n" +
                "INSTRUMENTATION_STATUS_CODE: 0\nOK (1 test)\nINSTRUMENTATION_CODE: -1\n"
        val result = Evidence.parseInstrumentation(raw)
        val failure = assertFailsWith<IllegalArgumentException> {
            Evidence.validateLane(result, setOf("Missing#test"), setOf("Suite#passes"), 0)
        }
        assertTrue(failure.message!!.contains("missing"))
    }

    test("rejects skipped case") {
        val raw = """
            INSTRUMENTATION_STATUS: dyn4k_case=Suite#test
            INSTRUMENTATION_STATUS: dyn4k_status=SKIPPED
            INSTRUMENTATION_STATUS_CODE: 0
            INSTRUMENTATION_STATUS: class=Suite
            INSTRUMENTATION_STATUS: test=passes
            INSTRUMENTATION_STATUS_CODE: 0
            OK (1 test)
            INSTRUMENTATION_CODE: -1

        """.trimIndent() + "\n"
        val failure = assertFailsWith<IllegalArgumentException> {
            Evidence.validateLane(
                Evidence.parseInstrumentation(raw),
                setOf("Suite#test"),
                setOf("Suite#passes"),
                0,
            )
        }
        assertTrue(failure.message!!.contains("skipped"))
    }

    test("rejects duplicate case") {
        val raw = """
            INSTRUMENTATION_STATUS: dyn4k_case=Suite#test
            INSTRUMENTATION_STATUS: dyn4k_status=PASSED
            INSTRUMENTATION_STATUS_CODE: 0
            INSTRUMENTATION_STATUS: dyn4k_case=Suite#test
            INSTRUMENTATION_STATUS: dyn4k_status=PASSED
            INSTRUMENTATION_STATUS_CODE: 0
            OK (1 test)
            INSTRUMENTATION_CODE: -1

        """.trimIndent() + "\n"
        val failure = assertFailsWith<IllegalArgumentException> {
            Evidence.parseInstrumentation(raw)
        }
        assertTrue(failure.message!!.contains("duplicate"))
    }

    test("retains multiline failure cause") {
        val raw = """
            INSTRUMENTATION_STATUS: class=Suite
            INSTRUMENTATION_STATUS: test=fails
            INSTRUMENTATION_STATUS: stack=java.lang.AssertionError
            Caused by: java.lang.LinkageError: method became final
            INSTRUMENTATION_STATUS_CODE: -2
            OK (1 test)
            INSTRUMENTATION_CODE: -1

        """.trimIndent() + "\n"
        val result = Evidence.parseInstrumentation(raw)
        val stack = result.instrumentation.cases.getValue("Suite#fails").stack
        assertTrue(stack!!.contains("LinkageError"))
    }

    test("rejects failed duplicate or nonterminal runner code") {
        val cases = "INSTRUMENTATION_STATUS: class=Suite\n" +
            "INSTRUMENTATION_STATUS: test=passes\n" +
            "INSTRUMENTATION_STATUS_CODE: 0\n" +
            "INSTRUMENTATION_RESULT: stream=\n" +
            "OK (1 test)\n"
        for (suffix in listOf(
            "INSTRUMENTATION_CODE: 0\n",
            "INSTRUMENTATION_CODE: -1\nINSTRUMENTATION_CODE: -1\n",
            "INSTRUMENTATION_CODE: -1\ntrailing output\n",
        )) {
            assertFailsWith<IllegalArgumentException>(suffix) {
                Evidence.validateLane(
                    Evidence.parseInstrumentation(cases + suffix),
                    emptySet(),
                    setOf("Suite#passes"),
                    0,
                )
            }
        }
    }

    test("rejects missing duplicate or inconsistent summary") {
        val case = "INSTRUMENTATION_STATUS: class=Suite\n" +
            "INSTRUMENTATION_STATUS: test=passes\n" +
            "INSTRUMENTATION_STATUS_CODE: 0\n" +
            "INSTRUMENTATION_RESULT: stream=\n"
        for (summary in listOf(
            "",
            "OK (2 tests)\n",
            "OK (0 tests)\n",
            "OK (1 test)\nOK (1 test)\n",
            "OK (1 test)\nother final result\n",
            "FAILURES!!!\nTests run: 1,  Failures: 1\n",
        )) {
            assertFailsWith<IllegalArgumentException>(summary) {
                Evidence.validateLane(
                    Evidence.parseInstrumentation(case + summary + "INSTRUMENTATION_CODE: -1\n"),
                    emptySet(),
                    setOf("Suite#passes"),
                    0,
                )
            }
        }
    }

    test("rejects summary before case execution") {
        val raw = "OK (1 test)\n" +
            "INSTRUMENTATION_STATUS: class=Suite\n" +
            "INSTRUMENTATION_STATUS: test=passes\n" +
            "INSTRUMENTATION_STATUS_CODE: 0\n" +
            "INSTRUMENTATION_CODE: -1\n"
        assertFailsWith<IllegalArgumentException> {
            Evidence.validateLane(
                Evidence.parseInstrumentation(raw),
                emptySet(),
                setOf("Suite#passes"),
                0,
            )
        }
    }

    test("rejects failed instrumentation process exit") {
        val raw = """
            INSTRUMENTATION_STATUS: class=Suite
            INSTRUMENTATION_STATUS: test=passes
            INSTRUMENTATION_STATUS_CODE: 0
            INSTRUMENTATION_RESULT: stream=
            OK (1 test)
            INSTRUMENTATION_CODE: -1

        """.trimIndent() + "\n"
        val failure = assertFailsWith<IllegalArgumentException> {
            Evidence.validateLane(
                Evidence.parseInstrumentation(raw),
                emptySet(),
                setOf("Suite#passes"),
                1,
            )
        }
        assertTrue(failure.message!!.contains("process exit"))
    }
}
