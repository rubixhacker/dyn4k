package io.github.rubixhacker.harness.numerical

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import kotlin.math.abs

/**
 * Python's `Decimal` rendered at a fixed precision, which `weld_pulley_quality.shown` uses to
 * report a metric enclosure.
 *
 * The arithmetic that decides a limit stays in exact rationals; only the report goes through
 * this formatter, so it reproduces `Decimal(num)/Decimal(den)` under `prec = 80` and Python's
 * `to-scientific-string` rendering.
 */
object DecimalText {
    const val PRECISION = 80

    fun shown(value: Fraction): String {
        val (digits, exponent) = significant(value, PRECISION)
        val negative = value.numerator.negative && !value.numerator.isZero()
        val sign = if (negative) "-" else ""
        if (digits == "0") return "$sign" + "0"
        val leftDigits = digits.length + exponent
        if (exponent <= 0 && leftDigits > -6) {
            val integerPart: String
            val fraction: String
            when {
                exponent == 0 -> { integerPart = digits; fraction = "" }
                leftDigits > 0 -> {
                    integerPart = digits.substring(0, leftDigits)
                    fraction = digits.substring(leftDigits)
                }
                else -> {
                    integerPart = "0"
                    fraction = "0".repeat(-leftDigits) + digits
                }
            }
            return sign + integerPart + if (fraction.isEmpty()) "" else ".$fraction"
        }
        val head = if (digits.length > 1) digits[0] + "." + digits.substring(1) else digits
        val adjusted = leftDigits - 1
        val exponentText = "E" + (if (adjusted >= 0) "+" else "-") + abs(adjusted)
        return sign + head + exponentText
    }

    /** The significant digits and the exponent of the last digit, at [precision] digits. */
    fun significant(value: Fraction, precision: Int): Pair<String, Int> {
        val numerator = value.numerator.magnitude
        val denominator = value.denominator
        if (numerator.isZero()) return "0" to 0
        exactDecimal(numerator, denominator, precision)?.let { return it }
        val adjusted = adjustedExponent(numerator, denominator)
        val shift = precision - 1 - adjusted
        var scaledNumerator = numerator
        var scaledDenominator = denominator
        if (shift >= 0) scaledNumerator = scaledNumerator.times(BigNat.powerOfTen(shift))
        else scaledDenominator = scaledDenominator.times(BigNat.powerOfTen(-shift))
        var quotient = rounded(scaledNumerator, scaledDenominator)
        var exponent = -shift
        val limit = BigNat.powerOfTen(precision)
        if (quotient >= limit) {
            quotient = quotient.divMod(BigNat.ofInt(10)).first
            exponent += 1
        }
        var digits = quotient.toString()
        while (digits.length < precision) digits = "0$digits"
        return digits to exponent
    }

    /** The exact terminating decimal, when the value has one within [precision] digits. */
    private fun exactDecimal(
        numerator: BigNat,
        denominator: BigNat,
        precision: Int,
    ): Pair<String, Int>? {
        var twos = 0
        var fives = 0
        var rest = denominator
        while (true) {
            val division = rest.divSmall(2)
            if (division.second != 0L) break
            rest = division.first
            twos += 1
        }
        while (true) {
            val division = rest.divSmall(5)
            if (division.second != 0L) break
            rest = division.first
            fives += 1
        }
        if (rest != BigNat.ONE) return null
        val scale = maxOf(twos, fives)
        val scaled = numerator.times(BigNat.powerOfTen(scale))
        val division = scaled.divMod(denominator)
        if (!division.second.isZero()) return null
        var digits = division.first.toString()
        var exponent = -scale
        while (digits.length > 1 && digits.endsWith("0")) {
            digits = digits.dropLast(1)
            exponent += 1
        }
        if (digits.length > precision) return null
        return digits to exponent
    }

    /** `-` one below the decimal exponent of the value, so `10^E <= value < 10^(E+1)`. */
    private fun adjustedExponent(numerator: BigNat, denominator: BigNat): Int {
        fun compareToPower(exponent: Int): Int = if (exponent >= 0) {
            numerator.compareTo(denominator.times(BigNat.powerOfTen(exponent)))
        } else {
            numerator.times(BigNat.powerOfTen(-exponent)).compareTo(denominator)
        }
        var exponent = numerator.toString().length - denominator.toString().length
        while (compareToPower(exponent) < 0) exponent -= 1
        while (compareToPower(exponent + 1) >= 0) exponent += 1
        return exponent
    }

