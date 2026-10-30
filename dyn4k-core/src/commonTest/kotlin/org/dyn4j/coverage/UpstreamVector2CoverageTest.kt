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

import de.infix.testBalloon.framework.core.testSuite
import org.dyn4j.geometry.*
import org.dyn4j.Epsilon
import kotlin.math.*
import kotlin.test.*

val UpstreamVector2CoverageTest by testSuite {
    test("create") { UpstreamVector2CoverageTestFixture().run { create() } }
    test("copy") { UpstreamVector2CoverageTestFixture().run { copy() } }
    test("distance") { UpstreamVector2CoverageTestFixture().run { distance() } }
    test("distanceBugInVersions_1_1_0_to_3_1_7") { UpstreamVector2CoverageTestFixture().run { distanceBugInVersions_1_1_0_to_3_1_7() } }
    test("tripleProduct") { UpstreamVector2CoverageTestFixture().run { tripleProduct() } }
    test("equals") { UpstreamVector2CoverageTestFixture().run { equals() } }
    test("set") { UpstreamVector2CoverageTestFixture().run { set() } }
    test("get") { UpstreamVector2CoverageTestFixture().run { get() } }
    test("add") { UpstreamVector2CoverageTestFixture().run { add() } }
    test("subtract") { UpstreamVector2CoverageTestFixture().run { subtract() } }
    test("to") { UpstreamVector2CoverageTestFixture().run { to() } }
    test("multiply") { UpstreamVector2CoverageTestFixture().run { multiply() } }
    test("divide") { UpstreamVector2CoverageTestFixture().run { divide() } }
    test("dot") { UpstreamVector2CoverageTestFixture().run { dot() } }
    test("cross") { UpstreamVector2CoverageTestFixture().run { cross() } }
    test("isOrthogonal") { UpstreamVector2CoverageTestFixture().run { isOrthogonal() } }
    test("isZero") { UpstreamVector2CoverageTestFixture().run { isZero() } }
    test("negate") { UpstreamVector2CoverageTestFixture().run { negate() } }
    test("zero") { UpstreamVector2CoverageTestFixture().run { zero() } }
    test("rotate") { UpstreamVector2CoverageTestFixture().run { rotate() } }
    test("project") { UpstreamVector2CoverageTestFixture().run { project() } }
    test("left") { UpstreamVector2CoverageTestFixture().run { left() } }
    test("right") { UpstreamVector2CoverageTestFixture().run { right() } }
    test("normalize") { UpstreamVector2CoverageTestFixture().run { normalize() } }
    test("getAngleBetweenRange") { UpstreamVector2CoverageTestFixture().run { getAngleBetweenRange() } }
    test("interpolate") { UpstreamVector2CoverageTestFixture().run { interpolate() } }
    test("equalsEpsilon") { UpstreamVector2CoverageTestFixture().run { equalsEpsilon() } }
}

