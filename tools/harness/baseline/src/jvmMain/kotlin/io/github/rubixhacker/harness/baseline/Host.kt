package io.github.rubixhacker.harness.baseline

import io.github.rubixhacker.harness.host.FileDigest
import java.io.ByteArrayOutputStream
import java.io.File
import java.io.IOException
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.LinkOption
import java.nio.file.Path
import java.util.zip.ZipFile

/** One captured process: the exit status plus the raw stdout and stderr bytes. */
class ProcessOutput(
    val exitCode: Int,
    val stdout: ByteArray,
    val stderr: ByteArray,
) {
    /** The text-mode stdout `subprocess.run(text=True)` returns. */
    fun stdoutText(): String = textMode(stdout)

    /** The text-mode stderr `subprocess.run(text=True)` returns. */
    fun stderrText(): String = textMode(stderr)
}

/** Universal-newline decoding, which is what `subprocess.run(text=True)` applies. */
internal fun textMode(bytes: ByteArray): String {
    val text = String(bytes, StandardCharsets.UTF_8)
    return text.replace("\r\n", "\n").replace('\r', '\n')
}

/** The entries and uncompressed bytes of a ZIP archive. */
interface ZipArchive : AutoCloseable {
    fun names(): List<String>

    fun read(name: String): ByteArray
}

/** The class-file inventory `verify.jar_types` returns. */
data class JarInventory(val classes: List<String>, val signatures: Map<String, String>)

/**
 * The impure steps `verify.py` performs, behind one seam.
 *
 * The Python unittest suites replace `verify.jar_types`, `verify.subprocess.run`,
 * `verify.zipfile.ZipFile` and `verify.added_member_gate` mid-run to prove the identity checks hold
 * under concurrent replacement. The Kotlin port keeps the same seams so those proofs are ported
 * with the cases.
 */
interface BaselineSeams {
    /** `verify.run` before `check=True` is applied; `environment` null inherits the process env. */
    fun run(command: List<String>, environment: Map<String, String>?): ProcessOutput

    /** `verify.jar_types`. */
    fun jarInventory(binary: Path, only: Set<String>?, visibility: String, verbose: Boolean): JarInventory

    /** `zipfile.ZipFile(path)`. */
    fun openZip(path: Path): ZipArchive

    /** `verify.added_member_gate`. */
    fun addedMemberGate(
        selected: Set<String>,
        baselineSignatures: Map<String, String>,
        candidateSignatures: Map<String, String>,
        baselineClasspath: String,
        candidateClasspath: String,
        artifactSha256: String,
    ): MemberAdditionResult
}

/** `verify.run(command, check=True)`. */
fun BaselineSeams.requireRun(
    command: List<String>,
    environment: Map<String, String>? = null,
): ProcessOutput {
    val output = run(command, environment)
    if (output.exitCode != 0) throw CommandFailure(command, output.exitCode)
    return output
}

/** `verify.digest`. */
fun digest(path: Path): String = FileDigest.sha256(path)

/** `shutil.copyfile`: replace the destination with the source bytes. */
internal fun copyFile(source: Path, target: Path) {
    Files.copy(source, target, java.nio.file.StandardCopyOption.REPLACE_EXISTING)
}

/** `verify.jar_types`: every class the archive holds, and the `javap` surface of each. */
fun BaselineSeams.jarTypes(
    binary: Path,
    only: Set<String>? = null,
    visibility: String = "-protected",
    verbose: Boolean = false,
): JarInventory {
    val names = pySplitLines(requireRun(listOf("jar", "tf", binary.toString())).stdoutText())
    val classes = sortedByCodePoint(
        names
            .filter { it.endsWith(".class") && !it.endsWith("module-info.class") }
            .map { it.dropLast(".class".length).replace('/', '.') },
    )
    val signatures = linkedMapOf<String, String>()
    for (name in classes) {
        if (only != null && name !in only) continue
        val command = mutableListOf("javap", "-classpath", binary.toString(), visibility, "-s")
        if (verbose) command.add("-v")
        command.add(name)
        signatures[name] = requireRun(command).stdoutText()
    }
    return JarInventory(classes, signatures)
}