    /** `numerator / denominator` rounded to an integer, ties to even. */
    private fun rounded(numerator: BigNat, denominator: BigNat): BigNat {
        val division = numerator.divMod(denominator)
        val twiceRemainder = division.second.timesSmall(2L)
        val comparison = twiceRemainder.compareTo(denominator)
        return when {
            comparison > 0 -> division.first.plus(BigNat.ONE)
            comparison < 0 -> division.first
            division.first.divSmall(2).second == 0L -> division.first
            else -> division.first.plus(BigNat.ONE)
        }
    }
}

/**
 * `weld_pulley_quality.py`: the frozen Weld and Pulley physical quality engine.
 *
 * Each state is reduced to enclosure intervals for the metric the case declares, and every
 * state is compared against the declaration's absolute limit. A value whose enclosure straddles
 * the limit fails closed instead of being rounded into a pass.
 */
object WeldPulleyQuality {
    private val CALLBACKS = listOf("begin", "postSolve", "end")
    private val ROOT_SCALE = BigNat.powerOfTen(60)
    private val U: Double = 1.0 / (1L shl 53).toDouble()

    private fun require(condition: Boolean, message: String) {
        if (!condition) throw Rejected(message)
    }

    /** `weld_pulley_quality.number`: the exact rational value of a finite JSON number. */
    fun number(value: JsonElement?): Fraction {
        val parsed = value?.numberOrNull()
        if (!value.isNumber() || parsed == null || !parsed.isFinite()) {
            throw Rejected("missing or nonfinite numeric field")
        }
        return Fraction.ofDouble(parsed)
    }

    fun vectorOf(value: JsonElement?): Pair<Fraction, Fraction> {
        if (value !is JsonArray || value.size != 2) {
            throw Rejected("missing vector component")
        }
        return number(value[0]) to number(value[1])
    }

    fun distanceInterval(a: JsonElement?, b: JsonElement?): Pair<Fraction, Fraction> {
        val (x, y) = vectorOf(a)
        val (p, q) = vectorOf(b)
        val square = (x - p).pow(2) + (y - q).pow(2)
        val scaled = square.numerator.magnitude.times(ROOT_SCALE).times(ROOT_SCALE)
        val floor = scaled.divMod(square.denominator).first.isqrt()
        val lower = Fraction.ofRatio(floor, ROOT_SCALE)
        val upper = if (lower * lower == square) lower else {
            Fraction.ofRatio(floor.plus(BigNat.ONE), ROOT_SCALE)
        }
        return lower to upper
    }

    fun shown(value: Fraction): String = DecimalText.shown(value)

    fun atanInterval(value: Fraction): Pair<Fraction, Fraction> {
        if (value < Fraction.of(0)) {
            val inner = atanInterval(value.negated())
            return inner.second.negated() to inner.first.negated()
        }
        if (value > Fraction.ofRatio(BigNat.ONE, BigNat.ofInt(2))) {
            throw Rejected("atan argument exceeds the certified series range")
        }
        var power = value
        var total = Fraction.of(0)
        val threshold = Fraction.ofRatio(BigNat.ONE, ROOT_SCALE)
        for (index in 0 until 256) {
            val term = power / Fraction.ofMagnitude(BigNat.ofInt(2 * index + 1))
            total = if (index % 2 == 0) total + term else total - term
            power = power * value * value
            val remainder = power / Fraction.ofMagnitude(BigNat.ofInt(2 * index + 3))
            if (remainder <= threshold) {
                return if (index % 2 == 0) {
                    (total - remainder) to total
                } else {
                    total to (total + remainder)
                }
            }
        }
        throw Rejected("atan enclosure did not converge")
    }

    private val PI_INTERVAL: Pair<Fraction, Fraction> by lazy(LazyThreadSafetyMode.SYNCHRONIZED) {
        val fifth = atanInterval(Fraction.ofRatio(BigNat.ONE, BigNat.ofInt(5)))
        val twoThirtyNinth = atanInterval(Fraction.ofRatio(BigNat.ONE, BigNat.ofInt(239)))
        (fifth.first * Fraction.of(16) - twoThirtyNinth.second * Fraction.of(4)) to
            (fifth.second * Fraction.of(16) - twoThirtyNinth.first * Fraction.of(4))
    }

