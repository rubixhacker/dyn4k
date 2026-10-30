package io.github.rubixhacker.harness.numerical

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlin.math.abs
import kotlin.math.atan2
import kotlin.math.sqrt

/**
 * `orthogonality`: the closed-form rotation error bound and the rotation-audit validator.
 *
 * The bound is exact rational arithmetic over `fractions.Fraction`, so it needs the
 * arbitrary-precision integers in `ExactNumbers`. `math.factorial(201)` in the Python trig
 * enclosure overflows a double for every nonzero angle, so `trigAgrees` throws
 * [PythonOverflow] exactly where the reference does.
 */
object Orthogonality {
    private val SCALE = BigNat.powerOfTen(100)
    private val U = Fraction.ofRatio(BigNat.ONE, BigNat.powerOfTwo(53))
    private val Q = Fraction.ofRatio(BigNat.ofInt(2), BigNat.powerOfTwo(53))
    private val GAMMA3: Fraction = run {
        val threeU = U * Fraction.of(3)
        threeU / (Fraction.of(1) - threeU)
    }
    private val ONE = Fraction.of(1)
    private val TWO_TO_THE_MINUS_1022 = Fraction.ofRatio(BigNat.ONE, BigNat.powerOfTwo(1022))

    /** `float(_Q)`, which is exactly 2^-52. */
    private val Q_VALUE: Double = 1.0 / (1L shl 52).toDouble()

    private val JOINT_CAPS = mapOf(
        "Angle" to 7, "Distance" to 7, "Friction" to 5,
        "Motor" to 5, "Pin" to 5, "Prismatic" to 7,
        "Pulley" to 7, "Revolute" to 9, "Weld" to 11, "Wheel" to 9,
    )

    fun sourceRotationCap(case: JsonObject): Int = when (case["family"]?.stringOrNull()) {
        "geometry-collision", "ccd" -> 5
        "free-motion" -> if (case["id"]?.stringOrNull() == "motion-forces-60") 1 else 5
        "joints-limits-motors" -> {
            val jointType = (case["input"] as JsonObject)["jointType"]?.stringOrNull()
            JOINT_CAPS[jointType] ?: throw IllegalArgumentException(
                "unknown prospective rotation source: ${case["id"]?.stringOrNull()}",
            )
        }
        else -> throw IllegalArgumentException(
            "unknown prospective rotation source: ${case["id"]?.stringOrNull()}",
        )
    }

    private fun sqrtBounds(value: Fraction): Pair<Fraction, Fraction> {
        val numerator = value.numerator.magnitude.times(SCALE).times(SCALE)
        val denominator = value.denominator
        val floor = numerator.divMod(denominator).first.isqrt()
        val lower = Fraction.ofRatio(floor, SCALE)
        val upper = if (floor.times(floor).times(denominator) == numerator) {
            lower
        } else {
            Fraction.ofRatio(floor.plus(BigNat.ONE), SCALE)
        }
        return lower to upper
    }

    private fun limitAt(rotations: Int): BigNat = LIMITS[rotations]

    private val LIMITS: List<BigNat> by lazy(LazyThreadSafetyMode.SYNCHRONIZED) { computeLimits() }

    fun orthogonalityUlps(rotations: Int): Long {
        if (rotations < 0 || rotations > 6600) {
            throw IllegalArgumentException("rotation cap is outside the approved domain")
        }
        return limitAt(rotations).toLong()
    }

    private fun computeLimits(): List<BigNat> {
        val sqrt2Upper = sqrtBounds(Fraction.of(2)).second
        val deltaUpper = (sqrt2Upper * U) * Fraction.of(4) + (U * U) * Fraction.of(8)
        val aUpper = sqrtBounds(ONE + deltaUpper).second * (ONE + sqrt2Upper * GAMMA3)
        val bLower = sqrtBounds(ONE - deltaUpper).first * (ONE - sqrt2Upper * GAMMA3)
        val aScaled = (aUpper * Fraction.ofRatio(SCALE, BigNat.ONE)).ceil().magnitude
        val bScaled = bLower.numerator.magnitude.times(SCALE).divMod(bLower.denominator).first
        val squaredScale = SCALE.times(SCALE)
        var upperPower = SCALE
        var lowerPower = SCALE
        val limits = ArrayList<BigNat>(6601)
        repeat(6601) {
            val positive = (ONE + GAMMA3) * Fraction.ofRatio(upperPower, SCALE) - ONE
            val negative = ONE - (ONE - GAMMA3) * Fraction.ofRatio(lowerPower, SCALE)
            val largest = if (positive >= negative) positive else negative
            limits.add((largest / Q).ceil().magnitude)
            upperPower = upperPower.times(aScaled).times(aScaled)
                .plus(squaredScale).minus(BigNat.ONE).divByPowerOfTen(200)
            lowerPower = lowerPower.times(bScaled).times(bScaled).divByPowerOfTen(200)
        }
        return limits
    }

