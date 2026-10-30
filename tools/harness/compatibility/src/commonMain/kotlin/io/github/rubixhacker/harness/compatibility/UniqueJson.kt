package io.github.rubixhacker.harness.compatibility

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/**
 * Reads JSON the way `full_ci.load_json_unique` does: with a duplicate-key check that Python's
 * `json.loads(object_pairs_hook=unique_pairs)` performs.
 *
 * Numbers become integral [JsonPrimitive] values when they have no fraction or exponent, matching
 * the Python integers these reports carry; any other number is a double.
 */
object UniqueJson {
    fun parse(text: String): JsonElement = Reader(text).document()

    private class Reader(private val text: String) {
        private var index = 0

        fun document(): JsonElement {
            val value = value()
            whitespace()
            if (index != text.length) fail("extra data")
            return value
        }

        private fun value(): JsonElement {
            whitespace()
            if (index >= text.length) fail("expecting value")
            return when (val char = text[index]) {
                '{' -> obj()
                '[' -> array()
                '"' -> JsonPrimitive(string())
                't' -> literal("true", JsonPrimitive(true))
                'f' -> literal("false", JsonPrimitive(false))
                'n' -> literal("null", JsonNull)
                else -> if (char == '-' || char.isDigit()) number() else fail("expecting value")
            }
        }

        private fun obj(): JsonObject {
            index++
            val result = linkedMapOf<String, JsonElement>()
            whitespace()
            if (peek() == '}') {
                index++
                return JsonObject(result)
            }
            while (true) {
                whitespace()
                if (peek() != '"') fail("expecting property name")
                val key = string()
                if (key in result) throw IllegalArgumentException("duplicate JSON key: $key")
                whitespace()
                if (peek() != ':') fail("expecting ':'")
                index++
                result[key] = value()
                whitespace()
                when (peek()) {
                    ',' -> index++
                    '}' -> {
                        index++
                        return JsonObject(result)
                    }
                    else -> fail("expecting ',' or '}'")
                }
            }
        }

        private fun array(): JsonArray {
            index++
            val result = mutableListOf<JsonElement>()
            whitespace()
            if (peek() == ']') {
                index++
                return JsonArray(result)
            }
            while (true) {
                result.add(value())
                whitespace()
                when (peek()) {
                    ',' -> index++
                    ']' -> {
                        index++
                        return JsonArray(result)
                    }
                    else -> fail("expecting ',' or ']'")
                }
            }
        }

        private fun string(): String {
            index++
            val out = StringBuilder()
            while (true) {
                if (index >= text.length) fail("unterminated string")
                when (val char = text[index]) {
                    '"' -> {
                        index++
                        return out.toString()
                    }
                    '\\' -> {
                        index++
                        if (index >= text.length) fail("unterminated escape")
                        when (val escape = text[index]) {
                            '"' -> out.append('"')
                            '\\' -> out.append('\\')
                            '/' -> out.append('/')
                            'b' -> out.append('\b')
                            'f' -> out.append('\u000C')
                            'n' -> out.append('\n')
                            'r' -> out.append('\r')
                            't' -> out.append('\t')
                            'u' -> {
                                if (index + 4 >= text.length) fail("invalid \\u escape")
                                val code = text.substring(index + 1, index + 5).toIntOrNull(16)
                                    ?: fail("invalid \\u escape")
                                out.append(code.toChar())
                                index += 4
                            }
                            else -> fail("invalid escape '$escape'")
                        }
                        index++
                    }
                    else -> {
                        out.append(char)
                        index++
                    }
                }
            }
        }

        private fun number(): JsonElement {
            val start = index
            if (peek() == '-') index++
            while (index < text.length && (text[index].isDigit() || text[index] in ".eE+-")) index++
            val raw = text.substring(start, index)
            val integral = raw.none { it == '.' || it == 'e' || it == 'E' }
            return if (integral) {
                val value = raw.toLongOrNull() ?: fail("invalid number")
                JsonPrimitive(value)
            } else {
                val value = raw.toDoubleOrNull() ?: fail("invalid number")
                JsonPrimitive(value)
            }
        }

        private fun literal(token: String, value: JsonElement): JsonElement {
            if (!text.startsWith(token, index)) fail("expecting value")
            index += token.length
            return value
        }

        private fun whitespace() {
            while (index < text.length && text[index] in " \t\r\n") index++
        }

        private fun peek(): Char {
            if (index >= text.length) fail("unexpected end")
            return text[index]
        }

