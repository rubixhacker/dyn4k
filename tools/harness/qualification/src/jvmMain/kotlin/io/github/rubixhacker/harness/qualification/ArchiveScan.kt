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
 * `independent_gates._archive_scan`, `_file_path_name`, and `archive_digest`.
 *
 * The reference opens directories relative to their parent with `O_NOFOLLOW` and compares the
 * opened handle's identity with the identity it recorded earlier, so a tree that changes while it
 * is scanned is rejected. The JVM cannot pass a directory descriptor to an open, so this port
 * records the identity of every path before it is read, re-reads it afterwards, reads each file
 * twice, and re-lists every directory at the end. A swap that restores an identical inode between
 * those checks is therefore not detected here, which is narrower than the reference.
 */
object ArchiveScan {
    private val UNSAFE_COMPONENTS = setOf("", ".", "..")

    private data class Identity(
        val dev: Long,
        val ino: Long,
        val mode: Long,
        val nlink: Long,
        val size: Long,
        val mtimeNs: Long,
        val ctimeNs: Long,
    ) {
        /** `_archive_stable_identity`: identity without the change time. */
        fun stable(): List<Long> = listOf(dev, ino, mode, nlink, size, mtimeNs)

        /** `_archive_ancestor_identity`: only the parts an ancestor check compares. */
        fun ancestor(): List<Long> = listOf(dev, ino, mode)
    }

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
        val ancestors = LinkedHashMap<Path, Identity>()
        var current: Path? = root
        while (current != null) {
            val identity = identity(current)
            ancestors[current] = identity
            current = current.parent
        }
        for ((path, _) in ancestors) {
            if (!Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS)) {
                throw ArchiveScanError("archive ancestor is not a directory: $path")
            }
        }

        val identities = LinkedHashMap<Path, Identity>()
        identities[root] = ancestors.getValue(root)
        val members = LinkedHashMap<Path, List<String>>()
        val files = LinkedHashMap<String, ArchiveFile>()
        val seen = mutableSetOf<String>()

        fun visit(directory: Path) {
            val entries = Files.newDirectoryStream(directory).use { stream -> stream.toList() }
            members[directory] = entries.map { it.fileName.toString() }.sortedWith(CanonicalText::compare)
            for (entry in entries) {
                val path = directory.resolve(entry.fileName.toString())
                val relative = root.relativize(path).toString()
                checkName(relative)
                if (!seen.add(relative)) throw ArchiveScanError("duplicate archive path: $relative")
                val before = identity(path)
                identities[path] = before
                if (Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS)) {
                    visit(path)
                    if (identity(path).stable() != before.stable()) {
                        throw ArchiveScanError("archive directory identity changed: $relative")
                    }
                    continue
                }
                val first = readAndHash(path, relative)
                val second = readAndHash(path, relative)
                if (first != second) {
                    throw ArchiveScanError("archive file changed during read: $relative")
                }
                if (identity(path).stable() != before.stable()) {
                    throw ArchiveScanError("archive file identity changed: $relative")
                }
                files[relative] = ArchiveFile(first, before.mtimeNs)
            }
        }

        visit(root)
        for ((path, before) in identities) {
            if (identity(path).stable() != before.stable()) {
                throw ArchiveScanError("archive entry changed during scan: $path")
            }
        }
        for ((directory, listed) in members) {
            val current = Files.newDirectoryStream(directory).use { stream ->
                stream.map { it.fileName.toString() }.sortedWith(CanonicalText::compare)
            }
            if (current != listed) throw ArchiveScanError("archive entry changed during scan: $directory")
        }
        for ((path, before) in ancestors) {
            val now = identity(path)
            val expected = if (path == root) before.stable() else before.ancestor()
            val actual = if (path == root) now.stable() else now.ancestor()
            if (actual != expected) throw ArchiveScanError("archive ancestor changed during scan: $path")
        }
        return files
    }

    /** `independent_gates._file_path_name`. */
    private fun checkName(relative: String) {
        val parts = relative.split('/')
        if (relative.isEmpty() ||
            "\\" in relative ||
            "\n" in relative ||
            "\r" in relative ||
            parts.any { it in UNSAFE_COMPONENTS } ||
            ":" in parts.first()
        ) {
            throw ArchiveScanError("unsafe archive path: $relative")
        }
    }

    /** `independent_gates._archive_identity`, with the identity checks the reference applies. */
    private fun identity(path: Path): Identity {
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
        return Identity(
            dev = dev,
            ino = ino,
            mode = mode,
            nlink = nlink,
            size = basic.size(),
            mtimeNs = basic.lastModifiedTime().to(java.util.concurrent.TimeUnit.NANOSECONDS),
            ctimeNs = ctime,
        )
    }

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
