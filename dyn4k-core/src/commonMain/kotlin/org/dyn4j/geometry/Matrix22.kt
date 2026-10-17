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
import kotlin.math.max
import kotlin.math.sqrt
import org.dyn4j.Copyable
import org.dyn4j.Epsilon
import org.dyn4j.exception.ArgumentNullException

open class Matrix22 : Copyable<Matrix22> {
    @kotlin.jvm.JvmField var m00: Double = 0.0
    @kotlin.jvm.JvmField var m01: Double = 0.0
    @kotlin.jvm.JvmField var m10: Double = 0.0
    @kotlin.jvm.JvmField var m11: Double = 0.0

    constructor()
    constructor(m00: Double, m01: Double, m10: Double, m11: Double) {
        this.m00 = m00; this.m01 = m01; this.m10 = m10; this.m11 = m11
    }
    constructor(values: DoubleArray?) {
        if (values == null) throw ArgumentNullException("values")
        if (values.size != 4) throw IndexOutOfBoundsException("The values array must have exactly 4 elements")
        m00 = values[0]; m01 = values[1]; m10 = values[2]; m11 = values[3]
    }
    constructor(matrix: Matrix22) {
        m00 = matrix.m00; m01 = matrix.m01; m10 = matrix.m10; m11 = matrix.m11
    }
    override fun copy() = Matrix22(this)
    override fun hashCode(): Int {
        var result = 1
        for (value in doubleArrayOf(m00, m01, m10, m11)) {
            val bits = value.toBits()
            result = 31 * result + (bits xor (bits ushr 32)).toInt()
        }
        return result
    }
    override fun equals(other: Any?): Boolean =
        other === this || (other is Matrix22 && m00 == other.m00 && m01 == other.m01 &&
            m10 == other.m10 && m11 == other.m11)
    override fun toString() = "[" + m00 + " " + m01 + "][" + m10 + " " + m11 + "]"

    open fun add(matrix: Matrix22): Matrix22 {
        m00 += matrix.m00; m01 += matrix.m01; m10 += matrix.m10; m11 += matrix.m11
        return this
    }
    open fun sum(matrix: Matrix22) = copy().add(matrix)
    open fun subtract(matrix: Matrix22): Matrix22 {
        m00 -= matrix.m00; m01 -= matrix.m01; m10 -= matrix.m10; m11 -= matrix.m11
        return this
    }
    open fun difference(matrix: Matrix22) = copy().subtract(matrix)
    open fun multiply(matrix: Matrix22): Matrix22 {
        val a = m00; val b = m01; val c = m10; val d = m11
        m00 = a * matrix.m00 + b * matrix.m10
        m01 = a * matrix.m01 + b * matrix.m11
        m10 = c * matrix.m00 + d * matrix.m10
        m11 = c * matrix.m01 + d * matrix.m11
        return this
    }
    open fun product(matrix: Matrix22) = copy().multiply(matrix)
    open fun multiply(vector: Vector2): Vector2 {
        val x = vector.x; val y = vector.y
        vector.x = m00 * x + m01 * y
        vector.y = m10 * x + m11 * y
        return vector
    }
    open fun product(vector: Vector2) = multiply(vector.copy())
    open fun multiplyT(vector: Vector2): Vector2 {
        val x = vector.x; val y = vector.y
        vector.x = m00 * x + m10 * y
        vector.y = m01 * x + m11 * y
        return vector
    }
    open fun productT(vector: Vector2) = multiplyT(vector.copy())
    open fun multiply(scalar: Double): Matrix22 {
        m00 *= scalar; m01 *= scalar; m10 *= scalar; m11 *= scalar
        return this
    }
    open fun product(scalar: Double) = copy().multiply(scalar)
    open fun identity(): Matrix22 {
        m00 = 1.0; m01 = 0.0; m10 = 0.0; m11 = 1.0
        return this
    }
    open fun transpose(): Matrix22 {
        val m = m01; m01 = m10; m10 = m
        return this
    }
    open fun getTranspose() = copy().transpose()
    open fun determinant() = m00 * m11 - m01 * m10
    open fun invert(): Matrix22 {
        var det = determinant()
        det = if (abs(det) > Epsilon.E) 1.0 / det else 0.0
        val a = m00; val b = m01; val c = m10; val d = m11
        m00 = det * d; m01 = -det * b; m10 = -det * c; m11 = det * a
        return this
    }
    open fun invert(dest: Matrix22) {
        var det = determinant()
        det = if (abs(det) > Epsilon.E) 1.0 / det else 0.0
        dest.m00 = det * m11; dest.m01 = -det * m01
        dest.m10 = -det * m10; dest.m11 = det * m00
    }
    open fun getInverse() = copy().invert()
    open fun solve(b: Vector2): Vector2 {
        var det = determinant()
        det = if (abs(det) > Epsilon.E) 1.0 / det else 0.0
        return Vector2(det * (m11 * b.x - m01 * b.y), det * (m00 * b.y - m10 * b.x))
    }
    open fun normMax() = max(abs(m00), max(abs(m01), max(abs(m10), abs(m11))))
    open fun normInfinity() = max(abs(m00) + abs(m01), abs(m10) + abs(m11))
    open fun norm1() = max(abs(m00) + abs(m10), abs(m01) + abs(m11))
    open fun normFrobenius() = sqrt(m00 * m00 + m10 * m10 + m01 * m01 + m11 * m11)
}
