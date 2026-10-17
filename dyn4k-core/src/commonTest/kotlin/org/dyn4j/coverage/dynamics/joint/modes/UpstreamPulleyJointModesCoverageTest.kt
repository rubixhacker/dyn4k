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

private fun pulleyBody() = Body().apply {
    addFixture(Geometry.createCircle(1.0), 1.0, 0.2, 0.0)
    setMass(MassType.NORMAL)
}

private fun pulleyRadians(degrees: Double) = degrees * PI / 180.0

private class PulleyTestBody : Body()

class UpstreamPulleyJointModesCoverageTest {
    @Test fun createSuccess() {
        val b1 = pulleyBody()
        val b2 = pulleyBody()
        var pa1 = Vector2(-1.0, 1.0)
        var pa2 = Vector2(1.0, 1.0)
        var a1 = Vector2(-1.0, 0.0)
        var a2 = Vector2(1.0, 0.0)
        var pj = PulleyJoint<Body>(b1, b2, pa1, pa2, a1, a2)
        assertEquals(pa1, pj.getPulleyAnchor1())
        assertEquals(pa2, pj.getPulleyAnchor2())
        assertNotSame(pa1, pj.getPulleyAnchor1())
        assertNotSame(pa2, pj.getPulleyAnchor2())
        assertEquals(a1, pj.getAnchor1())
        assertEquals(a2, pj.getAnchor2())
        assertNotSame(a1, pj.getAnchor1())
        assertNotSame(a2, pj.getAnchor2())
        assertEquals(pa1.distance(a1) + pa2.distance(a2), pj.getLength())
        assertEquals(pa1.distance(a1), pj.getCurrentLength1())
        assertEquals(pa2.distance(a2), pj.getCurrentLength2())
        assertEquals(1.0, pj.getRatio())
        assertEquals(b1, pj.getBody1())
        assertEquals(b2, pj.getBody2())
        assertEquals(null, pj.getOwner())
        assertEquals(null, pj.getUserData())
        assertEquals(b2, pj.getOtherBody(b1))
        assertEquals(false, pj.isCollisionAllowed())
        assertEquals(false, pj.isSlackEnabled())
        assertNotNull(pj.toString())
    }

    @Test fun createWithNullAnchor1() {
        val b1 = pulleyBody()
        val b2 = pulleyBody()
        assertFailsWith<NullPointerException> {
            PulleyJoint<Body>(b1, b2, null, Vector2(), Vector2(), Vector2())
        }
    }

    @Test fun createWithNullAnchor2() {
        val b1 = pulleyBody()
        val b2 = pulleyBody()
        assertFailsWith<NullPointerException> {
            PulleyJoint<Body>(b1, b2, Vector2(), null, Vector2(), Vector2())
        }
    }

    @Test fun createWithNullAnchor3() {
        val b1 = pulleyBody()
        val b2 = pulleyBody()
        assertFailsWith<NullPointerException> {
            PulleyJoint<Body>(b1, b2, Vector2(), Vector2(), null, Vector2())
        }
    }

    @Test fun createWithNullAnchor4() {
        val b1 = pulleyBody()
        val b2 = pulleyBody()
        assertFailsWith<NullPointerException> {
            PulleyJoint<Body>(b1, b2, Vector2(), Vector2(), Vector2(), null)
        }
    }

    @Test fun createWithSameBody() {
        val b1 = pulleyBody()
        val b2 = pulleyBody()
        assertFailsWith<IllegalArgumentException> {
            PulleyJoint<Body>(b1, b1, Vector2(), Vector2(), Vector2(), Vector2())
        }
    }

    @Test fun setRatio() {
        val b1 = pulleyBody()
        val b2 = pulleyBody()
        var pj = PulleyJoint<Body>(b1, b2, Vector2(), Vector2(), Vector2(), Vector2())
        pj.setRatio(2.0)
        assertEquals(2.0, pj.getRatio())
    }

