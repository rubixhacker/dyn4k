package io.github.rubixhacker.harness.qualification

import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.LinkOption
import java.nio.file.Path
import java.nio.file.StandardOpenOption
import java.nio.file.attribute.BasicFileAttributes
import java.util.concurrent.TimeUnit
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

/**
 * `tools/qualification/safari_yarn_lock.py` host half: the diagnostic source reads, the candidate
 * gate, the archived-file copy, the Gradle lock-failure signature, and the bounded lock task.
 *
 * The reference opens every component with `dir_fd` + `O_NOFOLLOW` on POSIX and with
 * `CreateFileW`/`NtCreateFile` handles on Windows. The JVM has no descriptor, so each component is
 * checked with `NOFOLLOW_LINKS` and the file identity is re-read after the bytes are taken; a swap
 * between the check and the read is not detectable. The Windows lock task (`_run_lock_task_windows`,
 * job objects, suspended creation) is not ported: on a Windows host the task fails closed rather
 * than degrading to the POSIX drain.
 */
object SafariYarnLockHost {
    /** `source_path`: an in-checkout relative path with no symbolic component. */
    fun sourcePath(repository: Path, relative: String): Path {
        val parts = relative.split('/').filter { it.isNotEmpty() }
        if (relative.startsWith("/") || parts.isEmpty() ||
            parts.any { it == "." || it == ".." } || relative.contains('\\')
        ) {
            throw IllegalArgumentException("unsafe source path: $relative")
        }
        var path = repository
        for (part in parts) {
            path = path.resolve(part)
            if (Files.isSymbolicLink(path)) {
                throw IllegalArgumentException("symlink source path or ancestor: $relative")
            }
        }
        if (path.toRealPath() != repository.toRealPath().resolve(relative)) {
            throw IllegalArgumentException("source path escapes checkout: $relative")
        }
        return path
    }

    /** `source_bytes`: one bounded, identity-pinned diagnostic source. */
    fun sourceBytes(repository: Path, relative: String): ByteArray {
        val root = repository.toRealPath()
        val path = sourcePath(repository, relative)
        val before = Files.readAttributes(path, BasicFileAttributes::class.java, LinkOption.NOFOLLOW_LINKS)
        if (!before.isRegularFile) {
            throw IllegalArgumentException("non-regular diagnostic source: $relative")
        }
        if (before.size() > SafariYarnLockRules.MAX_FILE_BYTES) {
            throw IllegalArgumentException("oversized diagnostic source: $relative")
        }
        val data = Files.newInputStream(path, LinkOption.NOFOLLOW_LINKS).use { it.readBytes() }
        if (data.size.toLong() > SafariYarnLockRules.MAX_FILE_BYTES) {
            throw IllegalArgumentException("oversized diagnostic source: $relative")
        }
        val after = Files.readAttributes(path, BasicFileAttributes::class.java, LinkOption.NOFOLLOW_LINKS)
        if (identity(before) != identity(after) ||
            data.size.toLong() != before.size() ||
            path.toRealPath() != root.resolve(relative)
        ) {
            throw IllegalArgumentException("source path identity changed: $relative")
        }
        return data
    }

    /** `source_digest`: the SHA-256 of one diagnostic source. */
    fun sourceDigest(repository: Path, relative: String): String =
        io.github.rubixhacker.harness.contract.Sha256.of(sourceBytes(repository, relative))

    /** `require_candidate`: the checkout must be the exact candidate with a clean tree. */
    fun requireCandidate(repository: Path, candidateSha: String) {
        if (git(repository, "rev-parse", "HEAD") != candidateSha) {
            throw IllegalArgumentException("candidate SHA differs from checkout")
        }
        val committed = SafariReporterHost.committedBytes(
            repository,
            candidateSha,
            Path.of(SafariYarnLockRules.TRACKED_LOCK),
        )
        if (git(repository, "status", "--porcelain=v1", "--untracked-files=all").isNotEmpty()) {
            throw IllegalArgumentException("dirty tracked or untracked source checkout")
        }
        if (!sourceBytes(repository, SafariYarnLockRules.TRACKED_LOCK).contentEquals(committed)) {
            throw IllegalArgumentException("tracked lock differs from candidate")
        }
    }

