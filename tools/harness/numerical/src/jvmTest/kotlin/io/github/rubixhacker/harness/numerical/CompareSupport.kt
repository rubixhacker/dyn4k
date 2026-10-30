package io.github.rubixhacker.harness.numerical

import io.github.rubixhacker.harness.contract.Sha256
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import java.io.ByteArrayOutputStream
import java.nio.file.Files
import java.nio.file.Path
import java.util.zip.GZIPOutputStream

/** `json.dumps(value, separators=(",", ":"), sort_keys=True)`, including `NaN` and `Infinity`. */
internal fun pyDumps(value: JsonElement): String {
    val out = StringBuilder()
    fun write(item: JsonElement) {
        when (item) {
            is JsonNull -> out.append("null")
            is JsonObject -> {
                out.append('{')
                item.keys.sortedWith(io.github.rubixhacker.harness.contract.CanonicalJson::compareCodePoints)
                    .forEachIndexed { index, key ->
                        if (index > 0) out.append(',')
                        out.append(JsonPrimitive(key).toString()).append(':')
                        write(item.getValue(key))
                    }
                out.append('}')
            }
            is JsonArray -> {
                out.append('[')
                item.forEachIndexed { index, child ->
                    if (index > 0) out.append(',')
                    write(child)
                }
                out.append(']')
            }
            is JsonPrimitive -> {
                if (item.isString) {
                    out.append(item.toString())
                } else if (item.isIntegerLiteral()) {
                    out.append(item.content)
                } else {
                    val number = item.content.toDoubleOrNull()
                    when {
                        number == null -> out.append(item.content)
                        number.isNaN() -> out.append("NaN")
                        number == Double.POSITIVE_INFINITY -> out.append("Infinity")
                        number == Double.NEGATIVE_INFINITY -> out.append("-Infinity")
                        else -> out.append(
                            io.github.rubixhacker.harness.contract.CanonicalJson.pythonFloat(number),
                        )
                    }
                }
            }
        }
    }
    write(value)
    return out.toString()
}

internal fun encoded(rows: List<JsonObject>): ByteArray =
    rows.joinToString("") { pyDumps(it) + "\n" }.toByteArray(Charsets.UTF_8)

internal fun gzip(data: ByteArray): ByteArray {
    val buffer = ByteArrayOutputStream()
    GZIPOutputStream(buffer).use { it.write(data) }
    return buffer.toByteArray()
}

/** The scenario scaffolding `test_compare.py` builds in `setUp`. */
internal class ComparatorScenario {
    val root: Path = Files.createTempDirectory("numerical-compare")
    var rows: List<JsonObject> = defaultRows()
    val fixture = LinkedHashMap<String, JsonElement>(defaultFixture())

    init {
        writeReference(rows)
        writeCandidate(rows)
    }

    fun close() {
        root.toFile().deleteRecursively()
    }

    fun referencePath(): Path = root.resolve("reference.jsonl.gz")
    fun candidatePath(): Path = root.resolve("candidate.jsonl")
    fun receiptPath(): Path = root.resolve("receipt.json")

    fun writeReference(rows: List<JsonObject>) {
        val data = encoded(rows)
        val path = referencePath()
        Files.write(path, gzip(data))
        val reference = LinkedHashMap<String, JsonElement>(fixture.getValue("reference") as JsonObject)
        reference["gzip_sha256"] = JsonPrimitive(Sha256.of(Files.readAllBytes(path)))
        reference["stream_sha256"] = JsonPrimitive(Sha256.of(data))
        reference["input_sha256"] = JsonPrimitive(
            Sha256.of(data.toString(Charsets.UTF_8).split("\n")[0]),
        )
        fixture["reference"] = JsonObject(reference)
    }

    fun writeCandidate(
        rows: List<JsonObject>,
        source: String = "c".repeat(64),
        artifact: String = "d".repeat(64),
        counts: JsonObject = fixture.getValue("counts") as JsonObject,
        skipped: Int = 0,
    ) {
        val data = encoded(rows)
        Files.write(candidatePath(), data)
        val reference = fixture.getValue("reference") as JsonObject
        val receipt = LinkedHashMap<String, JsonElement>()
        receipt["source_sha256"] = JsonPrimitive(source)
        receipt["artifact_sha256"] = JsonPrimitive(artifact)
        receipt["candidate_commit"] = JsonPrimitive("1".repeat(40))
        receipt["trace_sha256"] = JsonPrimitive(Sha256.of(data))
        receipt["reference_source_revision"] = fixture.getValue("baseline_source_revision")
        receipt["reference_artifact_sha256"] = fixture.getValue("baseline_jar_sha256")
        receipt["reference_trace_sha256"] = reference.getValue("gzip_sha256")
        receipt["expected_counts"] = counts
        receipt["executed_counts"] = counts
        receipt["skipped"] = JsonPrimitive(skipped)
        Files.writeString(receiptPath(), JsonObject(receipt).toString())
    }

