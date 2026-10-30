package io.github.rubixhacker.harness.qualification

import de.infix.testBalloon.framework.core.testSuite
import io.github.rubixhacker.harness.contract.Qualification
import io.github.rubixhacker.harness.contract.StrictJson
import java.nio.file.Files
import java.nio.file.Path
import java.util.concurrent.TimeUnit
import kotlin.io.path.writeText
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import org.apache.commons.compress.archivers.tar.TarArchiveEntry
import org.apache.commons.compress.archivers.tar.TarArchiveOutputStream

/**
 * `tools/qualification/collection.py`: the artifact route table, the 112-lane ledger, the frozen
 * cross-run index, the signed external audit ingestion, and the workflow-text contract of the
 * central collection job.
 *
 * The three empty-collection documents are recorded by the Python reference at the candidate
 * revision (`parity/generate_collection_vectors.py`) and compared byte for byte. The workflow
 * assertions read the current `.github/workflows` files: no workflow was edited here.
 */
/** The tree object of the checked-out revision, which every receipt binds. */
private fun headTree(repository: java.nio.file.Path): String =
    hostedGit(repository, "rev-parse", "HEAD^{tree}").trim()

val CollectionContract by testSuite {
    test("an empty collection keeps all 112 lanes not run without a signature") {
        val repository = repositoryRoot()
        val head = hostedGit(repository, "rev-parse", "HEAD").trim()
        withCollectionTemp { root ->
            val output = root.resolve("collection")
            val report = CollectionRuntime.collect(repository, head, emptyList(), output)
            assertEquals("NOT_RUN", Py.str(report["status"]))
            assertEquals("MISSING", Py.str(report["independent_signature"]))
            assertEquals(112L, Py.int(report["required_lanes"]!!))
            assertEquals(
                setOf("full-ci", "full-common", "publication-ubuntu", "duplicate-provider"),
                (report["missing_artifacts"] as JsonArray).map { Py.str(it) }.toSet(),
            )
            assertEquals(
                listOf("duplicate-provider", "full-ci", "full-common", "publication-ubuntu"),
                (report["missing_artifacts"] as JsonArray).map { Py.str(it) },
            )
            assertEquals(
                listOf(
                    "all 112 exact-source common gate archives and runtime identities",
                    "independently audited archive digests and 21-target artifact hashes",
                    "complete candidate manifest bound to a verified staged audit",
                    "exact staged repository bytes available to the public qualifier",
                    "detached Ed25519 audit signature and pinned trusted public-key fingerprint",
                ),
                (report["external_inputs_required"] as JsonArray).map { Py.str(it) },
            )
            // The recorded documents embed the revision they were produced at. Those two
            // fields are the only revision-bound values, so they are normalised before the
            // byte comparison; everything else still has to match exactly.
            val tree = hostedGit(repository, "rev-parse", "HEAD^{tree}").trim()
            fun recorded(name: String): String = resourceText("collection/empty-$name")
                .replace(CollectionVectors.REVISION, head)
                .replace(CollectionVectors.SOURCE_TREE, tree)
            for (name in listOf(
                "collection.json", "assembly-inputs.json", "candidate-manifest-inputs.json",
            )) {
                assertEquals(recorded(name), Files.readString(output.resolve(name)), name)
            }
            val inputs = StrictJson.load(Files.readString(output.resolve("assembly-inputs.json")))
                as JsonObject
            assertEquals(112, inputs.size)
            assertTrue(
                inputs.values.all { it == buildJsonObject { put("archives", buildJsonObject { }) } },
            )
            assertTrue(CollectionRuntime.verifyCollection(repository, head, emptyList(), output))
            val candidate = StrictJson.load(
                Files.readString(output.resolve("candidate-manifest-inputs.json")),
            ) as JsonObject
            assertEquals("INCOMPLETE", Py.str(candidate["status"]))
            assertEquals(tree, Py.str(report["source_tree"]))
            val lanes = candidate["lanes"] as JsonObject
            val jvm = lanes.values.map { it as JsonObject }
                .filter { Py.str(it["target"]) == "jvm" }
            assertEquals(4, jvm.size)
            assertEquals(
                setOf("default", "no-optimize"),
                jvm.map { Py.str((it["jvm_mode_publication"] as JsonObject)["mode"]) }.toSet(),
            )
            assertTrue(jvm.all { Py.str(it["runtime_identity"]) == null })
            assertTrue(jvm.all { it["artifact_hashes"] is JsonNull })
        }
    }

    test("a staged audit does not assign one jvm pair to both modes") {
        val repository = repositoryRoot()
        val head = hostedGit(repository, "rev-parse", "HEAD").trim()
        withCollectionTemp { root ->
            val artifact = root.resolve("publication-$head-ubuntu")
            val receipt = artifact.resolve("fixture-publication")
            Files.createDirectories(receipt)
            val audit = buildJsonObject {
                put("candidate_sha", JsonPrimitive(head))
                put("status", JsonPrimitive("PASSED"))
                put(
                    "artifacts",
                    JsonArray(
                        listOf("jvm" to "a", "linuxX64" to "b").flatMap { (target, letter) ->
                            Qualification.modules.map { module ->
                                buildJsonObject {
                                    put(
                                        "path",
                                        JsonPrimitive(Qualification.targetBinaryPath(module, target)),
                                    )
                                    put("sha256", JsonPrimitive(letter.repeat(64)))
                                }
                            }
                        },
                    ),
                )
            }
            receipt.resolve("artifact-audit.json").writeText(audit.toString())
            val output = root.resolve("collected")
            CollectionRuntime.collect(
                repository,
                head,
                listOf(artifact.fileName.toString() to artifact.toString()),
                output,
                inspect = { _, _, _, _, _, _, _ -> "PRODUCER_VERIFIED" },
            )
            val candidate = StrictJson.load(
                Files.readString(output.resolve("candidate-manifest-inputs.json")),
            ) as JsonObject
            val lanes = (candidate["lanes"] as JsonObject).values.map { it as JsonObject }
            assertTrue(
                lanes.filter { Py.str(it["target"]) == "jvm" }
                    .all { it["artifact_hashes"] is JsonNull },
            )
            val linux = lanes.filter { Py.str(it["target"]) == "linuxX64" }
            assertEquals(4, linux.size)
            for (lane in linux) {
                val hashes = lane["artifact_hashes"] as JsonObject
                assertEquals(
                    Qualification.modules.toSet(),
                    hashes.keys,
                )
                assertTrue(hashes.values.all { Py.str(it) == "b".repeat(64) })
            }
        }
    }

    test("a wrong candidate and a duplicate route are failed and retained") {
        val repository = repositoryRoot()
        val head = hostedGit(repository, "rev-parse", "HEAD").trim()
        withCollectionTemp { root ->
            val wrong = CollectionVectors.OTHER_CANDIDATE
            val bad = root.resolve("full-ci-$wrong")
            Files.createDirectories(bad)
            bad.resolve("raw.log").writeText("failed exact-source producer\n")
            val result = CollectionRuntime.collect(
                repository,
                head,
                listOf(bad.fileName.toString() to bad.toString()),
                root.resolve("wrong"),
            )
            assertEquals("FAILED", Py.str(result["status"]))
            val row = (result["artifacts"] as JsonArray)[0] as JsonObject
            assertTrue("candidate" in (Py.str(row["reason"]) ?: ""))
            assertEquals(
                CollectionRuntime.digest(bad.resolve("raw.log")),
                Py.str((row["files"] as JsonObject)["raw.log"]),
            )
            assertTrue("full-ci" in (result["missing_artifacts"] as JsonArray).map { Py.str(it) })
            val first = root.resolve("first")
            val second = root.resolve("second")
            Files.createDirectories(first)
            Files.createDirectories(second)
            val name = "duplicate-provider-$head"
            val duplicated = CollectionRuntime.collect(
                repository,
                head,
                listOf(name to first.toString(), name to second.toString()),
                root.resolve("duplicate"),
            )
            assertEquals("FAILED", Py.str(duplicated["status"]))
            val secondRow = (duplicated["artifacts"] as JsonArray)[1] as JsonObject
            assertTrue(
                "duplicate producer artifact route" in (Py.str(secondRow["reason"]) ?: ""),
            )
        }
    }

    test("a forged pass cannot enter the unsigned map") {
        val repository = repositoryRoot()
        val head = hostedGit(repository, "rev-parse", "HEAD").trim()
        withCollectionTemp { root ->
            val artifact = root.resolve("duplicate-provider-$head")
            Files.createDirectories(artifact)
            artifact.resolve("receipt.json").writeText(
                buildJsonObject {
                    put("schema", JsonPrimitive(1))
                    put("candidate_sha", JsonPrimitive(head))
                    put("source_tree", JsonPrimitive(headTree(repository)))
                    put("status", JsonPrimitive("PASSED"))
                }.toString(),
            )
            val result = CollectionRuntime.collect(
                repository,
                head,
                listOf(artifact.fileName.toString() to artifact.toString()),
                root.resolve("collection"),
            )
            assertEquals("FAILED", Py.str(result["status"]))
            val row = (result["artifacts"] as JsonArray)[0] as JsonObject
            assertTrue("inventory" in (Py.str(row["reason"]) ?: ""))
            val inputs = StrictJson.load(
                Files.readString(root.resolve("collection/assembly-inputs.json")),
            ) as JsonObject
            assertEquals(
                buildJsonObject {
                    put("duplicate-provider", JsonPrimitive(artifact.toAbsolutePath().normalize().toString()))
                },
                (inputs["jvm:Java:current:default"] as JsonObject)["archives"],
            )
            assertTrue(
                inputs.filterKeys { it != "jvm:Java:current:default" }.values.all {
                    it == buildJsonObject { put("archives", buildJsonObject { }) }
                },
            )
        }
    }

    test("a missing external signature keeps audit ingestion not run") {
        val repository = repositoryRoot()
        val head = hostedGit(repository, "rev-parse", "HEAD").trim()
        withCollectionTemp { root ->
            val output = root.resolve("collection")
            CollectionRuntime.collect(repository, head, emptyList(), output)
            val external = root.resolve("external")
            Files.createDirectories(external)
            external.resolve("audit.json").writeText(
                buildJsonObject {
                    put("schema", JsonPrimitive(1))
                    put("candidate_sha", JsonPrimitive(head))
                    put("status", JsonPrimitive("PASSED"))
                }.toString(),
            )
            val result = CollectionRuntime.ingestExternal(
                repository,
                head,
                emptyList(),
                output,
                external,
                trustedKeySha256 = "a".repeat(64),
            )
            assertEquals("NOT_RUN", Py.str(result["status"]))
            assertTrue("audit.sig" in (result["missing_external_inputs"] as JsonArray).map { Py.str(it) })
            assertFalse(Files.exists(output.resolve("signed-runtime-matrix.json")))
        }
    }

    test("a retained failed route verifies until a raw file changes") {
        val repository = repositoryRoot()
        val head = hostedGit(repository, "rev-parse", "HEAD").trim()
        withCollectionTemp { root ->
            val artifact = root.resolve("duplicate-provider-$head")
            Files.createDirectories(artifact)
            val raw = artifact.resolve("task.log")
            raw.writeText("BUILD FAILED\n")
            val started = FullHostedRuntime.nowNs() - 1_000_000_000L
            val finished = FullHostedRuntime.nowNs() + 1_000_000_000L
            artifact.resolve("receipt.json").writeText(
                buildJsonObject {
                    put("schema", JsonPrimitive(1))
                    put("status", JsonPrimitive("FAILED"))
                    put("candidate_sha", JsonPrimitive(head))
                    put("source_tree", JsonPrimitive(headTree(repository)))
                    put(
                        "process",
                        buildJsonObject {
                            put(
                                "command",
                                JsonArray(
                                    listOf("./gradlew", "verifySingleProvider")
                                        .map { JsonPrimitive(it) },
                                ),
                            )
                            put("exit_code", JsonPrimitive(1))
                            put("started_ns", JsonPrimitive(started))
                            put("finished_ns", JsonPrimitive(finished))
                            put("stdout", JsonPrimitive("task.log"))
                        },
                    )
                    put(
                        "files",
                        JsonArray(
                            listOf(
                                buildJsonObject {
                                    put("path", JsonPrimitive("task.log"))
                                    put("sha256", JsonPrimitive(CollectionRuntime.digest(raw)))
                                    put(
                                        "mtime_ns",
                                        JsonPrimitive(
                                            Files.getLastModifiedTime(raw).to(TimeUnit.NANOSECONDS),
                                        ),
                                    )
                                },
                            ),
                        ),
                    )
                }.toString(),
            )
            val artifacts = listOf(artifact.fileName.toString() to artifact.toString())
            val output = root.resolve("collection")
            val result = CollectionRuntime.collect(repository, head, artifacts, output)
            assertEquals("FAILED", Py.str(result["status"]))
            val row = (result["artifacts"] as JsonArray)[0] as JsonObject
            assertNull(Py.str(row["reason"]))
            assertTrue(Files.isRegularFile(raw))
            assertTrue(CollectionRuntime.verifyCollection(repository, head, artifacts, output))
            raw.writeText("changed raw output\n")
            assertEquals(
                "collected raw artifact bytes differ: duplicate-provider-$head",
                assertFailsWith<IllegalArgumentException> {
                    CollectionRuntime.verifyCollection(repository, head, artifacts, output)
                }.message,
            )
            val changed = CollectionRuntime.collect(
                repository,
                head,
                artifacts,
                root.resolve("changed"),
            )
            assertTrue(
                "raw file hash differs" in
                    (Py.str(((changed["artifacts"] as JsonArray)[0] as JsonObject)["reason"]) ?: ""),
            )
        }
    }

    test("an altered transport archive is failed and retained") {
        val repository = repositoryRoot()
        val head = hostedGit(repository, "rev-parse", "HEAD").trim()
        withCollectionTemp { root ->
            val artifact = root.resolve("full-ci-$head")
            Files.createDirectories(artifact)
            val packed = artifact.resolve("full-ci-$head.tar.gz")
            TarArchiveOutputStream(Files.newOutputStream(packed)).use { archive ->
                archive.finish()
            }
            artifact.resolve("full-ci-$head.sha256").writeText(
                CollectionRuntime.digest(packed) + "  " + packed.fileName + "\n",
            )
            val artifacts = listOf(artifact.fileName.toString() to artifact.toString())
            val before = root.resolve("before")
            CollectionRuntime.collect(repository, head, artifacts, before)
            assertTrue(CollectionRuntime.verifyCollection(repository, head, artifacts, before))
            Files.write(packed, Files.readAllBytes(packed) + "altered".toByteArray())
            assertEquals(
                "collected raw artifact bytes differ: full-ci-$head",
                assertFailsWith<IllegalArgumentException> {
                    CollectionRuntime.verifyCollection(repository, head, artifacts, before)
                }.message,
            )
            val result = CollectionRuntime.collect(
                repository,
                head,
                artifacts,
                root.resolve("after"),
            )
            assertEquals("FAILED", Py.str(result["status"]))
            val row = (result["artifacts"] as JsonArray)[0] as JsonObject
            assertTrue("archive bytes differ" in (Py.str(row["reason"]) ?: ""))
            assertTrue(Files.isRegularFile(packed))
        }
    }

    // ------------------------------------------------------------------------------------
    // Workflow text contract of the central collection job
    // ------------------------------------------------------------------------------------

    test("the central collection workflow runs after the producers and retains raw results") {
        val workflow = Files.readString(
            repositoryRoot().resolve(".github/workflows/qualification.yml"),
        )
        assertManualQualificationTrigger(workflow)
        assertEquals(EXPECTED_CENTRAL_NEEDS, centralCollectionNeeds(workflow))
        val steps = centralCollectionSteps(workflow)

        fun namedStep(name: String): Pair<Int, String> {
            val matches = steps.withIndex().filter { (_, step) ->
                step.startsWith("      - name: $name\n")
            }
            assertEquals(1, matches.size, name)
            return matches[0].index to matches[0].value
        }

        val (downloadIndex, download) = namedStep("Download every retained producer artifact")
        val (collectIndex, collect) = namedStep("Collect and independently enumerate 112 lanes")
        val (uploadIndex, upload) = namedStep("Upload central raw collection and failed routes")
        assertEquals(0, downloadIndex)
        assertTrue(downloadIndex < collectIndex)
        assertEquals(collectIndex + 1, uploadIndex)
        assertTrue("        id: raw_download\n" in download)
        assertTrue("        if: always()\n" in download)
        assertTrue("        continue-on-error: true\n" in download)
        assertTrue("        uses: actions/download-artifact@v4\n" in download)
        assertTrue("          pattern: '*'\n" in download)
        assertTrue("          path: \${{ runner.temp }}/producer-artifacts\n" in download)
        assertTrue("          merge-multiple: false\n" in download)
        assertEquals(
            "      - name: Collect and independently enumerate 112 lanes\n" +
                "        if: always()\n" +
                "        env:\n" +
                "          DYN4K_DOWNLOAD_OUTCOME: \${{ steps.raw_download.outcome }}\n" +
                "          DYN4K_CROSS_RUN_ONLY: \${{ inputs.cross_run_only }}\n" +
                "          DYN4K_GITHUB_TOKEN: \${{ github.token }}\n" +
                "        run: |\n",
            collect.split("        run: |\n", limit = 2)[0] + "        run: |\n",
        )
        assertEquals(EXPECTED_CENTRAL_COMMANDS, centralCollectionCommands(collect))
        assertTrue("        if: always()\n" in upload)
        assertTrue("        uses: actions/upload-artifact@v4\n" in upload)
        assertTrue("          name: qualification-central-\${{ github.sha }}\n" in upload)
        for (path in listOf("central-collection/", "central-logs/", "producer-artifacts/")) {
            assertTrue("            \${{ runner.temp }}/$path\n" in upload)
        }
        assertTrue("          if-no-files-found: error\n" in upload)
        assertTrue("duplicate_provider.py" in workflow)
    }

    test("the central collection rejects inactive, bypassed, or reordered steps") {
        val workflow = Files.readString(
            repositoryRoot().resolve(".github/workflows/qualification.yml"),
        )
        val jobs = workflowJobs(workflow)
        val central = jobs.getValue("central-qualification-collection")
        val other = jobs.getValue("hosted-mac")
        val steps = centralCollectionSteps(workflow)
        val collectName = "Collect and independently enumerate 112 lanes"
        val verifyLine =
            "          ./gradlew -p tools/harness :qualification:collectQualification " +
                "--console=plain -q \\\n"

        fun rejects(altered: String, label: String) {
            val error = assertFailsWith<AssertionError>(label) {
                assertCentralCollectionContract(altered)
            }
            assertTrue((error.message ?: "").isNotEmpty())
        }

        val collectStep = steps.first { it.startsWith("      - name: $collectName\n") }
        val start = collectStep.indexOf(verifyLine)
        val end = collectStep.indexOf("          transport_exit=\$?\n", start)
        val command = collectStep.substring(start, end)
        rejects(
            workflow.replace(
                central,
                central.replace(
                    collectStep,
                    collectStep.replace(
                        command,
                        "          # ./gradlew -p tools/harness " +
                            ":qualification:collectQualification --console=plain -q\n",
                    ))),
            "commented verifier",
        )
        rejects(
            workflow.replace(
                central,
                central.replace(
                    collectStep,
                    collectStep.replace(
                        command,
                        "          echo skipped # ./gradlew -p tools/harness " +
                            ":qualification:collectQualification --console=plain -q\n",
                    ))),
            "no-op verifier",
        )
        val withoutCollect = central.replace(collectStep, "")
        rejects(
            workflow.replace(central, withoutCollect),
            "missing verifier",
        )
        val misplaced = workflow.replace(central, withoutCollect).replace(
            other,
            other.replace("    steps:\n", "    steps:\n" + collectStep))
        rejects(misplaced, "misplaced verifier")

        val downloadStep = steps.first {
            it.startsWith("      - name: Download every retained producer artifact\n")
        }
        val uploadStep = steps.first {
            it.startsWith("      - name: Upload central raw collection and failed routes\n")
        }
        rejects(
            workflow.replace(
                central,
                central.replace(downloadStep, "").replace(
                    collectStep,
                    collectStep + downloadStep)),
            "download after collect",
        )
        rejects(
            workflow.replace(
                central,
                central.replace(uploadStep, "").replace(
                    collectStep,
                    uploadStep + collectStep)),
            "upload before collect",
        )
        for ((label, replacements) in listOf(
            "early-success-exit" to listOf(
                "        run: |\n          set +e\n" to "        run: |\n          exit 0\n          set +e\n",
            ),
            "ignored-final-status" to listOf(
                "          test \"\$assembly_exit\" -eq 0 && test \"\$record_exit\" -eq 0\n" to
                    "          test \"\$assembly_exit\" -eq 0 && test \"\$record_exit\" -eq 0 || true\n",
            ),
            "stop-before-raw-results" to listOf("          set +e\n" to "          set -e\n"),
        ) + listOf("collection", "transport", "assembly", "record").map { name ->
            "overwrite-$name-exit" to listOf(
                "          ${name}_exit=\$?\n" to "          ${name}_exit=0\n",
            )
        }) {
            var changed = central
            for ((old, new) in replacements) {
                assertTrue(old in changed, "$label: $old")
                changed = changed.replace(old, new)
            }
            rejects(workflow.replace(central, changed), label)
        }
    }

    test("full qualification requires manual dispatch and the approved job needs") {
        val workflow = Files.readString(
            repositoryRoot().resolve(".github/workflows/qualification.yml"),
        )
        assertEquals(listOf("workflow_dispatch"), workflowEventBlocks(workflow).keys.toList())
        for (event in listOf("push", "pull_request", "schedule", "workflow_run")) {
            val altered = workflow.replace("on:\n", "on:\n  $event:\n")
            val error = assertFailsWith<AssertionError>(event) {
                assertManualQualificationTrigger(altered)
            }
            assertTrue("manual dispatch" in (error.message ?: ""))
        }
        val approvedBlock = "    needs:\n" +
            "      - staged-jvm-and-linux\n" +
            "      - hosted-publications\n" +
            "      - hosted-native\n"
        assertEquals(1, workflow.split(approvedBlock).size - 1)
        for (dependencies in listOf(
            listOf("staged-jvm-and-linux"),
            EXPECTED_CENTRAL_NEEDS + "safari-browser",
            listOf("staged-jvm-and-linux", "hosted-publications", "hosted-native", "wrong-producer"),
            EXPECTED_CENTRAL_NEEDS.reversed(),
        )) {
            val replacement = "    needs:\n" + dependencies.joinToString("") { "      - $it\n" }
            val altered = workflow.replace(approvedBlock, replacement)
            assertTrue(EXPECTED_CENTRAL_NEEDS != centralCollectionNeeds(altered))
        }
        val withoutNeeds = workflow.replace(approvedBlock, "")
        assertNull(centralCollectionNeeds(withoutNeeds))
        for (jobKey in listOf(
            "\"spare-diagnostic\":", "spare-diagnostic :", "spare-diagnostic: # diagnostic",
        )) {
            val later = withoutNeeds + "\n  $jobKey\n    needs:\n" +
                "      - staged-jvm-and-linux\n      - hosted-publications\n" +
                "      - hosted-native\n    runs-on: ubuntu-latest\n    steps:\n" +
                "      - run: true\n"
            assertNull(centralCollectionNeeds(later))
            val earlier = withoutNeeds.replace(
                "  central-qualification-collection:\n",
                "\n  $jobKey\n    needs:\n      - staged-jvm-and-linux\n" +
                    "      - hosted-publications\n      - hosted-native\n" +
                    "    runs-on: ubuntu-latest\n    steps:\n      - run: true\n" +
                    "  central-qualification-collection:\n")
            assertNull(centralCollectionNeeds(earlier))
        }
    }

    test("the workflow download survives a replay setup failure") {
        val workflow = Files.readString(
            repositoryRoot().resolve(".github/workflows/qualification.yml"),
        )
        val central = workflow.split("  central-qualification-collection:\n", limit = 2)[1]

        fun assertDownloadContract(job: String) {
            val download = job.indexOf("      - name: Download every retained producer artifact\n")
            val nextStep = job.indexOf("      - ", download + 1)
            val downloadStep = job.substring(download, nextStep)
            assertTrue("        if: always()\n" in downloadStep)
            assertTrue("        id: raw_download\n" in downloadStep)
            assertTrue("        continue-on-error: true\n" in downloadStep)
            for (fallible in listOf(
                "      - uses: actions/checkout@v4\n",
                "      - uses: actions/setup-java@v4\n",
                "      - uses: gradle/actions/setup-gradle@v4\n",
                "      - name: Provision pinned upstream source for raw replay\n",
            )) {
                assertTrue(download < job.indexOf(fallible), fallible)
            }
            assertTrue("DYN4K_DOWNLOAD_OUTCOME: \${{ steps.raw_download.outcome }}" in job)
            assertTrue("test \"\$DYN4K_DOWNLOAD_OUTCOME\" = success" in job)
            assertTrue("download=%s" in job)
            assertTrue("::error::Producer artifact download failed or was skipped" in job)
        }

        assertDownloadContract(central)
        val download = central.indexOf("      - name: Download every retained producer artifact\n")
        val nextStep = central.indexOf("      - ", download + 1)
        val downloadStep = central.substring(download, nextStep)
        assertFailsWith<AssertionError> {
            assertDownloadContract(
                central.replace(
                    downloadStep,
                    downloadStep.replace("        if: always()\n", ""),
                ),
            )
        }
        assertFailsWith<AssertionError> {
            assertDownloadContract(
                central.replace(downloadStep, "").replace(
                    "      - name: Collect and independently enumerate 112 lanes\n",
                    downloadStep + "      - name: Collect and independently enumerate 112 lanes\n",
                ),
            )
        }
    }
}

