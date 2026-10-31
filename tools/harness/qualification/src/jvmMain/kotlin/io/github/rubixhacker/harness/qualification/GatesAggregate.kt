package io.github.rubixhacker.harness.qualification

import io.github.rubixhacker.harness.contract.Sha256
import io.github.rubixhacker.harness.contract.StrictJson
import java.io.IOException
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.Path
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import org.apache.commons.compress.archivers.tar.TarArchiveInputStream

/**
 * `independent_gates` aggregation: `_independent_review`, `_java_full_ci`, `evaluate_gate`,
 * `evaluate`, `evaluate_assembly`, and `main`.
 *
 * Four gate bodies still run Python-only harnesses — `_migration_journeys` (the Python
 * `journeys`/`validate_plain`/`validate_scene` drivers), `_numerical_entries` (the Python
 * `compare`/`physical` replay engine), `_performance_resource` (the Python
 * `verify_candidate_archive` verifier) and `_evaluate_signed_full_consumer` (the Python
 * `full_signed_routes`/`full_browser_consumer` verifiers). Those bodies fail closed with an
 * explicit `NOT_RUN` verdict naming the missing harness; a gate is never reported `PASSED` from an
 * unperformed check.
 */
object GatesAggregate {
    /** `_result`: one gate verdict with its recorded extras. */
    fun result(
        gate: String,
        status: String,
        reason: String,
        details: Map<String, JsonElement> = emptyMap(),
    ): JsonObject = IndependentGates.result(gate, status, reason, details)

    /**
     * `_independent_review`: two distinct Sol review sessions against the exact final head, each
     * with a substantive assessment and every actionable finding resolved by committed evidence.
     */
    fun reviewVerification(root: Path, candidateSha: String, repository: Path): String {
        val reports = mutableListOf<JsonObject>()
        val sessions = mutableSetOf<String>()
        for (kind in listOf("standards", "spec")) {
            val report = IndependentGates.json(IndependentGates.filePath(root, "$kind.json")) as? JsonObject
                ?: throw IllegalArgumentException("$kind review identity differs from final candidate")
            val sessionPath = IndependentGates.filePath(root, "$kind.jsonl")
            if (Py.str(report["review_kind"]) != kind ||
                Py.str(report["candidate_sha"]) != candidateSha ||
                Py.str(report["model"]) != "gpt-6-sol"
            ) {
                throw IllegalArgumentException("$kind review identity differs from final candidate")
            }
            val rawSession = Files.readString(sessionPath)
            val messages = rawSession.lines().filter { it.isNotEmpty() }.map { line ->
                StrictObjectJson.parse(line) as? JsonObject
                    ?: throw IllegalArgumentException("$kind raw session line is not an object")
            }
            fun payload(item: JsonObject): JsonObject = item["payload"] as? JsonObject ?: JsonObject(emptyMap())
            val turnModels = messages.filter { Py.str(it["type"]) == "turn_context" }
                .map { Py.str(payload(it)["model"]) }.toSet()
            val sessionIds = messages.filter { Py.str(it["type"]) == "session_meta" }
                .mapNotNull { Py.str(payload(it)["id"]) }.toSet()
            if (turnModels != setOf("gpt-6-sol") || sessionIds.size != 1) {
                throw IllegalArgumentException("$kind raw session does not prove one Sol review")
            }
            val finalReviews = mutableListOf<JsonObject>()
            val observedFindings = mutableListOf<JsonElement>()
            for (item in messages) {
                if (Py.str(item["type"]) != "response_item") continue
                val body = payload(item)
                (body["findings"] as? JsonArray)?.let { observedFindings.addAll(it) }
                if (Py.str(body["type"]) != "message" || Py.str(body["role"]) != "assistant") continue
                for (part in (body["content"] as? JsonArray) ?: JsonArray(emptyList())) {
                    val content = part as? JsonObject ?: continue
                    if (Py.str(content["type"]) != "output_text") continue
                    val value = try {
                        StrictObjectJson.parse(Py.str(content["text"]) ?: "")
                    } catch (error: Exception) {
                        continue
                    }
                    if (value is JsonObject && Py.str(value["kind"]) == "independent-review-result") {
                        finalReviews.add(value)
                    } else if (value is JsonObject && value["findings"] is JsonArray) {
                        observedFindings.addAll(value["findings"] as JsonArray)
                    }
                }
            }
            if (finalReviews.size != 1) {
                throw IllegalArgumentException(
                    "$kind raw final review output is absent or ambiguous",
                )
            }
            val rawReview = finalReviews[0]
            if (Py.str(rawReview["review_kind"]) != kind ||
                Py.str(rawReview["candidate_sha"]) != candidateSha ||
                rawReview["findings"] != report["findings"] ||
                Py.str(rawReview["verdict"]) != Py.str(report["verdict"]) ||
                Py.str(rawReview["assessment"]) != Py.str(report["assessment"]) ||
                rawReview["reviewed_paths"] != report["reviewed_paths"]
            ) {
                throw IllegalArgumentException(
                    "$kind raw review findings differ from report or exact final head",
                )
            }
            val requiredPaths = if (kind == "standards") {
                setOf("AGENTS.md", "docs/agents/writing.md")
            } else {
                setOf("docs/specs/complete-port.md", "docs/planning/acceptance-implementation.md")
            }
            val reviewedPaths = (rawReview["reviewed_paths"] as? JsonArray)
                ?.mapNotNull { Py.str(it) } ?: emptyList()
            val assessment = Py.str(rawReview["assessment"])
            if (assessment == null || assessment.trim().length < 40 ||
                rawReview["reviewed_paths"] !is JsonArray ||
                !reviewedPaths.toSet().containsAll(requiredPaths) ||
                reviewedPaths.size != reviewedPaths.toSet().size
            ) {
                throw IllegalArgumentException(
                    "$kind raw review has no substantive standards or spec assessment",
                )
            }
            for (path in reviewedPaths) {
                IndependentGates.filePathName(path)
                gitShow(repository, candidateSha, path)
            }
            val sessionId = sessionIds.single()
            if (Py.str(report["session_id"]) != sessionId || !sessions.add(sessionId)) {
                throw IllegalArgumentException(
                    "independent reviews repeat or misstate session identity",
                )
            }
            val findings = rawReview["findings"] as? JsonArray
                ?: throw IllegalArgumentException("$kind actionable findings are missing")
            val finalById = LinkedHashMap<String, JsonObject>()
            for (finding in findings) {
                val item = finding as? JsonObject ?: continue
                val id = Py.str(item["id"]) ?: continue
                finalById[id] = item
            }
            for (observed in observedFindings) {
                val item = observed as? JsonObject
                    ?: throw IllegalArgumentException(
                        "$kind raw actionable finding is absent from final review",
                    )
                val id = Py.str(item["id"]) ?: ""
                val final = finalById[id]
                    ?: throw IllegalArgumentException(
                        "$kind raw actionable finding is absent from final review",
                    )
                val severity = item["severity"]
                if (severity != null && severity !is JsonNull &&
                    severity != final["severity"]
                ) {
                    throw IllegalArgumentException(
                        "$kind raw actionable finding is absent from final review",
                    )
                }
            }
            val ids = findings.map { Py.str((it as? JsonObject)?.get("id")) }
            if (ids.any { it == null } || ids.size != ids.toSet().size) {
                throw IllegalArgumentException("$kind finding identities are invalid")
            }
            for (finding in findings) {
                val item = finding as? JsonObject
                    ?: throw IllegalArgumentException("$kind finding identities are invalid")
                val description = Py.str(item["description"])
                if (Py.str(item["severity"]) == null || description == null ||
                    description.isBlank()
                ) {
                    throw IllegalArgumentException("$kind raw finding lacks actionable details")
                }
                val resolution = item["resolution"] as? JsonObject
                val evidence = Py.str(resolution?.get("evidence"))
                if (resolution == null ||
                    Py.str(resolution["status"]) != "RESOLVED" ||
                    Py.str(resolution["candidate_sha"]) != candidateSha ||
                    evidence == null || evidence.isBlank()
                ) {
                    throw IllegalArgumentException("$kind actionable finding is unresolved")
                }
                IndependentGates.filePathName(evidence)
                val committed = gitShow(repository, candidateSha, evidence)
                if (Sha256.of(committed) != Py.str(resolution["evidence_sha256"])) {
                    throw IllegalArgumentException(
                        "$kind resolution evidence differs from exact final head",
                    )
                }
            }
            if (Py.str(rawReview["verdict"]) != "PASSED") {
                throw IllegalArgumentException("$kind raw reviewer verdict is not PASSED")
            }
            reports.add(report)
        }
        return "${reports.size} distinct Sol reviews verified against final head"
    }

