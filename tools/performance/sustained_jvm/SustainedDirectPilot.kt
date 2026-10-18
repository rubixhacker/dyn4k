package performance

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

private fun collectionCount(): Long {
    val collectors = ManagementFactory.getGarbageCollectorMXBeans()
    if (collectors.isEmpty()) return -1
    val counts = collectors.map { it.collectionCount }
    if (counts.any { it < 0 }) return -1
    return counts.fold(0L, Math::addExact)
}

private fun retainedHeap(): Long = Runtime.getRuntime().totalMemory() - Runtime.getRuntime().freeMemory()

private fun pace(start: Long, step: Int, hz: Int): Long {
    val deadline = start + (1_000_000_000L * step) / hz
    val wait = deadline - System.nanoTime()
    if (wait > 0) LockSupport.parkNanos(wait)
    return max(0L, System.nanoTime() - deadline)
}

private fun plateau(family: String, variant: String, count: Int, hz: Int, warmup: Int) {
    val probe = SustainedSidecars.AllocationProbe.require()
    var warmed: DirectFixture? = DirectFixture(family, variant, count, hz)
    System.err.println("warmup_step,elapsed_ns")
    val start = System.nanoTime()
    SustainedSidecars.clock("DYN4K_WARMUP_CLOCK_CSV", "warmup_step,begin_ns,end_ns").use { clock ->
        for (step in 0 until warmup) {
            pace(start, step, hz)
            val began = System.nanoTime()
            warmed!!.mutate(step)
            warmed.world.step(1, 1.0 / hz)
            val ended = System.nanoTime()
            SustainedSidecars.clockRow(clock, step, began, ended)
            System.err.println("$step,${ended - began}")
        }
    }
    warmed = null
    System.out.println("cycle,heap_after_collection_bytes,rss_after_collection_bytes,collection_count,managed_bytes,native_bytes,wasm_linear_bytes,attributed_workload_bytes,reserved_runtime_bytes")
    repeat(100) { cycle ->
        val allocatedBefore = probe.read()
        plateauCycle(family, variant, count, hz)
        val cycleDisposedNs = System.nanoTime()
        SustainedSidecars.allocation("plateau", cycle, probe, allocatedBefore, probe.read())
        val before = collectionCount()
        val beforeSampleNs = System.nanoTime()
        val gcRequestedNs = System.nanoTime()
        System.gc()
        Thread.sleep(10)
        val heap = retainedHeap()
        val rss = rssBytes()
        val collected = collectionCount()
        val afterSampleNs = System.nanoTime()
        SustainedSidecars.plateau(cycle, heap, rss, before, collected,
            cycleDisposedNs, beforeSampleNs, gcRequestedNs, afterSampleNs)
        System.out.println("$cycle,$heap,$rss,$collected,-1,-1,0,-1,-1")
    }
}

private fun plateauCycle(family: String, variant: String, count: Int, hz: Int) {
    val fixture = DirectFixture(family, variant, count, hz)
    for (step in 0 until 2 * hz) {
        fixture.mutate(step)
        fixture.world.step(1, 1.0 / hz)
    }
}

private fun warm(fixture: DirectFixture, warmup: Int, mode: String, probe: SustainedSidecars.AllocationProbe?) {
    System.err.println("warmup_step,elapsed_ns,rss_bytes")
    SustainedSidecars.clock("DYN4K_WARMUP_CLOCK_CSV", "warmup_step,begin_ns,end_ns").use { clock ->
        val warmStart = System.nanoTime()
        for (step in 0 until warmup) {
            pace(warmStart, step, fixture.hz)
            val allocatedBefore = probe?.read() ?: -1
            val began = System.nanoTime()
            fixture.mutate(step)
            fixture.world.step(1, 1.0 / fixture.hz)
            val ended = System.nanoTime()
            val allocatedAfter = probe?.read() ?: -1
            SustainedSidecars.clockRow(clock, step, began, ended)
            if (probe != null) SustainedSidecars.allocation("warmup", step, probe, allocatedBefore, allocatedAfter)
            val rss = if (mode == "memory") rssBytes() else -1
            System.err.println("$step,${ended - began},$rss")
            SustainedSidecars.resource("warmup", step, retainedHeap(), rss, -1)
            if (mode == "memory") SustainedSidecars.memory("warmup", step, retainedHeap(), rss, -1)
        }
    }
}

