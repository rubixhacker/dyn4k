package io.github.rubixhacker.harness.numerical

/**
 * Arbitrary-precision non-negative integers in base 10^5.
 *
 * The orthogonality bound is a closed-form error bound over exact rationals of about 300
 * decimal digits; the Python reference computes it with `fractions.Fraction` and `math.isqrt`.
 * Base 10^5 makes the fixed-point rescaling in that recurrence (`// 10^200`) a limb shift while
 * keeping every partial product inside a `Long`. Only the division and square root need the
 * general algorithm.
 */
internal class BigNat private constructor(source: IntArray) : Comparable<BigNat> {
    private val limbs: IntArray = normalize(source)

    val size: Int get() = limbs.size

    fun isZero(): Boolean = limbs.isEmpty()

    override fun compareTo(other: BigNat): Int {
        if (limbs.size != other.limbs.size) return limbs.size.compareTo(other.limbs.size)
        for (index in limbs.indices.reversed()) {
            if (limbs[index] != other.limbs[index]) return limbs[index].compareTo(other.limbs[index])
        }
        return 0
    }

    fun plus(other: BigNat): BigNat {
        val length = maxOf(limbs.size, other.limbs.size) + 1
        val result = IntArray(length)
        var carry = 0
        for (index in 0 until length) {
            var sum = carry
            if (index < limbs.size) sum += limbs[index]
            if (index < other.limbs.size) sum += other.limbs[index]
            if (sum >= BASE) {
                result[index] = sum - BASE
                carry = 1
            } else {
                result[index] = sum
                carry = 0
            }
        }
        return BigNat(result)
    }

    /** Requires `this >= other`, as every subtraction in the Python reference already holds. */
    fun minus(other: BigNat): BigNat {
        require(this >= other) { "BigNat underflow" }
        val result = IntArray(limbs.size)
        var borrow = 0
        for (index in limbs.indices) {
            var difference = limbs[index] - borrow
            if (index < other.limbs.size) difference -= other.limbs[index]
            if (difference < 0) {
                result[index] = difference + BASE
                borrow = 1
            } else {
                result[index] = difference
                borrow = 0
            }
        }
        return BigNat(result)
    }

    fun times(other: BigNat): BigNat {
        if (isZero() || other.isZero()) return ZERO
        val accumulator = LongArray(limbs.size + other.limbs.size + 1)
        for (index in limbs.indices) {
            var carry = 0L
            val left = limbs[index].toLong()
            for (otherIndex in other.limbs.indices) {
                val sum = accumulator[index + otherIndex] + left * other.limbs[otherIndex] + carry
                accumulator[index + otherIndex] = sum % BASE
                carry = sum / BASE
            }
            var position = index + other.limbs.size
            while (carry > 0L) {
                val sum = accumulator[position] + carry
                accumulator[position] = sum % BASE
                carry = sum / BASE
                position += 1
            }
        }
        return BigNat(IntArray(accumulator.size) { accumulator[it].toInt() })
    }

    fun timesSmall(factor: Long): BigNat {
        if (factor == 0L || isZero()) return ZERO
        val result = IntArray(limbs.size + 2)
        var carry = 0L
        for (index in limbs.indices) {
            val product = limbs[index] * factor + carry
            result[index] = (product % BASE).toInt()
            carry = product / BASE
        }
        var position = limbs.size
        while (carry > 0L) {
            result[position] = (carry % BASE).toInt()
            carry /= BASE
            position += 1
        }
        return BigNat(result)
    }

    fun divSmall(divisor: Long): Pair<BigNat, Long> {
        val quotient = IntArray(limbs.size)
        var remainder = 0L
        for (index in limbs.indices.reversed()) {
            val current = remainder * BASE + limbs[index]
            quotient[index] = (current / divisor).toInt()
            remainder = current % divisor
        }
        return BigNat(quotient) to remainder
    }

    /** The greatest common divisor, as `math.gcd`. */
    fun gcd(other: BigNat): BigNat {
        var left = this
        var right = other
        while (!right.isZero()) {
            val remainder = left.divMod(right).second
            left = right
            right = remainder
        }
        return left
    }

    /** `math.isqrt`. */
    fun isqrt(): BigNat {
        if (isZero()) return ZERO
        if (this < THREE) return ONE
        var estimate = powerOfTen(limbs.size * 5 / 2 + 2)
        while (true) {
            val next = estimate.plus(divMod(estimate).first).divSmall(2).first
            if (next >= estimate) return estimate
            estimate = next
        }
    }

    /** Floor division by 10^[exponent], which is a limb shift in this base. */
    fun divByPowerOfTen(exponent: Int): BigNat {
        require(exponent >= 0)
        val shift = exponent / 5
        if (shift >= limbs.size) return ZERO
        var value = BigNat(limbs.copyOfRange(shift, limbs.size))
        val tail = exponent % 5
        if (tail > 0) value = value.divSmall(pow10(tail).toLong()).first
        return value
    }

