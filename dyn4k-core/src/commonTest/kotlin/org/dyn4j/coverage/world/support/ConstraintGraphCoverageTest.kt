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
package org.dyn4j.coverage.world.support

import de.infix.testBalloon.framework.core.testSuite
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertSame
import kotlin.test.assertTrue
import org.dyn4j.collision.BasicCollisionItem
import org.dyn4j.collision.BasicCollisionPair
import org.dyn4j.collision.CollisionItem
import org.dyn4j.collision.manifold.Manifold
import org.dyn4j.dynamics.Body
import org.dyn4j.dynamics.BodyFixture
import org.dyn4j.dynamics.Settings
import org.dyn4j.dynamics.TimeStep
import org.dyn4j.dynamics.contact.Contact
import org.dyn4j.dynamics.contact.ContactConstraint
import org.dyn4j.dynamics.contact.ContactUpdateHandler
import org.dyn4j.dynamics.contact.SequentialImpulses
import org.dyn4j.dynamics.joint.AbstractJoint
import org.dyn4j.dynamics.joint.AngleJoint
import org.dyn4j.dynamics.joint.PinJoint
import org.dyn4j.geometry.Geometry
import org.dyn4j.geometry.MassType
import org.dyn4j.geometry.Vector2
import org.dyn4j.world.ConstraintGraph

val ConstraintGraphCoverageTest by testSuite {
    test("create") { ConstraintGraphCoverageTestFixture().run { create() } }
    test("addBody") { ConstraintGraphCoverageTestFixture().run { addBody() } }
    test("addContactConstraint") { ConstraintGraphCoverageTestFixture().run { addContactConstraint() } }
    test("addContactConstraintBodiesNotAdded") { ConstraintGraphCoverageTestFixture().run { addContactConstraintBodiesNotAdded() } }
    test("addJoint") { ConstraintGraphCoverageTestFixture().run { addJoint() } }
    test("addJointBodiesNotAdded") { ConstraintGraphCoverageTestFixture().run { addJointBodiesNotAdded() } }
    test("savedNodeViewIteratorsFailFastAfterStructuralMutation") { ConstraintGraphCoverageTestFixture().run { savedNodeViewIteratorsFailFastAfterStructuralMutation() } }
    test("removeAllContactConstraints") { ConstraintGraphCoverageTestFixture().run { removeAllContactConstraints() } }
    test("removeAllJoints") { ConstraintGraphCoverageTestFixture().run { removeAllJoints() } }
    test("removeBody") { ConstraintGraphCoverageTestFixture().run { removeBody() } }
    test("clear") { ConstraintGraphCoverageTestFixture().run { clear() } }
    test("removeJoint") { ConstraintGraphCoverageTestFixture().run { removeJoint() } }
    test("removeContactConstraint") { ConstraintGraphCoverageTestFixture().run { removeContactConstraint() } }
    test("size") { ConstraintGraphCoverageTestFixture().run { size() } }
    test("isJoined") { ConstraintGraphCoverageTestFixture().run { isJoined() } }
    test("isJointCollisionAllowed") { ConstraintGraphCoverageTestFixture().run { isJointCollisionAllowed() } }
    test("getJoinedBodies") { ConstraintGraphCoverageTestFixture().run { getJoinedBodies() } }
    test("getJointsForBody") { ConstraintGraphCoverageTestFixture().run { getJointsForBody() } }
    test("getInContactBodies") { ConstraintGraphCoverageTestFixture().run { getInContactBodies() } }
    test("getContacts") { ConstraintGraphCoverageTestFixture().run { getContacts() } }
    test("isInContact") { ConstraintGraphCoverageTestFixture().run { isInContact() } }
    test("getJoinedBodiesMulti") { ConstraintGraphCoverageTestFixture().run { getJoinedBodiesMulti() } }
    test("getInContactBodiesMulti") { ConstraintGraphCoverageTestFixture().run { getInContactBodiesMulti() } }
    test("multiCollision") { ConstraintGraphCoverageTestFixture().run { multiCollision() } }
    test("testRemoveBodyWithUnaryJoint") { ConstraintGraphCoverageTestFixture().run { testRemoveBodyWithUnaryJoint() } }
    test("removeBodyWithQuadrupleJoint") { ConstraintGraphCoverageTestFixture().run { removeBodyWithQuadrupleJoint() } }
}

