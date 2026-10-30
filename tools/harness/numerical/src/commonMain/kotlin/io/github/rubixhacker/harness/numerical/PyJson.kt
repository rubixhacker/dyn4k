package io.github.rubixhacker.harness.numerical

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/**
 * The rejection the Python numerical modules raise as `Rejected(ValueError)`.
 *
 * Callers catch it by type; the message is part of the contract because several Python
 * assertions match on it.
 */
class Rejected(message: String) : IllegalArgumentException(message)

/** A failure the Python reference raises as `OverflowError`, which is not a [Rejected]. */
class PythonOverflow(message: String) : ArithmeticException(message)

/** The CPython `json.JSONDecodeError` this parser raises; `records` prefixes it with the line. */
internal class JsonDecodeFailure(message: String) : Exception(message)

/** Reads JSON text the way CPython's `json.loads` reads it, minus the accept-by-default parts. */
internal object PyJson {
    /**
     * Parses [text] as CPython's `json.loads` would with `object_pairs_hook` rejecting duplicate
     * keys and `parse_constant` rejecting `NaN`, `Infinity` and `-Infinity`.
     */
    fun load(text: String, nonfinite: String = "nonfinite JSON token"): JsonElement =
        Scanner(text, nonfinite).document()

    /** CPython's `JSONDecodeError.__str__`. */
    private fun describe(message: String, doc: String, position: Int): String {
        var lineNumber = 1
        var lineStart = 0
        for (index in 0 until minOf(position, doc.length)) {
            if (doc[index] == '\n') {
                lineNumber += 1
                lineStart = index + 1
            }
        }
        val column = position - lineStart + 1
        return "$message: line $lineNumber column $column (char $position)"
    }

    private class Scanner(private val doc: String, private val nonfinite: String) {
        private var position = 0

        fun document(): JsonElement {
            skipWhitespace()
            val value = value("Expecting value")
            skipWhitespace()
            if (position != doc.length) throw fail("Extra data", position)
            return value
        }

        private fun fail(message: String, at: Int = position): JsonDecodeFailure =
            JsonDecodeFailure(describe(message, doc, at))

        private fun skipWhitespace() {
            while (position < doc.length) {
                when (doc[position]) {
                    ' ', '\t', '\n', '\r' -> position += 1
                    else -> return
                }
            }
        }

        private fun value(missing: String): JsonElement {
            if (position >= doc.length) throw fail(missing)
            return when (val character = doc[position]) {
                '{' -> obj()
                '[' -> array()
                '"' -> JsonPrimitive(string())
                'n' -> literal("null", JsonNull, missing)
                't' -> literal("true", JsonPrimitive(true), missing)
                'f' -> literal("false", JsonPrimitive(false), missing)
                'N' -> constant("NaN", missing)
                'I' -> constant("Infinity", missing)
                '-' -> {
                    if (doc.startsWith("-Infinity", position)) constant("-Infinity", missing) else number(missing)
                }
                else -> {
                    if (character.isDigit()) number(missing) else throw fail(missing)
                }
            }
        }

        private fun constant(token: String, missing: String): Nothing {
            if (!doc.startsWith(token, position)) throw fail(missing)
            throw Rejected("$nonfinite: $token")
        }

        private fun literal(token: String, value: JsonElement, missing: String): JsonElement {
            if (!doc.startsWith(token, position)) throw fail(missing)
            position += token.length
            return value
        }

        @OptIn(kotlinx.serialization.ExperimentalSerializationApi::class)
        private fun number(missing: String): JsonElement {
            val start = position
            if (position < doc.length && (doc[position] == '-' || doc[position] == '+')) position += 1
            var digits = 0
            while (position < doc.length && doc[position].isDigit()) { position += 1; digits += 1 }
            if (digits == 0) {
                position = start
                throw fail(missing)
            }
            if (position < doc.length && doc[position] == '.') {
                position += 1
                var fraction = 0
                while (position < doc.length && doc[position].isDigit()) { position += 1; fraction += 1 }
                if (fraction == 0) {
                    position -= 1
                    throw fail("Expecting value")
                }
            }
            if (position < doc.length && (doc[position] == 'e' || doc[position] == 'E')) {
                position += 1
                if (position < doc.length && (doc[position] == '-' || doc[position] == '+')) position += 1
                var exponent = 0
                while (position < doc.length && doc[position].isDigit()) { position += 1; exponent += 1 }
                if (exponent == 0) throw fail("Expecting value")
            }
            return kotlinx.serialization.json.JsonUnquotedLiteral(doc.substring(start, position))
        }

