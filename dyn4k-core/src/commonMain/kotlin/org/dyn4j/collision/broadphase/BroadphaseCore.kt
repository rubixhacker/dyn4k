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
import kotlin.math.min
import org.dyn4j.JvmFieldBridge
import org.dyn4j.JvmStaticBridge
import org.dyn4j.collision.AbstractCollisionItem
import org.dyn4j.collision.AbstractCollisionPair
import org.dyn4j.collision.CollisionBody
import org.dyn4j.collision.CollisionItem
import org.dyn4j.collision.CollisionPair
import org.dyn4j.collision.Collisions
import org.dyn4j.collision.Fixture
import org.dyn4j.exception.ArgumentNullException
import org.dyn4j.geometry.AABB
import org.dyn4j.geometry.Convex
import org.dyn4j.geometry.Ray
import org.dyn4j.geometry.Shiftable
import org.dyn4j.geometry.Transform
import org.dyn4j.geometry.Vector2

interface AABBProducer<T> {
    fun compute(item: T): AABB
    fun compute(item: T, result: AABB)
}

interface AABBExpansionMethod<T> {
    fun expand(item: T, aabb: AABB)
}

interface BroadphaseFilter<T> {
    fun isAllowed(first: T?, second: T?): Boolean
}

class NullAABBExpansionMethod<T> : AABBExpansionMethod<T> {
    override fun expand(item: T, aabb: AABB) {}
}

class StaticValueAABBExpansionMethod<T>(private val expansion: Double) : AABBExpansionMethod<T> {
    override fun expand(item: T, aabb: AABB) { aabb.expand(expansion) }
    fun getExpansion() = expansion
}

internal class AABBBroadphaseProxy<T>(val item: T) : Comparable<AABBBroadphaseProxy<T>> {
    val aabb = AABB(0.0, 0.0, 0.0, 0.0)
    override fun compareTo(other: AABBBroadphaseProxy<T>): Int {
        if (this === other) return 0
        val xs = listOf(aabb.getMinX() - other.aabb.getMinX(), aabb.getMinY() - other.aabb.getMinY(),
            aabb.getMaxX() - other.aabb.getMaxX(), aabb.getMaxY() - other.aabb.getMaxY())
        for (difference in xs) if (difference != 0.0) return difference.compareTo(0.0)
        return item.hashCode() - other.item.hashCode()
    }
    override fun toString() = "SapProxy[Item=$item|AABB=$aabb]"
}

internal class BroadphasePair<T> : CollisionPair<T> {
    @get:kotlin.jvm.JvmName("firstField")
    @set:kotlin.jvm.JvmName("setFirstField")
    @JvmFieldBridge
    var first: T? = null
    @get:kotlin.jvm.JvmName("secondField")
    @set:kotlin.jvm.JvmName("setSecondField")
    @JvmFieldBridge
    var second: T? = null
    constructor()
    constructor(first: T, second: T) { this.first = first; this.second = second }
    @Suppress("UNCHECKED_CAST")
    override fun getFirst(): T = first as T
    @Suppress("UNCHECKED_CAST")
    override fun getSecond(): T = second as T
    override fun copy(): BroadphasePair<T> = BroadphasePair(getFirst(), getSecond())
    override fun equals(other: Any?) = AbstractCollisionPair.equals(this, other)
    override fun hashCode() = AbstractCollisionPair.getHashCode(first, second)
    override fun toString() = "BroadphasePair[First=$first|Second=$second]"
}

internal class BroadphaseItem<T : CollisionBody<E>, E : Fixture> : AbstractCollisionItem<T, E>, CollisionItem<T, E> {
    @get:kotlin.jvm.JvmName("bodyField")
    @set:kotlin.jvm.JvmName("setBodyField")
    @JvmFieldBridge
    var body: T?
    @get:kotlin.jvm.JvmName("fixtureField")
    @set:kotlin.jvm.JvmName("setFixtureField")
    @JvmFieldBridge
    var fixture: E?
    constructor(body: T?, fixture: E?) { this.body = body; this.fixture = fixture }
    constructor(other: BroadphaseItem<T, E>) { body = other.body; fixture = other.fixture }
    override fun getBody() = body
    override fun getFixture() = fixture
    override fun copy() = BroadphaseItem(this)
    override fun equals(other: Any?) = AbstractCollisionItem.equals(this, other)
    override fun hashCode() = AbstractCollisionItem.getHashCode(body, fixture)
    override fun toString() = "BroadphaseItem[Body=${body!!.hashCode()}|Fixture=${fixture!!.hashCode()}]"
}

