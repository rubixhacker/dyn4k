package io.github.rubixhacker.harness.compatibility

import io.github.rubixhacker.harness.host.FileDigest
import java.io.File
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.LinkOption
import java.nio.file.Path
import java.util.concurrent.TimeUnit
import kotlin.concurrent.thread

/** One finished process, with the bytes decoded as UTF-8 the way `subprocess.run(text=True)` reads them. */
data class ProcessOutput(
    val command: List<String>,
    val exitCode: Int,
    val stdout: String,
    val stderr: String,
)

/** A process that exceeded its timeout, standing in for `subprocess.TimeoutExpired`. */
class ProcessTimeout(val command: List<String>, val timeoutSeconds: Long) :
    RuntimeException("Command '${command.joinToString(" ")}' timed out after $timeoutSeconds seconds")

/** Runs commands the way the compatibility tooling runs them with `subprocess.run`. */
object Processes {
    fun run(
        command: List<String>,
        cwd: String? = null,
        environment: Map<String, String>? = null,
        timeoutSeconds: Long = 1200,
        check: Boolean = false,
    ): ProcessOutput {
        val builder = ProcessBuilder(command).redirectErrorStream(false)
        if (cwd != null) builder.directory(File(cwd))
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
        val finished = process.waitFor(timeoutSeconds, TimeUnit.SECONDS)
        if (!finished) {
            process.destroyForcibly()
            outReader.join(1000)
            errReader.join(1000)
            throw ProcessTimeout(command, timeoutSeconds)
        }
        outReader.join()
        errReader.join()
        val result = ProcessOutput(command, process.exitValue(), stdout.toString(), stderr.toString())
        if (check && result.exitCode != 0) {
            throw IllegalStateException(
                "command ${command.joinToString(" ")} failed: ${result.stderr.trim()}",
            )
        }
        return result
    }

    /** Runs `git -C <root> <args>` and returns its trimmed stdout, requiring success. */
    fun git(root: String, vararg arguments: String): String =
        run(listOf("git", "-C", root, *arguments), check = true).stdout.trim()
}

/** The repository filesystem used by the compatibility host adapters. */
class JvmCorpusFiles : CorpusFiles {
    override fun isSymlink(path: String): Boolean = Files.isSymbolicLink(Path.of(path))

    override fun isFile(path: String): Boolean = Files.isRegularFile(Path.of(path))

    override fun isDirectory(path: String): Boolean = Files.isDirectory(Path.of(path))

    override fun digest(path: String): String = FileDigest.sha256(path)

    override fun readText(path: String): String = Files.readString(Path.of(path), StandardCharsets.UTF_8)

    override fun filesBelow(root: String): List<String> = walk(root) { path ->
        !Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS)
    }

    override fun entriesBelow(root: String): List<String> = walk(root) { true }

    private fun walk(root: String, include: (Path) -> Boolean): List<String> {
        val base = Path.of(root)
        val result = mutableListOf<String>()
        if (!Files.exists(base, LinkOption.NOFOLLOW_LINKS)) return result
        Files.walk(base).use { stream ->
            val iterator = stream.iterator()
            while (iterator.hasNext()) {
                val path = iterator.next()
                if (path == base) continue
                if (include(path)) result.add(base.relativize(path).toString())
            }
        }
        return result
    }
}

/** Reads the artifact JARs the module probes describe. */
object Archives {
    fun entries(jar: String): List<String> =
        java.util.zip.ZipFile(File(jar)).use { archive ->
            archive.entries().asSequence().map { it.name }.toList()
        }

    fun read(jar: String, name: String): ByteArray =
        java.util.zip.ZipFile(File(jar)).use { archive ->
            val entry = archive.getEntry(name)
                ?: throw NoSuchElementException("archive entry is absent: $name")
            archive.getInputStream(entry).use { it.readBytes() }
        }
}
