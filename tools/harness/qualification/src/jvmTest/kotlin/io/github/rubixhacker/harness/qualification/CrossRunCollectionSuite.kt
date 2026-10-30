package io.github.rubixhacker.harness.qualification

import de.infix.testBalloon.framework.core.testSuite
import io.github.rubixhacker.harness.contract.Qualification
import io.github.rubixhacker.harness.contract.StrictJson
import java.io.ByteArrayOutputStream
import java.net.http.HttpClient
import java.net.http.HttpRequest
import java.net.http.HttpResponse
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.attribute.PosixFilePermissions
import java.util.concurrent.TimeUnit
import java.util.zip.ZipEntry
import kotlin.io.path.writeText
import kotlin.test.assertEquals
import kotlin.test.assertContentEquals
import kotlin.test.assertFailsWith
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
import org.apache.commons.compress.archivers.zip.ZipArchiveEntry
import org.apache.commons.compress.archivers.zip.ZipArchiveOutputStream

/**
 * `tools/qualification/test_cross_run_collection.py`: the frozen cross-run source index, its
 * transports, the external archive handoff, and the anchoring of every read and copy.
 *
 * Where the reference interposes on `_directory_names`, `digest`, `_copy_regular`, `_file_inventory`
 * and `subprocess.run`, this suite supplies a [CollectionIo]; the port has no descriptor, so a swap
 * that restores an identical identity is not detectable and the test says so instead of asserting
 * a rejection. Windows handle machinery is not ported: those cases reproduce the POSIX half and
 * `UNPORTED.md` records the rest.
 */
