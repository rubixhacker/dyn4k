package io.github.rubixhacker.harness.baseline

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import java.io.ByteArrayOutputStream
import java.io.PrintStream
import java.nio.file.Files
import java.nio.file.Path

/**
 * The fixtures the Python unittest suites build for `tools/baseline/verify.py`.
 *
 * Each helper mirrors a helper in `tools/baseline/test_verify.py` or
 * `tools/baseline/test_added_members.py`: the same `javac` invocation, the same `jar` archive, the
 * same `javap` probe and the same command invocation. They need only a JDK and git on this host;
 * no pinned `dyn4j-6.0.0.jar`, no JDK 8 runtime and no network.
 */

/** One run of [BaselineCli]: the exit status and what it wrote. */
internal class CliResult(val code: Int, val stdout: String, val stderr: String) {
    /**
     * The JSON document the command printed, or an empty document when it stopped before printing
     * one. A run-stopping condition writes its message on stderr and exits 1.
     */
    fun report(): JsonObject =
        if (stdout.isBlank()) JsonObject(emptyMap()) else Json.parseToJsonElement(stdout).jsonObject
}

/** `verify.run`: the real process, captured by the port's own seam. */
internal val seams: BaselineSeams = RealSeams

/** `subprocess.run(["git", "-C", root, *args], check=True).stdout.strip()`. */
internal fun git(root: Path, vararg args: String, environment: Map<String, String>? = null): String =
    pyStrip(seams.requireRun(listOf("git", "-C", root.toString()) + args, environment).stdoutText())

/** `os.environ` without the `GIT_*` entries, the environment the Python helpers use. */
internal fun gitCleanEnvironment(): Map<String, String> =
    System.getenv().filterKeys { !it.startsWith("GIT_") }

/** `os.environ` with the given entries replaced. */
internal fun poisonEnvironment(poison: Map<String, String>): Map<String, String> =
    System.getenv() + poison

/** `subprocess.run(["javac", ...], check=True)` that returns the captured streams. */
internal fun javac(destination: Path, sources: List<Path>, extra: List<String> = emptyList()): ProcessOutput {
    makeDirectories(destination)
    return seams.run(
        listOf("javac", "--release", "8", "-Xlint:-options", "-d", destination.toString()) +
            extra + sources.map { it.toString() },
        null,
    )
}

/** `ComparatorTests.jar`: compile sources, archive the classes, return the archive path. */
internal fun jarOf(
    root: Path,
    sources: Map<String, String>,
    syntheticMethod: Pair<String, String>? = null,
): Path {
    makeDirectories(root)
    val paths = sources.map { (name, source) ->
        val path = root.resolve(name)
        path.parent?.let { makeDirectories(it) }
        writeText(path, source)
        path
    }
    val classes = root.resolve("classes")
    makeDirectories(classes)
    val compiled = javac(classes, paths)
    check(compiled.exitCode == 0) { "javac failed: ${compiled.stderrText()}" }
    if (syntheticMethod != null) {
        val (className, methodName) = syntheticMethod
        val target = classes.resolve("$className.class")
        writeBytes(target, markSynthetic(readBytes(target), methodName))
    }
    val archive = root.resolve("library.jar")
    seams.requireRun(listOf("jar", "cf", archive.toString(), "-C", classes.toString(), "."))
    return archive
}

/** `compile_source`: one consumer source compiled against one archive. */
internal fun compileSource(root: Path, archive: Path, source: String, label: String): ProcessOutput {
    val path = root.resolve("Consumer.java")
    writeText(path, source)
    val output = root.resolve(label)
    makeDirectories(output)
    return seams.run(
        listOf(
            "javac", "--release", "8", "-Xlint:-options", "-cp", archive.toString(),
            "-d", output.toString(), path.toString(),
        ),
        null,
    )
}

/** `ComparatorTests.consumer`: write the consumer source into the case directory. */
internal fun consumer(root: Path, source: String): Path {
    val path = root.resolve("Consumer.java")
    writeText(path, source)
    return path
}

/** `command(...)` and `test_compare_command(...)`: run the ported CLI in-process. */
internal fun cli(
    vararg argv: String,
    overlappingSeams: BaselineSeams = seams,
    policy: BaselinePolicy = BaselinePolicy(),
): CliResult {
    val out = ByteArrayOutputStream()
    val err = ByteArrayOutputStream()
    val code = PrintStream(out, true, "UTF-8").use { stdout ->
        PrintStream(err, true, "UTF-8").use { stderr ->
            BaselineCli.run(argv.toList(), overlappingSeams, policy, stdout, stderr)
        }
    }
    return CliResult(code, out.toString("UTF-8"), err.toString("UTF-8"))
}

/** `compare(baseline, candidate)`: the `compare` subcommand with the baseline digest accepted. */
internal fun compare(
    baseline: Path,
    candidate: Path,
    vararg extra: String,
    overlappingSeams: BaselineSeams = seams,
    policy: BaselinePolicy = BaselinePolicy(binarySha256 = digest(baseline)),
): Pair<CliResult, JsonObject> {
    val result = cli(
        "compare",
        "--baseline-jar", baseline.toString(),
        "--candidate", candidate.toString(),
        *extra,
        overlappingSeams = overlappingSeams,
        policy = policy,
    )
    return result to result.report()
}

