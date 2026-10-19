package org.dyn4j.geometry

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertSame
import kotlin.test.assertTrue

class Vector3OverloadDispatchTest {
    @Test
    fun scalarDistanceComputesWithoutCallingOverriddenSquaredDistance() {
        var squaredCalls = 0
        val vector = object : Vector3(0.0, 0.0, 0.0) {
            override fun distanceSquared(x: Double, y: Double, z: Double): Double {
                squaredCalls++
                return 777.0
            }
        }

        assertEquals(5.0, vector.distance(3.0, 4.0, 0.0))
        assertEquals(0, squaredCalls)
        assertEquals(777.0, vector.distanceSquared(3.0, 4.0, 0.0))
        assertEquals(1, squaredCalls)
    }

    @Test
    fun objectDistancesComputeWithoutCallingScalarOverrides() {
        var scalarCalls = 0
        val vector = object : Vector3(0.0, 0.0, 0.0) {
            override fun distance(x: Double, y: Double, z: Double): Double {
                scalarCalls++
                return 777.0
            }
            override fun distanceSquared(x: Double, y: Double, z: Double): Double {
                scalarCalls++
                return 888.0
            }
        }

        assertEquals(5.0, vector.distance(Vector3(3.0, 4.0, 0.0)))
        assertEquals(25.0, vector.distanceSquared(Vector3(3.0, 4.0, 0.0)))
        assertEquals(0, scalarCalls)
        assertEquals(777.0, vector.distance(3.0, 4.0, 0.0))
        assertEquals(888.0, vector.distanceSquared(3.0, 4.0, 0.0))
        assertEquals(2, scalarCalls)
    }

    @Test
    fun objectMutationOverloadsIgnoreScalarOverrides() {
        var scalarCalls = 0
        val vector = object : Vector3(2.0, 3.0, 4.0) {
            override fun set(x: Double, y: Double, z: Double): Vector3 { scalarCalls++; return this }
            override fun add(x: Double, y: Double, z: Double): Vector3 { scalarCalls++; return this }
            override fun subtract(x: Double, y: Double, z: Double): Vector3 { scalarCalls++; return this }
        }

        assertSame(vector, vector.set(Vector3(3.0, 4.0, 5.0)))
        assertEquals(Vector3(3.0, 4.0, 5.0), Vector3(vector))
        assertSame(vector, vector.add(Vector3(2.0, 1.0, 3.0)))
        assertEquals(Vector3(5.0, 5.0, 8.0), Vector3(vector))
        assertSame(vector, vector.subtract(Vector3(1.0, 2.0, 3.0)))
        assertEquals(Vector3(4.0, 3.0, 5.0), Vector3(vector))
        assertEquals(0, scalarCalls)
        vector.set(1.0, 1.0, 1.0)
        vector.add(1.0, 1.0, 1.0)
        vector.subtract(1.0, 1.0, 1.0)
        assertEquals(3, scalarCalls)
    }

    @Test
    fun objectResultOverloadsIgnoreScalarOverrides() {
        var scalarCalls = 0
        val vector = object : Vector3(3.0, 4.0, 5.0) {
            override fun sum(x: Double, y: Double, z: Double): Vector3 {
                scalarCalls++; return Vector3(777.0, 777.0, 777.0)
            }
            override fun difference(x: Double, y: Double, z: Double): Vector3 {
                scalarCalls++; return Vector3(777.0, 777.0, 777.0)
            }
            override fun to(x: Double, y: Double, z: Double): Vector3 {
                scalarCalls++; return Vector3(777.0, 777.0, 777.0)
            }
        }

        assertEquals(Vector3(5.0, 5.0, 8.0), vector.sum(Vector3(2.0, 1.0, 3.0)))
        assertEquals(Vector3(1.0, 3.0, 2.0), vector.difference(Vector3(2.0, 1.0, 3.0)))
        assertEquals(Vector3(-1.0, -3.0, -2.0), vector.to(Vector3(2.0, 1.0, 3.0)))
        assertEquals(0, scalarCalls)
        assertEquals(Vector3(777.0, 777.0, 777.0), vector.sum(2.0, 1.0, 3.0))
        assertEquals(Vector3(777.0, 777.0, 777.0), vector.difference(2.0, 1.0, 3.0))
        assertEquals(Vector3(777.0, 777.0, 777.0), vector.to(2.0, 1.0, 3.0))
        assertEquals(3, scalarCalls)
    }

    @Test
    fun objectProductsIgnoreScalarOverrides() {
        var scalarCalls = 0
        val vector = object : Vector3(1.0, 2.0, 3.0) {
            override fun dot(x: Double, y: Double, z: Double): Double {
                scalarCalls++; return 777.0
            }
            override fun cross(x: Double, y: Double, z: Double): Vector3 {
                scalarCalls++; return Vector3(777.0, 777.0, 777.0)
            }
        }

        assertEquals(32.0, vector.dot(Vector3(4.0, 5.0, 6.0)))
        assertEquals(Vector3(-3.0, 6.0, -3.0), vector.cross(Vector3(4.0, 5.0, 6.0)))
        assertEquals(0, scalarCalls)
        assertEquals(777.0, vector.dot(4.0, 5.0, 6.0))
        assertEquals(Vector3(777.0, 777.0, 777.0), vector.cross(4.0, 5.0, 6.0))
        assertEquals(2, scalarCalls)
    }