val CrossRunCollectionContract by testSuite {
    val head = hostedGit(repositoryRoot(), "rev-parse", "HEAD").trim()
    val tree = CollectionRuntime.sourceTree(repositoryRoot(), head)
    val lane = "tvosSimulatorArm64:tvOS simulator ARM64:current:debug-g"
    val manifest = IndependentGates.loadApprovedManifest(repositoryRoot())

    // ------------------------------------------------------------------------------------
    // Anchoring: unreadable descendants, directory swaps, transient parent swaps
    // ------------------------------------------------------------------------------------

    test("files_in rejects an unreadable descendant and keeps its hash shape") {
        crossRunTemp { root ->
            val artifact = root.resolve("artifact")
            val hidden = artifact.resolve("hidden")
            Files.createDirectories(hidden)
            artifact.resolve("visible.bin").writeText("visible")
            hidden.resolve("unlisted.bin").writeText("hidden")
            var hits = 0
            val io = object : CollectionIo() {
                override fun directoryNames(anchor: Path): List<String> {
                    if (anchor == hidden) {
                        hits++
                        // The reference raises PermissionError; a JVM directory stream raises IO.
                        throw java.io.UncheckedIOException(
                            java.io.IOException("unreadable artifact descendant"),
                        )
                    }
                    return super.directoryNames(anchor)
                }
            }
            val error = assertFailsWith<java.io.UncheckedIOException> {
                CollectionRuntime.filesIn(artifact, io)
            }
            assertTrue("unreadable artifact" in (error.message ?: ""))
            assertEquals(1, hits)
            assertEquals(
                buildJsonObject {
                    put("hidden/unlisted.bin", JsonPrimitive(crossRunSha256("hidden".toByteArray())))
                    put("visible.bin", JsonPrimitive(crossRunSha256("visible".toByteArray())))
                },
                CollectionRuntime.filesIn(artifact),
            )
        }
    }

    test("collect and verify reject an unreadable descendant") {
        crossRunTemp { root ->
            val artifact = root.resolve("artifact")
            val hidden = artifact.resolve("hidden")
            Files.createDirectories(hidden)
            artifact.resolve("visible.bin").writeText("visible")
            hidden.resolve("unlisted.bin").writeText("hidden")
            val name = "windows-failure-raw-$head-unreadable"
            val io = object : CollectionIo() {
                override fun directoryNames(anchor: Path): List<String> {
                    if (anchor == hidden) {
                        throw java.io.UncheckedIOException(
                            java.io.IOException("unreadable artifact descendant"),
                        )
                    }
                    return super.directoryNames(anchor)
                }
            }
            val rejected = CollectionRuntime.collect(
                repositoryRoot(),
                head,
                listOf(name to artifact.toString()),
                root.resolve("rejected"),
                io = io,
            )
            val row = (rejected["artifacts"] as JsonArray)[0] as JsonObject
            assertEquals("FAILED", Py.str(row["status"]))
            assertTrue("unreadable artifact" in (Py.str(row["reason"]) ?: ""))
            val recorded = CollectionRuntime.collect(
                repositoryRoot(),
                head,
                listOf(name to artifact.toString()),
                root.resolve("recorded"),
            )
            assertEquals(
                "RETAINED_UNVERIFIED",
                Py.str(((recorded["artifacts"] as JsonArray)[0] as JsonObject)["status"]),
            )
            assertTrue(
                CollectionRuntime.verifyCollection(
                    repositoryRoot(), head, listOf(name to artifact.toString()), root.resolve("recorded"),
                ),
            )
            assertFailsWith<java.io.UncheckedIOException> {
                CollectionRuntime.verifyCollection(
                    repositoryRoot(),
                    head,
                    listOf(name to artifact.toString()),
                    root.resolve("recorded"),
                    io,
                )
            }
        }
    }

    test("files_in binds an ordinary directory swap detected by identity, not by an atomic read") {
        // The reference renames the enumerated directory and proves the descriptor kept the
        // approved member. The port reads the enumerated name after the swap, so it detects the
        // change through the file identity it re-reads; a swap that restored an identical identity
        // would be undetectable here.
        crossRunTemp { root ->
            val artifact = root.resolve("artifact")
            val alternate = root.resolve("alternate")
            Files.createDirectories(artifact.resolve("nested"))
            Files.createDirectories(alternate.resolve("nested"))
            val member = artifact.resolve("nested/receipt.bin")
            member.writeText("approved")
            alternate.resolve("nested/receipt.bin").writeText("outside")
            var swaps = 0
            val io = object : CollectionIo() {
                override fun directoryNames(anchor: Path): List<String> {
                    val names = super.directoryNames(anchor)
                    if (anchor == artifact && swaps == 0) {
                        swaps++
                        val parked = root.resolve("artifact-parked")
                        Files.move(artifact, parked)
                        Files.move(alternate, artifact)
                        try {
                            return names
                        } finally {
                            Files.move(artifact, alternate)
                            Files.move(parked, artifact)
                        }
                    }
                    return names
                }
            }
            val files = CollectionRuntime.filesIn(artifact, io)
            assertEquals(1, swaps)
            assertEquals(
                buildJsonObject {
                    put("nested/receipt.bin", JsonPrimitive(crossRunSha256("approved".toByteArray())))
                },
                files,
            )
            assertEquals("approved", Files.readString(member))
        }
    }

    test("collect and verify bind a directory swap for a retained route") {
        crossRunTemp { root ->
            val artifact = root.resolve("artifact")
            val alternate = root.resolve("alternate")
            Files.createDirectories(artifact.resolve("nested"))
            Files.createDirectories(alternate.resolve("nested"))
            artifact.resolve("nested/receipt.bin").writeText("approved")
            alternate.resolve("nested/receipt.bin").writeText("outside")
            val name = "windows-failure-raw-$head-swapped"
            val io = object : CollectionIo() {
                var swaps = 0

                override fun directoryNames(anchor: Path): List<String> {
                    val names = super.directoryNames(anchor)
                    if (anchor == artifact && swaps == 0) {
                        swaps++
                        val parked = root.resolve("artifact-parked")
                        Files.move(artifact, parked)
                        Files.move(alternate, artifact)
                        try {
                            return names
                        } finally {
                            Files.move(artifact, alternate)
                            Files.move(parked, artifact)
                        }
                    }
                    return names
                }
            }
            val report = CollectionRuntime.collect(
                repositoryRoot(),
                head,
                listOf(name to artifact.toString()),
                root.resolve("collection"),
                io = io,
            )
            val row = (report["artifacts"] as JsonArray)[0] as JsonObject
            assertEquals("RETAINED_UNVERIFIED", Py.str(row["status"]))
            assertEquals(
                crossRunSha256("approved".toByteArray()),
                Py.str((row["files"] as JsonObject)["nested/receipt.bin"]),
            )
            assertTrue(
                CollectionRuntime.verifyCollection(
                    repositoryRoot(), head, listOf(name to artifact.toString()), root.resolve("collection"),
                ),
            )
        }
    }

    test("inventory and copy use the enumerated parent for a nested regular member") {
        for (mode in listOf("inventory", "copy")) {
            crossRunTemp { root ->
                val source = root.resolve("source")
                val alternate = root.resolve("alternate")
                Files.createDirectories(source.resolve("sub"))
                Files.createDirectories(alternate.resolve("sub"))
                source.resolve("sub/receipt.bin").writeText("approved")
                alternate.resolve("sub/receipt.bin").writeText("outside")
                var swaps = 0
                val io = object : CollectionIo() {
                    override fun directoryNames(anchor: Path): List<String> {
                        val names = super.directoryNames(anchor)
                        if (anchor == source && swaps == 0) {
                            swaps++
                            val parked = root.resolve("source-parked")
                            Files.move(source, parked)
                            Files.move(alternate, source)
                            try {
                                return names
                            } finally {
                                Files.move(source, alternate)
                                Files.move(parked, source)
                            }
                        }
                        return names
                    }
                }
                if (mode == "inventory") {
                    val files = CollectionRuntime.fileInventory(source, io)
                    assertEquals(
                        crossRunSha256("approved".toByteArray()),
                        Py.str(((files["sub/receipt.bin"]) as JsonObject)["sha256"]),
                    )
                } else {
                    CollectionRuntime.copyDirectory(source, root.resolve("frozen"), io)
                    assertEquals("approved", Files.readString(root.resolve("frozen/sub/receipt.bin")))
                }
                assertEquals(1, swaps)
                assertEquals("approved", Files.readString(source.resolve("sub/receipt.bin")))
            }
        }
    }

    test("a parent replaced by a symbolic link is rejected, a plain rename is not detectable") {
        // `test_public_index_and_archive_reads_resist_transient_parent_swap` and
        // `test_public_directory_snapshot_binds_transient_parent_swap` rely on descriptor-relative
        // opens. The port rejects a symlinked ancestor; a rename that restores an ordinary
        // directory with identical identity leaves nothing to detect.
        crossRunTemp { root ->
            val holder = root.resolve("holder")
            val archive = holder.resolve("mobile.zip")
            Files.createDirectories(holder)
            writeMobileZip(archive, head)
            val outside = root.resolve("outside")
            Files.createDirectories(outside)
            Files.write(outside.resolve("mobile.zip"), "outside".toByteArray())
            val parked = root.resolve("holder-parked")
            Files.move(holder, parked)
            Files.createSymbolicLink(holder, outside)
            try {
                val error = assertFailsWith<IllegalArgumentException> {
                    CollectionRuntime.safeSourcePath(holder.resolve("mobile.zip"))
                }
                assertTrue("symbolic source path" in (error.message ?: ""))
            } finally {
                Files.delete(holder)
                Files.move(parked, holder)
            }
            assertContentEquals(
                Files.readAllBytes(holder.resolve("mobile.zip")),
                Files.readAllBytes(archive),
            )
        }
    }

    // ------------------------------------------------------------------------------------
    // Mobile transport and snapshot verification
    // ------------------------------------------------------------------------------------

    test("a mobile zip is frozen and source bound without a gate pass") {
        crossRunTemp { root ->
            val (archive, index) = mobileFixture(root, head, tree, lane)
            val result = collectFixture(root, index)
            assertEquals("NOT_RUN", Py.str(result["status"]))
            val row = ((result["cross_run"] as JsonObject)["sources"] as JsonArray)[0] as JsonObject
            assertEquals("NOT_RUN", Py.str(row["status"]))
            assertTrue(
                "portable-mobile-capture-v1 source and target bound" in (Py.str(row["reason"]) ?: ""),
            )
            assertContentEquals(Files.readAllBytes(archive), Files.readAllBytes(root.resolve("collection/raw/sources/mobile/original")))
            val inputs = StrictJson.load(
                Files.readString(root.resolve("collection/assembly-inputs.json")),
            ) as JsonObject
            assertEquals(112, inputs.size)
            assertTrue(
                inputs.values.all { it == buildJsonObject { put("archives", buildJsonObject { }) } },
            )
            assertTrue(
                CollectionRuntime.verifyCollection(repositoryRoot(), head, emptyList(), root.resolve("collection")),
            )
            Files.write(root.resolve("collection/raw/sources/mobile/unrecorded"), "x".toByteArray())
            assertTrue(
                "unrecorded files" in (assertFailsWith<IllegalArgumentException> {
                    CollectionRuntime.verifyCollection(
                        repositoryRoot(), head, emptyList(), root.resolve("collection"),
                    )
                }.message ?: ""),
            )
            Files.delete(root.resolve("collection/raw/sources/mobile/unrecorded"))
            val normalized = root.resolve("collection/normalized/mobile/build/stage-receipt.json")
            Files.write(normalized, "changed".toByteArray())
            assertTrue(
                "normalized source archive bytes differ" in (assertFailsWith<IllegalArgumentException> {
                    CollectionRuntime.verifyCollection(
                        repositoryRoot(), head, emptyList(), root.resolve("collection"),
                    )
                }.message ?: ""),
            )
            writeStageReceipt(normalized, head)
            Files.write(root.resolve("collection/raw/sources/mobile/original"), "changed".toByteArray())
            assertTrue(
                "frozen source archive bytes differ" in (assertFailsWith<IllegalArgumentException> {
                    CollectionRuntime.verifyCollection(
                        repositoryRoot(), head, emptyList(), root.resolve("collection"),
                    )
                }.message ?: ""),
            )
        }
    }

    test("verify requires the exact failed packed and directory snapshot children") {
        for (kind in listOf("packed", "directory")) {
            for (alteration in listOf("delete", "alternate")) {
                crossRunTemp { root ->
                    val index: Path
                    if (kind == "packed") {
                        val fixture = mobileFixture(root, head, tree, lane, mapOf("../escape" to "x"))
                        index = fixture.second
                    } else {
                        val source = root.resolve("directory")
                        Files.createDirectories(source)
                        source.resolve("receipt.json").writeText("raw failure\n")
                        val files = CollectionRuntime.fileInventory(source)
                        val digest = CollectionRules.inventoryDigest(files)
                        val altered = JsonObject(
                            files + (
                                "receipt.json" to buildJsonObject {
                                    put("size", JsonPrimitive(15))
                                    put("sha256", JsonPrimitive("0".repeat(64)))
                                }
                                ),
                        )
                        index = writeIndex(
                            root,
                            head,
                            tree,
                            JsonObject(
                                buildJsonObject {
                                    put("id", JsonPrimitive("failed"))
                                    put(
                                        "origin",
                                        buildJsonObject {
                                            put("kind", JsonPrimitive("local"))
                                            put("path", JsonPrimitive(source.toString()))
                                        },
                                    )
                                    put(
                                        "transport",
                                        buildJsonObject {
                                            put("format", JsonPrimitive("directory"))
                                            put("files", altered)
                                            put(
                                                "inventory_sha256",
                                                JsonPrimitive(CollectionRules.inventoryDigest(altered)),
                                            )
                                        },
                                    )
                                },
                            ),
                            lane,
                            "staged-consumer",
                            null,
                            digest,
                        )
                    }
                    val result = collectFixture(root, index)
                    val row = ((result["cross_run"] as JsonObject)["sources"] as JsonArray)[0]
                        as JsonObject
                    assertEquals("FAILED", Py.str(row["status"]))
                    assertTrue(
                        CollectionRuntime.verifyCollection(
                            repositoryRoot(), head, emptyList(), root.resolve("collection"),
                        ),
                    )
                    val folder = root.resolve(
                        if (kind == "packed") "collection/raw/sources/mobile"
                        else "collection/raw/sources/failed",
                    )
                    if (alteration == "delete") {
                        crossRunDelete(
                            folder.resolve(if (kind == "packed") "original" else "original-directory"),
                        )
                    } else if (kind == "packed") {
                        Files.createDirectories(folder.resolve("original-directory"))
                        folder.resolve("original-directory/other.txt").writeText("unrecorded")
                    } else {
                        Files.write(folder.resolve("original"), "unrecorded".toByteArray())
                    }
                    assertFailsWith<IllegalArgumentException> {
                        CollectionRuntime.verifyCollection(
                            repositoryRoot(), head, emptyList(), root.resolve("collection"),
                        )
                    }
                }
            }
        }
    }

    // ------------------------------------------------------------------------------------
    // The index contract
    // ------------------------------------------------------------------------------------

    test("a same-run rerun attempt needs artifact provenance") {
        val index = buildJsonObject {
            put("schema", JsonPrimitive(1))
            put("candidate_sha", JsonPrimitive(head))
            put("source_tree", JsonPrimitive(tree))
            put(
                "sources",
                JsonArray(
                    listOf(
                        buildJsonObject {
                            put("id", JsonPrimitive("rerun"))
                            put(
                                "origin",
                                buildJsonObject {
                                    put("kind", JsonPrimitive("same_run"))
                                    put("repository", JsonPrimitive("rubixhacker/dyn4k"))
                                    put(
                                        "workflow",
                                        JsonPrimitive(".github/workflows/qualification.yml"),
                                    )
                                    put("run_id", JsonPrimitive(42))
                                    put("run_attempt", JsonPrimitive(2))
                                    put("name", JsonPrimitive("full-ci-$head"))
                                    put("head_sha", JsonPrimitive(head))
                                },
                            )
                            put(
                                "transport",
                                buildJsonObject {
                                    put("format", JsonPrimitive("zip"))
                                    put("size", JsonPrimitive(10))
                                    put("sha256", JsonPrimitive("a".repeat(64)))
                                },
                            )
                        },
                    ),
                ),
            )
            put(
                "bindings",
                JsonArray(
                    listOf(
                        buildJsonObject {
                            put("source_id", JsonPrimitive("rerun"))
                            put("lane", JsonPrimitive(lane))
                            put("gate", JsonPrimitive("staged-consumer"))
                        },
                    ),
                ),
            )
        }
        assertTrue(
            "attempt ownership" in (assertFailsWith<IllegalArgumentException> {
                validateIndex(index, 42, 2)
            }.message ?: ""),
        )
    }

    test("a lane binding rejects a conflicting declared target") {
        crossRunTemp { root ->
            val (_, indexPath, index) = mobileFixtureWithIndex(root, head, tree, lane)
            Files.writeString(
                indexPath,
                JsonObject(
                    index + (
                        "bindings" to JsonArray(
                            listOf(
                                buildJsonObject {
                                    put("source_id", JsonPrimitive("mobile"))
                                    put("lane", JsonPrimitive(lane))
                                    put("gate", JsonPrimitive("staged-consumer"))
                                    put("target", JsonPrimitive("jvm"))
                                },
                            ),
                        )
                        ),
                ).toString(),
            )
            val result = collectFixture(root, indexPath)
            assertEquals("FAILED", Py.str(result["status"]))
            assertTrue(
                "lane binding target differs" in
                    (Py.str((result["cross_run"] as JsonObject)["reason"]) ?: ""),
            )
            crossRunTemp { second ->
                val (_, secondIndex, secondValue) = mobileFixtureWithIndex(second, head, tree, lane)
                Files.writeString(
                    secondIndex,
                    JsonObject(
                        secondValue + (
                            "bindings" to JsonArray(
                                listOf(
                                    buildJsonObject {
                                        put("source_id", JsonPrimitive("mobile"))
                                        put("lane", JsonPrimitive(lane))
                                        put("gate", JsonPrimitive("staged-consumer"))
                                        put("target", JsonPrimitive("tvosSimulatorArm64"))
                                    },
                                ),
                            )
                            ),
                    ).toString(),
                )
                val accepted = collectFixture(second, secondIndex)
                assertEquals("NOT_RUN", Py.str(accepted["status"]))
                assertTrue(
                    CollectionRuntime.verifyCollection(
                        repositoryRoot(), head, emptyList(), second.resolve("collection"),
                    ),
                )
            }
        }
    }

    test("a wrong candidate, tree, or duplicate binding fails") {
        for ((label, mutate, reason) in listOf<Triple<String, (LinkedHashMap<String, JsonElement>) -> Unit, String>>(
            Triple("candidate", { value -> value["candidate_sha"] = JsonPrimitive("0".repeat(40)) },
                "candidate or tree differs"),
            Triple("tree", { value -> value["source_tree"] = JsonPrimitive("0".repeat(40)) },
                "candidate or tree differs"),
            Triple("target", { value ->
                value["bindings"] = JsonArray(
                    listOf(
                        buildJsonObject {
                            put("source_id", JsonPrimitive("mobile"))
                            put("lane", JsonPrimitive("not-a-lane"))
                            put("gate", JsonPrimitive("staged-consumer"))
                        },
                    ),
                )
            }, "lane or gate binding is not approved"),
            Triple("duplicate binding", { value ->
                val bindings = (value["bindings"] as JsonArray).toMutableList()
                bindings.add(bindings[0])
                value["bindings"] = JsonArray(bindings)
            }, "duplicate lane or global gate binding"),
            Triple("duplicate source", { value ->
                val sources = (value["sources"] as JsonArray).toMutableList()
                sources.add(sources[0])
                value["sources"] = JsonArray(sources)
            }, "duplicate or unsafe source ID"),
        )) {
            crossRunTemp { root ->
                val (_, indexPath, index) = mobileFixtureWithIndex(root, head, tree, lane)
                val changed = LinkedHashMap<String, JsonElement>(index)
                mutate(changed)
                Files.writeString(indexPath, JsonObject(changed).toString())
                val result = collectFixture(root, indexPath)
                assertEquals("FAILED", Py.str(result["status"]), label)
                val crossRun = result["cross_run"] as JsonObject
                val message = (Py.str(crossRun["reason"])
                    ?: Py.str(((crossRun["sources"] as JsonArray)[0] as JsonObject)["reason"])
                    ?: "")
                assertTrue(reason in message, "$label: $message")
            }
        }
    }

    test("collect binds the three directory enumerations of a regular directory swap") {
        crossRunTemp { root ->
            val source = root.resolve("source")
            val alternate = root.resolve("alternate")
            Files.createDirectories(source)
            Files.createDirectories(alternate)
            source.resolve("receipt.bin").writeText("approved")
            alternate.resolve("receipt.bin").writeText("outside")
            val files = CollectionRuntime.fileInventory(source)
            val index = writeIndex(
                root,
                head,
                tree,
                directorySource(source, files),
                lane,
                "staged-consumer",
                null,
                null,
            )
            val io = regularDirectorySwap(source, alternate)
            val result = CollectionRuntime.collect(
                repositoryRoot(),
                head,
                emptyList(),
                root.resolve("collection"),
                sourceIndex = index,
                artifactsDir = root.resolve("artifacts").also { Files.createDirectories(it) },
                io = io,
            )
            // The reference's `regular_directory_swap` fires on every enumeration of the approved
            // directory: the pre-inventory, the frozen copy, and the post-inventory.
            assertEquals(3, io.swaps)
            val row = ((result["cross_run"] as JsonObject)["sources"] as JsonArray)[0] as JsonObject
            assertEquals("NOT_RUN", Py.str(row["status"]))
            assertContentEquals(
                "approved".toByteArray(),
                Files.readAllBytes(
                    root.resolve("collection/raw/sources/rawdir/original-directory/receipt.bin"),
                ),
            )
            assertContentEquals(
                "approved".toByteArray(),
                Files.readAllBytes(source.resolve("receipt.bin")),
            )
            assertTrue(
                CollectionRuntime.verifyCollection(
                    repositoryRoot(), head, emptyList(), root.resolve("collection"),
                ),
            )
        }
    }

    test("collect rejects an alternate directory pin across the three swaps") {
        crossRunTemp { root ->
            val source = root.resolve("source")
            val alternate = root.resolve("alternate")
            Files.createDirectories(source)
            Files.createDirectories(alternate)
            source.resolve("receipt.bin").writeText("approved")
            alternate.resolve("receipt.bin").writeText("outside")
            // The index pins the alternate directory's bytes while the origin names `source`.
            val files = CollectionRuntime.fileInventory(alternate)
            val index = writeIndex(
                root,
                head,
                tree,
                directorySource(source, files),
                lane,
                "staged-consumer",
                null,
                null,
            )
            val io = regularDirectorySwap(source, alternate)
            val result = CollectionRuntime.collect(
                repositoryRoot(),
                head,
                emptyList(),
                root.resolve("collection"),
                sourceIndex = index,
                artifactsDir = root.resolve("artifacts").also { Files.createDirectories(it) },
                io = io,
            )
            assertEquals(3, io.swaps)
            val row = ((result["cross_run"] as JsonObject)["sources"] as JsonArray)[0] as JsonObject
            assertEquals("FAILED", Py.str(row["status"]))
            assertTrue(
                "source directory byte inventory differs" in (Py.str(row["reason"]) ?: ""),
                Py.str(row["reason"]) ?: "no reason",
            )
            assertContentEquals(
                "approved".toByteArray(),
                Files.readAllBytes(
                    root.resolve("collection/raw/sources/rawdir/original-directory/receipt.bin"),
                ),
            )
            assertTrue(
                CollectionRuntime.verifyCollection(
                    repositoryRoot(), head, emptyList(), root.resolve("collection"),
                ),
            )
        }
    }

    test("a directory and an unsupported format remain not run") {
        crossRunTemp { root ->
            val source = root.resolve("raw-directory")
            Files.createDirectories(source)
            source.resolve("receipt.json").writeText(
                buildJsonObject {
                    put("candidate_sha", JsonPrimitive(head))
                    put("status", JsonPrimitive("PASSED"))
                }.toString(),
            )
            val files = CollectionRuntime.fileInventory(source)
            val index = writeIndex(
                root,
                head,
                tree,
                buildJsonObject {
                    put("id", JsonPrimitive("rawdir"))
                    put(
                        "origin",
                        buildJsonObject {
                            put("kind", JsonPrimitive("local"))
                            put("path", JsonPrimitive(source.toString()))
                        },
                    )
                    put(
                        "transport",
                        buildJsonObject {
                            put("format", JsonPrimitive("directory"))
                            put("files", files)
                            put("inventory_sha256", JsonPrimitive(CollectionRules.inventoryDigest(files)))
                        },
                    )
                },
                lane,
                "staged-consumer",
                null,
                null,
            )
            val result = collectFixture(root, index)
            assertEquals("NOT_RUN", Py.str(result["status"]))
            assertTrue(
                "unsupported producer format" in
                    (Py.str((((result["cross_run"] as JsonObject)["sources"] as JsonArray)[0]
                        as JsonObject)["reason"]) ?: ""),
            )
            assertTrue(
                CollectionRuntime.verifyCollection(
                    repositoryRoot(), head, emptyList(), root.resolve("collection"),
                ),
            )
            root.resolve("collection/raw/sources/rawdir/original-directory/receipt.json")
                .writeText("altered")
            assertTrue(
                "frozen source directory bytes differ" in (assertFailsWith<IllegalArgumentException> {
                    CollectionRuntime.verifyCollection(
                        repositoryRoot(), head, emptyList(), root.resolve("collection"),
                    )
                }.message ?: ""),
            )
        }
    }

    test("a same-run directory needs the current run and freezes its bytes") {
        crossRunTemp { root ->
            val artifacts = root.resolve("artifacts")
            val source = artifacts.resolve("qualification-$head")
            Files.createDirectories(source)
            source.resolve("failed.log").writeText("raw failure\n")
            val files = CollectionRuntime.fileInventory(source)
            val index = writeIndex(
                root,
                head,
                tree,
                buildJsonObject {
                    put("id", JsonPrimitive("current"))
                    put(
                        "origin",
                        buildJsonObject {
                            put("kind", JsonPrimitive("same_run"))
                            put("repository", JsonPrimitive("rubixhacker/dyn4k"))
                            put("workflow", JsonPrimitive(".github/workflows/qualification.yml"))
                            put("run_id", JsonPrimitive(42))
                            put("run_attempt", JsonPrimitive(1))
                            put("name", JsonPrimitive(source.fileName.toString()))
                            put("head_sha", JsonPrimitive(head))
                        },
                    )
                    put(
                        "transport",
                        buildJsonObject {
                            put("format", JsonPrimitive("directory"))
                            put("files", files)
                            put("inventory_sha256", JsonPrimitive(CollectionRules.inventoryDigest(files)))
                        },
                    )
                },
                lane,
                "staged-consumer",
                null,
                null,
            )
            val output = root.resolve("transport")
            Files.createDirectories(output)
            val result = CollectionRuntime.snapshotSourceIndex(
                index,
                head,
                tree,
                manifest,
                artifacts,
                output,
                runId = 42,
                runAttempt = 1,
            )
            assertEquals("NOT_RUN", Py.str(result["status"]))
            assertContentEquals(Files.readAllBytes(source.resolve("failed.log")), Files.readAllBytes(output.resolve("raw/sources/current/original-directory/failed.log")))
            assertTrue(CollectionRuntime.verifySourceSnapshot(output, head, tree))
        }
    }

    test("a missing source, a wrong pin, a duplicate JSON key, and a symlink fail") {
        crossRunTemp { root ->
            val (_, index, value) = mobileFixtureWithIndex(root, head, tree, lane)
            assertTrue(
                "cannot read arbitrary local source" in (assertFailsWith<IllegalArgumentException> {
                    validateIndex(value, null, null, allowLocal = false)
                }.message ?: ""),
            )
            val missing = LinkedHashMap<String, JsonElement>(value)
            missing["sources"] = JsonArray(
                listOf(
                    JsonObject(
                        ((value["sources"] as JsonArray)[0] as JsonObject) + (
                            "origin" to buildJsonObject {
                                put("kind", JsonPrimitive("local"))
                                put(
                                    "path",
                                    JsonPrimitive(root.resolve("missing/archive.zip").toString()),
                                )
                            }
                            ),
                    ),
                ),
            )
            Files.writeString(index, JsonObject(missing).toString())
            val result = collectFixture(root, index)
            assertEquals("FAILED", Py.str((result["cross_run"] as JsonObject)["status"]))
            val missingReason = Py.str((((result["cross_run"] as JsonObject)["sources"] as JsonArray)[0]
                as JsonObject)["reason"]) ?: "no reason"
            assertTrue("source archive is missing" in missingReason, missingReason)
            crossRunTemp { second ->
                val (_, secondIndex, secondValue) = mobileFixtureWithIndex(second, head, tree, lane)
                val wrongPin = LinkedHashMap<String, JsonElement>(secondValue)
                wrongPin["sources"] = JsonArray(
                    listOf(
                        JsonObject(
                            ((secondValue["sources"] as JsonArray)[0] as JsonObject) + (
                                "transport" to buildJsonObject {
                                    put("format", JsonPrimitive("zip"))
                                    put("size", JsonPrimitive(1))
                                    put("sha256", JsonPrimitive("0".repeat(64)))
                                }
                                ),
                        ),
                    ),
                )
                Files.writeString(secondIndex, JsonObject(wrongPin).toString())
                val pinResult = collectFixture(second, secondIndex)
                val pinReason = Py.str((((pinResult["cross_run"] as JsonObject)["sources"] as JsonArray)[0]
                    as JsonObject)["reason"]) ?: "no reason"
                assertTrue("source archive bytes differ from exact pin" in pinReason, pinReason)
                assertTrue(
                    CollectionRuntime.verifyCollection(
                        repositoryRoot(), head, emptyList(), second.resolve("collection"),
                    ),
                )
            }
            crossRunTemp { third ->
                val (_, thirdIndex, _) = mobileFixtureWithIndex(third, head, tree, lane)
                Files.writeString(thirdIndex, "{\"schema\":1,\"schema\":1}")
                val duplicate = collectFixture(third, thirdIndex)
                assertEquals("FAILED", Py.str(duplicate["status"]))
                val keyReason = Py.str((duplicate["cross_run"] as JsonObject)["reason"]) ?: "no reason"
                assertTrue("duplicate JSON key" in keyReason, keyReason)
                assertContentEquals(
                    Files.readAllBytes(thirdIndex),
                    Files.readAllBytes(third.resolve("collection/source-index.rejected")),
                )
            }
            crossRunTemp { fourth ->
                val (archive, fourthIndex, fourthValue) = mobileFixtureWithIndex(fourth, head, tree, lane)
                val alias = fourth.resolve("alias.zip")
                Files.createSymbolicLink(alias, archive)
                val changed = LinkedHashMap<String, JsonElement>(fourthValue)
                changed["sources"] = JsonArray(
                    listOf(
                        JsonObject(
                            ((fourthValue["sources"] as JsonArray)[0] as JsonObject) + (
                                "origin" to buildJsonObject {
                                    put("kind", JsonPrimitive("local"))
                                    put("path", JsonPrimitive(alias.toString()))
                                }
                                ),
                        ),
                    ),
                )
                Files.writeString(fourthIndex, JsonObject(changed).toString())
                val linked = collectFixture(fourth, fourthIndex)
                assertEquals("FAILED", Py.str(linked["status"]))
                val linkedReason = Py.str((linked["cross_run"] as JsonObject)["reason"]) ?: "no reason"
                assertTrue("symbolic source path" in linkedReason, linkedReason)
            }
        }
    }

    // ------------------------------------------------------------------------------------
    // Transport safety
    // ------------------------------------------------------------------------------------

    test("unsafe zip members fail with the raw archive retained") {
        for (members in listOf(mapOf("../escape" to "x"), mapOf("build/ok" to "a", "build/../ok" to "b"))) {
            crossRunTemp { root ->
                val (archive, index) = mobileFixture(root, head, tree, lane, members)
                val result = collectFixture(root, index)
                assertEquals("FAILED", Py.str((result["cross_run"] as JsonObject)["status"]))
                assertTrue(
                    "unsafe archive path" in
                        (Py.str((((result["cross_run"] as JsonObject)["sources"] as JsonArray)[0]
                            as JsonObject)["reason"]) ?: ""),
                )
                assertContentEquals(
                    Files.readAllBytes(archive),
                    Files.readAllBytes(root.resolve("collection/raw/sources/mobile/original")),
                )
            }
        }
    }

    test("a source archive changed during the copy is retained as failed") {
        crossRunTemp { root ->
            val (archive, index) = mobileFixture(root, head, tree, lane)
            val io = object : CollectionIo() {
                override fun copyRegular(source: Path, destination: Path, limit: Long, preflight: Boolean): Long {
                    val copied = super.copyRegular(source, destination, limit, preflight)
                    Files.write(source, Files.readAllBytes(source) + "changed".toByteArray())
                    return copied
                }
            }
            val result = CollectionRuntime.collect(
                repositoryRoot(),
                head,
                emptyList(),
                root.resolve("collection"),
                sourceIndex = index,
                artifactsDir = root.resolve("artifacts").also { Files.createDirectories(it) },
                io = io,
            )
            assertEquals("FAILED", Py.str((result["cross_run"] as JsonObject)["status"]))
            assertTrue(
                "changed while copied" in
                    (Py.str((((result["cross_run"] as JsonObject)["sources"] as JsonArray)[0]
                        as JsonObject)["reason"]) ?: ""),
            )
            assertTrue(Files.isRegularFile(root.resolve("collection/raw/sources/mobile/original")))
            assertTrue(Files.isRegularFile(archive))
        }
    }

    test("a duplicate zip member and a symbolic zip member fail") {
        for (member in listOf("duplicate", "symbolic")) {
            crossRunTemp { root ->
                val archive = root.resolve("mobile.zip")
                ZipArchiveOutputStream(Files.newOutputStream(archive)).use { packed ->
                    if (member == "duplicate") {
                        for (value in listOf("a", "b")) {
                            val entry = ZipArchiveEntry("same.txt")
                            entry.size = 1
                            packed.putArchiveEntry(entry)
                            packed.write(value.toByteArray())
                            packed.closeArchiveEntry()
                        }
                    } else {
                        val entry = ZipArchiveEntry("link")
                        entry.unixMode = 0xA1FF
                        entry.size = 6
                        packed.putArchiveEntry(entry)
                        packed.write("target".toByteArray())
                        packed.closeArchiveEntry()
                    }
                }
                val index = writeZipIndex(root, head, tree, archive, lane)
                val result = collectFixture(root, index)
                assertEquals("FAILED", Py.str((result["cross_run"] as JsonObject)["status"]))
                val reason = Py.str((((result["cross_run"] as JsonObject)["sources"] as JsonArray)[0]
                    as JsonObject)["reason"]) ?: ""
                assertTrue(
                    (if (member == "duplicate") "duplicate archive member" else "nonregular ZIP member")
                        in reason,
                    "$member: $reason",
                )
            }
        }
    }

    test("tar traversal and duplicate members fail") {
        for (names in listOf(listOf("../escape"), listOf("same", "same"))) {
            crossRunTemp { root ->
                val packed = root.resolve("raw.tar")
                TarArchiveOutputStream(Files.newOutputStream(packed)).use { archive ->
                    for (name in names) {
                        val entry = TarArchiveEntry(name)
                        entry.size = 1
                        archive.putArchiveEntry(entry)
                        archive.write("x".toByteArray())
                        archive.closeArchiveEntry()
                    }
                }
                val index = writeZipIndex(root, head, tree, packed, lane, "tar")
                val result = collectFixture(root, index)
                assertEquals("FAILED", Py.str((result["cross_run"] as JsonObject)["status"]))
                val reason = Py.str((((result["cross_run"] as JsonObject)["sources"] as JsonArray)[0]
                    as JsonObject)["reason"]) ?: ""
                assertTrue(
                    (if (names.size == 1) "unsafe archive path" else "duplicate archive member") in reason,
                    reason,
                )
            }
        }
    }

    // ------------------------------------------------------------------------------------
    // GitHub provenance and the external handoff
    // ------------------------------------------------------------------------------------

    test("a GitHub source requires the exact metadata and attempt identity") {
        val origin = buildJsonObject {
            put("kind", JsonPrimitive("github_actions"))
            put("repository", JsonPrimitive("rubixhacker/dyn4k"))
            put("workflow", JsonPrimitive(".github/workflows/qualification.yml"))
            put("run_id", JsonPrimitive(42))
            put("run_attempt", JsonPrimitive(1))
            put("artifact_id", JsonPrimitive(77))
            put("api_size_in_bytes", JsonPrimitive(10))
            put("name", JsonPrimitive("pinned"))
            put("head_sha", JsonPrimitive(head))
        }
        val run = buildJsonObject {
            put("id", JsonPrimitive(42))
            put("head_sha", JsonPrimitive(head))
            put("run_attempt", JsonPrimitive(1))
            put("path", JsonPrimitive(".github/workflows/qualification.yml@main"))
            put(
                "repository",
                buildJsonObject {
                    put("full_name", JsonPrimitive("rubixhacker/dyn4k"))
                    put("id", JsonPrimitive(12))
                },
            )
        }
        val artifact = buildJsonObject {
            put("id", JsonPrimitive(77))
            put("name", JsonPrimitive("pinned"))
            put("expired", JsonPrimitive(false))
            put("size_in_bytes", JsonPrimitive(10))
            put(
                "workflow_run",
                buildJsonObject {
                    put("id", JsonPrimitive(42))
                    put("head_sha", JsonPrimitive(head))
                    put("repository_id", JsonPrimitive(12))
                },
            )
        }
        crossRunTemp { root ->
            val destination = root.resolve("raw.zip")
            val bodies = ArrayDeque(listOf(run.toString(), artifact.toString(), "zip-bytes"))
            val opener: (HttpRequest) -> HttpResponse<ByteArray> = { request ->
                val body = bodies.removeFirst().toByteArray()
                fakeResponse(request, body)
            }
            val observed = CollectionRuntime.githubArtifact(
                origin, head, "secret", destination, 10, opener,
            )
            assertEquals(77L, Py.int(observed["artifact_id"]!!))
            assertEquals("zip-bytes", Files.readString(destination))
            for (changed in listOf(
                JsonObject(run + ("head_sha" to JsonPrimitive("0".repeat(40)))),
                JsonObject(run + ("run_attempt" to JsonPrimitive(2))),
                JsonObject(run + ("path" to JsonPrimitive(".github/workflows/other.yml@main"))),
            )) {
                val failing = ArrayDeque(listOf(changed.toString(), artifact.toString()))
                val error = assertFailsWith<IllegalArgumentException> {
                    CollectionRuntime.githubArtifact(
                        origin, head, "secret", destination, 10,
                    ) { request -> fakeResponse(request, failing.removeFirst().toByteArray()) }
                }
                assertTrue("source identity differs" in (error.message ?: ""))
            }
            for (changed in listOf(
                JsonObject(artifact + ("id" to JsonPrimitive(78))),
                JsonObject(artifact + ("name" to JsonPrimitive("other"))),
                JsonObject(artifact + ("expired" to JsonPrimitive(true))),
                JsonObject(artifact + ("size_in_bytes" to JsonPrimitive(11))),
            )) {
                val failing = ArrayDeque(listOf(run.toString(), changed.toString()))
                assertFailsWith<IllegalArgumentException> {
                    CollectionRuntime.githubArtifact(
                        origin, head, "secret", destination, 10,
                    ) { request -> fakeResponse(request, failing.removeFirst().toByteArray()) }
                }
            }
            val rerun = JsonObject(origin + ("run_attempt" to JsonPrimitive(2)))
            val failing = ArrayDeque(
                listOf(
                    JsonObject(run + ("run_attempt" to JsonPrimitive(2))).toString(),
                    artifact.toString(),
                ),
            )
            val error = assertFailsWith<IllegalArgumentException> {
                CollectionRuntime.githubArtifact(
                    rerun, head, "secret", destination, 10,
                ) { request -> fakeResponse(request, failing.removeFirst().toByteArray()) }
            }
            assertTrue("rerun attempt ownership" in (error.message ?: ""))
        }
    }

    test("a duplicate artifact id and a wrong same-run identity fail before any copy") {
        val origin = buildJsonObject {
            put("kind", JsonPrimitive("github_actions"))
            put("repository", JsonPrimitive("rubixhacker/dyn4k"))
            put("workflow", JsonPrimitive(".github/workflows/qualification.yml"))
            put("run_id", JsonPrimitive(42))
            put("run_attempt", JsonPrimitive(1))
            put("artifact_id", JsonPrimitive(77))
            put("api_size_in_bytes", JsonPrimitive(10))
            put("name", JsonPrimitive("pinned"))
            put("head_sha", JsonPrimitive(head))
        }
        val transport = buildJsonObject {
            put("format", JsonPrimitive("zip"))
            put("size", JsonPrimitive(10))
            put("sha256", JsonPrimitive("a".repeat(64)))
        }
        val duplicate = buildJsonObject {
            put("schema", JsonPrimitive(1))
            put("candidate_sha", JsonPrimitive(head))
            put("source_tree", JsonPrimitive(tree))
            put(
                "sources",
                JsonArray(
                    listOf("one", "two").map { name ->
                        buildJsonObject {
                            put("id", JsonPrimitive(name))
                            put("origin", origin)
                            put("transport", transport)
                        }
                    },
                ),
            )
            put(
                "bindings",
                JsonArray(
                    listOf(
                        buildJsonObject {
                            put("source_id", JsonPrimitive("one"))
                            put("lane", JsonPrimitive(lane))
                            put("gate", JsonPrimitive("staged-consumer"))
                        },
                        buildJsonObject {
                            put("source_id", JsonPrimitive("two"))
                            put("lane", JsonPrimitive(lane))
                            put("gate", JsonPrimitive("staged-artifacts"))
                        },
                    ),
                ),
            )
        }
        assertTrue(
            "duplicate or invalid GitHub artifact ID" in (assertFailsWith<IllegalArgumentException> {
                validateIndex(duplicate, 42, 1)
            }.message ?: ""),
        )
        val wrongRun = buildJsonObject {
            put("schema", JsonPrimitive(1))
            put("candidate_sha", JsonPrimitive(head))
            put("source_tree", JsonPrimitive(tree))
            put(
                "sources",
                JsonArray(
                    listOf(
                        buildJsonObject {
                            put("id", JsonPrimitive("one"))
                            put(
                                "origin",
                                buildJsonObject {
                                    put("kind", JsonPrimitive("same_run"))
                                    put("repository", JsonPrimitive("rubixhacker/dyn4k"))
                                    put(
                                        "workflow",
                                        JsonPrimitive(".github/workflows/qualification.yml"),
                                    )
                                    put("run_id", JsonPrimitive(41))
                                    put("run_attempt", JsonPrimitive(1))
                                    put("name", JsonPrimitive("full-ci-$head"))
                                    put("head_sha", JsonPrimitive(head))
                                },
                            )
                            put("transport", transport)
                        },
                    ),
                ),
            )
            put(
                "bindings",
                JsonArray(
                    listOf(
                        buildJsonObject {
                            put("source_id", JsonPrimitive("one"))
                            put("lane", JsonPrimitive(lane))
                            put("gate", JsonPrimitive("staged-consumer"))
                        },
                    ),
                ),
            )
        }
        assertTrue(
            "same-run source identity differs" in (assertFailsWith<IllegalArgumentException> {
                validateIndex(wrongRun, 42, 1)
            }.message ?: ""),
        )
    }

    test("the external archive map uses frozen referenced bytes") {
        crossRunTemp { root ->
            val source = root.resolve("source")
            Files.createDirectories(source)
            source.resolve("receipt.json").writeText("raw receipt\n")
            val stable = root.resolve("stable")
            Files.createDirectories(stable)
            val (map, snapshots) = CollectionRuntime.snapshotExternalReferences(
                archiveMap(head, manifest, lane, source.toString()),
                manifest,
                stable,
            )
            val frozen = Path.of(
                Py.str(
                    ((StrictJson.load(Files.readString(map)) as JsonObject)["lanes"] as JsonObject)
                        .getValue(lane).let { (it as JsonObject)["staged-consumer"] }!!,
                )!!,
            )
            assertTrue(frozen != source)
            assertContentEquals(
                Files.readAllBytes(source.resolve("receipt.json")),
                Files.readAllBytes(frozen.resolve("receipt.json")),
            )
            CollectionRuntime.verifyExternalReferences(snapshots)
            frozen.resolve("receipt.json").writeText("changed\n")
            assertTrue(
                "frozen external archive" in (assertFailsWith<IllegalArgumentException> {
                    CollectionRuntime.verifyExternalReferences(snapshots)
                }.message ?: ""),
            )
        }
    }

    test("the external handoff passes only frozen paths and the explicit key") {
        crossRunTemp { root ->
            val repository = root.resolve("repository")
            Files.createDirectories(repository.resolve("build/staging-repository"))
            val output = root.resolve("collection")
            // `ingest_external` starts from a verified collection; this fixture is the empty one.
            CollectionRuntime.collect(repositoryRoot(), head, emptyList(), output)
            val raw = root.resolve("raw-gate")
            Files.createDirectories(raw)
            raw.resolve("receipt.json").writeText("raw\n")
            val key = root.resolve("independent-performance.pem")
            key.writeText("external verification key\n")
            val pin = crossRunSha256(Files.readAllBytes(key))
            val inputs = root.resolve("audit-inputs")
            Files.createDirectories(inputs)
            Files.writeString(
                inputs.resolve("archive-map.json"),
                archiveMap(head, manifest, lane, raw.toString()).toString(),
            )
            for (name in listOf("candidate-manifest.json", "staged-audit.json")) {
                inputs.resolve(name).writeText(
                    buildJsonObject { put("candidate_sha", JsonPrimitive(head)) }.toString(),
                )
            }
            for (name in listOf("audit.json", "audit.sig", "public.pem", "evidence.json")) {
                inputs.resolve(name).writeText("external input\n")
            }
            var command: List<String>? = null
            val io = object : CollectionIo() {
                override fun runAdapter(command: List<String>, cwd: Path): AdapterRun {
                    captured = command
                    return AdapterRun(1, ByteArray(0), "failed verification".toByteArray())
                }
            }
            captured = null
            val result = CollectionRuntime.ingestExternal(
                repositoryRoot(),
                head,
                emptyList(),
                output,
                inputs,
                trustedKeySha256 = "a".repeat(64),
                independentPerformanceKey = key,
                performanceKeySha256 = pin,
                io = io,
            )
            command = captured
            assertEquals("FAILED", Py.str(result["status"]))
            val called = command!!
            val archiveMapPath = Path.of(called[called.indexOf("--independent-archives") + 1])
            val performanceKey = Path.of(called[called.indexOf("--independent-performance-key") + 1])
            assertTrue(archiveMapPath != inputs.resolve("archive-map.json"))
            assertTrue(performanceKey != key)
            assertEquals(pin, CollectionRuntime.digest(performanceKey))
            val frozen = Path.of(
                Py.str(
                    ((StrictJson.load(Files.readString(archiveMapPath)) as JsonObject)["lanes"]
                        as JsonObject).getValue(lane).let { (it as JsonObject)["staged-consumer"] }!!,
                )!!,
            )
            assertTrue(frozen != raw)
            assertContentEquals(
                Files.readAllBytes(raw.resolve("receipt.json")),
                Files.readAllBytes(frozen.resolve("receipt.json")),
            )
        }
    }

    // ------------------------------------------------------------------------------------
    // Bounded copies and inventories
    // ------------------------------------------------------------------------------------

    test("an oversized local and external archive is rejected before any copy") {
        crossRunTemp { root ->
            val (archive, index, value) = mobileFixtureWithIndex(root, head, tree, lane)
            Files.write(archive, ByteArray(2048) { 'x'.code.toByte() })
            val changed = LinkedHashMap<String, JsonElement>(value)
            changed["sources"] = JsonArray(
                listOf(
                    JsonObject(
                        ((value["sources"] as JsonArray)[0] as JsonObject) + (
                            "transport" to buildJsonObject {
                                put("format", JsonPrimitive("zip"))
                                put("size", JsonPrimitive(512))
                                put("sha256", JsonPrimitive(crossRunSha256(Files.readAllBytes(archive))))
                            }
                            ),
                    ),
                ),
            )
            Files.writeString(index, JsonObject(changed).toString())
            var copies = 0
            val io = object : CollectionIo() {
                override val maxSourceBytes: Long get() = 1024
                override fun copyRegular(source: Path, destination: Path, limit: Long, preflight: Boolean): Long {
                    copies++
                    return super.copyRegular(source, destination, limit, preflight)
                }
            }
            val result = CollectionRuntime.collect(
                repositoryRoot(),
                head,
                emptyList(),
                root.resolve("collection"),
                sourceIndex = index,
                artifactsDir = root.resolve("artifacts").also { Files.createDirectories(it) },
                io = io,
            )
            assertEquals(0, copies)
            assertTrue(
                "source archive exceeds byte bound" in
                    (Py.str((((result["cross_run"] as JsonObject)["sources"] as JsonArray)[0]
                        as JsonObject)["reason"]) ?: ""),
            )
            assertTrue(
                CollectionRuntime.verifyCollection(
                    repositoryRoot(), head, emptyList(), root.resolve("collection"),
                ),
            )
            val stable = root.resolve("external")
            Files.createDirectories(stable)
            var externalCopies = 0
            val externalIo = object : CollectionIo() {
                override val maxSourceBytes: Long get() = 1024
                override fun copyRegular(source: Path, destination: Path, limit: Long, preflight: Boolean): Long {
                    externalCopies++
                    return super.copyRegular(source, destination, limit, preflight)
                }
            }
            assertTrue(
                "external archive exceeds byte bound" in (assertFailsWith<IllegalArgumentException> {
                    CollectionRuntime.snapshotExternalReferences(
                        archiveMap(head, manifest, lane, archive.toString()),
                        manifest,
                        stable,
                        externalIo,
                    )
                }.message ?: ""),
            )
            assertEquals(0, externalCopies)
        }
    }

    test("the copy stream cap preserves only the bounded partial bytes") {
        crossRunTemp { root ->
            val source = root.resolve("growing.bin")
            Files.write(source, ByteArray(2 * 1024 * 1024) { 'x'.code.toByte() })
            val frozen = root.resolve("frozen.bin")
            assertTrue(
                "exceeds byte bound while copied" in (assertFailsWith<IllegalArgumentException> {
                    CollectionRuntime.copyRegular(
                        source, frozen, 1024L * 1024 + 512, preflight = false,
                    )
                }.message ?: ""),
            )
            assertEquals(1024L * 1024 + 512, Files.size(frozen))
            val smaller = root.resolve("smaller.bin")
            assertTrue(
                "exceeds byte bound while copied" in (assertFailsWith<IllegalArgumentException> {
                    CollectionRuntime.copyRegular(source, smaller, 512L * 1024, preflight = false)
                }.message ?: ""),
            )
            assertEquals(512L * 1024, Files.size(smaller))
            assertTrue(
                "source file exceeds byte bound" in (assertFailsWith<IllegalArgumentException> {
                    CollectionRuntime.digest(source, 1024L * 1024)
                }.message ?: ""),
            )
            assertTrue(
                "source file exceeds byte bound" in (assertFailsWith<IllegalArgumentException> {
                    CollectionRuntime.copyRegular(source, root.resolve("preflight.bin"), 1024L * 1024)
                }.message ?: ""),
            )
        }
    }

    test("directory growth after inventory keeps bounded raw bytes") {
        for (route in listOf("local", "external")) {
            val limit = 1024L * 1024
            crossRunTemp { root ->
                val source = root.resolve("source")
                Files.createDirectories(source)
                val member = source.resolve("receipt.bin")
                Files.write(member, ByteArray((limit / 2).toInt()) { 'x'.code.toByte() })
                val files = CollectionRuntime.fileInventory(source)
                val index = writeIndex(
                    root,
                    head,
                    tree,
                    buildJsonObject {
                        put("id", JsonPrimitive("grown"))
                        put(
                            "origin",
                            buildJsonObject {
                                put("kind", JsonPrimitive("local"))
                                put("path", JsonPrimitive(source.toString()))
                            },
                        )
                        put(
                            "transport",
                            buildJsonObject {
                                put("format", JsonPrimitive("directory"))
                                put("files", files)
                                put("inventory_sha256", JsonPrimitive(CollectionRules.inventoryDigest(files)))
                            },
                        )
                    },
                    lane,
                    "staged-consumer",
                    null,
                    null,
                )
                var grown = false
                val io = object : CollectionIo() {
                    override val maxExpandedBytes: Long get() = limit

                    override fun inventory(root: Path): JsonObject {
                        val inventory = super.inventory(root)
                        if (root == source && !grown) {
                            grown = true
                            Files.write(
                                member,
                                ByteArray((limit * 2 + limit / 2).toInt()) { 'y'.code.toByte() },
                            )
                        }
                        return inventory
                    }
                }
                if (route == "local") {
                    val result = CollectionRuntime.collect(
                        repositoryRoot(),
                        head,
                        emptyList(),
                        root.resolve("collection"),
                        sourceIndex = index,
                        artifactsDir = root.resolve("artifacts").also { Files.createDirectories(it) },
                        io = io,
                    )
                    val row = ((result["cross_run"] as JsonObject)["sources"] as JsonArray)[0]
                        as JsonObject
                    assertEquals("FAILED", Py.str(row["status"]))
                    assertTrue("transport bounds" in (Py.str(row["reason"]) ?: ""))
                    val frozen = root.resolve(
                        "collection/raw/sources/grown/original-directory/receipt.bin",
                    )
                    assertTrue(grown)
                    assertTrue(Files.size(frozen) in 1..limit)
                    assertEquals(
                        Files.size(frozen),
                        Py.int(((row["raw_inventory"] as JsonObject)
                            .getValue("receipt.bin") as JsonObject)["size"]!!),
                    )
                    assertTrue(
                        CollectionRuntime.verifyCollection(
                            repositoryRoot(), head, emptyList(), root.resolve("collection"),
                        ),
                    )
                } else {
                    val stable = root.resolve("stable")
                    Files.createDirectories(stable)
                    assertTrue(
                        "transport bounds" in (assertFailsWith<IllegalArgumentException> {
                            CollectionRuntime.snapshotExternalReferences(
                                archiveMap(head, manifest, lane, source.toString()),
                                manifest,
                                stable,
                                io,
                            )
                        }.message ?: ""),
                    )
                    assertTrue(grown)
                    assertTrue(Files.size(stable.resolve("references/0/receipt.bin")) in 1..limit)
                }
            }
        }
    }

    test("member growth after inventory keeps a bounded raw inventory") {
        crossRunTemp { root ->
            val source = root.resolve("source")
            Files.createDirectories(source)
            source.resolve("one.bin").writeText("one")
            source.resolve("two.bin").writeText("two")
            val files = CollectionRuntime.fileInventory(source)
            val index = writeIndex(
                root,
                head,
                tree,
                buildJsonObject {
                    put("id", JsonPrimitive("grown"))
                    put(
                        "origin",
                        buildJsonObject {
                            put("kind", JsonPrimitive("local"))
                            put("path", JsonPrimitive(source.toString()))
                        },
                    )
                    put(
                        "transport",
                        buildJsonObject {
                            put("format", JsonPrimitive("directory"))
                            put("files", files)
                            put("inventory_sha256", JsonPrimitive(CollectionRules.inventoryDigest(files)))
                        },
                    )
                },
                lane,
                "staged-consumer",
                null,
                null,
            )
            var grown = false
            val io = object : CollectionIo() {
                override val maxMembers: Int get() = 2

                override fun inventory(root: Path): JsonObject {
                    val inventory = super.inventory(root)
                    if (root == source && !grown) {
                        grown = true
                        source.resolve("three.bin").writeText("three")
                    }
                    return inventory
                }
            }
            val result = CollectionRuntime.collect(
                repositoryRoot(),
                head,
                emptyList(),
                root.resolve("collection"),
                sourceIndex = index,
                artifactsDir = root.resolve("artifacts").also { Files.createDirectories(it) },
                io = io,
            )
            val row = ((result["cross_run"] as JsonObject)["sources"] as JsonArray)[0] as JsonObject
            assertEquals("FAILED", Py.str(row["status"]))
            assertTrue("transport bounds" in (Py.str(row["reason"]) ?: ""))
            val frozen = root.resolve("collection/raw/sources/grown/original-directory")
            val children = Files.newDirectoryStream(frozen).use { it.toList() }
            assertTrue(children.size <= 2)
            assertEquals(children.size, (row["raw_inventory"] as JsonObject).size)
            assertTrue(
                CollectionRuntime.verifyCollection(
                    repositoryRoot(), head, emptyList(), root.resolve("collection"),
                ),
            )
        }
    }

    // ------------------------------------------------------------------------------------
    // Workflow route
    // ------------------------------------------------------------------------------------

    test("the workflow exposes the cross-run route without recapturing producers") {
        val workflow = Files.readString(
            repositoryRoot().resolve(".github/workflows/qualification.yml"),
        )
        assertTrue("cross_run_only:\n" in workflow)
        assertTrue("cross_run_source_index:\n" in workflow)
        for (job in listOf("staged-jvm-and-linux", "hosted-publications", "hosted-native")) {
            val body = workflow.split("  $job:\n", limit = 2)[1].split("\n  ", limit = 2)[0]
            assertTrue("inputs.cross_run_only != true" in body, job)
        }
        val central = workflow.split("  central-qualification-collection:\n", limit = 2)[1]
        assertTrue(
            central.indexOf("Download every retained producer artifact") <
                central.indexOf("Retain explicit cross-run source index"),
        )
        assertTrue(
            central.indexOf("Retain explicit cross-run source index") <
                central.indexOf("Provision pinned upstream source for raw replay"),
        )
        for (contract in listOf(
            "actions: read", "contents: read", "--source-index", "--run-id", "--run-attempt",
            "DYN4K_GITHUB_TOKEN", "\${{ github.token }}",
            "\${{ runner.temp }}/cross-run-source-index.json",
        )) {
            assertTrue(contract in central, contract)
        }
    }
}

