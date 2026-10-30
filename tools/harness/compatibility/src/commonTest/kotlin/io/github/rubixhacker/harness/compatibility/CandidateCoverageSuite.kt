package io.github.rubixhacker.harness.compatibility

import de.infix.testBalloon.framework.core.testSuite
import io.github.rubixhacker.harness.contract.Sha256
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import okio.ByteString.Companion.decodeBase64
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

private val mapping = Vectors.candidateCoverage

/**
 * The pure source-mapping helpers of `candidate_coverage.py`.
 *
 * The `materialize` cases in `test_candidate_coverage.py` need the candidate JAR, git objects, and a
 * Kotlin worktree, so they stay with the unported host half.
 */
val CandidateCoverageContract by testSuite {
    test("candidate source safety matches the recorded answers") {
        for (case in mapping.array("safe_source").map { it.jsonObject }) {
            assertEquals(
                case.getValue("result").jsonPrimitive.content.toBooleanStrict(),
                CandidateCoverage.safeSource(case.str("path")),
                case.str("path"),
            )
        }
    }

    test("frozen mapping tables match the recorded tables") {
        assertEquals(
            mapping.obj("anonymous_behaviors").mapValues { it.value.jsonArray.map { entry -> entry.jsonPrimitive.content } },
            CandidateCoverage.ANONYMOUS_BEHAVIORS.mapValues { (_, value) -> listOf(value.first, value.second) },
        )
        assertEquals(
            mapping.obj("common_expect_sources").mapValues { it.value.jsonArray.map { entry -> entry.jsonPrimitive.content } },
            CandidateCoverage.COMMON_EXPECT_SOURCES.mapValues { (_, value) -> listOf(value.first, value.second) },
        )
    }

    test("recorded class files carry the recorded SourceFile") {
        assertTrue(mapping.array("class_files").isNotEmpty())
        for (case in mapping.array("class_files").map { it.jsonObject }) {
            val data = case.str("bytes_base64").decodeBase64()!!.toByteArray()
            assertEquals(case.str("sha256"), Sha256.of(data), case.str("path"))
            val recorded = case.obj("source_file")
            val error = recorded["error"]
            if (error == null) {
                assertEquals(
                    recorded.obj("ok").nullableStr("value"),
                    CandidateCoverage.classSourceFile(data),
                    case.str("path"),
                )
            } else {
                assertFailsWith<IllegalArgumentException>(case.str("path")) {
                    CandidateCoverage.classSourceFile(data)
                }
            }
        }
    }

    test("malformed class files fail with the recorded message") {
        for (case in mapping.array("class_errors").map { it.jsonObject }) {
            val data = case.str("bytes_base64").decodeBase64()!!.toByteArray()
            val thrown = assertFailsWith<IllegalArgumentException>(case.str("name")) {
                CandidateCoverage.classSourceFile(data)
            }
            assertEquals(case.obj("result").str("error"), thrown.message, case.str("name"))
        }
    }
}
