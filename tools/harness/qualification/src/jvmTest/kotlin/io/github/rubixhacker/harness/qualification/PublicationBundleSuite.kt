package io.github.rubixhacker.harness.qualification

import de.infix.testBalloon.framework.core.testSuite
import io.github.rubixhacker.harness.contract.StrictJson
import java.nio.file.Files
import java.nio.file.Path
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/**
 * `publication.files_in`, `publication.package`, and `publication.verify`.
 *
 * The manifest is compared against the reference rendering with its file order normalised: the
 * reference lists files in the traversal order of the filesystem that produced the bundle, and
 * both implementations recompute that list from the bytes in front of them, so only the set of
 * paths and digests is a contract. Every other byte of the manifest is compared exactly.
 */
val PublicationBundling by testSuite {
    val vector = TestVectors.root.objectAt("publication")

    test("a staged fixture packages into the recorded bundle") {
        withBundle(vector) { destination, candidate, manifestDigest ->
            val manifestPath = destination.resolve("manifest.json")
            val manifest = StrictJson.load(Fs.readText(manifestPath)) as JsonObject

            assertEquals(vector.objectAt("files"), manifest["files"], "manifest files")
            assertEquals(
                normalizedManifest(vector.primitive("manifest_text")),
                normalizedManifest(Fs.readText(manifestPath)),
                "manifest bytes apart from file order",
            )
            assertEquals(
                vector.objectAt("verified_manifest")["targets"],
                manifest["targets"],
            )
            assertEquals(
                manifest,
                PublicationBundle.verify(destination, candidate, manifestDigest),
            )
            assertEquals(
                PublicationBundle.filesIn(destination).keys,
                (manifest["files"] as JsonObject).keys,
            )
        }
    }

    test("a changed bundled byte is rejected") {
        withBundle(vector) { destination, candidate, digest ->
            val binary = destination.resolve(
                "build/staging-repository/io/github/rubixhacker/dyn4k-core-jvm/" +
                    "0.1.0-alpha.1/dyn4k-core-jvm-0.1.0-alpha.1.jar",
            )
            Files.write(binary, Fs.readBytes(binary) + "\n".toByteArray())
            val error = assertFailsWith<IllegalArgumentException> {
                PublicationBundle.verify(destination, candidate, digest)
            }
            assertEquals("publication bundle files or bytes differ from manifest", error.message)
        }
    }

    test("a missing bundled file is rejected") {
        withBundle(vector) { destination, candidate, digest ->
            Files.delete(destination.resolve("LICENSE.md"))
            val error = assertFailsWith<IllegalArgumentException> {
                PublicationBundle.verify(destination, candidate, digest)
            }
            assertEquals("publication bundle files or bytes differ from manifest", error.message)
        }
    }

    test("an untrusted manifest digest is rejected") {
        withBundle(vector) { destination, candidate, _ ->
            val error = assertFailsWith<IllegalArgumentException> {
                PublicationBundle.verify(destination, candidate, "0".repeat(64))
            }
            assertEquals("trusted manifest SHA-256 differs from downloaded bundle", error.message)
            val malformed = assertFailsWith<IllegalArgumentException> {
                PublicationBundle.verify(destination, candidate, "not-a-digest")
            }
            assertEquals("trusted manifest SHA-256 differs from downloaded bundle", malformed.message)
        }
    }

    test("a bundle for another candidate is rejected") {
        withBundle(vector) { destination, _, digest ->
            val error = assertFailsWith<IllegalArgumentException> {
                PublicationBundle.verify(destination, "f".repeat(40), digest)
            }
            assertEquals("publication bundle candidate, targets, or audit status differs", error.message)
        }
    }

    test("a bundle whose audit did not pass is rejected") {
        withBundle(vector) { destination, candidate, _ ->
            val audit = StrictJson.load(Fs.readText(destination.resolve("artifact-audit.json"))) as JsonObject
            Fs.writeText(
                destination.resolve("artifact-audit.json"),
                PyJson.render(JsonObject(audit + ("status" to JsonPrimitive("FAILED")))) + "\n",
            )
            val error = assertFailsWith<IllegalArgumentException> {
                PublicationBundle.verify(
                    destination, candidate, Fs.digest(destination.resolve("manifest.json")),
                )
            }
            assertEquals("publication bundle candidate, targets, or audit status differs", error.message)
        }
    }

    test("a bundle that no longer reproduces its audit is rejected") {
        withBundle(vector) { destination, candidate, _ ->
            // Rebind the manifest to the changed audit so the file inventory still agrees, then
            // change the recorded error list: the audit can no longer reproduce the staged tree.
            val auditPath = destination.resolve("artifact-audit.json")
            val audit = StrictJson.load(Fs.readText(auditPath)) as JsonObject
            val forged = JsonObject(
                audit + ("errors" to JsonArray(listOf(JsonPrimitive("forged error")))),
            )
            Fs.writeText(auditPath, PyJson.render(forged) + "\n")
            val manifestPath = destination.resolve("manifest.json")
            val manifest = StrictJson.load(Fs.readText(manifestPath)) as JsonObject
            val files = JsonObject(
                PublicationBundle.filesIn(destination).mapValues { JsonPrimitive(it.value) },
            )
            Fs.writeText(manifestPath, PyJson.render(JsonObject(manifest + ("files" to files))) + "\n")
            val error = assertFailsWith<IllegalArgumentException> {
                PublicationBundle.verify(destination, candidate, Fs.digest(manifestPath))
            }
            assertEquals("staged audit differs from current staged files", error.message)
        }
    }

    test("packaging refuses an existing destination") {
        Fixture.extract("stage-receipt.zip").use { fixture ->
            val directory = Files.createTempDirectory("publication-exists")
            try {
                val auditPath = fixture.root.resolve("audit.json")
                Fs.writeText(auditPath, vector.primitive("audit_text"))
                val destination = directory.resolve("bundle")
                PublicationBundle.packageBundle(fixture.root, auditPath, destination)
                val error = assertFailsWith<java.nio.file.FileAlreadyExistsException> {
                    PublicationBundle.packageBundle(fixture.root, auditPath, destination)
                }
                assertTrue(error.message!!.contains("bundle"))
            } finally {
                deleteRecursively(directory)
            }
        }
    }

    test("packaging refuses an audit that did not pass") {
        Fixture.extract("stage-receipt.zip").use { fixture ->
            val directory = Files.createTempDirectory("publication-failed-audit")
            try {
                val audit = StrictJson.load(Fs.readText(fixture.root.resolve("audit.json"))) as JsonObject
                val auditPath = directory.resolve("audit.json")
                Fs.writeText(
                    auditPath,
                    PyJson.render(JsonObject(audit + ("status" to JsonPrimitive("FAILED")))) + "\n",
                )
                val error = assertFailsWith<IllegalArgumentException> {
                    PublicationBundle.packageBundle(fixture.root, auditPath, directory.resolve("bundle"))
                }
                assertEquals("staged publication audit did not pass", error.message)
            } finally {
                deleteRecursively(directory)
            }
        }
    }
}

/** Renders a manifest with its `files` object in path order, so only ordering is normalised. */
internal fun normalizedManifest(text: String): String {
    val manifest = StrictJson.load(text) as JsonObject
    val files = manifest["files"] as JsonObject
    val ordered = JsonObject(
        files.keys.sortedWith(CanonicalText::compare).associateWith { files.getValue(it) },
    )
    return PyJson.render(JsonObject(manifest + ("files" to ordered)))
}

private fun withBundle(
    vector: JsonObject,
    block: (Path, String, String) -> Unit,
) {
    Fixture.extract("stage-receipt.zip").use { fixture ->
        val directory = Files.createTempDirectory("publication-verify")
        try {
            val auditPath = fixture.root.resolve("audit.json")
            Fs.writeText(auditPath, vector.primitive("audit_text"))
            val destination = directory.resolve("bundle")
            val manifest = PublicationBundle.packageBundle(fixture.root, auditPath, destination)
            block(
                destination,
                Py.str(manifest["candidate_sha"])!!,
                Fs.digest(destination.resolve("manifest.json")),
            )
        } finally {
            deleteRecursively(directory)
        }
    }
}