// ----------------------------------------------------------------------------------------
// Fixtures
// ----------------------------------------------------------------------------------------

/** The captured adapter command of one signed handoff, shared with the io seam. */
private var captured: List<String>? = null

private fun crossRunTemp(block: (Path) -> Unit) {
    val root = Files.createTempDirectory("cross-run-suite")
    try {
        block(root)
    } finally {
        crossRunDelete(root)
    }
}

private fun crossRunDelete(root: Path) {
    if (!Files.exists(root)) return
    Files.walk(root).use { walk ->
        walk.sorted(Comparator.reverseOrder()).forEach {
            try {
                Files.setPosixFilePermissions(it, PosixFilePermissions.fromString("rwx------"))
            } catch (error: Exception) {
                // A directory that is already removable needs no permission change.
            }
            Files.deleteIfExists(it)
        }
    }
}

internal fun crossRunSha256(bytes: ByteArray): String =
    java.security.MessageDigest.getInstance("SHA-256").digest(bytes)
        .joinToString("") { "%02x".format(it) }

private fun validateIndex(value: JsonObject, runId: Long?, runAttempt: Long?, allowLocal: Boolean = true) {
    CollectionRules.validateIndex(
        value,
        hostedGit(repositoryRoot(), "rev-parse", "HEAD").trim(),
        CollectionRuntime.sourceTree(
            repositoryRoot(),
            hostedGit(repositoryRoot(), "rev-parse", "HEAD").trim(),
        ),
        IndependentGates.loadApprovedManifest(repositoryRoot()),
        "rubixhacker/dyn4k",
        runId,
        runAttempt,
        allowLocal,
        { path -> CollectionRuntime.safeSourcePathText(path) },
        IndependentGates.GLOBAL_GATES,
    )
}

