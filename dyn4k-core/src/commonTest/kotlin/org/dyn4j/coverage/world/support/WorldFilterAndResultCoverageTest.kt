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
package org.dyn4j.coverage.world.support

import kotlin.math.sqrt
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
import org.dyn4j.collision.CategoryFilter
import org.dyn4j.collision.CollisionItem
import org.dyn4j.collision.Filter
import org.dyn4j.collision.continuous.TimeOfImpact
import org.dyn4j.collision.narrowphase.Penetration
import org.dyn4j.collision.narrowphase.Raycast
import org.dyn4j.dynamics.Body
import org.dyn4j.dynamics.BodyFixture
import org.dyn4j.dynamics.joint.DistanceJoint
import org.dyn4j.geometry.Geometry
import org.dyn4j.geometry.MassType
import org.dyn4j.world.BroadphaseCollisionDataFilterAdapter
import org.dyn4j.world.CollisionBodyBroadphaseCollisionDataFilter
import org.dyn4j.world.DetectFilter
import org.dyn4j.world.PhysicsBodyBroadphaseCollisionDataFilter
import org.dyn4j.world.ValueMixer
import org.dyn4j.world.World
import org.dyn4j.world.result.ConvexCastResult
import org.dyn4j.world.result.ConvexDetectResult
import org.dyn4j.world.result.DetectResult
import org.dyn4j.world.result.RaycastResult

class WorldFilterAndResultCoverageTest {
    private class WorldProbe : World<Body>() {
        fun collisionData(pair: BasicCollisionPair<CollisionItem<Body, BodyFixture>>) = createCollisionData(pair)
    }

    private fun bodies(): Pair<Body, Body> {
        val a = Body().also { it.addFixture(Geometry.createCircle(0.5)) }
        val b = Body().also { it.addFixture(Geometry.createCircle(0.5)) }
        return a to b
    }

    private fun fixture(body: Body): BodyFixture = body.getFixture(0)

    @Test fun broadphaseFilterAdapterAlwaysAllowed() {
        val (a, b) = bodies()
        val filter = BroadphaseCollisionDataFilterAdapter<Body, BodyFixture>()
        assertTrue(filter.isAllowed(a, fixture(a), b, fixture(b)))
        assertTrue(filter.isAllowed(null, null, null, null))
    }

    @Test fun collisionBodyBroadphaseFilterEnabled() {
        val (a, b) = bodies()
        val filter = CollisionBodyBroadphaseCollisionDataFilter<Body, BodyFixture>()
        assertTrue(filter.isAllowed(a, fixture(a), b, fixture(b)))
        a.setEnabled(false)
        assertFalse(filter.isAllowed(a, fixture(a), b, fixture(b)))
        b.setEnabled(false)
        assertFalse(filter.isAllowed(a, fixture(a), b, fixture(b)))
        a.setEnabled(true); b.setEnabled(true)
        assertTrue(filter.isAllowed(a, fixture(a), b, fixture(b)))
    }

    private fun verifyCategories(allowed: (Body, Body) -> Boolean) {
        val (a, b) = bodies()
        val first = CategoryFilter(1L, 3L)
        val second = CategoryFilter(2L, 2L)
        val third = CategoryFilter(2L, 7L)
        fixture(a).setFilter(first); fixture(b).setFilter(first)
        assertTrue(allowed(a, b))
        fixture(b).setFilter(second)
        assertFalse(allowed(a, b))
        fixture(b).setFilter(third)
        assertTrue(allowed(a, b))
        fixture(a).setFilter(Filter.DEFAULT_FILTER)
        assertTrue(allowed(a, b))
        fixture(a).setFilter(second)
        assertTrue(allowed(a, b))
    }

    @Test fun collisionBodyBroadphaseFilterFilters() {
        val filter = CollisionBodyBroadphaseCollisionDataFilter<Body, BodyFixture>()
        verifyCategories { a, b -> filter.isAllowed(a, fixture(a), b, fixture(b)) }
    }

