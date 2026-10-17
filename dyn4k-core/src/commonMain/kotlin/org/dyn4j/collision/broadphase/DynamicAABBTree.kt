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
package org.dyn4j.collision.broadphase

import kotlin.math.max
import org.dyn4j.collision.CollisionPair
import org.dyn4j.geometry.AABB
import org.dyn4j.geometry.Ray
import org.dyn4j.geometry.Vector2

internal open class DynamicAABBTreeNode {
    var left: DynamicAABBTreeNode? = null
    var right: DynamicAABBTreeNode? = null
    var parent: DynamicAABBTreeNode? = null
    var height = 0
    val aabb = AABB(0.0, 0.0, 0.0, 0.0)
    open fun isLeaf() = left == null
    override fun toString() = "DynamicAABBTreeNode[AABB=$aabb|Height=$height]"
}

internal class DynamicAABBTreeLeaf<T>(val item: T) : DynamicAABBTreeNode() {
    override fun toString() = "DynamicAABBTreeLeaf[Item=$item|AABB=$aabb|Height=$height]"
}

class DynamicAABBTree<T> : AbstractBroadphaseDetector<T> {
    private var root: DynamicAABBTreeNode? = null
    private val leaves: MutableMap<T, DynamicAABBTreeLeaf<T>>
    private val updated: MutableMap<T, DynamicAABBTreeLeaf<T>?>
    private val updatedAABB = AABB(0.0, 0.0, 0.0, 0.0)

    constructor(filter: BroadphaseFilter<T>, producer: AABBProducer<T>, expansion: AABBExpansionMethod<T>) :
        this(filter, producer, expansion, BroadphaseDetector.DEFAULT_INITIAL_CAPACITY)
    constructor(filter: BroadphaseFilter<T>, producer: AABBProducer<T>, expansion: AABBExpansionMethod<T>, initialCapacity: Int) :
        super(filter, producer, expansion) {
        leaves = LinkedHashMap(initialCapacity * 4 / 3 + 1)
        updated = LinkedHashMap(initialCapacity * 4 / 3 + 1)
    }

    override fun getAABB(item: T): AABB {
        val node = leaves[item]
        if (node != null) return node.aabb
        val aabb = aabbProducer.compute(item)
        if (aabb.isDegenerate()) return aabb
        aabbExpansionMethod.expand(item, aabb)
        return aabb
    }
    override fun add(item: T) {
        val node = leaves[item]
        if (node != null) updateNode(item, node) else addNode(item)
    }
    private fun addNode(item: T) {
        aabbProducer.compute(item, updatedAABB)
        aabbExpansionMethod.expand(item, updatedAABB)
        val node = DynamicAABBTreeLeaf(item)
        node.aabb.set(updatedAABB)
        leaves[item] = node
        insert(node)
        if (updateTrackingEnabled) updated[item] = node
    }
    override fun remove(item: T): Boolean {
        val node = leaves.remove(item) ?: return false
        updated.remove(item)
        removeNode(node)
        return true
    }
    override fun update() { for (node in leaves.values) update(node.item) }
    override fun update(item: T) {
        val node = leaves[item]
        if (node != null) updateNode(item, node) else addNode(item)
    }
    private fun updateNode(item: T, node: DynamicAABBTreeLeaf<T>) {
        aabbProducer.compute(item, updatedAABB)
        val newContainedInOld = node.aabb.contains(updatedAABB)
        aabbExpansionMethod.expand(item, updatedAABB)
        if (newContainedInOld) {
            val ratio = node.aabb.getPerimeter() / updatedAABB.getPerimeter()
            if (ratio <= AABB_REDUCTION_RATIO) return
        }
        removeNode(node)
        node.aabb.set(updatedAABB)
        insert(node)
        if (updateTrackingEnabled) updated[item] = node
    }
    override fun isUpdated(item: T): Boolean {
        if (!leaves.containsKey(item)) return false
        if (!updateTrackingEnabled) return true
        return updated.containsKey(item)
    }
    override fun setUpdated(item: T) {
        if (!updateTrackingEnabled) return
        updated[item] = leaves[item]
    }
    override fun setUpdateTrackingEnabled(flag: Boolean) {
        if (updateTrackingEnabled != flag && !flag) updated.clear()
        super.setUpdateTrackingEnabled(flag)
    }
    override fun clearUpdates() { updated.clear() }
    override fun contains(item: T) = leaves.containsKey(item)
    override fun clear() { leaves.clear(); updated.clear(); root = null }
    override fun size() = leaves.size
    override fun detectIterator(forceFullDetection: Boolean): MutableIterator<CollisionPair<T>> =
        if (forceFullDetection || !updateTrackingEnabled) DetectPairsIterator(leaves.values.iterator())
        else DetectPairsIterator(updated.values.iterator())
    override fun detectIterator(aabb: AABB): MutableIterator<T> = DetectAABBIterator(aabb)
    override fun raycastIterator(ray: Ray, length: Double): MutableIterator<T> = DetectRayIterator(ray, length)
    override fun shift(shift: Vector2) { shiftNode(root, shift) }
    private fun shiftNode(node: DynamicAABBTreeNode?, shift: Vector2) {
        if (node == null) return
        node.aabb.translate(shift)
        shiftNode(node.left, shift)
        shiftNode(node.right, shift)
    }
    override fun isUpdateTrackingSupported() = true

