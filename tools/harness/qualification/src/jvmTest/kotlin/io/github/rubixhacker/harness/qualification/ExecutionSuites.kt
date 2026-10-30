package io.github.rubixhacker.harness.qualification

import de.infix.testBalloon.framework.core.testSuite
import io.github.rubixhacker.harness.contract.Qualification
import io.github.rubixhacker.harness.contract.StrictJson
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.attribute.PosixFilePermissions
import kotlin.io.path.writeText
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

/**
 * `qualify.execute_plan`.
 *
 * A lane result is only evidence when the command ran, wrote its result file during this
 * invocation, and the file echoes the invocation ID the plan generated. A prior result file is
 * moved aside first, so a no-op command cannot reuse it.
 */
val PlanExecution by testSuite {
    val lane = Qualification.expand().first()

    test("a no-op cannot reuse a prior result") {
        val directory = Files.createTempDirectory("execute-plan")
        try {
            val resultFile = directory.resolve("lane.json")
            resultFile.writeText("""{"candidate_sha": "${"a".repeat(40)}"}""")
            val plan = buildJsonObject {
                put(
                    lane.id,
                    buildJsonObject {
                        put("command", kotlinx.serialization.json.JsonArray(listOf(
                            JsonPrimitive("/bin/sh"), JsonPrimitive("-c"), JsonPrimitive("true"),
                        )))
                        put("result_file", JsonPrimitive(resultFile.toString()))
                    },
                )
            }
            val evidence = Execution.executePlan(plan, "a".repeat(40), directory.resolve("execution.json"))
            val entry = evidence.getValue(lane.id) as JsonObject
            assertEquals("command failed or result file missing", Py.str(entry["error"]))
            assertFalse(Files.exists(resultFile))
            val previous = Files.list(directory).use { stream ->
                stream.filter { it.fileName.toString().startsWith("lane.json.previous-") }.count()
            }
            assertEquals(1, previous)
        } finally {
            deleteRecursively(directory)
        }
    }

    test("a recorded invocation is successful evidence") {
        val directory = Files.createTempDirectory("execute-plan-run")
        try {
            val resultFile = directory.resolve("lane.json")
            val script = "printf '{\"expected\":1,\"executed\":1,\"failures\":0,\"skipped\":0," +
                "\"invocation_id\":\"%s\"}' \"\$DYN4K_QUALIFICATION_INVOCATION\" > $resultFile"
            val plan = buildJsonObject {
                put(
                    lane.id,
                    buildJsonObject {
                        put("command", kotlinx.serialization.json.JsonArray(listOf(
                            JsonPrimitive("/bin/sh"), JsonPrimitive("-c"), JsonPrimitive(script),
                        )))
                        put("result_file", JsonPrimitive(resultFile.toString()))
                    },
                )
            }
            val evidence = Execution.executePlan(plan, "a".repeat(40), directory.resolve("execution.json"))
            val entry = evidence.getValue(lane.id) as JsonObject
            assertEquals(1, evidence.size)
            assertEquals(1L, Py.int(entry["executed"]))
            assertEquals(0L, Py.int(entry["exit_code"]))
            assertTrue(Py.INVOCATION.matches(Py.str(entry["invocation_id"])!!))
            assertEquals(listOf("/bin/sh", "-c", script), (entry["command"] as kotlinx.serialization.json.JsonArray).map { Py.str(it) })
            assertTrue(ProbeManifest.executionSucceeded(evidence))
            val written = StrictJson.load(Fs.readText(directory.resolve("execution.json"))) as JsonObject
            assertEquals(evidence, written)
        } finally {
            deleteRecursively(directory)
        }
    }

    test("an unavailable lane records only its reason") {
        val directory = Files.createTempDirectory("execute-plan-unavailable")
        try {
            val plan = buildJsonObject {
                put(
                    lane.id,
                    buildJsonObject { put("unavailable_reason", JsonPrimitive("no device")) },
                )
            }
            val evidence = Execution.executePlan(plan, "a".repeat(40), directory.resolve("execution.json"))
            assertEquals(JsonObject(mapOf("unavailable_reason" to JsonPrimitive("no device"))), evidence.getValue(lane.id))
            assertFalse(ProbeManifest.executionSucceeded(evidence))
        } finally {
            deleteRecursively(directory)
        }
    }

    test("a plan without a command or result file is rejected per lane") {
        val directory = Files.createTempDirectory("execute-plan-invalid")
        try {
            val plan = buildJsonObject {
                put(lane.id, buildJsonObject { put("command", kotlinx.serialization.json.JsonArray(emptyList())) })
            }
            val evidence = Execution.executePlan(plan, "a".repeat(40), directory.resolve("execution.json"))
            assertEquals("no executable command", Py.str((evidence.getValue(lane.id) as JsonObject)["error"]))

            val missing = buildJsonObject {
                put(lane.id, buildJsonObject {
                    put("command", kotlinx.serialization.json.JsonArray(listOf(JsonPrimitive("true"))))
                })
            }
            val second = Execution.executePlan(missing, "a".repeat(40), directory.resolve("second.json"))
            assertEquals("result file path is missing", Py.str((second.getValue(lane.id) as JsonObject)["error"]))

            val directoryPath = Files.createTempDirectory("execute-plan-directory")
            val third = buildJsonObject {
                put(lane.id, buildJsonObject {
                    put("command", kotlinx.serialization.json.JsonArray(listOf(JsonPrimitive("true"))))
                    put("result_file", JsonPrimitive(directoryPath.toString()))
                })
            }
            val thirdEvidence = Execution.executePlan(third, "a".repeat(40), directory.resolve("third.json"))
            assertEquals("result file path is a directory", Py.str((thirdEvidence.getValue(lane.id) as JsonObject)["error"]))
            deleteRecursively(directoryPath)
        } finally {
            deleteRecursively(directory)
        }
    }

    test("a stale invocation ID is rejected") {
        val directory = Files.createTempDirectory("execute-plan-stale")
        try {
            val resultFile = directory.resolve("lane.json")
            val script = "printf '{\"invocation_id\":\"%s\"}' " + "0".repeat(32) + " > $resultFile"
            val plan = buildJsonObject {
                put(lane.id, buildJsonObject {
                    put("command", kotlinx.serialization.json.JsonArray(listOf(
                        JsonPrimitive("/bin/sh"), JsonPrimitive("-c"), JsonPrimitive(script),
                    )))
                    put("result_file", JsonPrimitive(resultFile.toString()))
                })
            }
            val evidence = Execution.executePlan(plan, "a".repeat(40), directory.resolve("execution.json"))
            assertEquals(
                "result invocation ID differs from execution",
                Py.str((evidence.getValue(lane.id) as JsonObject)["error"]),
            )
        } finally {
            deleteRecursively(directory)
        }
    }
}