        private fun string(): String {
            val quote = position
            position += 1
            val out = StringBuilder()
            while (true) {
                if (position >= doc.length) throw fail("Unterminated string starting at", quote)
                val character = doc[position]
                when {
                    character == '"' -> { position += 1; return out.toString() }
                    character == '\\' -> {
                        position += 1
                        if (position >= doc.length) throw fail("Unterminated string starting at", quote)
                        val escape = doc[position]
                        position += 1
                        when (escape) {
                            '"' -> out.append('"')
                            '\\' -> out.append('\\')
                            '/' -> out.append('/')
                            'b' -> out.append('\b')
                            'f' -> out.append('\u000C')
                            'n' -> out.append('\n')
                            'r' -> out.append('\r')
                            't' -> out.append('\t')
                            'u' -> {
                                if (position + 4 > doc.length) throw fail("Invalid \\uXXXX escape", position - 2)
                                var code = 0
                                for (offset in 0 until 4) {
                                    val digit = Character.digit(doc[position + offset], 16)
                                    if (digit < 0) throw fail("Invalid \\uXXXX escape", position - 2)
                                    code = code * 16 + digit
                                }
                                position += 4
                                out.append(code.toChar())
                            }
                            else -> throw fail("Invalid \\escape: ${pyRepr(escape)}", position - 2)
                        }
                    }
                    character < ' ' -> throw fail("Invalid control character ${pyRepr(character)} at", position)
                    else -> { out.append(character); position += 1 }
                }
            }
        }

        private fun obj(): JsonObject {
            position += 1
            val entries = LinkedHashMap<String, JsonElement>()
            skipWhitespace()
            if (position < doc.length && doc[position] == '}') {
                position += 1
                return JsonObject(entries)
            }
            while (true) {
                skipWhitespace()
                if (position >= doc.length || doc[position] != '"') {
                    throw fail("Expecting property name enclosed in double quotes")
                }
                val key = string()
                if (entries.containsKey(key)) throw Rejected("duplicate JSON key: $key")
                skipWhitespace()
                if (position >= doc.length || doc[position] != ':') throw fail("Expecting ':' delimiter")
                position += 1
                skipWhitespace()
                entries[key] = value("Expecting value")
                skipWhitespace()
                if (position >= doc.length) throw fail("Expecting ',' delimiter")
                when (doc[position]) {
                    ',' -> position += 1
                    '}' -> { position += 1; return JsonObject(entries) }
                    else -> throw fail("Expecting ',' delimiter")
                }
            }
        }

        private fun array(): JsonArray {
            position += 1
            val items = ArrayList<JsonElement>()
            skipWhitespace()
            if (position < doc.length && doc[position] == ']') {
                position += 1
                return JsonArray(items)
            }
            while (true) {
                skipWhitespace()
                items.add(value("Expecting value"))
                skipWhitespace()
                if (position >= doc.length) throw fail("Expecting ',' delimiter")
                when (doc[position]) {
                    ',' -> position += 1
                    ']' -> { position += 1; return JsonArray(items) }
                    else -> throw fail("Expecting ',' delimiter")
                }
            }
        }
    }

    private fun pyRepr(character: Char): String = "'" + when (character) {
        '\\' -> "\\\\"
        '\'' -> "\\'"
        else -> character.toString()
    } + "'"
}

/** Element access that mirrors Python's `dict.get` and list indexing. */
internal fun JsonElement?.orNull(): JsonElement? = if (this is JsonNull) null else this

internal fun JsonObject.field(key: String): JsonElement? = this[key].orNull()

internal fun JsonObject.list(key: String): JsonArray? = field(key) as? JsonArray

internal fun JsonObject.obj(key: String): JsonObject? = field(key) as? JsonObject

internal fun JsonElement.asObject(): JsonObject? = this as? JsonObject

