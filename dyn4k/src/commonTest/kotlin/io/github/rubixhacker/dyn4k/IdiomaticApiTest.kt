package io.github.rubixhacker.dyn4k

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotSame
import kotlin.test.assertSame
import kotlin.test.assertTrue

class IdiomaticApiTest {
    @Test
    fun mutableVectorBindingReassignsValuesWithoutChangingSharedReferences() {
        var value = Vector2(2.0, 3.0)
        val shared: org.dyn4j.geometry.Vector2 = value
        value += Vector2(4.0, -1.0)
        assertNotSame(shared, value)
        assertEquals(2.0, shared.x)
        assertEquals(3.0, shared.y)
        assertEquals(6.0, value.x)
        assertEquals(2.0, value.y)

        val afterAddition = value
        value -= Vector2(1.0, 3.0)
        assertNotSame(afterAddition, value)
        assertEquals(6.0, afterAddition.x)
        assertEquals(5.0, value.x)
        assertEquals(-1.0, value.y)

        val afterSubtraction = value
        value *= 2.0
        assertNotSame(afterSubtraction, value)
        assertEquals(5.0, afterSubtraction.x)
        assertEquals(10.0, value.x)
        assertEquals(-2.0, value.y)

        val afterMultiplication = value
        value /= 2.0
        assertNotSame(afterMultiplication, value)
        assertEquals(10.0, afterMultiplication.x)
        assertEquals(5.0, value.x)
        assertEquals(-1.0, value.y)
    }

    @Test
    fun fixedVectorBindingMutatesSharedStateThroughNamedMethods() {
        val value = Vector2(2.0, 3.0)
        val compatibility: org.dyn4j.geometry.Vector2 = value
        value.add(Vector2(4.0, -1.0))
        assertSame(compatibility, value)
        assertEquals(6.0, compatibility.x)
        assertEquals(2.0, compatibility.y)
        value.subtract(Vector2(1.0, 3.0))
        assertEquals(5.0, compatibility.x)
        assertEquals(-1.0, compatibility.y)
        value.multiply(2.0)
        assertEquals(10.0, compatibility.x)
        assertEquals(-2.0, compatibility.y)
        value.divide(2.0)
        assertSame(compatibility, value)
        assertEquals(5.0, compatibility.x)
        assertEquals(-1.0, compatibility.y)
    }

    private class ObservedWorld : World<Body>() {
        var steps = 0
        var observedBody: Body? = null

        protected override fun step() {
            steps++
            observedBody = getBody(0)
            super.step()
        }
    }

    @Test
    fun builderKeepsSubclassAndDispatchesItsStepOverride() {
        val extended = ObservedWorld()
        val built = world(extended) {
            gravity = Vector2(0.0, 0.0)
            body { fixture(circle(0.5)); massType = MassType.NORMAL }
        }
        val compatibility: org.dyn4j.world.PhysicsWorld<Body, *> = built
        assertSame(extended, built)
        built.step(1)
        assertEquals(1, extended.steps)
        assertSame(built.bodies.single(), extended.observedBody)
        assertSame(compatibility.getBody(0), extended.observedBody)
    }

    @Test
    fun retainedMembershipViewsTrackAddsAndRemoves() {
        val built = world { gravity = Vector2(0.0, 0.0) }
        val bodyView = built.bodies
        val jointView = built.joints
        val first = built.body { massType = MassType.NORMAL }
        val fixtureView = first.fixtures
        val fixture = first.fixture(circle(0.5))
        val second = built.body { fixture(circle(0.5)); massType = MassType.NORMAL }
        val joint = built.distanceJoint(first, second, Vector2(), Vector2(2.0, 0.0))

        assertSame(bodyView, built.getBodies())
        assertSame(jointView, built.getJoints())
        assertSame(fixtureView, first.getFixtures())
        assertEquals(2, bodyView.size)
        assertSame(first, bodyView[0])
        assertEquals(1, fixtureView.size)
        assertSame(fixture, fixtureView[0])
        assertSame(joint, jointView.single())

        assertTrue(built.removeJoint(joint))
        assertTrue(first.removeFixture(fixture))
        assertTrue(built.removeBody(second))
        assertEquals(0, jointView.size)
        assertEquals(0, fixtureView.size)
        assertEquals(1, bodyView.size)
        assertSame(first, bodyView.single())
    }

