package io.github.rubixhacker.harness.baseline

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/** The two `javap -v` readings `verify.type_header`, `surface` and `member_inventory` perform. */

private val TYPE_HEADER = Regex(
    "^(?:(?:public|protected|private|abstract|final|sealed|strictfp) )*" +
        "(?:class|interface|enum|@interface) ",
)
private val INDENTED = Regex("^  \\S")
private val DECLARED_NAME = Regex("(?:^|\\s)(?:class|interface|enum|@interface) ([^< ]+)")
private val FLAG = Regex("ACC_[A-Z_]+")

/** `verify.type_header`: the type declaration line of a `javap` surface, or null. */
fun typeHeader(signature: String): String? =
    pySplitLines(signature).map { pyStrip(it) }.firstOrNull { TYPE_HEADER.containsMatchIn(it) }

/** One member of a `jpublic`/`protected` surface: the name and parameter types that key it. */
data class MemberKey(val name: String, val parameterTypes: String)

/** `verify.surface`: the header and the members a source unit can name. */
data class ApiSurface(val header: String, val members: Map<MemberKey, List<String>>)

/**
 * `verify.surface(signature, include_package=False)`.
 *
 * A private type, or a type outside the requested visibility, has no surface. Members keep their
 * `javap` declaration plus ` descriptor: <descriptor>`, the exact text the comparison reports.
 */
fun surface(signature: String, includePackage: Boolean = false): ApiSurface? {
    val rawLines = pySplitLines(signature)
    val lines = rawLines.map { pyStrip(it) }
    var header = typeHeader(signature) ?: return null
    if (header.startsWith("private ")) return null
    if (!includePackage && !header.startsWith("public ") && !header.startsWith("protected ")) return null
    header = Regex("\\s+").replace(header, " ")
    val members = linkedMapOf<MemberKey, MutableList<String>>()
    for (index in lines.indices) {
        if (!INDENTED.containsMatchIn(rawLines[index])) continue
        val line = lines[index]
        if (!line.endsWith(";")) continue
        if (!includePackage && !line.startsWith("public ") && !line.startsWith("protected ")) continue
        if (includePackage && (line.startsWith("private ") || line.startsWith("#"))) continue
        if (index + 1 >= lines.size || !lines[index + 1].startsWith("descriptor: ")) {
            throw IllegalArgumentException("missing descriptor for $line")
        }
        if (index + 2 >= lines.size || !lines[index + 2].startsWith("flags: ")) {
            throw IllegalArgumentException("missing flags for $line")
        }
        val flags = lines[index + 2]
        if ("ACC_BRIDGE" in flags || "ACC_SYNTHETIC" in flags) continue
        val descriptor = lines[index + 1].removePrefix("descriptor: ")
        val name = if ("(" in line) {
            pySplitWhitespace(line.substringBefore("(", "")).last()
        } else {
            pySplitWhitespace(line.dropLast(1)).last()
        }
        val parameterTypes = if ("(" in descriptor) descriptor.substringBefore(")") + ")" else ""
        val declaration = Regex("\\s+").replace(line, " ") + " descriptor: " + descriptor
        members.getOrPut(MemberKey(name, parameterTypes)) { mutableListOf() }.add(declaration)
    }
    return ApiSurface(header, members)
}

/** One class-file member record, in the field order `member_inventory` builds. */
data class MemberRecord(
    val name: String,
    val descriptor: String,
    val flags: List<String>,
    val declaration: String,
    val parameters: String,
    val sourceParameters: String,
    val returnType: String,
    val kind: String,
) {
    fun toJson(): JsonObject = buildJsonObject {
        put("name", name)
        put("descriptor", descriptor)
        put("flags", buildJsonArray { flags.forEach { add(JsonPrimitive(it)) } })
        put("declaration", declaration)
        put("parameters", parameters)
        put("source_parameters", sourceParameters)
        put("return_type", returnType)
        put("kind", kind)
    }
}

