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
import org.dyn4j.dynamics.joint.PrismaticJoint
import org.dyn4j.geometry.Geometry
import org.dyn4j.geometry.MassType
import org.dyn4j.geometry.Vector2
import org.dyn4j.world.World
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class PrismaticJointSimulationTest {
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
        var dj = PrismaticJoint<Body>(g, b, b.getWorldCenter(), Vector2(1.0, 0.0))
        w.addJoint(dj)
        w.step(4)
        var v2 = b.getWorldCenter()
        assertEquals(0.0, v2.x)
        assertEquals(2.0, v2.y)
        b.setLinearVelocity(0.0, 1.0)
        w.step(4)
        v2 = b.getWorldCenter()
        assertEquals(0.0, v2.x)
        assertEquals(2.0, v2.y)
        b.setLinearVelocity(1.0, 1.0)
        w.step(4)
        v2 = b.getWorldCenter()
        assertTrue(v2.x > 0.0)
        assertEquals(2.0, v2.y)
        b.applyTorque(simulationRadians(30))
        w.step(1)
        var invdt = w.getTimeStep().getInverseDeltaTime()
        v2 = b.getWorldCenter()
        assertTrue(v2.x > 0.0)
        assertEquals(2.0, v2.y)
        assertEquals(0.0, b.getTransform().getRotationAngle())
        assertEquals(-0.52359, dj.getReactionTorque(invdt), 1e-5)
    }
    @Test
    fun limits() {
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
        var dj = PrismaticJoint<Body>(g, b, p, Vector2(1.0, 0.0))
        dj.setLimitsEnabled(-1.0, 5.0)
        w.addJoint(dj)
        var v2 = b.getWorldCenter()
        assertEquals(0.0, p.distance(v2))
        b.setLinearVelocity(-16.0, 0.0)
        w.step(1)
        var invdt = w.getTimeStep().getInverseDeltaTime()
        v2 = b.getWorldCenter()
        assertEquals(0.26666, p.distance(v2), 1e-5)
        assertEquals(0.0, dj.getReactionForce(invdt).getMagnitude(), 1e-3)
        dj.setLimitsEnabled(6.0, 7.0)
        w.step(1)
        v2 = b.getWorldCenter()
        assertEquals(6.0, p.distance(v2), 1e-5)
        assertEquals(753.982, dj.getReactionForce(invdt).getMagnitude(), 1e-3)
        b.setLinearVelocity(16.0, 0.0)
        dj.setLimitsEnabled(1.0, 3.0)
        w.step(1)
        v2 = b.getWorldCenter()
        assertEquals(3.0, p.distance(v2), 1e-5)
        assertEquals(753.982, dj.getReactionForce(invdt).getMagnitude(), 1e-3)
    }
    @Test
    fun motorWithAndWithoutLimits() {
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
        var dj = PrismaticJoint<Body>(g, b, p, Vector2(1.0, 0.0))
        dj.setMaximumMotorForce(1000.0)
        dj.setMotorSpeed(10.0)
        dj.setMotorEnabled(true)
        dj.setMaximumMotorForceEnabled(true)
        w.addJoint(dj)
        var invdt = w.getTimeStep().getInverseDeltaTime()
        var v2 = b.getWorldCenter()
        var v = b.getLinearVelocity()
        assertEquals(0.0, p.distance(v2))
        assertEquals(0.0, dj.getLinearTranslation())
        assertEquals(0.0, v.x)
        assertEquals(0.0000, dj.getLinearSpeed(), 1e-5)
        assertEquals(0.0, dj.getMotorForce(invdt))
        w.step(1)
        v2 = b.getWorldCenter()
        v = b.getLinearVelocity()
        assertEquals(0.16666, p.distance(v2), 1e-5)
        assertEquals(0.16666, dj.getLinearTranslation(), 1e-5)
        assertEquals(10.0000, v.x, 1e-5)
        assertEquals(10.0000, dj.getLinearSpeed(), 1e-5)
        assertEquals(471.238, dj.getMotorForce(invdt), 1e-3)
        assertEquals(471.238, dj.getReactionForce(invdt).getMagnitude(), 1e-3)
        dj.setLimitsEnabled(6.0, 7.0)
        w.step(1)
        v2 = b.getWorldCenter()
        v = b.getLinearVelocity()
        assertEquals(6.0, p.distance(v2), 1e-5)
        assertEquals(6.0, dj.getLinearTranslation(), 1e-5)
        assertEquals(10.0000, v.x, 1e-5)
        assertEquals(10.0000, dj.getLinearSpeed(), 1e-5)
        assertEquals(0.0000, dj.getMotorForce(invdt), 1e-3)
        assertEquals(0.0000, dj.getReactionForce(invdt).getMagnitude(), 1e-3)
        w.step(10)
        v2 = b.getWorldCenter()
        v = b.getLinearVelocity()
        assertEquals(7.0000, p.distance(v2), 1e-5)
        assertEquals(7.0000, dj.getLinearTranslation(), 1e-5)
        assertEquals(0.0000, v.x, 1e-5)
        assertEquals(0.0000, dj.getLinearSpeed(), 1e-5)
        assertEquals(1000.0, dj.getMotorForce(invdt), 1e-3)
        assertEquals(0.0000, dj.getReactionForce(invdt).getMagnitude(), 1e-3)
        dj.setMotorSpeed(-10.0)
        w.step(1)
        v2 = b.getWorldCenter()
        v = b.getLinearVelocity()
        assertEquals(6.83333, p.distance(v2), 1e-5)
        assertEquals(6.83333, dj.getLinearTranslation(), 1e-5)
        assertEquals(-10.0000, v.x, 1e-5)
        assertEquals(-10.0000, dj.getLinearSpeed(), 1e-5)
        assertEquals(-471.238, dj.getMotorForce(invdt), 1e-3)
        assertEquals(471.238, dj.getReactionForce(invdt).getMagnitude(), 1e-3)
        w.step(10)
        v2 = b.getWorldCenter()
        v = b.getLinearVelocity()
        assertEquals(6.0000, p.distance(v2), 1e-5)
        assertEquals(6.0000, dj.getLinearTranslation(), 1e-5)
        assertEquals(0.0000, v.x, 1e-5)
        assertEquals(0.0000, dj.getLinearSpeed(), 1e-5)
        assertEquals(-1000.0000, dj.getMotorForce(invdt), 1e-3)
        assertEquals(0.0000, dj.getReactionForce(invdt).getMagnitude(), 1e-3)
    }
    @Test
    fun springOnly() {
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
        var dj = PrismaticJoint<Body>(g, b, p, Vector2(1.0, 0.0))
        dj.setSpringEnabled(true)
        dj.setSpringFrequency(8.0)
        dj.setSpringDamperEnabled(true)
        dj.setSpringDampingRatio(0.2)
        dj.setMaximumSpringForceEnabled(true)
        dj.setMaximumSpringForce(1000.0)
        dj.setSpringRestOffset(2.0)
        w.addJoint(dj)
        var invdt = w.getTimeStep().getInverseDeltaTime()
        var v2 = b.getWorldCenter()
        var v = b.getLinearVelocity()
        assertEquals(0.0, p.distance(v2))
        assertEquals(0.0, dj.getLinearTranslation())
        assertEquals(0.0, v.x)
        assertEquals(0.0000, dj.getLinearSpeed(), 1e-5)
        assertEquals(0.0, dj.getMotorForce(invdt))
        w.step(1)
        v2 = b.getWorldCenter()
        v = b.getLinearVelocity()
        assertEquals(0.35367, p.distance(v2), 1e-5)
        assertEquals(0.35367, dj.getLinearTranslation(), 1e-5)
        assertEquals(21.22065, v.x, 1e-5)
        assertEquals(21.22065, dj.getLinearSpeed(), 1e-5)
        assertEquals(1000.0, dj.getSpringForce(invdt), 1e-3)
        assertEquals(1000.0, dj.getReactionForce(invdt).getMagnitude(), 1e-3)
    }
}