/** A git checkout that is at [revision] and holds the given tracked files. */
internal class Checkout(val root: Path, val revision: String)

/** `git init` + `git add src` + one commit, the way every Python fixture prepares a repository. */
internal fun initCheckout(root: Path, files: Map<String, String>, message: String = "fixture"): Checkout {
    for ((name, text) in files) {
        val path = root.resolve(name)
        path.parent?.let { makeDirectories(it) }
        writeText(path, text)
    }
    makeDirectories(root)
    git(root, "init", "-q", environment = gitCleanEnvironment())
    git(root, "add", "src", environment = gitCleanEnvironment())
    git(
        root,
        "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", message,
        environment = gitCleanEnvironment(),
    )
    val revision = git(root, "rev-parse", "HEAD", environment = gitCleanEnvironment())
    return Checkout(root, revision)
}

/** A sources archive holding one entry per [entries] key, the way the Python suites write one. */
internal fun sourcesArchive(path: Path, entries: Map<String, String>) {
    makeDirectories(path.parent)
    java.util.zip.ZipOutputStream(Files.newOutputStream(path)).use { zip ->
        for ((name, text) in entries) {
            zip.putNextEntry(java.util.zip.ZipEntry(name))
            zip.write(text.encodeToByteArray())
            zip.closeEntry()
        }
    }
}

/** `mark_synthetic`: set `ACC_SYNTHETIC` on one method of one class file. */
internal fun markSynthetic(binary: ByteArray, target: String): ByteArray {
    val data = binary.copyOf()
    fun u1(at: Int): Int = data[at].toInt() and 0xFF
    fun u2(at: Int): Int = (u1(at) shl 8) or u1(at + 1)
    fun u4(at: Int): Int = (u2(at) shl 16) or u2(at + 2)
    var offset = 8
    val count = u2(offset)
    offset += 2
    val names = mutableMapOf<Int, String>()
    var index = 1
    while (index < count) {
        val tag = u1(offset)
        offset += 1
        when {
            tag == 1 -> {
                val size = u2(offset)
                offset += 2
                names[index] = String(data, offset, size, Charsets.UTF_8)
                offset += size
            }
            tag in listOf(3, 4, 9, 10, 11, 12, 17, 18) -> offset += 4
            tag in listOf(5, 6) -> {
                offset += 8
                index += 1
            }
            tag in listOf(7, 8, 16, 19, 20) -> offset += 2
            tag == 15 -> offset += 3
            else -> error("unknown constant pool tag $tag")
        }
        index += 1
    }
    offset += 6
    val interfaces = u2(offset)
    offset += 2 + 2 * interfaces

    fun skipMembers(position: Int): Int {
        var at = position
        val number = u2(at)
        at += 2
        repeat(number) {
            at += 6
            val attributes = u2(at)
            at += 2
            repeat(attributes) {
                val size = u4(at + 2)
                at += 6 + size
            }
        }
        return at
    }

    offset = skipMembers(offset)
    val number = u2(offset)
    offset += 2
    var found = false
    repeat(number) {
        val name = names.getValue(u2(offset + 2))
        if (name == target) {
            val flags = u2(offset)
            val updated = flags or 0x1000
            data[offset] = ((updated shr 8) and 0xFF).toByte()
            data[offset + 1] = (updated and 0xFF).toByte()
            found = true
        }
        offset += 6
        val attributes = u2(offset)
        offset += 2
        repeat(attributes) {
            val size = u4(offset + 2)
            offset += 6 + size
        }
    }
    check(found) { "method $target not found" }
    return data
}

/** `tempfile.TemporaryDirectory()` with the block form the Python suites use. */
internal fun withCase(block: (Path) -> Unit) {
    val directory = Files.createTempDirectory("dyn4k-baseline-case-")
    try {
        block(directory)
    } finally {
        directory.toFile().deleteRecursively()
    }
}

/** The three `javap`/`jar`-style checks the Python suites perform directly. */
internal fun javapOutput(archive: Path, className: String, vararg flags: String): String =
    seams.requireRun(listOf("javap", *flags, "-classpath", archive.toString(), className)).stdoutText()

/** A seam decorator: one behaviour replaced, everything else delegated. */
internal open class TestSeams(private val base: BaselineSeams = RealSeams) : BaselineSeams {
    override fun run(command: List<String>, environment: Map<String, String>?): ProcessOutput =
        base.run(command, environment)

    override fun jarInventory(
        binary: Path,
        only: Set<String>?,
        visibility: String,
        verbose: Boolean,
    ): JarInventory = base.jarInventory(binary, only, visibility, verbose)

    override fun openZip(path: Path): ZipArchive = base.openZip(path)

    override fun addedMemberGate(
        selected: Set<String>,
        baselineSignatures: Map<String, String>,
        candidateSignatures: Map<String, String>,
        baselineClasspath: String,
        candidateClasspath: String,
        artifactSha256: String,
    ): MemberAdditionResult = base.addedMemberGate(
        selected,
        baselineSignatures,
        candidateSignatures,
        baselineClasspath,
        candidateClasspath,
        artifactSha256,
    )
}
