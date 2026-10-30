package io.github.rubixhacker.harness.qualification

import de.infix.testBalloon.framework.core.testSuite
import java.nio.file.Files
import java.nio.file.Path
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

private const val LOCK_FAILURE =
    "FAILURE: Build failed with an exception.\n" +
        "\n" +
        "* What went wrong:\n" +
        "Execution failed for task ':kotlinStoreYarnLock' (registered by plugin class " +
        "'org.jetbrains.kotlin.gradle.targets.js.yarn.YarnPlugin').\n" +
        "> Lock file was changed. Run the `kotlinUpgradeYarnLock` task to actualize lock file\n" +
        "\n" +
        "* Try:\n" +
        "> Run with --stacktrace option to get the stack trace.\n" +
        "> Run with --info or --debug option to get more log output.\n" +
        "\n" +
        "BUILD FAILED in 21s\n"

/** `SafariYarnLockTests.setUp`: the checkout the reference's capture cases run against. */
internal class SafariFixture(val root: Path = Files.createTempDirectory("safari-capture")) {
    val repository: Path = root.resolve("source")
    val output: Path = root.resolve("capture")
    var candidate: String

    init {
        Files.createDirectories(repository.resolve("kotlin-js-store"))
        Files.writeString(repository.resolve("kotlin-js-store/yarn.lock"), "tracked lock\n")
        Files.writeString(repository.resolve("gradlew"), "#!/bin/sh\n")
        Files.writeString(repository.resolve(".gitignore"), "build/\n")
        Files.writeString(repository.resolve("build.gradle.kts"), "plugins {}\n")
        Files.writeString(
            repository.resolve("settings.gradle.kts"),
            "rootProject.name = \"dyn4k\"\n",
        )
        Files.createDirectories(repository.resolve("gradle/wrapper"))
        Files.writeString(
            repository.resolve("gradle/wrapper/gradle-wrapper.properties"),
            "distributionUrl=gradle-9.5-bin.zip\n",
        )
        for (path in SafariYarnLockRules.SOURCE_INPUTS + SafariYarnLockRules.HOSTED_SOURCE_INPUTS) {
            val target = repository.resolve(path)
            target.parent?.let { Files.createDirectories(it) }
            val content = if (path.endsWith("safari-karma-reporter.js")) {
                "config.plugins = [];\n"
            } else {
                "// $path\n"
            }
            Files.writeString(target, content)
        }
        for (module in listOf("dyn4k-core", "dyn4k")) {
            Files.createDirectories(repository.resolve(module))
            Files.writeString(repository.resolve("$module/build.gradle.kts"), "plugins {}\n")
        }
        hostedGit(repository, "init", "-q")
        hostedGit(repository, "config", "--local", "core.autocrlf", "false")
        hostedGit(repository, "add", ".")
        commit("fixture")
        candidate = hostedGit(repository, "rev-parse", "HEAD")
    }

    fun commit(message: String): String {
        hostedGit(
            repository, "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
            "commit", "-qm", message,
        )
        return hostedGit(repository, "rev-parse", "HEAD")
    }

    /** `generated`: the workspace graph a real `kotlinNpmInstall`/store task leaves behind. */
    fun generated(data: String = "host generated lock\n", safari: Boolean = false) {
        val build = repository.resolve("build/js")
        Files.createDirectories(build)
        Files.writeString(build.resolve("yarn.lock"), data)
        val names = SafariYarnLockRules.REQUIRED_PACKAGES
        Files.writeString(
            build.resolve("package.json"),
            """{"name": "dyn4k", "workspaces": [""" +
                names.joinToString(", ") { "\"packages/$it\"" } + "]}\n",
        )
        for (name in names) {
            val packageJson = build.resolve("packages").resolve(name).resolve("package.json")
            Files.createDirectories(packageJson.parent)
            val value = if (safari && name.endsWith("-test")) {
                """{"name": "$name", "devDependencies": {"karma-safari-launcher": "1.0.0"}}"""
            } else {
                """{"name": "$name"}"""
            }
            Files.writeString(packageJson, value + "\n")
        }
    }

    fun writeLogs(folder: Path = output, stderr: String = LOCK_FAILURE) {
        Files.createDirectories(folder)
        Files.writeString(
            folder.resolve("stdout.txt"),
            "> Task :dyn4k-core:jsTestPackageJson\n" +
                "> Task :dyn4k:jsTestPackageJson\n" +
                "> Task :kotlinNpmInstall\n" +
                "> Task :kotlinStoreYarnLock FAILED\n",
        )
        Files.writeString(folder.resolve("stderr.txt"), stderr)
    }

    fun cleanup() {
        Files.walk(root).use { walk ->
            walk.sorted(Comparator.reverseOrder()).forEach { Files.deleteIfExists(it) }
        }
    }
}

private fun processRecord(
    command: List<String>,
    exitCode: Int,
    extras: Map<String, JsonElement> = emptyMap(),
): JsonObject = buildJsonObject {
    put("command", JsonArray(command.map { JsonPrimitive(it) }))
    put("pid", JsonPrimitive(123))
    put("exit_code", JsonPrimitive(exitCode))
    put("started_ns", JsonPrimitive(1))
    put("finished_ns", JsonPrimitive(2))
    for ((key, value) in extras) put(key, value)
}

private fun defaultLockCommand(repository: Path): List<String> = listOf(
    repository.resolve("gradlew").toString(),
    "--no-daemon",
    "--console=plain",
    "--rerun-tasks",
    ":kotlinStoreYarnLock",
)

private fun withFixture(block: (SafariFixture) -> Unit) {
    val fixture = SafariFixture()
    try {
        block(fixture)
    } finally {
        fixture.cleanup()
    }
}

