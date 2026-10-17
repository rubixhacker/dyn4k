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
package org.dyn4j.dynamics.contact

import kotlin.math.max
import kotlin.math.min
import org.dyn4j.Epsilon
import org.dyn4j.dynamics.PhysicsBody
import org.dyn4j.dynamics.Settings
import org.dyn4j.dynamics.TimeStep
import org.dyn4j.geometry.Interval
import org.dyn4j.geometry.Matrix22
import org.dyn4j.geometry.Vector2

open class SequentialImpulses<T : PhysicsBody> : ContactConstraintSolver<T> {
    private fun massCoefficient(constraint: ContactConstraint<T>, r1: Vector2, r2: Vector2, axis: Vector2): Double {
        val mass1 = constraint.getBody1().getMass()
        val mass2 = constraint.getBody2().getMass()
        val cross1 = r1.cross(axis)
        val cross2 = r2.cross(axis)
        return mass1.getInverseMass() + mass2.getInverseMass() +
            mass1.getInverseInertia() * cross1 * cross1 + mass2.getInverseInertia() * cross2 * cross2
    }

    private fun relativeVelocity(constraint: ContactConstraint<T>, contact: SolvableContact): Vector2 {
        val velocity1 = contact.r1!!.cross(constraint.getBody1().getAngularVelocity())
            .add(constraint.getBody1().getLinearVelocity())
        val velocity2 = contact.r2!!.cross(constraint.getBody2().getAngularVelocity())
            .add(constraint.getBody2().getLinearVelocity())
        return velocity1.subtract(velocity2)
    }

    private fun updateBodies(constraint: ContactConstraint<T>, contact: SolvableContact, impulse: Vector2) {
        val body1 = constraint.getBody1()
        val body2 = constraint.getBody2()
        val mass1 = body1.getMass()
        val mass2 = body2.getMass()
        body1.getLinearVelocity().add(impulse.x * mass1.getInverseMass(), impulse.y * mass1.getInverseMass())
        body1.setAngularVelocity(body1.getAngularVelocity() + mass1.getInverseInertia() * contact.r1!!.cross(impulse))
        body2.getLinearVelocity().subtract(impulse.x * mass2.getInverseMass(), impulse.y * mass2.getInverseMass())
        body2.setAngularVelocity(body2.getAngularVelocity() - mass2.getInverseInertia() * contact.r2!!.cross(impulse))
    }

    private fun updateBodies(constraint: ContactConstraint<T>, first: SolvableContact, second: SolvableContact,
                             next: Vector2, previous: Vector2) {
        val body1 = constraint.getBody1()
        val body2 = constraint.getBody2()
        val mass1 = body1.getMass()
        val mass2 = body2.getMass()
        val impulse1 = constraint.solverNormal().product(next.x - previous.x)
        val impulse2 = constraint.solverNormal().product(next.y - previous.y)
        val x = impulse1.x + impulse2.x
        val y = impulse1.y + impulse2.y
        body1.getLinearVelocity().add(x * mass1.getInverseMass(), y * mass1.getInverseMass())
        body1.setAngularVelocity(body1.getAngularVelocity() + mass1.getInverseInertia() *
            (first.r1!!.cross(impulse1) + second.r1!!.cross(impulse2)))
        body2.getLinearVelocity().subtract(x * mass2.getInverseMass(), y * mass2.getInverseMass())
        body2.setAngularVelocity(body2.getAngularVelocity() - mass2.getInverseInertia() *
            (first.r2!!.cross(impulse1) + second.r2!!.cross(impulse2)))
        first.jn = next.x
        second.jn = next.y
    }

