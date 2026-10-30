package io.github.rubixhacker.harness.qualification

import io.github.rubixhacker.harness.contract.Qualification
import io.github.rubixhacker.harness.contract.StrictJson
import java.nio.file.Files
import java.nio.file.Path
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

/**
 * `qualify.main`: the qualification command line.
 *
 * Ported actions: `matrix`, `check-providers`, `probe`, `audit-staging`, `execute`.
 * `record` fails closed because `LaneEvaluation.evaluate` returns a status verdict, not the
 * reference's full lane object (`runtime_identity`, `suite_id`, `case_results`, …), so a report it
 * wrote would not be the reference's bytes.
 */
object QualificationCli {
    @JvmStatic
    fun main(arguments: Array<String>) {
        System.exit(run(arguments))
    }

    fun run(arguments: Array<String>, repository: Path? = null): Int {
        var action: String? = null
        var candidateSha: String? = null
        var output: Path? = null
        var manifest: Path? = null
        var graph: Path? = null
        val reports = mutableListOf<String>()
        val groups = mutableListOf<String>()
        var stageReceipt: Path? = null
        var stageConsole: Path? = null
        var repositoryOption: Path? = null
        val targets = mutableListOf<String>()
        val command = mutableListOf<String>()
        var plan: Path? = null
        var evidencePath: Path? = null
        var auditPath: Path? = null
        var candidateManifestPath: Path? = null
        var availabilityPath: Path? = null
        var independentPerformanceKey: Path? = null
        val hostedProbes = mutableListOf<Path>()
        val rawBundles = mutableListOf<Path>()
        val fullHostedBundles = mutableListOf<Path>()
        val independentOptions = mutableListOf<Any>()
        var index = 0
        while (index < arguments.size) {
            when (val argument = arguments[index]) {
                "--candidate-sha" -> candidateSha = arguments[++index]
                "--output" -> output = Path.of(arguments[++index])
                "--manifest" -> manifest = Path.of(arguments[++index])
                "--report" -> reports.add(arguments[++index])
                "--group" -> groups.add(arguments[++index])
                "--stage-receipt" -> stageReceipt = Path.of(arguments[++index])
                "--stage-console" -> stageConsole = Path.of(arguments[++index])
                "--repository" -> repositoryOption = Path.of(arguments[++index])
                "--target" -> targets.add(arguments[++index])
                "--plan" -> plan = Path.of(arguments[++index])
                "--evidence" -> evidencePath = Path.of(arguments[++index])
                "--audit" -> auditPath = Path.of(arguments[++index])
                "--candidate-manifest" -> candidateManifestPath = Path.of(arguments[++index])
                "--availability" -> availabilityPath = Path.of(arguments[++index])
                "--hosted-probe" -> hostedProbes.add(Path.of(arguments[++index]))
                "--raw-bundle" -> rawBundles.add(Path.of(arguments[++index]))
                "--full-hosted-bundle" -> fullHostedBundles.add(Path.of(arguments[++index]))
                "--independent-archives" -> independentOptions.add(Path.of(arguments[++index]))
                "--independent-audit" -> independentOptions.add(Path.of(arguments[++index]))
                "--independent-audit-signature" -> independentOptions.add(Path.of(arguments[++index]))
                "--trusted-audit-public-key" -> independentOptions.add(Path.of(arguments[++index]))
                "--trusted-audit-key-sha256" -> independentOptions.add(arguments[++index])
                "--independent-performance-key" -> independentPerformanceKey = Path.of(arguments[++index])
                "--" -> {
                    for (rest in (index + 1) until arguments.size) command.add(arguments[rest])
                    index = arguments.size
                }
                else -> if (argument.startsWith("--")) {
                    return usage("unexpected argument: $argument")
                } else if (action == null) {
                    action = argument
                } else {
                    command.add(argument)
                }
            }
            index++
        }
        if (action == null) return usage("the action must be one of matrix, check-providers, record, execute, audit-staging, probe")
        if (action !in setOf("matrix", "check-providers", "record", "execute", "audit-staging", "probe")) {
            return usage("argument action: invalid choice: '$action'")
        }
        if (action == "matrix") {
            println(PyJson.render(Qualification.expand().let { cases -> lanesJson(cases) }))
            return 0
        }
        if (action == "check-providers") {
            // `check-providers` takes one positional graph path, as the reference parser does.
            val graphPath = graph ?: command.firstOrNull()?.let { Path.of(it) }
            val text = if (graphPath != null) Fs.readText(graphPath) else ""
            return try {
                Qualification.checkProviders(text)
                println("one org.dyn4j provider")
                0
            } catch (error: IllegalArgumentException) {
                System.err.println(error.message)
                1
            }
        }
        val root = repositoryOption ?: repository ?: repositoryRoot()
        val sha = candidateSha
        if (sha == null) return usage("--candidate-sha is required")
        try {
            io.github.rubixhacker.harness.host.CleanCheckout.require(root.toFile(), sha)
        } catch (error: Exception) {
            return usage(error.message ?: error.toString())
        }
        if (action == "probe") {
            if (!Py.SHA40.matches(sha)) return usage("candidate SHA must be a full commit hash")
            if (output == null || manifest == null) {
                return usage("--manifest and --output are required")
            }
            if (command.isEmpty()) return usage("probe needs a command")
            val frozenPath = root.resolve("tools/qualification/foundation-probes.json")
            if (manifest.toAbsolutePath().normalize() != frozenPath.toAbsolutePath().normalize()) {
                return usage("probe manifest must be the tracked frozen foundation manifest")
            }
            val frozen = StrictJson.load(Fs.readText(frozenPath)) as JsonObject
            val declared = (frozen["groups"] as JsonArray).mapNotNull { it as? JsonObject }
            val selected = declared.filter { Py.str(it["id"]) in groups }
            if (selected.size != groups.size || groups.toSet().size != groups.size) {
                return usage("unknown or duplicate frozen probe group")
            }
            val scoped = JsonObject(frozen + ("groups" to JsonArray(selected)))
            val report = ProbeRunner.run(command, reports, sha, output, scoped)
            print(report.stdout)
            System.err.print(report.stderr)
            println(PyJson.renderDefault(report.report))
            return if (Py.str(report.report["status"]) == "PROBE_PASSED") 0 else 1
        }
        if (action == "audit-staging") {
            if (output == null || stageReceipt == null || stageConsole == null || targets.isEmpty()) {
                return usage("--target, --stage-receipt, --stage-console and --output are required")
            }
            val result = StagingAudit.audit(
                repositoryOption ?: root,
                sha,
                targets,
                root.resolve("LICENSE.md"),
                stageReceipt,
                stageConsole,
            )
            Fs.writeText(output, PyJson.render(result) + "\n")
            println(PyJson.renderDefault(result))
            return if (Py.str(result["status"]) == "PASSED") 0 else 1
        }
        if (action == "execute") {
            if (plan == null || output == null) return usage("--plan and --output are required")
            val planValue = StrictJson.load(Fs.readText(plan)) as JsonObject
            val valid = Qualification.expand().map { it.id }.toSet()
            val unknown = planValue.keys - valid
            if (unknown.isNotEmpty()) {
                return usage("unknown lane: " + unknown.sortedWith(CanonicalText::compare).joinToString(", "))
            }
            val evidence = Execution.executePlan(planValue, sha, output)
            return if (ProbeManifest.executionSucceeded(evidence)) 0 else 1
        }
        if (action == "record") {
            return record(
                root,
                sha,
                output ?: return usage("--output is required"),
                evidencePath,
                auditPath,
                candidateManifestPath,
                availabilityPath,
                hostedProbes,
                rawBundles,
                fullHostedBundles,
                independentOptions,
                independentPerformanceKey,
            )
        }
        return usage("unsupported action: $action")
    }

