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

import org.dyn4j.collision.manifold.ClippingManifoldSolver
import org.dyn4j.collision.manifold.Manifold
import org.dyn4j.collision.manifold.ManifoldPoint
import org.dyn4j.collision.narrowphase.Gjk
import org.dyn4j.collision.narrowphase.Penetration
import org.dyn4j.collision.narrowphase.Separation
import org.dyn4j.geometry.Capsule
import org.dyn4j.geometry.Rectangle
import org.dyn4j.geometry.Transform
import org.dyn4j.geometry.Vector2
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import kotlin.test.assertFailsWith




class RectangleCapsuleTest : AbstractNarrowphaseShapeTest() {
    private lateinit var rectangle: Rectangle

    private lateinit var capsule: Capsule

    @BeforeTest
    fun setup() {
        this.rectangle = Rectangle(1.0, 0.5)
        this.capsule = Capsule(1.0, 0.5)
    }

    @Test
    fun detectSat() {
        val p = Penetration()
        val t1 = Transform()
        val t2 = Transform()
        lateinit var n: Vector2

        // test containment
        assertTrue(this.sat.detect(rectangle, t1, capsule, t2, p))
        assertTrue(this.sat.detect(rectangle, t1, capsule, t2))
        n = p.getNormal()
        assertClose( 0.000, n.x, 1.0e-3)
        assertClose( 1.000, n.y, 1.0e-3)
        assertClose( 0.500, p.getDepth(), 1.0e-3)

        // try reversing the shapes
        p.clear()
        assertTrue(this.sat.detect(capsule, t2, rectangle, t1, p))
        assertTrue(this.sat.detect(capsule, t2, rectangle, t1))
        n = p.getNormal()
        assertClose( 0.000, n.x, 1.0e-3)
        assertClose( 1.000, n.y, 1.0e-3)
        assertClose( 0.500, p.getDepth(), 1.0e-3)

        // test overlap
        p.clear()
        t1.translate(-0.5, 0.0)
        assertTrue(this.sat.detect(rectangle, t1, capsule, t2, p))
        assertTrue(this.sat.detect(rectangle, t1, capsule, t2))
        n = p.getNormal()
        assertClose( 1.000, n.x, 1.0e-3)
        assertClose( 0.000, n.y, 1.0e-3)
        assertClose( 0.500, p.getDepth(), 1.0e-3)

        // try reversing the shapes
        p.clear()
        assertTrue(this.sat.detect(capsule, t2, rectangle, t1, p))
        assertTrue(this.sat.detect(capsule, t2, rectangle, t1))
        n = p.getNormal()
        assertClose(-1.000, n.x, 1.0e-3)
        assertClose( 0.000, n.y, 1.0e-3)
        assertClose( 0.500, p.getDepth(), 1.0e-3)

        // test AABB overlap
        p.clear()
        t2.translate(0.35, -0.5)
        assertFalse(this.sat.detect(rectangle, t1, capsule, t2, p))
        assertFalse(this.sat.detect(rectangle, t1, capsule, t2))

        // try reversing the shapes
        p.clear()
        assertFalse(this.sat.detect(capsule, t2, rectangle, t1, p))
        assertFalse(this.sat.detect(capsule, t2, rectangle, t1))

        // test no overlap
        p.clear()
        t2.translate(1.0, 0.0)
        assertFalse(this.sat.detect(rectangle, t1, capsule, t2, p))
        assertFalse(this.sat.detect(rectangle, t1, capsule, t2))

        // try reversing the shapes
        p.clear()
        assertFalse(this.sat.detect(capsule, t2, rectangle, t1, p))
        assertFalse(this.sat.detect(capsule, t2, rectangle, t1))
    }

