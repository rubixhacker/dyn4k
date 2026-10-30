package io.github.rubixhacker.harness.qualification

import io.github.rubixhacker.harness.contract.Sha256
import java.io.IOException
import java.nio.ByteBuffer
import java.nio.charset.StandardCharsets
import java.nio.file.DirectoryStream
import java.nio.file.Files
import java.nio.file.LinkOption
import java.nio.file.NoSuchFileException
import java.nio.file.OpenOption
import java.nio.file.Path
import java.nio.file.StandardOpenOption
import java.nio.file.attribute.BasicFileAttributes
import java.nio.file.attribute.FileTime
import java.nio.file.attribute.PosixFilePermissions
import java.security.MessageDigest
import java.util.concurrent.TimeUnit
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

/** An `OSError` of the reference: a file-system failure whose message keeps the `OSError` shape. */
class SafariFileError(message: String) : IOException(message)

/** `os.fstat` of one path: the `(st_dev, st_ino)` identity plus size and both timestamps. */
data class SafariFileIdentity(
    val key: Any?,
    val size: Long,
    val modifiedNanos: Long,
    val changedNanos: Long?,
)

/** One generated Karma configuration read through the no-follow path. */
class GeneratedConfig(val data: ByteArray, val identity: SafariFileIdentity)

/**
 * `tools/qualification/safari_reporter.py` file-system half: committed Git bytes, the no-follow
 * directory walk, the generated-config read, the staging run, and the forensic capture.
 *
 * The reference opens directories and files with `dir_fd`-relative `os.open` and `O_NOFOLLOW`.
 * The JVM has no descriptor-relative open, so every component is checked with
 * `LinkOption.NOFOLLOW_LINKS` and the directory identity is compared through
 * `BasicFileAttributes.fileKey()` — the `(st_dev, st_ino)` pair. A swap that happens between a
 * check and the operation it protects is not detectable; see the port report for the list.
 */
object SafariReporterHost {
    private const val MAX_FRAGMENT_BYTES = SafariReporter.MAX_FRAGMENT_BYTES
    private const val MAX_COMMITTED_OBJECT_BYTES = SafariReporter.MAX_COMMITTED_OBJECT_BYTES
    private const val STAGED_NAME = SafariReporter.STAGED_NAME

