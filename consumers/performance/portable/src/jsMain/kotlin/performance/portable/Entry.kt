package performance.portable

private fun commandLine(): Array<String> =
    js("globalThis.DYN4K_ARGS || (typeof process !== 'undefined' ? process.argv.slice(2) : [])")

fun main() = runPortable(commandLine())
