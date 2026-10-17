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

private fun pinBody() = Body().apply {
    addFixture(Geometry.createCircle(1.0), 1.0, 0.2, 0.0)
    setMass(MassType.NORMAL)
}

private fun pinRadians(degrees: Double) = degrees * PI / 180.0

private class PinTestBody : Body()

class UpstreamPinJointModesCoverageTest {
    @Test fun createSuccess() {
        val b1 = pinBody()
        val b2 = pinBody()
        var p = Vector2(1.0, -1.0)
        var pj = PinJoint<Body>(b1, p)
        assertEquals(p, pj.getAnchor())
        assertNotSame(p, pj.getAnchor())
        assertEquals(0.3, pj.getSpringDampingRatio())
        assertEquals(8.0, pj.getSpringFrequency())
        assertEquals(1000.0, pj.getMaximumSpringForce())
        assertTrue(pj.isSpringDamperEnabled())
        assertTrue(pj.isSpringEnabled())
        assertTrue(pj.isMaximumSpringForceEnabled())
        assertEquals(Joint.SPRING_MODE_FREQUENCY, pj.getSpringMode())
        assertEquals(b1, pj.getBody())
        assertEquals(null, pj.getOwner())
        assertEquals(null, pj.getUserData())
        assertEquals(false, pj.isCollisionAllowed())
        assertEquals(p, pj.getTarget())
        assertNotNull(pj.toString())
    }

    @Test fun createWithNullBody() {
        val b1 = pinBody()
        val b2 = pinBody()
        assertFailsWith<NullPointerException> {
            PinJoint<Body>(null, Vector2())
        }
    }

    @Test fun createWithNullTarget() {
        val b1 = pinBody()
        val b2 = pinBody()
        assertFailsWith<NullPointerException> {
            PinJoint<Body>(b1, null)
        }
    }

    @Test fun setTarget() {
        val b1 = pinBody()
        val b2 = pinBody()
        var pj = PinJoint<Body>(b1, Vector2())
        var v1 = Vector2()
        pj.setTarget(v1)
        assertTrue(v1.equals(pj.getTarget()))
        var v2 = Vector2(2.0, 1.032)
        pj.setTarget(v2)
        assertTrue(v2.equals(pj.getTarget()))
    }

    @Test fun setNullTarget() {
        val b1 = pinBody()
        val b2 = pinBody()
        assertFailsWith<NullPointerException> {
            var pj = PinJoint<Body>(b1, Vector2())
            pj.setTarget(null)
        }
    }

    @Test fun isSpringEnabled() {
        val b1 = pinBody()
        val b2 = pinBody()
        var pj = PinJoint<Body>(b1, Vector2())
        assertTrue(pj.isSpringEnabled())
        pj.setSpringEnabled(false)
        assertFalse(pj.isSpringEnabled())
        pj.setSpringFrequency(1.0)
        assertFalse(pj.isSpringEnabled())
        pj.setSpringFrequency(100.0)
        assertFalse(pj.isSpringEnabled())
        pj.setSpringEnabled(true)
        assertTrue(pj.isSpringEnabled())
        pj.setSpringEnabled(false)
        assertFalse(pj.isSpringEnabled())
    }

    @Test fun isSpringDamperEnabled() {
        val b1 = pinBody()
        val b2 = pinBody()
        var pj = PinJoint<Body>(b1, Vector2())
        assertTrue(pj.isSpringEnabled())
        assertTrue(pj.isSpringDamperEnabled())
        pj.setSpringEnabled(false)
        pj.setSpringDamperEnabled(false)
        assertFalse(pj.isSpringEnabled())
        assertFalse(pj.isSpringDamperEnabled())
        pj.setSpringFrequency(1.0)
        assertFalse(pj.isSpringDamperEnabled())
        pj.setSpringFrequency(100.0)
        assertFalse(pj.isSpringDamperEnabled())
        pj.setSpringDampingRatio(0.4)
        assertFalse(pj.isSpringDamperEnabled())
        pj.setSpringDampingRatio(1.0)
        assertFalse(pj.isSpringDamperEnabled())
        pj.setSpringEnabled(false)
        pj.setSpringDamperEnabled(true)
        assertTrue(pj.isSpringDamperEnabled())
        pj.setSpringEnabled(true)
        pj.setSpringDamperEnabled(true)
        assertTrue(pj.isSpringDamperEnabled())
        pj.setSpringEnabled(true)
        pj.setSpringDamperEnabled(false)
        assertFalse(pj.isSpringDamperEnabled())
    }

