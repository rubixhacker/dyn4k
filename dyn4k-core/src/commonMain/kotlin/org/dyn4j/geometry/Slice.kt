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
import kotlin.math.cos
import kotlin.math.max
import kotlin.math.sin
import kotlin.math.sqrt
import org.dyn4j.JvmFieldBridge
import org.dyn4j.exception.ValueOutOfRangeException

open class Slice : AbstractShape, Convex {
    @get:kotlin.jvm.JvmName("getAlphaField")
    @JvmFieldBridge protected val alpha: Double
    @get:kotlin.jvm.JvmName("getCosAlphaField")
    @JvmFieldBridge protected val cosAlpha: Double
    @get:kotlin.jvm.JvmName("getSliceRadiusField")
    @JvmFieldBridge protected val sliceRadius: Double
    @get:kotlin.jvm.JvmName("getVerticesField")
    @JvmFieldBridge protected val vertices: Array<Vector2>
    @get:kotlin.jvm.JvmName("getNormalsField")
    @JvmFieldBridge protected val normals: Array<Vector2>
    @get:kotlin.jvm.JvmName("getRotationFieldValue")
    @JvmFieldBridge protected val rotation: Rotation

    constructor(radius: Double, theta: Double) : super(
        Vector2(2.0 * radius * sin(theta * 0.5) / (1.5 * theta), 0.0),
        max(
            2.0 * radius * sin(theta * 0.5) / (1.5 * theta),
            Vector2(2.0 * radius * sin(theta * 0.5) / (1.5 * theta), 0.0)
                .distance(Vector2(radius, 0.0).rotate(0.5 * theta))
        )
    ) {
        if (radius <= 0.0) throw ValueOutOfRangeException("radius", radius, ValueOutOfRangeException.MUST_BE_GREATER_THAN, 0.0)
        if (theta <= 0.0) throw ValueOutOfRangeException("theta", theta, ValueOutOfRangeException.MUST_BE_GREATER_THAN, 0.0)
        if (theta > PI) throw ValueOutOfRangeException("theta", theta, ValueOutOfRangeException.MUST_BE_LESS_THAN_OR_EQUAL_TO, PI)
        sliceRadius = radius
        alpha = theta * 0.5
        cosAlpha = cos(alpha)
        val x = radius * cosAlpha
        val y = radius * sin(alpha)
        vertices = arrayOf(Vector2(), Vector2(x, y), Vector2(x, -y))
        val normal1 = vertices[1].to(vertices[0]).left().also { it.normalize() }
        val normal2 = vertices[0].to(vertices[2]).left().also { it.normalize() }
        normals = arrayOf(normal1, normal2)
        rotation = Rotation()
    }

    protected constructor(other: Slice) : super(other) {
        alpha = other.alpha
        cosAlpha = other.cosAlpha
        rotation = other.rotation.copy()
        sliceRadius = other.sliceRadius
        vertices = Array(other.vertices.size) { other.vertices[it].copy() }
        normals = Array(other.normals.size) { other.normals[it].copy() }
    }
    override fun copy() = Slice(this)
    override fun toString() = "Slice[${super.toString()}|Radius=$sliceRadius|Theta=${getTheta()}]"

    override fun getAxes(foci: Array<Vector2>?, transform: Transform): Array<Vector2> {
        val axes = Array(2 + (foci?.size ?: 0)) { Vector2() }
        axes[0] = transform.getTransformedR(normals[0])
        axes[1] = transform.getTransformedR(normals[1])
        if (foci != null) {
            val tip = transform.getTransformed(vertices[0])
            for ((index, focus) in foci.withIndex()) {
                var closest = tip
                var distance = focus.distanceSquared(closest)
                for (vertexIndex in 1 until vertices.size) {
                    val vertex = transform.getTransformed(vertices[vertexIndex])
                    val candidate = focus.distanceSquared(vertex)
                    if (candidate < distance) { closest = vertex; distance = candidate }
                }
                axes[index + 2] = focus.to(closest).also { it.normalize() }
            }
        }
        return axes
    }
    override fun getFoci(transform: Transform) = arrayOf(transform.getTransformed(vertices[0]))

