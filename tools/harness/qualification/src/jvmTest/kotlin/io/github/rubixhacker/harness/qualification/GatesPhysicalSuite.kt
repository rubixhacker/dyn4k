package io.github.rubixhacker.harness.qualification

import de.infix.testBalloon.framework.core.testSuite
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.attribute.PosixFilePermissions
import kotlin.io.path.writeText
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

/**
 * The numerical analyzer seam and the physical verifiers: every path that needs a Python analyzer
 * raises a precise "not ported" error instead of returning an unverified verdict, while the
 * cheap input checks keep their reference messages.
 */
val GatesPhysicalContract by testSuite {
    test("the analyzer adapters name the missing Python module") {
        val directory = repositoryRoot().resolve("tools/numerical")
        for ((call, message) in listOf(
            { GatesPhysical.numericalModules(directory) } to
                "Python numerical analyzer is not ported: compare.compare_pair / physical.py " +
                "(use the :numerical port instead)",
            { GatesPhysical.jointQualityModule(directory) } to
                "Python numerical analyzer is not ported: weld_pulley_quality " +
                "(use the :numerical port instead)",
            { GatesPhysical.nominalModule(directory) } to
                "Python numerical analyzer is not ported: candidate/nominal_zero.compare_pair " +
                "(use the :numerical port instead)",
        )) {
            val error = assertFailsWith<AnalyzerNotPorted> { call() }
            assertEquals(message, error.message)
        }
        val absent = assertFailsWith<IllegalArgumentException> {
            GatesPhysical.nominalModule(directory.resolve("absent"))
        }
        assertTrue("numerical analyzer directory is absent" in (absent.message ?: ""))
    }

    test("an absent nominal capture is NOT_RUN rather than unverified") {
        val repository = repositoryRoot()
        val result = GatesPhysical.verifyNominalPhysicalCase(
            Files.createTempDirectory("nominal"),
            buildJsonObject { },
            "a".repeat(40),
            mapOf("dyn4k-core" to "1".repeat(64)),
            "2".repeat(64),
            repository,
        )
        assertEquals("NOT_RUN", Py.str(result["candidate_status"]))
        assertEquals("PASSED_BASELINE_ONLY", Py.str(result["approved_reference_status"]))
        assertEquals("36,000-step nominal capture is absent", Py.str(result["reason"]))
    }

    test("a nominal case with the wrong identity keeps the reference message") {
        val repository = repositoryRoot()
        val root = Files.createTempDirectory("nominal-identity")
        try {
            for (name in listOf("reference.jsonl", "candidate.jsonl", "capture.json")) {
                root.resolve(name).writeText("{}\n")
            }
            val receipt = buildJsonObject {
                put(
                    "nominal_physical_case",
                    buildJsonObject {
                        put("key", JsonPrimitive("other-case"))
                        put("reference", JsonPrimitive("reference.jsonl"))
                        put("candidate", JsonPrimitive("candidate.jsonl"))
                        put("capture_receipt", JsonPrimitive("capture.json"))
                    },
                )
            }
            val error = assertFailsWith<IllegalArgumentException> {
                GatesPhysical.verifyNominalPhysicalCase(
                    root, receipt, "a".repeat(40),
                    mapOf("dyn4k-core" to "1".repeat(64)), "2".repeat(64), repository,
                )
            }
            assertEquals("nominal physical case identity or raw paths differ", error.message)
        } finally {
            deleteRecursively(root)
        }
    }

    test("missing Weld/Pulley traces keep the reference message") {
        val repository = repositoryRoot()
        val error = assertFailsWith<IllegalArgumentException> {
            GatesPhysical.verifyJointPhysicalCases(
                Files.createTempDirectory("joint"),
                buildJsonObject { },
                "a".repeat(40),
                mapOf("dyn4k-core" to "1".repeat(64)),
                "2".repeat(64),
                repository,
            )
        }
        assertEquals("36,000-step candidate Weld and Pulley traces are absent", error.message)
    }

    test("a Weld/Pulley case identity mismatch is diagnosed before the engine seam") {
        val repository = repositoryRoot()
        val root = Files.createTempDirectory("joint-identities")
        try {
            val rows = kotlinx.serialization.json.JsonArray(
                listOf(
                    buildJsonObject {
                        put("case", JsonPrimitive("other"))
                        put("reference", JsonPrimitive("r.jsonl"))
                        put("candidate", JsonPrimitive("c.jsonl"))
                        put("capture_receipt", JsonPrimitive("capture.json"))
                    },
                ),
            )
            val error = assertFailsWith<IllegalArgumentException> {
                GatesPhysical.verifyJointPhysicalCases(
                    root,
                    buildJsonObject { put("joint_physical_cases", rows) },
                    "a".repeat(40),
                    mapOf("dyn4k-core" to "1".repeat(64)),
                    "2".repeat(64),
                    repository,
                )
            }
            assertEquals("candidate Weld/Pulley case identities or counts differ", error.message)
        } finally {
            deleteRecursively(root)
        }
    }
}

