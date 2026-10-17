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
package org.dyn4j.collision

import org.dyn4j.Copyable
import org.dyn4j.DataContainer
import org.dyn4j.Ownable
import org.dyn4j.Unsafe
import org.dyn4j.exception.ArgumentNullException
import org.dyn4j.geometry.AABB
import org.dyn4j.geometry.Convex
import org.dyn4j.geometry.Rotation
import org.dyn4j.geometry.Shiftable
import org.dyn4j.geometry.Transform
import org.dyn4j.geometry.Transformable
import org.dyn4j.geometry.Vector2
import kotlin.math.max

interface FixtureModificationHandler<T : Fixture> {
    fun onFixtureAdded(fixture: T)
    fun onFixtureRemoved(fixture: T)
    fun onAllFixturesRemoved()
}

interface CollisionBody<T : Fixture> : Transformable, Shiftable, DataContainer, Ownable, Copyable<CollisionBody<T>> {
    companion object { const val TYPICAL_FIXTURE_COUNT = 1 }
    override fun copy(): CollisionBody<T>
    fun addFixture(fixture: T?): CollisionBody<T>
    fun addFixture(convex: Convex): T
    fun getFixture(index: Int): T
    fun containsFixture(fixture: T?): Boolean
    fun getFixture(point: Vector2): T?
    fun getFixtures(point: Vector2): List<T>
    fun removeFixture(fixture: T?): Boolean
    fun removeFixture(index: Int): T
    fun removeAllFixtures(): List<T>
    fun removeFixture(point: Vector2): T?
    fun removeFixtures(point: Vector2): List<T>
    fun getFixtureCount(): Int
    fun getFixtures(): List<T>
    fun getFixtureIterator(): MutableIterator<T>
    fun contains(point: Vector2): Boolean
    fun getLocalCenter(): Vector2
    fun getWorldCenter(): Vector2
    fun getLocalPoint(worldPoint: Vector2): Vector2
    fun getLocalPoint(worldPoint: Vector2, destination: Vector2)
    fun getWorldPoint(localPoint: Vector2): Vector2
    fun getWorldPoint(localPoint: Vector2, destination: Vector2)
    fun getLocalVector(worldVector: Vector2): Vector2
    fun getLocalVector(worldVector: Vector2, destination: Vector2)
    fun getWorldVector(localVector: Vector2): Vector2
    fun getWorldVector(localVector: Vector2, destination: Vector2)
    fun getRotationDiscRadius(): Double
    fun getTransform(): Transform
    fun getPreviousTransform(): Transform
    fun setTransform(transform: Transform?)
    fun rotateAboutCenter(theta: Double)
    fun translateToOrigin()
    fun createAABB(): AABB
    fun createAABB(transform: Transform): AABB
    fun computeAABB(result: AABB)
    fun computeAABB(transform: Transform, result: AABB)
    fun setEnabled(enabled: Boolean)
    fun isEnabled(): Boolean
    fun getFixtureModificationHandler(): FixtureModificationHandler<T>?
    fun setFixtureModificationHandler(handler: FixtureModificationHandler<T>?)
}

abstract class AbstractCollisionBody<T : Fixture> : CollisionBody<T>, Transformable, DataContainer, Ownable {
    @kotlin.jvm.JvmField protected val transform: Transform
    @kotlin.jvm.JvmField protected val transform0: Transform
    @kotlin.jvm.JvmField protected val fixtures: MutableList<T>
    @kotlin.jvm.JvmField protected val fixturesUnmodifiable: List<T>
    @kotlin.jvm.JvmField protected var radius: Double = 0.0
    @kotlin.jvm.JvmField protected var userData: Any? = null
    @kotlin.jvm.JvmField protected var enabled: Boolean = true
    @kotlin.jvm.JvmField protected var fixtureModificationHandler: FixtureModificationHandler<T>? = null
    @kotlin.jvm.JvmField protected var owner: Any? = null

