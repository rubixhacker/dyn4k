/*
 * Copyright (c) 2010-2021 William Bittle  http://www.dyn4j.org/
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

import de.infix.testBalloon.framework.core.testSuite
import org.dyn4j.dynamics.Body
import org.dyn4j.dynamics.BodyFixture
import org.dyn4j.dynamics.joint.FrictionJoint
import org.dyn4j.geometry.Geometry
import org.dyn4j.geometry.MassType
import org.dyn4j.geometry.Vector2
import org.dyn4j.world.World
import kotlin.test.assertEquals
import kotlin.test.assertTrue

val FrictionJointSimulationTest by testSuite {
    test("simulationWithLargeForceTorqueMaximums") { FrictionJointSimulationTestFixture().run { simulationWithLargeForceTorqueMaximums() } }
    test("simulationWithLowForceTorqueMaximums") { FrictionJointSimulationTestFixture().run { simulationWithLowForceTorqueMaximums() } }
}

private class FrictionJointSimulationTestFixture  {
fun simulationWithLargeForceTorqueMaximums() {
        val w = World<Body>()
        w.setGravity(Vector2(0.0, 0.0))
        var g = Body()
        var gf = g.addFixture(Geometry.createRectangle(10.0, 0.5))
        gf.setFriction(0.0)
        g.setMass(MassType.INFINITE)
        g.setLinearDamping(0.0)
        g.setAngularDamping(0.0)
        w.addBody(g)
        var b = Body()
        var bf = b.addFixture(Geometry.createCircle(0.5))
        bf.setFriction(0.0)
        b.setMass(MassType.NORMAL)
        b.translate(0.0, 2.0)
        b.setLinearVelocity(Vector2(4.0, 3.0))
        b.setAngularVelocity(simulationRadians(30.0))
        b.setLinearDamping(0.0)
        b.setAngularDamping(0.0)
        w.addBody(b)
        var fj = FrictionJoint<Body>(g, b, b.getWorldCenter())
        fj.setMaximumForce(1000.0)
        fj.setMaximumTorque(1000.0)
        w.addJoint(fj)
        w.step(1)
        assertTrue(b.getLinearVelocity().getMagnitude() < 5.0)
        assertTrue(b.getAngularVelocity() < simulationRadians(30))
        var invdt = w.getTimeStep().getInverseDeltaTime()
        assertEquals(3.084, fj.getReactionTorque(invdt), 1e-3)
        assertEquals(235.619, fj.getReactionForce(invdt).getMagnitude(), 1e-3)
        w.step(1)
        assertTrue(b.getLinearVelocity().getMagnitude() < 5.0)
        assertTrue(b.getAngularVelocity() < simulationRadians(30))
        assertEquals(0.0, fj.getReactionTorque(invdt), 1e-3)
        assertEquals(0.0, fj.getReactionForce(invdt).getMagnitude(), 1e-3)
    }
fun simulationWithLowForceTorqueMaximums() {
        val w = World<Body>()
        w.setGravity(Vector2(0.0, 0.0))
        var g = Body()
        var gf = g.addFixture(Geometry.createRectangle(10.0, 0.5))
        gf.setFriction(0.0)
        g.setMass(MassType.INFINITE)
        g.setLinearDamping(0.0)
        g.setAngularDamping(0.0)
        w.addBody(g)
        var b = Body()
        var bf = b.addFixture(Geometry.createCircle(0.5))
        bf.setFriction(0.0)
        b.setMass(MassType.NORMAL)
        b.translate(0.0, 2.0)
        b.setLinearVelocity(Vector2(4.0, 3.0))
        b.setAngularVelocity(simulationRadians(30.0))
        b.setLinearDamping(0.0)
        b.setAngularDamping(0.0)
        w.addBody(b)
        var fj = FrictionJoint<Body>(g, b, b.getWorldCenter())
        fj.setMaximumForce(10.0)
        fj.setMaximumTorque(0.25)
        w.addJoint(fj)
        w.step(1)
        var invdt = w.getTimeStep().getInverseDeltaTime()
        assertTrue(b.getLinearVelocity().getMagnitude() < 5.0)
        assertTrue(b.getAngularVelocity() < simulationRadians(30))
        assertEquals(0.25, fj.getReactionTorque(invdt), 1e-3)
        assertEquals(10.0, fj.getReactionForce(invdt).getMagnitude(), 1e-3)
        repeat(12) {
            w.step(1)
        }
        assertTrue(b.getAngularVelocity() < 1e-10)
        repeat(11) {
            w.step(1)
        }
        assertTrue(b.getLinearVelocity().getMagnitude() < 1e-10)
    }
}
