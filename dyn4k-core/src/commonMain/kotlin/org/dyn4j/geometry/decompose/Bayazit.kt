/*
 * Copyright (c) 2010-2020 William Bittle  http://www.dyn4j.org/
 * Copyright (c) 2010-2021 William Bittle  http://www.dyn4j.org/
 * Copyright (c) 2010-2022 William Bittle  http://www.dyn4j.org/
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
package org.dyn4j.geometry.decompose

import org.dyn4j.Epsilon
import org.dyn4j.exception.NullElementException
import org.dyn4j.exception.ValueOutOfRangeException
import org.dyn4j.geometry.Convex
import org.dyn4j.geometry.Geometry
import org.dyn4j.geometry.Segment
import org.dyn4j.geometry.Triangle
import org.dyn4j.geometry.Vector2
import kotlin.math.abs
import kotlin.math.sqrt

interface Decomposer {
    fun decompose(vararg points: Vector2?): List<Convex>
    fun decompose(points: List<Vector2?>): List<Convex>
}

interface Triangulator {
    fun triangulate(vararg points: Vector2?): List<org.dyn4j.geometry.Triangle>
}

abstract class AbstractDecomposer : Decomposer {
    override fun decompose(points: List<Vector2?>): List<Convex> = decompose(*points.toTypedArray())
}

open class Bayazit : AbstractDecomposer() {
    override fun decompose(vararg points: Vector2?): List<Convex> {
        if (points.size < 4) throw ValueOutOfRangeException(
            "points.length", points.size, ValueOutOfRangeException.MUST_BE_GREATER_THAN_OR_EQUAL_TO, 4
        )
        val polygon = MutableList(points.size) { i -> points[i] ?: throw NullElementException("points", i) }
        if (Geometry.getWinding(polygon) < 0.0) {
            polygon.reverse()
            reverseInput(points)
        }
        val result = mutableListOf<Convex>()
        decomposePolygon(polygon, result)
        return result
    }

    protected open fun decomposePolygon(polygon: List<Vector2>, polygons: MutableList<Convex>) {
        val size = polygon.size
        val upperIntersection = Vector2()
        val lowerIntersection = Vector2()
        var upperDistance = Double.MAX_VALUE
        var lowerDistance = Double.MAX_VALUE
        var closestDistance = Double.MAX_VALUE
        var upperIndex = 0
        var lowerIndex = 0
        var closestIndex: Int
        val lower = mutableListOf<Vector2>()
        val upper = mutableListOf<Vector2>()
        for (i in 0 until size) {
            val p = polygon[i]
            val p0 = polygon[(i + size - 1) % size]
            val p1 = polygon[(i + 1) % size]
            if (isReflex(p0, p, p1)) {
                for (j in 0 until size) {
                    val q = polygon[j]
                    val q0 = polygon[(j + size - 1) % size]
                    val q1 = polygon[(j + 1) % size]
                    val s = Vector2()
                    if (left(p0, p, q) && rightOn(p0, p, q0) && getIntersection(p0, p, q, q0, s)) {
                        if (right(p1, p, s)) {
                            val distance = p.distanceSquared(s)
                            if (distance < lowerDistance) {
                                lowerDistance = distance
                                lowerIntersection.set(s)
                                lowerIndex = j
                            }
                        }
                    }
                    if (left(p1, p, q1) && rightOn(p1, p, q) && getIntersection(p1, p, q, q1, s)) {
                        if (left(p0, p, s)) {
                            val distance = p.distanceSquared(s)
                            if (distance < upperDistance) {
                                upperDistance = distance
                                upperIntersection.set(s)
                                upperIndex = j
                            }
                        }
                    }
                }
                if (lowerIndex == (upperIndex + 1) % size) {
                    val s = upperIntersection.sum(lowerIntersection).multiply(0.5)
                    if (i < upperIndex) {
                        lower.addAll(polygon.subList(i, upperIndex + 1))
                        lower.add(s)
                        upper.add(s)
                        if (lowerIndex != 0) upper.addAll(polygon.subList(lowerIndex, size))
                        upper.addAll(polygon.subList(0, i + 1))
                    } else {
                        if (i != 0) lower.addAll(polygon.subList(i, size))
                        lower.addAll(polygon.subList(0, upperIndex + 1))
                        lower.add(s)
                        upper.add(s)
                        upper.addAll(polygon.subList(lowerIndex, i + 1))
                    }
                } else {
                    if (lowerIndex > upperIndex) upperIndex += size
                    closestIndex = lowerIndex
                    for (j in lowerIndex..upperIndex) {
                        val index = j % size
                        val q = polygon[index]
                        if (q === p || q === p0 || q === p1) continue
                        val distance = p.distanceSquared(q)
                        if (distance < closestDistance && isVisible(polygon, i, index)) {
                            closestDistance = distance
                            closestIndex = index
                        }
                    }
                    if (i < closestIndex) {
                        lower.addAll(polygon.subList(i, closestIndex + 1))
                        if (closestIndex != 0) upper.addAll(polygon.subList(closestIndex, size))
                        upper.addAll(polygon.subList(0, i + 1))
                    } else {
                        if (i != 0) lower.addAll(polygon.subList(i, size))
                        lower.addAll(polygon.subList(0, closestIndex + 1))
                        upper.addAll(polygon.subList(closestIndex, i + 1))
                    }
                }
                if (lower.size < upper.size) {
                    decomposePolygon(lower, polygons)
                    decomposePolygon(upper, polygons)
                } else {
                    decomposePolygon(upper, polygons)
                    decomposePolygon(lower, polygons)
                }
                return
            }
        }
        if (polygon.size < 3) throw IllegalArgumentException("The given simple polygon has crossing edges and not supported")
        polygons.add(Geometry.createPolygon(*polygon.toTypedArray()))
    }

    protected open fun isReflex(p0: Vector2, p: Vector2, p1: Vector2): Boolean = right(p1, p0, p)
    protected open fun left(a: Vector2, b: Vector2, p: Vector2): Boolean = Segment.getLocation(p, a, b) > 0.0
    protected open fun leftOn(a: Vector2, b: Vector2, p: Vector2): Boolean = Segment.getLocation(p, a, b) >= 0.0
    protected open fun right(a: Vector2, b: Vector2, p: Vector2): Boolean = Segment.getLocation(p, a, b) < 0.0
    protected open fun rightOn(a: Vector2, b: Vector2, p: Vector2): Boolean = Segment.getLocation(p, a, b) <= 0.0

    protected open fun getIntersection(a1: Vector2, a2: Vector2, b1: Vector2, b2: Vector2, p: Vector2): Boolean {
        val s1 = a1.difference(a2)
        val s2 = b1.difference(b2)
        var determinant = s1.cross(s2)
        if (abs(determinant) <= Epsilon.E) return false
        determinant = 1.0 / determinant
        val t2 = determinant * (a1.cross(s1) - b1.cross(s1))
        p.x = b1.x * (1.0 - t2) + b2.x * t2
        p.y = b1.y * (1.0 - t2) + b2.y * t2
        return true
    }

    private fun isVisible(polygon: List<Vector2>, i: Int, j: Int): Boolean {
        val size = polygon.size
        val iv0 = polygon[(i + size - 1) % size]
        val iv = polygon[i]
        val iv1 = polygon[(i + 1) % size]
        val jv0 = polygon[(j + size - 1) % size]
        val jv = polygon[j]
        val jv1 = polygon[(j + 1) % size]
        if (isReflex(iv0, iv, iv1)) {
            if (leftOn(iv, iv0, jv) && rightOn(iv, iv1, jv)) return false
        } else if (rightOn(iv, iv1, jv) || leftOn(iv, iv0, jv)) return false
        if (isReflex(jv0, jv, jv1)) {
            if (leftOn(jv, jv0, iv) && rightOn(jv, jv1, iv)) return false
        } else if (rightOn(jv, jv1, iv) || leftOn(jv, jv0, iv)) return false
        for (k in 0 until size) {
            val next = (k + 1) % size
            if (k == i || k == j || next == i || next == j) continue
            if (Segment.getSegmentIntersection(iv, jv, polygon[k], polygon[next]) != null) return false
        }
        return true
    }
}

class EarClippingVertex(val point: Vector2) {
    lateinit var prev: EarClippingVertex
    lateinit var next: EarClippingVertex
    var ear: Boolean = false
    var reflex: Boolean = false
    var index: Int = 0
    override fun toString(): String = point.toString()
}

open class EarClipping : AbstractDecomposer(), Triangulator {
    companion object {
        private val CONTAINS_EPSILON = sqrt(Epsilon.E)
    }

    override fun decompose(vararg points: Vector2?): List<Convex> {
        val dcel = createTriangulationArray(points)
        dcel.hertelMehlhorn()
        return dcel.getConvexDecomposition()
    }

    override fun triangulate(vararg points: Vector2?): List<Triangle> = createTriangulationArray(points).getTriangulation()

    fun createTriangulation(vararg points: Vector2?): DoubleEdgeList = createTriangulationArray(points)

    private fun createTriangulationArray(points: Array<out Vector2?>): DoubleEdgeList {
        if (points.size < 4) throw ValueOutOfRangeException(
            "points.length", points.size, ValueOutOfRangeException.MUST_BE_GREATER_THAN_OR_EQUAL_TO, 4
        )
        val source = Array(points.size) { i -> points[i] ?: throw NullElementException("points", i) }
        if (Geometry.getWinding(*source) < 0.0) {
            source.reverse()
            reverseInput(points)
        }
        val dcel = DoubleEdgeList(source)
        val nodes = Array(source.size) { i -> EarClippingVertex(source[i]) }
        for (i in nodes.indices) {
            val current = nodes[i]
            current.prev = nodes[(i + nodes.size - 1) % nodes.size]
            current.next = nodes[(i + 1) % nodes.size]
            current.index = i
            val backward = current.point.to(current.prev.point)
            val forward = current.point.to(current.next.point)
            if (forward.isZero()) throw IllegalArgumentException("The given simple polygon has coincident vertices")
            current.reflex = backward.cross(forward) >= 0.0
        }
        for (node in nodes) node.ear = isEar(node, nodes.size)
        var node = nodes[0]
        var remaining = nodes.size
        while (remaining > 3) {
            if (node.ear) {
                dcel.addHalfEdges(node.next.index, node.prev.index)
                val previous = node.prev
                val next = node.next
                previous.next = next
                next.prev = previous
                if (previous.reflex) previous.reflex = isReflex(previous)
                if (next.reflex) next.reflex = isReflex(next)
                if (!previous.reflex) previous.ear = isEar(previous, remaining)
                if (!next.reflex) next.ear = isEar(next, remaining)
                remaining--
            }
            node = node.next
        }
        return dcel
    }

    fun isReflex(vertex: EarClippingVertex): Boolean =
        vertex.point.to(vertex.prev.point).cross(vertex.point.to(vertex.next.point)) >= 0.0

    fun isEar(vertex: EarClippingVertex, n: Int): Boolean {
        if (vertex.reflex) return false
        val a = vertex.point
        val b = vertex.next.point
        val c = vertex.prev.point
        var candidate = vertex.next.next
        for (j in 0 until n - 3) {
            if (candidate.reflex && contains(a, b, c, candidate.point)) return false
            candidate = candidate.next
        }
        return true
    }

    protected open fun contains(a: Vector2, b: Vector2, c: Vector2, p: Vector2): Boolean {
        val ab = a.to(b)
        val ac = a.to(c)
        val pa = a.to(p)
        val dot00 = ac.dot(ac)
        val dot01 = ac.dot(ab)
        val dot02 = ac.dot(pa)
        val dot11 = ab.dot(ab)
        val dot12 = ab.dot(pa)
        val denominator = dot00 * dot11 - dot01 * dot01
        val u = (dot11 * dot02 - dot01 * dot12) / denominator
        val v = (dot00 * dot12 - dot01 * dot02) / denominator
        return u > 0.0 && v > 0.0 && u + v <= 1.0 + CONTAINS_EPSILON
    }
}

@Suppress("UNCHECKED_CAST")
internal fun reverseInput(points: Array<out Vector2?>) {
    (points as Array<Vector2?>).reverse()
}
