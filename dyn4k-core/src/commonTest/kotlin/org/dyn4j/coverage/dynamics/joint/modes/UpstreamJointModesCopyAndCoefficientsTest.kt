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
package org.dyn4j.coverage.dynamics.joint.modes

import kotlin.math.abs
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotSame
import kotlin.test.assertNull
import kotlin.test.assertSame
import kotlin.test.assertTrue
import org.dyn4j.dynamics.Body
import org.dyn4j.dynamics.Settings
import org.dyn4j.dynamics.TimeStep
import org.dyn4j.dynamics.joint.AngleJoint
import org.dyn4j.dynamics.joint.FrictionJoint
import org.dyn4j.dynamics.joint.Joint
import org.dyn4j.dynamics.joint.MotorJoint
import org.dyn4j.dynamics.joint.PinJoint
import org.dyn4j.dynamics.joint.PulleyJoint
import org.dyn4j.dynamics.joint.WeldJoint
import org.dyn4j.dynamics.joint.WheelJoint
import org.dyn4j.geometry.Geometry
import org.dyn4j.geometry.MassType
import org.dyn4j.geometry.Vector2

private fun copyBody() = Body().apply {
    addFixture(Geometry.createCircle(1.0), 1.0, 0.2, 0.0)
    setMass(MassType.NORMAL)
}

private fun checkCopiedImpulse(joint: Joint<Body>, first: Body, second: Body?) {
    first.setLinearVelocity(2.0, 1.0)
    first.setAngularVelocity(2.0)
    second?.setLinearVelocity(-1.0, -2.0)
    second?.setAngularVelocity(-1.0)
    val step = TimeStep(1.0 / 60.0)
    val settings = Settings()
    joint.initializeConstraints(step, settings)
    repeat(3) { joint.solveVelocityConstraints(step, settings) }
    val sourceForce = joint.getReactionForce(60.0)
    val sourceTorque = joint.getReactionTorque(60.0)
    assertTrue(sourceForce.getMagnitude() > 1e-9 || abs(sourceTorque) > 1e-9)
    val copy = joint.copy()
    assertEquals(sourceForce, copy.getReactionForce(60.0))
    assertEquals(sourceTorque, copy.getReactionTorque(60.0))
}

private class PinCoefficientProbe(body: Body) : PinJoint<Body>(body, Vector2()) {
    fun update() = updateSpringCoefficients()
}

private class WeldCoefficientProbe(first: Body, second: Body) :
    WeldJoint<Body>(first, second, Vector2()) {
    fun update() = updateSpringCoefficients()
}

private class WheelCoefficientProbe(first: Body, second: Body) :
    WheelJoint<Body>(first, second, Vector2(1.0, 2.0), Vector2(-3.0, 0.5)) {
    fun update() = updateSpringCoefficients()
}

class UpstreamJointModesCopyAndCoefficientsTest {
    @Test fun angleCopy() {
        val first = copyBody()
        val second = copyBody()
        val joint = AngleJoint(first, second)
        joint.setOwner(Any())
        joint.setUserData(Any())
        joint.setCollisionAllowed(true)
        joint.setRatio(1.5)
        joint.setLimitsEnabled(-0.5, 0.7)
        checkCopiedImpulse(joint, first, second)
        val copy = joint.copy()
        assertNotSame(joint, copy)
        assertNotSame(first, copy.getBody1())
        assertNotSame(second, copy.getBody2())
        assertEquals(1.5, copy.getRatio())
        assertEquals(-0.5, copy.getLowerLimit())
        assertEquals(0.7, copy.getUpperLimit())
        assertTrue(copy.isLimitsEnabled())
        assertEquals(joint.isCollisionAllowed(), copy.isCollisionAllowed())
        assertNull(copy.getOwner())
        assertNull(copy.getUserData())
        assertSame(first, joint.copy(first, second).getBody1())
        assertNotSame(second, joint.copy(first, null).getBody2())
        assertSame(second, joint.copy(null, second).getBody2())
    }

