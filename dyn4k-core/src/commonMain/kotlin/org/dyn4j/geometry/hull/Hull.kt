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
package org.dyn4j.geometry.hull

import org.dyn4j.exception.NullElementException
import org.dyn4j.geometry.RobustGeometry
import org.dyn4j.geometry.Vector2

interface HullGenerator {
    fun generate(vararg points: Vector2?): Array<out Vector2?>
    fun generate(points: List<Vector2?>): List<Vector2?>
}

abstract class AbstractHullGenerator : HullGenerator {
    override fun generate(points: List<Vector2?>): List<Vector2?> = generate(*points.toTypedArray()).asList()
}

internal class MinXYPointComparator : Comparator<Vector2> {
    override fun compare(p1: Vector2, p2: Vector2): Int {
        var diff = p1.x - p2.x
        if (diff == 0.0) diff = p1.y - p2.y
        return if (diff > 0.0) 1 else if (diff < 0.0) -1 else 0
    }
}

internal class ReferencePointComparator(val reference: Vector2) : Comparator<Vector2> {
    override fun compare(p1: Vector2, p2: Vector2): Int {
        val location = RobustGeometry.getLocation(p2, p1, reference)
        val sign = if (location > 0.0) 1 else if (location < 0.0) -1 else 0
        return if (sign == 0) reference.distanceSquared(p1).compareTo(reference.distanceSquared(p2)) else sign
    }
}

open class MonotoneChain : AbstractHullGenerator() {
    override fun generate(vararg points: Vector2?): Array<out Vector2?> {
        if (points.size <= 2) return points
        val sorted = points.requirePoints()
        sorted.sortWith(MinXYPointComparator())
        writeSorted(points, sorted)
        var minmin = 0
        var minmax = 0
        var maxmin = 0
        var maxmax = 0
        for (i in 1 until sorted.size) {
            val p = sorted[i]
            if (p.x < sorted[minmin].x) {
                minmin = i; minmax = i
            } else if (p.x == sorted[minmin].x) {
                if (p.y > sorted[minmax].y) minmax = i
                else if (p.y < sorted[minmin].y) minmin = i
            }
            if (p.x > sorted[maxmin].x) {
                maxmin = i; maxmax = i
            } else if (p.x == sorted[maxmin].x) {
                if (p.y > sorted[maxmax].y) maxmax = i
                else if (p.y < sorted[maxmin].y) maxmin = i
            }
        }
        val lower = mutableListOf(sorted[minmin])
        val lp1 = sorted[maxmin]
        val lp2 = sorted[minmin]
        for (i in minmax + 1..maxmin) {
            val p = sorted[i]
            if (RobustGeometry.getLocation(p, lp1, lp2) >= 0.0) {
                while (lower.size >= 2) {
                    if (RobustGeometry.getLocation(p, lower[lower.size - 2], lower.last()) > 0.0) break
                    lower.removeAt(lower.lastIndex)
                }
                lower.add(p)
            }
        }
        val upper = mutableListOf(sorted[maxmax])
        val up1 = sorted[minmax]
        val up2 = sorted[maxmax]
        for (i in maxmax - 1 downTo minmax) {
            val p = sorted[i]
            if (RobustGeometry.getLocation(p, up1, up2) >= 0.0) {
                while (upper.size >= 2) {
                    if (RobustGeometry.getLocation(p, upper[upper.size - 2], upper.last()) > 0.0) break
                    upper.removeAt(upper.lastIndex)
                }
                upper.add(p)
            }
        }
        if (upper.first() === lower.last()) upper.removeAt(0)
        if (lower.first() === upper.last()) lower.removeAt(0)
        lower.addAll(upper)
        return lower.toTypedArray()
    }
}

open class GrahamScan : AbstractHullGenerator() {
    override fun generate(vararg points: Vector2?): Array<out Vector2?> {
        if (points.size <= 2) return points
        val sorted = points.requirePoints()
        var minY = sorted[0]
        for (i in 1 until sorted.size) {
            val p = sorted[i]
            if (p.y < minY.y || p.y == minY.y && p.x > minY.x) minY = p
        }
        sorted.sortWith(ReferencePointComparator(minY))
        writeSorted(points, sorted)
        val stack = mutableListOf(sorted[0], sorted[1])
        var i = 2
        while (i < sorted.size) {
            if (stack.size == 1) {
                stack.add(sorted[i++])
                continue
            }
            val location = RobustGeometry.getLocation(sorted[i], stack.last(), stack[stack.size - 2])
            if (location < 0.0) stack.add(sorted[i++]) else stack.removeAt(stack.lastIndex)
        }
        return stack.toTypedArray()
    }
}

