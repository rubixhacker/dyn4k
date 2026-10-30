package io.github.rubixhacker.harness.compatibility

import de.infix.testBalloon.framework.core.testSuite
import kotlinx.serialization.json.jsonObject
import kotlin.test.assertEquals

/**
 * The normalisation `execution_probe.ledger_signature` applies before comparing a strict `javap`
 * surface with a class-file member.
 *
 * The Python suite has no direct case for this function; `test_ledger.py` exercises it through the
 * pinned baseline JAR, which the pure port cannot reach.
 */
val ExecutionProbeContract by testSuite {
    test("ledger signatures match the recorded normalisation") {
        for (case in Vectors.executionProbe.array("ledger_signature").map { it.jsonObject }) {
            assertEquals(
                case.str("result"),
                ExecutionProbe.ledgerSignature(case.str("input")),
                case.str("input"),
            )
        }
        assertEquals(
            listOf("ACC_PUBLIC", "ACC_PROTECTED", "ACC_BRIDGE", "ACC_SYNTHETIC"),
            ExecutionProbe.DECLARATION_FLAGS,
        )
    }
}
