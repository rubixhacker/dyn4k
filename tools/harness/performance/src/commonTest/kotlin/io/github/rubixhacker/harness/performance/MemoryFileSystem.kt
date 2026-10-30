package io.github.rubixhacker.harness.performance

/**
 * An in-memory [PerformanceFileSystem] for the archive suites. It models regular files, their
 * bytes, optional hard-link identity, and the "missing" case; it does not model permission errors.
 */
class MemoryFileSystem : PerformanceFileSystem {
    private val files = linkedMapOf<String, ByteArray>()
    private val hardLinks = linkedMapOf<String, String>()
    private var inodeSerial = 0

    fun write(path: String, text: String) = write(path, text.encodeToByteArray())

    override fun writeText(path: String, text: String) = write(path, text.encodeToByteArray())

    override fun writeBytes(path: String, bytes: ByteArray) = write(path, bytes)

    fun write(path: String, bytes: ByteArray) {
        files[PerformancePaths.normalize(path)] = bytes
        hardLinks.remove(PerformancePaths.normalize(path))
        inodeSerial += 1
        inodeFor[PerformancePaths.normalize(path)] = "1:${inodeSerial}"
    }

    fun remove(path: String) {
        files.remove(PerformancePaths.normalize(path))
        inodeFor.remove(PerformancePaths.normalize(path))
    }

    /** Makes [alias] a hard link to [source], so both paths report the same inode. */
    fun link(source: String, alias: String) {
        val normalizedSource = PerformancePaths.normalize(source)
        val bytes = files[normalizedSource] ?: throw IllegalArgumentException("missing $source")
        val normalizedAlias = PerformancePaths.normalize(alias)
        files[normalizedAlias] = bytes
        hardLinks[normalizedAlias] = normalizedSource
        inodeFor[normalizedAlias] = inodeFor.getValue(normalizedSource)
    }

    private val inodeFor = linkedMapOf<String, String>()

    override fun isFile(path: String): Boolean = PerformancePaths.normalize(path) in files

    override fun isDirectory(path: String): Boolean {
        val prefix = PerformancePaths.normalize(path).trimEnd('/') + "/"
        return files.keys.any { it.startsWith(prefix) }
    }

    override fun readBytes(path: String): ByteArray =
        files[PerformancePaths.normalize(path)]?.copyOf()
            ?: throw IllegalArgumentException("missing file: $path")

    override fun walkFiles(path: String): List<String> {
        val prefix = PerformancePaths.normalize(path).trimEnd('/') + "/"
        return files.keys.filter { it.startsWith(prefix) }.map { it.removePrefix(prefix) }
    }

    override fun inode(path: String): String? = inodeFor[PerformancePaths.normalize(path)]

    override fun sizeOf(path: String): Long? = files[PerformancePaths.normalize(path)]?.size?.toLong()
}
