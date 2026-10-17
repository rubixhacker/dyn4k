/*
 * Copyright (c) 2010-2024 William Bittle  http://www.dyn4j.org/
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

open class Triangle : Polygon {
    constructor(point1: Vector2, point2: Vector2, point3: Vector2) : super(point1, point2, point3)
    protected constructor(triangle: Triangle) : super(triangle)

    override fun copy() = Triangle(this)
    override fun toString() = "Triangle[${super.toString()}]"
    override fun contains(point: Vector2, transform: Transform): Boolean {
        val local = transform.getInverseTransformed(point)
        val p1 = vertices[0]
        val ab = p1.to(vertices[1])
        val ac = p1.to(vertices[2])
        val pa = p1.to(local)
        val dot00 = ac.dot(ac)
        val dot01 = ac.dot(ab)
        val dot02 = ac.dot(pa)
        val dot11 = ab.dot(ab)
        val dot12 = ab.dot(pa)
        val inverseDenominator = 1.0 / (dot00 * dot11 - dot01 * dot01)
        val u = (dot11 * dot02 - dot01 * dot12) * inverseDenominator
        if (u <= 0.0) return false
        val v = (dot00 * dot12 - dot01 * dot02) * inverseDenominator
        return v > 0.0 && u + v <= 1.0
    }
}
