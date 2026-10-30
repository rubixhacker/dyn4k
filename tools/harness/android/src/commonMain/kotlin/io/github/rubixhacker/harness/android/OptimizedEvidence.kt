package io.github.rubixhacker.harness.android

/**
 * `tools/android-runtime/optimized_evidence.py`.
 *
 * The optimized route relies on R8 shrinking the engine and rewriting the facade, so its evidence is a
 * proof about the keep rules: every rule that could pin an engine or facade subtree is rejected, and the
 * mapping, usage, and DEX inventory must show the consumer entry ran and the engine was transformed.
 */

/** Whether a keep rule pins a protected namespace, and whether a member selector is broad. */
class ClassSpec(
    val selectors: List<String>,
    val annotations: List<String>,
    val ancestry: List<String>,
    val memberBroad: Boolean,
)

object OptimizedEvidence {
    const val CASE: String =
        "io.github.rubixhacker.dyn4k.optimized.OptimizedJourneyTest#appSideWorldAndSubclassCallbacks"

    val REQUIRED_CLASSES: List<String> = listOf(
        "io.github.rubixhacker.dyn4k.optimized.OptimizedConsumer\$CountingWorld",
        "org.dyn4j.geometry.Vector2",
        "org.dyn4j.dynamics.Body",
        "org.dyn4j.world.World",
    )

    private val PROTECTED_NAMESPACES = listOf("org.dyn4j", "io.github.rubixhacker.dyn4k", "kotlin")

    val EFFECTIVE_KEEP_DIRECTIVES: Set<String> = setOf(
        "keep", "keepclassmembers", "keepclasseswithmembers", "keepnames",
        "keepclassmembernames", "keepclasseswithmembernames",
    )

    private val NON_CLASS_KEEP_DIRECTIVES: Set<String> = setOf(
        "keepattributes", "keepdirectories", "keeppackagenames", "keepparameternames",
    )

    private val CLASS_KINDS: Set<String> = setOf("class", "interface", "enum", "@interface")

    private val KEEP_OPTIONS: Set<String> = setOf(
        "allowshrinking", "allowoptimization", "allowobfuscation", "includedescriptorclasses",
        "allowaccessmodification", "allowrepackage", "allowannotationremoval",
    )

    private val CLASS_MODIFIERS: Set<String> =
        setOf("public", "private", "protected", "final", "abstract", "synthetic")

    private val MEMBER_MODIFIERS: Set<String> = setOf(
        "public", "private", "protected", "static", "final", "abstract", "native", "synthetic",
        "synchronized", "transient", "volatile", "strictfp", "bridge",
    )

    private val MEMBER_KEEP_DIRECTIVES: Set<String> = setOf(
        "keepclassmembers", "keepclasseswithmembers", "keepclassmembernames",
        "keepclasseswithmembernames",
    )

    private val CLASS_SELECTOR = Regex("""!?[\w.${'$'}*?]+""")
    private val DIRECTIVE = Regex("""-[A-Za-z][A-Za-z0-9]*""")
    private val MEMBER_MODIFIER = Regex("""!?[A-Za-z]+""")
    private val MEMBER_NAME = Regex("""[\w${'$'}*?<>]+""")
    private val MEMBER_TYPE = Regex("""[\w.${'$'}*?%\[\]<>]+""")
    private val ARGUMENT = Regex("""[\w.${'$'}*?%\[\]<>]+|\.\.\.""")
    private val WHITESPACE = Regex("""\s+""")

    /**
     * `validate_installed_case`: the one optimized case ran and every expected case is present.
     */
    fun validateInstalledCase(
        raw: String,
        processExitCode: Int,
        expectedCase: String = CASE,
    ): ParsedInstrumentation {
        val result = Evidence.parseInstrumentation(raw)
        Evidence.validateLane(result, emptySet(), setOf(expectedCase), processExitCode)
        return result
    }

