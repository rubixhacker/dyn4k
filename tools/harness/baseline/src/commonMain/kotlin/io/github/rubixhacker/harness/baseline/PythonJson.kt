package io.github.rubixhacker.harness.baseline

import io.github.rubixhacker.harness.contract.CanonicalJson
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/**
 * Renders JSON the way Python's `json.dumps` renders it with its default value rules.
 *
 * `verify.py` writes the inventory with `indent=2, sort_keys=True`, the run summary with
 * `indent=2`, and prints the comparison and the source provenance with `indent=2`. The value rules
 * are [CanonicalJson]'s; only separators, indentation and key order differ here.
 */
object PythonJson {
    /** `json.dumps(value)` and, with [sortKeys], `json.dumps(value, sort_keys=True)`. */
    fun render(value: JsonElement, sortKeys: Boolean = false): String {
        val out = StringBuilder()
        write(value, out, sortKeys)
        return out.toString()
    }

    /** `json.dumps(value, indent=indent, sort_keys=sortKeys)`. */
    fun renderIndented(value: JsonElement, sortKeys: Boolean = false, indent: Int = 2): String {
        val out = StringBuilder()
        writeIndented(value, out, sortKeys, indent, 0)
        return out.toString()
    }

    private fun write(value: JsonElement, out: StringBuilder, sortKeys: Boolean) {
        when (value) {
            is JsonNull -> out.append("null")
            is JsonObject -> {
                out.append('{')
                members(value, sortKeys).forEachIndexed { index, (key, member) ->
                    if (index > 0) out.append(", ")
                    writeString(key, out)
                    out.append(": ")
                    write(member, out, sortKeys)
                }
                out.append('}')
            }
            is JsonArray -> {
                out.append('[')
                value.forEachIndexed { index, item ->
                    if (index > 0) out.append(", ")
                    write(item, out, sortKeys)
                }
                out.append(']')
            }
            is JsonPrimitive -> writePrimitive(value, out)
        }
    }

    private fun writeIndented(
        value: JsonElement,
        out: StringBuilder,
        sortKeys: Boolean,
        indent: Int,
        depth: Int,
    ) {
        when (value) {
            is JsonNull -> out.append("null")
            is JsonObject -> {
                if (value.isEmpty()) {
                    out.append("{}")
                    return
                }
                out.append('{')
                val pad = " ".repeat(indent * (depth + 1))
                members(value, sortKeys).forEachIndexed { index, (key, member) ->
                    if (index > 0) out.append(',')
                    out.append('\n').append(pad)
                    writeString(key, out)
                    out.append(": ")
                    writeIndented(member, out, sortKeys, indent, depth + 1)
                }
                out.append('\n').append(" ".repeat(indent * depth)).append('}')
            }
            is JsonArray -> {
                if (value.isEmpty()) {
                    out.append("[]")
                    return
                }
                out.append('[')
                val pad = " ".repeat(indent * (depth + 1))
                value.forEachIndexed { index, item ->
                    if (index > 0) out.append(',')
                    out.append('\n').append(pad)
                    writeIndented(item, out, sortKeys, indent, depth + 1)
                }
                out.append('\n').append(" ".repeat(indent * depth)).append(']')
            }
            is JsonPrimitive -> writePrimitive(value, out)
        }
    }

    private fun members(value: JsonObject, sortKeys: Boolean): List<Pair<String, JsonElement>> {
        val entries = value.entries.map { it.key to it.value }
        return if (sortKeys) {
            entries.sortedWith { left, right -> CanonicalJson.compareCodePoints(left.first, right.first) }
        } else {
            entries
        }
    }

    private fun writePrimitive(value: JsonPrimitive, out: StringBuilder) {
        if (value.isString) {
            writeString(value.content, out)
            return
        }
        when (val content = value.content) {
            "true", "false" -> out.append(content)
            else -> {
                if (content.none { it == '.' || it == 'e' || it == 'E' }) {
                    out.append(content)
                } else {
                    out.append(CanonicalJson.pythonFloat(content.toDouble()))
                }
            }
        }
    }

    /** `ensure_ascii=True`: everything outside printable ASCII becomes a `\uXXXX` escape. */
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
                    if (code < 0x20 || code > 0x7E) {
                        out.append("\\u").append(code.toString(16).padStart(4, '0'))
                    } else {
                        out.append(char)
                    }
                }
            }
        }
        out.append('"')
    }
}
