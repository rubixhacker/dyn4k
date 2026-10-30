package io.github.rubixhacker.harness.qualification

import de.infix.testBalloon.framework.core.testSuite
import io.github.rubixhacker.harness.contract.Qualification
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.attribute.FileTime
import java.util.Base64
import java.util.concurrent.TimeUnit
import kotlin.test.assertEquals
import kotlin.test.assertNotEquals
import kotlin.test.assertFailsWith
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/**
 * `qualify.verify_jvm_mode_publication` and the archive digest it depends on.
 *
 * The fixture archive lives at the absolute path the reference recorded, because a binding
 * carries absolute paths and a receipt's log paths must stay inside the selected archive.
 */
val JvmModePublicationBinding by testSuite {
    val vector = TestVectors.root.objectAt("jvm_mode")
    materialize(vector, Path.of(vector.primitive("archive")))

    test("the archive digest reproduces the reference digest") {
        val archive = Path.of(vector.primitive("archive"))
        assertEquals(vector.primitive("digest"), StableTreeDigest.digest(archive))
    }

    test("a changed binary byte changes the archive digest") {
        val copy = Path.of("/tmp/qualification-parity/jvm-mode/mutant-digest")
        materialize(vector, copy)
        val jar = copy.resolve("staged/${Qualification.targetBinaryPath("dyn4k", "jvm")}")
        Files.write(jar, Fs.readBytes(jar) + "\n".toByteArray())
        assertNotEquals(vector.primitive("digest"), StableTreeDigest.digest(copy))

        val binding = JsonObject(
            exactBinding(vector) + ("publication_archive" to JsonPrimitive(copy.toString())),
        )
        val error = assertFailsWith<IllegalArgumentException> {
            verifier(vector).verify(
                binding,
                TestVectors.matrixCase(vector.objectAt("case")),
                vector.primitive("candidate_sha"),
                exactHashes(vector),
            )
        }
        assertEquals("JVM mode publication archive digest differs", error.message)
    }

    test("a receipt log outside the archive is rejected") {
        val copy = Path.of("/tmp/qualification-parity/jvm-mode/mutant-log")
        materialize(vector, copy)
        val receipt = copy.resolve("receipt.json")
        val data = io.github.rubixhacker.harness.contract.StrictJson.load(Fs.readText(receipt))
        val processes = (data as JsonObject).getValue("processes") as JsonArray
        val replaced = JsonArray(
            processes.map { JsonObject(it as JsonObject + ("log" to JsonPrimitive("/etc/passwd"))) },
        )
        Fs.writeText(receipt, JsonObject(data + ("processes" to replaced)).toString())

        val binding = JsonObject(
            exactBinding(vector) +
                ("publication_archive" to JsonPrimitive(copy.toString())) +
                ("archive_digest" to JsonPrimitive(StableTreeDigest.digest(copy))),
        )
        val error = assertFailsWith<IllegalArgumentException> {
            verifier(vector).verify(
                binding,
                TestVectors.matrixCase(vector.objectAt("case")),
                vector.primitive("candidate_sha"),
                exactHashes(vector),
            )
        }
        assertEquals("JVM mode publication log escapes selected archive", error.message)
    }

    for (entry in (vector.getValue("vectors") as JsonArray).map { it as JsonObject }) {
        test("verify_jvm_mode_publication: ${entry.primitive("name")}") {
            val expected = entry.objectAt("result")
            val expectedHashes = entry.objectAt("expected_hashes").mapValues {
                TestVectors.strOrNull(it.value)
            }
            val lane = TestVectors.matrixCase(vector.objectAt("case"))
            if ("ok" in expected) {
                verifier(vector).verify(
                    entry["binding"], lane, vector.primitive("candidate_sha"), expectedHashes,
                )
            } else {
                val error = assertFailsWith<IllegalArgumentException> {
                    verifier(vector).verify(
                        entry["binding"], lane, vector.primitive("candidate_sha"), expectedHashes,
                    )
                }
                assertEquals(expected.primitive("error"), error.message, entry.primitive("name"))
            }
        }
    }
}

private class RecordedReplay(private val report: JsonElement) : ModeReplay {
    override fun replay(source: Path, archive: Path, candidateSha: String, mode: String): JsonElement = report
}

private fun verifier(vector: JsonObject): JvmModePublication =
    JvmModePublication(StableTreeDigest, RecordedReplay(vector.objectAt("replay")))

private fun exactBinding(vector: JsonObject): JsonObject =
    ((vector.getValue("vectors") as JsonArray)[0] as JsonObject).objectAt("binding")

private fun exactHashes(vector: JsonObject): Map<String, String?> =
    ((vector.getValue("vectors") as JsonArray)[0] as JsonObject).objectAt("expected_hashes")
        .mapValues { TestVectors.strOrNull(it.value) }

/** Recreates the recorded archive, including the modification times its digest binds. */
private fun materialize(vector: JsonObject, archive: Path) {
    deleteRecursively(archive)
    Files.createDirectories(Path.of(vector.primitive("source_checkout")))
    for ((relative, spec) in vector.objectAt("files")) {
        val path = archive.resolve(relative)
        path.parent?.let { Files.createDirectories(it) }
        Files.write(path, Base64.getDecoder().decode(TestVectors.str((spec as JsonObject)["content"])))
        Files.setLastModifiedTime(
            path,
            FileTime.from(TestVectors.long(spec["mtime_ns"]), TimeUnit.NANOSECONDS),
        )
    }
}
