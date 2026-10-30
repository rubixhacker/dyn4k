package io.github.rubixhacker.harness.qualification

import io.github.rubixhacker.harness.contract.Sha256
import java.io.IOException
import java.nio.file.Files
import java.nio.file.LinkOption
import java.nio.file.Path
import java.nio.file.StandardOpenOption
import java.nio.file.attribute.BasicFileAttributes
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/** Thrown when a raw archive cannot be scanned as an immutable tree. */
class ArchiveScanError(message: String) : Exception(message)

/** One scanned archive file. */
data class ArchiveFile(val sha256: String, val mtimeNs: Long)

/**
 * `_archive_identity`: the recorded identity of one archive path.
 *
 * `attributes` is the Windows reparse tag, which `java.nio.file` exposes only as
 * `isSymbolicLink`/`isOther`; on this port it is always absent, and a symbolic link or any other
 * reparse point is rejected outright, so the comparisons that carry it stay exact.
 */
data class ArchiveIdentity(
    val dev: Long,
    val ino: Long,
    val mode: Long,
    val nlink: Long,
    val size: Long,
    val mtimeNs: Long,
    val ctimeNs: Long,
    val attributes: Long? = null,
)

/** `_archive_stable_identity`: identity without the change time. */
fun ArchiveIdentity.stable(): List<Long?> =
    listOf(dev, ino, mode, nlink, size, mtimeNs, attributes)

/** `_archive_ancestor_identity`: only the parts an ancestor check compares. */
fun ArchiveIdentity.ancestor(): List<Long?> = listOf(dev, ino, mode, attributes)

/** `_archive_handle_identity`: identity without the change time or the modification time. */
fun ArchiveIdentity.handle(): List<Long?> = listOf(dev, ino, mode, nlink, size, mtimeNs, attributes)

/** `_archive_ancestor_handle_identity`: the directory handle identity an ancestor check compares. */
fun ArchiveIdentity.ancestorHandle(): List<Long?> = listOf(dev, ino, mode, attributes)

/**
 * A validated directory of the archive walk.
 *
 * The reference keeps the `O_DIRECTORY | O_NOFOLLOW` descriptor it opened and lists through it,
 * so nothing can be swapped between the open and the listing. `java.nio.file` has no directory
 * descriptor, so this handle carries the identity it validated plus the path it lists, and every
 * listing re-checks that identity first.
 */
class ArchiveDirectory internal constructor(val path: Path, val identity: ArchiveIdentity) {
    /** `os.scandir(directory)`: the member names, unsorted. */
    fun members(): List<String> =
        Files.newDirectoryStream(path).use { stream -> stream.map { it.fileName.toString() } }
}

/**
 * `independent_gates._archive_scan`, `_archive_identity`, `_archive_directory`,
 * `_file_path_name`, and `archive_digest`.
 *
 * The reference opens every directory relative to its parent with `O_NOFOLLOW`, and compares the
 * opened handle's identity with the identity it recorded earlier, so a tree that changes while it
 * is scanned is rejected. The JVM cannot pass a directory descriptor to an open, so this port
 * records the identity of every path, validates the identity of every path component of every
 * directory it walks, reads each file twice around two identity checks, and re-walks every
 * directory at the end. A swap that restores an identical identity between those checks is
 * therefore not detected here, which is narrower than the reference.
 */
object ArchiveScan {
    /** `independent_gates.archive_digest`: the canonical digest of the raw archive contents. */
    fun digest(root: Path): String {
        val files = scan(root)
        if ("receipt.json" !in files) throw ArchiveScanError("raw receipt is absent")
        val records = files.keys.sortedWith(CanonicalText::compare).map { name ->
            JsonObject(
                linkedMapOf(
                    "path" to JsonPrimitive(name),
                    "sha256" to JsonPrimitive(files.getValue(name).sha256),
                    "mtime_ns" to JsonPrimitive(files.getValue(name).mtimeNs),
                ),
            )
        }
        return Sha256.ofCanonical(JsonArray(records))
    }

