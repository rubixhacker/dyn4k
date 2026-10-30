package io.github.rubixhacker.harness.numerical

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/**
 * `cases.declared_cases`: the declared portable numerical matrix.
 *
 * The Python declaration is ordered by dictionary insertion order, and so is this one. The
 * order, the identifiers, the case counts and every number are contract, because receipts
 * digest the canonical rendering of this list.
 */
object Cases {
    private val HALF_PI = Math.PI / 2
    private val SIXTH_PI = Math.PI / 6

    private val BOOLEAN_JOINT_FIELDS: List<Pair<String, List<String>>> = listOf(
        "Angle" to listOf("LimitsEnabled"),
        "Distance" to listOf(
            "LimitsEnabled", "LowerLimitEnabled", "UpperLimitEnabled",
            "SpringEnabled", "SpringDamperEnabled", "MaximumSpringForceEnabled",
        ),
        "Pin" to listOf("SpringEnabled", "SpringDamperEnabled", "MaximumSpringForceEnabled"),
        "Prismatic" to listOf(
            "LimitsEnabled", "LowerLimitEnabled", "UpperLimitEnabled",
            "MotorEnabled", "MaximumMotorForceEnabled", "SpringEnabled",
            "SpringDamperEnabled", "MaximumSpringForceEnabled",
        ),
        "Pulley" to listOf("SlackEnabled"),
        "Revolute" to listOf("LimitsEnabled", "MotorEnabled", "MaximumMotorTorqueEnabled"),
        "Weld" to listOf(
            "LimitsEnabled", "SpringEnabled", "SpringDamperEnabled",
            "MaximumSpringTorqueEnabled",
        ),
        "Wheel" to listOf(
            "LimitsEnabled", "LowerLimitEnabled", "UpperLimitEnabled",
            "MotorEnabled", "MaximumMotorTorqueEnabled", "SpringEnabled",
            "SpringDamperEnabled", "MaximumSpringForceEnabled",
        ),
    )

    private val NUMERIC_JOINT_FIELDS: List<Pair<String, List<Pair<String, List<Double>>>>> = listOf(
        "Angle" to listOf("Ratio" to listOf(0.5, 1.0, 2.0, -1.0)),
        "Distance" to listOf(
            "SpringDampingRatio" to listOf(0.0, 0.2, 1.0),
            "SpringFrequency" to listOf(2.0, 8.0),
            "MaximumSpringForce" to listOf(0.0, 10.0, 1000.0),
        ),
        "Friction" to listOf(
            "MaximumForce" to listOf(0.0, 10.0, 1000.0),
            "MaximumTorque" to listOf(0.0, 0.25, 10.0),
        ),
        "Motor" to listOf(
            "CorrectionFactor" to listOf(0.0, 0.3, 1.0),
            "MaximumForce" to listOf(0.0, 10.0, 1000.0),
            "MaximumTorque" to listOf(0.0, 0.25, 10.0),
        ),
        "Pin" to listOf(
            "SpringDampingRatio" to listOf(0.0, 0.2, 1.0),
            "SpringFrequency" to listOf(2.0, 8.0),
            "CorrectionFactor" to listOf(0.0, 0.3, 1.0),
            "MaximumSpringForce" to listOf(0.0, 10.0, 1000.0),
            "MaximumCorrectionForce" to listOf(0.0, 10.0, 1000.0),
        ),
        "Prismatic" to listOf(
            "SpringDampingRatio" to listOf(0.0, 0.2, 1.0),
            "SpringFrequency" to listOf(2.0, 8.0),
            "MaximumSpringForce" to listOf(0.0, 10.0, 1000.0),
            "MaximumMotorForce" to listOf(0.0, 10.0, 1000.0),
            "MotorSpeed" to listOf(-1.0, 0.0, 1.0),
        ),
        "Pulley" to listOf("Ratio" to listOf(0.5, 1.0, 2.0)),
        "Revolute" to listOf(
            "MaximumMotorTorque" to listOf(0.0, 0.25, 10.0),
            "MotorSpeed" to listOf(-HALF_PI, 0.0, HALF_PI),
        ),
        "Weld" to listOf(
            "SpringDampingRatio" to listOf(0.0, 0.2, 1.0),
            "SpringFrequency" to listOf(2.0, 8.0),
            "MaximumSpringTorque" to listOf(0.0, 0.25, 10.0),
        ),
        "Wheel" to listOf(
            "SpringDampingRatio" to listOf(0.0, 0.2, 1.0),
            "SpringFrequency" to listOf(2.0, 8.0),
            "MaximumSpringForce" to listOf(0.0, 10.0, 1000.0),
            "MaximumMotorTorque" to listOf(0.0, 0.25, 10.0),
            "MotorSpeed" to listOf(-HALF_PI, 0.0, HALF_PI),
        ),
    )

