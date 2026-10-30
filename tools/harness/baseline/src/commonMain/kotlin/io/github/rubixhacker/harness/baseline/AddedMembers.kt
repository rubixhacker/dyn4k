package io.github.rubixhacker.harness.baseline

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/**
 * `verify.added_member_gate`: every member a candidate adds — declared or inherited — that a Java 8
 * source unit compiled against the baseline could newly name, shadow, override or find ambiguous.
 *
 * The candidate's added members are read from `javap` inventories. [loadSignature] is the one impure
 * step; `:baseline`'s JVM host supplies the `javap` call, and the golden vectors replay recorded
 * inventories through it.
 */

/** One added member the gate reports. */
data class MemberRisk(
    val candidateType: String,
    val declaringType: String,
    val descriptor: String,
    val flags: List<String>,
    val origin: String,
    val kind: String,
    val declaration: String,
    val artifactSha256: String,
) {
    fun toJson(): JsonObject = buildJsonObject {
        put("candidate_type", candidateType)
        put("declaring_type", declaringType)
        put("descriptor", descriptor)
        put("flags", buildJsonArray { flags.forEach { add(JsonPrimitive(it)) } })
        put("origin", origin)
        put("kind", kind)
        put("declaration", declaration)
        put("artifact_sha256", artifactSha256)
    }
}

/** The gate's two outputs, in the order the comparison report records them. */
data class MemberAdditionResult(val risks: List<MemberRisk>, val errors: List<String>)

private val METHOD_TYPE_PARAMETERS = Regex(
    "^(?:(?:public|protected|private|static|final|abstract|synchronized|native|strictfp) )*<",
)
private val ENCLOSING_METHOD = Regex("^EnclosingMethod:", RegexOption.MULTILINE)

/** `\bfinal class\b|\benum\b|@interface`: a type Java source cannot extend. */
private val NON_SUBCLASSABLE = Regex("\\bfinal class\\b|\\benum\\b|@interface")

/** `\benum\b|@interface`: a type the gate has no source-level member to report for. */
private val ENUM_OR_ANNOTATION = Regex("\\benum\\b|@interface")
private val FINAL_CLASS = Regex("\\bfinal class\\b")

