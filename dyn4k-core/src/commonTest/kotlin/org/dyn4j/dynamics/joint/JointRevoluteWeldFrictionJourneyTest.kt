package org.dyn4j.dynamics.joint

import de.infix.testBalloon.framework.core.testSuite
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotSame
import kotlin.test.assertTrue
import org.dyn4j.dynamics.Body
import org.dyn4j.dynamics.Settings
import org.dyn4j.dynamics.TimeStep
import org.dyn4j.geometry.Circle
import org.dyn4j.geometry.MassType
import org.dyn4j.geometry.Vector2

val JointRevoluteWeldFrictionJourneyTest by testSuite {
    test("revoluteMotorAndLimitsRetainSettingsAcrossCopy") { JointRevoluteWeldFrictionJourneyTestFixture().run { revoluteMotorAndLimitsRetainSettingsAcrossCopy() } }
    test("weldSpringAndLimitsRetainSettingsAcrossCopy") { JointRevoluteWeldFrictionJourneyTestFixture().run { weldSpringAndLimitsRetainSettingsAcrossCopy() } }
    test("frictionCapsVelocityImpulseAndNeedsNoPositionSolve") { JointRevoluteWeldFrictionJourneyTestFixture().run { frictionCapsVelocityImpulseAndNeedsNoPositionSolve() } }
    test("revoluteMotorTorqueIsCappedDuringVelocitySolve") { JointRevoluteWeldFrictionJourneyTestFixture().run { revoluteMotorTorqueIsCappedDuringVelocitySolve() } }
    test("weldSpringTorqueIsCappedDuringVelocitySolve") { JointRevoluteWeldFrictionJourneyTestFixture().run { weldSpringTorqueIsCappedDuringVelocitySolve() } }
    test("weldSpringUsesSubclassCoefficientOverride") { JointRevoluteWeldFrictionJourneyTestFixture().run { weldSpringUsesSubclassCoefficientOverride() } }
}

