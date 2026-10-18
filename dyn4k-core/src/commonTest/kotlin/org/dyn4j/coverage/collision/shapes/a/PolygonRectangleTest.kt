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

import kotlin.test.Test
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

class PolygonRectangleTest {
    private val sat = Sat()
    private val gjk = Gjk()
    private val cmfs = ClippingManifoldSolver()
    private lateinit var poly: Polygon
    private lateinit var rect: Rectangle
    private fun setup() {
        poly = Geometry.createUnitCirclePolygon(5, 1.0)
        rect = Rectangle(1.0, 1.0)
    }
    @Test
    fun detectSat() {
        setup()
        val p = Penetration()
        val t1 = Transform()
        val t2 = Transform()
        lateinit var n: Vector2
        assertTrue(sat.detect(poly, t1, rect, t2, p))
        assertTrue(sat.detect(poly, t1, rect, t2))
        n = p.getNormal()
        assertFiniteClose(1.309, p.getDepth(), 1.0e-3)
        assertFiniteClose(1.0, n.x, 1.0e-3)
        assertFiniteClose(0.0, n.y, 1.0e-3)
        p.clear()
        assertTrue(sat.detect(rect, t2, poly, t1, p))
        assertTrue(sat.detect(rect, t2, poly, t1))
        n = p.getNormal()
        assertFiniteClose(1.309, p.getDepth(), 1.0e-3)
        assertFiniteClose(-1.0, n.x, 1.0e-3)
        assertFiniteClose(0.0, n.y, 1.0e-3)
        p.clear()
        t1.translate(-1.0, 0.0)
        assertTrue(sat.detect(poly, t1, rect, t2, p))
        assertTrue(sat.detect(poly, t1, rect, t2))
        n = p.getNormal()
        assertFiniteClose(0.5, p.getDepth(), 1.0e-3)
        assertFiniteClose(1.0, n.x, 1.0e-3)
        assertFiniteClose(0.0, n.y, 1.0e-3)
        p.clear()
        assertTrue(sat.detect(rect, t2, poly, t1, p))
        assertTrue(sat.detect(rect, t2, poly, t1))
        n = p.getNormal()
        assertFiniteClose(0.5, p.getDepth(), 1.0e-3)
        assertFiniteClose(-1.0, n.x, 1.0e-3)
        assertFiniteClose(0.0, n.y, 1.0e-3)
        p.clear()
        t2.translate(0.0, 1.3)
        assertFalse(sat.detect(poly, t1, rect, t2, p))
        assertFalse(sat.detect(poly, t1, rect, t2))
        p.clear()
        assertFalse(sat.detect(rect, t2, poly, t1, p))
        assertFalse(sat.detect(rect, t2, poly, t1))
        p.clear()
        t1.translate(-1.0, 0.0)
        assertFalse(sat.detect(poly, t1, rect, t2, p))
        assertFalse(sat.detect(poly, t1, rect, t2))
        p.clear()
        assertFalse(sat.detect(rect, t2, poly, t1, p))
        assertFalse(sat.detect(rect, t2, poly, t1))
    }
    @Test
    fun detectGjk() {
        setup()
        val p = Penetration()
        val t1 = Transform()
        val t2 = Transform()
        lateinit var n: Vector2
        assertTrue(gjk.detect(poly, t1, rect, t2, p))
        assertTrue(gjk.detect(poly, t1, rect, t2))
        n = p.getNormal()
        assertFiniteClose(1.309, p.getDepth(), 1.0e-3)
        assertFiniteClose(-1.0, n.x, 1.0e-3)
        assertFiniteClose(0.0, n.y, 1.0e-3)
        p.clear()
        assertTrue(gjk.detect(rect, t2, poly, t1, p))
        assertTrue(gjk.detect(rect, t2, poly, t1))
        n = p.getNormal()
        assertFiniteClose(1.309, p.getDepth(), 1.0e-3)
        assertFiniteClose(1.0, n.x, 1.0e-3)
        assertFiniteClose(0.0, n.y, 1.0e-3)
        p.clear()
        t1.translate(-1.0, 0.0)
        assertTrue(gjk.detect(poly, t1, rect, t2, p))
        assertTrue(gjk.detect(poly, t1, rect, t2))
        n = p.getNormal()
        assertFiniteClose(0.5, p.getDepth(), 1.0e-3)
        assertFiniteClose(1.0, n.x, 1.0e-3)
        assertFiniteClose(0.0, n.y, 1.0e-3)
        p.clear()
        assertTrue(gjk.detect(rect, t2, poly, t1, p))
        assertTrue(gjk.detect(rect, t2, poly, t1))
        n = p.getNormal()
        assertFiniteClose(0.5, p.getDepth(), 1.0e-3)
        assertFiniteClose(-1.0, n.x, 1.0e-3)
        assertFiniteClose(0.0, n.y, 1.0e-3)
        p.clear()
        t2.translate(0.0, 1.3)
        assertFalse(gjk.detect(poly, t1, rect, t2, p))
        assertFalse(gjk.detect(poly, t1, rect, t2))
        p.clear()
        assertFalse(gjk.detect(rect, t2, poly, t1, p))
        assertFalse(gjk.detect(rect, t2, poly, t1))
        p.clear()
        t1.translate(-1.0, 0.0)
        assertFalse(gjk.detect(poly, t1, rect, t2, p))
        assertFalse(gjk.detect(poly, t1, rect, t2))
        p.clear()
        assertFalse(gjk.detect(rect, t2, poly, t1, p))
        assertFalse(gjk.detect(rect, t2, poly, t1))
    }
    @Test
    fun gjkDistance() {
        setup()
        val s = Separation()
        val t1 = Transform()
        val t2 = Transform()
        lateinit var n: Vector2
        lateinit var p1: Vector2
        lateinit var p2: Vector2
        assertFalse(gjk.distance(poly, t1, rect, t2, s))
        s.clear()
        assertFalse(gjk.distance(rect, t2, poly, t1, s))
        s.clear()
        t1.translate(-1.0, 0.0)
        assertFalse(gjk.distance(poly, t1, rect, t2, s))
        s.clear()
        assertFalse(gjk.distance(rect, t2, poly, t1, s))
        s.clear()
        t2.translate(0.0, 1.3)
        assertTrue(gjk.distance(poly, t1, rect, t2, s))
        n = s.getNormal()
        p1 = s.getPoint1()
        p2 = s.getPoint2()
        assertFiniteClose(0.065, s.getDistance(), 1.0e-3)
        assertFiniteClose(0.809, n.x, 1.0e-3)
        assertFiniteClose(0.587, n.y, 1.0e-3)
        assertFiniteClose(-0.553, p1.x, 1.0e-3)
        assertFiniteClose(0.761, p1.y, 1.0e-3)
        assertFiniteClose(-0.500, p2.x, 1.0e-3)
        assertFiniteClose(0.800, p2.y, 1.0e-3)
        s.clear()
        assertTrue(gjk.distance(rect, t2, poly, t1, s))
        n = s.getNormal()
        p1 = s.getPoint1()
        p2 = s.getPoint2()
        assertFiniteClose(0.065, s.getDistance(), 1.0e-3)
        assertFiniteClose(-0.809, n.x, 1.0e-3)
        assertFiniteClose(-0.587, n.y, 1.0e-3)
        assertFiniteClose(-0.500, p1.x, 1.0e-3)
        assertFiniteClose(0.800, p1.y, 1.0e-3)
        assertFiniteClose(-0.553, p2.x, 1.0e-3)
        assertFiniteClose(0.761, p2.y, 1.0e-3)
        s.clear()
        t1.translate(-1.0, 0.0)
        assertTrue(gjk.distance(poly, t1, rect, t2, s))
        n = s.getNormal()
        p1 = s.getPoint1()
        p2 = s.getPoint2()
        assertFiniteClose(0.874, s.getDistance(), 1.0e-3)
        assertFiniteClose(0.809, n.x, 1.0e-3)
        assertFiniteClose(0.587, n.y, 1.0e-3)
        assertFiniteClose(-1.207, p1.x, 1.0e-3)
        assertFiniteClose(0.285, p1.y, 1.0e-3)
        assertFiniteClose(-0.500, p2.x, 1.0e-3)
        assertFiniteClose(0.800, p2.y, 1.0e-3)
        s.clear()
        assertTrue(gjk.distance(rect, t2, poly, t1, s))
        n = s.getNormal()
        p1 = s.getPoint1()
        p2 = s.getPoint2()
        assertFiniteClose(0.874, s.getDistance(), 1.0e-3)
        assertFiniteClose(-0.809, n.x, 1.0e-3)
        assertFiniteClose(-0.587, n.y, 1.0e-3)
        assertFiniteClose(-0.500, p1.x, 1.0e-3)
        assertFiniteClose(0.800, p1.y, 1.0e-3)
        assertFiniteClose(-1.207, p2.x, 1.0e-3)
        assertFiniteClose(0.285, p2.y, 1.0e-3)
    }
    @Test
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
        gjk.detect(poly, t1, rect, t2, p)
        assertTrue(cmfs.getManifold(p, poly, t1, rect, t2, m))
        assertEquals(2, m.getPoints().size)
        p.clear()
        m.clear()
        gjk.detect(rect, t2, poly, t1, p)
        assertTrue(cmfs.getManifold(p, rect, t2, poly, t1, m))
        assertEquals(2, m.getPoints().size)
        p.clear()
        m.clear()
        sat.detect(poly, t1, rect, t2, p)
        assertTrue(cmfs.getManifold(p, poly, t1, rect, t2, m))
        assertEquals(2, m.getPoints().size)
        p.clear()
        m.clear()
        sat.detect(rect, t2, poly, t1, p)
        assertTrue(cmfs.getManifold(p, rect, t2, poly, t1, m))
        assertEquals(2, m.getPoints().size)
        t1.translate(-1.0, 0.0)
        p.clear()
        m.clear()
        gjk.detect(poly, t1, rect, t2, p)
        assertTrue(cmfs.getManifold(p, poly, t1, rect, t2, m))
        assertEquals(2, m.getPoints().size)
        mp1 = m.getPoints().get(0)
        mp2 = m.getPoints().get(1)
        p1 = mp1.getPoint()
        p2 = mp2.getPoint()
        assertFiniteClose(0.000, p1.x, 1.0e-3)
        assertFiniteClose(0.000, p1.y, 1.0e-3)
        assertFiniteClose(0.500, mp1.getDepth(), 1.0e-3)
        assertFiniteClose(-0.363, p2.x, 1.0e-3)
        assertFiniteClose(-0.500, p2.y, 1.0e-3)
        assertFiniteClose(0.136, mp2.getDepth(), 1.0e-3)
        p.clear()
        m.clear()
        gjk.detect(rect, t2, poly, t1, p)
        assertTrue(cmfs.getManifold(p, rect, t2, poly, t1, m))
        assertEquals(2, m.getPoints().size)
        mp1 = m.getPoints().get(0)
        mp2 = m.getPoints().get(1)
        p1 = mp1.getPoint()
        p2 = mp2.getPoint()
        assertFiniteClose(0.000, p1.x, 1.0e-3)
        assertFiniteClose(0.000, p1.y, 1.0e-3)
        assertFiniteClose(0.500, mp1.getDepth(), 1.0e-3)
        assertFiniteClose(-0.363, p2.x, 1.0e-3)
        assertFiniteClose(-0.500, p2.y, 1.0e-3)
        assertFiniteClose(0.136, mp2.getDepth(), 1.0e-3)
        p.clear()
        m.clear()
        sat.detect(poly, t1, rect, t2, p)
        assertTrue(cmfs.getManifold(p, poly, t1, rect, t2, m))
        assertEquals(2, m.getPoints().size)
        mp1 = m.getPoints().get(0)
        mp2 = m.getPoints().get(1)
        p1 = mp1.getPoint()
        p2 = mp2.getPoint()
        assertFiniteClose(0.000, p1.x, 1.0e-3)
        assertFiniteClose(0.000, p1.y, 1.0e-3)
        assertFiniteClose(0.500, mp1.getDepth(), 1.0e-3)
        assertFiniteClose(-0.363, p2.x, 1.0e-3)
        assertFiniteClose(-0.500, p2.y, 1.0e-3)
        assertFiniteClose(0.136, mp2.getDepth(), 1.0e-3)
        p.clear()
        m.clear()
        sat.detect(rect, t2, poly, t1, p)
        assertTrue(cmfs.getManifold(p, rect, t2, poly, t1, m))
        assertEquals(2, m.getPoints().size)
        mp1 = m.getPoints().get(0)
        mp2 = m.getPoints().get(1)
        p1 = mp1.getPoint()
        p2 = mp2.getPoint()
        assertFiniteClose(0.000, p1.x, 1.0e-3)
        assertFiniteClose(0.000, p1.y, 1.0e-3)
        assertFiniteClose(0.500, mp1.getDepth(), 1.0e-3)
        assertFiniteClose(-0.363, p2.x, 1.0e-3)
        assertFiniteClose(-0.500, p2.y, 1.0e-3)
        assertFiniteClose(0.136, mp2.getDepth(), 1.0e-3)
    }
    @Test
    fun nearZeroDistance1() {
        setup()
        val c1 = Geometry.createUnitCirclePolygon(5, 0.1)
        val c2 = Geometry.createRectangle(20.0, 0.5)
        val t1 = Transform()
        val t2 = Transform()
        t1.translate(0.0, 0.34510565162951545)
        val s = Separation()
        val separated = gjk.distance(c1, t1, c2, t2, s)
        assertTrue(separated)
        assertTrue(s.getDistance() >= 0.0)
    }
}
