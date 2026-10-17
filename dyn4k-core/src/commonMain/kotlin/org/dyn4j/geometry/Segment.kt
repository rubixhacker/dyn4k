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
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sqrt
import org.dyn4j.Epsilon
import org.dyn4j.JvmFieldBridge
import org.dyn4j.exception.ArgumentNullException

open class Segment : AbstractShape, Convex, Wound {
    @get:kotlin.jvm.JvmName("getVerticesField")
    @JvmFieldBridge protected val vertices: Array<Vector2>
    @get:kotlin.jvm.JvmName("getNormalsField")
    @JvmFieldBridge protected val normals: Array<Vector2>
    @get:kotlin.jvm.JvmName("getLengthField")
    @set:kotlin.jvm.JvmName("setLengthField")
    @JvmFieldBridge protected var length: Double

    constructor(point1: Vector2?, point2: Vector2?) : super(averageCenter(point1, point2), point1!!.distance(point2!!) * 0.5) {
        vertices = arrayOf(point1, point2)
        val edge = point1.to(point2)
        normals = arrayOf(edge.copy().also { it.normalize() }, edge.right().also { it.normalize() })
        length = point1.distance(point2)
    }
    protected constructor(segment: Segment) : super(segment) {
        vertices = Array(segment.vertices.size) { segment.vertices[it].copy() }
        normals = Array(segment.normals.size) { segment.normals[it].copy() }
        length = segment.length
    }

    override fun copy() = Segment(this)
    override fun toString() = "Segment[${super.toString()}|Length=$length]"
    override fun getVertices() = vertices
    override fun getNormals() = normals
    override fun getVertexIterator(): MutableIterator<Vector2> = WoundIterator(vertices)
    override fun getNormalIterator(): MutableIterator<Vector2> = WoundIterator(normals)
    override fun getRadius(center: Vector2) = sqrt(max(center.distanceSquared(vertices[0]), center.distanceSquared(vertices[1])))
    fun getPoint1() = vertices[0]
    fun getPoint2() = vertices[1]
    fun getLength() = length
    fun getPointOnLineClosestToPoint(point: Vector2) = getPointOnLineClosestToPoint(point, vertices[0], vertices[1])
    fun getPointOnSegmentClosestToPoint(point: Vector2) = getPointOnSegmentClosestToPoint(point, vertices[0], vertices[1])
    fun getLineIntersection(segment: Segment) = getLineIntersection(vertices[0], vertices[1], segment.vertices[0], segment.vertices[1])
    fun getSegmentIntersection(segment: Segment) = getSegmentIntersection(vertices[0], vertices[1], segment.vertices[0], segment.vertices[1], true)

    override fun getAxes(foci: Array<Vector2>?, transform: Transform): Array<Vector2> {
        val axes = Array(2 + (foci?.size ?: 0)) { Vector2() }
        val p1 = transform.getTransformed(vertices[0])
        val p2 = transform.getTransformed(vertices[1])
        axes[0] = transform.getTransformedR(normals[1])
        axes[1] = transform.getTransformedR(normals[0])
        if (foci != null) {
            for ((index, focus) in foci.withIndex()) {
                val axis = if (p1.distanceSquared(focus) < p2.distanceSquared(focus)) p1.to(focus) else p2.to(focus)
                axis.normalize()
                axes[index + 2] = axis
            }
        }
        return axes
    }
    override fun getFoci(transform: Transform): Array<Vector2>? = null
    override fun contains(point: Vector2, transform: Transform, inclusive: Boolean): Boolean {
        if (!inclusive) return false
        val local = transform.getInverseTransformed(point)
        val p1 = vertices[0]
        val p2 = vertices[1]
        if (abs(getLocation(local, p1, p2)) <= Epsilon.E) {
            val squaredLength = p1.distanceSquared(p2)
            return local.distanceSquared(p1) <= squaredLength && local.distanceSquared(p2) <= squaredLength
        }
        return false
    }
    fun contains(point: Vector2, transform: Transform, radius: Double): Boolean {
        if (radius <= 0.0) return contains(point, transform)
        val local = transform.getInverseTransformed(point)
        val squaredRadius = radius * radius
        if (vertices[0].distanceSquared(local) <= squaredRadius) return true
        if (vertices[1].distanceSquared(local) <= squaredRadius) return true
        val edge = vertices[0].to(vertices[1])
        val p1 = vertices[0].to(local)
        val p2 = vertices[1].to(local)
        return edge.dot(p1) > 0.0 && -edge.dot(p2) > 0.0 &&
            p1.project(edge.getRightHandOrthogonalVector()).getMagnitudeSquared() <= squaredRadius
    }
    override fun project(vector: Vector2, transform: Transform): Interval {
        val p1 = transform.getTransformed(vertices[0])
        val p2 = transform.getTransformed(vertices[1])
        val first = vector.dot(p1)
        val second = vector.dot(p2)
        return Interval(min(first, second), max(first, second))
    }
    override fun getFarthestPoint(vector: Vector2, transform: Transform) =
        getFarthestPoint(vertices[0], vertices[1], vector, transform)
    override fun getFarthestFeature(vector: Vector2, transform: Transform) =
        getFarthestFeature(vertices[0], vertices[1], vector, transform)
    override fun rotate(rotation: Rotation, x: Double, y: Double) {
        super.rotate(rotation, x, y)
        vertices[0].rotate(rotation, x, y)
        vertices[1].rotate(rotation, x, y)
        normals[0].rotate(rotation)
        normals[1].rotate(rotation)
    }
    override fun translate(x: Double, y: Double) {
        super.translate(x, y)
        vertices[0].add(x, y)
        vertices[1].add(x, y)
    }
    override fun createMass(density: Double): Mass {
        val mass = density * length
        return Mass(center, mass, length * length * mass / 12.0)
    }
    override fun getArea() = 0.0
    override fun createAABB(transform: Transform): AABB {
        val aabb = AABB(0.0, 0.0, 0.0, 0.0)
        computeAABB(transform, aabb)
        return aabb
    }
    override fun computeAABB(transform: Transform, aabb: AABB) {
        val p1 = transform.getTransformed(vertices[0])
        val p2 = transform.getTransformed(vertices[1])
        aabb.set(AABB(min(p1.x, p2.x), min(p1.y, p2.y), max(p1.x, p2.x), max(p1.y, p2.y)))
    }
    fun getEdgeVector() = vertices[0].to(vertices[1]).also { it.normalize() }

