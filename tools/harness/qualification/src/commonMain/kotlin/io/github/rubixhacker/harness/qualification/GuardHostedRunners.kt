package io.github.rubixhacker.harness.qualification

/**
 * Checks that active workflows use explicit hosted Linux and Windows runners.
 *
 * GitHub-hosted macOS labels are forbidden because all Apple work runs on the self-hosted
 * `mac-mini` runner. A user-controlled `runs-on` expression fails closed.
 *
 * Ported from `tools/qualification/guard_hosted_runners.py`.
 */
object GuardHostedRunners {
    private val hostedLabel = Regex(
        "(?:ubuntu-(?:latest|22\\.04|24\\.04|26\\.04)|ubuntu-24\\.04-arm|windows-(?:latest|2022|2025))\\z",
    )
    private val selfHostedMacLabel = Regex("mac-mini\\z")
    private val macLabel = Regex("(?i)\\bmacos-[a-z0-9][a-z0-9_-]*\\b")
    private val jobHeader = Regex(" {2}([A-Za-z_][A-Za-z0-9_-]*):(?:\\s*#.*)?\\z")
    private val runnerLine = Regex(" {4}runs-on: (\\S+)(?:\\s*#.*)?\\z")
    private val runnerKey = Regex("(?:^|[\\s,{])['\"]?runs-on['\"]?\\s*:")
    private val jobsKey = Regex("^['\"]?jobs['\"]?\\s*:")

    private const val HOSTED_MACOS_ERROR = "macOS hosted label is forbidden"
    private const val RUNNER_ERROR =
        "runner must be an explicit Linux/Windows hosted label or the mac-mini self-hosted runner"

    /** Returns every error of one workflow source. An empty list means the workflow passed. */
    fun checkWorkflow(path: String, source: String): List<String> {
        val errors = mutableListOf<String>()

        val lines = source.splitLines()
        for ((index, line) in lines.withIndex()) {
            if (macLabel.containsMatchIn(line)) {
                errors.add("$path:${index + 1}: $HOSTED_MACOS_ERROR")
            }
        }

        val jobsSections = lines.indices.filter { jobsKey.containsMatchIn(lines[it]) }
        if (jobsSections.size != 1 || lines[jobsSections.single()] != "jobs:") {
            errors.add("$path: require one block-style jobs section")
            return errors
        }
        if (lines.any { line -> line.takeWhile { it == ' ' || it == '\t' }.contains('\t') }) {
            errors.add("$path: tab indentation is forbidden")
        }
        if (lines.any { it.trim() in setOf("---", "...") }) {
            errors.add("$path: multiple YAML documents are forbidden")
        }
        if (lines.any { Regex("\\s*<<\\s*:").containsMatchIn(it) }) {
            errors.add("$path: YAML merge keys are forbidden")
        }

        val jobsStart = jobsSections.single() + 1
        val jobsEnd = (jobsStart until lines.size).firstOrNull { index ->
            lines[index].isNotEmpty() && !lines[index][0].isWhitespace() && !lines[index].startsWith("#")
        } ?: lines.size

        val jobNames = mutableListOf<String>()
        val runnerCount = mutableMapOf<String, Int>()
        var currentJob: String? = null

        for ((index, line) in lines.withIndex()) {
            val number = index + 1
            if (line.trimStart().startsWith("#")) continue
            val inJobs = index in jobsStart until jobsEnd

            if (inJobs && line.startsWith("  ") && !line.startsWith("   ")) {
                val match = jobHeader.matchEntire(line)
                if (match == null) {
                    errors.add("$path:$number: job must use a block-style header")
                    currentJob = null
                } else {
                    val name = match.groupValues[1]
                    currentJob = name
                    if (name in runnerCount) {
                        errors.add("$path:$number: duplicate job $name")
                    }
                    jobNames.add(name)
                    runnerCount[name] = 0
                }
            }

            if (!runnerKey.containsMatchIn(line)) continue

            val match = if (inJobs && currentJob != null) runnerLine.matchEntire(line) else null
            if (match == null) {
                errors.add("$path:$number: unsupported runs-on syntax")
                continue
            }
            runnerCount[currentJob!!] = runnerCount.getValue(currentJob!!) + 1
            val raw = match.groupValues[1]
            val label = raw.trim('\'', '"')
            val accepted = (hostedLabel.matches(label) || selfHostedMacLabel.matches(label)) &&
                raw in setOf(label, "'$label'", "\"$label\"")
            if (!accepted) {
                errors.add("$path:$number: $RUNNER_ERROR")
            }
        }

        if (jobNames.isEmpty()) {
            errors.add("$path: no jobs found")
        }
        for (job in jobNames) {
            if (runnerCount[job] != 1) {
                errors.add("$path: job $job must have exactly one explicit runs-on")
            }
        }
        return errors
    }

    /** Splits lines as Python's `str.splitlines` does for workflow text. */
    private fun String.splitLines(): List<String> {
        val lines = mutableListOf<String>()
        val current = StringBuilder()
        var index = 0
        while (index < length) {
            val char = this[index]
            if (char == '\r') {
                lines.add(current.toString())
                current.clear()
                index += if (index + 1 < length && this[index + 1] == '\n') 2 else 1
                continue
            }
            if (char in "\n\u000B\u000C\u001C\u001D\u001E\u0085\u2028\u2029") {
                lines.add(current.toString())
                current.clear()
                index += 1
                continue
            }
            current.append(char)
            index += 1
        }
        if (current.isNotEmpty()) lines.add(current.toString())
        return lines
    }
}