private class ConstraintGraphCoverageTestFixture  {
    private fun body(): Body = Body().also {
        it.addFixture(Geometry.createCircle(0.5)); it.setMass(MassType.NORMAL)
    }

    private fun constraint(a: Body, b: Body, fa: BodyFixture = a.getFixture(0), fb: BodyFixture = b.getFixture(0)):
        ContactConstraint<Body> = ContactConstraint(BasicCollisionPair<CollisionItem<Body, BodyFixture>>(
            BasicCollisionItem(a, fa), BasicCollisionItem(b, fb)))

    private data class Triangle(
        val graph: ConstraintGraph<Body>, val a: Body, val b: Body, val c: Body,
        val ab: ContactConstraint<Body>, val ac: ContactConstraint<Body>, val bc: ContactConstraint<Body>,
        val jab: AngleJoint<Body>, val jac: AngleJoint<Body>, val jbc: AngleJoint<Body>
    )

    private fun triangle(): Triangle {
        val graph = ConstraintGraph<Body>()
        val a = Body().also { it.addFixture(Geometry.createCircle(1.0)) }
        val b = Body().also { it.addFixture(Geometry.createEquilateralTriangle(0.5)) }
        val c = Body().also { it.addFixture(Geometry.createCircle(0.5)) }
        graph.addBody(a); graph.addBody(b); graph.addBody(c)
        val jab = AngleJoint(a, b); val jac = AngleJoint(a, c); val jbc = AngleJoint(b, c)
        val ab = constraint(a, b); val ac = constraint(a, c); val bc = constraint(b, c)
        listOf(jab, jac, jbc).forEach(graph::addJoint)
        listOf(ab, ac, bc).forEach(graph::addContactConstraint)
        return Triangle(graph, a, b, c, ab, ac, bc, jab, jac, jbc)
    }

    private fun <T> assertOrderedIdentities(actual: List<T>, first: T, second: T) {
        assertEquals(2, actual.size)
        assertSame(first, actual[0])
        assertSame(second, actual[1])
    }

