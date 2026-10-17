package org.dyn4j.world

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertFailsWith
import kotlin.test.assertSame
import kotlin.test.assertTrue
import org.dyn4j.collision.BasicCollisionItem
import org.dyn4j.collision.BasicCollisionPair
import org.dyn4j.collision.CollisionItem
import org.dyn4j.dynamics.Body
import org.dyn4j.dynamics.BodyFixture
import org.dyn4j.dynamics.contact.ContactConstraint
import org.dyn4j.dynamics.joint.PinJoint
import org.dyn4j.geometry.Circle
import org.dyn4j.geometry.Vector2

class GraphContactJourneyTest {
    @Test
    fun graphContactAndJointViewsKeepLiveIdentityAndFailFastIterators() {
        val body1 = Body()
        val fixture1 = body1.addFixture(Circle(0.5))
        val body2 = Body()
        val fixture2 = body2.addFixture(Circle(0.5))
        val contact = ContactConstraint(
            BasicCollisionPair(
                BasicCollisionItem(body1, fixture1),
                BasicCollisionItem(body2, fixture2)
            )
        )
        val joint = PinJoint(body1, Vector2())
        val graph = ConstraintGraph<Body>()
        graph.addBody(body1)
        graph.addBody(body2)
        graph.addContactConstraint(contact)
        graph.addJoint(joint)
        val node = graph.getNode(body1)!!
        val contacts = node.getContactConstraints()
        val joints = node.getJoints()
        assertSame(contacts, node.getContactConstraints())
        assertSame(joints, node.getJoints())

        val contactAfterSet = contacts.iterator()
        val jointAfterSet = joints.iterator()
        node.mutableContacts()[0] = contact
        node.mutableJoints()[0] = joint
        assertSame(contact, contactAfterSet.next())
        assertSame(joint, jointAfterSet.next())

        val contactBeforeAdd = contacts.iterator()
        val jointBeforeAdd = joints.iterator()
        graph.addContactConstraint(contact)
        graph.addJoint(PinJoint(body1, Vector2()))
        assertEquals(2, contacts.size)
        assertEquals(2, joints.size)
        assertFailsWith<ConcurrentModificationException> { contactBeforeAdd.next() }
        assertFailsWith<ConcurrentModificationException> { jointBeforeAdd.next() }
    }

    @Test
    fun graphProtectedIteratorsAndPublicSubListsRejectStructuralChangeOnly() {
        val a = Body()
        val af = a.addFixture(Circle(0.5))
        val b = Body()
        val bf = b.addFixture(Circle(0.5))
        val contact = ContactConstraint(
            BasicCollisionPair(BasicCollisionItem(a, af), BasicCollisionItem(b, bf))
        )
        val joint = PinJoint(a, Vector2())
        val graph = ConstraintGraph<Body>()
        graph.addBody(a)
        graph.addBody(b)
        graph.addContactConstraint(contact)
        graph.addJoint(joint)
        val node = graph.getNode(a)!!
        val contacts = node.getContactConstraints()
        val joints = node.getJoints()
        val contactSubList = contacts.subList(0, 1)
        val jointSubList = joints.subList(0, 1)
        val contactBeforeSet = node.mutableContacts().iterator()
        val jointBeforeSet = node.mutableJoints().iterator()
        node.mutableContacts()[0] = contact
        node.mutableJoints()[0] = joint
        assertSame(contact, contactBeforeSet.next())
        assertSame(joint, jointBeforeSet.next())
        assertSame(contact, contactSubList[0])
        assertSame(joint, jointSubList[0])

        val contactBeforeAdd = node.mutableContacts().iterator()
        val jointBeforeAdd = node.mutableJoints().iterator()
        graph.addContactConstraint(contact)
        graph.addJoint(PinJoint(a, Vector2()))
        assertEquals(2, contacts.size)
        assertEquals(2, joints.size)
        assertFailsWith<ConcurrentModificationException> { contactBeforeAdd.next() }
        assertFailsWith<ConcurrentModificationException> { jointBeforeAdd.next() }
        assertFailsWith<ConcurrentModificationException> { contactSubList[0] }
        assertFailsWith<ConcurrentModificationException> { jointSubList[0] }
    }

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
