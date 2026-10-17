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

private fun angleBody() = Body().apply {
    addFixture(Geometry.createCircle(1.0), 1.0, 0.2, 0.0)
    setMass(MassType.NORMAL)
}

private fun angleRadians(degrees: Double) = degrees * PI / 180.0

private class AngleTestBody : Body()

class UpstreamAngleJointModesCoverageTest {
    @Test fun create() {
        val b1 = angleBody()
        val b2 = angleBody()
        var aj = AngleJoint<Body>(b1, b2)
        assertEquals(0.0, aj.getAngularTranslation())
        assertEquals(1.0, aj.getRatio())
        assertEquals(0.0, aj.getLimitsReferenceAngle())
        assertEquals(0.0, aj.getLowerLimit())
        assertEquals(0.0, aj.getUpperLimit())
        assertEquals(b1, aj.getBody1())
        assertEquals(b2, aj.getBody2())
        assertEquals(null, aj.getOwner())
        assertEquals(null, aj.getUserData())
        assertEquals(b2, aj.getOtherBody(b1))
        assertEquals(false, aj.isCollisionAllowed())
        assertEquals(true, aj.isLimitsEnabled())
        assertNotNull(aj.toString())
    }

    @Test fun setUpperLimitSuccess() {
        val b1 = angleBody()
        val b2 = angleBody()
        var aj = AngleJoint<Body>(b1, b2)
        aj.setUpperLimit(angleRadians(10.0))
        assertEquals(angleRadians(10.0), aj.getUpperLimit(), 1e-6)
    }

    @Test fun setLowerLimit() {
        val b1 = angleBody()
        val b2 = angleBody()
        var aj = AngleJoint<Body>(b1, b2)
        aj.setLowerLimit(angleRadians(-10.0))
        assertEquals(angleRadians(-10.0), aj.getLowerLimit(), 1e-6)
    }

    @Test fun setUpperAndLowerLimits() {
        val b1 = angleBody()
        val b2 = angleBody()
        var aj = AngleJoint<Body>(b1, b2)
        aj.setLimits(angleRadians(-30.0), angleRadians(20.0))
        assertEquals(angleRadians(-30.0), aj.getLowerLimit(), 1e-6)
        assertEquals(angleRadians(20.0), aj.getUpperLimit(), 1e-6)
    }

    @Test fun setUpperAndLowerLimitsToSameValue() {
        val b1 = angleBody()
        val b2 = angleBody()
        var aj = AngleJoint<Body>(b1, b2)
        aj.setLimits(angleRadians(30.0))
        assertEquals(angleRadians(30.0), aj.getLowerLimit(), 1e-6)
        assertEquals(angleRadians(30.0), aj.getUpperLimit(), 1e-6)
    }

    @Test fun setLimitsReferenceAngle() {
        val b1 = angleBody()
        val b2 = angleBody()
        var aj = AngleJoint<Body>(b1, b2)
        assertEquals(0.0, aj.getLimitsReferenceAngle())
        aj.setLimitsReferenceAngle(angleRadians(30.0))
        assertEquals(angleRadians(30.0), aj.getLimitsReferenceAngle())
    }

    @Test fun setRatio() {
        val b1 = angleBody()
        val b2 = angleBody()
        var aj = AngleJoint<Body>(b1, b2)
        assertEquals(1.0, aj.getRatio())
        aj.setRatio(1.5)
        assertEquals(1.5, aj.getRatio())
        aj.setRatio(-1.0)
        assertEquals(-1.0, aj.getRatio())
    }

    @Test fun setRatioZero() {
        val b1 = angleBody()
        val b2 = angleBody()
        assertFailsWith<IllegalArgumentException> {
            var aj = AngleJoint<Body>(b1, b2)
            aj.setRatio(0.0)
        }
    }