// ----------------------------------------------------------------------------------------
// Contract helpers of `test_collection.py`
// ----------------------------------------------------------------------------------------

private val EXPECTED_CENTRAL_NEEDS =
    listOf("staged-jvm-and-linux", "hosted-publications", "hosted-native")

private val EXPECTED_CENTRAL_COMMANDS = listOf(
    "set +e",
    "mkdir -p \"\$RUNNER_TEMP/central-logs\" \"\$RUNNER_TEMP/producer-artifacts\"",
    "source_args=()",
    "if [ \"\$DYN4K_CROSS_RUN_ONLY\" = true ]; then",
    "source_args=(--source-index \"\$RUNNER_TEMP/cross-run-source-index.json\"",
    "--repository-name \"\$GITHUB_REPOSITORY\"",
    "--run-id \"\$GITHUB_RUN_ID\" --run-attempt \"\$GITHUB_RUN_ATTEMPT\")",
    "fi",
    "./gradlew -p tools/harness :qualification:collectQualification --console=plain -q " +
        "--args=\"--repository \$GITHUB_WORKSPACE --candidate-sha \$GITHUB_SHA " +
        "--artifacts-dir \$RUNNER_TEMP/producer-artifacts " +
        "--upstream \$RUNNER_TEMP/dyn4j-source \${source_args[*]} " +
        "--output \$RUNNER_TEMP/central-collection\" " +
        "> \"\$RUNNER_TEMP/central-logs/collection.stdout\" " +
        "2> \"\$RUNNER_TEMP/central-logs/collection.stderr\"",
    "collection_exit=\$?",
    "./gradlew -p tools/harness :qualification:collectQualification --console=plain -q " +
        "--args=\"--verify --repository \$GITHUB_WORKSPACE --candidate-sha \$GITHUB_SHA " +
        "--artifacts-dir \$RUNNER_TEMP/producer-artifacts " +
        "--output \$RUNNER_TEMP/central-collection\" " +
        "> \"\$RUNNER_TEMP/central-logs/transport.stdout\" " +
        "2> \"\$RUNNER_TEMP/central-logs/transport.stderr\"",
    "transport_exit=\$?",
    "python3 tools/qualification/independent_gates.py " +
        "--repository \"\$GITHUB_WORKSPACE\" --candidate-sha \"\$GITHUB_SHA\" " +
        "--assembly \"\$RUNNER_TEMP/central-collection/assembly-inputs.json\" " +
        "> \"\$RUNNER_TEMP/central-logs/independent-112.json\" " +
        "2> \"\$RUNNER_TEMP/central-logs/independent-112.stderr\"",
    "assembly_exit=\$?",
    "python3 tools/qualification/qualify.py record " +
        "--candidate-sha \"\$GITHUB_SHA\" " +
        "--output \"\$RUNNER_TEMP/central-logs/runtime-matrix.json\" " +
        "> \"\$RUNNER_TEMP/central-logs/record.stdout\" " +
        "2> \"\$RUNNER_TEMP/central-logs/record.stderr\"",
    "record_exit=\$?",
    "printf 'download=%s\\ncollection=%s\\ntransport=%s\\nassembly=%s\\nrecord=%s\\n' " +
        "\"\$DYN4K_DOWNLOAD_OUTCOME\" \"\$collection_exit\" \"\$transport_exit\" " +
        "\"\$assembly_exit\" \"\$record_exit\" > \"\$RUNNER_TEMP/central-logs/exit-codes.txt\"",
    "if [ \"\$DYN4K_DOWNLOAD_OUTCOME\" != success ]; then",
    "echo \"::error::Producer artifact download failed or was skipped: \$DYN4K_DOWNLOAD_OUTCOME\"",
    "fi",
    "test \"\$DYN4K_DOWNLOAD_OUTCOME\" = success && " +
        "test \"\$collection_exit\" -eq 0 && test \"\$transport_exit\" -eq 0 && " +
        "test \"\$assembly_exit\" -eq 0 && test \"\$record_exit\" -eq 0",
)

