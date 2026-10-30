package org.dyn4j.dynamics.joint

import de.infix.testBalloon.framework.core.testSuite
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertSame
import kotlin.test.assertTrue
import org.dyn4j.dynamics.Body
import org.dyn4j.dynamics.Settings
import org.dyn4j.dynamics.TimeStep
import org.dyn4j.exception.InvalidIndexException
import org.dyn4j.exception.ArgumentNullException
import org.dyn4j.exception.EmptyCollectionException
import org.dyn4j.exception.NullElementException
import org.dyn4j.exception.SameObjectException
import org.dyn4j.geometry.Vector2

val JointBaseJourneyTest by testSuite {
    test("pairedJointExposesBodiesThroughReadOnlyIdentityPreservingView") { JointBaseJourneyTestFixture().run { pairedJointExposesBodiesThroughReadOnlyIdentityPreservingView() } }
    test("pairedJointCopyAndCollisionStateFollowBaseline") { JointBaseJourneyTestFixture().run { pairedJointCopyAndCollisionStateFollowBaseline() } }
    test("singleJointKeepsItsBodyAndCopiesOnlyOnRequest") { JointBaseJourneyTestFixture().run { singleJointKeepsItsBodyAndCopiesOnlyOnRequest() } }
    test("abstractJointAcceptsListsAndKeepsTheUnmodifiableViewLive") { JointBaseJourneyTestFixture().run { abstractJointAcceptsListsAndKeepsTheUnmodifiableViewLive() } }
}

private class JointBaseJourneyTestFixture  {
fun pairedJointExposesBodiesThroughReadOnlyIdentityPreservingView() {
        val first = Body()
        val second = Body()
        val joint: Joint<Body> = TestPair(first, second)

        assertEquals(2, joint.getBodyCount())
        assertSame(first, joint.getBody(0))
        assertSame(second, joint.getBody(1))
        assertTrue(joint.isMember(first))
        assertFalse(joint.isMember(Body()))
        assertSame(first, joint.getBodies()[0])
        assertFailsWith<UnsupportedOperationException> { joint.getBodies().clear() }
        assertFailsWith<UnsupportedOperationException> { joint.getBodyIterator().remove() }
        assertFailsWith<InvalidIndexException> { joint.getBody(2) }
        second.setEnabled(false)
        assertFalse(joint.isEnabled())
        second.setEnabled(true)
        assertTrue(joint.isEnabled())
    }

fun pairedJointCopyAndCollisionStateFollowBaseline() {
        val first = Body()
        val second = Body()
        val joint = TestPair(first, second)
        val marker = Any()
        joint.setUserData(marker)
        joint.setOwner(marker)
        first.setAtRest(true)
        second.setAtRest(true)
        joint.setCollisionAllowed(true)
        assertFalse(first.isAtRest())
        assertFalse(second.isAtRest())
        assertTrue(joint.isCollisionAllowed())
        assertSame(second, joint.getOtherBody(first))
        assertNull(joint.getOtherBody(Body()))

        val copy = joint.copy()
        assertTrue(copy.isCollisionAllowed())
        assertNull(copy.getUserData())
        assertNull(copy.getOwner())
        assertFalse(copy.getBody1() === first)
        assertFalse(copy.getBody2() === second)
        assertFailsWith<SameObjectException> { TestPair(first, first) }
    }

fun singleJointKeepsItsBodyAndCopiesOnlyOnRequest() {
        val body = Body()
        val joint = TestSingle(body)
        assertSame(body, joint.getBody())
        assertSame(body, joint.getBody(0))
        assertEquals(1, joint.getBodyCount())
        assertTrue(joint.isMember(body))
        assertFailsWith<InvalidIndexException> { joint.getBody(-1) }
        val sharedCopy = joint.copy(body)
        assertSame(body, sharedCopy.getBody())
        val deepCopy = joint.copy()
        assertFalse(deepCopy.getBody() === body)
        assertFailsWith<NullElementException> { TestSingle(null) }
        assertFailsWith<NullElementException> { TestPair(null, Body()) }
    }

fun abstractJointAcceptsListsAndKeepsTheUnmodifiableViewLive() {
        val first = Body()
        val second = Body()
        val source = mutableListOf(first)
        val joint = TestGeneral(source)
        val view = joint.getBodies()
        source.add(second)
        assertSame(view, joint.getBodies())
        assertEquals(2, joint.getBodyCount())
        assertSame(second, view[1])
        assertFailsWith<UnsupportedOperationException> { view.remove(Body()) }
        assertFailsWith<ArgumentNullException> { TestGeneral(null) }
        assertFailsWith<EmptyCollectionException> { TestGeneral(emptyList()) }
        @Suppress("UNCHECKED_CAST")
        val withNull = listOf<Body?>(null) as List<Body>
        assertFailsWith<NullElementException> { TestGeneral(withNull) }
    }

    private class TestPair : AbstractPairedBodyJoint<Body> {
        constructor(first: Body?, second: Body?) : super(first, second)
        private constructor(source: TestPair, first: Body?, second: Body?) : super(source, first, second)

        override fun copy() = TestPair(this, null, null)
        override fun copy(body1: Body?, body2: Body?) = TestPair(this, body1, body2)
        override fun shift(shift: Vector2) {}
        override fun initializeConstraints(step: TimeStep?, settings: Settings?) {}
        override fun solveVelocityConstraints(step: TimeStep?, settings: Settings?) {}
        override fun solvePositionConstraints(step: TimeStep?, settings: Settings?) = true
        override fun getReactionForce(invdt: Double) = Vector2()
        override fun getReactionTorque(invdt: Double) = 0.0
    }

    private class TestSingle : AbstractSingleBodyJoint<Body> {
        constructor(body: Body?) : super(body)
        private constructor(source: TestSingle, body: Body?) : super(source, body)

        override fun copy() = TestSingle(this, null)
        override fun copy(body: Body?) = TestSingle(this, body)
        override fun shift(shift: Vector2) {}
        override fun initializeConstraints(step: TimeStep?, settings: Settings?) {}
        override fun solveVelocityConstraints(step: TimeStep?, settings: Settings?) {}
        override fun solvePositionConstraints(step: TimeStep?, settings: Settings?) = true
        override fun getReactionForce(invdt: Double) = Vector2()
        override fun getReactionTorque(invdt: Double) = 0.0
    }

    private class TestGeneral(source: List<Body>?) : AbstractJoint<Body>(source) {
        override fun copy() = TestGeneral(getBodies().map { it.copy() })
        override fun shift(shift: Vector2) {}
        override fun initializeConstraints(step: TimeStep?, settings: Settings?) {}
        override fun solveVelocityConstraints(step: TimeStep?, settings: Settings?) {}
        override fun solvePositionConstraints(step: TimeStep?, settings: Settings?) = true
        override fun getReactionForce(invdt: Double) = Vector2()
        override fun getReactionTorque(invdt: Double) = 0.0
    }
}