/**
 * `stage.run_stage`.
 *
 * The staging task runs the Gradle wrapper from a clean checkout and records the console bytes.
 * A receipt may only claim `PASSED` when the console shows every publication task and a successful
 * build.
 */
val StagingRun by testSuite {
    test("a passing wrapper records a verified receipt") {
        withScriptedCheckout(passingWrapper()) { repository, sha ->
            val directory = Files.createTempDirectory("stage-run")
            try {
                val output = directory.resolve("receipt.json")
                val console = directory.resolve("stage.log")
                val receipt = Staging.run(repository, sha, listOf("jvm"), output, console)
                assertEquals("PASSED", Py.str(receipt["status"]))
                assertEquals(0L, Py.int(receipt["exit_code"]))
                assertEquals(listOf("jvm"), TestVectors.strings(receipt["targets"]))
                assertEquals(
                    StageReceipt.publicationTasks(listOf("jvm")),
                    TestVectors.strings(receipt["tasks"]),
                )
                assertEquals(Fs.digest(console), Py.str(receipt["console_sha256"]))
                assertEquals(
                    listOf("candidate_sha", "repository", "targets", "tasks", "command",
                        "exit_code", "console_sha256", "status"),
                    receipt.keys.toList(),
                )
                assertEquals(repository.toString(), Py.str(receipt["repository"]))
                assertEquals(Fs.readText(output), PyJson.render(receipt) + "\n")
                assertEquals("PASSED", Py.str(StrictJson.load(Fs.readText(output)).let { (it as JsonObject)["status"] }))
            } finally {
                deleteRecursively(directory)
            }
        }
    }

    test("a failing wrapper records a failed receipt without a reason") {
        withScriptedCheckout("#!/bin/sh\necho 'BUILD FAILED in 1s'\nexit 3\n") { repository, sha ->
            val directory = Files.createTempDirectory("stage-run-failed")
            try {
                val receipt = Staging.run(
                    repository, sha, listOf("jvm"),
                    directory.resolve("receipt.json"), directory.resolve("stage.log"),
                )
                assertEquals("FAILED", Py.str(receipt["status"]))
                assertEquals(3L, Py.int(receipt["exit_code"]))
                assertTrue("reason" !in receipt)
            } finally {
                deleteRecursively(directory)
            }
        }
    }

    test("a console that omits a publication task fails the receipt") {
        withScriptedCheckout(
            "#!/bin/sh\nfor a in \"\$@\"; do case \"\$a\" in :dyn4k-core:publishKotlinMultiplatform*) " +
                "echo \"> Task \$a\";; esac; done\necho 'BUILD SUCCESSFUL in 1s'\n",
        ) { repository, sha ->
            val directory = Files.createTempDirectory("stage-run-missing-task")
            try {
                val receipt = Staging.run(
                    repository, sha, listOf("jvm"),
                    directory.resolve("receipt.json"), directory.resolve("stage.log"),
                )
                assertEquals("FAILED", Py.str(receipt["status"]))
                assertEquals(
                    "staging console has a missing, skipped, or failed publication task",
                    Py.str(receipt["reason"]),
                )
                assertEquals(
                    listOf("candidate_sha", "repository", "targets", "tasks", "command",
                        "exit_code", "console_sha256", "status", "reason"),
                    receipt.keys.toList(),
                )
            } finally {
                deleteRecursively(directory)
            }
        }
    }

    test("a dirty checkout cannot stage") {
        withScriptedCheckout(passingWrapper()) { repository, sha ->
            repository.resolve("README.md").writeText("changed\n")
            val directory = Files.createTempDirectory("stage-run-dirty")
            try {
                val error = assertFailsWith<IllegalArgumentException> {
                    Staging.run(
                        repository, sha, listOf("jvm"),
                        directory.resolve("receipt.json"), directory.resolve("stage.log"),
                    )
                }
                assertTrue("dirty tracked checkout" in (error.message ?: ""), error.message)
            } finally {
                deleteRecursively(directory)
            }
        }
    }
}

private fun passingWrapper(): String =
    "#!/bin/sh\nfor a in \"\$@\"; do case \"\$a\" in :*) echo \"> Task \$a\";; esac; done\n" +
        "echo 'BUILD SUCCESSFUL in 1s'\n"

private fun withScriptedCheckout(script: String, block: (Path, String) -> Unit) {
    val repository = Files.createTempDirectory("stage-checkout")
    try {
        git(repository, "init", "-q")
        val wrapper = repository.resolve("gradlew")
        wrapper.writeText(script)
        Files.setPosixFilePermissions(wrapper, PosixFilePermissions.fromString("rwxr-xr-x"))
        repository.resolve("README.md").writeText("Staging fixture.\n")
        git(repository, "add", "-A")
        git(
            repository, "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
            "commit", "-qm", "base",
        )
        block(repository, git(repository, "rev-parse", "HEAD").trim())
    } finally {
        deleteRecursively(repository)
    }
}
