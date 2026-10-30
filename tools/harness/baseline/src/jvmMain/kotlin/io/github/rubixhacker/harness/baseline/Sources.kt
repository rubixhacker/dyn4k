package io.github.rubixhacker.harness.baseline

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.io.IOException
import java.nio.file.Files
import java.nio.file.LinkOption
import java.nio.file.Path
import java.nio.file.StandardCopyOption
import java.nio.file.attribute.BasicFileAttributes
import java.nio.file.attribute.FileTime
import java.util.concurrent.TimeUnit

/** `SystemExit`: a run-stopping condition the command reports and exits on. */
class BaselineExit(message: String) : Exception(message)

/** The three outputs `verify.checked_java_sources` returns. */
data class CheckedSources(
    val production: List<String>,
    val tests: List<String>,
    val pinned: Map<String, ByteArray>,
)

/** `verify.verify_source_inputs`'s provenance record. */
data class SourceProvenance(
    val commit: String,
    val trackedProductionJavaFiles: Int,
    val sourceJarJavaFiles: Int,
    val sourceJarSha256: String,
) {
    fun toJson(): JsonObject = buildJsonObject {
        put("commit", commit)
        put("tracked_production_java_files", trackedProductionJavaFiles)
        put("source_jar_java_files", sourceJarJavaFiles)
        put("source_jar_sha256", sourceJarSha256)
        put("source_inputs_clean", true)
        put("source_jar_matches_tracked_bytes", true)
    }
}

/**
 * `verify.pinned_git`: one git command against one pinned work tree.
 *
 * [processEnvironment] is the environment the git call observes. The Python module reads
 * `os.environ` at every call; the port takes it as a parameter so a test can prove that a
 * redirected `GIT_DIR`, `GIT_WORK_TREE` or `GIT_INDEX_FILE` cannot hide a changed source file.
 */
fun pinnedGit(
    seams: BaselineSeams,
    source: Path,
    command: List<String>,
    processEnvironment: Map<String, String> = System.getenv(),
): ProcessOutput {
    // `Path.absolute()`: make absolute without resolving `.` or `..`, like the Python module.
    val absolute = source.toAbsolutePath()
    val metadata = absolute.resolve(".git")
    if (Files.isSymbolicLink(absolute) || !isDirectory(absolute) ||
        Files.isSymbolicLink(metadata) || !exists(metadata)
    ) {
        throw IllegalArgumentException("source path is not a Git checkout: $absolute")
    }
    val environment = gitEnvironment(
        processEnvironment,
        networkAuth = command.isNotEmpty() && command[0] == "fetch",
    )
    return seams.requireRun(
        listOf(
            "git", "--no-replace-objects", "-C", absolute.toString(),
            "--work-tree", absolute.toString(),
        ) + command,
        environment,
    )
}

/**
 * `verify.checked_java_sources`: the checkout must be at [commit], clean and untracked-free under
 * the three input trees, and every tracked Java path must still hold its committed bytes.
 */
fun checkedJavaSources(
    seams: BaselineSeams,
    source: Path,
    commit: String,
    expected: Map<String, ByteArray>? = null,
    processEnvironment: Map<String, String> = System.getenv(),
): CheckedSources {
    val revision = pyStrip(
        pinnedGit(seams, source, listOf("rev-parse", "HEAD"), processEnvironment).stdoutText(),
    )
    if (revision != commit) {
        throw IllegalArgumentException("pinned source revision mismatch: expected $commit, got $revision")
    }
    val status = pinnedGit(
        seams,
        source,
        listOf(
            "status", "--porcelain=v1", "--untracked-files=all", "--ignored", "--",
            "src/main/java", "src/test/java", "src/test/resources",
        ),
        processEnvironment,
    ).stdoutText()
    if (status.isNotEmpty()) {
        throw IllegalArgumentException("dirty or untracked source inputs: ${pyStrip(status)}")
    }
    val tracked = pySplitLines(
        pinnedGit(
            seams,
            source,
            listOf("ls-tree", "-r", "--name-only", commit, "src/main/java", "src/test/java"),
            processEnvironment,
        ).stdoutText(),
    )
    val production = tracked.filter { it.startsWith("src/main/java/") && it.endsWith(".java") }
    val tests = tracked.filter { it.startsWith("src/test/java/") && it.endsWith(".java") }
    val paths = production + tests
    if (paths.isEmpty() || paths.size != paths.toSet().size) {
        throw IllegalArgumentException("pinned source Java paths are empty or duplicated")
    }
    if (expected != null && paths.toSet() != expected.keys) {
        throw IllegalArgumentException("pinned source Java paths changed during verification")
    }
    val pinned = linkedMapOf<String, ByteArray>()
    for (path in paths) {
        val committed = pinnedGit(
            seams,
            source,
            listOf("show", "$commit:$path"),
            processEnvironment,
        ).stdout
        val recorded = expected?.get(path)
        if (recorded != null && !recorded.contentEquals(committed)) {
            throw IllegalArgumentException("pinned source object bytes changed: $path")
        }
        if (!sourceFileBytes(source, path).contentEquals(committed)) {
            throw IllegalArgumentException("pinned source bytes differ: $path")
        }
        pinned[path] = committed
    }
    return CheckedSources(production, tests, pinned)
}

