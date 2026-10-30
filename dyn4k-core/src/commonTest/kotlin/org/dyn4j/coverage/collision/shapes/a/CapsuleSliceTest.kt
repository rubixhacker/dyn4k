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

val CapsuleSliceTest by testSuite {
    test("detectSat") { CapsuleSliceTestFixture().run { detectSat() } }
    test("detectGjk") { CapsuleSliceTestFixture().run { detectGjk() } }
    test("gjkDistance") { CapsuleSliceTestFixture().run { gjkDistance() } }
    test("getClipManifold") { CapsuleSliceTestFixture().run { getClipManifold() } }
}

private class CapsuleSliceTestFixture  {
    private val sat = Sat()
    private val gjk = Gjk()
    private val cmfs = ClippingManifoldSolver()
    private lateinit var capsule: Capsule
    private lateinit var slice: Slice
    private fun setup() {
        capsule = Capsule(1.0, 0.5)
        slice = Slice(0.5, radians(50.0))
    }
fun detectSat() {
        setup()
        val p = Penetration()
        val t1 = Transform()
        val t2 = Transform()
        lateinit var n: Vector2
        assertTrue(sat.detect(capsule, t1, slice, t2, p))
        assertTrue(sat.detect(capsule, t1, slice, t2))
        n = p.getNormal()
        assertFiniteClose( 0.422, n.x, 1.0e-3)
        assertFiniteClose(-0.906, n.y, 1.0e-3)
        assertFiniteClose( 0.355, p.getDepth(), 1.0e-3)
        p.clear()
        assertTrue(sat.detect(slice, t2, capsule, t1, p))
        assertTrue(sat.detect(slice, t2, capsule, t1))
        n = p.getNormal()
        assertFiniteClose(-0.422, n.x, 1.0e-3)
        assertFiniteClose( 0.906, n.y, 1.0e-3)
        assertFiniteClose( 0.355, p.getDepth(), 1.0e-3)
        p.clear()
        t1.translate(-0.25, 0.0)
        assertTrue(sat.detect(capsule, t1, slice, t2, p))
        assertTrue(sat.detect(capsule, t1, slice, t2))
        n = p.getNormal()
        assertFiniteClose( 0.422, n.x, 1.0e-3)
        assertFiniteClose(-0.906, n.y, 1.0e-3)
        assertFiniteClose( 0.249, p.getDepth(), 1.0e-3)
        p.clear()
        assertTrue(sat.detect(slice, t2, capsule, t1, p))
        assertTrue(sat.detect(slice, t2, capsule, t1))
        n = p.getNormal()
        assertFiniteClose(-0.422, n.x, 1.0e-3)
        assertFiniteClose( 0.906, n.y, 1.0e-3)
        assertFiniteClose( 0.249, p.getDepth(), 1.0e-3)
        p.clear()
        t2.translate(0.0, 0.3)
        assertFalse(sat.detect(capsule, t1, slice, t2, p))
        assertFalse(sat.detect(capsule, t1, slice, t2))
        p.clear()
        assertFalse(sat.detect(slice, t2, capsule, t1, p))
        assertFalse(sat.detect(slice, t2, capsule, t1))
        p.clear()
        t2.translate(1.0, 0.0)
        assertFalse(sat.detect(capsule, t1, slice, t2, p))
        assertFalse(sat.detect(capsule, t1, slice, t2))
        p.clear()
        assertFalse(sat.detect(slice, t2, capsule, t1, p))
        assertFalse(sat.detect(slice, t2, capsule, t1))
    }
fun detectGjk() {
        setup()
        val p = Penetration()
        val t1 = Transform()
        val t2 = Transform()
        lateinit var n: Vector2
        assertTrue(gjk.detect(capsule, t1, slice, t2, p))
        assertTrue(gjk.detect(capsule, t1, slice, t2))
        n = p.getNormal()
        assertFiniteClose( 0.422, n.x, 1.0e-3)
        assertFiniteClose(-0.906, n.y, 1.0e-3)
        assertFiniteClose( 0.355, p.getDepth(), 1.0e-3)
        p.clear()
        assertTrue(gjk.detect(slice, t2, capsule, t1, p))
        assertTrue(gjk.detect(slice, t2, capsule, t1))
        n = p.getNormal()
        assertFiniteClose(-0.422, n.x, 1.0e-3)
        assertFiniteClose( 0.906, n.y, 1.0e-3)
        assertFiniteClose( 0.355, p.getDepth(), 1.0e-3)
        p.clear()
        t1.translate(-0.25, 0.0)
        assertTrue(gjk.detect(capsule, t1, slice, t2, p))
        assertTrue(gjk.detect(capsule, t1, slice, t2))
        n = p.getNormal()
        assertFiniteClose( 0.981, n.x, 1.0e-3)
        assertFiniteClose( 0.190, n.y, 1.0e-3)
        assertFiniteClose( 0.250, p.getDepth(), 1.0e-3)
        p.clear()
        assertTrue(gjk.detect(slice, t2, capsule, t1, p))
        assertTrue(gjk.detect(slice, t2, capsule, t1))
        n = p.getNormal()
        assertFiniteClose(-0.981, n.x, 1.0e-3)
        assertFiniteClose(-0.190, n.y, 1.0e-3)
        assertFiniteClose( 0.250, p.getDepth(), 1.0e-3)
        p.clear()
        t2.translate(0.0, 0.3)
        assertFalse(gjk.detect(capsule, t1, slice, t2, p))
        assertFalse(gjk.detect(capsule, t1, slice, t2))
        p.clear()
        assertFalse(gjk.detect(slice, t2, capsule, t1, p))
        assertFalse(gjk.detect(slice, t2, capsule, t1))
        p.clear()
        t2.translate(1.0, 0.0)
        assertFalse(gjk.detect(capsule, t1, slice, t2, p))
        assertFalse(gjk.detect(capsule, t1, slice, t2))
        p.clear()
        assertFalse(gjk.detect(slice, t2, capsule, t1, p))
        assertFalse(gjk.detect(slice, t2, capsule, t1))
    }
fun gjkDistance() {
        setup()
        val s = Separation()
        val t1 = Transform()
        val t2 = Transform()
        lateinit var n: Vector2
        lateinit var p1: Vector2
        lateinit var p2: Vector2
        assertFalse(gjk.distance(capsule, t1, slice, t2, s))
        s.clear()
        assertFalse(gjk.distance(slice, t2, capsule, t1, s))
        s.clear()
        t1.translate(-0.25, 0.0)
        assertFalse(gjk.distance(capsule, t1, slice, t2, s))
        s.clear()
        assertFalse(gjk.distance(slice, t2, capsule, t1, s))
        s.clear()
        t2.translate(0.0, 0.3)
        assertTrue(gjk.distance(capsule, t1, slice, t2, s))
        n = s.getNormal()
        p1 = s.getPoint1()
        p2 = s.getPoint2()
        assertFiniteClose( 0.021, s.getDistance(), 1.0e-3)
        assertFiniteClose( 0.422, n.x, 1.0e-3)
        assertFiniteClose( 0.906, n.y, 1.0e-3)
        assertFiniteClose( 0.105, p1.x, 1.0e-3)
        assertFiniteClose( 0.226, p1.y, 1.0e-3)
        assertFiniteClose( 0.114, p2.x, 1.0e-3)
        assertFiniteClose( 0.246, p2.y, 1.0e-3)
        s.clear()
        assertTrue(gjk.distance(slice, t2, capsule, t1, s))
        n = s.getNormal()
        p1 = s.getPoint1()
        p2 = s.getPoint2()
        assertFiniteClose( 0.021, s.getDistance(), 1.0e-3)
        assertFiniteClose(-0.422, n.x, 1.0e-3)
        assertFiniteClose(-0.906, n.y, 1.0e-3)
        assertFiniteClose( 0.114, p1.x, 1.0e-3)
        assertFiniteClose( 0.246, p1.y, 1.0e-3)
        assertFiniteClose( 0.105, p2.x, 1.0e-3)
        assertFiniteClose( 0.226, p2.y, 1.0e-3)
        s.clear()
        t2.translate(1.0, 0.0)
        assertTrue(gjk.distance(capsule, t1, slice, t2, s))
        n = s.getNormal()
        p1 = s.getPoint1()
        p2 = s.getPoint2()
        assertFiniteClose( 0.794, s.getDistance(), 1.0e-3)
        assertFiniteClose( 0.957, n.x, 1.0e-3)
        assertFiniteClose( 0.287, n.y, 1.0e-3)
        assertFiniteClose( 0.239, p1.x, 1.0e-3)
        assertFiniteClose( 0.071, p1.y, 1.0e-3)
        assertFiniteClose( 1.000, p2.x, 1.0e-3)
        assertFiniteClose( 0.300, p2.y, 1.0e-3)
        s.clear()
        assertTrue(gjk.distance(slice, t2, capsule, t1, s))
        n = s.getNormal()
        p1 = s.getPoint1()
        p2 = s.getPoint2()
        assertFiniteClose( 0.794, s.getDistance(), 1.0e-3)
        assertFiniteClose(-0.957, n.x, 1.0e-3)
        assertFiniteClose(-0.287, n.y, 1.0e-3)
        assertFiniteClose( 1.000, p1.x, 1.0e-3)
        assertFiniteClose( 0.300, p1.y, 1.0e-3)
        assertFiniteClose( 0.239, p2.x, 1.0e-3)
        assertFiniteClose( 0.071, p2.y, 1.0e-3)
    }
fun getClipManifold() {
        setup()
        val m = Manifold()
        val p = Penetration()
        val t1 = Transform()
        val t2 = Transform()
        lateinit var mp: ManifoldPoint
        lateinit var p1: Vector2
        gjk.detect(capsule, t1, slice, t2, p)
        assertTrue(cmfs.getManifold(p, capsule, t1, slice, t2, m))
        assertEquals(1, m.getPoints().size)
        p.clear()
        m.clear()
        gjk.detect(slice, t2, capsule, t1, p)
        assertTrue(cmfs.getManifold(p, slice, t2, capsule, t1, m))
        assertEquals(1, m.getPoints().size)
        p.clear()
        m.clear()
        sat.detect(capsule, t1, slice, t2, p)
        assertTrue(cmfs.getManifold(p, capsule, t1, slice, t2, m))
        assertEquals(1, m.getPoints().size)
        p.clear()
        m.clear()
        sat.detect(slice, t2, capsule, t1, p)
        assertTrue(cmfs.getManifold(p, slice, t2, capsule, t1, m))
        assertEquals(1, m.getPoints().size)
        t1.translate(-0.25, 0.0)
        p.clear()
        m.clear()
        gjk.detect(capsule, t1, slice, t2, p)
        assertTrue(cmfs.getManifold(p, capsule, t1, slice, t2, m))
        assertEquals(1, m.getPoints().size)
        mp = m.getPoints().get(0)
        p1 = mp.getPoint()
        assertFiniteClose( 0.245, p1.x, 1.0e-3)
        assertFiniteClose( 0.047, p1.y, 1.0e-3)
        assertFiniteClose( 0.250, mp.getDepth(), 1.0e-3)
        p.clear()
        m.clear()
        gjk.detect(slice, t2, capsule, t1, p)
        assertTrue(cmfs.getManifold(p, slice, t2, capsule, t1, m))
        assertEquals(1, m.getPoints().size)
        mp = m.getPoints().get(0)
        p1 = mp.getPoint()
        assertFiniteClose( 0.245, p1.x, 1.0e-3)
        assertFiniteClose( 0.047, p1.y, 1.0e-3)
        assertFiniteClose( 0.250, mp.getDepth(), 1.0e-3)
        p.clear()
        m.clear()
        sat.detect(capsule, t1, slice, t2, p)
        assertTrue(cmfs.getManifold(p, capsule, t1, slice, t2, m))
        assertEquals(1, m.getPoints().size)
        mp = m.getPoints().get(0)
        p1 = mp.getPoint()
        assertFiniteClose( 0.105, p1.x, 1.0e-3)
        assertFiniteClose(-0.226, p1.y, 1.0e-3)
        assertFiniteClose( 0.250, mp.getDepth(), 1.0e-3)
        p.clear()
        m.clear()
        sat.detect(slice, t2, capsule, t1, p)
        assertTrue(cmfs.getManifold(p, slice, t2, capsule, t1, m))
        assertEquals(1, m.getPoints().size)
        mp = m.getPoints().get(0)
        p1 = mp.getPoint()
        assertFiniteClose( 0.105, p1.x, 1.0e-3)
        assertFiniteClose(-0.226, p1.y, 1.0e-3)
        assertFiniteClose( 0.250, mp.getDepth(), 1.0e-3)
    }
}
