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

class CircleCircleTest {
    private val sat = Sat()
    private val gjk = Gjk()
    private val cmfs = ClippingManifoldSolver()
    private lateinit var c1: Circle
    private lateinit var c2: Circle
    private fun setup() {
        c1 = Circle(1.0)
        c2 = Circle(0.5)
    }
    @Test
    fun detectSat() {
        setup()
        val p = Penetration()
        val t1 = Transform()
        val t2 = Transform()
        lateinit var n: Vector2
        assertTrue(sat.detect(c1, t1, c2, t2, p))
        assertTrue(sat.detect(c1, t1, c2, t2))
        n = p.getNormal()
        assertEquals(0.0, n.x)
        assertEquals(0.0, n.y)
        assertEquals(1.5, p.getDepth())
        p.clear()
        assertTrue(sat.detect(c2, t2, c1, t1, p))
        assertTrue(sat.detect(c2, t2, c1, t1))
        n = p.getNormal()
        assertEquals(0.0, n.x)
        assertEquals(0.0, n.y)
        assertEquals(1.5, p.getDepth())
        p.clear()
        t1.translate(-1.0, 0.0)
        assertTrue(sat.detect(c1, t1, c2, t2, p))
        assertTrue(sat.detect(c1, t1, c2, t2))
        n = p.getNormal()
        assertEquals(1.0, n.x)
        assertEquals(0.0, n.y)
        assertEquals(0.5, p.getDepth())
        p.clear()
        assertTrue(sat.detect(c2, t2, c1, t1, p))
        assertTrue(sat.detect(c2, t2, c1, t1))
        n = p.getNormal()
        assertEquals(-1.0, n.x)
        assertEquals(0.0, n.y)
        assertEquals(0.5, p.getDepth())
        p.clear()
        t2.translate(0.0, 1.5)
        assertFalse(sat.detect(c1, t1, c2, t2, p))
        assertFalse(sat.detect(c1, t1, c2, t2))
        p.clear()
        assertFalse(sat.detect(c2, t2, c1, t1, p))
        assertFalse(sat.detect(c2, t2, c1, t1))
        p.clear()
        t1.translate(-1.0, 0.0)
        assertFalse(sat.detect(c1, t1, c2, t2, p))
        assertFalse(sat.detect(c1, t1, c2, t2))
        p.clear()
        assertFalse(sat.detect(c2, t2, c1, t1, p))
        assertFalse(sat.detect(c2, t2, c1, t1))
    }
    @Test
    fun detectGjk() {
        setup()
        val p = Penetration()
        val t1 = Transform()
        val t2 = Transform()
        lateinit var n: Vector2
        assertTrue(gjk.detect(c1, t1, c2, t2, p))
        assertTrue(gjk.detect(c1, t1, c2, t2))
        n = p.getNormal()
        assertEquals(0.0, n.x)
        assertEquals(0.0, n.y)
        assertEquals(1.5, p.getDepth())
        p.clear()
        assertTrue(gjk.detect(c2, t2, c1, t1, p))
        assertTrue(gjk.detect(c2, t2, c1, t1))
        n = p.getNormal()
        assertEquals(0.0, n.x)
        assertEquals(0.0, n.y)
        assertEquals(1.5, p.getDepth())
        p.clear()
        t1.translate(-1.0, 0.0)
        assertTrue(gjk.detect(c1, t1, c2, t2, p))
        assertTrue(gjk.detect(c1, t1, c2, t2))
        n = p.getNormal()
        assertEquals(1.0, n.x)
        assertEquals(0.0, n.y)
        assertEquals(0.5, p.getDepth())
        p.clear()
        assertTrue(gjk.detect(c2, t2, c1, t1, p))
        assertTrue(gjk.detect(c2, t2, c1, t1))
        n = p.getNormal()
        assertEquals(-1.0, n.x)
        assertEquals(0.0, n.y)
        assertEquals(0.5, p.getDepth())
        p.clear()
        t2.translate(0.0, 1.5)
        assertFalse(gjk.detect(c1, t1, c2, t2, p))
        assertFalse(gjk.detect(c1, t1, c2, t2))
        p.clear()
        assertFalse(gjk.detect(c2, t2, c1, t1, p))
        assertFalse(gjk.detect(c2, t2, c1, t1))
        p.clear()
        t1.translate(-1.0, 0.0)
        assertFalse(gjk.detect(c1, t1, c2, t2, p))
        assertFalse(gjk.detect(c1, t1, c2, t2))
        p.clear()
        assertFalse(gjk.detect(c2, t2, c1, t1, p))
        assertFalse(gjk.detect(c2, t2, c1, t1))
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
        assertFalse(gjk.distance(c1, t1, c2, t2, s))
        s.clear()
        assertFalse(gjk.distance(c2, t2, c1, t1, s))
        s.clear()
        t1.translate(-1.0, 0.0)
        assertFalse(gjk.distance(c1, t1, c2, t2, s))
        s.clear()
        assertFalse(gjk.distance(c2, t2, c1, t1, s))
        s.clear()
        t2.translate(0.0, 1.5)
        assertTrue(gjk.distance(c1, t1, c2, t2, s))
        n = s.getNormal()
        p1 = s.getPoint1()
        p2 = s.getPoint2()
        assertFiniteClose(0.302, s.getDistance(), 1.0e-3)
        assertFiniteClose(0.554, n.x, 1.0e-3)
        assertFiniteClose(0.832, n.y, 1.0e-3)
        assertFiniteClose(-0.445, p1.x, 1.0e-3)
        assertFiniteClose(0.832, p1.y, 1.0e-3)
        assertFiniteClose(-0.277, p2.x, 1.0e-3)
        assertFiniteClose(1.083, p2.y, 1.0e-3)
        s.clear()
        assertTrue(gjk.distance(c2, t2, c1, t1, s))
        n = s.getNormal()
        p1 = s.getPoint1()
        p2 = s.getPoint2()
        assertFiniteClose(0.302, s.getDistance(), 1.0e-3)
        assertFiniteClose(-0.554, n.x, 1.0e-3)
        assertFiniteClose(-0.832, n.y, 1.0e-3)
        assertFiniteClose(-0.277, p1.x, 1.0e-3)
        assertFiniteClose(1.083, p1.y, 1.0e-3)
        assertFiniteClose(-0.445, p2.x, 1.0e-3)
        assertFiniteClose(0.832, p2.y, 1.0e-3)
        s.clear()
        t1.translate(-1.0, 0.0)
        assertTrue(gjk.distance(c1, t1, c2, t2, s))
        n = s.getNormal()
        p1 = s.getPoint1()
        p2 = s.getPoint2()
        assertFiniteClose(1.000, s.getDistance(), 1.0e-3)
        assertFiniteClose(0.800, n.x, 1.0e-3)
        assertFiniteClose(0.600, n.y, 1.0e-3)
        assertFiniteClose(-1.200, p1.x, 1.0e-3)
        assertFiniteClose(0.600, p1.y, 1.0e-3)
        assertFiniteClose(-0.400, p2.x, 1.0e-3)
        assertFiniteClose(1.200, p2.y, 1.0e-3)
        s.clear()
        assertTrue(gjk.distance(c2, t2, c1, t1, s))
        n = s.getNormal()
        p1 = s.getPoint1()
        p2 = s.getPoint2()
        assertFiniteClose(1.000, s.getDistance(), 1.0e-3)
        assertFiniteClose(-0.800, n.x, 1.0e-3)
        assertFiniteClose(-0.600, n.y, 1.0e-3)
        assertFiniteClose(-0.400, p1.x, 1.0e-3)
        assertFiniteClose(1.200, p1.y, 1.0e-3)
        assertFiniteClose(-1.200, p2.x, 1.0e-3)
        assertFiniteClose(0.600, p2.y, 1.0e-3)
    }
    @Test
    fun getClipManifold() {
        setup()
        val m = Manifold()
        val p = Penetration()
        val t1 = Transform()
        val t2 = Transform()
        lateinit var mp: ManifoldPoint
        lateinit var p1: Vector2
        gjk.detect(c1, t1, c2, t2, p)
        assertTrue(cmfs.getManifold(p, c1, t1, c2, t2, m))
        assertEquals(1, m.getPoints().size)
        p.clear()
        m.clear()
        gjk.detect(c2, t2, c1, t1, p)
        assertTrue(cmfs.getManifold(p, c2, t2, c1, t1, m))
        assertEquals(1, m.getPoints().size)
        p.clear()
        m.clear()
        sat.detect(c1, t1, c2, t2, p)
        assertTrue(cmfs.getManifold(p, c1, t1, c2, t2, m))
        assertEquals(1, m.getPoints().size)
        p.clear()
        m.clear()
        gjk.detect(c2, t2, c1, t1, p)
        assertTrue(cmfs.getManifold(p, c2, t2, c1, t1, m))
        assertEquals(1, m.getPoints().size)
        t1.translate(-1.0, 0.0)
        p.clear()
        m.clear()
        gjk.detect(c1, t1, c2, t2, p)
        assertTrue(cmfs.getManifold(p, c1, t1, c2, t2, m))
        assertEquals(1, m.getPoints().size)
        mp = m.getPoints().get(0)
        p1 = mp.getPoint()
        assertEquals(0.0, p1.x)
        assertEquals(0.0, p1.y)
        assertEquals(0.5, mp.getDepth())
        p.clear()
        m.clear()
        gjk.detect(c2, t2, c1, t1, p)
        assertTrue(cmfs.getManifold(p, c2, t2, c1, t1, m))
        assertEquals(1, m.getPoints().size)
        mp = m.getPoints().get(0)
        p1 = mp.getPoint()
        assertEquals(-0.5, p1.x)
        assertEquals(0.0, p1.y)
        assertEquals(0.5, mp.getDepth())
        p.clear()
        m.clear()
        sat.detect(c1, t1, c2, t2, p)
        assertTrue(cmfs.getManifold(p, c1, t1, c2, t2, m))
        assertEquals(1, m.getPoints().size)
        mp = m.getPoints().get(0)
        p1 = mp.getPoint()
        assertEquals(0.0, p1.x)
        assertEquals(0.0, p1.y)
        assertEquals(0.5, mp.getDepth())
        p.clear()
        m.clear()
        gjk.detect(c2, t2, c1, t1, p)
        assertTrue(cmfs.getManifold(p, c2, t2, c1, t1, m))
        assertEquals(1, m.getPoints().size)
        mp = m.getPoints().get(0)
        p1 = mp.getPoint()
        assertEquals(-0.5, p1.x)
        assertEquals(0.0, p1.y)
        assertEquals(0.5, mp.getDepth())
    }
}
