package portable

import org.dyn4j.geometry.RotationOperationTap
import org.dyn4j.geometry.Transform
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertSame
import kotlin.test.assertTrue

class ProspectiveArithmeticTest {
    @Test
    fun nestedCapturesKeepTheirOwnOperationsAndRestoreOuterScope() {
        val outer = Transform()
        val inner = Transform()
        RotationOperationTap.capture("outer") { outerScope ->
            outer.rotate(0.25)
            RotationOperationTap.capture("inner") { innerScope ->
                inner.rotate(0.5)
                val innerCall = innerScope.drain().single()
                    as RotationOperationTap.Observation.Rotation
                assertSame(inner, innerCall.call.target)
            }
            assertSame(outerScope, RotationOperationTap.currentCapture())
            val outerCall = outerScope.drain().single()
                as RotationOperationTap.Observation.Rotation
            assertSame(outer, outerCall.call.target)
        }
        assertEquals(null, RotationOperationTap.currentCapture())
    }
    @Test
    fun scopedObservationCompletesRotationBeforeConsumerFailure() {
        val transform = Transform()
        val expected = Transform().also { it.rotate(0.25) }
        val observed = RotationOperationTap.capture("failure-probe") { scope ->
            transform.rotate(0.25)
            scope.drain()
        }
        assertEquals(1, observed.size)
        assertEquals(expected.getValues().toList(), transform.getValues().toList())
        try {
            observed.forEach { throw IllegalStateException("consumer failed") }
        } catch (_: IllegalStateException) {
        }
        assertEquals(expected.getValues().toList(), transform.getValues().toList())
    }
    @Test fun observedProbe() = observe("observedProbe") {
        val value = Transform()
        value.rotate(0.25)
        val end = Transform()
        end.rotate(0.5)
        value.lerp(end, 0.5)
        assertTrue(value.getCost().isFinite())
    }

    private fun observe(method: String, run: () -> Unit) {
        RotationOperationTap.capture(method) { capture ->
            run()
            for (observation in capture.drain()) {
                val rotation = observation as? RotationOperationTap.Observation.Rotation
                    ?: error("accepted TOI observation outside recorder")
                println("PROSPECTIVE_ROTATION_JSON " +
                    ProspectiveOperationMarker.encode(capture, rotation.call))
            }
        }
    }

    @Test fun captureGeometry() = observe("geometryCollisionBoundaryAndScale") {
        PortableMatrixTest().geometryCollisionBoundaryAndScale()
    }
    @Test fun captureFreeMotion() = observe("freeMotionForcesDampingAndRestitution") {
        PortableMatrixTest().freeMotionForcesDampingAndRestitution()
    }
    @Test fun captureDefaultContacts() = observe("defaultContactsFrictionSleepAndWake") {
        PortableMatrixTest().defaultContactsFrictionSleepAndWake()
    }
    @Test fun captureConfigured30Repeat1() = observe("configured30Repeat1") { PortableMatrixTest().configured30Repeat1() }
    @Test fun captureConfigured30Repeat2() = observe("configured30Repeat2") { PortableMatrixTest().configured30Repeat2() }
    @Test fun captureConfigured60Repeat1() = observe("configured60Repeat1") { PortableMatrixTest().configured60Repeat1() }
    @Test fun captureConfigured60Repeat2() = observe("configured60Repeat2") { PortableMatrixTest().configured60Repeat2() }
    @Test fun captureConfigured120Repeat1() = observe("configured120Repeat1") { PortableMatrixTest().configured120Repeat1() }
    @Test fun captureConfigured120Repeat2() = observe("configured120Repeat2") { PortableMatrixTest().configured120Repeat2() }
    @Test fun captureJoints() = observe("everyJointWithInitialAndApplicableActiveModes") {
        PortableMatrixTest().everyJointWithInitialAndApplicableActiveModes()
    }
    @Test fun captureWheelActive() = observe("everyJointWithInitialAndApplicableActiveModes") {
        PortableMatrixTest().captureJointCase("Wheel", "active")
    }
    @Test fun captureJointBooleanModes() = observe("independentJointBooleanModes") {
        PortableMatrixTest().independentJointBooleanModes()
    }
    @Test fun captureJointNumericModes() = observe("independentJointNumericAndLimitModes") {
        PortableMatrixTest().independentJointNumericAndLimitModes()
    }
    @Test fun captureAngleFailure() = observe("baselineAngleNegativeRatioRemainsAnIsolatedPhysicalFailure") {
        PortableMatrixTest().baselineAngleNegativeRatioRemainsAnIsolatedPhysicalFailure()
    }
    @Test fun captureCcd() = observe("continuousCollisionCasesAtFrozenRates") {
        PortableMatrixTest().continuousCollisionCasesAtFrozenRates()
    }
    @Test fun captureLongMotion() = observe("longRunningFreeMotionInvariantScene") {
        PortableMatrixTest().longRunningFreeMotionInvariantScene()
    }

    @Test
    fun executedRotateAndDirectReset() {
        RotationOperationTap.capture("direct-reset-probe") { scope ->
            val value = Transform()
            value.rotate(0.25)
            val calls = scope.drain().map {
                (it as RotationOperationTap.Observation.Rotation).call
            }
            assertEquals(1, calls.size)
            assertEquals("rotate", calls[0].kind)
            assertEquals(0.25.toBits(), calls[0].angleBits)
            assertEquals(value.getCost().toBits(), calls[0].postCost.toBits())
            assertEquals(value.getSint().toBits(), calls[0].postSint.toBits())
            val end = Transform()
            end.rotate(0.5)
            assertEquals(1, scope.drain().size)
            value.lerp(end, 0.5)
            val reset = scope.drain().map {
                (it as RotationOperationTap.Observation.Rotation).call
            }
            assertEquals(1, reset.size)
            assertEquals("lerp-reset", reset.last().kind)
            assertEquals(value.getCost().toBits(), reset.last().postCost.toBits())
            assertTrue(reset.last().angleBits != null)
        }
    }
}
