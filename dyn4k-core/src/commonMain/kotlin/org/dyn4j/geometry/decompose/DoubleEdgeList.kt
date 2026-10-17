/*
 * Copyright (c) 2010-2020 William Bittle  http://www.dyn4j.org/
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
import org.dyn4j.geometry.Convex
import org.dyn4j.geometry.Geometry
import org.dyn4j.geometry.Segment
import org.dyn4j.geometry.Triangle
import org.dyn4j.geometry.Vector2

class DoubleEdgeListVertex(val point: Vector2) {
    lateinit var leaving: DoubleEdgeListHalfEdge
    fun getEdgeTo(node: DoubleEdgeListVertex): DoubleEdgeListHalfEdge? {
        if (!::leaving.isInitialized) return null
        if (leaving.twin.origin === node) return leaving
        var edge = leaving.twin.next
        while (edge !== leaving) {
            if (edge.twin.origin === node) return edge
            edge = edge.twin.next
        }
        return null
    }
    override fun toString(): String = point.toString()
}

class DoubleEdgeListHalfEdge {
    lateinit var origin: DoubleEdgeListVertex
    lateinit var twin: DoubleEdgeListHalfEdge
    lateinit var next: DoubleEdgeListHalfEdge
    var face: DoubleEdgeListFace? = null
    fun getDestination(): DoubleEdgeListVertex = next.origin
    fun getPrevious(): DoubleEdgeListHalfEdge {
        var edge = twin.next.twin
        while (edge.next !== this) edge = edge.next.twin
        return edge
    }
    override fun toString(): String = "$origin to ${next.origin}"
}

class DoubleEdgeListFace {
    lateinit var edge: DoubleEdgeListHalfEdge
    fun getEdgeCount(): Int {
        if (!::edge.isInitialized) return 0
        var current = edge
        var count = 1
        while (current.next !== edge) {
            count++
            current = current.next
        }
        return count
    }
    override fun toString(): String = "Face[Edge=$edge]"
}

enum class MonotoneChainType { LEFT, RIGHT, TOP, BOTTOM }
enum class MonotonePolygonType { X, Y }

class MonotoneVertex<E>(val data: E) {
    lateinit var next: MonotoneVertex<E>
    lateinit var previous: MonotoneVertex<E>
    lateinit var chainType: MonotoneChainType
    fun isAdjacent(vertex: MonotoneVertex<E>): Boolean = vertex === previous || vertex === next
    override fun toString(): String = data.toString()
}

class MonotonePolygon<E>(val type: MonotonePolygonType, val vertices: List<MonotoneVertex<E>>) {
    fun getMaximum(): MonotoneVertex<E> = vertices.first()
    fun getMinimum(): MonotoneVertex<E> = vertices.last()
    override fun toString(): String = "MonotonePolygon[Type=$type|Vertices={${vertices.joinToString(",")}}]"
}

class DoubleEdgeList(points: Array<Vector2>) {
    val vertices = mutableListOf<DoubleEdgeListVertex>()
    val edges = mutableListOf<DoubleEdgeListHalfEdge>()
    val faces = mutableListOf<DoubleEdgeListFace>()

    init { initialize(points) }

    fun initialize(points: Array<Vector2>) {
        val face = DoubleEdgeListFace()
        faces.add(face)
        var prevLeft: DoubleEdgeListHalfEdge? = null
        var prevRight: DoubleEdgeListHalfEdge? = null
        for (point in points) {
            val vertex = DoubleEdgeListVertex(point)
            val left = DoubleEdgeListHalfEdge()
            val right = DoubleEdgeListHalfEdge()
            left.face = face
            left.origin = vertex
            left.twin = right
            right.twin = left
            edges.add(left)
            edges.add(right)
            vertex.leaving = left
            vertices.add(vertex)
            if (prevLeft != null) prevLeft.next = left
            if (prevRight != null) {
                right.next = prevRight
                prevRight.origin = vertex
            }
            prevLeft = left
            prevRight = right
        }
        prevLeft!!.next = edges[0]
        edges[1].next = prevRight!!
        prevRight.origin = vertices[0]
        face.edge = edges[0]
    }

    fun addHalfEdges(i: Int, j: Int) = addHalfEdges(vertices[i], vertices[j])

    fun addHalfEdges(v1: DoubleEdgeListVertex, v2: DoubleEdgeListVertex) {
        val face = DoubleEdgeListFace()
        val left = DoubleEdgeListHalfEdge()
        val right = DoubleEdgeListHalfEdge()
        val referenceFace = getReferenceFace(v1, v2)
        val prev1 = getPreviousEdge(v1, referenceFace)
        val prev2 = getPreviousEdge(v2, referenceFace)
        if (Segment.getSegmentIntersection(
                prev1.origin.point, prev1.next.origin.point, prev2.origin.point, prev2.next.origin.point
            ) != null
        ) throw IllegalArgumentException(
            "The input must be a simple polygon. Edges ${prev1.origin.point} -> ${prev1.next.origin.point}" +
                " and ${prev2.origin.point} -> ${prev2.next.origin.point} cross each other."
        )
        face.edge = left
        referenceFace.edge = right
        left.face = face
        left.next = prev2.next
        left.origin = v1
        left.twin = right
        right.face = referenceFace
        right.next = prev1.next
        right.origin = v2
        right.twin = left
        prev1.next = left
        prev2.next = right
        var current = left.next
        while (current !== left) {
            current.face = face
            current = current.next
        }
        edges.add(left)
        edges.add(right)
        faces.add(face)
    }

    fun getPreviousEdge(vertex: DoubleEdgeListVertex, face: DoubleEdgeListFace): DoubleEdgeListHalfEdge {
        val twin = vertex.leaving.twin
        var edge = twin.next.twin
        while (edge !== twin) {
            if (edge.face === face) return edge
            edge = edge.next.twin
        }
        return edge
    }

    fun getReferenceFace(v1: DoubleEdgeListVertex, v2: DoubleEdgeListVertex): DoubleEdgeListFace {
        if (v1.leaving.face === v2.leaving.face) return v1.leaving.face!!
        var e1 = v1.leaving.twin.next.twin
        while (e1 !== v1.leaving.twin) {
            var e2 = v2.leaving.twin.next.twin
            while (e2 !== v2.leaving.twin) {
                if (e1.face === e2.face) return e1.face!!
                e2 = e2.next.twin
            }
            e1 = e1.next.twin
        }
        return v1.leaving.face!!
    }

    fun removeHalfEdges(index: Int) = removeHalfEdges(index, edges[index])
    fun removeHalfEdges(edge: DoubleEdgeListHalfEdge) = removeHalfEdges(edges.indexOf(edge), edge)
    fun removeHalfEdges(index: Int, edge: DoubleEdgeListHalfEdge) {
        val face = edge.twin.face!!
        val ePrev = edge.getPrevious()
        val tPrev = edge.twin.getPrevious()
        val eNext = edge.next
        val tNext = edge.twin.next
        ePrev.next = tNext
        tPrev.next = eNext
        face.edge = eNext
        var current = eNext
        while (current !== tNext) {
            current.face = face
            current = current.next
        }
        faces.remove(edge.face)
        edges.removeAt(index)
        edges.removeAt(index)
    }

    private fun faceVertices(face: DoubleEdgeListFace): Array<Vector2> {
        val points = mutableListOf<Vector2>()
        var edge = face.edge
        do {
            points.add(edge.origin.point)
            edge = edge.next
        } while (edge !== face.edge)
        return points.toTypedArray()
    }

    fun getConvexDecomposition(): List<Convex> = faces.map { face ->
        val points = faceVertices(face)
        if (points.size < 3) throw IllegalArgumentException("The given simple polygon has crossing edges and not supported")
        Geometry.createPolygon(*points)
    }

    fun getTriangulation(): List<Triangle> = faces.map { face ->
        val points = faceVertices(face)
        if (points.size != 3) throw IllegalArgumentException("The given simple polygon has crossing edges and not supported")
        Geometry.createTriangle(points[0], points[1], points[2])
    }

    fun triangulateYMonotonePolygons() {
        for (polygon in getYMonotonePolygons()) triangulateYMonotonePolygon(polygon)
    }

    fun triangulateYMonotonePolygon(polygon: MonotonePolygon<DoubleEdgeListVertex>) {
        val stack = mutableListOf(polygon.vertices[0], polygon.vertices[1])
        val sorted = polygon.vertices
        var i = 2
        while (stack.isNotEmpty()) {
            val v = sorted[i]
            val bottom = stack.first()
            val top = stack.last()
            if (v.isAdjacent(bottom) && !v.isAdjacent(top)) {
                while (stack.size > 1) addHalfEdges(v.data, stack.removeAt(stack.lastIndex).data)
                stack.clear()
                stack.add(top)
                stack.add(v)
            } else if (v.isAdjacent(top) && !v.isAdjacent(bottom)) {
                var size = stack.size
                while (size > 1) {
                    val vt = stack[size - 1]
                    val vt1 = stack[size - 2]
                    val p1 = v.data.point
                    val p2 = vt.data.point
                    val p3 = vt1.data.point
                    val cross = if (v.chainType == MonotoneChainType.LEFT || v.chainType == MonotoneChainType.BOTTOM) {
                        p2.to(p3).cross(p2.to(p1))
                    } else p1.to(p2).cross(p3.to(p2))
                    if (cross < -Epsilon.E) {
                        addHalfEdges(v.data, vt1.data)
                        stack.removeAt(size - 1)
                        size--
                    } else break
                }
                stack.add(v)
            } else if (v.isAdjacent(top) && v.isAdjacent(bottom)) {
                stack.removeAt(stack.lastIndex)
                while (stack.size > 1) addHalfEdges(v.data, stack.removeAt(stack.lastIndex).data)
                break
            }
            i++
        }
    }

    fun getYMonotonePolygons(): List<MonotonePolygon<DoubleEdgeListVertex>> {
        val result = mutableListOf<MonotonePolygon<DoubleEdgeListVertex>>()
        for (face in faces) {
            val size = face.getEdgeCount()
            var edge = face.edge
            val root = MonotoneVertex(edge.origin)
            edge = edge.next
            var previous = root
            var maximum = root
            while (edge !== face.edge) {
                val current = MonotoneVertex(edge.origin)
                current.previous = previous
                previous.next = current
                val p = current.data.point
                val q = maximum.data.point
                if (p.y > q.y || p.y == q.y && p.x < q.x) maximum = current
                edge = edge.next
                previous = current
            }
            root.previous = previous
            previous.next = root
            val sorted = mutableListOf(maximum)
            maximum.chainType = MonotoneChainType.LEFT
            var left = maximum.next
            var right = maximum.previous
            while (sorted.size < size) {
                val l = left.data.point
                val r = right.data.point
                if (l.y > r.y || l.y == r.y && l.x < r.x) {
                    sorted.add(left)
                    left.chainType = MonotoneChainType.LEFT
                    left = left.next
                } else {
                    sorted.add(right)
                    right.chainType = MonotoneChainType.RIGHT
                    right = right.previous
                }
            }
            sorted.last().chainType = MonotoneChainType.RIGHT
            result.add(MonotonePolygon(MonotonePolygonType.Y, sorted))
        }
        return result
    }

    fun hertelMehlhorn() {
        var i = vertices.size * 2
        while (i < edges.size) {
            val edge = edges[i]
            if (isReflex(edge.getPrevious().origin, edge.origin, edge.twin.next.next.origin) ||
                isReflex(edge.twin.getPrevious().origin, edge.twin.origin, edge.next.next.origin)
            ) {
                i += 2
                continue
            }
            removeHalfEdges(i, edge)
        }
    }

    fun isReflex(v0: DoubleEdgeListVertex, v1: DoubleEdgeListVertex, v2: DoubleEdgeListVertex): Boolean =
        v0.point.to(v1.point).cross(v1.point.to(v2.point)) < 0.0
}
