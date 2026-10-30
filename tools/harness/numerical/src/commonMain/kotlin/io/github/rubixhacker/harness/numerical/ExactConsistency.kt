package io.github.rubixhacker.harness.numerical

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/**
 * `exact_consistency`: the structural contract the recorded sleep/wake snapshots must satisfy.
 *
 * Every rejection message is contract; the Python assertions match several of them by regex.
 */
object ExactConsistency {
    private val TRANSFORM_FIELDS = setOf(
        "getCost", "getSint", "getRotationAngle", "getTranslation",
        "getTranslationX", "getTranslationY", "getValues", "isIdentity", "type",
    )

    private val DUPLICATES: List<Pair<String, String>> = listOf(
        "getForce" to "force",
        "getAccumulatedForce" to "accumulatedForce",
        "getTorque" to "torque",
        "getAccumulatedTorque" to "accumulatedTorque",
        "getLinearVelocity" to "velocity",
        "getAngularVelocity" to "angularVelocity",
        "getTransform" to "transform",
        "getPreviousTransform" to "previousTransform",
        "getWorldCenter" to "worldCenter",
        "isAtRest" to "atRest",
    )

    private val BODY_FIELDS = setOf(
        "id", "atRest", "force", "accumulatedForce", "torque",
        "accumulatedTorque", "velocity", "angularVelocity", "worldCenter",
        "fixedOriginPosition", "transform", "previousTransform",
        "rotationIncrementSum", "rotationStepBoundBelowPi", "rotationTrackingScope",
    )

    private val PROPERTY_FIELDS = DUPLICATES.map { it.first }.toSet() + setOf(
        "getAngularDamping", "getChangeInOrientation", "getChangeInPosition",
        "getFixtureCount", "getGravityScale", "getLinearDamping", "getLocalCenter",
        "getMass", "getRotationDiscRadius", "isAtRestDetectionEnabled", "isBullet",
        "isDynamic", "isEnabled", "isKinematic", "isStatic", "type",
    )

    private val TIMESTEP_FIELDS = setOf(
        "getDeltaTime", "getDeltaTimeRatio", "getInverseDeltaTime",
        "getPreviousInverseDeltaTime", "getPrevousDeltaTime", "type",
    )

    private fun require(condition: Boolean, reason: String) {
        if (!condition) throw Rejected(reason)
    }

    private fun finite(value: JsonElement?, path: String = "snapshot") {
        when {
            value is JsonPrimitive && value.isNumber() ->
                require(value.numberOrNull()?.isFinite() == true, "nonfinite $path")
            value is JsonObject -> value.forEach { (key, child) -> finite(child, "$path.$key") }
            value is JsonArray -> value.forEachIndexed { index, child ->
                finite(child, "$path[$index]")
            }
        }
    }

    private fun fields(value: JsonElement?, expected: Set<String>, label: String) {
        val dictionary = value as? JsonObject
        require(dictionary != null && dictionary.keys == expected, "$label schema")
    }

    private fun equal(left: JsonElement?, right: JsonElement?, label: String) {
        require(same(left, right), label)
    }

    private fun JsonObject.body(index: Int): JsonObject = getValue("bodies").let {
        ((it as JsonArray)[index] as JsonObject)
    }

    private fun transformAliases(transformElement: JsonElement?) {
        fields(transformElement, TRANSFORM_FIELDS, "transform")
        val transform = transformElement as JsonObject
        require(
            transform["getRotationAngle"].isNumber() && transform["isIdentity"].isBoolean(),
            "transform schema",
        )
        equal(
            transform["getTranslation"],
            JsonArray(
                listOf(
                    transform["getTranslationX"] ?: JsonNull,
                    transform["getTranslationY"] ?: JsonNull,
                ),
            ),
            "translation alias",
        )
        val cosine = transform.getValue("getCost")
        val sine = transform.getValue("getSint")
        equal(
            transform["getValues"],
            JsonArray(
                listOf(
                    cosine,
                    negate(sine),
                    transform["getTranslationX"] ?: JsonNull,
                    sine,
                    cosine,
                    transform["getTranslationY"] ?: JsonNull,
                ),
            ),
            "matrix alias",
        )
    }

    private fun negate(value: JsonElement): JsonElement {
        val number = value.numberOrNull()
        return if (number == null) JsonNull else JsonPrimitive(-number)
    }

