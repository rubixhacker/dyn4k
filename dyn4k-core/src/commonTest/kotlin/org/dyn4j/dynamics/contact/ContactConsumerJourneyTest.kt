package org.dyn4j.dynamics.contact

import de.infix.testBalloon.framework.core.testSuite
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertSame
import kotlin.test.assertTrue
import org.dyn4j.collision.BasicCollisionItem
import org.dyn4j.collision.BasicCollisionPair
import org.dyn4j.collision.CollisionItem
import org.dyn4j.collision.manifold.Manifold
import org.dyn4j.collision.manifold.ManifoldPoint
import org.dyn4j.collision.manifold.ManifoldPointId
import org.dyn4j.collision.continuous.TimeOfImpact
import org.dyn4j.collision.narrowphase.Separation
import org.dyn4j.dynamics.Body
import org.dyn4j.dynamics.BodyFixture
import org.dyn4j.dynamics.Settings
import org.dyn4j.dynamics.TimeStep
import org.dyn4j.geometry.Circle
import org.dyn4j.geometry.MassType
import org.dyn4j.geometry.Vector2

val ContactConsumerJourneyTest by testSuite {
    test("subclassedSolverReceivesWarmStartDispatch") { ContactConsumerJourneyTestFixture().run { subclassedSolverReceivesWarmStartDispatch() } }
    test("twoBodiesExchangeAnImpulseThroughThePublicSolver") { ContactConsumerJourneyTestFixture().run { twoBodiesExchangeAnImpulseThroughThePublicSolver() } }
    test("callbackCanChangeConstraintStateBeforeUpdateReturns") { ContactConsumerJourneyTestFixture().run { callbackCanChangeConstraintStateBeforeUpdateReturns() } }
    test("timeOfImpactSolverMovesOnlyTheFiniteMassBody") { ContactConsumerJourneyTestFixture().run { timeOfImpactSolverMovesOnlyTheFiniteMassBody() } }
    test("pairLookupUsesBodyIdentityEvenWhenEqualityIsOverridden") { ContactConsumerJourneyTestFixture().run { pairLookupUsesBodyIdentityEvenWhenEqualityIsOverridden() } }
}

