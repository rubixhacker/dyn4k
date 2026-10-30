package io.github.rubixhacker.harness.qualification

import io.github.rubixhacker.harness.contract.StrictJson
import io.github.rubixhacker.harness.host.CleanCheckout
import java.nio.file.Files
import java.nio.file.Path
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

/**
 * `artifact.main`: package and verify complete bounded XML evidence.
 *
 * ```
 * artifact hosted --candidate-sha SHA --target TARGET --probe PROBE [--matrix MATRIX] --output DIR
 * artifact ubuntu --candidate-sha SHA --evidence-dir DIR --output DIR
 * artifact verify --candidate-sha SHA --output DIR
 * artifact verify --candidate-sha SHA --output BUNDLE.tar      (or a hosted receipt directory)
 * artifact verify --candidate-sha SHA --output DIR --full-hosted
 * ```
 *
 * `--full-hosted` is the only mode that accepts a hosted full-corpus receipt directory or its
 * transport archive, and `--full-hosted` may only be used with `verify`.
 */
object ArtifactCli {
    @JvmStatic
    fun main(arguments: Array<String>) {
        System.exit(run(arguments))
    }

    fun run(arguments: Array<String>, repository: Path? = null): Int {
        var action: String? = null
        var candidateSha: String? = null
        var target: String? = null
        var probe: Path? = null
        var matrix: Path? = null
        var evidenceDir: Path? = null
        var output: Path? = null
        var fullHosted = false
        var index = 0
        while (index < arguments.size) {
            when (val argument = arguments[index]) {
                "--candidate-sha" -> candidateSha = arguments[++index]
                "--target" -> target = arguments[++index]
                "--probe" -> probe = Path.of(arguments[++index])
                "--matrix" -> matrix = Path.of(arguments[++index])
                "--evidence-dir" -> evidenceDir = Path.of(arguments[++index])
                "--output" -> output = Path.of(arguments[++index])
                "--full-hosted" -> fullHosted = true
                else -> if (argument.startsWith("--")) {
                    return usage("unexpected argument: $argument")
                } else if (action == null) {
                    action = argument
                } else {
                    return usage("unexpected argument: $argument")
                }
            }
            index++
        }
        if (action == null) return usage("the action must be one of hosted, ubuntu, verify")
        if (action !in setOf("hosted", "ubuntu", "verify")) {
            return usage("argument action: invalid choice: '$action'")
        }
        if (candidateSha == null) return usage("--candidate-sha is required")
        if (output == null) return usage("--output is required")
        val root = repository ?: Path.of("").toAbsolutePath()
        CleanCheckout.require(root.toFile(), candidateSha)
        if (fullHosted ||
            (action == "verify" &&
                (output.fileName?.toString()?.endsWith(".tar") == true ||
                    Files.isRegularFile(output.resolve("receipt.json"))))
        ) {
            if (action != "verify") {
                return usage("full hosted archive supports verify only")
            }
            val result = try {
                ArtifactCapture.verifyFullHosted(output, candidateSha, root)
            } catch (error: Exception) {
                System.err.println("full hosted archive failed: ${error.message}")
                return 1
            }
            val configurations = (result["configurations"] as? JsonArray)?.size ?: 0
            println(
                PyJson.renderDefault(
                    buildJsonObject {
                        put("target", result["target"] ?: JsonNull)
                        put("status", result["status"] ?: JsonNull)
                        put("configurations", JsonPrimitive(configurations))
                    },
                ),
            )
            return 0
        }
        val manifest = StrictJson.load(
            Files.readString(root.resolve("tools/qualification/foundation-probes.json")),
        ) as? JsonObject
            ?: throw IllegalArgumentException("foundation probe manifest is not an object")
        val result = when (action) {
            "hosted" -> ArtifactCapture.stageHosted(
                root,
                manifest,
                candidateSha,
                target,
                probe ?: throw IllegalArgumentException("--probe is required for hosted"),
                matrix,
                output,
            )
            "ubuntu" -> ArtifactCapture.stageUbuntu(
                root,
                manifest,
                candidateSha,
                evidenceDir ?: throw IllegalArgumentException("--evidence-dir is required for ubuntu"),
                output,
            )
            else -> ArtifactCapture.verifyBundle(output, manifest, candidateSha)
        }
        println(
            PyJson.renderDefault(
                buildJsonObject {
                    put("route", result["route"] ?: JsonNull)
                    put("status", result["status"] ?: JsonNull)
                    put("executed", result["executed"] ?: JsonNull)
                    put("expected", result["expected"] ?: JsonNull)
                    put("reported", result["reported"] ?: JsonPrimitive(0))
                    put("reason", result["reason"] ?: JsonNull)
                },
            ),
        )
        return if (Py.str(result["status"]) == "PROBE_PASSED") 0 else 1
    }

    private fun usage(message: String): Int {
        System.err.println("usage error: $message")
        return 2
    }

    /** The recorded evidence of one bundle, for a caller that wants the object rather than text. */
    fun summary(result: JsonObject): Map<String, JsonElement> = mapOf(
        "route" to (result["route"] ?: JsonNull),
        "status" to (result["status"] ?: JsonNull),
        "executed" to (result["executed"] ?: JsonNull),
    )
}