    private fun <T> assertSingleIdentity(actual: List<T>, expected: T) {
        assertEquals(1, actual.size)
        assertSame(expected, actual[0])
    }

fun create() {
        for (graph in listOf(ConstraintGraph<Body>(), ConstraintGraph(10, 5),
            ConstraintGraph(-1, 5), ConstraintGraph(0, 5), ConstraintGraph(5, -5), ConstraintGraph(10, 0))) {
            assertEquals(0, graph.size())
        }
    }

fun addBody() {
        val graph = ConstraintGraph<Body>(); val body = body()
        graph.addBody(body)
        val node = assertNotNull(graph.getNode(body))
        assertTrue(graph.containsBody(body))
        assertSame(body, node.getBody())
        assertTrue(node.getJoints().isEmpty()); assertTrue(node.getContactConstraints().isEmpty())
        graph.addBody(body)
        assertSame(node, graph.getNode(body))
        assertEquals(1, graph.size())
    }

fun addContactConstraint() {
        val graph = ConstraintGraph<Body>(); val a = body(); val b = body()
        graph.addBody(a); graph.addBody(b)
        val contact = constraint(a, b); graph.addContactConstraint(contact)
        assertTrue(graph.isInContact(a, b)); assertTrue(graph.containsContactConstraint(contact))
        assertSame(contact, graph.getNode(a)!!.getContactConstraints().single())
        assertSame(contact, graph.getNode(b)!!.getContactConstraints().single())
        assertFalse(graph.containsContactConstraint(constraint(a, b)))
    }

fun addContactConstraintBodiesNotAdded() {
        val graph = ConstraintGraph<Body>(); val a = body(); val b = body()
        val contact = constraint(a, b); graph.addContactConstraint(contact)
        assertEquals(2, graph.size())
        assertTrue(graph.isInContact(a, b))
        assertSame(contact, graph.getNode(a)!!.getContactConstraints().single())
        assertSame(contact, graph.getNode(b)!!.getContactConstraints().single())
    }

fun addJoint() {
        val graph = ConstraintGraph<Body>(); val a = body(); val b = body()
        graph.addBody(a); graph.addBody(b)
        val joint = AngleJoint(a, b); graph.addJoint(joint)
        assertSame(joint, graph.getNode(a)!!.getJoints().single())
        assertSame(joint, graph.getNode(b)!!.getJoints().single())
        assertTrue(graph.isJoined(a, b)); assertTrue(graph.containsJoint(joint))
        assertFalse(graph.containsJoint(AngleJoint(a, b)))
    }

fun addJointBodiesNotAdded() {
        val graph = ConstraintGraph<Body>(); val a = body(); val b = body()
        val joint = AngleJoint(a, b); graph.addJoint(joint)
        assertEquals(2, graph.size())
        assertSame(joint, graph.getNode(a)!!.getJoints().single())
        assertSame(joint, graph.getNode(b)!!.getJoints().single())
        assertTrue(graph.isJoined(a, b)); assertFalse(graph.containsJoint(AngleJoint(a, b)))
    }

fun savedNodeViewIteratorsFailFastAfterStructuralMutation() {
        val graph = ConstraintGraph<Body>(); val a = body(); val b = body()
        graph.addContactConstraint(constraint(a, b))
        graph.addJoint(AngleJoint(a, b))
        val node = assertNotNull(graph.getNode(a))
        val contacts = node.getContactConstraints()
        val joints = node.getJoints()
        val contactIterator = contacts.iterator()
        val jointIterator = joints.iterator()

        graph.addContactConstraint(constraint(a, b))
        graph.addJoint(AngleJoint(a, b))
        assertEquals(2, contacts.size)
        assertEquals(2, joints.size)
        val contactFailure = runCatching { contactIterator.next() }.exceptionOrNull()
        val jointFailure = runCatching { jointIterator.next() }.exceptionOrNull()
        assertTrue(contactFailure is ConcurrentModificationException &&
            jointFailure is ConcurrentModificationException,
            "contact=$contactFailure, joint=$jointFailure")
    }

fun removeAllContactConstraints() {
        val graph = ConstraintGraph<Body>(); val a = body(); val b = body()
        val first = constraint(a, b); val second = constraint(a, b)
        graph.addContactConstraint(first); graph.addContactConstraint(second)
        val view = graph.getNode(a)!!.getContactConstraints()
        assertEquals(listOf(first, second), view)
        assertEquals(listOf(first, second), graph.getNode(b)!!.getContactConstraints())
        graph.removeAllContactConstraints()
        assertTrue(view.isEmpty()); assertTrue(graph.getNode(b)!!.getContactConstraints().isEmpty())
        assertFalse(graph.isInContact(a, b))
        assertFalse(graph.containsContactConstraint(first)); assertFalse(graph.containsContactConstraint(second))
        assertTrue(graph.containsBody(a)); assertTrue(graph.containsBody(b))
    }

fun removeAllJoints() {
        val graph = ConstraintGraph<Body>(); val a = body(); val b = body()
        val first = AngleJoint(a, b); val second = AngleJoint(a, b)
        graph.addJoint(first); graph.addJoint(second)
        val view = graph.getNode(a)!!.getJoints()
        assertEquals(listOf(first, second), view)
        assertEquals(listOf(first, second), graph.getNode(b)!!.getJoints())
        graph.removeAllJoints()
        assertTrue(view.isEmpty()); assertTrue(graph.getNode(b)!!.getJoints().isEmpty())
        assertFalse(graph.isJoined(a, b)); assertFalse(graph.containsJoint(first))
        assertFalse(graph.containsJoint(second)); assertTrue(graph.containsBody(a)); assertTrue(graph.containsBody(b))
    }

fun removeBody() {
        val t = triangle()
        val nodeA = assertNotNull(t.graph.getNode(t.a))
        val nodeB = assertNotNull(t.graph.getNode(t.b))
        val nodeC = assertNotNull(t.graph.getNode(t.c))
        val aContacts = nodeA.getContactConstraints(); val aJoints = nodeA.getJoints()
        val bContacts = nodeB.getContactConstraints(); val bJoints = nodeB.getJoints()
        val cContacts = nodeC.getContactConstraints(); val cJoints = nodeC.getJoints()
        assertOrderedIdentities(aContacts, t.ab, t.ac)
        assertOrderedIdentities(aJoints, t.jab, t.jac)
        assertOrderedIdentities(bContacts, t.ab, t.bc)
        assertOrderedIdentities(bJoints, t.jab, t.jbc)
        assertOrderedIdentities(cContacts, t.ac, t.bc)
        assertOrderedIdentities(cJoints, t.jac, t.jbc)
        assertEquals(listOf(t.ab, t.ac), t.graph.getContacts(t.a))
        assertEquals(listOf(t.jab, t.jac), t.graph.getJoints(t.a))
        assertTrue(t.graph.isInContact(t.a, t.b)); assertTrue(t.graph.isInContact(t.a, t.c))
        assertTrue(t.graph.isInContact(t.b, t.c))
        assertTrue(t.graph.containsContactConstraint(t.ab)); assertTrue(t.graph.containsContactConstraint(t.ac))
        assertTrue(t.graph.containsContactConstraint(t.bc))
        assertTrue(t.graph.isJoined(t.a, t.b)); assertTrue(t.graph.isJoined(t.a, t.c))
        assertTrue(t.graph.isJoined(t.b, t.c))
        assertTrue(t.graph.containsJoint(t.jab)); assertTrue(t.graph.containsJoint(t.jac))
        assertTrue(t.graph.containsJoint(t.jbc))
        t.graph.removeBody(t.a)
        assertNull(t.graph.getNode(t.a)); assertFalse(t.graph.containsBody(t.a))
        val remainingB = assertNotNull(t.graph.getNode(t.b))
        val remainingC = assertNotNull(t.graph.getNode(t.c))
        assertSingleIdentity(remainingB.getContactConstraints(), t.bc)
        assertSingleIdentity(remainingB.getJoints(), t.jbc)
        assertSingleIdentity(remainingC.getContactConstraints(), t.bc)
        assertSingleIdentity(remainingC.getJoints(), t.jbc)
        assertSingleIdentity(bContacts, t.bc); assertSingleIdentity(bJoints, t.jbc)
        assertSingleIdentity(cContacts, t.bc); assertSingleIdentity(cJoints, t.jbc)
        assertEquals(listOf(t.bc), t.graph.getContacts(t.b))
        assertEquals(listOf(t.bc), t.graph.getContacts(t.c))
        assertEquals(listOf(t.jbc), t.graph.getJoints(t.b))
        assertEquals(listOf(t.jbc), t.graph.getJoints(t.c))
        assertFalse(t.graph.isInContact(t.a, t.b)); assertFalse(t.graph.isInContact(t.a, t.c))
        assertFalse(t.graph.isJoined(t.a, t.b)); assertFalse(t.graph.isJoined(t.a, t.c))
        assertFalse(t.graph.containsContactConstraint(t.ab)); assertFalse(t.graph.containsContactConstraint(t.ac))
        assertFalse(t.graph.containsJoint(t.jab)); assertFalse(t.graph.containsJoint(t.jac))
        assertTrue(t.graph.containsContactConstraint(t.bc)); assertTrue(t.graph.containsJoint(t.jbc))
        assertTrue(t.graph.isInContact(t.b, t.c)); assertTrue(t.graph.isJoined(t.b, t.c))
    }

fun clear() {
        val t = triangle()
        assertEquals(3, t.graph.size())
        val nodeA = assertNotNull(t.graph.getNode(t.a))
        val nodeB = assertNotNull(t.graph.getNode(t.b))
        val nodeC = assertNotNull(t.graph.getNode(t.c))
        assertOrderedIdentities(nodeA.getContactConstraints(), t.ab, t.ac)
        assertOrderedIdentities(nodeA.getJoints(), t.jab, t.jac)
        assertOrderedIdentities(nodeB.getContactConstraints(), t.ab, t.bc)
        assertOrderedIdentities(nodeB.getJoints(), t.jab, t.jbc)
        assertOrderedIdentities(nodeC.getContactConstraints(), t.ac, t.bc)
        assertOrderedIdentities(nodeC.getJoints(), t.jac, t.jbc)
        assertTrue(t.graph.isInContact(t.a, t.b)); assertTrue(t.graph.isInContact(t.a, t.c))
        assertTrue(t.graph.isInContact(t.b, t.c))
        assertTrue(t.graph.containsContactConstraint(t.ab)); assertTrue(t.graph.containsContactConstraint(t.ac))
        assertTrue(t.graph.containsContactConstraint(t.bc))
        assertTrue(t.graph.isJoined(t.a, t.b)); assertTrue(t.graph.isJoined(t.a, t.c))
        assertTrue(t.graph.isJoined(t.b, t.c))
        assertTrue(t.graph.containsJoint(t.jab)); assertTrue(t.graph.containsJoint(t.jac))
        assertTrue(t.graph.containsJoint(t.jbc))
        t.graph.clear()
        assertEquals(0, t.graph.size())
        for (body in listOf(t.a, t.b, t.c)) assertNull(t.graph.getNode(body))
        assertFalse(t.graph.isInContact(t.a, t.b)); assertFalse(t.graph.isInContact(t.a, t.c))
        assertFalse(t.graph.isInContact(t.b, t.c))
        assertFalse(t.graph.containsContactConstraint(t.ab)); assertFalse(t.graph.containsContactConstraint(t.ac))
        assertFalse(t.graph.containsContactConstraint(t.bc))
        assertFalse(t.graph.isJoined(t.a, t.b)); assertFalse(t.graph.isJoined(t.a, t.c))
        assertFalse(t.graph.isJoined(t.b, t.c))
        assertFalse(t.graph.containsJoint(t.jab)); assertFalse(t.graph.containsJoint(t.jac))
        assertFalse(t.graph.containsJoint(t.jbc))
    }

fun removeJoint() {
        val graph = ConstraintGraph<Body>(); val a = body(); val b = body()
        val first = AngleJoint(a, b); val second = AngleJoint(a, b)
        graph.addJoint(first); graph.addJoint(second)
        graph.removeJoint(first)
        assertFalse(graph.containsJoint(first)); assertTrue(graph.containsJoint(second))
        assertTrue(graph.isJoined(a, b))
        assertEquals(listOf(second), graph.getJoints(a)); assertEquals(listOf(second), graph.getJoints(b))
        assertTrue(graph.containsBody(a)); assertTrue(graph.containsBody(b))
    }

fun removeContactConstraint() {
        val graph = ConstraintGraph<Body>(); val a = body(); val b = body()
        val first = constraint(a, b); val second = constraint(a, b)
        graph.addContactConstraint(first); graph.addContactConstraint(second)
        graph.removeContactConstraint(first)
        assertFalse(graph.containsContactConstraint(first)); assertTrue(graph.containsContactConstraint(second))
        assertTrue(graph.isInContact(a, b))
        assertEquals(listOf(second), graph.getContacts(a))
        assertEquals(listOf(second), graph.getContacts(b))
    }

fun size() {
        val t = triangle()
        assertEquals(3, t.graph.size())
        t.graph.removeBody(t.a)
        assertEquals(2, t.graph.size())
        t.graph.removeContactConstraint(t.bc)
        assertEquals(2, t.graph.size())
        t.graph.removeJoint(t.jbc)
        assertEquals(2, t.graph.size())
        t.graph.clear(); assertEquals(0, t.graph.size())
    }

fun isJoined() {
        val graph = ConstraintGraph<Body>(); val a = body(); val b = body(); val c = body()
        graph.addBody(a); graph.addBody(b); graph.addBody(c)
        assertFalse(graph.isJoined(a, null)); assertFalse(graph.isJoined(a, b))
        graph.addJoint(AngleJoint(a, b))
        assertFalse(graph.isJoined(a, c)); assertTrue(graph.isJoined(a, b))
    }

fun isJointCollisionAllowed() {
        val graph = ConstraintGraph<Body>(); val a = body(); val b = body()
        graph.addBody(a); graph.addBody(b)
        val first = AngleJoint(a, b); val second = AngleJoint(a, b)
        graph.addJoint(first); graph.addJoint(second)
        assertFalse(graph.isJointCollisionAllowed(a, b))
        second.setCollisionAllowed(true)
        assertTrue(graph.isJointCollisionAllowed(a, b))
        assertFalse(graph.isJointCollisionAllowed(a, null))
        assertFalse(graph.isJointCollisionAllowed(null, b))
        assertFalse(graph.isJointCollisionAllowed(null, null))
        assertFalse(graph.isJointCollisionAllowed(a, Body()))
        assertFalse(graph.isJointCollisionAllowed(Body(), b))
        val c = body(); graph.addBody(c)
        assertTrue(graph.isJointCollisionAllowed(c, a))
    }

fun getJoinedBodies() {
        val graph = ConstraintGraph<Body>(); val a = body(); val b = body()
        graph.addBody(a); graph.addBody(b)
        assertTrue(graph.getJoinedBodies(a).isEmpty())
        graph.addJoint(AngleJoint(a, b))
        assertSame(b, graph.getJoinedBodies(a).single())
    }

fun getJointsForBody() {
        val graph = ConstraintGraph<Body>(); val a = body(); val b = body()
        graph.addBody(a); graph.addBody(b)
        val view = graph.getJoints(a)
        assertTrue(view.isEmpty())
        val joint = AngleJoint(a, b); graph.addJoint(joint)
        assertSame(joint, view.single())
        assertTrue(graph.getJoints(null).isEmpty())
    }

