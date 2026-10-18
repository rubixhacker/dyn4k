package org.dyn4j.geometry

import org.dyn4j.geometry.Vector2

internal class ExactDyadic private constructor(
    private val sign: Int,
    private val limbs: IntArray,
    private val exponent: Int
) {
    fun signum(): Int = sign

    operator fun minus(other: ExactDyadic): ExactDyadic = this + ExactDyadic(-other.sign, other.limbs, other.exponent)

    operator fun plus(other: ExactDyadic): ExactDyadic {
        if (sign == 0) return other
        if (other.sign == 0) return this
        val commonExponent = minOf(exponent, other.exponent)
        val left = shift(limbs, exponent - commonExponent)
        val right = shift(other.limbs, other.exponent - commonExponent)
        if (sign == other.sign) return of(sign, add(left, right), commonExponent)
        val order = compare(left, right)
        if (order == 0) return ZERO
        return if (order > 0) of(sign, subtract(left, right), commonExponent)
        else of(other.sign, subtract(right, left), commonExponent)
    }

    operator fun times(other: ExactDyadic): ExactDyadic {
        if (sign == 0 || other.sign == 0) return ZERO
        val output = IntArray(limbs.size + other.limbs.size)
        for (i in limbs.indices) {
            var carry = 0L
            for (j in other.limbs.indices) {
                val index = i + j
                val total = output[index].toLong() + limbs[i].toLong() * other.limbs[j] + carry
                output[index] = (total and 0xffffL).toInt()
                carry = total ushr 16
            }
            output[i + other.limbs.size] = carry.toInt()
        }
        return of(sign * other.sign, output, exponent + other.exponent)
    }

    companion object {
        private val ZERO = ExactDyadic(0, intArrayOf(), 0)

        fun from(value: Double): ExactDyadic {
            val bits = value.toBits()
            val biased = ((bits ushr 52) and 0x7ffL).toInt()
            require(biased != 0x7ff)
            val fraction = bits and ((1L shl 52) - 1L)
            val mantissa = if (biased == 0) fraction else fraction or (1L shl 52)
            if (mantissa == 0L) return ZERO
            val words = IntArray(4) { ((mantissa ushr (it * 16)) and 0xffffL).toInt() }
            val exponent = if (biased == 0) -1074 else biased - 1075
            return of(if (bits < 0L) -1 else 1, words, exponent)
        }

        private fun of(sign: Int, words: IntArray, exponent: Int): ExactDyadic {
            var length = words.size
            while (length > 0 && words[length - 1] == 0) length--
            return if (length == 0) ZERO else ExactDyadic(sign, words.copyOf(length), exponent)
        }

        private fun shift(words: IntArray, bits: Int): IntArray {
            val whole = bits / 16
            val rest = bits % 16
            val output = IntArray(words.size + whole + 1)
            var carry = 0
            for (i in words.indices) {
                val value = (words[i] shl rest) or carry
                output[i + whole] = value and 0xffff
                carry = value ushr 16
            }
            output[words.size + whole] = carry
            return output
        }

        private fun compare(left: IntArray, right: IntArray): Int {
            val size = maxOf(left.size, right.size)
            for (i in size - 1 downTo 0) {
                val a = left.getOrElse(i) { 0 }
                val b = right.getOrElse(i) { 0 }
                if (a != b) return a.compareTo(b)
            }
            return 0
        }

        private fun add(left: IntArray, right: IntArray): IntArray {
            val output = IntArray(maxOf(left.size, right.size) + 1)
            var carry = 0
            for (i in 0 until output.size - 1) {
                val total = left.getOrElse(i) { 0 } + right.getOrElse(i) { 0 } + carry
                output[i] = total and 0xffff
                carry = total ushr 16
            }
            output[output.lastIndex] = carry
            return output
        }

        private fun subtract(left: IntArray, right: IntArray): IntArray {
            val output = IntArray(left.size)
            var borrow = 0
            for (i in left.indices) {
                val difference = left[i] - right.getOrElse(i) { 0 } - borrow
                output[i] = difference and 0xffff
                borrow = if (difference < 0) 1 else 0
            }
            return output
        }
    }
}

internal fun exactLocationSign(point: Vector2, linePoint1: Vector2, linePoint2: Vector2): Int {
    val pax = ExactDyadic.from(point.x)
    val pay = ExactDyadic.from(point.y)
    val pbx = ExactDyadic.from(linePoint1.x)
    val pby = ExactDyadic.from(linePoint1.y)
    val pcx = ExactDyadic.from(linePoint2.x)
    val pcy = ExactDyadic.from(linePoint2.y)
    return ((pcx - pbx) * (pay - pby) - (pax - pbx) * (pcy - pby)).signum()
}
