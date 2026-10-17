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

private fun frictionBody() = Body().apply {
    addFixture(Geometry.createCircle(1.0), 1.0, 0.2, 0.0)
    setMass(MassType.NORMAL)
}

private fun frictionRadians(degrees: Double) = degrees * PI / 180.0

private class FrictionTestBody : Body()

class UpstreamFrictionJointModesCoverageTest {
    @Test fun createWithTwoDifferentBodies() {
        val b1 = frictionBody()
        val b2 = frictionBody()
        var p = Vector2(1.0, 2.0)
        var fj = FrictionJoint<Body>(b1, b2, p)
        assertEquals(p, fj.getAnchor1())
        assertEquals(p, fj.getAnchor2())
        assertNotSame(p, fj.getAnchor1())
        assertNotSame(p, fj.getAnchor2())
        assertEquals(10.0, fj.getMaximumForce())
        assertEquals(0.25, fj.getMaximumTorque())
        assertEquals(b1, fj.getBody1())
        assertEquals(b2, fj.getBody2())
        assertEquals(null, fj.getOwner())
        assertEquals(null, fj.getUserData())
        assertEquals(b2, fj.getOtherBody(b1))
        assertEquals(false, fj.isCollisionAllowed())
        assertNotNull(fj.toString())
    }

    @Test fun createWithNullBody1() {
        val b1 = frictionBody()
        val b2 = frictionBody()
        assertFailsWith<NullPointerException> {
            FrictionJoint<Body>(null, b2, Vector2())
        }
    }

    @Test fun createWithNullBody2() {
        val b1 = frictionBody()
        val b2 = frictionBody()
        assertFailsWith<NullPointerException> {
            FrictionJoint<Body>(b1, null, Vector2())
        }
    }

    @Test fun createWithNullAnchor() {
        val b1 = frictionBody()
        val b2 = frictionBody()
        assertFailsWith<NullPointerException> {
            FrictionJoint<Body>(b1, b2, null)
        }
    }

    @Test fun createWithSameBody() {
        val b1 = frictionBody()
        val b2 = frictionBody()
        assertFailsWith<IllegalArgumentException> {
            FrictionJoint<Body>(b1, b1, Vector2())
        }
    }

    @Test fun setMaximumTorque() {
        val b1 = frictionBody()
        val b2 = frictionBody()
        var fj = FrictionJoint<Body>(b1, b2, Vector2())
        fj.setMaximumTorque(0.0)
        assertEquals(0.0, fj.getMaximumTorque())
        fj.setMaximumTorque(10.0)
        assertEquals(10.0, fj.getMaximumTorque())
        fj.setMaximumTorque(2548.0)
        assertEquals(2548.0, fj.getMaximumTorque())
    }

    @Test fun setNegativeMaximumTorque() {
        val b1 = frictionBody()
        val b2 = frictionBody()
        assertFailsWith<IllegalArgumentException> {
            var fj = FrictionJoint<Body>(b1, b2, Vector2())
            fj.setMaximumTorque(-2.0)
        }
    }

    @Test fun setMaximumForce() {
        val b1 = frictionBody()
        val b2 = frictionBody()
        var fj = FrictionJoint<Body>(b1, b2, Vector2())
        fj.setMaximumForce(0.0)
        assertEquals(0.0, fj.getMaximumForce())
        fj.setMaximumForce(10.0)
        assertEquals(10.0, fj.getMaximumForce())
        fj.setMaximumForce(2548.0)
        assertEquals(2548.0, fj.getMaximumForce())
    }

    @Test fun setNegativeMaximumForce() {
        val b1 = frictionBody()
        val b2 = frictionBody()
        assertFailsWith<IllegalArgumentException> {
            var fj = FrictionJoint<Body>(b1, b2, Vector2())
            fj.setMaximumForce(-2.0)
        }
    }

    @Test fun shift() {
        val b1 = frictionBody()
        val b2 = frictionBody()
        var fj = FrictionJoint<Body>(b1, b2, Vector2(1.0, 2.0))
        assertEquals(1.0, fj.getAnchor1().x)
        assertEquals(2.0, fj.getAnchor1().y)
        assertEquals(1.0, fj.getAnchor2().x)
        assertEquals(2.0, fj.getAnchor2().y)
        fj.shift(Vector2(1.0, 3.0))
        assertEquals(1.0, fj.getAnchor1().x)
        assertEquals(2.0, fj.getAnchor1().y)
        assertEquals(1.0, fj.getAnchor2().x)
        assertEquals(2.0, fj.getAnchor2().y)
    }

    @Test fun copyFailed() {
        val b1 = frictionBody()
        val b2 = frictionBody()
        assertFailsWith<ClassCastException> {
            var b1 = FrictionTestBody()
            var b2 = FrictionTestBody()
            var fj = FrictionJoint<Body>(b1, b2, Vector2(1.0, 1.0))
            fj.copy()
        }
    }
}
