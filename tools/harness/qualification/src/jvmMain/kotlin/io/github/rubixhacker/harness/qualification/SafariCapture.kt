package io.github.rubixhacker.harness.qualification

import io.github.rubixhacker.harness.contract.Sha256
import io.github.rubixhacker.harness.contract.StrictJson
import java.io.IOException
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.NoSuchFileException
import java.nio.file.NotDirectoryException
import java.nio.file.Path
import java.util.UUID
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

/** `safari_reporter.StageFailure`: the staging cleanup left residue and the run is unqualified. */
class SafariStageFailure(val result: JsonObject, message: String) : IOException(message)

/**
 * `safari_yarn_lock.capture` and `safari_yarn_lock.audit_capture`: the diagnostic run and the
 * public audit of its receipt.
 *
 * The reference patches `run_lock_task`, `safari_reporter.stage`, `capture_package_graph`, and
 * `MAX_PROCESS_SECONDS` to drive the failure branches. The JVM has no monkey-patching, so the same
 * seams are explicit parameters: [lockTask], [stageHook], [afterPackageGraph], and
 * [deadlineSeconds]. Production passes none of them.
 *
 * Anchoring is `NOFOLLOW_LINKS` plus an identity re-read, not `dir_fd`/`O_NOFOLLOW`; the residual
 * race is recorded in `docs/specs/harness-port-status.md`. The Windows machinery (`CreateFileW`,
 * job objects, `LockedDirectory`) is not ported, so a Windows host fails closed in
 * [SafariYarnLockHost.runLockTask] and [SafariReporterHost.stage].
 */
object SafariCapture {
    /** The lock task signature: `(repository, output, expected command or null) -> process`. */
    fun interface LockTask {
        fun run(repository: Path, output: Path, command: List<String>?): JsonObject
    }

    /** The staging signature: `(repository, candidate, projects, output, body) -> final stage`. */
    fun interface StageHook {
        fun stage(
            repository: Path,
            candidateSha: String,
            projects: List<String>,
            output: Path,
            body: () -> Unit,
        ): JsonObject
    }

