package io.github.rubixhacker.harness.compatibility

/**
 * The ledger declaration signature normalisation used by the JVM probe, ported from
 * `tools/compatibility/execution_probe.py`.
 *
 * `declarations` and `signature` stay unported: they call `tools/baseline/verify.py`'s `surface`
 * and `member_inventory` parsers, read a candidate JAR, and run `javap` twice per type. Porting them
 * requires `tools/baseline`, which is outside this scope.
 */
object ExecutionProbe {
    val DECLARATION_FLAGS = listOf(
        "ACC_PUBLIC",
        "ACC_PROTECTED",
        "ACC_BRIDGE",
        "ACC_SYNTHETIC",
    )

    /** Removes the `final` modifier from a static initializer or method declaration. */
    fun ledgerSignature(signature: String): String {
        val index = signature.indexOf("; descriptor: ")
        val declaration: String
        val marker: String
        val descriptor: String
        if (index < 0) {
            declaration = signature
            marker = ""
            descriptor = ""
        } else {
            declaration = signature.substring(0, index)
            marker = "; descriptor: "
            descriptor = signature.substring(index + marker.length)
        }
        val normalised = if (marker.isNotEmpty() && "(" in declaration && " static " in declaration) {
            declaration.replaceFirst(STATIC_FINAL, "")
        } else {
            declaration
        }
        return normalised + marker + descriptor
    }

    private val STATIC_FINAL = Regex("\\bfinal ")
}
