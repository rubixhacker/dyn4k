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

val EllipseTest by testSuite {
    test("createZeroWidth") { EllipseTestFixture().run { createZeroWidth() } }
    test("createNegativeWidth") { EllipseTestFixture().run { createNegativeWidth() } }
    test("createZeroHeight") { EllipseTestFixture().run { createZeroHeight() } }
    test("createNegativeHeight") { EllipseTestFixture().run { createNegativeHeight() } }
    test("createSuccess") { EllipseTestFixture().run { createSuccess() } }
    test("contains") { EllipseTestFixture().run { contains() } }
    test("project") { EllipseTestFixture().run { project() } }
    test("getFarthest") { EllipseTestFixture().run { getFarthest() } }
    test("getFarthestPointOnEllipse") { EllipseTestFixture().run { getFarthestPointOnEllipse() } }
    test("getAxes") { EllipseTestFixture().run { getAxes() } }
    test("getFoci") { EllipseTestFixture().run { getFoci() } }
    test("rotate") { EllipseTestFixture().run { rotate() } }
    test("translate") { EllipseTestFixture().run { translate() } }
    test("createAABB") { EllipseTestFixture().run { createAABB() } }
    test("getRadius") { EllipseTestFixture().run { getRadius() } }
    test("createMass") { EllipseTestFixture().run { createMass() } }
    test("getArea") { EllipseTestFixture().run { getArea() } }
    test("getRotation") { EllipseTestFixture().run { getRotation() } }
    test("copy") { EllipseTestFixture().run { copy() } }
}

