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
package org.dyn4j.collision.narrowphase

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertSame
import kotlin.test.assertTrue
import kotlin.test.assertFailsWith
import org.dyn4j.collision.narrowphase.*
import org.dyn4j.geometry.*

class NarrowphaseModelCoverageTest {
    private class Condition(index: Int) : AbstractFallbackCondition(index) {
        override fun isMatch(convex1: Convex, convex2: Convex) = false
    }
    private class TypedCondition : TypedFallbackCondition() {
        override fun isMatch(type1: ConvexClass<out Convex>, type2: ConvexClass<out Convex>) = false
    }
    private val a = Vector2(-1.0, -1.0)
    private val b = Vector2(2.0, -1.0)
    private val c = Vector2(0.0, 2.0)
    private fun vector(expectedX: Double, expectedY: Double, actual: Vector2, tolerance: Double = 1e-3) {
        assertEquals(expectedX, actual.x, tolerance)
        assertEquals(expectedY, actual.y, tolerance)
    }

    @Test fun abstractFallbackConditionCreate() {
        assertEquals(1, Condition(1).getSortIndex())
        assertEquals(0, TypedCondition().getSortIndex())
    }
    @Test fun abstractFallbackConditionGetSortIndex() {
        listOf(1, 2, 5, -1, 2).forEach { assertEquals(it, Condition(it).getSortIndex()) }
    }
    @Test fun abstractFallbackConditionCompareTo() {
        val conditions = listOf(Condition(1), Condition(2), Condition(5), Condition(-1), Condition(2))
        assertTrue(conditions[0] > conditions[3]); assertTrue(conditions[3] < conditions[0])
        assertEquals(0, conditions[1].compareTo(conditions[4]))
        assertEquals(0, conditions[4].compareTo(conditions[1]))
        assertTrue(conditions[0] < conditions[2]); assertTrue(conditions[2] > conditions[0])
    }

    @Test fun epaCreateGetSet() {
        val epa = Epa()
        assertEquals(Epa.DEFAULT_DISTANCE_EPSILON, epa.getDistanceEpsilon())
        assertEquals(Epa.DEFAULT_MAX_ITERATIONS, epa.getMaxIterations())
        epa.setDistanceEpsilon(0.1); epa.setMaxIterations(20)
        assertEquals(0.1, epa.getDistanceEpsilon()); assertEquals(20, epa.getMaxIterations())
    }
    @Test fun epaSetSmallMaxIterations() { assertFailsWith<IllegalArgumentException> { Epa().setMaxIterations(3) } }
    @Test fun epaSetZeroMaxIterations() { assertFailsWith<IllegalArgumentException> { Epa().setMaxIterations(0) } }
    @Test fun epaSetNegativeMaxIterations() { assertFailsWith<IllegalArgumentException> { Epa().setMaxIterations(-3) } }
    @Test fun epaSetZeroDistanceEpsilon() { assertFailsWith<IllegalArgumentException> { Epa().setDistanceEpsilon(0.0) } }
    @Test fun epaSetNegativeDistanceEpsilon() { assertFailsWith<IllegalArgumentException> { Epa().setDistanceEpsilon(-0.11) } }

    @Test fun expandingSimplexEdgeCreateSuccess() {
        val edges = listOf(
            ExpandingSimplexEdge(a, b, 1) to doubleArrayOf(1.0, 0.0, -1.0),
            ExpandingSimplexEdge(b, c, 1) to doubleArrayOf(1.109, 0.832, 0.554),
            ExpandingSimplexEdge(c, a, 1) to doubleArrayOf(0.632, -0.948, 0.316),
            ExpandingSimplexEdge(a, c, -1) to doubleArrayOf(0.632, -0.948, 0.316)
        )
        val endpoints = listOf(a to b, b to c, c to a, a to c)
        edges.forEachIndexed { i, (edge, expected) ->
            vector(endpoints[i].first.x, endpoints[i].first.y, edge.point1)
            vector(endpoints[i].second.x, endpoints[i].second.y, edge.point2)
            assertEquals(expected[0], edge.distance, 1e-3)
            vector(expected[1], expected[2], edge.normal)
            assertEquals(1.0, edge.normal.getMagnitude(), 1e-3)
        }
    }
    @Test fun expandingSimplexEdgeCompareTo() {
        val e1 = ExpandingSimplexEdge(a, b, 1); val e2 = ExpandingSimplexEdge(b, c, 1); val e3 = ExpandingSimplexEdge(c, a, 1)
        assertEquals(-1, e1.compareTo(e2)); assertEquals(1, e2.compareTo(e1))
        assertEquals(1, e1.compareTo(e3)); assertEquals(-1, e3.compareTo(e1)); assertEquals(0, e1.compareTo(e1))
    }
    @Test fun expandingSimplexEdgeTostring() { assertNotNull(ExpandingSimplexEdge(a, b, 1).toString()) }

