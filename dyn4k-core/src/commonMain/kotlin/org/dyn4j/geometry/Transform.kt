/*
 * Copyright (c) 2010-2021 William Bittle  http://www.dyn4j.org/
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
import kotlin.math.acos
import kotlin.math.cos
import kotlin.math.sin
import org.dyn4j.Copyable

open class Transform : Transformable, Copyable<Transform> {
    @kotlin.jvm.JvmField protected var cost: Double = 1.0
    @kotlin.jvm.JvmField protected var sint: Double = 0.0
    @kotlin.jvm.JvmField protected var x: Double = 0.0
    @kotlin.jvm.JvmField protected var y: Double = 0.0

    constructor()
    constructor(transform: Transform) {
        cost = transform.cost; sint = transform.sint
        x = transform.x; y = transform.y
    }
    private constructor(cost: Double, sint: Double, x: Double, y: Double) {
        this.cost = cost; this.sint = sint; this.x = x; this.y = y
    }

    override fun toString() =
        "[" + cost + " " + -sint + " | " + x + "][" + sint + " " + cost + " | " + y + "]"

    @kotlin.jvm.JvmName("rotate")
    internal fun rotate(c: Double, s: Double) {
        val nc = clamp(c * cost - s * sint)
        val ns = clamp(s * cost + c * sint)
        val nx = c * x - s * y
        val ny = s * x + c * y
        cost = nc; sint = ns; x = nx; y = ny
    }
    override fun rotate(theta: Double) = rotate(cos(theta), sin(theta))
    override fun rotate(rotation: Rotation) =
        rotate(rotation.costValue(), rotation.sintValue())
    @kotlin.jvm.JvmName("rotate")
    internal fun rotate(c: Double, s: Double, x: Double, y: Double) {
        val nc = clamp(c * cost - s * sint)
        val ns = clamp(s * cost + c * sint)
        cost = nc; sint = ns
        val cx = this.x - x; val cy = this.y - y
        this.x = c * cx - s * cy + x
        this.y = s * cx + c * cy + y
    }
    override fun rotate(theta: Double, x: Double, y: Double) =
        rotate(cos(theta), sin(theta), x, y)
    override fun rotate(rotation: Rotation, x: Double, y: Double) =
        rotate(rotation.costValue(), rotation.sintValue(), x, y)
    override fun rotate(theta: Double, point: Vector2) = rotate(theta, point.x, point.y)
    override fun rotate(rotation: Rotation, point: Vector2) =
        rotate(rotation, point.x, point.y)
    override fun translate(x: Double, y: Double) { this.x += x; this.y += y }
    override fun translate(vector: Vector2) { x += vector.x; y += vector.y }
    override fun copy() = Transform(this)
    open fun set(transform: Transform) {
        cost = transform.cost; sint = transform.sint; x = transform.x; y = transform.y
    }
    open fun identity() { cost = 1.0; sint = 0.0; x = 0.0; y = 0.0 }
    open fun isIdentity() = cost == 1.0 && sint == 0.0 && x == 0.0 && y == 0.0
    open fun getTransformedX(vector: Vector2) = cost * vector.x - sint * vector.y + x
    open fun getTransformedY(vector: Vector2) = sint * vector.x + cost * vector.y + y
    open fun transformX(vector: Vector2) { vector.x = getTransformedX(vector) }
    open fun transformY(vector: Vector2) { vector.y = getTransformedY(vector) }
    open fun getTransformed(vector: Vector2): Vector2 {
        val destination = Vector2()
        getTransformed(vector, destination)
        return destination
    }
    open fun getTransformed(vector: Vector2, destination: Vector2) {
        val vx = vector.x; val vy = vector.y
        destination.x = cost * vx - sint * vy + x
        destination.y = sint * vx + cost * vy + y
    }
    open fun transform(vector: Vector2) = getTransformed(vector, vector)
    open fun getInverseTransformed(vector: Vector2): Vector2 {
        val destination = Vector2()
        getInverseTransformed(vector, destination)
        return destination
    }
    open fun getInverseTransformed(vector: Vector2, destination: Vector2) {
        val tx = vector.x - x; val ty = vector.y - y
        destination.x = cost * tx + sint * ty
        destination.y = -sint * tx + cost * ty
    }
    open fun inverseTransform(vector: Vector2) = getInverseTransformed(vector, vector)
    open fun getTransformedR(vector: Vector2): Vector2 {
        val destination = Vector2()
        getTransformedR(vector, destination)
        return destination
    }
    open fun getTransformedR(vector: Vector2, destination: Vector2) {
        val vx = vector.x; val vy = vector.y
        destination.x = cost * vx - sint * vy
        destination.y = sint * vx + cost * vy
    }
    open fun transformR(vector: Vector2) = getTransformedR(vector, vector)
    open fun getInverseTransformedR(vector: Vector2): Vector2 {
        val destination = Vector2()
        getInverseTransformedR(vector, destination)
        return destination
    }
    open fun getInverseTransformedR(vector: Vector2, destination: Vector2) {
        val vx = vector.x; val vy = vector.y
        destination.x = cost * vx + sint * vy
        destination.y = -sint * vx + cost * vy
    }
    open fun inverseTransformR(vector: Vector2) = getInverseTransformedR(vector, vector)

    open fun getTranslationX() = x
    open fun setTranslationX(x: Double) { this.x = x }
    open fun getTranslationY() = y
    open fun setTranslationY(y: Double) { this.y = y }
    open fun getTranslation() = Vector2(x, y)
    open fun setTranslation(x: Double, y: Double) { this.x = x; this.y = y }
    open fun setTranslation(translation: Vector2) = setTranslation(translation.x, translation.y)
    open fun getTranslationTransform() = Transform(1.0, 0.0, x, y)
    open fun getCost() = cost
    open fun getSint() = sint
    @kotlin.jvm.JvmSynthetic fun costValue() = cost
    @kotlin.jvm.JvmSynthetic fun sintValue() = sint
    open fun getRotationAngle(): Double {
        val a = acos(cost)
        return if (sint >= 0.0) a else -a
    }
    open fun getRotation() = Rotation.of(this)
    open fun setRotation(theta: Double): Double {
        val previous = getRotationAngle()
        cost = cos(theta); sint = sin(theta)
        return previous
    }
    open fun setRotation(rotation: Rotation): Rotation {
        val previous = getRotation()
        cost = rotation.costValue(); sint = rotation.sintValue()
        return previous
    }
    open fun getRotationTransform() = Transform(cost, sint, 0.0, 0.0)
    open fun getValues() = doubleArrayOf(cost, -sint, x, sint, cost, y)

    open fun lerp(end: Transform, alpha: Double) = lerp(end, alpha, this)
    open fun lerp(end: Transform, alpha: Double, result: Transform) {
        val nx = (1.0 - alpha) * x + alpha * end.x
        val ny = (1.0 - alpha) * y + alpha * end.y
        val startAngle = getRotationAngle()
        val endAngle = end.getRotationAngle()
        var difference = endAngle - startAngle
        if (difference < -PI) difference += 2.0 * PI
        if (difference > PI) difference -= 2.0 * PI
        val angle = difference * alpha + startAngle
        result.cost = cos(angle); result.sint = sin(angle)
        result.x = nx; result.y = ny
    }
    private fun rotateOnly(theta: Double) {
        val c = cos(theta); val s = sin(theta)
        val nc = clamp(c * cost - s * sint)
        val ns = clamp(s * cost + c * sint)
        cost = nc; sint = ns
    }
    open fun lerp(dp: Vector2, da: Double, alpha: Double, result: Transform) {
        result.set(this)
        result.rotateOnly(da * alpha)
        result.translate(dp.x * alpha, dp.y * alpha)
    }
    open fun lerp(dp: Vector2, da: Double, alpha: Double) {
        rotateOnly(da * alpha)
        translate(dp.x * alpha, dp.y * alpha)
    }
    open fun lerped(dp: Vector2, da: Double, alpha: Double): Transform {
        val result = copy()
        result.rotateOnly(da * alpha)
        result.translate(dp.x * alpha, dp.y * alpha)
        return result
    }
    open fun lerped(end: Transform, alpha: Double): Transform {
        val result = Transform()
        lerp(end, alpha, result)
        return result
    }

    companion object {
        private fun clamp(value: Double): Double =
            if (value <= 1.0 && value >= -1.0) value else if (1.0 < value) 1.0 else -1.0
    }
}