    /**
     * `capture`: run the lock task under the hosted diagnostic and write `receipt.json`.
     *
     * Every branch writes a receipt except the three preconditions and the archived-input
     * comparison, which raise before the archive exists.
     */
    fun capture(
        repositoryInput: Path,
        candidateSha: String,
        outputInput: Path,
        configuration: String? = null,
        deadlineSeconds: Int = SafariYarnLockRules.MAX_PROCESS_SECONDS,
        lockTask: LockTask? = null,
        stageHook: StageHook? = null,
        afterPackageGraph: (() -> Unit)? = null,
    ): JsonObject {
        val repository = SafariReporterHost.resolvePath(repositoryInput)
        val output = SafariReporterHost.resolvePath(outputInput)
        if (configuration != null && configuration != "development" &&
            configuration != "production"
        ) {
            throw IllegalArgumentException("invalid Safari diagnostic configuration")
        }
        if (output.startsWith(repository)) {
            throw IllegalArgumentException("diagnostic output must be outside the source checkout")
        }
        if (Files.exists(output)) {
            val entries = try {
                Files.newDirectoryStream(output).use { it.iterator().hasNext() }
            } catch (error: NotDirectoryException) {
                throw IllegalArgumentException("diagnostic output must be empty")
            }
            if (entries) {
                throw IllegalArgumentException("diagnostic output must be empty")
            }
        }
        if (Files.exists(repository.resolve(SafariYarnLockRules.GENERATED_LOCK))) {
            throw IllegalArgumentException("preexisting generated lock prevents a fresh diagnosis")
        }
        SafariYarnLockHost.requireCandidate(repository, candidateSha)
        Files.createDirectories(output)

        val files = mutableListOf<JsonObject>()
        files.add(
            SafariYarnLockHost.copyFile(
                repository,
                SafariYarnLockRules.TRACKED_LOCK,
                output,
                "tracked",
            ),
        )
        val sourceInputs = listOf(SafariYarnLockRules.TRACKED_LOCK) +
            SafariYarnLockRules.SOURCE_INPUTS +
            (if (configuration != null) SafariYarnLockRules.HOSTED_SOURCE_INPUTS else emptyList())
        for (path in sourceInputs.drop(1)) {
            files.add(SafariYarnLockHost.copyFile(repository, path, output, "inputs"))
        }
        val committedHashes = LinkedHashMap<String, String>()
        for (path in sourceInputs) {
            committedHashes[path] = Sha256.of(
                SafariReporterHost.committedBytes(repository, candidateSha, Path.of(path)),
            )
        }
        val capturedHashes = LinkedHashMap<String, String>()
        for (item in files) {
            val source = Path.of(Py.str(item["source_path"])!!)
            capturedHashes[posixRelative(repository, source)] = Py.str(item["sha256"])!!
        }
        if (capturedHashes != committedHashes) {
            throw IllegalArgumentException("archived source inputs differ from candidate")
        }

        val receipt = LinkedHashMap<String, JsonElement>()
        receipt["schema"] = JsonPrimitive(1)
        receipt["kind"] = JsonPrimitive("safari-yarn-lock-diagnostic")
        receipt["candidate_sha"] = JsonPrimitive(candidateSha)
        receipt["qualified"] = JsonPrimitive(false)
        receipt["configuration"] = configuration?.let { JsonPrimitive(it) } ?: JsonNull
        receipt["repository_root"] = JsonPrimitive(repository.toString())
        receipt["archive_root"] = JsonPrimitive(output.toString())
        receipt["host"] = JsonObject(
            linkedMapOf(
                "system" to JsonPrimitive(DefaultHostEnvironment.system()),
                "machine" to JsonPrimitive(DefaultHostEnvironment.machine()),
                "java_home" to environment("JAVA_HOME"),
                "runner_image_os" to environment("ImageOS"),
                "runner_image_version" to environment("ImageVersion"),
            ),
        )
        receipt["tracked_sha256"] = JsonPrimitive(capturedHashes[SafariYarnLockRules.TRACKED_LOCK]!!)
        receipt["source_input_sha256"] = JsonObject(
            LinkedHashMap(committedHashes.mapValues { JsonPrimitive(it.value) }),
        )

        var expectedCommand: List<String>? = null
        if (configuration != null) {
            val init = output.resolve(configuration).resolve("qualification.init.gradle")
            Files.createDirectory(init.parent)
            val script = FullHostedRules.initScript("jsSafari", configuration)
                .toByteArray(StandardCharsets.UTF_8)
            Files.write(init, script)
            files.add(
                buildJsonObject {
                    put("path", JsonPrimitive(posixRelative(output, init)))
                    put("sha256", JsonPrimitive(digestFile(init)))
                    put("size", JsonPrimitive(Files.size(init)))
                },
            )
            val invocationId = UUID.randomUUID().toString().replace("-", "")
            receipt["invocation_id"] = JsonPrimitive(invocationId)
            expectedCommand = SafariYarnLockRules.fullHostedCommand(
                repository.toString(),
                init.toString(),
                configuration,
                invocationId,
            )
            receipt["init_script_sha256"] = JsonPrimitive(digestFile(init))
        }

        var reporterStage: JsonObject? = null
        var process: JsonObject? = null
        val runner = lockTask ?: LockTask { repo, folder, command ->
            SafariYarnLockHost.runLockTask(
                repo,
                folder,
                command,
                deadlineSeconds = deadlineSeconds,
            )
        }
        try {
            if (configuration != null) {
                var bodyFailure: Throwable? = null
                val staged = (stageHook ?: StageHook { repo, sha, projects, folder, body ->
                    SafariReporterHost.stage(repo, sha, projects, folder) { body() }
                }).stage(
                    repository,
                    candidateSha,
                    listOf("dyn4k-core", "dyn4k"),
                    output,
                ) {
                    try {
                        process = runner.run(repository, output, expectedCommand)
                    } catch (error: Throwable) {
                        bodyFailure = error
                    }
                }
                reporterStage = staged
                if (bodyFailure != null) throw bodyFailure!!
                receipt["reporter_stage"] = staged
                addForensicFiles(staged, files)
            } else {
                process = runner.run(repository, output, null)
            }
        } catch (error: SafariStageFailure) {
            addForensicFiles(error.result, files)
            receipt["status"] = JsonPrimitive("STAGED_REPORTER_CHANGED")
            receipt["reason"] = JsonPrimitive(error.message ?: "")
            receipt["reporter_stage"] = error.result
            receipt["files"] = JsonArray(files)
            writeReceipt(output, receipt)
            return JsonObject(receipt)
        } catch (error: Exception) {
            if (reporterStage != null) {
                receipt["reporter_stage"] = reporterStage
                addForensicFiles(reporterStage, files)
            }
            for (name in listOf("stdout.txt", "stderr.txt")) {
                val path = output.resolve(name)
                try {
                    if (Files.isRegularFile(path)) {
                        files.add(
                            buildJsonObject {
                                put("path", JsonPrimitive(name))
                                put("sha256", JsonPrimitive(digestFile(path)))
                                put("size", JsonPrimitive(Files.size(path)))
                            },
                        )
                    }
                } catch (ignored: IOException) {
                    // The reference ignores an unreadable log here as well.
                }
            }
            receipt["status"] = JsonPrimitive("PROCESS_CAPTURE_FAILED")
            receipt["reason"] = JsonPrimitive((error.message ?: "").take(512))
            receipt["files"] = JsonArray(files)
            writeReceipt(output, receipt)
            return JsonObject(receipt)
        }
        val execution = process!!
        receipt["process"] = execution
        for (name in listOf("stdout.txt", "stderr.txt")) {
            val path = output.resolve(name)
            if (Files.isRegularFile(path)) {
                files.add(
                    buildJsonObject {
                        put("path", JsonPrimitive(name))
                        put("sha256", JsonPrimitive(digestFile(path)))
                        put("size", JsonPrimitive(Files.size(path)))
                    },
                )
            }
        }
        receipt["head_after_task"] = JsonPrimitive(git(repository, "rev-parse", "HEAD"))
        receipt["tracked_changes_after_task"] = JsonPrimitive(
            git(repository, "status", "--porcelain=v1", "--untracked-files=no"),
        )
        try {
            if (configuration != null &&
                digestFile(output.resolve(configuration).resolve("qualification.init.gradle")) !=
                Py.str(receipt["init_script_sha256"])
            ) {
                throw IllegalArgumentException("hosted Safari init script changed during task")
            }
            if (Files.isRegularFile(
                    SafariYarnLockHost.sourcePath(repository, SafariYarnLockRules.GENERATED_LOCK),
                )
            ) {
                files.add(
                    SafariYarnLockHost.copyFile(
                        repository,
                        SafariYarnLockRules.GENERATED_LOCK,
                        output,
                        "generated",
                    ),
                )
                receipt["generated_sha256"] = JsonPrimitive(
                    digestFile(
                        output.resolve("generated")
                            .resolve(SafariYarnLockRules.GENERATED_LOCK),
                    ),
                )
            }
            capturePackageGraph(repository, output, files, receipt)
            afterPackageGraph?.invoke()
            files.add(
                SafariYarnLockHost.copyFile(
                    repository,
                    SafariYarnLockRules.TRACKED_LOCK,
                    output,
                    "tracked-after",
                ),
            )
            receipt["tracked_after_sha256"] = JsonPrimitive(
                digestFile(
                    output.resolve("tracked-after")
                        .resolve(SafariYarnLockRules.TRACKED_LOCK),
                ),
            )
            for (item in files) {
                val archivedPath = Py.str(item["path"])!!
                if (!archivedPath.startsWith("generated/")) continue
                val source = Path.of(Py.str(item["source_path"])!!)
                if (SafariYarnLockHost.sourceDigest(repository, posixRelative(repository, source)) !=
                    Py.str(item["sha256"])
                ) {
                    throw IllegalArgumentException(
                        "generated input changed during capture: $archivedPath",
                    )
                }
            }
            receipt["source_input_after_sha256"] = JsonObject(
                LinkedHashMap(
                    sourceInputs.associateWith {
                        JsonPrimitive(SafariYarnLockHost.sourceDigest(repository, it))
                    },
                ),
            )
            receipt["head_after"] = JsonPrimitive(git(repository, "rev-parse", "HEAD"))
            receipt["tracked_changes_after"] = JsonPrimitive(
                git(repository, "status", "--porcelain=v1", "--untracked-files=no"),
            )
            val stdout = Files.readAllBytes(output.resolve("stdout.txt"))
            val stderrBytes = Files.readAllBytes(output.resolve("stderr.txt"))
            val lockSucceeded = containsLine(stdout, "> Task :kotlinStoreYarnLock")
            val lockFailed = containsLine(stdout, "> Task :kotlinStoreYarnLock FAILED")
            val generated = Py.str(receipt["generated_sha256"])
            val tracked = Py.str(receipt["tracked_sha256"])
            fun exitCode(): Long = Py.int(execution["exit_code"]!!)
            val stageStatus = Py.str(reporterStage?.get("status"))
            val hosted = configuration != null
            val sourceChanged = Py.str(receipt["head_after_task"]) != candidateSha ||
                Py.str(receipt["head_after"]) != candidateSha ||
                Py.truthy(receipt["tracked_changes_after_task"]) ||
                Py.truthy(receipt["tracked_changes_after"]) ||
                receipt["source_input_after_sha256"] != receipt["source_input_sha256"]
            val bindingRejected = hosted && (
                !commandMatches(execution["command"], expectedCommand) ||
                    !Py.isInt(execution["pid"]) || Py.int(execution["pid"]) <= 0 ||
                    !Py.isInt(execution["started_ns"]) ||
                    !Py.isInt(execution["finished_ns"]) ||
                    Py.int(execution["started_ns"]) >= Py.int(execution["finished_ns"]) ||
                    SafariYarnLockRules.HOSTED_TASK_MARKERS.any {
                        !containsBytes(stdout, it)
                    } ||
                    !(lockSucceeded || lockFailed)
                )
            val incompleteLog = Py.truthy(execution["stream_incomplete"]) ||
                Py.truthy(execution["stdout_truncated"]) ||
                Py.truthy(execution["stderr_truncated"]) ||
                !Files.isRegularFile(output.resolve("stdout.txt")) ||
                !Files.isRegularFile(output.resolve("stderr.txt"))
            val incompleteGraph = Py.truthy(receipt["missing_package_inputs"]) ||
                Py.truthy(receipt["unexpected_package_inputs"]) ||
                Py.truthy(receipt["package_count_exceeds_bound"]) ||
                Py.truthy(receipt["package_graph_errors"])
            when {
                hosted && stageStatus != "CLEAN" ->
                    receipt["status"] = JsonPrimitive("STAGED_REPORTER_CHANGED")
                sourceChanged -> receipt["status"] = JsonPrimitive("SOURCE_CHANGED")
                bindingRejected -> receipt["status"] = JsonPrimitive("PROCESS_BINDING_REJECTED")
                Py.truthy(execution["timed_out"]) ->
                    receipt["status"] = JsonPrimitive("PROCESS_TIMEOUT")
                incompleteLog -> receipt["status"] = JsonPrimitive("INCOMPLETE_LOG_CAPTURE")
                !receipt.containsKey("generated_sha256") ->
                    receipt["status"] = JsonPrimitive("NO_GENERATED_LOCK")
                incompleteGraph -> receipt["status"] = JsonPrimitive("INCOMPLETE_PACKAGE_GRAPH")
                exitCode() == 0L && (!hosted || lockSucceeded) && generated == tracked ->
                    receipt["status"] = JsonPrimitive("LOCK_MATCHED_DIAGNOSTIC_ONLY")
                exitCode() != 0L && (!hosted || lockFailed) && generated != tracked &&
                    SafariYarnLockHost.lockFailureSignature(
                        String(stderrBytes, StandardCharsets.UTF_8),
                    ) -> receipt["status"] = JsonPrimitive("LOCK_MISMATCH_CAPTURED")
                hosted && exitCode() != 0L && lockSucceeded && generated == tracked &&
                    SafariYarnLockRules.safariCaptureTimeout(
                        String(stdout, StandardCharsets.UTF_8),
                        String(stderrBytes, StandardCharsets.UTF_8),
                    ) -> receipt["status"] = JsonPrimitive("SAFARI_CAPTURE_TIMEOUT")
                hosted && exitCode() != 0L && lockSucceeded && generated == tracked &&
                    SafariYarnLockRules.safariOutputOverflow(
                        String(stdout, StandardCharsets.UTF_8),
                        String(stderrBytes, StandardCharsets.UTF_8),
                    ) -> receipt["status"] = JsonPrimitive("SAFARI_TEST_OUTPUT_OVERFLOW")
                else -> receipt["status"] = JsonPrimitive("OTHER_GRADLE_RESULT")
            }
        } catch (error: IOException) {
            reject(receipt, error.message)
        } catch (error: IllegalArgumentException) {
            reject(receipt, error.message)
        }
        receipt["files"] = JsonArray(files)
        writeReceipt(output, receipt)
        return JsonObject(receipt)
    }