    /** Returns the SHA-256 and modification time of every regular file of the archive. */
    fun scan(root: Path): Map<String, ArchiveFile> {
        if (!root.isAbsolute || ".." in root.toString().split('/') || !Files.isDirectory(root)) {
            throw ArchiveScanError("archive path is absent or relative: $root")
        }
        val ancestors = LinkedHashMap<Path, ArchiveIdentity>()
        var current: Path? = root
        while (current != null) {
            ancestors[current] = identity(current)
            current = current.parent
        }
        for ((path, value) in ancestors) {
            if (!Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS)) {
                throw ArchiveScanError("archive ancestor is not a directory: $path")
            }
            if (!isDirectoryState(value)) {
                throw ArchiveScanError("archive ancestor is not a directory: $path")
            }
        }

        val identities = LinkedHashMap<Path, ArchiveIdentity>()
        identities[root] = ancestors.getValue(root)
        val members = LinkedHashMap<Path, List<String>>()
        val files = LinkedHashMap<String, ArchiveFile>()
        val seen = mutableSetOf<String>()

        fun visit(directory: ArchiveDirectory) {
            val entries = directory.members()
            members[directory.path] = entries.sortedWith(CanonicalText::compare)
            for (name in entries) {
                val path = directory.path.resolve(name)
                val relative = root.relativize(path).toString()
                filePathName(relative)
                if (!seen.add(relative)) throw ArchiveScanError("duplicate archive path: $relative")
                val before = identity(path)
                identities[path] = before
                if (isDirectoryState(before)) {
                    val child = archiveDirectory(path)
                    if (child.identity.handle() != before.stable()) {
                        throw ArchiveScanError("archive directory identity changed: $relative")
                    }
                    visit(child)
                    continue
                }
                val opened = identity(path)
                if (opened.handle() != before.stable()) {
                    throw ArchiveScanError("archive file identity changed: $relative")
                }
                val first = readAndHash(path, relative)
                val second = readAndHash(path, relative)
                if (first != second) {
                    throw ArchiveScanError("archive file changed during read: $relative")
                }
                val closed = identity(path)
                if (closed.handle() != opened.handle() || closed.ctimeNs != opened.ctimeNs) {
                    throw ArchiveScanError("archive file changed during read: $relative")
                }
                if (identity(path) != before) {
                    throw ArchiveScanError("archive file identity changed: $relative")
                }
                files[relative] = ArchiveFile(first, before.mtimeNs)
            }
        }