    override fun getFarthestPoint(vector: Vector2, transform: Transform): Vector2 {
        val local = transform.getInverseTransformedR(vector)
        local.normalize()
        val rotated = if (rotation.isIdentity()) local else local.copy().inverseRotate(rotation)
        if (rotated.x < cosAlpha) {
            val tipProjection = vertices[0].dot(local)
            var index = 0
            if (rotated.y < 0.0) {
                if (vertices[2].dot(local) > tipProjection) index = 2
            } else if (vertices[1].dot(local) > tipProjection) index = 1
            return transform.getTransformed(vertices[index])
        }
        local.multiply(sliceRadius).add(vertices[0])
        transform.transform(local)
        return local
    }

    override fun getFarthestFeature(vector: Vector2, transform: Transform): Feature {
        val local = transform.getInverseTransformedR(vector)
        local.normalize()
        val rotated = if (rotation.isIdentity()) local else local.copy().inverseRotate(rotation)
        if (rotated.x < cosAlpha) {
            if (cosAlpha <= 1e-6) return Segment.getFarthestFeature(vertices[1], vertices[2], vector, transform)
            if (rotated.y > 0.0) return Segment.getFarthestFeature(vertices[0], vertices[1], vector, transform)
            if (rotated.y < 0.0) return Segment.getFarthestFeature(vertices[0], vertices[2], vector, transform)
            return PointFeature(transform.getTransformed(vertices[0]))
        }
        local.multiply(sliceRadius).add(vertices[0])
        transform.transform(local)
        return PointFeature(local)
    }

    override fun project(vector: Vector2, transform: Transform): Interval {
        val farthest = getFarthestPoint(vector, transform)
        val opposite = getFarthestPoint(vector.getNegative(), transform)
        return Interval(opposite.dot(vector), farthest.dot(vector))
    }
    override fun computeAABB(transform: Transform, aabb: AABB) {
        val minX = getFarthestPoint(Vector2.INV_X_AXIS, transform).x
        val maxX = getFarthestPoint(Vector2.X_AXIS, transform).x
        val minY = getFarthestPoint(Vector2.INV_Y_AXIS, transform).y
        val maxY = getFarthestPoint(Vector2.Y_AXIS, transform).y
        aabb.set(AABB(minX, minY, maxX, maxY))
    }
    override fun createMass(density: Double): Mass {
        val r2 = sliceRadius * sliceRadius
        val mass = density * r2 * alpha
        val sine = sin(alpha)
        val inertia = density * (1.0 / 18.0 * r2 * r2 * (9.0 * alpha * alpha - 8.0 * sine * sine) / alpha)
        return Mass(center, mass, inertia)
    }
    override fun getArea(): Double = sliceRadius * sliceRadius * alpha
    override fun getRadius(center: Vector2): Double {
        if (Segment.getLocation(center, vertices[1], vertices[0]) <= 0.0 &&
            Segment.getLocation(center, vertices[2], vertices[0]) >= 0.0
        ) return sliceRadius + center.distance(vertices[0])
        return sqrt(max(vertices[0].distanceSquared(center), max(vertices[1].distanceSquared(center), vertices[2].distanceSquared(center))))
    }
    override fun contains(point: Vector2, transform: Transform, inclusive: Boolean): Boolean {
        val local = transform.getInverseTransformed(point)
        val displacement = vertices[0].to(local)
        val distance = displacement.getMagnitudeSquared()
        val r2 = sliceRadius * sliceRadius
        if (if (inclusive) distance > r2 else distance >= r2) return false
        val left = Segment.getLocation(local, vertices[0], vertices[1])
        val right = Segment.getLocation(local, vertices[0], vertices[2])
        return if (inclusive) left <= 0.0 && right >= 0.0 else left < 0.0 && right > 0.0
    }
    override fun rotate(rotation: Rotation, x: Double, y: Double) {
        super.rotate(rotation, x, y)
        for (vertex in vertices) vertex.rotate(rotation, x, y)
        for (normal in normals) normal.rotate(rotation)
        this.rotation.rotate(rotation)
    }
    override fun translate(x: Double, y: Double) {
        super.translate(x, y)
        for (vertex in vertices) vertex.add(x, y)
    }
    fun getRotationAngle(): Double = rotation.toRadians()
    fun getRotation(): Rotation = rotation.copy()
    fun getTheta(): Double = alpha * 2.0
    fun getSliceRadius(): Double = sliceRadius
    fun getCircleCenter(): Vector2 = vertices[0]
}
