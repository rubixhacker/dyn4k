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
import org.dyn4j.dynamics.joint.MotorJoint
import org.dyn4j.geometry.Geometry
import org.dyn4j.geometry.MassType
import org.dyn4j.geometry.Vector2
import org.dyn4j.world.World
import kotlin.test.assertEquals
import kotlin.test.assertTrue

val MotorJointSimulationTest by testSuite {
    test("simple") { MotorJointSimulationTestFixture().run { simple() } }
}

private class MotorJointSimulationTestFixture  {
fun simple() {
        val w = World<Body>()
        w.setGravity(Vector2(0.0, 0.0))
        var g = Body()
        var gf = g.addFixture(Geometry.createCircle(0.5))
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
        b.setLinearDamping(0.0)
        b.setAngularDamping(0.0)
        w.addBody(b)
        var mj = MotorJoint<Body>(g, b)
        mj.setLinearTarget(Vector2(0.0, 3.0))
        mj.setAngularTarget(simulationRadians(30))
        mj.setMaximumForce(0.0)
        mj.setMaximumTorque(0.0)
        w.addJoint(mj)
        w.step(25)
        assertEquals(2.0, b.getWorldCenter().distance(g.getWorldCenter()))
        assertEquals(0.0, b.getTransform().getRotationAngle())
        mj.setMaximumForce(100.0)
        mj.setMaximumTorque(10.0)
        w.step(5)
        var invdt = w.getTimeStep().getInverseDeltaTime()
        assertTrue(b.getWorldCenter().distance(g.getWorldCenter()) > 2.0)
        assertTrue(b.getTransform().getRotationAngle() > simulationRadians(5))
        assertEquals(100.0, mj.getReactionForce(invdt).y)
        assertEquals(-10.0, mj.getReactionTorque(invdt))
        w.step(20)
        assertEquals(3.0, b.getWorldCenter().distance(g.getWorldCenter()), 1e-3)
        assertEquals(simulationRadians(30), b.getTransform().getRotationAngle(), 1e-3)
    }
}
