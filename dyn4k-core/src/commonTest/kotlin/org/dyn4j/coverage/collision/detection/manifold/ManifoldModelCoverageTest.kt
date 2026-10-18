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
package org.dyn4j.collision.manifold

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNotSame
import kotlin.test.assertSame
import kotlin.test.assertTrue
import org.dyn4j.collision.manifold.IndexedManifoldPointId
import org.dyn4j.collision.manifold.ClippingManifoldSolver
import org.dyn4j.collision.manifold.Manifold
import org.dyn4j.collision.manifold.ManifoldPoint
import org.dyn4j.collision.manifold.ManifoldPointId
import org.dyn4j.collision.narrowphase.Gjk
import org.dyn4j.collision.narrowphase.Penetration
import org.dyn4j.geometry.Convex
import org.dyn4j.geometry.Geometry
import org.dyn4j.geometry.Transform
import org.dyn4j.geometry.Vector2
import kotlin.math.PI

class ManifoldModelCoverageTest {
    private class SeedManifold(normal: Vector2, points: List<ManifoldPoint>) : Manifold(normal, points)

    @Test fun indexedManifoldPointIdCreate() {
        val plain = IndexedManifoldPointId(0, 1, 0)
        assertEquals(0, plain.getReferenceEdgeIndex())
        assertEquals(1, plain.getIncidentEdgeIndex())
        assertEquals(0, plain.getIncidentVertexIndex())
        assertFalse(plain.isFlipped())
        val flipped = IndexedManifoldPointId(1, 2, 3, true)
        assertEquals(1, flipped.getReferenceEdgeIndex())
        assertEquals(2, flipped.getIncidentEdgeIndex())
        assertEquals(3, flipped.getIncidentVertexIndex())
        assertTrue(flipped.isFlipped())
    }

    @Test fun indexedManifoldPointIdEquals() {
        val source = IndexedManifoldPointId(0, 1, 0)
        assertEquals(source, source)
        assertEquals(source, IndexedManifoldPointId(0, 1, 0))
        assertNotSame(source, IndexedManifoldPointId(0, 1, 0))
        assertNotEquals(source, IndexedManifoldPointId(0, 1, 2))
        assertNotEquals(source, IndexedManifoldPointId(0, 0, 0))
        assertNotEquals(source, IndexedManifoldPointId(1, 0, 0))
        assertNotEquals(source, IndexedManifoldPointId(0, 1, 0, true))
        assertFalse(source.equals(null))
        assertFalse(source.equals(Any()))
    }

    @Test fun indexedManifoldPointIdHashcode() {
        val source = IndexedManifoldPointId(0, 1, 0)
        assertEquals(source.hashCode(), IndexedManifoldPointId(0, 1, 0).hashCode())
        assertNotEquals(source.hashCode(), IndexedManifoldPointId(0, 1, 2).hashCode())
        assertNotEquals(source.hashCode(), IndexedManifoldPointId(0, 1, 0, true).hashCode())
    }

    @Test fun indexedManifoldPointIdTostring() {
        assertNotNull(IndexedManifoldPointId(0, 1, 0).toString())
    }

    @Test fun indexedManifoldPointIdCopy() {
        val source = IndexedManifoldPointId(0, 1, 0, true)
        val copy = source.copy()
        assertEquals(source, copy)
        assertNotSame(source, copy)
    }

    @Test fun manifoldPointIdCreate() {
        assertNotNull(ManifoldPointId.DISTANCE.toString())
    }

    @Test fun manifoldPointIdCopy() {
        val id = ManifoldPointId.DISTANCE
        assertSame(id, id.copy())
    }

    @Test fun manifoldPointCreate() {
        val empty = ManifoldPoint(ManifoldPointId.DISTANCE)
        assertEquals(Vector2(), empty.getPoint())
        assertEquals(0.0, empty.getDepth())
        assertSame(ManifoldPointId.DISTANCE, empty.getId())
        val input = Vector2(1.0, 2.0)
        val seeded = ManifoldPoint(ManifoldPointId.DISTANCE, input, 1.0)
        assertSame(ManifoldPointId.DISTANCE, seeded.getId())
        assertEquals(Vector2(1.0, 2.0), seeded.getPoint())
        assertNotSame(input, seeded.getPoint())
        assertEquals(1.0, seeded.getDepth())
        assertSame(ManifoldPointId.DISTANCE, ManifoldPoint(null).getId())
    }