    /**
     * `safari_reporter.committed_bytes`: the exact committed bytes of one path, read from Git
     * objects and verified against their own object identity.
     */
    fun committedBytes(repository: Path, candidateSha: String, relative: Path): ByteArray {
        val parts = pathlibParts(relative)
        if (relative.isAbsolute || parts.isEmpty() ||
            parts.any { it.isEmpty() || it == "." || it == ".." } ||
            !Py.SHA40.matches(candidateSha)
        ) {
            throw IllegalArgumentException("invalid Safari candidate source path or commit")
        }
        val normalized = Path.of(parts.joinToString("/"))
        val base = listOf("git", "--no-replace-objects", "-C", repository.toString())
        val format = try {
            checkOutput(base + listOf("rev-parse", "--show-object-format"), null, 0)
        } catch (error: IOException) {
            throw IllegalArgumentException("Safari candidate object format is unavailable")
        }
        if (!format.decodeToString().trim().equals("sha1")) {
            throw IllegalArgumentException("Safari candidate requires SHA-1 Git objects")
        }

        val objects = HashMap<String, Pair<String, ByteArray>>()

        fun readObject(oid: String, expectedKind: String): ByteArray {
            objects[oid]?.let { (kind, raw) ->
                if (kind != expectedKind) {
                    throw IllegalArgumentException("Safari candidate object type differs: $oid")
                }
                return raw
            }
            val size: Long
            val response: ByteArray
            try {
                val sizeRaw = checkOutput(base + listOf("cat-file", "-s", oid), null, 15)
                    .decodeToString().trim()
                if (!Regex("0|[1-9][0-9]*").matches(sizeRaw)) {
                    throw IllegalArgumentException("Safari candidate object size is invalid: $oid")
                }
                size = sizeRaw.toLong()
                if (size > MAX_COMMITTED_OBJECT_BYTES) {
                    throw IllegalArgumentException("Safari candidate object is oversized: $oid")
                }
                response = checkOutput(
                    base + listOf("cat-file", "--batch"),
                    (oid + "\n").toByteArray(StandardCharsets.UTF_8),
                    15,
                )
            } catch (error: NumberFormatException) {
                throw IllegalArgumentException("Safari candidate object is oversized: $oid")
            } catch (error: IOException) {
                throw IllegalArgumentException("Safari candidate object is unavailable: $oid")
            }
            val header = "$oid $expectedKind $size\n".toByteArray(StandardCharsets.UTF_8)
            if (response.size < header.size ||
                !response.copyOfRange(0, header.size).contentEquals(header) ||
                response.size.toLong() != header.size.toLong() + size + 1 ||
                response[response.size - 1] != '\n'.code.toByte()
            ) {
                throw IllegalArgumentException("Safari candidate object type or size differs: $oid")
            }
            val raw = response.copyOfRange(header.size, response.size - 1)
            val digest = MessageDigest.getInstance("SHA-1")
            digest.update(expectedKind.toByteArray(StandardCharsets.UTF_8))
            digest.update(' '.code.toByte())
            digest.update(size.toString().toByteArray(StandardCharsets.UTF_8))
            digest.update(0.toByte())
            digest.update(raw)
            val identity = digest.digest().toHex()
            if (identity != oid) {
                throw IllegalArgumentException("Safari candidate object identity differs: $oid")
            }
            objects[oid] = expectedKind to raw
            return raw
        }

        fun treeEntries(oid: String): Map<String, Pair<ByteArray, String>> {
            val raw = readObject(oid, "tree")
            val entries = LinkedHashMap<String, Pair<ByteArray, String>>()
            var position = 0
            while (position < raw.size) {
                val separator = raw.indexOf(' '.code.toByte(), position)
                val end = if (separator < 0) -1 else raw.indexOf(0.toByte(), separator + 1)
                if (separator < 0 || separator < position || end < 0 || end + 21 > raw.size) {
                    throw IllegalArgumentException("Safari candidate tree entry is malformed: $oid")
                }
                val mode = raw.copyOfRange(position, separator)
                val name = raw.copyOfRange(separator + 1, end)
                val child = raw.copyOfRange(end + 1, end + 21).toHex()
                val key = String(name, StandardCharsets.ISO_8859_1)
                if (name.isEmpty() ||
                    name.contentEquals(".".toByteArray()) ||
                    name.contentEquals("..".toByteArray()) ||
                    name.contains('/'.code.toByte()) ||
                    key in entries
                ) {
                    throw IllegalArgumentException("Safari candidate tree has duplicate or invalid name: $oid")
                }
                entries[key] = mode to child
                position = end + 21
            }
            return entries
        }

        val commit = readObject(candidateSha, "commit")
        val newline = commit.indexOf('\n'.code.toByte())
        val firstLine = String(
            if (newline < 0) commit else commit.copyOfRange(0, newline),
            StandardCharsets.ISO_8859_1,
        )
        if (!Regex("tree [0-9a-f]{40}").matches(firstLine)) {
            throw IllegalArgumentException("Safari candidate commit tree is invalid")
        }
        var tree = firstLine.substring(5)
        for (part in parts.dropLast(1)) {
            val entry = treeEntries(tree)[String(part.toByteArray(StandardCharsets.UTF_8), StandardCharsets.ISO_8859_1)]
                ?: throw IllegalArgumentException("Safari candidate source tree path differs: $normalized")
            if (!entry.first.contentEquals("40000".toByteArray())) {
                throw IllegalArgumentException("Safari candidate source tree path differs: $normalized")
            }
            tree = entry.second
        }
        val last = parts.last()
        val entry = treeEntries(tree)[String(last.toByteArray(StandardCharsets.UTF_8), StandardCharsets.ISO_8859_1)]
            ?: throw IllegalArgumentException("Safari candidate source is not a regular file: $normalized")
        if (!entry.first.contentEquals("100644".toByteArray()) &&
            !entry.first.contentEquals("100755".toByteArray())
        ) {
            throw IllegalArgumentException("Safari candidate source is not a regular file: $normalized")
        }
        return readObject(entry.second, "blob")
    }

    /**
     * `safari_reporter.committed_fragment`: the working tree must hold exactly the committed
     * reporter source.
     */
    fun committedFragment(repository: Path, candidateSha: String): ByteArray {
        val path = repository.resolve(SafariReporter.SOURCE)
        if (Files.isSymbolicLink(path) || !Files.isRegularFile(path) ||
            Files.size(path) > MAX_FRAGMENT_BYTES
        ) {
            throw IllegalArgumentException("committed Safari reporter source is unsafe or oversized")
        }
        val current = Files.readAllBytes(path)
        val committed = committedBytes(repository, candidateSha, Path.of(SafariReporter.SOURCE))
        if (!current.contentEquals(committed)) {
            throw IllegalArgumentException("Safari reporter source differs from candidate")
        }
        return committed
    }

    /**
     * `safari_reporter.open_directory_no_follow`: the same directory, reached without following a
     * single symbolic link.
     */
    fun openDirectoryNoFollow(repository: Path, relative: Path): Path {
        val parts = pathlibParts(relative)
        if (relative.isAbsolute || parts.any { it.isEmpty() || it == "." || it == ".." }) {
            throw IllegalArgumentException("unsafe Safari path: $relative")
        }
        var current = requireDirectory(repository, repository)
        for (part in parts) {
            current = requireDirectory(current, current.resolve(part))
        }
        return current
    }

