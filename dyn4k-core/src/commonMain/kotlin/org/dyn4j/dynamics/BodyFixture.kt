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

import org.dyn4j.DataContainer
import org.dyn4j.collision.Fixture
import org.dyn4j.exception.ValueOutOfRangeException
import org.dyn4j.geometry.Convex
import org.dyn4j.geometry.Mass
import kotlin.jvm.JvmField

open class BodyFixture : Fixture, DataContainer {
    @JvmField protected var density = DEFAULT_DENSITY
    @JvmField protected var friction = DEFAULT_FRICTION
    @JvmField protected var restitution = DEFAULT_RESTITUTION
    @JvmField protected var restitutionVelocity = DEFAULT_RESTITUTION_VELOCITY

    constructor(shape: Convex?) : super(shape)
    protected constructor(fixture: BodyFixture) : super(fixture) {
        density = fixture.density
        friction = fixture.friction
        restitution = fixture.restitution
        restitutionVelocity = fixture.restitutionVelocity
    }

    override fun copy(): Fixture = BodyFixture(this)
    open fun setDensity(density: Double) {
        if (density < 0.0) throw ValueOutOfRangeException("density", density, ValueOutOfRangeException.MUST_BE_GREATER_THAN_OR_EQUAL_TO, 0.0)
        this.density = density
    }
    open fun getDensity() = density
    internal fun rawDensity() = density
    open fun setFriction(friction: Double) {
        if (friction < 0.0) throw ValueOutOfRangeException("friction", friction, ValueOutOfRangeException.MUST_BE_GREATER_THAN_OR_EQUAL_TO, 0.0)
        this.friction = friction
    }
    open fun getFriction() = friction
    open fun setRestitution(restitution: Double) {
        if (restitution < 0.0) throw ValueOutOfRangeException("restitution", restitution, ValueOutOfRangeException.MUST_BE_GREATER_THAN_OR_EQUAL_TO, 0.0)
        this.restitution = restitution
    }
    open fun getRestitution() = restitution
    open fun setRestitutionVelocity(value: Double) { restitutionVelocity = value }
    open fun getRestitutionVelocity() = restitutionVelocity
    open fun createMass(): Mass = shape.createMass(density)
    override fun toString() = "BodyFixture[HashCode=${hashCode()}|Shape=$shape|Filter=$filter|IsSensor=$sensor|Density=$density|Friction=$friction|Restitution=$restitution|RestitutionVelocity=$restitutionVelocity]"

    companion object {
        const val DEFAULT_FRICTION = 0.2
        const val DEFAULT_RESTITUTION = 0.0
        const val DEFAULT_DENSITY = 1.0
        const val DEFAULT_RESTITUTION_VELOCITY = 1.0
    }
}
