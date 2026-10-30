package io.github.rubixhacker.harness.migration

import io.github.rubixhacker.harness.contract.CanonicalJson
import io.github.rubixhacker.harness.host.FileDigest
import java.io.File
import java.io.IOException
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.LinkOption
import java.nio.file.Path
import java.util.concurrent.TimeUnit
import kotlin.concurrent.thread

/** One finished process, with its streams decoded as UTF-8 the way `text=True` reads them. */
data class ProcessResult(
    val command: List<String>,
    val exitCode: Int,
    val stdout: String,
    val stderr: String,
)

/** `subprocess.CalledProcessError`, with Python's message text. */
class ProcessFailure(val command: List<String>, val exitCode: Int) :
    RuntimeException("Command '${pythonListRepr(command)}' returned non-zero exit status $exitCode.")

/** `subprocess.TimeoutExpired`, carrying the partial output Python collects after the kill. */
class ProcessTimeout(
    val command: List<String>,
    val timeoutSeconds: Double,
    val stdout: String,
    val stderr: String,
) : RuntimeException(
    "Command '${pythonListRepr(command)}' timed out after ${CanonicalJson.pythonFloat(timeoutSeconds)} seconds",
)

/** Python's `repr` of a list of strings, as `subprocess` renders commands in error text. */
fun pythonListRepr(values: List<String>): String = values.joinToString(", ", "[", "]") { pythonRepr(pyText(it)) }

/** Runs external commands with `subprocess.run` semantics. */
object Processes {
    /**
     * Runs [command] and collects its streams.
     *
     * With [timeoutSeconds] set, a process that exceeds the deadline is killed and its partial
     * output is reported in a [ProcessTimeout], as `subprocess.run` does. With [check] the call
     * fails with [ProcessFailure] on a non-zero exit status.
     */
    fun run(
        command: List<String>,
        timeoutSeconds: Double? = null,
        check: Boolean = false,
        environment: Map<String, String>? = null,
    ): ProcessResult {
        val builder = ProcessBuilder(command).redirectErrorStream(false)
        if (environment != null) builder.environment().putAll(environment)
        val process = builder.start()
        val stdout = StringBuilder()
        val stderr = StringBuilder()
        val outReader = thread(isDaemon = true) {
            stdout.append(process.inputStream.readBytes().toString(StandardCharsets.UTF_8))
        }
        val errReader = thread(isDaemon = true) {
            stderr.append(process.errorStream.readBytes().toString(StandardCharsets.UTF_8))
        }
        val finished = if (timeoutSeconds == null) {
            process.waitFor()
            true
        } else {
            process.waitFor((timeoutSeconds * 1000.0).toLong(), TimeUnit.MILLISECONDS)
        }
        if (!finished) {
            process.destroyForcibly()
            process.waitFor(5, TimeUnit.SECONDS)
            outReader.join(1000)
            errReader.join(1000)
            throw ProcessTimeout(command, timeoutSeconds!!, stdout.toString(), stderr.toString())
        }
        outReader.join()
        errReader.join()
        val result = ProcessResult(command, process.exitValue(), stdout.toString(), stderr.toString())
        if (check && result.exitCode != 0) throw ProcessFailure(command, result.exitCode)
        return result
    }

    /** Runs [command] with [input] on standard input, as `subprocess.run(input=data)` does. */
    fun runWithInput(command: List<String>, input: ByteArray, timeoutSeconds: Double? = null): ProcessResult {
        val process = ProcessBuilder(command).redirectErrorStream(false).start()
        val stdout = StringBuilder()
        val stderr = StringBuilder()
        val writer = thread(isDaemon = true) {
            try {
                process.outputStream.use { it.write(input) }
            } catch (error: IOException) {
                // A process that exits before reading its input closes the pipe; Python reports the
                // stream results and no write failure, so the same happens here.
            }
        }
        val outReader = thread(isDaemon = true) {
            stdout.append(process.inputStream.readBytes().toString(StandardCharsets.UTF_8))
        }
        val errReader = thread(isDaemon = true) {
            stderr.append(process.errorStream.readBytes().toString(StandardCharsets.UTF_8))
        }
        val finished = if (timeoutSeconds == null) {
            process.waitFor()
            true
        } else {
            process.waitFor((timeoutSeconds * 1000.0).toLong(), TimeUnit.MILLISECONDS)
        }
        if (!finished) {
            process.destroyForcibly()
            process.waitFor(5, TimeUnit.SECONDS)
            writer.join(1000)
            outReader.join(1000)
            errReader.join(1000)
            throw ProcessTimeout(command, timeoutSeconds!!, stdout.toString(), stderr.toString())
        }
        writer.join()
        outReader.join()
        errReader.join()
        return ProcessResult(command, process.exitValue(), stdout.toString(), stderr.toString())
    }
}

/** Filesystem reads and writes in the shapes the Python tools use. */
object MigrationFiles {
    fun readText(path: Path): String? = try {
        Files.readString(path, StandardCharsets.UTF_8)
    } catch (error: IOException) {
        null
    }

    fun readTextOrEmpty(path: Path): String = readText(path) ?: ""

