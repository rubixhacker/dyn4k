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

val SliceTest by testSuite {
    test("createZeroRadius") { SliceTestFixture().run { createZeroRadius() } }
    test("createNegativeRadius") { SliceTestFixture().run { createNegativeRadius() } }
    test("createZeroTheta") { SliceTestFixture().run { createZeroTheta() } }
    test("createNegativeTheta") { SliceTestFixture().run { createNegativeTheta() } }
    test("createSuccess") { SliceTestFixture().run { createSuccess() } }
    test("contains") { SliceTestFixture().run { contains() } }
    test("project") { SliceTestFixture().run { project() } }
    test("getFarthest") { SliceTestFixture().run { getFarthest() } }
    test("getAxes") { SliceTestFixture().run { getAxes() } }
    test("getFoci") { SliceTestFixture().run { getFoci() } }
    test("rotate") { SliceTestFixture().run { rotate() } }
    test("translate") { SliceTestFixture().run { translate() } }
    test("createAABB") { SliceTestFixture().run { createAABB() } }
    test("sliceRadius") { SliceTestFixture().run { sliceRadius() } }
    test("createMass") { SliceTestFixture().run { createMass() } }
    test("getArea") { SliceTestFixture().run { getArea() } }
    test("getRadiusAtPoint") { SliceTestFixture().run { getRadiusAtPoint() } }
    test("getRotation") { SliceTestFixture().run { getRotation() } }
    test("copy") { SliceTestFixture().run { copy() } }
}