    constructor() : this(CollisionBody.TYPICAL_FIXTURE_COUNT)
    constructor(fixtureCount: Int) {
        fixtures = TrackedFixtureList(if (fixtureCount <= 0) CollisionBody.TYPICAL_FIXTURE_COUNT else fixtureCount)
        fixturesUnmodifiable = object : AbstractList<T>() {
            override val size: Int get() = fixtures.size
            override fun get(index: Int): T = fixtures[index]
            override fun iterator(): Iterator<T> = listIterator()
            override fun listIterator(): ListIterator<T> = listIterator(0)
            override fun listIterator(index: Int): ListIterator<T> {
                if (index < 0 || index > size) throw IndexOutOfBoundsException()
                val tracked = fixtures
                val expected = (tracked as TrackedFixtureList<T>).version
                return object : ListIterator<T> {
                    private var cursor = index
                    override fun hasNext() = cursor < fixtures.size
                    override fun next(): T {
                        if (expected != tracked.version) throw ConcurrentModificationException()
                        if (!hasNext()) throw NoSuchElementException()
                        return fixtures[cursor++]
                    }
                    override fun hasPrevious() = cursor > 0
                    override fun previous(): T {
                        if (expected != tracked.version) throw ConcurrentModificationException()
                        if (!hasPrevious()) throw NoSuchElementException()
                        return fixtures[--cursor]
                    }
                    override fun nextIndex() = cursor
                    override fun previousIndex() = cursor - 1
                }
            }
        }
        transform = Transform()
        transform0 = Transform()
    }

    protected constructor(body: AbstractCollisionBody<T>) : this() {
        enabled = body.enabled
        radius = body.radius
        transform.set(body.transform)
        transform0.set(body.transform0)
        for (index in body.fixtures.indices) fixtures.add(Unsafe.copy(body.getFixture(index)))
    }

    override fun addFixture(fixture: T?): CollisionBody<T> {
        val added = fixture ?: throw ArgumentNullException("fixture")
        fixtures.add(added)
        fixtureModificationHandler?.onFixtureAdded(added)
        return this
    }

    override fun removeFixture(fixture: T?): Boolean {
        val removed = fixtures.remove(fixture)
        if (removed && fixture != null) fixtureModificationHandler?.onFixtureRemoved(fixture)
        return removed
    }

    override fun removeFixture(index: Int): T {
        val removed = fixtures.removeAt(index)
        fixtureModificationHandler?.onFixtureRemoved(removed)
        return removed
    }

    override fun removeAllFixtures(): List<T> {
        val removed = ArrayList(fixtures)
        fixtureModificationHandler?.onAllFixturesRemoved()
        fixtures.clear()
        return removed
    }

    override fun removeFixture(point: Vector2): T? {
        for (index in fixtures.indices) {
            val fixture = fixtures[index]
            if (fixture.getShape().contains(point, transform)) {
                fixtures.removeAt(index)
                fixtureModificationHandler?.onFixtureRemoved(fixture)
                return fixture
            }
        }
        return null
    }

    override fun removeFixtures(point: Vector2): List<T> {
        val removed = ArrayList<T>()
        val iterator = fixtures.iterator()
        while (iterator.hasNext()) {
            val fixture = iterator.next()
            if (fixture.getShape().contains(point, transform)) {
                iterator.remove()
                fixtureModificationHandler?.onFixtureRemoved(fixture)
                removed.add(fixture)
            }
        }
        return removed
    }

    override fun containsFixture(fixture: T?) = fixtures.contains(fixture)
    override fun getFixture(index: Int) = fixtures[index]
    override fun getFixture(point: Vector2): T? = fixtures.firstOrNull { it.getShape().contains(point, transform) }
    override fun getFixtures(point: Vector2): List<T> = fixtures.filter { it.getShape().contains(point, transform) }
    override fun getFixtureCount() = fixtures.size
    override fun getFixtures(): List<T> = fixturesUnmodifiable
    override fun getFixtureIterator(): MutableIterator<T> = FixtureIterator()

    protected open fun setRotationDiscRadius(center: Vector2) {
        radius = 0.0
        for (fixture in fixtures) radius = max(radius, fixture.getShape().getRadius(center))
    }

