package io.github.rubixhacker.harness.qualification

import io.github.rubixhacker.harness.contract.Qualification
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.StandardOpenOption
import java.util.UUID
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

/**
 * `full_hosted.run`: the hosted full-common-corpus run of one target.
 *
 * Both configurations stage once, run the source and staged-consumer test tasks, capture every
 * product, report, and resolved artifact, and then the receipt is verified by
 * `FullHosted.verifyRawFiles`. The reference writes `receipt.json` in a `finally` block, so a run
 * that fails at any point still leaves the evidence that says why.
 */
object FullHostedRun {
    private const val STAGE_TASK =
        ":dyn4k-core:publishKotlinMultiplatformPublicationToStagingRepository"

    fun run(repository: Path, candidateSha: String, target: String, outputInput: Path): JsonObject {
        val repositoryPath = repository.toAbsolutePath().normalize()
        Files.createDirectories(outputInput)
        val output = outputInput.toAbsolutePath().normalize()
        val receipt = LinkedHashMap<String, JsonElement>()
        receipt["schema"] = JsonPrimitive(2)
        receipt["kind"] = JsonPrimitive("hosted-full-common-corpus")
        receipt["candidate_sha"] = JsonPrimitive(candidateSha)
        receipt["target"] = JsonPrimitive(target)
        receipt["status"] = JsonPrimitive("NOT_RUN")
        receipt["configurations"] = JsonArray(emptyList())
        receipt["archive_root"] = JsonPrimitive(output.toString())
        receipt["repository_root"] = JsonPrimitive(repositoryPath.toString())
        receipt["runner_home"] = JsonPrimitive(System.getProperty("user.home"))
        receipt["gradle_user_home_override"] = System.getenv("GRADLE_USER_HOME")?.let {
            JsonPrimitive(it)
        } ?: JsonNull
        receipt["github_run_id"] = System.getenv("GITHUB_RUN_ID")?.let { JsonPrimitive(it) } ?: JsonNull
        receipt["github_job"] = System.getenv("GITHUB_JOB")?.let { JsonPrimitive(it) } ?: JsonNull
        receipt["runner_name"] = System.getenv("RUNNER_NAME")?.let { JsonPrimitive(it) } ?: JsonNull
        receipt["runner_os"] = System.getenv("RUNNER_OS")?.let { JsonPrimitive(it) } ?: JsonNull
        receipt["runner_arch"] = System.getenv("RUNNER_ARCH")?.let { JsonPrimitive(it) } ?: JsonNull
        val lanes = mutableListOf<JsonElement>()
        try {
            if (target !in Hosted.TARGETS || !Py.SHA40.matches(candidateSha)) {
                throw IllegalArgumentException("target or candidate SHA is invalid")
            }
            val manifest = FullHostedRuntime.loadCorpus(repositoryPath, candidateSha)
            receipt["manifest_sha256"] = JsonPrimitive(FullHosted.canonicalHash(manifest))
            receipt["source_tree_sha256"] = manifest["source_tree_sha256"] ?: JsonNull
            receipt["map_sha256"] = JsonPrimitive(
                FullHosted.sha256(repositoryPath.resolve(FullHosted.MAPPING)),
            )
            receipt["reviewed_pairs_sha256"] = JsonPrimitive(
                FullHosted.sha256(repositoryPath.resolve(FullHosted.PAIRS)),
            )
            for (path in FullHosted.INPUTS) {
                FullHosted.archiveCopy(repositoryPath.resolve(path), output, "inputs/$path")
            }
            for (element in manifest["source_files"] as JsonArray) {
                val source = element as JsonObject
                val name = Py.str(source["path"])!!
                FullHosted.archiveCopy(repositoryPath.resolve(name), output, "sources/$name")
            }
            val runtime = LinkedHashMap<String, JsonElement>(HostedHost.discoverRuntime(target))
            receipt["runtime"] = JsonObject(runtime)
            val verdict = Hosted.runtimeStatus(target, JsonObject(runtime))
            if (verdict.status != "READY") {
                receipt["status"] = JsonPrimitive(verdict.status)
                receipt["reason"] = JsonPrimitive(verdict.reason)
                return JsonObject(receipt)
            }
            val wrapper = Hosted.gradleWrapper(
                repositoryPath.toString(),
                DefaultHostEnvironment.isWindows(),
            )
            runtime["gradle_version"] = JsonPrimitive(
                HostedHost.toolVersion(listOf(wrapper, "--version"), Regex("Gradle ([0-9.]+)")),
            )
            val build = Fs.readText(repositoryPath.resolve("build.gradle.kts"))
            runtime["kgp_declared_version"] = JsonPrimitive(
                FullHosted.declaredPluginVersion(
                    build,
                    Regex("kotlin\\(\"multiplatform\"\\) version \"([^\"]+)\""),
                ),
            )
            runtime["agp_declared_version"] = JsonPrimitive(
                FullHosted.declaredPluginVersion(
                    build,
                    Regex("id\\(\"com\\.android\\.kotlin\\.multiplatform\\.library\"\\) version \"([^\"]+)\""),
                ),
            )
            FullHosted.requirePinnedToolchain(JsonObject(runtime))
            receipt["runtime"] = JsonObject(runtime)
            var simulatorUdid: String? = null
            val simulatorFamily = Hosted.NATIVE_TARGETS[target]?.simulator
            if (simulatorFamily != null) {
                val devices = ((runtime["simulators"] as? JsonObject)?.get(simulatorFamily) as? JsonArray)
                    ?.toList() ?: emptyList()
                val chosen = devices.firstOrNull() as? JsonObject
                    ?: throw IllegalArgumentException("available simulator identity is absent")
                simulatorUdid = Py.str(chosen["udid"])
                receipt["selected_simulator"] = chosen
            }
            val artifactTarget = if (target == "jsSafari") "js" else target
            val stage = mutableListOf(wrapper, "--no-daemon", "--console=plain", "--rerun-tasks")
            for (module in Qualification.modules) {
                stage.add(":$module:publishKotlinMultiplatformPublicationToStagingRepository")
                stage.add(
                    ":$module:publish${artifactTarget.replaceFirstChar { it.uppercase() }}" +
                        "PublicationToStagingRepository",
                )
            }
            val stageProcess = FullHostedRuntime.runCommand(stage, repositoryPath, output.resolve("stage"))
            receipt["stage"] = stageProcess
            if (!Py.equalsInt(stageProcess["exit_code"], 0L)) {
                throw IllegalArgumentException("staging command failed")
            }
            val staging = repositoryPath.resolve("build/staging-repository")
            receipt["staging_repository"] = JsonPrimitive(staging.toString())
            val targetHashes = HostedHost.targetHashes(staging, artifactTarget)
            receipt["artifact_hashes"] = targetHashes
            val captured = ArtifactCapture.captureStaging(
                repositoryPath,
                output,
                listOf(artifactTarget),
                candidateSha,
            )
            receipt["staged_gav"] = JsonArray(captured.gav.map { JsonPrimitive(it) })
            receipt["staged_content_contract"] = captured.contentContract
            if (captured.hashes[artifactTarget] != targetHashes) {
                throw IllegalArgumentException("staged artifact capture differs from target hashes")
            }
            FullHostedRuntime.captureDokkaOutput(repositoryPath, output, receipt)
            val task = FullHosted.SOURCE_TASK.getValue(target)
            for (config in FullHosted.CONFIGS.getValue(target)) {
                val folder = output.resolve(config)
                Files.createDirectory(folder)
                val lane = LinkedHashMap<String, JsonElement>()
                lane["configuration"] = JsonPrimitive(config)
                lane["invocation_id"] = JsonPrimitive(UUID.randomUUID().toString().replace("-", ""))
                lane["status"] = JsonPrimitive("NOT_RUN")
                receipt["configurations"] = JsonArray(lanes + JsonObject(lane))
                try {
                    val script = FullHostedRules.initScript(target, config, simulatorUdid)
                    val init = folder.resolve("qualification.init.gradle")
                    Fs.writeText(init, script)
                    val args = if (script.isEmpty()) emptyList() else listOf("--init-script", init.toString())
                    for (module in Qualification.modules) {
                        val directory = repositoryPath.resolve(module)
                            .resolve("build/test-results").resolve(task)
                        if (Files.isDirectory(directory)) {
                            Files.newDirectoryStream(directory).use { stream ->
                                stream.filter {
                                    it.fileName.toString().startsWith("TEST-") &&
                                        it.fileName.toString().endsWith(".xml")
                                }.forEach { Files.deleteIfExists(it) }
                            }
                        }
                    }
                    val invocation = Py.str(lane["invocation_id"])!!
                    val command = mutableListOf(
                        wrapper, "--no-daemon", "--console=plain", "--rerun-tasks",
                    )
                    command.addAll(args)
                    command.add(":dyn4k-core:$task")
                    command.add(":dyn4k:$task")
                    command.add("-PqualificationInvocationId=$invocation")
                    if (target == "jsSafari" && config == "production") {
                        command.add("-PqualificationProduction=true")
                    }
                    if (target == "jsSafari") {
                        lane["safari_reporter_stage"] = JsonObject(emptyMap())
                        lane["safari_karma_configs"] = JsonObject(emptyMap())
                        val staged = SafariReporterHost.stage(
                            repositoryPath,
                            candidateSha,
                            listOf("dyn4k-core", "dyn4k"),
                            folder,
                        ) {
                            lane["source_process"] = FullHostedRuntime.runCommand(
                                command,
                                repositoryPath,
                                folder.resolve("source"),
                                invocation,
                            )
                        }
                        (lane["safari_reporter_stage"] as? JsonObject)?.let { _ -> }
                        lane["safari_reporter_stage"] = stageResult(lane, "source", staged)
                        if (Py.str(staged["status"]) != "CLEAN") {
                            throw IllegalArgumentException("staged Safari source reporter changed")
                        }
                        val configs = LinkedHashMap<String, JsonElement>()
                        for (module in Qualification.modules) {
                            configs[module] = FullHostedRuntime.captureSafariConfig(
                                repositoryPath,
                                candidateSha,
                                module,
                                config,
                                lane["source_process"] as JsonObject,
                                output,
                                "$config/karma-config/$module/karma.conf.js",
                            )
                        }
                        lane["safari_karma_configs"] = JsonObject(configs)
                    } else {
                        lane["source_process"] = FullHostedRuntime.runCommand(
                            command,
                            repositoryPath,
                            folder.resolve("source"),
                            invocation,
                        )
                    }
                    val sourceProcess = lane["source_process"] as JsonObject
                    FullHostedRuntime.requireTestTasks(
                        sourceProcess,
                        folder.resolve("source"),
                        target,
                        config,
                        Qualification.modules,
                    )
                    val sourceExecutables = FullHostedRuntime.collectTestProducts(
                        Qualification.modules.associateWith { repositoryPath.resolve(it) },
                        target,
                        config,
                        sourceProcess,
                        folder.resolve("product-inventory-source.json"),
                        output,
                        if (target == "jsSafari") {
                            (lane["safari_karma_configs"] as JsonObject).keys.associateWith { module ->
                                Py.str(
                                    ((lane["safari_karma_configs"] as JsonObject).getValue(module)
                                        as JsonObject)["input_path"],
                                )!!
                            }
                        } else {
                            null
                        },
                    )
                    for ((module, product) in sourceExecutables) {
                        FullHostedRuntime.archiveTestProduct(product, output, config, module, target)
                    }
                    lane["source_executables"] = JsonObject(
                        sourceExecutables.mapValues { (_, value) -> JsonObject(value) },
                    )
                    lane["source"] = JsonArray(
                        FullHostedRuntime.copyReports(
                            repositoryPath,
                            target,
                            folder,
                            sourceProcess,
                            manifest,
                            Py.str(runtime["safari_version"]),
                            lane,
                        ),
                    )
                    val consumer = repositoryPath.resolve("consumers/qualification/portable")
                    val consumerDirectory = consumer.resolve("build/test-results").resolve(task)
                    if (Files.isDirectory(consumerDirectory)) {
                        Files.newDirectoryStream(consumerDirectory).use { stream ->
                            stream.filter {
                                it.fileName.toString().startsWith("TEST-") &&
                                    it.fileName.toString().endsWith(".xml")
                            }.forEach { Files.deleteIfExists(it) }
                        }
                    }
                    val consumerCommand = mutableListOf(
                        wrapper, "-p", consumer.toString(), "--no-daemon", "--console=plain",
                        "--rerun-tasks",
                    )
                    consumerCommand.addAll(args)
                    consumerCommand.add(task)
                    consumerCommand.add("-PqualificationRepository=$staging")
                    consumerCommand.add("-PqualificationInvocationId=$invocation")
                    if (target == "jsSafari") {
                        consumerCommand.add("-PqualificationSafari=true")
                        if (config == "production") {
                            consumerCommand.add("-PqualificationProduction=true")
                        }
                    }
                    if (target == "jsSafari") {
                        val stagedConsumer = SafariReporterHost.stage(
                            repositoryPath,
                            candidateSha,
                            listOf("consumers/qualification/portable"),
                            folder,
                        ) {
                            lane["consumer_process"] = FullHostedRuntime.runCommand(
                                consumerCommand,
                                repositoryPath,
                                folder.resolve("consumer"),
                                invocation,
                            )
                        }
                        lane["safari_reporter_stage"] = stageResult(lane, "consumer", stagedConsumer)
                        if (Py.str(stagedConsumer["status"]) != "CLEAN") {
                            throw IllegalArgumentException("staged Safari consumer reporter changed")
                        }
                        (lane["safari_karma_configs"] as JsonObject).let { configs ->
                            val merged = LinkedHashMap<String, JsonElement>(configs)
                            merged["consumer"] = FullHostedRuntime.captureSafariConfig(
                                repositoryPath,
                                candidateSha,
                                "consumers/qualification/portable",
                                config,
                                lane["consumer_process"] as JsonObject,
                                output,
                                "$config/karma-config/consumer/karma.conf.js",
                            )
                            lane["safari_karma_configs"] = JsonObject(merged)
                        }
                    } else {
                        lane["consumer_process"] = FullHostedRuntime.runCommand(
                            consumerCommand,
                            repositoryPath,
                            folder.resolve("consumer"),
                            invocation,
                        )
                    }
                    val consumerProcess = lane["consumer_process"] as JsonObject
                    FullHostedRuntime.requireTestTasks(
                        consumerProcess,
                        folder.resolve("consumer"),
                        target,
                        config,
                        listOf(""),
                    )
                    val consumerProducts = FullHostedRuntime.collectTestProducts(
                        mapOf("consumer" to consumer),
                        target,
                        config,
                        consumerProcess,
                        folder.resolve("product-inventory-consumer.json"),
                        output,
                        if (target == "jsSafari") {
                            mapOf(
                                "consumer" to Py.str(
                                    (((lane["safari_karma_configs"] as JsonObject)
                                        .getValue("consumer") as JsonObject)["input_path"]),
                                )!!,
                            )
                        } else {
                            null
                        },
                    )
                    val consumerProduct = consumerProducts.getValue("consumer")
                    FullHostedRuntime.archiveTestProduct(consumerProduct, output, config, "consumer", target)
                    lane["consumer_executable"] = JsonObject(consumerProduct)
                    lane["consumer"] = FullHostedRuntime.captureConsumer(
                        repositoryPath,
                        target,
                        folder,
                        consumerProcess,
                    ).toJson("consumer")
                    val graphInit = folder.resolve("qualification-graph.init.gradle")
                    Fs.writeText(graphInit, FullHostedRules.graphScript(target))
                    val graphCommand = listOf(
                        wrapper, "-p", consumer.toString(), "--no-daemon", "--console=plain",
                        "--init-script", graphInit.toString(), "qualificationResolvedGraph",
                        "-PqualificationRepository=$staging",
                        "-PqualificationInvocationId=$invocation",
                    )
                    val graphProcess = FullHostedRuntime.runCommand(
                        graphCommand,
                        repositoryPath,
                        folder.resolve("graph"),
                        invocation,
                    )
                    lane["graph_process"] = graphProcess
                    val graph = FullHostedRuntime.parseGraph(
                        folder.resolve("graph"),
                        graphProcess,
                        target,
                        receipt["artifact_hashes"] as JsonObject,
                        staging.toString(),
                        expectedHome = FullHosted.expectedGradleHome(target, JsonObject(receipt)),
                        stagedRoot = output.resolve("staged"),
                    )
                    lane["consumer_graph"] = graph
                    if ("gradle_user_home" !in receipt) {
                        receipt["gradle_user_home"] = graph["gradle_user_home"] ?: JsonNull
                    }
                    val resolved = mutableListOf<JsonElement>()
                    for ((index, element) in (graph["artifacts"] as JsonArray).withIndex()) {
                        val item = element as JsonObject
                        val name = "$config/resolved-artifacts/" +
                            "${index.toString().padStart(3, '0')}-${Py.str(item["name"])}"
                        val archived = FullHosted.archiveCopy(
                            Path.of(Py.str(item["file"])!!), output, name,
                        )
                        if (Py.str(archived["sha256"]) != Py.str(item["sha256"]) ||
                            !Py.equalsInt(archived["size"], Py.int(item["size"]!!))
                        ) {
                            throw IllegalArgumentException(
                                "resolved dependency changed after graph observation",
                            )
                        }
                        resolved.add(JsonObject(item + ("archive_path" to JsonPrimitive(name))))
                    }
                    lane["resolved_artifacts"] = JsonArray(resolved)
                    if (simulatorUdid != null) {
                        lane["simulator_udid"] = JsonPrimitive(simulatorUdid)
                    }
                    lane["status"] = JsonPrimitive("FULL_COMMON_PASSED")
                    lanes.add(JsonObject(lane))
                } catch (error: Exception) {
                    lane["status"] = JsonPrimitive("FAILED")
                    lane["reason"] = JsonPrimitive(error.message ?: error.toString())
                    lanes.add(JsonObject(lane))
                }
                receipt["configurations"] = JsonArray(lanes)
            }
            FullHostedRuntime.loadCorpus(repositoryPath, candidateSha)
            if (lanes.all { Py.str((it as JsonObject)["status"]) == "FULL_COMMON_PASSED" }) {
                receipt["status"] = JsonPrimitive("FULL_COMMON_PASSED")
                receipt["reason"] = JsonPrimitive(
                    "source-derived common core and facade cases and staged consumers ran",
                )
                receipt["files"] = JsonArray(FullHosted.archiveInventory(output))
                FullHosted.verifyRawFiles(output, JsonObject(receipt), manifest)
            } else {
                receipt["status"] = JsonPrimitive("FAILED")
                receipt["reason"] = JsonPrimitive("one or more hosted configurations failed")
            }
        } catch (error: Exception) {
            if (!isCaught(error)) throw error
            receipt["status"] = JsonPrimitive("FAILED")
            receipt["reason"] = JsonPrimitive(error.message ?: error.toString())
            if (lanes.isNotEmpty()) {
                val last = lanes.removeAt(lanes.size - 1) as JsonObject
                lanes.add(JsonObject(last + ("status" to JsonPrimitive("FAILED"))))
                receipt["configurations"] = JsonArray(lanes)
            }
        } finally {
            if (target == "jsSafari" && Py.str(receipt["status"]) != "FULL_COMMON_PASSED") {
                receipt["files"] = JsonArray(FullHosted.archiveInventory(output))
            }
            Fs.writeText(
                output.resolve("receipt.json"),
                PyJson.renderSorted(JsonObject(receipt)) + "\n",
            )
        }
        return JsonObject(receipt)
    }

    /** Records one Safari reporter stage result under its phase key. */
    private fun stageResult(
        lane: LinkedHashMap<String, JsonElement>,
        phase: String,
        staged: JsonObject,
    ): JsonObject {
        val current = lane["safari_reporter_stage"] as? JsonObject ?: JsonObject(emptyMap())
        return JsonObject(current + (phase to staged))
    }

    /**
     * The reference's caught failure set: `ImportError, OSError, ValueError, KeyError,
     * CalledProcessError, ParseError`. The port's helpers raise `IllegalArgumentException` for the
     * reference's `ValueError`/`KeyError` and `IOException` for `OSError`.
     */
    private fun isCaught(error: Exception): Boolean = when (error) {
        is IllegalArgumentException, is java.io.IOException, is NoSuchElementException,
        is ClassCastException, is HostedXmlError -> true
        else -> false
    }
}
