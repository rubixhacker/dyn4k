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

/** A locked directory whose `child` refuses the staging handle. */
private fun handleFailureDirectories(): SafariLockedDirectoryFactory =
    SafariLockedDirectoryFactory { source, relative ->
        object : SafariLockedDirectory {
            override val path: Path = source.resolve(relative)
            override fun child(name: String, removable: Boolean): SafariLockedDirectory =
                throw SafariFileError("injected Win32 stage handle failure")
            override fun openFile(name: String): SafariHandle = error("unused")
            override fun removeEmpty() = error("unused")
            override fun close() {}
        }
    }

private fun windowsStage(directories: SafariLockedDirectoryFactory): SafariCapture.StageHook =
    SafariCapture.StageHook { repository, candidate, projects, output, body ->
        SafariReporterHost.stage(
            repository,
            candidate,
            projects,
            output,
            windows = true,
            windowsDirectories = directories,
        ) { body() }
    }

/** A stream that yields each chunk once and then reaches end of file. */
private fun onceStream(chunks: List<ByteArray>): ScriptedStream {
    var index = 0
    return ScriptedStream {
        if (index < chunks.size) chunks[index++] else ByteArray(0)
    }
}

/**
 * `assert_incomplete_fixture_status`: bound the diagnostic to fixed predicates, never the fixture's
 * text, and fail unless the receipt says the log capture was incomplete.
 */
internal fun assertIncompleteFixtureStatus(receipt: JsonObject) {
    val process = receipt["process"] as? JsonObject ?: JsonObject(emptyMap())
    val expectedCommand = buildJsonObject {
        put("__expected", JsonPrimitive(true))
    }
    fun boundedInt(value: JsonElement?): Long? =
        if (Py.isInt(value)) Py.int(value) else null
    val stdoutPath = Path.of(receipt["archive_root"]?.let { Py.str(it) } ?: "")
        .resolve("stdout.txt")
    val stdout = try {
        Files.newInputStream(stdoutPath).use { it.readNBytes(SafariYarnLockRules.MAX_FILE_BYTES + 1) }
    } catch (error: java.io.IOException) {
        null
    }
    val output = stdout ?: ByteArray(0)
    val status = Py.str(receipt["status"])
    val reason = receipt["reason"]
    val started = process["started_ns"]
    val finished = process["finished_ns"]
    val detail = buildJsonObject {
        put(
            "status_category",
            JsonPrimitive(
                when (status) {
                    "INCOMPLETE_LOG_CAPTURE" -> "expected"
                    "PROCESS_BINDING_REJECTED" -> "process_binding_rejected"
                    else -> "other"
                },
            ),
        )
        put(
            "reason_category",
            JsonPrimitive(
                when {
                    reason == null || reason is JsonNull -> "absent"
                    reason is JsonPrimitive && reason.isString -> "text"
                    else -> "other"
                },
            ),
        )
        put("command_identity", JsonPrimitive(false))
        put("pid", boundedInt(process["pid"])?.let { JsonPrimitive(it) } ?: JsonNull)
        put("pid_valid", JsonPrimitive(Py.isInt(process["pid"]) && Py.int(process["pid"]) > 0))
        put("started_ns", boundedInt(started)?.let { JsonPrimitive(it) } ?: JsonNull)
        put("finished_ns", boundedInt(finished)?.let { JsonPrimitive(it) } ?: JsonNull)
        put(
            "timing_ordered",
            JsonPrimitive(
                Py.isInt(started) && Py.isInt(finished) &&
                    Py.int(started) < Py.int(finished),
            ),
        )
        put(
            "exit_code",
            boundedInt(process["exit_code"])?.let { JsonPrimitive(it) } ?: JsonNull,
        )
        put("stdout_present", JsonPrimitive(stdout != null))
        put(
            "stdout_over_limit",
            JsonPrimitive(stdout != null && stdout.size > SafariYarnLockRules.MAX_FILE_BYTES),
        )
        put(
            "task_markers",
            JsonArray(
                SafariYarnLockRules.HOSTED_TASK_MARKERS.map {
                    JsonPrimitive(String(output, Charsets.ISO_8859_1).contains(it))
                },
            ),
        )
        put("lock_success_marker", JsonPrimitive(hasLine(output, "> Task :kotlinStoreYarnLock")))
        put(
            "lock_failure_marker",
            JsonPrimitive(hasLine(output, "> Task :kotlinStoreYarnLock FAILED")),
        )
        put(
            "stream_flags",
            buildJsonObject {
                for (name in listOf(
                    "timed_out", "stream_incomplete", "stdout_truncated", "stderr_truncated",
                )) {
                    val value = process[name]
                    put(
                        name,
                        if (value is JsonPrimitive && (value.content == "true" || value.content == "false")) {
                            value
                        } else {
                            JsonNull
                        },
                    )
                }
            },
        )
    }
    val message = PyJson.renderDefault(detail)
    if (message.length > 700) throw AssertionError("process fixture diagnostic exceeded its bound")
    if (status != "INCOMPLETE_LOG_CAPTURE") throw AssertionError(message)
}

