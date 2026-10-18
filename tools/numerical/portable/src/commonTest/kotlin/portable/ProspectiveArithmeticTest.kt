package portable

import org.dyn4j.geometry.RotationOperationTap
import org.dyn4j.geometry.Transform
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class ProspectiveArithmeticTest {
    @Test fun observedProbe() = observe("observedProbe") {
        val value = Transform()
        value.rotate(0.25)
        val end = Transform()
        end.rotate(0.5)
        value.lerp(end, 0.5)
        assertTrue(value.getCost().isFinite())
    }

    private fun hex(value: Double): String = value.toBits().toULong().toString(16).padStart(16, '0')
    private fun hexNullable(value: Double?): String = if (value == null) "null" else "\"${hex(value)}\""
    private fun bits(value: Long?): String = if (value == null) "null"
        else "\"${value.toULong().toString(16).padStart(16, '0')}\""

    private fun observe(method: String, run: () -> Unit) {
        check(RotationOperationTap.listener == null)
        val targets = mutableMapOf<Transform, Int>()
        var sequence = 0
        RotationOperationTap.listener = { call ->
            val target = targets.getOrPut(call.target) { targets.size }
            println("PROSPECTIVE_ROTATION_JSON " +
                "{\"schema\":\"portable-rotation-op/1\",\"method\":\"$method\"," +
                "\"sequence\":${sequence++},\"target_token\":$target," +
                "\"kind\":\"${call.kind}\",\"source\":\"${call.source}\"," +
                "\"pre\":[\"${hex(call.preCost)}\",\"${hex(call.preSint)}\"]," +
                "\"trig\":[\"${hex(call.trigCost)}\",\"${hex(call.trigSint)}\"]," +
                "\"raw\":[${hexNullable(call.rawCost)},${hexNullable(call.rawSint)}]," +
                "\"post\":[\"${hex(call.postCost)}\",\"${hex(call.postSint)}\"]," +
                "\"angle_bits\":${bits(call.angleBits)}," +
                "\"alpha_bits\":${hexNullable(call.alpha)}," +
                "\"start_angle_bits\":${hexNullable(call.startAngle)}," +
                "\"end_angle_bits\":${hexNullable(call.endAngle)}," +
                "\"diff_bits\":${hexNullable(call.difference)}," +
                "\"start\":[${hexNullable(call.startCost)},${hexNullable(call.startSint)}]," +
                "\"end\":[${hexNullable(call.endCost)},${hexNullable(call.endSint)}]}")
        }
        try {
            run()
        } finally {
            RotationOperationTap.listener = null
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
        val calls = mutableListOf<RotationOperationTap.Call>()
        RotationOperationTap.listener = { calls.add(it) }
        try {
            val value = Transform()
            value.rotate(0.25)
            assertEquals(1, calls.size)
            assertEquals("rotate", calls[0].kind)
            assertEquals(0.25.toBits(), calls[0].angleBits)
            assertEquals(value.getCost().toBits(), calls[0].postCost.toBits())
            assertEquals(value.getSint().toBits(), calls[0].postSint.toBits())
            val end = Transform()
            end.rotate(0.5)
            val count = calls.size
            value.lerp(end, 0.5)
            assertEquals(count + 1, calls.size)
            assertEquals("lerp-reset", calls.last().kind)
            assertEquals(value.getCost().toBits(), calls.last().postCost.toBits())
            assertTrue(calls.last().angleBits != null)
        } finally {
            RotationOperationTap.listener = null
        }
    }
}