    /** Floor division, as Python's `//` on non-negative integers. */
    fun divMod(divisor: BigNat): Pair<BigNat, BigNat> {
        require(!divisor.isZero()) { "division by zero" }
        if (this < divisor) return ZERO to this
        val top = limbs.size - 1
        val quotient = IntArray(limbs.size)
        var remainder = ZERO
        for (index in top downTo 0) {
            remainder = remainder.timesSmall(BASE.toLong()).plus(BigNat.ofLong(limbs[index].toLong()))
            var low = 0
            var high = BASE - 1
            while (low < high) {
                val middle = (low + high + 1) / 2
                if (divisor.timesSmall(middle.toLong()) <= remainder) low = middle else high = middle - 1
            }
            quotient[index] = low
            remainder = remainder.minus(divisor.timesSmall(low.toLong()))
        }
        return BigNat(quotient) to remainder
    }

    override fun equals(other: Any?): Boolean = other is BigNat && compareTo(other) == 0

    override fun hashCode(): Int = limbs.contentHashCode()

    override fun toString(): String {
        if (isZero()) return "0"
        val text = StringBuilder(limbs.last().toString())
        for (index in limbs.size - 2 downTo 0) {
            text.append(limbs[index].toString().padStart(5, '0'))
        }
        return text.toString()
    }

    companion object {
        private const val BASE = 100000

        private fun normalize(source: IntArray): IntArray {
            var length = source.size
            while (length > 0 && source[length - 1] == 0) length -= 1
            return if (length == source.size) source else source.copyOf(length)
        }

        val ZERO: BigNat = BigNat(IntArray(0))
        val ONE: BigNat = BigNat(intArrayOf(1))
        private val THREE: BigNat = BigNat(intArrayOf(3))

        fun ofLong(value: Long): BigNat {
            require(value >= 0) { "negative BigNat" }
            if (value == 0L) return ZERO
            var remaining = value
            val digits = ArrayList<Int>(4)
            while (remaining > 0) {
                digits.add((remaining % BASE).toInt())
                remaining /= BASE
            }
            return BigNat(digits.toIntArray())
        }

        fun ofInt(value: Int): BigNat = ofLong(value.toLong())

        /** 10^[exponent] for a non-negative exponent. */
        fun powerOfTen(exponent: Int): BigNat {
            require(exponent >= 0)
            val shift = exponent / 5
            val tail = exponent % 5
            var value = ONE
            repeat(shift) { value = value.timesSmall(BASE.toLong()) }
            if (tail > 0) value = value.timesSmall(pow10(tail).toLong())
            return value
        }

        /** 2^[exponent] for a non-negative exponent. */
        fun powerOfTwo(exponent: Int): BigNat = ONE.shiftLeft(exponent)

        internal fun pow10(exponent: Int): Int {
            var value = 1
            repeat(exponent) { value *= 10 }
            return value
        }
    }

    fun shiftLeft(bits: Int): BigNat {
        if (isZero()) return ZERO
        var value = this
        repeat(bits) { value = value.timesSmall(2L) }
        return value
    }
}

/** A signed arbitrary-precision integer. */
internal class BigInt constructor(val negative: Boolean, val magnitude: BigNat) :
    Comparable<BigInt> {
    fun isZero(): Boolean = magnitude.isZero()

    fun abs(): BigInt = BigInt(false, magnitude)

    operator fun plus(other: BigInt): BigInt = when {
        negative == other.negative -> BigInt(negative, magnitude.plus(other.magnitude))
        magnitude >= other.magnitude -> BigInt(negative, magnitude.minus(other.magnitude))
        else -> BigInt(other.negative, other.magnitude.minus(magnitude))
    }

    operator fun minus(other: BigInt): BigInt = plus(other.negated())

    operator fun times(other: BigInt): BigInt =
        BigInt(negative != other.negative, magnitude.times(other.magnitude))

    fun negated(): BigInt = if (isZero()) this else BigInt(!negative, magnitude)

    override fun compareTo(other: BigInt): Int = when {
        negative != other.negative -> if (negative) -1 else 1
        negative -> other.magnitude.compareTo(magnitude)
        else -> magnitude.compareTo(other.magnitude)
    }

    override fun equals(other: Any?): Boolean =
        other is BigInt && negative == other.negative && magnitude == other.magnitude

    override fun hashCode(): Int = 31 * negative.hashCode() + magnitude.hashCode()

    override fun toString(): String = (if (negative) "-" else "") + magnitude

    companion object {
        val ZERO = BigInt(false, BigNat.ZERO)
        fun of(value: Long): BigInt =
            if (value < 0) BigInt(true, BigNat.ofLong(-value)) else BigInt(false, BigNat.ofLong(value))

        fun ofMagnitude(value: BigNat): BigInt = BigInt(false, value)
    }
}

/** An exact rational with a positive denominator, as `fractions.Fraction`. */
internal class Fraction(val numerator: BigInt, val denominator: BigNat) : Comparable<Fraction> {
    init {
        require(!denominator.isZero()) { "zero denominator" }
    }

    operator fun plus(other: Fraction): Fraction = Fraction(
        numerator * BigInt.ofMagnitude(other.denominator) +
            other.numerator * BigInt.ofMagnitude(denominator),
        denominator.times(other.denominator),
    )

