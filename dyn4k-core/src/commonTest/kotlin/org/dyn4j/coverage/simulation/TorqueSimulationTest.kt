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

import de.infix.testBalloon.framework.core.testSuite
import org.dyn4j.dynamics.Body
import org.dyn4j.dynamics.Torque
import org.dyn4j.geometry.Geometry
import org.dyn4j.geometry.MassType
import org.dyn4j.world.World
import kotlin.test.assertEquals
import kotlin.test.assertTrue

val TorqueSimulationTest by testSuite {
    test("applyTimed") { TorqueSimulationTestFixture().run { applyTimed() } }
}

private class TorqueSimulationTestFixture  {
fun applyTimed() {
        val w = World<Body>()
        var b = Body()
        b.addFixture(Geometry.createCircle(1.0))
        b.setMass(MassType.NORMAL)
        var t = object : Torque(1.0) {
            private var time = 0.0
            override fun isComplete(elapsedTime: Double): Boolean {
                time += elapsedTime
                if (time >= 2.0 / 60.0) {
                    return true
                }
                return false
            }
        }
        b.applyTorque(t)
        w.addBody(b)
        w.step(1)
        assertEquals(1.0, b.getAccumulatedTorque())
        w.step(1)
        assertEquals(0.0, b.getAccumulatedTorque())
    }
}