    override fun rotate(theta: Double, x: Double, y: Double) = transform.rotate(theta, x, y)
    override fun rotate(rotation: Rotation, x: Double, y: Double) = transform.rotate(rotation, x, y)
    override fun rotate(theta: Double, point: Vector2) = transform.rotate(theta, point)
    override fun rotate(rotation: Rotation, point: Vector2) = transform.rotate(rotation, point)
    override fun rotate(theta: Double) = transform.rotate(theta)
    override fun rotate(rotation: Rotation) = transform.rotate(rotation)
    override fun rotateAboutCenter(theta: Double) = rotate(theta, getWorldCenter())
    override fun translate(x: Double, y: Double) = transform.translate(x, y)
    override fun translate(vector: Vector2) = transform.translate(vector)
    override fun translateToOrigin() { val center = getWorldCenter(); transform.translate(-center.x, -center.y) }
    override fun shift(shift: Vector2) = transform.translate(shift)
    override fun getTransform() = transform
    override fun getPreviousTransform() = transform0
    override fun getRotationDiscRadius() = radius
    override fun setTransform(transform: Transform?) { if (transform != null) this.transform.set(transform) }
    override fun getUserData() = userData
    override fun setUserData(data: Any?) { userData = data }

    override fun createAABB() = AABB(0.0, 0.0, 0.0, 0.0).also { computeAABB(transform, it) }
    override fun createAABB(transform: Transform) = AABB(0.0, 0.0, 0.0, 0.0).also { computeAABB(transform, it) }
    override fun computeAABB(result: AABB) = computeAABB(transform, result)
    override fun computeAABB(transform: Transform, result: AABB) {
        if (fixtures.isEmpty()) { result.zero(); return }
        fixtures[0].getShape().computeAABB(transform, result)
        val next = AABB(0.0, 0.0, 0.0, 0.0)
        for (index in 1 until fixtures.size) {
            fixtures[index].getShape().computeAABB(transform, next)
            result.union(next)
        }
    }

    override fun getLocalPoint(worldPoint: Vector2) = transform.getInverseTransformed(worldPoint)
    override fun getLocalPoint(worldPoint: Vector2, destination: Vector2) = transform.getInverseTransformed(worldPoint, destination)
    override fun getWorldPoint(localPoint: Vector2) = transform.getTransformed(localPoint)
    override fun getWorldPoint(localPoint: Vector2, destination: Vector2) = transform.getTransformed(localPoint, destination)
    override fun getLocalVector(worldVector: Vector2) = transform.getInverseTransformedR(worldVector)
    override fun getLocalVector(worldVector: Vector2, destination: Vector2) = transform.getInverseTransformedR(worldVector, destination)
    override fun getWorldVector(localVector: Vector2) = transform.getTransformedR(localVector)
    override fun getWorldVector(localVector: Vector2, destination: Vector2) = transform.getTransformedR(localVector, destination)
    override fun getWorldCenter() = transform.getTransformed(getLocalCenter())
    override fun contains(point: Vector2) = fixtures.any { it.getShape().contains(point, transform) }
    override fun isEnabled() = enabled
    override fun setEnabled(enabled: Boolean) { this.enabled = enabled }
    override fun getOwner() = owner
    override fun setOwner(owner: Any?) { this.owner = owner }
    override fun getFixtureModificationHandler() = fixtureModificationHandler
    override fun setFixtureModificationHandler(handler: FixtureModificationHandler<T>?) { fixtureModificationHandler = handler }

    private inner class FixtureIterator : MutableIterator<T> {
        private var index = -1
        private var removed = false
        override fun hasNext() = index + 1 < fixtures.size
        override fun next(): T {
            if (index + 1 >= fixtures.size) throw IndexOutOfBoundsException()
            index++
            removed = false
            return try { fixtures[index] } catch (_: IndexOutOfBoundsException) {
                throw ConcurrentModificationException()
            }
        }
        override fun remove() {
            if (index < 0 || removed) throw IllegalStateException()
            if (index >= fixtures.size) throw IndexOutOfBoundsException()
            try { removeFixture(index) } catch (_: IndexOutOfBoundsException) {
                throw ConcurrentModificationException()
            }
            index--
            removed = true
        }
    }

    private class TrackedFixtureList<E>(capacity: Int) : AbstractMutableList<E>() {
        private val backing = ArrayList<E>(capacity)
        var version: Int = 0
            private set
        override val size: Int get() = backing.size
        override fun get(index: Int): E = backing[index]
        override fun set(index: Int, element: E): E = backing.set(index, element)
        override fun add(index: Int, element: E) { backing.add(index, element); version++ }
        override fun removeAt(index: Int): E = backing.removeAt(index).also { version++ }
        override fun clear() { backing.clear(); version++ }
    }
}
