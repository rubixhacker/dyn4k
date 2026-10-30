package io.github.rubixhacker.harness.qualification

import io.github.rubixhacker.harness.host.FileDigest
import java.io.IOException
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.Path
import okio.FileSystem
import okio.Path.Companion.toOkioPath

/** Thrown when a Git invocation cannot produce the source bytes a contract needs. */
class GitFailure(message: String) : Exception(message)

/** Thrown when an archive is not a readable ZIP file. Stands in for `zipfile.BadZipFile`. */
class BadArchiveException(message: String, cause: Throwable? = null) : Exception(message, cause)

/**
 * File access of the ported publication checks.
 *
 * Byte reads and digests go through okio so the JVM implementation stays on the same library as
 * the shared contracts; path semantics stay on `java.nio.file.Path`, which mirrors `pathlib`.
 */
internal object Fs {
    private val fileSystem = FileSystem.SYSTEM

    fun readBytes(path: Path): ByteArray = fileSystem.read(path.toOkioPath()) { readByteArray() }

    fun readText(path: Path): String = String(readBytes(path), StandardCharsets.UTF_8)

    /** `qualify.digest`: SHA-256 of the file bytes, shared with the host module. */
    fun digest(path: Path): String = FileDigest.sha256(path)

    fun writeText(path: Path, text: String) {
        path.parent?.let { Files.createDirectories(it) }
        Files.write(path, text.toByteArray(StandardCharsets.UTF_8))
    }

    fun writeBytes(path: Path, bytes: ByteArray) {
        path.parent?.let { Files.createDirectories(it) }
        Files.write(path, bytes)
    }

    /** `path.resolve(other)` with `pathlib`'s rule that an absolute right operand wins. */
    fun resolve(base: Path, other: String): Path = base.resolve(other)

    /** `PurePath.relative_to(...).as_posix()`. */
    fun relativePosix(root: Path, path: Path): String =
        root.relativize(path).toString().replace('\\', '/')

    /** `path.is_relative_to(root)` on resolved paths. */
    fun isRelativeTo(path: Path, root: Path): Boolean = path.startsWith(root)

    fun exists(path: Path): Boolean = Files.exists(path)

    fun isFile(path: Path): Boolean = Files.isRegularFile(path)

    fun isDirectory(path: Path): Boolean = Files.isDirectory(path)

    fun isSymlink(path: Path): Boolean = Files.isSymbolicLink(path)

    fun isAbsolute(path: Path): Boolean = path.isAbsolute

    fun deleteIfExists(path: Path) {
        Files.deleteIfExists(path)
    }
}
