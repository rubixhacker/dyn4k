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
import org.dyn4j.geometry.Ellipse
import org.dyn4j.geometry.Segment
import org.dyn4j.geometry.Transform
import org.dyn4j.geometry.Vector2
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import kotlin.test.assertFailsWith




class SegmentEllipseTest : AbstractNarrowphaseShapeTest() {
    private lateinit var s: Segment

    private lateinit var e: Ellipse

    @BeforeTest
    fun setup() {
        this.s = Segment(Vector2(-1.5, 1.0), Vector2(1.5, -1.0))
        this.e = Ellipse(1.0, 0.5)
    }

    @Test
    fun detectSat() {
        assertFailsWith<UnsupportedOperationException> {
            val p = Penetration()
            val t1 = Transform()
            val t2 = Transform()

            this.sat.detect(s, t1, e, t2, p)
        }
    }

    @Test
    fun detectGjk() {
        val p = Penetration()
        val t1 = Transform()
        val t2 = Transform()

        lateinit var n: Vector2

        // test containment
        assertTrue(this.gjk.detect(s, t1, e, t2, p))
        assertTrue(this.gjk.detect(s, t1, e, t2))
        n = p.getNormal()
        assertClose(-0.554, n.x, 1.0e-3)
        assertClose(-0.832, n.y, 1.0e-3)
        assertClose( 0.346, p.getDepth(), 1.0e-3)

        // try reversing the shapes
        p.clear()
        assertTrue(this.gjk.detect(e, t2, s, t1, p))
        assertTrue(this.gjk.detect(e, t2, s, t1))
        n = p.getNormal()
        assertClose(-0.554, n.x, 1.0e-3)
        assertClose(-0.832, n.y, 1.0e-3)
        assertClose( 0.346, p.getDepth(), 1.0e-3)

        // test overlap
        p.clear()
        t1.translate(-0.5, 0.0)
        assertTrue(this.gjk.detect(s, t1, e, t2, p))
        assertTrue(this.gjk.detect(s, t1, e, t2))
        n = p.getNormal()
        assertClose( 0.554, n.x, 1.0e-3)
        assertClose( 0.832, n.y, 1.0e-3)
        assertClose( 0.069, p.getDepth(), 1.0e-3)

        // try reversing the shapes
        p.clear()
        assertTrue(this.gjk.detect(e, t2, s, t1, p))
        assertTrue(this.gjk.detect(e, t2, s, t1))
        n = p.getNormal()
        assertClose(-0.554, n.x, 1.0e-3)
        assertClose(-0.832, n.y, 1.0e-3)
        assertClose( 0.069, p.getDepth(), 1.0e-3)

        // test AABB overlap
        p.clear()
        t2.translate(1.0, 0.0)
        assertFalse(this.gjk.detect(s, t1, e, t2, p))
        assertFalse(this.gjk.detect(s, t1, e, t2))

        // try reversing the shapes
        p.clear()
        assertFalse(this.gjk.detect(e, t2, s, t1, p))
        assertFalse(this.gjk.detect(e, t2, s, t1))

        // test no overlap
        p.clear()
        t2.translate(3.0, 2.0)
        assertFalse(this.gjk.detect(s, t1, e, t2, p))
        assertFalse(this.gjk.detect(s, t1, e, t2))

        // try reversing the shapes
        p.clear()
        assertFalse(this.gjk.detect(e, t2, s, t1, p))
        assertFalse(this.gjk.detect(e, t2, s, t1))
    }

