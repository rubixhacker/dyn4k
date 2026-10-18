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

class FeatureTest {
    @Test
    fun create() {

		var pf1 = PointFeature(Vector2(1.0, 1.0), 1);
		var pf2 = PointFeature(Vector2(1.0, 2.0), 0);
		var ef = EdgeFeature(pf1, pf2, pf1, pf1.getPoint()!!.to(pf2.getPoint()!!), 2);

		assertEquals(1.0, pf1.getPoint()!!.x);
		assertEquals(1.0, pf1.getPoint()!!.y);
		assertEquals(1, pf1.getIndex());
		assertNotNull(pf1.toString());

		assertEquals(1.0, pf2.getPoint()!!.x);
		assertEquals(2.0, pf2.getPoint()!!.y);
		assertEquals(0, pf2.getIndex());
		assertNotNull(pf2.toString());

		assertEquals(pf1, ef.getMaximum());
		assertEquals(pf1, ef.getVertex1());
		assertEquals(pf2, ef.getVertex2());
		assertEquals(0.0, ef.getEdge()!!.x);
		assertEquals(1.0, ef.getEdge()!!.y);
		assertEquals(2, ef.getIndex());
		assertNotNull(ef.toString());

    }

    @Test
    fun createNonIndexed() {

		var pf1 = PointFeature(Vector2(1.0, 1.0), Feature.NOT_INDEXED);

		assertEquals(1.0, pf1.getPoint()!!.x);
		assertEquals(1.0, pf1.getPoint()!!.y);
		assertEquals(Feature.NOT_INDEXED, pf1.getIndex());
		assertNotNull(pf1.toString());

    }

    @Test
    fun copy() {

		var pf = PointFeature(Vector2(5.0, -4.0), 1);
		var cpf = pf.copy();

		assertNotSame(pf, cpf);
		assertNotSame(pf.getPoint()!!, cpf.getPoint()!!);
		assertEquals(pf.getIndex(), cpf.getIndex());
		assertEquals(pf.getPoint()!!.x, cpf.getPoint()!!.x);
		assertEquals(pf.getPoint()!!.y, cpf.getPoint()!!.y);

		var pf1 = PointFeature(Vector2(5.0, -4.0), 1);
		var pf2 = PointFeature(Vector2(5.0, -4.0), 2);
		var ef = EdgeFeature(pf1, pf2, pf1, Vector2(-1.0, 0.0), 1);
		var cef = ef.copy();

		assertNotSame(ef, cef);
		assertNotSame(ef.getVertex1()!!, cef.getVertex1()!!);
		assertNotSame(ef.getVertex1()!!.getPoint()!!, cef.getVertex1()!!.getPoint()!!);
		assertEquals(ef.getVertex1()!!.getIndex(), cef.getVertex1()!!.getIndex());
		assertEquals(ef.getVertex1()!!.getPoint()!!.x, cef.getVertex1()!!.getPoint()!!.x);
		assertEquals(ef.getVertex1()!!.getPoint()!!.y, cef.getVertex1()!!.getPoint()!!.y);
		assertNotSame(ef.getVertex2()!!, cef.getVertex2()!!);
		assertNotSame(ef.getVertex2()!!.getPoint()!!, cef.getVertex2()!!.getPoint()!!);
		assertEquals(ef.getVertex2()!!.getIndex(), cef.getVertex2()!!.getIndex());
		assertEquals(ef.getVertex2()!!.getPoint()!!.x, cef.getVertex2()!!.getPoint()!!.x);
		assertEquals(ef.getVertex2()!!.getPoint()!!.y, cef.getVertex2()!!.getPoint()!!.y);
		assertNotSame(ef.getMaximum()!!, cef.getMaximum()!!);
		assertNotSame(ef.getMaximum()!!.getPoint()!!, cef.getMaximum()!!.getPoint()!!);
		assertEquals(ef.getMaximum()!!.getIndex(), cef.getMaximum()!!.getIndex());
		assertEquals(ef.getMaximum()!!.getPoint()!!.x, cef.getMaximum()!!.getPoint()!!.x);
		assertEquals(ef.getMaximum()!!.getPoint()!!.y, cef.getMaximum()!!.getPoint()!!.y);
		assertNotSame(ef.getEdge()!!, cef.getEdge()!!);
		assertEquals(ef.getEdge()!!.x, cef.getEdge()!!.x);
		assertEquals(ef.getEdge()!!.y, cef.getEdge()!!.y);
		assertEquals(ef.getIndex(), cef.getIndex());

    }

}
