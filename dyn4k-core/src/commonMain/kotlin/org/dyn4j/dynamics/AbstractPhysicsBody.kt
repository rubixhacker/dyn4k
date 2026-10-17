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
package org.dyn4j.dynamics

import org.dyn4j.Epsilon
import org.dyn4j.collision.AbstractCollisionBody
import org.dyn4j.exception.ArgumentNullException
import org.dyn4j.exception.ValueOutOfRangeException
import org.dyn4j.geometry.AABB
import org.dyn4j.geometry.Convex
import org.dyn4j.geometry.Geometry
import org.dyn4j.geometry.Interval
import org.dyn4j.geometry.Mass
import org.dyn4j.geometry.MassType
import org.dyn4j.geometry.Transform
import org.dyn4j.geometry.Vector2
import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.sqrt
import kotlin.jvm.JvmField

abstract class AbstractPhysicsBody : AbstractCollisionBody<BodyFixture>, PhysicsBody {
    @JvmField protected var mass = Mass()
    @JvmField protected val linearVelocity = Vector2()
    @JvmField protected var angularVelocity = 0.0
    @JvmField protected var linearDamping = PhysicsBody.DEFAULT_LINEAR_DAMPING
    @JvmField protected var angularDamping = PhysicsBody.DEFAULT_ANGULAR_DAMPING
    @JvmField protected var gravityScale = 1.0
    @JvmField protected var bullet = false
    @JvmField protected var atRestDetectionEnabled = true
    @JvmField protected var atRest = false
    @JvmField protected var atRestTime = 0.0
    @JvmField protected val force = Vector2()
    @JvmField protected var torque = 0.0
    @JvmField protected val forces: MutableList<Force> = ArrayList(5)
    @JvmField protected val torques: MutableList<Torque> = ArrayList(5)

    constructor() : super()
    constructor(fixtureCount: Int) : super(fixtureCount)
    protected constructor(body: AbstractPhysicsBody) : super(body) {
        radius = body.radius
        mass = body.mass.copy()
        linearVelocity.set(body.linearVelocity)
        angularVelocity = body.angularVelocity
        force.set(body.force)
        torque = body.torque
        atRestDetectionEnabled = body.atRestDetectionEnabled
        atRest = body.atRest
        bullet = body.bullet
        atRestTime = body.atRestTime
        linearDamping = body.linearDamping
        angularDamping = body.angularDamping
        gravityScale = body.gravityScale
        for (item in body.forces) forces.add(item.copy())
        for (item in body.torques) torques.add(item.copy())
    }

    override fun addFixture(convex: Convex): BodyFixture =
        addFixture(convex, BodyFixture.DEFAULT_DENSITY, BodyFixture.DEFAULT_FRICTION, BodyFixture.DEFAULT_RESTITUTION)
    override fun addFixture(convex: Convex, density: Double): BodyFixture =
        addFixture(convex, density, BodyFixture.DEFAULT_FRICTION, BodyFixture.DEFAULT_RESTITUTION)
    override fun addFixture(convex: Convex?, density: Double, friction: Double, restitution: Double): BodyFixture {
        val fixture = BodyFixture(convex ?: throw ArgumentNullException("convex"))
        fixture.setDensity(density)
        fixture.setFriction(friction)
        fixture.setRestitution(restitution)
        super.addFixture(fixture)
        setAtRest(false)
        return fixture
    }
    override fun removeAllFixtures(): List<BodyFixture> = super.removeAllFixtures().also { if (it.isNotEmpty()) setAtRest(false) }
    override fun removeFixture(fixture: BodyFixture?): Boolean = super.removeFixture(fixture).also { if (it) setAtRest(false) }
    override fun removeFixture(index: Int): BodyFixture = super.removeFixture(index).also { setAtRest(false) }
    override fun removeFixture(point: Vector2?): BodyFixture? = super.removeFixture(point).also { if (it != null) setAtRest(false) }
    override fun removeFixtures(point: Vector2?): List<BodyFixture> = super.removeFixtures(point).also { if (it.isNotEmpty()) setAtRest(false) }
    override fun setEnabled(enabled: Boolean) { if (enabled != this.enabled && enabled) setAtRest(false); super.setEnabled(enabled) }

