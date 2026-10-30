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

import de.infix.testBalloon.framework.core.testSuite
import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.sqrt
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertFailsWith
import kotlin.test.assertNotNull
import kotlin.test.assertNotSame
import kotlin.test.assertNull
import kotlin.test.assertSame
import kotlin.test.assertTrue
import org.dyn4j.dynamics.Body
import org.dyn4j.dynamics.joint.*
import org.dyn4j.geometry.Geometry
import org.dyn4j.geometry.MassType
import org.dyn4j.geometry.Vector2

val UpstreamWheelJointModesCoverageTest by testSuite {
    test("createSuccess") { UpstreamWheelJointModesCoverageTestFixture().run { createSuccess() } }
    test("createWithNullBody1") { UpstreamWheelJointModesCoverageTestFixture().run { createWithNullBody1() } }
    test("createWithNullBody2") { UpstreamWheelJointModesCoverageTestFixture().run { createWithNullBody2() } }
    test("createWithNullAnchor") { UpstreamWheelJointModesCoverageTestFixture().run { createWithNullAnchor() } }
    test("createWithNullAxis") { UpstreamWheelJointModesCoverageTestFixture().run { createWithNullAxis() } }
    test("isSpringEnabled") { UpstreamWheelJointModesCoverageTestFixture().run { isSpringEnabled() } }
    test("isSpringDamperEnabled") { UpstreamWheelJointModesCoverageTestFixture().run { isSpringDamperEnabled() } }
    test("setSpringRestOffset") { UpstreamWheelJointModesCoverageTestFixture().run { setSpringRestOffset() } }
    test("setSpringDampingRatio") { UpstreamWheelJointModesCoverageTestFixture().run { setSpringDampingRatio() } }
    test("setNegativeDampingRatio") { UpstreamWheelJointModesCoverageTestFixture().run { setNegativeDampingRatio() } }
    test("setDampingRatioGreaterThan1") { UpstreamWheelJointModesCoverageTestFixture().run { setDampingRatioGreaterThan1() } }
    test("setSpringFrequency") { UpstreamWheelJointModesCoverageTestFixture().run { setSpringFrequency() } }
    test("setSpringMode") { UpstreamWheelJointModesCoverageTestFixture().run { setSpringMode() } }
    test("setSpringStiffnessNegative") { UpstreamWheelJointModesCoverageTestFixture().run { setSpringStiffnessNegative() } }
    test("setSpringStiffness") { UpstreamWheelJointModesCoverageTestFixture().run { setSpringStiffness() } }
    test("setSpringFrequencyNegative") { UpstreamWheelJointModesCoverageTestFixture().run { setSpringFrequencyNegative() } }
    test("setSpringMaximumForceNegative") { UpstreamWheelJointModesCoverageTestFixture().run { setSpringMaximumForceNegative() } }
    test("setSpringMaximumForce") { UpstreamWheelJointModesCoverageTestFixture().run { setSpringMaximumForce() } }
    test("setSpringRestOffsetAtRest") { UpstreamWheelJointModesCoverageTestFixture().run { setSpringRestOffsetAtRest() } }
    test("setMotorMaximumTorque") { UpstreamWheelJointModesCoverageTestFixture().run { setMotorMaximumTorque() } }
    test("setMaximumMotorTorqueNegative") { UpstreamWheelJointModesCoverageTestFixture().run { setMaximumMotorTorqueNegative() } }
    test("setMaximumMotorTorqueSleep") { UpstreamWheelJointModesCoverageTestFixture().run { setMaximumMotorTorqueSleep() } }
    test("setMaximumMotorTorqueEnabledSleep") { UpstreamWheelJointModesCoverageTestFixture().run { setMaximumMotorTorqueEnabledSleep() } }
    test("setMotorEnabled") { UpstreamWheelJointModesCoverageTestFixture().run { setMotorEnabled() } }
    test("setMotorEnabledSleep") { UpstreamWheelJointModesCoverageTestFixture().run { setMotorEnabledSleep() } }
    test("setMotorSpeed") { UpstreamWheelJointModesCoverageTestFixture().run { setMotorSpeed() } }
    test("setMotorSpeedSleep") { UpstreamWheelJointModesCoverageTestFixture().run { setMotorSpeedSleep() } }
    test("setUpperLimitSuccess") { UpstreamWheelJointModesCoverageTestFixture().run { setUpperLimitSuccess() } }
    test("setUpperLimitInvalid") { UpstreamWheelJointModesCoverageTestFixture().run { setUpperLimitInvalid() } }
    test("setLowerLimit") { UpstreamWheelJointModesCoverageTestFixture().run { setLowerLimit() } }
    test("setLowerLimitInvalid") { UpstreamWheelJointModesCoverageTestFixture().run { setLowerLimitInvalid() } }
    test("setUpperAndLowerLimits") { UpstreamWheelJointModesCoverageTestFixture().run { setUpperAndLowerLimits() } }
    test("setUpperAndLowerLimitsInvalid1") { UpstreamWheelJointModesCoverageTestFixture().run { setUpperAndLowerLimitsInvalid1() } }
    test("setUpperAndLowerLimitsInvalid2") { UpstreamWheelJointModesCoverageTestFixture().run { setUpperAndLowerLimitsInvalid2() } }
    test("setSameLimitValid") { UpstreamWheelJointModesCoverageTestFixture().run { setSameLimitValid() } }
    test("setLimitsEnabledSleep") { UpstreamWheelJointModesCoverageTestFixture().run { setLimitsEnabledSleep() } }
    test("setLimitsSameSleep") { UpstreamWheelJointModesCoverageTestFixture().run { setLimitsSameSleep() } }
    test("setLimitsDifferentSleep") { UpstreamWheelJointModesCoverageTestFixture().run { setLimitsDifferentSleep() } }
    test("setLowerLimitSleep") { UpstreamWheelJointModesCoverageTestFixture().run { setLowerLimitSleep() } }
    test("setUpperLimitSleep") { UpstreamWheelJointModesCoverageTestFixture().run { setUpperLimitSleep() } }
    test("setLimitsEnabledSameSleep") { UpstreamWheelJointModesCoverageTestFixture().run { setLimitsEnabledSameSleep() } }
    test("setLimitsEnabledDifferentSleep") { UpstreamWheelJointModesCoverageTestFixture().run { setLimitsEnabledDifferentSleep() } }
    test("shift") { UpstreamWheelJointModesCoverageTestFixture().run { shift() } }
    test("copyFailed") { UpstreamWheelJointModesCoverageTestFixture().run { copyFailed() } }
}

