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

val TriangleTest by testSuite {
    test("tostring") { TriangleTestFixture().run { tostring() } }
    test("contains") { TriangleTestFixture().run { contains() } }
    test("copy") { TriangleTestFixture().run { copy() } }
}

private class TriangleTestFixture  {
fun tostring() {

		var t = Triangle(
			Vector2( 0.0,  0.5),
			Vector2(-0.5, -0.5),
			Vector2( 0.5, -0.5)
		);

		var s = t.toString();

		assertNotNull(s);
		assertTrue(s.length > 0);

    }

fun contains() {

		var t = Triangle(
			Vector2( 0.0,  0.5),
			Vector2(-0.5, -0.5),
			Vector2( 0.5, -0.5)
		);
		var tx = Transform();

		var p = Vector2(1.0, 1.0);
		assertFalse(t.contains(p, tx));

		p.set(0.2, 0.0);
		assertTrue(t.contains(p, tx));

		p.set(0.3, -0.5);
		assertTrue(t.contains(p, tx));

		tx.rotate(Math.toRadians(90));
		tx.translate(0.0, 1.0);

		p.set(1.0, 1.0);
		assertFalse(t.contains(p, tx));

		p.set(0.4, 1.0);
		assertTrue(t.contains(p, tx));

		p.set(0.0, 0.76);

		assertTrue(t.contains(p, tx));

    }

fun copy() {

		var tri = Triangle(
				Vector2( 0.0,  0.5),
				Vector2(-0.5, -0.5),
				Vector2( 0.5, -0.5)
			);
		tri.setUserData(Any());
		var copy = tri.copy();

		assertNotSame(tri, copy);
		assertNotSame(tri.getCenter(), copy.getCenter());
		assertNotSame(tri.getNormals(), copy.getNormals());
		assertNotSame(tri.getVertices(), copy.getVertices());
		assertEquals(tri.getRadius(), copy.getRadius());
		assertNull(copy.getUserData());

		assertEquals(tri.getCenter().x, copy.getCenter().x);
		assertEquals(tri.getCenter().y, copy.getCenter().y);

		assertEquals(tri.getNormals().size, copy.getNormals().size);
		for (i in 0 until tri.getNormals().size) {
			assertEquals(tri.getNormals()[i].x, copy.getNormals()[i].x);
			assertEquals(tri.getNormals()[i].y, copy.getNormals()[i].y);
		}

		assertEquals(tri.getVertices().size, copy.getVertices().size);
		for (i in 0 until tri.getVertices().size) {
			assertEquals(tri.getVertices()[i].x, copy.getVertices()[i].x);
			assertEquals(tri.getVertices()[i].y, copy.getVertices()[i].y);
		}

    }

}
