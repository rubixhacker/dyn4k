package io.github.rubixhacker.harness.migration

import de.infix.testBalloon.framework.core.testSuite
import io.github.rubixhacker.harness.contract.Sha256
import java.nio.file.Files
import java.nio.file.Path
import java.util.Base64
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * `tools/migration/test_journeys.py` replayed against generated pinned samples, published JARs,
 * and a missing headful image. The production policy is the Python module's constants; these
 * cases build a `JourneyPolicy` over fixtures whose bytes the test controls.
 */
val JourneyCommandContract by testSuite {
    test("pinned samples have the exact source manifest") {
        assertEquals(Journeys.SAMPLE_REVISION, JourneyPolicy.DEFAULT.sampleRevision)
        assertEquals(Journeys.SOURCE_MANIFEST_SHA256, JourneyPolicy.DEFAULT.sourceManifestSha256)
        assertEquals("2c6b318e929baab77e9753ae78a4965eee74a30a", JourneyPolicy.DEFAULT.sampleRevision)
        assertEquals(
            "15ce636ac8eec34b24e73bc96270b49a44c94318850050b1e9bc0d930a9c8d58",
            JourneyPolicy.DEFAULT.sourceManifestSha256,
        )
        assertEquals(3, JourneyPolicy.DEFAULT.pinnedJars.size)
        Fixture().use { fixture ->
            val report = fixture.runner.inspectSamples(fixture.samples)
            val recorded = okRecord("inspect_samples")
            assertEquals(pyJsonText(recorded), pyJsonText(report))
            assertEquals(42L, (report.get("java_source_count") as PyValue.Int).value)
            assertEquals(fixture.manifestDigest, (report.get("manifest_sha256") as PyValue.Text).value)
        }
    }

    test("dirty sample checkout is rejected") {
        Fixture().use { fixture ->
            val copied = fixture.work.resolve("samples-dirty")
            copyTree(fixture.samples, copied)
            val source = Files.walk(copied).use { stream ->
                stream.filter {
                    Files.isRegularFile(it) && it.toString().endsWith(".java")
                }.findFirst().get()
            }
            Files.write(source, Files.readAllBytes(source) + byteArrayOf('\n'.code.toByte()))
            val error = assertFailsWith<MigrationFailure> { fixture.runner.inspectSamples(copied) }
            assertEquals(errorRecord("inspect_samples_dirty"), error.message)
        }
    }

    test("unavailable runtime records all ten cases") {
        Fixture().use { fixture ->
            val output = fixture.work.resolve("evidence-unavailable")
            fixture.runner.recordUnavailable(output, "no display")
            val recorded = VectorData.section("journeys").get("unavailable_empty")
            assertEquals(
                (recorded.get("summary_text") as PyValue.Text).value,
                MigrationFiles.readTextOrEmpty(output.resolve("summary.json")),
            )
            assertEquals(
                (recorded.get("evidence_text") as PyValue.Text).value,
                MigrationFiles.readTextOrEmpty(output.resolve("evidence.sha256")),
            )
            val summary = pyFromJson(
                kotlinx.serialization.json.Json.parseToJsonElement(
                    MigrationFiles.readTextOrEmpty(output.resolve("summary.json")),
                ),
            )
            assertEquals(10, (summary.get("cases") as PyValue.Seq).items.size)
            assertTrue(
                (summary.get("cases") as PyValue.Seq).items.all {
                    pyEquals(it.get("status"), pyText("UNAVAILABLE")) &&
                        pyEquals(it.get("reason"), pyText("no display"))
                },
            )
        }
    }

    test("baseline uses pinned published jars") {
        Fixture().use { fixture ->
            val resolved = fixture.work.resolve("resolved-baseline")
            fixture.writeJars(resolved)
            val report = fixture.runner.inspectArtifacts("baseline", resolved, null)
            assertEquals(pyJsonText(okRecord("baseline_artifacts")), pyJsonText(report))
            assertEquals(3, (report.get("jars") as PyValue.Seq).items.size)
            MigrationFiles.writeBytes(resolved.resolve("dyn4j-6.0.0.jar"), "changed".toByteArray())
            val error = assertFailsWith<MigrationFailure> {
                fixture.runner.inspectArtifacts("baseline", resolved, null)
            }
            assertEquals(errorRecord("baseline_artifacts_changed"), error.message)
        }
    }

    test("candidate rejects staged, duplicate, and unstaged artifacts") {
        Fixture().use { fixture ->
            val resolved = fixture.work.resolve("resolved-candidate")
            val staged = fixture.work.resolve("staged")
            val stagedJar = staged.resolve(
                "io/github/rubixhacker/dyn4k-core-jvm/0.1.0-alpha.1/${Journeys.CANDIDATE_JAR}",
            )
            fixture.writeStagedPublication(stagedJar)
            Files.createDirectories(resolved)
            Files.copy(stagedJar, resolved.resolve(stagedJar.fileName))
            for (name in listOf("jogl-all-2.3.2.jar", "gluegen-rt-2.3.2.jar")) {
                MigrationFiles.writeBytes(resolved.resolve(name), fixture.emptyJar)
            }
            assertEquals(
                pyJsonText(okRecord("candidate_artifacts")),
                pyJsonText(fixture.runner.inspectArtifacts("candidate", resolved, staged)),
            )
            MigrationFiles.writeBytes(resolved.resolve(stagedJar.fileName), "project source output".toByteArray())
            assertEquals(
                errorRecord("candidate_artifacts_unstaged"),
                assertFailsWith<MigrationFailure> {
                    fixture.runner.inspectArtifacts("candidate", resolved, staged)
                }.message,
            )
            Files.copy(stagedJar, resolved.resolve(stagedJar.fileName), java.nio.file.StandardCopyOption.REPLACE_EXISTING)
            MigrationFiles.writeBytes(resolved.resolve("dyn4j-6.0.0.jar"), fixture.emptyJar)
            assertEquals(
                errorRecord("candidate_artifacts_duplicate"),
                assertFailsWith<MigrationFailure> {
                    fixture.runner.inspectArtifacts("candidate", resolved, staged)
                }.message,
            )
            Files.delete(resolved.resolve("dyn4j-6.0.0.jar"))
            Files.delete(fixture.withSuffix(stagedJar, ".pom"))
            assertEquals(
                errorRecord("candidate_artifacts_missing_metadata"),
                assertFailsWith<MigrationFailure> {
                    fixture.runner.inspectArtifacts("candidate", resolved, staged)
                }.message,
            )
            fixture.writePublicationMetadata(stagedJar, "io.github.other")
            assertEquals(
                errorRecord("candidate_artifacts_identity"),
                assertFailsWith<MigrationFailure> {
                    fixture.runner.inspectArtifacts("candidate", resolved, staged)
                }.message,
            )
            fixture.writePublicationMetadata(stagedJar, "io.github.rubixhacker")
        }
    }

    test("baseline compiles all unchanged sources at Java 8") {
        Fixture().use { fixture ->
            fixture.writeJars(fixture.work.resolve("resolved-baseline"))
            val output = fixture.work.resolve("compile-ok")
            val receipt = fixture.runner.compileSamples(
                "baseline", fixture.samples, fixture.work.resolve("resolved-baseline"),
                null, output, fixture.javac,
            )
            val recorded = VectorData.section("journeys").get("compile_success")
            assertEquals(pyJsonText((recorded.get("receipt"))), pyJsonText(fixture.normalise(receipt)))
            assertEquals("PASSED", (receipt.get("status") as PyValue.Text).value)
            assertEquals(42L, (receipt.get("source_count") as PyValue.Int).value)
            assertTrue((receipt.get("class_count") as PyValue.Int).value > 42)
            assertEquals(0L, (receipt.get("exit_code") as PyValue.Int).value)
            assertTrue(Files.isRegularFile(output.resolve("javac.log")))
        }
    }

    test("run rejects a dirty candidate worktree") {
        Fixture().use { fixture ->
            val marker = fixture.candidate.resolve("marker.txt")
            Files.write(marker, Files.readAllBytes(marker) + byteArrayOf('\n'.code.toByte()))
            val output = fixture.work.resolve("run-all-dirty")
            val error = assertFailsWith<MigrationFailure> {
                fixture.runner.runAll(
                    fixture.samples, fixture.work.resolve("resolved-root"),
                    fixture.work.resolve("staged"), fixture.work.resolve("instrumentation"),
                    output, fixture.javac, defaultJava(), fixture.work.resolve("jdk"),
                    "localhost/dyn4k-migration:missing-test-image", 180.0,
                )
            }
            assertEquals("candidate worktree changed; exact committed harness required", error.message)
            assertFalse(Files.exists(output))
        }
    }

    test("compiler timeout records a failed receipt") {
        Fixture().use { fixture ->
            fixture.writeJars(fixture.work.resolve("resolved-baseline"))
            val slow = fixture.work.resolve("slow-javac")
            MigrationFiles.writeText(slow, "#!/bin/sh\nsleep 5\n")
            slow.toFile().setExecutable(true)
            val output = fixture.work.resolve("compile-timeout")
            val receipt = fixture.runner.compileSamples(
                "baseline", fixture.samples, fixture.work.resolve("resolved-baseline"),
                null, output, slow, 0.2,
            )
            val recorded = VectorData.section("journeys").get("compile_timeout")
            assertEquals(pyJsonText(recorded.get("receipt")), pyJsonText(fixture.normalise(receipt, slow)))
            assertEquals("FAILED", (receipt.get("status") as PyValue.Text).value)
            assertEquals("TIMEOUT", (receipt.get("reason") as PyValue.Text).value)
            assertEquals(124L, (receipt.get("exit_code") as PyValue.Int).value)
            assertTrue("PROCESS TIMEOUT" in MigrationFiles.readTextOrEmpty(output.resolve("javac.log")))
        }
    }

    test("altered raw evidence fails manifest verification") {
        Fixture().use { fixture ->
            val output = fixture.work.resolve("evidence")
            Files.createDirectories(output)
            MigrationFiles.writeText(output.resolve("raw.log"), "original observation\n")
            MigrationFiles.writeText(output.resolve("a.log"), "earlier evidence\n")
            fixture.runner.recordUnavailable(output, "no display")
            val recorded = VectorData.section("journeys").get("unavailable_with_files")
            assertEquals(
                (recorded.get("summary_text") as PyValue.Text).value,
                MigrationFiles.readTextOrEmpty(output.resolve("summary.json")),
            )
            assertEquals(
                (recorded.get("evidence_text") as PyValue.Text).value,
                MigrationFiles.readTextOrEmpty(output.resolve("evidence.sha256")),
            )
            val manifest = pythonSplitlines(MigrationFiles.readTextOrEmpty(output.resolve("evidence.sha256")))
            assertEquals(2, manifest.size)
            assertTrue(manifest[0].endsWith("  a.log"))
            assertTrue(manifest[1].endsWith("  raw.log"))
            fixture.runner.verifyEvidence(output)
            MigrationFiles.writeText(output.resolve("raw.log"), "changed observation\n")
            val error = assertFailsWith<MigrationFailure> { fixture.runner.verifyEvidence(output) }
            assertEquals("raw evidence changed or summary manifest binding differs", error.message)
        }
    }

    test("missing published dependency records a preparation failure") {
        Fixture().use { fixture ->
            val output = fixture.work.resolve("compile-missing")
            val receipt = fixture.runner.compileSamples(
                "baseline", fixture.samples, fixture.work.resolve("missing"),
                null, output, fixture.javac,
            )
            val recorded = VectorData.section("journeys").get("compile_missing_dependency")
            assertEquals(pyJsonText(recorded.get("receipt")), pyJsonText(fixture.normalise(receipt)))
            assertEquals("FAILED", (receipt.get("status") as PyValue.Text).value)
            assertEquals("preparation", (receipt.get("stage") as PyValue.Text).value)
            assertTrue("resolved JAR set is empty" in (receipt.get("reason") as PyValue.Text).value)
        }
    }

    test("a sample change after compilation prevents the summary") {
        Fixture().use { fixture ->
            val output = fixture.work.resolve("run-all-changed")
            val error = assertFailsWith<MigrationFailure> {
                fixture.runAll(output, mutate = true)
            }
            assertEquals("sample checkout changed", error.message)
            for (provider in Journeys.PROVIDERS) {
                val receipt = pyFromJson(
                    kotlinx.serialization.json.Json.parseToJsonElement(
                        MigrationFiles.readTextOrEmpty(output.resolve("$provider/compile/compile.json")),
                    ),
                )
                assertEquals("PASSED", (receipt.get("status") as PyValue.Text).value)
            }
            assertFalse(Files.exists(output.resolve("summary.json")))
            val check = pyFromJson(
                kotlinx.serialization.json.Json.parseToJsonElement(
                    MigrationFiles.readTextOrEmpty(output.resolve("sample-check.json")),
                ),
            )
            assertEquals("FAILED", (check.get("status") as PyValue.Text).value)
            assertEquals("sample checkout changed", (check.get("reason") as PyValue.Text).value)
            assertTrue(fixture.sampleStatus().isNotEmpty())
            val recorded = VectorData.section("journeys").get("run_all_changed")
            assertEquals(
                (recorded.get("receipts").get("sample-check.json") as PyValue.Text).value,
                fixture.normaliseText(output.resolve("sample-check.json")),
            )
        }
    }

    test("a stable checkout writes a verified summary") {
        Fixture().use { fixture ->
            val output = fixture.work.resolve("run-all-stable")
            val report = fixture.runAll(output, mutate = false)
            assertTrue(Files.isRegularFile(output.resolve("summary.json")))
            val check = pyFromJson(
                kotlinx.serialization.json.Json.parseToJsonElement(
                    MigrationFiles.readTextOrEmpty(output.resolve("sample-check.json")),
                ),
            )
            assertEquals("PASSED", (check.get("status") as PyValue.Text).value)
            assertEquals(42L, (check.get("java_source_count") as PyValue.Int).value)
            assertEquals(fixture.manifestDigest, (check.get("manifest_sha256") as PyValue.Text).value)
            assertEquals(10L, (report.get("unavailable_cases") as PyValue.Int).value)
            fixture.runner.verifyEvidence(output)
            assertTrue(fixture.sampleStatus().isEmpty())
            val recorded = VectorData.section("journeys").get("run_all_stable").get("summary")
            val withoutManifest = report.let { map ->
                pyMap(
                    *map.entries.filterKeys {
                        it != "evidence_manifest_sha256" && it != "evidence_file_count"
                    }.map { it.key to it.value }.toTypedArray(),
                )
            }
            if (which("podman") != null) {
                assertEquals(pyJsonText(recorded), pyJsonText(fixture.normalise(withoutManifest)))
            }
            val stable = VectorData.section("journeys").get("run_all_stable")
            assertEquals(
                (stable.get("receipts").get("sample-check.json") as PyValue.Text).value,
                fixture.normaliseText(output.resolve("sample-check.json")),
            )
            if (which("podman") != null) {
                assertEquals(
                    (stable.get("receipts").get("preparation.json") as PyValue.Text).value,
                    fixture.normaliseText(output.resolve("preparation.json")),
                )
            }
        }
    }
}