private class JointRevoluteWeldFrictionJourneyTestFixture  {
    private fun dynamicBody(): Body = Body().apply {
        addFixture(Circle(1.0))
        setMass(MassType.NORMAL)
    }

fun revoluteMotorAndLimitsRetainSettingsAcrossCopy() {
        val first = Body()
        val second = Body()
        val joint = RevoluteJoint(first, second, Vector2(1.0, 2.0))
        joint.setMotorEnabled(true)
        joint.setMotorSpeed(2.5)
        joint.setMaximumMotorTorqueEnabled(true)
        joint.setMaximumMotorTorque(6.0)
        joint.setLimitsEnabled(-0.2, 0.4)

        assertTrue(joint.isMotorEnabled())
        assertEquals(2.5, joint.getMotorSpeed())
        assertTrue(joint.isMaximumMotorTorqueEnabled())
        assertEquals(6.0, joint.getMaximumMotorTorque())
        assertTrue(joint.isLimitsEnabled())
        assertEquals(-0.2, joint.getLowerLimit())
        assertEquals(0.4, joint.getUpperLimit())
        assertNotSame(first, joint.copy().getBody1())
    }

fun weldSpringAndLimitsRetainSettingsAcrossCopy() {
        val first = Body()
        val second = Body()
        val joint = WeldJoint(first, second, Vector2())
        joint.setSpringEnabled(true)
        joint.setSpringFrequency(4.0)
        joint.setSpringDamperEnabled(true)
        joint.setSpringDampingRatio(0.5)
        joint.setMaximumSpringTorqueEnabled(true)
        joint.setMaximumSpringTorque(3.0)
        joint.setLimitsEnabled(-0.1, 0.1)

        val copy = joint.copy()
        assertTrue(copy.isSpringEnabled())
        assertEquals(4.0, copy.getSpringFrequency())
        assertTrue(copy.isSpringDamperEnabled())
        assertEquals(0.5, copy.getSpringDampingRatio())
        assertTrue(copy.isMaximumSpringTorqueEnabled())
        assertEquals(3.0, copy.getMaximumSpringTorque())
        assertTrue(copy.isLimitsEnabled())
        assertNotSame(first, copy.getBody1())
    }

fun frictionCapsVelocityImpulseAndNeedsNoPositionSolve() {
        val first = dynamicBody()
        val second = dynamicBody()
        val joint = FrictionJoint(first, second, Vector2())
        joint.setMaximumForce(2.0)
        joint.setMaximumTorque(1.0)
        first.getLinearVelocity().x = 10.0
        first.setAngularVelocity(5.0)
        val step = TimeStep(1.0 / 60.0)
        val settings = Settings()

        joint.initializeConstraints(step, settings)
        joint.solveVelocityConstraints(step, settings)

        assertTrue(joint.solvePositionConstraints(step, settings))
        assertTrue(joint.getReactionForce(60.0).getMagnitude() > 0.0)
        assertTrue(kotlin.math.abs(joint.getReactionTorque(60.0)) > 0.0)
        assertTrue(joint.getReactionForce(60.0).getMagnitude() <= 2.0 + 1e-10)
        assertTrue(kotlin.math.abs(joint.getReactionTorque(60.0)) <= 1.0 + 1e-10)
        assertEquals(2.0, joint.copy().getMaximumForce())
        assertFalse(joint.isCollisionAllowed())
    }

fun revoluteMotorTorqueIsCappedDuringVelocitySolve() {
        val first = dynamicBody()
        val second = dynamicBody()
        val joint = RevoluteJoint(first, second, Vector2())
        joint.setMotorEnabled(true)
        joint.setMotorSpeed(10.0)
        joint.setMaximumMotorTorqueEnabled(true)
        joint.setMaximumMotorTorque(2.0)
        val step = TimeStep(1.0 / 60.0)
        val settings = Settings()

        joint.initializeConstraints(step, settings)
        joint.solveVelocityConstraints(step, settings)

        assertEquals(2.0, kotlin.math.abs(joint.getMotorTorque(60.0)), 1e-10)
        assertTrue(joint.getAngularSpeed() > 0.0)
    }

fun weldSpringTorqueIsCappedDuringVelocitySolve() {
        val first = dynamicBody()
        val second = dynamicBody()
        val joint = WeldJoint(first, second, Vector2())
        joint.setSpringEnabled(true)
        joint.setMaximumSpringTorqueEnabled(true)
        joint.setMaximumSpringTorque(1.0)
        second.rotateAboutCenter(0.3)
        val step = TimeStep(1.0 / 60.0)
        val settings = Settings()

        joint.initializeConstraints(step, settings)
        joint.solveVelocityConstraints(step, settings)

        assertEquals(1.0, kotlin.math.abs(joint.getSpringTorque(60.0)), 1e-10)
        assertTrue(joint.getSpringStiffness() > 0.0)
    }

fun weldSpringUsesSubclassCoefficientOverride() {
        val joint = InstrumentedWeld(dynamicBody(), dynamicBody(), Vector2())
        joint.setSpringEnabled(true)

        joint.initializeConstraints(TimeStep(1.0 / 60.0), Settings())

        assertEquals(1, joint.coefficientUpdates)
        val extension: Joint<Body> = joint
        assertTrue(extension.copy() is InstrumentedWeld)
    }

    private class InstrumentedWeld : WeldJoint<Body> {
        var coefficientUpdates = 0

        constructor(first: Body, second: Body, anchor: Vector2) : super(first, second, anchor)
        private constructor(source: InstrumentedWeld, first: Body?, second: Body?) : super(source, first, second)

        override fun updateSpringCoefficients() {
            coefficientUpdates++
            super.updateSpringCoefficients()
        }

        override fun copy() = InstrumentedWeld(this, null, null)
        override fun copy(body1: Body?, body2: Body?) = InstrumentedWeld(this, body1, body2)
    }
}
