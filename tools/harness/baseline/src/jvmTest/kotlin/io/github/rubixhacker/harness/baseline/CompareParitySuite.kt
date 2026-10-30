package io.github.rubixhacker.harness.baseline

import de.infix.testBalloon.framework.core.testSuite
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/** One recorded risk with its artifact digest left out, which is what the vectors pin. */
private fun riskOf(value: JsonObject): String = listOf(
    value.str("candidate_type"),
    value.str("declaring_type"),
    value.str("descriptor"),
    value.strings("flags").joinToString(","),
    value.str("origin"),
    value.str("kind"),
    value.str("declaration"),
).joinToString(" | ")

/**
 * End-to-end parity for `compare_jars`: the recorded report of six fixture pairs is replayed by
 * rebuilding the same sources and comparing every textual field of the report — the API type list,
 * the declaration count, the missing types, every mismatch and compatible difference, the inventory
 * errors, and each added-member risk.
 *
 * The digests are not compared: the archives are rebuilt on this host, so their bytes are new even
 * though the javap text is the same.
 */
val CompareParityCases by testSuite {
    test("the six recorded pairs cover accepted, rejected and compatible differences") {
        assertEquals(
            listOf(
                "kotlin-style-additions",
                "final-method-override",
                "final-type",
                "transitive-interface",
                "constructor-widening",
                "missing-method",
            ),
            Vectors.compare.map { it.jsonObject.str("label") },
        )
    }

    test("the comparison report reproduces the recorded text") {
        for (element in Vectors.compare) {
            val recorded = element.jsonObject
            withCase { root ->
                val label = recorded.str("label")
                val baseline = jarOf(root.resolve("baseline"), recorded.obj("baseline_sources").stringMap())
                val candidate = jarOf(root.resolve("candidate"), recorded.obj("candidate_sources").stringMap())
                val only = if (recorded["only"] is JsonNull) null else recorded.strings("only").toSet()
                val report = compareJars(
                    baseline,
                    candidate,
                    only = only,
                    policy = BaselinePolicy(binarySha256 = digest(baseline)),
                )
                assertEquals(recorded.int("baseline_types"), report.baselineTypes, label)
                assertEquals(recorded.int("candidate_types"), report.candidateTypes, label)
                assertEquals(
                    recorded.int("compared_baseline_declarations"),
                    report.comparedBaselineDeclarations,
                    label,
                )
                assertEquals(recorded.strings("compared_api_types"), report.comparedApiTypes, label)
                assertEquals(recorded.strings("missing_types"), report.missingTypes, label)
                assertEquals(recorded.strings("signature_mismatches"), report.signatureMismatches, label)
                assertEquals(recorded.strings("compatible_differences"), report.compatibleDifferences, label)
                assertEquals(recorded.strings("inventory_errors"), report.inventoryErrors, label)
                assertEquals(recorded.strings("fixture_failures"), report.fixtureFailures, label)
                assertEquals(recorded.strings("fixture_errors"), report.fixtureErrors, label)
                assertEquals(
                    recorded.array("risk_declarations").map { riskOf(it.jsonObject) },
                    report.addedMemberRisks.map {
                        listOf(
                            it.candidateType,
                            it.declaringType,
                            it.descriptor,
                            it.flags.joinToString(","),
                            it.origin,
                            it.kind,
                            it.declaration,
                        ).joinToString(" | ")
                    },
                    label,
                )
                assertTrue(report.baselineSha256 == digest(baseline), label)
            }
        }
    }

    test("the rendered report keeps the Python document's key order") {
        for (element in Vectors.compare) {
            val recorded = element.jsonObject
            withCase { root ->
                val baseline = jarOf(root.resolve("baseline"), recorded.obj("baseline_sources").stringMap())
                val candidate = jarOf(root.resolve("candidate"), recorded.obj("candidate_sources").stringMap())
                val run = cli(
                    "compare",
                    "--baseline-jar", baseline.toString(),
                    "--candidate", candidate.toString(),
                    policy = BaselinePolicy(binarySha256 = digest(baseline)),
                )
                val document = run.report()
                assertEquals(
                    listOf(
                        "baseline_types",
                        "candidate_types",
                        "compared_baseline_declarations",
                        "compared_api_types",
                        "missing_types",
                        "signature_mismatches",
                        "compatible_differences",
                        "baseline_sha256",
                        "candidate_sha256",
                        "dependency_sha256",
                        "added_member_risks",
                        "inventory_errors",
                        "fixture_results",
                        "fixture_failures",
                        "fixture_errors",
                    ),
                    document.keys.toList(),
                    recorded.str("label"),
                )
                val failed = document.strings("missing_types").isNotEmpty() ||
                    document.strings("signature_mismatches").isNotEmpty() ||
                    document.strings("inventory_errors").isNotEmpty() ||
                    document.array("added_member_risks").isNotEmpty() ||
                    document.strings("fixture_errors").isNotEmpty() ||
                    document.strings("fixture_failures").isNotEmpty()
                assertEquals(if (failed) 1 else 0, run.code, recorded.str("label"))
            }
        }
    }
}
