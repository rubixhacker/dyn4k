package io.github.rubixhacker.harness.performance

import java.io.File
import java.nio.file.Files
import java.nio.file.LinkOption
import java.nio.file.Path
import java.nio.file.Paths

/** A [PerformanceFileSystem] backed by the real filesystem, for the host adapters and the CLIs. */
class PathFileSystem : PerformanceFileSystem {
    private fun path(path: String): Path = Paths.get(path)

    override fun isFile(path: String): Boolean = Files.isRegularFile(path(path))

    override fun isDirectory(path: String): Boolean = Files.isDirectory(path(path))

    override fun exists(path: String): Boolean = Files.exists(path(path), LinkOption.NOFOLLOW_LINKS)

    override fun readBytes(path: String): ByteArray = Files.readAllBytes(path(path))

    override fun writeText(path: String, text: String) {
        val target = path(path)
        target.parent?.let { Files.createDirectories(it) }
        Files.writeString(target, text)
    }

    override fun writeBytes(path: String, bytes: ByteArray) {
        val target = path(path)
        target.parent?.let { Files.createDirectories(it) }
        Files.write(target, bytes)
    }

    override fun walkFiles(path: String): List<String> {
        val root = path(path)
        if (!Files.isDirectory(root)) return emptyList()
        return Files.walk(root).use { stream ->
            stream.filter { Files.isRegularFile(it) }
                .map { root.relativize(it).toString().replace(File.separatorChar, '/') }
                .toList()
        }.sorted()
    }

    override fun isSymlink(path: String): Boolean = Files.isSymbolicLink(path(path))

    override fun inode(path: String): String? = try {
        val device = Files.getAttribute(path(path), "unix:dev") as Long
        val node = Files.getAttribute(path(path), "unix:ino") as Long
        "$device:$node"
    } catch (_: UnsupportedOperationException) {
        null
    } catch (_: java.io.IOException) {
        null
    }

    override fun sizeOf(path: String): Long? = try {
        Files.size(path(path))
    } catch (_: java.io.IOException) {
        null
    }
}
