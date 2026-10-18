/*
 * Copyright (c) 2010-2024 William Bittle  http://www.dyn4j.org/
 * All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without modification, are permitted
 * provided that the following conditions are met:
 *
 *   * Redistributions of source code must retain the above copyright notice, this list of conditions
 *     and the following disclaimer.
 *   * Redistributions in binary form must reproduce the above copyright notice, this list of conditions
 *     and the following disclaimer in the documentation and/or other materials provided with the
 *     distribution.
 *   * Neither the name of the copyright holder nor the names of its contributors may be used to endorse or
 *     promote products derived from this software without specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR
 * IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND
 * FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
 * CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
 * DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
 * DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER
 * IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT
 * OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 */
package org.dyn4j.coverage

import org.dyn4j.Epsilon
import org.dyn4j.geometry.*
import kotlin.math.*
import kotlin.test.*

class UpstreamVector3CoverageTest {
    @Test
    fun create() {
        var v1 = Vector3()
        assertEquals(0.0, v1.x)
        assertEquals(0.0, v1.y)
        assertEquals(0.0, v1.z)
        assertNotNull(v1.toString())
        var v2 = Vector3(1.0, 2.0, 3.0)
        assertEquals(1.0, v2.x)
        assertEquals(2.0, v2.y)
        assertEquals(3.0, v2.z)
        var v3 = Vector3(v2)
        assertFalse(v3 === v2)
        assertEquals(1.0, v3.x)
        assertEquals(2.0, v3.y)
        assertEquals(3.0, v3.z)
        var v4 = Vector3(0.0, 1.0, 1.0, 2.0, 3.0, 1.0)
        assertEquals(2.0, v4.x)
        assertEquals(2.0, v4.y)
        assertEquals(0.0, v4.z)
        var v5 = Vector3(v2, v1)
        assertEquals(-1.0, v5.x)
        assertEquals(-2.0, v5.y)
        assertEquals(-3.0, v5.z)
    }

    @Test
    fun copy() {
        var v = Vector3(1.0, 3.0, 2.0)
        var vc = v.copy()
        assertFalse(v === vc)
        assertEquals(v.x, vc.x)
        assertEquals(v.y, vc.y)
        assertEquals(v.z, vc.z)
    }

    @Test
    fun distance() {
        var v = Vector3()
        assertEquals(4.000, v.distanceSquared(2.0, 0.0, 0.0), 1.0e-3)
        assertEquals(9.000, v.distanceSquared(2.0, -1.0, 2.0), 1.0e-3)
        assertEquals(2.000, v.distance(2.0, 0.0, 0.0), 1.0e-3)
        assertEquals(3.000, v.distance(2.0, -1.0, 2.0), 1.0e-3)
        assertEquals(4.000, v.distanceSquared(Vector3(2.0, 0.0, 0.0)), 1.0e-3)
        assertEquals(9.000, v.distanceSquared(Vector3(2.0, -1.0, 2.0)), 1.0e-3)
        assertEquals(2.000, v.distance(Vector3(2.0, 0.0, 0.0)), 1.0e-3)
        assertEquals(3.000, v.distance(Vector3(2.0, -1.0, 2.0)), 1.0e-3)
    }

    @Test
    fun tripleProduct() {
        var v1 = Vector3(1.0, 1.0, 0.0)
        var v2 = Vector3(0.0, -1.0, 1.0)
        var r = Vector3.tripleProduct(v1, v2, v2)
        assertEquals(-2.000, r.x, 1.0e-3)
        assertEquals(-1.000, r.y, 1.0e-3)
        assertEquals(-1.000, r.z, 1.0e-3)
    }

    @Test
    fun equals() {
        var v = Vector3(1.0, 2.0, -1.0)
        assertTrue(v.equals(v))
        assertEquals(v.hashCode(), v.hashCode())
        assertTrue(v.equals(v.copy()))
        assertEquals(v.hashCode(), v.copy().hashCode())
        assertTrue(v.equals(Vector3(1.0, 2.0, -1.0)))
        assertEquals(v.hashCode(), Vector3(1.0, 2.0, -1.0).hashCode())
        assertTrue(v.equals(1.0, 2.0, -1.0))
        assertFalse(v.equals(v.copy().set(2.0, 1.0, -1.0)))
        assertFalse(v.hashCode() == Vector3(2.0, 1.0, -1.0).hashCode())
        assertFalse(v.equals(2.0, 2.0, 3.0))
        assertFalse(v.hashCode() == Vector3(2.0, 2.0, 3.0).hashCode())
        assertFalse(v.equals(null))
        assertFalse(v.equals((null as Any?)))
        assertFalse(v.equals(Any()))
        assertFalse(v.equals((Vector3(1.0, 1.0, 1.0) as Any)))
        assertTrue(v.equals((Vector3(1.0, 2.0, -1.0) as Any)))
    }

