package portable

import de.infix.testBalloon.framework.core.TestConfig
import de.infix.testBalloon.framework.core.testScope
import de.infix.testBalloon.framework.core.testSuite
import kotlin.time.Duration.Companion.minutes
import org.dyn4j.dynamics.Body
import org.dyn4j.dynamics.ContinuousDetectionMode
import org.dyn4j.dynamics.TimeStep
import org.dyn4j.geometry.Geometry
import org.dyn4j.geometry.MassType
import org.dyn4j.geometry.RotationOperationTap
import org.dyn4j.world.listener.StepListener
import org.dyn4j.world.PhysicsWorld
import org.dyn4j.world.World
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import kotlin.test.assertFailsWith
import kotlin.test.assertSame

val RecorderTestSuite by testSuite(
    testConfig = TestConfig.testScope(isEnabled = true, timeout = 60.minutes),
) {
    test("throwingOutputForBeforeRotationWaitsUntilWorldStepCompletes") { RecorderTest().run { throwingOutputForBeforeRotationWaitsUntilWorldStepCompletes() } }
    test("beforeRotationMarkerKeepsItsOrderAfterTheCompletedStep") { RecorderTest().run { beforeRotationMarkerKeepsItsOrderAfterTheCompletedStep() } }
    test("throwingBeforeRotationMarkerStillCompletesTheWorldStep") { RecorderTest().run { throwingBeforeRotationMarkerStillCompletesTheWorldStep() } }
    test("throwingOutputDuringStepWaitsUntilEngineCompletes") { RecorderTest().run { throwingOutputDuringStepWaitsUntilEngineCompletes() } }
    test("recorderConsumesScopedRotationAfterCompletedStep") { RecorderTest().run { recorderConsumesScopedRotationAfterCompletedStep() } }
    test("failingOutputAfterStepLeavesCompletedEngineState") { RecorderTest().run { failingOutputAfterStepLeavesCompletedEngineState() } }
    test("scopedWorldStepRecordsOnlyItsOwnWorld") { RecorderTest().run { scopedWorldStepRecordsOnlyItsOwnWorld() } }
    test("throwingWorldRegistrationRestoresTapsAndListeners") { RecorderTest().run { throwingWorldRegistrationRestoresTapsAndListeners() } }
    test("throwingInitialOutputRestoresTapsAndListeners") { RecorderTest().run { throwingInitialOutputRestoresTapsAndListeners() } }
    test("acceptedToiObservationKeepsSubclassCallsAndState") { RecorderTest().run { acceptedToiObservationKeepsSubclassCallsAndState() } }
    test("frozenConfigurationUsesCommonWorldGetters") { RecorderTest().run { frozenConfigurationUsesCommonWorldGetters() } }
    test("recordsPublicWorldStateAndSignedZeroAtEveryStep") { RecorderTest().run { recordsPublicWorldStateAndSignedZeroAtEveryStep() } }
}

