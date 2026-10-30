package io.github.rubixhacker.harness.baseline

import io.github.rubixhacker.harness.contract.CanonicalJson

/**
 * The Python string primitives the verifier depends on.
 *
 * `tools/baseline/verify.py` parses `javap` text with `str.splitlines`, `str.strip`, `str.split`
 * and `sorted`. Each one has a Unicode definition that differs from the Kotlin default, so the
 * verifier calls these helpers instead of the standard library.
 */

/** Python `str.splitlines()`: a trailing line break does not produce a final empty line. */
internal fun pySplitLines(text: String): List<String> {
    val lines = mutableListOf<String>()
    val current = StringBuilder()
    var index = 0
    while (index < text.length) {
        val char = text[index]
        val boundary = when (char) {
            '\n', '\r', '\u000B', '\u000C', '\u001C', '\u001D', '\u001E', '\u0085',
            '\u2028', '\u2029',
            -> true
            else -> false
        }
        if (boundary) {
            lines.add(current.toString())
            current.setLength(0)
            if (char == '\r' && index + 1 < text.length && text[index + 1] == '\n') index++
        } else {
            current.append(char)
        }
        index++
    }
    if (current.isNotEmpty()) lines.add(current.toString())
    return lines
}

/** Python `str.isspace()` for one character. */
private fun isPySpace(char: Char): Boolean = when (char) {
    '\t', '\n', '\u000B', '\u000C', '\r', ' ', '\u001C', '\u001D', '\u001E', '\u001F',
    '\u0085', '\u00A0', '\u1680', '\u2007', '\u202F', '\u205F', '\u3000',
    -> true
    else -> char.isWhitespace() || char in '\u2000'..'\u200A' || char == '\u2028' || char == '\u2029'
}

/** Python `str.strip()`. */
internal fun pyStrip(value: String): String = value.trim { isPySpace(it) }

/** Python `str.strip()` applied to a `javap` line list. */
internal fun pyStripLines(value: String): List<String> = pySplitLines(value).map { pyStrip(it) }

/** Python `str.split()` with no argument: split on runs of whitespace, dropping empty fields. */
internal fun pySplitWhitespace(value: String): List<String> {
    val parts = mutableListOf<String>()
    val current = StringBuilder()
    for (char in value) {
        if (isPySpace(char)) {
            if (current.isNotEmpty()) {
                parts.add(current.toString())
                current.setLength(0)
            }
        } else {
            current.append(char)
        }
    }
    if (current.isNotEmpty()) parts.add(current.toString())
    return parts
}

/** Python `sorted(values)`: code-point order, not UTF-16 code-unit order. */
internal fun sortedByCodePoint(values: Collection<String>): List<String> =
    values.sortedWith(CanonicalJson::compareCodePoints)

/**
 * The code points Python's `str.isprintable()` reports as unprintable and that are not ISO control
 * characters: separators other than the space, format characters, surrogates, private use and the
 * non-characters. `pyStr` prints everything else literally, which is why `repr("é")` is `'é'`.
 */
private val UNPRINTABLE_RANGES = listOf(
    0x00A0..0x00A0, 0x00AD..0x00AD, 0x0600..0x0605, 0x061C..0x061C, 0x06DD..0x06DD,
    0x070F..0x070F, 0x1680..0x1680, 0x180E..0x180E, 0x2000..0x200F, 0x2028..0x202F,
    0x205F..0x2064, 0x2066..0x206F, 0x3000..0x3000, 0xD800..0xDFFF, 0xE000..0xF8FF,
    0xFEFF..0xFEFF, 0xFFF9..0xFFFB, 0xFFFE..0xFFFF,
)

private fun isPythonPrintable(char: Char): Boolean =
    char == ' ' || (!char.isISOControl() && UNPRINTABLE_RANGES.none { char.code in it })

/**
 * Python `str.__repr__` for the strings a mismatch message can carry. The verifier interpolates
 * `f"{actual[1][key]}"`, which renders a list of Java declarations with single quotes.
 *
 * A Java declaration is ASCII, where this is exact. For other text it reproduces Python's
 * printability rule for the code points listed in [UNPRINTABLE_RANGES]; a code point Python treats
 * as unassigned is printed literally here.
 */
internal fun pythonStrRepr(value: String): String {
    val quote = if ('\'' in value && '"' !in value) '"' else '\''
    val out = StringBuilder()
    out.append(quote)
    for (char in value) {
        when (char) {
            '\\' -> out.append("\\\\")
            '\n' -> out.append("\\n")
            '\r' -> out.append("\\r")
            '\t' -> out.append("\\t")
            else -> when {
                char == quote -> out.append('\\').append(quote)
                isPythonPrintable(char) -> out.append(char)
                char.code < 0x100 -> out.append("\\x").append(char.code.toString(16).padStart(2, '0'))
                else -> out.append("\\u").append(char.code.toString(16).padStart(4, '0'))
            }
        }
    }
    out.append(quote)
    return out.toString()
}

/** Python `repr` of a `list[str]`. */
internal fun pythonListRepr(values: Collection<String>): String =
    values.joinToString(", ", prefix = "[", postfix = "]") { pythonStrRepr(it) }
