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
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import org.dyn4j.collision.narrowphase.Gjk
import org.dyn4j.collision.narrowphase.LinkPostProcessor
import org.dyn4j.collision.narrowphase.Penetration
import org.dyn4j.geometry.Geometry
import org.dyn4j.geometry.Link
import org.dyn4j.geometry.Transform
import org.dyn4j.geometry.Vector2

val LinkPostProcessorCoverageTest by testSuite {
    test("create") { LinkPostProcessorCoverageTestFixture().run { create() } }
    test("typeDetectionIgnore") { LinkPostProcessorCoverageTestFixture().run { typeDetectionIgnore() } }
    test("failureWidthTwoWayLinksInVersionsPriorTo_4_2_0") { LinkPostProcessorCoverageTestFixture().run { failureWidthTwoWayLinksInVersionsPriorTo_4_2_0() } }
    test("caseMiddleConvexConvex") { LinkPostProcessorCoverageTestFixture().run { caseMiddleConvexConvex() } }
    test("caseMiddleConcaveConcave") { LinkPostProcessorCoverageTestFixture().run { caseMiddleConcaveConcave() } }
    test("caseMiddleConvexConcave") { LinkPostProcessorCoverageTestFixture().run { caseMiddleConvexConcave() } }
    test("caseMiddleConcaveConvex") { LinkPostProcessorCoverageTestFixture().run { caseMiddleConcaveConvex() } }
    test("caseRightConcave") { LinkPostProcessorCoverageTestFixture().run { caseRightConcave() } }
    test("caseLeftConcave") { LinkPostProcessorCoverageTestFixture().run { caseLeftConcave() } }
    test("caseRightConvex") { LinkPostProcessorCoverageTestFixture().run { caseRightConvex() } }
    test("caseLeftConvex") { LinkPostProcessorCoverageTestFixture().run { caseLeftConvex() } }
    test("noPreviousOrNext") { LinkPostProcessorCoverageTestFixture().run { noPreviousOrNext() } }
}