    @Test
    fun set() {
        var v = Vector3()
        var v2 = Vector3(1.0, -3.0, 2.0)
        v.set(v2)
        assertFalse(v === v2)
        assertEquals(1.0, v.x)
        assertEquals(-3.0, v.y)
        assertEquals(2.0, v.z)
        v.set(-1.0, 0.0, 0.0)
        assertEquals(-1.0, v.x)
        assertEquals( 0.0, v.y)
        assertEquals( 0.0, v.z)
        v.setMagnitude(3.0)
        assertEquals(-3.0, v.x, 1.0e-3)
        assertEquals( 0.0, v.y)
        assertEquals( 0.0, v.z)
        v.setMagnitude(0.0)
        assertEquals( 0.0, v.x, 1.0e-3)
        assertEquals( 0.0, v.y)
        assertEquals( 0.0, v.z)
    }

    @Test
    fun get() {
        var v = Vector3(2.0, 1.0, -2.0)
        var x = v.getXComponent()
        var y = v.getYComponent()
        var z = v.getZComponent()
        assertEquals(2.0, x.x)
        assertEquals(0.0, x.y)
        assertEquals(0.0, x.z)
        assertEquals(0.0, y.x)
        assertEquals(1.0, y.y)
        assertEquals(0.0, y.z)
        assertEquals( 0.0, z.x)
        assertEquals( 0.0, z.y)
        assertEquals(-2.0, z.z)
        assertEquals(3.000, v.getMagnitude(), 1.0e-3)
        assertEquals(9.000, v.getMagnitudeSquared(), 1.0e-3)
        var v2 = v.getNegative()
        assertEquals(-2.0, v2.x)
        assertEquals(-1.0, v2.y)
        assertEquals( 2.0, v2.z)
        v2 = v.getNormalized()
        assertEquals( 0.666, v2.x, 1.0e-3)
        assertEquals( 0.333, v2.y, 1.0e-3)
        assertEquals(-0.666, v2.z, 1.0e-3)
        v.set(0.0,0.0,0.0)
        v2 = v.getNormalized()
        assertEquals( 0.0, v2.x, 1.0e-3)
        assertEquals( 0.0, v2.y, 1.0e-3)
        assertEquals( 0.0, v2.z, 1.0e-3)
    }

    @Test
    fun add() {
        var v1 = Vector3(1.0, 2.0, 3.0)
        var v2 = Vector3(-2.0, 1.0, -1.0)
        var v3 = v1.sum(v2)
        assertEquals(-1.0, v3.x)
        assertEquals( 3.0, v3.y)
        assertEquals( 2.0, v3.z)
        v3 = v1.sum(3.0, -7.5, 2.0)
        assertEquals( 4.0, v3.x)
        assertEquals(-5.5, v3.y)
        assertEquals( 5.0, v3.z)
        v1.add(v2)
        assertEquals(-1.0, v1.x)
        assertEquals( 3.0, v1.y)
        assertEquals( 2.0, v1.z)
        v1.add(-2.0, 1.0, 0.0)
        assertEquals(-3.0, v1.x)
        assertEquals( 4.0, v1.y)
        assertEquals( 2.0, v1.z)
    }

    @Test
    fun subtract() {
        var v1 = Vector3(1.0, 2.0, 3.0)
        var v2 = Vector3(-2.0, 1.0, -1.0)
        var v3 = v1.difference(v2)
        assertEquals(3.0, v3.x)
        assertEquals(1.0, v3.y)
        assertEquals(4.0, v3.z)
        v3 = v1.difference(3.0, -7.5, 2.0)
        assertEquals(-2.0, v3.x)
        assertEquals( 9.5, v3.y)
        assertEquals( 1.0, v3.z)
        v1.subtract(v2)
        assertEquals(3.0, v1.x)
        assertEquals(1.0, v1.y)
        assertEquals(4.0, v1.z)
        v1.subtract(-2.0, 1.0, 0.0)
        assertEquals(5.0, v1.x)
        assertEquals(0.0, v1.y)
        assertEquals(4.0, v1.z)
    }

    @Test
    fun to() {
        var p1 = Vector3(1.0, 1.0, 1.0)
        var p2 = Vector3(0.0, 1.0, 0.0)
        var r = p1.to(p2)
        assertEquals(-1.0, r.x)
        assertEquals( 0.0, r.y)
        assertEquals(-1.0, r.z)
        r = p1.to(2.0, 0.0, -1.0)
        assertEquals( 1.0, r.x)
        assertEquals(-1.0, r.y)
        assertEquals(-2.0, r.z)
    }

