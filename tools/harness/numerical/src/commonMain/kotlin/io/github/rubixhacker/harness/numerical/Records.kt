package io.github.rubixhacker.harness.numerical

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/**
 * `receipt._finite`. Rejects non-finite numbers, and rejects a recorded non-finite value
 * unless the caller allows the tagged form.
 */
internal fun requireFinite(value: JsonElement?, allowTaggedNonfinite: Boolean = false) {
    when (value) {
        null, JsonNull -> return
        is JsonPrimitive -> {
            if (value.isNumber()) {
                val number = value.numberOrNull() ?: return
                if (!number.isFinite()) throw Rejected("nonfinite number")
            }
        }
        is JsonArray -> value.forEach { requireFinite(it, allowTaggedNonfinite) }
        is JsonObject -> {
            if (value.containsKey("nonfinite")) {
                if (!allowTaggedNonfinite) {
                    throw Rejected("nonfinite recorded value: ${value.tagText()}")
                }
                if (value.keys != setOf("nonfinite") ||
                    value["nonfinite"]?.stringOrNull() !in
                    setOf("Infinity", "-Infinity", "NaN")
                ) {
                    throw Rejected("invalid tagged nonfinite value")
                }
                return
            }
            value.values.forEach { requireFinite(it, allowTaggedNonfinite) }
        }
    }
}

private fun JsonObject.tagText(): String {
    val tag = this["nonfinite"] ?: return "None"
    return tag.stringOrNull() ?: tag.toString()
}

/** `receipt._tagged`: whether the value carries a `nonfinite` tag anywhere below it. */
internal fun tagged(value: JsonElement?): Boolean = when (value) {
    null, JsonNull -> false
    is JsonObject -> value.containsKey("nonfinite") || value.values.any { tagged(it) }
    is JsonArray -> value.any { tagged(it) }
    else -> false
}

/**
 * `receipt.records` over the trace lines, each keeping its terminating newline so that a JSON
 * position report matches the one CPython produces for the same line.
 */
fun records(lines: List<String>, allowTaggedNonfinite: Boolean = false): List<JsonObject> {
    val result = ArrayList<JsonObject>(lines.size)
    for ((index, line) in lines.withIndex()) {
        val number = index + 1
        val value = try {
            PyJson.load(line)
        } catch (failure: JsonDecodeFailure) {
            throw Rejected("line $number: ${failure.message}")
        }
        if (value !is JsonObject) throw Rejected("line $number is not an object")
        requireFinite(value, allowTaggedNonfinite)
        result.add(value)
    }
    return result
}

/** `receipt.require`. */
internal fun require(condition: Boolean, message: String) {
    if (!condition) throw Rejected(message)
}
