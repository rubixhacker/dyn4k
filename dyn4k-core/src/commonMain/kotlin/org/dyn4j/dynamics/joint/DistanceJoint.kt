/*
 * Copyright (c) 2010-2026 William Bittle  http://www.dyn4j.org/
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
package org.dyn4j.dynamics.joint

import kotlin.math.abs
import kotlin.math.max
import org.dyn4j.Epsilon
import org.dyn4j.JvmFieldBridge
import org.dyn4j.dynamics.PhysicsBody
import org.dyn4j.dynamics.Settings
import org.dyn4j.dynamics.TimeStep
import org.dyn4j.exception.ArgumentNullException
import org.dyn4j.exception.ValueOutOfRangeException
import org.dyn4j.geometry.Interval
import org.dyn4j.geometry.Vector2

open class DistanceJoint<T : PhysicsBody> : AbstractPairedBodyJoint<T>, LinearLimitsJoint, LinearSpringJoint {
    @JvmFieldBridge protected val localAnchor1: Vector2
    @JvmFieldBridge protected val localAnchor2: Vector2
    @get:kotlin.jvm.JvmName("readRestDistance")
    @set:kotlin.jvm.JvmName("writeRestDistance")
    @JvmFieldBridge protected var restDistance: Double
    @get:kotlin.jvm.JvmName("readSpringEnabled")
    @set:kotlin.jvm.JvmName("writeSpringEnabled")
    @JvmFieldBridge protected var springEnabled = false
    @get:kotlin.jvm.JvmName("readSpringMode")
    @set:kotlin.jvm.JvmName("writeSpringMode")
    @JvmFieldBridge protected var springMode = Joint.SPRING_MODE_FREQUENCY
    @get:kotlin.jvm.JvmName("readSpringFrequency")
    @set:kotlin.jvm.JvmName("writeSpringFrequency")
    @JvmFieldBridge protected var springFrequency = 8.0
    @get:kotlin.jvm.JvmName("readSpringStiffness")
    @set:kotlin.jvm.JvmName("writeSpringStiffness")
    @JvmFieldBridge protected var springStiffness = 0.0
    @get:kotlin.jvm.JvmName("readSpringDamperEnabled")
    @set:kotlin.jvm.JvmName("writeSpringDamperEnabled")
    @JvmFieldBridge protected var springDamperEnabled = false
    @get:kotlin.jvm.JvmName("readSpringDampingRatio")
    @set:kotlin.jvm.JvmName("writeSpringDampingRatio")
    @JvmFieldBridge protected var springDampingRatio = 0.3
    @JvmFieldBridge protected var springMaximumForceEnabled = false
    @JvmFieldBridge protected var springMaximumForce = 1000.0
    @get:kotlin.jvm.JvmName("readUpperLimit")
    @set:kotlin.jvm.JvmName("writeUpperLimit")
    @JvmFieldBridge protected var upperLimit: Double
    @get:kotlin.jvm.JvmName("readLowerLimit")
    @set:kotlin.jvm.JvmName("writeLowerLimit")
    @JvmFieldBridge protected var lowerLimit: Double
    @get:kotlin.jvm.JvmName("readUpperLimitEnabled")
    @set:kotlin.jvm.JvmName("writeUpperLimitEnabled")
    @JvmFieldBridge protected var upperLimitEnabled = false
    @get:kotlin.jvm.JvmName("readLowerLimitEnabled")
    @set:kotlin.jvm.JvmName("writeLowerLimitEnabled")
    @JvmFieldBridge protected var lowerLimitEnabled = false
    @JvmFieldBridge internal var currentDistance: Double
    @JvmFieldBridge internal var damping = 0.0
    @JvmFieldBridge internal val n = Vector2()
    @JvmFieldBridge internal var gamma = 0.0
    @JvmFieldBridge internal var bias = 0.0
    @JvmFieldBridge internal var mass = 0.0
    @JvmFieldBridge internal var softMass = 0.0
    @JvmFieldBridge internal var impulse = 0.0
    @JvmFieldBridge internal var upperLimitImpulse = 0.0
    @JvmFieldBridge internal var lowerLimitImpulse = 0.0

    constructor(body1: T, body2: T, anchor1: Vector2?, anchor2: Vector2?) : super(body1, body2) {
        if (anchor1 == null) throw ArgumentNullException("anchor1")
        if (anchor2 == null) throw ArgumentNullException("anchor2")
        collisionAllowed = false
        localAnchor1 = body1.getLocalPoint(anchor1)
        localAnchor2 = body2.getLocalPoint(anchor2)
        restDistance = anchor1.distance(anchor2)
        currentDistance = restDistance
        upperLimit = restDistance
        lowerLimit = restDistance
    }
    protected constructor(joint: DistanceJoint<T>) : this(joint, null, null)
    protected constructor(joint: DistanceJoint<T>, body1: T?, body2: T?) : super(joint, body1, body2) {
        localAnchor1 = joint.localAnchor1.copy()
        localAnchor2 = joint.localAnchor2.copy()
        restDistance = joint.restDistance
        springEnabled = joint.springEnabled
        springMode = joint.springMode
        springFrequency = joint.springFrequency
        springStiffness = joint.springStiffness
        springDamperEnabled = joint.springDamperEnabled
        springDampingRatio = joint.springDampingRatio
        springMaximumForceEnabled = joint.springMaximumForceEnabled
        springMaximumForce = joint.springMaximumForce
        upperLimit = joint.upperLimit
        lowerLimit = joint.lowerLimit
        upperLimitEnabled = joint.upperLimitEnabled
        lowerLimitEnabled = joint.lowerLimitEnabled
        currentDistance = joint.currentDistance
        damping = joint.damping
        n.set(joint.n)
        gamma = joint.gamma
        bias = joint.bias
        mass = joint.mass
        softMass = joint.softMass
        impulse = joint.impulse
        upperLimitImpulse = joint.upperLimitImpulse
        lowerLimitImpulse = joint.lowerLimitImpulse
    }

    override fun copy() = DistanceJoint(this)
    override fun copy(body1: T?, body2: T?) = DistanceJoint(this, body1, body2)
    override fun toString() = "DistanceJoint[${super.toString()}|Anchor1=${getAnchor1()}|Anchor2=${getAnchor2()}|Frequency=$springFrequency|DampingRatio=$springDampingRatio|RestDistance=$restDistance|LowerLimit=$lowerLimit|UpperLimit=$upperLimit|LowerLimitEnabled=$lowerLimitEnabled|UpperLimitEnabled=$upperLimitEnabled]"

    override fun initializeConstraints(step: TimeStep?, settings: Settings?) {
        val s = step!!
        val cfg = settings!!
        val t1 = body1.getTransform()
        val t2 = body2.getTransform()
        val m1 = body1.getMass()
        val m2 = body2.getMass()
        val invM1 = m1.getInverseMass()
        val invM2 = m2.getInverseMass()
        val invI1 = m1.getInverseInertia()
        val invI2 = m2.getInverseInertia()
        val r1 = t1.getTransformedR(body1.getLocalCenter().to(localAnchor1))
        val r2 = t2.getTransformedR(body2.getLocalCenter().to(localAnchor2))
        n.set(r1.sum(body1.getWorldCenter()).subtract(r2.sum(body2.getWorldCenter())))
        currentDistance = n.getMagnitude()
        if (currentDistance < cfg.getLinearTolerance()) {
            n.zero()
            upperLimitImpulse = 0.0
            lowerLimitImpulse = 0.0
            return
        }
        n.multiply(1.0 / currentDistance)
        if (!upperLimitEnabled) upperLimitImpulse = 0.0
        if (!lowerLimitEnabled) lowerLimitImpulse = 0.0
        val cr1n = r1.cross(n)
        val cr2n = r2.cross(n)
        var invMass = invM1 + invI1 * cr1n * cr1n + invM2 + invI2 * cr2n * cr2n
        mass = if (invMass <= Epsilon.E) 0.0 else 1.0 / invMass
        if (springEnabled) {
            updateSpringCoefficients()
            val dt = s.getDeltaTime()
            val x = currentDistance - restDistance
            gamma = getConstraintImpulseMixing(dt, springStiffness, damping)
            val erp = getErrorReductionParameter(dt, springStiffness, damping)
            bias = x * erp
            invMass += gamma
            softMass = if (invMass <= Epsilon.E) 0.0 else 1.0 / invMass
        } else {
            gamma = 0.0
            bias = 0.0
            damping = 0.0
            softMass = mass
        }
        if (cfg.isWarmStartingEnabled()) {
            impulse *= s.getDeltaTimeRatio()
            upperLimitImpulse *= s.getDeltaTimeRatio()
            lowerLimitImpulse *= s.getDeltaTimeRatio()
            applyImpulse(n.product(impulse + lowerLimitImpulse - upperLimitImpulse), r1, r2, invM1, invM2, invI1, invI2)
        } else {
            impulse = 0.0
            upperLimitImpulse = 0.0
            lowerLimitImpulse = 0.0
        }
    }

    override fun solveVelocityConstraints(step: TimeStep?, settings: Settings?) {
        val s = step!!
        val t1 = body1.getTransform()
        val t2 = body2.getTransform()
        val m1 = body1.getMass()
        val m2 = body2.getMass()
        val invM1 = m1.getInverseMass()
        val invM2 = m2.getInverseMass()
        val invI1 = m1.getInverseInertia()
        val invI2 = m2.getInverseInertia()
        val r1 = t1.getTransformedR(body1.getLocalCenter().to(localAnchor1))
        val r2 = t2.getTransformedR(body2.getLocalCenter().to(localAnchor2))
        val v1 = body1.getLinearVelocity().sum(r1.cross(body1.getAngularVelocity()))
        val v2 = body2.getLinearVelocity().sum(r2.cross(body2.getAngularVelocity()))
        val invdt = s.getInverseDeltaTime()
        if (lowerLimit < upperLimit) {
            if (springEnabled) {
                val jv = n.dot(v1.difference(v2))
                var p = -softMass * (jv + bias + gamma * impulse)
                if (springMaximumForceEnabled) {
                    val old = impulse
                    val maxImpulse = s.getDeltaTime() * springMaximumForce
                    impulse = Interval.clamp(impulse + p, -maxImpulse, maxImpulse)
                    p = impulse - old
                } else impulse += p
                applyImpulse(n.product(p), r1, r2, invM1, invM2, invI1, invI2)
            }
            if (lowerLimitEnabled) {
                val d = currentDistance - lowerLimit
                val jv = n.dot(v1.difference(v2))
                val old = lowerLimitImpulse
                lowerLimitImpulse = max(0.0, lowerLimitImpulse - mass * (jv + max(d, 0.0) * invdt))
                applyImpulse(n.product(lowerLimitImpulse - old), r1, r2, invM1, invM2, invI1, invI2)
            }
            if (upperLimitEnabled) {
                val d = upperLimit - currentDistance
                val jv = n.dot(v2.difference(v1))
                val old = upperLimitImpulse
                upperLimitImpulse = max(0.0, upperLimitImpulse - mass * (jv + max(d, 0.0) * invdt))
                applyImpulse(n.product(old - upperLimitImpulse), r1, r2, invM1, invM2, invI1, invI2)
            }
        } else {
            val jv = n.dot(v1.difference(v2))
            var p = -softMass * (jv + bias + gamma * impulse)
            if (springEnabled && springMaximumForceEnabled) {
                val old = impulse
                val maxImpulse = s.getDeltaTime() * springMaximumForce
                impulse = Interval.clamp(impulse + p, -maxImpulse, maxImpulse)
                p = impulse - old
            } else impulse += p
            applyImpulse(n.product(p), r1, r2, invM1, invM2, invI1, invI2)
        }
    }

    private fun applyImpulse(j: Vector2, r1: Vector2, r2: Vector2, invM1: Double, invM2: Double, invI1: Double, invI2: Double) {
        body1.getLinearVelocity().add(j.product(invM1))
        body1.setAngularVelocity(body1.getAngularVelocity() + invI1 * r1.cross(j))
        body2.getLinearVelocity().subtract(j.product(invM2))
        body2.setAngularVelocity(body2.getAngularVelocity() - invI2 * r2.cross(j))
    }

    override fun solvePositionConstraints(step: TimeStep?, settings: Settings?): Boolean {
        val tolerance = settings!!.getLinearTolerance()
        val t1 = body1.getTransform()
        val t2 = body2.getTransform()
        val m1 = body1.getMass()
        val m2 = body2.getMass()
        val invM1 = m1.getInverseMass()
        val invM2 = m2.getInverseMass()
        val invI1 = m1.getInverseInertia()
        val invI2 = m2.getInverseInertia()
        val c1 = body1.getWorldCenter()
        val c2 = body2.getWorldCenter()
        val r1 = t1.getTransformedR(body1.getLocalCenter().to(localAnchor1))
        val r2 = t2.getTransformedR(body2.getLocalCenter().to(localAnchor2))
        val normal = r1.sum(c1).subtract(r2.sum(c2))
        val length = normal.normalize()
        val c = if (upperLimitEnabled && lowerLimitEnabled && abs(upperLimit - lowerLimit) < 2.0 * tolerance) {
            length - lowerLimit
        } else if (lowerLimitEnabled && length < lowerLimit) {
            length - lowerLimit
        } else if (upperLimitEnabled && length > upperLimit) {
            length - upperLimit
        } else if (!upperLimitEnabled && !lowerLimitEnabled && !springEnabled) {
            length - restDistance
        } else return true
        val j = normal.product(-mass * c)
        body1.translate(j.product(invM1))
        body1.rotate(invI1 * r1.cross(j), c1)
        body2.translate(j.product(-invM2))
        body2.rotate(-invI2 * r2.cross(j), c2)
        return abs(c) < tolerance
    }

    protected open fun updateSpringCoefficients() {
        val reduced = getReducedMass()
        val natural = if (springMode == Joint.SPRING_MODE_FREQUENCY) {
            getNaturalFrequency(springFrequency).also { springStiffness = getSpringStiffness(reduced, it) }
        } else {
            getNaturalFrequency(springStiffness, reduced).also { springFrequency = getFrequency(it) }
        }
        damping = if (springDamperEnabled) getSpringDampingCoefficient(reduced, natural, springDampingRatio) else 0.0
    }

    open fun getAnchor1() = body1.getWorldPoint(localAnchor1)
    open fun getAnchor2() = body2.getWorldPoint(localAnchor2)
    override fun getReactionForce(invdt: Double) = n.product((impulse + lowerLimitImpulse - upperLimitImpulse) * invdt)
    override fun getReactionTorque(invdt: Double) = 0.0
    override fun shift(shift: Vector2) {}
    open fun getRestDistance() = restDistance
    open fun setRestDistance(distance: Double) {
        nonnegative("distance", distance)
        if (restDistance != distance) { wakeBodies(); restDistance = distance }
    }
    open fun getCurrentDistance() = body1.getTransform().getTransformed(localAnchor1).distance(body2.getTransform().getTransformed(localAnchor2))
    override fun getSpringDampingRatio() = springDampingRatio
    override fun setSpringDampingRatio(dampingRatio: Double) {
        nonnegative("dampingRatio", dampingRatio)
        if (dampingRatio > 1.0) throw ValueOutOfRangeException("dampingRatio", dampingRatio, ValueOutOfRangeException.MUST_BE_LESS_THAN_OR_EQUAL_TO, 1.0)
        if (springDampingRatio != dampingRatio) {
            springDampingRatio = dampingRatio
            if (springEnabled && springDamperEnabled) wakeBodies()
        }
    }
    override fun getSpringFrequency() = springFrequency
    override fun getSpringStiffness() = springStiffness
    override fun setSpringFrequency(frequency: Double) {
        nonnegative("frequency", frequency)
        springMode = Joint.SPRING_MODE_FREQUENCY
        if (springFrequency != frequency) { springFrequency = frequency; if (springEnabled) wakeBodies() }
    }
    override fun setSpringStiffness(stiffness: Double) {
        nonnegative("stiffness", stiffness)
        springMode = Joint.SPRING_MODE_STIFFNESS
        if (springStiffness != stiffness) { springStiffness = stiffness; if (springEnabled) wakeBodies() }
    }
    override fun getMaximumSpringForce() = springMaximumForce
    override fun setMaximumSpringForce(maximum: Double) {
        nonnegative("maximum", maximum)
        if (springMaximumForce != maximum) { springMaximumForce = maximum; if (springEnabled && springMaximumForceEnabled) wakeBodies() }
    }
    override fun isMaximumSpringForceEnabled() = springMaximumForceEnabled
    override fun setMaximumSpringForceEnabled(enabled: Boolean) {
        if (springMaximumForceEnabled != enabled) { springMaximumForceEnabled = enabled; if (springEnabled) wakeBodies() }
    }
    override fun isSpringEnabled() = springEnabled
    override fun setSpringEnabled(enabled: Boolean) {
        if (springEnabled != enabled) { springEnabled = enabled; wakeBodies() }
    }
    override fun isSpringDamperEnabled() = springDamperEnabled
    override fun setSpringDamperEnabled(enabled: Boolean) {
        if (springDamperEnabled != enabled) { springDamperEnabled = enabled; if (springEnabled) wakeBodies() }
    }
    override fun getSpringForce(invdt: Double) = if (springEnabled) impulse * invdt else 0.0
    override fun getSpringMode() = springMode
    override fun getUpperLimit() = upperLimit
    override fun setUpperLimit(upperLimit: Double) {
        nonnegative("upperLimit", upperLimit)
        if (upperLimit < lowerLimit) throw ValueOutOfRangeException("upperLimit", upperLimit, ValueOutOfRangeException.MUST_BE_GREATER_THAN_OR_EQUAL_TO, "lowerLimit", lowerLimit)
        if (this.upperLimit != upperLimit) { if (upperLimitEnabled) wakeBodies(); this.upperLimit = upperLimit; upperLimitImpulse = 0.0 }
    }
    override fun setUpperLimitEnabled(flag: Boolean) {
        if (upperLimitEnabled != flag) { wakeBodies(); upperLimitEnabled = flag; upperLimitImpulse = 0.0 }
    }
    override fun isUpperLimitEnabled() = upperLimitEnabled
    override fun getLowerLimit() = lowerLimit
    override fun setLowerLimit(lowerLimit: Double) {
        nonnegative("lowerLimit", lowerLimit)
        if (lowerLimit > upperLimit) throw ValueOutOfRangeException("lowerLimit", lowerLimit, ValueOutOfRangeException.MUST_BE_LESS_THAN_OR_EQUAL_TO, "upperLimit", upperLimit)
        if (this.lowerLimit != lowerLimit) { if (lowerLimitEnabled) wakeBodies(); this.lowerLimit = lowerLimit; lowerLimitImpulse = 0.0 }
    }
    override fun setLowerLimitEnabled(flag: Boolean) {
        if (lowerLimitEnabled != flag) { wakeBodies(); lowerLimitEnabled = flag; lowerLimitImpulse = 0.0 }
    }
    override fun isLowerLimitEnabled() = lowerLimitEnabled
    override fun setLimits(lowerLimit: Double, upperLimit: Double) {
        nonnegative("lowerLimit", lowerLimit)
        nonnegative("upperLimit", upperLimit)
        if (lowerLimit > upperLimit) throw ValueOutOfRangeException("lowerLimit", lowerLimit, ValueOutOfRangeException.MUST_BE_LESS_THAN_OR_EQUAL_TO, "upperLimit", upperLimit)
        if (this.lowerLimit != lowerLimit || this.upperLimit != upperLimit) {
            if (lowerLimitEnabled || upperLimitEnabled) wakeBodies()
            this.lowerLimit = lowerLimit
            this.upperLimit = upperLimit
            lowerLimitImpulse = 0.0
            upperLimitImpulse = 0.0
        }
    }
    override fun setLimitsEnabled(lowerLimit: Double, upperLimit: Double) { setLimitsEnabled(true); setLimits(lowerLimit, upperLimit) }
    override fun setLimitsEnabled(flag: Boolean) {
        if (upperLimitEnabled != flag || lowerLimitEnabled != flag) {
            upperLimitEnabled = flag
            lowerLimitEnabled = flag
            wakeBodies()
            upperLimitImpulse = 0.0
            lowerLimitImpulse = 0.0
        }
    }
    override fun setLimits(limit: Double) {
        nonnegative("limit", limit)
        if (lowerLimit != limit || upperLimit != limit) {
            if (lowerLimitEnabled || upperLimitEnabled) wakeBodies()
            lowerLimit = limit
            upperLimit = limit
            lowerLimitImpulse = 0.0
            upperLimitImpulse = 0.0
        }
    }
    override fun setLimitsEnabled(limit: Double) { setLimitsEnabled(true); setLimits(limit) }
    private fun nonnegative(name: String, value: Double) {
        if (value < 0.0) throw ValueOutOfRangeException(name, value, ValueOutOfRangeException.MUST_BE_GREATER_THAN_OR_EQUAL_TO, 0.0)
    }
    private fun wakeBodies() { body1.setAtRest(false); body2.setAtRest(false) }
}