    fun writeReceipt(fields: Map<String, JsonElement>) {
        val receipt = LinkedHashMap<String, JsonElement>(
            kotlinx.serialization.json.Json
                .parseToJsonElement(Files.readString(receiptPath())) as JsonObject,
        )
        receipt.putAll(fields)
        Files.writeString(receiptPath(), JsonObject(receipt).toString())
    }

    fun result(): JsonObject = CompareHost.compare(
        JsonObject(fixture),
        referencePath(),
        candidatePath(),
        receiptPath(),
        "c".repeat(64),
        "d".repeat(64),
        "1".repeat(40),
    )

    fun auditReference(): JsonObject =
        CompareHost.auditReference(JsonObject(fixture), referencePath())

    companion object {
        fun defaultRows(): List<JsonObject> = listOf(
            parseRow(
                """{"kind":"inputs","id":"sample","dt":0.5}""",
            ),
            parseRow(
                """{"kind":"event","step":1,"order":0,"listener":"StepListener",""" +
                    """"method":"begin","payload":[{"velocity":[1.0,-2.0],""" +
                    """"getPoint":[0.0,0.0],"getDepth":0.1,"getNormalImpulse":0.25}]}""",
            ),
            parseRow(
                """{"kind":"state","step":1,"state":{"position":[2.0,3.0],""" +
                    """"normal":[1.0,0.0],"angle":3.141592653589793,"sum":9.0}}""",
            ),
        )

        fun defaultFixture(): Map<String, JsonElement> = linkedMapOf(
            "id" to JsonPrimitive("sample"),
            "reference" to parseRow("""{"file":"reference.jsonl.gz"}"""),
            "source_sha256" to JsonPrimitive("a".repeat(64)),
            "artifact_sha256" to JsonPrimitive("b".repeat(64)),
            "baseline_source_revision" to JsonPrimitive("f".repeat(40)),
            "baseline_jar_sha256" to JsonPrimitive("e".repeat(64)),
            "counts" to parseRow("""{"inputs":1,"event":1,"state":1}"""),
            "rules" to kotlinx.serialization.json.Json.parseToJsonElement(
                """[{"path":"event.payload[].velocity[]","metric":"scalar","absolute":0.1,""" +
                    """"relative":0,"unit":"m/s"},""" +
                    """{"path":"event.payload[].getPoint[]","metric":"scalar","absolute":0.01,""" +
                    """"relative":0,"unit":"m"},""" +
                    """{"path":"event.payload[].getDepth","metric":"scalar","absolute":0.01,""" +
                    """"relative":0,"unit":"m"},""" +
                    """{"path":"event.payload[].getNormalImpulse","metric":"scalar",""" +
                    """"absolute":0.01,"relative":0,"unit":"N s"},""" +
                    """{"path":"state.state.position[]","metric":"scalar","absolute":0.1,""" +
                    """"relative":0.01,"unit":"m"},""" +
                    """{"path":"state.state.normal","metric":"direction","absolute":0.01,""" +
                    """"relative":0,"magnitude_absolute":0.001,"unit_deviation":0.001,""" +
                    """"unit":"rad"},""" +
                    """{"path":"state.state.angle","metric":"orientation","absolute":0.01,""" +
                    """"relative":0,"unit":"rad"},""" +
                    """{"path":"state.state.sum","metric":"scalar","absolute":0.01,""" +
                    """"relative":0,"unit":"rad"}]""",
            ),
            "exact_numeric" to kotlinx.serialization.json.Json.parseToJsonElement(
                """["inputs.dt","event.step","event.order","state.step"]""",
            ),
        )
    }
}

internal fun parseRow(text: String): JsonObject =
    kotlinx.serialization.json.Json.parseToJsonElement(text) as JsonObject

internal fun parseJson(text: String): JsonElement =
    kotlinx.serialization.json.Json.parseToJsonElement(text)

/** The rows of a recorded trace as mutable JSON objects. */
internal fun rows(text: String): List<JsonObject> =
    text.trim().lines().filter { it.isNotBlank() }.map { parseRow(it) }

internal fun JsonArray.deepCopy(): JsonArray =
    kotlinx.serialization.json.Json.parseToJsonElement(toString()) as JsonArray

internal fun numbers(vararg values: Double): JsonArray =
    JsonArray(values.map { JsonPrimitive(it) })

internal fun JsonObject.with(key: String, value: JsonElement): JsonObject =
    JsonObject(LinkedHashMap(this).apply { put(key, value) })

internal fun JsonObject.without(key: String): JsonObject =
    JsonObject(LinkedHashMap(this).apply { remove(key) })

internal fun JsonArray.with(index: Int, value: JsonElement): JsonArray =
    JsonArray(toMutableList().apply { set(index, value) })
