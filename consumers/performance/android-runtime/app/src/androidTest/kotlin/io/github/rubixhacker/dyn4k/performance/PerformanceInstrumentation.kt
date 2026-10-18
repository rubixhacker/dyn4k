package io.github.rubixhacker.dyn4k.performance

import android.app.Instrumentation
import android.os.Build
import android.os.Bundle
import android.os.Process
import android.os.SystemClock
import java.io.OutputStreamWriter
import org.json.JSONObject
import performance.portable.Fixture

class PerformanceInstrumentation : Instrumentation() {
    private lateinit var arguments: Bundle

    override fun onCreate(arguments: Bundle) {
        super.onCreate(arguments)
        this.arguments = arguments
        start()
    }

    override fun onStart() {
        val nonce = arguments.getString("nonce") ?: "missing"
        val output = targetContext.openFileOutput("performance-$nonce.jsonl", 0)
        val writer = OutputStreamWriter(output, Charsets.UTF_8).buffered()
        fun emit(type: String, vararg fields: Pair<String, Any>) {
            val row = JSONObject().put("schema", 1).put("type", type)
            fields.forEach { (key, value) -> row.put(key, value) }
            writer.write(row.toString())
            writer.newLine()
            writer.flush()
        }
        try {
            val scenario = required("scenario")
            val match = Regex("^(separated|pile|joint|ccd|lifecycle)\\.([a-z_]+)\\.(small|medium)\\.(30|60|120)hz\\.(direct_kotlin|compatibility)$")
                .matchEntire(scenario) ?: error("invalid scenario")
            val (family, variant, size, rateText, api) = match.destructured
            val hz = rateText.toInt()
            val count = when (family) {
                "separated" -> if (size == "small") 100 else 1000
                "pile" -> if (size == "small") 100 else 500
                "joint" -> if (size == "small") 50 else 250
                "ccd" -> if (size == "small") 25 else 100
                else -> if (size == "small") 100 else 1000
            }
            val steps = required("steps").toInt()
            val warmup = required("warmup_steps").toInt()
            require(steps in 1..(5 * hz) && warmup in 0..(600 * hz))
            require(required("source_commit").matches(Regex("[0-9a-f]{40}")))
            for (name in listOf("manifest_sha256", "fixture_sha256", "core_aar_sha256", "kotlin_aar_sha256")) {
                require(required(name).matches(Regex("[0-9a-f]{64}")))
            }
            require(nonce.matches(Regex("[0-9a-f]{32}")))
            require(targetContext.packageName == "io.github.rubixhacker.dyn4k.performance")
            require(context.packageName == "io.github.rubixhacker.dyn4k.performance.test")
            val provider = org.dyn4j.world.World::class.java
            require(provider.name == "org.dyn4j.world.World")
            emit("identity", "nonce" to nonce, "scenario" to scenario,
                 "source_commit" to required("source_commit"),
                 "manifest_sha256" to required("manifest_sha256"),
                 "fixture_sha256" to required("fixture_sha256"),
                 "core_aar_sha256" to required("core_aar_sha256"),
                 "kotlin_aar_sha256" to required("kotlin_aar_sha256"),
                 "app_package" to targetContext.packageName, "test_package" to context.packageName,
                 "provider_class" to provider.name, "pid" to Process.myPid(),
                 "api_level" to Build.VERSION.SDK_INT, "abi" to Build.SUPPORTED_ABIS[0],
                 "fingerprint" to Build.FINGERPRINT)
            val warm = Fixture(family, variant, count, hz, api)
            emit("construction", "phase" to "warmup", "bodies" to warm.world.getBodyCount(),
                 "joints" to warm.world.getJointCount())
            runPhase(warm, warmup, "warmup", emitStep = false, emit = ::emit)
            val measured = Fixture(family, variant, count, hz, api)
            emit("reset", "after_warmup" to warmup,
                 "warmup_world_id" to System.identityHashCode(warm.world),
                 "measure_world_id" to System.identityHashCode(measured.world))
            emit("construction", "phase" to "measure", "bodies" to measured.world.getBodyCount(),
                 "joints" to measured.world.getJointCount())
            val (elapsed, active) = runPhase(measured, steps, "measure", emitStep = true, emit = ::emit)
            emit("run", "steps" to steps, "warmup_steps" to warmup,
                 "wall_ns" to elapsed, "active_steps" to active, "qualification" to "unpassed")
            finish(-1, Bundle().apply { putString("stream", "OK (1 test)") })
        } catch (failure: Throwable) {
            emit("failure", "message" to failure.toString())
            finish(0, Bundle().apply { putString("shortMsg", failure.toString()) })
        } finally {
            writer.close()
        }
    }

    private fun required(name: String): String = arguments.getString(name)
        ?: error("missing argument: $name")

    private fun runPhase(
        fixture: Fixture,
        steps: Int,
        phase: String,
        emitStep: Boolean,
        emit: (String, Array<out Pair<String, Any>>) -> Unit,
    ): Pair<Long, Int> {
        val start = SystemClock.elapsedRealtimeNanos()
        var active = 0
        for (step in 0 until steps) {
            val deadline = start + step * 1_000_000_000L / fixture.hz
            while (SystemClock.elapsedRealtimeNanos() < deadline) Thread.yield()
            val begin = SystemClock.elapsedRealtimeNanos()
            fixture.mutate(step)
            val mutated = SystemClock.elapsedRealtimeNanos()
            fixture.world.step(1, 1.0 / fixture.hz)
            val end = SystemClock.elapsedRealtimeNanos()
            check(begin > 0 && mutated >= begin && end > mutated)
            emit("clock", arrayOf("phase" to phase, "step" to step,
                                  "begin_ns" to begin, "end_ns" to end))
            if (emitStep) {
                val activity = fixture.activity()
                if (activity.first > 0) active++
                val pairs = if (step % fixture.hz == 0 || step == steps - 1) fixture.pairs()
                            else Triple(-1, -1, -1)
                emit("step", arrayOf("step" to step, "begin_ns" to begin,
                                     "end_ns" to end, "duration_ns" to end - begin,
                                     "mutate_ns" to mutated - begin,
                                     "late_ns" to (begin - deadline).coerceAtLeast(0),
                                     "bodies" to fixture.world.getBodyCount(),
                                     "joints" to fixture.world.getJointCount(),
                                     "awake" to activity.first,
                                     "linear_speed" to activity.second,
                                     "angular_speed" to activity.third,
                                     "contact_begins" to fixture.contactBegins,
                                     "contact_ends" to fixture.contactEnds,
                                     "toi_events" to fixture.toiEvents,
                                     "broad_pairs" to pairs.first,
                                     "contact_pairs" to pairs.second,
                                     "contact_points" to pairs.third))
            }
        }
        return Pair(SystemClock.elapsedRealtimeNanos() - start, active)
    }
}