/** One generated fixture tree with the pinned policy the tests run under. */
private class Fixture : AutoCloseable {
    val work: Path = Files.createTempDirectory("dyn4k-journey-")
    val samples: Path = work.resolve("samples")
    val candidate: Path = work.resolve("candidate")
    val emptyJar: ByteArray = Base64.getDecoder().decode(
        (VectorData.section("fixture").get("empty_jar_base64") as PyValue.Text).value,
    )
    val javac: Path = defaultJavac()
    val manifestDigest: String
    val policy: JourneyPolicy
    val runner: JourneyRunner

    init {
        val recorded = VectorData.section("journeys")
        val files = linkedMapOf<String, ByteArray>()
        val fixtureFiles = VectorData.section("fixture").get("samples_files") as PyValue.Map
        for (relative in fixtureFiles.entries.keys) {
            val index = relative.substringAfter("Sample").substringBefore(".java").toInt()
            files[relative] = (
                "package fixture;\npublic class Sample" + index.toString().padStart(2, '0') +
                    " { public static class Inner { } }\n"
                ).toByteArray()
        }
        val revision = gitRepo(samples, files)
        gitRepo(candidate, linkedMapOf("marker.txt" to "fixture\n".toByteArray()))
        assertEquals(
            (recorded.get("samples_revision") as PyValue.Text).value,
            revision,
            "generated samples revision",
        )
        manifestDigest = pythonSplitlines(readGit(samples, "ls-files", "--", "*.java"))
            .sortedWith { left, right ->
                io.github.rubixhacker.harness.contract.CanonicalJson.compareCodePoints(left, right)
            }
            .joinToString("") { path -> MigrationFiles.digest(samples.resolve(path)) + "  " + path + "\n" }
            .let { Sha256.of(it) }
        assertEquals(
            (recorded.get("manifest_sha256") as PyValue.Text).value,
            manifestDigest,
        )
        policy = JourneyPolicy(
            sampleRevision = revision,
            sourceManifestSha256 = manifestDigest,
            pinnedJars = mapOf(
                "dyn4j-6.0.0.jar" to MigrationFiles.digest(emptyJar),
                "jogl-all-2.3.2.jar" to MigrationFiles.digest(emptyJar),
                "gluegen-rt-2.3.2.jar" to MigrationFiles.digest(emptyJar),
            ),
        )
        runner = JourneyRunner(candidate, policy)
    }

