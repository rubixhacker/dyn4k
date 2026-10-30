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

val AbstractShapeTest by testSuite {
    test("create") { AbstractShapeTestFixture().run { create() } }
    test("setUserData") { AbstractShapeTestFixture().run { setUserData() } }
}

private class AbstractShapeTestFixture  {
    private class TestShape(center: Vector2, radius: Double) : AbstractShape(center, radius) {
        override fun contains(point: Vector2, transform: Transform, inclusive: Boolean) = false
        override fun createMass(density: Double) = Mass()
        override fun getRadius(center: Vector2) = 0.0
        override fun project(vector: Vector2, transform: Transform) = Interval(0.0, 0.0)
        override fun computeAABB(transform: Transform, aabb: AABB) = Unit
        override fun getArea() = 0.0
        override fun copy() = TestShape(getCenter().copy(), getRadius())
    }

fun create() {

		var c = Vector2(1.0, 2.0);
		var r = 2.0;
		var s = TestShape(c, r);

		assertEquals(r, s.getRadius());
		assertEquals(c.x, s.getCenter().x);
		assertEquals(c.y, s.getCenter().y);

    }

fun setUserData() {

		var s = TestShape(Vector2(), 0.0);

		assertNull(s.getUserData());

		var obj = "hello";
		s.setUserData(obj);
		assertNotNull(s.getUserData());
		assertSame(obj, s.getUserData());

    }

}