    fun checkSnapshot(state: JsonElement?, phase: String, prior: JsonObject? = null) {
        require(
            phase == "initial" || phase == "step" || phase == "before" || phase == "after",
            "snapshot phase",
        )
        fields(state, setOf("bodies", "joints"), "state")
        finite(state)
        val snapshot = state as JsonObject
        val bodies = snapshot.getValue("bodies") as JsonArray
        require(bodies.size == 2, "two bodies")
        equal(snapshot["joints"], JsonArray(emptyList()), "no joints")
        for (index in 0 until 2) {
            val body = bodies[index] as JsonObject
            fields(
                body,
                if (phase == "step") {
                    BODY_FIELDS
                } else {
                    BODY_FIELDS + setOf("properties", "fixtures")
                },
                "body",
            )
            equal(body["id"], JsonPrimitive("b$index"), "body identity")
            require(body["atRest"].isBoolean(), "atRest schema")
            require(body["rotationIncrementSum"].isNumber(), "rotation accumulator schema")
            require(body["angularVelocity"].isNumber(), "angular velocity schema")
            run {
                val velocity = body["velocity"] as? JsonArray
                require(
                    velocity != null && velocity.size == 2 && velocity.all { it.isNumber() },
                    "velocity schema",
                )
            }
            for ((field, target) in listOf(
                "force" to JsonArray(listOf(JsonPrimitive(0), JsonPrimitive(0))),
                "accumulatedForce" to JsonArray(listOf(JsonPrimitive(0), JsonPrimitive(0))),
                "torque" to JsonPrimitive(0),
                "accumulatedTorque" to JsonPrimitive(0),
            )) {
                equal(body[field], target, "$field zero")
            }
            transformAliases(body["transform"])
            transformAliases(body["previousTransform"])
            equal(
                body["worldCenter"],
                (body.getValue("transform") as JsonObject)["getTranslation"],
                "world center alias",
            )
            equal(body["fixedOriginPosition"], body["worldCenter"], "fixed origin alias")
            if (phase != "step") {
                val fixtures = body["fixtures"]
                require(fixtures is JsonArray && fixtures.size == 1, "snapshot fixtures")
                val properties = body["properties"]
                fields(properties, PROPERTY_FIELDS, "properties")
                val propertyObject = properties as JsonObject
                for ((getter, source) in DUPLICATES) {
                    equal(propertyObject[getter], body[source], "duplicate $getter")
                }
                equal(
                    propertyObject["getLocalCenter"],
                    JsonArray(listOf(JsonPrimitive(0), JsonPrimitive(0))),
                    "local center alias premise",
                )
                equal(
                    (propertyObject["getMass"] as? JsonObject)?.get("getCenter"),
                    JsonArray(listOf(JsonPrimitive(0), JsonPrimitive(0))),
                    "mass center alias premise",
                )
            }
            if (index == 0) {
                val transform = body.getValue("transform") as JsonObject
                equal(
                    transform["getTranslation"],
                    JsonArray(listOf(JsonPrimitive(0), JsonPrimitive(-0.25))),
                    "floor pose",
                )
                equal(
                    JsonArray(
                        listOf(
                            transform["getCost"] ?: JsonNull,
                            transform["getSint"] ?: JsonNull,
                            transform["getRotationAngle"] ?: JsonNull,
                        ),
                    ),
                    JsonArray(listOf(JsonPrimitive(1), JsonPrimitive(0), JsonPrimitive(0))),
                    "floor rotation",
                )
                equal(
                    body["velocity"],
                    JsonArray(listOf(JsonPrimitive(0), JsonPrimitive(0))),
                    "floor velocity",
                )
                equal(body["angularVelocity"], JsonPrimitive(0), "floor angular velocity")
                equal(body["rotationIncrementSum"], JsonPrimitive(0), "floor rotation accumulator")
                equal(body["previousTransform"], body["transform"], "floor previous pose")
            }
            if (index == 1 && body["atRest"].booleanOrNull() == true) {
                equal(
                    body["velocity"],
                    JsonArray(listOf(JsonPrimitive(0), JsonPrimitive(0))),
                    "sleep velocity",
                )
                equal(body["angularVelocity"], JsonPrimitive(0), "sleep angular velocity")
                if (prior != null && prior.body(1)["atRest"].booleanOrNull() == true) {
                    equal(
                        body["transform"],
                        prior.body(1)["transform"],
                        "sleep pose freeze",
                    )
                }
            }
            if (phase == "initial") {
                equal(body["previousTransform"], body["transform"], "initial previous copy")
            } else {
                require(prior != null, "prior snapshot required")
                val earlier = prior!!.body(index)
                equal(
                    body["previousTransform"],
                    if (phase == "step") earlier["transform"] else earlier["previousTransform"],
                    "phase-correct previous copy",
                )
                if (phase == "before" || phase == "after") {
                    equal(body["transform"], earlier["transform"], "action current pose copy")
                }
            }
        }
    }

