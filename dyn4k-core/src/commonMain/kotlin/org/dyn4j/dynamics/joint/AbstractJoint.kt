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
package org.dyn4j.dynamics.joint

import kotlin.math.sqrt
import org.dyn4j.Epsilon
import org.dyn4j.collision.CollisionBody
import org.dyn4j.dynamics.PhysicsBody
import org.dyn4j.exception.ArgumentNullException
import org.dyn4j.exception.EmptyCollectionException
import org.dyn4j.exception.NullElementException
import org.dyn4j.geometry.Geometry

abstract class AbstractJoint<T : PhysicsBody> : Joint<T> {
    @kotlin.jvm.JvmField protected val bodies: MutableList<T>
    @kotlin.jvm.JvmField protected var collisionAllowed: Boolean = false
    @kotlin.jvm.JvmField protected var userData: Any? = null
    @kotlin.jvm.JvmField protected var owner: Any? = null

    constructor(bodies: List<T>?) {
        if (bodies == null) throw ArgumentNullException("bodies")
        if (bodies.isEmpty()) throw EmptyCollectionException("bodies")
        @Suppress("UNCHECKED_CAST")
        val nullableBodies = bodies as List<T?>
        for (index in bodies.indices) {
            if (nullableBodies[index] == null) throw NullElementException("bodies", index)
        }
        this.bodies = BodyView(bodies)
    }

    protected constructor(joint: AbstractJoint<T>, bodies: List<T>) {
        this.bodies = BodyView(bodies)
        this.collisionAllowed = joint.collisionAllowed
    }

    override fun toString(): String =
        "HashCode=${hashCode()}|${super.toString()}|IsCollisionAllowed=$collisionAllowed"

    final override fun getBodies(): MutableList<T> = bodies
    override fun getBodyCount(): Int = bodies.size
    override fun getBody(index: Int): T = bodies[index]
    final override fun getBodyIterator(): MutableIterator<T> = bodies.iterator()
    override fun isEnabled(): Boolean {
        for (body in bodies) if (!body.isEnabled()) return false
        return true
    }
    override fun isMember(body: CollisionBody<*>?): Boolean = bodies.any { it === body }
    override fun isCollisionAllowed(): Boolean = collisionAllowed
    override fun setCollisionAllowed(flag: Boolean) { collisionAllowed = flag }
    override fun getUserData(): Any? = userData
    override fun setUserData(data: Any?) { userData = data }
    override fun getOwner(): Any? = owner
    override fun setOwner(owner: Any?) { this.owner = owner }

    companion object {
        @kotlin.jvm.JvmStatic protected fun getFrequency(naturalFrequency: Double): Double =
            naturalFrequency / Geometry.TWO_PI
        @kotlin.jvm.JvmStatic protected fun getNaturalFrequency(frequency: Double): Double =
            Geometry.TWO_PI * frequency
        @kotlin.jvm.JvmStatic protected fun getNaturalFrequency(stiffness: Double, mass: Double): Double =
            if (mass <= Epsilon.E) 0.0 else sqrt(stiffness / mass)
        @kotlin.jvm.JvmStatic protected fun getSpringDampingCoefficient(
            mass: Double, naturalFrequency: Double, dampingRatio: Double
        ): Double = dampingRatio * 2.0 * mass * naturalFrequency
        @kotlin.jvm.JvmStatic protected fun getSpringStiffness(mass: Double, naturalFrequency: Double): Double =
            mass * naturalFrequency * naturalFrequency
        @kotlin.jvm.JvmStatic protected fun getConstraintImpulseMixing(
            deltaTime: Double, stiffness: Double, damping: Double
        ): Double {
            val mixing = deltaTime * (deltaTime * stiffness + damping)
            return if (mixing <= Epsilon.E) 0.0 else 1.0 / mixing
        }
        @kotlin.jvm.JvmStatic protected fun getErrorReductionParameter(
            deltaTime: Double, stiffness: Double, damping: Double
        ): Double {
            val denominator = deltaTime * stiffness + damping
            return if (denominator <= Epsilon.E) 0.0 else stiffness / denominator
        }
    }

    private class BodyView<E>(private val source: List<E>) : AbstractMutableList<E>() {
        override val size: Int get() = source.size
        override fun get(index: Int): E = source[index]
        override fun add(index: Int, element: E): Unit = throw UnsupportedOperationException()
        override fun add(element: E): Boolean = throw UnsupportedOperationException()
        override fun addAll(elements: Collection<E>): Boolean = throw UnsupportedOperationException()
        override fun addAll(index: Int, elements: Collection<E>): Boolean = throw UnsupportedOperationException()
        override fun removeAt(index: Int): E = throw UnsupportedOperationException()
        override fun remove(element: E): Boolean = throw UnsupportedOperationException()
        override fun removeAll(elements: Collection<E>): Boolean = throw UnsupportedOperationException()
        override fun retainAll(elements: Collection<E>): Boolean = throw UnsupportedOperationException()
        override fun set(index: Int, element: E): E = throw UnsupportedOperationException()
        override fun clear(): Unit = throw UnsupportedOperationException()
        override fun iterator(): MutableIterator<E> = object : MutableIterator<E> {
            private val delegate = source.iterator()
            override fun hasNext() = delegate.hasNext()
            override fun next() = delegate.next()
            override fun remove(): Unit = throw UnsupportedOperationException()
        }
        override fun listIterator(index: Int): MutableListIterator<E> {
            val delegate = source.listIterator(index)
            return object : MutableListIterator<E> {
                override fun hasNext() = delegate.hasNext()
                override fun next() = delegate.next()
                override fun hasPrevious() = delegate.hasPrevious()
                override fun previous() = delegate.previous()
                override fun nextIndex() = delegate.nextIndex()
                override fun previousIndex() = delegate.previousIndex()
                override fun add(element: E): Unit = throw UnsupportedOperationException()
                override fun remove(): Unit = throw UnsupportedOperationException()
                override fun set(element: E): Unit = throw UnsupportedOperationException()
            }
        }
    }
}
