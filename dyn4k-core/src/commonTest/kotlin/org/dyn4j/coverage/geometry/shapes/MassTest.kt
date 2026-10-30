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
package org.dyn4j.geometry

import de.infix.testBalloon.framework.core.testSuite
import org.dyn4j.geometry.*
import org.dyn4j.Epsilon
import kotlin.test.*

val MassTest by testSuite {
    test("createNegativeMass") { MassTestFixture().run { createNegativeMass() } }
    test("createNegativeInertia") { MassTestFixture().run { createNegativeInertia() } }
    test("createNullCenter") { MassTestFixture().run { createNullCenter() } }
    test("createSuccess") { MassTestFixture().run { createSuccess() } }
    test("createInfinite") { MassTestFixture().run { createInfinite() } }
    test("createFixedLinearVelocity") { MassTestFixture().run { createFixedLinearVelocity() } }
    test("createFixedAngularVelocity") { MassTestFixture().run { createFixedAngularVelocity() } }
    test("createCopyNull") { MassTestFixture().run { createCopyNull() } }
    test("createCopy") { MassTestFixture().run { createCopy() } }
    test("createList") { MassTestFixture().run { createList() } }
    test("createListInfinite") { MassTestFixture().run { createListInfinite() } }
    test("createListOneElement") { MassTestFixture().run { createListOneElement() } }
    test("createListNull") { MassTestFixture().run { createListNull() } }
    test("createListEmpty") { MassTestFixture().run { createListEmpty() } }
    test("createListOneNullElement") { MassTestFixture().run { createListOneNullElement() } }
    test("createListNullElement") { MassTestFixture().run { createListNullElement() } }
    test("setType") { MassTestFixture().run { setType() } }
    test("setNullType") { MassTestFixture().run { setNullType() } }
    test("setTypeIgnored") { MassTestFixture().run { setTypeIgnored() } }
    test("polygonInertiaAndCOM") { MassTestFixture().run { polygonInertiaAndCOM() } }
    test("polygonInertiaAndMass") { MassTestFixture().run { polygonInertiaAndMass() } }
    test("equals") { MassTestFixture().run { equals() } }
}

