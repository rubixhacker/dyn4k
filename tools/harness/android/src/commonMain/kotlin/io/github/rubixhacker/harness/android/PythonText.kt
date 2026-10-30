package io.github.rubixhacker.harness.android

/**
 * Python text behaviour the ported modules depend on.
 *
 * The Python tooling splits output with `str.splitlines`, reports failures with `repr` of lists and
 * dictionaries, and escapes regular expressions with `re.escape`. Reproducing those three exactly is
 * what keeps ported error messages and recorded evidence byte-identical.
 */

/** `str.splitlines()`: splits on every Python line boundary and drops a trailing empty line. */
internal fun pySplitLines(raw: String): List<String> {
    val lines = mutableListOf<String>()
    val current = StringBuilder()
    var index = 0
    while (index < raw.length) {
        val char = raw[index]
        when {
            char == '\r' -> {
                lines += current.toString()
                current.setLength(0)
                if (index + 1 < raw.length && raw[index + 1] == '\n') index++
            }
            char == '\n' || char == '\u000b' || char == '\u000c' || char == '\u001c' ||
                char == '\u001d' || char == '\u001e' || char == '\u0085' ||
                char == '\u2028' || char == '\u2029' -> {
                lines += current.toString()
                current.setLength(0)
            }
            else -> current.append(char)
        }
        index++
    }
    if (current.isNotEmpty()) lines += current.toString()
    return lines
}

/** `int(text)` for a base-ten literal, with Python's message when the text is not one. */
internal fun pyInt(text: String): Int {
    val trimmed = text.trim()
    val valid = trimmed.isNotEmpty() && (
        trimmed.all { it.isDigit() } ||
            (trimmed[0] == '-' && trimmed.drop(1).isNotEmpty() && trimmed.drop(1).all { it.isDigit() }) ||
            (trimmed[0] == '+' && trimmed.drop(1).isNotEmpty() && trimmed.drop(1).all { it.isDigit() })
        )
    if (!valid) throw IllegalArgumentException("invalid literal for int() with base 10: '$text'")
    return trimmed.toInt()
}

/** Python `repr` of a `str`. */
internal fun pyRepr(value: String): String {
    val hasSingle = '\'' in value
    val hasDouble = '"' in value
    val quote = if (hasSingle && !hasDouble) '"' else '\''
    val builder = StringBuilder()
    builder.append(quote)
    for (char in value) {
        when {
            char == '\\' -> builder.append("\\\\")
            char == quote -> builder.append('\\').append(char)
            char == '\n' -> builder.append("\\n")
            char == '\r' -> builder.append("\\r")
            char == '\t' -> builder.append("\\t")
            char.code < 0x20 || char.code == 0x7f -> builder.append("\\x").append(
                char.code.toString(16).padStart(2, '0'),
            )
            else -> builder.append(char)
        }
    }
    builder.append(quote)
    return builder.toString()
}

/** Python `repr` of a `list` of strings. */
internal fun pyListRepr(values: List<String>): String =
    values.joinToString(", ", "[", "]") { pyRepr(it) }

/** Python `repr` of a `dict` of strings, in insertion order. */
internal fun pyDictRepr(values: Map<String, String>): String =
    values.entries.joinToString(", ", "{", "}") { (key, value) -> "${pyRepr(key)}: ${pyRepr(value)}" }

/**
 * `re.escape`: escapes the characters Python's `_special_chars_map` covers and nothing else.
 *
 * The map is `b'()[]{}?*+-|^$\\.&~# \t\n\r\v\f'`; every other character, including `@`, `!`, and
 * `%`, passes through unescaped.
 */
internal fun pyRegexEscape(value: String): String {
    val special = "()[]{}?*+-|^$\\.&~# \t\n\r\u000b\u000c"
    val builder = StringBuilder()
    for (char in value) {
        if (char in special) builder.append('\\')
        builder.append(char)
    }
    return builder.toString()
}

/** `re.fullmatch(pattern, text)`. */
internal fun regexFullMatch(pattern: String, text: String): Boolean =
    Regex(pattern).matches(text)

/** The last non-blank line of [lines], or null when every line is blank. */
internal fun lastNonBlank(lines: List<String>): String? {
    for (index in lines.indices.reversed()) {
        if (lines[index].isNotBlank()) return lines[index]
    }
    return null
}
