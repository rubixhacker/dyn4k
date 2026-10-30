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
package org.dyn4j.coverage

import de.infix.testBalloon.framework.core.testSuite
import org.dyn4j.Epsilon
import org.dyn4j.geometry.*
import kotlin.math.*
import kotlin.test.*

val UpstreamMatrix33CoverageTest by testSuite {
    test("createFull") { UpstreamMatrix33CoverageTestFixture().run { createFull() } }
    test("createFullArray") { UpstreamMatrix33CoverageTestFixture().run { createFullArray() } }
    test("createNullArray") { UpstreamMatrix33CoverageTestFixture().run { createNullArray() } }
    test("createPartialArray") { UpstreamMatrix33CoverageTestFixture().run { createPartialArray() } }
    test("equalsHashcode") { UpstreamMatrix33CoverageTestFixture().run { equalsHashcode() } }
    test("copy") { UpstreamMatrix33CoverageTestFixture().run { copy() } }
    test("add") { UpstreamMatrix33CoverageTestFixture().run { add() } }
    test("sum") { UpstreamMatrix33CoverageTestFixture().run { sum() } }
    test("subtract") { UpstreamMatrix33CoverageTestFixture().run { subtract() } }
    test("difference") { UpstreamMatrix33CoverageTestFixture().run { difference() } }
    test("multiplyMatrix") { UpstreamMatrix33CoverageTestFixture().run { multiplyMatrix() } }
    test("productMatrix") { UpstreamMatrix33CoverageTestFixture().run { productMatrix() } }
    test("multiplyVector") { UpstreamMatrix33CoverageTestFixture().run { multiplyVector() } }
    test("productVector") { UpstreamMatrix33CoverageTestFixture().run { productVector() } }
    test("multiplyVectorT") { UpstreamMatrix33CoverageTestFixture().run { multiplyVectorT() } }
    test("productVectorT") { UpstreamMatrix33CoverageTestFixture().run { productVectorT() } }
    test("multiplyScalar") { UpstreamMatrix33CoverageTestFixture().run { multiplyScalar() } }
    test("productScalar") { UpstreamMatrix33CoverageTestFixture().run { productScalar() } }
    test("identity") { UpstreamMatrix33CoverageTestFixture().run { identity() } }
    test("transpose") { UpstreamMatrix33CoverageTestFixture().run { transpose() } }
    test("getTranspose") { UpstreamMatrix33CoverageTestFixture().run { getTranspose() } }
    test("determinant") { UpstreamMatrix33CoverageTestFixture().run { determinant() } }
    test("invert") { UpstreamMatrix33CoverageTestFixture().run { invert() } }
    test("getInverse") { UpstreamMatrix33CoverageTestFixture().run { getInverse() } }
    test("solve22") { UpstreamMatrix33CoverageTestFixture().run { solve22() } }
    test("solve33") { UpstreamMatrix33CoverageTestFixture().run { solve33() } }
}

