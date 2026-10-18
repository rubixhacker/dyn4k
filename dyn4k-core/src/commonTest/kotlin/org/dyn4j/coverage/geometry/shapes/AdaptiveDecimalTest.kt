/*
 * Copyright (c) 2010-2020 William Bittle  http://www.dyn4j.org/
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

class AdaptiveDecimalTest {
    @Test
    fun create() {

		var ed = AdaptiveDecimal(2);
		assertEquals(0, ed.size());
		assertEquals(2, ed.capacity());

		ed.append(1.0);

		var ed2 = AdaptiveDecimal(ed);
		assertEquals(1, ed.size());
		assertEquals(2, ed.capacity());

		ed2.clear();
		ed2.append(2.0);

		assertEquals(1.0, ed.get(0));

		var ed3 = AdaptiveDecimal.valueOf(10.0);
		assertEquals(10.0, ed3.get(0));

		var ed4 = AdaptiveDecimal.fromSum(0.1, 0.2);
		assertEquals(0.1 + 0.2, ed4.getEstimation());

		var ed5 = AdaptiveDecimal.fromDiff(0.1, 0.2);
		assertEquals(0.1 - 0.2, ed5.getEstimation());

		var ed6 = AdaptiveDecimal.fromProduct(0.1, 0.2);
		assertEquals(0.1 * 0.2, ed6.getEstimation());

		assertNotNull(ed.toString());

    }

    @Test
    fun size() {

		var ed = AdaptiveDecimal(2);
		assertEquals(0, ed.size());
		assertEquals(2, ed.capacity());

		ed.append(1.0);
		assertEquals(1, ed.size());
		assertEquals(2, ed.capacity());

    }

    @Test
    fun append() {

		var ed = AdaptiveDecimal(5);

		ed.append(1.0);
		assertEquals(1, ed.size());
		assertEquals(1.0, ed.get(0));

		ed.append(15.5);
		assertEquals(2, ed.size());
		assertEquals(15.5, ed.get(1));

		ed.appendNonZero(0.0);
		assertEquals(2, ed.size());

		ed.appendNonZero(111.0);
		assertEquals(3, ed.size());
		assertEquals(111.0, ed.get(2));

    }

    @Test
    fun copy() {

		var ed = AdaptiveDecimal(2);
		ed.append(0.1).append(15.0);

		var copy = ed.copy();

		assertEquals(0.1, copy.get(0));
		assertEquals(15.0, copy.get(1));

		copy.clear();
		copy.append(0.2);

		assertEquals(0.1, ed.get(0));
		assertEquals(15.0, ed.get(1));

		var copy2 = AdaptiveDecimal(5);
		copy2.set(ed);

		assertEquals(0.1, copy2.get(0));
		assertEquals(15.0, copy2.get(1));
		assertEquals(5, copy2.capacity());

		copy2.clear();
		copy2.append(0.2);

		assertEquals(0.1, ed.get(0));
		assertEquals(15.0, ed.get(1));

    }

    @Test
    fun clear() {

		var ed = AdaptiveDecimal(2);
		ed.append(0.1).append(15.0);

		assertEquals(2, ed.size());

		ed.clear();

		assertEquals(0, ed.size());

    }

    @Test
    fun removeZeros() {

		var ed = AdaptiveDecimal(6);

		ed.removeZeros();
		assertEquals(0, ed.size());

		ed.append(0.0);
		ed.removeZeros();
		assertEquals(0, ed.size());

		ed.append(0.1).append(2.0).append(0.0).append(10.5).append(0.0);
		ed.removeZeros();
		assertEquals(3, ed.size());

    }

    @Test
    fun negate() {

		var ed = AdaptiveDecimal(5);

		ed.negate();

		ed.append(1.0);
		ed = ed.sum(AdaptiveDecimal.valueOf(2.0));
		ed = ed.sum(AdaptiveDecimal.valueOf(3.0));
		ed = ed.sum(AdaptiveDecimal.valueOf(5.0));
		ed.negate();

		assertEquals(-11.0, ed.getEstimation());

		ed.clear();
		ed.append(-1.0);
		ed = ed.sum(AdaptiveDecimal.valueOf(-2.0));
		ed = ed.sum(AdaptiveDecimal.valueOf(-7.0));
		ed.negate();

		assertEquals(10.0, ed.getEstimation());
		ed.negate();
		assertEquals(-10.0, ed.getEstimation());

    }

    @Test
    fun getEstimation() {

		var ed = AdaptiveDecimal(5);

		assertEquals(0.0, ed.getEstimation());

		ed.append(0.0);
		ed = ed.sum(AdaptiveDecimal.valueOf(1.0e-5));
		ed = ed.sum(AdaptiveDecimal.valueOf(1.0e2));
		ed = ed.sum(AdaptiveDecimal.valueOf(1.0e100));

		assertEquals(1.0e100, ed.getEstimation());

		ed.clear();
		ed.append(1.0);
		ed = ed.sum(AdaptiveDecimal.valueOf(2.0));
		ed = ed.sum(AdaptiveDecimal.valueOf(3.0));
		ed = ed.sum(AdaptiveDecimal.valueOf(-5.0));

		assertEquals(1.0, ed.getEstimation());

    }

    @Test
    fun normalize() {

		var ed = AdaptiveDecimal(2);
		assertEquals(0, ed.size());
		ed.normalize();

		assertEquals(1, ed.size());

		var ed2 = AdaptiveDecimal(2);
		ed2.append(1.0).append(-4.0);
		ed2.normalize();

		assertEquals(2, ed2.size());
		assertEquals(1.0, ed2.get(0));
		assertEquals(-4.0, ed2.get(1));

    }

    @Test
    fun sum() {

		var ed1 = AdaptiveDecimal.valueOf(10.0);
		var ed2 = AdaptiveDecimal.valueOf(3.0);

		var result = ed1.sum(ed2);
		assertEquals(13.0, result.getEstimation(), 1.0e-9);

		var ed3 = AdaptiveDecimal.valueOf(0.35);

		var result2 = result.sum(ed3);
		assertEquals(13.35, result2.getEstimation(), 1.0e-9);

    }

    @Test
    fun checkInvariants() {

		var ed1 = AdaptiveDecimal(3);
		ed1.append(1.0).append(0.0).append(0.2);
		assertFalse(ed1.checkInvariants());

		var ed2 = AdaptiveDecimal(5);
		ed2.append(-1.0).append(0.0).append(0.0).append(0.2).append(0.0);
		assertFalse(ed2.checkInvariants());

		var ed3 = AdaptiveDecimal(2);
		ed3.append(1.0e-2).append(1.0e2 + 1.0e-2);
		assertFalse(ed3.checkInvariants());

		var ed4 = AdaptiveDecimal(5);
		ed4.append(-1.0 / 4.0).append(0.0).append(0.0).append(4.0 + 1.0 / 4.0).append(0.0);
		assertFalse(ed4.checkInvariants());

		var ed5 = AdaptiveDecimal(5);
		ed5.append(0.0).append(1.0 / 4.0).append(0.0).append(4.0 + 32.0).append(32.0 * 32.0);
		assertTrue(ed5.checkInvariants());
		ed5.ensureInvariants();

		var ed6 = AdaptiveDecimal(3);
		ed6.append(0.0).append(0.0).append(0.0);
		assertTrue(ed6.checkInvariants());
		ed5.ensureInvariants();

		var random = JavaRandom(0L);
		var iterations = 10000;

		var acc = AdaptiveDecimal.valueOf(0.0);

		for (i in 0 until iterations) {
			var test = AdaptiveDecimal.valueOf(random.nextDouble() * 10 - 5);
			acc = acc.sum(test);

			assertTrue(acc.checkInvariants());
		}

		for (i in 0 until iterations) {
			var a = random.nextDouble() * 10 - 5;
			var b = random.nextDouble() * 10 - 5;
			lateinit var test: AdaptiveDecimal

			test = AdaptiveDecimal.fromSum(a, b);
			assertTrue(test.checkInvariants());

			test = AdaptiveDecimal.fromDiff(a, b);
			assertTrue(test.checkInvariants());

			test = AdaptiveDecimal.fromProduct(a, b);
			assertTrue(test.checkInvariants());

			var c = random.nextDouble() * 10 - 5;
			var d = random.nextDouble() * 10 - 5;

			test = RobustGeometry.cross(a, b, c, d);
			assertTrue(test.checkInvariants());
		}

    }

    @Test
    fun testIndex1() {
        assertFailsWith<IndexOutOfBoundsException> {

		AdaptiveDecimal(1).get(-1);

        }
    }

    @Test
    fun testIndex2() {
        assertFailsWith<IndexOutOfBoundsException> {

		AdaptiveDecimal(2).get(2);

        }
    }

    @Test
    fun testIndex3() {
        assertFailsWith<IndexOutOfBoundsException> {

		AdaptiveDecimal(2).append(0.0).append(0.0).append(0.0);

        }
    }

    @Test
    fun testArgument1() {
        assertFailsWith<IllegalArgumentException> {

		AdaptiveDecimal(-5);

        }
    }

    @Test
    fun testArgument2() {
        assertFailsWith<IllegalArgumentException> {

		AdaptiveDecimal(0);

        }
    }

    @Test
    fun testState() {
        assertFailsWith<IllegalStateException> {

		var ed = AdaptiveDecimal(2);
		ed.append(1.0).append(0.5);
		ed.ensureInvariants();

        }
    }

}