    fun checkImpulse(before: JsonElement?, after: JsonElement?) {
        finite(before)
        finite(after)
        val beforeObject = before as JsonObject
        val afterObject = after as JsonObject
        val first = beforeObject.body(1)
        val second = afterObject.body(1)
        equal(
            JsonArray(
                listOf(
                    first["atRest"] ?: JsonNull,
                    first["velocity"] ?: JsonNull,
                    first["angularVelocity"] ?: JsonNull,
                ),
            ),
            JsonArray(
                listOf(
                    JsonPrimitive(true),
                    JsonArray(listOf(JsonPrimitive(0), JsonPrimitive(0))),
                    JsonPrimitive(0),
                ),
            ),
            "impulse sleeping input",
        )
        equal(
            JsonArray(
                listOf(
                    second["atRest"] ?: JsonNull,
                    second["velocity"] ?: JsonNull,
                    second["angularVelocity"] ?: JsonNull,
                ),
            ),
            JsonArray(
                listOf(
                    JsonPrimitive(false),
                    JsonArray(listOf(JsonPrimitive(1), JsonPrimitive(0))),
                    JsonPrimitive(0),
                ),
            ),
            "impulse immediate output",
        )
        val expected = LinkedHashMap<String, JsonElement>(beforeObject)
        val expectedBodies = ArrayList<JsonElement>(beforeObject.getValue("bodies") as JsonArray)
        val body = LinkedHashMap<String, JsonElement>(expectedBodies.last() as JsonObject)
        body["atRest"] = JsonPrimitive(false)
        body["velocity"] = JsonArray(listOf(JsonPrimitive(1), JsonPrimitive(0)))
        val properties = LinkedHashMap<String, JsonElement>(body.getValue("properties") as JsonObject)
        properties["isAtRest"] = JsonPrimitive(false)
        properties["getLinearVelocity"] = JsonArray(listOf(JsonPrimitive(1), JsonPrimitive(0)))
        body["properties"] = JsonObject(properties)
        expectedBodies[expectedBodies.size - 1] = JsonObject(body)
        expected["bodies"] = JsonArray(expectedBodies)
        equal(JsonObject(expected), after, "impulse unchanged fields")
    }

    fun checkTimeStep(value: JsonElement?, hz: Int, step: Int) {
        require(hz == 30 || hz == 60 || hz == 120, "timestep scope")
        require(step >= 1, "timestep scope")
        fields(value, TIMESTEP_FIELDS, "timestep")
        val timestep = value as JsonObject
        equal(timestep["type"], JsonPrimitive("org.dyn4j.dynamics.TimeStep"), "timestep type")
        val old = if (step == 1) 1.0 / 60.0 else 1.0 / hz
        for ((key, expected) in listOf(
            "getDeltaTime" to 1.0 / hz,
            "getInverseDeltaTime" to hz.toDouble(),
            "getPrevousDeltaTime" to old,
            "getPreviousInverseDeltaTime" to 1.0 / old,
            "getDeltaTimeRatio" to (1.0 / hz) / old,
        )) {
            equal(timestep[key], JsonPrimitive(expected), "timestep $key")
        }
    }

    fun checkEndpoint(endpoint: JsonElement?, inner: JsonObject, outerHz: Int) {
        fields(endpoint, setOf("kind", "outerStep", "state", "step"), "endpoint")
        val value = endpoint as JsonObject
        val group = 120 / outerHz
        val innerStep = inner["step"]
        val innerStepValue = innerStep.numberOrNull()
        require(
            value["kind"]?.stringOrNull() == "outer-endpoint" &&
                innerStepValue != null && innerStepValue % group == 0.0 &&
                exact(value["step"], innerStep) &&
                exact(value["outerStep"], JsonPrimitive(innerStepValue.toInt() / group)) &&
                same(value["state"], inner["state"]),
            "endpoint numeric copy",
        )
    }

