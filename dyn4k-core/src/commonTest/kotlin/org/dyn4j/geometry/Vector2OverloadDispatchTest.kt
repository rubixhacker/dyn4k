package org.dyn4j.geometry

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertSame
import kotlin.test.assertTrue

class Vector2OverloadDispatchTest {
    @Test
    fun objectDistanceUsesItsOwnArithmetic() {
        var scalarCalls = 0
        val vector = object : Vector2(0.0, 0.0) {
            override fun distance(x: Double, y: Double): Double {
                scalarCalls++
                return 777.0
            }
        }

        assertEquals(5.0, vector.distance(Vector2(3.0, 4.0)))
        assertEquals(0, scalarCalls)
        assertEquals(777.0, vector.distance(3.0, 4.0))
        assertEquals(1, scalarCalls)
    }

    @Test
    fun objectDistanceSquaredUsesItsOwnArithmetic() {
        var scalarCalls = 0
        val vector = object : Vector2(0.0, 0.0) {
            override fun distanceSquared(x: Double, y: Double): Double {
                scalarCalls++
                return 888.0
            }
        }

        assertEquals(25.0, vector.distanceSquared(Vector2(3.0, 4.0)))
        assertEquals(0, scalarCalls)
        assertEquals(888.0, vector.distanceSquared(3.0, 4.0))
        assertEquals(1, scalarCalls)
    }

    @Test
    fun objectMutationOverloadsIgnoreScalarOverrides() {
        var scalarCalls = 0
        val vector = object : Vector2(2.0, 3.0) {
            override fun set(x: Double, y: Double): Vector2 { scalarCalls++; return this }
            override fun add(x: Double, y: Double): Vector2 { scalarCalls++; return this }
            override fun subtract(x: Double, y: Double): Vector2 { scalarCalls++; return this }
        }

        assertSame(vector, vector.set(Vector2(3.0, 4.0)))
        assertEquals(3.0, vector.x)
        assertEquals(4.0, vector.y)
        assertSame(vector, vector.add(Vector2(2.0, 1.0)))
        assertEquals(5.0, vector.x)
        assertEquals(5.0, vector.y)
        assertSame(vector, vector.subtract(Vector2(1.0, 2.0)))
        assertEquals(4.0, vector.x)
        assertEquals(3.0, vector.y)
        assertEquals(0, scalarCalls)
        vector.set(1.0, 1.0)
        vector.add(1.0, 1.0)
        vector.subtract(1.0, 1.0)
        assertEquals(3, scalarCalls)
    }

    @Test
    fun objectResultOverloadsIgnoreScalarOverrides() {
        var scalarCalls = 0
        val vector = object : Vector2(3.0, 4.0) {
            override fun sum(x: Double, y: Double): Vector2 { scalarCalls++; return Vector2(777.0, 777.0) }
            override fun difference(x: Double, y: Double): Vector2 { scalarCalls++; return Vector2(777.0, 777.0) }
            override fun to(x: Double, y: Double): Vector2 { scalarCalls++; return Vector2(777.0, 777.0) }
        }

        assertEquals(Vector2(5.0, 5.0), vector.sum(Vector2(2.0, 1.0)))
        assertEquals(Vector2(1.0, 3.0), vector.difference(Vector2(2.0, 1.0)))
        assertEquals(Vector2(-1.0, -3.0), vector.to(Vector2(2.0, 1.0)))
        assertEquals(0, scalarCalls)
        assertEquals(Vector2(777.0, 777.0), vector.sum(2.0, 1.0))
        assertEquals(Vector2(777.0, 777.0), vector.difference(2.0, 1.0))
        assertEquals(Vector2(777.0, 777.0), vector.to(2.0, 1.0))
        assertEquals(3, scalarCalls)
    }

    @Test
    fun objectProductsIgnoreScalarOverrides() {
        var scalarCalls = 0
        val vector = object : Vector2(3.0, 4.0) {
            override fun dot(x: Double, y: Double): Double { scalarCalls++; return 777.0 }
            override fun cross(x: Double, y: Double): Double { scalarCalls++; return 777.0 }
        }

        assertEquals(25.0, vector.dot(Vector2(3.0, 4.0)))
        assertEquals(-7.0, vector.cross(Vector2(4.0, 3.0)))
        assertEquals(0, scalarCalls)
        assertEquals(777.0, vector.dot(3.0, 4.0))
        assertEquals(777.0, vector.cross(4.0, 3.0))
        assertEquals(2, scalarCalls)
    }