    private fun insert(item: DynamicAABBTreeNode) {
        if (root == null) { root = item; return }
        val temp = AABB(0.0, 0.0, 0.0, 0.0)
        val itemAABB = item.aabb
        var node = root!!
        while (!node.isLeaf()) {
            val perimeter = node.aabb.getPerimeter()
            val unionPerimeter = temp.set(node.aabb).union(itemAABB).getPerimeter()
            val cost = 2.0 * unionPerimeter
            val descendCost = 2.0 * (unionPerimeter - perimeter)
            val left = node.left!!
            val right = node.right!!
            val costLeft = if (left.isLeaf()) temp.union(left.aabb, itemAABB).getPerimeter() + descendCost
                else temp.union(left.aabb, itemAABB).getPerimeter() - left.aabb.getPerimeter() + descendCost
            val costRight = if (right.isLeaf()) temp.union(right.aabb, itemAABB).getPerimeter() + descendCost
                else temp.union(right.aabb, itemAABB).getPerimeter() - right.aabb.getPerimeter() + descendCost
            if (cost < costLeft && cost < costRight) break
            node = if (costLeft < costRight) left else right
        }
        val parent = node.parent
        val newParent = DynamicAABBTreeNode()
        newParent.parent = parent
        newParent.aabb.union(node.aabb, itemAABB)
        newParent.height = node.height + 1
        if (parent != null) {
            if (parent.left === node) parent.left = newParent else parent.right = newParent
        } else root = newParent
        newParent.left = node
        newParent.right = item
        node.parent = newParent
        item.parent = newParent
        node = item.parent!!
        while (true) {
            node = balance(node)
            val left = node.left!!
            val right = node.right!!
            node.height = 1 + max(left.height, right.height)
            node.aabb.union(left.aabb, right.aabb)
            node = node.parent ?: break
        }
    }

    private fun removeNode(node: DynamicAABBTreeNode) {
        if (root == null) return
        if (node === root) { root = null; return }
        val parent = node.parent!!
        val grandparent = parent.parent
        val other = if (parent.left === node) parent.right!! else parent.left!!
        if (grandparent != null) {
            if (grandparent.left === parent) grandparent.left = other else grandparent.right = other
            other.parent = grandparent
            var current: DynamicAABBTreeNode? = grandparent
            while (current != null) {
                current = balance(current)
                val left = current.left!!
                val right = current.right!!
                current.height = 1 + max(left.height, right.height)
                current.aabb.union(left.aabb, right.aabb)
                current = current.parent
            }
        } else { root = other; other.parent = null }
    }

