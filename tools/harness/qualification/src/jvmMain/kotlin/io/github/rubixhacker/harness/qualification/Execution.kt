package io.github.rubixhacker.harness.qualification

import io.github.rubixhacker.harness.contract.Qualification
import io.github.rubixhacker.harness.contract.StrictJson
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.Path
import java.util.UUID
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

/**
 * `qualify.execute_plan`.
 *
 * Each planned lane runs once with a fresh invocation ID in its environment. A previous result
 * file is moved aside, so a no-op command cannot leave a stale result in place; the result must be
 * a strict JSON object that echoes the invocation ID this run generated.
 */
object Execution {
    fun executePlan(plan: JsonObject, candidateSha: String, output: Path): JsonObject {
        val evidence = LinkedHashMap<String, JsonElement>()
        for (case in Qualification.expand()) {
            val specification = plan[case.id] as? JsonObject ?: continue
            val unavailable = specification["unavailable_reason"]
            if (Py.truthy(unavailable)) {
                evidence[case.id] = JsonObject(linkedMapOf("unavailable_reason" to unavailable!!))
                continue
            }
            val commandElement = specification["command"]
            if (commandElement !is JsonArray || commandElement.isEmpty()) {
                evidence[case.id] = error("no executable command")
                continue
            }
            val command = commandElement.mapNotNull { Py.str(it) }
            val resultName = Py.str(specification["result_file"])
            if (resultName.isNullOrEmpty()) {
                evidence[case.id] = error("result file path is missing")
                continue
            }
            val resultFile = Path.of(resultName)
            if (Files.isDirectory(resultFile)) {
                evidence[case.id] = error("result file path is a directory")
                continue
            }
            val invocationId = UUID.randomUUID().toString().replace("-", "")
            var previous: Path? = null
            if (Files.exists(resultFile) || Files.isSymbolicLink(resultFile)) {
                previous = resultFile.resolveSibling("${resultFile.fileName}.previous-$invocationId")
                Files.move(resultFile, previous)
            }
            val builder = ProcessBuilder(command)
            for ((key, value) in System.getenv()) builder.environment()[key] = value
            builder.environment()["DYN4K_QUALIFICATION_INVOCATION"] = invocationId
            val process = builder.start()
            // Drain stdout on a helper thread while stderr is read, so neither pipe can block.
            val drain = Thread { process.inputStream.use { it.readBytes() } }
            drain.start()
            val stderr = process.errorStream.use { it.readBytes() }
            val status = process.waitFor()
            drain.join()
            if (status != 0 || !Files.isRegularFile(resultFile) || Files.isSymbolicLink(resultFile)) {
                val detail = String(stderr, StandardCharsets.UTF_8)
                evidence[case.id] = buildJsonObject {
                    put("error", JsonPrimitive("command failed or result file missing"))
                    put("exit_code", JsonPrimitive(status))
                    put("stderr", JsonPrimitive(detail.takeLast(4000)))
                    put("previous_result", previous?.let { JsonPrimitive(it.toString()) } ?: JsonNull)
                }
                continue
            }
            val observed = try {
                StrictJson.load(Fs.readText(resultFile))
            } catch (error: Exception) {
                evidence[case.id] = buildJsonObject {
                    put("error", JsonPrimitive("invalid result JSON: ${error.message}"))
                    put("exit_code", JsonPrimitive(status))
                }
                continue
            }
            if (observed !is JsonObject || Py.str(observed["invocation_id"]) != invocationId) {
                evidence[case.id] = buildJsonObject {
                    put("error", JsonPrimitive("result invocation ID differs from execution"))
                    put("exit_code", JsonPrimitive(status))
                }
                continue
            }
            val merged = LinkedHashMap(observed)
            merged["command"] = JsonArray(command.map { JsonPrimitive(it) })
            merged["exit_code"] = JsonPrimitive(status)
            evidence[case.id] = JsonObject(merged)
        }
        val result = JsonObject(evidence)
        Fs.writeText(output, PyJson.render(result) + "\n")
        return result
    }

    private fun error(message: String): JsonObject =
        JsonObject(linkedMapOf("error" to JsonPrimitive(message)))
}

/** `qualify.main` action `execute`: validates the plan and reports whether every lane ran. */
object ExecutionCli {
    /** Entry point of the `executePlan` task. */
    @JvmStatic
    fun main(arguments: Array<String>) {
        System.exit(run(arguments))
    }

    fun run(arguments: Array<String>): Int {
        var candidateSha: String? = null
        var plan: Path? = null
        var output: Path? = null
        var index = 0
        while (index < arguments.size) {
            when (arguments[index]) {
                "--candidate-sha" -> candidateSha = arguments[++index]
                "--plan" -> plan = Path.of(arguments[++index])
                "--output" -> output = Path.of(arguments[++index])
                else -> return usage("unexpected argument: ${arguments[index]}")
            }
            index++
        }
        if (candidateSha == null || plan == null || output == null) {
            return usage("--candidate-sha, --plan, and --output are required")
        }
        if (!Py.SHA40.matches(candidateSha)) return usage("candidate SHA must be a full commit hash")
        val document = StrictJson.load(Fs.readText(plan)) as? JsonObject
            ?: return usage("plan must be an object")
        val validIds = Qualification.expand().map { it.id }.toSet()
        val unknown = document.keys - validIds
        if (unknown.isNotEmpty()) {
            System.err.println("unknown lane: ${unknown.sortedWith(CanonicalText::compare).joinToString(", ")}")
            return 2
        }
        val evidence = Execution.executePlan(document, candidateSha, output)
        return if (ProbeManifest.executionSucceeded(evidence)) 0 else 1
    }

    private fun usage(message: String): Int {
        System.err.println("usage error: $message")
        return 2
    }
}