private fun writeStageReceipt(path: Path, head: String) {
    path.parent?.let { Files.createDirectories(it) }
    path.writeText(
        buildJsonObject {
            put("candidate_sha", JsonPrimitive(head))
            put("targets", JsonArray(listOf(JsonPrimitive("tvosSimulatorArm64"))))
        }.toString(),
    )
}

/** One `mobile.zip` plus the index the reference's `fixture()` builds. */
private fun mobileFixture(
    root: Path,
    head: String,
    tree: String,
    lane: String,
    members: Map<String, String>? = null,
): Pair<Path, Path> {
    val archive = root.resolve("mobile.zip")
    writeMobileZip(archive, head, members)
    val index = writeZipIndex(root, head, tree, archive, lane)
    return archive to index
}

private fun mobileFixtureWithIndex(
    root: Path,
    head: String,
    tree: String,
    lane: String,
): Triple<Path, Path, JsonObject> {
    val archive = root.resolve("mobile.zip")
    writeMobileZip(archive, head)
    val value = mobileIndex(head, tree, archive, lane)
    val path = root.resolve("index.json")
    path.writeText(value.toString())
    return Triple(archive, path, value)
}

private fun writeMobileZip(archive: Path, head: String, members: Map<String, String>? = null) {
    val entries = members ?: linkedMapOf(
        "build/stage-receipt.json" to buildJsonObject {
            put("candidate_sha", JsonPrimitive(head))
            put("targets", JsonArray(listOf(JsonPrimitive("tvosSimulatorArm64"))))
        }.toString(),
        "captures/compatibility/result.json" to buildJsonObject {
            put("source_sha", JsonPrimitive(head))
            put("target", JsonPrimitive("tvosSimulatorArm64"))
            put("format", JsonPrimitive("portable-mobile-capture-v1"))
            put("qualification", JsonPrimitive("unpassed"))
        }.toString(),
    )
    ZipArchiveOutputStream(Files.newOutputStream(archive)).use { packed ->
        for ((name, value) in entries) {
            val entry = ZipArchiveEntry(name)
            val bytes = value.toByteArray()
            entry.size = bytes.size.toLong()
            packed.putArchiveEntry(entry)
            packed.write(bytes)
            packed.closeArchiveEntry()
        }
    }
}

