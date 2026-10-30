package io.github.rubixhacker.harness.numerical

import de.infix.testBalloon.framework.core.testSuite
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonObject
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith

/**
 * `portable/rotation_oracle.py`: the encoding, digest and pair helpers that do not need an MPFR
 * interval, plus the seam that refuses the rest.
 */
val RotationOracleContract by testSuite {
    test("the binary64 encoding matches the Python struct format") {
        assertEquals("0000000000000000", RotationOracle.bits(0.0))
        assertEquals("8000000000000000", RotationOracle.bits(-0.0))
        assertEquals("3ff0000000000000", RotationOracle.bits(1.0))
        assertEquals("400921fb54442d18", RotationOracle.bits(Math.PI))
        assertEquals(Math.PI, RotationOracle.binary64(JsonPrimitive("400921fb54442d18")))
        assertEquals(-0.0, RotationOracle.binary64(JsonPrimitive("8000000000000000")))
    }

    test("malformed or nonfinite binary64 fields are rejected") {
        assertEquals(
            "invalid binary64 encoding",
            assertFailsWith<IllegalArgumentException> {
                RotationOracle.binary64(JsonPrimitive("3FF0000000000000"))
            }.message,
        )
        assertEquals(
            "nonfinite binary64 field",
            assertFailsWith<IllegalArgumentException> {
                RotationOracle.binary64(JsonPrimitive("7ff0000000000000"))
            }.message,
        )
        assertEquals(
            "incomplete binary64 pair",
            assertFailsWith<IllegalArgumentException> {
                RotationOracle.pair(Json.parseToJsonElement("""["0000000000000000"]"""))
            }.message,
        )
    }

    test("a transform pair encodes the stored cost and sine") {
        val transform = Json.parseToJsonElement("""{"getCost":1.0,"getSint":-0.0}""").jsonObject
        assertEquals(
            "3ff0000000000000" to "8000000000000000",
            RotationOracle.statePair(transform),
        )
    }

    test("the digest helpers render canonical JSON") {
        val value = Json.parseToJsonElement("""{"b":1,"a":[true,null]}""").jsonObject
        assertEquals("""{"a":[true,null],"b":1}""", String(RotationOracle.manifestBytes(value)))
        assertEquals(
            io.github.rubixhacker.harness.contract.Sha256.of("""{"a":[true,null],"b":1}"""),
            RotationOracle.digest(value),
        )
    }

    test("the MPFR-dependent entry points refuse rather than pass") {
        val failure = assertFailsWith<MpfrNotPorted> {
            RotationOracle.verifyRotationArithmetic(null, emptyMap(), ByteArray(0), ByteArray(0), ByteArray(0))
        }
        assertEquals(
            "MPFR is not ported: rotation_oracle.verify_rotation_arithmetic " +
                "(the ctypes binding to libmpfr stays with the Python module)",
            failure.message,
        )
        assertFailsWith<MpfrNotPorted> { RotationOracle.trigInterval(null) }
        assertFailsWith<MpfrNotPorted> { RotationOracle.verifyOperationMarker(null) }
    }
}
