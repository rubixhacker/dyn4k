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

import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.max
import org.dyn4j.Epsilon
import org.dyn4j.dynamics.PhysicsBody
import org.dyn4j.dynamics.Settings
import org.dyn4j.dynamics.TimeStep
import org.dyn4j.exception.ArgumentNullException
import org.dyn4j.exception.ValueOutOfRangeException
import org.dyn4j.geometry.Interval
import org.dyn4j.geometry.Matrix33
import org.dyn4j.geometry.Rotation
import org.dyn4j.geometry.Vector2
import org.dyn4j.geometry.Vector3

open class WeldJoint<T : PhysicsBody> : AbstractPairedBodyJoint<T>, AngularLimitsJoint, AngularSpringJoint {
    @kotlin.jvm.JvmField protected val localAnchor1: Vector2
    @kotlin.jvm.JvmField protected val localAnchor2: Vector2
    @kotlin.jvm.JvmField protected var limitsEnabled: Boolean
    @kotlin.jvm.JvmField protected var lowerLimit: Double
    @kotlin.jvm.JvmField protected var upperLimit: Double
    @kotlin.jvm.JvmField protected var referenceAngle: Double
    @kotlin.jvm.JvmField protected var limitOffset: Double
    @kotlin.jvm.JvmField protected var adjustedLowerLimit: Double
    @kotlin.jvm.JvmField protected var adjustedUpperLimit: Double
    @kotlin.jvm.JvmField protected var springEnabled: Boolean
    @kotlin.jvm.JvmField protected var springDamperEnabled: Boolean
    @kotlin.jvm.JvmField protected var springMode: Int
    @kotlin.jvm.JvmField protected var springFrequency: Double
    @kotlin.jvm.JvmField protected var springStiffness: Double
    @kotlin.jvm.JvmField protected var springDampingRatio: Double
    @kotlin.jvm.JvmField protected var springMaximumTorqueEnabled: Boolean
    @kotlin.jvm.JvmField protected var springMaximumTorque: Double
    @kotlin.jvm.JvmField internal var angle: Double
    @kotlin.jvm.JvmField internal val r1: Vector2
    @kotlin.jvm.JvmField internal val r2: Vector2
    @kotlin.jvm.JvmField internal val K: Matrix33
    @kotlin.jvm.JvmField internal var axialMass: Double
    @kotlin.jvm.JvmField internal var springMass: Double
    @kotlin.jvm.JvmField internal var damping: Double
    @kotlin.jvm.JvmField internal var bias: Double
    @kotlin.jvm.JvmField internal var gamma: Double
    @kotlin.jvm.JvmField internal val impulse: Vector3
    @kotlin.jvm.JvmField internal var springImpulse: Double
    @kotlin.jvm.JvmField internal var lowerLimitImpulse: Double
    @kotlin.jvm.JvmField internal var upperLimitImpulse: Double

    constructor(body1: T?, body2: T?, anchor: Vector2?) : super(body1, body2) {
        if (anchor == null) throw ArgumentNullException("anchor")
        localAnchor1 = this.body1.getLocalPoint(anchor)
        localAnchor2 = this.body2.getLocalPoint(anchor)
        referenceAngle = this.body2.getTransform().getRotationAngle() - this.body1.getTransform().getRotationAngle()
        lowerLimit = Rotation.getNormalizedAngle(referenceAngle)
        upperLimit = lowerLimit
        limitsEnabled = false
        limitOffset = 0.0
        adjustedLowerLimit = 0.0
        adjustedUpperLimit = 0.0
        calculateLimitOffsetAndAdjustedLimits()
        K = Matrix33()
        r1 = Vector2()
        r2 = Vector2()
        springMode = Joint.SPRING_MODE_FREQUENCY
        springEnabled = false
        springDamperEnabled = false
        springMaximumTorque = 1000.0
        springMaximumTorqueEnabled = false
        springStiffness = 0.0
        springFrequency = 8.0
        springDampingRatio = 0.3
        angle = 0.0
        axialMass = 0.0
        springMass = 0.0
        damping = 0.0
        gamma = 0.0
        bias = 0.0
        impulse = Vector3()
        springImpulse = 0.0
        lowerLimitImpulse = 0.0
        upperLimitImpulse = 0.0
    }

