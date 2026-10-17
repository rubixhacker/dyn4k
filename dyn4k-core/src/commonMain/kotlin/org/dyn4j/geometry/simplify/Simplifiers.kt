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
package org.dyn4j.geometry.simplify

import org.dyn4j.Epsilon
import org.dyn4j.exception.ValueOutOfRangeException
import org.dyn4j.geometry.AABB
import org.dyn4j.geometry.Interval
import org.dyn4j.geometry.Vector2
import kotlin.math.abs

interface Simplifier {
    fun simplify(vertices: List<Vector2?>?): List<Vector2>?
    fun simplify(vararg vertices: Vector2?): Array<Vector2>?
}

abstract class AbstractSimplifier : Simplifier {
    override fun simplify(vararg vertices: Vector2?): Array<Vector2>? = simplify(vertices.asList())?.toTypedArray()

    protected fun buildSegmentTree(start: SimplePolygonVertex): SegmentTree {
        val tree = SegmentTree()
        var vertex = start.next
        while (vertex !== start) {
            tree.add(vertex.prevSegment)
            vertex = vertex.next
        }
        tree.add(vertex.prevSegment)
        return tree
    }

    protected fun buildResult(start: SimplePolygonVertex): List<Vector2> {
        val result = mutableListOf(start.point)
        var current = start.next
        while (current !== start) {
            result.add(current.point)
            current = current.next
        }
        return result
    }

    protected fun isSelfIntersectionProduced(vertex: SimplePolygonVertex, tree: SegmentTree): Boolean {
        val p1 = vertex.prev.point
        val p2 = vertex.next.point
        val iterator = tree.getAABBDetectIterator(AABB.createFromPoints(p1, p2))
        while (iterator.hasNext()) {
            val leaf = iterator.next()
            if (vertex.index == leaf.index1 || vertex.index == leaf.index2 ||
                vertex.prev.index == leaf.index1 || vertex.prev.index == leaf.index2 ||
                vertex.next.index == leaf.index1 || vertex.next.index == leaf.index2
            ) continue
            if (intersects(p1, p2, leaf.point1, leaf.point2)) return true
        }
        return false
    }

    protected fun isSelfIntersectionProduced(
        vertex1: SimplePolygonVertex, vertex2: SimplePolygonVertex, tree: SegmentTree
    ): Boolean {
        val minimum = minOf(vertex1.index, vertex2.index)
        val maximum = maxOf(vertex1.index, vertex2.index)
        val iterator = tree.getAABBDetectIterator(AABB.createFromPoints(vertex1.point, vertex2.point))
        while (iterator.hasNext()) {
            val leaf = iterator.next()
            if (leaf.index1 >= minimum && leaf.index2 <= maximum ||
                leaf.index1 <= maximum && leaf.index2 >= minimum
            ) continue
            if (intersects(vertex1.point, vertex2.point, leaf.point1, leaf.point2)) return true
        }
        return false
    }

    protected fun intersects(a1: Vector2, a2: Vector2, b1: Vector2, b2: Vector2): Boolean {
        val a = a1.to(a2)
        val b = b1.to(b2)
        val bottom = b.cross(a)
        val top = a1.difference(b1).cross(a)
        if (abs(bottom) <= Epsilon.E) {
            if (abs(top) <= Epsilon.E) {
                a.normalize()
                val ad1 = a1.dot(a)
                val ad2 = a2.dot(a)
                val bd1 = b1.dot(a)
                val bd2 = b2.dot(a)
                if (Interval(ad1, ad2).overlaps(Interval(minOf(bd1, bd2), maxOf(bd1, bd2)))) return true
            }
            return false
        }
        if (abs(top) <= Epsilon.E) return false
        val tb = top / bottom
        if (tb <= 0.0 || tb >= 1.0) return false
        val intersection = b.product(tb).add(b1)
        val ta = intersection.difference(a1).dot(a) / a.dot(a)
        return ta > 0.0 && ta < 1.0
    }
}

