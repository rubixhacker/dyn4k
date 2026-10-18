package org.dyn4j.collision.narrowphase

import kotlinx.cinterop.ExperimentalForeignApi
import kotlinx.cinterop.alloc
import kotlinx.cinterop.memScoped
import kotlinx.cinterop.ptr
import kotlin.math.sqrt
import kotlin.test.Test
import kotlin.test.assertEquals
import org.dyn4j.coverage.collision.shapes.a.CapsuleSliceTest
import org.dyn4j.coverage.collision.shapes.a.CirclePolygonTest
import org.dyn4j.coverage.collision.shapes.a.CircleSegmentTest
import org.dyn4j.coverage.collision.shapes.a.CircleSliceTest
import org.dyn4j.coverage.collision.shapes.a.PolygonCapsuleTest
import org.dyn4j.coverage.collision.shapes.a.PolygonPolygonTest
import platform.posix.fegetenv
import platform.posix.fenv_t
import platform.posix.fesetenv
import platform.windows.GetCurrentThreadId

@OptIn(ExperimentalForeignApi::class)
class WindowsCollisionPrecisionControlTest {
    private data class ScalarInput(val id: String, val xBits: Long, val yBits: Long, val rootBits: Long, val reciprocalBits: Long)

    private val inputs = listOf(
        ScalarInput("CirclePolygon.edge3", -4621899953565315924L, -4625196817309499400L, 4602678819172646911L, 4611686018427387905L),
        ScalarInput("CapsuleSlice.epa4", 4603460912955918154L, -4617903595553423057L, 4607182418800017407L, 4607182418800017409L),
        ScalarInput("CirclePolygon.epa3", -4619490269450149183L, -4618227961596862473L, 4607182418800017407L, 4607182418800017409L),
        ScalarInput("CircleSegment.epa2", -4621644133008675367L, -4617140533381304871L, 4607182418800017407L, 4607182418800017409L),
        ScalarInput("CircleSlice.epa35", 4606804953716818183L, 4598831979030654181L, 4607182418800017407L, 4607182418800017409L),
        ScalarInput("PolygonCapsule.sat1", -4624133661653997234L, 4606741575090066687L, 4607182418800017407L, 4607182418800017409L),
        ScalarInput("PolygonCapsule.sat4", 4605462196814083239L, -4619902518423102882L, 4607182418800017407L, 4607182418800017409L)
    )

    @Test fun scalarVectorsPc53() {
        inputs.forEach { emitScalar("before", it) }
        withPc53("scalarVectors") {
            val measured = inputs.map { input -> input to emitScalar("pc53", input) }
            measured.forEach { (input, values) ->
                val (root, reciprocal) = values
                assertEquals(input.rootBits, root.toRawBits(), "${input.id} root")
                assertEquals(input.reciprocalBits, reciprocal.toRawBits(), "${input.id} reciprocal")
            }
        }
    }

    @Test fun tracePc53() {
        val diagnostic = WindowsCollisionIntermediateDiagnosticTest()
        withPc53("trace") {
            diagnostic.capsuleSlice()
            diagnostic.circlePolygon()
            diagnostic.circleSegment()
            diagnostic.circleSlice()
            diagnostic.polygonCapsule()
            diagnostic.polygonPolygon()
        }
    }

    @Test fun capsuleSliceDetectGjkPc53() {
        val fixture = CapsuleSliceTest()
        withPc53("CapsuleSlice.detectGjk") { fixture.detectGjk() }
    }

    @Test fun capsuleSliceGetClipManifoldPc53() {
        val fixture = CapsuleSliceTest()
        withPc53("CapsuleSlice.getClipManifold") { fixture.getClipManifold() }
    }

    @Test fun circlePolygonDetectGjkPc53() {
        val fixture = CirclePolygonTest()
        withPc53("CirclePolygon.detectGjk") { fixture.detectGjk() }
    }

    @Test fun circleSegmentDetectGjkPc53() {
        val fixture = CircleSegmentTest()
        withPc53("CircleSegment.detectGjk") { fixture.detectGjk() }
    }

    @Test fun circleSliceDetectGjkPc53() {
        val fixture = CircleSliceTest()
        withPc53("CircleSlice.detectGjk") { fixture.detectGjk() }
    }

    @Test fun polygonCapsuleDetectSatPc53() {
        val fixture = PolygonCapsuleTest()
        withPc53("PolygonCapsule.detectSat") { fixture.detectSat() }
    }