    protected constructor(joint: WeldJoint<T>) : this(joint, null, null)
    protected constructor(joint: WeldJoint<T>, body1: T?, body2: T?) : super(joint, body1, body2) {
        localAnchor1 = joint.localAnchor1.copy()
        localAnchor2 = joint.localAnchor2.copy()
        limitsEnabled = joint.limitsEnabled
        lowerLimit = joint.lowerLimit
        upperLimit = joint.upperLimit
        referenceAngle = joint.referenceAngle
        limitOffset = joint.limitOffset
        adjustedLowerLimit = joint.adjustedLowerLimit
        adjustedUpperLimit = joint.adjustedUpperLimit
        springMode = joint.springMode
        springEnabled = joint.springEnabled
        springFrequency = joint.springFrequency
        springStiffness = joint.springStiffness
        springDamperEnabled = joint.springDamperEnabled
        springDampingRatio = joint.springDampingRatio
        springMaximumTorqueEnabled = joint.springMaximumTorqueEnabled
        springMaximumTorque = joint.springMaximumTorque
        angle = joint.angle
        axialMass = joint.axialMass
        bias = joint.bias
        damping = joint.damping
        gamma = joint.gamma
        K = joint.K.copy()
        r1 = joint.r1.copy()
        r2 = joint.r2.copy()
        springMass = joint.springMass
        impulse = joint.impulse.copy()
        springImpulse = joint.springImpulse
        lowerLimitImpulse = joint.lowerLimitImpulse
        upperLimitImpulse = joint.upperLimitImpulse
    }

    override fun copy(): WeldJoint<T> = WeldJoint(this)
    override fun copy(body1: T?, body2: T?): WeldJoint<T> = WeldJoint(this, body1, body2)
    override fun toString(): String = "WeldJoint[${super.toString()}|Anchor=${getAnchor1()}|ReferenceAngle=$referenceAngle|Frequency=$springFrequency|DampingRatio=$springDampingRatio]"

    override fun initializeConstraints(step: TimeStep?, settings: Settings?) {
        val t1 = body1.getTransform()
        val t2 = body2.getTransform()
        val m1 = body1.getMass()
        val m2 = body2.getMass()
        val invM1 = m1.getInverseMass()
        val invM2 = m2.getInverseMass()
        val invI1 = m1.getInverseInertia()
        val invI2 = m2.getInverseInertia()
        angle = getRelativeRotation()
        t1.getTransformedR(body1.getLocalCenter().to(localAnchor1), r1)
        t2.getTransformedR(body2.getLocalCenter().to(localAnchor2), r2)
        K.m00 = invM1 + invM2 + r1.y * r1.y * invI1 + r2.y * r2.y * invI2
        K.m01 = -r1.y * r1.x * invI1 - r2.y * r2.x * invI2
        K.m02 = -r1.y * invI1 - r2.y * invI2
        K.m10 = K.m01
        K.m11 = invM1 + invM2 + r1.x * r1.x * invI1 + r2.x * r2.x * invI2
        K.m12 = r1.x * invI1 + r2.x * invI2
        K.m20 = K.m02
        K.m21 = K.m12
        K.m22 = invI1 + invI2
        axialMass = if (K.m22 > Epsilon.E) 1.0 / K.m22 else 0.0
        if (!limitsEnabled) {
            lowerLimitImpulse = 0.0
            upperLimitImpulse = 0.0
        }
        if (springEnabled) {
            val dt = step!!.getDeltaTime()
            var invI = K.m22
            updateSpringCoefficients()
            gamma = getConstraintImpulseMixing(dt, springStiffness, damping)
            val erp = getErrorReductionParameter(dt, springStiffness, damping)
            bias = angle * erp
            invI += gamma
            springMass = if (invI <= Epsilon.E) 0.0 else 1.0 / invI
        } else {
            springMass = 0.0
            gamma = 0.0
            bias = 0.0
            springImpulse = 0.0
        }
        if (settings!!.isWarmStartingEnabled()) {
            val dtr = step!!.getDeltaTimeRatio()
            impulse.multiply(dtr)
            springImpulse *= dtr
            lowerLimitImpulse *= dtr
            upperLimitImpulse *= dtr
            val axialImpulse = impulse.z + springImpulse + lowerLimitImpulse - upperLimitImpulse
            val applied = Vector2(impulse.x, impulse.y)
            body1.getLinearVelocity().subtract(applied.product(invM1))
            body1.setAngularVelocity(body1.getAngularVelocity() - invI1 * (r1.cross(applied) + axialImpulse))
            body2.getLinearVelocity().add(applied.product(invM2))
            body2.setAngularVelocity(body2.getAngularVelocity() + invI2 * (r2.cross(applied) + axialImpulse))
        } else {
            impulse.zero()
            springImpulse = 0.0
            lowerLimitImpulse = 0.0
            upperLimitImpulse = 0.0
        }
    }

