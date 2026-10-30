package io.github.rubixhacker.harness.qualification

import de.infix.testBalloon.framework.core.testSuite
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.attribute.FileTime
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
 * `independent_gates.py`, first slice, against reference vectors.
 *
 * Each case materialises the recorded raw archive and calls one verifier; the reference verdict
 * (a returned value or an exact message) must be reproduced.
 */
val IndependentGateContract by testSuite {
    val vector = TestVectors.root.objectAt("gates")

    test("process proofs accept the recorded launchers and reject the rest") {
        for (entry in vector.getValue("process_proof") as JsonArray) {
            val record = entry as JsonObject
            withGateRoot { root ->
                materialize(root, record)
                val process = record.objectAt("process")
                val gate = record.primitive("gate")
                val lane = record.primitive("lane")
                val expected = record.objectAt("result")
                if ("ok" in expected) {
                    assertEquals(
                        expected.primitive("ok"),
                        IndependentGates.processProof(root, process, gate, lane),
                    )
                } else {
                    val error = assertFailsWith<IllegalArgumentException> {
                        IndependentGates.processProof(root, process, gate, lane)
                    }
                    assertEquals(expected.primitive("error"), error.message)
                }
            }
        }
    }

    test("duplicate provider diagnosis requires a failing consumer task") {
        for (entry in vector.getValue("duplicate_provider") as JsonArray) {
            val record = entry as JsonObject
            withGateRoot { root ->
                materialize(root, record)
                val expected = record.objectAt("result")
                if ("ok" in expected) {
                    assertEquals(
                        expected.primitive("ok"),
                        IndependentGates.duplicateProvider(
                            root, record.objectAt("receipt"), record.objectAt("process"),
                        ),
                    )
                } else {
                    val error = assertFailsWith<IllegalArgumentException> {
                        IndependentGates.duplicateProvider(
                            root, record.objectAt("receipt"), record.objectAt("process"),
                        )
                    }
                    assertEquals(expected.primitive("error"), error.message)
                }
            }
        }
    }

    test("process output must bind the named input digest") {
        for (entry in vector.getValue("process_file_binding") as JsonArray) {
            val record = entry as JsonObject
            withGateRoot { root ->
                materialize(root, record)
                val expected = record.objectAt("result")
                if ("ok" in expected) {
                    IndependentGates.processFileBinding(
                        root, record.objectAt("process"), record.primitive("relative"),
                        record.primitive("label"),
                    )
                } else {
                    val error = assertFailsWith<IllegalArgumentException> {
                        IndependentGates.processFileBinding(
                            root, record.objectAt("process"), record.primitive("relative"),
                            record.primitive("label"),
                        )
                    }
                    assertEquals(expected.primitive("error"), error.message)
                }
            }
        }
    }

    test("an external unavailability observation records its reason and digest") {
        for (entry in vector.getValue("external_unavailable") as JsonArray) {
            val record = entry as JsonObject
            val receipt = record.objectAt("receipt")
            val expected = record.objectAt("result")
            if ("ok" in expected) {
                assertEquals(
                    expected.objectAt("ok"),
                    IndependentGates.externalUnavailable(
                        receipt, "a".repeat(40), "jvm:Java:minimum:default", "staged-consumer",
                    ),
                )
            } else {
                val error = assertFailsWith<IllegalArgumentException> {
                    IndependentGates.externalUnavailable(
                        receipt, "a".repeat(40), "jvm:Java:minimum:default", "staged-consumer",
                    )
                }
                assertEquals(expected.primitive("error"), error.message)
            }
        }
    }

    test("the 21-target hash map is validated before use") {
        for (entry in vector.getValue("all_target_hashes") as JsonArray) {
            val record = entry as JsonObject
            val expected = record.objectAt("result")
            if ("ok" in expected) {
                assertEquals(record.objectAt("hashes"), IndependentGates.validatedAllTargetHashes(record["hashes"]))
            } else {
                val error = assertFailsWith<IllegalArgumentException> {
                    IndependentGates.validatedAllTargetHashes(record["hashes"])
                }
                assertEquals(expected.primitive("error"), error.message)
            }
        }
    }

    test("the JVM publication gates compare against the all-target audit") {
        for (entry in vector.getValue("gate_artifact_hashes") as JsonArray) {
            val record = entry as JsonObject
            val expected = record.objectAt("result")
            val lane = buildJsonObject { put("target", record.getValue("target")) }
            val laneHashes = record.objectAt("lane_hashes").mapValues { (_, value) -> TestVectors.str(value) }
            if ("ok" in expected) {
                val observed = IndependentGates.gateArtifactHashes(
                    record.primitive("gate"), lane, laneHashes, record["all"],
                )
                if (TestVectors.str(record["target"]) == "jvm") {
                    assertEquals(
                        (record.objectAt("all").getValue("jvm") as JsonObject)
                            .mapValues { (_, value) -> TestVectors.str(value) },
                        observed,
                    )
                } else {
                    assertEquals(laneHashes, observed)
                }
            } else {
                val error = assertFailsWith<IllegalArgumentException> {
                    IndependentGates.gateArtifactHashes(
                        record.primitive("gate"), lane, laneHashes, record["all"],
                    )
                }
                assertEquals(expected.primitive("error"), error.message)
            }
        }
    }

    test("the staged consumer contract selects the lane scopes") {
        for (entry in vector.getValue("consumer_contract") as JsonArray) {
            val record = entry as JsonObject
            val manifest = record.objectAt("manifest")
            val lane = record.primitive("lane")
            val expected = record.objectAt("result")
            if ("ok" in expected) {
                assertEquals(expected.objectAt("ok"), IndependentGates.consumerContract(manifest, lane))
            } else {
                val error = assertFailsWith<IllegalArgumentException> {
                    IndependentGates.consumerContract(manifest, lane)
                }
                assertEquals(expected.primitive("error"), error.message)
            }
        }
    }

    test("a producer scope must pin the candidate, toolchain, hashes, and manifest") {
        for (entry in vector.getValue("producer_scope") as JsonArray) {
            val record = entry as JsonObject
            val gate = record.primitive("gate")
            val scopes = record.objectAt("result").let { result ->
                if ("ok" in result) {
                    buildJsonObject { put(gate, result.getValue("ok")) }
                } else {
                    buildJsonObject { put(gate, record["scope"] ?: JsonObject(emptyMap())) }
                }
            }
            val expected = record.objectAt("result")
            if ("ok" in expected) {
                assertEquals(expected.objectAt("ok"), IndependentGates.producerScope(gate, "a".repeat(40), scopes))
            } else {
                val error = assertFailsWith<IllegalArgumentException> {
                    IndependentGates.producerScope(gate, "a".repeat(40), scopes)
                }
                assertEquals(expected.primitive("error"), error.message)
            }
        }
    }

    test("archive member paths are validated before use") {
        for (entry in vector.getValue("file_path") as JsonArray) {
            val record = entry as JsonObject
            withGateRoot { root ->
                materialize(root, record)
                val relative = record.primitive("relative")
                val expected = record.objectAt("result")
                if ("ok" in expected) {
                    assertEquals(
                        root.resolve(relative).toString(),
                        IndependentGates.filePath(root, relative).toString(),
                    )
                } else {
                    val error = assertFailsWith<IllegalArgumentException> {
                        IndependentGates.filePath(root, relative)
                    }
                    assertEquals(expected.primitive("error"), error.message)
                }
            }
        }
    }

    test("an inventory seals exactly the archive it lists") {
        for (entry in vector.getValue("inventory") as JsonArray) {
            val record = entry as JsonObject
            withGateRoot { root ->
                materialize(root, record)
                val inventory = root.resolve("inventory")
                Files.createDirectories(inventory)
                inventory.resolve("receipt.json").writeText("{}\n")
                inventory.resolve("one.txt").writeText("one\n")
                for (name in listOf("receipt.json", "one.txt")) {
                    Files.setLastModifiedTime(
                        inventory.resolve(name),
                        FileTime.from(1_700_000_000L, TimeUnit.SECONDS),
                    )
                }
                val receipt = record.objectAt("receipt")
                val expected = record.objectAt("result")
                if ("ok" in expected) {
                    assertEquals(expected.primitive("ok"), IndependentGates.inventory(inventory, receipt))
                } else {
                    val error = assertFailsWith<IllegalArgumentException> {
                        IndependentGates.inventory(inventory, receipt)
                    }
                    assertEquals(expected.primitive("error"), error.message)
                }
            }
        }
    }

    test("a missing staged repository is diagnosed before the audit") {
        val expected = vector.objectAt("staged_publication")
        withGateRoot { root ->
            val lane = buildJsonObject { put("target", JsonPrimitive("jvm")) }
            val error = assertFailsWith<IllegalArgumentException> {
                IndependentGates.stagedPublication(root, "a".repeat(40), lane, emptyMap(), root)
            }
            assertEquals(expected.primitive("error"), error.message)
        }
    }

    test("a browser launch line is strict JSON and finite") {
        val parsed = IndependentGates.strictJsonLine("""{"pid":1,"value":0.5}""")
        assertEquals(1L, Py.int((parsed as JsonObject)["pid"]))
        assertEquals(
            "duplicate JSON key: pid",
            assertFailsWith<ObservationError> {
                IndependentGates.strictJsonLine("""{"pid":1,"pid":2}""")
            }.message,
        )
        assertEquals(
            "non-finite browser launch value: NaN",
            assertFailsWith<IllegalArgumentException> {
                IndependentGates.strictJsonLine("""{"value":NaN}""")
            }.message,
        )
        assertEquals(
            "non-finite browser launch value: -Infinity",
            assertFailsWith<IllegalArgumentException> {
                IndependentGates.strictJsonLine("""{"value":-Infinity}""")
            }.message,
        )
    }

    test("the approved manifest is pinned by revision and digest") {
        val repository = repositoryRoot()
        val manifest = IndependentGates.loadApprovedManifest(repository)
        assertEquals("complete-port", Py.str(manifest["kind"]))
        assertEquals(IndependentGates.APPROVED_MANIFEST_SHA256, IndependentGates.digest(manifest))
        assertEquals(112, (manifest["lanes"] as JsonObject).size)
        assertEquals(8, IndependentGates.LOCAL_KLIB_LANES.size)
        assertEquals(7, IndependentGates.LANE_GATES.size)
        assertEquals(4, IndependentGates.GLOBAL_GATES.size)
        assertEquals(5, IndependentGates.PRODUCER_SCOPED_GATES.size)
    }
}

/** A fresh raw-archive root for one recorded gate case. */
private fun withGateRoot(block: (Path) -> Unit) {
    val root = Files.createTempDirectory("gates")
    try {
        block(root)
    } finally {
        deleteRecursively(root)
    }
}

/** Writes the shared recorded fixture files under [root]. */
private fun materialize(root: Path, record: JsonObject) {
    val files = TestVectors.root.objectAt("gates")["files"] as? JsonObject ?: JsonObject(emptyMap())
    for ((name, content) in files) {
        val path = root.resolve(name)
        path.parent?.let { Files.createDirectories(it) }
        path.writeText(TestVectors.str(content))
    }
}