    private fun requireDirectory(anchor: Path, candidate: Path): Path {
        val attributes = try {
            Files.readAttributes(candidate, BasicFileAttributes::class.java, LinkOption.NOFOLLOW_LINKS)
        } catch (error: NoSuchFileException) {
            throw SafariFileError("[Errno 2] No such file or directory: '$candidate'")
        } catch (error: IOException) {
            throw SafariFileError("[Errno 5] Input/output error: '$candidate'")
        }
        if (attributes.isSymbolicLink) {
            throw SafariFileError("[Errno 40] Too many levels of symbolic links: '$candidate'")
        }
        if (!attributes.isDirectory) {
            throw SafariFileError("[Errno 20] Not a directory: '$candidate'")
        }
        return candidate
    }

    /**
     * `safari_reporter.same_directory`: the directory at that path is still [held].
     *
     * The reference compares `os.fstat` of an open descriptor with `os.fstat` of a freshly
     * reopened path. A JVM path has no descriptor, so [held] is the identity captured when the
     * directory was opened; the comparison is the same `(st_dev, st_ino)` pair.
     */
    fun sameDirectory(repository: Path, relative: Path, held: SafariFileIdentity): Boolean {
        val current = try {
            openDirectoryNoFollow(repository, relative)
        } catch (error: IOException) {
            return false
        }
        return try {
            val after = identityOf(current)
            held.key != null && held.key == after.key
        } catch (error: IOException) {
            false
        }
    }

    /**
     * `safari_reporter.read_generated_config`: the generated Karma configuration bytes, with the
     * file identity that must still hold when the bytes are published.
     */
    fun readGeneratedConfig(
        repository: Path,
        relative: Path,
        windows: Boolean = DefaultHostEnvironment.isWindows(),
    ): GeneratedConfig {
        if (windows) {
            throw UnsupportedOperationException(
                "Safari generated-config read is not supported on this host: the Windows " +
                    "locked-directory read is not ported",
            )
        }
        val parent = relative.parent ?: Path.of("")
        val directory = openDirectoryNoFollow(repository, parent)
        val path = directory.resolve(relative.fileName.toString())
        val before: SafariFileIdentity
        val data: ByteArray
        val attributes = try {
            Files.readAttributes(path, BasicFileAttributes::class.java, LinkOption.NOFOLLOW_LINKS)
        } catch (error: NoSuchFileException) {
            throw SafariFileError("[Errno 2] No such file or directory: '$path'")
        }
        if (attributes.isSymbolicLink) {
            throw SafariFileError("[Errno 40] Too many levels of symbolic links: '$path'")
        }
        if (!attributes.isRegularFile) {
            throw IllegalArgumentException("unsafe or oversized Safari generated config: $relative")
        }
        before = identityOf(path)
        if (before.size > MAX_FRAGMENT_BYTES) {
            throw IllegalArgumentException("unsafe or oversized Safari generated config: $relative")
        }
        data = readBounded(path, MAX_FRAGMENT_BYTES + 1)
        val after = identityOf(path)
        if (data.size.toLong() != before.size || before != after) {
            throw IllegalArgumentException("Safari generated config changed while reading: $relative")
        }
        val currentDirectory = openDirectoryNoFollow(repository, parent)
        val currentPath = currentDirectory.resolve(relative.fileName.toString())
        val currentAttributes = try {
            Files.readAttributes(currentPath, BasicFileAttributes::class.java, LinkOption.NOFOLLOW_LINKS)
        } catch (error: NoSuchFileException) {
            throw SafariFileError("[Errno 2] No such file or directory: '$currentPath'")
        }
        if (currentAttributes.isSymbolicLink) {
            throw SafariFileError("[Errno 40] Too many levels of symbolic links: '$currentPath'")
        }
        if (identityOf(currentPath) != before) {
            throw IllegalArgumentException("Safari generated config path identity changed: $relative")
        }
        return GeneratedConfig(data, before)
    }

    /**
     * `safari_reporter._forensic`: retain what a changed staged file held, outside the repository.
     *
     * A capture that cannot prove the file did not change records its error instead of bytes.
     */
    fun forensic(directory: Path, name: String, output: Path, relative: Path): JsonObject {
        val record = LinkedHashMap<String, JsonElement>()
        record["path"] = JsonPrimitive(relative.toString())
        record["original_size"] = JsonNull
        record["retained_size"] = JsonPrimitive(0)
        try {
            val path = directory.resolve(name)
            val attributes = try {
                Files.readAttributes(path, BasicFileAttributes::class.java, LinkOption.NOFOLLOW_LINKS)
            } catch (error: NoSuchFileException) {
                throw SafariFileError("[Errno 2] No such file or directory: '$path'")
            }
            if (attributes.isSymbolicLink) {
                throw SafariFileError("[Errno 40] Too many levels of symbolic links: '$path'")
            }
            if (!attributes.isRegularFile) throw IllegalArgumentException("nonregular staged reporter")
            val size = attributes.size()
            record["original_size"] = JsonPrimitive(size)
            val retained = minOf(size, MAX_FRAGMENT_BYTES.toLong()).toInt()
            val data = readBounded(path, retained)
            if (data.size != retained) {
                throw IllegalArgumentException("staged reporter changed during forensic capture")
            }
            val after = identityOf(path)
            if (attributes.fileKey() != after.key ||
                size != after.size ||
                attributes.lastModifiedTime().to(TimeUnit.NANOSECONDS) != after.modifiedNanos
            ) {
                throw IllegalArgumentException("staged reporter changed during forensic capture")
            }
            val destination = output.resolve("forensic/safari-reporter").resolve(relative)
            destination.parent?.let { Files.createDirectories(it) }
            Files.newOutputStream(destination, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE)
                .use { it.write(data) }
            record["archive_path"] = JsonPrimitive(posixRelative(output, destination))
            record["retained_size"] = JsonPrimitive(data.size)
            record["sha256"] = JsonPrimitive(Sha256.of(data))
            record["truncated"] = JsonPrimitive(size > MAX_FRAGMENT_BYTES)
        } catch (error: IOException) {
            record["error"] = JsonPrimitive(error.message ?: "")
        } catch (error: IllegalArgumentException) {
            record["error"] = JsonPrimitive(error.message ?: "")
        }
        return JsonObject(record)
    }

