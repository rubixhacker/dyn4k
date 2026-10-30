package io.github.rubixhacker.harness.compatibility

import de.infix.testBalloon.framework.core.testSuite
import kotlinx.serialization.json.jsonObject
import kotlin.test.assertEquals

private val seams = Vectors.governingSeams

/**
 * `test_governing_seams.py` cases 3 and 4, which are the pure part of that suite. Cases 1, 2, 5, and
 * 6 need the pinned archives, the fixture compilation, and the JaCoCo analysis, so they stay with
 * the unported `capture` and `check`.
 */
val GoverningSeamsContract by testSuite {
    test("recorded lane environments replay") {
        for (case in seams.array("env").map { it.jsonObject }) {
            val environment = case.obj("env").stringMap()
            val recorded = case.array("baseline").map { it.textOrNull() }
            val (baselineEnv, baselineOptions) = GoverningSeams.laneEnvironment(environment)
            assertEquals(recorded[0], baselineEnv["JAVA_TOOL_OPTIONS"])
            assertEquals(recorded[1], baselineOptions)

            val candidateRecorded = case.array("candidate").map { it.textOrNull() }
            val (candidateEnv, candidateOptions) =
                GoverningSeams.laneEnvironment(environment, "-Dcoverage.agent=enabled")
            assertEquals(candidateRecorded[0], candidateEnv["JAVA_TOOL_OPTIONS"])
            assertEquals(candidateRecorded[1], candidateOptions)
        }
    }

    test("java options keep the inherited route for both providers") {
        val route = "-Duser.home=/owned/tmp -Djava.io.tmpdir=/owned/tmp"
        val agent = "-Dcoverage.agent=enabled"
        val (baselineEnv, baselineOptions) =
            GoverningSeams.laneEnvironment(mapOf("JAVA_TOOL_OPTIONS" to route))
        val (candidateEnv, candidateOptions) =
            GoverningSeams.laneEnvironment(mapOf("JAVA_TOOL_OPTIONS" to route), agent)

        assertEquals(route, baselineEnv["JAVA_TOOL_OPTIONS"])
        assertEquals(route, baselineOptions)
        assertEquals("$route $agent", candidateEnv["JAVA_TOOL_OPTIONS"])
        assertEquals("$route $agent", candidateOptions)
    }

    test("only one exact java options banner is removed") {
        val options = "-Duser.home=/owned/tmp -Djava.io.tmpdir=/owned/tmp"
        val banner = "Picked up JAVA_TOOL_OPTIONS: $options\n"

        assertEquals(
            "unexpected\n",
            GoverningSeams.stripJavaToolOptionsBanner(banner + "unexpected\n", options),
        )
        assertEquals(banner, GoverningSeams.stripJavaToolOptionsBanner(banner + banner, options))
        assertEquals(
            "Picked up JAVA_TOOL_OPTIONS: $options extra\n",
            GoverningSeams.stripJavaToolOptionsBanner(
                "Picked up JAVA_TOOL_OPTIONS: $options extra\n",
                options,
            ),
        )
        assertEquals(
            "unexpected\n$banner",
            GoverningSeams.stripJavaToolOptionsBanner("unexpected\n$banner", options),
        )
        assertEquals("", GoverningSeams.stripJavaToolOptionsBanner("", options))
        assertEquals(banner, GoverningSeams.stripJavaToolOptionsBanner(banner, null))
        assertEquals(
            "unexpected\n",
            GoverningSeams.stripJavaToolOptionsBanner("unexpected\n", options),
        )
    }

    test("recorded banner cases replay") {
        for (case in seams.array("banner").map { it.jsonObject }) {
            assertEquals(
                case.str("result"),
                GoverningSeams.stripJavaToolOptionsBanner(
                    case.str("stderr"),
                    case.nullableStr("options"),
                ),
            )
        }
    }
}
