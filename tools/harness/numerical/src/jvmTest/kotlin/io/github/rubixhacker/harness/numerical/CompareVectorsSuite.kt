package io.github.rubixhacker.harness.numerical

import de.infix.testBalloon.framework.core.testSuite
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonObject
import kotlin.test.assertEquals

private val vectors = parseVectors(COMPARE_VECTORS)

/**
 * `compare.compare` and `weld_pulley_quality.shown` replayed from the recorded vectors: the whole
 * result object, not just its status, so the check counters, the unpassed channels and the
 * rendered enclosures are all pinned.
 */
val CompareVectorsContract by testSuite {
    test("the comparison engine reproduces every recorded result object") {
        for (element in vectors.array("compare")) {
            val scenario = element.jsonObject
            val fixture = scenario.obj("fixture")
            val rows = rowsOf(scenario.getValue("rows"))
            val candidate = if (scenario["candidate"] is kotlinx.serialization.json.JsonNull) {
                rows
            } else {
                rowsOf(scenario.getValue("candidate"))
            }
            val directory = java.nio.file.Files.createTempDirectory("compare-vector")
            try {
                val reference = directory.resolve("reference.jsonl.gz")
                val referenceData = encoded(rows)
                java.nio.file.Files.write(reference, gzip(referenceData))
                val mutableFixture = LinkedHashMap<String, kotlinx.serialization.json.JsonElement>(
                    fixture,
                )
                mutableFixture["reference"] = parseRow(
                    """{"file":"reference.jsonl.gz",""" +
                        """"gzip_sha256":"${io.github.rubixhacker.harness.contract.Sha256.of(
                            java.nio.file.Files.readAllBytes(reference),
                        )}",""" +
                        """"stream_sha256":"${io.github.rubixhacker.harness.contract.Sha256.of(referenceData)}",""" +
                        """"input_sha256":"${io.github.rubixhacker.harness.contract.Sha256.of(
                            referenceData.toString(Charsets.UTF_8).split("\n")[0],
                        )}"}""",
                )
                val candidatePath = directory.resolve("candidate.jsonl")
                val candidateData = encoded(candidate)
                java.nio.file.Files.write(candidatePath, candidateData)
                val receipt = directory.resolve("receipt.json")
                java.nio.file.Files.writeString(
                    receipt,
                    pyDumps(
                        parseRow(
                            """{"source_sha256":"${"c".repeat(64)}",""" +
                                """"artifact_sha256":"${"d".repeat(64)}",""" +
                                """"candidate_commit":"${"1".repeat(40)}",""" +
                                """"trace_sha256":"${io.github.rubixhacker.harness.contract.Sha256.of(candidateData)}",""" +
                                """"reference_source_revision":"${mutableFixture.getValue("baseline_source_revision").stringOrNull()}",""" +
                                """"reference_artifact_sha256":"${mutableFixture.getValue("baseline_jar_sha256").stringOrNull()}",""" +
                                """"reference_trace_sha256":"${(mutableFixture.getValue("reference") as JsonObject).str("gzip_sha256")}",""" +
                                """"expected_counts":${pyDumps(mutableFixture.getValue("counts"))},""" +
                                """"executed_counts":${pyDumps(mutableFixture.getValue("counts"))},""" +
                                """"skipped":0}""",
                        ),
                    ),
                )
                val outcome = CompareHost.compare(
                    JsonObject(mutableFixture),
                    reference,
                    candidatePath,
                    receipt,
                    "c".repeat(64),
                    "d".repeat(64),
                    "1".repeat(40),
                )
                assertSameJson(scenario.obj("outcome"), outcome)
            } finally {
                directory.toFile().deleteRecursively()
            }
        }
    }

    test("the decimal rendering at precision 80 matches Python") {
        for (element in vectors.array("decimal_sample")) {
            val sample = element.jsonObject
            val numerator = sample.getValue("numerator").numberOrNull()!!.toLong()
            val denominator = sample.getValue("denominator").numberOrNull()!!.toLong()
            val fraction = Fraction(BigInt.of(numerator), BigNat.ofLong(denominator))
            assertEquals(
                sample.str("shown"),
                DecimalText.shown(fraction),
                "$numerator/$denominator",
            )
        }
    }

    test("the frozen Weld and Pulley audits reproduce their metrics") {
        val directory = repositoryRoot()
        val declaration = parseRow(
            java.nio.file.Files.readString(
                directory.resolve("tools/numerical/weld-pulley-physical-declaration.json"),
            ),
        )
        val manifest = parseRow(
            java.nio.file.Files.readString(
                directory.resolve("tools/numerical/weld-pulley-physical-manifest.json"),
            ),
        )
        val cases = manifest.getValue("cases") as JsonObject
        for ((case, element) in vectors.obj("weld_pulley")) {
            val reference = directory.resolve("tools/numerical/references")
                .resolve((cases.getValue(case) as JsonObject).str("file"))
            val outcome = WeldPulleyHost.auditQuality(declaration, manifest, case, reference)
            val recorded = element.jsonObject
            if (recorded.str("status") != "PHYSICAL_PASSED") {
                assertEquals(recorded.str("status"), outcome.str("status"), case)
                continue
            }
            val expectedMetrics = recorded.obj("metrics")
            val actualMetrics = outcome.obj("metrics")
            for ((name, metrics) in expectedMetrics) {
                val expected = metrics.jsonObject
                val actual = actualMetrics.getValue(name).jsonObject
                assertEquals(expected.str("maximum"), actual.str("maximum"), "$case/$name maximum")
                assertEquals(
                    expected.getValue("checked"),
                    actual.getValue("checked"),
                    "$case/$name checked",
                )
                assertEquals(expected.getValue("failed"), actual.getValue("failed"), "$case/$name failed")
            }
        }
    }
}
