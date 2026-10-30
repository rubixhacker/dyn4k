package io.github.rubixhacker.harness.qualification

import io.github.rubixhacker.harness.contract.Sha256
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.LinkOption
import java.nio.file.Path
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

/** Thrown when evidence that the reference reports as absent is missing. */
class IncompleteEvidence(message: String) : Exception(message)

/**
 * `independent_gates.py`, second slice: the numerical policy and ancestry layer, the physical
 * disposition tables, and the prospective (P2) scope and summary contracts.
 *
 * The verifiers that *execute* the numerical engines (`verify_nominal_physical_case`,
 * `verify_joint_physical_cases`, `_verify_p2_host`, `verify_pending_prospective_bridge`,
 * `verify_prospective_case_subgates`, `_numerical_modules`, `_joint_quality_module`,
 * `_nominal_module`) load the Python analyzers under `tools/numerical` at run time; they cannot be
 * ported until those analyzers are Kotlin. The checker and producer bindings that select those
 * analyzers' approved bytes, and the rotation-oracle audit of one target payload, are ported in
 * [GatesProspective].
 */
object GatesNumerical {
    const val HISTORICAL_FIXTURE_SHA256 =
        "658f3216584a9842b9d9826767521f6bca1a9df0ed006b447a72a47d4915065c"
    const val CURRENT_FIXTURE_REVISION = "b22ea2ddeb6c68242e688e9c9aa3214c4a8b495b"

    const val PROSPECTIVE_POLICY_REVISION = "83914cfc86f3add09ea65c89dc5b3e6035f709a0"
    const val PROSPECTIVE_POLICY_SHA256 =
        "fab269814476a5a0c1d65f268f6c4177bb942ea8e7cdf1ea5ab8d4d9dcd2e160"
    const val PROSPECTIVE_PREVIOUS_POLICY_REVISION = "e038c334caa07a1547b86839f5d467c5f73ec708"
    const val PROSPECTIVE_PREVIOUS_POLICY_SHA256 =
        "1b80b7c198d510ab16784348661053a4bde6507548f5ec12d4a460287ec7b484"
    const val PROSPECTIVE_HISTORICAL_POLICY_REVISION = "7213238591db1611da86cdec075978190ca6d52f"
    const val PROSPECTIVE_HISTORICAL_POLICY_SHA256 =
        "5c8e2ca48a2128b99b2f52188f0f556c3dad3030bde00975bc80d2a25b0c74bb"
    const val PROSPECTIVE_POLICY_PATH = "tools/numerical/portable/prospective_policy_catalog.json"
    const val PROSPECTIVE_CASE_COUNT = 318
    const val JOINT_PHYSICAL_STEPS = 36000
    val JOINT_PHYSICAL_CASES = listOf("weld-spring-equal", "pulley-taut")

    val APPROVED_COMPARATOR_REVISIONS = listOf(
        "f0349a0d29f91879fc52286899f39e042c8523f6",
        "168fbfcdabd68cfb9317310958d6be7f52b38f05",
    )

    val APPROVED_POLICY = linkedMapOf(
        "tools/numerical/fixtures.json" to
            "3086e982d8a4915634bd62d50dbfa0bf4f6e8cc0070a7a16d1f4bede9764d48a",
        "tools/numerical/compare.py" to
            "4a6b4646683389aca643551b5672ca94d2f1e6dd49adad1c4684472b2b97348d",
        "tools/numerical/physical.py" to
            "98ff243a02eece8a47a4faeda06385696174b2b10836e4e1315d6a13e22ee5ba",
        "tools/numerical/weld-pulley-physical-declaration.json" to
            "9794a4ef64c93f6ff76afb03d98784b27be68fe413256362abf1a3f84cf96368",
        "tools/numerical/weld-pulley-physical-manifest.json" to
            "5531b263fbd5a7684db0ea9fbef167c8d8772104949ce01ba4de7606498aecab",
        "tools/numerical/weld_pulley_quality.py" to
            "f8c7cb7449b5d007e5c7dabb20e08deda93974b3cd8a4bedf0cd96f1640c2c87",
    )

