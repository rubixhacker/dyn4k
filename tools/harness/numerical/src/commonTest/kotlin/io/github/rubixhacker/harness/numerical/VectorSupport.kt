package io.github.rubixhacker.harness.numerical

import io.github.rubixhacker.harness.contract.CanonicalJson
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

internal fun parseVectors(text: String): JsonObject =
    Json.parseToJsonElement(text).jsonObject

internal fun JsonObject.obj(key: String): JsonObject = getValue(key).jsonObject

internal fun JsonObject.array(key: String): JsonArray = getValue(key).jsonArray

internal fun JsonObject.str(key: String): String = getValue(key).jsonPrimitive.content

internal fun JsonObject.int(key: String): Int = getValue(key).jsonPrimitive.content.toInt()

internal fun JsonObject.element(key: String): JsonElement = getValue(key)

/** The recorded outcome of one Python call: a result, or the message of the rejection. */
internal class RecordedOutcome(val result: JsonElement?, val error: String?) {
    val succeeded: Boolean get() = error == null
}

internal fun JsonObject.outcome(): RecordedOutcome {
    val error = this["error"]
    val message = if (error == null || error is JsonNull) null else error.jsonPrimitive.content
    return RecordedOutcome(this["result"], message)
}

/** Asserts that [block] reproduces the recorded Python result. */
internal fun assertOutcome(recorded: JsonObject, block: () -> JsonElement?) {
    val outcome = recorded.outcome()
    if (!outcome.succeeded) {
        val failure = assertFailsWith<IllegalArgumentException> { block() }
        assertEquals(outcome.error, failure.message)
        return
    }
    val actual = block() ?: JsonNull
    assertEquals(canonical(actual), canonical(outcome.result ?: JsonNull))
}

internal fun assertOutcomeUnit(recorded: JsonObject, block: () -> Unit) {
    val outcome = recorded.outcome()
    if (!outcome.succeeded) {
        val failure = assertFailsWith<IllegalArgumentException> { block() }
        assertEquals(outcome.error, failure.message)
        return
    }
    block()
}

internal fun canonical(value: JsonElement): String = CanonicalJson.render(value)

/** The recorded rows of a trace as the JSON Lines text `receipt` reads. */
internal fun traceLines(rows: List<JsonObject>): List<String> = rows.map { it.toString() + "\n" }

/** The recorded rows of a trace, in document order. */
internal fun rowsOf(recorded: JsonElement): List<JsonObject> =
    (recorded as JsonArray).map { it.jsonObject as JsonObject }

/** Splits a recorded trace text into the lines `receipt.records` consumes. */
internal fun linesOf(text: String): List<String> {
    if (text.isEmpty()) return emptyList()
    assertTrue(text.endsWith("\n"), "a recorded trace text must end with a newline")
    val lines = text.split("\n")
    return lines.subList(0, lines.size - 1).map { it + "\n" }
}

internal fun assertSameJson(expected: JsonElement, actual: JsonElement) {
    assertEquals(canonical(expected), canonical(actual))
}