/** The capture status ladder, driven through the reference's own seams. */
val SafariCaptureStatus by testSuite {
    test("a failed lock task captures the exact different bytes and inputs") {
        withFixture { fixture ->
            val receipt = SafariCapture.capture(
                fixture.repository,
                fixture.candidate,
                fixture.output,
                lockTask = { _, _, _ ->
                    fixture.generated()
                    fixture.writeLogs()
                    processRecord(defaultLockCommand(fixture.repository), 1)
                },
            )
            assertEquals("LOCK_MISMATCH_CAPTURED", Py.str(receipt["status"]))
            assertEquals(
                "tracked lock\n",
                Files.readString(fixture.output.resolve("tracked/kotlin-js-store/yarn.lock")),
            )
            assertEquals(
                "host generated lock\n",
                Files.readString(fixture.output.resolve("generated/build/js/yarn.lock")),
            )
            assertEquals(
                """{"name": "dyn4k-dyn4k-core-test"}""" + "\n",
                Files.readString(
                    fixture.output.resolve(
                        "generated/build/js/packages/dyn4k-dyn4k-core-test/package.json",
                    ),
                ),
            )
            assertTrue(
                Py.str(receipt["tracked_sha256"]) != Py.str(receipt["generated_sha256"]),
            )
            for (item in receipt["files"] as JsonArray) {
                val record = item as JsonObject
                if (record.containsKey("source_path")) {
                    assertEquals(
                        Py.str(record["source_path"]),
                        Py.str(record["source_realpath"]),
                    )
                }
            }
            val written = io.github.rubixhacker.harness.contract.StrictJson
                .load(Files.readString(fixture.output.resolve("receipt.json"))) as JsonObject
            assertEquals(fixture.candidate, Py.str(written["candidate_sha"]))
        }
    }

    test("a successful lock task stays diagnostic only") {
        withFixture { fixture ->
            val receipt = SafariCapture.capture(
                fixture.repository,
                fixture.candidate,
                fixture.output,
                lockTask = { _, _, _ ->
                    fixture.generated("tracked lock\n")
                    fixture.writeLogs(stderr = "")
                    processRecord(defaultLockCommand(fixture.repository), 0)
                },
            )
            assertEquals("LOCK_MATCHED_DIAGNOSTIC_ONLY", Py.str(receipt["status"]))
            assertEquals(false, Py.truthy(receipt["qualified"]))
        }
    }

    test("an unrelated Gradle failure cannot be called a lock mismatch") {
        withFixture { fixture ->
            val receipt = SafariCapture.capture(
                fixture.repository,
                fixture.candidate,
                fixture.output,
                lockTask = { _, _, _ ->
                    fixture.generated()
                    fixture.writeLogs(stderr = "Task failed for another reason\n")
                    processRecord(defaultLockCommand(fixture.repository), 1)
                },
            )
            assertEquals("OTHER_GRADLE_RESULT", Py.str(receipt["status"]))
        }
    }

    test("a truncated log cannot be labelled a complete mismatch") {
        withFixture { fixture ->
            val receipt = SafariCapture.capture(
                fixture.repository,
                fixture.candidate,
                fixture.output,
                lockTask = { _, _, _ ->
                    fixture.generated()
                    fixture.writeLogs()
                    processRecord(
                        defaultLockCommand(fixture.repository),
                        1,
                        mapOf(
                            "stdout_truncated" to JsonPrimitive(true),
                            "stderr_truncated" to JsonPrimitive(false),
                            "timed_out" to JsonPrimitive(false),
                        ),
                    )
                },
            )
            assertEquals("INCOMPLETE_LOG_CAPTURE", Py.str(receipt["status"]))
            assertEquals(false, Py.truthy(receipt["qualified"]))
        }
    }

    test("a missing generated lock is explicitly incomplete") {
        withFixture { fixture ->
            val receipt = SafariCapture.capture(
                fixture.repository,
                fixture.candidate,
                fixture.output,
                lockTask = { _, _, _ ->
                    fixture.writeLogs()
                    processRecord(defaultLockCommand(fixture.repository), 1)
                },
            )
            assertEquals("NO_GENERATED_LOCK", Py.str(receipt["status"]))
            assertFalse(Files.exists(fixture.output.resolve("generated/build/js/yarn.lock")))
        }
    }

    test("missing root or all workspace packages is incomplete") {
        for (absent in listOf("all", "root")) {
            val fixture = SafariFixture()
            try {
                val output = fixture.root.resolve("capture-$absent")
                val receipt = SafariCapture.capture(
                    fixture.repository,
                    fixture.candidate,
                    output,
                    lockTask = { _, _, _ ->
                        fixture.generated()
                        if (absent == "all") {
                            fixture.repository.resolve("build/js/packages").toFile().deleteRecursively()
                        } else {
                            Files.delete(fixture.repository.resolve("build/js/package.json"))
                        }
                        fixture.writeLogs(output)
                        processRecord(defaultLockCommand(fixture.repository), 1)
                    },
                )
                assertEquals("INCOMPLETE_PACKAGE_GRAPH", Py.str(receipt["status"]), absent)
                assertTrue(Py.truthy(receipt["missing_package_inputs"]), absent)
                assertEquals(false, Py.truthy(receipt["qualified"]), absent)
            } finally {
                fixture.cleanup()
            }
        }
    }

    test("a malformed workspace graph is incomplete with a receipt") {
        withFixture { fixture ->
            val receipt = SafariCapture.capture(
                fixture.repository,
                fixture.candidate,
                fixture.output,
                lockTask = { _, _, _ ->
                    fixture.generated()
                    Files.writeString(
                        fixture.repository.resolve("build/js/package.json"),
                        """{"name":"dyn4k","workspaces":[{}]}""" + "\n",
                    )
                    fixture.writeLogs()
                    processRecord(defaultLockCommand(fixture.repository), 1)
                },
            )
            assertEquals("INCOMPLETE_PACKAGE_GRAPH", Py.str(receipt["status"]))
            assertEquals(
                listOf("root package workspaces differ"),
                (receipt["package_graph_errors"] as JsonArray).map { Py.str(it) },
            )
            assertTrue(Files.isRegularFile(fixture.output.resolve("receipt.json")))
        }
    }

    test("a clean checkout swap during the task rejects the original candidate") {
        withFixture { fixture ->
            Files.writeString(fixture.repository.resolve("build.gradle.kts"), "plugins { swapped }\n")
            hostedGit(fixture.repository, "add", "build.gradle.kts")
            val swapped = fixture.commit("swapped")
            hostedGit(fixture.repository, "checkout", "-q", fixture.candidate)
            val receipt = SafariCapture.capture(
                fixture.repository,
                fixture.candidate,
                fixture.output,
                lockTask = { _, _, _ ->
                    fixture.generated()
                    fixture.writeLogs()
                    hostedGit(fixture.repository, "checkout", "-q", swapped)
                    processRecord(defaultLockCommand(fixture.repository), 1)
                },
            )
            assertEquals("SOURCE_CHANGED", Py.str(receipt["status"]))
            assertEquals(swapped, Py.str(receipt["head_after"]))
            assertEquals(false, Py.truthy(receipt["qualified"]))
        }
    }

    test("a source mutation during the task is not a clean capture") {
        withFixture { fixture ->
            val receipt = SafariCapture.capture(
                fixture.repository,
                fixture.candidate,
                fixture.output,
                lockTask = { _, _, _ ->
                    fixture.generated()
                    fixture.writeLogs()
                    Files.writeString(
                        fixture.repository.resolve("kotlin-js-store/yarn.lock"),
                        "mutated\n",
                    )
                    processRecord(defaultLockCommand(fixture.repository), 1)
                },
            )
            assertEquals("SOURCE_CHANGED", Py.str(receipt["status"]))
            assertEquals(
                "mutated\n",
                Files.readString(fixture.output.resolve("tracked-after/kotlin-js-store/yarn.lock")),
            )
        }
    }

    test("a generated lock change during capture rejects the stale copy") {
        withFixture { fixture ->
            val receipt = SafariCapture.capture(
                fixture.repository,
                fixture.candidate,
                fixture.output,
                lockTask = { _, _, _ ->
                    fixture.generated()
                    fixture.writeLogs()
                    processRecord(defaultLockCommand(fixture.repository), 1)
                },
                afterPackageGraph = {
                    Files.writeString(fixture.repository.resolve("build/js/yarn.lock"), "changed again\n")
                },
            )
            assertEquals("CAPTURE_REJECTED", Py.str(receipt["status"]))
            assertTrue("generated input changed" in (Py.str(receipt["reason"]) ?: ""))
        }
    }

    test("a generated build or package symlink ancestor is rejected") {
        for (ancestor in listOf("build/js", "build/js/packages/dyn4k-dyn4k-core-test")) {
            val fixture = SafariFixture()
            try {
                val output = fixture.root.resolve("capture-${ancestor.replace('/', '-')}")
                val receipt = SafariCapture.capture(
                    fixture.repository,
                    fixture.candidate,
                    output,
                    lockTask = { _, _, _ ->
                        fixture.generated()
                        val path = fixture.repository.resolve(ancestor)
                        val outside = fixture.root.resolve("outside-${ancestor.replace('/', '-')}")
                        Files.move(path, outside)
                        Files.createSymbolicLink(path, outside)
                        fixture.writeLogs(output)
                        processRecord(defaultLockCommand(fixture.repository), 1)
                    },
                )
                assertEquals("CAPTURE_REJECTED", Py.str(receipt["status"]), ancestor)
                assertTrue("symlink" in (Py.str(receipt["reason"]) ?: ""), ancestor)
                assertEquals(false, Py.truthy(receipt["qualified"]), ancestor)
            } finally {
                fixture.cleanup()
            }
        }
    }

    test("preexisting generated lock and in-tree output are rejected before running") {
        withFixture { fixture ->
            fixture.generated()
            var launched = false
            assertFailsWith<IllegalArgumentException> {
                SafariCapture.capture(
                    fixture.repository,
                    fixture.candidate,
                    fixture.output,
                    lockTask = { _, _, _ ->
                        launched = true
                        processRecord(defaultLockCommand(fixture.repository), 1)
                    },
                )
            }
            Files.delete(fixture.repository.resolve("build/js/yarn.lock"))
            val error = assertFailsWith<IllegalArgumentException> {
                SafariCapture.capture(
                    fixture.repository,
                    fixture.candidate,
                    fixture.repository.resolve("build/capture"),
                    lockTask = { _, _, _ ->
                        launched = true
                        processRecord(defaultLockCommand(fixture.repository), 1)
                    },
                )
            }
            assertTrue("outside the source" in (error.message ?: ""))
            assertEquals(false, launched)
        }
    }

    test("a candidate and source drift are rejected before running") {
        withFixture { fixture ->
            var launched = false
            val lockTask = SafariCapture.LockTask { _, _, _ ->
                launched = true
                processRecord(defaultLockCommand(fixture.repository), 1)
            }
            assertTrue(
                "candidate SHA" in (
                    assertFailsWith<IllegalArgumentException> {
                        SafariCapture.capture(
                            fixture.repository,
                            "a".repeat(40),
                            fixture.output,
                            lockTask = lockTask,
                        )
                    }.message ?: ""
                    ),
            )
            Files.writeString(fixture.repository.resolve("build.gradle.kts"), "plugins { altered }\n")
            assertTrue(
                "dirty tracked" in (
                    assertFailsWith<IllegalArgumentException> {
                        SafariCapture.capture(
                            fixture.repository,
                            fixture.candidate,
                            fixture.output,
                            lockTask = lockTask,
                        )
                    }.message ?: ""
                    ),
            )
            assertEquals(false, launched)
        }
    }

    test("a clean checkout swap after the package graph rejects the original candidate") {
        withFixture { fixture ->
            Files.writeString(fixture.repository.resolve("new-source.kt"), "fun changed() = true\n")
            hostedGit(fixture.repository, "add", "new-source.kt")
            val swapped = fixture.commit("source")
            hostedGit(fixture.repository, "checkout", "-q", fixture.candidate)
            val receipt = SafariCapture.capture(
                fixture.repository,
                fixture.candidate,
                fixture.output,
                lockTask = { _, _, _ ->
                    fixture.generated()
                    fixture.writeLogs()
                    processRecord(defaultLockCommand(fixture.repository), 1)
                },
                afterPackageGraph = {
                    hostedGit(fixture.repository, "checkout", "-q", swapped)
                },
            )
            assertEquals("SOURCE_CHANGED", Py.str(receipt["status"]))
            assertEquals(swapped, Py.str(receipt["head_after"]))
        }
    }

    test("a non-lock source mutation during the task is not a clean capture") {
        withFixture { fixture ->
            val receipt = SafariCapture.capture(
                fixture.repository,
                fixture.candidate,
                fixture.output,
                lockTask = { _, _, _ ->
                    fixture.generated()
                    fixture.writeLogs()
                    Files.writeString(fixture.repository.resolve("build.gradle.kts"), "plugins { altered }\n")
                    processRecord(defaultLockCommand(fixture.repository), 1)
                },
            )
            assertEquals("SOURCE_CHANGED", Py.str(receipt["status"]))
        }
    }

    test("a quoted lock phrase with an unrelated failure is not a mismatch") {
        withFixture { fixture ->
            val receipt = SafariCapture.capture(
                fixture.repository,
                fixture.candidate,
                fixture.output,
                lockTask = { _, _, _ ->
                    fixture.generated()
                    fixture.writeLogs(
                        stderr = "Some log quoted: Lock file was changed. Run the " +
                            "`kotlinUpgradeYarnLock` task\n" +
                            "Execution failed for unrelated plugin\n",
                    )
                    processRecord(defaultLockCommand(fixture.repository), 1)
                },
            )
            assertEquals("OTHER_GRADLE_RESULT", Py.str(receipt["status"]))
        }
    }

    test("the real lock task captures a child-free mismatch end to end") {
        withFixture { fixture ->
            val wrapper = fixture.repository.resolve("gradlew")
            Files.writeString(wrapper, realLockWrapper())
            Files.setPosixFilePermissions(
                wrapper,
                java.nio.file.attribute.PosixFilePermissions.fromString("rwxr-xr-x"),
            )
            hostedGit(fixture.repository, "add", "gradlew")
            val candidate = fixture.commit("real lock wrapper fixture")
            val receipt = SafariCapture.capture(fixture.repository, candidate, fixture.output)
            assertEquals("LOCK_MISMATCH_CAPTURED", Py.str(receipt["status"]))
            val process = receipt["process"] as JsonObject
            assertEquals(false, Py.truthy(process["stream_incomplete"]))
            assertEquals(false, Py.truthy(process["timed_out"]))
            assertEquals(1L, Py.int(process["exit_code"]))
            assertTrue(Py.truthy(receipt["generated_sha256"]))
        }
    }

    test("a failed process records the capture failure with the archive it made") {
        withFixture { fixture ->
            val receipt = SafariCapture.capture(
                fixture.repository,
                fixture.candidate,
                fixture.output,
                configuration = "development",
                lockTask = { _, _, _ ->
                    throw SafariFileError("injected launch failure")
                },
            )
            assertEquals("PROCESS_CAPTURE_FAILED", Py.str(receipt["status"]))
            assertEquals("injected launch failure", Py.str(receipt["reason"]))
            assertEquals("CLEAN", Py.str((receipt["reporter_stage"] as JsonObject)["status"]))
            assertFalse(Files.exists(fixture.repository.resolve("dyn4k-core/karma.config.d")))
            assertFalse(Files.exists(fixture.repository.resolve("dyn4k/karma.config.d")))
            assertTrue(Files.isRegularFile(fixture.output.resolve("receipt.json")))
        }
    }
}

