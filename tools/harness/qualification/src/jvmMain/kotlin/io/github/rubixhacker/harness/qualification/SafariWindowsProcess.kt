package io.github.rubixhacker.harness.qualification

import java.io.IOException
import java.io.InputStream
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.Path
import java.util.concurrent.TimeUnit
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

/** `subprocess.Popen` as the Windows drain needs it: pipes, a wait with a timeout, and a kill. */
interface SafariChildProcess {
    val pid: Long

    /** `process._handle`: the process handle `AssignProcessToJobObject` receives. */
    val processHandle: Long

    val stdout: SafariProcessStream
    val stderr: SafariProcessStream

    /** `process.returncode`; `null` while the process is still running. */
    fun exitCode(): Int?

    /** `process.wait(timeout=...)`; `false` means `TimeoutExpired`. */
    fun waitFor(timeoutSeconds: Double): Boolean

    fun poll(): Int?

    fun kill()
}

/** One pipe of a child process; `read` raises what `os.read` would raise. */
interface SafariProcessStream {
    fun read(count: Int): ByteArray

    fun close()
}

/** `QueryInformationJobObject(..., 1, ...)`'s active process count. */
data class SafariJobAccounting(val activeProcesses: Int)

/** One `THREADENTRY32` row of the suspended-process snapshot. */
data class SafariThreadEntry(var threadId: Int, var ownerPid: Int)

/**
 * The `kernel32` calls `_run_lock_task_windows`, `_resume_suspended_windows_process`, and
 * `_windows_job_active_count` make.
 *
 * `ctypes.WinDLL("kernel32")` has no JVM equivalent, so the whole Windows process layer takes this
 * kernel as a seam: production supplies [SafariWindowsProcess.failClosedKernel] and fails closed
 * with an explicit message, and the reference suite supplies the fake it installs over
 * `ctypes.WinDLL`.
 */
interface SafariWindowsJobKernel {
    fun createJobObject(): Long = unsupported("CreateJobObjectW")

    fun setInformationJobObject(job: Long, infoClass: Int, killOnClose: Boolean): Boolean =
        unsupported("SetInformationJobObject")

    fun assignProcessToJobObject(job: Long, handle: Long): Boolean =
        unsupported("AssignProcessToJobObject")

    fun terminateJobObject(job: Long, exitCode: Int): Boolean = unsupported("TerminateJobObject")

    fun closeHandle(handle: Long): Boolean = unsupported("CloseHandle")

    fun queryInformationJobObject(job: Long, infoClass: Int, size: Int): SafariJobAccounting? =
        unsupported("QueryInformationJobObject")

    fun createToolhelp32Snapshot(flags: Int, pid: Int): Long =
        unsupported("CreateToolhelp32Snapshot")

    fun thread32First(snapshot: Long): SafariThreadEntry? = unsupported("Thread32First")

    fun thread32Next(snapshot: Long, entry: SafariThreadEntry): Boolean =
        unsupported("Thread32Next")

    fun openThread(access: Int, inherit: Boolean, threadId: Int): Long = unsupported("OpenThread")

    fun resumeThread(thread: Long): Int = unsupported("ResumeThread")

    private fun unsupported(name: String): Nothing = throw UnsupportedOperationException(
        "Safari Windows process control is not supported on this host: $name has no JVM " +
            "equivalent, so it must be driven through an injected kernel",
    )
}

/**
 * `_run_lock_task_windows`: start the lock task suspended, bind it to a kill-on-close job, resume
 * it, and drain both pipes on reader threads with the deadline and the truncation bounds.
 *
 * The reference reaches every branch on a Windows runner; this port reaches the same branches
 * through [kernel], [launch], [taskkill], [startReader], [resume], and [activeCount], which is how
 * the reference's own suite drives them on POSIX.
 */
object SafariWindowsProcess {
    const val CREATE_NEW_PROCESS_GROUP = 0x00000200