    @Test
    fun multiply() {
        var v1 = Vector3(2.0, 1.0, -1.0)
        var r = v1.product(-1.5)
        assertEquals(-3.0, r.x)
        assertEquals(-1.5, r.y)
        assertEquals( 1.5, r.z)
        v1.multiply(-1.5)
        assertEquals(-3.0, v1.x)
        assertEquals(-1.5, v1.y)
        assertEquals( 1.5, v1.z)
    }

    @Test
    fun dot() {
        var v1 = Vector3(1.0, 1.0, -1.0)
        var v2 = Vector3(0.0, 1.0, 0.0)
        assertEquals(1.0, v1.dot(v2))
        assertEquals(1.0, v1.dot(0.0, 1.0, 0.0))
        assertEquals(0.0, v1.dot(-1.0, 1.0, 0.0))
        assertEquals(2.0, v1.dot(1.0, 1.0, 0.0))
    }

    @Test
    fun cross() {
        var v1 = Vector3(1.0, 1.0, 0.0)
        var v2 = Vector3(0.0, 1.0, -1.0)
        var r = v1.cross(v1)
        assertEquals(0.0, r.x)
        assertEquals(0.0, r.y)
        assertEquals(0.0, r.z)
        r = v1.cross(v2)
        assertEquals(-1.0, r.x)
        assertEquals( 1.0, r.y)
        assertEquals( 1.0, r.z)
        r = v1.cross(1.0, 1.0, 0.0)
        assertEquals(0.0, r.x)
        assertEquals(0.0, r.y)
        assertEquals(0.0, r.z)
        r = v1.cross(0.0, 1.0, 1.0)
        assertEquals( 1.0, r.x)
        assertEquals(-1.0, r.y)
        assertEquals( 1.0, r.z)
        r = v1.cross(-1.0, 1.0, -1.0)
        assertEquals(-1.0, r.x)
        assertEquals( 1.0, r.y)
        assertEquals( 2.0, r.z)
    }

    @Test
    fun isOrthogonal() {
        var v1 = Vector3(1.0, 1.0, 0.0)
        var v2 = Vector3(0.0, 1.0, 2.0)
        assertFalse(v1.isOrthogonal(v2))
        assertFalse(v1.isOrthogonal(v1))
        assertFalse(v1.isOrthogonal(0.0, 1.0, 0.0))
        assertTrue(v1.isOrthogonal(1.0, -1.0, 0.0))
        assertTrue(v1.isOrthogonal(-1.0, 1.0, 0.0))
        assertFalse(v1.isOrthogonal(1.0, 1.0, 0.0))
        assertTrue(v1.isOrthogonal(0.0, 0.0, 0.0))
    }

    @Test
    fun isZero() {
        var v = Vector3()
        assertTrue(v.isZero())
        v.set(1.0, 0.0, 0.0)
        assertFalse(v.isZero())
        v.set(1.0, 1.0, 0.0)
        assertFalse(v.isZero())
        v.set(0.0, 1.0, 1.0)
        assertFalse(v.isZero())
        v.set(0.0, 0.0, 1.0)
        assertFalse(v.isZero())
    }

    @Test
    fun negate() {
        var v = Vector3(1.0, -6.0, 2.0)
        v.negate()
        assertEquals(-1.0, v.x)
        assertEquals( 6.0, v.y)
        assertEquals(-2.0, v.z)
    }

    @Test
    fun zero() {
        var v = Vector3(1.0, -2.0, 3.0)
        v.zero()
        assertEquals( 0.0, v.x)
        assertEquals( 0.0, v.y)
        assertEquals( 0.0, v.z)
    }

    @Test
    fun project() {
        var v1 = Vector3(1.0, 1.0, 0.0)
        var v2 = Vector3(0.5, 1.0, 1.0)
        var r = v1.project(v2)
        assertEquals( 0.333, r.x, 1.0e-3)
        assertEquals( 0.666, r.y, 1.0e-3)
        assertEquals( 0.666, r.z, 1.0e-3)
        r = v1.project(Vector3())
        assertEquals( 0.0, r.x, 1.0e-3)
        assertEquals( 0.0, r.y, 1.0e-3)
        assertEquals( 0.0, r.z, 1.0e-3)
    }

    @Test
    fun normalize() {
        var v = Vector3(2.0, 1.0, 2.0)
        v.normalize()
        assertEquals( 2.0 / 3.0, v.x, 1.0e-3)
        assertEquals( 1.0 / 3.0, v.y, 1.0e-3)
        assertEquals( 2.0 / 3.0, v.z, 1.0e-3)
    }