    operator fun minus(other: Fraction): Fraction = plus(other.negated())

    operator fun times(other: Fraction): Fraction =
        Fraction(numerator * other.numerator, denominator.times(other.denominator))

    operator fun div(other: Fraction): Fraction = Fraction(
        numerator * BigInt.ofMagnitude(other.denominator),
        denominator.times(other.numerator.magnitude),
    )

    fun negated(): Fraction = Fraction(numerator.negated(), denominator)

    fun abs(): Fraction = Fraction(numerator.abs(), denominator)

    /** `math.floor` of the rational, which is `numerator // denominator` in Python. */
    fun floor(): BigInt {
        val quotient = numerator.magnitude.divMod(denominator)
        val magnitude = quotient.first
        if (!numerator.negative) return BigInt.ofMagnitude(magnitude)
        val exact = quotient.second.isZero()
        return if (exact) {
            BigInt(true, magnitude)
        } else {
            BigInt(true, magnitude.plus(BigNat.ONE))
        }
    }

    /** `-(-numerator // denominator)`. */
    fun ceil(): BigInt = negated().floor().negated()

    override fun compareTo(other: Fraction): Int =
        (numerator * BigInt.ofMagnitude(other.denominator)).compareTo(
            other.numerator * BigInt.ofMagnitude(denominator),
        )

    override fun equals(other: Any?): Boolean = other is Fraction && compareTo(other) == 0

    override fun hashCode(): Int = 31 * numerator.hashCode() + denominator.hashCode()

    /**
     * Python's `Fraction` is always in lowest terms, and `str()` of it appears in the physical
     * diagnostic, so the rendering reduces by the greatest common divisor first.
     */
    override fun toString(): String {
        if (denominator == BigNat.ONE) return numerator.toString()
        val divisor = numerator.magnitude.gcd(denominator)
        if (divisor == BigNat.ONE) return "$numerator/$denominator"
        val reducedNumerator = numerator.magnitude.divMod(divisor).first
        val reducedDenominator = denominator.divMod(divisor).first
        val sign = if (numerator.negative) "-" else ""
        return "$sign$reducedNumerator/$reducedDenominator"
    }

    companion object {
        fun of(value: Long): Fraction = Fraction(BigInt.of(value), BigNat.ONE)

        /** `Fraction.from_float`: the exact rational value of the double. */
        fun ofDouble(value: Double): Fraction {
            if (value == 0.0) return Fraction(BigInt.ZERO, BigNat.ONE)
            val bits = value.toRawBits()
            val negative = bits < 0
            val exponent = ((bits ushr 52) and 0x7FF).toInt()
            val mantissa = bits and 0x000FFFFFFFFFFFFFL
            val significand: BigNat
            val shift: Int
            if (exponent == 0) {
                significand = BigNat.ofLong(mantissa)
                shift = -1074
            } else {
                significand = BigNat.ofLong(mantissa or 0x0010000000000000L)
                shift = exponent - 1075
            }
            val numerator = if (negative) BigInt(true, significand) else BigInt(false, significand)
            return if (shift >= 0) {
                Fraction(
                    numerator * BigInt.ofMagnitude(BigNat.powerOfTwo(shift)),
                    BigNat.ONE,
                )
            } else {
                Fraction(numerator, BigNat.powerOfTwo(-shift))
            }
        }

        fun ofRatio(numerator: BigNat, denominator: BigNat): Fraction =
            Fraction(BigInt.ofMagnitude(numerator), denominator)

        /** `Fraction("...")` for a plain decimal literal, as used for the phase ceilings. */
        fun ofDecimalString(text: String): Fraction {
            val trimmed = text.trim()
            val negative = trimmed.startsWith("-")
            var body = trimmed.removePrefix("-").removePrefix("+")
            var exponent = 0
            val marker = body.indexOfFirst { it == 'e' || it == 'E' }
            if (marker >= 0) {
                exponent = body.substring(marker + 1).toInt()
                body = body.substring(0, marker)
            }
            val point = body.indexOf('.')
            val digits: String
            val scale: Int
            if (point >= 0) {
                digits = body.substring(0, point) + body.substring(point + 1)
                scale = body.length - point - 1
            } else {
                digits = body
                scale = 0
            }
            var numerator = javaFreeParse(digits)
            var denominator = BigNat.powerOfTen(scale)
            val shift = exponent - scale
            if (shift >= 0) {
                numerator = numerator.times(BigNat.powerOfTen(shift))
            } else {
                denominator = BigNat.powerOfTen(-shift)
            }
            val signed = if (negative) BigInt(true, numerator) else BigInt(false, numerator)
            return Fraction(signed, denominator)
        }

        private fun javaFreeParse(digits: String): BigNat {
            var value = BigNat.ZERO
            for (character in digits) {
                if (character < '0' || character > '9') {
                    throw IllegalArgumentException("invalid decimal literal")
                }
                value = value.timesSmall(10L).plus(BigNat.ofInt(character - '0'))
            }
            return value
        }
    }
}