    /** `validate_provider`: the resolved graph holds only the two staged dyn4k artifacts. */
    fun validateProvider(graph: String) {
        val required = listOf(
            "io.github.rubixhacker:dyn4k-android:0.1.0-alpha.1",
            "io.github.rubixhacker:dyn4k-core-android:0.1.0-alpha.1",
        )
        if (required.any { it !in graph } || "org.dyn4j:dyn4j:" in graph) {
            throw IllegalArgumentException("optimized app provider graph does not contain only staged dyn4k")
        }
    }

    /** `_pattern_covers_namespace`: whether a keep selector can pin a protected namespace. */
    fun patternCoversNamespace(pattern: String): Boolean {
        if (pattern in setOf("*", "**", "***")) return true
        if ("*" !in pattern && "?" !in pattern) return false
        if (PROTECTED_NAMESPACES.any { pattern.startsWith("$it.") }) return true
        val glob = pyRegexEscape(pattern)
            .replace("\\*\\*", ".*")
            .replace("\\*", "[^.]*")
            .replace("\\?", "[^.]")
        if (PROTECTED_NAMESPACES.any { regexFullMatch(glob, "$it.Probe") }) return true
        val firstWildcard = pattern.indexOfFirst { it == '*' || it == '?' }
        val prefix = pattern.substring(0, firstWildcard)
        return PROTECTED_NAMESPACES.any { it.startsWith(prefix) } &&
            ("**" in pattern || "." in pattern.substring(firstWildcard + 1))
    }

    /**
     * `_has_broad_member_selector`: whether a keep member block can pin members the evidence cannot
     * bound. Fails closed on selectors the Python parser does not model.
     */
    fun hasBroadMemberSelector(body: String, classKind: String, generatedEnumRule: Boolean): Boolean {
        val statements = body.split(";").map { it.trim() }.filter { it.isNotEmpty() }
        if (!body.trimEnd().endsWith(";") || statements.isEmpty()) {
            throw IllegalArgumentException("unsupported optimized R8 keep member selector")
        }
        for (statement in statements) {
            val opening = statement.indexOf('(')
            val hasArgs = opening >= 0
            val head: String
            val arguments: String?
            if (hasArgs) {
                val args = statement.substring(opening + 1)
                if (!args.endsWith(")") || "(" in args) {
                    throw IllegalArgumentException("unsupported optimized R8 keep member selector")
                }
                head = statement.substring(0, opening)
                arguments = args.dropLast(1).trim()
            } else {
                head = statement
                arguments = null
            }
            if (!arguments.isNullOrEmpty() &&
                arguments.split(",").any { !ARGUMENT.matches(it.trim()) }
            ) {
                throw IllegalArgumentException("unsupported optimized R8 keep member selector")
            }
            val tokens = head.split(WHITESPACE).filter { it.isNotEmpty() }
            if (tokens.isEmpty()) {
                throw IllegalArgumentException("unsupported optimized R8 keep member selector")
            }
            val memberName = tokens.last()
            when {
                memberName == "<methods>" || memberName == "<fields>" -> {
                    validateMemberModifiers(tokens.dropLast(1))
                    if (hasArgs) {
                        throw IllegalArgumentException("unsupported optimized R8 keep member selector")
                    }
                    val annotations = tokens.filter { it.startsWith("@") }
                    if (annotations.isNotEmpty() &&
                        !annotations.all { it.startsWith("@android.") || it.startsWith("@androidx.") }
                    ) {
                        return true
                    }
                    if ("native" !in tokens && annotations.isEmpty()) return true
                    continue
                }
                memberName == "<init>" -> {
                    validateMemberModifiers(tokens.dropLast(1))
                    if (!hasArgs) {
                        throw IllegalArgumentException("unsupported optimized R8 keep member selector")
                    }
                    if (!arguments.isNullOrEmpty() &&
                        tokens.none { it.startsWith("@android.") || it.startsWith("@androidx.") }
                    ) {
                        return true
                    }
                    continue
                }
                !MEMBER_NAME.matches(memberName) -> {
                    throw IllegalArgumentException("unsupported optimized R8 keep member selector")
                }
            }
            if (tokens.size >= 2) validateMemberModifiers(tokens.dropLast(2))
            val generatedSignature = generatedEnumRule && classKind == "enum" && hasArgs && (
                (tokens == listOf("public", "static", "**[]", "values") && arguments == "") ||
                    (tokens == listOf("public", "static", "**", "valueOf") &&
                        arguments == "java.lang.String")
                )
            if (generatedSignature) continue
            if (classKind == "enum" && memberName in setOf("values", "valueOf")) return true
            if ("*" in memberName || "?" in memberName) return true
            if (tokens.size < 2) {
                throw IllegalArgumentException("unsupported optimized R8 keep member selector")
            }
            val memberType = tokens[tokens.size - 2]
            if (!MEMBER_TYPE.matches(memberType)) {
                throw IllegalArgumentException("unsupported optimized R8 keep member selector")
            }
            if (memberType.any { it in setOf('*', '?', '%') } ||
                (!arguments.isNullOrEmpty() && arguments.any { it in setOf('*', '?', '%') }) ||
                (!arguments.isNullOrEmpty() && "..." in arguments)
            ) {
                return true
            }
        }
        return false
    }