    /** `_proven_ancestor`: is `revision` a proven ancestor of the candidate commit? */
    fun provenAncestor(repository: Path, revision: String, candidateSha: String, label: String): Boolean {
        val prefix = listOf("git", "--no-replace-objects", "-C", repository.toString())
        fun run(vararg arguments: String): Pair<Int, String> {
            val process = ProcessBuilder(prefix + arguments).start()
            val output = process.inputStream.use { it.readBytes() }
            val error = process.errorStream.use { it.readBytes() }
            val status = process.waitFor()
            if (error.isNotEmpty()) {
                throw IllegalArgumentException("$label revision ancestry is unavailable")
            }
            return status to output.toString(StandardCharsets.UTF_8)
        }
        val shallow = run("rev-parse", "--is-shallow-repository")
        if (shallow.first != 0 || shallow.second.trim() != "false") {
            throw IllegalArgumentException("$label revision ancestry is unavailable")
        }
        val graftPath = run("rev-parse", "--git-path", "info/grafts")
        if (graftPath.first != 0 || graftPath.second.trim().isEmpty()) {
            throw IllegalArgumentException("$label revision ancestry is unavailable")
        }
        var grafts = Path.of(graftPath.second.trim())
        if (!grafts.isAbsolute) grafts = repository.resolve(grafts)
        if (Files.isRegularFile(grafts) && Files.size(grafts) > 0) {
            throw IllegalArgumentException("$label revision ancestry is unavailable")
        }
        val history = run("rev-list", "--missing=print", candidateSha)
        if (history.first != 0 || history.second.lines().any { it.startsWith("?") }) {
            throw IllegalArgumentException("$label revision ancestry is unavailable")
        }
        val checked = ProcessBuilder(
            prefix + listOf("merge-base", "--is-ancestor", revision, candidateSha),
        ).redirectOutput(ProcessBuilder.Redirect.DISCARD).start()
        val error = checked.errorStream.use { it.readBytes() }
        val status = checked.waitFor()
        if (error.isNotEmpty() || status !in setOf(0, 1)) {
            throw IllegalArgumentException("$label revision ancestry is unavailable")
        }
        return status == 0
    }

    /** `verified_numerical_source_sha256`: SHA-256 of the committed source archive. */
    fun verifiedNumericalSourceSha256(repository: Path, candidateSha: String?): String {
        if (candidateSha == null || !IndependentGates.SHA40.matches(candidateSha)) {
            throw IllegalArgumentException("numerical source requires an exact candidate commit")
        }
        val process = ProcessBuilder(
            "git", "-c", "core.autocrlf=false", "--no-replace-objects",
            "-C", repository.toString(), "archive", "--format=tar", candidateSha,
        ).start()
        val output = process.inputStream.use { it.readBytes() }
        process.errorStream.close()
        if (process.waitFor() != 0) {
            throw IllegalArgumentException("candidate source archive is unavailable")
        }
        return CorpusFiles.digest(output)
    }

    /** `_prospective_policy_version`: which adopted prospective policy catalog applies. */
    fun prospectivePolicyVersion(repository: Path, candidateSha: String): Pair<String, String> {
        for ((revision, digest) in listOf(
            PROSPECTIVE_POLICY_REVISION to PROSPECTIVE_POLICY_SHA256,
            PROSPECTIVE_PREVIOUS_POLICY_REVISION to PROSPECTIVE_PREVIOUS_POLICY_SHA256,
            PROSPECTIVE_HISTORICAL_POLICY_REVISION to PROSPECTIVE_HISTORICAL_POLICY_SHA256,
        )) {
            val checked = ProcessBuilder(
                "git", "--no-replace-objects", "-C", repository.toString(),
                "merge-base", "--is-ancestor", revision, candidateSha,
            ).redirectOutput(ProcessBuilder.Redirect.DISCARD).start()
            val error = checked.errorStream.use { it.readBytes() }
            val status = checked.waitFor()
            if (status == 0) return revision to digest
            if (status != 1 || error.isNotEmpty()) {
                throw IllegalArgumentException("prospective policy revision ancestry is unavailable")
            }
        }
        return PROSPECTIVE_HISTORICAL_POLICY_REVISION to PROSPECTIVE_HISTORICAL_POLICY_SHA256
    }

