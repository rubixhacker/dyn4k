package performance.portable

import kotlin.time.TimeSource
import kotlin.coroutines.Continuation
import kotlin.coroutines.EmptyCoroutineContext
import kotlin.coroutines.startCoroutine

private val origin = TimeSource.Monotonic.markNow()

private fun nowNs(): Long = origin.elapsedNow().inWholeNanoseconds

private suspend fun pace(startNs: Long, step: Int, hz: Int, pause: suspend (Int) -> Unit): Long {
    val deadline = startNs + step * 1_000_000_000L / hz
    while (nowNs() < deadline) {
        val remainingMs = ((deadline - nowNs()) / 1_000_000L).toInt()
        pause((remainingMs - 1).coerceAtLeast(0))
    }
    return (nowNs() - deadline).coerceAtLeast(0)
}

private fun emit(vararg fields: Any) {
    println(fields.joinToString("\t", prefix = "DYN4K\t"))
}

private fun expectedCount(family: String, size: String): Int {
    val counts = when (family) {
        "separated" -> listOf(100, 1000, 10000)
        "pile" -> listOf(100, 500, 2000)
        "joint" -> listOf(50, 250, 1000)
        "ccd" -> listOf(25, 100, 500)
        "lifecycle" -> listOf(100, 1000, 5000)
        else -> error("unknown family")
    }
    val index = listOf("small", "medium", "stress").indexOf(size)
    require(index >= 0)
    return counts[index]
}

private fun calibratedResolutionNs(): Long {
    var minimum = Long.MAX_VALUE
    repeat(64) {
        val started = nowNs()
        var ended: Long
        do { ended = nowNs() } while (ended <= started)
        minimum = minOf(minimum, ended - started)
    }
    return minimum
}

private suspend fun phase(
    fixture: Fixture, steps: Int, warmup: Boolean, pause: suspend (Int) -> Unit,
): Pair<Long, Int> {
    val phase = if (warmup) "warmup" else "measure"
    var active = 0
    val started = nowNs()
    for (step in 0 until steps) {
        val late = pace(started, step, fixture.hz, pause)
        val began = nowNs()
        fixture.mutate(step)
        val mutated = nowNs()
        fixture.world.step(1, 1.0 / fixture.hz)
        val ended = nowNs()
        emit("CLOCK", phase, step, began, ended)
        if (!warmup) {
            val activity = fixture.activity()
            if (activity.first > 0) active++
            val pairs = if (step % fixture.hz == 0 || step == steps - 1) fixture.pairs()
                        else Triple(-1, -1, -1)
            emit("STEP", step, ended - began, mutated - began, late,
                fixture.world.getBodyCount(), fixture.world.getJointCount(),
                activity.first, activity.second, activity.third,
                fixture.contactBegins, fixture.contactEnds, fixture.toiEvents,
                pairs.first, pairs.second, pairs.third)
        }
        pause(0)
    }
    return Pair(nowNs() - started, active)
}

internal suspend fun runPortable(
    args: Array<String>, pause: suspend (Int) -> Unit = {},
    memoryProbe: (() -> Pair<Long, Long>)? = null,
) {
    require(args.size == 14) {
        "scenario family variant size hz steps warmup mode api source core kotlin build nonce"
    }
    val scenario = args[0]
    val family = args[1]
    val variant = args[2]
    val size = args[3]
    val hz = args[4].toInt()
    val steps = args[5].toInt()
    val warmup = args[6].toInt()
    val mode = args[7]
    val api = args[8]
    val source = args[9]
    val core = args[10]
    val kotlin = args[11]
    val build = args[12]
    val nonce = args[13]
    require(api == "direct_kotlin" || api == "compatibility")
    require(hz == 30 || hz == 60 || hz == 120)
    require(steps > 0 && warmup >= 0)
    require(mode == "timing" || mode == "memory")
    require(mode != "memory" || memoryProbe != null)
    require(build == "development" || build == "optimized")
    require(scenario == "$family.$variant.$size.${hz}hz.$api")
    require(source.matches(Regex("[0-9a-f]{40}")))
    require(source == BuildIdentity.sourceSha) { "launched source differs from linked producer" }
    require(core.matches(Regex("[0-9a-f]{64}")))
    require(kotlin.matches(Regex("[0-9a-f]{64}")))
    require(nonce.matches(Regex("[0-9a-f]{32}")))
    fun heap(stage: String) {
        if (mode == "memory") {
            val sample = requireNotNull(memoryProbe).invoke()
            require(sample.first > 0 && sample.second > 0)
            emit("HEAP", stage, sample.first, sample.second)
        }
    }
    val count = expectedCount(family, size)
    emit("PROVIDER", api, source, core, kotlin, scenario, build, nonce)
    emit("RESOLUTION", calibratedResolutionNs(), 64)
    emit("LINK", BuildIdentity.sourceSha, BuildIdentity.producerTree)
    var warmed: Fixture? = Fixture(family, variant, count, hz, api)
    emit("CONSTRUCTION", warmed!!.world.getBodyCount(), warmed.world.getJointCount())
    heap("constructed")
    phase(warmed, warmup, true, pause)
    warmed = null
    emit("RESET", "after_warmup", warmup)
    heap("after_reset")
    val measured = Fixture(family, variant, count, hz, api)
    val (wallNs, activeSteps) = phase(measured, steps, false, pause)
    heap("measured")
    emit("RUN", api, mode, steps, warmup, wallNs, activeSteps,
        "memory_attribution_missing", "plateau_missing", "unpassed")
    emit("COMPLETE", nonce)
}

internal fun startPortable(
    args: Array<String>, pause: suspend (Int) -> Unit = {},
    memoryProbe: (() -> Pair<Long, Long>)? = null,
) {
    suspend { runPortable(args, pause, memoryProbe) }.startCoroutine(object : Continuation<Unit> {
        override val context = EmptyCoroutineContext
        override fun resumeWith(result: Result<Unit>) { result.getOrThrow() }
    })
}
