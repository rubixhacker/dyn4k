package io.github.rubixhacker.harness.numerical

import io.github.rubixhacker.harness.contract.Sha256
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.io.IOException
import java.nio.file.Files
import java.nio.file.NoSuchFileException
import java.nio.file.Path
import java.util.zip.GZIPInputStream

/** `compare.records(path)`: the binary line stream, gunzipped when the name ends in `.gz`. */
object TraceFiles {
    fun recordsOf(path: Path): List<Compare.Record> {
        val bytes = openStream(path).use { it.readBytes() }
        val records = ArrayList<Compare.Record>()
        var start = 0
        var index = 0
        while (index < bytes.size) {
            if (bytes[index] != '\n'.code.toByte()) {
                index += 1
                continue
            }
            val line = bytes.copyOfRange(start, index + 1)
            val text = line.toString(Charsets.UTF_8).dropLast(1)
            records.add(Compare.Record(line = text + "\n", row = Compare.parse(line)))
            start = index + 1
            index += 1
        }
        if (start != bytes.size) throw Rejected("record has no newline")
        return records
    }

    private fun openStream(path: Path): java.io.InputStream {
        val raw = try {
            Files.newInputStream(path)
        } catch (error: NoSuchFileException) {
            throw Rejected("[Errno 2] No such file or directory: '$path'")
        }
        return if (path.fileName.toString().endsWith(".gz")) GZIPInputStream(raw) else raw
    }

    fun bytesOf(path: Path): ByteArray = try {
        Files.readAllBytes(path)
    } catch (error: NoSuchFileException) {
        throw Rejected("[Errno 2] No such file or directory: '$path'")
    }

    fun digestOf(path: Path): String = Sha256.of(bytesOf(path))
}

/**
 * The host half of `compare`: `audit_reference` and `compare`, which read frozen gzip members,
 * candidate traces and a receipt from disk.
 */
object CompareHost {
    private val FAILURES = listOf(
        Rejected::class.java,
        IOException::class.java,
        NoSuchElementException::class.java,
        ClassCastException::class.java,
        IllegalArgumentException::class.java,
        NullPointerException::class.java,
        IndexOutOfBoundsException::class.java,
    )

    /** `compare.audit_reference`. */
    fun auditReference(fixture: JsonObject, path: Path): JsonObject = try {
        val expected = fixture["reference"] as JsonObject
        val bytes = TraceFiles.bytesOf(path)
        if (path.fileName.toString() != expected["file"]?.stringOrNull() ||
            Sha256.of(bytes) != expected["gzip_sha256"]?.stringOrNull()
        ) {
            throw Rejected("frozen reference file or hash differs")
        }
        val records = TraceFiles.recordsOf(path)
        val streamHash = Sha256.of(records.joinToString("") { it.line })
        val counts = Compare.checkCounts(records, fixture, reference = true)
        if (streamHash != expected["stream_sha256"]?.stringOrNull()) {
            throw Rejected("frozen decompressed stream hash differs")
        }
        buildJsonObject {
            put("status", "PASSED")
            put("scope", "FROZEN_BASELINE_ONLY")
            put(
                "counts",
                buildJsonObject { counts.forEach { (kind, count) -> put(kind, count) } },
            )
        }
    } catch (error: Exception) {
        if (FAILURES.none { it.isInstance(error) }) throw error
        buildJsonObject {
            put("status", "FAILED")
            put("scope", "FROZEN_BASELINE_ONLY")
            put("reason", error.message.orEmpty())
        }
    }

    /** `compare.compare`. */
    fun compare(
        fixture: JsonObject,
        reference: Path,
        candidate: Path,
        receipt: Path,
        expectedSource: String,
        expectedArtifact: String,
        expectedCommit: String,
    ): JsonObject {
        val baseline = auditReference(fixture, reference)
        if (baseline["status"]?.stringOrNull() != "PASSED") {
            return buildJsonObject {
                put("status", "FAILED")
                put("reason", baseline["reason"] ?: JsonPrimitive(""))
            }
        }
        return try {
            val candidateBytes = TraceFiles.bytesOf(candidate)
            Compare.loadReceipt(
                TraceFiles.bytesOf(receipt),
                candidateBytes,
                fixture,
                expectedSource,
                expectedArtifact,
                expectedCommit,
                fixture["counts"] as JsonObject,
            )
            Compare.compareRecords(
                fixture,
                TraceFiles.recordsOf(reference),
                TraceFiles.recordsOf(candidate),
            )
        } catch (error: Exception) {
            if (FAILURES.none { it.isInstance(error) }) throw error
            buildJsonObject {
                put("status", "FAILED")
                put("reason", error.message.orEmpty())
            }
        }
    }

    /** `compare.records` over a raw byte stream, for callers that already hold the bytes. */
    fun recordsOfBytes(bytes: ByteArray): List<Compare.Record> {
        val temporary = Files.createTempFile("numerical-trace", ".jsonl")
        try {
            Files.write(temporary, bytes)
            return TraceFiles.recordsOf(temporary)
        } finally {
            Files.deleteIfExists(temporary)
        }
    }
}