    private fun number(value: Double): JsonPrimitive = JsonPrimitive(value)
    private fun number(value: Int): JsonPrimitive = JsonPrimitive(value)
    private fun text(value: String): JsonPrimitive = JsonPrimitive(value)
    private fun flag(value: Boolean): JsonPrimitive = JsonPrimitive(value)
    private fun array(values: List<JsonElement>): JsonArray = JsonArray(values)
    private fun arrayOfNumbers(values: List<Double>): JsonArray = JsonArray(values.map { JsonPrimitive(it) })

    private fun record(vararg pairs: Pair<String, JsonElement>): JsonObject =
        JsonObject(LinkedHashMap<String, JsonElement>().apply {
            pairs.forEach { (key, value) -> put(key, value) }
        })

    fun declaredCases(): List<JsonObject> {
        val cases = ArrayList<JsonObject>()
        val scales = listOf(0.01, 1.0, 100.0)
        val origins = listOf(
            listOf(0.0, 0.0),
            listOf(1000.0, 1000.0),
            listOf(-1000.0, 1000.0),
            listOf(1000000.0, -1000000.0),
            listOf(-1000000.0, 1000000.0),
        )
        val deltas = listOf(-1e-8, -1e-12, 0.0, 1e-12, 1e-8)
        for ((scaleIndex, scale) in scales.withIndex()) {
            for ((originIndex, origin) in origins.withIndex()) {
                for ((deltaIndex, delta) in deltas.withIndex()) {
                    cases.add(
                        record(
                            "id" to text("geometry-boundary-s$scaleIndex-o$originIndex-d$deltaIndex"),
                            "family" to text("geometry-collision"),
                            "profile" to text("default"),
                            "hz" to number(60),
                            "steps" to number(1),
                            "input" to record(
                                "scale" to number(scale),
                                "origin" to arrayOfNumbers(origin),
                                "delta" to number(delta),
                                "signedZero" to number(-0.0),
                            ),
                        ),
                    )
                }
            }
        }
        cases.add(
            record(
                "id" to text("motion-forces-60"),
                "family" to text("free-motion"),
                "profile" to text("default"),
                "hz" to number(60),
                "steps" to number(600),
                "input" to record(
                    "force" to arrayOfNumbers(listOf(1.0, 0.0)),
                    "torque" to number(0.25),
                    "damping" to number(0.1),
                    "durationSeconds" to number(10),
                ),
            ),
        )
        for (hz in listOf(30, 60, 120)) {
            val restitutions = listOf(0.0, 0.5, 1.0)
            for ((restitutionIndex, restitution) in restitutions.withIndex()) {
                cases.add(
                    record(
                        "id" to text("motion-restitution-e$restitutionIndex-$hz"),
                        "family" to text("free-motion"),
                        "profile" to text("default"),
                        "hz" to number(hz),
                        "steps" to number(10 * hz),
                        "input" to record(
                            "restitution" to number(restitution),
                            "gravity" to arrayOfNumbers(listOf(0.0, -9.8)),
                            "durationSeconds" to number(10),
                        ),
                    ),
                )
            }
        }
        for (hz in listOf(30, 60, 120)) {
            cases.add(
                record(
                    "id" to text("contacts-default-$hz"),
                    "family" to text("contacts-friction-sleep-wake"),
                    "profile" to text("default"),
                    "hz" to number(hz),
                    "steps" to number(600 * hz),
                    "input" to record(
                        "impulse" to arrayOfNumbers(listOf(1.0, 0.0)),
                        "actionStep" to number(300 * hz + 1),
                        "gravity" to arrayOfNumbers(listOf(0.0, -9.8)),
                        "friction" to number(0.5),
                    ),
                ),
            )
        }
        for ((outerHz, group) in listOf(30 to 4, 60 to 2, 120 to 1)) {
            for (repetition in listOf(1, 2)) {
                cases.add(
                    record(
                        "id" to text("contacts-configured-$outerHz-r$repetition"),
                        "family" to text("contacts-friction-sleep-wake"),
                        "profile" to text("configured"),
                        "hz" to number(120),
                        "steps" to number(72000),
                        "outer_group" to number(group),
                        "input" to record(
                            "outerHz" to number(outerHz),
                            "repetition" to number(repetition),
                            "innerHz" to number(120),
                            "linearTolerance" to number(1.0 / 4096.0),
                            "positionIterations" to number(8),
                            "impulse" to arrayOfNumbers(listOf(1.0, 0.0)),
                            "actionStep" to number(36001),
                        ),
                    ),
                )
            }
        }
        val jointTypes = listOf(
            "Angle", "Distance", "Friction", "Motor", "Pin",
            "Prismatic", "Pulley", "Revolute", "Weld", "Wheel",
        )
        for (jointType in jointTypes) {
            for (mode in listOf("initial", "active")) {
                cases.add(
                    record(
                        "id" to text("joint-$jointType-$mode"),
                        "family" to text("joints-limits-motors"),
                        "profile" to text("default"),
                        "hz" to number(60),
                        "steps" to number(600),
                        "input" to record(
                            "jointType" to text(jointType),
                            "mode" to text(mode),
                            "durationSeconds" to number(10),
                        ),
                    ),
                )
            }
        }
        cases.add(
            record(
                "id" to text("P-JINT-Weld-enabled-equal"),
                "family" to text("joints-limits-motors"),
                "profile" to text("frozen-weld-pulley"),
                "hz" to number(60),
                "steps" to number(600),
                "input" to record(
                    "jointType" to text("Weld"),
                    "limits" to arrayOfNumbers(listOf(0.0, 0.0)),
                    "offCenterForce" to arrayOfNumbers(listOf(0.0, -10.0)),
                ),
            ),
        )
        for (segment in listOf("preparation-0", "preparation-1", "main")) {
            val steps = when (segment) {
                "preparation-0" -> 1
                "preparation-1" -> 2
                else -> 600
            }
            cases.add(
                record(
                    "id" to text("P-JINT-Pulley-slack-transition-$segment"),
                    "family" to text("joints-limits-motors"),
                    "profile" to text("frozen-weld-pulley"),
                    "hz" to number(60),
                    "steps" to number(steps),
                    "start_step" to number(if (segment == "preparation-1") 1 else 0),
                    "input" to record(
                        "jointType" to text("Pulley"),
                        "segment" to text(segment),
                        "sourceVelocity" to arrayOfNumbers(
                            if (segment != "preparation-0") listOf(0.0, 10.0) else listOf(0.0, 0.0),
                        ),
                    ),
                ),
            )
        }
        for ((jointType, fields) in BOOLEAN_JOINT_FIELDS) {
            for (field in fields) {
                for (variant in listOf("false", "true", "toggle")) {
                    cases.add(
                        record(
                            "id" to text("joint-$jointType-$field-$variant"),
                            "family" to text("joints-limits-motors"),
                            "profile" to text("default"),
                            "hz" to number(60),
                            "steps" to number(600),
                            "input" to record(
                                "jointType" to text(jointType),
                                "field" to text(field),
                                "variant" to text(variant),
                                "initialValue" to flag(variant == "true"),
                            ),
                        ),
                    )
                }
            }
        }
        for ((jointType, fields) in NUMERIC_JOINT_FIELDS) {
            for ((field, values) in fields) {
                for (value in values) {
                    cases.add(
                        record(
                            "id" to text("joint-$jointType-$field-$value"),
                            "family" to text("joints-limits-motors"),
                            "profile" to text("default"),
                            "hz" to number(60),
                            "steps" to number(600),
                            "input" to record(
                                "jointType" to text(jointType),
                                "field" to text(field),
                                "initialValue" to number(value),
                            ),
                        ),
                    )
                }
            }
        }
        for (jointType in listOf("Angle", "Distance", "Prismatic", "Revolute", "Weld", "Wheel")) {
            val limit = if (jointType in listOf("Angle", "Revolute", "Weld")) SIXTH_PI else 1.0
            val rangeLimits = if (jointType == "Distance") listOf(1.0, 3.0) else listOf(-limit, limit)
            for ((variant, limits) in listOf("range" to rangeLimits, "equal" to listOf(0.0, 0.0))) {
                cases.add(
                    record(
                        "id" to text("joint-$jointType-limits-$variant"),
                        "family" to text("joints-limits-motors"),
                        "profile" to text("default"),
                        "hz" to number(60),
                        "steps" to number(600),
                        "input" to record(
                            "jointType" to text(jointType),
                            "limits" to text(variant),
                            "lowerLimit" to number(limits[0]),
                            "upperLimit" to number(limits[1]),
                        ),
                    ),
                )
            }
        }
        cases.add(
            record(
                "id" to text("P-J-Angle-ratio-limits-off--1.0"),
                "family" to text("joints-limits-motors"),
                "profile" to text("baseline-failed"),
                "hz" to number(60),
                "steps" to number(600),
                "input" to record(
                    "jointType" to text("Angle"),
                    "ratio" to number(-1.0),
                    "limitsEnabled" to flag(false),
                ),
            ),
        )
        for (hz in listOf(30, 60, 120)) {
            for (shape in listOf("circle", "pentagon")) {
                for (mode in listOf("ALL", "NONE")) {
                    cases.add(
                        record(
                            "id" to text("ccd-$shape-$mode-$hz"),
                            "family" to text("ccd"),
                            "profile" to text("default"),
                            "hz" to number(hz),
                            "steps" to number(hz),
                            "input" to record(
                                "shape" to text(shape),
                                "mode" to text(mode),
                                "speed" to number(-120.0),
                                "durationSeconds" to number(1),
                            ),
                        ),
                    )
                }
            }
        }
        cases.add(
            record(
                "id" to text("long-free-60"),
                "family" to text("long-running-invariant"),
                "profile" to text("default"),
                "hz" to number(60),
                "steps" to number(36000),
                "input" to record(
                    "velocity" to arrayOfNumbers(listOf(0.25, -0.125)),
                    "angularVelocity" to number(0.5),
                    "durationSeconds" to number(600),
                ),
            ),
        )
        return cases.map(::annotate)
    }

