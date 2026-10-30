package io.github.rubixhacker.harness.numerical

import de.infix.testBalloon.framework.core.testSuite
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.jsonObject
import kotlin.test.assertEquals
import kotlin.test.assertTrue

private val vectors = parseVectors(WITNESS_VECTORS)

/**
 * `numeric_class_witness.read_witness`, replayed from the crafted-witness cases of
 * `tools/numerical/portable/test_numeric_class_witness.py`.
 *
 * `build_agent` is not ported: it runs `javac` and writes a byte-exact stored ZIP, so the cases
 * that compile the agent are absent here rather than weakened.
 */
val ClassWitnessContract by testSuite {
    test("every recorded witness is read or rejected exactly as Python does") {
        val cases = vectors.array("cases")
        assertTrue(cases.size >= 16)
        for (element in cases) {
            val scenario = element.jsonObject
            val raw = base64Decode(scenario.str("raw_base64"))
            val expected = scenario.obj("expected_classes").mapValues {
                base64Decode(it.value.stringOrNull().orEmpty())
            }
            val origins = scenario["expected_origins"].let {
                if (it is JsonNull) null else scenario.obj("expected_origins")
                    .mapValues { entry -> entry.value.stringOrNull().orEmpty() }
            }
            assertOutcome(scenario.obj("outcome")) {
                NumericClassWitness.readWitness(
                    raw,
                    expected,
                    origins,
                    scenario.str("profile"),
                )
            }
        }
    }

    test("the accepted witness reports the callback and load sequence") {
        val good = vectors.array("cases")[0].jsonObject
        assertEquals("good", good.str("name"))
        val expected = good.obj("expected_classes").mapValues {
            base64Decode(it.value.stringOrNull().orEmpty())
        }
        val result = NumericClassWitness.readWitness(
            base64Decode(good.str("raw_base64")),
            expected,
            good.obj("expected_origins").mapValues { it.value.stringOrNull().orEmpty() },
        )
        assertEquals("class-witness/2", result.str("schema"))
        assertEquals(3, result.array("helpers").size)
        assertEquals(1, result.array("definitions").size)
        assertEquals("java:1", result.array("definitions")[0].jsonObject.str("thread"))
        assertEquals("L1", result.array("loaded")[0].jsonObject.str("loader"))
        assertEquals(64, result.str("sha256").length)
    }

    test("the boolean profile reports the transform focus record") {
        val cases = vectors.array("cases").associateBy { it.jsonObject.str("name") }
        val valid = cases.getValue("boolean-valid").jsonObject
        val expected = valid.obj("expected_classes").mapValues {
            base64Decode(it.value.stringOrNull().orEmpty())
        }
        val origins = valid.obj("expected_origins").mapValues {
            it.value.stringOrNull().orEmpty()
        }
        val result = NumericClassWitness.readWitness(
            base64Decode(valid.str("raw_base64")),
            expected,
            origins,
            "boolean",
        )
        assertEquals("class-witness/3", result.str("schema"))
        assertEquals("org/dyn4j/geometry/Transform", result.obj("focus").str("name"))
        assertEquals(1, result.obj("focus").int("ordinal"))
        val missing = cases.getValue("boolean-no-focus").jsonObject
        assertOutcome(missing.obj("outcome")) {
            NumericClassWitness.readWitness(
                base64Decode(missing.str("raw_base64")),
                expected,
                origins,
                "boolean",
            )
        }
    }

    test("a non-ASCII witness is rejected") {
        val failure = kotlin.test.assertFailsWith<Rejected> {
            NumericClassWitness.readWitness(
                byteArrayOf(0x80.toByte(), '\n'.code.toByte()),
                emptyMap(),
            )
        }
        assertEquals("class witness is not ASCII", failure.message)
    }

    test("a zero-length witness is rejected as incomplete") {
        val failure = kotlin.test.assertFailsWith<Rejected> {
            NumericClassWitness.readWitness(ByteArray(0), emptyMap())
        }
        assertEquals("class witness is incomplete or oversized", failure.message)
    }

    test("an unknown profile is rejected") {
        val failure = kotlin.test.assertFailsWith<Rejected> {
            NumericClassWitness.readWitness("x\n".encodeToByteArray(), emptyMap(), null, "other")
        }
        assertEquals("class witness profile differs", failure.message)
    }
}

private val BASE64 =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"

/** A minimal standard base64 decoder; the common source set has no codec. */
internal fun base64Decode(text: String): ByteArray {
    val out = ArrayList<Byte>(text.length * 3 / 4 + 3)
    var accumulator = 0
    var bits = 0
    for (character in text) {
        if (character == '=' || character == '\n' || character == '\r') continue
        val value = BASE64.indexOf(character)
        require(value >= 0) { "invalid base64 character: $character" }
        accumulator = (accumulator shl 6) or value
        bits += 6
        if (bits >= 8) {
            bits -= 8
            out.add(((accumulator ushr bits) and 0xFF).toByte())
        }
    }
    return out.toByteArray()
}