/** The hosted half of the ladder and the audit. */
val SafariHostedCapture by testSuite {
    test("the hosted capture stages and binds the reporter source") {
        withFixture { fixture ->
            val reporter = fixture.repository.resolve("tools/qualification/safari-karma-reporter.js")
            val receipt = SafariCapture.capture(
                fixture.repository,
                fixture.candidate,
                fixture.output,
                configuration = "development",
                lockTask = { repository, _, command ->
                    for (module in listOf("dyn4k-core", "dyn4k")) {
                        assertEquals(
                            Files.readAllBytes(reporter).toList(),
                            Files.readAllBytes(
                                repository.resolve(
                                    "$module/karma.config.d/qualification-safari-reporter.js",
                                ),
                            ).toList(),
                        )
                    }
                    fixture.generated(safari = true)
                    fixture.writeLogs()
                    processRecord(command!!, 1)
                },
            )
            assertEquals("LOCK_MISMATCH_CAPTURED", Py.str(receipt["status"]))
            assertEquals("development", Py.str(receipt["configuration"]))
            val digests = receipt["source_input_sha256"] as JsonObject
            assertEquals(
                io.github.rubixhacker.harness.contract.Sha256.of(Files.readAllBytes(reporter)),
                Py.str(digests["tools/qualification/safari-karma-reporter.js"]),
            )
            assertTrue(
                Files.readAllBytes(
                    fixture.output.resolve("inputs/tools/qualification/safari-karma-reporter.js"),
                ).contentEquals(Files.readAllBytes(reporter)),
            )
            for (relative in listOf(
                "tools/qualification/safari-launch.sh",
                "docs/archive/hosted-macos-workflows/safari-yarn-lock-diagnostic.yml",
            )) {
                assertEquals(
                    io.github.rubixhacker.harness.contract.Sha256.of(
                        Files.readAllBytes(fixture.repository.resolve(relative)),
                    ),
                    Py.str(digests[relative]),
                )
            }
            for (module in listOf("dyn4k-core", "dyn4k")) {
                assertFalse(Files.exists(fixture.repository.resolve("$module/karma.config.d")))
            }
        }
    }

    test("the hosted command is bound and a wrong one is rejected") {
        withFixture { fixture ->
            var seen: List<String>? = null
            val receipt = SafariCapture.capture(
                fixture.repository,
                fixture.candidate,
                fixture.output,
                configuration = "development",
                lockTask = { _, _, command ->
                    seen = command
                    fixture.generated(safari = true)
                    fixture.writeLogs()
                    processRecord(
                        listOf(fixture.repository.resolve("gradlew").toString(), ":kotlinStoreYarnLock"),
                        1,
                    )
                },
            )
            assertEquals("PROCESS_BINDING_REJECTED", Py.str(receipt["status"]))
            val expected = SafariYarnLockRules.fullHostedCommand(
                fixture.repository.toString(),
                fixture.output.resolve("development/qualification.init.gradle").toString(),
                "development",
                Py.str(receipt["invocation_id"])!!,
            )
            assertEquals(expected, seen)
            assertTrue("--init-script" in expected)
        }
    }

    test("a changed init script rejects the capture") {
        withFixture { fixture ->
            val receipt = SafariCapture.capture(
                fixture.repository,
                fixture.candidate,
                fixture.output,
                configuration = "development",
                lockTask = { _, output, command ->
                    fixture.generated(safari = true)
                    fixture.writeLogs()
                    Files.writeString(
                        output.resolve("development/qualification.init.gradle"),
                        "// changed\n",
                    )
                    processRecord(command!!, 1)
                },
            )
            assertEquals("CAPTURE_REJECTED", Py.str(receipt["status"]))
        }
    }

    test("a changed reporter source during the task is a source change") {
        withFixture { fixture ->
            val receipt = SafariCapture.capture(
                fixture.repository,
                fixture.candidate,
                fixture.output,
                configuration = "development",
                lockTask = { repository, _, command ->
                    fixture.generated(safari = true)
                    fixture.writeLogs()
                    Files.writeString(
                        repository.resolve("tools/qualification/safari-karma-reporter.js"),
                        "config.plugins = [];\n// changed\n",
                    )
                    processRecord(command!!, 1)
                },
            )
            assertEquals("SOURCE_CHANGED", Py.str(receipt["status"]))
            for (module in listOf("dyn4k-core", "dyn4k")) {
                assertFalse(Files.exists(fixture.repository.resolve("$module/karma.config.d")))
            }
        }
    }

    test("a changed staged reporter is rejected for both modules") {
        for (module in listOf("dyn4k-core", "dyn4k")) {
            val fixture = SafariFixture()
            try {
                val output = fixture.root.resolve("capture-$module")
                val changed = "config.plugins = [];\n// tampered\n"
                val receipt = SafariCapture.capture(
                    fixture.repository,
                    fixture.candidate,
                    output,
                    configuration = "development",
                    lockTask = { repository, destination, command ->
                        fixture.generated("tracked lock\n", safari = true)
                        Files.writeString(
                            destination.resolve("stdout.txt"),
                            "> Task :dyn4k-core:jsTestPackageJson\n" +
                                "> Task :dyn4k:jsTestPackageJson\n" +
                                "> Task :kotlinNpmInstall\n" +
                                "> Task :kotlinStoreYarnLock\n",
                        )
                        Files.writeString(destination.resolve("stderr.txt"), "")
                        Files.writeString(
                            repository.resolve("$module/karma.config.d/qualification-safari-reporter.js"),
                            changed,
                        )
                        processRecord(
                            command!!,
                            0,
                            mapOf(
                                "stdout_bytes_seen" to JsonPrimitive(129),
                                "stderr_bytes_seen" to JsonPrimitive(0),
                                "stdout_truncated" to JsonPrimitive(false),
                                "stderr_truncated" to JsonPrimitive(false),
                                "timed_out" to JsonPrimitive(false),
                                "stream_incomplete" to JsonPrimitive(false),
                            ),
                        )
                    },
                )
                assertEquals("STAGED_REPORTER_CHANGED", Py.str(receipt["status"]), module)
                assertEquals(
                    changed,
                    Files.readString(
                        output.resolve(
                            "forensic/safari-reporter/$module/qualification-safari-reporter.js",
                        ),
                    ),
                )
                assertFalse(Files.exists(fixture.repository.resolve("$module/karma.config.d")))
            } finally {
                fixture.cleanup()
            }
        }
    }

    test("the Safari capture timeout and output overflow are explicit statuses") {
        withFixture { fixture ->
            val timeout = SafariCapture.capture(
                fixture.repository,
                fixture.candidate,
                fixture.output,
                configuration = "development",
                lockTask = { _, output, command ->
                    fixture.generated("tracked lock\n", safari = true)
                    Files.writeString(
                        output.resolve("stdout.txt"),
                        "> Task :dyn4k-core:jsTestPackageJson\n" +
                            "> Task :dyn4k:jsTestPackageJson\n" +
                            "> Task :kotlinNpmInstall\n" +
                            "> Task :kotlinStoreYarnLock\n" +
                            "> Task :dyn4k:jsBrowserTest\n" +
                            "Safari has not captured in 60000 ms, killing.\n" +
                            "> Task :dyn4k:jsBrowserTest FAILED\n",
                    )
                    Files.writeString(
                        output.resolve("stderr.txt"),
                        "Safari failed 2 times (timeout). Giving up.\n" +
                            "Execution failed for task ':dyn4k:jsBrowserTest'.\n" +
                            "> Errors occurred during launch of browser for testing.\n",
                    )
                    processRecord(command!!, 1, streamingFlags(184, 176))
                },
            )
            assertEquals("SAFARI_CAPTURE_TIMEOUT", Py.str(timeout["status"]))
            assertEquals(false, Py.truthy(timeout["qualified"]))
        }
        withFixture { fixture ->
            val overflow = SafariCapture.capture(
                fixture.repository,
                fixture.candidate,
                fixture.output,
                configuration = "development",
                lockTask = { _, output, command ->
                    fixture.generated("tracked lock\n", safari = true)
                    Files.writeString(
                        output.resolve("stdout.txt"),
                        "> Task :dyn4k-core:jsTestPackageJson\n" +
                            "> Task :dyn4k:jsTestPackageJson\n" +
                            "> Task :kotlinNpmInstall\n" +
                            "> Task :kotlinStoreYarnLock\n" +
                            "> Task :dyn4k-core:jsBrowserTest FAILED\n",
                    )
                    Files.writeString(
                        output.resolve("stderr.txt"),
                        "##teamcity[testFailed name='overflow-message' message='" +
                            "Cannot process output: too long teamcity service message " +
                            "(more than 1Mb). Event was lost.\n",
                    )
                    processRecord(command!!, 1, streamingFlags(166, 130))
                },
            )
            assertEquals("SAFARI_TEST_OUTPUT_OVERFLOW", Py.str(overflow["status"]))
            assertEquals(false, Py.truthy(overflow["qualified"]))
        }
    }

    test("a Chrome-only package graph cannot match Safari") {
        withFixture { fixture ->
            val receipt = SafariCapture.capture(
                fixture.repository,
                fixture.candidate,
                fixture.output,
                configuration = "development",
                lockTask = { _, _, command ->
                    fixture.generated()
                    fixture.writeLogs()
                    processRecord(command!!, 1)
                },
            )
            assertEquals("INCOMPLETE_PACKAGE_GRAPH", Py.str(receipt["status"]))
        }
    }

    test("a hosted source failure is not a browser capture timeout") {
        withFixture { fixture ->
            val receipt = SafariCapture.capture(
                fixture.repository,
                fixture.candidate,
                fixture.output,
                configuration = "development",
                lockTask = { _, output, command ->
                    fixture.generated("tracked lock\n", safari = true)
                    Files.writeString(
                        output.resolve("stdout.txt"),
                        "> Task :dyn4k-core:jsTestPackageJson\n" +
                            "> Task :dyn4k:jsTestPackageJson\n" +
                            "> Task :kotlinNpmInstall\n" +
                            "> Task :kotlinStoreYarnLock\n" +
                            "> Task :dyn4k:jsBrowserTest FAILED\n",
                    )
                    Files.writeString(
                        output.resolve("stderr.txt"),
                        "Execution failed for task ':dyn4k:jsBrowserTest'.\n" +
                            "> Test assertion failed.\n",
                    )
                    processRecord(command!!, 1, streamingFlags(166, 84))
                },
            )
            assertEquals("OTHER_GRADLE_RESULT", Py.str(receipt["status"]))
            assertEquals(false, Py.truthy(receipt["qualified"]))
        }
    }

    test("an unowned config leftover is rejected as staged reporter residue") {
        withFixture { fixture ->
            val leftover = fixture.repository.resolve("dyn4k-core/karma.config.d/extra.js")
            val receipt = SafariCapture.capture(
                fixture.repository,
                fixture.candidate,
                fixture.output,
                configuration = "development",
                lockTask = { _, destination, command ->
                    fixture.generated("tracked lock\n", safari = true)
                    Files.writeString(destination.resolve("stdout.txt"), "> Task :kotlinStoreYarnLock\n")
                    Files.writeString(destination.resolve("stderr.txt"), "")
                    Files.writeString(leftover, "other config\n")
                    processRecord(command!!, 0, streamingFlags(33, 0))
                },
            )
            assertEquals("STAGED_REPORTER_CHANGED", Py.str(receipt["status"]))
            val stage = receipt["reporter_stage"] as JsonObject
            assertEquals("LEFTOVER", Py.str((stage["projects"] as JsonObject)["dyn4k-core"]))
            assertEquals(
                "other config\n",
                Files.readString(
                    fixture.output.resolve("forensic/safari-reporter/dyn4k-core/extra.js"),
                ),
            )
            assertFalse(Files.exists(fixture.repository.resolve("dyn4k/karma.config.d")))
        }
    }

    test("the audit accepts a hosted capture and rejects each resealed mutation") {
        fun hosted(fixture: SafariFixture): JsonObject = SafariCapture.capture(
            fixture.repository,
            fixture.candidate,
            fixture.output,
            configuration = "development",
            lockTask = { _, output, command ->
                fixture.generated(safari = true)
                fixture.writeLogs()
                val stdout = Files.size(output.resolve("stdout.txt"))
                val stderr = Files.size(output.resolve("stderr.txt"))
                processRecord(command!!, 1, streamingFlags(stdout, stderr))
            },
        )

        withFixture { fixture ->
            assertEquals("LOCK_MISMATCH_CAPTURED", Py.str(hosted(fixture)["status"]))
            assertEquals(
                "LOCK_MISMATCH_CAPTURED",
                Py.str(SafariCapture.auditCapture(fixture.repository, fixture.candidate, fixture.output)["status"]),
            )
        }
        for (mutation in listOf("candidate", "command", "process", "raw")) {
            withFixture { fixture ->
                hosted(fixture)
                val saved = Files.readAllBytes(fixture.output.resolve("receipt.json"))
                val raw = fixture.output.resolve("generated/build/js/yarn.lock")
                val rawSaved = Files.readAllBytes(raw)
                val record = io.github.rubixhacker.harness.contract.StrictJson
                    .load(String(saved)) as JsonObject
                val changed = LinkedHashMap(record)
                when (mutation) {
                    "candidate" -> changed["candidate_sha"] = JsonPrimitive("a".repeat(40))
                    "command" -> {
                        val process = LinkedHashMap(record["process"] as JsonObject)
                        process["command"] = JsonArray(
                            (process["command"] as JsonArray).filter {
                                Py.str(it) != "--init-script"
                            },
                        )
                        changed["process"] = JsonObject(process)
                    }
                    "process" -> {
                        val process = LinkedHashMap(record["process"] as JsonObject)
                        process["pid"] = JsonPrimitive(0)
                        changed["process"] = JsonObject(process)
                    }
                    else -> Files.writeString(raw, "tampered lock\n")
                }
                Files.writeString(fixture.output.resolve("receipt.json"), JsonObject(changed).toString())
                assertFailsWith<IllegalArgumentException>(mutation) {
                    SafariCapture.auditCapture(fixture.repository, fixture.candidate, fixture.output)
                }
                Files.write(fixture.output.resolve("receipt.json"), saved)
                Files.write(raw, rawSaved)
            }
        }
    }

    test("the audit rejects a legacy workflow path and resealed archived bytes") {
        withFixture { fixture ->
            captureHosted(fixture)
            val archived = "docs/archive/hosted-macos-workflows/safari-yarn-lock-diagnostic.yml"
            val legacy = ".github/workflows/safari-yarn-lock-diagnostic.yml"
            val old = fixture.output.resolve("inputs").resolve(archived)
            val moved = fixture.output.resolve("inputs").resolve(legacy)
            Files.createDirectories(moved.parent)
            Files.move(old, moved)
            val receiptPath = fixture.output.resolve("receipt.json")
            val receipt = io.github.rubixhacker.harness.contract.StrictJson
                .load(Files.readString(receiptPath)) as JsonObject
            val files = (receipt["files"] as JsonArray).map { item ->
                val record = LinkedHashMap(item as JsonObject)
                if (Py.str(record["path"]) == "inputs/$archived") record["path"] = JsonPrimitive("inputs/$legacy")
                JsonObject(record)
            }
            val changed = LinkedHashMap(receipt)
            changed["files"] = JsonArray(files)
            Files.writeString(receiptPath, JsonObject(changed).toString())
            assertTrue(
                "file inventory differs" in (
                    assertFailsWith<IllegalArgumentException> {
                        SafariCapture.auditCapture(fixture.repository, fixture.candidate, fixture.output)
                    }.message ?: ""
                    ),
            )
        }
        withFixture { fixture ->
            captureHosted(fixture)
            val archived = "docs/archive/hosted-macos-workflows/safari-yarn-lock-diagnostic.yml"
            val path = fixture.output.resolve("inputs").resolve(archived)
            Files.write(path, Files.readAllBytes(path) + "# changed after capture\n".toByteArray())
            val receiptPath = fixture.output.resolve("receipt.json")
            val receipt = io.github.rubixhacker.harness.contract.StrictJson
                .load(Files.readString(receiptPath)) as JsonObject
            val files = (receipt["files"] as JsonArray).map { item ->
                val record = LinkedHashMap(item as JsonObject)
                if (Py.str(record["path"]) == "inputs/$archived") {
                    record["sha256"] = JsonPrimitive(
                        io.github.rubixhacker.harness.contract.Sha256.of(Files.readAllBytes(path)),
                    )
                    record["size"] = JsonPrimitive(Files.size(path))
                }
                JsonObject(record)
            }
            val changed = LinkedHashMap(receipt)
            changed["files"] = JsonArray(files)
            Files.writeString(receiptPath, JsonObject(changed).toString())
            assertTrue(
                "archived source differs" in (
                    assertFailsWith<IllegalArgumentException> {
                        SafariCapture.auditCapture(fixture.repository, fixture.candidate, fixture.output)
                    }.message ?: ""
                    ),
            )
        }
    }

    test("the audit rejects a resealed Chrome-only package") {
        withFixture { fixture ->
            captureHosted(fixture)
            val name = "dyn4k-dyn4k-core-test"
            val path = fixture.output.resolve("generated/build/js/packages/$name/package.json")
            val packageJson = LinkedHashMap(
                io.github.rubixhacker.harness.contract.StrictJson
                    .load(Files.readString(path)) as JsonObject,
            )
            packageJson.remove("devDependencies")
            Files.writeString(path, JsonObject(packageJson).toString())
            val receiptPath = fixture.output.resolve("receipt.json")
            val receipt = io.github.rubixhacker.harness.contract.StrictJson
                .load(Files.readString(receiptPath)) as JsonObject
            val files = (receipt["files"] as JsonArray).map { item ->
                val record = LinkedHashMap(item as JsonObject)
                if (Py.str(record["path"]) == "generated/build/js/packages/$name/package.json") {
                    record["sha256"] = JsonPrimitive(
                        io.github.rubixhacker.harness.contract.Sha256.of(Files.readAllBytes(path)),
                    )
                    record["size"] = JsonPrimitive(Files.size(path))
                }
                JsonObject(record)
            }
            val changed = LinkedHashMap(receipt)
            changed["files"] = JsonArray(files)
            Files.writeString(receiptPath, JsonObject(changed).toString())
            assertTrue(
                "Safari package" in (
                    assertFailsWith<IllegalArgumentException> {
                        SafariCapture.auditCapture(fixture.repository, fixture.candidate, fixture.output)
                    }.message ?: ""
                    ),
            )
        }
    }

    test("the CLI audits a capture and reports the status") {
        withFixture { fixture ->
            captureHosted(fixture)
            val printed = StringBuilder()
            val code = captureStdout(printed) {
                SafariCaptureCli.run(
                    arrayOf(
                        "--candidate-sha", fixture.candidate,
                        "--output", fixture.output.toString(),
                        "--audit",
                    ),
                    fixture.repository,
                )
            }
            assertEquals(0, code)
            assertTrue("\"status\": \"LOCK_MISMATCH_CAPTURED\"" in printed.toString())
            assertTrue("\"qualified\": false" in printed.toString())
            assertEquals(
                2,
                SafariCaptureCli.run(arrayOf("--output", fixture.output.toString()), fixture.repository),
            )
            // The capture form of the CLI: a committed gradlew that writes nothing is NO_GENERATED_LOCK.
            fixture.repository.resolve("build").toFile().deleteRecursively()
            val wrapper = fixture.repository.resolve("gradlew")
            Files.setPosixFilePermissions(
                wrapper,
                java.nio.file.attribute.PosixFilePermissions.fromString("rwxr-xr-x"),
            )
            hostedGit(fixture.repository, "add", "gradlew")
            val candidate = fixture.commit("silent wrapper")
            val capturePrinted = StringBuilder()
            val captureCode = captureStdout(capturePrinted) {
                SafariCaptureCli.run(
                    arrayOf(
                        "--candidate-sha", candidate,
                        "--output", fixture.root.resolve("second").toString(),
                    ),
                    fixture.repository,
                )
            }
            assertEquals(1, captureCode, capturePrinted.toString())
            assertTrue(
                "\"status\": \"NO_GENERATED_LOCK\"" in capturePrinted.toString(),
                capturePrinted.toString(),
            )
            assertEquals(
                2,
                SafariCaptureCli.run(
                    arrayOf(
                        "--candidate-sha", fixture.candidate,
                        "--output", fixture.output.toString(),
                        "--input-context", fixture.root.toString(),
                    ),
                    fixture.repository,
                ),
            )
        }
    }
}

