/*
 * Copyright (c) 2010-2026 William Bittle  http://www.dyn4j.org/
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
import org.dyn4j.Epsilon
import org.dyn4j.geometry.*
import kotlin.math.*
import kotlin.test.*

val UpstreamRotationCoverageTest by testSuite {
    test("create") { UpstreamRotationCoverageTestFixture().run { create() } }
    test("testIsUnit") { UpstreamRotationCoverageTestFixture().run { testIsUnit() } }
    test("copy") { UpstreamRotationCoverageTestFixture().run { copy() } }
    test("equals") { UpstreamRotationCoverageTestFixture().run { equals() } }
    test("set") { UpstreamRotationCoverageTestFixture().run { set() } }
    test("get") { UpstreamRotationCoverageTestFixture().run { get() } }
    test("toAngle") { UpstreamRotationCoverageTestFixture().run { toAngle() } }
    test("toVector") { UpstreamRotationCoverageTestFixture().run { toVector() } }
    test("dot") { UpstreamRotationCoverageTestFixture().run { dot() } }
    test("cross") { UpstreamRotationCoverageTestFixture().run { cross() } }
    test("isIdentity") { UpstreamRotationCoverageTestFixture().run { isIdentity() } }
    test("inverse") { UpstreamRotationCoverageTestFixture().run { inverse() } }
    test("rotate") { UpstreamRotationCoverageTestFixture().run { rotate() } }
    test("getRotated") { UpstreamRotationCoverageTestFixture().run { getRotated() } }
    test("compare") { UpstreamRotationCoverageTestFixture().run { compare() } }
    test("getRotationBetween") { UpstreamRotationCoverageTestFixture().run { getRotationBetween() } }
    test("getNormalizedAngle") { UpstreamRotationCoverageTestFixture().run { getNormalizedAngle() } }
    test("getShortestDistance") { UpstreamRotationCoverageTestFixture().run { getShortestDistance() } }
    test("isAngleBetween") { UpstreamRotationCoverageTestFixture().run { isAngleBetween() } }
}

private class UpstreamRotationCoverageTestFixture  {
fun create() {
        var r1 = Rotation()
        assertEquals(1.0, r1.getCost(), 1.0e-6)
        assertEquals(0.0, r1.getSint(), 1.0e-6)
        assertNotNull(r1.toString())
        var r2 = Rotation(PI)
        assertEquals(-1.0, r2.getCost(), 1.0e-6)
        assertEquals(0.0, r2.getSint(), 1.0e-6)
        var r3 = RawRotation(-1.0, 0.0)
        assertEquals(-1.0, r3.getCost())
        assertEquals(0.0, r3.getSint())
        var r4 = Rotation(1.0)
        assertEquals(cos(1.0), r4.getCost(), 1.0e-6)
        assertEquals(sin(1.0), r4.getSint(), 1.0e-6)
        var r5 = Rotation(r4)
        assertEquals(cos(1.0), r5.getCost(), 1.0e-6)
        assertEquals(sin(1.0), r5.getSint(), 1.0e-6)
        var r6 = Rotation.of(2.5)
        assertEquals(cos(2.5), r6.getCost(), 1.0e-6)
        assertEquals(sin(2.5), r6.getSint(), 1.0e-6)
        var r9 = Rotation.of(Vector2())
        assertEquals(1.0, r9.getCost(), 1.0e-6)
        assertEquals(0.0, r9.getSint(), 1.0e-6)
        var v1 = Vector2(5.0, -5.0)
        var r7 = Rotation.of(v1)
        assertEquals(cos(radians(-45.0)), r7.getCost(), 1.0e-6)
        assertEquals(sin(radians(-45.0)), r7.getSint(), 1.0e-6)
        var t1 = Transform()
        t1.setRotation(-1.0)
        t1.translate(-10.0, -20.0)
        var r8 = Rotation.of(t1)
        assertEquals(cos(-1.0), r8.getCost(), 1.0e-6)
        assertEquals(sin(-1.0), r8.getSint(), 1.0e-6)
        var r0 = Rotation.rotation0()
        assertEquals(cos(radians(0.0)), r0.getCost(), 1.0e-6)
        assertEquals(sin(radians(0.0)), r0.getSint(), 1.0e-6)
        var r90 = Rotation.rotation90()
        assertEquals(cos(radians(90.0)), r90.getCost(), 1.0e-6)
        assertEquals(sin(radians(90.0)), r90.getSint(), 1.0e-6)
        var r180 = Rotation.rotation180()
        assertEquals(cos(radians(180.0)), r180.getCost(), 1.0e-6)
        assertEquals(sin(radians(180.0)), r180.getSint(), 1.0e-6)
        var r270 = Rotation.rotation270()
        assertEquals(cos(radians(270.0)), r270.getCost(), 1.0e-6)
        assertEquals(sin(radians(270.0)), r270.getSint(), 1.0e-6)
        var r45 = Rotation.rotation45()
        assertEquals(cos(radians(45.0)), r45.getCost(), 1.0e-6)
        assertEquals(sin(radians(45.0)), r45.getSint(), 1.0e-6)
        var r135 = Rotation.rotation135()
        assertEquals(cos(radians(135.0)), r135.getCost(), 1.0e-6)
        assertEquals(sin(radians(135.0)), r135.getSint(), 1.0e-6)
        var r225 = Rotation.rotation225()
        assertEquals(cos(radians(225.0)), r225.getCost(), 1.0e-6)
        assertEquals(sin(radians(225.0)), r225.getSint(), 1.0e-6)
        var r315 = Rotation.rotation315()
        assertEquals(cos(radians(315.0)), r315.getCost(), 1.0e-6)
        assertEquals(sin(radians(315.0)), r315.getSint(), 1.0e-6)
    }

fun testIsUnit() {
        for (i in 0 until 1000) {
            var r = Rotation(radians(i.toDouble()))
            assertEquals(1.0, r.dot(r), 1.0e-6)
        }
    }

fun copy() {
        var r = RawRotation(1.0, 3.0)
        var rc = r.copy()
        assertFalse(r === rc)
        assertEquals(r.getCost(), rc.getCost())
        assertEquals(r.getSint(), rc.getSint())
    }

fun equals() {
        var r = Rotation(2.0)
        assertTrue(r.equals(r))
        assertTrue(r.equals(r.copy()))
        assertTrue(r.equals(Rotation(2.0)))
        assertFalse(r.equals(Rotation(1.0)))
        assertFalse(r.equals(Any()))
        assertFalse(r.equals(null))
        assertFalse(r.equals((Rotation(1.0) as Any)))
        assertFalse(r.equals((null as Any?)))
        assertTrue(r.equals(r, 1.0e-4))
        var r2 = r.copy().rotate(5.0).rotate(-5.0)
        assertTrue(r.equals(r2, 1.0e-4))
        assertFalse(r.equals(Rotation(1.0), 1.0e-4))
        assertTrue(r.equals(2.0))
        assertTrue(r.equals(2.0 + 1.0e-6, 1.0e-4))
        assertFalse(r.equals(1.0))
        assertFalse(r.equals(2.0 + 1.0e-2, 1.0e-4))
    }

fun set() {
        var r = Rotation(2.0)
        var r2 = Rotation(3.0)
        r.set(r2)
        assertFalse(r === r2)
        assertEquals(cos(3.0), r.getCost(), 1.0e-6)
        assertEquals(sin(3.0), r.getSint(), 1.0e-6)
        assertEquals(r2.getCost(), r.getCost())
        assertEquals(r2.getSint(), r.getSint())
        r.set(-1.0)
        assertEquals(cos(-1.0), r.getCost(), 1.0e-6)
        assertEquals(sin(-1.0), r.getSint(), 1.0e-6)
        r.setIdentity()
        assertEquals(1.0, r.getCost(), 1.0e-6)
        assertEquals(0.0, r.getSint(), 1.0e-6)
    }

fun get() {
        var r = Rotation(1.5)
        assertEquals(cos(1.5), r.getCost())
        assertEquals(sin(1.5), r.getSint())
    }

fun toAngle() {
        var r = RawRotation(0.0, -1.0)
        assertEquals(-PI / 2.0, r.toRadians(), 1.0e-6)
        assertEquals(-90.0, r.toDegrees(), 1.0e-6)
        r.rotate135()
        assertEquals(PI / 4.0, r.toRadians(), 1.0e-6)
        assertEquals(45.0, r.toDegrees(), 1.0e-6)
    }

fun toVector() {
        var r = Rotation(radians(30.0))
        var v1 = r.toVector()
        var v2 = r.toVector(2.5)
        assertEquals(r.toRadians(), v1.getDirection(), 1.0e-6)
        assertEquals(r.toRadians(), v2.getDirection(), 1.0e-6)
        assertEquals(1.0, v1.getMagnitude(), 1.0e-6)
        assertEquals(2.5, v2.getMagnitude(), 1.0e-6)
    }

fun dot() {
        var r1 = RawRotation(1.0, 0.0)
        var r2 = RawRotation(0.0, 1.0)
        var v = Vector2(0.0, -5.0)
        assertEquals(0.0, r1.dot(r2), 1.0e-6)
        assertEquals(-1.0, r1.dot(r2.getRotated90()), 1.0e-6)
        assertEquals(0.0, RotationVectorAccessFixture.dot(r1, v), 1.0e-6)
        assertEquals(1.0, r1.dot(r1), 1.0e-6)
        assertEquals(1.0, r2.dot(r2), 1.0e-6)
    }

fun cross() {
        var r1 = RawRotation(1.0, 0.0)
        var r2 = RawRotation(0.0, 1.0)
        var v = Vector2(-5.0, 0.0)
        assertEquals(1.0, r1.cross(r2), 1.0e-6)
        assertEquals(0.0, r1.cross(r2.getRotated90()), 1.0e-6)
        assertEquals(0.0, RotationVectorAccessFixture.cross(r1, v), 1.0e-6)
        assertEquals(0.0, r1.cross(r1), 1.0e-6)
        assertEquals(0.0, r2.cross(r2), 1.0e-6)
    }

fun isIdentity() {
        var r = Rotation()
        assertTrue(r.isIdentity())
        assertTrue(r.isIdentity(1.0e-6))
        r.set(1.0)
        assertFalse(r.isIdentity())
        assertFalse(r.isIdentity(1.0e-6))
        r.set(1.0e-6)
        assertFalse(r.isIdentity())
        assertTrue(r.isIdentity(1.0e-4))
    }

fun inverse() {
        var r1 = Rotation(0.0)
        r1.inverse()
        assertEquals(1.0, r1.getCost(), 1.0e-6)
        assertEquals(0.0, r1.getSint(), 1.0e-6)
        var r2 = Rotation(PI / 2.0)
        var r3 = r2.copy()
        r2.inverse()
        assertEquals(0.0, r2.getCost(), 1.0e-6)
        assertEquals(-1.0, r2.getSint(), 1.0e-6)
        r2.inverse()
        assertEquals(r3, r2)
        var temp = r2.getInversed()
        assertEquals(0.0, temp.getCost(), 1.0e-6)
        assertEquals(-1.0, temp.getSint(), 1.0e-6)
        assertEquals(r3, r2)
    }

fun rotate() {
        var r1 = Rotation(radians(0.0))
        r1.rotate(radians(90.0))
        assertEquals(0.0, r1.getCost(), 1.0e-6)
        assertEquals(1.0, r1.getSint(), 1.0e-6)
        r1.rotate(Rotation(radians(90.0)))
        assertEquals(-1.0, r1.getCost(), 1.0e-6)
        assertEquals( 0.0, r1.getSint(), 1.0e-6)
        var r2 = Rotation(radians(45.0))
        r2.rotate(radians(63.0))
        assertEquals(-0.309, r2.getCost(), 1.0e-3)
        assertEquals( 0.951, r2.getSint(), 1.0e-3)
        r2.rotate(Rotation(radians(29.0)))
        assertEquals(-0.731, r2.getCost(), 1.0e-3)
        assertEquals( 0.682, r2.getSint(), 1.0e-3)
        var r3 = Rotation(radians(60.0))
        assertEquals(0.500, r3.getCost(), 1.0e-3)
        assertEquals(0.866, r3.getSint(), 1.0e-3)
        r3.rotate90()
        assertEquals(-0.866, r3.getCost(), 1.0e-3)
        assertEquals( 0.500, r3.getSint(), 1.0e-3)
        r3.rotate180()
        assertEquals( 0.866, r3.getCost(), 1.0e-3)
        assertEquals(-0.500, r3.getSint(), 1.0e-3)
        r3.rotate270()
        assertEquals(-0.500, r3.getCost(), 1.0e-3)
        assertEquals(-0.866, r3.getSint(), 1.0e-3)
        r3.rotate90()
        assertEquals( 0.866, r3.getCost(), 1.0e-3)
        assertEquals(-0.500, r3.getSint(), 1.0e-3)
        r3.rotate45()
        assertEquals(0.966, r3.getCost(), 1.0e-3)
        assertEquals(0.259, r3.getSint(), 1.0e-3)
        r3.rotate45()
        assertEquals(0.500, r3.getCost(), 1.0e-3)
        assertEquals(0.866, r3.getSint(), 1.0e-3)
        r3.rotate135()
        assertEquals(-0.966, r3.getCost(), 1.0e-3)
        assertEquals(-0.259, r3.getSint(), 1.0e-3)
        r3.rotate225()
        assertEquals(0.500, r3.getCost(), 1.0e-3)
        assertEquals(0.866, r3.getSint(), 1.0e-3)
        r3.rotate315()
        assertEquals(0.966, r3.getCost(), 1.0e-3)
        assertEquals(0.259, r3.getSint(), 1.0e-3)
    }

fun getRotated() {
        lateinit var temp: Rotation
        var r1 = Rotation(radians(0.0))
        temp = r1.getRotated(radians(90.0))
        assertEquals(0.0, temp.getCost(), 1.0e-6)
        assertEquals(1.0, temp.getSint(), 1.0e-6)
        temp = r1.getRotated(Rotation(radians(180.0)))
        assertEquals(-1.0, temp.getCost(), 1.0e-6)
        assertEquals( 0.0, temp.getSint(), 1.0e-6)
        var r2 = Rotation(radians(45.0))
        temp = r2.getRotated(radians(63.0))
        assertEquals(-0.309, temp.getCost(), 1.0e-3)
        assertEquals( 0.951, temp.getSint(), 1.0e-3)
        temp = r2.getRotated(Rotation(radians(29.0)))
        assertEquals(0.276, temp.getCost(), 1.0e-3)
        assertEquals(0.961, temp.getSint(), 1.0e-3)
        var r3 = Rotation(radians(60.0))
        assertEquals(0.500, r3.getCost(), 1.0e-3)
        assertEquals(0.866, r3.getSint(), 1.0e-3)
        temp = r3.getRotated90()
        assertEquals(-0.866, temp.getCost(), 1.0e-3)
        assertEquals( 0.500, temp.getSint(), 1.0e-3)
        temp = r3.getRotated180()
        assertEquals(-0.500, temp.getCost(), 1.0e-3)
        assertEquals(-0.866, temp.getSint(), 1.0e-3)
        temp = r3.getRotated270()
        assertEquals( 0.866, temp.getCost(), 1.0e-3)
        assertEquals(-0.500, temp.getSint(), 1.0e-3)
        temp = r3.getRotated45()
        assertEquals(-0.259, temp.getCost(), 1.0e-3)
        assertEquals( 0.966, temp.getSint(), 1.0e-3)
        temp = r3.getRotated135()
        assertEquals(-0.966, temp.getCost(), 1.0e-3)
        assertEquals(-0.259, temp.getSint(), 1.0e-3)
        temp = r3.getRotated225()
        assertEquals( 0.259, temp.getCost(), 1.0e-3)
        assertEquals(-0.966, temp.getSint(), 1.0e-3)
        temp = r3.getRotated315()
        assertEquals(0.966, temp.getCost(), 1.0e-3)
        assertEquals(0.259, temp.getSint(), 1.0e-3)
    }

fun compare() {
        var r1 = Rotation(radians(10.0))
        var r2 = Rotation(radians(100.0))
        var r3 = Rotation(radians(100.0))
        var r4 = Rotation(radians(-50.0))
        var r5 = Rotation(radians(110.0 + 10.0 * 360.0))
        var v1 = Vector2(radians(-65.0))
        var v2 = Vector2(radians(120.0))
        v1.multiply(4.5)
        v2.multiply(0.75)
        assertEquals(0, r1.compare(r1))
        assertEquals(r1.hashCode(), r1.hashCode())
        assertEquals(0, r2.compare(r3))
        assertEquals(r2.hashCode(), r3.hashCode())
        assertEquals(1, r1.compare(r2))
        assertFalse(r1.hashCode() == r2.hashCode())
        assertEquals(1, r3.compare(r5))
        assertFalse(r3.hashCode() == r5.hashCode())
        assertEquals(-1, r1.compare(r4))
        assertFalse(r1.hashCode() == r4.hashCode())
        assertEquals(1, r3.compare(v2))
        assertEquals(-1, r4.compare(v1))
    }

fun getRotationBetween() {
        var r1 = Rotation(radians(10.0))
        var r2 = Rotation(radians(100.0))
        var r3 = Rotation(radians(100.0))
        var r4 = Rotation(radians(-50.0))
        var r5 = Rotation(radians(110.0 + 10.0 * 360.0))
        var v1 = Vector2(radians(-65.0))
        var v2 = Vector2(radians(120.0))
        v1.multiply(4.5)
        v2.multiply(0.75)
        assertEquals(radians(0.0), r1.getRotationBetween(r1).toRadians(), 1.0e-6)
        assertEquals(radians(0.0), r2.getRotationBetween(r3).toRadians(), 1.0e-6)
        assertEquals(radians(90.0), r1.getRotationBetween(r2).toRadians(), 1.0e-6)
        assertEquals(radians(-60.0), r1.getRotationBetween(r4).toRadians(), 1.0e-6)
        assertEquals(radians(10.0), r3.getRotationBetween(r5).toRadians(), 1.0e-6)
        assertEquals(radians(20.0), r3.getRotationBetween(v2).toRadians(), 1.0e-6)
        assertEquals(radians(-15.0), r4.getRotationBetween(v1).toRadians(), 1.0e-6)
    }

fun getNormalizedAngle() {
        var data = arrayOf(

            doubleArrayOf(0.0, 0.0),
            doubleArrayOf(PI / 2.0, PI / 2.0),
            doubleArrayOf(PI, -PI),

            doubleArrayOf(1.5 * PI, -0.5 * PI),
            doubleArrayOf(2.0 * PI, 0.0),
            doubleArrayOf(2.5 * PI, PI / 2.0),

            doubleArrayOf(-0.5 * PI, -0.5 * PI),
            doubleArrayOf(-PI, -PI),
            doubleArrayOf(-1.5 * PI, PI / 2.0),
            doubleArrayOf(-2.0 * PI, 0.0),

            doubleArrayOf(100.0 * 2.0 * PI + 1.0, 1.0),
            doubleArrayOf(-100.0 * 2.0 * PI - 1.0, -1.0)
        )

        for (testCase in data) {
            var input = testCase[0]
            var expected = testCase[1]
            assertEquals(expected, Rotation.getNormalizedAngle(input), 1e-9)
        }
    }

fun getShortestDistance() {
        var testCases = arrayOf(

            doubleArrayOf(0.0, 0.0, 0.0),
            doubleArrayOf(PI, PI, 0.0),
            doubleArrayOf(-PI, -PI, 0.0),

            doubleArrayOf(0.0, PI / 2.0, PI / 2.0),
            doubleArrayOf(-PI / 2.0, 0.0, PI / 2.0),
            doubleArrayOf(-3.0 * PI / 4.0, -PI / 4.0, PI / 2.0),

            doubleArrayOf(PI / 2.0, 0.0, -PI / 2.0),
            doubleArrayOf(0.0, -PI / 2.0, -PI / 2.0),
            doubleArrayOf(-PI / 4.0, -3.0 * PI / 4.0, -PI / 2.0),

            doubleArrayOf(3.0 * PI / 4.0, -3.0 * PI / 4.0, PI / 2.0),
            doubleArrayOf(-3.0 * PI / 4.0, 3.0 * PI / 4.0, -PI / 2.0),

            doubleArrayOf(0.0, PI, -PI),
            doubleArrayOf(PI, 0.0, -PI),
            doubleArrayOf(-PI, 0.0, -PI)
        )

        for (testCase in testCases) {
            var angle1 = testCase[0]
            var angle2 = testCase[1]
            var expected = testCase[2]
            assertEquals(expected, Rotation.getShortestDistance(angle1, angle2), 1e-9)
        }
    }

fun isAngleBetween() {
        var data = arrayOf(
            doubleArrayOf(-30.0, 30.0, 10.0),
            doubleArrayOf(0.0, 30.0, 10.0),
            doubleArrayOf(20.0, 30.0, 10.0),
            doubleArrayOf(10.0, 30.0, 10.0),
            doubleArrayOf(-50.0, -20.0, 10.0),
            doubleArrayOf(-50.0, -20.0, -30.0),
            doubleArrayOf(50.0, -30.0, 80.0),
            doubleArrayOf(50.0, -30.0, 10.0),
            doubleArrayOf(50.0, -50.0, 100.0),
            doubleArrayOf(50.0, -50.0, 180.0),
            doubleArrayOf(50.0, -50.0, -170.0),
            doubleArrayOf(100.0, -100.0, 160.0),
            doubleArrayOf(100.0, -100.0, -180.0),
            doubleArrayOf(0.0, 0.0, 10.0),
            doubleArrayOf(5.0, -5.0, 10.0),
            doubleArrayOf(-60.0, 60.0, -10.0)
        )

        var expectedOutcome = booleanArrayOf(
            true,
            true,
            false,
            true,
            false,
            true,
            true,
            false,
            true,
            true,
            true,
            true,
            true,
            false,
            true,
            true
        )
        for (i in 0 until data.size) {
            var a1 = radians(data[i][0])
            var a2 = radians(data[i][1])
            var a = radians(data[i][2])
            var outcome = expectedOutcome[i]
            assertEquals(outcome, Rotation.isAngleBetween(a, a1, a2), "${degrees(a1)} <= ${degrees(a)} <= ${degrees(a2)}")
        }
    }
}

private fun radians(value: Double) = value / 180.0 * PI
private fun degrees(value: Double) = value * 180.0 / PI


private class RawRotation(cost: Double, sint: Double) : Rotation(cost, sint)
