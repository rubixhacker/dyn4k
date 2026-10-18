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
package org.dyn4j.coverage.collision.detection.continuous

import kotlin.math.PI
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertFailsWith
import kotlin.test.assertSame
import kotlin.test.assertTrue
import org.dyn4j.collision.continuous.ConservativeAdvancement
import org.dyn4j.collision.continuous.TimeOfImpact
import org.dyn4j.collision.narrowphase.Gjk
import org.dyn4j.geometry.Convex
import org.dyn4j.geometry.Geometry
import org.dyn4j.geometry.Transform
import org.dyn4j.geometry.Vector2

class ConservativeAdvancementCoverageTest {
    private val moving = Geometry.createUnitCirclePolygon(5, 0.1)
    private val ground = Geometry.createRectangle(20.0, 0.5)
    private val detector = ConservativeAdvancement()
    private val step = 1.0 / 60.0

    private fun moved(x: Double, y: Double) = Transform().also { it.translate(x, y) }
    private fun impact(
        first: Convex, firstTransform: Transform, firstMotion: Vector2, firstRotation: Double,
        second: Convex, secondTransform: Transform, secondMotion: Vector2, secondRotation: Double
    ): Pair<Boolean, TimeOfImpact> {
        val result = TimeOfImpact()
        val hit = detector.getTimeOfImpact(first, firstTransform, firstMotion, firstRotation,
            second, secondTransform, secondMotion, secondRotation, result)
        return hit to result
    }

    @Test fun afterMidPoint() {
        val start = moved(0.0, 1.5)
        val motion = Vector2(0.0, -120.0 * step)
        val (hit, result) = impact(moving, start, motion, 0.0, ground, Transform(), Vector2(), 0.0)
        assertTrue(hit)
        assertEquals(0.577, result.getTime(), 1e-3)
        val final = start.lerped(motion, 0.0, result.getTime())
        assertEquals(0.000, final.getTranslationX(), 1e-3)
        assertEquals(0.346, final.getTranslationY(), 1e-3)
    }

    @Test fun beforeMidPoint() {
        val start = moved(0.0, 1.0)
        val motion = Vector2(0.0, -120.0 * step)
        val (hit, result) = impact(moving, start, motion, 0.0, ground, Transform(), Vector2(), 0.0)
        assertTrue(hit)
        assertEquals(0.327, result.getTime(), 1e-3)
        val final = start.lerped(motion, 0.0, result.getTime())
        assertEquals(0.000, final.getTranslationX(), 1e-3)
        assertEquals(0.346, final.getTranslationY(), 1e-3)
    }

    @Test fun sameDirection() {
        val start = moved(0.0, 1.5)
        val motion = Vector2(120.0 * step, 0.0)
        val (hit, result) = impact(moving, start, motion, 0.0, Geometry.createSquare(0.2),
            moved(0.5, 1.5), Vector2(30.0 * step, 0.0), 0.0)
        assertTrue(hit)
        assertEquals(0.200, result.getTime(), 1e-3)
        val final = start.lerped(motion, 0.0, result.getTime())
        assertEquals(0.400, final.getTranslationX(), 1e-3)
        assertEquals(1.500, final.getTranslationY(), 1e-3)
    }

    @Test fun oppositeDirection() {
        val start = moved(0.0, 1.5)
        val second = moved(2.0, 1.5)
        val firstMotion = Vector2(120.0 * step, 0.0)
        val secondMotion = Vector2(-30.0 * step, 0.0)
        val (hit, result) = impact(moving, start, firstMotion, 0.0, Geometry.createSquare(0.5),
            second, secondMotion, 0.0)
        assertTrue(hit)
        assertEquals(0.659, result.getTime(), 1e-3)
        val firstFinal = start.lerped(firstMotion, 0.0, result.getTime())
        val secondFinal = second.lerped(secondMotion, 0.0, result.getTime())
        assertEquals(1.319, firstFinal.getTranslationX(), 1e-3)
        assertEquals(1.500, firstFinal.getTranslationY(), 1e-3)
        assertEquals(1.670, secondFinal.getTranslationX(), 1e-3)
        assertEquals(1.500, secondFinal.getTranslationY(), 1e-3)
    }

    @Test fun orthogonalDirection() {
        val start = moved(0.0, 1.5)
        val second = moved(1.0, 1.25)
        val firstMotion = Vector2(120.0 * step, 0.0)
        val secondMotion = Vector2(0.0, 30.0 * step)
        val (hit, result) = impact(moving, start, firstMotion, 0.0, Geometry.createSquare(0.2),
            second, secondMotion, 0.0)
        assertTrue(hit)
        assertEquals(0.400, result.getTime(), 1e-3)
        val firstFinal = start.lerped(firstMotion, 0.0, result.getTime())
        val secondFinal = second.lerped(secondMotion, 0.0, result.getTime())
        assertEquals(0.800, firstFinal.getTranslationX(), 1e-3)
        assertEquals(1.500, firstFinal.getTranslationY(), 1e-3)
        assertEquals(1.000, secondFinal.getTranslationX(), 1e-3)
        assertEquals(1.450, secondFinal.getTranslationY(), 1e-3)
    }

    @Test fun sameDirectionNoCollision() {
        val (hit, _) = impact(moving, moved(0.0, 1.0), Vector2(120.0 * step, 0.0), 0.0,
            Geometry.createSquare(0.5), moved(0.0, 1.5), Vector2(30.0 * step, 0.0), 0.0)
        assertFalse(hit)
    }

