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

import org.dyn4j.geometry.*
import org.dyn4j.Epsilon
import kotlin.test.*

class RectangleTest {
    @Test
    fun createInvalidWidth() {
        assertFailsWith<IllegalArgumentException> {

		Rectangle(-1.0, 3.0);

        }
    }

    @Test
    fun createInvalidHeight() {
        assertFailsWith<IllegalArgumentException> {

		Rectangle(2.0, 0.0);

        }
    }

    @Test
    fun createSuccess() {

		var r = Rectangle(2.0, 2.0);

		assertEquals(0.000, r.getCenter().x, 1.0e-3);
		assertEquals(0.000, r.getCenter().y, 1.0e-3);

		assertEquals(-1.000, r.getVertices()[0].x, 1.0e-3);
		assertEquals(-1.000, r.getVertices()[0].y, 1.0e-3);

		assertEquals( 1.000, r.getVertices()[1].x, 1.0e-3);
		assertEquals(-1.000, r.getVertices()[1].y, 1.0e-3);

		assertEquals( 1.000, r.getVertices()[2].x, 1.0e-3);
		assertEquals( 1.000, r.getVertices()[2].y, 1.0e-3);

		assertEquals(-1.000, r.getVertices()[3].x, 1.0e-3);
		assertEquals( 1.000, r.getVertices()[3].y, 1.0e-3);

		assertNotNull(r.toString());

    }

    @Test
    fun getAxes() {

		var r = Rectangle(1.0, 1.0);
		var t = Transform();
		var axes = r.getAxes(null, t);

		assertEquals(2, axes.size);

		var ab = r.getVertices()[0].to(r.getVertices()[1]);
		var ad = r.getVertices()[0].to(r.getVertices()[3]);

		assertEquals(0.000, ab.dot(axes[1]), 1.0e-3);
		assertEquals(0.000, ad.dot(axes[0]), 1.0e-3);

		var pt = Vector2(2.0, -1.0);
		axes = r.getAxes(arrayOf(pt), t);

		assertEquals(3, axes.size);

		assertEquals(0.000, r.getVertices()[1].to(pt).cross(axes[2]), 1.0e-3);

    }

    @Test
    fun contains() {

		var r = Rectangle(1.0, 2.0);
		var t = Transform();

		var pt = Vector2(2.0, 0.5);

		assertTrue(!r.contains(pt, t));
		assertTrue(!r.contains(pt, t, false));

		t.translate(2.0, 0.0);
		t.rotate(Math.toRadians(30), r.getCenter());

		assertTrue(r.contains(pt, t));
		assertTrue(r.contains(pt, t, false));

		t.identity();
		pt.set(0.5, 0.5);

		assertTrue(r.contains(pt, t));
		assertFalse(r.contains(pt, t, false));

    }

    @Test
    fun project() {

		var r = Rectangle(2.0, 1.0);
		var t = Transform();

		var axis = Vector2(1.0, 0.0);

		var i = r.project(axis, t);

		assertEquals(-1.000, i.getMin(), 1.0e-3);
		assertEquals( 1.000, i.getMax(), 1.0e-3);

		t.translate(1.0, 1.0);
		t.rotate(Math.toRadians(30), t.getTransformed(r.getCenter()));

		i = r.project(axis, t);

		assertEquals(-0.116, i.getMin(), 1.0e-3);
		assertEquals( 2.116, i.getMax(), 1.0e-3);

		axis.set(0.0, 1.0);

		i = r.project(axis, t);

		assertEquals(0.066, i.getMin(), 1.0e-3);
		assertEquals(1.933, i.getMax(), 1.0e-3);

    }

    @Test
    fun getRotation() {

		var r = Geometry.createRectangle(1.0, 1.0);
		r.translate(1.0, 1.0);
		r.rotate(Math.toRadians(30));

		assertEquals(30.0, Math.toDegrees(r.getRotationAngle()), 1.0e-3);

		var rt = r.getRotation();
		assertEquals(30.0, rt.toDegrees(), 1.0e-3);

    }

    @Test
    fun createMass() {

		var r = Rectangle(1.0, 1.0);
		var m = r.createMass(1.5);

		assertEquals(1.500, m.getMass(), 1.0e-3);
		assertEquals(0.250, m.getInertia(), 1.0e-3);

		m = r.createMass(0.0);
		assertEquals(0.000, m.getMass(), 1e-3);
		assertEquals(0.000, m.getInertia(), 1e-3);
		assertEquals(0.000, m.getInverseMass(), 1e-3);
		assertEquals(0.000, m.getInverseInertia(), 1e-3);
		assertEquals(0.000, m.getCenter().x, 1e-3);
		assertEquals(0.000, m.getCenter().y, 1e-3);
		assertEquals(MassType.INFINITE, m.getType());

    }

    @Test
    fun getArea() {

		var r = Rectangle(1.0, 1.0);
		assertEquals(1.0, r.getArea(), 1.0e-3);

		r = Rectangle(2.5, 3.0);
		assertEquals(7.5, r.getArea(), 1.0e-3);

    }

    @Test
    fun computeAABB() {

		var r = Rectangle(1.0, 1.0);
		var aabb = r.createAABB();
		assertEquals(0.5, aabb.getMaxX(), 1e-8);
		assertEquals(0.5, aabb.getMaxY(), 1e-8);
		assertEquals(-0.5, aabb.getMinX(), 1e-8);
		assertEquals(-0.5, aabb.getMinY(), 1e-8);

		r.rotate(Math.toRadians(45.0));
		aabb = r.createAABB();
		assertEquals(0.707, aabb.getMaxX(), 1e-3);
		assertEquals(0.707, aabb.getMaxY(), 1e-3);
		assertEquals(-0.707, aabb.getMinX(), 1e-3);
		assertEquals(-0.707, aabb.getMinY(), 1e-3);

    }

    @Test
    fun copy() {

		var rect = Rectangle(1.0, 1.0);
		rect.setUserData(Any());
		var copy = rect.copy();

		assertNotSame(rect, copy);
		assertNotSame(rect.getCenter(), copy.getCenter());
		assertNotSame(rect.getNormals(), copy.getNormals());
		assertNotSame(rect.getVertices(), copy.getVertices());
		assertEquals(rect.getRadius(), copy.getRadius());
		assertEquals(rect.getHeight(), copy.getHeight());
		assertEquals(rect.getWidth(), copy.getWidth());
		assertNull(copy.getUserData());

		assertEquals(rect.getCenter().x, copy.getCenter().x);
		assertEquals(rect.getCenter().y, copy.getCenter().y);

		assertEquals(rect.getNormals().size, copy.getNormals().size);
		for (i in 0 until rect.getNormals().size) {
			assertEquals(rect.getNormals()[i].x, copy.getNormals()[i].x);
			assertEquals(rect.getNormals()[i].y, copy.getNormals()[i].y);
		}

		assertEquals(rect.getVertices().size, copy.getVertices().size);
		for (i in 0 until rect.getVertices().size) {
			assertEquals(rect.getVertices()[i].x, copy.getVertices()[i].x);
			assertEquals(rect.getVertices()[i].y, copy.getVertices()[i].y);
		}

    }

}