    fun piInterval(): Pair<Fraction, Fraction> = PI_INTERVAL

    fun acuteOrientationInterval(
        cosine: Fraction,
        sine: Fraction,
    ): Pair<Fraction, Fraction> {
        if (cosine == Fraction.of(0)) {
            val pi = piInterval()
            return pi.first / Fraction.of(2) to pi.second / Fraction.of(2)
        }
        val ratio = sine / cosine
        val half = Fraction.ofRatio(BigNat.ONE, BigNat.ofInt(2))
        val two = Fraction.of(2)
        if (ratio <= half) return atanInterval(ratio)
        if (ratio <= two) {
            val inner = atanInterval((ratio - Fraction.of(1)) / (ratio + Fraction.of(1)))
            val pi = piInterval()
            return pi.first / Fraction.of(4) + inner.first to
                pi.second / Fraction.of(4) + inner.second
        }
        val inner = atanInterval(Fraction.of(1) / ratio)
        val pi = piInterval()
        return pi.first / Fraction.of(2) - inner.second to
            pi.second / Fraction.of(2) - inner.first
    }

    fun absoluteOrientationInterval(
        cosine: Fraction,
        sine: Fraction,
    ): Pair<Fraction, Fraction> {
        if (cosine == Fraction.of(0) && sine == Fraction.of(0)) {
            throw Rejected("zero rotation coefficients")
        }
        if (cosine >= Fraction.of(0)) {
            return acuteOrientationInterval(cosine, sine.abs())
        }
        val inner = acuteOrientationInterval(cosine.negated(), sine.abs())
        val pi = piInterval()
        return pi.first - inner.second to pi.second - inner.first
    }

    fun limit(declaration: JsonObject, case: String, name: String): Fraction {
        val cases = declaration["cases"] as JsonObject
        val metrics = (cases[case] as JsonObject)["metrics"] as JsonObject
        val rule = metrics[name] as JsonObject
        if (rule["relative_limit"]?.stringOrNull() != "0") {
            throw Rejected("physical quality requires zero relative allowance")
        }
        val result = Fraction.ofDecimalString(rule["absolute_limit"]?.stringOrNull().orEmpty())
        if (result <= Fraction.of(0)) throw Rejected("invalid physical limit")
        return result
    }

    fun phases(declaration: JsonObject) {
        var current = 1
        for (element in declaration["phases"] as JsonArray) {
            val entry = element as JsonArray
            val name = entry[0].stringOrNull()
            val first = entry[1].intOrNull()
            val last = entry[2].intOrNull()
            if ((name != "excitation" && name != "long-run") || first == null || last == null ||
                first != current || last < first
            ) {
                throw Rejected("physical phase schedule has a gap")
            }
            current = last + 1
        }
        if (current - 1 != declaration["steps_per_case"]?.intOrNull()) {
            throw Rejected("physical phase schedule does not cover all states")
        }
    }

    private fun keys(value: JsonObject): Set<String> = value.keys