    val directResetUlps: Long by lazy(LazyThreadSafetyMode.SYNCHRONIZED) {
        val deltaUpper = (sqrtBounds(Fraction.of(2)).second * U) * Fraction.of(4) +
            (U * U) * Fraction.of(8)
        val positive = (ONE + GAMMA3) * (ONE + deltaUpper) - ONE
        val negative = ONE - (ONE - GAMMA3) * (ONE - deltaUpper)
        val largest = if (positive >= negative) positive else negative
        (largest / Q).ceil().magnitude.toLong()
    }

    private val BINARY64 = Regex("[0-9a-f]{16}")
    private val LOADER = Regex("(?:bootstrap|system|L[1-9][0-9]*)")

    private fun binary64(bits: String?): Double {
        if (bits == null || BINARY64.matches(bits).not()) {
            throw Rejected("rotation audit has invalid binary64 bits")
        }
        val value = Double.fromBits(bits.toULong(16).toLong())
        if (!value.isFinite()) throw Rejected("rotation audit has a nonfinite value")
        return value
    }

    private fun pair(bits: JsonElement?): Pair<Double, Double> {
        val array = bits as? JsonArray
        if (array == null || array.size != 2) {
            throw Rejected("rotation audit pair is incomplete")
        }
        return binary64(array[0].stringOrNull()) to binary64(array[1].stringOrNull())
    }

    private fun statePair(transform: JsonObject): Pair<String, String> {
        val values = listOf(transform["getCost"], transform["getSint"])
        if (values.any { !it.isNumber() }) {
            throw Rejected("rotation audit state has an invalid number")
        }
        val doubles = values.map { it.numberOrNull()!! }
        if (doubles.any { !it.isFinite() }) {
            throw Rejected("rotation audit state is nonfinite")
        }
        return bits(doubles[0]) to bits(doubles[1])
    }

    fun bits(value: Double): String = value.toRawBits().toULong().toString(16).padStart(16, '0')

    /** `math.ulp`, shared with the comparison engine. */
    fun ulpValue(value: Double): Double = ulp(value)

    /** `math.ulp`. */
    private fun ulp(value: Double): Double {
        val magnitude = abs(value)
        if (magnitude == 0.0) return Double.MIN_VALUE
        if (magnitude.isInfinite()) return Double.POSITIVE_INFINITY
        return Double.fromBits(magnitude.toRawBits() + 1) - magnitude
    }

    private fun acos(value: Double): Double = atan2(sqrt(1.0 - value * value), value)

    private fun sourceAngle(pair: Pair<Double, Double>): Double {
        val (cosine, sine) = pair
        if (!(-1.0 <= cosine && cosine <= 1.0)) {
            throw Rejected("rotation audit source angle cosine differs")
        }
        val angle = acos(cosine)
        return if (sine >= 0.0) angle else -angle
    }

    private fun sourceAngleAgrees(recordedBits: String?, pair: Pair<Double, Double>): Boolean {
        val recorded = binary64(recordedBits)
        val expected = sourceAngle(pair)
        if (pair.second >= 0.0 && !(0.0 <= recorded && recorded <= Math.PI)) return false
        if (pair.second < 0.0 && !(-Math.PI <= recorded && recorded <= 0.0)) return false
        if (expected == 0.0) return recordedBits == bits(expected)
        val tolerance = 8 * ulp(maxOf(abs(recorded), abs(expected), 1.0))
        return abs(recorded - expected) <= tolerance
    }