    fun auditRows(
        rows: List<JsonObject>,
        caseId: String,
        outerHz: Int,
        configured: Boolean,
    ): JsonObject {
        require(outerHz == 30 || outerHz == 60 || outerHz == 120, "unsupported exact-consistency rate")
        val innerHz = if (configured) 120 else outerHz
        val group = if (configured) 120 / outerHz else null
        val expectedStates = if (configured) 72000 else 600 * outerHz
        val actionStep = if (configured) 36001 else 300 * outerHz + 1
        val coverage = LinkedHashMap<String, Int>()
        for (name in listOf(
            "initial", "inner", "before", "after", "impulse", "timestep", "endpoints",
            "sleeping_states", "sleep_pose_comparisons",
        )) {
            coverage[name] = 0
        }
        val counts = LinkedHashMap<String, Int>()
        var prior: JsonObject? = null
        var before: JsonElement? = null
        var last: JsonObject? = null
        var states = 0
        var orderedStep = 0
        var order = 0
        var actionPhase = 0
        var pendingEndpoint = false
        var lifecycle = ArrayList<String>()
        for (row in rows) {
            finite(row, "record")
            val kind = row.getValue("kind").stringOrNull().orEmpty()
            counts[kind] = (counts[kind] ?: 0) + 1
            if (pendingEndpoint) require(kind == "outer-endpoint", "missing endpoint")
            if (kind == "inputs") {
                require(counts[kind] == 1 && states == 0, "one initial snapshot")
                equal(row["id"], JsonPrimitive(caseId), "configured input identity")
                equal(row["dt"], JsonPrimitive(1.0 / innerHz), "input timestep")
                equal(row["steps"], JsonPrimitive(expectedStates), "input state count")
                if (configured) {
                    val grouping = row.getValue("grouping") as JsonObject
                    equal(grouping["innerPerOuter"], JsonPrimitive(group!!), "configured grouping")
                    equal(grouping["outerHz"], JsonPrimitive(outerHz), "configured outer rate")
                } else {
                    require(!row.containsKey("grouping"), "unexpected default grouping")
                }
                checkSnapshot(row["state"], "initial")
                prior = row.getValue("state") as JsonObject
                coverage["initial"] = coverage.getValue("initial") + 1
                continue
            }
            require(coverage.getValue("initial") == 1, "inputs first")
            if (kind == "outer-endpoint") {
                require(pendingEndpoint && configured, "unexpected endpoint")
                checkEndpoint(row, last!!, outerHz)
                coverage["endpoints"] = coverage.getValue("endpoints") + 1
                pendingEndpoint = false
                continue
            }
            equal(row["step"], JsonPrimitive(states + 1), "record step")
            val step = row.getValue("step").intOrNull()!!
            if (orderedStep != step) {
                orderedStep = step
                order = 0
            }
            if (kind != "state") {
                equal(row["order"], JsonPrimitive(order), "record order")
                order += 1
            }
            when (kind) {
                "instrumented-callback" -> {
                    equal(row["step"], JsonPrimitive(actionStep), "action callback step")
                    val values = row.getValue("values") as JsonArray
                    require(values.size == 1, "action callback values")
                    val phase = when (row["event"]?.stringOrNull()) {
                        "before-wake" -> "before"
                        "after-wake" -> "after"
                        else -> null
                    }
                    if (phase == null) throw Rejected("known action callback")
                    equal(
                        JsonPrimitive(actionPhase),
                        JsonPrimitive(if (phase == "before") 0 else 2),
                        "action callback order",
                    )
                    equal(
                        row["order"],
                        JsonPrimitive(if (phase == "before") 0 else 2),
                        "action callback position",
                    )
                    checkSnapshot(values[0], phase, prior)
                    coverage[phase] = coverage.getValue(phase) + 1
                    if (phase == "before") {
                        before = values[0]
                        actionPhase = 1
                    } else {
                        checkImpulse(before, values[0])
                        coverage["impulse"] = coverage.getValue("impulse") + 1
                        prior = values[0] as JsonObject
                        actionPhase = 3
                    }
                }
                "action" -> {
                    equal(row["step"], JsonPrimitive(actionStep), "action step")
                    equal(row["order"], JsonPrimitive(1), "action order")
                    equal(JsonPrimitive(actionPhase), JsonPrimitive(1), "before/action/after sequence")
                    equal(
                        row["description"],
                        JsonPrimitive(
                            "impulse=(1,0) at center; sleepingBefore=true; " +
                                "precedingSecondAsleep=true",
                        ),
                        "action identity",
                    )
                    actionPhase = 2
                }
                "event" -> {
                    if (step == actionStep) {
                        equal(JsonPrimitive(actionPhase), JsonPrimitive(3), "action before physics callbacks")
                    }
                    if (row["listener"]?.stringOrNull() == "StepListener") {
                        val payload = row.getValue("payload") as JsonArray
                        require(payload.size == 2, "step listener payload")
                        equal(
                            payload[1],
                            buildJsonObject { put("world", caseId) },
                            "step listener world",
                        )
                        checkTimeStep(payload[0], innerHz, step)
                        coverage["timestep"] = coverage.getValue("timestep") + 1
                        val found = Regex("""\.([^. (]+)\(""").find(
                            row["method"]?.stringOrNull().orEmpty(),
                        )
                        require(found != null, "step listener method")
                        lifecycle.add(found!!.groupValues[1])
                    }
                }
                "state" -> {
                    if (step == actionStep) {
                        equal(JsonPrimitive(actionPhase), JsonPrimitive(3), "complete action before physics state")
                    }
                    equal(
                        JsonArray(lifecycle.map { JsonPrimitive(it) }),
                        JsonArray(
                            (if (step == 1) {
                                listOf("begin", "updatePerformed", "postSolve", "end")
                            } else {
                                listOf("begin", "postSolve", "end")
                            }).map { JsonPrimitive(it) },
                        ),
                        "complete ordered step lifecycle",
                    )
                    lifecycle = ArrayList()
                    states += 1
                    val grouping = group
                    if (grouping != null) {
                        equal(
                            row["outerStep"],
                            JsonPrimitive((states - 1) / grouping + 1),
                            "outer step grouping",
                        )
                        equal(
                            row["innerWithinOuter"],
                            JsonPrimitive((states - 1) % grouping + 1),
                            "inner step grouping",
                        )
                    } else {
                        require(
                            !row.containsKey("outerStep") && !row.containsKey("innerWithinOuter"),
                            "unexpected default grouping",
                        )
                    }
                    checkSnapshot(row["state"], "step", prior)
                    coverage["inner"] = coverage.getValue("inner") + 1
                    val state = row.getValue("state") as JsonObject
                    if (state.body(1)["atRest"].booleanOrNull() == true) {
                        coverage["sleeping_states"] = coverage.getValue("sleeping_states") + 1
                        if (prior!!.body(1)["atRest"].booleanOrNull() == true) {
                            coverage["sleep_pose_comparisons"] =
                                coverage.getValue("sleep_pose_comparisons") + 1
                        }
                    }
                    prior = state
                    last = row
                    pendingEndpoint = grouping != null && states % grouping == 0
                }
                else -> throw Rejected("unclassified exact-consistency record $kind")
            }
        }
        require(!pendingEndpoint, "missing final endpoint")
        equal(JsonPrimitive(states), JsonPrimitive(expectedStates), "complete inner states")
        equal(JsonPrimitive(coverage.getValue("initial")), JsonPrimitive(1), "initial coverage")
        equal(
            JsonArray(
                listOf(
                    JsonPrimitive(coverage.getValue("before")),
                    JsonPrimitive(coverage.getValue("after")),
                    JsonPrimitive(coverage.getValue("impulse")),
                ),
            ),
            JsonArray(listOf(JsonPrimitive(1), JsonPrimitive(1), JsonPrimitive(1))),
            "wake action coverage",
        )
        equal(
            JsonPrimitive(coverage.getValue("timestep")),
            JsonPrimitive(3 * expectedStates + 1),
            "timestep coverage",
        )
        equal(
            JsonPrimitive(coverage.getValue("endpoints")),
            JsonPrimitive(if (configured) 600 * outerHz else 0),
            "endpoint coverage",
        )
        require(
            coverage.getValue("sleeping_states") > 0 &&
                coverage.getValue("sleep_pose_comparisons") > 0,
            "sleep coverage",
        )
        return buildJsonObject {
            put("status", "PASSED")
            put("case_id", caseId)
            put("outer_hz", outerHz)
            put("profile", if (configured) "configured" else "default")
            put(
                "groups",
                buildJsonObject {
                    for (name in listOf(
                        "fixed_floor", "zero_applied_force",
                        "sleep_velocity_and_own_run_pose", "immediate_center_impulse",
                        "aliases_previous_copies_and_duplicates", "timestep_metadata",
                    )) {
                        put(name, "PASSED")
                    }
                },
            )
            put(
                "coverage",
                buildJsonObject { coverage.forEach { (name, count) -> put(name, count) } },
            )
            put("counts", buildJsonObject { counts.forEach { (name, count) -> put(name, count) } })
            put("qualification", "UNPASSED")
        }
    }