    override fun updateMass(): AbstractPhysicsBody = setMass(mass.getType())
    override fun setMass(type: MassType?): AbstractPhysicsBody {
        val nextType = type ?: mass.getType()
        val count = fixtures.size
        mass = when (count) {
            0 -> Mass()
            1 -> fixtures[0].createMass()
            else -> {
                val masses = ArrayList<Mass?>(count)
                for (fixture in fixtures) if (fixture.rawDensity() > 0.0) masses.add(fixture.createMass())
                if (masses.isEmpty()) Mass() else Mass.create(masses)
            }
        }
        mass.setType(nextType)
        setRotationDiscRadius(mass.getCenter())
        setAtRest(false)
        return this
    }
    override fun setMass(mass: Mass?): AbstractPhysicsBody {
        this.mass = mass ?: throw ArgumentNullException("mass")
        setRotationDiscRadius(this.mass.getCenter())
        setAtRest(false)
        return this
    }
    override fun setMassType(type: MassType?): AbstractPhysicsBody {
        val nextType = type ?: throw ArgumentNullException("type")
        if (nextType != mass.getType()) setAtRest(false)
        mass.setType(nextType)
        return this
    }
    override fun getMass() = mass

    override fun applyForce(force: Vector2?): AbstractPhysicsBody {
        val value = force ?: throw ArgumentNullException("force")
        if (mass.getMass() == 0.0) return this
        forces.add(Force(value))
        setAtRest(false)
        return this
    }
    override fun applyForce(force: Force?): AbstractPhysicsBody {
        val value = force ?: throw ArgumentNullException("force")
        if (mass.getMass() == 0.0) return this
        forces.add(value)
        setAtRest(false)
        return this
    }
    override fun applyTorque(torque: Double): AbstractPhysicsBody {
        if (mass.getInertia() == 0.0) return this
        torques.add(Torque(torque))
        setAtRest(false)
        return this
    }
    override fun applyTorque(torque: Torque?): AbstractPhysicsBody {
        val value = torque ?: throw ArgumentNullException("torque")
        if (mass.getInertia() == 0.0) return this
        torques.add(value)
        setAtRest(false)
        return this
    }
    override fun applyForce(force: Vector2?, point: Vector2?): AbstractPhysicsBody {
        val value = force ?: throw ArgumentNullException("force")
        val position = point ?: throw ArgumentNullException("point")
        var awaken = false
        if (mass.getMass() != 0.0) { forces.add(Force(value)); awaken = true }
        if (mass.getInertia() != 0.0) {
            val r = getWorldCenter().to(position)
            if (!r.isZero()) { torques.add(Torque(r.cross(value))); awaken = true }
        }
        if (awaken) setAtRest(false)
        return this
    }
    override fun applyImpulse(impulse: Vector2?): AbstractPhysicsBody {
        val value = impulse ?: throw ArgumentNullException("impulse")
        val inverseMass = mass.getInverseMass()
        if (inverseMass == 0.0) return this
        linearVelocity.add(value.x * inverseMass, value.y * inverseMass)
        setAtRest(false)
        return this
    }
    override fun applyImpulse(impulse: Double): AbstractPhysicsBody {
        val inverseInertia = mass.getInverseInertia()
        if (inverseInertia == 0.0) return this
        angularVelocity += inverseInertia * impulse
        setAtRest(false)
        return this
    }
    override fun applyImpulse(impulse: Vector2?, point: Vector2?): AbstractPhysicsBody {
        val value = impulse ?: throw ArgumentNullException("impulse")
        val position = point ?: throw ArgumentNullException("point")
        val inverseMass = mass.getInverseMass()
        val inverseInertia = mass.getInverseInertia()
        var awaken = false
        if (inverseMass != 0.0) { linearVelocity.add(value.x * inverseMass, value.y * inverseMass); awaken = true }
        if (inverseInertia != 0.0) { angularVelocity += inverseInertia * getWorldCenter().to(position).cross(value); awaken = true }
        if (awaken) setAtRest(false)
        return this
    }
    override fun clearForce() { force.zero() }
    override fun clearAccumulatedForce() { forces.clear() }
    override fun clearTorque() { torque = 0.0 }
    override fun clearAccumulatedTorque() { torques.clear() }
    protected open fun accumulate(elapsedTime: Double) {
        force.zero()
        val forceIterator = forces.iterator()
        while (forceIterator.hasNext()) {
            val item = forceIterator.next()
            force.add(item.rawForce())
            if (item.isComplete(elapsedTime)) forceIterator.remove()
        }
        torque = 0.0
        val torqueIterator = torques.iterator()
        while (torqueIterator.hasNext()) {
            val item = torqueIterator.next()
            torque += item.rawTorque()
            if (item.isComplete(elapsedTime)) torqueIterator.remove()
        }
    }
    override fun integrateVelocity(gravity: Vector2?, timestep: TimeStep?, settings: Settings?) {
        if (mass.getType() == MassType.INFINITE) return
        val elapsedTime = timestep!!.rawDeltaTime()
        accumulate(elapsedTime)
        val bodyMass = mass.getMass()
        val inverseMass = mass.getInverseMass()
        val inverseInertia = mass.getInverseInertia()
        if (inverseMass > Epsilon.E) {
            linearVelocity.x += elapsedTime * inverseMass * (gravity!!.x * gravityScale * bodyMass + force.x)
            linearVelocity.y += elapsedTime * inverseMass * (gravity.y * gravityScale * bodyMass + force.y)
        }
        if (inverseInertia > Epsilon.E) angularVelocity += inverseInertia * torque * elapsedTime
        if (linearDamping != 0.0) {
            val linear = Interval.clamp(1.0 - elapsedTime * linearDamping, 0.0, 1.0)
            linearVelocity.x *= linear
            linearVelocity.y *= linear
        }
        val angular = Interval.clamp(1.0 - elapsedTime * angularDamping, 0.0, 1.0)
        angularVelocity *= angular
    }
    override fun integratePosition(timestep: TimeStep?, settings: Settings?) {
        val elapsedTime = timestep!!.rawDeltaTime()
        val maxTranslation = settings!!.getMaximumTranslation()
        val maxTranslationSquared = settings.getMaximumTranslationSquared()
        val maxRotation = settings.getMaximumRotation()
        if (isStatic()) return
        var translationX = linearVelocity.x * elapsedTime
        var translationY = linearVelocity.y * elapsedTime
        val magnitudeSquared = translationX * translationX + translationY * translationY
        if (magnitudeSquared > maxTranslationSquared) {
            val ratio = maxTranslation / sqrt(magnitudeSquared)
            linearVelocity.multiply(ratio)
            translationX *= ratio
            translationY *= ratio
        }
        var rotation = angularVelocity * elapsedTime
        if (rotation > maxRotation) {
            val ratio = maxRotation / abs(rotation)
            angularVelocity *= ratio
            rotation *= ratio
        }
        translate(translationX, translationY)
        rotateAboutCenter(rotation)
    }
    override fun updateAtRestTime(timestep: TimeStep?, settings: Settings?): Double {
        if (atRestDetectionEnabled) {
            if (isStatic()) return -1.0
            if (linearVelocity.getMagnitudeSquared() > settings!!.getMaximumAtRestLinearVelocitySquared() ||
                abs(angularVelocity) > settings.getMaximumAtRestAngularVelocity()) atRestTime = 0.0
            else atRestTime += timestep!!.rawDeltaTime()
        } else atRestTime = 0.0
        return atRestTime
    }
    override fun isStatic() = mass.getType() == MassType.INFINITE && abs(linearVelocity.x) <= Epsilon.E &&
        abs(linearVelocity.y) <= Epsilon.E && abs(angularVelocity) <= Epsilon.E
    override fun isKinematic() = mass.getType() == MassType.INFINITE &&
        (abs(linearVelocity.x) > Epsilon.E || abs(linearVelocity.y) > Epsilon.E || abs(angularVelocity) > Epsilon.E)
    override fun isDynamic() = mass.getType() != MassType.INFINITE
    override fun setAtRestDetectionEnabled(flag: Boolean) { atRestDetectionEnabled = flag; if (!flag) setAtRest(false) }
    override fun isAtRestDetectionEnabled() = atRestDetectionEnabled
    override fun isAtRest() = atRest
    override fun setAtRest(flag: Boolean) {
        if (flag) {
            atRest = true
            linearVelocity.zero()
            angularVelocity = 0.0
            forces.clear()
            torques.clear()
        } else if (atRest) {
            atRestTime = 0.0
            atRest = false
        }
    }
    override fun isBullet() = bullet
    override fun setBullet(flag: Boolean) { bullet = flag }
    override fun createSweptAABB() = AABB(0.0, 0.0, 0.0, 0.0).also { computeSweptAABB(transform0, transform, it) }
    override fun createSweptAABB(initialTransform: Transform?, finalTransform: Transform?) =
        AABB(0.0, 0.0, 0.0, 0.0).also { computeSweptAABB(initialTransform, finalTransform, it) }
    override fun computeSweptAABB(result: AABB) = computeSweptAABB(transform0, transform, result)
    override fun computeSweptAABB(initialTransform: Transform?, finalTransform: Transform?, result: AABB) {
        val count = fixtures.size
        if (count == 0) { result.zero(); return }
        val initialLocalCenter = getLocalCenter()
        val initial = initialTransform!!
        val initialCenter = initial.getTransformed(initialLocalCenter)
        val finalLocalCenter = getLocalCenter()
        val final = finalTransform!!
        val finalCenter = final.getTransformed(finalLocalCenter)
        if (initial.getCost() != final.getCost() ||
            initial.getSint() != final.getSint() || angularVelocity != 0.0 || count > 1) {
            AABB.setFromPoints(initialCenter, finalCenter, result)
            result.expand(radius * 2.0)
        } else if (initial.getTranslationX() == final.getTranslationX() &&
            initial.getTranslationY() == final.getTranslationY()) {
            fixtures[0].getShape().computeAABB(initial, result)
        } else {
            fixtures[0].getShape().computeAABB(initial, result)
            val next = result.copy()
            next.translate(finalCenter.x - initialCenter.x, finalCenter.y - initialCenter.y)
            result.union(next)
        }
    }
    override fun getChangeInPosition() = transform.getTranslation().subtract(transform0.getTranslation())
    override fun getChangeInOrientation(): Double {
        var initial = transform0.getRotationAngle()
        var final = transform.getRotationAngle()
        if (initial == final) return 0.0
        val twoPi = Geometry.TWO_PI
        if (initial < 0.0) initial += twoPi
        if (final < 0.0) final += twoPi
        var result = final - initial
        if (angularVelocity == 0.0) return when {
            result > PI -> result - twoPi
            result < -PI -> result + twoPi
            else -> result
        }
        if (final < initial && angularVelocity > 0.0) result += twoPi
        if (final > initial && angularVelocity < 0.0) result -= twoPi
        return result
    }
    override fun getLocalCenter() = mass.getCenter()
    override fun getWorldCenter() = transform.getTransformed(mass.getCenter())
    override fun getLinearVelocity() = linearVelocity
    override fun getLinearVelocity(point: Vector2?): Vector2 = getWorldCenter().to(point!!).cross(angularVelocity).add(linearVelocity)
    override fun setLinearVelocity(velocity: Vector2?) { linearVelocity.set(velocity ?: throw ArgumentNullException("velocity")) }
    override fun setLinearVelocity(x: Double, y: Double) { linearVelocity.x = x; linearVelocity.y = y }
    override fun getAngularVelocity() = angularVelocity
    override fun setAngularVelocity(angularVelocity: Double) { this.angularVelocity = angularVelocity }
    override fun getForce() = force.copy()
    override fun getAccumulatedForce(): Vector2 {
        val result = Vector2()
        for (item in forces) result.add(item.rawForce())
        return result
    }
    override fun getTorque() = torque
    override fun getAccumulatedTorque(): Double {
        var result = 0.0
        for (item in torques) result += item.rawTorque()
        return result
    }
    override fun getLinearDamping() = linearDamping
    override fun setLinearDamping(linearDamping: Double) {
        if (linearDamping < 0.0) throw ValueOutOfRangeException("linearDamping", linearDamping, ValueOutOfRangeException.MUST_BE_GREATER_THAN_OR_EQUAL_TO, 0.0)
        if (linearDamping != this.linearDamping) setAtRest(false)
        this.linearDamping = linearDamping
    }
    override fun getAngularDamping() = angularDamping
    override fun setAngularDamping(angularDamping: Double) {
        if (angularDamping < 0.0) throw ValueOutOfRangeException("angularDamping", angularDamping, ValueOutOfRangeException.MUST_BE_GREATER_THAN_OR_EQUAL_TO, 0.0)
        if (angularDamping != this.angularDamping) setAtRest(false)
        this.angularDamping = angularDamping
    }
    override fun getGravityScale() = gravityScale
    override fun setGravityScale(scale: Double) { if (scale != gravityScale) setAtRest(false); gravityScale = scale }
    override fun toString() = "Body[HashCode=${hashCode()}|Fixtures={${fixtures.joinToString(",")}}|InitialTransform=$transform0|Transform=$transform|RotationDiscRadius=$radius|Mass=$mass|LinearVelocity=$linearVelocity|AngularVelocity=$angularVelocity|Force=$force|Torque=$torque|AccumulatedForce=${getAccumulatedForce()}|AccumulatedTorque=${getAccumulatedTorque()}|IsAtRestDetectionEnabled=$atRestDetectionEnabled|IsAtRest=$atRest|IsActive=$enabled|IsBullet=$bullet|LinearDamping=$linearDamping|AngularDamping$angularDamping|GravityScale=$gravityScale]"
}
