package io.github.rubixhacker.harness.numerical

import io.github.rubixhacker.harness.contract.CanonicalJson
import io.github.rubixhacker.harness.contract.Sha256
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/** `receipt.Identity`. */
data class Identity(
    val candidateCommit: String,
    val sourceSha256: String,
    val artifactSha256: Map<String, String>,
    val runtime: JsonElement,
)

/** The parts of `tools/numerical/fixtures.json` that a receipt seals. */
data class FixtureCatalog(
    val baselineSourceRevision: String,
    val baselineJarSha256: String,
    val referenceGzipSha256: Map<String, String>,
)

private val ZERO_TWO = JsonArray(listOf(JsonPrimitive(0.0), JsonPrimitive(0.0)))
private val NEGATIVE_GRAVITY = JsonArray(listOf(JsonPrimitive(0.0), JsonPrimitive(-9.8)))

private fun numbers(vararg values: Double): JsonArray = JsonArray(values.map { JsonPrimitive(it) })

private fun dict(value: JsonElement?, message: String): JsonObject =
    value as? JsonObject ?: throw Rejected(message)

private fun list(value: JsonElement?): JsonArray? = value as? JsonArray

/** The first fixture of a body, which every declaration requires to have exactly one. */
private fun fixtureOf(body: JsonElement): JsonObject =
    (dict(body, "input body setup is malformed")["fixtures"] as JsonArray)[0] as JsonObject

/** `receipt` validation of a recorded portable trace. */
object Receipt {
    private val REQUIRED_SETTINGS = setOf(
        "gravity", "stepFrequency", "maximumTranslation", "maximumRotation",
        "atRestDetectionEnabled", "maximumAtRestLinearVelocity",
        "maximumAtRestAngularVelocity", "minimumAtRestTime", "velocityIterations",
        "positionIterations", "warmStartingEnabled", "maximumWarmStartDistance",
        "linearTolerance", "angularTolerance", "maximumLinearCorrection",
        "maximumAngularCorrection", "baumgarte", "continuousDetectionMode",
        "narrowphase", "timeOfImpact",
    )

    private val REQUIRED_BODY = setOf(
        "transform", "massType", "mass", "inertia", "massCenter", "linearDamping",
        "angularDamping", "initialVelocity", "initialAngularVelocity",
        "atRestDetectionEnabled", "bullet", "fixtures",
    )

    private val REQUIRED_FIXTURE = setOf(
        "density", "friction", "restitution", "restitutionVelocity", "sensor",
        "filter", "shape",
    )

    private val REQUIRED_STATE_BODY = setOf(
        "transform", "previousTransform", "worldCenter", "fixedOriginPosition",
        "velocity", "angularVelocity", "force", "torque", "accumulatedForce",
        "accumulatedTorque", "atRest", "bullet", "rotationIncrementSum",
        "kineticEnergy", "linearMomentum", "angularMomentumCenter",
    )

    private val REQUIRED_TRANSFORM = setOf(
        "getTranslation", "getTranslationX", "getTranslationY", "getCost",
        "getSint", "getRotationAngle", "getValues",
    )

    private const val DEFAULT_TOI_DISTANCE_EPSILON = 4.806217383937352e-6

    private fun JsonElement?.isTrue(): Boolean = this?.booleanOrNull() == true

    private fun JsonElement?.isFalse(): Boolean = this?.booleanOrNull() == false

    private fun JsonObject.required(key: String): JsonElement =
        this[key] ?: throw NoSuchElementException("KeyError: $key")

    private fun JsonObject.number(key: String): Double = required(key).numberOrNull()!!

