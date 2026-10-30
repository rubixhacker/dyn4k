package io.github.rubixhacker.harness.contract

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/**
 * Renders JSON exactly as Python's `json.dumps(value, sort_keys=True, separators=(",", ":"),
 * allow_nan=False)` renders it.
 *
 * Evidence digests depend on this byte sequence. Do not change the escaping or the number
 * formatting without regenerating every recorded digest.
 */
object CanonicalJson {
    fun render(value: JsonElement): String {
        val out = StringBuilder()
        write(value, out)
        return out.toString()
    }

    private fun write(value: JsonElement, out: StringBuilder) {
        when (value) {
            is JsonNull -> out.append("null")
            is JsonObject -> {
                out.append('{')
                val keys = value.keys.sortedWith(::compareCodePoints)
                keys.forEachIndexed { index, key ->
                    if (index > 0) out.append(',')
                    writeString(key, out)
                    out.append(':')
                    write(value.getValue(key), out)
                }
                out.append('}')
            }
            is JsonArray -> {
                out.append('[')
                value.forEachIndexed { index, item ->
                    if (index > 0) out.append(',')
                    write(item, out)
                }
                out.append(']')
            }
            is JsonPrimitive -> writePrimitive(value, out)
        }
    }

    private fun writePrimitive(value: JsonPrimitive, out: StringBuilder) {
        if (value.isString) {
            writeString(value.content, out)
            return
        }
        val content = value.content
        if (content == "true" || content == "false") {
            out.append(content)
            return
        }
        if (isInteger(content)) {
            out.append(content)
            return
        }
        val number = content.toDoubleOrNull()
            ?: throw IllegalArgumentException("not a JSON number: $content")
        out.append(pythonFloat(number))
    }

    private fun isInteger(content: String): Boolean =
        content.none { it == '.' || it == 'e' || it == 'E' }

    private fun writeString(value: String, out: StringBuilder) {
        out.append('"')
        for (char in value) {
            when (char) {
                '\\' -> out.append("\\\\")
                '"' -> out.append("\\\"")
                '\b' -> out.append("\\b")
                '\u000C' -> out.append("\\f")
                '\n' -> out.append("\\n")
                '\r' -> out.append("\\r")
                '\t' -> out.append("\\t")
                else -> {
                    val code = char.code
                    when {
                        code < 0x20 || code > 0x7E -> out.append("\\u").append(code.toString(16).padStart(4, '0'))
                        else -> out.append(char)
                    }
                }
            }
        }
        out.append('"')
    }

    /**
     * Formats a double as Python's `repr` formats it: the shortest round-trip digits, plain
     * notation for decimal exponents from -4 up to 15, and a signed two-digit exponent otherwise.
     */
    fun pythonFloat(value: Double): String {
        if (value.isNaN() || value.isInfinite()) {
            throw IllegalArgumentException("non-finite number cannot enter canonical JSON")
        }
        if (value == 0.0) {
            return if (1.0 / value < 0) "-0.0" else "0.0"
        }

        val negative = value < 0
        val magnitude = if (negative) -value else value
        val parts = shortestDecimalParts(magnitude)
        val digits = parts.digits.trimEnd('0').ifEmpty { "0" }
        val exponent = parts.exponent
        val sign = if (negative) "-" else ""

        if (exponent >= -4 && exponent < 16) {
            val plain = if (exponent >= 0) {
                if (digits.length <= exponent + 1) {
                    digits + "0".repeat(exponent + 1 - digits.length) + ".0"
                } else {
                    digits.substring(0, exponent + 1) + "." + digits.substring(exponent + 1)
                }
            } else {
                "0." + "0".repeat(-exponent - 1) + digits
            }
            return sign + plain
        }

        val mantissaText = if (digits.length == 1) digits else digits.substring(0, 1) + "." + digits.substring(1)
        val exponentSign = if (exponent < 0) "-" else "+"
        val exponentDigits = (if (exponent < 0) -exponent else exponent).toString().padStart(2, '0')
        return "$sign${mantissaText}e$exponentSign$exponentDigits"
    }

    /** Compares two strings by Unicode code point, as Python sorts dictionary keys. */
    fun compareCodePoints(left: String, right: String): Int {
        var leftIndex = 0
        var rightIndex = 0
        while (leftIndex < left.length && rightIndex < right.length) {
            val leftCode = left.codePointAt(leftIndex)
            val rightCode = right.codePointAt(rightIndex)
            if (leftCode != rightCode) return leftCode.compareTo(rightCode)
            leftIndex += if (leftCode > 0xFFFF) 2 else 1
            rightIndex += if (rightCode > 0xFFFF) 2 else 1
        }
        return (left.length - leftIndex).compareTo(right.length - rightIndex)
    }

    private fun String.codePointAt(index: Int): Int {
        val high = this[index]
        if (high.isHighSurrogate() && index + 1 < length && this[index + 1].isLowSurrogate()) {
            return 0x10000 + ((high.code - 0xD800) shl 10) + (this[index + 1].code - 0xDC00)
        }
        return high.code
    }
}

/** Reads JSON with the strictness of `qualify.load_json_strict`. */
object StrictJson {
    private val parser = Json

    fun load(text: String): JsonElement {
        val value = parser.parseToJsonElement(text)
        rejectConstants(value)
        return value
    }

    private fun rejectConstants(value: JsonElement) {
        when (value) {
            is JsonObject -> value.values.forEach(::rejectConstants)
            is JsonArray -> value.forEach(::rejectConstants)
            is JsonNull -> Unit
            is JsonPrimitive -> {
                if (!value.isString && value.content in setOf("NaN", "Infinity", "-Infinity")) {
                    throw IllegalArgumentException(value.content)
                }
            }
        }
    }

    /** Returns true when every number in the value is finite. */
    fun isFinite(value: JsonElement): Boolean = when (value) {
        is JsonObject -> value.values.all(::isFinite)
        is JsonArray -> value.all(::isFinite)
        is JsonNull -> true
        is JsonPrimitive -> {
            if (value.isString || value.content == "true" || value.content == "false") {
                true
            } else {
                val number = value.content.toDoubleOrNull()
                number == null || number.isFinite()
            }
        }
    }
}
