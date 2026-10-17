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

import org.dyn4j.collision.CollisionBody
import org.dyn4j.geometry.AABB
import org.dyn4j.geometry.Convex
import org.dyn4j.geometry.Mass
import org.dyn4j.geometry.MassType
import org.dyn4j.geometry.Transform
import org.dyn4j.geometry.Vector2

interface PhysicsBody : CollisionBody<BodyFixture> {
    override fun copy(): PhysicsBody
    fun addFixture(convex: Convex?, density: Double): BodyFixture
    fun addFixture(convex: Convex?, density: Double, friction: Double, restitution: Double): BodyFixture
    fun updateMass(): PhysicsBody
    fun setMass(type: MassType?): PhysicsBody
    fun setMass(mass: Mass?): PhysicsBody
    fun setMassType(type: MassType?): PhysicsBody
    fun getMass(): Mass
    fun applyForce(force: Vector2?): PhysicsBody
    fun applyForce(force: Force?): PhysicsBody
    fun applyTorque(torque: Double): PhysicsBody
    fun applyTorque(torque: Torque?): PhysicsBody
    fun applyForce(force: Vector2?, point: Vector2?): PhysicsBody
    fun applyImpulse(impulse: Vector2?): PhysicsBody
    fun applyImpulse(impulse: Double): PhysicsBody
    fun applyImpulse(impulse: Vector2?, point: Vector2?): PhysicsBody
    fun clearForce()
    fun clearAccumulatedForce()
    fun clearTorque()
    fun clearAccumulatedTorque()
    fun integrateVelocity(gravity: Vector2?, timestep: TimeStep?, settings: Settings?)
    fun integratePosition(timestep: TimeStep?, settings: Settings?)
    fun updateAtRestTime(timestep: TimeStep?, settings: Settings?): Double
    fun isStatic(): Boolean
    fun isKinematic(): Boolean
    fun isDynamic(): Boolean
    fun setAtRestDetectionEnabled(flag: Boolean)
    fun isAtRestDetectionEnabled(): Boolean
    fun setAtRest(flag: Boolean)
    fun isAtRest(): Boolean
    fun setBullet(flag: Boolean)
    fun isBullet(): Boolean
    fun getChangeInPosition(): Vector2
    fun getChangeInOrientation(): Double
    fun getLinearVelocity(): Vector2
    fun getLinearVelocity(point: Vector2?): Vector2
    fun setLinearVelocity(velocity: Vector2?)
    fun setLinearVelocity(x: Double, y: Double)
    fun getAngularVelocity(): Double
    fun setAngularVelocity(angularVelocity: Double)
    fun getForce(): Vector2
    fun getAccumulatedForce(): Vector2
    fun getTorque(): Double
    fun getAccumulatedTorque(): Double
    fun getLinearDamping(): Double
    fun setLinearDamping(linearDamping: Double)
    fun getAngularDamping(): Double
    fun setAngularDamping(angularDamping: Double)
    fun getGravityScale(): Double
    fun setGravityScale(scale: Double)
    fun createSweptAABB(): AABB
    fun createSweptAABB(initialTransform: Transform?, finalTransform: Transform?): AABB
    fun computeSweptAABB(result: AABB)
    fun computeSweptAABB(initialTransform: Transform?, finalTransform: Transform?, result: AABB)

    companion object {
        const val DEFAULT_LINEAR_DAMPING = 0.0
        const val DEFAULT_ANGULAR_DAMPING = 0.01
    }
}