    private fun validateMemberModifiers(tokens: List<String>) {
        for (token in tokens) {
            if (token.startsWith("@") && CLASS_SELECTOR.matches(token.substring(1))) continue
            if (!MEMBER_MODIFIER.matches(token) || token.removePrefix("!") !in MEMBER_MODIFIERS) {
                throw IllegalArgumentException("unsupported optimized R8 keep member modifier")
            }
        }
    }

    /** `_configuration_tokens`: the keep-file lexer, dropping `#` comments. */
    fun configurationTokens(configuration: String): List<String> {
        val tokens = mutableListOf<String>()
        var index = 0
        while (index < configuration.length) {
            val char = configuration[index]
            when {
                char == '#' -> {
                    val end = configuration.indexOf('\n', index)
                    index = if (end < 0) configuration.length else end + 1
                }
                char.isWhitespace() -> index += 1
                char in "{}();," -> {
                    tokens += char.toString()
                    index += 1
                }
                else -> {
                    var end = index
                    while (end < configuration.length &&
                        !configuration[end].isWhitespace() &&
                        configuration[end] !in "#{}();,"
                    ) {
                        end += 1
                    }
                    tokens += configuration.substring(index, end)
                    index = end
                }
            }
        }
        return tokens
    }

    /** `_directives`: name and body token pairs, in configuration order. */
    fun directives(configuration: String): List<Pair<String, List<String>>> {
        val tokens = configurationTokens(configuration)
        val directives = mutableListOf<Pair<String, List<String>>>()
        var index = 0
        while (index < tokens.size) {
            if (!DIRECTIVE.matches(tokens[index])) {
                throw IllegalArgumentException("unsupported optimized R8 configuration token")
            }
            val name = tokens[index].substring(1)
            val start = index + 1
            index = start
            var depth = 0
            while (index < tokens.size) {
                val token = tokens[index]
                when {
                    token == "{" -> depth += 1
                    token == "}" -> {
                        depth -= 1
                        if (depth < 0) {
                            throw IllegalArgumentException("unsupported optimized R8 keep block")
                        }
                    }
                    depth == 0 && DIRECTIVE.matches(token) -> break
                }
                index += 1
            }
            if (depth != 0) throw IllegalArgumentException("unsupported optimized R8 keep block")
            directives += name to tokens.subList(start, index)
        }
        return directives
    }

