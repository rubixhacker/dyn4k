package io.github.rubixhacker.harness.qualification

import java.nio.file.Path
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

object FullJvmConsumerCli {
    @JvmStatic
    fun main(arguments: Array<String>) {
        try {
            System.exit(run(arguments))
        } catch (e: Exception) {
            System.err.println(e.message ?: e.toString())
            System.exit(1)
        }
    }

    fun run(arguments: Array<String>): Int {
        var index = 0
        if (index >= arguments.size) {
            usage("action required")
            return 2
        }
        val action = arguments[index++]
        val values = linkedMapOf<String, String>()
        while (index < arguments.size) {
            val arg = arguments[index++]
            if (!arg.startsWith("--")) {
                usage("unexpected argument: $arg")
                return 2
            }
            val name = arg.removePrefix("--")
            if (index >= arguments.size) {
                usage("argument $arg: expected one argument")
                return 2
            }
            values[name] = arguments[index++]
        }
        return try {
            if (action == "prepare") {
                val repo = Path.of(values["repository"] ?: throw IllegalArgumentException("missing --repository"))
                val candidate = values["candidate-sha"] ?: throw IllegalArgumentException("missing --candidate-sha")
                val dest = Path.of(values["destination"] ?: throw IllegalArgumentException("missing --destination"))
                val lane = values["lane"] ?: FullJvmConsumer.LANE
                val result = prepare(repo, candidate, dest, lane)
                println(io.github.rubixhacker.harness.contract.CanonicalJson.render(result))
                0
            } else if (action == "verify") {
                // For now, delegate to Python if needed - but better to implement basic verify
                val repo = Path.of(values["repository"] ?: throw IllegalArgumentException("missing --repository"))
                val candidate = values["candidate-sha"] ?: throw IllegalArgumentException("missing --candidate-sha")
                val archive = Path.of(values["archive"] ?: throw IllegalArgumentException("missing --archive"))
                val lane = values["lane"] ?: FullJvmConsumer.LANE
                val hashes = mapOf(
                    "dyn4k-core" to (values["expected-core-sha256"] ?: throw IllegalArgumentException("missing hash")),
                    "dyn4k" to (values["expected-facade-sha256"] ?: throw IllegalArgumentException("missing hash")),
                )
                val javaHash = values["expected-java-executable-sha256"]
                val gradleHash = values["expected-gradle-executable-sha256"]
                val runtimeHash = values["expected-runtime-java-executable-sha256"]
                if (javaHash == null || gradleHash == null || runtimeHash == null ||
                    !Py.SHA64.matches(javaHash) || !Py.SHA64.matches(gradleHash) || !Py.SHA64.matches(runtimeHash)
                ) {
                    throw IllegalArgumentException("independent Java and Gradle executable SHA-256 values are required")
                }
                val publication = values["mode-publication"]?.let { Path.of(it) }
                val pubDigest = values["expected-mode-publication-digest"]
                if (publication == null || pubDigest == null) {
                    throw IllegalArgumentException("independent JVM mode publication is required")
                }
                val identity = values["runtime-identity"] ?: ""
                val digest = values["expected-archive-digest"] ?: ""
                val result = verify(archive, repo, candidate, hashes, identity, digest, javaHash, gradleHash, runtimeHash, lane, publication, pubDigest)
                println(io.github.rubixhacker.harness.contract.CanonicalJson.render(result))
                0
            } else {
                usage("unknown action")
                2
            }
        } catch (e: Exception) {
            System.err.println("usage error: ${e.message}")
            2
        }
    }

    private fun usage(msg: String): Int {
        System.err.println("usage error: $msg")
        return 2
    }
}