class RecorderTest {
fun throwingOutputForBeforeRotationWaitsUntilWorldStepCompletes() {
        fun scene(): Pair<World<Body>, Body> {
            val world = World<Body>()
            world.setGravity(0.0, 0.0)
            val body = Body()
            body.addFixture(Geometry.createCircle(0.5))
            body.setMass(MassType.NORMAL)
            body.setAngularVelocity(1.0)
            world.addBody(body)
            return world to body
        }
        val (controlWorld, controlBody) = scene()
        controlBody.getTransform().rotate(0.25)
        controlWorld.step(1, 1.0 / 60.0)

        val (world, body) = scene()
        var completed = 0
        world.addStepListener(object : StepListener<Body> {
            override fun begin(step: TimeStep?, world: PhysicsWorld<Body, *>?) = Unit
            override fun updatePerformed(step: TimeStep?, world: PhysicsWorld<Body, *>?) = Unit
            override fun postSolve(step: TimeStep?, world: PhysicsWorld<Body, *>?) = Unit
            override fun end(step: TimeStep?, world: PhysicsWorld<Body, *>?) { completed++ }
        })
        assertFailsWith<IllegalStateException> {
            RotationOperationTap.capture("before-rotation-output") {
                NumericalRecorder { line ->
                    if (line.contains("\"kind\":\"action\""))
                        throw IllegalStateException("action output failed")
                }.capture(CaseSpec("before-rotation-output", "free-motion", "default",
                    60, 1, emptyMap()), world,
                    before = { _, _ ->
                        body.getTransform().rotate(0.25)
                        "rotate-before-step"
                    })
            }
        }
        assertEquals(1, completed)
        assertEquals(controlBody.getTransform().getValues().toList(),
            body.getTransform().getValues().toList())
        assertEquals(null, RotationOperationTap.currentCapture())
        assertEquals(1, world.getStepListeners().size)
    }

fun beforeRotationMarkerKeepsItsOrderAfterTheCompletedStep() {
        val world = World<Body>()
        world.setGravity(0.0, 0.0)
        val body = Body()
        body.addFixture(Geometry.createCircle(0.5))
        body.setMass(MassType.NORMAL)
        body.setAngularVelocity(1.0)
        world.addBody(body)
        val rows = mutableListOf<String>()
        var completed = 0
        world.addStepListener(object : StepListener<Body> {
            override fun begin(step: TimeStep?, world: PhysicsWorld<Body, *>?) = Unit
            override fun updatePerformed(step: TimeStep?, world: PhysicsWorld<Body, *>?) = Unit
            override fun postSolve(step: TimeStep?, world: PhysicsWorld<Body, *>?) = Unit
            override fun end(step: TimeStep?, world: PhysicsWorld<Body, *>?) { completed++ }
        })
        RotationOperationTap.capture("ordered-before-rotation") {
            NumericalRecorder(
                { rows.add("NUMERICAL_JSON $it") },
                { assertEquals(1, completed); rows.add(it) },
            ).capture(CaseSpec("ordered-before-rotation", "free-motion", "default",
                60, 1, emptyMap()), world,
                before = { _, _ ->
                    body.getTransform().rotate(0.25)
                    "rotate-before-step"
                })
        }
        val action = rows.indexOfFirst { it.contains("\"kind\":\"action\"") }
        val begin = rows.indexOfFirst { it.contains("\"name\":\"step.begin\"") }
        val state = rows.indexOfFirst { it.contains("\"kind\":\"state\"") }
        val rotations = rows.withIndex().filter { it.value.startsWith("PROSPECTIVE_ROTATION_JSON ") }
        assertEquals(2, rotations.size)
        assertTrue(action in 0 until rotations[0].index)
        assertTrue(rotations[0].index < begin)
        assertTrue(begin < rotations[1].index)
        assertTrue(rotations[1].index < state)
        assertTrue(rotations[0].value.contains("\"sequence\":0"))
        assertTrue(rotations[1].value.contains("\"sequence\":1"))
        assertEquals(1, completed)
    }

fun throwingBeforeRotationMarkerStillCompletesTheWorldStep() {
        val world = World<Body>()
        world.setGravity(0.0, 0.0)
        val body = Body()
        body.addFixture(Geometry.createCircle(0.5))
        body.setMass(MassType.NORMAL)
        body.setAngularVelocity(1.0)
        world.addBody(body)
        var completed = 0
        world.addStepListener(object : StepListener<Body> {
            override fun begin(step: TimeStep?, world: PhysicsWorld<Body, *>?) = Unit
            override fun updatePerformed(step: TimeStep?, world: PhysicsWorld<Body, *>?) = Unit
            override fun postSolve(step: TimeStep?, world: PhysicsWorld<Body, *>?) = Unit
            override fun end(step: TimeStep?, world: PhysicsWorld<Body, *>?) { completed++ }
        })
        assertFailsWith<IllegalStateException> {
            RotationOperationTap.capture("throwing-before-marker") {
                NumericalRecorder(
                    { },
                    { throw IllegalStateException("marker output failed") },
                ).capture(CaseSpec("throwing-before-marker", "free-motion", "default",
                    60, 1, emptyMap()), world,
                    before = { _, _ ->
                        body.getTransform().rotate(0.25)
                        "rotate-before-step"
                    })
            }
        }
        assertEquals(1, completed)
        assertEquals(null, RotationOperationTap.currentCapture())
        assertEquals(1, world.getStepListeners().size)
    }

fun throwingOutputDuringStepWaitsUntilEngineCompletes() {
        val world = World<Body>()
        world.setGravity(0.0, 0.0)
        val body = Body()
        body.addFixture(Geometry.createCircle(0.5))
        body.setMass(MassType.NORMAL)
        body.setAngularVelocity(1.0)
        world.addBody(body)
        var completed = 0
        world.addStepListener(object : StepListener<Body> {
            override fun begin(step: TimeStep?, world: PhysicsWorld<Body, *>?) = Unit
            override fun updatePerformed(step: TimeStep?, world: PhysicsWorld<Body, *>?) = Unit
            override fun postSolve(step: TimeStep?, world: PhysicsWorld<Body, *>?) = Unit
            override fun end(step: TimeStep?, world: PhysicsWorld<Body, *>?) {
                completed++
            }
        })
        assertFailsWith<IllegalStateException> {
            RotationOperationTap.capture("throwing-step-output") {
                NumericalRecorder { line ->
                    if (line.contains("\"name\":\"step.postSolve\""))
                        throw IllegalStateException("event output failed")
                }.capture(CaseSpec("throwing-step-output", "free-motion", "default",
                    60, 1, emptyMap()), world)
            }
        }
        assertEquals(1, completed)
        assertEquals(null, RotationOperationTap.currentCapture())
    }
fun recorderConsumesScopedRotationAfterCompletedStep() {
        val world = World<Body>()
        world.setGravity(0.0, 0.0)
        val body = Body()
        body.addFixture(Geometry.createCircle(0.5))
        body.setMass(MassType.NORMAL)
        body.setAngularVelocity(1.0)
        world.addBody(body)
        RotationOperationTap.capture("recorder-probe") { scope ->
            NumericalRecorder { }.capture(
                CaseSpec("recorded-rotation", "free-motion", "default", 60, 1,
                    emptyMap()), world)
            assertTrue(scope.drain().isEmpty())
        }
    }

fun failingOutputAfterStepLeavesCompletedEngineState() {
        fun scene(): Pair<World<Body>, Body> {
            val world = World<Body>()
            world.setGravity(0.0, 0.0)
            val body = Body()
            body.addFixture(Geometry.createCircle(0.5))
            body.setMass(MassType.NORMAL)
            body.setAngularVelocity(1.0)
            world.addBody(body)
            return world to body
        }
        val (controlWorld, controlBody) = scene()
        controlWorld.step(1, 1.0 / 60.0)
        val (observedWorld, observedBody) = scene()
        assertFailsWith<IllegalStateException> {
            RotationOperationTap.capture("throwing-state-output") {
                NumericalRecorder { line ->
                    if (line.contains("\"kind\":\"state\""))
                        throw IllegalStateException("state output failed")
                }.capture(CaseSpec("throwing-state-output", "free-motion", "default",
                    60, 1, emptyMap()), observedWorld)
            }
        }
        assertEquals(controlBody.getTransform().getValues().toList(),
            observedBody.getTransform().getValues().toList())
        assertEquals(null, RotationOperationTap.currentCapture())
        assertTrue(observedWorld.getStepListeners().isEmpty())
    }
fun scopedWorldStepRecordsOnlyItsOwnWorld() {
        val owned = World<Body>()
        val foreign = World<Body>()
        RotationOperationTap.capture("world-probe") { scope ->
            scope.captureStep(owned) { owned.step(1, 1.0 / 60.0) }
            assertTrue(scope.drain().isEmpty())
        }
        assertFailsWith<IllegalStateException> {
            RotationOperationTap.capture("foreign-world-probe") { scope ->
                scope.captureStep(owned) {
                    owned.step(1, 1.0 / 60.0)
                    foreign.step(1, 1.0 / 60.0)
                }
            }
        }
    }
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
        RotationOperationTap.capture("throwing-registration") { scope ->
            assertFailsWith<IllegalStateException> {
                NumericalRecorder { }.capture(
                    CaseSpec("throwing-registration", "free-motion", "default", 60, 1,
                        emptyMap()), world)
            }
            assertSame(scope, RotationOperationTap.currentCapture())
            assertTrue(world.getContactListeners().isEmpty())
            assertTrue(world.getTimeOfImpactListeners().isEmpty())
            assertTrue(world.getStepListeners().isEmpty())
        }
        assertEquals(null, RotationOperationTap.currentCapture())
    }