    /**
     * `_java_full_ci`: the reviewed `full_ci.py` verifier at its pinned revision must accept the
     * archive, after this port re-binds every raw artifact to the independent staging audit.
     */
    fun javaFullCi(
        root: Path,
        receipt: JsonObject,
        gate: String,
        candidateSha: String,
        repository: Path,
        expectedArtifactHashes: Map<String, String>,
    ): String {
        if (Py.str(receipt["producer"]) != "reviewed-full-ci") {
            throw IllegalArgumentException(
                "$gate requires the reviewed full_ci raw archive contract",
            )
        }
        val relative = Py.str(receipt["full_ci_archive"])
        IndependentGates.filePathName(relative)
        val archive = root.resolve(relative!!)
        val manifestFile = IndependentGates.filePath(root, "$relative/lane-manifest.json")
        val manifestSha = Py.str(receipt["full_ci_manifest_sha256"])
        if (manifestSha == null || !Py.SHA64.matches(manifestSha) ||
            Sha256.of(Files.readAllBytes(manifestFile)) != manifestSha
        ) {
            throw IllegalArgumentException(
                "reviewed full_ci manifest differs from independently pinned receipt",
            )
        }
        val verifiedSource = gitShow(
            repository,
            GateConstants.REVIEWED_FULL_CI_REVISION,
            "tools/compatibility/full_ci.py",
        )
        if (Sha256.of(verifiedSource) != GateConstants.REVIEWED_FULL_CI_SHA256) {
            throw IllegalArgumentException("reviewed full_ci verifier source differs")
        }
        val evidence = IndependentGates.json(IndependentGates.filePath(root, "$relative/result.json"))
            as? JsonObject ?: throw IllegalArgumentException("reviewed full_ci result is missing")
        val archives = evidence["archives"] as? JsonObject
        if (Py.str(archives?.get("staged_jvm_jar")) != expectedArtifactHashes["dyn4k-core"]) {
            throw IllegalArgumentException(
                "reviewed Java corpus core JAR differs from independent staging audit",
            )
        }
        val corpus = evidence["corpus"] as? JsonObject
        val routePattern = Regex("(baseline|candidate|android)-javac(8|21)-java(8|21)")
        val routes = corpus?.filterKeys { routePattern.matches(it) } ?: emptyMap()
        if (routes.size != 12 ||
            routes.values.any { !Py.equalsInt((it as? JsonObject)?.get("cases"), 2385) }
        ) {
            throw IllegalArgumentException(
                "reviewed Java producer manifest omits 2,385 expanded identities on 12 routes",
            )
        }
        val resolved = receipt["resolved_artifacts"] as? JsonObject
        if (resolved == null || resolved.keys != setOf("dyn4k-core", "dyn4k") ||
            resolved.entries.any { (module, path) ->
                val file = IndependentGates.filePath(root, Py.str(path))
                Sha256.of(Files.readAllBytes(file)) != expectedArtifactHashes[module]
            }
        ) {
            throw IllegalArgumentException(
                "Java corpus resolved publications differ from independent staging audit",
            )
        }
        val sourceArchive = gitArchive(
            repository,
            GateConstants.REVIEWED_FULL_CI_REVISION,
            listOf(
                "tools/compatibility",
                "tools/baseline",
                "dyn4k-core/src/jvmConsumer/java",
            ),
        )
        val temporary = Files.createTempDirectory("dyn4k-reviewed-full-ci-")
        try {
            extractTar(sourceArchive, temporary)
            val command = listOf(
                pythonExecutable(),
                temporary.resolve("tools/compatibility/full_ci.py").toString(),
                "verify", "--candidate-sha", candidateSha,
                "--output", archive.toAbsolutePath().toString(),
                "--manifest-sha256", manifestSha,
            )
            val checked = runCommand(command, packageRoot(), 120)
            if (checked.exitCode != 0) {
                throw IllegalArgumentException(
                    "reviewed full_ci/strict raw verifier rejected archive: " +
                        checked.stdout.takeLast(1000) + checked.stderr.takeLast(300),
                )
            }
            val verified = StrictObjectJson.parse(checked.stdout) as? JsonObject
            if (Py.str(verified?.get("status")) != "PASSED" ||
                !Py.equalsInt(verified?.get("corpus_files"), 24)
            ) {
                throw IllegalArgumentException(
                    "reviewed full_ci/strict verifier did not pass full Java corpus",
                )
            }
        } finally {
            deleteTree(temporary)
        }
        return "2,385 unchanged Java cases across 12 compile/runtime routes and " +
            "216-type strict source compatibility verified by reviewed full_ci"
    }