private class MassTestFixture  {
fun createNegativeMass() {
        assertFailsWith<IllegalArgumentException> {

		Mass(Vector2(), -1.0, 1.0);

        }
    }

fun createNegativeInertia() {
        assertFailsWith<IllegalArgumentException> {

		Mass(Vector2(), 1.0, -1.0);

        }
    }

fun createNullCenter() {
        assertFailsWith<NullPointerException> {

		Mass(null, 1.0, 1.0);

        }
    }

fun createSuccess() {

		var m = Mass(Vector2(), 1.0, 1.0);
		assertTrue(m.getCenter().equals(Vector2()));
		assertEquals(m.getMass(), 1.0);
		assertEquals(m.getInertia(), 1.0);

    }

fun createInfinite() {

		var m = Mass(Vector2(), 0.0, 0.0);
		assertTrue(m.isInfinite());
		assertTrue(m.getCenter().equals(Vector2()));
		assertEquals(m.getMass(), 0.0);
		assertEquals(m.getInertia(), 0.0);

    }

fun createFixedLinearVelocity() {

		var m = Mass(Vector2(), 0.0, 1.0);
		assertFalse(m.isInfinite());
		assertEquals(MassType.FIXED_LINEAR_VELOCITY, m.getType());
		assertTrue(m.getCenter().equals(Vector2()));
		assertEquals(m.getMass(), 0.0);
		assertEquals(m.getInertia(), 1.0);

    }

fun createFixedAngularVelocity() {

		var m = Mass(Vector2(), 1.0, 0.0);
		assertFalse(m.isInfinite());
		assertEquals(MassType.FIXED_ANGULAR_VELOCITY, m.getType());
		assertTrue(m.getCenter().equals(Vector2()));
		assertEquals(m.getMass(), 1.0);
		assertEquals(m.getInertia(), 0.0);

    }

fun createCopyNull() {
        assertFailsWith<NullPointerException> {

		Mass(null);

        }
    }

fun createCopy() {

		var m = Mass(Vector2(1.0, 0.0), 2.0, 1.0);
		var m2 = Mass(m);

		assertNotSame(m, m2);
		assertNotSame(m.getCenter(), m2.getCenter());
		assertEquals(m.getCenter().x, m2.getCenter().x);
		assertEquals(m.getCenter().y, m2.getCenter().y);
		assertEquals(m.getMass(), m2.getMass());
		assertEquals(m.getInertia(), m2.getInertia());
		assertEquals(m.getType(), m2.getType());

		var m3 = m2.copy();
		assertNotSame(m2, m3);
		assertNotSame(m2.getCenter(), m3.getCenter());
		assertEquals(m2.getCenter().x, m3.getCenter().x);
		assertEquals(m2.getCenter().y, m3.getCenter().y);
		assertEquals(m2.getMass(), m3.getMass());
		assertEquals(m2.getInertia(), m3.getInertia());
		assertEquals(m2.getType(), m3.getType());

    }

fun createList() {

		var m1 = Mass(Vector2( 1.0,  1.0), 3.00, 1.00);
		var m2 = Mass(Vector2(-1.0,  0.0), 0.50, 0.02);
		var m3 = Mass(Vector2( 1.0, -2.0), 2.00, 3.00);
		var masses = mutableListOf<Mass?>();
		masses.add(m1);
		masses.add(m2);
		masses.add(m3);
		var m = Mass.create(masses);

		var c = m.getCenter();
		assertEquals( 0.818, c.x, 1.0e-3);
		assertEquals(-0.181, c.y, 1.0e-3);
		assertEquals( 5.500, m.getMass(), 1.0e-3);
		assertEquals(16.656, m.getInertia(), 1.0e-3);

    }

fun createListInfinite() {

		var m1 = Mass();
		var m2 = Mass();
		var m3 = Mass();
		var masses = mutableListOf<Mass?>();
		masses.add(m1);
		masses.add(m2);
		masses.add(m3);
		var m = Mass.create(masses);

		var c = m.getCenter();
		assertTrue(m.isInfinite());
		assertEquals(0.000, c.x, 1.0e-3);
		assertEquals(0.000, c.y, 1.0e-3);
		assertEquals(0.000, m.getMass(), 1.0e-3);
		assertEquals(0.000, m.getInertia(), 1.0e-3);

    }

fun createListOneElement() {

		var m1 = Mass(Vector2(), 1.0, 2.0);
		var masses = mutableListOf<Mass?>();
		masses.add(m1);
		var m = Mass.create(masses);

		var c = m.getCenter();
		assertFalse(m.isInfinite());
		assertNotSame(m1, m);
		assertEquals(0.000, c.x, 1.0e-3);
		assertEquals(0.000, c.y, 1.0e-3);
		assertEquals(1.000, m.getMass(), 1.0e-3);
		assertEquals(2.000, m.getInertia(), 1.0e-3);

    }

fun createListNull() {
        assertFailsWith<NullPointerException> {

		Mass.create(null);

        }
    }

fun createListEmpty() {
        assertFailsWith<IllegalArgumentException> {

		Mass.create(mutableListOf<Mass?>());

        }
    }

fun createListOneNullElement() {
        assertFailsWith<NullPointerException> {

		var masses = mutableListOf<Mass?>();
		masses.add(null);
		Mass.create(masses);

        }
    }

fun createListNullElement() {
        assertFailsWith<NullPointerException> {

		var m1 = Mass(Vector2(), 1.0, 2.0);
		var m2 = Mass(Vector2(), 2.0, 7.0);
		var masses = mutableListOf<Mass?>();
		masses.add(m1);
		masses.add(null);
		masses.add(m2);
		Mass.create(masses);

        }
    }

fun setType() {

		var c = Geometry.createCircle(2.0);
		var mi = c.createMass(1.0);


		mi.setType(MassType.INFINITE);
		assertTrue(mi.isInfinite());

		assertEquals(0.0, mi.getMass());
		assertEquals(0.0, mi.getInverseMass());
		assertEquals(0.0, mi.getInertia());
		assertEquals(0.0, mi.getInverseInertia());

		mi.setType(MassType.FIXED_ANGULAR_VELOCITY);
		assertEquals(0.0, mi.getInertia());
		assertEquals(0.0, mi.getInverseInertia());

		mi.setType(MassType.FIXED_LINEAR_VELOCITY);
		assertEquals(0.0, mi.getMass());
		assertEquals(0.0, mi.getInverseMass());

    }

fun setNullType() {
        assertFailsWith<NullPointerException> {

		var m = Mass();
		m.setType(null);

        }
    }

fun setTypeIgnored() {

		var m = Mass();
		assertEquals(MassType.INFINITE, m.getType());

		m.setType(MassType.NORMAL);
		assertEquals(MassType.INFINITE, m.getType());
		m.setType(MassType.FIXED_ANGULAR_VELOCITY);
		assertEquals(MassType.INFINITE, m.getType());
		m.setType(MassType.FIXED_LINEAR_VELOCITY);
		assertEquals(MassType.INFINITE, m.getType());
		m.setType(MassType.INFINITE);
		assertEquals(MassType.INFINITE, m.getType());


		m = Mass(Vector2(), 0.0, 1.0);
		assertEquals(MassType.FIXED_LINEAR_VELOCITY, m.getType());
		m.setType(MassType.NORMAL);
		assertEquals(MassType.FIXED_LINEAR_VELOCITY, m.getType());
		m.setType(MassType.FIXED_ANGULAR_VELOCITY);
		assertEquals(MassType.FIXED_LINEAR_VELOCITY, m.getType());
		m.setType(MassType.INFINITE);
		assertEquals(MassType.INFINITE, m.getType());
		m.setType(MassType.FIXED_LINEAR_VELOCITY);
		assertEquals(MassType.FIXED_LINEAR_VELOCITY, m.getType());


		m = Mass(Vector2(), 1.0, 0.0);
		assertEquals(MassType.FIXED_ANGULAR_VELOCITY, m.getType());
		m.setType(MassType.NORMAL);
		assertEquals(MassType.FIXED_ANGULAR_VELOCITY, m.getType());
		m.setType(MassType.FIXED_LINEAR_VELOCITY);
		assertEquals(MassType.FIXED_ANGULAR_VELOCITY, m.getType());
		m.setType(MassType.INFINITE);
		assertEquals(MassType.INFINITE, m.getType());
		m.setType(MassType.FIXED_ANGULAR_VELOCITY);
		assertEquals(MassType.FIXED_ANGULAR_VELOCITY, m.getType());

    }

fun polygonInertiaAndCOM() {

		var p = Geometry.createUnitCirclePolygon(4, Math.hypot(0.5, 0.5));
		var r = Geometry.createSquare(1.0);

		var pm = p.createMass(10.0);
		var rm = r.createMass(10.0);

		assertEquals(rm.getMass(), pm.getMass(), 1.0e-3);
		assertEquals(rm.getInertia(), pm.getInertia(), 1.0e-3);

    }

fun polygonInertiaAndMass() {

		var p = Geometry.createUnitCirclePolygon(4, Math.hypot(0.5, 0.5));
		var m1 = p.createMass(10.0);

		p.translate(0.5, -2.0);
		var m2 = p.createMass(10.0);

		assertEquals(m1.getMass(), m2.getMass(), 1.0e-3);
		assertEquals(m1.getInertia(), m2.getInertia(), 1.0e-3);

    }

fun equals() {

		var m1 = Mass();
		var m2 = Mass();

		assertEquals(m1, m2);
		assertEquals(m1.hashCode(), m2.hashCode());
		assertEquals(m1, m1);
		assertEquals(m1.hashCode(), m1.hashCode());
		assertEquals(m2, m2);
		assertEquals(m2.hashCode(), m2.hashCode());
		assertFalse(m1 === m2);

		var m3 = Mass(Vector2(), 5.0, 1.0);
		assertFalse(m1.equals(m3));
		assertFalse(m1.hashCode() == m3.hashCode());
		assertFalse(m1.equals(null));
		assertFalse(m1.equals(null));
		assertFalse(m1.equals(m3));
		assertTrue(m1.equals(m1));
		assertFalse(m1.equals(Any()));

    }

}
