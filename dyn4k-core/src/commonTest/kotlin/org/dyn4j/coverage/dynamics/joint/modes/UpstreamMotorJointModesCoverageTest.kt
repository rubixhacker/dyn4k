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

val UpstreamMotorJointModesCoverageTest by testSuite {
    test("createWithTwoDifferentBodies") { UpstreamMotorJointModesCoverageTestFixture().run { createWithTwoDifferentBodies() } }
    test("createWithNullBody2") { UpstreamMotorJointModesCoverageTestFixture().run { createWithNullBody2() } }
    test("createWithNullBody1") { UpstreamMotorJointModesCoverageTestFixture().run { createWithNullBody1() } }
    test("createWithSameBody") { UpstreamMotorJointModesCoverageTestFixture().run { createWithSameBody() } }
    test("setValidCorrectionFactor") { UpstreamMotorJointModesCoverageTestFixture().run { setValidCorrectionFactor() } }
    test("setNegativeCorrectionFactor") { UpstreamMotorJointModesCoverageTestFixture().run { setNegativeCorrectionFactor() } }
    test("setCorrectionFactorGreaterThan1") { UpstreamMotorJointModesCoverageTestFixture().run { setCorrectionFactorGreaterThan1() } }
    test("setMaximumTorque") { UpstreamMotorJointModesCoverageTestFixture().run { setMaximumTorque() } }
    test("setNegativeMaximumTorque") { UpstreamMotorJointModesCoverageTestFixture().run { setNegativeMaximumTorque() } }
    test("setMaximumForce") { UpstreamMotorJointModesCoverageTestFixture().run { setMaximumForce() } }
    test("setNegativeMaximumForce") { UpstreamMotorJointModesCoverageTestFixture().run { setNegativeMaximumForce() } }
    test("setLinearTargetSleep") { UpstreamMotorJointModesCoverageTestFixture().run { setLinearTargetSleep() } }
    test("setAngularTargetSleep") { UpstreamMotorJointModesCoverageTestFixture().run { setAngularTargetSleep() } }
    test("copyFailed") { UpstreamMotorJointModesCoverageTestFixture().run { copyFailed() } }
}

private fun motorBody() = Body().apply {
    addFixture(Geometry.createCircle(1.0), 1.0, 0.2, 0.0)
    setMass(MassType.NORMAL)
}

private fun motorRadians(degrees: Double) = degrees * PI / 180.0

private class MotorTestBody : Body()

