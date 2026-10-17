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

import org.dyn4j.Copyable
import org.dyn4j.JvmFieldBridge
import org.dyn4j.exception.ArgumentNullException

open class Ray : Copyable<Ray> {
    @kotlin.jvm.JvmField protected var start: Vector2
    @kotlin.jvm.JvmField protected var direction: Vector2

    constructor(direction: Double) : this(Vector2(direction))
    constructor(direction: Vector2?) : this(Vector2(), direction)
    constructor(start: Vector2?, direction: Double) : this(start, Vector2(direction))
    constructor(start: Vector2?, direction: Vector2?) {
        if (start == null) throw ArgumentNullException("start")
        if (direction == null) throw ArgumentNullException("direction")
        if (direction.isZero()) throw IllegalArgumentException("The direction cannot be the zero vector")
        this.start = start
        this.direction = direction.getNormalized()
    }
    protected constructor(ray: Ray) {
        start = ray.start.copy()
        direction = ray.direction.copy()
    }

    override fun copy() = Ray(this)
    override fun toString() = "Ray[Start=$start|Direction=${getDirection()}]"
    open fun getStart() = start
    open fun setStart(start: Vector2?) {
        this.start = start ?: throw ArgumentNullException("start")
    }
    open fun setDirection(direction: Double) {
        this.direction = Vector2(direction)
    }
    open fun getDirection() = direction.getDirection()
    open fun setDirection(direction: Vector2?) {
        if (direction == null) throw ArgumentNullException("direction")
        if (direction.isZero()) throw IllegalArgumentException("The direction cannot be the zero vector")
        this.direction = direction
    }
    open fun getDirectionVector() = direction
}
