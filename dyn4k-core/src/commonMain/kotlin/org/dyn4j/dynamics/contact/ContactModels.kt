/*
 * Copyright (c) 2010-2022 William Bittle  http://www.dyn4j.org/
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
package org.dyn4j.dynamics.contact

import kotlin.jvm.JvmField
import kotlin.jvm.JvmWildcard
import org.dyn4j.collision.CollisionBody
import org.dyn4j.collision.CollisionItem
import org.dyn4j.collision.CollisionPair
import org.dyn4j.collision.continuous.TimeOfImpact
import org.dyn4j.collision.manifold.Manifold
import org.dyn4j.collision.manifold.ManifoldPointId
import org.dyn4j.dynamics.BodyFixture
import org.dyn4j.dynamics.PhysicsBody
import org.dyn4j.dynamics.Settings
import org.dyn4j.dynamics.TimeStep
import org.dyn4j.exception.ValueOutOfRangeException
import org.dyn4j.geometry.Matrix22
import org.dyn4j.geometry.Interval
import org.dyn4j.geometry.Shiftable
import org.dyn4j.geometry.Vector2

interface Contact {
    fun getId(): ManifoldPointId
    fun getPoint(): Vector2
    fun getDepth(): Double
    fun isIgnored(): Boolean
}

interface SolvedContact : Contact {
    fun getNormalImpulse(): Double
    fun getTangentialImpulse(): Double
    fun isSolved(): Boolean
}

interface ContactUpdateHandler {
    fun getFriction(fixture1: BodyFixture, fixture2: BodyFixture): Double
    fun getRestitution(fixture1: BodyFixture, fixture2: BodyFixture): Double
    fun getRestitutionVelocity(fixture1: BodyFixture, fixture2: BodyFixture): Double
    fun begin(contact: Contact)
    fun persist(oldContact: Contact, newContact: Contact)
    fun end(contact: Contact)
}

interface ContactConstraintSolver<T : PhysicsBody> {
    fun initialize(contactConstraints: List<ContactConstraint<T>>, step: TimeStep, settings: Settings)
    fun solveVelocityContraints(contactConstraints: List<ContactConstraint<T>>, step: TimeStep, settings: Settings)
    fun solvePositionContraints(contactConstraints: List<ContactConstraint<T>>, step: TimeStep, settings: Settings): Boolean
}

interface TimeOfImpactSolver<T : PhysicsBody> {
    fun solve(body1: T, body2: T, timeOfImpact: TimeOfImpact, settings: Settings)
}

open class ForceCollisionTimeOfImpactSolver<T : PhysicsBody> : TimeOfImpactSolver<T> {
    open override fun solve(body1: T, body2: T, timeOfImpact: TimeOfImpact, settings: Settings) {
        val mass1 = body1.getMass()
        val mass2 = body2.getMass()
        val inverseMass1 = mass1.getMass() * mass1.getInverseMass()
        val inverseMass2 = mass2.getMass() * mass2.getInverseMass()
        val separation = timeOfImpact.getSeparation()
        val distance = Interval.clamp(separation.getDistance() + settings.getLinearTolerance(),
            0.0, settings.getMaximumLinearCorrection())
        val sum = inverseMass1 + inverseMass2
        val impulse = if (sum > 0.0) distance / sum else 0.0
        val movement = separation.getNormal().product(impulse)
        body1.translate(movement.product(inverseMass1))
        body2.translate(movement.product(-inverseMass2))
    }
}

class SolvableContact(
    @JvmField val id: ManifoldPointId,
    @JvmField val p: Vector2,
    @JvmField val depth: Double,
    @JvmField val p1: Vector2,
    @JvmField val p2: Vector2
) : Contact, SolvedContact {
    @JvmField var r1: Vector2? = null
    @JvmField var r2: Vector2? = null
    @JvmField var jn = 0.0
    @JvmField var jt = 0.0
    @JvmField var jp = 0.0
    @JvmField var massN = 0.0
    @JvmField var massT = 0.0
    @JvmField var vb = 0.0
    @JvmField var ignored = false
    @JvmField var solved = false

    override fun getId() = id
    override fun getPoint() = p
    override fun getDepth() = depth
    override fun getNormalImpulse() = jn
    override fun getTangentialImpulse() = jt
    override fun isSolved() = solved
    override fun isIgnored() = ignored
    override fun toString() = "Contact[Id=$id|Point=$p|Depth=$depth|NormalImpulse=$jn|TangentImpulse=$jt]"
}

class ContactConstraint<T : PhysicsBody>(
    @JvmField protected val pair: CollisionPair<CollisionItem<T, BodyFixture>>
) : Shiftable {
    @JvmField protected val contacts: MutableList<SolvableContact> = ArrayList(2)
    @JvmField protected val contactsUnmodifiable: List<SolvableContact> = object : AbstractList<SolvableContact>() {
        override val size: Int get() = contacts.size
        override fun get(index: Int) = contacts[index]
    }
    @JvmField protected val normal = Vector2()
    @JvmField protected val tangent = Vector2()
    @JvmField protected var friction = BodyFixture.DEFAULT_FRICTION
    @JvmField protected var restitution = BodyFixture.DEFAULT_RESTITUTION
    @JvmField protected var restitutionVelocity = BodyFixture.DEFAULT_RESTITUTION_VELOCITY
    @JvmField protected var sensor = false
    @JvmField protected var tangentSpeed = 0.0
    @JvmField protected var enabled = true
    @JvmField protected var size = 0
    @JvmField internal var K: Matrix22? = null
    @JvmField internal var invK: Matrix22? = null

    fun update(manifold: Manifold, settings: Settings, handler: ContactUpdateHandler) {
        val maxWarmStartDistanceSquared = settings.getMaximumWarmStartDistanceSquared()
        val isWarmStartEnabled = settings.isWarmStartingEnabled()
        val body1 = getBody1()
        val body2 = getBody2()
        val fixture1 = getFixture1()
        val fixture2 = getFixture2()

        val manifoldNormal = manifold.getNormal()
        normal.x = manifoldNormal.x
        normal.y = manifoldNormal.y
        tangent.x = manifoldNormal.y
        tangent.y = -manifoldNormal.x
        friction = handler.getFriction(fixture1, fixture2)
        restitution = handler.getRestitution(fixture1, fixture2)
        restitutionVelocity = handler.getRestitutionVelocity(fixture1, fixture2)
        sensor = fixture1.isSensor() || fixture2.isSensor()

        val fresh = ArrayList<SolvableContact>(manifold.getPoints().size)
        for (point in manifold.getPoints()) {
            val worldPoint = point.getPoint()
            val next = SolvableContact(point.getId(), worldPoint, point.getDepth(),
                body1.getLocalPoint(worldPoint), body2.getLocalPoint(worldPoint))
            next.ignored = sensor || !enabled
            fresh.add(next)
            var found = false
            for (index in contacts.indices.reversed()) {
                val old = contacts[index]
                if ((next.id === ManifoldPointId.DISTANCE &&
                        next.p.distanceSquared(old.p) <= maxWarmStartDistanceSquared) || next.id == old.id) {
                    found = true
                    handler.persist(old, next)
                    if (isWarmStartEnabled) {
                        next.jn = old.jn
                        next.jt = old.jt
                        next.solved = old.solved
                    }
                    contacts.removeAt(index)
                    break
                }
            }
            if (!found) handler.begin(next)
        }
        for (index in contacts.indices.reversed()) handler.end(contacts[index])
        contacts.clear()
        contacts.addAll(fresh)
        size = contacts.size
    }

    override fun shift(shift: Vector2) {
        for (contact in contacts) contact.p.add(shift)
    }

    fun getNormal() = normal
    fun getTangent() = tangent
    fun getContacts(): List<@JvmWildcard SolvedContact> = javaReadOnlyContacts
    private val javaReadOnlyContacts: List<SolvedContact> get() = contactsUnmodifiable
    fun getCollisionPair() = pair
    fun getBody1(): T = pair.getFirst().getBody()!!
    fun getBody2(): T = pair.getSecond().getBody()!!
    fun getFixture1(): BodyFixture = pair.getFirst().getFixture()!!
    fun getFixture2(): BodyFixture = pair.getSecond().getFixture()!!
    fun getBody(body: CollisionBody<*>?): T? = when {
        body === getBody1() -> getBody1()
        body === getBody2() -> getBody2()
        else -> null
    }
    fun getFixture(body: CollisionBody<*>?): BodyFixture? = when {
        body === getBody1() -> getFixture1()
        body === getBody2() -> getFixture2()
        else -> null
    }
    fun getOtherBody(body: CollisionBody<*>?): T? = when {
        body === getBody1() -> getBody2()
        body === getBody2() -> getBody1()
        else -> null
    }
    fun getOtherFixture(body: CollisionBody<*>?): BodyFixture? = when {
        body === getBody1() -> getFixture2()
        body === getBody2() -> getFixture1()
        else -> null
    }
    fun getFriction() = friction
    @Deprecated("Set fixture friction instead")
    fun setFriction(value: Double) {
        if (value < 0.0) throw ValueOutOfRangeException("friction", value,
            ValueOutOfRangeException.MUST_BE_GREATER_THAN_OR_EQUAL_TO, 0.0)
        friction = value
    }
    fun getRestitution() = restitution
    @Deprecated("Set fixture restitution instead")
    fun setRestitution(value: Double) {
        if (value < 0.0) throw ValueOutOfRangeException("restitution", value,
            ValueOutOfRangeException.MUST_BE_GREATER_THAN_OR_EQUAL_TO, 0.0)
        restitution = value
    }
    fun getRestitutionVelocity() = restitutionVelocity
    @Deprecated("Set fixture restitution velocity instead")
    fun setRestitutionVelocity(value: Double) { restitutionVelocity = value }
    fun isSensor() = sensor
    @Deprecated("Set fixture sensor state instead")
    fun setSensor(flag: Boolean) { sensor = flag }
    fun getTangentSpeed() = tangentSpeed
    fun setTangentSpeed(speed: Double) { tangentSpeed = speed }
    fun setEnabled(flag: Boolean) { enabled = flag }
    fun isEnabled() = enabled

    internal fun solverContacts() = contacts
    internal fun solverSize() = size
    internal fun setSolverSize(value: Int) { size = value }
    internal fun solverNormal() = normal
    internal fun solverTangent() = tangent
    override fun toString() = "ContactConstraint[${super.toString()}" +
        "|Body1=${getBody1().hashCode()}|Fixture1=${getFixture1().hashCode()}" +
        "|Body2=${getBody2().hashCode()}|Fixture2=${getFixture2().hashCode()}" +
        "|Normal=$normal|Tangent=$tangent|Friction=$friction|Restitution=$restitution" +
        "|RestitutionVelocity=$restitutionVelocity|IsSensor=$sensor|TangentSpeed=$tangentSpeed" +
        "|Enabled=$enabled|Contacts={${contacts.joinToString(",")}}]"
}
