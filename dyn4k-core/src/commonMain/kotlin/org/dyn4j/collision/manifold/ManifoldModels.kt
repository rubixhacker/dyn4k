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
package org.dyn4j.collision.manifold

import org.dyn4j.Copyable
import org.dyn4j.JvmFieldBridge
import org.dyn4j.collision.narrowphase.Penetration
import org.dyn4j.geometry.Convex
import org.dyn4j.geometry.EdgeFeature
import org.dyn4j.geometry.Feature
import org.dyn4j.geometry.PointFeature
import org.dyn4j.geometry.Shiftable
import org.dyn4j.geometry.Transform
import org.dyn4j.geometry.Vector2
import kotlin.math.abs

interface ManifoldPointId : Copyable<ManifoldPointId> {
    companion object {
        @kotlin.jvm.JvmField val DISTANCE: ManifoldPointId = object : ManifoldPointId {
            override fun copy(): ManifoldPointId = this
            override fun toString() = "DistanceManifoldPointId[]"
        }
    }
}

open class IndexedManifoldPointId : ManifoldPointId {
    @kotlin.jvm.JvmField protected val referenceEdgeIndex: Int
    @kotlin.jvm.JvmField protected val incidentEdgeIndex: Int
    @kotlin.jvm.JvmField protected val incidentVertexIndex: Int
    @kotlin.jvm.JvmField protected val flipped: Boolean

    constructor(referenceEdgeIndex: Int, incidentEdgeIndex: Int, incidentVertexIndex: Int) :
        this(referenceEdgeIndex, incidentEdgeIndex, incidentVertexIndex, false)
    constructor(referenceEdgeIndex: Int, incidentEdgeIndex: Int, incidentVertexIndex: Int, flipped: Boolean) {
        this.referenceEdgeIndex = referenceEdgeIndex
        this.incidentEdgeIndex = incidentEdgeIndex
        this.incidentVertexIndex = incidentVertexIndex
        this.flipped = flipped
    }
    protected constructor(other: IndexedManifoldPointId) : this(
        other.referenceEdgeIndex, other.incidentEdgeIndex, other.incidentVertexIndex, other.flipped
    )

    override fun copy(): IndexedManifoldPointId = IndexedManifoldPointId(this)
    override fun equals(other: Any?): Boolean = other === this || (other is IndexedManifoldPointId &&
        referenceEdgeIndex == other.referenceEdgeIndex && incidentEdgeIndex == other.incidentEdgeIndex &&
        incidentVertexIndex == other.incidentVertexIndex && flipped == other.flipped)
    override fun hashCode(): Int {
        var hash = referenceEdgeIndex
        hash = 37 * hash + incidentEdgeIndex
        hash = 37 * hash + incidentVertexIndex
        hash = 37 * hash + if (flipped) 1231 else 1237
        return hash
    }
    override fun toString() = "IndexedManifoldPointId[ReferenceEdge=$referenceEdgeIndex|IncidentEdge=$incidentEdgeIndex|IncidentVertex=$incidentVertexIndex|IsFlipped=$flipped]"
    open fun getReferenceEdgeIndex() = referenceEdgeIndex
    open fun getIncidentEdgeIndex() = incidentEdgeIndex
    open fun getIncidentVertexIndex() = incidentVertexIndex
    open fun isFlipped() = flipped
}

open class ManifoldPoint : Shiftable, Copyable<ManifoldPoint> {
    @kotlin.jvm.JvmField protected var id: ManifoldPointId
    @kotlin.jvm.JvmField protected val point: Vector2
    @kotlin.jvm.JvmField protected var depth: Double = 0.0

    constructor(id: ManifoldPointId?) { this.id = id ?: ManifoldPointId.DISTANCE; point = Vector2() }
    internal constructor(id: ManifoldPointId, point: Vector2, depth: Double) {
        this.id = id.copy(); this.point = point.copy(); this.depth = depth
    }
    protected constructor(other: ManifoldPoint) {
        id = other.id.copy(); point = other.point.copy(); depth = other.depth
    }

    open fun getId() = id
    open fun getPoint() = point
    open fun setPoint(value: Vector2) { point.x = value.x; point.y = value.y }
    open fun getDepth() = depth
    open fun setDepth(value: Double) { depth = value }
    @Deprecated("Use set")
    open fun copy(other: ManifoldPoint) = set(other)
    open fun set(other: ManifoldPoint) {
        id = other.id.copy(); depth = other.depth; point.x = other.point.x; point.y = other.point.y
    }
    override fun shift(shift: Vector2) { shiftPointDirect(shift) }
    @kotlin.jvm.JvmName("shiftPointDirect-dyn4k")
    internal fun shiftPointDirect(shift: Vector2) { point.x += shift.x; point.y += shift.y }
    override fun copy(): ManifoldPoint = ManifoldPoint(this)
    override fun toString() = "ManifoldPoint[Id=$id|Point=$point|Depth=$depth]"
}

open class Manifold : Shiftable, Copyable<Manifold> {
    @kotlin.jvm.JvmField protected val points: MutableList<ManifoldPoint>
    @kotlin.jvm.JvmField protected val normal: Vector2

