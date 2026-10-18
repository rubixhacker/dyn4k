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
package org.dyn4j.coverage.world.core

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertFailsWith
import kotlin.test.assertNotNull
import kotlin.test.assertNotSame
import kotlin.test.assertNull
import kotlin.test.assertSame
import kotlin.test.assertTrue
import org.dyn4j.dynamics.Body
import org.dyn4j.dynamics.BodyFixture
import org.dyn4j.dynamics.Settings
import org.dyn4j.dynamics.TimeStep
import org.dyn4j.dynamics.contact.ContactConstraint
import org.dyn4j.dynamics.contact.Contact
import org.dyn4j.dynamics.contact.SequentialImpulses
import org.dyn4j.dynamics.contact.ForceCollisionTimeOfImpactSolver
import org.dyn4j.dynamics.joint.AngleJoint
import org.dyn4j.dynamics.joint.DistanceJoint
import org.dyn4j.dynamics.joint.Joint
import org.dyn4j.dynamics.joint.PinJoint
import org.dyn4j.dynamics.joint.RevoluteJoint
import org.dyn4j.collision.CollisionItem
import org.dyn4j.collision.CollisionPair
import org.dyn4j.collision.broadphase.CollisionBodyAABBProducer
import org.dyn4j.collision.broadphase.CollisionBodyBroadphaseFilter
import org.dyn4j.collision.broadphase.Sap
import org.dyn4j.collision.broadphase.StaticValueAABBExpansionMethod
import org.dyn4j.geometry.Circle
import org.dyn4j.collision.AxisAlignedBounds
import org.dyn4j.geometry.Geometry
import org.dyn4j.geometry.MassType
import org.dyn4j.geometry.Vector2
import org.dyn4j.geometry.Transform
import org.dyn4j.world.World
import org.dyn4j.world.AbstractPhysicsWorld
import org.dyn4j.world.WorldCollisionData
import org.dyn4j.world.ContactCollisionData
import org.dyn4j.world.ValueMixer
import org.dyn4j.world.listener.DestructionListenerAdapter
import org.dyn4j.world.listener.ContactListenerAdapter
import org.dyn4j.world.listener.StepListenerAdapter
import org.dyn4j.world.listener.TimeOfImpactListenerAdapter
import org.dyn4j.world.PhysicsWorld

private class CorePhysicsWorld(bodyCapacity: Int = 10, jointCapacity: Int = 10) :
    AbstractPhysicsWorld<Body, WorldCollisionData<Body>>(bodyCapacity, jointCapacity) {
    override fun createCollisionData(pair: CollisionPair<CollisionItem<Body, BodyFixture>>) = WorldCollisionData(pair)
    fun scan() = detect()
    fun collisionCount() = collisionData.size
    fun broadphaseContains(body: Body) = broadphaseDetector.contains(body)
    fun broadphaseContains(body: Body, fixture: BodyFixture) = broadphaseDetector.contains(body, fixture)
    fun graphContains(body: Body) = constraintGraph.containsBody(body)
    fun graphSize() = constraintGraph.size()
    fun graphContactCount(body: Body) = constraintGraph.getNode(body)?.getContactConstraints()?.size
    fun graphJointCount(body: Body) = constraintGraph.getNode(body)?.getJoints()?.size
}

private fun pairedWorld(): Triple<World<Body>, Body, Body> {
    val world = World<Body>()
    val first = Body().also { it.addFixture(Circle(1.0)); it.setMass(MassType.NORMAL) }
    val second = Body().also { it.addFixture(Geometry.createEquilateralTriangle(0.5)); it.setMass(MassType.NORMAL) }
    world.addBody(first)
    world.addBody(second)
    return Triple(world, first, second)
}

private fun joinedWorld(): Triple<World<Body>, Body, Body> {
    val (world, first, second) = pairedWorld()
    world.addJoint(AngleJoint(first, second))
    return Triple(world, first, second)
}

private class RemovalEvents {
    var destruction = 0
    var destroyedContact = 0
    var endedContact = 0
    fun install(world: CorePhysicsWorld) {
        world.addDestructionListener(object : DestructionListenerAdapter<Body>() {
            override fun destroyed(joint: Joint<Body>?) { destruction++ }
            override fun destroyed(contactConstraint: ContactConstraint<Body>?) { destruction++ }
            override fun destroyed(body: Body?) { destruction++ }
        })
        world.addContactListener(object : ContactListenerAdapter<Body>() {
            override fun destroyed(collision: ContactCollisionData<Body>?, contact: Contact?) { destroyedContact++ }
            override fun end(collision: ContactCollisionData<Body>?, contact: Contact?) { endedContact++ }
        })
    }
}

private fun removalWorld(): Pair<CorePhysicsWorld, RemovalEvents> {
    val world = CorePhysicsWorld()
    val events = RemovalEvents()
    events.install(world)
    return world to events
}

class PhysicsWorldCoreCoverageTest {
    @Test fun createSuccess() {
        for ((bodies, joints) in listOf(10 to 10, 16 to 2, -16 to 2, 0 to 2, 5 to -2, 5 to 0, -5 to -2, 0 to 0)) {
            val world = CorePhysicsWorld(bodies, joints)
            assertTrue(world.getBodies().isEmpty())
            assertTrue(world.getJoints().isEmpty())
            assertEquals(0, world.graphSize())
            assertNull(world.getBounds())
            assertNull(world.getUserData())
            assertNotNull(world.getBroadphaseDetector())
            assertNotNull(world.getBroadphaseCollisionDataFilter())
            assertNotNull(world.getNarrowphaseDetector())
            assertNotNull(world.getNarrowphasePostProcessor())
            assertNotNull(world.getManifoldSolver())
            assertNotNull(world.getRaycastDetector())
            assertNotNull(world.getTimeOfImpactDetector())
            assertNotNull(world.getContactConstraintSolver())
            assertNotNull(world.getValueMixer())
            assertNotNull(world.getGravity())
            assertNotNull(world.getSettings())
            assertNotNull(world.getTimeStep())
            assertNotNull(world.getTimeOfImpactSolver())
            assertTrue(world.isUpdateRequired())
            assertEquals(0.0, world.getAccumulatedTime())
        }
    }

