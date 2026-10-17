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
import org.dyn4j.Epsilon
import org.dyn4j.dynamics.PhysicsBody
import org.dyn4j.dynamics.Settings
import org.dyn4j.dynamics.TimeStep
import org.dyn4j.exception.ArgumentNullException
import org.dyn4j.exception.ValueOutOfRangeException
import org.dyn4j.geometry.Vector2

open class PulleyJoint<T : PhysicsBody> : AbstractPairedBodyJoint<T> {
    @kotlin.jvm.JvmField protected val pulleyAnchor1: Vector2
    @kotlin.jvm.JvmField protected val pulleyAnchor2: Vector2
    @kotlin.jvm.JvmField protected val localAnchor1: Vector2
    @kotlin.jvm.JvmField protected val localAnchor2: Vector2
    @kotlin.jvm.JvmField protected var ratio = 1.0
    @kotlin.jvm.JvmField protected var slackEnabled = false
    @kotlin.jvm.JvmField internal var overLength = false
    @kotlin.jvm.JvmField internal var length: Double
    @kotlin.jvm.JvmField internal val n1 = Vector2()
    @kotlin.jvm.JvmField internal val n2 = Vector2()
    @kotlin.jvm.JvmField internal var invK = 0.0
    @kotlin.jvm.JvmField internal var impulse = 0.0

    constructor(body1: T, body2: T, pulleyAnchor1: Vector2?, pulleyAnchor2: Vector2?, bodyAnchor1: Vector2?, bodyAnchor2: Vector2?) : super(body1, body2) {
        if (pulleyAnchor1 == null) throw ArgumentNullException("pulleyAnchor1")
        if (pulleyAnchor2 == null) throw ArgumentNullException("pulleyAnchor2")
        if (bodyAnchor1 == null) throw ArgumentNullException("bodyAnchor1")
        if (bodyAnchor2 == null) throw ArgumentNullException("bodyAnchor2")
        this.pulleyAnchor1 = pulleyAnchor1.copy()
        this.pulleyAnchor2 = pulleyAnchor2.copy()
        localAnchor1 = body1.getLocalPoint(bodyAnchor1)
        localAnchor2 = body2.getLocalPoint(bodyAnchor2)
        length = bodyAnchor1.distance(pulleyAnchor1) + bodyAnchor2.distance(pulleyAnchor2)
    }
    protected constructor(joint: PulleyJoint<T>) : this(joint, null, null)
    protected constructor(joint: PulleyJoint<T>, body1: T?, body2: T?) : super(joint, body1, body2) {
        pulleyAnchor1 = joint.pulleyAnchor1.copy()
        pulleyAnchor2 = joint.pulleyAnchor2.copy()
        localAnchor1 = joint.localAnchor1.copy()
        localAnchor2 = joint.localAnchor2.copy()
        ratio = joint.ratio
        slackEnabled = joint.slackEnabled
        invK = joint.invK
        length = joint.length
        n1.set(joint.n1)
        n2.set(joint.n2)
        overLength = joint.overLength
        impulse = joint.impulse
    }
    override fun copy() = PulleyJoint(this)
    override fun copy(body1: T?, body2: T?) = PulleyJoint(this, body1, body2)
    override fun toString() = "PulleyJoint[${super.toString()}|PulleyAnchor1=$pulleyAnchor1|PulleyAnchor2=$pulleyAnchor2|Anchor1=${getAnchor1()}|Anchor2=${getAnchor2()}|Ratio=$ratio|Length=$length|SlackEnabled=$slackEnabled]"

    override fun initializeConstraints(step: TimeStep?, settings: Settings?) {
        val cfg = settings!!
        val m1 = body1.getMass()
        val m2 = body2.getMass()
        val invM1 = m1.getInverseMass()
        val invM2 = m2.getInverseMass()
        val invI1 = m1.getInverseInertia()
        val invI2 = m2.getInverseInertia()
        val r1 = body1.getTransform().getTransformedR(body1.getLocalCenter().to(localAnchor1))
        val r2 = body2.getTransform().getTransformedR(body2.getLocalCenter().to(localAnchor2))
        val p1 = r1.sum(body1.getWorldCenter())
        val p2 = r2.sum(body2.getWorldCenter())
        n1.x = p1.x - pulleyAnchor1.x
        n1.y = p1.y - pulleyAnchor1.y
        n2.x = p2.x - pulleyAnchor2.x
        n2.y = p2.y - pulleyAnchor2.y
        val l1 = n1.normalize()
        val l2 = n2.normalize()
        val l = l1 + l2
        if (l > length || !slackEnabled) {
            overLength = true
            if (l1 <= 10.0 * cfg.getLinearTolerance()) n1.zero()
            if (l2 <= 10.0 * cfg.getLinearTolerance()) n2.zero()
            val cr1 = r1.cross(n1)
            val cr2 = r2.cross(n2)
            val pm1 = invM1 + invI1 * cr1 * cr1
            val pm2 = invM2 + invI2 * cr2 * cr2
            invK = pm1 + ratio * ratio * pm2
            invK = if (invK > Epsilon.E) 1.0 / invK else 0.0
            if (cfg.isWarmStartingEnabled()) {
                impulse *= step!!.getDeltaTimeRatio()
                val j1 = n1.product(-impulse)
                val j2 = n2.product(-ratio * impulse)
                body1.getLinearVelocity().add(j1.product(invM1))
                body1.setAngularVelocity(body1.getAngularVelocity() + invI1 * r1.cross(j1))
                body2.getLinearVelocity().add(j2.product(invM2))
                body2.setAngularVelocity(body2.getAngularVelocity() + invI2 * r2.cross(j2))
            } else impulse = 0.0
        } else {
            impulse = 0.0
            overLength = false
        }
    }

