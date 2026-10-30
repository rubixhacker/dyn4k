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