    @Test fun sameDirectionNoCollision2() {
        val (hit, _) = impact(moving, moved(0.0, 1.0), Vector2(120.0 * step, 0.0), 0.0,
            Geometry.createSquare(0.5), moved(1.6, 1.5), Vector2(60.0 * step, 0.0), 0.0)
        assertFalse(hit)
    }

    @Test fun orthogonalDirectionNoCollision() {
        val (hit, _) = impact(moving, moved(0.0, 1.0), Vector2(120.0 * step, 0.0), 0.0,
            Geometry.createSquare(0.1), moved(1.0, 1.3), Vector2(0.0, 60.0 * step), 0.0)
        assertFalse(hit)
    }

    @Test fun setDistanceDetector() {
        val injected = Gjk()
        detector.setDistanceDetector(injected)
        assertSame(injected, detector.getDistanceDetector())
    }

    @Test fun setNullDistanceDetector() {
        assertFailsWith<NullPointerException> { detector.setDistanceDetector(null) }
    }

    @Test fun createWithNullDistanceDetector() {
        assertFailsWith<NullPointerException> { ConservativeAdvancement(null) }
    }

    @Test fun createSuccess() {
        val injected = Gjk()
        val result = ConservativeAdvancement(injected)
        assertSame(injected, result.getDistanceDetector())
        assertEquals(ConservativeAdvancement.DEFAULT_DISTANCE_EPSILON, result.getDistanceEpsilon())
        assertEquals(ConservativeAdvancement.DEFAULT_MAX_ITERATIONS, result.getMaxIterations())
    }

    @Test fun setTolerance() {
        detector.setDistanceEpsilon(0.3)
        assertEquals(0.3, detector.getDistanceEpsilon())
        detector.setDistanceEpsilon(0.000002)
        assertEquals(0.000002, detector.getDistanceEpsilon())
    }

    @Test fun setZeroTolerance() {
        assertFailsWith<IllegalArgumentException> { detector.setDistanceEpsilon(0.0) }
    }

    @Test fun setNegativeTolerance() {
        assertFailsWith<IllegalArgumentException> { detector.setDistanceEpsilon(-0.00003) }
    }

    @Test fun setMaxIterations() {
        detector.setMaxIterations(23)
        assertEquals(23, detector.getMaxIterations())
        detector.setMaxIterations(10)
        assertEquals(10, detector.getMaxIterations())
    }

    @Test fun setZeroMaxIterations() {
        assertFailsWith<IllegalArgumentException> { detector.setMaxIterations(0) }
    }

    @Test fun setNegativeMaxIterations() {
        assertFailsWith<IllegalArgumentException> { detector.setMaxIterations(-2) }
    }

    @Test fun setLessThanTenMaxIterations() {
        assertFailsWith<IllegalArgumentException> { detector.setMaxIterations(4) }
    }

    private fun spinningFirst() = moved(0.5, 0.0).also {
        it.rotate(-40.0 * PI / 180.0, it.getTranslationX(), it.getTranslationY())
    }

    @Test fun fastRotationAgainstStatic() {
        val first = spinningFirst()
        val rotation = 80.0 * PI / 180.0
        val (hit, result) = impact(Geometry.createRectangle(2.0, 0.2), first, Vector2(), rotation,
            Geometry.createRectangle(10.0, 0.5), moved(-5.0, 0.0), Vector2(), 0.0)
        assertTrue(hit)
        assertEquals(0.039, result.getTime(), 1e-3)
        assertEquals(-0.643, first.lerped(Vector2(), rotation, result.getTime()).getRotationAngle(), 1e-3)
    }

    @Test fun fastRotationAgainstFastRotation() {
        val first = spinningFirst()
        val second = moved(-5.0, 0.0).also {
            it.rotate(-20.0 * PI / 180.0, it.getTranslationX(), it.getTranslationY())
        }
        val firstRotation = 80.0 * PI / 180.0
        val secondRotation = 60.0 * PI / 180.0
        val (hit, result) = impact(Geometry.createRectangle(2.0, 0.2), first, Vector2(), firstRotation,
            Geometry.createRectangle(10.0, 0.5), second, Vector2(), secondRotation)
        assertTrue(hit)
        assertEquals(0.293, result.getTime(), 1e-3)
        assertEquals(-0.288, first.lerped(Vector2(), firstRotation, result.getTime()).getRotationAngle(), 1e-3)
        assertEquals(-0.041, second.lerped(Vector2(), secondRotation, result.getTime()).getRotationAngle(), 1e-3)
    }

    @Test fun fastRotationAgainstFastRotationNoCollision() {
        val first = spinningFirst()
        val second = moved(-5.0, 0.0).also {
            it.rotate(-80.0 * PI / 180.0, it.getTranslationX(), it.getTranslationY())
        }
        val (hit, _) = impact(Geometry.createRectangle(2.0, 0.2), first, Vector2(), 80.0 * PI / 180.0,
            Geometry.createRectangle(10.0, 0.5), second, Vector2(), 60.0 * PI / 180.0)
        assertFalse(hit)
    }

    @Test fun equidistantSameVelocityTest() {
        val (hit, _) = impact(Geometry.createSquare(1.0), Transform(), Vector2(1.0, 0.0), 0.0,
            Geometry.createSquare(1.0), moved(3.0, 0.0), Vector2(1.0, 0.0), 0.0)
        assertFalse(hit)
    }

    @Test fun separationTooSmall() {
        val (hit, _) = impact(Geometry.createSquare(1.0), Transform(), Vector2(1.0, 0.0), 0.0,
            Geometry.createSquare(1.0), moved(1.000001, 0.0), Vector2(1.0, 0.0), 0.0)
        assertFalse(hit)
    }
}