    @Test fun addBody() {
        val world = CorePhysicsWorld()
        val body = Body().also { it.addFixture(Geometry.createCapsule(1.0, 0.5)) }
        assertFalse(world.graphContains(body))
        world.addBody(body)
        assertTrue(world.graphContains(body))
        assertSame(world, body.getOwner())
        assertTrue(world.containsBody(body))
    }

    @Test fun addJoint() {
        val world = CorePhysicsWorld()
        val first = Body().also(world::addBody)
        val second = Body().also(world::addBody)
        val joint = AngleJoint(first, second)
        assertNull(joint.getOwner())
        assertEquals(0, world.getJointCount())
        assertTrue(world.graphContains(first))
        assertTrue(world.graphContains(second))
        world.addJoint(joint)
        assertEquals(1, world.getJointCount())
        assertSame(world, joint.getOwner())
        assertTrue(world.isJoined(first, second))
        assertFalse(world.isJointCollisionAllowed(first, second))
        assertEquals(listOf(joint), world.getJoints(first))
        assertEquals(listOf(joint), world.getJoints(second))
        assertEquals(1, world.graphJointCount(first))
        assertEquals(1, world.graphJointCount(second))
    }

    @Test fun addNullJoint() = assertFailsWith<NullPointerException> { World<Body>().addJoint(null) }.let { Unit }
    @Test fun addJointFromOtherWorld() {
        val (firstWorld, first, second) = pairedWorld()
        val joint = AngleJoint(first, second)
        firstWorld.addJoint(joint)
        assertFailsWith<IllegalArgumentException> { World<Body>().addJoint(joint) }
        assertSame(firstWorld, joint.getOwner())
    }
    @Test fun addSameJointToSameWorld() {
        val (world, first, second) = pairedWorld()
        val joint = AngleJoint(first, second)
        world.addJoint(joint)
        assertFailsWith<IllegalArgumentException> { world.addJoint(joint) }
        assertEquals(1, world.getJointCount())
    }
    @Test fun addJointWithoutBodies() {
        val joint = AngleJoint(Body(), Body())
        assertFailsWith<IllegalArgumentException> { World<Body>().addJoint(joint) }
    }
    @Test fun getJointsAndAdd() {
        assertFailsWith<UnsupportedOperationException> { (World<Body>().getJoints() as MutableList<Joint<Body>>).add(AngleJoint(Body(), Body())) }
    }
    @Test fun getJointsAndRemove() {
        assertFailsWith<UnsupportedOperationException> { (World<Body>().getJoints() as MutableList<Joint<Body>>).removeAt(0) }
    }
    @Test fun getJointAtIndex() {
        val (world, first, second) = pairedWorld()
        val joint = AngleJoint(first, second)
        world.addJoint(joint)
        assertSame(joint, world.getJoint(0))
    }
    @Test fun getJointAtNegativeIndex() = assertFailsWith<IndexOutOfBoundsException> { World<Body>().getJoint(-1) }.let { Unit }
    @Test fun getJointAtBadIndex() = assertFailsWith<IndexOutOfBoundsException> { World<Body>().getJoint(1) }.let { Unit }
    @Test fun getJointCount() {
        val (world, first, second) = pairedWorld()
        assertEquals(0, world.getJointCount())
        world.addJoint(AngleJoint(first, second))
        assertEquals(1, world.getJointCount())
    }
    @Test fun getJointIterator() {
        val (world, first, second) = pairedWorld()
        val one = AngleJoint(first, second)
        val two = AngleJoint(first, second)
        world.addJoint(one)
        world.addJoint(two)
        assertEquals(listOf(one, two), world.getJointIterator().asSequence().toList())
        val iterator = world.getJointIterator()
        assertSame(one, iterator.next())
        iterator.remove()
        assertEquals(1, world.getJointCount())
        assertSame(two, iterator.next())
        iterator.remove()
        assertEquals(0, world.getJointCount())
    }
    @Test fun getJointIteratorFailure() {
        val (world, first, second) = pairedWorld()
        world.addJoint(AngleJoint(first, second))
        world.addJoint(AngleJoint(first, second))
        val overflow = world.getJointIterator()
        overflow.next()
        overflow.next()
        assertFailsWith<IndexOutOfBoundsException> { overflow.next() }
        val beforeNext = world.getJointIterator()
        assertFailsWith<IllegalStateException> { beforeNext.remove() }
        beforeNext.next()
        beforeNext.remove()
        assertFailsWith<IllegalStateException> { beforeNext.remove() }
        val modified = world.getJointIterator()
        modified.next()
        world.removeAllJoints()
        assertFailsWith<IndexOutOfBoundsException> { modified.remove() }
    }
    @Test fun containsJoint() {
        val (world, first, second) = pairedWorld()
        val joint = AngleJoint(first, second)
        world.addJoint(joint)
        assertTrue(world.containsJoint(joint))
        assertFalse(world.containsJoint(null))
        assertFalse(world.containsJoint(AngleJoint(first, second)))
    }
    @Test fun removeJointNegativeIndex() = assertFailsWith<IndexOutOfBoundsException> { World<Body>().removeJoint(-1) }.let { Unit }
    @Test fun removeJointBadIndex() = assertFailsWith<IndexOutOfBoundsException> { World<Body>().removeJoint(2) }.let { Unit }
    @Test fun removeJoint() {
        val (world, first, second) = pairedWorld()
        assertFalse(world.removeJoint(null as Joint<Body>?))
        val joint = DistanceJoint(first, second, Vector2(), Vector2())
        joint.setCollisionAllowed(true)
        world.addJoint(joint)
        assertTrue(world.removeJoint(joint))
        assertEquals(0, world.getJointCount())
        assertEquals(2, world.getBodyCount())
        assertNull(joint.getOwner())
        assertTrue(world.getJoints(first).isEmpty())
        assertTrue(world.getJoints(second).isEmpty())
    }
    @Test fun removeAllJoints() {
        val (world, first, second) = pairedWorld()
        var destroyed = 0
        world.addDestructionListener(object : DestructionListenerAdapter<Body>() {
            override fun destroyed(joint: Joint<Body>?) { destroyed++ }
        })
        val joint = DistanceJoint(first, second, Vector2(), Vector2())
        world.addJoint(joint)
        world.removeAllJoints()
        assertEquals(0, destroyed)
        assertEquals(0, world.getJointCount())
        assertEquals(2, world.getBodyCount())
        assertNull(joint.getOwner())
        assertTrue(world.getJoints(first).isEmpty())
        world.addJoint(joint)
        world.removeAllJoints(true)
        assertEquals(1, destroyed)
        assertNull(joint.getOwner())
        assertEquals(0, world.getJointCount())
        assertTrue(world.getJoints(second).isEmpty())
    }

