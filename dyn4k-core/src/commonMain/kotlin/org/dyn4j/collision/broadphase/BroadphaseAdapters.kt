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

import org.dyn4j.collision.BasicCollisionItem
import org.dyn4j.collision.CollisionBody
import org.dyn4j.collision.CollisionItem
import org.dyn4j.collision.CollisionPair
import org.dyn4j.collision.Fixture
import org.dyn4j.geometry.AABB
import org.dyn4j.geometry.Convex
import org.dyn4j.geometry.Ray
import org.dyn4j.geometry.Transform
import org.dyn4j.geometry.Vector2

class CollisionBodyAABBProducer<T : CollisionBody<*>> : AABBProducer<T> {
    override fun compute(item: T): AABB = item.createAABB()
    override fun compute(item: T, result: AABB) { item.computeAABB(result) }
}

class CollisionBodyBroadphaseFilter<T : CollisionBody<*>> : BroadphaseFilter<T> {
    override fun isAllowed(first: T?, second: T?) = first !== second
}

class CollisionItemAABBProducer<T : CollisionBody<E>, E : Fixture> : AABBProducer<CollisionItem<T, E>> {
    override fun compute(item: CollisionItem<T, E>): AABB {
        val body = item.getBody()!!
        val fixture = item.getFixture()!!
        return fixture.getShape().createAABB(body.getTransform())
    }
    override fun compute(item: CollisionItem<T, E>, result: AABB) {
        val body = item.getBody()!!
        val fixture = item.getFixture()!!
        fixture.getShape().computeAABB(body.getTransform(), result)
    }
}

class CollisionItemBroadphaseFilter<T : CollisionBody<E>, E : Fixture> : BroadphaseFilter<CollisionItem<T, E>> {
    override fun isAllowed(first: CollisionItem<T, E>?, second: CollisionItem<T, E>?) =
        first !== second && first!!.getBody() !== second!!.getBody()
}

interface BroadphaseDetectorDecorator<T> : BroadphaseDetector<T> {
    fun getDecoratedBroadphaseDetector(): BroadphaseDetector<T>
}

open class BroadphaseDetectorDecoratorAdapter<T>(protected val detector: BroadphaseDetector<T>) : BroadphaseDetectorDecorator<T> {
    override fun getDecoratedBroadphaseDetector() = detector
    override fun shift(shift: Vector2) = detector.shift(shift)
    override fun add(item: T) = detector.add(item)
    override fun remove(item: T) = detector.remove(item)
    override fun update() = detector.update()
    override fun update(item: T) = detector.update(item)
    override fun setUpdated(item: T) = detector.setUpdated(item)
    override fun isUpdated(item: T) = detector.isUpdated(item)
    override fun clearUpdates() = detector.clearUpdates()
    override fun getAABB(item: T) = detector.getAABB(item)
    override fun contains(item: T) = detector.contains(item)
    override fun clear() = detector.clear()
    override fun size() = detector.size()
    override fun detect() = detector.detect()
    override fun detect(forceFullDetection: Boolean) = detector.detect(forceFullDetection)
    override fun detectIterator() = detector.detectIterator()
    override fun detectIterator(forceFullDetection: Boolean) = detector.detectIterator(forceFullDetection)
    override fun detect(aabb: AABB) = detector.detect(aabb)
    override fun detectIterator(aabb: AABB) = detector.detectIterator(aabb)
    override fun raycast(ray: Ray, length: Double) = detector.raycast(ray, length)
    override fun raycastIterator(ray: Ray, length: Double) = detector.raycastIterator(ray, length)
    override fun detect(a: T, b: T) = detector.detect(a, b)
    override fun detect(convex1: Convex, transform1: Transform, convex2: Convex, transform2: Transform) =
        detector.detect(convex1, transform1, convex2, transform2)
    override fun isUpdateTrackingSupported() = detector.isUpdateTrackingSupported()
    override fun isUpdateTrackingEnabled() = detector.isUpdateTrackingEnabled()
    override fun setUpdateTrackingEnabled(flag: Boolean) = detector.setUpdateTrackingEnabled(flag)
    override fun getAABBProducer() = detector.getAABBProducer()
    override fun getAABBExpansionMethod() = detector.getAABBExpansionMethod()
    override fun getBroadphaseFilter() = detector.getBroadphaseFilter()
    override fun optimize() = detector.optimize()
}