/** `capture_package_graph` and `hosted_expected_files` on their own. */
val SafariPackageGraphSuite by testSuite {
    test("the archive inventory uses posix separators for every member") {
        val expected = SafariYarnLockRules.hostedExpectedFiles(
            "development",
            "kotlin-js-store/yarn.lock",
            "build/js/yarn.lock",
            listOf("kotlin-js-store/yarn.lock", "tools/qualification/safari-launch.sh"),
            listOf("build/js/package.json"),
        )
        assertTrue("tracked/kotlin-js-store/yarn.lock" in expected)
        assertTrue("inputs/tools/qualification/safari-launch.sh" in expected)
        assertTrue("generated/build/js/package.json" in expected)
        assertTrue(expected.all { '\\' !in it })
        assertEquals(8, expected.size)
    }

    test("the package graph records the workspace contract and the Safari launcher") {
        withFixture { fixture ->
            fixture.generated(safari = true)
            val files = mutableListOf<JsonObject>()
            val receipt = LinkedHashMap<String, JsonElement>()
            receipt["configuration"] = JsonPrimitive("development")
            capturePackageGraph(fixture.repository, fixture.output, files, receipt)
            assertEquals(
                SafariYarnLockRules.REQUIRED_PACKAGE_INPUTS,
                (receipt["package_inputs_expected"] as JsonArray).map { Py.str(it) },
            )
            assertEquals(
                listOf(
                    "build/js/package.json",
                    "build/js/packages/dyn4k-dyn4k/package.json",
                    "build/js/packages/dyn4k-dyn4k-core/package.json",
                    "build/js/packages/dyn4k-dyn4k-core-test/package.json",
                    "build/js/packages/dyn4k-dyn4k-test/package.json",
                ),
                (receipt["package_inputs_observed"] as JsonArray).map { Py.str(it) },
            )
            assertEquals(0, (receipt["missing_package_inputs"] as JsonArray).size)
            assertEquals(0, (receipt["unexpected_package_inputs"] as JsonArray).size)
            assertEquals(false, Py.truthy(receipt["package_count_exceeds_bound"]))
            assertEquals(0, (receipt["package_graph_errors"] as JsonArray).size)
            assertEquals(5, files.size)
        }
    }

    test("the package graph records a differing name and a missing launcher") {
        withFixture { fixture ->
            fixture.generated(safari = false)
            Files.writeString(
                fixture.repository.resolve("build/js/packages/dyn4k-dyn4k-test/package.json"),
                """{"name": "wrong"}""" + "\n",
            )
            val files = mutableListOf<JsonObject>()
            val receipt = LinkedHashMap<String, JsonElement>()
            receipt["configuration"] = JsonPrimitive("development")
            capturePackageGraph(fixture.repository, fixture.output, files, receipt)
            assertEquals(
                listOf(
                    "package name differs: build/js/packages/dyn4k-dyn4k-test/package.json",
                    "Safari launcher dependency differs: dyn4k-dyn4k-core-test",
                    "Safari launcher dependency differs: dyn4k-dyn4k-test",
                ),
                (receipt["package_graph_errors"] as JsonArray).map { Py.str(it) },
            )
        }
    }

    test("the package count bound is recorded and enforced") {
        withFixture { fixture ->
            fixture.generated()
            val packages = fixture.repository.resolve("build/js/packages")
            for (index in 0 until SafariYarnLockRules.MAX_PACKAGES + 1) {
                val name = "extra-$index"
                val target = packages.resolve(name)
                Files.createDirectories(target)
                Files.writeString(target.resolve("package.json"), """{"name": "$name"}""" + "\n")
            }
            val files = mutableListOf<JsonObject>()
            val receipt = LinkedHashMap<String, JsonElement>()
            receipt["configuration"] = JsonNull
            capturePackageGraph(fixture.repository, fixture.output, files, receipt)
            assertEquals(true, Py.truthy(receipt["package_count_exceeds_bound"]))
            assertEquals(
                SafariYarnLockRules.MAX_PACKAGES + 1,
                (receipt["package_inputs_observed"] as JsonArray).size,
            )
            assertEquals(
                SafariYarnLockRules.MAX_PACKAGES + 1,
                (receipt["package_inputs_observed"] as JsonArray).size,
            )
            assertTrue((receipt["unexpected_package_inputs"] as JsonArray).isNotEmpty())
        }
    }
}