    /** The production kernel: `kernel32` cannot be called from this JVM, so it fails closed. */
    val failClosedKernel: SafariWindowsJobKernel = object : SafariWindowsJobKernel {}

    internal fun run(
        repository: Path,
        output: Path,
        command: List<String>,
        windows: Boolean = false,
        kernel: SafariWindowsJobKernel? = null,
        launch: (List<String>, Path, Int) -> SafariChildProcess = ::launchChild,
        taskkill: (List<String>, Double) -> Int? = ::taskkill,
        openSink: (Path) -> SafariYarnLockHost.Sink = { SafariYarnLockHost.Sink(it) },
        startReader: (Thread) -> Unit = { it.start() },
        resume: (SafariWindowsJobKernel, SafariChildProcess) -> Unit =
            ::resumeSuspendedWindowsProcess,
        activeCount: (SafariWindowsJobKernel, Long) -> Int = ::windowsJobActiveCount,
        maxProcessSeconds: Double = SafariYarnLockRules.MAX_PROCESS_SECONDS.toDouble(),
        maxDrainSeconds: Double = SafariYarnLockRules.MAX_DRAIN_SECONDS.toDouble(),
        maxFileBytes: Long = SafariYarnLockRules.MAX_FILE_BYTES.toLong(),
        createNewProcessGroup: Int = 0,
    ): JsonObject {
        val stdoutSink = openSink(output.resolve("stdout.txt"))
        val stderrSink = try {
            openSink(output.resolve("stderr.txt"))
        } catch (error: Throwable) {
            stdoutSink.close()
            throw error
        }
        try {
            return runOpened(
                repository,
                command,
                stdoutSink,
                stderrSink,
                windows,
                kernel,
                launch,
                taskkill,
                startReader,
                resume,
                activeCount,
                maxProcessSeconds,
                maxDrainSeconds,
                maxFileBytes,
                createNewProcessGroup,
            )
        } finally {
            stdoutSink.close()
            stderrSink.close()
        }
    }

    @Suppress("LongParameterList")
    private fun runOpened(
        repository: Path,
        command: List<String>,
        stdoutSink: SafariYarnLockHost.Sink,
        stderrSink: SafariYarnLockHost.Sink,
        windows: Boolean,
        kernel: SafariWindowsJobKernel?,
        launch: (List<String>, Path, Int) -> SafariChildProcess,
        taskkill: (List<String>, Double) -> Int?,
        startReader: (Thread) -> Unit,
        resume: (SafariWindowsJobKernel, SafariChildProcess) -> Unit,
        activeCount: (SafariWindowsJobKernel, Long) -> Int,
        maxProcessSeconds: Double,
        maxDrainSeconds: Double,
        maxFileBytes: Long,
        createNewProcessGroup: Int,
    ): JsonObject {
        val started = FullHostedRuntime.nowNs()
        val startedTick = System.nanoTime()
        var job: Long? = null
        var boundKernel: SafariWindowsJobKernel? = null
        if (windows) {
            val active = kernel ?: failClosedKernel
            boundKernel = active
            val created = active.createJobObject()
            if (created == 0L) {
                throw SafariFileError("cannot create Safari diagnostic Windows job")
            }
            job = created
            try {
                if (!active.setInformationJobObject(created, 9, true)) {
                    throw SafariFileError("cannot set Safari diagnostic kill-on-close job limit")
                }
            } catch (error: Throwable) {
                active.closeHandle(created)
                throw error
            }
        }
        val flags = createNewProcessGroup or
            (if (job != null) SafariYarnLockRules.WINDOWS_CREATE_SUSPENDED else 0)
        val process = try {
            launch(command, repository, flags)
        } catch (error: Throwable) {
            boundKernel?.let { it.closeHandle(job!!) }
            throw error
        }
        val threads = mutableListOf<Thread>()
        var failed = true
        try {
            if (boundKernel != null && job != null) {
                try {
                    if (!boundKernel.assignProcessToJobObject(job, process.processHandle)) {
                        throw SafariFileError(
                            "cannot assign suspended Safari diagnostic process to Windows job",
                        )
                    }
                    resume(boundKernel, process)
                } catch (error: Exception) {
                    throw SafariFileError(
                        "cannot bind Safari diagnostic process before execution: " +
                            (error.message ?: error.toString()),
                    )
                }
            }
            val drained = drain(
                process,
                command,
                stdoutSink,
                stderrSink,
                started,
                boundKernel,
                job,
                threads,
                taskkill,
                startReader,
                activeCount,
                maxProcessSeconds,
                maxDrainSeconds,
                maxFileBytes,
            )
            failed = false
            val finished = FullHostedRuntime.nowNs()
            val finishedTick = System.nanoTime()
            val completed = LinkedHashMap<String, kotlinx.serialization.json.JsonElement>(drained)
            completed["finished_ns"] = JsonPrimitive(maxOf(finished, started + finishedTick - startedTick))
            return JsonObject(completed)
        } finally {
            try {
                if (failed) {
                    terminateWindowsTree(boundKernel, job, process, taskkill, maxDrainSeconds)
                    if (!process.waitFor(maxDrainSeconds)) {
                        process.kill()
                        process.waitFor(maxDrainSeconds)
                    }
                }
                for (thread in threads) {
                    thread.join((maxDrainSeconds * 1000).toLong())
                }
                if (threads.none { it.isAlive }) {
                    process.stdout.close()
                    process.stderr.close()
                }
            } finally {
                boundKernel?.let { it.closeHandle(job!!) }
            }
        }
    }

