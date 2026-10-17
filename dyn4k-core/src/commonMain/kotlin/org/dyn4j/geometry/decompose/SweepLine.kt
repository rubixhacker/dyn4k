/*
 * Copyright (c) 2010-2021 William Bittle  http://www.dyn4j.org/
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

import org.dyn4j.AVLTree
import org.dyn4j.BinarySearchTree
import org.dyn4j.BinarySearchTreeSearchCriteria
import org.dyn4j.Reference
import org.dyn4j.exception.NullElementException
import org.dyn4j.exception.ValueOutOfRangeException
import org.dyn4j.geometry.Convex
import org.dyn4j.geometry.Geometry
import org.dyn4j.geometry.Segment
import org.dyn4j.geometry.Triangle
import org.dyn4j.geometry.Vector2

enum class SweepLineVertexType { START, END, SPLIT, MERGE, REGULAR }

class SweepLineVertex(val point: Vector2, val index: Int) : Comparable<SweepLineVertex> {
    var type = SweepLineVertexType.REGULAR
    lateinit var next: SweepLineVertex
    lateinit var prev: SweepLineVertex
    lateinit var left: SweepLineEdge
    lateinit var right: SweepLineEdge
    override fun compareTo(other: SweepLineVertex): Int {
        val difference = other.point.y - point.y
        val value = if (difference == 0.0) point.x - other.point.x else difference
        return if (value > 0.0) 1 else if (value < 0.0) -1 else 0
    }
    fun isLeft(edge: SweepLineEdge): Boolean = Segment.getLocation(point, edge.v0.point, edge.v1.point) < 0.0
    fun isInteriorRight(): Boolean = left.isInteriorRight()
    override fun toString(): String = point.toString()
}

class SweepLineEdge(val referenceY: Reference<Double>) : Comparable<SweepLineEdge> {
    lateinit var v0: SweepLineVertex
    lateinit var v1: SweepLineVertex
    lateinit var helper: SweepLineVertex
    var slope = 0.0
    override fun compareTo(other: SweepLineEdge): Int {
        if (this === other) return 0
        val y = referenceY.value!!
        return if (getSortValue(y) < other.getSortValue(y)) -1 else 1
    }
    fun getSortValue(y: Double): Double {
        val min = if (v1.point.x < v0.point.x) v1.point else v0.point
        return if (slope == Double.POSITIVE_INFINITY) min.x else min.x + (y - min.y) * slope
    }
    fun isInteriorRight(): Boolean {
        val difference = v0.point.y - v1.point.y
        return if (difference == 0.0) v0.point.x < v1.point.x else difference > 0.0
    }
    override fun toString(): String = "$v0 to $v1"
}

class ClosestEdgeToVertexSearchCriteria(val vertex: SweepLineVertex) : BinarySearchTreeSearchCriteria<SweepLineEdge> {
    var closest: SweepLineEdge? = null
    override fun evaluate(comparable: SweepLineEdge): Int {
        if (vertex.isLeft(comparable)) return -1
        closest = comparable
        return 1
    }
}

class SweepLineState {
    val referenceY = Reference(0.0)
    val tree: BinarySearchTree<SweepLineEdge> = AVLTree()
    lateinit var dcel: DoubleEdgeList

    fun initializeSorted(points: Array<Vector2>): List<SweepLineVertex> {
        dcel = DoubleEdgeList(points)
        val vertices = Array(points.size) { i -> SweepLineVertex(points[i], i) }
        val edges = Array(points.size) { SweepLineEdge(referenceY) }
        for (i in points.indices) {
            val vertex = vertices[i]
            val next = (i + 1) % points.size
            val previous = (i + points.size - 1) % points.size
            vertex.prev = vertices[previous]
            vertex.next = vertices[next]
            vertex.left = edges[i]
            vertex.right = edges[previous]
            vertex.type = getType(points[previous], points[i], points[next])
            val edge = edges[i]
            edge.v0 = vertex
            edge.v1 = vertices[next]
            val rise = points[i].y - points[next].y
            edge.slope = if (rise == 0.0) Double.POSITIVE_INFINITY else (points[i].x - points[next].x) / rise
        }
        return vertices.sorted()
    }

    fun getType(point0: Vector2, point: Vector2, point1: Vector2): SweepLineVertexType {
        val v1 = point0.to(point)
        val v2 = point.to(point1)
        if (v1.isZero() || v2.isZero()) throw IllegalArgumentException("The given simple polygon has coincident vertices")
        val cross = v1.cross(v2)
        val below0 = isBelow(point, point0)
        val below1 = isBelow(point, point1)
        if (below0 && below1) return if (cross > 0.0) SweepLineVertexType.END else SweepLineVertexType.MERGE
        if (!below0 && !below1) return if (cross > 0.0) SweepLineVertexType.START else SweepLineVertexType.SPLIT
        return SweepLineVertexType.REGULAR
    }

    fun isBelow(p: Vector2, q: Vector2): Boolean = p.y < q.y || p.y == q.y && p.x > q.x
}

open class SweepLine : AbstractDecomposer(), Triangulator {
    override fun decompose(vararg points: Vector2?): List<Convex> {
        val dcel = createTriangulation(*points)
        dcel.hertelMehlhorn()
        return dcel.getConvexDecomposition()
    }

    override fun triangulate(vararg points: Vector2?): List<Triangle> = createTriangulation(*points).getTriangulation()

    fun createTriangulation(vararg points: Vector2?): DoubleEdgeList {
        if (points.size < 4) throw ValueOutOfRangeException(
            "points.length", points.size, ValueOutOfRangeException.MUST_BE_GREATER_THAN_OR_EQUAL_TO, 4
        )
        val source = Array(points.size) { i -> points[i] ?: throw NullElementException("points", i) }
        if (Geometry.getWinding(*source) < 0.0) {
            source.reverse()
            reverseInput(points)
        }
        val state = SweepLineState()
        val queue = state.initializeSorted(source)
        for (vertex in queue) when (vertex.type) {
            SweepLineVertexType.START -> start(vertex, state)
            SweepLineVertexType.END -> end(vertex, state)
            SweepLineVertexType.SPLIT -> split(vertex, state)
            SweepLineVertexType.MERGE -> merge(vertex, state)
            SweepLineVertexType.REGULAR -> regular(vertex, state)
        }
        state.dcel.triangulateYMonotonePolygons()
        return state.dcel
    }

    fun start(vertex: SweepLineVertex, state: SweepLineState) {
        val edge = vertex.left
        state.referenceY.value = vertex.point.y
        state.tree.insert(edge)
        edge.helper = vertex
    }

    fun end(vertex: SweepLineVertex, state: SweepLineState) {
        val edge = vertex.right
        if (edge.helper.type == SweepLineVertexType.MERGE) state.dcel.addHalfEdges(vertex.index, edge.helper.index)
        state.referenceY.value = vertex.point.y
        state.tree.remove(edge)
    }

    fun split(vertex: SweepLineVertex, state: SweepLineState) {
        val edge = state.tree.search(ClosestEdgeToVertexSearchCriteria(vertex))!!.closest
            ?: throw IllegalArgumentException("The input must be a simple polygon")
        state.dcel.addHalfEdges(vertex.index, edge.helper.index)
        edge.helper = vertex
        state.referenceY.value = vertex.point.y
        state.tree.insert(vertex.left)
        vertex.left.helper = vertex
    }

    fun merge(vertex: SweepLineVertex, state: SweepLineState) {
        val previous = vertex.right
        if (previous.helper.type == SweepLineVertexType.MERGE) state.dcel.addHalfEdges(vertex.index, previous.helper.index)
        state.referenceY.value = vertex.point.y
        state.tree.remove(previous)
        val edge = state.tree.search(ClosestEdgeToVertexSearchCriteria(vertex))!!.closest
            ?: throw IllegalArgumentException("The input must be a simple polygon")
        if (edge.helper.type == SweepLineVertexType.MERGE) state.dcel.addHalfEdges(vertex.index, edge.helper.index)
        edge.helper = vertex
    }

    fun regular(vertex: SweepLineVertex, state: SweepLineState) {
        if (vertex.isInteriorRight()) {
            if (vertex.right.helper.type == SweepLineVertexType.MERGE) {
                state.dcel.addHalfEdges(vertex.index, vertex.right.helper.index)
            }
            state.referenceY.value = vertex.point.y
            state.tree.remove(vertex.right)
            state.tree.insert(vertex.left)
            vertex.left.helper = vertex
        } else {
            val edge = state.tree.search(ClosestEdgeToVertexSearchCriteria(vertex))!!.closest
                ?: throw IllegalArgumentException("The input must be a simple polygon")
            if (edge.helper.type == SweepLineVertexType.MERGE) state.dcel.addHalfEdges(vertex.index, edge.helper.index)
            edge.helper = vertex
        }
    }
}
