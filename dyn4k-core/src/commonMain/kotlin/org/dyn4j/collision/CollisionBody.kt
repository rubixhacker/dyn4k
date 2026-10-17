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

internal expect fun <T> passNullable(value: T?): T

interface FixtureModificationHandler<T : Fixture> {
    fun onFixtureAdded(fixture: T)
    fun onFixtureRemoved(fixture: T)
    fun onAllFixturesRemoved()
}

interface CollisionBody<T : Fixture> : Transformable, Shiftable, DataContainer, Ownable, Copyable<CollisionBody<T>> {
    companion object { const val TYPICAL_FIXTURE_COUNT = 1 }
    override fun copy(): CollisionBody<T>
    fun addFixture(fixture: T?): CollisionBody<T>
    fun addFixture(convex: Convex?): T
    @kotlin.jvm.JvmSynthetic
    fun addFixture(absent: Nothing?): CollisionBody<T> = addFixture(fixture = null)
    fun getFixture(index: Int): T
    fun containsFixture(fixture: T?): Boolean
    fun getFixture(point: Vector2?): T?
    fun getFixtures(point: Vector2?): List<T>
    fun removeFixture(fixture: T?): Boolean
    fun removeFixture(index: Int): T
    fun removeAllFixtures(): List<T>
    fun removeFixture(point: Vector2?): T?
    fun removeFixtures(point: Vector2?): List<T>
    fun getFixtureCount(): Int
    fun getFixtures(): List<T>
    fun getFixtureIterator(): MutableIterator<T>
    fun contains(point: Vector2?): Boolean
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
    fun createAABB(transform: Transform?): AABB
    fun computeAABB(result: AABB)
    fun computeAABB(transform: Transform?, result: AABB)
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
        fixturesUnmodifiable = FixtureView(0, null, null)
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

    override fun removeFixture(point: Vector2?): T? {
        for (index in fixtures.indices) {
            val fixture = fixtures[index]
            if (fixture.getShape().contains(passNullable(point), transform)) {
                fixtures.removeAt(index)
                fixtureModificationHandler?.onFixtureRemoved(fixture)
                return fixture
            }
        }
        return null
    }

    override fun removeFixtures(point: Vector2?): List<T> {
        val removed = ArrayList<T>()
        val iterator = fixtures.iterator()
        while (iterator.hasNext()) {
            val fixture = iterator.next()
            if (fixture.getShape().contains(passNullable(point), transform)) {
                iterator.remove()
                fixtureModificationHandler?.onFixtureRemoved(fixture)
                removed.add(fixture)
            }
        }
        return removed
    }

    override fun containsFixture(fixture: T?) = fixtures.contains(fixture)
    override fun getFixture(index: Int) = fixtures[index]
    override fun getFixture(point: Vector2?): T? {
        val count = fixtures.size
        for (index in 0 until count) {
            val fixture = fixtures[index]
            if (fixture.getShape().contains(passNullable(point), transform)) return fixture
        }
        return null
    }
    override fun getFixtures(point: Vector2?): List<T> {
        val selected = ArrayList<T>()
        val count = fixtures.size
        for (index in 0 until count) {
            val fixture = fixtures[index]
            if (fixture.getShape().contains(passNullable(point), transform)) selected.add(fixture)
        }
        return selected
    }
    override fun getFixtureCount() = fixtures.size
    override fun getFixtures(): List<T> = fixturesUnmodifiable
    override fun getFixtureIterator(): MutableIterator<T> = FixtureIterator()