    @Test fun setLimitEnabledSleep() {
        val b1 = angleBody()
        val b2 = angleBody()
        var aj = AngleJoint<Body>(b1, b2)
        assertTrue(aj.isLimitsEnabled())
        aj.setLimitsEnabled(false)
        assertFalse(aj.isLimitsEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        aj.setLimitsEnabled(false)
        assertFalse(aj.isLimitsEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        aj.setLimitsEnabled(true)
        assertTrue(aj.isLimitsEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        aj.setLimitsEnabled(true)
        assertTrue(aj.isLimitsEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        aj.setLimitsEnabled(false)
        assertFalse(aj.isLimitsEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
    }

    @Test fun setLimitsSameSleep() {
        val b1 = angleBody()
        val b2 = angleBody()
        var aj = AngleJoint<Body>(b1, b2)
        assertTrue(aj.isLimitsEnabled())
        var defaultLowerLimit = aj.getLowerLimit()
        var defaultUpperLimit = aj.getUpperLimit()
        assertEquals(defaultLowerLimit, defaultUpperLimit)
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        aj.setLimits(defaultLowerLimit)
        assertTrue(aj.isLimitsEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(defaultLowerLimit, aj.getLowerLimit())
        assertEquals(defaultUpperLimit, aj.getUpperLimit())
        aj.setLimits(PI)
        assertTrue(aj.isLimitsEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(PI, aj.getLowerLimit())
        assertEquals(PI, aj.getUpperLimit())
        aj.setLowerLimit(-PI)
        assertEquals(-PI, aj.getLowerLimit())
        b1.setAtRest(true)
        b2.setAtRest(true)
        aj.setLimits(PI)
        assertTrue(aj.isLimitsEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(PI, aj.getLowerLimit())
        assertEquals(PI, aj.getUpperLimit())
        aj.setUpperLimit(2.0*PI)
        assertEquals(2*PI, aj.getUpperLimit())
        b1.setAtRest(true)
        b2.setAtRest(true)
        aj.setLimits(PI)
        assertTrue(aj.isLimitsEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(PI, aj.getLowerLimit())
        assertEquals(PI, aj.getUpperLimit())
        aj.setLimitsEnabled(false)
        b1.setAtRest(true)
        b2.setAtRest(true)
        aj.setLimits(-PI)
        assertFalse(aj.isLimitsEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(-PI, aj.getLowerLimit())
        assertEquals(-PI, aj.getUpperLimit())
    }

    @Test fun setLimitsDifferentSleep() {
        val b1 = angleBody()
        val b2 = angleBody()
        var aj = AngleJoint<Body>(b1, b2)
        assertTrue(aj.isLimitsEnabled())
        var defaultLowerLimit = aj.getLowerLimit()
        var defaultUpperLimit = aj.getUpperLimit()
        assertEquals(defaultLowerLimit, defaultUpperLimit)
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        aj.setLimits(defaultLowerLimit, defaultUpperLimit)
        assertTrue(aj.isLimitsEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(defaultLowerLimit, aj.getLowerLimit())
        assertEquals(defaultUpperLimit, aj.getUpperLimit())
        aj.setLimits(-PI, PI)
        assertTrue(aj.isLimitsEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(-PI, aj.getLowerLimit())
        assertEquals(PI, aj.getUpperLimit())
        aj.setLowerLimit(-2.0*PI)
        assertEquals(-2*PI, aj.getLowerLimit())
        b1.setAtRest(true)
        b2.setAtRest(true)
        aj.setLimits(-PI, PI)
        assertTrue(aj.isLimitsEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(-PI, aj.getLowerLimit())
        assertEquals(PI, aj.getUpperLimit())
        aj.setUpperLimit(2.0*PI)
        assertEquals(2*PI, aj.getUpperLimit())
        b1.setAtRest(true)
        b2.setAtRest(true)
        aj.setLimits(-PI, PI)
        assertTrue(aj.isLimitsEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(-PI, aj.getLowerLimit())
        assertEquals(PI, aj.getUpperLimit())
        aj.setLimitsEnabled(false)
        b1.setAtRest(true)
        b2.setAtRest(true)
        aj.setLimits(PI, 2.0*PI)
        assertFalse(aj.isLimitsEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(PI, aj.getLowerLimit())
        assertEquals(2*PI, aj.getUpperLimit())
    }

    @Test fun setLowerLimitSleep() {
        val b1 = angleBody()
        val b2 = angleBody()
        var aj = AngleJoint<Body>(b1, b2)
        assertTrue(aj.isLimitsEnabled())
        var defaultLowerLimit = aj.getLowerLimit()
        var defaultUpperLimit = aj.getUpperLimit()
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        aj.setLowerLimit(defaultLowerLimit)
        assertTrue(aj.isLimitsEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(defaultLowerLimit, aj.getLowerLimit())
        assertEquals(defaultUpperLimit, aj.getUpperLimit())
        aj.setLowerLimit(-PI)
        assertTrue(aj.isLimitsEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(-PI, aj.getLowerLimit())
        assertEquals(defaultUpperLimit, aj.getUpperLimit())
        aj.setLimitsEnabled(false)
        b1.setAtRest(true)
        b2.setAtRest(true)
        aj.setLowerLimit(-2.0*PI)
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(-2*PI, aj.getLowerLimit())
        assertEquals(defaultUpperLimit, aj.getUpperLimit())
    }

    @Test fun setUpperLimitSleep() {
        val b1 = angleBody()
        val b2 = angleBody()
        var aj = AngleJoint<Body>(b1, b2)
        assertTrue(aj.isLimitsEnabled())
        var defaultLowerLimit = aj.getLowerLimit()
        var defaultUpperLimit = aj.getUpperLimit()
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        aj.setUpperLimit(defaultUpperLimit)
        assertTrue(aj.isLimitsEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(defaultLowerLimit, aj.getLowerLimit())
        assertEquals(defaultUpperLimit, aj.getUpperLimit())
        aj.setUpperLimit(PI)
        assertTrue(aj.isLimitsEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(defaultLowerLimit, aj.getLowerLimit())
        assertEquals(PI, aj.getUpperLimit())
        aj.setLimitsEnabled(false)
        b1.setAtRest(true)
        b2.setAtRest(true)
        aj.setUpperLimit(2.0*PI)
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(defaultLowerLimit, aj.getLowerLimit())
        assertEquals(2*PI, aj.getUpperLimit())
    }

    @Test fun setLimitsEnabledSameSleep() {
        val b1 = angleBody()
        val b2 = angleBody()
        var aj = AngleJoint<Body>(b1, b2)
        assertTrue(aj.isLimitsEnabled())
        var defaultLowerLimit = aj.getLowerLimit()
        var defaultUpperLimit = aj.getUpperLimit()
        assertEquals(defaultLowerLimit, defaultUpperLimit)
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        aj.setLimitsEnabled(defaultLowerLimit)
        assertTrue(aj.isLimitsEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(defaultLowerLimit, aj.getLowerLimit())
        assertEquals(defaultUpperLimit, aj.getUpperLimit())
        aj.setLimitsEnabled(PI)
        assertTrue(aj.isLimitsEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(PI, aj.getLowerLimit())
        assertEquals(PI, aj.getUpperLimit())
        b1.setAtRest(true)
        b2.setAtRest(true)
        aj.setLimitsEnabled(false)
        aj.setLimitsEnabled(PI)
        assertTrue(aj.isLimitsEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(PI, aj.getLowerLimit())
        assertEquals(PI, aj.getUpperLimit())
    }

    @Test fun setLimitsEnabledDifferentSleep() {
        val b1 = angleBody()
        val b2 = angleBody()
        var aj = AngleJoint<Body>(b1, b2)
        assertTrue(aj.isLimitsEnabled())
        var defaultLowerLimit = aj.getLowerLimit()
        var defaultUpperLimit = aj.getUpperLimit()
        assertEquals(defaultLowerLimit, defaultUpperLimit)
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        aj.setLimitsEnabled(defaultLowerLimit, defaultUpperLimit)
        assertTrue(aj.isLimitsEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(defaultLowerLimit, aj.getLowerLimit())
        assertEquals(defaultUpperLimit, aj.getUpperLimit())
        aj.setLimitsEnabled(-PI, PI)
        assertTrue(aj.isLimitsEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(-PI, aj.getLowerLimit())
        assertEquals(PI, aj.getUpperLimit())
        aj.setLowerLimit(-2.0*PI)
        assertEquals(-2*PI, aj.getLowerLimit())
        b1.setAtRest(true)
        b2.setAtRest(true)
        aj.setLimitsEnabled(-PI, PI)
        assertTrue(aj.isLimitsEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(-PI, aj.getLowerLimit())
        assertEquals(PI, aj.getUpperLimit())
        aj.setUpperLimit(2.0*PI)
        assertEquals(2*PI, aj.getUpperLimit())
        b1.setAtRest(true)
        b2.setAtRest(true)
        aj.setLimitsEnabled(-PI, PI)
        assertTrue(aj.isLimitsEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(-PI, aj.getLowerLimit())
        assertEquals(PI, aj.getUpperLimit())
        aj.setLimitsEnabled(false)
        b1.setAtRest(true)
        b2.setAtRest(true)
        aj.setLimitsEnabled(-PI, PI)
        assertTrue(aj.isLimitsEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(-PI, aj.getLowerLimit())
        assertEquals(PI, aj.getUpperLimit())
    }

    @Test fun shift() {
        val b1 = angleBody()
        val b2 = angleBody()
        var aj = AngleJoint<Body>(b1, b2)
        var p1 = b1.getWorldCenter()
        var p2 = b2.getWorldCenter()
        aj.shift(Vector2(1.0, 2.0))
        assertEquals(p1, b1.getWorldCenter())
        assertEquals(p2, b2.getWorldCenter())
    }

    @Test fun copyFailed() {
        val b1 = angleBody()
        val b2 = angleBody()
        assertFailsWith<ClassCastException> {
            var b1 = AngleTestBody()
            var b2 = AngleTestBody()
            val aj = AngleJoint<AngleTestBody>(b1, b2)
            aj.copy()
        }
    }
}