        val handle = archiveDirectory(root, ancestors)
        if (handle.identity.handle() != ancestors.getValue(root).stable()) {
            throw ArchiveScanError("archive root identity changed during scan: $root")
        }
        visit(handle)
        for ((path, before) in identities) {
            if (identity(path) != before) {
                throw ArchiveScanError("archive entry changed during scan: $path")
            }
        }
        val checkedAncestors = LinkedHashMap(ancestors)
        checkedAncestors.putAll(identities)
        for ((directory, listed) in members) {
            val checked = archiveDirectory(directory, checkedAncestors)
            val current = checked.members().sortedWith(CanonicalText::compare)
            if (current != listed || identity(directory) != identities.getValue(directory)) {
                throw ArchiveScanError("archive entry changed during scan: $directory")
            }
        }
        for ((path, before) in ancestors) {
            val now = identity(path)
            val expected = if (path == root) before.stable() else before.ancestor()
            val actual = if (path == root) now.stable() else now.ancestor()
            if (actual != expected) throw ArchiveScanError("archive ancestor changed during scan: $path")
        }
        return files
    }

    /**
     * `_archive_directory`: validate the identity of every path component, then hand back the
     * directory.
     *
     * The reference opens each component with `dir_fd` and `O_NOFOLLOW` and validates the opened
     * handle; this port reads the same components' attributes and validates the same projections.
     * A component that changes between the attribute read and the listing is caught by the
     * caller's re-check, which the reference gets for free from the descriptor.
     */
    fun archiveDirectory(
        path: Path,
        ancestors: Map<Path, ArchiveIdentity>? = null,
    ): ArchiveDirectory {
        if (!path.isAbsolute) {
            throw ArchiveScanError("archive directory safe open is unavailable")
        }
        val parts = ArrayList<Path>()
        var current: Path? = path
        while (current != null) {
            parts.add(current)
            current = current.parent
        }
        parts.reverse()
        for (component in parts) {
            val opened = identity(component)
            if (ancestors != null) {
                val expected = ancestors[component]
                    ?: throw ArchiveScanError("archive ancestor changed during scan: $component")
                val valid = if (component == path) {
                    opened.handle() == expected.stable()
                } else {
                    opened.ancestorHandle() == expected.ancestor()
                }
                if (!valid) {
                    throw ArchiveScanError("archive ancestor changed during scan: $component")
                }
            }
        }
        return ArchiveDirectory(path, identity(path))
    }

    /** `_file_path_name`: the archive member name contract, as a scan rejection. */
    fun filePathName(relative: String) {
        try {
            IndependentGates.filePathName(relative)
        } catch (error: IllegalArgumentException) {
            throw ArchiveScanError(error.message ?: "unsafe archive path: $relative")
        }
    }

    /** `independent_gates._archive_identity`, with the checks the reference applies. */
    fun identity(path: Path): ArchiveIdentity {
        if (Files.isSymbolicLink(path)) {
            throw ArchiveScanError("symbolic or reparse archive path: $path")
        }
        val basic = try {
            Files.readAttributes(path, BasicFileAttributes::class.java, LinkOption.NOFOLLOW_LINKS)
        } catch (error: IOException) {
            throw ArchiveScanError("archive file identity is unavailable: $path")
        }
        val dev = unixAttribute(path, "dev")
        val ino = unixAttribute(path, "ino")
        val mode = unixAttribute(path, "mode")
        val nlink = unixAttribute(path, "nlink")
        val ctime = unixAttribute(path, "ctime")
        if (dev == null || ino == null || ino <= 0L || mode == null || nlink == null || ctime == null) {
            throw ArchiveScanError("archive file identity is unavailable: $path")
        }
        val regular = basic.isRegularFile
        if (regular && nlink != 1L) throw ArchiveScanError("hardlinked archive file: $path")
        if (!regular && !basic.isDirectory) throw ArchiveScanError("nonregular archive path: $path")
        return ArchiveIdentity(
            dev = dev,
            ino = ino,
            mode = mode,
            nlink = nlink,
            size = basic.size(),
            mtimeNs = basic.lastModifiedTime().to(java.util.concurrent.TimeUnit.NANOSECONDS),
            ctimeNs = ctime,
        )
    }

    /** `stat.S_ISDIR(state.st_mode)`. */
    private fun isDirectoryState(value: ArchiveIdentity): Boolean = value.mode and 0xF000L == 0x4000L

    private fun unixAttribute(path: Path, name: String): Long? = try {
        when (val value = Files.getAttribute(path, "unix:$name", LinkOption.NOFOLLOW_LINKS)) {
            is Number -> value.toLong()
            is java.nio.file.attribute.FileTime -> value.to(java.util.concurrent.TimeUnit.NANOSECONDS)
            else -> null
        }
    } catch (_: IOException) {
        null
    } catch (_: UnsupportedOperationException) {
        null
    }

    private fun readAndHash(path: Path, relative: String): String {
        val digest = java.security.MessageDigest.getInstance("SHA-256")
        try {
            Files.newByteChannel(path, StandardOpenOption.READ, LinkOption.NOFOLLOW_LINKS)
                .use { channel ->
                    val block = java.nio.ByteBuffer.allocate(1024 * 1024)
                    while (true) {
                        block.clear()
                        val read = channel.read(block)
                        if (read < 0) break
                        digest.update(block.array(), 0, read)
                    }
                }
        } catch (error: IOException) {
            throw ArchiveScanError("archive file is unreadable: $relative")
        } catch (error: UnsupportedOperationException) {
            throw ArchiveScanError("archive file is unreadable: $relative")
        }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }
}
