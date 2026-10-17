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

import org.dyn4j.Epsilon
import org.dyn4j.dynamics.PhysicsBody
import org.dyn4j.dynamics.Settings
import org.dyn4j.dynamics.TimeStep
import org.dyn4j.exception.ArgumentNullException
import org.dyn4j.exception.ValueOutOfRangeException
import org.dyn4j.geometry.Interval
import org.dyn4j.geometry.Matrix22
import org.dyn4j.geometry.Vector2

open class FrictionJoint<T : PhysicsBody> : AbstractPairedBodyJoint<T> {
    @kotlin.jvm.JvmField protected val localAnchor1: Vector2
    @kotlin.jvm.JvmField protected val localAnchor2: Vector2
    @kotlin.jvm.JvmField protected var maximumForce: Double
    @kotlin.jvm.JvmField protected var maximumTorque: Double
    @kotlin.jvm.JvmField internal val K: Matrix22
    @kotlin.jvm.JvmField internal var angularMass: Double
    @kotlin.jvm.JvmField internal val linearImpulse: Vector2
    @kotlin.jvm.JvmField internal var angularImpulse: Double

    constructor(body1: T?, body2: T?, anchor: Vector2?) : super(body1, body2) {
        if (anchor == null) throw ArgumentNullException("anchor")
        localAnchor1 = this.body1.getLocalPoint(anchor)
        localAnchor2 = this.body2.getLocalPoint(anchor)
        maximumForce = 10.0
        maximumTorque = 0.25
        K = Matrix22()
        angularMass = 0.0
        linearImpulse = Vector2()
        angularImpulse = 0.0
    }

    protected constructor(joint: FrictionJoint<T>) : this(joint, null, null)

    protected constructor(joint: FrictionJoint<T>, body1: T?, body2: T?) : super(joint, body1, body2) {
        localAnchor1 = joint.localAnchor1.copy()
        localAnchor2 = joint.localAnchor2.copy()
        maximumForce = joint.maximumForce
        maximumTorque = joint.maximumTorque
        angularMass = joint.angularMass
        K = joint.K.copy()
        angularImpulse = joint.angularImpulse
        linearImpulse = joint.linearImpulse.copy()
    }

    override fun copy(): FrictionJoint<T> = FrictionJoint(this)
    override fun copy(body1: T?, body2: T?): FrictionJoint<T> = FrictionJoint(this, body1, body2)

    override fun toString(): String = "FrictionJoint[${super.toString()}|Anchor=${getAnchor1()}|MaximumForce=$maximumForce|MaximumTorque=$maximumTorque]"

    override fun initializeConstraints(step: TimeStep?, settings: Settings?) {
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

        K.m00 = invM1 + invM2 + r1.y * r1.y * invI1 + r2.y * r2.y * invI2
        K.m01 = -invI1 * r1.x * r1.y - invI2 * r2.x * r2.y
        K.m10 = K.m01
        K.m11 = invM1 + invM2 + r1.x * r1.x * invI1 + r2.x * r2.x * invI2
        angularMass = invI1 + invI2
        angularMass = if (angularMass > Epsilon.E) 1.0 / angularMass else 0.0

        if (settings!!.isWarmStartingEnabled()) {
            linearImpulse.multiply(step!!.getDeltaTimeRatio())
            angularImpulse *= step.getDeltaTimeRatio()
            body1.getLinearVelocity().add(linearImpulse.product(invM1))
            body1.setAngularVelocity(body1.getAngularVelocity() + invI1 * (r1.cross(linearImpulse) + angularImpulse))
            body2.getLinearVelocity().subtract(linearImpulse.product(invM2))
            body2.setAngularVelocity(body2.getAngularVelocity() - invI2 * (r2.cross(linearImpulse) + angularImpulse))
        } else {
            linearImpulse.zero()
            angularImpulse = 0.0
        }
    }

    override fun solveVelocityConstraints(step: TimeStep?, settings: Settings?) {
        val t1 = body1.getTransform()
        val t2 = body2.getTransform()
        val m1 = body1.getMass()
        val m2 = body2.getMass()
        val invM1 = m1.getInverseMass()
        val invM2 = m2.getInverseMass()
        val invI1 = m1.getInverseInertia()
        val invI2 = m2.getInverseInertia()

        val c = body1.getAngularVelocity() - body2.getAngularVelocity()
        var stepImpulseAngular = angularMass * -c
        val oldAngularImpulse = angularImpulse
        val maxAngularImpulse = maximumTorque * step!!.getDeltaTime()
        angularImpulse = Interval.clamp(angularImpulse + stepImpulseAngular, -maxAngularImpulse, maxAngularImpulse)
        stepImpulseAngular = angularImpulse - oldAngularImpulse
        body1.setAngularVelocity(body1.getAngularVelocity() + invI1 * stepImpulseAngular)
        body2.setAngularVelocity(body2.getAngularVelocity() - invI2 * stepImpulseAngular)

        val r1 = t1.getTransformedR(body1.getLocalCenter().to(localAnchor1))
        val r2 = t2.getTransformedR(body2.getLocalCenter().to(localAnchor2))
        val v1 = body1.getLinearVelocity().sum(r1.cross(body1.getAngularVelocity()))
        val v2 = body2.getLinearVelocity().sum(r2.cross(body2.getAngularVelocity()))
        val pivotV = v1.subtract(v2)
        val oldLinearImpulse = linearImpulse.copy()
        linearImpulse.add(K.solve(pivotV.negate()))
        val maxLinearImpulse = maximumForce * step.getDeltaTime()
        if (linearImpulse.getMagnitudeSquared() > maxLinearImpulse * maxLinearImpulse) {
            linearImpulse.normalize()
            linearImpulse.multiply(maxLinearImpulse)
        }
        val stepImpulseLinear = linearImpulse.difference(oldLinearImpulse)
        body1.getLinearVelocity().add(stepImpulseLinear.product(invM1))
        body1.setAngularVelocity(body1.getAngularVelocity() + invI1 * r1.cross(stepImpulseLinear))
        body2.getLinearVelocity().subtract(stepImpulseLinear.product(invM2))
        body2.setAngularVelocity(body2.getAngularVelocity() - invI2 * r2.cross(stepImpulseLinear))
    }

    override fun solvePositionConstraints(step: TimeStep?, settings: Settings?): Boolean = true
    open fun getAnchor1(): Vector2 = body1.getWorldPoint(localAnchor1)
    open fun getAnchor2(): Vector2 = body2.getWorldPoint(localAnchor2)
    override fun getReactionForce(invdt: Double): Vector2 = linearImpulse.product(invdt)
    override fun getReactionTorque(invdt: Double): Double = angularImpulse * invdt
    override fun shift(shift: Vector2) {}
    open fun getMaximumTorque(): Double = maximumTorque
    open fun setMaximumTorque(maximumTorque: Double) {
        if (maximumTorque < 0.0) throw ValueOutOfRangeException("maximumTorque", maximumTorque, ValueOutOfRangeException.MUST_BE_GREATER_THAN_OR_EQUAL_TO, 0.0)
        this.maximumTorque = maximumTorque
    }
    open fun getMaximumForce(): Double = maximumForce
    open fun setMaximumForce(maximumForce: Double) {
        if (maximumForce < 0.0) throw ValueOutOfRangeException("maximumForce", maximumForce, ValueOutOfRangeException.MUST_BE_GREATER_THAN_OR_EQUAL_TO, 0.0)
        this.maximumForce = maximumForce
    }
}
