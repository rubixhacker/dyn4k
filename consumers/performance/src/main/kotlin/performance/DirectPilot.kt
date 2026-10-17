package performance

import com.sun.management.ThreadMXBean
import java.lang.management.ManagementFactory
import java.nio.file.Files
import java.nio.file.Path
import java.util.concurrent.locks.LockSupport
import kotlin.math.abs
import kotlin.math.hypot
import kotlin.math.max

private const val STEP_HEADER = "step,elapsed_ns,mutation_ns,lateness_ns,allocation_bytes,heap_used_bytes,rss_bytes,rss_delta_bytes,body_count,joint_count,awake_count,linear_speed_sum_m_per_s,angular_speed_sum_rad_per_s,contact_begins,contact_ends,toi_events,broadphase_candidates,active_contact_pairs,active_contact_points"

private fun rssBytes(): Long = try {
    Files.readAllLines(Path.of("/proc/self/status"))
        .firstOrNull { it.startsWith("VmRSS:") }
        ?.trim()?.split(Regex("\\s+"))?.get(1)?.toLong()?.times(1024) ?: -1
} catch (_: Exception) {
    -1
}

private fun collectionCount(): Long = ManagementFactory.getGarbageCollectorMXBeans()
    .sumOf { max(0L, it.collectionCount) }

private fun retainedHeap(): Long = Runtime.getRuntime().totalMemory() - Runtime.getRuntime().freeMemory()

private fun pace(start: Long, step: Int, hz: Int): Long {
    val deadline = start + (1_000_000_000L * step) / hz
    val wait = deadline - System.nanoTime()
    if (wait > 0) LockSupport.parkNanos(wait)
    return max(0L, System.nanoTime() - deadline)
}

private fun plateau(family: String, variant: String, count: Int, hz: Int, warmup: Int) {
    var warmed: DirectFixture? = DirectFixture(family, variant, count, hz)
    System.err.println("warmup_step,elapsed_ns")
    val start = System.nanoTime()
    for (step in 0 until warmup) {
        pace(start, step, hz)
        val began = System.nanoTime()
        warmed!!.mutate(step)
        warmed.world.step(1, 1.0 / hz)
        System.err.println("$step,${System.nanoTime() - began}")
    }
    warmed = null
    System.out.println("cycle,heap_after_collection_bytes,rss_after_collection_bytes,collection_count")
    repeat(100) { cycle ->
        var fixture: DirectFixture? = DirectFixture(family, variant, count, hz)
        for (step in 0 until 2 * hz) {
            fixture!!.mutate(step)
            fixture.world.step(1, 1.0 / hz)
        }
        fixture = null
        System.gc()
        Thread.sleep(10)
        System.out.println("$cycle,${retainedHeap()},${rssBytes()},${collectionCount()}")
    }
}

