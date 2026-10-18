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

class RayTest {
    @Test
    fun createNullStart() {
        assertFailsWith<NullPointerException> {

		Ray(null, Math.toRadians(10));

        }
    }

    @Test
    fun createNullDirection() {
        assertFailsWith<NullPointerException> {

		Ray(Vector2(), null);

        }
    }

    @Test
    fun createZeroDirection() {
        assertFailsWith<IllegalArgumentException> {

		Ray(Vector2(), Vector2());

        }
    }

    @Test
    fun create() {

		var s = Vector2(1.0, 2.0);
		var r = Ray(s, Math.toRadians(10));

		assertSame(s, r.getStart());
		assertEquals(s.x, r.getStart().x, 1e-3);
		assertEquals(s.y, r.getStart().y, 1e-3);
		assertEquals(Math.toRadians(10), r.getDirection(), 1e-3);
		assertEquals(0.984, r.getDirectionVector().x, 1e-3);
		assertEquals(0.173, r.getDirectionVector().y, 1e-3);
		assertNotNull(r.toString());

    }

    @Test
    fun createFromOrigin() {

		var r = Ray(Math.toRadians(10));

		assertEquals(0.0, r.getStart().x, 1e-3);
		assertEquals(0.0, r.getStart().y, 1e-3);
		assertEquals(Math.toRadians(10), r.getDirection(), 1e-3);
		assertEquals(0.984, r.getDirectionVector().x, 1e-3);
		assertEquals(0.173, r.getDirectionVector().y, 1e-3);
		assertNotNull(r.toString());

    }

    @Test
    fun setStartNull() {
        assertFailsWith<NullPointerException> {

		var r = Ray(Math.toRadians(30));
		r.setStart(null);

        }
    }

    @Test
    fun setDirectionNull() {
        assertFailsWith<NullPointerException> {

		var r = Ray(Math.toRadians(30));
		r.setDirection(null);

        }
    }

    @Test
    fun setDirectionZero() {
        assertFailsWith<IllegalArgumentException> {

		var r = Ray(Math.toRadians(30));
		r.setDirection(Vector2());

        }
    }

    @Test
    fun setDirection() {

		var s = Vector2(1.0, 2.0);
		var r = Ray(s, Math.toRadians(10));

		assertSame(s, r.getStart());
		assertEquals(s.x, r.getStart().x, 1e-3);
		assertEquals(s.y, r.getStart().y, 1e-3);
		assertEquals(Math.toRadians(10), r.getDirection(), 1e-3);
		assertEquals(0.984, r.getDirectionVector().x, 1e-3);
		assertEquals(0.173, r.getDirectionVector().y, 1e-3);

		r.setDirection(Math.toRadians(30));

		assertSame(s, r.getStart());
		assertEquals(s.x, r.getStart().x, 1e-3);
		assertEquals(s.y, r.getStart().y, 1e-3);
		assertEquals(Math.toRadians(30), r.getDirection(), 1e-3);
		assertEquals(0.866, r.getDirectionVector().x, 1e-3);
		assertEquals(0.499, r.getDirectionVector().y, 1e-3);

		r.setDirection(Vector2(5.0, 7.0));

		assertSame(s, r.getStart());
		assertEquals(s.x, r.getStart().x, 1e-3);
		assertEquals(s.y, r.getStart().y, 1e-3);
		assertEquals(0.950, r.getDirection(), 1e-3);
		assertEquals(5.0, r.getDirectionVector().x, 1e-3);
		assertEquals(7.0, r.getDirectionVector().y, 1e-3);

    }

    @Test
    fun copy() {

		var ray = Ray(Vector2(1.0, 1.0), Math.toRadians(30));
		var copy = ray.copy();

		assertNotSame(ray, copy);
		assertNotSame(ray.getDirectionVector(), copy.getDirectionVector());
		assertNotSame(ray.getStart(), copy.getStart());
		assertEquals(ray.getDirectionVector().x, copy.getDirectionVector().x);
		assertEquals(ray.getDirectionVector().y, copy.getDirectionVector().y);
		assertEquals(ray.getStart().x, copy.getStart().x);
		assertEquals(ray.getStart().y, copy.getStart().y);

    }

}
