package io.github.rubixhacker.harness.baseline

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

/**
 * The parity payload `parity/generate_vectors.py` recorded from `tools/baseline/verify.py`.
 *
 * Every value here was printed by the Python implementation, so an assertion against it is
 * evidence the port reproduces the original rather than evidence the port agrees with itself.
 */
internal object Vectors {
    val root: JsonObject = Json.parseToJsonElement(BaselineVectors.json).jsonObject

    val revision: String = root.str("revision")

    val policy: JsonObject = root.obj("policy")
    val text: JsonObject = root.obj("text")
    val declarations: JsonObject = root.obj("declarations")
    val types: JsonObject = root.obj("types")
    val gates: JsonArray = root.array("gate")
    val reports: JsonObject = root.obj("reports")
    val json: JsonObject = root.obj("json")
    val compare: JsonArray = root.array("compare")
    val checkSource: JsonArray = root.array("check_source")
    val checkRun: JsonArray = root.array("check_run")
    val harness: JsonObject = root.obj("harness")
}

internal fun JsonObject.obj(key: String): JsonObject = getValue(key).jsonObject

internal fun JsonObject.array(key: String): JsonArray = getValue(key).jsonArray

internal fun JsonObject.str(key: String): String = getValue(key).jsonPrimitive.content

internal fun JsonObject.int(key: String): Int = getValue(key).jsonPrimitive.content.toInt()

internal fun JsonObject.bool(key: String): Boolean = getValue(key).jsonPrimitive.content.toBoolean()

internal fun JsonObject.nullableStr(key: String): String? = getValue(key).textOrNull()

internal fun JsonObject.strings(key: String): List<String> =
    array(key).map { it.jsonPrimitive.content }

internal fun JsonObject.stringMap(): Map<String, String> =
    entries.associate { (key, value) -> key to value.jsonPrimitive.content }

/** The text of a JSON string element, or null for a JSON null. */
internal fun JsonElement.textOrNull(): String? = when (this) {
    is JsonNull -> null
    is JsonPrimitive -> content
    else -> null
}

internal fun JsonArray.strings(): List<String> = map { it.jsonPrimitive.content }

/** One `member_inventory` record, as the port models it. */
internal fun memberRecordOf(value: JsonObject): MemberRecord = MemberRecord(
    name = value.str("name"),
    descriptor = value.str("descriptor"),
    flags = value.strings("flags"),
    declaration = value.str("declaration"),
    parameters = value.str("parameters"),
    sourceParameters = value.str("source_parameters"),
    returnType = value.str("return_type"),
    kind = value.str("kind"),
)

/** One `added_member_gate` risk, as the port models it. */
internal fun memberRiskOf(value: JsonObject): MemberRisk = MemberRisk(
    candidateType = value.str("candidate_type"),
    declaringType = value.str("declaring_type"),
    descriptor = value.str("descriptor"),
    flags = value.strings("flags"),
    origin = value.str("origin"),
    kind = value.str("kind"),
    declaration = value.str("declaration"),
    artifactSha256 = value.str("artifact_sha256"),
)