    /** `_drain_lock_task_windows`: two reader threads, a deadline, and the job's live count. */
    @Suppress("LongParameterList")
    private fun drain(
        process: SafariChildProcess,
        command: List<String>,
        stdoutSink: SafariYarnLockHost.Sink,
        stderrSink: SafariYarnLockHost.Sink,
        started: Long,
        kernel: SafariWindowsJobKernel?,
        job: Long?,
        threads: MutableList<Thread>,
        taskkill: (List<String>, Double) -> Int?,
        startReader: (Thread) -> Unit,
        activeCount: (SafariWindowsJobKernel, Long) -> Int,
        maxProcessSeconds: Double,
        maxDrainSeconds: Double,
        maxFileBytes: Long,
    ): JsonObject {
        val seen = linkedMapOf("stdout" to 0L, "stderr" to 0L)
        val kept = linkedMapOf("stdout" to 0L, "stderr" to 0L)
        val readerErrors = mutableListOf<String>()

        fun drainStream(
            name: String,
            source: SafariProcessStream,
            destination: SafariYarnLockHost.Sink,
        ) {
            try {
                while (true) {
                    val chunk = source.read(64 * 1024)
                    if (chunk.isEmpty()) break
                    seen[name] = seen.getValue(name) + chunk.size
                    val writable = minOf(
                        chunk.size.toLong(),
                        maxOf(0L, maxFileBytes - kept.getValue(name)),
                    ).toInt()
                    if (writable > 0) {
                        destination.append(chunk, writable)
                        kept[name] = kept.getValue(name) + writable
                    }
                }
            } catch (error: Exception) {
                readerErrors.add("$name: ${error.javaClass.simpleName}: ${error.message}")
            }
        }

        threads.add(Thread { drainStream("stdout", process.stdout, stdoutSink) })
        threads.add(Thread { drainStream("stderr", process.stderr, stderrSink) })
        for (thread in threads) startReader(thread)
        var timedOut = false
        if (!process.waitFor(maxProcessSeconds)) {
            timedOut = true
            terminateWindowsTree(kernel, job, process, taskkill, maxDrainSeconds)
            if (!process.waitFor(maxDrainSeconds)) {
                process.kill()
                process.waitFor(maxDrainSeconds)
            }
        }
        for (thread in threads) {
            thread.join((maxDrainSeconds * 1000).toLong())
        }
        var streamIncomplete = readerErrors.isNotEmpty() || threads.any { it.isAlive }
        if (kernel != null && job != null) {
            val active = try {
                activeCount(kernel, job)
            } catch (error: IOException) {
                1
            }
            if (active != 0) streamIncomplete = true
        }
        if (streamIncomplete && !timedOut) {
            terminateWindowsTree(kernel, job, process, taskkill, maxDrainSeconds)
            for (thread in threads) {
                thread.join((maxDrainSeconds * 1000).toLong())
            }
        }
        return buildJsonObject {
            put("command", JsonArray(command.map { JsonPrimitive(it) }))
            put("pid", JsonPrimitive(process.pid))
            put(
                "exit_code",
                process.exitCode()?.let { JsonPrimitive(it) }
                    ?: kotlinx.serialization.json.JsonNull,
            )
            put("started_ns", JsonPrimitive(started))
            put("deadline_seconds", secondsJson(maxProcessSeconds))
            put("timed_out", JsonPrimitive(timedOut))
            put("stream_incomplete", JsonPrimitive(streamIncomplete))
            put("stdout_bytes_seen", JsonPrimitive(seen.getValue("stdout")))
            put("stderr_bytes_seen", JsonPrimitive(seen.getValue("stderr")))
            put(
                "stdout_truncated",
                JsonPrimitive(seen.getValue("stdout") > kept.getValue("stdout")),
            )
            put(
                "stderr_truncated",
                JsonPrimitive(seen.getValue("stderr") > kept.getValue("stderr")),
            )
        }
    }

