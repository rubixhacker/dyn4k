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

import org.dyn4j.DataContainer
import org.dyn4j.Epsilon
import org.dyn4j.Ownable
import org.dyn4j.dynamics.PhysicsBody
import org.dyn4j.dynamics.Settings
import org.dyn4j.dynamics.TimeStep
import org.dyn4j.exception.ArgumentNullException
import org.dyn4j.exception.ValueOutOfRangeException
import org.dyn4j.geometry.Matrix22
import org.dyn4j.geometry.Shiftable
import org.dyn4j.geometry.Vector2

open class PinJoint<T : PhysicsBody> : AbstractSingleBodyJoint<T>, LinearSpringJoint, SingleBodyJoint<T>, Joint<T>, Shiftable, DataContainer, Ownable {
    @kotlin.jvm.JvmField protected val target: Vector2
    @kotlin.jvm.JvmField protected val localAnchor: Vector2
    @kotlin.jvm.JvmField protected var springEnabled: Boolean
    @kotlin.jvm.JvmField protected var springMode: Int
    @kotlin.jvm.JvmField protected var springFrequency: Double
    @kotlin.jvm.JvmField protected var springStiffness: Double
    @kotlin.jvm.JvmField protected var springDamperEnabled: Boolean
    @kotlin.jvm.JvmField protected var springDampingRatio: Double
    @kotlin.jvm.JvmField protected var springMaximumForceEnabled: Boolean
    @kotlin.jvm.JvmField protected var springMaximumForce: Double
    @kotlin.jvm.JvmField protected var correctionFactor: Double
    @kotlin.jvm.JvmField protected var correctionMaximumForce: Double

    @kotlin.jvm.JvmField protected val r: Vector2
    @kotlin.jvm.JvmField protected var damping: Double
    @kotlin.jvm.JvmField protected val bias: Vector2
    @kotlin.jvm.JvmField protected var gamma: Double
    @kotlin.jvm.JvmField protected val K: Matrix22
    @kotlin.jvm.JvmField protected val linearError: Vector2
    @kotlin.jvm.JvmField protected val impulse: Vector2

    constructor(body: T?, anchor: Vector2?) : super(body) {
        if (anchor == null) throw ArgumentNullException("anchor")
        target = anchor.copy()
        localAnchor = this.body.getLocalPoint(anchor)
        springMode = Joint.SPRING_MODE_FREQUENCY
        springEnabled = true
        springFrequency = 8.0
        springStiffness = 0.0
        springDamperEnabled = true
        springDampingRatio = 0.3
        springMaximumForceEnabled = true
        springMaximumForce = 1000.0
        correctionFactor = 0.3
        correctionMaximumForce = 1000.0
        damping = 0.0
        gamma = 0.0
        r = Vector2()
        bias = Vector2()
        K = Matrix22()
        linearError = Vector2()
        impulse = Vector2()
    }

    protected constructor(joint: PinJoint<T>) : this(joint, null)

    protected constructor(joint: PinJoint<T>, body: T?) : super(joint, body) {
        target = joint.target.copy()
        localAnchor = joint.localAnchor.copy()
        springMode = joint.springMode
        springEnabled = joint.springEnabled
        springFrequency = joint.springFrequency
        springStiffness = joint.springStiffness
        springDamperEnabled = joint.springDamperEnabled
        springDampingRatio = joint.springDampingRatio
        springMaximumForceEnabled = joint.springMaximumForceEnabled
        springMaximumForce = joint.springMaximumForce
        correctionFactor = joint.correctionFactor
        correctionMaximumForce = joint.correctionMaximumForce
        r = joint.r.copy()
        linearError = joint.linearError.copy()
        damping = joint.damping
        gamma = joint.gamma
        bias = joint.bias.copy()
        K = joint.K.copy()
        impulse = joint.impulse.copy()
    }

    override fun copy(): PinJoint<T> = PinJoint(this)
    override fun copy(body: T?): PinJoint<T> = PinJoint(this, body)

    override fun toString(): String =
        "PinJoint[${super.toString()}|Target=$target|Anchor=$localAnchor|Frequency=$springFrequency" +
            "|DampingRatio=$springDampingRatio|MaximumForce=$springMaximumForce]"

