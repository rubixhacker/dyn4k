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
import kotlin.math.max

interface CollisionItem<T : CollisionBody<E>, E : Fixture> : Copyable<CollisionItem<T, E>> {
    fun getBody(): T
    fun getFixture(): E
}

abstract class AbstractCollisionItem<T : CollisionBody<E>, E : Fixture> : CollisionItem<T, E>, Copyable<CollisionItem<T, E>> {
    companion object {
        @kotlin.jvm.JvmStatic fun getHashCode(body: CollisionBody<*>, fixture: Fixture): Int =
            (1 * 17 + body.hashCode()) * 17 + fixture.hashCode()

        @kotlin.jvm.JvmStatic fun equals(item: CollisionItem<*, *>?, obj: Any?): Boolean =
            item === obj || item != null && obj is CollisionItem<*, *> &&
                item.getBody() === obj.getBody() && item.getFixture() === obj.getFixture()
    }
}

class BasicCollisionItem<T : CollisionBody<E>, E : Fixture> : AbstractCollisionItem<T, E>, CollisionItem<T, E> {
    private val body: T
    private val fixture: E

    constructor(body: T, fixture: E) { this.body = body; this.fixture = fixture }
    protected constructor(item: BasicCollisionItem<T, E>) : this(item.body, item.fixture)
    override fun getBody() = body
    override fun getFixture() = fixture
    override fun copy() = BasicCollisionItem(this)
    override fun equals(other: Any?) = AbstractCollisionItem.equals(this, other)
    override fun hashCode() = AbstractCollisionItem.getHashCode(body, fixture)
}

interface CollisionPair<T> : Copyable<CollisionPair<T>> {
    fun getFirst(): T
    fun getSecond(): T
}

abstract class AbstractCollisionPair<T> : CollisionPair<T>, Copyable<CollisionPair<T>> {
    companion object {
        @kotlin.jvm.JvmStatic fun getHashCode(body1: CollisionBody<*>, fixture1: Fixture,
                                   body2: CollisionBody<*>, fixture2: Fixture): Int =
            AbstractCollisionItem.getHashCode(body1, fixture1) +
                AbstractCollisionItem.getHashCode(body2, fixture2)

        @kotlin.jvm.JvmStatic fun getHashCode(item1: Any, item2: Any): Int = item1.hashCode() + item2.hashCode()

        @kotlin.jvm.JvmStatic fun equals(pair: CollisionPair<*>?, obj: Any?): Boolean {
            if (pair === obj) return true
            if (pair == null || obj !is CollisionPair<*>) return false
            val first = pair.getFirst()
            val second = pair.getSecond()
            return first == obj.getFirst() && second == obj.getSecond() ||
                first == obj.getSecond() && second == obj.getFirst()
        }
    }
}

class BasicCollisionPair<T> : AbstractCollisionPair<T>, CollisionPair<T> {
    private val first: T
    private val second: T

    constructor(first: T, second: T) { this.first = first; this.second = second }
    protected constructor(pair: BasicCollisionPair<T>) : this(pair.first, pair.second)
    override fun getFirst() = first
    override fun getSecond() = second
    override fun copy() = BasicCollisionPair(this)
    override fun equals(other: Any?) = AbstractCollisionPair.equals(this, other)
    override fun hashCode() = AbstractCollisionPair.getHashCode(first as Any, second as Any)
}

class Collisions private constructor() {
    companion object {
        @kotlin.jvm.JvmStatic fun getEstimatedCollisionPairs(n: Int) = n * 4
        @kotlin.jvm.JvmStatic fun getEstimatedCollisionsPerObject() = 4
        @kotlin.jvm.JvmStatic fun getEstimatedRaycastCollisions(n: Int) = max(1.0, n * 0.02).toInt()
    }
}
