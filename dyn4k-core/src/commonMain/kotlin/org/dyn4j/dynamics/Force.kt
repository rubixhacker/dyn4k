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
package org.dyn4j.dynamics

import org.dyn4j.Copyable
import org.dyn4j.exception.ArgumentNullException
import org.dyn4j.geometry.Vector2
import kotlin.jvm.JvmField

open class Force : Copyable<Force> {
    @JvmField protected var force: Vector2

    constructor() { force = Vector2() }
    constructor(x: Double, y: Double) { force = Vector2(x, y) }
    constructor(force: Vector2?) { this.force = force ?: throw ArgumentNullException("force") }
    constructor(force: Force?) {
        this.force = (force ?: throw ArgumentNullException("force")).force.copy()
    }

    override fun copy() = Force(this)
    open fun set(x: Double, y: Double) { force.set(x, y) }
    open fun set(force: Vector2?) { this.force.set(force ?: throw ArgumentNullException("force")) }
    open fun set(force: Force?) { this.force.set((force ?: throw ArgumentNullException("force")).force) }
    open fun isComplete(elapsedTime: Double) = true
    open fun getForce(): Vector2 = force
    internal fun rawForce(): Vector2 = force
    override fun toString() = force.toString()
}