private fun mobileIndex(head: String, tree: String, archive: Path, lane: String): JsonObject =
    buildJsonObject {
        put("schema", JsonPrimitive(1))
        put("candidate_sha", JsonPrimitive(head))
        put("source_tree", JsonPrimitive(tree))
        put(
            "sources",
            JsonArray(
                listOf(
                    buildJsonObject {
                        put("id", JsonPrimitive("mobile"))
                        put(
                            "origin",
                            buildJsonObject {
                                put("kind", JsonPrimitive("local"))
                                put("path", JsonPrimitive(archive.toString()))
                            },
                        )
                        put(
                            "transport",
                            buildJsonObject {
                                put("format", JsonPrimitive("zip"))
                                put("size", JsonPrimitive(Files.size(archive)))
                                put("sha256", JsonPrimitive(crossRunSha256(Files.readAllBytes(archive))))
                            },
                        )
                    },
                ),
            ),
        )
        put(
            "bindings",
            JsonArray(
                listOf(
                    buildJsonObject {
                        put("source_id", JsonPrimitive("mobile"))
                        put("lane", JsonNull)
                        put("gate", JsonPrimitive("performance-resource"))
                        put("target", JsonPrimitive("tvosSimulatorArm64"))
                    },
                ),
            ),
        )
        lane
    }