private fun wheelBody() = Body().apply {
    addFixture(Geometry.createCircle(1.0), 1.0, 0.2, 0.0)
    setMass(MassType.NORMAL)
}

private fun wheelRadians(degrees: Double) = degrees * PI / 180.0

private class WheelTestBody : Body()

private class UpstreamWheelJointModesCoverageTestFixture  {
fun createSuccess() {
        val b1 = wheelBody()
        val b2 = wheelBody()
        var p = Vector2(1.0, 1.0)
        var a = Vector2(0.0, 1.0)
        var wj = WheelJoint<Body>(b1, b2, p, a)
        assertEquals(p, wj.getAnchor1())
        assertEquals(p, wj.getAnchor2())
        assertNotSame(p, wj.getAnchor1())
        assertNotSame(p, wj.getAnchor2())
        assertEquals(a, wj.getAxis())
        assertEquals(0.0, wj.getAngularSpeed())
        assertEquals(0.0, wj.getAngularTranslation())
        assertEquals(0.0, wj.getLinearSpeed())
        assertEquals(0.0, wj.getLinearTranslation())
        assertEquals(0.3, wj.getSpringDampingRatio())
        assertEquals(8.0, wj.getSpringFrequency())
        assertEquals(0.0, wj.getSpringStiffness())
        assertEquals(1000.0, wj.getMaximumSpringForce())
        assertEquals(0.0, wj.getSpringRestOffset())
        assertEquals(0.0, wj.getLowerLimit())
        assertEquals(0.0, wj.getUpperLimit())
        assertEquals(1000.0, wj.getMaximumMotorTorque())
        assertEquals(0.0, wj.getMotorSpeed())
        assertEquals(b1, wj.getBody1())
        assertEquals(b2, wj.getBody2())
        assertEquals(null, wj.getOwner())
        assertEquals(null, wj.getUserData())
        assertEquals(b2, wj.getOtherBody(b1))
        assertEquals(false, wj.isCollisionAllowed())
        assertEquals(false, wj.isLowerLimitEnabled())
        assertEquals(false, wj.isUpperLimitEnabled())
        assertEquals(false, wj.isMotorEnabled())
        assertEquals(false, wj.isMaximumMotorTorqueEnabled())
        assertEquals(true, wj.isSpringDamperEnabled())
        assertEquals(true, wj.isSpringEnabled())
        assertEquals(false, wj.isMaximumSpringForceEnabled())
        assertNotNull(wj.toString())
    }

fun createWithNullBody1() {
        val b1 = wheelBody()
        val b2 = wheelBody()
        assertFailsWith<NullPointerException> {
            WheelJoint<Body>(null, b2, Vector2(), Vector2(0.0, 1.0))
        }
    }

fun createWithNullBody2() {
        val b1 = wheelBody()
        val b2 = wheelBody()
        assertFailsWith<NullPointerException> {
            WheelJoint<Body>(b1, null, Vector2(), Vector2(0.0, 1.0))
        }
    }

fun createWithNullAnchor() {
        val b1 = wheelBody()
        val b2 = wheelBody()
        assertFailsWith<NullPointerException> {
            WheelJoint<Body>(b1, b2, null, Vector2(0.0, 1.0))
        }
    }

fun createWithNullAxis() {
        val b1 = wheelBody()
        val b2 = wheelBody()
        assertFailsWith<NullPointerException> {
            WheelJoint<Body>(b1, b2, Vector2(), null)
        }
    }

fun isSpringEnabled() {
        val b1 = wheelBody()
        val b2 = wheelBody()
        var wj = WheelJoint<Body>(b1, b2, Vector2(1.0, 2.0), Vector2(-3.0, 0.5))
        assertTrue(wj.isSpringEnabled())
        wj.setSpringFrequency(1.0)
        assertTrue(wj.isSpringEnabled())
        wj.setSpringFrequency(100.0)
        assertTrue(wj.isSpringEnabled())
        wj.setSpringEnabled(false)
        assertFalse(wj.isSpringEnabled())
        wj.setSpringFrequency(50.0)
        assertFalse(wj.isSpringEnabled())
        wj.setSpringEnabled(true)
        assertTrue(wj.isSpringEnabled())
    }

fun isSpringDamperEnabled() {
        val b1 = wheelBody()
        val b2 = wheelBody()
        var wj = WheelJoint<Body>(b1, b2, Vector2(1.0, 2.0), Vector2(-3.0, 0.5))
        assertTrue(wj.isSpringDamperEnabled())
        wj.setSpringFrequency(1.0)
        assertTrue(wj.isSpringDamperEnabled())
        wj.setSpringFrequency(100.0)
        assertTrue(wj.isSpringDamperEnabled())
        wj.setSpringDampingRatio(0.4)
        assertTrue(wj.isSpringDamperEnabled())
        wj.setSpringDampingRatio(1.0)
        assertTrue(wj.isSpringDamperEnabled())
        wj.setSpringEnabled(false)
        wj.setSpringDamperEnabled(true)
        assertTrue(wj.isSpringDamperEnabled())
        wj.setSpringEnabled(true)
        wj.setSpringDamperEnabled(true)
        assertTrue(wj.isSpringDamperEnabled())
        wj.setSpringEnabled(true)
        wj.setSpringDamperEnabled(false)
        assertFalse(wj.isSpringDamperEnabled())
    }

fun setSpringRestOffset() {
        val b1 = wheelBody()
        val b2 = wheelBody()
        var wj = WheelJoint<Body>(b1, b2, Vector2(1.0, 2.0), Vector2(-3.0, 0.5))
        wj.setSpringRestOffset(0.0)
        assertEquals(0.0, wj.getSpringRestOffset())
        wj.setSpringRestOffset(1.0)
        assertEquals(1.0, wj.getSpringRestOffset())
        wj.setSpringRestOffset(-1.0)
        assertEquals(-1.0, wj.getSpringRestOffset())
    }

fun setSpringDampingRatio() {
        val b1 = wheelBody()
        val b2 = wheelBody()
        var wj = WheelJoint<Body>(b1, b2, Vector2(1.0, 2.0), Vector2(-3.0, 0.5))
        wj.setSpringDampingRatio(0.0)
        assertEquals(0.0, wj.getSpringDampingRatio())
        wj.setSpringDampingRatio(0.001)
        assertEquals(0.001, wj.getSpringDampingRatio())
        wj.setSpringDampingRatio(1.0)
        assertEquals(1.0, wj.getSpringDampingRatio())
        wj.setSpringDampingRatio(0.2)
        assertEquals(0.2, wj.getSpringDampingRatio())
        wj.setSpringEnabled(false)
        wj.setSpringDamperEnabled(false)
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setSpringDampingRatio(0.5)
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        wj.setSpringDamperEnabled(true)
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        wj.setSpringEnabled(true)
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setSpringDampingRatio(0.5)
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        wj.setSpringDampingRatio(0.6)
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
    }

fun setNegativeDampingRatio() {
        val b1 = wheelBody()
        val b2 = wheelBody()
        assertFailsWith<IllegalArgumentException> {
            var wj = WheelJoint<Body>(b1, b2, Vector2(1.0, 2.0), Vector2(-3.0, 0.5))
            wj.setSpringDampingRatio(-1.0)
        }
    }

fun setDampingRatioGreaterThan1() {
        val b1 = wheelBody()
        val b2 = wheelBody()
        assertFailsWith<IllegalArgumentException> {
            var wj = WheelJoint<Body>(b1, b2, Vector2(1.0, 2.0), Vector2(-3.0, 0.5))
            wj.setSpringDampingRatio(2.0)
        }
    }

fun setSpringFrequency() {
        val b1 = wheelBody()
        val b2 = wheelBody()
        var wj = WheelJoint<Body>(b1, b2, Vector2(1.0, 2.0), Vector2(-3.0, 0.5))
        wj.setSpringFrequency(0.0)
        assertEquals(0.0, wj.getSpringFrequency())
        wj.setSpringFrequency(0.001)
        assertEquals(0.001, wj.getSpringFrequency())
        assertEquals(Joint.SPRING_MODE_FREQUENCY, wj.getSpringMode())
        wj.setSpringFrequency(1.0)
        assertEquals(1.0, wj.getSpringFrequency())
        wj.setSpringFrequency(29.0)
        assertEquals(29.0, wj.getSpringFrequency())
        wj.setSpringEnabled(false)
        wj.setSpringDamperEnabled(false)
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setSpringFrequency(3.0)
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        wj.setSpringEnabled(true)
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setSpringFrequency(3.0)
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        wj.setSpringFrequency(5.0)
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setSpringDamperEnabled(true)
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
    }

fun setSpringMode() {
        val b1 = wheelBody()
        val b2 = wheelBody()
        var wj = WheelJoint<Body>(b1, b2, Vector2(1.0, 2.0), Vector2(-3.0, 0.5))
        assertEquals(Joint.SPRING_MODE_FREQUENCY, wj.getSpringMode())
        wj.setSpringStiffness(0.3)
        assertEquals(Joint.SPRING_MODE_STIFFNESS, wj.getSpringMode())
        wj.setSpringFrequency(0.5)
        assertEquals(Joint.SPRING_MODE_FREQUENCY, wj.getSpringMode())
    }

fun setSpringStiffnessNegative() {
        val b1 = wheelBody()
        val b2 = wheelBody()
        assertFailsWith<IllegalArgumentException> {
            var wj = WheelJoint<Body>(b1, b2, Vector2(1.0, 2.0), Vector2(-3.0, 0.5))
            wj.setSpringStiffness(-0.3)
        }
    }

fun setSpringStiffness() {
        val b1 = wheelBody()
        val b2 = wheelBody()
        var wj = WheelJoint<Body>(b1, b2, Vector2(1.0, 2.0), Vector2(-3.0, 0.5))
        wj.setSpringStiffness(0.0)
        assertEquals(0.0, wj.getSpringStiffness())
        wj.setSpringStiffness(0.001)
        assertEquals(0.001, wj.getSpringStiffness())
        wj.setSpringStiffness(1.0)
        assertEquals(1.0, wj.getSpringStiffness())
        wj.setSpringStiffness(29.0)
        assertEquals(29.0, wj.getSpringStiffness())
        wj.setSpringEnabled(false)
        wj.setSpringDamperEnabled(false)
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setSpringStiffness(3.0)
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        wj.setSpringEnabled(true)
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setSpringStiffness(3.0)
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        wj.setSpringStiffness(5.0)
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setSpringDamperEnabled(true)
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
    }

fun setSpringFrequencyNegative() {
        val b1 = wheelBody()
        val b2 = wheelBody()
        assertFailsWith<IllegalArgumentException> {
            var wj = WheelJoint<Body>(b1, b2, Vector2(1.0, 2.0), Vector2(-3.0, 0.5))
            wj.setSpringFrequency(-0.3)
        }
    }

fun setSpringMaximumForceNegative() {
        val b1 = wheelBody()
        val b2 = wheelBody()
        assertFailsWith<IllegalArgumentException> {
            var wj = WheelJoint<Body>(b1, b2, Vector2(1.0, 2.0), Vector2(-3.0, 0.5))
            wj.setMaximumSpringForce(-1.0)
        }
    }

fun setSpringMaximumForce() {
        val b1 = wheelBody()
        val b2 = wheelBody()
        var wj = WheelJoint<Body>(b1, b2, Vector2(1.0, 2.0), Vector2(-3.0, 0.5))
        wj.setMaximumSpringForce(0.0)
        assertEquals(0.0, wj.getMaximumSpringForce())
        wj.setMaximumSpringForce(0.001)
        assertEquals(0.001, wj.getMaximumSpringForce())
        wj.setMaximumSpringForce(1.0)
        assertEquals(1.0, wj.getMaximumSpringForce())
        wj.setMaximumSpringForce(1000.0)
        assertEquals(1000.0, wj.getMaximumSpringForce())
        wj.setSpringEnabled(false)
        wj.setMaximumSpringForceEnabled(false)
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setMaximumSpringForce(0.5)
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        wj.setMaximumSpringForceEnabled(true)
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        wj.setSpringEnabled(true)
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setMaximumSpringForce(0.5)
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        wj.setMaximumSpringForce(0.6)
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setMaximumSpringForceEnabled(false)
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
    }

fun setSpringRestOffsetAtRest() {
        val b1 = wheelBody()
        val b2 = wheelBody()
        var wj = WheelJoint<Body>(b1, b2, Vector2(1.0, 2.0), Vector2(-3.0, 0.5))
        var distance = wj.getSpringRestOffset()
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(distance, wj.getSpringRestOffset())
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setSpringRestOffset(distance)
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(distance, wj.getSpringRestOffset())
        wj.setSpringRestOffset(10.0)
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(10.0, wj.getSpringRestOffset())
    }

fun setMotorMaximumTorque() {
        val b1 = wheelBody()
        val b2 = wheelBody()
        var wj = WheelJoint<Body>(b1, b2, Vector2(1.0, 2.0), Vector2(-3.0, 0.5))
        wj.setMaximumMotorTorque(0.0)
        assertEquals(0.0, wj.getMaximumMotorTorque())
        wj.setMaximumMotorTorque(10.0)
        assertEquals(10.0, wj.getMaximumMotorTorque())
        wj.setMaximumMotorTorque(2548.0)
        assertEquals(2548.0, wj.getMaximumMotorTorque())
    }

fun setMaximumMotorTorqueNegative() {
        val b1 = wheelBody()
        val b2 = wheelBody()
        assertFailsWith<IllegalArgumentException> {
            var wj = WheelJoint<Body>(b1, b2, Vector2(1.0, 2.0), Vector2(-3.0, 0.5))
            wj.setMaximumMotorTorque(-2.0)
        }
    }

fun setMaximumMotorTorqueSleep() {
        val b1 = wheelBody()
        val b2 = wheelBody()
        var wj = WheelJoint<Body>(b1, b2, Vector2(1.0, 2.0), Vector2(-3.0, 0.5))
        assertFalse(wj.isMotorEnabled())
        assertEquals(1000.0, wj.getMaximumMotorTorque())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        wj.setMotorEnabled(true)
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setMaximumMotorTorque(1000.0)
        assertEquals(1000.0, wj.getMaximumMotorTorque())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        wj.setMaximumMotorTorque(2.0)
        assertEquals(2.0, wj.getMaximumMotorTorque())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        wj.setMotorEnabled(false)
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setMaximumMotorTorque(1.0)
        assertEquals(1.0, wj.getMaximumMotorTorque())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
    }

fun setMaximumMotorTorqueEnabledSleep() {
        val b1 = wheelBody()
        val b2 = wheelBody()
        var wj = WheelJoint<Body>(b1, b2, Vector2(1.0, 2.0), Vector2(-3.0, 0.5))
        assertFalse(wj.isMotorEnabled())
        assertEquals(1000.0, wj.getMaximumMotorTorque())
        assertFalse(wj.isMaximumMotorTorqueEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        wj.setMotorEnabled(true)
        wj.setMaximumMotorTorqueEnabled(true)
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setMaximumMotorTorqueEnabled(true)
        assertTrue(wj.isMaximumMotorTorqueEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        wj.setMaximumMotorTorqueEnabled(false)
        assertFalse(wj.isMaximumMotorTorqueEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        wj.setMotorEnabled(false)
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setMaximumMotorTorqueEnabled(true)
        assertTrue(wj.isMaximumMotorTorqueEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
    }

fun setMotorEnabled() {
        val b1 = wheelBody()
        val b2 = wheelBody()
        var wj = WheelJoint<Body>(b1, b2, Vector2(1.0, 2.0), Vector2(-3.0, 0.5))
        assertFalse(wj.isMotorEnabled())
        wj.setMotorEnabled(true)
        assertTrue(wj.isMotorEnabled())
        wj.setMotorEnabled(false)
        assertFalse(wj.isMotorEnabled())
    }

fun setMotorEnabledSleep() {
        val b1 = wheelBody()
        val b2 = wheelBody()
        var wj = WheelJoint<Body>(b1, b2, Vector2(1.0, 2.0), Vector2(-3.0, 0.5))
        assertFalse(wj.isMotorEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setMotorEnabled(false)
        assertFalse(wj.isMotorEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        wj.setMotorEnabled(true)
        assertTrue(wj.isMotorEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setMotorEnabled(true)
        assertTrue(wj.isMotorEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        wj.setMotorEnabled(false)
        assertFalse(wj.isMotorEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
    }

fun setMotorSpeed() {
        val b1 = wheelBody()
        val b2 = wheelBody()
        var wj = WheelJoint<Body>(b1, b2, Vector2(1.0, 2.0), Vector2(-3.0, 0.5))
        assertEquals(0.0, wj.getMotorSpeed())
        wj.setMotorSpeed(2.0)
        assertEquals(2.0, wj.getMotorSpeed())
        wj.setMotorSpeed(-1.0)
        assertEquals(-1.0, wj.getMotorSpeed())
        wj.setMotorSpeed(0.0)
        assertEquals(0.0, wj.getMotorSpeed())
    }

fun setMotorSpeedSleep() {
        val b1 = wheelBody()
        val b2 = wheelBody()
        var wj = WheelJoint<Body>(b1, b2, Vector2(1.0, 2.0), Vector2(-3.0, 0.5))
        assertFalse(wj.isMotorEnabled())
        assertEquals(0.0, wj.getMotorSpeed())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        wj.setMotorEnabled(true)
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setMotorSpeed(0.0)
        assertEquals(0.0, wj.getMotorSpeed())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        wj.setMotorSpeed(2.0)
        assertEquals(2.0, wj.getMotorSpeed())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        wj.setMotorEnabled(false)
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setMotorSpeed(-1.0)
        assertEquals(-1.0, wj.getMotorSpeed())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
    }

fun setUpperLimitSuccess() {
        val b1 = wheelBody()
        val b2 = wheelBody()
        var wj = WheelJoint<Body>(b1, b2, Vector2(1.0, 2.0), Vector2(-3.0, 0.5))
        wj.setLowerLimit(-5.0)
        assertEquals(0.0, wj.getUpperLimit())
        wj.setUpperLimit(2.0)
        assertEquals(2.0, wj.getUpperLimit(), 1e-6)
        wj.setUpperLimit(-2.0)
        assertEquals(-2.0, wj.getUpperLimit(), 1e-6)
        wj.setUpperLimit(0.0)
        assertEquals(0.0, wj.getUpperLimit(), 1e-6)
    }

fun setUpperLimitInvalid() {
        val b1 = wheelBody()
        val b2 = wheelBody()
        assertFailsWith<IllegalArgumentException> {
            var wj = WheelJoint<Body>(b1, b2, Vector2(1.0, 2.0), Vector2(-3.0, 0.5))
            assertEquals(0.0, wj.getUpperLimit())
            wj.setUpperLimit(-0.5)
        }
    }

fun setLowerLimit() {
        val b1 = wheelBody()
        val b2 = wheelBody()
        var wj = WheelJoint<Body>(b1, b2, Vector2(1.0, 2.0), Vector2(-3.0, 0.5))
        wj.setUpperLimit(5.0)
        assertEquals(0.0, wj.getLowerLimit())
        wj.setLowerLimit(-1.0)
        assertEquals(-1.0, wj.getLowerLimit(), 1e-6)
        wj.setLowerLimit(0.0)
        assertEquals(0.0, wj.getLowerLimit(), 1e-6)
        wj.setLowerLimit(2.0)
        assertEquals(2.0, wj.getLowerLimit(), 1e-6)
    }

fun setLowerLimitInvalid() {
        val b1 = wheelBody()
        val b2 = wheelBody()
        assertFailsWith<IllegalArgumentException> {
            var wj = WheelJoint<Body>(b1, b2, Vector2(1.0, 2.0), Vector2(-3.0, 0.5))
            assertEquals(0.0, wj.getLowerLimit())
            wj.setLowerLimit(1.5)
        }
    }

fun setUpperAndLowerLimits() {
        val b1 = wheelBody()
        val b2 = wheelBody()
        var wj = WheelJoint<Body>(b1, b2, Vector2(1.0, 2.0), Vector2(-3.0, 0.5))
        assertEquals(0.0, wj.getLowerLimit())
        assertEquals(0.0, wj.getUpperLimit())
        wj.setLimits(0.0, 1.0)
        assertEquals(0.0, wj.getLowerLimit(), 1e-6)
        assertEquals(1.0, wj.getUpperLimit(), 1e-6)
        wj.setLimits(-1.0, 2.0)
        assertEquals(-1.0, wj.getLowerLimit(), 1e-6)
        assertEquals(2.0, wj.getUpperLimit(), 1e-6)
        wj.setLimits(-1.0, -1.0)
        assertEquals(-1.0, wj.getLowerLimit())
        assertEquals(-1.0, wj.getUpperLimit())
        wj.setLimits(-4.0, -1.0)
        assertEquals(-4.0, wj.getLowerLimit())
        assertEquals(-1.0, wj.getUpperLimit())
        wj.setLimits(3.0, 5.0)
        assertEquals(3.0, wj.getLowerLimit())
        assertEquals(5.0, wj.getUpperLimit())
    }

fun setUpperAndLowerLimitsInvalid1() {
        val b1 = wheelBody()
        val b2 = wheelBody()
        assertFailsWith<IllegalArgumentException> {
            var wj = WheelJoint<Body>(b1, b2, Vector2(1.0, 2.0), Vector2(-3.0, 0.5))
            assertEquals(0.0, wj.getLowerLimit())
            assertEquals(0.0, wj.getUpperLimit())
            wj.setLimits(1.0, 0.0)
        }
    }

fun setUpperAndLowerLimitsInvalid2() {
        val b1 = wheelBody()
        val b2 = wheelBody()
        assertFailsWith<IllegalArgumentException> {
            var wj = WheelJoint<Body>(b1, b2, Vector2(1.0, 2.0), Vector2(-3.0, 0.5))
            assertEquals(0.0, wj.getLowerLimit())
            assertEquals(0.0, wj.getUpperLimit())
            wj.setLimits(0.0, -1.0)
        }
    }

fun setSameLimitValid() {
        val b1 = wheelBody()
        val b2 = wheelBody()
        var wj = WheelJoint<Body>(b1, b2, Vector2(1.0, 2.0), Vector2(-3.0, 0.5))
        assertEquals(0.0, wj.getLowerLimit())
        assertEquals(0.0, wj.getUpperLimit())
        wj.setLimits(2.0)
        assertEquals(2.0, wj.getLowerLimit())
        assertEquals(2.0, wj.getUpperLimit())
        wj.setLimits(-2.0)
        assertEquals(-2.0, wj.getLowerLimit())
        assertEquals(-2.0, wj.getUpperLimit())
    }

fun setLimitsEnabledSleep() {
        val b1 = wheelBody()
        val b2 = wheelBody()
        var wj = WheelJoint<Body>(b1, b2, Vector2(1.0, 2.0), Vector2(-3.0, 0.5))
        wj.setLowerLimitEnabled(true)
        wj.setUpperLimitEnabled(true)
        assertTrue(wj.isUpperLimitEnabled())
        assertTrue(wj.isLowerLimitEnabled())
        wj.setLimitsEnabled(false)
        assertFalse(wj.isUpperLimitEnabled())
        assertFalse(wj.isLowerLimitEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setLimitsEnabled(false)
        assertFalse(wj.isUpperLimitEnabled())
        assertFalse(wj.isLowerLimitEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        wj.setLimitsEnabled(true)
        assertTrue(wj.isUpperLimitEnabled())
        assertTrue(wj.isLowerLimitEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setLimitsEnabled(true)
        assertTrue(wj.isUpperLimitEnabled())
        assertTrue(wj.isLowerLimitEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        wj.setLimitsEnabled(false)
        assertFalse(wj.isUpperLimitEnabled())
        assertFalse(wj.isLowerLimitEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
    }

fun setLimitsSameSleep() {
        val b1 = wheelBody()
        val b2 = wheelBody()
        var wj = WheelJoint<Body>(b1, b2, Vector2(1.0, 2.0), Vector2(-3.0, 0.5))
        wj.setLowerLimitEnabled(true)
        wj.setUpperLimitEnabled(true)
        assertTrue(wj.isUpperLimitEnabled())
        assertTrue(wj.isLowerLimitEnabled())
        var defaultLowerLimit = wj.getLowerLimit()
        var defaultUpperLimit = wj.getUpperLimit()
        assertEquals(defaultLowerLimit, defaultUpperLimit)
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setLimits(defaultLowerLimit, defaultUpperLimit)
        assertTrue(wj.isUpperLimitEnabled())
        assertTrue(wj.isLowerLimitEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(defaultLowerLimit, wj.getLowerLimit())
        assertEquals(defaultUpperLimit, wj.getUpperLimit())
        wj.setLimits(2.0)
        assertTrue(wj.isUpperLimitEnabled())
        assertTrue(wj.isLowerLimitEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(2.0, wj.getLowerLimit())
        assertEquals(2.0, wj.getUpperLimit())
        wj.setLowerLimit(0.0)
        assertEquals(0.0, wj.getLowerLimit())
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setLimits(2.0)
        assertTrue(wj.isUpperLimitEnabled())
        assertTrue(wj.isLowerLimitEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(2.0, wj.getLowerLimit())
        assertEquals(2.0, wj.getUpperLimit())
        wj.setUpperLimit(3.0)
        assertEquals(3.0, wj.getUpperLimit())
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setLimits(2.0)
        assertTrue(wj.isUpperLimitEnabled())
        assertTrue(wj.isLowerLimitEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(2.0, wj.getLowerLimit())
        assertEquals(2.0, wj.getUpperLimit())
        wj.setLimitsEnabled(false)
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setLimits(1.0)
        assertFalse(wj.isUpperLimitEnabled())
        assertFalse(wj.isLowerLimitEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(1.0, wj.getLowerLimit())
        assertEquals(1.0, wj.getUpperLimit())
    }

fun setLimitsDifferentSleep() {
        val b1 = wheelBody()
        val b2 = wheelBody()
        var wj = WheelJoint<Body>(b1, b2, Vector2(1.0, 2.0), Vector2(-3.0, 0.5))
        wj.setLowerLimitEnabled(true)
        wj.setUpperLimitEnabled(true)
        assertTrue(wj.isUpperLimitEnabled())
        assertTrue(wj.isLowerLimitEnabled())
        var defaultLowerLimit = wj.getLowerLimit()
        var defaultUpperLimit = wj.getUpperLimit()
        assertEquals(defaultLowerLimit, defaultUpperLimit)
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setLimits(defaultLowerLimit, defaultUpperLimit)
        assertTrue(wj.isUpperLimitEnabled())
        assertTrue(wj.isLowerLimitEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(defaultLowerLimit, wj.getLowerLimit())
        assertEquals(defaultUpperLimit, wj.getUpperLimit())
        wj.setLimits(2.0, 3.0)
        assertTrue(wj.isUpperLimitEnabled())
        assertTrue(wj.isLowerLimitEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(2.0, wj.getLowerLimit())
        assertEquals(3.0, wj.getUpperLimit())
        wj.setLowerLimit(1.0)
        assertEquals(1.0, wj.getLowerLimit())
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setLimits(0.0, 3.0)
        assertTrue(wj.isUpperLimitEnabled())
        assertTrue(wj.isLowerLimitEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(0.0, wj.getLowerLimit())
        assertEquals(3.0, wj.getUpperLimit())
        wj.setUpperLimit(2.0)
        assertEquals(2.0, wj.getUpperLimit())
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setLimits(0.0, 1.0)
        assertTrue(wj.isUpperLimitEnabled())
        assertTrue(wj.isLowerLimitEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(0.0, wj.getLowerLimit())
        assertEquals(1.0, wj.getUpperLimit())
        wj.setLimitsEnabled(false)
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setLimits(1.0, 2.0)
        assertFalse(wj.isUpperLimitEnabled())
        assertFalse(wj.isLowerLimitEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(1.0, wj.getLowerLimit())
        assertEquals(2.0, wj.getUpperLimit())
    }

fun setLowerLimitSleep() {
        val b1 = wheelBody()
        val b2 = wheelBody()
        var wj = WheelJoint<Body>(b1, b2, Vector2(1.0, 2.0), Vector2(-3.0, 0.5))
        wj.setLowerLimitEnabled(true)
        wj.setUpperLimitEnabled(true)
        assertTrue(wj.isLowerLimitEnabled())
        var defaultLowerLimit = wj.getLowerLimit()
        var defaultUpperLimit = wj.getUpperLimit()
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setLowerLimit(defaultLowerLimit)
        assertTrue(wj.isLowerLimitEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(defaultLowerLimit, wj.getLowerLimit())
        assertEquals(defaultUpperLimit, wj.getUpperLimit())
        wj.setLowerLimit(-0.5)
        assertTrue(wj.isLowerLimitEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(-0.5, wj.getLowerLimit())
        assertEquals(defaultUpperLimit, wj.getUpperLimit())
        wj.setLimitsEnabled(false)
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setLowerLimit(-0.2)
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(-0.2, wj.getLowerLimit())
        assertEquals(defaultUpperLimit, wj.getUpperLimit())
    }

fun setUpperLimitSleep() {
        val b1 = wheelBody()
        val b2 = wheelBody()
        var wj = WheelJoint<Body>(b1, b2, Vector2(1.0, 2.0), Vector2(-3.0, 0.5))
        wj.setLowerLimitEnabled(true)
        wj.setUpperLimitEnabled(true)
        assertTrue(wj.isUpperLimitEnabled())
        var defaultLowerLimit = wj.getLowerLimit()
        var defaultUpperLimit = wj.getUpperLimit()
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setUpperLimit(defaultUpperLimit)
        assertTrue(wj.isUpperLimitEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(defaultLowerLimit, wj.getLowerLimit())
        assertEquals(defaultUpperLimit, wj.getUpperLimit())
        wj.setUpperLimit(2.0)
        assertTrue(wj.isUpperLimitEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(defaultLowerLimit, wj.getLowerLimit())
        assertEquals(2.0, wj.getUpperLimit())
        wj.setLimitsEnabled(false)
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setUpperLimit(3.0)
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(defaultLowerLimit, wj.getLowerLimit())
        assertEquals(3.0, wj.getUpperLimit())
    }

fun setLimitsEnabledSameSleep() {
        val b1 = wheelBody()
        val b2 = wheelBody()
        var wj = WheelJoint<Body>(b1, b2, Vector2(1.0, 2.0), Vector2(-3.0, 0.5))
        wj.setLowerLimitEnabled(true)
        wj.setUpperLimitEnabled(true)
        assertTrue(wj.isUpperLimitEnabled())
        assertTrue(wj.isLowerLimitEnabled())
        var defaultLowerLimit = wj.getLowerLimit()
        var defaultUpperLimit = wj.getUpperLimit()
        assertEquals(defaultLowerLimit, defaultUpperLimit)
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setLimitsEnabled(defaultLowerLimit, defaultUpperLimit)
        assertTrue(wj.isUpperLimitEnabled())
        assertTrue(wj.isLowerLimitEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(defaultLowerLimit, wj.getLowerLimit())
        assertEquals(defaultUpperLimit, wj.getUpperLimit())
        wj.setLimitsEnabled(2.0)
        assertTrue(wj.isUpperLimitEnabled())
        assertTrue(wj.isLowerLimitEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(2.0, wj.getLowerLimit())
        assertEquals(2.0, wj.getUpperLimit())
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setLimitsEnabled(false)
        wj.setLimitsEnabled(1.0)
        assertTrue(wj.isUpperLimitEnabled())
        assertTrue(wj.isLowerLimitEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(1.0, wj.getLowerLimit())
        assertEquals(1.0, wj.getUpperLimit())
    }

fun setLimitsEnabledDifferentSleep() {
        val b1 = wheelBody()
        val b2 = wheelBody()
        var wj = WheelJoint<Body>(b1, b2, Vector2(1.0, 2.0), Vector2(-3.0, 0.5))
        wj.setLowerLimitEnabled(true)
        wj.setUpperLimitEnabled(true)
        assertTrue(wj.isUpperLimitEnabled())
        assertTrue(wj.isLowerLimitEnabled())
        var defaultLowerLimit = wj.getLowerLimit()
        var defaultUpperLimit = wj.getUpperLimit()
        assertEquals(defaultLowerLimit, defaultUpperLimit)
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setLimitsEnabled(defaultLowerLimit, defaultUpperLimit)
        assertTrue(wj.isUpperLimitEnabled())
        assertTrue(wj.isLowerLimitEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(defaultLowerLimit, wj.getLowerLimit())
        assertEquals(defaultUpperLimit, wj.getUpperLimit())
        wj.setLimitsEnabled(0.0, 2.0)
        assertTrue(wj.isUpperLimitEnabled())
        assertTrue(wj.isLowerLimitEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(0.0, wj.getLowerLimit())
        assertEquals(2.0, wj.getUpperLimit())
        wj.setLowerLimit(0.5)
        assertEquals(0.5, wj.getLowerLimit())
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setLimitsEnabled(0.0, 2.0)
        assertTrue(wj.isUpperLimitEnabled())
        assertTrue(wj.isLowerLimitEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(0.0, wj.getLowerLimit())
        assertEquals(2.0, wj.getUpperLimit())
        wj.setUpperLimit(3.0)
        assertEquals(3.0, wj.getUpperLimit())
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setLimitsEnabled(0.0, 2.0)
        assertTrue(wj.isUpperLimitEnabled())
        assertTrue(wj.isLowerLimitEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(0.0, wj.getLowerLimit())
        assertEquals(2.0, wj.getUpperLimit())
        wj.setLimitsEnabled(false)
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setLimitsEnabled(0.5, 4.0)
        assertTrue(wj.isUpperLimitEnabled())
        assertTrue(wj.isLowerLimitEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(0.5, wj.getLowerLimit())
        assertEquals(4.0, wj.getUpperLimit())
    }

fun shift() {
        val b1 = wheelBody()
        val b2 = wheelBody()
        var wj = WheelJoint<Body>(b1, b2, Vector2(1.0, 2.0), Vector2(-3.0, 0.5))
        assertEquals(1.0, wj.getAnchor1().x)
        assertEquals(2.0, wj.getAnchor1().y)
        assertEquals(1.0, wj.getAnchor2().x)
        assertEquals(2.0, wj.getAnchor2().y)
        wj.shift(Vector2(1.0, 3.0))
        assertEquals(1.0, wj.getAnchor1().x)
        assertEquals(2.0, wj.getAnchor1().y)
        assertEquals(1.0, wj.getAnchor2().x)
        assertEquals(2.0, wj.getAnchor2().y)
    }

fun copyFailed() {
        val b1 = wheelBody()
        val b2 = wheelBody()
        assertFailsWith<ClassCastException> {
            var b1 = WheelTestBody()
            var b2 = WheelTestBody()
            var wj = WheelJoint<Body>(b1, b2, Vector2(1.0, 2.0), Vector2(-3.0, 0.5))
            wj.copy()
        }
    }
}
