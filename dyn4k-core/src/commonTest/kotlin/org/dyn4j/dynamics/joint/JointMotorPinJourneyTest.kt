package org.dyn4j.dynamics.joint

import de.infix.testBalloon.framework.core.testSuite
import kotlin.math.abs
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotSame
import kotlin.test.assertSame
import kotlin.test.assertTrue
import org.dyn4j.dynamics.Body
import org.dyn4j.dynamics.Settings
import org.dyn4j.dynamics.TimeStep
import org.dyn4j.geometry.Circle
import org.dyn4j.geometry.MassType
import org.dyn4j.geometry.Vector2

val JointMotorPinJourneyTest by testSuite {
    test("motorTargetsWakeBodiesAndStayIndependentAcrossCopies") { JointMotorPinJourneyTestFixture().run { motorTargetsWakeBodiesAndStayIndependentAcrossCopies() } }
    test("motorSolverLimitsLinearForceAndAngularTorque") { JointMotorPinJourneyTestFixture().run { motorSolverLimitsLinearForceAndAngularTorque() } }
    test("pinSwitchesBetweenSpringAndCorrectionWithSeparateForceCaps") { JointMotorPinJourneyTestFixture().run { pinSwitchesBetweenSpringAndCorrectionWithSeparateForceCaps() } }
    test("pinStiffnessModeCanRunWithoutTheSpringForceCap") { JointMotorPinJourneyTestFixture().run { pinStiffnessModeCanRunWithoutTheSpringForceCap() } }
    test("jointSubclassesCanUseProtectedTargetsAndOverrideSolverHooks") { JointMotorPinJourneyTestFixture().run { jointSubclassesCanUseProtectedTargetsAndOverrideSolverHooks() } }
}