    /** `receipt.validate_setup`. */
    fun validateSetup(header: JsonObject, case: JsonObject) {
        val settings = header["settings"] as? JsonObject
        val setup = header["setup"] as? JsonObject
        if (settings == null || setup == null) {
            throw Rejected("input settings or setup is absent")
        }
        require(settings.keys.containsAll(REQUIRED_SETTINGS), "input settings omit a required field")
        val toi = settings["timeOfImpact"] as? JsonObject
        if (toi == null) throw Rejected("input TOI settings are malformed")
        require(
            exact(toi["distanceEpsilon"], JsonPrimitive(DEFAULT_TOI_DISTANCE_EPSILON)),
            "default TOI distance epsilon differs from pinned cbrt value",
        )
        val bodies = setup["bodies"] as? JsonArray
        val joints = setup["joints"] as? JsonArray
        if (bodies == null || bodies.isEmpty() || joints == null) {
            throw Rejected("input body or joint setup is absent")
        }
        for ((index, bodyElement) in bodies.withIndex()) {
            val body = bodyElement as? JsonObject
            if (body == null) throw Rejected("input body setup is malformed")
            require(body["id"]?.stringOrNull() == "b$index", "input body identity differs")
            require(body.keys.containsAll(REQUIRED_BODY), "input body setup omits a required field")
            val fixtures = body["fixtures"] as? JsonArray
            if (fixtures == null || fixtures.isEmpty()) {
                throw Rejected("input fixture setup is empty")
            }
            require(fixtures.size == 1, "input fixture count differs")
            for ((fixtureIndex, fixtureElement) in fixtures.withIndex()) {
                val fixture = fixtureElement as? JsonObject
                if (fixture == null) throw Rejected("input fixture setup is malformed")
                require(
                    fixture["id"]?.stringOrNull() == "b${index}f$fixtureIndex",
                    "input fixture identity differs",
                )
                require(
                    fixture.keys.containsAll(REQUIRED_FIXTURE),
                    "input fixture setup omits a required field",
                )
                require(
                    fixture["filter"]?.stringOrNull() == "DEFAULT_FILTER",
                    "unsupported fixture filter",
                )
                val shape = fixture["shape"] as? JsonObject
                require(shape != null && shape.containsKey("type"), "input shape setup is absent")
                require(
                    exact(fixture["density"], JsonPrimitive(1.0)) && fixture["sensor"].isFalse(),
                    "input fixture density or sensor differs",
                )
            }
        }
        for ((index, jointElement) in joints.withIndex()) {
            val joint = jointElement as? JsonObject
            if (joint == null) throw Rejected("input joint setup is malformed")
            require(
                joint["id"]?.stringOrNull() == "j$index" &&
                    joint["mode"] is JsonObject &&
                    joint["bodies"] is JsonArray,
                "input joint identity or mode is absent",
            )
        }
        val input = case.required("input") as JsonObject
        when (case.required("family").stringOrNull()) {
            "geometry-collision" -> validateGeometry(settings, input, bodies, joints)
            "free-motion" -> validateFreeMotion(settings, case, input, bodies, joints)
            "contacts-friction-sleep-wake" ->
                validateContacts(settings, case, bodies, joints)
            "joints-limits-motors" -> validateJoints(settings, case, input, bodies, joints)
            "ccd" -> validateCcd(settings, input, bodies, joints)
            "long-running-invariant" -> validateLongRun(settings, input, bodies, joints)
            else -> Unit
        }
    }

    private fun validateGeometry(
        settings: JsonObject,
        input: JsonObject,
        bodies: JsonArray,
        joints: JsonArray,
    ) {
        val scale = input.number("scale")
        val origin = input.required("origin") as JsonArray
        val ox = origin[0].numberOrNull()!!
        val oy = origin[1].numberOrNull()!!
        val delta = input.number("delta")
        require(
            bodies.size == 2 && joints.isEmpty() &&
                exact(
                    ((fixtureOf(bodies[0])["shape"] as JsonObject)["radius"]),
                    JsonPrimitive(scale),
                ) &&
                exact(
                    ((fixtureOf(bodies[1])["shape"] as JsonObject)["radius"]),
                    JsonPrimitive(0.5 * scale),
                ) &&
                exact(
                    dict(bodies[0], "")["transform"].let { (it as JsonObject)["getTranslation"] },
                    numbers(ox, oy),
                ) &&
                exact(
                    dict(bodies[1], "")["transform"].let { (it as JsonObject)["getTranslation"] },
                    numbers(ox + scale * (1.5 + delta), oy),
                ),
            "geometry boundary input differs",
        )
    }

    private fun validateFreeMotion(
        settings: JsonObject,
        case: JsonObject,
        input: JsonObject,
        bodies: JsonArray,
        joints: JsonArray,
    ) {
        require(input.number("durationSeconds") == 10.0, "motion duration differs")
        if (case["id"]?.stringOrNull() == "motion-forces-60") {
            val body = bodies.getOrNull(0) as? JsonObject
            require(
                bodies.size == 1 && joints.isEmpty() && body != null &&
                    exact(settings["gravity"], ZERO_TWO) &&
                    exact(body["linearDamping"], input["damping"]) &&
                    exact(body["angularDamping"], input["damping"]) &&
                    exact(
                        (fixtureOf(body)["shape"] as JsonObject)["radius"],
                        JsonPrimitive(0.5),
                    ) &&
                    exact(input["force"], numbers(1.0, 0.0)) &&
                    exact(input["torque"], JsonPrimitive(0.25)),
                "force and damping input differs",
            )
        } else {
            require(
                bodies.size == 2 && joints.isEmpty() &&
                    exact(settings["gravity"], input.required("gravity")) &&
                    bodies.map {
                        (fixtureOf(it)["shape"] as JsonObject)["type"]
                    } == listOf(JsonPrimitive("Rectangle"), JsonPrimitive("Circle")) &&
                    bodies.all {
                        val fixture = fixtureOf(it)
                        exact(fixture["restitution"], input["restitution"]) &&
                            exact(fixture["restitutionVelocity"], JsonPrimitive(0.0))
                    },
                "restitution input differs",
            )
        }
    }

