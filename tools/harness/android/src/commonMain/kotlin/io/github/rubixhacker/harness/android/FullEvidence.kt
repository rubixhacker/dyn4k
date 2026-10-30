package io.github.rubixhacker.harness.android

/**
 * `tools/android-runtime/full_evidence.py`.
 *
 * The full installed route runs the whole frozen common corpus inside one instrumentation umbrella
 * case, so its evidence is the umbrella transcript plus the process identity in the device log, and,
 * for the optimized build, the R8 proof that nothing outside the frozen test entries was kept.
 */
object FullEvidence {
    const val UMBRELLA: String = "io.github.rubixhacker.dyn4k.full.FullJourneyTest#allInstalledCases"

    private val PROTECTED = listOf("org.dyn4j.", "io.github.rubixhacker.dyn4k.")

    private val X86_DEXOPT_TOKENS: List<String> = listOf(
        "class", "org.dyn4j.geometry.Matrix22", "{", "public", "double",
        "normMax", "(", ")", ";", "}",
    )

    private const val MATRIX_FAMILY = "org.dyn4j.geometry.Matrix22"

    /** `validate_full_process_log`: the app process started once and shut down normally. */
    fun validateFullProcessLog(log: String, pkg: String): String {
        val escaped = pyRegexEscape(pkg)
        val started = Regex(
            "(?m)\\bActivityManager: Start proc (\\d+):$escaped/\\S+ " +
                "for added application $escaped${'$'}",
        ).findAll(log).map { it.groupValues[1] }.toList()
        val finished = Regex(
            "(?m)\\bActivityManager: Killing (\\d+):$escaped/\\S+ \\(adj \\d+\\): " +
                "stop $escaped due to finished inst${'$'}",
        ).findAll(log).map { it.groupValues[1] }.toList()
        if (started.size != 1 || finished != started) {
            throw IllegalArgumentException(
                "instrumentation process identity or normal shutdown missing",
            )
        }
        return started[0]
    }

    /**
     * `validate_full_installed`: the umbrella case plus every frozen portable case passed, and the
     * portable tally equals the expected case list.
     */
    fun validateFullInstalled(
        raw: String,
        expectedCases: Set<String>,
        processExitCode: Int,
    ): ParsedInstrumentation {
        if (expectedCases.isEmpty()) {
            throw IllegalArgumentException("full installed case list empty")
        }
        val result = Evidence.parseInstrumentation(raw)
        Evidence.validateLane(result, expectedCases, setOf(UMBRELLA), processExitCode)
        if (result.portable.passed != expectedCases.size) {
            throw IllegalArgumentException("installed case count differs")
        }
        return result
    }

    /**
     * `validate_full_keep_scope`: no broad namespace keep, exactly the pinned Matrix22 member keep, and
     * no engine or facade class kept outside the frozen test entries.
     */
    fun validateFullKeepScope(configuration: String, allowedTestClasses: Set<String>) {
        if (OptimizedEvidence.hasBroadNamespaceKeep(configuration)) {
            throw IllegalArgumentException("full optimized route has a broad keep rule")
        }
        var dexoptMemberCount = 0
        for ((name, tokens) in OptimizedEvidence.directives(configuration)) {
            if (name == "keepclassmembers" && tokens.take(2) == X86_DEXOPT_TOKENS.take(2)) {
                dexoptMemberCount += 1
                if (tokens != X86_DEXOPT_TOKENS || dexoptMemberCount != 1) {
                    throw IllegalArgumentException(
                        "full optimized route has an unexpected Matrix22 member keep",
                    )
                }
                continue
            }
            if (name !in OptimizedEvidence.EFFECTIVE_KEEP_DIRECTIVES) continue
            val spec = OptimizedEvidence.parseClassSpec(name, tokens)
            for (selector in spec.selectors) {
                if (PROTECTED.any { selector.startsWith(it) }) {
                    if (selector !in allowedTestClasses &&
                        !selector.startsWith("io.github.rubixhacker.dyn4k.full.")
                    ) {
                        throw IllegalArgumentException(
                            "engine or facade class kept outside full test entries: $selector",
                        )
                    }
                }
            }
        }
        if (dexoptMemberCount != 1) {
            throw IllegalArgumentException("full optimized route has a missing Matrix22 member keep")
        }
    }

    /** The R8 transformation facts the full receipt records. */
    class FullR8Evidence(
        val transformedEngineClasses: Map<String, String>,
        val removedEngineClasses: Int,
        val debugDexClasses: Int,
        val releaseDexClasses: Int,
    ) {
        fun toJson(): kotlinx.serialization.json.JsonObject = kotlinx.serialization.json.buildJsonObject {
            put(
                "transformed_engine_classes",
                kotlinx.serialization.json.JsonObject(
                    transformedEngineClasses.mapValues { (_, value) ->
                        kotlinx.serialization.json.JsonPrimitive(value)
                    },
                ),
            )
            put("removed_engine_classes", kotlinx.serialization.json.JsonPrimitive(removedEngineClasses))
            put("debug_dex_classes", kotlinx.serialization.json.JsonPrimitive(debugDexClasses))
            put("release_dex_classes", kotlinx.serialization.json.JsonPrimitive(releaseDexClasses))
        }
    }

    /**
     * `validate_full_r8`: the full optimized route must show engine classes removed from usage,
     * transformed in the mapping, present under their new descriptors in the release DEX, and gone from
     * the debug inventory under their old descriptors.
     */
    fun validateFullR8(
        configuration: String,
        mapping: String,
        usage: String,
        debugDex: Set<String>,
        releaseDex: Set<String>,
        allowedTestClasses: Set<String> = emptySet(),
        minimumTransformed: Int = 10,
    ): FullR8Evidence {
        validateFullKeepScope(configuration, allowedTestClasses)
        val removedEngine = Regex("(?m)^(org\\.dyn4j\\.[\\w.${'$'}]+)(?::)?${'$'}")
            .findAll(usage)
            .map { it.groupValues[1] }
            .filter { it !in allowedTestClasses && !it.endsWith("Test") }
            .toSet()
        if (mapping.isBlank() || removedEngine.isEmpty()) {
            throw IllegalArgumentException("full R8 mapping or usage is empty")
        }
        if (debugDex.isEmpty() || releaseDex.isEmpty() || releaseDex.size >= debugDex.size) {
            throw IllegalArgumentException("full optimized DEX class inventory did not shrink")
        }
        val transformed = LinkedHashMap<String, String>()
        for (match in Regex(
            "(?m)^(org\\.dyn4j\\.[\\w.${'$'}]+) -> ([^:\\s]+):${'$'}",
        ).findAll(mapping)) {
            val original = match.groupValues[1]
            val target = match.groupValues[2]
            if (target == original || target.startsWith("R8\$\$REMOVED\$\$CLASS\$\$")) continue
            val descriptor = "L" + target.replace(".", "/") + ";"
            if (descriptor !in releaseDex) {
                throw IllegalArgumentException("mapped engine class absent from release DEX: $original")
            }
            if ("L" + original.replace(".", "/") + ";" in debugDex) {
                transformed[original] = target
            }
        }
        if (transformed.size < minimumTransformed) {
            throw IllegalArgumentException("too few transformed engine classes: ${transformed.size}")
        }
        return FullR8Evidence(transformed, removedEngine.size, debugDex.size, releaseDex.size)
    }

    /** The pinned Matrix22 family the x86 dexopt exception names; exposed for the corpus port. */
    val matrixFamily: String get() = MATRIX_FAMILY
}