    private val contactHandler = object : ContactUpdateHandler {
        override fun getFriction(fixture1: BodyFixture, fixture2: BodyFixture) = 0.0
        override fun getRestitution(fixture1: BodyFixture, fixture2: BodyFixture) = 0.0
        override fun getRestitutionVelocity(fixture1: BodyFixture, fixture2: BodyFixture) = 0.0
        override fun begin(contact: Contact) {}
        override fun persist(oldContact: Contact, newContact: Contact) {}
        override fun end(contact: Contact) {}
    }

fun getInContactBodies() {
        val graph = ConstraintGraph<Body>(); val a = body(); val b = body()
        graph.addBody(a); graph.addBody(b)
        assertTrue(graph.getInContactBodies(a, false).isEmpty())
        assertTrue(graph.getInContactBodies(a, true).isEmpty())
        val contact = constraint(a, b); graph.addContactConstraint(contact)
        assertSame(b, graph.getInContactBodies(a, false).single())
        a.getFixture(0).setSensor(true)
        contact.update(Manifold(), Settings(), contactHandler)
        assertTrue(graph.getInContactBodies(a, false).isEmpty())
        assertSame(b, graph.getInContactBodies(a, true).single())
    }

fun getContacts() {
        val graph = ConstraintGraph<Body>(); val a = body(); val b = body()
        graph.addBody(a); graph.addBody(b)
        val view = graph.getContacts(a)
        assertTrue(view.isEmpty())
        val contact = constraint(a, b); graph.addContactConstraint(contact)
        assertSame(contact, view.single())
        assertTrue(graph.getContacts(null).isEmpty())
    }

fun isInContact() {
        val graph = ConstraintGraph<Body>(); val a = body(); val b = body()
        graph.addBody(a); graph.addBody(b)
        assertFalse(graph.isInContact(a, b))
        graph.addContactConstraint(constraint(a, b))
        assertTrue(graph.isInContact(a, b))
    }

fun getJoinedBodiesMulti() {
        val graph = ConstraintGraph<Body>(); val a = body(); val b = body()
        graph.addJoint(AngleJoint(a, b)); graph.addJoint(AngleJoint(a, b))
        assertEquals(listOf(b), graph.getJoinedBodies(a))
    }

fun getInContactBodiesMulti() {
        val graph = ConstraintGraph<Body>(); val a = body(); val b = body()
        val extra = b.addFixture(Geometry.createCircle(0.25))
        graph.addContactConstraint(constraint(a, b))
        graph.addContactConstraint(constraint(a, b, fb = extra))
        assertEquals(listOf(b), graph.getInContactBodies(a, false))
    }