internal fun JsonElement.asArray(): JsonArray? = this as? JsonArray

/** True when the primitive is JSON `true` or `false`. */
internal fun JsonElement?.isBoolean(): Boolean {
    if (this == null || this is JsonNull) return false
    val value = this as? JsonPrimitive ?: return false
    return !value.isString && (value.content == "true" || value.content == "false")
}

internal fun JsonElement?.booleanOrNull(): Boolean? {
    if (!isBoolean()) return null
    return (this as JsonPrimitive).content == "true"
}

/** True when the primitive is a JSON integer literal, as Python's `type(value) is int`. */
internal fun JsonElement?.isIntegerLiteral(): Boolean {
    if (this == null || this is JsonNull) return false
    val value = this as? JsonPrimitive ?: return false
    if (value.isString) return false
    val text = value.content
    if (text == "true" || text == "false") return false
    return text.none { it == '.' || it == 'e' || it == 'E' }
}

internal fun JsonElement?.isNumber(): Boolean {
    if (this == null || this is JsonNull) return false
    val value = this as? JsonPrimitive ?: return false
    return !value.isString && value.content != "true" && value.content != "false"
}

internal fun JsonElement?.numberOrNull(): Double? =
    if (!isNumber()) null else (this as JsonPrimitive).content.toDoubleOrNull()

internal fun JsonElement?.intOrNull(): Int? {
    if (!isIntegerLiteral()) return null
    return (this as JsonPrimitive).content.toIntOrNull()
}

internal fun JsonElement?.stringOrNull(): String? {
    val value = this as? JsonPrimitive ?: return null
    return if (value.isString) value.content else null
}

/**
 * Equates `-0.0` with `0.0` and rejects non-finite operands, as
 * `exact_consistency.same` does. Integers and floats compare by value.
 */
internal fun same(left: JsonElement?, right: JsonElement?): Boolean {
    val a = left ?: JsonNull
    val b = right ?: JsonNull
    if (a.isBoolean() || b.isBoolean()) {
        return a.isBoolean() && b.isBoolean() && a.booleanOrNull() == b.booleanOrNull()
    }
    if (a.isNumber() || b.isNumber()) {
        if (!a.isNumber() || !b.isNumber()) return false
        val x = a.numberOrNull() ?: return false
        val y = b.numberOrNull() ?: return false
        return x.isFinite() && y.isFinite() && x == y
    }
    if (a is JsonObject || b is JsonObject) {
        if (a !is JsonObject || b !is JsonObject) return false
        if (a.keys != b.keys) return false
        return a.keys.all { same(a[it], b[it]) }
    }
    if (a is JsonArray || b is JsonArray) {
        if (a !is JsonArray || b !is JsonArray) return false
        if (a.size != b.size) return false
        return a.indices.all { same(a[it], b[it]) }
    }
    if (a is JsonNull || b is JsonNull) return a is JsonNull && b is JsonNull
    val leftText = a.stringOrNull()
    val rightText = b.stringOrNull()
    if (leftText != null || rightText != null) return leftText == rightText
    return a is JsonPrimitive && b is JsonPrimitive && a.content == b.content
}

/**
 * Equates numbers through their IEEE-754 bit patterns, so `-0.0` and `0.0` differ, as
 * `receipt.exact` does.
 */
fun exact(left: JsonElement?, right: JsonElement?): Boolean {
    val a = left ?: JsonNull
    val b = right ?: JsonNull
    if (a.isNumber() && b.isNumber()) {
        val x = a.numberOrNull() ?: return false
        val y = b.numberOrNull() ?: return false
        return x.toRawBits() == y.toRawBits()
    }
    if (a is JsonObject && b is JsonObject) {
        if (a.keys != b.keys) return false
        return a.keys.all { exact(a[it], b[it]) }
    }
    if (a is JsonArray && b is JsonArray) {
        if (a.size != b.size) return false
        return a.indices.all { exact(a[it], b[it]) }
    }
    if (a is JsonNull || b is JsonNull) return a is JsonNull && b is JsonNull
    if (a is JsonPrimitive && b is JsonPrimitive) {
        if (a.isString != b.isString) return false
        if (a.isString) return a.content == b.content
        return a.content == b.content
    }
    return false
}
