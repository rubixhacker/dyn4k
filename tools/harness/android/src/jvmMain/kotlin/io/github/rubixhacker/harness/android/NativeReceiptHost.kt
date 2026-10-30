package io.github.rubixhacker.harness.android

import java.nio.file.Files
import java.nio.file.Path
import io.github.rubixhacker.harness.contract.Sha256
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

/** `tools/android-native-runtime/receipt.py` host half: ADB trust, build pins, and receipt replay. */
object NativeReceiptHost {
    /** `trusted_adb`: the pinned SDK ADB, whose bytes must still match the recorded digest. */
    fun trustedAdb(): String {
        val path = Path.of(NativeReceipt.TRUSTED_ADB)
        if (!Files.isRegularFile(path) || sha256(path) != NativeReceipt.TRUSTED_ADB_SHA256) {
            throw IllegalArgumentException("trusted SDK ADB is missing or changed")
        }
        return NativeReceipt.TRUSTED_ADB
    }

    /** `validated_adb_argument`: the runner accepts only the trusted SDK ADB path. */
    fun validatedAdbArgument(candidate: Path): String {
        val adb = trustedAdb()
        if (candidate != Path.of(NativeReceipt.TRUSTED_ADB)) {
            throw IllegalArgumentException("ADB path differs from the trusted SDK tool")
        }
        return adb
    }

    /** `receipt.git_output`: bytes of a git object, or a rejection. */
    fun gitOutput(root: Path, vararg arguments: String): ByteArray {
        val process = ProcessBuilder(listOf("git", "-C", posix(root)) + arguments)
            .redirectErrorStream(false)
            .start()
        val output = process.inputStream.use { it.readBytes() }
        process.errorStream.use { it.readBytes() }
        if (process.waitFor() != 0) {
            throw IllegalArgumentException("Git object is unavailable: ${arguments.toList()}")
        }
        return output
    }

    /** `receipt.load_pins`: the committed build pins for one source revision. */
    fun loadPins(root: Path, sourceSha: String): Pair<JsonObject, String> {
        val raw = gitOutput(root, "show", "$sourceSha:${NativeReceipt.PIN_PATH}")
        val pins = FullHost.parseJson(raw)
        if (pins.integerOrNull("schema") != 1L ||
            pins.textOrNull("adb_sha256") != NativeReceipt.TRUSTED_ADB_SHA256 ||
            pins.textOrNull("guest_fingerprint") != NativeReceipt.EXPECTED_FINGERPRINT ||
            pins.stringMap("artifacts")?.keys != setOf("dyn4k-core", "dyn4k") ||
            pins.stringMap("executables")?.keys != setOf("debug", "optimized")
        ) {
            throw IllegalArgumentException("committed build pin manifest is incomplete")
        }
        return pins to Sha256.of(raw)
    }

    /** `receipt.dependency_command`: the native compile dependency query for the staged consumer. */
    fun dependencyCommand(root: Path): List<String> {
        val resolved = root.toAbsolutePath().normalize()
        return listOf(
            "$resolved/gradlew",
            "-p",
            "$resolved/consumers/android-native-runtime",
            "--no-daemon",
            "--console=plain",
            "-PstagingRepository=$resolved/build/staging-repository",
            "dependencies",
            "--configuration",
            "androidNativeX64CompileKlibraries",
        )
    }