    private fun validateContacts(
        settings: JsonObject,
        case: JsonObject,
        bodies: JsonArray,
        joints: JsonArray,
    ) {
        require(
            bodies.size == 2 && joints.isEmpty() &&
                bodies.map { (fixtureOf(it)["shape"] as JsonObject)["type"] } ==
                listOf(JsonPrimitive("Rectangle"), JsonPrimitive("Rectangle")) &&
                bodies.map { (it as JsonObject)["massType"] } ==
                listOf(JsonPrimitive("INFINITE"), JsonPrimitive("NORMAL")) &&
                bodies.all { exact(fixtureOf(it)["friction"], JsonPrimitive(0.5)) } &&
                exact(settings["gravity"], NEGATIVE_GRAVITY) &&
                exact(
                    (dict(bodies[0], "")["transform"] as JsonObject)["getTranslation"],
                    numbers(0.0, -0.25),
                ) &&
                exact(
                    (dict(bodies[1], "")["transform"] as JsonObject)["getTranslation"],
                    numbers(0.0, 0.51),
                ),
            "sleep/wake input differs",
        )
        if (case["profile"]?.stringOrNull() == "configured") {
            require(
                exact(settings["linearTolerance"], JsonPrimitive(1.0 / 4096.0)) &&
                    settings["positionIterations"]?.intOrNull() == 8 &&
                    case["outer_group"]?.intOrNull() in setOf(1, 2, 4),
                "configured quality input differs",
            )
        }
    }

    private fun validateCcd(
        settings: JsonObject,
        input: JsonObject,
        bodies: JsonArray,
        joints: JsonArray,
    ) {
        val speed = input.number("speed")
        val body = bodies.getOrNull(1) as? JsonObject
        require(
            bodies.size == 2 && joints.isEmpty() && body != null &&
                body["bullet"].isTrue() &&
                exact(body["initialVelocity"], numbers(0.0, speed)) &&
                settings["continuousDetectionMode"] == input["mode"] &&
                exact(settings["gravity"], ZERO_TWO) &&
                exact(
                    (body["transform"] as JsonObject)["getTranslation"],
                    numbers(0.0, 1.0),
                ) &&
                (fixtureOf(body)["shape"] as JsonObject)["type"].stringOrNull() ==
                (if (input["shape"]?.stringOrNull() == "circle") "Circle" else "Polygon"),
            "CCD input differs",
        )
    }

    private fun validateLongRun(
        settings: JsonObject,
        input: JsonObject,
        bodies: JsonArray,
        joints: JsonArray,
    ) {
        val body = bodies.getOrNull(0) as? JsonObject
        require(
            bodies.size == 1 && joints.isEmpty() && body != null &&
                exact(body["initialVelocity"], input.required("velocity")) &&
                exact(body["initialAngularVelocity"], input["angularVelocity"]) &&
                exact(settings["gravity"], ZERO_TWO) &&
                settings["atRestDetectionEnabled"].isFalse(),
            "long-run input differs",
        )
    }

    private fun validateJoints(
        settings: JsonObject,
        case: JsonObject,
        input: JsonObject,
        bodies: JsonArray,
        joints: JsonArray,
    ) {
        require(joints.size == 1, "joint type or mode is absent")
        val joint = joints[0] as JsonObject
        val mode = joint["mode"] as JsonObject
        require(mode["type"] == input["jointType"], "joint type or mode is absent")
        val id = case["id"]?.stringOrNull().orEmpty()
        val jointType = input["jointType"]?.stringOrNull()
        when {
            id.startsWith("joint-") -> validateIndependentJoint(
                settings,
                input,
                bodies,
                joint,
                mode,
                jointType,
            )
            id == "P-J-Angle-ratio-limits-off--1.0" -> require(
                bodies.size == 2 && mode["limitsEnabled"].isFalse() &&
                    exact(mode["ratio"], JsonPrimitive(-1.0)) &&
                    exact(
                        (bodies[1] as JsonObject)["initialAngularVelocity"],
                        JsonPrimitive(-Math.PI / 6),
                    ),
                "baseline Angle failure input differs",
            )
            id == "P-JINT-Weld-enabled-equal" -> require(
                exact(settings["gravity"], NEGATIVE_GRAVITY) &&
                    mode["limitsEnabled"].isTrue() &&
                    exact(
                        JsonArray(listOf(mode["lowerLimit"] ?: JsonNull, mode["upperLimit"] ?: JsonNull)),
                        input["limits"],
                    ) &&
                    mode["springEnabled"].isTrue() &&
                    mode["springDamperEnabled"].isTrue() &&
                    exact(mode["springDampingRatio"], JsonPrimitive(0.3)),
                "frozen weld mode differs",
            )
            else -> {
                val segment = input["segment"]?.stringOrNull()
                val source = (bodies.getOrNull(2) as? JsonObject)?.get("initialVelocity")
                require(
                    exact(settings["gravity"], NEGATIVE_GRAVITY) &&
                        bodies.size == 3 &&
                        joint["bodies"] == JsonArray(listOf(JsonPrimitive(1), JsonPrimitive(2))) &&
                        (
                            if (segment != "main") {
                                exact(source, input["sourceVelocity"])
                            } else {
                                val velocity = source as? JsonArray
                                velocity != null && velocity.size == 2 &&
                                    velocity.all {
                                        it.isNumber() && it.numberOrNull()?.isFinite() == true
                                    }
                            }
                            ),
                    "frozen pulley input differs",
                )
            }
        }
    }

