package io.github.rubixhacker.harness.android

/**
 * `tools/android-runtime/run.py` (pure half).
 *
 * The installed diagnostic route drives two emulator serials through one isolated ADB server on port
 * 5038. Only the two task emulators are accepted, and on API 21 the candidate route passes the test
 * class selection through a device file because the `-e class` argument grows past the shell limit.
 */

/** `argparse.ArgumentTypeError`: a rejected command-line value. */
class ArgumentTypeError(message: String) : Exception(message)

/** The chosen test classes and how the runner is told about them. */
class InstrumentationSelection(
    val classes: List<String>,
    val arguments: List<String>,
    val selectionPath: String?,
    val selectionText: String?,
    val devicePath: String?,
)

object RunContract {
    val EMULATOR_SERIALS = listOf("emulator-5558", "emulator-5562")

    private val SERIAL_PATTERN = Regex("""emulator-[0-9]{4}""")

    val CONSUMER_CASES: Set<String> = setOf(
        "geometryAndIdentity", "collisionAndExtension", "collisionModel", "dynamicsAndErrors",
        "worldAndCallbacks", "jointsAndExtension", "contacts",
    ).mapTo(LinkedHashSet()) { "io.github.rubixhacker.dyn4k.runtime.ConsumerJourneyTest#$it" }

    /** `selected_emulator_serial`: only the two task emulators are accepted. */
    fun selectedEmulatorSerial(serial: String): String {
        if (!SERIAL_PATTERN.matches(serial) || serial !in EMULATOR_SERIALS) {
            throw ArgumentTypeError(
                "Android emulator serial must be emulator-5558 or emulator-5562",
            )
        }
        return serial
    }

    /** `adb_for_serial`: the isolated ADB server on port 5038 bound to [serial]. */
    fun adbForSerial(sdk: String, serial: String): List<String> = listOf(
        "$sdk/platform-tools/adb",
        "-P",
        "5038",
        "-s",
        selectedEmulatorSerial(serial),
    )

    /** `instrumentation_classes`: the journey suite plus, for a candidate, the staged and portable tests. */
    fun instrumentationClasses(portableClasses: List<String>, flavor: String): List<String> {
        val selected = linkedSetOf("io.github.rubixhacker.dyn4k.runtime.ConsumerJourneyTest")
        if (flavor == "candidate") {
            selected += "io.github.rubixhacker.dyn4k.runtime.StagedKotlinConsumerTest"
            selected += portableClasses
        }
        return selected.sorted()
    }

    /**
     * `instrumentation_filter`: the runner arguments and, on API 21 candidates, the device selection file.
     *
     * The file content is returned rather than written, so the decision stays pure; the host half writes
     * it at [InstrumentationSelection.selectionPath].
     */
    fun instrumentationFilter(
        portableClasses: List<String>,
        flavor: String,
        buildType: String,
        expectedApi: String,
        directory: String,
    ): InstrumentationSelection {
        val classes = instrumentationClasses(portableClasses, flavor)
        if (expectedApi != "21" || flavor != "candidate") {
            return InstrumentationSelection(classes, listOf("-e", "class", classes.joinToString(",")), null, null, null)
        }
        val selection = "$directory/selected-classes.txt"
        val devicePath = "/data/local/tmp/dyn4k-$flavor-$buildType-classes.txt"
        return InstrumentationSelection(
            classes,
            listOf("-e", "testFile", devicePath),
            selection,
            classes.joinToString("") { "$it\n" },
            devicePath,
        )
    }
}
