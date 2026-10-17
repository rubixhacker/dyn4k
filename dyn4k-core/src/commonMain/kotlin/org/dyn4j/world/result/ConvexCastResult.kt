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
package org.dyn4j.world.result

import org.dyn4j.JvmFieldBridge
import org.dyn4j.collision.CollisionBody
import org.dyn4j.collision.Fixture
import org.dyn4j.collision.continuous.TimeOfImpact

open class ConvexCastResult<T : CollisionBody<E>, E : Fixture> : DetectResult<T, E>, Comparable<ConvexCastResult<T, E>> {
    @get:kotlin.jvm.JvmName("timeOfImpactField")
    @get:kotlin.jvm.JvmSynthetic
    @JvmFieldBridge protected val timeOfImpact: TimeOfImpact

    constructor() : super() {
        timeOfImpact = TimeOfImpact()
    }

    protected constructor(body: T?, fixture: E?, timeOfImpact: TimeOfImpact) : super(body, fixture) {
        this.timeOfImpact = timeOfImpact.copy()
    }

    protected constructor(result: ConvexCastResult<T, E>) : super(result) {
        timeOfImpact = result.timeOfImpact.copy()
    }

    open fun getTimeOfImpact(): TimeOfImpact = timeOfImpact
    open fun setTimeOfImpact(timeOfImpact: TimeOfImpact) { this.timeOfImpact.set(timeOfImpact) }

    @Deprecated("Use set(result)")
    open fun copy(result: ConvexCastResult<T, E>) {
        super.set(result)
        timeOfImpact.set(result.timeOfImpact)
    }

    open fun set(result: ConvexCastResult<T, E>) {
        super.set(result)
        timeOfImpact.set(result.timeOfImpact)
    }

    override fun compareTo(other: ConvexCastResult<T, E>): Int {
        val difference = timeOfImpact.getTime() - other.timeOfImpact.getTime()
        return when {
            difference < 0.0 -> -1
            difference > 0.0 -> 1
            else -> 0
        }
    }

    override fun copy(): ConvexCastResult<T, E> = ConvexCastResult(this)
}
