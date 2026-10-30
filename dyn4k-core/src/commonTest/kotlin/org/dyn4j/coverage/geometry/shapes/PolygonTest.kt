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

val PolygonTest by testSuite {
    test("createNotEnoughPoints") { PolygonTestFixture().run { createNotEnoughPoints() } }
    test("createNotCCW") { PolygonTestFixture().run { createNotCCW() } }
    test("createCCW") { PolygonTestFixture().run { createCCW() } }
    test("createCoincident") { PolygonTestFixture().run { createCoincident() } }
    test("createNonConvex") { PolygonTestFixture().run { createNonConvex() } }
    test("createDegenerate") { PolygonTestFixture().run { createDegenerate() } }
    test("createNullPoint") { PolygonTestFixture().run { createNullPoint() } }
    test("createSuccess") { PolygonTestFixture().run { createSuccess() } }
    test("contains") { PolygonTestFixture().run { contains() } }
    test("project") { PolygonTestFixture().run { project() } }
    test("getFarthest") { PolygonTestFixture().run { getFarthest() } }
    test("getAxes") { PolygonTestFixture().run { getAxes() } }
    test("getFoci") { PolygonTestFixture().run { getFoci() } }
    test("rotate") { PolygonTestFixture().run { rotate() } }
    test("translate") { PolygonTestFixture().run { translate() } }
    test("createAABB") { PolygonTestFixture().run { createAABB() } }
    test("containsPointCoIncidentStart") { PolygonTestFixture().run { containsPointCoIncidentStart() } }
    test("containsPointCoIncidentMid") { PolygonTestFixture().run { containsPointCoIncidentMid() } }
    test("containsPointCoIncidentWithCoincidentEdges") { PolygonTestFixture().run { containsPointCoIncidentWithCoincidentEdges() } }
    test("containsPointCoIncidentWithCoincidentEdges2") { PolygonTestFixture().run { containsPointCoIncidentWithCoincidentEdges2() } }
    test("getNormals") { PolygonTestFixture().run { getNormals() } }
    test("createMass") { PolygonTestFixture().run { createMass() } }
    test("getArea") { PolygonTestFixture().run { getArea() } }
    test("copy") { PolygonTestFixture().run { copy() } }
}