private class ContactConsumerJourneyTestFixture  {
fun subclassedSolverReceivesWarmStartDispatch() {
        val solver = object : SequentialImpulses<Body>() {
            var calls = 0

            override fun warmStart(contactConstraints: List<ContactConstraint<Body>>, step: TimeStep, settings: Settings) {
                calls++
                super.warmStart(contactConstraints, step, settings)
            }
        }
        val seam: ContactConstraintSolver<Body> = solver
        seam.initialize(emptyList(), TimeStep(1.0 / 60.0), Settings())
        assertEquals(1, solver.calls)
    }

fun twoBodiesExchangeAnImpulseThroughThePublicSolver() {
        val first = Body()
        val second = Body()
        val fixture1 = first.addFixture(Circle(0.5))
        val fixture2 = second.addFixture(Circle(0.5))
        first.setMass(MassType.NORMAL)
        second.setMass(MassType.NORMAL)
        first.setLinearVelocity(1.0, 0.0)
        second.translate(0.9, 0.0)
        val pair = BasicCollisionPair<CollisionItem<Body, BodyFixture>>(
            BasicCollisionItem(first, fixture1), BasicCollisionItem(second, fixture2))
        val constraint = ContactConstraint(pair)
        val manifold = Manifold()
        manifold.setNormal(Vector2(-1.0, 0.0))
        manifold.getPoints().add(ManifoldPoint(ManifoldPointId.DISTANCE).also {
            it.setPoint(Vector2(0.45, 0.0))
            it.setDepth(0.1)
        })
        constraint.update(manifold, Settings(), object : ContactUpdateHandler {
            override fun getFriction(fixture1: BodyFixture, fixture2: BodyFixture) = 0.0
            override fun getRestitution(fixture1: BodyFixture, fixture2: BodyFixture) = 0.0
            override fun getRestitutionVelocity(fixture1: BodyFixture, fixture2: BodyFixture) = 1.0
            override fun begin(contact: Contact) {}
            override fun persist(oldContact: Contact, newContact: Contact) {}
            override fun end(contact: Contact) {}
        })
        val solver = SequentialImpulses<Body>()
        val constraints = listOf(constraint)
        val step = TimeStep(1.0 / 60.0)
        val settings = Settings()
        solver.initialize(constraints, step, settings)
        solver.solveVelocityContraints(constraints, step, settings)
        assertTrue(first.getLinearVelocity().x < 1.0)
        assertTrue(second.getLinearVelocity().x > 0.0)
        assertEquals(true, constraint.getContacts().single().isSolved())
    }

fun callbackCanChangeConstraintStateBeforeUpdateReturns() {
        val first = Body()
        val second = Body()
        val fixture1 = first.addFixture(Circle(0.5))
        val fixture2 = second.addFixture(Circle(0.5))
        val pair = BasicCollisionPair<CollisionItem<Body, BodyFixture>>(
            BasicCollisionItem(first, fixture1), BasicCollisionItem(second, fixture2))
        val constraint = ContactConstraint(pair)
        val liveContacts = constraint.getContacts()
        val manifold = Manifold()
        manifold.setNormal(Vector2(1.0, 0.0))
        manifold.getPoints().add(ManifoldPoint(ManifoldPointId.DISTANCE).also {
            it.setPoint(Vector2(0.25, 0.0))
            it.setDepth(0.1)
        })
        val callbacks = ArrayList<String>()
        val handler = object : ContactUpdateHandler {
            override fun getFriction(fixture1: BodyFixture, fixture2: BodyFixture) = 0.5
            override fun getRestitution(fixture1: BodyFixture, fixture2: BodyFixture) = 0.0
            override fun getRestitutionVelocity(fixture1: BodyFixture, fixture2: BodyFixture) = 1.0
            override fun begin(contact: Contact) {
                callbacks.add("begin")
                assertTrue(liveContacts.isEmpty())
                constraint.setTangentSpeed(2.0)
                constraint.setEnabled(false)
            }
            override fun persist(oldContact: Contact, newContact: Contact) {
                callbacks.add("persist")
                assertSame(oldContact, liveContacts.single())
            }
            override fun end(contact: Contact) { callbacks.add("end") }
        }
        constraint.update(manifold, Settings(), handler)
        assertEquals(listOf("begin"), callbacks)
        assertEquals(2.0, constraint.getTangentSpeed())
        assertFalse(constraint.isEnabled())
        assertEquals(1, liveContacts.size)
        constraint.update(manifold, Settings(), handler)
        assertEquals(listOf("begin", "persist"), callbacks)
        manifold.clear()
        constraint.update(manifold, Settings(), handler)
        assertEquals(listOf("begin", "persist", "end"), callbacks)
        assertTrue(liveContacts.isEmpty())
    }

fun timeOfImpactSolverMovesOnlyTheFiniteMassBody() {
        val first = Body()
        val second = Body()
        first.addFixture(Circle(1.0))
        second.addFixture(Circle(1.0))
        first.setMass(MassType.NORMAL)
        second.setMass(MassType.INFINITE)
        second.translate(2.5, 0.0)
        val separation = Separation()
        separation.setDistance(0.5)
        separation.setNormal(Vector2(1.0, 0.0))
        val toi = TimeOfImpact()
        toi.setSeparation(separation)
        ForceCollisionTimeOfImpactSolver<Body>().solve(first, second, toi, Settings())
        assertEquals(0.2, first.getTransform().getTranslationX())
        assertEquals(2.5, second.getTransform().getTranslationX())
    }

fun pairLookupUsesBodyIdentityEvenWhenEqualityIsOverridden() {
        val first = object : Body() {
            override fun equals(other: Any?) = other is Body
            override fun hashCode() = 1
        }
        val second = Body()
        val fixture1 = first.addFixture(Circle(0.5))
        val fixture2 = second.addFixture(Circle(0.5))
        val pair = BasicCollisionPair<CollisionItem<Body, BodyFixture>>(
            BasicCollisionItem(first, fixture1), BasicCollisionItem(second, fixture2))
        val constraint = ContactConstraint(pair)
        val stranger = object : Body() {
            override fun equals(other: Any?) = other is Body
            override fun hashCode() = 1
        }
        assertEquals(null, constraint.getBody(stranger))
        assertEquals(null, constraint.getFixture(stranger))
        assertEquals(null, constraint.getOtherBody(stranger))
        assertEquals(null, constraint.getOtherFixture(stranger))
        assertSame(first, constraint.getBody(first))
    }
}