    /** `approved_prospective_catalog`: the adopted 318-case policy catalog. */
    fun approvedProspectiveCatalog(repository: Path, candidateSha: String? = null): JsonObject {
        val (revision, expectedSha) = if (candidateSha == null) {
            PROSPECTIVE_POLICY_REVISION to PROSPECTIVE_POLICY_SHA256
        } else {
            prospectivePolicyVersion(repository, candidateSha)
        }
        val raw = gitShow(repository, revision, PROSPECTIVE_POLICY_PATH)
        if (CorpusFiles.digest(raw) != expectedSha) {
            throw IllegalArgumentException("adopted prospective policy catalog differs")
        }
        val catalog = StrictObjectJson.parse(raw.toString(StandardCharsets.UTF_8)) as? JsonObject
            ?: throw IllegalArgumentException("adopted prospective policy catalog differs")
        val cases = catalog["cases"]
        if (cases !is JsonObject || cases.size != PROSPECTIVE_CASE_COUNT ||
            cases.keys.any { it.isEmpty() }
        ) {
            throw IllegalArgumentException("adopted prospective case inventory differs")
        }
        return catalog
    }

    /** `approved_prospective_cases`: the adopted case names in reference order. */
    fun approvedProspectiveCases(repository: Path): List<String> =
        approvedProspectiveCatalog(repository).getValue("cases").let { it as JsonObject }
            .keys.sortedWith(CanonicalText::compare)

    /** `_policy_binding`: the numerical policy, comparator, and fixture blobs of one candidate. */
    fun policyBinding(repository: Path, candidateSha: String): Map<String, String> {
        val fixture = "tools/numerical/fixtures.json"
        val checker = "tools/numerical/compare.py"
        val approved = IndependentGates.sourceBinding(
            repository, candidateSha,
            APPROVED_POLICY.filterKeys { it != fixture && it != checker },
            "numerical approved policy/checker",
        )
        val localChecker = repository.resolve(checker)
        if (CorpusFiles.digest(localChecker) != APPROVED_POLICY.getValue(checker)) {
            throw IllegalArgumentException("numerical approved policy/checker blob differs: $checker")
        }
        val committedChecker = gitShow(repository, candidateSha, checker)
        val lineage = APPROVED_COMPARATOR_REVISIONS.map { revision ->
            provenAncestor(repository, revision, candidateSha, "numerical comparator")
        }
        val expectedChecker = if (lineage.any { it }) {
            APPROVED_POLICY.getValue(checker)
        } else {
            HISTORICAL_COMPARATOR_SHA256
        }
        val checkerDigest = CorpusFiles.digest(committedChecker)
        if (checkerDigest != expectedChecker) {
            throw IllegalArgumentException("numerical approved policy/checker blob differs: $checker")
        }
        val localFixture = repository.resolve(fixture)
        val committedFixture = gitShow(repository, candidateSha, fixture)
        val candidateDigest = CorpusFiles.digest(committedFixture)
        val changed = provenAncestor(repository, CURRENT_FIXTURE_REVISION, candidateSha, "numerical fixture")
        val expectedFixture = if (changed) APPROVED_POLICY.getValue(fixture) else HISTORICAL_FIXTURE_SHA256
        if (CorpusFiles.digest(localFixture) != APPROVED_POLICY.getValue(fixture) ||
            candidateDigest != expectedFixture
        ) {
            throw IllegalArgumentException("numerical approved policy/checker blob differs: $fixture")
        }
        return approved + mapOf(checker to checkerDigest, fixture to candidateDigest)
    }

    /** `HISTORICAL_COMPARATOR_SHA256`, the comparator of the historic baseline. */
    const val HISTORICAL_COMPARATOR_SHA256 =
        "6e9abe839c74ac9be1e8507e4a693b0414e70063f878481c94ab136c7ec89f4f"

    /** `_missing_numerical_subgates`: the recorded NOT_RUN numerical subgates. */
    fun missingNumericalSubgates(repository: Path): JsonObject {
        val cases = buildJsonObject {
            for (name in approvedProspectiveCases(repository)) {
                put(
                    name,
                    buildJsonObject {
                        put("rule", JsonPrimitive("NOT_RUN"))
                        put("arithmetic", JsonPrimitive("NOT_RUN"))
                        put("status", JsonPrimitive("NOT_RUN"))
                    },
                )
            }
        }
        return buildJsonObject {
            put(
                "frozen-traces",
                buildJsonObject {
                    put("status", JsonPrimitive("NOT_RUN"))
                    put("required_cases", JsonPrimitive(14))
                },
            )
            put(
                "prospective-rule-arithmetic",
                buildJsonObject {
                    put("status", JsonPrimitive("NOT_RUN"))
                    put("required_cases", JsonPrimitive(PROSPECTIVE_CASE_COUNT))
                    put(
                        "reason",
                        JsonPrimitive(
                            "318 per-case rule comparisons and target arithmetic audits are absent",
                        ),
                    )
                    put(
                        "reference_diagnostic",
                        JsonPrimitive(
                            "historical b22ea2ddeb6c68242e688e9c9aa3214c4a8b495b 318-case " +
                                "self-check with checker SHA-256 " +
                                "2f7743fed70ec9403492f84e880a286368a5f4c9f06f32c62996c91da837dd4f: " +
                                "41 failed derived rules, 4 unpassed premises, " +
                                "1 failed physical; current checker 75-case geometry replay: " +
                                "12 unpassed premises; current 318-case self-check NOT_RUN",
                        ),
                    )
                    put("cases", cases)
                },
            )
        }
    }