    @Test fun frictionCopy() {
        val first = copyBody()
        val second = copyBody()
        val joint = FrictionJoint(first, second, Vector2(1.0, 1.0))
        joint.setOwner(Any())
        joint.setUserData(Any())
        joint.setCollisionAllowed(true)
        joint.setMaximumForce(5.0)
        joint.setMaximumTorque(9.0)
        checkCopiedImpulse(joint, first, second)
        val copy = joint.copy()
        assertNotSame(joint, copy)
        assertNotSame(first, copy.getBody1())
        assertNotSame(second, copy.getBody2())
        assertEquals(Vector2(1.0, 1.0), copy.getAnchor1())
        assertEquals(Vector2(1.0, 1.0), copy.getAnchor2())
        assertEquals(5.0, copy.getMaximumForce())
        assertEquals(9.0, copy.getMaximumTorque())
        assertTrue(copy.isCollisionAllowed())
        assertNull(copy.getOwner())
        assertNull(copy.getUserData())
        assertSame(first, joint.copy(first, second).getBody1())
        assertNotSame(second, joint.copy(first, null).getBody2())
        assertSame(second, joint.copy(null, second).getBody2())
    }

    @Test fun motorCopy() {
        val first = copyBody()
        val second = copyBody()
        val joint = MotorJoint(first, second)
        joint.setOwner(Any())
        joint.setUserData(Any())
        joint.setCollisionAllowed(true)
        joint.setLinearTarget(3.0, 4.0)
        joint.setAngularTarget(0.7)
        joint.setCorrectionFactor(0.1)
        joint.setMaximumForce(5.0)
        joint.setMaximumTorque(9.0)
        checkCopiedImpulse(joint, first, second)
        val copy = joint.copy()
        assertNotSame(first, copy.getBody1())
        assertNotSame(second, copy.getBody2())
        assertNotSame(joint.getLinearTarget(), copy.getLinearTarget())
        assertEquals(Vector2(3.0, 4.0), copy.getLinearTarget())
        assertEquals(0.7, copy.getAngularTarget())
        assertEquals(0.1, copy.getCorrectionFactor())
        assertEquals(5.0, copy.getMaximumForce())
        assertEquals(9.0, copy.getMaximumTorque())
        assertTrue(copy.isCollisionAllowed())
        assertNull(copy.getOwner())
        assertNull(copy.getUserData())
        assertSame(first, joint.copy(first, second).getBody1())
        assertNotSame(second, joint.copy(first, null).getBody2())
        assertSame(second, joint.copy(null, second).getBody2())
    }

    @Test fun pinCopy() {
        val body = copyBody()
        val joint = PinJoint(body, Vector2())
        joint.setOwner(Any())
        joint.setUserData(Any())
        joint.setCollisionAllowed(true)
        joint.setTarget(3.0, 4.0)
        joint.setSpringEnabled(false)
        joint.setSpringDampingRatio(0.5)
        joint.setMaximumSpringForce(5.0)
        joint.setCorrectionFactor(0.7)
        joint.setMaximumCorrectionForce(9.0)
        checkCopiedImpulse(joint, body, null)
        val copy = joint.copy()
        assertNotSame(body, copy.getBody())
        assertNotSame(joint.getTarget(), copy.getTarget())
        assertEquals(Vector2(3.0, 4.0), copy.getTarget())
        assertFalse(copy.isSpringEnabled())
        assertEquals(0.5, copy.getSpringDampingRatio())
        assertEquals(5.0, copy.getMaximumSpringForce())
        assertEquals(0.7, copy.getCorrectionFactor())
        assertEquals(9.0, copy.getMaximumCorrectionForce())
        assertEquals(joint.isCollisionAllowed(), copy.isCollisionAllowed())
        assertNull(copy.getOwner())
        assertNull(copy.getUserData())
        assertSame(body, joint.copy(body).getBody())
    }