private fun run(family: String, variant: String, count: Int, hz: Int, steps: Int, mode: String, rssBase: Long,
                probe: SustainedSidecars.AllocationProbe?): Pair<Long, Int> {
    require(mode in setOf("timing", "allocation", "memory")) { "unknown mode: $mode" }
    val measured = DirectFixture(family, variant, count, hz)
    if (mode == "memory") {
        val before = collectionCount()
        System.gc()
        Thread.sleep(100)
        val after = collectionCount()
        val collectionDelta = if (before < 0 || after < 0) -1 else after - before
        System.err.println("#retained_collection_count_delta=$collectionDelta")
        if (collectionDelta > 0) System.err.println("#retained_heap_world_alive_bytes=${retainedHeap()}")
        SustainedSidecars.memory("retained", 0, retainedHeap(), rssBytes(), collectionDelta)
    } else {
        System.err.println("#retained_heap_world_alive_bytes=-1")
        System.err.println("#retained_collection_count_delta=-1")
    }
    System.out.println(STEP_HEADER)
    var activeSteps = 0
    var measuredWall = 0L
    SustainedSidecars.clock("DYN4K_CLOCK_CSV", "step,begin_ns,end_ns").use { clock ->
    val start = System.nanoTime()
    for (step in 0 until steps) {
        val lateness = pace(start, step, hz)
        val allocatedBefore = probe?.read() ?: -1
        val began = System.nanoTime()
        val mutation = measured.mutate(step)
        measured.world.step(1, 1.0 / hz)
        val ended = System.nanoTime()
        val elapsed = ended - began
        val allocatedAfter = probe?.read() ?: -1
        val allocated = if (probe == null) -1 else allocatedAfter - allocatedBefore
        SustainedSidecars.clockRow(clock, step, began, ended)
        if (probe != null) SustainedSidecars.allocation("measure", step, probe, allocatedBefore, allocatedAfter)
        var awake = 0
        var linearSpeed = 0.0
        var angularSpeed = 0.0
        for (body in measured.dynamic) {
            if (!body.isAtRest()) awake++
            val velocity = body.getLinearVelocity()
            linearSpeed += hypot(velocity.x, velocity.y)
            angularSpeed += abs(body.getAngularVelocity())
        }
        if (awake > 0) activeSteps++
        val heap = retainedHeap()
        val rss = rssBytes()
        val delta = if (rss < 0 || rssBase < 0) -1 else rss - rssBase
        var candidates = -1
        var activePairs = -1
        var activePoints = -1
        if (step % hz == 0 || step == steps - 1) {
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
            step, elapsed, mutation, lateness, allocated, heap, rss, delta,
            measured.world.getBodyCount(), measured.world.getJointCount(), awake,
            linearSpeed, angularSpeed, measured.contactBegins, measured.contactEnds,
            measured.toiEvents, candidates, activePairs, activePoints,
        ).joinToString(","))
        SustainedSidecars.resource("measure", step, heap, rss, allocated)
        if (mode == "memory") SustainedSidecars.memory("measure", step, heap, rss, -1)
    }
    measuredWall = System.nanoTime() - start
    }
    java.lang.ref.Reference.reachabilityFence(measured)
    return measuredWall to activeSteps
}

fun main(args: Array<String>) {
    require(args.size == 8 && args[7] == "direct_kotlin") {
        "family variant size hz steps mode warmup_steps direct_kotlin"
    }
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
    SustainedSidecars.provider("direct_kotlin", org.dyn4j.world.World::class.java,
        Class.forName("performance.SustainedDirectPilotKt"),
        Class.forName("io.github.rubixhacker.dyn4k.WorldConveniencesKt"))
    SustainedSidecars.openResource()
    SustainedSidecars.openMemory("direct_kotlin", mode, family, variant, size, hz, steps, warmup)
    if (mode == "fixture_identity") {
        require(steps == 1 && warmup == 0) { "identity requires one step and no warm-up" }
        DirectFixture(family, variant, count, hz).printCcdIdentity()
        return
    }
    if (mode == "plateau") {
        SustainedSidecars.emptyHeap(retainedHeap())
        plateau(family, variant, count, hz, warmup)
        SustainedSidecars.closeResource()
        return
    }
    val probe = if (mode == "timing") null else SustainedSidecars.AllocationProbe.require()
    val rssBase = rssBytes()
    val emptyHeap = retainedHeap()
    SustainedSidecars.emptyHeap(emptyHeap)
    SustainedSidecars.resource("empty", 0, emptyHeap, rssBase, -1)
    if (mode == "memory") SustainedSidecars.memory("empty", 0, emptyHeap, rssBase, -1)
    val allocatedBefore = probe?.read() ?: -1
    val began = System.nanoTime()
    var fixture: DirectFixture? = DirectFixture(family, variant, count, hz)
    val ended = System.nanoTime()
    val allocatedAfter = probe?.read() ?: -1
    System.err.println("#construction_ns=${ended - began}")
    System.err.println("#construction_allocated_bytes=${if (probe == null) -1 else allocatedAfter - allocatedBefore}")
    if (probe != null) SustainedSidecars.allocation("construction", 0, probe, allocatedBefore, allocatedAfter)
    System.err.println("#rss_empty_harness_bytes=$rssBase")
    System.err.println("#rss_after_construction_bytes=${rssBytes()}")
    SustainedSidecars.resource("construction", 0, retainedHeap(), rssBytes(),
        if (probe == null) -1 else allocatedAfter - allocatedBefore)
    if (mode == "memory") SustainedSidecars.memory("construction", 0, retainedHeap(), rssBytes(), -1)
    warm(fixture!!, warmup, mode, probe)
    fixture = null
    System.err.println("#fixture_reset_after_warmup=1")
    val (measuredWall, activeSteps) = run(family, variant, count, hz, steps, mode, rssBase, probe)
    SustainedSidecars.run("direct_kotlin", mode, steps, warmup, measuredWall, activeSteps)
    SustainedSidecars.closeResource()
}
