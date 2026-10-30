package io.github.rubixhacker.harness.qualification

import io.github.rubixhacker.harness.contract.MatrixCase
import io.github.rubixhacker.harness.contract.Qualification
import io.github.rubixhacker.harness.contract.Sha256
import io.github.rubixhacker.harness.contract.StrictJson
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/** One lane verdict of `qualify.evaluate`. */
data class LaneVerdict(val id: String, val status: String, val reason: String)

/**
 * Verification of a JVM mode publication binding.
 *
 * The replay that proves both compiler modes publish distinct JARs still runs the Python
 * `compiler_modes.replay`; the port reaches it through this seam so that `evaluate` keeps the
 * exact problem strings of the reference implementation.
 */
interface JvmModeVerifier {
    /** Throws [IllegalArgumentException] when the binding cannot be verified. */
    fun verify(
        binding: JsonElement?,
        case: MatrixCase,
        candidateSha: String?,
        expectedHashes: Map<String, String?>,
    )
}

/**
 * Lane evidence rules of `qualify.evaluate`.
 *
 * Every problem string is retained verbatim: reports record the joined reason, so a reworded
 * check invalidates retained evidence.
 */
object LaneEvaluation {
    private val requiredEvidence = listOf(
        "candidate_sha", "runtime_identity", "runtime_version", "expected",
        "executed", "failures", "skipped", "consumer", "suite_id",
        "target", "runtime", "version", "configuration", "case_results",
        "artifact_hashes", "invocation_id", "exit_code", "command",
        "candidate_manifest_sha256", "suite_manifest_sha256", "audit_manifest_sha256",
    )

