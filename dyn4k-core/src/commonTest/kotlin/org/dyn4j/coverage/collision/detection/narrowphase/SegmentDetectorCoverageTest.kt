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
package org.dyn4j.coverage.collision.detection.narrowphase

import de.infix.testBalloon.framework.core.testSuite
import kotlin.math.PI
import kotlin.test.*
import org.dyn4j.collision.narrowphase.Raycast
import org.dyn4j.collision.narrowphase.SegmentDetector
import org.dyn4j.geometry.Ray
import org.dyn4j.geometry.Segment
import org.dyn4j.geometry.Transform
import org.dyn4j.geometry.Vector2

val SegmentDetectorCoverageTest by testSuite {
    test("raycastHorizontalSegmentNoIntersection") { SegmentDetectorCoverageTestFixture().run { raycastHorizontalSegmentNoIntersection() } }
    test("raycastHorizontalSegmentWithIntersection") { SegmentDetectorCoverageTestFixture().run { raycastHorizontalSegmentWithIntersection() } }
    test("raycastVerticalSegmentNoIntersection") { SegmentDetectorCoverageTestFixture().run { raycastVerticalSegmentNoIntersection() } }
    test("raycastVerticalSegmentWithIntersection") { SegmentDetectorCoverageTestFixture().run { raycastVerticalSegmentWithIntersection() } }
    test("raycastParallelSegmentBehindRay") { SegmentDetectorCoverageTestFixture().run { raycastParallelSegmentBehindRay() } }
    test("raycastParallelSegmentInFrontOfRay") { SegmentDetectorCoverageTestFixture().run { raycastParallelSegmentInFrontOfRay() } }
    test("raycastWithRayStartingInsideParallelSegment") { SegmentDetectorCoverageTestFixture().run { raycastWithRayStartingInsideParallelSegment() } }
    test("raycastDegenerateSegment") { SegmentDetectorCoverageTestFixture().run { raycastDegenerateSegment() } }
}

private class SegmentDetectorCoverageTestFixture  {
    private fun cast(start: Vector2, direction: Vector2, first: Vector2, second: Vector2) =
        Raycast().also { result -> SegmentDetector.raycast(Ray(start, direction), 0.0, Segment(first, second), Transform(), result) }
    private fun expectRaycast(ray: Ray, segment: Segment, hit: Boolean, x: Double = 0.0, y: Double = 0.0, nx: Double = 0.0, ny: Double = 0.0, distance: Double = 0.0) {
        val result = Raycast()
        assertEquals(hit, SegmentDetector.raycast(ray, 0.0, segment, Transform(), result))
        assertEquals(x, result.getPoint().x, 1e-3); assertEquals(y, result.getPoint().y, 1e-3)
        assertEquals(nx, result.getNormal().x, 1e-3); assertEquals(ny, result.getNormal().y, 1e-3)
        assertEquals(distance, result.getDistance(), 1e-3)
    }
    private val diagonalRay get() = Ray(Vector2(-0.85, 0.48), PI * 0.25)
fun raycastHorizontalSegmentNoIntersection() = expectRaycast(diagonalRay, Segment(Vector2(-0.59, 0.68), Vector2(-0.40, 0.68)), false)
fun raycastHorizontalSegmentWithIntersection() = expectRaycast(diagonalRay, Segment(Vector2(-0.68, 0.68), Vector2(-0.53, 0.68)), true, -0.649, 0.680, 0.000, -1.000, 0.282)
fun raycastVerticalSegmentNoIntersection() = expectRaycast(diagonalRay, Segment(Vector2(-0.58, 0.68), Vector2(-0.58, 0.41)), false)
fun raycastVerticalSegmentWithIntersection() = expectRaycast(diagonalRay, Segment(Vector2(-0.58, 1.2), Vector2(-0.58, 0.41)), true, -0.580, 0.750, -1.000, 0.000, 0.381)
fun raycastParallelSegmentBehindRay() {
        expectRaycast(Ray(Vector2(3.0, 0.0), Vector2(1.0, 0.0)), Segment(Vector2(0.0, 0.0), Vector2(2.0, 0.0)), false)
        val ray = Ray(Vector2(-3.0, 0.0), Vector2(-1.0, 0.0))
        expectRaycast(ray, Segment(Vector2(0.0, 0.0), Vector2(-2.0, 0.0)), false)
        expectRaycast(ray, Segment(Vector2(-2.0, 0.0), Vector2(0.0, 0.0)), false)
    }
fun raycastParallelSegmentInFrontOfRay() {
        val forward = Ray(Vector2(-1.0, 0.0), Vector2(1.0, 0.0))
        expectRaycast(forward, Segment(Vector2(0.0, 0.0), Vector2(2.0, 0.0)), true, 0.0, 0.0, -1.0, 0.0, 1.0)
        val backward = Ray(Vector2(3.0, 0.0), Vector2(-1.0, 0.0))
        expectRaycast(backward, Segment(Vector2(0.0, 0.0), Vector2(2.0, 0.0)), true, 2.0, 0.0, 1.0, 0.0, 1.0)
        expectRaycast(backward, Segment(Vector2(2.0, 0.0), Vector2(0.0, 0.0)), true, 2.0, 0.0, 1.0, 0.0, 1.0)
    }
fun raycastWithRayStartingInsideParallelSegment() {
        for (direction in listOf(Vector2(1.0, 0.0), Vector2(-1.0, 0.0)))
            expectRaycast(Ray(Vector2(1.0, 0.0), direction), Segment(Vector2(0.0, 0.0), Vector2(2.0, 0.0)), false)
        for (direction in listOf(Vector2(-1.0, 0.0), Vector2(1.0, 0.0)))
            for ((first, second) in listOf(Vector2(0.0, 0.0) to Vector2(-2.0, 0.0), Vector2(-2.0, 0.0) to Vector2(0.0, 0.0)))
                expectRaycast(Ray(Vector2(-1.0, 0.0), direction), Segment(first, second), false)
    }
fun raycastDegenerateSegment() {
        val segment = Segment(Vector2(1.0, 0.0), Vector2(0.0, 0.0))
        segment.getPoint1().set(0.0, 0.0)
        expectRaycast(Ray(Vector2(1.0, 0.0), Vector2(1.0, 0.0)), segment, false)
    }
}
