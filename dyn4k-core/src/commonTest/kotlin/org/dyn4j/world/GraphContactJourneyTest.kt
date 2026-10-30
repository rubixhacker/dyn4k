package org.dyn4j.world

import de.infix.testBalloon.framework.core.testSuite
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

val GraphContactJourneyTest by testSuite {
    test("emptyNestedGraphClearInvalidatesSavedSiblings") { GraphContactJourneyTestFixture().run { emptyNestedGraphClearInvalidatesSavedSiblings() } }
    test("trackedGraphEdgeSortAndReplaceAllInvalidateSavedViews") { GraphContactJourneyTestFixture().run { trackedGraphEdgeSortAndReplaceAllInvalidateSavedViews() } }
    test("graphContactAndJointViewsKeepLiveIdentityAndFailFastIterators") { GraphContactJourneyTestFixture().run { graphContactAndJointViewsKeepLiveIdentityAndFailFastIterators() } }
    test("graphProtectedIteratorsAndPublicSubListsRejectStructuralChangeOnly") { GraphContactJourneyTestFixture().run { graphProtectedIteratorsAndPublicSubListsRejectStructuralChangeOnly() } }
    test("graphProtectedSubListsRejectStructuralChangeOnly") { GraphContactJourneyTestFixture().run { graphProtectedSubListsRejectStructuralChangeOnly() } }
    test("graphPublicSubListsUseBaselineRangeErrors") { GraphContactJourneyTestFixture().run { graphPublicSubListsUseBaselineRangeErrors() } }
    test("graphListsAndSubListsMarkRandomAccess") { GraphContactJourneyTestFixture().run { graphListsAndSubListsMarkRandomAccess() } }
    test("contactViewsTrackEdgesAndBodyRemoval") { GraphContactJourneyTestFixture().run { contactViewsTrackEdgesAndBodyRemoval() } }
}

private class GraphContactJourneyTestFixture  {
fun emptyNestedGraphClearInvalidatesSavedSiblings() {
        val node = ConstraintGraphNode(Body())
        val joint = PinJoint(node.getBody(), Vector2())
        node.mutableJoints().add(joint)
        val rootIterator = node.mutableJoints().iterator()
        val parent = node.mutableJoints().subList(0, 1)
        val child = parent.subList(0, 0)
        val sibling = parent.subList(0, 1)
        child.clear()
        assertEquals(0, assertWorldViewOutcome(worldNestedViewOutcome(WorldViewOperation.EMPTY_CLEAR_CHILD_SIZE)) { child.size })
        assertSame(joint, assertWorldViewOutcome(worldNestedViewOutcome(WorldViewOperation.EMPTY_CLEAR_PARENT_READ)) { parent[0] })
        val iteratorOutcome = worldNestedViewOutcome(WorldViewOperation.EMPTY_CLEAR_ROOT_ITERATOR)
        val iteratorValue = assertWorldViewOutcome(iteratorOutcome) { rootIterator.next() }
        if (iteratorOutcome == WorldViewOutcome.VALUE) assertSame(joint, iteratorValue)
        val siblingOutcome = worldNestedViewOutcome(WorldViewOperation.EMPTY_CLEAR_SIBLING_READ)
        val siblingValue = assertWorldViewOutcome(siblingOutcome) { sibling[0] }
        if (siblingOutcome == WorldViewOutcome.VALUE) assertSame(joint, siblingValue)
    }

fun trackedGraphEdgeSortAndReplaceAllInvalidateSavedViews() {
        val body = Body()
        val fixture = body.addFixture(Circle(0.5))
        val other = Body()
        val otherFixture = other.addFixture(Circle(0.5))
        val contact = ContactConstraint(
            BasicCollisionPair(BasicCollisionItem(body, fixture), BasicCollisionItem(other, otherFixture))
        )
        val joint = PinJoint(body, Vector2())
        fun <E> verify(backing: WorldTrackedArrayList<E>, mutate: (WorldTrackedArrayList<E>) -> Unit) {
            val view = backing.liveView()
            val iterator = backing.iterator()
            val protectedSublist = backing.subList(0, 1)
            val publicSublist = view.subList(0, 1)
            val original = backing[0]
            mutate(backing)
            assertSame(original, view[0])
            assertFailsWith<ConcurrentModificationException> { iterator.next() }
            assertFailsWith<ConcurrentModificationException> { protectedSublist[0] }
            assertFailsWith<ConcurrentModificationException> { publicSublist[0] }
        }

        val contacts = WorldTrackedArrayList<ContactConstraint<Body>>()
        val joints = WorldTrackedArrayList<PinJoint<Body>>()
        contacts.add(contact)
        joints.add(joint)
        verify(contacts) { it.sortElements(Comparator { _, _ -> 0 }) }
        verify(contacts) { it.replaceAllElements { value -> value } }
        verify(joints) { it.sortElements(Comparator { _, _ -> 0 }) }
        verify(joints) { it.replaceAllElements { value -> value } }
    }

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

fun graphProtectedSubListsRejectStructuralChangeOnly() {
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
        val contacts = node.mutableContacts().subList(0, 1)
        val joints = node.mutableJoints().subList(0, 1)
        node.mutableContacts()[0] = contact
        node.mutableJoints()[0] = joint
        assertSame(contact, contacts[0])
        assertSame(joint, joints[0])
        graph.addContactConstraint(contact)
        graph.addJoint(PinJoint(a, Vector2()))
        assertFailsWith<ConcurrentModificationException> { contacts[0] }
        assertFailsWith<ConcurrentModificationException> { contacts.size }
        assertFailsWith<ConcurrentModificationException> { joints[0] }
        assertFailsWith<ConcurrentModificationException> { joints.size }
    }

fun graphPublicSubListsUseBaselineRangeErrors() {
        val node = ConstraintGraphNode(Body())
        val views: List<List<*>> = listOf(node.getContactConstraints(), node.getJoints())
        for (view in views) {
            assertFailsWith<IllegalArgumentException> { view.subList(1, 0) }
            assertFailsWith<IndexOutOfBoundsException> { view.subList(-1, 0) }
        }
    }

fun graphListsAndSubListsMarkRandomAccess() {
        val node = ConstraintGraphNode(Body())
        assertTrue(node.mutableContacts() is RandomAccess)
        assertTrue(node.mutableJoints() is RandomAccess)
        val views = listOf(node.getContactConstraints(), node.getJoints())
        for (view in views) {
            assertTrue(view is RandomAccess)
            assertTrue(view.subList(0, 0) is RandomAccess)
        }
    }

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
