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
package org.dyn4j.collision.narrowphase

import kotlin.math.abs
import kotlin.math.sqrt
import org.dyn4j.Epsilon
import org.dyn4j.JvmFieldBridge
import org.dyn4j.JvmStaticBridge
import org.dyn4j.exception.ArgumentNullException
import org.dyn4j.exception.ValueOutOfRangeException
import org.dyn4j.geometry.Circle
import org.dyn4j.geometry.Convex
import org.dyn4j.geometry.Ray
import org.dyn4j.geometry.Segment
import org.dyn4j.geometry.Transform
import org.dyn4j.geometry.Vector2

internal class ExpandingSimplexEdge(val point1: Vector2, val point2: Vector2, winding: Int) : Comparable<ExpandingSimplexEdge> {
    val normal = Vector2(point2.x - point1.x, point2.y - point1.y).also {
        if (winding < 0) it.right() else it.left()
        it.normalize()
    }
    val distance = abs(point1.x * normal.x + point1.y * normal.y)
    override fun compareTo(other: ExpandingSimplexEdge): Int = when {
        distance < other.distance -> -1
        distance > other.distance -> 1
        else -> 0
    }
    override fun toString() = "ExpandingSimplexEdge[Point1=$point1|Point2=$point2|Normal=$normal|Distance=$distance]"
}

internal class ExpandingSimplex(simplex: List<@kotlin.jvm.JvmSuppressWildcards Vector2>) {
    private val winding: Int
    private val edges = ArrayList<ExpandingSimplexEdge>(simplex.size)
    init {
        var direction = 0
        for (i in simplex.indices) {
            val cross = simplex[i].cross(simplex[(i + 1) % simplex.size])
            if (cross > 0.0) { direction = 1; break }
            if (cross < 0.0) { direction = -1; break }
        }
        winding = direction
        for (i in simplex.indices) add(ExpandingSimplexEdge(simplex[i], simplex[(i + 1) % simplex.size], winding))
    }
    fun getWinding() = winding
    fun getClosestEdge(): ExpandingSimplexEdge = edges.firstOrNull()!!
    fun expand(point: Vector2) {
        val edge = poll()
        add(ExpandingSimplexEdge(edge.point1, point, winding))
        add(ExpandingSimplexEdge(point, edge.point2, winding))
    }
    fun size() = edges.size
    override fun toString() = edges.joinToString(",", "[", "]") { "${it.point1}=${it.distance}" }

    private fun add(edge: ExpandingSimplexEdge) {
        var index = edges.size
        edges.add(edge)
        while (index > 0) {
            val parent = (index - 1) ushr 1
            if (edge >= edges[parent]) break
            edges[index] = edges[parent]
            index = parent
        }
        edges[index] = edge
    }

    private fun poll(): ExpandingSimplexEdge {
        val result = getClosestEdge()
        val last = edges.removeAt(edges.lastIndex)
        if (edges.isEmpty()) return result
        var index = 0
        val half = edges.size ushr 1
        while (index < half) {
            var child = (index shl 1) + 1
            if (child + 1 < edges.size && edges[child + 1] < edges[child]) child++
            if (last <= edges[child]) break
            edges[index] = edges[child]
            index = child
        }
        edges[index] = last
        return result
    }
}

open class Epa : MinkowskiPenetrationSolver {
    @get:kotlin.jvm.JvmName("maxIterationsField")
    @set:kotlin.jvm.JvmName("setMaxIterationsField")
    @JvmFieldBridge protected var maxIterations = DEFAULT_MAX_ITERATIONS
    @get:kotlin.jvm.JvmName("distanceEpsilonField")
    @set:kotlin.jvm.JvmName("setDistanceEpsilonField")
    @JvmFieldBridge protected var distanceEpsilon = DEFAULT_DISTANCE_EPSILON

    override fun getPenetration(simplex: List<@kotlin.jvm.JvmSuppressWildcards Vector2>, minkowskiSum: MinkowskiSum, penetration: Penetration) {
        val expanding = ExpandingSimplex(simplex)
        var edge: ExpandingSimplexEdge? = null
        var point: Vector2? = null
        for (i in 0 until maxIterations) {
            edge = expanding.getClosestEdge()
            point = minkowskiSum.getSupportPoint(edge.normal)
            val projection = point.dot(edge.normal)
            if (projection - edge.distance < distanceEpsilon) {
                penetration.setDirect(edge.normal.x, edge.normal.y, projection)
                return
            }
            expanding.expand(point)
        }
        penetration.setDirect(edge!!.normal.x, edge.normal.y, point!!.dot(edge.normal))
    }

