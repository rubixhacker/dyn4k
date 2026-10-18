package org.dyn4j.geometry

internal class JavaRandom(initialSeed: Long) {
    private var state = (initialSeed xor 0x5DEECE66DL) and ((1L shl 48) - 1L)

    private fun next(bits: Int): Int {
        state = (state * 0x5DEECE66DL + 11L) and ((1L shl 48) - 1L)
        return (state ushr (48 - bits)).toInt()
    }

    fun nextDouble(): Double = ((next(26).toLong() shl 27) + next(27)) / 9007199254740992.0
}
