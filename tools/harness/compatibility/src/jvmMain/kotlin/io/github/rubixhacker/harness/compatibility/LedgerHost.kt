package io.github.rubixhacker.harness.compatibility

import kotlinx.serialization.json.JsonObject
import java.io.ByteArrayOutputStream
import java.nio.file.Files
import java.nio.file.Path
import java.util.zip.ZipEntry
import java.util.zip.ZipFile
import java.util.zip.ZipOutputStream

/** The git-backed ledger binding check of `ledger.candidate_source_binding`. */
object LedgerHost {
    /**
     * Compares the recorded candidate source with the requested HEAD and returns the scope status
     * and, when the binding fails, the reason `validate` reports.
     */
    fun candidateSourceBinding(
        source: JsonObject,
        requestedRevision: String,
        root: String,
    ): Pair<String, String?> {
        if (!COMMIT_HEX.matches(requestedRevision)) {
            return "invalid" to "requested candidate revision is invalid"
        }
        val requestedTree = try {
            Processes.git(root, "rev-parse", "$requestedRevision^{tree}")
        } catch (error: Exception) {
            return "invalid" to "requested candidate revision cannot be verified"
        }
        val recordedRevision = source.textOrNull("revision")
        if (recordedRevision == null || !COMMIT_HEX.matches(recordedRevision)) {
            return "invalid" to "candidate source revision is invalid"
        }
        val recordedCommit: String
        val recordedTree: String
        try {
            recordedCommit = Processes.git(root, "rev-parse", "$recordedRevision^{commit}")
            recordedTree = Processes.git(root, "rev-parse", "$recordedRevision^{tree}")
        } catch (error: Exception) {
            return "invalid" to "candidate source revision cannot be verified"
        }
        if (recordedCommit != recordedRevision) {
            return "invalid" to "candidate source revision is not a commit"
        }
        if (source.textOrNull("tree") != recordedTree) {
            return "invalid" to "candidate source tree differs from recorded revision tree"
        }
        if (recordedRevision != requestedRevision) {
            return "historical" to
                "historical candidate source revision differs from requested HEAD: " +
                "recorded=$recordedRevision, requested=$requestedRevision"
        }
        if (source.textOrNull("tree") != requestedTree) {
            return "invalid" to "candidate source tree differs from requested HEAD tree"
        }
        return "bound" to null
    }
}

/** The UID mutation of `exception_ci.mutate_uid`, which rewrites one class inside a JAR. */
object ExceptionCiHost {
    private const val MUTATED_CLASS = "org/dyn4j/exception/ArgumentNullException.class"

    fun mutateUid(source: String, target: String) {
        val before = bigEndianLong(ExceptionCi.UIDS.getValue("ArgumentNullException"))
        val after = bigEndianLong(ExceptionCi.UIDS.getValue("ArgumentNullException") + 1)
        ZipFile(source).use { original ->
            ZipOutputStream(Files.newOutputStream(Path.of(target))).use { mutated ->
                for (item in original.entries()) {
                    var contents = original.getInputStream(item).use { it.readBytes() }
                    if (item.name == MUTATED_CLASS) {
                        if (count(contents, before) != 1) {
                            throw IllegalArgumentException("UID mutation target was not unique")
                        }
                        contents = replace(contents, before, after)
                    }
                    mutated.putNextEntry(ZipEntry(item.name).apply {
                        time = item.time
                        if (item.method == ZipEntry.STORED) {
                            method = ZipEntry.STORED
                            size = contents.size.toLong()
                            compressedSize = contents.size.toLong()
                            crc = java.util.zip.CRC32().apply { update(contents) }.value
                        }
                    })
                    mutated.write(contents)
                    mutated.closeEntry()
                }
            }
        }
        if (io.github.rubixhacker.harness.host.FileDigest.sha256(source) ==
            io.github.rubixhacker.harness.host.FileDigest.sha256(target)
        ) {
            throw IllegalArgumentException("UID mutation did not change the archive")
        }
    }

    private fun bigEndianLong(value: Long): ByteArray = ByteArrayOutputStream().use { stream ->
        for (shift in intArrayOf(56, 48, 40, 32, 24, 16, 8, 0)) {
            stream.write(((value ushr shift) and 0xFF).toInt())
        }
        stream.toByteArray()
    }

    private fun count(haystack: ByteArray, needle: ByteArray): Int {
        var found = 0
        for (index in 0..haystack.size - needle.size) {
            var matches = true
            for (offset in needle.indices) {
                if (haystack[index + offset] != needle[offset]) {
                    matches = false
                    break
                }
            }
            if (matches) found++
        }
        return found
    }

    private fun replace(haystack: ByteArray, needle: ByteArray, replacement: ByteArray): ByteArray {
        val index = (0..haystack.size - needle.size).first { start ->
            needle.indices.all { haystack[start + it] == needle[it] }
        }
        val result = ByteArray(haystack.size)
        haystack.copyInto(result, 0, 0, index)
        replacement.copyInto(result, index)
        haystack.copyInto(result, index + replacement.size, index + needle.size)
        return result
    }
}
