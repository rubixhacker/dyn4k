package io.github.rubixhacker.harness.qualification

import io.github.rubixhacker.harness.contract.StrictJson
import io.github.rubixhacker.harness.host.CleanCheckout
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.StandardCopyOption
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

/**
 * `duplicate_provider.py`: capture the staged consumer's rejection of two providers.
 *
 * The capture copies the exact staged JVM binaries, resolves the consumer dependency graph,
 * runs the single-provider task, and records a receipt whose inventory seals every file. The
 * gate later re-reads this receipt with [IndependentGates.inventory].
 */
object DuplicateProvider {
    const val LANE = "jvm:Java:current:default"

    /** `run_capture`. */
    fun runCapture(
        repositoryInput: Path,
        candidateSha: String,
        stagingInput: Path,
        auditPath: Path,
        output: Path,
    ): JsonObject {
        val repository = repositoryInput.toAbsolutePath().normalize()
        val staging = stagingInput.toAbsolutePath().normalize()
        CleanCheckout.require(repository.toFile(), candidateSha)
        val audit = StrictJson.load(Fs.readText(auditPath)) as? JsonObject
            ?: throw IllegalArgumentException(
                "duplicate provider requires a passing exact-source staging audit",
            )
        if (Py.str(audit["candidate_sha"]) != candidateSha || Py.str(audit["status"]) != "PASSED") {
            throw IllegalArgumentException(
                "duplicate provider requires a passing exact-source staging audit",
            )
        }
        StagingAudit.verifyAuditAgainstStaging(audit, repository)
        val hashes = TargetBinaryHashes.of(audit["artifacts"])[ "jvm" ] ?: emptyMap()
        val sourceTree = git(repository, "rev-parse", "$candidateSha^{tree}").trim()
        if (Files.exists(output)) {
            throw IllegalArgumentException("duplicate provider output already exists")
        }
        Files.createDirectories(output)
        val started = System.currentTimeMillis() * 1_000_000
        Files.createDirectory(output.resolve("artifacts"))
        for (module in listOf("dyn4k-core", "dyn4k")) {
            val source = staging.resolve(
                io.github.rubixhacker.harness.contract.Qualification.targetBinaryPath(module, "jvm"),
            )
            val destination = output.resolve("artifacts").resolve("$module.jar")
            Files.copy(source, destination, StandardCopyOption.REPLACE_EXISTING)
            if (CorpusFiles.digest(destination) != hashes[module]) {
                throw IllegalArgumentException("duplicate provider staged binary differs: $module")
            }
        }
        val base = listOf(
            "./gradlew", "-p", "consumers/qualification", "--no-daemon", "--console=plain",
            "-PqualificationRepository=${staging}", "-PwithUpstream=true",
        )
        val graphCommand = base + listOf("dependencies", "--configuration", "runtimeClasspath")
        val graph = run(graphCommand, repository)
        Fs.writeBytes(output.resolve("graph.log"), graph.output)
        Fs.writeText(
            output.resolve("graph-command.json"),
            PyJson.renderDefault(
                buildJsonObject {
                    put("command", JsonArray(graphCommand.map { JsonPrimitive(it) }))
                    put("exit_code", JsonPrimitive(graph.exitCode))
                },
            ) + "\n",
        )
        val command = base + listOf("verifySingleProvider")
        val task = run(command, repository)
        Fs.writeBytes(output.resolve("task.raw.log"), task.output)
        val runtime = run(listOf("java", "-version"), repository)
        Fs.writeBytes(output.resolve("runtime.log"), runtime.output)
        val graphHash = CorpusFiles.digest(output.resolve("graph.log"))
        val outputText = "QUALIFICATION_LANE=$LANE\n".toByteArray() + task.output +
            "\nQUALIFICATION_PROVIDER_GRAPH_SHA256=$graphHash\n".toByteArray()
        Fs.writeBytes(output.resolve("task.log"), outputText)

        val graphText = graph.output.toString(StandardCharsets.UTF_8)
        val graphHasDuplicate = try {
            io.github.rubixhacker.harness.contract.Qualification.checkProviders(graphText)
            false
        } catch (error: IllegalArgumentException) {
            "duplicate org.dyn4j provider" in (error.message ?: "")
        }
        val taskText = task.output.toString(StandardCharsets.ISO_8859_1)
        val diagnostic = "duplicate org.dyn4j provider" in taskText
        val succeeded = graph.exitCode == 0 && graphHasDuplicate && task.exitCode != 0 &&
            diagnostic && runtime.exitCode == 0 &&
            "> Task :verifySingleProvider" in taskText &&
            "BUILD FAILED" in taskText
        val finished = System.currentTimeMillis() * 1_000_000
        val paths = Files.walk(output).use { stream ->
            stream.filter { Files.isRegularFile(it) }.toList()
        }.map { output.relativize(it) }.sortedWith { left, right ->
            CanonicalText.compare(left.toString(), right.toString())
        }
        val files = JsonArray(
            paths.map { relative ->
                val path = output.resolve(relative)
                buildJsonObject {
                    put("path", JsonPrimitive(relative.toString().replace('\\', '/')))
                    put("sha256", JsonPrimitive(CorpusFiles.digest(path)))
                    put("mtime_ns", JsonPrimitive(Files.getLastModifiedTime(path).to(java.util.concurrent.TimeUnit.NANOSECONDS)))
                }
            },
        )
        val receipt = buildJsonObject {
            put("schema", JsonPrimitive(1))
            put("status", JsonPrimitive(if (succeeded) "PASSED" else "FAILED"))
            put("candidate_sha", JsonPrimitive(candidateSha))
            put("source_tree", JsonPrimitive(sourceTree))
            put("lane", JsonPrimitive(LANE))
            put("target", JsonPrimitive("jvm"))
            put("runtime", JsonPrimitive("Java"))
            put("version", JsonPrimitive("current"))
            put("configuration", JsonPrimitive("default"))
            put(
                "runtime_identity",
                JsonPrimitive(runtime.output.toString(StandardCharsets.UTF_8).trim()),
            )
            put("artifact_hashes", JsonObject(hashes.mapValues { JsonPrimitive(it.value ?: "") }))
            put(
                "process",
                buildJsonObject {
                    put("command", JsonArray(command.map { JsonPrimitive(it) }))
                    put("exit_code", JsonPrimitive(task.exitCode))
                    put("started_ns", JsonPrimitive(started))
                    put("finished_ns", JsonPrimitive(finished))
                    put("stdout", JsonPrimitive("task.log"))
                    put("stderr", JsonPrimitive("task.raw.log"))
                },
            )
            put("provider_graph", JsonPrimitive("graph.log"))
            put("files", files)
        }
        Fs.writeText(output.resolve("receipt.json"), PyJson.render(receipt) + "\n")
        IndependentGates.inventory(output, receipt)
        return receipt
    }

