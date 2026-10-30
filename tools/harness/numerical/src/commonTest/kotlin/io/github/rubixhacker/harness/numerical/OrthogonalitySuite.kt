package io.github.rubixhacker.harness.numerical

import de.infix.testBalloon.framework.core.testSuite
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

private val vectors = parseVectors(ORTHOGONALITY_VECTORS)

/**
 * `orthogonality`: the exact rational error bound and the rotation source caps.
 *
 * The bound is the closed-form `orthogonality_ulps` table; the recorded values are the ones the
 * Python reference computes with `fractions.Fraction` and `math.isqrt`.
 */
val OrthogonalityContract by testSuite {
    test("the direct trig reset bound matches") {
        assertEquals(vectors.int("direct_reset_ulps"), Orthogonality.directResetUlps.toInt())
    }

    test("the cumulative orthogonality bound matches at every recorded rotation count") {
        val recorded = vectors.obj("ulps")
        for ((count, expected) in recorded) {
            assertEquals(
                expected.jsonNumberLong(),
                Orthogonality.orthogonalityUlps(count.toInt()),
                "rotations $count",
            )
        }
    }

    test("the bound grows monotonically across the approved domain") {
        var previous = -1L
        for (rotations in 0..6600 step 137) {
            val bound = Orthogonality.orthogonalityUlps(rotations)
            assertEquals(true, bound >= previous, "monotone at $rotations")
            previous = bound
        }
    }

    test("rotation counts outside the approved domain are rejected") {
        val errors = vectors.obj("domain_errors")
        for ((count, element) in errors) {
            val failure = assertFailsWith<IllegalArgumentException> {
                Orthogonality.orthogonalityUlps(count.toInt())
            }
            assertEquals(element.jsonObject.outcome().error, failure.message, "rotations $count")
        }
    }

    test("the rotation source caps follow the case families") {
        val cases = parseVectors(CASES_VECTORS)
        val caps = cases.obj("caps")
        val byId = Cases.declaredCases().associateBy {
            it.getValue("id").stringOrNull().orEmpty()
        }
        for ((id, expected) in caps) {
            val case = byId[id] ?: error("missing case $id")
            assertEquals(expected.jsonNumberInt(), Orthogonality.sourceRotationCap(case), id)
        }
        val errors = cases.obj("cap_error")
        for ((id, message) in errors) {
            val case = byId[id] ?: error("missing case $id")
            val failure = assertFailsWith<IllegalArgumentException> {
                Orthogonality.sourceRotationCap(case)
            }
            assertEquals(message.jsonPrimitive.content, failure.message, id)
        }
    }

    test("the binary64 rendering matches the Python struct format") {
        assertEquals("0000000000000000", Orthogonality.bits(0.0))
        assertEquals("8000000000000000", Orthogonality.bits(-0.0))
        assertEquals("3ff0000000000000", Orthogonality.bits(1.0))
        assertEquals("bff0000000000000", Orthogonality.bits(-1.0))
    }
}

private fun kotlinx.serialization.json.JsonElement.jsonNumberLong(): Long =
    (this as kotlinx.serialization.json.JsonPrimitive).content.toLong()

private fun kotlinx.serialization.json.JsonElement.jsonNumberInt(): Int =
    (this as kotlinx.serialization.json.JsonPrimitive).content.toInt()