    private class CountingBody : Body() {
        var integrations = 0
        override fun integrateVelocity(gravity: Vector2?, timestep: TimeStep?, settings: Settings?) {
            integrations++
            if (integrations > 1) throw IllegalStateException("body integrated twice")
            super.integrateVelocity(gravity, timestep, settings)
        }
    }

fun multiCollision() {
        val graph = ConstraintGraph<Body>()
        val bodies = List(4) { CountingBody().also { it.addFixture(Geometry.createCircle(0.5)); it.setMass(MassType.NORMAL) } }
        bodies.forEach(graph::addBody)
        for ((first, second) in listOf(0 to 1, 0 to 1, 0 to 2, 2 to 3, 1 to 2, 1 to 3)) {
            graph.addContactConstraint(constraint(bodies[first], bodies[second]))
        }
        val settings = Settings()
        graph.solve(SequentialImpulses(), Vector2(), TimeStep(settings.getStepFrequency()), settings)
        bodies.forEach { assertEquals(1, it.integrations) }
    }

fun testRemoveBodyWithUnaryJoint() {
        val graph = ConstraintGraph<Body>(); val body = body()
        graph.addBody(body)
        val joint = PinJoint(body, body.getWorldCenter()); graph.addJoint(joint)
        assertTrue(graph.containsBody(body)); assertTrue(graph.containsJoint(joint))
        graph.removeBody(body)
        assertFalse(graph.containsBody(body)); assertFalse(graph.containsJoint(joint))
    }

