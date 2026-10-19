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
package org.dyn4j.geometry

import org.dyn4j.JvmStaticBridge

import kotlin.math.abs
import org.dyn4j.Copyable
import org.dyn4j.Epsilon
import org.dyn4j.exception.ArgumentNullException

open class Matrix33 : Copyable<Matrix33> {
    @kotlin.jvm.JvmField var m00: Double = 0.0
    @kotlin.jvm.JvmField var m01: Double = 0.0
    @kotlin.jvm.JvmField var m02: Double = 0.0
    @kotlin.jvm.JvmField var m10: Double = 0.0
    @kotlin.jvm.JvmField var m11: Double = 0.0
    @kotlin.jvm.JvmField var m12: Double = 0.0
    @kotlin.jvm.JvmField var m20: Double = 0.0
    @kotlin.jvm.JvmField var m21: Double = 0.0
    @kotlin.jvm.JvmField var m22: Double = 0.0

    constructor()
    constructor(m00: Double, m01: Double, m02: Double, m10: Double, m11: Double, m12: Double, m20: Double, m21: Double, m22: Double) {
        this.m00 = m00
        this.m01 = m01
        this.m02 = m02
        this.m10 = m10
        this.m11 = m11
        this.m12 = m12
        this.m20 = m20
        this.m21 = m21
        this.m22 = m22
    }
    constructor(values: DoubleArray?) {
        if (values == null) throw ArgumentNullException("values")
        if (values.size != 9) throw IndexOutOfBoundsException("The values array must have exactly 9 elements")
        m00 = values[0]
        m01 = values[1]
        m02 = values[2]
        m10 = values[3]
        m11 = values[4]
        m12 = values[5]
        m20 = values[6]
        m21 = values[7]
        m22 = values[8]
    }
    constructor(matrix: Matrix33) {
        m00 = matrix.m00
        m01 = matrix.m01
        m02 = matrix.m02
        m10 = matrix.m10
        m11 = matrix.m11
        m12 = matrix.m12
        m20 = matrix.m20
        m21 = matrix.m21
        m22 = matrix.m22
    }
    override fun copy() = Matrix33(this)
    override fun hashCode(): Int {
        var result = 1
        for (value in doubleArrayOf(m00, m01, m02, m10, m11, m12, m20, m21, m22)) {
            val bits = value.toBits()
            result = 31 * result + (bits xor (bits ushr 32)).toInt()
        }
        return result
    }
    override fun equals(other: Any?): Boolean =
        other === this || (other is Matrix33 && m00 == other.m00 &&
            m01 == other.m01 &&
            m02 == other.m02 &&
            m10 == other.m10 &&
            m11 == other.m11 &&
            m12 == other.m12 &&
            m20 == other.m20 &&
            m21 == other.m21 &&
            m22 == other.m22)
    override fun toString() =
        "[" + m00 + " " + m01 + " " + m02 + "][" + m10 + " " + m11 + " " + m12 +
            "][" + m20 + " " + m21 + " " + m22 + "]"

