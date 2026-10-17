/*
 * Copyright (c) 2010-2026 William Bittle  http://www.dyn4j.org/
 * Copyright (c) 2010-2026 William Bittle  http://www.dyn4j.org/
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

import org.dyn4j.geometry.AABB
import org.dyn4j.geometry.Vector2
import kotlin.jvm.JvmName
import kotlin.math.max

open class SegmentTreeNode {
    @get:JvmName("getLeft-dyn4k") @set:JvmName("setLeft-dyn4k")
    var left: SegmentTreeNode? = null
    @get:JvmName("getRight-dyn4k") @set:JvmName("setRight-dyn4k")
    var right: SegmentTreeNode? = null
    @get:JvmName("getParent-dyn4k") @set:JvmName("setParent-dyn4k")
    var parent: SegmentTreeNode? = null
    @get:JvmName("getHeight-dyn4k") @set:JvmName("setHeight-dyn4k")
    var height = 0
    @get:JvmName("getAabb-dyn4k")
    val aabb = AABB(0.0, 0.0, 0.0, 0.0)
    fun isLeaf(): Boolean = left == null
    override fun toString(): String = "RTreeNode[AABB=$aabb|Height=$height]"
}

class SegmentTreeLeaf(
    val point1: Vector2, val point2: Vector2, val index1: Int, val index2: Int
) : SegmentTreeNode() {
    init { AABB.setFromPoints(point1, point2, aabb) }
    override fun toString(): String = "RTreeLeaf[P1=$point1|P2=$point2|AABB=$aabb|Height=$height]"
}

open class SimplePolygonVertex(
    @get:JvmName("getIndex-dyn4k") val index: Int,
    @get:JvmName("getPoint-dyn4k") val point: Vector2
) {
    @get:JvmName("getPrev-dyn4k") @set:JvmName("setPrev-dyn4k")
    var prev: SimplePolygonVertex? = null
    @get:JvmName("getNext-dyn4k") @set:JvmName("setNext-dyn4k")
    var next: SimplePolygonVertex? = null
    @get:JvmName("getPrevSegment-dyn4k") @set:JvmName("setPrevSegment-dyn4k")
    var prevSegment: SegmentTreeLeaf? = null
    @get:JvmName("getNextSegment-dyn4k") @set:JvmName("setNextSegment-dyn4k")
    var nextSegment: SegmentTreeLeaf? = null
    override fun toString(): String = point.toString()
}

class SegmentTree {
    private var root: SegmentTreeNode? = null

    fun add(leaf: SegmentTreeLeaf) = insert(leaf)
    fun remove(leaf: SegmentTreeLeaf) = removeNode(leaf)
    fun getAABBDetectIterator(aabb: AABB): MutableIterator<SegmentTreeLeaf> = DetectAABBIterator(aabb)

    private fun insert(item: SegmentTreeNode) {
        if (root == null) {
            root = item
            return
        }
        val temp = AABB(0.0, 0.0, 0.0, 0.0)
        val itemAabb = item.aabb
        var node = root!!
        while (!node.isLeaf()) {
            val perimeter = node.aabb.getPerimeter()
            val unionPerimeter = temp.set(node.aabb).union(itemAabb).getPerimeter()
            val cost = 2.0 * unionPerimeter
            val descendCost = 2.0 * (unionPerimeter - perimeter)
            val left = node.left!!
            val right = node.right!!
            val leftUnion = temp.union(left.aabb, itemAabb).getPerimeter()
            val costLeft = if (left.isLeaf()) leftUnion + descendCost
                else leftUnion - left.aabb.getPerimeter() + descendCost
            val rightUnion = temp.union(right.aabb, itemAabb).getPerimeter()
            val costRight = if (right.isLeaf()) rightUnion + descendCost
                else rightUnion - right.aabb.getPerimeter() + descendCost
            if (cost < costLeft && cost < costRight) break
            node = if (costLeft < costRight) left else right
        }
        val parent = node.parent
        val newParent = SegmentTreeNode()
        newParent.parent = parent
        newParent.aabb.union(node.aabb, itemAabb)
        newParent.height = node.height + 1
        if (parent != null) {
            if (parent.left === node) parent.left = newParent else parent.right = newParent
        } else root = newParent
        newParent.left = node
        newParent.right = item
        node.parent = newParent
        item.parent = newParent
        node = newParent
        while (true) {
            node = balance(node)
            val left = node.left!!
            val right = node.right!!
            node.height = 1 + max(left.height, right.height)
            node.aabb.union(left.aabb, right.aabb)
            node = node.parent ?: break
        }
    }

    private fun removeNode(node: SegmentTreeNode) {
        if (root == null) return
        if (node === root) {
            root = null
            return
        }
        val parent = node.parent!!
        val grandparent = parent.parent
        val other = if (parent.left === node) parent.right!! else parent.left!!
        if (grandparent != null) {
            if (grandparent.left === parent) grandparent.left = other else grandparent.right = other
            other.parent = grandparent
            var current: SegmentTreeNode? = grandparent
            while (current != null) {
                current = balance(current)
                val left = current.left!!
                val right = current.right!!
                current.height = 1 + max(left.height, right.height)
                current.aabb.union(left.aabb, right.aabb)
                current = current.parent
            }
        } else {
            root = other
            other.parent = null
        }
    }

    private fun balance(a: SegmentTreeNode): SegmentTreeNode {
        if (a.isLeaf() || a.height < 2) return a
        val b = a.left!!
        val c = a.right!!
        val factor = c.height - b.height
        if (factor > 1) {
            val f = c.left!!
            val g = c.right!!
            c.left = a
            c.parent = a.parent
            a.parent = c
            if (c.parent != null) {
                if (c.parent!!.left === a) c.parent!!.left = c else c.parent!!.right = c
            } else root = c
            if (f.height > g.height) {
                c.right = f
                a.right = g
                g.parent = a
                a.aabb.union(b.aabb, g.aabb)
                c.aabb.union(a.aabb, f.aabb)
                a.height = 1 + max(b.height, g.height)
                c.height = 1 + max(a.height, f.height)
            } else {
                c.right = g
                a.right = f
                f.parent = a
                a.aabb.union(b.aabb, f.aabb)
                c.aabb.union(a.aabb, g.aabb)
                a.height = 1 + max(b.height, f.height)
                c.height = 1 + max(a.height, g.height)
            }
            return c
        }
        if (factor < -1) {
            val d = b.left!!
            val e = b.right!!
            b.left = a
            b.parent = a.parent
            a.parent = b
            if (b.parent != null) {
                if (b.parent!!.left === a) b.parent!!.left = b else b.parent!!.right = b
            } else root = b
            if (d.height > e.height) {
                b.right = d
                a.left = e
                e.parent = a
                a.aabb.union(c.aabb, e.aabb)
                b.aabb.union(a.aabb, d.aabb)
                a.height = 1 + max(c.height, e.height)
                b.height = 1 + max(a.height, d.height)
            } else {
                b.right = e
                a.left = d
                d.parent = a
                a.aabb.union(c.aabb, d.aabb)
                b.aabb.union(a.aabb, e.aabb)
                a.height = 1 + max(c.height, d.height)
                b.height = 1 + max(a.height, e.height)
            }
            return b
        }
        return a
    }

    private inner class DetectAABBIterator(private val aabb: AABB) : MutableIterator<SegmentTreeLeaf> {
        private var currentNode: SegmentTreeNode? = root
        private var nextItem: SegmentTreeLeaf? = null
        init { findNext() }
        override fun hasNext(): Boolean = nextItem != null
        override fun next(): SegmentTreeLeaf {
            val item = nextItem ?: throw NoSuchElementException()
            findNext()
            return item
        }
        override fun remove(): Unit = throw UnsupportedOperationException()

        private fun findNext() {
            nextItem = null
            var node = currentNode
            while (node != null) {
                var found = false
                if (aabb.overlaps(node.aabb)) {
                    if (node.left != null) {
                        node = node.left
                        continue
                    }
                    nextItem = node as SegmentTreeLeaf
                    found = true
                }
                var nextFound = false
                while (node!!.parent != null) {
                    if (node === node.parent!!.left) {
                        node = node.parent!!.right
                        nextFound = true
                        break
                    }
                    node = node.parent
                }
                currentNode = node
                if (!nextFound) {
                    currentNode = null
                    break
                }
                if (found) break
            }
        }
    }
}