interface BroadphaseDetector<T> : Shiftable {
    fun add(item: T)
    fun remove(item: T): Boolean
    fun update()
    fun update(item: T)
    fun setUpdated(item: T)
    fun isUpdated(item: T): Boolean
    fun clearUpdates()
    fun getAABB(item: T): AABB
    fun contains(item: T): Boolean
    fun clear()
    fun size(): Int
    fun detect(): MutableList<CollisionPair<T>>
    fun detect(forceFullDetection: Boolean): MutableList<CollisionPair<T>>
    fun detectIterator(): MutableIterator<CollisionPair<T>>
    fun detectIterator(forceFullDetection: Boolean): MutableIterator<CollisionPair<T>>
    fun detect(aabb: AABB): MutableList<T>
    fun detectIterator(aabb: AABB): MutableIterator<T>
    fun raycast(ray: Ray, length: Double): MutableList<T>
    fun raycastIterator(ray: Ray, length: Double): MutableIterator<T>
    fun detect(a: T, b: T): Boolean
    fun detect(convex1: Convex, transform1: Transform, convex2: Convex, transform2: Transform): Boolean
    fun getAABBProducer(): AABBProducer<T>
    fun getAABBExpansionMethod(): AABBExpansionMethod<T>
    fun getBroadphaseFilter(): BroadphaseFilter<T>
    fun isUpdateTrackingSupported(): Boolean
    fun isUpdateTrackingEnabled(): Boolean
    fun setUpdateTrackingEnabled(flag: Boolean)
    fun optimize()
    companion object { const val DEFAULT_INITIAL_CAPACITY = 64 }
}

abstract class AbstractBroadphaseDetector<T> : BroadphaseDetector<T> {
    @get:kotlin.jvm.JvmName("aabbProducerField")
    @JvmFieldBridge protected val aabbProducer: AABBProducer<T>
    @get:kotlin.jvm.JvmName("aabbExpansionMethodField")
    @JvmFieldBridge protected val aabbExpansionMethod: AABBExpansionMethod<T>
    @get:kotlin.jvm.JvmName("broadphaseFilterField")
    @JvmFieldBridge protected val broadphaseFilter: BroadphaseFilter<T>
    @get:kotlin.jvm.JvmName("updateTrackingEnabledField")
    @set:kotlin.jvm.JvmName("setUpdateTrackingEnabledField")
    @JvmFieldBridge protected var updateTrackingEnabled = false

    constructor(filter: BroadphaseFilter<T>?, producer: AABBProducer<T>?, expansion: AABBExpansionMethod<T>?) {
        if (filter == null) throw ArgumentNullException("broadphaseFilter")
        if (producer == null) throw ArgumentNullException("aabbProducer")
        if (expansion == null) throw ArgumentNullException("aabbExpansionMethod")
        broadphaseFilter = filter; aabbProducer = producer; aabbExpansionMethod = expansion
    }

    override fun detect(a: T, b: T): Boolean = getAABB(a).overlaps(getAABB(b))
    override fun detect(convex1: Convex, transform1: Transform, convex2: Convex, transform2: Transform): Boolean =
        convex1.createAABB(transform1).overlaps(convex2.createAABB(transform2))
    override fun detect(): MutableList<CollisionPair<T>> = detect(true)
    override fun detect(forceFullDetection: Boolean): MutableList<CollisionPair<T>> {
        val pairs = ArrayList<CollisionPair<T>>(Collisions.getEstimatedCollisionPairs(size()))
        val iterator = detectIterator(forceFullDetection)
        while (iterator.hasNext()) pairs.add(iterator.next().copy())
        return pairs
    }
    override fun detectIterator(): MutableIterator<CollisionPair<T>> = detectIterator(false)
    override fun detect(aabb: AABB): MutableList<T> {
        val items = ArrayList<T>(Collisions.getEstimatedCollisionsPerObject())
        val iterator = detectIterator(aabb)
        while (iterator.hasNext()) items.add(iterator.next())
        return items
    }
    override fun raycast(ray: Ray, length: Double): MutableList<T> {
        val items = ArrayList<T>(Collisions.getEstimatedRaycastCollisions(size()))
        val iterator = raycastIterator(ray, length)
        while (iterator.hasNext()) items.add(iterator.next())
        return items
    }
    override fun getAABBProducer() = aabbProducer
    override fun getAABBExpansionMethod() = aabbExpansionMethod
    override fun getBroadphaseFilter() = broadphaseFilter
    override fun isUpdateTrackingEnabled() = updateTrackingEnabled
    override fun setUpdateTrackingEnabled(flag: Boolean) { updateTrackingEnabled = flag }

