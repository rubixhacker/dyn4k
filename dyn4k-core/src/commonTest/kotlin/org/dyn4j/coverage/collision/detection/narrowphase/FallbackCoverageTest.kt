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
import org.dyn4j.collision.narrowphase.*
import org.dyn4j.geometry.*

val FallbackCoverageTest by testSuite {
    test("fallbackCreateSuccess") { FallbackCoverageTestFixture().run { fallbackCreateSuccess() } }
    test("fallbackCreateNullPrimary") { FallbackCoverageTestFixture().run { fallbackCreateNullPrimary() } }
    test("fallbackCreateNullSecondary") { FallbackCoverageTestFixture().run { fallbackCreateNullSecondary() } }
    test("fallbackNoConditions") { FallbackCoverageTestFixture().run { fallbackNoConditions() } }
    test("fallbackAddRemoveCondition") { FallbackCoverageTestFixture().run { fallbackAddRemoveCondition() } }
    test("fallbackSingleTypedCondition") { FallbackCoverageTestFixture().run { fallbackSingleTypedCondition() } }
    test("fallbackSingleTypedConditionStrict") { FallbackCoverageTestFixture().run { fallbackSingleTypedConditionStrict() } }
    test("fallbackSingleTypedConditionOrder") { FallbackCoverageTestFixture().run { fallbackSingleTypedConditionOrder() } }
    test("fallbackPairwiseTypedCondition") { FallbackCoverageTestFixture().run { fallbackPairwiseTypedCondition() } }
    test("fallbackPairwiseTypedConditionStrict") { FallbackCoverageTestFixture().run { fallbackPairwiseTypedConditionStrict() } }
    test("fallbackPairwiseTypedConditionStrictOne") { FallbackCoverageTestFixture().run { fallbackPairwiseTypedConditionStrictOne() } }
    test("fallbackDetect") { FallbackCoverageTestFixture().run { fallbackDetect() } }
    test("singleTypedCreate") { FallbackCoverageTestFixture().run { singleTypedCreate() } }
    test("singleTypedIsMatch") { FallbackCoverageTestFixture().run { singleTypedIsMatch() } }
    test("pairwiseTypedCreate") { FallbackCoverageTestFixture().run { pairwiseTypedCreate() } }
    test("pairwiseTypedIsMatch") { FallbackCoverageTestFixture().run { pairwiseTypedIsMatch() } }
}