    private fun unsupported(function: String, harness: String): Nothing =
        throw UnsupportedOperationException(
            "independent gate $function is not expressed in Kotlin yet: it drives $harness, " +
                "which has no Kotlin counterpart in this build",
        )

    /** `_migration_journeys` — needs the Python `journeys`/`validate_plain`/`validate_scene` drivers. */
    fun migrationJourneys(
        root: Path,
        candidateSha: String,
        expectedArtifactHashes: JsonElement?,
    ): Nothing = unsupported("_migration_journeys", "tools/migration's journeys and scene validators")

    /** `_numerical_entries` — needs the Python `compare`/`physical` replay engine. */
    fun numericalEntries(
        root: Path,
        receipt: JsonObject,
        candidateSha: String,
        expectedArtifactHashes: JsonElement?,
        repository: Path,
        physicalOnly: Boolean,
        prospectiveScope: JsonElement?,
    ): Nothing = unsupported("_numerical_entries", "tools/numerical's compare and physical engines")

    /** `_performance_resource` — needs the Python `verify_candidate_archive` verifier. */
    fun performanceResource(
        root: Path,
        candidateSha: String,
        expectedArtifactHashes: JsonElement?,
        scope: JsonElement?,
        repository: Path?,
        trustedKey: String?,
    ): Nothing = unsupported("_performance_resource", "tools/performance's archive verifiers")

    /** `_evaluate_signed_full_consumer` — needs `full_signed_routes`/`full_browser_consumer`. */
    fun signedFullConsumer(
        gate: String,
        root: Path,
        candidateSha: String,
        laneId: String,
        repository: Path,
        hashes: JsonElement?,
        runtime: JsonElement?,
        expectedDigest: String?,
        signedLane: JsonElement?,
        family: String,
    ): Nothing = unsupported(
        "_evaluate_signed_full_consumer",
        "tools/qualification/full_signed_routes and full_browser_consumer",
    )

