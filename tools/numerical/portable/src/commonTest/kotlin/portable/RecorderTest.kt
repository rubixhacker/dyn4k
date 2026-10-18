package portable

import org.dyn4j.dynamics.Body
import org.dyn4j.dynamics.ContinuousDetectionMode
import org.dyn4j.geometry.Geometry
import org.dyn4j.geometry.MassType
import org.dyn4j.geometry.RotationOperationTap
import org.dyn4j.world.listener.StepListener
import org.dyn4j.world.ToiAcceptedResetTap
import org.dyn4j.world.World
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import kotlin.test.assertFailsWith
import kotlin.test.assertSame

class RecorderTest {
    @Test
    fun throwingWorldRegistrationRestoresTapsAndListeners() {
        val world = object : World<Body>() {
            override fun addStepListener(listener: StepListener<Body>?): Boolean {
                super.addStepListener(listener)
                throw IllegalStateException("registration failed")
            }
        }
        val body = Body()
        body.addFixture(Geometry.createCircle(0.5))
        body.setMass(MassType.NORMAL)
        world.addBody(body)
        val previousRotation = RotationOperationTap.listener
        val previousReset = ToiAcceptedResetTap.listener
        val rotation: (RotationOperationTap.Call) -> Unit = {}
        val reset: (Any, Any, Double, Boolean) -> Unit = { _, _, _, _ -> }
        RotationOperationTap.listener = rotation
        ToiAcceptedResetTap.listener = reset
        try {
            assertFailsWith<IllegalStateException> {
                NumericalRecorder { }.capture(
                    CaseSpec("throwing-registration", "free-motion", "default", 60, 1,
                        emptyMap()), world)
            }
            assertSame(rotation, RotationOperationTap.listener)
            assertSame(reset, ToiAcceptedResetTap.listener)
            assertTrue(world.getContactListeners().isEmpty())
            assertTrue(world.getTimeOfImpactListeners().isEmpty())
            assertTrue(world.getStepListeners().isEmpty())
        } finally {
            RotationOperationTap.listener = previousRotation
            ToiAcceptedResetTap.listener = previousReset
        }
    }

    @Test
    fun throwingInitialOutputRestoresTapsAndListeners() {
        val world = World<Body>()
        val body = Body()
        body.addFixture(Geometry.createCircle(0.5))
        body.setMass(MassType.NORMAL)
        world.addBody(body)
        val previousRotation = RotationOperationTap.listener
        val previousReset = ToiAcceptedResetTap.listener
        val rotation: (RotationOperationTap.Call) -> Unit = {}
        val reset: (Any, Any, Double, Boolean) -> Unit = { _, _, _, _ -> }
        RotationOperationTap.listener = rotation
        ToiAcceptedResetTap.listener = reset
        try {
            assertFailsWith<IllegalStateException> {
                NumericalRecorder { throw IllegalStateException("emit failed") }.capture(
                    CaseSpec("throwing-output", "free-motion", "default", 60, 1,
                        emptyMap()), world)
            }
            assertSame(rotation, RotationOperationTap.listener)
            assertSame(reset, ToiAcceptedResetTap.listener)
            assertTrue(world.getContactListeners().isEmpty())
            assertTrue(world.getTimeOfImpactListeners().isEmpty())
            assertTrue(world.getStepListeners().isEmpty())
        } finally {
            RotationOperationTap.listener = previousRotation
            ToiAcceptedResetTap.listener = previousReset
        }
    }

