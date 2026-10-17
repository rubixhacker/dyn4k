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
import org.dyn4j.dynamics.joint.DistanceJoint
import org.dyn4j.dynamics.joint.Joint
import org.dyn4j.exception.CopyException
import org.dyn4j.geometry.Geometry
import org.dyn4j.geometry.MassType
import org.dyn4j.geometry.Vector2

private class DistanceCoefficientProbe(first: Body, second: Body, a1: Vector2, a2: Vector2) :
    DistanceJoint<Body>(first, second, a1, a2) {
    fun updateCoefficients() = updateSpringCoefficients()
}

class DistanceJointCoreCoverageTest {
    private lateinit var b1: Body
    private lateinit var b2: Body

    @BeforeTest fun setup() {
        b1 = Body()
        b1.addFixture(Geometry.createCircle(1.0), 1.0, 0.2, 0.0)
        b1.setMass(MassType.NORMAL)
        b2 = Body()
        b2.addFixture(Geometry.createCircle(1.0), 1.0, 0.2, 0.0)
        b2.setMass(MassType.NORMAL)
    }
    @Test fun createWithTwoDifferentBodies() {
        var p1 = Vector2(1.0, 2.0)
        var p2 = Vector2(-2.0, 5.0)
        var d = p1.distance(p2)
        var dj = DistanceJoint<Body>(b1, b2, p1, p2)
        assertEquals(p1, dj.getAnchor1())
        assertEquals(p2, dj.getAnchor2())
        assertNotSame(p1, dj.getAnchor1())
        assertNotSame(p2, dj.getAnchor2())
        assertEquals(d, dj.getRestDistance())
        assertEquals(d, dj.getCurrentDistance())
        assertEquals(0.3, dj.getSpringDampingRatio())
        assertEquals(8.0, dj.getSpringFrequency())
        assertEquals(1000.0, dj.getMaximumSpringForce())
        assertEquals(0.0, dj.getSpringStiffness())
        assertEquals(Joint.SPRING_MODE_FREQUENCY, dj.getSpringMode())
        assertEquals(d, dj.getLowerLimit())
        assertEquals(d, dj.getUpperLimit())
        assertEquals(b1, dj.getBody1())
        assertEquals(b2, dj.getBody2())
        assertEquals(null, dj.getOwner())
        assertEquals(null, dj.getUserData())
        assertEquals(b2, dj.getOtherBody(b1))
        assertEquals(false, dj.isCollisionAllowed())
        assertEquals(false, dj.isLowerLimitEnabled())
        assertEquals(false, dj.isUpperLimitEnabled())
        assertEquals(false, dj.isSpringDamperEnabled())
        assertEquals(false, dj.isSpringEnabled())
        assertEquals(false, dj.isMaximumSpringForceEnabled())
        assertNotNull(dj.toString())
    }

    @Test fun createWithNullAnchor1Point() {
        assertFailsWith<NullPointerException> { DistanceJoint<Body>(b1, b2, null, Vector2()) }
    }

    @Test fun createWithNullAnchor2Point() {
        assertFailsWith<NullPointerException> { DistanceJoint<Body>(b1, b2, Vector2(), null) }
    }

    @Test fun createWithSameBody() {
        assertFailsWith<IllegalArgumentException> { DistanceJoint<Body>(b1, b1, Vector2(), Vector2()) }
    }

    @Test fun shift() {
        var dj = DistanceJoint<Body>(b1, b2, Vector2(1.0, 2.0), Vector2(-3.0, 0.5))
        assertEquals(1.0, dj.getAnchor1().x)
        assertEquals(2.0, dj.getAnchor1().y)
        assertEquals(-3.0, dj.getAnchor2().x)
        assertEquals(0.5, dj.getAnchor2().y)
        dj.shift(Vector2(1.0, 3.0))
        assertEquals(1.0, dj.getAnchor1().x)
        assertEquals(2.0, dj.getAnchor1().y)
        assertEquals(-3.0, dj.getAnchor2().x)
        assertEquals(0.5, dj.getAnchor2().y)
    }