    /**
     * `evaluate_gate`: one approved gate route over one raw archive.
     *
     * Every branch that can be decided in this JVM is; the four Python-harness bodies return
     * `NOT_RUN` with the explicit reason instead of a fabricated verdict.
     */
    @Suppress("LongParameterList")
    fun evaluateGate(
        gate: String,
        archive: Path?,
        candidateSha: String,
        laneId: String,
        lane: JsonObject,
        repository: Path,
        expectedArtifactHashes: Map<String, String>?,
        expectedRuntimeIdentity: String?,
        expectedArchiveDigest: String? = null,
        expectedAllTargetHashes: JsonElement? = null,
        manifest: JsonObject? = null,
        expectedProducerScopes: JsonElement? = null,
        expectedPerformanceKey: Path? = null,
        expectedSignedLane: JsonElement? = null,
    ): JsonObject {
        if (archive == null) {
            if (gate == "physical-correctness") {
                return result(
                    gate, "NOT_RUN", "no raw candidate physical archive supplied",
                    mapOf("profiles" to GatesNumerical.missingPhysicalProfiles()),
                )
            }
            if (gate == "numerical-parity") {
                return result(
                    gate, "NOT_RUN", "no raw candidate numerical archive supplied",
                    mapOf("subgates" to GatesNumerical.missingNumericalSubgates(repository)),
                )
            }
            return result(gate, "NOT_RUN", "no raw archive supplied")
        }
        val root = archive
        try {
            if (!Files.isDirectory(root) || Files.isSymbolicLink(root)) {
                throw IllegalArgumentException("raw archive directory is missing or symbolic")
            }
            if (gate == "staged-consumer" && manifest != null &&
                (manifest["lanes"] as? JsonObject)?.size == 112
            ) {
                // The signed-route families live in full_signed_routes, a Python module.
                if (expectedSignedLane != null) {
                    return result(
                        gate, "NOT_RUN",
                        "dedicated signed lane is not expressed in Kotlin yet: it verifies " +
                            "full_signed_routes/full_browser_consumer, which have no Kotlin counterpart",
                    )
                }
            }
            if (gate == "staged-consumer" && Files.isRegularFile(root.resolve("verification.json"))) {
                IndependentGates.archivePaths(root)
                val summary = IndependentGates.boundedBundle(
                    root, candidateSha, lane,
                    expectedArtifactHashes?.let { map ->
                        JsonObject(map.mapValues { JsonPrimitive(it.value) })
                    },
                    repository,
                )
                return result(
                    gate, "NOT_RUN",
                    "bounded staged consumer verified; full lane configuration and suite remain unexecuted",
                    mapOf("bounded_executed" to (summary["executed"] ?: JsonNull)),
                )
            }
            val receipt = IndependentGates.json(IndependentGates.filePath(root, "receipt.json")) as? JsonObject
                ?: throw IllegalArgumentException("raw archive receipt is not an object")
            if (Py.str(receipt["status"]) == "UNAVAILABLE") {
                val names = Files.list(root).use { stream -> stream.map { it.fileName.toString() }.toList() }
                if (names.toSet() != setOf("receipt.json")) {
                    throw IllegalArgumentException("unavailability receipt has unexpected raw files")
                }
                if (gate == "staged-consumer" && expectedSignedLane != null) {
                    val signed = expectedSignedLane as? JsonObject
                    if (signed?.get("expected_unavailability") != receipt ||
                        expectedArchiveDigest == null ||
                        !Py.SHA64.matches(expectedArchiveDigest) ||
                        ArchiveScan.digest(root) != expectedArchiveDigest
                    ) {
                        throw IllegalArgumentException("unavailability is not independently audited")
                    }
                }
                return IndependentGates.externalUnavailable(receipt, candidateSha, laneId, gate)
            }
            if (Py.str(receipt["status"]) == "PASSED") {
                val digest = expectedArchiveDigest
                if (digest == null || !Py.SHA64.matches(digest)) {
                    throw IllegalArgumentException("independent archive provenance digest is missing")
                }
                if (ArchiveScan.digest(root) != digest) {
                    throw IllegalArgumentException("independent archive provenance digest differs")
                }
            }
            if (gate == "staged-consumer" &&
                ("consumer_contract_sha256" in receipt || "browser_support_sha256" in receipt)
            ) {
                return result(
                    gate, "NOT_RUN",
                    "full Chromium consumer replay is not expressed in Kotlin yet: it verifies " +
                        "full_browser_consumer, which has no Kotlin counterpart",
                )
            }
            val archiveSha = IndependentGates.inventory(root, receipt)
            val laneHashes = expectedArtifactHashes ?: emptyMap()
            val gateHashes = IndependentGates.gateArtifactHashes(
                gate, lane, laneHashes, expectedAllTargetHashes,
            )
            val process = IndependentGates.binding(
                root, receipt, candidateSha, laneId, lane, repository, gateHashes,
                expectedRuntimeIdentity, gate, expectedProducerScopes,
            )
            val status = Py.str(receipt["status"])
            if (status !in setOf("PASSED", "FAILED", "NOT_RUN")) {
                throw IllegalArgumentException("reported gate status is invalid")
            }
            if (status == "NOT_RUN") {
                return result(
                    gate, "NOT_RUN", "producer records no execution",
                    mapOf("archive_sha256" to JsonPrimitive(archiveSha)),
                )
            }
            if (status == "FAILED") {
                if (Py.int(process["exit_code"]!!) == 0L) {
                    throw IllegalArgumentException(
                        "producer reports failure but raw process exited successfully",
                    )
                }
                IndependentGates.processProof(root, process, gate, laneId, receipt)
                return result(
                    gate, "FAILED", "raw command exited ${Py.int(process["exit_code"]!!)}",
                    mapOf("archive_sha256" to JsonPrimitive(archiveSha)),
                )
            }
            IndependentGates.processProof(root, process, gate, laneId, receipt)
            if (gate == "duplicate-provider") {
                val reason = IndependentGates.duplicateProvider(root, receipt, process)
                return result(
                    gate, "PASSED", reason,
                    mapOf("archive_sha256" to JsonPrimitive(archiveSha)),
                )
            }
            if (Py.int(process["exit_code"]!!) != 0L) {
                return result(
                    gate, "FAILED", "raw command exited ${Py.int(process["exit_code"]!!)}",
                    mapOf("archive_sha256" to JsonPrimitive(archiveSha)),
                )
            }
            if (gate == "staged-artifacts" || gate == "publication-contract") {
                if (gate == "publication-contract" && expectedAllTargetHashes == null) {
                    throw IllegalArgumentException(
                        "independently audited 21-target binary hash map is missing",
                    )
                }
                if (gate == "publication-contract") {
                    IndependentGates.validatedAllTargetHashes(expectedAllTargetHashes)
                }
                val reason = IndependentGates.stagedPublication(
                    root, candidateSha, lane, gateHashes, repository,
                    if (gate == "publication-contract") expectedAllTargetHashes else null,
                )
                return result(
                    gate, "PASSED", reason,
                    mapOf("archive_sha256" to JsonPrimitive(archiveSha)),
                )
            }
            if (gate == "staged-consumer") {
                val suite = manifest
                    ?: throw IllegalArgumentException("staged consumer requires the suite manifest")
                val (reason, complete) = IndependentGates.stagedConsumer(
                    root, receipt, candidateSha, laneId, lane, laneHashes, repository,
                    process, suite,
                )
                val details = LinkedHashMap<String, JsonElement>()
                details["archive_sha256"] = JsonPrimitive(archiveSha)
                details["complete_selected_suite"] = JsonPrimitive(complete)
                details["selected_cases"] = if (complete) {
                    JsonPrimitive(
                        IndependentGates.consumerContract(suite, laneId)["cases"]!!.let {
                            (it as JsonArray).size
                        },
                    )
                } else {
                    JsonNull
                }
                return result(gate, if (complete) "PASSED" else "NOT_RUN", reason, details)
            }
            if (gate == "unchanged-java-corpus" || gate == "java-source-compatibility") {
                val scope = (expectedProducerScopes as? JsonObject)?.get(gate) as? JsonObject
                val hashes = (scope?.get("artifact_hashes") as? JsonObject)
                    ?.mapValues { (_, value) -> Py.str(value)!! }
                    ?: emptyMap()
                val reason = javaFullCi(root, receipt, gate, candidateSha, repository, hashes)
                return result(
                    gate, "PASSED", reason,
                    mapOf("archive_sha256" to JsonPrimitive(archiveSha)),
                )
            }
            if (gate == "independent-review") {
                val reason = reviewVerification(root, candidateSha, repository)
                return result(
                    gate, "PASSED", reason,
                    mapOf("archive_sha256" to JsonPrimitive(archiveSha)),
                )
            }
            if (gate == "migration-journeys") {
                migrationJourneys(root, candidateSha, expectedArtifactHashes?.let { map ->
                    JsonObject(map.mapValues { JsonPrimitive(it.value) })
                })
            }
            if (gate == "numerical-parity" || gate == "physical-correctness") {
                numericalEntries(
                    root,
                    receipt,
                    candidateSha,
                    expectedArtifactHashes?.let { map ->
                        JsonObject(map.mapValues { JsonPrimitive(it.value) })
                    },
                    repository,
                    physicalOnly = gate == "physical-correctness",
                    prospectiveScope = (expectedProducerScopes as? JsonObject)
                        ?.get("numerical-parity"),
                )
            }
            if (gate == "performance-resource") {
                val scope = (expectedProducerScopes as? JsonObject)?.get(gate)
                performanceResource(
                    root,
                    candidateSha,
                    expectedArtifactHashes?.let { map ->
                        JsonObject(map.mapValues { JsonPrimitive(it.value) })
                    },
                    scope,
                    repository,
                    expectedPerformanceKey?.toString(),
                )
            }
            throw IllegalArgumentException("unknown approved gate route: $gate")
        } catch (error: IncompleteEvidence) {
            return result(gate, "NOT_RUN", error.message ?: "")
        } catch (error: UnsupportedOperationException) {
            return result(gate, "NOT_RUN", error.message ?: "")
        } catch (error: IOException) {
            return failure(gate, error.message, repository)
        } catch (error: IllegalArgumentException) {
            return failure(gate, error.message, repository)
        } catch (error: NoSuchElementException) {
            return failure(gate, error.message, repository)
        } catch (error: ClassCastException) {
            return failure(gate, error.message, repository)
        } catch (error: ObservationError) {
            return failure(gate, error.message, repository)
        }
    }

