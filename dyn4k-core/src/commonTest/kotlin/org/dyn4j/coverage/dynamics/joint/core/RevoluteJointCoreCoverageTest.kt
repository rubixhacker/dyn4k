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
import org.dyn4j.dynamics.joint.RevoluteJoint
import org.dyn4j.dynamics.joint.Joint
import org.dyn4j.exception.CopyException
import org.dyn4j.geometry.Geometry
import org.dyn4j.geometry.MassType
import org.dyn4j.geometry.Vector2

class RevoluteJointCoreCoverageTest {
    private lateinit var b1: Body
    private lateinit var b2: Body

    @Test fun createWithNullBody1() { assertFailsWith<NullPointerException> { RevoluteJoint<Body>(null, Body(), Vector2()) } }
    @Test fun createWithNullBody2() { assertFailsWith<NullPointerException> { RevoluteJoint<Body>(Body(), null, Vector2()) } }

    @BeforeTest fun setup() {
        b1 = Body()
        b1.addFixture(Geometry.createCircle(1.0), 1.0, 0.2, 0.0)
        b1.setMass(MassType.NORMAL)
        b2 = Body()
        b2.addFixture(Geometry.createCircle(1.0), 1.0, 0.2, 0.0)
        b2.setMass(MassType.NORMAL)
    }
    @Test fun createSuccess() {
        var p = Vector2(1.0, 2.0)
        var rj = RevoluteJoint<Body>(b1, b2, p)
        assertEquals(p, rj.getAnchor1())
        assertEquals(p, rj.getAnchor2())
        assertNotSame(p, rj.getAnchor1())
        assertNotSame(p, rj.getAnchor2())
        assertEquals(0.0, rj.getAngularTranslation())
        assertEquals(1000.0, rj.getMaximumMotorTorque())
        assertEquals(0.0, rj.getMotorSpeed())
        assertEquals(0.0, rj.getLimitsReferenceAngle())
        assertEquals(0.0, rj.getLowerLimit())
        assertEquals(0.0, rj.getUpperLimit())
        assertEquals(b1, rj.getBody1())
        assertEquals(b2, rj.getBody2())
        assertEquals(null, rj.getOwner())
        assertEquals(null, rj.getUserData())
        assertEquals(b2, rj.getOtherBody(b1))
        assertEquals(false, rj.isCollisionAllowed())
        assertEquals(false, rj.isLimitsEnabled())
        assertEquals(false, rj.isMotorEnabled())
        assertEquals(false, rj.isMaximumMotorTorqueEnabled())
        assertNotNull(rj.toString())
    }

    @Test fun createWithNullAnchor() {
        assertFailsWith<NullPointerException> { RevoluteJoint<Body>(b1, b2, null) }
    }

    @Test fun createWithSameBody() {
        assertFailsWith<IllegalArgumentException> { RevoluteJoint<Body>(b1, b1, Vector2()) }
    }

    @Test fun setMaximumMotorTorque() {
        var rj = RevoluteJoint<Body>(b1, b2, Vector2())
        rj.setMaximumMotorTorque(0.0)
        assertEquals(0.0, rj.getMaximumMotorTorque())
        rj.setMaximumMotorTorque(10.0)
        assertEquals(10.0, rj.getMaximumMotorTorque())
        rj.setMaximumMotorTorque(2548.0)
        assertEquals(2548.0, rj.getMaximumMotorTorque())
    }

    @Test fun setMaximumMotorTorqueNegative() {
        var rj = RevoluteJoint<Body>(b1, b2, Vector2())
        assertFailsWith<IllegalArgumentException> { rj.setMaximumMotorTorque(-2.0) }
    }

