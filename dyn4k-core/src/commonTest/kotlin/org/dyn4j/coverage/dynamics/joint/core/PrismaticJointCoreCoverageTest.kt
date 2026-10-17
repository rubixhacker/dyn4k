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
package org.dyn4j.coverage.dynamics.joint.core

import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertNotSame
import kotlin.test.assertNull
import kotlin.test.assertSame
import kotlin.test.assertTrue
import org.dyn4j.dynamics.Body
import org.dyn4j.dynamics.joint.PrismaticJoint
import org.dyn4j.dynamics.joint.Joint
import org.dyn4j.exception.CopyException
import org.dyn4j.geometry.Geometry
import org.dyn4j.geometry.MassType
import org.dyn4j.geometry.Vector2

private class PrismaticCoefficientProbe(first: Body, second: Body, anchor: Vector2, axis: Vector2) :
    PrismaticJoint<Body>(first, second, anchor, axis) {
    fun updateCoefficients() = updateSpringCoefficients()
}

class PrismaticJointCoreCoverageTest {
    private lateinit var b1: Body
    private lateinit var b2: Body

    @Test fun createWithNullBody1() { assertFailsWith<NullPointerException> { PrismaticJoint<Body>(null, Body(), Vector2(), Vector2(0.0, 1.0)) } }
    @Test fun createWithNullBody2() { assertFailsWith<NullPointerException> { PrismaticJoint<Body>(Body(), null, Vector2(), Vector2(0.0, 1.0)) } }

    @BeforeTest fun setup() {
        b1 = Body()
        b1.addFixture(Geometry.createCircle(1.0), 1.0, 0.2, 0.0)
        b1.setMass(MassType.NORMAL)
        b2 = Body()
        b2.addFixture(Geometry.createCircle(1.0), 1.0, 0.2, 0.0)
        b2.setMass(MassType.NORMAL)
    }
    @Test fun createSuccess() {
        var anchor = Vector2()
        var axis = Vector2(0.0, 1.0)
        var pj = PrismaticJoint<Body>(b1, b2, anchor, axis)
        assertEquals(anchor, pj.getAnchor1())
        assertEquals(anchor, pj.getAnchor2())
        assertNotSame(anchor, pj.getAnchor1())
        assertNotSame(anchor, pj.getAnchor2())
        assertEquals(axis, pj.getAxis())
        assertNotSame(axis, pj.getAxis())
        assertEquals(1000.0, pj.getMaximumMotorForce())
        assertEquals(0.0, pj.getMotorSpeed())
        assertEquals(0.0, pj.getReferenceAngle())
        assertEquals(0.0, pj.getLowerLimit())
        assertEquals(0.0, pj.getUpperLimit())
        assertEquals(b1, pj.getBody1())
        assertEquals(b2, pj.getBody2())
        assertEquals(null, pj.getOwner())
        assertEquals(null, pj.getUserData())
        assertEquals(b2, pj.getOtherBody(b1))
        assertEquals(false, pj.isCollisionAllowed())
        assertEquals(false, pj.isLowerLimitEnabled())
        assertEquals(false, pj.isUpperLimitEnabled())
        assertEquals(false, pj.isMotorEnabled())
        assertEquals(false, pj.isMaximumMotorForceEnabled())
        assertNotNull(pj.toString())
    }

    @Test fun createWithNullAnchor() {
        assertFailsWith<NullPointerException> { PrismaticJoint<Body>(b1, b2, null, Vector2(0.0, 1.0)) }
    }

    @Test fun createWithNullAxis() {
        assertFailsWith<NullPointerException> { PrismaticJoint<Body>(b1, b2, Vector2(), null) }
    }

    @Test fun setMotorMaximumForce() {
        var pj = PrismaticJoint<Body>(b1, b2, Vector2(), Vector2(0.0, 1.0))
        pj.setMaximumMotorForce(0.0)
        assertEquals(0.0, pj.getMaximumMotorForce())
        pj.setMaximumMotorForce(10.0)
        assertEquals(10.0, pj.getMaximumMotorForce())
        pj.setMaximumMotorForce(2548.0)
        assertEquals(2548.0, pj.getMaximumMotorForce())
    }

    @Test fun setNegativeMaximumMotorForce() {
        var pj = PrismaticJoint<Body>(b1, b2, Vector2(), Vector2(0.0, 1.0))
        assertFailsWith<IllegalArgumentException> { pj.setMaximumMotorForce(-2.0) }
    }

