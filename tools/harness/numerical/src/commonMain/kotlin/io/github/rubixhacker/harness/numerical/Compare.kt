package io.github.rubixhacker.harness.numerical

import io.github.rubixhacker.harness.contract.CanonicalJson
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.put

/**
 * Python's `str()` and `repr()` of the JSON scalars the numerical modules interpolate into
 * their messages and limits.
 */
object PyText {
    /** `str(value)`: `None`, `True`, `False`, the text of a string, or the number's repr. */
    fun of(value: JsonElement?): String = when {
        value == null || value is JsonNull -> "None"
        value is JsonPrimitive -> when {
            value.isBoolean() -> if (value.content == "true") "True" else "False"
            value.isString -> value.content
            value.isIntegerLiteral() -> value.content
            else -> CanonicalJson.pythonFloat(value.content.toDouble())
        }
        else -> value.toString()
    }

    /** `repr(value)` for the scalars that reach a message. */
    fun repr(value: JsonElement?): String = when {
        value == null || value is JsonNull -> "None"
        value is JsonPrimitive -> when {
            value.isBoolean() -> if (value.content == "true") "True" else "False"
            value.isString -> "'" + value.content + "'"
            value.isIntegerLiteral() -> value.content
            else -> CanonicalJson.pythonFloat(value.content.toDouble())
        }
        else -> value.toString()
    }

    /** `str(dict)` for a counter of record kinds, in first-encounter order. */
    fun dict(entries: List<Pair<String, Int>>): String =
        entries.joinToString(", ", "{", "}") { (key, count) -> "'$key': $count" }

    /** `Fraction(str(value))`: the exact rational the text denotes. */
    fun fraction(value: JsonElement?): Fraction {
        val text = of(value)
        return Fraction.ofDecimalString(text)
    }
}

/**
 * `compare.py`: the per-case comparison engine that the qualification gate verifiers call.
 *
 * The engine walks a reference and a candidate trace record by record and applies the
 * declaration's numeric rules, direction metrics, zero invariants and derived formulas. Every
 * limit is decided over exact rationals with certified enclosures, so a value that straddles a
 * limit fails closed rather than rounding into a pass.
 */
object Compare {
    /** One trace record: the raw line, which the input digest covers, and its object. */
    data class Record(val line: String, val row: JsonObject)

    private val DUPLICATE_GETTERS = listOf(
        "getTransform" to "transform",
        "getPreviousTransform" to "previousTransform",
        "getWorldCenter" to "worldCenter",
        "getLinearVelocity" to "velocity",
        "getAngularVelocity" to "angularVelocity",
        "getForce" to "force",
        "getTorque" to "torque",
        "getAccumulatedForce" to "accumulatedForce",
        "getAccumulatedTorque" to "accumulatedTorque",
    )

    private val U = Fraction.ofRatio(BigNat.ONE, BigNat.powerOfTwo(53))
    private val ROOT_SCALE = BigNat.powerOfTen(70)

    private fun require(condition: Boolean, message: String) {
        if (!condition) throw Rejected(message)
    }

    /** `compare.same_value`: numbers compare by their binary64 bits, so `-0.0` differs. */
    fun sameValue(left: JsonElement?, right: JsonElement?): Boolean {
        val a = left ?: JsonNull
        val b = right ?: JsonNull
        if (a.isNumber() && b.isNumber()) {
            val x = a.numberOrNull() ?: return false
            val y = b.numberOrNull() ?: return false
            return x.toRawBits() == y.toRawBits()
        }
        if (a is JsonArray && b is JsonArray) {
            return a.size == b.size && a.indices.all { sameValue(a[it], b[it]) }
        }
        if (a is JsonObject && b is JsonObject) {
            return a.keys == b.keys && a.keys.all { sameValue(a[it], b[it]) }
        }
        return a == b
    }

    /** `compare.same_run_alias`: numbers compare by value and must be finite. */
    fun sameRunAlias(left: JsonElement?, right: JsonElement?): Boolean {
        val a = left ?: JsonNull
        val b = right ?: JsonNull
        if (a.isNumber() || b.isNumber()) {
            if (!a.isNumber() || !b.isNumber()) return false
            val x = a.numberOrNull() ?: return false
            val y = b.numberOrNull() ?: return false
            return x.isFinite() && y.isFinite() && x == y
        }
        if (a is JsonArray || b is JsonArray) {
            if (a !is JsonArray || b !is JsonArray) return false
            return a.size == b.size && a.indices.all { sameRunAlias(a[it], b[it]) }
        }
        if (a is JsonObject || b is JsonObject) {
            if (a !is JsonObject || b !is JsonObject) return false
            return a.keys == b.keys && a.keys.all { sameRunAlias(a[it], b[it]) }
        }
        if (a is JsonNull || b is JsonNull) return a is JsonNull && b is JsonNull
        if (a.isBoolean() || b.isBoolean()) {
            return a.isBoolean() && b.isBoolean() && a.booleanOrNull() == b.booleanOrNull()
        }
        return a.stringOrNull() == b.stringOrNull() &&
            (a.stringOrNull() != null || a == b)
    }

    // ------------------------------------------------------------- snapshot aliases

    fun checkTranslationAliases(state: JsonObject) {
        val bodies = state["bodies"] as? JsonArray
            ?: throw Rejected("translation getter alias differs")
        for (element in bodies) {
            val body = element as? JsonObject ?: throw Rejected("translation getter alias differs")
            for (name in listOf("transform", "previousTransform")) {
                val transform = body[name] as? JsonObject ?: continue
                val translation = transform["getTranslation"] as? JsonArray
                    ?: throw Rejected("translation getter alias differs")
                if (translation.size != 2 ||
                    !sameRunAlias(transform["getTranslationX"], translation[0]) ||
                    !sameRunAlias(transform["getTranslationY"], translation[1])
                ) {
                    throw Rejected("translation getter alias differs")
                }
                if (transform.containsKey("getValues")) {
                    val values = transform["getValues"] as JsonArray
                    val sine = transform["getSint"] ?: JsonNull
                    val cosine = transform["getCost"] ?: JsonNull
                    if (values.size != 6 ||
                        !sameRunAlias(values[2], translation[0]) ||
                        !sameRunAlias(values[5], translation[1]) ||
                        !sameRunAlias(values[0], cosine) ||
                        !sameRunAlias(
                            values[1],
                            negate(sine),
                        ) ||
                        !sameRunAlias(values[3], sine) ||
                        !sameRunAlias(values[4], cosine)
                    ) {
                        throw Rejected("matrix getter alias differs")
                    }
                }
            }
            if (body.containsKey("fixedOriginPosition") &&
                !sameRunAlias(
                    body["fixedOriginPosition"],
                    (body["transform"] as? JsonObject)?.get("getTranslation"),
                )
            ) {
                throw Rejected("fixed origin position alias differs")
            }
            if (body.containsKey("worldCenter") &&
                !sameRunAlias(
                    body["worldCenter"],
                    (body["transform"] as? JsonObject)?.get("getTranslation"),
                )
            ) {
                throw Rejected("world center alias differs")
            }
        }
    }