    open override fun initialize(contactConstraints: List<ContactConstraint<T>>, step: TimeStep, settings: Settings) {
        for (constraint in contactConstraints) {
            val contacts = constraint.solverContacts()
            val count = contacts.size
            if (count == 0) return
            val body1 = constraint.getBody1()
            val body2 = constraint.getBody2()
            val mass1 = body1.getMass()
            val mass2 = body2.getMass()
            val center1 = body1.getTransform().getTransformed(mass1.getCenter())
            val center2 = body2.getTransform().getTransformed(mass2.getCenter())
            val normal = constraint.solverNormal()
            val tangent = constraint.solverTangent()
            for (contact in contacts) {
                contact.r1 = center1.to(contact.p)
                contact.r2 = center2.to(contact.p)
                contact.massN = 1.0 / massCoefficient(constraint, contact.r1!!, contact.r2!!, normal)
                contact.massT = 1.0 / massCoefficient(constraint, contact.r1!!, contact.r2!!, tangent)
                contact.vb = 0.0
                contact.ignored = false
                contact.solved = true
                val relativeNormalVelocity = normal.dot(relativeVelocity(constraint, contact))
                if (relativeNormalVelocity < -constraint.getRestitutionVelocity()) {
                    contact.vb += -constraint.getRestitution() * relativeNormalVelocity
                }
            }
            if (count == 2) {
                val first = contacts[0]
                val second = contacts[1]
                val rn1a = first.r1!!.cross(normal)
                val rn1b = first.r2!!.cross(normal)
                val rn2a = second.r1!!.cross(normal)
                val rn2b = second.r2!!.cross(normal)
                val matrix = Matrix22()
                matrix.m00 = mass1.getInverseMass() + mass2.getInverseMass() +
                    mass1.getInverseInertia() * rn1a * rn1a + mass2.getInverseInertia() * rn1b * rn1b
                matrix.m01 = mass1.getInverseMass() + mass2.getInverseMass() +
                    mass1.getInverseInertia() * rn1a * rn2a + mass2.getInverseInertia() * rn1b * rn2b
                matrix.m10 = matrix.m01
                matrix.m11 = mass1.getInverseMass() + mass2.getInverseMass() +
                    mass1.getInverseInertia() * rn2a * rn2a + mass2.getInverseInertia() * rn2b * rn2b
                if (matrix.m00 * matrix.m00 < 1000.0 * matrix.determinant()) {
                    constraint.K = matrix
                    constraint.invK = matrix.getInverse()
                } else {
                    constraint.setSolverSize(1)
                    if (first.depth < second.depth) {
                        contacts[0] = second
                        contacts[1] = first
                    }
                    contacts[1].ignored = true
                    contacts[1].solved = false
                }
            }
        }
        warmStart(contactConstraints, step, settings)
    }

    protected open fun warmStart(contactConstraints: List<ContactConstraint<T>>, step: TimeStep, settings: Settings) {
        val ratio = 1.0 / step.getDeltaTimeRatio()
        for (constraint in contactConstraints) {
            val normal = constraint.solverNormal()
            val tangent = constraint.solverTangent()
            val contacts = constraint.solverContacts()
            for (index in 0 until constraint.solverSize()) {
                val contact = contacts[index]
                contact.jn *= ratio
                contact.jt *= ratio
                updateBodies(constraint, contact,
                    Vector2(normal.x * contact.jn + tangent.x * contact.jt,
                            normal.y * contact.jn + tangent.y * contact.jt))
            }
        }
    }