private class FallbackCoverageTestFixture  {
    private val shapes: List<Convex> = listOf(
        Geometry.createCapsule(1.0, 0.5), Geometry.createCircle(0.5), Geometry.createEllipse(1.0, 0.5),
        Geometry.createHalfEllipse(1.0, 0.25), Geometry.createHorizontalSegment(1.0),
        Geometry.createRectangle(1.0, 2.0), Geometry.createSlice(0.5, 50.0 * PI / 180.0),
        Geometry.createUnitCirclePolygon(5, 0.5), Geometry.createEquilateralTriangle(1.0)
    )
    private fun detector() = FallbackNarrowphaseDetector(Sat(), Gjk())
    private fun matrix(condition: FallbackCondition, expected: (Int, Int) -> Boolean) {
        val detector = detector(); detector.addCondition(condition)
        for (i in shapes.indices) for (j in i until shapes.size) {
            assertEquals(expected(i, j), detector.isFallbackRequired(shapes[i], shapes[j]), "pair $i,$j")
        }
    }

fun fallbackCreateSuccess() {
        val primary = Sat(); val secondary = Gjk(); val conditions = mutableListOf<FallbackCondition?>()
        val detector = FallbackNarrowphaseDetector(primary, secondary, conditions)
        assertSame(primary, detector.getPrimaryNarrowphaseDetector())
        assertSame(secondary, detector.getFallbackNarrowphaseDetector())
        detector.addCondition(SingleTypedFallbackCondition(convexClassOf(Capsule::class)))
        assertEquals(1, conditions.size)
    }
fun fallbackCreateNullPrimary() { assertFailsWith<NullPointerException> { FallbackNarrowphaseDetector(null, Gjk()) } }
fun fallbackCreateNullSecondary() { assertFailsWith<NullPointerException> { FallbackNarrowphaseDetector(Sat(), null) } }
fun fallbackNoConditions() {
        val detector = detector()
        for (i in shapes.indices) for (j in i until shapes.size) assertFalse(detector.isFallbackRequired(shapes[i], shapes[j]))
        assertEquals(0, detector.getConditionCount())
    }
fun fallbackAddRemoveCondition() {
        val detector = detector(); val condition = SingleTypedFallbackCondition(convexClassOf(Capsule::class))
        detector.addCondition(condition)
        assertTrue(detector.containsCondition(condition)); assertEquals(1, detector.getConditionCount())
        assertSame(condition, detector.getCondition(0))
        assertNotEquals(condition, SingleTypedFallbackCondition(convexClassOf(Capsule::class)))
        assertNotEquals(condition, SingleTypedFallbackCondition(convexClassOf(Capsule::class), false))
        assertNotEquals(condition, SingleTypedFallbackCondition(convexClassOf(Capsule::class), 1))
        assertTrue(detector.removeCondition(condition)); assertEquals(0, detector.getConditionCount())
        assertFalse(detector.containsCondition(condition))
    }
fun fallbackSingleTypedCondition() = matrix(SingleTypedFallbackCondition(convexClassOf(Ellipse::class))) { i, j -> i == 2 || j == 2 }
fun fallbackSingleTypedConditionStrict() = matrix(SingleTypedFallbackCondition(convexClassOf(Polygon::class), true)) { i, j -> i == 7 || j == 7 }
fun fallbackSingleTypedConditionOrder() {
        val detector = detector()
        val polygon = SingleTypedFallbackCondition(convexClassOf(Polygon::class), 1, true)
        val rectangle = SingleTypedFallbackCondition(convexClassOf(Rectangle::class), 0, true)
        detector.addCondition(polygon); detector.addCondition(rectangle)
        assertSame(rectangle, detector.getCondition(0)); assertSame(polygon, detector.getCondition(1))
        for (i in shapes.indices) for (j in i until shapes.size)
            assertEquals(i == 5 || i == 7 || j == 5 || j == 7, detector.isFallbackRequired(shapes[i], shapes[j]))
    }
fun fallbackPairwiseTypedCondition() = matrix(PairwiseTypedFallbackCondition(convexClassOf(Ellipse::class), convexClassOf(Ellipse::class))) { i, j -> i == 2 && j == 2 }
fun fallbackPairwiseTypedConditionStrict() = matrix(PairwiseTypedFallbackCondition(convexClassOf(Polygon::class), convexClassOf(Ellipse::class), true)) { i, j -> (i == 7 && j == 2) || (i == 2 && j == 7) }
fun fallbackPairwiseTypedConditionStrictOne() = matrix(PairwiseTypedFallbackCondition(convexClassOf(Polygon::class), true, convexClassOf(Polygon::class), false)) { i, j -> (i == 7 && j in 5..8 && j != 6) || (j == 7 && i in 5..8 && i != 6) }
fun fallbackDetect() {
        val detector = detector()
        detector.addCondition(SingleTypedFallbackCondition(convexClassOf(Ellipse::class)))
        detector.addCondition(SingleTypedFallbackCondition(convexClassOf(HalfEllipse::class)))
        val ellipse = Geometry.createEllipse(1.0, 0.4); val half = Geometry.createHalfEllipse(1.0, 0.5)
        val rectangle = Geometry.createSquare(1.0); val triangle = Geometry.createEquilateralTriangle(0.5)
        val transform = Transform(); val penetration = Penetration()
        for (shape in listOf(ellipse, half, triangle)) for ((first, second) in listOf(shape to rectangle, rectangle to shape)) {
            assertTrue(detector.detect(first, transform, second, transform))
            assertTrue(detector.detect(first, transform, second, transform, penetration))
            assertTrue(penetration.getDepth() > 0.0)
        }
    }

fun singleTypedCreate() {
        val type = convexClassOf(Ellipse::class)
        val variants = listOf(SingleTypedFallbackCondition(type), SingleTypedFallbackCondition(type, 1), SingleTypedFallbackCondition(type, false), SingleTypedFallbackCondition(type, 1, false))
        variants.forEachIndexed { index, condition ->
            assertEquals(type, condition.getType()); assertEquals(index == 0 || index == 1, condition.isStrict())
            assertEquals(if (index % 2 == 0) 0 else 1, condition.getSortIndex()); assertNotNull(condition.toString())
        }
    }
fun singleTypedIsMatch() {
        val polygon = convexClassOf(Polygon::class); val rectangle = convexClassOf(Rectangle::class); val circle = convexClassOf(Circle::class)
        for (strict in listOf(true, false)) {
            val condition = SingleTypedFallbackCondition(polygon, strict)
            for ((left, right) in listOf(polygon to polygon, rectangle to polygon, polygon to rectangle, polygon to circle, circle to polygon)) assertTrue(condition.isMatch(left, right))
            assertEquals(!strict, condition.isMatch(rectangle, rectangle))
            assertEquals(!strict, condition.isMatch(circle, rectangle))
            assertEquals(!strict, condition.isMatch(rectangle, circle))
            assertFalse(condition.isMatch(circle, circle))
        }
    }
fun pairwiseTypedCreate() {
        val ellipse = convexClassOf(Ellipse::class); val circle = convexClassOf(Circle::class)
        val variants = listOf(
            PairwiseTypedFallbackCondition(ellipse, circle), PairwiseTypedFallbackCondition(ellipse, circle, 1),
            PairwiseTypedFallbackCondition(ellipse, circle, false), PairwiseTypedFallbackCondition(ellipse, circle, false, 1),
            PairwiseTypedFallbackCondition(ellipse, false, circle, true), PairwiseTypedFallbackCondition(ellipse, false, circle, true, 1)
        )
        variants.forEachIndexed { index, condition ->
            assertEquals(ellipse, condition.getType1()); assertEquals(circle, condition.getType2())
            assertEquals(index < 2, condition.isStrict1()); assertEquals(index < 2 || index > 3, condition.isStrict2())
            assertEquals(index % 2, condition.getSortIndex()); assertNotNull(condition.toString())
        }
    }
fun pairwiseTypedIsMatch() {
        val p = convexClassOf(Polygon::class); val r = convexClassOf(Rectangle::class); val c = convexClassOf(Circle::class)
        val strict = PairwiseTypedFallbackCondition(p, p)
        val loose = PairwiseTypedFallbackCondition(p, false, p, false)
        val firstLoose = PairwiseTypedFallbackCondition(p, false, p, true)
        val secondLoose = PairwiseTypedFallbackCondition(p, true, p, false)
        for (condition in listOf(strict, loose, firstLoose, secondLoose)) assertTrue(condition.isMatch(p, p))
        assertFalse(strict.isMatch(r, r)); assertFalse(strict.isMatch(r, p)); assertFalse(strict.isMatch(p, r))
        assertTrue(loose.isMatch(r, r)); assertTrue(loose.isMatch(r, p)); assertTrue(loose.isMatch(p, r))
        for (condition in listOf(firstLoose, secondLoose)) {
            assertFalse(condition.isMatch(r, r)); assertTrue(condition.isMatch(r, p)); assertTrue(condition.isMatch(p, r))
        }
        for (condition in listOf(strict, loose, firstLoose, secondLoose)) {
            assertFalse(condition.isMatch(p, c)); assertFalse(condition.isMatch(c, p))
        }
    }
}
