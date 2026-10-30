package io.github.rubixhacker.harness.compatibility

import de.infix.testBalloon.framework.core.testSuite
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlin.test.assertEquals

private val ledgerVectors = Vectors.ledger

/**
 * The pure ledger assembly helpers: `generate`, `unbound_candidate_report`,
 * `require_baseline_test_inputs`, and `declaration_inventory`.
 *
 * `reference`, `check_evidence`, `validate_module`, and `validate` replay the pinned baseline JAR,
 * the git object store, and every review receipt, so they stay with the unported host half.
 */
val LedgerContract by testSuite {
    test("generate builds the unpinned ledger") {
        assertEquals(
            ledgerVectors.obj("generate"),
            Ledger.generate(ledgerVectors.obj("expected")),
        )
    }

    test("unbound candidate reports keep every obligation") {
        assertEquals(
            ledgerVectors.obj("unbound"),
            Ledger.unboundCandidateReport(
                ledgerVectors.obj("expected"),
                ledgerVectors.obj("source"),
                ledgerVectors.obj("unbound").str("requested_candidate_revision"),
                "invalid",
                ledgerVectors.obj("unbound").array("invalid")[0].jsonPrimitive.content,
            ),
        )
    }

    test("baseline test inputs must match exactly") {
        for (case in ledgerVectors.array("baseline_inputs").map { it.jsonObject }) {
            val observed = case.obj("observed").jsonObject
            val result = case.obj("result")
            if (result["error"] == null || result["error"] is JsonNull) {
                Ledger.requireBaselineTestInputs(
                    observed,
                    mapOf("src/test/java/A.java" to "a".repeat(64)),
                    mapOf("src/test/resources/r.txt" to "b".repeat(64)),
                )
            } else {
                val thrown = kotlin.test.assertFailsWith<IllegalArgumentException> {
                    Ledger.requireBaselineTestInputs(
                        observed,
                        mapOf("src/test/java/A.java" to "a".repeat(64)),
                        mapOf("src/test/resources/r.txt" to "b".repeat(64)),
                    )
                }
                assertEquals(result.str("error"), thrown.message)
            }
        }
    }

    test("declaration inventory binds every member to its source owner") {
        val recorded = ledgerVectors.obj("declaration_inventory")
        val production = recorded.obj("production").mapValues { it.value.jsonPrimitive.content }
        val inventory = Ledger.declarationInventory(
            mapOf("org.dyn4j.Sample" to recorded.str("plain")),
            mapOf("org.dyn4j.Sample" to recorded.str("verbose")),
            production,
        )
        val expected = recorded.array("inventory").map {
            val row = it.jsonArray
            row[0].jsonPrimitive.content to Ledger.DeclaredSource(
                row[1].jsonPrimitive.content,
                row[2].jsonPrimitive.content,
                (row[3] as? JsonArray)?.map { flag -> flag.jsonPrimitive.content }
                    ?: if (row[3] is JsonNull) null else emptyList(),
            )
        }.toMap()
        assertEquals(expected, inventory)
    }
}