    @Test fun setSpringDampingRatio() {
        val b1 = pinBody()
        val b2 = pinBody()
        var pj = PinJoint<Body>(b1, Vector2())
        pj.setSpringDampingRatio(0.0)
        assertEquals(0.0, pj.getSpringDampingRatio())
        pj.setSpringDampingRatio(0.001)
        assertEquals(0.001, pj.getSpringDampingRatio())
        pj.setSpringDampingRatio(1.0)
        assertEquals(1.0, pj.getSpringDampingRatio())
        pj.setSpringDampingRatio(0.2)
        assertEquals(0.2, pj.getSpringDampingRatio())
        pj.setSpringEnabled(false)
        b1.setAtRest(true)
        pj.setSpringDampingRatio(0.5)
        assertTrue(b1.isAtRest())
        pj.setSpringDamperEnabled(true)
        assertTrue(b1.isAtRest())
        pj.setSpringEnabled(true)
        b1.setAtRest(true)
        pj.setSpringDampingRatio(0.5)
        assertTrue(b1.isAtRest())
        pj.setSpringDampingRatio(0.6)
        assertFalse(b1.isAtRest())
    }

    @Test fun setNegativeDampingRatio() {
        val b1 = pinBody()
        val b2 = pinBody()
        assertFailsWith<IllegalArgumentException> {
            var pj = PinJoint<Body>(b1, Vector2())
            pj.setSpringDampingRatio(-1.0)
        }
    }

    @Test fun setDampingRatioGreaterThan1() {
        val b1 = pinBody()
        val b2 = pinBody()
        assertFailsWith<IllegalArgumentException> {
            var pj = PinJoint<Body>(b1, Vector2())
            pj.setSpringDampingRatio(2.0)
        }
    }

    @Test fun setSpringFrequency() {
        val b1 = pinBody()
        val b2 = pinBody()
        var pj = PinJoint<Body>(b1, Vector2())
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
        pj.setSpringFrequency(3.0)
        assertTrue(b1.isAtRest())
        pj.setSpringEnabled(true)
        assertFalse(b1.isAtRest())
        b1.setAtRest(true)
        pj.setSpringFrequency(3.0)
        assertTrue(b1.isAtRest())
        pj.setSpringFrequency(5.0)
        assertFalse(b1.isAtRest())
        b1.setAtRest(true)
        pj.setSpringDamperEnabled(true)
        assertFalse(b1.isAtRest())
    }

    @Test fun setSpringMode() {
        val b1 = pinBody()
        val b2 = pinBody()
        var pj = PinJoint<Body>(b1, Vector2())
        assertEquals(Joint.SPRING_MODE_FREQUENCY, pj.getSpringMode())
        pj.setSpringStiffness(0.3)
        assertEquals(Joint.SPRING_MODE_STIFFNESS, pj.getSpringMode())
        pj.setSpringFrequency(0.5)
        assertEquals(Joint.SPRING_MODE_FREQUENCY, pj.getSpringMode())
    }

    @Test fun setSpringStiffnessNegative() {
        val b1 = pinBody()
        val b2 = pinBody()
        assertFailsWith<IllegalArgumentException> {
            var pj = PinJoint<Body>(b1, Vector2())
            pj.setSpringStiffness(-0.3)
        }
    }

    @Test fun setSpringStiffness() {
        val b1 = pinBody()
        val b2 = pinBody()
        var pj = PinJoint<Body>(b1, Vector2())
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
        pj.setSpringStiffness(3.0)
        assertTrue(b1.isAtRest())
        pj.setSpringEnabled(true)
        assertFalse(b1.isAtRest())
        b1.setAtRest(true)
        pj.setSpringStiffness(3.0)
        assertTrue(b1.isAtRest())
        pj.setSpringStiffness(5.0)
        assertFalse(b1.isAtRest())
        b1.setAtRest(true)
        pj.setSpringDamperEnabled(true)
        assertFalse(b1.isAtRest())
    }

    @Test fun setSpringFrequencyNegative() {
        val b1 = pinBody()
        val b2 = pinBody()
        assertFailsWith<IllegalArgumentException> {
            var pj = PinJoint<Body>(b1, Vector2())
            pj.setSpringFrequency(-0.3)
        }
    }

    @Test fun setSpringMaximumForceNegative() {
        val b1 = pinBody()
        val b2 = pinBody()
        assertFailsWith<IllegalArgumentException> {
            var pj = PinJoint<Body>(b1, Vector2())
            pj.setMaximumSpringForce(-1.0)
        }
    }

