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

class CapsuleTest {
    private val IDENTITY = Transform()
    @Test
    fun createZeroWidth() {
        assertFailsWith<IllegalArgumentException> {

		Capsule(0.0, 1.0);

        }
    }

    @Test
    fun createNegativeWidth() {
        assertFailsWith<IllegalArgumentException> {

		Capsule(-1.0, 1.0);

        }
    }

    @Test
    fun createZeroHeight() {
        assertFailsWith<IllegalArgumentException> {

		Capsule(1.0, 0.0);

        }
    }

    @Test
    fun createNegativeHeight() {
        assertFailsWith<IllegalArgumentException> {

		Capsule(1.0, -1.0);

        }
    }

    @Test
    fun createCircle() {
        assertFailsWith<IllegalArgumentException> {

		Capsule(1.0, 1.0);

        }
    }

    @Test
    fun createSuccessHorizontal() {

		var cap = Capsule(2.0, 1.0);
		var x = Vector2(cap.getRotation().getCost(), cap.getRotation().getSint());
		assertEquals(1.000, x.x, 1.0e-3);
		assertEquals(0.000, x.y, 1.0e-3);

		assertEquals(2.0, cap.getLength());
		assertEquals(0.5, cap.getCapRadius());

		assertNotNull(cap.toString());

    }

    @Test
    fun createSuccessVertical() {

		var cap = Capsule(1.0, 2.0);
		var x = Vector2(cap.getRotation().getCost(), cap.getRotation().getSint());
		assertEquals(0.000, x.x, 1.0e-3);
		assertEquals(1.000, x.y, 1.0e-3);

		assertEquals(2.0, cap.getLength());
		assertEquals(0.5, cap.getCapRadius());

		assertNotNull(cap.toString());

    }

    @Test
    fun contains() {

		var e = Capsule(2.0, 1.0);
		var t = Transform();
		var p = Vector2(0.8, -0.45);

		assertTrue(!e.contains(p, t));
		assertTrue(!e.contains(p, t, false));

		t.translate(0.5, 0.0);

		assertTrue(e.contains(p, t));
		assertTrue(e.contains(p, t, false));

		p.set(1.5, 0.0);

		assertTrue(e.contains(p, t));
		assertFalse(e.contains(p, t, false));
		p.set(0.75, 0.5);

		assertTrue(e.contains(p, t));
		assertFalse(e.contains(p, t, false));

    }

    @Test
    fun project() {

		var e = Capsule(2.0, 1.0);
		var t = Transform();
		var x = Vector2(1.0, 0.0);
		var y = Vector2(0.0, -1.0);

		t.translate(1.0, 0.5);

		var i = e.project(x, t);
		assertEquals( 0.000, i.getMin(), 1.0e-3);
		assertEquals( 2.000, i.getMax(), 1.0e-3);

		t.rotate(Math.toRadians(30), 1.0, 0.5);

		i = e.project(y, t);
		assertEquals(-1.25, i.getMin(), 1.0e-3);
		assertEquals( 0.25, i.getMax(), 1.0e-3);

		e.translate(1.0, 0.5);
		e.rotate(Math.toRadians(30), 1.0, 0.5);

		i = e.project(y, IDENTITY);
		assertEquals(-1.25, i.getMin(), 1.0e-3);
		assertEquals( 0.25, i.getMax(), 1.0e-3);

		t.identity();
		t.translate(0.0, 1.0);
		i = e.project(y, t);
		assertEquals(-2.25, i.getMin(), 1.0e-3);
		assertEquals(-0.75, i.getMax(), 1.0e-3);

    }

