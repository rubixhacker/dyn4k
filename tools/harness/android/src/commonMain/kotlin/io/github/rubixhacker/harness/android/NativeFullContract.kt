package io.github.rubixhacker.harness.android

/**
 * `tools/android-native-runtime/full.py` (pure half).
 *
 * The full native route stages both publications, links six lane executables, pushes each to the task
 * emulator, and replays every frozen common case. The pin file, build commands, listing and result
 * grammar, and deployment checks are text and path work; the git, Gradle, ADB, and filesystem adapters
 * are host work.
 */

/** One case of the full common corpus manifest. */
class CorpusCase(
    val classname: String,
    val method: String,
    val module: String,
    val sourceSet: String,
)

object NativeFullContract {
    const val PIN_PATH = "tools/android-native-runtime/full-pins.json"
    const val CORPUS_PATH = "tools/qualification/full-common-corpus.json"
    const val VERSION = "0.1.0-alpha.1"

    val LANES: List<Pair<String, String>> = listOf("core", "facade", "consumer").flatMap { module ->
        listOf("debug", "optimized").map { variant -> module to variant }
    }

    val STAGE_TASKS = listOf(
        ":dyn4k-core:publishKotlinMultiplatformPublicationToStagingRepository",
        ":dyn4k:publishKotlinMultiplatformPublicationToStagingRepository",
        ":dyn4k-core:publishAndroidNativeX64PublicationToStagingRepository",
        ":dyn4k:publishAndroidNativeX64PublicationToStagingRepository",
    )

    val TEST_TASKS: List<String> = listOf("dyn4k-core", "dyn4k").flatMap { module ->
        listOf("Debug", "Release").map { build -> ":$module:link${build}TestAndroidNativeX64" }
    }

    val CONSUMER_TASKS = listOf(
        "linkDebugExecutableAndroidNativeX64",
        "linkReleaseExecutableAndroidNativeX64",
    )

    val ROOT_GRADLE = listOf(
        "./gradlew", "--no-daemon", "--max-workers=2", "--rerun-tasks", "--console=plain",
    )

    const val GUEST_REMOTE = "/data/local/tmp/dyn4k-full-{module}-{variant}"

    private val CASE_LINE = Regex("""(?m)^\[ RUN      \] ([A-Za-z_][\w.]+)${'$'}""")
    private val OK_LINE = Regex("""(?m)^\[       OK \] ([A-Za-z_][\w.]+) \(\d+ ms\)${'$'}""")
    private val PASS_LINE = Regex("""(?m)^\[  PASSED  \] (\d+) tests\.${'$'}""")
    private val TOTAL_LINE = Regex(
        """(?m)^\[==========\] (\d+) tests from \d+ test cases ran\. \(\d+ ms total\)${'$'}""",
    )
    private val FAILURE_LINE = Regex("""(?m)^\[\s*(?:FAILED|SKIPPED|DISABLED)\s*\]""")
    private val DEVICE_ROW = Regex(
        """emulator-5558[ \t]+device(?:[ \t]+[A-Za-z_][A-Za-z0-9_.-]*:[^\s]+)*[ \t]*""",
    )
    private val LIST_METHOD = Regex("""  [A-Za-z_]\w*""")
    private val LIST_SUITE = Regex("""[A-Za-z_][\w.]*\.${'$'}""")
    private val WHITESPACE = Regex("""\s+""")

    /** `expected_cases`: the frozen common cases of one root module, as `classname.method`. */
    fun expectedCases(cases: List<CorpusCase>, module: String): Set<String> {
        val sourceModule = if (module == "core") "dyn4k-core" else "dyn4k"
        return cases.filter { it.module == sourceModule && it.sourceSet == "commonTest" }
            .mapTo(linkedSetOf()) { "${it.classname}.${it.method}" }
    }

    /** `executable_path`: the linked lane executable or the staged consumer journey. */
    fun executablePath(root: String, module: String, variant: String): String {
        if (module == "consumer") {
            val build = if (variant == "debug") "debugExecutable" else "releaseExecutable"
            return "$root/consumers/android-native-runtime/build/bin/androidNativeX64/$build/journey.kexe"
        }
        val sourceModule = if (module == "core") "dyn4k-core" else "dyn4k"
        val build = if (variant == "debug") "debugTest" else "releaseTest"
        return "$root/$sourceModule/build/bin/androidNativeX64/$build/test.kexe"
    }