    private fun trigAgrees(angle: Double, trig: Pair<Double, Double>): Boolean {
        if (angle == 0.0) {
            return bits(trig.first) == bits(1.0) && bits(trig.second) == bits(angle)
        }
        if (abs(angle) > 32.0) {
            throw Rejected("rotation audit trig enclosure domain is unavailable")
        }
        // `abs(x) ** 201 / math.factorial(201)` converts 201! to a double, which overflows for
        // every |x| > 0, so the Python reference raises OverflowError here.
        throw PythonOverflow("int too large to convert to float")
    }

    private fun validateRotate(
        call: JsonObject,
        pre: Pair<Double, Double>,
        trig: Pair<Double, Double>,
        post: Pair<Double, Double>,
    ) {
        val required = mutableSetOf(
            "sequence", "step", "body_id", "kind", "branch", "input_kind",
            "pre", "trig", "raw", "post", "clamp",
        )
        when (call["input_kind"]?.stringOrNull()) {
            "angle" -> required.add("angle_bits")
            "pair" -> required.add("rotation_input")
        }
        if (call.keys != required ||
            call["branch"]?.stringOrNull() !in setOf("integrate", "joint", "contact")
        ) {
            throw Rejected("rotation audit source branch differs")
        }
        if (call["input_kind"]?.stringOrNull() == "angle") {
            if (!trigAgrees(binary64(call["angle_bits"]?.stringOrNull()), trig)) {
                throw Rejected("rotation audit angle and trig pair differ")
            }
        } else if (call["rotation_input"] != call["trig"]) {
            throw Rejected("rotation audit pair input differs")
        }
        if (abs(trig.first * trig.first + trig.second * trig.second - 1.0) >
            directResetUlps.toDouble() * Q_VALUE
        ) {
            throw Rejected("rotation audit trig-pair norm differs")
        }
        val raw = pair(call["raw"])
        val rawText = call.getValue("raw") as JsonArray
        val clamp = call["clamp"] as? JsonArray
        if (clamp == null || clamp.size != 2 || clamp.any { !it.isBoolean() }) {
            throw Rejected("rotation audit clamp markers differ")
        }
        val postText = call.getValue("post") as JsonArray
        for (index in 0..1) {
            val a = Fraction.ofDouble(if (index == 0) pre.first else pre.second) *
                Fraction.ofDouble(trig.first)
            val b = Fraction.ofDouble(if (index == 0) pre.second else pre.first) *
                Fraction.ofDouble(trig.second)
            if (subnormal(a) || subnormal(b)) {
                throw Rejected("rotation audit subnormal product premise is unproved")
            }
            val ideal = if (index == 0) a - b else a + b
            if (subnormal(ideal)) {
                throw Rejected("rotation audit subnormal sum premise is unproved")
            }
            val observed = Fraction.ofDouble(if (index == 0) raw.first else raw.second)
            if ((observed - ideal).abs() > GAMMA3 * (a.abs() + b.abs())) {
                throw Rejected("rotation audit orientation rounding differs")
            }
            val first = if (index == 0) pre.first * trig.first else pre.second * trig.first
            val second = if (index == 0) pre.second * trig.second else pre.first * trig.second
            val sourceRaw = if (index == 0) first - second else first + second
            if ((sourceRaw == 0.0 || (if (index == 0) raw.first else raw.second) == 0.0) &&
                rawText[index] != JsonPrimitive(bits(sourceRaw))
            ) {
                throw Rejected("rotation audit signed zero raw differs")
            }
            val observedRaw = if (index == 0) raw.first else raw.second
            val wasClamped = observedRaw < -1.0 || observedRaw > 1.0
            val expectedBits = when {
                observedRaw < -1.0 -> bits(-1.0)
                observedRaw > 1.0 -> bits(1.0)
                else -> rawText[index].stringOrNull()
            }
            if (clamp[index].booleanOrNull() != wasClamped ||
                postText[index].stringOrNull() != expectedBits
            ) {
                throw Rejected("rotation audit clamp result differs")
            }
        }
    }

    private fun subnormal(value: Fraction): Boolean =
        !value.numerator.isZero() && value.abs() < TWO_TO_THE_MINUS_1022