    override fun solveVelocityConstraints(step: TimeStep?, settings: Settings?) {
        if (overLength || !slackEnabled) {
            val m1 = body1.getMass()
            val m2 = body2.getMass()
            val invM1 = m1.getInverseMass()
            val invM2 = m2.getInverseMass()
            val invI1 = m1.getInverseInertia()
            val invI2 = m2.getInverseInertia()
            val r1 = body1.getTransform().getTransformedR(body1.getLocalCenter().to(localAnchor1))
            val r2 = body2.getTransform().getTransformedR(body2.getLocalCenter().to(localAnchor2))
            val v1 = body1.getLinearVelocity().sum(r1.cross(body1.getAngularVelocity()))
            val v2 = body2.getLinearVelocity().sum(r2.cross(body2.getAngularVelocity()))
            val c = -n1.dot(v1) - ratio * n2.dot(v2)
            val p = -invK * c
            impulse += p
            val j1 = n1.product(-p)
            val j2 = n2.product(-p * ratio)
            body1.getLinearVelocity().add(j1.product(invM1))
            body1.setAngularVelocity(body1.getAngularVelocity() + invI1 * r1.cross(j1))
            body2.getLinearVelocity().add(j2.product(invM2))
            body2.setAngularVelocity(body2.getAngularVelocity() + invI2 * r2.cross(j2))
        }
    }

    override fun solvePositionConstraints(step: TimeStep?, settings: Settings?): Boolean {
        if (overLength || !slackEnabled) {
            val tolerance = settings!!.getLinearTolerance()
            val m1 = body1.getMass()
            val m2 = body2.getMass()
            val invM1 = m1.getInverseMass()
            val invM2 = m2.getInverseMass()
            val invI1 = m1.getInverseInertia()
            val invI2 = m2.getInverseInertia()
            val r1 = body1.getTransform().getTransformedR(body1.getLocalCenter().to(localAnchor1))
            val r2 = body2.getTransform().getTransformedR(body2.getLocalCenter().to(localAnchor2))
            val p1 = r1.sum(body1.getWorldCenter())
            val p2 = r2.sum(body2.getWorldCenter())
            val normal1 = pulleyAnchor1.to(p1)
            val normal2 = pulleyAnchor2.to(p2)
            val l1 = normal1.normalize()
            val l2 = normal2.normalize()
            if (l1 <= 10.0 * tolerance) normal1.zero()
            if (l2 <= 10.0 * tolerance) normal2.zero()
            val cr1 = r1.cross(normal1)
            val cr2 = r2.cross(normal2)
            val pm1 = invM1 + invI1 * cr1 * cr1
            val pm2 = invM2 + invI2 * cr2 * cr2
            invK = pm1 + pm2
            invK = if (invK > Epsilon.E) 1.0 / invK else 0.0
            val c = length - l1 - l2
            val p = -invK * c
            val j1 = normal1.product(-p)
            val j2 = normal2.product(-p)
            body1.translate(j1.x * invM1, j1.y * invM1)
            body1.rotateAboutCenter(r1.cross(j1) * invI1)
            body2.translate(j2.x * invM2, j2.y * invM2)
            body2.rotateAboutCenter(r2.cross(j2) * invI2)
            return abs(c) < tolerance
        }
        return true
    }

    open fun getAnchor1() = body1.getWorldPoint(localAnchor1)
    open fun getAnchor2() = body2.getWorldPoint(localAnchor2)
    override fun getReactionForce(invdt: Double) = n2.product(impulse * invdt)
    override fun getReactionTorque(invdt: Double) = 0.0
    override fun shift(shift: Vector2) { pulleyAnchor1.add(shift); pulleyAnchor2.add(shift) }
    open fun getPulleyAnchor1() = pulleyAnchor1
    open fun getPulleyAnchor2() = pulleyAnchor2
    open fun getLength() = length
    open fun getCurrentLength() = getCurrentLength1() + getCurrentLength2()
    open fun setLength(length: Double) {
        if (length < 0.0) throw ValueOutOfRangeException("length", length, ValueOutOfRangeException.MUST_BE_GREATER_THAN_OR_EQUAL_TO, 0.0)
        if (this.length != length) { this.length = length; wakeBodies() }
    }
    open fun getCurrentLength1() = pulleyAnchor1.distance(body1.getWorldPoint(localAnchor1))
    open fun getCurrentLength2() = pulleyAnchor2.distance(body2.getWorldPoint(localAnchor2))
    open fun getRatio() = ratio
    open fun setRatio(ratio: Double) {
        if (ratio <= 0.0) throw ValueOutOfRangeException("ratio", ratio, ValueOutOfRangeException.MUST_BE_GREATER_THAN, 0.0)
        if (this.ratio != ratio) { this.ratio = ratio; wakeBodies() }
    }
    open fun isSlackEnabled() = slackEnabled
    open fun setSlackEnabled(flag: Boolean) {
        if (slackEnabled != flag) { slackEnabled = flag; wakeBodies() }
    }
    private fun wakeBodies() { body1.setAtRest(false); body2.setAtRest(false) }
}
