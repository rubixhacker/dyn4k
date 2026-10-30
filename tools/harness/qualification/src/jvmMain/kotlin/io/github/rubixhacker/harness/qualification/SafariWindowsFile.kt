package io.github.rubixhacker.harness.qualification

import java.io.IOException
import java.nio.file.Files
import java.nio.file.LinkOption
import java.nio.file.Path
import java.nio.file.attribute.BasicFileAttributes
import kotlin.io.path.name

/** `safari_windows_file.py`: the Win32 access masks, share modes, and attribute bits. */
object SafariWindowsFile {
    const val FILE_READ_ATTRIBUTES = 0x80
    const val DELETE = 0x00010000
    const val GENERIC_READ = 0x80000000.toInt()
    const val FILE_SHARE_READ = 0x1
    const val FILE_SHARE_WRITE = 0x2
    const val OPEN_EXISTING = 3
    const val FILE_ATTRIBUTE_DIRECTORY = 0x10
    const val FILE_ATTRIBUTE_REPARSE_POINT = 0x400
    const val FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
    const val FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
    const val INVALID_HANDLE_VALUE = -1L

    /** `ctypes.WinError`: an `OSError` carrying the last Win32 error. */
    fun winError(message: String): SafariFileError = SafariFileError(message)

    /** `ctypes.WinError` when the API failed without a message. */
    fun winError(): SafariFileError = SafariFileError("Windows API failure")
}

/** `os.fstat` of an open Windows handle. */
data class SafariHandleStat(
    val device: Long,
    val inode: Long,
    val size: Long,
    val modifiedNanos: Long,
    val regular: Boolean,
) {
    /** The `(st_dev, st_ino, st_size, st_mtime_ns)` tuple the reference compares. */
    fun identity(): List<Long> = listOf(device, inode, size, modifiedNanos)
}

/** An open file: `msvcrt.open_osfhandle` plus the `os.read`/`os.fstat`/`os.close` calls on it. */
interface SafariHandle : AutoCloseable {
    fun stat(): SafariHandleStat

    /** `os.read(descriptor, count)`: fewer bytes only at end of file. */
    fun read(count: Int): ByteArray

    override fun close()
}

/**
 * The Win32 calls of `safari_windows_file`: `CreateFileW`, `GetFileInformationByHandle`,
 * `CloseHandle`, `msvcrt.open_osfhandle`, and the delete-on-close disposition.
 *
 * The reference loads `kernel32` through `ctypes.WinDLL`; a JVM cannot make that call without a
 * native bridge, so production supplies [SafariWindowsFile.failClosed] and every branch below is
 * exercised through this seam instead.
 */
interface SafariWindowsFileKernel {
    fun createFile(path: Path, desired: Int, share: Int, disposition: Int, flags: Int): Long

    /** `GetFileInformationByHandle`; only the attribute bits `_open` checks. */
    fun attributes(handle: Long): Int

    fun closeHandle(handle: Long): Boolean

    /** `open_osfhandle` plus `os.fstat`: the handle as a readable stream. */
    fun open(handle: Long): SafariHandle

    /** `SetFileInformationByHandle(handle, 4, delete, 1)`: mark the directory for deletion. */
    fun removeEmptyDirectory(handle: Long)
}

/**
 * `safari_windows_file.LockedDirectory`: the directory chain, held open component by component so a
 * rename of any component cannot redirect a later read.
 */
interface SafariLockedDirectory : AutoCloseable {
    val path: Path

    fun child(name: String, removable: Boolean = false): SafariLockedDirectory

    fun openFile(name: String): SafariHandle

    fun removeEmpty()

    override fun close()
}

/** The factory the staging code and the Windows source read use to reach a directory chain. */
fun interface SafariLockedDirectoryFactory {
    fun create(repository: Path, relative: Path): SafariLockedDirectory
}

/**
 * `LockedDirectory.__init__` and its `_open`: every component from the volume anchor down is opened
 * with `FILE_FLAG_OPEN_REPARSE_POINT`, and a reparse point or a type mismatch is refused.
 *
 * `resolveRoot` is the reference's `resolve_root`; `removable` lets the leaf directory be unlinked
 * while its handle is open, which is what `remove_empty` needs.
 */
