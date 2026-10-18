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

import org.dyn4j.dynamics.Body
import org.dyn4j.dynamics.BodyFixture
import org.dyn4j.dynamics.joint.WeldJoint
import org.dyn4j.geometry.Geometry
import org.dyn4j.geometry.MassType
import org.dyn4j.geometry.Vector2
import org.dyn4j.world.World
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class WeldJointSimulationTest {
    @Test
    fun standard() {
        val w = World<Body>()
        var g = Body()
        var gf = g.addFixture(Geometry.createRectangle(10.0, 0.5))
        gf.setFriction(0.0)
        g.setMass(MassType.INFINITE)
        g.setLinearDamping(0.0)
        g.setAngularDamping(0.0)
        w.addBody(g)
        var b = Body()
        var bf = b.addFixture(Geometry.createRectangle(1.0, 0.5))
        bf.setFriction(0.0)
        b.setMass(MassType.NORMAL)
        b.translate(0.0, 2.0)
        b.setLinearDamping(0.0)
        b.setAngularDamping(0.0)
        w.addBody(b)
        var wj = WeldJoint<Body>(g, b, b.getWorldCenter())
        w.addJoint(wj)
        var invdt = w.getTimeStep().getInverseDeltaTime()
        w.step(4)
        var v2 = b.getWorldCenter()
        assertEquals(0.0, v2.x)
        assertEquals(2.0, v2.y)
        assertEquals(0.0, b.getAngularVelocity())
        assertEquals(4.9000, wj.getReactionForce(invdt).getMagnitude(), 1e-5)
        b.setLinearVelocity(0.0, 1.0)
        w.step(4)
        v2 = b.getWorldCenter()
        assertEquals(0.0, v2.x)
        assertEquals(2.0, v2.y)
        assertEquals(0.0, b.getAngularVelocity())
        assertEquals(4.9000, wj.getReactionForce(invdt).getMagnitude(), 1e-5)
        b.setLinearVelocity(1.0, 1.0)
        w.step(4)
        v2 = b.getWorldCenter()
        assertEquals(0.0, v2.x)
        assertEquals(2.0, v2.y)
        assertEquals(0.0, b.getAngularVelocity())
        assertEquals(4.9000, wj.getReactionForce(invdt).getMagnitude(), 1e-5)
        b.applyTorque(simulationRadians(30))
        w.step(1)
        v2 = b.getWorldCenter()
        assertEquals(0.0, v2.x)
        assertEquals(2.0, v2.y)
        assertEquals(0.0, b.getAngularVelocity())
        assertEquals(0.0, b.getTransform().getRotationAngle(), 1e-5)
        assertEquals(-0.52359, wj.getReactionTorque(invdt), 1e-5)
        assertEquals(4.9000, wj.getReactionForce(invdt).getMagnitude(), 1e-5)
    }
    @Test
    fun softConstraint() {
        val w = World<Body>()
        var g = Body()
        var gf = g.addFixture(Geometry.createRectangle(10.0, 0.5))
        gf.setFriction(0.0)
        g.setMass(MassType.INFINITE)
        g.setLinearDamping(0.0)
        g.setAngularDamping(0.0)
        w.addBody(g)
        var b = Body()
        var bf = b.addFixture(Geometry.createRectangle(1.0, 0.5))
        bf.setFriction(0.0)
        b.setMass(MassType.NORMAL)
        b.translate(0.0, 2.0)
        b.setLinearDamping(0.0)
        b.setAngularDamping(0.0)
        w.addBody(b)
        var p = b.getWorldCenter().sum(-0.5, 0.0)
        var wj = WeldJoint<Body>(g, b, p)
        wj.setSpringEnabled(true)
        wj.setSpringDamperEnabled(true)
        wj.setSpringDampingRatio(0.3)
        wj.setSpringFrequency(8.0)
        w.addJoint(wj)
        assertEquals(0.0, b.getAngularVelocity())
        assertEquals(0.0, b.getTransform().getRotationAngle(), 1e-5)
        w.step(1)
        var invdt = w.getTimeStep().getInverseDeltaTime()
        assertEquals(-0.17027, b.getAngularVelocity(), 1e-3)
        assertEquals(-0.00283, b.getTransform().getRotationAngle(), 1e-3)
        assertEquals( 0.63542, wj.getSpringTorque(invdt), 1e-3)
        assertEquals( 0.63542, wj.getReactionTorque(invdt), 1e-3)
        assertEquals( 2.33825, wj.getReactionForce(invdt).getMagnitude(), 1e-3)
        w.step(20)
        assertEquals(-0.01919, b.getAngularVelocity(), 1e-5)
        assertEquals(-0.01884, b.getTransform().getRotationAngle(), 1e-5)
        assertEquals( 2.50980, wj.getSpringTorque(invdt), 1e-5)
        assertEquals( 2.50980, wj.getReactionTorque(invdt), 1e-5)
        assertEquals( 4.98500, wj.getReactionForce(invdt).getMagnitude(), 1e-5)
        wj.setMaximumSpringTorque(5.0)
        wj.setMaximumSpringTorqueEnabled(true)
        b.applyForce(Vector2(0.0, -10.0), Vector2(0.5, 2.0))
        w.step(1)
        assertEquals(-0.72033, b.getAngularVelocity(), 1e-5)
        assertEquals(-0.03084, b.getTransform().getRotationAngle(), 1e-5)
        assertEquals( 5.00000, wj.getSpringTorque(invdt), 1e-5)
        assertEquals( 5.00000, wj.getReactionTorque(invdt), 1e-5)
        assertEquals( 4.38931, wj.getReactionForce(invdt).getMagnitude(), 1e-5)
    }
    @Test
    fun softConstraintWithLimitsLower() {
        val w = World<Body>()
        var g = Body()
        var gf = g.addFixture(Geometry.createRectangle(10.0, 0.5))
        gf.setFriction(0.0)
        g.setMass(MassType.INFINITE)
        g.setLinearDamping(0.0)
        g.setAngularDamping(0.0)
        w.addBody(g)
        var b = Body()
        var bf = b.addFixture(Geometry.createRectangle(1.0, 0.5))
        bf.setFriction(0.0)
        b.setMass(MassType.NORMAL)
        b.translate(0.0, 2.0)
        b.setLinearDamping(0.0)
        b.setAngularDamping(0.0)
        w.addBody(b)
        var p = b.getWorldCenter().sum(-0.5, 0.0)
        var wj = WeldJoint<Body>(g, b, p)
        wj.setSpringEnabled(true)
        wj.setSpringDamperEnabled(true)
        wj.setSpringDampingRatio(0.3)
        wj.setSpringFrequency(8.0)
        var lim = kotlin.math.PI * 0.2
        wj.setLimitsEnabled(-lim, lim)
        w.addJoint(wj)
        assertEquals(0.0, b.getAngularVelocity())
        assertEquals(0.0, b.getTransform().getRotationAngle(), 1e-5)
        var invdt = w.getTimeStep().getInverseDeltaTime()
        wj.setMaximumSpringTorque(1.0)
        wj.setMaximumSpringTorqueEnabled(true)
        w.step(50)
        assertEquals( 0.00000, b.getAngularVelocity(), 1e-5)
        assertEquals(-lim, b.getTransform().getRotationAngle(), 1e-3)
        assertEquals( 1.00000, wj.getSpringTorque(invdt), 1e-5)
        assertEquals( 1.98177, wj.getReactionTorque(invdt), 1e-5)
        assertEquals( 4.90000, wj.getReactionForce(invdt).getMagnitude(), 1e-5)
    }
    @Test
    fun softConstraintWithLimitsUpper() {
        val w = World<Body>()
        var g = Body()
        var gf = g.addFixture(Geometry.createRectangle(10.0, 0.5))
        gf.setFriction(0.0)
        g.setMass(MassType.INFINITE)
        g.setLinearDamping(0.0)
        g.setAngularDamping(0.0)
        w.addBody(g)
        var b = Body()
        var bf = b.addFixture(Geometry.createRectangle(1.0, 0.5))
        bf.setFriction(0.0)
        b.setMass(MassType.NORMAL)
        b.translate(0.0, 2.0)
        b.setLinearDamping(0.0)
        b.setAngularDamping(0.0)
        w.addBody(b)
        var p = b.getWorldCenter().sum(0.5, 0.0)
        var wj = WeldJoint<Body>(g, b, p)
        wj.setSpringEnabled(true)
        wj.setSpringDamperEnabled(true)
        wj.setSpringDampingRatio(0.3)
        wj.setSpringFrequency(8.0)
        var lim = kotlin.math.PI * 0.2
        wj.setLimitsEnabled(-lim, lim)
        w.addJoint(wj)
        assertEquals(0.0, b.getAngularVelocity())
        assertEquals(0.0, b.getTransform().getRotationAngle(), 1e-5)
        var invdt = w.getTimeStep().getInverseDeltaTime()
        wj.setMaximumSpringTorque(1.0)
        wj.setMaximumSpringTorqueEnabled(true)
        b.applyForce(Vector2(0.0, -10.0), Vector2(-0.5, 2.0))
        w.step(50)
        assertEquals( 0.00000, b.getAngularVelocity(), 1e-5)
        assertEquals( lim, b.getTransform().getRotationAngle(), 1e-3)
        assertEquals(-1.00000, wj.getSpringTorque(invdt), 1e-5)
        assertEquals(-1.98177, wj.getReactionTorque(invdt), 1e-5)
        assertEquals( 4.90000, wj.getReactionForce(invdt).getMagnitude(), 1e-5)
    }
}