    constructor() { points = ArrayList(2); normal = Vector2() }
    protected constructor(normal: Vector2, points: List<@kotlin.jvm.JvmSuppressWildcards ManifoldPoint>) {
        this.points = ArrayList(points.size); this.normal = normal.copy()
        for (point in points) this.points.add(point.copy())
    }
    protected constructor(other: Manifold) {
        points = ArrayList(other.points.size); normal = other.normal.copy()
        for (point in other.points) points.add(point.copy())
    }

    open fun clear() { points.clear(); normal.x = 0.0; normal.y = 0.0 }
    open fun getPoints(): MutableList<ManifoldPoint> = points
    open fun getNormal() = normal
    open fun setPoints(values: List<@kotlin.jvm.JvmSuppressWildcards ManifoldPoint>) {
        points.clear()
        for (point in values) points.add(point.copy())
    }
    open fun setNormal(value: Vector2) { normal.x = value.x; normal.y = value.y }
    @Deprecated("Use set")
    open fun copy(other: Manifold) = set(other)
    open fun set(other: Manifold) {
        normal.x = other.normal.x; normal.y = other.normal.y
        points.clear()
        for (point in other.points) points.add(point.copy())
    }
    override fun shift(shift: Vector2) { for (point in points) point.shiftPointDirect(shift) }
    override fun copy(): Manifold = Manifold(this)
    override fun toString() = "Manifold[Normal=$normal|Points={${points.joinToString(",")}}]"
    @kotlin.jvm.JvmName("appendPointDirect-dyn4k")
    internal fun appendPointDirect(point: ManifoldPoint) { points.add(point) }
    @kotlin.jvm.JvmName("setNormalDirect-dyn4k")
    internal fun setNormalDirect(x: Double, y: Double) { normal.x = x; normal.y = y }
    @kotlin.jvm.JvmName("pointCountDirect-dyn4k")
    internal fun pointCountDirect() = points.size
}

interface ManifoldSolver {
    fun getManifold(penetration: Penetration, convex1: Convex, transform1: Transform, convex2: Convex, transform2: Transform, manifold: Manifold): Boolean
}

open class ClippingManifoldSolver : ManifoldSolver {
    override fun getManifold(
        penetration: Penetration, convex1: Convex, transform1: Transform,
        convex2: Convex, transform2: Transform, manifold: Manifold
    ): Boolean {
        val normal = penetration.getNormal()
        val feature1: Feature = convex1.getFarthestFeature(normal, transform1)
        if (feature1 is PointFeature) {
            manifold.appendPointDirect(ManifoldPoint(ManifoldPointId.DISTANCE, feature1.getPoint()!!, penetration.getDepth()))
            manifold.setNormalDirect(-normal.x, -normal.y)
            return true
        }
        val negative = normal.getNegative()
        val feature2: Feature = convex2.getFarthestFeature(negative, transform2)
        if (feature2 is PointFeature) {
            manifold.appendPointDirect(ManifoldPoint(ManifoldPointId.DISTANCE, feature2.getPoint()!!, penetration.getDepth()))
            manifold.setNormalDirect(negative.x, negative.y)
            return true
        }
        var reference = feature1 as EdgeFeature
        var incident = feature2 as EdgeFeature
        var flipped = false
        val edge1 = reference.getEdge()!!
        val edge2 = incident.getEdge()!!
        if (abs(edge1.dot(normal)) > abs(edge2.dot(normal))) {
            val old = reference; reference = incident; incident = old; flipped = true
        }
        val referenceEdge = reference.getEdge()!!
        referenceEdge.normalize()
        val offset1 = -referenceEdge.dot(reference.getVertex1()!!.getPoint()!!)
        val clip1 = clip(incident.getVertex1()!!, incident.getVertex2()!!, referenceEdge.getNegative(), offset1)
        if (clip1.size < 2) return false
        val offset2 = referenceEdge.dot(reference.getVertex2()!!.getPoint()!!)
        val clip2 = clip(clip1[0], clip1[1], referenceEdge, offset2)
        if (clip2.size < 2) return false
        val frontNormal = referenceEdge.getRightHandOrthogonalVector()
        val frontOffset = frontNormal.dot(reference.getMaximum()!!.getPoint()!!)
        manifold.setNormalDirect(if (flipped) -frontNormal.x else frontNormal.x, if (flipped) -frontNormal.y else frontNormal.y)
        for (vertex in clip2) {
            val point = vertex.getPoint()!!
            val depth = frontNormal.dot(point) - frontOffset
            if (depth >= 0.0) {
                val id = IndexedManifoldPointId(reference.getIndex(), incident.getIndex(), vertex.getIndex(), flipped)
                manifold.appendPointDirect(ManifoldPoint(id, point, depth))
            }
        }
        return manifold.pointCountDirect() != 0
    }

    protected open fun clip(v1: PointFeature, v2: PointFeature, normal: Vector2, offset: Double): List<PointFeature> {
        val points = ArrayList<PointFeature>(2)
        val p1 = v1.getPoint()!!
        val p2 = v2.getPoint()!!
        val d1 = normal.dot(p1) - offset
        val d2 = normal.dot(p2) - offset
        if (d1 <= 0.0) points.add(v1)
        if (d2 <= 0.0) points.add(v2)
        if (d1 * d2 < 0.0) {
            val intersection = p1.to(p2)
            intersection.multiply(d1 / (d1 - d2))
            intersection.add(p1)
            points.add(PointFeature(intersection, if (d1 > 0.0) v1.getIndex() else v2.getIndex()))
        }
        return points
    }
}
