package io.github.rubixhacker.harness.qualification

import de.infix.testBalloon.framework.core.testSuite
import io.github.rubixhacker.harness.contract.StrictJson
import java.nio.file.Files
import java.nio.file.Path
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/**
 * The bundle-transport half of `test_publication.py`: what a *downloaded* publication bundle must
 * still prove after its files, its audit, and its trusted manifest pin have all been refreshed.
 *
 * The staging tree is the recorded `stage-receipt.zip` fixture; its audit is re-run here with
 * `StagingAudit.audit`, so every byte the tests mutate starts from a reference-produced tree.
 */
val PublicationTransport by testSuite {
    val candidate = "a".repeat(40)

    /** `test_hosted_publication_transport_preserves_hidden_staging_evidence`. */
    test("packaging keeps hidden staging evidence and a delivered copy without it is rejected") {
        publicationFixture(candidate) { fixture, root ->
            val auditPath = root.resolve("artifact-audit.json")
            val audit = stageAudit(fixture, candidate)
            Fs.writeText(auditPath, PyJson.render(audit) + "\n")
            val bundle = root.resolve("bundle")
            val manifest = PublicationBundle.packageBundle(fixture.root, auditPath, bundle)
            val files = manifest["files"] as JsonObject
            val hidden = listOf(
                "build/staging-repository/.qualification/stage-receipt.json",
                "build/staging-repository/.qualification/stage-console.txt",
            )
            for (relative in hidden) assertTrue(relative in files, relative)
            val pin = Fs.digest(bundle.resolve("manifest.json"))
            assertEquals(manifest, PublicationBundle.verify(bundle, candidate, pin))
            val delivered = root.resolve("delivered")
            copyWithoutDotfiles(bundle, delivered)
            assertEquals(
                "publication bundle files or bytes differ from manifest",
                assertFailsWith<IllegalArgumentException> {
                    PublicationBundle.verify(delivered, candidate, pin)
                }.message,
            )
            val workflow = Files.readString(
                repositoryRoot().resolve(".github/workflows/qualification.yml"),
            )
            val hostedUpload = workflow
                .split("      - name: Upload hosted publication bytes\n", limit = 2)[1]
                .split("      - name:", limit = 2)[0]
            assertTrue("          include-hidden-files: true\n" in hostedUpload)
        }
    }

    /**
     * The reference's "coherently refreshed" cases: the byte, its sidecar, the bundled audit, and
     * the manifest all agree, yet the bundle is still rejected because the audit no longer
     * reproduces its own staging tree.
     */
    test("a coherently refreshed staged byte is rejected even with a refreshed pin") {
        val version = "0.1.0-alpha.1"
        val mutations = listOf(
            "jar" to "io/github/rubixhacker/dyn4k-core-jvm/$version/dyn4k-core-jvm-$version.jar",
            "module" to "io/github/rubixhacker/dyn4k-core-jvm/$version/dyn4k-core-jvm-$version.module",
            "pom" to "io/github/rubixhacker/dyn4k-jvm/$version/dyn4k-jvm-$version.pom",
        )
        for ((label, relative) in mutations) {
            publicationFixture(candidate) { fixture, root ->
                val auditPath = root.resolve("artifact-audit.json")
                Fs.writeText(auditPath, PyJson.render(stageAudit(fixture, candidate)) + "\n")
                val bundle = root.resolve("bundle")
                PublicationBundle.packageBundle(fixture.root, auditPath, bundle)
                val originalPin = Fs.digest(bundle.resolve("manifest.json"))
                PublicationBundle.verify(bundle, candidate, originalPin)
                val changed = root.resolve("changed-$label")
                copyTree(bundle, changed)
                val staged = changed.resolve("build/staging-repository").resolve(relative)
                assertTrue(Files.isRegularFile(staged), "$label: $relative")
                when (label) {
                    "pom" -> Files.writeString(
                        staged,
                        Files.readString(staged).replace("<scope>compile</scope>", "<scope>test</scope>"),
                    )
                    "module" -> {
                        val parsed = StrictJson.load(Files.readString(staged)) as JsonObject
                        val component = parsed["component"] as JsonObject
                        Files.writeString(
                            staged,
                            JsonObject(
                                parsed + (
                                    "component" to JsonObject(
                                        component + ("version" to JsonPrimitive("9.9.9")),
                                    )
                                    ),
                            ).toString(),
                        )
                    }
                    else -> Files.write(staged, Files.readAllBytes(staged) + "changed".toByteArray())
                }
                refresh(changed, relative, staged)
                assertEquals(
                    "trusted manifest SHA-256 differs from downloaded bundle",
                    assertFailsWith<IllegalArgumentException> {
                        PublicationBundle.verify(changed, candidate, originalPin)
                    }.message,
                )
                val error = assertFailsWith<IllegalArgumentException>(label) {
                    PublicationBundle.verify(changed, candidate, Fs.digest(changed.resolve("manifest.json")))
                }
                assertTrue("staged audit differs" in (error.message ?: ""), "$label: ${error.message}")
            }
        }
    }

    /** `test_downloaded_bundle_rejects_unc_share_aliases_with_refreshed_pin`. */
    test("a refreshed UNC share alias in the bundled stage receipt is rejected") {
        for ((index, share) in listOf("share.", "share ").withIndex()) {
            publicationFixture(candidate) { fixture, root ->
                val auditPath = root.resolve("artifact-audit.json")
                Fs.writeText(auditPath, PyJson.render(stageAudit(fixture, candidate)) + "\n")
                val bundle = root.resolve("bundle")
                PublicationBundle.packageBundle(fixture.root, auditPath, bundle)
                val originalPin = Fs.digest(bundle.resolve("manifest.json"))
                val changed = root.resolve("changed-$index")
                copyTree(bundle, changed)
                val relative = ".qualification/stage-receipt.json"
                val receipt = changed.resolve("build/staging-repository").resolve(relative)
                val data = StrictJson.load(Files.readString(receipt)) as JsonObject
                val command = (data["command"] as JsonArray).toMutableList()
                val alias = "\\\\server\\$share\\repo"
                command[0] = JsonPrimitive("$alias\\gradlew.bat")
                Files.writeString(
                    receipt,
                    JsonObject(
                        (data + ("repository" to JsonPrimitive(alias))) +
                            ("command" to JsonArray(command)),
                    ).toString(),
                )
                refresh(changed, relative, receipt)
                assertEquals(
                    "trusted manifest SHA-256 differs from downloaded bundle",
                    assertFailsWith<IllegalArgumentException> {
                        PublicationBundle.verify(changed, candidate, originalPin)
                    }.message,
                )
                val error = assertFailsWith<IllegalArgumentException> {
                    PublicationBundle.verify(changed, candidate, Fs.digest(changed.resolve("manifest.json")))
                }
                assertTrue("staged audit differs" in (error.message ?: ""), error.message ?: "no message")
            }
        }
    }
}

