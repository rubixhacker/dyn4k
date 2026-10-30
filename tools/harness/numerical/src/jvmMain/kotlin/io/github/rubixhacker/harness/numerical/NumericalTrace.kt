package io.github.rubixhacker.harness.numerical

import io.github.rubixhacker.harness.contract.Sha256
import io.github.rubixhacker.harness.host.FileDigest
import kotlinx.serialization.json.JsonObject
import java.nio.file.Files
import java.nio.file.Path

/**
 * The host half of `receipt`: reading a trace file into the lines `records` consumes, the
 * artifact digests a receipt seals, and the build configuration digest.
 */
object NumericalTrace {
    /**
     * Reads [path] as `receipt.records` reads it: binary lines that each end with a newline.
     * The returned lines keep their terminating newline, because CPython reports JSON error
     * positions against that text.
     */
    fun linesOf(path: Path): List<String> {
        val bytes = Files.readAllBytes(path)
        val lines = ArrayList<String>()
        var start = 0
        var number = 1
        for (index in bytes.indices) {
            if (bytes[index] != '\n'.code.toByte()) continue
            lines.add(decode(bytes, start, index + 1, number))
            start = index + 1
            number += 1
        }
        if (start != bytes.size) {
            throw Rejected("line $number has no newline")
        }
        return lines
    }

    private fun decode(bytes: ByteArray, from: Int, to: Int, number: Int): String = try {
        Charsets.UTF_8.newDecoder()
            .onMalformedInput(java.nio.charset.CodingErrorAction.REPORT)
            .onUnmappableCharacter(java.nio.charset.CodingErrorAction.REPORT)
            .decode(java.nio.ByteBuffer.wrap(bytes, from, to - from))
            .toString()
    } catch (error: java.nio.charset.CharacterCodingException) {
        throw Rejected("line $number: ${error.message}")
    }

    fun recordsOf(path: Path, allowTaggedNonfinite: Boolean = false): List<JsonObject> =
        records(linesOf(path), allowTaggedNonfinite)

    /** `receipt.digest`: the streaming SHA-256 of a file. */
    fun digest(path: Path): String = FileDigest.sha256(path)

    /**
     * `receipt.seal`'s `build_config_sha256` input: each build file's name, a NUL byte, and its
     * bytes, concatenated in `BUILD_FILES` order.
     */
    fun buildConfigData(directory: Path): ByteArray {
        val buffer = java.io.ByteArrayOutputStream()
        for (name in BUILD_FILES) {
            buffer.write(name.toByteArray(Charsets.UTF_8))
            buffer.write(0)
            buffer.write(Files.readAllBytes(directory.resolve(name)))
        }
        return buffer.toByteArray()
    }

    fun buildConfigSha256(directory: Path): String = Sha256.of(buildConfigData(directory))

    /** The build files whose bytes a receipt records, as `receipt.BUILD_FILES`. */
    val BUILD_FILES: List<String> = listOf("settings.gradle.kts", "build.gradle.kts")
}
