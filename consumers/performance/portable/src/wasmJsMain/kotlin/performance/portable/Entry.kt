@file:OptIn(kotlin.js.ExperimentalWasmJsInterop::class)

package performance.portable

import kotlin.coroutines.resume
import kotlin.coroutines.suspendCoroutine

private fun commandLine(): String =
    js("(globalThis.DYN4K_ARGS || (typeof process !== 'undefined' ? process.argv.slice(2) : [])).join('\\u001f')")

private fun schedule(callback: () -> Unit, delayMs: Int): Unit = js("setTimeout(callback, delayMs)")

private suspend fun browserPause(delayMs: Int): Unit = suspendCoroutine { continuation ->
    schedule({ continuation.resume(Unit) }, delayMs)
}

fun main() = startPortable(commandLine().split('\u001f').toTypedArray(), ::browserPause)
