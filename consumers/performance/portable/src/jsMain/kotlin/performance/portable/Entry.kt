package performance.portable

import kotlin.coroutines.resume
import kotlin.coroutines.suspendCoroutine

private fun commandLine(): Array<String> =
    js("globalThis.DYN4K_ARGS || (typeof process !== 'undefined' ? process.argv.slice(2) : [])")

private suspend fun browserPause(delayMs: Int): Unit = suspendCoroutine { continuation ->
    js("setTimeout")( { continuation.resume(Unit) }, delayMs)
}

fun main() = startPortable(commandLine(), ::browserPause)