private fun streamingFlags(stdout: Long, stderr: Long): Map<String, JsonElement> = mapOf(
    "stdout_bytes_seen" to JsonPrimitive(stdout),
    "stderr_bytes_seen" to JsonPrimitive(stderr),
    "stdout_truncated" to JsonPrimitive(false),
    "stderr_truncated" to JsonPrimitive(false),
    "timed_out" to JsonPrimitive(false),
    "stream_incomplete" to JsonPrimitive(false),
)

/** `hosted_capture`: the hosted fixture the audit cases reuse. */
private fun captureHosted(fixture: SafariFixture): JsonObject = SafariCapture.capture(
    fixture.repository,
    fixture.candidate,
    fixture.output,
    configuration = "development",
    lockTask = { _, output, command ->
        fixture.generated(safari = true)
        fixture.writeLogs()
        processRecord(
            command!!,
            1,
            streamingFlags(
                Files.size(output.resolve("stdout.txt")),
                Files.size(output.resolve("stderr.txt")),
            ),
        )
    },
)

private fun captureStdout(sink: StringBuilder, block: () -> Int): Int {
    val original = System.out
    val stream = java.io.ByteArrayOutputStream()
    System.setOut(java.io.PrintStream(stream, true))
    try {
        val code = block()
        sink.append(stream.toString())
        return code
    } finally {
        System.setOut(original)
    }
}