    @Test fun physicsBodyBroadphaseFilterEnabled() {
        val world = World<Body>()
        val filter = PhysicsBodyBroadphaseCollisionDataFilter(world)
        val (a, b) = bodies()
        a.setMass(MassType.NORMAL); b.setMass(MassType.NORMAL)
        world.addBody(a); world.addBody(b)
        assertTrue(filter.isAllowed(a, fixture(a), b, fixture(b)))
        a.setEnabled(false)
        assertFalse(filter.isAllowed(a, fixture(a), b, fixture(b)))
        b.setEnabled(false)
        assertFalse(filter.isAllowed(a, fixture(a), b, fixture(b)))
        a.setEnabled(true); b.setEnabled(true)
        assertTrue(filter.isAllowed(a, fixture(a), b, fixture(b)))
    }

    @Test fun physicsBodyBroadphaseFilterFilters() {
        val world = World<Body>()
        val filter = PhysicsBodyBroadphaseCollisionDataFilter(world)
        verifyCategories { a, b ->
            a.setMass(MassType.NORMAL); b.setMass(MassType.NORMAL)
            if (!world.containsBody(a)) world.addBody(a)
            if (!world.containsBody(b)) world.addBody(b)
            filter.isAllowed(a, fixture(a), b, fixture(b))
        }
    }

    @Test fun physicsBodyBroadphaseFilterDynamicSensor() {
        val world = World<Body>()
        val filter = PhysicsBodyBroadphaseCollisionDataFilter(world)
        val (a, b) = bodies()
        a.setMass(MassType.INFINITE); b.setMass(MassType.NORMAL)
        world.addBody(a); world.addBody(b)
        assertTrue(filter.isAllowed(a, fixture(a), b, fixture(b)))
        b.setMassType(MassType.INFINITE)
        assertFalse(filter.isAllowed(a, fixture(a), b, fixture(b)))
        fixture(b).setSensor(true)
        assertTrue(filter.isAllowed(a, fixture(a), b, fixture(b)))
        fixture(a).setSensor(true)
        assertTrue(filter.isAllowed(a, fixture(a), b, fixture(b)))
        a.setMassType(MassType.NORMAL); b.setMassType(MassType.NORMAL)
        assertTrue(filter.isAllowed(a, fixture(a), b, fixture(b)))
    }

    @Test fun physicsBodyBroadphaseFilterJointCollisionAllowed() {
        val world = World<Body>()
        val filter = PhysicsBodyBroadphaseCollisionDataFilter(world)
        val (a, b) = bodies()
        a.setMass(MassType.NORMAL); b.setMass(MassType.NORMAL)
        world.addBody(a); world.addBody(b)
        val joint = DistanceJoint(a, b, a.getWorldCenter(), b.getWorldCenter())
        world.addJoint(joint)
        joint.setCollisionAllowed(true)
        assertTrue(filter.isAllowed(a, fixture(a), b, fixture(b)))
        joint.setCollisionAllowed(false)
        assertFalse(filter.isAllowed(a, fixture(a), b, fixture(b)))
    }

    @Test fun detectFilterCreate() {
        val none = DetectFilter<Body, BodyFixture>(false, false, null)
        assertFalse(none.isIgnoreSensorsEnabled())
        assertFalse(none.IsIgnoreDisabledEnabled())
        assertNull(none.getFilter())
        val sensors = DetectFilter<Body, BodyFixture>(true, false, null)
        assertTrue(sensors.isIgnoreSensorsEnabled())
        assertFalse(sensors.IsIgnoreDisabledEnabled())
        assertNull(sensors.getFilter())
        val disabled = DetectFilter<Body, BodyFixture>(false, true, null)
        assertFalse(disabled.isIgnoreSensorsEnabled())
        assertTrue(disabled.IsIgnoreDisabledEnabled())
        assertNull(disabled.getFilter())
        val filtered = DetectFilter<Body, BodyFixture>(false, false, Filter.DEFAULT_FILTER)
        assertFalse(filtered.isIgnoreSensorsEnabled())
        assertFalse(filtered.IsIgnoreDisabledEnabled())
        assertSame(Filter.DEFAULT_FILTER, filtered.getFilter())
    }

