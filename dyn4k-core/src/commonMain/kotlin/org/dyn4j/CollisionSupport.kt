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
package org.dyn4j

import org.dyn4j.exception.CopyException

interface Ownable {
    fun getOwner(): Any?
    fun setOwner(owner: Any?)
}

class Unsafe private constructor() {
    companion object {
        @kotlin.jvm.JvmStatic fun <T : Copyable<*>> copy(copyable: T): T {
            val copy = copyable.copy()
            if (copy::class != copyable::class) throw CopyException(runtimeClassName(copyable), runtimeClassName(copy))
            @Suppress("UNCHECKED_CAST")
            return copy as T
        }
    }
}

class UnitConversion private constructor() {
    companion object {
        const val FOOT_TO_METER = 0.0254 * 12.0
        const val METER_TO_FOOT = 1.0 / FOOT_TO_METER
        const val SLUG_TO_KILOGRAM = 14.5939029
        const val KILOGRAM_TO_SLUG = 1.0 / SLUG_TO_KILOGRAM
        const val POUND_TO_KILOGRAM = 0.45359237
        const val KILOGRAM_TO_POUND = 1.0 / POUND_TO_KILOGRAM
        const val POUND_TO_NEWTON = 4.448222
        const val NEWTON_TO_POUND = 1.0 / POUND_TO_NEWTON
        const val FOOT_POUND_TO_NEWTON_METER = 0.7375621
        const val NEWTON_METER_TO_FOOT_POUND = 1.0 / FOOT_POUND_TO_NEWTON_METER

        @kotlin.jvm.JvmStatic fun feetToMeters(feet: Double) = feet * FOOT_TO_METER
        @kotlin.jvm.JvmStatic fun slugsToKilograms(slugs: Double) = slugs * SLUG_TO_KILOGRAM
        @kotlin.jvm.JvmStatic fun poundsToKilograms(pound: Double) = pound * POUND_TO_KILOGRAM
        @kotlin.jvm.JvmStatic fun feetPerSecondToMetersPerSecond(feetPerSecond: Double) = feetPerSecond * METER_TO_FOOT
        @kotlin.jvm.JvmStatic fun poundsToNewtons(pound: Double) = pound * POUND_TO_NEWTON
        @kotlin.jvm.JvmStatic fun footPoundsToNewtonMeters(footPound: Double) = footPound * FOOT_POUND_TO_NEWTON_METER
        @kotlin.jvm.JvmStatic fun metersToFeet(meters: Double) = meters * METER_TO_FOOT
        @kotlin.jvm.JvmStatic fun kilogramsToSlugs(kilograms: Double) = kilograms * KILOGRAM_TO_SLUG
        @kotlin.jvm.JvmStatic fun kilogramsToPounds(kilograms: Double) = kilograms * KILOGRAM_TO_POUND
        @kotlin.jvm.JvmStatic fun metersPerSecondToFeetPerSecond(metersPerSecond: Double) = metersPerSecond * FOOT_TO_METER
        @kotlin.jvm.JvmStatic fun newtonsToPounds(newtons: Double) = newtons * NEWTON_TO_POUND
        @kotlin.jvm.JvmStatic fun newtonMetersToFootPounds(newtonMeters: Double) = newtonMeters * NEWTON_METER_TO_FOOT_POUND
    }
}
