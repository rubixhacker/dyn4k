package org.dyn4j.geometry

private const val FRACTION_MASK = (1L shl 52) - 1L
private const val LOW_WORD_MASK = 0xffffffffUL

private data class BinaryValue(val significand: ULong, val exponent: Int)

private fun binaryValue(value: Double): BinaryValue {
    val bits = value.toRawBits()
    val fraction = (bits and FRACTION_MASK).toULong()
    val exponentBits = ((bits ushr 52) and 0x7ffL).toInt()
    return if (exponentBits == 0) {
        BinaryValue(fraction, -1074)
    } else {
        BinaryValue((1UL shl 52) or fraction, exponentBits - 1075)
    }
}

private fun compareSquare(significand: ULong, exponent: Int, input: BinaryValue): Int {
    if (significand == 0UL) return -1
    val low = significand and LOW_WORD_MASK
    val high = significand shr 32
    val lowProduct = low * low
    val crossProduct = low * high
    val middle = (lowProduct shr 32) + ((crossProduct and LOW_WORD_MASK) shl 1)
    val productLow = (lowProduct and LOW_WORD_MASK) or ((middle and LOW_WORD_MASK) shl 32)
    val productHigh = high * high + ((crossProduct shr 32) shl 1) + (middle shr 32)

    val productTop = 2 * exponent + if (productHigh != 0UL) {
        127 - productHigh.countLeadingZeroBits()
    } else {
        63 - productLow.countLeadingZeroBits()
    }
    val inputTop = input.exponent + 63 - input.significand.countLeadingZeroBits()
    if (productTop != inputTop) return productTop.compareTo(inputTop)

    val shift = input.exponent - 2 * exponent
    if (shift >= 0) {
        val inputHigh = if (shift == 0) 0UL else if (shift < 64) {
            input.significand shr (64 - shift)
        } else {
            input.significand shl (shift - 64)
        }
        val inputLow = if (shift < 64) input.significand shl shift else 0UL
        return if (productHigh != inputHigh) productHigh.compareTo(inputHigh)
        else productLow.compareTo(inputLow)
    }
    val amount = -shift
    val shiftedHigh = if (amount < 64) {
        (productHigh shl amount) or (productLow shr (64 - amount))
    } else {
        productLow shl (amount - 64)
    }
    val shiftedLow = if (amount < 64) productLow shl amount else 0UL
    return if (shiftedHigh != 0UL) 1 else shiftedLow.compareTo(input.significand)
}

private fun compareSquare(value: Double, input: BinaryValue): Int {
    val binary = binaryValue(value)
    return compareSquare(binary.significand, binary.exponent, input)
}

private fun roundedBetween(lower: Double, upper: Double, input: BinaryValue): Double {
    val a = binaryValue(lower)
    val b = binaryValue(upper)
    val exponent = minOf(a.exponent, b.exponent)
    val midpointSignificand =
        (a.significand shl (a.exponent - exponent)) +
        (b.significand shl (b.exponent - exponent))
    val midpointCompare = compareSquare(midpointSignificand, exponent - 1, input)
    return when {
        midpointCompare > 0 -> lower
        midpointCompare < 0 -> upper
        (lower.toRawBits() and 1L) == 0L -> lower
        else -> upper
    }
}

private fun searchNearest(input: BinaryValue): Double {
    var lowerBits = 0L
    var upperBits = 0x7fefffffffffffffL
    while (upperBits - lowerBits > 1L) {
        val midpointBits = lowerBits + (upperBits - lowerBits) / 2L
        val comparison = compareSquare(Double.fromBits(midpointBits), input)
        if (comparison == 0) return Double.fromBits(midpointBits)
        if (comparison < 0) lowerBits = midpointBits else upperBits = midpointBits
    }
    return roundedBetween(Double.fromBits(lowerBits), Double.fromBits(upperBits), input)
}

internal fun nearestSqrtFromCandidate(value: Double, candidate: Double): Double {
    val input = binaryValue(value)
    if (!candidate.isFinite() || candidate <= 0.0) return searchNearest(input)
    val comparison = compareSquare(candidate, input)
    if (comparison == 0) return candidate

    var lower: Double
    var upper: Double
    var steps = 0
    if (comparison > 0) {
        upper = candidate
        lower = Double.fromBits(candidate.toRawBits() - 1L)
        while (compareSquare(lower, input) > 0) {
            if (++steps > 4) return searchNearest(input)
            upper = lower
            lower = Double.fromBits(lower.toRawBits() - 1L)
        }
    } else {
        lower = candidate
        upper = Double.fromBits(candidate.toRawBits() + 1L)
        while (compareSquare(upper, input) < 0) {
            if (++steps > 4) return searchNearest(input)
            lower = upper
            upper = Double.fromBits(upper.toRawBits() + 1L)
        }
    }
    return roundedBetween(lower, upper, input)
}

internal expect fun nearestSqrt(value: Double): Double
