package io.github.rubixhacker.harness.host

import io.github.rubixhacker.harness.contract.Sha256
import okio.FileSystem
import okio.Path
import okio.Path.Companion.toPath

/** File digests in the form receipts record them. */
object FileDigest {
    /** Streams the file and returns its SHA-256 hex digest. */
    fun sha256(path: java.nio.file.Path): String = sha256(path.toString())

    fun sha256(path: String): String =
        FileSystem.SYSTEM.source(path.toPath()).use { source -> Sha256.of(source) }

    fun sha256(path: Path): String = FileSystem.SYSTEM.source(path).use { Sha256.of(it) }
}