    override fun solveVelocityConstraints(step: TimeStep?, settings: Settings?) {
        val m1 = body1.getMass()
        val m2 = body2.getMass()
        val invM1 = m1.getInverseMass()
        val invM2 = m2.getInverseMass()
        val invI1 = m1.getInverseInertia()
        val invI2 = m2.getInverseInertia()
        if (springEnabled) {
            val rav = body2.getAngularVelocity() - body1.getAngularVelocity()
            var applied = -springMass * (rav + bias + gamma * springImpulse)
            if (springMaximumTorqueEnabled) {
                val old = springImpulse
                val maxImpulse = springMaximumTorque * step!!.getDeltaTime()
                springImpulse = Interval.clamp(springImpulse + applied, -maxImpulse, maxImpulse)
                applied = springImpulse - old
            } else {
                springImpulse += applied
            }
            body1.setAngularVelocity(body1.getAngularVelocity() - invI1 * applied)
            body2.setAngularVelocity(body2.getAngularVelocity() + invI2 * applied)
            if (limitsEnabled && axialMass > 0.0) {
                val cLower = angle - adjustedLowerLimit
                val cdotLower = body2.getAngularVelocity() - body1.getAngularVelocity()
                var limitImpulse = -axialMass * (cdotLower + max(cLower, 0.0) * step!!.getInverseDeltaTime())
                val oldLower = lowerLimitImpulse
                lowerLimitImpulse = max(lowerLimitImpulse + limitImpulse, 0.0)
                limitImpulse = lowerLimitImpulse - oldLower
                body1.setAngularVelocity(body1.getAngularVelocity() - invI1 * limitImpulse)
                body2.setAngularVelocity(body2.getAngularVelocity() + invI2 * limitImpulse)
                val cUpper = adjustedUpperLimit - angle
                val cdotUpper = body1.getAngularVelocity() - body2.getAngularVelocity()
                limitImpulse = -axialMass * (cdotUpper + max(cUpper, 0.0) * step.getInverseDeltaTime())
                val oldUpper = upperLimitImpulse
                upperLimitImpulse = max(upperLimitImpulse + limitImpulse, 0.0)
                limitImpulse = upperLimitImpulse - oldUpper
                body1.setAngularVelocity(body1.getAngularVelocity() + invI1 * limitImpulse)
                body2.setAngularVelocity(body2.getAngularVelocity() - invI2 * limitImpulse)
            }
            val v1 = body1.getLinearVelocity().sum(r1.cross(body1.getAngularVelocity()))
            val v2 = body2.getLinearVelocity().sum(r2.cross(body2.getAngularVelocity()))
            val relv = v2.subtract(v1)
            val pointImpulse = K.solve22(relv.negate())
            impulse.x += pointImpulse.x
            impulse.y += pointImpulse.y
            body1.getLinearVelocity().subtract(pointImpulse.product(invM1))
            body1.setAngularVelocity(body1.getAngularVelocity() - invI1 * r1.cross(pointImpulse))
            body2.getLinearVelocity().add(pointImpulse.product(invM2))
            body2.setAngularVelocity(body2.getAngularVelocity() + invI2 * r2.cross(pointImpulse))
        } else {
            val v1 = body1.getLinearVelocity().sum(r1.cross(body1.getAngularVelocity()))
            val v2 = body2.getLinearVelocity().sum(r2.cross(body2.getAngularVelocity()))
            val relv = v2.subtract(v1)
            val c = Vector3(relv.x, relv.y, body2.getAngularVelocity() - body1.getAngularVelocity())
            val applied = if (K.m22 > 0.0) K.solve33(c.negate()) else {
                val point = K.solve22(relv).negate()
                Vector3(point.x, point.y, 0.0)
            }
            impulse.add(applied)
            val point = Vector2(applied.x, applied.y)
            body1.getLinearVelocity().subtract(point.product(invM1))
            body1.setAngularVelocity(body1.getAngularVelocity() - invI1 * (r1.cross(point) + applied.z))
            body2.getLinearVelocity().add(point.product(invM2))
            body2.setAngularVelocity(body2.getAngularVelocity() + invI2 * (r2.cross(point) + applied.z))
        }
    }