/** The recorded `stage-receipt.zip` tree plus its reference audit, in a scratch directory. */
private fun publicationFixture(candidate: String, block: (Fixture, Path) -> Unit) {
    Fixture.extract("stage-receipt.zip").use { fixture ->
        val root = Files.createTempDirectory("publication-transport")
        try {
            block(fixture, root)
        } finally {
            Files.walk(root).use { walk ->
                walk.sorted(Comparator.reverseOrder()).forEach { Files.deleteIfExists(it) }
            }
        }
    }
}

private fun stageAudit(fixture: Fixture, candidate: String): JsonObject = StagingAudit.audit(
    fixture.staging,
    candidate,
    listOf("jvm", "js"),
    fixture.license,
    fixture.root.resolve("build/staging-repository/.qualification/stage-receipt.json"),
    fixture.root.resolve("build/staging-repository/.qualification/stage-console.txt"),
)

/** Re-binds one changed staged file into the bundled audit and manifest. */
private fun refresh(bundle: Path, relative: String, staged: Path) {
    val digest = Fs.digest(staged)
    val auditPath = bundle.resolve("artifact-audit.json")
    val audit = StrictJson.load(Files.readString(auditPath)) as JsonObject
    val artifacts = (audit["artifacts"] as JsonArray).map { element ->
        val item = element as JsonObject
        if (Py.str(item["path"]) == relative) JsonObject(item + ("sha256" to JsonPrimitive(digest)))
        else item
    }
    Files.writeString(auditPath, JsonObject(audit + ("artifacts" to JsonArray(artifacts))).toString())
    val manifestPath = bundle.resolve("manifest.json")
    val manifest = StrictJson.load(Files.readString(manifestPath)) as JsonObject
    val files = LinkedHashMap<String, JsonElement>((manifest["files"] as JsonObject).mapValues { it.value })
    val stagedRelative = "build/staging-repository/$relative"
    files[stagedRelative] = JsonPrimitive(digest)
    val sidecar = staged.resolveSibling(staged.fileName.toString() + ".sha256")
    if (Files.isRegularFile(sidecar)) files["$stagedRelative.sha256"] = JsonPrimitive(Fs.digest(sidecar))
    files["artifact-audit.json"] = JsonPrimitive(Fs.digest(auditPath))
    Files.writeString(manifestPath, JsonObject(manifest + ("files" to JsonObject(files))).toString())
}

private fun copyTree(source: Path, destination: Path) {
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

private fun copyWithoutDotfiles(source: Path, destination: Path) {
    Files.walk(source).use { walk ->
        for (path in walk.toList()) {
            val relative = source.relativize(path)
            if (relative.any { it.toString().startsWith(".") }) continue
            val target = destination.resolve(relative.toString())
            if (Files.isDirectory(path)) Files.createDirectories(target)
            else {
                target.parent?.let { Files.createDirectories(it) }
                Files.copy(path, target)
            }
        }
    }
}