    @Test fun expandingSimplexCreateSuccess() {
        val simplex = ExpandingSimplex(listOf(a, b, c))
        assertEquals(1, simplex.getWinding()); assertEquals(3, simplex.size())
        val edge = simplex.getClosestEdge()
        vector(0.0, 2.0, edge.point1); vector(-1.0, -1.0, edge.point2)
        vector(-0.948, 0.316, edge.normal); assertEquals(0.632, edge.distance, 1e-3)
        assertNotNull(simplex.toString())
    }
    @Test fun expandingSimplexGetWinding() {
        assertEquals(1, ExpandingSimplex(listOf(a, b, c)).getWinding())
        assertEquals(-1, ExpandingSimplex(listOf(c, b, a)).getWinding())
        assertEquals(-1, ExpandingSimplex(listOf(c, b)).getWinding())
        assertEquals(1, ExpandingSimplex(listOf(b, c)).getWinding())
        assertEquals(0, ExpandingSimplex(listOf(b)).getWinding())
        assertEquals(0, ExpandingSimplex(listOf(b, b)).getWinding())
        assertEquals(1, ExpandingSimplex(listOf(b)).size())
        assertEquals(2, ExpandingSimplex(listOf(b, b)).size())
    }
    @Test fun expandingSimplexExpandAndGetClosest() {
        val simplex = ExpandingSimplex(listOf(a, b, c))
        simplex.expand(Vector2(-1.0, 1.0))
        assertEquals(4, simplex.size())
        var edge = simplex.getClosestEdge()
        vector(-1.0, -1.0, edge.point1); vector(2.0, -1.0, edge.point2)
        assertEquals(1.0, edge.distance, 1e-3); vector(0.0, -1.0, edge.normal)
        simplex.expand(Vector2(1.0, -2.0))
        assertEquals(5, simplex.size()); edge = simplex.getClosestEdge()
        vector(-1.0, 1.0, edge.point1); vector(-1.0, -1.0, edge.point2)
        assertEquals(1.0, edge.distance, 1e-3); vector(-1.0, 0.0, edge.normal)
    }

    @Test fun minkowskiSumPointCreateSuccess() {
        val first = Vector2(0.0, 0.0); val second = Vector2(1.0, 1.0)
        val point = MinkowskiSumPoint(first, second)
        assertSame(first, point.getSupportPoint1()); assertSame(second, point.getSupportPoint2())
        vector(-1.0, -1.0, point.getPoint()); assertNotNull(point.toString())
    }
    private fun sum(): MinkowskiSum {
        val second = Transform(); second.translate(1.0, 0.0)
        return MinkowskiSum(Geometry.createCircle(1.0), Transform(), Geometry.createCircle(1.0), second)
    }
    @Test fun minkowskiSumCreateSuccess() {
        val c1 = Geometry.createCircle(1.0); val c2 = Geometry.createCircle(1.0)
        val t1 = Transform(); val t2 = Transform(); t2.translate(1.0, 0.0)
        val sum = MinkowskiSum(c1, t1, c2, t2)
        assertSame(c1, sum.getConvex1()); assertSame(t1, sum.getTransform1())
        assertSame(c2, sum.getConvex2()); assertSame(t2, sum.getTransform2())
    }
    @Test fun minkowskiSumTostring() { assertNotNull(sum().toString()) }
    @Test fun minkowskiSumGetSupportPoint() {
        val sum = sum()
        listOf(
            Vector2(0.0, 1.0) to Vector2(-1.0, 2.0),
            Vector2(0.0, -1.0) to Vector2(-1.0, -2.0),
            Vector2(1.0, 0.0) to Vector2(1.0, 0.0),
            Vector2(-1.0, 0.0) to Vector2(-3.0, 0.0)
        ).forEach { (direction, expected) -> vector(expected.x, expected.y, sum.getSupportPoint(direction)) }
    }
    @Test fun minkowskiSumGetSupportPoints() {
        val sum = sum()
        listOf(
            Triple(Vector2(0.0, 1.0), Vector2(0.0, 1.0), Vector2(1.0, -1.0)),
            Triple(Vector2(0.0, -1.0), Vector2(0.0, -1.0), Vector2(1.0, 1.0)),
            Triple(Vector2(1.0, 0.0), Vector2(1.0, 0.0), Vector2(0.0, 0.0)),
            Triple(Vector2(-1.0, 0.0), Vector2(-1.0, 0.0), Vector2(2.0, 0.0))
        ).forEach { (direction, first, second) ->
            val point = sum.getSupportPoints(direction)
            vector(first.x, first.y, point.getSupportPoint1())
            vector(second.x, second.y, point.getSupportPoint2())
            vector(first.x - second.x, first.y - second.y, point.getPoint())
        }
    }
}
