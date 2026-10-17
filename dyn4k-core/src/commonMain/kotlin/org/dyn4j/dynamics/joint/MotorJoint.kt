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
import org.dyn4j.DataContainer
import org.dyn4j.Epsilon
import org.dyn4j.JvmFieldBridge
import org.dyn4j.Ownable
import org.dyn4j.dynamics.PhysicsBody
import org.dyn4j.dynamics.Settings
import org.dyn4j.dynamics.TimeStep
import org.dyn4j.exception.ValueOutOfRangeException
import org.dyn4j.geometry.Geometry
import org.dyn4j.geometry.Interval
import org.dyn4j.geometry.Matrix22
import org.dyn4j.geometry.Shiftable
import org.dyn4j.geometry.Vector2

open class MotorJoint<T : PhysicsBody> : AbstractPairedBodyJoint<T>, PairedBodyJoint<T>, Joint<T>, Shiftable, DataContainer, Ownable {
    @get:kotlin.jvm.JvmName("getLinearTargetField")
    @JvmFieldBridge protected val linearTarget: Vector2
    @get:kotlin.jvm.JvmName("getAngularTargetField")
    @set:kotlin.jvm.JvmName("setAngularTargetField")
    @JvmFieldBridge protected var angularTarget: Double
    @get:kotlin.jvm.JvmName("getCorrectionFactorField")
    @set:kotlin.jvm.JvmName("setCorrectionFactorField")
    @JvmFieldBridge protected var correctionFactor: Double
    @get:kotlin.jvm.JvmName("getMaximumForceField")
    @set:kotlin.jvm.JvmName("setMaximumForceField")
    @JvmFieldBridge protected var maximumForce: Double
    @get:kotlin.jvm.JvmName("getMaximumTorqueField")
    @set:kotlin.jvm.JvmName("setMaximumTorqueField")
    @JvmFieldBridge protected var maximumTorque: Double

    @JvmFieldBridge protected val r1: Vector2
    @JvmFieldBridge protected val r2: Vector2
    @JvmFieldBridge protected val K: Matrix22
    @JvmFieldBridge protected var angularMass: Double
    @JvmFieldBridge protected val linearError: Vector2
    @get:kotlin.jvm.JvmName("getAngularErrorField")
    @JvmFieldBridge protected var angularError: Double
    @JvmFieldBridge protected val linearImpulse: Vector2
    @JvmFieldBridge protected var angularImpulse: Double

    constructor(body1: T?, body2: T?) : super(body1, body2) {
        linearTarget = this.body1.getLocalPoint(this.body2.getWorldCenter())
        angularTarget = this.body2.getTransform().getRotationAngle() - this.body1.getTransform().getRotationAngle()
        correctionFactor = 0.3
        maximumForce = 1000.0
        maximumTorque = 1000.0
        r1 = Vector2()
        r2 = Vector2()
        K = Matrix22()
        angularMass = 0.0
        linearError = Vector2()
        angularError = 0.0
        linearImpulse = Vector2()
        angularImpulse = 0.0
    }

    protected constructor(joint: MotorJoint<T>) : this(joint, null, null)

    protected constructor(joint: MotorJoint<T>, body1: T?, body2: T?) : super(joint, body1, body2) {
        linearTarget = joint.linearTarget.copy()
        angularTarget = joint.angularTarget
        correctionFactor = joint.correctionFactor
        maximumForce = joint.maximumForce
        maximumTorque = joint.maximumTorque
        r1 = joint.r1.copy()
        r2 = joint.r2.copy()
        K = joint.K.copy()
        angularMass = joint.angularMass
        linearError = joint.linearError.copy()
        angularError = joint.angularError
        linearImpulse = joint.linearImpulse.copy()
        angularImpulse = joint.angularImpulse
    }

    override fun copy(): MotorJoint<T> = MotorJoint(this)
    override fun copy(body1: T?, body2: T?): MotorJoint<T> = MotorJoint(this, body1, body2)

    override fun toString(): String =
        "MotorJoint[${super.toString()}|LinearTarget=$linearTarget|AngularTarget=$angularTarget" +
            "|CorrectionFactor=$correctionFactor|MaximumForce=$maximumForce|MaximumTorque=$maximumTorque]"

    override fun initializeConstraints(step: TimeStep?, settings: Settings?) {
        val step = step!!
        val settings = settings!!
        val t1 = body1.getTransform()
        val t2 = body2.getTransform()
        val m1 = body1.getMass()
        val m2 = body2.getMass()
        val invM1 = m1.getInverseMass()
        val invM2 = m2.getInverseMass()
        val invI1 = m1.getInverseInertia()
        val invI2 = m2.getInverseInertia()

        t1.getTransformedR(linearTarget.difference(body1.getLocalCenter()), r1)
        t2.getTransformedR(body2.getLocalCenter().getNegative(), r2)
        K.m00 = invM1 + invM2 + r1.y * r1.y * invI1 + r2.y * r2.y * invI2
        K.m01 = -invI1 * r1.x * r1.y - invI2 * r2.x * r2.y
        K.m10 = K.m01
        K.m11 = invM1 + invM2 + r1.x * r1.x * invI1 + r2.x * r2.x * invI2
        K.invert()

        angularMass = invI1 + invI2
        angularMass = if (angularMass > Epsilon.E) 1.0 / angularMass else 0.0
        val d1 = r1.sum(body1.getWorldCenter())
        val d2 = r2.sum(body2.getWorldCenter())
        linearError.set(d2.x - d1.x, d2.y - d1.y)
        angularError = getAngularError()

        if (settings.isWarmStartingEnabled()) {
            linearImpulse.multiply(step.getDeltaTimeRatio())
            angularImpulse *= step.getDeltaTimeRatio()
            body1.getLinearVelocity().subtract(linearImpulse.product(invM1))
            body1.setAngularVelocity(body1.getAngularVelocity() - invI1 * (r1.cross(linearImpulse) + angularImpulse))
            body2.getLinearVelocity().add(linearImpulse.product(invM2))
            body2.setAngularVelocity(body2.getAngularVelocity() + invI2 * (r2.cross(linearImpulse) + angularImpulse))
        } else {
            linearImpulse.zero()
            angularImpulse = 0.0
        }
    }

