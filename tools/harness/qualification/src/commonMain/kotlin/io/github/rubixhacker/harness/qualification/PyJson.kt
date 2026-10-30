package io.github.rubixhacker.harness.qualification

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/**
 * Renders JSON exactly as Python's `json.dumps(value, indent=2)` renders it.
 *
 * Receipts, execution evidence, and publication bundles are written with this renderer, and their
 * digests are recorded as evidence. Do not change the indentation, the key order, the escaping, or
 * the number formatting without regenerating every recorded digest.
 */
object PyJson {
    fun render(value: JsonElement, indent: Int? = 2): String {
        val out = StringBuilder()
        write(value, out, indent, 0)
        return out.toString()
    }

    /** `json.dumps(value, indent=2, sort_keys=True)`, as the corpus files are written. */
    fun renderSorted(value: JsonElement): String {
        val out = StringBuilder()
        writeSorted(value, out, 2, 0)
        return out.toString()
    }

    private fun writeSorted(value: JsonElement, out: StringBuilder, indent: Int, level: Int) {
        when (value) {
            is JsonNull -> out.append("null")
            is JsonObject -> if (value.isEmpty()) {
                out.append("{}")
            } else {
                out.append('{')
                val keys = value.keys.sortedWith(CanonicalText::compare)
                for ((index, key) in keys.withIndex()) {
                    if (index > 0) out.append(',')
                    out.append('\n')
                    repeat(indent * (level + 1)) { out.append(' ') }
                    writeString(key, out)
                    out.append(": ")
                    writeSorted(value.getValue(key), out, indent, level + 1)
                }
                out.append('\n')
                repeat(indent * level) { out.append(' ') }
                out.append('}')
            }
            is JsonArray -> if (value.isEmpty()) {
                out.append("[]")
            } else {
                out.append('[')
                for ((index, item) in value.withIndex()) {
                    if (index > 0) out.append(',')
                    out.append('\n')
                    repeat(indent * (level + 1)) { out.append(' ') }
                    writeSorted(item, out, indent, level + 1)
                }
                out.append('\n')
                repeat(indent * level) { out.append(' ') }
                out.append(']')
            }
            is JsonPrimitive -> writePrimitive(value, out)
        }
    }

    /** `json.dumps(value)` with Python's default separators, as the command line prints it. */
    fun renderDefault(value: JsonElement): String {
        val out = StringBuilder()
        writeDefault(value, out)
        return out.toString()
    }

    private fun writeDefault(value: JsonElement, out: StringBuilder) {
        when (value) {
            is JsonNull -> out.append("null")
            is JsonObject -> {
                out.append('{')
                var first = true
                for ((key, item) in value) {
                    if (!first) out.append(", ")
                    first = false
                    writeString(key, out)
                    out.append(": ")
                    writeDefault(item, out)
                }
                out.append('}')
            }
            is JsonArray -> {
                out.append('[')
                for ((index, item) in value.withIndex()) {
                    if (index > 0) out.append(", ")
                    writeDefault(item, out)
                }
                out.append(']')
            }
            is JsonPrimitive -> writePrimitive(value, out)
        }
    }

    private fun write(value: JsonElement, out: StringBuilder, indent: Int?, level: Int) {
        when (value) {
            is JsonNull -> out.append("null")
            is JsonObject -> if (value.isEmpty()) {
                out.append("{}")
            } else {
                out.append('{')
                var first = true
                for ((key, item) in value) {
                    if (!first) out.append(',')
                    first = false
                    newline(out, indent, level + 1)
                    writeString(key, out)
                    out.append(": ")
                    write(item, out, indent, level + 1)
                }
                newline(out, indent, level)
                out.append('}')
            }
            is JsonArray -> if (value.isEmpty()) {
                out.append("[]")
            } else {
                out.append('[')
                for ((index, item) in value.withIndex()) {
                    if (index > 0) out.append(',')
                    newline(out, indent, level + 1)
                    write(item, out, indent, level + 1)
                }
                newline(out, indent, level)
                out.append(']')
            }
            is JsonPrimitive -> writePrimitive(value, out)
        }
    }

    private fun newline(out: StringBuilder, indent: Int?, level: Int) {
        if (indent == null) return
        out.append('\n')
        repeat(indent * level) { out.append(' ') }
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
        if (content.none { it == '.' || it == 'e' || it == 'E' }) {
            out.append(content)
            return
        }
        val number = content.toDoubleOrNull()
            ?: throw IllegalArgumentException("not a JSON number: $content")
        out.append(io.github.rubixhacker.harness.contract.CanonicalJson.pythonFloat(number))
    }

    /** Python's `json.dumps` string escaping: always ASCII, lowercase `\\uXXXX` escapes. */
    private fun writeString(value: String, out: StringBuilder) {
        out.append('"')
        var index = 0
        while (index < value.length) {
            val char = value[index]
            when {
                char == '\\' -> out.append("\\\\")
                char == '"' -> out.append("\\\"")
                char == '\b' -> out.append("\\b")
                char == '\u000C' -> out.append("\\f")
                char == '\n' -> out.append("\\n")
                char == '\r' -> out.append("\\r")
                char == '\t' -> out.append("\\t")
                char.code < 0x20 || char.code > 0x7E ->
                    out.append("\\u").append(char.code.toString(16).padStart(4, '0'))
                else -> out.append(char)
            }
            index++
        }
        out.append('"')
    }
}
