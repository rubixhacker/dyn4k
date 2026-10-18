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

class HalfEllipseTest {
    private val IDENTITY = Transform()
    @Test
    fun createZeroWidth() {
        assertFailsWith<IllegalArgumentException> {

		HalfEllipse(0.0, 1.0);

        }
    }

    @Test
    fun createNegativeWidth() {
        assertFailsWith<IllegalArgumentException> {

		HalfEllipse(-1.0, 1.0);

        }
    }

    @Test
    fun createZeroHeight() {
        assertFailsWith<IllegalArgumentException> {

		HalfEllipse(1.0, 0.0);

        }
    }

    @Test
    fun createNegativeHeight() {
        assertFailsWith<IllegalArgumentException> {

		HalfEllipse(1.0, -1.0);

        }
    }

    @Test
    fun createSuccess() {

		var he = HalfEllipse(1.0, 2.0);

		assertEquals(2.0, he.getHeight());
		assertEquals(0.5, he.getHalfWidth());
		assertEquals(1.0, he.getWidth());

		assertNotNull(he.toString());

    }

    @Test
    fun contains() {

		var e = HalfEllipse(2.0, 0.5);
		var t = Transform();
		var p = Vector2(0.75, 0.35);

		assertTrue(!e.contains(p, t));
		assertTrue(!e.contains(p, t, false));

		p.set(0.75, -0.2);
		assertTrue(!e.contains(p, t));
		assertTrue(!e.contains(p, t, false));

		p.set(0.75, 0.35);
		t.translate(0.5, 0.0);

		assertTrue(e.contains(p, t));
		assertTrue(e.contains(p, t, false));

		p.set(1.5, 0.0);

		assertTrue(e.contains(p, t));
		assertFalse(e.contains(p, t, false));

		p.set(0.75, 0.35);
		e.translate(e.getCenter().getNegative());
		assertFalse(e.contains(p, t));
		assertFalse(e.contains(p, t, false));

		e.rotate(Math.toDegrees(90));
		e.translate(0.5, 1.0);

		p.set(0.3, 0.3);
		assertFalse(e.contains(p, t));
		assertFalse(e.contains(p, t, false));

		p.set(0.7, 0.4);
		assertTrue(e.contains(p, t));
		assertTrue(e.contains(p, t, false));

    }

    @Test
    fun project() {

		var e = HalfEllipse(2.0, 0.5);
		var t = Transform();
		var x = Vector2(1.0, 0.0);
		var y = Vector2(0.0, 1.0);

		t.translate(1.0, 0.5);

		var i = e.project(x, t);
		assertEquals( 0.000, i.getMin(), 1.0e-3);
		assertEquals( 2.000, i.getMax(), 1.0e-3);

		i = e.project(y, t);
		assertEquals( 0.500, i.getMin(), 1.0e-3);
		assertEquals( 1.000, i.getMax(), 1.0e-3);

		t.rotate(Math.toRadians(30), t.getTransformed(e.getCenter()));

		i = e.project(y, t);
		assertEquals( 0.028, i.getMin(), 1.0e-3);
		assertEquals( 1.189, i.getMax(), 1.0e-3);

		e.translate(1.0, 0.5);
		e.rotateAboutCenter(Math.toRadians(30));

		i = e.project(y, IDENTITY);
		assertEquals( 0.028, i.getMin(), 1.0e-3);
		assertEquals( 1.189, i.getMax(), 1.0e-3);

		t.identity();
		t.translate(0.0, 1.0);
		i = e.project(y, t);
		assertEquals( 1.028, i.getMin(), 1.0e-3);
		assertEquals( 2.189, i.getMax(), 1.0e-3);

    }

    @Test
    fun getFarthest() {

		var e = HalfEllipse(2.0, 0.5);
		var t = Transform();
		var x = Vector2(1.0, 0.0);
		var y = Vector2(0.0, -1.0);

		t.translate(1.0, 0.5);

		var p = e.getFarthestPoint(x, t);
		assertEquals( 2.000, p.x, 1.0e-3);
		assertEquals( 0.5, p.y, 1.0e-3);

		t.rotate(Math.toRadians(30), 1.0, 0.5);

		p = e.getFarthestPoint(y, t);
		assertEquals( 0.133, p.x, 1.0e-3);
		assertEquals( 0.000, p.y, 1.0e-3);

		e.translate(1.0, 0.5);
		e.rotate(Math.toRadians(30), 1.0, 0.5);

		p = e.getFarthestPoint(y, IDENTITY);
		assertEquals( 0.133, p.x, 1.0e-3);
		assertEquals( 0.000, p.y, 1.0e-3);

		t.identity();
		t.translate(0.0, 1.0);
		p = e.getFarthestPoint(y, t);
		assertEquals( 0.133, p.x, 1.0e-3);
		assertEquals( 1.000, p.y, 1.0e-3);

    }

