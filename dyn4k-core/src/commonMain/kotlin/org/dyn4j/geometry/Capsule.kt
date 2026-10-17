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
import kotlin.math.atan2
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sqrt
import org.dyn4j.Epsilon
import org.dyn4j.JvmFieldBridge
import org.dyn4j.exception.ValueOutOfRangeException

open class Capsule : AbstractShape, Convex {
    @get:kotlin.jvm.JvmName("getLengthField")
    @JvmFieldBridge protected val length: Double
    @get:kotlin.jvm.JvmName("getCapRadiusField")
    @JvmFieldBridge protected val capRadius: Double
    @get:kotlin.jvm.JvmName("getFociField")
    @JvmFieldBridge protected val foci: Array<Vector2>
    @get:kotlin.jvm.JvmName("getLocalXAxisField")
    @JvmFieldBridge protected val localXAxis: Vector2

    constructor(width: Double, height: Double) : super(max(width, height) * 0.5) {
        if (width <= 0.0) throw ValueOutOfRangeException("width", width, ValueOutOfRangeException.MUST_BE_GREATER_THAN, 0.0)
        if (height <= 0.0) throw ValueOutOfRangeException("height", height, ValueOutOfRangeException.MUST_BE_GREATER_THAN, 0.0)
        if (abs(width - height) < Epsilon.E) throw IllegalArgumentException("The width and height cannot be near equal - use a Circle instead.")
        val major = max(width, height)
        val minor = min(width, height)
        length = major
        capRadius = minor * 0.5
        val focus = (major - minor) * 0.5
        if (width < height) {
            foci = arrayOf(Vector2(0.0, -focus), Vector2(0.0, focus))
            localXAxis = Vector2(0.0, 1.0)
        } else {
            foci = arrayOf(Vector2(-focus, 0.0), Vector2(focus, 0.0))
            localXAxis = Vector2(1.0, 0.0)
        }
    }

    protected constructor(capsule: Capsule) : super(capsule) {
        capRadius = capsule.capRadius
        foci = arrayOf(capsule.foci[0].copy(), capsule.foci[1].copy())
        length = capsule.length
        localXAxis = capsule.localXAxis.copy()
    }

    override fun copy() = Capsule(this)
    override fun toString() = "Capsule[${super.toString()}|Width=$length|CapRadius=$capRadius]"

    override fun getAxes(foci: Array<Vector2>?, transform: Transform): Array<Vector2> {
        val axes = Array(2 + (foci?.size ?: 0)) { Vector2() }
        axes[0] = transform.getTransformedR(localXAxis)
        axes[1] = transform.getTransformedR(localXAxis.getRightHandOrthogonalVector())
        if (foci != null) {
            val focus1 = transform.getTransformed(this.foci[0])
            val focus2 = transform.getTransformed(this.foci[1])
            for ((index, focus) in foci.withIndex()) {
                val axis = if (focus1.distanceSquared(focus) < focus2.distanceSquared(focus)) focus1.to(focus) else focus2.to(focus)
                axis.normalize()
                axes[index + 2] = axis
            }
        }
        return axes
    }

    override fun getFoci(transform: Transform) = arrayOf(transform.getTransformed(foci[0]), transform.getTransformed(foci[1]))

    override fun getFarthestPoint(vector: Vector2, transform: Transform): Vector2 {
        vector.normalize()
        return Segment.getFarthestPoint(foci[0], foci[1], vector, transform).add(vector.product(capRadius))
    }

    override fun getFarthestFeature(vector: Vector2, transform: Transform): Feature {
        val localAxis = transform.getInverseTransformedR(vector)
        val normal = localXAxis.getLeftHandOrthogonalVector()
        val threshold = localAxis.dot(localAxis) * EDGE_FEATURE_SELECTION_CRITERIA
        val projection = localAxis.dot(normal)
        if (abs(projection) < threshold) return PointFeature(getFarthestPoint(vector, transform))
        val offset = normal.multiply(capRadius)
        val expansion = localXAxis.product(length * 0.5 * EDGE_FEATURE_EXPANSION_FACTOR)
        val p1 = if (projection > 0.0) foci[0].sum(offset).subtract(expansion) else foci[0].difference(offset).subtract(expansion)
        val p2 = if (projection > 0.0) foci[1].sum(offset).add(expansion) else foci[1].difference(offset).add(expansion)
        return Segment.getFarthestFeature(p1, p2, vector, transform)
    }

    override fun project(vector: Vector2, transform: Transform): Interval {
        val farthest = getFarthestPoint(vector, transform)
        val projection = transform.getTransformed(center).dot(vector)
        return Interval(2.0 * projection - farthest.dot(vector), farthest.dot(vector))
    }

    override fun computeAABB(transform: Transform, aabb: AABB) {
        val x = getFarthestPoint(Vector2.X_AXIS, transform)
        val cx = transform.getTransformedX(center)
        val y = getFarthestPoint(Vector2.Y_AXIS, transform)
        val cy = transform.getTransformedY(center)
        aabb.set(AABB(2.0 * cx - x.x, 2.0 * cy - y.y, x.x, y.y))
    }

    override fun createMass(density: Double): Mass {
        val h = capRadius * 2.0
        val w = length - h
        val r2 = capRadius * capRadius
        val rectangularMass = density * w * h
        val circularMass = density * r2 * PI
        val mass = rectangularMass + circularMass
        val d = w * 0.5
        val circularInertia = 0.5 * circularMass * r2 + circularMass * d * d
        val rectangularInertia = rectangularMass * (h * h + w * w) / 12.0
        return Mass(center, mass, rectangularInertia + circularInertia)
    }

    override fun getArea(): Double {
        val h = capRadius * 2.0
        return (length - h) * h + capRadius * capRadius * PI
    }

    override fun getRadius(center: Vector2): Double =
        sqrt(max(center.distanceSquared(foci[0]), center.distanceSquared(foci[1]))) + capRadius

    override fun contains(point: Vector2, transform: Transform, inclusive: Boolean): Boolean {
        val closest = Segment.getPointOnSegmentClosestToPoint(point, transform.getTransformed(foci[0]), transform.getTransformed(foci[1]))
        val distance = closest.distanceSquared(point)
        val radiusSquared = capRadius * capRadius
        return if (inclusive) distance <= radiusSquared else distance < radiusSquared
    }

    override fun rotate(rotation: Rotation, x: Double, y: Double) {
        super.rotate(rotation, x, y)
        foci[0].rotate(rotation, x, y)
        foci[1].rotate(rotation, x, y)
        localXAxis.rotate(rotation)
    }
    override fun translate(x: Double, y: Double) {
        super.translate(x, y)
        foci[0].add(x, y)
        foci[1].add(x, y)
    }
    fun getRotationAngle(): Double = atan2(localXAxis.y, localXAxis.x)
    fun getRotation(): Rotation = Rotation.fromComponentsUnchecked(localXAxis.x, localXAxis.y)
    fun getLength(): Double = length
    fun getCapRadius(): Double = capRadius

    companion object {
        const val EDGE_FEATURE_SELECTION_CRITERIA = 0.98
        const val EDGE_FEATURE_EXPANSION_FACTOR = 0.1
    }
}
