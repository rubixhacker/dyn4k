package io.github.rubixhacker.harness.baseline

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.StandardCopyOption

/**
 * `verify.execute`: compile the pinned upstream JUnit suite against the pinned baseline and run it,
 * then prove that every input, the harness class file and the working checkout still hold the bytes
 * the report describes.
 */
fun execute(
    seams: BaselineSeams,
    source: Path,
    binary: Path,
    cache: Path,
    output: Path,
    policy: BaselinePolicy = BaselinePolicy(),
    processEnvironment: Map<String, String> = System.getenv(),
): JsonObject = withTemporaryDirectory("dyn4k-run-inputs-") { privateRoot ->
    executeSnapshot(seams, source, binary, cache, output, privateRoot, policy, processEnvironment)
}

private fun executeSnapshot(
    seams: BaselineSeams,
    source: Path,
    binary: Path,
    cache: Path,
    output: Path,
    privateRoot: Path,
    policy: BaselinePolicy,
    processEnvironment: Map<String, String>,
): JsonObject {
    val pinnedSources = checkedJavaSources(seams, source, policy.commit, null, processEnvironment)
    val deps = cache.resolve("deps")
    val junit = deps.resolve(Baseline.JUNIT_FILE)
    val hamcrest = deps.resolve(Baseline.HAMCREST_FILE)
    fetch(Baseline.JUNIT, junit)
    fetch(Baseline.HAMCREST, hamcrest)
    val testSourceRoot = source.resolve("src/test/java")
    val testSources = javaSourcesUnder(testSourceRoot)
    val resources = source.resolve("src/test/resources")
    val testInputs = testSources + resourceFilesUnder(resources)
    val work = cache.resolve("run")
    if (exists(work)) work.toFile().deleteRecursively()
    val inputRoot = privateRoot.resolve("inputs")
    val artifacts = privateRoot.resolve("artifacts")
    makeDirectories(artifacts)
    val snapshots = mutableListOf<Pair<Path, String>>()
    val testHashes = linkedMapOf<String, String>()
    for (path in testInputs) {
        val relative = source.relativize(path).toString()
        val snapshot = inputRoot.resolve(relative)
        snapshot.parent?.let { makeDirectories(it) }
        copyFile(path, snapshot)
        val sourceHash = digest(snapshot)
        snapshots.add(snapshot to sourceHash)
        testHashes[relative] = sourceHash
    }
    val revision = pyStrip(
        pinnedGit(seams, source, listOf("rev-parse", "HEAD"), processEnvironment).stdoutText(),
    )
    if (revision != policy.commit) {
        throw IllegalArgumentException(
            "pinned source revision mismatch: expected ${policy.commit}, got $revision",
        )
    }
    val tracked = pySplitLines(
        pinnedGit(
            seams,
            source,
            listOf("ls-tree", "-r", "--name-only", policy.commit, "src/test/java", "src/test/resources"),
            processEnvironment,
        ).stdoutText(),
    )
    val expectedInputs = tracked
        .filter { it.endsWith(".java") || it.startsWith("src/test/resources/") }
        .toSet()
    if (expectedInputs != testHashes.keys) {
        throw IllegalArgumentException("pinned source test input paths differ")
    }
    for (path in expectedInputs) {
        val committed = pinnedGit(
            seams,
            source,
            listOf("show", "${policy.commit}:$path"),
            processEnvironment,
        ).stdout
        if (!readBytes(inputRoot.resolve(path)).contentEquals(committed)) {
            throw IllegalArgumentException("pinned source test input bytes differ: $path")
        }
    }
    val snapshotTestSources = testSources.map { inputRoot.resolve(source.relativize(it).toString()) }
    val testClasses = snapshotTestSources.filter {
        val text = readText(it)
        "@Test" in text || "@RunWith" in text
    }
    if (testClasses.isEmpty()) throw BaselineExit("empty test suite")
    val binarySnapshot = artifacts.resolve("baseline.jar")
    val junitSnapshot = artifacts.resolve("junit.jar")
    val hamcrestSnapshot = artifacts.resolve("hamcrest.jar")
    for ((original, snapshot) in listOf(
        binary to binarySnapshot,
        junit to junitSnapshot,
        hamcrest to hamcrestSnapshot,
    )) {
        copyFile(original, snapshot)
        snapshots.add(snapshot to digest(snapshot))
    }
    val binaryHash = snapshots[snapshots.size - 3].second
    val junitHash = snapshots[snapshots.size - 2].second
    val hamcrestHash = snapshots[snapshots.size - 1].second
    if (binaryHash != policy.binarySha256) {
        throw IllegalArgumentException(
            "baseline SHA-256 mismatch: expected ${policy.binarySha256}, got $binaryHash",
        )
    }
    val classes = work.resolve("classes")
    makeDirectories(classes)
    val classpath = listOf(binarySnapshot, junitSnapshot, hamcrestSnapshot)
        .joinToString(java.io.File.pathSeparator) { it.toString() }
    val argfile = work.resolve("test-sources.args")
    writeText(
        argfile,
        snapshotTestSources.joinToString("\n") { "\"" + it.toString().replace("\"", "\\\"") + "\"" } + "\n",
    )
    seams.requireRun(
        listOf(
            "javac", "-encoding", "UTF-8", "--release", "8", "-cp", classpath,
            "-d", classes.toString(), "@$argfile",
        ),
    )
    val snapshotResources = inputRoot.resolve("src/test/resources")
    if (exists(snapshotResources)) copyTree(snapshotResources, classes)
    val testJavaRoot = inputRoot.resolve("src/test/java")
    val classNames = sortedByCodePoint(
        testClasses.map { source -> classFileName(testJavaRoot.relativize(source)) }.toSet(),
    )
    val reportClass = work.resolve("BaselineJUnitReport.java")
    writeText(reportClass, REPORT_HARNESS)
    seams.requireRun(
        listOf(
            "javac", "--release", "8", "-cp",
            classpath + java.io.File.pathSeparator + classes, "-d", classes.toString(),
            reportClass.toString(),
        ),
    )
    val harnessBytes = readBytes(classes.resolve("BaselineJUnitReport.class"))
    val harnessMajor = ((harnessBytes[6].toInt() and 0xFF) shl 8) or (harnessBytes[7].toInt() and 0xFF)
    val result = seams.run(
        listOf(
            "java", "-cp", classpath + java.io.File.pathSeparator + classes,
            "BaselineJUnitReport",
        ) + classNames,
        null,
    )
    for ((snapshot, expectedHash) in snapshots) {
        if (digest(snapshot) != expectedHash) {
            throw IllegalArgumentException(
                "run input snapshot SHA-256 changed during execution: $snapshot",
            )
        }
    }
    checkedJavaSources(seams, source, policy.commit, pinnedSources.pinned, processEnvironment)
    val actual = resultField(result.stdoutText(), "ACTUAL_TESTS")
    val failures = resultField(result.stdoutText(), "FAILURES")
    val summary = buildJsonObject {
        put("commit", policy.commit)
        put("binary_sha256", binaryHash)
        put("test_files", snapshotTestSources.size)
        put("test_classes", classNames.size)
        put("actual_executed_cases", actual)
        put("failures", failures)
        put("ignored", resultField(result.stdoutText(), "IGNORED"))
        put("process_exit_code", result.exitCode)
        put("output", result.stdoutText())
        put("stderr", result.stderrText())
        put(
            "javac_version",
            pyStrip(seams.requireRun(listOf("javac", "-version")).stdoutText()),
        )
        put(
            "java_version",
            pySplitLines(seams.requireRun(listOf("java", "-version")).stderrText()).first(),
        )
        put("compile_release", 8)
        put("harness_class_major", harnessMajor)
        put(
            "test_input_sha256",
            JsonObject(testHashes.mapValues { JsonPrimitive(it.value) }),
        )
        put("junit_sha256", junitHash)
        put("hamcrest_sha256", hamcrestHash)
    }
    output.parent?.let { makeDirectories(it) }
    writeText(output, PythonJson.renderIndented(summary) + "\n")
    try {
        validateRunReport(summary, policy.expectedCases)
    } catch (error: IllegalArgumentException) {
        throw BaselineExit(
            "upstream baseline suite failed: ${error.message}; see the retained run summary",
        )
    }
    return summary
}