private fun assertManualQualificationTrigger(workflow: String) {
    if (workflowEventBlocks(workflow).keys.toList() != listOf("workflow_dispatch")) {
        throw AssertionError("full qualification must require manual dispatch")
    }
}

private fun workflowEventBlocks(workflow: String): LinkedHashMap<String, String> {
    val match = Regex("(?ms)^on:\\n(.*?)(?=^jobs:\\n)").find(workflow)
        ?: throw AssertionError("workflow trigger block is missing")
    val source = match.groupValues[1]
    val events = Regex("(?m)^  ([a-z][a-z0-9_-]*):\\s*$").findAll(source).toList()
    val blocks = LinkedHashMap<String, String>()
    for ((index, event) in events.withIndex()) {
        val end = if (index + 1 < events.size) events[index + 1].range.first else source.length
        blocks[event.groupValues[1]] = source.substring(event.range.last + 1, end)
    }
    return blocks
}

private fun workflowJobs(workflow: String): Map<String, String> {
    val body = workflow.split("jobs:\n", limit = 2)[1]
    val matches = Regex("(?m)^  ([a-z][a-z0-9-]+):\\n").findAll(body).toList()
    val jobs = LinkedHashMap<String, String>()
    for ((index, match) in matches.withIndex()) {
        val end = if (index + 1 < matches.size) matches[index + 1].range.first else body.length
        jobs[match.groupValues[1]] = body.substring(match.range.last + 1, end)
    }
    return jobs
}