    @Test
    fun acceptedToiObservationKeepsSubclassCallsAndState() {
        class CountingBody : Body() {
            var checks = 0
            override fun isDynamic(): Boolean {
                checks++
                return super.isDynamic()
            }
        }
        data class Result(val groundChecks: Int, val bulletChecks: Int,
                          val accepted: Int, val state: List<Double>)
        fun run(observe: Boolean): Result {
            val world = World<Body>()
            world.setGravity(0.0, 0.0)
            world.getSettings().setContinuousDetectionMode(ContinuousDetectionMode.ALL)
            val ground = CountingBody()
            ground.addFixture(Geometry.createRectangle(20.0, 0.05))
            ground.setMass(MassType.INFINITE)
            world.addBody(ground)
            val bullet = CountingBody()
            bullet.addFixture(Geometry.createCircle(0.1))
            bullet.translate(0.0, 1.0)
            bullet.setMass(MassType.NORMAL)
            bullet.setLinearVelocity(0.0, -120.0)
            bullet.setBullet(true)
            world.addBody(bullet)
            var accepted = 0
            val previous = ToiAcceptedResetTap.listener
            if (observe) ToiAcceptedResetTap.listener = { _, _, _, _ -> accepted++ }
            try {
                world.step(1, 1.0 / 30.0)
                return Result(ground.checks, bullet.checks, accepted,
                    ground.getTransform().getValues().toList() +
                    bullet.getTransform().getValues().toList() +
                    listOf(bullet.getLinearVelocity().x, bullet.getLinearVelocity().y))
            } finally {
                ToiAcceptedResetTap.listener = previous
            }
        }
        val default = run(false)
        val observed = run(true)
        assertEquals(0, default.accepted)
        assertEquals(1, observed.accepted)
        assertEquals(3, default.groundChecks)
        assertEquals(2, default.bulletChecks)
        assertEquals(default.groundChecks, observed.groundChecks)
        assertEquals(default.bulletChecks, observed.bulletChecks)
        assertEquals(default.state, observed.state)
    }

    @Test
    fun frozenConfigurationUsesCommonWorldGetters() {
        val world = World<Body>()
        val body = Body()
        body.addFixture(Geometry.createCircle(0.5))
        body.setMass(MassType.NORMAL)
        world.addBody(body)
        val lines = mutableListOf<String>()
        NumericalRecorder(lines::add).capture(
            CaseSpec("long-free-60", "long-running-invariant", "default", 60, 1,
                mapOf("velocity" to listOf(0.0, 0.0))), world)
        assertTrue(lines.first().contains("\"frozenConfiguration\""))
        assertTrue(lines.first().contains("\"getBroadphaseDetector\""))
        assertTrue(lines.first().contains("\"getTimeOfImpactDetector\""))
        assertTrue(lines.first().contains("\"getAngularToleranceSquared\""))
    }

    @Test
    fun recordsPublicWorldStateAndSignedZeroAtEveryStep() {
        val world = World<Body>()
        world.setGravity(0.0, 0.0)
        val body = Body()
        body.addFixture(Geometry.createCircle(0.5))
        body.setMass(MassType.NORMAL)
        body.setLinearVelocity(-0.0, 1.0)
        world.addBody(body)
        val lines = mutableListOf<String>()
        NumericalRecorder(lines::add).capture(
            CaseSpec("red-green", "free-motion", "default", 60, 2,
                mapOf("velocity" to listOf(-0.0, 1.0))), world,
            observe = { mapOf("signedZero" to -0.0) }
        )
        assertTrue(lines.size >= 4)
        assertTrue(lines.first().contains("\"velocity\":[-0.0,"))
        assertTrue(lines.first().contains("\"fixtures\""))
        assertTrue(lines.first().contains("\"radius\":0.5"))
        assertTrue(lines.any { it.contains("\"kind\":\"state\"") && it.contains("\"signedZero\":-0.0") })
        assertEquals(2, lines.count { it.contains("\"kind\":\"state\"") })
        assertTrue(lines.any { it.contains("\"kind\":\"state\"") && it.contains("\"step\":1") })
        assertTrue(lines.any { it.contains("\"kind\":\"state\"") && it.contains("\"step\":2") })
        assertTrue(lines.last().contains("\"kind\":\"case-end\""))
    }
}
