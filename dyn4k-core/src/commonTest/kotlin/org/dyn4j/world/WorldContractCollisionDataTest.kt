package org.dyn4j.world

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertSame
import kotlin.test.assertTrue
import org.dyn4j.collision.BasicCollisionItem
import org.dyn4j.collision.BasicCollisionPair
import org.dyn4j.collision.CollisionItem
import org.dyn4j.collision.CollisionPair
import org.dyn4j.collision.manifold.ManifoldPoint
import org.dyn4j.collision.manifold.ManifoldPointId
import org.dyn4j.dynamics.Body
import org.dyn4j.dynamics.BodyFixture
import org.dyn4j.geometry.Circle
import org.dyn4j.geometry.Vector2

class WorldContractCollisionDataTest {
    @Test
    fun resetClearsDetectionStagesAndPreservesContactData() {
        val body1 = Body()
        val body2 = Body()
        val fixture1 = body1.addFixture(Circle(1.0))
        val fixture2 = body2.addFixture(Circle(2.0))
        val pair: CollisionPair<CollisionItem<Body, BodyFixture>> = BasicCollisionPair(
            BasicCollisionItem(body1, fixture1),
            BasicCollisionItem(body2, fixture2)
        )
        val data = WorldCollisionData(pair)
        val contact = data.getContactConstraint()
        val penetration = data.getPenetration()
        val manifold = data.getManifold()

        assertSame(pair, data.getPair())
        assertSame(body1, data.getBody1())
        assertSame(fixture1, data.getFixture1())
        assertSame(body2, data.getBody2())
        assertSame(fixture2, data.getFixture2())

        penetration.setDepth(2.0)
        manifold.setNormal(Vector2(1.0, 0.0))
        data.setBroadphaseCollision(true)
        data.setNarrowphaseCollision(true)
        data.setManifoldCollision(true)
        data.setContactConstraintCollision(true)
        data.reset()

        assertFalse(data.isBroadphaseCollision())
        assertFalse(data.isNarrowphaseCollision())
        assertFalse(data.isManifoldCollision())
        assertFalse(data.isContactConstraintCollision())
        assertSame(contact, data.getContactConstraint())
        assertSame(penetration, data.getPenetration())
        assertSame(manifold, data.getManifold())
        assertEquals(0.0, penetration.getDepth())
        assertEquals(0.0, manifold.getNormal().x)
    }

    @Test
    fun shiftMovesManifoldPointsWithoutChangingPenetration() {
        val body = Body()
        val fixture = body.addFixture(Circle(1.0))
        val pair: CollisionPair<CollisionItem<Body, BodyFixture>> = BasicCollisionPair(
            BasicCollisionItem(body, fixture),
            BasicCollisionItem(body, fixture)
        )
        val data = WorldCollisionData(pair)
        val point = ManifoldPoint(ManifoldPointId.DISTANCE)
        point.setPoint(Vector2(2.0, 3.0))
        data.getManifold().setPoints(listOf(point))
        data.getPenetration().setDepth(1.25)

        data.shift(Vector2(4.0, -2.0))

        val shiftedPoint = data.getManifold().getPoints().single().getPoint()
        assertEquals(6.0, shiftedPoint.x)
        assertEquals(1.0, shiftedPoint.y)
        assertEquals(1.25, data.getPenetration().getDepth())
    }

    @Test
    fun nullCollisionItemValuesRemainObservable() {
        val body = Body()
        val fixture = body.addFixture(Circle(1.0))
        val pair: CollisionPair<CollisionItem<Body, BodyFixture>> = BasicCollisionPair(
            BasicCollisionItem(null, null),
            BasicCollisionItem(body, fixture)
        )
        val data = WorldCollisionData(pair)

        assertEquals(null, data.getBody1())
        assertEquals(null, data.getFixture1())
        assertSame(body, data.getBody2())
        assertSame(fixture, data.getFixture2())
        assertTrue(data.getContactConstraint().isEnabled())
    }
}