    @Test
    fun detectGjk() {
        val p = Penetration()
        val t1 = Transform()
        val t2 = Transform()
        lateinit var n: Vector2

        // test containment
        assertTrue(this.gjk.detect(rectangle, t1, capsule, t2, p))
        assertTrue(this.gjk.detect(rectangle, t1, capsule, t2))
        n = p.getNormal()
        assertClose( 0.000, n.x, 1.0e-3)
        assertClose( 1.000, n.y, 1.0e-3)
        assertClose( 0.500, p.getDepth(), 1.0e-3)

        // try reversing the shapes
        p.clear()
        assertTrue(this.gjk.detect(capsule, t2, rectangle, t1, p))
        assertTrue(this.gjk.detect(capsule, t2, rectangle, t1))
        n = p.getNormal()
        assertClose( 0.000, n.x, 1.0e-3)
        assertClose(-1.000, n.y, 1.0e-3)
        assertClose( 0.500, p.getDepth(), 1.0e-3)

        // test overlap
        p.clear()
        t1.translate(-0.5, 0.0)
        assertTrue(this.gjk.detect(rectangle, t1, capsule, t2, p))
        assertTrue(this.gjk.detect(rectangle, t1, capsule, t2))
        n = p.getNormal()
        assertClose( 1.000, n.x, 1.0e-3)
        assertClose( 0.000, n.y, 1.0e-3)
        assertClose( 0.500, p.getDepth(), 1.0e-3)

        // try reversing the shapes
        p.clear()
        assertTrue(this.gjk.detect(capsule, t2, rectangle, t1, p))
        assertTrue(this.gjk.detect(capsule, t2, rectangle, t1))
        n = p.getNormal()
        assertClose(-1.000, n.x, 1.0e-3)
        assertClose( 0.000, n.y, 1.0e-3)
        assertClose( 0.500, p.getDepth(), 1.0e-3)

        // test AABB overlap
        p.clear()
        t2.translate(0.35, -0.5)
        assertFalse(this.gjk.detect(rectangle, t1, capsule, t2, p))
        assertFalse(this.gjk.detect(rectangle, t1, capsule, t2))

        // try reversing the shapes
        p.clear()
        assertFalse(this.gjk.detect(capsule, t2, rectangle, t1, p))
        assertFalse(this.gjk.detect(capsule, t2, rectangle, t1))

        // test no overlap
        p.clear()
        t2.translate(1.0, 0.0)
        assertFalse(this.gjk.detect(rectangle, t1, capsule, t2, p))
        assertFalse(this.gjk.detect(rectangle, t1, capsule, t2))

        // try reversing the shapes
        p.clear()
        assertFalse(this.gjk.detect(capsule, t2, rectangle, t1, p))
        assertFalse(this.gjk.detect(capsule, t2, rectangle, t1))
    }

    @Test
    fun gjkDistance() {
        val s = Separation()

        val t1 = Transform()
        val t2 = Transform()

        lateinit var n: Vector2
        lateinit var p1: Vector2
        lateinit var p2: Vector2

        // test containment
        assertFalse(this.gjk.distance(rectangle, t1, capsule, t2, s))

        // try reversing the shapes
        s.clear()
        assertFalse(this.gjk.distance(capsule, t2, rectangle, t1, s))

        // test overlap
        s.clear()
        t1.translate(-0.5, 0.0)
        assertFalse(this.gjk.distance(rectangle, t1, capsule, t2, s))

        // try reversing the shapes
        s.clear()
        assertFalse(this.gjk.distance(capsule, t2, rectangle, t1, s))

        // test AABB overlap
        s.clear()
        t2.translate(0.35, -0.5)
        assertTrue(this.gjk.distance(rectangle, t1, capsule, t2, s))
        n = s.getNormal()
        p1 = s.getPoint1()
        p2 = s.getPoint2()
        assertClose( 0.019, s.getDistance(), 1.0e-3)
        assertClose( 0.371, n.x, 1.0e-3)
        assertClose(-0.928, n.y, 1.0e-3)
        assertClose( 0.000, p1.x, 1.0e-3)
        assertClose(-0.250, p1.y, 1.0e-3)
        assertClose( 0.007, p2.x, 1.0e-3)
        assertClose(-0.267, p2.y, 1.0e-3)

        // try reversing the shapes
        s.clear()
        assertTrue(this.gjk.distance(capsule, t2, rectangle, t1, s))
        n = s.getNormal()
        p1 = s.getPoint1()
        p2 = s.getPoint2()
        assertClose( 0.019, s.getDistance(), 1.0e-3)
        assertClose(-0.371, n.x, 1.0e-3)
        assertClose( 0.928, n.y, 1.0e-3)
        assertClose( 0.007, p1.x, 1.0e-3)
        assertClose(-0.267, p1.y, 1.0e-3)
        assertClose( 0.000, p2.x, 1.0e-3)
        assertClose(-0.250, p2.y, 1.0e-3)

        // test no overlap
        s.clear()
        t2.translate(1.0, 0.0)
        assertTrue(this.gjk.distance(rectangle, t1, capsule, t2, s))
        n = s.getNormal()
        p1 = s.getPoint1()
        p2 = s.getPoint2()
        assertClose( 0.878, s.getDistance(), 1.0e-3)
        assertClose( 0.975, n.x, 1.0e-3)
        assertClose(-0.221, n.y, 1.0e-3)
        assertClose( 0.000, p1.x, 1.0e-3)
        assertClose(-0.250, p1.y, 1.0e-3)
        assertClose( 0.856, p2.x, 1.0e-3)
        assertClose(-0.444, p2.y, 1.0e-3)

        // try reversing the shapes
        s.clear()
        assertTrue(this.gjk.distance(capsule, t2, rectangle, t1, s))
        n = s.getNormal()
        p1 = s.getPoint1()
        p2 = s.getPoint2()
        assertClose( 0.878, s.getDistance(), 1.0e-3)
        assertClose(-0.975, n.x, 1.0e-3)
        assertClose( 0.221, n.y, 1.0e-3)
        assertClose( 0.856, p1.x, 1.0e-3)
        assertClose(-0.444, p1.y, 1.0e-3)
        assertClose( 0.000, p2.x, 1.0e-3)
        assertClose(-0.250, p2.y, 1.0e-3)
    }

