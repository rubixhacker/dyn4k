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

val CapsuleCapsuleTest by testSuite {
    test("detectSat") { CapsuleCapsuleTestFixture().run { detectSat() } }
    test("detectGjk") { CapsuleCapsuleTestFixture().run { detectGjk() } }
    test("gjkDistance") { CapsuleCapsuleTestFixture().run { gjkDistance() } }
    test("getClipManifold") { CapsuleCapsuleTestFixture().run { getClipManifold() } }
}

private class CapsuleCapsuleTestFixture  {
    private val sat = Sat()
    private val gjk = Gjk()
    private val cmfs = ClippingManifoldSolver()
    private lateinit var capsule1: Capsule
    private lateinit var capsule2: Capsule
    private fun setup() {
        capsule1 = Capsule(0.5, 1.0)
        capsule2 = Capsule(1.0, 0.5)
    }
fun detectSat() {
        setup()
        val p = Penetration()
        val t1 = Transform()
        val t2 = Transform()
        lateinit var n: Vector2
        assertTrue(sat.detect(capsule1, t1, capsule2, t2, p))
        assertTrue(sat.detect(capsule1, t1, capsule2, t2))
        n = p.getNormal()
        assertFiniteClose( 0.000, n.x, 1.0e-3)
        assertFiniteClose( 1.000, n.y, 1.0e-3)
        assertFiniteClose( 0.750, p.getDepth(), 1.0e-3)
        p.clear()
        assertTrue(sat.detect(capsule2, t2, capsule1, t1, p))
        assertTrue(sat.detect(capsule2, t2, capsule1, t1))
        n = p.getNormal()
        assertFiniteClose( 1.000, n.x, 1.0e-3)
        assertFiniteClose( 0.000, n.y, 1.0e-3)
        assertFiniteClose( 0.750, p.getDepth(), 1.0e-3)
        p.clear()
        t1.translate(-0.5, 0.0)
        assertTrue(sat.detect(capsule1, t1, capsule2, t2, p))
        assertTrue(sat.detect(capsule1, t1, capsule2, t2))
        n = p.getNormal()
        assertFiniteClose( 1.000, n.x, 1.0e-3)
        assertFiniteClose( 0.000, n.y, 1.0e-3)
        assertFiniteClose( 0.250, p.getDepth(), 1.0e-3)
        p.clear()
        assertTrue(sat.detect(capsule2, t2, capsule1, t1, p))
        assertTrue(sat.detect(capsule2, t2, capsule1, t1))
        n = p.getNormal()
        assertFiniteClose(-1.000, n.x, 1.0e-3)
        assertFiniteClose( 0.000, n.y, 1.0e-3)
        assertFiniteClose( 0.250, p.getDepth(), 1.0e-3)
        p.clear()
        t2.translate(0.0, 0.7)
        assertFalse(sat.detect(capsule1, t1, capsule2, t2, p))
        assertFalse(sat.detect(capsule1, t1, capsule2, t2))
        p.clear()
        assertFalse(sat.detect(capsule2, t2, capsule1, t1, p))
        assertFalse(sat.detect(capsule2, t2, capsule1, t1))
        p.clear()
        t2.translate(1.0, 0.0)
        assertFalse(sat.detect(capsule1, t1, capsule2, t2, p))
        assertFalse(sat.detect(capsule1, t1, capsule2, t2))
        p.clear()
        assertFalse(sat.detect(capsule2, t2, capsule1, t1, p))
        assertFalse(sat.detect(capsule2, t2, capsule1, t1))
    }
fun detectGjk() {
        setup()
        val p = Penetration()
        val t1 = Transform()
        val t2 = Transform()
        lateinit var n: Vector2
        assertTrue(gjk.detect(capsule1, t1, capsule2, t2, p))
        assertTrue(gjk.detect(capsule1, t1, capsule2, t2))
        n = p.getNormal()
        assertFiniteClose( 0.000, n.x, 1.0e-3)
        assertFiniteClose( 1.000, n.y, 1.0e-3)
        assertFiniteClose( 0.750, p.getDepth(), 1.0e-3)
        p.clear()
        assertTrue(gjk.detect(capsule2, t2, capsule1, t1, p))
        assertTrue(gjk.detect(capsule2, t2, capsule1, t1))
        n = p.getNormal()
        assertFiniteClose( 1.000, n.x, 1.0e-3)
        assertFiniteClose( 0.000, n.y, 1.0e-3)
        assertFiniteClose( 0.750, p.getDepth(), 1.0e-3)
        p.clear()
        t1.translate(-0.5, 0.0)
        assertTrue(gjk.detect(capsule1, t1, capsule2, t2, p))
        assertTrue(gjk.detect(capsule1, t1, capsule2, t2))
        n = p.getNormal()
        assertFiniteClose( 1.000, n.x, 1.0e-3)
        assertFiniteClose( 0.000, n.y, 1.0e-3)
        assertFiniteClose( 0.250, p.getDepth(), 1.0e-3)
        p.clear()
        assertTrue(gjk.detect(capsule2, t2, capsule1, t1, p))
        assertTrue(gjk.detect(capsule2, t2, capsule1, t1))
        n = p.getNormal()
        assertFiniteClose(-1.000, n.x, 1.0e-3)
        assertFiniteClose( 0.000, n.y, 1.0e-3)
        assertFiniteClose( 0.250, p.getDepth(), 1.0e-3)
        p.clear()
        t2.translate(0.0, 0.7)
        assertFalse(gjk.detect(capsule1, t1, capsule2, t2, p))
        assertFalse(gjk.detect(capsule1, t1, capsule2, t2))
        p.clear()
        assertFalse(gjk.detect(capsule2, t2, capsule1, t1, p))
        assertFalse(gjk.detect(capsule2, t2, capsule1, t1))
        p.clear()
        t2.translate(1.0, 0.0)
        assertFalse(gjk.detect(capsule1, t1, capsule2, t2, p))
        assertFalse(gjk.detect(capsule1, t1, capsule2, t2))
        p.clear()
        assertFalse(gjk.detect(capsule2, t2, capsule1, t1, p))
        assertFalse(gjk.detect(capsule2, t2, capsule1, t1))
    }
fun gjkDistance() {
        setup()
        val s = Separation()
        val t1 = Transform()
        val t2 = Transform()
        lateinit var n: Vector2
        lateinit var p1: Vector2
        lateinit var p2: Vector2
        assertFalse(gjk.distance(capsule1, t1, capsule2, t2, s))
        s.clear()
        assertFalse(gjk.distance(capsule2, t2, capsule1, t1, s))
        s.clear()
        t1.translate(-0.5, 0.0)
        assertFalse(gjk.distance(capsule1, t1, capsule2, t2, s))
        s.clear()
        assertFalse(gjk.distance(capsule2, t2, capsule1, t1, s))
        s.clear()
        t2.translate(0.0, 0.7)
        assertTrue(gjk.distance(capsule1, t1, capsule2, t2, s))
        n = s.getNormal()
        p1 = s.getPoint1()
        p2 = s.getPoint2()
        assertFiniteClose( 0.014, s.getDistance(), 1.0e-3)
        assertFiniteClose( 0.485, n.x, 1.0e-3)
        assertFiniteClose( 0.874, n.y, 1.0e-3)
        assertFiniteClose(-0.378, p1.x, 1.0e-3)
        assertFiniteClose( 0.468, p1.y, 1.0e-3)
        assertFiniteClose(-0.371, p2.x, 1.0e-3)
        assertFiniteClose( 0.481, p2.y, 1.0e-3)
        s.clear()
        assertTrue(gjk.distance(capsule2, t2, capsule1, t1, s))
        n = s.getNormal()
        p1 = s.getPoint1()
        p2 = s.getPoint2()
        assertFiniteClose( 0.014, s.getDistance(), 1.0e-3)
        assertFiniteClose(-0.485, n.x, 1.0e-3)
        assertFiniteClose(-0.874, n.y, 1.0e-3)
        assertFiniteClose(-0.371, p1.x, 1.0e-3)
        assertFiniteClose( 0.481, p1.y, 1.0e-3)
        assertFiniteClose(-0.378, p2.x, 1.0e-3)
        assertFiniteClose( 0.468, p2.y, 1.0e-3)
        s.clear()
        t2.translate(1.0, 0.0)
        assertTrue(gjk.distance(capsule1, t1, capsule2, t2, s))
        n = s.getNormal()
        p1 = s.getPoint1()
        p2 = s.getPoint2()
        assertFiniteClose( 0.828, s.getDistance(), 1.0e-3)
        assertFiniteClose( 0.940, n.x, 1.0e-3)
        assertFiniteClose( 0.338, n.y, 1.0e-3)
        assertFiniteClose(-0.264, p1.x, 1.0e-3)
        assertFiniteClose( 0.334, p1.y, 1.0e-3)
        assertFiniteClose( 0.514, p2.x, 1.0e-3)
        assertFiniteClose( 0.615, p2.y, 1.0e-3)
        s.clear()
        assertTrue(gjk.distance(capsule2, t2, capsule1, t1, s))
        n = s.getNormal()
        p1 = s.getPoint1()
        p2 = s.getPoint2()
        assertFiniteClose( 0.828, s.getDistance(), 1.0e-3)
        assertFiniteClose(-0.940, n.x, 1.0e-3)
        assertFiniteClose(-0.338, n.y, 1.0e-3)
        assertFiniteClose( 0.514, p1.x, 1.0e-3)
        assertFiniteClose( 0.615, p1.y, 1.0e-3)
        assertFiniteClose(-0.264, p2.x, 1.0e-3)
        assertFiniteClose( 0.334, p2.y, 1.0e-3)
    }
fun getClipManifold() {
        setup()
        val m = Manifold()
        val p = Penetration()
        val t1 = Transform()
        val t2 = Transform()
        lateinit var mp: ManifoldPoint
        lateinit var p1: Vector2
        gjk.detect(capsule1, t1, capsule2, t2, p)
        assertTrue(cmfs.getManifold(p, capsule1, t1, capsule2, t2, m))
        assertEquals(1, m.getPoints().size)
        p.clear()
        m.clear()
        gjk.detect(capsule2, t2, capsule1, t1, p)
        assertTrue(cmfs.getManifold(p, capsule2, t2, capsule1, t1, m))
        assertEquals(1, m.getPoints().size)
        p.clear()
        m.clear()
        sat.detect(capsule1, t1, capsule2, t2, p)
        assertTrue(cmfs.getManifold(p, capsule1, t1, capsule2, t2, m))
        assertEquals(1, m.getPoints().size)
        p.clear()
        m.clear()
        sat.detect(capsule2, t2, capsule1, t1, p)
        assertTrue(cmfs.getManifold(p, capsule2, t2, capsule1, t1, m))
        assertEquals(1, m.getPoints().size)
        t1.translate(-0.5, 0.0)
        p.clear()
        m.clear()
        gjk.detect(capsule1, t1, capsule2, t2, p)
        assertTrue(cmfs.getManifold(p, capsule1, t1, capsule2, t2, m))
        assertEquals(1, m.getPoints().size)
        mp = m.getPoints().get(0)
        p1 = mp.getPoint()
        assertFiniteClose(-0.500, p1.x, 1.0e-3)
        assertFiniteClose( 0.000, p1.y, 1.0e-3)
        assertFiniteClose( 0.250, mp.getDepth(), 1.0e-3)
        p.clear()
        m.clear()
        gjk.detect(capsule2, t2, capsule1, t1, p)
        assertTrue(cmfs.getManifold(p, capsule2, t2, capsule1, t1, m))
        assertEquals(1, m.getPoints().size)
        mp = m.getPoints().get(0)
        p1 = mp.getPoint()
        assertFiniteClose(-0.500, p1.x, 1.0e-3)
        assertFiniteClose( 0.000, p1.y, 1.0e-3)
        assertFiniteClose( 0.250, mp.getDepth(), 1.0e-3)
        p.clear()
        m.clear()
        sat.detect(capsule1, t1, capsule2, t2, p)
        assertTrue(cmfs.getManifold(p, capsule1, t1, capsule2, t2, m))
        assertEquals(1, m.getPoints().size)
        mp = m.getPoints().get(0)
        p1 = mp.getPoint()
        assertFiniteClose(-0.500, p1.x, 1.0e-3)
        assertFiniteClose( 0.000, p1.y, 1.0e-3)
        assertFiniteClose( 0.250, mp.getDepth(), 1.0e-3)
        p.clear()
        m.clear()
        sat.detect(capsule2, t2, capsule1, t1, p)
        assertTrue(cmfs.getManifold(p, capsule2, t2, capsule1, t1, m))
        assertEquals(1, m.getPoints().size)
        mp = m.getPoints().get(0)
        p1 = mp.getPoint()
        assertFiniteClose(-0.500, p1.x, 1.0e-3)
        assertFiniteClose( 0.000, p1.y, 1.0e-3)
        assertFiniteClose( 0.250, mp.getDepth(), 1.0e-3)
    }
}