private fun runProcess(command: List<String>, environment: Map<String, String>?): ProcessOutput {
    val builder = ProcessBuilder(command)
    if (environment != null) {
        val target = builder.environment()
        target.clear()
        target.putAll(environment)
    }
    val process = try {
        builder.start()
    } catch (error: IOException) {
        throw error
    }
    process.outputStream.close()
    val stdout = ByteArrayOutputStream()
    val stderr = ByteArrayOutputStream()
    val outThread = Thread { process.inputStream.use { it.copyTo(stdout) } }
    val errThread = Thread { process.errorStream.use { it.copyTo(stderr) } }
    outThread.isDaemon = true
    errThread.isDaemon = true
    outThread.start()
    errThread.start()
    val exitCode = process.waitFor()
    outThread.join()
    errThread.join()
    return ProcessOutput(exitCode, stdout.toByteArray(), stderr.toByteArray())
}

private class JavaZip(private val archive: ZipFile) : ZipArchive {
    override fun names(): List<String> = archive.entries().toList().map { it.name }

    override fun read(name: String): ByteArray {
        val entry = archive.getEntry(name)
            ?: throw IllegalArgumentException("archive entry is missing: $name")
        return archive.getInputStream(entry).use { it.readBytes() }
    }

    override fun close() {
        archive.close()
    }
}

/** The real process, archive, `javap` and gate implementations. */
object RealSeams : BaselineSeams {
    override fun run(command: List<String>, environment: Map<String, String>?): ProcessOutput =
        runProcess(command, environment)

    override fun jarInventory(
        binary: Path,
        only: Set<String>?,
        visibility: String,
        verbose: Boolean,
    ): JarInventory = jarTypes(binary, only, visibility, verbose)

    override fun openZip(path: Path): ZipArchive = JavaZip(ZipFile(path.toFile()))

    override fun addedMemberGate(
        selected: Set<String>,
        baselineSignatures: Map<String, String>,
        candidateSignatures: Map<String, String>,
        baselineClasspath: String,
        candidateClasspath: String,
        artifactSha256: String,
    ): MemberAdditionResult = MemberAddition.gate(
        selected = selected,
        baselineSignatures = baselineSignatures,
        candidateSignatures = candidateSignatures,
        baselineClasspath = baselineClasspath,
        candidateClasspath = candidateClasspath,
        artifactSha256 = artifactSha256,
        loadSignature = { classpath, name ->
            requireRun(listOf("javap", "-classpath", classpath, "-p", "-s", "-v", name)).stdoutText()
        },
    )
}

/** `Path.is_file()` from Python: a regular file, following symlinks. */
internal fun isFile(path: Path): Boolean = Files.isRegularFile(path)

/** `Path.is_dir()` from Python: a directory, following symlinks. */
internal fun isDirectory(path: Path): Boolean = Files.isDirectory(path)

/** `Path.exists()` from Python. */
internal fun exists(path: Path): Boolean = Files.exists(path)

/** `Path.lstat()` presence without following the final component. */
internal fun existsNoFollow(path: Path): Boolean = Files.exists(path, LinkOption.NOFOLLOW_LINKS)

/** `Path.mkdir(parents=True, exist_ok=True)`. */
internal fun makeDirectories(path: Path) {
    Files.createDirectories(path)
}

/** `Path.write_text(text)`: UTF-8, no newline translation. */
internal fun writeText(path: Path, text: String) {
    Files.write(path, text.toByteArray(StandardCharsets.UTF_8))
}

/** `Path.write_bytes(bytes)`. */
internal fun writeBytes(path: Path, bytes: ByteArray) {
    Files.write(path, bytes)
}

/** `Path.read_bytes()`. */
internal fun readBytes(path: Path): ByteArray = Files.readAllBytes(path)

/** `Path.read_text(errors="replace")`. */
internal fun readText(path: Path): String = String(Files.readAllBytes(path), StandardCharsets.UTF_8)

/** `tempfile.TemporaryDirectory`, closed by [block]. */
internal inline fun <T> withTemporaryDirectory(prefix: String, block: (Path) -> T): T {
    val directory = Files.createTempDirectory(prefix)
    try {
        return block(directory)
    } finally {
        directory.toFile().deleteRecursively()
    }
}

/** The repository root the verifier's relative defaults resolve against. */
internal fun repositoryRoot(): File = File("").absoluteFile