    fun writeJars(directory: Path) {
        Files.createDirectories(directory)
        for (name in listOf("dyn4j-6.0.0.jar", "jogl-all-2.3.2.jar", "gluegen-rt-2.3.2.jar")) {
            MigrationFiles.writeBytes(directory.resolve(name), emptyJar)
        }
    }

    fun writeStagedPublication(stagedJar: Path) {
        Files.createDirectories(stagedJar.parent)
        MigrationFiles.writeBytes(stagedJar, emptyJar)
        writePublicationMetadata(stagedJar, "io.github.rubixhacker")
        MigrationFiles.writeText(withSuffix(stagedJar, ".module"), "{}")
    }

    fun writePublicationMetadata(stagedJar: Path, groupId: String) {
        MigrationFiles.writeText(
            withSuffix(stagedJar, ".pom"),
            "<project><groupId>$groupId</groupId>" +
                "<artifactId>dyn4k-core-jvm</artifactId><version>0.1.0-alpha.1</version></project>",
        )
    }

    fun withSuffix(path: Path, suffix: String): Path = MigrationFiles.withSuffix(path, suffix)

    fun sampleStatus(): String =
        readGit(samples, "status", "--porcelain=v1")

    /** Prepares the resolved trees, staged publication, and counting compiler `run-all` needs. */
    fun runAll(output: Path, mutate: Boolean): PyValue.Map {
        val resolvedRoot = work.resolve("resolved-root")
        writeJars(resolvedRoot.resolve("baseline"))
        val candidateResolved = resolvedRoot.resolve("candidate")
        Files.createDirectories(candidateResolved)
        for (name in listOf("jogl-all-2.3.2.jar", "gluegen-rt-2.3.2.jar")) {
            MigrationFiles.writeBytes(candidateResolved.resolve(name), emptyJar)
        }
        val stagedJar = work.resolve(
            "staged/io/github/rubixhacker/dyn4k-core-jvm/0.1.0-alpha.1/${Journeys.CANDIDATE_JAR}",
        )
        writeStagedPublication(stagedJar)
        Files.copy(stagedJar, candidateResolved.resolve(stagedJar.fileName))
        val counter = work.resolve("compile-count")
        Files.deleteIfExists(counter)
        val wrapper = work.resolve("counting-javac")
        val mutatePath = if (mutate) {
            samples.resolve("src/main/java/fixture/Sample01.java").toString()
        } else {
            ""
        }
        MigrationFiles.writeText(
            wrapper,
            "#!/bin/sh\n" +
                "\"$javac\" \"\$@\"\n" +
                "result=\$?\n" +
                "if [ \"\$result\" -eq 0 ] && [ \"\$1\" = \"--release\" ]; then\n" +
                "  printf 'x\\n' >> \"$counter\"\n" +
                "  if [ \"\$(wc -l < \"$counter\")\" -eq 2 ] && [ -n \"$mutatePath\" ]; then\n" +
                "    printf '\\n' >> \"$mutatePath\"\n" +
                "  fi\n" +
                "fi\n" +
                "exit \"\$result\"\n",
        )
        wrapper.toFile().setExecutable(true)
        return runner.runAll(
            samples, resolvedRoot, work.resolve("staged"), work.resolve("instrumentation"),
            output, wrapper, defaultJava(), work.resolve("jdk"),
            "localhost/dyn4k-migration:missing-test-image", 180.0,
        )
    }