    private fun negate(value: JsonElement): JsonElement {
        val number = value.numberOrNull() ?: return JsonNull
        return JsonPrimitive(-number)
    }

    /** `compare.orientation_change`: the change and the branch it took. */
    fun orientationChange(
        previousAngle: Double,
        currentAngle: Double,
        angularVelocity: Double,
    ): Pair<Double, Triple<Boolean, Boolean, String>> {
        if (previousAngle == currentAngle) return 0.0 to Triple(false, false, "same-angle")
        var previous = previousAngle
        var current = currentAngle
        val previousNegative = previous < 0
        val currentNegative = current < 0
        if (previousNegative) previous += 2 * Math.PI
        if (currentNegative) current += 2 * Math.PI
        var change = current - previous
        var branch: String
        if (angularVelocity == 0.0) {
            branch = "zero-velocity"
            if (change > Math.PI) {
                change -= 2 * Math.PI
                branch += ":subtract-turn"
            } else if (change < -Math.PI) {
                change += 2 * Math.PI
                branch += ":add-turn"
            }
        } else if (current < previous && angularVelocity > 0) {
            change += 2 * Math.PI
            branch = "positive-wrap"
        } else if (current > previous && angularVelocity < 0) {
            change -= 2 * Math.PI
            branch = "negative-wrap"
        } else {
            branch = "direct"
        }
        return change to Triple(previousNegative, currentNegative, branch)
    }

    fun checkBodyGetters(body: JsonObject) {
        val properties = body["properties"] as? JsonObject ?: return
        if (properties.isEmpty()) return
        for ((getter, field) in DUPLICATE_GETTERS) {
            if (properties.containsKey(getter) && body.containsKey(field) &&
                !sameRunAlias(properties[getter], body[field])
            ) {
                throw Rejected("body getter alias differs: $getter")
            }
        }
        if (properties.containsKey("getChangeInPosition")) {
            val current = ((body["transform"] as? JsonObject)?.get("getTranslation")) as? JsonArray
            val previous = ((body["previousTransform"] as? JsonObject)?.get("getTranslation"))
                as? JsonArray
            if (current == null || previous == null || current.size != 2 || previous.size != 2 ||
                !sameValue(
                    properties["getChangeInPosition"],
                    JsonArray(
                        (0..1).map {
                            JsonPrimitive(
                                (current[it].numberOrNull() ?: 0.0) -
                                    (previous[it].numberOrNull() ?: 0.0),
                            )
                        },
                    ),
                )
            ) {
                throw Rejected("change in position formula differs")
            }
        }
        if (properties.containsKey("getChangeInOrientation")) {
            val current = ((body["transform"] as? JsonObject)?.get("getRotationAngle"))
                ?.numberOrNull() ?: 0.0
            val previous = ((body["previousTransform"] as? JsonObject)?.get("getRotationAngle"))
                ?.numberOrNull() ?: 0.0
            val change = orientationChange(
                previous,
                current,
                body["angularVelocity"]?.numberOrNull() ?: 0.0,
            ).first
            if (!sameValue(properties["getChangeInOrientation"], JsonPrimitive(change))) {
                throw Rejected("change in orientation formula differs")
            }
        }
    }

    fun checkSnapshot(state: JsonElement?) {
        val snapshot = state as? JsonObject ?: throw Rejected("translation getter alias differs")
        checkTranslationAliases(snapshot)
        for (element in snapshot["bodies"] as JsonArray) {
            checkBodyGetters(element as JsonObject)
        }
    }

    fun checkFixedBodyCallbackVelocities(event: JsonObject, fixture: JsonObject) {
        val fixedId = fixture["callback_fixed_body_id"]?.stringOrNull() ?: return
        for (side in listOf(1, 2)) {
            if (event["body$side"]?.stringOrNull() != fixedId) continue
            for (name in listOf("velocity$side", "angularVelocity$side")) {
                if (!event.containsKey(name)) continue
                val value = event[name] ?: JsonNull
                val components = if (value is JsonArray) value.toList() else listOf(value)
                if (components.isEmpty() ||
                    components.any { it.numberOrNull()?.let { number -> number != 0.0 } ?: true }
                ) {
                    throw Rejected("fixed callback body velocity is not zero: $name")
                }
            }
        }
    }

    fun fixedFloorId(fixture: JsonObject): String? {
        if (fixture["family"]?.stringOrNull() != "contacts-friction-sleep-wake") return null
        if (fixture["profile"]?.stringOrNull() == "default-sleep-wake") return "b0"
        if (fixture["profile"]?.stringOrNull() == "configured-sleep-wake") {
            return fixture["callback_fixed_body_id"]?.stringOrNull()
                ?: throw Rejected("configured fixed floor role is missing")
        }
        return null
    }

    fun endpointIndexMatches(
        row: JsonObject,
        fixture: JsonObject,
        stateCount: Int?,
        endpointCount: Int?,
    ): Boolean {
        val group = fixture["inner_per_outer"]?.intOrNull()
        val startStep = fixture["start_step"]?.intOrNull() ?: 0
        if (!fixture.containsKey("start_step")) {
            if (fixture["start_step"] != null) return false
        }
        return group != null && group > 0 &&
            fixture["start_step"].let { it == null || it.intOrNull() != null } &&
            startStep >= 0 &&
            stateCount != null && stateCount > 0 && stateCount % group == 0 &&
            endpointCount != null && endpointCount == stateCount / group &&
            row["step"].isIntegerLiteral() &&
            (row["step"]?.intOrNull() ?: -1) == startStep + stateCount &&
            row["outerStep"].isIntegerLiteral() &&
            (row["outerStep"]?.intOrNull() ?: -1) == stateCount / group
    }

    // ------------------------------------------------------------- counting

