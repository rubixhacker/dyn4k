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
import org.dyn4j.dynamics.joint.PulleyJoint
import org.dyn4j.geometry.Geometry
import org.dyn4j.geometry.MassType
import org.dyn4j.geometry.Vector2
import org.dyn4j.world.World
import kotlin.test.assertEquals
import kotlin.test.assertTrue

val PulleyJointSimulationTest by testSuite {
    test("simpleLinkage") { PulleyJointSimulationTestFixture().run { simpleLinkage() } }
    test("withAndWithoutSlack") { PulleyJointSimulationTestFixture().run { withAndWithoutSlack() } }
}

private class PulleyJointSimulationTestFixture  {
fun simpleLinkage() {
        val w = World<Body>()
        var b1 = Body()
        var b1f = b1.addFixture(Geometry.createCircle(0.5))
        b1f.setFriction(0.0)
        b1.setMass(MassType.NORMAL)
        b1.setLinearDamping(0.0)
        b1.setAngularDamping(0.0)
        b1.translate(-1.0, 0.0)
        w.addBody(b1)
        var b2 = Body()
        var b2f = b2.addFixture(Geometry.createCircle(0.5))
        b2f.setFriction(0.0)
        b2.setMass(MassType.NORMAL)
        b2.setLinearDamping(0.0)
        b2.setAngularDamping(0.0)
        b2.translate(1.0, 0.0)
        w.addBody(b2)
        var pa1 = Vector2(-1.0, 1.0)
        var pa2 = Vector2(1.0, 1.0)
        var a1 = Vector2(-1.0, 0.0)
        var a2 = Vector2(1.0, 0.0)
        var aj = PulleyJoint<Body>(b1, b2, pa1, pa2, a1, a2)
        w.addJoint(aj)
        var invdt = w.getTimeStep().getInverseDeltaTime()
        w.step(1)
        assertEquals(0.0, b1.getLinearVelocity().getMagnitude())
        assertEquals(0.0, b2.getLinearVelocity().getMagnitude())
        assertEquals(7.696, aj.getReactionForce(invdt).getMagnitude(), 1e-3)
        assertEquals(0.0, aj.getReactionTorque(invdt))
        aj.setRatio(0.5)
        w.step(1)
        assertTrue(b1.getLinearVelocity().y > 0.0)
        assertTrue(b2.getLinearVelocity().y < 0.0)
        assertTrue(aj.getCurrentLength2() > aj.getCurrentLength1())
        assertEquals(2.0, aj.getLength())
        assertEquals(9.236, aj.getReactionForce(invdt).getMagnitude(), 1e-3)
        assertEquals(0.0, aj.getReactionTorque(invdt))
        aj.setRatio(2.0)
        w.step(10)
        assertTrue(b1.getLinearVelocity().y < 0.0)
        assertTrue(b2.getLinearVelocity().y > 0.0)
        assertTrue(aj.getCurrentLength2() < aj.getCurrentLength1())
        assertEquals(2.0, aj.getLength())
        assertEquals(4.618, aj.getReactionForce(invdt).getMagnitude(), 1e-3)
        assertEquals(0.0, aj.getReactionTorque(invdt))
    }
fun withAndWithoutSlack() {
        val w = World<Body>()
        var g = Body()
        var gf = g.addFixture(Geometry.createRectangle(10.0, 1.0))
        gf.setFriction(0.0)
        g.setMass(MassType.INFINITE)
        g.setLinearDamping(0.0)
        g.setAngularDamping(0.0)
        g.translate(0.0, -1.0)
        w.addBody(g)
        var b1 = Body()
        var b1f = b1.addFixture(Geometry.createCircle(0.5))
        b1f.setFriction(0.0)
        b1.setMass(MassType.NORMAL)
        b1.setLinearDamping(0.0)
        b1.setAngularDamping(0.0)
        b1.translate(-1.0, 0.0)
        w.addBody(b1)
        var b2 = Body()
        var b2f = b2.addFixture(Geometry.createCircle(0.5))
        b2f.setFriction(0.0)
        b2.setMass(MassType.NORMAL)
        b2.setLinearDamping(0.0)
        b2.setAngularDamping(0.0)
        b2.translate(1.0, 0.5)
        w.addBody(b2)
        var pa1 = Vector2(-1.0, 1.0)
        var pa2 = Vector2(1.0, 1.0)
        var a1 = Vector2(-1.0, 0.0)
        var a2 = Vector2(1.0, 0.5)
        var aj = PulleyJoint<Body>(b1, b2, pa1, pa2, a1, a2)
        w.addJoint(aj)
        w.step(1)
        assertEquals(0.0, b1.getLinearVelocity().getMagnitude())
        assertEquals(0.0, b2.getLinearVelocity().getMagnitude())
        b2.setLinearVelocity(0.0, 10.0)
        w.step(2)
        assertEquals(1.041, b1.getWorldCenter().distance(pa1), 1e-3)
        assertEquals(0.458, b2.getWorldCenter().distance(pa2), 1e-3)
        assertEquals(-0.041, b1.getTransform().getTranslationY(), 1e-3)
        assertEquals(0.541, b2.getTransform().getTranslationY(), 1e-3)
        assertEquals(0.156, b2.getLinearVelocity().y, 1e-3)
        assertEquals(1.500, aj.getCurrentLength(), 1e-3)
        b2.setLinearVelocity(0.0, 10.0)
        b2.translate(0.0, 0.1)
        aj.setSlackEnabled(true)
        w.step(1)
        assertEquals(9.836, b2.getLinearVelocity().y, 1e-3)
        assertEquals(0.805, b2.getTransform().getTranslationY(), 1e-3)
        assertEquals(0.194, b2.getWorldCenter().distance(pa2), 1e-3)
        assertEquals(1.222, aj.getCurrentLength(), 1e-3)
    }
}