    @Test
    fun gjkDistance() {
        val se = Separation()

        val t1 = Transform()
        val t2 = Transform()

        lateinit var n: Vector2
        lateinit var p1: Vector2
        lateinit var p2: Vector2

        // test containment
        assertFalse(this.gjk.distance(s, t1, e, t2, se))

        // try reversing the shapes
        se.clear()
        assertFalse(this.gjk.distance(e, t2, s, t1, se))

        // test overlap
        se.clear()
        t1.translate(-0.5, 0.0)
        assertFalse(this.gjk.distance(s, t1, e, t2, se))

        // try reversing the shapes
        se.clear()
        assertFalse(this.gjk.distance(e, t2, s, t1, se))

        // test AABB overlap
        se.clear()
        t2.translate(1.0, 0.0)
        assertTrue(this.gjk.distance(s, t1, e, t2, se))
        n = se.getNormal()
        p1 = se.getPoint1()
        p2 = se.getPoint2()
        assertClose( 0.485, se.getDistance(), 1.0e-3)
        assertClose( 0.554, n.x, 1.0e-3)
        assertClose( 0.832, n.y, 1.0e-3)
        assertClose( 0.330, p1.x, 1.0e-3)
        assertClose(-0.553, p1.y, 1.0e-3)
        assertClose( 0.599, p2.x, 1.0e-3)
        assertClose(-0.149, p2.y, 1.0e-3)

        // try reversing the shapes
        se.clear()
        assertTrue(this.gjk.distance(e, t2, s, t1, se))
        n = se.getNormal()
        p1 = se.getPoint1()
        p2 = se.getPoint2()
        assertClose( 0.485, se.getDistance(), 1.0e-3)
        assertClose(-0.554, n.x, 1.0e-3)
        assertClose(-0.832, n.y, 1.0e-3)
        assertClose( 0.599, p1.x, 1.0e-3)
        assertClose(-0.149, p1.y, 1.0e-3)
        assertClose( 0.330, p2.x, 1.0e-3)
        assertClose(-0.553, p2.y, 1.0e-3)

        // test no overlap
        se.clear()
        t2.translate(3.0, 2.0)
        assertTrue(this.gjk.distance(s, t1, e, t2, se))
        n = se.getNormal()
        p1 = se.getPoint1()
        p2 = se.getPoint2()
        assertClose( 3.854, se.getDistance(), 1.0e-3)
        assertClose( 0.665, n.x, 1.0e-3)
        assertClose( 0.746, n.y, 1.0e-3)
        assertClose( 1.000, p1.x, 1.0e-3)
        assertClose(-1.000, p1.y, 1.0e-3)
        assertClose( 3.563, p2.x, 1.0e-3)
        assertClose( 1.877, p2.y, 1.0e-3)

        // try reversing the shapes
        se.clear()
        assertTrue(this.gjk.distance(e, t2, s, t1, se))
        n = se.getNormal()
        p1 = se.getPoint1()
        p2 = se.getPoint2()
        assertClose( 3.854, se.getDistance(), 1.0e-3)
        assertClose(-0.665, n.x, 1.0e-3)
        assertClose(-0.746, n.y, 1.0e-3)
        assertClose( 3.563, p1.x, 1.0e-3)
        assertClose( 1.877, p1.y, 1.0e-3)
        assertClose( 1.000, p2.x, 1.0e-3)
        assertClose(-1.000, p2.y, 1.0e-3)
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
        this.gjk.detect(s, t1, e, t2, p)
        assertTrue(this.cmfs.getManifold(p, s, t1, e, t2, m))
        assertEquals(1, m.getPoints().size)

        // try reversing the shapes
        p.clear()
        m.clear()
        this.gjk.detect(e, t2, s, t1, p)
        assertTrue(this.cmfs.getManifold(p, e, t2, s, t1, m))
        assertEquals(1, m.getPoints().size)

        t1.translate(-0.5, 0.0)

        // test overlap gjk
        p.clear()
        m.clear()
        this.gjk.detect(s, t1, e, t2, p)
        assertTrue(this.cmfs.getManifold(p, s, t1, e, t2, m))
        assertEquals(1, m.getPoints().size)
        mp = m.getPoints().get(0)
        p1 = mp.getPoint()
        assertClose(-0.400, p1.x, 1.0e-3)
        assertClose(-0.149, p1.y, 1.0e-3)
        assertClose( 0.069, mp.getDepth(), 1.0e-3)

        // try reversing the shapes
        p.clear()
        m.clear()
        this.gjk.detect(e, t2, s, t1, p)
        assertTrue(this.cmfs.getManifold(p, e, t2, s, t1, m))
        assertEquals(1, m.getPoints().size)
        mp = m.getPoints().get(0)
        p1 = mp.getPoint()
        assertClose(-0.400, p1.x, 1.0e-3)
        assertClose(-0.149, p1.y, 1.0e-3)
        assertClose( 0.069, mp.getDepth(), 1.0e-3)
    }
}
