package org.dyn4j.world

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertSame
import kotlin.test.assertTrue
import org.dyn4j.collision.BasicCollisionItem
import org.dyn4j.collision.BasicCollisionPair
import org.dyn4j.collision.CollisionItem
import org.dyn4j.dynamics.Body
import org.dyn4j.dynamics.BodyFixture
import org.dyn4j.dynamics.contact.ContactConstraint
import org.dyn4j.geometry.Circle

class GraphContactJourneyTest {
    @Test
    fun contactViewsTrackEdgesAndBodyRemoval() {
        val body1 = Body()
        val fixture1 = body1.addFixture(Circle(0.5))
        val body2 = Body()
        val fixture2 = body2.addFixture(Circle(0.5))
        val item1: CollisionItem<Body, BodyFixture> = BasicCollisionItem(body1, fixture1)
        val item2: CollisionItem<Body, BodyFixture> = BasicCollisionItem(body2, fixture2)
        val contact = ContactConstraint(BasicCollisionPair(item1, item2))
        val graph = ConstraintGraph<Body>()
        graph.addBody(body1)
        graph.addBody(body2)
        val contacts = graph.getContacts(body1)

        assertTrue(contacts.isEmpty())
        graph.addContactConstraint(contact)
        assertEquals(1, contacts.size)
        assertSame(contact, contacts.single())
        assertTrue(graph.containsContactConstraint(contact))
        assertTrue(graph.isInContact(body1, body2))
        assertEquals(listOf(body2), graph.getInContactBodies(body1, false))

        graph.removeContactConstraint(contact)
        assertTrue(contacts.isEmpty())
        assertFalse(graph.isInContact(body1, body2))

        graph.addContactConstraint(contact)
        graph.removeBody(body1)
        assertFalse(graph.containsBody(body1))
        assertTrue(graph.getContacts(body2).isEmpty())
    }
}