    /**
     * `qualify.main` action `record`: evaluate every lane and write the runtime matrix.
     *
     * The `--independent-*` branch needs `independent_adapter.verify_lanes`, which is not ported;
     * asking for it refuses explicitly rather than recording an unbounded report.
     */
    private fun record(
        repository: Path,
        candidateSha: String,
        output: Path,
        evidencePath: Path?,
        auditPath: Path?,
        candidateManifestPath: Path?,
        availabilityPath: Path?,
        hostedProbes: List<Path>,
        rawBundles: List<Path>,
        fullHostedBundles: List<Path>,
        independentOptions: List<Any>,
        independentPerformanceKey: Path?,
    ): Int {
        val evidence = LinkedHashMap<String, JsonElement>()
        evidencePath?.let {
            (StrictJson.load(Fs.readText(it)) as? JsonObject)?.forEach { (key, value) -> evidence[key] = value }
        }
        val auditData = auditPath?.let { StrictJson.load(Fs.readText(it)) as? JsonObject }
        if (auditData != null && Py.str(auditData["candidate_sha"]) != candidateSha) {
            return usage("audit candidate SHA differs from report")
        }
        if (auditData != null) {
            try {
                StagingAudit.verifyAuditAgainstStaging(auditData, repository)
            } catch (error: IllegalArgumentException) {
                return usage(error.message ?: error.toString())
            }
        }
        val candidateManifest = candidateManifestPath?.let {
            StrictJson.load(Fs.readText(it)) as? JsonObject
        }
        val fullManifestPath = repository.resolve("tools/qualification/full-suite-manifest.json")
        val tracked = try {
            hostedGitStatus(
                repository,
                listOf(
                    "ls-files", "--error-unmatch", "--",
                    repository.relativize(fullManifestPath).toString(),
                ),
            ) == 0
        } catch (error: Exception) {
            false
        }
        val suiteManifest = if (tracked && Files.isRegularFile(fullManifestPath)) {
            StrictJson.load(Fs.readText(fullManifestPath))
        } else {
            null
        }
        if (suiteManifest != null) {
            try {
                SuiteBindings.validate(suiteManifest, repository)
            } catch (error: Exception) {
                return usage(error.message ?: error.toString())
            }
        }
        val cases = Qualification.expand()
        val availability = availabilityPath?.let {
            StrictJson.load(Fs.readText(it)) as? JsonObject
        } ?: JsonObject(emptyMap())
        val matrix = Qualification.matrix()
        val validAvailability = mutableSetOf<String>()
        for (row in matrix) {
            validAvailability.add(row.target)
            validAvailability.add("${row.target}:${row.runtime}")
        }
        for (case in cases) {
            validAvailability.add("${case.target}:${case.runtime}:${case.version}")
            validAvailability.add(case.id)
        }
        val unknown = availability.keys - validAvailability
        if (unknown.isNotEmpty()) {
            return usage("unknown availability selector: " + unknown.sortedWith(CanonicalText::compare).joinToString(", "))
        }
        if (availability.values.any { !Py.truthy(it) || (it as? JsonPrimitive)?.isString != true }) {
            return usage("every unavailable reason must be nonempty text")
        }
        for (case in cases) {
            if (case.id in evidence) continue
            val reason = Py.str(availability[case.id])
                ?: Py.str(availability["${case.target}:${case.runtime}:${case.version}"])
                ?: Py.str(availability["${case.target}:${case.runtime}"])
                ?: Py.str(availability[case.target])
            if (!reason.isNullOrEmpty()) {
                evidence[case.id] = buildJsonObject { put("unavailable_reason", JsonPrimitive(reason)) }
            }
        }
        val jvmMode = JvmModePublication(
            StableTreeDigest,
            PythonModeReplay(repository.resolve("tools/qualification")),
        )
        val results = mutableListOf<JsonObject>()
        for (case in cases) {
            val verdict = LaneEvaluation.evaluate(
                case,
                evidence[case.id],
                candidateSha,
                candidateManifest,
                suiteManifest,
                auditData,
                jvmMode,
            )
            results.add(
                buildJsonObject {
                    put("id", JsonPrimitive(verdict.id))
                    put("status", JsonPrimitive(verdict.status))
                    put("reason", JsonPrimitive(verdict.reason))
                },
            )
        }
        val fullHosted = mutableListOf<JsonElement>()
        val laneReceipts = mutableListOf<String>()
        for (bundle in fullHostedBundles) {
            val scoped: LinkedHashMap<String, JsonElement>
            try {
                val verified = LinkedHashMap(
                    ArtifactCapture.verifyFullHosted(bundle, candidateSha, repository),
                )
                val receiptSha256 = Py.str(verified.remove("_verified_receipt_sha256"))
                    ?: throw IllegalArgumentException("verified receipt digest is missing")
                val transportSha256 = Py.str(verified.remove("_verified_transport_sha256"))
                scoped = LinkedHashMap(
                    FullHostedLane.of(JsonObject(verified), receiptSha256, suiteManifest),
                )
                if (transportSha256 != null) {
                    scoped["transport_sha256"] = JsonPrimitive(transportSha256)
                }
                val lanes = (scoped["configuration_lanes"] as JsonArray).mapNotNull { Py.str(it) }
                if (laneReceipts.any { it in lanes }) {
                    throw IllegalArgumentException("duplicate full hosted lane receipt")
                }
                laneReceipts.addAll(lanes)
                if (auditData != null) {
                    val audited = TargetBinaryHashes.of(
                        auditData["artifacts"] as? JsonArray ?: JsonArray(emptyList()),
                    )
                    if (audited[Py.str(scoped["target"])!!] != scoped["artifact_hashes"]) {
                        throw IllegalArgumentException(
                            "full hosted binaries differ from staged audit",
                        )
                    }
                    scoped["audit_manifest_sha256"] =
                        JsonPrimitive(FullCorpus.canonicalDigest(auditData))
                    scoped["audit_status"] = JsonPrimitive("PASSED")
                } else {
                    scoped["audit_status"] = JsonPrimitive("NOT_RUN")
                }
                if (candidateManifest != null) {
                    val declared = candidateManifest["lanes"] as? JsonObject
                    for (laneId in lanes) {
                        val selected = declared?.get(laneId) as? JsonObject
                        if (selected == null ||
                            selected["runtime_version"] != scoped["runtime_version"] ||
                            selected["runtime_identity"] != scoped["runtime_identity"] ||
                            selected["artifact_hashes"] != scoped["artifact_hashes"]
                        ) {
                            throw IllegalArgumentException(
                                "full hosted selected candidate lane differs",
                            )
                        }
                    }
                    scoped["candidate_manifest_sha256"] =
                        JsonPrimitive(FullCorpus.canonicalDigest(candidateManifest))
                    scoped["candidate_manifest_status"] = JsonPrimitive("BOUND")
                } else {
                    scoped["candidate_manifest_status"] = JsonPrimitive("NOT_RUN")
                }
                scoped["complete_suite_status"] = JsonPrimitive(
                    if (suiteManifest == null) "NOT_RUN" else "UNPASSED",
                )
                scoped["release_gate_status"] = JsonPrimitive("NOT_RUN")
                fullHosted.add(JsonObject(scoped))
            } catch (error: Exception) {
                if (error !is IllegalArgumentException && error !is java.io.IOException &&
                    error !is NoSuchElementException && error !is ClassCastException
                ) {
                    throw error
                }
                return usage("full hosted receipt failed: ${error.message}")
            }
        }
        if (independentPerformanceKey != null && independentOptions.isEmpty()) {
            return usage("independent performance key requires raw gate archives")
        }
        if (independentOptions.isNotEmpty()) {
            if (independentOptions.size < 5) {
                return usage("independent archives require a signed audit and pinned trusted key")
            }
            if (suiteManifest == null) {
                return usage("independent archives require the tracked complete suite")
            }
            return usage(
                "independent gate verification is not ported: independent_adapter.verify_lanes " +
                    "has no Kotlin implementation",
            )
        }
        val byId = LinkedHashMap<String, JsonObject>()
        for (result in results) byId[Py.str(result["id"])!!] = result
        for (element in fullHosted) {
            val scoped = element as JsonObject
            for (laneId in (scoped["configuration_lanes"] as JsonArray).mapNotNull { Py.str(it) }) {
                val result = byId[laneId] ?: continue
                if (Py.str(result["status"]) != "PASSED") continue
                val laneEvidence = evidence[laneId] as? JsonObject
                if (Py.str(laneEvidence?.get("full_hosted_receipt_sha256")) !=
                    Py.str(scoped["receipt_sha256"])
                ) {
                    byId[laneId] = JsonObject(
                        result + (
                            "status" to JsonPrimitive("FAILED")
                            ) + (
                            "reason" to JsonPrimitive(
                                "complete lane evidence does not bind verified full hosted receipt",
                            )
                            ),
                    )
                }
            }
        }
        if (rawBundles.size != hostedProbes.size) {
            return usage("each hosted probe needs its matching raw XML bundle")
        }
        val probes = mutableListOf<JsonElement>()
        for ((path, bundle) in hostedProbes.zip(rawBundles)) {
            try {
                var observed = ArtifactCapture.validateHostedProbe(
                    StrictJson.load(Fs.readText(path)) as? JsonObject,
                    candidateSha,
                    StrictJson.load(
                        Fs.readText(repository.resolve("tools/qualification/foundation-probes.json")),
                    ) as JsonObject,
                    repository,
                )
                if (Py.str(observed["status"]) == "PROBE_PASSED") {
                    try {
                        val manifest = StrictJson.load(
                            Fs.readText(repository.resolve("tools/qualification/foundation-probes.json")),
                        ) as JsonObject
                        val verified = ArtifactCapture.verifyBundle(
                            bundle, manifest, candidateSha, requireMatrix = false,
                        )
                        if (Py.str(verified["route"]) != Py.str(observed["target"])) {
                            throw IllegalArgumentException(
                                "raw bundle target differs from hosted probe",
                            )
                        }
                    } catch (error: Exception) {
                        if (error !is IllegalArgumentException && error !is java.io.IOException) throw error
                        observed = JsonObject(
                            (observed + ("status" to JsonPrimitive("PROBE_FAILED"))) + (
                                "reason" to JsonPrimitive("raw XML bundle failed: ${error.message}")
                                ),
                        )
                    }
                }
                probes.add(observed)
            } catch (error: Exception) {
                if (error !is IllegalArgumentException && error !is java.io.IOException) throw error
                return usage(error.message ?: error.toString())
            }
        }
        val finalResults = cases.map { byId.getValue(it.id) }
        val statuses = listOf("PASSED", "FAILED", "UNAVAILABLE", "NOT_RUN")
        val counts = LinkedHashMap<String, Long>()
        for (status in statuses) {
            counts[status] = finalResults.count { Py.str(it["status"]) == status }.toLong()
        }
        val report = buildJsonObject {
            put("candidate_sha", JsonPrimitive(candidateSha))
            put("total", JsonPrimitive(finalResults.size))
            put(
                "counts",
                buildJsonObject { counts.forEach { (key, value) -> put(key, JsonPrimitive(value)) } },
            )
            put("lanes", JsonArray(finalResults))
            put("bounded_hosted_probes", JsonArray(probes))
            put("full_hosted_receipts", JsonArray(fullHosted))
            put("independent_gate_results", buildJsonObject { })
        }
        Fs.writeText(output, PyJson.render(report) + "\n")
        println(
            PyJson.renderDefault(
                buildJsonObject { counts.forEach { (key, value) -> put(key, JsonPrimitive(value)) } },
            ),
        )
        return if (counts["PASSED"] == finalResults.size.toLong()) 0 else 1
    }

