package io.github.rubixhacker.harness.qualification

import de.infix.testBalloon.framework.core.testSuite
import java.io.IOException
import java.nio.file.Files
import java.nio.file.Path
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/** A pipe that yields what its script returns, or raises what the script throws. */
internal class ScriptedStream(private val body: () -> ByteArray) : SafariProcessStream {
    override fun read(count: Int): ByteArray = body()

    override fun close() {}
}

internal fun emptyStream(): ScriptedStream = ScriptedStream { ByteArray(0) }

/** A stream that returns [first] once, then raises what a closed or broken pipe raises. */
internal fun failingStream(first: ByteArray): ScriptedStream {
    var calls = 0
    return ScriptedStream {
        calls += 1
        if (calls == 1) first else throw IOException("read failed after signature")
    }
}

/** A child process with fixed pipes and a recorded kill. */
internal class FakeChild(
    override val pid: Long = 345,
    override val processHandle: Long = 456,
    override val stdout: SafariProcessStream = emptyStream(),
    override val stderr: SafariProcessStream = emptyStream(),
    private val exit: Int? = 0,
    private var running: Boolean = false,
) : SafariChildProcess {
    var killed = 0
        private set

    override fun exitCode(): Int? = if (running) null else exit

    override fun waitFor(timeoutSeconds: Double): Boolean {
        running = false
        return true
    }

    override fun poll(): Int? = if (running) null else exit

    override fun kill() {
        killed += 1
        running = false
    }
}

/** `stop_fixture_process`: kill and wait, with no POSIX process group. */
internal fun stopFixtureProcess(process: SafariChildProcess) {
    if (process.poll() == null) {
        process.kill()
        process.waitFor(5.0)
    }
}

/** The kernel the reference suite's `ctypes.WinDLL` mock stands in for. */
internal class FakeKernel(
    var createJob: Long = 789,
    var assign: (Long, Long) -> Boolean = { _, _ -> true },
    var terminate: (Long, Int) -> Boolean = { _, _ -> true },
    var close: (Long) -> Boolean = { true },
    var query: (Long, Int, Int) -> SafariJobAccounting? = { _, _, _ -> SafariJobAccounting(0) },
    var setLimit: (Long, Int) -> Boolean = { _, _ -> true },
) : SafariWindowsJobKernel {
    val calls = mutableListOf<Any>()

    override fun createJobObject(): Long {
        calls.add("create")
        return createJob
    }

    override fun setInformationJobObject(job: Long, infoClass: Int, killOnClose: Boolean): Boolean {
        calls.add(Triple("limit", job, infoClass))
        return setLimit(job, infoClass)
    }

    override fun assignProcessToJobObject(job: Long, handle: Long): Boolean {
        calls.add("assign" to listOf(job, handle))
        return assign(job, handle)
    }

    override fun terminateJobObject(job: Long, exitCode: Int): Boolean {
        calls.add("terminate" to listOf(job, exitCode))
        return terminate(job, exitCode)
    }

    override fun closeHandle(handle: Long): Boolean {
        closedHandles.add(handle)
        calls.add("close" to handle)
        return close(handle)
    }

    override fun queryInformationJobObject(
        job: Long,
        infoClass: Int,
        size: Int,
    ): SafariJobAccounting? {
        calls.add("query" to listOf(job, infoClass, size))
        return query(job, infoClass, size)
    }

    override fun createToolhelp32Snapshot(flags: Int, pid: Int): Long {
        calls.add("snapshot" to listOf(flags, pid))
        return snapshot
    }

    override fun thread32First(snapshot: Long): SafariThreadEntry? {
        calls.add("first" to snapshot)
        return firstEntry
    }

    override fun thread32Next(snapshot: Long, entry: SafariThreadEntry): Boolean {
        calls.add("next" to snapshot)
        return hasNext
    }

    override fun openThread(access: Int, inherit: Boolean, threadId: Int): Long {
        calls.add(Triple("open", access, threadId))
        return threadHandle
    }

    override fun resumeThread(thread: Long): Int {
        calls.add("resume" to thread)
        return resumeResult
    }

    val closedHandles = mutableListOf<Long>()

    var snapshot: Long = 777
    var firstEntry: SafariThreadEntry? = SafariThreadEntry(901, 345)
    var hasNext = false
    var threadHandle: Long = 888
    var resumeResult = 1
}

