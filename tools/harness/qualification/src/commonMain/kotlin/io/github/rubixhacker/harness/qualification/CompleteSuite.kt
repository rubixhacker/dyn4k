package io.github.rubixhacker.harness.qualification

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject

/**
 * Case selection of the frozen complete-port suite manifest.
 *
 * Ported from `qualify.full_suite_cases`. The checks are the ones that make a suite usable as
 * lane evidence: every required area is covered, identities are unique, and a lane selects a
 * complete, non-duplicated subset of case scopes.
 */
object CompleteSuite {
    private val areas = listOf("geometry", "collision", "dynamics", "joints", "compatibility")
    private val areaSet: Set<String> = areas.toSet()
    private val scopeNames = setOf("portable", "jvm-only")

    /** Returns the selected case identities of one lane, or of the whole suite when no lane is given. */
    fun cases(suiteManifest: JsonElement?, laneId: String? = null): List<String> {
        val manifest = suiteManifest as? JsonObject
            ?: throw IllegalArgumentException("frozen complete suite manifest is unavailable")
        if (Py.str(manifest["kind"]) != "complete-port") {
            throw IllegalArgumentException("frozen complete suite manifest is unavailable")
        }
        if (!Py.equalsInt(manifest["schema"], 1) || !Py.truthy(manifest["id"])) {
            throw IllegalArgumentException("complete suite manifest identity is invalid")
        }
        val cases = manifest["cases"]
        if (cases !is JsonArray || cases.isEmpty()) {
            throw IllegalArgumentException("complete suite manifest has no cases")
        }
        val declaredAreas = manifest["areas"]
        if (declaredAreas !is JsonArray ||
            declaredAreas.any { Py.str(it) == null } ||
            declaredAreas.map { Py.str(it)!! }.toSet() != areaSet
        ) {
            throw IllegalArgumentException("complete suite manifest omits a required area")
        }

        val identities = mutableListOf<String>()
        val covered = mutableSetOf<String>()
        for (item in cases) {
            if (item !is JsonObject) {
                throw IllegalArgumentException("complete suite case identity is invalid")
            }
            val identity = Py.str(item["id"])
            if (identity == null || identity.isEmpty()) {
                throw IllegalArgumentException("complete suite case identity is invalid")
            }
            val area = Py.str(item["area"])
            if (area == null || area !in areaSet) {
                throw IllegalArgumentException("complete suite case area is invalid")
            }
            identities.add(identity)
            covered.add(area)
        }
        if (identities.toSet().size != identities.size || covered != areaSet) {
            throw IllegalArgumentException("complete suite cases are duplicate or incomplete")
        }

        val lanes = manifest["lanes"]
        if (laneId == null || lanes == null) return identities

        val lane = if (lanes is JsonObject) lanes[laneId] else null
        if (lane !is JsonObject) {
            throw IllegalArgumentException("complete suite lane is missing")
        }
        val declaredScopes = (lane["case_scopes"] as? JsonArray)?.map { Py.str(it) } ?: emptyList()
        if (declaredScopes.isEmpty() ||
            declaredScopes.any { it == null || it !in scopeNames } ||
            declaredScopes.toSet().size != declaredScopes.size
        ) {
            throw IllegalArgumentException("complete suite lane case scopes are invalid")
        }
        val declared = declaredScopes.filterNotNull().toSet()

        val selected = mutableListOf<String>()
        val selectedAreas = mutableSetOf<String>()
        for (item in cases) {
            val case = item as JsonObject
            if (Py.str(case["scope"]) in declared) {
                selected.add(Py.str(case["id"])!!)
                selectedAreas.add(Py.str(case["area"])!!)
            }
        }
        if (selected.isEmpty() || selectedAreas != areaSet) {
            throw IllegalArgumentException("complete suite lane cases are incomplete")
        }
        return selected
    }
}