    /** The live stage result the caller sees between staging and cleanup. */
    class StagedSafari internal constructor(private val state: StageState) {
        val result: JsonObject get() = state.snapshot()
    }

    internal class StageState(val sourceSha256: String) {
        var status: String = "CLEAN"
        val projects = LinkedHashMap<String, String>()
        val forensic = mutableListOf<JsonObject>()
        val leftovers = LinkedHashMap<String, List<String>>()
        val leftoversTruncated = mutableListOf<String>()

        fun snapshot(): JsonObject = buildJsonObject {
            put("status", JsonPrimitive(status))
            put("source_sha256", JsonPrimitive(sourceSha256))
            put(
                "projects",
                buildJsonObject { projects.forEach { (key, value) -> put(key, JsonPrimitive(value)) } },
            )
            put("forensic", JsonArray(forensic))
            if (leftovers.isNotEmpty()) {
                put(
                    "leftovers",
                    buildJsonObject {
                        leftovers.forEach { (key, names) ->
                            put(key, JsonArray(names.map { JsonPrimitive(it) }))
                        }
                    },
                )
            }
            if (leftoversTruncated.isNotEmpty()) {
                put("leftovers_truncated", JsonArray(leftoversTruncated.map { JsonPrimitive(it) }))
            }
        }
    }

    private class Created(
        val relative: Path,
        val root: Path,
        val directory: Path,
        val rootIdentity: SafariFileIdentity,
        val directoryIdentity: SafariFileIdentity,
    )

    /**
     * `safari_reporter.stage`: place the committed reporter beside each generated Karma
     * configuration for the duration of [body], then remove it and record what was left.
     *
     * The returned result is the cleanup record: `CLEAN` only when every directory was removed
     * and no file was changed. A changed or unremovable file is captured under
     * `<output>/forensic/safari-reporter/` and reported.
     */
    fun stage(
        repositoryInput: Path,
        candidateSha: String,
        projects: List<String>,
        outputInput: Path,
        windows: Boolean = DefaultHostEnvironment.isWindows(),
        windowsDirectories: SafariLockedDirectoryFactory = SafariLockedDirectoryFactory { root, relative ->
            LockedDirectory(root, relative)
        },
        body: (StagedSafari) -> Unit,
    ): JsonObject {
        val repository = resolvePath(repositoryInput)
        val output = resolvePath(outputInput)
        if (output.startsWith(repository)) {
            throw IllegalArgumentException("Safari reporter forensic output must be external")
        }
        val content = committedFragment(repository, candidateSha)
        if (projects.isEmpty() || projects.any { canonicalPath(it) !in SafariReporter.PROJECTS } ||
            projects.map { canonicalPath(it) }.toSet().size != projects.size
        ) {
            throw IllegalArgumentException("invalid Safari reporter projects")
        }
        val state = StageState(Sha256.of(content))
        if (windows) {
            try {
                stageWindows(
                    repository,
                    projects,
                    content,
                    output,
                    state,
                    windowsDirectories,
                ) { body(StagedSafari(state)) }
            } catch (error: IOException) {
                if (state.status != "CLEAN") {
                    throw SafariStageFailure(state.snapshot(), stageFailureMessage(state))
                }
                throw error
            } catch (error: IllegalArgumentException) {
                if (state.status != "CLEAN") {
                    throw SafariStageFailure(state.snapshot(), stageFailureMessage(state))
                }
                throw error
            }
            return state.snapshot()
        }
        val created = mutableListOf<Created>()
        try {
            for (project in projects) {
                val relative = Path.of(canonicalPath(project))
                val root = openDirectoryNoFollow(repository, relative)
                Files.createDirectory(root.resolve("karma.config.d"))
                val directory = openDirectoryNoFollow(root, Path.of("karma.config.d"))
                created.add(
                    Created(relative, root, directory, identityOf(root), identityOf(directory)),
                )
                writeStagedFile(directory, content)
                state.projects[relative.toString()] = "STAGED"
            }
            body(StagedSafari(state))
        } finally {
            for (item in created.asReversed()) {
                cleanup(item, repository, content, output, state)
            }
        }
        return state.snapshot()
    }