    @Test fun manifoldPointCopy() {
        val source = ManifoldPoint(ManifoldPointId.DISTANCE, Vector2(1.0, 2.0), 1.0)
        for (result in listOf(source.copy(), ManifoldPoint(ManifoldPointId.DISTANCE).also { it.set(source) })) {
            assertSame(source.getId(), result.getId())
            assertEquals(Vector2(1.0, 2.0), result.getPoint())
            assertEquals(1.0, result.getDepth())
            assertNotSame(source.getPoint(), result.getPoint())
        }
        val indexed = IndexedManifoldPointId(1, 2, 3, true)
        val indexedPoint = ManifoldPoint(indexed, Vector2(3.0, 4.0), 2.0)
        val copy = indexedPoint.copy()
        assertNotSame(indexedPoint, copy)
        assertEquals(indexedPoint.getId(), copy.getId())
        assertNotSame(indexedPoint.getId(), copy.getId())
        assertEquals(Vector2(3.0, 4.0), copy.getPoint())
        assertNotSame(indexedPoint.getPoint(), copy.getPoint())
        assertEquals(2.0, copy.getDepth())
    }

    @Test fun manifoldPointGetSetPoint() {
        val result = ManifoldPoint(ManifoldPointId.DISTANCE)
        val exposed = result.getPoint()
        val input = Vector2(-2.0, 1.0)
        result.setPoint(input)
        assertSame(exposed, result.getPoint())
        assertNotSame(input, exposed)
        assertEquals(Vector2(-2.0, 1.0), exposed)
        assertEquals(0.0, result.getDepth())
        assertSame(ManifoldPointId.DISTANCE, result.getId())
    }

    @Test fun manifoldPointGetSetDepth() {
        val result = ManifoldPoint(ManifoldPointId.DISTANCE)
        result.setDepth(5.0)
        assertEquals(5.0, result.getDepth())
        assertEquals(Vector2(), result.getPoint())
        assertSame(ManifoldPointId.DISTANCE, result.getId())
    }

    @Test fun manifoldPointTostring() {
        assertNotNull(ManifoldPoint(ManifoldPointId.DISTANCE).toString())
    }

    @Test fun manifoldPointShift() {
        val result = ManifoldPoint(ManifoldPointId.DISTANCE)
        result.setPoint(Vector2(1.0, -1.0))
        result.setDepth(4.0)
        result.shift(Vector2(2.0, -1.0))
        assertEquals(Vector2(3.0, -2.0), result.getPoint())
        assertEquals(4.0, result.getDepth())
        assertSame(ManifoldPointId.DISTANCE, result.getId())
    }

    @Test fun manifoldCreate() {
        val result = Manifold()
        assertEquals(Vector2(), result.getNormal())
        assertTrue(result.getPoints().isEmpty())
        assertSame(result.getNormal(), result.getNormal())
        assertSame(result.getPoints(), result.getPoints())
        val seeded = SeedManifold(result.getNormal(), result.getPoints())
        assertEquals(Vector2(), seeded.getNormal())
        assertTrue(seeded.getPoints().isEmpty())
    }

    @Test fun manifoldClear() {
        val result = Manifold()
        result.setNormal(Vector2(1.0, 1.0))
        result.getPoints().add(ManifoldPoint(ManifoldPointId.DISTANCE, Vector2(1.0, 1.0), 1.0))
        result.clear()
        assertEquals(Vector2(), result.getNormal())
        assertTrue(result.getPoints().isEmpty())
    }

    @Test fun manifoldCopy() {
        val source = Manifold()
        source.setNormal(Vector2(1.0, 1.0))
        source.getPoints().add(ManifoldPoint(ManifoldPointId.DISTANCE, Vector2(1.0, 1.0), 1.0))
        for (result in listOf(source.copy(), Manifold().also { it.set(source) })) {
            assertEquals(Vector2(1.0, 1.0), result.getNormal())
            assertNotSame(source.getNormal(), result.getNormal())
            assertNotSame(source.getPoints(), result.getPoints())
            assertEquals(1, result.getPoints().size)
            assertNotSame(source.getPoints()[0], result.getPoints()[0])
            assertSame(source.getPoints()[0].getId(), result.getPoints()[0].getId())
            assertEquals(Vector2(1.0, 1.0), result.getPoints()[0].getPoint())
            assertNotSame(source.getPoints()[0].getPoint(), result.getPoints()[0].getPoint())
            assertEquals(1.0, result.getPoints()[0].getDepth())
        }
    }

    @Test fun manifoldGetSetNormal() {
        val result = Manifold()
        val exposed = result.getNormal()
        val input = Vector2(1.0, 2.0)
        result.setNormal(input)
        assertSame(exposed, result.getNormal())
        assertNotSame(input, exposed)
        assertEquals(Vector2(1.0, 2.0), exposed)
    }

    @Test fun manifoldGetSetPoints() {
        val result = Manifold()
        val input = arrayListOf(ManifoldPoint(ManifoldPointId.DISTANCE, Vector2(2.0, 3.0), 5.0))
        val exposed = result.getPoints()
        result.setPoints(input)
        assertSame(exposed, result.getPoints())
        assertNotSame(input, exposed)
        assertEquals(1, exposed.size)
        assertNotSame(input[0], exposed[0])
        assertNotSame(input[0].getPoint(), exposed[0].getPoint())
        assertEquals(Vector2(2.0, 3.0), exposed[0].getPoint())
        assertEquals(5.0, exposed[0].getDepth())
    }