/** The archived workflow document is part of the ported diagnostic and stays byte-identical. */
val SafariArchivedWorkflow by testSuite {
    test("the archived workflow records the historical capture route and launch context") {
        val root = repositoryRoot()
        val workflow = Files.readString(
            root.resolve("docs/archive/hosted-macos-workflows/safari-yarn-lock-diagnostic.yml"),
        )
        assertFalse(
            Files.exists(root.resolve(".github/workflows/safari-yarn-lock-diagnostic.yml")),
        )
        assertTrue(
            "    env:\n      SAFARI_BIN: \${{ github.workspace }}/tools/qualification/" +
                "safari-launch.sh\n" in workflow,
        )
        assertTrue("workflow_dispatch:" in workflow)
        assertTrue("runs-on: macos-26" in workflow)
        assertTrue("java-version: '21'" in workflow)
        assertTrue("ref: \${{ inputs.candidate_sha }}" in workflow)
        assertTrue("--configuration \"\${{ inputs.configuration }}\"" in workflow)
        assertTrue("--audit" in workflow)
        assertTrue("\${{ github.run_id }}-\${{ github.run_attempt }}" in workflow)
        assertTrue("if: always()" in workflow)
        assertTrue("tools/qualification/safari_yarn_lock.py" in workflow)
        assertFalse("kotlinUpgradeYarnLock" in workflow)
        assertFalse("yarnLockMismatchReport" in workflow)
        assertTrue(
            "DYN4K_SAFARI_LAUNCH_CONTEXT: \${{ runner.temp }}/safari-launch-context-raw" in
                workflow,
        )
        assertTrue("--capture-context" in workflow)
        assertTrue("--input-context \"\$raw\" --output \"\$context\"" in workflow)
    }
}

