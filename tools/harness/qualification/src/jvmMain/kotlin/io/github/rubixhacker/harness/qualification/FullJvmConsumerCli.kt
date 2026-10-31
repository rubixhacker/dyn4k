package io.github.rubixhacker.harness.qualification

import java.nio.file.Path

/**
 * `full_jvm_consumer.py`'s entry point.
 *
 * ```
 * prepare --repository <dir> --candidate-sha <sha> --destination <dir> [--lane <lane>]
 * verify  --repository <dir> --candidate-sha <sha> --archive <dir>
 *         --expected-core-sha256 <sha> --expected-facade-sha256 <sha> [--lane <lane>]
 * run     (not ported: fails closed naming the Python module)
 * ```
 */
object FullJvmConsumerCli {
    @JvmStatic
    fun main(arguments: Array<String>) {
        System.exit(run(arguments))
    }

    fun run(arguments: Array<String>): Int {
        if (arguments.isEmpty()) return usage("action required: prepare, run, or verify")
        val action = arguments[0]
        val values = linkedMapOf<String, String>()
        var index = 1
        while (index < arguments.size) {
            val argument = arguments[index++]
            if (!argument.startsWith("--")) return usage("unexpected argument: $argument")
            if (index >= arguments.size) return usage("argument $argument: expected one argument")
            values[argument.removePrefix("--")] = arguments[index++]
        }
        return try {
            when (action) {
                "prepare" -> {
                    val result = FullJvmConsumer.prepare(
                        Path.of(values["repository"] ?: throw IllegalArgumentException("missing --repository")),
                        values["candidate-sha"] ?: throw IllegalArgumentException("missing --candidate-sha"),
                        Path.of(values["destination"] ?: throw IllegalArgumentException("missing --destination")),
                        values["lane"] ?: FullJvmConsumer.LANE,
                    )
                    println(io.github.rubixhacker.harness.contract.CanonicalJson.render(result))
                    0
                }
                "verify" -> {
                    val hashes = mapOf(
                        "dyn4k-core" to (
                            values["expected-core-sha256"]
                                ?: throw IllegalArgumentException("missing --expected-core-sha256")
                            ),
                        "dyn4k" to (
                            values["expected-facade-sha256"]
                                ?: throw IllegalArgumentException("missing --expected-facade-sha256")
                            ),
                    )
                    val result = FullJvmConsumer.verify(
                        Path.of(values["archive"] ?: throw IllegalArgumentException("missing --archive")),
                        Path.of(values["repository"] ?: throw IllegalArgumentException("missing --repository")),
                        values["candidate-sha"] ?: throw IllegalArgumentException("missing --candidate-sha"),
                        hashes,
                        values["lane"] ?: FullJvmConsumer.LANE,
                    )
                    println(io.github.rubixhacker.harness.contract.CanonicalJson.render(result))
                    0
                }
                "run" -> FullJvmConsumer.run()
                else -> usage("unknown action: $action")
            }
        } catch (error: IllegalArgumentException) {
            System.err.println(error.message ?: error.toString())
            1
        }
    }

    private fun usage(message: String): Int {
        System.err.println("usage error: $message")
        return 2
    }
}