private fun run(fixture: DirectFixture, steps: Int, mode: String, warmup: Int, rssBase: Long) {
    require(mode in setOf("timing", "allocation", "memory")) { "unknown mode: $mode" }
    val bean = ManagementFactory.getThreadMXBean() as ThreadMXBean
    val allocation = mode != "timing" && bean.isThreadAllocatedMemorySupported
    if (allocation) bean.isThreadAllocatedMemoryEnabled = true
    val thread = Thread.currentThread().id
    System.err.println("warmup_step,elapsed_ns,rss_bytes")
    val warmStart = System.nanoTime()
    for (step in 0 until warmup) {
        pace(warmStart, step, fixture.hz)
        val began = System.nanoTime()
        fixture.mutate(step)
        fixture.world.step(1, 1.0 / fixture.hz)
        System.err.println("$step,${System.nanoTime() - began},${if (mode == "memory") rssBytes() else -1}")
    }
    val measured = DirectFixture(fixture.family, fixture.variant, fixture.count, fixture.hz)
    if (mode == "memory") {
        val before = collectionCount()
        System.gc()
        Thread.sleep(100)
        System.err.println("#retained_heap_world_alive_bytes=${retainedHeap()}")
        System.err.println("#retained_collection_count_delta=${collectionCount() - before}")
    } else {
        System.err.println("#retained_heap_world_alive_bytes=-1")
        System.err.println("#retained_collection_count_delta=-1")
    }
    val start = System.nanoTime()
    System.out.println(STEP_HEADER)
    for (step in 0 until steps) {
        val lateness = pace(start, step, fixture.hz)
        val allocatedBefore = if (allocation) bean.getThreadAllocatedBytes(thread) else -1
        val began = System.nanoTime()
        val mutation = measured.mutate(step)
        measured.world.step(1, 1.0 / fixture.hz)
        val elapsed = System.nanoTime() - began
        val allocated = if (allocation) bean.getThreadAllocatedBytes(thread) - allocatedBefore else -1
        var awake = 0
        var linearSpeed = 0.0
        var angularSpeed = 0.0
        for (body in measured.dynamic) {
            if (!body.isAtRest()) awake++
            val velocity = body.getLinearVelocity()
            linearSpeed += hypot(velocity.x, velocity.y)
            angularSpeed += abs(body.getAngularVelocity())
        }
        val rss = rssBytes()
        val delta = if (rss < 0 || rssBase < 0) -1 else rss - rssBase
        var candidates = -1
        var activePairs = -1
        var activePoints = -1
        if (step % fixture.hz == 0 || step == steps - 1) {
            candidates = 0
            val broadphase = measured.world.getBroadphaseDetector().detectIterator(true)
            while (broadphase.hasNext()) {
                broadphase.next()
                candidates++
            }
            activePairs = 0
            activePoints = 0
            val collisions = measured.world.getCollisionDataIterator()
            while (collisions.hasNext()) {
                val collision = collisions.next()
                val constraint = collision.getContactConstraint()
                if (collision.isContactConstraintCollision() && constraint != null) {
                    activePairs++
                    activePoints += constraint.getContacts().size
                }
            }
        }
        System.out.println(listOf(
            step, elapsed, mutation, lateness, allocated, retainedHeap(), rss, delta,
            measured.world.getBodyCount(), measured.world.getJointCount(), awake,
            linearSpeed, angularSpeed, measured.contactBegins, measured.contactEnds,
            measured.toiEvents, candidates, activePairs, activePoints,
        ).joinToString(","))
    }
}

fun main(args: Array<String>) {
    require(args.size == 7) { "family variant size hz steps mode warmup_steps" }
    val family = args[0]
    val variant = args[1]
    val size = args[2]
    val hz = args[3].toInt()
    val steps = args[4].toInt()
    val mode = args[5]
    val warmup = args[6].toInt()
    require(hz in setOf(30, 60, 120) && steps > 0 && warmup >= 0)
    val sizes = mapOf(
        "separated" to listOf(100, 1000, 10000),
        "pile" to listOf(100, 500, 2000),
        "joint" to listOf(50, 250, 1000),
        "ccd" to listOf(25, 100, 500),
        "lifecycle" to listOf(100, 1000, 5000),
    )
    val count = sizes.getValue(family)[listOf("small", "medium", "stress").indexOf(size)]
    if (mode == "plateau") {
        plateau(family, variant, count, hz, warmup)
        return
    }
    val rssBase = rssBytes()
    val bean = ManagementFactory.getThreadMXBean() as ThreadMXBean
    val allocation = bean.isThreadAllocatedMemorySupported
    if (allocation) bean.isThreadAllocatedMemoryEnabled = true
    val thread = Thread.currentThread().id
    val allocatedBefore = if (allocation) bean.getThreadAllocatedBytes(thread) else -1
    val began = System.nanoTime()
    val fixture = DirectFixture(family, variant, count, hz)
    System.err.println("#construction_ns=${System.nanoTime() - began}")
    System.err.println("#construction_allocated_bytes=${if (allocation) bean.getThreadAllocatedBytes(thread) - allocatedBefore else -1}")
    System.err.println("#rss_empty_harness_bytes=$rssBase")
    System.err.println("#rss_after_construction_bytes=${rssBytes()}")
    run(fixture, steps, mode, warmup, rssBase)
}
