package org.dyn4j.world

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotSame
import kotlin.test.assertSame
import kotlin.test.assertTrue
import org.dyn4j.collision.CategoryFilter
import org.dyn4j.dynamics.Body
import org.dyn4j.dynamics.BodyFixture
import org.dyn4j.dynamics.joint.DistanceJoint
import org.dyn4j.geometry.AABB
import org.dyn4j.geometry.Circle
import org.dyn4j.geometry.Vector2

class WorldUtilityJourneyTest {
    @Test
    fun defaultMixerUsesBaselineRules() {
        val mixer = ValueMixer.DEFAULT_MIXER
        assertEquals(0.3, mixer.mixFriction(0.09, 1.0))
        assertEquals(0.8, mixer.mixRestitution(0.2, 0.8))
        assertEquals(0.2, mixer.mixRestitutionVelocity(0.2, 0.8))
    }

    @Test
    fun queryFilterTracksSensorDisabledAndFixtureFilterState() {
        val body = Body()
        val fixture = body.addFixture(Circle(0.5))
        val filter = DetectFilter<Body, BodyFixture>(true, true, CategoryFilter(1, 2))
        fixture.setFilter(CategoryFilter(4, 8))
        assertFalse(filter.isAllowed(body, fixture))
        fixture.setFilter(CategoryFilter(2, 1))
        assertTrue(filter.isAllowed(body, fixture))
        fixture.setSensor(true)
        assertFalse(filter.isAllowed(body, fixture))
        fixture.setSensor(false)
        body.setEnabled(false)
        assertFalse(filter.isAllowed(body, fixture))
        assertTrue(filter.isIgnoreSensorsEnabled())
        assertTrue(filter.IsIgnoreDisabledEnabled())
    }

    @Test
    fun collisionItemCopyRetainsReferencesWhileAdapterCanBeReused() {
        val body1 = Body()
        val fixture1 = body1.addFixture(Circle(0.5))
        val body2 = Body()
        val fixture2 = body2.addFixture(Circle(0.5))
        val adapter = CollisionItemAdapter(body1, fixture1)
        val copy = adapter.copy()
        assertNotSame(adapter, copy)
        assertEquals(adapter, copy)
        assertSame(body1, copy.getBody())
        assertSame(fixture1, copy.getFixture())
        adapter.set(body2, fixture2)
        assertFalse(adapter == copy)
        assertSame(body1, copy.getBody())
        assertSame(fixture1, copy.getFixture())
    }

    @Test
    fun broadphaseFilterChecksBodyStateAndFixtureMasks() {
        val body1 = Body()
        val fixture1 = body1.addFixture(Circle(0.5))
        val body2 = Body()
        val fixture2 = body2.addFixture(Circle(0.5))
        val filter = CollisionBodyBroadphaseCollisionDataFilter<Body, BodyFixture>()
        assertTrue(filter.isAllowed(body1, fixture1, body2, fixture2))
        fixture1.setFilter(CategoryFilter(1, 2))
        fixture2.setFilter(CategoryFilter(4, 8))
        assertFalse(filter.isAllowed(body1, fixture1, body2, fixture2))
        fixture2.setFilter(CategoryFilter(2, 1))
        assertTrue(filter.isAllowed(body1, fixture1, body2, fixture2))
        body2.setEnabled(false)
        assertFalse(filter.isAllowed(body1, fixture1, body2, fixture2))
    }

    @Test
    fun sweptProducerUpdatesExistingBounds() {
        val body = Body()
        body.addFixture(Circle(0.5))
        body.translate(1.0, 0.0)
        val producer = PhysicsBodySweptAABBProducer<Body>()
        val expected = producer.compute(body)
        val result = AABB(0.0, 0.0, 0.0, 0.0)
        producer.compute(body, result)
        assertEquals(expected.getMinX(), result.getMinX())
        assertEquals(expected.getMaxX(), result.getMaxX())
        assertEquals(-0.5, result.getMinX())
        assertEquals(1.5, result.getMaxX())
    }

    @Test
    fun graphJointViewIsLiveAndLinksFollowRemoval() {
        val body1 = Body()
        val body2 = Body()
        val joint = DistanceJoint(body1, body2, Vector2(), Vector2())
        val graph = ConstraintGraph<Body>()
        graph.addBody(body1)
        graph.addBody(body2)
        val view = graph.getNode(body1)!!.getJoints()
        assertTrue(view.isEmpty())
        graph.addJoint(joint)
        assertEquals(listOf(joint), view)
        assertTrue(graph.containsJoint(joint))
        assertTrue(graph.isJoined(body1, body2))
        assertFalse(graph.isJointCollisionAllowed(body1, body2))
        joint.setCollisionAllowed(true)
        assertTrue(graph.isJointCollisionAllowed(body1, body2))
        graph.removeJoint(joint)
        assertTrue(view.isEmpty())
        assertFalse(graph.isJoined(body1, body2))
    }
}
