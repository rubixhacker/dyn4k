package io.github.rubixhacker.harness.qualification

import de.infix.testBalloon.framework.core.testSuite
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject

/**
 * `qualify.validate_complete_suite_bindings`, replayed against the tracked frozen suite.
 *
 * The reference mutations are recorded as small edit operations instead of whole manifests: the
 * input is the tracked `full-suite-manifest.json` plus the recorded operation, and the expected
 * verdict comes from the reference run of the same edit.
 */
val CompleteSuiteBindings by testSuite {
    val repository = repositoryRoot()
    val tracked = strictLoad(
        repository.resolve("tools/qualification/full-suite-manifest.json"),
    ).jsonObject

    for (vector in TestVectors.list("complete_suite_bindings")) {
        test("validate_complete_suite_bindings: ${vector.primitive("name")}") {
            val mutated = applyOperations(tracked, vector.getValue("ops").jsonArray)
            val expected = vector.objectAt("result")
            if ("ok" in expected) {
                SuiteBindings.validate(mutated, repository)
            } else {
                val error = assertFailsWith<IllegalArgumentException> {
                    SuiteBindings.validate(mutated, repository)
                }
                assertEquals(expected.primitive("error"), error.message, vector.primitive("name"))
            }
        }
    }

    test("the recorded manifest is the independently reviewed one") {
        assertEquals(
            SuiteBindings.APPROVED_COMPLETE_SUITE_SHA256,
            io.github.rubixhacker.harness.contract.Sha256.ofCanonical(tracked),
        )
        assertEquals(2526, tracked.getValue("cases").jsonArray.size)
        assertEquals(112, tracked.getValue("lanes").jsonObject.size)
    }

    test("a manifest bound to a corpus that is not production is rejected") {
        // The reference reads the corpus beside the manifest, so this check needs the tracked
        // files; the port fails the same way when the manifest identity no longer matches.
        val mutated = setAt(tracked, listOf("kind"), JsonPrimitive("foundation-probe"))
        val error = assertFailsWith<IllegalArgumentException> {
            SuiteBindings.validate(mutated, repository)
        }
        assertEquals("complete suite manifest identity is invalid", error.message)
    }
}

private fun applyOperations(manifest: JsonObject, operations: JsonArray): JsonObject {
    var document = manifest
    for (operation in operations.map { it.jsonObject }) {
        document = when {
            "set" in operation -> setAt(
                document,
                TestVectors.strings(operation["set"]),
                operation.getValue("value"),
            )
            "pop_case" in operation -> JsonObject(
                document + ("cases" to JsonArray(document.getValue("cases").jsonArray.dropLast(1))),
            )
            "set_case_field" in operation -> {
                val field = operation.primitive("set_case_field")
                val cases = document.getValue("cases").jsonArray.map { it.jsonObject }.toMutableList()
                cases[0] = JsonObject(cases[0] + (field to operation.getValue("value")))
                JsonObject(document + ("cases" to JsonArray(cases)))
            }
            "pop_global_gate" in operation -> JsonObject(
                document + (
                    "global_gates" to JsonArray(
                        document.getValue("global_gates").jsonArray.dropLast(1),
                    )
                    ),
            )
            "set_first_lane_field" in operation -> {
                val field = operation.primitive("set_first_lane_field")
                val lanes = document.getValue("lanes").jsonObject
                val first = lanes.keys.sortedWith(CanonicalText::compare).first()
                val lane = JsonObject(lanes.getValue(first).jsonObject + (field to operation.getValue("value")))
                JsonObject(document + ("lanes" to JsonObject(lanes + (first to lane))))
            }
            else -> error("unsupported recorded manifest operation: $operation")
        }
    }
    return document
}

private fun setAt(value: JsonObject, path: List<String>, replacement: JsonElement): JsonObject {
    if (path.size == 1) return JsonObject(value + (path[0] to replacement))
    val child = value.getValue(path[0]).jsonObject
    return JsonObject(value + (path[0] to setAt(child, path.drop(1), replacement)))
}

private fun strictLoad(path: java.nio.file.Path): JsonElement =
    io.github.rubixhacker.harness.contract.StrictJson.load(
        io.github.rubixhacker.harness.qualification.Fs.readText(path),
    )