    private fun validateReset(call: JsonObject, trig: Pair<Double, Double>, post: Pair<Double, Double>) {
        if (call.keys != setOf(
                "sequence", "step", "body_id", "kind", "branch", "pre", "trig",
                "post", "alpha_bits", "start_angle_bits", "end_angle_bits",
                "diff_bits", "angle_bits", "end_rotation",
            ) || call["branch"]?.stringOrNull() != "toi"
        ) {
            throw Rejected("rotation audit direct reset branch differs")
        }
        val alpha = binary64(call["alpha_bits"]?.stringOrNull())
        val start = binary64(call["start_angle_bits"]?.stringOrNull())
        val end = binary64(call["end_angle_bits"]?.stringOrNull())
        binary64(call["diff_bits"]?.stringOrNull())
        val angle = binary64(call["angle_bits"]?.stringOrNull())
        if (!(0.0 <= alpha && alpha <= 1.0)) {
            throw Rejected("rotation audit lerp alpha differs")
        }
        val endRotation = pair(call["end_rotation"])
        if (abs(
                endRotation.first * endRotation.first +
                    endRotation.second * endRotation.second - 1.0,
            ) > 32 * Q_VALUE
        ) {
            throw Rejected("rotation audit lerp end orientation differs")
        }
        if (!sourceAngleAgrees(call["start_angle_bits"]?.stringOrNull(), pair(call["pre"])) ||
            !sourceAngleAgrees(call["end_angle_bits"]?.stringOrNull(), endRotation)
        ) {
            throw Rejected("rotation audit lerp source angle differs")
        }
        var difference = end - start
        if (difference < -Math.PI) difference += 2.0 * Math.PI
        if (difference > Math.PI) difference -= 2.0 * Math.PI
        if (call["diff_bits"]?.stringOrNull() != bits(difference) ||
            call["angle_bits"]?.stringOrNull() != bits(difference * alpha + start)
        ) {
            throw Rejected("rotation audit lerp angle arithmetic differs")
        }
        if (!trigAgrees(angle, trig)) {
            throw Rejected("rotation audit lerp angle and trig pair differ")
        }
        if (call["post"] != call["trig"]) {
            throw Rejected("rotation audit direct trig reset differs")
        }
        if (abs(post.first * post.first + post.second * post.second - 1.0) >
            directResetUlps.toDouble() * Q_VALUE
        ) {
            throw Rejected("rotation audit direct trig norm differs")
        }
    }

    private fun bodyList(container: JsonObject, key: String): JsonArray =
        container[key] as? JsonArray ?: throw Rejected("rotation audit body inventory differs")

