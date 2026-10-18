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

import kotlin.math.PI
import kotlin.test.Test
import kotlin.test.assertEquals
import org.dyn4j.collision.narrowphase.Containment
import org.dyn4j.collision.narrowphase.Sat
import org.dyn4j.geometry.Convex
import org.dyn4j.geometry.Geometry
import org.dyn4j.geometry.Transform
import org.dyn4j.geometry.Vector2

class SatCoverageTest {
    private val sat = Sat()
    private val containment = Containment()
    private fun both(first: Convex, firstTransform: Transform, second: Convex, secondTransform: Transform, expected: Boolean) {
        assertEquals(expected, sat.contains(first, firstTransform, second, secondTransform, containment))
        assertEquals(expected, sat.contains(second, secondTransform, first, firstTransform, containment))
    }
    private fun polygons(smallRadius: Double, shift: Double = 0.0, expected: Boolean) {
        val first = Geometry.createUnitCirclePolygon(5, 0.4)
        val second = Geometry.createUnitCirclePolygon(5, smallRadius)
        val secondTransform = Transform(); secondTransform.translate(shift, 0.0)
        both(first, Transform(), second, secondTransform, expected)
    }
    @Test fun containsPolygonCompletely() = polygons(0.2, expected = true)
    @Test fun doesNotContainPolygon() = polygons(0.2, shift = 0.3, expected = false)
    @Test fun containPolygonButNotInclusive() = polygons(0.2, shift = 0.2, expected = false)
    @Test fun samePolygon() = polygons(0.4, expected = false)
    @Test fun differentPolygons() = both(Geometry.createUnitCirclePolygon(5, 0.4), Transform(), Geometry.createSquare(1.0), Transform(), true)
    @Test fun differentPolygonsNoContainment() {
        val shifted = Transform(); shifted.translate(0.2, 0.0)
        both(Geometry.createUnitCirclePolygon(5, 0.4), shifted, Geometry.createSquare(1.0), Transform(), false)
    }
    @Test fun slice() {
        val polygon = Geometry.createUnitCirclePolygon(5, 0.4)
        both(polygon, Transform(), Geometry.createSlice(0.2, 30.0 * PI / 180.0), Transform(), true)
        val shifted = Transform(); shifted.translate(-0.7, 0.0)
        both(polygon, Transform(), Geometry.createSlice(2.0, 120.0 * PI / 180.0), shifted, true)
    }
    @Test fun sliceNoContainment() = both(Geometry.createUnitCirclePolygon(5, 0.4), Transform(), Geometry.createSlice(0.5, 30.0 * PI / 180.0), Transform(), false)
    @Test fun segmentSegment() {
        both(Geometry.createSegment(Vector2(1.0, 1.0)), Transform(), Geometry.createSegment(Vector2(1.0, 1.0)), Transform(), false)
        both(Geometry.createSegment(Vector2(1.0, 1.0)), Transform(), Geometry.createSegment(Vector2(-1.0, 1.0)), Transform(), false)
    }
    @Test fun circleCircle() {
        val large = Geometry.createCircle(1.0); var small = Geometry.createCircle(1.0)
        val shifted = Transform(); val identity = Transform()
        both(large, shifted, small, identity, false)
        shifted.translate(0.5, 0.0); both(large, shifted, small, identity, false)
        small = Geometry.createCircle(0.5); both(large, shifted, small, identity, false)
        shifted.identity(); both(large, shifted, small, identity, true)
    }
    @Test fun segmentCircle() {
        val segment = Geometry.createSegment(Vector2(0.0, 0.4)); val circle = Geometry.createCircle(0.6)
        val shifted = Transform(); val identity = Transform()
        fun check(expected: Boolean) {
            assertEquals(expected, sat.contains(segment, shifted, circle, identity, containment))
            assertEquals(expected, sat.contains(segment, identity, circle, shifted, containment))
        }
        check(true); shifted.translate(0.6, 0.0); check(false); shifted.translate(0.25, 0.0); check(false)
    }
    @Test fun capsuleCircle() {
        val capsule = Geometry.createCapsule(1.0, 0.5); val circle = Geometry.createCircle(0.6)
        val shifted = Transform(); val identity = Transform()
        fun check(expected: Boolean) {
            assertEquals(expected, sat.contains(capsule, shifted, circle, identity, containment))
            assertEquals(expected, sat.contains(capsule, identity, circle, shifted, containment))
        }
        check(true); shifted.translate(0.6, 0.0); check(false); shifted.translate(0.25, 0.0); check(false)
        shifted.translate(5.0, 0.0); check(false)
    }
}
