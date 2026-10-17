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
import kotlin.math.cos
import kotlin.math.max
import kotlin.math.sin
import kotlin.math.sqrt
import org.dyn4j.Epsilon
import org.dyn4j.exception.EmptyCollectionException
import org.dyn4j.exception.ValueOutOfRangeException
import org.dyn4j.exception.NullElementException
import org.dyn4j.exception.ArgumentNullException

class Geometry {
    companion object {
        const val TWO_PI = 2.0 * PI
        const val INV_3 = 1.0 / 3.0
     val INV_SQRT_3 = 1.0 / sqrt(3.0)

     fun getWinding(points: List<Vector2?>?): Double {
            if (points == null) throw ArgumentNullException("points")
            if (points.size < 2) throw ValueOutOfRangeException("points.size", points.size, ValueOutOfRangeException.MUST_BE_GREATER_THAN_OR_EQUAL_TO, 2)
            return winding(points)
        }
     fun getWinding(vararg points: Vector2?): Double {
            if (points.size < 2) throw ValueOutOfRangeException("points.length", points.size, ValueOutOfRangeException.MUST_BE_GREATER_THAN_OR_EQUAL_TO, 2)
            return winding(points.asList())
        }
        private fun winding(points: List<Vector2?>): Double {
            var area = 0.0
            for (index in points.indices) {
                val next = if (index + 1 == points.size) 0 else index + 1
                val p1 = points[index] ?: throw NullElementException("points", index)
                val p2 = points[next] ?: throw NullElementException("points", next)
                area += p1.cross(p2)
            }
            return area
        }
     fun reverseWinding(vararg points: Vector2?) {
            @Suppress("UNCHECKED_CAST") val mutable = points as Array<Vector2?>
            var left = 0
            var right = mutable.lastIndex
            while (left < right) {
                val temporary = mutable[left]
                mutable[left++] = mutable[right]
                mutable[right--] = temporary
            }
        }
     fun reverseWinding(points: MutableList<Vector2?>?) {
            if (points == null) throw ArgumentNullException("points")
            points.reverse()
        }
     fun getAverageCenter(points: List<Vector2?>?): Vector2 {
            if (points == null) throw ArgumentNullException("points")
            return averageCenter(points)
        }
     fun getAverageCenter(vararg points: Vector2?): Vector2 = averageCenter(points.asList())
        private fun averageCenter(points: List<Vector2?>): Vector2 {
            if (points.isEmpty()) throw EmptyCollectionException("points")
            if (points.size == 1) return (points[0] ?: throw NullElementException("points", 0)).copy()
            val center = Vector2()
            for ((index, point) in points.withIndex()) center.add(point ?: throw NullElementException("points", index))
            return center.divide(points.size.toDouble())
        }
     fun getAreaWeightedCenter(points: List<Vector2?>?): Vector2 {
            if (points == null) throw ArgumentNullException("points")
            return areaWeightedCenter(points)
        }
     fun getAreaWeightedCenter(vararg points: Vector2?): Vector2 = areaWeightedCenter(points.asList())
        private fun areaWeightedCenter(points: List<Vector2?>): Vector2 {
            val average = averageCenter(points)
            val center = Vector2()
            var area = 0.0
            for (index in points.indices) {
                val p1 = points[index]!!.difference(average)
                val p2 = points[if (index + 1 < points.size) index + 1 else 0]!!.difference(average)
                val triangleArea = 0.5 * p1.cross(p2)
                area += triangleArea
                center.add(p1.add(p2).multiply(INV_3).multiply(triangleArea))
            }
            if (abs(area) <= Epsilon.E) return points[0]!!.copy()
            return center.divide(area).add(average)
        }
     fun getRotationRadius(vertices: Array<out Vector2?>?): Double = getRotationRadius(Vector2(), vertices)
     fun getRotationRadius(center: Vector2?, vertices: Array<out Vector2?>?): Double {
            if (vertices == null) return 0.0
            val origin = center ?: Vector2()
            var radiusSquared = 0.0
            for (vertex in vertices) if (vertex != null) radiusSquared = max(radiusSquared, origin.distanceSquared(vertex))
            return sqrt(radiusSquared)
        }
     fun getCounterClockwiseEdgeNormals(vertices: Array<out Vector2?>?): Array<Vector2>? {
            if (vertices == null || vertices.isEmpty()) return null
            return Array(vertices.size) { index ->
                val current = vertices[index]!!
                val next = vertices[if (index + 1 == vertices.size) 0 else index + 1]!!
                current.to(next).left().also { it.normalize() }
            }
        }

     fun createUnitCirclePolygon(count: Int, radius: Double) = createPolygonalCircle(count, radius, 0.0)
     fun createUnitCirclePolygon(count: Int, radius: Double, theta: Double) = createPolygonalCircle(count, radius, theta)
     fun createPolygonalCircle(count: Int, radius: Double) = createPolygonalCircle(count, radius, 0.0)
     fun createPolygonalCircle(count: Int, radius: Double, theta: Double): Polygon {
            if (count < 3) throw ValueOutOfRangeException("count", count, ValueOutOfRangeException.MUST_BE_GREATER_THAN_OR_EQUAL_TO, 3)
            if (radius <= 0.0) throw ValueOutOfRangeException("radius", radius, ValueOutOfRangeException.MUST_BE_GREATER_THAN, 0.0)
            val step = TWO_PI / count
            val cosine = cos(step)
            val sine = sin(step)
            var x = radius
            var y = 0.0
            if (theta != 0.0) {
                x = radius * cos(theta)
                y = radius * sin(theta)
            }
            val vertices = Array(count) {
                val vertex = Vector2(x, y)
                val previousX = x
                x = cosine * x - sine * y
                y = sine * previousX + cosine * y
                vertex
            }
            return Polygon(*vertices)
        }
     fun createPolygonalSlice(count: Int, radius: Double, theta: Double): Polygon {
            if (count < 1) throw ValueOutOfRangeException("count", count, ValueOutOfRangeException.MUST_BE_GREATER_THAN_OR_EQUAL_TO, 1)
            if (radius <= 0.0) throw ValueOutOfRangeException("radius", radius, ValueOutOfRangeException.MUST_BE_GREATER_THAN, 0.0)
            if (theta <= 0.0) throw ValueOutOfRangeException("theta", theta, ValueOutOfRangeException.MUST_BE_GREATER_THAN, 0.0)
            val increment = theta / (count + 1)
            val vertices = Array(count + 3) { Vector2() }
            val cosine = cos(increment)
            val sine = sin(increment)
            var x = radius * cos(-theta * 0.5)
            var y = radius * sin(-theta * 0.5)
            vertices[0] = Vector2(x, y)
            vertices[count + 1] = Vector2(x, -y)
            for (index in 1..count) {
                val previousX = x
                x = cosine * x - sine * y
                y = sine * previousX + cosine * y
                vertices[index] = Vector2(x, y)
            }
            vertices[count + 2] = Vector2()
            return Polygon(*vertices)
        }
     fun createPolygonalSliceAtOrigin(count: Int, radius: Double, theta: Double): Polygon {
            val polygon = createPolygonalSlice(count, radius, theta)
            val center = polygon.getCenter()
            polygon.translate(-center.x, -center.y)
            return polygon
        }
     fun createPolygonalEllipse(count: Int, width: Double, height: Double): Polygon {
            if (count < 4) throw ValueOutOfRangeException("count", count, ValueOutOfRangeException.MUST_BE_GREATER_THAN_OR_EQUAL_TO, 4)
            if (width <= 0.0) throw ValueOutOfRangeException("width", width, ValueOutOfRangeException.MUST_BE_GREATER_THAN, 0.0)
            if (height <= 0.0) throw ValueOutOfRangeException("height", height, ValueOutOfRangeException.MUST_BE_GREATER_THAN, 0.0)
            val a = width * 0.5
            val b = height * 0.5
            val halfCount = count / 2
            val increment = PI / halfCount
            val vertices = Array(halfCount * 2) { Vector2() }
            var position = 0
            for (index in 0..halfCount) {
                val angle = increment * index
                val x = a * cos(angle)
                val y = b * sin(angle)
                if (index > 0) vertices[vertices.size - position] = Vector2(x, -y)
                vertices[position++] = Vector2(x, y)
            }
            return Polygon(*vertices)
        }
     fun createPolygonalHalfEllipse(count: Int, width: Double, height: Double): Polygon {
            if (count < 4) throw ValueOutOfRangeException("count", count, ValueOutOfRangeException.MUST_BE_GREATER_THAN_OR_EQUAL_TO, 4)
            if (width <= 0.0) throw ValueOutOfRangeException("width", width, ValueOutOfRangeException.MUST_BE_GREATER_THAN, 0.0)
            if (height <= 0.0) throw ValueOutOfRangeException("height", height, ValueOutOfRangeException.MUST_BE_GREATER_THAN, 0.0)
            val a = width * 0.5
            val b = height * 0.5
            val increment = PI / (count + 1)
            val vertices = Array(count + 2) { Vector2() }
            vertices[0] = Vector2(a, 0.0)
            vertices[count + 1] = Vector2(-a, 0.0)
            for (index in 1..count) {
                val angle = increment * index
                vertices[index] = Vector2(a * cos(angle), b * sin(angle))
            }
            return Polygon(*vertices)
        }
     fun createPolygonalHalfEllipseAtOrigin(count: Int, width: Double, height: Double): Polygon {
            val polygon = createPolygonalHalfEllipse(count, width, height)
            val center = polygon.getCenter()
            polygon.translate(-center.x, -center.y)
            return polygon
        }
     fun createPolygonalCapsule(count: Int, width: Double, height: Double): Polygon {
            if (count < 1) throw ValueOutOfRangeException("count", count, ValueOutOfRangeException.MUST_BE_GREATER_THAN_OR_EQUAL_TO, 1)
            if (width <= 0.0) throw ValueOutOfRangeException("width", width, ValueOutOfRangeException.MUST_BE_GREATER_THAN, 0.0)
            if (height <= 0.0) throw ValueOutOfRangeException("height", height, ValueOutOfRangeException.MUST_BE_GREATER_THAN, 0.0)
            if (abs(width - height) < Epsilon.E) return createPolygonalCircle(count, width)
            val increment = PI / (count + 1)
            val vertices = Array(4 + 2 * count) { Vector2() }
            val cosine = cos(increment)
            val sine = sin(increment)
            val vertical = width < height
            val major = if (vertical) height else width
            val minor = if (vertical) width else height
            val capRadius = minor * 0.5
            val offset = major * 0.5 - capRadius
            val ox = if (vertical) 0.0 else offset
            val oy = if (vertical) offset else 0.0
            var position = 0
            var angleOffset = if (vertical) 0.0 else PI * 0.5
            var x = capRadius * cos(increment - angleOffset)
            var y = capRadius * sin(increment - angleOffset)
            repeat(count) {
                vertices[position++] = Vector2(x + ox, y + oy)
                val previousX = x
                x = cosine * x - sine * y
                y = sine * previousX + cosine * y
            }
            if (vertical) {
                vertices[position++] = Vector2(-capRadius, oy)
                vertices[position++] = Vector2(-capRadius, -oy)
            } else {
                vertices[position++] = Vector2(ox, capRadius)
                vertices[position++] = Vector2(-ox, capRadius)
            }
            angleOffset = if (vertical) PI else PI * 0.5
            x = capRadius * cos(increment + angleOffset)
            y = capRadius * sin(increment + angleOffset)
            repeat(count) {
                vertices[position++] = Vector2(x - ox, y - oy)
                val previousX = x
                x = cosine * x - sine * y
                y = sine * previousX + cosine * y
            }
            if (vertical) {
                vertices[position++] = Vector2(capRadius, -oy)
                vertices[position] = Vector2(capRadius, oy)
            } else {
                vertices[position++] = Vector2(-ox, -capRadius)
                vertices[position] = Vector2(ox, -capRadius)
            }
            return Polygon(*vertices)
        }
     fun cleanse(points: List<Vector2?>?): List<Vector2> {
            if (points == null) throw ArgumentNullException("points")
            if (points.isEmpty()) {
                @Suppress("UNCHECKED_CAST")
                return points as List<Vector2>
            }
            val result = mutableListOf<Vector2>()
            var winding = 0.0
            for (index in points.indices) {
                val previousIndex = if (index == 0) points.lastIndex else index - 1
                val nextIndex = if (index == points.lastIndex) 0 else index + 1
                val point = points[index] ?: throw NullElementException("points", index)
                val previous = points[previousIndex] ?: throw NullElementException("points", previousIndex)
                val next = points[nextIndex] ?: throw NullElementException("points", nextIndex)
                if (point.difference(next).isZero()) continue
                val incoming = previous.to(point)
                val outgoing = point.to(next)
                if (!incoming.isZero() && abs(incoming.cross(outgoing)) <= Epsilon.E) continue
                winding += point.cross(next)
                result.add(point)
            }
            if (winding < 0.0) result.reverse()
            return result
        }
     fun cleanse(vararg points: Vector2?): Array<Vector2> = cleanse(points.asList()).toTypedArray()

     fun flipAlongTheXAxis(polygon: Polygon?): Polygon = flip(polygon, Vector2.X_AXIS, null)
     fun flipAlongTheYAxis(polygon: Polygon?): Polygon = flip(polygon, Vector2.Y_AXIS, null)
     fun flipAlongTheXAxis(polygon: Polygon?, point: Vector2?): Polygon = flip(polygon, Vector2.X_AXIS, point)
     fun flipAlongTheYAxis(polygon: Polygon?, point: Vector2?): Polygon = flip(polygon, Vector2.Y_AXIS, point)
     fun flip(polygon: Polygon?, axis: Vector2?): Polygon = flip(polygon, axis, null)
     fun flip(polygon: Polygon?, axis: Vector2?, point: Vector2?): Polygon {
            if (polygon == null) throw ArgumentNullException("polygon")
            if (axis == null) throw ArgumentNullException("axis")
            if (axis.isZero()) throw IllegalArgumentException("The axis cannot be a zero vector")
            val origin = point ?: polygon.getCenter()
            axis.normalize()
            val vertices = Array(polygon.getVertices().size) { index ->
                val local = polygon.getVertices()[index].difference(origin)
                val projection = axis.product(local.dot(axis))
                projection.add(projection.x - local.x, projection.y - local.y).add(origin)
            }
            if (getWinding(*vertices) < 0.0) vertices.reverse()
            return Polygon(*vertices)
        }
     fun <E> minkowskiSum(convex1: E?, convex2: E?): Polygon where E : Wound, E : Convex {
            if (convex1 == null) throw ArgumentNullException("convex1")
            if (convex2 == null) throw ArgumentNullException("convex2")
            val first = convex1.getVertices()
            val second = convex2.getVertices()
            if (convex1 is Segment && convex2 is Segment && first[0].to(first[1]).cross(second[0].to(second[1])) <= Epsilon.E)
                throw IllegalArgumentException("Two segments were given and they are colinear")
            val firstCount = first.size
            val secondCount = second.size
            var i = first.indices.minWithOrNull(compareBy<Int> { first[it].y }.thenBy { first[it].x })!!
            var j = second.indices.minWithOrNull(compareBy<Int> { second[it].y }.thenBy { second[it].x })!!
            val endI = firstCount + i
            val endJ = secondCount + j
            val vertices = mutableListOf<Vector2>()
            while (i < endI || j < endJ) {
                val start1 = first[i % firstCount]
                val end1 = first[(i + 1) % firstCount]
                val start2 = second[j % secondCount]
                val end2 = second[(j + 1) % secondCount]
                vertices.add(start1.sum(start2))
                var cross = start1.to(end1).cross(start2.to(end2))
                if (abs(cross) <= Epsilon.E) cross = 0.0
                if (cross > 0.0) i++ else if (cross < 0.0) j++ else { i++; j++ }
            }
            return Polygon(*vertices.toTypedArray())
        }
     fun minkowskiSum(circle: Circle?, polygon: Polygon?, count: Int): Polygon =
            minkowskiSum(polygon, circle, count)
     fun minkowskiSum(polygon: Polygon?, circle: Circle?, count: Int): Polygon {
            if (circle == null) throw ArgumentNullException("circle")
            return minkowskiSum(polygon, circle.getRadius(), count)
        }
     fun minkowskiSum(polygon: Polygon?, radius: Double, count: Int): Polygon {
            if (polygon == null) throw ArgumentNullException("polygon")
            if (radius <= 0.0) throw ValueOutOfRangeException("radius", radius, ValueOutOfRangeException.MUST_BE_GREATER_THAN, 0.0)
            if (count <= 0) throw ValueOutOfRangeException("count", count, ValueOutOfRangeException.MUST_BE_GREATER_THAN, 0)
            val vertices = polygon.getVertices()
            val normals = polygon.getNormals()
            val size = vertices.size
            val result = Array(size * (count + 2)) { Vector2() }
            var position = 0
            for (index in 0 until size) {
                val v1 = vertices[index]
                val v2 = vertices[if (index + 1 == size) 0 else index + 1]
                val normal = normals[index]
                val shifted1 = normal.product(radius).add(v1)
                val shifted2 = normal.product(radius).add(v2)
                val previous = if (index == 0) v1.to(normals[size - 1].product(radius).add(v1))
                    else v1.to(result[position - 1])
                val current = v1.to(shifted1)
                val theta = previous.getAngleBetween(current)
                val increment = theta / (count + 1)
                val cosine = cos(increment)
                val sine = sin(increment)
                var startAngle = Vector2.X_AXIS.getAngleBetween(normals[if (index == 0) size - 1 else index - 1])
                if (startAngle < 0.0) startAngle += TWO_PI
                var x = radius * cos(startAngle)
                var y = radius * sin(startAngle)
                repeat(count) {
                    val previousX = x
                    x = cosine * x - sine * y
                    y = sine * previousX + cosine * y
                    result[position++] = Vector2(x, y).add(v1)
                }
                result[position++] = shifted1
                result[position++] = shifted2
            }
            return Polygon(*result)
        }
        private fun checkedScale(scale: Double) {
            if (scale <= 0.0) throw ValueOutOfRangeException("scale", scale, ValueOutOfRangeException.MUST_BE_GREATER_THAN, 0.0)
        }
     fun scale(circle: Circle?, scale: Double): Circle {
            if (circle == null) throw ArgumentNullException("circle")
            checkedScale(scale)
            return Circle(circle.getRadius() * scale)
        }
     fun scale(capsule: Capsule?, scale: Double): Capsule {
            if (capsule == null) throw ArgumentNullException("circle")
            checkedScale(scale)
            return Capsule(capsule.getLength() * scale, capsule.getCapRadius() * 2.0 * scale)
        }
     fun scale(ellipse: Ellipse?, scale: Double): Ellipse {
            if (ellipse == null) throw ArgumentNullException("circle")
            checkedScale(scale)
            return Ellipse(ellipse.getWidth() * scale, ellipse.getHeight() * scale)
        }
     fun scale(ellipse: HalfEllipse?, scale: Double): HalfEllipse {
            if (ellipse == null) throw ArgumentNullException("circle")
            checkedScale(scale)
            return HalfEllipse(ellipse.getWidth() * scale, ellipse.getHeight() * scale)
        }
     fun scale(slice: Slice?, scale: Double): Slice {
            if (slice == null) throw ArgumentNullException("circle")
            checkedScale(scale)
            return Slice(slice.getSliceRadius() * scale, slice.getTheta())
        }
     fun scale(polygon: Polygon?, scale: Double): Polygon {
            if (polygon == null) throw ArgumentNullException("circle")
            checkedScale(scale)
            val center = polygon.getCenter()
            val vertices = Array(polygon.getVertices().size) { index ->
                center.to(polygon.getVertices()[index]).multiply(scale).add(center)
            }
            return Polygon(*vertices)
        }
     fun scale(segment: Segment?, scale: Double): Segment {
            if (segment == null) throw ArgumentNullException("circle")
            checkedScale(scale)
            val halfLength = segment.getLength() * scale * 0.5
            val direction = segment.getPoint1().to(segment.getPoint2())
            direction.normalize()
            direction.multiply(halfLength)
            val center = segment.getCenter()
            return Segment(center.sum(direction.x, direction.y), center.difference(direction.x, direction.y))
        }
     fun getIntersection(p1: Polygon, tx1: Transform, p2: Polygon, tx2: Transform): Polygon? {
            var firstIntersectionI = -1
            var firstIntersectionP = -1
            var firstIntersectionQ = -1
            val result = mutableListOf<Vector2>()
            val firstVertices = p1.getVertices()
            val secondVertices = p2.getVertices()
            val pn = firstVertices.size
            val qn = secondVertices.size
            var pi = 0
            var qi = 0
            var p = tx1.getTransformed(firstVertices[0])
            var q = tx2.getTransformed(secondVertices[0])
            val p0 = tx1.getTransformed(firstVertices[pn - 1])
            val q0 = tx2.getTransformed(secondVertices[qn - 1])
            val pv = p0.to(p)
            val qv = q0.to(q)
            var insideP = false
            var insideQ = false
            for (iteration in 0 until 2 * (pn + qn)) {
                val intersection = Segment.getSegmentIntersection(p0, p, q0, q, false)
                if (intersection != null) {
                    if (pi == firstIntersectionP && qi == firstIntersectionQ && iteration - 1 != firstIntersectionI)
                        return Polygon(*result.toTypedArray())
                    if (firstIntersectionP == -1) {
                        firstIntersectionI = iteration
                        firstIntersectionP = pi
                        firstIntersectionQ = qi
                    }
                    result.add(intersection)
                    insideP = Segment.getLocation(p, q0, q) >= 0.0
                    insideQ = !insideP
                }
                if (qv.cross(pv) >= 0.0) {
                    if (Segment.getLocation(p, q0, q) >= 0.0) {
                        if (insideQ) result.add(q)
                        qi = if (qi + 1 == qn) 0 else qi + 1
                        q0.set(q)
                        q = tx2.getTransformed(secondVertices[qi])
                        qv.set(q).subtract(q0)
                    } else {
                        if (insideP) result.add(p)
                        pi = if (pi + 1 == pn) 0 else pi + 1
                        p0.set(p)
                        p = tx1.getTransformed(firstVertices[pi])
                        pv.set(p).subtract(p0)
                    }
                } else {
                    if (Segment.getLocation(q, p0, p) >= 0.0) {
                        if (insideP) result.add(p)
                        pi = if (pi + 1 == pn) 0 else pi + 1
                        p0.set(p)
                        p = tx1.getTransformed(firstVertices[pi])
                        pv.set(p).subtract(p0)
                    } else {
                        if (insideQ) result.add(q)
                        qi = if (qi + 1 == qn) 0 else qi + 1
                        q0.set(q)
                        q = tx2.getTransformed(secondVertices[qi])
                        qv.set(q).subtract(q0)
                    }
                }
            }
            tx1.getTransformed(firstVertices[0], p)
            tx2.getTransformed(secondVertices[0], q)
            return if (p2.contains(p, tx2, false)) p1 else if (p1.contains(q, tx1, false)) p2 else null
        }
     fun createSquare(size: Double): Rectangle {
            if (size <= 0.0) throw ValueOutOfRangeException("size", size, ValueOutOfRangeException.MUST_BE_GREATER_THAN, 0.0)
            return Rectangle(size, size)
        }
     fun createRectangle(width: Double, height: Double) = Rectangle(width, height)
     fun createCircle(radius: Double) = Circle(radius)
     fun createTriangle(p1: Vector2?, p2: Vector2?, p3: Vector2?): Triangle = Triangle(
            (p1 ?: throw ArgumentNullException("p1")).copy(),
            (p2 ?: throw ArgumentNullException("p2")).copy(),
            (p3 ?: throw ArgumentNullException("p3")).copy()
        )
     fun createTriangleAtOrigin(p1: Vector2?, p2: Vector2?, p3: Vector2?): Triangle {
            val triangle = createTriangle(p1, p2, p3)
            val center = triangle.getCenter()
            triangle.translate(-center.x, -center.y)
            return triangle
        }
     fun createRightTriangle(width: Double, height: Double): Triangle = createRightTriangle(width, height, false)
     fun createRightTriangle(width: Double, height: Double, mirror: Boolean): Triangle {
            if (width <= 0.0) throw ValueOutOfRangeException("width", width, ValueOutOfRangeException.MUST_BE_GREATER_THAN, 0.0)
            if (height <= 0.0) throw ValueOutOfRangeException("height", height, ValueOutOfRangeException.MUST_BE_GREATER_THAN, 0.0)
            val top = Vector2(0.0, height)
            val left = Vector2()
            val right = Vector2(if (mirror) -width else width, 0.0)
            val triangle = if (mirror) Triangle(top, right, left) else Triangle(top, left, right)
            val center = triangle.getCenter()
            triangle.translate(-center.x, -center.y)
            return triangle
        }
     fun createSegment(p1: Vector2?, p2: Vector2?): Segment = Segment(
            (p1 ?: throw ArgumentNullException("p1")).copy(),
            (p2 ?: throw ArgumentNullException("p2")).copy()
        )
     fun createSegmentAtOrigin(p1: Vector2?, p2: Vector2?): Segment {
            val segment = createSegment(p1, p2)
            val center = segment.getCenter()
            segment.translate(-center.x, -center.y)
            return segment
        }
     fun createSegment(end: Vector2?): Segment = createSegment(Vector2(), end)
     fun createPolygon(vararg vertices: Vector2?): Polygon {
            val copied = Array(vertices.size) { index -> vertices[index]?.copy() ?: throw NullElementException("vertices", index) }
            return Polygon(*copied)
        }
     fun createPolygonAtOrigin(vararg vertices: Vector2?): Polygon {
            val polygon = createPolygon(*vertices)
            val center = polygon.getCenter()
            polygon.translate(-center.x, -center.y)
            return polygon
        }
     fun createHorizontalSegment(length: Double): Segment {
            if (length <= 0.0) throw ValueOutOfRangeException("length", length, ValueOutOfRangeException.MUST_BE_GREATER_THAN, 0.0)
            return Segment(Vector2(-length * 0.5, 0.0), Vector2(length * 0.5, 0.0))
        }
     fun createVerticalSegment(length: Double): Segment {
            if (length <= 0.0) throw ValueOutOfRangeException("length", length, ValueOutOfRangeException.MUST_BE_GREATER_THAN, 0.0)
            return Segment(Vector2(0.0, -length * 0.5), Vector2(0.0, length * 0.5))
        }
     fun createCapsule(width: Double, height: Double): Capsule = Capsule(width, height)
     fun createSlice(radius: Double, theta: Double): Slice = Slice(radius, theta)
     fun createSliceAtOrigin(radius: Double, theta: Double): Slice {
            val slice = Slice(radius, theta)
            val center = slice.getCenter()
            slice.translate(-center.x, -center.y)
            return slice
        }
     fun createEllipse(width: Double, height: Double): Ellipse = Ellipse(width, height)
     fun createHalfEllipse(width: Double, height: Double): HalfEllipse = HalfEllipse(width, height)
     fun createHalfEllipseAtOrigin(width: Double, height: Double): HalfEllipse {
            val ellipse = HalfEllipse(width, height)
            val center = ellipse.getCenter()
            ellipse.translate(-center.x, -center.y)
            return ellipse
        }
     fun createIsoscelesTriangle(width: Double, height: Double): Triangle {
            if (width <= 0.0) throw ValueOutOfRangeException("width", width, ValueOutOfRangeException.MUST_BE_GREATER_THAN, 0.0)
            if (height <= 0.0) throw ValueOutOfRangeException("height", height, ValueOutOfRangeException.MUST_BE_GREATER_THAN, 0.0)
            val triangle = Triangle(Vector2(0.0, height), Vector2(-width * 0.5, 0.0), Vector2(width * 0.5, 0.0))
            val center = triangle.getCenter()
            triangle.translate(-center.x, -center.y)
            return triangle
        }
     fun createEquilateralTriangle(height: Double): Triangle {
            if (height <= 0.0) throw ValueOutOfRangeException("height", height, ValueOutOfRangeException.MUST_BE_GREATER_THAN, 0.0)
            return createIsoscelesTriangle(2.0 * height * INV_SQRT_3, height)
        }
     fun createLinks(vertices: List<Vector2?>?, closed: Boolean): MutableList<Link> =
            createLinks(vertices!!.toTypedArray(), closed)

     fun createLinks(vertices: Array<Vector2?>?, closed: Boolean): MutableList<Link> {
            if (vertices == null) throw ArgumentNullException("vertices")
            val size = vertices.size
            if (size < 2) throw ValueOutOfRangeException("vertices.length", size, ValueOutOfRangeException.MUST_BE_GREATER_THAN_OR_EQUAL_TO, 2)
            val links = mutableListOf<Link>()
            for (index in 0 until size - 1) {
                val p0 = if (index == 0) {
                    if (closed) vertices[size - 1] else null
                } else vertices[index - 1]
                val p1 = vertices[index] ?: throw NullElementException("points", index)
                val p2 = vertices[index + 1] ?: throw NullElementException("points", index + 1)
                val p3 = if (index + 2 >= size) {
                    if (closed) vertices[index + 2 - size] else null
                } else vertices[index + 2]
                links.add(Link(p0?.copy(), p1.copy(), p2.copy(), p3?.copy()))
            }
            if (closed) links.add(Link(
                vertices[size - 2]!!.copy(), vertices[size - 1]!!.copy(),
                vertices[0]!!.copy(), vertices[1]!!.copy()
            ))
            return links
        }
    }
}