private class SliceTestFixture  {
    private val IDENTITY = Transform()
fun createZeroRadius() {
        assertFailsWith<IllegalArgumentException> {

		Slice(0.0, Math.toRadians(50));

        }
    }

fun createNegativeRadius() {
        assertFailsWith<IllegalArgumentException> {

		Slice(-1.0, Math.toRadians(50));

        }
    }

fun createZeroTheta() {
        assertFailsWith<IllegalArgumentException> {

		Slice(1.0, 0.0);

        }
    }

fun createNegativeTheta() {
        assertFailsWith<IllegalArgumentException> {

		Slice(1.0, -Math.toRadians(50));

        }
    }

fun createSuccess() {

		var slice = Slice(1.0, Math.toRadians(50));

		assertEquals(0.000, slice.getCircleCenter().x, 1.0e-3);
		assertEquals(0.000, slice.getCircleCenter().y, 1.0e-3);
		assertNotNull(slice.toString());

    }

fun contains() {

		var e = Slice(1.0, Math.toRadians(50));
		var t = Transform();
		var p = Vector2(0.5, -0.3);

		assertTrue(!e.contains(p, t));
		assertTrue(!e.contains(p, t, false));

		t.translate(-0.25, 0.0);

		assertTrue(e.contains(p, t));
		assertTrue(e.contains(p, t, false));

		p.set(0.75, 0.0);

		assertTrue(e.contains(p, t));
		assertFalse(e.contains(p, t, false));

    }

fun project() {

		var e = Slice(1.0, Math.toRadians(50));
		var t = Transform();
		var x = Vector2(1.0, 0.0);
		var y = Vector2(0.0, 1.0);

		t.translate(1.0, 0.5);

		var i = e.project(x, t);
		assertEquals( 1.000, i.getMin(), 1.0e-3);
		assertEquals( 2.000, i.getMax(), 1.0e-3);

		t.rotate(Math.toRadians(30), t.getTransformed(e.getCenter()));

		i = e.project(y, t);
		assertEquals(0.177, i.getMin(), 1.0e-3);
		assertEquals(0.996, i.getMax(), 1.0e-3);

		e.translate(1.0, 0.5);
		e.rotateAboutCenter(Math.toRadians(30));

		i = e.project(y, IDENTITY);
		assertEquals(0.177, i.getMin(), 1.0e-3);
		assertEquals(0.996, i.getMax(), 1.0e-3);

		t.identity();
		t.translate(0.0, 1.0);
		i = e.project(y, t);
		assertEquals(1.177, i.getMin(), 1.0e-3);
		assertEquals(1.996, i.getMax(), 1.0e-3);

    }

fun getFarthest() {

		var e = Slice(1.0, Math.toRadians(50));
		var t = Transform();
		var x = Vector2(1.0, 0.0);
		var y = Vector2(0.0, 1.0);

		t.translate(1.0, 0.5);

		var p = e.getFarthestPoint(x, t);
		assertEquals( 2.000, p.x, 1.0e-3);
		assertEquals( 0.500, p.y, 1.0e-3);

		t.rotate(Math.toRadians(30), 1.0, 0.5);

		p = e.getFarthestPoint(y, t);
		assertEquals( 1.573, p.x, 1.0e-3);
		assertEquals( 1.319, p.y, 1.0e-3);

		e.translate(1.0, 0.5);
		e.rotate(Math.toRadians(30), 1.0, 0.5);

		p = e.getFarthestPoint(y, IDENTITY);
		assertEquals( 1.573, p.x, 1.0e-3);
		assertEquals( 1.319, p.y, 1.0e-3);

		t.identity();
		t.translate(0.0, 1.0);
		p = e.getFarthestPoint(y, t);
		assertEquals( 1.573, p.x, 1.0e-3);
		assertEquals( 2.319, p.y, 1.0e-3);

    }

fun getAxes() {

		var e = Slice(1.0, Math.toRadians(50));

		var foci = arrayOf(
			Vector2(2.0, -0.5),
			Vector2(1.0, 3.0)
		);
		var axes = e.getAxes(foci, IDENTITY);
		assertEquals(4, axes.size);

		axes = e.getAxes(null, IDENTITY);
		assertEquals(-0.422, axes[0].x, 1.0e-3);
		assertEquals( 0.906, axes[0].y, 1.0e-3);
		assertEquals(-0.422, axes[1].x, 1.0e-3);
		assertEquals(-0.906, axes[1].y, 1.0e-3);

    }

fun getFoci() {

		var e = Slice(1.0, Math.toRadians(50));
		var foci = e.getFoci(IDENTITY);

		assertEquals(1, foci.size);

		assertEquals( 0.000, foci[0].x, 1.0e-3);
		assertEquals( 0.000, foci[0].y, 1.0e-3);

    }

fun rotate() {

		var e = Slice(1.0, Math.toRadians(50));


		e.translate(1.0, 1.0);
		e.rotateAboutCenter(Math.toRadians(30));
		assertEquals(1.645, e.getCenter().x, 1.0e-3);
		assertEquals(1.000, e.getCenter().y, 1.0e-3);

		e.rotate(Math.toRadians(90));
		assertEquals(-1.000, e.getCenter().x, 1.0e-3);
		assertEquals( 1.645, e.getCenter().y, 1.0e-3);
		e.translate(e.getCenter().getNegative());

		e.rotate(Math.toRadians(90), 1.0, -1.0);
		assertEquals( 0.000, e.getCenter().x, 1.0e-3);
		assertEquals(-2.000, e.getCenter().y, 1.0e-3);

    }

fun translate() {

		var e = Slice(1.0, Math.toRadians(50));

		e.translate(1.0, -0.5);

		assertEquals( 1.645, e.getCenter().x, 1.0e-3);
		assertEquals(-0.500, e.getCenter().y, 1.0e-3);

    }

fun createAABB() {

		var e = Slice(1.0, Math.toRadians(50));

		var aabb = e.createAABB(IDENTITY);
		assertEquals( 0.000, aabb.getMinX(), 1.0e-3);
		assertEquals(-0.422, aabb.getMinY(), 1.0e-3);
		assertEquals( 1.000, aabb.getMaxX(), 1.0e-3);
		assertEquals( 0.422, aabb.getMaxY(), 1.0e-3);

		var aabb2 = e.createAABB();
		assertEquals(aabb.getMinX(), aabb2.getMinX());
		assertEquals(aabb.getMinY(), aabb2.getMinY());
		assertEquals(aabb.getMaxX(), aabb2.getMaxX());
		assertEquals(aabb.getMaxY(), aabb2.getMaxY());

		var tx = Transform();
		tx.rotate(Math.toRadians(30.0));
		tx.translate(1.0, 2.0);

		aabb = e.createAABB(tx);
		assertEquals( 1.000, aabb.getMinX(), 1.0e-3);
		assertEquals( 2.000, aabb.getMinY(), 1.0e-3);
		assertEquals( 1.996, aabb.getMaxX(), 1.0e-3);
		assertEquals( 2.819, aabb.getMaxY(), 1.0e-3);

    }

fun sliceRadius() {

		var e = Slice(1.0, Math.toRadians(50));
		assertEquals(1.000, e.getSliceRadius(), 1.0e-3);
		assertFalse(kotlin.math.abs(1.0 - e.getRadius()) < Epsilon.E);
		assertFalse(kotlin.math.abs(e.getSliceRadius() - e.getRadius()) < Epsilon.E);

    }

fun createMass() {

		var s = Slice(0.5, Math.toRadians(30));
		var mass = s.createMass(1.0);
		assertEquals(0.065, mass.getMass(), 1.0e-3);
		assertEquals(0.001, mass.getInertia(), 1.0e-3);
		assertEquals(15.278, mass.getInverseMass(), 1.0e-3);
		assertEquals(931.395, mass.getInverseInertia(), 1.0e-3);
		assertEquals(0.329, mass.getCenter().x, 1.0e-3);
		assertEquals(0.0, mass.getCenter().y, 1.0e-3);
		assertEquals(MassType.NORMAL, mass.getType());

		mass = s.createMass(2.0);
		assertEquals(0.130, mass.getMass(), 1.0e-3);
		assertEquals(0.002, mass.getInertia(), 1.0e-3);
		assertEquals(7.639, mass.getInverseMass(), 1.0e-3);
		assertEquals(465.697, mass.getInverseInertia(), 1.0e-3);
		assertEquals(0.329, mass.getCenter().x, 1.0e-3);
		assertEquals(0.0, mass.getCenter().y, 1.0e-3);
		assertEquals(MassType.NORMAL, mass.getType());

		mass = s.createMass(0.0);
		assertEquals(0.000, mass.getMass(), 1e-3);
		assertEquals(0.000, mass.getInertia(), 1e-3);
		assertEquals(0.000, mass.getInverseMass(), 1e-3);
		assertEquals(0.000, mass.getInverseInertia(), 1e-3);
		assertEquals(0.329, mass.getCenter().x, 1e-3);
		assertEquals(0.000, mass.getCenter().y, 1e-3);
		assertEquals(MassType.INFINITE, mass.getType());

    }

fun getArea() {

		var s = Slice(0.5, Math.toRadians(30));
		assertEquals(0.065, s.getArea(), 1.0e-3);

    }

fun getRadiusAtPoint() {

		var s = Slice(0.5, Math.toRadians(30));
		assertEquals(0.329, s.getRadius(s.getCenter()), 1e-3);

		assertEquals(0.5, s.getRadius(Vector2(0.0, 0.0)), 1e-3);

    }

fun getRotation() {

		var s = Slice(0.5, Math.toRadians(30));
		assertNotNull(s.getRotation());
		assertEquals(1.0, s.getRotation().getCost(), 1e-3);
		assertEquals(0.0, s.getRotation().getSint(), 1e-3);
		assertEquals(0.0, s.getRotationAngle(), 1e-3);

		s.rotate(Math.toRadians(30));
		assertNotNull(s.getRotation());
		assertEquals(0.866, s.getRotation().getCost(), 1e-3);
		assertEquals(0.499, s.getRotation().getSint(), 1e-3);
		assertEquals(Math.toRadians(30), s.getRotationAngle(), 1e-3);

    }

fun copy() {

		var slice = Slice(1.0, Math.toRadians(45));
		slice.setUserData(Any());
		var copy = slice.copy();

		assertNotSame(slice, copy);
		assertNotSame(slice.getCenter(), copy.getCenter());
		assertEquals(slice.getTheta() / 2.0, copy.getTheta()/2.0);
		assertEquals(slice.getRadius(), copy.getRadius());
		assertEquals(slice.getSliceRadius(), copy.getSliceRadius());
		assertNull(copy.getUserData());

		assertEquals(slice.getCenter().x, copy.getCenter().x);
		assertEquals(slice.getCenter().y, copy.getCenter().y);
		assertEquals(slice.getRotation().getCost(), copy.getRotation().getCost());
		assertEquals(slice.getRotation().getSint(), copy.getRotation().getSint());

		assertEquals(slice.getAxes(null, IDENTITY).size, copy.getAxes(null, IDENTITY).size);
		for (i in 0 until slice.getAxes(null, IDENTITY).size) {
			assertEquals(slice.getAxes(null, IDENTITY)[i].x, copy.getAxes(null, IDENTITY)[i].x);
			assertEquals(slice.getAxes(null, IDENTITY)[i].y, copy.getAxes(null, IDENTITY)[i].y);
		}

		assertEquals(slice.getFoci(IDENTITY).size, copy.getFoci(IDENTITY).size);
		for (i in 0 until slice.getFoci(IDENTITY).size) {
			assertEquals(slice.getFoci(IDENTITY)[i].x, copy.getFoci(IDENTITY)[i].x);
			assertEquals(slice.getFoci(IDENTITY)[i].y, copy.getFoci(IDENTITY)[i].y);
		}
		val originalCenter = slice.getCenter().copy();
		val originalAngle = slice.getRotationAngle();
		copy.translate(1.0, -2.0);
		copy.rotate(Math.toRadians(30));
		assertEquals(originalCenter.x, slice.getCenter().x);
		assertEquals(originalCenter.y, slice.getCenter().y);
		assertEquals(originalAngle, slice.getRotationAngle());

    }

}