    fun checkCounts(rows: List<Record>, fixture: JsonObject, reference: Boolean): Map<String, Int> {
        val declared = (fixture["counts"] as? JsonObject)?.mapValues { it.value.intOrNull() ?: 0 }
            ?: throw NoSuchElementException("counts")
        val counts = LinkedHashMap<String, Int>()
        val startStep = fixture["start_step"]?.intOrNull()
        if (fixture.containsKey("start_step") && startStep == null) {
            throw Rejected("invalid fixture start step")
        }
        var stateStep = startStep ?: 0
        if ((startStep ?: 0) < 0) throw Rejected("invalid fixture start step")
        var eventStep = 0
        var eventOrder = -1
        var inputSeen = false
        var inputHash: String? = null
        var lastState: JsonElement? = null
        for (record in rows) {
            val row = record.row
            val kind = row["kind"]?.stringOrNull()
            if (kind == null || !declared.containsKey(kind)) {
                throw Rejected("unexpected record kind: ${PyText.of(row["kind"])}")
            }
            counts[kind] = (counts[kind] ?: 0) + 1
            if (kind == "inputs") {
                if (inputSeen || counts.values.sum() != 1 ||
                    row["id"]?.stringOrNull() != fixture["id"]?.stringOrNull()
                ) {
                    throw Rejected("wrong input order or fixture identity")
                }
                inputSeen = true
                inputHash = io.github.rubixhacker.harness.contract.Sha256.of(
                    record.line.dropLast(1),
                )
                if (fixture["check_translation_aliases"].booleanOrNull() == true &&
                    row.containsKey("state")
                ) {
                    checkSnapshot(row["state"])
                }
            } else if (!inputSeen) {
                throw Rejected("record precedes input")
            }
            if (kind == "state") {
                stateStep += 1
                if (!row["step"].isIntegerLiteral() ||
                    (row["step"]?.intOrNull() ?: -1) != stateStep
                ) {
                    throw Rejected("missing or reordered state")
                }
                lastState = row["state"]
                if (fixture["check_translation_aliases"].booleanOrNull() == true) {
                    checkSnapshot(lastState)
                }
            }
            if (kind == "outer-endpoint") {
                if (!endpointIndexMatches(row, fixture, counts["state"], counts["outer-endpoint"]) ||
                    !sameRunAlias(row["state"], lastState)
                ) {
                    throw Rejected("outer endpoint does not copy the matching inner state")
                }
            }
            if (kind == "instrumented-callback" &&
                fixture["check_translation_aliases"].booleanOrNull() == true
            ) {
                for (snapshot in (row["values"] as? JsonArray ?: JsonArray(emptyList()))) {
                    checkSnapshot(snapshot)
                }
            }
            if (kind == "event") {
                for (payload in (row["payload"] as? JsonArray ?: JsonArray(emptyList()))) {
                    if (payload is JsonObject) checkFixedBodyCallbackVelocities(payload, fixture)
                }
                val step = row["step"]?.intOrNull()
                val order = row["order"]?.intOrNull()
                if (!row["step"].isIntegerLiteral() || !row["order"].isIntegerLiteral() ||
                    step == null || order == null || step < eventStep || order < 0
                ) {
                    throw Rejected("invalid event step or order")
                }
                if (step == eventStep && order <= eventOrder) {
                    throw Rejected("event order is not increasing")
                }
                if (step > eventStep) eventOrder = -1
                eventStep = step
                eventOrder = order
            }
            if ((counts[kind] ?: 0) > (declared[kind] ?: 0)) {
                throw Rejected("too many $kind records")
            }
        }
        if (counts != declared) {
            throw Rejected("incomplete suite: ${PyText.dict(counts.entries.map { it.toPair() })}")
        }
        if (reference && inputHash != fixture["reference"]?.let { (it as JsonObject)["input_sha256"] }
                ?.stringOrNull()
        ) {
            throw Rejected("frozen input hash differs")
        }
        return counts
    }

    // ------------------------------------------------------------- path canonicalisation

    fun canonicalPath(path: String): String {
        var result = path
        if (result.startsWith("outer-endpoint.state.")) {
            result = "state.state." + result.removePrefix("outer-endpoint.state.")
        }
        if (result.startsWith("instrumented-callback.values[].bodies[].")) {
            result = "state.state.bodies[]." +
                result.removePrefix("instrumented-callback.values[].bodies[].")
            for ((getter, field) in DUPLICATE_GETTERS) {
                val prefix = "state.state.bodies[].properties.$getter"
                if (result == prefix || result.startsWith("$prefix.") ||
                    result.startsWith("${prefix}[]")
                ) {
                    result = "state.state.bodies[].$field" + result.removePrefix(prefix)
                    break
                }
            }
        }
        return result
    }

    /** `fnmatch.fnmatchcase`, with the array marker substituted on both sides. */
    fun matchesPath(path: String, pattern: String): Boolean {
        val expression = fnmatchTranslate(
            pattern.replace("[]", "{array}"),
        )
        return Regex(expression, RegexOption.DOT_MATCHES_ALL)
            .matches(path.replace("[]", "{array}"))
    }

    private fun fnmatchTranslate(pattern: String): String {
        val out = StringBuilder("^")
        var index = 0
        while (index < pattern.length) {
            val character = pattern[index]
            index += 1
            when (character) {
                '*' -> out.append(".*")
                '?' -> out.append('.')
                '[' -> {
                    var position = index
                    if (position < pattern.length && pattern[position] == '!') position += 1
                    if (position < pattern.length && pattern[position] == ']') position += 1
                    while (position < pattern.length && pattern[position] != ']') position += 1
                    if (position >= pattern.length) {
                        out.append("\\[")
                    } else {
                        var stuff = pattern.substring(index, position)
                        index = position + 1
                        stuff = stuff.replace("\\", "\\\\")
                        if (stuff.startsWith("!")) {
                            stuff = "^" + stuff.substring(1)
                        } else if (stuff.startsWith("^")) {
                            stuff = "\\" + stuff
                        }
                        out.append("[$stuff]")
                    }
                }
                else -> out.append(Regex.escape(character.toString()))
            }
        }
        out.append("$")
        return out.toString()
    }

    fun ruleFor(fixture: JsonObject, path: String, state: CompareState): JsonObject? {
        val canonical = canonicalPath(path)
        if (state.ruleCache.containsKey(canonical)) return state.ruleCache[canonical]
        val matches = (fixture["rules"] as? JsonArray ?: JsonArray(emptyList()))
            .map { it as JsonObject }
            .filter { matchesPath(canonical, it["path"]?.stringOrNull().orEmpty()) }
        if (matches.size > 1) throw Rejected("ambiguous numeric rule: $canonical")
        val rule = matches.firstOrNull()
        state.ruleCache[canonical] = rule
        return rule
    }

    // ------------------------------------------------------------- certified enclosures

    private val PI_BOUNDS: Pair<Fraction, Fraction> by lazy(LazyThreadSafetyMode.SYNCHRONIZED) {
        fun arctanReciprocal(denominator: Int): Pair<Fraction, Fraction> {
            var subtotal = Fraction.of(0)
            val base = BigNat.ofInt(denominator)
            for (index in 0 until 50) {
                val power = BigNat.pow(base, 2 * index + 1)
                val term = Fraction.ofRatio(BigNat.ONE, power.timesSmall((2L * index + 1)))
                subtotal = if (index % 2 == 0) subtotal + term else subtotal - term
            }
            val remainder = Fraction.ofRatio(
                BigNat.ONE,
                BigNat.ofInt(101).times(BigNat.pow(base, 101)),
            )
            return subtotal to subtotal + remainder
        }

        val fifth = arctanReciprocal(5)
        val twoThirtyNinth = arctanReciprocal(239)
        (fifth.first * Fraction.of(16) - twoThirtyNinth.second * Fraction.of(4)) to
            (fifth.second * Fraction.of(16) - twoThirtyNinth.first * Fraction.of(4))
    }

