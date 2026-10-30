package io.github.rubixhacker.harness.qualification

import java.nio.file.Path

/**
 * `hosted.main`: `hosted.py run --candidate-sha … --target … --output …`.
 *
 * The probe JSON is printed as one line and the exit status is 0 only for `PROBE_PASSED`, so a
 * workflow step can gate on it without parsing the file.
 */
object HostedCli {
    /** Entry point of the hosted probe command line. */
    @JvmStatic
    fun main(arguments: Array<String>) {
        System.exit(run(arguments))
    }

    fun run(arguments: Array<String>, repository: Path? = null): Int {
        var run: String? = null
        var candidateSha: String? = null
        var target: String? = null
        var output: Path? = null
        var index = 0
        while (index < arguments.size) {
            when (val argument = arguments[index]) {
                "--candidate-sha" -> candidateSha = arguments[++index]
                "--target" -> target = arguments[++index]
                "--output" -> output = Path.of(arguments[++index])
                else -> if (argument.startsWith("--")) {
                    return usage("unexpected argument: $argument")
                } else if (run == null) {
                    run = argument
                } else {
                    return usage("unexpected argument: $argument")
                }
            }
            index++
        }
        if (run != "run") return usage("the command must be 'run'")
        if (candidateSha == null || target == null || output == null) {
            return usage("--candidate-sha, --target, and --output are required")
        }
        if (target !in Hosted.TARGETS) {
            return usage("argument --target: invalid choice: '$target'")
        }
        val root = repository ?: Path.of("").toAbsolutePath()
        val result = HostedHost.runHosted(
            target,
            candidateSha,
            output,
            HostedHost.HostedDependencies(root),
        )
        println(PyJson.renderDefault(result))
        return if (Py.str(result["status"]) == "PROBE_PASSED") 0 else 1
    }

    private fun usage(message: String): Int {
        System.err.println("usage error: $message")
        return 2
    }
}
