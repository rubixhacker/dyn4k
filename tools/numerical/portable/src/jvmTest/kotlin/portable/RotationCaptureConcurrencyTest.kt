package portable

import java.util.concurrent.CyclicBarrier
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference
import org.dyn4j.geometry.RotationOperationTap
import org.dyn4j.geometry.Transform
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

class RotationCaptureConcurrencyTest {
    @Test
    fun engineExposesNoMutableDiagnosticListener() {
        val rotationMethods = RotationOperationTap::class.java.methods.map { it.name }
        assertTrue(rotationMethods.none { it == "setListener" || it == "getListener" })
        val resetType = runCatching {
            Class.forName("org.dyn4j.world.ToiAcceptedResetTap")
        }.getOrNull()
        assertTrue(resetType == null || resetType.methods.none {
            it.name == "setListener" || it.name == "getListener"
        })
    }

    @Test
    fun concurrentCapturesKeepOperationsOnTheirOwnThreads() {
        val barrier = CyclicBarrier(2)
        val first = AtomicReference<Long?>()
        val second = AtomicReference<Long?>()
        val failure = AtomicReference<Throwable?>()
        fun worker(angle: Double, result: AtomicReference<Long?>): Thread = Thread {
            try {
                RotationOperationTap.capture("concurrent") { scope ->
                    barrier.await(10, TimeUnit.SECONDS)
                    Transform().rotate(angle)
                    val call = scope.drain().single()
                        as RotationOperationTap.Observation.Rotation
                    result.set(call.call.angleBits)
                }
            } catch (error: Throwable) {
                failure.compareAndSet(null, error)
            }
        }
        val a = worker(0.25, first)
        val b = worker(0.5, second)
        a.start()
        b.start()
        a.join(15000)
        b.join(15000)
        assertFalse(a.isAlive)
        assertFalse(b.isAlive)
        assertNull(failure.get())
        assertEquals(0.25.toBits(), first.get())
        assertEquals(0.5.toBits(), second.get())
    }
}