private fun mappingBlock(
    lines: List<String>,
    key: String,
    indentation: Int,
    start: Int = 0,
    limit: Int = lines.size,
    required: Boolean = true,
): Pair<Int, Int>? {
    val header = " ".repeat(indentation) + key
    val matches = (start until limit).filter { lines[it] == header }
    if (matches.isEmpty()) {
        if (required) throw AssertionError("missing workflow key: $key")
        return null
    }
    if (matches.size != 1) throw AssertionError("duplicate workflow key: $key")
    val headerIndex = matches[0]
    for (index in (headerIndex + 1) until limit) {
        val line = lines[index]
        if (line.isNotBlank() && !line.trimStart().startsWith("#") &&
            line.startsWith(" ".repeat(indentation)) && line.length > indentation &&
            line[indentation] !in setOf(' ', '\t')
        ) {
            return headerIndex to index
        }
    }
    return headerIndex to limit
}

private fun blockListValues(lines: List<String>, start: Int, end: Int, indentation: Int): List<String> {
    val prefix = " ".repeat(indentation) + "- "
    val values = mutableListOf<String>()
    for (index in start until end) {
        val line = lines[index]
        if (line.isBlank() || line.trimStart().startsWith("#")) continue
        if (!line.startsWith(prefix)) throw AssertionError("unsupported workflow list syntax")
        var value = line.substring(prefix.length)
        if (value.isEmpty() || value != value.trim()) {
            throw AssertionError("unsupported workflow list value")
        }
        if (value.startsWith("'")) {
            if (value.length < 2 || !value.endsWith("'")) {
                throw AssertionError("unsupported quoted workflow list value")
            }
            value = value.substring(1, value.length - 1).replace("''", "'")
        } else if (value.startsWith("\"")) {
            val decoded = runCatching {
                StrictJson.load(value)
            }.getOrNull()
            if (decoded !is JsonPrimitive || !decoded.isString) {
                throw AssertionError("unsupported quoted workflow list value")
            }
            value = decoded.content
        } else if (value.any { it.isWhitespace() } || "#" in value ||
            value[0] in "!&*{}[]|>@`"
        ) {
            throw AssertionError("unsupported plain workflow list value")
        }
        values.add(value)
    }
    return values
}

