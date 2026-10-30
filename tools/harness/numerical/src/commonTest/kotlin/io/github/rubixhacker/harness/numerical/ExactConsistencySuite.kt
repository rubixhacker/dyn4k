package io.github.rubixhacker.harness.numerical

import de.infix.testBalloon.framework.core.testSuite
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject

private val vectors = parseVectors(EXACT_VECTORS)

/**
 * `exact_consistency`: the snapshot, impulse, timestep and endpoint contracts, replayed from
 * `tools/numerical/portable/test_exact_consistency.py`.
 */
val ExactConsistencyContract by testSuite {
    test("every recorded snapshot check reproduces the Python outcome") {
        var checked = 0
        for (element in vectors.array("checks")) {
            val scenario = element.jsonObject
            val name = scenario.str("name")
            assertOutcomeUnit(scenario.obj("outcome")) {
                when (scenario.str("call")) {
                    "check_snapshot" -> ExactConsistency.checkSnapshot(
                        scenario["state"],
                        scenario.str("phase"),
                        scenario["prior"] as? JsonObject,
                    )
                    "check_impulse" -> ExactConsistency.checkImpulse(
                        scenario["before"],
                        scenario["after"],
                    )
                    "check_time_step" -> ExactConsistency.checkTimeStep(
                        scenario["value"],
                        scenario.int("hz"),
                        scenario.int("step"),
                    )
                    "check_endpoint" -> ExactConsistency.checkEndpoint(
                        scenario["endpoint"],
                        scenario["inner"] as JsonObject,
                        scenario.int("outerHz"),
                    )
                    else -> error("unknown call in $name")
                }
            }
            checked += 1
        }
        check(checked >= 15) { "expected the whole recorded scenario set, ran $checked" }
    }
}