open class VertexClusterReduction(val clusterTolerance: Double) : AbstractSimplifier() {
    init {
        if (clusterTolerance < 0.0) throw ValueOutOfRangeException(
            "clusterTolerance", clusterTolerance, ValueOutOfRangeException.MUST_BE_GREATER_THAN_OR_EQUAL_TO, 0.0
        )
    }

    override fun simplify(vertices: List<Vector2?>?): List<Vector2>? {
        if (vertices == null || vertices.isEmpty()) return vertices?.filterNotNull()
        val all = buildVertexList(vertices)
        if (all.isEmpty()) return emptyList()
        if (all.size == 1) return listOf(all[0].point)
        val reduced = mutableListOf(all[0].point)
        var start = all[0]
        val tree = buildSegmentTree(start)
        val toleranceSquared = clusterTolerance * clusterTolerance
        for (i in 1..all.size) {
            val vertex = all[if (i == all.size) 0 else i]
            val distanceSquared = start.point.distanceSquared(vertex.point)
            if (distanceSquared < toleranceSquared || distanceSquared == toleranceSquared && toleranceSquared == 0.0) {
                if (!isSelfIntersectionProduced(vertex, tree)) {
                    removeVertex(vertex, tree)
                    continue
                }
            }
            if (i < all.size) reduced.add(vertex.point)
            start = vertex
        }
        return reduced
    }

    protected fun buildVertexList(polygon: List<Vector2?>): List<SimplePolygonVertex> {
        val result = mutableListOf<SimplePolygonVertex>()
        var previous: SimplePolygonVertex? = null
        for (i in polygon.indices) {
            val point = polygon[i] ?: continue
            var nextPoint: Vector2? = null
            for (j in i + 1..polygon.size) {
                nextPoint = polygon[if (j == polygon.size) 0 else j]
                if (nextPoint != null) break
            }
            val vertex = SimplePolygonVertex(result.size, point)
            if (nextPoint != null) vertex.nextSegment = SegmentTreeLeaf(point, nextPoint, result.size, result.size + 1)
            if (previous != null) {
                vertex.prevSegment = previous.nextSegment
                previous.next = vertex
                vertex.prev = previous
            }
            previous = vertex
            result.add(vertex)
        }
        if (result.isNotEmpty()) {
            val first = result.first()
            val last = result.last()
            first.prev = last
            last.next = first
            val closing = SegmentTreeLeaf(last.point, first.point, last.index, first.index)
            first.prevSegment = closing
            last.nextSegment = closing
        }
        return result
    }

    private fun removeVertex(vertex: SimplePolygonVertex, tree: SegmentTree) {
        val previous = vertex.prev
        val next = vertex.next
        val previousSegment = vertex.prevSegment
        val nextSegment = vertex.nextSegment
        previous.next = next
        next.prev = previous
        val replacement = SegmentTreeLeaf(previous.point, next.point, previous.index, next.index)
        previous.nextSegment = replacement
        next.prevSegment = replacement
        tree.remove(previousSegment)
        tree.remove(nextSegment)
        tree.add(replacement)
    }
}

class DouglasPeucker(clusterTolerance: Double, val epsilon: Double) : VertexClusterReduction(clusterTolerance) {
    init {
        if (epsilon < 0.0) throw ValueOutOfRangeException(
            "epsilon", epsilon, ValueOutOfRangeException.MUST_BE_GREATER_THAN_OR_EQUAL_TO, 0.0
        )
    }

    override fun simplify(vertices: List<Vector2?>?): List<Vector2>? {
        if (vertices == null) return null
        val clustered = super.simplify(vertices)!!
        if (clustered.size < 4) return clustered
        val nodes = buildVertexList(clustered)
        val tree = buildSegmentTree(nodes[0])
        val end = getFartherestVertexFromVertex(0, clustered)
        val first = douglasPeucker(nodes.subList(0, end + 1), tree)
        val second = douglasPeucker(nodes.subList(end, clustered.size), tree)
        return first.dropLast(1) + second
    }

