/*
 * Copyright (c) 2010-2024 William Bittle  http://www.dyn4j.org/
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
import kotlin.math.max
import kotlin.math.min
import org.dyn4j.Copyable
import org.dyn4j.exception.ValueOutOfRangeException

open class Interval : Copyable<Interval> {
    @kotlin.jvm.JvmField protected var min: Double
    @kotlin.jvm.JvmField protected var max: Double

    constructor(min: Double, max: Double) {
        if (min > max) throw ValueOutOfRangeException("min", min, ValueOutOfRangeException.MUST_BE_LESS_THAN_OR_EQUAL_TO, "max", max)
        this.min = min
        this.max = max
    }
    constructor(interval: Interval) : this(interval.min, interval.max)

    override fun copy() = Interval(this)
    override fun toString() = "[$min, $max]"
    open fun getMin() = min
    open fun getMax() = max
    open fun setMin(min: Double) {
        if (min > max) throw ValueOutOfRangeException("min", min, ValueOutOfRangeException.MUST_BE_LESS_THAN_OR_EQUAL_TO, "max", max)
        this.min = min
    }
    open fun setMax(max: Double) {
        if (max < min) throw ValueOutOfRangeException("max", max, ValueOutOfRangeException.MUST_BE_GREATER_THAN_OR_EQUAL_TO, "min", min)
        this.max = max
    }
    open fun set(interval: Interval) {
        max = interval.max
        min = interval.min
    }

    open fun includesInclusive(value: Double) = value <= max && value >= min
    open fun includesExclusive(value: Double) = value < max && value > min
    open fun includesInclusiveMin(value: Double) = value < max && value >= min
    open fun includesInclusiveMax(value: Double) = value <= max && value > min
    open fun overlaps(interval: Interval) = !(min > interval.max || interval.min > max)
    open fun getOverlap(interval: Interval) = if (overlaps(interval)) min(max, interval.max) - max(min, interval.min) else 0.0
    open fun clamp(value: Double) = clamp(value, min, max)
    open fun isDegenerate() = min == max
    open fun isDegenerate(error: Double) = abs(max - min) <= error
    open fun containsExclusive(interval: Interval) = interval.min > min && interval.max < max
    open fun containsInclusive(interval: Interval) = interval.min >= min && interval.max <= max
    open fun containsInclusiveMax(interval: Interval) = interval.min > min && interval.max <= max
    open fun containsInclusiveMin(interval: Interval) = interval.min >= min && interval.max < max
    open fun union(interval: Interval) {
        min = min(interval.min, min)
        max = max(interval.max, max)
    }
    open fun getUnion(interval: Interval) = Interval(min(interval.min, min), max(interval.max, max))
    open fun intersection(interval: Interval) {
        if (overlaps(interval)) {
            min = max(interval.min, min)
            max = min(interval.max, max)
        } else {
            min = 0.0
            max = 0.0
        }
    }
    open fun getIntersection(interval: Interval) = if (overlaps(interval))
        Interval(max(interval.min, min), min(interval.max, max)) else Interval(0.0, 0.0)
    open fun distance(interval: Interval) = if (overlaps(interval)) 0.0 else
        if (max < interval.min) interval.min - max else min - interval.max
    open fun expand(value: Double) {
        val e = value * 0.5
        min -= e
        max += e
        if (value < 0.0 && min > max) {
            min = (min + max) * 0.5
            max = min
        }
    }
    open fun getExpanded(value: Double) = copy().also { it.expand(value) }
    open fun getLength() = max - min

    companion object {
     fun clamp(value: Double, min: Double, max: Double) = when {
            value <= max && value >= min -> value
            max < value -> max
            else -> min
        }
    }
}