/**
 * `duplicate_provider.py`: the capture refuses an audit that did not pass, an existing output
 * directory, and a checkout that is not the candidate, before it runs any Gradle task.
 */
val DuplicateProviderCapture by testSuite {
    test("a failing staging audit is rejected before any capture") {
        withCleanCheckout { repository, sha ->
            val directory = Files.createTempDirectory("duplicate-provider")
            try {
                val audit = directory.resolve("audit.json")
                Fs.writeText(
                    audit,
                    PyJson.render(
                        buildJsonObject {
                            put("candidate_sha", JsonPrimitive(sha))
                            put("status", JsonPrimitive("FAILED"))
                            put("artifacts", kotlinx.serialization.json.JsonArray(emptyList()))
                        },
                    ) + "\n",
                )
                val error = assertFailsWith<IllegalArgumentException> {
                    DuplicateProvider.runCapture(
                        repository, sha, repository.resolve("staging"), audit,
                        directory.resolve("out"),
                    )
                }
                assertEquals(
                    "duplicate provider requires a passing exact-source staging audit",
                    error.message,
                )
                assertEquals(false, Files.exists(directory.resolve("out")))
            } finally {
                deleteRecursively(directory)
            }
        }
    }

    test("an audit for another candidate is rejected") {
        withCleanCheckout { repository, sha ->
            val directory = Files.createTempDirectory("duplicate-provider-sha")
            try {
                val audit = directory.resolve("audit.json")
                Fs.writeText(
                    audit,
                    PyJson.render(
                        buildJsonObject {
                            put("candidate_sha", JsonPrimitive("f".repeat(40)))
                            put("status", JsonPrimitive("PASSED"))
                            put("artifacts", kotlinx.serialization.json.JsonArray(emptyList()))
                        },
                    ) + "\n",
                )
                val error = assertFailsWith<IllegalArgumentException> {
                    DuplicateProvider.runCapture(
                        repository, sha, repository.resolve("staging"), audit,
                        directory.resolve("out"),
                    )
                }
                assertEquals(
                    "duplicate provider requires a passing exact-source staging audit",
                    error.message,
                )
            } finally {
                deleteRecursively(directory)
            }
        }
    }

    test("the capture records its own failure for the caller") {
        withCleanCheckout { repository, sha ->
            val directory = Files.createTempDirectory("duplicate-provider-cli")
            try {
                val audit = directory.resolve("audit.json")
                Fs.writeText(
                    audit,
                    PyJson.render(
                        buildJsonObject {
                            put("candidate_sha", JsonPrimitive(sha))
                            put("status", JsonPrimitive("FAILED"))
                            put("artifacts", kotlinx.serialization.json.JsonArray(emptyList()))
                        },
                    ) + "\n",
                )
                val output = directory.resolve("out")
                val status = DuplicateProviderCli.run(
                    arrayOf(
                        "--repository", repository.toString(),
                        "--candidate-sha", sha,
                        "--staging-repository", repository.resolve("staging").toString(),
                        "--audit", audit.toString(),
                        "--output", output.toString(),
                    ),
                )
                assertEquals(1, status)
                assertEquals(
                    "duplicate provider requires a passing exact-source staging audit\n",
                    Fs.readText(output.resolve("capture-error.txt")),
                )
            } finally {
                deleteRecursively(directory)
            }
        }
    }
}

/** A committed checkout with a stub Gradle wrapper, so the clean-checkout rule passes. */
private fun withCleanCheckout(block: (Path, String) -> Unit) {
    val repository = Files.createTempDirectory("duplicate-checkout")
    try {
        checkoutGit(repository, "init", "-q")
        val wrapper = repository.resolve("gradlew")
        wrapper.writeText("#!/bin/sh\nexit 0\n")
        Files.setPosixFilePermissions(wrapper, PosixFilePermissions.fromString("rwxr-xr-x"))
        Files.createDirectories(repository.resolve("consumers/qualification"))
        repository.resolve("consumers/qualification/README.md").writeText("consumer fixture\n")
        checkoutGit(repository, "add", "-A")
        checkoutGit(
            repository, "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
            "commit", "-qm", "base",
        )
        block(repository, checkoutGit(repository, "rev-parse", "HEAD").trim())
    } finally {
        deleteRecursively(repository)
    }
}

internal fun checkoutGit(repository: Path, vararg arguments: String): String {
    val process = ProcessBuilder(listOf("git", "-C", repository.toString()) + arguments).start()
    val output = process.inputStream.use { it.readBytes() }
    val error = process.errorStream.use { it.readBytes() }
    check(process.waitFor() == 0) { "git ${arguments.joinToString(" ")} failed: ${String(error)}" }
    return String(output)
}