    fun weld(state: JsonObject): Map<String, Pair<Fraction, Fraction>> {
        if (keys(state) != setOf("bodies", "joint")) throw Rejected("weld state paths differ")
        val bodies = state["bodies"] as? JsonArray ?: throw Rejected("weld state paths differ")
        val joint = state["joint"] as? JsonObject ?: throw Rejected("weld state paths differ")
        val bodyKeys = setOf("id", "center", "angle", "cost", "sint")
        if (bodies.size != 2 ||
            bodies.any { it !is JsonObject || keys(it) != bodyKeys } ||
            keys(joint) != setOf(
                "type", "spring", "limits", "frequency", "dampingRatio", "lowerLimit",
                "upperLimit", "anchor1", "anchor2", "referenceAngle",
            )
        ) {
            throw Rejected("weld body or joint paths differ")
        }
        val ids = bodies.map { (it as JsonObject)["id"]?.stringOrNull() }
        if (ids != listOf("ground", "member") ||
            joint["type"]?.stringOrNull() != "WeldJoint" ||
            joint["spring"].booleanOrNull() != true ||
            joint["limits"].booleanOrNull() != true ||
            number(joint["referenceAngle"]) != Fraction.of(0) ||
            number(joint["frequency"]) != Fraction.of(8) ||
            number(joint["dampingRatio"]) != Fraction.ofDouble(0.3) ||
            number(joint["lowerLimit"]) != Fraction.of(0) ||
            number(joint["upperLimit"]) != Fraction.of(0)
        ) {
            throw Rejected("weld structure or mode differs")
        }
        val fixed = bodies[0] as JsonObject
        val moving = bodies[1] as JsonObject
        val anchor1 = vectorOf(joint["anchor1"])
        if (vectorOf(fixed["center"]) != (Fraction.of(0) to Fraction.of(0)) ||
            number(fixed["angle"]) != Fraction.of(0) ||
            number(fixed["cost"]) != Fraction.of(1) ||
            number(fixed["sint"]) != Fraction.of(0) ||
            anchor1 != (
                Fraction.ofDecimalString("-0.5") to Fraction.ofDecimalString("2")
                )
        ) {
            throw Rejected("fixed weld body or anchor differs")
        }
        val center = vectorOf(moving["center"])
        val cosine = number(moving["cost"])
        val sine = number(moving["sint"])
        if (cosine.abs() > Fraction.of(1) || sine.abs() > Fraction.of(1)) {
            throw Rejected("rotation coefficient exceeds the source range")
        }
        val anchor = vectorOf(joint["anchor2"])
        val expected = listOf(
            center.first - cosine / Fraction.of(2),
            center.second - sine / Fraction.of(2),
        )
        for ((index, formula) in expected.withIndex()) {
            val allowance = Fraction.ofDouble(8 * U) * (
                formula.abs() + center.first.abs() + center.second.abs() + Fraction.of(1)
                )
            if ((anchor.toList()[index] - formula).abs() > allowance) {
                throw Rejected("weld moving anchor does not follow stored transform")
            }
        }
        val angle = (number(moving["angle"]) - number(fixed["angle"])).toDouble()
        if (abs(angle) > Math.PI) {
            throw Rejected("weld angle is outside the source normalized range")
        }
        val exactAngle = Fraction.ofDouble(abs(angle))
        val represented = absoluteOrientationInterval(cosine, sine)
        return mapOf(
            "anchor_gap_m" to distanceInterval(joint["anchor1"], joint["anchor2"]),
            "angular_error_rad" to (
                maxOf(exactAngle, represented.first) to maxOf(exactAngle, represented.second)
                ),
        )
    }

    fun pulley(state: JsonObject): Map<String, Pair<Fraction, Fraction>> {
        if (keys(state) != setOf("bodies", "joint")) throw Rejected("pulley state paths differ")
        val bodies = state["bodies"] as? JsonArray ?: throw Rejected("pulley state paths differ")
        val joint = state["joint"] as? JsonObject ?: throw Rejected("pulley state paths differ")
        if (bodies.size != 2 ||
            bodies.any { it !is JsonObject || keys(it) != setOf("id", "center") } ||
            keys(joint) != setOf(
                "type", "slack", "ratio", "length", "pulleyAnchor1", "pulleyAnchor2",
                "anchor1", "anchor2",
            )
        ) {
            throw Rejected("pulley body or joint paths differ")
        }
        val ids = bodies.map { (it as JsonObject)["id"]?.stringOrNull() }
        if (ids != listOf("left", "right") ||
            joint["type"]?.stringOrNull() != "PulleyJoint" ||
            joint["slack"].booleanOrNull() != false ||
            number(joint["ratio"]) != Fraction.of(1) ||
            number(joint["length"]) != Fraction.of(2) ||
            vectorOf(joint["pulleyAnchor1"]) !=
            (Fraction.of(-1) to Fraction.of(1)) ||
            vectorOf(joint["pulleyAnchor2"]) != (Fraction.of(1) to Fraction.of(1))
        ) {
            throw Rejected("pulley structure, anchors, ratio, or mode differs")
        }
        if (vectorOf(joint["anchor1"]) != vectorOf((bodies[0] as JsonObject)["center"]) ||
            vectorOf(joint["anchor2"]) != vectorOf((bodies[1] as JsonObject)["center"])
        ) {
            throw Rejected("pulley body-anchor alias differs")
        }
        val first = distanceInterval(joint["anchor1"], joint["pulleyAnchor1"])
        val second = distanceInterval(joint["anchor2"], joint["pulleyAnchor2"])
        val lower = first.first + second.first - Fraction.of(2)
        val upper = first.second + second.second - Fraction.of(2)
        val absolute = when {
            lower >= Fraction.of(0) -> lower to upper
            upper <= Fraction.of(0) -> upper.negated() to lower.negated()
            else -> Fraction.of(0) to maxOf(lower.negated(), upper)
        }
        return mapOf("absolute_rope_error_m" to absolute)
    }

