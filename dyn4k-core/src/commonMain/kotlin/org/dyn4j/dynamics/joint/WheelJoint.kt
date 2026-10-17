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
package org.dyn4j.dynamics.joint

import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min
import org.dyn4j.Epsilon
import org.dyn4j.JvmFieldBridge
import org.dyn4j.dynamics.PhysicsBody
import org.dyn4j.dynamics.Settings
import org.dyn4j.dynamics.TimeStep
import org.dyn4j.exception.ArgumentNullException
import org.dyn4j.exception.ValueOutOfRangeException
import org.dyn4j.geometry.Interval
import org.dyn4j.geometry.Vector2

open class WheelJoint<T : PhysicsBody> : AbstractPairedBodyJoint<T>, LinearLimitsJoint,
    LinearSpringJoint, AngularMotorJoint {
    @JvmFieldBridge protected val localAnchor1: Vector2
    @JvmFieldBridge protected val localAnchor2: Vector2
    @JvmFieldBridge protected val xAxis: Vector2
    @JvmFieldBridge protected val yAxis: Vector2
    @set:kotlin.jvm.JvmName("setUpperLimitEnabledField")
    @JvmFieldBridge protected var upperLimitEnabled = false
    @set:kotlin.jvm.JvmName("setLowerLimitEnabledField")
    @JvmFieldBridge protected var lowerLimitEnabled = false
    @get:kotlin.jvm.JvmName("getUpperLimitField")
    @set:kotlin.jvm.JvmName("setUpperLimitField")
    @JvmFieldBridge protected var upperLimit = 0.0
    @get:kotlin.jvm.JvmName("getLowerLimitField")
    @set:kotlin.jvm.JvmName("setLowerLimitField")
    @JvmFieldBridge protected var lowerLimit = 0.0
    @set:kotlin.jvm.JvmName("setMotorEnabledField")
    @JvmFieldBridge protected var motorEnabled = false
    @get:kotlin.jvm.JvmName("getMotorSpeedField")
    @set:kotlin.jvm.JvmName("setMotorSpeedField")
    @JvmFieldBridge protected var motorSpeed = 0.0
    @JvmFieldBridge protected var motorMaximumTorqueEnabled = false
    @JvmFieldBridge protected var motorMaximumTorque = 1000.0
    @set:kotlin.jvm.JvmName("setSpringEnabledField")
    @JvmFieldBridge protected var springEnabled = true
    @set:kotlin.jvm.JvmName("setSpringDamperEnabledField")
    @JvmFieldBridge protected var springDamperEnabled = true
    @get:kotlin.jvm.JvmName("getSpringModeField")
    @JvmFieldBridge protected var springMode = Joint.SPRING_MODE_FREQUENCY
    @get:kotlin.jvm.JvmName("getSpringFrequencyField")
    @set:kotlin.jvm.JvmName("setSpringFrequencyField")
    @JvmFieldBridge protected var springFrequency = 8.0
    @get:kotlin.jvm.JvmName("getSpringStiffnessField")
    @set:kotlin.jvm.JvmName("setSpringStiffnessField")
    @JvmFieldBridge protected var springStiffness = 0.0
    @get:kotlin.jvm.JvmName("getSpringDampingRatioField")
    @set:kotlin.jvm.JvmName("setSpringDampingRatioField")
    @JvmFieldBridge protected var springDampingRatio = 0.3
    @JvmFieldBridge protected var springMaximumForceEnabled = false
    @JvmFieldBridge protected var springMaximumForce = 1000.0
    @get:kotlin.jvm.JvmName("getSpringRestOffsetField")
    @set:kotlin.jvm.JvmName("setSpringRestOffsetField")
    @JvmFieldBridge protected var springRestOffset = 0.0

    @JvmFieldBridge internal var damping = 0.0
    @JvmFieldBridge internal var bias = 0.0
    @JvmFieldBridge internal var gamma = 0.0
    @JvmFieldBridge internal var translation = 0.0
    @JvmFieldBridge internal var invK = 0.0
    @JvmFieldBridge internal var axialMass = 0.0
    @JvmFieldBridge internal var springMass = 0.0
    @JvmFieldBridge internal var motorMass = 0.0
    @JvmFieldBridge internal val wyAxis: Vector2
    @JvmFieldBridge internal val wxAxis: Vector2
    @JvmFieldBridge internal var s1y = 0.0
    @JvmFieldBridge internal var s2y = 0.0
    @JvmFieldBridge internal var s1x = 0.0
    @JvmFieldBridge internal var s2x = 0.0
    @JvmFieldBridge internal var impulse = 0.0
    @JvmFieldBridge internal var lowerLimitImpulse = 0.0
    @JvmFieldBridge internal var upperLimitImpulse = 0.0
    @JvmFieldBridge internal var springImpulse = 0.0
    @JvmFieldBridge internal var motorImpulse = 0.0

    constructor(frame: T?, wheel: T?, anchor: Vector2?, axis: Vector2?) : super(frame, wheel) {
        val point = anchor ?: throw ArgumentNullException("anchor")
        val direction = axis ?: throw ArgumentNullException("axis")
        if (direction.getMagnitude() <= Epsilon.E) throw IllegalArgumentException("The axis cannot be a zero vector.")
        localAnchor1 = body1.getLocalPoint(point)
        localAnchor2 = body2.getLocalPoint(point)
        xAxis = body1.getLocalVector(direction.getNormalized())
        yAxis = xAxis.getRightHandOrthogonalVector()
        wyAxis = Vector2()
        wxAxis = Vector2()
    }

    protected constructor(joint: WheelJoint<T>) : this(joint, null, null)

    protected constructor(joint: WheelJoint<T>, frame: T?, wheel: T?) : super(joint, frame, wheel) {
        localAnchor1 = joint.localAnchor1.copy()
        localAnchor2 = joint.localAnchor2.copy()
        xAxis = joint.xAxis.copy()
        yAxis = joint.yAxis.copy()
        upperLimitEnabled = joint.upperLimitEnabled
        lowerLimitEnabled = joint.lowerLimitEnabled
        upperLimit = joint.upperLimit
        lowerLimit = joint.lowerLimit
        motorEnabled = joint.motorEnabled
        motorSpeed = joint.motorSpeed
        motorMaximumTorqueEnabled = joint.motorMaximumTorqueEnabled
        motorMaximumTorque = joint.motorMaximumTorque
        springEnabled = joint.springEnabled
        springDamperEnabled = joint.springDamperEnabled
        springMode = joint.springMode
        springFrequency = joint.springFrequency
        springStiffness = joint.springStiffness
        springDampingRatio = joint.springDampingRatio
        springMaximumForceEnabled = joint.springMaximumForceEnabled
        springMaximumForce = joint.springMaximumForce
        springRestOffset = joint.springRestOffset
        damping = joint.damping
        bias = joint.bias
        gamma = joint.gamma
        translation = joint.translation
        invK = joint.invK
        axialMass = joint.axialMass
        springMass = joint.springMass
        motorMass = joint.motorMass
        wyAxis = joint.wyAxis.copy()
        wxAxis = joint.wxAxis.copy()
        s1y = joint.s1y
        s2y = joint.s2y
        s1x = joint.s1x
        s2x = joint.s2x
        impulse = joint.impulse
        lowerLimitImpulse = joint.lowerLimitImpulse
        upperLimitImpulse = joint.upperLimitImpulse
        springImpulse = joint.springImpulse
        motorImpulse = joint.motorImpulse
    }

    override fun copy(): WheelJoint<T> = WheelJoint(this)
    override fun copy(body1: T?, body2: T?): WheelJoint<T> = WheelJoint(this, body1, body2)

    override fun toString() = "WheelJoint[${super.toString()}|WorldAnchor=${getAnchor1()}|Axis=${getAxis()}" +
        "|IsMotorEnabled=$motorEnabled|MotorSpeed=$motorSpeed|MaximumMotorTorque=$motorMaximumTorque" +
        "|Frequency=$springFrequency|DampingRatio=$springDampingRatio]"

    override fun initializeConstraints(step: TimeStep?, settings: Settings?) {
        val h = step!!
        val config = settings!!
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
        val d = body2.getWorldCenter().sum(r2).subtract(body1.getWorldCenter().sum(r1))
        body1.getWorldVector(xAxis, wxAxis)
        body1.getWorldVector(yAxis, wyAxis)
        s1y = r1.sum(d).cross(wyAxis)
        s2y = r2.cross(wyAxis)
        invK = invM1 + invM2 + s1y * s1y * invI1 + s2y * s2y * invI2
        invK = if (invK > Epsilon.E) 1.0 / invK else 0.0
        s1x = r1.sum(d).cross(wxAxis)
        s2x = r2.cross(wxAxis)
        val invMass = invM1 + invM2 + s1x * s1x * invI1 + s2x * s2x * invI2
        axialMass = if (invMass > Epsilon.E) 1.0 / invMass else 0.0
        if (springEnabled && invMass > 0.0) {
            updateSpringCoefficients()
            springMass = axialMass
            val c = d.dot(wxAxis) + springRestOffset
            val dt = h.getDeltaTime()
            gamma = getConstraintImpulseMixing(dt, springStiffness, damping)
            val erp = getErrorReductionParameter(dt, springStiffness, damping)
            bias = c * erp
            springMass = invMass + gamma
            if (springMass > Epsilon.E) springMass = 1.0 / springMass
        } else {
            springMass = 0.0
            springImpulse = 0.0
            gamma = 0.0
            bias = 0.0
            damping = 0.0
        }
        if (lowerLimitEnabled || upperLimitEnabled) translation = wxAxis.dot(d)
        if (!lowerLimitEnabled) lowerLimitImpulse = 0.0
        if (!upperLimitEnabled) upperLimitImpulse = 0.0
        if (motorEnabled) {
            motorMass = invI1 + invI2
            if (motorMass > Epsilon.E) motorMass = 1.0 / motorMass
        } else {
            motorMass = 0.0
            motorImpulse = 0.0
        }
        if (config.isWarmStartingEnabled()) {
            val ratio = h.getDeltaTimeRatio()
            impulse *= ratio
            springImpulse *= ratio
            motorImpulse *= ratio
            val axialImpulse = springImpulse + lowerLimitImpulse - upperLimitImpulse
            val p = Vector2(wyAxis.x * impulse + axialImpulse * wxAxis.x,
                wyAxis.y * impulse + axialImpulse * wxAxis.y)
            val l1 = impulse * s1y + axialImpulse * s1x + motorImpulse
            val l2 = impulse * s2y + axialImpulse * s2x + motorImpulse
            body1.getLinearVelocity().subtract(p.product(invM1))
            body1.setAngularVelocity(body1.getAngularVelocity() - invI1 * l1)
            body2.getLinearVelocity().add(p.product(invM2))
            body2.setAngularVelocity(body2.getAngularVelocity() + invI2 * l2)
        } else {
            impulse = 0.0
            lowerLimitImpulse = 0.0
            upperLimitImpulse = 0.0
            motorImpulse = 0.0
            springImpulse = 0.0
        }
    }

    override fun solveVelocityConstraints(step: TimeStep?, settings: Settings?) {
        val h = step!!
        val m1 = body1.getMass()
        val m2 = body2.getMass()
        val invM1 = m1.getInverseMass()
        val invM2 = m2.getInverseMass()
        val invI1 = m1.getInverseInertia()
        val invI2 = m2.getInverseInertia()
        val v1 = body1.getLinearVelocity()
        val v2 = body2.getLinearVelocity()
        var w1 = body1.getAngularVelocity()
        var w2 = body2.getAngularVelocity()
        if (springEnabled) {
            val cdt = wxAxis.dot(v2.difference(v1)) + s2x * w2 - s1x * w1
            var amount = -springMass * (cdt + bias + gamma * springImpulse)
            if (springMaximumForceEnabled) {
                val previous = springImpulse
                val cap = h.getDeltaTime() * springMaximumForce
                springImpulse = Interval.clamp(springImpulse + amount, -cap, cap)
                amount = springImpulse - previous
            } else springImpulse += amount
            val p = wxAxis.product(amount)
            v1.subtract(p.product(invM1))
            w1 -= amount * s1x * invI1
            v2.add(p.product(invM2))
            w2 += amount * s2x * invI2
        }
        if (motorEnabled) {
            val cdt = w2 - w1 - motorSpeed
            var amount = -motorMass * cdt
            if (motorMaximumTorqueEnabled) {
                val previous = motorImpulse
                val cap = motorMaximumTorque * h.getDeltaTime()
                motorImpulse = Interval.clamp(motorImpulse + amount, -cap, cap)
                amount = motorImpulse - previous
            } else motorImpulse += amount
            w1 -= amount * invI1
            w2 += amount * invI2
        }
        if (lowerLimitEnabled) {
            val c = translation - lowerLimit
            val cdt = wxAxis.dot(v2.difference(v1)) + s2x * w2 - s1x * w1
            var amount = -axialMass * (cdt + max(c, 0.0) * h.getInverseDeltaTime())
            val previous = lowerLimitImpulse
            lowerLimitImpulse = max(lowerLimitImpulse + amount, 0.0)
            amount = lowerLimitImpulse - previous
            val p = wxAxis.product(amount)
            v1.subtract(p.product(invM1))
            w1 -= amount * s1x * invI1
            v2.add(p.product(invM2))
            w2 += amount * s2x * invI2
        }
        if (upperLimitEnabled) {
            val c = upperLimit - translation
            val cdt = wxAxis.dot(v1.difference(v2)) + s1x * w1 - s2x * w2
            var amount = -axialMass * (cdt + max(c, 0.0) * h.getInverseDeltaTime())
            val previous = upperLimitImpulse
            upperLimitImpulse = max(upperLimitImpulse + amount, 0.0)
            amount = upperLimitImpulse - previous
            val p = wxAxis.product(amount)
            v1.add(p.product(invM1))
            w1 += amount * s1x * invI1
            v2.subtract(p.product(invM2))
            w2 -= amount * s2x * invI2
        }
        val cdt = wyAxis.dot(v2.difference(v1)) + s2y * w2 - s1y * w1
        val amount = -invK * cdt
        impulse += amount
        val p = wyAxis.product(amount)
        v1.subtract(p.product(invM1))
        w1 -= amount * s1y * invI1
        v2.add(p.product(invM2))
        w2 += amount * s2y * invI2
        body1.setAngularVelocity(w1)
        body2.setAngularVelocity(w2)
    }

    override fun solvePositionConstraints(step: TimeStep?, settings: Settings?): Boolean {
        val linearTolerance = settings!!.getLinearTolerance()
        val t1 = body1.getTransform()
        val t2 = body2.getTransform()
        val m1 = body1.getMass()
        val m2 = body2.getMass()
        val invM1 = m1.getInverseMass()
        val invM2 = m2.getInverseMass()
        val invI1 = m1.getInverseInertia()
        val invI2 = m2.getInverseInertia()
        var linearError = 0.0
        if (lowerLimitEnabled || upperLimitEnabled) {
            val c1 = body1.getWorldCenter()
            val c2 = body2.getWorldCenter()
            val r1 = t1.getTransformedR(body1.getLocalCenter().to(localAnchor1))
            val r2 = t2.getTransformedR(body2.getLocalCenter().to(localAnchor2))
            val d = c2.sum(r2).subtract(c1.sum(r1))
            val worldAxis = body1.getWorldVector(xAxis)
            val ax1 = r1.sum(d).cross(worldAxis)
            val ax2 = r2.cross(worldAxis)
            var c = 0.0
            val position = worldAxis.dot(d)
            if (upperLimitEnabled && lowerLimitEnabled && abs(upperLimit - lowerLimit) < 2.0 * linearTolerance) {
                c = position
            } else if (lowerLimitEnabled && position <= lowerLimit) {
                c = min(position - lowerLimit, 0.0)
            } else if (upperLimitEnabled && position >= upperLimit) {
                c = max(position - upperLimit, 0.0)
            }
            if (c != 0.0) {
                val invMass = invM1 + invM2 + ax1 * ax1 * invI1 + ax2 * ax2 * invI2
                val amount = if (invMass > Epsilon.E) -c / invMass else 0.0
                val p = worldAxis.product(amount)
                body1.translate(p.product(-invM1))
                body1.rotateAboutCenter(-amount * ax1 * invI1)
                body2.translate(p.product(invM2))
                body2.rotateAboutCenter(amount * ax2 * invI2)
                linearError = abs(c)
            }
        }
        val c1 = body1.getWorldCenter()
        val c2 = body2.getWorldCenter()
        val r1 = t1.getTransformedR(body1.getLocalCenter().to(localAnchor1))
        val r2 = t2.getTransformedR(body2.getLocalCenter().to(localAnchor2))
        val d = c2.sum(r2).subtract(c1.sum(r1))
        val ay = body1.getWorldVector(yAxis)
        val sy1 = r1.sum(d).cross(ay)
        val sy2 = r2.cross(ay)
        val cx = ay.dot(d)
        val invMass = invM1 + invM2 + sy1 * sy1 * invI1 + sy2 * sy2 * invI2
        val amount = if (invMass > Epsilon.E) -cx / invMass else 0.0
        val p = Vector2(ay.x * amount, ay.y * amount)
        body1.translate(p.product(-invM1))
        body1.rotateAboutCenter(-sy1 * amount * invI1)
        body2.translate(p.product(invM2))
        body2.rotateAboutCenter(sy2 * amount * invI2)
        linearError = max(linearError, abs(cx))
        return linearError <= linearTolerance
    }

    protected open fun updateSpringCoefficients() {
        val reducedMass = getReducedMass()
        var naturalFrequency = 0.0
        if (springMode == Joint.SPRING_MODE_FREQUENCY) {
            naturalFrequency = getNaturalFrequency(springFrequency)
            springStiffness = getSpringStiffness(reducedMass, naturalFrequency)
        } else if (springMode == Joint.SPRING_MODE_STIFFNESS) {
            naturalFrequency = getNaturalFrequency(springStiffness, reducedMass)
            springFrequency = getFrequency(naturalFrequency)
        }
        damping = if (springDamperEnabled)
            getSpringDampingCoefficient(reducedMass, naturalFrequency, springDampingRatio) else 0.0
    }

    open fun getAnchor1(): Vector2 = body1.getWorldPoint(localAnchor1)
    open fun getAnchor2(): Vector2 = body2.getWorldPoint(localAnchor2)
    override fun getReactionForce(invdt: Double): Vector2 {
        val axialImpulse = springImpulse + lowerLimitImpulse - upperLimitImpulse
        return Vector2(impulse * wyAxis.x + axialImpulse * wxAxis.x,
            impulse * wyAxis.y + axialImpulse * wxAxis.y).multiply(invdt)
    }
    override fun getReactionTorque(invdt: Double): Double = motorImpulse * invdt
    override fun shift(shift: Vector2) {}

    open fun getLinearSpeed(): Double {
        val t1 = body1.getTransform()
        val t2 = body2.getTransform()
        val r1 = t1.getTransformedR(body1.getLocalCenter().to(localAnchor1))
        val r2 = t2.getTransformedR(body2.getLocalCenter().to(localAnchor2))
        val worldAxis = body1.getWorldVector(xAxis)
        val p1 = body1.getWorldCenter().sum(r1)
        val p2 = body2.getWorldCenter().sum(r2)
        val d = p2.subtract(p1)
        val v1 = r1.cross(body1.getAngularVelocity()).add(body1.getLinearVelocity())
        val v2 = r2.cross(body2.getAngularVelocity()).add(body2.getLinearVelocity())
        return worldAxis.dot(v2.subtract(v1)) + d.dot(worldAxis.cross(body1.getAngularVelocity()))
    }
    open fun getAngularSpeed(): Double = body2.getAngularVelocity() - body1.getAngularVelocity()
    open fun getLinearTranslation(): Double {
        val d = body2.getWorldPoint(localAnchor2).difference(body1.getWorldPoint(localAnchor1))
        return d.dot(body1.getWorldVector(xAxis))
    }
    open fun getAngularTranslation(): Double = body2.getTransform().getRotationAngle() - body1.getTransform().getRotationAngle()
    open fun getAxis(): Vector2 = body1.getWorldVector(xAxis)
    open fun setSpringRestOffset(offset: Double) {
        if (springRestOffset != offset) {
            springRestOffset = offset
            if (springEnabled) wakeBodies()
        }
    }
    open fun getSpringRestOffset(): Double = springRestOffset

    override fun isMotorEnabled(): Boolean = motorEnabled
    override fun setMotorEnabled(motorEnabled: Boolean) {
        if (this.motorEnabled != motorEnabled) {
            wakeBodies()
            this.motorEnabled = motorEnabled
        }
    }
    override fun getMotorSpeed(): Double = motorSpeed
    override fun setMotorSpeed(motorSpeed: Double) {
        if (this.motorSpeed != motorSpeed) {
            if (motorEnabled) wakeBodies()
            this.motorSpeed = motorSpeed
        }
    }
    override fun isMaximumMotorTorqueEnabled(): Boolean = motorMaximumTorqueEnabled
    override fun setMaximumMotorTorqueEnabled(enabled: Boolean) {
        if (motorMaximumTorqueEnabled != enabled) {
            if (motorEnabled) wakeBodies()
            motorMaximumTorqueEnabled = enabled
        }
    }
    override fun getMaximumMotorTorque(): Double = motorMaximumTorque
    override fun setMaximumMotorTorque(maximumMotorTorque: Double) {
        if (maximumMotorTorque < 0.0) throw ValueOutOfRangeException("maximumMotorTorque", maximumMotorTorque,
            ValueOutOfRangeException.MUST_BE_GREATER_THAN_OR_EQUAL_TO, 0.0)
        if (motorMaximumTorque != maximumMotorTorque) {
            if (motorEnabled) wakeBodies()
            motorMaximumTorque = maximumMotorTorque
        }
    }
    override fun getMotorTorque(invdt: Double): Double = motorImpulse * invdt

    override fun getSpringDampingRatio(): Double = springDampingRatio
    override fun setSpringDampingRatio(dampingRatio: Double) {
        if (dampingRatio < 0.0) throw ValueOutOfRangeException("dampingRatio", dampingRatio,
            ValueOutOfRangeException.MUST_BE_GREATER_THAN_OR_EQUAL_TO, 0.0)
        if (dampingRatio > 1.0) throw ValueOutOfRangeException("dampingRatio", dampingRatio,
            ValueOutOfRangeException.MUST_BE_LESS_THAN_OR_EQUAL_TO, 1.0)
        if (springDampingRatio != dampingRatio) {
            springDampingRatio = dampingRatio
            if (springEnabled && springDamperEnabled) wakeBodies()
        }
    }
    override fun getSpringFrequency(): Double = springFrequency
    override fun getSpringStiffness(): Double = springStiffness
    override fun setSpringFrequency(frequency: Double) {
        if (frequency < 0.0) throw ValueOutOfRangeException("frequency", frequency,
            ValueOutOfRangeException.MUST_BE_GREATER_THAN_OR_EQUAL_TO, 0.0)
        springMode = Joint.SPRING_MODE_FREQUENCY
        if (springFrequency != frequency) {
            springFrequency = frequency
            if (springEnabled) wakeBodies()
        }
    }
    override fun setSpringStiffness(stiffness: Double) {
        if (stiffness < 0.0) throw ValueOutOfRangeException("stiffness", stiffness,
            ValueOutOfRangeException.MUST_BE_GREATER_THAN_OR_EQUAL_TO, 0.0)
        springMode = Joint.SPRING_MODE_STIFFNESS
        if (springStiffness != stiffness) {
            springStiffness = stiffness
            if (springEnabled) wakeBodies()
        }
    }
    override fun getMaximumSpringForce(): Double = springMaximumForce
    override fun setMaximumSpringForce(maximum: Double) {
        if (maximum < 0.0) throw ValueOutOfRangeException("maximum", maximum,
            ValueOutOfRangeException.MUST_BE_GREATER_THAN_OR_EQUAL_TO, 0.0)
        if (springMaximumForce != maximum) {
            springMaximumForce = maximum
            if (springEnabled && springMaximumForceEnabled) wakeBodies()
        }
    }
    override fun isMaximumSpringForceEnabled(): Boolean = springMaximumForceEnabled
    override fun setMaximumSpringForceEnabled(enabled: Boolean) {
        if (springMaximumForceEnabled != enabled) {
            springMaximumForceEnabled = enabled
            if (springEnabled) wakeBodies()
        }
    }
    override fun isSpringEnabled(): Boolean = springEnabled
    override fun setSpringEnabled(enabled: Boolean) {
        if (springEnabled != enabled) {
            springEnabled = enabled
            wakeBodies()
        }
    }
    override fun isSpringDamperEnabled(): Boolean = springDamperEnabled
    override fun setSpringDamperEnabled(enabled: Boolean) {
        if (springDamperEnabled != enabled) {
            springDamperEnabled = enabled
            if (springEnabled) wakeBodies()
        }
    }
    override fun getSpringForce(invdt: Double): Double = springImpulse * invdt
    override fun getSpringMode(): Int = springMode

    override fun getUpperLimit(): Double = upperLimit
    override fun setUpperLimit(upperLimit: Double) {
        if (upperLimit < lowerLimit) throw ValueOutOfRangeException("upperLimit", upperLimit,
            ValueOutOfRangeException.MUST_BE_GREATER_THAN_OR_EQUAL_TO, "lowerLimit", lowerLimit)
        if (this.upperLimit != upperLimit) {
            if (upperLimitEnabled) wakeBodies()
            this.upperLimit = upperLimit
            upperLimitImpulse = 0.0
        }
    }
    override fun setUpperLimitEnabled(flag: Boolean) {
        if (upperLimitEnabled != flag) {
            wakeBodies()
            upperLimitEnabled = flag
            upperLimitImpulse = 0.0
        }
    }
    override fun isUpperLimitEnabled(): Boolean = upperLimitEnabled
    override fun getLowerLimit(): Double = lowerLimit
    override fun setLowerLimit(lowerLimit: Double) {
        if (lowerLimit > upperLimit) throw ValueOutOfRangeException("lowerLimit", lowerLimit,
            ValueOutOfRangeException.MUST_BE_LESS_THAN_OR_EQUAL_TO, "upperLimit", upperLimit)
        if (this.lowerLimit != lowerLimit) {
            if (lowerLimitEnabled) wakeBodies()
            this.lowerLimit = lowerLimit
            lowerLimitImpulse = 0.0
        }
    }
    override fun setLowerLimitEnabled(flag: Boolean) {
        if (lowerLimitEnabled != flag) {
            wakeBodies()
            lowerLimitEnabled = flag
            lowerLimitImpulse = 0.0
        }
    }
    override fun isLowerLimitEnabled(): Boolean = lowerLimitEnabled
    override fun setLimits(lowerLimit: Double, upperLimit: Double) {
        if (lowerLimit > upperLimit) throw ValueOutOfRangeException("lowerLimit", lowerLimit,
            ValueOutOfRangeException.MUST_BE_LESS_THAN_OR_EQUAL_TO, "upperLimit", upperLimit)
        if (this.lowerLimit != lowerLimit || this.upperLimit != upperLimit) {
            if (lowerLimitEnabled || upperLimitEnabled) wakeBodies()
            this.lowerLimit = lowerLimit
            this.upperLimit = upperLimit
            lowerLimitImpulse = 0.0
            upperLimitImpulse = 0.0
        }
    }
    override fun setLimitsEnabled(lowerLimit: Double, upperLimit: Double) {
        setLimitsEnabled(true)
        setLimits(lowerLimit, upperLimit)
    }
    override fun setLimitsEnabled(flag: Boolean) {
        if (lowerLimitEnabled != flag || upperLimitEnabled != flag) {
            lowerLimitEnabled = flag
            upperLimitEnabled = flag
            wakeBodies()
            lowerLimitImpulse = 0.0
            upperLimitImpulse = 0.0
        }
    }
    override fun setLimits(limit: Double) {
        if (lowerLimit != limit || upperLimit != limit) {
            if (lowerLimitEnabled || upperLimitEnabled) wakeBodies()
            lowerLimit = limit
            upperLimit = limit
            lowerLimitImpulse = 0.0
            upperLimitImpulse = 0.0
        }
    }
    override fun setLimitsEnabled(limit: Double) {
        setLimitsEnabled(true)
        setLimits(limit)
    }

    private fun wakeBodies() {
        body1.setAtRest(false)
        body2.setAtRest(false)
    }
}
