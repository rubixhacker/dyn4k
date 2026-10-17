package org.dyn4j.dynamics.joint

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue
import org.dyn4j.dynamics.Body
import org.dyn4j.dynamics.Settings
import org.dyn4j.dynamics.TimeStep
import org.dyn4j.geometry.Geometry
import org.dyn4j.geometry.MassType
import org.dyn4j.geometry.Vector2

class JointDistanceAnglePulleyJourneyTest {
    @Test
    fun angleJointLocksRotationAndAllowsRatioMotion() {
        val first = dynamicBody()
        val second = dynamicBody()
        val joint = AngleJoint(first, second)
        assertTrue(joint.isLimitsEnabled())
        assertEquals(0.0, joint.getAngularTranslation())
        joint.setLimitsEnabled(false)
        joint.setRatio(2.0)
        assertFailsWith<IllegalArgumentException> { joint.setRatio(0.0) }
        first.setAngularVelocity(4.0)
        second.setAngularVelocity(0.0)
        val step = TimeStep(1.0 / 60.0)
        val settings = Settings()
        joint.initializeConstraints(step, settings)
        joint.solveVelocityConstraints(step, settings)
        assertEquals(2.0, joint.getRatio())
        assertEquals(2.0 * first.getAngularVelocity(), second.getAngularVelocity(), 1e-12)
    }

    @Test
    fun distanceJointKeepsConfiguredSpringAndLimits() {
        val first = dynamicBody()
        val second = dynamicBody()
        second.translate(2.0, 0.0)
        val joint = DistanceJoint(first, second, Vector2(), Vector2(2.0, 0.0))
        assertEquals(2.0, joint.getRestDistance())
        joint.setSpringEnabled(true)
        joint.setSpringFrequency(4.0)
        joint.setSpringDamperEnabled(true)
        joint.setSpringDampingRatio(0.5)
        joint.setLimitsEnabled(1.0, 3.0)
        assertTrue(joint.isSpringEnabled())
        assertEquals(4.0, joint.getSpringFrequency())
        assertTrue(joint.isLowerLimitEnabled())
        assertTrue(joint.isUpperLimitEnabled())
        assertEquals(2.0, joint.getCurrentDistance(), 1e-12)
        joint.setSpringEnabled(false)
        joint.setLimitsEnabled(false)
        joint.setRestDistance(1.0)
        val step = TimeStep(1.0 / 60.0)
        val settings = Settings()
        joint.initializeConstraints(step, settings)
        joint.solvePositionConstraints(step, settings)
        assertEquals(1.0, joint.getCurrentDistance(), 1e-12)
    }

    @Test
    fun pulleyJointUsesRatioAndTracksRopeLength() {
        val first = dynamicBody()
        val second = dynamicBody()
        val joint = PulleyJoint(first, second, Vector2(-2.0, 2.0), Vector2(2.0, 2.0), Vector2(-2.0, 0.0), Vector2(2.0, 0.0))
        assertEquals(4.0, joint.getLength())
        joint.setRatio(2.0)
        assertEquals(2.0, joint.getRatio())
        joint.setSlackEnabled(true)
        assertTrue(joint.isSlackEnabled())
        assertEquals(4.0, joint.getLength())
        assertFailsWith<IllegalArgumentException> { joint.setRatio(0.0) }
        joint.shift(Vector2(1.0, 0.0))
        assertEquals(-1.0, joint.getPulleyAnchor1().x)
        assertEquals(3.0, joint.getPulleyAnchor2().x)
        assertEquals(4.0, joint.copy(first, second).getLength())
    }

    private fun dynamicBody() = Body().apply {
        addFixture(Geometry.createCircle(0.5), 1.0, 0.2, 0.0)
        setMass(MassType.NORMAL)
    }
}