    @Test
    fun interpolate() {
        var start = Vector3(1.0, 1.0, 1.0)
        var end = Vector3(2.0, 2.0, 2.0)
        start.lerp(end, 0.5)
        assertEquals(start.x, 1.5, 1e-5)
        assertEquals(start.y, 1.5, 1e-5)
        assertEquals(start.z, 1.5, 1e-5)
        assertEquals(end.x, 2.0)
        assertEquals(end.y, 2.0)
        assertEquals(end.z, 2.0)
        start.lerp(end, 0.5)
        assertEquals(start.x, 1.75, 1e-5)
        assertEquals(start.y, 1.75, 1e-5)
        assertEquals(start.z, 1.75, 1e-5)
        assertEquals(end.x, 2.0)
        assertEquals(end.y, 2.0)
        assertEquals(end.z, 2.0)
        start.set(1.0, 1.0, 1.0)
        start.lerp(end, -0.5)
        assertEquals(start.x, 0.5, 1e-5)
        assertEquals(start.y, 0.5, 1e-5)
        assertEquals(start.z, 0.5, 1e-5)
        assertEquals(end.x, 2.0)
        assertEquals(end.y, 2.0)
        assertEquals(end.z, 2.0)
        start.lerp(end, 0.0)
        assertEquals(start.x, 0.5, 1e-5)
        assertEquals(start.y, 0.5, 1e-5)
        assertEquals(start.z, 0.5, 1e-5)
        assertEquals(end.x, 2.0)
        assertEquals(end.y, 2.0)
        assertEquals(end.z, 2.0)
        start.lerp(end, 0.1)
        assertEquals(start.x, 0.65, 1e-5)
        assertEquals(start.y, 0.65, 1e-5)
        assertEquals(start.z, 0.65, 1e-5)
        assertEquals(end.x, 2.0)
        assertEquals(end.y, 2.0)
        assertEquals(end.z, 2.0)
        var dest = Vector3()
        start.set(1.0, 1.0, 1.0)
        dest.lerp(start, end, 0.5)
        assertEquals(dest.x, 1.5, 1e-5)
        assertEquals(dest.y, 1.5, 1e-5)
        assertEquals(dest.z, 1.5, 1e-5)
        assertEquals(start.x, 1.0)
        assertEquals(start.y, 1.0)
        assertEquals(start.z, 1.0)
        assertEquals(end.x, 2.0)
        assertEquals(end.y, 2.0)
        assertEquals(end.z, 2.0)
        dest.lerp(start, end, 0.5)
        assertEquals(dest.x, 1.5, 1e-5)
        assertEquals(dest.y, 1.5, 1e-5)
        assertEquals(dest.z, 1.5, 1e-5)
        assertEquals(start.x, 1.0)
        assertEquals(start.y, 1.0)
        assertEquals(start.z, 1.0)
        assertEquals(end.x, 2.0)
        assertEquals(end.y, 2.0)
        assertEquals(end.z, 2.0)
        dest.lerp(start, end, -0.5)
        assertEquals(dest.x, 0.5, 1e-5)
        assertEquals(dest.y, 0.5, 1e-5)
        assertEquals(dest.z, 0.5, 1e-5)
        assertEquals(start.x, 1.0)
        assertEquals(start.y, 1.0)
        assertEquals(start.z, 1.0)
        assertEquals(end.x, 2.0)
        assertEquals(end.y, 2.0)
        assertEquals(end.z, 2.0)
        dest.lerp(start, end, 0.0)
        assertEquals(dest.x, 1.0, 1e-5)
        assertEquals(dest.y, 1.0, 1e-5)
        assertEquals(dest.z, 1.0, 1e-5)
        assertEquals(start.x, 1.0)
        assertEquals(start.y, 1.0)
        assertEquals(start.z, 1.0)
        assertEquals(end.x, 2.0)
        assertEquals(end.y, 2.0)
        assertEquals(end.z, 2.0)
        dest.lerp(start, end, 0.1)
        assertEquals(dest.x, 1.1, 1e-5)
        assertEquals(dest.y, 1.1, 1e-5)
        assertEquals(dest.z, 1.1, 1e-5)
        assertEquals(start.x, 1.0)
        assertEquals(start.y, 1.0)
        assertEquals(start.z, 1.0)
        assertEquals(end.x, 2.0)
        assertEquals(end.y, 2.0)
        assertEquals(end.z, 2.0)
    }

