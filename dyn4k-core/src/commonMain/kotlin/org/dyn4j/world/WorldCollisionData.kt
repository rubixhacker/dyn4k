/*
 * Copyright (c) 2010-2023 William Bittle  http://www.dyn4j.org/
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
package org.dyn4j.world

import org.dyn4j.collision.CollisionItem
import org.dyn4j.collision.CollisionPair
import org.dyn4j.collision.manifold.Manifold
import org.dyn4j.collision.narrowphase.Penetration
import org.dyn4j.dynamics.BodyFixture
import org.dyn4j.dynamics.PhysicsBody
import org.dyn4j.dynamics.contact.ContactConstraint
import org.dyn4j.geometry.Vector2

open class WorldCollisionData<T : PhysicsBody>(
    private val pair: CollisionPair<CollisionItem<T, BodyFixture>>
) : ContactCollisionData<T> {
    private var broadphaseCollision = false
    private var narrowphaseCollision = false
    private var manifoldCollision = false
    private var contactConstraintCollision = false

    private val penetration = Penetration()
    private val manifold = Manifold()
    private val contactConstraint = ContactConstraint<T>(pair)

    private val body1: T? = pair.getFirst().getBody()
    private val body2: T? = pair.getSecond().getBody()
    private val fixture1: BodyFixture? = pair.getFirst().getFixture()
    private val fixture2: BodyFixture? = pair.getSecond().getFixture()

    override fun getPair(): CollisionPair<CollisionItem<T, BodyFixture>> = pair
    override fun getBody1(): T? = body1
    override fun getFixture1(): BodyFixture? = fixture1
    override fun getBody2(): T? = body2
    override fun getFixture2(): BodyFixture? = fixture2

    override fun shift(shift: Vector2) {
        manifold.shift(shift)
    }

    override fun getManifold(): Manifold = manifold
    override fun getPenetration(): Penetration = penetration
    override fun getContactConstraint(): ContactConstraint<T> = contactConstraint

    override fun isBroadphaseCollision(): Boolean = broadphaseCollision
    override fun setBroadphaseCollision(flag: Boolean) { broadphaseCollision = flag }
    override fun isNarrowphaseCollision(): Boolean = narrowphaseCollision
    override fun setNarrowphaseCollision(flag: Boolean) { narrowphaseCollision = flag }
    override fun isManifoldCollision(): Boolean = manifoldCollision
    override fun setManifoldCollision(flag: Boolean) { manifoldCollision = flag }
    override fun isContactConstraintCollision(): Boolean = contactConstraintCollision
    override fun setContactConstraintCollision(flag: Boolean) { contactConstraintCollision = flag }

    override fun reset() {
        broadphaseCollision = false
        narrowphaseCollision = false
        manifoldCollision = false
        contactConstraintCollision = false
        penetration.clear()
        manifold.clear()
        // Keep the old contact data so the world can report ending contacts.
    }
}
