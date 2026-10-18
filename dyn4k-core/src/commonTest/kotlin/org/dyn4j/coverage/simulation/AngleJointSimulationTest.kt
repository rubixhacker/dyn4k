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
import org.dyn4j.dynamics.joint.AngleJoint
import org.dyn4j.geometry.Geometry
import org.dyn4j.geometry.MassType
import org.dyn4j.geometry.Vector2
import org.dyn4j.world.World
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class AngleJointSimulationTest {
    @Test
    fun simpleLinkage() {
        val w = World<Body>()
        w.setGravity(Vector2(0.0, 0.0))
        var g = Body()
        var gf = g.addFixture(Geometry.createCircle(0.5))
        gf.setFriction(0.0)
        g.setMass(MassType.NORMAL)
        g.setLinearDamping(0.0)
        g.setAngularDamping(0.0)
        w.addBody(g)
        var b = Body()
        var bf = b.addFixture(Geometry.createCircle(0.5))
        bf.setFriction(0.0)
        b.setMass(MassType.NORMAL)
        b.translate(0.0, 2.0)
        b.setAngularVelocity(-simulationRadians(30.0))
        b.setLinearDamping(0.0)
        b.setAngularDamping(0.0)
        w.addBody(b)
        var aj = AngleJoint<Body>(g, b)
        w.addJoint(aj)
        w.step(1)
        var invdt = w.getTimeStep().getInverseDeltaTime()
        assertEquals(-simulationRadians(15), g.getAngularVelocity())
        assertEquals(-simulationRadians(15), b.getAngularVelocity())
        assertEquals(Vector2(0.0, 0.0), aj.getReactionForce(invdt))
        assertEquals(1.542, aj.getReactionTorque(invdt), 1e-3)
        aj.setRatio(0.5)
        w.step(1)
        assertEquals(-simulationRadians(15), g.getAngularVelocity())
        assertEquals(-simulationRadians(15), b.getAngularVelocity())
        assertEquals(Vector2(0.0, 0.0), aj.getReactionForce(invdt))
        assertEquals(0.0, aj.getReactionTorque(invdt), 1e-3)
        aj.setLimitsEnabled(false)
        w.step(1)
        assertEquals(-simulationRadians(20), g.getAngularVelocity(), 1e-8)
        assertEquals(-simulationRadians(10), b.getAngularVelocity(), 1e-8)
        assertEquals(Vector2(0.0, 0.0), aj.getReactionForce(invdt))
        assertEquals(0.514, aj.getReactionTorque(invdt), 1e-3)
    }
    @Test
    fun withLimitsHitUpper() {
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
        b.setAngularVelocity(simulationRadians(30.0))
        b.setLinearDamping(0.0)
        b.setAngularDamping(0.0)
        w.addBody(b)
        var aj = AngleJoint<Body>(g, b)
        aj.setLimitsEnabled(simulationRadians(-30.0), simulationRadians(30.0))
        w.addJoint(aj)
        w.step(40)
        assertEquals(0.0, g.getAngularVelocity())
        assertEquals(simulationRadians(30), b.getAngularVelocity())
        w.step(40)
        assertEquals(0.0, g.getAngularVelocity(), 1e-9)
        assertEquals(0.0, b.getAngularVelocity(), 1e-9)
    }
    @Test
    fun withLimitsHitLower() {
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
        b.setAngularVelocity(simulationRadians(-30.0))
        b.setLinearDamping(0.0)
        b.setAngularDamping(0.0)
        w.addBody(b)
        var aj = AngleJoint<Body>(g, b)
        aj.setLimitsEnabled(simulationRadians(-30.0), simulationRadians(30.0))
        w.addJoint(aj)
        w.step(40)
        assertEquals(0.0, g.getAngularVelocity())
        assertEquals(simulationRadians(-30), b.getAngularVelocity())
        w.step(40)
        assertEquals(0.0, g.getAngularVelocity(), 1e-9)
        assertEquals(0.0, b.getAngularVelocity(), 1e-9)
    }
}
