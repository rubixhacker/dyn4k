package org.dyn4j.geometry

import de.infix.testBalloon.framework.core.testSuite
import org.dyn4j.world.World
import org.dyn4j.dynamics.Body
import org.dyn4j.dynamics.TimeStep
import org.dyn4j.world.PhysicsWorld
import org.dyn4j.world.listener.StepListenerAdapter
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertSame
import kotlin.test.assertTrue

val RotationObservationIsolationTest by testSuite {
    test("observedRotationMatchesOrdinaryRotation") { RotationObservationIsolationTestFixture().run { observedRotationMatchesOrdinaryRotation() } }
    test("nestedObservationRestoresOuterScope") { RotationObservationIsolationTestFixture().run { nestedObservationRestoresOuterScope() } }
    test("foreignWorldStepFailsCaptureAfterBothWorldsComplete") { RotationObservationIsolationTestFixture().run { foreignWorldStepFailsCaptureAfterBothWorldsComplete() } }
    test("failedWorldObservationCannotBeClearedByAnotherStep") { RotationObservationIsolationTestFixture().run { failedWorldObservationCannotBeClearedByAnotherStep() } }
    test("stepCallbackCannotConsumeOperationRecordsBeforeStepEnds") { RotationObservationIsolationTestFixture().run { stepCallbackCannotConsumeOperationRecordsBeforeStepEnds() } }
}

private class RotationObservationIsolationTestFixture  {
fun observedRotationMatchesOrdinaryRotation() {
        val ordinary = Transform()
        ordinary.rotate(0.25)
        val captured = Transform()
        val records = RotationOperationTap.capture("rotation") { scope ->
            captured.rotate(0.25)
            scope.drain()
        }
        val call = records.single() as RotationOperationTap.Observation.Rotation
        assertSame(captured, call.call.target)
        assertEquals(0.25.toBits(), call.call.angleBits)
        assertEquals(ordinary.getValues().toList(), captured.getValues().toList())
    }

fun nestedObservationRestoresOuterScope() {
        RotationOperationTap.capture("outer") { outer ->
            Transform().rotate(0.25)
            RotationOperationTap.capture("inner") { inner ->
                Transform().rotate(0.5)
                assertEquals(1, inner.drain().size)
            }
            assertSame(outer, RotationOperationTap.currentCapture())
            assertEquals(1, outer.drain().size)
        }
        assertEquals(null, RotationOperationTap.currentCapture())
    }

fun foreignWorldStepFailsCaptureAfterBothWorldsComplete() {
        val owned = World<Body>()
        val foreign = World<Body>()
        assertFailsWith<IllegalStateException> {
            RotationOperationTap.capture("world") { scope ->
                scope.captureStep(owned) {
                    owned.step(1, 1.0 / 60.0)
                    foreign.step(1, 1.0 / 60.0)
                }
            }
        }
        assertEquals(null, RotationOperationTap.currentCapture())
        assertTrue(owned.getStepListeners().isEmpty())
        assertTrue(foreign.getStepListeners().isEmpty())
    }

fun failedWorldObservationCannotBeClearedByAnotherStep() {
        val owned = World<Body>()
        val foreign = World<Body>()
        assertFailsWith<IllegalStateException> {
            RotationOperationTap.capture("sticky-failure") { scope ->
                assertFailsWith<IllegalStateException> {
                    scope.captureStep(owned) { foreign.step(1, 1.0 / 60.0) }
                }
                scope.captureStep(owned) { owned.step(1, 1.0 / 60.0) }
            }
        }
        assertEquals(null, RotationOperationTap.currentCapture())
    }

fun stepCallbackCannotConsumeOperationRecordsBeforeStepEnds() {
        val world = World<Body>()
        world.setGravity(0.0, 0.0)
        val body = Body()
        body.addFixture(Geometry.createCircle(0.5))
        body.setMass(MassType.NORMAL)
        body.setAngularVelocity(1.0)
        world.addBody(body)
        lateinit var scope: RotationOperationTap.Capture
        var completed = 0
        var stolen = -1
        world.addStepListener(object : StepListenerAdapter<Body>() {
            override fun end(step: TimeStep?, world: PhysicsWorld<Body, *>?) {
                val exposed = scope.drain()
                stolen = exposed.size
                for (record in exposed) {
                    val rotation = record as? RotationOperationTap.Observation.Rotation
                    rotation?.call?.target?.identity()
                }
                completed++
            }
        })
        assertFailsWith<IllegalStateException> {
            RotationOperationTap.capture("callback-attempt") { capture ->
                scope = capture
                capture.captureStep(world) { world.step(1, 1.0 / 60.0) }
            }
        }
        assertEquals(1, completed)
        assertEquals(0, stolen)
        assertTrue(body.getTransform().getRotationAngle() != 0.0)
        assertEquals(null, RotationOperationTap.currentCapture())
    }
}