    @Test fun detectFilterSensor() {
        val (body, _) = bodies()
        val filter = DetectFilter<Body, BodyFixture>(true, false, null)
        assertTrue(filter.isAllowed(body, fixture(body)))
        fixture(body).setSensor(true)
        assertFalse(filter.isAllowed(body, fixture(body)))
        fixture(body).setSensor(false)
        assertTrue(filter.isAllowed(body, fixture(body)))
        fixture(body).setSensor(true)
        assertTrue(DetectFilter<Body, BodyFixture>(false, false, null).isAllowed(body, fixture(body)))
    }

    @Test fun detectFilterDisabled() {
        val (body, _) = bodies()
        val filter = DetectFilter<Body, BodyFixture>(false, true, null)
        assertTrue(filter.isAllowed(body, fixture(body)))
        body.setEnabled(false)
        assertFalse(filter.isAllowed(body, fixture(body)))
        body.setEnabled(true)
        assertTrue(filter.isAllowed(body, fixture(body)))
        body.setEnabled(false)
        assertTrue(DetectFilter<Body, BodyFixture>(false, false, null).isAllowed(body, fixture(body)))
    }

    @Test fun detectFilterFilter() {
        val (body, _) = bodies()
        val fixture = fixture(body)
        val first = CategoryFilter(1L, 7L)
        val allowed = CategoryFilter(4L, 3L)
        val denied = CategoryFilter(4L, 4L)
        assertTrue(DetectFilter<Body, BodyFixture>(false, false, null).isAllowed(body, fixture))
        assertTrue(DetectFilter<Body, BodyFixture>(false, false, denied).isAllowed(body, fixture))
        fixture.setFilter(first)
        assertTrue(DetectFilter<Body, BodyFixture>(false, false, allowed).isAllowed(body, fixture))
        assertFalse(DetectFilter<Body, BodyFixture>(false, false, denied).isAllowed(body, fixture))
    }

    @Test fun valueMixerMixFriction() {
        assertEquals(sqrt(0.35), ValueMixer.DEFAULT_MIXER.mixFriction(0.5, 0.7), 1e-15)
    }

    private fun assertRestitutionChoice(mixer: ValueMixer) {
        assertEquals(0.7, mixer.mixRestitution(0.5, 0.7))
    }

    @Test fun valueMixerMixRestitution() {
        assertRestitutionChoice(ValueMixer.DEFAULT_MIXER)
    }

    @Test fun valueMixerMixRestitutionVelocity() {
        assertEquals(0.5, ValueMixer.DEFAULT_MIXER.mixRestitutionVelocity(0.5, 0.7))
    }

    @Test fun worldCreateCollisionData() {
        val (a, b) = bodies()
        val pair = BasicCollisionPair<CollisionItem<Body, BodyFixture>>(
            BasicCollisionItem(a, fixture(a)), BasicCollisionItem(b, fixture(b)))
        val data = WorldProbe().collisionData(pair)
        assertSame(a, data.getBody1())
        assertSame(b, data.getBody2())
        assertSame(fixture(a), data.getFixture1())
        assertSame(fixture(b), data.getFixture2())
        assertSame(pair, data.getPair())
        assertNotNull(data.getPenetration())
        assertNotNull(data.getManifold())
        assertNotNull(data.getContactConstraint())
        assertFalse(data.isBroadphaseCollision())
        assertFalse(data.isNarrowphaseCollision())
        assertFalse(data.isManifoldCollision())
        assertFalse(data.isContactConstraintCollision())
    }

    @Test fun detectResultCreateSuccess() {
        val basic = DetectResult<Body, BodyFixture>()
        val cast = ConvexCastResult<Body, BodyFixture>()
        val convex = ConvexDetectResult<Body, BodyFixture>()
        val ray = RaycastResult<Body, BodyFixture>()
        for (result in listOf(basic, cast, convex, ray)) {
            assertNull(result.getBody()); assertNull(result.getFixture())
        }
        assertNotNull(cast.getTimeOfImpact())
        assertNotNull(convex.getPenetration())
        assertNotNull(ray.getRaycast())
    }