private class PolygonTestFixture  {
    private val IDENTITY = Transform()
fun createNotEnoughPoints() {
        assertFailsWith<IllegalArgumentException> {

		Polygon(*arrayOf(
			Vector2(),
			Vector2()
		));

        }
    }

fun createNotCCW() {
        assertFailsWith<IllegalArgumentException> {

		Polygon(*arrayOf(
			Vector2(),
			Vector2(2.0, 2.0),
			Vector2(1.0, 0.0)
		));

        }
    }

fun createCCW() {

		Polygon(*arrayOf(
			Vector2(0.5, 0.5),
			Vector2(-0.3, -0.5),
			Vector2(1.0, -0.3)
		));

    }

fun createCoincident() {
        assertFailsWith<IllegalArgumentException> {

		Polygon(*arrayOf(
			Vector2(),
			Vector2(2.0, 2.0),
			Vector2(2.0, 2.0),
			Vector2(1.0, 0.0)
		));

        }
    }

fun createNonConvex() {
        assertFailsWith<IllegalArgumentException> {

		Polygon(*arrayOf(
			Vector2(1.0, 1.0),
			Vector2(-1.0, 1.0),
			Vector2(-0.5, 0.0),
			Vector2(-1.0, -1.0),
			Vector2(1.0, -1.0)
		));

        }
    }

fun createDegenerate() {
        assertFailsWith<IllegalArgumentException> {

		Polygon(*arrayOf(
			Vector2(1.0, 0.0),
			Vector2(2.0, 0.0),
			Vector2(1.0, 0.0)
		));

        }
    }

fun createNullPoint() {
        assertFailsWith<NullPointerException> {

		Polygon(*arrayOf(
			Vector2(),
			null,
			Vector2(0.0, 2.0)
		));

        }
    }

fun createSuccess() {

		Polygon(*arrayOf(
			Vector2(0.0, 1.0),
			Vector2(-2.0, -2.0),
			Vector2(1.0, -2.0)
		));

    }

fun contains() {

		var vertices = arrayOf(
			Vector2(0.0, 1.0),
			Vector2(-1.0, 0.0),
			Vector2(1.0, 0.0)
		);
		var p = Polygon(*vertices);

		var t = Transform();
		var pt = Vector2(2.0, 4.0);

		assertTrue(!p.contains(pt, t));
		assertTrue(!p.contains(pt, t, false));

		t.translate(2.0, 3.5);

		assertTrue(p.contains(pt, t));
		assertTrue(p.contains(pt, t, false));

		t.translate(0.0, -0.5);

		assertTrue(p.contains(pt, t));
		assertFalse(p.contains(pt, t, false));

		t.translate(0.5, 0.5);

		assertTrue(p.contains(pt, t));
		assertFalse(p.contains(pt, t, false));

		t.translate(-1.0, -1.0);

		assertFalse(p.contains(pt, t));
		assertFalse(p.contains(pt, t, false));

    }

fun project() {

		var vertices = arrayOf(
				Vector2(0.0, 1.0),
				Vector2(-1.0, 0.0),
				Vector2(1.0, 0.0)
			);
		var p = Polygon(*vertices);
		var t = Transform();
		var x = Vector2(1.0, 0.0);
		var y = Vector2(0.0, 1.0);

		t.translate(1.0, 0.5);

		var i = p.project(x, t);

		assertEquals(0.000, i.getMin(), 1.0e-3);
		assertEquals(2.000, i.getMax(), 1.0e-3);

		t.rotate(Math.toRadians(90), 1.0, 0.5);

		i = p.project(y, t);

		assertEquals(-0.500, i.getMin(), 1.0e-3);
		assertEquals(1.500, i.getMax(), 1.0e-3);

    }

fun getFarthest() {

		var vertices = arrayOf(
				Vector2(0.0, 1.0),
				Vector2(-1.0, -1.0),
				Vector2(1.0, -1.0)
			);
		var p = Polygon(*vertices);
		var t = Transform();
		var y = Vector2(0.0, -1.0);

		var f = p.getFarthestFeature(y, t);

		assertEquals(-1.000, f.getMaximum()!!.getPoint()!!.x, 1.0e-3);
		assertEquals(-1.000, f.getMaximum()!!.getPoint()!!.y, 1.0e-3);
		assertEquals(-1.000, f.getVertex1()!!.getPoint()!!.x, 1.0e-3);
		assertEquals(-1.000, f.getVertex1()!!.getPoint()!!.y, 1.0e-3);
		assertEquals( 1.000, f.getVertex2()!!.getPoint()!!.x, 1.0e-3);
		assertEquals(-1.000, f.getVertex2()!!.getPoint()!!.y, 1.0e-3);

		var pt = p.getFarthestPoint(y, t);

		assertEquals(-1.000, pt.x, 1.0e-3);
		assertEquals(-1.000, pt.y, 1.0e-3);

		t.rotate(Math.toRadians(90), 0.0, 0.0);

		pt = p.getFarthestPoint(y, t);

		assertEquals( 1.000, pt.x, 1.0e-3);
		assertEquals(-1.000, pt.y, 1.0e-3);

    }

fun getAxes() {

		var vertices = arrayOf(
				Vector2(0.0, 1.0),
				Vector2(-1.0, -1.0),
				Vector2(1.0, -1.0)
			);
		var p = Polygon(*vertices);
		var t = Transform();

		var axes = p.getAxes(null, t);
		assertNotNull(axes);
		assertEquals(3, axes.size);

		var pt = Vector2(-3.0, 2.0);
		axes = p.getAxes(arrayOf(pt), t);
		assertEquals(4, axes.size);

		var ab = p.getVertices()[0].to(p.getVertices()[1]);
		var bc = p.getVertices()[1].to(p.getVertices()[2]);
		var ca = p.getVertices()[2].to(p.getVertices()[0]);

		assertEquals(0.000, ab.dot(axes[0]), 1.0e-3);
		assertEquals(0.000, bc.dot(axes[1]), 1.0e-3);
		assertEquals(0.000, ca.dot(axes[2]), 1.0e-3);

		assertEquals(0.000, p.getVertices()[0].to(pt).cross(axes[3]), 1.0e-3);

    }

fun getFoci() {

		var vertices = arrayOf(
				Vector2(0.0, 1.0),
				Vector2(-1.0, -1.0),
				Vector2(1.0, -1.0)
			);
		var p = Polygon(*vertices);
		var t = Transform();

		var foci = p.getFoci(t);
		assertNull(foci);

    }

fun rotate() {

		var vertices = arrayOf(
				Vector2(0.0, 1.0),
				Vector2(-1.0, -1.0),
				Vector2(1.0, -1.0)
			);
		var p = Polygon(*vertices);

		p.rotate(Math.toRadians(90), 0.0, 0.0);

		assertEquals(-1.000, p.getVertices()[0].x, 1.0e-3);
		assertEquals( 0.000, p.getVertices()[0].y, 1.0e-3);

		assertEquals( 1.000, p.getVertices()[1].x, 1.0e-3);
		assertEquals(-1.000, p.getVertices()[1].y, 1.0e-3);

		assertEquals( 1.000, p.getVertices()[2].x, 1.0e-3);
		assertEquals( 1.000, p.getVertices()[2].y, 1.0e-3);

    }

fun translate() {

		var vertices = arrayOf(
				Vector2(0.0, 1.0),
				Vector2(-1.0, -1.0),
				Vector2(1.0, -1.0)
			);
		var p = Polygon(*vertices);

		p.translate(1.0, -0.5);

		assertEquals( 1.000, p.getVertices()[0].x, 1.0e-3);
		assertEquals( 0.500, p.getVertices()[0].y, 1.0e-3);

		assertEquals( 0.000, p.getVertices()[1].x, 1.0e-3);
		assertEquals(-1.500, p.getVertices()[1].y, 1.0e-3);

		assertEquals( 2.000, p.getVertices()[2].x, 1.0e-3);
		assertEquals(-1.500, p.getVertices()[2].y, 1.0e-3);

    }

fun createAABB() {

		var vertices = arrayOf(
				Vector2(0.0, 1.0),
				Vector2(-1.0, -1.0),
				Vector2(1.0, -1.0)
			);
		var p = Polygon(*vertices);

		var aabb = p.createAABB(IDENTITY);
		assertEquals(-1.0, aabb.getMinX(), 1.0e-3);
		assertEquals(-1.0, aabb.getMinY(), 1.0e-3);
		assertEquals( 1.0, aabb.getMaxX(), 1.0e-3);
		assertEquals( 1.0, aabb.getMaxY(), 1.0e-3);

		var aabb2 = p.createAABB();
		assertEquals(aabb.getMinX(), aabb2.getMinX());
		assertEquals(aabb.getMinY(), aabb2.getMinY());
		assertEquals(aabb.getMaxX(), aabb2.getMaxX());
		assertEquals(aabb.getMaxY(), aabb2.getMaxY());

		var tx = Transform();
		tx.rotate(Math.toRadians(30.0));
		tx.translate(1.0, 2.0);
		aabb = p.createAABB(tx);
		assertEquals( 0.500, aabb.getMinX(), 1.0e-3);
		assertEquals( 0.634, aabb.getMinY(), 1.0e-3);
		assertEquals( 2.366, aabb.getMaxX(), 1.0e-3);
		assertEquals( 2.866, aabb.getMaxY(), 1.0e-3);

    }

fun containsPointCoIncidentStart() {

		var vertices = arrayOf(
				Vector2(2.0, 0.0),
				Vector2(4.0, 0.0),
				Vector2(7.0, 3.0),
				Vector2(7.0, 5.0),
				Vector2(5.0, 7.0),
				Vector2(3.0, 7.0),
				Vector2(0.0, 4.0),
				Vector2(0.0, 2.0)
			);
		var p = Polygon(*vertices);

		assertFalse(p.contains(Vector2(0.0, 0.0)));

    }

fun containsPointCoIncidentMid() {

		var vertices = arrayOf(
				Vector2(0.0, 4.0),
				Vector2(0.0, 2.0),
				Vector2(2.0, 0.0),
				Vector2(4.0, 0.0),
				Vector2(7.0, 3.0),
				Vector2(7.0, 5.0),
				Vector2(5.0, 7.0),
				Vector2(3.0, 7.0)
			);
		var p = Polygon(*vertices);

		assertFalse(p.contains(Vector2(0.0, 0.0)));

    }

fun containsPointCoIncidentWithCoincidentEdges() {

		var vertices = arrayOf(
				Vector2(2.0, 0.0),
				Vector2(4.0, 0.0),
				Vector2(5.0, 0.0),
				Vector2(7.0, 3.0),
				Vector2(7.0, 5.0),
				Vector2(5.0, 7.0),
				Vector2(3.0, 7.0),
				Vector2(0.0, 4.0),
				Vector2(0.0, 2.0)
			);
		var p = Polygon(*vertices);

		assertFalse(p.contains(Vector2(0.0, 0.0)));

    }

fun containsPointCoIncidentWithCoincidentEdges2() {

		var vertices = arrayOf(
				Vector2(2.0, 0.0),
				Vector2(4.0, 0.0),
				Vector2(5.0, 0.0),
				Vector2(7.0, 3.0),
				Vector2(7.0, 5.0),
				Vector2(5.0, 7.0),
				Vector2(3.0, 7.0),
				Vector2(0.0, 4.0),
				Vector2(0.0, 2.0)
			);
		var p = Polygon(*vertices);

		assertTrue(p.contains(Vector2(4.5, 0.0)));

    }

fun getNormals() {

		var vertices = arrayOf(
			Vector2(0.0, 1.0),
			Vector2(-1.0, 0.0),
			Vector2(1.0, 0.0)
		);
		var p = Polygon(*vertices);

		var normals = p.getNormals();

		assertNotNull(normals);
		assertEquals(3, normals.size);
		assertEquals(-0.707, normals[0].x, 1e-3);
		assertEquals( 0.707, normals[0].y, 1e-3);
		assertEquals( 0.0, normals[1].x, 1e-3);
		assertEquals(-1.0, normals[1].y, 1e-3);
		assertEquals( 0.707, normals[2].x, 1e-3);
		assertEquals( 0.707, normals[2].y, 1e-3);

		var iterator = p.getNormalIterator();

		assertNotNull(iterator);
		assertEquals(WoundIterator::class, iterator::class);
		while (iterator.hasNext()) {
			iterator.next();
		}

    }

fun createMass() {

		var p = Geometry.createUnitCirclePolygon(5, 0.5);
		var m = p.createMass(1.0);

		assertEquals(0.594, m.getMass(), 1.0e-3);
		assertEquals(0.057, m.getInertia(), 1.0e-3);

		m = p.createMass(0.0);
		assertEquals(0.000, m.getMass(), 1e-3);
		assertEquals(0.000, m.getInertia(), 1e-3);
		assertEquals(0.000, m.getInverseMass(), 1e-3);
		assertEquals(0.000, m.getInverseInertia(), 1e-3);
		assertEquals(0.000, m.getCenter().x, 1e-3);
		assertEquals(0.000, m.getCenter().y, 1e-3);
		assertEquals(MassType.INFINITE, m.getType());

    }

fun getArea() {

		var p = Geometry.createUnitCirclePolygon(5, 0.5);
		assertEquals(0.594, p.getArea(), 1.0e-3);

    }

fun copy() {

		var poly = Geometry.createUnitCirclePolygon(5, 0.5);
		poly.setUserData(Any());
		var copy = poly.copy();

		assertNotSame(poly, copy);
		assertNotSame(poly.getCenter(), copy.getCenter());
		assertNotSame(poly.getNormals(), copy.getNormals());
		assertNotSame(poly.getVertices(), copy.getVertices());
		assertEquals(poly.getRadius(), copy.getRadius());
		assertNull(copy.getUserData());

		assertEquals(poly.getCenter().x, copy.getCenter().x);
		assertEquals(poly.getCenter().y, copy.getCenter().y);

		assertEquals(poly.getNormals().size, copy.getNormals().size);
		for (i in 0 until poly.getNormals().size) {
			assertEquals(poly.getNormals()[i].x, copy.getNormals()[i].x);
			assertEquals(poly.getNormals()[i].y, copy.getNormals()[i].y);
		}

		assertEquals(poly.getVertices().size, copy.getVertices().size);
		for (i in 0 until poly.getVertices().size) {
			assertEquals(poly.getVertices()[i].x, copy.getVertices()[i].x);
			assertEquals(poly.getVertices()[i].y, copy.getVertices()[i].y);
		}

    }

}
