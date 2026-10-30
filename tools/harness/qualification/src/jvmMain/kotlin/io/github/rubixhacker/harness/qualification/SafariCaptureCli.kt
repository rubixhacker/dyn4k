package io.github.rubixhacker.harness.qualification

import java.nio.file.Path
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

/**
 * `safari_yarn_lock.main`: capture or audit a Kotlin/JS Yarn lock diagnostic.
 *
 * Invocation forms (the reference's own parser):
 *
 * ```
 * --candidate-sha <sha> --output <dir>                      # capture, no hosted configuration
 * --candidate-sha <sha> --output <dir> --configuration development|production
 * --candidate-sha <sha> --output <dir> --audit              # audit an existing capture
 * --candidate-sha <sha> --output <dir> --input-context <raw> --capture-context
 * ```
 *
 * The context scan is ported as [SafariContext.captureKarmaContext]: it writes the inventory next to
 * the copied configurations and sidecars, prints the same four-field summary, and exits non-zero
 * unless the inventory says `CONTEXT_COMPLETE`.
 */
object SafariCaptureCli {
    @JvmStatic
    fun main(arguments: Array<String>) {
        System.exit(run(arguments))
    }

    fun run(arguments: Array<String>, repository: Path? = null): Int {
        var candidateSha: String? = null
        var output: Path? = null
        var configuration: String? = null
        var audit = false
        var inputContext: Path? = null
        var captureContext = false
        var index = 0
        while (index < arguments.size) {
            when (val argument = arguments[index]) {
                "--candidate-sha" -> candidateSha = next(arguments, ++index) ?: return usage(
                    "argument --candidate-sha: expected one argument",
                )
                "--output" -> output = next(arguments, ++index)?.let { Path.of(it) } ?: return usage(
                    "argument --output: expected one argument",
                )
                "--configuration" -> {
                    configuration = next(arguments, ++index) ?: return usage(
                        "argument --configuration: expected one argument",
                    )
                    if (configuration != "development" && configuration != "production") {
                        return usage(
                            "argument --configuration: invalid choice: '$configuration' " +
                                "(choose from 'development', 'production')",
                        )
                    }
                }
                "--audit" -> audit = true
                "--input-context" -> inputContext =
                    next(arguments, ++index)?.let { Path.of(it) } ?: return usage(
                        "argument --input-context: expected one argument",
                    )
                "--capture-context" -> captureContext = true
                else -> return usage("unrecognized arguments: $argument")
            }
            index++
        }
        if (candidateSha == null) return usage("the following arguments are required: --candidate-sha")
        if (output == null) return usage("the following arguments are required: --output")
        val root = repository ?: Path.of("").toAbsolutePath()
        if (captureContext) {
            if (audit || configuration != null || inputContext == null) {
                return usage("context scan requires input context and cannot audit or run Gradle")
            }
            val inventory = try {
                SafariContext.captureKarmaContext(root, candidateSha, output, inputContext)
            } catch (error: Exception) {
                System.err.println(error.message ?: error.toString())
                return 1
            }
            val status = Py.str(inventory["status"])
            println(
                PyJson.renderDefault(
                    buildJsonObject {
                        put("candidate_sha", inventory["candidate_sha"] ?: JsonNull)
                        put("status", status?.let { JsonPrimitive(it) } ?: JsonNull)
                        put("qualified", JsonPrimitive(false))
                        put("output", JsonPrimitive(output.toString()))
                    },
                ),
            )
            return if (status == SafariContextRules.COMPLETE) 0 else 1
        }
        if (inputContext != null) {
            return usage("input context requires --capture-context")
        }
        val receipt = try {
            if (audit) {
                SafariCapture.auditCapture(root, candidateSha, output)
            } else {
                SafariCapture.capture(root, candidateSha, output, configuration)
            }
        } catch (error: Exception) {
            System.err.println(error.message ?: error.toString())
            return 1
        }
        val status = Py.str(receipt["status"])
        println(
            PyJson.renderDefault(
                buildJsonObject {
                    put("candidate_sha", receipt["candidate_sha"] ?: JsonNull)
                    put("status", status?.let { JsonPrimitive(it) } ?: JsonNull)
                    put("qualified", JsonPrimitive(false))
                    put("output", JsonPrimitive(output.toString()))
                },
            ),
        )
        return if (status == "LOCK_MISMATCH_CAPTURED" || status == "LOCK_MATCHED_DIAGNOSTIC_ONLY") {
            0
        } else {
            1
        }
    }

    private fun next(arguments: Array<String>, index: Int): String? =
        if (index < arguments.size) arguments[index] else null

    private fun usage(message: String): Int {
        System.err.println("usage error: $message")
        return 2
    }
}