    @Test fun isSpringEnabled() {
        var dj = DistanceJoint<Body>(b1, b2, Vector2(1.0, 2.0), Vector2(-3.0, 0.5))
        assertFalse(dj.isSpringEnabled())
        dj.setSpringFrequency(1.0)
        assertFalse(dj.isSpringEnabled())
        dj.setSpringFrequency(100.0)
        assertFalse(dj.isSpringEnabled())
        dj.setSpringEnabled(true)
        assertTrue(dj.isSpringEnabled())
        dj.setSpringEnabled(false)
        assertFalse(dj.isSpringEnabled())
    }

    @Test fun isSpringDamperEnabled() {
        var dj = DistanceJoint<Body>(b1, b2, Vector2(1.0, 2.0), Vector2(-3.0, 0.5))
        assertFalse(dj.isSpringDamperEnabled())
        dj.setSpringFrequency(1.0)
        assertFalse(dj.isSpringDamperEnabled())
        dj.setSpringFrequency(100.0)
        assertFalse(dj.isSpringDamperEnabled())
        dj.setSpringDampingRatio(0.4)
        assertFalse(dj.isSpringDamperEnabled())
        dj.setSpringDampingRatio(1.0)
        assertFalse(dj.isSpringDamperEnabled())
        dj.setSpringEnabled(false)
        dj.setSpringDamperEnabled(true)
        assertTrue(dj.isSpringDamperEnabled())
        dj.setSpringEnabled(true)
        dj.setSpringDamperEnabled(true)
        assertTrue(dj.isSpringDamperEnabled())
        dj.setSpringEnabled(true)
        dj.setSpringDamperEnabled(false)
        assertFalse(dj.isSpringDamperEnabled())
    }

    @Test fun setPositiveRestDistance() {
        var dj = DistanceJoint<Body>(b1, b2, Vector2(1.0, 2.0), Vector2(-3.0, 0.5))
        dj.setRestDistance(0.0)
        assertEquals(0.0, dj.getRestDistance())
        dj.setRestDistance(1.0)
        assertEquals(1.0, dj.getRestDistance())
    }

    @Test fun setNegativeRestDistance() {
        var dj = DistanceJoint<Body>(b1, b2, Vector2(1.0, 2.0), Vector2(-3.0, 0.5))
        assertFailsWith<IllegalArgumentException> { dj.setRestDistance(-2.0) }
    }

    @Test fun setSpringDampingRatio() {
        var dj = DistanceJoint<Body>(b1, b2, Vector2(1.0, 2.0), Vector2(-3.0, 0.5))
        dj.setSpringDampingRatio(0.0)
        assertEquals(0.0, dj.getSpringDampingRatio())
        dj.setSpringDampingRatio(0.001)
        assertEquals(0.001, dj.getSpringDampingRatio())
        dj.setSpringDampingRatio(1.0)
        assertEquals(1.0, dj.getSpringDampingRatio())
        dj.setSpringDampingRatio(0.2)
        assertEquals(0.2, dj.getSpringDampingRatio())
        b1.setAtRest(true)
        b2.setAtRest(true)
        dj.setSpringDampingRatio(0.5)
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        dj.setSpringDamperEnabled(true)
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        dj.setSpringEnabled(true)
        b1.setAtRest(true)
        b2.setAtRest(true)
        dj.setSpringDampingRatio(0.5)
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        dj.setSpringDampingRatio(0.6)
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
    }

    @Test fun setNegativeDampingRatio() {
        var dj = DistanceJoint<Body>(b1, b2, Vector2(1.0, 2.0), Vector2(-3.0, 0.5))
        assertFailsWith<IllegalArgumentException> { dj.setSpringDampingRatio(-1.0) }
    }

    @Test fun setDampingRatioGreaterThan1() {
        var dj = DistanceJoint<Body>(b1, b2, Vector2(1.0, 2.0), Vector2(-3.0, 0.5))
        assertFailsWith<IllegalArgumentException> { dj.setSpringDampingRatio(2.0) }
    }

