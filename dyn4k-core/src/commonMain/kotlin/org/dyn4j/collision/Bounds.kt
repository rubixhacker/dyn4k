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
package org.dyn4j.collision

import org.dyn4j.Copyable
import org.dyn4j.exception.ValueOutOfRangeException
import org.dyn4j.geometry.AABB
import org.dyn4j.geometry.Shiftable
import org.dyn4j.geometry.Transform
import org.dyn4j.geometry.Translatable
import org.dyn4j.geometry.Vector2

interface Bounds : Translatable, Shiftable, Copyable<Bounds> {
    fun getTranslation(): Vector2
    fun isOutside(body: CollisionBody<*>): Boolean
    fun isOutside(aabb: AABB): Boolean
    fun isOutside(aabb: AABB, transform: Transform?, fixture: Fixture?): Boolean
}

abstract class AbstractBounds : Bounds, Translatable {
    @kotlin.jvm.JvmField protected var transform: Transform

    constructor() { transform = Transform() }
    constructor(x: Double, y: Double) : this() { translate(x, y) }
    constructor(translation: Vector2) : this() { translate(translation) }
    protected constructor(bounds: AbstractBounds) { transform = bounds.transform.copy() }

    override fun getTranslation() = transform.getTranslation()
    override fun translate(x: Double, y: Double) = transform.translate(x, y)
    override fun translate(vector: Vector2) = transform.translate(vector)
    override fun shift(shift: Vector2) = transform.translate(shift)
}

class AxisAlignedBounds : AbstractBounds, Bounds, Translatable {
    @kotlin.jvm.JvmField protected val aabb: AABB

    constructor(width: Double, height: Double) : super() {
        if (width <= 0.0) throw ValueOutOfRangeException("width", width, ValueOutOfRangeException.MUST_BE_GREATER_THAN, 0.0)
        if (height <= 0.0) throw ValueOutOfRangeException("height", height, ValueOutOfRangeException.MUST_BE_GREATER_THAN, 0.0)
        aabb = AABB(-width * 0.5, -height * 0.5, width * 0.5, height * 0.5)
    }

    protected constructor(bounds: AxisAlignedBounds) : super(bounds) { aabb = bounds.aabb.copy() }
    override fun copy() = AxisAlignedBounds(this)
    override fun isOutside(body: CollisionBody<*>) = !getBounds().overlaps(body.createAABB())
    override fun isOutside(aabb: AABB) = !getBounds().overlaps(aabb)
    override fun isOutside(aabb: AABB, transform: Transform?, fixture: Fixture?) = !getBounds().overlaps(aabb)
    open fun getBounds() = aabb.getTranslated(transform.getTranslation())
    open fun getWidth() = aabb.getWidth()
    open fun getHeight() = aabb.getHeight()
    override fun toString() = "AxisAlignedBounds[Width=${getWidth()}|Height=${getHeight()}|Translation=${getTranslation()}]"
}
