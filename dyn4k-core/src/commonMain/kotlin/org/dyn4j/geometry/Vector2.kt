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

import org.dyn4j.JvmStaticBridge

import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.sin
import kotlin.math.sqrt
import org.dyn4j.Copyable
import org.dyn4j.Epsilon

open class Vector2 : Copyable<Vector2> {
    @kotlin.jvm.JvmField var x: Double = 0.0
    @kotlin.jvm.JvmField var y: Double = 0.0

    constructor()
    constructor(vector: Vector2) { x = vector.x; y = vector.y }
    constructor(x: Double, y: Double) { this.x = x; this.y = y }
    constructor(x1: Double, y1: Double, x2: Double, y2: Double) {
        x = x2 - x1; y = y2 - y1
    }
    constructor(p1: Vector2, p2: Vector2) { x = p2.x - p1.x; y = p2.y - p1.y }
    constructor(direction: Double) { x = cos(direction); y = sin(direction) }

    override fun copy() = Vector2(x, y)
    open fun distance(x: Double, y: Double): Double {
        val dx = this.x - x; val dy = this.y - y
        return sqrt(dx * dx + dy * dy)
    }
    open fun distance(point: Vector2) = distance(point.x, point.y)
    open fun distanceSquared(x: Double, y: Double): Double {
        val dx = this.x - x; val dy = this.y - y
        return dx * dx + dy * dy
    }
    open fun distanceSquared(point: Vector2) = distanceSquared(point.x, point.y)

    override fun hashCode(): Int {
        var result = 1
        var bits = x.toBits()
        result = 31 * result + (bits xor (bits ushr 32)).toInt()
        bits = y.toBits()
        return 31 * result + (bits xor (bits ushr 32)).toInt()
    }
    override fun equals(other: Any?): Boolean =
        other === this || (other is Vector2 && x == other.x && y == other.y)
    open fun equals(vector: Vector2?): Boolean =
        vector === this || (vector != null && x == vector.x && y == vector.y)
    open fun equals(x: Double, y: Double) = this.x == x && this.y == y
    open fun equals(vector: Vector2?, epsilon: Double): Boolean =
        vector === this || (vector != null && equals(vector.x, vector.y, epsilon))
    open fun equals(x: Double, y: Double, epsilon: Double) =
        !(abs(x - this.x) > epsilon) && !(abs(y - this.y) > epsilon)
    override fun toString() = "(" + x + ", " + y + ")"

    open fun set(vector: Vector2): Vector2 = set(vector.x, vector.y)
    open fun set(x: Double, y: Double): Vector2 { this.x = x; this.y = y; return this }
    open fun getXComponent() = Vector2(x, 0.0)
    open fun getYComponent() = Vector2(0.0, y)
    open fun getMagnitude() = sqrt(x * x + y * y)
    open fun getMagnitudeSquared() = x * x + y * y
    open fun setMagnitude(magnitude: Double): Vector2 {
        if (abs(magnitude) <= Epsilon.E) return zero()
        if (isZero()) return this
        val scale = magnitude / getMagnitude()
        x *= scale; y *= scale
        return this
    }
    open fun getDirection() = atan2(y, x)
    open fun setDirection(angle: Double): Vector2 {
        val magnitude = getMagnitude()
        x = magnitude * cos(angle); y = magnitude * sin(angle)
        return this
    }
    open fun add(vector: Vector2) = add(vector.x, vector.y)
    open fun add(x: Double, y: Double): Vector2 { this.x += x; this.y += y; return this }
    open fun sum(vector: Vector2) = sum(vector.x, vector.y)
    open fun sum(x: Double, y: Double) = Vector2(this.x + x, this.y + y)
    open fun subtract(vector: Vector2) = subtract(vector.x, vector.y)
    open fun subtract(x: Double, y: Double): Vector2 { this.x -= x; this.y -= y; return this }
    open fun difference(vector: Vector2) = difference(vector.x, vector.y)
    open fun difference(x: Double, y: Double) = Vector2(this.x - x, this.y - y)
    open fun to(vector: Vector2) = to(vector.x, vector.y)
    open fun to(x: Double, y: Double) = Vector2(x - this.x, y - this.y)
    open fun multiply(scalar: Double): Vector2 { x *= scalar; y *= scalar; return this }
    open fun divide(scalar: Double): Vector2 { x /= scalar; y /= scalar; return this }
    open fun product(scalar: Double) = Vector2(x * scalar, y * scalar)
    open fun quotient(scalar: Double) = Vector2(x / scalar, y / scalar)
    open fun dot(vector: Vector2) = dot(vector.x, vector.y)
    open fun dot(x: Double, y: Double) = this.x * x + this.y * y
    open fun cross(vector: Vector2) = cross(vector.x, vector.y)
    open fun cross(x: Double, y: Double) = this.x * y - this.y * x
    open fun cross(z: Double) = Vector2(-y * z, x * z)
    open fun isOrthogonal(vector: Vector2) = isOrthogonal(vector.x, vector.y)
    open fun isOrthogonal(x: Double, y: Double) = abs(dot(x, y)) <= Epsilon.E
    open fun isZero() = abs(x) <= Epsilon.E && abs(y) <= Epsilon.E
    open fun negate(): Vector2 { x = -x; y = -y; return this }
    open fun getNegative() = Vector2(-x, -y)
    open fun zero(): Vector2 { x = 0.0; y = 0.0; return this }