    @Test fun setRatioNegative() {
        val b1 = pulleyBody()
        val b2 = pulleyBody()
        assertFailsWith<IllegalArgumentException> {
            var pj = PulleyJoint<Body>(b1, b2, Vector2(), Vector2(), Vector2(), Vector2())
            pj.setRatio(-1.0)
        }
    }

    @Test fun setRatioZero() {
        val b1 = pulleyBody()
        val b2 = pulleyBody()
        assertFailsWith<IllegalArgumentException> {
            var pj = PulleyJoint<Body>(b1, b2, Vector2(), Vector2(), Vector2(), Vector2())
            pj.setRatio(0.0)
        }
    }

    @Test fun setRatioSleep() {
        val b1 = pulleyBody()
        val b2 = pulleyBody()
        var pj = PulleyJoint<Body>(b1, b2, Vector2(), Vector2(), Vector2(), Vector2())
        var ratio = pj.getRatio()
        assertEquals(1.0, ratio)
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        pj.setRatio(ratio)
        assertEquals(ratio, pj.getRatio())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        pj.setRatio(2.0)
        assertEquals(2.0, pj.getRatio())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
    }

    @Test fun setSlackEnabled() {
        val b1 = pulleyBody()
        val b2 = pulleyBody()
        var pj = PulleyJoint<Body>(b1, b2, Vector2(), Vector2(), Vector2(), Vector2())
        assertFalse(pj.isSlackEnabled())
        pj.setSlackEnabled(true)
        assertTrue(pj.isSlackEnabled())
        pj.setSlackEnabled(false)
        assertFalse(pj.isSlackEnabled())
    }

    @Test fun setLength() {
        val b1 = pulleyBody()
        val b2 = pulleyBody()
        var pj = PulleyJoint<Body>(b1, b2, Vector2(), Vector2(), Vector2(), Vector2())
        pj.setLength(2.0)
        assertEquals(2.0, pj.getLength())
    }

    @Test fun setLengthNegative() {
        val b1 = pulleyBody()
        val b2 = pulleyBody()
        assertFailsWith<IllegalArgumentException> {
            var pj = PulleyJoint<Body>(b1, b2, Vector2(), Vector2(), Vector2(), Vector2())
            pj.setLength(-1.0)
        }
    }

    @Test fun setLengthSleep() {
        val b1 = pulleyBody()
        val b2 = pulleyBody()
        var pj = PulleyJoint<Body>(b1, b2, Vector2(), Vector2(), Vector2(), Vector2())
        var length = pj.getLength()
        assertEquals(0.0, length)
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
        b1.setAtRest(true)
        b2.setAtRest(true)
        pj.setLength(length)
        assertEquals(length, pj.getLength())
        assertTrue(b1.isAtRest())
        assertTrue(b2.isAtRest())
        pj.setLength(2.0)
        assertEquals(2.0, pj.getLength())
        assertFalse(b1.isAtRest())
        assertFalse(b2.isAtRest())
    }

    @Test fun shiftCoordinates() {
        val b1 = pulleyBody()
        val b2 = pulleyBody()
        var pj = PulleyJoint<Body>(b1, b2, Vector2(1.0, 0.0), Vector2(-1.0, 1.0), Vector2(), Vector2())
        pj.shift(Vector2(-1.0, 2.0))
        assertEquals( 0.0, pj.getPulleyAnchor1().x, 1.0e-3)
        assertEquals( 2.0, pj.getPulleyAnchor1().y, 1.0e-3)
        assertEquals(-2.0, pj.getPulleyAnchor2().x, 1.0e-3)
        assertEquals( 3.0, pj.getPulleyAnchor2().y, 1.0e-3)
    }

    @Test fun copyFailed() {
        val b1 = pulleyBody()
        val b2 = pulleyBody()
        assertFailsWith<ClassCastException> {
            var b1 = PulleyTestBody()
            var b2 = PulleyTestBody()
            var pj = PulleyJoint<Body>(b1, b2, Vector2(1.0, 0.0), Vector2(-1.0, 1.0), Vector2(), Vector2())
            pj.copy()
        }
    }
}
