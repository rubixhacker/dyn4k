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

val CircleTest by testSuite {
    test("createZeroRadius") { CircleTestFixture().run { createZeroRadius() } }
    test("createNegativeRadius") { CircleTestFixture().run { createNegativeRadius() } }
    test("createSuccess") { CircleTestFixture().run { createSuccess() } }
    test("contains") { CircleTestFixture().run { contains() } }
    test("project") { CircleTestFixture().run { project() } }
    test("getFarthest") { CircleTestFixture().run { getFarthest() } }
    test("getAxes") { CircleTestFixture().run { getAxes() } }
    test("getFoci") { CircleTestFixture().run { getFoci() } }
    test("rotate") { CircleTestFixture().run { rotate() } }
    test("translate") { CircleTestFixture().run { translate() } }
    test("createAABB") { CircleTestFixture().run { createAABB() } }
    test("getRadius") { CircleTestFixture().run { getRadius() } }
    test("createMass") { CircleTestFixture().run { createMass() } }
    test("getArea") { CircleTestFixture().run { getArea() } }
    test("copy") { CircleTestFixture().run { copy() } }
}

private class CircleTestFixture  {
    private val IDENTITY = Transform()
fun createZeroRadius() {
        assertFailsWith<IllegalArgumentException> {

		Circle(0.0);

        }
    }

fun createNegativeRadius() {
        assertFailsWith<IllegalArgumentException> {

		Circle(-1.0);

        }
    }

fun createSuccess() {

		var c = Circle(1.0);
		assertNotNull(c.toString());

    }

fun contains() {

		var c = Circle(2.0);
		var t = Transform();
		var p = Vector2(2.0, 4.0);

		assertTrue(!c.contains(p, t));
		assertTrue(!c.contains(p, t, false));

		t.translate(2.0, 2.5);

		assertTrue(c.contains(p, t));
		assertTrue(c.contains(p, t, false));

		t.translate(0.0, -0.5);

		assertTrue(c.contains(p, t));
		assertFalse(c.contains(p, t, false));

    }

fun project() {

		var c = Circle(1.5);
		var t = Transform();
		var x = Vector2(1.0, 0.0);
		var y = Vector2(0.0, 1.0);

		t.translate(1.0, 0.5);

		var i = c.project(x, t);

		assertEquals(-0.500, i.getMin(), 1.0e-3);
		assertEquals( 2.500, i.getMax(), 1.0e-3);

		t.rotate(Math.toRadians(30), 1.0, 0.5);

		i = c.project(y, t);

		assertEquals(-1.000, i.getMin(), 1.0e-3);
		assertEquals( 2.000, i.getMax(), 1.0e-3);

    }

fun getFarthest() {

		var c = Circle(1.5);
		var t = Transform();
		var y = Vector2(0.0, -1.0);

		var f = c.getFarthestFeature(y, t);
		assertEquals( 0.000, f.getPoint()!!.x, 1.0e-3);
		assertEquals(-1.500, f.getPoint()!!.y, 1.0e-3);

		var p = c.getFarthestPoint(y, t);
		assertEquals( 0.000, p.x, 1.0e-3);
		assertEquals(-1.500, p.y, 1.0e-3);

		t.translate(0.0, -0.5);

		f = c.getFarthestFeature(y.getNegative(), t);
		assertEquals(0.000, f.getPoint()!!.x, 1.0e-3);
		assertEquals(1.000, f.getPoint()!!.y, 1.0e-3);

		p = c.getFarthestPoint(y.getNegative(), t);
		assertEquals(0.000, p.x, 1.0e-3);
		assertEquals(1.000, p.y, 1.0e-3);

    }

fun getAxes() {

		var c = Circle(1.5);
		var t = Transform();

		var axes = c.getAxes(null, t);
		assertNull(axes);

    }

fun getFoci() {

		var c = Circle(1.5);
		var t = Transform();

		var foci = c.getFoci(t);
		assertEquals(1, foci.size);

    }

fun rotate() {

		var c = Circle(1.0);

		c.translate(1.0, 1.0);
		c.rotateAboutCenter(Math.toRadians(30));
		assertEquals(1.000, c.getCenter().x, 1.0e-3);
		assertEquals(1.000, c.getCenter().y, 1.0e-3);

		c.rotate(Math.toRadians(90));
		assertEquals(-1.000, c.getCenter().x, 1.0e-3);
		assertEquals( 1.000, c.getCenter().y, 1.0e-3);
		c.translate(c.getCenter().getNegative());

		c.rotate(Math.toRadians(90), 1.0, -1.0);
		assertEquals( 0.000, c.getCenter().x, 1.0e-3);
		assertEquals(-2.000, c.getCenter().y, 1.0e-3);

    }

fun translate() {

		var c = Circle(1.0);

		c.translate(1.0, -0.5);

		assertEquals( 1.000, c.getCenter().x, 1.0e-3);
		assertEquals(-0.500, c.getCenter().y, 1.0e-3);

    }

fun createAABB() {

		var c = Circle(1.2);

		var aabb = c.createAABB(IDENTITY);
		assertEquals(-1.2, aabb.getMinX(), 1.0e-3);
		assertEquals(-1.2, aabb.getMinY(), 1.0e-3);
		assertEquals( 1.2, aabb.getMaxX(), 1.0e-3);
		assertEquals( 1.2, aabb.getMaxY(), 1.0e-3);

		var aabb2 = c.createAABB();
		assertEquals(aabb.getMinX(), aabb2.getMinX());
		assertEquals(aabb.getMinY(), aabb2.getMinY());
		assertEquals(aabb.getMaxX(), aabb2.getMaxX());
		assertEquals(aabb.getMaxY(), aabb2.getMaxY());

		var tx = Transform();
		tx.rotate(Math.toRadians(30.0));
		tx.translate(1.0, 2.0);

		aabb = c.createAABB(tx);
		assertEquals(-0.2, aabb.getMinX(), 1.0e-3);
		assertEquals( 0.8, aabb.getMinY(), 1.0e-3);
		assertEquals( 2.2, aabb.getMaxX(), 1.0e-3);
		assertEquals( 3.2, aabb.getMaxY(), 1.0e-3);

    }

fun getRadius() {

		var c = Circle(3.0);
		assertEquals(3.0, c.getRadius());
		assertEquals(4.0, c.getRadius(Vector2(-1.0, 0.0)));
		assertEquals(8.0, c.getRadius(Vector2(-3.0, 4.0)), 1e-3);

    }

fun createMass() {

		var c = Circle(3.0);
		var mass = c.createMass(2.0);

		assertEquals(56.548, mass.getMass(), 1e-3);
		assertEquals(254.469, mass.getInertia(), 1e-3);
		assertEquals(0.017, mass.getInverseMass(), 1e-3);
		assertEquals(0.003, mass.getInverseInertia(), 1e-3);
		assertEquals(0.0, mass.getCenter().x, 1e-3);
		assertEquals(0.0, mass.getCenter().y, 1e-3);
		assertEquals(MassType.NORMAL, mass.getType());

		mass = c.createMass(0.0);
		assertEquals(0.000, mass.getMass(), 1e-3);
		assertEquals(0.000, mass.getInertia(), 1e-3);
		assertEquals(0.000, mass.getInverseMass(), 1e-3);
		assertEquals(0.000, mass.getInverseInertia(), 1e-3);
		assertEquals(0.000, mass.getCenter().x, 1e-3);
		assertEquals(0.000, mass.getCenter().y, 1e-3);
		assertEquals(MassType.INFINITE, mass.getType());

    }

fun getArea() {

		var c = Circle(3.0);
		assertEquals(28.274, c.getArea(), 1e-3);

    }

fun copy() {

		var circ = Circle(3.0);
		circ.setUserData(Any());
		var copy = circ.copy();

		assertNotSame(circ, copy);
		assertNotSame(circ.getCenter(), copy.getCenter());
		assertEquals(circ.getRadius(), copy.getRadius());
		assertNull(copy.getUserData());

		assertEquals(circ.getCenter().x, copy.getCenter().x);
		assertEquals(circ.getCenter().y, copy.getCenter().y);

    }

}
