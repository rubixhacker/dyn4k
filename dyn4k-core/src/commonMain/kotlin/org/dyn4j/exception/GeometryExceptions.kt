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
import kotlin.math.floor

class EmptyCollectionException(argumentName: String) : IllegalArgumentException("$argumentName cannot be empty")

class NullElementException : NullPointerException {
    constructor(argumentName: String, index: Int) : super("$argumentName contains a null element at index $index")
    constructor(argumentName: String) : super("$argumentName contains a null element")
}

class InvalidIndexException(index: Int) : IndexOutOfBoundsException("The index $index is out of bounds")

private fun fixedSix(value: Double): String {
    if (value.isNaN()) return "NaN"
    if (value == Double.POSITIVE_INFINITY) return "Infinity"
    if (value == Double.NEGATIVE_INFINITY) return "-Infinity"
    val negative = value.toBits() < 0
    val magnitude = abs(value)
    val rounded = floor(magnitude * 1_000_000.0 + 0.5).toLong()
    val sign = if (negative) "-" else ""
    return "$sign${rounded / 1_000_000}.${(rounded % 1_000_000).toString().padStart(6, '0')}"
}

class ValueOutOfRangeException : IllegalArgumentException {
    constructor(argumentName: String, value: Double, boundType: String, bound: Double) :
        super("${fixedSix(value)} was supplied for $argumentName: $argumentName must be $boundType ${fixedSix(bound)}")

    constructor(argumentName: String, value: Int, boundType: String, bound: Int) :
        super("$value was supplied for $argumentName: $argumentName must be $boundType $bound")

    constructor(argumentName1: String, value1: Double, boundType: String, argumentName2: String, value2: Double) :
        super("$argumentName1 must be $boundType $argumentName2: $argumentName1 was ${fixedSix(value1)} and $argumentName2 was ${fixedSix(value2)}")

    constructor(argumentName1: String, value1: Int, boundType: String, argumentName2: String, value2: Int) :
        super("$argumentName1 must be $boundType $argumentName2: $argumentName1 was $value1 and $argumentName2 was $value2")

    constructor(argumentName: String, value: Double) : super("$argumentName cannot be ${fixedSix(value)}")
    constructor(argumentName: String, value: Int) : super("$argumentName cannot be $value")

    companion object {
        const val MUST_BE_GREATER_THAN = "greater than"
        const val MUST_BE_GREATER_THAN_OR_EQUAL_TO = "greater than or equal to"
        const val MUST_BE_LESS_THAN = "less than"
        const val MUST_BE_LESS_THAN_OR_EQUAL_TO = "less than or equal to"
    }
}