class LockedDirectory(
    repository: Path,
    relative: Path = Path.of(""),
    resolveRoot: Boolean = true,
    removable: Boolean = false,
    private val kernel: SafariWindowsFileKernel = SafariWindowsFile.fileKernel(),
) : SafariLockedDirectory {
    override val path: Path
    private val handles = mutableListOf<Long>()
    private var leafHandle: Long? = null
    private val leafRemovable: Boolean = removable

    init {
        val root = if (resolveRoot) {
            SafariReporterHost.resolvePath(repository)
        } else {
            repository.toAbsolutePath()
        }
        val parts = relative.map { it.toString() }
        if (!root.isAbsolute ||
            root.map { it.toString() }.any { it == ".." } ||
            relative.isAbsolute ||
            parts.any { it.isEmpty() || it == "." || it == ".." }
        ) {
            throw IllegalArgumentException("unsafe Safari path: $relative")
        }
        this.path = root.resolve(relative)
        try {
            val chain = mutableListOf<Path>()
            var current = root.root ?: Path.of("/")
            chain.add(current)
            for (name in root) {
                current = current.resolve(name)
                chain.add(current)
            }
            for (name in relative) {
                current = current.resolve(name)
                chain.add(current)
            }
            for ((index, component) in chain.withIndex()) {
                val handle = open(
                    component,
                    true,
                    removable && index == chain.size - 1,
                    kernel,
                )
                handles.add(handle)
                leafHandle = handle
            }
        } catch (error: Throwable) {
            close()
            throw error
        }
    }

    override fun close() {
        for (handle in handles.asReversed()) {
            kernel.closeHandle(handle)
        }
        handles.clear()
        leafHandle = null
    }

    override fun child(name: String, removable: Boolean): SafariLockedDirectory {
        if (!safeName(name)) throw IllegalArgumentException("unsafe Safari child name")
        return LockedDirectory(
            path,
            Path.of(name),
            resolveRoot = true,
            removable = removable,
            kernel = kernel,
        )
    }

    override fun removeEmpty() {
        val handle = leafHandle
        if (!leafRemovable || handle == null) {
            throw IllegalArgumentException("Safari directory handle does not own deletion")
        }
        kernel.removeEmptyDirectory(handle)
    }

    override fun openFile(name: String): SafariHandle {
        if (!safeName(name)) throw IllegalArgumentException("unsafe Safari file name")
        val handle = open(path.resolve(name), false, false, kernel)
        val opened = try {
            kernel.open(handle)
        } catch (error: Throwable) {
            kernel.closeHandle(handle)
            throw error
        }
        if (!opened.stat().regular) {
            opened.close()
            throw IllegalArgumentException("non-regular Safari file: $name")
        }
        return opened
    }

    private fun safeName(name: String): Boolean =
        name.isNotEmpty() && name != "." && name != ".." &&
            '\\' !in name && '/' !in name

    private companion object {
        fun open(
            path: Path,
            directory: Boolean,
            removable: Boolean,
            kernel: SafariWindowsFileKernel,
        ): Long {
            var flags = SafariWindowsFile.FILE_FLAG_OPEN_REPARSE_POINT
            if (directory) flags = flags or SafariWindowsFile.FILE_FLAG_BACKUP_SEMANTICS
            val desired = when {
                removable -> SafariWindowsFile.FILE_READ_ATTRIBUTES or SafariWindowsFile.DELETE
                directory -> SafariWindowsFile.FILE_READ_ATTRIBUTES
                else -> SafariWindowsFile.GENERIC_READ
            }
            val handle = kernel.createFile(
                path,
                desired,
                SafariWindowsFile.FILE_SHARE_READ or SafariWindowsFile.FILE_SHARE_WRITE,
                SafariWindowsFile.OPEN_EXISTING,
                flags,
            )
            if (handle == SafariWindowsFile.INVALID_HANDLE_VALUE) {
                throw SafariWindowsFile.winError()
            }
            val attributes = try {
                kernel.attributes(handle)
            } catch (error: Throwable) {
                kernel.closeHandle(handle)
                throw error
            }
            if ((attributes and SafariWindowsFile.FILE_ATTRIBUTE_REPARSE_POINT) != 0 ||
                ((attributes and SafariWindowsFile.FILE_ATTRIBUTE_DIRECTORY) != 0) != directory
            ) {
                kernel.closeHandle(handle)
                throw IllegalArgumentException("unsafe Safari path or file type: $path")
            }
            return handle
        }
    }
}

/**
 * The production file kernel.
 *
 * `CreateFileW`, `GetFileInformationByHandle`, `msvcrt.open_osfhandle`, and
 * `SetFileInformationByHandle` have no JVM equivalent without a native bridge, so this kernel fails
 * closed with an explicit message rather than silently degrading to a POSIX path check that a
 * Windows rename could defeat.
 */
