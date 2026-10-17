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
import kotlin.math.atan2
import org.dyn4j.JvmFieldBridge
import org.dyn4j.exception.ValueOutOfRangeException

open class Rectangle : Polygon {
    @get:kotlin.jvm.JvmName("getWidthField")
    @JvmFieldBridge private val width: Double
    @get:kotlin.jvm.JvmName("getHeightField")
    @JvmFieldBridge private val height: Double

    constructor(width: Double, height: Double) : super(
        Vector2(),
        Vector2(width * 0.5, height * 0.5).getMagnitude(),
        arrayOf(
            Vector2(-width * 0.5, -height * 0.5),
            Vector2(width * 0.5, -height * 0.5),
            Vector2(width * 0.5, height * 0.5),
            Vector2(-width * 0.5, height * 0.5)
        ),
        arrayOf(Vector2(0.0, -1.0), Vector2(1.0, 0.0), Vector2(0.0, 1.0), Vector2(-1.0, 0.0))
    ) {
        if (width <= 0.0) throw ValueOutOfRangeException("width", width, ValueOutOfRangeException.MUST_BE_GREATER_THAN, 0.0)
        if (height <= 0.0) throw ValueOutOfRangeException("height", height, ValueOutOfRangeException.MUST_BE_GREATER_THAN, 0.0)
        this.width = width
        this.height = height
    }
    protected constructor(rectangle: Rectangle) : super(rectangle) {
        width = rectangle.width
        height = rectangle.height
    }

    override fun copy() = Rectangle(this)
    override fun toString() = "Rectangle[${super.toString()}|Width=$width|Height=$height]"
    fun getWidth() = width
    fun getHeight() = height
    fun getRotationAngle() = atan2(normals[1].y, normals[1].x)
    fun getRotation() = Rotation.fromComponentsUnchecked(normals[1].x, normals[1].y)
    override fun getAxes(foci: Array<Vector2>?, transform: Transform): Array<Vector2> {
        val axes = Array(2 + (foci?.size ?: 0)) { Vector2() }
        axes[0] = transform.getTransformedR(normals[1])
        axes[1] = transform.getTransformedR(normals[2])
        if (foci != null) {
            for ((focusIndex, focus) in foci.withIndex()) {
                var closest = transform.getTransformed(vertices[0])
                var distance = focus.distanceSquared(closest)
                for (index in 1 until 4) {
                    val point = transform.getTransformed(vertices[index])
                    val candidate = focus.distanceSquared(point)
                    if (candidate < distance) {
                        closest = point
                        distance = candidate
                    }
                }
                axes[focusIndex + 2] = focus.to(closest).also { it.normalize() }
            }
        }
        return axes
    }
    override fun contains(point: Vector2, transform: Transform): Boolean {
        val local = transform.getInverseTransformed(point)
        val p1 = vertices[0]
        val axis0 = p1.to(vertices[1])
        val axis1 = p1.to(vertices[3])
        val toPoint = center.to(local)
        return toPoint.project(axis0).getMagnitudeSquared() <= p1.distanceSquared(vertices[1]) * 0.25 &&
            toPoint.project(axis1).getMagnitudeSquared() <= p1.distanceSquared(vertices[3]) * 0.25
    }
    override fun project(vector: Vector2, transform: Transform): Interval {
        val projectedCenter = transform.getTransformed(center).dot(vector)
        val axis0 = transform.getTransformedR(normals[1])
        val axis1 = transform.getTransformedR(normals[2])
        val extent = width * 0.5 * abs(axis0.dot(vector)) + height * 0.5 * abs(axis1.dot(vector))
        return Interval(projectedCenter - extent, projectedCenter + extent)
    }
    override fun createMass(density: Double): Mass {
        val mass = density * height * width
        return Mass(center, mass, mass * (height * height + width * width) / 12.0)
    }
    override fun computeAABB(transform: Transform, aabb: AABB) {
        val x0 = transform.getTransformedX(vertices[0])
        val y0 = transform.getTransformedY(vertices[0])
        val x1 = transform.getTransformedX(vertices[1])
        val y1 = transform.getTransformedY(vertices[1])
        val x2 = transform.getTransformedX(vertices[2])
        val y2 = transform.getTransformedY(vertices[2])
        val x3 = transform.getTransformedX(vertices[3])
        val y3 = transform.getTransformedY(vertices[3])
        val bounds = if (y0 > y1) {
            if (x0 < x1) AABB(x0, y1, x2, y3) else AABB(x1, y2, x3, y0)
        } else {
            if (x0 < x1) AABB(x3, y0, x1, y2) else AABB(x2, y3, x0, y1)
        }
        aabb.set(bounds)
    }
}