    override fun initializeConstraints(step: TimeStep?, settings: Settings?) {
        val step = step!!
        val settings = settings!!
        val transform = body.getTransform()
        val mass = body.getMass()
        val invM = mass.getInverseMass()
        val invI = mass.getInverseInertia()
        transform.getTransformedR(body.getLocalCenter().to(localAnchor), r)
        K.m00 = invM + r.y * r.y * invI
        K.m01 = -invI * r.x * r.y
        K.m10 = K.m01
        K.m11 = invM + r.x * r.x * invI

        if (springEnabled) {
            updateSpringCoefficients()
            val dt = step.getDeltaTime()
            gamma = getConstraintImpulseMixing(dt, springStiffness, damping)
            val erp = getErrorReductionParameter(dt, springStiffness, damping)
            bias.set(body.getWorldCenter().add(r).difference(target))
            bias.multiply(erp)
            K.m00 += gamma
            K.m11 += gamma
        } else {
            val bodyPoint = r.sum(body.getWorldCenter())
            linearError.set(target.x - bodyPoint.x, target.y - bodyPoint.y)
        }

        if (settings.isWarmStartingEnabled()) {
            impulse.multiply(step.getDeltaTimeRatio())
            body.getLinearVelocity().add(impulse.product(invM))
            body.setAngularVelocity(body.getAngularVelocity() + invI * r.cross(impulse))
        } else {
            impulse.zero()
        }
    }

    override fun solveVelocityConstraints(step: TimeStep?, settings: Settings?) {
        val step = step!!
        val mass = body.getMass()
        val invM = mass.getInverseMass()
        val invI = mass.getInverseInertia()
        val invdt = step.getInverseDeltaTime()
        val dt = step.getDeltaTime()
        val relativeVelocity = r.cross(body.getAngularVelocity()).add(body.getLinearVelocity())

        if (springEnabled) {
            relativeVelocity.add(bias)
            relativeVelocity.add(impulse.product(gamma))
            relativeVelocity.negate()
            var stepImpulse = K.solve(relativeVelocity)
            if (springMaximumForceEnabled) {
                val previousImpulse = impulse.copy()
                impulse.add(stepImpulse)
                val maximumImpulse = step.getDeltaTime() * springMaximumForce
                if (impulse.getMagnitudeSquared() > maximumImpulse * maximumImpulse) {
                    impulse.normalize()
                    impulse.multiply(maximumImpulse)
                }
                stepImpulse = impulse.difference(previousImpulse)
            } else {
                impulse.add(stepImpulse)
            }
            body.getLinearVelocity().add(stepImpulse.product(invM))
            body.setAngularVelocity(body.getAngularVelocity() + invI * r.cross(stepImpulse))
        } else {
            val pivotVelocity = relativeVelocity.getNegative()
            pivotVelocity.add(linearError.product(correctionFactor * invdt))
            var stepImpulse = K.solve(pivotVelocity)
            val previousImpulse = impulse.copy()
            impulse.add(stepImpulse)
            val maximumImpulse = correctionMaximumForce * dt
            if (impulse.getMagnitudeSquared() > maximumImpulse * maximumImpulse) {
                impulse.normalize()
                impulse.multiply(maximumImpulse)
            }
            stepImpulse = impulse.difference(previousImpulse)
            body.getLinearVelocity().add(stepImpulse.product(invM))
            body.setAngularVelocity(body.getAngularVelocity() + invI * r.cross(stepImpulse))
        }
    }

    override fun solvePositionConstraints(step: TimeStep?, settings: Settings?): Boolean = true

    protected open fun updateSpringCoefficients() {
        val mass = body.getMass()
        var m = mass.getMass()
        if (m <= Epsilon.E) m = mass.getInertia()
        var naturalFrequency = 0.0
        if (springMode == Joint.SPRING_MODE_FREQUENCY) {
            naturalFrequency = getNaturalFrequency(springFrequency)
            springStiffness = getSpringStiffness(m, naturalFrequency)
        } else if (springMode == Joint.SPRING_MODE_STIFFNESS) {
            naturalFrequency = getNaturalFrequency(springStiffness, m)
            springFrequency = getFrequency(naturalFrequency)
        }
        damping = if (springDamperEnabled) getSpringDampingCoefficient(m, naturalFrequency, springDampingRatio) else 0.0
    }

    open fun getAnchor(): Vector2 = body.getWorldPoint(localAnchor)
    open fun setTarget(target: Vector2?) {
        if (target == null) throw ArgumentNullException("target")
        if (!target.equals(this.target)) {
            body.setAtRest(false)
            this.target.set(target)
        }
    }
    open fun setTarget(x: Double, y: Double) {
        if (!target.equals(x, y)) {
            body.setAtRest(false)
            target.set(x, y)
        }
    }
    open fun getTarget(): Vector2 = target
    override fun getReactionForce(invdt: Double): Vector2 = impulse.product(invdt)
    override fun getReactionTorque(invdt: Double): Double = 0.0
    override fun isCollisionAllowed(): Boolean = false
    override fun shift(shift: Vector2) { target.add(shift) }