    @Test
    fun removedStepCallbacksDoNotRunAgain() {
        val built = world { gravity = Vector2(0.0, 0.0) }
        var begins = 0
        var ends = 0
        val begin = built.onStepBegin { _, source ->
            assertSame(built, source)
            begins++
        }
        val end = built.onStepEnd { _, source ->
            assertSame(built, source)
            ends++
        }
        built.step(1)
        assertEquals(1, begins)
        assertEquals(1, ends)
        assertTrue(built.removeStepListener(begin))
        assertTrue(built.removeStepListener(end))
        built.step(1)
        assertEquals(1, begins)
        assertEquals(1, ends)
    }

    @Test
    fun contactEndRunsOnSeparationAndStopsAfterRemoval() {
        val built = world {
            gravity = Vector2(0.0, 0.0)
            body { fixture(circle(1.0)); massType = MassType.INFINITE }
            body { fixture(circle(1.0)); massType = MassType.NORMAL; translate(0.5, 0.0) }
        }
        val moving = built.bodies[1]
        var begins = 0
        var ends = 0
        val begin = built.onContactBegin { collision, _ ->
            assertSame(built.bodies[0], collision!!.getBody1())
            begins++
        }
        val end = built.onContactEnd { collision, _ ->
            assertSame(built.bodies[0], collision!!.getBody1())
            ends++
        }
        built.step(1)
        assertTrue(begins > 0)
        moving.translate(10.0, 0.0)
        built.step(1)
        assertTrue(ends > 0)
        val beginCount = begins
        val endCount = ends
        assertTrue(built.removeContactListener(begin))
        assertTrue(built.removeContactListener(end))
        moving.translate(-10.0, 0.0)
        built.step(1)
        moving.translate(10.0, 0.0)
        built.step(1)
        assertEquals(beginCount, begins)
        assertEquals(endCount, ends)
    }

    @Test
    fun vectorOperatorsAndShapePropertiesPreserveMutableCompatibilityObjects() {
        val left: Vector2 = Vector2(2.0, 3.0)
        val right = Vector2(4.0, -1.0)
        val result = left + right
        assertEquals(6.0, result.x)
        assertEquals(2.0, result.y)
        assertNotSame(left, result)
        left.add(right)
        assertEquals(6.0, left.x)
        assertEquals(2.0, left.y)
        assertEquals(12.0, left dotWith Vector2(2.0, 0.0))

        val shape: Shape = Circle(2.0)
        val convex: Convex = shape as Convex
        assertSame(shape, convex)
        assertEquals(kotlin.math.PI * 4.0, shape.area, 1e-12)
        assertSame(shape.getCenter(), shape.center)
        val capsule = Capsule(2.0, 1.0)
        val built = shape(capsule) { translate(3.0, 0.0) }
        assertSame(capsule, built)
        assertEquals(3.0, capsule.center.x)
    }

    @Test
    fun bodyBuilderUsesLiveFixtureAndVelocityState() {
        val built = body {
            fixture(circle(1.0)) { density = 2.0 }
            massType = MassType.NORMAL
            linearVelocity = Vector2(3.0, 0.0)
        }
        val compatibility: org.dyn4j.dynamics.PhysicsBody = built
        assertSame(built.fixtures[0], compatibility.getFixture(0))
        assertEquals(2.0, compatibility.getFixture(0).getDensity())
        assertTrue(compatibility.getMass().getMass() > 0.0)
        val liveVelocity = built.linearVelocity
        assertSame(liveVelocity, compatibility.getLinearVelocity())
        liveVelocity.x = 5.0
        assertEquals(5.0, compatibility.getLinearVelocity().x)
    }