    /** `_parse_class_spec`: the selectors, annotations, ancestry, and member breadth of one rule. */
    fun parseClassSpec(name: String, tokens: List<String>): ClassSpec {
        val header: List<String>
        val members: List<String>?
        if ("{" in tokens) {
            val opening = tokens.indexOf("{")
            if (tokens.count { it == "{" } != 1 || tokens.count { it == "}" } != 1 ||
                tokens.last() != "}"
            ) {
                throw IllegalArgumentException("unsupported optimized R8 keep block")
            }
            header = tokens.subList(0, opening)
            members = tokens.subList(opening + 1, tokens.size - 1)
            if (members.isEmpty() || members.last() != ";") {
                throw IllegalArgumentException("unsupported optimized R8 keep member selector")
            }
        } else {
            if ("}" in tokens || name in MEMBER_KEEP_DIRECTIVES) {
                throw IllegalArgumentException("unsupported optimized R8 keep block")
            }
            header = tokens
            members = null
        }
        var index = 0
        while (index < header.size && header[index] == ",") {
            if (index + 1 >= header.size || header[index + 1] !in KEEP_OPTIONS || name == "if") {
                throw IllegalArgumentException("unsupported optimized R8 keep option")
            }
            index += 2
        }
        val kinds = header.indices.filter { header[it] in CLASS_KINDS }
        if (kinds.size != 1 || kinds[0] < index) {
            throw IllegalArgumentException("unsupported optimized R8 keep class selector")
        }
        val kindIndex = kinds[0]
        val prefix = header.subList(index, kindIndex)
        for (token in prefix) {
            if (token.startsWith("@") && CLASS_SELECTOR.matches(token.substring(1))) continue
            if (!MEMBER_MODIFIER.matches(token) || token.removePrefix("!") !in CLASS_MODIFIERS) {
                throw IllegalArgumentException("unsupported optimized R8 keep class modifier")
            }
        }
        val remainder = header.subList(kindIndex + 1, header.size)
        val inheritance = remainder.indices.filter {
            remainder[it] == "extends" || remainder[it] == "implements"
        }
        if (inheritance.size > 1) {
            throw IllegalArgumentException("unsupported optimized R8 keep class selector")
        }
        val selectorTokens = if (inheritance.isEmpty()) {
            remainder
        } else {
            remainder.subList(0, inheritance[0])
        }
        if (selectorTokens.isEmpty() || selectorTokens.size % 2 == 0 ||
            selectorTokens.withIndex().any { (position, token) ->
                (position % 2 == 1) != (token == ",")
            }
        ) {
            throw IllegalArgumentException("unsupported optimized R8 keep class selector")
        }
        val selectors = selectorTokens.filterIndexed { position, _ -> position % 2 == 0 }
        if (selectors.any { !CLASS_SELECTOR.matches(it) }) {
            throw IllegalArgumentException("unsupported optimized R8 keep class selector")
        }
        val ancestry = if (inheritance.isEmpty()) {
            emptyList()
        } else {
            remainder.subList(inheritance[0] + 1, remainder.size)
        }
        if (inheritance.isNotEmpty() && (ancestry.size != 1 || !CLASS_SELECTOR.matches(ancestry[0]))) {
            throw IllegalArgumentException("unsupported optimized R8 keep ancestry")
        }
        val kind = header[kindIndex]
        val memberBroad = if (members == null) {
            false
        } else {
            hasBroadMemberSelector(
                members.joinToString(" "),
                kind,
                name == "keepclassmembers" && kind == "enum" && selectors == listOf("*") &&
                    prefix.isEmpty() && ancestry.isEmpty(),
            )
        }
        return ClassSpec(selectors, prefix.filter { it.startsWith("@") }, ancestry, memberBroad)
    }

