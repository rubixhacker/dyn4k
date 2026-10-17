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
import kotlin.math.sign
import kotlin.math.sqrt
import org.dyn4j.Epsilon
import org.dyn4j.JvmFieldBridge
import org.dyn4j.exception.NullElementException
import org.dyn4j.exception.ValueOutOfRangeException

open class Polygon : AbstractShape, Convex, Wound {
    @get:kotlin.jvm.JvmName("getVerticesField")
    @JvmFieldBridge protected val vertices: Array<Vector2>
    @get:kotlin.jvm.JvmName("getNormalsField")
    @JvmFieldBridge protected val normals: Array<Vector2>

    internal constructor(center: Vector2, radius: Double, vertices: Array<Vector2>, normals: Array<Vector2>) : super(center, radius) {
        this.vertices = vertices
        this.normals = normals
    }

    constructor(vararg vertices: Vector2?) : this(vertices, validatedCenter(vertices))

    private constructor(vertices: Array<out Vector2?>, center: Vector2) : super(center, rotationRadius(center, nonnullVertices(vertices))) {
        @Suppress("UNCHECKED_CAST")
        this.vertices = vertices as Array<Vector2>
        normals = edgeNormals(this.vertices)
    }

    protected constructor(polygon: Polygon) : super(polygon) {
        vertices = Array(polygon.vertices.size) { polygon.vertices[it].copy() }
        normals = Array(polygon.normals.size) { polygon.normals[it].copy() }
    }

    override fun copy() = Polygon(this)
    override fun toString() = "Polygon[${super.toString()}|Vertices={${vertices.joinToString(",")}}]"
    override fun getVertices() = vertices
    override fun getNormals() = normals
    override fun getVertexIterator(): MutableIterator<Vector2> = WoundIterator(vertices)
    override fun getNormalIterator(): MutableIterator<Vector2> = WoundIterator(normals)
    override fun getRadius(center: Vector2) = rotationRadius(center, vertices)

    override fun getAxes(foci: Array<Vector2>?, transform: Transform): Array<Vector2> {
        val axes = Array(vertices.size + (foci?.size ?: 0)) { Vector2() }
        for (index in vertices.indices) axes[index] = transform.getTransformedR(normals[index])
        if (foci != null) {
            for ((focusIndex, focus) in foci.withIndex()) {
                var closest = transform.getTransformed(vertices[0])
                var distance = focus.distanceSquared(closest)
                for (index in 1 until vertices.size) {
                    val point = transform.getTransformed(vertices[index])
                    val candidate = focus.distanceSquared(point)
                    if (candidate < distance) {
                        closest = point
                        distance = candidate
                    }
                }
                val axis = focus.to(closest)
                axis.normalize()
                axes[vertices.size + focusIndex] = axis
            }
        }
        return axes
    }
    override fun getFoci(transform: Transform): Array<Vector2>? = null

    override fun contains(point: Vector2, transform: Transform, inclusive: Boolean): Boolean {
        val local = transform.getInverseTransformed(point)
        var p1 = vertices.last()
        var p2 = vertices[0]
        var last = location(local, p1, p2)
        for (index in 0 until vertices.size - 1) {
            p1 = p2
            p2 = vertices[index + 1]
            if (inclusive && (local == p1 || local == p2)) return true
            val current = location(local, p1, p2)
            if (!inclusive && current == 0.0) return false
            if (last * current < 0.0) return false
            if (abs(current) > Epsilon.E) last = current
        }
        return true
    }

    override fun rotate(rotation: Rotation, x: Double, y: Double) {
        super.rotate(rotation, x, y)
        for (index in vertices.indices) {
            vertices[index].rotate(rotation, x, y)
            normals[index].rotate(rotation)
        }
    }
    override fun translate(x: Double, y: Double) {
        super.translate(x, y)
        for (vertex in vertices) vertex.add(x, y)
    }
    override fun project(vector: Vector2, transform: Transform): Interval {
        var minimum = vector.dot(transform.getTransformed(vertices[0]))
        var maximum = minimum
        for (index in 1 until vertices.size) {
            val value = vector.dot(transform.getTransformed(vertices[index]))
            if (value < minimum) minimum = value else if (value > maximum) maximum = value
        }
        return Interval(minimum, maximum)
    }
    override fun getFarthestFeature(vector: Vector2, transform: Transform): EdgeFeature {
        val local = transform.getInverseTransformedR(vector)
        val index = getFarthestVertexIndex(local)
        val count = vertices.size
        val maximum = transform.getTransformed(vertices[index].copy())
        val leftNormal = normals[if (index == 0) count - 1 else index - 1]
        val rightNormal = normals[index]
        val feature = PointFeature(maximum, index)
        if (leftNormal.dot(local) < rightNormal.dot(local)) {
            val leftIndex = if (index == count - 1) 0 else index + 1
            val left = transform.getTransformed(vertices[leftIndex])
            return EdgeFeature(feature, PointFeature(left, leftIndex), feature, maximum.to(left), index + 1)
        }
        val rightIndex = if (index == 0) count - 1 else index - 1
        val right = transform.getTransformed(vertices[rightIndex])
        return EdgeFeature(PointFeature(right, rightIndex), feature, feature, right.to(maximum), index)
    }
    override fun getFarthestPoint(vector: Vector2, transform: Transform): Vector2 =
        transform.getTransformed(vertices[getFarthestVertexIndex(transform.getInverseTransformedR(vector))])

