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
import kotlin.math.sign
import org.dyn4j.Epsilon
import org.dyn4j.dynamics.PhysicsBody
import org.dyn4j.dynamics.Settings
import org.dyn4j.dynamics.TimeStep
import org.dyn4j.exception.ValueOutOfRangeException
import org.dyn4j.geometry.Interval
import org.dyn4j.geometry.Rotation
import org.dyn4j.geometry.Vector2

open class AngleJoint<T : PhysicsBody> : AbstractPairedBodyJoint<T>, AngularLimitsJoint {
    @kotlin.jvm.JvmField protected var ratio = 1.0
    @kotlin.jvm.JvmField protected var limitsEnabled = true
    @kotlin.jvm.JvmField protected var lowerLimit: Double
    @kotlin.jvm.JvmField protected var upperLimit: Double
    @kotlin.jvm.JvmField protected var referenceAngle: Double
    @kotlin.jvm.JvmField internal var limitOffset = 0.0
    @kotlin.jvm.JvmField internal var adjustedLowerLimit = 0.0
    @kotlin.jvm.JvmField internal var adjustedUpperLimit = 0.0
    @kotlin.jvm.JvmField internal var angle = 0.0
    @kotlin.jvm.JvmField internal var axialMass = 0.0
    @kotlin.jvm.JvmField internal var fixedRotation = false
    @kotlin.jvm.JvmField internal var impulse = 0.0
    @kotlin.jvm.JvmField internal var lowerLimitImpulse = 0.0
    @kotlin.jvm.JvmField internal var upperLimitImpulse = 0.0

    constructor(body1: T, body2: T) : super(body1, body2) {
        referenceAngle = body2.getTransform().getRotationAngle() - body1.getTransform().getRotationAngle()
        lowerLimit = Rotation.getNormalizedAngle(referenceAngle)
        upperLimit = lowerLimit
        calculateLimitOffsetAndAdjustedLimits()
    }

    protected constructor(joint: AngleJoint<T>) : this(joint, null, null)

    protected constructor(joint: AngleJoint<T>, body1: T?, body2: T?) : super(joint, body1, body2) {
        ratio = joint.ratio
        limitsEnabled = joint.limitsEnabled
        lowerLimit = joint.lowerLimit
        upperLimit = joint.upperLimit
        referenceAngle = joint.referenceAngle
        limitOffset = joint.limitOffset
        adjustedLowerLimit = joint.adjustedLowerLimit
        adjustedUpperLimit = joint.adjustedUpperLimit
        angle = joint.angle
        axialMass = joint.axialMass
        fixedRotation = joint.fixedRotation
        impulse = joint.impulse
        lowerLimitImpulse = joint.lowerLimitImpulse
        upperLimitImpulse = joint.upperLimitImpulse
    }

    override fun copy() = AngleJoint(this)
    override fun copy(body1: T?, body2: T?) = AngleJoint(this, body1, body2)

    override fun toString() = "AngleJoint[${super.toString()}|Ratio=$ratio|LowerLimit=$lowerLimit|UpperLimit=$upperLimit|IsLimitEnabled=$limitsEnabled|ReferenceAngle=$referenceAngle]"

    override fun initializeConstraints(step: TimeStep?, settings: Settings?) {
        val s = step!!
        val cfg = settings!!
        val invI1 = body1.getMass().getInverseInertia()
        val invI2 = body2.getMass().getInverseInertia()
        axialMass = invI1 + abs(ratio) * invI2
        if (axialMass > Epsilon.E) axialMass = 1.0 / axialMass else {
            axialMass = 0.0
            fixedRotation = true
        }
        angle = getRelativeRotation()
        if (!limitsEnabled || fixedRotation) {
            lowerLimitImpulse = 0.0
            upperLimitImpulse = 0.0
        }
        if (limitsEnabled || ratio == 1.0) impulse = 0.0
        if (cfg.isWarmStartingEnabled()) {
            val dtr = s.getDeltaTimeRatio()
            impulse *= dtr
            lowerLimitImpulse *= dtr
            upperLimitImpulse *= dtr
            val axialImpulse = impulse * sign(ratio) + lowerLimitImpulse - upperLimitImpulse
            body1.setAngularVelocity(body1.getAngularVelocity() - invI1 * axialImpulse)
            body2.setAngularVelocity(body2.getAngularVelocity() + invI2 * axialImpulse)
        } else {
            impulse = 0.0
            lowerLimitImpulse = 0.0
            upperLimitImpulse = 0.0
        }
    }

    override fun solveVelocityConstraints(step: TimeStep?, settings: Settings?) {
        val invI1 = body1.getMass().getInverseInertia()
        val invI2 = body2.getMass().getInverseInertia()
        if (limitsEnabled && !fixedRotation) {
            val lowerC = angle - adjustedLowerLimit
            val lowerCdot = body2.getAngularVelocity() - body1.getAngularVelocity()
            var stepImpulse = -axialMass * (lowerCdot + max(lowerC, 0.0) * step!!.getInverseDeltaTime())
            val oldLowerImpulse = lowerLimitImpulse
            lowerLimitImpulse = max(lowerLimitImpulse + stepImpulse, 0.0)
            stepImpulse = lowerLimitImpulse - oldLowerImpulse
            body1.setAngularVelocity(body1.getAngularVelocity() - invI1 * stepImpulse)
            body2.setAngularVelocity(body2.getAngularVelocity() + invI2 * stepImpulse)

            val upperC = adjustedUpperLimit - angle
            val upperCdot = body1.getAngularVelocity() - body2.getAngularVelocity()
            stepImpulse = -axialMass * (upperCdot + max(upperC, 0.0) * step.getInverseDeltaTime())
            val oldUpperImpulse = upperLimitImpulse
            upperLimitImpulse = max(upperLimitImpulse + stepImpulse, 0.0)
            stepImpulse = upperLimitImpulse - oldUpperImpulse
            body1.setAngularVelocity(body1.getAngularVelocity() + invI1 * stepImpulse)
            body2.setAngularVelocity(body2.getAngularVelocity() - invI2 * stepImpulse)
        }
        if (!limitsEnabled) {
            val c = body2.getAngularVelocity() - ratio * body1.getAngularVelocity()
            val stepImpulse = -axialMass * c
            impulse += stepImpulse
            body1.setAngularVelocity(body1.getAngularVelocity() - invI1 * stepImpulse)
            body2.setAngularVelocity(body2.getAngularVelocity() + invI2 * stepImpulse * sign(ratio))
        }
    }