    /**
     * `safari_reporter._stage_windows`: the locked-directory stage.
     *
     * Every directory component is held open, the staged file is removed through the held handle,
     * and the staging directory is unlinked while its handle is open. [directories] is the
     * `safari_windows_file.LockedDirectory` the reference imports; production supplies the
     * fail-closed kernel above, and the reference suite supplies the fake it installs over
     * `ctypes.WinDLL`.
     */
    internal fun stageWindows(
        repository: Path,
        projects: List<String>,
        content: ByteArray,
        output: Path,
        state: StageState,
        directories: SafariLockedDirectoryFactory,
        body: () -> Unit,
    ) {
        val created = mutableListOf<WindowsCreated>()
        try {
            for (project in projects) {
                val relative = Path.of(canonicalPath(project))
                val root = directories.create(repository, relative)
                try {
                    Files.createDirectory(root.path.resolve("karma.config.d"))
                } catch (error: Throwable) {
                    root.close()
                    throw error
                }
                created.add(WindowsCreated(relative, root, null))
                val directory = try {
                    root.child("karma.config.d", removable = true)
                } catch (error: Throwable) {
                    throw error
                }
                created[created.size - 1] = WindowsCreated(relative, root, directory)
                Files.newOutputStream(
                    root.path.resolve("karma.config.d").resolve(SafariReporter.STAGED_NAME),
                    StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.WRITE,
                ).use { it.write(content) }
                state.projects[relative.toString()] = "STAGED"
            }
            body()
        } finally {
            for (item in created.asReversed()) {
                cleanupWindows(item, content, output, state)
            }
        }
    }

    private class WindowsCreated(
        val relative: Path,
        val root: SafariLockedDirectory,
        val directory: SafariLockedDirectory?,
    )

    private fun cleanupWindows(
        item: WindowsCreated,
        content: ByteArray,
        output: Path,
        state: StageState,
    ) {
        val key = item.relative.toString()
        val directory = item.directory
        if (directory == null) {
            state.status = "CHANGED"
            state.projects[key] = "LEFTOVER"
            state.forensic.add(
                record(
                    item.relative.resolve("karma.config.d").toString(),
                    "staging directory handle unavailable",
                ),
            )
            item.root.close()
            return
        }
        try {
            val unchanged = try {
                val descriptor = directory.openFile(SafariReporter.STAGED_NAME)
                try {
                    val observed = descriptor.stat()
                    observed.size == content.size.toLong() &&
                        descriptor.read(content.size + 1).contentEquals(content)
                } finally {
                    descriptor.close()
                }
            } catch (error: IOException) {
                false
            } catch (error: IllegalArgumentException) {
                false
            }
            if (!unchanged) {
                state.status = "CHANGED"
                state.projects[key] = "CHANGED"
                state.forensic.add(
                    forensicWindows(
                        directory,
                        SafariReporter.STAGED_NAME,
                        output,
                        item.relative.resolve(SafariReporter.STAGED_NAME),
                    ),
                )
            } else {
                state.projects[key] = "CLEAN"
            }
            val staged = directory.path.resolve(SafariReporter.STAGED_NAME)
            try {
                Files.deleteIfExists(staged)
            } catch (error: IOException) {
                state.status = "CHANGED"
                state.projects[key] = "LEFTOVER"
                state.forensic.add(record(item.relative.resolve(SafariReporter.STAGED_NAME).toString(), error.message ?: ""))
            }
            val leftovers = try {
                scanWindows(directory.path)
            } catch (error: IOException) {
                state.status = "CHANGED"
                state.projects[key] = "LEFTOVER"
                state.forensic.add(record(item.relative.resolve("karma.config.d").toString(), error.message ?: ""))
                emptyList()
            }
            if (leftovers.isNotEmpty()) {
                state.status = "CHANGED"
                state.projects[key] = "LEFTOVER"
                state.leftovers[key] = leftovers.take(16)
                if (leftovers.size > 16) state.leftoversTruncated.add(key)
                for (name in leftovers.take(16)) {
                    state.forensic.add(
                        forensicWindows(directory, name, output, item.relative.resolve(name)),
                    )
                }
            }
        } finally {
            if (state.leftovers[key].isNullOrEmpty()) {
                try {
                    directory.removeEmpty()
                } catch (error: IOException) {
                    state.status = "CHANGED"
                    state.projects[key] = "LEFTOVER"
                    state.forensic.add(
                        record(
                            item.relative.resolve("karma.config.d").toString(),
                            (error.message ?: "").take(512),
                        ),
                    )
                } catch (error: IllegalArgumentException) {
                    state.status = "CHANGED"
                    state.projects[key] = "LEFTOVER"
                    state.forensic.add(
                        record(
                            item.relative.resolve("karma.config.d").toString(),
                            (error.message ?: "").take(512),
                        ),
                    )
                }
            }
            directory.close()
            val residue = try {
                Files.readAttributes(
                    item.root.path.resolve("karma.config.d"),
                    BasicFileAttributes::class.java,
                    LinkOption.NOFOLLOW_LINKS,
                )
                true
            } catch (error: NoSuchFileException) {
                false
            } catch (error: IOException) {
                true
            }
            if (residue) {
                state.status = "CHANGED"
                state.projects[key] = "LEFTOVER"
                state.forensic.add(
                    record(
                        item.relative.resolve("karma.config.d").toString(),
                        "staging directory remains after cleanup",
                    ),
                )
            }
            item.root.close()
        }
    }