    @Test
    fun worldBuilderAddsTheSameBodiesAndJointSeenByCompatibilityApi() {
        val built: World<Body> = world {
            gravity = Vector2(0.0, 0.0)
            val fixed = body { fixture(circle(0.5)); massType = MassType.INFINITE }
            val moving = body { fixture(circle(0.5)); massType = MassType.NORMAL }
            distanceJoint(fixed, moving, Vector2(0.0, 0.0), Vector2(2.0, 0.0)) {
                collisionAllowed = true
            }
        }
        val compatibility: org.dyn4j.world.PhysicsWorld<Body, *> = built
        assertEquals(2, built.bodies.size)
        assertSame(built.bodies[1], compatibility.getBody(1))
        assertSame(built.joints[0], compatibility.getJoint(0))
        assertTrue(compatibility.getJoint(0).isCollisionAllowed())
        built.step(1)
        assertEquals(2, compatibility.getBodyCount())
    }

    @Test
    fun queryAndStepCallbackObserveTheCompatibilityWorld() {
        val built = world {
            gravity = Vector2(0.0, 0.0)
            body { fixture(circle(1.0)); massType = MassType.NORMAL }
        }
        val events = mutableListOf<org.dyn4j.world.PhysicsWorld<Body, *>?>()
        val listener = built.onStepBegin { _, source -> events.add(source) }
        built.step(1)
        assertSame(built, events.single())
        val hits: List<DetectResult<Body, BodyFixture>> = built.find(AABB(-2.0, -2.0, 2.0, 2.0)) { candidate, _ ->
            candidate === built.bodies[0]
        }
        assertSame(built.bodies[0], hits.single().getBody())
        assertTrue(built.removeStepListener(listener))
    }

    @Test
    fun genericJointBuilderPreservesConcreteJointIdentity() {
        val built = world {
            val first = body { fixture(circle(0.5)); massType = MassType.NORMAL }
            val second = body { fixture(circle(0.5)); massType = MassType.NORMAL }
            joint(AngleJoint(first, second)) { collisionAllowed = true }
            joint(PinJoint(second, Vector2(1.0, 0.0)))
        }
        assertEquals(2, built.joints.size)
        assertTrue(built.joints[0] is org.dyn4j.dynamics.joint.AngleJoint<*>)
        assertTrue(built.joints[1] is org.dyn4j.dynamics.joint.PinJoint<*>)
        assertSame(built.joints[0], built.getJoint(0))
        assertTrue(built.joints[0].isCollisionAllowed())
    }

    @Test
    fun queryAndContactHelpersReceiveLiveWorldObjects() {
        val built = world {
            gravity = Vector2(0.0, 0.0)
            body { fixture(circle(1.0)); massType = MassType.INFINITE }
            body { fixture(circle(1.0)); massType = MassType.NORMAL; translate(0.5, 0.0) }
        }
        val contacts = mutableListOf<org.dyn4j.world.ContactCollisionData<Body>?>()
        val listener = built.onContactBegin { collision, _ -> contacts.add(collision) }
        built.step(1)
        assertTrue(contacts.isNotEmpty())
        assertSame(built.bodies[0], contacts.first()!!.getBody1())
        assertTrue(built.removeContactListener(listener))

        val hits = built.raycastWhere(Ray(Vector2(-3.0, 0.0), Vector2(1.0, 0.0)), 10.0) { candidate, _ ->
            candidate === built.bodies[0]
        }
        assertSame(built.bodies[0], hits.single().getBody())
        val closest = built.raycastClosestWhere(Ray(Vector2(-3.0, 0.0), Vector2(1.0, 0.0)), 10.0) { candidate, _ ->
            candidate === built.bodies[0]
        }
        assertSame(built.bodies[0], closest!!.getBody())
        val overlaps = built.find(circle(0.5), Transform()) { candidate, _ -> candidate === built.bodies[0] }
        assertSame(built.bodies[0], overlaps.single().getBody())
        val sweep = built.sweep(circle(0.25), Transform().apply { translate(-3.0, 0.0) }, Vector2(6.0, 0.0)) {
            candidate, _ -> candidate === built.bodies[0]
        }
        assertSame(built.bodies[0], sweep.single().getBody())
    }
}
