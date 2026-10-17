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

import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.sqrt
import org.dyn4j.JvmFieldBridge
import org.dyn4j.exception.ValueOutOfRangeException

open class Ellipse(width: Double, height: Double) : AbstractShape(max(width, height) * 0.5), Convex {
    @get:kotlin.jvm.JvmName("getHalfWidthField")
    @JvmFieldBridge protected val halfWidth: Double
    @get:kotlin.jvm.JvmName("getHalfHeightField")
    @JvmFieldBridge protected val halfHeight: Double
    @get:kotlin.jvm.JvmName("getRotationFieldValue")
    @JvmFieldBridge protected val rotation: Rotation

    init {
        if (width <= 0.0) throw ValueOutOfRangeException("width", width, ValueOutOfRangeException.MUST_BE_GREATER_THAN, 0.0)
        if (height <= 0.0) throw ValueOutOfRangeException("height", height, ValueOutOfRangeException.MUST_BE_GREATER_THAN, 0.0)
        halfWidth = width * 0.5
        halfHeight = height * 0.5
        rotation = Rotation()
    }

    protected constructor(ellipse: Ellipse) : this(ellipse.getWidth(), ellipse.getHeight()) {
        center.set(ellipse.center)
        radius = ellipse.radius
        rotation.set(ellipse.rotation)
    }

    override fun copy() = Ellipse(this)
    override fun toString() = "Ellipse[${super.toString()}|Width=${getWidth()}|Height=${getHeight()}]"
    override fun getAxes(foci: Array<Vector2>?, transform: Transform): Array<Vector2> =
        throw UnsupportedOperationException("SAT does not support the Ellipse shape.")
    override fun getFoci(transform: Transform): Array<Vector2> =
        throw UnsupportedOperationException("SAT does not support the Ellipse shape.")

    override fun getFarthestPoint(vector: Vector2, transform: Transform): Vector2 {
        val localAxis = transform.getInverseTransformedR(vector)
        if (rotation.isIdentity()) {
            farthestAligned(localAxis)
        } else {
            localAxis.inverseRotate(rotation)
            farthestAligned(localAxis)
            localAxis.rotate(rotation)
        }
        localAxis.add(center)
        transform.transform(localAxis)
        return localAxis
    }

    private fun farthestAligned(axis: Vector2) {
        axis.x *= halfWidth
        axis.y *= halfHeight
        axis.normalize()
        axis.x *= halfWidth
        axis.y *= halfHeight
    }

    override fun getFarthestFeature(vector: Vector2, transform: Transform): Feature =
        PointFeature(getFarthestPoint(vector, transform))

    override fun project(vector: Vector2, transform: Transform): Interval {
        val farthest = getFarthestPoint(vector, transform)
        val c = transform.getTransformed(center).dot(vector)
        val d = farthest.dot(vector)
        return Interval(2.0 * c - d, d)
    }

    override fun computeAABB(transform: Transform, aabb: AABB) {
        val u = rotation.toVector()
        transform.transformR(u)
        val x2 = u.x * u.x
        val y2 = u.y * u.y
        val hw2 = halfWidth * halfWidth
        val hh2 = halfHeight * halfHeight
        val extentX = sqrt(x2 * hw2 + y2 * hh2)
        val extentY = sqrt(y2 * hw2 + x2 * hh2)
        val cx = transform.getTransformedX(center)
        val cy = transform.getTransformedY(center)
        aabb.set(AABB(cx - extentX, cy - extentY, cx + extentX, cy + extentY))
    }

    override fun createMass(density: Double): Mass {
        val mass = getArea() * density
        return Mass(center, mass, mass * (halfWidth * halfWidth + halfHeight * halfHeight) / 4.0)
    }
    override fun getArea(): Double = PI * halfWidth * halfHeight
    override fun getRadius(center: Vector2): Double {
        val point = center.difference(this.center).inverseRotate(rotation)
        return point.distance(getFarthestPointOnEllipse(halfWidth, halfHeight, point))
    }