    @Test fun manifoldTostring() {
        val result = Manifold()
        assertNotNull(result.toString())
        result.setNormal(Vector2(1.0, 1.0))
        result.getPoints().add(ManifoldPoint(ManifoldPointId.DISTANCE, Vector2(1.0, 1.0), 1.0))
        result.getPoints().add(ManifoldPoint(ManifoldPointId.DISTANCE, Vector2(2.0, 3.0), 0.5))
        assertNotNull(result.toString())
    }

    @Test fun manifoldShift() {
        val result = Manifold()
        result.setNormal(Vector2(1.0, 1.0))
        result.getPoints().add(ManifoldPoint(ManifoldPointId.DISTANCE, Vector2(1.0, 1.0), 1.0))
        result.shift(Vector2(2.0, -1.0))
        assertEquals(Vector2(1.0, 1.0), result.getNormal())
        assertEquals(1, result.getPoints().size)
        assertEquals(Vector2(3.0, 0.0), result.getPoints()[0].getPoint())
        assertEquals(1.0, result.getPoints()[0].getDepth())
    }
}

class ClippingManifoldCoverageTest {
    private data class Contact(val depth: Double, val x: Double, val y: Double)
    private data class Expected(val x: Double, val y: Double, val points: List<Contact>)

    private fun verify(
        first: Convex, second: Convex, shifted: Transform, forward: Expected, reverse: Expected
    ) {
        val detector = Gjk()
        val solver = ClippingManifoldSolver()
        val origin = Transform()
        val penetration = Penetration()
        val manifold = Manifold()
        assertTrue(detector.detect(first, origin, second, shifted, penetration))
        assertTrue(solver.getManifold(penetration, first, origin, second, shifted, manifold))
        check(manifold, forward)
        penetration.clear()
        manifold.clear()
        assertTrue(detector.detect(second, shifted, first, origin, penetration))
        assertTrue(solver.getManifold(penetration, second, shifted, first, origin, manifold))
        check(manifold, reverse)
    }

    private fun check(result: Manifold, expected: Expected) {
        assertEquals(expected.x, result.getNormal().x, 1e-3)
        assertEquals(expected.y, result.getNormal().y, 1e-3)
        assertEquals(expected.points.size, result.getPoints().size)
        for (index in expected.points.indices) {
            val actual = result.getPoints()[index]
            val point = expected.points[index]
            assertEquals(point.depth, actual.getDepth(), 1e-3)
            assertEquals(point.x, actual.getPoint().x, 1e-3)
            assertEquals(point.y, actual.getPoint().y, 1e-3)
        }
    }

    @Test fun scenario1() {
        val shifted = Transform().also { it.translate(0.5, 0.5) }
        val point = listOf(Contact(0.250, 0.500, 0.000))
        verify(Geometry.createRectangle(1.0, 0.5), Geometry.createCircle(0.5), shifted,
            Expected(0.0, -1.0, point), Expected(0.0, 1.0, point))
    }

    @Test fun scenario2() {
        val shifted = Transform().also { it.translate(-0.5, -0.35) }
        verify(Geometry.createRectangle(1.0, 0.5), Geometry.createSquare(0.5), shifted,
            Expected(0.0, 1.0, listOf(Contact(0.150, -0.250, -0.100), Contact(0.150, -0.500, -0.100))),
            Expected(0.0, -1.0, listOf(Contact(0.150, -0.500, -0.250), Contact(0.150, -0.250, -0.250))))
    }

    @Test fun scenario3() {
        val shifted = Transform().also { it.rotate(PI / 18.0); it.translate(-0.5, -0.5) }
        val points = listOf(Contact(0.039, -0.297, -0.210), Contact(0.003, -0.500, -0.246))
        verify(Geometry.createRectangle(1.0, 0.5), Geometry.createSquare(0.5), shifted,
            Expected(0.0, 1.0, points), Expected(0.0, -1.0, points))
    }

    @Test fun scenario4() {
        val shifted = Transform().also { it.rotate(PI / 3.0); it.translate(-0.5, -0.5) }
        val point = listOf(Contact(0.033, -0.500, -0.250))
        verify(Geometry.createRectangle(1.0, 0.5), Geometry.createSquare(0.5), shifted,
            Expected(0.500, 0.866, point), Expected(-0.500, -0.866, point))
    }

    @Test fun scenario5() {
        val shifted = Transform().also { it.translate(0.0, -0.35) }
        verify(Geometry.createRectangle(1.0, 0.5), Geometry.createSquare(0.5), shifted,
            Expected(0.0, 1.0, listOf(Contact(0.150, 0.250, -0.100), Contact(0.150, -0.250, -0.100))),
            Expected(0.0, -1.0, listOf(Contact(0.150, 0.250, -0.250), Contact(0.150, -0.250, -0.250))))
    }
}
