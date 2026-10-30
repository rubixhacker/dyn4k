package io.github.rubixhacker.harness.compatibility

import de.infix.testBalloon.framework.core.testSuite
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

private val disposition = Vectors.governingDisposition

private data class ForwarderCase(
    val opcodes: List<Int>,
    val candidateFlags: Int,
    val baselineFlags: List<String>,
    val signature: String,
    val invocationCount: Int,
)

/**
 * `test_governing_disposition.py` case 4, which is the only self-contained case in that suite, plus
 * the recorded parity sweep. Cases 1 to 3 need the gzipped disposition receipt, the ledger, and the
 * pinned upstream checkout, so they stay with the unported host half.
 */
val GoverningDispositionContract by testSuite {
    test("bridge and static forwarder require exact pure dispatch") {
        val bridge = listOf(25, 182, 192, 176)
        val static = listOf(178, 25, 182, 177)
        assertTrue(
            GoverningDisposition.pureForwarder(
                bridge,
                0x1041,
                listOf("ACC_PUBLIC", "ACC_BRIDGE", "ACC_SYNTHETIC"),
                "public org.dyn4j.Copyable copy();",
                1,
            ),
        )
        assertTrue(
            GoverningDisposition.pureForwarder(
                static,
                0x0009,
                listOf("ACC_PUBLIC"),
                "public static void run();",
                1,
            ),
        )
        val rejected = listOf(
            ForwarderCase(
                bridge,
                0x0001,
                listOf("ACC_PUBLIC", "ACC_BRIDGE"),
                "public Copyable copy();",
                1,
            ),
            ForwarderCase(
                static,
                0x0001,
                listOf("ACC_PUBLIC"),
                "public static void run();",
                1,
            ),
            ForwarderCase(
                listOf(25, 182, 153, 176),
                0x1041,
                listOf("ACC_PUBLIC", "ACC_BRIDGE", "ACC_SYNTHETIC"),
                "public Copyable copy();",
                1,
            ),
            ForwarderCase(
                listOf(25, 182, 182, 176),
                0x1041,
                listOf("ACC_PUBLIC", "ACC_BRIDGE", "ACC_SYNTHETIC"),
                "public Copyable copy();",
                2,
            ),
        )
        for (case in rejected) {
            assertFalse(
                GoverningDisposition.pureForwarder(
                    case.opcodes,
                    case.candidateFlags,
                    case.baselineFlags,
                    case.signature,
                    case.invocationCount,
                ),
                "$case",
            )
        }
    }

    test("recorded forwarder sweep replays") {
        val opcodeSets = disposition.array("opcode_sets").map { set ->
            set.jsonArray.map { it.jsonPrimitive.content.toInt() }
        }
        val flagValues = disposition.array("flag_values").map { it.jsonPrimitive.content.toInt() }
        val baselineSets = disposition.array("baseline_sets").map { set ->
            set.jsonArray.map { it.jsonPrimitive.content }
        }
        val signatures = disposition.array("signatures").map { it.jsonPrimitive.content }
        val cases = disposition.array("pure_forwarder")
        assertTrue(cases.size > 1000)
        for (entry in cases) {
            val row = entry.jsonArray
            val opcodes = opcodeSets[row[0].jsonPrimitive.content.toInt()]
            val flags = flagValues[row[1].jsonPrimitive.content.toInt()]
            val baseline = baselineSets[row[2].jsonPrimitive.content.toInt()]
            val signature = signatures[row[3].jsonPrimitive.content.toInt()]
            val calls = row[4].jsonPrimitive.content.toInt()
            assertEquals(
                row[5].jsonPrimitive.content.toBooleanStrict(),
                GoverningDisposition.pureForwarder(opcodes, flags, baseline, signature, calls),
                "$opcodes $flags $baseline $signature $calls",
            )
        }
    }

    test("parameter descriptors match the recorded prefixes") {
        for (case in disposition.array("parameter_descriptor").map { it.jsonObject }) {
            val recorded = case.obj("result")
            val error = recorded["error"]
            if (error == null) {
                assertEquals(
                    recorded.str("ok"),
                    GoverningDisposition.parameterDescriptor(case.str("descriptor")),
                    case.str("descriptor"),
                )
            } else {
                assertRecordedOutcome(recorded) {
                    GoverningDisposition.parameterDescriptor(case.str("descriptor"))
                }
            }
        }
    }
}
