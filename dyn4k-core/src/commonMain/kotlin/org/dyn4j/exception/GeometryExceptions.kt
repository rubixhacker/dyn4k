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
package org.dyn4j.exception

import kotlin.math.abs

open class EmptyCollectionException(argumentName: String) : IllegalArgumentException("$argumentName cannot be empty") {
    private companion object {
        private const val serialVersionUID = 3188055341987092721L
    }
}

open class NullElementException : NullPointerException {
    constructor(argumentName: String, index: Int) : super("$argumentName contains a null element at index $index")
    constructor(argumentName: String) : super("$argumentName contains a null element")

    private companion object {
        private const val serialVersionUID = 4560521220204618552L
    }
}

open class InvalidIndexException(index: Int) : IndexOutOfBoundsException("The index $index is out of bounds") {
    private companion object {
        private const val serialVersionUID = 1297019115982655104L
    }
}

internal expect fun fixedSix(value: Double): String
internal expect fun formatInt(value: Int): String

internal fun portableFixedSix(value: Double): String {
    if (value.isNaN()) return "NaN"
    if (value == Double.POSITIVE_INFINITY) return "Infinity"
    if (value == Double.NEGATIVE_INFINITY) return "-Infinity"
    val negative = value.toBits() < 0
    val decimal = abs(value).toString()
    val exponentStart = decimal.indexOf('E').let { if (it < 0) decimal.indexOf('e') else it }
    val mantissa = if (exponentStart < 0) decimal else decimal.substring(0, exponentStart)
    val exponent = if (exponentStart < 0) 0 else decimal.substring(exponentStart + 1).toInt()
    val dot = mantissa.indexOf('.')
    var decimalPosition = (if (dot < 0) mantissa.length else dot) + exponent
    val digits = StringBuilder(mantissa.filter { it != '.' })
    if (decimalPosition < 0) {
        digits.insert(0, "0".repeat(-decimalPosition))
        decimalPosition = 0
    }
    while (digits.length <= decimalPosition + 6) digits.append('0')
    val roundUp = digits[decimalPosition + 6] >= '5'
    digits.setLength(decimalPosition + 6)
    if (roundUp) {
        var index = digits.lastIndex
        while (index >= 0 && digits[index] == '9') {
            digits[index] = '0'
            index--
        }
        if (index < 0) {
            digits.insert(0, '1')
            decimalPosition++
        } else {
            digits[index] = digits[index] + 1
        }
    }
    val sign = if (negative) "-" else ""
    val integer = digits.substring(0, decimalPosition).trimStart('0').ifEmpty { "0" }
    return "$sign$integer.${digits.substring(decimalPosition)}"
}

open class ValueOutOfRangeException : IllegalArgumentException {
    constructor(argumentName: String, value: Double, boundType: String, bound: Double) :
        super("${fixedSix(value)} was supplied for $argumentName: $argumentName must be $boundType ${fixedSix(bound)}")

    constructor(argumentName: String, value: Int, boundType: String, bound: Int) :
        super("${formatInt(value)} was supplied for $argumentName: $argumentName must be $boundType ${formatInt(bound)}")

    constructor(argumentName1: String, value1: Double, boundType: String, argumentName2: String, value2: Double) :
        super("$argumentName1 must be $boundType $argumentName2: $argumentName1 was ${fixedSix(value1)} and $argumentName2 was ${fixedSix(value2)}")

    constructor(argumentName1: String, value1: Int, boundType: String, argumentName2: String, value2: Int) :
        super("$argumentName1 must be $boundType $argumentName2: $argumentName1 was ${formatInt(value1)} and $argumentName2 was ${formatInt(value2)}")

    constructor(argumentName: String, value: Double) : super("$argumentName cannot be ${fixedSix(value)}")
    constructor(argumentName: String, value: Int) : super("$argumentName cannot be ${formatInt(value)}")

    companion object {
        private const val serialVersionUID = -7115378379246433066L
        const val MUST_BE_GREATER_THAN = "greater than"
        const val MUST_BE_GREATER_THAN_OR_EQUAL_TO = "greater than or equal to"
        const val MUST_BE_LESS_THAN = "less than"
        const val MUST_BE_LESS_THAN_OR_EQUAL_TO = "less than or equal to"
    }
}
