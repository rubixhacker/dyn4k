package io.github.rubixhacker.harness.qualification

/**
 * The pure contract of `tools/qualification/safari_yarn_lock.py`: the tracked and generated lock
 * paths, the frozen package inventory, the context bounds, the hosted task markers, and the two
 * failure-signature predicates.
 *
 * `HOSTED_SOURCE_INPUTS` substitutes the Kotlin sources for the Python tools the reference
 * archives: the diagnostic records the bytes that *produced* it, and in this port those bytes are
 * `FullHosted.kt`/`FullHostedRuntime.kt`/`FullHostedRules.kt`, `SafariReporter`/`SafariReporterHost`,
 * and the Kotlin replacement for `safari_windows_file.py` (`SafariYarnLockHost`). The launch shell
 * script and the archived workflow document are ported with their own paths unchanged. Nothing
 * here imports Python; `full_hosted.init_script` is `FullHostedRules.initScript`.
 */
object SafariYarnLockRules {
    const val TRACKED_LOCK = "kotlin-js-store/yarn.lock"
    const val GENERATED_LOCK = "build/js/yarn.lock"

    val SOURCE_INPUTS: List<String> = listOf(
        "build.gradle.kts",
        "settings.gradle.kts",
        "gradle/wrapper/gradle-wrapper.properties",
    )

    /** `HOSTED_SOURCE_INPUTS`, with the Kotlin tools substituted for the Python ones. */
    val HOSTED_SOURCE_INPUTS: List<String> = listOf(
        "tools/harness/qualification/src/jvmMain/kotlin/io/github/rubixhacker/harness/qualification/FullHosted.kt",
        "dyn4k-core/build.gradle.kts",
        "dyn4k/build.gradle.kts",
        "tools/qualification/safari-launch.sh",
        "docs/archive/hosted-macos-workflows/safari-yarn-lock-diagnostic.yml",
        "tools/harness/qualification/src/commonMain/kotlin/io/github/rubixhacker/harness/qualification/SafariReporter.kt",
        "tools/harness/qualification/src/jvmMain/kotlin/io/github/rubixhacker/harness/qualification/SafariYarnLockHost.kt",
        "tools/qualification/safari-karma-reporter.js",
    )

    const val MAX_FILE_BYTES = 10 * 1024 * 1024
    const val MAX_PACKAGES = 128
    const val MAX_PROCESS_SECONDS = 600
    const val MAX_DRAIN_SECONDS = 5

    const val WINDOWS_KILL_JOB_ON_CLOSE = 0x00002000
    const val WINDOWS_CREATE_SUSPENDED = 0x00000004

    val REQUIRED_PACKAGES: List<String> = listOf(
        "dyn4k-dyn4k-core",
        "dyn4k-dyn4k-core-test",
        "dyn4k-dyn4k",
        "dyn4k-dyn4k-test",
    )

    /** `REQUIRED_PACKAGE_INPUTS`: the root package plus one package per required workspace. */
    val REQUIRED_PACKAGE_INPUTS: List<String> =
        listOf("build/js/package.json") + REQUIRED_PACKAGES.map { "build/js/packages/$it/package.json" }

    val CONTEXT_ROOTS: List<String> = listOf(
        "build/js/packages/dyn4k-dyn4k-core-test",
        "build/js/packages/dyn4k-dyn4k-test",
    )

    const val CONTEXT_MAX_FILES = 16
    const val CONTEXT_MAX_FILE_BYTES = 256 * 1024
    const val CONTEXT_MAX_TOTAL_BYTES = 1024 * 1024
    const val CONTEXT_MAX_ENTRIES = 2048
    const val CONTEXT_MAX_DEPTH = 16
    const val CONTEXT_MAX_SECONDS = 15
    const val CONTEXT_MAX_LAUNCHES = 8
    const val CONTEXT_MAX_RAW_ENTRIES = 128
    const val CONTEXT_MAX_UPLOAD_BYTES = 2 * 1024 * 1024
    const val CONTEXT_MAX_INVENTORY_BYTES = 256 * 1024

    const val LOCK_ERROR_LINE =
        "> Lock file was changed. Run the `kotlinUpgradeYarnLock` task to actualize lock file"

    val HOSTED_TASK_MARKERS: List<String> = listOf(
        "> Task :dyn4k-core:jsTestPackageJson",
        "> Task :dyn4k:jsTestPackageJson",
        "> Task :kotlinNpmInstall",
    )

    /**
     * `hosted_task_markers`: the three install markers plus the lock-store task, which is
     * `FAILED` when the task failed.
     */
    fun hostedTaskMarkers(exitCode: Long?): List<String> {
        val final = if (exitCode == 0L) {
            "> Task :kotlinStoreYarnLock"
        } else {
            "> Task :kotlinStoreYarnLock FAILED"
        }
        return HOSTED_TASK_MARKERS + final
    }

    private val BROWSER_FAILED =
        Regex("(?m)^> Task :(?:dyn4k-core|dyn4k):jsBrowserTest FAILED\\r?$")

    /** `safari_capture_timeout`: Safari gave up after the capture deadline. */
    fun safariCaptureTimeout(stdout: String, stderr: String): Boolean =
        "Safari has not captured in 60000 ms, killing." in stdout &&
            BROWSER_FAILED.containsMatchIn(stdout) &&
            Regex("Safari failed \\d+ times \\(timeout\\)\\. Giving up\\.").containsMatchIn(stderr) &&
            "Errors occurred during launch of browser for testing." in stderr

    /** `safari_output_overflow`: a TeamCity message exceeded the one-megabyte transport bound. */
    fun safariOutputOverflow(stdout: String, stderr: String): Boolean =
        BROWSER_FAILED.containsMatchIn(stdout) &&
            "##teamcity[testFailed name='overflow-message'" in stderr &&
            "Cannot process output: too long teamcity service message (more than 1Mb). " +
            "Event was lost." in stderr

    /**
     * `hosted_expected_files`: every archive member a hosted capture must contain.
     *
     * The tracked lock is archived twice (before and after), the generated lock and each package
     * input under `generated/`, the source inputs under `inputs/`, and the init script, both logs.
     */
    fun hostedExpectedFiles(
        configuration: String,
        trackedLock: String,
        generatedLock: String,
        sourceInputs: List<String>,
        packageInputs: List<String>,
    ): Set<String> {
        val expected = linkedSetOf(
            "$configuration/qualification.init.gradle",
            "stdout.txt",
            "stderr.txt",
            "tracked/$trackedLock",
            "tracked-after/$trackedLock",
            "generated/$generatedLock",
        )
        for (path in sourceInputs.drop(1)) expected.add("inputs/$path")
        for (path in packageInputs) expected.add("generated/$path")
        return expected
    }

    /** `full_hosted_command`: the exact Safari source command of one configuration. */
    fun fullHostedCommand(
        repository: String,
        init: String,
        configuration: String,
        invocationId: String,
        windows: Boolean = false,
    ): List<String> {
        val command = mutableListOf(
            joinPosix(repository, if (windows) "gradlew.bat" else "gradlew"),
            "--no-daemon",
            "--console=plain",
            "--rerun-tasks",
            "--init-script",
            init,
            ":dyn4k-core:jsBrowserTest",
            ":dyn4k:jsBrowserTest",
            "-PqualificationInvocationId=$invocationId",
        )
        if (configuration == "production") command.add("-PqualificationProduction=true")
        return command
    }

    /** `str(Path(a) / b)` for the wrapper path. */
    private fun joinPosix(base: String, name: String): String =
        if (base.isEmpty() || base == ".") name
        else if (base.endsWith("/")) base + name
        else "$base/$name"
}
