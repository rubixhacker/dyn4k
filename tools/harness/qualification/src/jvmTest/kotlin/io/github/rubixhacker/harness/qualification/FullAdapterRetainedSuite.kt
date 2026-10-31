package io.github.rubixhacker.harness.qualification

import de.infix.testBalloon.framework.core.testSuite
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.StandardCopyOption
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

private fun retainedMessageContains(expected: String, body: () -> Unit) {
    val error = assertFailsWith<IllegalArgumentException> { body() }
    assertTrue(
        (error.message ?: "").contains(expected),
        "expected '$expected' in '${error.message}'",
    )
}

/**
 * `test_full_android_adapter.py`'s four retained cases.
 *
 * They need `DYN4K_RETAINED_ANDROID_EVIDENCE` (the reference's `skipUnless`); a bare host registers
 * and disables them. Each case keeps the reference's assertion sequence; the public replay itself is
 * `full_android_consumer.verify_archive`, which is still a named seam, so an enabled run fails with
 * that exact reason rather than passing.
 */
val FullAndroidAdapterRetained by testSuite {
    val config = retainedEvidenceConfig("DYN4K_RETAINED_ANDROID_EVIDENCE")
    val root = System.getenv("DYN4K_RETAINED_ANDROID_EVIDENCE")

    data class Row(
        val lane: String,
        val checkout: String,
        val archive: String,
        val candidate: String,
        val digest: String,
        val runtime: String,
        val source: String,
    )

    val routes = listOf(
        Row(
            "android:Android JVM:minimum:debug",
            "full-android-api21-bb2-sol-run/replay-checkout",
            "full-android-api21-bb2-sol-run/archives/api21-x64-debug-1",
            "09ef68ead49c0be97ebc0422b918845978a7421e",
            "9126d7c4da87f5df9978cf8647a73d22cd3470df1d7d9b0329b3f4ddf303436e",
            "7bfd8373dbd54adbd89494ceb745d15a1bba09fb987b380a1745f3a22695c072",
            "8bb8af96a50dbf6182b21540c2075300879bb032b74a9f709f6778160e08dc5a",
        ),
        Row(
            "android:Android JVM:minimum:r8-optimized",
            "full-android-api21-bb2-sol-run/replay-checkout",
            "full-android-api21-bb2-sol-run/archives/api21-x64-r8-1",
            "09ef68ead49c0be97ebc0422b918845978a7421e",
            "89cbaee3d01167f044b4195dd37848648dd5a0df52e15a4081213641a5636f55",
            "1bff0cc2ce2a323ae5d30143d4fc95e45f9bdaab9b66e3e5af1b40ca5a6b10a1",
            "8bb8af96a50dbf6182b21540c2075300879bb032b74a9f709f6778160e08dc5a",
        ),
        Row(
            "android:Android JVM:current:debug",
            "full-staged-android-112-sol-final/replay-checkout",
            "full-staged-android-112-sol-final/api37-debug",
            "415acaacc4415ca1b2d2fa4abda0b6c6c78f9d4a",
            "5e38aa2ddc28934672c887111cb1a39947aa29f98f3543d6754a687e7a776f3e",
            "824f227a12e410ffb5bd07ff5bde9dc9e207d649b3570c24eaf4f06b9b1ee296",
            "89c057851c524665a4f7024f3b461b5e2bd10b4924c7aeb3a61c1445abc3f036",
        ),
        Row(
            "android:Android JVM:current:r8-optimized",
            "full-staged-android-112-sol-final/replay-checkout",
            "full-staged-android-112-sol-final/api37-release",
            "415acaacc4415ca1b2d2fa4abda0b6c6c78f9d4a",
            "7f6d38a88e61137a6bd17a770c80d2c15e1b77c2c086e4b4df8ae3dacb43cd50",
            "a2e7c7fc58f02b25e6464036ec7a22c775efadfce95b99007fd9c41684ea6657",
            "89c057851c524665a4f7024f3b461b5e2bd10b4924c7aeb3a61c1445abc3f036",
        ),
    )

    val hashes = mapOf(
        "dyn4k-core" to "9eaf8113aa62365b2ca0a4a9e5fe13615271ad2e22f3a8c414633ffcde824a53",
        "dyn4k" to "352e3433ba8af93ad7ace849b0baa4abd35cf5262c8aead9109e9c140c8547ed",
    )

    fun inputs(row: Row): List<Any> {
        val evidence = Path.of(root!!)
        val checkout = evidence.resolve(row.checkout)
        val archive = evidence.resolve(row.archive)
        val (manifest, cases) = RetainedAndroidConsumer.approvedCases(checkout)
        val selected = buildJsonObject {
            put("case_ids", JsonArray(cases.map { it["id"] as JsonElement }))
        }
        val expected = buildJsonObject {
            put(
                "expected_artifact_hashes",
                JsonObject(hashes.mapValues { JsonPrimitive(it.value) }),
            )
            put("expected_runtime_identity", JsonPrimitive(row.runtime))
            put(
                "expected_archive_digests",
                buildJsonObject { put("staged-consumer", JsonPrimitive(row.digest)) },
            )
            put("expected_android_source_toolchain_sha256", JsonPrimitive(row.source))
        }
        val lane = (manifest["lanes"] as JsonObject).getValue(row.lane) as JsonObject
        val gate = GatesAggregate.evaluateGate(
            "staged-consumer",
            archive,
            row.candidate,
            row.lane,
            lane,
            checkout,
            hashes,
            row.runtime,
            expectedArchiveDigest = row.digest,
            manifest = manifest,
        )
        return listOf(checkout, row.candidate, row.lane, selected, archive, expected, gate)
    }

    test("the four retained complete Android routes", config) {
        for (row in routes) {
            val arguments = inputs(row)
            @Suppress("UNCHECKED_CAST")
            val gate = arguments[6] as JsonObject
            assertEquals("PASSED", Py.str(gate["status"]), row.lane)
            val public = FullAndroidAdapter.verify(
                arguments[0] as Path,
                arguments[1] as String,
                arguments[2] as String,
                arguments[3] as JsonObject,
                arguments[4] as Path,
                arguments[5] as JsonObject,
                gate,
                RetainedAndroidConsumer,
            )
            assertEquals(2523L, Py.int(public["cases"]!!))
            assertEquals(gate, public["gate"])
        }
    }

    test("missing and wrong signed Android expectations fail", config) {
        val arguments = inputs(routes[0])
        val checkout = arguments[0] as Path
        val candidate = arguments[1] as String
        val lane = arguments[2] as String
        val selected = arguments[3] as JsonObject
        val archive = arguments[4] as Path
        val expected = arguments[5] as JsonObject
        val gate = arguments[6] as JsonObject
        fun call(changed: JsonObject, selectedIds: JsonObject = selected) =
            RetainedAndroidConsumer.let {
                FullAndroidAdapter.verify(
                    checkout, candidate, lane, selectedIds, archive, changed, gate,
                    RetainedAndroidConsumer,
                )
            }
        for (field in listOf(
            "expected_android_source_toolchain_sha256",
            "expected_runtime_identity",
            "expected_archive_digests",
        )) {
            val changed = JsonObject(LinkedHashMap(expected).apply { remove(field) })
            assertFailsWith<IllegalArgumentException>(field) { call(changed) }
        }
        val wrongSource = JsonObject(
            LinkedHashMap(expected).apply {
                this["expected_android_source_toolchain_sha256"] = JsonPrimitive("a".repeat(64))
            },
        )
        retainedMessageContains("source/toolchain digest differs") { call(wrongSource) }
        val wrongRuntime = JsonObject(
            LinkedHashMap(expected).apply {
                this["expected_runtime_identity"] = JsonPrimitive("a".repeat(64))
            },
        )
        assertFailsWith<IllegalArgumentException> { call(wrongRuntime) }
        val wrongDigest = JsonObject(
            LinkedHashMap(expected).apply {
                this["expected_archive_digests"] = buildJsonObject {
                    put("staged-consumer", JsonPrimitive("a".repeat(64)))
                }
            },
        )
        assertFailsWith<IllegalArgumentException> { call(wrongDigest) }
        val wrongArtifact = JsonObject(
            LinkedHashMap(expected).apply {
                this["expected_artifact_hashes"] = buildJsonObject {
                    put("dyn4k-core", JsonPrimitive("a".repeat(64)))
                    put("dyn4k", JsonPrimitive(hashes.getValue("dyn4k")))
                }
            },
        )
        assertFailsWith<IllegalArgumentException> { call(wrongArtifact) }
        val shortIds = (selected["case_ids"] as JsonArray).dropLast(1)
        val fewer = buildJsonObject { put("case_ids", JsonArray(shortIds)) }
        retainedMessageContains("different approved case suite") { call(expected, fewer) }
    }

    test("a wrong lane, candidate, and gate fail", config) {
        val arguments = inputs(routes[0])
        val checkout = arguments[0] as Path
        val candidate = arguments[1] as String
        val lane = arguments[2] as String
        val selected = arguments[3] as JsonObject
        val archive = arguments[4] as Path
        val expected = arguments[5] as JsonObject
        val gate = arguments[6] as JsonObject
        for ((index, value) in listOf(1 to routes[2].candidate, 2 to "android:Android JVM:minimum:unsupported")) {
            val actualCandidate = if (index == 1) value else candidate
            val actualLane = if (index == 2) value else lane
            assertFailsWith<IllegalArgumentException> {
                FullAndroidAdapter.verify(
                    checkout, actualCandidate, actualLane, selected, archive, expected, gate,
                    RetainedAndroidConsumer,
                )
            }
        }
        val changedGate = buildJsonObject {
            for ((key, value) in gate) put(key, value)
            put("selected_cases", JsonPrimitive(1))
        }
        retainedMessageContains("differs from independent gate") {
            FullAndroidAdapter.verify(
                checkout, candidate, lane, selected, archive, expected, changedGate,
                RetainedAndroidConsumer,
            )
        }
    }

    test("a resealed process tamper fails the public replay", config) {
        val arguments = inputs(routes[0])
        val checkout = arguments[0] as Path
        val candidate = arguments[1] as String
        val lane = arguments[2] as String
        val selected = arguments[3] as JsonObject
        val gate = arguments[6] as JsonObject
        val tampered = Path.of(root!!)
            .resolve("full-android-api21-bb2-sol-run/archives/api21-x64-debug-ps-tampered")
        val expected = buildJsonObject {
            put(
                "expected_artifact_hashes",
                JsonObject(hashes.mapValues { JsonPrimitive(it.value) }),
            )
            put("expected_runtime_identity", JsonPrimitive(routes[0].runtime))
            put(
                "expected_archive_digests",
                buildJsonObject {
                    put(
                        "staged-consumer",
                        JsonPrimitive(
                            "a23139ee41b4260924ed0d3bda36655d8090d23122c287a260586343abcfac1f",
                        ),
                    )
                },
            )
            put(
                "expected_android_source_toolchain_sha256",
                JsonPrimitive(routes[0].source),
            )
        }
        retainedMessageContains("process snapshots differ") {
            FullAndroidAdapter.verify(
                checkout, candidate, lane, selected, tampered, expected, gate,
                RetainedAndroidConsumer,
            )
        }
    }
}