/** `sorted((root).rglob("*.java"))`, or an empty list when the tree is absent. */
private fun javaSourcesUnder(root: Path): List<Path> {
    if (!Files.isDirectory(root)) return emptyList()
    val found = mutableListOf<Path>()
    Files.walk(root).use { paths ->
        paths.forEach { path ->
            if (path.fileName.toString().endsWith(".java") && Files.isRegularFile(path)) found.add(path)
        }
    }
    return found.sortedWith { left, right ->
        pyComparePaths(root.relativize(left).toString(), root.relativize(right).toString())
    }
}

/** `sorted(path for path in (root).rglob("*") if path.is_file())`. */
private fun resourceFilesUnder(root: Path): List<Path> {
    if (!Files.isDirectory(root)) return emptyList()
    val found = mutableListOf<Path>()
    Files.walk(root).use { paths ->
        paths.forEach { path ->
            if (path != root && Files.isRegularFile(path)) found.add(path)
        }
    }
    return found.sortedWith { left, right ->
        pyComparePaths(root.relativize(left).toString(), root.relativize(right).toString())
    }
}

private fun pyComparePaths(left: String, right: String): Int =
    io.github.rubixhacker.harness.contract.CanonicalJson.compareCodePoints(left, right)

/** `path.relative_to(root).with_suffix("").parts` joined with dots. */
private fun classFileName(relative: Path): String {
    val name = relative.fileName.toString()
    val stem = if ('.' in name.substring(1)) name.substringBeforeLast('.') else name
    val parts = (0 until relative.nameCount - 1).map { relative.getName(it).toString() } + stem
    return parts.joinToString(".")
}

/** `shutil.copytree(source, target, dirs_exist_ok=True)`. */
private fun copyTree(source: Path, target: Path) {
    Files.walk(source).use { paths ->
        paths.forEach { path ->
            val destination = target.resolve(source.relativize(path).toString())
            if (Files.isDirectory(path)) {
                makeDirectories(destination)
            } else {
                destination.parent?.let { makeDirectories(it) }
                Files.copy(path, destination, StandardCopyOption.REPLACE_EXISTING)
            }
        }
    }
}

/** The JUnit runner harness `verify._execute_snapshot` writes. Byte-identical to the Python text. */
internal val REPORT_HARNESS: String = """
import org.junit.runner.JUnitCore;
import org.junit.runner.Result;
public final class BaselineJUnitReport {
 public static void main(String[] args) { Result r = new JUnitCore().run(load(args));
  System.out.println("ACTUAL_TESTS=" + r.getRunCount()); System.out.println("FAILURES=" + r.getFailureCount());
  System.out.println("IGNORED=" + r.getIgnoreCount()); if (!r.wasSuccessful()) { r.getFailures().forEach(System.err::println); System.exit(1); } }
 static Class<?>[] load(String[] names) { try { Class<?>[] c = new Class<?>[names.length]; for (int i=0;i<names.length;i++) c[i]=Class.forName(names[i]); return c; } catch(Exception e) { throw new RuntimeException(e); } }
}
""".trimStart('\n')