    private class Completed(val exitCode: Int, val output: ByteArray)

    private fun run(command: List<String>, directory: Path): Completed {
        val builder = ProcessBuilder(command).directory(directory.toFile()).redirectErrorStream(true)
        val process = builder.start()
        val output = process.inputStream.use { it.readBytes() }
        return Completed(process.waitFor(), output)
    }

    private fun git(repository: Path, vararg arguments: String): String {
        val process = ProcessBuilder(
            listOf("git", "--no-replace-objects", "-C", repository.toString()) + arguments,
        ).start()
        val output = process.inputStream.use { it.readBytes() }
        process.errorStream.close()
        if (process.waitFor() != 0) throw IllegalArgumentException("git failed")
        return output.toString(StandardCharsets.UTF_8)
    }
}

/** `duplicate_provider.main`. */
object DuplicateProviderCli {
    @JvmStatic
    fun main(arguments: Array<String>) {
        System.exit(run(arguments))
    }

    fun run(arguments: Array<String>): Int {
        var repository: Path? = null
        var candidateSha: String? = null
        var staging: Path? = null
        var audit: Path? = null
        var output: Path? = null
        var index = 0
        while (index < arguments.size) {
            when (arguments[index]) {
                "--repository" -> repository = Path.of(arguments[++index])
                "--candidate-sha" -> candidateSha = arguments[++index]
                "--staging-repository" -> staging = Path.of(arguments[++index])
                "--audit" -> audit = Path.of(arguments[++index])
                "--output" -> output = Path.of(arguments[++index])
                else -> return usage("unexpected argument: ${arguments[index]}")
            }
            index++
        }
        if (repository == null || candidateSha == null || staging == null || audit == null ||
            output == null
        ) {
            return usage("--repository, --candidate-sha, --staging-repository, --audit, and --output are required")
        }
        return try {
            val result = DuplicateProvider.runCapture(repository, candidateSha, staging, audit, output)
            println(
                PyJson.renderDefault(
                    buildJsonObject {
                        put("status", result.getValue("status"))
                        put("candidate_sha", result.getValue("candidate_sha"))
                        put("task_exit", (result["process"] as JsonObject).getValue("exit_code"))
                    },
                ),
            )
            if (Py.str(result["status"]) == "PASSED") 0 else 1
        } catch (error: Exception) {
            Files.createDirectories(output)
            Fs.writeText(output.resolve("capture-error.txt"), (error.message ?: "") + "\n")
            1
        }
    }

    private fun usage(message: String): Int {
        System.err.println("usage error: $message")
        return 2
    }
}
