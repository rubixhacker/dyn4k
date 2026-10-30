package io.github.rubixhacker.harness.qualification

import de.infix.testBalloon.framework.core.testSuite
import java.nio.file.Files
import java.nio.file.Path
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/** `qualify.expected_probe_cases`, `validate_probe_accounting`, and `execution_succeeded`. */
val ProbeManifestContract by testSuite {
    for (vector in TestVectors.list("probe_cases")) {
        test("expected_probe_cases: ${vector.primitive("name")}") {
            val manifest = vector.objectAt("manifest")
            val group = vector.objectAt("group")
            val expected = vector.objectAt("result")
            if ("cases" in expected) {
                val cases = ProbeManifest.expectedCases(manifest, group)
                val want = (expected["cases"] as JsonArray).map { item ->
                    val entry = item as JsonArray
                    ProbeCase(TestVectors.str(entry[0]), TestVectors.str(entry[1]))
                }
                assertEquals(want, cases, vector.primitive("name"))
            } else {
                val error = assertFailsWith<IllegalArgumentException> {
                    ProbeManifest.expectedCases(manifest, group)
                }
                assertEquals(expected.primitive("error"), error.message, vector.primitive("name"))
            }
        }
    }

    for (vector in TestVectors.list("probe_accounting")) {
        test("validate_probe_accounting: ${vector.primitive("name")}") {
            val probe = vector.objectAt("probe")
            val manifest = vector.objectAt("manifest")
            val groupIds = TestVectors.strings(vector["group_ids"])
            val expected = vector.objectAt("result")
            if ("totals" in expected) {
                val totals = ProbeManifest.validateAccounting(probe, manifest, groupIds)
                val want = expected.objectAt("totals")
                assertEquals(want.keys, totals.keys)
                for (key in want.keys) {
                    assertEquals(TestVectors.long(want[key]), totals[key], key)
                }
            } else {
                val error = assertFailsWith<IllegalArgumentException> {
                    ProbeManifest.validateAccounting(probe, manifest, groupIds)
                }
                assertEquals(expected.primitive("error"), error.message, vector.primitive("name"))
            }
        }
    }

    for (vector in TestVectors.list("execution")) {
        test("execution_succeeded: ${vector.primitive("name")}") {
            val evidence = vector.objectAt("evidence")
            assertEquals(
                TestVectors.str(vector["result"]) == "true",
                ProbeManifest.executionSucceeded(evidence),
                vector.primitive("name"),
            )
        }
    }
}

/**
 * `qualify.run_probe`, replayed with the recorded command scripts.
 *
 * The reference ran each script through `/bin/sh -c` in a directory holding only the reports it
 * wrote, so the port runs the same script in a fresh directory and compares the report it writes.
 */
val ProbeRunnerContract by testSuite {
    for (vector in TestVectors.list("run_probe")) {
        test("run_probe: ${vector.primitive("name")}") {
            val directory = Files.createTempDirectory("probe-run")
            try {
                val output = directory.resolve("probe.json")
                val command = vector.objectAt("result").let { TestVectors.strings(it["command"]) }
                val manifest = TestVectors.nullable(vector["manifest"]) as JsonObject?
                val report = ProbeRunner.run(
                    command = command,
                    reportPaths = TestVectors.strings(vector["report_paths"]),
                    candidateSha = TestVectors.str(vector.objectAt("result")["candidate_sha"]),
                    output = output,
                    manifest = manifest,
                    workingDirectory = directory,
                )
                val expected = vector.objectAt("result")
                for (key in listOf(
                    "status", "reason", "expected", "executed", "reported",
                    "failures", "errors", "skipped", "scope",
                )) {
                    assertEquals(
                        expected.primitive(key),
                        TestVectors.str(report.report.getValue(key)),
                        "${vector.primitive("name")}: $key",
                    )
                }
                assertEquals(
                    TestVectors.strOrNull(expected["exit_code"]),
                    TestVectors.strOrNull(report.report["exit_code"]),
                    "exit_code",
                )
                val groups = expected["groups"] as JsonArray
                val observed = report.report["groups"] as JsonArray
                for (index in groups.indices) {
                    val want = groups[index] as JsonObject
                    val got = observed[index] as JsonObject
                    for (key in want.keys) {
                        if (key == "id") {
                            assertEquals(
                                TestVectors.str(want[key]),
                                TestVectors.str(got[key]),
                                "${vector.primitive("name")}: group $index id",
                            )
                        } else {
                            assertEquals(
                                TestVectors.long(want[key]),
                                TestVectors.long(got[key]),
                                "${vector.primitive("name")}: group $index $key",
                            )
                        }
                    }
                }
                assertEquals(
                    normalizeTimestamps(vector.primitive("written")),
                    normalizeTimestamps(Fs.readText(output)),
                    "written report",
                )
            } finally {
                deleteRecursively(directory)
            }
        }
    }

    test("an unexpected report for an empty group is rejected") {
        val directory = Files.createTempDirectory("probe-empty-group")
        try {
            val script = "cat > one.xml <<'XML'\n${probeSuiteText()}\nXML\n" +
                "cat > extra.xml <<'XML'\n${probeSuiteText()}\nXML"
            val report = ProbeRunner.run(
                command = listOf("/bin/sh", "-c", script),
                reportPaths = listOf("one.xml", "extra.xml"),
                candidateSha = "a".repeat(40),
                output = directory.resolve("probe.json"),
                manifest = twoGroupManifest(),
                workingDirectory = directory,
            )
            assertEquals("PROBE_FAILED", Py.str(report.report["status"]))
            assertTrue("unexpected report for empty group none" in Py.str(report.report["reason"])!!)
        } finally {
            deleteRecursively(directory)
        }
    }
}

private fun twoGroupManifest(): JsonObject =
    io.github.rubixhacker.harness.contract.StrictJson.load(
        """
        {"kind": "foundation-probe", "groups": [
          {"id": "core", "report_pattern": "one.xml",
           "cases": [{"classname": "C", "name": "one"}]},
          {"id": "none", "report_pattern": "extra.xml", "cases": []}
        ]}
        """.trimIndent(),
    ) as JsonObject

private fun probeSuiteText(): String =
    "<testsuite tests=\"1\" failures=\"0\" errors=\"0\" skipped=\"0\" time=\"0.1\">" +
        "<testcase classname=\"C\" name=\"one\" time=\"0.1\"/></testsuite>"

/** The probe report records wall-clock nanos, which no two runs share. */
private fun normalizeTimestamps(text: String): String = text
    .replace(Regex("\"started_at_ns\": [0-9]+"), "\"started_at_ns\": 0")
    .replace(Regex("\"finished_at_ns\": [0-9]+"), "\"finished_at_ns\": 0")

/** `json.dumps(value, indent=2)` byte output, against recorded reference renderings. */
val PythonJsonRendering by testSuite {
    for (vector in TestVectors.list("py_json")) {
        test("indented rendering matches Python") {
            val value = vector["value"] as JsonElement
            assertEquals(vector.primitive("indented"), PyJson.render(value))
            assertEquals(vector.primitive("default"), PyJson.renderDefault(value))
        }
    }
}
