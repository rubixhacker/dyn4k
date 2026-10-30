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
import org.dyn4j.collision.narrowphase.Sat
import org.dyn4j.collision.narrowphase.Separation
import org.dyn4j.geometry.Transform
import org.dyn4j.geometry.Triangle
import org.dyn4j.geometry.Vector2
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import kotlin.test.assertFailsWith

val TriangleTriangleTest by testSuite {
    test("detectSat") { TriangleTriangleTestFixture().apply { setup() }.run { detectSat() } }
    test("detectGjk") { TriangleTriangleTestFixture().apply { setup() }.run { detectGjk() } }
    test("gjkDistance") { TriangleTriangleTestFixture().apply { setup() }.run { gjkDistance() } }
    test("getClipManifold") { TriangleTriangleTestFixture().apply { setup() }.run { getClipManifold() } }
    test("distanceNotFound") { TriangleTriangleTestFixture().apply { setup() }.run { distanceNotFound() } }
    test("falsePenetration1") { TriangleTriangleTestFixture().apply { setup() }.run { falsePenetration1() } }
}




private class TriangleTriangleTestFixture : AbstractNarrowphaseShapeTest()  {
    private lateinit var tri1: Triangle

    private lateinit var tri2: Triangle

    fun setup() {
        this.tri1 = Triangle(
        Vector2(1.29, 0.25),
        Vector2(-0.71, 0.65),
        Vector2(-0.59, -0.85))
        this.tri2 = Triangle(
        Vector2(0.45, -0.12),
        Vector2(-0.45, 0.38),
        Vector2(-0.15, -0.22))
    }

fun detectSat() {
        val p = Penetration()
        val t1 = Transform()
        val t2 = Transform()

        lateinit var n: Vector2

        // test containment
        assertTrue(this.sat.detect(tri1, t1, tri2, t2, p))
        assertTrue(this.sat.detect(tri1, t1, tri2, t2))
        n = p.getNormal()
        assertClose(-0.196, n.x, 1.0e-3)
        assertClose(-0.980, n.y, 1.0e-3)
        assertClose(0.743, p.getDepth(), 1.0e-3)

        // try reversing the shapes
        p.clear()
        assertTrue(this.sat.detect(tri2, t2, tri1, t1, p))
        assertTrue(this.sat.detect(tri2, t2, tri1, t1))
        n = p.getNormal()
        assertClose(0.196, n.x, 1.0e-3)
        assertClose(0.980, n.y, 1.0e-3)
        assertClose(0.743, p.getDepth(), 1.0e-3)

        // test overlap
        p.clear()
        t2.translate(0.0, 0.5)
        assertTrue(this.sat.detect(tri1, t1, tri2, t2, p))
        assertTrue(this.sat.detect(tri1, t1, tri2, t2))
        n = p.getNormal()
        assertClose(0.196, n.x, 1.0e-3)
        assertClose(0.980, n.y, 1.0e-3)
        assertClose(0.252, p.getDepth(), 1.0e-3)

        // try reversing the shapes
        p.clear()
        assertTrue(this.sat.detect(tri2, t2, tri1, t1, p))
        assertTrue(this.sat.detect(tri2, t2, tri1, t1))
        n = p.getNormal()
        assertClose(-0.196, n.x, 1.0e-3)
        assertClose(-0.980, n.y, 1.0e-3)
        assertClose(0.252, p.getDepth(), 1.0e-3)

        // test AABB overlap
        p.clear()
        t2.translate(0.0, 0.3)
        assertFalse(this.sat.detect(tri1, t1, tri2, t2, p))
        assertFalse(this.sat.detect(tri1, t1, tri2, t2))

        // try reversing the shapes
        p.clear()
        assertFalse(this.sat.detect(tri2, t2, tri1, t1, p))
        assertFalse(this.sat.detect(tri2, t2, tri1, t1))

        // test no overlap
        p.clear()
        t2.translate(0.0, 0.3)
        assertFalse(this.sat.detect(tri1, t1, tri2, t2, p))
        assertFalse(this.sat.detect(tri1, t1, tri2, t2))

        // try reversing the shapes
        p.clear()
        assertFalse(this.sat.detect(tri2, t2, tri1, t1, p))
        assertFalse(this.sat.detect(tri2, t2, tri1, t1))
    }

fun detectGjk() {
        val p = Penetration()
        val t1 = Transform()
        val t2 = Transform()

        lateinit var n: Vector2

        // test containment
        assertTrue(this.gjk.detect(tri1, t1, tri2, t2, p))
        assertTrue(this.gjk.detect(tri1, t1, tri2, t2))
        n = p.getNormal()
        assertClose(0.196, n.x, 1.0e-3)
        assertClose(0.980, n.y, 1.0e-3)
        assertClose(0.743, p.getDepth(), 1.0e-3)

        // try reversing the shapes
        p.clear()
        assertTrue(this.gjk.detect(tri2, t2, tri1, t1, p))
        assertTrue(this.gjk.detect(tri2, t2, tri1, t1))
        n = p.getNormal()
        assertClose(-0.196, n.x, 1.0e-3)
        assertClose(-0.980, n.y, 1.0e-3)
        assertClose(0.743, p.getDepth(), 1.0e-3)

        // test overlap
        p.clear()
        t2.translate(0.0, 0.5)
        assertTrue(this.gjk.detect(tri1, t1, tri2, t2, p))
        assertTrue(this.gjk.detect(tri1, t1, tri2, t2))
        n = p.getNormal()
        assertClose(0.196, n.x, 1.0e-3)
        assertClose(0.980, n.y, 1.0e-3)
        assertClose(0.252, p.getDepth(), 1.0e-3)

        // try reversing the shapes
        p.clear()
        assertTrue(this.gjk.detect(tri2, t2, tri1, t1, p))
        assertTrue(this.gjk.detect(tri2, t2, tri1, t1))
        n = p.getNormal()
        assertClose(-0.196, n.x, 1.0e-3)
        assertClose(-0.980, n.y, 1.0e-3)
        assertClose(0.252, p.getDepth(), 1.0e-3)

        // test AABB overlap
        p.clear()
        t2.translate(0.0, 0.3)
        assertFalse(this.gjk.detect(tri1, t1, tri2, t2, p))
        assertFalse(this.gjk.detect(tri1, t1, tri2, t2))

        // try reversing the shapes
        p.clear()
        assertFalse(this.gjk.detect(tri2, t2, tri1, t1, p))
        assertFalse(this.gjk.detect(tri2, t2, tri1, t1))

        // test no overlap
        p.clear()
        t2.translate(0.0, 0.3)
        assertFalse(this.gjk.detect(tri1, t1, tri2, t2, p))
        assertFalse(this.gjk.detect(tri1, t1, tri2, t2))

        // try reversing the shapes
        p.clear()
        assertFalse(this.gjk.detect(tri2, t2, tri1, t1, p))
        assertFalse(this.gjk.detect(tri2, t2, tri1, t1))
    }

fun gjkDistance() {
        val s = Separation()

        val t1 = Transform()
        val t2 = Transform()

        lateinit var n: Vector2
        lateinit var p1: Vector2
        lateinit var p2: Vector2

        // test containment
        assertFalse(this.gjk.distance(tri1, t1, tri2, t2, s))

        // try reversing the shapes
        s.clear()
        assertFalse(this.gjk.distance(tri2, t2, tri1, t1, s))

        // test overlap
        s.clear()
        t2.translate(0.0, 0.5)
        assertFalse(this.gjk.distance(tri1, t1, tri2, t2, s))

        // try reversing the shapes
        s.clear()
        assertFalse(this.gjk.distance(tri2, t2, tri1, t1, s))

        // test AABB overlap
        s.clear()
        t2.translate(0.0, 0.3)
        assertTrue(this.gjk.distance(tri1, t1, tri2, t2, s))
        n = s.getNormal()
        p1 = s.getPoint1()
        p2 = s.getPoint2()
        assertClose(0.041, s.getDistance(), 1.0e-3)
        assertClose(0.196, n.x, 1.0e-3)
        assertClose(0.980, n.y, 1.0e-3)
        assertClose(-0.158, p1.x, 1.0e-3)
        assertClose(0.539, p1.y, 1.0e-3)
        assertClose(-0.150, p2.x, 1.0e-3)
        assertClose(0.580, p2.y, 1.0e-3)

        // try reversing the shapes
        s.clear()
        assertTrue(this.gjk.distance(tri2, t2, tri1, t1, s))
        n = s.getNormal()
        p1 = s.getPoint1()
        p2 = s.getPoint2()
        assertClose(0.041, s.getDistance(), 1.0e-3)
        assertClose(-0.196, n.x, 1.0e-3)
        assertClose(-0.980, n.y, 1.0e-3)
        assertClose(-0.150, p1.x, 1.0e-3)
        assertClose(0.580, p1.y, 1.0e-3)
        assertClose(-0.158, p2.x, 1.0e-3)
        assertClose(0.539, p2.y, 1.0e-3)

        // test no overlap
        s.clear()
        t2.translate(0.0, 0.3)
        assertTrue(this.gjk.distance(tri1, t1, tri2, t2, s))
        n = s.getNormal()
        p1 = s.getPoint1()
        p2 = s.getPoint2()
        assertClose(0.335, s.getDistance(), 1.0e-3)
        assertClose(0.196, n.x, 1.0e-3)
        assertClose(0.980, n.y, 1.0e-3)
        assertClose(-0.215, p1.x, 1.0e-3)
        assertClose(0.551, p1.y, 1.0e-3)
        assertClose(-0.150, p2.x, 1.0e-3)
        assertClose(0.880, p2.y, 1.0e-3)

        // try reversing the shapes
        s.clear()
        assertTrue(this.gjk.distance(tri2, t2, tri1, t1, s))
        n = s.getNormal()
        p1 = s.getPoint1()
        p2 = s.getPoint2()
        assertClose(0.335, s.getDistance(), 1.0e-3)
        assertClose(-0.196, n.x, 1.0e-3)
        assertClose(-0.980, n.y, 1.0e-3)
        assertClose(-0.150, p1.x, 1.0e-3)
        assertClose(0.880, p1.y, 1.0e-3)
        assertClose(-0.215, p2.x, 1.0e-3)
        assertClose(0.551, p2.y, 1.0e-3)
    }

fun getClipManifold() {
        val m = Manifold()
        val p = Penetration()

        val t1 = Transform()
        val t2 = Transform()

        lateinit var mp1: ManifoldPoint
        lateinit var mp2: ManifoldPoint
        lateinit var p1: Vector2
        lateinit var p2: Vector2

        // test containment gjk
        this.gjk.detect(tri1, t1, tri2, t2, p)
        assertTrue(this.cmfs.getManifold(p, tri1, t1, tri2, t2, m))
        assertEquals(2, m.getPoints().size)

        // try reversing the shapes
        p.clear()
        m.clear()
        this.gjk.detect(tri2, t2, tri1, t1, p)
        assertTrue(this.cmfs.getManifold(p, tri2, t2, tri1, t1, m))
        assertEquals(2, m.getPoints().size)

        // test containment sat
        p.clear()
        m.clear()
        this.sat.detect(tri1, t1, tri2, t2, p)
        assertTrue(this.cmfs.getManifold(p, tri1, t1, tri2, t2, m))
        assertEquals(2, m.getPoints().size)

        // try reversing the shapes
        p.clear()
        m.clear()
        this.sat.detect(tri2, t2, tri1, t1, p)
        assertTrue(this.cmfs.getManifold(p, tri2, t2, tri1, t1, m))
        assertEquals(2, m.getPoints().size)

        t2.translate(0.0, 0.5)

        // test overlap gjk
        p.clear()
        m.clear()
        this.gjk.detect(tri1, t1, tri2, t2, p)
        assertTrue(this.cmfs.getManifold(p, tri1, t1, tri2, t2, m))
        assertEquals(2, m.getPoints().size)
        mp1 = m.getPoints().get(0)
        mp2 = m.getPoints().get(1)
        p1 = mp1.getPoint()
        p2 = mp2.getPoint()
        assertClose(-0.150, p1.x, 1.0e-3)
        assertClose(0.280, p1.y, 1.0e-3)
        assertClose(0.252, mp1.getDepth(), 1.0e-3)
        assertClose(0.450, p2.x, 1.0e-3)
        assertClose(0.380, p2.y, 1.0e-3)
        assertClose(0.037, mp2.getDepth(), 1.0e-3)

        // try reversing the shapes
        p.clear()
        m.clear()
        this.gjk.detect(tri2, t2, tri1, t1, p)
        assertTrue(this.cmfs.getManifold(p, tri2, t2, tri1, t1, m))
        assertEquals(2, m.getPoints().size)
        mp1 = m.getPoints().get(0)
        mp2 = m.getPoints().get(1)
        p1 = mp1.getPoint()
        p2 = mp2.getPoint()
        assertClose(-0.150, p1.x, 1.0e-3)
        assertClose(0.280, p1.y, 1.0e-3)
        assertClose(0.252, mp1.getDepth(), 1.0e-3)
        assertClose(0.450, p2.x, 1.0e-3)
        assertClose(0.380, p2.y, 1.0e-3)
        assertClose(0.037, mp2.getDepth(), 1.0e-3)

        // test overlap sat
        p.clear()
        m.clear()
        this.sat.detect(tri1, t1, tri2, t2, p)
        assertTrue(this.cmfs.getManifold(p, tri1, t1, tri2, t2, m))
        assertEquals(2, m.getPoints().size)
        mp1 = m.getPoints().get(0)
        mp2 = m.getPoints().get(1)
        p1 = mp1.getPoint()
        p2 = mp2.getPoint()
        assertClose(-0.150, p1.x, 1.0e-3)
        assertClose(0.280, p1.y, 1.0e-3)
        assertClose(0.252, mp1.getDepth(), 1.0e-3)
        assertClose(0.450, p2.x, 1.0e-3)
        assertClose(0.380, p2.y, 1.0e-3)
        assertClose(0.037, mp2.getDepth(), 1.0e-3)

        // try reversing the shapes
        p.clear()
        m.clear()
        this.sat.detect(tri2, t2, tri1, t1, p)
        assertTrue(this.cmfs.getManifold(p, tri2, t2, tri1, t1, m))
        assertEquals(2, m.getPoints().size)
        mp1 = m.getPoints().get(0)
        mp2 = m.getPoints().get(1)
        p1 = mp1.getPoint()
        p2 = mp2.getPoint()
        assertClose(-0.150, p1.x, 1.0e-3)
        assertClose(0.280, p1.y, 1.0e-3)
        assertClose(0.252, mp1.getDepth(), 1.0e-3)
        assertClose(0.450, p2.x, 1.0e-3)
        assertClose(0.380, p2.y, 1.0e-3)
        assertClose(0.037, mp2.getDepth(), 1.0e-3)
    }

fun distanceNotFound() {
        val s = Separation()
        val t1 = Transform()
        val t2 = Transform()

        lateinit var p1: Vector2
        lateinit var p2: Vector2

        t2.translate(1.578125, 0.6875)

        assertTrue(this.gjk.distance(tri1, t1, tri2, t2, s))
        p1 = s.getPoint1()
        p2 = s.getPoint2()
        // this bug was caused by the point solving code returning two
        // points whose coordinates where NaN, NaN
        assertTrue(p1.x.isFinite())
        assertTrue(p1.y.isFinite())
        assertTrue(p2.x.isFinite())
        assertTrue(p2.y.isFinite())
    }

fun falsePenetration1() {
        // this config would generate a penetration object with zero depth
        val t1 = Triangle(
        Vector2(-0.5877852522924732, -0.8090169943749473),
        Vector2(-0.30901699437494756, -0.9510565162951535),
        Vector2(3.592757177872429E-17, -2.470020559787295E-17))
        val t2 = Triangle(
        Vector2(-0.9510565162951536, -0.3090169943749473),
        Vector2(-0.8090169943749475, -0.587785252292473),
        Vector2(3.592757177872429E-17, -2.470020559787295E-17))
        val p = Penetration()
        val tx = Transform()
        tx.translate(-2.5, -2.5752222222222203)
        var collided = this.gjk.detect(t1, tx, t2, tx, p)
        assertFalse(collided)

        val t3 = Triangle(
        Vector2(-0.30901699437494756, -0.9510565162951535),
        Vector2(-1.8369701987210297E-16, -1.0),
        Vector2(3.592757177872429E-17, -2.470020559787295E-17))
        val t4 = Triangle(
        Vector2(-1.8369701987210297E-16, -1.0),
        Vector2(0.30901699437494723, -0.9510565162951536),
        Vector2(3.592757177872429E-17, -2.470020559787295E-17))

        collided = this.gjk.detect(t3, tx, t4, tx, p)
        assertFalse(collided)
    }
}
