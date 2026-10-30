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

val LinkTest by testSuite {
    test("createCoincident") { LinkTestFixture().run { createCoincident() } }
    test("creatSuccess") { LinkTestFixture().run { creatSuccess() } }
    test("rotate") { LinkTestFixture().run { rotate() } }
    test("translate") { LinkTestFixture().run { translate() } }
    test("copy") { LinkTestFixture().run { copy() } }
    test("copyNonLoop") { LinkTestFixture().run { copyNonLoop() } }
}

private class LinkTestFixture  {
fun createCoincident() {
        assertFailsWith<IllegalArgumentException> {

		Link(null, Vector2(), Vector2(), null);

        }
    }

fun creatSuccess() {

		var l = Link(
			null,
			Vector2(0.0, 1.0),
			Vector2(1.0, 2.0),
			null
		);

		assertEquals(0.500, l.getCenter().x, 1.0e-3);
		assertEquals(1.500, l.getCenter().y, 1.0e-3);
		assertNotNull(l.toString());
		assertNotNull(l.getVertexIterator());
		assertEquals(WoundIterator::class, l.getVertexIterator()::class);
		assertNotNull(l.getNormalIterator());
		assertEquals(WoundIterator::class, l.getNormalIterator()::class);
		assertNull(l.getPoint0());
		assertNotNull(l.getPoint1());
		assertNotNull(l.getPoint2());
		assertEquals(l.getVertices()[0], l.getPoint1());
		assertEquals(l.getVertices()[1], l.getPoint2());
		assertNull(l.getPoint3());

    }

fun rotate() {

		var links = Geometry.createLinks(arrayOf(
			Vector2(0.0, 0.0),
			Vector2(1.0, 0.0),
			Vector2(2.0, 1.0),
			Vector2(3.0, 1.0),
		), false);

		assertEquals(3, links.size);

		for (link in links) {
			try { link.rotate(Math.toRadians(30)); fail(); } catch (ex: UnsupportedOperationException) { }
			try { link.rotate(Rotation.of(Math.toRadians(40))); fail(); } catch (ex: UnsupportedOperationException) { }
			try { link.rotate(Math.toRadians(40), Vector2(1.0, 2.0)); fail(); } catch (ex: UnsupportedOperationException) { }
			try { link.rotate(Rotation.of(Math.toRadians(20)), Vector2(0.0, 3.0)); fail(); } catch (ex: UnsupportedOperationException) { }
			try { link.rotate(Math.toRadians(10), 2.0, -1.0); fail(); } catch (ex: UnsupportedOperationException) { }
			try { link.rotate(Rotation.of(Math.toRadians(45)), -1.0, -1.0); fail(); } catch (ex: UnsupportedOperationException) { }
			try { link.rotateAboutCenter(Math.toRadians(26)); fail(); } catch (ex: UnsupportedOperationException) { }
		}

    }

fun translate() {

		var links = Geometry.createLinks(arrayOf(
			Vector2(0.0, 0.0),
			Vector2(1.0, 0.0),
			Vector2(2.0, 1.0),
			Vector2(3.0, 1.0),
		), false);

		assertEquals(3, links.size);

		for (link in links) {
			try { link.translate(Vector2(1.0, 1.0)); fail(); } catch (ex: UnsupportedOperationException) { }
			try { link.translate(6.0, 7.0); fail(); } catch (ex: UnsupportedOperationException) { }
		}

    }

fun copy() {

		var link = Link(
				Vector2(0.0, 0.0),
				Vector2(1.0, 1.0),
				Vector2(2.0, 1.0),
				Vector2(3.0, 0.0));
		link.setUserData(Any());

		var copy = link.copy();

		assertNotSame(link, copy);
		assertNotSame(link.getPoint0(), copy.getPoint0());
		assertNotSame(link.getPoint3(), copy.getPoint3());
		assertNotSame(link.getCenter(), copy.getCenter());
		assertNotSame(link.getNormals(), copy.getNormals());
		assertNotSame(link.getVertices(), copy.getVertices());
		assertEquals(link.getLength(), copy.getLength());
		assertEquals(link.getRadius(), copy.getRadius());
		assertNull(copy.getUserData());

		assertEquals(link.getCenter().x, copy.getCenter().x);
		assertEquals(link.getCenter().y, copy.getCenter().y);
		assertEquals(link.getPoint0()!!.x, copy.getPoint0()!!.x);
		assertEquals(link.getPoint0()!!.y, copy.getPoint0()!!.y);
		assertEquals(link.getPoint3()!!.x, copy.getPoint3()!!.x);
		assertEquals(link.getPoint3()!!.y, copy.getPoint3()!!.y);

		assertEquals(link.getNormals().size, copy.getNormals().size);
		for (i in 0 until link.getNormals().size) {
			assertEquals(link.getNormals()[i].x, copy.getNormals()[i].x);
			assertEquals(link.getNormals()[i].y, copy.getNormals()[i].y);
		}

		assertEquals(link.getVertices().size, copy.getVertices().size);
		for (i in 0 until link.getVertices().size) {
			assertEquals(link.getVertices()[i].x, copy.getVertices()[i].x);
			assertEquals(link.getVertices()[i].y, copy.getVertices()[i].y);
		}

    }

fun copyNonLoop() {

		var points = mutableListOf<Vector2>();
		points.add(Vector2(0.0, 0.0));
		points.add(Vector2(1.0, 0.0));
		points.add(Vector2(2.0, 1.0));
		points.add(Vector2(3.0, 1.0));
		points.add(Vector2(2.0, 2.0));

		var links = Geometry.createLinks(points, false);

		for (link in links) {
			var copy = link.copy();

			assertNotSame(link, copy);
			if (link.getPoint0() != null) {
				assertNotSame(link.getPoint0(), copy.getPoint0());
			} else {
				assertNull(copy.getPoint0());
			}
			if (link.getPoint3() != null) {
				assertNotSame(link.getPoint3(), copy.getPoint3());
		} else {
				assertNull(copy.getPoint3());
			}
			assertNotSame(link.getCenter(), copy.getCenter());
			assertNotSame(link.getNormals(), copy.getNormals());
			assertNotSame(link.getVertices(), copy.getVertices());
			assertEquals(link.getLength(), copy.getLength());
			assertEquals(link.getRadius(), copy.getRadius());
			assertNull(copy.getUserData());

			assertEquals(link.getCenter().x, copy.getCenter().x);
			assertEquals(link.getCenter().y, copy.getCenter().y);
			if (link.getPoint0() != null) {
				assertEquals(link.getPoint0()!!.x, copy.getPoint0()!!.x);
				assertEquals(link.getPoint0()!!.y, copy.getPoint0()!!.y);
			}
			if (link.getPoint3() != null) {
				assertEquals(link.getPoint3()!!.x, copy.getPoint3()!!.x);
				assertEquals(link.getPoint3()!!.y, copy.getPoint3()!!.y);
			}

			assertEquals(link.getNormals().size, copy.getNormals().size);
			for (i in 0 until link.getNormals().size) {
				assertEquals(link.getNormals()[i].x, copy.getNormals()[i].x);
				assertEquals(link.getNormals()[i].y, copy.getNormals()[i].y);
			}

			assertEquals(link.getVertices().size, copy.getVertices().size);
			for (i in 0 until link.getVertices().size) {
				assertEquals(link.getVertices()[i].x, copy.getVertices()[i].x);
				assertEquals(link.getVertices()[i].y, copy.getVertices()[i].y);
			}
		}

    }

}