    override fun solvePositionConstraints(step: TimeStep?, settings: Settings?): Boolean {
        val linearTolerance = settings!!.getLinearTolerance()
        val angularTolerance = settings.getAngularTolerance()
        val maxAngularCorrection = settings.getMaximumAngularCorrection()
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
        val p1 = body1.getWorldCenter().add(r1)
        val p2 = body2.getWorldCenter().add(r2)
        val relativePosition = p2.difference(p1)
        val relativeRotation = getRelativeRotation()
        val c = Vector3(relativePosition.x, relativePosition.y, relativeRotation)
        val linearError = relativePosition.getMagnitude()
        var angularError = abs(relativeRotation)
        val k = Matrix33()
        k.m00 = invM1 + invM2 + r1.y * r1.y * invI1 + r2.y * r2.y * invI2
        k.m01 = -r1.y * r1.x * invI1 - r2.y * r2.x * invI2
        k.m02 = -r1.y * invI1 - r2.y * invI2
        k.m10 = k.m01
        k.m11 = invM1 + invM2 + r1.x * r1.x * invI1 + r2.x * r2.x * invI2
        k.m12 = r1.x * invI1 + r2.x * invI2
        k.m20 = k.m02
        k.m21 = k.m12
        k.m22 = invI1 + invI2
        if (springEnabled) {
            angularError = 0.0
            if (limitsEnabled && axialMass > 0.0) {
                val c3 = if (abs(adjustedUpperLimit - adjustedLowerLimit) < 2.0 * angularTolerance) {
                    Interval.clamp(relativeRotation - adjustedLowerLimit, -maxAngularCorrection, maxAngularCorrection)
                } else if (relativeRotation <= adjustedLowerLimit) {
                    Interval.clamp(relativeRotation - adjustedLowerLimit + angularTolerance, -maxAngularCorrection, 0.0)
                } else if (relativeRotation >= adjustedUpperLimit) {
                    Interval.clamp(relativeRotation - adjustedUpperLimit - angularTolerance, 0.0, maxAngularCorrection)
                } else 0.0
                val applied = -axialMass * c3
                body1.rotateAboutCenter(-invI1 * applied)
                body2.rotateAboutCenter(invI2 * applied)
                angularError = abs(c3)
            }
            val applied = k.solve22(relativePosition.negate())
            body1.translate(applied.product(-invM1))
            body1.rotateAboutCenter(-invI1 * r1.cross(applied))
            body2.translate(applied.product(invM2))
            body2.rotateAboutCenter(invI2 * r2.cross(applied))
        } else {
            val applied = if (k.m22 > 0.0) k.solve33(c.negate()) else {
                val point = k.solve22(relativePosition).negate()
                Vector3(point.x, point.y, 0.0)
            }
            val point = Vector2(applied.x, applied.y)
            body1.translate(point.product(-invM1))
            body1.rotateAboutCenter(-invI1 * (r1.cross(point) + applied.z))
            body2.translate(point.product(invM2))
            body2.rotateAboutCenter(invI2 * (r2.cross(point) + applied.z))
        }
        return linearError <= linearTolerance && angularError <= angularTolerance
    }