    open fun getMaxIterations() = maxIterations
    open fun setMaxIterations(value: Int) {
        if (value < 5) throw ValueOutOfRangeException("maxIterations", value, ValueOutOfRangeException.MUST_BE_GREATER_THAN_OR_EQUAL_TO, 5)
        maxIterations = value
    }
    open fun getDistanceEpsilon() = distanceEpsilon
    open fun setDistanceEpsilon(value: Double) {
        if (value <= 0.0) throw ValueOutOfRangeException("distanceEpsilon", value, ValueOutOfRangeException.MUST_BE_GREATER_THAN, 0.0)
        distanceEpsilon = value
    }
    companion object {
        const val DEFAULT_MAX_ITERATIONS = 100
        @kotlin.jvm.JvmField val DEFAULT_DISTANCE_EPSILON = sqrt(Epsilon.E)
    }
}

open class Gjk : NarrowphaseDetector, DistanceDetector, RaycastDetector {
    @get:kotlin.jvm.JvmName("solverField")
    @set:kotlin.jvm.JvmName("setSolverField")
    @JvmFieldBridge protected var minkowskiPenetrationSolver: MinkowskiPenetrationSolver = Epa()
    @get:kotlin.jvm.JvmName("maxDetectIterationsField")
    @set:kotlin.jvm.JvmName("setMaxDetectIterationsField")
    @JvmFieldBridge protected var maxDetectIterations = DEFAULT_MAX_ITERATIONS
    @get:kotlin.jvm.JvmName("maxDistanceIterationsField")
    @set:kotlin.jvm.JvmName("setMaxDistanceIterationsField")
    @JvmFieldBridge protected var maxDistanceIterations = DEFAULT_MAX_ITERATIONS
    @get:kotlin.jvm.JvmName("maxRaycastIterationsField")
    @set:kotlin.jvm.JvmName("setMaxRaycastIterationsField")
    @JvmFieldBridge protected var maxRaycastIterations = DEFAULT_MAX_ITERATIONS
    @get:kotlin.jvm.JvmName("detectEpsilonField")
    @set:kotlin.jvm.JvmName("setDetectEpsilonField")
    @JvmFieldBridge protected var detectEpsilon = DEFAULT_DETECT_EPSILON
    @get:kotlin.jvm.JvmName("distanceEpsilonField")
    @set:kotlin.jvm.JvmName("setDistanceEpsilonField")
    @JvmFieldBridge protected var distanceEpsilon = DEFAULT_DISTANCE_EPSILON
    @get:kotlin.jvm.JvmName("raycastEpsilonField")
    @set:kotlin.jvm.JvmName("setRaycastEpsilonField")
    @JvmFieldBridge protected var raycastEpsilon = DEFAULT_RAYCAST_EPSILON

    constructor()
    constructor(solver: MinkowskiPenetrationSolver?) {
        minkowskiPenetrationSolver = solver ?: throw ArgumentNullException("minkowskiPenetrationSolver")
    }

    override fun detect(convex1: Convex, transform1: Transform, convex2: Convex, transform2: Transform, penetration: Penetration): Boolean {
        if (convex1 is Circle && convex2 is Circle) return CircleDetector.detect(convex1, transform1, convex2, transform2, penetration)
        val simplex = ArrayList<Vector2>(3)
        val sum = MinkowskiSum(convex1, transform1, convex2, transform2)
        val direction = getInitialDirection(convex1, transform1, convex2, transform2)
        if (detect(sum, simplex, direction)) {
            minkowskiPenetrationSolver.getPenetration(simplex, sum, penetration)
            return true
        }
        return false
    }

