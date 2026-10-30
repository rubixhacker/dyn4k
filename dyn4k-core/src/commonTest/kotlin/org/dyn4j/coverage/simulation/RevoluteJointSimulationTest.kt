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
package org.dyn4j.coverage.simulation

import de.infix.testBalloon.framework.core.testSuite
import org.dyn4j.dynamics.Body
import org.dyn4j.dynamics.BodyFixture
import org.dyn4j.dynamics.joint.RevoluteJoint
import org.dyn4j.geometry.Geometry
import org.dyn4j.geometry.MassType
import org.dyn4j.geometry.Vector2
import org.dyn4j.world.World
import kotlin.test.assertEquals
import kotlin.test.assertTrue

val RevoluteJointSimulationTest by testSuite {
    test("noLimitsNoMotor") { RevoluteJointSimulationTestFixture().run { noLimitsNoMotor() } }
    test("limits") { RevoluteJointSimulationTestFixture().run { limits() } }
    test("motorWithAndWithoutLimits") { RevoluteJointSimulationTestFixture().run { motorWithAndWithoutLimits() } }
}

private class RevoluteJointSimulationTestFixture  {
fun noLimitsNoMotor() {
        val w = World<Body>()
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
        b.setLinearDamping(0.0)
        b.setAngularDamping(0.0)
        w.addBody(b)
        var rj = RevoluteJoint<Body>(g, b, b.getWorldCenter())
        w.addJoint(rj)
        var invdt = w.getTimeStep().getInverseDeltaTime()
        w.step(4)
        var v2 = b.getWorldCenter()
        assertEquals(0.0, v2.x)
        assertEquals(2.0, v2.y)
        assertEquals(7.6969, rj.getReactionForce(invdt).getMagnitude(), 1e-5)
        b.setLinearVelocity(0.0, 1.0)
        w.step(4)
        v2 = b.getWorldCenter()
        assertEquals(0.0, v2.x)
        assertEquals(2.0, v2.y)
        assertEquals(7.6969, rj.getReactionForce(invdt).getMagnitude(), 1e-5)
        b.setLinearVelocity(1.0, 1.0)
        w.step(4)
        v2 = b.getWorldCenter()
        assertEquals(0.0, v2.x)
        assertEquals(2.0, v2.y)
        assertEquals(7.6969, rj.getReactionForce(invdt).getMagnitude(), 1e-5)
        b.applyTorque(simulationRadians(30))
        w.step(1)
        v2 = b.getWorldCenter()
        assertEquals(0.0, v2.x)
        assertEquals(2.0, v2.y)
        assertEquals(0.00148, b.getTransform().getRotationAngle(), 1e-5)
        assertEquals(0.0, rj.getReactionTorque(invdt), 1e-5)
        assertEquals(7.6969, rj.getReactionForce(invdt).getMagnitude(), 1e-5)
    }
fun limits() {
        val w = World<Body>()
        w.setGravity(Vector2(0.0, 0.0))
        w.getSettings().setAngularTolerance(0.0)
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
        b.setLinearDamping(0.0)
        b.setAngularDamping(0.0)
        w.addBody(b)
        var rj = RevoluteJoint<Body>(g, b, b.getWorldCenter())
        rj.setLimitsEnabled(-simulationRadians(30), simulationRadians(30))
        w.addJoint(rj)
        assertEquals(0.0, b.getAngularVelocity())
        assertEquals(0.0, rj.getAngularTranslation())
        assertEquals(0.0, b.getTransform().getRotationAngle())
        assertEquals(0.0, rj.getLimitsReferenceAngle())
        b.setAngularVelocity(simulationRadians(10))
        w.step(1)
        var invdt = w.getTimeStep().getInverseDeltaTime()
        assertEquals(0.00290, b.getTransform().getRotationAngle(), 1e-5)
        assertEquals(0.17453, b.getAngularVelocity(), 1e-5)
        assertEquals(0.17453, rj.getAngularSpeed(), 1e-3)
        assertEquals(0.00290, rj.getAngularTranslation(), 1e-3)
        assertEquals(0.0, rj.getReactionTorque(invdt), 1e-3)
        rj.setLimitsEnabled(simulationRadians(10), simulationRadians(30))
        w.step(1)
        assertEquals(0.17453, b.getTransform().getRotationAngle(), 1e-5)
        assertEquals(0.17453, b.getAngularVelocity(), 1e-5)
        assertEquals(0.17453, rj.getAngularSpeed(), 1e-3)
        assertEquals(0.17453, rj.getAngularTranslation(), 1e-3)
        assertEquals(0.0, rj.getReactionTorque(invdt), 1e-3)
        b.setAngularVelocity(-simulationRadians(10))
        rj.setLimitsEnabled(-simulationRadians(30), simulationRadians(5))
        w.step(1)
        assertEquals( 0.08726, b.getTransform().getRotationAngle(), 1e-5)
        assertEquals(-0.17453, b.getAngularVelocity(), 1e-5)
        assertEquals(-0.17453, rj.getAngularSpeed(), 1e-3)
        assertEquals( 0.08726, rj.getAngularTranslation(), 1e-3)
        assertEquals( 0.0, rj.getReactionTorque(invdt), 1e-3)
    }
fun motorWithAndWithoutLimits() {
        val w = World<Body>()
        w.setGravity(Vector2(0.0, 0.0))
        w.getSettings().setAngularTolerance(0.0)
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
        b.setLinearDamping(0.0)
        b.setAngularDamping(0.0)
        w.addBody(b)
        var rj = RevoluteJoint<Body>(g, b, b.getWorldCenter())
        rj.setMaximumMotorTorque(1000.0)
        rj.setMaximumMotorTorqueEnabled(true)
        rj.setMotorSpeed(simulationRadians(20))
        rj.setMotorEnabled(true)
        w.addJoint(rj)
        var invdt = w.getTimeStep().getInverseDeltaTime()
        assertEquals(0.0, rj.getAngularTranslation())
        assertEquals(0.0000, rj.getAngularSpeed(), 1e-5)
        assertEquals(0.0, rj.getMotorTorque(invdt))
        w.step(1)
        assertEquals(0.00581, b.getTransform().getRotationAngle(), 1e-5)
        assertEquals(0.34906, b.getAngularVelocity(), 1e-5)
        assertEquals(simulationRadians(20) / 60.0, rj.getAngularTranslation(), 1e-5)
        assertEquals(simulationRadians(20), rj.getAngularSpeed(), 1e-5)
        assertEquals(2.05616, rj.getReactionTorque(invdt), 1e-3)
        rj.setLimitsEnabled(-simulationRadians(5), simulationRadians(5))
        w.step(30)
        assertEquals(0.08726, b.getTransform().getRotationAngle(), 1e-5)
        assertEquals(0.00000, b.getAngularVelocity(), 1e-5)
        assertEquals(0.00000, rj.getAngularSpeed(), 1e-3)
        assertEquals(0.08726, rj.getAngularTranslation(), 1e-3)
        assertEquals(0.000, rj.getReactionTorque(invdt), 1e-3)
        rj.setMotorSpeed(-simulationRadians(20))
        w.step(1)
        assertEquals(0.08144, b.getTransform().getRotationAngle(), 1e-5)
        assertEquals(-0.34906, b.getAngularVelocity(), 1e-5)
        assertEquals(-0.34906, rj.getAngularSpeed(), 1e-3)
        assertEquals(0.08144, rj.getAngularTranslation(), 1e-3)
        assertEquals(-2.05616, rj.getReactionTorque(invdt), 1e-3)
        w.step(60)
        assertEquals(-0.08726, b.getTransform().getRotationAngle(), 1e-5)
        assertEquals(0.00000, b.getAngularVelocity(), 1e-5)
        assertEquals(0.00000, rj.getAngularSpeed(), 1e-3)
        assertEquals(-0.08726, rj.getAngularTranslation(), 1e-3)
        assertEquals(0.000, rj.getReactionTorque(invdt), 1e-3)
    }
}
