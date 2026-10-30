package io.github.rubixhacker.harness.qualification

import java.nio.file.Files
import java.nio.file.Path
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

/**
 * `collection.main`: the 112-lane collection command line.
 *
 * ```
 * collection --repository DIR --candidate-sha SHA --artifacts-dir DIR --output DIR
 *            [--upstream DIR] [--source-index FILE] [--repository-name OWNER/NAME]
 *            [--run-id N] [--run-attempt N]
 * collection --repository DIR --candidate-sha SHA --artifacts-dir DIR --output DIR
 *            --audit-input-dir DIR [--trusted-key-sha256 HEX]
 *            [--independent-performance-key FILE] [--performance-key-sha256 HEX]
 * collection --verify --repository DIR --candidate-sha SHA --artifacts-dir DIR --output DIR
 * ```
 *
 * Every form requires `--repository`, `--candidate-sha`, `--artifacts-dir`, and `--output`; the
 * artifact set is the sorted listing of `--artifacts-dir`, as the reference takes it.
 */
object CollectionCli {
    @JvmStatic
    fun main(arguments: Array<String>) {
        System.exit(run(arguments))
    }

    fun run(arguments: Array<String>): Int {
        var repository: Path? = null
        var candidateSha: String? = null
        var artifactsDir: Path? = null
        var output: Path? = null
        var upstream: Path? = null
        var sourceIndex: Path? = null
        var repositoryName = "rubixhacker/dyn4k"
        var runId: Long? = null
        var runAttempt: Long? = null
        var auditInputDir: Path? = null
        var trustedKeySha256: String? = null
        var performanceKey: Path? = null
        var performanceKeySha256: String? = null
        var verify = false
        var index = 0
        while (index < arguments.size) {
            when (val argument = arguments[index]) {
                "--repository" -> repository = Path.of(arguments[++index])
                "--candidate-sha" -> candidateSha = arguments[++index]
                "--artifacts-dir" -> artifactsDir = Path.of(arguments[++index])
                "--output" -> output = Path.of(arguments[++index])
                "--upstream" -> upstream = Path.of(arguments[++index])
                "--source-index" -> sourceIndex = Path.of(arguments[++index])
                "--repository-name" -> repositoryName = arguments[++index]
                "--run-id" -> runId = arguments[++index].toLongOrNull()
                    ?: return usage("argument --run-id: invalid int value")
                "--run-attempt" -> runAttempt = arguments[++index].toLongOrNull()
                    ?: return usage("argument --run-attempt: invalid int value")
                "--audit-input-dir" -> auditInputDir = Path.of(arguments[++index])
                "--trusted-key-sha256" -> trustedKeySha256 = arguments[++index]
                "--independent-performance-key" ->
                    performanceKey = Path.of(arguments[++index])
                "--performance-key-sha256" -> performanceKeySha256 = arguments[++index]
                "--verify" -> verify = true
                else -> return usage("unexpected argument: $argument")
            }
            index++
        }
        if (repository == null) return usage("--repository is required")
        if (candidateSha == null) return usage("--candidate-sha is required")
        if (artifactsDir == null) return usage("--artifacts-dir is required")
        if (output == null) return usage("--output is required")
        val artifacts = Files.newDirectoryStream(artifactsDir).use { stream ->
            stream.map { it.fileName.toString() to it.toString() }.toList()
        }.sortedWith { left, right -> CanonicalText.compare(left.first, right.first) }
        if (verify) {
            CollectionRuntime.verifyCollection(repository, candidateSha, artifacts, output)
            println(
                PyJson.renderDefault(
                    buildJsonObject {
                        put("candidate_sha", JsonPrimitive(candidateSha))
                        put("transport", JsonPrimitive("VERIFIED"))
                    },
                ),
            )
            return 0
        }
        if (auditInputDir != null) {
            val result: JsonObject = try {
                CollectionRuntime.ingestExternal(
                    repository,
                    candidateSha,
                    artifacts,
                    output,
                    auditInputDir,
                    trustedKeySha256,
                    performanceKey,
                    performanceKeySha256,
                )
            } catch (error: Exception) {
                if (error !is IllegalArgumentException && error !is java.io.IOException &&
                    error !is NoSuchElementException && error !is ClassCastException
                ) {
                    throw error
                }
                val failed = buildJsonObject {
                    put("candidate_sha", JsonPrimitive(candidateSha))
                    put("status", JsonPrimitive("FAILED"))
                    put("reason", JsonPrimitive(error.message ?: error.toString()))
                }
                Files.createDirectories(output)
                Fs.writeText(output.resolve("audit-ingestion.json"), PyJson.render(failed) + "\n")
                failed
            }
            println(PyJson.renderDefault(result))
            return if (Py.str(result["status"]) == "PASSED") 0 else 1
        }
        val report = CollectionRuntime.collect(
            repository,
            candidateSha,
            artifacts,
            output,
            upstream,
            sourceIndex,
            repositoryName,
            runId,
            runAttempt,
            System.getenv("DYN4K_GITHUB_TOKEN"),
            artifactsDir,
        )
        println(
            PyJson.renderDefault(
                buildJsonObject {
                    put("candidate_sha", report["candidate_sha"] ?: JsonNull)
                    put("status", report["status"] ?: JsonNull)
                    put("missing_artifacts", report["missing_artifacts"] ?: JsonNull)
                },
            ),
        )
        return if (Py.str(report["status"]) == "PASSED") 0 else 1
    }

    private fun usage(message: String): Int {
        System.err.println("usage error: $message")
        return 2
    }
}