    @Test fun fixtureModification() {
        val world = CorePhysicsWorld()
        val first = Body().also { it.addFixture(Circle(1.0)); it.setMass(MassType.NORMAL) }
        val second = Body().also { it.addFixture(Geometry.createEquilateralTriangle(0.5)); it.setMass(MassType.NORMAL) }
        val old = first.getFixture(0)
        val other = second.getFixture(0)
        world.addBody(first)
        world.addBody(second)
        world.scan()
        assertTrue(world.broadphaseContains(first, old))
        assertEquals(1, world.collisionCount())
        assertTrue(assertNotNull(world.getCollisionData(first, old, second, other)).isContactConstraintCollision())
        assertEquals(1, world.getContacts(first).size)
        assertEquals(1, world.graphContactCount(first))
        assertEquals(1, world.graphContactCount(second))
        val added = first.addFixture(Geometry.createEquilateralTriangle(0.5))
        world.scan()
        assertEquals(2, world.collisionCount())
        assertTrue(assertNotNull(world.getCollisionData(first, added, second, other)).isContactConstraintCollision())
        assertEquals(2, world.getContacts(first).size)
        assertEquals(2, world.graphContactCount(first))
        assertEquals(2, world.graphContactCount(second))
        first.removeFixture(old)
        assertFalse(world.broadphaseContains(first, old))
        assertTrue(world.broadphaseContains(first, added))
        assertEquals(1, world.collisionCount())
        assertNull(world.getCollisionData(first, old, second, other))
        assertEquals(1, world.getContacts(first).size)
        assertEquals(1, world.graphContactCount(first))
        assertEquals(1, world.graphContactCount(second))
        first.addFixture(old)
        world.scan()
        assertEquals(2, world.collisionCount())
        assertEquals(2, world.getContacts(second).size)
        assertEquals(2, world.graphContactCount(first))
        assertEquals(2, world.graphContactCount(second))
        first.removeAllFixtures()
        assertEquals(0, world.collisionCount())
        assertNull(world.getCollisionData(first, old, second, other))
        assertNull(world.getCollisionData(first, added, second, other))
        assertTrue(world.getContacts(first).isEmpty())
        assertTrue(world.getContacts(second).isEmpty())
        assertEquals(0, world.graphContactCount(first))
        assertEquals(0, world.graphContactCount(second))
    }

