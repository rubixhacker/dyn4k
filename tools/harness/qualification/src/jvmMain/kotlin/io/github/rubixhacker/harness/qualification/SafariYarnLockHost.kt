package io.github.rubixhacker.harness.qualification

import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.LinkOption
import java.nio.file.Path
import java.nio.file.StandardOpenOption
import java.nio.file.attribute.BasicFileAttributes
import java.util.concurrent.TimeUnit
import io.github.rubixhacker.harness.contract.StrictJson
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonElement
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
        if (SafariReporterHost.resolvePath(path) !=
            SafariReporterHost.resolvePath(repository).resolve(relative)
        ) {
            throw IllegalArgumentException("source path escapes checkout: $relative")
        }
        return path
    }

    /**
     * `source_bytes`: one bounded, identity-pinned diagnostic source.
     *
     * [windows] selects the reference's `LockedDirectory` branch; [pathSeam] replaces the
     * `source_path` call the reference's own suite patches. Production passes neither.
     */
    fun sourceBytes(
        repository: Path,
        relative: String,
        windows: SafariLockedDirectoryFactory? = null,
        pathSeam: ((Path, String) -> Path)? = null,
    ): ByteArray {
        val root = repository.toRealPath()
        val path = (pathSeam ?: ::sourcePath)(repository, relative)
        if (windows != null) return windowsSourceBytes(windows, root, path, relative)
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

    /** The Windows branch of `source_bytes`: the same bounds over a locked handle. */
    private fun windowsSourceBytes(
        windows: SafariLockedDirectoryFactory,
        root: Path,
        path: Path,
        relative: String,
    ): ByteArray {
        val parent = Path.of(relative).parent ?: Path.of("")
        val directory = windows.create(root, parent)
        return directory.use { held ->
            val descriptor = held.openFile(Path.of(relative).fileName.toString())
            try {
                val before = descriptor.stat()
                if (before.size > SafariYarnLockRules.MAX_FILE_BYTES) {
                    throw IllegalArgumentException("oversized diagnostic source: $relative")
                }
                val chunks = java.io.ByteArrayOutputStream()
                var read = 0L
                while (read < before.size) {
                    val chunk = descriptor.read(
                        minOf(64L * 1024, before.size - read).toInt(),
                    )
                    if (chunk.isEmpty()) {
                        throw IllegalArgumentException("incomplete diagnostic source: $relative")
                    }
                    chunks.write(chunk)
                    read += chunk.size
                }
                if (descriptor.read(1).isNotEmpty()) {
                    throw IllegalArgumentException("source path identity changed: $relative")
                }
                val data = chunks.toByteArray()
                val after = descriptor.stat()
                if (before.identity() != after.identity() ||
                    SafariReporterHost.resolvePath(path) != root.resolve(relative)
                ) {
                    throw IllegalArgumentException("source path identity changed: $relative")
                }
                data
            } finally {
                descriptor.close()
            }
        }
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
    fun copyFile(
        repository: Path,
        relative: String,
        output: Path,
        prefix: String,
        windows: SafariLockedDirectoryFactory? = null,
        pathSeam: ((Path, String) -> Path)? = null,
    ): JsonObject {
        val source = (pathSeam ?: ::sourcePath)(repository, relative)
        val data = sourceBytes(repository, relative, windows, pathSeam)
        val destination = output.resolve(prefix).resolve(relative)
        destination.parent?.let { Files.createDirectories(it) }
        Files.write(destination, data)
        val sourceReal = SafariReporterHost.resolvePath(source)
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
        group: SafariPosixGroup = DefaultSafariPosixGroup,
        drain: SafariPosixDrain? = null,
        openSink: (Path) -> Sink = { Sink(it) },
        maxDrainSeconds: Double = SafariYarnLockRules.MAX_DRAIN_SECONDS.toDouble(),
    ): JsonObject {
        if (windows) {
            throw UnsupportedOperationException(
                "Safari lock task is not supported on this host: the Windows job-object runner " +
                    "(_run_lock_task_windows, CreateFileW/job objects) has no JVM equivalent; " +
                    "it runs only through SafariWindowsProcess's injected kernel",
            )
        }
        val resolved = command ?: listOf(
            repository.resolve("gradlew").toString(),
            "--no-daemon",
            "--console=plain",
            "--rerun-tasks",
            ":kotlinStoreYarnLock",
        )
        output.resolve("stdout.txt").parent?.let { Files.createDirectories(it) }
        val stdoutSink = openSink(output.resolve("stdout.txt"))
        val stderrSink = try {
            openSink(output.resolve("stderr.txt"))
        } catch (error: Throwable) {
            stdoutSink.close()
            throw error
        }
        try {
            duringLaunchGuard()
            val started = FullHostedRuntime.nowNs()
            val process = group.launch(resolved, repository)
            try {
                val result = (drain ?: DefaultSafariPosixDrain).drain(
                    process,
                    resolved,
                    stdoutSink,
                    stderrSink,
                    started,
                    deadlineSeconds,
                    maxDrainSeconds,
                )
                var alive = false
                try {
                    group.probe(process)
                    alive = true
                } catch (error: SafariNoSuchProcess) {
                    // The process group is gone; that is the clean outcome.
                }
                if (alive) result["stream_incomplete"] = JsonPrimitive(true)
                result["finished_ns"] = JsonPrimitive(FullHostedRuntime.nowNs())
                return JsonObject(result)
            } finally {
                try {
                    group.kill(process)
                } catch (error: SafariNoSuchProcess) {
                    // Already gone.
                }
                if (!process.waitFor(maxDrainSeconds)) {
                    process.destroyForcibly()
                    process.waitFor(maxDrainSeconds)
                }
                runCatching { process.stdout.close() }
                runCatching { process.stderr.close() }
            }
        } finally {
            stdoutSink.close()
            stderrSink.close()
        }
    }

    /** The seam a test can use to model a launch-time failure (`postlaunch setup failures`). */
    internal var launchGuard: (() -> Unit)? = null

    internal fun duringLaunchGuard() {
        launchGuard?.invoke()
    }

    /** One bounded, truncating stream sink. */
    class Sink(
        private val path: Path,
        private val limit: Long = SafariYarnLockRules.MAX_FILE_BYTES.toLong(),
    ) {
        var seen: Long = 0
            private set
        private var written: Long = 0
        private val out = Files.newOutputStream(
            path,
            StandardOpenOption.CREATE,
            StandardOpenOption.TRUNCATE_EXISTING,
            StandardOpenOption.WRITE,
        )

        fun append(chunk: ByteArray, count: Int) {
            seen += count
            val writable = minOf(count.toLong(), maxOf(0L, limit - written)).toInt()
            if (writable > 0) {
                out.write(chunk, 0, writable)
                written += writable
            }
        }

        fun drain(stream: java.io.InputStream) {
            val buffer = ByteArray(64 * 1024)
            while (true) {
                val read = try {
                    stream.read(buffer)
                } catch (error: java.io.IOException) {
                    return
                }
                if (read <= 0) return
                append(buffer, read)
            }
        }

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
            listOf("git", "--no-replace-objects", "-C", repository.toString()) + arguments,
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

/**
 * `sorted(Path)`: `pathlib` compares the parts of a path, not its text, so `a/b` sorts before
 * `a-b` and `x/core` before `x/core-test`.
 */
internal object PackagePathOrder : Comparator<String> {
    override fun compare(left: String, right: String): Int {
        val first = left.split('/')
        val second = right.split('/')
        for (index in 0 until minOf(first.size, second.size)) {
            val order = CanonicalText.compare(first[index], second[index])
            if (order != 0) return order
        }
        return first.size.compareTo(second.size)
    }
}

/** `digest`: the SHA-256 of a file's whole contents. */
internal fun digestFile(path: Path): String =
    io.github.rubixhacker.harness.contract.Sha256.of(Files.readAllBytes(path))

/** `pathlib` spelling of a path under [root]: `/` separators, no leading `./`. */
internal fun posixRelative(root: Path, path: Path): String =
    root.relativize(path).toString().replace('\\', '/')

/**
 * `capture_package_graph`: the generated workspace inventory, its JSON contract, and the Safari
 * launcher dependency of the two test packages.
 *
 * Every path is read back out of the archive, not out of the working tree, so the recorded graph is
 * the graph the diagnostic captured.
 */
internal fun capturePackageGraph(
    repository: Path,
    output: Path,
    files: MutableList<JsonObject>,
    receipt: MutableMap<String, JsonElement>,
) {
    val rootPackage = "build/js/package.json"
    val packagesRoot = "build/js/packages"
    val directory = SafariYarnLockHost.sourcePath(repository, packagesRoot)
    val packages = mutableListOf<Path>()
    if (Files.isDirectory(directory)) {
        Files.newDirectoryStream(directory).use { stream ->
            for (child in stream) {
                if (packages.size > SafariYarnLockRules.MAX_PACKAGES) break
                if (Files.exists(child.resolve("package.json"))) {
                    packages.add(child.resolve("package.json"))
                }
            }
        }
    }
    val tooMany = packages.size > SafariYarnLockRules.MAX_PACKAGES
    val observed = mutableListOf<String>()
    if (Files.isRegularFile(SafariYarnLockHost.sourcePath(repository, rootPackage))) {
        observed.add(rootPackage)
    }
    observed.addAll(
        packages.take(SafariYarnLockRules.MAX_PACKAGES)
            .map { posixRelative(repository, it) }
            .sortedWith(PackagePathOrder),
    )
    receipt["package_inputs_expected"] = JsonArray(
        SafariYarnLockRules.REQUIRED_PACKAGE_INPUTS.map { JsonPrimitive(it) },
    )
    receipt["package_inputs_observed"] = JsonArray(observed.map { JsonPrimitive(it) })
    receipt["missing_package_inputs"] = JsonArray(
        SafariYarnLockRules.REQUIRED_PACKAGE_INPUTS.filter { it !in observed }
            .map { JsonPrimitive(it) },
    )
    receipt["unexpected_package_inputs"] = JsonArray(
        observed.filter { it !in SafariYarnLockRules.REQUIRED_PACKAGE_INPUTS }
            .map { JsonPrimitive(it) },
    )
    receipt["package_count_exceeds_bound"] = JsonPrimitive(tooMany)
    for (relative in observed) {
        files.add(SafariYarnLockHost.copyFile(repository, relative, output, "generated"))
    }
    val errors = mutableListOf<String>()
    for (relative in observed) {
        val archived = output.resolve("generated").resolve(Path.of(relative))
        val text = try {
            String(Files.readAllBytes(archived), StandardCharsets.UTF_8)
        } catch (error: java.io.IOException) {
            errors.add("invalid JSON: $relative")
            continue
        }
        val value = try {
            StrictJson.load(text)
        } catch (error: Exception) {
            errors.add("invalid JSON: $relative")
            continue
        }
        if (value !is JsonObject) {
            errors.add("invalid package object: $relative")
        } else if (relative == rootPackage) {
            val expectedWorkspaces =
                SafariYarnLockRules.REQUIRED_PACKAGES.map { "packages/$it" }.toSet()
            val workspaces = value["workspaces"]
            val items = (workspaces as? JsonArray)?.map { Py.str(it) }
            if (Py.str(value["name"]) != "dyn4k" ||
                workspaces !is JsonArray ||
                items == null || items.any { it == null } ||
                items.mapNotNull { it }.toSet() != expectedWorkspaces ||
                items.size != expectedWorkspaces.size
            ) {
                errors.add("root package workspaces differ")
            }
        } else if (Py.str(value["name"]) != Path.of(relative).parent?.fileName?.toString()) {
            errors.add("package name differs: $relative")
        }
    }
    receipt["package_graph_errors"] = JsonArray(errors.map { JsonPrimitive(it) })
    val configuration = Py.str(receipt["configuration"])
    if (configuration == "development" || configuration == "production") {
        for (name in listOf("dyn4k-dyn4k-core-test", "dyn4k-dyn4k-test")) {
            val path = output.resolve("generated/build/js/packages").resolve(name)
                .resolve("package.json")
            val dependency = try {
                val value = StrictJson.load(
                    String(Files.readAllBytes(path), StandardCharsets.UTF_8),
                )
                Py.str(((value as? JsonObject)?.get("devDependencies") as? JsonObject)
                    ?.get("karma-safari-launcher"))
            } catch (error: Exception) {
                null
            }
            if (dependency != "1.0.0") {
                errors.add("Safari launcher dependency differs: $name")
            }
        }
        receipt["package_graph_errors"] = JsonArray(errors.map { JsonPrimitive(it) })
    }
}

/** `ProcessLookupError`: the process group is gone. */
class SafariNoSuchProcess : Exception()

/** A launched child, as `_run_lock_task_posix` drives it. */
interface SafariGroupedProcess {
    val pid: Long
    val stdout: java.io.InputStream
    val stderr: java.io.InputStream
    fun isAlive(): Boolean
    fun exitCode(): Int?
    fun destroyForcibly()
    /** `process.wait(timeout=...)`; `false` means `TimeoutExpired`. */
    fun waitFor(timeoutSeconds: Double): Boolean
}

/** `subprocess.Popen(..., start_new_session=True)`, `os.killpg(pid, 0)`, `os.killpg(pid, SIGKILL)`. */
interface SafariPosixGroup {
    fun launch(command: List<String>, repository: Path): SafariGroupedProcess

    /** `os.killpg(process.pid, 0)`; throws [SafariNoSuchProcess] when the group is empty. */
    fun probe(process: SafariGroupedProcess)

    /** `os.killpg(process.pid, signal.SIGKILL)`. */
    fun kill(process: SafariGroupedProcess)
}

/**
 * The production group: a new session, a descendant probe, and a forced kill.
 *
 * `killpg` has no Java API; the port probes and kills the process's live descendants instead of its
 * process id's group. A `start_new_session` child's group is normally exactly its descendant tree,
 * so the probe answers the same question for the processes this diagnostic starts.
 */
object DefaultSafariPosixGroup : SafariPosixGroup {
    /** `setsid` gives the child its own session, the way `start_new_session=True` does. */
    private val setsid: String? = findExecutable("setsid")

    /** `kill -s 0 -- -<pid>` asks the kernel whether the process group still has a member. */
    private val kill: String? = findExecutable("kill")

    private fun usesSetsid(): Boolean = setsid != null

    override fun launch(command: List<String>, repository: Path): SafariGroupedProcess {
        val prefix = setsid?.let { listOf(it) } ?: emptyList()
        val process = ProcessBuilder(prefix + command).directory(repository.toFile()).start()
        return JvmGroupedProcess(process)
    }

    override fun probe(process: SafariGroupedProcess) {
        if (usesSetsid() && signal("0", process.pid) == 0) return
        if (!usesSetsid() && liveDescendants(process)) return
        throw SafariNoSuchProcess()
    }

    override fun kill(process: SafariGroupedProcess) {
        if (usesSetsid()) signal("KILL", process.pid)
        val jvm = (process as? JvmGroupedProcess)?.process
        if (jvm == null) {
            process.destroyForcibly()
            return
        }
        jvm.toHandle().descendants().forEach { handle -> runCatching { handle.destroyForcibly() } }
        if (jvm.isAlive) jvm.destroyForcibly()
    }

    private fun signal(name: String, pid: Long): Int? {
        val binary = kill ?: return null
        return try {
            val signal = ProcessBuilder(binary, "-s", name, "--", "-$pid")
                .redirectOutput(ProcessBuilder.Redirect.DISCARD)
                .redirectError(ProcessBuilder.Redirect.DISCARD)
                .start()
            if (signal.waitFor(5, TimeUnit.SECONDS)) signal.exitValue() else null
        } catch (error: java.io.IOException) {
            null
        }
    }

    private fun liveDescendants(process: SafariGroupedProcess): Boolean {
        val jvm = (process as? JvmGroupedProcess)?.process ?: return process.isAlive()
        return jvm.toHandle().descendants().anyMatch { it.isAlive }
    }

    private fun findExecutable(name: String): String? {
        val candidates = listOf(
            System.getenv("PATH")?.split(java.io.File.pathSeparator) ?: emptyList(),
            listOf("/usr/bin", "/bin", "/usr/local/bin"),
        ).flatten()
        for (directory in candidates) {
            if (directory.isEmpty()) continue
            val path = Path.of(directory).resolve(name)
            if (Files.isRegularFile(path) && Files.isExecutable(path)) return path.toString()
        }
        return null
    }

    internal class JvmGroupedProcess(val process: java.lang.Process) : SafariGroupedProcess {
        override val pid: Long = process.pid()
        override val stdout: java.io.InputStream = process.inputStream
        override val stderr: java.io.InputStream = process.errorStream

        override fun isAlive(): Boolean = process.isAlive

        override fun exitCode(): Int? = if (process.isAlive) null else process.exitValue()

        override fun destroyForcibly() {
            process.destroyForcibly()
        }

        override fun waitFor(timeoutSeconds: Double): Boolean =
            process.waitFor((timeoutSeconds * 1000).toLong(), TimeUnit.MILLISECONDS)
    }
}

/** `_drain_lock_task_posix` as a seam: the selector setup the reference suite can make fail. */
fun interface SafariPosixDrain {
    fun drain(
        process: SafariGroupedProcess,
        command: List<String>,
        stdoutSink: SafariYarnLockHost.Sink,
        stderrSink: SafariYarnLockHost.Sink,
        started: Long,
        deadlineSeconds: Int,
        maxDrainSeconds: Double,
    ): LinkedHashMap<String, JsonElement>
}

/** The thread-based drain: bounded reads, a deadline, and truncation accounting. */
object DefaultSafariPosixDrain : SafariPosixDrain {
    override fun drain(
        process: SafariGroupedProcess,
        command: List<String>,
        stdoutSink: SafariYarnLockHost.Sink,
        stderrSink: SafariYarnLockHost.Sink,
        started: Long,
        deadlineSeconds: Int,
        maxDrainSeconds: Double,
    ): LinkedHashMap<String, JsonElement> {
        val stdoutThread = Thread { stdoutSink.drain(process.stdout) }
        val stderrThread = Thread { stderrSink.drain(process.stderr) }
        stdoutThread.start()
        stderrThread.start()
        var timedOut = false
        val deadline = System.nanoTime() + deadlineSeconds.toLong() * 1_000_000_000L
        while (process.isAlive() && System.nanoTime() < deadline) {
            Thread.sleep(20)
        }
        if (process.isAlive()) {
            timedOut = true
            process.destroyForcibly()
        }
        process.waitFor(maxDrainSeconds)
        stdoutThread.join((maxDrainSeconds * 1000).toLong())
        stderrThread.join((maxDrainSeconds * 1000).toLong())
        val incomplete = stdoutThread.isAlive || stderrThread.isAlive
        val result = LinkedHashMap<String, JsonElement>()
        result["command"] = JsonArray(command.map { JsonPrimitive(it) })
        result["pid"] = JsonPrimitive(process.pid)
        result["exit_code"] = process.exitCode()?.let { JsonPrimitive(it) } ?: JsonNull
        result["started_ns"] = JsonPrimitive(started)
        result["finished_ns"] = JsonPrimitive(FullHostedRuntime.nowNs())
        result["deadline_seconds"] = JsonPrimitive(deadlineSeconds)
        result["timed_out"] = JsonPrimitive(timedOut)
        result["stream_incomplete"] = JsonPrimitive(incomplete)
        result["stdout_bytes_seen"] = JsonPrimitive(stdoutSink.seen)
        result["stderr_bytes_seen"] = JsonPrimitive(stderrSink.seen)
        result["stdout_truncated"] = JsonPrimitive(
            stdoutSink.seen > SafariYarnLockRules.MAX_FILE_BYTES,
        )
        result["stderr_truncated"] = JsonPrimitive(
            stderrSink.seen > SafariYarnLockRules.MAX_FILE_BYTES,
        )
        return result
    }
}