fun throwingInitialOutputRestoresTapsAndListeners() {
        val world = World<Body>()
        val body = Body()
        body.addFixture(Geometry.createCircle(0.5))
        body.setMass(MassType.NORMAL)
        world.addBody(body)
        RotationOperationTap.capture("throwing-output") { scope ->
            assertFailsWith<IllegalStateException> {
                NumericalRecorder { throw IllegalStateException("emit failed") }.capture(
                    CaseSpec("throwing-output", "free-motion", "default", 60, 1,
                        emptyMap()), world)
            }
            assertSame(scope, RotationOperationTap.currentCapture())
            assertTrue(world.getContactListeners().isEmpty())
            assertTrue(world.getTimeOfImpactListeners().isEmpty())
            assertTrue(world.getStepListeners().isEmpty())
        }
        assertEquals(null, RotationOperationTap.currentCapture())
    }

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
            if (observe) RotationOperationTap.capture("accepted-toi") { scope ->
                scope.captureStep(world) { world.step(1, 1.0 / 30.0) }
                accepted = scope.drain().count {
                    it is RotationOperationTap.Observation.ToiAccepted
                }
            } else {
                world.step(1, 1.0 / 30.0)
            }
            return Result(ground.checks, bullet.checks, accepted,
                ground.getTransform().getValues().toList() +
                bullet.getTransform().getValues().toList() +
                listOf(bullet.getLinearVelocity().x, bullet.getLinearVelocity().y))
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