    private fun calculateLimitOffsetAndAdjustedLimits() {
        val lower = Rotation.getNormalizedAngle(lowerLimit)
        val upper = Rotation.getNormalizedAngle(upperLimit)
        val sameSign = (lower > 0.0) == (upper > 0.0)
        val reversed = lower > upper
        val average = (lower + upper) * 0.5
        var difference = lower - upper
        if (sameSign && reversed) {
            if (lower > 0.0) difference *= -1.0
            limitOffset = average + difference
            adjustedLowerLimit = lower - average - PI
            adjustedUpperLimit = upper - average + PI
        } else if (reversed) {
            limitOffset = PI
            adjustedLowerLimit = upper
            adjustedUpperLimit = lower
        } else {
            limitOffset = 0.0
            adjustedLowerLimit = lower
            adjustedUpperLimit = upper
        }
    }

    private fun getRelativeRotation(): Double = Rotation.getNormalizedAngle(
        body2.getTransform().getRotationAngle() - body1.getTransform().getRotationAngle() - referenceAngle - limitOffset
    )

    protected open fun updateSpringCoefficients() {
        val reducedInertia = getReducedInertia()
        var naturalFrequency = 0.0
        if (springMode == Joint.SPRING_MODE_FREQUENCY) {
            naturalFrequency = getNaturalFrequency(springFrequency)
            springStiffness = getSpringStiffness(reducedInertia, naturalFrequency)
        } else if (springMode == Joint.SPRING_MODE_STIFFNESS) {
            naturalFrequency = getNaturalFrequency(springStiffness, reducedInertia)
            springFrequency = getFrequency(naturalFrequency)
        }
        damping = if (springDamperEnabled) getSpringDampingCoefficient(reducedInertia, naturalFrequency, springDampingRatio) else 0.0
    }

    open fun getAngularTranslation(): Double = Rotation.getNormalizedAngle(
        body2.getTransform().getRotationAngle() - body1.getTransform().getRotationAngle() - referenceAngle
    )
    open fun getAnchor1(): Vector2 = body1.getWorldPoint(localAnchor1)
    open fun getAnchor2(): Vector2 = body2.getWorldPoint(localAnchor2)
    override fun getReactionForce(invdt: Double): Vector2 = Vector2(impulse.x, impulse.y).multiply(invdt)
    override fun getReactionTorque(invdt: Double): Double = (impulse.z + springImpulse + lowerLimitImpulse - upperLimitImpulse) * invdt
    override fun shift(shift: Vector2) {}

