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

import org.dyn4j.JvmFieldBridge
import org.dyn4j.JvmStaticBridge

import kotlin.math.abs
import kotlin.math.sqrt
import org.dyn4j.Copyable
import org.dyn4j.Epsilon

open class Vector3 : Copyable<Vector3> {
    @JvmFieldBridge var x: Double = 0.0
    @JvmFieldBridge var y: Double = 0.0
    @JvmFieldBridge var z: Double = 0.0

    constructor()
    constructor(vector: Vector3) { x = vector.x; y = vector.y; z = vector.z }
    constructor(x: Double, y: Double, z: Double) { this.x = x; this.y = y; this.z = z }
    constructor(x1: Double, y1: Double, z1: Double, x2: Double, y2: Double, z2: Double) {
        x = x2 - x1; y = y2 - y1; z = z2 - z1
    }
    constructor(p1: Vector3, p2: Vector3) {
        x = p2.x - p1.x; y = p2.y - p1.y; z = p2.z - p1.z
    }
    override fun copy() = Vector3(x, y, z)
    open fun distance(x: Double, y: Double, z: Double) = sqrt(distanceSquared(x, y, z))
    open fun distance(point: Vector3) = distance(point.x, point.y, point.z)
    open fun distanceSquared(x: Double, y: Double, z: Double): Double {
        val dx = this.x - x; val dy = this.y - y; val dz = this.z - z
        return dx * dx + dy * dy + dz * dz
    }
    open fun distanceSquared(point: Vector3) = distanceSquared(point.x, point.y, point.z)

    override fun hashCode(): Int {
        var result = 1
        for (value in doubleArrayOf(x, y, z)) {
            val bits = value.toBits()
            result = 31 * result + (bits xor (bits ushr 32)).toInt()
        }
        return result
    }
    override fun equals(other: Any?): Boolean =
        other === this || (other is Vector3 && x == other.x && y == other.y && z == other.z)
    open fun equals(vector: Vector3?): Boolean =
        vector === this || (vector != null && x == vector.x && y == vector.y && z == vector.z)
    open fun equals(x: Double, y: Double, z: Double) =
        this.x == x && this.y == y && this.z == z
    open fun equals(vector: Vector3?, epsilon: Double) =
        vector === this || (vector != null && equals(vector.x, vector.y, vector.z, epsilon))
    open fun equals(x: Double, y: Double, z: Double, epsilon: Double) =
        !(abs(x - this.x) > epsilon) &&
        !(abs(y - this.y) > epsilon) &&
        !(abs(z - this.z) > epsilon)
    override fun toString() = "(" + x + ", " + y + ", " + z + ")"

    open fun set(vector: Vector3) = set(vector.x, vector.y, vector.z)
    open fun set(x: Double, y: Double, z: Double): Vector3 {
        this.x = x; this.y = y; this.z = z
        return this
    }
    open fun getXComponent() = Vector3(x, 0.0, 0.0)
    open fun getYComponent() = Vector3(0.0, y, 0.0)
    open fun getZComponent() = Vector3(0.0, 0.0, z)
    open fun getMagnitude() = sqrt(x * x + y * y + z * z)
    open fun getMagnitudeSquared() = x * x + y * y + z * z
    open fun setMagnitude(magnitude: Double): Vector3 {
        if (abs(magnitude) <= Epsilon.E) return zero()
        if (isZero()) return this
        val scale = magnitude / getMagnitude()
        x *= scale; y *= scale; z *= scale
        return this
    }
    open fun add(vector: Vector3) = add(vector.x, vector.y, vector.z)
    open fun add(x: Double, y: Double, z: Double): Vector3 {
        this.x += x; this.y += y; this.z += z
        return this
    }
    open fun sum(vector: Vector3) = sum(vector.x, vector.y, vector.z)
    open fun sum(x: Double, y: Double, z: Double) = Vector3(this.x + x, this.y + y, this.z + z)
    open fun subtract(vector: Vector3) = subtract(vector.x, vector.y, vector.z)
    open fun subtract(x: Double, y: Double, z: Double): Vector3 {
        this.x -= x; this.y -= y; this.z -= z
        return this
    }
    open fun difference(vector: Vector3) = difference(vector.x, vector.y, vector.z)
    open fun difference(x: Double, y: Double, z: Double) =
        Vector3(this.x - x, this.y - y, this.z - z)
    open fun to(vector: Vector3) = to(vector.x, vector.y, vector.z)
    open fun to(x: Double, y: Double, z: Double) = Vector3(x - this.x, y - this.y, z - this.z)
    open fun multiply(scalar: Double): Vector3 { x *= scalar; y *= scalar; z *= scalar; return this }
    open fun product(scalar: Double) = Vector3(x * scalar, y * scalar, z * scalar)
    open fun dot(vector: Vector3) = dot(vector.x, vector.y, vector.z)
    open fun dot(x: Double, y: Double, z: Double) = this.x * x + this.y * y + this.z * z
    open fun cross(vector: Vector3) = cross(vector.x, vector.y, vector.z)
    open fun cross(x: Double, y: Double, z: Double) =
        Vector3(this.y * z - this.z * y, this.z * x - this.x * z, this.x * y - this.y * x)
    open fun isOrthogonal(vector: Vector3) = isOrthogonal(vector.x, vector.y, vector.z)
    open fun isOrthogonal(x: Double, y: Double, z: Double) =
        abs(dot(x, y, z)) <= Epsilon.E
    open fun isZero() = abs(x) <= Epsilon.E && abs(y) <= Epsilon.E && abs(z) <= Epsilon.E
    open fun negate(): Vector3 { x = -x; y = -y; z = -z; return this }
    open fun getNegative() = Vector3(-x, -y, -z)
    open fun zero(): Vector3 { x = 0.0; y = 0.0; z = 0.0; return this }
    open fun project(vector: Vector3): Vector3 {
        val dotProd = dot(vector)
        val denominator = vector.dot(vector)
        if (denominator <= Epsilon.E) return Vector3()
        val scale = dotProd / denominator
        return Vector3(scale * vector.x, scale * vector.y, scale * vector.z)
    }
    open fun getNormalized(): Vector3 {
        val magnitude = getMagnitude()
        if (magnitude <= Epsilon.E) return Vector3()
        return Vector3(x / magnitude, y / magnitude, z / magnitude)
    }
    open fun normalize(): Double {
        val magnitude = getMagnitude()
        if (magnitude <= Epsilon.E) return 0.0
        x /= magnitude; y /= magnitude; z /= magnitude
        return magnitude
    }
    open fun lerp(end: Vector3, changeAmount: Double): Vector3 {
        x = (1 - changeAmount) * x + changeAmount * end.x
        y = (1 - changeAmount) * y + changeAmount * end.y
        z = (1 - changeAmount) * z + changeAmount * end.z
        return this
    }
    open fun lerp(start: Vector3, end: Vector3, changeAmount: Double): Vector3 {
        x = (1 - changeAmount) * start.x + changeAmount * end.x
        y = (1 - changeAmount) * start.y + changeAmount * end.y
        z = (1 - changeAmount) * start.z + changeAmount * end.z
        return this
    }

    companion object {
        @JvmStaticBridge fun tripleProduct(a: Vector3, b: Vector3, c: Vector3): Vector3 {
            val ac = a.x * c.x + a.y * c.y + a.z * c.z
            val bc = b.x * c.x + b.y * c.y + b.z * c.z
            return Vector3(b.x * ac - a.x * bc, b.y * ac - a.y * bc, b.z * ac - a.z * bc)
        }
    }
}