private fun centralCollectionNeeds(workflow: String): List<String>? {
    val lines = workflow.lines()
    val jobs = mappingBlock(lines, "jobs:", 0)!!
    val central = mappingBlock(lines, "central-qualification-collection:", 2, jobs.first + 1, jobs.second)!!
    val needs = mappingBlock(lines, "needs:", 4, central.first + 1, central.second, required = false)
        ?: return null
    return blockListValues(lines, needs.first + 1, needs.second, 6)
}

private fun centralCollectionSteps(workflow: String): List<String> {
    val job = workflowJobs(workflow).getValue("central-qualification-collection")
    val steps = job.split("    steps:\n", limit = 2)[1]
    val matches = Regex("(?m)^      - (?:name|uses): .+$").findAll(steps).toList()
    if (matches.isEmpty()) throw AssertionError("central collection has no runnable steps")
    return matches.mapIndexed { index, match ->
        val end = if (index + 1 < matches.size) matches[index + 1].range.first else steps.length
        steps.substring(match.range.first, end)
    }
}

private fun centralCollectionCommands(step: String): List<String> {
    val marker = "        run: |\n"
    if (step.split(marker).size - 1 != 1) {
        throw AssertionError("central collection must have one shell script")
    }
    val script = step.split(marker, limit = 2)[1]
    val commands = mutableListOf<String>()
    var continued = ""
    for (physical in script.lines()) {
        if (!physical.startsWith("          ") || physical.isBlank()) {
            if (physical.isEmpty() && continued.isEmpty()) continue
            throw AssertionError("central collection shell line is malformed")
        }
        val line = physical.trim()
        if (line.endsWith("\\")) {
            continued += line.dropLast(1).trimEnd() + " "
        } else {
            commands.add(continued + line)
            continued = ""
        }
    }
    if (continued.isNotEmpty()) {
        throw AssertionError("central collection shell continuation is incomplete")
    }
    return commands
}

