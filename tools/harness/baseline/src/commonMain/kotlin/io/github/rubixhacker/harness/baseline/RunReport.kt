package io.github.rubixhacker.harness.baseline

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/**
 * `verify.result_field` and `verify.validate_run_report`: the gate the upstream JUnit run summary
 * must pass before its counts become evidence.
 */

/** `verify.result_field`: the single `LABEL=<integer>` line of [output], or null. */
fun resultField(output: String, label: String): Int? {
    val values = pySplitLines(output)
        .filter { it.startsWith("$label=") }
        .map { it.substringAfter("=") }
    if (values.size != 1) return null
    val value = values[0]
    if (value.isEmpty() || value.any { it !in '0'..'9' }) return null
    return value.toIntOrNull()
}

/** A JSON value Python's `type(x) is int` accepts, or null. */
private fun JsonObject.strictInt(key: String): Int? {
    val value = this[key] as? JsonPrimitive ?: return null
    if (value.isString) return null
    val content = value.content
    if (content.isEmpty() || content.any { it !in '0'..'9' }) return null
    return content.toIntOrNull()
}

private fun JsonObject.strictString(key: String): String? {
    val value = this[key] as? JsonPrimitive ?: return null
    return if (value.isString) value.content else null
}

/**
 * `verify.validate_run_report`: the compiled suite must have run every pinned case, reported no
 * failure and no ignored case, exited zero, and recorded Java 8 bytecode plus non-empty version
 * and input hashes.
 */
fun validateRunReport(report: JsonObject, expectedCases: Int = Baseline.EXPECTED_CASES) {
    val output = report.strictString("output")
    val stderr = report.strictString("stderr")
    if (output == null || stderr == null) {
        throw IllegalArgumentException("run output fields are missing or invalid")
    }
    val expected = listOf(
        Triple("actual_executed_cases", "ACTUAL_TESTS", expectedCases),
        Triple("failures", "FAILURES", 0),
        Triple("ignored", "IGNORED", 0),
    )
    for ((field, marker, value) in expected) {
        val observed = report.strictInt(field)
        if (observed == null || observed != value || resultField(output, marker) != observed) {
            throw IllegalArgumentException(
                "invalid $field: expected $value and matching $marker marker",
            )
        }
    }
    if (report.strictInt("process_exit_code") != 0) {
        throw IllegalArgumentException("baseline test process did not exit successfully")
    }
    if (report.strictInt("compile_release") != 8 || report.strictInt("harness_class_major") != 52) {
        throw IllegalArgumentException("harness must use Java 8 APIs and bytecode")
    }
    if (report.strictString("javac_version").isNullOrEmpty()) {
        throw IllegalArgumentException("missing compiler version")
    }
    if (report.strictString("java_version").isNullOrEmpty()) {
        throw IllegalArgumentException("missing runtime version")
    }
    val hashes = report["test_input_sha256"] as? JsonObject
    if (hashes == null || hashes.isEmpty()) {
        throw IllegalArgumentException("missing test input hashes")
    }
}
