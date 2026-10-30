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

val CircleSegmentTest by testSuite {
    test("detectSat") { CircleSegmentTestFixture().run { detectSat() } }
    test("detectGjk") { CircleSegmentTestFixture().run { detectGjk() } }
    test("gjkDistance") { CircleSegmentTestFixture().run { gjkDistance() } }
    test("getClipManifold") { CircleSegmentTestFixture().run { getClipManifold() } }
}

private class CircleSegmentTestFixture  {
    private val sat = Sat()
    private val gjk = Gjk()
    private val cmfs = ClippingManifoldSolver()
    private lateinit var circ: Circle
    private lateinit var seg: Segment
    private fun setup() {
        circ = Circle(1.0)
        seg = Segment(Vector2(-0.5, 0.0), Vector2(0.5, 0.0))
    }
fun detectSat() {
        setup()
        val p = Penetration()
        val t1 = Transform()
        val t2 = Transform()
        lateinit var n: Vector2
        assertTrue(sat.detect(circ, t1, seg, t2, p))
        assertTrue(sat.detect(circ, t1, seg, t2))
        n = p.getNormal()
        assertFiniteClose(0.0, n.x, 1.0e-10)
        assertFiniteClose(1.0, n.y, 1.0e-10)
        assertFiniteClose(1.0, p.getDepth(), 1.0e-10)
        p.clear()
        assertTrue(sat.detect(seg, t2, circ, t1, p))
        assertTrue(sat.detect(seg, t2, circ, t1))
        n = p.getNormal()
        assertFiniteClose(0.0, n.x, 1.0e-10)
        assertFiniteClose(1.0, n.y, 1.0e-10)
        assertFiniteClose(1.0, p.getDepth(), 1.0e-10)
        p.clear()
        t1.translate(-1.0, 0.0)
        assertTrue(sat.detect(circ, t1, seg, t2, p))
        assertTrue(sat.detect(circ, t1, seg, t2))
        n = p.getNormal()
        assertEquals(1.0, n.x)
        assertEquals(0.0, n.y)
        assertEquals(0.5, p.getDepth())
        p.clear()
        assertTrue(sat.detect(seg, t2, circ, t1, p))
        assertTrue(sat.detect(seg, t2, circ, t1))
        n = p.getNormal()
        assertEquals(-1.0, n.x)
        assertEquals(0.0, kotlin.math.abs(n.y))
        assertEquals(0.5, p.getDepth())
        p.clear()
        t2.translate(0.0, 0.9)
        assertFalse(sat.detect(circ, t1, seg, t2, p))
        assertFalse(sat.detect(circ, t1, seg, t2))
        p.clear()
        assertFalse(sat.detect(seg, t2, circ, t1, p))
        assertFalse(sat.detect(seg, t2, circ, t1))
        p.clear()
        t1.translate(-1.0, 0.0)
        assertFalse(sat.detect(circ, t1, seg, t2, p))
        assertFalse(sat.detect(circ, t1, seg, t2))
        p.clear()
        assertFalse(sat.detect(seg, t2, circ, t1, p))
        assertFalse(sat.detect(seg, t2, circ, t1))
    }
fun detectGjk() {
        setup()
        val p = Penetration()
        val t1 = Transform()
        val t2 = Transform()
        lateinit var n: Vector2
        assertTrue(gjk.detect(circ, t1, seg, t2, p))
        assertTrue(gjk.detect(circ, t1, seg, t2))
        n = p.getNormal()
        assertFiniteClose(1.0, p.getDepth(), 1.0e-10)
        assertFiniteClose(0.0, n.x, 1.0e-10)
        assertFiniteClose(1.0, n.y, 1.0e-10)
        p.clear()
        assertTrue(gjk.detect(seg, t2, circ, t1, p))
        assertTrue(gjk.detect(seg, t2, circ, t1))
        n = p.getNormal()
        assertFiniteClose(1.0, p.getDepth(), 1.0e-10)
        assertFiniteClose(0.0, n.x, 1.0e-10)
        assertFiniteClose(-1.0, n.y, 1.0e-10)
        p.clear()
        t1.translate(-1.0, 0.0)
        assertTrue(gjk.detect(circ, t1, seg, t2, p))
        assertTrue(gjk.detect(circ, t1, seg, t2))
        n = p.getNormal()
        assertFiniteClose(0.5, p.getDepth(), 1.0e-8)
        assertFiniteClose(1.0, n.x, 1.0e-8)
        assertFiniteClose(0.0, n.y, 1.0e-4)
        p.clear()
        assertTrue(gjk.detect(seg, t2, circ, t1, p))
        assertTrue(gjk.detect(seg, t2, circ, t1))
        n = p.getNormal()
        assertFiniteClose(0.5, p.getDepth(), 1.0e-8)
        assertFiniteClose(-1.0, n.x, 1.0e-8)
        assertFiniteClose(0.0, n.y, 1.0e-4)
        p.clear()
        t2.translate(0.0, 0.9)
        assertFalse(gjk.detect(circ, t1, seg, t2, p))
        assertFalse(gjk.detect(circ, t1, seg, t2))
        p.clear()
        assertFalse(gjk.detect(seg, t2, circ, t1, p))
        assertFalse(gjk.detect(seg, t2, circ, t1))
        p.clear()
        t1.translate(-1.0, 0.0)
        assertFalse(gjk.detect(circ, t1, seg, t2, p))
        assertFalse(gjk.detect(circ, t1, seg, t2))
        p.clear()
        assertFalse(gjk.detect(seg, t2, circ, t1, p))
        assertFalse(gjk.detect(seg, t2, circ, t1))
    }
fun gjkDistance() {
        setup()
        val s = Separation()
        val t1 = Transform()
        val t2 = Transform()
        lateinit var n: Vector2
        lateinit var p1: Vector2
        lateinit var p2: Vector2
        assertFalse(gjk.distance(circ, t1, seg, t2, s))
        s.clear()
        assertFalse(gjk.distance(seg, t2, circ, t1, s))
        s.clear()
        t1.translate(-1.0, 0.0)
        assertFalse(gjk.distance(circ, t1, seg, t2, s))
        s.clear()
        assertFalse(gjk.distance(seg, t2, circ, t1, s))
        s.clear()
        t2.translate(0.0, 0.9)
        assertTrue(gjk.distance(circ, t1, seg, t2, s))
        assertFiniteClose(0.029, s.getDistance(), 1.0e-3)
        n = s.getNormal()
        p1 = s.getPoint1()
        p2 = s.getPoint2()
        assertFiniteClose(0.485, n.x, 1.0e-3)
        assertFiniteClose(0.874, n.y, 1.0e-3)
        assertFiniteClose(-0.514, p1.x, 1.0e-3)
        assertFiniteClose(0.874, p1.y, 1.0e-3)
        assertFiniteClose(-0.500, p2.x, 1.0e-3)
        assertFiniteClose(0.900, p2.y, 1.0e-3)
        s.clear()
        assertTrue(gjk.distance(seg, t2, circ, t1, s))
        assertFiniteClose(0.029, s.getDistance(), 1.0e-3)
        n = s.getNormal()
        p1 = s.getPoint1()
        p2 = s.getPoint2()
        assertFiniteClose(-0.485, n.x, 1.0e-3)
        assertFiniteClose(-0.874, n.y, 1.0e-3)
        assertFiniteClose(-0.500, p1.x, 1.0e-3)
        assertFiniteClose(0.900, p1.y, 1.0e-3)
        assertFiniteClose(-0.514, p2.x, 1.0e-3)
        assertFiniteClose(0.874, p2.y, 1.0e-3)
        s.clear()
        t1.translate(-1.0, 0.0)
        assertTrue(gjk.distance(circ, t1, seg, t2, s))
        assertFiniteClose(0.749, s.getDistance(), 1.0e-3)
        n = s.getNormal()
        p1 = s.getPoint1()
        p2 = s.getPoint2()
        assertFiniteClose(0.857, n.x, 1.0e-3)
        assertFiniteClose(0.514, n.y, 1.0e-3)
        assertFiniteClose(-1.142, p1.x, 1.0e-3)
        assertFiniteClose(0.514, p1.y, 1.0e-3)
        assertFiniteClose(-0.500, p2.x, 1.0e-3)
        assertFiniteClose(0.900, p2.y, 1.0e-3)
        s.clear()
        assertTrue(gjk.distance(seg, t2, circ, t1, s))
        assertFiniteClose(0.749, s.getDistance(), 1.0e-3)
        n = s.getNormal()
        p1 = s.getPoint1()
        p2 = s.getPoint2()
        assertFiniteClose(-0.857, n.x, 1.0e-3)
        assertFiniteClose(-0.514, n.y, 1.0e-3)
        assertFiniteClose(-0.500, p1.x, 1.0e-3)
        assertFiniteClose(0.900, p1.y, 1.0e-3)
        assertFiniteClose(-1.142, p2.x, 1.0e-3)
        assertFiniteClose(0.514, p2.y, 1.0e-3)
    }
fun getClipManifold() {
        setup()
        val m = Manifold()
        val p = Penetration()
        val t1 = Transform()
        val t2 = Transform()
        lateinit var mp: ManifoldPoint
        lateinit var p1: Vector2
        gjk.detect(circ, t1, seg, t2, p)
        assertTrue(cmfs.getManifold(p, circ, t1, seg, t2, m))
        assertEquals(1, m.getPoints().size)
        p.clear()
        m.clear()
        gjk.detect(seg, t2, circ, t1, p)
        assertTrue(cmfs.getManifold(p, seg, t2, circ, t1, m))
        assertEquals(1, m.getPoints().size)
        p.clear()
        m.clear()
        sat.detect(circ, t1, seg, t2, p)
        assertTrue(cmfs.getManifold(p, circ, t1, seg, t2, m))
        assertEquals(1, m.getPoints().size)
        p.clear()
        m.clear()
        sat.detect(seg, t2, circ, t1, p)
        assertTrue(cmfs.getManifold(p, seg, t2, circ, t1, m))
        assertEquals(1, m.getPoints().size)
        t1.translate(-1.0, 0.0)
        p.clear()
        m.clear()
        gjk.detect(circ, t1, seg, t2, p)
        assertTrue(cmfs.getManifold(p, circ, t1, seg, t2, m))
        assertEquals(1, m.getPoints().size)
        mp = m.getPoints().get(0)
        p1 = mp.getPoint()
        assertFiniteClose(0.0, p1.x, 1.0e-4)
        assertFiniteClose(0.0, p1.y, 1.0e-4)
        assertFiniteClose(0.5, mp.getDepth(), 1.0e-4)
        p.clear()
        m.clear()
        gjk.detect(seg, t2, circ, t1, p)
        assertTrue(cmfs.getManifold(p, seg, t2, circ, t1, m))
        assertEquals(1, m.getPoints().size)
        mp = m.getPoints().get(0)
        p1 = mp.getPoint()
        assertFiniteClose(0.0, p1.x, 1.0e-4)
        assertFiniteClose(0.0, p1.y, 1.0e-4)
        assertFiniteClose(0.5, mp.getDepth(), 1.0e-4)
        p.clear()
        m.clear()
        sat.detect(circ, t1, seg, t2, p)
        assertTrue(cmfs.getManifold(p, circ, t1, seg, t2, m))
        assertEquals(1, m.getPoints().size)
        mp = m.getPoints().get(0)
        p1 = mp.getPoint()
        assertEquals(0.0, p1.x)
        assertEquals(0.0, p1.y)
        assertEquals(0.5, mp.getDepth())
        p.clear()
        m.clear()
        sat.detect(seg, t2, circ, t1, p)
        assertTrue(cmfs.getManifold(p, seg, t2, circ, t1, m))
        assertEquals(1, m.getPoints().size)
        mp = m.getPoints().get(0)
        p1 = mp.getPoint()
        assertEquals(0.0, p1.x)
        assertEquals(0.0, p1.y)
        assertEquals(0.5, mp.getDepth())
    }
}
