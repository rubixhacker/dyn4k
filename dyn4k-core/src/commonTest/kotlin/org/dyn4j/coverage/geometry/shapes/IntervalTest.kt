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

class IntervalTest {
    @Test
    fun createMinGreaterThanMax() {
        assertFailsWith<IllegalArgumentException> {

		Interval(0.0, -1.0);

        }
    }

    @Test
    fun create() {

		var i = Interval(0.0, 2.0);
		assertNotNull(i.toString());

    }

    @Test
    fun createCopy() {

		var i1 = Interval(-1.0, 2.0);
		var i2 = Interval(i1);

		assertNotSame(i2, i1);
		assertEquals(i1.getMin(), i2.getMin());
		assertEquals(i1.getMax(), i2.getMax());

    }

    @Test
    fun setInvalidMax() {
        assertFailsWith<IllegalArgumentException> {

		var i = Interval(0.0, 2.0);
		i.setMax(-1.0);

        }
    }

    @Test
    fun setMax() {

		var i = Interval(0.0, 2.0);
		i.setMax(1.5);

    }

    @Test
    fun setInvalidMin() {
        assertFailsWith<IllegalArgumentException> {

		var i = Interval(0.0, 2.0);
		i.setMin(3.0);

        }
    }

    @Test
    fun setMin() {

		var i = Interval(0.0, 2.0);
		i.setMin(1.5);

    }

    @Test
    fun includes() {

		var i = Interval(-2.5, 100.521);

		assertTrue(i.includesExclusive(50.0));
		assertTrue(!i.includesExclusive(100.521));
		assertTrue(!i.includesExclusive(-3.0));

		assertTrue(i.includesInclusive(50.0));
		assertTrue(i.includesInclusive(-2.5));
		assertTrue(!i.includesInclusive(-3.0));

		assertTrue(i.includesInclusiveMax(50.0));
		assertTrue(i.includesInclusiveMax(100.521));
		assertTrue(!i.includesInclusiveMax(-2.5));
		assertTrue(!i.includesInclusiveMax(200.0));

		assertTrue(i.includesInclusiveMin(50.0));
		assertTrue(i.includesInclusiveMin(-2.5));
		assertTrue(!i.includesInclusiveMin(100.521));
		assertTrue(!i.includesInclusiveMin(-3.0));

    }

    @Test
    fun overlaps() {

		var i1 = Interval(-2.0, 5.0);
		var i2 = Interval(-4.0, 1.0);

		assertTrue(i1.overlaps(i2));

		assertTrue(i2.overlaps(i1));

		assertEquals(0.0, i1.distance(i2));
		assertEquals(0.0, i2.distance(i1));

		var ov1 = i1.getOverlap(i2);
		var ov2 = i2.getOverlap(i1);

		assertEquals(3.0, ov1);
		assertEquals(3.0, ov2);

		var ov0 = i1.getOverlap(Interval(-10.0, -6.0));
		assertEquals(0.0, ov0);

    }

    @Test
    fun contains() {

		var i1 = Interval(-2.0, 5.0);
		var i2 = Interval(-1.0, 3.0);

		assertTrue(i1.containsExclusive(i2));
		assertFalse(i2.containsExclusive(i1));
		assertTrue(i1.containsInclusive(i2));
		assertFalse(i2.containsInclusive(i1));
		assertTrue(i1.containsInclusiveMax(i2));
		assertFalse(i2.containsInclusiveMax(i1));
		assertTrue(i1.containsInclusiveMin(i2));
		assertFalse(i2.containsInclusiveMin(i1));


		i1 = Interval(-1.0, 5.0);
		i2 = Interval(-1.0, 3.0);

		assertFalse(i1.containsExclusive(i2));
		assertFalse(i2.containsExclusive(i1));
		assertTrue(i1.containsInclusive(i2));
		assertFalse(i2.containsInclusive(i1));
		assertFalse(i1.containsInclusiveMax(i2));
		assertFalse(i2.containsInclusiveMax(i1));
		assertTrue(i1.containsInclusiveMin(i2));
		assertFalse(i2.containsInclusiveMin(i1));


		i1 = Interval(-2.0, 5.0);
		i2 = Interval(-1.0, 5.0);

		assertFalse(i1.containsExclusive(i2));
		assertFalse(i2.containsExclusive(i1));
		assertTrue(i1.containsInclusive(i2));
		assertFalse(i2.containsInclusive(i1));
		assertTrue(i1.containsInclusiveMax(i2));
		assertFalse(i2.containsInclusiveMax(i1));
		assertFalse(i1.containsInclusiveMin(i2));
		assertFalse(i2.containsInclusiveMin(i1));


		i1 = Interval(-1.0, 5.0);
		i2 = Interval(-1.0, 5.0);

		assertFalse(i1.containsExclusive(i2));
		assertFalse(i2.containsExclusive(i1));
		assertTrue(i1.containsInclusive(i2));
		assertTrue(i2.containsInclusive(i1));
		assertFalse(i1.containsInclusiveMax(i2));
		assertFalse(i2.containsInclusiveMax(i1));
		assertFalse(i1.containsInclusiveMin(i2));
		assertFalse(i2.containsInclusiveMin(i1));

    }

    @Test
    fun clamp() {

		var i = Interval(-1.0, 6.5);

		assertEquals(2.0, i.clamp(2.0));
		assertEquals(2.0, Interval.clamp(2.0, -1.0, 6.5));
		assertEquals(-1.0, i.clamp(-2.0));
		assertEquals(6.5, i.clamp(7.0));

    }