    private fun failure(gate: String, message: String?, repository: Path): JsonObject {
        if (gate == "numerical-parity") {
            return result(
                gate, "FAILED", message ?: "",
                mapOf("subgates" to GatesNumerical.missingNumericalSubgates(repository)),
            )
        }
        return result(gate, "FAILED", message ?: "")
    }

    /**
     * `evaluate`: every approved route of one lane, then the global gates, then the verdict.
     */
    @Suppress("LongParameterList")
    fun evaluate(
        manifest: JsonObject,
        candidateSha: String,
        laneId: String,
        archives: Map<String, Path>,
        repository: Path,
        expectedArtifactHashes: Map<String, String>? = null,
        expectedRuntimeIdentity: String? = null,
        expectedArchiveDigests: JsonObject? = null,
        expectedAllTargetHashes: JsonElement? = null,
        expectedProducerScopes: JsonElement? = null,
        expectedPerformanceKey: Path? = null,
        expectedSignedLane: JsonElement? = null,
    ): JsonObject {
        if (IndependentGates.digest(manifest) != IndependentGates.APPROVED_MANIFEST_SHA256) {
            throw IllegalArgumentException(
                "manifest differs from independently approved complete suite",
            )
        }
        if (!Py.SHA40.matches(candidateSha)) {
            throw IllegalArgumentException("candidate SHA must be an exact commit")
        }
        val actual = gitOutput(repository, "rev-parse", "--verify", "$candidateSha^{commit}")
        if (actual != candidateSha) {
            throw IllegalArgumentException(
                "candidate SHA does not identify the requested commit",
            )
        }
        val lanes = manifest["lanes"] as? JsonObject
            ?: throw IllegalArgumentException("lane is absent from approved manifest")
        val lane = lanes[laneId] as? JsonObject
            ?: throw IllegalArgumentException("lane is absent from approved manifest")
        val required = (lane["required_gates"] as? JsonArray)?.mapNotNull { Py.str(it) }
            ?: throw IllegalArgumentException("approved gate routes are incomplete or duplicated")
        val globals = (manifest["global_gates"] as? JsonArray)?.mapNotNull { Py.str(it) }
            ?: emptyList()
        if (!IndependentGates.LANE_GATES.containsAll(required) ||
            required.size != required.toSet().size ||
            globals.toSet() != IndependentGates.GLOBAL_GATES
        ) {
            throw IllegalArgumentException("approved gate routes are incomplete or duplicated")
        }
        val names = required + globals
        if (archives.keys.any { it !in names }) {
            throw IllegalArgumentException("archive map has an unknown or inapplicable gate")
        }
        val digests = expectedArchiveDigests ?: JsonObject(emptyMap())
        if (digests.keys.any { it !in names }) {
            throw IllegalArgumentException("independent archive digest map has an unknown gate")
        }
        val scopes = expectedProducerScopes ?: JsonObject(emptyMap())
        val scopeKeys = (scopes as? JsonObject)?.keys ?: emptySet()
        if (scopeKeys.any { it !in names ||
                it !in IndependentGates.PRODUCER_SCOPED_GATES + setOf("numerical-parity")
            }
        ) {
            throw IllegalArgumentException(
                "independent producing scope map has an unknown gate",
            )
        }
        val gates = LinkedHashMap<String, JsonElement>()
        for (gate in names) {
            @Suppress("UNCHECKED_CAST")
            gates[gate] = evaluateGate(
                gate,
                archives[gate],
                candidateSha,
                laneId,
                lane,
                repository,
                expectedArtifactHashes,
                expectedRuntimeIdentity,
                Py.str(digests[gate]),
                expectedAllTargetHashes,
                manifest,
                scopes,
                expectedPerformanceKey,
                expectedSignedLane,
            )
        }
        val statuses = gates.values.map { Py.str((it as JsonObject)["status"]) }.toSet()
        val status = listOf("FAILED", "UNAVAILABLE", "NOT_RUN").firstOrNull { it in statuses }
            ?: "PASSED"
        val result = LinkedHashMap<String, JsonElement>()
        result["schema"] = JsonPrimitive(1)
        result["kind"] = JsonPrimitive("independent-gate-verification")
        result["candidate_sha"] = JsonPrimitive(candidateSha)
        result["lane"] = JsonPrimitive(laneId)
        result["manifest_sha256"] = JsonPrimitive(IndependentGates.digest(manifest))
        result["approved_numerical_blobs"] = JsonObject(
            GatesNumerical.APPROVED_POLICY.mapValues { JsonPrimitive(it.value) },
        )
        result["approved_nominal_blobs"] = JsonObject(
            GateConstants.APPROVED_NOMINAL.mapValues { JsonPrimitive(it.value) },
        )
        result["approved_migration_blobs"] = JsonObject(
            GateConstants.APPROVED_MIGRATION.mapValues { JsonPrimitive(it.value) },
        )
        result["reviewed_full_ci_revision"] = JsonPrimitive(GateConstants.REVIEWED_FULL_CI_REVISION)
        result["expected_artifact_hashes"] = expectedArtifactHashes?.let { map ->
            JsonObject(map.mapValues { JsonPrimitive(it.value) })
        } ?: JsonNull
        result["expected_all_target_hashes"] = expectedAllTargetHashes ?: JsonNull
        result["expected_producer_scopes"] = scopes
        result["expected_archive_digests"] = digests
        result["expected_runtime_identity"] = expectedRuntimeIdentity?.let { JsonPrimitive(it) }
            ?: JsonNull
        result["expected_performance_key_sha256"] = expectedPerformanceKey
            ?.takeIf { Files.isRegularFile(it) }
            ?.let { JsonPrimitive(Sha256.of(Files.readAllBytes(it))) }
            ?: JsonNull
        result["gates"] = JsonObject(gates)
        result["status"] = JsonPrimitive(status)
        result["result_sha256"] = JsonPrimitive(IndependentGates.digest(JsonObject(result)))
        return JsonObject(result)
    }

