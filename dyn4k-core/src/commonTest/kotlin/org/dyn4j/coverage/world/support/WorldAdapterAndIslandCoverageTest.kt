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
package org.dyn4j.world

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertNotSame
import kotlin.test.assertNull
import kotlin.test.assertSame
import kotlin.test.assertTrue
import org.dyn4j.collision.BasicCollisionItem
import org.dyn4j.collision.BasicCollisionPair
import org.dyn4j.collision.CollisionItem
import org.dyn4j.dynamics.Body
import org.dyn4j.dynamics.BodyFixture
import org.dyn4j.dynamics.joint.AngleJoint
import org.dyn4j.geometry.AABB
import org.dyn4j.geometry.Geometry
import org.dyn4j.geometry.MassType
import org.dyn4j.dynamics.contact.ContactConstraint

class WorldAdapterAndIslandCoverageTest {
    private fun fixture(body: Body) = body.addFixture(Geometry.createCircle(0.5))

    private fun constraint(): ContactConstraint<Body> {
        val a = Body(); val b = Body()
        val first = BodyFixture(Geometry.createCircle(1.0))
        val second = BodyFixture(Geometry.createCircle(1.0))
        val pair = BasicCollisionPair<CollisionItem<Body, BodyFixture>>(
            BasicCollisionItem(a, first), BasicCollisionItem(b, second))
        return ContactConstraint(pair)
    }

    @Test fun collisionItemAdapterGetAndSet() {
        val item = CollisionItemAdapter<Body, BodyFixture>()
        val a = Body(); val b = Body()
        val fa = fixture(a); val fb = fixture(b)
        assertNull(item.getBody()); assertNull(item.getFixture())
        item.set(a, fa)
        assertSame(a, item.getBody()); assertSame(fa, item.getFixture())
        item.set(b, fb)
        assertSame(b, item.getBody()); assertSame(fb, item.getFixture())
    }

    @Test fun collisionItemAdapterEqualsAndHashcode() {
        val a = Body(); val b = Body()
        val fa = fixture(a); val fb = fixture(b)
        val first = CollisionItemAdapter<Body, BodyFixture>(a, fa)
        val second = CollisionItemAdapter<Body, BodyFixture>(a, fa)
        assertEquals(first, second); assertEquals(first.hashCode(), second.hashCode())
        second.set(b, fb)
        assertFalse(first == second)
        second.set(a, fb)
        assertFalse(first == second)
    }

    @Test fun collisionItemAdapterCopy() {
        val item = CollisionItemAdapter<Body, BodyFixture>()
        val empty = item.copy()
        assertNull(empty.getBody()); assertNull(empty.getFixture())
        val body = Body(); val fixture = fixture(body)
        item.set(body, fixture)
        val copy = item.copy()
        assertNotSame(item, copy)
        assertSame(body, copy.getBody()); assertSame(fixture, copy.getFixture())
        empty.set(null, null)
        assertSame(body, copy.getBody()); assertSame(fixture, copy.getFixture())
    }

    @Test fun collisionItemAdapterCreate() {
        val empty = CollisionItemAdapter<Body, BodyFixture>()
        assertNull(empty.getBody()); assertNull(empty.getFixture())
        val body = Body(); val fixture = fixture(body)
        val item = CollisionItemAdapter(body, fixture)
        assertSame(body, item.getBody()); assertSame(fixture, item.getFixture())
    }

    @Test fun collisionItemAdapterSet() {
        val body = Body(); val fixture = fixture(body)
        val source = CollisionItemAdapter(body, fixture)
        val target = CollisionItemAdapter<Body, BodyFixture>()
        target.set(source)
        assertSame(body, target.getBody()); assertSame(fixture, target.getFixture())
    }

    private fun assertBounds(box: AABB, minX: Double, minY: Double, maxX: Double, maxY: Double) {
        assertEquals(minX, box.getMinX()); assertEquals(minY, box.getMinY())
        assertEquals(maxX, box.getMaxX()); assertEquals(maxY, box.getMaxY())
    }

    private fun movingBody(): Body = Body().also {
        fixture(it); it.setMass(MassType.NORMAL); it.translate(1.0, 0.0)
    }

    @Test fun physicsBodySweptAABBProducerSweepIntoNewAABB() {
        val producer = PhysicsBodySweptAABBProducer<Body>()
        val body = movingBody()
        assertBounds(producer.compute(body), -0.5, -0.5, 1.5, 0.5)
        body.translate(1.0, 1.0)
        assertBounds(producer.compute(body), -0.5, -0.5, 2.5, 1.5)
        body.getPreviousTransform().set(body.getTransform())
        assertBounds(producer.compute(body), 1.5, 0.5, 2.5, 1.5)
    }

    @Test fun physicsBodySweptAABBProducerSweepIntoExistingAABB() {
        val producer = PhysicsBodySweptAABBProducer<Body>()
        val body = movingBody()
        val box = AABB(0.0, 0.0, 0.0, 0.0)
        producer.compute(body, box)
        assertBounds(box, -0.5, -0.5, 1.5, 0.5)
        body.translate(1.0, 1.0)
        producer.compute(body, box)
        assertBounds(box, -0.5, -0.5, 2.5, 1.5)
        body.getPreviousTransform().set(body.getTransform())
        producer.compute(body, box)
        assertBounds(box, 1.5, 0.5, 2.5, 1.5)
    }

    @Test fun physicsBodySweptAABBProducerNoSweep() {
        val body = Body(); fixture(body); body.setMass(MassType.NORMAL)
        assertBounds(PhysicsBodySweptAABBProducer<Body>().compute(body), -0.5, -0.5, 0.5, 0.5)
    }

    @Test fun physicsBodySweptAABBProducerZero() {
        assertBounds(PhysicsBodySweptAABBProducer<Body>().compute(Body()), 0.0, 0.0, 0.0, 0.0)
    }

    @Test fun islandCreateSuccess() {
        val island = Island<Body>()
        assertNotNull(island.bodies); assertNotNull(island.joints); assertNotNull(island.contactConstraints)
        assertEquals(0, island.bodies.size)
    }

    @Test fun islandCreateInvalidInitialCapacity() {
        val island = Island<Body>(-1, 0)
        assertNotNull(island.bodies); assertNotNull(island.joints); assertNotNull(island.contactConstraints)
        assertEquals(0, island.joints.size)
    }

    @Test fun islandAdd() {
        val island = Island<Body>()
        val a = Body(); val b = Body()
        val joint = AngleJoint(a, b)
        val contact = constraint()
        island.add(a); island.add(b); island.add(joint); island.add(contact)
        assertEquals(2, island.bodies.size)
        assertEquals(1, island.joints.size)
        assertEquals(1, island.contactConstraints.size)
        island.add(a); island.add(b); island.add(joint); island.add(contact)
        assertEquals(4, island.bodies.size)
        assertEquals(2, island.joints.size)
        assertEquals(2, island.contactConstraints.size)
    }

    @Test fun islandClear() {
        val island = Island<Body>()
        island.add(Body()); island.add(AngleJoint(Body(), Body())); island.add(constraint())
        assertEquals(1, island.bodies.size)
        assertEquals(1, island.joints.size)
        assertEquals(1, island.contactConstraints.size)
        island.clear()
        assertTrue(island.bodies.isEmpty())
        assertTrue(island.joints.isEmpty())
        assertTrue(island.contactConstraints.isEmpty())
    }
}
