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
package org.dyn4j.world

import org.dyn4j.DataContainer
import org.dyn4j.collision.BasicCollisionItem
import org.dyn4j.collision.BasicCollisionPair
import org.dyn4j.collision.Bounds
import org.dyn4j.collision.CollisionBody
import org.dyn4j.collision.CollisionItem
import org.dyn4j.collision.CollisionPair
import org.dyn4j.collision.Collisions
import org.dyn4j.collision.Fixture
import org.dyn4j.collision.FixtureModificationHandler
import org.dyn4j.collision.broadphase.CollisionItemBroadphaseDetector
import org.dyn4j.collision.broadphase.CollisionItemBroadphaseDetectorAdapter
import org.dyn4j.collision.broadphase.CollisionItemBroadphaseFilter
import org.dyn4j.collision.broadphase.CollisionItemAABBProducer
import org.dyn4j.collision.broadphase.DynamicAABBTree
import org.dyn4j.collision.broadphase.StaticValueAABBExpansionMethod
import org.dyn4j.collision.continuous.ConservativeAdvancement
import org.dyn4j.collision.continuous.TimeOfImpact
import org.dyn4j.collision.continuous.TimeOfImpactDetector
import org.dyn4j.collision.manifold.ClippingManifoldSolver
import org.dyn4j.collision.manifold.ManifoldSolver
import org.dyn4j.collision.narrowphase.Gjk
import org.dyn4j.collision.narrowphase.LinkPostProcessor
import org.dyn4j.collision.narrowphase.NarrowphaseDetector
import org.dyn4j.collision.narrowphase.NarrowphasePostProcessor
import org.dyn4j.collision.narrowphase.Raycast
import org.dyn4j.collision.narrowphase.RaycastDetector
import org.dyn4j.exception.ArgumentNullException
import org.dyn4j.exception.ObjectAlreadyExistsException
import org.dyn4j.exception.ObjectAlreadyOwnedException
import org.dyn4j.geometry.AABB
import org.dyn4j.geometry.Convex
import org.dyn4j.geometry.Ray
import org.dyn4j.geometry.Shiftable
import org.dyn4j.geometry.Transform
import org.dyn4j.geometry.Vector2
import org.dyn4j.world.listener.BoundsListener
import org.dyn4j.world.listener.CollisionListener
import org.dyn4j.world.result.ConvexCastResult
import org.dyn4j.world.result.ConvexDetectResult
import org.dyn4j.world.result.DetectResult
import org.dyn4j.world.result.RaycastResult

@Suppress("UNCHECKED_CAST")
private fun <Q> worldUnsafe(value: Q?): Q = value as Q

internal fun <Q> worldLiveUnmodifiableList(backing: MutableList<Q>): List<Q> {
    if (backing is WorldTrackedArrayList<*>) {
        @Suppress("UNCHECKED_CAST")
        return (backing as WorldTrackedArrayList<Q>).liveView()
    }
    return worldPlatformUnmodifiableBackingList(backing, worldReadOnlyView(backing))
}

private fun <Q> worldReadOnlyView(backing: MutableList<Q>): MutableList<Q> = object : AbstractMutableList<Q>(), RandomAccess {
    override val size: Int get() = backing.size
    override fun get(index: Int): Q = backing[index]
    override fun set(index: Int, element: Q): Q = throw UnsupportedOperationException()
    override fun add(index: Int, element: Q): Unit = throw UnsupportedOperationException()
    override fun removeAt(index: Int): Q = throw UnsupportedOperationException()
    override fun remove(element: Q): Boolean = throw UnsupportedOperationException()
    override fun clear(): Unit = throw UnsupportedOperationException()
    override fun addAll(elements: Collection<Q>): Boolean = throw UnsupportedOperationException()
    override fun addAll(index: Int, elements: Collection<Q>): Boolean = throw UnsupportedOperationException()
    override fun removeAll(elements: Collection<Q>): Boolean = throw UnsupportedOperationException()
    override fun retainAll(elements: Collection<Q>): Boolean = throw UnsupportedOperationException()

    override fun iterator(): MutableIterator<Q> = listIterator()
    override fun listIterator(): MutableListIterator<Q> = listIterator(0)
    override fun listIterator(index: Int): MutableListIterator<Q> {
        val iterator = backing.listIterator(index)
        return object : MutableListIterator<Q> {
            override fun hasNext() = iterator.hasNext()
            override fun next() = iterator.next()
            override fun hasPrevious() = iterator.hasPrevious()
            override fun previous() = iterator.previous()
            override fun nextIndex() = iterator.nextIndex()
            override fun previousIndex() = iterator.previousIndex()
            override fun remove(): Unit = throw UnsupportedOperationException()
            override fun set(element: Q): Unit = throw UnsupportedOperationException()
            override fun add(element: Q): Unit = throw UnsupportedOperationException()
        }
    }
    override fun subList(fromIndex: Int, toIndex: Int): MutableList<Q> =
        worldReadOnlyView(backing.subList(fromIndex, toIndex))
}