    @Test fun polygonCapsuleGetClipManifoldPc53() {
        val fixture = PolygonCapsuleTest()
        withPc53("PolygonCapsule.getClipManifold") { fixture.getClipManifold() }
    }

    @Test fun polygonPolygonDetectSatPc53() {
        val fixture = PolygonPolygonTest()
        withPc53("PolygonPolygon.detectSat") { fixture.detectSat() }
    }

    @Test fun polygonPolygonGetClipManifoldPc53() {
        val fixture = PolygonPolygonTest()
        withPc53("PolygonPolygon.getClipManifold") { fixture.getClipManifold() }
    }

    private fun emitScalar(mode: String, input: ScalarInput): Pair<Double, Double> {
        val x = Double.fromBits(input.xBits)
        val y = Double.fromBits(input.yBits)
        val xx = x * x
        val yy = y * y
        val sum = xx + yy
        val root = sqrt(sum)
        val reciprocal = 1.0 / root
        println(listOf(
            "DYN4K_COLLISION_FP_SCALAR", "v1", "mode=$mode", "id=${input.id}",
            "thread=${GetCurrentThreadId()}", "x=${number(x)}", "y=${number(y)}",
            "xSquared=${number(xx)}", "ySquared=${number(yy)}", "sum=${number(sum)}",
            "sqrt=${number(root)}", "reciprocal=${number(reciprocal)}"
        ).joinToString("\t"))
        return root to reciprocal
    }

    private fun number(value: Double) = "${value}@${value.toRawBits()}"

    private fun withPc53(id: String, body: () -> Unit) = memScoped {
        val saved = alloc<fenv_t>()
        check(fegetenv(saved.ptr) == 0) { "Failed to read the original floating-point environment for $id" }
        val thread = GetCurrentThreadId()
        emitState(id, "before", thread, saved.__control_word, mxcsr(saved), 0)
        try {
            val requested = alloc<fenv_t>()
            check(fegetenv(requested.ptr) == 0) { "Failed to prepare the PC53 environment for $id" }
            requested.__control_word = ((requested.__control_word.toInt() and 0xfcff) or 0x0200).toUShort()
            val setStatus = fesetenv(requested.ptr)
            val active = alloc<fenv_t>()
            val readStatus = fegetenv(active.ptr)
            emitState(id, "pc53", GetCurrentThreadId(),
                if (readStatus == 0) active.__control_word else null,
                if (readStatus == 0) mxcsr(active) else null, readStatus, setStatus)
            check(setStatus == 0 && readStatus == 0 &&
                (active.__control_word.toInt() and 0x0300) == 0x0200 &&
                (mxcsr(active) and 0xffffffc0u) == (mxcsr(saved) and 0xffffffc0u)) {
                "The x87 precision control did not enter PC53 for $id"
            }
            check(GetCurrentThreadId() == thread) { "The controlled body moved to a different thread for $id" }
            body()
        } finally {
            val restoreStatus = fesetenv(saved.ptr)
            val restored = alloc<fenv_t>()
            val readStatus = fegetenv(restored.ptr)
            emitState(id, "restored", GetCurrentThreadId(),
                if (readStatus == 0) restored.__control_word else null,
                if (readStatus == 0) mxcsr(restored) else null, restoreStatus or readStatus)
            check(restoreStatus == 0 && readStatus == 0 && GetCurrentThreadId() == thread &&
                restored.__control_word == saved.__control_word &&
                (mxcsr(restored) and 0xffffffc0u) == (mxcsr(saved) and 0xffffffc0u)) {
                "The original x87 state or SSE control bits were not restored for $id"
            }
        }
    }

    private fun mxcsr(environment: fenv_t): UInt {
        // The linked MinGW fegetenv stores the MXCSR halves in these two fields.
        return (environment.__unused0.toUInt() shl 16) or environment.__unused1.toUInt()
    }

    private fun emitState(
        id: String, phase: String, thread: UInt, controlWord: UShort?, mxcsr: UInt?, status: Int,
        setStatus: Int? = null
    ) {
        println(listOf(
            "DYN4K_COLLISION_FP_STATE", "v1", "id=$id", "phase=$phase",
            "thread=$thread", "x87cw=${controlWord ?: "unavailable"}",
            "mxcsr=${mxcsr ?: "unavailable"}", "status=$status",
            "setStatus=${setStatus ?: "na"}"
        ).joinToString("\t"))
    }
}
