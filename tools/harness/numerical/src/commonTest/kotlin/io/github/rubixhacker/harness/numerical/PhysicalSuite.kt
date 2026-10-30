package io.github.rubixhacker.harness.numerical

import de.infix.testBalloon.framework.core.testSuite
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import kotlinx.serialization.json.jsonObject
import kotlin.test.assertEquals
import kotlin.test.assertTrue

private val vectors = parseVectors(PHYSICAL_VECTORS)

/**
 * `physical`: the analytical free-motion diagnostic and the represented-geometry sleep/wake
 * check, replayed from `tools/numerical/portable/test_physical.py`.
 *
 * The sleep/wake fixtures are the merged views the Python `load_fixture` builds from
 * `tools/numerical/fixtures.json`, projected onto the fields the diagnostic reads.
 */
val PhysicalContract by testSuite {
    test("the nominal free-motion diagnostic reproduces every recorded outcome") {
        val checks = vectors.array("nominal")
        assertEquals(7, checks.size)
        for (element in checks) {
            val scenario = element.jsonObject
            val rows = traceLines(rowsOf(scenario.getValue("rows")))
            assertOutcome(scenario.obj("outcome")) {
                Physical.nominalFree(rows, scenario.int("expected_steps"))
            }
        }
    }

    test("the recorded free-motion failures are reported per component") {
        val checks = vectors.array("nominal").associateBy { it.jsonObject.str("name") }
        val exact = checks.getValue("exact").jsonObject.obj("outcome").element("result").jsonObject
        assertEquals("PASSED", exact.str("status"))
        assertEquals(1, exact.int("checked"))
        assertEquals(0, exact.int("failed_samples"))
        val drift = checks.getValue("drift").jsonObject.obj("outcome").element("result").jsonObject
        assertEquals("FAILED", drift.str("status"))
        assertTrue(drift.array("first_failures")[0].jsonObject.containsKey("positionY_m"))
        val shortRun = checks.getValue("exact-default-steps").jsonObject
            .obj("outcome").element("result").jsonObject
        assertEquals("FAILED", shortRun.str("status"))
        assertTrue(
            (shortRun.array("first_failures").last().jsonObject).str("reason")
                .startsWith("expected 36000 long-free states"),
        )
    }

    test("the sleep/wake diagnostic reproduces every recorded outcome") {
        val checks = vectors.array("sleep_wake")
        assertTrue(checks.size >= 5)
        for (element in checks) {
            val scenario = element.jsonObject
            val rows = rowsOf(scenario.getValue("rows"))
            val keys = if (scenario["keys"] is JsonNull) {
                null
            } else {
                scenario.array("keys").map { it.stringOrNull().orEmpty() }
            }
            assertOutcome(scenario.obj("outcome")) {
                Physical.sleepWakeRows(rows, keys, fixtures())
            }
        }
    }

    test("a missing sleep/wake case cannot pass") {
        val empty = vectors.array("sleep_wake")[0].jsonObject.obj("outcome")
            .element("result").jsonObject
        assertEquals("INVALID", empty.str("status"))
        assertEquals(0, empty.obj("cases").obj("default-sleep-30").int("states"))
    }

    test("the phase schedule covers every declared state") {
        for ((key, element) in vectors.obj("fixtures")) {
            val fixture = element.jsonObject
            val schedule = Physical.phasesForFixture(fixture)
            val states = fixture.obj("counts").int("state")
            assertTrue(schedule.isNotEmpty(), "$key has an empty schedule")
            assertEquals(states, schedule.last().third, "$key schedule coverage")
            assertEquals(1, schedule.first().second, "$key schedule start")
        }
    }

    test("a fixture without a phase schedule is rejected") {
        val failure = assertFailsWithRejected {
            Physical.phasesForFixture(
                buildJsonObject {
                    put("id", "x")
                    put("counts", JsonPrimitive(0))
                },
            )
        }
        assertEquals("no approved physical phase schedule", failure)
    }

    test("the declared keys name the approved sleep/wake fixtures") {
        assertEquals(
            listOf(
                "default-sleep-30", "default-sleep-60", "default-sleep-120",
                "configured-30-r1", "configured-30-r2", "configured-60-r1",
                "configured-60-r2", "configured-120-r1", "configured-120-r2",
            ),
            Physical.defaultKeys(),
        )
        assertEquals(
            Physical.defaultKeys().toSet(),
            vectors.obj("fixtures").keys,
        )
    }
}

private fun assertFailsWithRejected(block: () -> Unit): String? {
    val failure = kotlin.test.assertFailsWith<Rejected> { block() }
    return failure.message
}

private fun fixtures(): Map<String, JsonObject> =
    vectors.obj("fixtures").mapValues { it.value.jsonObject }