    /** `MAX_PROCESS_SECONDS` as JSON: `600` for the default, `0.2` when a test shrinks it. */
    private fun secondsJson(value: Double): JsonPrimitive =
        if (value % 1.0 == 0.0) JsonPrimitive(value.toLong()) else JsonPrimitive(value)

    /** `_terminate_windows_tree`: the job first, then `taskkill /T /F`, then a hard kill. */
    private fun terminateWindowsTree(
        kernel: SafariWindowsJobKernel?,
        job: Long?,
        process: SafariChildProcess,
        taskkill: (List<String>, Double) -> Int?,
        maxDrainSeconds: Double,
    ) {
        if (kernel != null && job != null && kernel.terminateJobObject(job, 1)) return
        val killed = taskkill(
            listOf("taskkill", "/T", "/F", "/PID", process.pid.toString()),
            maxDrainSeconds,
        )
        if (killed != null && killed != 0 && process.poll() == null) {
            process.kill()
        } else if (killed == null && process.poll() == null) {
            process.kill()
        }
    }

    /** `_resume_suspended_windows_process`: exactly one primary thread, one resume. */
    fun resumeSuspendedWindowsProcess(
        kernel: SafariWindowsJobKernel,
        process: SafariChildProcess,
    ) {
        val snapshot = kernel.createToolhelp32Snapshot(0x00000004, 0)
        if (snapshot == 0L || snapshot == -1L) {
            throw SafariFileError("cannot snapshot suspended Safari diagnostic thread")
        }
        try {
            val entry = kernel.thread32First(snapshot)
                ?: throw SafariFileError("cannot enumerate suspended Safari diagnostic thread")
            val threads = mutableListOf<Int>()
            val deadline = System.nanoTime() +
                (SafariYarnLockRules.MAX_DRAIN_SECONDS * 1_000_000_000L)
            while (true) {
                if (entry.ownerPid.toLong() == process.pid) {
                    threads.add(entry.threadId)
                    if (threads.size != 1) {
                        throw SafariFileError("suspended Safari diagnostic has multiple threads")
                    }
                }
                if (System.nanoTime() >= deadline) {
                    throw SafariFileError(
                        "suspended Safari diagnostic thread scan exceeded deadline",
                    )
                }
                if (!kernel.thread32Next(snapshot, entry)) break
            }
            if (threads.size != 1) {
                throw SafariFileError("suspended Safari diagnostic primary thread is missing")
            }
            val thread = kernel.openThread(0x0002, false, threads[0])
            if (thread == 0L) {
                throw SafariFileError("cannot open suspended Safari diagnostic primary thread")
            }
            try {
                if (kernel.resumeThread(thread) != 1) {
                    throw SafariFileError(
                        "cannot resume suspended Safari diagnostic primary thread",
                    )
                }
            } finally {
                kernel.closeHandle(thread)
            }
        } finally {
            kernel.closeHandle(snapshot)
        }
    }

