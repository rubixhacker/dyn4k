package io.github.rubixhacker.harness.android

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

/**
 * `tools/android-runtime/evidence.py`.
 *
 * The instrumentation runner writes `INSTRUMENTATION_STATUS` records; the parser turns them into the
 * two lane groups the diagnostic receipt records, and `validateLane` decides whether the lane is
 * usable. Both are pure text functions, so they live in `commonMain`.
 */

/** One executed case: its verdict and, for failures, the retained stack text. */
class InstrumentationCase(val status: String, val stack: String?)

/** One lane group: the executed cases in transcript order and their tallies. */
class LaneGroup {
    val cases: MutableMap<String, InstrumentationCase> = LinkedHashMap()
    var passed: Int = 0
    var failed: Int = 0
    var skipped: Int = 0

    internal fun record(name: String, status: String, stack: String?) {
        cases[name] = InstrumentationCase(status, stack)
        when (status) {
            "SKIPPED" -> skipped += 1
            "PASSED" -> passed += 1
            "FAILED" -> failed += 1
            else -> error("unreachable status $status")
        }
    }
}

/** The parsed instrumentation transcript. */
class ParsedInstrumentation(
    val instrumentation: LaneGroup,
    val portable: LaneGroup,
    val summaryTests: Int,
    val reportedTotals: MutableList<Int> = mutableListOf(),
    var runnerError: String? = null,
) {
    /** The Python dictionary this object replaces, for byte-level comparison against a recording. */
    fun toJson(): JsonObject = buildJsonObject {
        put("instrumentation", instrumentation.toJson())
        put("portable", portable.toJson())
        put("completed", JsonPrimitive(true))
        put("summary_tests", JsonPrimitive(summaryTests))
        put("reported_totals", JsonArray(reportedTotals.map { JsonPrimitive(it) }))
        runnerError?.let { put("runner_error", JsonPrimitive(it)) }
    }
}

private fun LaneGroup.toJson(): JsonObject = buildJsonObject {
    put(
        "cases",
        JsonObject(
            cases.mapValues { (_, case) ->
                buildJsonObject {
                    put("status", JsonPrimitive(case.status))
                    put("stack", case.stack?.let { JsonPrimitive(it) } ?: JsonNull)
                }
            },
        ),
    )
    put("passed", JsonPrimitive(passed))
    put("failed", JsonPrimitive(failed))
    put("skipped", JsonPrimitive(skipped))
}

object Evidence {
    private const val STATUS = "INSTRUMENTATION_STATUS: "
    private const val STATUS_CODE = "INSTRUMENTATION_STATUS_CODE: "
    private const val TERMINAL = "INSTRUMENTATION_CODE:"
    private const val SUMMARY_PREFIX = "OK ("
    private val summaryPattern = Regex("""OK \(([1-9]\d*) tests?\)""")

