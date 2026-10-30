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

val EllipseEllipseTest by testSuite {
    test("detectSat") { EllipseEllipseTestFixture().run { detectSat() } }
    test("detectGjk") { EllipseEllipseTestFixture().run { detectGjk() } }
    test("gjkDistance") { EllipseEllipseTestFixture().run { gjkDistance() } }
    test("getClipManifold") { EllipseEllipseTestFixture().run { getClipManifold() } }
    test("falsePositiveCollision") { EllipseEllipseTestFixture().run { falsePositiveCollision() } }
    test("falseNegativeDistance") { EllipseEllipseTestFixture().run { falseNegativeDistance() } }
}

private class EllipseEllipseTestFixture  {
    private val sat = Sat()
    private val gjk = Gjk()
    private val cmfs = ClippingManifoldSolver()
    private lateinit var c1: Ellipse
    private lateinit var c2: Ellipse
    private fun setup() {
        c1 = Ellipse(1.0, 0.5)
        c2 = Ellipse(0.5, 1.0)
    }
fun detectSat() {
        setup()
        val p = Penetration()
        val t1 = Transform()
        val t2 = Transform()
        assertFailsWith<UnsupportedOperationException> { sat.detect(c1, t1, c2, t2, p) }
    }
fun detectGjk() {
        setup()
        val p = Penetration()
        val t1 = Transform()
        val t2 = Transform()
        lateinit var n: Vector2
        assertTrue(gjk.detect(c1, t1, c2, t2, p))
        assertTrue(gjk.detect(c1, t1, c2, t2))
        n = p.getNormal()
        assertFiniteClose(-1.000, n.x, 1.0e-3)
        assertFiniteClose( 0.000, n.y, 1.0e-3)
        assertFiniteClose( 0.750, p.getDepth(), 1.0e-3)
        p.clear()
        assertTrue(gjk.detect(c2, t2, c1, t1, p))
        assertTrue(gjk.detect(c2, t2, c1, t1))
        n = p.getNormal()
        assertFiniteClose(-1.000, n.x, 1.0e-3)
        assertFiniteClose( 0.000, n.y, 1.0e-3)
        assertFiniteClose( 0.750, p.getDepth(), 1.0e-3)
        p.clear()
        t1.translate(-0.5, 0.0)
        assertTrue(gjk.detect(c1, t1, c2, t2, p))
        assertTrue(gjk.detect(c1, t1, c2, t2))
        n = p.getNormal()
        assertFiniteClose( 1.000, n.x, 1.0e-3)
        assertFiniteClose( 0.000, n.y, 1.0e-3)
        assertFiniteClose( 0.250, p.getDepth(), 1.0e-3)
        p.clear()
        assertTrue(gjk.detect(c2, t2, c1, t1, p))
        assertTrue(gjk.detect(c2, t2, c1, t1))
        n = p.getNormal()
        assertFiniteClose(-1.000, n.x, 1.0e-3)
        assertFiniteClose( 0.000, n.y, 1.0e-3)
        assertFiniteClose( 0.250, p.getDepth(), 1.0e-3)
        p.clear()
        t2.translate(0.0, -0.62)
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
        t1.translate(-0.5, 0.0)
        assertFalse(gjk.distance(c1, t1, c2, t2, s))
        s.clear()
        assertFalse(gjk.distance(c2, t2, c1, t1, s))
        s.clear()
        t2.translate(0.0, -0.62)
        assertTrue(gjk.distance(c1, t1, c2, t2, s))
        n = s.getNormal()
        p1 = s.getPoint1()
        p2 = s.getPoint2()
        assertFiniteClose( 0.008, s.getDistance(), 1.0e-3)
        assertFiniteClose( 0.583, n.x, 1.0e-3)
        assertFiniteClose(-0.812, n.y, 1.0e-3)
        assertFiniteClose(-0.089, p1.x, 1.0e-3)
        assertFiniteClose(-0.142, p1.y, 1.0e-3)
        assertFiniteClose(-0.084, p2.x, 1.0e-3)
        assertFiniteClose(-0.149, p2.y, 1.0e-3)
        s.clear()
        assertTrue(gjk.distance(c2, t2, c1, t1, s))
        n = s.getNormal()
        p1 = s.getPoint1()
        p2 = s.getPoint2()
        assertFiniteClose( 0.008, s.getDistance(), 1.0e-3)
        assertFiniteClose(-0.583, n.x, 1.0e-3)
        assertFiniteClose( 0.812, n.y, 1.0e-3)
        assertFiniteClose(-0.084, p1.x, 1.0e-3)
        assertFiniteClose(-0.149, p1.y, 1.0e-3)
        assertFiniteClose(-0.089, p2.x, 1.0e-3)
        assertFiniteClose(-0.142, p2.y, 1.0e-3)
        s.clear()
        t1.translate(-1.0, 0.0)
        assertTrue(gjk.distance(c1, t1, c2, t2, s))
        n = s.getNormal()
        p1 = s.getPoint1()
        p2 = s.getPoint2()
        assertFiniteClose( 0.853, s.getDistance(), 1.0e-3)
        assertFiniteClose( 0.942, n.x, 1.0e-3)
        assertFiniteClose(-0.335, n.y, 1.0e-3)
        assertFiniteClose(-1.007, p1.x, 1.0e-3)
        assertFiniteClose(-0.043, p1.y, 1.0e-3)
        assertFiniteClose(-0.203, p2.x, 1.0e-3)
        assertFiniteClose(-0.329, p2.y, 1.0e-3)
        s.clear()
        assertTrue(gjk.distance(c2, t2, c1, t1, s))
        n = s.getNormal()
        p1 = s.getPoint1()
        p2 = s.getPoint2()
        assertFiniteClose( 0.853, s.getDistance(), 1.0e-3)
        assertFiniteClose(-0.942, n.x, 1.0e-3)
        assertFiniteClose( 0.335, n.y, 1.0e-3)
        assertFiniteClose(-0.203, p1.x, 1.0e-3)
        assertFiniteClose(-0.329, p1.y, 1.0e-3)
        assertFiniteClose(-1.007, p2.x, 1.0e-3)
        assertFiniteClose(-0.043, p2.y, 1.0e-3)
    }
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
        t1.translate(-0.65, 0.0)
        p.clear()
        m.clear()
        gjk.detect(c1, t1, c2, t2, p)
        assertTrue(cmfs.getManifold(p, c1, t1, c2, t2, m))
        assertEquals(1, m.getPoints().size)
        mp = m.getPoints().get(0)
        p1 = mp.getPoint()
        assertFiniteClose(-0.150, p1.x, 1.0e-3)
        assertFiniteClose( 0.000, p1.y, 1.0e-3)
        assertFiniteClose( 0.100, mp.getDepth(), 1.0e-3)
        p.clear()
        m.clear()
        gjk.detect(c2, t2, c1, t1, p)
        assertTrue(cmfs.getManifold(p, c2, t2, c1, t1, m))
        assertEquals(1, m.getPoints().size)
        mp = m.getPoints().get(0)
        p1 = mp.getPoint()
        assertFiniteClose(-0.249, p1.x, 1.0e-3)
        assertFiniteClose( 0.000, p1.y, 1.0e-3)
        assertFiniteClose( 0.100, mp.getDepth(), 1.0e-3)
    }
fun falsePositiveCollision() {
        setup()
        val p = Penetration()
        val t1 = Transform()
        val t2 = Transform()
        t2.translate(-0.5, -0.6)
        assertTrue(gjk.detect(c1, t1, c2, t2, p))
    }
fun falseNegativeDistance() {
        setup()
        val s = Separation()
        val t1 = Transform()
        val t2 = Transform()
        t2.translate(-0.5, -0.6)
        assertFalse(gjk.distance(c1, t1, c2, t2, s))
    }
}
