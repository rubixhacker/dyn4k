package io.github.rubixhacker.harness.android

/**
 * `tools/android-runtime/run_full.py` (pure half).
 *
 * The full installed route resolves the whole runtime dependency graph for both variants and requires
 * the staged artifacts, the exact frozen runtime identity, and the instrumentation process identity in
 * the device log. Those decisions are text and set work; the graph walk itself is host work.
 */
object RunFullContract {
    const val PROVIDER_GROUP = "io.github.rubixhacker"
    const val PROVIDER_VERSION = "0.1.0-alpha.1"

    val GRAPH_COMPONENTS: Set<String> = linkedSetOf(
        "project:full",
        "$PROVIDER_GROUP:dyn4k-android:$PROVIDER_VERSION",
        "$PROVIDER_GROUP:dyn4k-core:$PROVIDER_VERSION",
        "$PROVIDER_GROUP:dyn4k-core-android:$PROVIDER_VERSION",
        "org.jetbrains.kotlin:kotlin-stdlib:2.4.20",
        "org.jetbrains:annotations:13.0",
        "org.jetbrains.kotlin:kotlin-test-junit:2.4.20",
        "org.jetbrains.kotlin:kotlin-test:2.4.20",
        "junit:junit:4.13.2",
        "org.hamcrest:hamcrest-core:1.3",
        "com.google.errorprone:error_prone_annotations:2.50.0",
    )

    val GRAPH_EDGES: Set<String> = linkedSetOf(
        "project:full $PROVIDER_GROUP:dyn4k-android:$PROVIDER_VERSION",
        "project:full $PROVIDER_GROUP:dyn4k-core-android:$PROVIDER_VERSION",
        "project:full org.jetbrains.kotlin:kotlin-stdlib:2.4.20",
        "project:full org.jetbrains.kotlin:kotlin-test-junit:2.4.20",
        "project:full junit:junit:4.13.2",
        "project:full com.google.errorprone:error_prone_annotations:2.50.0",
        "$PROVIDER_GROUP:dyn4k-android:$PROVIDER_VERSION " +
            "$PROVIDER_GROUP:dyn4k-core:$PROVIDER_VERSION",
        "$PROVIDER_GROUP:dyn4k-android:$PROVIDER_VERSION " +
            "org.jetbrains.kotlin:kotlin-stdlib:2.4.20",
        "$PROVIDER_GROUP:dyn4k-core:$PROVIDER_VERSION " +
            "$PROVIDER_GROUP:dyn4k-core-android:$PROVIDER_VERSION",
        "$PROVIDER_GROUP:dyn4k-core-android:$PROVIDER_VERSION " +
            "org.jetbrains.kotlin:kotlin-stdlib:2.4.20",
        "org.jetbrains.kotlin:kotlin-stdlib:2.4.20 org.jetbrains:annotations:13.0",
        "org.jetbrains.kotlin:kotlin-test-junit:2.4.20 org.jetbrains.kotlin:kotlin-test:2.4.20",
        "org.jetbrains.kotlin:kotlin-test-junit:2.4.20 junit:junit:4.13.2",
        "org.jetbrains.kotlin:kotlin-test:2.4.20 org.jetbrains.kotlin:kotlin-stdlib:2.4.20",
        "junit:junit:4.13.2 org.hamcrest:hamcrest-core:1.3",
    )

    val GRAPH_ARTIFACTS: Set<String> = GRAPH_COMPONENTS -
        setOf("project:full", "$PROVIDER_GROUP:dyn4k-core:$PROVIDER_VERSION")

    val API21_FINGERPRINTS: Map<String, String> = linkedMapOf(
        "x86_64" to
            "generic_x86_64/sdk_google_phone_x86_64/generic_x86_64:5.0.2/LSY66K/6695550:eng/test-keys",
        "x86" to
            "generic_x86/sdk_google_phone_x86/generic_x86:5.0.2/LSY66K/6695550:eng/test-keys",
    )

    /**
     * `validate_runtime`: the installed emulator matches the expected API, ABI, fingerprint, and boot
     * state. API 21 uses the Google phone images; API 36 and 37 use the released emulator images.
     */
    fun validateRuntime(
        identity: Map<String, String>,
        expectedApi: String,
        expectedAbi: String,
        bootCompleted: String,
    ) {
        val fingerprint = if (expectedApi == "21") {
            API21_FINGERPRINTS[expectedAbi]
        } else {
            AndroidCorpus.FINGERPRINTS[expectedApi]
        }
        if (identity["ro.build.version.sdk"] != expectedApi ||
            identity["ro.product.cpu.abi"] != expectedAbi ||
            fingerprint == null ||
            identity["ro.build.fingerprint"] != fingerprint ||
            bootCompleted != "1"
        ) {
            throw IllegalArgumentException("wrong installed runtime: ${pyDictRepr(identity)}")
        }
    }