    @Test fun setSpringFrequency() {
        var dj = DistanceJoint<Body>(b1, b2, Vector2(1.0, 2.0), Vector2(-3.0, 0.5))
        dj.setSpringFrequency(0.0)
        assertEquals(0.0, dj.getSpringFrequency())
        dj.setSpringFrequency(0.001)
        assertEquals(0.001, dj.getSpringFrequency())
        assertEquals(Joint.SPRING_MODE_FREQUENCY, dj.getSpringMode())
        dj.setSpringFrequency(1.0)
        assertEquals(1.0, dj.getSpringFrequency())
        dj.setSpringFrequency(29.0)
        assertEquals(29.0, dj.getSpringFrequency())
        b1.setAtRest(true)
        b2.setAtRest(true)
        dj.setSpringFrequency(3.0)
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        dj.setSpringEnabled(true)
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        dj.setSpringFrequency(3.0)
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        dj.setSpringFrequency(5.0)
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        dj.setSpringDamperEnabled(true)
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
    }

    @Test fun setSpringMode() {
        var dj = DistanceJoint<Body>(b1, b2, Vector2(1.0, 2.0), Vector2(-3.0, 0.5))
        assertEquals(Joint.SPRING_MODE_FREQUENCY, dj.getSpringMode())
        dj.setSpringStiffness(0.3)
        assertEquals(Joint.SPRING_MODE_STIFFNESS, dj.getSpringMode())
        dj.setSpringFrequency(0.5)
        assertEquals(Joint.SPRING_MODE_FREQUENCY, dj.getSpringMode())
    }

    @Test fun setSpringStiffnessNegative() {
        var dj = DistanceJoint<Body>(b1, b2, Vector2(1.0, 2.0), Vector2(-3.0, 0.5))
        assertFailsWith<IllegalArgumentException> { dj.setSpringStiffness(-0.3) }
    }

    @Test fun setSpringStiffness() {
        var dj = DistanceJoint<Body>(b1, b2, Vector2(1.0, 2.0), Vector2(-3.0, 0.5))
        dj.setSpringStiffness(0.0)
        assertEquals(0.0, dj.getSpringStiffness())
        dj.setSpringStiffness(0.001)
        assertEquals(0.001, dj.getSpringStiffness())
        dj.setSpringStiffness(1.0)
        assertEquals(1.0, dj.getSpringStiffness())
        dj.setSpringStiffness(29.0)
        assertEquals(29.0, dj.getSpringStiffness())
        b1.setAtRest(true)
        b2.setAtRest(true)
        dj.setSpringStiffness(3.0)
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        dj.setSpringEnabled(true)
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        dj.setSpringStiffness(3.0)
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        dj.setSpringStiffness(5.0)
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        dj.setSpringDamperEnabled(true)
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
    }

    @Test fun setSpringFrequencyNegative() {
        var dj = DistanceJoint<Body>(b1, b2, Vector2(1.0, 2.0), Vector2(-3.0, 0.5))
        assertFailsWith<IllegalArgumentException> { dj.setSpringFrequency(-0.3) }
    }

    @Test fun setSpringMaximumForceNegative() {
        var dj = DistanceJoint<Body>(b1, b2, Vector2(1.0, 2.0), Vector2(-3.0, 0.5))
        assertFailsWith<IllegalArgumentException> { dj.setMaximumSpringForce(-1.0) }
    }

    @Test fun setSpringMaximumForce() {
        var dj = DistanceJoint<Body>(b1, b2, Vector2(1.0, 2.0), Vector2(-3.0, 0.5))
        dj.setMaximumSpringForce(0.0)
        assertEquals(0.0, dj.getMaximumSpringForce())
        dj.setMaximumSpringForce(0.001)
        assertEquals(0.001, dj.getMaximumSpringForce())
        dj.setMaximumSpringForce(1.0)
        assertEquals(1.0, dj.getMaximumSpringForce())
        dj.setMaximumSpringForce(1000.0)
        assertEquals(1000.0, dj.getMaximumSpringForce())
        b1.setAtRest(true)
        b2.setAtRest(true)
        dj.setMaximumSpringForce(0.5)
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        dj.setMaximumSpringForceEnabled(true)
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        dj.setSpringEnabled(true)
        b1.setAtRest(true)
        b2.setAtRest(true)
        dj.setMaximumSpringForce(0.5)
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        dj.setMaximumSpringForce(0.6)
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        dj.setMaximumSpringForceEnabled(false)
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
    }

