package io.github.rubixhacker.harness.baseline

/**
 * `verify.split_top_level`, `type_contract`, `source_compatible_declaration`,
 * `constructor_list_widening`, `source_visible` and `private_nested_type`.
 *
 * These are the Java 8 source-compatibility rules the comparator applies to `javap` declarations.
 */

private val LIST_OF_TYPE_PARAMETER = Regex("java\\.util\\.List<([A-Za-z_$][\\p{L}\\p{N}_$]*)>")
private val TYPE_PARAMETER_HEADER = Regex("\\b(?:class|interface|enum) [^< ]+<(.+)>$")
private val MEMBER_REFERENCE = Regex("(?<!\\.)\\b[A-Za-z_$][\\p{L}\\p{N}_$]*\\b")
private val ANY_REFERENCE = Regex("\\b[A-Za-z_$][\\p{L}\\p{N}_$]*\\b")

/** Python `re.sub(r"\bfinal ", "", value, count=1)`. */
private val FINAL_MODIFIER = Regex("\\bfinal ")
private val STATIC_MODIFIER = Regex("\\bstatic ")
private val ACCESS_MODIFIER = Regex("^(public|protected) ")

/** `verify.split_top_level`: split on [separator] while outside `<...>` depth. */
fun splitTopLevel(value: String, separator: String): List<String> {
    val parts = mutableListOf<String>()
    var depth = 0
    var start = 0
    var index = 0
    while (index < value.length) {
        when {
            value[index] == '<' -> depth++
            value[index] == '>' -> depth--
            depth == 0 && value.startsWith(separator, index) -> {
                parts.add(pyStrip(value.substring(start, index)))
                index += separator.length
                start = index
                continue
            }
        }
        index++
    }
    parts.add(pyStrip(value.substring(start)))
    return parts
}

/** `verify.type_contract`: the declaration, its superclass and its interfaces. */
data class TypeContract(
    val declaration: String,
    val superclass: String?,
    val interfaces: Set<String>,
)

fun typeContract(header: String): TypeContract {
    val declaration = header.removeSuffix(" {")
    val implemented = splitTopLevel(declaration, " implements ")
    val base = implemented[0]
    val interfaces = if (implemented.size > 1) {
        splitTopLevel(implemented[1], ",").toMutableSet()
    } else {
        mutableSetOf()
    }
    val extended = splitTopLevel(base, " extends ")
    val superclass: String?
    if (extended.size > 1) {
        if (" interface " in " ${extended[0]} ") {
            interfaces.addAll(splitTopLevel(extended[1], ","))
            superclass = null
        } else {
            superclass = extended[1]
        }
    } else {
        superclass = null
    }
    return TypeContract(extended[0], superclass, interfaces)
}

/**
 * `verify.source_compatible_declaration`: whether a Java 8 source unit written against
 * [expected] still compiles against [actual].
 */
fun sourceCompatibleDeclaration(
    expected: String,
    actual: String,
    allowFinalRemoval: Boolean = true,
    allowFinalAddition: Boolean = false,
): Boolean {
    if (expected == actual) return true
    var widened = expected
    if (expected.startsWith("protected ") && actual.startsWith("public ")) {
        widened = "public " + expected.removePrefix("protected ")
    } else if (!expected.startsWith("public ") && !expected.startsWith("protected ") &&
        (actual.startsWith("public ") || actual.startsWith("protected "))
    ) {
        widened = actual.split(" ", limit = 2)[0] + " " + expected
    }
    if (allowFinalRemoval && " final " in " $widened " && " final " !in " $actual ") {
        widened = FINAL_MODIFIER.replaceFirst(widened, "")
    }
    if (allowFinalAddition && " final " !in " $widened " && " final " in " $actual ") {
        if (" static " in " $widened ") {
            widened = STATIC_MODIFIER.replaceFirst(widened, "static final ")
        } else if (widened.startsWith("public ") || widened.startsWith("protected ")) {
                widened = ACCESS_MODIFIER.replace(widened) { match ->
                    match.groupValues[1] + " final "
                }
        } else {            widened = "final " + widened
        }
    }
    return widened == actual
}

/**
 * `verify.constructor_list_widening`: `List<T>` becoming `List<? extends T>` keeps a constructor
 * callable, and only constructors may be widened.
 */
fun constructorListWidening(expected: String, actual: String, typeParameters: Set<String>): Boolean {
    val found = LIST_OF_TYPE_PARAMETER.findAll(expected).map { it.groupValues[1] }.toSet()
    if (found.isEmpty() || !typeParameters.containsAll(found)) return false
    val widened = LIST_OF_TYPE_PARAMETER.replace(expected) { match ->
        "java.util.List<? extends " + match.groupValues[1] + ">"
    }
    return sourceCompatibleDeclaration(widened, actual)
}

/** `verify.source_visible`: whether Java source can name a class-file member. */
fun sourceVisible(record: MemberRecord): Boolean {
    if (record.flags.any { it == "ACC_PRIVATE" || it == "ACC_BRIDGE" || it == "ACC_SYNTHETIC" }) {
        return false
    }
    return !(record.kind == "method" && "-" in record.name)
}

/** `verify.private_nested_type`: whether [name] is a `private` nested class of its outer class. */
fun privateNestedType(signature: String, name: String): Boolean {
    val section = signature.partitionAfter("\nInnerClasses:\n")
    if (section.isEmpty()) return false
    val internalName = name.replace('.', '/')
    val match = Regex("=class " + Regex.escape(internalName) + "(?:\\s|$)")
    for (line in pySplitLines(section)) {
        if (!line.startsWith("  ")) break
        if (match.containsMatchIn(line)) {
            return "private" in pySplitWhitespace(line.substringBefore("#", ""))
        }
    }
    return false
}

/** The class-level type-parameter names of a declaration, in declaration order. */
internal fun classTypeParameters(declaration: String): List<String> {
    val generic = TYPE_PARAMETER_HEADER.find(declaration) ?: return emptyList()
    return splitTopLevel(generic.groupValues[1], ",")
}

/** `verify`'s `substitute` inside `walk`: leave member access alone, replace type parameters. */
internal fun substituteTypeParameters(
    value: String,
    mapping: Map<String, String>,
    protected: Set<String> = emptySet(),
): String = MEMBER_REFERENCE.replace(value) { match ->
    val token = match.value
    if (token in protected) token else mapping[token] ?: token
}

/** `candidate_interfaces`' `substitute`: replace every type-parameter occurrence. */
internal fun substituteEveryTypeParameter(value: String, mapping: Map<String, String>): String =
    ANY_REFERENCE.replace(value) { match -> mapping[match.value] ?: match.value }