    /** The second half of `declared_cases`: derived coverage and frozen-projection identity. */
    private fun annotate(source: JsonObject): JsonObject {
        val case = LinkedHashMap<String, JsonElement>(source)
        case["require_setup"] = flag(true)
        val id = source.getValue("id").stringOrNull().orEmpty()
        val profile = source.getValue("profile").stringOrNull().orEmpty()
        val frozen = id == "long-free-60" ||
            id.startsWith("contacts-default-") ||
            id.startsWith("contacts-configured-") ||
            profile == "frozen-weld-pulley"
        case["require_frozen_projection"] = flag(frozen)
        if (frozen) {
            case["frozen_origin"] = arrayOfNumbers(listOf(0.0, 0.0))
            case["frozen_scale"] = number(1.0)
            when {
                id == "long-free-60" -> case["frozen_id"] = text("L-free-s1.0-o0.0,0.0-hz60")
                id.startsWith("contacts-default-") ->
                    case["frozen_id"] = text("S-sleep-wake-hz" + id.substringAfterLast("-"))
                id.startsWith("contacts-configured-") -> {
                    val input = source.getValue("input") as JsonObject
                    val outerHz = input.getValue("outerHz").intOrNull() ?: 0
                    val repetition = input.getValue("repetition").intOrNull() ?: 0
                    case["frozen_id"] = text("Q-sleep-wake-outer$outerHz-repeat$repetition")
                    val group = source.getValue("outer_group").intOrNull() ?: 0
                    val steps = source.getValue("steps").intOrNull() ?: 0
                    case["frozen_grouping"] = record(
                        "outerHz" to number(outerHz),
                        "repetition" to number(repetition),
                        "innerPerOuter" to number(group),
                        "outerDt" to number(1.0 / outerHz),
                        "outerSteps" to number(steps / group),
                        "actionInnerStep" to number(input.getValue("actionStep").intOrNull() ?: 0),
                    )
                }
                id.startsWith("P-JINT-Pulley-slack-transition-preparation-") ->
                    case["frozen_id"] = text("P-JINT-Pulley-slack-transition-preparation")
                id == "P-JINT-Pulley-slack-transition-main" ->
                    case["frozen_id"] = text("P-JINT-Pulley-slack-transition")
                else -> case["frozen_id"] = text(id)
            }
        }
        case["min_step_events"] = number(1)
        var actions = JsonArray(emptyList())
        var callbacks = JsonArray(emptyList())
        if (id == "P-JINT-Weld-enabled-equal" || id == "P-JINT-Pulley-slack-transition-main") {
            callbacks = JsonArray(listOf(number(1)))
        }
        if (id.startsWith("contacts-default-") || id.startsWith("contacts-configured-")) {
            val actionStep = (source.getValue("input") as JsonObject).getValue("actionStep")
            callbacks = JsonArray(listOf(actionStep, actionStep))
        }
        when {
            id == "motion-forces-60" ->
                actions = JsonArray((1..60).map { number(it) })
            id.startsWith("contacts-default-") -> actions =
                JsonArray(listOf((source.getValue("input") as JsonObject).getValue("actionStep")))
            id.startsWith("contacts-configured-") ->
                actions = JsonArray(listOf(number(36001)))
            id.startsWith("joint-") &&
                (source.getValue("input") as JsonObject)["mode"]?.stringOrNull() == "active" ->
                actions = JsonArray(listOf(number(201), number(401)))
            id.startsWith("joint-") &&
                (source.getValue("input") as JsonObject)["variant"]?.stringOrNull() == "toggle" ->
                actions = JsonArray(listOf(number(201), number(401)))
            id == "P-JINT-Pulley-slack-transition-main" ->
                actions = JsonArray(listOf(number(201), number(401)))
        }
        case["expected_actions"] = actions
        case["expected_instrumented_callbacks"] = callbacks
        return JsonObject(case)
    }
}