    /** Runs one git command and returns its exit status, for the tracked-manifest check. */
    private fun hostedGitStatus(repository: Path, arguments: List<String>): Int {
        val process = ProcessBuilder(listOf("git", "-C", repository.toString()) + arguments)
            .redirectErrorStream(false)
            .start()
        process.inputStream.use { it.readBytes() }
        process.errorStream.use { it.readBytes() }
        return process.waitFor()
    }

    private fun lanesJson(cases: List<io.github.rubixhacker.harness.contract.MatrixCase>): JsonElement =
        JsonArray(
            cases.map { case ->
                buildJsonObject {
                    put("target", JsonPrimitive(case.target))
                    put("runtime", JsonPrimitive(case.runtime))
                    put("minimum", JsonPrimitive(case.minimum))
                    put("kind", JsonPrimitive(case.kind))
                    put("version", JsonPrimitive(case.version))
                    put("configuration", JsonPrimitive(case.configuration))
                    put("id", JsonPrimitive(case.id))
                }
            },
        )

    private fun repositoryRoot(): Path {
        var current: Path? = Path.of("").toAbsolutePath()
        while (current != null) {
            if (Files.isDirectory(current.resolve("tools/qualification"))) return current
            current = current.parent
        }
        throw IllegalArgumentException("qualification repository root was not found")
    }

    private fun usage(message: String): Int {
        System.err.println("usage error: $message")
        return 2
    }
}
