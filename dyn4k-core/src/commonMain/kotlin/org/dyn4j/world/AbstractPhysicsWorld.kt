/*
 * Copyright (c) 2010-2026 William Bittle  http://www.dyn4j.org/
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
import org.dyn4j.collision.CollisionPair
import org.dyn4j.collision.Collisions
import org.dyn4j.collision.broadphase.BroadphaseDetector
import org.dyn4j.collision.broadphase.CollisionBodyBroadphaseFilter
import org.dyn4j.collision.broadphase.DynamicAABBTree
import org.dyn4j.collision.broadphase.StaticValueAABBExpansionMethod
import org.dyn4j.collision.continuous.TimeOfImpact
import org.dyn4j.dynamics.BodyFixture
import org.dyn4j.dynamics.ContinuousDetectionMode
import org.dyn4j.dynamics.PhysicsBody
import org.dyn4j.dynamics.Settings
import org.dyn4j.dynamics.TimeStep
import org.dyn4j.dynamics.contact.Contact
import org.dyn4j.dynamics.contact.ContactConstraint
import org.dyn4j.dynamics.contact.ContactConstraintSolver
import org.dyn4j.dynamics.contact.ContactUpdateHandler
import org.dyn4j.dynamics.contact.ForceCollisionTimeOfImpactSolver
import org.dyn4j.dynamics.contact.SequentialImpulses
import org.dyn4j.dynamics.contact.TimeOfImpactSolver
import org.dyn4j.dynamics.joint.Joint
import org.dyn4j.exception.ArgumentNullException
import org.dyn4j.exception.ObjectAlreadyExistsException
import org.dyn4j.exception.ObjectAlreadyOwnedException
import org.dyn4j.geometry.Shiftable
import org.dyn4j.geometry.Vector2
import org.dyn4j.world.listener.ContactListener
import org.dyn4j.world.listener.DestructionListener
import org.dyn4j.world.listener.StepListener
import org.dyn4j.world.listener.TimeOfImpactListener
import org.dyn4j.JvmFieldBridge

abstract class AbstractPhysicsWorld<T : PhysicsBody, V : ContactCollisionData<T>> :
    AbstractCollisionWorld<T, BodyFixture, V>, PhysicsWorld<T, V>, Shiftable, DataContainer {

    @get:kotlin.jvm.JvmName("settingsField-dyn4k")
    @get:kotlin.jvm.JvmSynthetic
    @JvmFieldBridge protected val settings: Settings
    @get:kotlin.jvm.JvmName("timeStepField-dyn4k")
    @get:kotlin.jvm.JvmSynthetic
    @JvmFieldBridge protected val timeStep: TimeStep
    @get:kotlin.jvm.JvmName("gravityField-dyn4k")
    @get:kotlin.jvm.JvmSynthetic
    @JvmFieldBridge protected val gravity: Vector2
    @get:kotlin.jvm.JvmName("valueMixerField-dyn4k")
    @get:kotlin.jvm.JvmSynthetic
    @set:kotlin.jvm.JvmName("setValueMixerField-dyn4k")
    @set:kotlin.jvm.JvmSynthetic
    @JvmFieldBridge protected var valueMixer: ValueMixer
    @get:kotlin.jvm.JvmName("contactConstraintSolverField-dyn4k")
    @get:kotlin.jvm.JvmSynthetic
    @set:kotlin.jvm.JvmName("setContactConstraintSolverField-dyn4k")
    @set:kotlin.jvm.JvmSynthetic
    @JvmFieldBridge protected var contactConstraintSolver: ContactConstraintSolver<T>
    @get:kotlin.jvm.JvmName("timeOfImpactSolverField-dyn4k")
    @get:kotlin.jvm.JvmSynthetic
    @set:kotlin.jvm.JvmName("setTimeOfImpactSolverField-dyn4k")
    @set:kotlin.jvm.JvmSynthetic
    @JvmFieldBridge protected var timeOfImpactSolver: TimeOfImpactSolver<T>
    @get:kotlin.jvm.JvmName("ccdBroadphaseField-dyn4k")
    @get:kotlin.jvm.JvmSynthetic
    @set:kotlin.jvm.JvmName("setCcdBroadphaseField-dyn4k")
    @set:kotlin.jvm.JvmSynthetic
    @JvmFieldBridge protected var ccdBroadphase: BroadphaseDetector<T>
    @get:kotlin.jvm.JvmName("jointsField-dyn4k")
    @get:kotlin.jvm.JvmSynthetic
    @JvmFieldBridge protected val joints: MutableList<Joint<T>>
    @get:kotlin.jvm.JvmName("jointsUnmodifiableField-dyn4k")
    @get:kotlin.jvm.JvmSynthetic
    @JvmFieldBridge protected val jointsUnmodifiable: List<Joint<T>>
    @get:kotlin.jvm.JvmName("contactListenersField-dyn4k")
    @get:kotlin.jvm.JvmSynthetic
    @JvmFieldBridge protected val contactListeners: MutableList<ContactListener<T>?>
    @get:kotlin.jvm.JvmName("contactListenersUnmodifiableField-dyn4k")
    @get:kotlin.jvm.JvmSynthetic
    @JvmFieldBridge protected val contactListenersUnmodifiable: List<ContactListener<T>?>
    @get:kotlin.jvm.JvmName("destructionListenersField-dyn4k")
    @get:kotlin.jvm.JvmSynthetic
    @JvmFieldBridge protected val destructionListeners: MutableList<DestructionListener<T>?>
    @get:kotlin.jvm.JvmName("destructionListenersUnmodifiableField-dyn4k")
    @get:kotlin.jvm.JvmSynthetic
    @JvmFieldBridge protected val destructionListenersUnmodifiable: List<DestructionListener<T>?>
    @get:kotlin.jvm.JvmName("timeOfImpactListenersField-dyn4k")
    @get:kotlin.jvm.JvmSynthetic
    @JvmFieldBridge protected val timeOfImpactListeners: MutableList<TimeOfImpactListener<T>?>
    @get:kotlin.jvm.JvmName("timeOfImpactListenersUnmodifiableField-dyn4k")
    @get:kotlin.jvm.JvmSynthetic
    @JvmFieldBridge protected val timeOfImpactListenersUnmodifiable: List<TimeOfImpactListener<T>?>
    @get:kotlin.jvm.JvmName("stepListenersField-dyn4k")
    @get:kotlin.jvm.JvmSynthetic
    @JvmFieldBridge protected val stepListeners: MutableList<StepListener<T>?>
    @get:kotlin.jvm.JvmName("stepListenersUnmodifiableField-dyn4k")
    @get:kotlin.jvm.JvmSynthetic
    @JvmFieldBridge protected val stepListenersUnmodifiable: List<StepListener<T>?>
    @get:kotlin.jvm.JvmName("timeField-dyn4k")
    @get:kotlin.jvm.JvmSynthetic
    @set:kotlin.jvm.JvmName("setTimeField-dyn4k")
    @set:kotlin.jvm.JvmSynthetic
    @JvmFieldBridge protected var time: Double = 0.0
    @get:kotlin.jvm.JvmName("updateRequiredField-dyn4k")
    @get:kotlin.jvm.JvmSynthetic
    @set:kotlin.jvm.JvmName("setUpdateRequiredField-dyn4k")
    @set:kotlin.jvm.JvmSynthetic
    @JvmFieldBridge protected var updateRequired: Boolean = true
    @get:kotlin.jvm.JvmName("constraintGraphField-dyn4k")
    @get:kotlin.jvm.JvmSynthetic
    @JvmFieldBridge protected val constraintGraph: ConstraintGraph<T>
    @get:kotlin.jvm.JvmName("contactCollisionsField-dyn4k")
    @get:kotlin.jvm.JvmSynthetic
    @JvmFieldBridge protected val contactCollisions: MutableList<V>
    @get:kotlin.jvm.JvmName("ccdCollisionDataField-dyn4k")
    @get:kotlin.jvm.JvmSynthetic
    @JvmFieldBridge protected val ccdCollisionData: MutableSet<CollisionPair<T>>

    constructor() : this(CollisionWorld.DEFAULT_INITIAL_BODY_CAPACITY, PhysicsWorld.DEFAULT_INITIAL_JOINT_CAPACITY)

    constructor(initialBodyCapacity: Int, initialJointCapacity: Int) : super(initialBodyCapacity) {
        val bodyCapacity = if (initialBodyCapacity > 0) initialBodyCapacity else CollisionWorld.DEFAULT_INITIAL_BODY_CAPACITY
        val jointCapacity = if (initialJointCapacity > 0) initialJointCapacity else PhysicsWorld.DEFAULT_INITIAL_JOINT_CAPACITY
        settings = Settings()
        timeStep = TimeStep(settings.getStepFrequency())
        gravity = PhysicsWorld.EARTH_GRAVITY.copy()
        broadphaseFilter = PhysicsBodyBroadphaseCollisionDataFilter(this)
        valueMixer = ValueMixer.DEFAULT_MIXER
        contactConstraintSolver = SequentialImpulses()
        timeOfImpactSolver = ForceCollisionTimeOfImpactSolver()
        ccdBroadphase = DynamicAABBTree(
            CollisionBodyBroadphaseFilter(), PhysicsBodySweptAABBProducer(),
            StaticValueAABBExpansionMethod(0.2), bodyCapacity
        )
        ccdBroadphase.setUpdateTrackingEnabled(true)
        val jointList = WorldTrackedArrayList<Joint<T>>(jointCapacity)
        joints = jointList
        jointsUnmodifiable = jointList.liveView()
        val contactListenerList = WorldTrackedArrayList<ContactListener<T>?>()
        val destructionListenerList = WorldTrackedArrayList<DestructionListener<T>?>()
        val timeOfImpactListenerList = WorldTrackedArrayList<TimeOfImpactListener<T>?>()
        val stepListenerList = WorldTrackedArrayList<StepListener<T>?>()
        contactListeners = contactListenerList
        destructionListeners = destructionListenerList
        timeOfImpactListeners = timeOfImpactListenerList
        stepListeners = stepListenerList
        contactListenersUnmodifiable = contactListenerList.liveView()
        destructionListenersUnmodifiable = destructionListenerList.liveView()
        timeOfImpactListenersUnmodifiable = timeOfImpactListenerList.liveView()
        stepListenersUnmodifiable = stepListenerList.liveView()
        constraintGraph = ConstraintGraph(bodyCapacity, jointCapacity)
        contactCollisions = ArrayList(Collisions.getEstimatedCollisionPairs(bodyCapacity))
        ccdCollisionData = LinkedHashSet()
    }

    override fun update(elapsedTime: Double): Boolean = update(elapsedTime, -1.0, 1)
    override fun update(elapsedTime: Double, maximumSteps: Int): Boolean = update(elapsedTime, -1.0, maximumSteps)
    override fun update(elapsedTime: Double, stepElapsedTime: Double): Boolean = update(elapsedTime, stepElapsedTime, 1)

    override fun update(elapsedTime: Double, stepElapsedTime: Double, maximumSteps: Int): Boolean {
        time += if (elapsedTime < 0.0) 0.0 else elapsedTime
        val frequency = settings.getStepFrequency()
        var steps = 0
        while (time >= frequency && steps < maximumSteps) {
            timeStep.update(if (stepElapsedTime <= 0.0) frequency else stepElapsedTime)
            time -= frequency
            step()
            steps++
        }
        return steps > 0
    }

    override fun updatev(elapsedTime: Double) {
        if (elapsedTime <= 0.0) return
        timeStep.update(elapsedTime)
        step()
    }

    override fun step(steps: Int) = step(steps, settings.getStepFrequency())

    override fun step(steps: Int, elapsedTime: Double) {
        if (steps <= 0 || elapsedTime <= 0.0) return
        repeat(steps) {
            timeStep.update(elapsedTime)
            step()
        }
    }

    override fun addBody(body: T?) {
        super.addBody(body)
        val added = body!!
        constraintGraph.addBody(added)
        ccdBroadphase.add(added)
    }

    override fun addJoint(joint: Joint<T>?) {
        if (joint == null) throw ArgumentNullException("joint")
        val owner = joint.getOwner()
        if (owner === this) throw ObjectAlreadyExistsException("joint", joint, owner)
        if (owner != null) throw ObjectAlreadyOwnedException("joint", joint, owner)
        for (i in 0 until joint.getBodyCount()) {
            val body = joint.getBody(i)
            if (!constraintGraph.containsBody(body)) {
                throw IllegalArgumentException("All bodies must be added to the world before the joint is added. The body $body doesn't exist.")
            }
        }
        joints.add(joint)
        joint.setOwner(this)
        constraintGraph.addJoint(joint)
    }

    override fun containsJoint(joint: Joint<T>?): Boolean = joints.contains(joint)
    override fun removeJoint(index: Int): Boolean = removeJoint(joints[index])
    override fun removeAllBodies() = removeAllBodiesAndJoints(false)
    override fun removeBody(index: Int): Boolean = removeBody(index, false)
    override fun removeBody(index: Int, notify: Boolean): Boolean = removeBody(bodies[index], notify)
    override fun removeBody(body: T?): Boolean = removeBody(body, false)
    override fun removeAllBodiesAndJoints() = removeAllBodiesAndJoints(false)
    override fun removeAllJoints() = removeAllJoints(false)
    override fun removeAllBodiesAndJoints(notify: Boolean) = removeAllBodies(notify)

    protected open fun destroyJoints(node: ConstraintGraphNode<T>, notify: Boolean) {
        val body = node.getBody()
        val connected = node.mutableJoints()
        val jointCount = connected.size
        for (j in 0 until jointCount) {
            val joint = connected[j]
            for (i in 0 until joint.getBodyCount()) {
                val other = joint.getBody(i)
                if (other === body) continue
                other.setAtRest(false)
                constraintGraph.getNode(other)?.mutableJoints()?.remove(joint)
            }
            joint.setOwner(null)
            if (notify) for (listener in destructionListeners) listener!!.destroyed(joint)
            joints.remove(joint)
        }
        node.mutableJoints().clear()
    }

    protected open fun destroyContacts(node: ConstraintGraphNode<T>, fixture: BodyFixture?, notify: Boolean) {
        val body = node.getBody()
        val iterator = node.mutableContacts().iterator()
        while (iterator.hasNext()) {
            val constraint = iterator.next()
            if (fixture != null && constraint.getFixture1() !== fixture && constraint.getFixture2() !== fixture) continue
            val other = constraint.getOtherBody(body)!!
            if (!constraint.isSensor() && constraint.isEnabled()) other.setAtRest(false)
            val data = collisionData.remove(constraint.getCollisionPair())
            if (notify) {
                for (contact in constraint.getContacts()) {
                    for (listener in contactListeners) listener!!.destroyed(data, contact)
                }
                for (listener in destructionListeners) listener!!.destroyed(constraint)
            }
            if (fixture != null) iterator.remove()
            constraintGraph.getNode(other)?.mutableContacts()?.remove(constraint)
        }
        if (fixture == null) node.mutableContacts().clear()
    }

    override fun removeBody(body: T?, notify: Boolean): Boolean {
        if (body == null) return false
        val removed = bodies.remove(body)
        if (removed) {
            body.setFixtureModificationHandler(null)
            body.setOwner(null)
            body.setAtRest(false)
            body.setEnabled(true)
            broadphaseDetector.remove(body)
            ccdBroadphase.remove(body)
            val node = constraintGraph.removeBody(body)
            destroyJoints(node, notify)
            destroyContacts(node, null, notify)
        }
        return removed
    }

    override fun removeJoint(joint: Joint<T>?): Boolean {
        val removed = joints.remove(joint)
        if (removed) {
            val attached = joint!!
            attached.setOwner(null)
            for (i in 0 until attached.getBodyCount()) attached.getBody(i).setAtRest(false)
            constraintGraph.removeJoint(attached)
        }
        return removed
    }

    override fun removeAllBodies(notify: Boolean) {
        if (!notify) {
            for (body in bodies) {
                body.setFixtureModificationHandler(null)
                body.setOwner(null)
                body.setAtRest(false)
                body.setEnabled(true)
            }
            for (joint in joints) joint.setOwner(null)
            clear()
            return
        }
        val count = bodies.size
        for (i in 0 until count) {
            val body = bodies[i]
            body.setFixtureModificationHandler(null)
            body.setOwner(null)
            body.setAtRest(false)
            body.setEnabled(true)
            val node = constraintGraph.removeBody(body)
            destroyJoints(node, true)
            destroyContacts(node, null, true)
            for (listener in destructionListeners) listener!!.destroyed(body)
        }
        clear()
    }

    protected open fun clear() {
        bodies.clear()
        broadphaseDetector.clear()
        ccdBroadphase.clear()
        collisionData.clear()
        constraintGraph.clear()
        contactCollisions.clear()
        joints.clear()
    }

    override fun removeAllJoints(notify: Boolean) {
        val count = joints.size
        for (i in 0 until count) {
            val joint = joints[i]
            joint.setOwner(null)
            for (i in 0 until joint.getBodyCount()) joint.getBody(i).setAtRest(false)
            if (notify) for (listener in destructionListeners) listener!!.destroyed(joint)
        }
        constraintGraph.removeAllJoints()
        joints.clear()
    }

    protected override fun handleFixtureRemoved(body: T, fixture: BodyFixture) {
        super.handleFixtureRemoved(body, fixture)
        constraintGraph.getNode(body)?.let { destroyContacts(it, fixture, true) }
    }

    protected override fun handleAllFixturesRemoved(body: T) {
        super.handleAllFixturesRemoved(body)
        constraintGraph.getNode(body)?.let { destroyContacts(it, null, true) }
    }

    override fun getSettings(): Settings = settings
    override fun setSettings(settings: Settings?) {
        if (settings != null) this.settings.set(settings)
    }

    override fun setGravity(gravity: Vector2?) {
        if (gravity != null) {
            this.gravity.x = gravity.x
            this.gravity.y = gravity.y
        }
    }

    override fun setGravity(x: Double, y: Double) {
        gravity.x = x
        gravity.y = y
    }

    override fun getGravity(): Vector2 = gravity
    override fun getValueMixer(): ValueMixer = valueMixer
    override fun setValueMixer(valueMixer: ValueMixer?) {
        this.valueMixer = valueMixer ?: throw ArgumentNullException("valueMixer")
    }

    override fun setContactConstraintSolver(constraintSolver: ContactConstraintSolver<T>?) {
        contactConstraintSolver = constraintSolver ?: throw ArgumentNullException("constraintSolver")
    }

    override fun getContactConstraintSolver(): ContactConstraintSolver<T> = contactConstraintSolver
    override fun getContinuousCollisionDetectionBroadphaseDetector(): BroadphaseDetector<T> = ccdBroadphase

    override fun setContinuousCollisionDetectionBroadphaseDetector(broadphaseDetector: BroadphaseDetector<T>?) {
        ccdBroadphase = broadphaseDetector ?: throw ArgumentNullException("broadphaseDetector")
        for (body in bodies) ccdBroadphase.add(body)
    }

    override fun setTimeOfImpactSolver(timeOfImpactSolver: TimeOfImpactSolver<T>?) {
        this.timeOfImpactSolver = timeOfImpactSolver ?: throw ArgumentNullException("timeOfImpactSolver")
    }

    override fun getTimeOfImpactSolver(): TimeOfImpactSolver<T> = timeOfImpactSolver
    override fun getJointCount(): Int = joints.size
    override fun getJoint(index: Int): Joint<T> = joints[index]
    override fun getJoints(): List<Joint<T>> = jointsUnmodifiable
    override fun getJointIterator(): MutableIterator<Joint<T>> = JointIterator()
    override fun getTimeStep(): TimeStep = timeStep
    override fun getAccumulatedTime(): Double = time
    override fun setAccumulatedTime(elapsedTime: Double) {
        if (elapsedTime < 0.0) return
        time = elapsedTime
    }

    override fun setUpdateRequired(flag: Boolean) {
        updateRequired = flag
    }

    override fun isUpdateRequired(): Boolean = updateRequired
    override fun isEmpty(): Boolean = bodies.isEmpty() && joints.isEmpty()

    override fun shift(shift: Vector2) {
        super.shift(shift)
        for (joint in joints) joint.shift(shift)
    }

    override fun isInContact(body1: T?, body2: T?): Boolean =
        body1 != null && body2 != null && constraintGraph.isInContact(body1, body2)
    override fun getContacts(body: T?): List<ContactConstraint<T>> = constraintGraph.getContacts(body)
    override fun getInContactBodies(body: T?, includeSensedContact: Boolean): List<T> =
        constraintGraph.getInContactBodies(body, includeSensedContact)
    override fun isJointCollisionAllowed(body1: T?, body2: T?): Boolean = constraintGraph.isJointCollisionAllowed(body1, body2)
    override fun isJoined(body1: T?, body2: T?): Boolean = constraintGraph.isJoined(body1, body2)
    override fun getJoints(body: T?): List<Joint<T>> = constraintGraph.getJoints(body)
    override fun getJoinedBodies(body: T?): List<T> = constraintGraph.getJoinedBodies(body)

    override fun getContactListeners(): List<ContactListener<T>?> = contactListenersUnmodifiable
    override fun getDestructionListeners(): List<DestructionListener<T>?> = destructionListenersUnmodifiable
    override fun getStepListeners(): List<StepListener<T>?> = stepListenersUnmodifiable
    override fun getTimeOfImpactListeners(): List<TimeOfImpactListener<T>?> = timeOfImpactListenersUnmodifiable

    override fun removeAllListeners() {
        super.removeAllListeners()
        stepListeners.clear()
        contactListeners.clear()
        destructionListeners.clear()
        timeOfImpactListeners.clear()
    }

    override fun removeAllContactListeners() = contactListeners.clear()
    override fun removeAllDestructionListeners() = destructionListeners.clear()
    override fun removeAllStepListeners() = stepListeners.clear()
    override fun removeAllTimeOfImpactListeners() = timeOfImpactListeners.clear()
    override fun removeContactListener(listener: ContactListener<T>?): Boolean = contactListeners.remove(listener)
    override fun removeDestructionListener(listener: DestructionListener<T>?): Boolean = destructionListeners.remove(listener)
    override fun removeStepListener(listener: StepListener<T>?): Boolean = stepListeners.remove(listener)
    override fun removeTimeOfImpactListener(listener: TimeOfImpactListener<T>?): Boolean = timeOfImpactListeners.remove(listener)
    override fun addContactListener(listener: ContactListener<T>?): Boolean = contactListeners.add(listener)
    override fun addDestructionListener(listener: DestructionListener<T>?): Boolean = destructionListeners.add(listener)
    override fun addStepListener(listener: StepListener<T>?): Boolean = stepListeners.add(listener)
    override fun addTimeOfImpactListener(listener: TimeOfImpactListener<T>?): Boolean = timeOfImpactListeners.add(listener)

    protected open fun step() {
        val stepListenerCount = stepListeners.size
        for (i in 0 until stepListenerCount) stepListeners[i]!!.begin(timeStep, this)
        if (updateRequired) {
            detect()
            for (i in 0 until stepListenerCount) stepListeners[i]!!.updatePerformed(timeStep, this)
            updateRequired = false
        }
        if (contactListeners.isNotEmpty()) {
            for (data in contactCollisions) {
                for (contact in data.getContactConstraint().getContacts()) {
                    for (listener in contactListeners) listener!!.preSolve(data, contact)
                }
            }
        }
        val mode = settings.getContinuousDetectionMode()
        for (body in bodies) body.getPreviousTransform().set(body.getTransform())
        constraintGraph.solve(contactConstraintSolver, gravity, timeStep, settings)
        if (contactListeners.isNotEmpty()) {
            for (data in contactCollisions) {
                for (contact in data.getContactConstraint().getContacts()) {
                    for (listener in contactListeners) listener!!.postSolve(data, contact)
                }
            }
        }
        for (i in 0 until stepListenerCount) stepListeners[i]!!.postSolve(timeStep, this)
        if (mode != ContinuousDetectionMode.NONE) {
            ccdBroadphase.update()
            solveTOI(mode)
            ccdBroadphase.clearUpdates()
        }
        detect()
        updateRequired = false
        for (i in 0 until stepListenerCount) stepListeners[i]!!.end(timeStep, this)
    }

    protected override fun processCollisions(iterator: MutableIterator<@kotlin.jvm.JvmSuppressWildcards V>) {
        constraintGraph.removeAllContactConstraints()
        contactCollisions.clear()
        val handler = WarmStartHandler()
        while (iterator.hasNext()) {
            val collision = iterator.next()
            val constraint = collision.getContactConstraint()
            if (!collision.isManifoldCollision() && constraint.getContacts().isEmpty()) continue
            handler.data = collision
            constraint.update(collision.getManifold(), settings, handler)
            if (collision.isManifoldCollision()) {
                collision.setContactConstraintCollision(true)
                constraintGraph.addContactConstraint(constraint)
                for (listener in contactListeners) listener!!.collision(collision)
                if (constraint.isEnabled() && !constraint.isSensor()) contactCollisions.add(collision)
            }
        }
    }

    protected open fun solveTOI(mode: ContinuousDetectionMode): Boolean {
        val listeners = timeOfImpactListeners
        val bulletsOnly = mode == ContinuousDetectionMode.BULLETS_ONLY
        val detected = ccdBroadphase.detectIterator()
        while (detected.hasNext()) ccdCollisionData.add(detected.next().copy())

        val pairMapping = HashMap<T, MutableList<T>>()
        val tracked = ccdCollisionData.iterator()
        while (tracked.hasNext()) {
            val pair = tracked.next()
            val body1 = pair.getFirst()
            val body2 = pair.getSecond()
            if (!ccdBroadphase.contains(body1) || !ccdBroadphase.contains(body2)) {
                tracked.remove()
                continue
            }
            if ((ccdBroadphase.isUpdated(body1) || ccdBroadphase.isUpdated(body2)) &&
                !ccdBroadphase.detect(body1, body2)
            ) {
                tracked.remove()
                continue
            }
            if (bulletsOnly && !body1.isBullet() && !body2.isBullet()) continue
            if (!body1.isEnabled() || !body2.isEnabled()) continue
            if (body1.isDynamic() && body2.isDynamic() && !body1.isBullet() && !body2.isBullet()) continue
            if (body1.getMass().isInfinite() && body2.getMass().isInfinite()) continue
            if (body1.isAtRest() && body2.isAtRest()) continue
            if (!isJointCollisionAllowed(body1, body2) || isInContact(body1, body2)) continue
            var allow = true
            for (listener in listeners) if (!listener!!.collision(body1, body2)) allow = false
            if (!allow) continue
            if (body1.isDynamic()) pairMapping.getOrPut(body1) { ArrayList() }.add(body2)
            else if (body2.isDynamic()) pairMapping.getOrPut(body2) { ArrayList() }.add(body1)
        }
        var solved = false
        for ((body, others) in pairMapping) solved = solveTOI(body, others, listeners) || solved
        return solved
    }

    protected open fun solveTOI(
        body1: T,
        others: List<@kotlin.jvm.JvmSuppressWildcards T>,
        listeners: List<@kotlin.jvm.JvmSuppressWildcards TimeOfImpactListener<T>?>
    ): Boolean {
        val t1 = 0.0
        var t2 = 1.0
        var minToi: TimeOfImpact? = null
        var minBody: T? = null
        val reusableItem = CollisionItemAdapter<T, BodyFixture>()
        for (body2 in others) {
            val toi = TimeOfImpact()
            val fixtureCount1 = body1.getFixtureCount()
            val fixtureCount2 = body2.getFixtureCount()
            val staticMultiFixture = body2.isStatic() && fixtureCount2 > 1
            val dt = timeStep.getDeltaTime()
            val velocity1 = body1.getLinearVelocity().product(dt)
            val velocity2 = body2.getLinearVelocity().product(dt)
            val angularVelocity1 = body1.getAngularVelocity() * dt
            val angularVelocity2 = body2.getAngularVelocity() * dt
            val transform1 = body1.getPreviousTransform()
            val transform2 = body2.getPreviousTransform()
            for (k in 0 until fixtureCount2) {
                val fixture2 = body2.getFixture(k)
                if (staticMultiFixture) {
                    val sweptAABB = ccdBroadphase.getAABB(body1)
                    reusableItem.set(body2, fixture2)
                    val staticAABB = broadphaseDetector.getAABB(reusableItem)
                    if (!sweptAABB.overlaps(staticAABB)) continue
                }
                if (fixture2.isSensor()) continue
                for (j in 0 until fixtureCount1) {
                    val fixture1 = body1.getFixture(j)
                    if (fixture2.isSensor()) continue
                    val filter1 = fixture1.getFilter()
                    val filter2 = fixture2.getFilter()
                    if (!filter1.isAllowed(filter2)) continue
                    var allow = true
                    for (listener in listeners) {
                        if (!listener!!.collision(body1, fixture1, body2, fixture2)) allow = false
                    }
                    if (!allow) continue
                    val shape1 = fixture1.getShape()
                    val shape2 = fixture2.getShape()
                    if (timeOfImpactDetector.getTimeOfImpact(
                            shape1, transform1, velocity1, angularVelocity1,
                            shape2, transform2, velocity2, angularVelocity2,
                            t1, t2, toi
                        )
                    ) {
                        val impactTime = toi.getTime()
                        if (impactTime == 0.0) return false
                        if (impactTime < t2) {
                            allow = true
                            for (listener in listeners) {
                                if (!listener!!.collision(body1, fixture1, body2, fixture2, toi)) allow = false
                            }
                            if (allow) {
                                t2 = impactTime
                                minToi = toi
                                minBody = body2
                            }
                        }
                    }
                }
            }
        }
        val impact = minToi ?: return false
        val other = minBody ?: return false
        var allow = true
        for (listener in listeners) if (!listener!!.collision(body1, other, impact)) allow = false
        if (!allow) return false
        val impactTime = impact.getTime()
        ToiAcceptedResetTap.listener?.invoke(body1, other, impactTime, other.isDynamic())
        body1.getPreviousTransform().lerp(body1.getTransform(), impactTime, body1.getTransform())
        if (other.isDynamic()) other.getPreviousTransform().lerp(other.getTransform(), impactTime, other.getTransform())
        if (impact.getSeparation().getDistance() <= 0.0) return true
        timeOfImpactSolver.solve(body1, other, impact, settings)
        return true
    }

    private inner class WarmStartHandler : ContactUpdateHandler {
        lateinit var data: ContactCollisionData<T>
        override fun getFriction(fixture1: BodyFixture, fixture2: BodyFixture): Double =
            valueMixer.mixFriction(fixture1.getFriction(), fixture2.getFriction())
        override fun getRestitution(fixture1: BodyFixture, fixture2: BodyFixture): Double =
            valueMixer.mixRestitution(fixture1.getRestitution(), fixture2.getRestitution())
        override fun getRestitutionVelocity(fixture1: BodyFixture, fixture2: BodyFixture): Double =
            valueMixer.mixRestitutionVelocity(fixture1.getRestitutionVelocity(), fixture2.getRestitutionVelocity())
        override fun begin(contact: Contact) {
            val count = contactListeners.size
            for (i in 0 until count) contactListeners[i]!!.begin(data, contact)
        }
        override fun persist(oldContact: Contact, newContact: Contact) {
            val count = contactListeners.size
            for (i in 0 until count) contactListeners[i]!!.persist(data, oldContact, newContact)
        }
        override fun end(contact: Contact) {
            val count = contactListeners.size
            for (i in 0 until count) contactListeners[i]!!.end(data, contact)
        }
    }

    private inner class JointIterator : MutableIterator<Joint<T>> {
        private var index = -1
        private var removed = false
        override fun hasNext(): Boolean = index + 1 < joints.size
        override fun next(): Joint<T> {
            if (index + 1 >= joints.size) throw IndexOutOfBoundsException()
            try {
                index++
                removed = false
                return joints[index]
            } catch (error: IndexOutOfBoundsException) {
                throw ConcurrentModificationException()
            }
        }
        override fun remove() {
            if (index < 0 || removed) throw IllegalStateException()
            if (index >= joints.size) throw IndexOutOfBoundsException()
            try {
                removeJoint(index)
                index--
                removed = true
            } catch (error: IndexOutOfBoundsException) {
                throw ConcurrentModificationException()
            }
        }
    }

}
