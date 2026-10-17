/*
 * Copyright (c) 2010-2026 William Bittle  http://www.dyn4j.org/
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

import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.sqrt
import kotlin.test.Test
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

private fun weldBody() = Body().apply {
    addFixture(Geometry.createCircle(1.0), 1.0, 0.2, 0.0)
    setMass(MassType.NORMAL)
}

private fun weldRadians(degrees: Double) = degrees * PI / 180.0

private class WeldTestBody : Body()

class UpstreamWeldJointModesCoverageTest {
    @Test fun createSuccess() {
        val b1 = weldBody()
        val b2 = weldBody()
        var p = Vector2(2.0, 4.0)
        var wj = WeldJoint<Body>(b1, b2, p)
        assertEquals(p, wj.getAnchor1())
        assertEquals(p, wj.getAnchor2())
        assertNotSame(p, wj.getAnchor1())
        assertNotSame(p, wj.getAnchor2())
        assertEquals(0.3, wj.getSpringDampingRatio())
        assertEquals(8.0, wj.getSpringFrequency())
        assertEquals(0.0, wj.getSpringStiffness())
        assertEquals(1000.0, wj.getMaximumSpringTorque())
        assertEquals(0.0, wj.getLimitsReferenceAngle())
        assertEquals(0.0, wj.getLowerLimit())
        assertEquals(0.0, wj.getUpperLimit())
        assertEquals(b1, wj.getBody1())
        assertEquals(b2, wj.getBody2())
        assertEquals(null, wj.getOwner())
        assertEquals(null, wj.getUserData())
        assertEquals(b2, wj.getOtherBody(b1))
        assertEquals(false, wj.isCollisionAllowed())
        assertEquals(false, wj.isSpringDamperEnabled())
        assertEquals(false, wj.isSpringEnabled())
        assertEquals(false, wj.isMaximumSpringTorqueEnabled())
        assertEquals(false, wj.isLimitsEnabled())
        assertNotNull(wj.toString())
    }

    @Test fun createWithNullBody1() {
        val b1 = weldBody()
        val b2 = weldBody()
        assertFailsWith<NullPointerException> {
            WeldJoint<Body>(null, b2, Vector2())
        }
    }

    @Test fun createWithNullBody2() {
        val b1 = weldBody()
        val b2 = weldBody()
        assertFailsWith<NullPointerException> {
            WeldJoint<Body>(b1, null, Vector2())
        }
    }

    @Test fun createWithNullAnchor() {
        val b1 = weldBody()
        val b2 = weldBody()
        assertFailsWith<NullPointerException> {
            WeldJoint<Body>(b1, b2, null)
        }
    }

    @Test fun createWithSameBody() {
        val b1 = weldBody()
        val b2 = weldBody()
        assertFailsWith<IllegalArgumentException> {
            WeldJoint<Body>(b1, b1, Vector2())
        }
    }

    @Test fun isSpringEnabled() {
        val b1 = weldBody()
        val b2 = weldBody()
        var wj = WeldJoint<Body>(b1, b2, Vector2())
        assertFalse(wj.isSpringEnabled())
        wj.setSpringFrequency(1.0)
        assertFalse(wj.isSpringEnabled())
        wj.setSpringEnabled(true)
        assertTrue(wj.isSpringEnabled())
        wj.setSpringFrequency(50.0)
        assertTrue(wj.isSpringEnabled())
        wj.setSpringEnabled(false)
        assertFalse(wj.isSpringEnabled())
    }

    @Test fun isSpringDamperEnabled() {
        val b1 = weldBody()
        val b2 = weldBody()
        var wj = WeldJoint<Body>(b1, b2, Vector2())
        assertFalse(wj.isSpringDamperEnabled())
        wj.setSpringFrequency(1.0)
        assertFalse(wj.isSpringDamperEnabled())
        wj.setSpringDampingRatio(0.4)
        assertFalse(wj.isSpringDamperEnabled())
        wj.setSpringEnabled(true)
        wj.setSpringDamperEnabled(false)
        assertFalse(wj.isSpringDamperEnabled())
        wj.setSpringEnabled(true)
        wj.setSpringDamperEnabled(true)
        assertTrue(wj.isSpringDamperEnabled())
        wj.setSpringEnabled(false)
        wj.setSpringDamperEnabled(true)
        assertTrue(wj.isSpringDamperEnabled())
    }

    @Test fun setSpringDampingRatio() {
        val b1 = weldBody()
        val b2 = weldBody()
        var wj = WeldJoint<Body>(b1, b2, Vector2())
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

    @Test fun setNegativeDampingRatio() {
        val b1 = weldBody()
        val b2 = weldBody()
        assertFailsWith<IllegalArgumentException> {
            var wj = WeldJoint<Body>(b1, b2, Vector2())
            wj.setSpringDampingRatio(-1.0)
        }
    }

    @Test fun setDampingRatioGreaterThan1() {
        val b1 = weldBody()
        val b2 = weldBody()
        assertFailsWith<IllegalArgumentException> {
            var wj = WeldJoint<Body>(b1, b2, Vector2())
            wj.setSpringDampingRatio(2.0)
        }
    }

    @Test fun setSpringFrequency() {
        val b1 = weldBody()
        val b2 = weldBody()
        var wj = WeldJoint<Body>(b1, b2, Vector2())
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

    @Test fun setSpringMode() {
        val b1 = weldBody()
        val b2 = weldBody()
        var wj = WeldJoint<Body>(b1, b2, Vector2())
        assertEquals(Joint.SPRING_MODE_FREQUENCY, wj.getSpringMode())
        wj.setSpringStiffness(0.3)
        assertEquals(Joint.SPRING_MODE_STIFFNESS, wj.getSpringMode())
        wj.setSpringFrequency(0.5)
        assertEquals(Joint.SPRING_MODE_FREQUENCY, wj.getSpringMode())
    }

    @Test fun setSpringStiffnessNegative() {
        val b1 = weldBody()
        val b2 = weldBody()
        assertFailsWith<IllegalArgumentException> {
            var wj = WeldJoint<Body>(b1, b2, Vector2())
            wj.setSpringStiffness(-0.3)
        }
    }

    @Test fun setSpringStiffness() {
        val b1 = weldBody()
        val b2 = weldBody()
        var wj = WeldJoint<Body>(b1, b2, Vector2())
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

    @Test fun setSpringFrequencyNegative() {
        val b1 = weldBody()
        val b2 = weldBody()
        assertFailsWith<IllegalArgumentException> {
            var wj = WeldJoint<Body>(b1, b2, Vector2())
            wj.setSpringFrequency(-0.3)
        }
    }

    @Test fun setSpringMaximumForceNegative() {
        val b1 = weldBody()
        val b2 = weldBody()
        assertFailsWith<IllegalArgumentException> {
            var wj = WeldJoint<Body>(b1, b2, Vector2())
            wj.setMaximumSpringTorque(-1.0)
        }
    }

    @Test fun setSpringMaximumForce() {
        val b1 = weldBody()
        val b2 = weldBody()
        var wj = WeldJoint<Body>(b1, b2, Vector2())
        wj.setMaximumSpringTorque(0.0)
        assertEquals(0.0, wj.getMaximumSpringTorque())
        wj.setMaximumSpringTorque(0.001)
        assertEquals(0.001, wj.getMaximumSpringTorque())
        wj.setMaximumSpringTorque(1.0)
        assertEquals(1.0, wj.getMaximumSpringTorque())
        wj.setMaximumSpringTorque(1000.0)
        assertEquals(1000.0, wj.getMaximumSpringTorque())
        wj.setSpringEnabled(false)
        wj.setMaximumSpringTorqueEnabled(false)
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setMaximumSpringTorque(0.5)
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        wj.setMaximumSpringTorqueEnabled(true)
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        wj.setSpringEnabled(true)
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setMaximumSpringTorque(0.5)
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        wj.setMaximumSpringTorque(0.6)
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setMaximumSpringTorqueEnabled(false)
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
    }

    @Test fun setUpperLimitSuccess() {
        val b1 = weldBody()
        val b2 = weldBody()
        var wj = WeldJoint<Body>(b1, b2, Vector2())
        wj.setUpperLimit(weldRadians(10.0))
        assertEquals(weldRadians(10.0), wj.getUpperLimit(), 1e-6)
    }

    @Test fun setLowerLimit() {
        val b1 = weldBody()
        val b2 = weldBody()
        var wj = WeldJoint<Body>(b1, b2, Vector2())
        wj.setLowerLimit(weldRadians(-10.0))
        assertEquals(weldRadians(-10.0), wj.getLowerLimit(), 1e-6)
    }

    @Test fun setUpperAndLowerLimits() {
        val b1 = weldBody()
        val b2 = weldBody()
        var wj = WeldJoint<Body>(b1, b2, Vector2())
        wj.setLimits(weldRadians(-30.0), weldRadians(20.0))
        assertEquals(weldRadians(-30.0), wj.getLowerLimit(), 1e-6)
        assertEquals(weldRadians(20.0), wj.getUpperLimit(), 1e-6)
    }

    @Test fun setUpperAndLowerLimitsToSameValue() {
        val b1 = weldBody()
        val b2 = weldBody()
        var wj = WeldJoint<Body>(b1, b2, Vector2())
        wj.setLimits(weldRadians(30.0))
        assertEquals(weldRadians(30.0), wj.getLowerLimit(), 1e-6)
        assertEquals(weldRadians(30.0), wj.getUpperLimit(), 1e-6)
    }

    @Test fun setLimitsReferenceAngle() {
        val b1 = weldBody()
        val b2 = weldBody()
        var wj = WeldJoint<Body>(b1, b2, Vector2())
        assertEquals(0.0, wj.getLimitsReferenceAngle())
        wj.setLimitsReferenceAngle(weldRadians(30.0))
        assertEquals(weldRadians(30.0), wj.getLimitsReferenceAngle())
    }

    @Test fun setLimitsReferenceAngleSleep() {
        val b1 = weldBody()
        val b2 = weldBody()
        var wj = WeldJoint<Body>(b1, b2, Vector2())
        assertFalse(wj.isLimitsEnabled())
        wj.setLimitsEnabled(true)
        assertTrue(wj.isLimitsEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setLimitsReferenceAngle(0.0)
        assertTrue(wj.isLimitsEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        wj.setLimitsReferenceAngle(1.0)
        assertTrue(wj.isLimitsEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
    }

    @Test fun setLimitEnabledSleep() {
        val b1 = weldBody()
        val b2 = weldBody()
        var wj = WeldJoint<Body>(b1, b2, Vector2())
        assertFalse(wj.isLimitsEnabled())
        wj.setLimitsEnabled(false)
        assertFalse(wj.isLimitsEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setLimitsEnabled(false)
        assertFalse(wj.isLimitsEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        wj.setLimitsEnabled(true)
        assertTrue(wj.isLimitsEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setLimitsEnabled(true)
        assertTrue(wj.isLimitsEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        wj.setLimitsEnabled(false)
        assertFalse(wj.isLimitsEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
    }

    @Test fun setLimitsSameSleep() {
        val b1 = weldBody()
        val b2 = weldBody()
        var wj = WeldJoint<Body>(b1, b2, Vector2())
        assertFalse(wj.isLimitsEnabled())
        var defaultLowerLimit = wj.getLowerLimit()
        var defaultUpperLimit = wj.getUpperLimit()
        assertEquals(defaultLowerLimit, defaultUpperLimit)
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        wj.setLimitsEnabled(true)
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setLimits(defaultLowerLimit)
        assertTrue(wj.isLimitsEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(defaultLowerLimit, wj.getLowerLimit())
        assertEquals(defaultUpperLimit, wj.getUpperLimit())
        wj.setLimits(PI)
        assertTrue(wj.isLimitsEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(PI, wj.getLowerLimit())
        assertEquals(PI, wj.getUpperLimit())
        wj.setLowerLimit(-PI)
        assertEquals(-PI, wj.getLowerLimit())
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setLimits(PI)
        assertTrue(wj.isLimitsEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(PI, wj.getLowerLimit())
        assertEquals(PI, wj.getUpperLimit())
        wj.setUpperLimit(2.0*PI)
        assertEquals(2*PI, wj.getUpperLimit())
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setLimits(PI)
        assertTrue(wj.isLimitsEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(PI, wj.getLowerLimit())
        assertEquals(PI, wj.getUpperLimit())
        wj.setLimitsEnabled(false)
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setLimits(-PI)
        assertFalse(wj.isLimitsEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(-PI, wj.getLowerLimit())
        assertEquals(-PI, wj.getUpperLimit())
    }

    @Test fun setLimitsDifferentSleep() {
        val b1 = weldBody()
        val b2 = weldBody()
        var wj = WeldJoint<Body>(b1, b2, Vector2())
        assertFalse(wj.isLimitsEnabled())
        var defaultLowerLimit = wj.getLowerLimit()
        var defaultUpperLimit = wj.getUpperLimit()
        assertEquals(defaultLowerLimit, defaultUpperLimit)
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        wj.setLimitsEnabled(true)
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setLimits(defaultLowerLimit, defaultUpperLimit)
        assertTrue(wj.isLimitsEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(defaultLowerLimit, wj.getLowerLimit())
        assertEquals(defaultUpperLimit, wj.getUpperLimit())
        wj.setLimits(-PI, PI)
        assertTrue(wj.isLimitsEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(-PI, wj.getLowerLimit())
        assertEquals(PI, wj.getUpperLimit())
        wj.setLowerLimit(-2.0*PI)
        assertEquals(-2*PI, wj.getLowerLimit())
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setLimits(-PI, PI)
        assertTrue(wj.isLimitsEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(-PI, wj.getLowerLimit())
        assertEquals(PI, wj.getUpperLimit())
        wj.setUpperLimit(2.0*PI)
        assertEquals(2*PI, wj.getUpperLimit())
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setLimits(-PI, PI)
        assertTrue(wj.isLimitsEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(-PI, wj.getLowerLimit())
        assertEquals(PI, wj.getUpperLimit())
        wj.setLimitsEnabled(false)
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setLimits(PI, 2.0*PI)
        assertFalse(wj.isLimitsEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(PI, wj.getLowerLimit())
        assertEquals(2*PI, wj.getUpperLimit())
    }

    @Test fun setLowerLimitSleep() {
        val b1 = weldBody()
        val b2 = weldBody()
        var wj = WeldJoint<Body>(b1, b2, Vector2())
        assertFalse(wj.isLimitsEnabled())
        var defaultLowerLimit = wj.getLowerLimit()
        var defaultUpperLimit = wj.getUpperLimit()
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        wj.setLimitsEnabled(true)
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setLowerLimit(defaultLowerLimit)
        assertTrue(wj.isLimitsEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(defaultLowerLimit, wj.getLowerLimit())
        assertEquals(defaultUpperLimit, wj.getUpperLimit())
        wj.setLowerLimit(-PI)
        assertTrue(wj.isLimitsEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(-PI, wj.getLowerLimit())
        assertEquals(defaultUpperLimit, wj.getUpperLimit())
        wj.setLimitsEnabled(false)
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setLowerLimit(-2.0*PI)
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(-2*PI, wj.getLowerLimit())
        assertEquals(defaultUpperLimit, wj.getUpperLimit())
    }

    @Test fun setUpperLimitSleep() {
        val b1 = weldBody()
        val b2 = weldBody()
        var wj = WeldJoint<Body>(b1, b2, Vector2())
        assertFalse(wj.isLimitsEnabled())
        var defaultLowerLimit = wj.getLowerLimit()
        var defaultUpperLimit = wj.getUpperLimit()
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        wj.setLimitsEnabled(true)
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setUpperLimit(defaultUpperLimit)
        assertTrue(wj.isLimitsEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(defaultLowerLimit, wj.getLowerLimit())
        assertEquals(defaultUpperLimit, wj.getUpperLimit())
        wj.setUpperLimit(PI)
        assertTrue(wj.isLimitsEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(defaultLowerLimit, wj.getLowerLimit())
        assertEquals(PI, wj.getUpperLimit())
        wj.setLimitsEnabled(false)
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setUpperLimit(2.0*PI)
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(defaultLowerLimit, wj.getLowerLimit())
        assertEquals(2*PI, wj.getUpperLimit())
    }

    @Test fun setLimitsEnabledSameSleep() {
        val b1 = weldBody()
        val b2 = weldBody()
        var wj = WeldJoint<Body>(b1, b2, Vector2())
        assertFalse(wj.isLimitsEnabled())
        var defaultLowerLimit = wj.getLowerLimit()
        var defaultUpperLimit = wj.getUpperLimit()
        assertEquals(defaultLowerLimit, defaultUpperLimit)
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        wj.setLimitsEnabled(true)
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setLimitsEnabled(defaultLowerLimit)
        assertTrue(wj.isLimitsEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(defaultLowerLimit, wj.getLowerLimit())
        assertEquals(defaultUpperLimit, wj.getUpperLimit())
        wj.setLimitsEnabled(PI)
        assertTrue(wj.isLimitsEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(PI, wj.getLowerLimit())
        assertEquals(PI, wj.getUpperLimit())
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setLimitsEnabled(false)
        wj.setLimitsEnabled(PI)
        assertTrue(wj.isLimitsEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(PI, wj.getLowerLimit())
        assertEquals(PI, wj.getUpperLimit())
    }

    @Test fun setLimitsEnabledDifferentSleep() {
        val b1 = weldBody()
        val b2 = weldBody()
        var wj = WeldJoint<Body>(b1, b2, Vector2())
        assertFalse(wj.isLimitsEnabled())
        var defaultLowerLimit = wj.getLowerLimit()
        var defaultUpperLimit = wj.getUpperLimit()
        assertEquals(defaultLowerLimit, defaultUpperLimit)
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        wj.setLimitsEnabled(true)
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setLimitsEnabled(defaultLowerLimit, defaultUpperLimit)
        assertTrue(wj.isLimitsEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(defaultLowerLimit, wj.getLowerLimit())
        assertEquals(defaultUpperLimit, wj.getUpperLimit())
        wj.setLimitsEnabled(-PI, PI)
        assertTrue(wj.isLimitsEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(-PI, wj.getLowerLimit())
        assertEquals(PI, wj.getUpperLimit())
        wj.setLowerLimit(-2.0*PI)
        assertEquals(-2*PI, wj.getLowerLimit())
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setLimitsEnabled(-PI, PI)
        assertTrue(wj.isLimitsEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(-PI, wj.getLowerLimit())
        assertEquals(PI, wj.getUpperLimit())
        wj.setUpperLimit(2.0*PI)
        assertEquals(2*PI, wj.getUpperLimit())
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setLimitsEnabled(-PI, PI)
        assertTrue(wj.isLimitsEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(-PI, wj.getLowerLimit())
        assertEquals(PI, wj.getUpperLimit())
        wj.setLimitsEnabled(false)
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setLimitsEnabled(-PI, PI)
        assertTrue(wj.isLimitsEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(-PI, wj.getLowerLimit())
        assertEquals(PI, wj.getUpperLimit())
    }

    @Test fun setLimitsEnabledSleep() {
        val b1 = weldBody()
        val b2 = weldBody()
        var wj = WeldJoint<Body>(b1, b2, Vector2())
        assertFalse(wj.isLimitsEnabled())
        wj.setLimitsEnabled(true)
        wj.setLimitsEnabled(false)
        assertFalse(wj.isLimitsEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setLimitsEnabled(false)
        assertFalse(wj.isLimitsEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        wj.setLimitsEnabled(true)
        assertTrue(wj.isLimitsEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        wj.setLimitsEnabled(true)
        assertTrue(wj.isLimitsEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        wj.setLimitsEnabled(false)
        assertFalse(wj.isLimitsEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
    }

    @Test fun shift() {
        val b1 = weldBody()
        val b2 = weldBody()
        var wj = WeldJoint<Body>(b1, b2, Vector2(-3.0, 0.5))
        assertEquals(-3.0, wj.getAnchor1().x)
        assertEquals(0.5, wj.getAnchor1().y)
        assertEquals(-3.0, wj.getAnchor2().x)
        assertEquals(0.5, wj.getAnchor2().y)
        wj.shift(Vector2(1.0, 3.0))
        assertEquals(-3.0, wj.getAnchor1().x)
        assertEquals(0.5, wj.getAnchor1().y)
        assertEquals(-3.0, wj.getAnchor2().x)
        assertEquals(0.5, wj.getAnchor2().y)
    }

    @Test fun copyFailed() {
        val b1 = weldBody()
        val b2 = weldBody()
        assertFailsWith<ClassCastException> {
            var b1 = WeldTestBody()
            var b2 = WeldTestBody()
            var wj = WeldJoint<Body>(b1, b2, Vector2(-3.0, 0.5))
            wj.copy()
        }
    }
}