    /**
     * `validate_api21_process_log`: on API 21 the activity process is replaced by the instrumentation
     * process, and both start and finish events must name the same PIDs in order.
     */
    fun validateApi21ProcessLog(
        log: String,
        pkg: String,
        expectedAbi: String,
        beforePid: String,
    ): String {
        val escaped = pyRegexEscape(pkg)
        val identityFailure = "instrumentation process identity or normal shutdown missing"
        val allStarts = Regex(
            "(?m)^[A-Z]/ActivityManager\\(\\s*\\d+\\): Start proc " +
                "$escaped(?=\\s|${'$'})[^\\n]*${'$'}",
        ).findAll(log).toList()
        val activities = Regex(
            "(?m)^[A-Z]/ActivityManager\\(\\s*\\d+\\): Start proc $escaped for activity " +
                "$escaped/\\.FullActivity: [^\\n]*${'$'}",
        ).findAll(log).toList()
        val starts = Regex(
            "(?m)^[A-Z]/ActivityManager\\(\\s*\\d+\\): Start proc $escaped for added application " +
                "$escaped: [^\\n]*${'$'}",
        ).findAll(log).toList()
        val finishes = Regex(
            "(?m)^I/ActivityManager\\(\\s*\\d+\\): Force stopping $escaped " +
                "appid=(\\d+) user=\\d+: finished inst${'$'}",
        ).findAll(log).toList()
        if (allStarts.size != 2 || activities.size != 1 || starts.size != 1 ||
            allStarts[0].range.first != activities[0].range.first ||
            allStarts[1].range.first != starts[0].range.first || finishes.size != 1 ||
            beforePid.isEmpty() || !beforePid.all { it.isDigit() } ||
            activities[0].range.first >= starts[0].range.first ||
            starts[0].range.first >= finishes[0].range.first
        ) {
            throw IllegalArgumentException(identityFailure)
        }
        val activity = Regex(
            "I/ActivityManager\\(\\s*\\d+\\): Start proc $escaped for activity " +
                "$escaped/\\.FullActivity: pid=(\\d+) uid=(\\d+) gids=\\{[\\d, ]*\\} abi=(\\S+)",
        ).matchEntire(activities[0].value.trimEnd('\r'))
        if (activity == null || activity.groupValues[1] != beforePid ||
            activity.groupValues[3] != expectedAbi
        ) {
            throw IllegalArgumentException(identityFailure)
        }
        val started = Regex(
            "I/ActivityManager\\(\\s*\\d+\\): Start proc $escaped for added application " +
                "$escaped: pid=(\\d+) uid=(\\d+) gids=\\{[\\d, ]*\\} abi=(\\S+)",
        ).matchEntire(starts[0].value.trimEnd('\r'))
        if (started == null || started.groupValues[3] != expectedAbi ||
            started.groupValues[2] != activity.groupValues[2] ||
            finishes[0].groupValues[1] != started.groupValues[2]
        ) {
            throw IllegalArgumentException(identityFailure)
        }
        val killLine = "(?m)^[A-Z]/ActivityManager\\(\\s*\\d+\\): Killing [^\\n]*:$escaped/[^\\n]*${'$'}"
        val killPattern = Regex(killLine)

        fun killedPid(section: String): String {
            val lines = killPattern.findAll(section).toList()
            if (lines.size != 1) throw IllegalArgumentException(identityFailure)
            val killed = Regex(
                "I/ActivityManager\\(\\s*\\d+\\): Killing (\\d+):$escaped/\\S+ " +
                    "\\(adj \\d+\\): stop $escaped",
            ).matchEntire(lines[0].value.trimEnd('\r'))
                ?: throw IllegalArgumentException(identityFailure)
            return killed.groupValues[1]
        }

        if (killedPid(log.substring(activities[0].range.last + 1, starts[0].range.first)) != beforePid ||
            killPattern.containsMatchIn(log.substring(starts[0].range.last + 1, finishes[0].range.first)) ||
            killedPid(log.substring(finishes[0].range.last + 1)) != started.groupValues[1]
        ) {
            throw IllegalArgumentException(identityFailure)
        }
        return started.groupValues[1]
    }

    /** `api21_process_pid`: the one `ps` row for the package, or null when the process is gone. */
    fun api21ProcessPid(processList: String, pkg: String, required: Boolean = true): String? {
        val lines = pySplitLines(processList)
        val words = lines.map { splitWhitespace(it) }
        if (lines.isEmpty() || words[0].take(2) != listOf("USER", "PID") ||
            words[0].takeLast(1) != listOf("NAME")
        ) {
            throw IllegalArgumentException("API 21 app process list is invalid")
        }
        val selected = words.drop(1).filter { it.isNotEmpty() && it.last() == pkg }
        if (selected.size > 1 || (required && selected.size != 1)) {
            throw IllegalArgumentException("API 21 app process identity is missing or ambiguous")
        }
        if (selected.isEmpty()) return null
        val row = selected[0]
        if (row.size < 3 || row[1].isEmpty() || !row[1].all { it.isDigit() } ||
            pyInt(row[1]) <= 0
        ) {
            throw IllegalArgumentException("API 21 app process PID is invalid")
        }
        return row[1]
    }

    private val WHITESPACE = Regex("""\s+""")

    internal fun splitWhitespace(text: String): List<String> =
        text.split(WHITESPACE).filter { it.isNotEmpty() }
}