    @Test fun setMaximumMotorTorqueSleep() {
        var rj = RevoluteJoint<Body>(b1, b2, Vector2())
        assertFalse(rj.isMotorEnabled())
        assertEquals(1000.0, rj.getMaximumMotorTorque())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        rj.setMotorEnabled(true)
        b1.setAtRest(true)
        b2.setAtRest(true)
        rj.setMaximumMotorTorque(1000.0)
        assertEquals(1000.0, rj.getMaximumMotorTorque())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        rj.setMaximumMotorTorque(2.0)
        assertEquals(2.0, rj.getMaximumMotorTorque())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        rj.setMotorEnabled(false)
        b1.setAtRest(true)
        b2.setAtRest(true)
        rj.setMaximumMotorTorque(1.0)
        assertEquals(1.0, rj.getMaximumMotorTorque())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
    }

    @Test fun setMaximumMotorTorqueEnabledSleep() {
        var rj = RevoluteJoint<Body>(b1, b2, Vector2())
        assertFalse(rj.isMotorEnabled())
        assertEquals(1000.0, rj.getMaximumMotorTorque())
        assertFalse(rj.isMaximumMotorTorqueEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        rj.setMotorEnabled(true)
        rj.setMaximumMotorTorqueEnabled(true)
        b1.setAtRest(true)
        b2.setAtRest(true)
        rj.setMaximumMotorTorqueEnabled(true)
        assertTrue(rj.isMaximumMotorTorqueEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        rj.setMaximumMotorTorqueEnabled(false)
        assertFalse(rj.isMaximumMotorTorqueEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        rj.setMotorEnabled(false)
        b1.setAtRest(true)
        b2.setAtRest(true)
        rj.setMaximumMotorTorqueEnabled(true)
        assertTrue(rj.isMaximumMotorTorqueEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
    }

    @Test fun setMotorEnabled() {
        var rj = RevoluteJoint<Body>(b1, b2, Vector2())
        assertFalse(rj.isMotorEnabled())
        rj.setMotorEnabled(true)
        assertTrue(rj.isMotorEnabled())
        rj.setMotorEnabled(false)
        assertFalse(rj.isMotorEnabled())
    }

    @Test fun setMotorEnabledSleep() {
        var rj = RevoluteJoint<Body>(b1, b2, Vector2())
        assertFalse(rj.isMotorEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        rj.setMotorEnabled(false)
        assertFalse(rj.isMotorEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        rj.setMotorEnabled(true)
        assertTrue(rj.isMotorEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        rj.setMotorEnabled(true)
        assertTrue(rj.isMotorEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        rj.setMotorEnabled(false)
        assertFalse(rj.isMotorEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
    }

    @Test fun setMotorSpeed() {
        var rj = RevoluteJoint<Body>(b1, b2, Vector2())
        assertEquals(0.0, rj.getMotorSpeed())
        rj.setMotorSpeed(2.0)
        assertEquals(2.0, rj.getMotorSpeed())
        rj.setMotorSpeed(-1.0)
        assertEquals(-1.0, rj.getMotorSpeed())
        rj.setMotorSpeed(0.0)
        assertEquals(0.0, rj.getMotorSpeed())
    }

    @Test fun setMotorSpeedSleep() {
        var rj = RevoluteJoint<Body>(b1, b2, Vector2())
        assertFalse(rj.isMotorEnabled())
        assertEquals(0.0, rj.getMotorSpeed())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        rj.setMotorEnabled(true)
        b1.setAtRest(true)
        b2.setAtRest(true)
        rj.setMotorSpeed(0.0)
        assertEquals(0.0, rj.getMotorSpeed())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        rj.setMotorSpeed(2.0)
        assertEquals(2.0, rj.getMotorSpeed())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        rj.setMotorEnabled(false)
        b1.setAtRest(true)
        b2.setAtRest(true)
        rj.setMotorSpeed(-1.0)
        assertEquals(-1.0, rj.getMotorSpeed())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
    }

    @Test fun setUpperLimitSuccess() {
        var rj = RevoluteJoint<Body>(b1, b2, Vector2())
        rj.setUpperLimit((10.0 * kotlin.math.PI / 180.0))
        assertEquals((10.0 * kotlin.math.PI / 180.0), rj.getUpperLimit(), 1e-6)
    }

    @Test fun setLowerLimit() {
        var rj = RevoluteJoint<Body>(b1, b2, Vector2())
        rj.setLowerLimit((-10.0 * kotlin.math.PI / 180.0))
        assertEquals((-10.0 * kotlin.math.PI / 180.0), rj.getLowerLimit(), 1e-6)
    }

    @Test fun setUpperAndLowerLimits() {
        var rj = RevoluteJoint<Body>(b1, b2, Vector2())
        rj.setLimits((-30.0 * kotlin.math.PI / 180.0), (20.0 * kotlin.math.PI / 180.0))
        assertEquals((-30.0 * kotlin.math.PI / 180.0), rj.getLowerLimit(), 1e-6)
        assertEquals((20.0 * kotlin.math.PI / 180.0), rj.getUpperLimit(), 1e-6)
    }

    @Test fun setUpperAndLowerLimitsToSameValue() {
        var rj = RevoluteJoint<Body>(b1, b2, Vector2())
        rj.setLimits((30.0 * kotlin.math.PI / 180.0))
        assertEquals((30.0 * kotlin.math.PI / 180.0), rj.getLowerLimit(), 1e-6)
        assertEquals((30.0 * kotlin.math.PI / 180.0), rj.getUpperLimit(), 1e-6)
    }

    @Test fun setLimitsReferenceAngle() {
        var rj = RevoluteJoint<Body>(b1, b2, Vector2())
        assertEquals(0.0, rj.getLimitsReferenceAngle())
        rj.setLimitsReferenceAngle((30.0 * kotlin.math.PI / 180.0))
        assertEquals((30.0 * kotlin.math.PI / 180.0), rj.getLimitsReferenceAngle())
    }

    @Test fun setLimitsReferenceAngleSleep() {
        var rj = RevoluteJoint<Body>(b1, b2, Vector2())
        assertFalse(rj.isLimitsEnabled())
        rj.setLimitsEnabled(true)
        assertTrue(rj.isLimitsEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        rj.setLimitsReferenceAngle(0.0)
        assertTrue(rj.isLimitsEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        rj.setLimitsReferenceAngle(1.0)
        assertTrue(rj.isLimitsEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
    }

    @Test fun setLimitEnabledSleep() {
        var rj = RevoluteJoint<Body>(b1, b2, Vector2())
        assertFalse(rj.isLimitsEnabled())
        rj.setLimitsEnabled(false)
        assertFalse(rj.isLimitsEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        rj.setLimitsEnabled(false)
        assertFalse(rj.isLimitsEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        rj.setLimitsEnabled(true)
        assertTrue(rj.isLimitsEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        rj.setLimitsEnabled(true)
        assertTrue(rj.isLimitsEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        rj.setLimitsEnabled(false)
        assertFalse(rj.isLimitsEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
    }

    @Test fun setLimitsSameSleep() {
        var rj = RevoluteJoint<Body>(b1, b2, Vector2())
        assertFalse(rj.isLimitsEnabled())
        var defaultLowerLimit = rj.getLowerLimit()
        var defaultUpperLimit = rj.getUpperLimit()
        assertEquals(defaultLowerLimit, defaultUpperLimit)
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        rj.setLimitsEnabled(true)
        b1.setAtRest(true)
        b2.setAtRest(true)
        rj.setLimits(defaultLowerLimit)
        assertTrue(rj.isLimitsEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(defaultLowerLimit, rj.getLowerLimit())
        assertEquals(defaultUpperLimit, rj.getUpperLimit())
        rj.setLimits(kotlin.math.PI)
        assertTrue(rj.isLimitsEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(kotlin.math.PI, rj.getLowerLimit())
        assertEquals(kotlin.math.PI, rj.getUpperLimit())
        rj.setLowerLimit(-kotlin.math.PI)
        assertEquals(-kotlin.math.PI, rj.getLowerLimit())
        b1.setAtRest(true)
        b2.setAtRest(true)
        rj.setLimits(kotlin.math.PI)
        assertTrue(rj.isLimitsEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(kotlin.math.PI, rj.getLowerLimit())
        assertEquals(kotlin.math.PI, rj.getUpperLimit())
        rj.setUpperLimit(2*kotlin.math.PI)
        assertEquals(2*kotlin.math.PI, rj.getUpperLimit())
        b1.setAtRest(true)
        b2.setAtRest(true)
        rj.setLimits(kotlin.math.PI)
        assertTrue(rj.isLimitsEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(kotlin.math.PI, rj.getLowerLimit())
        assertEquals(kotlin.math.PI, rj.getUpperLimit())
        rj.setLimitsEnabled(false)
        b1.setAtRest(true)
        b2.setAtRest(true)
        rj.setLimits(-kotlin.math.PI)
        assertFalse(rj.isLimitsEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(-kotlin.math.PI, rj.getLowerLimit())
        assertEquals(-kotlin.math.PI, rj.getUpperLimit())
    }

    @Test fun setLimitsDifferentSleep() {
        var rj = RevoluteJoint<Body>(b1, b2, Vector2())
        assertFalse(rj.isLimitsEnabled())
        var defaultLowerLimit = rj.getLowerLimit()
        var defaultUpperLimit = rj.getUpperLimit()
        assertEquals(defaultLowerLimit, defaultUpperLimit)
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        rj.setLimitsEnabled(true)
        b1.setAtRest(true)
        b2.setAtRest(true)
        rj.setLimits(defaultLowerLimit, defaultUpperLimit)
        assertTrue(rj.isLimitsEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(defaultLowerLimit, rj.getLowerLimit())
        assertEquals(defaultUpperLimit, rj.getUpperLimit())
        rj.setLimits(-kotlin.math.PI, kotlin.math.PI)
        assertTrue(rj.isLimitsEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(-kotlin.math.PI, rj.getLowerLimit())
        assertEquals(kotlin.math.PI, rj.getUpperLimit())
        rj.setLowerLimit(-0.5*kotlin.math.PI)
        assertEquals(-0.5*kotlin.math.PI, rj.getLowerLimit())
        b1.setAtRest(true)
        b2.setAtRest(true)
        rj.setLimits(-kotlin.math.PI, kotlin.math.PI)
        assertTrue(rj.isLimitsEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(-kotlin.math.PI, rj.getLowerLimit())
        assertEquals(kotlin.math.PI, rj.getUpperLimit())
        rj.setUpperLimit(0.5*kotlin.math.PI)
        assertEquals(0.5*kotlin.math.PI, rj.getUpperLimit())
        b1.setAtRest(true)
        b2.setAtRest(true)
        rj.setLimits(-kotlin.math.PI, kotlin.math.PI)
        assertTrue(rj.isLimitsEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(-kotlin.math.PI, rj.getLowerLimit())
        assertEquals(kotlin.math.PI, rj.getUpperLimit())
        rj.setLimitsEnabled(false)
        b1.setAtRest(true)
        b2.setAtRest(true)
        rj.setLimits(kotlin.math.PI, 2*kotlin.math.PI)
        assertFalse(rj.isLimitsEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(kotlin.math.PI, rj.getLowerLimit())
        assertEquals(2*kotlin.math.PI, rj.getUpperLimit())
    }

    @Test fun setLowerLimitSleep() {
        var rj = RevoluteJoint<Body>(b1, b2, Vector2())
        assertFalse(rj.isLimitsEnabled())
        var defaultLowerLimit = rj.getLowerLimit()
        var defaultUpperLimit = rj.getUpperLimit()
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        rj.setLimitsEnabled(true)
        b1.setAtRest(true)
        b2.setAtRest(true)
        rj.setLowerLimit(defaultLowerLimit)
        assertTrue(rj.isLimitsEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(defaultLowerLimit, rj.getLowerLimit())
        assertEquals(defaultUpperLimit, rj.getUpperLimit())
        rj.setLowerLimit(-kotlin.math.PI)
        assertTrue(rj.isLimitsEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(-kotlin.math.PI, rj.getLowerLimit())
        assertEquals(defaultUpperLimit, rj.getUpperLimit())
        rj.setLimitsEnabled(false)
        b1.setAtRest(true)
        b2.setAtRest(true)
        rj.setLowerLimit(-2*kotlin.math.PI)
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(-2*kotlin.math.PI, rj.getLowerLimit())
        assertEquals(defaultUpperLimit, rj.getUpperLimit())
    }

    @Test fun setUpperLimitSleep() {
        var rj = RevoluteJoint<Body>(b1, b2, Vector2())
        assertFalse(rj.isLimitsEnabled())
        var defaultLowerLimit = rj.getLowerLimit()
        var defaultUpperLimit = rj.getUpperLimit()
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        rj.setLimitsEnabled(true)
        b1.setAtRest(true)
        b2.setAtRest(true)
        rj.setUpperLimit(defaultUpperLimit)
        assertTrue(rj.isLimitsEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(defaultLowerLimit, rj.getLowerLimit())
        assertEquals(defaultUpperLimit, rj.getUpperLimit())
        rj.setUpperLimit(kotlin.math.PI)
        assertTrue(rj.isLimitsEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(defaultLowerLimit, rj.getLowerLimit())
        assertEquals(kotlin.math.PI, rj.getUpperLimit())
        rj.setLimitsEnabled(false)
        b1.setAtRest(true)
        b2.setAtRest(true)
        rj.setUpperLimit(2*kotlin.math.PI)
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(defaultLowerLimit, rj.getLowerLimit())
        assertEquals(2*kotlin.math.PI, rj.getUpperLimit())
    }

    @Test fun setLimitsEnabledSameSleep() {
        var rj = RevoluteJoint<Body>(b1, b2, Vector2())
        assertFalse(rj.isLimitsEnabled())
        var defaultLowerLimit = rj.getLowerLimit()
        var defaultUpperLimit = rj.getUpperLimit()
        assertEquals(defaultLowerLimit, defaultUpperLimit)
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        rj.setLimitsEnabled(true)
        b1.setAtRest(true)
        b2.setAtRest(true)
        rj.setLimitsEnabled(defaultLowerLimit)
        assertTrue(rj.isLimitsEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(defaultLowerLimit, rj.getLowerLimit())
        assertEquals(defaultUpperLimit, rj.getUpperLimit())
        rj.setLimitsEnabled(kotlin.math.PI)
        assertTrue(rj.isLimitsEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(kotlin.math.PI, rj.getLowerLimit())
        assertEquals(kotlin.math.PI, rj.getUpperLimit())
        b1.setAtRest(true)
        b2.setAtRest(true)
        rj.setLimitsEnabled(false)
        rj.setLimitsEnabled(kotlin.math.PI)
        assertTrue(rj.isLimitsEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(kotlin.math.PI, rj.getLowerLimit())
        assertEquals(kotlin.math.PI, rj.getUpperLimit())
    }

    @Test fun setLimitsEnabledDifferentSleep() {
        var rj = RevoluteJoint<Body>(b1, b2, Vector2())
        assertFalse(rj.isLimitsEnabled())
        var defaultLowerLimit = rj.getLowerLimit()
        var defaultUpperLimit = rj.getUpperLimit()
        assertEquals(defaultLowerLimit, defaultUpperLimit)
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        rj.setLimitsEnabled(true)
        b1.setAtRest(true)
        b2.setAtRest(true)
        rj.setLimitsEnabled(defaultLowerLimit, defaultUpperLimit)
        assertTrue(rj.isLimitsEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(defaultLowerLimit, rj.getLowerLimit())
        assertEquals(defaultUpperLimit, rj.getUpperLimit())
        rj.setLimitsEnabled(-kotlin.math.PI, kotlin.math.PI)
        assertTrue(rj.isLimitsEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(-kotlin.math.PI, rj.getLowerLimit())
        assertEquals(kotlin.math.PI, rj.getUpperLimit())
        rj.setLowerLimit(-0.5*kotlin.math.PI)
        assertEquals(-0.5*kotlin.math.PI, rj.getLowerLimit())
        b1.setAtRest(true)
        b2.setAtRest(true)
        rj.setLimitsEnabled(-kotlin.math.PI, kotlin.math.PI)
        assertTrue(rj.isLimitsEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(-kotlin.math.PI, rj.getLowerLimit())
        assertEquals(kotlin.math.PI, rj.getUpperLimit())
        rj.setUpperLimit(2*kotlin.math.PI)
        assertEquals(2*kotlin.math.PI, rj.getUpperLimit())
        b1.setAtRest(true)
        b2.setAtRest(true)
        rj.setLimitsEnabled(-kotlin.math.PI, kotlin.math.PI)
        assertTrue(rj.isLimitsEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(-kotlin.math.PI, rj.getLowerLimit())
        assertEquals(kotlin.math.PI, rj.getUpperLimit())
        rj.setLimitsEnabled(false)
        b1.setAtRest(true)
        b2.setAtRest(true)
        rj.setLimitsEnabled(-kotlin.math.PI, kotlin.math.PI)
        assertTrue(rj.isLimitsEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(-kotlin.math.PI, rj.getLowerLimit())
        assertEquals(kotlin.math.PI, rj.getUpperLimit())
    }

    @Test fun setLimitsEnabledSleep() {
        var rj = RevoluteJoint<Body>(b1, b2, Vector2())
        assertFalse(rj.isLimitsEnabled())
        rj.setLimitsEnabled(true)
        rj.setLimitsEnabled(false)
        assertFalse(rj.isLimitsEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        rj.setLimitsEnabled(false)
        assertFalse(rj.isLimitsEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        rj.setLimitsEnabled(true)
        assertTrue(rj.isLimitsEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        rj.setLimitsEnabled(true)
        assertTrue(rj.isLimitsEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        rj.setLimitsEnabled(false)
        assertFalse(rj.isLimitsEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
    }

    @Test fun shift() {
        var rj = RevoluteJoint<Body>(b1, b2, Vector2(-3.0, 0.5))
        assertEquals(-3.0, rj.getAnchor1().x)
        assertEquals(0.5, rj.getAnchor1().y)
        assertEquals(-3.0, rj.getAnchor2().x)
        assertEquals(0.5, rj.getAnchor2().y)
        rj.shift(Vector2(1.0, 3.0))
        assertEquals(-3.0, rj.getAnchor1().x)
        assertEquals(0.5, rj.getAnchor1().y)
        assertEquals(-3.0, rj.getAnchor2().x)
        assertEquals(0.5, rj.getAnchor2().y)
    }

    @Test fun copy() {
        val joint = RevoluteJoint<Body>(b1, b2, Vector2(-3.0, 0.5))
        joint.setCollisionAllowed(true)
        joint.setLimits(2.0, 5.0)
        joint.setLimitsEnabled(true)
        joint.setOwner(Any())
        joint.setUserData(Any())
        joint.setLimitsReferenceAngle(3.0)
        joint.setMaximumMotorTorque(6.0)
        joint.setMaximumMotorTorqueEnabled(true)
        joint.setMotorEnabled(true)
        joint.setMotorSpeed(5.0)
        b2.setAngularVelocity(2.0)
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
        assertEquals(Vector2(-3.0, 0.5), copy.getAnchor1())
        assertEquals(Vector2(-3.0, 0.5), copy.getAnchor2())
        assertNull(copy.getOwner())
        assertNull(copy.getUserData())
        assertTrue(copy.isCollisionAllowed())
        assertTrue(copy.isLimitsEnabled())
        assertEquals(2.0, copy.getLowerLimit())
        assertEquals(5.0, copy.getUpperLimit())
        assertTrue(copy.isMotorEnabled())
        assertEquals(6.0, copy.getMaximumMotorTorque())
        assertTrue(copy.isMaximumMotorTorqueEnabled())
        assertEquals(5.0, copy.getMotorSpeed())
        assertEquals(3.0, copy.getLimitsReferenceAngle())
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
        val joint = RevoluteJoint<Body>(SubBody(), SubBody(), Vector2())
        assertFailsWith<CopyException> { joint.copy() }
    }
}