/**
 * `verify.member_inventory`: every class-file member, including private and synthetic ones, with
 * the descriptor, flags, source-level parameters and return type.
 */
fun memberInventory(signature: String): Pair<String, List<MemberRecord>> {
    val header = typeHeader(signature)
        ?: throw IllegalArgumentException("class-file type header is missing")
    val declaredName = DECLARED_NAME.find(header)?.groupValues?.get(1)
        ?: throw IllegalArgumentException("class-file type name is missing")
    val rawLines = pySplitLines(signature)
    val records = mutableListOf<MemberRecord>()
    var inBody = false
    var opened = false
    var closed = false
    for (index in rawLines.indices) {
        val raw = rawLines[index]
        if (raw == "{") {
            inBody = true
            opened = true
            continue
        }
        if (raw == "}") {
            inBody = false
            closed = true
        }
        if (!inBody) continue
        if (!INDENTED.containsMatchIn(raw)) continue
        val declaration = pyStrip(raw)
        if (!declaration.endsWith(";") || declaration.endsWith("{};")) continue
        if (index + 2 >= rawLines.size) {
            throw IllegalArgumentException("incomplete class-file member: $declaration")
        }
        val descriptorLine = pyStrip(rawLines[index + 1])
        val flagsLine = pyStrip(rawLines[index + 2])
        if (!descriptorLine.startsWith("descriptor: ") || !flagsLine.startsWith("flags: ")) {
            throw IllegalArgumentException("class-file descriptor or flags missing: $declaration")
        }
        val descriptor = descriptorLine.removePrefix("descriptor: ")
        val flags = FLAG.findAll(flagsLine).map { it.value }.toList()
        if (descriptor.isEmpty()) {
            throw IllegalArgumentException("empty class-file descriptor: $declaration")
        }
        val method = "(" in descriptor
        val name = if (method) {
            pySplitWhitespace(declaration.substringBefore("(", "")).last()
        } else {
            pySplitWhitespace(declaration.dropLast(1)).last()
        }
        val constructor = method && name == declaredName
        val parameters = if (method) descriptor.substringBefore(")") + ")" else ""
        // `javap` prints a varargs parameter with an ellipsis; Java source cannot write one.
        val sourceParameters = if (method) {
            declaration.substringAfter("(", "").rsplitPython(")", 1)[0].replace("...", "[]")
        } else {
            ""
        }
        val returnType = if (method && !constructor) {
            pySplitWhitespace(declaration.substringBefore("(", "").rsplitPython(name, 1)[0]).last()
        } else {
            ""
        }
        records.add(
            MemberRecord(
                name = name,
                descriptor = descriptor,
                flags = flags,
                declaration = declaration,
                parameters = parameters,
                sourceParameters = sourceParameters,
                returnType = returnType,
                kind = if (constructor) "constructor" else if (method) "method" else "field",
            ),
        )
    }
    if (!opened || !closed) throw IllegalArgumentException("class-file member inventory is incomplete")
    return header to records
}

/**
 * Python `str.rsplit(separator, maxsplit)`. `String.substringBeforeLast` returns its fallback when
 * the separator is absent, where Python returns the whole string.
 */
internal fun String.rsplitPython(separator: String, maxSplit: Int): List<String> {
    if (maxSplit <= 0 || separator.isEmpty()) return listOf(this)
    val parts = mutableListOf<String>()
    var rest = this
    var splits = 0
    while (splits < maxSplit) {
        val index = rest.lastIndexOf(separator)
        if (index < 0) break
        parts.add(0, rest.substring(index + separator.length))
        rest = rest.substring(0, index)
        splits++
    }
    parts.add(0, rest)
    return parts
}

/** Python `str.partition(separator)[2]`: the text after the first separator, or "". */
internal fun String.partitionAfter(separator: String): String {
    val index = indexOf(separator)
    return if (index < 0) "" else substring(index + separator.length)
}
