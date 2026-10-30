package io.github.rubixhacker.harness.qualification

import de.infix.testBalloon.framework.core.testSuite
import java.io.InputStream
import java.nio.file.Files
import java.nio.file.Path
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import kotlinx.serialization.json.JsonObject

/** A stream that records its close, so the `finally` that closes the pipes is observable. */
internal class TrackingStream(private val inner: InputStream) : InputStream() {
    var closed = false
        private set

    override fun read(): Int = inner.read()

    override fun read(buffer: ByteArray, offset: Int, length: Int): Int =
        inner.read(buffer, offset, length)

    override fun close() {
        closed = true
        inner.close()
    }
}

/** A launched process whose pipes and liveness the test can inspect after the run. */
internal class TrackingProcess(private val inner: SafariGroupedProcess) : SafariGroupedProcess {
    val out = TrackingStream(inner.stdout)
    val err = TrackingStream(inner.stderr)

    override val pid: Long = inner.pid
    override val stdout: InputStream = out
    override val stderr: InputStream = err

    override fun isAlive(): Boolean = inner.isAlive()

    override fun exitCode(): Int? = inner.exitCode()

    override fun destroyForcibly() = inner.destroyForcibly()

    override fun waitFor(timeoutSeconds: Double): Boolean = inner.waitFor(timeoutSeconds)
}

/** The default group plus the probe and kill the reference suite replaces. */
internal class RecordingGroup(
    private val launched: MutableList<TrackingProcess>,
    private val probe: ((TrackingProcess) -> Unit)? = null,
) : SafariPosixGroup {
    override fun launch(command: List<String>, repository: Path): SafariGroupedProcess =
        TrackingProcess(DefaultSafariPosixGroup.launch(command, repository)).also {
            launched.add(it)
        }

    override fun probe(process: SafariGroupedProcess) {
        val tracked = process as TrackingProcess
        probe?.invoke(tracked) ?: DefaultSafariPosixGroup.probe(tracked)
    }

    override fun kill(process: SafariGroupedProcess) {
        DefaultSafariPosixGroup.kill(process)
    }
}

private fun posixFailure(
    block: (SafariFixture) -> Unit,
) {
    withFixture(block)
}