    /** Reads a written receipt with the fixture root replaced by the vector's placeholder. */
    fun normaliseText(path: Path, compiler: Path = javac): String =
        MigrationFiles.readTextOrEmpty(path)
            .replace(compiler.toString(), "<javac>")
            .replace(work.toString(), "<work>")

    /** Replaces the fixture root and compiler path with the vector's placeholders. */
    fun normalise(value: PyValue, compiler: Path = javac): PyValue {
        val replaced = replaceStrings(value) {
            it.replace(compiler.toString(), "<javac>").replace(work.toString(), "<work>")
        }
        return if (replaced is PyValue.Map && replaced.entries.containsKey("javac_version")) {
            PyValue.Map(LinkedHashMap(replaced.entries).apply { put("javac_version", pyText("<version>")) })
        } else {
            replaced
        }
    }

    override fun close() {
        deleteTree(work)
    }
}

private fun replaceStrings(value: PyValue, transform: (String) -> String): PyValue = when (value) {
    is PyValue.Text -> pyText(transform(value.value))
    is PyValue.Seq -> pyList(value.items.map { replaceStrings(it, transform) })
    is PyValue.Map -> PyValue.Map(
        LinkedHashMap(value.entries.mapValues { replaceStrings(it.value, transform) }),
    )
    else -> value
}