/** The subset of the workflow contract the mutation cases exercise. */
private fun assertCentralCollectionContract(workflow: String) {
    assertManualQualificationTrigger(workflow)
    if (centralCollectionNeeds(workflow) != EXPECTED_CENTRAL_NEEDS) {
        throw AssertionError("central collection needs differ")
    }
    val steps = centralCollectionSteps(workflow)
    val names = listOf(
        "Download every retained producer artifact",
        "Collect and independently enumerate 112 lanes",
        "Upload central raw collection and failed routes",
    )
    val indexes = names.map { name ->
        val matches = steps.withIndex().filter { (_, step) ->
            step.startsWith("      - name: $name\n")
        }
        if (matches.size != 1) throw AssertionError("$name is missing or duplicated")
        matches[0].index
    }
    if (indexes != listOf(0, 1, 2)) throw AssertionError("central collection step order differs")
    val collect = steps[indexes[1]]
    if (centralCollectionCommands(collect) != EXPECTED_CENTRAL_COMMANDS) {
        throw AssertionError("central collection commands differ")
    }
    if ("        continue-on-error: true\n" !in steps[indexes[0]]) {
        throw AssertionError("download is not tolerant")
    }
    if ("          if-no-files-found: error\n" !in steps[indexes[2]]) {
        throw AssertionError("upload retention differs")
    }
}

private fun resourceText(name: String): String {
    val stream = CollectionVectors::class.java.getResourceAsStream("/$name")
        ?: error("resource $name is missing")
    return stream.use { it.readBytes() }.decodeToString()
}

private fun withCollectionTemp(block: (Path) -> Unit) {
    val root = Files.createTempDirectory("collection-suite")
    try {
        block(root)
    } finally {
        Files.walk(root).use { walk ->
            walk.sorted(Comparator.reverseOrder()).forEach { Files.deleteIfExists(it) }
        }
    }
}