    @Test
    fun getAxes() {
        assertFailsWith<UnsupportedOperationException> {

		var e = HalfEllipse(1.0, 0.5);
		e.getAxes(arrayOf( Vector2() ), IDENTITY);

        }
    }

    @Test
    fun getFoci() {
        assertFailsWith<UnsupportedOperationException> {

		var e = HalfEllipse(1.0, 0.5);
		e.getFoci(IDENTITY);

        }
    }

    @Test
    fun rotate() {

		var e = HalfEllipse(1.0, 0.25);

		e.translate(1.0, 1.0);
		e.rotateAboutCenter(Math.toRadians(30));
		assertEquals(1.000, e.getCenter().x, 1.0e-3);
		assertEquals(1.106, e.getCenter().y, 1.0e-3);
		assertEquals(Math.toRadians(30), e.getRotationAngle(), 1.0e-3);
		assertEquals(kotlin.math.cos(Math.toRadians(30)), e.getRotation().getCost(), 1.0e-3);
		assertEquals(kotlin.math.sin(Math.toRadians(30)), e.getRotation().getSint(), 1.0e-3);

		e.rotate(Math.toRadians(90));
		assertEquals(-1.106, e.getCenter().x, 1.0e-3);
		assertEquals( 1.000, e.getCenter().y, 1.0e-3);
		assertEquals(Math.toRadians(120), e.getRotationAngle(), 1.0e-3);
		assertEquals(kotlin.math.cos(Math.toRadians(120)), e.getRotation().getCost(), 1.0e-3);
		assertEquals(kotlin.math.sin(Math.toRadians(120)), e.getRotation().getSint(), 1.0e-3);

		e.translate(e.getCenter().getNegative());

		e.rotate(Math.toRadians(90), 1.0, -1.0);
		assertEquals( 0.000, e.getCenter().x, 1.0e-3);
		assertEquals(-2.000, e.getCenter().y, 1.0e-3);

    }

    @Test
    fun translate() {

		var e = HalfEllipse(1.0, 0.25);

		e.translate(1.0, -0.5);

		assertEquals( 1.000, e.getEllipseCenter().x, 1.0e-3);
		assertEquals(-0.500, e.getEllipseCenter().y, 1.0e-3);

    }

    @Test
    fun createAABB() {

		var e = HalfEllipse(1.0, 0.25);

		var aabb = e.createAABB(IDENTITY);
		assertEquals(-0.500, aabb.getMinX(), 1.0e-3);
		assertEquals( 0.000, aabb.getMinY(), 1.0e-3);
		assertEquals( 0.500, aabb.getMaxX(), 1.0e-3);
		assertEquals( 0.250, aabb.getMaxY(), 1.0e-3);

		var aabb2 = e.createAABB();
		assertEquals(aabb.getMinX(), aabb2.getMinX());
		assertEquals(aabb.getMinY(), aabb2.getMinY());
		assertEquals(aabb.getMaxX(), aabb2.getMaxX());
		assertEquals(aabb.getMaxY(), aabb2.getMaxY());

		var tx = Transform();
		tx.rotate(Math.toRadians(30.0));
		tx.translate(1.0, 2.0);

		aabb = e.createAABB(tx);
		assertEquals(0.549, aabb.getMinX(), 1.0e-3);
		assertEquals(1.750, aabb.getMinY(), 1.0e-3);
		assertEquals(1.433, aabb.getMaxX(), 1.0e-3);
		assertEquals(2.330, aabb.getMaxY(), 1.0e-3);

		tx = Transform();
		tx.rotate(Math.toRadians(60.0));
		tx.translate(1.0, 2.0);

		aabb = e.createAABB(tx);
		assertEquals(0.669, aabb.getMinX(), 1.0e-3);
		assertEquals(1.566, aabb.getMinY(), 1.0e-3);
		assertEquals(1.250, aabb.getMaxX(), 1.0e-3);
		assertEquals(2.450, aabb.getMaxY(), 1.0e-3);

		tx.rotate(Math.toRadians(60.0), 1.0, 2.0);
		aabb = e.createAABB(tx);
		assertEquals(0.669, aabb.getMinX(), 1.0e-3);
		assertEquals(1.549, aabb.getMinY(), 1.0e-3);
		assertEquals(1.250, aabb.getMaxX(), 1.0e-3);
		assertEquals(2.433, aabb.getMaxY(), 1.0e-3);

		tx.rotate(Math.toRadians(100.0), 1.0, 2.0);
		aabb = e.createAABB(tx);
		assertEquals(0.616, aabb.getMinX(), 1.0e-3);
		assertEquals(1.625, aabb.getMinY(), 1.0e-3);
		assertEquals(1.415, aabb.getMaxX(), 1.0e-3);
		assertEquals(2.321, aabb.getMaxY(), 1.0e-3);

		tx.rotate(Math.toRadians(80.0), 1.0, 2.0);
		aabb = e.createAABB(tx);
		assertEquals(0.750, aabb.getMinX(), 1.0e-3);
		assertEquals(1.566, aabb.getMinY(), 1.0e-3);
		assertEquals(1.330, aabb.getMaxX(), 1.0e-3);
		assertEquals(2.450, aabb.getMaxY(), 1.0e-3);

    }

