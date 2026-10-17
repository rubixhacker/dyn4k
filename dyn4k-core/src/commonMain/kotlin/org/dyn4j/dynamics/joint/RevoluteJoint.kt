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
import org.dyn4j.geometry.Matrix22
import org.dyn4j.geometry.Rotation
import org.dyn4j.geometry.Vector2

open class RevoluteJoint<T : PhysicsBody> : AbstractPairedBodyJoint<T>, AngularLimitsJoint, AngularMotorJoint {
    @kotlin.jvm.JvmField protected val localAnchor1: Vector2
    @kotlin.jvm.JvmField protected val localAnchor2: Vector2
    @kotlin.jvm.JvmField protected var limitsEnabled: Boolean
    @kotlin.jvm.JvmField protected var lowerLimit: Double
    @kotlin.jvm.JvmField protected var upperLimit: Double
    @kotlin.jvm.JvmField protected var referenceAngle: Double
    @kotlin.jvm.JvmField protected var limitOffset: Double
    @kotlin.jvm.JvmField protected var adjustedLowerLimit: Double
    @kotlin.jvm.JvmField protected var adjustedUpperLimit: Double
    @kotlin.jvm.JvmField protected var motorEnabled: Boolean
    @kotlin.jvm.JvmField protected var motorSpeed: Double
    @kotlin.jvm.JvmField protected var motorMaximumTorqueEnabled: Boolean
    @kotlin.jvm.JvmField protected var motorMaximumTorque: Double
    @kotlin.jvm.JvmField internal var angle: Double
    @kotlin.jvm.JvmField internal var axialMass: Double
    @kotlin.jvm.JvmField internal var fixedRotation: Boolean
    @kotlin.jvm.JvmField internal val r1: Vector2
    @kotlin.jvm.JvmField internal val r2: Vector2
    @kotlin.jvm.JvmField internal val K: Matrix22
    @kotlin.jvm.JvmField internal val impulse: Vector2
    @kotlin.jvm.JvmField internal var motorImpulse: Double
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
        motorSpeed = 0.0
        motorMaximumTorque = 1000.0
        motorEnabled = false
        motorMaximumTorqueEnabled = false
        axialMass = 0.0
        fixedRotation = false
        r1 = Vector2()
        r2 = Vector2()
        angle = 0.0
        impulse = Vector2()
        lowerLimitImpulse = 0.0
        upperLimitImpulse = 0.0
        motorImpulse = 0.0
        K = Matrix22()
    }

    protected constructor(joint: RevoluteJoint<T>) : this(joint, null, null)
    protected constructor(joint: RevoluteJoint<T>, body1: T?, body2: T?) : super(joint, body1, body2) {
        localAnchor1 = joint.localAnchor1.copy()
        localAnchor2 = joint.localAnchor2.copy()
        limitsEnabled = joint.limitsEnabled
        lowerLimit = joint.lowerLimit
        upperLimit = joint.upperLimit
        referenceAngle = joint.referenceAngle
        limitOffset = joint.limitOffset
        adjustedLowerLimit = joint.adjustedLowerLimit
        adjustedUpperLimit = joint.adjustedUpperLimit
        motorEnabled = joint.motorEnabled
        motorMaximumTorque = joint.motorMaximumTorque
        motorMaximumTorqueEnabled = joint.motorMaximumTorqueEnabled
        motorSpeed = joint.motorSpeed
        angle = joint.angle
        axialMass = joint.axialMass
        fixedRotation = joint.fixedRotation
        K = joint.K.copy()
        r1 = joint.r1.copy()
        r2 = joint.r2.copy()
        impulse = joint.impulse.copy()
        motorImpulse = joint.motorImpulse
        lowerLimitImpulse = joint.lowerLimitImpulse
        upperLimitImpulse = joint.upperLimitImpulse
    }

    override fun copy(): RevoluteJoint<T> = RevoluteJoint(this)
    override fun copy(body1: T?, body2: T?): RevoluteJoint<T> = RevoluteJoint(this, body1, body2)
    override fun toString(): String = "RevoluteJoint[${super.toString()}|Anchor=${getAnchor1()}|IsMotorEnabled=$motorEnabled|MotorSpeed=$motorSpeed|MaximumMotorTorque=$motorMaximumTorque|IsLimitEnabled=$limitsEnabled|LowerLimit=$lowerLimit|UpperLimit=$upperLimit|ReferenceAngle=$referenceAngle]"

    override fun initializeConstraints(step: TimeStep?, settings: Settings?) {
        val t1 = body1.getTransform()
        val t2 = body2.getTransform()
        val m1 = body1.getMass()
        val m2 = body2.getMass()
        val invM1 = m1.getInverseMass()
        val invM2 = m2.getInverseMass()
        val invI1 = m1.getInverseInertia()
        val invI2 = m2.getInverseInertia()
        t1.getTransformedR(body1.getLocalCenter().to(localAnchor1), r1)
        t2.getTransformedR(body2.getLocalCenter().to(localAnchor2), r2)
        K.m00 = invM1 + invM2 + r1.y * r1.y * invI1 + r2.y * r2.y * invI2
        K.m01 = -r1.y * r1.x * invI1 - r2.y * r2.x * invI2
        K.m10 = K.m01
        K.m11 = invM1 + invM2 + r1.x * r1.x * invI1 + r2.x * r2.x * invI2
        axialMass = invI1 + invI2
        if (axialMass > Epsilon.E) {
            axialMass = 1.0 / axialMass
            fixedRotation = false
        } else {
            axialMass = 0.0
            fixedRotation = true
        }
        if (!motorEnabled) motorImpulse = 0.0
        angle = getRelativeRotation()
        if (!limitsEnabled || fixedRotation) {
            lowerLimitImpulse = 0.0
            upperLimitImpulse = 0.0
        }
        if (!motorEnabled || fixedRotation) motorImpulse = 0.0
        if (settings!!.isWarmStartingEnabled()) {
            val dtr = step!!.getDeltaTimeRatio()
            impulse.multiply(dtr)
            motorImpulse *= dtr
            lowerLimitImpulse *= dtr
            upperLimitImpulse *= dtr
            val axialImpulse = motorImpulse + lowerLimitImpulse - upperLimitImpulse
            val applied = Vector2(impulse.x, impulse.y)
            body1.getLinearVelocity().subtract(applied.product(invM1))
            body1.setAngularVelocity(body1.getAngularVelocity() - invI1 * (r1.cross(applied) + axialImpulse))
            body2.getLinearVelocity().add(applied.product(invM2))
            body2.setAngularVelocity(body2.getAngularVelocity() + invI2 * (r2.cross(applied) + axialImpulse))
        } else {
            impulse.zero()
            motorImpulse = 0.0
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
        if (motorEnabled && !fixedRotation) {
            val c = body2.getAngularVelocity() - body1.getAngularVelocity() - motorSpeed
            var applied = axialMass * -c
            if (motorMaximumTorqueEnabled) {
                val old = motorImpulse
                val maxImpulse = motorMaximumTorque * step!!.getDeltaTime()
                motorImpulse = Interval.clamp(motorImpulse + applied, -maxImpulse, maxImpulse)
                applied = motorImpulse - old
            } else {
                motorImpulse += applied
            }
            body1.setAngularVelocity(body1.getAngularVelocity() - invI1 * applied)
            body2.setAngularVelocity(body2.getAngularVelocity() + invI2 * applied)
        }
        if (limitsEnabled && !fixedRotation) {
            val cLower = angle - adjustedLowerLimit
            val cdotLower = body2.getAngularVelocity() - body1.getAngularVelocity()
            var applied = -axialMass * (cdotLower + max(cLower, 0.0) * step!!.getInverseDeltaTime())
            val oldLower = lowerLimitImpulse
            lowerLimitImpulse = max(lowerLimitImpulse + applied, 0.0)
            applied = lowerLimitImpulse - oldLower
            body1.setAngularVelocity(body1.getAngularVelocity() - invI1 * applied)
            body2.setAngularVelocity(body2.getAngularVelocity() + invI2 * applied)

            val cUpper = adjustedUpperLimit - angle
            val cdotUpper = body1.getAngularVelocity() - body2.getAngularVelocity()
            applied = -axialMass * (cdotUpper + max(cUpper, 0.0) * step.getInverseDeltaTime())
            val oldUpper = upperLimitImpulse
            upperLimitImpulse = max(upperLimitImpulse + applied, 0.0)
            applied = upperLimitImpulse - oldUpper
            body1.setAngularVelocity(body1.getAngularVelocity() + invI1 * applied)
            body2.setAngularVelocity(body2.getAngularVelocity() - invI2 * applied)
        }
        val v1 = body1.getLinearVelocity().sum(r1.cross(body1.getAngularVelocity()))
        val v2 = body2.getLinearVelocity().sum(r2.cross(body2.getAngularVelocity()))
        val jvb = v2.subtract(v1)
        val applied = K.solve(jvb.negate())
        impulse.x += applied.x
        impulse.y += applied.y
        body1.getLinearVelocity().subtract(applied.product(invM1))
        body1.setAngularVelocity(body1.getAngularVelocity() - invI1 * r1.cross(applied))
        body2.getLinearVelocity().add(applied.product(invM2))
        body2.setAngularVelocity(body2.getAngularVelocity() + invI2 * r2.cross(applied))
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
        var angularError = 0.0
        if (limitsEnabled && !fixedRotation) {
            val angle = getRelativeRotation()
            val c = if (abs(adjustedUpperLimit - adjustedLowerLimit) < 2.0 * angularTolerance) {
                Interval.clamp(angle - adjustedLowerLimit, -maxAngularCorrection, maxAngularCorrection)
            } else if (angle <= adjustedLowerLimit) {
                Interval.clamp(angle - adjustedLowerLimit + angularTolerance, -maxAngularCorrection, 0.0)
            } else if (angle >= adjustedUpperLimit) {
                Interval.clamp(angle - adjustedUpperLimit - angularTolerance, 0.0, maxAngularCorrection)
            } else 0.0
            val applied = -axialMass * c
            body1.rotateAboutCenter(-invI1 * applied)
            body2.rotateAboutCenter(invI2 * applied)
            angularError = abs(c)
        }
        val r1 = t1.getTransformedR(body1.getLocalCenter().to(localAnchor1))
        val r2 = t2.getTransformedR(body2.getLocalCenter().to(localAnchor2))
        val p1 = body1.getWorldCenter().add(r1)
        val p2 = body2.getWorldCenter().add(r2)
        val p = p2.difference(p1)
        val linearError = p.getMagnitude()
        val k = Matrix22()
        k.m00 = invM1 + invM2 + r1.y * r1.y * invI1 + r2.y * r2.y * invI2
        k.m01 = -invI1 * r1.x * r1.y - invI2 * r2.x * r2.y
        k.m10 = K.m01
        k.m11 = invM1 + invM2 + r1.x * r1.x * invI1 + r2.x * r2.x * invI2
        val applied = k.solve(p.negate())
        body1.translate(applied.product(-invM1))
        body1.rotateAboutCenter(-invI1 * r1.cross(applied))
        body2.translate(applied.product(invM2))
        body2.rotateAboutCenter(invI2 * r2.cross(applied))
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

    open fun getAnchor1(): Vector2 = body1.getWorldPoint(localAnchor1)
    open fun getAnchor2(): Vector2 = body2.getWorldPoint(localAnchor2)
    override fun getReactionForce(invdt: Double): Vector2 = Vector2(impulse.x * invdt, impulse.y * invdt)
    override fun getReactionTorque(invdt: Double): Double = (motorImpulse + lowerLimitImpulse - upperLimitImpulse) * invdt
    override fun shift(shift: Vector2) {}
    open fun getAngularSpeed(): Double = body2.getAngularVelocity() - body1.getAngularVelocity()
    open fun getAngularTranslation(): Double = Rotation.getNormalizedAngle(
        body2.getTransform().getRotationAngle() - body1.getTransform().getRotationAngle() - referenceAngle
    )
    override fun isMotorEnabled(): Boolean = motorEnabled
    override fun setMotorEnabled(motorEnabled: Boolean) {
        if (this.motorEnabled != motorEnabled) { wake(); this.motorEnabled = motorEnabled }
    }
    override fun getMaximumMotorTorque(): Double = motorMaximumTorque
    override fun setMaximumMotorTorque(maximumMotorTorque: Double) {
        if (maximumMotorTorque < 0.0) throw ValueOutOfRangeException("maximumMotorTorque", maximumMotorTorque, ValueOutOfRangeException.MUST_BE_GREATER_THAN_OR_EQUAL_TO, 0.0)
        if (motorMaximumTorque != maximumMotorTorque) {
            if (motorEnabled) wake()
            motorMaximumTorque = maximumMotorTorque
        }
    }
    override fun setMaximumMotorTorqueEnabled(enabled: Boolean) {
        if (motorMaximumTorqueEnabled != enabled) {
            motorMaximumTorqueEnabled = enabled
            if (motorEnabled) wake()
        }
    }
    override fun isMaximumMotorTorqueEnabled(): Boolean = motorMaximumTorqueEnabled
    override fun getMotorSpeed(): Double = motorSpeed
    override fun setMotorSpeed(motorSpeed: Double) {
        if (this.motorSpeed != motorSpeed) {
            if (motorEnabled) wake()
            this.motorSpeed = motorSpeed
            motorImpulse = 0.0
            lowerLimitImpulse = 0.0
            upperLimitImpulse = 0.0
        }
    }
    override fun getMotorTorque(invdt: Double): Double = motorImpulse * invdt
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
