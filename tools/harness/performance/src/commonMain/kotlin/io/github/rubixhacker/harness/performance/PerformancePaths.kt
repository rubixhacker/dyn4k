package io.github.rubixhacker.harness.performance

/**
 * The filesystem operations the performance tools perform, so their validation can be ported
 * without a platform API. `:host` supplies a real implementation; tests supply an in-memory one.
 */
interface PerformanceFileSystem {
    fun isFile(path: String): Boolean

    fun isDirectory(path: String): Boolean

    fun exists(path: String): Boolean = isFile(path) || isDirectory(path)

    fun readBytes(path: String): ByteArray

    fun readText(path: String): String = readBytes(path).decodeToString()

    fun writeText(path: String, text: String)

    fun writeBytes(path: String, bytes: ByteArray)

    /** Every regular file below [path], with paths relative to [path], in sorted order. */
    fun walkFiles(path: String): List<String>

    fun isSymlink(path: String): Boolean = false

    /** A stable device/inode identity for the path, or `null` when the filesystem cannot report one. */
    fun inode(path: String): String? = null

    /** The path size in bytes, or `null` when it does not exist. */
    fun sizeOf(path: String): Long?
}

/** Lexical path handling with the parts of `pathlib` behaviour the tools depend on. */
object PerformancePaths {
    const val SEPARATOR: String = "/"

    fun isAbsolute(path: String): Boolean = path.startsWith(SEPARATOR)

    /** Collapses `.` and `..` segments and drops a trailing separator, as `Path.resolve` does lexically. */
    fun normalize(path: String): String {
        if (path.isEmpty()) return "."
        val absolute = isAbsolute(path)
        val parts = mutableListOf<String>()
        for (part in path.split(SEPARATOR)) {
            when (part) {
                "", "." -> Unit
                ".." -> {
                    if (parts.isNotEmpty() && parts.last() != "..") parts.removeAt(parts.size - 1)
                    else if (!absolute) parts.add("..")
                }
                else -> parts.add(part)
            }
        }
        val joined = parts.joinToString(SEPARATOR)
        return when {
            absolute -> SEPARATOR + joined
            joined.isEmpty() -> "."
            else -> joined
        }
    }

    /**
     * `PurePath.parts`. `pathlib` splits the text as written: it drops `.` and empty segments but
     * keeps `..`, which the archive rules test for before any path is resolved.
     */
    fun parts(path: String): List<String> {
        val pieces = path.split(SEPARATOR).filter { it.isNotEmpty() && it != "." }
        return if (isAbsolute(path)) listOf(SEPARATOR) + pieces else pieces
    }

    /** `PurePath.name`. */
    fun name(path: String): String {
        val pieces = parts(path).filter { it != SEPARATOR }
        return pieces.lastOrNull() ?: ""
    }

    /** `PurePath.suffix`, including the leading dot and empty when there is none. */
    fun suffix(path: String): String {
        val last = name(path)
        val dot = last.lastIndexOf('.')
        if (dot <= 0 || dot == last.length - 1) return ""
        return last.substring(dot)
    }

    /** `PurePath.is_relative_to`: [path] lies at or below [root] after normalisation. */
    fun isRelativeTo(path: String, root: String): Boolean {
        val target = parts(path)
        val base = parts(root)
        if (target.size < base.size) return false
        return target.subList(0, base.size) == base
    }

    fun join(left: String, right: String): String = if (left.isEmpty()) right else "$left$SEPARATOR$right"
}
