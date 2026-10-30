/*
 * Copyright (c) 2010-2024 William Bittle  http://www.dyn4j.org/
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
package org.dyn4j.geometry

import de.infix.testBalloon.framework.core.testSuite
import org.dyn4j.geometry.*
import org.dyn4j.Epsilon
import kotlin.test.*

val SegmentTest by testSuite {
    test("createNullPoint1") { SegmentTestFixture().run { createNullPoint1() } }
    test("createNullPoint2") { SegmentTestFixture().run { createNullPoint2() } }
    test("createCoincident") { SegmentTestFixture().run { createCoincident() } }
    test("creatSuccess") { SegmentTestFixture().run { creatSuccess() } }
    test("getLength") { SegmentTestFixture().run { getLength() } }
    test("getLocation") { SegmentTestFixture().run { getLocation() } }
    test("getPointClosest") { SegmentTestFixture().run { getPointClosest() } }
    test("getAxes") { SegmentTestFixture().run { getAxes() } }
    test("getFoci") { SegmentTestFixture().run { getFoci() } }
    test("contains") { SegmentTestFixture().run { contains() } }
    test("containsRadius") { SegmentTestFixture().run { containsRadius() } }
    test("project") { SegmentTestFixture().run { project() } }
    test("getFarthest") { SegmentTestFixture().run { getFarthest() } }
    test("rotate") { SegmentTestFixture().run { rotate() } }
    test("translate") { SegmentTestFixture().run { translate() } }
    test("createAABB") { SegmentTestFixture().run { createAABB() } }
    test("getLineIntersection") { SegmentTestFixture().run { getLineIntersection() } }
    test("getSegmentIntersection") { SegmentTestFixture().run { getSegmentIntersection() } }
    test("createMass") { SegmentTestFixture().run { createMass() } }
    test("getArea") { SegmentTestFixture().run { getArea() } }
    test("getNormals") { SegmentTestFixture().run { getNormals() } }
    test("copy") { SegmentTestFixture().run { copy() } }
}

private class SegmentTestFixture  {
    private val IDENTITY = Transform()
fun createNullPoint1() {
        assertFailsWith<NullPointerException> {

		Segment(null, Vector2());

        }
    }

fun createNullPoint2() {
        assertFailsWith<NullPointerException> {

		Segment(Vector2(), null);

        }
    }

fun createCoincident() {
        assertFailsWith<IllegalArgumentException> {

		Segment(Vector2(), Vector2());

        }
    }

fun creatSuccess() {

		var s = Segment(
			Vector2(0.0, 1.0),
			Vector2(1.0, 2.0)
		);

		assertEquals(0.500, s.getCenter().x, 1.0e-3);
		assertEquals(1.500, s.getCenter().y, 1.0e-3);
		assertNotNull(s.toString());
		assertNotNull(s.getVertexIterator());
		assertEquals(WoundIterator::class, s.getVertexIterator()::class);
		assertNotNull(s.getNormalIterator());
		assertEquals(WoundIterator::class, s.getNormalIterator()::class);

    }

fun getLength() {

		var s = Segment(
			Vector2(0.0, 1.0),
			Vector2(1.5, 3.0)
		);

		assertEquals(2.500, s.getLength(), 1.0e-3);

    }

fun getLocation() {

		var loc = Segment.getLocation(Vector2(1.0, 1.0), Vector2(), Vector2());
		assertEquals(0.000, loc, 1.0e-3);

		loc = Segment.getLocation(Vector2(1.0, 1.0), Vector2(), Vector2(2.0, 2.0));
		assertEquals(0.000, loc, 1.0e-3);

		loc = Segment.getLocation(Vector2(1.0, 1.0), Vector2(), Vector2(1.0, 0.5));
		assertTrue(loc > 0);

		loc = Segment.getLocation(Vector2(1.0, 1.0), Vector2(), Vector2(1.0, 2.0));
		assertTrue(loc < 0);

		loc = Segment.getLocation(Vector2(1.0, 1.0), Vector2(), Vector2(0.0, 3.0));
		assertTrue(loc < 0);
		loc = Segment.getLocation(Vector2(-1.0, 1.0), Vector2(), Vector2(0.0, 3.0));
		assertTrue(loc > 0);

		loc = Segment.getLocation(Vector2(1.0, 1.0), Vector2(0.0, 0.0), Vector2(1.0, 0.0));
		assertTrue(loc > 0);
		loc = Segment.getLocation(Vector2(1.0, -1.0), Vector2(0.0, 0.0), Vector2(1.0, 0.0));
		assertTrue(loc < 0);

    }

fun getPointClosest() {

		var pt = Vector2(1.0, -1.0);

		var p = Segment.getPointOnLineClosestToPoint(pt, Vector2(1.0, 1.0), Vector2(1.0, 1.0));
		assertEquals(1.000, p.x, 1.0e-3);
		assertEquals(1.000, p.y, 1.0e-3);

		p = Segment.getPointOnSegmentClosestToPoint(pt, Vector2(1.0, 1.0), Vector2(1.0, 1.0));
		assertEquals(1.000, p.x, 1.0e-3);
		assertEquals(1.000, p.y, 1.0e-3);

		p = Segment.getPointOnLineClosestToPoint(pt, Vector2(), Vector2(5.0, 5.0));

		assertEquals(0.000, p.x, 1.0e-3);
		assertEquals(0.000, p.y, 1.0e-3);

		p = Segment(Vector2(), Vector2(5.0, 5.0)).getPointOnLineClosestToPoint(pt);

		assertEquals(0.000, p.x, 1.0e-3);
		assertEquals(0.000, p.y, 1.0e-3);

		p = Segment.getPointOnLineClosestToPoint(pt, Vector2(), Vector2(2.5, 5.0));
		assertEquals(-0.200, p.x, 1.0e-3);
		assertEquals(-0.400, p.y, 1.0e-3);

		p = Segment(Vector2(), Vector2(2.5, 5.0)).getPointOnLineClosestToPoint(pt);
		assertEquals(-0.200, p.x, 1.0e-3);
		assertEquals(-0.400, p.y, 1.0e-3);

		p = Segment.getPointOnSegmentClosestToPoint(pt, Vector2(-1.0, -1.0), Vector2(1.0, 1.0));

		assertEquals(0.000, p.x, 1.0e-3);
		assertEquals(0.000, p.y, 1.0e-3);

		p = Segment(Vector2(-1.0, -1.0), Vector2(1.0, 1.0)).getPointOnSegmentClosestToPoint(pt);

		assertEquals(0.000, p.x, 1.0e-3);
		assertEquals(0.000, p.y, 1.0e-3);

		p = Segment.getPointOnSegmentClosestToPoint(pt, Vector2(), Vector2(2.5, 5.0));
		assertEquals(0.000, p.x, 1.0e-3);
		assertEquals(0.000, p.y, 1.0e-3);

		p = Segment(Vector2(), Vector2(2.5, 5.0)).getPointOnSegmentClosestToPoint(pt);
		assertEquals(0.000, p.x, 1.0e-3);
		assertEquals(0.000, p.y, 1.0e-3);

    }

fun getAxes() {

		var s = Segment(
			Vector2(0.0, 1.0),
			Vector2(1.5, 3.0)
		);
		var t = Transform();

		var axes = s.getAxes(null, t);

		assertEquals(2, axes.size);

		var seg = s.getVertices()[0].to(s.getVertices()[1]);

		assertEquals(0.000, seg.cross(axes[1]), 1.0e-3);
		assertEquals(0.000, seg.dot(axes[0]), 1.0e-3);

		t.translate(1.0, 0.0);
		t.rotate(Math.toRadians(25));

		axes = s.getAxes(null, t);

		seg = t.getTransformed(s.getVertices()[0]).to(t.getTransformed(s.getVertices()[1]));

		assertEquals(0.000, seg.cross(axes[1]), 1.0e-3);
		assertEquals(0.000, seg.dot(axes[0]), 1.0e-3);

		var f = Vector2(2.0, -2.0);
		t.identity();

		axes = s.getAxes(arrayOf(f), t);

		assertEquals(3, axes.size);

		var v1 = s.getVertices()[0].to(f);
		v1.normalize();

		assertEquals(v1.x, axes[2].x, 1.0e-3);
		assertEquals(v1.y, axes[2].y, 1.0e-3);

    }

fun getFoci() {

		var s = Segment(
			Vector2(0.0, 1.0),
			Vector2(1.5, 3.0)
		);
		var t = Transform();

		var foci = s.getFoci(t);
		assertNull(foci);

    }

fun contains() {

		var s = Segment(
			Vector2(0.0, 1.0),
			Vector2(1.5, 3.0)
		);
		var t = Transform();

		assertFalse(s.contains(Vector2(2.0, 2.0), t));
		assertFalse(s.contains(Vector2(2.0, 2.0), t, false));
		assertTrue(s.contains(Vector2(0.75, 2.0), t));
		assertFalse(s.contains(Vector2(0.75, 2.0), t, false));

    }

fun containsRadius() {

		var s = Segment(
				Vector2(1.0, 1.0),
				Vector2(-1.0, -1.0)
			);
			var t = Transform();

			assertFalse(s.contains(Vector2(2.0, 2.0), t, 0.1));
			assertTrue(s.contains(Vector2(1.05, 1.05), t, 0.1));
			assertFalse(s.contains(Vector2(1.05, 1.05), t, 0.0));
			assertFalse(s.contains(Vector2(1.05, 1.05), t, 0.05));
			assertTrue(s.contains(Vector2(0.505, 0.5), t, 0.1));

    }

fun project() {

		var s = Segment(
			Vector2(0.0, 1.0),
			Vector2(1.5, 3.0)
		);
		var t = Transform();
		var n = Vector2(1.0, 0.0);

		var i = s.project(n, t);

		assertEquals(0.000, i.getMin(), 1.0e-3);
		assertEquals(1.500, i.getMax(), 1.0e-3);

		n.set(1.0, 1.0);
		i = s.project(n, t);

		assertEquals(1.000, i.getMin(), 1.0e-3);
		assertEquals(4.500, i.getMax(), 1.0e-3);

		n.set(0.0, 1.0);
		i = s.project(n, t);

		assertEquals(1.000, i.getMin(), 1.0e-3);
		assertEquals(3.000, i.getMax(), 1.0e-3);

		t.translate(1.0, 2.0);
		t.rotate(Math.toRadians(90), t.getTransformed(s.getCenter()));

		i = s.project(n, t);

		assertEquals(3.250, i.getMin(), 1.0e-3);
		assertEquals(4.750, i.getMax(), 1.0e-3);

    }

fun getFarthest() {

		var s = Segment(
			Vector2(0.0, 1.0),
			Vector2(1.5, 3.0)
		);
		var t = Transform();
		var n = Vector2(1.0, 0.0);

		var f = s.getFarthestFeature(n, t);
		assertEquals(1.500, f.getMaximum()!!.getPoint()!!.x, 1.0e-3);
		assertEquals(3.000, f.getMaximum()!!.getPoint()!!.y, 1.0e-3);

		assertEquals(0.000, f.getVertex1()!!.getPoint()!!.x, 1.0e-3);
		assertEquals(1.000, f.getVertex1()!!.getPoint()!!.y, 1.0e-3);
		assertEquals(1.500, f.getVertex2()!!.getPoint()!!.x, 1.0e-3);
		assertEquals(3.000, f.getVertex2()!!.getPoint()!!.y, 1.0e-3);

		var p = s.getFarthestPoint(n, t);
		assertEquals(1.500, p.x, 1.0e-3);
		assertEquals(3.000, p.y, 1.0e-3);

		t.translate(0.0, -1.0);
		t.rotate(Math.toRadians(45));

		p = s.getFarthestPoint(n, t);
		assertEquals(0.000, p.x, 1.0e-3);
		assertEquals(0.000, p.y, 1.0e-3);

    }

fun rotate() {

		var s = Segment(
			Vector2(0.0, 0.0),
			Vector2(1.0, 1.0)
		);
		s.rotate(Math.toRadians(45), 0.0, 0.0);

		assertEquals(0.000, s.getVertices()[0].x, 1.0e-3);
		assertEquals(0.000, s.getVertices()[0].y, 1.0e-3);

		assertEquals(0.000, s.getVertices()[1].x, 1.0e-3);
		assertEquals(1.414, s.getVertices()[1].y, 1.0e-3);

    }

fun translate() {

		var s = Segment(
			Vector2(0.0, 0.0),
			Vector2(1.0, 1.0)
		);
		s.translate(2.0, -1.0);

		assertEquals( 2.000, s.getVertices()[0].x, 1.0e-3);
		assertEquals(-1.000, s.getVertices()[0].y, 1.0e-3);
		assertEquals( 3.000, s.getVertices()[1].x, 1.0e-3);
		assertEquals( 0.000, s.getVertices()[1].y, 1.0e-3);

    }

fun createAABB() {

		var s = Segment(
			Vector2(0.0, 0.0),
			Vector2(1.0, 1.0)
		);

		var aabb = s.createAABB(IDENTITY);
		assertEquals(0.0, aabb.getMinX(), 1.0e-3);
		assertEquals(0.0, aabb.getMinY(), 1.0e-3);
		assertEquals(1.0, aabb.getMaxX(), 1.0e-3);
		assertEquals(1.0, aabb.getMaxY(), 1.0e-3);

		var aabb2 = s.createAABB();
		assertEquals(aabb.getMinX(), aabb2.getMinX());
		assertEquals(aabb.getMinY(), aabb2.getMinY());
		assertEquals(aabb.getMaxX(), aabb2.getMaxX());
		assertEquals(aabb.getMaxY(), aabb2.getMaxY());

		var tx = Transform();
		tx.rotate(Math.toRadians(30.0));
		tx.translate(1.0, 2.0);
		aabb = s.createAABB(tx);
		assertEquals(1.0, aabb.getMinX(), 1.0e-3);
		assertEquals(2.0, aabb.getMinY(), 1.0e-3);
		assertEquals(1.366, aabb.getMaxX(), 1.0e-3);
		assertEquals(3.366, aabb.getMaxY(), 1.0e-3);

    }

fun getLineIntersection() {

		var p = Segment.getLineIntersection(
				Vector2(-1.0, -1.0), Vector2(2.0, 0.0),
				Vector2(-1.0,  0.0), Vector2(1.0, 0.5));

		assertNotNull(p);
		assertEquals(11.0, p.x);
		assertEquals(3.0, p.y);

		p = Segment(Vector2(-1.0, -1.0), Vector2(2.0, 0.0)).getLineIntersection(
				Segment(Vector2(-1.0,  0.0), Vector2(1.0, 0.5)));

		assertNotNull(p);
		assertEquals(11.0, p.x);
		assertEquals(3.0, p.y);

		p = Segment.getLineIntersection(
				Vector2(-1.0, 1.0), Vector2(2.0, 1.0),
				Vector2(-1.0, 0.0), Vector2(1.0, 0.5));

		assertNotNull(p);
		assertEquals(3.0, p.x);
		assertEquals(1.0, p.y);

		p = Segment.getLineIntersection(
				Vector2(3.0, 0.0), Vector2(3.0, 1.0),
				Vector2(-1.0, 0.0), Vector2(1.0, 0.5));

		assertNotNull(p);
		assertEquals(3.0, p.x);
		assertEquals(1.0, p.y);

		p = Segment.getLineIntersection(
				Vector2(3.0, 0.0), Vector2(3.0, -2.0),
				Vector2(0.0, 1.0), Vector2(4.0, 1.0));

		assertNotNull(p);
		assertEquals(3.0, p.x);
		assertEquals(1.0, p.y);

		p = Segment.getLineIntersection(
				Vector2(-2.0, -1.0), Vector2(-1.0, 0.0),
				Vector2(-1.0, -1.0), Vector2(0.0, 0.0));

		assertNull(p);

		p = Segment.getLineIntersection(
				Vector2(3.0, 0.0), Vector2(3.0, 1.0),
				Vector2(2.0, 0.0), Vector2(2.0, 1.0));

		assertNull(p);

		p = Segment.getLineIntersection(
				Vector2(3.0, 1.0), Vector2(4.0, 1.0),
				Vector2(2.0, 2.0), Vector2(4.0, 2.0));

		assertNull(p);

		p = Segment.getLineIntersection(
				Vector2(-1.0, -1.0), Vector2(1.0, 1.0),
				Vector2(-2.0, -2.0), Vector2(-1.5, -1.5));

		assertNull(p);

		p = Segment.getLineIntersection(
				Vector2(3.0, 0.0), Vector2(3.0, 1.0),
				Vector2(3.0, 2.0), Vector2(3.0, 7.0));

		assertNull(p);

		p = Segment.getLineIntersection(
				Vector2(4.0, 1.0), Vector2(5.0, 1.0),
				Vector2(-1.0, 1.0), Vector2(1.0, 1.0));

		assertNull(p);

    }

fun getSegmentIntersection() {

		var p = Segment.getSegmentIntersection(
				Vector2(-3.0, -1.0), Vector2(3.0, 1.0),
				Vector2(-1.0, -2.0), Vector2(1.0, 2.0));

		assertNotNull(p);
		assertEquals(0.0, p.x);
		assertEquals(0.0, p.y);

		p = Segment.getSegmentIntersection(
				Vector2(-3.0, -1.0), Vector2(3.0, 1.0),
				Vector2(-1.0, -2.0), Vector2(1.0, 2.0),
				false);

		assertNotNull(p);
		assertEquals(0.0, p.x);
		assertEquals(0.0, p.y);

		p = Segment.getSegmentIntersection(
				Vector2(-1.0, -1.0), Vector2(2.0, 0.0),
				Vector2(-1.0,  0.0), Vector2(1.0, 0.5));

		assertNull(p);

		p = Segment.getSegmentIntersection(
				Vector2(-1.0, -1.0), Vector2(2.0, 0.0),
				Vector2(-1.0,  0.0), Vector2(1.0, 0.5),
				false);

		assertNull(p);

		p = Segment.getSegmentIntersection(
				Vector2(-1.0, 1.0), Vector2(2.0, 1.0),
				Vector2(-1.0, 0.0), Vector2(1.0, 2.0));

		assertNotNull(p);
		assertEquals(0.0, p.x);
		assertEquals(1.0, p.y);

		p = Segment.getSegmentIntersection(
				Vector2(-1.0, 1.0), Vector2(2.0, 1.0),
				Vector2(-1.0, 0.0), Vector2(1.0, 2.0),
				false);

		assertNotNull(p);
		assertEquals(0.0, p.x);
		assertEquals(1.0, p.y);

		p = Segment.getSegmentIntersection(
				Vector2(3.0, 0.0), Vector2(3.0, 3.0),
				Vector2(4.0, 0.0), Vector2(1.0, 3.0));

		assertNotNull(p);
		assertEquals(3.0, p.x);
		assertEquals(1.0, p.y);

		p = Segment.getSegmentIntersection(
				Vector2(3.0, 0.0), Vector2(3.0, 3.0),
				Vector2(4.0, 0.0), Vector2(1.0, 3.0),
				false);

		assertNotNull(p);
		assertEquals(3.0, p.x);
		assertEquals(1.0, p.y);

		p = Segment.getSegmentIntersection(
				Vector2(3.0, 2.0), Vector2(3.0, -2.0),
				Vector2(0.0, 1.0), Vector2(4.0, 1.0));

		assertNotNull(p);
		assertEquals(3.0, p.x);
		assertEquals(1.0, p.y);

		p = Segment.getSegmentIntersection(
				Vector2(3.0, 2.0), Vector2(3.0, -2.0),
				Vector2(0.0, 1.0), Vector2(4.0, 1.0),
				false);

		assertNotNull(p);
		assertEquals(3.0, p.x);
		assertEquals(1.0, p.y);

		p = Segment.getSegmentIntersection(
				Vector2(-2.0, -1.0), Vector2(-1.0, 0.0),
				Vector2(-1.0, -1.0), Vector2(0.0, 0.0));

		assertNull(p);

		p = Segment.getSegmentIntersection(
				Vector2(-2.0, -1.0), Vector2(-1.0, 0.0),
				Vector2(-1.0, -1.0), Vector2(0.0, 0.0),
				false);

		assertNull(p);

		p = Segment.getSegmentIntersection(
				Vector2(3.0, 0.0), Vector2(3.0, 1.0),
				Vector2(2.0, 0.0), Vector2(2.0, 1.0));

		assertNull(p);

		p = Segment.getSegmentIntersection(
				Vector2(3.0, 0.0), Vector2(3.0, 1.0),
				Vector2(2.0, 0.0), Vector2(2.0, 1.0),
				false);

		assertNull(p);

		p = Segment.getSegmentIntersection(
				Vector2(3.0, 1.0), Vector2(4.0, 1.0),
				Vector2(3.0, 2.0), Vector2(4.0, 2.0));

		assertNull(p);

		p = Segment.getSegmentIntersection(
				Vector2(3.0, 1.0), Vector2(4.0, 1.0),
				Vector2(3.0, 2.0), Vector2(4.0, 2.0),
				false);

		assertNull(p);

		p = Segment.getSegmentIntersection(
				Vector2(-1.0, -1.0), Vector2(1.0, 1.0),
				Vector2(-2.0, -2.0), Vector2(-1.5, -1.5));

		assertNull(p);

		p = Segment.getSegmentIntersection(
				Vector2(-1.0, -1.0), Vector2(1.0, 1.0),
				Vector2(-2.0, -2.0), Vector2(-1.5, -1.5),
				false);

		assertNull(p);

		p = Segment.getSegmentIntersection(
				Vector2(3.0, 0.0), Vector2(3.0, 1.0),
				Vector2(3.0, -1.0), Vector2(3.0, 7.0));

		assertNull(p);

		p = Segment.getSegmentIntersection(
				Vector2(3.0, 0.0), Vector2(3.0, 1.0),
				Vector2(3.0, -1.0), Vector2(3.0, 7.0),
				false);

		assertNull(p);

		p = Segment.getSegmentIntersection(
				Vector2(-1.0, 1.0), Vector2(5.0, 1.0),
				Vector2(-1.0, 1.0), Vector2(1.0, 1.0));

		assertNull(p);

		p = Segment.getSegmentIntersection(
				Vector2(-1.0, 1.0), Vector2(5.0, 1.0),
				Vector2(-1.0, 1.0), Vector2(1.0, 1.0),
				false);

		assertNull(p);

		p = Segment.getSegmentIntersection(
				Vector2(1.0, 0.0), Vector2(3.0, -2.0),
				Vector2(-1.0, -1.0), Vector2(1.0, 0.0));

		assertNotNull(p);
		assertEquals(1.0, p.x);
		assertEquals(0.0, p.y);

		p = Segment.getSegmentIntersection(
				Vector2(1.0, 0.0), Vector2(3.0, -2.0),
				Vector2(-1.0, -1.0), Vector2(1.0, 0.0),
				false);

		assertNull(p);

		var s1 = Segment(Vector2(-10.0, 10.0), Vector2(10.0, 10.0));
		var s2 = Segment(Vector2(0.0, 0.0), Vector2(0.0, 5.0));
		p = s2.getSegmentIntersection(s1);
		assertNull(p);

    }

fun createMass() {

		var s = Segment(Vector2(-1.0, 0.0), Vector2(1.0, 0.5));
		var m = s.createMass(1.0);

		assertEquals(2.061, m.getMass(), 1.0e-3);

		assertEquals(0.730, m.getInertia(), 1.0e-3);

		m = s.createMass(0.0);
		assertEquals(0.000, m.getMass(), 1e-3);
		assertEquals(0.000, m.getInertia(), 1e-3);
		assertEquals(0.000, m.getInverseMass(), 1e-3);
		assertEquals(0.000, m.getInverseInertia(), 1e-3);
		assertEquals(0.000, m.getCenter().x, 1e-3);
		assertEquals(0.250, m.getCenter().y, 1e-3);
		assertEquals(MassType.INFINITE, m.getType());

    }

fun getArea() {

		var s = Segment(Vector2(-1.0, 0.0), Vector2(1.0, 0.5));

		assertEquals(0.0, s.getArea(), 1.0e-3);

    }

fun getNormals() {

		var p = Segment(
				Vector2(0.0, 1.0),
				Vector2(-1.0, 0.0));

		var normals = p.getNormals();

		assertNotNull(normals);
		assertEquals(2, normals.size);
		assertEquals(-0.707, normals[0].x, 1e-3);
		assertEquals(-0.707, normals[0].y, 1e-3);
		assertEquals( 0.707, normals[1].x, 1e-3);
		assertEquals(-0.707, normals[1].y, 1e-3);

		var iterator = p.getNormalIterator();

		assertNotNull(iterator);
		assertEquals(WoundIterator::class, iterator::class);
		while (iterator.hasNext()) {
			iterator.next();
		}

    }

fun copy() {

		var seg = Segment(
				Vector2(0.0, 1.0),
				Vector2(-1.0, 0.0));
		seg.setUserData(Any());

		var copy = seg.copy();

		assertNotSame(seg, copy);
		assertNotSame(seg.getCenter(), copy.getCenter());
		assertNotSame(seg.getNormals(), copy.getNormals());
		assertNotSame(seg.getVertices(), copy.getVertices());
		assertEquals(seg.getLength(), copy.getLength());
		assertEquals(seg.getRadius(), copy.getRadius());
		assertNull(copy.getUserData());

		assertEquals(seg.getCenter().x, copy.getCenter().x);
		assertEquals(seg.getCenter().y, copy.getCenter().y);

		assertEquals(seg.getNormals().size, copy.getNormals().size);
		for (i in 0 until seg.getNormals().size) {
			assertEquals(seg.getNormals()[i].x, copy.getNormals()[i].x);
			assertEquals(seg.getNormals()[i].y, copy.getNormals()[i].y);
		}

		assertEquals(seg.getVertices().size, copy.getVertices().size);
		for (i in 0 until seg.getVertices().size) {
			assertEquals(seg.getVertices()[i].x, copy.getVertices()[i].x);
			assertEquals(seg.getVertices()[i].y, copy.getVertices()[i].y);
		}

    }

}