    fun piBounds(): Pair<Fraction, Fraction> = PI_BOUNDS

    fun orientationErrorBounds(reference: Double, candidate: Double): Pair<Fraction, Fraction> {
        if (kotlin.math.abs(reference) > 4 || kotlin.math.abs(candidate) > 4) {
            throw Rejected("orientation outside certified wrap domain")
        }
        val difference = Fraction.ofDouble(candidate) - Fraction.ofDouble(reference)
        val piLow = piBounds().first
        val piHigh = piBounds().second
        val lows = ArrayList<Fraction>()
        val highs = ArrayList<Fraction>()
        for (turns in -2..2) {
            val endpoints = listOf(
                difference - piLow * Fraction.of(2L * turns),
                difference - piHigh * Fraction.of(2L * turns),
            )
            val low = minOf(endpoints[0], endpoints[1])
            val high = maxOf(endpoints[0], endpoints[1])
            val lower = if (low <= Fraction.of(0) && Fraction.of(0) <= high) {
                Fraction.of(0)
            } else {
                minOf(low.abs(), high.abs())
            }
            lows.add(lower)
            highs.add(maxOf(low.abs(), high.abs()))
        }
        return lows.min() to highs.min()
    }

    private val SQRT_CACHE = HashMap<Fraction, Pair<Fraction, Fraction>>()
    private val COSINE_CACHE = HashMap<Pair<String, Int>, Pair<Fraction, Fraction>>()
    private val TANGENT_CACHE = HashMap<Fraction, Pair<Fraction, Fraction>>()

    fun sqrtBounds(value: Fraction): Pair<Fraction, Fraction> {
        val cached = SQRT_CACHE[value]
        if (cached != null) return cached
        val scaled = value * Fraction.ofRatio(ROOT_SCALE, BigNat.ONE) *
            Fraction.ofRatio(ROOT_SCALE, BigNat.ONE)
        val floor = scaled.numerator.magnitude
            .divMod(scaled.denominator).first.isqrt()
        val low = Fraction.ofRatio(floor, ROOT_SCALE)
        val high = if (low * low == value) low else Fraction.ofRatio(floor.plus(BigNat.ONE), ROOT_SCALE)
        val result = low to high
        SQRT_CACHE[value] = result
        return result
    }

    fun cosineBounds(angle: Double, terms: Int): Pair<Fraction, Fraction> {
        val key = io.github.rubixhacker.harness.numerical.Orthogonality.bits(angle) to terms
        val cached = COSINE_CACHE[key]
        if (cached != null) return cached
        if (kotlin.math.abs(angle) > 4) throw Rejected("angle outside certified cosine domain")
        if (terms < 10) throw Rejected("cosine enclosure has too few terms")
        val value = Fraction.ofDouble(kotlin.math.abs(angle))
        var approximation = Fraction.of(0)
        for (index in 0 until terms) {
            val term = value.pow(2 * index) /
                Fraction.ofMagnitude(BigNat.factorial(2 * index))
            approximation = if (index % 2 == 0) approximation + term else approximation - term
        }
        val remainder = value.pow(2 * terms) / Fraction.ofMagnitude(BigNat.factorial(2 * terms))
        val result = (approximation - remainder) to (approximation + remainder)
        COSINE_CACHE[key] = result
        return result
    }

    fun tangentBounds(angle: Fraction): Pair<Fraction, Fraction> {
        val cached = TANGENT_CACHE[angle]
        if (cached != null) return cached
        if (angle < Fraction.of(0) || angle >= Fraction.of(1)) {
            throw Rejected("direction cap outside certified domain")
        }
        var sine = Fraction.of(0)
        var cosine = Fraction.of(0)
        for (index in 0 until 10) {
            val sineTerm = angle.pow(2 * index + 1) /
                Fraction.ofMagnitude(BigNat.factorial(2 * index + 1))
            val cosineTerm = angle.pow(2 * index) /
                Fraction.ofMagnitude(BigNat.factorial(2 * index))
            sine = if (index % 2 == 0) sine + sineTerm else sine - sineTerm
            cosine = if (index % 2 == 0) cosine + cosineTerm else cosine - cosineTerm
        }
        val sineHigh = sine + angle.pow(21) / Fraction.ofMagnitude(BigNat.factorial(21))
        val cosineHigh = cosine + angle.pow(20) / Fraction.ofMagnitude(BigNat.factorial(20))
        if (cosine <= Fraction.of(0)) {
            throw Rejected("direction cap has invalid cosine enclosure")
        }
        val result = (sine / cosineHigh) to (sineHigh / cosine)
        TANGENT_CACHE[angle] = result
        return result
    }

    // ------------------------------------------------------------- checks

    private fun unitFraction(value: JsonElement?): Fraction = PyText.fraction(value)

    fun checkDirection(
        reference: JsonArray,
        candidate: JsonArray,
        rule: JsonObject,
        path: String,
        state: CompareState,
    ) {
        val leftValues = reference.map { it.numberOrNull() }
        val rightValues = candidate.map { it.numberOrNull() }
        if (reference.size != 2 ||
            (leftValues + rightValues).any { it == null || !it.isFinite() }
        ) {
            throw Rejected("invalid direction: $path")
        }
        val left = Pair(
            Fraction.ofDouble(leftValues[0]!!),
            Fraction.ofDouble(leftValues[1]!!),
        )
        val right = Pair(
            Fraction.ofDouble(rightValues[0]!!),
            Fraction.ofDouble(rightValues[1]!!),
        )
        val leftSquare = left.first.pow(2) + left.second.pow(2)
        val rightSquare = right.first.pow(2) + right.second.pow(2)
        if (leftSquare == Fraction.of(0) || rightSquare == Fraction.of(0)) {
            if (left != right || leftSquare != Fraction.of(0)) {
                throw Rejected("direction placeholder differs: $path")
            }
            state.numericChecks += 3
            return
        }
        val angleCap = unitFraction(rule["absolute"])
        val magnitudeCap = unitFraction(rule["magnitude_absolute"])
        val unitCap = unitFraction(rule["unit_deviation"])
        if (minOf(angleCap, magnitudeCap, unitCap) < Fraction.of(0) ||
            unitCap >= Fraction.of(1)
        ) {
            throw Rejected("invalid direction limit: $path")
        }
        val one = Fraction.of(1)
        if (left == right) {
            if (!((one - unitCap).pow(2) <= leftSquare && leftSquare <= (one + unitCap).pow(2))) {
                throw Rejected("direction is not unit length: $path")
            }
            state.numericChecks += 3
            return
        }
        val dot = left.first * right.first + left.second * right.second
        val cross = (left.first * right.second - left.second * right.first).abs()
        if (dot <= Fraction.of(0)) throw Rejected("direction angle exceeded: $path")
        val tangent = tangentBounds(angleCap)
        val ratio = cross / dot
        if (ratio > tangent.second) throw Rejected("direction angle exceeded: $path")
        if (ratio > tangent.first) state.unpassed.add(path)
        val leftBounds = sqrtBounds(leftSquare)
        val rightBounds = sqrtBounds(rightSquare)
        val differenceLow = maxOf(
            Fraction.of(0),
            rightBounds.first - leftBounds.second,
            leftBounds.first - rightBounds.second,
        )
        val differenceHigh = maxOf(
            (rightBounds.first - leftBounds.second).abs(),
            (rightBounds.second - leftBounds.first).abs(),
        )
        if (differenceLow > magnitudeCap) throw Rejected("direction magnitude exceeded: $path")
        if (differenceHigh > magnitudeCap) state.unpassed.add(path)
        for (bounds in listOf(leftBounds, rightBounds)) {
            if (bounds.second < one - unitCap || bounds.first > one + unitCap) {
                throw Rejected("direction is not unit length: $path")
            }
            if (bounds.first < one - unitCap || bounds.second > one + unitCap) {
                state.unpassed.add(path)
            }
        }
        state.numericChecks += 3
    }

