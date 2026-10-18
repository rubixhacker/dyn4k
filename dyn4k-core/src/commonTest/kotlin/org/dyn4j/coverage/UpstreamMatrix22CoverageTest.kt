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
package org.dyn4j.coverage

import org.dyn4j.Epsilon
import org.dyn4j.geometry.*
import kotlin.math.*
import kotlin.test.*

class UpstreamMatrix22CoverageTest {
    @Test
    fun createNullArray() {
        assertFailsWith<NullPointerException> {
            Matrix22(null)
        }
    }

    @Test
    fun createLessThanFourElements() {
        assertFailsWith<IndexOutOfBoundsException> {
            Matrix22(doubleArrayOf( 0.0, 1.0, 5.0 ))
        }
    }

    @Test
    fun createMoreThanFourElements() {
        assertFailsWith<IndexOutOfBoundsException> {
            Matrix22(doubleArrayOf( 0.0, 1.0, 5.0, 4.0, 2.0 ))
        }
    }

    @Test
    fun createFull() {
        var m = Matrix22(1.0, 2.0,
            -3.0, 8.0)
        assertEquals(1.0, m.m00)
        assertEquals(2.0, m.m01)
        assertEquals(-3.0, m.m10)
        assertEquals(8.0, m.m11)
        assertNotNull(m.toString())
    }

    @Test
    fun createFullArray() {
        var m = Matrix22(doubleArrayOf(1.0, 2.0,
            -3.0, 8.0))
        assertEquals(1.0, m.m00)
        assertEquals(2.0, m.m01)
        assertEquals(-3.0, m.m10)
        assertEquals(8.0, m.m11)
    }

    @Test
    fun copy() {
        var m1 = Matrix22()
        m1.m00 = 0.0
        m1.m01 = 2.0
        m1.m10 = 1.0
        m1.m11 = 3.0
        var m2 = Matrix22(m1)
        assertEquals(m1.m00, m2.m00)
        assertEquals(m1.m01, m2.m01)
        assertEquals(m1.m10, m2.m10)
        assertEquals(m1.m11, m2.m11)
    }

    @Test
    fun add() {
        var m1 = Matrix22(0.0, 2.0,
            3.5, 1.2)
        var m2 = Matrix22(1.3, 0.3,
            0.0, 4.5)
        m1.add(m2)
        assertEquals(1.3, m1.m00)
        assertEquals(2.3, m1.m01)
        assertEquals(3.5, m1.m10)
        assertEquals(5.7, m1.m11)
    }

    @Test
    fun sum() {
        var m1 = Matrix22(0.0, 2.0,
            3.5, 1.2)
        var m2 = Matrix22(1.3, 0.3,
            0.0, 4.5)
        var m3 = m1.sum(m2)
        assertEquals(1.3, m3.m00)
        assertEquals(2.3, m3.m01)
        assertEquals(3.5, m3.m10)
        assertEquals(5.7, m3.m11)
        assertFalse(m1.equals(m3))
    }

    @Test
    fun subtract() {
        var m1 = Matrix22(0.0, 2.0,
            3.5, 1.2)
        var m2 = Matrix22(1.3, 0.3,
            0.0, 4.5)
        m1.subtract(m2)
        assertEquals(-1.3, m1.m00)
        assertEquals(1.7, m1.m01)
        assertEquals(3.5, m1.m10)
        assertEquals(-3.3, m1.m11)
    }

    @Test
    fun difference() {
        var m1 = Matrix22(0.0, 2.0,
            3.5, 1.2)
        var m2 = Matrix22(1.3, 0.3,
            0.0, 4.5)
        var m3 = m1.difference(m2)
        assertEquals(-1.3, m3.m00)
        assertEquals(1.7, m3.m01)
        assertEquals(3.5, m3.m10)
        assertEquals(-3.3, m3.m11)
        assertFalse(m1.equals(m3))
    }

    @Test
    fun multiplyMatrix() {
        var m1 = Matrix22(1.0, 2.0,
            3.0, 4.0)
        var m2 = Matrix22(4.0, 3.0,
            2.0, 1.0)
        m1.multiply(m2)
        assertEquals(8.0, m1.m00)
        assertEquals(5.0, m1.m01)
        assertEquals(20.0, m1.m10)
        assertEquals(13.0, m1.m11)
    }

    @Test
    fun productMatrix() {
        var m1 = Matrix22(1.0, 2.0,
            3.0, 4.0)
        var m2 = Matrix22(4.0, 3.0,
            2.0, 1.0)
        var m3 = m1.product(m2)
        assertEquals(8.0, m3.m00)
        assertEquals(5.0, m3.m01)
        assertEquals(20.0, m3.m10)
        assertEquals(13.0, m3.m11)
        assertFalse(m1.equals(m3))
    }

    @Test
    fun multiplyVector() {
        var m1 = Matrix22(1.0, 2.0,
            3.0, 4.0)
        var v1 = Vector2(1.0, -1.0)
        m1.multiply(v1)
        assertEquals(-1.0, v1.x)
        assertEquals(-1.0, v1.y)
    }

    @Test
    fun productVector() {
        var m1 = Matrix22(1.0, 2.0,
            3.0, 4.0)
        var v1 = Vector2(1.0, -1.0)
        var v2 = m1.product(v1)
        assertEquals(-1.0, v2.x)
        assertEquals(-1.0, v2.y)
        assertFalse(v1.equals(v2))
    }