    @Test fun pulleyCopy() {
        val first = copyBody()
        val second = copyBody()
        val joint = PulleyJoint(first, second, Vector2(-2.0, 2.0), Vector2(2.0, 2.0), Vector2(-2.0, 0.0), Vector2(2.0, 0.0))
        joint.setOwner(Any())
        joint.setUserData(Any())
        joint.setCollisionAllowed(true)
        joint.setRatio(1.5)
        checkCopiedImpulse(joint, first, second)
        joint.setLength(5.0)
        joint.setSlackEnabled(true)
        val copy = joint.copy()
        assertNotSame(first, copy.getBody1())
        assertNotSame(second, copy.getBody2())
        assertNotSame(joint.getPulleyAnchor1(), copy.getPulleyAnchor1())
        assertNotSame(joint.getPulleyAnchor2(), copy.getPulleyAnchor2())
        assertEquals(Vector2(-2.0, 2.0), copy.getPulleyAnchor1())
        assertEquals(Vector2(2.0, 2.0), copy.getPulleyAnchor2())
        assertEquals(1.5, copy.getRatio())
        assertEquals(5.0, copy.getLength())
        assertTrue(copy.isSlackEnabled())
        assertTrue(copy.isCollisionAllowed())
        assertNull(copy.getOwner())
        assertNull(copy.getUserData())
        assertSame(first, joint.copy(first, second).getBody1())
        assertNotSame(second, joint.copy(first, null).getBody2())
        assertSame(second, joint.copy(null, second).getBody2())
    }

    @Test fun weldCopy() {
        val first = copyBody()
        val second = copyBody()
        val joint = WeldJoint(first, second, Vector2(1.0, 1.0))
        joint.setOwner(Any())
        joint.setUserData(Any())
        joint.setCollisionAllowed(true)
        joint.setSpringEnabled(true)
        joint.setSpringFrequency(8.0)
        joint.setSpringDampingRatio(0.5)
        joint.setMaximumSpringTorque(5.0)
        joint.setLimitsEnabled(-0.5, 0.7)
        checkCopiedImpulse(joint, first, second)
        val copy = joint.copy()
        assertNotSame(first, copy.getBody1())
        assertNotSame(second, copy.getBody2())
        assertEquals(Vector2(1.0, 1.0), copy.getAnchor1())
        assertEquals(8.0, copy.getSpringFrequency())
        assertEquals(0.5, copy.getSpringDampingRatio())
        assertEquals(5.0, copy.getMaximumSpringTorque())
        assertEquals(-0.5, copy.getLowerLimit())
        assertEquals(0.7, copy.getUpperLimit())
        assertTrue(copy.isLimitsEnabled())
        assertTrue(copy.isCollisionAllowed())
        assertNull(copy.getOwner())
        assertNull(copy.getUserData())
        assertSame(first, joint.copy(first, second).getBody1())
        assertNotSame(second, joint.copy(first, null).getBody2())
        assertSame(second, joint.copy(null, second).getBody2())
    }

    @Test fun wheelCopy() {
        val first = copyBody()
        val second = copyBody()
        val joint = WheelJoint(first, second, Vector2(1.0, 2.0), Vector2(-3.0, 0.5))
        joint.setOwner(Any())
        joint.setUserData(Any())
        joint.setCollisionAllowed(true)
        joint.setSpringEnabled(true)
        joint.setSpringFrequency(8.0)
        joint.setSpringDampingRatio(0.5)
        joint.setSpringRestOffset(0.2)
        joint.setMaximumSpringForce(5.0)
        joint.setMotorEnabled(true)
        joint.setMotorSpeed(2.0)
        joint.setMaximumMotorTorque(9.0)
        joint.setLimitsEnabled(-0.5, 0.7)
        checkCopiedImpulse(joint, first, second)
        val copy = joint.copy()
        assertNotSame(first, copy.getBody1())
        assertNotSame(second, copy.getBody2())
        assertEquals(Vector2(1.0, 2.0), copy.getAnchor1())
        assertEquals(8.0, copy.getSpringFrequency())
        assertEquals(0.5, copy.getSpringDampingRatio())
        assertEquals(0.2, copy.getSpringRestOffset())
        assertEquals(5.0, copy.getMaximumSpringForce())
        assertTrue(copy.isMotorEnabled())
        assertEquals(2.0, copy.getMotorSpeed())
        assertEquals(9.0, copy.getMaximumMotorTorque())
        assertEquals(-0.5, copy.getLowerLimit())
        assertEquals(0.7, copy.getUpperLimit())
        assertTrue(copy.isCollisionAllowed())
        assertNull(copy.getOwner())
        assertNull(copy.getUserData())
        assertSame(first, joint.copy(first, second).getBody1())
        assertNotSame(second, joint.copy(first, null).getBody2())
        assertSame(second, joint.copy(null, second).getBody2())
    }

