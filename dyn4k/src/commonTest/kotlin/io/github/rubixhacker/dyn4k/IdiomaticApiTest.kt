package io.github.rubixhacker.dyn4k

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotSame
import kotlin.test.assertSame
import kotlin.test.assertTrue

class IdiomaticApiTest {
    @Test
    fun vectorOperatorsAndShapePropertiesPreserveMutableCompatibilityObjects() {
        val left: Vector2 = Vector2(2.0, 3.0)
        val right = Vector2(4.0, -1.0)
        val result = left + right
        assertEquals(6.0, result.x)
        assertEquals(2.0, result.y)
        assertNotSame(left, result)
        left += right
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
    }
}