    override fun detect(convex1: Convex, transform1: Transform, convex2: Convex, transform2: Transform): Boolean {
        if (convex1 is Circle && convex2 is Circle) return CircleDetector.detect(convex1, transform1, convex2, transform2)
        val simplex = ArrayList<Vector2>(3)
        val sum = MinkowskiSum(convex1, transform1, convex2, transform2)
        return detect(sum, simplex, getInitialDirection(convex1, transform1, convex2, transform2))
    }

    protected open fun getInitialDirection(convex1: Convex, transform1: Transform, convex2: Convex, transform2: Transform): Vector2 {
        val c1 = transform1.getTransformed(convex1.getCenter())
        val c2 = transform2.getTransformed(convex2.getCenter())
        return c2.subtract(c1)
    }

    protected open fun detect(sum: MinkowskiSum, simplex: MutableList<Vector2>, direction: Vector2): Boolean {
        if (direction.isZero()) direction.set(1.0, 0.0)
        simplex.add(sum.getSupportPoint(direction))
        if (simplex[0].dot(direction) <= 0.0) return false
        direction.negate()
        for (i in 0 until maxDetectIterations) {
            val support = sum.getSupportPoint(direction)
            simplex.add(support)
            if (support.dot(direction) <= detectEpsilon) return false
            if (checkSimplex(simplex, direction)) return true
        }
        return false
    }

    protected open fun checkSimplex(simplex: MutableList<Vector2>, direction: Vector2): Boolean {
        val a = simplex[simplex.size - 1]
        val ao = a.getNegative()
        if (simplex.size == 3) {
            val b = simplex[1]
            val c = simplex[0]
            val ab = a.to(b)
            val ac = a.to(c)
            val cross = ab.x * ac.y - ac.x * ab.y
            val acPerp = Vector2(-ac.y * cross, ac.x * cross)
            if (acPerp.dot(ao) >= 0.0) {
                simplex.removeAt(1)
                direction.set(acPerp)
            } else {
                val abPerp = Vector2(ab.y * cross, -ab.x * cross)
                if (abPerp.dot(ao) < 0.0) return true
                simplex.removeAt(0)
                direction.set(abPerp)
            }
        } else {
            val b = simplex[0]
            val ab = a.to(b)
            direction.set(Vector2.tripleProduct(ab, ao, ab))
            if (direction.getMagnitudeSquared() <= Epsilon.E) direction.set(ab.left())
        }
        return false
    }

    override fun distance(convex1: Convex, transform1: Transform, convex2: Convex, transform2: Transform, separation: Separation): Boolean {
        if (convex1 is Circle && convex2 is Circle) return CircleDetector.distance(convex1, transform1, convex2, transform2, separation)
        val sum = MinkowskiSum(convex1, transform1, convex2, transform2)
        val c1 = transform1.getTransformed(convex1.getCenter())
        val c2 = transform2.getTransformed(convex2.getCenter())
        var direction = c1.to(c2)
        if (direction.isZero()) return false
        var a = sum.getSupportPoints(direction)
        direction.negate()
        var b = sum.getSupportPoints(direction)
        direction = Segment.getPointOnSegmentClosestToPoint(ORIGIN, b.point, a.point)
        for (i in 0 until maxDistanceIterations) {
            direction.negate()
            if (direction.getMagnitudeSquared() <= Epsilon.E) return false
            val c = sum.getSupportPoints(direction)
            if (containsOrigin(a.point, b.point, c.point)) return false
            val projection = c.point.dot(direction)
            if (projection - a.point.dot(direction) < distanceEpsilon) {
                findClosestPoints(a, b, separation)
                return true
            }
            val p1 = Segment.getPointOnSegmentClosestToPoint(ORIGIN, a.point, c.point)
            val p2 = Segment.getPointOnSegmentClosestToPoint(ORIGIN, c.point, b.point)
            val p1Magnitude = p1.getMagnitudeSquared()
            val p2Magnitude = p2.getMagnitudeSquared()
            if (p1Magnitude <= Epsilon.E) { findClosestPoints(a, c, separation); return true }
            if (p2Magnitude <= Epsilon.E) { findClosestPoints(c, b, separation); return true }
            if (p1Magnitude < p2Magnitude) { b = c; direction = p1 } else { a = c; direction = p2 }
        }
        findClosestPoints(a, b, separation)
        return true
    }