    fun validateRotationAudit(
        audit: JsonElement?,
        case: JsonObject,
        header: JsonObject,
        states: Map<Int, JsonObject>,
        rotationCap: Int,
    ) {
        val value = audit as? JsonObject
        val calls = value?.get("calls") as? JsonArray
        if (value == null || calls == null ||
            value.keys != setOf(
                "schema", "case_id", "operation_model_revision", "declared_calls",
                "accepted_toi_resets", "calls",
            ) ||
            value["schema"]?.stringOrNull() != "portable-rotation-audit/2" ||
            !exact(value["case_id"], case["id"]) ||
            value["operation_model_revision"]?.stringOrNull() !=
            "058bf6d982a0fb89b54050f929f6ea9dae53b714" ||
            !value["declared_calls"].isIntegerLiteral() ||
            calls.any { it !is JsonObject } ||
            value["declared_calls"]?.intOrNull() != calls.size
        ) {
            throw Rejected("rotation audit identity or call count differs")
        }
        val initial = bodyList(header.getValue("initial") as JsonObject, "bodies")
        val bodyIds = bodyList(header.getValue("setup") as JsonObject, "bodies")
            .map { (it as JsonObject)["id"]?.stringOrNull().orEmpty() }
        if (bodyIds.size != initial.size || bodyIds.size != bodyIds.toSet().size) {
            throw Rejected("rotation audit body inventory differs")
        }
        val steps = case.getValue("steps").intOrNull()!!
        val accepted = value["accepted_toi_resets"] as? JsonArray
        if (accepted == null || accepted.any {
                val item = it as? JsonArray
                item == null || item.size != 2 || !item[0].isIntegerLiteral() ||
                    (item[0].intOrNull() ?: 0) < 1 || (item[0].intOrNull() ?: 0) > steps ||
                    item[1].stringOrNull() !in bodyIds
            }
        ) {
            throw Rejected("rotation audit TOI branch declaration differs")
        }
        val chain = LinkedHashMap<String, Pair<String, String>>()
        for ((index, id) in bodyIds.withIndex()) {
            if (index >= initial.size) break
            chain[id] = statePair((initial[index] as JsonObject).getValue("transform") as JsonObject)
        }
        var position = 0
        val resets = ArrayList<Pair<Int, String>>()
        for (step in 1..steps) {
            val counts = LinkedHashMap<String, Int>()
            bodyIds.forEach { counts[it] = 0 }
            val state = states[step] ?: throw Rejected("rotation audit state inventory differs")
            val stateBodies = state["bodies"] as? JsonArray
                ?: throw Rejected("rotation audit state inventory differs")
            val byId = LinkedHashMap<String, JsonObject>()
            for (body in stateBodies) {
                val entry = body as? JsonObject
                    ?: throw Rejected("rotation audit state inventory differs")
                byId[entry["id"]?.stringOrNull().orEmpty()] = entry
            }
            if (byId.keys != chain.keys) {
                throw Rejected("rotation audit state inventory differs")
            }
            while (position < calls.size &&
                (calls[position] as JsonObject)["step"]?.intOrNull() == step
            ) {
                val call = calls[position] as JsonObject
                if (!call["sequence"].isIntegerLiteral() ||
                    call["sequence"]?.intOrNull() != position ||
                    !call["step"].isIntegerLiteral() ||
                    call["body_id"]?.stringOrNull() !in chain
                ) {
                    throw Rejected("rotation audit call sequence or input differs")
                }
                val bodyId = call["body_id"]?.stringOrNull()!!
                if (call["kind"]?.stringOrNull() == "lerp-reset") {
                    val previous = byId.getValue(bodyId)["previousTransform"] as? JsonObject
                        ?: throw Rejected("rotation audit lerp end origin or start differs")
                    val previousPair = statePair(previous)
                    if (call["pre"] != JsonArray(listOf(JsonPrimitive(previousPair.first), JsonPrimitive(previousPair.second))) ||
                        call["end_rotation"] != JsonArray(
                            chain.getValue(bodyId).toList().map { JsonPrimitive(it) },
                        )
                    ) {
                        throw Rejected("rotation audit lerp end origin or start differs")
                    }
                } else if (call["pre"] != JsonArray(
                        chain.getValue(bodyId).toList().map { JsonPrimitive(it) },
                    )
                ) {
                    throw Rejected("rotation audit call sequence or input differs")
                }
                val pre = pair(call["pre"])
                val trig = pair(call["trig"])
                val postDoubles = pair(call["post"])
                when (call["kind"]?.stringOrNull()) {
                    "rotate" -> {
                        counts[bodyId] = counts.getValue(bodyId) + 1
                        if (counts.getValue(bodyId) > rotationCap) {
                            throw Rejected("rotation audit source cap exceeded")
                        }
                        validateRotate(call, pre, trig, postDoubles)
                    }
                    "lerp-reset" -> {
                        resets.add(step to bodyId)
                        validateReset(call, trig, postDoubles)
                    }
                    else -> throw Rejected("rotation audit operation differs")
                }
                chain[bodyId] = postPair(call)
                position += 1
            }
            for (body in stateBodies) {
                val entry = body as JsonObject
                val id = entry["id"]?.stringOrNull().orEmpty()
                if (statePair(entry.getValue("transform") as JsonObject) != chain.getValue(id)) {
                    throw Rejected("rotation audit state chain differs")
                }
            }
        }
        val declared = accepted.map {
            val item = it as JsonArray
            (item[0].intOrNull() ?: 0) to item[1].stringOrNull().orEmpty()
        }
        if (position != calls.size || resets != declared) {
            throw Rejected("rotation audit call or TOI reset coverage differs")
        }
    }

    private fun postPair(call: JsonObject): Pair<String, String> {
        val array = call.getValue("post") as JsonArray
        return array[0].stringOrNull().orEmpty() to array[1].stringOrNull().orEmpty()
    }
}

/** `BigNat` to a `Long`, for the bound values that fit. */
internal fun BigNat.toLong(): Long {
    var value = 0L
    val text = toString()
    require(text.length <= 18) { "bound does not fit in a Long: $text" }
    for (character in text) value = value * 10 + (character - '0')
    return value
}
