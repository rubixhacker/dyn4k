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

import org.dyn4j.AVLTree
import org.dyn4j.BinarySearchTree
import org.dyn4j.collision.CollisionPair
import org.dyn4j.geometry.AABB
import org.dyn4j.geometry.Ray
import org.dyn4j.geometry.Vector2

class Sap<T> : AbstractBroadphaseDetector<T> {
    private var tree: BinarySearchTree<AABBBroadphaseProxy<T>> = AVLTree()
    private val nodes: MutableMap<T, AABBBroadphaseProxy<T>>
    private val updated: MutableMap<T, AABBBroadphaseProxy<T>?>
    private val updatedAABB = AABB(0.0, 0.0, 0.0, 0.0)

    constructor(filter: BroadphaseFilter<T>, producer: AABBProducer<T>, expansion: AABBExpansionMethod<T>) :
        this(filter, producer, expansion, BroadphaseDetector.DEFAULT_INITIAL_CAPACITY)
    constructor(filter: BroadphaseFilter<T>, producer: AABBProducer<T>, expansion: AABBExpansionMethod<T>, initialCapacity: Int) :
        super(filter, producer, expansion) {
        nodes = HashMap(initialCapacity * 4 / 3 + 1)
        updated = LinkedHashMap(initialCapacity * 4 / 3 + 1)
    }

    override fun add(item: T) {
        val proxy = nodes[item]
        if (proxy == null) insert(item) else update(proxy, item)
    }
    @kotlin.jvm.JvmName("insert") internal fun insert(item: T) {
        aabbProducer.compute(item, updatedAABB)
        aabbExpansionMethod.expand(item, updatedAABB)
        val proxy = AABBBroadphaseProxy(item)
        proxy.aabb.set(updatedAABB)
        nodes[item] = proxy
        if (updateTrackingEnabled) updated[item] = proxy
        tree.insert(proxy)
    }
    override fun remove(item: T): Boolean {
        val proxy = nodes.remove(item) ?: return false
        tree.remove(proxy)
        updated.remove(item)
        return true
    }
    override fun update() { for (proxy in nodes.values) update(proxy.item) }
    override fun update(item: T) {
        val proxy = nodes[item]
        if (proxy != null) update(proxy, item) else insert(item)
    }
    @kotlin.jvm.JvmName("update") internal fun update(proxy: AABBBroadphaseProxy<T>, item: T) {
        aabbProducer.compute(item, updatedAABB)
        val newContainedInOld = proxy.aabb.contains(updatedAABB)
        aabbExpansionMethod.expand(item, updatedAABB)
        if (newContainedInOld) {
            val ratio = proxy.aabb.getPerimeter() / updatedAABB.getPerimeter()
            if (ratio <= AABB_REDUCTION_RATIO) return
        }
        tree.remove(proxy)
        proxy.aabb.set(updatedAABB)
        if (updateTrackingEnabled) updated[item] = proxy
        tree.insert(proxy)
    }
    override fun isUpdated(item: T): Boolean {
        if (!nodes.containsKey(item)) return false
        if (!updateTrackingEnabled) return true
        return updated.containsKey(item)
    }
    override fun setUpdated(item: T) {
        if (!updateTrackingEnabled) return
        updated[item] = nodes[item]
    }
    override fun clearUpdates() { updated.clear() }
    override fun getAABB(item: T): AABB {
        val proxy = nodes[item]
        if (proxy != null) return proxy.aabb
        val aabb = aabbProducer.compute(item)
        if (aabb.isDegenerate()) return aabb
        aabbExpansionMethod.expand(item, aabb)
        return aabb
    }
    override fun contains(item: T) = nodes.containsKey(item)
    override fun clear() { nodes.clear(); tree.clear(); updated.clear() }
    override fun size() = nodes.size
    override fun isUpdateTrackingSupported() = true
    override fun setUpdateTrackingEnabled(flag: Boolean) {
        if (updateTrackingEnabled != flag && !flag) updated.clear()
        super.setUpdateTrackingEnabled(flag)
    }
    override fun detectIterator(forceFullDetection: Boolean): MutableIterator<CollisionPair<T>> =
        if (forceFullDetection || !updateTrackingEnabled) DetectPairsIterator(tree.iterator())
        else DetectPairsIterator(updated.values.iterator())
    override fun detectIterator(aabb: AABB): MutableIterator<T> = DetectAABBIterator(aabb)
    override fun raycastIterator(ray: Ray, length: Double): MutableIterator<T> = DetectRayIterator(ray, length)
    override fun shift(shift: Vector2) {
        val iterator = tree.iterator()
        while (iterator.hasNext()) iterator.next().aabb.translate(shift)
    }
    override fun optimize() {}

    private inner class DetectPairsIterator(private val outer: MutableIterator<out AABBBroadphaseProxy<T>?>) : MutableIterator<CollisionPair<T>> {
        private val tested = HashMap<T, Boolean>()
        private var current: AABBBroadphaseProxy<T>? = if (outer.hasNext()) outer.next() else null
        private var inner: MutableIterator<AABBBroadphaseProxy<T>>? = null
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
            while (current != null) {
                if (inner == null) inner = tree.tailIterator(current)
                val iterator = inner!!
                while (iterator.hasNext()) {
                    val test = iterator.next()
                    if (!broadphaseFilter.isAllowed(current!!.item, test.item)) continue
                    if (tested.containsKey(test.item)) continue
                    if (current!!.aabb.getMaxX() >= test.aabb.getMinX()) {
                        if (current!!.aabb.overlaps(test.aabb)) {
                            nextPair.first = current!!.item; nextPair.second = test.item
                            return true
                        }
                    } else break
                }
                tested[current!!.item] = true
                inner = null
                current = if (outer.hasNext()) outer.next() else null
            }
            return false
        }
    }

    private inner class DetectAABBIterator(private val aabb: AABB) : MutableIterator<T> {
        private val iterator = tree.inOrderIterator()
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
        private fun findNext() {
            nextItem = null
            while (iterator.hasNext()) {
                val test = iterator.next()
                if (aabb.getMaxX() >= test.aabb.getMinX()) {
                    if (aabb.overlaps(test.aabb)) { nextItem = test.item; return }
                } else if (test.aabb.getMinX() > aabb.getMaxX()) break
            }
        }
    }

    private inner class DetectRayIterator(private val ray: Ray, length: Double) : MutableIterator<T> {
        private val iterator = tree.inOrderIterator()
        private val length = if (length <= 0.0) Double.MAX_VALUE else length
        private val aabb: AABB
        private val invDx: Double
        private val invDy: Double
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
        private fun findNext() {
            nextItem = null
            while (iterator.hasNext()) {
                val test = iterator.next()
                if (test.aabb.getMaxX() >= aabb.getMinX()) {
                    if (aabb.overlaps(test.aabb) && AbstractBroadphaseDetector.raycast(ray.getStart(), length, invDx, invDy, test.aabb)) {
                        nextItem = test.item; return
                    }
                } else if (test.aabb.getMinX() > aabb.getMaxX()) break
            }
        }
    }
}