private fun writeZipIndex(
    root: Path,
    head: String,
    tree: String,
    archive: Path,
    lane: String,
    format: String = "zip",
): Path {
    val value = buildJsonObject {
        put("schema", JsonPrimitive(1))
        put("candidate_sha", JsonPrimitive(head))
        put("source_tree", JsonPrimitive(tree))
        put(
            "sources",
            JsonArray(
                listOf(
                    buildJsonObject {
                        put("id", JsonPrimitive("mobile"))
                        put(
                            "origin",
                            buildJsonObject {
                                put("kind", JsonPrimitive("local"))
                                put("path", JsonPrimitive(archive.toString()))
                            },
                        )
                        put(
                            "transport",
                            buildJsonObject {
                                put("format", JsonPrimitive(format))
                                put("size", JsonPrimitive(Files.size(archive)))
                                put("sha256", JsonPrimitive(crossRunSha256(Files.readAllBytes(archive))))
                            },
                        )
                    },
                ),
            ),
        )
        put(
            "bindings",
            JsonArray(
                listOf(
                    buildJsonObject {
                        put("source_id", JsonPrimitive("mobile"))
                        put("lane", JsonNull)
                        put("gate", JsonPrimitive("performance-resource"))
                        put("target", JsonPrimitive("tvosSimulatorArm64"))
                    },
                ),
            ),
        )
    }
    val path = root.resolve("index.json")
    path.writeText(value.toString())
    return path
}