interface CollisionItemBroadphaseDetector<T : CollisionBody<E>, E : Fixture> :
    BroadphaseDetectorDecorator<CollisionItem<T, E>> {
    fun add(body: T)
    fun add(body: T, fixture: E)
    fun contains(body: T): Boolean
    fun contains(body: T, fixture: E): Boolean
    fun detect(body1: T, body2: T): Boolean
    fun detect(body1: T, fixture1: E, body2: T, fixture2: E): Boolean
    fun getAABB(body: T, fixture: E): AABB
    fun getAABB(body: T): AABB
    fun isUpdated(body: T): Boolean
    fun isUpdated(body: T, fixture: E): Boolean
    fun remove(body: T): Boolean
    fun remove(body: T, fixture: E): Boolean
    fun setUpdated(body: T)
    fun setUpdated(body: T, fixture: E)
    fun update(body: T)
    fun update(body: T, fixture: E)
}

class CollisionItemBroadphaseDetectorAdapter<T : CollisionBody<E>, E : Fixture>(
    detector: BroadphaseDetector<CollisionItem<T, E>>
) : BroadphaseDetectorDecoratorAdapter<CollisionItem<T, E>>(detector), CollisionItemBroadphaseDetector<T, E> {
    private val reusableItem = BroadphaseItem<T, E>(null, null)
    override fun add(body: T) {
        val size = body.getFixtureCount()
        for (i in 0 until size) detector.add(BasicCollisionItem(body, body.getFixture(i)))
    }
    override fun add(body: T, fixture: E) { detector.add(BasicCollisionItem(body, fixture)) }
    override fun contains(body: T): Boolean {
        reusableItem.body = body
        val size = body.getFixtureCount()
        if (size == 0) return false
        for (i in 0 until size) {
            reusableItem.fixture = body.getFixture(i)
            if (!detector.contains(reusableItem)) return false
        }
        return true
    }
    override fun contains(body: T, fixture: E): Boolean {
        reusableItem.body = body; reusableItem.fixture = fixture
        return detector.contains(reusableItem)
    }
    override fun detect(body1: T, body2: T): Boolean = getAABB(body1).overlaps(getAABB(body2))
    override fun detect(body1: T, fixture1: E, body2: T, fixture2: E): Boolean =
        detector.detect(BasicCollisionItem(body1, fixture1), BasicCollisionItem(body2, fixture2))
    override fun getAABB(body: T, fixture: E): AABB {
        reusableItem.body = body; reusableItem.fixture = fixture
        return detector.getAABB(reusableItem)
    }
    override fun getAABB(body: T): AABB {
        val size = body.getFixtureCount()
        if (size <= 0) return AABB(0.0, 0.0, 0.0, 0.0)
        reusableItem.body = body
        reusableItem.fixture = body.getFixture(0)
        val aabb = detector.getAABB(reusableItem)
        for (i in 1 until size) {
            reusableItem.fixture = body.getFixture(i)
            aabb.union(detector.getAABB(reusableItem))
        }
        return aabb
    }
    override fun isUpdated(body: T): Boolean {
        var updated = false
        reusableItem.body = body
        val size = body.getFixtureCount()
        for (i in 0 until size) {
            reusableItem.fixture = body.getFixture(i)
            updated = updated or detector.isUpdated(reusableItem)
        }
        return updated
    }
    override fun isUpdated(body: T, fixture: E): Boolean {
        reusableItem.body = body; reusableItem.fixture = fixture
        return detector.isUpdated(reusableItem)
    }
    override fun remove(body: T): Boolean {
        var removed = true
        reusableItem.body = body
        val size = body.getFixtureCount()
        for (i in 0 until size) {
            reusableItem.fixture = body.getFixture(i)
            removed = removed and detector.remove(reusableItem)
        }
        return removed
    }
    override fun remove(body: T, fixture: E): Boolean {
        reusableItem.body = body; reusableItem.fixture = fixture
        return detector.remove(reusableItem)
    }
    override fun setUpdated(body: T) {
        val size = body.getFixtureCount()
        for (i in 0 until size) detector.setUpdated(BroadphaseItem(body, body.getFixture(i)))
    }
    override fun setUpdated(body: T, fixture: E) { detector.setUpdated(BroadphaseItem(body, fixture)) }
    override fun update(body: T) {
        val size = body.getFixtureCount()
        for (i in 0 until size) detector.update(BroadphaseItem(body, body.getFixture(i)))
    }
    override fun update(body: T, fixture: E) { detector.update(BroadphaseItem(body, fixture)) }
}