private class UpstreamVector2CoverageTestFixture  {
fun create() {
        var v1 = Vector2()
        assertEquals(0.0, v1.x)
        assertEquals(0.0, v1.y)
        var v2 = Vector2(1.0, 2.0)
        assertEquals(1.0, v2.x)
        assertEquals(2.0, v2.y)
        var v3 = Vector2(v2)
        assertFalse(v3 === v2)
        assertEquals(1.0, v3.x)
        assertEquals(2.0, v3.y)
        var v4 = Vector2(0.0, 1.0, 2.0, 3.0)
        assertEquals(2.0, v4.x)
        assertEquals(2.0, v4.y)
        var v5 = Vector2(v2, v1)
        assertEquals(-1.0, v5.x)
        assertEquals(-2.0, v5.y)
        var v7 = Vector2(radians(30.0))
        assertEquals(1.000, v7.getMagnitude(), 1.0E-4)
        assertEquals(30.000, degrees(v7.getDirection()), 1.0E-4)
        var v6 = Vector2.create(1.0, radians(90.0))
        assertEquals( 0.000, v6.x, 1.0e-3)
        assertEquals( 1.000, v6.y, 1.0e-3)
    }

fun copy() {
        var v = Vector2(1.0, 3.0)
        var vc = v.copy()
        assertFalse(v === vc)
        assertEquals(v.x, vc.x)
        assertEquals(v.y, vc.y)
    }

fun distance() {
        var v = Vector2()
        assertEquals(4.000, v.distanceSquared(2.0, 0.0), 1.0e-3)
        assertEquals(5.000, v.distanceSquared(2.0, -1.0), 1.0e-3)
        assertEquals(2.000, v.distance(2.0, 0.0), 1.0e-3)
        assertEquals(5.000, v.distance(3.0, 4.0), 1.0e-3)
        assertEquals(4.000, v.distanceSquared(Vector2(2.0, 0.0)), 1.0e-3)
        assertEquals(5.000, v.distanceSquared(Vector2(2.0, -1.0)), 1.0e-3)
        assertEquals(2.000, v.distance(Vector2(2.0, 0.0)), 1.0e-3)
        assertEquals(5.000, v.distance(Vector2(3.0, 4.0)), 1.0e-3)
    }

fun distanceBugInVersions_1_1_0_to_3_1_7() {
        var v = Vector2(1.0, 2.0)
        assertEquals(2.236, v.getMagnitude(), 1.0e-3)
        assertEquals(2.236, v.distance(2.0, 0.0), 1.0e-3)
        assertEquals(0.000, v.distance(1.0, 2.0), 1.0e-3)
        assertEquals(1.414, v.distance(2.0, 1.0), 1.0e-3)
        assertEquals(4.242, v.distance(-2.0, -1.0), 1.0e-3)
    }

fun tripleProduct() {
        var v1 = Vector2(1.0, 1.0)
        var v2 = Vector2(1.0, -1.0)
        var r = Vector2.tripleProduct(v1, v2, v2)
        assertEquals(-2.000, r.x, 1.0e-3)
        assertEquals(-2.000, r.y, 1.0e-3)
    }

fun equals() {
        var v = Vector2(1.0, 2.0)
        assertTrue(v.equals(v))
        assertTrue(v.equals(v.copy()))
        assertTrue(v.equals(Vector2(1.0, 2.0)))
        assertTrue(v.equals(1.0, 2.0))
        assertFalse(v.equals(v.copy().set(2.0, 1.0)))
        assertFalse(v.equals(2.0, 2.0))
        assertFalse(v.equals(null))
        assertFalse(v.equals(Any()))
        assertTrue(v.equals((Vector2(1.0, 2.0) as Any)))
    }

fun set() {
        var v = Vector2()
        var v2 = Vector2(1.0, -3.0)
        v.set(v2)
        assertFalse(v === v2)
        assertEquals(1.0, v.x)
        assertEquals(-3.0, v.y)
        v.set(-1.0, 0.0)
        assertEquals(-1.0, v.x)
        assertEquals( 0.0, v.y)
        v.setDirection(radians(90.0))
        assertEquals( 0.0, v.x, 1E-10)
        assertEquals( 1.0, v.y)
        v.setMagnitude(3.0)
        assertEquals( 0.0, v.x, 1E-10)
        assertEquals( 3.0, v.y)
        v.set(-1.0, 0.0)
        v.setMagnitude(0.0)
        assertEquals( 0.0, v.x)
        assertEquals( 0.0, v.y)
        v.set(-1.0, 0.0)
        v.setMagnitude(Epsilon.E)
        assertEquals( 0.0, v.x)
        assertEquals( 0.0, v.y)
    }

fun get() {
        var v = Vector2(3.0, 4.0)
        var x = v.getXComponent()
        var y = v.getYComponent()
        assertEquals(3.0, x.x)
        assertEquals(0.0, x.y)
        assertEquals(0.0, y.x)
        assertEquals(4.0, y.y)
        assertEquals(5.000, v.getMagnitude(), 1.0e-3)
        assertEquals(25.000, v.getMagnitudeSquared(), 1.0e-3)
        assertEquals(53.130, degrees(v.getDirection()), 1.0e-3)
        var v2 = Vector2(-4.0, 3.0)
        assertEquals(90.000, degrees(v.getAngleBetween(v2)), 1.0e-3)
        v2 = v.getLeftHandOrthogonalVector()
        assertEquals( 4.0, v2.x)
        assertEquals(-3.0, v2.y)
        v2 = v.getRightHandOrthogonalVector()
        assertEquals(-4.0, v2.x)
        assertEquals( 3.0, v2.y)
        v2 = v.getNegative()
        assertEquals(-3.0, v2.x)
        assertEquals(-4.0, v2.y)
        v2 = v.getNormalized()
        assertEquals(0.600, v2.x, 1.0e-3)
        assertEquals(0.800, v2.y, 1.0e-3)
    }

fun add() {
        var v1 = Vector2(1.0, 2.0)
        var v2 = Vector2(-2.0, 1.0)
        var v3 = v1.sum(v2)
        assertEquals(-1.0, v3.x)
        assertEquals( 3.0, v3.y)
        v3 = v1.sum(3.0, -7.5)
        assertEquals( 4.0, v3.x)
        assertEquals(-5.5, v3.y)
        v1.add(v2)
        assertEquals(-1.0, v1.x)
        assertEquals( 3.0, v1.y)
        v1.add(-2.0, 1.0)
        assertEquals(-3.0, v1.x)
        assertEquals( 4.0, v1.y)
    }

fun subtract() {
        var v1 = Vector2(1.0, 2.0)
        var v2 = Vector2(-2.0, 1.0)
        var v3 = v1.difference(v2)
        assertEquals( 3.0, v3.x)
        assertEquals( 1.0, v3.y)
        v3 = v1.difference(3.0, -7.5)
        assertEquals(-2.0, v3.x)
        assertEquals( 9.5, v3.y)
        v1.subtract(v2)
        assertEquals( 3.0, v1.x)
        assertEquals( 1.0, v1.y)
        v1.subtract(-2.0, 1.0)
        assertEquals( 5.0, v1.x)
        assertEquals( 0.0, v1.y)
    }

fun to() {
        var p1 = Vector2(1.0, 1.0)
        var p2 = Vector2(0.0, 1.0)
        var r = p1.to(p2)
        assertEquals(-1.0, r.x)
        assertEquals( 0.0, r.y)
        r = p1.to(2.0, 0.0)
        assertEquals( 1.0, r.x)
        assertEquals(-1.0, r.y)
    }

fun multiply() {
        var v1 = Vector2(2.0, 1.0)
        var r = v1.product(-1.5)
        assertEquals(-3.0, r.x)
        assertEquals(-1.5, r.y)
        v1.multiply(-1.5)
        assertEquals(-3.0, v1.x)
        assertEquals(-1.5, v1.y)
    }

fun divide() {
        var v1 = Vector2(2.0, 1.0)
        var r = v1.quotient(-2.0)
        assertEquals(-1.0, r.x)
        assertEquals(-0.5, r.y)
        v1.divide(-2.0)
        assertEquals(-1.0, r.x)
        assertEquals(-0.5, r.y)
    }

fun dot() {
        var v1 = Vector2(1.0, 1.0)
        var v2 = Vector2(0.0, 1.0)
        assertEquals(1.0, v1.dot(v2))
        assertEquals(0.0, v1.dot(v1.getLeftHandOrthogonalVector()))
        assertEquals(v1.getMagnitudeSquared(), v1.dot(v1))
        assertEquals(1.0, v1.dot(0.0, 1.0))
        assertEquals(0.0, v1.dot(-1.0, 1.0))
        assertEquals(2.0, v1.dot(1.0, 1.0))
    }

fun cross() {
        var v1 = Vector2(1.0, 1.0)
        var v2 = Vector2(0.0, 1.0)
        assertEquals(0.0, v1.cross(v1))
        assertEquals(1.0, v1.cross(v2))
        assertEquals(-2.0, v1.cross(v1.getLeftHandOrthogonalVector()))
        assertEquals(0.0, v1.cross(1.0, 1.0))
        assertEquals(1.0, v1.cross(0.0, 1.0))
        assertEquals(2.0, v1.cross(-1.0, 1.0))
        var r = v1.cross(3.0)
        assertEquals(-3.0, r.x)
        assertEquals( 3.0, r.y)
    }

fun isOrthogonal() {
        var v1 = Vector2(1.0, 1.0)
        var v2 = Vector2(0.0, 1.0)
        assertFalse(v1.isOrthogonal(v2))
        assertTrue(v1.isOrthogonal(v1.getLeftHandOrthogonalVector()))
        assertTrue(v1.isOrthogonal(v1.getRightHandOrthogonalVector()))
        assertFalse(v1.isOrthogonal(v1))
        assertFalse(v1.isOrthogonal(0.0, 1.0))
        assertTrue(v1.isOrthogonal(1.0, -1.0))
        assertTrue(v1.isOrthogonal(-1.0, 1.0))
        assertFalse(v1.isOrthogonal(1.0, 1.0))
        assertTrue(v1.isOrthogonal(0.0, 0.0))
    }

fun isZero() {
        var v = Vector2()
        assertTrue(v.isZero())
        v.set(1.0, 0.0)
        assertFalse(v.isZero())
        v.set(1.0, 1.0)
        assertFalse(v.isZero())
        v.set(0.0, 1.0)
        assertFalse(v.isZero())
    }

fun negate() {
        var v = Vector2(1.0, -6.0)
        v.negate()
        assertEquals(-1.0, v.x)
        assertEquals( 6.0, v.y)
    }

fun zero() {
        var v = Vector2(1.0, -2.0)
        v.zero()
        assertEquals( 0.0, v.x)
        assertEquals( 0.0, v.y)
    }

fun rotate() {
        var v = Vector2(2.0, 1.0)
        v.rotate(radians(90.0))
        assertEquals(-1.000, v.x, 1.0e-3)
        assertEquals( 2.000, v.y, 1.0e-3)
        v.rotate(Rotation(radians(60.0)), 0.0, 1.0)
        assertEquals(-1.366, v.x, 1.0e-3)
        assertEquals( 0.634, v.y, 1.0e-3)
        v.inverseRotate(Rotation(radians(60.0)), 0.0, 1.0)
        assertEquals(-1.000, v.x, 1.0e-3)
        assertEquals( 2.000, v.y, 1.0e-3)
        v.inverseRotate(radians(90.0))
        assertEquals(2.0, v.x, 1.0e-3)
        assertEquals(1.0, v.y, 1.0e-3)
        v = Vector2(2.0, 1.0)
        v.rotate(Rotation(radians(90.0)), Vector2(0.0, 0.0))
        assertEquals(-1.000, v.x, 1.0e-3)
        assertEquals( 2.000, v.y, 1.0e-3)
        v = Vector2(2.0, 1.0)
        v.rotate(radians(90.0), Vector2(0.0, 0.0))
        assertEquals(-1.000, v.x, 1.0e-3)
        assertEquals( 2.000, v.y, 1.0e-3)
        v = Vector2(2.0, 1.0)
        v.rotate(radians(90.0), 0.0, 0.0)
        assertEquals(-1.000, v.x, 1.0e-3)
        assertEquals( 2.000, v.y, 1.0e-3)
        v = Vector2(2.0, 1.0)
        v.inverseRotate(radians(90.0), Vector2(0.0, 0.0))
        assertEquals( 1.000, v.x, 1.0e-3)
        assertEquals(-2.000, v.y, 1.0e-3)
        v = Vector2(2.0, 1.0)
        v.inverseRotate(radians(90.0), 0.0, 0.0)
        assertEquals( 1.000, v.x, 1.0e-3)
        assertEquals(-2.000, v.y, 1.0e-3)
    }

fun project() {
        var v1 = Vector2(1.0, 1.0)
        var v2 = Vector2(0.5, 1.0)
        var r = v1.project(v2)
        assertEquals( 0.600, r.x, 1.0e-3)
        assertEquals( 1.200, r.y, 1.0e-3)
        r = v1.project(Vector2())
        assertEquals( 0.000, r.x, 1.0e-3)
        assertEquals( 0.000, r.y, 1.0e-3)
    }

fun left() {
        var v = Vector2(11.0, 2.5)
        v.left()
        assertEquals( 2.5, v.x)
        assertEquals( -11.0, v.y)
    }

fun right() {
        var v = Vector2(11.0, 2.5)
        v.right()
        assertEquals( -2.5, v.x)
        assertEquals( 11.0, v.y)
    }

fun normalize() {
        var v = Vector2(3.0, 4.0)
        v.normalize()
        assertEquals( 3.0 / 5.0, v.x, 1.0e-3)
        assertEquals( 4.0 / 5.0, v.y, 1.0e-3)
    }

fun getAngleBetweenRange() {
        var v1 = Vector2(-1.0, 2.0)
        var v2 = Vector2(-2.0, -1.0)
        assertTrue(abs(v1.getAngleBetween(v2)) <= PI)
        v1 = Vector2(1.0, 2.0)
        v2 = Vector2(-2.0, -1.0)
        assertTrue(abs(v1.getAngleBetween(v2)) <= PI)
        v1 = Vector2(-1.0, -1.0)
        var angle = abs(v1.getAngleBetween(radians(300.0)))
        assertEquals(radians(75.0), angle, 1e-3)
        assertTrue(angle <= PI)
    }

fun interpolate() {
        var start = Vector2(1.0, 1.0)
        var end = Vector2(2.0, 2.0)
        start.lerp(end, 0.5)
        assertEquals(start.x, 1.5, 1e-5)
        assertEquals(start.y, 1.5, 1e-5)
        assertEquals(end.x, 2.0)
        assertEquals(end.y, 2.0)
        start.lerp(end, 0.5)
        assertEquals(start.x, 1.75, 1e-5)
        assertEquals(start.y, 1.75, 1e-5)
        assertEquals(end.x, 2.0)
        assertEquals(end.y, 2.0)
        start.set(1.0, 1.0)
        start.lerp(end, -0.5)
        assertEquals(start.x, 0.5, 1e-5)
        assertEquals(start.y, 0.5, 1e-5)
        assertEquals(end.x, 2.0)
        assertEquals(end.y, 2.0)
        start.lerp(end, 0.0)
        assertEquals(start.x, 0.5, 1e-5)
        assertEquals(start.y, 0.5, 1e-5)
        assertEquals(end.x, 2.0)
        assertEquals(end.y, 2.0)
        start.lerp(end, 0.1)
        assertEquals(start.x, 0.65, 1e-5)
        assertEquals(start.y, 0.65, 1e-5)
        assertEquals(end.x, 2.0)
        assertEquals(end.y, 2.0)
        var dest = Vector2()
        start.set(1.0, 1.0)
        dest.lerp(start, end, 0.5)
        assertEquals(dest.x, 1.5, 1e-5)
        assertEquals(dest.y, 1.5, 1e-5)
        assertEquals(start.x, 1.0)
        assertEquals(start.y, 1.0)
        assertEquals(end.x, 2.0)
        assertEquals(end.y, 2.0)
        dest.lerp(start, end, 0.5)
        assertEquals(dest.x, 1.5, 1e-5)
        assertEquals(dest.y, 1.5, 1e-5)
        assertEquals(start.x, 1.0)
        assertEquals(start.y, 1.0)
        assertEquals(end.x, 2.0)
        assertEquals(end.y, 2.0)
        dest.lerp(start, end, -0.5)
        assertEquals(dest.x, 0.5, 1e-5)
        assertEquals(dest.y, 0.5, 1e-5)
        assertEquals(start.x, 1.0)
        assertEquals(start.y, 1.0)
        assertEquals(end.x, 2.0)
        assertEquals(end.y, 2.0)
        dest.lerp(start, end, 0.0)
        assertEquals(dest.x, 1.0, 1e-5)
        assertEquals(dest.y, 1.0, 1e-5)
        assertEquals(start.x, 1.0)
        assertEquals(start.y, 1.0)
        assertEquals(end.x, 2.0)
        assertEquals(end.y, 2.0)
        dest.lerp(start, end, 0.1)
        assertEquals(dest.x, 1.1, 1e-5)
        assertEquals(dest.y, 1.1, 1e-5)
        assertEquals(start.x, 1.0)
        assertEquals(start.y, 1.0)
        assertEquals(end.x, 2.0)
        assertEquals(end.y, 2.0)
    }

fun equalsEpsilon() {
        var v1 = Vector2(1.0, 1.0)
        var v2 = Vector2(2.0, 2.0)
        assertFalse(v1.equals(v2, 0.0))
        assertFalse(v1.equals(v2, 0.1))
        assertFalse(v1.equals(v2, 0.99))
        assertTrue(v1.equals(v2, 1.0))
        assertTrue(v1.equals(v2, 5.0))
        assertTrue(v1.equals(v2, Double.MAX_VALUE))
        v1.set(Double.MAX_VALUE, Double.MAX_VALUE)
        v2.set(-Double.MAX_VALUE, -Double.MAX_VALUE)
        assertFalse(v1.equals(v2, 0.1))
        assertFalse(v1.equals(v2, 1.0))
        assertFalse(v1.equals(v2, 5.0))
        assertFalse(v1.equals(v2, Double.MAX_VALUE))
        assertTrue(v1.equals(v2, Double.POSITIVE_INFINITY))
        v1.set(1.0, 1.0)
        assertFalse(v1.equals(2.0, 2.0, 0.0))
        assertFalse(v1.equals(2.0, 2.0, 0.1))
        assertFalse(v1.equals(2.0, 2.0, 0.99))
        assertTrue(v1.equals(2.0, 2.0, 1.0))
        assertTrue(v1.equals(2.0, 2.0, 5.0))
        assertTrue(v1.equals(2.0, 2.0, Double.MAX_VALUE))
        v1.set(Double.MAX_VALUE, Double.MAX_VALUE)
        assertFalse(v1.equals(-Double.MAX_VALUE, -Double.MAX_VALUE, 0.1))
        assertFalse(v1.equals(-Double.MAX_VALUE, -Double.MAX_VALUE, 1.0))
        assertFalse(v1.equals(-Double.MAX_VALUE, -Double.MAX_VALUE, 5.0))
        assertFalse(v1.equals(-Double.MAX_VALUE, -Double.MAX_VALUE, Double.MAX_VALUE))
        assertTrue(v1.equals(-Double.MAX_VALUE, -Double.MAX_VALUE, Double.POSITIVE_INFINITY))
        assertFalse(v1.equals(null, 0.0))
        assertTrue(v1.equals(v1, 0.0))
        v1.set(1.0, 2.0)
        v2.set(1.0, 3.0)
        assertFalse(v1.equals(v2, 0.0))
        assertFalse(v1.equals(v2, 0.1))
        assertFalse(v1.equals(v2, 0.99))
        assertTrue(v1.equals(v2, 1.0))
        assertTrue(v1.equals(v2, 5.0))
        assertTrue(v1.equals(v2, Double.MAX_VALUE))
        assertFalse(v1.equals(1.0, 3.0, 0.0))
        assertFalse(v1.equals(1.0, 3.0, 0.1))
        assertFalse(v1.equals(1.0, 3.0, 0.99))
        assertTrue(v1.equals(1.0, 3.0, 1.0))
        assertTrue(v1.equals(1.0, 3.0, 5.0))
        assertTrue(v1.equals(1.0, 3.0, Double.MAX_VALUE))
    }
}

private fun radians(value: Double) = value / 180.0 * PI
private fun degrees(value: Double) = value * 180.0 / PI