    open fun add(matrix: Matrix33): Matrix33 {
        m00 += matrix.m00
        m01 += matrix.m01
        m02 += matrix.m02
        m10 += matrix.m10
        m11 += matrix.m11
        m12 += matrix.m12
        m20 += matrix.m20
        m21 += matrix.m21
        m22 += matrix.m22
        return this
    }
    open fun sum(matrix: Matrix33) = copy().add(matrix)
    open fun subtract(matrix: Matrix33): Matrix33 {
        m00 -= matrix.m00
        m01 -= matrix.m01
        m02 -= matrix.m02
        m10 -= matrix.m10
        m11 -= matrix.m11
        m12 -= matrix.m12
        m20 -= matrix.m20
        m21 -= matrix.m21
        m22 -= matrix.m22
        return this
    }
    open fun difference(matrix: Matrix33) = copy().subtract(matrix)
    open fun multiply(matrix: Matrix33): Matrix33 {
        val a00 = m00; val a01 = m01; val a02 = m02
        val a10 = m10; val a11 = m11; val a12 = m12
        val a20 = m20; val a21 = m21; val a22 = m22
        m00 = a00 * matrix.m00 + a01 * matrix.m10 + a02 * matrix.m20
        m01 = a00 * matrix.m01 + a01 * matrix.m11 + a02 * matrix.m21
        m02 = a00 * matrix.m02 + a01 * matrix.m12 + a02 * matrix.m22
        m10 = a10 * matrix.m00 + a11 * matrix.m10 + a12 * matrix.m20
        m11 = a10 * matrix.m01 + a11 * matrix.m11 + a12 * matrix.m21
        m12 = a10 * matrix.m02 + a11 * matrix.m12 + a12 * matrix.m22
        m20 = a20 * matrix.m00 + a21 * matrix.m10 + a22 * matrix.m20
        m21 = a20 * matrix.m01 + a21 * matrix.m11 + a22 * matrix.m21
        m22 = a20 * matrix.m02 + a21 * matrix.m12 + a22 * matrix.m22
        return this
    }
    open fun product(matrix: Matrix33) = copy().multiply(matrix)
    open fun multiply(vector: Vector3): Vector3 {
        val x = vector.x; val y = vector.y; val z = vector.z
        vector.x = m00 * x + m01 * y + m02 * z
        vector.y = m10 * x + m11 * y + m12 * z
        vector.z = m20 * x + m21 * y + m22 * z
        return vector
    }
    open fun product(vector: Vector3) = multiply(vector.copy())
    open fun multiplyT(vector: Vector3): Vector3 {
        val x = vector.x; val y = vector.y; val z = vector.z
        vector.x = m00 * x + m10 * y + m20 * z
        vector.y = m01 * x + m11 * y + m21 * z
        vector.z = m02 * x + m12 * y + m22 * z
        return vector
    }
    open fun productT(vector: Vector3) = multiplyT(vector.copy())
    open fun multiply(scalar: Double): Matrix33 {
        m00 *= scalar
        m01 *= scalar
        m02 *= scalar
        m10 *= scalar
        m11 *= scalar
        m12 *= scalar
        m20 *= scalar
        m21 *= scalar
        m22 *= scalar
        return this
    }
    open fun product(scalar: Double) = copy().multiply(scalar)
    open fun identity(): Matrix33 {
        m00 = 1.0
        m01 = 0.0
        m02 = 0.0
        m10 = 0.0
        m11 = 1.0
        m12 = 0.0
        m20 = 0.0
        m21 = 0.0
        m22 = 1.0
        return this
    }
    open fun transpose(): Matrix33 {
        var s = m01; m01 = m10; m10 = s
        s = m02; m02 = m20; m20 = s
        s = m12; m12 = m21; m21 = s
        return this
    }
    open fun getTranspose() = Matrix33(m00, m10, m20, m01, m11, m21, m02, m12, m22)
    open fun determinant() =
        m00 * m11 * m22 + m01 * m12 * m20 + m02 * m10 * m21 -
        m20 * m11 * m02 - m21 * m12 * m00 - m22 * m10 * m01

    open fun invert(): Matrix33 {
        var det = determinant()
        det = if (abs(det) > Epsilon.E) 1.0 / det else 0.0
        val n00 = det * (m11 * m22 - m12 * m21)
        val n01 = -det * (m01 * m22 - m21 * m02)
        val n02 = det * (m01 * m12 - m11 * m02)
        val n10 = -det * (m10 * m22 - m20 * m12)
        val n11 = det * (m00 * m22 - m20 * m02)
        val n12 = -det * (m00 * m12 - m10 * m02)
        val n20 = det * (m10 * m21 - m20 * m11)
        val n21 = -det * (m00 * m21 - m20 * m01)
        val n22 = det * (m00 * m11 - m10 * m01)
        m00 = n00; m01 = n01; m02 = n02
        m10 = n10; m11 = n11; m12 = n12
        m20 = n20; m21 = n21; m22 = n22
        return this
    }
    open fun getInverse() = copy().invert()
    open fun solve33(b: Vector3): Vector3 {
        var det = determinant()
        det = if (abs(det) > Epsilon.E) 1.0 / det else 0.0
        val c00 = m11 * m22 - m12 * m21
        val c01 = -m01 * m22 + m21 * m02
        val c02 = m01 * m12 - m11 * m02
        val c10 = -m10 * m22 + m20 * m12
        val c11 = m00 * m22 - m20 * m02
        val c12 = -m00 * m12 + m10 * m02
        val c20 = m10 * m21 - m20 * m11
        val c21 = -m00 * m21 + m20 * m01
        val c22 = m00 * m11 - m10 * m01
        return Vector3(
            det * (c00 * b.x + c01 * b.y + c02 * b.z),
            det * (c10 * b.x + c11 * b.y + c12 * b.z),
            det * (c20 * b.x + c21 * b.y + c22 * b.z)
        )
    }
    open fun solve22(b: Vector2): Vector2 {
        var det = m00 * m11 - m01 * m10
        det = if (abs(det) > Epsilon.E) 1.0 / det else 0.0
        return Vector2(det * (m11 * b.x - m01 * b.y), det * (m00 * b.y - m10 * b.x))
    }
}
