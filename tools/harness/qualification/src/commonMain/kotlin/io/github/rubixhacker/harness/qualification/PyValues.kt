package io.github.rubixhacker.harness.qualification

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/**
 * Python value semantics that the ported qualification checks rely on.
 *
 * `qualify.py` tests decoded JSON values with Python's `isinstance`, truthiness, equality with
 * numbers, and `str()` before matching them against digest patterns. Those rules differ from
 * Kotlin's typed accessors, so they are stated once here and used everywhere else.
 */
internal object Py {
    val SHA40 = Regex("[0-9a-f]{40}")
    val SHA64 = Regex("[0-9a-f]{64}")
    val INVOCATION = Regex("[0-9a-f]{32}")

    /** `str(value)` when the value is a JSON string, otherwise null. */
    fun str(value: JsonElement?): String? = (value as? JsonPrimitive)?.takeIf { it.isString }?.content

    fun isDict(value: JsonElement?): Boolean = value is JsonObject

    fun isList(value: JsonElement?): Boolean = value is JsonArray

    fun keys(value: JsonElement?): Set<String> = (value as? JsonObject)?.keys ?: emptySet()

    /** Python truthiness of a decoded JSON value. */
    fun truthy(value: JsonElement?): Boolean = when {
        value == null || value is JsonNull -> false
        value is JsonObject -> value.isNotEmpty()
        value is JsonArray -> value.isNotEmpty()
        value is JsonPrimitive && value.isString -> value.content.isNotEmpty()
        value is JsonPrimitive -> when (value.content) {
            "true" -> true
            "false" -> false
            else -> (value.content.toDoubleOrNull() ?: 0.0) != 0.0
        }
        else -> true
    }

    /** Python `value == target` for an integer target, where `True` equals `1`. */
    fun equalsInt(value: JsonElement?, target: Long): Boolean = when {
        value is JsonPrimitive && !value.isString -> when (value.content) {
            "true" -> target == 1L
            "false" -> target == 0L
            else -> value.content.toDoubleOrNull() == target.toDouble()
        }
        else -> false
    }

    /** `type(value) is int`, which excludes booleans and every JSON float. */
    fun isInt(value: JsonElement?): Boolean {
        val primitive = value as? JsonPrimitive ?: return false
        if (primitive.isString) return false
        if (primitive.content == "true" || primitive.content == "false") return false
        val number = primitive.content
        if (number.any { it == '.' || it == 'e' || it == 'E' }) return false
        return number.toLongOrNull() != null
    }

    fun int(value: JsonElement?): Long = (value as JsonPrimitive).content.toLong()

    /** Python `bool()` over a nullable string, as used for evidence reasons. */
    fun isNonBlankString(value: String?): Boolean = value != null && value.trim().isNotEmpty()

    /** Python's `repr()` of a list of strings, for example `['a', 'b']`. */
    fun listRepr(values: List<String>): String =
        values.joinToString(", ", prefix = "[", postfix = "]") { quote(it) }

    /** Python's `repr()` of a string. */
    fun quote(value: String): String {
        val single = value.count { it == '\'' }
        val double = value.count { it == '"' }
        if (single > 0 && double == 0) {
            return "\"" + value.map { if (it == '"' || it == '\\') "\\$it" else escape(it) }.joinToString("") + "\""
        }
        return "'" + value.map { if (it == '\'' || it == '\\') "\\$it" else escape(it) }.joinToString("") + "'"
    }

    private fun escape(char: Char): String = when {
        char == '\n' -> "\\n"
        char == '\r' -> "\\r"
        char == '\t' -> "\\t"
        char.code < 0x20 || char.code == 0x7F -> "\\x" + char.code.toString(16).padStart(2, '0')
        else -> char.toString()
    }
}