    override fun solveVelocityConstraints(step: TimeStep?, settings: Settings?) {
        val step = step!!
        val dt = step.getDeltaTime()
        val invdt = step.getInverseDeltaTime()
        val m1 = body1.getMass()
        val m2 = body2.getMass()
        val invM1 = m1.getInverseMass()
        val invM2 = m2.getInverseMass()
        val invI1 = m1.getInverseInertia()
        val invI2 = m2.getInverseInertia()

        val c = body2.getAngularVelocity() - body1.getAngularVelocity() + invdt * correctionFactor * angularError
        var angularStepImpulse = angularMass * -c
        val previousAngularImpulse = angularImpulse
        val maximumAngularImpulse = maximumTorque * dt
        angularImpulse = Interval.clamp(angularImpulse + angularStepImpulse, -maximumAngularImpulse, maximumAngularImpulse)
        angularStepImpulse = angularImpulse - previousAngularImpulse
        body1.setAngularVelocity(body1.getAngularVelocity() - invI1 * angularStepImpulse)
        body2.setAngularVelocity(body2.getAngularVelocity() + invI2 * angularStepImpulse)

        val v1 = body1.getLinearVelocity().sum(r1.cross(body1.getAngularVelocity()))
        val v2 = body2.getLinearVelocity().sum(r2.cross(body2.getAngularVelocity()))
        val pivotV = v2.subtract(v1)
        pivotV.add(linearError.product(correctionFactor * invdt))
        var stepImpulse = K.multiply(pivotV)
        stepImpulse.negate()
        val previousLinearImpulse = linearImpulse.copy()
        linearImpulse.add(stepImpulse)
        val maximumLinearImpulse = maximumForce * dt
        if (linearImpulse.getMagnitudeSquared() > maximumLinearImpulse * maximumLinearImpulse) {
            linearImpulse.normalize()
            linearImpulse.multiply(maximumLinearImpulse)
        }
        stepImpulse = linearImpulse.difference(previousLinearImpulse)
        body1.getLinearVelocity().subtract(stepImpulse.product(invM1))
        body1.setAngularVelocity(body1.getAngularVelocity() - invI1 * r1.cross(stepImpulse))
        body2.getLinearVelocity().add(stepImpulse.product(invM2))
        body2.setAngularVelocity(body2.getAngularVelocity() + invI2 * r2.cross(stepImpulse))
    }

    override fun solvePositionConstraints(step: TimeStep?, settings: Settings?): Boolean = true

    private fun getAngularError(): Double {
        var error = body2.getTransform().getRotationAngle() - body1.getTransform().getRotationAngle() - angularTarget
        if (error < -PI) error += Geometry.TWO_PI
        if (error > PI) error -= Geometry.TWO_PI
        return error
    }

    override fun getReactionForce(invdt: Double): Vector2 = linearImpulse.product(invdt)
    override fun getReactionTorque(invdt: Double): Double = angularImpulse * invdt
    override fun shift(shift: Vector2) {}

    open fun getLinearTarget(): Vector2 = linearTarget
    open fun setLinearTarget(target: Vector2?) {
        if (!target!!.equals(linearTarget)) {
            body1.setAtRest(false)
            body2.setAtRest(false)
            linearTarget.set(target)
        }
    }
    open fun setLinearTarget(x: Double, y: Double) {
        if (!linearTarget.equals(x, y)) {
            body1.setAtRest(false)
            body2.setAtRest(false)
            linearTarget.set(x, y)
        }
    }
    open fun getAngularTarget(): Double = angularTarget
    open fun setAngularTarget(target: Double) {
        if (target != angularTarget) {
            body1.setAtRest(false)
            body2.setAtRest(false)
            angularTarget = target
        }
    }
    open fun getCorrectionFactor(): Double = correctionFactor
    open fun setCorrectionFactor(value: Double) {
        if (value < 0.0) throw ValueOutOfRangeException("correctionFactor", value, ValueOutOfRangeException.MUST_BE_GREATER_THAN_OR_EQUAL_TO, 0.0)
        if (value > 1.0) throw ValueOutOfRangeException("correctionFactor", value, ValueOutOfRangeException.MUST_BE_LESS_THAN_OR_EQUAL_TO, 1.0)
        correctionFactor = value
    }
    open fun getMaximumTorque(): Double = maximumTorque
    open fun setMaximumTorque(value: Double) {
        if (value < 0.0) throw ValueOutOfRangeException("maximumTorque", value, ValueOutOfRangeException.MUST_BE_GREATER_THAN_OR_EQUAL_TO, 0.0)
        maximumTorque = value
    }
    open fun getMaximumForce(): Double = maximumForce
    open fun setMaximumForce(value: Double) {
        if (value < 0.0) throw ValueOutOfRangeException("maximumForce", value, ValueOutOfRangeException.MUST_BE_GREATER_THAN_OR_EQUAL_TO, 0.0)
        maximumForce = value
    }
}
