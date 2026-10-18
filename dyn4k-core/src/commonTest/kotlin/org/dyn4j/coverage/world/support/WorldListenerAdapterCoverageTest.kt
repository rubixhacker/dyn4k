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
package org.dyn4j.coverage.world.support

import kotlin.test.Test
import kotlin.test.assertTrue
import org.dyn4j.collision.BasicCollisionItem
import org.dyn4j.collision.BasicCollisionPair
import org.dyn4j.collision.CollisionItem
import org.dyn4j.collision.continuous.TimeOfImpact
import org.dyn4j.collision.manifold.ManifoldPointId
import org.dyn4j.dynamics.Body
import org.dyn4j.dynamics.BodyFixture
import org.dyn4j.dynamics.TimeStep
import org.dyn4j.dynamics.contact.ContactConstraint
import org.dyn4j.dynamics.contact.SolvableContact
import org.dyn4j.dynamics.joint.AngleJoint
import org.dyn4j.dynamics.joint.Joint
import org.dyn4j.geometry.Geometry
import org.dyn4j.geometry.Vector2
import org.dyn4j.world.BroadphaseCollisionData
import org.dyn4j.world.ManifoldCollisionData
import org.dyn4j.world.NarrowphaseCollisionData
import org.dyn4j.world.World
import org.dyn4j.world.WorldCollisionData
import org.dyn4j.world.listener.BoundsListenerAdapter
import org.dyn4j.world.listener.CollisionListenerAdapter
import org.dyn4j.world.listener.ContactListenerAdapter
import org.dyn4j.world.listener.DestructionListenerAdapter
import org.dyn4j.world.listener.StepListenerAdapter
import org.dyn4j.world.listener.TimeOfImpactListenerAdapter

class WorldListenerAdapterCoverageTest {
    private fun collision(): WorldCollisionData<Body> {
        val pair = BasicCollisionPair<CollisionItem<Body, BodyFixture>>(
            BasicCollisionItem(null, null), BasicCollisionItem(null, null))
        return WorldCollisionData(pair)
    }

    @Test fun listenerAdaptersBoundsListenerAdapter() {
        val adapter = BoundsListenerAdapter<Body, BodyFixture>()
        adapter.outside(null)
        adapter.outside(Body())
    }

    @Test fun listenerAdaptersCollisionListenerAdapter() {
        val adapter = CollisionListenerAdapter<Body, BodyFixture>()
        val data = collision()
        assertTrue(adapter.collision(null as BroadphaseCollisionData<Body, BodyFixture>?))
        assertTrue(adapter.collision(data as BroadphaseCollisionData<Body, BodyFixture>))
        assertTrue(adapter.collision(null as NarrowphaseCollisionData<Body, BodyFixture>?))
        assertTrue(adapter.collision(data as NarrowphaseCollisionData<Body, BodyFixture>))
        assertTrue(adapter.collision(null as ManifoldCollisionData<Body, BodyFixture>?))
        assertTrue(adapter.collision(data as ManifoldCollisionData<Body, BodyFixture>))
    }

    @Test fun listenerAdaptersContactListenerAdapter() {
        val adapter = ContactListenerAdapter<Body>()
        val data = collision()
        val point = Vector2(1.0, 2.0)
        val contact = SolvableContact(ManifoldPointId.DISTANCE, point, 0.0, point.copy(), point.copy())
        adapter.begin(data, null); adapter.begin(data, contact)
        adapter.end(data, null); adapter.end(data, contact)
        adapter.destroyed(data, null); adapter.destroyed(data, contact)
        adapter.persist(data, null, contact)
        adapter.persist(data, contact, null)
        adapter.persist(data, null, null)
        adapter.persist(data, contact, contact)
        adapter.postSolve(data, null); adapter.postSolve(data, contact)
        adapter.preSolve(data, null); adapter.preSolve(data, contact)
        adapter.collision(data)
    }

    @Test fun listenerAdaptersDestructionListenerAdapter() {
        val adapter = DestructionListenerAdapter<Body>()
        val constraint = ContactConstraint<Body>(BasicCollisionPair<CollisionItem<Body, BodyFixture>>(
            BasicCollisionItem(null, null), BasicCollisionItem(null, null)))
        val joint = AngleJoint(Body(), Body())
        adapter.destroyed(null as Body?); adapter.destroyed(Body())
        adapter.destroyed(null as ContactConstraint<Body>?); adapter.destroyed(constraint)
        adapter.destroyed(null as Joint<Body>?); adapter.destroyed(joint)
    }

    @Test fun listenerAdaptersStepListenerAdapter() {
        val adapter = StepListenerAdapter<Body>()
        val step = TimeStep(0.3)
        val world = World<Body>()
        for (s in listOf(null, step)) for (w in listOf(null, world)) {
            adapter.begin(s, w)
            adapter.end(s, w)
            adapter.postSolve(s, w)
            adapter.updatePerformed(s, w)
        }
    }

    @Test fun listenerAdaptersTimeOfImpactListenerAdapter() {
        val adapter = TimeOfImpactListenerAdapter<Body>()
        val body = Body()
        val fixture = BodyFixture(Geometry.createCircle(0.5))
        assertTrue(adapter.collision(null, null))
        assertTrue(adapter.collision(null, null, null, null))
        assertTrue(adapter.collision(null, null, null, null, null))
        assertTrue(adapter.collision(body, fixture, body, fixture, TimeOfImpact()))
        assertTrue(adapter.collision(body, body, TimeOfImpact()))
    }
}