    override fun getSpringDampingRatio(): Double = springDampingRatio
    override fun setSpringDampingRatio(dampingRatio: Double) {
        if (dampingRatio < 0.0) throw ValueOutOfRangeException("dampingRatio", dampingRatio, ValueOutOfRangeException.MUST_BE_GREATER_THAN_OR_EQUAL_TO, 0.0)
        if (dampingRatio > 1.0) throw ValueOutOfRangeException("dampingRatio", dampingRatio, ValueOutOfRangeException.MUST_BE_LESS_THAN_OR_EQUAL_TO, 1.0)
        if (springDampingRatio != dampingRatio) {
            springDampingRatio = dampingRatio
            if (springEnabled && springDamperEnabled) wake()
        }
    }
    override fun getSpringFrequency(): Double = springFrequency
    override fun getSpringStiffness(): Double = springStiffness
    override fun setSpringFrequency(frequency: Double) {
        if (frequency < 0.0) throw ValueOutOfRangeException("frequency", frequency, ValueOutOfRangeException.MUST_BE_GREATER_THAN_OR_EQUAL_TO, 0.0)
        springMode = Joint.SPRING_MODE_FREQUENCY
        if (springFrequency != frequency) {
            springFrequency = frequency
            if (springEnabled) wake()
        }
    }
    override fun setSpringStiffness(stiffness: Double) {
        if (stiffness < 0.0) throw ValueOutOfRangeException("stiffness", stiffness, ValueOutOfRangeException.MUST_BE_GREATER_THAN_OR_EQUAL_TO, 0.0)
        springMode = Joint.SPRING_MODE_STIFFNESS
        if (springStiffness != stiffness) {
            springStiffness = stiffness
            if (springEnabled) wake()
        }
    }
    override fun getMaximumSpringTorque(): Double = springMaximumTorque
    override fun setMaximumSpringTorque(maximum: Double) {
        if (maximum < 0.0) throw ValueOutOfRangeException("maximum", maximum, ValueOutOfRangeException.MUST_BE_GREATER_THAN_OR_EQUAL_TO, 0.0)
        if (springMaximumTorque != maximum) {
            springMaximumTorque = maximum
            if (springEnabled && springMaximumTorqueEnabled) wake()
        }
    }
    override fun isMaximumSpringTorqueEnabled(): Boolean = springMaximumTorqueEnabled
    override fun setMaximumSpringTorqueEnabled(enabled: Boolean) {
        if (springMaximumTorqueEnabled != enabled) {
            springMaximumTorqueEnabled = enabled
            if (springEnabled) wake()
        }
    }
    override fun isSpringEnabled(): Boolean = springEnabled
    override fun setSpringEnabled(enabled: Boolean) {
        if (springEnabled != enabled) {
            springEnabled = enabled
            wake()
        }
    }
    override fun isSpringDamperEnabled(): Boolean = springDamperEnabled
    override fun setSpringDamperEnabled(enabled: Boolean) {
        if (springDamperEnabled != enabled) {
            springDamperEnabled = enabled
            if (springEnabled) wake()
        }
    }
    override fun getSpringTorque(invdt: Double): Double = springImpulse * invdt
    override fun getSpringMode(): Int = springMode
    override fun isLimitsEnabled(): Boolean = limitsEnabled
    override fun setLimitsEnabled(flag: Boolean) {
        if (limitsEnabled != flag) {
            wake()
            limitsEnabled = flag
            lowerLimitImpulse = 0.0
            upperLimitImpulse = 0.0
        }
    }
    override fun getUpperLimit(): Double = upperLimit
    override fun setUpperLimit(upperLimit: Double) {
        if (this.upperLimit != upperLimit) {
            if (limitsEnabled) wake()
            this.upperLimit = upperLimit
            calculateLimitOffsetAndAdjustedLimits()
            upperLimitImpulse = 0.0
        }
    }
    override fun getLowerLimit(): Double = lowerLimit
    override fun setLowerLimit(lowerLimit: Double) {
        if (this.lowerLimit != lowerLimit) {
            if (limitsEnabled) wake()
            this.lowerLimit = lowerLimit
            calculateLimitOffsetAndAdjustedLimits()
            lowerLimitImpulse = 0.0
        }
    }
    override fun setLimits(lowerLimit: Double, upperLimit: Double) {
        if (this.lowerLimit != lowerLimit || this.upperLimit != upperLimit) {
            if (limitsEnabled) wake()
            this.lowerLimit = lowerLimit
            this.upperLimit = upperLimit
            calculateLimitOffsetAndAdjustedLimits()
            lowerLimitImpulse = 0.0
            upperLimitImpulse = 0.0
        }
    }
    override fun setLimitsEnabled(lowerLimit: Double, upperLimit: Double) {
        setLimitsEnabled(true)
        setLimits(lowerLimit, upperLimit)
    }
    override fun setLimitsEnabled(limit: Double) = setLimitsEnabled(limit, limit)
    override fun setLimits(limit: Double) = setLimits(limit, limit)
    override fun getLimitsReferenceAngle(): Double = referenceAngle
    override fun setLimitsReferenceAngle(angle: Double) {
        if (referenceAngle != angle) {
            referenceAngle = angle
            if (limitsEnabled) wake()
        }
    }
    private fun wake() {
        body1.setAtRest(false)
        body2.setAtRest(false)
    }
}