abstract class AbstractCollisionWorld<T : CollisionBody<E>, E : Fixture, V : CollisionData<T, E>> :
    CollisionWorld<T, E, V>, Shiftable, DataContainer {

    @kotlin.jvm.JvmField protected var userData: Any? = null
    @kotlin.jvm.JvmField protected var bounds: Bounds? = null
    @kotlin.jvm.JvmField protected var broadphaseDetector: CollisionItemBroadphaseDetector<T, E>
    @kotlin.jvm.JvmField protected var broadphaseFilter: BroadphaseCollisionDataFilter<T, E> = CollisionBodyBroadphaseCollisionDataFilter()
    @kotlin.jvm.JvmField protected var narrowphaseDetector: NarrowphaseDetector = Gjk()
    @kotlin.jvm.JvmField protected var narrowphasePostProcessor: NarrowphasePostProcessor? = LinkPostProcessor()
    @kotlin.jvm.JvmField protected var manifoldSolver: ManifoldSolver = ClippingManifoldSolver()
    @kotlin.jvm.JvmField protected var raycastDetector: RaycastDetector = Gjk()
    @kotlin.jvm.JvmField protected var timeOfImpactDetector: TimeOfImpactDetector = ConservativeAdvancement()
    @kotlin.jvm.JvmField protected val bodies: MutableList<T>
    @kotlin.jvm.JvmField protected val bodiesUnmodifiable: List<T>
    @kotlin.jvm.JvmField protected val collisionData: MutableMap<CollisionPair<CollisionItem<T, E>>, V>
    @kotlin.jvm.JvmField protected val collisionListeners: MutableList<CollisionListener<T, E>> = ArrayList(10)
    @kotlin.jvm.JvmField protected val collisionListenersUnmodifiable: List<CollisionListener<T, E>>
    @kotlin.jvm.JvmField protected val boundsListeners: MutableList<BoundsListener<T, E>> = ArrayList(10)
    @kotlin.jvm.JvmField protected val boundsListenersUnmodifiable: List<BoundsListener<T, E>>

    constructor() : this(CollisionWorld.DEFAULT_INITIAL_BODY_CAPACITY)

    constructor(initialBodyCapacity: Int) {
        val capacity = if (initialBodyCapacity <= 0) CollisionWorld.DEFAULT_INITIAL_BODY_CAPACITY else initialBodyCapacity
        val broadphase = DynamicAABBTree(
            CollisionItemBroadphaseFilter<T, E>(),
            CollisionItemAABBProducer<T, E>(),
            StaticValueAABBExpansionMethod<CollisionItem<T, E>>(0.2),
            capacity,
        )
        broadphaseDetector = CollisionItemBroadphaseDetectorAdapter(broadphase)
        broadphaseDetector.setUpdateTrackingEnabled(true)
        bodies = ArrayList(capacity)
        bodiesUnmodifiable = worldLiveUnmodifiableList(bodies)
        collisionData = LinkedHashMap(Collisions.getEstimatedCollisionPairs(capacity))
        collisionListenersUnmodifiable = worldLiveUnmodifiableList(collisionListeners)
        boundsListenersUnmodifiable = worldLiveUnmodifiableList(boundsListeners)
    }

    override fun addBody(body: T?) {
        val added = body ?: throw ArgumentNullException("body")
        if (added.getOwner() === this) throw ObjectAlreadyExistsException("body", added, added.getOwner())
        if (added.getOwner() != null) throw ObjectAlreadyOwnedException("body", added, added.getOwner())
        bodies.add(added)
        added.setFixtureModificationHandler(BodyModificationHandler(added))
        added.setOwner(this)
        added.getPreviousTransform().set(added.getTransform())
        broadphaseDetector.add(added)
    }

    override fun removeAllBodies() {
        val count = bodies.size
        for (index in 0 until count) {
            bodies[index].setFixtureModificationHandler(null)
            bodies[index].setOwner(null)
        }
        bodies.clear()
        broadphaseDetector.clear()
        collisionData.clear()
    }

    override fun containsBody(body: T?): Boolean = bodies.contains(body)
    override fun removeBody(index: Int): Boolean = removeBody(bodies[index])
    override fun removeBody(body: T?): Boolean {
        val removed = bodies.remove(body)
        if (removed && body != null) {
            body.setFixtureModificationHandler(null)
            body.setOwner(null)
            broadphaseDetector.remove(body)
        }
        return removed
    }
    override fun getBodies(): List<T> = bodiesUnmodifiable
    override fun getBody(index: Int): T = bodies[index]
    override fun getBodyCount(): Int = bodies.size
    override fun isEmpty(): Boolean = bodies.isEmpty()
    override fun getBodyIterator(): MutableIterator<T> = BodyIterator()

    override fun setBounds(bounds: Bounds?) { this.bounds = bounds }
    override fun getBounds(): Bounds? = bounds
    override fun setBroadphaseDetector(broadphaseDetector: CollisionItemBroadphaseDetector<T, E>?) {
        val detector = broadphaseDetector ?: throw ArgumentNullException("broadphaseDetector")
        this.broadphaseDetector = detector
        val count = bodies.size
        for (index in 0 until count) detector.add(bodies[index])
    }
    override fun getBroadphaseDetector() = broadphaseDetector
    override fun getBroadphaseCollisionDataFilter() = broadphaseFilter
    override fun setBroadphaseCollisionDataFilter(filter: BroadphaseCollisionDataFilter<T, E>?) {
        broadphaseFilter = filter ?: throw ArgumentNullException("filter")
    }
    override fun setNarrowphaseDetector(narrowphaseDetector: NarrowphaseDetector?) {
        this.narrowphaseDetector = narrowphaseDetector ?: throw ArgumentNullException("narrowphaseDetector")
    }
    override fun getNarrowphaseDetector() = narrowphaseDetector
    override fun setNarrowphasePostProcessor(narrowphasePostProcessor: NarrowphasePostProcessor?) {
        this.narrowphasePostProcessor = narrowphasePostProcessor ?: throw ArgumentNullException("narrowphasePostProcessor")
    }
    override fun getNarrowphasePostProcessor(): NarrowphasePostProcessor = worldUnsafe(narrowphasePostProcessor)
    override fun setManifoldSolver(manifoldSolver: ManifoldSolver?) {
        this.manifoldSolver = manifoldSolver ?: throw ArgumentNullException("manifoldSolver")
    }
    override fun getManifoldSolver() = manifoldSolver
    override fun setRaycastDetector(raycastDetector: RaycastDetector?) {
        this.raycastDetector = raycastDetector ?: throw ArgumentNullException("raycastDetector")
    }
    override fun getRaycastDetector() = raycastDetector
    override fun setTimeOfImpactDetector(timeOfImpactDetector: TimeOfImpactDetector?) {
        this.timeOfImpactDetector = timeOfImpactDetector ?: throw ArgumentNullException("timeOfImpactDetector")
    }
    override fun getTimeOfImpactDetector() = timeOfImpactDetector

    override fun shift(shift: Vector2) {
        broadphaseDetector.shift(shift)
        bounds?.shift(shift)
        val count = bodies.size
        for (index in 0 until count) bodies[index].shift(shift)
        for (collision in collisionData.values) if (collision.isManifoldCollision()) collision.shift(shift)
    }

    override fun getCollisionDataIterator(): MutableIterator<V> = CollisionDataIterator()
    override fun getCollisionData(body1: T?, fixture1: E?, body2: T?, fixture2: E?): V? {
        if (body1 == null || fixture1 == null || body2 == null || fixture2 == null) return null
        val item = CollisionItemAdapter<T, E>()
        item.set(body1, fixture1)
        if (!broadphaseDetector.contains(item)) return null
        item.set(body2, fixture2)
        if (!broadphaseDetector.contains(item)) return null
        val pair = BasicCollisionPair<CollisionItem<T, E>>(
            BasicCollisionItem(body1, fixture1), BasicCollisionItem(body2, fixture2))
        return collisionData[pair]
    }

    override fun getBoundsListeners(): List<BoundsListener<T, E>> = boundsListenersUnmodifiable
    override fun getCollisionListeners(): List<CollisionListener<T, E>> = collisionListenersUnmodifiable
    override fun removeAllListeners() { boundsListeners.clear(); collisionListeners.clear() }
    override fun removeAllBoundsListeners() { boundsListeners.clear() }
    override fun removeAllCollisionListeners() { collisionListeners.clear() }
    override fun removeBoundsListener(listener: BoundsListener<T, E>?): Boolean = boundsListeners.remove(listener)
    override fun removeCollisionListener(listener: CollisionListener<T, E>?): Boolean = collisionListeners.remove(listener)
    override fun addBoundsListener(listener: BoundsListener<T, E>?): Boolean = boundsListeners.add(worldUnsafe(listener))
    override fun addCollisionListener(listener: CollisionListener<T, E>?): Boolean = collisionListeners.add(worldUnsafe(listener))
    override fun getUserData(): Any? = userData
    override fun setUserData(data: Any?) { userData = data }

    protected open fun detect() {
        val listenerCount = boundsListeners.size
        val bodyCount = bodies.size
        broadphaseDetector.update()
        val adapter = CollisionItemAdapter<T, E>()
        for (index in 0 until bodyCount) {
            val body = bodies[index]
            val transform = body.getTransform()
            if (!body.isEnabled()) continue
            val currentBounds = bounds ?: continue
            var withinBounds = false
            val fixtureCount = body.getFixtureCount()
            for (fixtureIndex in 0 until fixtureCount) {
                val fixture = body.getFixture(fixtureIndex)
                adapter.set(body, fixture)
                val aabb = broadphaseDetector.getAABB(adapter)
                if (!currentBounds.isOutside(aabb, transform, fixture)) {
                    withinBounds = true
                    break
                }
            }
            if (!withinBounds) {
                body.setEnabled(false)
                for (listenerIndex in 0 until listenerCount) boundsListeners[listenerIndex].outside(body)
            }
        }
        val pairIterator = broadphaseDetector.detectIterator()
        while (pairIterator.hasNext()) {
            val pair = pairIterator.next().copy()
            if (!collisionData.containsKey(pair)) collisionData[pair] = createCollisionData(pair)
        }
        processCollisions(DetectIterator(collisionData.values.iterator()))
        broadphaseDetector.clearUpdates()
    }

    protected abstract fun createCollisionData(pair: CollisionPair<CollisionItem<T, E>>): V
    protected abstract fun processCollisions(iterator: MutableIterator<@kotlin.jvm.JvmSuppressWildcards V>)
    protected open fun handleFixtureAdded(body: T, fixture: E) { broadphaseDetector.add(body, fixture) }
    protected open fun handleFixtureRemoved(body: T, fixture: E) { broadphaseDetector.remove(body, fixture) }
    protected open fun handleAllFixturesRemoved(body: T) { broadphaseDetector.remove(body) }

    override fun detect(aabb: AABB?, filter: DetectFilter<T, E>?): List<DetectResult<T, E>> {
        val results = ArrayList<DetectResult<T, E>>()
        val iterator = detectIterator(aabb, filter)
        while (iterator.hasNext()) results.add(iterator.next().copy())
        return results
    }
    override fun detectIterator(aabb: AABB?, filter: DetectFilter<T, E>?): MutableIterator<DetectResult<T, E>> =
        AABBDetectIterator(worldUnsafe(aabb), filter)
    override fun detect(aabb: AABB?, body: T?, filter: DetectFilter<T, E>?): List<DetectResult<T, E>> {
        val results = ArrayList<DetectResult<T, E>>()
        val iterator = detectIterator(aabb, body, filter)
        while (iterator.hasNext()) results.add(iterator.next().copy())
        return results
    }
    override fun detectIterator(aabb: AABB?, body: T?, filter: DetectFilter<T, E>?): MutableIterator<DetectResult<T, E>> =
        AABBBodyDetectIterator(worldUnsafe(aabb), worldUnsafe(body), filter)
    override fun detect(convex: Convex?, transform: Transform?, filter: DetectFilter<T, E>?): List<ConvexDetectResult<T, E>> {
        val results = ArrayList<ConvexDetectResult<T, E>>()
        val iterator = detectIterator(convex, transform, filter)
        while (iterator.hasNext()) results.add(iterator.next().copy())
        return results
    }
    override fun detectIterator(convex: Convex?, transform: Transform?, filter: DetectFilter<T, E>?): MutableIterator<ConvexDetectResult<T, E>> =
        ConvexDetectIterator(worldUnsafe(convex), worldUnsafe(transform), filter)
    override fun detect(convex: Convex?, transform: Transform?, body: T?, filter: DetectFilter<T, E>?): List<ConvexDetectResult<T, E>> {
        val results = ArrayList<ConvexDetectResult<T, E>>()
        val iterator = detectIterator(convex, transform, body, filter)
        while (iterator.hasNext()) results.add(iterator.next().copy())
        return results
    }
    override fun detectIterator(convex: Convex?, transform: Transform?, body: T?, filter: DetectFilter<T, E>?): MutableIterator<ConvexDetectResult<T, E>> =
        ConvexBodyDetectIterator(worldUnsafe(convex), worldUnsafe(transform), worldUnsafe(body), filter)
    override fun raycast(ray: Ray?, maxLength: Double, filter: DetectFilter<T, E>?): List<RaycastResult<T, E>> {
        val results = ArrayList<RaycastResult<T, E>>()
        val iterator = raycastIterator(ray, maxLength, filter)
        while (iterator.hasNext()) results.add(iterator.next().copy())
        return results
    }
    override fun raycastIterator(ray: Ray?, maxLength: Double, filter: DetectFilter<T, E>?): MutableIterator<RaycastResult<T, E>> =
        RaycastDetectIterator(worldUnsafe(ray), maxLength, filter)
    override fun raycast(ray: Ray?, maxLength: Double, body: T?, filter: DetectFilter<T, E>?): List<RaycastResult<T, E>> {
        val results = ArrayList<RaycastResult<T, E>>()
        val iterator = raycastIterator(ray, maxLength, body, filter)
        while (iterator.hasNext()) results.add(iterator.next().copy())
        return results
    }
    override fun raycastIterator(ray: Ray?, maxLength: Double, body: T?, filter: DetectFilter<T, E>?): MutableIterator<RaycastResult<T, E>> =
        RaycastBodyDetectIterator(worldUnsafe(ray), maxLength, worldUnsafe(body), filter)

    override fun raycastClosest(ray: Ray?, maxLength: Double, filter: DetectFilter<T, E>?): RaycastResult<T, E>? {
        var max = if (maxLength > 0.0) maxLength else 0.0
        var result: RaycastResult<T, E>? = null
        val raycast = Raycast()
        val iterator = broadphaseDetector.raycastIterator(worldUnsafe(ray), maxLength)
        while (iterator.hasNext()) {
            val item = iterator.next()
            val body = item.getBody()!!
            val fixture = item.getFixture()!!
            if (!filter!!.isAllowed(body, fixture)) continue
            if (raycastDetector.raycast(worldUnsafe(ray), max, fixture.getShape(), body.getTransform(), raycast)) {
                if (result == null) result = RaycastResult()
                result.setBody(body)
                result.setFixture(fixture)
                result.setRaycast(raycast)
                max = raycast.getDistance()
            }
        }
        return result
    }
    override fun raycastClosest(ray: Ray?, maxLength: Double, body: T?, filter: DetectFilter<T, E>?): RaycastResult<T, E>? {
        val target = worldUnsafe<T>(body)
        var max = if (maxLength > 0.0) maxLength else 0.0
        var result: RaycastResult<T, E>? = null
        val raycast = Raycast()
        val count = target.getFixtureCount()
        val transform = target.getTransform()
        for (index in 0 until count) {
            val fixture = target.getFixture(index)
            if (!filter!!.isAllowed(target, fixture)) continue
            if (raycastDetector.raycast(worldUnsafe(ray), max, fixture.getShape(), transform, raycast)) {
                if (result == null) result = RaycastResult()
                max = raycast.getDistance()
                result.setBody(target)
                result.setFixture(fixture)
                result.setRaycast(raycast)
            }
        }
        return result
    }

    override fun convexCast(convex: Convex?, transform: Transform?, deltaPosition: Vector2?, deltaAngle: Double, filter: DetectFilter<T, E>?): List<ConvexCastResult<T, E>> {
        val results = ArrayList<ConvexCastResult<T, E>>()
        val iterator = convexCastIterator(convex, transform, deltaPosition, deltaAngle, filter)
        while (iterator.hasNext()) results.add(iterator.next().copy())
        return results
    }
    override fun convexCastIterator(convex: Convex?, transform: Transform?, deltaPosition: Vector2?, deltaAngle: Double, filter: DetectFilter<T, E>?): MutableIterator<ConvexCastResult<T, E>> =
        ConvexCastDetectIterator(worldUnsafe(convex), worldUnsafe(transform), worldUnsafe(deltaPosition), deltaAngle, filter)
    override fun convexCastClosest(convex: Convex?, transform: Transform?, deltaPosition: Vector2?, deltaAngle: Double, body: T?, filter: DetectFilter<T, E>?): ConvexCastResult<T, E>? {
        val target = worldUnsafe<T>(body)
        var result: ConvexCastResult<T, E>? = null
        val zero = Vector2()
        var upper = 1.0
        val count = target.getFixtureCount()
        val bodyTransform = target.getTransform()
        for (index in 0 until count) {
            val fixture = target.getFixture(index)
            if (!filter!!.isAllowed(target, fixture)) continue
            val toi = TimeOfImpact()
            if (timeOfImpactDetector.getTimeOfImpact(worldUnsafe(convex), worldUnsafe(transform), worldUnsafe(deltaPosition), deltaAngle,
                    fixture.getShape(), bodyTransform, zero, 0.0, 0.0, upper, toi)) {
                upper = toi.getTime()
                if (result == null) result = ConvexCastResult()
                result.setBody(target)
                result.setFixture(fixture)
                result.setTimeOfImpact(toi)
            }
        }
        return result
    }
    override fun convexCastClosest(convex: Convex?, transform: Transform?, deltaPosition: Vector2?, deltaAngle: Double, filter: DetectFilter<T, E>?): ConvexCastResult<T, E>? {
        val shape = worldUnsafe<Convex>(convex)
        val tx = worldUnsafe<Transform>(transform)
        val delta = worldUnsafe<Vector2>(deltaPosition)
        val radius = shape.getRadius()
        val start = AABB(tx.getTransformed(shape.getCenter()), radius)
        val endTransform = tx.lerped(delta, deltaAngle, 1.0)
        val end = AABB(endTransform.getTransformed(shape.getCenter()), radius)
        val aabb = start.getUnion(end)
        var result: ConvexCastResult<T, E>? = null
        val zero = Vector2()
        val upper = 1.0
        val iterator = broadphaseDetector.detectIterator(aabb)
        while (iterator.hasNext()) {
            val item = iterator.next()
            val body = item.getBody()!!
            val fixture = item.getFixture()!!
            if (!filter!!.isAllowed(body, fixture)) continue
            var fixtureUpper = upper
            val toi = TimeOfImpact()
            if (timeOfImpactDetector.getTimeOfImpact(shape, tx, delta, deltaAngle, fixture.getShape(), body.getTransform(),
                    zero, 0.0, 0.0, fixtureUpper, toi)) {
                if (result == null || toi.getTime() < result.getTimeOfImpact().getTime()) {
                    if (result == null) result = ConvexCastResult()
                    fixtureUpper = toi.getTime()
                    result.setBody(body)
                    result.setFixture(fixture)
                    result.setTimeOfImpact(toi)
                }
            }
        }
        return result
    }

    private inner class DetectIterator(private val iterator: MutableIterator<@kotlin.jvm.JvmSuppressWildcards V>) : MutableIterator<V> {
        private val listeners = collisionListeners
        private val listenerCount = listeners.size
        private val adapter1 = CollisionItemAdapter<T, E>()
        private val adapter2 = CollisionItemAdapter<T, E>()

        private fun isAllowedBroadphase(data: BroadphaseCollisionData<T, E>): Boolean {
            var allowed = true
            for (index in 0 until listenerCount) if (!listeners[index].collision(data)) allowed = false
            return allowed
        }
        private fun isAllowedNarrowphase(data: NarrowphaseCollisionData<T, E>): Boolean {
            var allowed = true
            for (index in 0 until listenerCount) if (!listeners[index].collision(data)) allowed = false
            return allowed
        }
        private fun isAllowedManifold(data: ManifoldCollisionData<T, E>): Boolean {
            var allowed = true
            for (index in 0 until listenerCount) if (!listeners[index].collision(data)) allowed = false
            return allowed
        }

        override fun hasNext() = iterator.hasNext()
        override fun next(): V {
            val collision = iterator.next()
            val body1 = collision.getBody1()!!
            val body2 = collision.getBody2()!!
            val fixture1 = collision.getFixture1()!!
            val fixture2 = collision.getFixture2()!!
            collision.reset()
            adapter1.set(body1, fixture1)
            adapter2.set(body2, fixture2)
            if (!broadphaseDetector.contains(adapter1) || !broadphaseDetector.contains(adapter2)) {
                iterator.remove()
                return collision
            }
            if (broadphaseDetector.isUpdated(adapter1) || broadphaseDetector.isUpdated(adapter2)) {
                if (!broadphaseDetector.detect(adapter1, adapter2)) {
                    iterator.remove()
                    return collision
                }
            }
            if (!broadphaseFilter.isAllowed(body1, fixture1, body2, fixture2)) return collision
            if (!isAllowedBroadphase(collision)) return collision
            collision.setBroadphaseCollision(true)
            val transform1 = body1.getTransform()
            val transform2 = body2.getTransform()
            val convex2 = fixture2.getShape()
            val convex1 = fixture1.getShape()
            val penetration = collision.getPenetration()
            if (narrowphaseDetector.detect(convex1, transform1, convex2, transform2, penetration)) {
                if (penetration.getDepth() == 0.0) return collision
                narrowphasePostProcessor?.process(convex1, transform1, convex2, transform2, penetration)
                if (penetration.getDepth() == 0.0) return collision
                if (!isAllowedNarrowphase(collision)) return collision
                collision.setNarrowphaseCollision(true)
                val manifold = collision.getManifold()
                if (manifoldSolver.getManifold(penetration, convex1, transform1, convex2, transform2, manifold)) {
                    if (manifold.getPoints().isEmpty()) return collision
                    if (!isAllowedManifold(collision)) return collision
                    collision.setManifoldCollision(true)
                }
            }
            return collision
        }
        override fun remove(): Nothing = throw UnsupportedOperationException()
    }

    private inner class CollisionDataIterator : MutableIterator<V> {
        private val iterator = collisionData.values.iterator()
        private val item = CollisionItemAdapter<T, E>()
        private var current: V? = null
        private var available = findNext()
        override fun hasNext() = available
        override fun next(): V {
            if (!available) throw NoSuchElementException()
            val result = current!!
            available = findNext()
            return result
        }
        override fun remove(): Nothing = throw UnsupportedOperationException()
        private fun findNext(): Boolean {
            while (iterator.hasNext()) {
                val collision = iterator.next()
                item.set(collision.getBody1(), collision.getFixture1())
                if (!broadphaseDetector.contains(item)) continue
                item.set(collision.getBody2(), collision.getFixture2())
                if (!broadphaseDetector.contains(item)) continue
                current = collision
                return true
            }
            return false
        }
    }

    private inner class AABBDetectIterator(aabb: AABB, private val filter: DetectFilter<T, E>?) : MutableIterator<DetectResult<T, E>> {
        private val iterator = broadphaseDetector.detectIterator(aabb)
        private val currentResult = DetectResult<T, E>()
        private val nextResult = DetectResult<T, E>()
        private var available = findNext()
        override fun hasNext() = available
        override fun next(): DetectResult<T, E> {
            if (!available) throw NoSuchElementException()
            currentResult.set(nextResult)
            available = findNext()
            return currentResult
        }
        override fun remove(): Nothing = throw UnsupportedOperationException()
        private fun findNext(): Boolean {
            while (iterator.hasNext()) {
                val item = iterator.next()
                val body = item.getBody()!!
                val fixture = item.getFixture()!!
                if (filter != null && !filter.isAllowed(body, fixture)) continue
                nextResult.setBody(body)
                nextResult.setFixture(fixture)
                return true
            }
            return false
        }
    }

    private inner class AABBBodyDetectIterator(private val aabb: AABB, private val body: T,
                                               private val filter: DetectFilter<T, E>?) : MutableIterator<DetectResult<T, E>> {
        private val iterator = body.getFixtureIterator()
        private val currentResult = DetectResult<T, E>()
        private val nextResult = DetectResult<T, E>()
        private var available = findNext()
        override fun hasNext() = available
        override fun next(): DetectResult<T, E> {
            if (!available) throw NoSuchElementException()
            currentResult.set(nextResult)
            available = findNext()
            return currentResult
        }
        override fun remove(): Nothing = throw UnsupportedOperationException()
        private fun findNext(): Boolean {
            while (iterator.hasNext()) {
                val fixture = iterator.next()
                if (filter != null && !filter.isAllowed(body, fixture)) continue
                if (aabb.overlaps(broadphaseDetector.getAABB(body, fixture))) {
                    nextResult.setBody(body)
                    nextResult.setFixture(fixture)
                    return true
                }
            }
            return false
        }
    }

    private inner class ConvexDetectIterator(private val convex: Convex, private val transform: Transform,
                                             private val filter: DetectFilter<T, E>?) : MutableIterator<ConvexDetectResult<T, E>> {
        private val iterator = broadphaseDetector.detectIterator(convex.createAABB(transform))
        private val currentResult = ConvexDetectResult<T, E>()
        private val nextResult = ConvexDetectResult<T, E>()
        private var available = findNext()
        override fun hasNext() = available
        override fun next(): ConvexDetectResult<T, E> {
            if (!available) throw NoSuchElementException()
            currentResult.set(nextResult)
            available = findNext()
            return currentResult
        }
        override fun remove(): Nothing = throw UnsupportedOperationException()
        private fun findNext(): Boolean {
            while (iterator.hasNext()) {
                val item = iterator.next()
                val body = item.getBody()!!
                val fixture = item.getFixture()!!
                if (filter != null && !filter.isAllowed(body, fixture)) continue
                if (narrowphaseDetector.detect(fixture.getShape(), body.getTransform(), convex, transform, nextResult.getPenetration())) {
                    nextResult.setBody(body)
                    nextResult.setFixture(fixture)
                }
                return true
            }
            return false
        }
    }

    private inner class ConvexBodyDetectIterator(private val convex: Convex, private val transform: Transform,
                                                 private val body: T, private val filter: DetectFilter<T, E>?) : MutableIterator<ConvexDetectResult<T, E>> {
        private val aabb = convex.createAABB(transform)
        private val iterator = body.getFixtureIterator()
        private val currentResult = ConvexDetectResult<T, E>()
        private val nextResult = ConvexDetectResult<T, E>()
        private var available = findNext()
        override fun hasNext() = available
        override fun next(): ConvexDetectResult<T, E> {
            if (!available) throw NoSuchElementException()
            currentResult.set(nextResult)
            available = findNext()
            return currentResult
        }
        override fun remove(): Nothing = throw UnsupportedOperationException()
        private fun findNext(): Boolean {
            while (iterator.hasNext()) {
                val fixture = iterator.next()
                if (filter != null && !filter.isAllowed(body, fixture)) continue
                if (aabb.overlaps(broadphaseDetector.getAABB(body, fixture))) {
                    if (narrowphaseDetector.detect(fixture.getShape(), body.getTransform(), convex, transform, nextResult.getPenetration())) {
                        nextResult.setBody(body)
                        nextResult.setFixture(fixture)
                    }
                    return true
                }
            }
            return false
        }
    }

    private inner class RaycastDetectIterator(private val ray: Ray, maxLength: Double,
                                              private val filter: DetectFilter<T, E>?) : MutableIterator<RaycastResult<T, E>> {
        private val iterator = broadphaseDetector.raycastIterator(ray, maxLength)
        private val max = if (maxLength > 0.0) maxLength else 0.0
        private val currentResult = RaycastResult<T, E>()
        private val nextResult = RaycastResult<T, E>()
        private var available = findNext()
        override fun hasNext() = available
        override fun next(): RaycastResult<T, E> {
            if (!available) throw NoSuchElementException()
            currentResult.set(nextResult)
            available = findNext()
            return currentResult
        }
        override fun remove(): Nothing = throw UnsupportedOperationException()
        private fun findNext(): Boolean {
            while (iterator.hasNext()) {
                val item = iterator.next()
                val body = item.getBody()!!
                val fixture = item.getFixture()!!
                if (filter != null && !filter.isAllowed(body, fixture)) continue
                if (raycastDetector.raycast(ray, max, fixture.getShape(), body.getTransform(), nextResult.getRaycast())) {
                    nextResult.setBody(body)
                    nextResult.setFixture(fixture)
                    return true
                }
            }
            return false
        }
    }

    private inner class RaycastBodyDetectIterator(private val ray: Ray, maxLength: Double, private val body: T,
                                                  private val filter: DetectFilter<T, E>?) : MutableIterator<RaycastResult<T, E>> {
        private val iterator = body.getFixtureIterator()
        private val max = if (maxLength > 0.0) maxLength else 0.0
        private val currentResult = RaycastResult<T, E>()
        private val nextResult = RaycastResult<T, E>()
        private var available = findNext()
        override fun hasNext() = available
        override fun next(): RaycastResult<T, E> {
            if (!available) throw NoSuchElementException()
            currentResult.set(nextResult)
            available = findNext()
            return currentResult
        }
        override fun remove(): Nothing = throw UnsupportedOperationException()
        private fun findNext(): Boolean {
            while (iterator.hasNext()) {
                val fixture = iterator.next()
                if (filter != null && !filter.isAllowed(body, fixture)) continue
                if (raycastDetector.raycast(ray, max, fixture.getShape(), body.getTransform(), nextResult.getRaycast())) {
                    nextResult.setBody(body)
                    nextResult.setFixture(fixture)
                    return true
                }
            }
            return false
        }
    }

    private inner class ConvexCastDetectIterator(private val convex: Convex, private val transform: Transform,
                                                 private val deltaPosition: Vector2, private val deltaAngle: Double,
                                                 private val filter: DetectFilter<T, E>?) : MutableIterator<ConvexCastResult<T, E>> {
        private val aabb: AABB
        private val iterator: MutableIterator<CollisionItem<T, E>>
        private val currentResult = ConvexCastResult<T, E>()
        private val nextResult = ConvexCastResult<T, E>()
        private var available: Boolean
        init {
            val radius = convex.getRadius()
            val startCenter = transform.getTransformed(convex.getCenter())
            val start = AABB(startCenter, radius)
            val finalTransform = transform.lerped(deltaPosition, deltaAngle, 1.0)
            val endCenter = finalTransform.getTransformed(convex.getCenter())
            aabb = start.getUnion(AABB(endCenter, radius))
            iterator = broadphaseDetector.detectIterator(aabb)
            available = findNext()
        }
        override fun hasNext() = available
        override fun next(): ConvexCastResult<T, E> {
            if (!available) throw NoSuchElementException()
            currentResult.set(nextResult)
            available = findNext()
            return currentResult
        }
        override fun remove(): Nothing = throw UnsupportedOperationException()
        private fun findNext(): Boolean {
            val zero = Vector2()
            while (iterator.hasNext()) {
                val item = iterator.next()
                val body = item.getBody()!!
                val fixture = item.getFixture()!!
                if (filter != null && !filter.isAllowed(body, fixture)) continue
                if (timeOfImpactDetector.getTimeOfImpact(convex, transform, deltaPosition, deltaAngle,
                        fixture.getShape(), body.getTransform(), zero, 0.0, 0.0, 1.0, nextResult.getTimeOfImpact())) {
                    nextResult.setBody(body)
                    nextResult.setFixture(fixture)
                    return true
                }
            }
            return false
        }
    }

    private inner class BodyIterator : MutableIterator<T> {
        private var index = -1
        private var removed = false
        override fun hasNext() = index + 1 < bodies.size
        override fun next(): T {
            if (index + 1 >= bodies.size) throw IndexOutOfBoundsException()
            try {
                index++
                removed = false
                return bodies[index]
            } catch (_: IndexOutOfBoundsException) { throw ConcurrentModificationException() }
        }
        override fun remove() {
            if (index < 0 || removed) throw IllegalStateException()
            if (index >= bodies.size) throw IndexOutOfBoundsException()
            try {
                removeBody(index)
                index--
                removed = true
            } catch (_: IndexOutOfBoundsException) { throw ConcurrentModificationException() }
        }
    }

    private inner class BodyModificationHandler(private val body: T) : FixtureModificationHandler<E> {
        override fun onFixtureAdded(fixture: E) { handleFixtureAdded(body, fixture) }
        override fun onFixtureRemoved(fixture: E) { handleFixtureRemoved(body, fixture) }
        override fun onAllFixturesRemoved() { handleAllFixturesRemoved(body) }
    }
}
