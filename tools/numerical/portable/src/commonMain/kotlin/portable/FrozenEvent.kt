package portable

import org.dyn4j.dynamics.TimeStep

internal object FrozenEvent {
    fun id(spec: CaseSpec): String = when {
        spec.id == "long-free-60" -> "L-free-s1.0-o0.0,0.0-hz60"
        spec.id.startsWith("contacts-default-") ->
            "S-sleep-wake-hz${spec.id.substringAfterLast('-')}"
        spec.id.startsWith("contacts-configured-") -> {
            val outer = spec.input["outerHz"] as Int
            val repetition = spec.input["repetition"] as Int
            "Q-sleep-wake-outer$outer-repeat$repetition"
        }
        spec.id == "P-JINT-Pulley-slack-transition-preparation-0" ||
            spec.id == "P-JINT-Pulley-slack-transition-preparation-1" ->
            "P-JINT-Pulley-slack-transition-preparation"
        spec.id == "P-JINT-Pulley-slack-transition-main" ->
            "P-JINT-Pulley-slack-transition"
        spec.id == "P-JINT-Weld-enabled-equal" -> spec.id
        else -> error("frozen event identity is unavailable for ${spec.id}")
    }

    fun step(spec: CaseSpec, name: String, number: Int, order: Int,
             value: TimeStep?): Map<String, Any?> {
        val time = value ?: error("step callback has no time step")
        val method = name.removePrefix("step.")
        require(method in setOf("begin", "updatePerformed", "postSolve", "end"))
        return mapOf("kind" to "event", "step" to number, "order" to order,
            "listener" to "StepListener",
            "method" to "public abstract void org.dyn4j.world.listener.StepListener.$method(org.dyn4j.dynamics.TimeStep,org.dyn4j.world.PhysicsWorld<T, ?>)",
            "payload" to listOf(mapOf(
                "type" to "org.dyn4j.dynamics.TimeStep",
                "getDeltaTime" to time.getDeltaTime(),
                "getDeltaTimeRatio" to time.getDeltaTimeRatio(),
                "getInverseDeltaTime" to time.getInverseDeltaTime(),
                "getPreviousInverseDeltaTime" to time.getPreviousInverseDeltaTime(),
                "getPrevousDeltaTime" to time.getPrevousDeltaTime()),
                mapOf("world" to id(spec))))
    }
}