private class UpstreamMatrix33CoverageTestFixture  {
fun createFull() {
        var m = Matrix33(1.0, 2.0, 1.0,
            -3.0, 8.0, 2.0,
            1.0, 5.0, -1.0)
        assertEquals(1.0, m.m00)
        assertEquals(2.0, m.m01)
        assertEquals(1.0, m.m02)
        assertEquals(-3.0, m.m10)
        assertEquals(8.0, m.m11)
        assertEquals(2.0, m.m12)
        assertEquals(1.0, m.m20)
        assertEquals(5.0, m.m21)
        assertEquals(-1.0, m.m22)
        assertNotNull(m.toString())
    }

fun createFullArray() {
        var m = Matrix33(doubleArrayOf(1.0, 2.0, 1.0,
            -3.0, 8.0, 2.0,
            1.0, 5.0, -1.0))
        assertEquals(1.0, m.m00)
        assertEquals(2.0, m.m01)
        assertEquals(1.0, m.m02)
        assertEquals(-3.0, m.m10)
        assertEquals(8.0, m.m11)
        assertEquals(2.0, m.m12)
        assertEquals(1.0, m.m20)
        assertEquals(5.0, m.m21)
        assertEquals(-1.0, m.m22)
    }

fun createNullArray() {
        assertFailsWith<NullPointerException> {
            Matrix33(null)
        }
    }

fun createPartialArray() {
        assertFailsWith<IndexOutOfBoundsException> {
            Matrix33(doubleArrayOf(1.0, 2.0, 1.0,
                -3.0, 8.0, 2.0,
                1.0, 5.0))
        }
    }

fun equalsHashcode() {
        var m = Matrix33(1.0, 2.0, 1.0,
            -3.0, 8.0, 2.0,
            1.0, 5.0, -1.0)
        assertTrue(m.equals(m))
        var m2 = Matrix33(m)
        assertNotSame(m, m2)
        assertTrue(m.equals(m2))
        assertTrue(m2.equals(m))
        assertEquals(m.hashCode(), m2.hashCode())
        m2.m22 = -5.0
        assertNotSame(m, m2)
        assertFalse(m.equals(m2))
        assertFalse(m2.equals(m))
        assertFalse(m.hashCode() == m2.hashCode())
        assertFalse(m.equals(null))
        assertFalse(m.equals(Any()))
    }

fun copy() {
        var m1 = Matrix33(0.0, 1.0, -1.0,
            2.0, -1.0, 3.0,
            3.0, 2.5, 0.5)
        var m2 = Matrix33(m1)
        assertEquals(m2.m00, m1.m00)
        assertEquals(m2.m01, m1.m01)
        assertEquals(m2.m02, m1.m02)
        assertEquals(m2.m10, m1.m10)
        assertEquals(m2.m11, m1.m11)
        assertEquals(m2.m12, m1.m12)
        assertEquals(m2.m20, m1.m20)
        assertEquals(m2.m21, m1.m21)
        assertEquals(m2.m22, m1.m22)
    }

fun add() {
        var m1 = Matrix33(0.0, 2.0, 0.0,
            3.0, 1.0, 1.0,
            2.0, 0.0, -1.0)
        var m2 = Matrix33(1.0, 1.0, 3.0,
            0.0, 4.0, 1.0,
            2.0, 2.0, 1.0)
        m1.add(m2)
        assertEquals(1.0, m1.m00)
        assertEquals(3.0, m1.m01)
        assertEquals(3.0, m1.m02)
        assertEquals(3.0, m1.m10)
        assertEquals(5.0, m1.m11)
        assertEquals(2.0, m1.m12)
        assertEquals(4.0, m1.m20)
        assertEquals(2.0, m1.m21)
        assertEquals(0.0, m1.m22)
    }

fun sum() {
        var m1 = Matrix33(0.0, 2.0, 0.0,
            3.0, 1.0, 1.0,
            2.0, 0.0, -1.0)
        var m2 = Matrix33(1.0, 1.0, 3.0,
            0.0, 4.0, 1.0,
            2.0, 2.0, 1.0)
        var m3 = m1.sum(m2)
        assertEquals(1.0, m3.m00)
        assertEquals(3.0, m3.m01)
        assertEquals(3.0, m3.m02)
        assertEquals(3.0, m3.m10)
        assertEquals(5.0, m3.m11)
        assertEquals(2.0, m3.m12)
        assertEquals(4.0, m3.m20)
        assertEquals(2.0, m3.m21)
        assertEquals(0.0, m3.m22)
        assertFalse(m1.equals(m3))
    }

fun subtract() {
        var m1 = Matrix33(0.0, 2.0, 0.0,
            3.0, 1.0, 1.0,
            2.0, 0.0, -1.0)
        var m2 = Matrix33(1.0, 1.0, 3.0,
            0.0, 4.0, 1.0,
            2.0, 2.0, 1.0)
        m1.subtract(m2)
        assertEquals(-1.0, m1.m00)
        assertEquals( 1.0, m1.m01)
        assertEquals(-3.0, m1.m02)
        assertEquals( 3.0, m1.m10)
        assertEquals(-3.0, m1.m11)
        assertEquals( 0.0, m1.m12)
        assertEquals( 0.0, m1.m20)
        assertEquals(-2.0, m1.m21)
        assertEquals(-2.0, m1.m22)
    }

fun difference() {
        var m1 = Matrix33(0.0, 2.0, 0.0,
            3.0, 1.0, 1.0,
            2.0, 0.0, -1.0)
        var m2 = Matrix33(1.0, 1.0, 3.0,
            0.0, 4.0, 1.0,
            2.0, 2.0, 1.0)
        var m3 = m1.difference(m2)
        assertEquals(-1.0, m3.m00)
        assertEquals( 1.0, m3.m01)
        assertEquals(-3.0, m3.m02)
        assertEquals( 3.0, m3.m10)
        assertEquals(-3.0, m3.m11)
        assertEquals( 0.0, m3.m12)
        assertEquals( 0.0, m3.m20)
        assertEquals(-2.0, m3.m21)
        assertEquals(-2.0, m3.m22)
        assertFalse(m1.equals(m3))
    }

fun multiplyMatrix() {
        var m1 = Matrix33(0.0, 2.0, 0.0,
            3.0, 1.0, 1.0,
            2.0, 0.0, -1.0)
        var m2 = Matrix33(1.0, 1.0, 3.0,
            0.0, 4.0, 1.0,
            2.0, 2.0, 1.0)
        m1.multiply(m2)
        assertEquals(0.0, m1.m00)
        assertEquals(8.0, m1.m01)
        assertEquals(2.0, m1.m02)
        assertEquals(5.0, m1.m10)
        assertEquals(9.0, m1.m11)
        assertEquals(11.0, m1.m12)
        assertEquals(0.0, m1.m20)
        assertEquals(0.0, m1.m21)
        assertEquals(5.0, m1.m22)
    }

fun productMatrix() {
        var m1 = Matrix33(0.0, 2.0, 0.0,
            3.0, 1.0, 1.0,
            2.0, 0.0, -1.0)
        var m2 = Matrix33(1.0, 1.0, 3.0,
            0.0, 4.0, 1.0,
            2.0, 2.0, 1.0)
        var m3 = m1.product(m2)
        assertEquals(0.0, m3.m00)
        assertEquals(8.0, m3.m01)
        assertEquals(2.0, m3.m02)
        assertEquals(5.0, m3.m10)
        assertEquals(9.0, m3.m11)
        assertEquals(11.0, m3.m12)
        assertEquals(0.0, m3.m20)
        assertEquals(0.0, m3.m21)
        assertEquals(5.0, m3.m22)
        assertFalse(m1.equals(m3))
    }

fun multiplyVector() {
        var m1 = Matrix33(0.0, 2.0, 0.0,
            3.0, 1.0, 1.0,
            2.0, 0.0, -1.0)
        var v1 = Vector3(1.0, -1.0, 2.0)
        m1.multiply(v1)
        assertEquals(-2.0, v1.x)
        assertEquals( 4.0, v1.y)
        assertEquals( 0.0, v1.z)
    }

fun productVector() {
        var m1 = Matrix33(0.0, 2.0, 0.0,
            3.0, 1.0, 1.0,
            2.0, 0.0, -1.0)
        var v1 = Vector3(1.0, -1.0, 2.0)
        var v2 = m1.product(v1)
        assertEquals(-2.0, v2.x)
        assertEquals( 4.0, v2.y)
        assertEquals( 0.0, v2.z)
        assertFalse(v1.equals(v2))
    }

fun multiplyVectorT() {
        var m1 = Matrix33(0.0, 2.0, 0.0,
            3.0, 1.0, 1.0,
            2.0, 0.0, -1.0)
        var v1 = Vector3(1.0, -1.0, 2.0)
        m1.multiplyT(v1)
        assertEquals( 1.0, v1.x)
        assertEquals( 1.0, v1.y)
        assertEquals(-3.0, v1.z)
    }

fun productVectorT() {
        var m1 = Matrix33(0.0, 2.0, 0.0,
            3.0, 1.0, 1.0,
            2.0, 0.0, -1.0)
        var v1 = Vector3(1.0, -1.0, 2.0)
        var v2 = m1.productT(v1)
        assertEquals( 1.0, v2.x)
        assertEquals( 1.0, v2.y)
        assertEquals(-3.0, v2.z)
        assertFalse(v1.equals(v2))
    }

fun multiplyScalar() {
        var m1 = Matrix33(0.0, 2.0, 0.0,
            3.0, 1.0, 1.0,
            2.0, 0.0, -1.0)
        m1.multiply(2.0)
        assertEquals(0.0, m1.m00)
        assertEquals(4.0, m1.m01)
        assertEquals(0.0, m1.m02)
        assertEquals(6.0, m1.m10)
        assertEquals(2.0, m1.m11)
        assertEquals(2.0, m1.m12)
        assertEquals(4.0, m1.m20)
        assertEquals(0.0, m1.m21)
        assertEquals(-2.0, m1.m22)
    }

fun productScalar() {
        var m1 = Matrix33(0.0, 2.0, 0.0,
            3.0, 1.0, 1.0,
            2.0, 0.0, -1.0)
        var m2 = m1.product(2.0)
        assertEquals(0.0, m2.m00)
        assertEquals(4.0, m2.m01)
        assertEquals(0.0, m2.m02)
        assertEquals(6.0, m2.m10)
        assertEquals(2.0, m2.m11)
        assertEquals(2.0, m2.m12)
        assertEquals(4.0, m2.m20)
        assertEquals(0.0, m2.m21)
        assertEquals(-2.0, m2.m22)
        assertFalse(m1.equals(m2))
    }

fun identity() {
        var m1 = Matrix33(0.0, 2.0, 0.0,
            3.0, 1.0, 1.0,
            2.0, 0.0, -1.0)
        m1.identity()
        assertEquals(1.0, m1.m00)
        assertEquals(0.0, m1.m01)
        assertEquals(0.0, m1.m02)
        assertEquals(0.0, m1.m10)
        assertEquals(1.0, m1.m11)
        assertEquals(0.0, m1.m12)
        assertEquals(0.0, m1.m20)
        assertEquals(0.0, m1.m21)
        assertEquals(1.0, m1.m22)
    }

fun transpose() {
        var m1 = Matrix33(0.0, 2.0, 0.0,
            3.0, 1.0, 1.0,
            2.0, 0.0, -1.0)
        m1.transpose()
        assertEquals(0.0, m1.m00)
        assertEquals(3.0, m1.m01)
        assertEquals(2.0, m1.m02)
        assertEquals(2.0, m1.m10)
        assertEquals(1.0, m1.m11)
        assertEquals(0.0, m1.m12)
        assertEquals(0.0, m1.m20)
        assertEquals(1.0, m1.m21)
        assertEquals(-1.0, m1.m22)
    }

fun getTranspose() {
        var m1 = Matrix33(0.0, 2.0, 0.0,
            3.0, 1.0, 1.0,
            2.0, 0.0, -1.0)
        var m2 = m1.getTranspose()
        assertEquals(0.0, m2.m00)
        assertEquals(3.0, m2.m01)
        assertEquals(2.0, m2.m02)
        assertEquals(2.0, m2.m10)
        assertEquals(1.0, m2.m11)
        assertEquals(0.0, m2.m12)
        assertEquals(0.0, m2.m20)
        assertEquals(1.0, m2.m21)
        assertEquals(-1.0, m2.m22)
        assertFalse(m1.equals(m2))
    }

fun determinant() {
        var m1 = Matrix33(1.0, 0.0, 5.0,
            2.0, 1.0, 6.0,
            3.0, 4.0, 0.0)
        var det = m1.determinant()
        assertEquals(1.0, det)
    }

fun invert() {
        var m1 = Matrix33(1.0, 0.0, 5.0,
            2.0, 1.0, 6.0,
            3.0, 4.0, 0.0)
        m1.invert()
        assertEquals(-24.0, m1.m00)
        assertEquals( 20.0, m1.m01)
        assertEquals( -5.0, m1.m02)
        assertEquals( 18.0, m1.m10)
        assertEquals(-15.0, m1.m11)
        assertEquals(  4.0, m1.m12)
        assertEquals(  5.0, m1.m20)
        assertEquals( -4.0, m1.m21)
        assertEquals(  1.0, m1.m22)
    }

fun getInverse() {
        var m1 = Matrix33(1.0, 0.0, 5.0,
            2.0, 1.0, 6.0,
            3.0, 4.0, 0.0)
        var m2 = m1.getInverse()
        assertEquals(-24.0, m2.m00)
        assertEquals( 20.0, m2.m01)
        assertEquals( -5.0, m2.m02)
        assertEquals( 18.0, m2.m10)
        assertEquals(-15.0, m2.m11)
        assertEquals(  4.0, m2.m12)
        assertEquals(  5.0, m2.m20)
        assertEquals( -4.0, m2.m21)
        assertEquals(  1.0, m2.m22)
        assertFalse(m1.equals(m2))
    }

fun solve22() {
        var A = Matrix33(3.0, -1.0, 0.0,
            -1.0, -1.0, 0.0,
            0.0,  0.0, 0.0)
        var b = Vector2(2.0, 6.0)
        var x = A.solve22(b)
        assertEquals(-1.0, x.x)
        assertEquals(-5.0, x.y)
    }

fun solve33() {
        var A = Matrix33(1.0, -3.0, 3.0,
            2.0, 3.0, -1.0,
            4.0, -3.0, -1.0)
        var b = Vector3(-4.0, 15.0, 19.0)
        var x = A.solve33(b)
        assertEquals( 5.0, x.x)
        assertEquals( 1.0, x.y)
        assertEquals(-2.0, x.z)
    }
}

private fun radians(value: Double) = value / 180.0 * PI
private fun degrees(value: Double) = value * 180.0 / PI