    /**
     * `evaluate_assembly`: all 112 lane inputs, one shared global-gate identity, and the complete
     * selected-suite adapter for every passing lane.
     */
    fun evaluateAssembly(
        manifest: JsonObject,
        candidateSha: String,
        laneInputs: JsonObject,
        repository: Path,
        expectedAllTargetHashes: JsonElement? = null,
        expectedPerformanceKey: Path? = null,
    ): JsonObject {
        if (IndependentGates.digest(manifest) != IndependentGates.APPROVED_MANIFEST_SHA256) {
            throw IllegalArgumentException(
                "assembly manifest differs from approved complete suite",
            )
        }
        val lanes = manifest["lanes"] as? JsonObject
            ?: throw IllegalArgumentException("approved manifest has no lanes")
        if (laneInputs.keys != lanes.keys) {
            throw IllegalArgumentException("assembly requires all ${lanes.size} approved lane inputs")
        }
        if (expectedAllTargetHashes != null) {
            IndependentGates.validatedAllTargetHashes(expectedAllTargetHashes)
        }
        val results = LinkedHashMap<String, JsonElement>()
        val selectedCases = LinkedHashMap<String, JsonElement>()
        val adapter = LinkedHashMap<String, JsonElement>()
        val globalsSeen = LinkedHashMap<String, Pair<String?, String?>>()
        val allowed = setOf(
            "archives", "expected_artifact_hashes", "expected_runtime_identity",
            "expected_archive_digests", "expected_producer_scopes",
        )
        for (laneId in lanes.keys) {
            val supplied = laneInputs[laneId] as? JsonObject
                ?: throw IllegalArgumentException("assembly lane input differs: $laneId")
            if (!allowed.containsAll(supplied.keys)) {
                throw IllegalArgumentException("assembly lane input differs: $laneId")
            }
            val hashesElement = supplied["expected_artifact_hashes"]
            val hashes: Map<String, String>? = if (hashesElement != null) {
                val map = hashesElement as? JsonObject
                    ?: throw IllegalArgumentException("assembly artifact hashes are invalid: $laneId")
                if (map.keys != setOf("dyn4k-core", "dyn4k") ||
                    map.values.any { !Py.SHA64.matches(Py.str(it) ?: "") }
                ) {
                    throw IllegalArgumentException("assembly artifact hashes are invalid: $laneId")
                }
                map.mapValues { (_, value) -> Py.str(value)!! }
            } else {
                null
            }
            val contract = IndependentGates.consumerContract(manifest, laneId)
            val cases = contract["cases"] as? JsonArray ?: JsonArray(emptyList())
            selectedCases[laneId] = JsonPrimitive(cases.size)
            val archives = (supplied["archives"] as? JsonObject)?.mapValues { (_, value) ->
                Path.of(Py.str(value)!!)
            } ?: emptyMap()
            val result = evaluate(
                manifest, candidateSha, laneId, archives, repository,
                hashes,
                Py.str(supplied["expected_runtime_identity"]),
                supplied["expected_archive_digests"] as? JsonObject,
                expectedAllTargetHashes,
                supplied["expected_producer_scopes"],
                expectedPerformanceKey,
            )
            val withoutDigest = JsonObject(result.filterKeys { it != "result_sha256" })
            if (Py.str(result["result_sha256"]) != IndependentGates.digest(withoutDigest)) {
                throw IllegalArgumentException("assembly lane result digest differs")
            }
            results[laneId] = result
            for (gate in (manifest["global_gates"] as JsonArray).mapNotNull { Py.str(it) }) {
                val gateResult = (result["gates"] as JsonObject).getValue(gate) as JsonObject
                val identity = Py.str(gateResult["status"]) to Py.str(gateResult["archive_sha256"])
                val seen = globalsSeen[gate]
                if (seen != null && seen != identity) {
                    throw IllegalArgumentException(
                        "assembly global gate differs across lanes: $gate",
                    )
                }
                globalsSeen[gate] = identity
            }
            if (Py.str(result["status"]) == "PASSED") {
                val gateObjects = result["gates"] as JsonObject
                if ((gateObjects["staged-consumer"] as JsonObject)["complete_selected_suite"] !=
                    JsonPrimitive(true)
                ) {
                    throw IllegalArgumentException(
                        "assembly lacks complete selected-suite case ingestion",
                    )
                }
                val digestMap = result["expected_archive_digests"] as JsonObject
                val gateResults = LinkedHashMap<String, JsonElement>()
                for ((gate, element) in gateObjects) {
                    val gateResult = element as JsonObject
                    val receiptHash = Py.str(digestMap[gate])
                    if (Py.str(gateResult["status"]) != "PASSED" ||
                        receiptHash == null || !Py.SHA64.matches(receiptHash)
                    ) {
                        throw IllegalArgumentException("assembly gate receipt is unbound: $gate")
                    }
                    gateResults[gate] = buildJsonObject {
                        put("status", JsonPrimitive("PASSED"))
                        put("receipt_sha256", JsonPrimitive(receiptHash))
                    }
                }
                adapter[laneId] = buildJsonObject {
                    put(
                        "case_results",
                        JsonArray(
                            cases.map { element ->
                                buildJsonObject {
                                    put("id", (element as JsonObject).getValue("id"))
                                    put("status", JsonPrimitive("PASSED"))
                                }
                            },
                        ),
                    )
                    put("expected", JsonPrimitive(cases.size))
                    put("executed", JsonPrimitive(cases.size))
                    put("failures", JsonPrimitive(0))
                    put("skipped", JsonPrimitive(0))
                    put("consumer", JsonPrimitive("PASSED"))
                    put("gate_results", JsonObject(gateResults))
                    put("independent_result_sha256", result.getValue("result_sha256"))
                }
            }
        }
        val statuses = results.values.map { Py.str((it as JsonObject)["status"]) }.toSet()
        val status = listOf("FAILED", "UNAVAILABLE", "NOT_RUN").firstOrNull { it in statuses }
            ?: "PASSED"
        val assembled = LinkedHashMap<String, JsonElement>()
        assembled["schema"] = JsonPrimitive(1)
        assembled["kind"] = JsonPrimitive("independent-gate-assembly")
        assembled["candidate_sha"] = JsonPrimitive(candidateSha)
        assembled["manifest_sha256"] = JsonPrimitive(IndependentGates.digest(manifest))
        assembled["required_lanes"] = JsonPrimitive(results.size)
        assembled["selected_cases"] = JsonObject(selectedCases)
        assembled["lane_results"] = JsonObject(results)
        assembled["qualify_adapter"] = JsonObject(adapter)
        assembled["status"] = JsonPrimitive(status)
        assembled["result_sha256"] = JsonPrimitive(IndependentGates.digest(JsonObject(assembled)))
        return JsonObject(assembled)
    }

