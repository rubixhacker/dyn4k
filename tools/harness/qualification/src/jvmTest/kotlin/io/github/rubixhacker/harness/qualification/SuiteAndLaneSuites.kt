package io.github.rubixhacker.harness.qualification

import de.infix.testBalloon.framework.core.testSuite
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import kotlin.test.assertFailsWith
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/** `qualify.full_suite_cases`, replayed against recorded reference verdicts. */
val CompleteSuiteCases by testSuite {
    for (vector in TestVectors.list("suite_cases")) {
        test("full_suite_cases: ${vector.primitive("name")}") {
            val manifest = TestVectors.nullable(vector["manifest"])
            val lane = TestVectors.strOrNull(vector["lane"])
            val expected = vector.objectAt("result")
            if ("cases" in expected) {
                assertEquals(
                    TestVectors.strings(expected["cases"]),
                    CompleteSuite.cases(manifest, lane),
                    vector.primitive("name"),
                )
            } else {
                val error = assertFailsWith<IllegalArgumentException> {
                    CompleteSuite.cases(manifest, lane)
                }
                assertEquals(expected.primitive("error"), error.message, vector.primitive("name"))
            }
        }
    }
}

/** `qualify.target_binary_hashes`, replayed against recorded reference mappings. */
val TargetBinaryHashesReport by testSuite {
    for (vector in TestVectors.list("target_binary_hashes")) {
        test("target_binary_hashes: ${vector.primitive("label")}") {
            val expected = vector.objectAt("result")
            val observed = TargetBinaryHashes.of(vector["artifacts"])
            assertEquals(expected.keys, observed.keys, vector.primitive("label"))
            for (target in expected.keys) {
                val want = expected.objectAt(target)
                val got = observed.getValue(target)
                assertEquals(want.keys, got.keys, "$target modules")
                for (module in want.keys) {
                    assertEquals(TestVectors.strOrNull(want[module]), got[module], "$target/$module")
                }
            }
        }
    }
}

/** `qualify.evaluate`, replayed against recorded reference verdicts and reasons. */
val LaneEvidenceEvaluation by testSuite {
    for (vector in TestVectors.list("evaluate")) {
        test("evaluate: ${vector.primitive("name")}") {
            val verdict = evaluateVector(vector)
            val expected = vector.objectAt("result")
            assertEquals(expected.primitive("id"), verdict.id, vector.primitive("name"))
            assertEquals(expected.primitive("status"), verdict.status, vector.primitive("name"))
            assertEquals(expected.primitive("reason"), verdict.reason, vector.primitive("name"))
        }
    }

    test("a non-finite observation is invalid") {
        // The reference records this through float('nan'), which strict JSON cannot carry.
        val vector = TestVectors.list("evaluate")
            .first { it.primitive("name") == "frozen lane passes" }
        val evidence = vector.objectAt("evidence")
        val observations = evidence.array("case_results")
        val tampered = JsonObject(
            evidence + (
                "case_results" to JsonArray(
                    listOf(
                        JsonObject(
                            (observations[0] as JsonObject) + ("value" to JsonPrimitive(Double.NaN)),
                        ),
                    ) + observations.drop(1),
                )
                ),
        )
        val verdict = LaneEvaluation.evaluate(
            TestVectors.matrixCase(vector.objectAt("case")),
            tampered,
            TestVectors.strOrNull(vector["candidate_sha"]),
            TestVectors.nullable(vector["candidate_manifest"]),
            TestVectors.nullable(vector["suite_manifest"]),
            TestVectors.nullable(vector["artifact_audit"]),
        )
        assertEquals("FAILED", verdict.status)
        assertTrue("non-finite observation is invalid" in verdict.reason, verdict.reason)
    }

    test("an unexpected extra case result is rejected") {
        val vector = TestVectors.list("evaluate")
            .first { it.primitive("name") == "frozen lane passes" }
        val evidence = vector.objectAt("evidence")
        val tampered = JsonObject(
            evidence + (
                "case_results" to JsonArray(
                    evidence.array("case_results") +
                        JsonObject(
                            linkedMapOf(
                                "id" to JsonPrimitive("extra"),
                                "status" to JsonPrimitive("PASSED"),
                            ),
                        ),
                )
                ),
        )
        val verdict = LaneEvaluation.evaluate(
            TestVectors.matrixCase(vector.objectAt("case")),
            tampered,
            TestVectors.strOrNull(vector["candidate_sha"]),
            TestVectors.nullable(vector["candidate_manifest"]),
            TestVectors.nullable(vector["suite_manifest"]),
            TestVectors.nullable(vector["artifact_audit"]),
        )
        assertEquals("FAILED", verdict.status)
        assertTrue("complete case identities are missing, duplicate, or unexpected" in verdict.reason)
    }
}

internal fun evaluateVector(vector: JsonObject): LaneVerdict = LaneEvaluation.evaluate(
    TestVectors.matrixCase(vector.objectAt("case")),
    TestVectors.nullable(vector["evidence"]),
    TestVectors.strOrNull(vector["candidate_sha"]),
    TestVectors.nullable(vector["candidate_manifest"]),
    TestVectors.nullable(vector["suite_manifest"]),
    TestVectors.nullable(vector["artifact_audit"]),
)