    @Test
    fun getClipManifold() {
        val m = Manifold()
        val p = Penetration()

        val t1 = Transform()
        val t2 = Transform()

        lateinit var mp: ManifoldPoint
        lateinit var p1: Vector2

        // test containment gjk
        this.gjk.detect(rectangle, t1, capsule, t2, p)
        assertTrue(this.cmfs.getManifold(p, rectangle, t1, capsule, t2, m))
        assertEquals(2, m.getPoints().size)

        // try reversing the shapes
        p.clear()
        m.clear()
        this.gjk.detect(capsule, t2, rectangle, t1, p)
        assertTrue(this.cmfs.getManifold(p, capsule, t2, rectangle, t1, m))
        assertEquals(2, m.getPoints().size)

        // test containment sat
        p.clear()
        m.clear()
        this.sat.detect(rectangle, t1, capsule, t2, p)
        assertTrue(this.cmfs.getManifold(p, rectangle, t1, capsule, t2, m))
        assertEquals(2, m.getPoints().size)

        // try reversing the shapes
        p.clear()
        m.clear()
        this.sat.detect(capsule, t2, rectangle, t1, p)
        assertTrue(this.cmfs.getManifold(p, capsule, t2, rectangle, t1, m))
        assertEquals(2, m.getPoints().size)

        t1.translate(-0.5, 0.0)

        // test overlap gjk
        p.clear()
        m.clear()
        this.gjk.detect(rectangle, t1, capsule, t2, p)
        assertTrue(this.cmfs.getManifold(p, rectangle, t1, capsule, t2, m))
        assertEquals(1, m.getPoints().size)
        mp = m.getPoints().get(0)
        p1 = mp.getPoint()
        assertClose(-0.500, p1.x, 1.0e-3)
        assertClose( 0.000, p1.y, 1.0e-3)
        assertClose( 0.500, mp.getDepth(), 1.0e-3)

        // try reversing the shapes
        p.clear()
        m.clear()
        this.gjk.detect(capsule, t2, rectangle, t1, p)
        assertTrue(this.cmfs.getManifold(p, capsule, t2, rectangle, t1, m))
        assertEquals(1, m.getPoints().size)
        mp = m.getPoints().get(0)
        p1 = mp.getPoint()
        assertClose(-0.500, p1.x, 1.0e-3)
        assertClose( 0.000, p1.y, 1.0e-3)
        assertClose( 0.500, mp.getDepth(), 1.0e-3)

        // test overlap sat
        p.clear()
        m.clear()
        this.sat.detect(rectangle, t1, capsule, t2, p)
        assertTrue(this.cmfs.getManifold(p, rectangle, t1, capsule, t2, m))
        assertEquals(1, m.getPoints().size)
        mp = m.getPoints().get(0)
        p1 = mp.getPoint()
        assertClose(-0.500, p1.x, 1.0e-3)
        assertClose( 0.000, p1.y, 1.0e-3)
        assertClose( 0.500, mp.getDepth(), 1.0e-3)

        // try reversing the shapes
        p.clear()
        m.clear()
        this.sat.detect(capsule, t2, rectangle, t1, p)
        assertTrue(this.cmfs.getManifold(p, capsule, t2, rectangle, t1, m))
        assertEquals(1, m.getPoints().size)
        mp = m.getPoints().get(0)
        p1 = mp.getPoint()
        assertClose(-0.500, p1.x, 1.0e-3)
        assertClose( 0.000, p1.y, 1.0e-3)
        assertClose( 0.500, mp.getDepth(), 1.0e-3)
    }
}