    /** `_has_broad_namespace_keep`: whether any effective rule can pin a protected namespace. */
    fun hasBroadNamespaceKeep(configuration: String): Boolean {
        var pendingCondition = false
        for ((name, tokens) in directives(configuration)) {
            if (name == "if") {
                if (pendingCondition) {
                    throw IllegalArgumentException("unsupported optimized R8 conditional keep")
                }
                parseClassSpec(name, tokens)
                pendingCondition = true
                continue
            }
            if (pendingCondition && name !in EFFECTIVE_KEEP_DIRECTIVES) {
                throw IllegalArgumentException("unsupported optimized R8 conditional keep")
            }
            if (name in NON_CLASS_KEEP_DIRECTIVES) {
                if ("{" in tokens || "}" in tokens) {
                    throw IllegalArgumentException("unsupported optimized R8 metadata option")
                }
                if (name == "keepparameternames" && tokens.isNotEmpty()) {
                    throw IllegalArgumentException("unsupported optimized R8 metadata option")
                }
                continue
            }
            if (!name.startsWith("keep")) continue
            if (name !in EFFECTIVE_KEEP_DIRECTIVES) {
                throw IllegalArgumentException("unsupported optimized R8 keep directive: -$name")
            }
            pendingCondition = false
            val spec = parseClassSpec(name, tokens)
            if (spec.selectors.any { it.startsWith("!") }) return true
            for (selector in spec.selectors) {
                if (!patternCoversNamespace(selector)) continue
                if (selector !in setOf("*", "**", "***")) return true
                if (spec.annotations.isNotEmpty() &&
                    !spec.annotations.all {
                        it.startsWith("@android.") || it.startsWith("@androidx.")
                    }
                ) {
                    return true
                }
                if (spec.ancestry.isNotEmpty() &&
                    !spec.ancestry.all { it.startsWith("android.") || it.startsWith("androidx.") }
                ) {
                    return true
                }
                if (spec.annotations.isNotEmpty() || spec.ancestry.isNotEmpty()) continue
                if (name in setOf("keep", "keepnames") || spec.memberBroad) return true
            }
        }
        if (pendingCondition) {
            throw IllegalArgumentException("unsupported optimized R8 conditional keep")
        }
        return false
    }

    /** One mapped engine class: its rewritten name and release descriptor, or null when removed. */
    class MappedClass(val name: String, val descriptor: String?)

    /**
     * `validate_r8`: the optimized keep rules, mapping, usage, and DEX inventory must show the
     * consumer entry was transformed and trimmed and the engine path was rewritten.
     */
    fun validateR8(
        configuration: String,
        mapping: String,
        usage: String,
        dexDescriptors: Set<String>,
    ): Map<String, MappedClass> {
        if (hasBroadNamespaceKeep(configuration)) {
            throw IllegalArgumentException("optimized route has a broad keep rule")
        }
        if (mapping.isBlank() || usage.isBlank() || "org.dyn4j." !in usage) {
            throw IllegalArgumentException("optimized R8 mapping or usage evidence missing")
        }
        if ("io.github.rubixhacker.dyn4k.optimized.OptimizedConsumer.run()" !in mapping ||
            "io.github.rubixhacker.dyn4k.optimized.OptimizedConsumer" !in usage
        ) {
            throw IllegalArgumentException("optimized consumer run was not transformed and trimmed")
        }
        val mapped = LinkedHashMap<String, MappedClass>()
        for (original in REQUIRED_CLASSES) {
            val pattern = Regex(
                "(?m)^${pyRegexEscape(original)} -> ([^:\\s]+):${'$'}",
            )
            val match = pattern.find(mapping)
                ?: throw IllegalArgumentException("optimized R8 mapping missing: $original")
            val target = match.groupValues[1]
            val removed = target.startsWith("R8\$\$REMOVED\$\$CLASS\$\$")
            val descriptor = if (removed) null else "L" + target.replace(".", "/") + ";"
            if (!removed && descriptor !in dexDescriptors) {
                throw IllegalArgumentException(
                    "optimized DEX class missing: $original -> $descriptor",
                )
            }
            mapped[original] = MappedClass(target, descriptor)
        }
        if (!mapped.getValue("org.dyn4j.world.World").name
                .startsWith("R8\$\$REMOVED\$\$CLASS\$\$")
        ) {
            throw IllegalArgumentException("optimized world class was not R8 merged")
        }
        if (REQUIRED_CLASSES.drop(1).none { mapped.getValue(it).name != it }) {
            throw IllegalArgumentException("optimized engine path has no R8 rename evidence")
        }
        return mapped
    }
}