    open override fun solveVelocityContraints(contactConstraints: List<ContactConstraint<T>>, step: TimeStep, settings: Settings) {
        for (constraint in contactConstraints) {
            val contacts = constraint.solverContacts()
            val count = constraint.solverSize()
            if (count == 0) continue
            val normal = constraint.solverNormal()
            val tangent = constraint.solverTangent()
            for (index in 0 until count) {
                val contact = contacts[index]
                val tangentVelocity = tangent.dot(relativeVelocity(constraint, contact)) - constraint.getTangentSpeed()
                var impulse = -contact.massT * tangentVelocity
                val maxImpulse = constraint.getFriction() * contact.jn
                val previous = contact.jt
                contact.jt = max(-maxImpulse, min(previous + impulse, maxImpulse))
                impulse = contact.jt - previous
                updateBodies(constraint, contact, tangent.product(impulse))
            }
            if (count == 1) {
                val contact = contacts[0]
                val relativeNormalVelocity = normal.dot(relativeVelocity(constraint, contact))
                var impulse = -contact.massN * (relativeNormalVelocity - contact.vb)
                val previous = contact.jn
                contact.jn = max(previous + impulse, 0.0)
                impulse = contact.jn - previous
                updateBodies(constraint, contact, normal.product(impulse))
            } else {
                val first = contacts[0]
                val second = contacts[1]
                val previous = Vector2(first.jn, second.jn)
                val velocity1 = normal.dot(relativeVelocity(constraint, first))
                val velocity2 = normal.dot(relativeVelocity(constraint, second))
                val bias = Vector2(velocity1 - first.vb, velocity2 - second.vb)
                bias.subtract(constraint.K!!.product(previous))
                var next = constraint.invK!!.product(bias).negate()
                if (next.x >= 0.0 && next.y >= 0.0) {
                    updateBodies(constraint, first, second, next, previous)
                    continue
                }
                next = Vector2(-first.massN * bias.x, 0.0)
                if (next.x >= 0.0 && constraint.K!!.m10 * next.x + bias.y >= 0.0) {
                    updateBodies(constraint, first, second, next, previous)
                    continue
                }
                next = Vector2(0.0, -second.massN * bias.y)
                if (next.y >= 0.0 && constraint.K!!.m01 * next.y + bias.x >= 0.0) {
                    updateBodies(constraint, first, second, next, previous)
                    continue
                }
                next = Vector2()
                if (bias.x >= 0.0 && bias.y >= 0.0) {
                    updateBodies(constraint, first, second, next, previous)
                }
            }
        }
    }

    open override fun solvePositionContraints(contactConstraints: List<ContactConstraint<T>>, step: TimeStep, settings: Settings): Boolean {
        if (contactConstraints.isEmpty()) return true
        var minimumSeparation = 0.0
        val maximumCorrection = settings.getMaximumLinearCorrection()
        val tolerance = settings.getLinearTolerance()
        val baumgarte = settings.getBaumgarte()
        for (constraint in contactConstraints) {
            val count = constraint.solverSize()
            if (count == 0) continue
            val body1 = constraint.getBody1()
            val body2 = constraint.getBody2()
            val transform1 = body1.getTransform()
            val transform2 = body2.getTransform()
            val mass1 = body1.getMass()
            val mass2 = body2.getMass()
            val normal = constraint.solverNormal()
            for (index in 0 until count) {
                val contact = constraint.solverContacts()[index]
                val center1 = transform1.getTransformed(mass1.getCenter())
                val center2 = transform2.getTransformed(mass2.getCenter())
                val r1 = contact.p1.difference(mass1.getCenter())
                val r2 = contact.p2.difference(mass2.getCenter())
                transform1.transformR(r1)
                transform2.transformR(r2)
                val point1 = center1.sum(r1)
                val point2 = center2.sum(r2)
                val penetration = point1.subtract(point2).dot(normal) - contact.depth
                minimumSeparation = min(minimumSeparation, penetration)
                val correction = baumgarte * Interval.clamp(penetration + tolerance, -maximumCorrection, 0.0)
                val coefficient = massCoefficient(constraint, r1, r2, normal)
                var impulse = if (coefficient > Epsilon.E) -correction / coefficient else 0.0
                val previous = contact.jp
                contact.jp = max(previous + impulse, 0.0)
                impulse = contact.jp - previous
                val movement = normal.product(impulse)
                transform1.translate(movement.product(mass1.getInverseMass()))
                transform1.rotate(mass1.getInverseInertia() * r1.cross(movement), center1.x, center1.y)
                transform2.translate(movement.product(-mass2.getInverseMass()))
                transform2.rotate(-mass2.getInverseInertia() * r2.cross(movement), center2.x, center2.y)
            }
        }
        return minimumSeparation >= -3.0 * tolerance
    }
}
