package io.github.rubixhacker.harness.android

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/**
 * `json.dumps` in the forms the Android tools write.
 *
 * Every receipt records `json.dumps(value, indent=2, sort_keys=True) + "\n"` and its digest, so the
 * writer must reproduce Python's bytes: two-space indentation, sorted object keys, `", "` between
 * items of a compact container, `": "` after a key, and `\uXXXX` for every character outside
 * space..`~`.
 */
object PyJson {
    /** `json.dumps(value, indent=2, sort_keys=True)`. */
    fun prettySorted(value: JsonElement): String = render(value, indent = 2, level = 0, sortKeys = true)

    /** `json.dumps(value)` with Python's default `", "` and `": "` separators. */
    fun compact(value: JsonElement): String = render(value, indent = null, level = 0, sortKeys = false)

    /** `json.dumps(value, sort_keys=True)`, the form the command-line tools print. */
    fun compactSorted(value: JsonElement): String = render(value, indent = null, level = 0, sortKeys = true)

    private fun render(
        value: JsonElement,
        indent: Int?,
        level: Int,
        sortKeys: Boolean,
    ): String = when (value) {
        is JsonNull -> "null"
        is JsonPrimitive -> primitive(value)
        is JsonArray -> if (value.isEmpty()) {
            "[]"
        } else {
            join(value.map { render(it, indent, level + 1, sortKeys) }, indent, level, "[", "]")
        }
        is JsonObject -> {
            val entries = if (sortKeys) value.entries.sortedBy { it.key } else value.entries.toList()
            if (entries.isEmpty()) {
                "{}"
            } else {
                join(
                    entries.map { (key, element) ->
                        string(key) + ": " + render(element, indent, level + 1, sortKeys)
                    },
                    indent,
                    level,
                    "{",
                    "}",
                )
            }
        }
    }

    private fun join(
        items: List<String>,
        indent: Int?,
        level: Int,
        opening: String,
        closing: String,
    ): String {
        if (indent == null) return items.joinToString(", ", opening, closing)
        val pad = " ".repeat(indent * (level + 1))
        val outer = " ".repeat(indent * level)
        return items.joinToString(",\n$pad", opening + "\n" + pad, "\n" + outer + closing)
    }

    private fun primitive(value: JsonPrimitive): String = when {
        value is JsonNull -> "null"
        value.isString -> string(value.content)
        else -> value.content
    }

    /** Python's `json.encoder.py_encode_basestring_ascii`. */
    internal fun string(text: String): String {
        val builder = StringBuilder()
        builder.append('"')
        for (char in text) {
            when {
                char == '"' -> builder.append("\\\"")
                char == '\\' -> builder.append("\\\\")
                char == '\n' -> builder.append("\\n")
                char == '\r' -> builder.append("\\r")
                char == '\t' -> builder.append("\\t")
                char == '\b' -> builder.append("\\b")
                char == '\u000c' -> builder.append("\\f")
                char.code in 0x20..0x7e -> builder.append(char)
                else -> builder.append("\\u").append(char.code.toString(16).padStart(4, '0'))
            }
        }
        builder.append('"')
        return builder.toString()
    }
}
