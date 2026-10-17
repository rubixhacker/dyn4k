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
import kotlin.math.pow
import kotlin.math.sqrt
import org.dyn4j.JvmFieldBridge
import org.dyn4j.exception.ValueOutOfRangeException

open class HalfEllipse(width: Double, height: Double) : AbstractShape(
    Vector2(0.0, (4.0 * height) / (3.0 * PI)),
    Vector2(0.0, (4.0 * height) / (3.0 * PI)).distance(Vector2(width * 0.5, 0.0))
), Convex {
    @get:kotlin.jvm.JvmName("getHeightField")
    @JvmFieldBridge protected val height: Double
    @get:kotlin.jvm.JvmName("getHalfWidthField")
    @JvmFieldBridge protected val halfWidth: Double
    @get:kotlin.jvm.JvmName("getRotationFieldValue")
    @JvmFieldBridge protected val rotation: Rotation
    @get:kotlin.jvm.JvmName("getEllipseCenterField")
    @JvmFieldBridge protected val ellipseCenter: Vector2
    @get:kotlin.jvm.JvmName("getVertexLeftField")
    @JvmFieldBridge protected val vertexLeft: Vector2
    @get:kotlin.jvm.JvmName("getVertexRightField")
    @JvmFieldBridge protected val vertexRight: Vector2

    init {
        if (width <= 0.0) throw ValueOutOfRangeException("width", width, ValueOutOfRangeException.MUST_BE_GREATER_THAN, 0.0)
        if (height <= 0.0) throw ValueOutOfRangeException("height", height, ValueOutOfRangeException.MUST_BE_GREATER_THAN, 0.0)
        this.height = height
        halfWidth = width * 0.5
        rotation = Rotation()
        ellipseCenter = Vector2()
        vertexLeft = Vector2(-halfWidth, 0.0)
        vertexRight = Vector2(halfWidth, 0.0)
    }

    protected constructor(other: HalfEllipse) : this(other.getWidth(), other.height) {
        center.set(other.center)
        radius = other.radius
        rotation.set(other.rotation)
        ellipseCenter.set(other.ellipseCenter)
        vertexLeft.set(other.vertexLeft)
        vertexRight.set(other.vertexRight)
    }

    override fun copy() = HalfEllipse(this)
    override fun toString() = "HalfEllipse[${super.toString()}|Width=${getWidth()}|Height=$height]"
    override fun getAxes(foci: Array<Vector2>?, transform: Transform): Array<Vector2> =
        throw UnsupportedOperationException("SAT does not support the HalfEllipse shape.")
    override fun getFoci(transform: Transform): Array<Vector2> =
        throw UnsupportedOperationException("SAT does not support the HalfEllipse shape.")

    private fun farthestAligned(axis: Vector2) {
        axis.x *= halfWidth
        axis.y *= height
        axis.normalize()
        axis.x *= halfWidth
        axis.y *= height
    }

    override fun getFarthestPoint(vector: Vector2, transform: Transform): Vector2 {
        val axis = transform.getInverseTransformedR(vector)
        axis.inverseRotate(rotation)
        if (axis.y <= 0.0) {
            axis.set(if (axis.x >= 0.0) vertexRight else vertexLeft)
        } else {
            farthestAligned(axis)
            axis.rotate(rotation)
            axis.add(ellipseCenter)
        }
        transform.transform(axis)
        return axis
    }

    override fun getFarthestFeature(vector: Vector2, transform: Transform): Feature {
        val axis = transform.getInverseTransformedR(vector)
        axis.inverseRotate(rotation)
        if (axis.y > 0.0) {
            farthestAligned(axis)
            axis.rotate(rotation)
            axis.add(ellipseCenter)
            transform.transform(axis)
            return PointFeature(axis)
        }
        val p1 = transform.getTransformed(vertexLeft)
        val p2 = transform.getTransformed(vertexRight)
        val v1 = PointFeature(p1, 0)
        val v2 = PointFeature(p2, 1)
        return EdgeFeature(v1, v2, if (axis.x <= 0.0) v1 else v2, p1.to(p2), 0)
    }

    override fun project(vector: Vector2, transform: Transform): Interval {
        val farthest = getFarthestPoint(vector, transform)
        val opposite = getFarthestPoint(vector.getNegative(), transform)
        return Interval(opposite.dot(vector), farthest.dot(vector))
    }

    override fun computeAABB(transform: Transform, aabb: AABB) {
        val u = rotation.toVector()
        transform.transformR(u)
        val x2 = u.x * u.x
        val y2 = u.y * u.y
        val widthSquared = halfWidth * halfWidth
        val heightSquared = height * height
        val extentX = sqrt(x2 * widthSquared + y2 * heightSquared)
        val extentY = sqrt(y2 * widthSquared + x2 * heightSquared)
        val cx = transform.getTransformedX(ellipseCenter)
        val cy = transform.getTransformedY(ellipseCenter)
        var minX = cx - extentX
        var minY = cy - extentY
        var maxX = cx + extentX
        var maxY = cy + extentY
        if (u.y > 0.0) {
            if (u.x > 0.0) {
                maxX = transform.getTransformedX(vertexRight)
                minY = transform.getTransformedY(vertexLeft)
            } else {
                maxX = transform.getTransformedX(vertexLeft)
                maxY = transform.getTransformedY(vertexRight)
            }
        } else {
            if (u.x > 0.0) {
                minX = transform.getTransformedX(vertexLeft)
                minY = transform.getTransformedY(vertexRight)
            } else {
                minX = transform.getTransformedX(vertexRight)
                maxY = transform.getTransformedY(vertexLeft)
            }
        }
        aabb.set(AABB(minX, minY, maxX, maxY))
    }

    override fun createMass(density: Double): Mass {
        val mass = getArea() * density
        return Mass(center, mass, mass * (halfWidth * halfWidth + height * height) * INERTIA_CONSTANT)
    }
    override fun getArea(): Double = PI * halfWidth * height * 0.5

    override fun getRadius(center: Vector2): Double {
        if (halfWidth >= height) {
            return if (Segment.getLocation(center, vertexLeft, vertexRight) <= 0.0) maxDistanceEllipse(center)
                else maxDistanceVertices(center)
        }
        return maxDistanceHalfEllipse(center)
    }

    private fun maxDistanceVertices(point: Vector2): Double =
        sqrt(max(point.distanceSquared(vertexLeft), point.distanceSquared(vertexRight)))

    private fun maxDistanceEllipse(point: Vector2): Double {
        val local = point.difference(ellipseCenter).inverseRotate(rotation)
        return local.distance(Ellipse.getFarthestPointOnEllipse(halfWidth, height, local))
    }

    private fun maxDistanceHalfEllipse(point: Vector2): Double {
        val a = halfWidth
        val b = height
        val p = point.difference(ellipseCenter).inverseRotate(rotation)
        if (p.y < 0.0) return maxDistanceEllipse(point)
        if (p.x < 0.0) p.x = -p.x
        val ab = b * b - a * a
        val ax = a * p.x
        var top = (ab * ab).pow(1.0 / 3.0) - (ax * ax).pow(1.0 / 3.0)
        if (top < 0.0) return maxDistanceVertices(point)
        top = sqrt(top)
        val ey = top * top * top / b
        if (p.y > ey) return maxDistanceVertices(point)
        if (abs(p.x) < 1e-16) return max(b - p.y, maxDistanceVertices(point))
        val m = -(a * a).pow(1.0 / 3.0) * top / (b * p.x.pow(1.0 / 3.0))
        val a2 = a * a
        val b2 = b * b
        val m2 = m * m
        val qa = a2 * m2 + b2
        val qb = 2.0 * a2 * m * ey - 2.0 * a2 * m2 * p.x
        val qc = a2 * m2 * p.x * p.x - 2.0 * a2 * m * p.x * ey + a2 * ey * ey - b2 * a2
        val discriminant = qb * qb - 4.0 * qa * qc
        if (discriminant < 0.0) return maxDistanceVertices(point)
        val xmin = (-qb - sqrt(discriminant)) / (2.0 * qa)
        val farthest = Ellipse.getFarthestPointOnBoundedEllipse(xmin, 0.0, a, b, p)
        return max(farthest.distance(p), maxDistanceVertices(point))
    }

    override fun contains(point: Vector2, transform: Transform, inclusive: Boolean): Boolean {
        val local = transform.getInverseTransformed(point)
        local.inverseRotate(rotation, ellipseCenter)
        val x = local.x - ellipseCenter.x
        val y = local.y - ellipseCenter.y
        if (y < 0.0) return false
        val value = x * x / (halfWidth * halfWidth) + y * y / (height * height)
        return if (inclusive) value <= 1.0 else value < 1.0
    }

    override fun rotate(rotation: Rotation, x: Double, y: Double) {
        super.rotate(rotation, x, y)
        this.rotation.rotate(rotation)
        vertexLeft.rotate(rotation, x, y)
        vertexRight.rotate(rotation, x, y)
        ellipseCenter.rotate(rotation, x, y)
    }
    override fun translate(x: Double, y: Double) {
        super.translate(x, y)
        vertexLeft.add(x, y)
        vertexRight.add(x, y)
        ellipseCenter.add(x, y)
    }
    fun getRotationAngle(): Double = rotation.toRadians()
    fun getRotation(): Rotation = rotation.copy()
    fun getWidth(): Double = halfWidth * 2.0
    fun getHeight(): Double = height
    fun getHalfWidth(): Double = halfWidth
    fun getEllipseCenter(): Vector2 = ellipseCenter

    companion object { private val INERTIA_CONSTANT = PI / 8.0 - 8.0 / (9.0 * PI) }
}