/** The real `gradlew` the child-free end-to-end case commits. */
private fun realLockWrapper(): String =
    """
    #!/usr/bin/env python3
    import json, sys
    from pathlib import Path
    build = Path.cwd() / 'build/js'
    build.mkdir(parents=True, exist_ok=True)
    (build / 'yarn.lock').write_bytes(b'host generated lock\n')
    names = ['dyn4k-dyn4k-core', 'dyn4k-dyn4k-core-test', 'dyn4k-dyn4k', 'dyn4k-dyn4k-test']
    (build / 'package.json').write_text(
        json.dumps({'name': 'dyn4k', 'workspaces': ['packages/' + n for n in names]}) + '\n')
    for name in names:
        path = build / 'packages' / name / 'package.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        value = {'name': name}
        if name.endswith('-test'):
            value['devDependencies'] = {'karma-safari-launcher': '1.0.0'}
        path.write_text(json.dumps(value) + '\n')
    print('> Task :dyn4k-core:jsTestPackageJson', flush=True)
    print('> Task :dyn4k:jsTestPackageJson', flush=True)
    print('> Task :kotlinNpmInstall', flush=True)
    print('> Task :kotlinStoreYarnLock FAILED', flush=True)
    sys.stderr.write(${Py.quote(LOCK_FAILURE)})
    sys.stderr.flush()
    sys.exit(1)
    """.trimIndent()