    @Test
    fun degenerate() {

		var i = Interval(2.0, 2.0);

		assertTrue(i.isDegenerate());

		i.expand(0.000001);

		assertEquals(1.9999995, i.getMin());
		assertEquals(2.0000005, i.getMax());

		assertTrue(!i.isDegenerate());
		assertTrue(!i.isDegenerate(0.0));
		assertTrue(i.isDegenerate(0.01));

    }

    @Test
    fun union() {

		var i1 = Interval(-2.0, 3.0);
		var i2 = Interval(-1.0, 4.0);

		var u = i1.getUnion(i2);
		assertEquals(-2.0, u.getMin());
		assertEquals(4.0, u.getMax());

		u = i2.getUnion(i1);
		assertEquals(-2.0, u.getMin());
		assertEquals(4.0, u.getMax());

		var i3 = Interval(-3.0, -2.5);
		u = i1.getUnion(i3);
		assertEquals(-3.0, u.getMin());
		assertEquals(3.0, u.getMax());

		i1.union(i2);
		assertEquals(-2.0, i1.getMin());
		assertEquals(4.0, i1.getMax());

		i1.setMin(-2.0);
		i1.setMax(3.0);
		i1.union(i3);
		assertEquals(-3.0, i1.getMin());
		assertEquals(3.0, i1.getMax());

    }

    @Test
    fun intersection() {

		var i1 = Interval(-2.0, 3.0);
		var i2 = Interval(-1.0, 4.0);

		var u = i1.getIntersection(i2);
		assertEquals(-1.0, u.getMin());
		assertEquals(3.0, u.getMax());

		u = i2.getIntersection(i1);
		assertEquals(-1.0, u.getMin());
		assertEquals(3.0, u.getMax());

		var i3 = Interval(-3.0, -2.5);
		u = i1.getIntersection(i3);
		assertEquals(0.0, u.getMin());
		assertEquals(0.0, u.getMax());

		i1.intersection(i2);
		assertEquals(-1.0, i1.getMin());
		assertEquals(3.0, i1.getMax());

		i1.setMin(-2.0);
		i1.setMax(3.0);
		i1.intersection(i3);
		assertEquals(0.0, i1.getMin());
		assertEquals(0.0, i1.getMax());

    }

    @Test
    fun distance() {

		var i1 = Interval(-2.0, 3.0);
		var i2 = Interval(-1.0, 4.0);

		assertEquals(0.0, i1.distance(i2));

		i2 = Interval(4.0, 6.0);

		assertEquals(1.0, i1.distance(i2));
		assertEquals(1.0, i2.distance(i1));

    }

    @Test
    fun expand() {

		var i = Interval(-2.0, 2.0);
		lateinit var ci: Interval;

		ci = i.getExpanded(2.0);
		assertEquals(-3.0, ci.getMin(), 1.0e-3);
		assertEquals( 3.0, ci.getMax(), 1.0e-3);
		i.expand(2.0);
		assertEquals(-3.0, i.getMin(), 1.0e-3);
		assertEquals( 3.0, i.getMax(), 1.0e-3);

		ci = i.getExpanded(0.0);
		assertEquals(-3.0, ci.getMin(), 1.0e-3);
		assertEquals( 3.0, ci.getMax(), 1.0e-3);
		i.expand(0.0);
		assertEquals(-3.0, i.getMin(), 1.0e-3);
		assertEquals( 3.0, i.getMax(), 1.0e-3);

		ci = i.getExpanded(-1.0);
		assertEquals(-2.5, ci.getMin(), 1.0e-3);
		assertEquals( 2.5, ci.getMax(), 1.0e-3);
		i.expand(-1.0);
		assertEquals(-2.5, i.getMin(), 1.0e-3);
		assertEquals( 2.5, i.getMax(), 1.0e-3);




		ci = i.getExpanded(-6.0);
		assertEquals(0.0, ci.getMin(), 1.0e-3);
		assertEquals(0.0, ci.getMax(), 1.0e-3);
		i.expand(-6.0);
		assertEquals(0.0, i.getMin(), 1.0e-3);
		assertEquals(0.0, i.getMax(), 1.0e-3);

		i = Interval(-2.5, 1.5);
		ci = i.getExpanded(-6.0);
		assertEquals(-0.5, ci.getMin(), 1.0e-3);
		assertEquals(-0.5, ci.getMax(), 1.0e-3);
		i.expand(-6.0);
		assertEquals(-0.5, i.getMin(), 1.0e-3);
		assertEquals(-0.5, i.getMax(), 1.0e-3);

    }

    @Test
    fun getLength() {

		var i = Interval(-2.0, 2.0);
		assertEquals(4.0, i.getLength());

		i = Interval(-1.0, 2.0);
		assertEquals(3.0, i.getLength());

		i = Interval(-3.0, -1.0);
		assertEquals(2.0, i.getLength());

		i = Interval(2.0, 3.0);
		assertEquals(1.0, i.getLength());

		i = Interval(-1.0, 2.0);
		i.expand(-4.0);
		assertEquals(0.0, i.getLength());

		i = Interval(-1.0, -1.0);
		assertEquals(0.0, i.getLength());

    }

    @Test
    fun copy() {

		var i = Interval(-1.0, 0.0);
		var copy = i.copy();

		assertNotSame(i, copy);
		assertEquals(i.getMax(), copy.getMax());
		assertEquals(i.getMin(), copy.getMin());

    }

    @Test
    fun set() {

		var i = Interval(-1.0, 0.0);
		var o = Interval(0.0, 0.0);
		o.set(i);

		assertNotSame(i, o);
		assertEquals(i.getMax(), o.getMax());
		assertEquals(i.getMin(), o.getMin());

    }

}