    @Test fun listeners() {
        val world = object : World<Body>() {
            fun listenerBackingSizes() = listOf(
                collisionListeners.size, boundsListeners.size, contactListeners.size,
                stepListeners.size, destructionListeners.size, timeOfImpactListeners.size)
        }
        val contact = ContactListenerAdapter<Body>()
        val step = StepListenerAdapter<Body>()
        val destruction = DestructionListenerAdapter<Body>()
        val toi = TimeOfImpactListenerAdapter<Body>()
        val contactView = world.getContactListeners()
        val stepView = world.getStepListeners()
        val destructionView = world.getDestructionListeners()
        val toiView = world.getTimeOfImpactListeners()
        fun assertSizes(contactCount: Int, stepCount: Int, destructionCount: Int, toiCount: Int) {
            assertEquals(contactCount, contactView.size)
            assertEquals(stepCount, stepView.size)
            assertEquals(destructionCount, destructionView.size)
            assertEquals(toiCount, toiView.size)
        }
        fun assertFreshViews(contactCount: Int, stepCount: Int, destructionCount: Int, toiCount: Int) {
            val currentContact = world.getContactListeners()
            val currentStep = world.getStepListeners()
            val currentDestruction = world.getDestructionListeners()
            val currentToi = world.getTimeOfImpactListeners()
            assertSame(contactView, currentContact)
            assertSame(stepView, currentStep)
            assertSame(destructionView, currentDestruction)
            assertSame(toiView, currentToi)
            assertEquals(contactCount, currentContact.size)
            assertEquals(stepCount, currentStep.size)
            assertEquals(destructionCount, currentDestruction.size)
            assertEquals(toiCount, currentToi.size)
            currentContact.forEach { assertSame(contact, it) }
            currentStep.forEach { assertSame(step, it) }
            currentDestruction.forEach { assertSame(destruction, it) }
            currentToi.forEach { assertSame(toi, it) }
        }
        world.addContactListener(contact)
        world.addStepListener(step)
        world.addDestructionListener(destruction)
        world.addTimeOfImpactListener(toi)
        assertEquals(listOf(0, 0, 1, 1, 1, 1), world.listenerBackingSizes())
        assertTrue(world.getCollisionListeners().isEmpty())
        assertTrue(world.getBoundsListeners().isEmpty())
        assertSizes(1, 1, 1, 1)
        assertFreshViews(1, 1, 1, 1)
        assertSame(contact, contactView[0])
        assertSame(step, stepView[0])
        assertSame(destruction, destructionView[0])
        assertSame(toi, toiView[0])
        world.addContactListener(contact)
        world.addStepListener(step)
        world.addDestructionListener(destruction)
        world.addTimeOfImpactListener(toi)
        assertSizes(2, 2, 2, 2)
        assertFreshViews(2, 2, 2, 2)
        world.removeContactListener(contact)
        assertSizes(1, 2, 2, 2)
        assertFreshViews(1, 2, 2, 2)
        world.removeStepListener(step)
        assertSizes(1, 1, 2, 2)
        assertFreshViews(1, 1, 2, 2)
        world.removeDestructionListener(destruction)
        assertSizes(1, 1, 1, 2)
        assertFreshViews(1, 1, 1, 2)
        world.removeTimeOfImpactListener(toi)
        assertSizes(1, 1, 1, 1)
        assertFreshViews(1, 1, 1, 1)
        world.removeAllContactListeners()
        assertSizes(0, 1, 1, 1)
        assertFreshViews(0, 1, 1, 1)
        world.removeAllStepListeners()
        assertSizes(0, 0, 1, 1)
        assertFreshViews(0, 0, 1, 1)
        world.removeAllDestructionListeners()
        assertSizes(0, 0, 0, 1)
        assertFreshViews(0, 0, 0, 1)
        world.removeAllTimeOfImpactListeners()
        assertSizes(0, 0, 0, 0)
        assertFreshViews(0, 0, 0, 0)
        world.addContactListener(contact)
        world.addStepListener(step)
        world.addDestructionListener(destruction)
        world.addTimeOfImpactListener(toi)
        assertSizes(1, 1, 1, 1)
        assertFreshViews(1, 1, 1, 1)
        world.removeAllListeners()
        assertSizes(0, 0, 0, 0)
        assertFreshViews(0, 0, 0, 0)
    }

    @Test fun savedListenerViewIteratorFailsAfterStructuralMutation() {
        val world = World<Body>()
        val first = StepListenerAdapter<Body>()
        val second = StepListenerAdapter<Body>()
        world.addStepListener(first)
        val view = world.getStepListeners()
        val iterator = view.iterator()
        world.addStepListener(second)
        assertEquals(2, view.size)
        assertFailsWith<ConcurrentModificationException> { iterator.next() }
    }

    @Test fun getSetAccumulatedTime() {
        val world = World<Body>()
        val half = Settings.DEFAULT_STEP_FREQUENCY * 0.5
        assertEquals(0.0, world.getAccumulatedTime())
        world.update(half)
        assertEquals(half, world.getAccumulatedTime())
        world.update(half)
        assertEquals(0.0, world.getAccumulatedTime())
        world.setAccumulatedTime(half)
        assertEquals(half, world.getAccumulatedTime())
        world.setAccumulatedTime(0.0)
        assertEquals(0.0, world.getAccumulatedTime())
        world.setAccumulatedTime(half)
        world.setAccumulatedTime(-10.0)
        assertEquals(half, world.getAccumulatedTime())
    }

    @Test fun getSetValueMixer() {
        val world = World<Body>()
        assertSame(ValueMixer.DEFAULT_MIXER, world.getValueMixer())
        val mixer = object : ValueMixer {
            override fun mixFriction(friction1: Double, friction2: Double) = (friction1 + friction2) * 0.5
            override fun mixRestitution(restitution1: Double, restitution2: Double) = (restitution1 + restitution2) * 0.5
            override fun mixRestitutionVelocity(restitutionVelocity1: Double, restitutionVelocity2: Double) = 0.0
        }
        world.setValueMixer(mixer)
        assertSame(mixer, world.getValueMixer())
    }
    @Test fun setNullVaueMixer() = assertFailsWith<NullPointerException> { World<Body>().setValueMixer(null) }.let { Unit }
    @Test fun getSetContactConstraintSolver() {
        val world = World<Body>()
        val solver = object : SequentialImpulses<Body>() {}
        world.setContactConstraintSolver(solver)
        assertSame(solver, world.getContactConstraintSolver())
    }
    @Test fun setNullContactConstraintSolver() = assertFailsWith<NullPointerException> { World<Body>().setContactConstraintSolver(null) }.let { Unit }
    @Test fun getSetGravity() {
        val world = World<Body>()
        assertEquals(0.0, world.getGravity().x)
        assertEquals(-9.8, world.getGravity().y)
        val gravity = Vector2(0.0, -10.0)
        world.setGravity(gravity)
        assertEquals(gravity, world.getGravity())
    }
    @Test fun setNullGravity() {
        val world = World<Body>()
        world.setGravity(0.0, -4.0)
        world.setGravity(null)
        assertEquals(0.0, world.getGravity().x)
        assertEquals(-4.0, world.getGravity().y)
    }
    @Test fun setNullCCDBroadphaseDetector() =
        assertFailsWith<NullPointerException> { World<Body>().setContinuousCollisionDetectionBroadphaseDetector(null) }.let { Unit }
    @Test fun getAndSetCCDBroadphaseDetector() {
        val world = World<Body>()
        val body = Body().also { it.addFixture(Circle(1.0)) }
        world.addBody(body)
        val original = world.getContinuousCollisionDetectionBroadphaseDetector()
        val replacement = Sap(
            CollisionBodyBroadphaseFilter<Body>(),
            CollisionBodyAABBProducer<Body>(),
            StaticValueAABBExpansionMethod<Body>(0.2)
        )
        world.setContinuousCollisionDetectionBroadphaseDetector(replacement)
        assertSame(replacement, world.getContinuousCollisionDetectionBroadphaseDetector())
        assertNotSame(original, replacement)
        assertTrue(replacement.contains(body))
    }