    /** `_legacy_joint_physical_profile`: the unresolved old four-case physical residual. */
    fun legacyJointPhysicalProfile(): JsonObject = buildJsonObject {
        put("candidate_status", JsonPrimitive("NOT_RUN"))
        put("required_cases", JsonPrimitive(4))
        put(
            "reason",
            JsonPrimitive(
                "old four Weld/Pulley physical residual disposition is unresolved; " +
                    "parity traces and newer cases do not establish physical acceptance",
            ),
        )
    }

    /** `_missing_physical_profiles`: the recorded physical profile dispositions. */
    fun missingPhysicalProfiles(): JsonObject = buildJsonObject {
        put(
            "default-sleep-wake",
            buildJsonObject {
                put("candidate_status", JsonPrimitive("NOT_RUN"))
                put("approved_reference_status", JsonPrimitive("FAILED_125847_OF_126000"))
            },
        )
        put(
            "configured-sleep-wake",
            buildJsonObject {
                put("candidate_status", JsonPrimitive("NOT_RUN"))
                put("approved_reference_status", JsonPrimitive("PASSED"))
            },
        )
        put(
            "weld-pulley",
            buildJsonObject {
                put("candidate_status", JsonPrimitive("NOT_RUN"))
                put("required_cases", JsonPrimitive(JOINT_PHYSICAL_CASES.size))
                put("steps_per_case", JsonPrimitive(JOINT_PHYSICAL_STEPS))
                put("approved_reference_status", JsonPrimitive("PASSED_BASELINE_ONLY"))
                put(
                    "legacy_pulley_diagnostic",
                    JsonPrimitive(
                        "39 old-reference samples exceeded the 0.005 m solver tolerance; " +
                            "observed maximum extension 0.1208278904872957 m",
                    ),
                )
                put(
                    "reason",
                    JsonPrimitive("candidate Weld and Pulley physical traces are absent"),
                )
            },
        )
        put("legacy-weld-pulley", legacyJointPhysicalProfile())
        put(
            "nominal",
            buildJsonObject {
                put("candidate_status", JsonPrimitive("NOT_RUN"))
                put(
                    "reason",
                    JsonPrimitive("candidate nominal physical quality evidence is absent"),
                )
            },
        )
    }

    /** `physical_status`: FAILED when any profile failed, otherwise NOT_RUN. */
    fun physicalStatus(profiles: JsonObject): String {
        val required = listOf("default-sleep-wake", "configured-sleep-wake", "weld-pulley", "nominal")
        val statuses = required.map { name ->
            val profile = profiles[name] as? JsonObject
                ?: throw IllegalArgumentException("physical profile status differs")
            Py.str(profile["candidate_status"])
                ?: throw IllegalArgumentException("physical profile status differs")
        }
        if (statuses.any { it !in setOf("PASSED", "FAILED", "NOT_RUN") }) {
            throw IllegalArgumentException("physical profile status differs")
        }
        if ("FAILED" in statuses) return "FAILED"
        val legacy = profiles["legacy-weld-pulley"] as? JsonObject
        if (legacy == null || Py.str(legacy["candidate_status"]) != "NOT_RUN") {
            throw IllegalArgumentException("legacy Weld/Pulley physical disposition is not approved")
        }
        return "NOT_RUN"
    }

    /** `_prospective_case_status`: combine one rule and its target arithmetic. */
    fun prospectiveCaseStatus(rule: String, arithmetic: String): String {
        if (rule.startsWith("FAILED") || arithmetic.startsWith("FAILED")) return "FAILED"
        if (rule != "PASSED_NUMERICAL_POLICY") return "NOT_RUN"
        return if (arithmetic == "PASSED") "PASSED" else "NOT_RUN"
    }

