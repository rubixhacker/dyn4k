package io.github.rubixhacker.harness.performance

/**
 * CPython's Mersenne Twister, ported so that `random.Random(seed).randrange(n)` yields the same
 * sequence as Python. The noise studies are only reproducible if the resampling draws match the
 * recorded intervals, so the twist, the seeding routine, and the rejection sampling of
 * `_randbelow_with_getrandbits` all follow CPython's `_randommodule.c` and `random.py`.
 */
class PythonRandom(seed: Long) {
    private val state = IntArray(N)
    private var index = N

    init {
        seedFromInteger(seed)
    }

    /** CPython splits the seed's magnitude into little-endian 32-bit words and runs `init_by_array`. */
    private fun seedFromInteger(seed: Long) {
        val magnitude = if (seed < 0) -seed else seed
        if (magnitude == 0L) {
            initByArray(intArrayOf(0))
            return
        }
        val key = mutableListOf<Int>()
        var remaining = magnitude
        while (remaining != 0L) {
            key.add((remaining and 0xffffffffL).toInt())
            remaining = remaining ushr 32
        }
        initByArray(key.toIntArray())
    }

    private fun initGenrand(value: Int) {
        state[0] = value
        for (position in 1 until N) {
            val previous = state[position - 1]
            state[position] = 1812433253 * (previous xor (previous ushr 30)) + position
        }
        index = N
    }

    private fun initByArray(key: IntArray) {
        initGenrand(19650218)
        var left = maxOf(N, key.size)
        var position = 1
        var keyPosition = 0
        while (left > 0) {
            val previous = state[position - 1]
            state[position] =
                (state[position] xor ((previous xor (previous ushr 30)) * 1664525)) + key[keyPosition] + keyPosition
            position += 1
            keyPosition += 1
            if (position >= N) {
                state[0] = state[N - 1]
                position = 1
            }
            if (keyPosition >= key.size) keyPosition = 0
            left -= 1
        }
        left = N - 1
        while (left > 0) {
            val previous = state[position - 1]
            state[position] =
                (state[position] xor ((previous xor (previous ushr 30)) * 1566083941)) - position
            position += 1
            if (position >= N) {
                state[0] = state[N - 1]
                position = 1
            }
            left -= 1
        }
        state[0] = Int.MIN_VALUE
        index = N
    }

    private fun twist() {
        for (position in 0 until N - M) {
            val combined = (state[position] and UPPER_MASK) or (state[position + 1] and LOWER_MASK)
            state[position] = state[position + M] xor (combined ushr 1) xor MAG01[combined and 1]
        }
        for (position in N - M until N - 1) {
            val combined = (state[position] and UPPER_MASK) or (state[position + 1] and LOWER_MASK)
            state[position] = state[position + (M - N)] xor (combined ushr 1) xor MAG01[combined and 1]
        }
        val combined = (state[N - 1] and UPPER_MASK) or (state[0] and LOWER_MASK)
        state[N - 1] = state[M - 1] xor (combined ushr 1) xor MAG01[combined and 1]
        index = 0
    }

    /** `genrand_uint32`: one tempered 32-bit output. */
    fun nextUInt32(): Int {
        if (index >= N) twist()
        var value = state[index]
        index += 1
        value = value xor (value ushr 11)
        value = value xor ((value shl 7) and 0x9d2c5680.toInt())
        value = value xor ((value shl 15) and 0xefc60000.toInt())
        return value xor (value ushr 18)
    }

    /** `getrandbits(k)` for `k` from 1 to 32. */
    fun getRandBits(bits: Int): Int {
        require(bits in 1..32) { "getrandbits supports 1 to 32 bits here" }
        return nextUInt32() ushr (32 - bits)
    }

    /** `randrange(width)` for a positive width: `_randbelow_with_getrandbits`. */
    fun randRange(width: Int): Int {
        require(width > 0) { "empty range for randrange" }
        val bits = 32 - width.toUInt().countLeadingZeroBits()
        var value = getRandBits(bits)
        while (value >= width) {
            value = getRandBits(bits)
        }
        return value
    }

    private companion object {
        const val N = 624
        const val M = 397
        const val UPPER_MASK = Int.MIN_VALUE
        const val LOWER_MASK = 0x7fffffff
        val MAG01 = intArrayOf(0, 0x9908b0df.toInt())
    }
}