    @Test fun setMotorMaximumForceSleep() {
        var pj = PrismaticJoint<Body>(b1, b2, Vector2(), Vector2(0.0, 1.0))
        assertFalse(pj.isMotorEnabled())
        assertEquals(1000.0, pj.getMaximumMotorForce())
        assertFalse(pj.isMaximumMotorForceEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        pj.setMotorEnabled(true)
        b1.setAtRest(true)
        b2.setAtRest(true)
        pj.setMaximumMotorForce(1000.0)
        assertEquals(1000.0, pj.getMaximumMotorForce())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        pj.setMaximumMotorForce(2.0)
        assertEquals(2.0, pj.getMaximumMotorForce())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        pj.setMaximumMotorForceEnabled(true)
        b1.setAtRest(true)
        b2.setAtRest(true)
        pj.setMaximumMotorForce(2.0)
        assertEquals(2.0, pj.getMaximumMotorForce())
        assertTrue(pj.isMaximumMotorForceEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        pj.setMaximumMotorForce(4.0)
        assertEquals(4.0, pj.getMaximumMotorForce())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        pj.setMotorEnabled(false)
        b1.setAtRest(true)
        b2.setAtRest(true)
        pj.setMaximumMotorForce(1.0)
        assertEquals(1.0, pj.getMaximumMotorForce())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
    }

    @Test fun setMotorEnabled() {
        var pj = PrismaticJoint<Body>(b1, b2, Vector2(), Vector2(0.0, 1.0))
        assertFalse(pj.isMotorEnabled())
        pj.setMotorEnabled(true)
        assertTrue(pj.isMotorEnabled())
        pj.setMotorEnabled(false)
        assertFalse(pj.isMotorEnabled())
    }

    @Test fun setMotorEnabledSleep() {
        var pj = PrismaticJoint<Body>(b1, b2, Vector2(), Vector2(0.0, 1.0))
        assertFalse(pj.isMotorEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        pj.setMotorEnabled(false)
        assertFalse(pj.isMotorEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        pj.setMotorEnabled(true)
        assertTrue(pj.isMotorEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        pj.setMotorEnabled(true)
        assertTrue(pj.isMotorEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        pj.setMotorEnabled(false)
        assertFalse(pj.isMotorEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
    }

    @Test fun setMotorSpeed() {
        var pj = PrismaticJoint<Body>(b1, b2, Vector2(), Vector2(0.0, 1.0))
        assertEquals(0.0, pj.getMotorSpeed())
        pj.setMotorSpeed(2.0)
        assertEquals(2.0, pj.getMotorSpeed())
        pj.setMotorSpeed(-1.0)
        assertEquals(-1.0, pj.getMotorSpeed())
        pj.setMotorSpeed(0.0)
        assertEquals(0.0, pj.getMotorSpeed())
    }

    @Test fun setMotorSpeedSleep() {
        var pj = PrismaticJoint<Body>(b1, b2, Vector2(), Vector2(0.0, 1.0))
        assertFalse(pj.isMotorEnabled())
        assertEquals(0.0, pj.getMotorSpeed())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        pj.setMotorEnabled(true)
        b1.setAtRest(true)
        b2.setAtRest(true)
        pj.setMotorSpeed(0.0)
        assertEquals(0.0, pj.getMotorSpeed())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        pj.setMotorSpeed(2.0)
        assertEquals(2.0, pj.getMotorSpeed())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        pj.setMotorEnabled(false)
        b1.setAtRest(true)
        b2.setAtRest(true)
        pj.setMotorSpeed(-1.0)
        assertEquals(-1.0, pj.getMotorSpeed())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
    }

    @Test fun setReferenceAngle() {
        var pj = PrismaticJoint<Body>(b1, b2, Vector2(), Vector2(0.0, 1.0))
        assertEquals(0.0, pj.getReferenceAngle())
        pj.setReferenceAngle((30.0 * kotlin.math.PI / 180.0))
        assertEquals((30.0 * kotlin.math.PI / 180.0), pj.getReferenceAngle())
    }

    @Test fun shift() {
        var pj = PrismaticJoint<Body>(b1, b2, Vector2(1.0, 1.0), Vector2(0.0, 1.0))
        assertEquals(1.0, pj.getAnchor1().x)
        assertEquals(1.0, pj.getAnchor1().y)
        assertEquals(1.0, pj.getAnchor2().x)
        assertEquals(1.0, pj.getAnchor2().y)
        pj.shift(Vector2(1.0, 3.0))
        assertEquals(1.0, pj.getAnchor1().x)
        assertEquals(1.0, pj.getAnchor1().y)
        assertEquals(1.0, pj.getAnchor2().x)
        assertEquals(1.0, pj.getAnchor2().y)
    }

    @Test fun setUpperLimitSuccess() {
        var pj = PrismaticJoint<Body>(b1, b2, Vector2(), Vector2(0.0, 1.0))
        pj.setLowerLimit(-5.0)
        assertEquals(0.0, pj.getUpperLimit())
        pj.setUpperLimit(2.0)
        assertEquals(2.0, pj.getUpperLimit(), 1e-6)
        pj.setUpperLimit(-2.0)
        assertEquals(-2.0, pj.getUpperLimit(), 1e-6)
        pj.setUpperLimit(0.0)
        assertEquals(0.0, pj.getUpperLimit(), 1e-6)
    }

    @Test fun setUpperLimitInvalid() {
        var pj = PrismaticJoint<Body>(b1, b2, Vector2(), Vector2(0.0, 1.0))
        assertEquals(0.0, pj.getUpperLimit())
        assertFailsWith<IllegalArgumentException> { pj.setUpperLimit(-0.5) }
    }

    @Test fun setLowerLimit() {
        var pj = PrismaticJoint<Body>(b1, b2, Vector2(), Vector2(0.0, 1.0))
        pj.setUpperLimit(5.0)
        assertEquals(0.0, pj.getLowerLimit())
        pj.setLowerLimit(-1.0)
        assertEquals(-1.0, pj.getLowerLimit(), 1e-6)
        pj.setLowerLimit(0.0)
        assertEquals(0.0, pj.getLowerLimit(), 1e-6)
        pj.setLowerLimit(2.0)
        assertEquals(2.0, pj.getLowerLimit(), 1e-6)
    }

    @Test fun setLowerLimitInvalid() {
        var pj = PrismaticJoint<Body>(b1, b2, Vector2(), Vector2(0.0, 1.0))
        assertEquals(0.0, pj.getLowerLimit())
        assertFailsWith<IllegalArgumentException> { pj.setLowerLimit(1.5) }
    }

    @Test fun setUpperAndLowerLimits() {
        var pj = PrismaticJoint<Body>(b1, b2, Vector2(), Vector2(0.0, 1.0))
        assertEquals(0.0, pj.getLowerLimit())
        assertEquals(0.0, pj.getUpperLimit())
        pj.setLimits(0.0, 1.0)
        assertEquals(0.0, pj.getLowerLimit(), 1e-6)
        assertEquals(1.0, pj.getUpperLimit(), 1e-6)
        pj.setLimits(-1.0, 2.0)
        assertEquals(-1.0, pj.getLowerLimit(), 1e-6)
        assertEquals(2.0, pj.getUpperLimit(), 1e-6)
        pj.setLimits(-1.0, -1.0)
        assertEquals(-1.0, pj.getLowerLimit())
        assertEquals(-1.0, pj.getUpperLimit())
        pj.setLimits(-4.0, -1.0)
        assertEquals(-4.0, pj.getLowerLimit())
        assertEquals(-1.0, pj.getUpperLimit())
        pj.setLimits(3.0, 5.0)
        assertEquals(3.0, pj.getLowerLimit())
        assertEquals(5.0, pj.getUpperLimit())
    }

    @Test fun setUpperAndLowerLimitsInvalid1() {
        var pj = PrismaticJoint<Body>(b1, b2, Vector2(), Vector2(0.0, 1.0))
        assertEquals(0.0, pj.getLowerLimit())
        assertEquals(0.0, pj.getUpperLimit())
        assertFailsWith<IllegalArgumentException> { pj.setLimits(1.0, 0.0) }
    }

    @Test fun setUpperAndLowerLimitsInvalid2() {
        var pj = PrismaticJoint<Body>(b1, b2, Vector2(), Vector2(0.0, 1.0))
        assertEquals(0.0, pj.getLowerLimit())
        assertEquals(0.0, pj.getUpperLimit())
        assertFailsWith<IllegalArgumentException> { pj.setLimits(0.0, -1.0) }
    }

    @Test fun setSameLimitValid() {
        var pj = PrismaticJoint<Body>(b1, b2, Vector2(), Vector2(0.0, 1.0))
        assertEquals(0.0, pj.getLowerLimit())
        assertEquals(0.0, pj.getUpperLimit())
        pj.setLimits(2.0)
        assertEquals(2.0, pj.getLowerLimit())
        assertEquals(2.0, pj.getUpperLimit())
        pj.setLimits(-2.0)
        assertEquals(-2.0, pj.getLowerLimit())
        assertEquals(-2.0, pj.getUpperLimit())
    }

    @Test fun setLimitsEnabledSleep() {
        var pj = PrismaticJoint<Body>(b1, b2, Vector2(), Vector2(0.0, 1.0))
        pj.setLowerLimitEnabled(true)
        pj.setUpperLimitEnabled(true)
        assertTrue(pj.isUpperLimitEnabled())
        assertTrue(pj.isLowerLimitEnabled())
        pj.setLimitsEnabled(false)
        assertFalse(pj.isUpperLimitEnabled())
        assertFalse(pj.isLowerLimitEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        pj.setLimitsEnabled(false)
        assertFalse(pj.isUpperLimitEnabled())
        assertFalse(pj.isLowerLimitEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        pj.setLimitsEnabled(true)
        assertTrue(pj.isUpperLimitEnabled())
        assertTrue(pj.isLowerLimitEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        pj.setLimitsEnabled(true)
        assertTrue(pj.isUpperLimitEnabled())
        assertTrue(pj.isLowerLimitEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        pj.setLimitsEnabled(false)
        assertFalse(pj.isUpperLimitEnabled())
        assertFalse(pj.isLowerLimitEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
    }

    @Test fun setLimitsSameSleep() {
        var pj = PrismaticJoint<Body>(b1, b2, Vector2(), Vector2(0.0, 1.0))
        pj.setLowerLimitEnabled(true)
        pj.setUpperLimitEnabled(true)
        assertTrue(pj.isUpperLimitEnabled())
        assertTrue(pj.isLowerLimitEnabled())
        var defaultLowerLimit = pj.getLowerLimit()
        var defaultUpperLimit = pj.getUpperLimit()
        assertEquals(defaultLowerLimit, defaultUpperLimit)
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        pj.setLimits(defaultLowerLimit, defaultUpperLimit)
        assertTrue(pj.isUpperLimitEnabled())
        assertTrue(pj.isLowerLimitEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(defaultLowerLimit, pj.getLowerLimit())
        assertEquals(defaultUpperLimit, pj.getUpperLimit())
        pj.setLimits(2.0)
        assertTrue(pj.isUpperLimitEnabled())
        assertTrue(pj.isLowerLimitEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(2.0, pj.getLowerLimit())
        assertEquals(2.0, pj.getUpperLimit())
        pj.setLowerLimit(0.0)
        assertEquals(0.0, pj.getLowerLimit())
        b1.setAtRest(true)
        b2.setAtRest(true)
        pj.setLimits(2.0)
        assertTrue(pj.isUpperLimitEnabled())
        assertTrue(pj.isLowerLimitEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(2.0, pj.getLowerLimit())
        assertEquals(2.0, pj.getUpperLimit())
        pj.setUpperLimit(3.0)
        assertEquals(3.0, pj.getUpperLimit())
        b1.setAtRest(true)
        b2.setAtRest(true)
        pj.setLimits(2.0)
        assertTrue(pj.isUpperLimitEnabled())
        assertTrue(pj.isLowerLimitEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(2.0, pj.getLowerLimit())
        assertEquals(2.0, pj.getUpperLimit())
        pj.setLimitsEnabled(false)
        b1.setAtRest(true)
        b2.setAtRest(true)
        pj.setLimits(1.0)
        assertFalse(pj.isUpperLimitEnabled())
        assertFalse(pj.isLowerLimitEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(1.0, pj.getLowerLimit())
        assertEquals(1.0, pj.getUpperLimit())
    }

    @Test fun setLimitsDifferentSleep() {
        var pj = PrismaticJoint<Body>(b1, b2, Vector2(), Vector2(0.0, 1.0))
        pj.setLowerLimitEnabled(true)
        pj.setUpperLimitEnabled(true)
        assertTrue(pj.isUpperLimitEnabled())
        assertTrue(pj.isLowerLimitEnabled())
        var defaultLowerLimit = pj.getLowerLimit()
        var defaultUpperLimit = pj.getUpperLimit()
        assertEquals(defaultLowerLimit, defaultUpperLimit)
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        pj.setLimits(defaultLowerLimit, defaultUpperLimit)
        assertTrue(pj.isUpperLimitEnabled())
        assertTrue(pj.isLowerLimitEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(defaultLowerLimit, pj.getLowerLimit())
        assertEquals(defaultUpperLimit, pj.getUpperLimit())
        pj.setLimits(2.0, 3.0)
        assertTrue(pj.isUpperLimitEnabled())
        assertTrue(pj.isLowerLimitEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(2.0, pj.getLowerLimit())
        assertEquals(3.0, pj.getUpperLimit())
        pj.setLowerLimit(1.0)
        assertEquals(1.0, pj.getLowerLimit())
        b1.setAtRest(true)
        b2.setAtRest(true)
        pj.setLimits(0.0, 3.0)
        assertTrue(pj.isUpperLimitEnabled())
        assertTrue(pj.isLowerLimitEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(0.0, pj.getLowerLimit())
        assertEquals(3.0, pj.getUpperLimit())
        pj.setUpperLimit(2.0)
        assertEquals(2.0, pj.getUpperLimit())
        b1.setAtRest(true)
        b2.setAtRest(true)
        pj.setLimits(0.0, 1.0)
        assertTrue(pj.isUpperLimitEnabled())
        assertTrue(pj.isLowerLimitEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(0.0, pj.getLowerLimit())
        assertEquals(1.0, pj.getUpperLimit())
        pj.setLimitsEnabled(false)
        b1.setAtRest(true)
        b2.setAtRest(true)
        pj.setLimits(1.0, 2.0)
        assertFalse(pj.isUpperLimitEnabled())
        assertFalse(pj.isLowerLimitEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(1.0, pj.getLowerLimit())
        assertEquals(2.0, pj.getUpperLimit())
    }

    @Test fun setLowerLimitSleep() {
        var pj = PrismaticJoint<Body>(b1, b2, Vector2(), Vector2(0.0, 1.0))
        pj.setLowerLimitEnabled(true)
        pj.setUpperLimitEnabled(true)
        assertTrue(pj.isLowerLimitEnabled())
        var defaultLowerLimit = pj.getLowerLimit()
        var defaultUpperLimit = pj.getUpperLimit()
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        pj.setLowerLimit(defaultLowerLimit)
        assertTrue(pj.isLowerLimitEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(defaultLowerLimit, pj.getLowerLimit())
        assertEquals(defaultUpperLimit, pj.getUpperLimit())
        pj.setLowerLimit(-0.5)
        assertTrue(pj.isLowerLimitEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(-0.5, pj.getLowerLimit())
        assertEquals(defaultUpperLimit, pj.getUpperLimit())
        pj.setLimitsEnabled(false)
        b1.setAtRest(true)
        b2.setAtRest(true)
        pj.setLowerLimit(-0.2)
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(-0.2, pj.getLowerLimit())
        assertEquals(defaultUpperLimit, pj.getUpperLimit())
    }

    @Test fun setUpperLimitSleep() {
        var pj = PrismaticJoint<Body>(b1, b2, Vector2(), Vector2(0.0, 1.0))
        pj.setLowerLimitEnabled(true)
        pj.setUpperLimitEnabled(true)
        assertTrue(pj.isUpperLimitEnabled())
        var defaultLowerLimit = pj.getLowerLimit()
        var defaultUpperLimit = pj.getUpperLimit()
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        pj.setUpperLimit(defaultUpperLimit)
        assertTrue(pj.isUpperLimitEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(defaultLowerLimit, pj.getLowerLimit())
        assertEquals(defaultUpperLimit, pj.getUpperLimit())
        pj.setUpperLimit(2.0)
        assertTrue(pj.isUpperLimitEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(defaultLowerLimit, pj.getLowerLimit())
        assertEquals(2.0, pj.getUpperLimit())
        pj.setLimitsEnabled(false)
        b1.setAtRest(true)
        b2.setAtRest(true)
        pj.setUpperLimit(3.0)
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(defaultLowerLimit, pj.getLowerLimit())
        assertEquals(3.0, pj.getUpperLimit())
    }

    @Test fun setLimitsEnabledSameSleep() {
        var pj = PrismaticJoint<Body>(b1, b2, Vector2(), Vector2(0.0, 1.0))
        pj.setLowerLimitEnabled(true)
        pj.setUpperLimitEnabled(true)
        assertTrue(pj.isUpperLimitEnabled())
        assertTrue(pj.isLowerLimitEnabled())
        var defaultLowerLimit = pj.getLowerLimit()
        var defaultUpperLimit = pj.getUpperLimit()
        assertEquals(defaultLowerLimit, defaultUpperLimit)
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        pj.setLimitsEnabled(defaultLowerLimit, defaultUpperLimit)
        assertTrue(pj.isUpperLimitEnabled())
        assertTrue(pj.isLowerLimitEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(defaultLowerLimit, pj.getLowerLimit())
        assertEquals(defaultUpperLimit, pj.getUpperLimit())
        pj.setLimitsEnabled(2.0)
        assertTrue(pj.isUpperLimitEnabled())
        assertTrue(pj.isLowerLimitEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(2.0, pj.getLowerLimit())
        assertEquals(2.0, pj.getUpperLimit())
        b1.setAtRest(true)
        b2.setAtRest(true)
        pj.setLimitsEnabled(false)
        pj.setLimitsEnabled(1.0)
        assertTrue(pj.isUpperLimitEnabled())
        assertTrue(pj.isLowerLimitEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(1.0, pj.getLowerLimit())
        assertEquals(1.0, pj.getUpperLimit())
    }

    @Test fun setLimitsEnabledDifferentSleep() {
        var pj = PrismaticJoint<Body>(b1, b2, Vector2(), Vector2(0.0, 1.0))
        pj.setLowerLimitEnabled(true)
        pj.setUpperLimitEnabled(true)
        assertTrue(pj.isUpperLimitEnabled())
        assertTrue(pj.isLowerLimitEnabled())
        var defaultLowerLimit = pj.getLowerLimit()
        var defaultUpperLimit = pj.getUpperLimit()
        assertEquals(defaultLowerLimit, defaultUpperLimit)
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        pj.setLimitsEnabled(defaultLowerLimit, defaultUpperLimit)
        assertTrue(pj.isUpperLimitEnabled())
        assertTrue(pj.isLowerLimitEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(defaultLowerLimit, pj.getLowerLimit())
        assertEquals(defaultUpperLimit, pj.getUpperLimit())
        pj.setLimitsEnabled(0.0, 2.0)
        assertTrue(pj.isUpperLimitEnabled())
        assertTrue(pj.isLowerLimitEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(0.0, pj.getLowerLimit())
        assertEquals(2.0, pj.getUpperLimit())
        pj.setLowerLimit(0.5)
        assertEquals(0.5, pj.getLowerLimit())
        b1.setAtRest(true)
        b2.setAtRest(true)
        pj.setLimitsEnabled(0.0, 2.0)
        assertTrue(pj.isUpperLimitEnabled())
        assertTrue(pj.isLowerLimitEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(0.0, pj.getLowerLimit())
        assertEquals(2.0, pj.getUpperLimit())
        pj.setUpperLimit(3.0)
        assertEquals(3.0, pj.getUpperLimit())
        b1.setAtRest(true)
        b2.setAtRest(true)
        pj.setLimitsEnabled(0.0, 2.0)
        assertTrue(pj.isUpperLimitEnabled())
        assertTrue(pj.isLowerLimitEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(0.0, pj.getLowerLimit())
        assertEquals(2.0, pj.getUpperLimit())
        pj.setLimitsEnabled(false)
        b1.setAtRest(true)
        b2.setAtRest(true)
        pj.setLimitsEnabled(0.5, 4.0)
        assertTrue(pj.isUpperLimitEnabled())
        assertTrue(pj.isLowerLimitEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(0.5, pj.getLowerLimit())
        assertEquals(4.0, pj.getUpperLimit())
    }

    @Test fun isSpringEnabled() {
        var pj = PrismaticJoint<Body>(b1, b2, Vector2(), Vector2(0.0, 1.0))
        assertFalse(pj.isSpringEnabled())
        pj.setSpringFrequency(1.0)
        assertFalse(pj.isSpringEnabled())
        pj.setSpringFrequency(100.0)
        assertFalse(pj.isSpringEnabled())
        pj.setSpringEnabled(true)
        assertTrue(pj.isSpringEnabled())
        pj.setSpringFrequency(50.0)
        assertTrue(pj.isSpringEnabled())
        pj.setSpringEnabled(false)
        assertFalse(pj.isSpringEnabled())
    }

    @Test fun isSpringDamperEnabled() {
        var pj = PrismaticJoint<Body>(b1, b2, Vector2(), Vector2(0.0, 1.0))
        assertFalse(pj.isSpringDamperEnabled())
        pj.setSpringFrequency(1.0)
        assertFalse(pj.isSpringDamperEnabled())
        pj.setSpringFrequency(100.0)
        assertFalse(pj.isSpringDamperEnabled())
        pj.setSpringDampingRatio(0.4)
        assertFalse(pj.isSpringDamperEnabled())
        pj.setSpringDampingRatio(1.0)
        assertFalse(pj.isSpringDamperEnabled())
        pj.setSpringEnabled(true)
        pj.setSpringDamperEnabled(false)
        assertFalse(pj.isSpringDamperEnabled())
        pj.setSpringDamperEnabled(true)
        assertTrue(pj.isSpringDamperEnabled())
        pj.setSpringEnabled(false)
        assertTrue(pj.isSpringDamperEnabled())
    }

    @Test fun setSpringRestOffset() {
        var pj = PrismaticJoint<Body>(b1, b2, Vector2(), Vector2(0.0, 1.0))
        pj.setSpringRestOffset(0.0)
        assertEquals(0.0, pj.getSpringRestOffset())
        pj.setSpringRestOffset(1.0)
        assertEquals(1.0, pj.getSpringRestOffset())
        pj.setSpringRestOffset(-1.0)
        assertEquals(-1.0, pj.getSpringRestOffset())
    }

    @Test fun setSpringDampingRatio() {
        var pj = PrismaticJoint<Body>(b1, b2, Vector2(), Vector2(0.0, 1.0))
        pj.setSpringDampingRatio(0.0)
        assertEquals(0.0, pj.getSpringDampingRatio())
        pj.setSpringDampingRatio(0.001)
        assertEquals(0.001, pj.getSpringDampingRatio())
        pj.setSpringDampingRatio(1.0)
        assertEquals(1.0, pj.getSpringDampingRatio())
        pj.setSpringDampingRatio(0.2)
        assertEquals(0.2, pj.getSpringDampingRatio())
        pj.setSpringEnabled(false)
        pj.setSpringDamperEnabled(false)
        b1.setAtRest(true)
        b2.setAtRest(true)
        pj.setSpringDampingRatio(0.5)
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        pj.setSpringDamperEnabled(true)
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        pj.setSpringEnabled(true)
        b1.setAtRest(true)
        b2.setAtRest(true)
        pj.setSpringDampingRatio(0.5)
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        pj.setSpringDampingRatio(0.6)
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
    }

    @Test fun setNegativeDampingRatio() {
        var pj = PrismaticJoint<Body>(b1, b2, Vector2(), Vector2(0.0, 1.0))
        assertFailsWith<IllegalArgumentException> { pj.setSpringDampingRatio(-1.0) }
    }

    @Test fun setDampingRatioGreaterThan1() {
        var pj = PrismaticJoint<Body>(b1, b2, Vector2(), Vector2(0.0, 1.0))
        assertFailsWith<IllegalArgumentException> { pj.setSpringDampingRatio(2.0) }
    }

    @Test fun setSpringFrequency() {
        var pj = PrismaticJoint<Body>(b1, b2, Vector2(), Vector2(0.0, 1.0))
        pj.setSpringFrequency(0.0)
        assertEquals(0.0, pj.getSpringFrequency())
        pj.setSpringFrequency(0.001)
        assertEquals(0.001, pj.getSpringFrequency())
        assertEquals(Joint.SPRING_MODE_FREQUENCY, pj.getSpringMode())
        pj.setSpringFrequency(1.0)
        assertEquals(1.0, pj.getSpringFrequency())
        pj.setSpringFrequency(29.0)
        assertEquals(29.0, pj.getSpringFrequency())
        pj.setSpringEnabled(false)
        pj.setSpringDamperEnabled(false)
        b1.setAtRest(true)
        b2.setAtRest(true)
        pj.setSpringFrequency(3.0)
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        pj.setSpringEnabled(true)
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        pj.setSpringFrequency(3.0)
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        pj.setSpringFrequency(5.0)
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        pj.setSpringDamperEnabled(true)
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
    }

    @Test fun setSpringMode() {
        var pj = PrismaticJoint<Body>(b1, b2, Vector2(), Vector2(0.0, 1.0))
        assertEquals(Joint.SPRING_MODE_FREQUENCY, pj.getSpringMode())
        pj.setSpringStiffness(0.3)
        assertEquals(Joint.SPRING_MODE_STIFFNESS, pj.getSpringMode())
        pj.setSpringFrequency(0.5)
        assertEquals(Joint.SPRING_MODE_FREQUENCY, pj.getSpringMode())
    }

    @Test fun setSpringStiffnessNegative() {
        var pj = PrismaticJoint<Body>(b1, b2, Vector2(), Vector2(0.0, 1.0))
        assertFailsWith<IllegalArgumentException> { pj.setSpringStiffness(-0.3) }
    }

    @Test fun setSpringStiffness() {
        var pj = PrismaticJoint<Body>(b1, b2, Vector2(), Vector2(0.0, 1.0))
        pj.setSpringStiffness(0.0)
        assertEquals(0.0, pj.getSpringStiffness())
        pj.setSpringStiffness(0.001)
        assertEquals(0.001, pj.getSpringStiffness())
        pj.setSpringStiffness(1.0)
        assertEquals(1.0, pj.getSpringStiffness())
        pj.setSpringStiffness(29.0)
        assertEquals(29.0, pj.getSpringStiffness())
        pj.setSpringEnabled(false)
        pj.setSpringDamperEnabled(false)
        b1.setAtRest(true)
        b2.setAtRest(true)
        pj.setSpringStiffness(3.0)
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        pj.setSpringEnabled(true)
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        pj.setSpringStiffness(3.0)
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        pj.setSpringStiffness(5.0)
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        pj.setSpringDamperEnabled(true)
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
    }

    @Test fun setSpringFrequencyNegative() {
        var pj = PrismaticJoint<Body>(b1, b2, Vector2(), Vector2(0.0, 1.0))
        assertFailsWith<IllegalArgumentException> { pj.setSpringFrequency(-0.3) }
    }

    @Test fun setSpringMaximumForceNegative() {
        var pj = PrismaticJoint<Body>(b1, b2, Vector2(), Vector2(0.0, 1.0))
        assertFailsWith<IllegalArgumentException> { pj.setMaximumSpringForce(-1.0) }
    }

    @Test fun setSpringMaximumForce() {
        var pj = PrismaticJoint<Body>(b1, b2, Vector2(), Vector2(0.0, 1.0))
        pj.setMaximumSpringForce(0.0)
        assertEquals(0.0, pj.getMaximumSpringForce())
        pj.setMaximumSpringForce(0.001)
        assertEquals(0.001, pj.getMaximumSpringForce())
        pj.setMaximumSpringForce(1.0)
        assertEquals(1.0, pj.getMaximumSpringForce())
        pj.setMaximumSpringForce(1000.0)
        assertEquals(1000.0, pj.getMaximumSpringForce())
        pj.setSpringEnabled(false)
        pj.setMaximumSpringForceEnabled(false)
        assertFalse(pj.isMaximumSpringForceEnabled())
        b1.setAtRest(true)
        b2.setAtRest(true)
        pj.setMaximumSpringForce(0.5)
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        pj.setMaximumSpringForceEnabled(true)
        assertTrue(pj.isMaximumSpringForceEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        pj.setSpringEnabled(true)
        b1.setAtRest(true)
        b2.setAtRest(true)
        pj.setMaximumSpringForce(0.5)
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        pj.setMaximumSpringForce(0.6)
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        pj.setMaximumSpringForceEnabled(false)
        assertFalse(pj.isMaximumSpringForceEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
    }

    @Test fun setSpringRestOffsetAtRest() {
        var pj = PrismaticJoint<Body>(b1, b2, Vector2(), Vector2(0.0, 1.0))
        var distance = pj.getSpringRestOffset()
        pj.setSpringEnabled(true)
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(distance, pj.getSpringRestOffset())
        b1.setAtRest(true)
        b2.setAtRest(true)
        pj.setSpringRestOffset(distance)
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(distance, pj.getSpringRestOffset())
        pj.setSpringRestOffset(10.0)
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(10.0, pj.getSpringRestOffset())
    }

    @Test fun computeSpringStiffnessFrequency() {
        val joint = PrismaticCoefficientProbe(b1, b2, Vector2(), Vector2(0.0, 1.0))
        joint.setSpringEnabled(true)
        joint.setSpringDamperEnabled(true)
        joint.setSpringFrequency(8.0)
        joint.setSpringDampingRatio(0.5)
        joint.updateCoefficients()
        assertEquals(8.0, joint.getSpringFrequency())
        assertEquals(0.5, joint.getSpringDampingRatio())
        assertEquals(Joint.SPRING_MODE_FREQUENCY, joint.getSpringMode())
        assertEquals(3968.803, joint.getSpringStiffness(), 1e-3)
        joint.setSpringStiffness(1000.0)
        joint.updateCoefficients()
        assertEquals(4.015, joint.getSpringFrequency(), 1e-3)
        assertEquals(0.5, joint.getSpringDampingRatio())
        assertEquals(Joint.SPRING_MODE_STIFFNESS, joint.getSpringMode())
        assertEquals(1000.0, joint.getSpringStiffness(), 1e-3)
    }

    @Test fun copy() {
        val joint = PrismaticJoint<Body>(b1, b2, Vector2(1.0, 1.0), Vector2(4.0, 1.0))
        joint.setCollisionAllowed(true)
        joint.setOwner(Any())
        joint.setUserData(Any())
        joint.setMaximumSpringForce(3.0)
        joint.setMaximumSpringForceEnabled(true)
        joint.setSpringDamperEnabled(true)
        joint.setSpringDampingRatio(0.5)
        joint.setSpringEnabled(true)
        joint.setSpringFrequency(1.0)
        joint.setLimits(2.0, 4.0)
        joint.setLimitsEnabled(true)
        joint.setMaximumMotorForce(2.0)
        joint.setMaximumMotorForceEnabled(true)
        joint.setMotorEnabled(true)
        joint.setMotorSpeed(8.0)
        joint.setReferenceAngle(10.0 * kotlin.math.PI / 180.0)
        joint.setSpringRestOffset(1.0)
        b2.setLinearVelocity(2.0, 0.0)
        val step = org.dyn4j.dynamics.TimeStep(1.0 / 60.0)
        val settings = org.dyn4j.dynamics.Settings()
        joint.initializeConstraints(step, settings)
        joint.solveVelocityConstraints(step, settings)

        val copy = joint.copy()
        assertNotSame(joint, copy)
        assertNotSame(joint.getBodies(), copy.getBodies())
        assertNotSame(b1, copy.getBody1())
        assertNotSame(b2, copy.getBody2())
        assertSame(copy.getBody1(), copy.getBodies()[0])
        assertSame(copy.getBody2(), copy.getBodies()[1])
        assertEquals(2, copy.getBodyCount())
        assertEquals(Vector2(1.0, 1.0), copy.getAnchor1())
        assertEquals(Vector2(1.0, 1.0), copy.getAnchor2())
        assertEquals(joint.getAxis(), copy.getAxis())
        assertNull(copy.getOwner())
        assertNull(copy.getUserData())
        assertTrue(copy.isCollisionAllowed())
        assertTrue(copy.isLowerLimitEnabled())
        assertTrue(copy.isUpperLimitEnabled())
        assertEquals(2.0, copy.getLowerLimit())
        assertEquals(4.0, copy.getUpperLimit())
        assertTrue(copy.isMotorEnabled())
        assertTrue(copy.isMaximumMotorForceEnabled())
        assertEquals(2.0, copy.getMaximumMotorForce())
        assertEquals(8.0, copy.getMotorSpeed())
        assertEquals(10.0 * kotlin.math.PI / 180.0, copy.getReferenceAngle())
        assertTrue(copy.isSpringEnabled())
        assertTrue(copy.isSpringDamperEnabled())
        assertEquals(0.5, copy.getSpringDampingRatio())
        assertEquals(1.0, copy.getSpringFrequency())
        assertEquals(3.0, copy.getMaximumSpringForce())
        assertTrue(copy.isMaximumSpringForceEnabled())
        assertEquals(Joint.SPRING_MODE_FREQUENCY, copy.getSpringMode())
        assertEquals(1.0, copy.getSpringRestOffset())
        assertEquals(joint.getReactionForce(60.0), copy.getReactionForce(60.0))
        assertEquals(joint.getReactionTorque(60.0), copy.getReactionTorque(60.0))

        val shared = joint.copy(b1, b2)
        assertNotSame(joint.getBodies(), shared.getBodies())
        assertSame(b1, shared.getBody1())
        assertSame(b2, shared.getBody2())
        assertSame(shared.getBody1(), shared.getBodies()[0])
        assertSame(shared.getBody2(), shared.getBodies()[1])
        val firstShared = joint.copy(b1, null)
        assertSame(b1, firstShared.getBody1())
        assertNotSame(b2, firstShared.getBody2())
        assertSame(firstShared.getBody2(), firstShared.getBodies()[1])
        val secondShared = joint.copy(null, b2)
        assertNotSame(b1, secondShared.getBody1())
        assertSame(b2, secondShared.getBody2())
        assertSame(secondShared.getBody1(), secondShared.getBodies()[0])
    }
    @Test fun copyFailed() {
        class SubBody : Body()
        val joint = PrismaticJoint<Body>(SubBody(), SubBody(), Vector2(), Vector2(0.0, 1.0))
        assertFailsWith<CopyException> { joint.copy() }
    }
}