        private fun fail(message: String): Nothing =
            throw IllegalArgumentException("$message at character $index")
    }
}

/** One XML element: its tag, its attributes, and the elements it contains directly. */
internal class XmlNode(
    val tag: String,
    val attributes: Map<String, String>,
    val children: List<XmlNode>,
)

/**
 * Reads the well-formed JUnit XML that Gradle and `PinnedCorpusReport` write, which is the only input
 * `java_corpus.read_xml` and `full_ci.validate_xml` accept.
 */
internal object MiniXml {
    fun parse(text: String): XmlNode {
        val children = mutableListOf<XmlNode>()
        val reader = Reader(text, children)
        reader.document()
        return children.singleOrNull() ?: throw IllegalArgumentException("XML document has no single root")
    }

    private class Reader(private val text: String, private val roots: MutableList<XmlNode>) {
        private var index = 0

        fun document() {
            while (index < text.length) {
                if (text.startsWith("<?", index)) {
                    skipPast("?>")
                } else if (text.startsWith("<!--", index)) {
                    skipPast("-->")
                } else if (text.startsWith("<!", index)) {
                    skipPast(">")
                } else if (text[index] == '<') {
                    roots.add(element())
                } else {
                    index++
                }
            }
        }

        private fun element(): XmlNode {
            index++ // '<'
            val tag = name()
            val attributes = linkedMapOf<String, String>()
            while (true) {
                whitespace()
                if (index >= text.length) fail("unterminated tag")
                if (text.startsWith("/>", index)) {
                    index += 2
                    return XmlNode(tag, attributes, emptyList())
                }
                if (text[index] == '>') {
                    index++
                    break
                }
                val attribute = name()
                whitespace()
                if (index >= text.length || text[index] != '=') fail("attribute without value")
                index++
                whitespace()
                if (index >= text.length || text[index] !in "\"'") fail("unquoted attribute")
                val quote = text[index]
                index++
                val start = index
                while (index < text.length && text[index] != quote) index++
                attributes[attribute] = unescape(text.substring(start, index))
                index++
            }
            val children = mutableListOf<XmlNode>()
            while (true) {
                if (index >= text.length) fail("unterminated element")
                if (text.startsWith("<!--", index)) {
                    skipPast("-->")
                } else if (text.startsWith("<![CDATA[", index)) {
                    skipPast("]]>")
                } else if (text.startsWith("</", index)) {
                    index += 2
                    val closing = name()
                    if (closing != tag) fail("mismatched closing tag")
                    whitespace()
                    if (index >= text.length || text[index] != '>') fail("unterminated closing tag")
                    index++
                    return XmlNode(tag, attributes, children)
                } else if (text[index] == '<') {
                    children.add(element())
                } else {
                    index++
                }
            }
        }

        private fun name(): String {
            val start = index
            while (index < text.length && (text[index].isLetterOrDigit() || text[index] in "_.:-")) {
                index++
            }
            if (start == index) fail("empty name")
            return text.substring(start, index)
        }

        private fun unescape(value: String): String {
            if ('&' !in value) return value
            val out = StringBuilder()
            var cursor = 0
            while (cursor < value.length) {
                val char = value[cursor]
                if (char != '&') {
                    out.append(char)
                    cursor++
                    continue
                }
                val end = value.indexOf(';', cursor)
                if (end < 0) fail("unterminated entity")
                val entity = value.substring(cursor + 1, end)
                out.append(
                    when {
                        entity == "amp" -> '&'
                        entity == "lt" -> '<'
                        entity == "gt" -> '>'
                        entity == "quot" -> '"'
                        entity == "apos" -> '\''
                        entity.startsWith("#x") || entity.startsWith("#X") ->
                            entity.substring(2).toIntOrNull(16)?.toChar() ?: fail("invalid entity")
                        entity.startsWith("#") ->
                            entity.substring(1).toIntOrNull()?.toChar() ?: fail("invalid entity")
                        else -> fail("unknown entity")
                    },
                )
                cursor = end + 1
            }
            return out.toString()
        }

        private fun skipPast(marker: String) {
            val end = text.indexOf(marker, index)
            if (end < 0) fail("unterminated declaration")
            index = end + marker.length
        }

        private fun whitespace() {
            while (index < text.length && text[index].isWhitespace()) index++
        }

        private fun fail(message: String): Nothing =
            throw IllegalArgumentException("$message at character $index")
    }
}