    @Test fun isJoined() {
        val world = World<Body>()
        val bodies = List(3) { Body().also(world::addBody) }
        assertFalse(world.isJoined(bodies[0], null))
        assertFalse(world.isJoined(bodies[0], bodies[1]))
        world.addJoint(DistanceJoint(bodies[0], bodies[1], Vector2(), Vector2()))
        assertFalse(world.isJoined(bodies[0], bodies[2]))
        assertTrue(world.isJoined(bodies[0], bodies[1]))
    }
    @Test fun isJointCollisionAllowed() {
        val (world, first, second) = pairedWorld()
        val revolute = RevoluteJoint(first, second, Vector2())
        val angle = AngleJoint(first, second)
        world.addJoint(revolute)
        world.addJoint(angle)
        assertFalse(world.isJointCollisionAllowed(first, second))
        angle.setCollisionAllowed(true)
        assertTrue(world.isJointCollisionAllowed(first, second))
    }
    @Test fun getJoinedBodies() {
        val (world, first, second) = pairedWorld()
        assertTrue(world.getJoinedBodies(first).isEmpty())
        world.addJoint(DistanceJoint(first, second, Vector2(), Vector2()))
        assertEquals(listOf(second), world.getJoinedBodies(first))
    }
    @Test fun getJointsForBody() {
        val (world, first, second) = pairedWorld()
        assertTrue(world.getJoints(first).isEmpty())
        val joint = DistanceJoint(first, second, Vector2(), Vector2())
        world.addJoint(joint)
        assertEquals(listOf(joint), world.getJoints(first))
    }
    @Test fun getInContactBodies() {
        val (world, first, second) = pairedWorld()
        assertTrue(world.getInContactBodies(first, false).isEmpty())
        assertTrue(world.getInContactBodies(first, true).isEmpty())
        world.step(1)
        assertEquals(listOf(second), world.getInContactBodies(first, false))
        first.getFixture(0).setSensor(true)
        world.step(1)
        assertTrue(world.getInContactBodies(first, false).isEmpty())
        assertEquals(listOf(second), world.getInContactBodies(first, true))
    }
    @Test fun getContacts() {
        val (world, first, _) = pairedWorld()
        assertTrue(world.getContacts(first).isEmpty())
        world.step(1)
        assertTrue(world.getContacts(first).isNotEmpty())
    }
    @Test fun isInContact() {
        val (world, first, second) = pairedWorld()
        assertFalse(world.isInContact(first, second))
        world.step(1)
        assertTrue(world.isInContact(first, second))
    }
    @Test fun getJoinedBodiesMulti() {
        val (world, first, second) = pairedWorld()
        world.addJoint(AngleJoint(first, second))
        world.addJoint(AngleJoint(first, second))
        assertEquals(listOf(second), world.getJoinedBodies(first))
    }
    @Test fun getInContactBodiesMulti() {
        val world = World<Body>()
        val first = Body().also { it.addFixture(Geometry.createRectangle(15.0, 1.0)); it.setMass(MassType.NORMAL) }
        val second = Body().also {
            it.addFixture(Geometry.createSquare(1.0))
            it.addFixture(Geometry.createSquare(1.0).also { shape -> shape.translate(-0.5, 0.0) })
            it.setMass(MassType.NORMAL)
            it.translate(0.0, 0.75)
        }
        world.addBody(first)
        world.addBody(second)
        world.step(1)
        assertEquals(listOf(second), world.getInContactBodies(first, false))
    }

