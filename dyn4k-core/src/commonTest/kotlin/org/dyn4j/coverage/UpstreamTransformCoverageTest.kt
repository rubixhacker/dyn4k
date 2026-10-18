/*
 * Copyright (c) 2010-2022 William Bittle  http://www.dyn4j.org/
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
package org.dyn4j.coverage

import org.dyn4j.Epsilon
import org.dyn4j.geometry.*
import kotlin.math.*
import kotlin.test.*

class UpstreamTransformCoverageTest {
    @Test
    fun identity() {
        var t = Transform()
        t.translate(5.0, 2.0)
        t.identity()
        assertEquals(0.0, t.getTranslationX())
        assertEquals(0.0, t.getTranslationY())
    }

    @Test
    fun translate() {
        var t = Transform()
        t.translate(2.0, -1.0)
        t.translate(4.0, 4.0)
        assertEquals(6.000, t.getTranslationX(), 1.0e-3)
        assertEquals(3.000, t.getTranslationY(), 1.0e-3)
    }

    @Test
    fun rotate() {
        var t = Transform()
        t.rotate(radians(30.0))
        assertEquals(radians(30.0), t.getRotationAngle(), 1.0e-3)
        t.rotate(Rotation.ofDegrees(50.0))
        assertEquals(radians(80.0), t.getRotationAngle(), 1.0e-3)
        assertEquals(radians(80.0), t.getRotation().toRadians(), 1.0e-3)
        t.identity()
        t.translate(5.0, 5.0)
        t.rotate(radians(90.0))
        var v = t.getTranslation()
        assertEquals(-5.000, v.x, 1.0e-3)
        assertEquals( 5.000, v.y, 1.0e-3)
        t.rotate(Rotation.ofDegrees(90.0))
        v = t.getTranslation()
        assertEquals(-5.000, v.x, 1.0e-3)
        assertEquals(-5.000, v.y, 1.0e-3)
        t.rotate(radians(35.0), -5.0, -5.0)
        v = t.getTranslation()
        assertEquals(-5.000, v.x, 1.0e-3)
        assertEquals(-5.000, v.y, 1.0e-3)
        t.rotate(Rotation.ofDegrees(45.0), -1.0, -1.0)
        v = t.getTranslation()
        assertEquals(-1.000, v.x, 1.0e-3)
        assertEquals(-6.656, v.y, 1.0e-3)
    }

    @Test
    fun copy() {
        var t = Transform()
        t.translate(2.0, -1.0)
        t.rotate(radians(20.0), -2.0, 6.0)
        var tc = t.copy()
        assertEquals(t.getCost(), tc.getCost())
        assertEquals(t.getSint(), tc.getSint())
        assertEquals(t.getTranslationX(), tc.getTranslationX())
        assertEquals(t.getTranslationY(), tc.getTranslationY())
    }

    @Test
    fun getTransformed() {
        var t = Transform()
        t.translate(2.0, 1.0)
        t.rotate(radians(25.0), 1.0, -1.0)
        var v = Vector2(1.0, 0.0)
        var vt = t.getTransformed(v)
        assertEquals(1.967, vt.x, 1.0e-3)
        assertEquals(1.657, vt.y, 1.0e-3)
        assertEquals(1.967, t.getTransformedX(v), 1.0e-3)
        assertEquals(1.657, t.getTransformedY(v), 1.0e-3)
        vt.zero()
        t.getTransformed(v, vt)
        assertEquals(1.967, vt.x, 1.0e-3)
        assertEquals(1.657, vt.y, 1.0e-3)
        assertEquals(1.967, t.getTransformedX(v), 1.0e-3)
        assertEquals(1.657, t.getTransformedY(v), 1.0e-3)
        vt = t.getInverseTransformed(vt)
        assertEquals(1.000, vt.x, 1.0e-3)
        assertEquals(0.000, vt.y, 1.0e-3)
        var v2 = t.getTransformed(v)
        t.getInverseTransformed(v2, vt)
        assertEquals(1.000, vt.x, 1.0e-3)
        assertEquals(0.000, vt.y, 1.0e-3)
        vt = t.getTransformedR(v)
        assertEquals(0.906, vt.x, 1.0e-3)
        assertEquals(0.422, vt.y, 1.0e-3)
        vt.zero()
        t.getTransformedR(v, vt)
        assertEquals(0.906, vt.x, 1.0e-3)
        assertEquals(0.422, vt.y, 1.0e-3)
        vt = t.getInverseTransformedR(v)
        vt = t.getTransformedR(vt)
        assertTrue(vt.equals(v))
        t.getInverseTransformedR(v, vt)
        vt = t.getTransformedR(vt)
        assertTrue(vt.equals(v))
    }

    @Test
    fun transform() {
        var t = Transform()
        t.translate(2.0, 1.0)
        t.rotate(radians(25.0), 1.0, -1.0)
        var v = Vector2(1.0, 0.0)
        var v2 = v.copy()
        t.transformX(v2)
        assertEquals(1.967, v2.x, 1.0e-3)
        assertEquals(0.0, v2.y, 1.0e-3)
        v2 = v.copy()
        t.transformY(v2)
        assertEquals(1.0, v2.x, 1.0e-3)
        assertEquals(1.657, v2.y, 1.0e-3)
        t.transform(v)
        assertEquals(1.967, v.x, 1.0e-3)
        assertEquals(1.657, v.y, 1.0e-3)
        t.inverseTransform(v)
        assertEquals(1.000, v.x, 1.0e-3)
        assertEquals(0.000, v.y, 1.0e-3)
        t.transformR(v)
        assertEquals(0.906, v.x, 1.0e-3)
        assertEquals(0.422, v.y, 1.0e-3)
        t.inverseTransformR(v)
        t.transformR(v)
        assertTrue(v.equals(v))
    }

    @Test
    fun setTransform() {
        var tx = Transform()
        tx.rotate(radians(30.0))
        tx.translate(2.0, 0.5)
        var tx2 = Transform()
        tx2.set(tx)
        assertNotSame(tx2, tx)
        assertEquals(tx.getCost(), tx2.getCost())
        assertEquals(tx.getSint(), tx2.getSint())
        assertEquals(tx.getTranslationX(), tx2.getTranslationX())
        assertEquals(tx.getTranslationY(), tx2.getTranslationY())
    }

    @Test
    fun setTranslation() {
        var tx = Transform()
        tx.translate(1.0, 2.0)
        tx.rotate(radians(45.0))
        tx.setTranslation(0.0, 0.0)
        assertEquals(0.0, tx.getTranslationX())
        assertEquals(0.0, tx.getTranslationY())
        assertEquals(radians(45.000), tx.getRotationAngle(), 1.0e-3)
        tx.setTranslationX(2.0)
        assertEquals(2.0, tx.getTranslationX())
        assertEquals(0.0, tx.getTranslationY())
        assertEquals(radians(45.000), tx.getRotationAngle(), 1.0e-3)
        tx.setTranslationY(3.0)
        assertEquals(2.0, tx.getTranslationX())
        assertEquals(3.0, tx.getTranslationY())
        assertEquals(radians(45.000), tx.getRotationAngle(), 1.0e-3)
        tx.setTranslation(Vector2(5.0, -7.0))
        assertEquals(5.0, tx.getTranslationX())
        assertEquals(-7.0, tx.getTranslationY())
        assertEquals(radians(45.000), tx.getRotationAngle(), 1.0e-3)
    }

    @Test
    fun setRotation() {
        var tx = Transform()
        tx.rotate(radians(45.0))
        tx.translate(1.0, 0.0)
        tx.setRotation(radians(30.0))
        assertEquals(30.000, degrees(tx.getRotationAngle()), 1.0e-3)
        assertEquals(1.0, tx.getTranslationX())
        assertEquals(0.0, tx.getTranslationY())
        tx.setRotation(Rotation.rotation135())
        assertEquals(135.000, degrees(tx.getRotationAngle()), 1.0e-3)
        assertEquals(1.0, tx.getTranslationX())
        assertEquals(0.0, tx.getTranslationY())
    }

    @Test
    fun lerp() {
        var p = Vector2()
        var start = Transform()
        start.translate(1.0, 0.0)
        start.rotate(radians(45.0))
        var end = Transform()
        end.set(start)
        end.translate(3.0, 2.0)
        end.rotate(radians(20.0))
        var s = start.getTransformed(p)
        var e = end.getTransformed(p)
        var alpha = 0.5
        var mid = Transform()
        start.lerp(end, alpha, mid)
        start.lerp(end, alpha)
        var m = mid.getTransformed(p)
        assertEquals((s.x + e.x) * alpha, m.x, 1.0e-9)
        assertEquals((s.y + e.y) * alpha, m.y, 1.0e-9)
        m = start.getTransformed(p)
        assertEquals((s.x + e.x) * alpha, m.x, 1.0e-9)
        assertEquals((s.y + e.y) * alpha, m.y, 1.0e-9)
        start.identity()
        start.rotate(radians(174.0))
        end.identity()
        end.rotate(radians(-168.0))
        var l = start.lerped(end, alpha)
        assertEquals(-3.089, l.getRotationAngle(), 1.0e-3)
        start.identity()
        start.rotate(radians(354.0))
        end.identity()
        end.rotate(radians(2.0))
        l = start.lerped(end, alpha)
        assertEquals(-0.034, l.getRotationAngle(), 1.0e-3)
        start.identity()
        start.translate(1.0, 0.0)
        start.lerp(Vector2(1.0, 0.0), radians(90.0), 0.5)
        assertEquals(radians(45.0), start.getRotationAngle(), 1.0e-3)
        assertEquals(1.5, start.getTranslationX(), 1.0e-3)
        assertEquals(0.0, start.getTranslationY(), 1.0e-3)
    }

    @Test
    fun values() {
        var t = Transform()
        t.translate(2.0, -1.0)
        var values = t.getValues()
        assertEquals(1.0, values[0])
        assertEquals(-0.0, values[1])
        assertEquals(2.0, values[2])
        assertEquals(0.0, values[3])
        assertEquals(1.0, values[4])
        assertEquals(-1.0, values[5])
    }

    @Test
    fun getTranslationRotationTransform() {
        var t = Transform()
        t.rotate(radians(30.0))
        t.translate(2.0, -1.0)
        var t2 = t.getTranslationTransform()
        assertEquals(2.0, t2.getTranslationX())
        assertEquals(-1.0, t2.getTranslationY())
        assertEquals(0.0, t2.getRotationAngle(), 1.0e-3)
        t2 = t.getRotationTransform()
        assertEquals(0.0, t2.getTranslationX())
        assertEquals(0.0, t2.getTranslationY())
        assertEquals( radians(30.0), t2.getRotationAngle(), 1.0e-3)
    }
}

private fun radians(value: Double) = value / 180.0 * PI
private fun degrees(value: Double) = value * 180.0 / PI