    override fun solvePositionConstraints(step: TimeStep?, settings: Settings?): Boolean {
        if (limitsEnabled && !fixedRotation) {
            val cfg = settings!!
            val tolerance = cfg.getAngularTolerance()
            val maxCorrection = cfg.getMaximumAngularCorrection()
            val invI1 = body1.getMass().getInverseInertia()
            val invI2 = body2.getMass().getInverseInertia()
            val a = getRelativeRotation()
            val c = if (abs(adjustedUpperLimit - adjustedLowerLimit) < 2.0 * tolerance) {
                Interval.clamp(a - adjustedLowerLimit, -maxCorrection, maxCorrection)
            } else if (a <= adjustedLowerLimit) {
                Interval.clamp(a - adjustedLowerLimit + tolerance, -maxCorrection, 0.0)
            } else if (a >= adjustedUpperLimit) {
                Interval.clamp(a - adjustedUpperLimit - tolerance, 0.0, maxCorrection)
            } else 0.0
            val p = -axialMass * c
            body1.rotateAboutCenter(-invI1 * p)
            body2.rotateAboutCenter(invI2 * p)
            return abs(c) <= tolerance
        }
        return true
    }

    private fun calculateLimitOffsetAndAdjustedLimits() {
        val lower = Rotation.getNormalizedAngle(lowerLimit)
        val upper = Rotation.getNormalizedAngle(upperLimit)
        val sameSign = (lower > 0.0) == (upper > 0.0)
        val lowerGreater = lower > upper
        val average = (lower + upper) * 0.5
        var difference = lower - upper
        if (sameSign && lowerGreater) {
            if (lower > 0.0) difference *= -1.0
            limitOffset = average + difference
            adjustedLowerLimit = lower - average - PI
            adjustedUpperLimit = upper - average + PI
        } else if (lowerGreater) {
            limitOffset = PI
            adjustedLowerLimit = upper
            adjustedUpperLimit = lower
        } else {
            limitOffset = 0.0
            adjustedLowerLimit = lower
            adjustedUpperLimit = upper
        }
    }

    private fun getRelativeRotation(): Double {
        val a1 = body1.getTransform().getRotationAngle()
        val a2 = body2.getTransform().getRotationAngle()
        return Rotation.getNormalizedAngle(a2 - a1 - referenceAngle - limitOffset)
    }

    override fun getReactionForce(invdt: Double) = Vector2()
    override fun getReactionTorque(invdt: Double) = (impulse + lowerLimitImpulse - upperLimit) * invdt
    override fun shift(shift: Vector2) {}

    @Deprecated("Use getAngularTranslation")
    open fun getJointAngle() = getAngularTranslation()
    open fun getAngularTranslation(): Double {
        val a1 = body1.getTransform().getRotationAngle()
        val a2 = body2.getTransform().getRotationAngle()
        return Rotation.getNormalizedAngle(a2 - a1 - referenceAngle)
    }
    open fun getRatio() = ratio
    open fun setRatio(ratio: Double) {
        if (ratio == 0.0) throw ValueOutOfRangeException("ratio", 0.0)
        this.ratio = ratio
    }

    override fun isLimitsEnabled() = limitsEnabled
    override fun setLimitsEnabled(flag: Boolean) {
        if (limitsEnabled != flag) {
            body1.setAtRest(false)
            body2.setAtRest(false)
            limitsEnabled = flag
            lowerLimitImpulse = 0.0
            upperLimitImpulse = 0.0
        }
    }
    override fun getUpperLimit() = upperLimit
    override fun setUpperLimit(upperLimit: Double) {
        if (this.upperLimit != upperLimit) {
            if (limitsEnabled) wakeBodies()
            this.upperLimit = upperLimit
            calculateLimitOffsetAndAdjustedLimits()
            upperLimitImpulse = 0.0
        }
    }
    override fun getLowerLimit() = lowerLimit
    override fun setLowerLimit(lowerLimit: Double) {
        if (this.lowerLimit != lowerLimit) {
            if (limitsEnabled) wakeBodies()
            this.lowerLimit = lowerLimit
            calculateLimitOffsetAndAdjustedLimits()
            lowerLimitImpulse = 0.0
        }
    }
    override fun setLimits(lowerLimit: Double, upperLimit: Double) {
        if (this.lowerLimit != lowerLimit || this.upperLimit != upperLimit) {
            if (limitsEnabled) wakeBodies()
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
    override fun getLimitsReferenceAngle() = referenceAngle
    override fun setLimitsReferenceAngle(angle: Double) {
        if (referenceAngle != angle) {
            referenceAngle = angle
            if (limitsEnabled) wakeBodies()
        }
    }
    private fun wakeBodies() {
        body1.setAtRest(false)
        body2.setAtRest(false)
    }
}