/** The identity `os.stat_result` fields Python compares: device, inode, mode, size, mtime, ctime. */
internal data class FileIdentity(
    val device: Long,
    val inode: Long,
    val mode: Int,
    val size: Long,
    val modifiedNanos: Long,
    val changedNanos: Long,
)

private fun identity(path: Path): FileIdentity {
    val basic = Files.readAttributes(path, BasicFileAttributes::class.java, LinkOption.NOFOLLOW_LINKS)
    val unix = Files.readAttributes(
        path,
        "unix:dev,ino,mode,ctime",
        LinkOption.NOFOLLOW_LINKS,
    )
    fun number(name: String): Long = (unix[name] as Number).toLong()
    val changed = unix["ctime"] as FileTime
    return FileIdentity(
        device = number("dev"),
        inode = number("ino"),
        mode = number("mode").toInt(),
        size = basic.size(),
        modifiedNanos = basic.lastModifiedTime().to(TimeUnit.NANOSECONDS),
        changedNanos = changed.to(TimeUnit.NANOSECONDS),
    )
}

/**
 * `verify.source_file_bytes`: read one pinned Java source without following a symlink in any path
 * component, and reject a read whose file, parent or root identity changed while it ran.
 */
fun sourceFileBytes(source: Path, name: String): ByteArray {
    val parts = name.split("/")
    val prefix = parts.take(3)
    if (parts.size < 4 || (prefix != listOf("src", "main", "java") &&
            prefix != listOf("src", "test", "java")) ||
        parts.any { it.isEmpty() || it == "." || it == ".." }
    ) {
        throw IllegalArgumentException("invalid pinned source path: $name")
    }
    try {
        val root = source.toAbsolutePath().normalize()
        val rootIdentity = identity(root)
        val tracked = mutableListOf<Pair<Path, FileIdentity>>()
        tracked.add(root to rootIdentity)
        var current = root
        for (part in parts.dropLast(1)) {
            current = current.resolve(part)
            if (!Files.isDirectory(current, LinkOption.NOFOLLOW_LINKS)) {
                throw IllegalArgumentException("pinned source path is missing or not a regular file: $name")
            }
            tracked.add(current to identity(current))
        }
        val file = current.resolve(parts.last())
        if (Files.isSymbolicLink(file)) {
            throw IllegalArgumentException("pinned source path is missing or not a regular file: $name")
        }
        if (!Files.isRegularFile(file, LinkOption.NOFOLLOW_LINKS)) {
            throw IllegalArgumentException("pinned source path is not a regular file: $name")
        }
        val before = identity(file)
        val bytes = Files.newInputStream(file, LinkOption.NOFOLLOW_LINKS).use { it.readAllBytes() }
        val after = identity(file)
        if (before != after) throw IllegalArgumentException("pinned source bytes changed during read: $name")
        for ((path, recorded) in tracked.drop(1)) {
            if (identity(path) != recorded) {
                throw IllegalArgumentException("pinned source path changed during read: $name")
            }
        }
        if (identity(root) != rootIdentity) {
            throw IllegalArgumentException("pinned source root changed during read: $name")
        }
        return bytes
    } catch (error: IOException) {
        throw IllegalArgumentException("pinned source path is missing or not a regular file: $name")
    }
}

/**
 * `verify.verify_source_inputs`: the tracked Java bytes and the published sources archive must be
 * the same bytes, and neither may change while the check runs.
 */
