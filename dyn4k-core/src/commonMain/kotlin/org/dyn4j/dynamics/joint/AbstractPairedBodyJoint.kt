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

import org.dyn4j.Unsafe
import org.dyn4j.collision.CollisionBody
import org.dyn4j.dynamics.PhysicsBody
import org.dyn4j.exception.InvalidIndexException
import org.dyn4j.exception.SameObjectException

abstract class AbstractPairedBodyJoint<T : PhysicsBody> : AbstractJoint<T>, PairedBodyJoint<T> {
    @kotlin.jvm.JvmField protected val body1: T
    @kotlin.jvm.JvmField protected val body2: T

    @Suppress("UNCHECKED_CAST")
    constructor(body1: T?, body2: T?) : super(mutableListOf(body1, body2) as List<T>) {
        if (body1 === body2) throw SameObjectException("body1", "body2", body1)
        this.body1 = body1!!
        this.body2 = body2!!
    }

    protected constructor(joint: AbstractPairedBodyJoint<T>, body1: T?, body2: T?) :
        super(joint, mutableListOf(body1 ?: Unsafe.copy(joint.body1), body2 ?: Unsafe.copy(joint.body2))) {
        this.body1 = bodies[0]
        this.body2 = bodies[1]
    }

    abstract fun copy(body1: T?, body2: T?): AbstractPairedBodyJoint<T>

    protected fun getReducedMass(): Double {
        val first = body1.getMass().getMass()
        val second = body2.getMass().getMass()
        return if (first > 0.0 && second > 0.0) first * second / (first + second)
            else if (first > 0.0) first else second
    }

    protected fun getReducedInertia(): Double {
        val first = body1.getMass().getInertia()
        val second = body2.getMass().getInertia()
        return if (first > 0.0 && second > 0.0) first * second / (first + second)
            else if (first > 0.0) first else second
    }

    final override fun isEnabled(): Boolean = body1.isEnabled() && body2.isEnabled()
    final override fun getBody(index: Int): T = when (index) {
        0 -> body1
        1 -> body2
        else -> throw InvalidIndexException(index)
    }
    final override fun getBodyCount(): Int = 2
    final override fun isMember(body: CollisionBody<*>?): Boolean = body === body1 || body === body2
    final override fun setCollisionAllowed(flag: Boolean) {
        if (collisionAllowed != flag) {
            body1.setAtRest(false)
            body2.setAtRest(false)
        }
        super.setCollisionAllowed(flag)
    }
    final override fun getOtherBody(body: CollisionBody<*>?): T? =
        if (body === body1) body2 else if (body === body2) body1 else null
    final override fun getBody1(): T = body1
    final override fun getBody2(): T = body2
}