    fun checkDerivedPair(
        fixture: JsonObject,
        reference: JsonObject,
        candidate: JsonObject,
        path: String,
        state: CompareState,
    ) {
        val left = reference["properties"] as? JsonObject ?: return
        val right = candidate["properties"] as? JsonObject ?: return
        if (left.isEmpty() || right.isEmpty()) return
        for ((getter, source, metric) in listOf(
            Triple("getChangeInPosition", "getTranslation[]", "position"),
            Triple("getChangeInOrientation", "getRotationAngle", "orientation"),
        )) {
            if (!left.containsKey(getter)) continue
            val formulas = fixture["derived_rules"] as? JsonObject
            val formula = formulas?.get("change_in_$metric") as? JsonObject ?: continue
            if (!formulas!!.containsKey("change_in_$metric") || formula["relative"]?.numberOrNull() != 0.0) {
                continue
            }
            val currentRule = ruleFor(
                fixture,
                "state.state.bodies[].transform.$source",
                state,
            ) ?: continue
            val previousRule = ruleFor(
                fixture,
                "state.state.bodies[].previousTransform.$source",
                state,
            ) ?: continue
            val cap = unitFraction(currentRule["absolute"]) + unitFraction(previousRule["absolute"])
            if (metric == "position") {
                val leftValues = left[getter] as JsonArray
                val rightValues = right[getter] as JsonArray
                for (index in 0..1) {
                    val currentLeft = Fraction.ofDouble(
                        ((reference["transform"] as JsonObject).getValue("getTranslation")
                            as JsonArray)[index].numberOrNull()!!,
                    )
                    val previousLeft = Fraction.ofDouble(
                        ((reference["previousTransform"] as JsonObject).getValue("getTranslation")
                            as JsonArray)[index].numberOrNull()!!,
                    )
                    val currentRight = Fraction.ofDouble(
                        ((candidate["transform"] as JsonObject).getValue("getTranslation")
                            as JsonArray)[index].numberOrNull()!!,
                    )
                    val previousRight = Fraction.ofDouble(
                        ((candidate["previousTransform"] as JsonObject).getValue("getTranslation")
                            as JsonArray)[index].numberOrNull()!!,
                    )
                    val exactLeft = currentLeft - previousLeft
                    val exactRight = currentRight - previousRight
                    val roundedLeft = Fraction.ofDouble(leftValues[index].numberOrNull()!!)
                    val roundedRight = Fraction.ofDouble(rightValues[index].numberOrNull()!!)
                    val rounding = (roundedLeft - exactLeft).abs() +
                        (roundedRight - exactRight).abs()
                    if ((roundedLeft - roundedRight).abs() > cap + rounding) {
                        throw Rejected("change in position derived limit exceeded")
                    }
                }
                state.derivedPaths.add("$path.properties.getChangeInPosition[]")
            } else {
                val leftBranch = orientationChange(
                    ((reference["previousTransform"] as JsonObject).getValue("getRotationAngle"))
                        .numberOrNull()!!,
                    ((reference["transform"] as JsonObject).getValue("getRotationAngle"))
                        .numberOrNull()!!,
                    reference["angularVelocity"]?.numberOrNull() ?: 0.0,
                ).second
                val rightBranch = orientationChange(
                    ((candidate["previousTransform"] as JsonObject).getValue("getRotationAngle"))
                        .numberOrNull()!!,
                    ((candidate["transform"] as JsonObject).getValue("getRotationAngle"))
                        .numberOrNull()!!,
                    candidate["angularVelocity"]?.numberOrNull() ?: 0.0,
                ).second
                if (leftBranch != rightBranch) {
                    throw Rejected("change in orientation branch differs")
                }
                val rounding = Fraction.ofDouble(
                    (formula["rounding_ulps_at_two_pi"]?.numberOrNull() ?: 0.0) *
                        Orthogonality.ulpValue(2 * Math.PI),
                )
                val difference = (
                    Fraction.ofDouble(left[getter]?.numberOrNull()!!) -
                        Fraction.ofDouble(right[getter]?.numberOrNull()!!)
                    ).abs()
                if (difference > cap + rounding) {
                    throw Rejected("change in orientation derived limit exceeded")
                }
                state.derivedPaths.add("$path.properties.getChangeInOrientation")
            }
        }
    }