    fun getFarthestVertexIndex(vector: Vector2): Int {
        var maxIndex = 0
        val count = vertices.size
        var maximum = vector.dot(vertices[0])
        var candidate = vector.dot(vertices[1])
        if (maximum < candidate) {
            do {
                maximum = candidate
                maxIndex++
                if (maxIndex + 1 >= count) break
                candidate = vector.dot(vertices[maxIndex + 1])
            } while (maximum < candidate)
        } else {
            candidate = vector.dot(vertices[count - 1])
            if (maximum < candidate) {
                maxIndex = count
                do {
                    maximum = candidate
                    maxIndex--
                    if (maxIndex <= 0) break
                    candidate = vector.dot(vertices[maxIndex - 1])
                } while (maximum <= candidate)
            }
        }
        return maxIndex
    }

    override fun createMass(density: Double): Mass {
        val average = averageCenter(vertices)
        val center = Vector2()
        var area = 0.0
        var inertia = 0.0
        var previous = vertices.last()
        for (current in vertices) {
            val p1 = previous.difference(average)
            val p2 = current.difference(average)
            val triangleArea = 0.5 * p1.cross(p2)
            area += triangleArea
            center.x += (p1.x + p2.x) * (1.0 / 3.0) * triangleArea
            center.y += (p1.y + p2.y) * (1.0 / 3.0) * triangleArea
            inertia += triangleArea * (p2.dot(p2) + p2.dot(p1) + p1.dot(p1))
            previous = current
        }
        val mass = density * area
        center.divide(area)
        val actualCenter = center.sum(average)
        inertia *= density / 6.0
        inertia -= mass * center.getMagnitudeSquared()
        return Mass(actualCenter, mass, inertia)
    }
    override fun getArea(): Double {
        val average = averageCenter(vertices)
        var area = 0.0
        var previous = vertices.last()
        for (current in vertices) {
            area += 0.5 * previous.difference(average).cross(current.difference(average))
            previous = current
        }
        return area
    }
    override fun computeAABB(transform: Transform, aabb: AABB) {
        val first = transform.getTransformed(vertices[0])
        var minX = first.x
        var minY = first.y
        var maxX = first.x
        var maxY = first.y
        for (index in 1 until vertices.size) {
            val x = transform.getTransformedX(vertices[index])
            val y = transform.getTransformedY(vertices[index])
            minX = min(minX, x)
            minY = min(minY, y)
            maxX = max(maxX, x)
            maxY = max(maxY, y)
        }
        aabb.set(AABB(minX, minY, maxX, maxY))
    }

    companion object {
        private fun validate(vertices: Array<out Vector2?>) {
            if (vertices.size < 3) throw ValueOutOfRangeException("vertices.length", vertices.size, ValueOutOfRangeException.MUST_BE_GREATER_THAN_OR_EQUAL_TO, 3)
            for (index in vertices.indices) {
                if (vertices[index] == null) throw NullElementException("vertices", index)
            }
            val points = nonnullVertices(vertices)
            var area = 0.0
            var windingSign = 0.0
            for (index in points.indices) {
                val p0 = points[if (index == 0) points.size - 1 else index - 1]
                val p1 = points[index]
                val p2 = points[if (index + 1 == points.size) 0 else index + 1]
                if (p1 == p2) throw IllegalArgumentException("A polygon cannot have coincident vertices")
                val cross = p0.to(p1).cross(p1.to(p2))
                val candidate = sign(cross)
                area += cross
                if (abs(cross) > Epsilon.E && windingSign != 0.0 && candidate != windingSign) throw IllegalArgumentException("A polygon must be convex")
                windingSign = candidate
            }
            if (abs(area) <= Epsilon.E) throw IllegalArgumentException("The polygon has zero or near zero area")
            if (area < 0.0) throw IllegalArgumentException("The polygon must have counter-clockwise winding")
        }
        private fun validatedCenter(vertices: Array<out Vector2?>): Vector2 {
            validate(vertices)
            return areaWeightedCenter(nonnullVertices(vertices))
        }
        @Suppress("UNCHECKED_CAST")
        private fun nonnullVertices(vertices: Array<out Vector2?>) = vertices as Array<Vector2>
        private fun averageCenter(vertices: Array<out Vector2>): Vector2 {
            val center = Vector2()
            for (point in vertices) center.add(point)
            return center.divide(vertices.size.toDouble())
        }
        private fun areaWeightedCenter(vertices: Array<out Vector2>): Vector2 {
            val average = averageCenter(vertices)
            val center = Vector2()
            var area = 0.0
            for (index in vertices.indices) {
                val p1 = vertices[index].difference(average)
                val p2 = vertices[(index + 1) % vertices.size].difference(average)
                val triangleArea = 0.5 * p1.cross(p2)
                area += triangleArea
                center.add(p1.add(p2).multiply(1.0 / 3.0).multiply(triangleArea))
            }
            if (abs(area) <= Epsilon.E) return vertices[0].copy()
            return center.divide(area).add(average)
        }
        private fun rotationRadius(center: Vector2, vertices: Array<out Vector2>): Double {
            var squared = 0.0
            for (point in vertices) squared = max(squared, center.distanceSquared(point))
            return sqrt(squared)
        }
        private fun edgeNormals(vertices: Array<Vector2>): Array<Vector2> = Array(vertices.size) { index ->
            vertices[index].to(vertices[(index + 1) % vertices.size]).left().also { it.normalize() }
        }
        private fun location(point: Vector2, p1: Vector2, p2: Vector2) =
            (p2.x - p1.x) * (point.y - p1.y) - (point.x - p1.x) * (p2.y - p1.y)
    }
}
