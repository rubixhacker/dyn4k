package io.github.rubixhacker.harness.numerical

import de.infix.testBalloon.framework.core.testSuite
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import kotlin.test.assertEquals

private val vectors = parseVectors(RECEIPT_VECTORS)

private fun identity(recorded: JsonObject): Identity = Identity(
    candidateCommit = recorded.str("candidate_commit"),
    sourceSha256 = recorded.str("source_sha256"),
    artifactSha256 = stringMap(recorded.obj("artifact_sha256")),
    runtime = recorded.getValue("runtime"),
)

private fun catalog(recorded: JsonObject): FixtureCatalog = FixtureCatalog(
    baselineSourceRevision = recorded.str("baseline_source_revision"),
    baselineJarSha256 = recorded.str("baseline_jar_sha256"),
    referenceGzipSha256 = recorded.array("fixtures").associate {
        val item = it.jsonObject
        item.str("key") to item.obj("reference").str("gzip_sha256")
    },
)

private fun stringMap(recorded: JsonObject): Map<String, String> =
    recorded.mapValues { it.value.stringOrNull().orEmpty() }

/**
 * `receipt`: the trace inspector, the setup and state validators, the exact comparator, and the
 * seal and verify pair.
 *
 * Every scenario replays one from `tools/numerical/portable/test_receipt.py` and compares the
 * Kotlin outcome with the one the Python reference produces at the recorded revision.
 */
