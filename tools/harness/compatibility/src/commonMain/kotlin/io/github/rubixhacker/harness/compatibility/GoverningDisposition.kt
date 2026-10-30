package io.github.rubixhacker.harness.compatibility

/**
 * The pure dispatch predicates of `tools/compatibility/governing_disposition.py`.
 *
 * Ported: [parameterDescriptor] and [pureForwarder].
 *
 * Not ported: `receipt`, `owner_sources`, `make`, `check`, and `main`. They read the ledger, the
 * candidate sources, the gzipped method execution archive, and the class-file dispatch inventory.
 */
object GoverningDisposition {
    /** The parameter half of a JVM method descriptor, with its closing parenthesis. */
    fun parameterDescriptor(descriptor: String): String {
        if (!descriptor.startsWith("(") || ")" !in descriptor) {
            throw IllegalArgumentException("method descriptor is invalid")
        }
        return descriptor.substringBefore(")") + ")"
    }

    /**
     * True when a bridge or static method body is exactly a visibility-preserving forwarder: one
     * invocation, a return, and only loads, the one invoke, casts, and the return before it.
     */
    fun pureForwarder(
        opcodes: List<Int>,
        candidateFlags: Int,
        baselineFlags: List<String>,
        signature: String,
        invocationCount: Int,
    ): Boolean {
        val bridge = "ACC_BRIDGE" in baselineFlags
        val visibility = when {
            "ACC_PUBLIC" in baselineFlags -> 0x0001
            "ACC_PROTECTED" in baselineFlags -> 0x0004
            else -> 0
        }
        if (visibility == 0 ||
            candidateFlags and 0x0005 != visibility ||
            invocationCount != 1 ||
            opcodes.size < 2 ||
            opcodes.last() !in 172..177 ||
            opcodes.count { it in 182..185 } != 1
        ) {
            return false
        }
        if (bridge) {
            if (candidateFlags and 0x1040 != 0x1040 || " static " in signature) return false
        } else if (candidateFlags and 0x0008 == 0 || " static " !in signature) {
            return false
        }
        return opcodes.dropLast(1).all { it in FORWARDER_OPCODES }
    }

    private val FORWARDER_OPCODES: Set<Int> =
        (21..25).toSet() + setOf(178, 180, 192) + (182..185).toSet()
}
