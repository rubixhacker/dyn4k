package io.github.rubixhacker.harness.migration

import de.infix.testBalloon.framework.core.testSuite
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * `tools/migration/test_fixed_replay.py` replayed against the inputs and outputs the Python
 * implementation produced while running that suite.
 */
val FixedReplayContract by testSuite {
    val section = VectorData.section("fixed_replay") as PyValue.Map
    val streams = section.get("streams") as PyValue.Map

    fun stream(sha: PyValue.Text): List<PyValue> =
        (streams.get(sha.value) as PyValue.Seq).items

    for (case in (section.get("cases") as PyValue.Seq).items) {
        val name = (case.get("case") as PyValue.Text).value
        test("${name.substringBefore('#')} [${name.substringAfter('#')}]") {
            val baseline = stream(case.get("baseline_sha") as PyValue.Text)
            val candidate = stream(case.get("candidate_sha") as PyValue.Text)
            val report = ReplayComparison.compare(baseline, candidate, "a".repeat(64), "b".repeat(64))
            assertEquals((case.get("report_text") as PyValue.Text).value, PyJson.prettyLine(report))
            assertEquals(
                pythonStr(case.get("exit_code")),
                pythonStr(pyInt(if (pyEquals(report.get("status"), pyText("PASSED"))) 0 else 1)),
            )
        }
    }

    test("repeatability detects the first changed step") {
        val records = (section.get("repeatability") as PyValue.Seq).items
        assertEquals(2, records.size)
        for (record in records) {
            val difference = ReplayComparison.repeatabilityDifference(
                (record.get("first") as PyValue.Seq).items,
                (record.get("second") as PyValue.Seq).items,
            )
            val expected = record.get("difference")
            assertEquals(pyJsonText(expected), pyJsonText(difference ?: PyValue.Null))
        }
        val first = (records[0].get("first") as PyValue.Seq).items
        assertEquals(
            "step[1].bodies[0].x",
            (records[0].get("difference").get("path") as PyValue.Text).value,
        )
        assertNull(ReplayComparison.repeatabilityDifference(first, first))
    }

    test("first difference follows Python types, keys, lengths, and tolerances") {
        for (record in (VectorData.section("first_difference") as PyValue.Seq).items) {
            val limits = if ((record.get("limits") as PyValue.Text).value == "default") {
                ReplayContract.LIMITS
            } else {
                emptyMap()
            }
            val difference = ReplayComparison.firstDifference(
                record.get("left"),
                record.get("right"),
                (record.get("path") as PyValue.Text).value,
                limits,
            )
            assertEquals(
                pyJsonText(record.get("result")),
                pyJsonText(difference ?: PyValue.Null),
                (record.get("path") as PyValue.Text).value,
            )
        }
    }

    test("process identity is required and unambiguous") {
        for (record in (VectorData.section("process_identity") as PyValue.Seq).items) {
            val stderr = (record.get("stderr") as PyValue.Text).value
            val recorded = record.get("result") as PyValue.Map
            if (recorded.entries.containsKey("ok")) {
                assertEquals(
                    (recorded.get("ok") as PyValue.Text).value,
                    ReplayComparison.processIdentity(stderr),
                )
            } else {
                val error = assertFailsWith<MigrationFailure> {
                    ReplayComparison.processIdentity(stderr)
                }
                assertEquals((recorded.get("error") as PyValue.Text).value, error.message)
            }
        }
    }

    test("matching fixed streams pass with three compared observations") {
        val cases = (section.get("cases") as PyValue.Seq).items
        val matching = cases.first {
            (it.get("case") as PyValue.Text).value.startsWith("test_matching_fixed_streams_pass")
        }
        val report = ReplayComparison.compare(
            stream(matching.get("baseline_sha") as PyValue.Text),
            stream(matching.get("candidate_sha") as PyValue.Text),
            "a".repeat(64),
            "b".repeat(64),
        )
        assertEquals("PASSED", (report.get("status") as PyValue.Text).value)
        assertEquals(3L, (report.get("compared_observations") as PyValue.Int).value)
        assertTrue(pyEquals(report.get("first_divergence"), PyValue.Null))
    }
}

/** Renders any vector value, including JSON null, for equality checks. */
internal fun pyJsonText(value: PyValue): String =
    PyJson.render(value, indent = 2, sortKeys = true)
