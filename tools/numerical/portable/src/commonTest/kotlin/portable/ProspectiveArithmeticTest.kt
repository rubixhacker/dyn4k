package portable

import de.infix.testBalloon.framework.core.TestConfig
import de.infix.testBalloon.framework.core.testScope
import de.infix.testBalloon.framework.core.testSuite
import kotlin.time.Duration.Companion.minutes
import org.dyn4j.geometry.RotationOperationTap
import org.dyn4j.geometry.Transform
import kotlin.test.assertEquals
import kotlin.test.assertSame
import kotlin.test.assertTrue

val ProspectiveArithmeticTestSuite by testSuite(
    testConfig = TestConfig.testScope(isEnabled = true, timeout = 60.minutes),
) {
    test("nestedCapturesKeepTheirOwnOperationsAndRestoreOuterScope") { ProspectiveArithmeticTest().run { nestedCapturesKeepTheirOwnOperationsAndRestoreOuterScope() } }
    test("scopedObservationCompletesRotationBeforeConsumerFailure") { ProspectiveArithmeticTest().run { scopedObservationCompletesRotationBeforeConsumerFailure() } }
    test("observedProbe") { ProspectiveArithmeticTest().run { observedProbe() } }
    test("captureGeometry") { ProspectiveArithmeticTest().run { captureGeometry() } }
    test("captureFreeMotion") { ProspectiveArithmeticTest().run { captureFreeMotion() } }
    test("captureDefaultContacts") { ProspectiveArithmeticTest().run { captureDefaultContacts() } }
    test("captureConfigured30Repeat1") { ProspectiveArithmeticTest().run { captureConfigured30Repeat1() } }
    test("captureConfigured30Repeat2") { ProspectiveArithmeticTest().run { captureConfigured30Repeat2() } }
    test("captureConfigured60Repeat1") { ProspectiveArithmeticTest().run { captureConfigured60Repeat1() } }
    test("captureConfigured60Repeat2") { ProspectiveArithmeticTest().run { captureConfigured60Repeat2() } }
    test("captureConfigured120Repeat1") { ProspectiveArithmeticTest().run { captureConfigured120Repeat1() } }
    test("captureConfigured120Repeat2") { ProspectiveArithmeticTest().run { captureConfigured120Repeat2() } }
    test("captureJoints") { ProspectiveArithmeticTest().run { captureJoints() } }
    test("captureWheelActive") { ProspectiveArithmeticTest().run { captureWheelActive() } }
    test("wheelCaseWithoutOperationCapture") { ProspectiveArithmeticTest().run { wheelCaseWithoutOperationCapture() } }
    test("captureJointBooleanModes") { ProspectiveArithmeticTest().run { captureJointBooleanModes() } }
    test("captureJointNumericModes") { ProspectiveArithmeticTest().run { captureJointNumericModes() } }
    test("captureAngleFailure") { ProspectiveArithmeticTest().run { captureAngleFailure() } }
    test("captureCcd") { ProspectiveArithmeticTest().run { captureCcd() } }
    test("captureLongMotion") { ProspectiveArithmeticTest().run { captureLongMotion() } }
    test("executedRotateAndDirectReset") { ProspectiveArithmeticTest().run { executedRotateAndDirectReset() } }
}

class ProspectiveArithmeticTest {
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
fun observedProbe() = observe("observedProbe") {
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

fun captureGeometry() = observe("geometryCollisionBoundaryAndScale") {
        PortableMatrixTest().geometryCollisionBoundaryAndScale()
    }
fun captureFreeMotion() = observe("freeMotionForcesDampingAndRestitution") {
        PortableMatrixTest().freeMotionForcesDampingAndRestitution()
    }
fun captureDefaultContacts() = observe("defaultContactsFrictionSleepAndWake") {
        PortableMatrixTest().defaultContactsFrictionSleepAndWake()
    }
fun captureConfigured30Repeat1() = observe("configured30Repeat1") { PortableMatrixTest().configured30Repeat1() }
fun captureConfigured30Repeat2() = observe("configured30Repeat2") { PortableMatrixTest().configured30Repeat2() }
fun captureConfigured60Repeat1() = observe("configured60Repeat1") { PortableMatrixTest().configured60Repeat1() }
fun captureConfigured60Repeat2() = observe("configured60Repeat2") { PortableMatrixTest().configured60Repeat2() }
fun captureConfigured120Repeat1() = observe("configured120Repeat1") { PortableMatrixTest().configured120Repeat1() }
fun captureConfigured120Repeat2() = observe("configured120Repeat2") { PortableMatrixTest().configured120Repeat2() }
fun captureJoints() = observe("everyJointWithInitialAndApplicableActiveModes") {
        PortableMatrixTest().everyJointWithInitialAndApplicableActiveModes()
    }
fun captureWheelActive() = observe("everyJointWithInitialAndApplicableActiveModes") {
        PortableMatrixTest().captureJointCase("Wheel", "active")
    }
fun wheelCaseWithoutOperationCapture() {
        assertEquals(null, RotationOperationTap.currentCapture())
        PortableMatrixTest().captureJointCase("Wheel", "active")
        assertEquals(null, RotationOperationTap.currentCapture())
    }
fun captureJointBooleanModes() = observe("independentJointBooleanModes") {
        PortableMatrixTest().independentJointBooleanModes()
    }
fun captureJointNumericModes() = observe("independentJointNumericAndLimitModes") {
        PortableMatrixTest().independentJointNumericAndLimitModes()
    }
fun captureAngleFailure() = observe("baselineAngleNegativeRatioRemainsAnIsolatedPhysicalFailure") {
        PortableMatrixTest().baselineAngleNegativeRatioRemainsAnIsolatedPhysicalFailure()
    }
fun captureCcd() = observe("continuousCollisionCasesAtFrozenRates") {
        PortableMatrixTest().continuousCollisionCasesAtFrozenRates()
    }
fun captureLongMotion() = observe("longRunningFreeMotionInvariantScene") {
        PortableMatrixTest().longRunningFreeMotionInvariantScene()
    }

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
