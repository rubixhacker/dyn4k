package io.github.rubixhacker.harness.qualification

import de.infix.testBalloon.framework.core.testSuite
import io.github.rubixhacker.harness.contract.Sha256
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.Path
import java.util.concurrent.TimeUnit
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

/** `commit_crlf_source_fixture`: commit the CRLF source only when it is not already committed. */
internal fun commitCrlfSourceFixture(repository: Path): String {
    Files.write(repository.resolve("build.gradle.kts"), "plugins {}\r\n".toByteArray())
    hostedGit(repository, "add", "build.gradle.kts")
    val staged = ProcessBuilder(
        listOf("git", "-C", repository.toString(), "diff", "--cached", "--quiet", "--",
            "build.gradle.kts"),
    ).start()
    val code = staged.waitFor(5, TimeUnit.SECONDS)
    check(code) { "git diff --cached did not finish" }
    when (staged.exitValue()) {
        1 -> hostedGit(
            repository, "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
            "commit", "-qm", "CRLF source fixture",
        )
        0 -> Unit
        else -> error("git diff --cached failed: ${staged.exitValue()}")
    }
    return hostedGit(repository, "rev-parse", "HEAD")
}

/** The reference-suite self-checks and capture/audit leftovers. */
val SafariLeftoversSuite by testSuite {
    test("the CRLF source fixture commit is idempotent") {
        withFixture { fixture ->
            val first = commitCrlfSourceFixture(fixture.repository)
            val second = commitCrlfSourceFixture(fixture.repository)
            assertEquals(first, second)
            assertEquals(
                "plugins {}\r\n",
                String(Files.readAllBytes(fixture.repository.resolve("build.gradle.kts"))),
            )
            assertEquals(
                "plugins {}\r\n",
                String(
                    SafariReporterHost.committedBytes(
                        fixture.repository,
                        second,
                        Path.of("build.gradle.kts"),
                    ),
                ),
            )
            val old = ProcessBuilder(
                listOf(
                    "git", "-C", fixture.repository.toString(), "-c", "user.name=Test",
                    "-c", "user.email=test@example.invalid", "commit", "-qm",
                    "CRLF source fixture",
                ),
            ).redirectErrorStream(true).start()
            assertEquals(1, old.waitFor())
        }
    }

    test("an unprotected fixture normalizes CRLF with autocrlf true") {
        withFixture { fixture ->
            hostedGit(fixture.repository, "config", "--local", "core.autocrlf", "true")
            val source = fixture.repository.resolve("tools/qualification/safari-karma-reporter.js")
            val windows = Files.readString(source).replace("\r\n", "\n")
                .replace("\n", "\r\n").toByteArray()
            Files.write(source, windows)
            hostedGit(
                fixture.repository, "add", "tools/qualification/safari-karma-reporter.js",
            )
            val committed = SafariReporterHost.committedBytes(
                fixture.repository,
                fixture.candidate,
                Path.of("tools/qualification/safari-karma-reporter.js"),
            )
            assertFalse(committed.contentEquals(windows))
            assertEquals(
                String(windows).replace("\r\n", "\n"),
                String(committed),
            )
        }
    }

    test("the Safari reporter splits service messages without dropping them") {
        val root = repositoryRoot()
        val result = ProcessBuilder(
            "node",
            root.resolve("tools/qualification/safari-reporter-control.js").toString(),
            root.resolve("tools/qualification/safari-karma-reporter.js").toString(),
        ).start()
        val stderr = result.errorStream.readBytes()
        assertTrue(
            result.waitFor(5, TimeUnit.SECONDS),
            "the reporter control did not finish",
        )
        assertEquals(0, result.exitValue(), String(stderr, StandardCharsets.UTF_8))
    }

    test("the lock task keeps the Gradle mismatch enforcement") {
        withFixture { fixture ->
            val wrapper = fixture.repository.resolve("gradlew")
            Files.writeString(
                wrapper,
                "#!/bin/sh\n" +
                    "printf ':kotlinStoreYarnLock FAILED\\n'\n" +
                    "printf 'Lock file was changed\\n' >&2\n" +
                    "exit 1\n",
            )
            Files.setPosixFilePermissions(
                wrapper,
                java.nio.file.attribute.PosixFilePermissions.fromString("rwxr-xr-x"),
            )
            val launched = mutableListOf<TrackingProcess>()
            val result = SafariYarnLockHost.runLockTask(
                fixture.repository,
                fixture.output,
                group = RecordingGroup(launched),
            )
            val command = (result["command"] as JsonArray).map { Py.str(it) }
            assertEquals(
                listOf(
                    wrapper.toString(),
                    "--no-daemon",
                    "--console=plain",
                    "--rerun-tasks",
                    ":kotlinStoreYarnLock",
                ),
                command,
            )
            assertFalse(command.any { it == "kotlinUpgradeYarnLock" })
            assertEquals(1L, Py.int(result["exit_code"]!!))
            assertEquals(
                listOf("Lock file was changed"),
                Files.readAllLines(fixture.output.resolve("stderr.txt")),
            )
        }
    }

    test("the init script digests and fragments are the reference ones") {
        for ((configuration, expected) in SafariYarnLockVectors.INIT_SCRIPT_SHA256) {
            val script = FullHostedRules.initScript("jsSafari", configuration)
            assertEquals(
                expected,
                Sha256.of(script.toByteArray(StandardCharsets.UTF_8)),
                configuration,
            )
            if (configuration == "development") {
                assertTrue("if (false) {" in script)
            } else {
                assertTrue("if (true) {" in script)
                assertTrue("def testFileName = project.name + '-test.js'" in script)
                assertTrue("if (project != project.rootProject) {" in script)
                assertTrue(
                    "testFileName = project.rootProject.name + '-' + testFileName" in script,
                )
                assertTrue(
                    "'compileSync/js/test/testProductionExecutable/kotlin/' + testFileName))" in
                        script,
                )
            }
        }
    }

    test("a quoted overflow phrase does not mask another Gradle failure") {
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
                            "> Task :dyn4k-core:jsBrowserTest FAILED\n",
                    )
                    Files.writeString(
                        output.resolve("stderr.txt"),
                        "Another failure quoted: Cannot process output: too long teamcity " +
                            "service message (more than 1Mb). Event was lost.\n",
                    )
                    processRecord(command!!, 1)
                },
            )
            assertEquals("OTHER_GRADLE_RESULT", Py.str(receipt["status"]))
        }
    }

    test("a staging directory swap is rejected without following it") {
        withFixture { fixture ->
            val outside = fixture.output.parent?.resolve("outside-reporter")
                ?: fixture.root.resolve("outside-reporter")
            Files.createDirectories(outside)
            Files.writeString(
                outside.resolve(SafariReporter.STAGED_NAME),
                "outside bytes\n",
            )
            val receipt = SafariCapture.capture(
                fixture.repository,
                fixture.candidate,
                fixture.output,
                configuration = "development",
                lockTask = { repository, destination, command ->
                    fixture.generated("tracked lock\n", safari = true)
                    Files.writeString(destination.resolve("stdout.txt"), "> Task :kotlinStoreYarnLock\n")
                    Files.writeString(destination.resolve("stderr.txt"), "")
                    val directory = repository.resolve("dyn4k-core/karma.config.d")
                    Files.delete(directory.resolve(SafariReporter.STAGED_NAME))
                    Files.delete(directory)
                    Files.createSymbolicLink(directory, outside)
                    processRecord(command!!, 0, streamingFlags(33, 0))
                },
            )
            assertEquals("STAGED_REPORTER_CHANGED", Py.str(receipt["status"]))
            assertEquals(
                "DIRECTORY_CHANGED",
                Py.str(((receipt["reporter_stage"] as JsonObject)["projects"] as JsonObject)["dyn4k-core"]),
            )
            assertEquals("outside bytes\n", Files.readString(outside.resolve(SafariReporter.STAGED_NAME)))
            assertTrue(Files.isSymbolicLink(fixture.repository.resolve("dyn4k-core/karma.config.d")))
        }
    }

    test("a project ancestor swap is rejected without outside access") {
        withFixture { fixture ->
            val project = fixture.repository.resolve("dyn4k-core")
            val moved = fixture.repository.resolve("moved-core")
            val outside = fixture.root.resolve("outside-core")
            val sentinel = outside.resolve("karma.config.d").resolve(SafariReporter.STAGED_NAME)
            Files.createDirectories(sentinel.parent)
            Files.writeString(sentinel, "OUTSIDE SENTINEL\n")
            val receipt = SafariCapture.capture(
                fixture.repository,
                fixture.candidate,
                fixture.output,
                configuration = "development",
                lockTask = { _, destination, command ->
                    fixture.generated("tracked lock\n", safari = true)
                    Files.writeString(destination.resolve("stdout.txt"), "> Task :kotlinStoreYarnLock\n")
                    Files.writeString(destination.resolve("stderr.txt"), "")
                    Files.move(project, moved)
                    Files.createSymbolicLink(project, outside)
                    processRecord(command!!, 0, streamingFlags(33, 0))
                },
            )
            assertEquals("CHANGED", Py.str((receipt["reporter_stage"] as JsonObject)["status"]))
            assertEquals("OUTSIDE SENTINEL\n", Files.readString(sentinel))
            assertFalse(
                Files.exists(
                    fixture.output.resolve(
                        "forensic/safari-reporter/dyn4k-core/${SafariReporter.STAGED_NAME}",
                    ),
                ),
            )
        }
    }

    test("a capture rejects a generated config symlinked package ancestor") {
        val context = SafariContextFixture()
        try {
            context.writeValidKarmaConfigs()
            val packageDirectory = context.repository.resolve("build/js/packages/dyn4k-dyn4k-core-test")
            val outside = context.root.resolve("outside-generated-package")
            Files.move(packageDirectory, outside)
            Files.createSymbolicLink(packageDirectory, outside)
            val error = assertFailsWith<IllegalArgumentException> {
                FullHosted.captureSafariConfig(
                    context.repository,
                    context.candidate,
                    "dyn4k-core",
                    "development",
                    buildJsonObject {
                        put("started_ns", JsonPrimitive(0))
                        put("finished_ns", JsonPrimitive(System.currentTimeMillis() * 1_000_000 + 1_000_000_000L))
                    },
                    context.root.resolve("capture"),
                    "development/karma-config/dyn4k-core/karma.conf.js",
                )
            }
            val message = error.message ?: ""
            assertTrue(
                "unsafe" in message || "symlink" in message || "identity" in message,
                message,
            )
            assertEquals(
                Files.readAllBytes(outside.resolve("karma.conf.js")).toList(),
                Files.readAllBytes(packageDirectory.resolve("karma.conf.js")).toList(),
            )
        } finally {
            context.cleanup()
        }
    }
}
