package org.dyn4j.geometry

import org.dyn4j.Epsilon
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotSame
import kotlin.test.assertTrue

class Vector2NormalizationParityTest {
    @Test
    fun normalizeUsesOneReciprocalAndMutatesTheSameVector() {
        val vector = Vector2(3.0, 4.0)

        assertEquals(5.0, vector.normalize())
        assertEquals(0x3fe3333333333334L, vector.x.toBits())
        assertEquals(0x3fe999999999999aL, vector.y.toBits())
    }

    @Test
    fun getNormalizedUsesOneReciprocalAndReturnsANewVector() {
        val vector = Vector2(3.0, 4.0)

        val normalized = vector.getNormalized()

        assertNotSame(vector, normalized)
        assertEquals(0x3fe3333333333334L, normalized.x.toBits())
        assertEquals(0x3fe999999999999aL, normalized.y.toBits())
        assertEquals(3.0, vector.x)
        assertEquals(4.0, vector.y)
    }

    @Test
    fun normalizeReadsFieldsWithoutCallingOverriddenMagnitude() {
        var calls = 0
        val vector = object : Vector2(3.0, 4.0) {
            override fun getMagnitude(): Double { calls++; return 10.0 }
        }

        assertEquals(5.0, vector.normalize())
        assertEquals(0, calls)
        assertEquals(0x3fe3333333333334L, vector.x.toBits())
    }

    @Test
    fun getNormalizedCallsOverriddenMagnitudeOnTheSource() {
        var calls = 0
        val vector = object : Vector2(3.0, 4.0) {
            override fun getMagnitude(): Double { calls++; return 10.0 }
        }

        val normalized = vector.getNormalized()

        assertEquals(1, calls)
        assertEquals(0x3fd3333333333334L, normalized.x.toBits())
        assertEquals(0x3fd999999999999aL, normalized.y.toBits())
        assertEquals(3.0, vector.x)
        assertEquals(4.0, vector.y)
    }

    @Test
    fun zeroThresholdLeavesMutableVectorAndReturnsFreshZeroCopy() {
        val vector = Vector2(Epsilon.E, 0.0)
        val copy = vector.getNormalized()

        assertEquals(0.0, vector.normalize())
        assertEquals(Epsilon.E, vector.x)
        assertNotSame(vector, copy)
        assertEquals(0.0, copy.x)
        assertEquals(0.0, copy.y)

        val above = Vector2(Epsilon.E * 2.0, 0.0)
        assertEquals(Epsilon.E * 2.0, above.normalize())
        assertEquals(1.0, above.x)
    }

    @Test
    fun invalidMagnitudeKeepsTheBaselineFloatingPointBehavior() {
        val infinite = Vector2(Double.POSITIVE_INFINITY, 1.0)
        val copy = infinite.getNormalized()
        assertTrue(copy.x.isNaN())
        assertEquals(0.0, copy.y)

        assertEquals(Double.POSITIVE_INFINITY, infinite.normalize())
        assertTrue(infinite.x.isNaN())
        assertEquals(0.0, infinite.y)

        val nan = Vector2(Double.NaN, 1.0)
        assertTrue(nan.normalize().isNaN())
        assertTrue(nan.x.isNaN())
        assertTrue(nan.y.isNaN())
    }
}