private class UpstreamMotorJointModesCoverageTestFixture  {
fun createWithTwoDifferentBodies() {
        val b1 = motorBody()
        val b2 = motorBody()
        var mj = MotorJoint<Body>(b1, b2)
        assertEquals(0.0, mj.getAngularTarget())
        assertEquals(b2.getWorldCenter(), mj.getLinearTarget())
        assertEquals(0.3, mj.getCorrectionFactor())
        assertEquals(1000.0, mj.getMaximumForce())
        assertEquals(1000.0, mj.getMaximumTorque())
        assertEquals(b1, mj.getBody1())
        assertEquals(b2, mj.getBody2())
        assertEquals(null, mj.getOwner())
        assertEquals(null, mj.getUserData())
        assertEquals(b2, mj.getOtherBody(b1))
        assertEquals(false, mj.isCollisionAllowed())
        assertNotNull(mj.toString())
    }

fun createWithNullBody2() {
        val b1 = motorBody()
        val b2 = motorBody()
        assertFailsWith<NullPointerException> {
            MotorJoint<Body>(b1, null)
        }
    }

fun createWithNullBody1() {
        val b1 = motorBody()
        val b2 = motorBody()
        assertFailsWith<NullPointerException> {
            MotorJoint<Body>(null, b2)
        }
    }

fun createWithSameBody() {
        val b1 = motorBody()
        val b2 = motorBody()
        assertFailsWith<IllegalArgumentException> {
            MotorJoint<Body>(b1, b1)
        }
    }

fun setValidCorrectionFactor() {
        val b1 = motorBody()
        val b2 = motorBody()
        var mj = MotorJoint<Body>(b1, b2)
        mj.setCorrectionFactor(0.0)
        assertEquals(0.0, mj.getCorrectionFactor())
        mj.setCorrectionFactor(0.5)
        assertEquals(0.5, mj.getCorrectionFactor())
        mj.setCorrectionFactor(1.0)
        assertEquals(1.0, mj.getCorrectionFactor())
    }

fun setNegativeCorrectionFactor() {
        val b1 = motorBody()
        val b2 = motorBody()
        assertFailsWith<IllegalArgumentException> {
            var mj = MotorJoint<Body>(b1, b2)
            mj.setCorrectionFactor(-1.0)
        }
    }

fun setCorrectionFactorGreaterThan1() {
        val b1 = motorBody()
        val b2 = motorBody()
        assertFailsWith<IllegalArgumentException> {
            var mj = MotorJoint<Body>(b1, b2)
            mj.setCorrectionFactor(1.1)
        }
    }

fun setMaximumTorque() {
        val b1 = motorBody()
        val b2 = motorBody()
        var mj = MotorJoint<Body>(b1, b2)
        mj.setMaximumTorque(0.0)
        assertEquals(0.0, mj.getMaximumTorque())
        mj.setMaximumTorque(10.0)
        assertEquals(10.0, mj.getMaximumTorque())
        mj.setMaximumTorque(2548.0)
        assertEquals(2548.0, mj.getMaximumTorque())
    }

fun setNegativeMaximumTorque() {
        val b1 = motorBody()
        val b2 = motorBody()
        assertFailsWith<IllegalArgumentException> {
            var mj = MotorJoint<Body>(b1, b2)
            mj.setMaximumTorque(-2.0)
        }
    }

fun setMaximumForce() {
        val b1 = motorBody()
        val b2 = motorBody()
        var mj = MotorJoint<Body>(b1, b2)
        mj.setMaximumForce(0.0)
        assertEquals(0.0, mj.getMaximumForce())
        mj.setMaximumForce(10.0)
        assertEquals(10.0, mj.getMaximumForce())
        mj.setMaximumForce(2548.0)
        assertEquals(2548.0, mj.getMaximumForce())
    }

fun setNegativeMaximumForce() {
        val b1 = motorBody()
        val b2 = motorBody()
        assertFailsWith<IllegalArgumentException> {
            var mj = MotorJoint<Body>(b1, b2)
            mj.setMaximumForce(-2.0)
        }
    }

fun setLinearTargetSleep() {
        val b1 = motorBody()
        val b2 = motorBody()
        var mj = MotorJoint<Body>(b1, b2)
        var defaultLinearTarget = mj.getLinearTarget()
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertTrue(defaultLinearTarget.equals(mj.getLinearTarget()))
        b1.setAtRest(true)
        b2.setAtRest(true)
        mj.setLinearTarget(defaultLinearTarget)
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertTrue(defaultLinearTarget.equals(mj.getLinearTarget()))
        var target = Vector2(1.0, 1.0)
        mj.setLinearTarget(target)
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertTrue(target.equals(mj.getLinearTarget()))
        b1.setAtRest(true)
        b2.setAtRest(true)
        mj.setLinearTarget(target)
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertTrue(target.equals(mj.getLinearTarget()))
    }

fun setAngularTargetSleep() {
        val b1 = motorBody()
        val b2 = motorBody()
        var mj = MotorJoint<Body>(b1, b2)
        var defaultAngularTarget = mj.getAngularTarget()
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(defaultAngularTarget, mj.getAngularTarget())
        b1.setAtRest(true)
        b2.setAtRest(true)
        mj.setAngularTarget(defaultAngularTarget)
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(defaultAngularTarget, mj.getAngularTarget())
        mj.setAngularTarget(1.0)
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        assertEquals(1.0, mj.getAngularTarget())
        b1.setAtRest(true)
        b2.setAtRest(true)
        mj.setAngularTarget(1.0)
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        assertEquals(1.0, mj.getAngularTarget())
    }

fun copyFailed() {
        val b1 = motorBody()
        val b2 = motorBody()
        assertFailsWith<ClassCastException> {
            var b1 = MotorTestBody()
            var b2 = MotorTestBody()
            var mj = MotorJoint<Body>(b1, b2)
            mj.copy()
        }
    }
}