    @Test fun setDistanceAtRest() {
        var dj = DistanceJoint<Body>(b1, b2, Vector2(1.0, 2.0), Vector2(-3.0, 0.5))
        var distance = dj.getRestDistance()
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(distance, dj.getRestDistance())
        b1.setAtRest(true)
        b2.setAtRest(true)
        dj.setRestDistance(distance)
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(distance, dj.getRestDistance())
        dj.setRestDistance(10.0)
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(10.0, dj.getRestDistance())
    }

    @Test fun setUpperLimitSuccess() {
        var dj = DistanceJoint<Body>(b1, b2, Vector2(), Vector2(0.0, 1.0))
        assertEquals(1.0, dj.getUpperLimit())
        dj.setUpperLimit(2.0)
        assertEquals(2.0, dj.getUpperLimit(), 1e-6)
    }

    @Test fun setUpperLimitNegative() {
        var dj = DistanceJoint<Body>(b1, b2, Vector2(), Vector2(0.0, 1.0))
        assertEquals(1.0, dj.getUpperLimit())
        assertFailsWith<IllegalArgumentException> { dj.setUpperLimit(-1.0) }
    }

    @Test fun setUpperLimitInvalid() {
        var dj = DistanceJoint<Body>(b1, b2, Vector2(), Vector2(0.0, 1.0))
        assertEquals(1.0, dj.getUpperLimit())
        assertFailsWith<IllegalArgumentException> { dj.setUpperLimit(0.5) }
    }

    @Test fun setLowerLimit() {
        var dj = DistanceJoint<Body>(b1, b2, Vector2(), Vector2(0.0, 1.0))
        assertEquals(1.0, dj.getLowerLimit())
        dj.setLowerLimit(0.0)
        assertEquals(0.0, dj.getLowerLimit(), 1e-6)
    }

    @Test fun setLowerLimitNegative() {
        var dj = DistanceJoint<Body>(b1, b2, Vector2(), Vector2(0.0, 1.0))
        assertEquals(1.0, dj.getLowerLimit())
        assertFailsWith<IllegalArgumentException> { dj.setLowerLimit(-1.0) }
    }

    @Test fun setLowerLimitInvalid() {
        var dj = DistanceJoint<Body>(b1, b2, Vector2(), Vector2(0.0, 1.0))
        assertEquals(1.0, dj.getLowerLimit())
        assertFailsWith<IllegalArgumentException> { dj.setLowerLimit(1.5) }
    }

    @Test fun setUpperAndLowerLimits() {
        var dj = DistanceJoint<Body>(b1, b2, Vector2(), Vector2(0.0, 1.0))
        assertEquals(1.0, dj.getLowerLimit())
        assertEquals(1.0, dj.getUpperLimit())
        dj.setLimits(0.0, 1.0)
        assertEquals(0.0, dj.getLowerLimit(), 1e-6)
        assertEquals(1.0, dj.getUpperLimit(), 1e-6)
        dj.setLimits(1.0, 2.0)
        assertEquals(1.0, dj.getLowerLimit(), 1e-6)
        assertEquals(2.0, dj.getUpperLimit(), 1e-6)
        dj.setLimits(1.0, 1.0)
        assertEquals(1.0, dj.getLowerLimit())
        assertEquals(1.0, dj.getUpperLimit())
    }

    @Test fun setUpperAndLowerLimitsInvalid() {
        var dj = DistanceJoint<Body>(b1, b2, Vector2(), Vector2(0.0, 1.0))
        assertEquals(1.0, dj.getLowerLimit())
        assertEquals(1.0, dj.getUpperLimit())
        assertFailsWith<IllegalArgumentException> { dj.setLimits(1.0, 0.0) }
    }