private class JointMotorPinJourneyTestFixture  {
fun motorTargetsWakeBodiesAndStayIndependentAcrossCopies() {
        val first = Body()
        val second = Body()
        second.translate(2.0, 1.0)
        val joint = MotorJoint(first, second)
        assertEquals(Vector2(2.0, 1.0), joint.getLinearTarget())
        assertEquals(0.0, joint.getAngularTarget())
        assertEquals(0.3, joint.getCorrectionFactor())

        first.setAtRest(true)
        second.setAtRest(true)
        joint.setLinearTarget(2.0, 1.0)
        assertTrue(first.isAtRest())
        assertTrue(second.isAtRest())
        joint.setLinearTarget(3.0, 1.0)
        assertFalse(first.isAtRest())
        assertFalse(second.isAtRest())

        val copy = joint.copy()
        assertNotSame(first, copy.getBody1())
        assertNotSame(second, copy.getBody2())
        assertNotSame(joint.getLinearTarget(), copy.getLinearTarget())
        assertEquals(joint.getLinearTarget(), copy.getLinearTarget())
        assertSame(first, joint.copy(first, null).getBody1())
    }

fun motorSolverLimitsLinearForceAndAngularTorque() {
        val first = dynamicBody()
        val second = dynamicBody()
        val joint = MotorJoint(first, second)
        joint.setLinearTarget(3.0, 0.0)
        joint.setAngularTarget(1.0)
        joint.setMaximumForce(2.0)
        joint.setMaximumTorque(1.0)
        val step = TimeStep(1.0 / 60.0)
        val settings = Settings()

        joint.initializeConstraints(step, settings)
        joint.solveVelocityConstraints(step, settings)

        assertTrue(joint.solvePositionConstraints(step, settings))
        assertTrue(joint.getReactionForce(60.0).getMagnitude() <= 2.0 + 1e-10)
        assertTrue(abs(joint.getReactionTorque(60.0)) <= 1.0 + 1e-10)
        assertTrue(joint.getReactionForce(60.0).getMagnitude() > 0.0)
    }

fun pinSwitchesBetweenSpringAndCorrectionWithSeparateForceCaps() {
        val body = dynamicBody()
        val joint = PinJoint(body, Vector2())
        assertTrue(joint.isSpringEnabled())
        assertEquals(Joint.SPRING_MODE_FREQUENCY, joint.getSpringMode())
        assertEquals(8.0, joint.getSpringFrequency())
        joint.setTarget(2.0, 0.0)
        joint.setMaximumSpringForce(2.0)
        val step = TimeStep(1.0 / 60.0)
        val settings = Settings()

        joint.initializeConstraints(step, settings)
        joint.solveVelocityConstraints(step, settings)
        assertTrue(joint.getSpringForce(60.0) > 0.0)
        assertTrue(joint.getSpringForce(60.0) <= 2.0 + 1e-10)
        assertEquals(0.0, joint.getCorrectionForce(60.0))

        joint.setSpringEnabled(false)
        joint.setMaximumCorrectionForce(1.0)
        joint.initializeConstraints(step, settings)
        joint.solveVelocityConstraints(step, settings)
        assertEquals(0.0, joint.getSpringForce(60.0))
        assertTrue(joint.getCorrectionForce(60.0) <= 1.0 + 1e-10)
        assertTrue(joint.solvePositionConstraints(step, settings))
        assertEquals(0.0, joint.getReactionTorque(60.0))

        joint.shift(Vector2(1.0, 0.0))
        assertEquals(Vector2(3.0, 0.0), joint.getTarget())
        val copy = joint.copy()
        assertNotSame(body, copy.getBody())
        assertNotSame(joint.getTarget(), copy.getTarget())
        assertFalse(copy.isSpringEnabled())
    }

fun pinStiffnessModeCanRunWithoutTheSpringForceCap() {
        val body = dynamicBody()
        val joint = PinJoint(body, Vector2())
        joint.setSpringEnabled(false)
        body.setAtRest(true)
        joint.setSpringStiffness(1000.0)
        assertEquals(Joint.SPRING_MODE_STIFFNESS, joint.getSpringMode())
        assertTrue(body.isAtRest())

        joint.setSpringEnabled(true)
        assertFalse(body.isAtRest())
        joint.setSpringDamperEnabled(false)
        joint.setMaximumSpringForceEnabled(false)
        joint.setMaximumSpringForce(0.01)
        joint.setTarget(5.0, 0.0)
        val step = TimeStep(1.0 / 60.0)
        val settings = Settings()
        joint.initializeConstraints(step, settings)
        joint.solveVelocityConstraints(step, settings)

        assertEquals(1000.0, joint.getSpringStiffness())
        assertTrue(joint.getSpringFrequency() > 0.0)
        assertTrue(joint.getSpringForce(60.0) > joint.getMaximumSpringForce())
    }

fun jointSubclassesCanUseProtectedTargetsAndOverrideSolverHooks() {
        val first = dynamicBody()
        val second = dynamicBody()
        val motor = TrackingMotor(first, second)
        assertSame(motor.getLinearTarget(), motor.protectedTarget())
        val joint: Joint<Body> = motor
        assertEquals(Vector2(7.0, 8.0), joint.getReactionForce(60.0))

        val pin = TrackingPin(dynamicBody())
        pin.initializeConstraints(TimeStep(1.0 / 60.0), Settings())
        assertEquals(1, pin.coefficientUpdates)
        assertEquals(pin.getSpringStiffness(), pin.protectedStiffness())
    }

    private class TrackingMotor(first: Body, second: Body) : MotorJoint<Body>(first, second) {
        fun protectedTarget(): Vector2 = linearTarget
        override fun getReactionForce(invdt: Double) = Vector2(7.0, 8.0)
    }

    private class TrackingPin(body: Body) : PinJoint<Body>(body, Vector2()) {
        var coefficientUpdates = 0
        fun protectedStiffness(): Double = springStiffness
        override fun updateSpringCoefficients() {
            coefficientUpdates++
            super.updateSpringCoefficients()
        }
    }

    private fun dynamicBody() = Body().also {
        it.addFixture(Circle(1.0))
        it.setMass(MassType.NORMAL)
    }
}
