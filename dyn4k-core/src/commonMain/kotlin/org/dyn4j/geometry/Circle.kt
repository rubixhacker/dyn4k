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
import org.dyn4j.exception.ValueOutOfRangeException

open class Circle : AbstractShape, Convex {
    constructor(radius: Double) : super(radius) {
        if (radius <= 0.0) throw ValueOutOfRangeException("radius", radius, ValueOutOfRangeException.MUST_BE_GREATER_THAN, 0.0)
    }
    protected constructor(circle: Circle) : super(circle)

    override fun copy() = Circle(this)
    override fun getRadius(center: Vector2) = radius + center.distance(this.center)
    override fun toString() = "Circle[${super.toString()}]"
    override fun contains(point: Vector2, transform: Transform, inclusive: Boolean): Boolean {
        val fromPoint = transform.getTransformed(center)
        fromPoint.subtract(point)
        val distanceSquared = fromPoint.getMagnitudeSquared()
        val radiusSquared = radius * radius
        return if (inclusive) distanceSquared <= radiusSquared else distanceSquared < radiusSquared
    }
    override fun project(vector: Vector2, transform: Transform): Interval {
        val projectedCenter = transform.getTransformed(center).dot(vector)
        return Interval(projectedCenter - radius, projectedCenter + radius)
    }
    override fun getFarthestFeature(vector: Vector2, transform: Transform) =
        PointFeature(getFarthestPoint(vector, transform))
    override fun getFarthestPoint(vector: Vector2, transform: Transform): Vector2 {
        val axis = vector.getNormalized()
        val farthest = transform.getTransformed(center)
        farthest.x += radius * axis.x
        farthest.y += radius * axis.y
        return farthest
    }
    override fun getAxes(foci: Array<Vector2>?, transform: Transform): Array<Vector2>? = null
    override fun getFoci(transform: Transform): Array<Vector2> = arrayOf(transform.getTransformed(center))
    override fun createMass(density: Double): Mass {
        val squaredRadius = radius * radius
        val mass = density * PI * squaredRadius
        return Mass(center, mass, mass * squaredRadius * 0.5)
    }
    override fun getArea() = PI * radius * radius
    override fun computeAABB(transform: Transform, aabb: AABB) {
        val center = transform.getTransformed(this.center)
        aabb.set(AABB(center.x - radius, center.y - radius, center.x + radius, center.y + radius))
    }
}