    @Test
    fun getFarthest() {

		var e = Capsule(2.0, 1.0);
		var t = Transform();
		var x = Vector2(1.0, 0.0);
		var y = Vector2(0.0, -1.0);

		t.translate(1.0, 0.5);

		var p = e.getFarthestPoint(x, t);
		assertEquals( 2.000, p.x, 1.0e-3);
		assertEquals( 0.500, p.y, 1.0e-3);

		t.rotate(Math.toRadians(30), 1.0, 0.5);

		p = e.getFarthestPoint(y, t);
		assertEquals( 0.566, p.x, 1.0e-3);
		assertEquals(-0.25, p.y, 1.0e-3);

		e.translate(1.0, 0.5);
		e.rotate(Math.toRadians(30), 1.0, 0.5);

		p = e.getFarthestPoint(y, IDENTITY);
		assertEquals( 0.566, p.x, 1.0e-3);
		assertEquals(-0.25, p.y, 1.0e-3);

		t.identity();
		t.translate(0.0, 1.0);
		p = e.getFarthestPoint(y, t);
		assertEquals( 0.566, p.x, 1.0e-3);
		assertEquals( 0.75, p.y, 1.0e-3);

    }

    @Test
    fun getAxes() {

		var e = Capsule(1.0, 0.5);

		var foci = arrayOf(
			Vector2(2.0, -0.5),
			Vector2(1.0, 3.0)
		);
		var axes = e.getAxes(foci, IDENTITY);
		assertEquals(4, axes.size);

		axes = e.getAxes(null, IDENTITY);
		assertEquals(1.000, axes[0].x, 1.0e-3);
		assertEquals(0.000, axes[0].y, 1.0e-3);
		assertEquals(0.000, axes[1].x, 1.0e-3);
		assertEquals(1.000, axes[1].y, 1.0e-3);

    }

    @Test
    fun getFoci() {

		var e = Capsule(1.0, 0.5);
		var foci = e.getFoci(IDENTITY);

		assertEquals(2, foci.size);

		assertEquals(-0.250, foci[0].x, 1.0e-3);
		assertEquals( 0.000, foci[0].y, 1.0e-3);
		assertEquals( 0.250, foci[1].x, 1.0e-3);
		assertEquals( 0.000, foci[1].y, 1.0e-3);

    }

