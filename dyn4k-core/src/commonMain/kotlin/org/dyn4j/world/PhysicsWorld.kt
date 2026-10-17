/*
 * Copyright (c) 2010-2022 William Bittle  http://www.dyn4j.org/
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
import org.dyn4j.collision.broadphase.BroadphaseDetector
import org.dyn4j.dynamics.BodyFixture
import org.dyn4j.dynamics.PhysicsBody
import org.dyn4j.dynamics.Settings
import org.dyn4j.dynamics.TimeStep
import org.dyn4j.dynamics.contact.ContactConstraint
import org.dyn4j.dynamics.contact.ContactConstraintSolver
import org.dyn4j.dynamics.contact.TimeOfImpactSolver
import org.dyn4j.dynamics.joint.Joint
import org.dyn4j.geometry.Shiftable
import org.dyn4j.geometry.Vector2
import org.dyn4j.world.listener.ContactListener
import org.dyn4j.world.listener.DestructionListener
import org.dyn4j.world.listener.StepListener
import org.dyn4j.world.listener.TimeOfImpactListener

interface PhysicsWorld<T : PhysicsBody, V : ContactCollisionData<T>> :
    CollisionWorld<T, BodyFixture, V>, Shiftable, DataContainer {
    companion object {
        @kotlin.jvm.JvmField val DEFAULT_INITIAL_JOINT_CAPACITY = 16
        @kotlin.jvm.JvmField val EARTH_GRAVITY = Vector2(0.0, -9.8)
        @kotlin.jvm.JvmField val ZERO_GRAVITY = Vector2(0.0, 0.0)
    }

    fun update(elapsedTime: Double): Boolean
    fun update(elapsedTime: Double, maximumSteps: Int): Boolean
    fun update(elapsedTime: Double, stepElapsedTime: Double): Boolean
    fun update(elapsedTime: Double, stepElapsedTime: Double, maximumSteps: Int): Boolean
    fun updatev(elapsedTime: Double)
    fun step(steps: Int)
    fun step(steps: Int, elapsedTime: Double)

    fun addJoint(joint: Joint<T>?)
    fun containsJoint(joint: Joint<T>?): Boolean
    fun removeJoint(index: Int): Boolean
    fun removeJoint(joint: Joint<T>?): Boolean
    fun removeAllBodiesAndJoints()
    fun removeAllBodiesAndJoints(notify: Boolean)
    fun removeBody(index: Int, notify: Boolean): Boolean
    fun removeBody(body: T?, notify: Boolean): Boolean
    fun removeAllBodies(notify: Boolean)
    fun removeAllJoints()
    fun removeAllJoints(notify: Boolean)

    fun getSettings(): Settings
    fun setSettings(settings: Settings?)
    fun setGravity(gravity: Vector2?)
    fun setGravity(x: Double, y: Double)
    fun getGravity(): Vector2

    fun getContactListeners(): List<ContactListener<T>?>
    fun getDestructionListeners(): List<DestructionListener<T>?>
    fun getStepListeners(): List<StepListener<T>?>
    fun getTimeOfImpactListeners(): List<TimeOfImpactListener<T>?>
    fun removeAllContactListeners()
    fun removeAllDestructionListeners()
    fun removeAllStepListeners()
    fun removeAllTimeOfImpactListeners()
    fun removeContactListener(listener: ContactListener<T>?): Boolean
    fun removeDestructionListener(listener: DestructionListener<T>?): Boolean
    fun removeStepListener(listener: StepListener<T>?): Boolean
    fun removeTimeOfImpactListener(listener: TimeOfImpactListener<T>?): Boolean
    fun addContactListener(listener: ContactListener<T>?): Boolean
    fun addDestructionListener(listener: DestructionListener<T>?): Boolean
    fun addStepListener(listener: StepListener<T>?): Boolean
    fun addTimeOfImpactListener(listener: TimeOfImpactListener<T>?): Boolean

    fun getValueMixer(): ValueMixer
    fun setValueMixer(valueMixer: ValueMixer?)
    fun setContactConstraintSolver(constraintSolver: ContactConstraintSolver<T>?)
    fun getContactConstraintSolver(): ContactConstraintSolver<T>
    fun setContinuousCollisionDetectionBroadphaseDetector(broadphaseDetector: BroadphaseDetector<T>?)
    fun getContinuousCollisionDetectionBroadphaseDetector(): BroadphaseDetector<T>
    fun setTimeOfImpactSolver(timeOfImpactSolver: TimeOfImpactSolver<T>?)
    fun getTimeOfImpactSolver(): TimeOfImpactSolver<T>

    fun getJointCount(): Int
    fun getJoint(index: Int): Joint<T>
    fun getJoints(): List<Joint<T>>
    fun getJointIterator(): MutableIterator<Joint<T>>
    fun getTimeStep(): TimeStep
    fun getAccumulatedTime(): Double
    fun setAccumulatedTime(elapsedTime: Double)
    fun isUpdateRequired(): Boolean
    fun setUpdateRequired(flag: Boolean)

    fun isInContact(body1: T?, body2: T?): Boolean
    fun getInContactBodies(body: T?, includeSensedContact: Boolean): List<T>
    fun getContacts(body: T?): List<ContactConstraint<T>>
    fun isJoined(body1: T?, body2: T?): Boolean
    fun isJointCollisionAllowed(body1: T?, body2: T?): Boolean
    fun getJoinedBodies(body: T?): List<T>
    fun getJoints(body: T?): List<Joint<T>>
}