    companion object {
        private fun averageCenter(point1: Vector2?, point2: Vector2?): Vector2 {
            if (point1 == null) throw ArgumentNullException("point1")
            if (point2 == null) throw ArgumentNullException("point2")
            if (point1 == point2) throw IllegalArgumentException("point1 and point2 cannot be the same point")
            return Vector2().add(point1).add(point2).divide(2.0)
        }
     fun getLocation(point: Vector2, linePoint1: Vector2, linePoint2: Vector2) =
            (linePoint2.x - linePoint1.x) * (point.y - linePoint1.y) -
                (point.x - linePoint1.x) * (linePoint2.y - linePoint1.y)

     fun getPointOnLineClosestToPoint(point: Vector2, linePoint1: Vector2, linePoint2: Vector2): Vector2 {
            val fromStart = point.difference(linePoint1)
            val line = linePoint2.difference(linePoint1)
            val squaredLength = line.dot(line)
            if (squaredLength <= Epsilon.E) return linePoint1.copy()
            return line.multiply(fromStart.dot(line) / squaredLength).add(linePoint1)
        }
     fun getPointOnSegmentClosestToPoint(point: Vector2, linePoint1: Vector2, linePoint2: Vector2): Vector2 {
            val fromStart = point.difference(linePoint1)
            val line = linePoint2.difference(linePoint1)
            val squaredLength = line.dot(line)
            val projected = fromStart.dot(line)
            if (squaredLength <= Epsilon.E) return linePoint1.copy()
            return line.multiply(Interval.clamp(projected / squaredLength, 0.0, 1.0)).add(linePoint1)
        }
     fun getLineIntersection(ap1: Vector2, ap2: Vector2, bp1: Vector2, bp2: Vector2): Vector2? {
            val a = ap1.to(ap2)
            val b = bp1.to(bp2)
            val cross = b.cross(a)
            if (abs(cross) <= Epsilon.E) return null
            val numerator = ap1.difference(bp1).cross(a)
            if (abs(numerator) <= Epsilon.E) return null
            return b.product(numerator / cross).add(bp1)
        }
     fun getSegmentIntersection(ap1: Vector2, ap2: Vector2, bp1: Vector2, bp2: Vector2): Vector2? =
            getSegmentIntersection(ap1, ap2, bp1, bp2, true)
     fun getSegmentIntersection(ap1: Vector2, ap2: Vector2, bp1: Vector2, bp2: Vector2, inclusive: Boolean): Vector2? {
            val a = ap1.to(ap2)
            val b = bp1.to(bp2)
            val cross = b.cross(a)
            if (abs(cross) <= Epsilon.E) return null
            val numerator = ap1.difference(bp1).cross(a)
            if (abs(numerator) <= Epsilon.E) return null
            val tb = numerator / cross
            if (inclusive) {
                if (tb < 0.0 || tb > 1.0) return null
            } else if (tb <= 0.0 || tb >= 1.0) return null
            val intersection = b.product(tb).add(bp1)
            val ta = intersection.difference(ap1).dot(a) / a.dot(a)
            if (inclusive) {
                if (ta < 0.0 || ta > 1.0) return null
            } else if (ta <= 0.0 || ta >= 1.0) return null
            return intersection
        }
     fun getFarthestFeature(v1: Vector2, v2: Vector2, vector: Vector2, transform: Transform): EdgeFeature {
            val p1 = transform.getTransformed(v1)
            val p2 = transform.getTransformed(v2)
            val index = if (vector.dot(p1) >= vector.dot(p2)) 0 else 1
            val maximum = if (index == 0) p1 else p2
            val vertex1 = PointFeature(p1, 0)
            val vertex2 = PointFeature(p2, 1)
            val maxFeature = PointFeature(maximum, index)
            return if (p1.to(p2).right().dot(vector) > 0.0)
                EdgeFeature(vertex2, vertex1, maxFeature, p2.to(p1), 0)
            else EdgeFeature(vertex1, vertex2, maxFeature, p1.to(p2), 0)
        }
     fun getFarthestPoint(v1: Vector2, v2: Vector2, vector: Vector2, transform: Transform): Vector2 {
            val p1 = transform.getTransformed(v1)
            val p2 = transform.getTransformed(v2)
            return if (vector.dot(p1) >= vector.dot(p2)) p1 else p2
        }
    }
}