    fun checkCostPair(
        fixture: JsonObject,
        reference: JsonObject,
        candidate: JsonObject,
        path: String,
        state: CompareState,
    ) {
        if (!path.startsWith("state.state.bodies[].") &&
            !path.startsWith("outer-endpoint.state.bodies[].") &&
            !path.startsWith("instrumented-callback.values[].bodies[].")
        ) {
            return
        }
        if (!reference.containsKey("getCost") || !reference.containsKey("getRotationAngle")) {
            return
        }
        val formulas = fixture["derived_rules"] as? JsonObject
        val formula = formulas?.get("stored_cosine") as? JsonObject ?: return
        if (formula["relative"]?.numberOrNull() != 0.0) return
        if (ruleFor(fixture, "$path.getCost", state) != null) return
        val angleRule = ruleFor(fixture, "$path.getRotationAngle", state) ?: return
        if (angleRule["metric"]?.stringOrNull() != "orientation" ||
            angleRule["relative"]?.numberOrNull() != 0.0
        ) {
            return
        }
        val allowances = ArrayList<Fraction>()
        for (transform in listOf(reference, candidate)) {
            val angle = transform["getRotationAngle"]?.numberOrNull()!!
            val cost = transform["getCost"]?.numberOrNull()!!
            val sine = transform["getSint"]?.numberOrNull()
            if (cost < -1 || cost > 1) throw Rejected("stored cosine outside source domain")
            if (sine != null && ((angle > 0 && sine < 0) || (angle < 0 && sine >= 0))) {
                throw Rejected("stored sine sign differs from public angle")
            }
            val bounds = cosineBounds(angle, formula["taylor_terms"]?.intOrNull() ?: 0)
            val allowance = Fraction.ofDouble(
                (formula["acos_ulp_multiplier"]?.numberOrNull() ?: 0.0) *
                    Orthogonality.ulpValue(kotlin.math.abs(angle)),
            )
            val represented = Fraction.ofDouble(cost)
            if (represented < bounds.first - allowance || represented > bounds.second + allowance) {
                throw Rejected("stored cosine and public angle formula differ")
            }
            allowances.add(allowance + bounds.second - bounds.first)
        }
        val angleCap = unitFraction(angleRule["absolute"])
        val bounds = if (reference["getRotationAngle"] == candidate["getRotationAngle"]) {
            Fraction.of(0) to Fraction.of(0)
        } else {
            orientationErrorBounds(
                reference["getRotationAngle"]?.numberOrNull()!!,
                candidate["getRotationAngle"]?.numberOrNull()!!,
            )
        }
        if (bounds.first > angleCap) {
            throw Rejected("public angle limit exceeded before cosine check")
        }
        if (bounds.second > angleCap) state.unpassed.add("$path.getCost")
        val cosineDifference = (
            Fraction.ofDouble(reference["getCost"]?.numberOrNull()!!) -
                Fraction.ofDouble(candidate["getCost"]?.numberOrNull()!!)
            ).abs()
        var totalAllowance = Fraction.of(0)
        allowances.forEach { totalAllowance += it }
        if (cosineDifference > angleCap + totalAllowance) {
            throw Rejected("stored cosine derived limit exceeded")
        }
        state.derivedPaths.add("$path.getCost")
    }

    private val SINE_CAP_CACHE = HashMap<List<String>, Fraction>()

    fun sineComponentCap(
        eta: Fraction,
        terms: Int,
        acosUlpMultiplier: Int,
        angleCap: Fraction,
    ): Fraction {
        val key = listOf(eta.toString(), terms.toString(), acosUlpMultiplier.toString(), angleCap.toString())
        SINE_CAP_CACHE[key]?.let { return it }
        val cosineError = Fraction.ofDouble(acosUlpMultiplier * Orthogonality.ulpValue(4.0)) +
            (Fraction.ofMagnitude(BigNat.pow(BigNat.ofInt(4), 2 * terms)) /
                Fraction.ofMagnitude(BigNat.factorial(2 * terms))) * Fraction.of(2)
        val sineError = sqrtBounds(
            eta * Fraction.of(2) + eta.pow(2) + cosineError * Fraction.of(2),
        ).second
        val result = angleCap + sineError * Fraction.of(2)
        SINE_CAP_CACHE[key] = result
        return result
    }

    fun checkSinePair(
        fixture: JsonObject,
        reference: JsonObject,
        candidate: JsonObject,
        path: String,
        state: CompareState,
    ) {
        val formulas = fixture["derived_rules"] as? JsonObject
        val formula = formulas?.get("stored_sine") as? JsonObject
        if (formula == null ||
            (!path.startsWith("state.state.bodies[].") &&
                !path.startsWith("outer-endpoint.state.bodies[].") &&
                !path.startsWith("instrumented-callback.values[].bodies[]."))
        ) {
            return
        }
        if (!reference.containsKey("getCost") || !reference.containsKey("getSint") ||
            !reference.containsKey("getRotationAngle")
        ) {
            return
        }
        if (ruleFor(fixture, "$path.getSint", state) != null) return
        val angleRule = ruleFor(fixture, "$path.getRotationAngle", state)
        val cosine = formulas?.get("stored_cosine") as? JsonObject
        if (formula["metric"]?.stringOrNull() != "rotation_norm_and_component" ||
            formula["relative"]?.numberOrNull() != 0.0 ||
            angleRule == null ||
            angleRule["metric"]?.stringOrNull() != "orientation" ||
            angleRule["relative"]?.numberOrNull() != 0.0 ||
            cosine == null ||
            cosine["relative"]?.numberOrNull() != 0.0
        ) {
            throw Rejected("stored sine lacks its selected formula premises")
        }
        val eta = unitFraction(formula["norm_absolute"])
        val steps = formula["max_inner_steps"]?.intOrNull()
        val rotations = formula["max_rotations_per_step"]?.intOrNull()
        val multiplier = formula["unit_roundoff_multiplier"]?.intOrNull()
        if (eta <= Fraction.of(0) || eta >= Fraction.of(1) ||
            !formula["max_inner_steps"].isIntegerLiteral() || steps == null || steps <= 0 ||
            !formula["max_rotations_per_step"].isIntegerLiteral() || rotations == null || rotations <= 0 ||
            !formula["unit_roundoff_multiplier"].isIntegerLiteral() || multiplier == null || multiplier <= 0 ||
            (fixture["counts"] as JsonObject)["state"]?.intOrNull()!! > steps
        ) {
            throw Rejected("stored sine norm premise is invalid")
        }
        val one = Fraction.of(1)
        val growth = Fraction.ofMagnitude(BigNat.ofInt(steps))
            .times(Fraction.ofMagnitude(BigNat.ofInt(rotations)))
            .times(Fraction.ofMagnitude(BigNat.ofInt(multiplier)))
            .times(Fraction.ofRatio(BigNat.ONE, BigNat.powerOfTwo(53)))
        if (growth >= one || growth / (one - growth) >= eta) {
            throw Rejected("stored sine operation enclosure exceeds norm limit")
        }
        val transforms = if (reference == candidate) listOf(reference) else listOf(reference, candidate)
        for (transform in transforms) {
            val cost = Fraction.ofDouble(transform["getCost"]?.numberOrNull()!!)
            val sine = Fraction.ofDouble(transform["getSint"]?.numberOrNull()!!)
            if (cost.abs() > one || sine.abs() > one) {
                throw Rejected("stored rotation coefficient outside source clamp")
            }
            val squared = cost.pow(2) + sine.pow(2)
            if (squared < (one - eta).pow(2) || squared > (one + eta).pow(2)) {
                throw Rejected("stored rotation norm limit exceeded")
            }
        }
        val terms = cosine["taylor_terms"]?.intOrNull()
        val cosineMultiplier = cosine["acos_ulp_multiplier"]?.intOrNull()
        if (terms == null || terms < 10 || cosineMultiplier == null || cosineMultiplier < 1) {
            throw Rejected("stored sine cosine enclosure is invalid")
        }
        val angleCap = unitFraction(angleRule["absolute"])
        val componentCap = sineComponentCap(eta, terms, cosineMultiplier, angleCap)
        val difference = (
            Fraction.ofDouble(reference["getSint"]?.numberOrNull()!!) -
                Fraction.ofDouble(candidate["getSint"]?.numberOrNull()!!)
            ).abs()
        if (difference > componentCap) throw Rejected("stored sine component limit exceeded")
        state.derivedPaths.add("$path.getSint")
    }

