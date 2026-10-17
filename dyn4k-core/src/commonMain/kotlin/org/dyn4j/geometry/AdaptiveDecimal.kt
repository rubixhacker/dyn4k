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

import kotlin.math.abs
import org.dyn4j.Copyable
import org.dyn4j.exception.ValueOutOfRangeException
import org.dyn4j.exception.InvalidIndexException

open class AdaptiveDecimal private constructor(
    private val components: DoubleArray,
    private var size: Int
) : Copyable<AdaptiveDecimal> {
    constructor(length: Int) : this(DoubleArray(validLength(length)), 0)
    constructor(other: AdaptiveDecimal) : this(other.components.copyOf(), other.size)
    protected constructor(a0: Double, a1: Double) : this(doubleArrayOf(a0, a1), 2)

    open fun size(): Int = size
    open fun capacity(): Int = components.size
    override fun copy(): AdaptiveDecimal = AdaptiveDecimal(this)

    @Deprecated("Use set")
    open fun copyFrom(other: AdaptiveDecimal) = set(other)

    open fun set(other: AdaptiveDecimal) {
        other.components.copyInto(components, 0, 0, other.size)
        size = other.size
    }

    open fun get(index: Int): Double {
        if (index < 0 || index >= size) throw InvalidIndexException(index)
        return components[index]
    }

    open fun append(value: Double): AdaptiveDecimal {
        if (size >= capacity()) throw InvalidIndexException(size)
        components[size++] = value
        return this
    }

    open fun appendNonZero(value: Double): AdaptiveDecimal {
        if (value != 0.0) append(value)
        return this
    }

    open fun checkInvariants(): Boolean {
        if (size == 0) return true
        var last = components[0]
        for (i in 1 until size) {
            val current = components[i]
            if (current == 0.0) continue
            if (abs(current) < abs(last)) return false
            val previousBits = last.toBits() and 0x000fffffffffffffL or 0x0010000000000000L
            val currentBits = current.toBits() and 0x000fffffffffffffL or 0x0010000000000000L
            val previousExponent = ((last.toBits() ushr 52) and 0x7ff).toInt() - 1023
            val currentExponent = ((current.toBits() ushr 52) and 0x7ff).toInt() - 1023
            val previousTop = previousBits.countLeadingZeroBits() - previousExponent
            val currentBottom = 63 - currentBits.countTrailingZeroBits() - currentExponent
            if (currentBottom >= previousTop) return false
            last = current
        }
        return true
    }

    open fun ensureInvariants() {
        if (!checkInvariants()) throw IllegalStateException()
    }

    open fun clear(): AdaptiveDecimal { size = 0; return this }
    open fun removeZeros(): AdaptiveDecimal {
        val oldSize = size
        size = 0
        for (i in 0 until oldSize) appendNonZero(components[i])
        return this
    }
    open fun normalize(): AdaptiveDecimal { if (size == 0) append(0.0); return this }
    open fun negate(): AdaptiveDecimal { for (i in 0 until size) components[i] = -components[i]; return this }
    open fun getEstimation(): Double { var value = 0.0; for (i in 0 until size) value += components[i]; return value }

    open fun sum(other: AdaptiveDecimal): AdaptiveDecimal = sum(other, null)

    open fun sum(other: AdaptiveDecimal, output: AdaptiveDecimal?): AdaptiveDecimal {
        val result = output?.clear() ?: AdaptiveDecimal(size + other.size)
        var left = 0
        var right = 0
        var carry: Double
        if (abs(get(left)) <= abs(other.get(right))) {
            carry = get(left++)
        } else {
            carry = other.get(right++)
        }
        while (left < size || right < other.size) {
            val next = if (left < size && (right >= other.size || abs(get(left)) <= abs(other.get(right))))
                get(left++) else other.get(right++)
            val sum = carry + next
            result.appendNonZero(getErrorComponentFromSum(carry, next, sum))
            carry = sum
        }
        result.appendNonZero(carry)
        return result.normalize()
    }

    open fun sumEpilogue(carryValue: Double, other: AdaptiveDecimal, index: Int, result: AdaptiveDecimal): AdaptiveDecimal {
        var carry = carryValue
        for (i in index until other.size()) {
            val next = other.get(i)
            val sum = carry + next
            result.appendNonZero(getErrorComponentFromSum(carry, next, sum))
            carry = sum
        }
        result.appendNonZero(carry)
        return result.normalize()
    }

    override fun toString(): String = components.take(size).joinToString(", ", "[", "] ~= ${getEstimation()}")

    companion object {
        private fun validLength(length: Int): Int {
            if (length <= 0) throw ValueOutOfRangeException("length", length, ValueOutOfRangeException.MUST_BE_GREATER_THAN, 0)
            return length
        }
     fun valueOf(value: Double): AdaptiveDecimal = AdaptiveDecimal(1).append(value)
     fun fromSum(a: Double, b: Double): AdaptiveDecimal {
            val sum = a + b
            return AdaptiveDecimal(getErrorComponentFromSum(a, b, sum), sum)
        }
     fun fromDiff(a: Double, b: Double): AdaptiveDecimal {
            val diff = a - b
            return AdaptiveDecimal(getErrorComponentFromDifference(a, b, diff), diff)
        }
     fun fromProduct(a: Double, b: Double): AdaptiveDecimal {
            val product = a * b
            return AdaptiveDecimal(getErrorComponentFromProduct(a, b, product), product)
        }
     fun fromDiff(a0: Double, a1: Double, b0: Double, b1: Double, output: AdaptiveDecimal?): AdaptiveDecimal {
            val result = output?.clear() ?: AdaptiveDecimal(4)
            val imm = a0 - b0
            val x0 = getErrorComponentFromDifference(a0, b0, imm)
            val imm2 = a1 + imm
            val imm1 = getErrorComponentFromSum(a1, imm, imm2)
            val diff = imm1 - b1
            val x1 = getErrorComponentFromDifference(imm1, b1, diff)
            val x3 = imm2 + diff
            val x2 = getErrorComponentFromSum(imm2, diff, x3)
            return result.append(x0).append(x1).append(x2).append(x3)
        }
     fun getErrorComponentFromSum(a: Double, b: Double, sum: Double): Double {
            val bvirt = sum - a
            val avirt = sum - bvirt
            return (a - avirt) + (b - bvirt)
        }
     fun getErrorComponentFromDifference(a: Double, b: Double, diff: Double): Double {
            val bvirt = a - diff
            val avirt = diff + bvirt
            return (a - avirt) + (bvirt - b)
        }
     fun getErrorComponentFromProduct(a: Double, b: Double, product: Double): Double {
            val ac = RobustGeometry.SPLITTER * a
            val abig = ac - a
            val ahi = ac - abig
            val alo = a - ahi
            val bc = RobustGeometry.SPLITTER * b
            val bbig = bc - b
            val bhi = bc - bbig
            val blo = b - bhi
            val error1 = product - ahi * bhi
            val error2 = error1 - alo * bhi
            val error3 = error2 - ahi * blo
            return alo * blo - error3
        }
    }
}
