/*
 * Copyright (c) 2010-2020 William Bittle  http://www.dyn4j.org/
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
package org.dyn4j.coverage.simulation

import org.dyn4j.dynamics.Body
import org.dyn4j.dynamics.joint.PinJoint
import org.dyn4j.geometry.Geometry
import org.dyn4j.geometry.MassType
import org.dyn4j.geometry.Vector2
import org.dyn4j.world.World
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class PinJointSimulationTest {
    @Test
    fun fixedLinearVelocity() {
        val w = World<Body>()
        var body = Body()
        body.addFixture(Geometry.createCircle(1.0))
        body.setMass(MassType.FIXED_LINEAR_VELOCITY)
        w.addBody(body)
        var pj = PinJoint<Body>(body, Vector2(0.5, 0.0))
        w.addJoint(pj)
        pj.setTarget(Vector2(0.7, 0.5))
        var invdt = w.getTimeStep().getInverseDeltaTime()
        w.step(1)
        assertTrue(pj.getReactionForce(invdt).getMagnitude() > 0)
        assertTrue(pj.getSpringForce(invdt) > 0.0)
        assertTrue(body.getTransform().getRotationAngle() != 0.0)
        assertEquals(0.0, pj.getReactionTorque(invdt))
    }
    @Test
    fun noSpringDamper() {
        val w = World<Body>()
        var body = Body()
        body.addFixture(Geometry.createCircle(1.0))
        body.setMass(MassType.NORMAL)
        w.addBody(body)
        assertEquals(0.0, body.getWorldCenter().x)
        assertEquals(0.0, body.getWorldCenter().y)
        var pj = PinJoint<Body>(body, Vector2(0.0, 0.0))
        pj.setSpringEnabled(false)
        pj.setSpringDamperEnabled(false)
        pj.setMaximumSpringForceEnabled(false)
        w.addJoint(pj)
        pj.setTarget(Vector2(0.7, 0.5))
        assertEquals(0.0, body.getWorldCenter().x)
        assertEquals(0.0, body.getWorldCenter().y)
        var invdt = w.getTimeStep().getInverseDeltaTime()
        w.step(30)
        assertTrue(pj.getReactionForce(invdt).getMagnitude() > 0)
        assertEquals( 0.0, pj.getReactionTorque(invdt))
        assertEquals( 0.0, pj.getSpringForce(invdt))
        assertEquals(30.754, pj.getCorrectionForce(invdt), 1e-3)
        assertEquals( 0.699, body.getWorldCenter().x, 1e-3)
        assertEquals( 0.499, body.getWorldCenter().y, 1e-3)
    }
}
