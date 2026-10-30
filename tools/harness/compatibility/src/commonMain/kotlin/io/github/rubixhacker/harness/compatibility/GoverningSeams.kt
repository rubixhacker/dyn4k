package io.github.rubixhacker.harness.compatibility

/**
 * The Java lane environment of the governing fixture, ported from
 * `tools/compatibility/governing_seams.py`.
 *
 * `capture`, `make`, `check`, `original_corpus`, and `main` stay unported: they compile and run the
 * fixture on two archives, analyse the JaCoCo execution archive with `javap`, and replay the
 * original Java corpus. `lane_environment` and `strip_java_tool_options_banner` are pure.
 */
object GoverningSeams {
    const val FIXTURE_PATH = "tools/compatibility/fixtures/governing/GoverningSeams.java"
    const val MAIN = "org.dyn4j.dynamics.contact.GoverningSeams"
    const val EXPECTED_OUTPUT = "governing seams passed\n"
    const val JAVA_TOOL_OPTIONS_BANNER = "Picked up JAVA_TOOL_OPTIONS: "

    /**
     * Copies [environment] and appends [additionalOptions] to any inherited `JAVA_TOOL_OPTIONS`.
     * Returns the environment and the options value, or null when both are empty.
     */
    fun laneEnvironment(
        environment: Map<String, String>,
        additionalOptions: String? = null,
    ): Pair<Map<String, String>, String?> {
        val env = environment.toMutableMap()
        val inherited = env["JAVA_TOOL_OPTIONS"].orEmpty()
        val options = listOfNotNull(
            inherited.takeIf { it.isNotEmpty() },
            additionalOptions?.takeIf { it.isNotEmpty() },
        ).joinToString(" ")
        if (options.isNotEmpty()) {
            env["JAVA_TOOL_OPTIONS"] = options
        } else {
            env.remove("JAVA_TOOL_OPTIONS")
        }
        return env to options.ifEmpty { null }
    }

    /** Removes one exact `Picked up JAVA_TOOL_OPTIONS: <options>` banner from the head. */
    fun stripJavaToolOptionsBanner(stderr: String, options: String?): String {
        if (options == null) return stderr
        val banner = JAVA_TOOL_OPTIONS_BANNER + options + "\n"
        return if (stderr.startsWith(banner)) stderr.substring(banner.length) else stderr
    }
}
