package org.dyn4j.world

import de.infix.testBalloon.framework.core.testSuite
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertSame
import kotlin.test.assertTrue
import org.dyn4j.dynamics.Body
import org.dyn4j.dynamics.BodyFixture
import org.dyn4j.collision.CollisionItem
import org.dyn4j.collision.CollisionPair
import org.dyn4j.collision.AxisAlignedBounds
import org.dyn4j.geometry.AABB
import org.dyn4j.geometry.Circle
import org.dyn4j.world.listener.BoundsListener
import org.dyn4j.world.listener.CollisionListenerAdapter

val CollisionWorldJourneyTest by testSuite {
    test("publicBodyAndCollisionListenerViewsMarkRandomAccess") { CollisionWorldJourneyTestFixture().run { publicBodyAndCollisionListenerViewsMarkRandomAccess() } }
    test("bodiesAndLiveViewFollowWorldOwnership") { CollisionWorldJourneyTestFixture().run { bodiesAndLiveViewFollowWorldOwnership() } }
    test("queryResultsCopyWhileIteratorReusesItsResult") { CollisionWorldJourneyTestFixture().run { queryResultsCopyWhileIteratorReusesItsResult() } }
    test("factoryAndCollisionDataFollowFixtureRemoval") { CollisionWorldJourneyTestFixture().run { factoryAndCollisionDataFollowFixtureRemoval() } }
    test("everyBroadphaseListenerRunsBeforeVeto") { CollisionWorldJourneyTestFixture().run { everyBroadphaseListenerRunsBeforeVeto() } }
    test("boundsCallbackDisablesBodyAndListenerViewStaysLive") { CollisionWorldJourneyTestFixture().run { boundsCallbackDisablesBodyAndListenerViewStaysLive() } }
}

private class CollisionProbeWorld : AbstractCollisionWorld<Body, BodyFixture, WorldCollisionData<Body>>() {
    var created = 0
    var processed = 0
    override fun createCollisionData(pair: CollisionPair<CollisionItem<Body, BodyFixture>>): WorldCollisionData<Body> {
        created++
        return WorldCollisionData(pair)
    }
    override fun processCollisions(iterator: MutableIterator<WorldCollisionData<Body>>) {
        while (iterator.hasNext()) {
            iterator.next()
            processed++
        }
    }
    fun scan() = detect()
}

private class CollisionWorldJourneyTestFixture  {
fun publicBodyAndCollisionListenerViewsMarkRandomAccess() {
        val world = World<Body>()
        val views = listOf(world.getBodies(), world.getCollisionListeners(), world.getBoundsListeners())
        for (view in views) {
            assertTrue(view is RandomAccess)
            assertTrue(view.subList(0, 0) is RandomAccess)
        }
    }

fun bodiesAndLiveViewFollowWorldOwnership() {
        val world = World<Body>()
        val bodies = world.getBodies()
        val body = Body()
        body.addFixture(Circle(1.0))

        assertTrue(bodies.isEmpty())
        world.addBody(body)
        assertSame(body, bodies.single())
        assertSame(world, body.getOwner())

        val iterator = world.getBodyIterator()
        assertSame(body, iterator.next())
        iterator.remove()
        assertTrue(bodies.isEmpty())
        assertEquals(0, world.getBodyCount())
        assertFalse(world.containsBody(body))
        assertEquals(null, body.getOwner())
    }

fun queryResultsCopyWhileIteratorReusesItsResult() {
        val world = CollisionProbeWorld()
        val first = Body().also { it.addFixture(Circle(1.0)) }
        val second = Body().also { it.addFixture(Circle(1.0)) }
        second.translate(4.0, 0.0)
        world.addBody(first)
        world.addBody(second)

        val query = AABB(-2.0, -2.0, 6.0, 2.0)
        val results = world.detect(query, null)
        assertEquals(2, results.size)
        assertTrue(results.any { it.getBody() === first })
        assertTrue(results.any { it.getBody() === second })
        assertFalse(results[0] === results[1])

        val iterator = world.detectIterator(query, null)
        val reused = iterator.next()
        assertSame(reused, iterator.next())
        assertEquals(1, world.detect(query, first, null).size)
    }

fun factoryAndCollisionDataFollowFixtureRemoval() {
        val world = CollisionProbeWorld()
        val first = Body().also { it.addFixture(Circle(1.0)) }
        val second = Body().also { it.addFixture(Circle(1.0)) }
        world.addBody(first)
        world.addBody(second)
        world.scan()

        assertEquals(1, world.created)
        assertEquals(1, world.processed)
        assertTrue(world.getCollisionDataIterator().hasNext())
        world.removeBody(second)
        assertFalse(world.getCollisionDataIterator().hasNext())
        world.scan()
        assertEquals(1, world.created)
        assertEquals(2, world.processed)
        assertEquals(null, world.getCollisionData(first, first.getFixture(0), second, second.getFixture(0)))
    }

fun everyBroadphaseListenerRunsBeforeVeto() {
        val world = CollisionProbeWorld()
        val first = Body().also { it.addFixture(Circle(1.0)) }
        val second = Body().also { it.addFixture(Circle(1.0)) }
        world.addBody(first)
        world.addBody(second)
        val calls = mutableListOf<String>()
        world.addCollisionListener(object : CollisionListenerAdapter<Body, BodyFixture>() {
            override fun collision(collision: BroadphaseCollisionData<Body, BodyFixture>?): Boolean {
                calls.add("first")
                return false
            }
        })
        world.addCollisionListener(object : CollisionListenerAdapter<Body, BodyFixture>() {
            override fun collision(collision: BroadphaseCollisionData<Body, BodyFixture>?): Boolean {
                calls.add("second")
                return true
            }
        })
        world.scan()
        assertEquals(listOf("first", "second"), calls)
        assertFalse(world.getCollisionData(first, first.getFixture(0), second, second.getFixture(0))!!.isBroadphaseCollision())
    }

fun boundsCallbackDisablesBodyAndListenerViewStaysLive() {
        val world = CollisionProbeWorld()
        val view = world.getBoundsListeners()
        val body = Body().also { it.addFixture(Circle(1.0)); it.translate(10.0, 0.0) }
        var outside: Body? = null
        val listener = object : BoundsListener<Body, BodyFixture> {
            override fun outside(body: Body?) { outside = body }
        }
        world.addBoundsListener(listener)
        assertSame(listener, view.single())
        world.setBounds(AxisAlignedBounds(4.0, 4.0))
        world.addBody(body)
        world.scan()
        assertSame(body, outside)
        assertFalse(body.isEnabled())
        world.removeAllBoundsListeners()
        assertTrue(view.isEmpty())
    }
}
