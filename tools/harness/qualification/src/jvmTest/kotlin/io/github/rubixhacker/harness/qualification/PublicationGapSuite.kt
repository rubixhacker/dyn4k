package io.github.rubixhacker.harness.qualification

import de.infix.testBalloon.framework.core.testSuite
import io.github.rubixhacker.harness.contract.Qualification
import io.github.rubixhacker.harness.contract.Sha256
import io.github.rubixhacker.harness.contract.StrictJson
import java.nio.file.Files
import java.nio.file.Path
import java.security.MessageDigest
import java.util.zip.ZipFile
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

/**
 * The four `test_publication.py` cases that had no Kotlin counterpart, on the programmatic staging
 * fixture so the Apple target is available.
 */
val PublicationGaps by testSuite {
    val version = Qualification.VERSION

    /** `test_documentation_fixture_survives_zip_entry_clock_changes`. */
    test("the documentation fixture survives zip entry clock changes") {
        gapTemp { root ->
            val tree = stagedPublication(root, listOf("jvm", "js"), advanceClocks = true)
            val javadoc = tree.staging
                .resolve(Qualification.GROUP.replace(".", "/"))
                .resolve("dyn4k-core-jvm").resolve(version)
                .resolve("dyn4k-core-jvm-$version-javadoc.jar")
            val clocks = ZipFile(javadoc.toFile()).use { archive ->
                archive.entries().toList().map { it.time }
            }
            assertTrue(clocks.distinct().size > 1, "the clock manipulation did not happen")
            val audit = StagingAudit.audit(
                tree.staging,
                FIXTURE_CANDIDATE,
                tree.targets,
                root.resolve("LICENSE.md"),
                tree.receipt,
                tree.console,
            )
            assertEquals("PASSED", Py.str(audit["status"]), audit["errors"].toString())
        }
    }

    /** `test_downloaded_bundle_rejects_coherent_pom_source_docs_and_apple_changes`. */
    test("a bundle rejects coherent pom, sources, docs, and Apple metadata changes") {
        gapTemp { root ->
            val targets = listOf("jvm", "iosArm64")
            val tree = stagedPublication(root, targets)
            val auditPath = root.resolve("artifact-audit.json")
            val audit = StagingAudit.audit(
                tree.staging, FIXTURE_CANDIDATE, targets, root.resolve("LICENSE.md"),
                tree.receipt, tree.console,
            )
            assertEquals("PASSED", Py.str(audit["status"]), audit["errors"].toString())
            Fs.writeText(auditPath, PyJson.render(audit) + "\n")
            val original = root.resolve("bundle")
            PublicationBundle.packageBundle(root, auditPath, original)
            val externalPin = Fs.digest(original.resolve("manifest.json"))
            val mutations = listOf(
                listOf("pom_scope", "dyn4k-jvm", ".pom", "false"),
                listOf("source_bytes", "dyn4k-core-jvm", "-sources.jar", "true"),
                listOf("fake_docs", "dyn4k-core-jvm", "-javadoc.jar", "false"),
                listOf("apple_literal", "dyn4k-core-iosarm64", "-metadata.jar", "true"),
            )
            for (mutation in mutations) {
                val label = mutation[0]
                val name = mutation[1]
                val extension = mutation[2]
                val refreshModule = mutation[3] == "true"
                val bundle = root.resolve("changed-$label")
                copyGapTree(original, bundle)
                val stageRoot = bundle.resolve("build/staging-repository")
                val base = stageRoot.resolve(Qualification.GROUP.replace(".", "/"))
                    .resolve(name).resolve(version)
                val changed = base.resolve("$name-$version$extension")
                assertTrue(Files.isRegularFile(changed), "$label: $changed")
                when (label) {
                    "pom_scope" -> Files.writeString(
                        changed,
                        Files.readString(changed).replaceFirst(
                            "<scope>compile</scope>",
                            "<scope>test</scope>",
                        ),
                    )
                    "source_bytes" -> Files.write(
                        changed,
                        zipBytes(
                            listOf(
                                "META-INF/MANIFEST.MF" to "Manifest-Version: 1.0\r\n\r\n",
                                "commonMain/api/Type.kt" to "package wrong\nclass Fake\n",
                            ),
                        ),
                    )
                    "fake_docs" -> Files.write(
                        changed,
                        zipBytes(
                            listOf(
                                "META-INF/MANIFEST.MF" to "Manifest-Version: 1.0\r\n\r\n",
                                "META-INF/LICENSE.md" to "Fixture license\n",
                                "index.html" to "<html>wrong API</html>",
                                "api/Wrong.html" to "<html>wrong API</html>",
                            ),
                        ),
                    )
                    else -> Files.write(changed, "not a jar".toByteArray())
                }
                fixtureWrite(changed, Files.readAllBytes(changed))
                val touched = mutableListOf(changed)
                if (refreshModule) {
                    val moduleFile = base.resolve("$name-$version.module")
                    rewriteModuleReference(moduleFile, changed)
                    fixtureWrite(moduleFile, Files.readAllBytes(moduleFile))
                    touched.add(moduleFile)
                }
                refreshBundle(bundle, touched)
                assertEquals(
                    "trusted manifest SHA-256 differs from downloaded bundle",
                    assertFailsWith<IllegalArgumentException>(label) {
                        PublicationBundle.verify(bundle, FIXTURE_CANDIDATE, externalPin)
                    }.message,
                )
                assertFailsWith<IllegalArgumentException>(label) {
                    PublicationBundle.verify(
                        bundle,
                        FIXTURE_CANDIDATE,
                        Fs.digest(bundle.resolve("manifest.json")),
                    )
                }
            }
        }
    }

    /** `test_downloaded_bundle_rejects_coherent_profile_and_embedded_notice`. */
    test("a bundle rejects an active profile and a wrong embedded notice") {
        gapTemp { root ->
            val targets = listOf("jvm")
            val tree = stagedPublication(root, targets)
            val auditPath = root.resolve("artifact-audit.json")
            val audit = StagingAudit.audit(
                tree.staging, FIXTURE_CANDIDATE, targets, root.resolve("LICENSE.md"),
                tree.receipt, tree.console,
            )
            assertEquals("PASSED", Py.str(audit["status"]), audit["errors"].toString())
            Fs.writeText(auditPath, PyJson.render(audit) + "\n")
            val original = root.resolve("bundle")
            PublicationBundle.packageBundle(root, auditPath, original)
            val externalPin = Fs.digest(original.resolve("manifest.json"))
            PublicationBundle.verify(original, FIXTURE_CANDIDATE, externalPin)
            for (mutation in listOf("active_profile_test_scope", "wrong_embedded_notice")) {
                val bundle = root.resolve(mutation)
                copyGapTree(original, bundle)
                val stageRoot = bundle.resolve("build/staging-repository")
                val name = if (mutation == "active_profile_test_scope") "dyn4k-jvm" else "dyn4k-core-jvm"
                val base = stageRoot.resolve(Qualification.GROUP.replace(".", "/"))
                    .resolve(name).resolve(version)
                val touched = mutableListOf<Path>()
                if (mutation == "active_profile_test_scope") {
                    val pom = base.resolve("$name-$version.pom")
                    val profile = "<profiles><profile><id>override-core</id><activation>" +
                        "<activeByDefault>true</activeByDefault></activation><dependencies>" +
                        "<dependency><groupId>${Qualification.GROUP}</groupId>" +
                        "<artifactId>dyn4k-core-jvm</artifactId><version>$version</version>" +
                        "<scope>test</scope></dependency></dependencies></profile></profiles>"
                    Files.writeString(pom, Files.readString(pom).replace("</project>", profile + "</project>"))
                    fixtureWrite(pom, Files.readAllBytes(pom))
                    touched.add(pom)
                } else {
                    val binary = base.resolve("$name-$version.jar")
                    val members = mutableListOf<Pair<String, String>>()
                    ZipFile(binary.toFile()).use { archive ->
                        for (entry in archive.entries()) {
                            val contents = archive.getInputStream(entry).use { it.readBytes() }
                            members.add(
                                entry.name to if (entry.name == "META-INF/LICENSE.md") {
                                    "Wrong legal notice\n"
                                } else {
                                    String(contents)
                                },
                            )
                        }
                    }
                    Files.write(binary, zipBytes(members))
                    fixtureWrite(binary, Files.readAllBytes(binary))
                    touched.add(binary)
                    val moduleFile = base.resolve("$name-$version.module")
                    rewriteModuleReference(moduleFile, binary)
                    fixtureWrite(moduleFile, Files.readAllBytes(moduleFile))
                    touched.add(moduleFile)
                }
                refreshBundle(bundle, touched)
                assertEquals(
                    "trusted manifest SHA-256 differs from downloaded bundle",
                    assertFailsWith<IllegalArgumentException>(mutation) {
                        PublicationBundle.verify(bundle, FIXTURE_CANDIDATE, externalPin)
                    }.message,
                )
                assertFailsWith<IllegalArgumentException>(mutation) {
                    PublicationBundle.verify(
                        bundle,
                        FIXTURE_CANDIDATE,
                        Fs.digest(bundle.resolve("manifest.json")),
                    )
                }
            }
        }
    }

    /** The stale-hidden-directory omission of `test_downloaded_publication_bundle_…`. */
    test("a stale hidden staging directory is not packaged") {
        gapTemp { root ->
            val targets = listOf("js", "jvm")
            val tree = stagedPublication(root, targets)
            val auditPath = root.resolve("artifact-audit.json")
            val audit = StagingAudit.audit(
                tree.staging, FIXTURE_CANDIDATE, targets, root.resolve("LICENSE.md"),
                tree.receipt, tree.console,
            )
            assertEquals("PASSED", Py.str(audit["status"]), audit["errors"].toString())
            Fs.writeText(auditPath, PyJson.render(audit) + "\n")
            plainWrite(
                tree.staging.resolve(".qualification/old/receipt.json"),
                "{\"candidate_sha\":\"old\"}".toByteArray(),
            )
            val bundle = root.resolve("bundle")
            PublicationBundle.packageBundle(root, auditPath, bundle)
            assertTrue(
                !Files.exists(bundle.resolve("build/staging-repository/.qualification/old")),
                "a stale hidden staging directory was packaged",
            )
            PublicationBundle.verify(
                bundle,
                FIXTURE_CANDIDATE,
                Fs.digest(bundle.resolve("manifest.json")),
            )
        }
    }
}

