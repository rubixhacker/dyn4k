package io.github.rubixhacker.harness.compatibility

import io.github.rubixhacker.harness.contract.CanonicalJson

/**
 * The filesystem reads the compatibility verifiers perform.
 *
 * `tools/compatibility` verifiers hash, read, and list files but never write them. `:host` supplies
 * the JVM adapter; the suites in `:compatibility` run the verifiers against an in-memory adapter.
 */
interface CorpusFiles {
    fun isSymlink(path: String): Boolean
    fun isFile(path: String): Boolean
    fun isDirectory(path: String): Boolean

    /** SHA-256 of the file bytes, hexadecimal, as `candidate_coverage.digest` returns it. */
    fun digest(path: String): String
    fun readText(path: String): String

    /**
     * Every file below [root] as a posix path relative to [root], in any order. Symlinks to files
     * are included so callers can reject them, matching `Path.rglob("*")` filtered by `is_file()`.
     */
    fun filesBelow(root: String): List<String>

    /**
     * Every entry below [root] — files, directories, and symlinks — as a posix path relative to
     * [root], without following directory symlinks, as `os.walk(root, followlinks=False)` visits it.
     */
    fun entriesBelow(root: String): List<String>
}

/** Joins a relative name to a root the way `Path(root) / name` joins it. */
internal fun joinPath(root: String, name: String): String = when {
    root.isEmpty() -> name
    root.endsWith("/") -> root + name
    else -> "$root/$name"
}

/** The final path component of [path]. */
internal fun fileName(path: String): String {
    val trimmed = path.trimEnd('/')
    val index = trimmed.lastIndexOf('/')
    return if (index < 0) trimmed else trimmed.substring(index + 1)
}

/**
 * The parts of a posix path as `pathlib.PurePosixPath.parts` reports them: empty and `.` segments
 * are dropped and `..` segments are kept.
 */
internal fun pathParts(path: String): List<String> =
    path.split('/').filter { it.isNotEmpty() && it != "." }

/** True when the path is absolute in the sense of `pathlib.PurePosixPath.is_absolute`. */
internal fun isAbsolutePath(path: String): Boolean = path.startsWith("/")

/**
 * Splits text on the line boundaries `str.splitlines` recognises, without the trailing empty
 * string a trailing newline would otherwise produce.
 */
internal fun pySplitLines(text: String): List<String> {
    val lines = mutableListOf<String>()
    val current = StringBuilder()
    var index = 0
    while (index < text.length) {
        val char = text[index]
        val boundary = when (char) {
            '\n', '\r', '\u000B', '\u000C', '\u001C', '\u001D', '\u001E', '\u0085',
            '\u2028', '\u2029',
            -> true
            else -> false
        }
        if (boundary) {
            lines.add(current.toString())
            current.setLength(0)
            if (char == '\r' && index + 1 < text.length && text[index + 1] == '\n') index++
        } else {
            current.append(char)
        }
        index++
    }
    if (current.isNotEmpty()) lines.add(current.toString())
    return lines
}

/** Sorts keys by code point, as `sorted(dict.items())?` and `sort_keys=True` sort them. */
internal fun sortedByCodePoint(values: Collection<String>): List<String> =
    values.sortedWith(CanonicalJson::compareCodePoints)