    /** `klib_paths`: the two staged Android Native x64 KLIBs. */
    fun klibPaths(root: String): Map<String, String> {
        val staging = "$root/build/staging-repository/io/github/rubixhacker"
        return linkedMapOf(
            "dyn4k-core" to
                "$staging/dyn4k-core-androidnativex64/$VERSION/" +
                "dyn4k-core-androidnativex64-$VERSION.klib",
            "dyn4k" to
                "$staging/dyn4k-androidnativex64/$VERSION/" +
                "dyn4k-androidnativex64-$VERSION.klib",
        )
    }

    /** `build_commands`: stage, link, and consumer build argument vectors. */
    fun buildCommands(root: String): Map<String, List<String>> {
        val consumer = listOf(
            "./gradlew", "-p", "consumers/android-native-runtime", "--no-daemon",
            "--max-workers=2", "--rerun-tasks", "--console=plain",
            "-PstagingRepository=$root/build/staging-repository",
        )
        return linkedMapOf(
            "stage" to ROOT_GRADLE + STAGE_TASKS,
            "tests" to ROOT_GRADLE + TEST_TASKS,
            "consumer" to consumer + CONSUMER_TASKS,
        )
    }

    /** `graph_commands`: the dependency queries whose sections the pin file records. */
    fun graphCommands(root: String): Map<String, List<String>> {
        val common = listOf("./gradlew", "--no-daemon", "--console=plain")
        return linkedMapOf(
            "core" to common + listOf(
                ":dyn4k-core:dependencies", "--configuration", "androidNativeX64TestCompileKlibraries",
            ),
            "facade" to common + listOf(
                ":dyn4k:dependencies", "--configuration", "androidNativeX64TestCompileKlibraries",
            ),
            "consumer" to listOf(
                "./gradlew", "-p", "consumers/android-native-runtime", "--no-daemon", "--console=plain",
                "-PstagingRepository=$root/build/staging-repository", "dependencies",
                "--configuration", "androidNativeX64CompileKlibraries",
            ),
        )
    }

    /**
     * `graph_section`: the one dependency section for [module], verified against the allowed providers.
     */
    fun graphSection(raw: String, module: String): String {
        val header = if (module == "consumer") {
            "androidNativeX64CompileKlibraries -"
        } else {
            "androidNativeX64TestCompileKlibraries -"
        }
        val lines = pySplitLines(raw)
        val starts = lines.indices.filter { lines[it].startsWith(header) }
        if (starts.size != 1) {
            throw IllegalArgumentException("missing or duplicate $module dependency graph")
        }
        var end = starts[0] + 1
        while (end < lines.size && lines[end].isNotEmpty()) end += 1
        val section = lines.subList(starts[0], end).joinToString("\n") + "\n"
        if (module == "consumer") {
            NativeReceipt.validateDependencyGraph(section)
        } else if ("org.dyn4j:dyn4j" in section || "io.github.rubixhacker:" in section) {
            throw IllegalArgumentException("root test graph has an unapproved provider")
        }
        return section
    }

    /** `parse_list`: the `--ktest_list_tests` listing as `suite.method` names. */
    fun parseList(raw: String): List<String> {
        val names = mutableListOf<String>()
        var suite: String? = null
        for (line in pySplitLines(raw)) {
            if (line.startsWith("  ")) {
                if (suite == null || !LIST_METHOD.matches(line)) {
                    throw IllegalArgumentException("native test listing has an invalid method")
                }
                names += suite + "." + line.trim()
            } else if (line.endsWith(".") && LIST_SUITE.matches(line)) {
                suite = line.dropLast(1)
            } else {
                throw IllegalArgumentException("native test listing has unexpected output")
            }
        }
        if (names.isEmpty()) {
            throw IllegalArgumentException("native test listing is empty")
        }
        return names
    }