    protected open fun findClosestPoints(a: MinkowskiSumPoint, b: MinkowskiSumPoint, separation: Separation) {
        val p1 = Vector2()
        val p2 = Vector2()
        val line = a.point.to(b.point)
        if (line.isZero()) {
            p1.set(a.supportPoint1); p2.set(a.supportPoint2)
        } else {
            val weight = -line.dot(a.point) / line.dot(line)
            if (weight > 1.0) {
                p1.set(b.supportPoint1); p2.set(b.supportPoint2)
            } else if (weight < 0.0) {
                p1.set(a.supportPoint1); p2.set(a.supportPoint2)
            } else {
                p1.x = a.supportPoint1.x + weight * (b.supportPoint1.x - a.supportPoint1.x)
                p1.y = a.supportPoint1.y + weight * (b.supportPoint1.y - a.supportPoint1.y)
                p2.x = a.supportPoint2.x + weight * (b.supportPoint2.x - a.supportPoint2.x)
                p2.y = a.supportPoint2.y + weight * (b.supportPoint2.y - a.supportPoint2.y)
            }
        }
        val normal = p1.to(p2)
        val distance = normal.normalize()
        separation.setDirect(normal.x, normal.y, distance, p1.x, p1.y, p2.x, p2.y)
    }

    protected open fun containsOrigin(a: Vector2, b: Vector2, c: Vector2): Boolean {
        val sa = a.cross(b)
        val sb = b.cross(c)
        val sc = c.cross(a)
        return sa * sb > 0.0 && sa * sc > 0.0
    }

    override fun raycast(ray: Ray, maxLength: Double, convex: Convex, transform: Transform, raycast: Raycast): Boolean {
        if (convex is Circle) return CircleDetector.raycast(ray, maxLength, convex, transform, raycast)
        if (convex is Segment) return SegmentDetector.raycast(ray, maxLength, convex, transform, raycast)
        var lambda = 0.0
        val lengthCheck = maxLength > 0.0
        var a: Vector2? = null
        var b: Vector2? = null
        val start = ray.getStart()
        var x = start
        val direction = ray.getDirectionVector()
        val normal = Vector2()
        if (convex.contains(start, transform)) return false
        val center = transform.getTransformed(convex.getCenter())
        var d = center.to(x)
        var distanceSquared = Double.MAX_VALUE
        var iterations = 0
        while (distanceSquared > raycastEpsilon) {
            val p = convex.getFarthestPoint(d, transform)
            val w = p.to(x)
            val dDotW = d.dot(w)
            if (dDotW > 0.0) {
                val dDotR = d.dot(direction)
                if (dDotR >= 0.0) return false
                lambda -= dDotW / dDotR
                if (lengthCheck && lambda > maxLength) return false
                x = direction.product(lambda).add(start)
                normal.set(d)
            }
            if (a != null) {
                if (b != null) {
                    val p1 = Segment.getPointOnSegmentClosestToPoint(x, a, p)
                    val p2 = Segment.getPointOnSegmentClosestToPoint(x, p, b)
                    if (p1.distanceSquared(x) < p2.distanceSquared(x)) {
                        b.set(p); distanceSquared = p1.distanceSquared(x)
                    } else {
                        a.set(p); distanceSquared = p2.distanceSquared(x)
                    }
                    d = Vector2.tripleProduct(a.to(b), a.to(x), a.to(b))
                } else {
                    b = p
                    val ab = a.to(b)
                    d = Vector2.tripleProduct(ab, a.to(x), ab)
                }
            } else {
                a = p
                d.negate()
            }
            if (iterations == maxRaycastIterations) return false
            iterations++
        }
        normal.normalize()
        raycast.setDirect(x.x, x.y, normal.x, normal.y, lambda)
        return true
    }