    fun isExactNumeric(fixture: JsonObject, path: String, state: CompareState): Boolean {
        state.exactCache[path]?.let { return it }
        val canonical = canonicalPath(path)
        val result = (fixture["exact_numeric"] as? JsonArray ?: JsonArray(emptyList())).any {
            val pattern = it.stringOrNull().orEmpty()
            matchesPath(path, pattern) || matchesPath(canonical, pattern)
        }
        state.exactCache[path] = result
        return result
    }

    fun isZeroNumeric(fixture: JsonObject, path: String, state: CompareState): Boolean {
        val canonical = canonicalPath(path)
        state.zeroCache[canonical]?.let { return it }
        val result = (fixture["zero_numeric"] as? JsonArray ?: JsonArray(emptyList())).any {
            matchesPath(canonical, it.stringOrNull().orEmpty())
        }
        state.zeroCache[canonical] = result
        return result
    }

    fun compareValue(
        fixture: JsonObject,
        reference: JsonElement?,
        candidate: JsonElement?,
        path: String,
        state: CompareState,
    ) {
        val left = reference ?: JsonNull
        val right = candidate ?: JsonNull
        val numeric = left.isNumber() && right.isNumber()
        if (kindOf(left) != kindOf(right) && !numeric) {
            throw Rejected("type differs: $path")
        }
        if (left is JsonObject) {
            val rightObject = right as JsonObject
            if (left.keys != rightObject.keys) throw Rejected("fields differ: $path")
            checkCostPair(fixture, left, rightObject, path, state)
            checkSinePair(fixture, left, rightObject, path, state)
            if (path == "instrumented-callback.values[].bodies[]") {
                checkDerivedPair(fixture, left, rightObject, path, state)
            }
            for (key in left.keys) {
                compareValue(
                    fixture,
                    left[key],
                    rightObject[key],
                    if (path.isEmpty()) key else "$path.$key",
                    state,
                )
            }
        } else if (left is JsonArray) {
            val rightArray = right as JsonArray
            if (left.size != rightArray.size) throw Rejected("length differs: $path")
            if (path == "state.state.bodies") {
                val fixedId = fixedFloorId(fixture)
                for (index in left.indices) {
                    if (fixedId != null &&
                        (left[index] as? JsonObject)?.get("id")?.stringOrNull() == fixedId &&
                        !sameValue(left[index], rightArray[index])
                    ) {
                        throw Rejected("fixed floor differs")
                    }
                }
            }
            val rule = ruleFor(fixture, path, state)
            if (rule != null && rule["metric"]?.stringOrNull() == "direction") {
                checkDirection(left, rightArray, rule, path, state)
                return
            }
            if (canonicalPath(path).startsWith("state.state.bodies[].") &&
                path.endsWith(".getValues")
            ) {
                if (left.size != 6) throw Rejected("invalid transform matrix: $path")
                val base = path.dropLast("getValues".length)
                val getters = listOf(
                    "getCost", "getSint", "getTranslationX",
                    "getSint", "getCost", "getTranslationY",
                )
                for (index in 0..5) {
                    compareValue(
                        fixture,
                        left[index],
                        rightArray[index],
                        base + getters[index],
                        state,
                    )
                }
                return
            }
            for (index in left.indices) {
                compareValue(fixture, left[index], rightArray[index], "$path[]", state)
            }
        } else if (left.isNumber()) {
            if ((path.endsWith(".getCost") || path.endsWith(".getSint")) &&
                state.derivedPaths.contains(path)
            ) {
                state.derivedChecks += 1
                return
            }
            if (path.startsWith("instrumented-callback.") &&
                (path.endsWith(".properties.getChangeInPosition[]") ||
                    path.endsWith(".properties.getChangeInOrientation"))
            ) {
                if (state.derivedPaths.contains(path)) {
                    state.derivedChecks += 1
                } else {
                    state.unpassed.add(path)
                }
                return
            }
            if (isZeroNumeric(fixture, path, state)) {
                if (left.numberOrNull() != 0.0 || right.numberOrNull() != 0.0) {
                    throw Rejected("zero invariant differs: $path")
                }
                state.exactNumericChecks += 1
                return
            }
            val rule = ruleFor(fixture, path, state)
            if (rule != null) {
                val absolute = rule["absolute"]?.numberOrNull()
                val relative = rule["relative"]?.numberOrNull()
                if (absolute == null || relative == null || !absolute.isFinite() ||
                    !relative.isFinite() || absolute < 0 || relative < 0
                ) {
                    throw Rejected("invalid numeric limit: $path")
                }
                val metric = rule["metric"]?.stringOrNull()
                if (metric != "scalar" && metric != "orientation") {
                    throw Rejected("unknown metric: $path")
                }
                val leftValue = left.numberOrNull()!!
                val rightValue = right.numberOrNull()!!
                if (sameValue(left, right)) {
                    if (metric == "orientation" && kotlin.math.abs(leftValue) > 4) {
                        throw Rejected("orientation outside certified wrap domain")
                    }
                    state.numericChecks += 1
                    return
                }
                val cap = unitFraction(rule["absolute"]) +
                    unitFraction(rule["relative"]) *
                    Fraction.ofDouble(leftValue).abs()
                val bounds = if (metric == "orientation") {
                    orientationErrorBounds(leftValue, rightValue)
                } else {
                    val difference = (Fraction.ofDouble(rightValue) -
                        Fraction.ofDouble(leftValue)).abs()
                    difference to difference
                }
                if (bounds.first > cap) throw Rejected("numeric limit exceeded: $path")
                if (bounds.second > cap) state.unpassed.add(path)
                state.numericChecks += 1
            } else if (isExactNumeric(fixture, path, state)) {
                if (!sameValue(left, right)) {
                    throw Rejected("exact numeric field differs: $path")
                }
                state.exactNumericChecks += 1
            } else {
                state.unpassed.add(path)
            }
        } else if (!sameValue(left, right)) {
            throw Rejected("exact field differs: $path")
        }
    }