    @Test fun setSettings() {
        val world = World<Body>()
        val settings = Settings()
        settings.setLinearTolerance(10000.0)
        world.setSettings(settings)
        assertNotSame(settings, world.getSettings())
        assertEquals(10000.0, world.getSettings().getLinearTolerance())
    }
    @Test fun setNullSettings() {
        val world = World<Body>()
        world.getSettings().setAngularTolerance(4.0)
        world.setSettings(null)
        assertEquals(4.0, world.getSettings().getAngularTolerance())
    }
    @Test fun getSetTimeOfImpactSolver() {
        val world = World<Body>()
        val solver = ForceCollisionTimeOfImpactSolver<Body>()
        world.setTimeOfImpactSolver(solver)
        assertSame(solver, world.getTimeOfImpactSolver())
    }
    @Test fun setNullTimeOfImpactSolver() =
        assertFailsWith<NullPointerException> { World<Body>().setTimeOfImpactSolver(null) }.let { Unit }
    @Test fun getTimeStep() {
        val world = World<Body>()
        val step = world.getTimeStep()
        assertEquals(Settings.DEFAULT_STEP_FREQUENCY, step.getDeltaTime())
        world.step(1)
        assertSame(step, world.getTimeStep())
        assertEquals(Settings.DEFAULT_STEP_FREQUENCY, step.getDeltaTime())
    }
    @Test fun isEmpty() {
        val world = World<Body>()
        assertTrue(world.isEmpty())
        val first = Body()
        val second = Body()
        val joint = DistanceJoint(first, second, Vector2(), Vector2())
        world.addBody(first)
        assertFalse(world.isEmpty())
        world.removeAllBodiesAndJoints()
        assertTrue(world.isEmpty())
        world.addBody(first)
        world.addBody(second)
        assertFalse(world.isEmpty())
        world.addJoint(joint)
        assertFalse(world.isEmpty())
    }
    @Test fun getSetUpdateRequired() {
        val world = World<Body>()
        assertTrue(world.isUpdateRequired())
        world.step(1)
        assertFalse(world.isUpdateRequired())
        world.setUpdateRequired(true)
        assertTrue(world.isUpdateRequired())
    }
    @Test fun shift() {
        val (world, first, _) = pairedWorld()
        world.setBounds(AxisAlignedBounds(20.0, 20.0))
        val joint = PinJoint(first, Vector2())
        world.addJoint(joint)
        world.shift(Vector2(5.0, 6.0))
        assertEquals(5.0, joint.getAnchor().x)
        assertEquals(6.0, joint.getAnchor().y)
    }
    @Test fun update() {
        val world = World<Body>()
        val frequency = Settings.DEFAULT_STEP_FREQUENCY
        assertTrue(world.update(frequency))
        assertTrue(world.update(frequency * 2.5, 10))
        assertEquals(frequency * 0.5, world.getAccumulatedTime(), 1.0e-8)
        assertFalse(world.update(-2.0))
        assertFalse(world.update(0.0))
        world.setAccumulatedTime(0.0)
        assertTrue(world.update(0.02, 0.01))
        assertEquals(0.02 - frequency, world.getAccumulatedTime())
        world.setAccumulatedTime(0.0)
        assertTrue(world.update(frequency * 4, 0.01, 5))
        assertEquals(0.0, world.getAccumulatedTime(), 1.0e-8)
    }
    @Test fun updatev() {
        val world = World<Body>()
        var steps = 0
        world.addStepListener(object : StepListenerAdapter<Body>() {
            override fun end(step: TimeStep?, world: PhysicsWorld<Body, *>?) { steps++ }
        })
        world.updatev(3.0)
        assertEquals(1, steps)
        world.updatev(0.0)
        world.updatev(-1.0)
        assertEquals(1, steps)
    }
    @Test fun stepInt() {
        val world = World<Body>()
        var steps = 0
        world.addStepListener(object : StepListenerAdapter<Body>() {
            override fun end(step: TimeStep?, world: PhysicsWorld<Body, *>?) { steps++ }
        })
        world.step(3)
        assertEquals(3, steps)
        world.step(0)
        world.step(-2)
        assertEquals(3, steps)
    }
    @Test fun stepIntElapsed() {
        val world = World<Body>()
        var steps = 0
        world.addStepListener(object : StepListenerAdapter<Body>() {
            override fun end(step: TimeStep?, world: PhysicsWorld<Body, *>?) { steps++ }
        })
        world.step(3, 1.0 / 50.0)
        assertEquals(3, steps)
        world.step(0, 1.0 / 50.0)
        world.step(-2, 1.0 / 50.0)
        world.step(1, 0.0)
        world.step(1, -1.0)
        assertEquals(3, steps)
    }

    @Test fun removeBody() {
        val (world, events) = removalWorld()
        assertFalse(world.removeBody(null as Body?))
        assertFalse(world.removeBody(Body()))
        val first = Body().also { it.addFixture(Circle(1.0)); it.setMass(MassType.NORMAL) }
        val second = Body().also { it.addFixture(Geometry.createEquilateralTriangle(0.5)); it.setMass(MassType.NORMAL) }
        world.addBody(first)
        world.addBody(second)
        assertTrue(world.removeBody(first, true))
        assertNull(first.getOwner())
        assertNull(first.getFixtureModificationHandler())
        assertEquals(1, world.getBodyCount())
        world.addBody(first)
        assertSame(world, first.getOwner())
        assertNotNull(first.getFixtureModificationHandler())
        val joint = DistanceJoint(first, second, Vector2(), Vector2())
        joint.setCollisionAllowed(true)
        world.addJoint(joint)
        world.step(1)
        assertEquals(1, world.collisionCount())
        assertTrue(world.removeBody(second, true))
        assertNull(second.getOwner())
        assertNull(second.getFixtureModificationHandler())
        assertEquals(0, world.getJointCount())
        assertSame(first, world.getBody(0))
        assertEquals(1, events.destroyedContact)
        assertEquals(2, events.destruction)
        assertTrue(world.getContacts(first).isEmpty())
        assertTrue(world.getJoints(first).isEmpty())
        assertEquals(0, world.graphContactCount(first))
        assertEquals(0, world.graphJointCount(first))
        assertFalse(world.graphContains(second))
        assertEquals(0, world.collisionCount())
        world.addBody(second)
        world.addJoint(joint)
        world.step(1)
        events.destruction = 0
        assertEquals(1, world.collisionCount())
        assertTrue(world.removeBody(second, false))
        assertEquals(0, events.destruction)
        assertNull(second.getOwner())
        assertNull(joint.getOwner())
        assertTrue(world.getContacts(first).isEmpty())
        assertTrue(world.getJoints(first).isEmpty())
        assertEquals(0, world.graphContactCount(first))
        assertEquals(0, world.graphJointCount(first))
        assertFalse(world.graphContains(second))
        assertEquals(0, world.collisionCount())
    }