    override fun getSpringDampingRatio(): Double = springDampingRatio
    override fun getSpringMode(): Int = springMode
    open fun getCorrectionFactor(): Double = correctionFactor
    open fun setCorrectionFactor(value: Double) {
        if (value < 0.0) throw ValueOutOfRangeException("correctionFactor", value, ValueOutOfRangeException.MUST_BE_GREATER_THAN_OR_EQUAL_TO, 0.0)
        if (value > 1.0) throw ValueOutOfRangeException("correctionFactor", value, ValueOutOfRangeException.MUST_BE_LESS_THAN_OR_EQUAL_TO, 1.0)
        correctionFactor = value
    }
    open fun getMaximumCorrectionForce(): Double = correctionMaximumForce
    open fun setMaximumCorrectionForce(maximumForce: Double) {
        if (maximumForce < 0.0) throw ValueOutOfRangeException("maximumForce", maximumForce, ValueOutOfRangeException.MUST_BE_GREATER_THAN_OR_EQUAL_TO, 0.0)
        correctionMaximumForce = maximumForce
    }
    open fun getCorrectionForce(invdt: Double): Double = if (!springEnabled) impulse.getMagnitude() * invdt else 0.0

    override fun setSpringDampingRatio(dampingRatio: Double) {
        if (dampingRatio < 0.0) throw ValueOutOfRangeException("dampingRatio", dampingRatio, ValueOutOfRangeException.MUST_BE_GREATER_THAN_OR_EQUAL_TO, 0.0)
        if (dampingRatio > 1.0) throw ValueOutOfRangeException("dampingRatio", dampingRatio, ValueOutOfRangeException.MUST_BE_LESS_THAN_OR_EQUAL_TO, 1.0)
        if (springDampingRatio != dampingRatio) {
            springDampingRatio = dampingRatio
            if (springEnabled && springDamperEnabled) body.setAtRest(false)
        }
    }
    override fun getSpringFrequency(): Double = springFrequency
    override fun getSpringStiffness(): Double = springStiffness
    override fun setSpringFrequency(frequency: Double) {
        if (frequency < 0.0) throw ValueOutOfRangeException("frequency", frequency, ValueOutOfRangeException.MUST_BE_GREATER_THAN_OR_EQUAL_TO, 0.0)
        springMode = Joint.SPRING_MODE_FREQUENCY
        if (springFrequency != frequency) {
            springFrequency = frequency
            if (springEnabled) body.setAtRest(false)
        }
    }
    override fun setSpringStiffness(stiffness: Double) {
        if (stiffness < 0.0) throw ValueOutOfRangeException("stiffness", stiffness, ValueOutOfRangeException.MUST_BE_GREATER_THAN_OR_EQUAL_TO, 0.0)
        springMode = Joint.SPRING_MODE_STIFFNESS
        if (springStiffness != stiffness) {
            springStiffness = stiffness
            if (springEnabled) body.setAtRest(false)
        }
    }
    override fun getMaximumSpringForce(): Double = springMaximumForce
    override fun setMaximumSpringForce(maximum: Double) {
        if (maximum < 0.0) throw ValueOutOfRangeException("maximum", maximum, ValueOutOfRangeException.MUST_BE_GREATER_THAN_OR_EQUAL_TO, 0.0)
        if (springMaximumForce != maximum) {
            springMaximumForce = maximum
            if (springEnabled && springMaximumForceEnabled) body.setAtRest(false)
        }
    }
    override fun isMaximumSpringForceEnabled(): Boolean = springMaximumForceEnabled
    override fun setMaximumSpringForceEnabled(enabled: Boolean) {
        if (springMaximumForceEnabled != enabled) {
            springMaximumForceEnabled = enabled
            if (springEnabled) body.setAtRest(false)
        }
    }
    override fun isSpringEnabled(): Boolean = springEnabled
    override fun setSpringEnabled(enabled: Boolean) {
        if (springEnabled != enabled) {
            springEnabled = enabled
            body.setAtRest(false)
            impulse.zero()
        }
    }
    override fun isSpringDamperEnabled(): Boolean = springDamperEnabled
    override fun setSpringDamperEnabled(enabled: Boolean) {
        if (springDamperEnabled != enabled) {
            springDamperEnabled = enabled
            if (springEnabled) body.setAtRest(false)
        }
    }
    override fun getSpringForce(invdt: Double): Double = if (springEnabled) impulse.getMagnitude() * invdt else 0.0
}
