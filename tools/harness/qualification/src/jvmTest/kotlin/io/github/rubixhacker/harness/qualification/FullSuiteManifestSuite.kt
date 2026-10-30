package io.github.rubixhacker.harness.qualification

import de.infix.testBalloon.framework.core.testSuite
import java.nio.file.Files
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject

/**
 * `full_suite_manifest.py`, against reference vectors and the tracked corpus.
 *
 * `area_for` is replayed case by case. The tracked corpus test asserts the reference contract:
 * either the working tree still reproduces the frozen corpus and the manifest is exactly the
 * derived one, or `read_corpus` diagnoses the drift with its own message.
 */
val FullSuiteManifestContract by testSuite {
    val vector = TestVectors.root.objectAt("full_corpus")

    test("area_for classifies every reviewed case family") {
        for (entry in vector.getValue("areas") as JsonArray) {
            val record = entry as JsonObject
            val case = record.objectAt("case")
            assertEquals(
                TestVectors.str(record["result"]),
                FullSuiteManifest.areaFor(case),
                TestVectors.str(case["classname"]),
            )
        }
    }

    test("an unclassified corpus case is rejected") {
        val error = assertFailsWith<IllegalArgumentException> {
            FullSuiteManifest.areaFor(vector.objectAt("area_unknown"))
        }
        assertEquals("unclassified corpus case: unknown.Thing", error.message)
    }

    test("the tracked corpus is reproduced exactly or diagnosed") {
        val repository = repositoryRoot()
        val tracked = repository.resolve(FullSuiteManifest.MANIFEST_PATH)
        assertTrue(Files.isRegularFile(tracked), "the tracked complete suite manifest is missing")
        val outcome = runCatching { FullSuiteManifest.readCorpus(repository) }
        if (outcome.isSuccess) {
            val manifest = FullSuiteManifest.buildManifest(repository)
            assertEquals(
                io.github.rubixhacker.harness.contract.StrictJson.load(Fs.readText(tracked)),
                manifest,
                "the derived suite must equal the tracked manifest",
            )
            assertTrue(FullSuiteManifest.validateManifest(manifest, repository))
            val selected = FullSuiteManifest.selectLane(manifest, "jvm:Java:minimum:default", repository)
            assertEquals(
                "jvm:Java:minimum:default",
                Py.str(selected["lane_id"]),
            )
            assertEquals(
                TestVectors.strings(selected["global_gates"]),
                FullSuiteManifest.GLOBAL_GATES,
            )
        } else {
            val message = (outcome.exceptionOrNull() as? IllegalArgumentException)?.message
            assertEquals("common test source hash differs", message)
        }
    }

    test("the suite constants match the reviewed gate inventory") {
        assertEquals(5, FullSuiteManifest.AREA_IDS.size)
        assertEquals(4, FullSuiteManifest.LANE_GATES.size)
        assertEquals(3, FullSuiteManifest.JVM_GATES.size)
        assertEquals(4, FullSuiteManifest.GLOBAL_GATES.size)
        assertEquals(11, FullSuiteManifest.GATE_DESCRIPTIONS.size)
        assertEquals(FullSuiteManifest.GATE_DESCRIPTIONS.keys, FullSuiteManifest.GATE_SOURCES.keys)
        assertEquals(112, io.github.rubixhacker.harness.contract.Qualification.expand().size)
    }
}
