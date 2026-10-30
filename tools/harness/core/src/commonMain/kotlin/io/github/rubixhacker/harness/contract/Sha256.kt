package io.github.rubixhacker.harness.contract

import kotlinx.serialization.json.JsonElement
import okio.Buffer
import okio.HashingSource
import okio.Source
import okio.ByteString.Companion.encodeUtf8

/** SHA-256 digests in the form the harness records in receipts. */
object Sha256 {
    fun of(bytes: ByteArray): String =
        Buffer().write(bytes).readByteString().sha256().hex()

    fun of(text: String): String = text.encodeUtf8().sha256().hex()

    /** Reads the source to its end and returns the digest. The source is closed. */
    fun of(source: Source): String {
        val hashing = HashingSource.sha256(source)
        val drain = Buffer()
        hashing.use { stream ->
            while (stream.read(drain, 1024 * 1024) != -1L) {
                drain.clear()
            }
        }
        return hashing.hash.hex()
    }

    /**
     * Digest of a manifest value, as `qualify.manifest_digest` computes it: SHA-256 of the
     * canonical JSON text encoded as UTF-8.
     */
    fun ofCanonical(value: JsonElement): String = of(CanonicalJson.render(value))
}