private fun windowsTemp(block: (Path, Path) -> Unit) {
    val root = Files.createTempDirectory("safari-windows-process")
    try {
        val output = root.resolve("capture")
        Files.createDirectories(output)
        block(root, output)
    } finally {
        Files.walk(root).use { walk ->
            walk.sorted(Comparator.reverseOrder()).forEach { Files.deleteIfExists(it) }
        }
    }
}

private fun pythonSleep(seconds: Int): List<String> =
    listOf("python3", "-c", "import time; time.sleep($seconds)")

/** `tools/qualification/test_safari_windows_process.py`. */
val SafariWindowsProcessSuite by testSuite {
    test("fixture cleanup uses process kill without POSIX groups") {
        val process = FakeChild(running = true)
        stopFixtureProcess(process)
        assertEquals(1, process.killed)
    }

    test("a job limit setup exception closes the handle before launch") {
        windowsTemp { root, output ->
            val kernel = FakeKernel()
            kernel.setLimit = { _, _ ->
                throw SafariFileError("injected job limit failure")
            }
            var launched = false
            val error = assertFailsWith<SafariFileError> {
                SafariWindowsProcess.run(
                    root,
                    output,
                    listOf("gradle"),
                    windows = true,
                    kernel = kernel,
                    launch = { _, _, _ ->
                        launched = true
                        FakeChild()
                    },
                )
            }
            assertEquals("injected job limit failure", error.message)
            assertFalse(launched)
            assertEquals(listOf<Long>(789L), kernel.closedHandles)
            assertFalse(launched)
        }
    }

    test("a second reader start failure stops the job and the started reader") {
        windowsTemp { root, output ->
            val launched = mutableListOf<SafariChildProcess>()
            var starts = 0
            val kernel = FakeKernel()
            kernel.terminate = { job, code ->
                assertTrue(job == 789L && code == 1)
                launched.firstOrNull()?.let { stopFixtureProcess(it) }
                true
            }
            try {
                val error = assertFailsWith<RuntimeException> {
                    SafariWindowsProcess.run(
                        root,
                        output,
                        listOf("gradle"),
                        windows = true,
                        kernel = kernel,
                        launch = { _, repository, _ ->
                            SafariWindowsProcess.launchChild(
                                pythonSleep(30),
                                repository,
                                0,
                            ).also { launched.add(it) }
                        },
                        startReader = { thread ->
                            starts += 1
                            if (starts == 2) {
                                throw RuntimeException("injected second reader start failure")
                            }
                            thread.start()
                        },
                        resume = { _, _ -> },
                    )
                }
                assertEquals("injected second reader start failure", error.message)
                assertEquals(2, starts)
                assertTrue(
                    kernel.calls.contains("terminate" to listOf<Any>(789L, 1)),
                    kernel.calls.toString(),
                )
                assertEquals(listOf<Long>(789L), kernel.closedHandles)
                assertTrue(launched[0].poll() != null)
            } finally {
                for (process in launched) stopFixtureProcess(process)
            }
        }
    }

    test("a log open failure never launches a process or leaves a job") {
        for (failedName in listOf("stdout.txt", "stderr.txt")) {
            windowsTemp { root, output ->
                val outside = root.resolve("outside.txt")
                Files.writeString(outside, "outside sentinel")
                val kernel = FakeKernel()
                var launched = false
                val error = assertFailsWith<SafariFileError> {
                    SafariWindowsProcess.run(
                        root,
                        output,
                        listOf("gradle"),
                        windows = true,
                        kernel = kernel,
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
                assertTrue((error.message ?: "").contains(failedName))
                assertFalse(launched)
                assertFalse(kernel.calls.contains("create"))
                assertEquals("outside sentinel", Files.readString(outside))
            }
        }
    }

    test("resume requires a unique primary thread and a suspend count of one") {
        val kernel = FakeKernel()
        val process = FakeChild()
        SafariWindowsProcess.resumeSuspendedWindowsProcess(kernel, process)
        assertEquals(listOf<Long>(888L, 777L), kernel.closedHandles)

        kernel.calls.clear()
        kernel.closedHandles.clear()
        kernel.resumeResult = 0
        assertTrue(
            "cannot resume" in (
                assertFailsWith<SafariFileError> {
                    SafariWindowsProcess.resumeSuspendedWindowsProcess(kernel, process)
                }.message ?: ""
                ),
        )
        assertEquals(listOf<Long>(888L, 777L), kernel.closedHandles)

        kernel.closedHandles.clear()
        kernel.resumeResult = 1
        val other = FakeChild(pid = 346)
        assertTrue(
            "primary thread is missing" in (
                assertFailsWith<SafariFileError> {
                    SafariWindowsProcess.resumeSuspendedWindowsProcess(kernel, other)
                }.message ?: ""
                ),
        )
        assertEquals(listOf<Long>(777L), kernel.closedHandles)
    }

    test("job accounting reads the active process count or fails closed") {
        val kernel = FakeKernel()
        kernel.query = { job, kind, size ->
            assertEquals(listOf<Any>(789L, 1, 48), listOf<Any>(job, kind, size))
            SafariJobAccounting(2)
        }
        assertEquals(2, SafariWindowsProcess.windowsJobActiveCount(kernel, 789))
        kernel.query = { _, _, _ -> null }
        assertTrue(
            "cannot query" in (
                assertFailsWith<SafariFileError> {
                    SafariWindowsProcess.windowsJobActiveCount(kernel, 789)
                }.message ?: ""
                ),
        )
    }

    test("a suspended launch assigns the job before resuming") {
        windowsTemp { root, output ->
            val calls = mutableListOf<Any>()
            val flags = mutableListOf<Int>()
            val kernel = FakeKernel()
            kernel.assign = { job, handle ->
                calls.add("assign" to listOf(job, handle))
                true
            }
            kernel.query = { _, _, _ -> SafariJobAccounting(0) }
            val result = SafariWindowsProcess.run(
                root,
                output,
                listOf("gradle"),
                windows = true,
                kernel = kernel,
                launch = { _, _, creationFlags ->
                    flags.add(creationFlags)
                    FakeChild()
                },
                resume = { _, process -> calls.add("resume" to process.pid) },
            )
            assertEquals(0L, Py.int(result["exit_code"]!!))
            assertTrue((flags[0] and SafariYarnLockRules.WINDOWS_CREATE_SUSPENDED) != 0)
            assertTrue(calls.indexOf("assign" to listOf(789L, 456L)) < calls.indexOf("resume" to 345L))
        }
    }

    test("a complete pipe stream rejects an active detached job child") {
        windowsTemp { root, output ->
            val kernel = FakeKernel()
            kernel.query = { _, _, _ -> SafariJobAccounting(1) }
            val result = SafariWindowsProcess.run(
                root,
                output,
                listOf("gradle"),
                windows = true,
                kernel = kernel,
                launch = { _, _, _ -> FakeChild() },
                resume = { _, _ -> },
            )
            assertEquals(true, Py.truthy(result["stream_incomplete"]))
            assertTrue(kernel.calls.contains("terminate" to listOf<Any>(789L, 1)))
        }
    }

    test("a reader failure is incomplete even after the thread exits") {
        windowsTemp { root, output ->
            val stdout = "> Task :kotlinStoreYarnLock FAILED\n"
            val process = FakeChild(
                pid = 123,
                exit = 1,
                stdout = failingStream(stdout.toByteArray()),
                stderr = failingStream("Lock file was changed\n".toByteArray()),
            )
            val result = SafariWindowsProcess.run(
                root,
                output,
                listOf("gradle"),
                launch = { _, _, _ -> process },
                taskkill = { _, _ -> 0 },
            )
            assertEquals(true, Py.truthy(result["stream_incomplete"]))
            assertEquals(1L, Py.int(result["exit_code"]!!))
            assertEquals(
                Files.size(output.resolve("stdout.txt")),
                Py.int(result["stdout_bytes_seen"]!!),
            )
        }
    }

    test("an exited parent with an open descendant pipe triggers tree cleanup") {
        windowsTemp { root, output ->
            val release = CountDownLatch(1)
            val killed = mutableListOf<List<String>>()
            val held = ScriptedStream {
                release.await(2, TimeUnit.SECONDS)
                ByteArray(0)
            }
            val process = FakeChild(stdout = held, stderr = held)
            try {
                val result = SafariWindowsProcess.run(
                    root,
                    output,
                    listOf("gradle"),
                    launch = { _, _, _ -> process },
                    taskkill = { command, _ ->
                        killed.add(command)
                        release.countDown()
                        0
                    },
                    maxDrainSeconds = 0.05,
                )
                assertEquals(true, Py.truthy(result["stream_incomplete"]))
                assertEquals(
                    listOf(listOf("taskkill", "/T", "/F", "/PID", "345")),
                    killed,
                )
            } finally {
                release.countDown()
            }
        }
    }

    test("the Windows job terminates the descendant after the parent exits") {
        windowsTemp { root, output ->
            val release = CountDownLatch(1)
            val calls = mutableListOf<Any>()
            val held = ScriptedStream {
                release.await(2, TimeUnit.SECONDS)
                ByteArray(0)
            }
            val kernel = FakeKernel()
            kernel.assign = { job, handle ->
                calls.add("assign" to listOf(job, handle))
                true
            }
            kernel.terminate = { job, code ->
                calls.add("terminate" to listOf(job, code))
                release.countDown()
                true
            }
            kernel.close = { handle ->
                calls.add("close" to handle)
                true
            }
            kernel.query = { _, _, _ -> SafariJobAccounting(1) }
            try {
                val result = SafariWindowsProcess.run(
                    root,
                    output,
                    listOf("gradle"),
                    windows = true,
                    kernel = kernel,
                    launch = { _, _, _ -> FakeChild(stdout = held, stderr = held) },
                    resume = { _, _ -> },
                    maxDrainSeconds = 0.05,
                )
                assertEquals(true, Py.truthy(result["stream_incomplete"]))
                assertTrue(calls.contains("assign" to listOf<Any>(789L, 456L)))
                assertTrue(calls.contains("terminate" to listOf<Any>(789L, 1)))
                assertTrue(calls.contains("close" to 789L))
            } finally {
                release.countDown()
            }
        }
    }

    test("a job assignment failure stops the process and closes the pipes") {
        windowsTemp { root, output ->
            val kernel = FakeKernel()
            kernel.assign = { _, _ -> false }
            val streams = mutableListOf<ScriptedStream>()
            val process = FakeChild(
                stdout = ScriptedStream { ByteArray(0) }.also { streams.add(it) },
                stderr = ScriptedStream { ByteArray(0) }.also { streams.add(it) },
                exit = 1,
            )
            var taskkill = false
            val error = assertFailsWith<SafariFileError> {
                SafariWindowsProcess.run(
                    root,
                    output,
                    listOf("gradle"),
                    windows = true,
                    kernel = kernel,
                    launch = { _, _, _ -> process },
                    taskkill = { _, _ ->
                        taskkill = true
                        0
                    },
                )
            }
            assertTrue("cannot bind" in (error.message ?: ""))
            assertTrue("before execution" in (error.message ?: ""))
            assertEquals(listOf<Long>(789L), kernel.closedHandles)
            assertFalse(taskkill)
        }
    }

    test("the threaded capture bounds both streams") {
        windowsTemp { root, output ->
            val command = listOf(
                "python3", "-c",
                "import sys; sys.stdout.buffer.write(b'x' * 257); " +
                    "sys.stderr.buffer.write(b'y' * 257)",
            )
            val result = SafariWindowsProcess.run(
                root,
                output,
                command,
                maxFileBytes = 128,
            )
            assertEquals(0L, Py.int(result["exit_code"]!!))
            assertEquals(false, Py.truthy(result["stream_incomplete"]))
            assertEquals(257L, Py.int(result["stdout_bytes_seen"]!!))
            assertEquals(257L, Py.int(result["stderr_bytes_seen"]!!))
            assertEquals(true, Py.truthy(result["stdout_truncated"]))
            assertEquals(true, Py.truthy(result["stderr_truncated"]))
            assertEquals("x".repeat(128), Files.readString(output.resolve("stdout.txt")))
            assertEquals("y".repeat(128), Files.readString(output.resolve("stderr.txt")))
        }
    }

    test("the threaded capture enforces the deadline") {
        windowsTemp { root, output ->
            val started = System.nanoTime()
            val result = SafariWindowsProcess.run(
                root,
                output,
                pythonSleep(5),
                maxProcessSeconds = 0.2,
            )
            assertEquals(true, Py.truthy(result["timed_out"]))
            assertEquals(false, Py.truthy(result["stream_incomplete"]))
            assertTrue(System.nanoTime() - started < 3_000_000_000L)
        }
    }
}