    /** `copy_file`: archive one source input and record its identity. */
    fun copyFile(repository: Path, relative: String, output: Path, prefix: String): JsonObject {
        val source = sourcePath(repository, relative)
        val data = sourceBytes(repository, relative)
        val destination = output.resolve(prefix).resolve(relative)
        destination.parent?.let { Files.createDirectories(it) }
        Files.write(destination, data)
        val sourceReal = source.toRealPath()
        return buildJsonObject {
            put("path", JsonPrimitive(output.relativize(destination).toString().replace('\\', '/')))
            put("sha256", JsonPrimitive(io.github.rubixhacker.harness.contract.Sha256.of(data)))
            put("size", JsonPrimitive(Files.size(destination)))
            put("source_path", JsonPrimitive(source.toString()))
            put("source_realpath", JsonPrimitive(sourceReal.toString()))
        }
    }

    /**
     * `lock_failure_signature`: the captured stderr is exactly the Yarn plugin's lock-mismatch
     * failure and nothing else.
     */
    fun lockFailureSignature(stderr: String): Boolean {
        val lines = stderr.lines()
        if (lines.count { it == "FAILURE: Build failed with an exception." } != 1 ||
            lines.count { it == "* What went wrong:" } != 1
        ) {
            return false
        }
        val start = lines.indexOf("* What went wrong:") + 1
        val end = (start until lines.size).firstOrNull { lines[it].startsWith("* ") } ?: lines.size
        val block = lines.subList(start, end).filter { it.isNotEmpty() }
        val failures = lines.filter { it.startsWith("Execution failed") }
        if (block.size != 2) return false
        if (!Regex(
                "Execution failed for task ':kotlinStoreYarnLock' \\(registered by plugin class " +
                    "'org\\.jetbrains\\.kotlin\\.gradle\\.targets\\.js\\.yarn\\.YarnPlugin'\\)\\.",
            ).matches(block[0])
        ) {
            return false
        }
        return block[1] == SafariYarnLockRules.LOCK_ERROR_LINE &&
            failures == listOf(block[0]) &&
            lines.any { Regex("BUILD FAILED in \\d+(?:ms|s|m \\d+s)").matches(it) }
    }