    @Test
    fun equalsEpsilon() {
        var v1 = Vector3(1.0, 1.0, 1.0)
        var v2 = Vector3(2.0, 2.0, 2.0)
        assertFalse(v1.equals(v2, 0.0))
        assertFalse(v1.equals(v2, 0.1))
        assertFalse(v1.equals(v2, 0.99))
        assertTrue(v1.equals(v2, 1.0))
        assertTrue(v1.equals(v2, 5.0))
        assertTrue(v1.equals(v2, Double.MAX_VALUE))
        v1.set(Double.MAX_VALUE, Double.MAX_VALUE, Double.MAX_VALUE)
        v2.set(-Double.MAX_VALUE, -Double.MAX_VALUE, -Double.MAX_VALUE)
        assertFalse(v1.equals(v2, 0.1))
        assertFalse(v1.equals(v2, 1.0))
        assertFalse(v1.equals(v2, 5.0))
        assertFalse(v1.equals(v2, Double.MAX_VALUE))
        assertTrue(v1.equals(v2, Double.POSITIVE_INFINITY))
        v1.set(1.0, 1.0, 1.0)
        assertFalse(v1.equals(2.0, 2.0, 2.0, 0.0))
        assertFalse(v1.equals(2.0, 2.0, 2.0, 0.1))
        assertFalse(v1.equals(2.0, 2.0, 2.0, 0.99))
        assertTrue(v1.equals(2.0, 2.0, 2.0, 1.0))
        assertTrue(v1.equals(2.0, 2.0, 2.0, 5.0))
        assertTrue(v1.equals(2.0, 2.0, 2.0, Double.MAX_VALUE))
        v1.set(Double.MAX_VALUE, Double.MAX_VALUE, Double.MAX_VALUE)
        assertFalse(v1.equals(-Double.MAX_VALUE, -Double.MAX_VALUE, -Double.MAX_VALUE, 0.1))
        assertFalse(v1.equals(-Double.MAX_VALUE, -Double.MAX_VALUE, -Double.MAX_VALUE, 1.0))
        assertFalse(v1.equals(-Double.MAX_VALUE, -Double.MAX_VALUE, -Double.MAX_VALUE, 5.0))
        assertFalse(v1.equals(-Double.MAX_VALUE, -Double.MAX_VALUE, -Double.MAX_VALUE, Double.MAX_VALUE))
        assertTrue(v1.equals(-Double.MAX_VALUE, -Double.MAX_VALUE, -Double.MAX_VALUE, Double.POSITIVE_INFINITY))
        assertFalse(v1.equals(null, 0.0))
        assertTrue(v1.equals(v1, 0.0))
        v1.set(1.0, 2.0, 1.0)
        v2.set(1.0, 3.0, 1.0)
        assertFalse(v1.equals(v2, 0.0))
        assertFalse(v1.equals(v2, 0.1))
        assertFalse(v1.equals(v2, 0.99))
        assertTrue(v1.equals(v2, 1.0))
        assertTrue(v1.equals(v2, 5.0))
        assertTrue(v1.equals(v2, Double.MAX_VALUE))
        assertFalse(v1.equals(1.0, 3.0, 1.0, 0.0))
        assertFalse(v1.equals(1.0, 3.0, 1.0, 0.1))
        assertFalse(v1.equals(1.0, 3.0, 1.0, 0.99))
        assertTrue(v1.equals(1.0, 3.0, 1.0, 1.0))
        assertTrue(v1.equals(1.0, 3.0, 1.0, 5.0))
        assertTrue(v1.equals(1.0, 3.0, 1.0, Double.MAX_VALUE))
        v1.set(1.0, 3.0, 0.0)
        v2.set(1.0, 3.0, 1.0)
        assertFalse(v1.equals(v2, 0.0))
        assertFalse(v1.equals(v2, 0.1))
        assertFalse(v1.equals(v2, 0.99))
        assertTrue(v1.equals(v2, 1.0))
        assertTrue(v1.equals(v2, 5.0))
        assertTrue(v1.equals(v2, Double.MAX_VALUE))
        assertFalse(v1.equals(1.0, 3.0, 1.0, 0.0))
        assertFalse(v1.equals(1.0, 3.0, 1.0, 0.1))
        assertFalse(v1.equals(1.0, 3.0, 1.0, 0.99))
        assertTrue(v1.equals(1.0, 3.0, 1.0, 1.0))
        assertTrue(v1.equals(1.0, 3.0, 1.0, 5.0))
        assertTrue(v1.equals(1.0, 3.0, 1.0, Double.MAX_VALUE))
    }
}

private fun radians(value: Double) = value / 180.0 * PI
private fun degrees(value: Double) = value * 180.0 / PI
