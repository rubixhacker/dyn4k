package io.github.rubixhacker.harness.qualification

/**
 * `independent_gates.main`: one lane's approved gate routes, or the whole 112-lane assembly.
 *
 * Invocation forms:
 *
 * ```
 * --candidate-sha <sha> --lane <lane> --archive GATE=PATH [--archive GATE=PATH ...]
 * --candidate-sha <sha> --assembly <lane-inputs.json>
 * ```
 *
 * plus `--manifest`, `--repository`, `--expected-artifacts`,
 * `--expected-all-target-artifacts`, `--expected-producer-scopes`,
 * `--expected-archive-digests`, `--expected-runtime-identity`, and
 * `--expected-performance-key`. The result is printed as sorted JSON and the exit code is 0 only for
 * `PASSED`.
 */
object IndependentGatesCli {
    @JvmStatic
    fun main(arguments: Array<String>) {
        System.exit(GatesAggregate.main(arguments))
    }
}