    @Test
    fun createMass() {

		var he = HalfEllipse(1.0, 0.5);
		var mass = he.createMass(1.0);

		assertEquals(0.392, mass.getMass(), 1e-3);
		assertEquals(0.021, mass.getInertia(), 1e-3);
		assertEquals(2.546, mass.getInverseMass(), 1e-3);
		assertEquals(46.402, mass.getInverseInertia(), 1e-3);
		assertEquals(MassType.NORMAL, mass.getType());
		assertEquals(0.000, mass.getCenter().x, 1e-3);
		assertEquals(0.212, mass.getCenter().y, 1e-3);

		mass = he.createMass(0.0);
		assertEquals(0.000, mass.getMass(), 1e-3);
		assertEquals(0.000, mass.getInertia(), 1e-3);
		assertEquals(0.000, mass.getInverseMass(), 1e-3);
		assertEquals(0.000, mass.getInverseInertia(), 1e-3);
		assertEquals(0.000, mass.getCenter().x, 1e-3);
		assertEquals(0.212, mass.getCenter().y, 1e-3);
		assertEquals(MassType.INFINITE, mass.getType());

    }

    @Test
    fun getArea() {

		var he = HalfEllipse(1.0, 0.5);
		assertEquals(0.392, he.getArea(), 1e-3);

    }

    @Test
    fun getRadius() {

		var he = HalfEllipse(1.0, 0.5);

		assertEquals(0.543, he.getRadius(), 1e-3);

		assertEquals(0.500, he.getRadius(Vector2(0.0, 0.0)), 1e-3);

		assertEquals(1.802, he.getRadius(Vector2(1.0, 1.0)), 1e-3);

		he.rotateAboutCenter(Math.toRadians(60));
		assertEquals(1.710, he.getRadius(Vector2(1.0, 1.0)), 1e-3);

		he = HalfEllipse(0.5, 1.0);
		assertEquals(2.243, he.getRadius(Vector2(1.0, -1.0)), 1e-3);

		assertEquals(2.243, he.getRadius(Vector2(-1.0, -1.0)), 1e-3);

		assertEquals(1.600, he.getRadius(Vector2(-1.0, 1.0)), 1e-3);

		assertEquals(1.286, he.getRadius(Vector2(1.0, 0.25)), 1e-3);

		assertEquals(2.358, he.getRadius(Vector2(1.0, 2.0)), 1e-3);

    }

    @Test
    fun getRadiusAboveXAxisBelowEvolute() {

		var he = HalfEllipse(4.0, 4.0);
		var x = 1.0;
		var y = 0.25;
		var d = he.getRadius(Vector2(x, y));

		assertEquals(3.927647520827677, d, 1e-3);

    }

    @Test
    fun copy() {

		var he = HalfEllipse(1.0, 1.0);
		he.setUserData(Any());
		var copy = he.copy();

		assertNotSame(he, copy);
		assertNotSame(he.getCenter(), copy.getCenter());
		assertNotSame(he.getEllipseCenter(), copy.getEllipseCenter());
		assertEquals(he.getRadius(), copy.getRadius());
		assertEquals(he.getHeight(), copy.getHeight());
		assertEquals(he.getHalfWidth(), copy.getHalfWidth());
		assertNull(copy.getUserData());

		assertEquals(he.getCenter().x, copy.getCenter().x);
		assertEquals(he.getCenter().y, copy.getCenter().y);

		assertEquals(he.getFarthestPoint(Vector2(-1.0, 0.0), IDENTITY).x, copy.getFarthestPoint(Vector2(-1.0, 0.0), IDENTITY).x);
		assertEquals(he.getFarthestPoint(Vector2(-1.0, 0.0), IDENTITY).y, copy.getFarthestPoint(Vector2(-1.0, 0.0), IDENTITY).y);
		assertEquals(he.getFarthestPoint(Vector2(1.0, 0.0), IDENTITY).x, copy.getFarthestPoint(Vector2(1.0, 0.0), IDENTITY).x);
		assertEquals(he.getFarthestPoint(Vector2(1.0, 0.0), IDENTITY).y, copy.getFarthestPoint(Vector2(1.0, 0.0), IDENTITY).y);
		assertEquals(he.getRotation().getCost(), copy.getRotation().getCost());
		assertEquals(he.getRotation().getSint(), copy.getRotation().getSint());
		val originalCenter = he.getCenter().copy();
		val originalAngle = he.getRotationAngle();
		copy.translate(1.0, -2.0);
		copy.rotate(Math.toRadians(30));
		assertEquals(originalCenter.x, he.getCenter().x);
		assertEquals(originalCenter.y, he.getCenter().y);
		assertEquals(originalAngle, he.getRotationAngle());

    }

}