    open fun getMaxDetectIterations() = maxDetectIterations
    open fun setMaxDetectIterations(value: Int) {
        if (value < 5) throw ValueOutOfRangeException("maxIterations", value, ValueOutOfRangeException.MUST_BE_GREATER_THAN_OR_EQUAL_TO, 5)
        maxDetectIterations = value
    }
    open fun getMaxDistanceIterations() = maxDistanceIterations
    open fun setMaxDistanceIterations(value: Int) {
        if (value < 5) throw ValueOutOfRangeException("maxIterations", value, ValueOutOfRangeException.MUST_BE_GREATER_THAN_OR_EQUAL_TO, 5)
        maxDistanceIterations = value
    }
    open fun getMaxRaycastIterations() = maxRaycastIterations
    open fun setMaxRaycastIterations(value: Int) {
        if (value < 5) throw ValueOutOfRangeException("maxIterations", value, ValueOutOfRangeException.MUST_BE_GREATER_THAN_OR_EQUAL_TO, 5)
        maxRaycastIterations = value
    }
    open fun getDetectEpsilon() = detectEpsilon
    open fun setDetectEpsilon(value: Double) {
        if (value < 0.0) throw ValueOutOfRangeException("detectEpsilon", value, ValueOutOfRangeException.MUST_BE_GREATER_THAN_OR_EQUAL_TO, 0.0)
        detectEpsilon = value
    }
    open fun getRaycastEpsilon() = raycastEpsilon
    open fun setRaycastEpsilon(value: Double) {
        if (value <= 0.0) throw ValueOutOfRangeException("raycastEpsilon", value, ValueOutOfRangeException.MUST_BE_GREATER_THAN, 0.0)
        raycastEpsilon = value
    }
    open fun getDistanceEpsilon() = distanceEpsilon
    open fun setDistanceEpsilon(value: Double) {
        if (value <= 0.0) throw ValueOutOfRangeException("distanceEpsilon", value, ValueOutOfRangeException.MUST_BE_GREATER_THAN, 0.0)
        distanceEpsilon = value
    }
    open fun getMinkowskiPenetrationSolver() = minkowskiPenetrationSolver
    open fun setMinkowskiPenetrationSolver(value: MinkowskiPenetrationSolver?) {
        minkowskiPenetrationSolver = value ?: throw ArgumentNullException("minkowskiPenetrationSolver")
    }

    companion object {
        private val ORIGIN = Vector2()
        const val DEFAULT_MAX_ITERATIONS = 30
        const val DEFAULT_DETECT_EPSILON = 0.0
        @kotlin.jvm.JvmField val DEFAULT_DISTANCE_EPSILON = sqrt(Epsilon.E)
        @kotlin.jvm.JvmField val DEFAULT_RAYCAST_EPSILON = DEFAULT_DISTANCE_EPSILON
    }
}

class SegmentDetector private constructor() {
    companion object {
        @JvmStaticBridge fun raycast(ray: Ray, maxLength: Double, segment: Segment, transform: Transform, raycast: Raycast): Boolean {
            val p0 = ray.getStart()
            val d0 = ray.getDirectionVector()
            val p1 = transform.getTransformed(segment.getPoint1())
            val p2 = transform.getTransformed(segment.getPoint2())
            val d1 = p1.to(p2)
            val vertical = abs(d1.x) <= Epsilon.E
            val horizontal = abs(d1.y) <= Epsilon.E
            if (vertical && horizontal) return false
            if (segment.contains(p0, transform)) return false
            val p0ToP1 = p1.difference(p0)
            val numerator = d1.cross(p0ToP1)
            val denominator = d1.cross(d0)
            if (abs(denominator) <= Epsilon.E) {
                val n = d0.getRightHandOrthogonalVector()
                val nDotP0 = n.dot(p0)
                val nDotP1 = n.dot(p1)
                if (abs(nDotP0 - nDotP1) < Epsilon.E) {
                    val d0DotP0 = d0.dot(p0)
                    val d0DotP1 = d0.dot(p1) - d0DotP0
                    val d0DotP2 = d0.dot(p2) - d0DotP0
                    if (d0DotP1 < 0.0 || d0DotP2 < 0.0) return false
                    val distance: Double
                    val point: Vector2
                    if (d0DotP1 < d0DotP2) { distance = d0DotP1; point = p1.copy() }
                    else { distance = d0DotP2; point = p2.copy() }
                    if (maxLength > 0.0 && distance > maxLength) return false
                    raycast.setDirect(point.x, point.y, -d0.x, -d0.y, distance)
                    return true
                }
                return false
            }
            val t = numerator / denominator
            if (t < 0.0 || maxLength > 0.0 && t > maxLength) return false
            val s = if (vertical) (t * d0.y + p0.y - p1.y) / d1.y else (t * d0.x + p0.x - p1.x) / d1.x
            if (s < 0.0 || s > 1.0) return false
            val point = d0.product(t).add(p0)
            val normal = p1.to(p2)
            normal.normalize()
            normal.right()
            if (normal.dot(d0) > 0.0) normal.negate()
            raycast.setDirect(point.x, point.y, normal.x, normal.y, t)
            return true
        }
    }
}

