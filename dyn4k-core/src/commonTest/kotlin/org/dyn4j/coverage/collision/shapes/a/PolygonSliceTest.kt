/*
 * Copyright (c) 2010-2022 William Bittle  http://www.dyn4j.org/
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

package org.dyn4j.coverage.collision.shapes.a

import de.infix.testBalloon.framework.core.testSuite
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue
import org.dyn4j.collision.manifold.ClippingManifoldSolver
import org.dyn4j.collision.manifold.Manifold
import org.dyn4j.collision.manifold.ManifoldPoint
import org.dyn4j.collision.narrowphase.Gjk
import org.dyn4j.collision.narrowphase.Penetration
import org.dyn4j.collision.narrowphase.Sat
import org.dyn4j.collision.narrowphase.Separation
import org.dyn4j.geometry.*

val PolygonSliceTest by testSuite {
    test("detectSat") { PolygonSliceTestFixture().run { detectSat() } }
    test("detectGjk") { PolygonSliceTestFixture().run { detectGjk() } }
    test("gjkDistance") { PolygonSliceTestFixture().run { gjkDistance() } }
    test("getClipManifold") { PolygonSliceTestFixture().run { getClipManifold() } }
}

private class PolygonSliceTestFixture  {
    private val sat = Sat()
    private val gjk = Gjk()
    private val cmfs = ClippingManifoldSolver()
    private lateinit var polygon: Polygon
    private lateinit var slice: Slice
    private fun setup() {
        polygon = Geometry.createUnitCirclePolygon(5, 0.5)
        slice = Slice(0.5, radians(50.0))
    }
fun detectSat() {
        setup()
        val p = Penetration()
        val t1 = Transform()
        val t2 = Transform()
        lateinit var n: Vector2
        assertTrue(sat.detect(polygon, t1, slice, t2, p))
        assertTrue(sat.detect(polygon, t1, slice, t2))
        n = p.getNormal()
        assertFiniteClose( 0.809, n.x, 1.0e-3)
        assertFiniteClose( 0.587, n.y, 1.0e-3)
        assertFiniteClose( 0.404, p.getDepth(), 1.0e-3)
        p.clear()
        assertTrue(sat.detect(slice, t2, polygon, t1, p))
        assertTrue(sat.detect(slice, t2, polygon, t1))
        n = p.getNormal()
        assertFiniteClose(-0.809, n.x, 1.0e-3)
        assertFiniteClose(-0.587, n.y, 1.0e-3)
        assertFiniteClose( 0.404, p.getDepth(), 1.0e-3)
        p.clear()
        t1.translate(-0.25, 0.0)
        assertTrue(sat.detect(polygon, t1, slice, t2, p))
        assertTrue(sat.detect(polygon, t1, slice, t2))
        n = p.getNormal()
        assertFiniteClose( 0.809, n.x, 1.0e-3)
        assertFiniteClose( 0.587, n.y, 1.0e-3)
        assertFiniteClose( 0.202, p.getDepth(), 1.0e-3)
        p.clear()
        assertTrue(sat.detect(slice, t2, polygon, t1, p))
        assertTrue(sat.detect(slice, t2, polygon, t1))
        n = p.getNormal()
        assertFiniteClose(-0.809, n.x, 1.0e-3)
        assertFiniteClose(-0.587, n.y, 1.0e-3)
        assertFiniteClose( 0.202, p.getDepth(), 1.0e-3)
        p.clear()
        t2.translate(0.0, 0.4)
        assertFalse(sat.detect(polygon, t1, slice, t2, p))
        assertFalse(sat.detect(polygon, t1, slice, t2))
        p.clear()
        assertFalse(sat.detect(slice, t2, polygon, t1, p))
        assertFalse(sat.detect(slice, t2, polygon, t1))
        p.clear()
        t2.translate(1.0, 0.0)
        assertFalse(sat.detect(polygon, t1, slice, t2, p))
        assertFalse(sat.detect(polygon, t1, slice, t2))
        p.clear()
        assertFalse(sat.detect(slice, t2, polygon, t1, p))
        assertFalse(sat.detect(slice, t2, polygon, t1))
    }
fun detectGjk() {
        setup()
        val p = Penetration()
        val t1 = Transform()
        val t2 = Transform()
        lateinit var n: Vector2
        assertTrue(gjk.detect(polygon, t1, slice, t2, p))
        assertTrue(gjk.detect(polygon, t1, slice, t2))
        n = p.getNormal()
        assertFiniteClose( 0.809, n.x, 1.0e-3)
        assertFiniteClose( 0.587, n.y, 1.0e-3)
        assertFiniteClose( 0.404, p.getDepth(), 1.0e-3)
        p.clear()
        assertTrue(gjk.detect(slice, t2, polygon, t1, p))
        assertTrue(gjk.detect(slice, t2, polygon, t1))
        n = p.getNormal()
        assertFiniteClose(-0.809, n.x, 1.0e-3)
        assertFiniteClose(-0.587, n.y, 1.0e-3)
        assertFiniteClose( 0.404, p.getDepth(), 1.0e-3)
        p.clear()
        t1.translate(-0.25, 0.0)
        assertTrue(gjk.detect(polygon, t1, slice, t2, p))
        assertTrue(gjk.detect(polygon, t1, slice, t2))
        n = p.getNormal()
        assertFiniteClose( 0.809, n.x, 1.0e-3)
        assertFiniteClose( 0.587, n.y, 1.0e-3)
        assertFiniteClose( 0.202, p.getDepth(), 1.0e-3)
        p.clear()
        assertTrue(gjk.detect(slice, t2, polygon, t1, p))
        assertTrue(gjk.detect(slice, t2, polygon, t1))
        n = p.getNormal()
        assertFiniteClose(-0.809, n.x, 1.0e-3)
        assertFiniteClose(-0.587, n.y, 1.0e-3)
        assertFiniteClose( 0.202, p.getDepth(), 1.0e-3)
        p.clear()
        t2.translate(0.0, 0.4)
        assertFalse(gjk.detect(polygon, t1, slice, t2, p))
        assertFalse(gjk.detect(polygon, t1, slice, t2))
        p.clear()
        assertFalse(gjk.detect(slice, t2, polygon, t1, p))
        assertFalse(gjk.detect(slice, t2, polygon, t1))
        p.clear()
        t2.translate(1.0, 0.0)
        assertFalse(gjk.detect(polygon, t1, slice, t2, p))
        assertFalse(gjk.detect(polygon, t1, slice, t2))
        p.clear()
        assertFalse(gjk.detect(slice, t2, polygon, t1, p))
        assertFalse(gjk.detect(slice, t2, polygon, t1))
    }
fun gjkDistance() {
        setup()
        val s = Separation()
        val t1 = Transform()
        val t2 = Transform()
        lateinit var n: Vector2
        lateinit var p1: Vector2
        lateinit var p2: Vector2
        assertFalse(gjk.distance(polygon, t1, slice, t2, s))
        s.clear()
        assertFalse(gjk.distance(slice, t2, polygon, t1, s))
        s.clear()
        t1.translate(-0.25, 0.0)
        assertFalse(gjk.distance(polygon, t1, slice, t2, s))
        s.clear()
        assertFalse(gjk.distance(slice, t2, polygon, t1, s))
        s.clear()
        t2.translate(0.0, 0.4)
        assertTrue(gjk.distance(polygon, t1, slice, t2, s))
        n = s.getNormal()
        p1 = s.getPoint1()
        p2 = s.getPoint2()
        assertFiniteClose( 0.032, s.getDistance(), 1.0e-3)
        assertFiniteClose( 0.809, n.x, 1.0e-3)
        assertFiniteClose( 0.587, n.y, 1.0e-3)
        assertFiniteClose(-0.026, p1.x, 1.0e-3)
        assertFiniteClose( 0.380, p1.y, 1.0e-3)
        assertFiniteClose( 0.000, p2.x, 1.0e-3)
        assertFiniteClose( 0.400, p2.y, 1.0e-3)
        s.clear()
        assertTrue(gjk.distance(slice, t2, polygon, t1, s))
        n = s.getNormal()
        p1 = s.getPoint1()
        p2 = s.getPoint2()
        assertFiniteClose( 0.032, s.getDistance(), 1.0e-3)
        assertFiniteClose(-0.809, n.x, 1.0e-3)
        assertFiniteClose(-0.587, n.y, 1.0e-3)
        assertFiniteClose( 0.000, p1.x, 1.0e-3)
        assertFiniteClose( 0.400, p1.y, 1.0e-3)
        assertFiniteClose(-0.026, p2.x, 1.0e-3)
        assertFiniteClose( 0.380, p2.y, 1.0e-3)
        s.clear()
        t2.translate(1.0, 0.0)
        assertTrue(gjk.distance(polygon, t1, slice, t2, s))
        n = s.getNormal()
        p1 = s.getPoint1()
        p2 = s.getPoint2()
        assertFiniteClose( 0.850, s.getDistance(), 1.0e-3)
        assertFiniteClose( 0.882, n.x, 1.0e-3)
        assertFiniteClose( 0.470, n.y, 1.0e-3)
        assertFiniteClose( 0.250, p1.x, 1.0e-3)
        assertFiniteClose( 0.000, p1.y, 1.0e-3)
        assertFiniteClose( 1.000, p2.x, 1.0e-3)
        assertFiniteClose( 0.400, p2.y, 1.0e-3)
        s.clear()
        assertTrue(gjk.distance(slice, t2, polygon, t1, s))
        n = s.getNormal()
        p1 = s.getPoint1()
        p2 = s.getPoint2()
        assertFiniteClose( 0.850, s.getDistance(), 1.0e-3)
        assertFiniteClose(-0.882, n.x, 1.0e-3)
        assertFiniteClose(-0.470, n.y, 1.0e-3)
        assertFiniteClose( 1.000, p1.x, 1.0e-3)
        assertFiniteClose( 0.400, p1.y, 1.0e-3)
        assertFiniteClose( 0.250, p2.x, 1.0e-3)
        assertFiniteClose( 0.000, p2.y, 1.0e-3)
    }
fun getClipManifold() {
        setup()
        val m = Manifold()
        val p = Penetration()
        val t1 = Transform()
        val t2 = Transform()
        lateinit var mp1: ManifoldPoint
        lateinit var mp2: ManifoldPoint
        lateinit var p1: Vector2
        lateinit var p2: Vector2
        gjk.detect(polygon, t1, slice, t2, p)
        assertTrue(cmfs.getManifold(p, polygon, t1, slice, t2, m))
        assertEquals(2, m.getPoints().size)
        p.clear()
        m.clear()
        gjk.detect(slice, t2, polygon, t1, p)
        assertTrue(cmfs.getManifold(p, slice, t2, polygon, t1, m))
        assertEquals(2, m.getPoints().size)
        p.clear()
        m.clear()
        sat.detect(polygon, t1, slice, t2, p)
        assertTrue(cmfs.getManifold(p, polygon, t1, slice, t2, m))
        assertEquals(2, m.getPoints().size)
        p.clear()
        m.clear()
        sat.detect(slice, t2, polygon, t1, p)
        assertTrue(cmfs.getManifold(p, slice, t2, polygon, t1, m))
        assertEquals(2, m.getPoints().size)
        t1.translate(-0.25, 0.0)
        p.clear()
        m.clear()
        gjk.detect(polygon, t1, slice, t2, p)
        assertTrue(cmfs.getManifold(p, polygon, t1, slice, t2, m))
        assertEquals(2, m.getPoints().size)
        mp1 = m.getPoints().get(0)
        p1 = mp1.getPoint()
        assertFiniteClose( 0.000, p1.x, 1.0e-3)
        assertFiniteClose( 0.000, p1.y, 1.0e-3)
        assertFiniteClose( 0.202, mp1.getDepth(), 1.0e-3)
        mp2 = m.getPoints().get(1)
        p2 = mp2.getPoint()
        assertFiniteClose( 0.152, p2.x, 1.0e-3)
        assertFiniteClose(-0.071, p2.y, 1.0e-3)
        assertFiniteClose( 0.120, mp2.getDepth(), 1.0e-3)
        p.clear()
        m.clear()
        gjk.detect(slice, t2, polygon, t1, p)
        assertTrue(cmfs.getManifold(p, slice, t2, polygon, t1, m))
        assertEquals(2, m.getPoints().size)
        mp1 = m.getPoints().get(0)
        p1 = mp1.getPoint()
        assertFiniteClose( 0.000, p1.x, 1.0e-3)
        assertFiniteClose( 0.000, p1.y, 1.0e-3)
        assertFiniteClose( 0.202, mp1.getDepth(), 1.0e-3)
        mp2 = m.getPoints().get(1)
        p2 = mp2.getPoint()
        assertFiniteClose( 0.152, p2.x, 1.0e-3)
        assertFiniteClose(-0.071, p2.y, 1.0e-3)
        assertFiniteClose( 0.120, mp2.getDepth(), 1.0e-3)
        p.clear()
        m.clear()
        sat.detect(polygon, t1, slice, t2, p)
        assertTrue(cmfs.getManifold(p, polygon, t1, slice, t2, m))
        assertEquals(2, m.getPoints().size)
        mp1 = m.getPoints().get(0)
        p1 = mp1.getPoint()
        assertFiniteClose( 0.000, p1.x, 1.0e-3)
        assertFiniteClose( 0.000, p1.y, 1.0e-3)
        assertFiniteClose( 0.202, mp1.getDepth(), 1.0e-3)
        mp2 = m.getPoints().get(1)
        p2 = mp2.getPoint()
        assertFiniteClose( 0.152, p2.x, 1.0e-3)
        assertFiniteClose(-0.071, p2.y, 1.0e-3)
        assertFiniteClose( 0.120, mp2.getDepth(), 1.0e-3)
        p.clear()
        m.clear()
        sat.detect(slice, t2, polygon, t1, p)
        assertTrue(cmfs.getManifold(p, slice, t2, polygon, t1, m))
        assertEquals(2, m.getPoints().size)
        mp1 = m.getPoints().get(0)
        p1 = mp1.getPoint()
        assertFiniteClose( 0.000, p1.x, 1.0e-3)
        assertFiniteClose( 0.000, p1.y, 1.0e-3)
        assertFiniteClose( 0.202, mp1.getDepth(), 1.0e-3)
        mp2 = m.getPoints().get(1)
        p2 = mp2.getPoint()
        assertFiniteClose( 0.152, p2.x, 1.0e-3)
        assertFiniteClose(-0.071, p2.y, 1.0e-3)
        assertFiniteClose( 0.120, mp2.getDepth(), 1.0e-3)
    }
}
