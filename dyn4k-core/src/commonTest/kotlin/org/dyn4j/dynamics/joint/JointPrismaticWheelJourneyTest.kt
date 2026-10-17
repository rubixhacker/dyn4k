package org.dyn4j.dynamics.joint

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import kotlin.math.abs
import org.dyn4j.dynamics.Body
import org.dyn4j.dynamics.Settings
import org.dyn4j.dynamics.TimeStep
import org.dyn4j.geometry.Circle
import org.dyn4j.geometry.MassType
import org.dyn4j.geometry.Vector2

class JointPrismaticWheelJourneyTest {
    private fun movingBody() = Body().apply {
        addFixture(Circle(0.5))
        setMass(MassType.NORMAL)
    }

    @Test
    fun prismaticMotorMovesAlongItsAxis() {
        val frame = Body()
        val slider = movingBody()
        val joint = PrismaticJoint(frame, slider, Vector2(), Vector2(2.0, 0.0))
        joint.setMotorEnabled(true)
        joint.setMotorSpeed(2.0)
        val step = TimeStep(1.0 / 60.0)
        val settings = Settings()

        joint.initializeConstraints(step, settings)
        joint.solveVelocityConstraints(step, settings)

        assertTrue(slider.getLinearVelocity().x > 0.0)
        assertEquals(0.0, slider.getLinearVelocity().y, 1.0e-12)
        assertTrue(joint.getMotorForce(step.getInverseDeltaTime()) > 0.0)
        assertEquals(1.0, joint.getAxis().x, 1.0e-12)
    }

    @Test
    fun wheelMotorRotatesWheelAndSpringIsEnabledByDefault() {
        val frame = Body()
        val wheel = movingBody()
        val joint = WheelJoint(frame, wheel, Vector2(), Vector2(0.0, 3.0))
        assertTrue(joint.isSpringEnabled())
        joint.setMotorEnabled(true)
        joint.setMotorSpeed(3.0)
        val step = TimeStep(1.0 / 60.0)

        joint.initializeConstraints(step, Settings())
        joint.solveVelocityConstraints(step, Settings())

        assertTrue(wheel.getAngularVelocity() > 0.0)
        assertTrue(joint.getMotorTorque(step.getInverseDeltaTime()) > 0.0)
        assertEquals(1.0, joint.getAxis().y, 1.0e-12)
    }

    @Test
    fun prismaticLimitCorrectsDisplacementAndCappedMotorStopsAtForceLimit() {
        val frame = Body()
        val slider = movingBody()
        val joint = PrismaticJoint(frame, slider, Vector2(), Vector2(1.0, 0.0))
        joint.setLimitsEnabled(0.0)
        slider.translate(0.5, 0.0)
        assertTrue(joint.getLinearTranslation() > 0.0)
        joint.solvePositionConstraints(TimeStep(1.0 / 60.0), Settings())
        assertEquals(0.0, joint.getLinearTranslation(), 1.0e-9)

        joint.setLimitsEnabled(false)
        joint.setMotorEnabled(true)
        joint.setMotorSpeed(10.0)
        joint.setMaximumMotorForceEnabled(true)
        joint.setMaximumMotorForce(0.5)
        val step = TimeStep(1.0 / 60.0)
        joint.initializeConstraints(step, Settings())
        joint.solveVelocityConstraints(step, Settings())
        assertEquals(0.5, joint.getMotorForce(step.getInverseDeltaTime()), 1.0e-9)
    }

