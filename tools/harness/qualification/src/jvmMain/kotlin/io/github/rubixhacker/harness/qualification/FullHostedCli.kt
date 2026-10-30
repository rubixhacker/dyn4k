package io.github.rubixhacker.harness.qualification

import io.github.rubixhacker.harness.contract.StrictJson
import java.nio.file.Files
import java.nio.file.Path
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

/**
 * `full_hosted.main`: the hosted full-corpus archive command line.
 *
 * The three verification modes (`--package`, `--verify-tar`, `--verify`) are ported. Execution
 * (`full_hosted.run`, the mode that drives both configurations on a hosted runner) is still the
 * Python reference, so that mode fails closed with status 2 instead of pretending to run.
 */
object FullHostedCli {
    @JvmStatic
    fun main(arguments: Array<String>) {
        System.exit(run(arguments))
    }

    fun run(arguments: Array<String>, repository: Path? = null): Int {
        var target: String? = null
        var candidateSha: String? = null
        var output: Path? = null
        var archive: Path? = null
        var verify = false
        var packageMode = false
        var verifyTar = false
        var index = 0
        while (index < arguments.size) {
            when (val argument = arguments[index]) {
                "--target" -> target = arguments[++index]
                "--candidate-sha" -> candidateSha = arguments[++index]
                "--output" -> output = Path.of(arguments[++index])
                "--archive" -> archive = Path.of(arguments[++index])
                "--verify" -> verify = true
                "--package" -> packageMode = true
                "--verify-tar" -> verifyTar = true
                else -> return usage("unexpected argument: $argument")
            }
            index++
        }
        val modes = listOf(verify, packageMode, verifyTar).count { it }
        if (modes > 1) return usage("argument --verify/--package/--verify-tar: not allowed with each other")
        if (packageMode) {
            if (output == null || archive == null) {
                return usage("--package requires --output and --archive")
            }
            FullHosted.packageArchive(output, archive)
            println(
                PyJson.renderDefault(
                    buildJsonObject {
                        put("archive", JsonPrimitive(archive.toString()))
                        put("packaged", JsonPrimitive(true))
                    },
                ),
            )
            return 0
        }
        if (verifyTar) {
            if (archive == null || target == null || candidateSha == null) {
                return usage("--verify-tar requires --archive, --target, and --candidate-sha")
            }
            val receipt = try {
                FullHosted.verifyTransportArchive(archive, candidateSha, target, repository)
            } catch (error: Exception) {
                return failure(error)
            }
            println(
                PyJson.renderDefault(
                    buildJsonObject {
                        put("status", receipt["status"] ?: JsonPrimitive(""))
                        put("verified", JsonPrimitive(true))
                    },
                ),
            )
            return 0
        }
        if (verify) {
            if (output == null) return usage("--verify requires --output")
            val receipt = try {
                StrictJson.load(Files.readString(output.resolve("receipt.json")))
            } catch (error: Exception) {
                return failure(error)
            }
            if (receipt !is JsonObject) {
                return failure(IllegalArgumentException("full hosted receipt must be an object"))
            }
            if ((target != null && target != Py.str(receipt["target"])) ||
                (candidateSha != null && candidateSha != Py.str(receipt["candidate_sha"]))
            ) {
                return failure(
                    IllegalArgumentException("verify target or candidate SHA differs from receipt"),
                )
            }
            try {
                FullHosted.verifyRawFiles(output, receipt)
            } catch (error: Exception) {
                return failure(error)
            }
            println(
                PyJson.renderDefault(
                    buildJsonObject {
                        put("status", receipt["status"] ?: JsonPrimitive(""))
                        put("verified", JsonPrimitive(true))
                    },
                ),
            )
            return 0
        }
        if (target == null || candidateSha == null || output == null) {
            return usage("--target, --candidate-sha, and --output are required for execution")
        }
        return usage(
            "execution is not ported: run full_hosted.py --target $target --candidate-sha " +
                "$candidateSha --output $output, or use --verify on its receipt",
        )
    }

    private fun failure(error: Exception): Int {
        System.err.println(error.message ?: error.toString())
        return 1
    }

    private fun usage(message: String): Int {
        System.err.println("usage error: $message")
        return 2
    }
}