private class EllipseTestFixture  {
    private val IDENTITY = Transform()
fun createZeroWidth() {
        assertFailsWith<IllegalArgumentException> {

		Ellipse(0.0, 1.0);

        }
    }

fun createNegativeWidth() {
        assertFailsWith<IllegalArgumentException> {

		Ellipse(-1.0, 1.0);

        }
    }

fun createZeroHeight() {
        assertFailsWith<IllegalArgumentException> {

		Ellipse(1.0, 0.0);

        }
    }

fun createNegativeHeight() {
        assertFailsWith<IllegalArgumentException> {

		Ellipse(1.0, -1.0);

        }
    }

fun createSuccess() {

		var e = Ellipse(1.0, 2.0);
		assertEquals(1.0, e.getHalfHeight());
		assertEquals(0.5, e.getHalfWidth());
		assertEquals(1.0, e.getWidth());
		assertEquals(2.0, e.getHeight());
		assertNotNull(e.toString());

    }

fun contains() {

		var e = Ellipse(2.0, 1.0);
		var t = Transform();
		var p = Vector2(0.75, 0.35);

		assertTrue(!e.contains(p, t));
		assertTrue(!e.contains(p, t, false));

		t.translate(0.5, 0.0);

		assertTrue(e.contains(p, t));
		assertTrue(e.contains(p, t, false));

		p.set(1.5, 0.0);

		assertTrue(e.contains(p, t));
		assertFalse(e.contains(p, t, false));

		e.rotate(Math.toRadians(90));
		e.translate(0.5, 1.0);

		assertFalse(e.contains(p, t));
		assertFalse(e.contains(p, t, false));
		p.set(1.0, 2.1);
		assertFalse(e.contains(p, t));
		assertFalse(e.contains(p, t, false));
		p.set(1.0, 2.0);
		assertTrue(e.contains(p, t));

		assertFalse(e.contains(p, t, false));

    }

fun project() {

		var e = Ellipse(2.0, 1.0);
		var t = Transform();
		var x = Vector2(1.0, 0.0);
		var y = Vector2(0.0, -1.0);

		t.translate(1.0, 0.5);

		var i = e.project(x, t);
		assertEquals( 0.000, i.getMin(), 1.0e-3);
		assertEquals( 2.000, i.getMax(), 1.0e-3);

		t.rotate(Math.toRadians(30), 1.0, 0.5);

		i = e.project(y, t);
		assertEquals(-1.161, i.getMin(), 1.0e-3);
		assertEquals( 0.161, i.getMax(), 1.0e-3);

		e.translate(1.0, 0.5);
		e.rotate(Math.toRadians(30), 1.0, 0.5);

		i = e.project(y, IDENTITY);
		assertEquals(-1.161, i.getMin(), 1.0e-3);
		assertEquals( 0.161, i.getMax(), 1.0e-3);

		t.identity();
		t.translate(0.0, 1.0);
		i = e.project(y, t);
		assertEquals(-2.161, i.getMin(), 1.0e-3);
		assertEquals(-0.839, i.getMax(), 1.0e-3);

    }

fun getFarthest() {

		var e = Ellipse(2.0, 1.0);
		var t = Transform();
		var x = Vector2(1.0, 0.0);
		var y = Vector2(0.0, -1.0);

		t.translate(1.0, 0.5);

		var p = e.getFarthestPoint(x, t);
		assertEquals( 2.000, p.x, 1.0e-3);
		assertEquals( 0.500, p.y, 1.0e-3);

		t.rotate(Math.toRadians(30), 1.0, 0.5);

		p = e.getFarthestPoint(y, t);
		assertEquals( 0.509, p.x, 1.0e-3);
		assertEquals(-0.161, p.y, 1.0e-3);

		e.translate(1.0, 0.5);
		e.rotate(Math.toRadians(30), 1.0, 0.5);

		p = e.getFarthestPoint(y, IDENTITY);
		assertEquals( 0.509, p.x, 1.0e-3);
		assertEquals(-0.161, p.y, 1.0e-3);

		t.identity();
		t.translate(0.0, 1.0);
		p = e.getFarthestPoint(y, t);
		assertEquals( 0.509, p.x, 1.0e-3);
		assertEquals( 0.838, p.y, 1.0e-3);

    }

fun getFarthestPointOnEllipse() {





		var p = Ellipse.getFarthestPointOnEllipse(1.0, 0.5, Vector2(2.0, 0.1));
		assertEquals(-1.000, p.x, 1e-3);
		assertEquals(-0.009, p.y, 1e-3);

		p = Ellipse.getFarthestPointOnEllipse(1.0, 0.5, Vector2(0.1, 2.0));
		assertEquals(-0.325, p.x, 1e-3);
		assertEquals(-0.472, p.y, 1e-3);

		p = Ellipse.getFarthestPointOnEllipse(1.0, 0.5, Vector2(-2.0, -0.1));
		assertEquals( 1.000, p.x, 1e-3);
		assertEquals( 0.009, p.y, 1e-3);

		p = Ellipse.getFarthestPointOnEllipse(1.0, 0.5, Vector2(0.1, -2.0));
		assertEquals(-0.325, p.x, 1e-3);
		assertEquals( 0.472, p.y, 1e-3);

		p = Ellipse.getFarthestPointOnEllipse(1.0, 0.5, Vector2(2.0, 0.0));
		assertEquals(-1.000, p.x, 1e-3);
		assertEquals( 0.000, p.y, 1e-3);

		p = Ellipse.getFarthestPointOnEllipse(0.5, 1.0, Vector2(0.0, 2.0));
		assertEquals( 0.000, p.x, 1e-3);
		assertEquals(-1.000, p.y, 1e-3);

    }

fun getAxes() {
        assertFailsWith<UnsupportedOperationException> {

		var e = Ellipse(1.0, 0.5);
		e.getAxes(arrayOf( Vector2() ), IDENTITY);

        }
    }

fun getFoci() {
        assertFailsWith<UnsupportedOperationException> {

		var e = Ellipse(1.0, 0.5);
		e.getFoci(IDENTITY);

        }
    }

fun rotate() {

		var e = Ellipse(1.0, 0.5);

		e.translate(1.0, 1.0);
		e.rotateAboutCenter(Math.toRadians(30));
		assertEquals(1.000, e.getCenter().x, 1.0e-3);
		assertEquals(1.000, e.getCenter().y, 1.0e-3);

		e.rotate(Math.toRadians(90));
		assertEquals(-1.000, e.getCenter().x, 1.0e-3);
		assertEquals( 1.000, e.getCenter().y, 1.0e-3);
		e.translate(e.getCenter().getNegative());

		e.rotate(Math.toRadians(90), 1.0, -1.0);
		assertEquals( 0.000, e.getCenter().x, 1.0e-3);
		assertEquals(-2.000, e.getCenter().y, 1.0e-3);

    }

fun translate() {

		var e = Ellipse(1.0, 0.5);

		e.translate(1.0, -0.5);

		assertEquals( 1.000, e.getCenter().x, 1.0e-3);
		assertEquals(-0.500, e.getCenter().y, 1.0e-3);

    }

fun createAABB() {

		var e = Ellipse(1.0, 0.5);

		var aabb = e.createAABB(IDENTITY);
		assertEquals(-0.500, aabb.getMinX(), 1.0e-3);
		assertEquals(-0.250, aabb.getMinY(), 1.0e-3);
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
		assertEquals(1.669, aabb.getMinY(), 1.0e-3);
		assertEquals(1.450, aabb.getMaxX(), 1.0e-3);
		assertEquals(2.330, aabb.getMaxY(), 1.0e-3);

    }

fun getRadius() {

		var e = Ellipse(1.0, 0.5);

		var r = e.getRadius();
		assertEquals(0.5, r, 1.0e-3);

		r = e.getRadius(Vector2(1.0, 0.0));
		assertEquals(1.5, r, 1.0e-3);

		e.rotate(Math.toRadians(30));
		r = e.getRadius(Vector2(1.0, 0.0));
		assertEquals(1.463, r, 1.0e-3);

    }

fun createMass() {

		var e = Ellipse(1.0, 0.5);
		var mass = e.createMass(1.0);

		assertEquals(0.392, mass.getMass(), 1e-3);
		assertEquals(0.030, mass.getInertia(), 1e-3);
		assertEquals(2.546, mass.getInverseMass(), 1e-3);
		assertEquals(32.594, mass.getInverseInertia(), 1e-3);
		assertEquals(0.0, mass.getCenter().x, 1e-3);
		assertEquals(0.0, mass.getCenter().y, 1e-3);
		assertEquals(MassType.NORMAL, mass.getType());

		e = Ellipse(0.5, 1.0);
		mass = e.createMass(2.0);

		assertEquals(0.785, mass.getMass(), 1e-3);
		assertEquals(0.061, mass.getInertia(), 1e-3);
		assertEquals(1.273, mass.getInverseMass(), 1e-3);
		assertEquals(16.297, mass.getInverseInertia(), 1e-3);
		assertEquals(0.0, mass.getCenter().x, 1e-3);
		assertEquals(0.0, mass.getCenter().y, 1e-3);
		assertEquals(MassType.NORMAL, mass.getType());

		mass = e.createMass(0.0);
		assertEquals(0.000, mass.getMass(), 1e-3);
		assertEquals(0.000, mass.getInertia(), 1e-3);
		assertEquals(0.000, mass.getInverseMass(), 1e-3);
		assertEquals(0.000, mass.getInverseInertia(), 1e-3);
		assertEquals(0.000, mass.getCenter().x, 1e-3);
		assertEquals(0.000, mass.getCenter().y, 1e-3);
		assertEquals(MassType.INFINITE, mass.getType());

    }

fun getArea() {

		var e = Ellipse(1.0, 0.5);
		assertEquals(0.392, e.getArea(), 1e-3);

		e = Ellipse(0.5, 1.0);
		assertEquals(0.392, e.getArea(), 1e-3);

    }

fun getRotation() {

		var e = Ellipse(1.0, 0.5);
		assertEquals(0.0, e.getRotationAngle());
		assertEquals(1.0, e.getRotation().getCost());
		assertEquals(0.0, e.getRotation().getSint());

		e = Ellipse(1.0, 1.1);
		assertEquals(0.0, e.getRotationAngle());
		assertEquals(1.0, e.getRotation().getCost());
		assertEquals(0.0, e.getRotation().getSint());

		e.rotate(Math.toRadians(30));
		assertEquals(Math.toRadians(30), e.getRotationAngle(), 1e-8);
		assertEquals(kotlin.math.cos(Math.toRadians(30)), e.getRotation().getCost(), 1e-8);
		assertEquals(kotlin.math.sin(Math.toRadians(30)), e.getRotation().getSint(), 1e-8);

		e.rotate(Math.toRadians(-60));
		assertEquals(Math.toRadians(-30), e.getRotationAngle(), 1e-8);
		assertEquals(kotlin.math.cos(Math.toRadians(-30)), e.getRotation().getCost(), 1e-8);
		assertEquals(kotlin.math.sin(Math.toRadians(-30)), e.getRotation().getSint(), 1e-8);

    }

fun copy() {

		var ellipse = Ellipse(1.0, 0.5);
		ellipse.setUserData(Any());
		var copy = ellipse.copy();

		assertNotSame(ellipse, copy);
		assertNotSame(ellipse.getCenter(), copy.getCenter());
		assertEquals(ellipse.getRadius(), copy.getRadius());
		assertEquals(ellipse.getHalfHeight(), copy.getHalfHeight());
		assertEquals(ellipse.getHalfWidth(), copy.getHalfWidth());
		assertNull(copy.getUserData());

		assertEquals(ellipse.getCenter().x, copy.getCenter().x);
		assertEquals(ellipse.getCenter().y, copy.getCenter().y);
		assertEquals(ellipse.getRotation().getCost(), copy.getRotation().getCost());
		assertEquals(ellipse.getRotation().getSint(), copy.getRotation().getSint());
		val originalCenter = ellipse.getCenter().copy();
		val originalAngle = ellipse.getRotationAngle();
		copy.translate(1.0, -2.0);
		copy.rotate(Math.toRadians(30));
		assertEquals(originalCenter.x, ellipse.getCenter().x);
		assertEquals(originalCenter.y, ellipse.getCenter().y);
		assertEquals(originalAngle, ellipse.getRotationAngle());

    }

}