    private fun validateIndependentJoint(
        settings: JsonObject,
        input: JsonObject,
        bodies: JsonArray,
        joint: JsonObject,
        mode: JsonObject,
        jointType: String?,
    ) {
        val declaredBodies = joint["bodies"]
        require(
            bodies.size == 2 &&
                (declaredBodies == JsonArray(listOf(JsonPrimitive(0), JsonPrimitive(1))) ||
                    declaredBodies == JsonArray(listOf(JsonPrimitive(1)))) &&
                exact(settings["gravity"], ZERO_TWO),
            "joint body input differs",
        )
        if (input.containsKey("field")) {
            val field = input.required("field").stringOrNull().orEmpty()
            val value = input.required("initialValue")
            val captured =
                if (field == "LimitsEnabled" &&
                    jointType in setOf("Distance", "Prismatic", "Wheel")
                ) {
                    JsonArray(
                        listOf(
                            mode["lowerLimitEnabled"] ?: JsonNull,
                            mode["upperLimitEnabled"] ?: JsonNull,
                        ),
                    )
                } else {
                    mode[field.replaceFirstChar { it.lowercaseChar() }] ?: JsonNull
                }
            require(
                exact(
                    captured,
                    if (captured is JsonArray) JsonArray(listOf(value, value)) else value,
                ),
                "joint mode input differs",
            )
            return
        }
        if (input.containsKey("limits")) {
            val enabled =
                if (jointType in setOf("Distance", "Prismatic", "Wheel")) {
                    JsonArray(
                        listOf(
                            mode["lowerLimitEnabled"] ?: JsonNull,
                            mode["upperLimitEnabled"] ?: JsonNull,
                        ),
                    )
                } else {
                    mode["limitsEnabled"] ?: JsonNull
                }
            require(
                exact(
                    enabled,
                    if (enabled is JsonArray) {
                        JsonArray(listOf(JsonPrimitive(true), JsonPrimitive(true)))
                    } else {
                        JsonPrimitive(true)
                    },
                ) &&
                    exact(mode["lowerLimit"], input["lowerLimit"]) &&
                    exact(mode["upperLimit"], input["upperLimit"]),
                "joint limit input differs",
            )
            return
        }
        val active = input["mode"]?.stringOrNull() == "active"
        val flag = mapOf(
            "Distance" to "springEnabled",
            "Prismatic" to "motorEnabled",
            "Pulley" to "slackEnabled",
            "Revolute" to "motorEnabled",
            "Weld" to "springEnabled",
            "Wheel" to "motorEnabled",
        )[jointType]
        if (flag != null) {
            require(
                mode[flag].isBoolean() && mode[flag]?.booleanOrNull() == active,
                "joint active mode differs",
            )
        }
        if (jointType == "Angle") {
            val limit = if (active) Math.PI / 6 else 0.0
            require(
                mode["limitsEnabled"].isTrue() &&
                    exact(mode["lowerLimit"], JsonPrimitive(if (active) -limit else 0.0)) &&
                    exact(mode["upperLimit"], JsonPrimitive(limit)),
                "angle joint mode differs",
            )
        }
        if (jointType == "Pin") {
            require(
                mode["springEnabled"].isTrue() &&
                    exact(mode["maximumSpringForce"], JsonPrimitive(if (active) 10.0 else 1000.0)),
                "pin joint mode differs",
            )
        }
        if (jointType == "Friction") {
            require(
                exact(mode["maximumForce"], JsonPrimitive(if (active) 20.0 else 10.0)) &&
                    exact(mode["maximumTorque"], JsonPrimitive(if (active) 0.5 else 0.25)),
                "friction joint mode differs",
            )
        }
        if (jointType == "Motor") {
            require(
                exact(mode["maximumForce"], JsonPrimitive(if (active) 10.0 else 1000.0)),
                "motor joint mode differs",
            )
        }
    }