    fun evaluate(
        case: MatrixCase,
        evidence: JsonElement?,
        candidateSha: String? = null,
        candidateManifest: JsonElement? = null,
        suiteManifest: JsonElement? = null,
        artifactAudit: JsonElement? = null,
        jvmMode: JvmModeVerifier? = null,
    ): LaneVerdict {
        if (evidence == null) {
            return LaneVerdict(case.id, "NOT_RUN", "no evidence supplied")
        }
        val supply = evidence as? JsonObject
            ?: return LaneVerdict(case.id, "FAILED", "evidence must be an object")
        val unavailable = supply["unavailable_reason"]
        if (Py.truthy(unavailable)) {
            val reason = Py.str(unavailable) ?: CanonicalText.of(unavailable)
            return LaneVerdict(case.id, "UNAVAILABLE", reason)
        }

        val problems = mutableListOf<String>()
        for (name in requiredEvidence) {
            if (name !in supply) problems.add("missing $name")
        }
        if (!StrictJson.isFinite(supply)) {
            problems.add("non-finite observation is invalid")
        }
        if (!Py.SHA40.matches(Py.str(supply["candidate_sha"]) ?: "")) {
            problems.add("candidate SHA must be a full commit hash")
        }
        if (!candidateSha.isNullOrEmpty() && Py.str(supply["candidate_sha"]) != candidateSha) {
            problems.add("candidate SHA differs from report")
        }
        val laneValues = linkedMapOf(
            "target" to case.target,
            "runtime" to case.runtime,
            "version" to case.version,
            "configuration" to case.configuration,
        )
        for ((key, value) in laneValues) {
            if (supply[key] != JsonPrimitive(value)) problems.add("$key differs from lane")
        }
        if (!Py.INVOCATION.matches(Py.str(supply["invocation_id"]) ?: "")) {
            problems.add("fresh execution invocation ID is missing")
        }
        if (!Py.equalsInt(supply["exit_code"], 0) || supply["command"] !is JsonArray) {
            problems.add("successful executable command is missing")
        }

        val cases: List<String> = try {
            CompleteSuite.cases(suiteManifest, case.id)
        } catch (error: IllegalArgumentException) {
            problems.add(error.message ?: "")
            emptyList()
        }

        val manifest = candidateManifest as? JsonObject
        val audit = artifactAudit as? JsonObject
        var lane: JsonObject? = null
        if (manifest == null || audit == null) {
            problems.add("candidate manifest and staged artifact audit are required")
        } else {
            if (!Py.equalsInt(manifest["schema"], 1)) {
                problems.add("candidate manifest schema is invalid")
            }
            if (Py.str(manifest["candidate_sha"]) != candidateSha) {
                problems.add("candidate manifest SHA differs from report")
            }
            if (Py.str(audit["candidate_sha"]) != candidateSha || Py.str(audit["status"]) != "PASSED") {
                problems.add("staged artifact audit did not pass for this candidate")
            }
            if (Py.truthy(suiteManifest) &&
                Py.str(manifest["suite_manifest_sha256"]) != Sha256.ofCanonical(suiteManifest!!)
            ) {
                problems.add("candidate manifest does not bind frozen suite")
            }
            if (Py.str(manifest["audit_manifest_sha256"]) != Sha256.ofCanonical(audit)) {
                problems.add("candidate manifest does not bind staged audit")
            }
            for ((name, source) in listOf("candidate_manifest_sha256" to manifest, "audit_manifest_sha256" to audit)) {
                if (Py.str(supply[name]) != Sha256.ofCanonical(source)) {
                    problems.add("$name differs from frozen candidate evidence")
                }
            }
            if (Py.truthy(suiteManifest) &&
                Py.str(supply["suite_manifest_sha256"]) != Sha256.ofCanonical(suiteManifest!!)
            ) {
                problems.add("suite manifest SHA-256 differs from frozen suite")
            }
            val lanes = manifest["lanes"]
            lane = if (lanes is JsonObject) lanes[case.id] as? JsonObject else null
            if (lane == null) {
                problems.add("selected runtime lane is absent from candidate manifest")
            }
        }

        if (lane != null && lane.isNotEmpty()) {
            for (key in listOf("runtime_identity", "runtime_version", "configuration")) {
                val laneValue = lane[key]
                if (Py.str(laneValue) == null || Py.str(laneValue)!!.isEmpty() || supply[key] != laneValue) {
                    problems.add("$key differs from selected candidate runtime")
                }
            }
            if (Py.truthy(suiteManifest)) {
                val suiteId = suiteManifest!!.let { (it as JsonObject)["id"] }
                if (lane["suite_id"] != suiteId || supply["suite_id"] != suiteId) {
                    problems.add("complete suite identity differs from frozen manifest")
                }
            }

            val artifacts = audit!!["artifacts"]
            val audited: Map<String, String?> = if (artifacts is JsonArray) {
                TargetBinaryHashes.of(artifacts)[case.target] ?: emptyMap()
            } else {
                emptyMap()
            }
            val boundHashes = lane["artifact_hashes"]
            if (boundHashes !is JsonObject || boundHashes.keys != Qualification.modules.toSet()) {
                problems.add("both target binary hashes are required")
            } else {
                var verifiedHashes: Map<String, String?> = audited
                val modeBinding = lane["jvm_mode_publication"]
                if (modeBinding != null || "jvm_mode_publication" in lane) {
                    if (case.target != "jvm" || supply["jvm_mode_publication"] != modeBinding) {
                        problems.add("JVM mode publication differs from selected lane evidence")
                    } else {
                        try {
                            val expected = boundHashes.mapValues { (_, value) -> Py.str(value) }
                            if (jvmMode == null) {
                                throw IllegalArgumentException("JVM mode publication verifier is not configured")
                            }
                            jvmMode.verify(modeBinding, case, candidateSha, expected)
                            verifiedHashes = expected
                        } catch (error: Exception) {
                            problems.add("JVM mode publication is unverified: ${error.message}")
                        }
                    }
                }
                for (module in Qualification.modules) {
                    val expectedHash = boundHashes[module]
                    val evidenceHashes = supply["artifact_hashes"]
                    if (!Py.SHA64.matches(Py.str(expectedHash) ?: "") ||
                        verifiedHashes[module] != Py.str(expectedHash) ||
                        evidenceHashes !is JsonObject ||
                        evidenceHashes[module] != expectedHash
                    ) {
                        problems.add("$module binary hash differs from target audit")
                    }
                }
            }
        }

        val observations = supply["case_results"]
        if (observations !is JsonArray) {
            problems.add("complete case results are missing")
        } else {
            val identities = observations.mapNotNull { item ->
                if (item is JsonObject) Py.str(item["id"]) else null
            }
            if (identities.size != observations.size ||
                identities.toSet().size != identities.size ||
                identities.toSet() != cases.toSet()
            ) {
                problems.add("complete case identities are missing, duplicate, or unexpected")
            }
            if (observations.any { item -> item !is JsonObject || Py.str(item["status"]) != "PASSED" }) {
                problems.add("a complete suite case did not pass")
            }
        }

        val countKeys = listOf("expected", "executed", "failures", "skipped")
        for (key in countKeys) {
            if (!Py.isInt(supply[key]) || Py.int(supply[key]) < 0) {
                problems.add("$key must be a nonnegative integer")
            }
        }
        if (countKeys.all { Py.isInt(supply[it]) }) {
            if (cases.isEmpty() ||
                Py.int(supply["expected"]) != cases.size.toLong() ||
                Py.int(supply["executed"]) != cases.size.toLong()
            ) {
                problems.add("suite counts differ from frozen expected cases")
            }
            if (Py.truthy(supply["failures"]) || Py.truthy(supply["skipped"])) {
                problems.add("failed or skipped tests")
            }
        }
        if (Py.str(supply["consumer"]) != "PASSED") {
            problems.add("staged external consumer did not pass")
        }

        if (suiteManifest is JsonObject && suiteManifest["lanes"] is JsonObject) {
            val lanes = suiteManifest["lanes"] as JsonObject
            val laneSpec = lanes[case.id] as? JsonObject
            val requiredGates = linkedSetOf<String>()
            requiredGates.addAll(strings(laneSpec?.get("required_gates")))
            requiredGates.addAll(strings(suiteManifest["global_gates"]))
            val gateResults = supply["gate_results"]
            if (requiredGates.isEmpty() || gateResults !is JsonObject || gateResults.keys != requiredGates) {
                problems.add("complete suite independent gate results are missing or unexpected")
            } else if (requiredGates.any { gate ->
                    val result = gateResults[gate]
                    result !is JsonObject ||
                        Py.str(result["status"]) != "PASSED" ||
                        !Py.SHA64.matches(Py.str(result["receipt_sha256"]) ?: "")
                }
            ) {
                problems.add("complete suite independent gate did not pass with a bound receipt")
            }
        }

        val status = if (problems.isEmpty()) "PASSED" else "FAILED"
        val reason = if (problems.isEmpty()) "all required evidence present" else problems.joinToString("; ")
        return LaneVerdict(case.id, status, reason)
    }

    private fun strings(value: JsonElement?): List<String> =
        if (value is JsonArray) value.mapNotNull { Py.str(it) } else emptyList()
}

/** Renders a decoded JSON value the way Python's `str()` renders it, for reason strings. */
internal object CanonicalText {
    fun compare(left: String, right: String): Int =
        io.github.rubixhacker.harness.contract.CanonicalJson.compareCodePoints(left, right)

    fun of(value: JsonElement?): String = when {
        value == null -> "None"
        value is JsonNull -> "None"
        value is JsonPrimitive -> value.content
        else -> value.toString()
    }
}