    /** `_p2_scope`: the external baseline attestation of one reviewed numerical scope. */
    fun p2Scope(
        scope: JsonElement?,
        candidateSha: String,
        sourceSha256: String,
        artifactSha256: String,
        root: Path,
    ): Path {
        val required = setOf(
            "candidate_sha", "target", "runtime", "runtime_identity",
            "artifact_hashes", "source_sha256", "baseline_attestation_path",
            "baseline_attestation_sha256",
        )
        val value = scope as? JsonObject ?: throw IncompleteEvidence("independent numerical P2 JVM scope is missing")
        val missing = required - value.keys
        if (missing.isNotEmpty()) {
            throw IncompleteEvidence(
                "independent numerical P2 scope field is missing: " +
                    missing.sortedWith(CanonicalText::compare).joinToString(", "),
            )
        }
        val hashes = value["artifact_hashes"] as? JsonObject
        if (value.keys != required ||
            Py.str(value["candidate_sha"]) != candidateSha ||
            Py.str(value["target"]) != "jvm" ||
            Py.str(value["runtime"]) != "Java" ||
            !IndependentGates.SHA64.matches(Py.str(value["runtime_identity"]) ?: "") ||
            Py.str(value["source_sha256"]) != sourceSha256 ||
            hashes == null ||
            hashes.keys != setOf("dyn4k-core", "dyn4k") ||
            Py.str(hashes["dyn4k-core"]) != artifactSha256 ||
            hashes.values.any { !IndependentGates.SHA64.matches(Py.str(it) ?: "") } ||
            !IndependentGates.SHA64.matches(Py.str(value["baseline_attestation_sha256"]) ?: "")
        ) {
            throw IllegalArgumentException(
                "independent numerical P2 source, JVM artifact, or attestation scope differs",
            )
        }
        val sidecar = Path.of(Py.str(value["baseline_attestation_path"]) ?: "")
        if (!sidecar.isAbsolute || !Files.isRegularFile(sidecar, LinkOption.NOFOLLOW_LINKS) ||
            Files.isSymbolicLink(sidecar) ||
            sidecar.toAbsolutePath().normalize().startsWith(root.toAbsolutePath().normalize())
        ) {
            throw IncompleteEvidence("external numerical baseline attestation file is absent")
        }
        if (CorpusFiles.digest(sidecar) != Py.str(value["baseline_attestation_sha256"])) {
            throw IllegalArgumentException(
                "external numerical baseline attestation differs from independent audit",
            )
        }
        return sidecar
    }

    /** `_p2_runtime_identity`: the digest of a reviewed P2 candidate runtime proof. */
    fun p2RuntimeIdentity(proof: JsonElement?): String {
        val required = setOf(
            "host", "os", "machine", "device", "executable",
            "executable_sha256", "version", "method_executions",
            "dependency_sha256", "method_process_sha256",
        )
        val value = proof as? JsonObject ?: throw IllegalArgumentException(
            "reviewed P2 candidate runtime/process proof is incomplete",
        )
        val textKeys = listOf("os", "machine", "executable", "version")
        if (value.keys != required ||
            Py.str(value["host"]) != "jvm" ||
            Py.truthy(value["device"]) ||
            !Py.equalsInt(value["method_executions"], 15) ||
            textKeys.any { Py.str(value[it]).isNullOrEmpty() } ||
            !Path.of(Py.str(value["executable"])!!).isAbsolute ||
            !(Py.str(value["version"])!!.contains("version \"21.")) ||
            listOf("executable_sha256", "dependency_sha256", "method_process_sha256")
                .any { !IndependentGates.SHA64.matches(Py.str(value[it]) ?: "") }
        ) {
            throw IllegalArgumentException("reviewed P2 candidate runtime/process proof is incomplete")
        }
        return IndependentGates.digest(
            buildJsonObject {
                put("schema", JsonPrimitive("reviewed-p2-runtime/1"))
                put("runtime", value)
            },
        )
    }

    /** `_p2_directory`: one prospective raw directory inside the archive. */
    fun p2Directory(root: Path, relative: String): Path {
        checkRelative(relative)
        val directory = relative.split('/').fold(root) { base, part -> base.resolve(part) }
        if (!Files.isDirectory(directory) || Files.isSymbolicLink(directory)) {
            throw IncompleteEvidence("prospective raw directory is missing: $relative")
        }
        if (!directory.toAbsolutePath().normalize()
                .startsWith(root.toAbsolutePath().normalize())
        ) {
            throw IllegalArgumentException("prospective raw directory escapes archive: $relative")
        }
        return directory
    }

