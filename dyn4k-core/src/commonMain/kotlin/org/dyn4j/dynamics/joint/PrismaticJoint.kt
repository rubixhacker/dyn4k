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

import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min
import org.dyn4j.Epsilon
import org.dyn4j.dynamics.PhysicsBody
import org.dyn4j.dynamics.Settings
import org.dyn4j.dynamics.TimeStep
import org.dyn4j.exception.ArgumentNullException
import org.dyn4j.exception.ValueOutOfRangeException
import org.dyn4j.geometry.Geometry
import org.dyn4j.geometry.Interval
import org.dyn4j.geometry.Matrix22
import org.dyn4j.geometry.Matrix33
import org.dyn4j.geometry.Vector2
import org.dyn4j.geometry.Vector3

open class PrismaticJoint<T : PhysicsBody> : AbstractPairedBodyJoint<T>, LinearLimitsJoint,
    LinearMotorJoint, LinearSpringJoint {
    @kotlin.jvm.JvmField protected val localAnchor1: Vector2
    @kotlin.jvm.JvmField protected val localAnchor2: Vector2
    @kotlin.jvm.JvmField protected val xAxis: Vector2
    @kotlin.jvm.JvmField protected val yAxis: Vector2
    @kotlin.jvm.JvmField protected var referenceAngle: Double
    @kotlin.jvm.JvmField protected var upperLimitEnabled = false
    @kotlin.jvm.JvmField protected var lowerLimitEnabled = false
    @kotlin.jvm.JvmField protected var upperLimit = 0.0
    @kotlin.jvm.JvmField protected var lowerLimit = 0.0
    @kotlin.jvm.JvmField protected var motorEnabled = false
    @kotlin.jvm.JvmField protected var motorSpeed = 0.0
    @kotlin.jvm.JvmField protected var maximumMotorForceEnabled = false
    @kotlin.jvm.JvmField protected var maximumMotorForce = 1000.0
    @kotlin.jvm.JvmField protected var springEnabled = false
    @kotlin.jvm.JvmField protected var springDamperEnabled = false
    @kotlin.jvm.JvmField protected var springMode = Joint.SPRING_MODE_FREQUENCY
    @kotlin.jvm.JvmField protected var springFrequency = 8.0
    @kotlin.jvm.JvmField protected var springStiffness = 0.0
    @kotlin.jvm.JvmField protected var springDampingRatio = 0.3
    @kotlin.jvm.JvmField protected var springMaximumForceEnabled = false
    @kotlin.jvm.JvmField protected var springMaximumForce = 1000.0
    @kotlin.jvm.JvmField protected var springRestOffset = 0.0

    @kotlin.jvm.JvmField internal var damping = 0.0
    @kotlin.jvm.JvmField internal var bias = 0.0
    @kotlin.jvm.JvmField internal var gamma = 0.0
    @kotlin.jvm.JvmField internal val K: Matrix22
    @kotlin.jvm.JvmField internal var axialMass = 0.0
    @kotlin.jvm.JvmField internal var springMass = 0.0
    @kotlin.jvm.JvmField internal val perp: Vector2
    @kotlin.jvm.JvmField internal val axis: Vector2
    @kotlin.jvm.JvmField internal var s1 = 0.0
    @kotlin.jvm.JvmField internal var s2 = 0.0
    @kotlin.jvm.JvmField internal var a1 = 0.0
    @kotlin.jvm.JvmField internal var a2 = 0.0
    @kotlin.jvm.JvmField internal var translation = 0.0
    @kotlin.jvm.JvmField internal val impulse: Vector2
    @kotlin.jvm.JvmField internal var springImpulse = 0.0
    @kotlin.jvm.JvmField internal var motorImpulse = 0.0
    @kotlin.jvm.JvmField internal var lowerLimitImpulse = 0.0
    @kotlin.jvm.JvmField internal var upperLimitImpulse = 0.0

    constructor(body1: T?, body2: T?, anchor: Vector2?, axis: Vector2?) : super(body1, body2) {
        val point = anchor ?: throw ArgumentNullException("anchor")
        val direction = axis ?: throw ArgumentNullException("axis")
        if (direction.getMagnitude() <= Epsilon.E) throw IllegalArgumentException("The axis cannot be a zero vector.")
        localAnchor1 = this.body1.getLocalPoint(point)
        localAnchor2 = this.body2.getLocalPoint(point)
        xAxis = this.body1.getLocalVector(direction.getNormalized())
        yAxis = xAxis.getRightHandOrthogonalVector()
        referenceAngle = this.body2.getTransform().getRotationAngle() - this.body1.getTransform().getRotationAngle()
        K = Matrix22()
        perp = Vector2()
        this.axis = Vector2()
        impulse = Vector2()
    }

    protected constructor(joint: PrismaticJoint<T>) : this(joint, null, null)

    protected constructor(joint: PrismaticJoint<T>, body1: T?, body2: T?) : super(joint, body1, body2) {
        localAnchor1 = joint.localAnchor1.copy()
        localAnchor2 = joint.localAnchor2.copy()
        xAxis = joint.xAxis.copy()
        yAxis = joint.yAxis.copy()
        referenceAngle = joint.referenceAngle
        upperLimitEnabled = joint.upperLimitEnabled
        lowerLimitEnabled = joint.lowerLimitEnabled
        upperLimit = joint.upperLimit
        lowerLimit = joint.lowerLimit
        motorEnabled = joint.motorEnabled
        motorSpeed = joint.motorSpeed
        maximumMotorForceEnabled = joint.maximumMotorForceEnabled
        maximumMotorForce = joint.maximumMotorForce
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
        K = joint.K.copy()
        axialMass = joint.axialMass
        springMass = joint.springMass
        perp = joint.perp.copy()
        axis = joint.axis.copy()
        s1 = joint.s1
        s2 = joint.s2
        a1 = joint.a1
        a2 = joint.a2
        translation = joint.translation
        impulse = joint.impulse.copy()
        springImpulse = joint.springImpulse
        motorImpulse = joint.motorImpulse
        lowerLimitImpulse = joint.lowerLimitImpulse
        upperLimitImpulse = joint.upperLimitImpulse
    }

    override fun copy(): PrismaticJoint<T> = PrismaticJoint(this)
    override fun copy(body1: T?, body2: T?): PrismaticJoint<T> = PrismaticJoint(this, body1, body2)

    override fun toString() = "PrismaticJoint[${super.toString()}|Anchor=${getAnchor1()}|Axis=${getAxis()}" +
        "|IsMotorEnabled=$motorEnabled|MotorSpeed=$motorSpeed|MaximumMotorForce=$maximumMotorForce" +
        "|ReferenceAngle=$referenceAngle|IsLowerLimitEnabled=$lowerLimitEnabled" +
        "|IsUpperLimitEnabled=$upperLimitEnabled|LowerLimit=$lowerLimit|UpperLimit=$upperLimit]"

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
        body1.getWorldVector(xAxis, axis)
        body1.getWorldVector(yAxis, perp)
        s1 = r1.sum(d).cross(perp)
        s2 = r2.cross(perp)
        a1 = r1.sum(d).cross(axis)
        a2 = r2.cross(axis)
        val invMass = invM1 + invM2 + a1 * a1 * invI1 + a2 * a2 * invI2
        axialMass = if (invMass > Epsilon.E) 1.0 / invMass else 0.0
        K.m00 = invM1 + invM2 + s1 * s1 * invI1 + s2 * s2 * invI2
        K.m01 = s1 * invI1 + s2 * invI2
        K.m10 = K.m01
        K.m11 = invI1 + invI2
        if (K.m11 <= Epsilon.E) K.m11 = 1.0
        if (springEnabled && invMass > 0.0) {
            updateSpringCoefficients()
            val c = d.dot(axis) - springRestOffset
            val dt = h.getDeltaTime()
            gamma = getConstraintImpulseMixing(dt, springStiffness, damping)
            val erp = getErrorReductionParameter(dt, springStiffness, damping)
            bias = c * erp
            springMass = invMass + gamma
            if (springMass > Epsilon.E) springMass = 1.0 / springMass
        } else {
            springMass = 0.0
            springImpulse = 0.0
            damping = 0.0
        }
        if (lowerLimitEnabled || upperLimitEnabled) translation = axis.dot(d)
        if (!lowerLimitEnabled) lowerLimitImpulse = 0.0
        if (!upperLimitEnabled) upperLimitImpulse = 0.0
        if (!motorEnabled) motorImpulse = 0.0
        if (config.isWarmStartingEnabled()) {
            val ratio = h.getDeltaTimeRatio()
            impulse.multiply(ratio)
            springImpulse *= ratio
            motorImpulse *= ratio
            lowerLimitImpulse *= ratio
            upperLimitImpulse *= ratio
            val axialImpulse = springImpulse + motorImpulse + lowerLimitImpulse - upperLimitImpulse
            val p = Vector2(perp.x * impulse.x + axialImpulse * axis.x,
                perp.y * impulse.x + axialImpulse * axis.y)
            val l1 = impulse.x * s1 + impulse.y + axialImpulse * a1
            val l2 = impulse.x * s2 + impulse.y + axialImpulse * a2
            body1.getLinearVelocity().subtract(p.product(invM1))
            body1.setAngularVelocity(body1.getAngularVelocity() - invI1 * l1)
            body2.getLinearVelocity().add(p.product(invM2))
            body2.setAngularVelocity(body2.getAngularVelocity() + invI2 * l2)
        } else {
            impulse.zero()
            motorImpulse = 0.0
            springImpulse = 0.0
            lowerLimitImpulse = 0.0
            upperLimitImpulse = 0.0
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
            val cdt = axis.dot(v2.difference(v1)) + a2 * w2 - a1 * w1
            var amount = -springMass * (cdt + bias + gamma * springImpulse)
            if (springMaximumForceEnabled) {
                val previous = springImpulse
                val cap = h.getDeltaTime() * springMaximumForce
                springImpulse = Interval.clamp(springImpulse + amount, -cap, cap)
                amount = springImpulse - previous
            } else springImpulse += amount
            val p = axis.product(amount)
            v1.subtract(p.product(invM1))
            w1 -= amount * a1 * invI1
            v2.add(p.product(invM2))
            w2 += amount * a2 * invI2
        }
        if (motorEnabled) {
            val cdt = axis.dot(v2.difference(v1)) + a2 * w2 - a1 * w1
            var amount = axialMass * (motorSpeed - cdt)
            if (maximumMotorForceEnabled) {
                val previous = motorImpulse
                val cap = maximumMotorForce * h.getDeltaTime()
                motorImpulse = Interval.clamp(motorImpulse + amount, -cap, cap)
                amount = motorImpulse - previous
            } else motorImpulse += amount
            val p = axis.product(amount)
            v1.subtract(p.product(invM1))
            w1 -= amount * a1 * invI1
            v2.add(p.product(invM2))
            w2 += amount * a2 * invI2
        }
        val invdt = h.getInverseDeltaTime()
        if (lowerLimitEnabled) {
            val c = translation - lowerLimit
            val cdt = axis.dot(v2.difference(v1)) + a2 * w2 - a1 * w1
            var amount = -axialMass * (cdt + max(c, 0.0) * invdt)
            val previous = lowerLimitImpulse
            lowerLimitImpulse = max(lowerLimitImpulse + amount, 0.0)
            amount = lowerLimitImpulse - previous
            val p = axis.product(amount)
            v1.subtract(p.product(invM1))
            w1 -= amount * a1 * invI1
            v2.add(p.product(invM2))
            w2 += amount * a2 * invI2
        }
        if (upperLimitEnabled) {
            val c = upperLimit - translation
            val cdt = axis.dot(v1.difference(v2)) + a1 * w1 - a2 * w2
            var amount = -axialMass * (cdt + max(c, 0.0) * invdt)
            val previous = upperLimitImpulse
            upperLimitImpulse = max(upperLimitImpulse + amount, 0.0)
            amount = upperLimitImpulse - previous
            val p = axis.product(amount)
            v1.add(p.product(invM1))
            w1 += amount * a1 * invI1
            v2.subtract(p.product(invM2))
            w2 -= amount * a2 * invI2
        }
        val cdt = Vector2(perp.dot(v2.difference(v1)) + s2 * w2 - s1 * w1, w2 - w1)
        val amount = K.solve(cdt.negate())
        impulse.x += amount.x
        impulse.y += amount.y
        val p = perp.product(amount.x)
        val l1 = amount.x * s1 + amount.y
        val l2 = amount.x * s2 + amount.y
        v1.subtract(p.product(invM1))
        w1 -= l1 * invI1
        v2.add(p.product(invM2))
        w2 += l2 * invI2
        body1.setAngularVelocity(w1)
        body2.setAngularVelocity(w2)
    }

    override fun solvePositionConstraints(step: TimeStep?, settings: Settings?): Boolean {
        val linearTolerance = settings!!.getLinearTolerance()
        val angularTolerance = settings.getAngularTolerance()
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
        val d = c2.sum(r2).subtract(c1.sum(r1))
        val worldAxis = body1.getWorldVector(xAxis)
        val ax1 = r1.sum(d).cross(worldAxis)
        val ax2 = r2.cross(worldAxis)
        val worldPerp = body1.getWorldVector(yAxis)
        val sy1 = r1.sum(d).cross(worldPerp)
        val sy2 = r2.cross(worldPerp)
        val c = Vector2(worldPerp.dot(d), getRelativeRotation())
        var c2Limit = 0.0
        var linearError = abs(c.x)
        val angularError = abs(c.y)
        var limitActive = false
        if (lowerLimitEnabled || upperLimitEnabled) {
            val position = worldAxis.dot(d)
            if (upperLimitEnabled && lowerLimitEnabled && abs(upperLimit - lowerLimit) < 2.0 * linearTolerance) {
                c2Limit = position
                linearError = max(linearError, abs(position))
                limitActive = true
            } else if (lowerLimitEnabled && position <= lowerLimit) {
                c2Limit = min(position - lowerLimit, 0.0)
                linearError = max(linearError, lowerLimit - position)
                limitActive = true
            } else if (upperLimitEnabled && position >= upperLimit) {
                c2Limit = max(position - upperLimit, 0.0)
                linearError = max(linearError, position - upperLimit)
                limitActive = true
            }
        }
        val correction: Vector3
        if (limitActive) {
            val matrix = Matrix33()
            matrix.m00 = invM1 + invM2 + sy1 * sy1 * invI1 + sy2 * sy2 * invI2
            matrix.m01 = sy1 * invI1 + sy2 * invI2
            matrix.m02 = sy1 * ax1 * invI1 + sy2 * ax2 * invI2
            matrix.m10 = matrix.m01
            matrix.m11 = invI1 + invI2
            if (matrix.m11 <= Epsilon.E) matrix.m11 = 1.0
            matrix.m12 = ax1 * invI1 + ax2 * invI2
            matrix.m20 = matrix.m02
            matrix.m21 = matrix.m12
            matrix.m22 = invM1 + invM2 + ax1 * ax1 * invI1 + ax2 * ax2 * invI2
            correction = matrix.solve33(Vector3(c.x, c.y, c2Limit).negate())
        } else {
            val matrix = Matrix22()
            matrix.m00 = invM1 + invM2 + sy1 * sy1 * invI1 + sy2 * sy2 * invI2
            matrix.m01 = sy1 * invI1 + sy2 * invI2
            matrix.m10 = matrix.m01
            matrix.m11 = invI1 + invI2
            if (matrix.m11 <= Epsilon.E) matrix.m11 = 1.0
            val result = matrix.solve(c.negate())
            correction = Vector3(result.x, result.y, 0.0)
        }
        val p = Vector2(worldPerp.x * correction.x + correction.z * worldAxis.x,
            worldPerp.y * correction.x + correction.z * worldAxis.y)
        val l1 = correction.x * sy1 + correction.y + correction.z * ax1
        val l2 = correction.x * sy2 + correction.y + correction.z * ax2
        body1.translate(p.product(-invM1))
        body1.rotateAboutCenter(-l1 * invI1)
        body2.translate(p.product(invM2))
        body2.rotateAboutCenter(l2 * invI2)
        return linearError <= linearTolerance && angularError <= angularTolerance
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

    private fun getRelativeRotation(): Double {
        var angle = body2.getTransform().getRotationAngle() - body1.getTransform().getRotationAngle() - referenceAngle
        if (angle < -PI) angle += Geometry.TWO_PI
        if (angle > PI) angle -= Geometry.TWO_PI
        return angle
    }

    open fun getAnchor1(): Vector2 = body1.getWorldPoint(localAnchor1)
    open fun getAnchor2(): Vector2 = body2.getWorldPoint(localAnchor2)
    override fun getReactionForce(invdt: Double): Vector2 {
        val axialImpulse = springImpulse + motorImpulse + lowerLimitImpulse - upperLimitImpulse
        return Vector2(impulse.x * perp.x + axialImpulse * axis.x,
            impulse.x * perp.y + axialImpulse * axis.y).multiply(invdt)
    }
    override fun getReactionTorque(invdt: Double): Double = invdt * impulse.y
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
    open fun getLinearTranslation(): Double {
        val d = body2.getWorldPoint(localAnchor2).difference(body1.getWorldPoint(localAnchor1))
        return d.dot(body1.getWorldVector(xAxis))
    }
    open fun getAxis(): Vector2 = body1.getWorldVector(xAxis)
    open fun getReferenceAngle(): Double = referenceAngle
    open fun setReferenceAngle(angle: Double) {
        if (referenceAngle != angle) {
            referenceAngle = angle
            wakeBodies()
        }
    }

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
            motorImpulse = 0.0
        }
    }
    override fun getMaximumMotorForce(): Double = maximumMotorForce
    override fun setMaximumMotorForce(maximumMotorForce: Double) {
        if (maximumMotorForce < 0.0) throw ValueOutOfRangeException("maximumMotorForce", maximumMotorForce,
            ValueOutOfRangeException.MUST_BE_GREATER_THAN_OR_EQUAL_TO, 0.0)
        if (this.maximumMotorForce != maximumMotorForce) {
            this.maximumMotorForce = maximumMotorForce
            if (motorEnabled && maximumMotorForceEnabled) wakeBodies()
        }
    }
    override fun setMaximumMotorForceEnabled(enabled: Boolean) {
        if (maximumMotorForceEnabled != enabled) {
            maximumMotorForceEnabled = enabled
            if (motorEnabled) wakeBodies()
        }
    }
    override fun isMaximumMotorForceEnabled(): Boolean = maximumMotorForceEnabled
    override fun getMotorForce(invdt: Double): Double = motorImpulse * invdt

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
    open fun setSpringRestOffset(offset: Double) {
        if (springRestOffset != offset) {
            springRestOffset = offset
            if (springEnabled) wakeBodies()
        }
    }
    open fun getSpringRestOffset(): Double = springRestOffset

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
