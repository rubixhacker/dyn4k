/*
 * Copyright (c) 2010-2020 William Bittle  http://www.dyn4j.org/
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

import org.dyn4j.dynamics.PhysicsBody
import org.dyn4j.dynamics.contact.ContactConstraint
import org.dyn4j.dynamics.joint.Joint

class ConstraintGraphNode<T : PhysicsBody>(@kotlin.jvm.JvmField protected val body: T) {
    @kotlin.jvm.JvmField protected val contactConstraints: MutableList<ContactConstraint<T>> = ArrayList()
    @kotlin.jvm.JvmField protected val joints: MutableList<Joint<T>> = ArrayList()
    @kotlin.jvm.JvmField protected val contactConstraintsUnmodifiable: List<ContactConstraint<T>> =
        LiveReadOnlyList(contactConstraints)
    @kotlin.jvm.JvmField protected val jointsUnmodifiable: List<Joint<T>> = LiveReadOnlyList(joints)

    fun getBody(): T = body
    fun getJoints(): List<Joint<T>> = jointsUnmodifiable
    fun getContactConstraints(): List<ContactConstraint<T>> = contactConstraintsUnmodifiable

    internal fun mutableContacts(): MutableList<ContactConstraint<T>> = contactConstraints
    internal fun mutableJoints(): MutableList<Joint<T>> = joints
}

private class LiveReadOnlyList<T>(private val source: List<T>) : AbstractList<T>() {
    override val size: Int get() = source.size
    override fun get(index: Int): T = source[index]
}