    /** `safari_reporter._forensic_windows`: what a changed staged file held, outside the checkout. */
    private fun forensicWindows(
        directory: SafariLockedDirectory,
        name: String,
        output: Path,
        relative: Path,
    ): JsonObject {
        val record = LinkedHashMap<String, JsonElement>()
        record["path"] = JsonPrimitive(relative.toString())
        record["original_size"] = JsonNull
        record["retained_size"] = JsonPrimitive(0)
        try {
            val descriptor = directory.openFile(name)
            val before: SafariHandleStat
            val data: ByteArray
            try {
                before = descriptor.stat()
                record["original_size"] = JsonPrimitive(before.size)
                val retained = minOf(before.size, MAX_FRAGMENT_BYTES.toLong()).toInt()
                data = descriptor.read(retained)
                val after = descriptor.stat()
                if (data.size != retained || before.identity() != after.identity()) {
                    throw IllegalArgumentException("staged reporter changed during forensic capture")
                }
            } finally {
                descriptor.close()
            }
            val destination = output.resolve("forensic/safari-reporter").resolve(relative)
            destination.parent?.let { Files.createDirectories(it) }
            Files.newOutputStream(
                destination,
                StandardOpenOption.CREATE_NEW,
                StandardOpenOption.WRITE,
            ).use { it.write(data) }
            record["archive_path"] = JsonPrimitive(posixRelative(output, destination))
            record["retained_size"] = JsonPrimitive(data.size)
            record["sha256"] = JsonPrimitive(Sha256.of(data))
            record["truncated"] = JsonPrimitive(before.size > MAX_FRAGMENT_BYTES)
        } catch (error: IOException) {
            record["error"] = JsonPrimitive(error.message ?: "")
        } catch (error: IllegalArgumentException) {
            record["error"] = JsonPrimitive(error.message ?: "")
        }
        return JsonObject(record)
    }

    /** `itertools.islice(os.scandir(directory.path), 17)`, sorted by name. */
    private fun scanWindows(directory: Path): List<String> {
        val names = mutableListOf<String>()
        val stream = try {
            Files.newDirectoryStream(directory)
        } catch (error: NoSuchFileException) {
            throw SafariFileError("[Errno 2] No such file or directory: '$directory'")
        }
        stream.use {
            for (entry in it) {
                if (names.size >= 17) break
                names.add(entry.fileName.toString())
            }
        }
        return names.sorted()
    }

    /** `StageFailure.__init__`: name the first recorded residue path. */
    private fun stageFailureMessage(state: StageState): String {
        val failed = state.forensic.firstOrNull { it.containsKey("error") }
            ?.let { Py.str(it["path"]) ?: "" } ?: "karma.config.d"
        return "Safari reporter staging residue: " + failed.take(256)
    }

