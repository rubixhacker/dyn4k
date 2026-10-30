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
package org.dyn4j.coverage.collision.shapes.b

import de.infix.testBalloon.framework.core.testSuite
import org.dyn4j.collision.manifold.ClippingManifoldSolver
import org.dyn4j.collision.manifold.Manifold
import org.dyn4j.collision.manifold.ManifoldPoint
import org.dyn4j.collision.narrowphase.Gjk
import org.dyn4j.collision.narrowphase.Penetration
import org.dyn4j.collision.narrowphase.Separation
import org.dyn4j.geometry.Ellipse
import org.dyn4j.geometry.Transform
import org.dyn4j.geometry.Triangle
import org.dyn4j.geometry.Vector2
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import kotlin.test.assertFailsWith

val TriangleEllipseTest by testSuite {
    test("detectSat") { TriangleEllipseTestFixture().apply { setup() }.run { detectSat() } }
    test("detectGjk") { TriangleEllipseTestFixture().apply { setup() }.run { detectGjk() } }
    test("gjkDistance") { TriangleEllipseTestFixture().apply { setup() }.run { gjkDistance() } }
    test("getClipManifold") { TriangleEllipseTestFixture().apply { setup() }.run { getClipManifold() } }
}




private class TriangleEllipseTestFixture : AbstractNarrowphaseShapeTest()  {
    private lateinit var t: Triangle

    private lateinit var e: Ellipse