    /** `receipt.validate_state`. */
    fun validateState(state: JsonElement?, bodyIds: List<String>, jointIds: List<String>) {
        val value = state as? JsonObject
        if (value == null || value["bodies"] !is JsonArray || value["joints"] !is JsonArray) {
            throw Rejected("state body or joint channel is absent")
        }
        val bodies = value["bodies"] as JsonArray
        val joints = value["joints"] as JsonArray
        require(
            bodies.all { it is JsonObject } && joints.all { it is JsonObject },
            "state body or joint channel is malformed",
        )
        require(
            bodies.map { (it as JsonObject)["id"]?.stringOrNull() } == bodyIds &&
                joints.map { (it as JsonObject)["id"]?.stringOrNull() } == jointIds,
            "state body or joint identity differs",
        )
        for (bodyElement in bodies) {
            val body = bodyElement as JsonObject
            require(body.keys.containsAll(REQUIRED_STATE_BODY), "state body channel is absent")
            for (name in listOf("transform", "previousTransform")) {
                val transform = body[name] as? JsonObject
                if (transform == null || !transform.keys.containsAll(REQUIRED_TRANSFORM)) {
                    throw Rejected("state transform channel is absent")
                }
                require(
                    exact(
                        transform["getTranslation"],
                        JsonArray(
                            listOf(
                                transform["getTranslationX"] ?: JsonNull,
                                transform["getTranslationY"] ?: JsonNull,
                            ),
                        ),
                    ),
                    "state transform aliases differ",
                )
            }
        }
        for (jointElement in joints) {
            val joint = jointElement as JsonObject
            require(
                setOf("reactionForce", "reactionTorque", "mode").all { joint.containsKey(it) },
                "state joint channel is absent",
            )
        }
    }

