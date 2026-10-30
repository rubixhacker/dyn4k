package io.github.rubixhacker.harness.android

/**
 * `tools/android-native-runtime/receipt.py` (pure half).
 *
 * The native lane runs a Kotlin/Native executable in the task emulator. Its receipt must prove the
 * executable is an x86_64 ELF, that the guest is the pinned image, and that the resolved dependency
 * graph contains only the staged dyn4k publications.
 */
object NativeReceipt {
    val ASSERTIONS = listOf(
        "facade_body",
        "body_count",
        "world_step",
        "contact_begin",
        "contact_solve",
        "contact_present",
    )

    const val TRUSTED_ADB = "/home/stewart/Android/Sdk/platform-tools/adb"

    const val TRUSTED_ADB_SHA256 =
        "a902be8f45c6c62e76c9efaf6947a0fa747c9cabd89a2ac8e0d16ecb30b3ed01"

    const val EXPECTED_FINGERPRINT =
        "google/sdk_gphone64_x86_64/emu64xa:17/CE2A.260420.019/15611780:user/release-keys"

    /** Guest properties in query order, mapped to the receipt field each fills. */
    val GUEST_PROPERTIES: Map<String, String> = linkedMapOf(
        "ro.boot.qemu.avd_name" to "avd_name",
        "ro.build.version.sdk" to "api",
        "ro.build.fingerprint" to "fingerprint",
        "ro.product.cpu.abi" to "primary_abi",
        "ro.product.cpu.abilist" to "abi_list",
        "sys.boot_completed" to "boot_completed",
    )

    const val PIN_PATH = "tools/android-native-runtime/pins.json"

    val ALLOWED_COMPONENTS: Set<String> = linkedSetOf(
        "org.jetbrains.kotlin:kotlin-stdlib:2.4.20",
        "io.github.rubixhacker:dyn4k-core:0.1.0-alpha.1",
        "io.github.rubixhacker:dyn4k-core-androidnativex64:0.1.0-alpha.1",
        "io.github.rubixhacker:dyn4k:0.1.0-alpha.1",
        "io.github.rubixhacker:dyn4k-androidnativex64:0.1.0-alpha.1",
    )

    private val ELF_MAGIC = byteArrayOf(0x7f, 'E'.code.toByte(), 'L'.code.toByte(), 'F'.code.toByte(), 2, 1)

    /** `elf_abi`: a 64-bit little-endian x86_64 ELF header, or a rejection. */
    fun elfAbi(header: ByteArray): String {
        if (header.size < 20 || !header.copyOfRange(0, 6).contentEquals(ELF_MAGIC)) {
            throw IllegalArgumentException("executable is not a 64-bit little-endian ELF")
        }
        val machine = (header[18].toInt() and 0xff) or ((header[19].toInt() and 0xff) shl 8)
        if (machine != 62) {
            throw IllegalArgumentException("executable is not x86_64")
        }
        return "x86_64"
    }

    private val DEPENDENCY_LINE = Regex("""(?:\+---|\\---)\s+(.+)$""")

    /**
     * `validate_dependency_graph`: exactly one native compile graph, only the allowed staged
     * components, and no project or baseline provider.
     */
    fun validateDependencyGraph(graph: String) {
        if ("project :" in graph || "org.dyn4j:dyn4j" in graph) {
            throw IllegalArgumentException("dependency graph contains a project or baseline provider")
        }
        val lines = pySplitLines(graph)
        val headers = lines.indices.filter {
            lines[it].startsWith("androidNativeX64CompileKlibraries -")
        }
        if (headers.size != 1) {
            throw IllegalArgumentException("native compile dependency graph is absent or duplicated")
        }
        val seen = linkedSetOf<String>()
        for (line in lines.drop(headers[0] + 1)) {
            if (line.isBlank()) break
            val match = DEPENDENCY_LINE.find(line)
                ?: throw IllegalArgumentException("unrecognized native dependency line: $line")
            val component = match.groupValues[1].removeSuffix(" (*)").trim()
            if (component !in ALLOWED_COMPONENTS) {
                throw IllegalArgumentException("unapproved native dependency: $component")
            }
            seen += component
        }
        if (seen != ALLOWED_COMPONENTS) {
            throw IllegalArgumentException("required staged native dependency is absent")
        }
    }

    /** The exact stdout the staged native consumer must print. */
    fun consumerOutput(): List<String> =
        ASSERTIONS.map { "ASSERT $it" } + "NATIVE_RESULT PASS ${ASSERTIONS.size}"
}