    companion object {
        const val AABB_REDUCTION_RATIO = 2.0
        @JvmStaticBridge @kotlin.jvm.JvmName("raycast") internal fun raycast(start: Vector2, length: Double, invDx: Double, invDy: Double, aabb: AABB): Boolean {
            val tx1 = (aabb.getMinX() - start.x) * invDx
            val tx2 = (aabb.getMaxX() - start.x) * invDx
            var tmin = min(tx1, tx2)
            var tmax = max(tx1, tx2)
            val ty1 = (aabb.getMinY() - start.y) * invDy
            val ty2 = (aabb.getMaxY() - start.y) * invDy
            tmin = max(tmin, min(ty1, ty2))
            tmax = min(tmax, max(ty1, ty2))
            if (tmax < 0.0 || tmin > length) return false
            return tmax >= tmin
        }
    }
}

class BruteForceBroadphase<T>(filter: BroadphaseFilter<T>, producer: AABBProducer<T>) :
    AbstractBroadphaseDetector<T>(filter, producer, NullAABBExpansionMethod()) {
    private val map = LinkedHashMap<T, AABBBroadphaseProxy<T>>()

    override fun add(item: T) {
        val node = map[item]
        val aabb = aabbProducer.compute(item)
        if (node != null) node.aabb.set(aabb)
        else {
            val created = AABBBroadphaseProxy(item)
            created.aabb.set(aabb)
            map[item] = created
        }
    }
    override fun remove(item: T): Boolean = map.remove(item) != null
    override fun update() { for (proxy in map.values) update(proxy.item) }
    override fun update(item: T) { add(item) }
    override fun isUpdated(item: T) = map.containsKey(item)
    override fun setUpdated(item: T) {}
    override fun clearUpdates() {}
    override fun getAABB(item: T): AABB = map[item]?.aabb ?: aabbProducer.compute(item)
    override fun contains(item: T) = map.containsKey(item)
    override fun clear() { map.clear() }
    override fun size() = map.size
    override fun detectIterator(forceFullDetection: Boolean): MutableIterator<CollisionPair<T>> = DetectPairsIterator()
    override fun detectIterator(aabb: AABB): MutableIterator<T> = DetectAABBIterator(aabb)
    override fun raycastIterator(ray: Ray, length: Double): MutableIterator<T> = DetectRayIterator(ray, length)
    override fun shift(shift: Vector2) { for (proxy in map.values) proxy.aabb.translate(shift) }
    override fun setUpdateTrackingEnabled(flag: Boolean) {}
    override fun isUpdateTrackingEnabled() = false
    override fun isUpdateTrackingSupported() = false
    override fun optimize() {}

    private inner class DetectPairsIterator : MutableIterator<CollisionPair<T>> {
        private val tested = HashMap<T, Boolean>()
        private val outerIterator = map.values.iterator()
        private var currentProxy: AABBBroadphaseProxy<T>? = if (outerIterator.hasNext()) outerIterator.next() else null
        private var innerIterator: MutableIterator<AABBBroadphaseProxy<T>>? = null
        private val currentPair = BroadphasePair<T>()
        private val nextPair = BroadphasePair<T>()
        private var nextReady = findNext()

        override fun hasNext() = nextReady
        override fun next(): CollisionPair<T> {
            if (!nextReady) throw NoSuchElementException()
            currentPair.first = nextPair.first
            currentPair.second = nextPair.second
            nextReady = findNext()
            return currentPair
        }
        override fun remove(): Unit = throw UnsupportedOperationException()

        private fun findNext(): Boolean {
            while (currentProxy != null) {
                if (innerIterator == null) innerIterator = map.values.iterator()
                val iterator = innerIterator!!
                while (iterator.hasNext()) {
                    val b = iterator.next()
                    if (!broadphaseFilter.isAllowed(currentProxy!!.item, b.item)) continue
                    if (tested.containsKey(b.item)) continue
                    if (currentProxy!!.aabb.overlaps(b.aabb)) {
                        nextPair.first = currentProxy!!.item
                        nextPair.second = b.item
                        return true
                    }
                }
                tested[currentProxy!!.item] = true
                innerIterator = null
                currentProxy = if (outerIterator.hasNext()) outerIterator.next() else null
            }
            return false
        }
    }

    private inner class DetectAABBIterator(private val aabb: AABB) : MutableIterator<T> {
        private val iterator = map.values.iterator()
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
                val candidate = iterator.next()
                if (aabb.overlaps(candidate.aabb)) { nextItem = candidate.item; return }
            }
        }
    }

    private inner class DetectRayIterator(ray: Ray, length: Double) : MutableIterator<T> {
        private val ray = ray
        private val iterator = map.values.iterator()
        private val invDx: Double
        private val invDy: Double
        private val length = if (length <= 0.0) Double.MAX_VALUE else length
        private var nextItem: T? = null
        init {
            val direction = ray.getDirectionVector()
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
                val candidate = iterator.next()
                if (AbstractBroadphaseDetector.raycast(ray.getStart(), length, invDx, invDy, candidate.aabb)) {
                    nextItem = candidate.item
                    return
                }
            }
        }
    }
}
