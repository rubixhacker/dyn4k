package io.github.rubixhacker.harness.qualification

import de.infix.testBalloon.framework.core.testSuite
import java.nio.file.Files
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject

/**
 * `independent_gates.py`, second slice: the physical disposition tables, the prospective case
 * status rule, the P2 scope/runtime/summary contracts, the numerical policy source pin, and the
 * adopted prospective catalog.
 */
val GatesNumericalContract by testSuite {
    val vector = TestVectors.root.objectAt("numerical")

    test("physical_status folds the four required profiles") {
        for (entry in vector.getValue("physical_status") as JsonArray) {
            val record = entry as JsonObject
            val profiles = record.objectAt("profiles")
            val expected = record.objectAt("result")
            if ("ok" in expected) {
                assertEquals(expected.primitive("ok"), GatesNumerical.physicalStatus(profiles))
            } else {
                val error = assertFailsWith<IllegalArgumentException> {
                    GatesNumerical.physicalStatus(profiles)
                }
                assertEquals(expected.primitive("error"), error.message)
            }
        }
    }

    test("the prospective case status combines rule and arithmetic") {
        for (entry in vector.getValue("prospective_case_status") as JsonArray) {
            val record = entry as JsonObject
            assertEquals(
                record.primitive("result"),
                GatesNumerical.prospectiveCaseStatus(
                    record.primitive("rule"), record.primitive("arithmetic"),
                ),
            )
        }
    }

    test("the recorded physical profile dispositions are reproduced exactly") {
        assertEquals(
            vector.objectAt("missing_physical_profiles"),
            GatesNumerical.missingPhysicalProfiles(),
        )
        assertEquals(
            vector.objectAt("legacy_joint_physical_profile"),
            GatesNumerical.legacyJointPhysicalProfile(),
        )
        assertTrue("legacy-weld-pulley" in GatesNumerical.missingPhysicalProfiles())
    }

    test("the P2 runtime identity is a digest of the reviewed proof") {
        for (entry in vector.getValue("p2_runtime_identity") as JsonArray) {
            val record = entry as JsonObject
            val proof = record.objectAt("proof")
            val expected = record.objectAt("result")
            if ("ok" in expected) {
                assertEquals(expected.primitive("ok"), GatesNumerical.p2RuntimeIdentity(proof))
            } else {
                val error = assertFailsWith<IllegalArgumentException> {
                    GatesNumerical.p2RuntimeIdentity(proof)
                }
                assertEquals(expected.primitive("error"), error.message)
            }
        }
    }

    test("a prospective raw directory stays inside the archive") {
        val root = Files.createTempDirectory("numerical-p2")
        try {
            Files.createDirectory(root.resolve("raw"))
            for (entry in vector.getValue("p2_directory") as JsonArray) {
                val record = entry as JsonObject
                val relative = record.primitive("relative")
                val expected = record.objectAt("result")
                if ("ok" in expected) {
                    assertEquals(
                        root.resolve(relative).toString(),
                        GatesNumerical.p2Directory(root, relative).toString(),
                    )
                } else {
                    val error = assertFailsWith<Exception> {
                        GatesNumerical.p2Directory(root, relative)
                    }
                    assertEquals(expected.primitive("error"), error.message)
                }
            }
        } finally {
            deleteRecursively(root)
        }
    }

    test("the P2 summary replays 318 bound case operations") {
        val inputs = vector.objectAt("p2_summary_inputs")
        val expectedCases = TestVectors.strings(inputs["expected"])
        val methods = TestVectors.strings(inputs["methods"]).toSet()
        val caseMethods = inputs.objectAt("case_methods").mapValues { (_, value) -> TestVectors.str(value) }
        for (entry in vector.getValue("p2_summary") as JsonArray) {
            val record = entry as JsonObject
            val summary = record.objectAt("summary")
            val expected = record.objectAt("result")
            if ("ok" in expected) {
                val observed = GatesNumerical.p2Summary(summary, expectedCases, methods, caseMethods)
                assertEquals(expected.objectAt("ok"), observed)
                assertEquals("PASSED", Py.str(observed["status"]))
                assertEquals(318L, Py.int(observed["required_cases"]))
                assertEquals(5L, Py.int(observed["methods_verified"]))
            } else {
                val error = assertFailsWith<IllegalArgumentException> {
                    GatesNumerical.p2Summary(summary, expectedCases, methods, caseMethods)
                }
                assertEquals(expected.primitive("error"), error.message)
            }
        }
    }

    test("the adopted prospective catalog is pinned to 318 cases") {
        val repository = repositoryRoot()
        val catalog = vector.objectAt("prospective_catalog")
        val expected = TestVectors.strings(catalog["cases"])
        assertEquals(318L, TestVectors.long(catalog["count"]))
        assertEquals(expected, GatesNumerical.approvedProspectiveCases(repository))
        val resolved = GatesNumerical.approvedProspectiveCatalog(repository)
        assertEquals(318, (resolved["cases"] as JsonObject).size)
    }

    test("the numerical source archive digest is pinned to the candidate commit") {
        val record = vector.objectAt("verified_source")
        val candidateSha = record.primitive("candidate_sha")
        val expected = record.objectAt("result")
        val repository = repositoryRoot()
        if ("ok" in expected) {
            assertEquals(
                expected.primitive("ok"),
                GatesNumerical.verifiedNumericalSourceSha256(repository, candidateSha),
            )
        } else {
            val error = assertFailsWith<IllegalArgumentException> {
                GatesNumerical.verifiedNumericalSourceSha256(repository, candidateSha)
            }
            assertEquals(expected.primitive("error"), error.message)
        }
        val rejected = assertFailsWith<IllegalArgumentException> {
            GatesNumerical.verifiedNumericalSourceSha256(repository, "abc")
        }
        assertEquals("numerical source requires an exact candidate commit", rejected.message)
    }

    test("the recorded numerical subgates are NOT_RUN over the adopted cases") {
        val subgates = GatesNumerical.missingNumericalSubgates(repositoryRoot())
        assertEquals(2, subgates.size)
        val frozen = subgates.objectAt("frozen-traces")
        assertEquals("NOT_RUN", Py.str(frozen["status"]))
        assertEquals(14L, Py.int(frozen["required_cases"]))
        val prospective = subgates.objectAt("prospective-rule-arithmetic")
        assertEquals("NOT_RUN", Py.str(prospective["status"]))
        assertEquals(318L, Py.int(prospective["required_cases"]))
        val cases = prospective["cases"] as JsonObject
        assertEquals(318, cases.size)
        assertTrue(cases.values.all { entry ->
            val row = entry as JsonObject
            Py.str(row["rule"]) == "NOT_RUN" && Py.str(row["status"]) == "NOT_RUN"
        })
    }
}