open class GiftWrap : AbstractHullGenerator() {
    override fun generate(vararg points: Vector2?): Array<out Vector2?> {
        if (points.size <= 2) return points
        val cloud = points.requirePoints()
        val leftMost = cloud.minWith(MinXYPointComparator())
        val hull = LinkedHashSet<Vector2>()
        var current = leftMost
        do {
            hull.add(current)
            var next = if (current === cloud[0]) cloud[1] else cloud[0]
            for (j in 1 until cloud.size) {
                val test = cloud[j]
                if (test === current || test === next) continue
                val location = RobustGeometry.getLocation(test, current, next)
                if (location < 0.0) next = test
                else if (location == 0.0) {
                    val d1 = test.distanceSquared(current)
                    val d2 = next.distanceSquared(current)
                    val dot = current.to(next).dot(current.to(test))
                    if (d1 > d2 && dot >= 0.0) next = test
                    else if (current.to(next).cross(next.to(test)) < 0.0) next = test
                }
            }
            current = next
        } while (current !== leftMost)
        return hull.toTypedArray()
    }
}

class LinkedVertex(val point: Vector2) {
    var next: LinkedVertex = this
    var prev: LinkedVertex = this
    override fun toString(): String = point.toString()
}

class LinkedVertexHull() {
    lateinit var leftMost: LinkedVertex
    lateinit var rightMost: LinkedVertex
    var size: Int = 0

    constructor(point: Vector2) : this() {
        val root = LinkedVertex(point)
        leftMost = root
        rightMost = root
        size = 1
    }

    override fun toString(): String =
        "LinkedVertexHull[Size=$size|LeftMostPoint=${leftMost.point}|RightMostPoint=${rightMost.point}"

    fun toArray(): Array<Vector2> {
        val points = Array(size) { leftMost.point }
        var vertex = leftMost
        for (i in 0 until size) {
            points[i] = vertex.point
            vertex = vertex.next
        }
        return points
    }

    companion object {
        fun merge(left: LinkedVertexHull, right: LinkedVertexHull): LinkedVertexHull {
            val hull = LinkedVertexHull()
            hull.leftMost = left.leftMost
            hull.rightMost = right.rightMost
            var lu = left.rightMost
            var ru = right.leftMost
            var limitRightU = right.size - 1
            var limitLeftU = left.size - 1
            while (true) {
                val prevLu = lu
                val prevRu = ru
                while (limitRightU > 0 && RobustGeometry.getLocation(ru.next.point, lu.point, ru.point) <= 0.0) {
                    ru = ru.next; limitRightU--
                }
                while (limitLeftU > 0 && RobustGeometry.getLocation(lu.prev.point, lu.point, ru.point) <= 0.0) {
                    lu = lu.prev; limitLeftU--
                }
                if (lu === prevLu && ru === prevRu) break
            }
            var ll = left.rightMost
            var rl = right.leftMost
            var limitRightL = right.size - 1
            var limitLeftL = left.size - 1
            while (true) {
                val prevLl = ll
                val prevRl = rl
                while (limitRightL > 0 && RobustGeometry.getLocation(rl.prev.point, ll.point, rl.point) >= 0.0) {
                    rl = rl.prev; limitRightL--
                }
                while (limitLeftL > 0 && RobustGeometry.getLocation(ll.next.point, ll.point, rl.point) >= 0.0) {
                    ll = ll.next; limitLeftL--
                }
                if (ll === prevLl && rl === prevRl) break
            }
            lu.next = ru
            ru.prev = lu
            ll.prev = rl
            rl.next = ll
            var vertex = lu
            do {
                hull.size++
                vertex = vertex.next
            } while (vertex !== lu)
            return hull
        }
    }
}

open class DivideAndConquer : AbstractHullGenerator() {
    override fun generate(vararg points: Vector2?): Array<out Vector2?> {
        if (points.size <= 2) return points
        val sorted = points.requirePoints()
        sorted.sortWith(MinXYPointComparator())
        writeSorted(points, sorted)
        return divide(sorted, 0, sorted.size).toArray()
    }

    fun divide(points: Array<Vector2>, first: Int, last: Int): LinkedVertexHull {
        if (last - first == 1) return LinkedVertexHull(points[first])
        val mid = (first + last) / 2
        return LinkedVertexHull.merge(divide(points, first, mid), divide(points, mid, last))
    }
}

private fun Array<out Vector2?>.requirePoints(): Array<Vector2> =
    Array(size) { i -> this[i] ?: throw NullElementException("points", i) }

@Suppress("UNCHECKED_CAST")
private fun writeSorted(input: Array<out Vector2?>, sorted: Array<Vector2>) {
    val mutable = input as Array<Vector2?>
    for (i in sorted.indices) mutable[i] = sorted[i]
}