    /**
     * `audit_capture`: re-derive every claim of a hosted capture from the archive and the checkout.
     *
     * Nothing here trusts the receipt's own digests: each file is re-read through the no-follow
     * path, and the archived source inputs are compared with the committed candidate objects.
     */
    fun auditCapture(
        repositoryInput: Path,
        candidateSha: String,
        outputInput: Path,
    ): JsonObject {
        val repository = SafariReporterHost.resolvePath(repositoryInput)
        val output = SafariReporterHost.resolvePath(outputInput)
        SafariYarnLockHost.requireCandidate(repository, candidateSha)
        val receipt = StrictJson.load(
            String(SafariYarnLockHost.sourceBytes(output, "receipt.json"), StandardCharsets.UTF_8),
        ) as? JsonObject
            ?: throw IllegalArgumentException("hosted diagnostic identity differs")
        val configuration = Py.str(receipt["configuration"])
        if (Py.str(receipt["candidate_sha"]) != candidateSha ||
            receipt["qualified"] != JsonPrimitive(false) ||
            Py.str(receipt["status"]) != "LOCK_MISMATCH_CAPTURED" ||
            Py.str(receipt["head_after_task"]) != candidateSha ||
            Py.str(receipt["head_after"]) != candidateSha ||
            Py.str(receipt["tracked_changes_after_task"]) != "" ||
            Py.str(receipt["tracked_changes_after"]) != "" ||
            (configuration != "development" && configuration != "production") ||
            !Py.INVOCATION.matches(Py.str(receipt["invocation_id"]) ?: "")
        ) {
            throw IllegalArgumentException("hosted diagnostic identity differs")
        }
        val sourceInputs = listOf(SafariYarnLockRules.TRACKED_LOCK) +
            SafariYarnLockRules.SOURCE_INPUTS +
            SafariYarnLockRules.HOSTED_SOURCE_INPUTS
        val initRelative = "$configuration/qualification.init.gradle"
        val expected = SafariYarnLockRules.hostedExpectedFiles(
            configuration,
            SafariYarnLockRules.TRACKED_LOCK,
            SafariYarnLockRules.GENERATED_LOCK,
            sourceInputs,
            SafariYarnLockRules.REQUIRED_PACKAGE_INPUTS,
        )
        val expectedInputs = SafariYarnLockRules.REQUIRED_PACKAGE_INPUTS
        val observedInputs = (receipt["package_inputs_observed"] as? JsonArray)
            ?.mapNotNull { Py.str(it) }?.toSet() ?: emptySet()
        if ((receipt["package_inputs_expected"] as? JsonArray)?.mapNotNull { Py.str(it) } !=
            expectedInputs ||
            observedInputs != expectedInputs.toSet() ||
            (receipt["missing_package_inputs"] as? JsonArray)?.isNotEmpty() == true ||
            (receipt["unexpected_package_inputs"] as? JsonArray)?.isNotEmpty() == true ||
            (receipt["package_graph_errors"] as? JsonArray)?.isNotEmpty() == true ||
            receipt["package_count_exceeds_bound"] != JsonPrimitive(false)
        ) {
            throw IllegalArgumentException(
                "hosted diagnostic package graph inventory differs",
            )
        }
        val files = receipt["files"] as? JsonArray
            ?: throw IllegalArgumentException("hosted diagnostic file inventory differs")
        val listed = files.mapNotNull { item ->
            (item as? JsonObject)?.let { Py.str(it["path"]) ?: CanonicalText.of(it["path"]) }
        }.toSet()
        if (listed != expected || files.size != expected.size) {
            throw IllegalArgumentException("hosted diagnostic file inventory differs")
        }
        for (item in files) {
            val record = item as JsonObject
            val relative = Py.str(record["path"])
                ?: throw IllegalArgumentException("hosted diagnostic file inventory differs")
            val data = SafariYarnLockHost.sourceBytes(output, relative)
            if (Sha256.of(data) != Py.str(record["sha256"]) ||
                !Py.equalsInt(record["size"], data.size.toLong())
            ) {
                throw IllegalArgumentException("hosted diagnostic raw file differs: $relative")
            }
        }
        val committed = LinkedHashMap<String, String>()
        for (path in sourceInputs) {
            committed[path] = Sha256.of(
                SafariReporterHost.committedBytes(repository, candidateSha, Path.of(path)),
            )
        }
        if (receipt["source_input_sha256"] != receipt["source_input_after_sha256"] ||
            (receipt["source_input_sha256"] as? JsonObject)?.mapValues { Py.str(it.value) } !=
            committed
        ) {
            throw IllegalArgumentException(
                "hosted diagnostic candidate source binding differs",
            )
        }
        for (path in sourceInputs) {
            val prefix = if (path == SafariYarnLockRules.TRACKED_LOCK) "tracked" else "inputs"
            if (Sha256.of(SafariYarnLockHost.sourceBytes(output, "$prefix/$path")) !=
                committed[path]
            ) {
                throw IllegalArgumentException("hosted diagnostic archived source differs: $path")
            }
        }
        val script = FullHostedRules.initScript("jsSafari", configuration)
            .toByteArray(StandardCharsets.UTF_8)
        if (!SafariYarnLockHost.sourceBytes(output, initRelative).contentEquals(script) ||
            Py.str(receipt["init_script_sha256"]) != Sha256.of(script)
        ) {
            throw IllegalArgumentException("hosted diagnostic init script differs")
        }
        val originalRepository = Py.str(receipt["repository_root"])?.let { Path.of(it) }
        val originalOutput = Py.str(receipt["archive_root"])?.let { Path.of(it) }
        if (originalRepository == null || originalOutput == null ||
            !originalRepository.isAbsolute || !originalOutput.isAbsolute
        ) {
            throw IllegalArgumentException("hosted diagnostic original paths are absent")
        }
        val process = receipt["process"] as? JsonObject
            ?: throw IllegalArgumentException("hosted diagnostic process binding differs")
        val expectedCommand = SafariYarnLockRules.fullHostedCommand(
            originalRepository.toString(),
            originalOutput.resolve(initRelative).toString(),
            configuration,
            Py.str(receipt["invocation_id"])!!,
        )
        if (!commandMatches(process["command"], expectedCommand) ||
            !Py.isInt(process["pid"]) || Py.int(process["pid"]) <= 0 ||
            !Py.isInt(process["started_ns"]) ||
            !Py.isInt(process["finished_ns"]) ||
            Py.int(process["started_ns"]) >= Py.int(process["finished_ns"]) ||
            !Py.isInt(process["exit_code"]) ||
            Py.int(process["exit_code"]) == 0L ||
            listOf("timed_out", "stream_incomplete", "stdout_truncated", "stderr_truncated")
                .any { Py.truthy(process[it]) }
        ) {
            throw IllegalArgumentException("hosted diagnostic process binding differs")
        }
        val stdoutPath = output.resolve("stdout.txt")
        val stderrPath = output.resolve("stderr.txt")
        val stdout = Files.readAllBytes(stdoutPath)
        val markers = SafariYarnLockRules.hostedTaskMarkers(Py.int(process["exit_code"]))
        if (Py.int(process["stdout_bytes_seen"]!!) != Files.size(stdoutPath) ||
            Py.int(process["stderr_bytes_seen"]!!) != Files.size(stderrPath) ||
            markers.any { !containsBytes(stdout, it) } ||
            !SafariYarnLockHost.lockFailureSignature(
                String(Files.readAllBytes(stderrPath), StandardCharsets.UTF_8),
            )
        ) {
            throw IllegalArgumentException("hosted diagnostic process output differs")
        }
        val tracked = SafariYarnLockHost.sourceBytes(
            output,
            "tracked/${SafariYarnLockRules.TRACKED_LOCK}",
        )
        val generated = SafariYarnLockHost.sourceBytes(
            output,
            "generated/${SafariYarnLockRules.GENERATED_LOCK}",
        )
        if (tracked.contentEquals(generated) ||
            !tracked.contentEquals(
                SafariYarnLockHost.sourceBytes(
                    output,
                    "tracked-after/${SafariYarnLockRules.TRACKED_LOCK}",
                ),
            ) ||
            Py.str(receipt["tracked_sha256"]) != Sha256.of(tracked) ||
            Py.str(receipt["tracked_after_sha256"]) != Sha256.of(tracked) ||
            Py.str(receipt["generated_sha256"]) != Sha256.of(generated)
        ) {
            throw IllegalArgumentException("hosted diagnostic lock bytes differ")
        }
        for (name in listOf("dyn4k-dyn4k-core-test", "dyn4k-dyn4k-test")) {
            val data = SafariYarnLockHost.sourceBytes(
                output,
                "generated/build/js/packages/$name/package.json",
            )
            val packageJson = try {
                StrictJson.load(String(data, StandardCharsets.UTF_8)) as? JsonObject
            } catch (error: Exception) {
                null
            }
            val dependency = Py.str(
                (packageJson?.get("devDependencies") as? JsonObject)?.get("karma-safari-launcher"),
            )
            if (dependency != "1.0.0") {
                throw IllegalArgumentException("hosted diagnostic Safari package differs: $name")
            }
        }
        return receipt
    }