    private fun checkRelative(relative: String) {
        if (relative.isEmpty() || "\\" in relative || "\n" in relative || "\r" in relative ||
            relative.split('/').any { it in setOf("", ".", "..") } ||
            ":" in relative.split('/').first()
        ) {
            throw IllegalArgumentException("unsafe archive path: $relative")
        }
    }

    /** `_p2_summary`: the reviewed P2 verifier summary of one 318-case replay. */
    fun p2Summary(
        summary: JsonElement?,
        expected: List<String>,
        methods: Set<String>,
        caseMethods: Map<String, String>,
    ): JsonObject {
        val value = summary as? JsonObject
        val rows = value?.get("results") as? JsonArray
        val evidence = value?.get("operation_evidence") as? JsonObject
        if (rows == null || rows.size != PROSPECTIVE_CASE_COUNT ||
            evidence == null || evidence.keys != methods ||
            caseMethods.keys != expected.toSet() ||
            Py.str(value["operation_binding"]) != "VERIFIED_ARITHMETIC_BINDING"
        ) {
            throw IllegalArgumentException(
                "reviewed P2 verifier omitted raw operation or case coverage",
            )
        }
        val identities = rows.map { element -> (element as? JsonObject)?.let { Py.str(it["id"]) } }
        if (identities != expected) {
            throw IllegalArgumentException("reviewed P2 comparison case identities or order differ")
        }
        val cases = LinkedHashMap<String, JsonObject>()
        for (element in rows) {
            val row = element as JsonObject
            val caseId = Py.str(row["id"])!!
            val method = Py.str(row["operation_method"])
            val receipt = Py.str(row["operation_receipt_sha256"])
            val bound = evidence[method ?: ""] as? JsonObject
            if (method == null || method != caseMethods[caseId] || bound == null ||
                receipt != Py.str(bound["receipt_sha256"]) ||
                !IndependentGates.SHA64.matches(receipt ?: "")
            ) {
                throw IllegalArgumentException(
                    "reviewed P2 operation method or receipt differs: $caseId",
                )
            }
            val rule = Py.str(row["status"])
                ?: throw IllegalArgumentException("reviewed P2 policy status is absent: $caseId")
            val arithmetic = if (Py.str(row["target_arithmetic"]) == "PASSED_BOUND_OPERATION_EVIDENCE") {
                "PASSED"
            } else {
                "NOT_RUN"
            }
            val status = prospectiveCaseStatus(rule, arithmetic)
            if (status == "PASSED" && Py.str(row["qualification"]) != "PASSED_CASE_POLICY") {
                throw IllegalArgumentException("reviewed P2 policy qualification differs: $caseId")
            }
            cases[caseId] = buildJsonObject {
                put("rule", JsonPrimitive(rule))
                put("arithmetic", JsonPrimitive(arithmetic))
                put("status", JsonPrimitive(status))
                put("method", JsonPrimitive(method))
                put("receipt_sha256", JsonPrimitive(receipt))
            }
        }
        val overall = when {
            cases.values.any { Py.str(it["status"]) == "FAILED" } -> "FAILED"
            cases.values.all { Py.str(it["status"]) == "PASSED" } -> "PASSED"
            else -> "NOT_RUN"
        }
        return buildJsonObject {
            put("status", JsonPrimitive(overall))
            put("required_cases", JsonPrimitive(PROSPECTIVE_CASE_COUNT))
            put("methods_verified", JsonPrimitive(evidence.size))
            put("cases", JsonObject(cases))
            put(
                "reason",
                JsonPrimitive("reviewed P2 raw arithmetic and adopted case policy replayed"),
            )
        }
    }

    private fun gitShow(repository: Path, revision: String, path: String): ByteArray {
        val process = ProcessBuilder(
            "git", "--no-replace-objects", "-C", repository.toString(), "show", "$revision:$path",
        ).start()
        val output = process.inputStream.use { it.readBytes() }
        process.errorStream.close()
        if (process.waitFor() != 0) {
            throw IllegalArgumentException("committed input is unavailable: $path")
        }
        return output
    }
}