    @kotlin.jvm.JvmName("rotate")
    internal fun rotate(cost: Double, sint: Double): Vector2 {
        val ox = x; val oy = y
        x = ox * cost - oy * sint; y = ox * sint + oy * cost
        return this
    }
    open fun rotate(theta: Double) = rotate(cos(theta), sin(theta))
    open fun rotate(rotation: Rotation) = rotate(rotation.costValue(), rotation.sintValue())
    open fun inverseRotate(theta: Double) = rotate(cos(theta), -sin(theta))
    open fun inverseRotate(rotation: Rotation) = rotate(rotation.costValue(), -rotation.sintValue())
    @kotlin.jvm.JvmName("rotate")
    internal fun rotate(cost: Double, sint: Double, x: Double, y: Double): Vector2 {
        val tx = this.x - x; val ty = this.y - y
        this.x = tx * cost - ty * sint + x
        this.y = tx * sint + ty * cost + y
        return this
    }
    open fun rotate(theta: Double, x: Double, y: Double) =
        rotate(cos(theta), sin(theta), x, y)
    open fun rotate(rotation: Rotation, x: Double, y: Double) =
        rotate(rotation.costValue(), rotation.sintValue(), x, y)
    open fun inverseRotate(theta: Double, x: Double, y: Double) =
        rotate(cos(theta), -sin(theta), x, y)
    open fun inverseRotate(rotation: Rotation, x: Double, y: Double) =
        rotate(rotation.costValue(), -rotation.sintValue(), x, y)
    open fun rotate(theta: Double, point: Vector2) = rotate(theta, point.x, point.y)
    open fun rotate(rotation: Rotation, point: Vector2) = rotate(rotation, point.x, point.y)
    open fun inverseRotate(theta: Double, point: Vector2) = inverseRotate(theta, point.x, point.y)
    open fun inverseRotate(rotation: Rotation, point: Vector2) =
        inverseRotate(rotation, point.x, point.y)
    open fun project(vector: Vector2): Vector2 {
        val dotProd = dot(vector)
        val denominator = vector.dot(vector)
        if (denominator <= Epsilon.E) return Vector2()
        val scale = dotProd / denominator
        return Vector2(scale * vector.x, scale * vector.y)
    }
    open fun getRightHandOrthogonalVector() = Vector2(-y, x)
    open fun right(): Vector2 { val oldX = x; x = -y; y = oldX; return this }
    open fun getLeftHandOrthogonalVector() = Vector2(y, -x)
    open fun left(): Vector2 { val oldX = x; x = y; y = -oldX; return this }
    open fun getNormalized(): Vector2 {
        val magnitude = getMagnitude()
        if (magnitude <= Epsilon.E) return Vector2()
        return Vector2(x / magnitude, y / magnitude)
    }
    open fun normalize(): Double {
        val magnitude = getMagnitude()
        if (magnitude <= Epsilon.E) return 0.0
        x /= magnitude; y /= magnitude
        return magnitude
    }
    open fun getAngleBetween(vector: Vector2) =
        normalizedDifference(atan2(vector.y, vector.x) - atan2(y, x))
    open fun getAngleBetween(otherAngle: Double) =
        normalizedDifference(otherAngle - atan2(y, x))
    private fun normalizedDifference(angle: Double) =
        when { angle > PI -> angle - 2.0 * PI; angle < -PI -> angle + 2.0 * PI; else -> angle }
    open fun lerp(end: Vector2, changeAmount: Double): Vector2 {
        x = (1 - changeAmount) * x + changeAmount * end.x
        y = (1 - changeAmount) * y + changeAmount * end.y
        return this
    }
    open fun lerp(start: Vector2, end: Vector2, changeAmount: Double): Vector2 {
        x = (1 - changeAmount) * start.x + changeAmount * end.x
        y = (1 - changeAmount) * start.y + changeAmount * end.y
        return this
    }

    companion object {
        @kotlin.jvm.JvmField internal val X_AXIS = Vector2(1.0, 0.0)
        @kotlin.jvm.JvmField internal val Y_AXIS = Vector2(0.0, 1.0)
        @kotlin.jvm.JvmField internal val INV_X_AXIS = Vector2(-1.0, 0.0)
        @kotlin.jvm.JvmField internal val INV_Y_AXIS = Vector2(0.0, -1.0)

        @JvmStaticBridge fun create(magnitude: Double, direction: Double) =
            Vector2(magnitude * cos(direction), magnitude * sin(direction))
        @JvmStaticBridge fun tripleProduct(a: Vector2, b: Vector2, c: Vector2): Vector2 {
            val dot = a.x * b.y - b.x * a.y
            return Vector2(-c.y * dot, c.x * dot)
        }
    }
}
