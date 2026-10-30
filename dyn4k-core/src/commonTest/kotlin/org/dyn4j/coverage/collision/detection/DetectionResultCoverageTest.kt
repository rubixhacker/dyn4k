/*
 * Copyright (c) 2010-2021 William Bittle  http://www.dyn4j.org/
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
package org.dyn4j.coverage.collision.detection

import de.infix.testBalloon.framework.core.testSuite
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertNotSame
import kotlin.test.assertSame
import kotlin.test.assertTrue
import org.dyn4j.collision.continuous.TimeOfImpact
import org.dyn4j.collision.narrowphase.Containment
import org.dyn4j.collision.narrowphase.Penetration
import org.dyn4j.collision.narrowphase.Raycast
import org.dyn4j.collision.narrowphase.Separation
import org.dyn4j.geometry.Vector2

val DetectionResultCoverageTest by testSuite {
    test("penetrationCreate") { DetectionResultCoverageTestFixture().run { penetrationCreate() } }
    test("penetrationGetSet") { DetectionResultCoverageTestFixture().run { penetrationGetSet() } }
    test("penetrationClear") { DetectionResultCoverageTestFixture().run { penetrationClear() } }
    test("penetrationCopy") { DetectionResultCoverageTestFixture().run { penetrationCopy() } }
    test("penetrationShift") { DetectionResultCoverageTestFixture().run { penetrationShift() } }
    test("separationCreate") { DetectionResultCoverageTestFixture().run { separationCreate() } }
    test("separationGetSet") { DetectionResultCoverageTestFixture().run { separationGetSet() } }
    test("separationClear") { DetectionResultCoverageTestFixture().run { separationClear() } }
    test("separationCopy") { DetectionResultCoverageTestFixture().run { separationCopy() } }
    test("separationShift") { DetectionResultCoverageTestFixture().run { separationShift() } }
    test("raycastCreate") { DetectionResultCoverageTestFixture().run { raycastCreate() } }
    test("raycastGetSet") { DetectionResultCoverageTestFixture().run { raycastGetSet() } }
    test("raycastClear") { DetectionResultCoverageTestFixture().run { raycastClear() } }
    test("raycastCopy") { DetectionResultCoverageTestFixture().run { raycastCopy() } }
    test("raycastShift") { DetectionResultCoverageTestFixture().run { raycastShift() } }
    test("containmentCreate") { DetectionResultCoverageTestFixture().run { containmentCreate() } }
    test("containmentGetSet") { DetectionResultCoverageTestFixture().run { containmentGetSet() } }
    test("containmentClear") { DetectionResultCoverageTestFixture().run { containmentClear() } }
    test("containmentCopy") { DetectionResultCoverageTestFixture().run { containmentCopy() } }
    test("containmentSet") { DetectionResultCoverageTestFixture().run { containmentSet() } }
    test("timeOfImpactCreate") { DetectionResultCoverageTestFixture().run { timeOfImpactCreate() } }
    test("timeOfImpactGetSet") { DetectionResultCoverageTestFixture().run { timeOfImpactGetSet() } }
    test("timeOfImpactCopy") { DetectionResultCoverageTestFixture().run { timeOfImpactCopy() } }
    test("timeOfImpactTostring") { DetectionResultCoverageTestFixture().run { timeOfImpactTostring() } }
}

private class DetectionResultCoverageTestFixture  {
    private class SeedPenetration(normal: Vector2, depth: Double) : Penetration(normal, depth)
    private class SeedSeparation(normal: Vector2, distance: Double, p1: Vector2, p2: Vector2) :
        Separation(normal, distance, p1, p2)
    private class SeedRaycast(point: Vector2, normal: Vector2, distance: Double) :
        Raycast(point, normal, distance)
    private class SeedContainment(a: Boolean, b: Boolean) : Containment(a, b)
    private class SeedTimeOfImpact(time: Double, separation: Separation) : TimeOfImpact(time, separation)

fun penetrationCreate() {
        val empty = Penetration()
        assertEquals(0.0, empty.getDepth())
        assertEquals(Vector2(), empty.getNormal())
        val input = Vector2(1.0, 1.0)
        val result = SeedPenetration(input, 2.0)
        assertEquals(2.0, result.getDepth())
        assertEquals(Vector2(1.0, 1.0), result.getNormal())
        assertNotSame(input, result.getNormal())
        assertNotNull(result.toString())
    }

fun penetrationGetSet() {
        val result = Penetration()
        val input = Vector2(1.0, 1.0)
        val exposed = result.getNormal()
        result.setNormal(input)
        assertSame(exposed, result.getNormal())
        assertNotSame(input, result.getNormal())
        assertEquals(Vector2(1.0, 1.0), exposed)
        result.setDepth(3.0)
        assertEquals(3.0, result.getDepth())
        assertEquals(Vector2(1.0, 1.0), exposed)
    }

fun penetrationClear() {
        val result = SeedPenetration(Vector2(1.0, 1.0), 2.0)
        val exposed = result.getNormal()
        result.clear()
        assertSame(exposed, result.getNormal())
        assertEquals(Vector2(), exposed)
        assertEquals(0.0, result.getDepth())
    }

fun penetrationCopy() {
        val source = SeedPenetration(Vector2(1.0, 1.0), 2.0)
        val target = Penetration()
        target.set(source)
        val copy = source.copy()
        for (result in listOf(target, copy)) {
            assertEquals(2.0, result.getDepth())
            assertEquals(Vector2(1.0, 1.0), result.getNormal())
            assertNotSame(source.getNormal(), result.getNormal())
        }
    }

fun penetrationShift() {
        val result = SeedPenetration(Vector2(1.0, 1.0), 2.0)
        result.shift(Vector2(3.0, -2.0))
        assertEquals(Vector2(1.0, 1.0), result.getNormal())
        assertEquals(2.0, result.getDepth())
    }

fun separationCreate() {
        val empty = Separation()
        assertEquals(0.0, empty.getDistance())
        assertEquals(Vector2(), empty.getNormal())
        assertEquals(Vector2(), empty.getPoint1())
        assertEquals(Vector2(), empty.getPoint2())
        val n = Vector2(1.0, 1.0)
        val p1 = Vector2(2.0, 2.0)
        val p2 = Vector2(3.0, 3.0)
        val result = SeedSeparation(n, 5.0, p1, p2)
        assertEquals(5.0, result.getDistance())
        assertEquals(n, result.getNormal())
        assertEquals(p1, result.getPoint1())
        assertEquals(p2, result.getPoint2())
        assertNotSame(n, result.getNormal())
        assertNotSame(p1, result.getPoint1())
        assertNotSame(p2, result.getPoint2())
        assertNotNull(result.toString())
    }

fun separationGetSet() {
        val result = Separation()
        val normal = result.getNormal()
        val point1 = result.getPoint1()
        val point2 = result.getPoint2()
        val n = Vector2(1.0, 1.0)
        val p1 = Vector2(2.0, 2.0)
        val p2 = Vector2(3.0, 3.0)
        result.setNormal(n)
        result.setPoint1(p1)
        result.setPoint2(p2)
        result.setDistance(5.0)
        assertSame(normal, result.getNormal())
        assertSame(point1, result.getPoint1())
        assertSame(point2, result.getPoint2())
        assertNotSame(n, normal)
        assertNotSame(p1, point1)
        assertNotSame(p2, point2)
        assertEquals(Vector2(1.0, 1.0), normal)
        assertEquals(Vector2(2.0, 2.0), point1)
        assertEquals(Vector2(3.0, 3.0), point2)
        assertEquals(5.0, result.getDistance())
    }

fun separationClear() {
        val result = SeedSeparation(Vector2(1.0, 1.0), 5.0, Vector2(2.0, 2.0), Vector2(3.0, 3.0))
        result.clear()
        assertEquals(Vector2(), result.getNormal())
        assertEquals(Vector2(), result.getPoint1())
        assertEquals(Vector2(), result.getPoint2())
        assertEquals(0.0, result.getDistance())
    }

fun separationCopy() {
        val source = SeedSeparation(Vector2(1.0, 1.0), 5.0, Vector2(2.0, 2.0), Vector2(3.0, 3.0))
        val target = Separation()
        target.set(source)
        for (result in listOf(target, source.copy())) {
            assertEquals(5.0, result.getDistance())
            assertEquals(Vector2(1.0, 1.0), result.getNormal())
            assertEquals(Vector2(2.0, 2.0), result.getPoint1())
            assertEquals(Vector2(3.0, 3.0), result.getPoint2())
            assertNotSame(source.getNormal(), result.getNormal())
            assertNotSame(source.getPoint1(), result.getPoint1())
            assertNotSame(source.getPoint2(), result.getPoint2())
        }
    }

fun separationShift() {
        val result = SeedSeparation(Vector2(1.0, 1.0), 5.0, Vector2(2.0, 2.0), Vector2(3.0, 3.0))
        result.shift(Vector2(3.0, -2.0))
        assertEquals(Vector2(1.0, 1.0), result.getNormal())
        assertEquals(Vector2(5.0, 0.0), result.getPoint1())
        assertEquals(Vector2(6.0, 1.0), result.getPoint2())
        assertEquals(5.0, result.getDistance())
    }

fun raycastCreate() {
        val empty = Raycast()
        assertEquals(Vector2(), empty.getPoint())
        assertEquals(Vector2(), empty.getNormal())
        assertEquals(0.0, empty.getDistance())
        val point = Vector2(1.0, 2.0)
        val normal = Vector2(3.0, 4.0)
        val result = SeedRaycast(point, normal, 5.0)
        assertEquals(point, result.getPoint())
        assertEquals(normal, result.getNormal())
        assertEquals(5.0, result.getDistance())
        assertNotSame(point, result.getPoint())
        assertNotSame(normal, result.getNormal())
    }

fun raycastGetSet() {
        val result = Raycast()
        val point = result.getPoint()
        val normal = result.getNormal()
        val newPoint = Vector2(1.0, 2.0)
        val newNormal = Vector2(3.0, 4.0)
        result.setPoint(newPoint)
        result.setNormal(newNormal)
        result.setDistance(5.0)
        assertSame(point, result.getPoint())
        assertSame(normal, result.getNormal())
        assertNotSame(newPoint, point)
        assertNotSame(newNormal, normal)
        assertEquals(Vector2(1.0, 2.0), point)
        assertEquals(Vector2(3.0, 4.0), normal)
        assertEquals(5.0, result.getDistance())
    }

fun raycastClear() {
        val result = SeedRaycast(Vector2(1.0, 2.0), Vector2(3.0, 4.0), 5.0)
        result.clear()
        assertEquals(Vector2(), result.getPoint())
        assertEquals(Vector2(), result.getNormal())
        assertEquals(0.0, result.getDistance())
    }

fun raycastCopy() {
        val source = SeedRaycast(Vector2(1.0, 2.0), Vector2(3.0, 4.0), 5.0)
        val target = Raycast()
        target.set(source)
        for (result in listOf(target, source.copy())) {
            assertEquals(Vector2(1.0, 2.0), result.getPoint())
            assertEquals(Vector2(3.0, 4.0), result.getNormal())
            assertEquals(5.0, result.getDistance())
            assertNotSame(source.getPoint(), result.getPoint())
            assertNotSame(source.getNormal(), result.getNormal())
        }
    }

fun raycastShift() {
        val result = SeedRaycast(Vector2(1.0, 2.0), Vector2(3.0, 4.0), 5.0)
        result.shift(Vector2(3.0, -2.0))
        assertEquals(Vector2(4.0, 0.0), result.getPoint())
        assertEquals(Vector2(3.0, 4.0), result.getNormal())
        assertEquals(5.0, result.getDistance())
    }

fun containmentCreate() {
        val empty = Containment()
        assertFalse(empty.isAContainedInB())
        assertFalse(empty.isBContainedInA())
        val result = SeedContainment(true, false)
        assertTrue(result.isAContainedInB())
        assertFalse(result.isBContainedInA())
        assertNotNull(result.toString())
    }

fun containmentGetSet() {
        val result = Containment()
        result.setAContainedInB(true)
        assertTrue(result.isAContainedInB())
        assertFalse(result.isBContainedInA())
        result.setBContainedInA(true)
        assertTrue(result.isBContainedInA())
        result.setAContainedInB(false)
        assertFalse(result.isAContainedInB())
        assertTrue(result.isBContainedInA())
        result.setBContainedInA(false)
        assertFalse(result.isBContainedInA())
    }

fun containmentClear() {
        val result = SeedContainment(true, true)
        result.clear()
        assertFalse(result.isAContainedInB())
        assertFalse(result.isBContainedInA())
    }

fun containmentCopy() {
        val result = SeedContainment(true, true).copy()
        assertTrue(result.isAContainedInB())
        assertTrue(result.isBContainedInA())
    }

fun containmentSet() {
        val result = Containment()
        result.set(SeedContainment(true, true))
        assertTrue(result.isAContainedInB())
        assertTrue(result.isBContainedInA())
    }

fun timeOfImpactCreate() {
        val input = Separation()
        val result = SeedTimeOfImpact(0.0, input)
        assertEquals(0.0, result.getTime())
        assertNotSame(input, result.getSeparation())
    }

fun timeOfImpactGetSet() {
        val input = Separation()
        val result = TimeOfImpact()
        val exposed = result.getSeparation()
        result.setTime(1.0)
        result.setSeparation(input)
        assertEquals(1.0, result.getTime())
        assertNotSame(input, result.getSeparation())
        assertSame(exposed, result.getSeparation())
    }

fun timeOfImpactCopy() {
        val result = TimeOfImpact()
        result.setTime(1.0)
        result.setSeparation(Separation().also { it.setDistance(2.0) })
        val copy = result.copy()
        assertEquals(1.0, copy.getTime())
        assertEquals(2.0, copy.getSeparation().getDistance())
        assertNotSame(result.getSeparation(), copy.getSeparation())
    }

fun timeOfImpactTostring() {
        val result = TimeOfImpact()
        result.setTime(1.0)
        assertNotNull(result.toString())
    }
}