private const val KLIB_RUNTIME = "Linux 7.2.9-ogc3.1.fc44.x86_64 x86_64 | " +
    "openjdk version \"21.0.12.1\" 2026-08-18 LTS | v26.10.0"
private const val KLIB_CANDIDATE_SHA = "d629b9e388db08b3c7e24b22ff853ac387b951ce"

/**
 * `test_full_klib_adapter.py`'s four retained cases, gated on `DYN4K_KLIB_EVIDENCE_ROOT`.
 *
 * The contract and staged-binary helpers are ported for real; the public replay
 * (`full_klib_consumer.verify`) is still a named seam, so an enabled run fails with that reason.
 */
val FullKlibAdapterRetained by testSuite {
    val config = retainedEvidenceConfig("DYN4K_KLIB_EVIDENCE_ROOT")
    val evidenceRoot = System.getenv("DYN4K_KLIB_EVIDENCE_ROOT")

    data class Lane(
        val id: String,
        val name: String,
        val variant: String,
        val digest: String,
    )

    val lanes = listOf(
        Lane(
            "linuxX64:Linux x64:current:debug-g",
            "native",
            "linuxx64",
            "9e84cd8c31a382598fd734f2d043dc69d5afc43102e7b125f4eabbfa4b18c7a1",
        ),
        Lane(
            "js:Node.js:current:development",
            "js",
            "js",
            "3aa17d2e02a8d3f5de38f5bbec57e41de80e18686d37b3f8f5c6107f855a1f6c",
        ),
    )

    class Evidence(val archive: Path, val expected: JsonObject, val ids: List<String>,
        val generic: JsonObject, val hashes: JsonObject)

    fun evidence(lane: Lane): Evidence {
        val root = Path.of(evidenceRoot!!)
        val archive = root.resolve("full-staged-klib-112-sol-${lane.name}-d629-transported")
        val trusted = (loadJson(
            root.resolve("full-staged-klib-112-sol-trusted-${lane.name}-toolchain.json"),
        ) as JsonObject)
        val stage = root.resolve("full-staged-klib-112-sol-stage-copy")
        val hashes = buildJsonObject {
            for (module in FullKlibAdapterRules.MODULES) {
                put(
                    module,
                    JsonPrimitive(
                        FullStagedConsumer.sha(
                            Files.readAllBytes(
                                FullKlibContract.stagedBinary(stage, module, lane.variant),
                            ),
                        ),
                    ),
                )
            }
        }
        val expected = buildJsonObject {
            put("expected_artifact_hashes", hashes)
            put("expected_runtime_identity", JsonPrimitive(KLIB_RUNTIME))
            put(
                "expected_archive_digests",
                buildJsonObject { put("staged-consumer", JsonPrimitive(lane.digest)) },
            )
            put("expected_klib_toolchain", trusted)
            put(
                "expected_klib_executables",
                buildJsonObject {
                    put("gradle", JsonPrimitive("/tmp/dyn4k-tools/gradle-9.5.0/bin/gradle"))
                    put("node", JsonPrimitive("/usr/local/bin/node"))
                },
            )
        }
        val (manifest, selected) = FullKlibContract.load(repositoryRoot(), lane.id)
        val ids = (selected["cases"] as JsonArray).map { (it as JsonObject)["id"] as JsonElement }
            .map { Py.str(it)!! }
        val laneContract = (manifest["lanes"] as JsonObject).getValue(lane.id) as JsonObject
        val hashMap = hashes.mapValues { (_, value) -> Py.str(value)!! }
        val generic = GatesAggregate.evaluateGate(
            "staged-consumer",
            archive,
            KLIB_CANDIDATE_SHA,
            lane.id,
            laneContract,
            repositoryRoot(),
            hashMap,
            KLIB_RUNTIME,
            expectedArchiveDigest = lane.digest,
            manifest = manifest,
        )
        if (Py.str(generic["status"]) != "PASSED") {
            throw AssertionError("retained generic KLIB gate failed: $generic")
        }
        return Evidence(archive, expected, ids, generic, hashes)
    }

    test("the real Linux and Node signed inputs replay", config) {
        for (lane in lanes) {
            val entry = evidence(lane)
            assertEquals(
                entry.expected["expected_archive_digests"]
                    ?.let { (it as JsonObject)["staged-consumer"] },
                JsonPrimitive(ArchiveScan.digest(entry.archive)),
                lane.id,
            )
            val result = FullKlibAdapter.verify(
                repositoryRoot(),
                KLIB_CANDIDATE_SHA,
                lane.id,
                entry.ids,
                entry.archive,
                entry.generic,
                entry.expected,
                entry.hashes,
                RetainedKlibConsumer,
            )
            assertEquals(entry.generic, result)
            assertEquals(2523L, Py.int(result["selected_cases"]!!))
        }
    }

    test("the real archive rejects incomplete and wrong audits", config) {
        val lane = lanes[1]
        val entry = evidence(lane)
        fun call(expected: JsonObject, ids: List<String> = entry.ids, hashes: JsonObject = entry.hashes) =
            FullKlibAdapter.verify(
                repositoryRoot(), KLIB_CANDIDATE_SHA, lane.id, ids, entry.archive,
                entry.generic, expected, hashes, RetainedKlibConsumer,
            )
        val missingRuntime = JsonObject(
            LinkedHashMap(entry.expected).apply { remove("expected_runtime_identity") },
        )
        retainedMessageContains("runtime or archive digest is incomplete") {
            call(missingRuntime)
        }
        val wrongRuntime = JsonObject(
            LinkedHashMap(entry.expected).apply {
                this["expected_runtime_identity"] = JsonPrimitive("wrong")
            },
        )
        retainedMessageContains("runtime identity differs") { call(wrongRuntime) }
        val wrongDigest = JsonObject(
            LinkedHashMap(entry.expected).apply {
                this["expected_archive_digests"] = buildJsonObject {
                    put("staged-consumer", JsonPrimitive("0".repeat(64)))
                }
            },
        )
        retainedMessageContains("archive digest differs") { call(wrongDigest) }
        val missingToolchain = JsonObject(
            LinkedHashMap(entry.expected).apply { remove("expected_klib_toolchain") },
        )
        retainedMessageContains("toolchain identity is incomplete") { call(missingToolchain) }
        val trusted = entry.expected["expected_klib_toolchain"] as JsonObject
        val wrongNode = JsonObject(
            LinkedHashMap(entry.expected).apply {
                this["expected_klib_toolchain"] = JsonObject(
                    LinkedHashMap(trusted).apply {
                        this["node_sha256"] = JsonPrimitive("0".repeat(64))
                    },
                )
            },
        )
        retainedMessageContains("Node executable SHA-256 differs") { call(wrongNode) }
        retainedMessageContains("different approved case suite") {
            call(entry.expected, entry.ids.dropLast(1))
        }
        retainedMessageContains("audited target") {
            call(
                entry.expected,
                hashes = JsonObject(
                    LinkedHashMap(entry.hashes).apply {
                        this["dyn4k"] = JsonPrimitive("0".repeat(64))
                    },
                ),
            )
        }
    }

    test("the real archive rejects a wrong supported lane", config) {
        val nodeLane = lanes[1]
        val nativeLane = lanes[0]
        val node = evidence(nodeLane)
        val native = evidence(nativeLane)
        assertTrue(node.archive != native.archive)
        val altered = JsonObject(
            LinkedHashMap(node.expected).apply {
                this["expected_archive_digests"] = buildJsonObject {
                    put(
                        "staged-consumer",
                        JsonPrimitive(ArchiveScan.digest(native.archive)),
                    )
                }
            },
        )
        retainedMessageContains("receipt differs from exact approved") {
            FullKlibAdapter.verify(
                repositoryRoot(), KLIB_CANDIDATE_SHA, nodeLane.id, node.ids, native.archive,
                node.generic, altered, node.hashes, RetainedKlibConsumer,
            )
        }
    }

    test("a resealed changed bundle cannot execute node", config) {
        val lane = lanes[1]
        val entry = evidence(lane)
        val root = Files.createTempDirectory("dyn4k-klib-adapter-")
        try {
            val changed = root.resolve("archive")
            Files.walk(entry.archive).use { walk ->
                walk.forEach { path ->
                    val target = changed.resolve(entry.archive.relativize(path).toString())
                    if (Files.isDirectory(path)) {
                        Files.createDirectories(target)
                    } else {
                        target.parent?.let { Files.createDirectories(it) }
                        Files.copy(path, target, StandardCopyOption.COPY_ATTRIBUTES)
                    }
                }
            }
            val receiptPath = changed.resolve("receipt.json")
            val receipt = loadJson(receiptPath) as JsonObject
            val program = Files.walk(changed.resolve("runtime/bundle/core")).use { walk ->
                walk.filter { it.fileName.toString().endsWith("-core-test.js") }.findFirst()
                    .orElseThrow { AssertionError("no Node bundle in the retained archive") }
            }
            Files.write(program, Files.readAllBytes(program) + "\nchanged bundle\n".toByteArray())
            val relative = changed.relativize(program).toString().replace('\\', '/')
            val rows = (receipt["files"] as JsonArray).map { it as JsonObject }
            val row = rows.first { Py.str(it["path"]) == relative }
            Files.setLastModifiedTime(
                program,
                java.nio.file.attribute.FileTime.from(
                    Py.int(row["mtime_ns"]!!),
                    java.util.concurrent.TimeUnit.NANOSECONDS,
                ),
            )
            val changedRows = rows.map { item ->
                if (Py.str(item["path"]) == relative) {
                    JsonObject(
                        LinkedHashMap(item).apply {
                            this["sha256"] = JsonPrimitive(
                                FullStagedConsumer.sha(Files.readAllBytes(program)),
                            )
                        },
                    )
                } else {
                    item
                }
            }
            val changedReceipt = LinkedHashMap(receipt).apply {
                this["files"] = JsonArray(changedRows)
            }
            Files.write(
                receiptPath,
                FullStagedConsumer.encoded(JsonObject(changedReceipt)) + "\n".toByteArray(),
            )
            val altered = JsonObject(
                LinkedHashMap(entry.expected).apply {
                    this["expected_archive_digests"] = buildJsonObject {
                        put("staged-consumer", JsonPrimitive(ArchiveScan.digest(changed)))
                    }
                },
            )
            retainedMessageContains("Node runtime process differs") {
                FullKlibAdapter.verify(
                    repositoryRoot(), KLIB_CANDIDATE_SHA, lane.id, entry.ids, changed,
                    entry.generic, altered, entry.hashes, RetainedKlibConsumer,
                )
            }
        } finally {
            Files.walk(root).use { walk ->
                walk.sorted(Comparator.reverseOrder()).forEach { Files.deleteIfExists(it) }
            }
        }
    }
}

/** `independent_gates._json` for the retained fixtures. */
private fun loadJson(path: Path): JsonElement =
    io.github.rubixhacker.harness.contract.StrictJson.load(Files.readString(path))