internal fun SafariWindowsFile.fileKernel(): SafariWindowsFileKernel = FailClosedFileKernel

private object FailClosedFileKernel : SafariWindowsFileKernel {
    private fun unavailable(): Nothing = throw UnsupportedOperationException(
        "Safari Windows file access is not supported on this host: the Win32 handle layer " +
            "(CreateFileW/GetFileInformationByHandle/SetFileInformationByHandle) has no JVM " +
            "equivalent, so LockedDirectory must be driven through an injected kernel",
    )

    override fun createFile(path: Path, desired: Int, share: Int, disposition: Int, flags: Int): Long =
        unavailable()

    override fun attributes(handle: Long): Int = unavailable()

    override fun closeHandle(handle: Long): Boolean = unavailable()

    override fun open(handle: Long): SafariHandle = unavailable()

    override fun removeEmptyDirectory(handle: Long) = unavailable()
}

/**
 * The POSIX-backed kernel a test can give [LockedDirectory], mirroring the fake the reference's own
 * suite installs over `ctypes.WinDLL`: `CreateFileW` resolves the path without following a final
 * symbolic link, `GetFileInformationByHandle` reports the directory and reparse bits, and the
 * disposition unlinks the directory.
 *
 * This is a *test* kernel, not a production fallback: it maps the Win32 contract onto
 * `java.nio.file` so the locked-directory logic is exercised exactly as the reference exercises it
 * on POSIX.
 */
class PosixWindowsFileKernel : SafariWindowsFileKernel, AutoCloseable {
    private val paths = HashMap<Long, Path>()
    private val channels = HashMap<Long, java.nio.channels.SeekableByteChannel>()
    private var next = 700L

    override fun createFile(path: Path, desired: Int, share: Int, disposition: Int, flags: Int): Long {
        val handle = next++
        paths[handle] = path
        return handle
    }

    override fun attributes(handle: Long): Int {
        val path = paths[handle] ?: throw SafariWindowsFile.winError("unknown handle: $handle")
        val attributes = try {
            Files.readAttributes(path, BasicFileAttributes::class.java, LinkOption.NOFOLLOW_LINKS)
        } catch (error: IOException) {
            throw SafariFileError(error.message ?: "No such file or directory: '$path'")
        }
        var bits = 0
        if (attributes.isDirectory) bits = bits or SafariWindowsFile.FILE_ATTRIBUTE_DIRECTORY
        if (attributes.isSymbolicLink) {
            bits = bits or SafariWindowsFile.FILE_ATTRIBUTE_REPARSE_POINT
        }
        return bits
    }

    override fun closeHandle(handle: Long): Boolean {
        channels.remove(handle)?.let { runCatching { it.close() } }
        paths.remove(handle)
        return true
    }

    override fun open(handle: Long): SafariHandle {
        val path = paths[handle] ?: throw SafariWindowsFile.winError("unknown handle: $handle")
        val channel = try {
            Files.newByteChannel(path, LinkOption.NOFOLLOW_LINKS)
        } catch (error: IOException) {
            throw SafariFileError(error.message ?: "cannot open: '$path'")
        }
        channels[handle] = channel
        return ChannelHandle(channel, path)
    }

    override fun removeEmptyDirectory(handle: Long) {
        val path = paths[handle] ?: throw SafariWindowsFile.winError("unknown handle: $handle")
        Files.delete(path)
    }

    override fun close() {
        for (handle in paths.keys.toList()) closeHandle(handle)
    }

    private class ChannelHandle(
        private val channel: java.nio.channels.SeekableByteChannel,
        private val path: Path,
    ) : SafariHandle {
        override fun stat(): SafariHandleStat {
            val attributes = Files.readAttributes(
                path,
                BasicFileAttributes::class.java,
                LinkOption.NOFOLLOW_LINKS,
            )
            return SafariHandleStat(
                0,
                0,
                attributes.size(),
                attributes.lastModifiedTime().to(java.util.concurrent.TimeUnit.NANOSECONDS),
                attributes.isRegularFile,
            )
        }

        override fun read(count: Int): ByteArray {
            if (count <= 0) return ByteArray(0)
            val buffer = java.nio.ByteBuffer.allocate(count)
            val read = channel.read(buffer)
            if (read <= 0) return ByteArray(0)
            buffer.flip()
            val out = ByteArray(buffer.remaining())
            buffer.get(out)
            return out
        }

        override fun close() {
            runCatching { channel.close() }
        }
    }
}
