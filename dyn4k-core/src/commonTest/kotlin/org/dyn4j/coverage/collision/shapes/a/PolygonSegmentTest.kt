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

val PolygonSegmentTest by testSuite {
    test("detectSat") { PolygonSegmentTestFixture().run { detectSat() } }
    test("detectGjk") { PolygonSegmentTestFixture().run { detectGjk() } }
    test("gjkDistance") { PolygonSegmentTestFixture().run { gjkDistance() } }
    test("getClipManifold") { PolygonSegmentTestFixture().run { getClipManifold() } }
    test("noManifoldPoints") { PolygonSegmentTestFixture().run { noManifoldPoints() } }
    test("testBadPoints1") { PolygonSegmentTestFixture().run { testBadPoints1() } }
}

private class PolygonSegmentTestFixture  {
    private val sat = Sat()
    private val gjk = Gjk()
    private val cmfs = ClippingManifoldSolver()
    private lateinit var poly: Polygon
    private lateinit var seg: Segment
    private fun setup() {
        poly = Geometry.createUnitCirclePolygon(5, 1.0)
        seg = Segment(Vector2(-0.5, 0.0), Vector2(0.0, 0.5))
    }
fun detectSat() {
        setup()
        val p = Penetration()
        val t1 = Transform()
        val t2 = Transform()
        lateinit var n: Vector2
        assertTrue(sat.detect(poly, t1, seg, t2, p))
        assertTrue(sat.detect(poly, t1, seg, t2))
        n = p.getNormal()
        assertFiniteClose(0.634, p.getDepth(), 1.0e-3)
        assertFiniteClose(-0.707, n.x, 1.0e-3)
        assertFiniteClose(0.707, n.y, 1.0e-3)
        p.clear()
        assertTrue(sat.detect(seg, t2, poly, t1, p))
        assertTrue(sat.detect(seg, t2, poly, t1))
        n = p.getNormal()
        assertFiniteClose(0.634, p.getDepth(), 1.0e-3)
        assertFiniteClose(0.707, n.x, 1.0e-3)
        assertFiniteClose(-0.707, n.y, 1.0e-3)
        p.clear()
        t1.translate(-1.0, 0.0)
        assertTrue(sat.detect(poly, t1, seg, t2, p))
        assertTrue(sat.detect(poly, t1, seg, t2))
        n = p.getNormal()
        assertFiniteClose(0.404, p.getDepth(), 1.0e-3)
        assertFiniteClose(0.809, n.x, 1.0e-3)
        assertFiniteClose(0.587, n.y, 1.0e-3)
        p.clear()
        assertTrue(sat.detect(seg, t2, poly, t1, p))
        assertTrue(sat.detect(seg, t2, poly, t1))
        n = p.getNormal()
        assertFiniteClose(0.404, p.getDepth(), 1.0e-3)
        assertFiniteClose(-0.809, n.x, 1.0e-3)
        assertFiniteClose(-0.587, n.y, 1.0e-3)
        p.clear()
        t2.translate(0.0, 0.9)
        assertFalse(sat.detect(poly, t1, seg, t2, p))
        assertFalse(sat.detect(poly, t1, seg, t2))
        p.clear()
        assertFalse(sat.detect(seg, t2, poly, t1, p))
        assertFalse(sat.detect(seg, t2, poly, t1))
        p.clear()
        t1.translate(-1.0, 0.0)
        assertFalse(sat.detect(poly, t1, seg, t2, p))
        assertFalse(sat.detect(poly, t1, seg, t2))
        p.clear()
        assertFalse(sat.detect(seg, t2, poly, t1, p))
        assertFalse(sat.detect(seg, t2, poly, t1))
    }
fun detectGjk() {
        setup()
        val p = Penetration()
        val t1 = Transform()
        val t2 = Transform()
        lateinit var n: Vector2
        assertTrue(gjk.detect(poly, t1, seg, t2, p))
        assertTrue(gjk.detect(poly, t1, seg, t2))
        n = p.getNormal()
        assertFiniteClose(0.634, p.getDepth(), 1.0e-3)
        assertFiniteClose(-0.707, n.x, 1.0e-3)
        assertFiniteClose(0.707, n.y, 1.0e-3)
        p.clear()
        assertTrue(gjk.detect(seg, t2, poly, t1, p))
        assertTrue(gjk.detect(seg, t2, poly, t1))
        n = p.getNormal()
        assertFiniteClose(0.634, p.getDepth(), 1.0e-3)
        assertFiniteClose(0.707, n.x, 1.0e-3)
        assertFiniteClose(-0.707, n.y, 1.0e-3)
        p.clear()
        t1.translate(-1.0, 0.0)
        assertTrue(gjk.detect(poly, t1, seg, t2, p))
        assertTrue(gjk.detect(poly, t1, seg, t2))
        n = p.getNormal()
        assertFiniteClose(0.404, p.getDepth(), 1.0e-3)
        assertFiniteClose(0.809, n.x, 1.0e-3)
        assertFiniteClose(0.587, n.y, 1.0e-3)
        p.clear()
        assertTrue(gjk.detect(seg, t2, poly, t1, p))
        assertTrue(gjk.detect(seg, t2, poly, t1))
        n = p.getNormal()
        assertFiniteClose(0.404, p.getDepth(), 1.0e-3)
        assertFiniteClose(-0.809, n.x, 1.0e-3)
        assertFiniteClose(-0.587, n.y, 1.0e-3)
        p.clear()
        t2.translate(0.0, 0.9)
        assertFalse(gjk.detect(poly, t1, seg, t2, p))
        assertFalse(gjk.detect(poly, t1, seg, t2))
        p.clear()
        assertFalse(gjk.detect(seg, t2, poly, t1, p))
        assertFalse(gjk.detect(seg, t2, poly, t1))
        p.clear()
        t1.translate(-1.0, 0.0)
        assertFalse(gjk.detect(poly, t1, seg, t2, p))
        assertFalse(gjk.detect(poly, t1, seg, t2))
        p.clear()
        assertFalse(gjk.detect(seg, t2, poly, t1, p))
        assertFalse(gjk.detect(seg, t2, poly, t1))
    }
fun gjkDistance() {
        setup()
        val s = Separation()
        val t1 = Transform()
        val t2 = Transform()
        lateinit var n: Vector2
        lateinit var p1: Vector2
        lateinit var p2: Vector2
        assertFalse(gjk.distance(poly, t1, seg, t2, s))
        s.clear()
        assertFalse(gjk.distance(seg, t2, poly, t1, s))
        s.clear()
        t1.translate(-1.0, 0.0)
        assertFalse(gjk.distance(poly, t1, seg, t2, s))
        s.clear()
        assertFalse(gjk.distance(seg, t2, poly, t1, s))
        s.clear()
        t2.translate(0.0, 1.3)
        assertTrue(gjk.distance(poly, t1, seg, t2, s))
        n = s.getNormal()
        p1 = s.getPoint1()
        p2 = s.getPoint2()
        assertFiniteClose(0.397, s.getDistance(), 1.0e-3)
        assertFiniteClose(0.480, n.x, 1.0e-3)
        assertFiniteClose(0.877, n.y, 1.0e-3)
        assertFiniteClose(-0.690, p1.x, 1.0e-3)
        assertFiniteClose(0.951, p1.y, 1.0e-3)
        assertFiniteClose(-0.500, p2.x, 1.0e-3)
        assertFiniteClose(1.300, p2.y, 1.0e-3)
        s.clear()
        assertTrue(gjk.distance(seg, t2, poly, t1, s))
        n = s.getNormal()
        p1 = s.getPoint1()
        p2 = s.getPoint2()
        assertFiniteClose(0.397, s.getDistance(), 1.0e-3)
        assertFiniteClose(-0.480, n.x, 1.0e-3)
        assertFiniteClose(-0.877, n.y, 1.0e-3)
        assertFiniteClose(-0.500, p1.x, 1.0e-3)
        assertFiniteClose(1.300, p1.y, 1.0e-3)
        assertFiniteClose(-0.690, p2.x, 1.0e-3)
        assertFiniteClose(0.951, p2.y, 1.0e-3)
        s.clear()
        t1.translate(-1.0, 0.0)
        assertTrue(gjk.distance(poly, t1, seg, t2, s))
        n = s.getNormal()
        p1 = s.getPoint1()
        p2 = s.getPoint2()
        assertFiniteClose(1.168, s.getDistance(), 1.0e-3)
        assertFiniteClose(0.809, n.x, 1.0e-3)
        assertFiniteClose(0.587, n.y, 1.0e-3)
        assertFiniteClose(-1.445, p1.x, 1.0e-3)
        assertFiniteClose(0.613, p1.y, 1.0e-3)
        assertFiniteClose(-0.500, p2.x, 1.0e-3)
        assertFiniteClose(1.3, p2.y, 1.0e-3)
        s.clear()
        assertTrue(gjk.distance(seg, t2, poly, t1, s))
        n = s.getNormal()
        p1 = s.getPoint1()
        p2 = s.getPoint2()
        assertFiniteClose(1.168, s.getDistance(), 1.0e-3)
        assertFiniteClose(-0.809, n.x, 1.0e-3)
        assertFiniteClose(-0.587, n.y, 1.0e-3)
        assertFiniteClose(-0.500, p1.x, 1.0e-3)
        assertFiniteClose(1.3, p1.y, 1.0e-3)
        assertFiniteClose(-1.445, p2.x, 1.0e-3)
        assertFiniteClose(0.613, p2.y, 1.0e-3)
    }
fun getClipManifold() {
        setup()
        val m = Manifold()
        val p = Penetration()
        val t1 = Transform()
        val t2 = Transform()
        lateinit var mp: ManifoldPoint
        lateinit var p1: Vector2
        gjk.detect(poly, t1, seg, t2, p)
        assertTrue(cmfs.getManifold(p, poly, t1, seg, t2, m))
        assertEquals(2, m.getPoints().size)
        p.clear()
        m.clear()
        gjk.detect(seg, t2, poly, t1, p)
        assertTrue(cmfs.getManifold(p, seg, t2, poly, t1, m))
        assertEquals(2, m.getPoints().size)
        p.clear()
        m.clear()
        sat.detect(poly, t1, seg, t2, p)
        assertTrue(cmfs.getManifold(p, poly, t1, seg, t2, m))
        assertEquals(2, m.getPoints().size)
        p.clear()
        m.clear()
        sat.detect(seg, t2, poly, t1, p)
        assertTrue(cmfs.getManifold(p, seg, t2, poly, t1, m))
        assertEquals(2, m.getPoints().size)
        t1.translate(-1.0, 0.0)
        p.clear()
        m.clear()
        gjk.detect(poly, t1, seg, t2, p)
        assertTrue(cmfs.getManifold(p, poly, t1, seg, t2, m))
        assertEquals(1, m.getPoints().size)
        mp = m.getPoints().get(0)
        p1 = mp.getPoint()
        assertFiniteClose(-0.500, p1.x, 1.0e-3)
        assertFiniteClose(0.000, p1.y, 1.0e-3)
        assertFiniteClose(0.404, mp.getDepth(), 1.0e-3)
        p.clear()
        m.clear()
        gjk.detect(seg, t2, poly, t1, p)
        assertTrue(cmfs.getManifold(p, seg, t2, poly, t1, m))
        assertEquals(1, m.getPoints().size)
        mp = m.getPoints().get(0)
        p1 = mp.getPoint()
        assertFiniteClose(-0.500, p1.x, 1.0e-3)
        assertFiniteClose(0.000, p1.y, 1.0e-3)
        assertFiniteClose(0.404, mp.getDepth(), 1.0e-3)
        p.clear()
        m.clear()
        sat.detect(poly, t1, seg, t2, p)
        assertTrue(cmfs.getManifold(p, poly, t1, seg, t2, m))
        assertEquals(1, m.getPoints().size)
        mp = m.getPoints().get(0)
        p1 = mp.getPoint()
        assertFiniteClose(-0.500, p1.x, 1.0e-3)
        assertFiniteClose(0.0, p1.y, 1.0e-3)
        assertFiniteClose(0.404, mp.getDepth(), 1.0e-3)
        p.clear()
        m.clear()
        sat.detect(seg, t2, poly, t1, p)
        assertTrue(cmfs.getManifold(p, seg, t2, poly, t1, m))
        assertEquals(1, m.getPoints().size)
        mp = m.getPoints().get(0)
        p1 = mp.getPoint()
        assertFiniteClose(-0.500, p1.x, 1.0e-3)
        assertFiniteClose(0.000, p1.y, 1.0e-3)
        assertFiniteClose(0.404, mp.getDepth(), 1.0e-3)
    }
fun noManifoldPoints() {
        setup()
        val m = Manifold()
        val p = Penetration()
        val t1 = Transform()
        val t2 = Transform()
        lateinit var mp1: ManifoldPoint
        lateinit var mp2: ManifoldPoint
        lateinit var p1: Vector2
        lateinit var p2: Vector2
        t1.translate(-1.0, 0.0)
        t2.translate(-0.6484375, -0.9375)
        assertTrue(sat.detect(poly, t1, seg, t2, p))
        assertTrue(cmfs.getManifold(p, poly, t1, seg, t2, m))
        mp1 = m.getPoints().get(0)
        mp2 = m.getPoints().get(1)
        p1 = mp1.getPoint()
        p2 = mp2.getPoint()
        assertFiniteClose(-0.690, p1.x, 1.0e-3)
        assertFiniteClose(-0.951, p1.y, 1.0e-3)
        assertFiniteClose(0.333, mp1.getDepth(), 1.0e-3)
        assertFiniteClose(-0.456, p2.x, 1.0e-3)
        assertFiniteClose(-0.628, p2.y, 1.0e-3)
        assertFiniteClose(0.270, mp2.getDepth(), 1.0e-3)
        assertTrue(sat.detect(seg, t2, poly, t1, p))
        assertTrue(cmfs.getManifold(p, seg, t2, poly, t1, m))
        mp1 = m.getPoints().get(0)
        mp2 = m.getPoints().get(1)
        p1 = mp1.getPoint()
        p2 = mp2.getPoint()
        assertFiniteClose(-0.690, p1.x, 1.0e-3)
        assertFiniteClose(-0.951, p1.y, 1.0e-3)
        assertFiniteClose(0.333, mp1.getDepth(), 1.0e-3)
        assertFiniteClose(-0.456, p2.x, 1.0e-3)
        assertFiniteClose(-0.628, p2.y, 1.0e-3)
        assertFiniteClose(0.270, mp2.getDepth(), 1.0e-3)
        assertTrue(gjk.detect(poly, t1, seg, t2, p))
        assertTrue(cmfs.getManifold(p, poly, t1, seg, t2, m))
        mp1 = m.getPoints().get(0)
        mp2 = m.getPoints().get(1)
        p1 = mp1.getPoint()
        p2 = mp2.getPoint()
        assertFiniteClose(-0.690, p1.x, 1.0e-3)
        assertFiniteClose(-0.951, p1.y, 1.0e-3)
        assertFiniteClose(0.333, mp1.getDepth(), 1.0e-3)
        assertFiniteClose(-0.456, p2.x, 1.0e-3)
        assertFiniteClose(-0.628, p2.y, 1.0e-3)
        assertFiniteClose(0.270, mp2.getDepth(), 1.0e-3)
        assertTrue(gjk.detect(seg, t2, poly, t1, p))
        assertTrue(cmfs.getManifold(p, seg, t2, poly, t1, m))
        mp1 = m.getPoints().get(0)
        mp2 = m.getPoints().get(1)
        p1 = mp1.getPoint()
        p2 = mp2.getPoint()
        assertFiniteClose(-0.690, p1.x, 1.0e-3)
        assertFiniteClose(-0.951, p1.y, 1.0e-3)
        assertFiniteClose(0.333, mp1.getDepth(), 1.0e-3)
        assertFiniteClose(-0.456, p2.x, 1.0e-3)
        assertFiniteClose(-0.628, p2.y, 1.0e-3)
        assertFiniteClose(0.270, mp2.getDepth(), 1.0e-3)
    }
fun testBadPoints1() {
        setup()
        val p = Geometry.createUnitCirclePolygon(5, 1.0)
        val s = Segment(Vector2(-0.5, 0.0), Vector2(0.5, 0.0))
        val t1 = Transform()
        val t2 = Transform()
        t1.translate(1.3671875, 0.8828125)
        t2.translate(0.171875, 1.0)
        val penetration = Penetration()
        assertTrue(gjk.detect(s, t2, p, t1, penetration))
        val manifold = Manifold()
        assertTrue(cmfs.getManifold(penetration, s, t2, p, t1, manifold))
        val mp1 = manifold.getPoints().get(0)
        val p1 = mp1.getPoint()
        assertFiniteClose(0.671, p1.x, 1.0e-3)
        assertFiniteClose(1.000, p1.y, 1.0e-3)
        assertFiniteClose(0.113, mp1.getDepth(), 1.0e-3)
    }
}