val ReceiptContract by testSuite {
    test("the trace inspector reproduces every recorded scenario") {
        val scenarios = vectors.array("inspect")
        assertEquals(true, scenarios.size >= 17)
        for (element in scenarios) {
            val scenario = element.jsonObject
            val rows = traceLines(rowsOf(scenario.getValue("rows")))
            val cases = rowsOf(scenario.getValue("cases"))
            val allow = scenario["allow_tagged"].booleanOrNull() == true
            assertOutcome(scenario.obj("outcome")) { Receipt.inspect(rows, cases, allow) }
        }
    }

    test("the exact comparator distinguishes signed zero and event order") {
        val reference =
            traceLines(rowsOf(vectors.array("inspect")[0].jsonObject.getValue("rows")))
        val cases = rowsOf(vectors.array("inspect")[0].jsonObject.getValue("cases"))
        for (element in vectors.array("compare")) {
            val scenario = element.jsonObject
            val candidate = traceLines(rowsOf(scenario.getValue("candidate")))
            assertOutcome(scenario.obj("outcome")) {
                Receipt.compareExact(reference, candidate, cases)
            }
        }
    }

    test("the record reader rejects malformed lines and tagged non-finite values") {
        for (element in vectors.array("records")) {
            val scenario = element.jsonObject
            val lines = if (scenario.containsKey("text")) {
                linesOf(scenario.str("text"))
            } else {
                scenario.array("lines").map { it.stringOrNull().orEmpty() + "\n" }
            }
            val allow = scenario["allow_tagged"].booleanOrNull() == true
            assertOutcome(scenario.obj("outcome")) { JsonArray(records(lines, allow)) }
        }
    }

    test("the setup validator reproduces every recorded scenario") {
        for (element in vectors.array("validate_setup")) {
            val scenario = element.jsonObject
            assertOutcome(scenario.obj("outcome")) {
                Receipt.validateSetup(scenario.obj("header"), scenario.obj("case"))
                JsonNull
            }
        }
    }

    test("a known non-finite case is retained only when tagged values are allowed") {
        val angle = vectors.obj("angle")
        assertOutcome(angle.obj("disallowed")) {
            Receipt.inspect(
                traceLines(rowsOf(angle.getValue("rows"))),
                rowsOf(angle.getValue("cases")),
            )
        }
        assertOutcome(angle.obj("allowed")) {
            Receipt.inspect(
                traceLines(rowsOf(angle.getValue("rows"))),
                rowsOf(angle.getValue("cases")),
                allowTaggedNonfinite = true,
            )
        }
        assertOutcome(angle.obj("input_outcome")) {
            Receipt.inspect(
                traceLines(rowsOf(angle.getValue("input_rows"))),
                rowsOf(angle.getValue("input_case")),
                allowTaggedNonfinite = true,
            )
        }
        assertOutcome(angle.obj("other_outcome")) {
            Receipt.inspect(
                traceLines(rowsOf(angle.getValue("other_rows"))),
                rowsOf(angle.getValue("other_case")),
                allowTaggedNonfinite = true,
            )
        }
    }

    test("configured endpoints do not advance the temporal state") {
        val endpoints = vectors.obj("endpoints")
        val cases = rowsOf(endpoints.getValue("cases"))
        assertOutcome(endpoints.obj("good")) {
            Receipt.inspect(traceLines(rowsOf(endpoints.getValue("rows"))), cases)
        }
        assertOutcome(endpoints.obj("bad")) {
            Receipt.inspect(traceLines(rowsOf(endpoints.getValue("bad_rows"))), cases)
        }
    }

    test("a missing callback or action cannot pass") {
        val callbacks = vectors.obj("callbacks")
        val expected = rowsOf(callbacks.getValue("expected"))
        assertOutcome(callbacks.obj("missing")) {
            Receipt.inspect(traceLines(rowsOf(callbacks.getValue("rows"))), expected)
        }
        assertOutcome(callbacks.obj("complete")) {
            Receipt.inspect(traceLines(rowsOf(callbacks.getValue("complete_rows"))), expected)
        }
    }

    test("seal and verify reproduce the recorded receipt") {
        val recorded = vectors.obj("seal")
        val rows = traceLines(rowsOf(recorded.getValue("rows")))
        val cases = rowsOf(recorded.getValue("cases"))
        val who = identity(recorded.obj("identity"))
        val paths = stringMap(recorded.obj("artifact_paths"))
        val digests = stringMap(recorded.obj("artifact_sha256"))
        val fixtures = catalog(recorded.obj("catalog"))
        val catalogSha = recorded.str("catalog_sha256")
        val buildSha = recorded.str("build_config_sha256")
        val traceSha = recorded.str("trace_sha256")
        val sealed = Receipt.seal(
            rows, cases, who, paths, digests, fixtures, catalogSha, buildSha, traceSha,
        )
        assertSameJson(recorded.getValue("sealed"), sealed)
        assertEquals(
            "058bf6d982a0fb89b54050f929f6ea9dae53b714",
            sealed.str("reference_source_revision"),
        )
        assertEquals(1, sealed.obj("expected_counts").int("cases"))
        assertOutcome(recorded.obj("verify")) {
            Receipt.verify(
                sealed, rows, cases, who, paths, digests, fixtures, catalogSha, buildSha, traceSha,
            )
        }
        assertOutcome(recorded.obj("stale_artifact")) {
            Receipt.seal(
                rows, cases, who, paths, mapOf("jvm" to "0".repeat(64)), fixtures,
                catalogSha, buildSha, traceSha,
            )
        }
        assertOutcome(recorded.obj("artifact_set")) {
            Receipt.seal(
                rows, cases, who, mapOf("other" to "/artifacts/other.jar"),
                mapOf("other" to who.artifactSha256.getValue("jvm")), fixtures,
                catalogSha, buildSha, traceSha,
            )
        }
    }

    test("a tampered sealed receipt fails verification") {
        val recorded = vectors.obj("seal")
        val rows = traceLines(rowsOf(recorded.getValue("rows")))
        val cases = rowsOf(recorded.getValue("cases"))
        val who = identity(recorded.obj("identity"))
        val paths = stringMap(recorded.obj("artifact_paths"))
        val digests = stringMap(recorded.obj("artifact_sha256"))
        val fixtures = catalog(recorded.obj("catalog"))
        val tampered = JsonObject(
            recorded.getValue("sealed").jsonObject.toMutableMap().apply {
                put("trace_sha256", kotlinx.serialization.json.JsonPrimitive("0".repeat(64)))
            },
        )
        assertOutcome(recorded.obj("verify_tampered")) {
            Receipt.verify(
                tampered, rows, cases, who, paths, digests, fixtures,
                recorded.str("catalog_sha256"), recorded.str("build_config_sha256"),
                recorded.str("trace_sha256"),
            )
        }
    }
}
