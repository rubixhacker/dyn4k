package io.github.rubixhacker.harness.compatibility

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject

/** The two `javap -v` readers `execution_probe.declarations` needs from `tools/baseline/verify.py`. */
interface SurfaceOracle {
    val binarySha256: String

    /** The type header and the public/protected members of a strict `javap` surface. */
    fun surface(verbose: String): Pair<String, Map<Pair<String, String>, List<String>>>?

    /** The type header and every class-file member record of a verbose `javap` surface. */
    fun memberInventory(verbose: String): Pair<String, List<JsonObject>>
}

/**
 * The parts of `tools/baseline/verify.py` that the compatibility probes read: `type_header`,
 * `surface`, and `member_inventory`, ported here because `:compatibility` may not depend on the
 * unported baseline tooling.
 */
object BaselineOracle : SurfaceOracle {
    override val binarySha256 = "204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e"

    private val HEADER = Regex(
        "^(?:(?:public|protected|private|abstract|final|sealed|strictfp) )*" +
            "(?:class|interface|enum|@interface) ",
    )
    private val INDENTED = Regex("^  \\S")
    private val DECLARED_NAME = Regex("(?:^|\\s)(?:class|interface|enum|@interface) ([^< ]+)")
    private val FLAG = Regex("ACC_[A-Z_]+")

    private fun typeHeader(signature: String): String? =
        pySplitLines(signature).map { it.trim() }.firstOrNull { HEADER.containsMatchIn(it) }

    override fun surface(verbose: String): Pair<String, Map<Pair<String, String>, List<String>>>? {
        val rawLines = pySplitLines(verbose)
        val lines = rawLines.map { it.trim() }
        var header = typeHeader(verbose) ?: return null
        if (header.startsWith("private ") || !header.startsWith("public ") && !header.startsWith("protected ")) {
            return null
        }
        header = header.replace(Regex("\\s+"), " ")
        val members = linkedMapOf<Pair<String, String>, MutableList<String>>()
        for (index in lines.indices) {
            if (!INDENTED.containsMatchIn(rawLines[index])) continue
            val line = lines[index]
            if (!line.endsWith(";") || (!line.startsWith("public ") && !line.startsWith("protected "))) {
                continue
            }
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
                line.substringBefore("(").split(" ").last()
            } else {
                line.dropLast(1).split(" ").last()
            }
            val parameterTypes = if ("(" in descriptor) descriptor.substringBefore(")") + ")" else ""
            val declaration = line.replace(Regex("\\s+"), " ") + " descriptor: " + descriptor
            members.getOrPut(name to parameterTypes) { mutableListOf() }.add(declaration)
        }
        return header to members
    }

    override fun memberInventory(verbose: String): Pair<String, List<JsonObject>> {
        val header = typeHeader(verbose)
            ?: throw IllegalArgumentException("class-file type header is missing")
        val declaredName = DECLARED_NAME.find(header)?.groupValues?.get(1)
            ?: throw IllegalArgumentException("class-file type name is missing")
        val rawLines = pySplitLines(verbose)
        val records = mutableListOf<JsonObject>()
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
            val declaration = raw.trim()
            if (!declaration.endsWith(";") || declaration.endsWith("{};")) continue
            if (index + 2 >= rawLines.size) {
                throw IllegalArgumentException("incomplete class-file member: $declaration")
            }
            val descriptorLine = rawLines[index + 1].trim()
            val flagsLine = rawLines[index + 2].trim()
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
                declaration.substringBefore("(").split(" ").last()
            } else {
                declaration.dropLast(1).split(" ").last()
            }
            val constructor = method && name == declaredName
            val parameters = if (method) descriptor.substringBefore(")") + ")" else ""
            val sourceParameters = if (method) {
                declaration.substringAfter("(", "").substringBeforeLast(")")
            } else {
                ""
            }.replace("...", "[]")
            val returnType = if (method && !constructor) {
                declaration.substringBefore("(").substringBeforeLast(name, "").split(" ").last()
            } else {
                ""
            }
            records.add(
                buildJsonObject {
                    put("name", JsonPrimitive(name))
                    put("descriptor", JsonPrimitive(descriptor))
                    put("flags", buildJsonArray { flags.forEach { add(JsonPrimitive(it)) } })
                    put("declaration", JsonPrimitive(declaration))
                    put("parameters", JsonPrimitive(parameters))
                    put("source_parameters", JsonPrimitive(sourceParameters))
                    put("return_type", JsonPrimitive(returnType))
                    put(
                        "kind",
                        JsonPrimitive(
                            if (constructor) "constructor" else if (method) "method" else "field",
                        ),
                    )
                },
            )
        }
        if (!opened || !closed) {
            throw IllegalArgumentException("class-file member inventory is incomplete")
        }
        return header to records
    }
}