    private fun balance(node: DynamicAABBTreeNode): DynamicAABBTreeNode {
        val a = node
        if (a.isLeaf() || a.height < 2) return a
        val b = a.left!!
        val c = a.right!!
        val balance = c.height - b.height
        if (balance > 1) {
            val f = c.left!!
            val g = c.right!!
            c.left = a; c.parent = a.parent; a.parent = c
            if (c.parent != null) {
                if (c.parent!!.left === a) c.parent!!.left = c else c.parent!!.right = c
            } else root = c
            if (f.height > g.height) {
                c.right = f; a.right = g; g.parent = a
                a.aabb.union(b.aabb, g.aabb); c.aabb.union(a.aabb, f.aabb)
                a.height = 1 + max(b.height, g.height); c.height = 1 + max(a.height, f.height)
            } else {
                c.right = g; a.right = f; f.parent = a
                a.aabb.union(b.aabb, f.aabb); c.aabb.union(a.aabb, g.aabb)
                a.height = 1 + max(b.height, f.height); c.height = 1 + max(a.height, g.height)
            }
            return c
        }
        if (balance < -1) {
            val d = b.left!!
            val e = b.right!!
            b.left = a; b.parent = a.parent; a.parent = b
            if (b.parent != null) {
                if (b.parent!!.left === a) b.parent!!.left = b else b.parent!!.right = b
            } else root = b
            if (d.height > e.height) {
                b.right = d; a.left = e; e.parent = a
                a.aabb.union(c.aabb, e.aabb); b.aabb.union(a.aabb, d.aabb)
                a.height = 1 + max(c.height, e.height); b.height = 1 + max(a.height, d.height)
            } else {
                b.right = e; a.left = d; d.parent = a
                a.aabb.union(c.aabb, d.aabb); b.aabb.union(a.aabb, e.aabb)
                a.height = 1 + max(c.height, d.height); b.height = 1 + max(a.height, e.height)
            }
            return b
        }
        return a
    }

    fun getHeight() = root?.height ?: 0
    fun getPerimeterRatio(): Double {
        val rootNode = root ?: return 0.0
        return perimeterTotal(rootNode) / rootNode.aabb.getPerimeter()
    }
    private fun perimeterTotal(node: DynamicAABBTreeNode?): Double =
        if (node == null) 0.0 else node.aabb.getPerimeter() + perimeterTotal(node.left) + perimeterTotal(node.right)
    override fun optimize() {
        if (root == null) return
        root = null
        val sorted = ArrayList(leaves.values)
        sorted.sortWith { first, second ->
            val difference = second.aabb.getPerimeter() - first.aabb.getPerimeter()
            if (difference < 0.0) -1 else if (difference > 0.0) 1 else 0
        }
        for (leaf in sorted) {
            leaf.height = 0; leaf.left = null; leaf.right = null; leaf.parent = null
            insert(leaf)
        }
    }
    @kotlin.jvm.JvmName("isValid")
    internal fun isValid(): Boolean = isValid(root)
    @kotlin.jvm.JvmName("isValid")
    internal fun isValid(node: DynamicAABBTreeNode?): Boolean {
        if (node == null) return true
        if (node === root && node.parent != null) return false
        val left = node.left
        val right = node.right
        if (node.isLeaf()) return node is DynamicAABBTreeLeaf<*> && node.left == null && node.right == null && node.height == 0 && node.item != null
        if (!node.aabb.contains(left!!.aabb)) return false
        if (right != null && !node.aabb.contains(right.aabb)) return false
        if (left.parent !== node || right?.parent !== node) return false
        return isValid(left) && isValid(right)
    }

