package io.github.rubixhacker.harness.migration

import io.github.rubixhacker.harness.contract.CanonicalJson

/**
 * Renders [PyValue] exactly as Python's `json.dumps` renders it.
 *
 * Every receipt, evidence file, and command-line summary in the migration tooling is written with
 * `json.dumps`, and retained evidence carries their SHA-256 digests. Do not change the indentation,
 * the key order, the escaping, or the number formatting without regenerating that evidence.
 */
object PyJson {
    /**
     * `json.dumps(value, indent=2)` when [indent] is set, `json.dumps(value)` otherwise.
     *
     * [sortKeys] selects `sort_keys=True`, which orders object keys by Unicode code point.
     */
    fun render(value: PyValue, indent: Int? = 2, sortKeys: Boolean = false): String {
        val out = StringBuilder()
        write(value, out, indent, 0, sortKeys)
        return out.toString()
    }

    /** `json.dumps(value, indent=2) + "\n"`, the form every evidence file is written in. */
    fun prettyLine(value: PyValue): String = render(value, 2) + "\n"

    /** `json.dumps(value, indent=2, sort_keys=True) + "\n"`. */
    fun prettySortedLine(value: PyValue): String = render(value, 2, sortKeys = true) + "\n"

    /** `json.dumps(value)` with Python's default separators, as the command line prints it. */
    fun compact(value: PyValue): String = render(value, null)

    /** `json.dumps(value, sort_keys=True)` with Python's default separators. */
    fun compactSorted(value: PyValue): String = render(value, null, sortKeys = true)

    private fun write(value: PyValue, out: StringBuilder, indent: Int?, level: Int, sortKeys: Boolean) {
        when (value) {
            PyValue.Null -> out.append("null")
            is PyValue.Bool -> out.append(if (value.value) "true" else "false")
            is PyValue.Int -> out.append(value.value)
            is PyValue.Real -> {
                if (value.value.isNaN() || value.value.isInfinite()) {
                    throw MigrationFailure("Out of range float values are not JSON compliant")
                }
                out.append(CanonicalJson.pythonFloat(value.value))
            }
            is PyValue.Text -> writeString(value.value, out)
            is PyValue.Seq -> if (value.items.isEmpty()) {
                out.append("[]")
            } else {
                out.append('[')
                value.items.forEachIndexed { index, item ->
                    if (index > 0) out.append(if (indent == null) ", " else ",")
                    newline(out, indent, level + 1)
                    write(item, out, indent, level + 1, sortKeys)
                }
                newline(out, indent, level)
                out.append(']')
            }
            is PyValue.Map -> if (value.entries.isEmpty()) {
                out.append("{}")
            } else {
                out.append('{')
                val keys = if (sortKeys) {
                    value.entries.keys.sortedWith(CanonicalJson::compareCodePoints)
                } else {
                    value.entries.keys.toList()
                }
                keys.forEachIndexed { index, key ->
                    if (index > 0) out.append(if (indent == null) ", " else ",")
                    newline(out, indent, level + 1)
                    writeString(key, out)
                    out.append(": ")
                    write(value.entries.getValue(key), out, indent, level + 1, sortKeys)
                }
                newline(out, indent, level)
                out.append('}')
            }
        }
    }

    private fun newline(out: StringBuilder, indent: Int?, level: Int) {
        if (indent == null) return
        out.append('\n')
        repeat(indent * level) { out.append(' ') }
    }

    /** Python's `json.dumps` string escaping: always ASCII, lowercase `\\uXXXX` escapes. */
    private fun writeString(value: String, out: StringBuilder) {
        out.append('"')
        for (char in value) {
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
        }
        out.append('"')
    }
}

/** The failure the Python tools raise as `ValueError`; `main` prints its message to stderr. */
class MigrationFailure(message: String) : RuntimeException(message)
