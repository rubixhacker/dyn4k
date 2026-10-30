package io.github.rubixhacker.harness.numerical

import de.infix.testBalloon.framework.core.testSuite
import io.github.rubixhacker.harness.contract.CanonicalJson
import io.github.rubixhacker.harness.contract.Sha256
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.put
import kotlin.test.assertEquals

private val vectors = parseVectors(CASES_VECTORS)

/** `cases.declared_cases` against the matrix the Python reference declares. */
val CasesContract by testSuite {
    test("the declared matrix matches the recorded digest") {
        val declared = Cases.declaredCases()
        assertEquals(vectors.int("count"), declared.size)
        assertEquals(
            vectors.str("canonical_sha256"),
            Sha256.of(CanonicalJson.render(JsonArray(declared))),
        )
        assertEquals(
            vectors.str("id_list_sha256"),
            Sha256.of(
                CanonicalJson.render(
                    JsonArray(declared.map { it.getValue("id") }),
                ),
            ),
        )
    }

    test("the family and profile inventory matches") {
        val declared = Cases.declaredCases()
        val families = vectors.obj("family_counts")
        for ((family, count) in families) {
            assertEquals(
                count.intOrNull(),
                declared.count { it["family"]?.stringOrNull() == family },
                "family $family",
            )
        }
        val profiles = vectors.obj("profile_counts")
        for ((profile, count) in profiles) {
            assertEquals(
                count.intOrNull(),
                declared.count { it["profile"]?.stringOrNull() == profile },
                "profile $profile",
            )
        }
    }

    test("the first case of every family matches byte for byte") {
        val declared = Cases.declaredCases()
        for ((family, element) in vectors.obj("samples")) {
            val recorded = element.jsonObject
            val actual = declared.firstOrNull { it["family"]?.stringOrNull() == family }
                ?: error("missing family $family")
            assertEquals(canonical(recorded), canonical(actual), family)
        }
    }

    test("derived coverage fields match the declaration") {
        val declared = Cases.declaredCases()
        val welded = declared.single {
            it["id"]?.stringOrNull() == "P-JINT-Weld-enabled-equal"
        }
        assertEquals(
            canonical(JsonArray(listOf(JsonPrimitive(1)))),
            canonical(welded.getValue("expected_instrumented_callbacks")),
        )
        val contacts = declared.single {
            it["id"]?.stringOrNull() == "contacts-default-60"
        }
        assertEquals(
            canonical(JsonArray(listOf(JsonPrimitive(18001), JsonPrimitive(18001)))),
            canonical(contacts.getValue("expected_instrumented_callbacks")),
        )
        assertEquals(
            canonical(JsonArray(listOf(JsonPrimitive(18001)))),
            canonical(contacts.getValue("expected_actions")),
        )
        assertEquals(
            canonical(JsonArray((1..60).map { JsonPrimitive(it) })),
            canonical(
                declared.single { it["id"]?.stringOrNull() == "motion-forces-60" }
                    .getValue("expected_actions"),
            ),
        )
        assertEquals(
            JsonArray(listOf(JsonPrimitive(201), JsonPrimitive(401))),
            declared.single {
                it["id"]?.stringOrNull() == "joint-Weld-SpringEnabled-toggle"
            }.getValue("expected_actions"),
        )
        val configured = declared.single {
            it["id"]?.stringOrNull() == "contacts-configured-120-r1"
        }
        assertEquals(
            canonical(
                buildJsonObject {
                    put("outerHz", 120)
                    put("repetition", 1)
                    put("innerPerOuter", 1)
                    put("outerDt", 1.0 / 120)
                    put("outerSteps", 72000)
                    put("actionInnerStep", 36001)
                },
            ),
            canonical(configured.getValue("frozen_grouping")),
        )
        assertEquals(
            "Q-sleep-wake-outer120-repeat1",
            configured["frozen_id"]?.stringOrNull(),
        )
        assertEquals(
            "P-JINT-Pulley-slack-transition-preparation",
            declared.single {
                it["id"]?.stringOrNull() == "P-JINT-Pulley-slack-transition-preparation-1"
            }["frozen_id"]?.stringOrNull(),
        )
        assertEquals(
            "S-sleep-wake-hz120",
            declared.single {
                it["id"]?.stringOrNull() == "contacts-default-120"
            }["frozen_id"]?.stringOrNull(),
        )
    }
}
