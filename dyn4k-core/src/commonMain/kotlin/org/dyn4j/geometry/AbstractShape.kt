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

abstract class AbstractShape : Shape {
    @kotlin.jvm.JvmField protected var center: Vector2
    @kotlin.jvm.JvmField protected var radius: Double
    @kotlin.jvm.JvmField protected var userData: Any? = null

    protected constructor(radius: Double) : this(Vector2(), radius)
    protected constructor(center: Vector2, radius: Double) {
        this.center = center
        this.radius = radius
    }
    protected constructor(shape: AbstractShape) {
        center = shape.center.copy()
        radius = shape.radius
    }

    override fun toString() = "HashCode=${hashCode()}|Center=$center|Radius=$radius"
    override fun getCenter() = center
    override fun getRadius() = radius
    override fun getUserData() = userData
    override fun setUserData(data: Any?) { userData = data }
    override fun rotate(theta: Double) = rotate(theta, 0.0, 0.0)
    override fun rotate(rotation: Rotation) = rotate(rotation, 0.0, 0.0)
    override fun rotateAboutCenter(theta: Double) = rotate(theta, center.x, center.y)
    override fun rotate(theta: Double, point: Vector2) = rotate(theta, point.x, point.y)
    override fun rotate(rotation: Rotation, point: Vector2) = rotate(rotation, point.x, point.y)
    override fun rotate(theta: Double, x: Double, y: Double) = rotate(Rotation(theta), x, y)
    override fun rotate(rotation: Rotation, x: Double, y: Double) {
        if (!center.equals(x, y)) center.rotate(rotation, x, y)
    }
    override fun translate(x: Double, y: Double) { center.add(x, y) }
    override fun translate(vector: Vector2) = translate(vector.x, vector.y)
    override fun project(vector: Vector2) = project(vector, IDENTITY)
    override fun contains(point: Vector2) = contains(point, IDENTITY, true)
    override fun contains(point: Vector2, transform: Transform) = contains(point, transform, true)
    override fun createAABB() = createAABB(IDENTITY)
    override fun computeAABB(aabb: AABB) = computeAABB(IDENTITY, aabb)
    override fun createAABB(transform: Transform): AABB {
        val aabb = AABB(0.0, 0.0, 0.0, 0.0)
        computeAABB(transform, aabb)
        return aabb
    }

    private companion object { val IDENTITY = Transform() }
}