private fun gapTemp(block: (Path) -> Unit) {
    val root = Files.createTempDirectory("publication-gap")
    try {
        block(root)
    } finally {
        Files.walk(root).use { walk ->
            walk.sorted(Comparator.reverseOrder()).forEach { Files.deleteIfExists(it) }
        }
    }
}

private fun copyGapTree(source: Path, destination: Path) {
    Files.walk(source).use { walk ->
        for (path in walk.toList()) {
            val target = destination.resolve(source.relativize(path).toString())
            if (Files.isDirectory(path)) Files.createDirectories(target)
            else {
                target.parent?.let { Files.createDirectories(it) }
                Files.copy(path, target)
            }
        }
    }
}

/** Re-binds every touched staged file into the bundled audit and manifest. */
private fun refreshBundle(bundle: Path, touched: List<Path>) {
    val stageRoot = bundle.resolve("build/staging-repository")
    val auditPath = bundle.resolve("artifact-audit.json")
    val audit = StrictJson.load(Files.readString(auditPath)) as JsonObject
    val digests = touched.associate {
        stageRoot.relativize(it).toString().replace('\\', '/') to Fs.digest(it)
    }
    val artifacts = (audit["artifacts"] as JsonArray).map { element ->
        val item = element as JsonObject
        val digest = digests[Py.str(item["path"])]
        if (digest == null) item else JsonObject(item + ("sha256" to JsonPrimitive(digest)))
    }
    Files.writeString(auditPath, JsonObject(audit + ("artifacts" to JsonArray(artifacts))).toString())
    val manifestPath = bundle.resolve("manifest.json")
    val manifest = StrictJson.load(Files.readString(manifestPath)) as JsonObject
    val files = LinkedHashMap<String, JsonElement>(
        (manifest["files"] as JsonObject).mapValues { it.value },
    )
    for (path in touched) {
        files[bundle.relativize(path).toString().replace('\\', '/')] = JsonPrimitive(Fs.digest(path))
        val sidecar = path.resolveSibling(path.fileName.toString() + ".sha256")
        if (Files.isRegularFile(sidecar)) {
            files[bundle.relativize(sidecar).toString().replace('\\', '/')] =
                JsonPrimitive(Fs.digest(sidecar))
        }
    }
    files["artifact-audit.json"] = JsonPrimitive(Fs.digest(auditPath))
    Files.writeString(manifestPath, JsonObject(manifest + ("files" to JsonObject(files))).toString())
}

