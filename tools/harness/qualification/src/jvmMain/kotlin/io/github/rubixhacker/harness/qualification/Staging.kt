package io.github.rubixhacker.harness.qualification

import io.github.rubixhacker.harness.host.CleanCheckout
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.Path
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

/**
 * `stage.run_stage`: run the staging publication tasks and record what happened.
 *
 * The receipt is written even when Gradle fails, so a failed staging run is retained evidence
 * rather than a missing file. A passing exit status is re-verified against the console before the
 * receipt can claim `PASSED`.
 */
object Staging {
    fun run(
        repositoryInput: Path,
        candidateSha: String,
        targets: List<String>,
        output: Path,
        console: Path,
    ): JsonObject {
        val repository = repositoryInput.toAbsolutePath().normalize()
        CleanCheckout.require(repository.toFile(), candidateSha)
        val selected = targets.sortedWith(CanonicalText::compare)
        val tasks = StageReceipt.publicationTasks(selected)
        val command = StageReceipt.stageCommand(repository, tasks)
        console.parent?.let { Files.createDirectories(it) }
        val builder = ProcessBuilder(command)
            .directory(repository.toFile())
            .redirectErrorStream(true)
            .redirectOutput(console.toFile())
        val completed = builder.start()
        val exitCode = completed.waitFor()

        val receipt = LinkedHashMap<String, kotlinx.serialization.json.JsonElement>()
        receipt["candidate_sha"] = JsonPrimitive(candidateSha)
        receipt["repository"] = JsonPrimitive(repository.toString())
        receipt["targets"] = JsonArray(selected.map { JsonPrimitive(it) })
        receipt["tasks"] = JsonArray(tasks.map { JsonPrimitive(it) })
        receipt["command"] = JsonArray(command.map { JsonPrimitive(it) })
        receipt["exit_code"] = JsonPrimitive(exitCode)
        // Python hashes the bytes the task wrote, which are complete once the process exited.
        receipt["console_sha256"] = JsonPrimitive(Fs.digest(console))
        receipt["status"] = JsonPrimitive(if (exitCode == 0) "PASSED" else "FAILED")
        if (Py.str(receipt["status"]) == "PASSED") {
            try {
                StageReceipt.verify(JsonObject(receipt), console, candidateSha, selected, repository)
            } catch (error: IllegalArgumentException) {
                receipt["status"] = JsonPrimitive("FAILED")
                receipt["reason"] = JsonPrimitive(error.message ?: "")
            }
        }
        output.parent?.let { Files.createDirectories(it) }
        val document = JsonObject(receipt)
        Fs.writeText(output, PyJson.render(document) + "\n")
        return document
    }
}

/** `stage.main`: the command line of the staging task. */
object StageCli {
    fun run(arguments: Array<String>, repository: Path? = null): Int {
        var candidateSha: String? = null
        val targets = mutableListOf<String>()
        var output: Path? = null
        var console: Path? = null
        var index = 0
        while (index < arguments.size) {
            when (arguments[index]) {
                "--candidate-sha" -> candidateSha = arguments[++index]
                "--target" -> targets.add(arguments[++index])
                "--output" -> output = Path.of(arguments[++index])
                "--console" -> console = Path.of(arguments[++index])
                else -> return usage("unexpected argument: ${arguments[index]}")
            }
            index++
        }
        if (candidateSha == null || targets.isEmpty() || output == null || console == null) {
            return usage("--candidate-sha, --target, --output, and --console are required")
        }
        val root = repository ?: Path.of("").toAbsolutePath()
        val result = Staging.run(root, candidateSha, targets, output, console)
        println(PyJson.renderDefault(result))
        return if (Py.str(result["status"]) == "PASSED") 0 else 1
    }

    private fun usage(message: String): Int {
        System.err.println("usage error: $message")
        return 2
    }
}
