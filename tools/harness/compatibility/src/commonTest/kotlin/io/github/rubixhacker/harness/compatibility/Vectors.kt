package io.github.rubixhacker.harness.compatibility

import io.github.rubixhacker.harness.contract.Sha256
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

/** Parsed golden vectors recorded from the Python implementation. */
internal object Vectors {
    val worldCi: JsonObject = parse(WorldCiVectors.json)
    val governingSeams: JsonObject = parse(GoverningSeamsVectors.json)
    val candidateCoverage: JsonObject = parse(CandidateCoverageVectors.json)
    val methodCoverage: JsonObject = parse(MethodCoverageVectors.json)
    val javaCorpus: JsonObject = parse(JavaCorpusVectors.json)
    val executionProbe: JsonObject = parse(ExecutionProbeVectors.json)
    val governingDisposition: JsonObject = parse(GoverningDispositionVectors.json)

    private fun parse(text: String): JsonObject = Json.parseToJsonElement(text).jsonObject
}

internal fun JsonObject.obj(key: String): JsonObject = getValue(key).jsonObject

internal fun JsonObject.array(key: String): JsonArray = getValue(key).jsonArray

internal fun JsonObject.str(key: String): String = getValue(key).jsonPrimitive.content

internal fun JsonObject.nullableStr(key: String): String? =
    if (getValue(key) is JsonNull) null else getValue(key).jsonPrimitive.content

internal fun JsonObject.int(key: String): Int = getValue(key).jsonPrimitive.content.toInt()

/** The text of a JSON string, or null for a JSON null. */
internal fun JsonElement.textOrNull(): String? = when (this) {
    is JsonNull -> null
    is JsonPrimitive -> content
    else -> null
}

/** The string entries of a JSON object, in document order. */
internal fun JsonObject.stringMap(): Map<String, String> =
    mapValues { (_, value) -> value.jsonPrimitive.content }

/**
 * Runs [block] and compares its failure with the recorded outcome: a JSON null outcome means the
 * call must succeed, otherwise the message must equal the recorded Python message.
 */
internal fun assertRecordedOutcome(recorded: JsonObject, block: () -> Unit) {
    val error = recorded["error"]
    if (error == null || error is JsonNull) {
        block()
    } else {
        val thrown = assertFailsWith<IllegalArgumentException> { block() }
        assertEquals(error.jsonPrimitive.content, thrown.message)
    }
}

/** An in-memory [CorpusFiles] over UTF-8 text entries. */
internal class MemoryFiles(
    entries: Map<String, String> = emptyMap(),
    symlinks: Set<String> = emptySet(),
) : CorpusFiles {
    private val entries = LinkedHashMap(entries)
    private val symlinks = symlinks.toSet()

    fun plus(path: String, text: String): MemoryFiles =
        MemoryFiles(entries + (path to text), symlinks)

    fun minus(path: String): MemoryFiles = MemoryFiles(entries - path, symlinks)

    fun link(path: String): MemoryFiles = MemoryFiles(entries, symlinks + path)

    override fun isSymlink(path: String): Boolean = path in symlinks
    override fun isFile(path: String): Boolean = path in entries
    override fun digest(path: String): String = Sha256.of(entries.getValue(path))
    override fun readText(path: String): String = entries.getValue(path)
    override fun filesBelow(root: String): List<String> =
        entries.keys.filter { it.startsWith("$root/") }.map { it.removePrefix("$root/") }
}

/** A JSON object rebuilt with [key] replaced. */
internal fun JsonObject.withEntry(key: String, value: JsonElement): JsonObject =
    JsonObject(toMutableMap().apply { put(key, value) })

internal fun JsonObject.withEntry(key: String, value: String): JsonObject =
    withEntry(key, JsonPrimitive(value))
