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

import org.dyn4j.dynamics.Body
import org.dyn4j.dynamics.BodyFixture
import org.dyn4j.dynamics.joint.WheelJoint
import org.dyn4j.geometry.Geometry
import org.dyn4j.geometry.MassType
import org.dyn4j.geometry.Vector2
import org.dyn4j.world.World
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class WheelJointSimulationTest {
    @Test
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
        var dj = WheelJoint<Body>(g, b, b.getWorldCenter(), Vector2(1.0, 0.0))
        w.addJoint(dj)
        w.step(4)
        var v2 = b.getWorldCenter()
        assertEquals(0.0, v2.x, 1e-3)
        assertEquals(2.0, v2.y, 1e-3)
        b.setLinearVelocity(0.0, 1.0)
        w.step(4)
        v2 = b.getWorldCenter()
        assertEquals(0.0, v2.x, 1e-3)
        assertEquals(2.0, v2.y, 1e-3)
        b.setLinearVelocity(1.0, 1.0)
        w.step(4)
        v2 = b.getWorldCenter()
        assertTrue(v2.x > 0.0)
        assertEquals(2.0, v2.y, 1e-3)
        b.applyTorque(simulationRadians(30))
        w.step(1)
        var invdt = w.getTimeStep().getInverseDeltaTime()
        v2 = b.getWorldCenter()
        assertTrue(v2.x > 0.0)
        assertEquals(2.0, v2.y, 1e-3)
        assertEquals(0.001, b.getTransform().getRotationAngle(), 1e-3)
        assertEquals(7.89277, dj.getReactionForce(invdt).getMagnitude(), 1e-5)
        assertEquals(0.0, dj.getReactionTorque(invdt), 1e-5)
    }
    @Test
    fun limitsOnly() {
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
        var p = b.getWorldCenter()
        var dj = WheelJoint<Body>(g, b, p, Vector2(0.0, 1.0))
        dj.setLimitsEnabled(-1.0, 5.0)
        dj.setSpringEnabled(false)
        w.addJoint(dj)
        var v2 = b.getWorldCenter()
        assertEquals(0.0, p.distance(v2))
        var invdt = w.getTimeStep().getInverseDeltaTime()
        w.step(30)
        v2 = b.getWorldCenter()
        assertEquals(1.000, p.distance(v2), 1e-3)
        assertEquals(7.696, dj.getReactionForce(invdt).getMagnitude(), 1e-3)
        assertEquals(0.0, dj.getReactionTorque(invdt), 1e-3)
        w.setGravity(0.0, 98.0)
        w.step(30)
        v2 = b.getWorldCenter()
        assertEquals(5.0, p.distance(v2), 1e-5)
        assertEquals(76.969, dj.getReactionForce(invdt).getMagnitude(), 1e-3)
        assertEquals(0.0, dj.getReactionTorque(invdt), 1e-3)
        w.setGravity(0.0, -9.8)
        dj.setLimitsEnabled(-1.0, 4.0)
        w.step(1)
        v2 = b.getWorldCenter()
        assertEquals(4.0, p.distance(v2), 1e-5)
        assertEquals(0.0, dj.getReactionForce(invdt).getMagnitude(), 1e-3)
        assertEquals(0.0, dj.getReactionTorque(invdt), 1e-3)
        w.step(50)
        dj.setLimitsEnabled(1.0, 3.0)
        w.step(1)
        v2 = b.getWorldCenter()
        assertEquals(1.0, p.distance(v2), 1e-5)
        assertEquals(400.238, dj.getReactionForce(invdt).getMagnitude(), 1e-3)
        assertEquals(0.0, dj.getReactionTorque(invdt), 1e-3)
    }
    @Test
    fun springDamperWithLimits() {
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
        var p = b.getWorldCenter()
        var dj = WheelJoint<Body>(g, b, p, Vector2(0.0, 1.0))
        dj.setLimitsEnabled(-1.0, 5.0)
        w.addJoint(dj)
        var v2 = b.getWorldCenter()
        assertEquals(0.0, p.distance(v2))
        w.step(20)
        var invdt = w.getTimeStep().getInverseDeltaTime()
        v2 = b.getWorldCenter()
        assertEquals(0.00387, p.distance(v2), 1e-5)
        assertEquals(7.695, dj.getReactionForce(invdt).getMagnitude(), 1e-3)
        assertEquals(0.0, dj.getReactionTorque(invdt), 1e-3)
        dj.setLimitsEnabled(1.0, 5.0)
        w.step(2)
        v2 = b.getWorldCenter()
        assertEquals(1.0, p.distance(v2), 1e-5)
        assertEquals(7.696, dj.getReactionForce(invdt).getMagnitude(), 1e-3)
        assertEquals(0.0, dj.getReactionTorque(invdt), 1e-3)
        dj.setLimitsEnabled(-1.0, -0.5)
        w.step(2)
        v2 = b.getWorldCenter()
        assertEquals(0.5, p.distance(v2), 1e-5)
        assertEquals(911.350, dj.getReactionForce(invdt).getMagnitude(), 1e-3)
        assertEquals(0.0, dj.getReactionTorque(invdt), 1e-3)
        dj.setLimitsEnabled(-1.5, 1.0)
        dj.setMaximumSpringForceEnabled(true)
        dj.setMaximumSpringForce(200.0)
        w.step(2)
        v2 = b.getWorldCenter()
        assertEquals(0.29596, p.distance(v2), 1e-5)
        assertEquals(200.0, dj.getSpringForce(invdt), 1e-3)
        assertEquals(200.0, dj.getReactionForce(invdt).getMagnitude(), 1e-3)
        assertEquals(0.0, dj.getReactionTorque(invdt), 1e-3)
    }
    @Test
    fun motorOnly() {
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
        b.setLinearDamping(0.0)
        b.setAngularDamping(0.0)
        w.addBody(b)
        var p = b.getWorldCenter()
        var dj = WheelJoint<Body>(g, b, p, Vector2(-1.0, 0.0))
        dj.setMaximumMotorTorqueEnabled(true)
        dj.setMaximumMotorTorque(10000.0)
        dj.setMotorSpeed(simulationRadians(90))
        dj.setMotorEnabled(true)
        w.addJoint(dj)
        var invdt = w.getTimeStep().getInverseDeltaTime()
        var v2 = b.getWorldCenter()
        var v = b.getLinearVelocity()
        assertEquals(0.0, p.distance(v2))
        assertEquals(0.0, dj.getAngularTranslation())
        assertEquals(0.0, v.x)
        assertEquals(0.0000, dj.getAngularSpeed(), 1e-5)
        assertEquals(0.0, dj.getReactionTorque(invdt))
        w.step(1)
        v2 = b.getWorldCenter()
        v = b.getLinearVelocity()
        assertEquals(0.0, p.distance(v2), 1e-3)
        assertEquals(0.026, dj.getAngularTranslation(), 1e-3)
        assertEquals(0.0, v.x, 1e-3)
        assertEquals(1.5707, dj.getAngularSpeed(), 1e-3)
        assertEquals(9.252, dj.getReactionTorque(invdt), 1e-3)
        assertEquals(9.252, dj.getMotorTorque(invdt), 1e-3)
    }
}
