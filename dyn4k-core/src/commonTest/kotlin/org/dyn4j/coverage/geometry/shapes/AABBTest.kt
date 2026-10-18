/*
 * Copyright (c) 2010-2021 William Bittle  http://www.dyn4j.org/
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

class AABBTest {
    @Test
    fun createSuccess() {

		AABB(0.0, 0.0, 1.0, 1.0);
		AABB(-2.0, 2.0, -1.0, 5.0);
		AABB(Vector2(-3.0, 0.0), Vector2(-2.0, 2.0));

    }

    @Test
    fun createRadius() {

		var aabb = AABB(0.5);
		assertEquals(-0.500, aabb.getMinX(), 1.0e-3);
		assertEquals(-0.500, aabb.getMinY(), 1.0e-3);
		assertEquals( 0.500, aabb.getMaxX(), 1.0e-3);
		assertEquals( 0.500, aabb.getMaxY(), 1.0e-3);

		aabb = AABB(Vector2(-1.0, 1.0), 0.5);
		assertEquals(-1.500, aabb.getMinX(), 1.0e-3);
		assertEquals( 0.500, aabb.getMinY(), 1.0e-3);
		assertEquals(-0.500, aabb.getMaxX(), 1.0e-3);
		assertEquals( 1.500, aabb.getMaxY(), 1.0e-3);

    }

    @Test
    fun createRadiusNegative() {
        assertFailsWith<IllegalArgumentException> {

		AABB(Vector2(-1.0, 1.0), -1.0);

        }
    }

    @Test
    fun createCopy() {

		var aabb1 = AABB(Vector2(-3.0, 0.0), Vector2(-2.0, 2.0));
		var aabb2 = AABB(aabb1);
		assertNotSame(aabb1, aabb2);
		assertEquals(aabb1.getMinX(), aabb2.getMinX(), 1.0E-4);
		assertEquals(aabb1.getMinY(), aabb2.getMinY(), 1.0E-4);
		assertEquals(aabb1.getMaxX(), aabb2.getMaxX(), 1.0E-4);
		assertEquals(aabb1.getMaxY(), aabb2.getMaxY(), 1.0E-4);

    }

    @Test
    fun createFailure1() {
        assertFailsWith<IllegalArgumentException> {

		AABB(0.0, 0.0, -1.0, 2.0);

        }
    }

    @Test
    fun createFailure2() {
        assertFailsWith<IllegalArgumentException> {

		AABB(Vector2(0.0, 0.0), Vector2(-1.0, 2.0));

        }
    }

    @Test
    fun perimeter() {

		var aabb = AABB(-2.0, 0.0, 2.0, 1.0);

		assertEquals(10.0, aabb.getPerimeter(), 1.0E-4);

    }

    @Test
    fun area() {

		var aabb = AABB(-2.0, 0.0, 2.0, 1.0);

		assertEquals(4.0, aabb.getArea(), 1.0E-4);

    }

    @Test
    fun union() {

		var aabb1 = AABB(-2.0, 0.0, 2.0, 1.0);
		var aabb2 = AABB(-1.0, -2.0, 5.0, 0.5);

		var aabbr = aabb1.getUnion(aabb2);
		assertEquals(-2.0, aabbr.getMinX(), 1.0E-4);
		assertEquals(-2.0, aabbr.getMinY(), 1.0E-4);
		assertEquals(5.0, aabbr.getMaxX(), 1.0E-4);
		assertEquals(1.0, aabbr.getMaxY(), 1.0E-4);

		var aabb3 = AABB(-4.0, 2.0, -3.0, 4.0);
		aabbr = aabb1.getUnion(aabb3);
		assertEquals(-4.0, aabbr.getMinX(), 1.0E-4);
		assertEquals(0.0, aabbr.getMinY(), 1.0E-4);
		assertEquals(2.0, aabbr.getMaxX(), 1.0E-4);
		assertEquals(4.0, aabbr.getMaxY(), 1.0E-4);

		aabb1.union(aabb2);
		assertEquals(-2.0, aabb1.getMinX(), 1.0E-4);
		assertEquals(-2.0, aabb1.getMinY(), 1.0E-4);
		assertEquals(5.0, aabb1.getMaxX(), 1.0E-4);
		assertEquals(1.0, aabb1.getMaxY(), 1.0E-4);

		aabb1.union(aabb2, aabb3);
		assertEquals(-4.0, aabb1.getMinX(), 1.0E-4);
		assertEquals(-2.0, aabb1.getMinY(), 1.0E-4);
		assertEquals(5.0, aabb1.getMaxX(), 1.0E-4);
		assertEquals(4.0, aabb1.getMaxY(), 1.0E-4);

    }

    @Test
    fun expand() {

		var aabb = AABB(-2.0, 0.0, 4.0, 4.0);
		var aabb2 = aabb.getExpanded(2.0);

		assertNotSame(aabb, aabb2);

		aabb.expand(1.0);
		assertEquals(-2.5, aabb.getMinX(), 1.0E-4);
		assertEquals(-0.5, aabb.getMinY(), 1.0E-4);
		assertEquals(4.5, aabb.getMaxX(), 1.0E-4);
		assertEquals(4.5, aabb.getMaxY(), 1.0E-4);

		assertEquals(-3.0, aabb2.getMinX(), 1.0E-4);
		assertEquals(-1.0, aabb2.getMinY(), 1.0E-4);
		assertEquals(5.0, aabb2.getMaxX(), 1.0E-4);
		assertEquals(5.0, aabb2.getMaxY(), 1.0E-4);

		aabb2 = aabb.getExpanded(-1.0);
		assertEquals(-2.0, aabb2.getMinX(), 1.0E-4);
		assertEquals(0.0, aabb2.getMinY(), 1.0E-4);
		assertEquals(4.0, aabb2.getMaxX(), 1.0E-4);
		assertEquals(4.0, aabb2.getMaxY(), 1.0E-4);
		aabb.expand(-1.0);
		assertEquals(-2.0, aabb.getMinX(), 1.0E-4);
		assertEquals(0.0, aabb.getMinY(), 1.0E-4);
		assertEquals(4.0, aabb.getMaxX(), 1.0E-4);
		assertEquals(4.0, aabb.getMaxY(), 1.0E-4);

		aabb2 = aabb.getExpanded(-8.0);
		assertEquals(1.0, aabb2.getMinX(), 1.0E-4);
		assertEquals(2.0, aabb2.getMinY(), 1.0E-4);
		assertEquals(1.0, aabb2.getMaxX(), 1.0E-4);
		assertEquals(2.0, aabb2.getMaxY(), 1.0E-4);
		aabb.expand(-8.0);
		assertEquals(1.0, aabb.getMinX(), 1.0E-4);
		assertEquals(2.0, aabb.getMinY(), 1.0E-4);
		assertEquals(1.0, aabb.getMaxX(), 1.0E-4);
		assertEquals(2.0, aabb.getMaxY(), 1.0E-4);

    }

    @Test
    fun overlaps() {

		var aabb1 = AABB(-2.0, 0.0, 2.0, 1.0);
		var aabb2 = AABB(-1.0, -2.0, 5.0, 2.0);
		assertTrue(aabb1.overlaps(aabb2));
		assertTrue(aabb2.overlaps(aabb1));

		var aabb3 = AABB(3.0, 2.0, 4.0, 3.0);
		assertFalse(aabb1.overlaps(aabb3));
		assertFalse(aabb3.overlaps(aabb1));

		var aabb4 = AABB(-1.0, 0.25, 1.0, 0.75);
		assertTrue(aabb1.overlaps(aabb4));
		assertTrue(aabb4.overlaps(aabb1));

    }

    @Test
    fun contains() {

		var aabb1 = AABB(-2.0, 0.0, 2.0, 1.0);
		var aabb2 = AABB(-1.0, -2.0, 5.0, 2.0);
		assertFalse(aabb1.contains(aabb2));
		assertFalse(aabb2.contains(aabb1));

		var aabb3 = AABB(3.0, 2.0, 4.0, 3.0);
		assertFalse(aabb1.contains(aabb3));
		assertFalse(aabb3.contains(aabb1));

		var aabb4 = AABB(-1.0, 0.25, 1.0, 0.75);
		assertTrue(aabb1.contains(aabb4));
		assertFalse(aabb4.contains(aabb1));

    }

    @Test
    fun getWidth() {

		var aabb = AABB(-2.0, 0.0, 1.0, 1.0);

		assertEquals(3.0, aabb.getWidth());

    }

    @Test
    fun getHeight() {

		var aabb = AABB(-2.0, 0.0, 1.0, 1.0);

		assertEquals(1.0, aabb.getHeight());

    }

    @Test
    fun translate() {

		var aabb = AABB(-2.0, 0.0, 1.0, 1.0);

		var aabb2 = aabb.getTranslated(Vector2(-1.0, 2.0));
		assertNotSame(aabb, aabb2);

		assertEquals(-2.0, aabb.getMinX(), 1.0E-4);
		assertEquals( 0.0, aabb.getMinY(), 1.0E-4);
		assertEquals( 1.0, aabb.getMaxX(), 1.0E-4);
		assertEquals( 1.0, aabb.getMaxY(), 1.0E-4);

		assertEquals(-3.0, aabb2.getMinX(), 1.0E-4);
		assertEquals( 2.0, aabb2.getMinY(), 1.0E-4);
		assertEquals( 0.0, aabb2.getMaxX(), 1.0E-4);
		assertEquals( 3.0, aabb2.getMaxY(), 1.0E-4);

		aabb.translate(Vector2(-1.0, 2.0));

		assertEquals(-3.0, aabb.getMinX(), 1.0E-4);
		assertEquals( 2.0, aabb.getMinY(), 1.0E-4);
		assertEquals( 0.0, aabb.getMaxX(), 1.0E-4);
		assertEquals( 3.0, aabb.getMaxY(), 1.0E-4);

    }

    @Test
    fun containsPoint() {

		var aabb = AABB(-2.0, 0.0, 2.0, 1.0);

		assertTrue(aabb.contains(0.0, 0.5));
		assertTrue(aabb.contains(Vector2(0.0, 0.5)));

		assertFalse(aabb.contains(0.0, 2.0));
		assertFalse(aabb.contains(Vector2(0.0, 2.0)));

		assertTrue(aabb.contains(0.0, 1.0));
		assertTrue(aabb.contains(Vector2(0.0, 1.0)));

    }

    @Test
    fun intersection() {

		var aabb1 = AABB(-2.0, 0.0, 2.0, 1.0);
		var aabb2 = AABB(-1.0, -2.0, 5.0, 0.5);

		var aabbr = aabb1.getIntersection(aabb2);
		assertEquals(-1.0, aabbr.getMinX(), 1.0E-4);
		assertEquals(0.0, aabbr.getMinY(), 1.0E-4);
		assertEquals(2.0, aabbr.getMaxX(), 1.0E-4);
		assertEquals(0.5, aabbr.getMaxY(), 1.0E-4);

		var aabb3 = AABB(-4.0, 2.0, -3.0, 4.0);
		aabbr = aabb1.getIntersection(aabb3);
		assertEquals(0.0, aabbr.getMinX(), 1.0E-4);
		assertEquals(0.0, aabbr.getMinY(), 1.0E-4);
		assertEquals(0.0, aabbr.getMaxX(), 1.0E-4);
		assertEquals(0.0, aabbr.getMaxY(), 1.0E-4);

		aabbr.intersection(aabb1, aabb2);
		assertEquals(-1.0, aabbr.getMinX(), 1.0E-4);
		assertEquals(0.0, aabbr.getMinY(), 1.0E-4);
		assertEquals(2.0, aabbr.getMaxX(), 1.0E-4);
		assertEquals(0.5, aabbr.getMaxY(), 1.0E-4);

		aabbr.intersection(aabb1, aabb3);
		assertEquals(0.0, aabbr.getMinX(), 1.0E-4);
		assertEquals(0.0, aabbr.getMinY(), 1.0E-4);
		assertEquals(0.0, aabbr.getMaxX(), 1.0E-4);
		assertEquals(0.0, aabbr.getMaxY(), 1.0E-4);

		aabb1.intersection(aabb2);
		assertEquals(-1.0, aabb1.getMinX(), 1.0E-4);
		assertEquals(0.0, aabb1.getMinY(), 1.0E-4);
		assertEquals(2.0, aabb1.getMaxX(), 1.0E-4);
		assertEquals(0.5, aabb1.getMaxY(), 1.0E-4);

    }

    @Test
    fun degenerate() {

		var aabb = AABB(0.0, 0.0, 0.0, 0.0);
		assertTrue(aabb.isDegenerate());

		aabb = AABB(1.0, 2.0, 1.0, 3.0);
		assertTrue(aabb.isDegenerate());

		aabb = AABB(1.0, 0.0, 2.0, 1.0);
		assertFalse(aabb.isDegenerate());

		aabb = AABB(1.0, 0.0, 1.000001, 2.0);
		assertFalse(aabb.isDegenerate());
		assertFalse(aabb.isDegenerate(Epsilon.E));
		assertTrue(aabb.isDegenerate(0.000001));

    }

    @Test
    fun testEquals() {

		var aabb1 = AABB(-2.0, 0.0, 2.0, 1.0);
		var aabb2 = AABB(-1.0, -2.0, 5.0, 2.0);
		var aabb3 = AABB(-1.0, -2.0, 5.0, 2.0);

		assertFalse(aabb1.equals(null));
		assertTrue(aabb1.equals(aabb1));
		assertFalse(aabb1.equals(aabb2));
		assertFalse(aabb1.equals(aabb3));
		assertTrue(aabb2.equals(aabb3));
		assertFalse(aabb1.equals(Any()));

    }

    @Test
    fun testHashcode() {

		var aabb1 = AABB(-2.0, 0.0, 2.0, 1.0);
		var aabb2 = AABB(-1.0, -2.0, 5.0, 2.0);
		var aabb3 = AABB(-1.0, -2.0, 5.0, 2.0);

		assertEquals(aabb1.hashCode(), aabb1.hashCode());
		assertEquals(aabb2.hashCode(), aabb3.hashCode());
		assertFalse(aabb1.hashCode() == aabb2.hashCode());

    }

    @Test
    fun testToString() {

		var aabb1 = AABB(-2.0, 0.0, 2.0, 1.0);
		assertNotNull(aabb1.toString());

    }

    @Test
    fun createFromPoints() {

		var p1 = Vector2(1.0, 1.0);
		var p2 = Vector2(3.0, 3.0);

		var aabb = AABB.createFromPoints(p1, p2);

		assertEquals(1.0, aabb.getMinX());
		assertEquals(1.0, aabb.getMinY());
		assertEquals(3.0, aabb.getMaxX());
		assertEquals(3.0, aabb.getMaxY());

		aabb = AABB.createFromPoints(1.0, 4.0, 2.0, 2.0);

		assertEquals(1.0, aabb.getMinX());
		assertEquals(2.0, aabb.getMinY());
		assertEquals(2.0, aabb.getMaxX());
		assertEquals(4.0, aabb.getMaxY());

    }

    @Test
    fun setFromPoints() {

		var p1 = Vector2(1.0, 1.0);
		var p2 = Vector2(3.0, 3.0);

		var aabb = AABB(0.0,0.0,0.0,0.0);
		AABB.setFromPoints(p1, p2, aabb);

		assertEquals(1.0, aabb.getMinX());
		assertEquals(1.0, aabb.getMinY());
		assertEquals(3.0, aabb.getMaxX());
		assertEquals(3.0, aabb.getMaxY());

		AABB.setFromPoints(1.0, 4.0, 2.0, 2.0, aabb);

		assertEquals(1.0, aabb.getMinX());
		assertEquals(2.0, aabb.getMinY());
		assertEquals(2.0, aabb.getMaxX());
		assertEquals(4.0, aabb.getMaxY());

    }

    @Test
    fun copy() {

		var aabb = AABB(1.0,1.0,3.0,3.0);

		var copy = aabb.copy();

		assertEquals(aabb.getMinX(), copy.getMinX());
		assertEquals(aabb.getMinY(), copy.getMinY());
		assertEquals(aabb.getMaxX(), copy.getMaxX());
		assertEquals(aabb.getMaxY(), copy.getMaxY());

    }

    @Test
    fun getCenter() {

		var aabb = AABB(1.0,1.0,3.0,3.0);
		var c = aabb.getCenter();

		assertEquals(2.0, c.x);
		assertEquals(2.0, c.y);

    }

    @Test
    fun zero() {

		var aabb = AABB(1.0,1.0,3.0,3.0);

		assertEquals(1.0, aabb.getMinX());
		assertEquals(1.0, aabb.getMinY());
		assertEquals(3.0, aabb.getMaxX());
		assertEquals(3.0, aabb.getMaxY());

		aabb.zero();

		assertEquals(0.0, aabb.getMinX());
		assertEquals(0.0, aabb.getMinY());
		assertEquals(0.0, aabb.getMaxX());
		assertEquals(0.0, aabb.getMaxY());

    }

}
