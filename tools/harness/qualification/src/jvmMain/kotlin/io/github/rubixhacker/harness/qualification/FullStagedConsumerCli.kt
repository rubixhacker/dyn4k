package io.github.rubixhacker.harness.qualification

/**
 * `full_staged_consumer.py`'s entry point.
 *
 * ```
 * run    --repository <dir> --candidate-sha <sha> --staging <dir> --output <dir>
 *        --gradle <executable> --expected-core-sha256 <sha> --expected-facade-sha256 <sha>
 * verify --repository <dir> --archive <dir>
 *        --expected-core-sha256 <sha> --expected-facade-sha256 <sha>
 * ```
 */
object FullStagedConsumerCli {
    @JvmStatic
    fun main(arguments: Array<String>) {
        System.exit(FullStagedConsumer.main(arguments))
    }
}
