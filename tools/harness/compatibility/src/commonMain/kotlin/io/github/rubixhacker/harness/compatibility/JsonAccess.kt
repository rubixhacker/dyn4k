package io.github.rubixhacker.harness.compatibility

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/** Reads the JSON shapes the compatibility reports use, with Python's `dict.get` semantics. */
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

internal fun JsonObject.field(key: String): JsonElement? = this[key]

internal fun JsonObject.textOrNull(key: String): String? = this[key].textOrNull()

internal fun JsonObject.integerOrNull(key: String): Long? = this[key].integerOrNull()

internal fun JsonObject.objectOrNull(key: String): JsonObject? = this[key].objectOrNull()

internal fun JsonObject.arrayOrNull(key: String): JsonArray? = this[key].arrayOrNull()

/** The relative paths of the files immediately inside [root], as `Path.glob("*.ser")` lists them. */
internal fun CorpusFiles.directFiles(root: String): List<String> =
    filesBelow(root).filter { '/' !in it }

/** Normalises an absolute posix path the way `str(Path(value))` renders it. */
internal fun normaliseAbsolutePath(path: String): String {
    val parts = path.split('/').filter { it.isNotEmpty() && it != "." }
    return "/" + parts.joinToString("/")
}

/** Normalises a relative posix path the way `PurePosixPath.as_posix` renders it. */
internal fun normaliseRelativePath(path: String): String =
    path.split('/').filter { it.isNotEmpty() && it != "." }.joinToString("/")

internal val SHA256_HEX = Regex("[0-9a-f]{64}")
internal val COMMIT_HEX = Regex("[0-9a-f]{40}")