/** `_run_lock_task_posix` through injected selector and probe seams. */
val SafariPosixProcessSuite by testSuite {
    test("a selector setup failure stops the launched process group") {
        withFixture { fixture ->
            val launched = mutableListOf<TrackingProcess>()
            val error = assertFailsWith<SafariFileError> {
                SafariYarnLockHost.runLockTask(
                    fixture.repository,
                    fixture.output,
                    listOf("python3", "-c", "import time; time.sleep(30)"),
                    group = RecordingGroup(launched),
                    drain = { _, _, _, _, _, _, _ ->
                        throw SafariFileError("injected selector setup failure")
                    },
                )
            }
            assertEquals("injected selector setup failure", error.message)
            assertEquals(1, launched.size)
            assertFalse(launched[0].isAlive())
            assertTrue(launched[0].out.closed && launched[0].err.closed)
        }
    }

    test("a selector registration failure stops the launched process group") {
        withFixture { fixture ->
            val launched = mutableListOf<TrackingProcess>()
            val error = assertFailsWith<SafariFileError> {
                SafariYarnLockHost.runLockTask(
                    fixture.repository,
                    fixture.output,
                    listOf("python3", "-c", "import time; time.sleep(30)"),
                    group = RecordingGroup(launched),
                    drain = { _, _, _, _, _, _, _ ->
                        throw SafariFileError("injected selector registration failure")
                    },
                )
            }
            assertEquals("injected selector registration failure", error.message)
            assertEquals(1, launched.size)
            assertFalse(launched[0].isAlive())
            assertTrue(launched[0].out.closed && launched[0].err.closed)
        }
    }

    test("a process-group probe error records a failed capture") {
        withFixture { fixture ->
            val launched = mutableListOf<TrackingProcess>()
            val group = RecordingGroup(launched) {
                throw SafariFileError("injected group probe failure")
            }
            val receipt = SafariCapture.capture(
                fixture.repository,
                fixture.candidate,
                fixture.output,
                configuration = "development",
                lockTask = { repository, output, command ->
                    SafariYarnLockHost.runLockTask(repository, output, command, group = group)
                },
            )
            assertEquals("PROCESS_CAPTURE_FAILED", Py.str(receipt["status"]))
            assertEquals(false, Py.truthy(receipt["qualified"]))
            assertEquals("CLEAN", Py.str((receipt["reporter_stage"] as JsonObject)["status"]))
            assertTrue((Py.str(receipt["reason"]) ?: "").contains("group probe failure"))
            assertFailsWith<IllegalArgumentException> {
                SafariCapture.auditCapture(fixture.repository, fixture.candidate, fixture.output)
            }
        }
    }

    test("a real detached child with closed pipes rejects the capture") {
        withFixture { fixture ->
            val wrapper = fixture.repository.resolve("gradlew")
            Files.writeString(wrapper, realDetachedWrapper())
            Files.setPosixFilePermissions(
                wrapper,
                java.nio.file.attribute.PosixFilePermissions.fromString("rwxr-xr-x"),
            )
            hostedGit(fixture.repository, "add", "gradlew")
            val candidate = fixture.commit("real lock wrapper fixture")
            val alias = fixture.root.resolve("var-style-source")
            Files.createSymbolicLink(alias, fixture.repository)
            assertTrue(alias != fixture.repository.toRealPath())
            try {
                val receipt = SafariCapture.capture(alias, candidate, fixture.output, "development")
                val process = receipt["process"] as JsonObject
                assertEquals(
                    SafariYarnLockRules.fullHostedCommand(
                        fixture.repository.toRealPath().toString(),
                        fixture.output.toRealPath()
                            .resolve("development/qualification.init.gradle").toString(),
                        "development",
                        Py.str(receipt["invocation_id"])!!,
                    ),
                    (process["command"] as kotlinx.serialization.json.JsonArray).map { Py.str(it) },
                )
                assertEquals(1L, Py.int(process["exit_code"]!!))
                assertEquals(true, Py.truthy(process["stream_incomplete"]))
                assertEquals("INCOMPLETE_LOG_CAPTURE", Py.str(receipt["status"]))
                assertEquals(false, Py.truthy(receipt["qualified"]))
                assertEquals("CLEAN", Py.str((receipt["reporter_stage"] as JsonObject)["status"]))
                assertFailsWith<IllegalArgumentException> {
                    SafariCapture.auditCapture(alias, candidate, fixture.output)
                }
            } finally {
                stopDetachedChild(fixture.output.resolve("stdout.txt"))
            }
        }
    }
}

/** Kill the child the fixture wrapper detached, so the suite leaves nothing running. */
private fun stopDetachedChild(stdoutPath: Path) {
    if (!Files.isRegularFile(stdoutPath)) return
    val text = Files.readString(stdoutPath)
    val match = Regex("(?m)^detached_child_pid (\\d+)$").find(text) ?: return
    ProcessHandle.of(match.groupValues[1].toLong()).ifPresent { it.destroyForcibly() }
}

/** The reference's `commit_real_lock_wrapper(detached_child=True)` script. */
private fun realDetachedWrapper(): String =
    """
    #!/usr/bin/env python3
    import json, subprocess, sys
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
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print('detached_child_pid', child.pid, flush=True)
    print('> Task :dyn4k-core:jsTestPackageJson', flush=True)
    print('> Task :dyn4k:jsTestPackageJson', flush=True)
    print('> Task :kotlinNpmInstall', flush=True)
    print('> Task :kotlinStoreYarnLock FAILED', flush=True)
    sys.stderr.write(${Py.quote(LOCK_FAILURE)})
    sys.stderr.flush()
    sys.exit(1)
    """.trimIndent()
