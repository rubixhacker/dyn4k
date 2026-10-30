package io.github.rubixhacker.harness.numerical

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/**
 * `candidate/nominal_zero.py`: the extra zero and timestep invariants the nominal free-motion
 * case needs on top of the shared comparison engine.
 */
object NominalZero {
    val ZERO_PATHS = listOf(
        "state.state.bodies[].force[]",
        "state.state.bodies[].torque",
        "state.state.bodies[].accumulatedForce[]",
        "state.state.bodies[].accumulatedTorque",
    )

    /** `float.fromhex` of the pinned timestep constants, built from their bit patterns. */
    val TIMESTEP_VALUES: List<Pair<String, Double>> = listOf(
        "getDeltaTime" to Double.fromBits((1017L shl 52) or 0x1111111111111L),
        "getPrevousDeltaTime" to Double.fromBits((1017L shl 52) or 0x1111111111111L),
        "getInverseDeltaTime" to Double.fromBits((1028L shl 52) or 0xE000000000000L),
        "getPreviousInverseDeltaTime" to Double.fromBits((1028L shl 52) or 0xE000000000000L),
        "getDeltaTimeRatio" to 1.0,
    )

    val STEP_METHODS = listOf("begin", "updatePerformed", "postSolve", "end")

    /** `nominal_zero.with_rules`: the fixture with the nominal zero and timestep rules added. */
    fun withRules(fixture: JsonObject): JsonObject {
        if (fixture["key"]?.stringOrNull() != "nominal-free-motion") {
            throw Rejected("nominal zero rule scope differs")
        }
        if (fixture.containsKey("zero_numeric") &&
            fixture["zero_numeric"] != JsonArray(ZERO_PATHS.map { JsonPrimitive(it) })
        ) {
            throw Rejected("nominal zero rule scope differs")
        }
        val exact = ArrayList<JsonElement>(
            (fixture["exact_numeric"] as? JsonArray ?: JsonArray(emptyList())).toList(),
        )
        for (field in TIMESTEP_VALUES.map { it.first }) {
            val path = "event.payload[].$field"
            if (exact.none { it.stringOrNull() == path }) exact.add(JsonPrimitive(path))
        }
        val result = LinkedHashMap<String, JsonElement>(fixture)
        result["zero_numeric"] = JsonArray(ZERO_PATHS.map { JsonPrimitive(it) })
        result["exact_numeric"] = JsonArray(exact)
        return JsonObject(result)
    }

    /** `nominal_zero.check_timestep`: the pinned TimeStep payload, returning the check count. */
    fun checkTimestep(row: JsonObject): Int {
        val method = row["method"]?.stringOrNull().orEmpty()
        if (row["listener"]?.stringOrNull() != "StepListener" ||
            STEP_METHODS.none { ".StepListener.$it(" in method }
        ) {
            throw Rejected("nominal callback identity differs")
        }
        val payload = row["payload"] as? JsonArray
        if (payload == null || payload.size != 2 || payload[0] !is JsonObject) {
            throw Rejected("nominal timestep payload schema differs")
        }
        val step = payload[0] as JsonObject
        val expectedKeys = TIMESTEP_VALUES.map { it.first }.toSet() + setOf("type")
        if (step.keys != expectedKeys ||
            step["type"]?.stringOrNull() != "org.dyn4j.dynamics.TimeStep"
        ) {
            throw Rejected("nominal timestep schema differs")
        }
        for ((field, expected) in TIMESTEP_VALUES) {
            val value = step[field]
            val number = value.numberOrNull()
            if (!value.isNumber() || number == null || !number.isFinite() ||
                number.toRawBits() != expected.toRawBits()
            ) {
                throw Rejected("nominal timestep $field differs")
            }
        }
        return TIMESTEP_VALUES.size
    }

    /** `nominal_zero.check_body`: every declared zero field must be positive binary64 zero. */
    fun checkBody(body: JsonObject): Int {
        var checks = 0
        for ((name, length) in listOf(
            "force" to 2,
            "torque" to null,
            "accumulatedForce" to 2,
            "accumulatedTorque" to null,
        )) {
            if (!body.containsKey(name)) throw Rejected("missing nominal zero field: $name")
            val field = body[name] ?: JsonNull
            val values: List<JsonElement> = if (length != null) {
                val array = field as? JsonArray
                if (array == null || array.size != length) {
                    throw Rejected("invalid nominal zero vector: $name")
                }
                array.toList()
            } else {
                listOf(field)
            }
            for (value in values) {
                if (value.isIntegerLiteral() || !value.isNumber()) {
                    throw Rejected("nominal field is not positive binary64 zero: $name")
                }
                val number = value.numberOrNull()!!
                if (!number.isFinite() || number.toRawBits() != 0L) {
                    throw Rejected("nominal field is not positive binary64 zero: $name")
                }
                checks += 1
            }
        }
        return checks
    }

    /** `nominal_zero.audit_trace` over already-parsed records. */
    fun auditTrace(
        records: List<Compare.Record>,
        expectedStates: Int,
        expectedCallbacks: Int,
    ): JsonObject {
        var states = 0
        var checks = 0
        var callbacks = 0
        var timestepChecks = 0
        for (record in records) {
            val row = record.row
            when (row["kind"]?.stringOrNull()) {
                "event" -> {
                    callbacks += 1
                    timestepChecks += checkTimestep(row)
                }
                "state" -> {
                    states += 1
                    val bodies = (row["state"] as JsonObject)["bodies"] as? JsonArray
                    if (bodies == null || bodies.size != 1) {
                        throw Rejected("nominal body count differs")
                    }
                    checks += checkBody(bodies[0] as JsonObject)
                }
                else -> Unit
            }
        }
        if (states != expectedStates || callbacks != expectedCallbacks) {
            throw Rejected("nominal state or callback count differs")
        }
        return buildJsonObject {
            put("states", states)
            put("positive_zero_checks", checks)
            put("timestep_callbacks", callbacks)
            put("exact_timestep_checks", timestepChecks)
        }
    }

    fun auditPair(
        reference: List<Compare.Record>,
        candidate: List<Compare.Record>,
        expectedStates: Int,
        expectedCallbacks: Int,
    ): Pair<JsonObject, JsonObject> =
        auditTrace(reference, expectedStates, expectedCallbacks) to
            auditTrace(candidate, expectedStates, expectedCallbacks)

    /** The `nominal_positive_zero` and `nominal_timestep` blocks `compare_pair` adds. */
    fun annotate(
        outcome: JsonObject,
        reference: JsonObject,
        candidate: JsonObject,
    ): JsonObject {
        val result = LinkedHashMap<String, JsonElement>(outcome)
        result["nominal_positive_zero"] = buildJsonObject {
            for ((provider, check) in listOf("reference" to reference, "candidate" to candidate)) {
                put(
                    provider,
                    buildJsonObject {
                        put("states", check["states"] ?: JsonNull)
                        put("positive_zero_checks", check["positive_zero_checks"] ?: JsonNull)
                    },
                )
            }
        }
        result["nominal_timestep"] = buildJsonObject {
            for ((provider, check) in listOf("reference" to reference, "candidate" to candidate)) {
                put(
                    provider,
                    buildJsonObject {
                        put("timestep_callbacks", check["timestep_callbacks"] ?: JsonNull)
                        put("exact_timestep_checks", check["exact_timestep_checks"] ?: JsonNull)
                    },
                )
            }
        }
        return JsonObject(result)
    }
}
