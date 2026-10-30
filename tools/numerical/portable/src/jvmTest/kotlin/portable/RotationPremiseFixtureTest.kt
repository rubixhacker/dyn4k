package portable

import de.infix.testBalloon.framework.core.TestConfig
import de.infix.testBalloon.framework.core.testScope
import de.infix.testBalloon.framework.core.testSuite
import kotlin.time.Duration.Companion.minutes
import org.dyn4j.geometry.RotationOperationTap
import org.dyn4j.geometry.Transform

val RotationPremiseFixtureTestSuite by testSuite(
    testConfig = TestConfig.testScope(isEnabled = true, timeout = 60.minutes),
) {
    test("captureRotationPremises") { RotationPremiseFixtureTest().run { captureRotationPremises() } }
}

class RotationPremiseFixtureTest {
    private class SeededTransform : Transform() {
        fun seed(costBits: Long, sintBits: Long) {
            cost = Double.fromBits(costBits)
            sint = Double.fromBits(sintBits)
        }
    }

    private data class PremiseInput(val id: String, val costBits: Long,
        val sintBits: Long, val angleBits: Long)

fun captureRotationPremises() {
        val inputs = listOf(
            PremiseInput("rotation-premise-mode", 0xbfd0cd683f9d3feaUL.toLong(),
                0x3feee0a3e97da062L, 0x4001c867da8b78fcL),
            PremiseInput("rotation-premise-zero", 0x3ff0000000000000L, 0L, 0L),
            PremiseInput("rotation-premise-negative-zero", 0x3ff0000000000000L,
                Long.MIN_VALUE, Long.MIN_VALUE),
            PremiseInput("rotation-premise-tiny-angle", 0x3ff0000000000000L, 0L, 1L),
            PremiseInput("rotation-premise-subnormal-product", 1L, 0L, 0L),
        )
        for (input in inputs) {
            val value = SeededTransform()
            value.seed(input.costBits, input.sintBits)
            val before = premiseState(value)
            println("NUMERICAL_JSON {\"kind\":\"inputs\",\"id\":\"${input.id}\"," +
                "\"steps\":1,\"setup\":{\"bodies\":[{\"id\":\"b0\"}]}," +
                "\"initial\":$before}")
            RotationOperationTap.capture("captureRotationPremises") { scope ->
                value.rotate(Double.fromBits(input.angleBits))
                val observed = scope.drain().single()
                    as RotationOperationTap.Observation.Rotation
                println("PROSPECTIVE_ROTATION_JSON " +
                    ProspectiveOperationMarker.encode(scope, observed.call.copy(
                        caseId = input.id, step = 1, bodyId = "b0", branch = "fixture")))
            }
            println("NUMERICAL_JSON {\"kind\":\"state\",\"id\":\"${input.id}\"," +
                "\"step\":1,\"state\":${premiseState(value)}}")
            println("NUMERICAL_JSON {\"kind\":\"case-end\",\"id\":\"${input.id}\"," +
                "\"steps\":1}")
        }
    }

    private fun premiseState(value: Transform): String =
        "{\"bodies\":[{\"id\":\"b0\",\"transform\":{" +
            "\"getCost\":${value.getCost()},\"getSint\":${value.getSint()}}}]}"
}