    /**
     * `parse_instrumentation`.
     *
     * Requires exactly one successful terminal code as the final line, exactly one successful JUnit
     * summary as the final result, and consistent per-case records.
     */
    fun parseInstrumentation(raw: String): ParsedInstrumentation {
        val lines = pySplitLines(raw)
        val terminals = lines.indices.filter { lines[it].startsWith(TERMINAL) }
        if (terminals.size != 1 || lines[terminals[0]] != "INSTRUMENTATION_CODE: -1") {
            throw IllegalArgumentException(
                "expected exactly one successful instrumentation terminal code",
            )
        }
        val terminal = terminals[0]
        val finalIndex = lines.indices.reversed().firstOrNull { lines[it].isNotBlank() }
        if (finalIndex != terminal) {
            throw IllegalArgumentException("instrumentation terminal code is not final")
        }
        val summaries = lines.filter { it.startsWith(SUMMARY_PREFIX) }
        val summary = summaries.singleOrNull()?.let { summaryPattern.matchEntire(it) }
        if (summaries.size != 1 || summary == null) {
            throw IllegalArgumentException("expected exactly one successful instrumentation summary")
        }
        val finalResult = lastNonBlank(lines.subList(0, terminal))
        if (finalResult != summaries[0]) {
            throw IllegalArgumentException("instrumentation summary is not final")
        }
        if (lines.any { it.startsWith("FAILURES!!!") }) {
            throw IllegalArgumentException("instrumentation failure summary present")
        }

        val result = ParsedInstrumentation(
            instrumentation = LaneGroup(),
            portable = LaneGroup(),
            summaryTests = pyInt(summary.groupValues[1]),
        )
        val fields = LinkedHashMap<String, String>()
        var stackOpen = false
        for (line in lines) {
            if (line.startsWith(STATUS)) {
                val rest = line.substring(STATUS.length)
                val separator = rest.indexOf('=')
                if (separator >= 0) {
                    val key = rest.substring(0, separator)
                    fields[key] = rest.substring(separator + 1)
                    stackOpen = key == "stack" || key == "dyn4k_stack"
                }
            } else if (line.startsWith(STATUS_CODE)) {
                val code = pyInt(line.substringAfterLast(": "))
                if ("numtests" in fields) result.reportedTotals += pyInt(fields.getValue("numtests"))
                if ("dyn4k_case" in fields) {
                    val name = fields.getValue("dyn4k_case")
                    // A missing status is Python's None, which the membership test rejects.
                    val status = fields["dyn4k_status"] ?: ""
                    if (code != 0 || status !in setOf("PASSED", "FAILED", "SKIPPED")) {
                        throw IllegalArgumentException("invalid portable status: $name")
                    }
                    if (name in result.portable.cases) {
                        throw IllegalArgumentException("duplicate portable case: $name")
                    }
                    result.portable.record(name, status, fields["dyn4k_stack"])
                } else if (code in setOf(0, -2, -3) && "class" in fields && "test" in fields) {
                    val name = fields.getValue("class") + "#" + fields.getValue("test")
                    if (name in result.instrumentation.cases) {
                        throw IllegalArgumentException("duplicate instrumentation case: $name")
                    }
                    val status = when (code) {
                        0 -> "PASSED"
                        -2 -> "FAILED"
                        else -> "SKIPPED"
                    }
                    result.instrumentation.record(name, status, fields["stack"])
                }
                fields.clear()
                stackOpen = false
            } else if (line.startsWith("INSTRUMENTATION_RESULT: shortMsg=")) {
                result.runnerError = line.substringAfter('=')
            } else if (stackOpen && fields.isNotEmpty()) {
                val key = if ("dyn4k_stack" in fields) "dyn4k_stack" else "stack"
                fields[key] = fields.getValue(key) + "\n" + line
            }
        }
        return result
    }

    /**
     * `validate_lane`.
     *
     * Fails on a nonzero process exit, an incomplete transcript, disagreeing totals, missing or extra
     * cases, and any skipped or failed case.
     */
    fun validateLane(
        result: ParsedInstrumentation,
        expectedPortable: Set<String>,
        expectedInstrumentation: Set<String>,
        processExitCode: Int,
    ) {
        if (processExitCode != 0) {
            throw IllegalArgumentException("instrumentation process exit: $processExitCode")
        }
        if (result.runnerError != null) {
            throw IllegalArgumentException("instrumentation did not complete")
        }
        val actualTotal = result.instrumentation.cases.size
        if (result.summaryTests != actualTotal ||
            result.reportedTotals.any { it != result.summaryTests }
        ) {
            throw IllegalArgumentException(
                "instrumentation summary mismatch: ${result.summaryTests} vs $actualTotal",
            )
        }
        for ((name, expected) in listOf(
            "portable" to expectedPortable,
            "instrumentation" to expectedInstrumentation,
        )) {
            val group = if (name == "portable") result.portable else result.instrumentation
            val actual = group.cases.keys
            val missing = expected - actual
            if (missing.isNotEmpty()) {
                throw IllegalArgumentException(
                    "missing $name cases: ${pyListRepr(missing.sorted())}",
                )
            }
            val extra = actual - expected
            if (extra.isNotEmpty()) {
                throw IllegalArgumentException(
                    "unexpected $name cases: ${pyListRepr(extra.sorted())}",
                )
            }
            if (group.skipped != 0) {
                throw IllegalArgumentException("skipped $name cases: ${group.skipped}")
            }
            if (group.failed != 0) {
                throw IllegalArgumentException("failed $name cases: ${group.failed}")
            }
        }
        if (expectedInstrumentation.isEmpty() || result.instrumentation.passed == 0) {
            throw IllegalArgumentException("empty instrumentation suite")
        }
    }
}