    /**
     * `weld_pulley_quality.audit_quality`. [read] returns the raw archive bytes and the
     * decompressed stream, so the filesystem stays in the host layer.
     */
    fun auditQuality(
        declaration: JsonObject,
        manifest: JsonObject,
        case: String,
        fileName: String,
        read: () -> Pair<ByteArray, ByteArray>,
    ): JsonObject = try {
        phases(declaration)
        val expected = ((manifest["cases"] as JsonObject)[case]) as? JsonObject
            ?: throw NoSuchElementException("KeyError: $case")
        if (!(declaration["cases"] as JsonObject).containsKey(case) ||
            manifest["baseline_source_revision"]?.stringOrNull() !=
            declaration["baseline_source_revision"]?.stringOrNull() ||
            manifest["baseline_jar_sha256"]?.stringOrNull() !=
            declaration["baseline_jar_sha256"]?.stringOrNull()
        ) {
            throw Rejected("baseline source, JAR, or case identity differs")
        }
        val (raw, stream) = read()
        if (fileName != expected["file"]?.stringOrNull() ||
            io.github.rubixhacker.harness.contract.Sha256.of(raw) !=
            expected["gzip_sha256"]?.stringOrNull()
        ) {
            throw Rejected("frozen gzip member identity differs")
        }
        if (io.github.rubixhacker.harness.contract.Sha256.of(stream) !=
            expected["stream_sha256"]?.stringOrNull()
        ) {
            throw Rejected("frozen stream identity differs")
        }
        val lines = splitKeepingEnds(stream)
        if (lines.isEmpty() || lines.any { !it.endsWith("\n") }) {
            throw Rejected("empty or incomplete JSONL stream")
        }
        if (io.github.rubixhacker.harness.contract.Sha256.of(lines[0].dropLast(1)) !=
            expected["input_sha256"]?.stringOrNull()
        ) {
            throw Rejected("frozen input identity differs")
        }
        val header = Compare.parse(lines[0].toByteArray(Charsets.UTF_8))
        val required = buildJsonObject {
            put("kind", "inputs")
            put("case", case)
            put("declaration_sha256", manifest["declaration_sha256"] ?: JsonNull)
            put("capture_sha256", manifest["capture_sha256"] ?: JsonNull)
            put("source_revision", declaration["baseline_source_revision"] ?: JsonNull)
            put("jar_sha256", declaration["baseline_jar_sha256"] ?: JsonNull)
            put("step_seconds", declaration["step_seconds"] ?: JsonNull)
            put("steps", declaration["steps_per_case"] ?: JsonNull)
        }
        if (!Compare.sameValue(header, required)) {
            throw Rejected("input header or source/artifact identity differs")
        }
        val steps = declaration["steps_per_case"]?.intOrNull() ?: 0
        val expectedCounts = mapOf("inputs" to 1, "event" to 3 * steps, "state" to steps)
        val declaredCounts = (expected["counts"] as? JsonObject)?.mapValues { it.value.intOrNull() ?: -1 }
        if (declaredCounts != expectedCounts || expectedCounts.getValue("state") == 0) {
            throw Rejected("empty, skipped, or incomplete declared suite")
        }
        val rows = lines.drop(1).map { Compare.parse(it.toByteArray(Charsets.UTF_8)) }
        if (rows.size != expectedCounts.getValue("event") + expectedCounts.getValue("state")) {
            throw Rejected("incomplete executed counts")
        }
        val metricNames = ((declaration["cases"] as JsonObject)[case] as JsonObject)["metrics"]
            .let { (it as JsonObject).keys }
        val metrics = LinkedHashMap<String, LinkedHashMap<String, JsonElement>>()
        val maxima = LinkedHashMap<String, Fraction>()
        for (name in metricNames) {
            metrics[name] = linkedMapOf(
                "checked" to JsonPrimitive(0),
                "failed" to JsonPrimitive(0),
                "maximum" to JsonPrimitive("0"),
                "first_failure" to JsonNull,
            )
            maxima[name] = Fraction.of(0)
        }
        val firstPhaseEnd = ((declaration["phases"] as JsonArray)[0] as JsonArray)[2].intOrNull() ?: 0
        for (step in 1..steps) {
            val base = (step - 1) * 4
            for ((order, callback) in CALLBACKS.withIndex()) {
                val expectedRow = buildJsonObject {
                    put("kind", "event")
                    put("step", step)
                    put("order", order)
                    put("callback", callback)
                }
                if (!Compare.sameValue(rows[base + order], expectedRow)) {
                    throw Rejected("callback identity or order differs")
                }
            }
            val row = rows[base + 3]
            if (row.keys != setOf("kind", "step", "state") ||
                row["kind"]?.stringOrNull() != "state" ||
                row["step"]?.intOrNull() != step
            ) {
                throw Rejected("state identity or order differs")
            }
            val values = if (case == "weld-spring-equal") {
                weld(row["state"] as JsonObject)
            } else {
                pulley(row["state"] as JsonObject)
            }
            val phase = if (step <= firstPhaseEnd) "excitation" else "long-run"
            for ((name, bounds) in values) {
                val item = metrics.getValue(name)
                item["checked"] = JsonPrimitive((item.getValue("checked").intOrNull() ?: 0) + 1)
                if (bounds.second > maxima.getValue(name)) maxima[name] = bounds.second
                val ceiling = limit(declaration, case, name)
                if (bounds.first <= ceiling && ceiling < bounds.second) {
                    throw Rejected("physical metric straddles its limit at enclosure precision")
                }
                if (bounds.first > ceiling) {
                    item["failed"] = JsonPrimitive((item.getValue("failed").intOrNull() ?: 0) + 1)
                    if (item.getValue("first_failure") is JsonNull) {
                        item["first_failure"] = buildJsonObject {
                            put("step", step)
                            put("phase", phase)
                            put(
                                "value_enclosure",
                                JsonArray(
                                    listOf(
                                        JsonPrimitive(shown(bounds.first)),
                                        JsonPrimitive(shown(bounds.second)),
                                    ),
                                ),
                            )
                            put("limit", ceiling.toString())
                        }
                    }
                }
            }
        }
        for ((name, value) in maxima) {
            metrics.getValue(name)["maximum"] = JsonPrimitive(shown(value))
        }
        val failed = metrics.values.any { (it.getValue("failed").intOrNull() ?: 0) != 0 }
        buildJsonObject {
            put("status", if (failed) "PHYSICAL_FAILED" else "PHYSICAL_PASSED")
            put("scope", "FROZEN_BASELINE_ONLY")
            put("case", case)
            put(
                "counts",
                buildJsonObject {
                    for (key in listOf("inputs", "event", "state")) {
                        put(key, expectedCounts.getValue(key))
                    }
                },
            )
            put(
                "metrics",
                buildJsonObject {
                    metrics.forEach { (name, value) -> put(name, JsonObject(value)) }
                },
            )
        }
    } catch (error: Exception) {
        buildJsonObject {
            put("status", "INVALID")
            put("scope", "FROZEN_BASELINE_ONLY")
            put("case", case)
            put("reason", error.message.orEmpty())
        }
    }

    /** `splitlines(keepends=True)` for the JSONL stream. */
    private fun splitKeepingEnds(stream: ByteArray): List<String> {
        val lines = ArrayList<String>()
        var start = 0
        for (index in stream.indices) {
            if (stream[index] == '\n'.code.toByte()) {
                lines.add(String(stream, start, index + 1 - start, Charsets.UTF_8))
                start = index + 1
            }
        }
        if (start != stream.size) {
            lines.add(String(stream, start, stream.size - start, Charsets.UTF_8))
        }
        return lines
    }
}