open class Sat : NarrowphaseDetector, ContainmentDetector {
    override fun detect(convex1: Convex, transform1: Transform, convex2: Convex, transform2: Transform, penetration: Penetration): Boolean {
        if (convex1 is Circle && convex2 is Circle) return CircleDetector.detect(convex1, transform1, convex2, transform2, penetration)
        var bestAxis: Vector2? = null
        var overlap = Double.MAX_VALUE
        val foci1 = convex1.getFoci(transform1)
        val foci2 = convex2.getFoci(transform2)
        val axes1 = convex1.getAxes(foci2, transform1)
        val axes2 = convex2.getAxes(foci1, transform2)
        for (axes in arrayOf(axes1, axes2)) {
            if (axes != null) for (axis in axes) {
                if (!axis.isZero()) {
                    val intervalA = convex1.project(axis, transform1)
                    val intervalB = convex2.project(axis, transform2)
                    if (!intervalA.overlaps(intervalB)) return false
                    var candidate = intervalA.getOverlap(intervalB)
                    if (intervalA.containsExclusive(intervalB) || intervalB.containsExclusive(intervalA)) {
                        val max = abs(intervalA.getMax() - intervalB.getMax())
                        val min = abs(intervalA.getMin() - intervalB.getMin())
                        if (max > min) { axis.negate(); candidate += min } else candidate += max
                    }
                    if (candidate < overlap) { overlap = candidate; bestAxis = axis }
                }
            }
        }
        val center1 = transform1.getTransformed(convex1.getCenter())
        val center2 = transform2.getTransformed(convex2.getCenter())
        val cToC = center1.to(center2)
        val axis = bestAxis!!
        if (cToC.dot(axis) < 0.0) axis.negate()
        penetration.setDirect(axis.x, axis.y, overlap)
        return true
    }

    override fun detect(convex1: Convex, transform1: Transform, convex2: Convex, transform2: Transform): Boolean {
        if (convex1 is Circle && convex2 is Circle) return CircleDetector.detect(convex1, transform1, convex2, transform2)
        val foci1 = convex1.getFoci(transform1)
        val foci2 = convex2.getFoci(transform2)
        val axes1 = convex1.getAxes(foci2, transform1)
        val axes2 = convex2.getAxes(foci1, transform2)
        for (axes in arrayOf(axes1, axes2)) {
            if (axes != null) for (axis in axes) {
                if (!axis.isZero()) {
                    val intervalA = convex1.project(axis, transform1)
                    val intervalB = convex2.project(axis, transform2)
                    if (!intervalA.overlaps(intervalB)) return false
                }
            }
        }
        return true
    }

    override fun contains(convex1: Convex, transform1: Transform, convex2: Convex, transform2: Transform, containment: Containment): Boolean {
        if (convex1 is Circle && convex2 is Circle) return CircleDetector.contains(convex1, transform1, convex2, transform2, containment)
        if (convex1 is Segment && convex2 is Segment) return false
        val foci1 = convex1.getFoci(transform1)
        val foci2 = convex2.getFoci(transform2)
        val axes1 = convex1.getAxes(foci2, transform1)
        val axes2 = convex2.getAxes(foci1, transform2)
        var aContainsB = true
        var bContainsA = true
        for (axes in arrayOf(axes1, axes2)) {
            if (axes != null) for (axis in axes) {
                if (!axis.isZero()) {
                    val intervalA = convex1.project(axis, transform1)
                    val intervalB = convex2.project(axis, transform2)
                    if (!intervalA.containsExclusive(intervalB)) aContainsB = false
                    if (!intervalB.containsExclusive(intervalA)) bContainsA = false
                }
                if (!aContainsB && !bContainsA) return false
            }
        }
        containment.setAContainedInB(bContainsA)
        containment.setBContainedInA(aContainsB)
        return true
    }
}
