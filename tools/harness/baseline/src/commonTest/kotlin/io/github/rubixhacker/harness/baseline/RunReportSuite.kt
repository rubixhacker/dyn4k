package io.github.rubixhacker.harness.baseline

import de.infix.testBalloon.framework.core.testSuite
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonPrimitive
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith

/**
 * `result_field` and `validate_run_report`: the gate the upstream JUnit run summary must pass before
 * its counts become evidence.
 *
 * The recorded cases are the Python suite's own invalid mutations plus every `result_field` shape a
 * compiler or a corrupted report can produce.
 */
val RunReportCases by testSuite {
    test("result_field reproduces the recorded readings") {
        for (element in Vectors.reports.array("result_field")) {
            val case = element.jsonObject
            assertRecordedInt(case["result"], case.str("label")) {
                resultField(case.str("output"), case.str("label"))
            }
        }
    }

    test("validate_run_report accepts the good report and rejects each recorded mutation") {
        val reports = Vectors.reports.array("validate")
        assertEquals(
            listOf(
                "good",
                "incomplete",
                "ignored",
                "failed",
                "exit",
                "missing_output",
                "nonnumeric",
                "wrong_bytecode",
            ),
            reports.map { it.jsonObject.str("label") },
        )
        for (element in reports) {
            val case = element.jsonObject
            val report = case.obj("report")
            val error = case["error"]?.takeIf { it !is JsonNull }?.jsonPrimitive?.content
            if (error == null) {
                validateRunReport(report)
            } else {
                val thrown = assertFailsWith<IllegalArgumentException>(case.str("label")) {
                    validateRunReport(report)
                }
                assertEquals(error, thrown.message, case.str("label"))
            }
        }
    }

    test("the recorded good report is the one the pinned run produces") {
        validateRunReport(goodReport())
        assertEquals(2385, Baseline.EXPECTED_CASES)
        assertEquals(2385, BaselinePolicy().expectedCases)
    }

    test("a report that is not an object of the pinned shape is rejected") {
        val thrown = assertFailsWith<IllegalArgumentException> {
            validateRunReport(JsonObject(mapOf("output" to JsonNull)))
        }
        assertEquals("run output fields are missing or invalid", thrown.message)
    }

    test("a missing test input hash map is rejected") {
        val report = JsonObject(goodReport().filterKeys { it != "test_input_sha256" })
        val thrown = assertFailsWith<IllegalArgumentException> { validateRunReport(report) }
        assertEquals("missing test input hashes", thrown.message)
    }
}

/** The `good` report the parity payload records, rebuilt from the vectors. */
internal fun goodReport(): JsonObject =
    Vectors.reports.array("validate").first().jsonObject.obj("report")

/** Compares an optional recorded integer with a call that may return null. */
private fun assertRecordedInt(recorded: kotlinx.serialization.json.JsonElement?, label: String, block: () -> Int?) {
    val expected = recorded?.takeIf { it !is JsonNull }?.jsonPrimitive?.content?.toInt()
    assertEquals(expected, block(), label)
}