    protected open fun setRotationDiscRadius(center: Vector2?) {
        var nextRadius = 0.0
        val count = fixtures.size
        for (index in 0 until count) {
            nextRadius = max(nextRadius, fixtures[index].getShape().getRadius(passNullable(center)))
        }
        radius = nextRadius
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
    override fun createAABB(transform: Transform?) = AABB(0.0, 0.0, 0.0, 0.0).also { computeAABB(transform, it) }
    override fun computeAABB(result: AABB) = computeAABB(transform, result)
    override fun computeAABB(transform: Transform?, result: AABB) {
        val count = fixtures.size
        if (count == 0) { result.zero(); return }
        fixtures[0].getShape().computeAABB(passNullable(transform), result)
        val next = AABB(0.0, 0.0, 0.0, 0.0)
        for (index in 1 until count) {
            fixtures[index].getShape().computeAABB(passNullable(transform), next)
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
    override fun contains(point: Vector2?): Boolean {
        val count = fixtures.size
        for (index in 0 until count) {
            if (fixtures[index].getShape().contains(passNullable(point), transform)) return true
        }
        return false
    }
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

    private inner class FixtureView(
        private val start: Int,
        private val end: Int?,
        private val expectedVersion: Int?
    ) : AbstractList<T>() {
        private val tracked get() = fixtures as TrackedFixtureList<T>
        private fun checkVersion() {
            if (expectedVersion != null && expectedVersion != tracked.version) throw ConcurrentModificationException()
        }
        override val size: Int get() {
            checkVersion()
            return (end ?: fixtures.size) - start
        }
        override fun get(index: Int): T {
            if (index < 0 || index >= size) throw IndexOutOfBoundsException()
            return fixtures[start + index]
        }
        override fun subList(fromIndex: Int, toIndex: Int): List<T> {
            val count = size
            if (fromIndex < 0 || toIndex > count || fromIndex > toIndex) throw IndexOutOfBoundsException()
            return FixtureView(start + fromIndex, start + toIndex, tracked.version)
        }
        override fun iterator(): Iterator<T> = listIterator()
        override fun listIterator(): ListIterator<T> = listIterator(0)
        override fun listIterator(index: Int): ListIterator<T> {
            if (index < 0 || index > size) throw IndexOutOfBoundsException()
            val expected = tracked.version
            return object : ListIterator<T> {
                private var cursor = index
                private fun check() {
                    if (expected != tracked.version) throw ConcurrentModificationException()
                }
                override fun hasNext() = cursor < size
                override fun next(): T {
                    check()
                    if (!hasNext()) throw NoSuchElementException()
                    return get(cursor++)
                }
                override fun hasPrevious() = cursor > 0
                override fun previous(): T {
                    check()
                    if (!hasPrevious()) throw NoSuchElementException()
                    return get(--cursor)
                }
                override fun nextIndex() = cursor
                override fun previousIndex() = cursor - 1
            }
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
        override fun subList(fromIndex: Int, toIndex: Int): MutableList<E> {
            if (fromIndex < 0 || toIndex > size || fromIndex > toIndex) throw IndexOutOfBoundsException()
            return TrackedSubList(fromIndex, toIndex, null)
        }
        override fun iterator(): MutableIterator<E> = listIterator()
        override fun listIterator(): MutableListIterator<E> = listIterator(0)
        override fun listIterator(index: Int): MutableListIterator<E> {
            if (index < 0 || index > size) throw IndexOutOfBoundsException()
            return object : MutableListIterator<E> {
                private var cursor = index
                private var lastReturned = -1
                private var expected = version
                private fun checkVersion() {
                    if (expected != version) throw ConcurrentModificationException()
                }
                override fun hasNext() = cursor < size
                override fun next(): E {
                    checkVersion()
                    if (!hasNext()) throw NoSuchElementException()
                    lastReturned = cursor
                    return backing[cursor++]
                }
                override fun hasPrevious() = cursor > 0
                override fun previous(): E {
                    checkVersion()
                    if (!hasPrevious()) throw NoSuchElementException()
                    lastReturned = --cursor
                    return backing[cursor]
                }
                override fun nextIndex() = cursor
                override fun previousIndex() = cursor - 1
                override fun remove() {
                    if (lastReturned < 0) throw IllegalStateException()
                    checkVersion()
                    removeAt(lastReturned)
                    if (lastReturned < cursor) cursor--
                    lastReturned = -1
                    expected = version
                }
                override fun set(element: E) {
                    if (lastReturned < 0) throw IllegalStateException()
                    checkVersion()
                    backing[lastReturned] = element
                }
                override fun add(element: E) {
                    checkVersion()
                    this@TrackedFixtureList.add(cursor++, element)
                    lastReturned = -1
                    expected = version
                }
            }
        }

        private inner class TrackedSubList(
            private val start: Int,
            private var end: Int,
            private val parent: TrackedSubList?
        ) : AbstractMutableList<E>() {
            private var expected = version
            private fun checkVersion() {
                if (expected != version) throw ConcurrentModificationException()
            }
            private fun changed(delta: Int) {
                var current: TrackedSubList? = this
                while (current != null) {
                    current.end += delta
                    current.expected = version
                    current = current.parent
                }
            }
            override val size: Int get() { checkVersion(); return end - start }
            override fun get(index: Int): E {
                val count = size
                if (index < 0 || index >= count) throw IndexOutOfBoundsException()
                return backing[start + index]
            }
            override fun set(index: Int, element: E): E {
                val count = size
                if (index < 0 || index >= count) throw IndexOutOfBoundsException()
                return backing.set(start + index, element)
            }
            override fun add(index: Int, element: E) {
                val count = size
                if (index < 0 || index > count) throw IndexOutOfBoundsException()
                this@TrackedFixtureList.add(start + index, element)
                changed(1)
            }
            override fun removeAt(index: Int): E {
                val count = size
                if (index < 0 || index >= count) throw IndexOutOfBoundsException()
                val removed = this@TrackedFixtureList.removeAt(start + index)
                changed(-1)
                return removed
            }
            override fun clear() {
                val count = size
                if (count == 0) { version++; changed(0); return }
                for (index in count - 1 downTo 0) this@TrackedFixtureList.removeAt(start + index)
                changed(-count)
            }
            override fun subList(fromIndex: Int, toIndex: Int): MutableList<E> {
                val count = size
                if (fromIndex < 0 || toIndex > count || fromIndex > toIndex) throw IndexOutOfBoundsException()
                return TrackedSubList(start + fromIndex, start + toIndex, this)
            }
            override fun iterator(): MutableIterator<E> = listIterator()
            override fun listIterator(): MutableListIterator<E> = listIterator(0)
            override fun listIterator(index: Int): MutableListIterator<E> {
                val count = size
                if (index < 0 || index > count) throw IndexOutOfBoundsException()
                return object : MutableListIterator<E> {
                    private var cursor = index
                    private var lastReturned = -1
                    private var iteratorVersion = version
                    private fun check() {
                        if (iteratorVersion != version) throw ConcurrentModificationException()
                    }
                    override fun hasNext() = cursor < end - start
                    override fun next(): E {
                        check()
                        if (!hasNext()) throw NoSuchElementException()
                        lastReturned = cursor
                        return get(cursor++)
                    }
                    override fun hasPrevious() = cursor > 0
                    override fun previous(): E {
                        check()
                        if (!hasPrevious()) throw NoSuchElementException()
                        lastReturned = --cursor
                        return get(cursor)
                    }
                    override fun nextIndex() = cursor
                    override fun previousIndex() = cursor - 1
                    override fun remove() {
                        if (lastReturned < 0) throw IllegalStateException()
                        check()
                        this@TrackedSubList.removeAt(lastReturned)
                        if (lastReturned < cursor) cursor--
                        lastReturned = -1
                        iteratorVersion = version
                    }
                    override fun set(element: E) {
                        if (lastReturned < 0) throw IllegalStateException()
                        check()
                        this@TrackedSubList[lastReturned] = element
                    }
                    override fun add(element: E) {
                        check()
                        this@TrackedSubList.add(cursor++, element)
                        lastReturned = -1
                        iteratorVersion = version
                    }
                }
            }
        }
    }
}