    /**
     * `receipt.validate_receipt`: every recorded byte, command, identity, and pin still agrees with the
     * checkout it describes.
     */
    fun validateReceipt(receipt: JsonObject, expectedSha: String, sourceRoot: Path): JsonObject {
        if (receipt.integerOrNull("schema") != 1L ||
            receipt.textOrNull("status") != "DIAGNOSTIC_PASSED"
        ) {
            throw IllegalArgumentException("receipt status or schema differs")
        }
        if (receipt.textOrNull("source_sha") != expectedSha || !COMMIT_SHA.matches(expectedSha)) {
            throw IllegalArgumentException("source SHA differs")
        }
        val sourceTree = gitOutput(sourceRoot, "rev-parse", "$expectedSha^{tree}")
            .decodeToString().trim()
        if (receipt.textOrNull("source_tree") != sourceTree) {
            throw IllegalArgumentException("source tree differs from the Git object")
        }
        val (pins, pinDigest) = loadPins(sourceRoot, expectedSha)
        if (receipt.textOrNull("pin_manifest_sha256") != pinDigest) {
            throw IllegalArgumentException("committed build pin manifest differs")
        }
        val variant = receipt.textOrNull("variant")
        if (variant != "debug" && variant != "optimized") {
            throw IllegalArgumentException("unknown native variant")
        }
        val adb = trustedAdb()
        val tooling = receipt.objectOrNull("tooling")
        if (tooling?.textOrNull("adb_path") != adb ||
            tooling.textOrNull("adb_sha256") != NativeReceipt.TRUSTED_ADB_SHA256
        ) {
            throw IllegalArgumentException("ADB tool path or image hash differs")
        }
        val evidence = receipt.objectOrNull("build_evidence") ?: JsonObject(emptyMap())
        if (evidence.keys != setOf("stage", "link")) {
            throw IllegalArgumentException("build logs are incomplete")
        }
        val requiredLogText = linkedMapOf(
            "stage" to listOf(
                ":dyn4k-core:publishKotlinMultiplatformPublicationToStagingRepository",
                ":dyn4k:publishKotlinMultiplatformPublicationToStagingRepository",
                ":dyn4k-core:publishAndroidNativeX64PublicationToStagingRepository",
                ":dyn4k:publishAndroidNativeX64PublicationToStagingRepository",
            ),
            "link" to listOf(
                ":linkDebugExecutableAndroidNativeX64",
                ":linkReleaseExecutableAndroidNativeX64",
            ),
        )
        for ((name, markers) in requiredLogText) {
            val log = evidence[name] as? JsonObject ?: JsonObject(emptyMap())
            val logPath = Path.of(log.textOrNull("path") ?: "")
            if (!Files.isRegularFile(logPath) || sha256(logPath) != log.textOrNull("sha256")) {
                throw IllegalArgumentException("$name log is absent or changed")
            }
            val content = logPath.toFile().readText()
            if ("BUILD SUCCESSFUL" !in content || markers.any { it !in content }) {
                throw IllegalArgumentException("$name log does not show required tasks")
            }
        }
        val report = receipt.objectOrNull("dependency_report") ?: JsonObject(emptyMap())
        if (report["command"] != jsonArrayOf(dependencyCommand(sourceRoot)) ||
            report.integerOrNull("exit_code") != 0L
        ) {
            throw IllegalArgumentException("native dependency command differs or failed")
        }
        val reportPath = Path.of(report.textOrNull("path") ?: "")
        if (!Files.isRegularFile(reportPath) || sha256(reportPath) != report.textOrNull("sha256")) {
            throw IllegalArgumentException("dependency report is absent or changed")
        }
        NativeReceipt.validateDependencyGraph(reportPath.toFile().readText())
        val artifacts = receipt.objectOrNull("artifacts")
            ?: throw IllegalArgumentException("both staged KLIBs are required")
        if (artifacts.keys != setOf("dyn4k-core", "dyn4k")) {
            throw IllegalArgumentException("both staged KLIBs are required")
        }
        val pinnedArtifacts = pins.stringMap("artifacts") ?: emptyMap()
        for ((module, element) in artifacts) {
            val record = element as? JsonObject ?: JsonObject(emptyMap())
            val path = Path.of(record.textOrNull("path") ?: "")
            if (!Files.isRegularFile(path) || !path.fileName.toString().endsWith(".klib") ||
                module !in path.fileName.toString()
            ) {
                throw IllegalArgumentException("missing staged KLIB: $module")
            }
            if (sha256(path) != record.textOrNull("sha256")) {
                throw IllegalArgumentException("staged KLIB hash differs: $module")
            }
            if (record.textOrNull("sha256") != pinnedArtifacts[module]) {
                throw IllegalArgumentException("staged KLIB differs from committed build pin: $module")
            }
        }
        val executable = receipt.objectOrNull("executable") ?: JsonObject(emptyMap())
        val executablePath = Path.of(executable.textOrNull("path") ?: "")
        if (!Files.isRegularFile(executablePath)) {
            throw IllegalArgumentException("missing native executable")
        }
        if (executable.textOrNull("sha256") != sha256(executablePath)) {
            throw IllegalArgumentException("native executable hash differs")
        }
        val pinnedExecutables = pins.stringMap("executables") ?: emptyMap()
        if (executable.textOrNull("sha256") != pinnedExecutables[variant]) {
            throw IllegalArgumentException("native executable differs from committed build pin")
        }
        if (executable.textOrNull("abi") != NativeReceipt.elfAbi(executablePath.toFile().readBytes())) {
            throw IllegalArgumentException("native executable ABI differs")
        }
        val guest = receipt.objectOrNull("guest") ?: JsonObject(emptyMap())
        if (guest.textOrNull("serial") != "emulator-5558" ||
            guest.textOrNull("primary_abi") != "x86_64" ||
            guest.textOrNull("boot_completed") != "1" ||
            guest.textOrNull("api") != "37" ||
            guest.textOrNull("fingerprint") != NativeReceipt.EXPECTED_FINGERPRINT ||
            guest.textOrNull("avd_name") != "dyn4k_api37_play_x64"
        ) {
            throw IllegalArgumentException("guest identity is incomplete or wrong ABI")
        }
        val observations = guest.objectOrNull("observations")
        if (observations == null || observations.keys != NativeReceipt.GUEST_PROPERTIES.keys) {
            throw IllegalArgumentException("guest property observations are incomplete")
        }
        for ((property, field) in NativeReceipt.GUEST_PROPERTIES) {
            val observation = observations[property] as? JsonObject ?: JsonObject(emptyMap())
            val expectedCommand = jsonArrayOf(
                listOf(adb, "-P", "5038", "-s", "emulator-5558", "shell", "getprop", property),
            )
            if (observation["command"] != expectedCommand ||
                observation.integerOrNull("exit_code") != 0L ||
                observation.textOrNull("stderr") != "" ||
                !observation["stdout"].isText() ||
                observation.textOrNull("stdout")?.trim() != guest.textOrNull(field)
            ) {
                throw IllegalArgumentException("guest property observation differs: $property")
            }
        }
        val deployment = receipt.objectOrNull("deployment") ?: JsonObject(emptyMap())
        if (deployment.textOrNull("remote_sha256") != executable.textOrNull("sha256") ||
            deployment.integerOrNull("chmod_exit_code") != 0L
        ) {
            throw IllegalArgumentException("deployed executable differs")
        }
        val process = receipt.objectOrNull("process") ?: JsonObject(emptyMap())
        val command = process.arrayOrNull("command")
        val remote = "/data/local/tmp/dyn4k-native-$variant"
        if (command == null || command.size != 7 ||
            command[0].textOrNull() != adb ||
            command.drop(1).map { it.textOrNull() } !=
            listOf("-P", "5038", "-s", "emulator-5558", "shell", remote)
        ) {
            throw IllegalArgumentException("native process command differs")
        }
        if (process.integerOrNull("exit_code") != 0L) {
            throw IllegalArgumentException("native process exited nonzero")
        }
        val stdout = process.textOrNull("stdout")
        if (stdout.isNullOrEmpty()) {
            throw IllegalArgumentException("native process produced no output")
        }
        for (stream in listOf("stdout", "stderr")) {
            val rawPath = Path.of(process.textOrNull("${stream}_path") ?: "")
            val recorded = process.textOrNull(stream)
            if (!Files.isRegularFile(rawPath) || recorded == null ||
                rawPath.toFile().readText() != recorded ||
                sha256(rawPath) != process.textOrNull("${stream}_sha256")
            ) {
                throw IllegalArgumentException("raw $stream differs")
            }
        }
        if (pySplitLines(stdout) != NativeReceipt.consumerOutput() ||
            receipt.integerOrNull("assertion_count") != NativeReceipt.ASSERTIONS.size.toLong()
        ) {
            throw IllegalArgumentException("native assertions are absent or differ")
        }
        return buildJsonObject {
            put("status", JsonPrimitive("CONSISTENCY_ONLY"))
            put("assertions", JsonPrimitive(NativeReceipt.ASSERTIONS.size))
        }
    }

    private val COMMIT_SHA = Regex("""[0-9a-f]{40}""")

    internal fun jsonArrayOf(values: List<String>): JsonElement =
        kotlinx.serialization.json.JsonArray(values.map { JsonPrimitive(it) })
}