    private class FourBodyJoint(bodies: List<Body>) : AbstractJoint<Body>(bodies) {
        override fun initializeConstraints(step: TimeStep?, settings: Settings?) {}
        override fun solveVelocityConstraints(step: TimeStep?, settings: Settings?) {}
        override fun solvePositionConstraints(step: TimeStep?, settings: Settings?) = false
        override fun getReactionForce(invdt: Double) = Vector2()
        override fun getReactionTorque(invdt: Double) = 0.0
        override fun shift(shift: Vector2) {}
        override fun copy(): FourBodyJoint = FourBodyJoint(getBodies().toList())
    }

fun removeBodyWithQuadrupleJoint() {
        val graph = ConstraintGraph<Body>()
        val bodies = List(4) { body().also(graph::addBody) }
        val joint = FourBodyJoint(bodies)
        graph.addJoint(joint)
        assertTrue(bodies.all(graph::containsBody)); assertTrue(graph.containsJoint(joint))
        graph.removeBody(bodies[2])
        assertTrue(graph.containsBody(bodies[0])); assertTrue(graph.containsBody(bodies[1]))
        assertFalse(graph.containsBody(bodies[2])); assertTrue(graph.containsBody(bodies[3]))
        assertFalse(graph.containsJoint(joint))
        graph.addBody(bodies[2]); graph.addJoint(joint)
        assertTrue(bodies.all(graph::containsBody)); assertTrue(graph.containsJoint(joint))
        graph.removeJoint(joint)
        assertTrue(bodies.all(graph::containsBody)); assertFalse(graph.containsJoint(joint))
    }
}