    @Test fun setUpperAndLowerLimitsNegative() {
        var dj = DistanceJoint<Body>(b1, b2, Vector2(), Vector2(0.0, 1.0))
        assertEquals(1.0, dj.getLowerLimit())
        assertEquals(1.0, dj.getUpperLimit())
        assertFailsWith<IllegalArgumentException> { dj.setLimits(-1.0, 0.0) }
    }

    @Test fun setUpperAndLowerLimitsNegative2() {
        var dj = DistanceJoint<Body>(b1, b2, Vector2(), Vector2(0.0, 1.0))
        assertEquals(1.0, dj.getLowerLimit())
        assertEquals(1.0, dj.getUpperLimit())
        assertFailsWith<IllegalArgumentException> { dj.setLimits(0.0, -1.0) }
    }

    @Test fun setSameLimitNegative() {
        var dj = DistanceJoint<Body>(b1, b2, Vector2(), Vector2(0.0, 1.0))
        assertEquals(1.0, dj.getLowerLimit())
        assertEquals(1.0, dj.getUpperLimit())
        assertFailsWith<IllegalArgumentException> { dj.setLimits(-1.0) }
    }

    @Test fun setSameLimitValid() {
        var dj = DistanceJoint<Body>(b1, b2, Vector2(), Vector2(0.0, 1.0))
        assertEquals(1.0, dj.getLowerLimit())
        assertEquals(1.0, dj.getUpperLimit())
        dj.setLimits(2.0)
        assertEquals(2.0, dj.getLowerLimit())
        assertEquals(2.0, dj.getUpperLimit())
    }

