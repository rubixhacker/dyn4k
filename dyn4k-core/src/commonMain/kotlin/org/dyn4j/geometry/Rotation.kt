/*
 * Copyright (c) 2010-2026 William Bittle  http://www.dyn4j.org/
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

import org.dyn4j.JvmFieldBridge
import org.dyn4j.JvmStaticBridge

import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.acos
import kotlin.math.cos
import kotlin.math.floor
import kotlin.math.sin
import kotlin.math.sqrt
import org.dyn4j.Copyable
import org.dyn4j.Epsilon

open class Rotation : Copyable<Rotation> {
    @JvmFieldBridge protected var cost: Double = 1.0
    @JvmFieldBridge protected var sint: Double = 0.0

    protected constructor(cost: Double, sint: Double) { this.cost = cost; this.sint = sint }
    constructor()
    constructor(rotation: Rotation) { cost = rotation.cost; sint = rotation.sint }
    constructor(angle: Double) { cost = cos(angle); sint = sin(angle) }

    override fun copy() = Rotation(this)
    override fun hashCode(): Int {
        var result = 3
        var bits = cost.toBits()
        result = 31 * result + (bits xor (bits ushr 32)).toInt()
        bits = sint.toBits()
        return 31 * result + (bits xor (bits ushr 32)).toInt()
    }
    override fun equals(other: Any?): Boolean =
        other === this || (other is Rotation && cost == other.cost && sint == other.sint)
    open fun equals(rotation: Rotation?) =
        rotation != null && cost == rotation.cost && sint == rotation.sint
    open fun equals(rotation: Rotation?, error: Double) =
        rotation != null && abs(cost - rotation.cost) < error && abs(sint - rotation.sint) < error
    open fun equals(angle: Double) = cost == cos(angle) && sint == sin(angle)
    open fun equals(angle: Double, error: Double) =
        abs(cost - cos(angle)) < error && abs(sint - sin(angle)) < error
    override fun toString() = "Rotation(" + cost + ", " + sint + ")"

    open fun set(rotation: Rotation): Rotation { cost = rotation.cost; sint = rotation.sint; return this }
    open fun setIdentity(): Rotation { cost = 1.0; sint = 0.0; return this }
    open fun set(angle: Double): Rotation { cost = cos(angle); sint = sin(angle); return this }
    open fun costValue() = cost
    open fun sintValue() = sint
    open fun toRadians(): Double {
        val c = clamp(cost)
        val a = acos(c)
        return if (sint >= 0.0) a else -a
    }
    open fun toDegrees() = toRadians() * 180.0 / PI
    open fun toVector() = Vector2(cost, sint)
    open fun toVector(magnitude: Double) = Vector2(cost * magnitude, sint * magnitude)

    internal fun rotate45Helper(cost: Double, sint: Double): Rotation {
        this.cost = SQRT_2_INV * (cost - sint)
        this.sint = SQRT_2_INV * (cost + sint)
        return this
    }
    internal fun getRotated45Helper(cost: Double, sint: Double) =
        Rotation(SQRT_2_INV * (cost - sint), SQRT_2_INV * (cost + sint))
    open fun rotate45() = rotate45Helper(cost, sint)
    open fun getRotated45() = getRotated45Helper(cost, sint)
    open fun rotate90(): Rotation { val c = cost; cost = -sint; sint = c; return this }
    open fun getRotated90() = Rotation(-sint, cost)
    open fun rotate135() = rotate45Helper(-sint, cost)
    open fun getRotated135() = getRotated45Helper(-sint, cost)
    open fun rotate180(): Rotation { cost = -cost; sint = -sint; return this }
    open fun getRotated180() = Rotation(-cost, -sint)
    open fun rotate225() = rotate45Helper(-cost, -sint)
    open fun getRotated225() = getRotated45Helper(-cost, -sint)
    open fun rotate270(): Rotation { val c = cost; cost = sint; sint = -c; return this }
    open fun getRotated270() = Rotation(sint, -cost)
    open fun rotate315() = rotate45Helper(sint, -cost)
    open fun getRotated315() = getRotated45Helper(sint, -cost)
    open fun inverse(): Rotation { sint = -sint; return this }
    open fun getInversed() = Rotation(cost, -sint)

    internal fun rotateComponents(c: Double, s: Double): Rotation {
        val oc = cost; val os = sint
        cost = clamp(oc * c - os * s)
        sint = clamp(oc * s + os * c)
        return this
    }
    open fun getRotated(c: Double, s: Double) =
        Rotation(clamp(cost * c - sint * s), clamp(cost * s + sint * c))
    open fun rotate(rotation: Rotation) = rotateComponents(rotation.cost, rotation.sint)
    open fun getRotated(rotation: Rotation) = getRotated(rotation.cost, rotation.sint)
    open fun rotate(angle: Double) = rotateComponents(cos(angle), sin(angle))
    open fun getRotated(angle: Double) = getRotated(cos(angle), sin(angle))
    open fun isIdentity() = cost == 1.0
    open fun isIdentity(error: Double) = abs(cost - 1.0) < error
    open fun dot(rotation: Rotation) = cost * rotation.cost + sint * rotation.sint
    open fun cross(rotation: Rotation) = cost * rotation.sint - sint * rotation.cost
    open fun dot(vector: Vector2) = cost * vector.x + sint * vector.y
    open fun cross(vector: Vector2) = cost * vector.y - sint * vector.x
    open fun compare(other: Rotation): Int {
        val difference = cross(other)
        return if (difference > 0.0) 1 else if (difference < 0.0) -1 else 0
    }
    open fun compare(other: Vector2): Int {
        val difference = cross(other)
        return if (difference > 0.0) 1 else if (difference < 0.0) -1 else 0
    }
    open fun getRotationBetween(rotation: Rotation) = Rotation(dot(rotation), cross(rotation))
    open fun getRotationBetween(vector: Vector2) = getRotationBetween(of(vector))

    companion object {
        private val SQRT_2_INV = 1.0 / sqrt(2.0)
        private val INV_TWO_PI = 1.0 / (2.0 * PI)
        private fun clamp(value: Double): Double =
            if (value <= 1.0 && value >= -1.0) value else if (1.0 < value) 1.0 else -1.0

        @JvmStaticBridge fun of(angle: Double) = Rotation(angle)
        @JvmStaticBridge fun ofDegrees(angle: Double) = Rotation(angle / 180.0 * PI)
        @JvmStaticBridge fun of(direction: Vector2): Rotation {
            val magnitude = sqrt(direction.x * direction.x + direction.y * direction.y)
            if (magnitude <= Epsilon.E) return Rotation()
            return Rotation(direction.x / magnitude, direction.y / magnitude)
        }
        @JvmStaticBridge fun of(cost: Double, sint: Double): Rotation {
            val magnitude = cost * cost + sint * sint
            if (abs(magnitude - 1.0) > Epsilon.E)
                throw IllegalArgumentException("The magnitude of the rotation is outside the unit circle.")
            return Rotation(cost, sint)
        }
        @JvmStaticBridge fun of(transform: Transform) = Rotation(transform.costValue(), transform.sintValue())
        @JvmStaticBridge fun rotation0() = Rotation()
        @JvmStaticBridge fun rotation90() = Rotation(0.0, 1.0)
        @JvmStaticBridge fun rotation180() = Rotation(-1.0, 0.0)
        @JvmStaticBridge fun rotation270() = Rotation(0.0, -1.0)
        @JvmStaticBridge fun rotation45() = Rotation(SQRT_2_INV, SQRT_2_INV)
        @JvmStaticBridge fun rotation135() = Rotation(-SQRT_2_INV, SQRT_2_INV)
        @JvmStaticBridge fun rotation225() = Rotation(-SQRT_2_INV, -SQRT_2_INV)
        @JvmStaticBridge fun rotation315() = Rotation(SQRT_2_INV, -SQRT_2_INV)
        @JvmStaticBridge fun getNormalizedAngle(angle: Double): Double {
            val rotations = floor((angle + PI) * INV_TWO_PI)
            return angle - rotations * (2.0 * PI)
        }
        @JvmStaticBridge fun getShortestDistance(angle1: Double, angle2: Double) =
            getNormalizedAngle(angle2 - angle1)
        @JvmStaticBridge fun isAngleBetween(
            angle: Double,
            clockwiseAngle: Double,
            counterClockwiseAngle: Double
        ) = if (clockwiseAngle <= counterClockwiseAngle)
            angle >= clockwiseAngle && angle <= counterClockwiseAngle
        else angle >= clockwiseAngle || angle <= counterClockwiseAngle
    }
}