    /** `_windows_job_active_count`: the live process count, or a failed-closed read. */
    fun windowsJobActiveCount(kernel: SafariWindowsJobKernel, job: Long): Int {
        val accounting = kernel.queryInformationJobObject(job, 1, 48)
            ?: throw SafariFileError("cannot query Safari diagnostic Windows job lifetime")
        return accounting.activeProcesses
    }

    /** The default launcher: a real child process, as `subprocess.Popen` starts one. */
    fun launchChild(command: List<String>, repository: Path, flags: Int): SafariChildProcess {
        val builder = ProcessBuilder(command).directory(repository.toFile())
        val process = builder.start()
        return JvmChildProcess(process)
    }

    /** The default `taskkill /T /F /PID`: exit code, or `null` when it could not run. */
    fun taskkill(command: List<String>, timeoutSeconds: Double): Int? = try {
        val process = ProcessBuilder(command)
            .redirectOutput(ProcessBuilder.Redirect.DISCARD)
            .redirectError(ProcessBuilder.Redirect.DISCARD)
            .start()
        if (process.waitFor((timeoutSeconds * 1000).toLong(), TimeUnit.MILLISECONDS)) {
            process.exitValue()
        } else {
            process.destroyForcibly()
            null
        }
    } catch (error: IOException) {
        null
    }

    /** The `gradlew.bat` command of a Windows lock task. */
    fun windowsCommand(repository: Path): List<String> = listOf(
        repository.resolve("gradlew.bat").toString(),
        "--no-daemon",
        "--console=plain",
        "--rerun-tasks",
        ":kotlinStoreYarnLock",
    )

    /** A child process backed by `java.lang.Process`. */
    private class JvmChildProcess(private val process: java.lang.Process) : SafariChildProcess {
        override val pid: Long = process.pid()
        override val processHandle: Long = process.pid()
        override val stdout: SafariProcessStream = JvmStream(process.inputStream)
        override val stderr: SafariProcessStream = JvmStream(process.errorStream)

        override fun exitCode(): Int? = if (process.isAlive) null else process.exitValue()

        override fun waitFor(timeoutSeconds: Double): Boolean =
            process.waitFor((timeoutSeconds * 1000).toLong(), TimeUnit.MILLISECONDS)

        override fun poll(): Int? = if (process.isAlive) null else process.exitValue()

        override fun kill() {
            process.destroyForcibly()
        }
    }

    private class JvmStream(private val stream: InputStream) : SafariProcessStream {
        override fun read(count: Int): ByteArray {
            val buffer = ByteArray(count)
            val read = stream.read(buffer)
            return if (read <= 0) ByteArray(0) else buffer.copyOf(read)
        }

        override fun close() {
            runCatching { stream.close() }
        }
    }
}

/** `taskkill` output decoding stays explicit so the fixture messages are readable. */
internal fun decodeTaskkill(bytes: ByteArray): String = String(bytes, StandardCharsets.UTF_8)

/** The `Files.createDirectories` helper the Windows log sinks rely on. */
internal fun ensureOutputDirectory(output: Path) {
    output.parent?.let { Files.createDirectories(it) }
}