object MemberAddition {
    /**
     * Runs the gate over the already-collected [baselineSignatures] and [candidateSignatures].
     *
     * [baselineClasspath] and [candidateClasspath] are the `-classpath` values a missing signature
     * is read from, and [artifactSha256] is the digest of the candidate snapshot whose bytes the
     * risks are attributed to.
     */
    fun gate(
        selected: Set<String>,
        baselineSignatures: Map<String, String>,
        candidateSignatures: Map<String, String>,
        baselineClasspath: String,
        candidateClasspath: String,
        artifactSha256: String,
        loadSignature: (classpath: String, name: String) -> String,
    ): MemberAdditionResult {
        val caches = listOf(HashMap(baselineSignatures), HashMap(candidateSignatures))
        val classpaths = listOf(baselineClasspath, candidateClasspath)
        val risks = mutableListOf<MemberRisk>()
        val errors = mutableListOf<String>()

        fun arity(record: MemberRecord): Int =
            if (record.sourceParameters.isEmpty()) 0 else splitTopLevel(record.sourceParameters, ",").size

        fun signature(provider: Int, name: String): String {
            val cache = caches[provider]
            val cached = cache[name]
            val value = if (cached != null) cached else loadSignature(classpaths[provider], name)
            cache[name] = value
            if (value.isBlank()) throw IllegalArgumentException("empty class-file inventory: $name")
            return value
        }

        fun walk(provider: Int, name: String): List<Pair<String, MemberRecord>> {
            val result = mutableListOf<Pair<String, MemberRecord>>()
            val seen = mutableSetOf<String>()

            fun visit(typeName: String) {
                if (!seen.add(typeName)) return
                val raw = typeName.split("<", limit = 2)[0]
                val (header, records) = memberInventory(signature(provider, raw))
                val contract = typeContract(header)
                val declaration = contract.declaration
                val parameters = classTypeParameters(declaration)
                val arguments = if (typeName.length > raw.length + 1 && typeName.startsWith("$raw<")) {
                    splitTopLevel(typeName.substring(raw.length + 1, typeName.length - 1), ",")
                } else {
                    emptyList()
                }
                val mapping = parameters.zip(arguments)
                    .associate { (parameter, value) -> pySplitWhitespace(parameter)[0] to value }

                for (record in records) {
                    if (!sourceVisible(record)) continue
                    if (raw != name && record.kind == "constructor") continue
                    val flags = record.flags
                    if ("ACC_PUBLIC" !in flags && "ACC_PROTECTED" !in flags &&
                        raw.substringBeforeLast(".", "") != name.substringBeforeLast(".", "")
                    ) {
                        continue
                    }
                    var resolved = record
                    val methodGenerics = METHOD_TYPE_PARAMETERS.find(record.declaration)
                    var methodParameters: Set<String> = emptySet()
                    if (methodGenerics != null) {
                        val genericStart = methodGenerics.range.last + 1
                        val genericTail = record.declaration.substring(genericStart)
                        var depth = 1
                        var genericEnd = 0
                        for ((index, character) in genericTail.withIndex()) {
                            if (character == '<') {
                                depth++
                            } else if (character == '>') {
                                depth--
                                if (depth == 0) {
                                    genericEnd = index
                                    break
                                }
                            }
                        }
                        if (depth != 0) {
                            throw IllegalArgumentException(
                                "incomplete method type parameters: ${record.declaration}",
                            )
                        }
                        methodParameters = splitTopLevel(genericTail.substring(0, genericEnd), ",")
                            .map { pySplitWhitespace(it)[0] }
                            .toSet()
                    }
                    resolved = resolved.copy(
                        sourceParameters = substituteTypeParameters(
                            record.sourceParameters,
                            mapping,
                            methodParameters,
                        ),
                        returnType = substituteTypeParameters(record.returnType, mapping, methodParameters),
                    )
                    result.add(raw to resolved)
                }
                if (contract.superclass != null) {
                    visit(substituteTypeParameters(contract.superclass, mapping))
                } else if (" interface " !in " $declaration " && raw != "java.lang.Object") {
                    visit("java.lang.Object")
                }
                for (implemented in contract.interfaces) {
                    visit(substituteTypeParameters(implemented, mapping))
                }
            }

            visit(name)
            return result
        }

        for (name in sortedByCodePoint(selected)) {
            if (name !in baselineSignatures) continue
            if (name.endsWith(".package-info") ||
                ENCLOSING_METHOD.containsMatchIn(baselineSignatures.getValue(name))
            ) {
                continue
            }
            if (name !in candidateSignatures) {
                val header = typeHeader(baselineSignatures.getValue(name))
                if (header != null &&
                    !privateNestedType(baselineSignatures.getValue(name), name) &&
                    !header.startsWith("public ") && !header.startsWith("protected ") &&
                    !header.startsWith("private ") &&
                    !NON_SUBCLASSABLE.containsMatchIn(header)
                ) {
                    errors.add("$name: missing same-package subclassable baseline type")
                }
                continue
            }
            val baselineMembers: List<Pair<String, MemberRecord>>
            val candidateMembers: List<Pair<String, MemberRecord>>
            val baselineFinal: Boolean
            try {
                val (expectedHeader, _) = memberInventory(signature(0, name))
                if (expectedHeader.startsWith("private ") ||
                    privateNestedType(signature(0, name), name)
                ) {
                    continue
                }
                if (ENUM_OR_ANNOTATION.containsMatchIn(expectedHeader)) continue
                baselineFinal = FINAL_CLASS.containsMatchIn(expectedHeader)
                baselineMembers = walk(0, name)
                candidateMembers = walk(1, name)
            } catch (error: IllegalArgumentException) {
                errors.add("$name: ${error.message}")
                continue
            } catch (error: CommandFailure) {
                errors.add("$name: ${error.message}")
                continue
            }
            for ((owner, record) in candidateMembers) {
                val prior = baselineMembers.filter {
                    it.second.kind == record.kind && it.second.name == record.name
                }
                var matched = false
                when (record.kind) {
                    "field" -> matched = prior.any { it.second.descriptor == record.descriptor }
                    "constructor" -> matched = prior.any { it.second.parameters == record.parameters }
                    else -> matched = prior.any {
                        it.second.sourceParameters == record.sourceParameters &&
                            it.second.returnType == record.returnType
                    }
                }
                if (matched) {
                    val newlyDeclared = owner == name && !prior.any {
                        it.first == name && it.second.sourceParameters == record.sourceParameters &&
                            it.second.returnType == record.returnType
                    }
                    if (!newlyDeclared) continue
                    val changedInherited = prior.any {
                        it.first != name && it.second.sourceParameters == record.sourceParameters &&
                            it.second.returnType == record.returnType &&
                            (
                                ("ACC_FINAL" in record.flags) != ("ACC_FINAL" in it.second.flags) ||
                                    ("ACC_STATIC" in record.flags) != ("ACC_STATIC" in it.second.flags)
                                )
                    }
                    if (!changedInherited || (baselineFinal && record.kind == "method")) continue
                }
                if (baselineFinal && record.kind != "field" && "ACC_STATIC" !in record.flags) {
                    val compatible = prior.any {
                        "ACC_VARARGS" in it.second.flags || "ACC_VARARGS" in record.flags ||
                            arity(it.second) == arity(record)
                    }
                    if (!compatible) continue
                }
                risks.add(
                    MemberRisk(
                        candidateType = name,
                        declaringType = owner,
                        descriptor = record.descriptor,
                        flags = record.flags,
                        origin = if (name == owner) "declared" else "inherited",
                        kind = record.kind,
                        declaration = record.declaration,
                        artifactSha256 = artifactSha256,
                    ),
                )
            }
        }
        return MemberAdditionResult(risks, errors)
    }
}