private class LinkPostProcessorCoverageTestFixture  {
    private data class State(
        val x: Double, val y: Double,
        val rawDepth: Double, val rawX: Double, val rawY: Double,
        val processedDepth: Double, val processedX: Double, val processedY: Double
    )
    private fun state(x: Double, y: Double, rawDepth: Double, rawX: Double, rawY: Double, processedDepth: Double, processedX: Double, processedY: Double) =
        State(x, y, rawDepth, rawX, rawY, processedDepth, processedX, processedY)
    private fun assertPenetration(penetration: Penetration, depth: Double, x: Double, y: Double) {
        assertEquals(depth, penetration.getDepth(), 1e-3)
        assertEquals(x, penetration.getNormal().x, 1e-3)
        assertEquals(y, penetration.getNormal().y, 1e-3)
    }
    private fun links(rightHeight: Double, leftHeight: Double) = Geometry.createLinks(
        listOf(Vector2(1.0, rightHeight), Vector2(0.5, 0.0), Vector2(-0.5, 0.0), Vector2(-1.0, leftHeight)), false
    )
    private fun check(link: Link, states: List<State>, rotateLast: Boolean = false) {
        val square = Geometry.createSquare(0.5)
        val linkTransform = Transform(); val squareTransform = Transform()
        val gjk = Gjk(); val processor = LinkPostProcessor(); val penetration = Penetration()
        states.forEachIndexed { index, expected ->
            squareTransform.identity()
            if (rotateLast && index == states.lastIndex) squareTransform.rotate(45.0 * PI / 180.0)
            squareTransform.translate(expected.x, expected.y)
            penetration.clear()
            assertTrue(gjk.detect(link, linkTransform, square, squareTransform, penetration))
            assertPenetration(penetration, expected.rawDepth, expected.rawX, expected.rawY)
            processor.process(link, linkTransform, square, squareTransform, penetration)
            assertPenetration(penetration, expected.processedDepth, expected.processedX, expected.processedY)
            penetration.clear()
            assertTrue(gjk.detect(square, squareTransform, link, linkTransform, penetration))
            processor.process(square, squareTransform, link, linkTransform, penetration)
            assertPenetration(penetration, expected.processedDepth, -expected.processedX, -expected.processedY)
        }
    }
fun create() { LinkPostProcessor() }
fun typeDetectionIgnore() {
        val circle1 = Geometry.createCircle(1.0); val circle2 = Geometry.createCircle(1.0)
        val penetration = Penetration(); penetration.setDepth(2.0); penetration.setNormal(Vector2(-1.0, 2.0))
        LinkPostProcessor().process(circle1, Transform(), circle2, Transform(), penetration)
        assertPenetration(penetration, 2.0, -1.0, 2.0)
    }
fun failureWidthTwoWayLinksInVersionsPriorTo_4_2_0() {
        val link = Geometry.createLinks(listOf(Vector2(5.0, 0.0), Vector2(4.0, 0.0), Vector2(0.0, 0.0), Vector2(0.0, 0.5)), false)[1]
        val rectangle = Geometry.createRectangle(0.1, 2.0)
        val linkTransform = Transform(); val rectangleTransform = Transform()
        rectangleTransform.rotate(30.0 * PI / 180.0); rectangleTransform.translate(-0.1, 0.85)
        val gjk = Gjk(); val processor = LinkPostProcessor(); val penetration = Penetration()
        assertTrue(gjk.detect(link, linkTransform, rectangle, rectangleTransform, penetration))
        processor.process(link, linkTransform, rectangle, rectangleTransform, penetration)
        assertPenetration(penetration, 0.041, 0.000, 1.000)
        penetration.clear()
        assertTrue(gjk.detect(rectangle, rectangleTransform, link, linkTransform, penetration))
        processor.process(rectangle, rectangleTransform, link, linkTransform, penetration)
        assertPenetration(penetration, 0.041, 0.000, -1.000)
    }
fun caseMiddleConvexConvex() = check(links(-0.5, -0.5)[1], listOf(
        state(0.749, 0.0, 0.001, 1.0, 0.0, 0.0, 0.0, 0.0),
        state(-0.749, 0.0, 0.001, -1.0, 0.0, 0.0, 0.0, 0.0),
        state(0.73, -0.24, 0.010, 0.0, -1.0, 0.0, 0.0, 0.0)
    ))
fun caseMiddleConcaveConcave() = check(links(0.5, 0.5)[1], listOf(
        state(-0.749, 0.0, 0.001, -1.0, 0.0, 0.001, 0.0, 1.0),
        state(0.749, 0.0, 0.001, 1.0, 0.0, 0.001, 0.0, 1.0),
        state(0.73, -0.24, 0.010, 0.0, -1.0, 0.0, 0.0, 0.0),
        state(-0.60, -0.20, 0.037, -0.707, -0.707, 0.0, 0.0, 0.0)
    ), rotateLast = true)
fun caseMiddleConvexConcave() = check(links(-0.5, 0.5)[1], listOf(
        state(-0.749, 0.0, 0.001, -1.0, 0.0, 0.001, 0.0, 1.0),
        state(0.749, 0.0, 0.001, 1.0, 0.0, 0.0, 0.0, 0.0),
        state(0.73, -0.24, 0.010, 0.0, -1.0, 0.0, 0.0, 0.0)
    ))
fun caseMiddleConcaveConvex() = check(links(0.5, -0.5)[1], listOf(
        state(-0.749, 0.0, 0.001, -1.0, 0.0, 0.0, 0.0, 0.0),
        state(0.749, 0.0, 0.001, 1.0, 0.0, 0.001, 0.0, 1.0),
        state(-0.73, -0.24, 0.010, 0.0, -1.0, 0.0, 0.0, 0.0)
    ))
fun caseRightConcave() = check(links(0.5, 0.5)[0], listOf(
        state(0.26, 0.0, 0.010, -1.0, 0.0, 0.010, -0.707, 0.707),
        state(1.24, 0.5, 0.010, 1.0, 0.0, 0.010, 1.0, 0.0)
    ))
fun caseLeftConcave() = check(links(0.5, 0.5)[2], listOf(
        state(-0.26, 0.0, 0.010, 1.0, 0.0, 0.010, 0.707, 0.707),
        state(-1.24, 0.5, 0.010, -1.0, 0.0, 0.010, -1.0, 0.0)
    ))
fun caseRightConvex() = check(links(-0.5, -0.5)[0], listOf(
        state(0.749, 0.0, 0.177, 0.707, 0.707, 0.177, 0.707, 0.707),
        state(1.23, -0.74, 0.010, 0.0, -1.0, 0.010, 0.0, -1.0),
        state(0.73, 0.24, 0.010, 0.0, 1.0, 0.010, 0.0, 1.0)
    ))
fun caseLeftConvex() = check(links(-0.5, -0.5)[2], listOf(
        state(-0.749, 0.0, 0.177, -0.707, 0.707, 0.177, -0.707, 0.707),
        state(-1.23, -0.74, 0.010, 0.0, -1.0, 0.010, 0.0, -1.0),
        state(-0.73, 0.24, 0.010, 0.0, 1.0, 0.010, 0.0, 1.0)
    ))
fun noPreviousOrNext() {
        val link = Geometry.createLinks(listOf(Vector2(0.5, 0.0), Vector2(-0.5, 0.0)), false)[0]
        val square = Geometry.createSquare(0.5); val transform = Transform(); transform.translate(-0.749, 0.0)
        val penetration = Penetration(); assertTrue(Gjk().detect(link, Transform(), square, transform, penetration))
        assertPenetration(penetration, 0.001, -1.0, 0.0)
        LinkPostProcessor().process(link, Transform(), square, transform, penetration)
        assertPenetration(penetration, 0.001, -1.0, 0.0)
    }
}