    private fun cleanup(
        item: Created,
        repository: Path,
        content: ByteArray,
        output: Path,
        state: StageState,
    ) {
        val projectKey = item.relative.toString()
        val stageRelative = item.relative.resolve("karma.config.d")
        val rootSame = sameDirectory(repository, item.relative, item.rootIdentity)
        val directorySame = try {
            val linked = identityOf(item.root.resolve("karma.config.d"))
            linked.key != null && linked.key == item.directoryIdentity.key
        } catch (error: IOException) {
            false
        }
        // The reference keeps a descriptor on the staging directory, so a rename of that
        // directory does not redirect its reads. A path can be redirected, so the directory with
        // the held identity is located by scanning the parent; when it cannot be found, every read
        // through the held descriptor would fail with ENOENT, and the path is not touched at all.
        val heldDirectory = if (directorySame) {
            item.directory
        } else {
            locateHeld(item.directory.parent ?: item.root, item.directoryIdentity)
        }
        if (!rootSame || !directorySame) {
            state.status = "CHANGED"
            state.projects[projectKey] = "DIRECTORY_CHANGED"
            state.forensic.add(record(stageRelative.toString(), "staging ancestor identity changed"))
        }
        val unchanged = heldDirectory != null && try {
            stagedUnchanged(heldDirectory, content)
        } catch (error: IOException) {
            false
        }
        if (!unchanged) {
            state.status = "CHANGED"
            if (rootSame && directorySame) state.projects[projectKey] = "CHANGED"
            state.forensic.add(
                if (heldDirectory != null) {
                    forensic(heldDirectory, STAGED_NAME, output, item.relative.resolve(STAGED_NAME))
                } else {
                    record(
                        item.relative.resolve(STAGED_NAME).toString(),
                        "[Errno 2] No such file or directory: '$STAGED_NAME'",
                    )
                },
            )
        } else if (rootSame && directorySame) {
            state.projects[projectKey] = "CLEAN"
        }
        if (heldDirectory != null) {
            try {
                unlinkNoFollow(heldDirectory.resolve(STAGED_NAME))
            } catch (error: IOException) {
                state.status = "CHANGED"
                state.projects[projectKey] = "LEFTOVER"
                state.forensic.add(
                    record(item.relative.resolve(STAGED_NAME).toString(), error.message ?: ""),
                )
            }
        }
        // The reference scans the held descriptor. When the directory was unlinked, the descriptor
        // still names the empty inode the cleanup itself emptied, so the scan is empty and the path
        // is never followed; a JVM path cannot read an unlinked directory, so its scan is empty by
        // construction rather than by listing.
        val leftovers = if (heldDirectory == null) {
            emptyList()
        } else {
            try {
                scanDirectory(heldDirectory)
            } catch (error: IOException) {
                state.status = "CHANGED"
                state.projects[projectKey] = "LEFTOVER"
                state.forensic.add(record(stageRelative.toString(), error.message ?: ""))
                emptyList()
            }
        }
        if (leftovers.isNotEmpty()) {
            state.status = "CHANGED"
            if (rootSame && directorySame) state.projects[projectKey] = "LEFTOVER"
            state.leftovers[projectKey] = leftovers.take(16)
            if (leftovers.size > 16) state.leftoversTruncated.add(projectKey)
            for (name in leftovers.take(16)) {
                if (heldDirectory == null) continue
                state.forensic.add(
                    forensic(heldDirectory, name, output, item.relative.resolve(name)),
                )
            }
        } else if (directorySame) {
            try {
                rmdirNoFollow(item.root.resolve("karma.config.d"))
            } catch (error: IOException) {
                state.status = "CHANGED"
                state.projects[projectKey] = "LEFTOVER"
                state.forensic.add(record(stageRelative.toString(), error.message ?: ""))
            }
        }
    }

    /** The directory under [parent] whose identity is [held], if a rename left it there. */
    private fun locateHeld(parent: Path, held: SafariFileIdentity): Path? {
        if (held.key == null) return null
        val stream = try {
            Files.newDirectoryStream(parent)
        } catch (error: IOException) {
            return null
        }
        stream.use {
            for (entry in it) {
                val candidate = try {
                    identityOf(entry)
                } catch (error: IOException) {
                    continue
                }
                if (candidate.key == held.key) return entry
            }
        }
        return null
    }

    private fun record(path: String, error: String): JsonObject = buildJsonObject {
        put("path", JsonPrimitive(path))
        put("error", JsonPrimitive(error))
    }

    private fun writeStagedFile(directory: Path, content: ByteArray) {
        val path = directory.resolve(STAGED_NAME)
        val options = linkedSetOf<OpenOption>(
            StandardOpenOption.CREATE_NEW,
            StandardOpenOption.WRITE,
            LinkOption.NOFOLLOW_LINKS,
        )
        val attributes = if (path.fileSystem.supportedFileAttributeViews().contains("posix")) {
            arrayOf(PosixFilePermissions.asFileAttribute(PosixFilePermissions.fromString("rw-------")))
        } else {
            emptyArray()
        }
        Files.newByteChannel(path, options, *attributes).use { channel ->
            var offset = 0
            while (offset < content.size) {
                offset += channel.write(ByteBuffer.wrap(content, offset, content.size - offset))
            }
        }
    }

    private fun stagedUnchanged(directory: Path, content: ByteArray): Boolean {
        val path = directory.resolve(STAGED_NAME)
        val attributes = Files.readAttributes(path, BasicFileAttributes::class.java, LinkOption.NOFOLLOW_LINKS)
        if (attributes.isSymbolicLink || !attributes.isRegularFile) return false
        if (attributes.size() != content.size.toLong()) return false
        return readBounded(path, content.size + 1).contentEquals(content)
    }

    private fun unlinkNoFollow(path: Path) {
        val attributes = try {
            Files.readAttributes(path, BasicFileAttributes::class.java, LinkOption.NOFOLLOW_LINKS)
        } catch (error: NoSuchFileException) {
            return
        }
        if (attributes.isDirectory && !attributes.isSymbolicLink) {
            throw SafariFileError("[Errno 21] Is a directory: '$path'")
        }
        Files.delete(path)
    }

    private fun rmdirNoFollow(path: Path) {
        val attributes = try {
            Files.readAttributes(path, BasicFileAttributes::class.java, LinkOption.NOFOLLOW_LINKS)
        } catch (error: NoSuchFileException) {
            throw SafariFileError("[Errno 2] No such file or directory: '$path'")
        }
        if (attributes.isSymbolicLink || !attributes.isDirectory) {
            throw SafariFileError("[Errno 20] Not a directory: '$path'")
        }
        Files.delete(path)
    }

