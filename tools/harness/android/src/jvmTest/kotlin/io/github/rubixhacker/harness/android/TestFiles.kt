package io.github.rubixhacker.harness.android

import java.nio.file.Files
import java.nio.file.Path
import kotlin.io.path.writeText

/** Creates a scratch directory, runs [block], and always removes it. */
internal fun <T> withTempDirectory(block: (Path) -> T): T {
    val directory = Files.createTempDirectory("dyn4k-android-test-")
    try {
        return block(directory)
    } finally {
        AndroidFiles.deleteRecursively(directory)
    }
}

/** Writes [text] at [relative] below [root], creating parents. */
internal fun writeFile(root: Path, relative: String, text: String): Path {
    val path = root.resolve(relative)
    Files.createDirectories(path.parent)
    path.toFile().writeText(text)
    return path
}

/** Writes [bytes] at [relative] below [root], creating parents. */
internal fun writeBytes(root: Path, relative: String, bytes: ByteArray): Path {
    val path = root.resolve(relative)
    Files.createDirectories(path.parent)
    path.toFile().writeBytes(bytes)
    return path
}