    private fun douglasPeucker(polyline: List<SimplePolygonVertex>, tree: SegmentTree): List<Vector2> {
        if (polyline.size < 3) return polyline.map { it.point }
        val start = polyline.first()
        val end = polyline.last()
        val farthest = getFarthestVertexFromLine(start, end, polyline)
        if (farthest.distance >= epsilon || isSelfIntersectionProduced(start, end, tree)) {
            val first = douglasPeucker(polyline.subList(0, farthest.index + 1), tree)
            val second = douglasPeucker(polyline.subList(farthest.index, polyline.size), tree)
            return first.dropLast(1) + second
        }
        var vertex = start
        while (vertex !== end) {
            tree.remove(vertex.nextSegment)
            vertex = vertex.next
        }
        start.next = end
        end.prev = start
        val replacement = SegmentTreeLeaf(start.point, end.point, start.index, end.index)
        start.nextSegment = replacement
        end.prevSegment = replacement
        tree.add(replacement)
        return listOf(start.point, end.point)
    }

    private fun getFartherestVertexFromVertex(index: Int, polygon: List<Vector2>): Int {
        var distance = 0.0
        var winner = -1
        val vertex = polygon[index]
        for (i in polygon.indices) {
            val test = vertex.distanceSquared(polygon[i])
            if (test > distance) {
                distance = test
                winner = i
            }
        }
        return winner
    }

    private fun getFarthestVertexFromLine(
        first: SimplePolygonVertex, last: SimplePolygonVertex, polyline: List<SimplePolygonVertex>
    ): FarthestVertex {
        var index = -1
        var distance = 0.0
        val normal = first.point.to(last.point).getLeftHandOrthogonalVector()
        normal.normalize()
        for (i in polyline.indices) {
            val test = abs(first.point.to(polyline[i].point).dot(normal))
            if (test > distance) {
                distance = test
                index = i
            }
        }
        if (index < 0) index = polyline.size / 2
        return FarthestVertex(index, distance)
    }

    private inner class FarthestVertex(val index: Int, val distance: Double)
}

class Visvalingam(clusterTolerance: Double, val minimumTriangleArea: Double) : VertexClusterReduction(clusterTolerance) {
    init {
        if (minimumTriangleArea < 0.0) throw ValueOutOfRangeException(
            "minimumTriangleArea", minimumTriangleArea, ValueOutOfRangeException.MUST_BE_GREATER_THAN_OR_EQUAL_TO, 0.0
        )
    }

    override fun simplify(vertices: List<Vector2?>?): List<Vector2>? {
        if (vertices == null) return null
        val clustered = super.simplify(vertices)!!
        if (clustered.size < 4) return clustered
        return visvalingam(clustered)
    }

    private fun visvalingam(polygon: List<Vector2>): List<Vector2> {
        val queue = buildTriangleAreaQueue(polygon)
        val tree = buildSegmentTree(queue.peek())
        while (!queue.isEmpty()) {
            val vertex = queue.poll()
            if (vertex.area >= minimumTriangleArea) return buildResult(vertex)
            if (isSelfIntersectionProduced(vertex, tree)) continue
            if (removeVertex(vertex, queue, tree)) break
        }
        return emptyList()
    }

    private fun buildTriangleAreaQueue(polygon: List<Vector2>): AreaPriorityQueue {
        val nodes = MutableList(polygon.size) { i -> AreaTrackedVertex(i, polygon[i]) }
        for (i in nodes.indices) {
            val previous = nodes[(i + nodes.size - 1) % nodes.size]
            val next = nodes[(i + 1) % nodes.size]
            val vertex = nodes[i]
            vertex.prev = previous
            vertex.next = next
            vertex.area = getTriangleArea(previous.point, vertex.point, next.point)
            vertex.nextSegment = SegmentTreeLeaf(vertex.point, next.point, vertex.index, next.index)
        }
        val queue = AreaPriorityQueue()
        for (vertex in nodes) {
            vertex.prevSegment = vertex.prev.nextSegment
            queue.add(vertex)
        }
        return queue
    }