    /** Reads at most [limit] bytes, as `stream.read(limit)` does. */
    fun readBytes(path: Path, limit: Int = Int.MAX_VALUE): ByteArray? = try {
        Files.newInputStream(path).use { stream -> stream.readNBytes(limit) }
    } catch (error: IOException) {
        null
    }

    fun readBytesOrThrow(path: Path): ByteArray = Files.readAllBytes(path)

    fun writeText(path: Path, text: String) {
        path.parent?.let { Files.createDirectories(it) }
        Files.writeString(path, text, StandardCharsets.UTF_8)
    }

    fun writeBytes(path: Path, bytes: ByteArray) {
        path.parent?.let { Files.createDirectories(it) }
        Files.write(path, bytes)
    }

    fun digest(path: Path): String = FileDigest.sha256(path.toString())

    fun digest(bytes: ByteArray): String = io.github.rubixhacker.harness.contract.Sha256.of(bytes)

    fun exists(path: Path): Boolean = Files.exists(path)

    fun isFile(path: Path): Boolean = Files.isRegularFile(path)

    fun isSymlink(path: Path): Boolean = Files.isSymbolicLink(path)

    fun isDirectoryEmpty(path: Path): Boolean =
        Files.list(path).use { !it.findAny().isPresent }

    fun pathSeparator(): String = File.pathSeparator

    /** Python's `Path.with_suffix(suffix)`. */
    fun withSuffix(path: Path, suffix: String): Path {
        val name = path.fileName.toString()
        val dot = name.lastIndexOf('.')
        val stem = if (dot <= 0) name else name.substring(0, dot)
        return path.resolveSibling(stem + suffix)
    }

    /** Python's `str(Path)` rendering. */
    fun posix(path: Path): String = path.toString().replace(File.separatorChar, '/')

    /** Python's `path.relative_to(root).as_posix()`. */
    fun relativePosix(root: Path, path: Path): String =
        root.relativize(path).toString().replace(File.separatorChar, '/')

    /** Recursive copy, as `shutil.copytree` creates a new tree and rejects an existing target. */
    fun copyTree(source: Path, target: Path) {
        if (Files.exists(target)) throw IOException("[Errno 17] File exists: '$target'")
        Files.walk(source).use { stream ->
            stream.forEach { path ->
                val relative = source.relativize(path)
                val destination = if (relative.toString().isEmpty()) target else target.resolve(relative.toString())
                if (Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS)) {
                    Files.createDirectories(destination)
                } else {
                    destination.parent?.let { Files.createDirectories(it) }
                    Files.copy(path, destination)
                }
            }
        }
    }

    /** Every file or symlink below [root], as `Path.rglob("*")` lists them. */
    fun filesBelow(root: Path): List<Path> {
        if (!Files.isDirectory(root)) return emptyList()
        val paths = mutableListOf<Path>()
        Files.walk(root).use { stream ->
            stream.forEach { path ->
                if (path != root && (Files.isRegularFile(path) || Files.isSymbolicLink(path))) paths.add(path)
            }
        }
        return paths.sortedWith { left, right ->
            CanonicalJson.compareCodePoints(left.toString(), right.toString())
        }
    }

    /** Every file named `*.jar` directly inside [directory], as `Path.glob("*.jar")` finds them. */
    fun jars(directory: Path): List<Path> {
        if (!Files.isDirectory(directory)) return emptyList()
        val paths = mutableListOf<Path>()
        Files.list(directory).use { stream ->
            stream.forEach { path ->
                if (Files.isRegularFile(path) && path.fileName.toString().endsWith(".jar")) paths.add(path)
            }
        }
        return paths.sortedWith { left, right ->
            CanonicalJson.compareCodePoints(left.toString(), right.toString())
        }
    }

    /** `len(list(directory.rglob("*.class")))`. */
    fun countClassFiles(directory: Path): Int {
        if (!Files.isDirectory(directory)) return 0
        var count = 0
        Files.walk(directory).use { stream ->
            stream.forEach { if (Files.isRegularFile(it) && it.fileName.toString().endsWith(".class")) count++ }
        }
        return count
    }
}

/** Python's `shutil.which(name)` for the host under test. */
fun which(name: String): Path? {
    val path = System.getenv("PATH") ?: return null
    for (entry in path.split(File.pathSeparatorChar)) {
        if (entry.isEmpty()) continue
        val candidate = Path.of(entry, name)
        if (Files.isRegularFile(candidate) && Files.isExecutable(candidate)) return candidate
    }
    return null
}

/** The JDK `javac` that ships with the JVM running the harness. */
fun defaultJavac(): Path = Path.of(System.getProperty("java.home"), "bin", "javac")

/** The JDK `java` that ships with the JVM running the harness. */
fun defaultJava(): Path = Path.of(System.getProperty("java.home"), "bin", "java")

/** The repository root that holds the harness build. */
fun migrationRepositoryRoot(): Path {
    var current: Path? = Path.of("").toAbsolutePath()
    while (current != null) {
        if (Files.isRegularFile(current.resolve("tools/harness/settings.gradle.kts"))) return current
        current = current.parent
    }
    error("repository root with tools/harness/settings.gradle.kts was not found")
}