    private fun kindOf(value: JsonElement): String = when {
        value is JsonObject -> "dict"
        value is JsonArray -> "list"
        value.isBoolean() -> "bool"
        value.stringOrNull() != null -> "str"
        value.isNumber() -> "number"
        else -> "none"
    }

    /** `compare.compare`, after the receipt and both traces have been read. */
    fun compareRecords(
        fixture: JsonObject,
        reference: List<Record>,
        candidate: List<Record>,
    ): JsonObject {
        checkCounts(candidate, fixture, reference = false)
        val state = CompareState()
        var index = 0
        val longest = maxOf(reference.size, candidate.size)
        while (index < longest) {
            if (index >= reference.size || index >= candidate.size) {
                throw Rejected("record count differs")
            }
            val left = reference[index]
            val right = candidate[index]
            if (left.row["kind"]?.stringOrNull() != right.row["kind"]?.stringOrNull()) {
                throw Rejected("record kind order differs")
            }
            compareValue(
                fixture,
                left.row,
                right.row,
                left.row["kind"]?.stringOrNull().orEmpty(),
                state,
            )
            index += 1
        }
        return buildResult(fixture, state)
    }

    private fun buildResult(fixture: JsonObject, state: CompareState): JsonObject {
        val status = if (state.unpassed.isEmpty()) "PASSED" else "UNPASSED"
        return kotlinx.serialization.json.buildJsonObject {
            put("status", status)
            put("numeric_checks", state.numericChecks)
            put("exact_numeric_checks", state.exactNumericChecks)
            put("derived_checks", state.derivedChecks)
            put(
                "unpassed_channels",
                JsonArray(state.unpassed.sorted().map { JsonPrimitive(it) }),
            )
            put("counts", fixture["counts"] ?: JsonNull)
        }
    }

    /** `compare.load_fixture`: the profile merged with the fixture entry. */
    fun loadFixture(catalog: JsonObject, key: String): JsonObject {
        val item = (catalog["fixtures"] as? JsonArray ?: JsonArray(emptyList()))
            .map { it as JsonObject }
            .firstOrNull { it["key"]?.stringOrNull() == key }
            ?: throw NoSuchElementException("no fixture: $key")
        val profile = (catalog["profiles"] as JsonObject)[
            item.getValue("profile").stringOrNull(),
        ] as JsonObject
        val merged = LinkedHashMap<String, JsonElement>(profile)
        merged.putAll(item)
        merged["baseline_source_revision"] = catalog["baseline_source_revision"] ?: JsonNull
        merged["baseline_jar_sha256"] = catalog["baseline_jar_sha256"] ?: JsonNull
        return JsonObject(merged)
    }

    /** `compare.load_receipt`, given the receipt and candidate bytes. */
    fun loadReceipt(
        receiptBytes: ByteArray,
        candidateBytes: ByteArray,
        fixture: JsonObject,
        source: String,
        artifact: String,
        commit: String,
        counts: JsonObject,
    ) {
        val receipt = parse(receiptBytes)
        val commitPattern = Regex("[0-9a-f]{40}")
        val digestPattern = Regex("[0-9a-f]{64}")
        if (!commitPattern.matches(commit) ||
            receipt["candidate_commit"]?.stringOrNull() != commit
        ) {
            throw Rejected("candidate commit identity differs")
        }
        if (!digestPattern.matches(source) || !digestPattern.matches(artifact)) {
            throw Rejected("candidate source or artifact digest is malformed")
        }
        if (receipt["source_sha256"]?.stringOrNull() != source ||
            receipt["artifact_sha256"]?.stringOrNull() != artifact
        ) {
            throw Rejected("candidate source or artifact identity differs")
        }
        if (receipt["reference_source_revision"]?.stringOrNull() !=
            fixture["baseline_source_revision"]?.stringOrNull() ||
            receipt["reference_artifact_sha256"]?.stringOrNull() !=
            fixture["baseline_jar_sha256"]?.stringOrNull() ||
            receipt["reference_trace_sha256"]?.stringOrNull() !=
            ((fixture["reference"] as? JsonObject)?.get("gzip_sha256"))?.stringOrNull()
        ) {
            throw Rejected("frozen source, artifact, or reference identity differs")
        }
        if (receipt["trace_sha256"]?.stringOrNull() !=
            io.github.rubixhacker.harness.contract.Sha256.of(candidateBytes)
        ) {
            throw Rejected("candidate trace hash differs")
        }
        for (field in listOf("expected_counts", "executed_counts")) {
            if (!sameValue(receipt[field], counts)) {
                throw Rejected("$field differs from frozen counts")
            }
        }
        if (receipt["skipped"]?.intOrNull() != 0) throw Rejected("suite has skipped cases")
        if (!counts.any { (kind, value) -> kind != "inputs" && (value.intOrNull() ?: 0) > 0 }) {
            throw Rejected("suite is empty")
        }
    }

    /** `compare.parse`: a whole document, not a line. */
    fun parse(bytes: ByteArray): JsonObject {
        val text = try {
            bytes.toString(Charsets.UTF_8)
        } catch (error: Exception) {
            throw Rejected("invalid JSON: ${error.message}")
        }
        val value = try {
            PyJson.load(text, nonfinite = "nonfinite token")
        } catch (failure: JsonDecodeFailure) {
            throw Rejected("invalid JSON: ${failure.message}")
        }
        if (value !is JsonObject) throw Rejected("record is not an object")
        finite(value)
        return value
    }

    /** `compare.finite`: also rejects integers a binary64 cannot carry. */
    fun finite(value: JsonElement) {
        when (value) {
            is JsonPrimitive -> {
                if (value.isNumber() && !isIntegerOrSafe(value)) {
                    throw Rejected("unsafe JSON integer")
                }
                if (value.isNumber()) {
                    val number = value.numberOrNull() ?: return
                    if (!number.isFinite()) throw Rejected("nonfinite number")
                }
            }
            is JsonObject -> value.values.forEach { finite(it) }
            is JsonArray -> value.forEach { finite(it) }
            else -> Unit
        }
    }

    private fun isIntegerOrSafe(value: JsonPrimitive): Boolean {
        if (!value.isIntegerLiteral()) return true
        val magnitude = value.content.removePrefix("-")
        if (magnitude.length < 16) return true
        val parsed = magnitude.toULongOrNull() ?: return false
        return parsed <= (1uL shl 53)
    }
}

/** The mutable counters and caches one comparison run carries. */
class CompareState {
    var numericChecks = 0
    var exactNumericChecks = 0
    var derivedChecks = 0
    val unpassed = LinkedHashSet<String>()
    val derivedPaths = LinkedHashSet<String>()
    val ruleCache = HashMap<String, JsonObject?>()
    val exactCache = HashMap<String, Boolean>()
    val zeroCache = HashMap<String, Boolean>()
}

private fun compareResultOf(state: CompareState): Unit = Unit
