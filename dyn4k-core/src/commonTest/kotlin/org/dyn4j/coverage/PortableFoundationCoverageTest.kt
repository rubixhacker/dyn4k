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
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertNotSame
import kotlin.test.assertSame
import kotlin.test.assertTrue
import org.dyn4j.AVLTree
import org.dyn4j.Reference
import org.dyn4j.Version
import org.dyn4j.geometry.AABB
import org.dyn4j.geometry.Circle
import org.dyn4j.geometry.Geometry
import org.dyn4j.geometry.Interval
import org.dyn4j.geometry.Matrix22
import org.dyn4j.geometry.Matrix33
import org.dyn4j.geometry.Polygon
import org.dyn4j.geometry.Ray
import org.dyn4j.geometry.Rectangle
import org.dyn4j.geometry.Rotation
import org.dyn4j.geometry.Segment
import org.dyn4j.geometry.Transform
import org.dyn4j.geometry.Vector2
import org.dyn4j.geometry.Vector3

val PortableFoundationCoverageTest by testSuite {
    test("referenceEqualityAndMutableValue") { PortableFoundationCoverageTestFixture().run { referenceEqualityAndMutableValue() } }
    test("versionNumbersAreAnIndependentValue") { PortableFoundationCoverageTestFixture().run { versionNumbersAreAnIndependentValue() } }
    test("vectorConstructionAndCopyKeepIndependentCoordinates") { PortableFoundationCoverageTestFixture().run { vectorConstructionAndCopyKeepIndependentCoordinates() } }
    test("vectorDistanceUsesBothCoordinates") { PortableFoundationCoverageTestFixture().run { vectorDistanceUsesBothCoordinates() } }
    test("boxUnionReturnsCopyAndMutationChangesReceiver") { PortableFoundationCoverageTestFixture().run { boxUnionReturnsCopyAndMutationChangesReceiver() } }
    test("treeRejectsDuplicateButRetainsSortedValues") { PortableFoundationCoverageTestFixture().run { treeRejectsDuplicateButRetainsSortedValues() } }
    test("treeAcceptsOriginalShuffledValuesAndRemainsBalanced") { PortableFoundationCoverageTestFixture().run { treeAcceptsOriginalShuffledValuesAndRemainsBalanced() } }
    test("treeRangeIteratorsIncludeBoundariesAndRejectRemoval") { PortableFoundationCoverageTestFixture().run { treeRangeIteratorsIncludeBoundariesAndRejectRemoval() } }
    test("treeRemovalChangesMembershipAndExtremeValues") { PortableFoundationCoverageTestFixture().run { treeRemovalChangesMembershipAndExtremeValues() } }
    test("vectorMutationAndProductHaveDifferentIdentity") { PortableFoundationCoverageTestFixture().run { vectorMutationAndProductHaveDifferentIdentity() } }
    test("matrixSolveAndCopyUseIndependentValues") { PortableFoundationCoverageTestFixture().run { matrixSolveAndCopyUseIndependentValues() } }
    test("protectedRotationStateAndOverrideRemainObservable") { PortableFoundationCoverageTestFixture().run { protectedRotationStateAndOverrideRemainObservable() } }
    test("transformTranslationAndInverseRecoverOriginalPoint") { PortableFoundationCoverageTestFixture().run { transformTranslationAndInverseRecoverOriginalPoint() } }
    test("boxRejectsReversedCoordinatesAndNegativeRadius") { PortableFoundationCoverageTestFixture().run { boxRejectsReversedCoordinatesAndNegativeRadius() } }
    test("circleBoundaryAndAreaUseOriginalRadius") { PortableFoundationCoverageTestFixture().run { circleBoundaryAndAreaUseOriginalRadius() } }
    test("polygonRejectsWrongWindingAndCoincidentVertices") { PortableFoundationCoverageTestFixture().run { polygonRejectsWrongWindingAndCoincidentVertices() } }
    test("polygonVertexViewIsLiveAndCopyIsIndependent") { PortableFoundationCoverageTestFixture().run { polygonVertexViewIsLiveAndCopyIsIndependent() } }
    test("vector3DistanceAndCopyIncludeThirdCoordinate") { PortableFoundationCoverageTestFixture().run { vector3DistanceAndCopyIncludeThirdCoordinate() } }
    test("matrix33SolveUsesAllThreeCoordinates") { PortableFoundationCoverageTestFixture().run { matrix33SolveUsesAllThreeCoordinates() } }
    test("intervalBoundaryModesAndUnionAreObservable") { PortableFoundationCoverageTestFixture().run { intervalBoundaryModesAndUnionAreObservable() } }
    test("rayExposesLiveStartAndCopyOwnsItsStart") { PortableFoundationCoverageTestFixture().run { rayExposesLiveStartAndCopyOwnsItsStart() } }
    test("rectangleAreaAndTranslationKeepDimensions") { PortableFoundationCoverageTestFixture().run { rectangleAreaAndTranslationKeepDimensions() } }
    test("segmentsIntersectAtKnownPoint") { PortableFoundationCoverageTestFixture().run { segmentsIntersectAtKnownPoint() } }
    test("windingChangesSignWhenVertexOrderReverses") { PortableFoundationCoverageTestFixture().run { windingChangesSignWhenVertexOrderReverses() } }
}