    /** `independent_gates.main`: `--assembly`, or one lane with its `GATE=PATH` archives. */
    fun main(arguments: Array<String>): Int {
        var candidateSha: String? = null
        var lane: String? = null
        var assembly: Path? = null
        var repository: Path? = null
        var manifestPath: Path? = null
        val archiveArguments = mutableListOf<String>()
        var expectedArtifacts: Path? = null
        var expectedAllTarget: Path? = null
        var expectedProducerScopes: Path? = null
        var expectedArchiveDigests: Path? = null
        var expectedRuntimeIdentity: String? = null
        var expectedPerformanceKey: Path? = null
        var index = 0
        while (index < arguments.size) {
            when (val argument = arguments[index]) {
                "--candidate-sha" -> candidateSha = next(arguments, ++index)
                    ?: return usage("argument --candidate-sha: expected one argument")
                "--lane" -> lane = next(arguments, ++index)
                    ?: return usage("argument --lane: expected one argument")
                "--assembly" -> assembly = next(arguments, ++index)?.let { Path.of(it) }
                    ?: return usage("argument --assembly: expected one argument")
                "--repository" -> repository = next(arguments, ++index)?.let { Path.of(it) }
                    ?: return usage("argument --repository: expected one argument")
                "--manifest" -> manifestPath = next(arguments, ++index)?.let { Path.of(it) }
                    ?: return usage("argument --manifest: expected one argument")
                "--archive" -> archiveArguments.add(
                    next(arguments, ++index)
                        ?: return usage("argument --archive: expected one argument"),
                )
                "--expected-artifacts" -> expectedArtifacts =
                    next(arguments, ++index)?.let { Path.of(it) }
                        ?: return usage("argument --expected-artifacts: expected one argument")
                "--expected-all-target-artifacts" -> expectedAllTarget =
                    next(arguments, ++index)?.let { Path.of(it) }
                        ?: return usage(
                            "argument --expected-all-target-artifacts: expected one argument",
                        )
                "--expected-producer-scopes" -> expectedProducerScopes =
                    next(arguments, ++index)?.let { Path.of(it) }
                        ?: return usage("argument --expected-producer-scopes: expected one argument")
                "--expected-archive-digests" -> expectedArchiveDigests =
                    next(arguments, ++index)?.let { Path.of(it) }
                        ?: return usage(
                            "argument --expected-archive-digests: expected one argument",
                        )
                "--expected-runtime-identity" -> expectedRuntimeIdentity =
                    next(arguments, ++index)
                        ?: return usage(
                            "argument --expected-runtime-identity: expected one argument",
                        )
                "--expected-performance-key" -> expectedPerformanceKey =
                    next(arguments, ++index)?.let { Path.of(it) }
                        ?: return usage("argument --expected-performance-key: expected one argument")
                else -> return usage("unrecognized arguments: $argument")
            }
            index++
        }
        val sha = candidateSha ?: return usage("the following arguments are required: --candidate-sha")
        val root = repository ?: packageRoot()
        val manifest = if (manifestPath != null) {
            StrictJson.load(Files.readString(manifestPath)) as? JsonObject
                ?: return usage("manifest is not an object")
        } else {
            IndependentGates.loadApprovedManifest(root)
        }
        val archives = LinkedHashMap<String, Path>()
        for (value in archiveArguments) {
            val separator = value.indexOf('=')
            val gate = if (separator < 0) value else value.substring(0, separator)
            val path = if (separator < 0) "" else value.substring(separator + 1)
            if (separator < 0 || path.isEmpty() || gate in archives) {
                return usage("each --archive must be a unique GATE=PATH")
            }
            archives[gate] = Path.of(path)
        }
        val hashes = readHashes(expectedArtifacts)
        val allHashes = expectedAllTarget?.let { StrictJson.load(Files.readString(it)) }
        val producerScopes = expectedProducerScopes?.let { StrictJson.load(Files.readString(it)) }
        val archiveDigests = expectedArchiveDigests?.let {
            StrictJson.load(Files.readString(it)) as? JsonObject
        }
        val result = try {
            if (assembly != null) {
                if (lane != null || archives.isNotEmpty()) {
                    return usage("--assembly cannot be combined with --lane or --archive")
                }
                evaluateAssembly(
                    manifest, sha, StrictJson.load(Files.readString(assembly)) as JsonObject,
                    root, allHashes, expectedPerformanceKey,
                )
            } else {
                if (lane == null) return usage("--lane is required without --assembly")
                evaluate(
                    manifest, sha, lane, archives, root, hashes,
                    expectedRuntimeIdentity, archiveDigests, allHashes, producerScopes,
                    expectedPerformanceKey,
                )
            }
        } catch (error: Exception) {
            System.err.println(error.message ?: error.toString())
            return 2
        }
        println(PyJson.renderSorted(result))
        return if (Py.str(result["status"]) == "PASSED") 0 else 1
    }