    private inner class DetectPairsIterator(private val iterator: MutableIterator<out DynamicAABBTreeLeaf<T>?>) : MutableIterator<CollisionPair<T>> {
        private val tested = HashMap<T, Boolean>()
        private var currentLeaf: DynamicAABBTreeLeaf<T>? = null
        private var currentNode: DynamicAABBTreeNode? = null
        private val currentPair = BroadphasePair<T>()
        private val nextPair = BroadphasePair<T>()
        private var nextReady = findNext()
        override fun hasNext() = nextReady
        override fun next(): CollisionPair<T> {
            if (!nextReady) throw NoSuchElementException()
            currentPair.first = nextPair.first; currentPair.second = nextPair.second
            nextReady = findNext()
            return currentPair
        }
        override fun remove(): Unit = throw UnsupportedOperationException()
        private fun findNext(): Boolean {
            while (iterator.hasNext() || currentLeaf != null) {
                if (currentLeaf == null) currentLeaf = iterator.next()
                if (currentNode == null) currentNode = root
                if (findNextForCurrentLeaf()) return true
            }
            return false
        }
        private fun findNextForCurrentLeaf(): Boolean {
            var found = false
            val current = currentLeaf!!
            var test = currentNode
            while (test != null) {
                if (test.aabb.overlaps(current.aabb)) {
                    if (test.left != null) { test = test.left; continue }
                    val leaf = test as DynamicAABBTreeLeaf<T>
                    if (broadphaseFilter.isAllowed(leaf.item, current.item) && !tested.containsKey(leaf.item)) {
                        nextPair.first = current.item; nextPair.second = leaf.item; found = true
                    }
                }
                var nextNodeFound = false
                while (test!!.parent != null) {
                    if (test === test.parent!!.left) {
                        test = test.parent!!.right
                        nextNodeFound = true
                        break
                    }
                    test = test.parent
                }
                currentNode = test
                if (!nextNodeFound) {
                    tested[currentLeaf!!.item] = true
                    currentLeaf = null; currentNode = null
                    break
                }
                if (found) break
            }
            return found
        }
    }

    private inner class DetectAABBIterator(private val aabb: AABB) : MutableIterator<T> {
        private var currentNode = root
        private var nextItem: T? = null
        init { findNext() }
        override fun hasNext() = nextItem != null
        @Suppress("UNCHECKED_CAST")
        override fun next(): T {
            val item = nextItem ?: throw NoSuchElementException()
            findNext()
            return item as T
        }
        override fun remove(): Unit = throw UnsupportedOperationException()
        private fun findNext(): Boolean {
            nextItem = null
            var found = false
            var node = currentNode
            while (node != null) {
                if (aabb.overlaps(node.aabb)) {
                    if (node.left != null) { node = node.left; continue }
                    nextItem = (node as DynamicAABBTreeLeaf<T>).item
                    found = true
                }
                var nextNodeFound = false
                while (node!!.parent != null) {
                    if (node === node.parent!!.left) {
                        node = node.parent!!.right
                        nextNodeFound = true
                        break
                    }
                    node = node.parent
                }
                currentNode = node
                if (!nextNodeFound) { currentNode = null; break }
                if (found) break
            }
            return found
        }
    }

    private inner class DetectRayIterator(private val ray: Ray, length: Double) : MutableIterator<T> {
        private val length = if (length <= 0.0) Double.MAX_VALUE else length
        private val aabb: AABB
        private val invDx: Double
        private val invDy: Double
        private var currentNode = root
        private var nextItem: T? = null
        init {
            val start = ray.getStart()
            val direction = ray.getDirectionVector()
            aabb = AABB.createFromPoints(start.x, start.y, start.x + direction.x * this.length, start.y + direction.y * this.length)
            invDx = 1.0 / direction.x
            invDy = 1.0 / direction.y
            findNext()
        }
        override fun hasNext() = nextItem != null
        @Suppress("UNCHECKED_CAST")
        override fun next(): T {
            val item = nextItem ?: throw NoSuchElementException()
            findNext()
            return item as T
        }
        override fun remove(): Unit = throw UnsupportedOperationException()
        private fun findNext(): Boolean {
            nextItem = null
            var found = false
            var node = currentNode
            while (node != null) {
                if (aabb.overlaps(node.aabb)) {
                    if (node.left != null) { node = node.left; continue }
                    if (AbstractBroadphaseDetector.raycast(ray.getStart(), length, invDx, invDy, node.aabb)) {
                        nextItem = (node as DynamicAABBTreeLeaf<T>).item
                        found = true
                    }
                }
                var nextNodeFound = false
                while (node!!.parent != null) {
                    if (node === node.parent!!.left) {
                        node = node.parent!!.right
                        nextNodeFound = true
                        break
                    }
                    node = node.parent
                }
                currentNode = node
                if (!nextNodeFound) { currentNode = null; break }
                if (found) break
            }
            return found
        }
    }
}