    /**
     * `run_lock_task`: run the Gradle lock task with a bounded, truncated drain.
     *
     * `deadlineSeconds` is the seam the reference's `MAX_PROCESS_SECONDS` patch exposes; production
     * passes 600.
     */
    fun runLockTask(
        repository: Path,
        output: Path,
        command: List<String>? = null,
        deadlineSeconds: Int = SafariYarnLockRules.MAX_PROCESS_SECONDS,
        windows: Boolean = DefaultHostEnvironment.isWindows(),
    ): JsonObject {
        if (windows) {
            throw UnsupportedOperationException(
                "Safari lock task is not supported on this host: the Windows job-object runner " +
                    "(_run_lock_task_windows, CreateFileW/job objects) is not ported",
            )
        }
        val resolved = command ?: listOf(
            repository.resolve("gradlew").toString(),
            "--no-daemon",
            "--console=plain",
            "--rerun-tasks",
            ":kotlinStoreYarnLock",
        )
        duringLaunchGuard()
        val started = FullHostedRuntime.nowNs()
        val builder = ProcessBuilder(resolved).directory(repository.toFile())
        val process = builder.start()
        output.resolve("stdout.txt").parent?.let { Files.createDirectories(it) }
        val stdoutSink = Sink(output.resolve("stdout.txt"))
        val stderrSink = Sink(output.resolve("stderr.txt"))
        val stdoutThread = Thread { stdoutSink.drain(process.inputStream) }
        val stderrThread = Thread { stderrSink.drain(process.errorStream) }
        stdoutThread.start()
        stderrThread.start()
        var timedOut = false
        val deadline = System.nanoTime() + deadlineSeconds.toLong() * 1_000_000_000L
        while (process.isAlive && System.nanoTime() < deadline) {
            Thread.sleep(20)
        }
        if (process.isAlive) {
            timedOut = true
            process.destroyForcibly()
        }
        process.waitFor(SafariYarnLockRules.MAX_DRAIN_SECONDS.toLong(), TimeUnit.SECONDS)
        stdoutThread.join(SafariYarnLockRules.MAX_DRAIN_SECONDS.toLong() * 1000)
        stderrThread.join(SafariYarnLockRules.MAX_DRAIN_SECONDS.toLong() * 1000)
        val incomplete = stdoutThread.isAlive || stderrThread.isAlive
        stdoutSink.close()
        stderrSink.close()
        val finished = FullHostedRuntime.nowNs()
        return buildJsonObject {
            put("command", kotlinx.serialization.json.JsonArray(resolved.map { JsonPrimitive(it) }))
            put("pid", JsonPrimitive(process.pid()))
            put("exit_code", JsonPrimitive(if (process.isAlive) null else process.exitValue()).let {
                if (process.isAlive) kotlinx.serialization.json.JsonNull else it
            })
            put("started_ns", JsonPrimitive(started))
            put("finished_ns", JsonPrimitive(finished))
            put("deadline_seconds", JsonPrimitive(deadlineSeconds))
            put("timed_out", JsonPrimitive(timedOut))
            put("stream_incomplete", JsonPrimitive(incomplete))
            put("stdout_bytes_seen", JsonPrimitive(stdoutSink.seen))
            put("stderr_bytes_seen", JsonPrimitive(stderrSink.seen))
            put(
                "stdout_truncated",
                JsonPrimitive(stdoutSink.seen > SafariYarnLockRules.MAX_FILE_BYTES),
            )
            put(
                "stderr_truncated",
                JsonPrimitive(stderrSink.seen > SafariYarnLockRules.MAX_FILE_BYTES),
            )
        }
    }

    /** The seam a test can use to model a launch-time failure (`postlaunch setup failures`). */
    internal var launchGuard: (() -> Unit)? = null

    internal fun duringLaunchGuard() {
        launchGuard?.invoke()
    }

    /** One bounded, truncating stream sink. */
    internal class Sink(private val path: Path) {
        var seen: Long = 0
            private set
        private val out = Files.newOutputStream(
            path,
            StandardOpenOption.CREATE,
            StandardOpenOption.TRUNCATE_EXISTING,
            StandardOpenOption.WRITE,
        )

        fun drain(stream: java.io.InputStream) {
            val buffer = ByteArray(64 * 1024)
            while (true) {
                val read = try {
                    stream.read(buffer)
                } catch (error: java.io.IOException) {
                    return
                }
                if (read <= 0) return
                seen += read
                val writable = minOf(read.toLong(), SafariYarnLockRules.MAX_FILE_BYTES.toLong() - written).toInt()
                if (writable > 0) {
                    out.write(buffer, 0, writable)
                    written += writable
                }
            }
        }

        private var written: Long = 0

        fun close() {
            runCatching { out.close() }
        }
    }

    private fun identity(attributes: BasicFileAttributes): List<Any?> =
        listOf(
            attributes.fileKey(),
            attributes.size(),
            attributes.lastModifiedTime().to(TimeUnit.NANOSECONDS),
        )

    private fun git(repository: Path, vararg arguments: String): String {
        val process = ProcessBuilder(
            listOf("git", "-C", repository.toString()) + arguments,
        ).start()
        val stdout = process.inputStream.use { it.readBytes() }
        val stderr = process.errorStream.use { it.readBytes() }
        if (process.waitFor() != 0) {
            throw IllegalArgumentException(
                "git ${arguments.joinToString(" ")} failed: " +
                    String(stderr, StandardCharsets.UTF_8).trim(),
            )
        }
        return String(stdout, StandardCharsets.UTF_8).trim()
    }
}
