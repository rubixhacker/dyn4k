package io.github.rubixhacker.harness.numerical

import io.github.rubixhacker.harness.contract.Sha256
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/**
 * `numeric_class_witness.read_witness`: the strict reader for the class-loading witness that
 * the `-javaagent` records.
 *
 * `build_agent` stays with the Java toolchain: it needs `javac` and a byte-exact stored ZIP
 * writer, which this pass does not port.
 */
object NumericClassWitness {
    private const val SCHEMA = "class-witness/2"
    private const val BOOLEAN_SCHEMA = "class-witness/3"
    private const val MAXIMUM_BYTES = 32 * 1024 * 1024

    private val HELPERS = setOf(
        "dyn4k/witness/NumericClassWitness",
        "dyn4k/witness/NumericClassWitness\$Observer",
        "dyn4k/witness/NumericClassWitness\$1",
    )

    private val TERMINAL = Regex("END\t(OK|FAIL)\t([0-9]+)\t([0-9]{20})")
    private val DIGEST = Regex("[0-9a-f]{64}")
    private val LOADER = Regex("(?:bootstrap|system|L[1-9][0-9]*)")
    private val THREAD = Regex("java:[1-9][0-9]*")
    private val ORDINAL = Regex("[1-9][0-9]*")

    fun readWitness(
        raw: ByteArray,
        expectedClasses: Map<String, ByteArray>,
        expectedOrigins: Map<String, String>? = null,
        profile: String = "numeric",
    ): JsonObject {
        if (profile != "numeric" && profile != "boolean") {
            throw Rejected("class witness profile differs")
        }
        val schema = if (profile == "numeric") SCHEMA else BOOLEAN_SCHEMA
        if (raw.size > MAXIMUM_BYTES || raw.isEmpty() || raw[raw.size - 1] != '\n'.code.toByte()) {
            throw Rejected("class witness is incomplete or oversized")
        }
        val text = decodeAscii(raw)
        val lines = splitLines(text)
        if (lines.size < 6 || lines[0] != "BEGIN\t$schema") {
            throw Rejected("class witness start differs")
        }
        val terminal = TERMINAL.matchEntire(lines.last())
        if (terminal == null || terminal.groupValues[1] != "OK" ||
            terminal.groupValues[3].toLong() != raw.size.toLong()
        ) {
            throw Rejected("class witness terminal record differs")
        }
        val helpers = ArrayList<JsonObject>()
        for (line in lines.subList(1, 4)) {
            val fields = line.split("\t")
            if (fields.size != 4 || fields[0] != "HELPER" || fields[1] !in HELPERS ||
                fields[2] != "system" || !fields[3].startsWith("file:/")
            ) {
                throw Rejected("class witness helper record differs")
            }
            helpers.add(
                buildJsonObject {
                    put("name", fields[1])
                    put("loader", fields[2])
                    put("origin", fields[3])
                },
            )
        }
        if (helpers.map { it.getValue("name").stringOrNull() }.toSet() != HELPERS) {
            throw Rejected("class witness helper inventory differs")
        }
        val sealIndex = lines.indexOfFirst { it.startsWith("SEALED\t") }
        if (sealIndex < 0) throw Rejected("class witness seal is absent")
        if (lines[sealIndex] != "SEALED\t" + (sealIndex - 4)) {
            throw Rejected("class witness seal count differs")
        }
        val definitions = ArrayList<JsonObject>()
        val seen = LinkedHashSet<String>()
        for ((offset, line) in lines.subList(4, sealIndex).withIndex()) {
            val ordinal = offset + 1
            val fields = line.split("\t")
            if (fields.size != 7 || fields[0] != "CLASS" ||
                fields[1] != ordinal.toString()
            ) {
                throw Rejected("class witness sequence differs")
            }
            val name = fields[2]
            val digest = fields[3]
            val loader = fields[4]
            val origin = fields[5]
            val thread = fields[6]
            val expected = expectedClasses[name]
            if (expected == null || name in seen ||
                !DIGEST.matches(digest) ||
                digest != Sha256.of(expected) ||
                !LOADER.matches(loader) ||
                !origin.startsWith("file:/") ||
                !THREAD.matches(thread)
            ) {
                throw Rejected("class witness definition differs")
            }
            if (expectedOrigins != null && origin != expectedOrigins[name]) {
                throw Rejected("class witness origin differs")
            }
            seen.add(name)
            definitions.add(
                buildJsonObject {
                    put("name", name)
                    put("sha256", digest)
                    put("loader", loader)
                    put("origin", origin)
                    put("thread", thread)
                    put("sequence", ordinal)
                },
            )
        }
        if (definitions.size != terminal.groupValues[2].toInt()) {
            throw Rejected("class witness count differs")
        }
        val loadedLines = ArrayList(lines.subList(sealIndex + 1, lines.size - 1))
        var focus: JsonObject? = null
        if (profile == "boolean") {
            if (loadedLines.isEmpty() || !loadedLines.last().startsWith("FOCUS\t")) {
                throw Rejected("class witness focus terminal record differs")
            }
            val fields = loadedLines.removeAt(loadedLines.size - 1).split("\t")
            if (fields.size != 4 || fields[1] != "org/dyn4j/geometry/Transform" ||
                !LOADER.matches(fields[2]) || !ORDINAL.matches(fields[3])
            ) {
                throw Rejected("class witness focus terminal record differs")
            }
            focus = buildJsonObject {
                put("name", fields[1])
                put("loader", fields[2])
                put("ordinal", fields[3].toInt())
            }
        }
        val loaded = ArrayList<JsonObject>()
        for ((offset, line) in loadedLines.withIndex()) {
            val ordinal = offset + 1
            val fields = line.split("\t")
            if (fields.size != 5 || fields[0] != "LOADED" || fields[1] != ordinal.toString()) {
                throw Rejected("class witness successful-load sequence differs")
            }
            if (!LOADER.matches(fields[3])) {
                throw Rejected("class witness successful loader differs")
            }
            loaded.add(
                buildJsonObject {
                    put("name", fields[2])
                    put("loader", fields[3])
                    put("origin", fields[4])
                },
            )
        }
        val byName = definitions.associateBy { it.getValue("name").stringOrNull() }
        val loadedNames = loaded.map { it.getValue("name").stringOrNull() }
        if (loaded.size != definitions.size ||
            loadedNames.toSet().size != loaded.size ||
            loadedNames.toSet() != seen ||
            loaded.any {
                val name = it.getValue("name").stringOrNull()
                val definition = byName[name] ?: return@any true
                it["loader"] != definition["loader"] || it["origin"] != definition["origin"]
            }
        ) {
            throw Rejected("class witness successful loads differ from callbacks")
        }
        if (profile == "boolean") {
            val transform = byName[focus!!.getValue("name").stringOrNull()]
            if (transform == null || transform["loader"] != focus!!["loader"] ||
                transform["sequence"]?.intOrNull() != focus!!["ordinal"]?.intOrNull()
            ) {
                throw Rejected("class witness focus definition differs")
            }
        }
        return buildJsonObject {
            put("schema", schema)
            put(
                "helpers",
                buildJsonArray { helpers.forEach { add(it) } },
            )
            put(
                "definitions",
                buildJsonArray { definitions.forEach { add(it) } },
            )
            put("loaded", buildJsonArray { loaded.forEach { add(it) } })
            put("sha256", Sha256.of(raw))
            if (profile == "boolean") put("focus", focus ?: JsonNull)
        }
    }

    private fun decodeAscii(raw: ByteArray): String {
        val builder = StringBuilder(raw.size)
        for (byte in raw) {
            val value = byte.toInt() and 0xFF
            if (value > 0x7F) throw Rejected("class witness is not ASCII")
            builder.append(value.toChar())
        }
        return builder.toString()
    }

    /** `str.splitlines()` for ASCII text. */
    private fun splitLines(text: String): List<String> {
        val lines = ArrayList<String>()
        val current = StringBuilder()
        var index = 0
        while (index < text.length) {
            val character = text[index]
            when (character) {
                '\n', '\u000B', '\u000C', '\u001C', '\u001D', '\u001E' -> {
                    lines.add(current.toString())
                    current.setLength(0)
                    index += 1
                }
                '\r' -> {
                    lines.add(current.toString())
                    current.setLength(0)
                    index += if (index + 1 < text.length && text[index + 1] == '\n') 2 else 1
                }
                else -> {
                    current.append(character)
                    index += 1
                }
            }
        }
        if (current.isNotEmpty()) lines.add(current.toString())
        return lines
    }
}