    private fun reject(receipt: MutableMap<String, JsonElement>, reason: String?) {
        receipt["status"] = JsonPrimitive("CAPTURE_REJECTED")
        receipt["reason"] = JsonPrimitive(reason ?: "")
    }

    private fun writeReceipt(output: Path, receipt: MutableMap<String, JsonElement>) {
        Files.writeString(
            output.resolve("receipt.json"),
            PyJson.renderSorted(JsonObject(receipt)) + "\n",
        )
    }

    /** The forensic members a staging result archived, as receipt file records. */
    private fun addForensicFiles(stage: JsonObject, files: MutableList<JsonObject>) {
        val forensic = stage["forensic"] as? JsonArray ?: return
        for (item in forensic) {
            val record = item as? JsonObject ?: continue
            val archivePath = Py.str(record["archive_path"]) ?: continue
            files.add(
                buildJsonObject {
                    put("path", JsonPrimitive(archivePath))
                    put("sha256", JsonPrimitive(Py.str(record["sha256"]) ?: ""))
                    put("size", JsonPrimitive(Py.int(record["retained_size"]!!)))
                },
            )
        }
    }

    private fun environment(name: String): JsonElement =
        System.getenv(name)?.let { JsonPrimitive(it) } ?: JsonNull

    /** The reference's `^> Task ...\r?$` marker: one complete line of the raw byte log. */
    private fun containsLine(stdout: ByteArray, marker: String): Boolean =
        String(stdout, StandardCharsets.ISO_8859_1).split('\n')
            .any { it.removeSuffix("\r") == marker }

    /** The reference's `marker in stdout` on bytes: a substring of the raw byte log. */
    private fun containsBytes(stdout: ByteArray, marker: String): Boolean =
        String(stdout, StandardCharsets.ISO_8859_1).contains(marker)

    private fun commandMatches(value: JsonElement?, expected: List<String>?): Boolean {
        if (expected == null) return false
        val items = (value as? JsonArray)?.mapNotNull { Py.str(it) } ?: return false
        return items == expected && items.size == (value as JsonArray).size
    }

    private fun git(repository: Path, vararg arguments: String): String {
        val process = ProcessBuilder(
            listOf("git", "--no-replace-objects", "-C", repository.toString()) + arguments,
        ).start()
        val stdout = process.inputStream.use { it.readBytes() }
        val stderr = process.errorStream.use { it.readBytes() }
        if (process.waitFor() != 0) {
            throw IllegalArgumentException(
                "git ${arguments.joinToString(" ")} failed: " +
                    String(stderr, StandardCharsets.UTF_8).trim(),
            )
        }
        return String(stdout, StandardCharsets.UTF_8).trim()
    }
}