    private fun readHashes(path: Path?): Map<String, String>? {
        if (path == null) return null
        val value = StrictJson.load(Files.readString(path)) as? JsonObject ?: return null
        return value.mapValues { (_, element) -> Py.str(element)!! }
    }

    private fun next(arguments: Array<String>, index: Int): String? =
        if (index < arguments.size) arguments[index] else null

    private fun usage(message: String): Int {
        System.err.println("usage error: $message")
        return 2
    }

    /** `Path(__file__).resolve().parents[2]`: the repository root of the ported harness. */
    fun packageRoot(): Path {
        var current: Path? = Path.of("").toAbsolutePath()
        while (current != null) {
            if (Files.isDirectory(current.resolve("tools/qualification"))) return current
            current = current.parent
        }
        return Path.of("").toAbsolutePath()
    }

    private fun pythonExecutable(): String = System.getenv("PYTHON") ?: "python3"

    private class CommandResult(
        val exitCode: Int,
        val stdout: String,
        val stderr: String,
    )

    private fun runCommand(command: List<String>, cwd: Path, timeoutSeconds: Long): CommandResult {
        val process = ProcessBuilder(command).directory(cwd.toFile()).start()
        val stdout = process.inputStream.readBytes()
        val stderr = process.errorStream.readBytes()
        if (!process.waitFor(timeoutSeconds, java.util.concurrent.TimeUnit.SECONDS)) {
            process.destroyForcibly()
            throw IncompleteEvidence("verifier command timed out")
        }
        return CommandResult(
            process.exitValue(),
            String(stdout, StandardCharsets.UTF_8),
            String(stderr, StandardCharsets.UTF_8),
        )
    }

    private fun gitShow(repository: Path, revision: String, path: String): ByteArray =
        gitBytes(repository, "show", "$revision:$path")

    private fun gitArchive(repository: Path, revision: String, paths: List<String>): ByteArray =
        gitBytes(
            repository,
            listOf("-c", "core.autocrlf=false") + listOf("archive", revision) + paths,
        )

    private fun gitOutput(repository: Path, vararg arguments: String): String =
        String(gitBytes(repository, *arguments), StandardCharsets.UTF_8).trim()

    private fun gitBytes(repository: Path, vararg arguments: String): ByteArray =
        gitBytes(repository, arguments.toList())

    private fun gitBytes(repository: Path, arguments: List<String>): ByteArray {
        val process = ProcessBuilder(
            listOf("git", "--no-replace-objects", "-C", repository.toString()) + arguments,
        ).start()
        val stdout = process.inputStream.readBytes()
        val stderr = process.errorStream.readBytes()
        if (process.waitFor() != 0) {
            throw IncompleteEvidence(
                "git ${arguments.joinToString(" ")} failed: " +
                    String(stderr, StandardCharsets.UTF_8).trim(),
            )
        }
        return stdout
    }

    /** `tarfile.extractall(filter="data")`: no escape, no link, no device. */
    private fun extractTar(archive: ByteArray, destination: Path) {
        TarArchiveInputStream(archive.inputStream()).use { input ->
            while (true) {
                val entry = input.nextEntry ?: break
                val target = destination.resolve(entry.name).normalize()
                if (!target.startsWith(destination)) {
                    throw IncompleteEvidence("pinned source archive escapes its extraction root")
                }
                if (entry.isDirectory) {
                    Files.createDirectories(target)
                    continue
                }
                if (!entry.isFile) {
                    throw IncompleteEvidence("pinned source archive holds a non-regular member")
                }
                target.parent?.let { Files.createDirectories(it) }
                Files.newOutputStream(target).use { output -> input.copyTo(output) }
            }
        }
    }

    private fun deleteTree(root: Path) {
        if (!Files.exists(root)) return
        Files.walk(root).use { walk ->
            walk.sorted(Comparator.reverseOrder()).forEach { Files.deleteIfExists(it) }
        }
    }
}