    @Test
    fun multiplyVectorT() {
        var m1 = Matrix22(1.0, 2.0,
            3.0, 4.0)
        var v1 = Vector2(1.0, -1.0)
        m1.multiplyT(v1)
        assertEquals(-2.0, v1.x)
        assertEquals(-2.0, v1.y)
    }

    @Test
    fun productVectorT() {
        var m1 = Matrix22(1.0, 2.0,
            3.0, 4.0)
        var v1 = Vector2(1.0, -1.0)
        var v2 = m1.productT(v1)
        assertEquals(-2.0, v2.x)
        assertEquals(-2.0, v2.y)
        assertFalse(v1.equals(v2))
    }

    @Test
    fun multiplyScalar() {
        var m1 = Matrix22(1.0, 2.0,
            3.0, 4.0)
        m1.multiply(2.0)
        assertEquals(2.0, m1.m00)
        assertEquals(4.0, m1.m01)
        assertEquals(6.0, m1.m10)
        assertEquals(8.0, m1.m11)
    }

    @Test
    fun productScalar() {
        var m1 = Matrix22(1.0, 2.0,
            3.0, 4.0)
        var m2 = m1.product(2.0)
        assertEquals(2.0, m2.m00)
        assertEquals(4.0, m2.m01)
        assertEquals(6.0, m2.m10)
        assertEquals(8.0, m2.m11)
        assertFalse(m1.equals(m2))
    }

    @Test
    fun identity() {
        var m1 = Matrix22(1.0, 2.0,
            3.0, 4.0)
        m1.identity()
        assertEquals(1.0, m1.m00)
        assertEquals(0.0, m1.m01)
        assertEquals(0.0, m1.m10)
        assertEquals(1.0, m1.m11)
    }

    @Test
    fun transpose() {
        var m1 = Matrix22(1.0, 2.0,
            3.0, 4.0)
        m1.transpose()
        assertEquals(1.0, m1.m00)
        assertEquals(3.0, m1.m01)
        assertEquals(2.0, m1.m10)
        assertEquals(4.0, m1.m11)
    }

    @Test
    fun getTranspose() {
        var m1 = Matrix22(1.0, 2.0,
            3.0, 4.0)
        var m2 = m1.getTranspose()
        assertEquals(1.0, m2.m00)
        assertEquals(3.0, m2.m01)
        assertEquals(2.0, m2.m10)
        assertEquals(4.0, m2.m11)
        assertFalse(m1.equals(m2))
    }

    @Test
    fun determinant() {
        var m1 = Matrix22(1.0, 2.0,
            3.0, 4.0)
        var det = m1.determinant()
        assertEquals(-2.0, det)
    }

    @Test
    fun invert() {
        var m1 = Matrix22(1.0, 2.0,
            3.0, 4.0)
        m1.invert()
        assertEquals(-2.0, m1.m00)
        assertEquals(1.0, m1.m01)
        assertEquals(1.5, m1.m10)
        assertEquals(-0.5, m1.m11)
        var m2 = Matrix22()
        m1.invert(m2)
        assertEquals(1.0, m2.m00)
        assertEquals(2.0, m2.m01)
        assertEquals(3.0, m2.m10)
        assertEquals(4.0, m2.m11)
        assertEquals(-2.0, m1.m00)
        assertEquals(1.0, m1.m01)
        assertEquals(1.5, m1.m10)
        assertEquals(-0.5, m1.m11)
    }

    @Test
    fun getInverse() {
        var m1 = Matrix22(1.0, 2.0,
            3.0, 4.0)
        var m2 = m1.getInverse()
        assertEquals(-2.0, m2.m00)
        assertEquals(1.0, m2.m01)
        assertEquals(1.5, m2.m10)
        assertEquals(-0.5, m2.m11)
        assertFalse(m1.equals(m2))
    }

    @Test
    fun solve() {
        var A = Matrix22(3.0, -1.0,
            -1.0, -1.0)
        var b = Vector2(2.0, 6.0)
        var x = A.solve(b)
        assertEquals(-1.0, x.x)
        assertEquals(-5.0, x.y)
    }

    @Test
    fun norm() {
        var A = Matrix22(3.0, -1.0,
            -1.0, -1.0)
        var n1 = A.norm1()
        assertEquals(4.0, n1)
        var nf = A.normFrobenius()
        assertEquals(3.464, nf, 1e-3)
        var ni = A.normInfinity()
        assertEquals(4.0, ni)
        var nm = A.normMax()
        assertEquals(3.0, nm)
    }

    @Test
    fun equals() {
        var A = Matrix22(3.0, -1.0, -1.0, -1.0)
        var B = Matrix22(3.0, -1.0, -1.0, -1.0)
        var C = Matrix22(4.0, 2.0, 5.0, 0.0)
        assertEquals(A, B)
        assertEquals(A.hashCode(), B.hashCode())
        assertEquals(A, A)
        assertEquals(A.hashCode(), A.hashCode())
        assertFalse(A.equals(null))
        assertFalse(A.equals((null as Any?)))
        assertFalse(A.equals(C))
        assertFalse(A.hashCode() == C.hashCode())
        assertFalse(A.equals((C as Any)))
        assertTrue(A.equals((B as Any)))
    }
}

private fun radians(value: Double) = value / 180.0 * PI
private fun degrees(value: Double) = value * 180.0 / PI
