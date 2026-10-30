package io.github.rubixhacker.harness.qualification

import de.infix.testBalloon.framework.core.testSuite
import io.github.rubixhacker.harness.contract.Qualification
import java.nio.file.Files
import java.nio.file.Path
import kotlin.io.path.writeText
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonObject

private const val CANDIDATE = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

/**
 * `qualify.audit_staging`, replayed against reference audits of Python-generated staging trees.
 *
 * Each fixture is a complete repository-shaped tree: staged publications, committed-shape module
 * sources, Dokka output, and sidecars. The reference produced the recorded verdict from exactly
 * these bytes.
 */
val StagedPublicationAudit by testSuite {
    for (vector in TestVectors.list("staging")) {
        test("audit_staging: ${vector.primitive("label")}") {
            Fixture.extract(vector.primitive("fixture")).use { fixture ->
                val expected = vector.objectAt("result")
                val targets = TestVectors.strings(vector["targets"])
                val result = StagingAudit.audit(
                    root = fixture.staging,
                    candidateSha = CANDIDATE,
                    targets = targets,
                    licenseFile = fixture.license,
                    receiptPath = stagePath(fixture, "stage-receipt.json"),
                    consolePath = stagePath(fixture, "stage-console.txt"),
                )
                assertEquals(expected.primitive("status"), TestVectors.str(result["status"]))
                assertEquals(
                    TestVectors.strings(expected["errors"]),
                    TestVectors.strings(result["errors"]),
                    vector.primitive("label"),
                )
                assertEquals(artifactFingerprints(expected), artifactFingerprints(result))
                assertEquals(expected["content_contract"], result["content_contract"])
                assertEquals(
                    TestVectors.strOrNull(expected["stage_receipt"]),
                    TestVectors.strOrNull(result["stage_receipt"]),
                )
                assertEquals(TestVectors.strings(expected["targets"]), TestVectors.strings(result["targets"]))
            }
        }
    }

    test("the recorded audit of a staged tree re-verifies against those same files") {
        Fixture.extract("stage-receipt.zip").use { fixture ->
            val recorded = TestVectors.list("staging")
                .first { it.primitive("label") == "stage receipt" }
                .objectAt("result")
            StagingAudit.verifyAuditAgainstStaging(recorded, fixture.root)
        }
    }

    test("a recorded audit with no task outcome paths is rejected") {
        val forged = buildJsonObject {
            put("candidate_sha", JsonPrimitive(CANDIDATE))
            put("status", JsonPrimitive("PASSED"))
            put("artifacts", kotlinx.serialization.json.JsonArray(emptyList()))
        }
        val error = assertFailsWith<IllegalArgumentException> {
            StagingAudit.verifyAuditAgainstStaging(forged, Files.createTempDirectory("forged-audit"))
        }
        assertTrue("staged audit" in (error.message ?: ""), error.message)
    }

    test("changed staged bytes invalidate the recorded audit") {
        Fixture.extract("stage-receipt.zip").use { fixture ->
            val recorded = TestVectors.list("staging")
                .first { it.primitive("label") == "stage receipt" }
                .objectAt("result")
            val binary = fixture.staging.resolve(
                Qualification.publicationBinaryPath("dyn4k-core", "jvm"),
            )
            Files.write(binary, "tampered\n".toByteArray())
            val error = assertFailsWith<IllegalArgumentException> {
                StagingAudit.verifyAuditAgainstStaging(recorded, fixture.root)
            }
            assertEquals("staged audit differs from current staged files", error.message)
        }
    }

    test("a changed recorded status invalidates the audit") {
        Fixture.extract("stage-receipt.zip").use { fixture ->
            val recorded = TestVectors.list("staging")
                .first { it.primitive("label") == "stage receipt" }
                .objectAt("result")
            val altered = JsonObject(recorded + ("status" to JsonPrimitive("FAILED")))
            val error = assertFailsWith<IllegalArgumentException> {
                StagingAudit.verifyAuditAgainstStaging(altered, fixture.root)
            }
            assertEquals("staged audit differs from current staged files", error.message)
        }
    }

    test("a task outcome path outside the staging repository is rejected") {
        Fixture.extract("stage-receipt.zip").use { fixture ->
            val recorded = TestVectors.list("staging")
                .first { it.primitive("label") == "stage receipt" }
                .objectAt("result")
            for (escape in listOf("stage-receipt.json", ".qualification/../../../../etc/passwd")) {
                val altered = JsonObject(recorded + ("stage_receipt" to JsonPrimitive(escape)))
                val error = assertFailsWith<IllegalArgumentException> {
                    StagingAudit.verifyAuditAgainstStaging(altered, fixture.root)
                }
                assertTrue("staged audit task outcome path" in (error.message ?: ""), error.message)
            }
        }
    }

    test("an empty staging tree fails every publication") {
        val repository = Files.createTempDirectory("empty-staging")
        try {
            git(repository, "init", "-q")
            repository.resolve("README.md").writeText("Empty staging fixture.\n")
            git(repository, "add", "README.md")
            git(repository, "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                "commit", "-qm", "base")
            val sha = git(repository, "rev-parse", "HEAD").trim()
            val staging = repository.resolve("empty-staging")
            val result = StagingAudit.audit(
                root = staging,
                candidateSha = sha,
                targets = Qualification.matrixTargets(),
                licenseFile = repository.resolve("LICENSE.md"),
                receiptPath = staging.resolve(".qualification/receipt.json"),
                consolePath = staging.resolve(".qualification/stage.log"),
            )
            val expected = TestVectors.root.objectAt("empty_staging")
            assertEquals(sha, TestVectors.str(result["candidate_sha"]))
            assertEquals("FAILED", TestVectors.str(result["status"]))
            assertEquals(0, (result["artifacts"] as kotlinx.serialization.json.JsonArray).size)
            assertEquals(".qualification/receipt.json", TestVectors.strOrNull(result["stage_receipt"]))
            val errors = TestVectors.strings(result["errors"])
            val recorded = TestVectors.strings(expected["errors"])
            // The reference reports the operating system's missing-file text; only the prefix is
            // reproducible across platforms.
            assertEquals(recorded.dropLast(1), errors.dropLast(1))
            assertTrue(errors.last().startsWith("staging task outcome invalid: "), errors.last())
            assertEquals(51, errors.size)
        } finally {
            deleteRecursively(repository)
        }
    }

    test("a pinned content contract is accepted when the caller allows it") {
        Fixture.extract("stage-receipt.zip").use { fixture ->
            val recorded = TestVectors.list("staging")
                .first { it.primitive("label") == "stage receipt" }
                .objectAt("result")
            StagingAudit.verifyAuditAgainstStaging(recorded, fixture.root, allowPinnedContentContract = true)
        }
    }

    test("an invalid recorded content contract fails the audit") {
        Fixture.extract("valid.zip").use { fixture ->
            val pinned = buildJsonObject {
                put("schema", JsonPrimitive(2))
                put("sources", JsonPrimitive("not a map"))
                put("api_docs_sha256", JsonPrimitive("not a map"))
            }
            val result = StagingAudit.audit(
                root = fixture.staging,
                candidateSha = CANDIDATE,
                targets = listOf("jvm"),
                licenseFile = fixture.license,
                contentContract = pinned,
            )
            assertTrue(
                "recorded publication content contract is invalid" in TestVectors.strings(result["errors"]),
                TestVectors.strings(result["errors"]).joinToString("\n"),
            )
        }
    }

    test("a staging tree that is not a Git checkout still binds committed-shape sources") {
        Fixture.extract("valid.zip").use { fixture ->
            val contract = CandidateSource.contract(fixture.root, CANDIDATE)
            assertTrue("commonMain/api/Type.kt" in contract.getValue("dyn4k-core"))
            assertTrue("commonMain/api/Type.kt" in contract.getValue("dyn4k"))
        }
    }
}

private fun stagePath(fixture: Fixture, name: String): Path? {
    val path = fixture.staging.resolve(".qualification").resolve(name)
    return if (Files.isRegularFile(path)) path else null
}

private fun artifactFingerprints(audit: JsonObject): List<String> =
    (audit["artifacts"] as kotlinx.serialization.json.JsonArray).map { item ->
        val entry = item.jsonObject
        "${TestVectors.str(entry["path"])}|${TestVectors.str(entry["sha256"])}"
    }