    @Test fun setLimitsEnabledSleep() {
        var dj = DistanceJoint<Body>(b1, b2, Vector2(), Vector2(0.0, 1.0))
        dj.setLowerLimitEnabled(true)
        dj.setUpperLimitEnabled(true)
        assertTrue(dj.isUpperLimitEnabled())
        assertTrue(dj.isLowerLimitEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        dj.setLimitsEnabled(false)
        assertFalse(dj.isUpperLimitEnabled())
        assertFalse(dj.isLowerLimitEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        dj.setLimitsEnabled(false)
        assertFalse(dj.isUpperLimitEnabled())
        assertFalse(dj.isLowerLimitEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        dj.setLimitsEnabled(true)
        assertTrue(dj.isUpperLimitEnabled())
        assertTrue(dj.isLowerLimitEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        dj.setLimitsEnabled(true)
        assertTrue(dj.isUpperLimitEnabled())
        assertTrue(dj.isLowerLimitEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        dj.setLimitsEnabled(false)
        assertFalse(dj.isUpperLimitEnabled())
        assertFalse(dj.isLowerLimitEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
    }

    @Test fun setLimitsSameSleep() {
        var dj = DistanceJoint<Body>(b1, b2, Vector2(), Vector2(0.0, 1.0))
        dj.setLowerLimitEnabled(true)
        dj.setUpperLimitEnabled(true)
        assertTrue(dj.isUpperLimitEnabled())
        assertTrue(dj.isLowerLimitEnabled())
        var defaultLowerLimit = dj.getLowerLimit()
        var defaultUpperLimit = dj.getUpperLimit()
        assertEquals(defaultLowerLimit, defaultUpperLimit)
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        dj.setLimits(defaultLowerLimit, defaultUpperLimit)
        assertTrue(dj.isUpperLimitEnabled())
        assertTrue(dj.isLowerLimitEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(defaultLowerLimit, dj.getLowerLimit())
        assertEquals(defaultUpperLimit, dj.getUpperLimit())
        dj.setLimits(2.0)
        assertTrue(dj.isUpperLimitEnabled())
        assertTrue(dj.isLowerLimitEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(2.0, dj.getLowerLimit())
        assertEquals(2.0, dj.getUpperLimit())
        dj.setLowerLimit(0.0)
        assertEquals(0.0, dj.getLowerLimit())
        b1.setAtRest(true)
        b2.setAtRest(true)
        dj.setLimits(2.0)
        assertTrue(dj.isUpperLimitEnabled())
        assertTrue(dj.isLowerLimitEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(2.0, dj.getLowerLimit())
        assertEquals(2.0, dj.getUpperLimit())
        dj.setUpperLimit(3.0)
        assertEquals(3.0, dj.getUpperLimit())
        b1.setAtRest(true)
        b2.setAtRest(true)
        dj.setLimits(2.0)
        assertTrue(dj.isUpperLimitEnabled())
        assertTrue(dj.isLowerLimitEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(2.0, dj.getLowerLimit())
        assertEquals(2.0, dj.getUpperLimit())
        dj.setLimitsEnabled(false)
        b1.setAtRest(true)
        b2.setAtRest(true)
        dj.setLimits(1.0)
        assertFalse(dj.isUpperLimitEnabled())
        assertFalse(dj.isLowerLimitEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(1.0, dj.getLowerLimit())
        assertEquals(1.0, dj.getUpperLimit())
    }

    @Test fun setLimitsDifferentSleep() {
        var dj = DistanceJoint<Body>(b1, b2, Vector2(), Vector2(0.0, 1.0))
        dj.setLowerLimitEnabled(true)
        dj.setUpperLimitEnabled(true)
        assertTrue(dj.isUpperLimitEnabled())
        assertTrue(dj.isLowerLimitEnabled())
        var defaultLowerLimit = dj.getLowerLimit()
        var defaultUpperLimit = dj.getUpperLimit()
        assertEquals(defaultLowerLimit, defaultUpperLimit)
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        dj.setLimits(defaultLowerLimit, defaultUpperLimit)
        assertTrue(dj.isUpperLimitEnabled())
        assertTrue(dj.isLowerLimitEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(defaultLowerLimit, dj.getLowerLimit())
        assertEquals(defaultUpperLimit, dj.getUpperLimit())
        dj.setLimits(2.0, 3.0)
        assertTrue(dj.isUpperLimitEnabled())
        assertTrue(dj.isLowerLimitEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(2.0, dj.getLowerLimit())
        assertEquals(3.0, dj.getUpperLimit())
        dj.setLowerLimit(1.0)
        assertEquals(1.0, dj.getLowerLimit())
        b1.setAtRest(true)
        b2.setAtRest(true)
        dj.setLimits(0.0, 3.0)
        assertTrue(dj.isUpperLimitEnabled())
        assertTrue(dj.isLowerLimitEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(0.0, dj.getLowerLimit())
        assertEquals(3.0, dj.getUpperLimit())
        dj.setUpperLimit(2.0)
        assertEquals(2.0, dj.getUpperLimit())
        b1.setAtRest(true)
        b2.setAtRest(true)
        dj.setLimits(0.0, 1.0)
        assertTrue(dj.isUpperLimitEnabled())
        assertTrue(dj.isLowerLimitEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(0.0, dj.getLowerLimit())
        assertEquals(1.0, dj.getUpperLimit())
        dj.setLimitsEnabled(false)
        b1.setAtRest(true)
        b2.setAtRest(true)
        dj.setLimits(1.0, 2.0)
        assertFalse(dj.isUpperLimitEnabled())
        assertFalse(dj.isLowerLimitEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(1.0, dj.getLowerLimit())
        assertEquals(2.0, dj.getUpperLimit())
    }

    @Test fun setLowerLimitSleep() {
        var dj = DistanceJoint<Body>(b1, b2, Vector2(), Vector2(0.0, 1.0))
        dj.setLowerLimitEnabled(true)
        dj.setUpperLimitEnabled(true)
        assertTrue(dj.isLowerLimitEnabled())
        var defaultLowerLimit = dj.getLowerLimit()
        var defaultUpperLimit = dj.getUpperLimit()
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        dj.setLowerLimit(defaultLowerLimit)
        assertTrue(dj.isLowerLimitEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(defaultLowerLimit, dj.getLowerLimit())
        assertEquals(defaultUpperLimit, dj.getUpperLimit())
        dj.setLowerLimit(0.5)
        assertTrue(dj.isLowerLimitEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(0.5, dj.getLowerLimit())
        assertEquals(defaultUpperLimit, dj.getUpperLimit())
        dj.setLimitsEnabled(false)
        b1.setAtRest(true)
        b2.setAtRest(true)
        dj.setLowerLimit(0.2)
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(0.2, dj.getLowerLimit())
        assertEquals(defaultUpperLimit, dj.getUpperLimit())
    }

    @Test fun setUpperLimitSleep() {
        var dj = DistanceJoint<Body>(b1, b2, Vector2(), Vector2(0.0, 1.0))
        dj.setLowerLimitEnabled(true)
        dj.setUpperLimitEnabled(true)
        assertTrue(dj.isUpperLimitEnabled())
        var defaultLowerLimit = dj.getLowerLimit()
        var defaultUpperLimit = dj.getUpperLimit()
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        dj.setUpperLimit(defaultUpperLimit)
        assertTrue(dj.isUpperLimitEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(defaultLowerLimit, dj.getLowerLimit())
        assertEquals(defaultUpperLimit, dj.getUpperLimit())
        dj.setUpperLimit(2.0)
        assertTrue(dj.isUpperLimitEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(defaultLowerLimit, dj.getLowerLimit())
        assertEquals(2.0, dj.getUpperLimit())
        dj.setLimitsEnabled(false)
        b1.setAtRest(true)
        b2.setAtRest(true)
        dj.setUpperLimit(3.0)
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(defaultLowerLimit, dj.getLowerLimit())
        assertEquals(3.0, dj.getUpperLimit())
    }

    @Test fun setLimitsEnabledSameSleep() {
        var dj = DistanceJoint<Body>(b1, b2, Vector2(), Vector2(0.0, 1.0))
        dj.setLowerLimitEnabled(true)
        dj.setUpperLimitEnabled(true)
        assertTrue(dj.isUpperLimitEnabled())
        assertTrue(dj.isLowerLimitEnabled())
        var defaultLowerLimit = dj.getLowerLimit()
        var defaultUpperLimit = dj.getUpperLimit()
        assertEquals(defaultLowerLimit, defaultUpperLimit)
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        dj.setLimitsEnabled(defaultLowerLimit, defaultUpperLimit)
        assertTrue(dj.isUpperLimitEnabled())
        assertTrue(dj.isLowerLimitEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(defaultLowerLimit, dj.getLowerLimit())
        assertEquals(defaultUpperLimit, dj.getUpperLimit())
        dj.setLimitsEnabled(2.0)
        assertTrue(dj.isUpperLimitEnabled())
        assertTrue(dj.isLowerLimitEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(2.0, dj.getLowerLimit())
        assertEquals(2.0, dj.getUpperLimit())
        b1.setAtRest(true)
        b2.setAtRest(true)
        dj.setLimitsEnabled(false)
        dj.setLimitsEnabled(1.0)
        assertTrue(dj.isUpperLimitEnabled())
        assertTrue(dj.isLowerLimitEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(1.0, dj.getLowerLimit())
        assertEquals(1.0, dj.getUpperLimit())
    }

    @Test fun setLimitsEnabledDifferentSleep() {
        var dj = DistanceJoint<Body>(b1, b2, Vector2(), Vector2(0.0, 1.0))
        dj.setLowerLimitEnabled(true)
        dj.setUpperLimitEnabled(true)
        assertTrue(dj.isUpperLimitEnabled())
        assertTrue(dj.isLowerLimitEnabled())
        var defaultLowerLimit = dj.getLowerLimit()
        var defaultUpperLimit = dj.getUpperLimit()
        assertEquals(defaultLowerLimit, defaultUpperLimit)
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        dj.setLimitsEnabled(defaultLowerLimit, defaultUpperLimit)
        assertTrue(dj.isUpperLimitEnabled())
        assertTrue(dj.isLowerLimitEnabled())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(defaultLowerLimit, dj.getLowerLimit())
        assertEquals(defaultUpperLimit, dj.getUpperLimit())
        dj.setLimitsEnabled(0.0, 2.0)
        assertTrue(dj.isUpperLimitEnabled())
        assertTrue(dj.isLowerLimitEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(0.0, dj.getLowerLimit())
        assertEquals(2.0, dj.getUpperLimit())
        dj.setLowerLimit(0.5)
        assertEquals(0.5, dj.getLowerLimit())
        b1.setAtRest(true)
        b2.setAtRest(true)
        dj.setLimitsEnabled(0.0, 2.0)
        assertTrue(dj.isUpperLimitEnabled())
        assertTrue(dj.isLowerLimitEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(0.0, dj.getLowerLimit())
        assertEquals(2.0, dj.getUpperLimit())
        dj.setUpperLimit(3.0)
        assertEquals(3.0, dj.getUpperLimit())
        b1.setAtRest(true)
        b2.setAtRest(true)
        dj.setLimitsEnabled(0.0, 2.0)
        assertTrue(dj.isUpperLimitEnabled())
        assertTrue(dj.isLowerLimitEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(0.0, dj.getLowerLimit())
        assertEquals(2.0, dj.getUpperLimit())
        dj.setLimitsEnabled(false)
        b1.setAtRest(true)
        b2.setAtRest(true)
        dj.setLimitsEnabled(0.5, 4.0)
        assertTrue(dj.isUpperLimitEnabled())
        assertTrue(dj.isLowerLimitEnabled())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(0.5, dj.getLowerLimit())
        assertEquals(4.0, dj.getUpperLimit())
    }

    @Test fun computeSpringStiffnessFrequency() {
        val joint = DistanceCoefficientProbe(b1, b2, Vector2(1.0, 2.0), Vector2(-3.0, 0.5))
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
        val joint = DistanceJoint<Body>(b1, b2, Vector2(), Vector2(0.0, 1.0))
        joint.setCollisionAllowed(true)
        joint.setLimits(2.0, 5.0)
        joint.setLimitsEnabled(true)
        joint.setOwner(Any())
        joint.setUserData(Any())
        joint.setMaximumSpringForce(3.0)
        joint.setMaximumSpringForceEnabled(true)
        joint.setRestDistance(2.0)
        joint.setSpringDamperEnabled(true)
        joint.setSpringDampingRatio(0.5)
        joint.setSpringEnabled(true)
        joint.setSpringFrequency(1.0)
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
        assertEquals(Vector2(), copy.getAnchor1())
        assertEquals(Vector2(0.0, 1.0), copy.getAnchor2())
        assertNull(copy.getOwner())
        assertNull(copy.getUserData())
        assertTrue(copy.isCollisionAllowed())
        assertTrue(copy.isLowerLimitEnabled())
        assertTrue(copy.isUpperLimitEnabled())
        assertEquals(2.0, copy.getLowerLimit())
        assertEquals(5.0, copy.getUpperLimit())
        assertEquals(2.0, copy.getRestDistance())
        assertTrue(copy.isSpringEnabled())
        assertTrue(copy.isSpringDamperEnabled())
        assertEquals(0.5, copy.getSpringDampingRatio())
        assertEquals(1.0, copy.getSpringFrequency())
        assertEquals(3.0, copy.getMaximumSpringForce())
        assertTrue(copy.isMaximumSpringForceEnabled())
        assertEquals(Joint.SPRING_MODE_FREQUENCY, copy.getSpringMode())
        assertEquals(joint.getCurrentDistance(), copy.getCurrentDistance())
        assertEquals(joint.getReactionForce(60.0), copy.getReactionForce(60.0))

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
        val joint = DistanceJoint<Body>(SubBody(), SubBody(), Vector2(), Vector2(0.0, 1.0))
        assertFailsWith<CopyException> { joint.copy() }
    }
}
