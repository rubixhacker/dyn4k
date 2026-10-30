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
package org.dyn4j.geometry

import de.infix.testBalloon.framework.core.testSuite
import org.dyn4j.geometry.RobustGeometry
import org.dyn4j.geometry.Vector2
import kotlin.math.sign
import kotlin.test.assertEquals
import kotlin.test.assertTrue

val RobustGeometryTest by testSuite {
    test("randomizedTest") { RobustGeometryTestFixture().run { randomizedTest() } }
    test("randomizedTest2") { RobustGeometryTestFixture().run { randomizedTest2() } }
}

private class RobustGeometryTestFixture  {
fun randomizedTest() {
        val random = JavaRandom(0L)
        repeat(100) {
            val pa = Vector2(random.nextDouble(), random.nextDouble())
            val pb = pa.product(random.nextDouble())
            val pc = pa.product(random.nextDouble())
            for (up in 0..4) {
                val xUp = up % 2 == 0
                val yUp = up / 2 == 0
                val pcOffset = pc.copy()
                repeat(10) {
                    repeat(10) {
                        val exact = exactLocationSign(pcOffset, pa, pb)
                        val robust = RobustGeometry.getLocation(pcOffset, pa, pb)
                        assertTrue(robust.isFinite())
                        assertEquals(exact, sign(robust).toInt())
                        pcOffset.x = if (xUp) Math.nextUp(pcOffset.x) else Math.nextDown(pcOffset.x)
                    }
                    pcOffset.y = if (yUp) Math.nextUp(pcOffset.y) else Math.nextDown(pcOffset.y)
                }
            }
        }
    }

fun randomizedTest2() {
        val random = JavaRandom(0L)
        repeat(1000) {
            val pa = Vector2(random.nextDouble(), random.nextDouble())
            val pb = Vector2(random.nextDouble(), random.nextDouble())
            val pc = Vector2(random.nextDouble(), random.nextDouble())
            val exact = exactLocationSign(pc, pa, pb)
            val robust = RobustGeometry.getLocation(pc, pa, pb)
            assertTrue(robust.isFinite())
            assertEquals(exact, sign(robust).toInt())
        }
    }
}