    /** `parse_test_run`: the executed cases, agreeing with the totals and free of failures. */
    fun parseTestRun(raw: String): List<String> {
        val running = CASE_LINE.findAll(raw).map { it.groupValues[1] }.toList()
        val passed = OK_LINE.findAll(raw).map { it.groupValues[1] }.toList()
        val totals = TOTAL_LINE.findAll(raw).map { it.groupValues[1] }.toList()
        val summaries = PASS_LINE.findAll(raw).map { it.groupValues[1] }.toList()
        if (running.isEmpty() || running != passed || totals.size != 1 || summaries.size != 1 ||
            pyInt(totals[0]) != running.size || pyInt(summaries[0]) != running.size ||
            FAILURE_LINE.containsMatchIn(raw)
        ) {
            throw IllegalArgumentException("native test result lines or totals differ")
        }
        return running
    }

    /** `check_cases`: observed cases equal the expected set, each exactly once. */
    fun checkCases(observed: List<String>, expected: Set<String>): Int {
        val counts = LinkedHashMap<String, Int>()
        for (name in observed) counts[name] = (counts[name] ?: 0) + 1
        val missing = expected - counts.keys
        val extra = counts.keys - expected
        val duplicates = counts.filterValues { it != 1 }.keys
        if (missing.isNotEmpty() || extra.isNotEmpty() || duplicates.isNotEmpty()) {
            throw IllegalArgumentException(
                "native cases differ: missing=${missing.size}, extra=${extra.size}, " +
                    "duplicate=${duplicates.size}",
            )
        }
        return observed.size
    }

    /** `require_task_device`: one ready `emulator-5558` row under the listing header. */
    fun requireTaskDevice(raw: String) {
        val lines = pySplitLines(raw)
        if (lines.isEmpty() || lines[0] != "List of devices attached") {
            throw IllegalArgumentException("isolated ADB device listing header differs")
        }
        val target = lines.drop(1).filter { line ->
            val words = line.split(WHITESPACE).filter { it.isNotEmpty() }
            words.isNotEmpty() && words[0] == "emulator-5558"
        }
        if (target.size != 1 || !DEVICE_ROW.matches(target[0])) {
            throw IllegalArgumentException(
                "isolated ADB task device is absent, duplicated, or not ready",
            )
        }
    }

    /** `guest_values`: the stripped guest properties, checked against the pinned task image. */
    fun guestValues(stdout: Map<String, String>): Map<String, String> {
        val values = linkedMapOf<String, String>()
        for ((property, field) in NativeReceipt.GUEST_PROPERTIES) {
            values[field] = (stdout[property] ?: "").trim()
        }
        if (values["avd_name"] != "dyn4k_api37_play_x64" || values["api"] != "37" ||
            values["fingerprint"] != NativeReceipt.EXPECTED_FINGERPRINT ||
            values["primary_abi"] != "x86_64" || values["boot_completed"] != "1" ||
            "x86_64" !in values.getValue("abi_list").split(",")
        ) {
            throw IllegalArgumentException("stale or wrong Android Native x64 guest")
        }
        return values
    }

    /** `build_task_marker`: the Gradle console line that proves a task ran. */
    fun buildTaskMarker(task: String): String = "> Task " + (if (task.startsWith(":")) task else ":$task")

    /**
     * `validate_deployment_output`: the push reported one file, nothing failed, and the remote hash
     * equals the staged executable's.
     */
    fun validateDeploymentOutput(
        push: ByteArray,
        pushError: ByteArray,
        chmodError: ByteArray,
        remoteOut: ByteArray,
        remoteError: ByteArray,
        expectedHash: String,
    ) {
        val combined = push + pushError
        if (!combined.containsSubsequence("1 file pushed".encodeToByteArray()) ||
            combined.decodeToString().lowercase().contains("failed") ||
            chmodError.isNotEmpty() || remoteError.isNotEmpty() ||
            remoteOut.decodeToString().split(WHITESPACE).firstOrNull() != expectedHash
        ) {
            throw IllegalArgumentException("deployed executable bytes differ")
        }
    }

    /** The six lane keys, in lane order. */
    fun laneKeys(): List<String> = LANES.map { (module, variant) -> "$module-$variant" }

    private fun ByteArray.containsSubsequence(needle: ByteArray): Boolean =
        PrepareContract.indexOf(this, needle, 0) >= 0
}