/** Rewrites every variant file reference that names `binary`, as the reference tests do. */
private fun rewriteModuleReference(moduleFile: Path, binary: Path) {
    val data = StrictJson.load(Files.readString(moduleFile)) as JsonObject
    val bytes = Files.readAllBytes(binary)
    val url = binary.fileName.toString()
    val variants = (data["variants"] as JsonArray).map { element ->
        val variant = element as JsonObject
        val files = (variant["files"] as? JsonArray) ?: return@map element
        val rewritten = files.map { fileElement ->
            val file = fileElement as JsonObject
            if (Py.str(file["url"]) != url) {
                file
            } else {
                val updated = LinkedHashMap<String, JsonElement>(file)
                updated["size"] = JsonPrimitive(bytes.size)
                for (algorithm in listOf("sha512", "sha256", "sha1", "md5")) {
                    updated[algorithm] = JsonPrimitive(hashOf(algorithm, bytes))
                }
                JsonObject(updated)
            }
        }
        JsonObject(variant + ("files" to JsonArray(rewritten)))
    }
    Files.writeString(moduleFile, JsonObject(data + ("variants" to JsonArray(variants))).toString())
}

private fun hashOf(algorithm: String, bytes: ByteArray): String {
    val name = when (algorithm) {
        "sha512" -> "SHA-512"
        "sha256" -> "SHA-256"
        "sha1" -> "SHA-1"
        else -> "MD5"
    }
    return MessageDigest.getInstance(name).digest(bytes).joinToString("") { "%02x".format(it) }
}
