package io.github.rubixhacker.harness.qualification

import de.infix.testBalloon.framework.core.testSuite
import io.github.rubixhacker.harness.contract.Qualification
import io.github.rubixhacker.harness.contract.StrictJson
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.StandardCopyOption
import java.util.concurrent.TimeUnit
import kotlin.io.path.writeText
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

/**
 * `tools/qualification/artifact.py`: the staged capture, both bundle builders, the bundle
 * verifier, the Ubuntu runtime rule, and the command line.
 *
 * The fixtures are recorded by the Python reference (see
 * `parity/generate_artifact_vectors.py`): a real staged publication and a complete `jsSafari`
 * hosted input tree whose report timestamps are fixed, so the bundle `stage_hosted` writes can be
 * compared byte for byte with the reference's own `verification.json`. No hosted runner, Ubuntu
 * runner, or publication ever ran here.
 */
val ArtifactCaptureContract by testSuite {
    // ------------------------------------------------------------------------------------
    // capture_staging
    // ------------------------------------------------------------------------------------

    test("capture_staging reproduces the reference staged publication") {
        Fixture.extract("valid.zip").use { fixture ->
            withArtifactTemp { root ->
                val destination = root.resolve("capture")
                Files.createDirectories(destination)
                val captured = ArtifactCapture.captureStaging(
                    fixture.root,
                    destination,
                    listOf("jvm", "js"),
                    ArtifactVectors.CANDIDATE,
                )
                val vector = ArtifactVectors.CAPTURE
                assertEquals(vector.gav, captured.gav)
                assertEquals(
                    vector.files,
                    captured.files.map { Py.str(it["path"])!! to Py.str(it["sha256"])!! },
                )
                assertEquals(
                    vector.hashes,
                    captured.hashes.mapValues { (_, value) ->
                        value.mapValues { (module, digest) -> Py.str(digest)!! }
                            .also { assertEquals(Qualification.modules.toSet(), value.keys) }
                    }.mapValues { (_, value) -> value.filterKeys { it in Qualification.modules } },
                )
                assertEquals(
                    FullCorpus.canonicalDigest(StrictJson.load(vector.contract)),
                    FullCorpus.canonicalDigest(captured.contentContract),
                )
                assertTrue(Files.isRegularFile(destination.resolve("LICENSE.md")))
                assertTrue(Files.isDirectory(destination.resolve("staged")))
            }
        }
    }

    test("capture_staging rejects a missing descriptor, a changed checksum, and changed metadata") {
        for ((label, mutate, message) in listOf<Triple<String, (Path) -> Unit, String>>(
            Triple("missing descriptor", { repository: Path ->
                Files.delete(
                    repository.resolve(
                        "build/staging-repository/io/github/rubixhacker/dyn4k-core-jvm/" +
                            "${Qualification.VERSION}/dyn4k-core-jvm-${Qualification.VERSION}-sources.jar",
                    ),
                )
            }, "staged GAV descriptor missing"),
            Triple("changed checksum", { repository: Path ->
                val sidecar = repository.resolve(
                    "build/staging-repository/io/github/rubixhacker/dyn4k/" +
                        "${Qualification.VERSION}/dyn4k-${Qualification.VERSION}.pom.sha256",
                )
                sidecar.writeText("0".repeat(64) + "\n")
            }, "staged checksum differs"),
            Triple("changed metadata", { repository: Path ->
                val metadata = repository.resolve(
                    "build/staging-repository/io/github/rubixhacker/dyn4k/" +
                        "${Qualification.VERSION}/dyn4k-${Qualification.VERSION}.module",
                )
                val parsed = StrictJson.load(Files.readString(metadata)) as JsonObject
                val component = parsed["component"] as JsonObject
                metadata.writeText(
                    JsonObject(
                        parsed + (
                            "component" to JsonObject(
                                component + ("version" to JsonPrimitive("9.9.9")),
                            )
                            ),
                    ).toString(),
                )
            }, "staged Gradle metadata version differs"),
        )) {
            Fixture.extract("valid.zip").use { fixture ->
                withArtifactTemp { root ->
                    mutate(fixture.root)
                    val destination = root.resolve("capture-$label")
                    Files.createDirectories(destination)
                    val error = assertFailsWith<IllegalArgumentException>(label) {
                        ArtifactCapture.captureStaging(
                            fixture.root,
                            destination,
                            listOf("jvm", "js"),
                            ArtifactVectors.CANDIDATE,
                        )
                    }
                    assertTrue(message in (error.message ?: ""), "$label: ${error.message}")
                }
            }
        }
    }

    // ------------------------------------------------------------------------------------
    // stage_hosted
    // ------------------------------------------------------------------------------------

    test("stage_hosted reproduces the reference verification byte for byte") {
        hostedFixture { repository, workspace ->
            val destination = workspace.resolve("bundle")
            val result = ArtifactCapture.stageHosted(
                repository,
                manifest(),
                ArtifactVectors.CANDIDATE,
                ArtifactVectors.HOSTED_TARGET,
                repository.resolve("hosted-jsSafari.json"),
                repository.resolve("matrix-jsSafari.json"),
                destination,
            )
            val vector = ArtifactVectors.STAGED
            assertEquals(vector.status, Py.str(result["status"]))
            assertEquals(vector.executed.toLong(), Py.int(result["executed"]!!))
            assertEquals(vector.expected.toLong(), Py.int(result["expected"]!!))
            assertEquals(vector.reported.toLong(), Py.int(result["reported"]!!))
            assertEquals(
                vector.groups,
                (result["groups"] as JsonObject).mapValues { Py.int(it.value).toInt() },
            )
            assertEquals(
                vector.reportedGroups,
                (result["reported_groups"] as JsonObject).mapValues { Py.int(it.value).toInt() },
            )
            assertEquals(vector.gav, (result["gav"] as JsonArray).mapNotNull { Py.str(it) })
            assertEquals(vector.verificationJson, Files.readString(destination.resolve("verification.json")))
            val verified = ArtifactCapture.verifyBundle(
                destination,
                manifest(),
                ArtifactVectors.CANDIDATE,
            )
            assertEquals(ArtifactVectors.VERIFIED_EXECUTED.toLong(), Py.int(verified["executed"]!!))

            val matrix = destination.resolve("json/matrix-jsSafari.json")
            val matrixBytes = Files.readAllBytes(matrix)
            Files.delete(matrix)
            assertEquals(
                ArtifactVectors.VERIFIED_WITHOUT_MATRIX,
                assertFailsWith<IllegalArgumentException> {
                    ArtifactCapture.verifyBundle(
                        destination,
                        manifest(),
                        ArtifactVectors.CANDIDATE,
                    )
                }.message,
            )
            ArtifactCapture.verifyBundle(
                destination,
                manifest(),
                ArtifactVectors.CANDIDATE,
                requireMatrix = false,
            )
            Files.write(matrix, matrixBytes)
            ArtifactCapture.verifyBundle(destination, manifest(), ArtifactVectors.CANDIDATE)
        }
    }

    test("stage_hosted records a missing report group and a non-passing probe") {
        val manifest = manifest()
        hostedFixture { repository, workspace ->
            val xml = repository.resolve(
                "consumers/qualification/portable/build/test-results/jsBrowserTest",
            )
            val saved = Files.walk(xml).use { stream -> stream.filter { Files.isRegularFile(it) }.toList() }
                .map { it to Files.readAllBytes(it) }
            for ((path, _) in saved) Files.delete(path)
            val missing = ArtifactCapture.stageHosted(
                repository,
                manifest,
                ArtifactVectors.CANDIDATE,
                ArtifactVectors.HOSTED_TARGET,
                repository.resolve("hosted-jsSafari.json"),
                null,
                workspace.resolve("bundle-missing"),
            )
            assertEquals("PROBE_FAILED", Py.str(missing["status"]))
            assertTrue("consumer-jsSafari" in (Py.str(missing["reason"]) ?: ""))
            for ((path, bytes) in saved) Files.write(path, bytes)
        }
        hostedFixture { repository, workspace ->
            val probePath = repository.resolve("hosted-jsSafari.json")
            val probe = StrictJson.load(Files.readString(probePath)) as JsonObject
            probePath.writeText(
                JsonObject(
                    (probe + ("status" to JsonPrimitive("UNAVAILABLE"))) +
                        ("reason" to JsonPrimitive("runner is unavailable")),
                ).toString(),
            )
            val unavailable = ArtifactCapture.stageHosted(
                repository,
                manifest,
                ArtifactVectors.CANDIDATE,
                ArtifactVectors.HOSTED_TARGET,
                probePath,
                null,
                workspace.resolve("bundle-unavailable"),
            )
            assertEquals("UNAVAILABLE", Py.str(unavailable["status"]))
            assertEquals("runner is unavailable", Py.str(unavailable["reason"]))
        }
        hostedFixture { repository, workspace ->
            val probePath = repository.resolve("hosted-jsSafari.json")
            probePath.writeText(
                JsonObject(
                    (StrictJson.load(Files.readString(probePath)) as JsonObject) +
                        ("candidate_sha" to JsonPrimitive("b".repeat(40))),
                ).toString(),
            )
            val stale = ArtifactCapture.stageHosted(
                repository,
                manifest,
                ArtifactVectors.CANDIDATE,
                ArtifactVectors.HOSTED_TARGET,
                probePath,
                null,
                workspace.resolve("bundle-stale"),
            )
            assertEquals("PROBE_FAILED", Py.str(stale["status"]))
            assertTrue("candidate" in (Py.str(stale["reason"]) ?: ""))
        }
    }

    // ------------------------------------------------------------------------------------
    // verify_bundle
    // ------------------------------------------------------------------------------------

    test("verify_bundle rejects a bundle that disagrees with its own bytes") {
        val manifest = manifest()
        stagedBundle(manifest) { bundle ->
            // A Windows-style inventory is still one path.
            val inventoryPath = bundle.resolve("verification.json")
            val inventoryBytes = Files.readAllBytes(inventoryPath)
            val windows = StrictJson.load(String(inventoryBytes)) as JsonObject
            inventoryPath.writeText(
                JsonObject(
                    windows + (
                        "files" to JsonArray(
                            (windows["files"] as JsonArray).map { element ->
                                JsonObject(
                                    (element as JsonObject) + (
                                        "path" to JsonPrimitive(
                                            Py.str(element["path"])!!.replace("/", "\\"),
                                        )
                                        ),
                                )
                            },
                        )
                        ) + (
                        "staged_files" to JsonArray(
                            (windows["staged_files"] as JsonArray).map { element ->
                                JsonObject(
                                    (element as JsonObject) + (
                                        "path" to JsonPrimitive(
                                            Py.str(element["path"])!!.replace("/", "\\"),
                                        )
                                        ),
                                )
                            },
                        )
                        ),
                ).toString(),
            )
            ArtifactCapture.verifyBundle(bundle, manifest, ArtifactVectors.CANDIDATE)

            fun expect(label: String, mutation: () -> Unit, message: String) {
                val restored = Files.readAllBytes(inventoryPath)
                try {
                    mutation()
                    val error = assertFailsWith<IllegalArgumentException>(label) {
                        ArtifactCapture.verifyBundle(bundle, manifest, ArtifactVectors.CANDIDATE)
                    }
                    assertTrue(message in (error.message ?: ""), "$label: ${error.message}")
                } finally {
                    Files.write(inventoryPath, restored)
                }
            }

            val unnormalized = StrictJson.load(String(Files.readAllBytes(inventoryPath))) as JsonObject
            expect("unsafe inventory", {
                inventoryPath.writeText(
                    JsonObject(
                        unnormalized + (
                            "files" to JsonArray(
                                (unnormalized["files"] as JsonArray).mapIndexed { index, element ->
                                    if (index == 0) {
                                        JsonObject(
                                            (element as JsonObject) + (
                                                "path" to JsonPrimitive("..\\outside.xml")
                                                ),
                                        )
                                    } else {
                                        element
                                    }
                                },
                            )
                            ),
                    ).toString(),
                )
            }, "bundle inventory path is unsafe")
            expect("counts", {
                inventoryPath.writeText(
                    JsonObject(
                        unnormalized + ("executed" to JsonPrimitive(4)),
                    ).toString(),
                )
            }, "bundle counts differ from raw XML")
            expect("stale report", {
                inventoryPath.writeText(
                    JsonObject(
                        unnormalized + (
                            "files" to JsonArray(
                                (unnormalized["files"] as JsonArray).mapIndexed { index, element ->
                                    if (index == 0) {
                                        JsonObject(
                                            (element as JsonObject) + (
                                                "mtime_ns" to JsonPrimitive(1)
                                                ),
                                        )
                                    } else {
                                        element
                                    }
                                },
                            )
                            ),
                    ).toString(),
                )
            }, "stale report")
            expect("unlisted XML", {
                val extra = bundle.resolve("xml/extra.xml")
                extra.parent?.let { Files.createDirectories(it) }
                Files.writeString(
                    extra,
                    """<testsuite tests="0" failures="0" errors="0" skipped="0" time="0.1"/>""",
                )
            }, "bundle contains unlisted XML")
        }
    }

    test("verify_bundle rejects a changed staged descriptor, binary, and matrix") {
        val manifest = manifest()
        stagedBundle(manifest) { bundle ->
            val pom = Files.walk(bundle.resolve("staged")).use { stream ->
                stream.filter { it.fileName.toString().endsWith(".pom") }.findFirst().orElseThrow()
            }
            val pomBytes = Files.readAllBytes(pom)
            Files.write(pom, pomBytes + " ".toByteArray())
            assertEquals(
                "staged GAV descriptor or checksum differs from bundle",
                assertFailsWith<IllegalArgumentException> {
                    ArtifactCapture.verifyBundle(bundle, manifest, ArtifactVectors.CANDIDATE)
                }.message,
            )
            Files.write(pom, pomBytes)

            val sidecar = bundle.resolve(
                "staged/${Qualification.targetBinaryPath("dyn4k-core", "js")}.sha256",
            )
            val sidecarBytes = Files.readAllBytes(sidecar)
            sidecar.writeText("f".repeat(64) + "\n")
            val fabricated = assertFailsWith<IllegalArgumentException> {
                ArtifactCapture.verifyBundle(bundle, manifest, ArtifactVectors.CANDIDATE)
            }
            assertTrue(
                "staged binary checksum" in (fabricated.message ?: "") ||
                    "staged GAV descriptor" in (fabricated.message ?: ""),
                fabricated.message,
            )
            Files.write(sidecar, sidecarBytes)

            val matrixPath = bundle.resolve("json/matrix-jsSafari.json")
            val matrixBytes = Files.readAllBytes(matrixPath)
            val matrix = StrictJson.load(String(matrixBytes)) as JsonObject
            val lanes = matrix["lanes"] as JsonArray
            val mutations = listOf<Triple<String, (MutableMap<String, JsonElement>) -> Unit, String>>(
                Triple("duplicate lane", { changed ->
                    val items = (changed.getValue("lanes") as JsonArray).toMutableList()
                    items[1] = items[0]
                    changed["lanes"] = JsonArray(items)
                }, "bundle matrix lane IDs are missing, duplicate, or unknown"),
                Triple("unknown lane", { changed ->
                    val items = (changed.getValue("lanes") as JsonArray).toMutableList()
                    items[1] = JsonObject(
                        (items[1] as JsonObject) + (
                            "id" to JsonPrimitive("unknown:runtime:minimum:default")
                            ),
                    )
                    changed["lanes"] = JsonArray(items)
                }, "bundle matrix lane IDs are missing, duplicate, or unknown"),
                Triple("contradictory counts", { changed ->
                    changed["counts"] = buildJsonObject {
                        put("PASSED", JsonPrimitive(1))
                        put("FAILED", JsonPrimitive(0))
                        put("UNAVAILABLE", JsonPrimitive(0))
                        put("NOT_RUN", JsonPrimitive(111))
                    }
                }, "bundle matrix counts differ from lane records"),
                Triple("bounded observation", { changed ->
                    changed["bounded_hosted_probes"] = JsonArray(
                        (changed.getValue("bounded_hosted_probes") as JsonArray).map { element ->
                            JsonObject(
                                (element as JsonObject) + (
                                    "reason" to JsonPrimitive("other observation")
                                    ),
                            )
                        },
                    )
                }, "bundle matrix bounded observation differs from hosted probe"),
                Triple("lane set", { changed ->
                    changed["lanes"] = JsonArray(emptyList())
                }, "bundle matrix lane set is incomplete"),
            )
            for ((label, change, message) in mutations) {
                val changed = LinkedHashMap<String, JsonElement>(matrix)
                change(changed)
                matrixPath.writeText(JsonObject(changed).toString())
                val error = assertFailsWith<IllegalArgumentException>(label) {
                    ArtifactCapture.verifyBundle(bundle, manifest, ArtifactVectors.CANDIDATE)
                }
                assertTrue(message in (error.message ?: ""), "$label: ${error.message}")
                Files.write(matrixPath, matrixBytes)
            }
            assertEquals(112, lanes.size)
        }
    }

    test("verify_bundle rejects an unknown route, a failed top probe, and a changed runtime") {
        val manifest = manifest()
        stagedBundle(manifest) { bundle ->
            val summaryPath = bundle.resolve("verification.json")
            val summaryBytes = Files.readAllBytes(summaryPath)
            val summary = StrictJson.load(String(summaryBytes)) as JsonObject
            summaryPath.writeText(
                JsonObject(summary + ("route" to JsonPrimitive("linuxX64"))).toString(),
            )
            assertEquals(
                "unknown bundle route",
                assertFailsWith<IllegalArgumentException> {
                    ArtifactCapture.verifyBundle(bundle, manifest, ArtifactVectors.CANDIDATE)
                }.message,
            )
            summaryPath.writeText(
                JsonObject(summary + ("runtime" to JsonPrimitive("other"))).toString(),
            )
            assertEquals(
                "bundle runtime differs from hosted observation",
                assertFailsWith<IllegalArgumentException> {
                    ArtifactCapture.verifyBundle(bundle, manifest, ArtifactVectors.CANDIDATE)
                }.message,
            )
            summaryPath.writeText(
                JsonObject(
                    (summary + ("status" to JsonPrimitive("PROBE_FAILED"))) +
                        ("reason" to JsonPrimitive("source probe failed")),
                ).toString(),
            )
            assertEquals(
                "source probe failed",
                assertFailsWith<IllegalArgumentException> {
                    ArtifactCapture.verifyBundle(bundle, manifest, ArtifactVectors.CANDIDATE)
                }.message,
            )
            Files.write(summaryPath, summaryBytes)

            val topPath = bundle.resolve("json/hosted-jsSafari.json")
            val topBytes = Files.readAllBytes(topPath)
            val top = StrictJson.load(String(topBytes)) as JsonObject
            topPath.writeText(
                JsonObject(
                    (top + ("status" to JsonPrimitive("PROBE_FAILED"))) +
                        ("reason" to JsonPrimitive("source probe failed")),
                ).toString(),
            )
            val error = assertFailsWith<IllegalArgumentException> {
                ArtifactCapture.verifyBundle(bundle, manifest, ArtifactVectors.CANDIDATE)
            }
            assertTrue("PROBE_FAILED" in (error.message ?: ""), error.message)
            Files.write(topPath, topBytes)
        }
    }

    test("verify_bundle rejects a bundle whose Ubuntu runtime is not the runner") {
        withArtifactTemp { root ->
            root.resolve("verification.json").writeText(
                buildJsonObject {
                    put("candidate_sha", JsonPrimitive(ArtifactVectors.CANDIDATE))
                    put("status", JsonPrimitive("PROBE_PASSED"))
                    put("route", JsonPrimitive("ubuntu-host"))
                    put(
                        "runtime",
                        buildJsonObject {
                            put("system", JsonPrimitive("Windows"))
                            put("machine", JsonPrimitive("AMD64"))
                        },
                    )
                }.toString(),
            )
            assertEquals(
                "Ubuntu bundle runtime identity is incomplete or wrong",
                assertFailsWith<IllegalArgumentException> {
                    ArtifactCapture.verifyBundle(
                        root,
                        manifest(),
                        ArtifactVectors.CANDIDATE,
                    )
                }.message,
            )
        }
    }

    // ------------------------------------------------------------------------------------
    // verify_full_hosted
    // ------------------------------------------------------------------------------------

    test("verify_full_hosted rejects a non-object receipt in a directory and in a tar") {
        withArtifactTemp { root ->
            val bundle = root.resolve("bundle")
            Files.createDirectories(bundle)
            bundle.resolve("receipt.json").writeText("[]")
            assertEquals(
                "full hosted receipt must be an object",
                assertFailsWith<IllegalArgumentException> {
                    ArtifactCapture.verifyFullHosted(bundle, "a".repeat(40), root)
                }.message,
            )
            val archive = root.resolve("bundle.tar")
            FullHosted.packageArchive(bundle, archive)
            assertEquals(
                "full hosted receipt must be an object",
                assertFailsWith<IllegalArgumentException> {
                    ArtifactCapture.verifyFullHosted(archive, "a".repeat(40), root)
                }.message,
            )
            val notATar = root.resolve("bundle.zip")
            Files.writeString(notATar, "not a tar")
            assertEquals(
                "full hosted bundle must be a directory or transport tar",
                assertFailsWith<IllegalArgumentException> {
                    ArtifactCapture.verifyFullHosted(notATar, "a".repeat(40), root)
                }.message,
            )
        }
    }

    // ------------------------------------------------------------------------------------
    // Ubuntu runtime
    // ------------------------------------------------------------------------------------

    test("check_ubuntu_runtime matches the reference") {
        for (vector in ArtifactVectors.UBUNTU_RUNTIME_CASES) {
            val runtime = StrictJson.load(vector.runtime) as JsonObject
            if (vector.error == null) {
                ArtifactRules.checkUbuntuRuntime(runtime)
            } else {
                assertEquals(
                    vector.error,
                    assertFailsWith<IllegalArgumentException>(vector.label) {
                        ArtifactRules.checkUbuntuRuntime(runtime)
                    }.message,
                    vector.label,
                )
            }
        }
        assertEquals(ArtifactVectors.UBUNTU_PROBES, ArtifactRules.UBUNTU_PROBES)
    }

    test("ubuntu_runtime records the host identity in the reference order") {
        val host = object : HostEnvironment {
            override fun system(): String = "Linux"
            override fun machine(): String = "x86_64"
            override fun platformVersion(): String = "#1 SMP"
            override fun environment(name: String): String? = when (name) {
                "ImageOS" -> "ubuntu24"
                "ImageVersion" -> "20250801.1.0"
                "GITHUB_ACTIONS" -> "true"
                else -> null
            }
            override fun run(command: List<String>): HostedCapture =
                if (command == listOf("uname", "-r")) {
                    HostedCapture(0, "6.8.0-45-generic\n", "")
                } else {
                    HostedCapture(
                        0,
                        "openjdk version \"21.0.8\" 2025-07-15\n",
                        "",
                    )
                }
        }
        val runtime = ArtifactCapture.ubuntuRuntime(host) {
            ArtifactRules.parseOsRelease(
                listOf(
                    "NAME=\"Ubuntu\"",
                    "ID=ubuntu",
                    "VERSION_ID=\"24.04\"",
                    "# a comment",
                    "INVALID-KEY=x",
                ),
            )
        }
        assertEquals(
            listOf(
                "system", "machine", "kernel_release", "distribution", "os_version",
                "runner_image_os", "runner_image_version", "github_actions", "java_version",
            ),
            runtime.keys.toList(),
        )
        assertEquals("Linux", Py.str(runtime["system"]))
        assertEquals("6.8.0-45-generic", Py.str(runtime["kernel_release"]))
        assertEquals("ubuntu", Py.str(runtime["distribution"]))
        assertEquals("24.04", Py.str(runtime["os_version"]))
        assertEquals(true, Py.truthy(runtime["github_actions"]))
        assertEquals("21.0.8", Py.str(runtime["java_version"]))
        ArtifactRules.checkUbuntuRuntime(runtime)
    }

    test("stage_ubuntu records a rejected runtime and missing evidence") {
        hostedFixture { repository, workspace ->
            val windows = buildJsonObject {
                put("system", JsonPrimitive("Windows"))
                put("machine", JsonPrimitive("AMD64"))
                put("kernel_release", JsonPrimitive("10.0"))
                put("distribution", JsonPrimitive("windows"))
                put("os_version", JsonPrimitive("2025"))
                put("runner_image_os", JsonPrimitive(""))
                put("runner_image_version", JsonPrimitive(""))
                put("github_actions", JsonPrimitive(false))
                put("java_version", JsonPrimitive("21.0.8"))
            }
            val rejected = ArtifactCapture.stageUbuntu(
                repository,
                manifest(),
                ArtifactVectors.CANDIDATE,
                repository,
                workspace.resolve("ubuntu-rejected"),
                windows,
            )
            assertEquals("PROBE_FAILED", Py.str(rejected["status"]))
            assertTrue(
                "Ubuntu bundle runtime identity" in (Py.str(rejected["reason"]) ?: ""),
                Py.str(rejected["reason"]) ?: "",
            )
            assertTrue(Files.isRegularFile(workspace.resolve("ubuntu-rejected/verification.json")))
            val linux = buildJsonObject {
                put("system", JsonPrimitive("Linux"))
                put("machine", JsonPrimitive("x86_64"))
                put("kernel_release", JsonPrimitive("6.8.0"))
                put("distribution", JsonPrimitive("ubuntu"))
                put("os_version", JsonPrimitive("24.04"))
                put("runner_image_os", JsonPrimitive(""))
                put("runner_image_version", JsonPrimitive(""))
                put("github_actions", JsonPrimitive(false))
                put("java_version", JsonPrimitive("21.0.8"))
            }
            val missing = ArtifactCapture.stageUbuntu(
                repository,
                manifest(),
                ArtifactVectors.CANDIDATE,
                repository,
                workspace.resolve("ubuntu-missing"),
                linux,
            )
            assertEquals("PROBE_FAILED", Py.str(missing["status"]))
            assertTrue(
                "missing evidence JSON" in (Py.str(missing["reason"]) ?: ""),
                Py.str(missing["reason"]) ?: "",
            )
        }
    }

    // ------------------------------------------------------------------------------------
    // The command line
    // ------------------------------------------------------------------------------------

    test("the artifact command line reproduces each mode") {
        withArtifactTemp { root ->
            val repository = root.resolve("repository")
            Files.createDirectories(repository)
            hostedGit(repository, "init", "-q")
            repository.resolve("README.md").writeText("Artifact CLI fixture.\n")
            hostedGit(repository, "add", "README.md")
            hostedGit(
                repository, "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                "commit", "-qm", "base",
            )
            val sha = hostedGit(repository, "rev-parse", "HEAD").trim()
            assertEquals(2, ArtifactCli.run(arrayOf("--candidate-sha", sha, "--output", "$root"), repository))
            assertEquals(
                2,
                ArtifactCli.run(arrayOf("nonsense", "--candidate-sha", sha, "--output", "$root"), repository),
            )
            assertEquals(2, ArtifactCli.run(arrayOf("verify", "--output", "$root"), repository))
            assertEquals(2, ArtifactCli.run(arrayOf("hosted", "--candidate-sha", sha), repository))
            assertEquals(
                2,
                ArtifactCli.run(
                    arrayOf(
                        "hosted", "--candidate-sha", sha, "--output", "$root", "--full-hosted",
                    ),
                    repository,
                ),
            )
            // A directory carrying a receipt is verified as a hosted archive.
            val receiptDir = root.resolve("receipt")
            Files.createDirectories(receiptDir)
            receiptDir.resolve("receipt.json").writeText(
                """{"status":"FULL_COMMON_PASSED","target":"jsSafari","configurations":[]}""",
            )
            assertEquals(
                1,
                ArtifactCli.run(
                    arrayOf("verify", "--candidate-sha", sha, "--output", "$receiptDir"),
                    repository,
                ),
            )
            // A dirty checkout cannot sign evidence.
            repository.resolve("README.md").writeText("changed\n")
            assertFailsWith<IllegalArgumentException> {
                ArtifactCli.run(arrayOf("verify", "--candidate-sha", sha, "--output", "$root"), repository)
            }
        }
    }
}