    override fun contains(point: Vector2, transform: Transform, inclusive: Boolean): Boolean {
        val local = transform.getInverseTransformed(point)
        local.inverseRotate(rotation, center)
        val x = local.x - center.x
        val y = local.y - center.y
        val value = x * x / (halfWidth * halfWidth) + y * y / (halfHeight * halfHeight)
        return if (inclusive) value <= 1.0 else value < 1.0
    }
    override fun rotate(rotation: Rotation, x: Double, y: Double) {
        super.rotate(rotation, x, y)
        this.rotation.rotate(rotation)
    }
    fun getRotationAngle(): Double = rotation.toRadians()
    fun getRotation(): Rotation = rotation.copy()
    fun getWidth(): Double = halfWidth * 2.0
    fun getHeight(): Double = halfHeight * 2.0
    fun getHalfWidth(): Double = halfWidth
    fun getHalfHeight(): Double = halfHeight

    companion object {
        private val INV_GOLDEN_RATIO = 1.0 / ((sqrt(5.0) + 1.0) * 0.5)
        private const val FARTHEST_POINT_MAX_ITERATIONS = 50
        private const val FARTHEST_POINT_EPSILON = 1e-8

     fun getFarthestPointOnEllipse(halfWidth: Double, halfHeight: Double, point: Vector2): Vector2 {
            var a = halfWidth
            var b = halfHeight
            var px = point.x
            var py = point.y
            val flipped = a < b
            if (flipped) {
                val previousA = a
                a = b; b = previousA
                val previousX = px
                px = -py; py = previousX
            }
            var quadrant = 3
            if (px >= 0.0 && py >= 0.0) {
                quadrant = 1; px = -px; py = -py
            } else if (px >= 0.0 && py <= 0.0) {
                quadrant = 4; px = -px
            } else if (px <= 0.0 && py >= 0.0) {
                quadrant = 2; py = -py
            }
            val farthest = if (py == 0.0) Vector2(if (px < 0.0) a else -a, 0.0)
                else getFarthestPointOnBoundedEllipse(0.0, a, a, b, Vector2(px, py))
            when (quadrant) {
                1 -> { farthest.x *= -1.0; farthest.y *= -1.0 }
                2 -> farthest.y *= -1.0
                4 -> farthest.x *= -1.0
            }
            if (flipped) {
                val previousX = farthest.x
                farthest.x = farthest.y; farthest.y = -previousX
            }
            return farthest
        }

     fun getFarthestPointOnBoundedEllipse(
            xmin: Double, xmax: Double, a: Double, b: Double, point: Vector2
        ): Vector2 {
            var x0 = xmin
            var x1 = xmax
            val output = Vector2()
            val a2 = a * a
            val ratio = b / a
            var x2 = x1 - (x1 - x0) * INV_GOLDEN_RATIO
            var x3 = x0 + (x1 - x0) * INV_GOLDEN_RATIO
            var fx2 = squaredDistance(a2, ratio, x2, point, output)
            var fx3 = squaredDistance(a2, ratio, x3, point, output)
            for (index in 0 until FARTHEST_POINT_MAX_ITERATIONS) {
                if (fx2 < fx3) {
                    if (abs(x1 - x2) <= FARTHEST_POINT_EPSILON) break
                    x0 = x2; x2 = x3; fx2 = fx3
                    x3 = x0 + (x1 - x0) * INV_GOLDEN_RATIO
                    fx3 = squaredDistance(a2, ratio, x3, point, output)
                } else {
                    if (abs(x3 - x0) <= FARTHEST_POINT_EPSILON) break
                    x1 = x3; x3 = x2; fx3 = fx2
                    x2 = x1 - (x1 - x0) * INV_GOLDEN_RATIO
                    fx2 = squaredDistance(a2, ratio, x2, point, output)
                }
            }
            return output
        }

        private fun squaredDistance(a2: Double, ratio: Double, x: Double, query: Vector2, output: Vector2): Double {
            val y = ratio * sqrt(max(0.0, a2 - x * x))
            val dx = query.x - x
            val dy = query.y - y
            output.x = x
            output.y = y
            return dx * dx + dy * dy
        }
    }
}