    @Test fun removeBodyAtIndex() {
        val (world, events) = removalWorld()
        val first = Body().also { it.addFixture(Circle(1.0)); it.setMass(MassType.NORMAL) }
        val second = Body().also { it.addFixture(Geometry.createEquilateralTriangle(0.5)); it.setMass(MassType.NORMAL) }
        world.addBody(first)
        world.addBody(second)
        assertTrue(world.removeBody(0))
        assertNull(first.getOwner())
        assertEquals(1, world.getBodyCount())
        world.addBody(first)
        val joint = DistanceJoint(first, second, Vector2(), Vector2())
        joint.setCollisionAllowed(true)
        world.addJoint(joint)
        world.step(1)
        assertEquals(1, world.collisionCount())
        assertTrue(world.removeBody(0, true))
        assertNull(second.getOwner())
        assertEquals(0, world.getJointCount())
        assertSame(first, world.getBody(0))
        assertEquals(2, events.destruction)
        assertEquals(0, world.collisionCount())
        assertTrue(world.getContacts(first).isEmpty())
        assertEquals(0, world.graphContactCount(first))
        assertEquals(0, world.graphJointCount(first))
        assertFalse(world.graphContains(second))
        world.addBody(second)
        world.addJoint(joint)
        world.step(1)
        events.destruction = 0
        assertTrue(world.removeBody(1, false))
        assertNull(second.getOwner())
        assertEquals(0, events.destruction)
        assertEquals(0, world.getJointCount())
        assertEquals(0, world.collisionCount())
        assertEquals(0, world.graphContactCount(first))
        assertEquals(0, world.graphJointCount(first))
        assertFalse(world.graphContains(second))
    }

    @Test fun removeBodyMemoryLeak() {
        val (world, events) = removalWorld()
        val first = Body().also { it.addFixture(Geometry.createSquare(1.0)); it.setMass(MassType.NORMAL); it.translate(0.5, 1.1) }
        val second = Body().also { it.addFixture(Geometry.createSquare(1.0)); it.setMass(MassType.NORMAL) }
        world.addBody(first)
        world.addBody(second)
        assertTrue(world.removeBody(first, true))
        assertEquals(1, world.getBodyCount())
        assertNull(first.getOwner())
        assertNull(first.getFixtureModificationHandler())
        assertFalse(world.broadphaseContains(first))
        world.addBody(first)
        assertNotNull(first.getOwner())
        assertNotNull(first.getFixtureModificationHandler())
        assertTrue(world.broadphaseContains(first))
        val joint = DistanceJoint(first, second, Vector2(), Vector2())
        joint.setCollisionAllowed(true)
        world.addJoint(joint)
        world.step(1)
        assertEquals(1, world.collisionCount())
        assertTrue(world.removeBody(second, true))
        assertNull(second.getOwner())
        assertNull(second.getFixtureModificationHandler())
        assertFalse(world.broadphaseContains(second))
        assertEquals(0, world.getJointCount())
        assertEquals(1, world.getBodyCount())
        assertSame(first, world.getBody(0))
        assertTrue(world.graphContains(first))
        assertEquals(0, world.graphContactCount(first))
        assertEquals(0, world.graphJointCount(first))
        assertFalse(world.graphContains(second))
        assertEquals(1, events.destruction)
        assertEquals(1, world.collisionCount())
        world.step(1)
        assertEquals(0, world.collisionCount())
    }

    @Test fun removeAll() {
        val (world, events) = removalWorld()
        val first = Body().also { it.addFixture(Circle(1.0)); it.setMass(MassType.NORMAL) }
        val second = Body().also { it.addFixture(Geometry.createEquilateralTriangle(0.5)); it.setMass(MassType.NORMAL) }
        world.addBody(first)
        world.addBody(second)
        val joint = DistanceJoint(first, second, Vector2(), Vector2())
        joint.setCollisionAllowed(true)
        world.addJoint(joint)
        world.step(1)
        world.removeAllBodiesAndJoints(true)
        assertEquals(0, world.getBodyCount())
        assertEquals(0, world.getJointCount())
        assertEquals(0, world.collisionCount())
        assertEquals(0, world.graphSize())
        assertNull(first.getOwner())
        assertNull(second.getOwner())
        assertNull(joint.getOwner())
        assertEquals(4, events.destruction)
    }

    @Test fun removeAllBodies() {
        val (world, events) = removalWorld()
        val first = Body().also { it.addFixture(Circle(1.0)); it.setMass(MassType.NORMAL) }
        val second = Body().also { it.addFixture(Geometry.createEquilateralTriangle(0.5)); it.setMass(MassType.NORMAL) }
        world.addBody(first)
        world.addBody(second)
        val joint = DistanceJoint(first, second, Vector2(), Vector2())
        joint.setCollisionAllowed(true)
        world.addJoint(joint)
        world.step(1)
        world.removeAllBodies(true)
        assertEquals(0, world.getBodyCount())
        assertEquals(0, world.getJointCount())
        assertEquals(0, world.collisionCount())
        assertEquals(0, world.graphSize())
        assertEquals(4, events.destruction)
        assertEquals(1, events.destroyedContact)
        assertEquals(0, events.endedContact)
        events.destruction = 0
        events.destroyedContact = 0
        world.addBody(first)
        world.addBody(second)
        world.addJoint(joint)
        world.step(1)
        world.removeAllBodies()
        assertEquals(0, world.getBodyCount())
        assertEquals(0, world.getJointCount())
        assertEquals(0, world.collisionCount())
        assertEquals(0, world.graphSize())
        assertEquals(0, events.destruction)
        assertEquals(0, events.destroyedContact)
    }