// ----------------------------------------------------------------------------------------
// Fixtures
// ----------------------------------------------------------------------------------------

private fun withArtifactTemp(block: (Path) -> Unit) {
    val root = Files.createTempDirectory("artifact-suite")
    try {
        block(root)
    } finally {
        Files.walk(root).use { walk ->
            walk.sorted(Comparator.reverseOrder()).forEach { Files.deleteIfExists(it) }
        }
    }
}

private fun manifest(): JsonObject = StrictJson.load(
    Files.readString(repositoryRoot().resolve("tools/qualification/foundation-probes.json")),
) as JsonObject

/**
 * Extract the recorded hosted input tree, then pin every report timestamp.
 *
 * The reference staged this tree with the same fixed timestamps, so `verification.json` is
 * comparable byte for byte.
 */
private fun hostedFixture(block: (Path, Path) -> Unit) {
    Fixture.extract(ArtifactVectors.SOURCE_FIXTURE).use { fixture ->
        val repository = fixture.root
        val workspace = Files.createTempDirectory("artifact-workspace")
        Files.walk(repository).use { walk ->
            for (path in walk) {
                if (Files.isRegularFile(path) && path.fileName.toString().endsWith(".xml")) {
                    Files.setLastModifiedTime(
                        path,
                        java.nio.file.attribute.FileTime.from(
                            ArtifactVectors.XML_MTIME_NS,
                            TimeUnit.NANOSECONDS,
                        ),
                    )
                }
            }
        }
        try {
            block(repository, workspace)
        } finally {
            Files.walk(workspace).use { walk ->
                walk.sorted(Comparator.reverseOrder()).forEach { Files.deleteIfExists(it) }
            }
        }
    }
}

/** Stage the recorded bundle once, then hand it to a test that mutates copies of it. */
private fun stagedBundle(manifest: JsonObject, block: (Path) -> Unit) {
    hostedFixture { repository, workspace ->
        val bundle = workspace.resolve("bundle")
        ArtifactCapture.stageHosted(
            repository,
            manifest,
            ArtifactVectors.CANDIDATE,
            ArtifactVectors.HOSTED_TARGET,
            repository.resolve("hosted-jsSafari.json"),
            repository.resolve("matrix-jsSafari.json"),
            bundle,
        )
        block(bundle)
    }
}