    /**
     * `receipt.inspect`: validates one recorded trace against the declared cases and returns the
     * coverage summary.
     */
    fun inspect(
        lines: List<String>,
        cases: List<JsonObject>,
        allowTaggedNonfinite: Boolean = false,
    ): JsonObject {
        val rows = records(lines, allowTaggedNonfinite)
        val expected = LinkedHashMap<String, JsonObject>()
        for (case in cases) {
            expected[case.getValue("id").stringOrNull().orEmpty()] = case
        }
        if (expected.isEmpty() || expected.size != cases.size) {
            throw Rejected("empty or duplicate case declaration")
        }
        val seen = LinkedHashSet<String>()
        var current: String? = null
        var nextStep = 1
        var lastOrder = -1.0
        var eventCount = 0
        var stateCount = 0
        var totalEvents = 0
        var totalStates = 0
        var totalEndpoints = 0
        var endpoints = 0
        val endpointSteps = HashSet<Long>()
        var activeStep = 0.0
        var lastState: JsonElement? = null
        var lastFrozenState: JsonElement? = null
        var stepCallbackCount = 0
        val actionSteps = ArrayList<Long>()
        val instrumentedSteps = ArrayList<Long>()
        var frozenId: String? = null
        var bodyIds = emptyList<String>()
        var jointIds = emptyList<String>()
        val knownNonfinite = sortedSetOf<String>()
        for (row in rows) {
            val kind = row["kind"]?.stringOrNull()
            val caseId = row["id"]?.stringOrNull()
            if (tagged(row)) {
                if (caseId != "P-J-Angle-ratio-limits-off--1.0" || kind != "state") {
                    throw Rejected("unexpected nonfinite case: $caseId")
                }
                knownNonfinite.add(caseId)
            }
            when (kind) {
                "inputs" -> {
                    if (current != null || !expected.containsKey(caseId) || seen.contains(caseId)) {
                        throw Rejected("unexpected, duplicate, or interleaved case")
                    }
                    val case = expected.getValue(caseId!!)
                    for (field in listOf("family", "profile", "hz", "steps")) {
                        if (!exact(row[field], case[field])) {
                            throw Rejected("$caseId: $field differs")
                        }
                    }
                    if (case.containsKey("input") && !exact(row["input"], case["input"])) {
                        throw Rejected("$caseId: input differs")
                    }
                    if (case.containsKey("start_step") &&
                        !exact(row["startStep"], case["start_step"])
                    ) {
                        throw Rejected("$caseId: start step differs")
                    }
                    if (!exact(row["dt"], JsonPrimitive(1.0 / case.number("hz")))) {
                        throw Rejected("$caseId: dt differs")
                    }
                    if (case["require_setup"].isTrue()) {
                        validateSetup(row, case)
                        val setup = row.getValue("setup") as JsonObject
                        bodyIds = (setup.getValue("bodies") as JsonArray)
                            .map { (it as JsonObject).getValue("id").stringOrNull().orEmpty() }
                        jointIds = (setup.getValue("joints") as JsonArray)
                            .map { (it as JsonObject).getValue("id").stringOrNull().orEmpty() }
                        validateState(row["initial"], bodyIds, jointIds)
                    }
                    if (case["require_frozen_projection"].isTrue()) {
                        val frozen = row["frozenConfiguration"] as? JsonObject
                        if (frozen == null || listOf("settings", "world", "state").any {
                                frozen[it] !is JsonObject
                            }
                        ) {
                            throw Rejected("$caseId: frozen input projection is absent")
                        }
                        val frozenInput = row["frozenInput"] as? JsonObject
                        val envelopeOk = frozenInput != null &&
                            frozenInput["kind"]?.stringOrNull() == "inputs" &&
                            exact(frozenInput["dt"], row["dt"]) &&
                            exact(frozenInput["steps"], row["steps"]) &&
                            listOf("settings", "world", "state").all {
                                exact(frozenInput[it], frozen[it])
                            }
                        if (!envelopeOk) {
                            throw Rejected("$caseId: frozen input envelope is absent or inconsistent")
                        }
                        for ((field, expectedValue) in listOf(
                            "id" to case["frozen_id"],
                            "origin" to case["frozen_origin"],
                            "scale" to case["frozen_scale"],
                        )) {
                            if (expectedValue != null) {
                                require(
                                    exact(frozenInput!![field], expectedValue),
                                    "$caseId: frozen input $field differs",
                                )
                            }
                        }
                        require(
                            exact(frozenInput!!["grouping"], case["frozen_grouping"]),
                            "$caseId: frozen input grouping differs",
                        )
                        frozenId = frozenInput["id"]?.stringOrNull()
                    }
                    current = caseId
                    nextStep = (case["start_step"]?.intOrNull() ?: 0) + 1
                    lastOrder = -1.0
                    eventCount = 0
                    stateCount = 0
                    endpoints = 0
                    endpointSteps.clear()
                    activeStep = 0.0
                    lastState = null
                    lastFrozenState = null
                    stepCallbackCount = 0
                    actionSteps.clear()
                    instrumentedSteps.clear()
                }
                "event", "action", "instrumented-callback", "state" -> {
                    if (current != caseId) throw Rejected("record is outside its case")
                    val step = row["step"]
                    val order = row["order"]
                    val stepNumber = step?.numberOrNull()
                    if (stepNumber != activeStep) {
                        activeStep = stepNumber ?: Double.NaN
                        lastOrder = -1.0
                        stepCallbackCount = 0
                    }
                    val declared = expected.getValue(current!!)
                    val startStep = declared["start_step"]?.intOrNull() ?: 0
                    val maxStep = startStep + declared.number("steps")
                    val orderNumber = order?.numberOrNull() ?: Double.NEGATIVE_INFINITY
                    if (!step.isIntegerLiteral() || !order.isIntegerLiteral() ||
                        stepNumber == null || stepNumber != nextStep.toDouble() ||
                        stepNumber > maxStep || orderNumber <= lastOrder
                    ) {
                        throw Rejected("$caseId: missing step or changed event order")
                    }
                    lastOrder = orderNumber
                    val stepValue = stepNumber.toLong()
                    if (kind == "state") {
                        if (stateCount.toLong() != stepValue - startStep - 1 ||
                            !row.containsKey("state")
                        ) {
                            throw Rejected("$caseId: missing or duplicate state")
                        }
                        if (declared["require_setup"].isTrue()) {
                            validateState(row["state"], bodyIds, jointIds)
                        }
                        if (declared["require_frozen_projection"].isTrue()) {
                            val frozen = row["frozenState"] as? JsonObject
                            if (frozen == null || frozen["bodies"] !is JsonArray ||
                                frozen["joints"] !is JsonArray
                            ) {
                                throw Rejected("$caseId: frozen step projection is absent")
                            }
                            if (declared["require_setup"].isTrue()) {
                                require(
                                    (frozen["bodies"] as JsonArray).map {
                                        (it as JsonObject)["id"]?.stringOrNull()
                                    } == bodyIds &&
                                        (frozen["joints"] as JsonArray).map {
                                            (it as JsonObject)["id"]?.stringOrNull()
                                        } == jointIds,
                                    "$caseId: frozen step identity differs",
                                )
                            }
                        }
                        if (stepCallbackCount < (declared["min_step_events"]?.intOrNull() ?: 0)) {
                            throw Rejected("$caseId: step $stepValue has too few callbacks")
                        }
                        stateCount += 1
                        totalStates += 1
                        lastState = row["state"]
                        lastFrozenState = row["frozenState"]
                        nextStep += 1
                    } else {
                        eventCount += 1
                        totalEvents += 1
                        if (kind == "event") stepCallbackCount += 1
                        if (kind == "action") {
                            if (declared["require_frozen_projection"].isTrue()) {
                                val frozenActions = row["frozenRecords"] as? JsonArray
                                val firstOrder =
                                    (frozenActions?.getOrNull(0) as? JsonObject)
                                        ?.get("order")?.intOrNull()
                                require(
                                    frozenActions != null && frozenActions.isNotEmpty() &&
                                        frozenActions.all {
                                            val action = it as? JsonObject
                                            action != null &&
                                                action["kind"]?.stringOrNull() == "action" &&
                                                action["id"]?.stringOrNull() == frozenId &&
                                                exact(action["step"], step) &&
                                                action["order"].isIntegerLiteral()
                                        } &&
                                        firstOrder != null &&
                                        frozenActions.map {
                                            (it as JsonObject)["order"]?.intOrNull()
                                        } == (firstOrder until firstOrder + frozenActions.size).toList(),
                                    "$caseId: frozen action projection is absent or unordered",
                                )
                            }
                            actionSteps.add(stepNumber.toLong())
                        }
                        if (kind == "instrumented-callback") {
                            val frozenRecord = row["frozenRecord"] as? JsonObject
                            require(
                                frozenRecord != null &&
                                    frozenRecord["kind"]?.stringOrNull() == kind &&
                                    frozenRecord["id"]?.stringOrNull() == frozenId &&
                                    exact(frozenRecord["event"], row["event"]) &&
                                    exact(frozenRecord["step"], step) &&
                                    exact(frozenRecord["order"], order) &&
                                    exact(frozenRecord["values"], row["values"]),
                                "$caseId: instrumented callback projection differs",
                            )
                            instrumentedSteps.add(stepNumber.toLong())
                        }
                    }
                }
                "endpoint" -> {
                    val group = current?.let { expected.getValue(it)["outer_group"]?.intOrNull() }
                    val rowStepNumber = row["step"]?.numberOrNull()
                    val rowStep = rowStepNumber?.toLong() ?: -1L
                    val rowOrder = row["order"]?.numberOrNull() ?: Double.NEGATIVE_INFINITY
                    if (current != caseId || group == null || group == 0 ||
                        rowStepNumber == null || rowStepNumber != (nextStep - 1).toDouble() ||
                        rowStep % group.toLong() != 0L ||
                        !row["order"].isIntegerLiteral() ||
                        rowOrder <= lastOrder ||
                        rowStep in endpointSteps ||
                        !exact(row["state"], lastState)
                    ) {
                        throw Rejected("$caseId: invalid endpoint copy")
                    }
                    val declared = expected.getValue(current)
                    if (declared["require_frozen_projection"].isTrue()) {
                        require(
                            exact(row["frozenState"], lastFrozenState),
                            "$caseId: frozen endpoint copy differs",
                        )
                    }
                    lastOrder = rowOrder
                    endpointSteps.add(rowStep)
                    endpoints += 1
                    totalEndpoints += 1
                }
                "case-end" -> {
                    val declaredId = current
                    if (declaredId == null || declaredId != caseId) {
                        throw Rejected("$caseId: incomplete case")
                    }
                    val declared = expected.getValue(declaredId)
                    if (stateCount != declared.getValue("steps").intOrNull()) {
                        throw Rejected("$caseId: incomplete case")
                    }
                    if (!exact(row["steps"], JsonPrimitive(stateCount)) ||
                        !exact(row["events"], JsonPrimitive(eventCount))
                    ) {
                        throw Rejected("$caseId: case-end counts differ")
                    }
                    val steps = declared.getValue("steps").intOrNull()!!
                    val outerGroup = declared["outer_group"]?.intOrNull()
                    if (endpoints != steps / (outerGroup ?: (steps + 1))) {
                        throw Rejected("$caseId: endpoint count differs")
                    }
                    if (outerGroup != null &&
                        endpointSteps != (1..steps / outerGroup).map {
                            (it.toLong() * outerGroup)
                        }.toSet()
                    ) {
                        throw Rejected("$caseId: endpoint schedule differs")
                    }
                    if (outerGroup != null && row["endpoints"]?.intOrNull() != endpoints) {
                        throw Rejected("$caseId: case-end endpoint count differs")
                    }
                    val expectedActions =
                        (declared["expected_actions"] as? JsonArray ?: JsonArray(emptyList()))
                            .map { it.intOrNull()?.toLong() }
                    if (actionSteps != expectedActions) {
                        throw Rejected("$caseId: action steps differ")
                    }
                    val expectedCallbacks =
                        (declared["expected_instrumented_callbacks"] as? JsonArray
                            ?: JsonArray(emptyList())).map { it.intOrNull()?.toLong() }
                    if (instrumentedSteps != expectedCallbacks) {
                        throw Rejected("$caseId: instrumented callback steps differ")
                    }
                    seen.add(declaredId)
                    current = null
                }
                else -> throw Rejected("unknown record kind: $kind")
            }
        }
        if (current != null || seen != expected.keys || totalStates == 0) {
            val missing = (expected.keys - seen).sorted()
            throw Rejected("missing cases: [${missing.joinToString(", ") { "'$it'" }}]")
        }
        return buildJsonObject {
            put("expected_cases", expected.size)
            put("executed_cases", seen.size)
            put("states", totalStates)
            put("events", totalEvents)
            put("endpoints", totalEndpoints)
            put("skipped", 0)
            put(
                "known_nonfinite_cases",
                buildJsonArray { knownNonfinite.forEach { add(JsonPrimitive(it)) } },
            )
        }
    }