    @Test fun removeBodyIllegalStateException() {
        val world = World<Body>()
        val first = Body().also { it.addFixture(Circle(1.0)); it.setMass(MassType.NORMAL) }
        val second = Body().also { it.addFixture(Circle(1.0)); it.setMass(MassType.NORMAL) }
        world.addBody(first)
        world.addBody(second)
        world.step(1)
        assertTrue(world.removeBody(second))
        world.getContinuousCollisionDetectionBroadphaseDetector().setUpdated(first)
        val moved = Transform().also { it.translate(10.0, 10.0) }
        second.setTransform(moved)
        second.getPreviousTransform().set(second.getTransform())
        world.step(1)
        assertEquals(1, world.getBodyCount())
        assertSame(first, world.getBody(0))
    }

    @Test fun disabledAndSensor() {
        val world = World<Body>()
        world.setGravity(0.0, 0.0)
        val first = Body().also { it.addFixture(Geometry.createUnitCirclePolygon(6, 0.7)); it.setMass(MassType.NORMAL) }
        val second = Body().also {
            it.addFixture(Geometry.createEquilateralTriangle(1.0)).setSensor(true)
            it.setMass(MassType.NORMAL)
        }
        val third = Body().also { it.addFixture(Circle(1.0)); it.setMass(MassType.NORMAL) }
        val fourth = Body().also { it.addFixture(Geometry.createSquare(1.2)); it.setMass(MassType.NORMAL) }
        listOf(first, second, third, fourth).forEach(world::addBody)
        world.addContactListener(object : ContactListenerAdapter<Body>() {
            override fun begin(collision: ContactCollisionData<Body>?, contact: Contact?) {
                val bodies = setOf(collision!!.getBody1(), collision.getBody2())
                if (bodies == setOf(first, second)) collision.getContactConstraint().setEnabled(false)
            }
        })
        var initialized = 0
        world.setContactConstraintSolver(object : SequentialImpulses<Body>() {
            override fun initialize(contactConstraints: List<ContactConstraint<Body>>, step: TimeStep, settings: Settings) {
                initialized++
                assertTrue(contactConstraints.all { it.isEnabled() && !it.isSensor() })
                super.initialize(contactConstraints, step, settings)
            }
        })
        world.step(1)
        assertTrue(initialized > 0)
    }

    @Test fun sensorRemovalShouldNotClearAtRestState() {
        val world = World<Body>()
        world.setGravity(0.0, 0.0)
        val sensorBody = Body().also { it.addFixture(Circle(1.0)); it.getFixture(0).setSensor(true); it.translate(-0.5, 0.0) }
        val fixture = sensorBody.getFixture(0)
        val movingBody = Body().also { it.addFixture(Circle(1.0)); it.translate(0.4, 0.0); it.setMass(MassType.NORMAL) }
        world.addBody(sensorBody)
        world.addBody(movingBody)
        world.step(10)
        movingBody.setAtRest(true)
        assertTrue(movingBody.isAtRest())
        sensorBody.removeFixture(fixture)
        assertTrue(movingBody.isAtRest())
        sensorBody.addFixture(fixture)
        world.step(1)
        movingBody.setAtRest(true)
        sensorBody.removeAllFixtures()
        assertTrue(movingBody.isAtRest())
        fixture.setSensor(false)
        sensorBody.addFixture(fixture)
        world.addContactListener(object : ContactListenerAdapter<Body>() {
            override fun collision(collision: ContactCollisionData<Body>?) {
                collision!!.getContactConstraint().setEnabled(false)
            }
        })
        world.step(1)
        movingBody.setAtRest(true)
        sensorBody.removeFixture(fixture)
        assertTrue(movingBody.isAtRest())
    }

    @Test fun solvedFlag() {
        val world = World<Body>()
        world.setGravity(0.0, 0.0)
        val first = Body().also { it.addFixture(Geometry.createSquare(0.5)); it.setMass(MassType.NORMAL); it.translate(0.450, 0.499) }
        val second = Body().also { it.addFixture(Geometry.createSquare(0.5)); it.setMass(MassType.NORMAL) }
        val fixture1 = first.getFixture(0)
        val fixture2 = second.getFixture(0)
        fixture1.setRestitution(0.1)
        fixture2.setRestitution(0.1)
        world.addBody(first)
        world.addBody(second)
        fixture1.setSensor(true)
        world.step(1)
        val constraint = world.getContacts(first)[0]
        assertEquals(2, constraint.getContacts().size)
        assertTrue(constraint.getContacts().all { !it.isSolved() })
        fixture1.setSensor(false)
        constraint.setEnabled(false)
        world.step(1)
        assertEquals(2, constraint.getContacts().size)
        assertTrue(constraint.getContacts().all { !it.isSolved() })
        constraint.setEnabled(true)
        world.step(1)
        assertEquals(2, constraint.getContacts().size)
        assertTrue(constraint.getContacts().all { it.isSolved() })
    }
}
