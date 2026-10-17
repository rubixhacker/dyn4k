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
package org.dyn4j.geometry

import org.dyn4j.Copyable
import org.dyn4j.Epsilon
import org.dyn4j.JvmFieldBridge
import org.dyn4j.exception.ArgumentNullException
import org.dyn4j.exception.EmptyCollectionException
import org.dyn4j.exception.NullElementException
import org.dyn4j.exception.ValueOutOfRangeException

open class Mass : Copyable<Mass> {
    @get:kotlin.jvm.JvmName("getTypeField")
    @set:kotlin.jvm.JvmName("setTypeField")
    @JvmFieldBridge private var type: MassType
    @get:kotlin.jvm.JvmName("getCenterField")
    @JvmFieldBridge private val center: Vector2
    @get:kotlin.jvm.JvmName("getMassField")
    @JvmFieldBridge private val mass: Double
    @get:kotlin.jvm.JvmName("getInertiaField")
    @JvmFieldBridge private val inertia: Double
    @JvmFieldBridge private val invMass: Double
    @JvmFieldBridge private val invInertia: Double

    constructor() {
        type = MassType.INFINITE
        center = Vector2()
        mass = 0.0
        inertia = 0.0
        invMass = 0.0
        invInertia = 0.0
    }

    constructor(center: Vector2?, mass: Double, inertia: Double) {
        if (center == null) throw ArgumentNullException("center")
        if (mass < 0.0) throw ValueOutOfRangeException("mass", mass, ValueOutOfRangeException.MUST_BE_GREATER_THAN_OR_EQUAL_TO, 0.0)
        if (inertia < 0.0) throw ValueOutOfRangeException("inertia", inertia, ValueOutOfRangeException.MUST_BE_GREATER_THAN_OR_EQUAL_TO, 0.0)
        this.center = center.copy()
        this.mass = mass
        this.inertia = inertia
        type = MassType.NORMAL
        if (mass > Epsilon.E) {
            invMass = 1.0 / mass
        } else {
            invMass = 0.0
            type = MassType.FIXED_LINEAR_VELOCITY
        }
        if (inertia > Epsilon.E) {
            invInertia = 1.0 / inertia
        } else {
            invInertia = 0.0
            type = MassType.FIXED_ANGULAR_VELOCITY
        }
        if (mass <= Epsilon.E && inertia <= Epsilon.E) type = MassType.INFINITE
    }

    constructor(mass: Mass?) {
        if (mass == null) throw ArgumentNullException("mass")
        type = mass.type
        center = mass.center.copy()
        this.mass = mass.mass
        inertia = mass.inertia
        invMass = mass.invMass
        invInertia = mass.invInertia
    }

    override fun copy() = Mass(this)
    override fun toString() = "Mass[Type=$type|Center=$center|Mass=$mass|Inertia=$inertia]"
    override fun equals(other: Any?) = other is Mass && type == other.type &&
        mass == other.mass && inertia == other.inertia && center == other.center

    override fun hashCode(): Int {
        var result = 31 + center.hashCode()
        for (value in doubleArrayOf(inertia, invInertia, invMass, mass)) {
            val bits = value.toBits()
            result = 31 * result + (bits xor (bits ushr 32)).toInt()
        }
        return 31 * result + type.hashCode()
    }

    open fun isInfinite() = type == MassType.INFINITE
    open fun setType(type: MassType?) {
        if (type == null) throw ArgumentNullException("type")
        if (type == MassType.NORMAL && (mass <= 0.0 || inertia <= 0.0)) return
        if (type == MassType.FIXED_LINEAR_VELOCITY && inertia <= 0.0) return
        if (type == MassType.FIXED_ANGULAR_VELOCITY && mass <= 0.0) return
        this.type = type
    }
    open fun getType() = type
    open fun getCenter() = center
    open fun getMass() = if (type == MassType.INFINITE || type == MassType.FIXED_LINEAR_VELOCITY) 0.0 else mass
    open fun getInertia() = if (type == MassType.INFINITE || type == MassType.FIXED_ANGULAR_VELOCITY) 0.0 else inertia
    open fun getInverseMass() = if (type == MassType.INFINITE || type == MassType.FIXED_LINEAR_VELOCITY) 0.0 else invMass
    open fun getInverseInertia() = if (type == MassType.INFINITE || type == MassType.FIXED_ANGULAR_VELOCITY) 0.0 else invInertia

    companion object {
     fun create(masses: List<Mass?>?): Mass {
            if (masses == null) throw ArgumentNullException("masses")
            if (masses.isEmpty()) throw EmptyCollectionException("masses")
            if (masses.size == 1) return Mass(masses[0] ?: throw NullElementException("masses", 0))
            val center = Vector2()
            var totalMass = 0.0
            for ((index, item) in masses.withIndex()) {
                val component = item ?: throw NullElementException("masses", index)
                center.add(component.center.product(component.mass))
                totalMass += component.mass
            }
            if (totalMass > 0.0) center.divide(totalMass)
            var totalInertia = 0.0
            for (component in masses) {
                component!!
                totalInertia += component.inertia + component.mass * component.center.distanceSquared(center)
            }
            return Mass(center, totalMass, totalInertia)
        }
    }
}
