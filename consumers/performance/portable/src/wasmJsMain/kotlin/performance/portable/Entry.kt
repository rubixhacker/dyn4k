@file:OptIn(kotlin.js.ExperimentalWasmJsInterop::class)

package performance.portable

private fun commandLine(): String =
    js("(globalThis.DYN4K_ARGS || (typeof process !== 'undefined' ? process.argv.slice(2) : [])).join('\\u001f')")

fun main() = runPortable(commandLine().split('\u001f').toTypedArray())