    @Test fun pinComputeSpringStiffnessFrequency() {
        val joint = PinCoefficientProbe(copyBody())
        joint.setSpringEnabled(true)
        joint.setSpringDamperEnabled(true)
        joint.setSpringFrequency(8.0)
        joint.setSpringDampingRatio(0.5)
        joint.update()
        assertEquals(Joint.SPRING_MODE_FREQUENCY, joint.getSpringMode())
        assertEquals(8.0, joint.getSpringFrequency())
        assertEquals(0.5, joint.getSpringDampingRatio())
        assertEquals(7937.606, joint.getSpringStiffness(), 1e-3)
        joint.setSpringStiffness(1000.0)
        joint.update()
        assertEquals(Joint.SPRING_MODE_STIFFNESS, joint.getSpringMode())
        assertEquals(2.839, joint.getSpringFrequency(), 1e-3)
        assertEquals(0.5, joint.getSpringDampingRatio())
        assertEquals(1000.0, joint.getSpringStiffness(), 1e-3)
    }

    @Test fun weldComputeSpringStiffnessFrequency() {
        val joint = WeldCoefficientProbe(copyBody(), copyBody())
        joint.setSpringEnabled(true)
        joint.setSpringDamperEnabled(true)
        joint.setSpringFrequency(8.0)
        joint.setSpringDampingRatio(0.5)
        joint.update()
        assertEquals(Joint.SPRING_MODE_FREQUENCY, joint.getSpringMode())
        assertEquals(8.0, joint.getSpringFrequency())
        assertEquals(0.5, joint.getSpringDampingRatio())
        assertEquals(1984.401, joint.getSpringStiffness(), 1e-3)
        joint.setSpringStiffness(1000.0)
        joint.update()
        assertEquals(Joint.SPRING_MODE_STIFFNESS, joint.getSpringMode())
        assertEquals(5.679, joint.getSpringFrequency(), 1e-3)
        assertEquals(0.5, joint.getSpringDampingRatio())
        assertEquals(1000.0, joint.getSpringStiffness(), 1e-3)
    }

    @Test fun wheelComputeSpringStiffnessFrequency() {
        val joint = WheelCoefficientProbe(copyBody(), copyBody())
        joint.setSpringEnabled(true)
        joint.setSpringDamperEnabled(true)
        joint.setSpringFrequency(8.0)
        joint.setSpringDampingRatio(0.5)
        joint.update()
        assertEquals(Joint.SPRING_MODE_FREQUENCY, joint.getSpringMode())
        assertEquals(8.0, joint.getSpringFrequency())
        assertEquals(0.5, joint.getSpringDampingRatio())
        assertEquals(3968.803, joint.getSpringStiffness(), 1e-3)
        joint.setSpringStiffness(1000.0)
        joint.update()
        assertEquals(Joint.SPRING_MODE_STIFFNESS, joint.getSpringMode())
        assertEquals(4.015, joint.getSpringFrequency(), 1e-3)
        assertEquals(0.5, joint.getSpringDampingRatio())
        assertEquals(1000.0, joint.getSpringStiffness(), 1e-3)
    }
}