    @Test fun detectResultSet() {
        val (body, _) = bodies()
        val fixture = fixture(body)
        val basic = DetectResult<Body, BodyFixture>()
        val cast = ConvexCastResult<Body, BodyFixture>()
        val convex = ConvexDetectResult<Body, BodyFixture>()
        val ray = RaycastResult<Body, BodyFixture>()
        val toi = TimeOfImpact().also { it.setTime(0.5) }
        val penetration = Penetration().also { it.setDepth(5.0) }
        val raycast = Raycast().also { it.setDistance(4.0) }
        for (result in listOf(basic, cast, convex, ray)) {
            result.setBody(body); result.setFixture(fixture)
            assertSame(body, result.getBody()); assertSame(fixture, result.getFixture())
        }
        cast.setTimeOfImpact(toi); convex.setPenetration(penetration); ray.setRaycast(raycast)
        assertEquals(0.5, cast.getTimeOfImpact().getTime())
        assertEquals(5.0, convex.getPenetration().getDepth())
        assertEquals(4.0, ray.getRaycast().getDistance())
    }

    @Test fun detectResultCopy() {
        val (body, _) = bodies()
        val fixture = fixture(body)
        val basic = DetectResult<Body, BodyFixture>().also { it.setBody(body); it.setFixture(fixture) }
        val cast = ConvexCastResult<Body, BodyFixture>().also {
            it.setBody(body); it.setFixture(fixture); it.setTimeOfImpact(TimeOfImpact().also { v -> v.setTime(0.5) })
        }
        val convex = ConvexDetectResult<Body, BodyFixture>().also {
            it.setBody(body); it.setFixture(fixture); it.setPenetration(Penetration().also { v -> v.setDepth(5.0) })
        }
        val ray = RaycastResult<Body, BodyFixture>().also {
            it.setBody(body); it.setFixture(fixture); it.setRaycast(Raycast().also { v -> v.setDistance(4.0) })
        }
        val basicCopy = basic.copy()
        val castCopy = cast.copy()
        val convexCopy = convex.copy()
        val rayCopy = ray.copy()
        for (result in listOf(basicCopy, castCopy, convexCopy, rayCopy)) {
            assertSame(body, result.getBody()); assertSame(fixture, result.getFixture())
        }
        assertNotSame(cast.getTimeOfImpact(), castCopy.getTimeOfImpact())
        assertNotSame(convex.getPenetration(), convexCopy.getPenetration())
        assertNotSame(ray.getRaycast(), rayCopy.getRaycast())
        cast.getTimeOfImpact().setTime(0.7)
        convex.getPenetration().setDepth(1.0)
        ray.getRaycast().setDistance(2.0)
        assertEquals(0.5, castCopy.getTimeOfImpact().getTime())
        assertEquals(5.0, convexCopy.getPenetration().getDepth())
        assertEquals(4.0, rayCopy.getRaycast().getDistance())
        val basicSet = DetectResult<Body, BodyFixture>().also { it.set(basic) }
        val castSet = ConvexCastResult<Body, BodyFixture>().also { it.set(cast) }
        val convexSet = ConvexDetectResult<Body, BodyFixture>().also { it.set(convex) }
        val raySet = RaycastResult<Body, BodyFixture>().also { it.set(ray) }
        for (result in listOf(basicSet, castSet, convexSet, raySet)) {
            assertSame(body, result.getBody()); assertSame(fixture, result.getFixture())
        }
        assertEquals(0.7, castSet.getTimeOfImpact().getTime())
        assertEquals(1.0, convexSet.getPenetration().getDepth())
        assertEquals(2.0, raySet.getRaycast().getDistance())
        assertNotSame(cast.getTimeOfImpact(), castSet.getTimeOfImpact())
        assertNotSame(convex.getPenetration(), convexSet.getPenetration())
        assertNotSame(ray.getRaycast(), raySet.getRaycast())
    }

    @Test fun detectResultCompareTo() {
        val cast = ConvexCastResult<Body, BodyFixture>()
        cast.getTimeOfImpact().setTime(0.5)
        val later = cast.copy().also { it.getTimeOfImpact().setTime(6.0) }
        assertTrue(cast.compareTo(later) < 0)
        val ray = RaycastResult<Body, BodyFixture>()
        ray.getRaycast().setDistance(4.0)
        val nearer = ray.copy().also { it.getRaycast().setDistance(2.0) }
        assertTrue(ray.compareTo(nearer) > 0)
    }
}
