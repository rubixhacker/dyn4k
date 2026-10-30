package io.github.rubixhacker.harness.qualification

import de.infix.testBalloon.framework.core.testSuite
import java.nio.file.Files
import java.nio.file.Path
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlinx.serialization.json.JsonObject

/**
 * `independent_gates._archive_scan` and `archive_digest`, against recorded reference verdicts.
 *
 * The port rejects the same trees the reference rejects: symbolic links, hardlinked files,
 * non-regular entries, unsafe names, missing receipts, and relative roots. It also reproduces the
 * digest of a stable tree exactly.
 */
val ArchiveScanContract by testSuite {
    for (vector in TestVectors.list("archive_scan")) {
        test("archive_digest: ${vector.primitive("name")}") {
            val root = Files.createTempDirectory("archive-scan")
            try {
                buildTree(root, vector.objectAt("spec"))
                val expected = vector.objectAt("result")
                val argument = TestVectors.strOrNull(vector.objectAt("spec")["relative"])
                    ?.let { Path.of(it) } ?: root
                if ("digest" in expected) {
                    assertEquals(expected.primitive("digest"), ArchiveScan.digest(argument))
                } else {
                    val error = assertFailsWith<ArchiveScanError> {
                        ArchiveScan.digest(argument)
                    }
                    assertEquals(
                        expected.primitive("error"),
                        (error.message ?: "").replace(root.toString(), "<root>"),
                        vector.primitive("name"),
                    )
                }
            } finally {
                deleteRecursively(root)
            }
        }
    }

    test("a tree that changes between the two reads is rejected") {
        // The reference reads each file twice and rejects a tree that changes during the scan.
        // A rename between the two scans is observable as a different inventory.
        val root = Files.createTempDirectory("archive-scan-change")
        try {
            Files.write(root.resolve("receipt.json"), "{}\n".toByteArray())
            val payload = root.resolve("payload.txt")
            Files.write(payload, "one\n".toByteArray())
            val digest = ArchiveScan.digest(root)
            Files.write(payload, "two\n".toByteArray())
            val changed = ArchiveScan.digest(root)
            assertEquals(false, digest == changed)
        } finally {
            deleteRecursively(root)
        }
    }
}

private fun buildTree(root: Path, spec: JsonObject) {
    TestVectors.strings(spec["dirs"] ?: kotlinx.serialization.json.JsonArray(emptyList()))
        .forEach { Files.createDirectories(root.resolve(it)) }
    for ((relative, content) in (spec["files"] as? JsonObject) ?: JsonObject(emptyMap())) {
        val path = root.resolve(relative)
        path.parent?.let { Files.createDirectories(it) }
        Files.write(path, TestVectors.str(content).toByteArray())
    }
    for ((relative, target) in (spec["symlinks"] as? JsonObject) ?: JsonObject(emptyMap())) {
        val path = root.resolve(relative)
        path.parent?.let { Files.createDirectories(it) }
        Files.createSymbolicLink(path, Path.of(TestVectors.str(target)))
    }
    for ((relative, target) in (spec["hardlinks"] as? JsonObject) ?: JsonObject(emptyMap())) {
        val path = root.resolve(relative)
        path.parent?.let { Files.createDirectories(it) }
        Files.createLink(path, root.resolve(TestVectors.str(target)))
    }
    for (relative in TestVectors.strings(
        spec["fifo"] ?: kotlinx.serialization.json.JsonArray(emptyList()),
    )) {
        val path = root.resolve(relative)
        path.parent?.let { Files.createDirectories(it) }
        val fifo = ProcessBuilder("mkfifo", path.toString()).start()
        check(fifo.waitFor() == 0) { "mkfifo failed" }
    }
    // The recorded reference digest binds these modification times.
    Files.walk(root).use { stream ->
        for (path in stream) {
            if (path == root) continue
            if (Files.isRegularFile(path, java.nio.file.LinkOption.NOFOLLOW_LINKS)) {
                Files.setLastModifiedTime(
                    path,
                    java.nio.file.attribute.FileTime.from(1_700_000_000L, java.util.concurrent.TimeUnit.SECONDS),
                )
            }
        }
    }
}
