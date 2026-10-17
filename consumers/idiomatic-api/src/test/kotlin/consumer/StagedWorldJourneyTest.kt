package consumer

import io.github.rubixhacker.dyn4k.*
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertSame
import kotlin.test.assertTrue

class StagedWorldJourneyTest {
    private class ExtendedWorld : World<Body>() {
        var dispatchCount = 0
        var observedBody: Body? = null

        protected override fun step() {
            dispatchCount++
            observedBody = getBody(0)
            super.step()
        }
    }

    @Test
    fun publishedApiBuildsAndExtendsOneMutableWorld() {
        val extended = ExtendedWorld()
        val simulation = world(extended) {
            gravity = Vector2(0.0, 0.0)
            body { fixture(circle(1.0)); massType = MassType.INFINITE }
            body { fixture(circle(1.0)); massType = MassType.NORMAL; translate(0.5, 0.0) }
        }
        val compatibility: org.dyn4j.world.PhysicsWorld<Body, *> = simulation
        assertSame(extended, simulation)
        val bodies = simulation.bodies
        val joints = simulation.joints
        val moving = bodies[1]
        val fixtures = moving.fixtures
        val addedFixture = moving.fixture(circle(0.25))
        val joint = simulation.distanceJoint(bodies[0], moving, Vector2(), Vector2(0.5, 0.0)) {
            collisionAllowed = true
        }
        assertEquals(1, joints.size)
        assertSame(joint, compatibility.getJoint(0))
        assertSame(addedFixture, fixtures[1])

        val hits = simulation.find(AABB(-2.0, -2.0, 2.0, 2.0)) { candidate, fixture ->
            candidate === moving && fixture === addedFixture
        }
        assertSame(moving, hits.single().getBody())
        assertSame(addedFixture, hits.single().getFixture())

        var stepBegins = 0
        var stepEnds = 0
        var contactBegins = 0
        var contactEnds = 0
        val stepBegin = simulation.onStepBegin { _, world ->
            assertSame(simulation, world)
            stepBegins++
        }
        val stepEnd = simulation.onStepEnd { _, world ->
            assertSame(simulation, world)
            stepEnds++
        }
        val contactBegin = simulation.onContactBegin { collision, _ ->
            assertSame(bodies[0], collision!!.getBody1())
            contactBegins++
        }
        val contactEnd = simulation.onContactEnd { collision, _ ->
            assertSame(bodies[0], collision!!.getBody1())
            contactEnds++
        }
        simulation.step(1)
        assertEquals(1, extended.dispatchCount)
        assertSame(bodies[0], extended.observedBody)
        assertSame(compatibility.getBody(0), extended.observedBody)
        assertEquals(1, stepBegins)
        assertEquals(1, stepEnds)
        assertTrue(contactBegins > 0)

        assertTrue(simulation.removeJoint(joint))
        assertEquals(0, joints.size)
        moving.translate(10.0, 0.0)
        simulation.step(1)
        assertTrue(contactEnds > 0)
        assertTrue(simulation.removeStepListener(stepBegin))
        assertTrue(simulation.removeStepListener(stepEnd))
        assertTrue(simulation.removeContactListener(contactBegin))
        assertTrue(simulation.removeContactListener(contactEnd))
        val seenBegins = contactBegins
        val seenEnds = contactEnds
        moving.translate(-10.0, 0.0)
        simulation.step(1)
        moving.translate(10.0, 0.0)
        simulation.step(1)
        assertEquals(2, stepBegins)
        assertEquals(2, stepEnds)
        assertEquals(seenBegins, contactBegins)
        assertEquals(seenEnds, contactEnds)

        assertTrue(moving.removeFixture(addedFixture))
        assertTrue(simulation.removeBody(moving))
        assertEquals(0, joints.size)
        assertEquals(1, fixtures.size)
        assertEquals(1, bodies.size)
        assertSame(bodies[0], compatibility.getBody(0))
    }
}