    private fun removeVertex(
        vertex: AreaTrackedVertex, queue: AreaPriorityQueue, tree: SegmentTree
    ): Boolean {
        val previous = vertex.prev as AreaTrackedVertex
        val next = vertex.next as AreaTrackedVertex
        val previousSegment = vertex.prevSegment
        val nextSegment = vertex.nextSegment
        previous.next = next
        next.prev = previous
        previous.area = getTriangleArea(previous.prev.point, previous.point, next.point)
        next.area = getTriangleArea(previous.point, next.point, next.next.point)
        val replacement = SegmentTreeLeaf(previous.point, next.point, previous.index, next.index)
        previous.nextSegment = replacement
        next.prevSegment = replacement
        tree.remove(previousSegment)
        tree.remove(nextSegment)
        tree.add(replacement)
        queue.remove(previous)
        queue.remove(next)
        queue.add(previous)
        queue.add(next)
        return previous === next
    }

    private fun getTriangleArea(v0: Vector2, v1: Vector2, v2: Vector2): Double = abs(
        (v0.x * (v1.y - v2.y) + v1.x * (v2.y - v0.y) + v2.x * (v0.y - v1.y)) * 0.5
    )

    private inner class AreaTrackedVertex(index: Int, point: Vector2) :
        SimplePolygonVertex(index, point), Comparable<AreaTrackedVertex> {
        var area = 0.0
        override fun compareTo(other: AreaTrackedVertex): Int {
            val difference = area - other.area
            return if (difference < 0.0) -1 else if (difference > 0.0) 1 else 0
        }
        override fun toString(): String = point.toString()
    }

    private class AreaPriorityQueue {
        private val heap = mutableListOf<AreaTrackedVertex>()
        fun isEmpty(): Boolean = heap.isEmpty()
        fun peek(): AreaTrackedVertex = heap.first()
        fun add(vertex: AreaTrackedVertex) {
            heap.add(vertex)
            siftUp(heap.lastIndex, vertex)
        }
        fun poll(): AreaTrackedVertex {
            val result = heap.first()
            val last = heap.removeAt(heap.lastIndex)
            if (heap.isNotEmpty()) siftDown(0, last)
            return result
        }
        fun remove(vertex: AreaTrackedVertex) {
            val index = heap.indexOf(vertex)
            if (index < 0) return
            val last = heap.removeAt(heap.lastIndex)
            if (index < heap.size) {
                siftDown(index, last)
                if (heap[index] === last) siftUp(index, last)
            }
        }
        private fun compare(a: AreaTrackedVertex, b: AreaTrackedVertex): Int {
            val difference = a.area - b.area
            return if (difference < 0.0) -1 else if (difference > 0.0) 1 else 0
        }
        private fun siftUp(index: Int, vertex: AreaTrackedVertex) {
            var k = index
            while (k > 0) {
                val parent = (k - 1) ushr 1
                val candidate = heap[parent]
                if (compare(vertex, candidate) >= 0) break
                heap[k] = candidate
                k = parent
            }
            heap[k] = vertex
        }
        private fun siftDown(index: Int, vertex: AreaTrackedVertex) {
            var k = index
            val half = heap.size ushr 1
            while (k < half) {
                var child = (k shl 1) + 1
                var candidate = heap[child]
                val right = child + 1
                if (right < heap.size && compare(candidate, heap[right]) > 0) {
                    child = right
                    candidate = heap[child]
                }
                if (compare(vertex, candidate) <= 0) break
                heap[k] = candidate
                k = child
            }
            heap[k] = vertex
        }
    }
}
