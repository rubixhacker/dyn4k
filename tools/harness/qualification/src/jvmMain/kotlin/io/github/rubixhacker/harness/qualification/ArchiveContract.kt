package io.github.rubixhacker.harness.qualification

import io.github.rubixhacker.harness.contract.Sha256
import java.io.IOException
import java.nio.file.Files
import java.nio.file.Path
import java.util.zip.ZipException
import java.util.zip.ZipFile

/**
 * Archive contracts of `qualify.py`.
 *
 * ZIP handling uses the JDK. All four checks compare exact entry names against an expected set,
 * so a renamed entry or an extra member is a failure rather than a warning.
 */
object ArchiveContract {
    private val MANIFEST_BYTES = "Manifest-Version: 1.0\r\n\r\n".toByteArray()

    /** Opens an archive and maps ZIP failures onto [BadArchiveException]. */
    fun <T> open(path: Path, block: (ZipFile) -> T): T {
        val archive = try {
            ZipFile(path.toFile())
        } catch (error: ZipException) {
            throw BadArchiveException(error.message ?: "invalid archive", error)
        } catch (error: IOException) {
            throw BadArchiveException(error.message ?: "unreadable archive", error)
        }
        return archive.use(block)
    }

    /**
     * `qualify.archive_file_names`: the set of file names, after rejecting duplicate entries and
     * members whose bytes cannot be read.
     */
    fun fileNames(archive: ZipFile): Set<String> {
        val names = mutableListOf<String>()
        for (entry in archive.entries()) names.add(entry.name)
        if (names.size != names.toSet().size) {
            throw IllegalArgumentException("archive has duplicate entries or a corrupt member")
        }
        for (entry in archive.entries()) {
            try {
                archive.getInputStream(entry).use { it.readBytes() }
            } catch (_: IOException) {
                throw IllegalArgumentException("archive has duplicate entries or a corrupt member")
            } catch (_: ZipException) {
                throw IllegalArgumentException("archive has duplicate entries or a corrupt member")
            }
        }
        return names.filter { !it.endsWith("/") }.toSet()
    }

    private fun read(archive: ZipFile, name: String): ByteArray {
        val entry = archive.getEntry(name) ?: throw IllegalArgumentException("archive member is missing: $name")
        return try {
            archive.getInputStream(entry).use { it.readBytes() }
        } catch (error: IOException) {
            throw BadArchiveException(error.message ?: "corrupt archive member", error)
        }
    }

    /** `qualify.validate_source_archive`: exact candidate source tree plus the fixed manifest. */
    fun validateSourceArchive(path: Path, expected: Map<String, String>) {
        open(path) { archive ->
            val names = fileNames(archive)
            if (names != expected.keys + "META-INF/MANIFEST.MF") {
                throw IllegalArgumentException("source entries differ from exact candidate source tree")
            }
            if (!read(archive, "META-INF/MANIFEST.MF").contentEquals(MANIFEST_BYTES)) {
                throw IllegalArgumentException("source JAR manifest differs from publication contract")
            }
            for ((name, sha) in expected) {
                if (Sha256.of(read(archive, name)) != sha) {
                    throw IllegalArgumentException("source bytes differ from exact candidate source tree")
                }
            }
        }
    }

    /** `qualify.validate_generated_docs`: the JAR mirrors the generated Dokka tree byte for byte. */
    fun validateGeneratedDocs(jarPath: Path, generated: Path, license: ByteArray?) {
        if (!Files.isDirectory(generated)) {
            throw IllegalArgumentException("generated Dokka output is missing")
        }
        val expected = LinkedHashMap<String, Path>()
        Files.walk(generated).use { stream ->
            for (path in stream) {
                if (Files.isRegularFile(path)) {
                    expected[generated.relativize(path).toString().replace('\\', '/')] = path
                }
            }
        }
        if (expected.isEmpty() || "index.html" !in expected) {
            throw IllegalArgumentException("generated Dokka output is incomplete")
        }
        open(jarPath) { archive ->
            val names = fileNames(archive)
            if (names != expected.keys + setOf("META-INF/MANIFEST.MF", "META-INF/LICENSE.md")) {
                throw IllegalArgumentException("API documentation entries differ from generated Dokka output")
            }
            if (!read(archive, "META-INF/MANIFEST.MF").contentEquals(MANIFEST_BYTES)) {
                throw IllegalArgumentException("API documentation JAR manifest differs from publication contract")
            }
            if (license == null || !read(archive, "META-INF/LICENSE.md").contentEquals(license)) {
                throw IllegalArgumentException("API documentation license notice differs from repository license")
            }
            for ((name, path) in expected) {
                if (!read(archive, name).contentEquals(Fs.readBytes(path))) {
                    throw IllegalArgumentException("API documentation bytes differ from generated Dokka output")
                }
            }
        }
    }

    /** `qualify.validate_apple_metadata`: manifest-only metadata JAR beside a populated KLIB. */
    fun validateAppleMetadata(metadataJar: Path, klib: Path) {
        open(metadataJar) { archive ->
            if (fileNames(archive) != setOf("META-INF/MANIFEST.MF")) {
                throw IllegalArgumentException("Apple metadata JAR entries differ from publication contract")
            }
            if (!read(archive, "META-INF/MANIFEST.MF").contentEquals(MANIFEST_BYTES)) {
                throw IllegalArgumentException("Apple metadata JAR manifest differs from publication contract")
            }
        }
        open(klib) { archive ->
            val names = fileNames(archive)
            val required = setOf("default/manifest", "default/linkdata/module", "default/ir/bodies.knb")
            // The reference short-circuits on the name checks before it reads any body.
            if (!names.containsAll(required) ||
                !names.any { it.startsWith("default/linkdata/package_") && it.endsWith(".knm") } ||
                required.any { read(archive, it).isEmpty() }
            ) {
                throw IllegalArgumentException("Apple KLIB metadata structure is incomplete")
            }
        }
    }
}
