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

import org.dyn4j.JvmFieldBridge

open class Link : Segment {
    @get:kotlin.jvm.JvmName("getPoint0Field")
    @JvmFieldBridge private val point0: Vector2?
    @get:kotlin.jvm.JvmName("getPoint3Field")
    @JvmFieldBridge private val point3: Vector2?

    constructor(point0: Vector2?, point1: Vector2, point2: Vector2, point3: Vector2?) : super(point1, point2) {
        this.point0 = point0
        this.point3 = point3
    }
    protected constructor(link: Link) : super(link) {
        point0 = link.point0?.copy()
        point3 = link.point3?.copy()
    }

    override fun copy() = Link(this)
    open fun getPoint0() = point0
    open fun getPoint3() = point3
    override fun toString() = "Link[${super.toString()}|Length=$length]"
    override fun rotate(theta: Double): Unit = throw UnsupportedOperationException()
    override fun rotate(rotation: Rotation, x: Double, y: Double): Unit = throw UnsupportedOperationException()
    final override fun rotate(theta: Double, x: Double, y: Double): Unit = throw UnsupportedOperationException()
    override fun rotate(theta: Double, point: Vector2): Unit = throw UnsupportedOperationException()
    override fun rotate(rotation: Rotation): Unit = throw UnsupportedOperationException()
    override fun rotate(rotation: Rotation, point: Vector2): Unit = throw UnsupportedOperationException()
    override fun rotateAboutCenter(theta: Double): Unit = throw UnsupportedOperationException()
    override fun translate(vector: Vector2): Unit = throw UnsupportedOperationException()
    final override fun translate(x: Double, y: Double): Unit = throw UnsupportedOperationException()
    open fun getPreviousEdgeVector() = point0!!.to(vertices[0]).also { it.normalize() }
    open fun getNextEdgeVector() = vertices[1].to(point3!!).also { it.normalize() }
}