    @Test
    fun orthogonalityComputesDirectlyForBothArgumentForms() {
        var dotCalls = 0
        var scalarOrthogonalCalls = 0
        val vector = object : Vector2(3.0, 4.0) {
            override fun dot(x: Double, y: Double): Double { dotCalls++; return 777.0 }
            override fun isOrthogonal(x: Double, y: Double): Boolean {
                scalarOrthogonalCalls++
                return false
            }
        }

        assertTrue(vector.isOrthogonal(Vector2(4.0, -3.0)))
        assertFalse(vector.isOrthogonal(Vector2(3.0, 4.0)))
        assertEquals(0, scalarOrthogonalCalls)
        assertFalse(vector.isOrthogonal(4.0, -3.0))
        assertEquals(1, scalarOrthogonalCalls)
        assertEquals(0, dotCalls)

        val scalarVector = object : Vector2(3.0, 4.0) {
            override fun dot(x: Double, y: Double): Double { dotCalls++; return 777.0 }
        }
        assertTrue(scalarVector.isOrthogonal(4.0, -3.0))
        assertEquals(0, dotCalls)
    }

    @Test
    fun objectEqualityWithToleranceIgnoresScalarOverride() {
        var scalarCalls = 0
        val vector = object : Vector2(3.0, 4.0) {
            override fun equals(x: Double, y: Double, epsilon: Double): Boolean {
                scalarCalls++
                return false
            }
        }

        assertTrue(vector.equals(Vector2(3.0, 4.0), 0.0))
        assertFalse(vector.equals(Vector2(3.0, 5.0), 0.0))
        assertFalse(vector.equals(null, 0.0))
        assertTrue(vector.equals(vector, 0.0))
        assertEquals(0, scalarCalls)
        assertFalse(vector.equals(3.0, 4.0, 0.0))
        assertEquals(1, scalarCalls)
    }

    @Test
    fun pointRotationAndProjectionKeepBaselineVirtualCalls() {
        var rotationCalls = 0
        val vector = object : Vector2(3.0, 4.0) {
            override fun rotate(theta: Double, x: Double, y: Double): Vector2 {
                rotationCalls++
                return this
            }
            override fun dot(vector: Vector2): Double = 10.0
        }

        assertSame(vector, vector.rotate(1.0, Vector2(2.0, 0.0)))
        assertEquals(1, rotationCalls)
        assertEquals(Vector2(5.0, 0.0), vector.project(Vector2(2.0, 0.0)))
        assertEquals(Vector2(3.0, 4.0), Vector2(vector))
    }

    @Test
    fun zeroMagnitudeWritesFieldsWithoutCallingOverriddenZero() {
        var zeroCalls = 0
        val vector = object : Vector2(3.0, 4.0) {
            override fun zero(): Vector2 { zeroCalls++; return this }
        }

        assertSame(vector, vector.setMagnitude(0.0))
        assertEquals(Vector2(0.0, 0.0), Vector2(vector))
        assertEquals(0, zeroCalls)
        vector.zero()
        assertEquals(1, zeroCalls)
    }

    @Test
    fun nonzeroMagnitudeComputesDirectlyButKeepsVirtualZeroCheck() {
        var magnitudeCalls = 0
        var zeroCheckCalls = 0
        val vector = object : Vector2(3.0, 4.0) {
            override fun getMagnitude(): Double { magnitudeCalls++; return 10.0 }
            override fun isZero(): Boolean { zeroCheckCalls++; return false }
        }

        assertSame(vector, vector.setMagnitude(10.0))
        assertEquals(Vector2(6.0, 8.0), Vector2(vector))
        assertEquals(0, magnitudeCalls)
        assertEquals(1, zeroCheckCalls)
    }

    @Test
    fun directionComputesMagnitudeWithoutCallingOverride() {
        var magnitudeCalls = 0
        val vector = object : Vector2(3.0, 4.0) {
            override fun getMagnitude(): Double { magnitudeCalls++; return 10.0 }
        }

        assertSame(vector, vector.setDirection(0.0))
        assertEquals(Vector2(5.0, 0.0), Vector2(vector))
        assertEquals(0, magnitudeCalls)
        assertEquals(10.0, vector.getMagnitude())
        assertEquals(1, magnitudeCalls)
    }
}
