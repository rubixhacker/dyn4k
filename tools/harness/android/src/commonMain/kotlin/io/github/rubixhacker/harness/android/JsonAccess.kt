package io.github.rubixhacker.harness.android

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/** Reads the JSON shapes the Android receipts use, with Python's `dict.get` semantics. */
internal fun JsonElement?.textOrNull(): String? = when (this) {
    null, is JsonNull -> null
    is JsonPrimitive -> content
    else -> null
}

internal fun JsonElement?.integerOrNull(): Long? {
    val value = this as? JsonPrimitive ?: return null
    if (value.isString) return null
    return value.content.toLongOrNull()
}

internal fun JsonElement?.objectOrNull(): JsonObject? = this as? JsonObject

internal fun JsonElement?.arrayOrNull(): JsonArray? = this as? JsonArray

internal fun JsonObject.textOrNull(key: String): String? = this[key].textOrNull()

internal fun JsonObject.integerOrNull(key: String): Long? = this[key].integerOrNull()

internal fun JsonObject.objectOrNull(key: String): JsonObject? = this[key].objectOrNull()

internal fun JsonObject.arrayOrNull(key: String): JsonArray? = this[key].arrayOrNull()

internal fun JsonObject.stringList(key: String): List<String>? =
    this[key].arrayOrNull()?.map { it.textOrNull() ?: return null }

internal fun JsonObject.stringMap(key: String): Map<String, String>? {
    val value = this[key].objectOrNull() ?: return null
    val result = linkedMapOf<String, String>()
    for ((name, element) in value) {
        result[name] = element.textOrNull() ?: return null
    }
    return result
}

/** Whether the element is a JSON string, as `isinstance(value, str)` asks. */
internal fun JsonElement?.isText(): Boolean = this is JsonPrimitive && isString