    @Test
    fun rotate() {

		var e = Capsule(1.0, 0.5);

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

    @Test
    fun translate() {

		var e = Capsule(1.0, 0.5);

		e.translate(1.0, -0.5);

		assertEquals( 1.000, e.getCenter().x, 1.0e-3);
		assertEquals(-0.500, e.getCenter().y, 1.0e-3);

    }

    @Test
    fun createAABB() {

		var e = Capsule(1.0, 0.5);

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
		assertEquals(0.533, aabb.getMinX(), 1.0e-3);
		assertEquals(1.625, aabb.getMinY(), 1.0e-3);
		assertEquals(1.466, aabb.getMaxX(), 1.0e-3);
		assertEquals(2.375, aabb.getMaxY(), 1.0e-3);

    }

    @Test
    fun createMass() {

		var e = Capsule(1.0, 0.5);
		var mass = e.createMass(1.0);

		assertEquals(0.446, mass.getMass(), 1e-3);
		assertEquals(0.028, mass.getInertia(), 1e-3);
		assertEquals(2.240, mass.getInverseMass(), 1e-3);
		assertEquals(34.692, mass.getInverseInertia(), 1e-3);
		assertEquals(0.0, mass.getCenter().x, 1e-3);
		assertEquals(0.0, mass.getCenter().y, 1e-3);
		assertEquals(MassType.NORMAL, mass.getType());

		e = Capsule(0.5, 1.0);
		mass = e.createMass(2.0);

		assertEquals(0.892, mass.getMass(), 1e-3);
		assertEquals(0.057, mass.getInertia(), 1e-3);
		assertEquals(1.120, mass.getInverseMass(), 1e-3);
		assertEquals(17.346, mass.getInverseInertia(), 1e-3);
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

    @Test
    fun getArea() {

		var e = Capsule(1.0, 0.5);
		assertEquals(0.446, e.getArea(), 1e-3);

		e = Capsule(0.5, 1.0);
		assertEquals(0.446, e.getArea(), 1e-3);

    }

    @Test
    fun getRadius() {

		var e = Capsule(1.0, 0.5);
		assertEquals(0.5, e.getRadius());
		assertEquals(1.5, e.getRadius(Vector2(-1.0, 0.0)));
		assertEquals(5.403, e.getRadius(Vector2(-3.0, 4.0)), 1e-3);

		e = Capsule(1.0, 1.1);
		assertEquals(0.55, e.getRadius());
		assertEquals(1.55, e.getRadius(Vector2(0.0, -1.0)), 1e-3);
		assertEquals(1.501, e.getRadius(Vector2(-1.0, 0.0)), 1e-3);

    }

    @Test
    fun getRotation() {

		var e = Capsule(1.0, 0.5);
		assertEquals(0.0, e.getRotationAngle());
		assertEquals(1.0, e.getRotation().getCost());
		assertEquals(0.0, e.getRotation().getSint());

		e = Capsule(1.0, 1.1);
		assertEquals(kotlin.math.PI * 0.5, e.getRotationAngle());
		assertEquals(0.0, e.getRotation().getCost());
		assertEquals(1.0, e.getRotation().getSint());

		e.rotate(Math.toRadians(30));
		assertEquals(kotlin.math.PI * 0.5 + Math.toRadians(30), e.getRotationAngle(), 1e-8);
		assertEquals(kotlin.math.cos(Math.toRadians(120)), e.getRotation().getCost(), 1e-8);
		assertEquals(kotlin.math.sin(Math.toRadians(120)), e.getRotation().getSint(), 1e-8);

		e.rotate(Math.toRadians(-60));
		assertEquals(kotlin.math.PI * 0.5 - Math.toRadians(30), e.getRotationAngle(), 1e-8);
		assertEquals(kotlin.math.cos(Math.toRadians(60)), e.getRotation().getCost(), 1e-8);
		assertEquals(kotlin.math.sin(Math.toRadians(60)), e.getRotation().getSint(), 1e-8);

    }

    @Test
    fun copy() {

		var cap = Capsule(1.0, 0.5);
		cap.setUserData(Any());
		var copy = cap.copy();

		assertNotSame(cap, copy);
		assertNotSame(cap.getCenter(), copy.getCenter());
		assertEquals(cap.getCapRadius(), copy.getCapRadius());
		assertEquals(cap.getRadius(), copy.getRadius());
		assertEquals(cap.getLength(), copy.getLength());
		assertNull(copy.getUserData());

		assertEquals(cap.getCenter().x, copy.getCenter().x);
		assertEquals(cap.getCenter().y, copy.getCenter().y);
		assertEquals(Vector2(cap.getRotation().getCost(), cap.getRotation().getSint()).x, Vector2(copy.getRotation().getCost(), copy.getRotation().getSint()).x);
		assertEquals(Vector2(cap.getRotation().getCost(), cap.getRotation().getSint()).y, Vector2(copy.getRotation().getCost(), copy.getRotation().getSint()).y);

		assertEquals(cap.getFoci(IDENTITY).size, copy.getFoci(IDENTITY).size);
		for (i in 0 until cap.getFoci(IDENTITY).size) {
			assertEquals(cap.getFoci(IDENTITY)[i].x, copy.getFoci(IDENTITY)[i].x);
			assertEquals(cap.getFoci(IDENTITY)[i].y, copy.getFoci(IDENTITY)[i].y);
		}
		val originalCenter = cap.getCenter().copy();
		val originalAngle = cap.getRotationAngle();
		copy.translate(1.0, -2.0);
		copy.rotate(Math.toRadians(30));
		assertEquals(originalCenter.x, cap.getCenter().x);
		assertEquals(originalCenter.y, cap.getCenter().y);
		assertEquals(originalAngle, cap.getRotationAngle());

    }

}