    /**
     * `reference_diagnostic.projected_records`: the frozen projection carried by each portable
     * record, re-stamped with the inner and outer step indices.
     */
    fun projectedRecords(portable: List<JsonObject>): List<JsonObject> {
        val projected = ArrayList<JsonObject>()
        var grouping: JsonObject? = null
        for (row in portable) {
            when (row["kind"]?.stringOrNull()) {
                "inputs" -> {
                    val frozen = row["frozenInput"] as? JsonObject
                        ?: throw Rejected("frozen input projection is absent")
                    grouping = frozen["grouping"] as? JsonObject
                    projected.add(frozen)
                }
                "event" -> projected.add(
                    row["frozenEvent"] as? JsonObject
                        ?: throw Rejected("frozen event projection is absent"),
                )
                "action" -> {
                    val frozen = row["frozenRecords"] as? JsonArray
                    if (frozen == null || frozen.isEmpty()) {
                        throw Rejected("frozen action projection is absent")
                    }
                    frozen.forEach { projected.add(it as JsonObject) }
                }
                "instrumented-callback" -> projected.add(
                    row["frozenRecord"] as? JsonObject
                        ?: throw Rejected("frozen instrumented callback projection is absent"),
                )
                "state" -> {
                    val frozen = row["frozenState"] as? JsonObject
                        ?: throw Rejected("frozen state projection is absent")
                    val result = LinkedHashMap<String, JsonElement>()
                    result["kind"] = JsonPrimitive("state")
                    result["step"] = row.getValue("step")
                    result["state"] = frozen
                    if (grouping != null) {
                        val group = grouping!!.getValue("innerPerOuter").intOrNull()!!
                        val step = row.getValue("step").intOrNull()!!
                        result["outerStep"] = JsonPrimitive((step - 1) / group + 1)
                        result["innerWithinOuter"] = JsonPrimitive((step - 1) % group + 1)
                    }
                    projected.add(JsonObject(result))
                }
                "endpoint" -> {
                    val current = grouping ?: throw Rejected("unexpected frozen outer endpoint")
                    projected.add(
                        buildJsonObject {
                            put("kind", "outer-endpoint")
                            put("step", row.getValue("step"))
                            put(
                                "outerStep",
                                (row.getValue("step").intOrNull() ?: 0) /
                                    current.getValue("innerPerOuter").intOrNull()!!,
                            )
                            put("state", row["frozenState"] ?: JsonNull)
                        },
                    )
                }
            }
        }
        return projected
    }

    fun auditTrace(
        portable: List<JsonObject>,
        caseId: String,
        outerHz: Int,
        configured: Boolean,
    ): JsonObject = try {
        auditRows(projectedRecords(portable), caseId, outerHz, configured)
    } catch (error: Rejected) {
        failed(caseId, outerHz, configured, error)
    } catch (error: NoSuchElementException) {
        failed(caseId, outerHz, configured, error)
    } catch (error: IndexOutOfBoundsException) {
        failed(caseId, outerHz, configured, error)
    } catch (error: NullPointerException) {
        failed(caseId, outerHz, configured, error)
    } catch (error: ClassCastException) {
        failed(caseId, outerHz, configured, error)
    } catch (error: IllegalArgumentException) {
        failed(caseId, outerHz, configured, error)
    }

    private fun failed(
        caseId: String,
        outerHz: Int,
        configured: Boolean,
        error: Exception,
    ): JsonObject = buildJsonObject {
        put("status", "FAILED")
        put("case_id", caseId)
        put("outer_hz", outerHz)
        put("profile", if (configured) "configured" else "default")
        put("reason", error.message.orEmpty())
        put("qualification", "UNPASSED")
    }
}