    /**
     * `os.scandir` of the staging directory: at most 17 raw entries, sorted by name.
     *
     * The reference sorts what the file system returned for the first 17 entries, so the order of
     * a directory with more than 17 leftovers is a file-system property in both ports.
     */
    private fun scanDirectory(directory: Path): List<String> {
        val names = mutableListOf<String>()
        val scan = directory.resolve(".")
        val stream: DirectoryStream<Path> = try {
            Files.newDirectoryStream(scan)
        } catch (error: NoSuchFileException) {
            throw SafariFileError("[Errno 2] No such file or directory: '$scan'")
        }
        stream.use {
            for (entry in it) {
                if (names.size >= 17) break
                names.add(entry.fileName.toString())
            }
        }
        return names.sorted()
    }

    /** `os.fstat` of one path: the identity a later check compares against. */
    fun identityOf(path: Path): SafariFileIdentity {
        val attributes = Files.readAttributes(
            path,
            BasicFileAttributes::class.java,
            LinkOption.NOFOLLOW_LINKS,
        )
        val changed = try {
            (Files.getAttribute(path, "unix:ctime", LinkOption.NOFOLLOW_LINKS) as? FileTime)
                ?.to(TimeUnit.NANOSECONDS)
        } catch (error: Exception) {
            null
        }
        return SafariFileIdentity(
            attributes.fileKey(),
            attributes.size(),
            attributes.lastModifiedTime().to(TimeUnit.NANOSECONDS),
            changed,
        )
    }

    /** `os.read(fd, limit)`: at most [limit] bytes, fewer only at end of file. */
    private fun readBounded(path: Path, limit: Int): ByteArray {
        if (limit <= 0) return ByteArray(0)
        val options = linkedSetOf<OpenOption>(StandardOpenOption.READ, LinkOption.NOFOLLOW_LINKS)
        Files.newByteChannel(path, options).use { channel ->
            val buffer = ByteBuffer.allocate(limit)
            while (buffer.hasRemaining()) {
                if (channel.read(buffer) < 0) break
            }
            buffer.flip()
            val out = ByteArray(buffer.remaining())
            buffer.get(out)
            return out
        }
    }

    /** `subprocess.check_output` with the stderr pipe discarded and an optional timeout. */
    private fun checkOutput(arguments: List<String>, input: ByteArray?, timeoutSeconds: Long): ByteArray {
        val process = ProcessBuilder(arguments)
            .redirectError(ProcessBuilder.Redirect.DISCARD)
            .start()
        if (input != null) {
            process.outputStream.use { it.write(input) }
        } else {
            process.outputStream.close()
        }
        val stdout = process.inputStream.use { it.readBytes() }
        val finished = if (timeoutSeconds > 0) {
            process.waitFor(timeoutSeconds, TimeUnit.SECONDS)
        } else {
            process.waitFor()
            true
        }
        if (!finished) {
            process.destroyForcibly()
            throw IOException("command timed out")
        }
        if (process.exitValue() != 0) throw IOException("command exited ${process.exitValue()}")
        return stdout
    }

    /** `Path.resolve()`, which does not require the leaf to exist. */
    internal fun resolvePath(path: Path): Path {
        val absolute = path.toAbsolutePath().normalize()
        if (Files.exists(absolute)) return absolute.toRealPath()
        val missing = ArrayDeque<Path>()
        var existing: Path? = absolute
        while (existing != null && !Files.exists(existing)) {
            existing.fileName?.let { missing.addFirst(it) }
            existing = existing.parent
        }
        var resolved = existing?.toRealPath() ?: return absolute
        for (part in missing) resolved = resolved.resolve(part)
        return resolved
    }

    /**
     * `PurePath.parts`: single dots and empty segments are dropped, `..` is kept, and the
     * platform separators are split. `pathlib` never removes `..` from a path, so neither do we.
     */
    private fun pathlibParts(path: Path): List<String> {
        val text = path.toString()
        if (text.isEmpty()) return emptyList()
        return text.split('/').filter { it.isNotEmpty() && it != "." }
    }

    /** The `pathlib` spelling of a project, matching [SafariReporter.canonicalProject]. */
    private fun canonicalPath(project: String): String =
        SafariReporter.canonicalProject(project).let { text ->
            if (text.isEmpty()) text else Path.of(text).toString()
        }

    private fun posixRelative(root: Path, path: Path): String =
        root.relativize(path).toString().replace('\\', '/')

    private fun ByteArray.indexOf(target: Byte, from: Int): Int {
        var index = from
        while (index < size) {
            if (this[index] == target) return index
            index++
        }
        return -1
    }

    private fun ByteArray.contains(target: Byte): Boolean = indexOf(target, 0) >= 0

    private fun ByteArray.toHex(): String {
        val digits = "0123456789abcdef"
        val out = StringBuilder(size * 2)
        for (byte in this) {
            val value = byte.toInt() and 0xFF
            out.append(digits[value shr 4]).append(digits[value and 0x0F])
        }
        return out.toString()
    }
}