private fun hasLine(bytes: ByteArray, marker: String): Boolean =
    String(bytes, Charsets.ISO_8859_1).split('\n').any { it.removeSuffix("\r") == marker }

/** The capture-level Windows cases of `test_safari_yarn_lock.py`. */
val SafariWindowsCaptureSuite by testSuite {
    test("a staging handle failure records residue and never starts the task") {
        withFixture { fixture ->
            val crlf = "plugins {}\r\n".toByteArray()
            Files.write(fixture.repository.resolve("build.gradle.kts"), crlf)
            hostedGit(fixture.repository, "add", "build.gradle.kts")
            val candidate = fixture.commit("CRLF source fixture")
            assertEquals(
                crlf.toList(),
                SafariReporterHost.committedBytes(
                    fixture.repository,
                    candidate,
                    Path.of("build.gradle.kts"),
                ).toList(),
            )
            val lf = "plugins {}\n".toByteArray()
            val stripped = SafariLockedDirectoryFactory { _, relative ->
                object : SafariLockedDirectory {
                    override val path: Path = fixture.repository.resolve(relative)
                    override fun child(name: String, removable: Boolean): SafariLockedDirectory =
                        error("unused")
                    override fun openFile(name: String): SafariHandle = object : SafariHandle {
                        private var offset = 0
                        override fun stat(): SafariHandleStat = SafariHandleStat(
                            0, 0, crlf.size.toLong(), 0, true,
                        )
                        override fun read(count: Int): ByteArray {
                            if (offset >= lf.size) return ByteArray(0)
                            val end = minOf(lf.size, offset + count)
                            return lf.copyOfRange(offset, end).also { offset = end }
                        }
                        override fun close() {}
                    }
                    override fun removeEmpty() = error("unused")
                    override fun close() {}
                }
            }
            assertEquals(
                "incomplete diagnostic source: build.gradle.kts",
                assertFailsWith<IllegalArgumentException> {
                    SafariYarnLockHost.sourceBytes(
                        fixture.repository,
                        "build.gradle.kts",
                        windows = stripped,
                    )
                }.message,
            )
            val binary = SafariLockedDirectoryFactory { _, relative ->
                object : SafariLockedDirectory {
                    override val path: Path = fixture.repository.resolve(relative)
                    override fun child(name: String, removable: Boolean): SafariLockedDirectory =
                        error("unused")
                    override fun openFile(name: String): SafariHandle = object : SafariHandle {
                        private var offset = 0
                        override fun stat(): SafariHandleStat = SafariHandleStat(
                            0, 0, crlf.size.toLong(), 0, true,
                        )
                        override fun read(count: Int): ByteArray {
                            if (offset >= crlf.size) return ByteArray(0)
                            val end = minOf(crlf.size, offset + count)
                            return crlf.copyOfRange(offset, end).also { offset = end }
                        }
                        override fun close() {}
                    }
                    override fun removeEmpty() = error("unused")
                    override fun close() {}
                }
            }
            assertEquals(
                crlf.toList(),
                SafariYarnLockHost.sourceBytes(
                    fixture.repository,
                    "build.gradle.kts",
                    windows = binary,
                ).toList(),
            )
            Files.writeString(fixture.repository.resolve("build.gradle.kts"), "plugins {}\n")
            assertTrue(
                "dirty tracked or untracked source" in (
                    assertFailsWith<IllegalArgumentException> {
                        SafariYarnLockHost.requireCandidate(fixture.repository, candidate)
                    }.message ?: ""
                    ),
            )
            Files.writeString(
                fixture.repository.resolve("build.gradle.kts"),
                "plugins changed\r\n",
            )
            assertTrue(
                "dirty tracked or untracked source" in (
                    assertFailsWith<IllegalArgumentException> {
                        SafariYarnLockHost.requireCandidate(fixture.repository, candidate)
                    }.message ?: ""
                    ),
            )
            Files.write(fixture.repository.resolve("build.gradle.kts"), crlf)
            SafariYarnLockHost.requireCandidate(fixture.repository, candidate)

            var launched = false
            val receipt = SafariCapture.capture(
                fixture.repository,
                candidate,
                fixture.output,
                configuration = "development",
                stageHook = windowsStage(handleFailureDirectories()),
                lockTask = { _, _, _ ->
                    launched = true
                    processRecord(defaultLockCommandFor(fixture.repository), 1)
                },
            )
            assertFalse(launched)
            assertEquals("STAGED_REPORTER_CHANGED", Py.str(receipt["status"]))
            assertFalse(receipt.containsKey("process"))
            assertEquals(false, Py.truthy(receipt["qualified"]))
            val stage = receipt["reporter_stage"] as JsonObject
            assertEquals("CHANGED", Py.str(stage["status"]))
            assertEquals("LEFTOVER", Py.str((stage["projects"] as JsonObject)["dyn4k-core"]))
            assertEquals(
                "dyn4k-core/karma.config.d",
                Py.str((((stage["forensic"] as JsonArray)[0]) as JsonObject)["path"]),
            )
            assertTrue(Files.isDirectory(fixture.repository.resolve("dyn4k-core/karma.config.d")))
        }
    }

    test("a detached job child with closed pipes is an incomplete log capture") {
        withFixture { fixture ->
            val stdout = (
                "> Task :dyn4k-core:jsTestPackageJson\n" +
                    "> Task :dyn4k:jsTestPackageJson\n" +
                    "> Task :kotlinNpmInstall\n" +
                    "> Task :kotlinStoreYarnLock FAILED\n"
                ).toByteArray()
            val kernel = FakeKernel()
            kernel.query = { _, _, _ -> SafariJobAccounting(1) }
            var unbound = false
            val receipt = SafariCapture.capture(
                fixture.repository,
                fixture.candidate,
                fixture.output,
                configuration = "development",
                lockTask = { repository, output, command ->
                    fixture.generated(safari = true)
                    SafariWindowsProcess.run(
                        repository,
                        output,
                        command!!,
                        windows = true,
                        kernel = kernel,
                        launch = { _, _, flags ->
                            if ((flags and SafariYarnLockRules.WINDOWS_CREATE_SUSPENDED) == 0) {
                                unbound = true
                            }
                            FakeChild(
                                stdout = onceStream(listOf(stdout)),
                                stderr = onceStream(listOf(LOCK_FAILURE.toByteArray())),
                                exit = 1,
                            )
                        },
                        resume = { _, _ -> },
                    )
                },
            )
            assertEquals("INCOMPLETE_LOG_CAPTURE", Py.str(receipt["status"]))
            assertEquals(
                true,
                Py.truthy((receipt["process"] as JsonObject)["stream_incomplete"]),
            )
            assertFalse(unbound)
            assertFalse(Py.truthy(receipt["qualified"]))
            assertIncompleteFixtureStatus(receipt)
            assertFailsWith<IllegalArgumentException> {
                SafariCapture.auditCapture(fixture.repository, fixture.candidate, fixture.output)
            }
        }
    }

    test("an incomplete pipe is rejected even with the lock signature") {
        withFixture { fixture ->
            val stdout = (
                "> Task :dyn4k-core:jsTestPackageJson\n" +
                    "> Task :dyn4k:jsTestPackageJson\n" +
                    "> Task :kotlinNpmInstall\n" +
                    "> Task :kotlinStoreYarnLock FAILED\n"
                ).toByteArray()
            val receipt = SafariCapture.capture(
                fixture.repository,
                fixture.candidate,
                fixture.output,
                configuration = "development",
                lockTask = { repository, output, command ->
                    fixture.generated(safari = true)
                    SafariWindowsProcess.run(
                        repository,
                        output,
                        command!!,
                        windows = true,
                        kernel = FakeKernel(),
                        launch = { _, _, _ ->
                            FakeChild(
                                stdout = failingStream(stdout),
                                stderr = failingStream(LOCK_FAILURE.toByteArray()),
                                exit = 1,
                            )
                        },
                        resume = { _, _ -> },
                    )
                },
            )
            assertEquals("INCOMPLETE_LOG_CAPTURE", Py.str(receipt["status"]))
            assertEquals(
                true,
                Py.truthy((receipt["process"] as JsonObject)["stream_incomplete"]),
            )
            assertEquals(false, Py.truthy(receipt["qualified"]))
            assertIncompleteFixtureStatus(receipt)
            assertFailsWith<IllegalArgumentException> {
                SafariCapture.auditCapture(fixture.repository, fixture.candidate, fixture.output)
            }
        }
    }

    test("post-launch setup failures stop the child and record the receipt") {
        withFixture { fixture ->
            val outside = fixture.root.resolve("outside.txt")
            Files.writeString(outside, "outside sentinel")
            val receipt = SafariCapture.capture(
                fixture.repository,
                fixture.candidate,
                fixture.output,
                configuration = "development",
                lockTask = { repository, output, command ->
                    SafariYarnLockHost.runLockTask(
                        repository,
                        output,
                        command,
                        drain = { _, _, _, _, _, _, _ ->
                            throw SafariFileError("injected selector setup failure")
                        },
                    )
                },
            )
            assertEquals("PROCESS_CAPTURE_FAILED", Py.str(receipt["status"]))
            assertEquals(false, Py.truthy(receipt["qualified"]))
            assertEquals("CLEAN", Py.str((receipt["reporter_stage"] as JsonObject)["status"]))
            for (module in listOf("dyn4k-core", "dyn4k")) {
                assertFalse(Files.exists(fixture.repository.resolve("$module/karma.config.d")))
            }
            assertEquals("outside sentinel", Files.readString(outside))
            assertFailsWith<IllegalArgumentException> {
                SafariCapture.auditCapture(fixture.repository, fixture.candidate, fixture.output)
            }
        }
        withFixture { fixture ->
            val launched = mutableListOf<SafariChildProcess>()
            var starts = 0
            val receipt = SafariCapture.capture(
                fixture.repository,
                fixture.candidate,
                fixture.output,
                configuration = "development",
                lockTask = { repository, output, command ->
                    SafariWindowsProcess.run(
                        repository,
                        output,
                        command!!,
                        windows = true,
                        kernel = FakeKernel(),
                        launch = { _, _, _ ->
                            SafariWindowsProcess.launchChild(
                                listOf("python3", "-c", "import time; time.sleep(30)"),
                                repository,
                                0,
                            ).also { launched.add(it) }
                        },
                        startReader = { thread ->
                            starts += 1
                            if (starts == 2) {
                                throw RuntimeException("injected reader start failure")
                            }
                            thread.start()
                        },
                        resume = { _, _ -> },
                    )
                },
            )
            try {
                assertEquals("PROCESS_CAPTURE_FAILED", Py.str(receipt["status"]))
                assertEquals(false, Py.truthy(receipt["qualified"]))
                assertEquals("CLEAN", Py.str((receipt["reporter_stage"] as JsonObject)["status"]))
                assertEquals(2, starts)
                for (module in listOf("dyn4k-core", "dyn4k")) {
                    assertFalse(Files.exists(fixture.repository.resolve("$module/karma.config.d")))
                }
            } finally {
                for (process in launched) stopFixtureProcess(process)
            }
        }
    }

    test("a capture log open failure records a clean stage without a launch") {
        for (platform in listOf("posix", "windows")) {
            for (failedName in listOf("stdout.txt", "stderr.txt")) {
                withFixture { fixture ->
                    val outside = fixture.root.resolve("outside.txt")
                    Files.writeString(outside, "outside sentinel")
                    var launched = false
                    val receipt = SafariCapture.capture(
                        fixture.repository,
                        fixture.candidate,
                        fixture.output,
                        configuration = "development",
                        lockTask = { repository, output, command ->
                            if (platform == "posix") {
                                SafariYarnLockHost.runLockTask(
                                    repository,
                                    output,
                                    command,
                                    openSink = { path ->
                                        if (path.fileName.toString() == failedName) {
                                            throw SafariFileError("injected $failedName open failure")
                                        }
                                        SafariYarnLockHost.Sink(path)
                                    },
                                )
                            } else {
                                SafariWindowsProcess.run(
                                    repository,
                                    output,
                                    command!!,
                                    windows = true,
                                    kernel = FakeKernel(),
                                    openSink = { path ->
                                        if (path.fileName.toString() == failedName) {
                                            throw SafariFileError("injected $failedName open failure")
                                        }
                                        SafariYarnLockHost.Sink(path)
                                    },
                                    launch = { _, _, _ ->
                                        launched = true
                                        FakeChild()
                                    },
                                )
                            }
                        },
                    )
                    assertEquals("PROCESS_CAPTURE_FAILED", Py.str(receipt["status"]), platform)
                    assertFalse(launched)
                    assertTrue((Py.str(receipt["reason"]) ?: "").contains(failedName))
                    assertEquals("CLEAN", Py.str((receipt["reporter_stage"] as JsonObject)["status"]))
                    assertEquals("outside sentinel", Files.readString(outside))
                    for (module in listOf("dyn4k-core", "dyn4k")) {
                        assertFalse(
                            Files.exists(fixture.repository.resolve("$module/karma.config.d")),
                        )
                    }
                }
            }
        }
    }

    test("a blocked stage rename records the capture failure and keeps the sentinel") {
        withFixture { fixture ->
            val outside = fixture.root.resolve("outside-reporter")
            Files.createDirectories(outside)
            val sentinel = outside.resolve("qualification-safari-reporter.js")
            Files.writeString(sentinel, "outside sentinel\n")
            val receipt = SafariCapture.capture(
                fixture.repository,
                fixture.candidate,
                fixture.output,
                configuration = "development",
                lockTask = { repository, _, command ->
                    val directory = repository.resolve("dyn4k-core/karma.config.d")
                    if (Files.exists(directory)) {
                        throw SafariFileError("injected Windows sharing violation")
                    }
                    processRecord(command!!, 1)
                },
            )
            assertEquals("PROCESS_CAPTURE_FAILED", Py.str(receipt["status"]))
            assertEquals("CLEAN", Py.str((receipt["reporter_stage"] as JsonObject)["status"]))
            assertFalse(receipt.containsKey("process"))
            assertFalse(Py.truthy(receipt["qualified"]))
            assertEquals("outside sentinel\n", Files.readString(sentinel))
            assertFalse(Files.exists(fixture.repository.resolve("dyn4k-core/karma.config.d")))
            assertTrue(Files.isRegularFile(fixture.output.resolve("receipt.json")))
        }
    }

    test("the init script keeps its exact bytes and the context fixture its exact reporter") {
        withFixture { fixture ->
            SafariCapture.capture(
                fixture.repository,
                fixture.candidate,
                fixture.output,
                configuration = "production",
                lockTask = { _, _, command ->
                    fixture.generated(safari = true)
                    fixture.writeLogs()
                    processRecord(command!!, 1)
                },
            )
            val init = fixture.output.resolve("production/qualification.init.gradle")
            assertEquals(
                FullHostedRules.initScript("jsSafari", "production").encodeToByteArray().toList(),
                Files.readAllBytes(init).toList(),
            )
            assertFalse(Files.readAllBytes(init).any { it == '\r'.code.toByte() })
        }
        val context = SafariContextFixture()
        try {
            context.writeValidKarmaConfigs()
            val fragment = context.reporterText().toByteArray()
            val config = Files.readAllBytes(context.projectConfig(0))
            assertTrue(
                java.nio.ByteBuffer.wrap(config).let { haystack ->
                    var found = false
                    for (index in 0..haystack.limit() - fragment.size) {
                        if (haystack.get(index) == fragment[0]) {
                            val slice = ByteArray(fragment.size)
                            haystack.duplicate().position(index).get(slice)
                            if (slice.contentEquals(fragment)) {
                                found = true
                                break
                            }
                        }
                    }
                    found
                },
            )
        } finally {
            context.cleanup()
        }
    }
}

private fun defaultLockCommandFor(repository: Path): List<String> = listOf(
    repository.resolve("gradlew").toString(),
    "--no-daemon",
    "--console=plain",
    "--rerun-tasks",
    ":kotlinStoreYarnLock",
)
