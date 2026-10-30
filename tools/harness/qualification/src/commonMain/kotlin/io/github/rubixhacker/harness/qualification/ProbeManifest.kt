package io.github.rubixhacker.harness.qualification

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject

/** One selected case of a foundation probe group. */
data class ProbeCase(val classname: String, val name: String)

/**
 * Foundation probe manifest rules of `qualify.py`.
 *
 * A probe group names its cases either directly or through shared case-name sets, and a probe
 * report is only accounting evidence when every selected case ran exactly once, nothing failed,
 * errored, or was skipped, and the aggregate totals equal the per-group totals.
 */
object ProbeManifest {
    /** `qualify.expected_probe_cases`. */
    fun expectedCases(manifest: JsonObject, group: JsonObject): List<ProbeCase> {
        val raw: JsonElement? = if ("cases" in group) group["cases"] else null
        val cases: JsonElement = raw ?: buildCases(manifest, group)
        if (cases !is JsonArray) {
            throw IllegalArgumentException("probe cases must be a list")
        }
        val identities = mutableListOf<ProbeCase>()
        for (item in cases) {
            val entry = item as? JsonObject
            val classname = Py.str(entry?.get("classname"))
            val name = Py.str(entry?.get("name"))
            if (entry == null || classname.isNullOrEmpty() || name.isNullOrEmpty()) {
                throw IllegalArgumentException("probe case identity is invalid")
            }
            identities.add(ProbeCase(classname, name))
        }
        if (identities.toSet().size != identities.size) {
            throw IllegalArgumentException("probe manifest has duplicate case identities")
        }
        return identities
    }

    private fun buildCases(manifest: JsonObject, group: JsonObject): JsonArray {
        val caseSets = manifest["case_sets"]
        if (caseSets != null && caseSets !is JsonObject) {
            throw IllegalArgumentException("probe case sets are invalid")
        }
        val sets = caseSets as? JsonObject
        val namesElement: JsonElement? = if ("case_set" in group) {
            val key = Py.str(group["case_set"])
            key?.let { sets?.get(it) }
        } else {
            manifest["case_names"] ?: JsonArray(emptyList())
        }
        val names = strings(namesElement, "probe case names are invalid")
        val suffix = Py.str(group["name_suffix"]) ?: ""

        val cases = mutableListOf<JsonObject>()
        for (name in names) {
            cases.add(caseOf(Py.str(group["classname"]), name + suffix))
        }
        val additional = group["additional_case_names"] ?: JsonArray(emptyList())
        if (additional !is JsonArray) {
            throw IllegalArgumentException("additional probe case names must be a list")
        }
        for (name in strings(additional, "probe case names are invalid")) {
            cases.add(caseOf(Py.str(group["additional_classname"]), name + suffix))
        }
        val extraSets = group["extra_case_sets"] ?: JsonArray(emptyList())
        if (extraSets !is JsonArray) {
            throw IllegalArgumentException("probe case sets are invalid")
        }
        for (extra in extraSets) {
            val reference = extra as? JsonObject
            val key = Py.str(reference?.get("case_set"))
            if (reference == null || key == null) {
                throw IllegalArgumentException("probe case set reference is invalid")
            }
            val extraNames = sets?.get(key)
            if (extraNames !is JsonArray || extraNames.isEmpty()) {
                throw IllegalArgumentException("probe case set is missing or invalid")
            }
            for (name in strings(extraNames, "probe case set is missing or invalid")) {
                cases.add(caseOf(Py.str(reference["classname"]), name + suffix))
            }
        }
        return JsonArray(cases)
    }

    private fun caseOf(classname: String?, name: String): JsonObject = JsonObject(
        linkedMapOf(
            "classname" to (classname?.let { kotlinx.serialization.json.JsonPrimitive(it) }
                ?: kotlinx.serialization.json.JsonNull),
            "name" to kotlinx.serialization.json.JsonPrimitive(name),
        ),
    )

    private fun strings(value: JsonElement?, message: String): List<String> {
        if (value !is JsonArray) throw IllegalArgumentException(message)
        val result = mutableListOf<String>()
        for (item in value) {
            val text = Py.str(item)
            if (text.isNullOrEmpty()) throw IllegalArgumentException(message)
            result.add(text)
        }
        return result
    }

    /** `qualify.validate_probe_accounting`: returns the aggregate totals in recorded order. */
    fun validateAccounting(probe: JsonObject, manifest: JsonObject, groupIds: List<String>): Map<String, Long> {
        val groups = LinkedHashMap<String, JsonObject>()
        val declared = manifest["groups"] ?: JsonArray(emptyList())
        if (declared is JsonArray) {
            for (item in declared) {
                val group = item as? JsonObject ?: continue
                val id = Py.str(group["id"]) ?: continue
                groups[id] = group
            }
        }
        val summaries = probe["groups"]
        if (summaries !is JsonArray) {
            throw IllegalArgumentException("probe report group counts are missing")
        }
        val byId = LinkedHashMap<String, JsonObject>()
        for (item in summaries) {
            val summary = item as? JsonObject ?: continue
            val id = Py.str(summary["id"]) ?: continue
            byId[id] = summary
        }
        if (byId.size != summaries.size || byId.keys != groupIds.toSet()) {
            throw IllegalArgumentException("probe report group counts differ from selected groups")
        }
        val totals = linkedMapOf(
            "expected" to 0L, "executed" to 0L, "reported" to 0L,
            "failures" to 0L, "errors" to 0L, "skipped" to 0L,
        )
        for (groupId in groupIds) {
            val group = groups[groupId]
                ?: throw IllegalArgumentException("probe manifest group is missing: $groupId")
            val summary = byId.getValue(groupId)
            val selected = expectedCases(manifest, group).size.toLong()
            if (!Py.isInt(summary["expected"]) || Py.int(summary["expected"]) != selected ||
                !Py.isInt(summary["executed"]) || Py.int(summary["executed"]) != selected ||
                !Py.isInt(summary["reported"]) || Py.int(summary["reported"]) < selected
            ) {
                throw IllegalArgumentException("probe counts differ from selected cases: $groupId")
            }
            for (key in listOf("failures", "errors", "skipped")) {
                if (!Py.isInt(summary[key]) || Py.int(summary[key]) != 0L) {
                    throw IllegalArgumentException("probe has failed, errored, or skipped cases: $groupId")
                }
            }
            for (key in totals.keys) {
                totals[key] = totals.getValue(key) + Py.int(summary[key])
            }
        }
        for ((key, value) in totals) {
            if (!Py.isInt(probe[key]) || Py.int(probe[key]) != value) {
                throw IllegalArgumentException("probe aggregate $key differs from report groups")
            }
        }
        return totals
    }

    /** `qualify.execution_succeeded`: every planned lane ran and recorded a fresh invocation. */
    fun executionSucceeded(evidence: JsonObject): Boolean {
        if (evidence.isEmpty()) return false
        for (result in evidence.values) {
            val entry = result as? JsonObject ?: return false
            if ("error" in entry || "unavailable_reason" in entry) return false
            if (!Py.equalsInt(entry["exit_code"], 0)) return false
            if (!Py.INVOCATION.matches(Py.str(entry["invocation_id"]) ?: "")) return false
        }
        return true
    }
}