    @Test
    fun wheelLimitCorrectsDisplacementAndCappedMotorStopsAtTorqueLimit() {
        val frame = Body()
        val wheel = movingBody()
        val joint = WheelJoint(frame, wheel, Vector2(), Vector2(0.0, 1.0))
        joint.setSpringEnabled(false)
        joint.setLimitsEnabled(0.0)
        wheel.translate(0.0, 0.5)
        joint.solvePositionConstraints(TimeStep(1.0 / 60.0), Settings())
        assertEquals(0.0, joint.getLinearTranslation(), 1.0e-9)

        joint.setLimitsEnabled(false)
        joint.setMotorEnabled(true)
        joint.setMotorSpeed(10.0)
        joint.setMaximumMotorTorqueEnabled(true)
        joint.setMaximumMotorTorque(0.5)
        val step = TimeStep(1.0 / 60.0)
        joint.initializeConstraints(step, Settings())
        joint.solveVelocityConstraints(step, Settings())
        assertEquals(0.5, joint.getMotorTorque(step.getInverseDeltaTime()), 1.0e-9)
    }

    @Test
    fun springModesAndCopiesRetainConfiguredBehavior() {
        val frame = Body()
        val moving = movingBody()
        val prismatic = PrismaticJoint(frame, moving, Vector2(), Vector2(1.0, 0.0))
        val wheel = WheelJoint(frame, moving, Vector2(), Vector2(1.0, 0.0))
        prismatic.setSpringEnabled(true)
        prismatic.setSpringDamperEnabled(true)
        prismatic.setSpringStiffness(10.0)
        prismatic.setSpringRestOffset(1.0)
        prismatic.setMaximumSpringForceEnabled(true)
        prismatic.setMaximumSpringForce(0.25)
        wheel.setSpringStiffness(10.0)
        wheel.setSpringRestOffset(1.0)
        wheel.setMaximumSpringForceEnabled(true)
        wheel.setMaximumSpringForce(0.25)
        val step = TimeStep(1.0 / 60.0)
        val settings = Settings()

        prismatic.initializeConstraints(step, settings)
        prismatic.solveVelocityConstraints(step, settings)
        wheel.initializeConstraints(step, settings)
        wheel.solveVelocityConstraints(step, settings)

        assertTrue(abs(prismatic.getSpringForce(step.getInverseDeltaTime())) > 0.0)
        assertTrue(abs(wheel.getSpringForce(step.getInverseDeltaTime())) > 0.0)
        assertTrue(abs(prismatic.getSpringForce(step.getInverseDeltaTime())) <= 0.25 + 1.0e-12)
        assertTrue(abs(wheel.getSpringForce(step.getInverseDeltaTime())) <= 0.25 + 1.0e-12)
        assertEquals(Joint.SPRING_MODE_STIFFNESS, prismatic.copy().getSpringMode())
        assertEquals(Joint.SPRING_MODE_STIFFNESS, wheel.copy().getSpringMode())
        assertFalse(prismatic.copy().getBody1() === frame)
        assertFalse(wheel.copy().getBody2() === moving)
    }

    @Test
    fun subclassSpringCoefficientOverridesRunDuringConstraintSetup() {
        val frame = Body()
        val moving = movingBody()
        val prismatic = PrismaticProbe(frame, moving)
        val wheel = WheelProbe(frame, moving)
        prismatic.setSpringEnabled(true)
        val step = TimeStep(1.0 / 60.0)

        prismatic.initializeConstraints(step, Settings())
        wheel.initializeConstraints(step, Settings())

        assertEquals(1, prismatic.updates)
        assertEquals(1, wheel.updates)
        assertEquals(Vector2(), prismatic.localAnchorCopy())
        assertEquals(Vector2(), wheel.localAnchorCopy())
    }

    private class PrismaticProbe(frame: Body, slider: Body) :
        PrismaticJoint<Body>(frame, slider, Vector2(), Vector2(1.0, 0.0)) {
        var updates = 0
        override fun updateSpringCoefficients() {
            updates++
            super.updateSpringCoefficients()
        }
        fun localAnchorCopy() = localAnchor1.copy()
    }

    private class WheelProbe(frame: Body, wheel: Body) :
        WheelJoint<Body>(frame, wheel, Vector2(), Vector2(1.0, 0.0)) {
        var updates = 0
        override fun updateSpringCoefficients() {
            updates++
            super.updateSpringCoefficients()
        }
        fun localAnchorCopy() = localAnchor1.copy()
    }
}