private fun gitRepo(root: Path, files: Map<String, ByteArray>): String {
    Files.createDirectories(root)
    Processes.run(listOf("git", "init", "-q", root.toString()), environment = gitEnvironment, check = true)
    for ((relative, bytes) in files) MigrationFiles.writeBytes(root.resolve(relative), bytes)
    Processes.run(listOf("git", "-C", root.toString(), "add", "."), environment = gitEnvironment, check = true)
    Processes.run(
        listOf(
            "git", "-C", root.toString(), "-c", "user.name=t",
            "-c", "user.email=t@example.invalid", "commit", "-qm", "fixture",
        ),
        environment = gitEnvironment,
        check = true,
    )
    return readGit(root, "rev-parse", "HEAD")
}

private fun readGit(root: Path, vararg arguments: String): String =
    Processes.run(listOf("git", "-C", root.toString(), *arguments), check = true).stdout.trim()

private val gitEnvironment = mapOf(
    "GIT_AUTHOR_NAME" to "t",
    "GIT_AUTHOR_EMAIL" to "t@example.invalid",
    "GIT_COMMITTER_NAME" to "t",
    "GIT_COMMITTER_EMAIL" to "t@example.invalid",
    "GIT_AUTHOR_DATE" to "2020-01-01T00:00:00 +0000",
    "GIT_COMMITTER_DATE" to "2020-01-01T00:00:00 +0000",
)

private fun copyTree(source: Path, target: Path) {
    Files.walk(source).use { stream ->
        stream.forEach { path ->
            val relative = source.relativize(path)
            val destination = if (relative.toString().isEmpty()) target else target.resolve(relative.toString())
            if (Files.isDirectory(path)) {
                Files.createDirectories(destination)
            } else {
                destination.parent?.let { Files.createDirectories(it) }
                Files.copy(path, destination)
            }
        }
    }
}

private fun okRecord(name: String): PyValue =
    VectorData.section("journeys").get(name).get("ok")

private fun errorRecord(name: String): String =
    (VectorData.section("journeys").get(name).get("error") as PyValue.Text).value