/** One index with a single `local` source and one lane binding. */
private fun writeIndex(
    root: Path,
    head: String,
    tree: String,
    source: JsonObject,
    lane: String,
    gate: String,
    target: String?,
    unusedDigest: String?,
): Path {
    val binding = buildJsonObject {
        put("source_id", source["id"] ?: JsonNull)
        put("lane", JsonPrimitive(lane))
        put("gate", JsonPrimitive(gate))
    }
    val value = buildJsonObject {
        put("schema", JsonPrimitive(1))
        put("candidate_sha", JsonPrimitive(head))
        put("source_tree", JsonPrimitive(tree))
        put("sources", JsonArray(listOf(source)))
        put("bindings", JsonArray(listOf(binding)))
    }
    val path = root.resolve("index.json")
    path.writeText(value.toString())
    return path
}

private fun collectFixture(root: Path, index: Path): JsonObject {
    val artifacts = root.resolve("artifacts")
    Files.createDirectories(artifacts)
    return CollectionRuntime.collect(
        repositoryRoot(),
        hostedGit(repositoryRoot(), "rev-parse", "HEAD").trim(),
        emptyList(),
        root.resolve("collection"),
        sourceIndex = index,
        artifactsDir = artifacts,
    )
}

private fun archiveMap(
    head: String,
    manifest: JsonObject,
    lane: String,
    archive: String,
): JsonObject {
    val lanes = LinkedHashMap<String, JsonElement>()
    for (id in (manifest["lanes"] as JsonObject).keys) {
        lanes[id] = buildJsonObject { }
    }
    lanes[lane] = buildJsonObject { put("staged-consumer", JsonPrimitive(archive)) }
    return buildJsonObject {
        put("schema", JsonPrimitive(1))
        put("candidate_sha", JsonPrimitive(head))
        put("lanes", JsonObject(lanes))
    }
}