private class PortableFoundationCoverageTestFixture  {
fun referenceEqualityAndMutableValue() {
        val reference = Reference(5)
        assertEquals(Reference(5), reference)
        assertEquals(reference.hashCode(), Reference(5).hashCode())
        reference.value = null
        assertEquals("null", reference.toString())
        assertEquals(Reference<Int>(), reference)
        assertFalse(reference == Reference(5))
    }

fun versionNumbersAreAnIndependentValue() {
        val numbers = Version.getVersionNumbers()
        assertEquals(listOf(6, 0, 0), numbers.toList())
        numbers[0] = 99
        assertEquals(6, Version.getMajorNumber())
        assertEquals("6.0.0", Version.getVersion())
    }

fun vectorConstructionAndCopyKeepIndependentCoordinates() {
        val vector = Vector2(0.0, 1.0, 2.0, 3.0)
        assertEquals(2.0, vector.x)
        assertEquals(2.0, vector.y)
        val copy = vector.copy()
        assertNotSame(vector, copy)
        copy.x = 7.0
        assertEquals(2.0, vector.x)
        assertEquals(7.0, copy.x)
    }

fun vectorDistanceUsesBothCoordinates() {
        val vector = Vector2(1.0, 2.0)
        assertEquals(2.236, vector.distance(2.0, 0.0), 1.0e-3)
        assertEquals(0.0, vector.distance(1.0, 2.0), 1.0e-3)
    }

fun boxUnionReturnsCopyAndMutationChangesReceiver() {
        val box = AABB(-2.0, 0.0, 2.0, 1.0)
        val other = AABB(-1.0, -2.0, 5.0, 0.5)
        val union = box.getUnion(other)
        assertNotSame(box, union)
        assertEquals(-2.0, union.getMinY())
        assertEquals(5.0, union.getMaxX())
        assertEquals(0.0, box.getMinY())
        assertSame(box, box.union(other))
        assertEquals(-2.0, box.getMinY())
    }

fun treeRejectsDuplicateButRetainsSortedValues() {
        val tree = AVLTree<Int>()
        listOf(4, 2, 6, 1, 3, 5, 7).forEach { assertTrue(tree.insert(it)) }
        assertFailsWith<IllegalArgumentException> { tree.insert(3) }
        assertEquals(7, tree.size())
        assertEquals(listOf(1, 2, 3, 4, 5, 6, 7), tree.toList())
        assertTrue(tree.isValid())
    }

fun treeAcceptsOriginalShuffledValuesAndRemainsBalanced() {
        val values = listOf(10, 3, -3, 4, 0, 1, 11, 19, 6, -1, 2, 9, -4, -8, 14, -5, 7, 31, 20, 8, -15, -11, -6, 16, -40)
        val tree = AVLTree<Int>()
        values.forEachIndexed { index, value ->
            assertTrue(tree.insert(value))
            assertEquals(index + 1, tree.size())
            assertTrue(tree.isBalanced())
            assertTrue(tree.isValid())
            assertTrue(tree.contains(value))
        }
        assertEquals(values.sorted(), tree.toList())
    }

fun treeRangeIteratorsIncludeBoundariesAndRejectRemoval() {
        val tree = AVLTree<Int>()
        listOf(4, 2, 6, 1, 3, 5, 7).forEach { tree.insert(it) }
        val range = tree.subsetIterator(3, 5)
        assertEquals(listOf(3, 4, 5), range.asSequence().toList())
        assertEquals(listOf(1, 2, 3), tree.headIterator(3).asSequence().toList())
        assertEquals(listOf(5, 6, 7), tree.tailIterator(5).asSequence().toList())
        assertFailsWith<UnsupportedOperationException> { range.remove() }
    }

fun treeRemovalChangesMembershipAndExtremeValues() {
        val tree = AVLTree<Int>()
        (1..40).forEach { tree.insert(it) }
        (2..40 step 2).forEach { assertTrue(tree.remove(it)); assertTrue(tree.isValid()) }
        assertFalse(tree.contains(20))
        assertEquals(1, tree.removeMinimum())
        assertEquals(39, tree.removeMaximum())
        assertEquals((3..37 step 2).toList(), tree.toList())
    }

fun vectorMutationAndProductHaveDifferentIdentity() {
        val vector = Vector2(1.0, 3.0)
        val product = vector.product(2.0)
        assertNotSame(vector, product)
        assertEquals(Vector2(2.0, 6.0), product)
        assertSame(vector, vector.multiply(2.0))
        assertEquals(Vector2(2.0, 6.0), vector)
    }

fun matrixSolveAndCopyUseIndependentValues() {
        val matrix = Matrix22(2.0, 0.0, 0.0, 4.0)
        assertEquals(Vector2(3.0, 2.0), matrix.solve(Vector2(6.0, 8.0)))
        val copy = matrix.copy()
        assertNotSame(matrix, copy)
        copy.m00 = 5.0
        assertEquals(2.0, matrix.m00)
    }

fun protectedRotationStateAndOverrideRemainObservable() {
        val rotation = object : Rotation() {
            fun setComponents(c: Double, s: Double) { cost = c; sint = s }
            override fun getCost(): Double = super.getCost() + 1.0
        }
        rotation.setComponents(0.0, 1.0)
        val consumer: Rotation = rotation
        assertEquals(1.0, consumer.getCost())
        assertEquals(1.0, consumer.getSint())
        assertEquals(1.0, consumer.toVector().y)
    }

fun transformTranslationAndInverseRecoverOriginalPoint() {
        val transform = Transform()
        transform.translate(2.0, -3.0)
        val point = Vector2(1.0, 2.0)
        val transformed = transform.getTransformed(point)
        assertEquals(Vector2(3.0, -1.0), transformed)
        assertEquals(point, transform.getInverseTransformed(transformed))
        assertEquals(Vector2(1.0, 2.0), point)
    }

fun boxRejectsReversedCoordinatesAndNegativeRadius() {
        assertFailsWith<IllegalArgumentException> { AABB(0.0, 0.0, -1.0, 2.0) }
        assertFailsWith<IllegalArgumentException> { AABB(Vector2(-1.0, 1.0), -1.0) }
    }

fun circleBoundaryAndAreaUseOriginalRadius() {
        assertFailsWith<IllegalArgumentException> { Circle(0.0) }
        val circle = Circle(0.5)
        assertTrue(circle.contains(Vector2(0.5, 0.0)))
        assertFalse(circle.contains(Vector2(0.5, 0.0), Transform(), false))
        assertEquals(kotlin.math.PI * 0.25, circle.getArea(), 1.0e-12)
    }

fun polygonRejectsWrongWindingAndCoincidentVertices() {
        assertFailsWith<IllegalArgumentException> {
            Polygon(Vector2(), Vector2(2.0, 2.0), Vector2(1.0, 0.0))
        }
        assertFailsWith<IllegalArgumentException> {
            Polygon(Vector2(), Vector2(2.0, 0.0), Vector2(2.0, 0.0), Vector2(0.0, 2.0))
        }
    }

fun polygonVertexViewIsLiveAndCopyIsIndependent() {
        val polygon = Polygon(Vector2(), Vector2(2.0, 0.0), Vector2(0.0, 2.0))
        val vertices = polygon.getVertices()
        assertSame(vertices, polygon.getVertices())
        val copy = polygon.copy()
        vertices[0].x = -1.0
        assertEquals(-1.0, polygon.getVertices()[0].x)
        assertEquals(0.0, copy.getVertices()[0].x)
    }

fun vector3DistanceAndCopyIncludeThirdCoordinate() {
        val vector = Vector3(1.0, 2.0, 3.0)
        assertEquals(9.0, vector.distanceSquared(1.0, 2.0, 6.0))
        val copy = vector.copy()
        copy.z = 6.0
        assertEquals(3.0, vector.z)
        assertEquals(3.0, vector.distance(copy))
    }

fun matrix33SolveUsesAllThreeCoordinates() {
        val matrix = Matrix33(2.0, 0.0, 0.0, 0.0, 4.0, 0.0, 0.0, 0.0, 5.0)
        assertEquals(Vector3(3.0, 2.0, 1.0), matrix.solve33(Vector3(6.0, 8.0, 5.0)))
        assertEquals(40.0, matrix.determinant())
    }

fun intervalBoundaryModesAndUnionAreObservable() {
        val interval = Interval(-2.0, 2.0)
        assertTrue(interval.includesInclusive(-2.0))
        assertFalse(interval.includesExclusive(-2.0))
        assertEquals(1.0, interval.getOverlap(Interval(1.0, 4.0)))
        val union = interval.getUnion(Interval(1.0, 4.0))
        assertEquals(4.0, union.getMax())
        assertEquals(2.0, interval.getMax())
    }

fun rayExposesLiveStartAndCopyOwnsItsStart() {
        val ray = Ray(Vector2(1.0, 2.0), Vector2(1.0, 0.0))
        val copy = ray.copy()
        ray.getStart().x = 3.0
        assertEquals(3.0, ray.getStart().x)
        assertEquals(1.0, copy.getStart().x)
        assertEquals(0.0, ray.getDirection())
    }

fun rectangleAreaAndTranslationKeepDimensions() {
        val rectangle = Rectangle(2.0, 3.0)
        assertEquals(6.0, rectangle.getArea())
        rectangle.translate(4.0, -2.0)
        assertEquals(2.0, rectangle.getWidth())
        assertEquals(3.0, rectangle.getHeight())
        assertEquals(Vector2(4.0, -2.0), rectangle.getCenter())
    }

fun segmentsIntersectAtKnownPoint() {
        val horizontal = Segment(Vector2(-1.0, 0.0), Vector2(1.0, 0.0))
        val vertical = Segment(Vector2(0.0, -1.0), Vector2(0.0, 1.0))
        assertEquals(Vector2(0.0, 0.0), horizontal.getSegmentIntersection(vertical))
        assertEquals(0.0, horizontal.getArea())
    }

fun windingChangesSignWhenVertexOrderReverses() {
        val points = mutableListOf<Vector2?>(Vector2(0.0, 0.0), Vector2(2.0, 0.0), Vector2(0.0, 2.0))
        assertEquals(4.0, Geometry.getWinding(points))
        Geometry.reverseWinding(points)
        assertEquals(-4.0, Geometry.getWinding(points))
    }
}