    /** `receipt.compare_exact`. */
    fun compareExact(
        reference: List<String>,
        candidate: List<String>,
        cases: List<JsonObject>,
    ): JsonObject {
        inspect(reference, cases)
        inspect(candidate, cases)
        val left = records(reference)
        val right = records(candidate)
        var number = 0
        val longest = maxOf(left.size, right.size)
        for (index in 1..longest) {
            if (index > left.size || index > right.size) {
                throw Rejected("record count differs")
            }
            number = index
            if (!exact(left[index - 1], right[index - 1])) {
                throw Rejected("record $number differs")
            }
        }
        return buildJsonObject {
            put("status", "PASSED")
            put("records", number)
        }
    }

    /** `receipt.seal`. */
    fun seal(
        lines: List<String>,
        cases: List<JsonObject>,
        identity: Identity,
        artifactPaths: Map<String, String>,
        artifactSha256: Map<String, String>,
        catalog: FixtureCatalog,
        catalogSha256: String,
        buildConfigSha256: String,
        traceSha256: String,
    ): JsonObject {
        val counts = inspect(lines, cases, allowTaggedNonfinite = true)
        if (artifactPaths.keys != identity.artifactSha256.keys) {
            throw Rejected("artifact set differs")
        }
        for (name in artifactPaths.keys) {
            if (artifactSha256[name] != identity.artifactSha256[name]) {
                throw Rejected("stale artifact: $name")
            }
        }
        val expectedCounts = buildJsonObject {
            put("cases", cases.size)
            put("states", cases.sumOf { it.getValue("steps").intOrNull() ?: 0 })
            put(
                "endpoints",
                cases.filter { it.containsKey("outer_group") }.sumOf {
                    (it.getValue("steps").intOrNull() ?: 0) /
                        (it.getValue("outer_group").intOrNull() ?: 0)
                },
            )
            put("actions", cases.sumOf { (it["expected_actions"] as? JsonArray)?.size ?: 0 })
        }
        return buildJsonObject {
            put("schema", "portable-numerical-receipt/1")
            put("candidate_commit", identity.candidateCommit)
            put("source_sha256", identity.sourceSha256)
            put(
                "artifact_sha256",
                buildJsonObject {
                    identity.artifactSha256.forEach { (name, hash) -> put(name, hash) }
                },
            )
            put("runtime", identity.runtime)
            put("fixture_key", "portable-matrix/1")
            put("source_hash_method", "SHA-256 of git archive --format=tar HEAD")
            put("baseline_source_revision", "058bf6d982a0fb89b54050f929f6ea9dae53b714")
            put(
                "baseline_jar_sha256",
                "204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e",
            )
            put("reference_source_revision", catalog.baselineSourceRevision)
            put("reference_artifact_sha256", catalog.baselineJarSha256)
            put(
                "reference_trace_sha256",
                buildJsonObject {
                    catalog.referenceGzipSha256.forEach { (key, hash) -> put(key, hash) }
                },
            )
            put("frozen_catalog_sha256", catalogSha256)
            put("build_config_sha256", buildConfigSha256)
            put("trace_sha256", traceSha256)
            put("cases_sha256", Sha256.of(CanonicalJson.render(JsonArray(cases))))
            put("counts", counts)
            put("expected_counts", expectedCounts)
            put("executed_counts", counts)
            put("skipped", 0)
            put(
                "artifact_paths",
                buildJsonObject {
                    artifactPaths.forEach { (name, path) -> put(name, path) }
                },
            )
        }
    }

    /** `receipt.verify`. */
    fun verify(
        sealed: JsonElement,
        lines: List<String>,
        cases: List<JsonObject>,
        identity: Identity,
        artifactPaths: Map<String, String>,
        artifactSha256: Map<String, String>,
        catalog: FixtureCatalog,
        catalogSha256: String,
        buildConfigSha256: String,
        traceSha256: String,
    ): JsonObject {
        val fresh = seal(
            lines,
            cases,
            identity,
            artifactPaths,
            artifactSha256,
            catalog,
            catalogSha256,
            buildConfigSha256,
            traceSha256,
        )
        if (!exact(sealed, fresh)) {
            throw Rejected("receipt identity or counts differ")
        }
        return buildJsonObject {
            put("status", "PASSED")
            put("counts", fresh.getValue("counts"))
        }
    }
}