    fun setup() {
        this.t = Triangle(
        Vector2(1.29, 0.25),
        Vector2(-0.71, 0.65),
        Vector2(-0.59, -0.85))
        this.e = Ellipse(1.0, 0.5)
    }

fun detectSat() {
        assertFailsWith<UnsupportedOperationException> {
            val p = Penetration()
            val t1 = Transform()
            val t2 = Transform()

            this.sat.detect(t, t1, e, t2, p)
        }
    }

fun detectGjk() {
        val p = Penetration()
        val t1 = Transform()
        val t2 = Transform()

        lateinit var n: Vector2

        // test containment
        assertTrue(this.gjk.detect(t, t1, e, t2, p))
        assertTrue(this.gjk.detect(t, t1, e, t2))
        n = p.getNormal()
        assertClose( 0.196, n.x, 1.0e-3)
        assertClose( 0.980, n.y, 1.0e-3)
        assertClose( 0.762, p.getDepth(), 1.0e-3)

        // try reversing the shapes
        p.clear()
        assertTrue(this.gjk.detect(e, t2, t, t1, p))
        assertTrue(this.gjk.detect(e, t2, t, t1))
        n = p.getNormal()
        assertClose(-0.196, n.x, 1.0e-3)
        assertClose(-0.980, n.y, 1.0e-3)
        assertClose( 0.762, p.getDepth(), 1.0e-3)

        // test overlap
        p.clear()
        t1.translate(-0.8, 0.0)
        assertTrue(this.gjk.detect(t, t1, e, t2, p))
        assertTrue(this.gjk.detect(t, t1, e, t2))
        n = p.getNormal()
        assertClose( 0.505, n.x, 1.0e-3)
        assertClose(-0.863, n.y, 1.0e-3)
        assertClose( 0.363, p.getDepth(), 1.0e-3)

        // try reversing the shapes
        p.clear()
        assertTrue(this.gjk.detect(e, t2, t, t1, p))
        assertTrue(this.gjk.detect(e, t2, t, t1))
        n = p.getNormal()
        assertClose(-0.505, n.x, 1.0e-3)
        assertClose( 0.863, n.y, 1.0e-3)
        assertClose( 0.363, p.getDepth(), 1.0e-3)

        // test AABB overlap
        p.clear()
        t2.translate(0.5, -0.5)
        assertFalse(this.gjk.detect(t, t1, e, t2, p))
        assertFalse(this.gjk.detect(t, t1, e, t2))

        // try reversing the shapes
        p.clear()
        assertFalse(this.gjk.detect(e, t2, t, t1, p))
        assertFalse(this.gjk.detect(e, t2, t, t1))

        // test no overlap
        p.clear()
        t2.translate(1.0, 0.5)
        assertFalse(this.gjk.detect(t, t1, e, t2, p))
        assertFalse(this.gjk.detect(t, t1, e, t2))

        // try reversing the shapes
        p.clear()
        assertFalse(this.gjk.detect(e, t2, t, t1, p))
        assertFalse(this.gjk.detect(e, t2, t, t1))
    }

fun gjkDistance() {
        val s = Separation()

        val t1 = Transform()
        val t2 = Transform()

        lateinit var n: Vector2
        lateinit var p1: Vector2
        lateinit var p2: Vector2

        // test containment
        assertFalse(this.gjk.distance(t, t1, e, t2, s))

        // try reversing the shapes
        s.clear()
        assertFalse(this.gjk.distance(e, t2, t, t1, s))

        // test overlap
        s.clear()
        t1.translate(-0.8, 0.0)
        assertFalse(this.gjk.distance(t, t1, e, t2, s))

        // try reversing the shapes
        s.clear()
        assertFalse(this.gjk.distance(e, t2, t, t1, s))

        // test AABB overlap
        s.clear()
        t2.translate(0.5, -0.5)
        assertTrue(this.gjk.distance(t, t1, e, t2, s))
        n = s.getNormal()
        p1 = s.getPoint1()
        p2 = s.getPoint2()
        assertClose( 0.320, s.getDistance(), 1.0e-3)
        assertClose( 0.505, n.x, 1.0e-3)
        assertClose(-0.863, n.y, 1.0e-3)
        assertClose(-0.041, p1.x, 1.0e-3)
        assertClose(-0.061, p1.y, 1.0e-3)
        assertClose( 0.119, p2.x, 1.0e-3)
        assertClose(-0.337, p2.y, 1.0e-3)

        // try reversing the shapes
        s.clear()
        assertTrue(this.gjk.distance(e, t2, t, t1, s))
        n = s.getNormal()
        p1 = s.getPoint1()
        p2 = s.getPoint2()
        assertClose( 0.320, s.getDistance(), 1.0e-3)
        assertClose(-0.505, n.x, 1.0e-3)
        assertClose( 0.863, n.y, 1.0e-3)
        assertClose( 0.119, p1.x, 1.0e-3)
        assertClose(-0.337, p1.y, 1.0e-3)
        assertClose(-0.041, p2.x, 1.0e-3)
        assertClose(-0.061, p2.y, 1.0e-3)

        // test no overlap
        s.clear()
        t2.translate(1.0, 0.5)
        assertTrue(this.gjk.distance(t, t1, e, t2, s))
        n = s.getNormal()
        p1 = s.getPoint1()
        p2 = s.getPoint2()
        assertClose( 0.557, s.getDistance(), 1.0e-3)
        assertClose( 0.931, n.x, 1.0e-3)
        assertClose(-0.362, n.y, 1.0e-3)
        assertClose( 0.490, p1.x, 1.0e-3)
        assertClose( 0.250, p1.y, 1.0e-3)
        assertClose( 1.009, p2.x, 1.0e-3)
        assertClose( 0.047, p2.y, 1.0e-3)

        // try reversing the shapes
        s.clear()
        assertTrue(this.gjk.distance(e, t2, t, t1, s))
        n = s.getNormal()
        p1 = s.getPoint1()
        p2 = s.getPoint2()
        assertClose( 0.557, s.getDistance(), 1.0e-3)
        assertClose(-0.931, n.x, 1.0e-3)
        assertClose( 0.362, n.y, 1.0e-3)
        assertClose( 1.009, p1.x, 1.0e-3)
        assertClose( 0.047, p1.y, 1.0e-3)
        assertClose( 0.490, p2.x, 1.0e-3)
        assertClose( 0.250, p2.y, 1.0e-3)
    }

fun getClipManifold() {
        val m = Manifold()
        val p = Penetration()

        val t1 = Transform()
        val t2 = Transform()

        lateinit var mp1: ManifoldPoint
        lateinit var p1: Vector2

        // test containment gjk
        this.gjk.detect(t, t1, e, t2, p)
        assertTrue(this.cmfs.getManifold(p, t, t1, e, t2, m))
        assertEquals(1, m.getPoints().size)

        // try reversing the shapes
        p.clear()
        m.clear()
        this.gjk.detect(e, t2, t, t1, p)
        assertTrue(this.cmfs.getManifold(p, e, t2, t, t1, m))
        assertEquals(1, m.getPoints().size)

        t1.translate(-0.8, 0.0)

        // test overlap gjk
        p.clear()
        m.clear()
        this.gjk.detect(t, t1, e, t2, p)
        assertTrue(this.cmfs.getManifold(p, t, t1, e, t2, m))
        assertEquals(1, m.getPoints().size)
        mp1 = m.getPoints().get(0)
        p1 = mp1.getPoint()
        assertClose(-0.380, p1.x, 1.0e-3)
        assertClose( 0.162, p1.y, 1.0e-3)
        assertClose( 0.363, mp1.getDepth(), 1.0e-3)

        // try reversing the shapes
        p.clear()
        m.clear()
        this.gjk.detect(e, t2, t, t1, p)
        assertTrue(this.cmfs.getManifold(p, e, t2, t, t1, m))
        assertEquals(1, m.getPoints().size)
        mp1 = m.getPoints().get(0)
        p1 = mp1.getPoint()
        assertClose(-0.380, p1.x, 1.0e-3)
        assertClose( 0.162, p1.y, 1.0e-3)
        assertClose( 0.363, mp1.getDepth(), 1.0e-3)
    }
}