    @Test fun setSpringMaximumForce() {
        val b1 = pinBody()
        val b2 = pinBody()
        var pj = PinJoint<Body>(b1, Vector2())
        pj.setMaximumSpringForce(0.0)
        assertEquals(0.0, pj.getMaximumSpringForce())
        pj.setMaximumSpringForce(0.001)
        assertEquals(0.001, pj.getMaximumSpringForce())
        pj.setMaximumSpringForce(1.0)
        assertEquals(1.0, pj.getMaximumSpringForce())
        pj.setMaximumSpringForce(1000.0)
        assertEquals(1000.0, pj.getMaximumSpringForce())
        pj.setSpringEnabled(false)
        b1.setAtRest(true)
        pj.setMaximumSpringForce(0.5)
        assertTrue(b1.isAtRest())
        pj.setMaximumSpringForceEnabled(true)
        assertTrue(b1.isAtRest())
        pj.setSpringEnabled(true)
        b1.setAtRest(true)
        pj.setMaximumSpringForce(0.5)
        assertTrue(b1.isAtRest())
        pj.setMaximumSpringForce(0.6)
        assertFalse(b1.isAtRest())
        b1.setAtRest(true)
        pj.setMaximumSpringForceEnabled(false)
        assertFalse(b1.isAtRest())
    }

    @Test fun shiftCoordinates() {
        val b1 = pinBody()
        val b2 = pinBody()
        var pj = PinJoint<Body>(b1, Vector2())
        pj.setTarget(Vector2(1.0, -1.0))
        pj.shift(Vector2(-1.0, 2.0))
        assertEquals(0.0, pj.getTarget().x, 1.0e-3)
        assertEquals(1.0, pj.getTarget().y, 1.0e-3)
    }

    @Test fun setTargetSleep() {
        val b1 = pinBody()
        val b2 = pinBody()
        var pj = PinJoint<Body>(b1, Vector2())
        var defaultTarget = pj.getTarget()
        assertFalse(b1.isAtRest())
        assertTrue(defaultTarget.equals(pj.getTarget()))
        b1.setAtRest(true)
        pj.setTarget(defaultTarget)
        assertTrue(b1.isAtRest())
        assertTrue(defaultTarget.equals(pj.getTarget()))
        var target = Vector2(1.0, 1.0)
        pj.setTarget(target)
        assertFalse(b1.isAtRest())
        assertTrue(target.equals(pj.getTarget()))
        b1.setAtRest(true)
        pj.setTarget(target)
        assertTrue(b1.isAtRest())
        assertTrue(target.equals(pj.getTarget()))
    }

    @Test fun getSetCorrectionFactor() {
        val b1 = pinBody()
        val b2 = pinBody()
        var pj = PinJoint<Body>(b1, Vector2())
        assertEquals(0.3, pj.getCorrectionFactor())
        pj.setCorrectionFactor(0.0)
        assertEquals(0.0, pj.getCorrectionFactor())
        pj.setCorrectionFactor(0.3)
        assertEquals(0.3, pj.getCorrectionFactor())
        pj.setCorrectionFactor(1.0)
        assertEquals(1.0, pj.getCorrectionFactor())
    }

    @Test fun setNegativeCorrectionFactor() {
        val b1 = pinBody()
        val b2 = pinBody()
        assertFailsWith<IllegalArgumentException> {
            var pj = PinJoint<Body>(b1, Vector2())
            pj.setCorrectionFactor(-1.0)
        }
    }

    @Test fun setGreaterThan1CorrectionFactor() {
        val b1 = pinBody()
        val b2 = pinBody()
        assertFailsWith<IllegalArgumentException> {
            var pj = PinJoint<Body>(b1, Vector2())
            pj.setCorrectionFactor(5.0)
        }
    }

    @Test fun setLessThanZeroCorrectionMaximumForce() {
        val b1 = pinBody()
        val b2 = pinBody()
        assertFailsWith<IllegalArgumentException> {
            var pj = PinJoint<Body>(b1, Vector2())
            pj.setMaximumCorrectionForce(-1.0)
        }
    }

    @Test fun getSetCorrectionMaximumForce() {
        val b1 = pinBody()
        val b2 = pinBody()
        var pj = PinJoint<Body>(b1, Vector2())
        assertEquals(1000.0, pj.getMaximumCorrectionForce())
        pj.setMaximumCorrectionForce(0.0)
        assertEquals(0.0, pj.getMaximumCorrectionForce())
        pj.setMaximumCorrectionForce(0.3)
        assertEquals(0.3, pj.getMaximumCorrectionForce())
        pj.setMaximumCorrectionForce(100.0)
        assertEquals(100.0, pj.getMaximumCorrectionForce())
    }

    @Test fun copyFailed() {
        val b1 = pinBody()
        val b2 = pinBody()
        assertFailsWith<ClassCastException> {
            var b1 = PinTestBody()
            var b2 = PinTestBody()
            var dj = DistanceJoint<Body>(b1, b2, Vector2(), Vector2(0.0, 1.0))
            dj.copy()
        }
    }
}
