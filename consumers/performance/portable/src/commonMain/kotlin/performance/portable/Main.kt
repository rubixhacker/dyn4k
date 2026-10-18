package performance.portable

import kotlin.time.TimeSource

private val origin = TimeSource.Monotonic.markNow()

private fun nowNs(): Long = origin.elapsedNow().inWholeNanoseconds

private fun pace(startNs: Long, step: Int, hz: Int): Long {
    val deadline = startNs + step * 1_000_000_000L / hz
    while (nowNs() < deadline) {
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

private fun phase(fixture: Fixture, steps: Int, warmup: Boolean): Pair<Long, Int> {
    val phase = if (warmup) "warmup" else "measure"
    var active = 0
    val started = nowNs()
    for (step in 0 until steps) {
        val late = pace(started, step, fixture.hz)
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
    }
    return Pair(nowNs() - started, active)
}

internal fun runPortable(args: Array<String>) {
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
    require(mode == "timing")
    require(build == "development" || build == "optimized")
    require(scenario == "$family.$variant.$size.${hz}hz.$api")
    require(source.matches(Regex("[0-9a-f]{40}")))
    require(core.matches(Regex("[0-9a-f]{64}")))
    require(kotlin.matches(Regex("[0-9a-f]{64}")))
    require(nonce.matches(Regex("[0-9a-f]{32}")))
    val count = expectedCount(family, size)
    emit("PROVIDER", api, source, core, kotlin, scenario, build, nonce)
    var warmed: Fixture? = Fixture(family, variant, count, hz, api)
    emit("CONSTRUCTION", warmed!!.world.getBodyCount(), warmed.world.getJointCount())
    phase(warmed, warmup, true)
    warmed = null
    emit("RESET", "after_warmup", warmup)
    val measured = Fixture(family, variant, count, hz, api)
    val (wallNs, activeSteps) = phase(measured, steps, false)
    emit("RUN", api, mode, steps, warmup, wallNs, activeSteps,
        "memory_attribution_missing", "plateau_missing", "unpassed")
}