fun verifySourceInputs(
    seams: BaselineSeams,
    source: Path,
    sourcesJar: Path,
    commit: String,
    policy: BaselinePolicy = BaselinePolicy(),
    processEnvironment: Map<String, String> = System.getenv(),
): SourceProvenance {
    val checked = checkedJavaSources(seams, source, commit, null, processEnvironment)
    val production = checked.production.associateBy { it.removePrefix("src/main/java/") }
    return withTemporaryDirectory("dyn4k-sources-") { directory ->
        val snapshot = directory.resolve("sources.jar")
        copyFile(sourcesJar, snapshot)
        val archiveHash = digest(snapshot)
        if (commit == policy.commit && archiveHash != policy.sourcesSha256) {
            throw IllegalArgumentException(
                "source archive SHA-256 mismatch: expected ${policy.sourcesSha256}, got $archiveHash",
            )
        }
        val archiveNames: Set<String>
        seams.openZip(snapshot).use { archive ->
            archiveNames = archive.names().filter { it.endsWith(".java") }.toSet()
            if (archiveNames != production.keys) {
                throw IllegalArgumentException(
                    "source archive entries differ: " +
                        "missing=${pythonListRepr(sortedByCodePoint(production.keys - archiveNames))}, " +
                        "extra=${pythonListRepr(sortedByCodePoint(archiveNames - production.keys))}",
                )
            }
            for ((name, path) in production) {
                if (!archive.read(name).contentEquals(checked.pinned.getValue(path))) {
                    throw IllegalArgumentException("source archive bytes differ: $name")
                }
            }
        }
        if (digest(snapshot) != archiveHash) {
            throw IllegalArgumentException("source archive snapshot SHA-256 changed during verification")
        }
        checkedJavaSources(seams, source, commit, checked.pinned, processEnvironment)
        SourceProvenance(
            commit = commit,
            trackedProductionJavaFiles = production.size,
            sourceJarJavaFiles = archiveNames.size,
            sourceJarSha256 = archiveHash,
        )
    }
}

/**
 * `verify.checked_out_sources`: clone the pinned upstream repository into the cache unless it is
 * already there, then check the three input trees out at [commit].
 */
fun checkedOutSources(
    seams: BaselineSeams,
    cache: Path,
    policy: BaselinePolicy = BaselinePolicy(),
    processEnvironment: Map<String, String> = System.getenv(),
): Path {
    val source = cache.resolve("dyn4j-source")
    if (!exists(source.resolve(".git"))) {
        seams.requireRun(
            listOf(
                "git", "--no-replace-objects", "clone", "--filter=blob:none",
                "https://github.com/dyn4j/dyn4j.git", source.toString(),
            ),
            gitEnvironment(processEnvironment, networkAuth = true),
        )
    }
    val status = pinnedGit(
        seams,
        source,
        listOf(
            "status", "--porcelain=v1", "--untracked-files=all", "--ignored", "--",
            "src/main/java", "src/test/java", "src/test/resources",
        ),
        processEnvironment,
    ).stdoutText()
    if (status.isNotEmpty()) {
        throw BaselineExit("dirty or untracked source inputs: ${pyStrip(status)}")
    }
    pinnedGit(seams, source, listOf("fetch", "origin", policy.commit), processEnvironment)
    pinnedGit(seams, source, listOf("checkout", "--detach", policy.commit), processEnvironment)
    val actual = pyStrip(
        pinnedGit(seams, source, listOf("rev-parse", "HEAD"), processEnvironment).stdoutText(),
    )
    if (actual != policy.commit) throw BaselineExit("source revision mismatch: $actual")
    checkedJavaSources(seams, source, policy.commit, null, processEnvironment)
    return source.toAbsolutePath().normalize()
}

/** `verify.fetch`: download [url] into [dest] once, then enforce [expected] and non-emptiness. */
fun fetch(url: String, dest: Path, expected: String? = null) {
    dest.parent?.let { makeDirectories(it) }
    if (!exists(dest)) {
        val temp = dest.resolveSibling(dest.fileName.toString() + ".part")
        java.net.URI(url).toURL().openStream().use { input ->
            Files.copy(input, temp, StandardCopyOption.REPLACE_EXISTING)
        }
        Files.move(temp, dest, StandardCopyOption.REPLACE_EXISTING)
    }
    if (expected != null && digest(dest) != expected) {
        Files.deleteIfExists(dest)
        throw BaselineExit("checksum mismatch for ${dest.fileName}")
    }
    if (!isFile(dest) || Files.size(dest) == 0L) {
        throw BaselineExit("missing or empty artifact: $dest")
    }
}
