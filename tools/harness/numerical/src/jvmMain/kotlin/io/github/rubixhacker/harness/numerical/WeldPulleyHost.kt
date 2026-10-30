package io.github.rubixhacker.harness.numerical

import kotlinx.serialization.json.JsonObject
import java.io.IOException
import java.nio.file.Files
import java.nio.file.NoSuchFileException
import java.nio.file.Path
import java.util.zip.GZIPInputStream

/**
 * The host half of `weld_pulley_quality.audit_quality`: reading the frozen gzip member and
 * decompressing it. `main`'s declaration/capture/JAR hash gate stays with the CLI that owns it.
 */
object WeldPulleyHost {
    fun auditQuality(
        declaration: JsonObject,
        manifest: JsonObject,
        case: String,
        path: Path,
    ): JsonObject = WeldPulleyQuality.auditQuality(
        declaration,
        manifest,
        case,
        path.fileName.toString(),
    ) {
        val raw = try {
            Files.readAllBytes(path)
        } catch (error: NoSuchFileException) {
            throw Rejected("[Errno 2] No such file or directory: '$path'")
        }
        val stream = try {
            GZIPInputStream(raw.inputStream()).use { it.readBytes() }
        } catch (error: IOException) {
            throw Rejected(error.message.orEmpty())
        }
        raw to stream
    }
}