    @Test
    fun orthogonalityComputesDirectlyForBothArgumentForms() {
        var dotCalls = 0
        var scalarOrthogonalCalls = 0
        val vector = object : Vector3(1.0, 2.0, 3.0) {
            override fun dot(x: Double, y: Double, z: Double): Double {
                dotCalls++; return 777.0
            }
            override fun isOrthogonal(x: Double, y: Double, z: Double): Boolean {
                scalarOrthogonalCalls++; return false
            }
        }

        assertTrue(vector.isOrthogonal(Vector3(2.0, -1.0, 0.0)))
        assertFalse(vector.isOrthogonal(Vector3(1.0, 2.0, 3.0)))
        assertEquals(0, scalarOrthogonalCalls)
        assertFalse(vector.isOrthogonal(2.0, -1.0, 0.0))
        assertEquals(1, scalarOrthogonalCalls)
        assertEquals(0, dotCalls)

        val scalarVector = object : Vector3(1.0, 2.0, 3.0) {
            override fun dot(x: Double, y: Double, z: Double): Double {
                dotCalls++; return 777.0
            }
        }
        assertTrue(scalarVector.isOrthogonal(2.0, -1.0, 0.0))
        assertEquals(0, dotCalls)
    }

    @Test
    fun objectEqualityWithToleranceIgnoresScalarOverride() {
        var scalarCalls = 0
        val vector = object : Vector3(3.0, 4.0, 5.0) {
            override fun equals(x: Double, y: Double, z: Double, epsilon: Double): Boolean {
                scalarCalls++
                return false
            }
        }

        assertTrue(vector.equals(Vector3(3.0, 4.0, 5.0), 0.0))
        assertFalse(vector.equals(Vector3(3.0, 4.0, 6.0), 0.0))
        assertFalse(vector.equals(null, 0.0))
        assertTrue(vector.equals(vector, 0.0))
        assertEquals(0, scalarCalls)
        assertFalse(vector.equals(3.0, 4.0, 5.0, 0.0))
        assertEquals(1, scalarCalls)
    }

    @Test
    fun projectionKeepsBaselineVirtualDotCall() {
        val vector = object : Vector3(3.0, 4.0, 5.0) {
            override fun dot(vector: Vector3): Double = 10.0
        }

        assertEquals(Vector3(5.0, 0.0, 0.0), vector.project(Vector3(2.0, 0.0, 0.0)))
        assertEquals(Vector3(3.0, 4.0, 5.0), Vector3(vector))
    }

    @Test
    fun zeroMagnitudeWritesFieldsWithoutCallingOverriddenZero() {
        var zeroCalls = 0
        val vector = object : Vector3(2.0, 3.0, 6.0) {
            override fun zero(): Vector3 { zeroCalls++; return this }
        }

        assertSame(vector, vector.setMagnitude(0.0))
        assertEquals(Vector3(0.0, 0.0, 0.0), Vector3(vector))
        assertEquals(0, zeroCalls)
        vector.zero()
        assertEquals(1, zeroCalls)
    }

    @Test
    fun nonzeroMagnitudeComputesDirectlyButKeepsVirtualZeroCheck() {
        var magnitudeCalls = 0
        var zeroCheckCalls = 0
        val vector = object : Vector3(2.0, 3.0, 6.0) {
            override fun getMagnitude(): Double { magnitudeCalls++; return 14.0 }
            override fun isZero(): Boolean { zeroCheckCalls++; return false }
        }

        assertSame(vector, vector.setMagnitude(14.0))
        assertEquals(Vector3(4.0, 6.0, 12.0), Vector3(vector))
        assertEquals(0, magnitudeCalls)
        assertEquals(1, zeroCheckCalls)
    }

    @Test
    fun normalizedCopyUsesDirectMagnitudeAndOneReciprocal() {
        var magnitudeCalls = 0
        val vector = object : Vector3(3.0, 4.0, 0.0) {
            override fun getMagnitude(): Double { magnitudeCalls++; return 10.0 }
        }

        val normalized = vector.getNormalized()

        assertFalse(normalized === vector)
        assertEquals(0x3fe3333333333334L, normalized.x.toBits())
        assertEquals(0x3fe999999999999aL, normalized.y.toBits())
        assertEquals(0.0, normalized.z)
        assertEquals(Vector3(3.0, 4.0, 0.0), Vector3(vector))
        assertEquals(0, magnitudeCalls)
    }

    @Test
    fun normalizeUsesDirectMagnitudeAndOneReciprocal() {
        var magnitudeCalls = 0
        val vector = object : Vector3(3.0, 4.0, 0.0) {
            override fun getMagnitude(): Double { magnitudeCalls++; return 10.0 }
        }

        assertEquals(5.0, vector.normalize())
        assertEquals(0x3fe3333333333334L, vector.x.toBits())
        assertEquals(0x3fe999999999999aL, vector.y.toBits())
        assertEquals(0.0, vector.z)
        assertEquals(0, magnitudeCalls)
    }

    @Test
    fun zeroNormalizationDoesNotCallOverriddenMagnitude() {
        var magnitudeCalls = 0
        val vector = object : Vector3() {
            override fun getMagnitude(): Double { magnitudeCalls++; return 10.0 }
        }

        val normalized = vector.getNormalized()
        assertFalse(normalized === vector)
        assertEquals(Vector3(), normalized)
        assertEquals(0.0, vector.normalize())
        assertEquals(Vector3(), Vector3(vector))
        assertEquals(0, magnitudeCalls)
    }
}
