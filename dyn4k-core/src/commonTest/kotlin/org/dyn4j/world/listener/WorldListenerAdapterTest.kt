package org.dyn4j.world.listener

import de.infix.testBalloon.framework.core.testSuite
import kotlin.test.assertTrue
import org.dyn4j.collision.continuous.TimeOfImpact
import org.dyn4j.dynamics.Body
import org.dyn4j.dynamics.BodyFixture
import org.dyn4j.dynamics.TimeStep
import org.dyn4j.dynamics.contact.Contact
import org.dyn4j.dynamics.contact.ContactConstraint
import org.dyn4j.dynamics.contact.SolvedContact
import org.dyn4j.dynamics.joint.Joint
import org.dyn4j.world.BroadphaseCollisionData
import org.dyn4j.world.ContactCollisionData
import org.dyn4j.world.ManifoldCollisionData
import org.dyn4j.world.NarrowphaseCollisionData
import org.dyn4j.world.PhysicsWorld

val WorldListenerAdapterTest by testSuite {
    test("collisionAndTimeOfImpactAdaptersAllowEveryStage") { WorldListenerAdapterTestFixture().run { collisionAndTimeOfImpactAdaptersAllowEveryStage() } }
    test("notificationAdaptersAcceptMissingCallbackData") { WorldListenerAdapterTestFixture().run { notificationAdaptersAcceptMissingCallbackData() } }
}

private class WorldListenerAdapterTestFixture  {
fun collisionAndTimeOfImpactAdaptersAllowEveryStage() {
        val collisions = CollisionListenerAdapter<Body, BodyFixture>()
        val broadphase: BroadphaseCollisionData<Body, BodyFixture>? = null
        val narrowphase: NarrowphaseCollisionData<Body, BodyFixture>? = null
        val manifold: ManifoldCollisionData<Body, BodyFixture>? = null
        assertTrue(collisions.collision(broadphase))
        assertTrue(collisions.collision(narrowphase))
        assertTrue(collisions.collision(manifold))

        val toiListener = TimeOfImpactListenerAdapter<Body>()
        val body = Body()
        val toi = TimeOfImpact()
        assertTrue(toiListener.collision(null, null))
        assertTrue(toiListener.collision(body, body, toi))
        assertTrue(toiListener.collision(null, null, null, null))
        assertTrue(toiListener.collision(body, null, body, null, toi))
    }

fun notificationAdaptersAcceptMissingCallbackData() {
        BoundsListenerAdapter<Body, BodyFixture>().outside(null)
        val contacts = ContactListenerAdapter<Body>()
        val collision: ContactCollisionData<Body>? = null
        val contact: Contact? = null
        val solved: SolvedContact? = null
        contacts.begin(collision, contact)
        contacts.persist(collision, contact, contact)
        contacts.end(collision, contact)
        contacts.destroyed(collision, contact)
        contacts.collision(collision)
        contacts.preSolve(collision, contact)
        contacts.postSolve(collision, solved)

        val destruction = DestructionListenerAdapter<Body>()
        val joint: Joint<Body>? = null
        val constraint: ContactConstraint<Body>? = null
        destruction.destroyed(joint)
        destruction.destroyed(constraint)
        destruction.destroyed(null as Body?)

        val steps = StepListenerAdapter<Body>()
        val step: TimeStep? = null
        val world: PhysicsWorld<Body, *>? = null
        steps.begin(step, world)
        steps.updatePerformed(step, world)
        steps.postSolve(step, world)
        steps.end(step, world)
    }
}