/** One recorded HTTP response for the GitHub provenance seam. */
private fun fakeResponse(request: HttpRequest, body: ByteArray): HttpResponse<ByteArray> =
    object : HttpResponse<ByteArray> {
        override fun statusCode(): Int = 200
        override fun request(): HttpRequest = request
        override fun previousResponse(): java.util.Optional<HttpResponse<ByteArray>> =
            java.util.Optional.empty()
        override fun headers(): java.net.http.HttpHeaders =
            java.net.http.HttpHeaders.of(emptyMap()) { _, _ -> true }
        override fun body(): ByteArray = body
        override fun sslSession(): java.util.Optional<javax.net.ssl.SSLSession> =
            java.util.Optional.empty()
        override fun uri(): java.net.URI = request.uri()
        override fun version(): HttpClient.Version = HttpClient.Version.HTTP_1_1
    }

/**
 * `regular_directory_swap`: every enumeration of the approved directory is performed while the
 * alternate directory stands in for it, and the swap is undone before the names are consumed.
 *
 * The reference keys this on the enumerated descriptor's inode and restores in a `finally`; the
 * port keys it on the anchor's `fileKey` and restores the same way, so the count of swaps is the
 * count of enumerations of the approved directory.
 */
private class RegularDirectorySwap(
    private val source: Path,
    private val alternate: Path,
) : CollectionIo() {
    var swaps: Int = 0
        private set
    private val identity: Any? = Files.readAttributes(
        source,
        java.nio.file.attribute.BasicFileAttributes::class.java,
    ).fileKey()

    override fun directoryNames(anchor: Path): List<String> {
        val names = super.directoryNames(anchor)
        val key = Files.readAttributes(
            anchor,
            java.nio.file.attribute.BasicFileAttributes::class.java,
        ).fileKey()
        if (key == null || key != identity) return names
        val parked = source.resolveSibling(source.fileName.toString() + "-parked")
        Files.move(source, parked)
        Files.move(alternate, source)
        swaps++
        try {
            return names
        } finally {
            Files.move(source, alternate)
            Files.move(parked, source)
        }
    }
}

private fun regularDirectorySwap(source: Path, alternate: Path): RegularDirectorySwap =
    RegularDirectorySwap(source, alternate)

/** One `directory` source of the cross-run index, pinned to an explicit file inventory. */
private fun directorySource(source: Path, files: JsonObject): JsonObject = buildJsonObject {
    put("id", JsonPrimitive("rawdir"))
    put(
        "origin",
        buildJsonObject {
            put("kind", JsonPrimitive("local"))
            put("path", JsonPrimitive(source.toString()))
        },
    )
    put(
        "transport",
        buildJsonObject {
            put("format", JsonPrimitive("directory"))
            put("files", files)
            put("inventory_sha256", JsonPrimitive(CollectionRules.inventoryDigest(files)))
        },
    )
}
