package io.github.rubixhacker.harness.android

import io.github.rubixhacker.harness.contract.Sha256
import java.nio.file.Files
import java.nio.file.Path
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

/**
 * The path lookups `full.validate_result` makes.
 *
 * The adverse controls substitute a wrong executable, KLIB, or Android image, so the lookups are a seam
 * rather than direct calls.
 */
interface NativeFullSeams {
    fun executablePath(root: Path, module: String, variant: String): String

    fun klibPaths(root: Path): Map<String, String>

    fun toolPaths(root: Path): Map<String, Path>

    object Default : NativeFullSeams {
        override fun executablePath(root: Path, module: String, variant: String): String =
            NativeFullContract.executablePath(posix(root), module, variant)

        override fun klibPaths(root: Path): Map<String, String> =
            NativeFullContract.klibPaths(posix(root))

        override fun toolPaths(root: Path): Map<String, Path> = NativeFullHost.toolPaths(root)
    }
}

/** A finished native command: argument vector, exit code, and both streams. */
class NativeCommand(
    val command: List<String>,
    val exitCode: Int,
    val stdout: ByteArray,
    val stderr: ByteArray,
)

/** `tools/android-native-runtime/full.py` host half: git, Gradle, ADB, and the six guest lanes. */
object NativeFullHost {
    /** `full.git`: raw stdout of a git command, or a rejection that keeps stderr. */
    fun git(root: Path, vararg arguments: String): ByteArray {
        val process = ProcessBuilder(listOf("git", "-C", posix(root)) + arguments)
            .redirectErrorStream(false)
            .start()
        val output = process.inputStream.use { it.readBytes() }
        val error = process.errorStream.use { it.readBytes() }
        if (process.waitFor() != 0) {
            throw IllegalArgumentException(
                "Git object unavailable: ${arguments.toList()}: ${error.decodeToString()}",
            )
        }
        return output
    }

    /** `full.source_identity`: the committed revision and its tree, with an optional clean check. */
    fun sourceIdentity(root: Path, requireClean: Boolean = true): Pair<String, String> {
        if (requireClean &&
            git(root, "status", "--porcelain", "--untracked-files=all").decodeToString().trim()
                .isNotEmpty()
        ) {
            throw IllegalArgumentException("source worktree is not clean")
        }
        val sourceSha = git(root, "rev-parse", "HEAD").decodeToString().trim()
        val sourceTree = git(root, "rev-parse", "HEAD^{tree}").decodeToString().trim()
        return sourceSha to sourceTree
    }

    /**
     * `full.manifest_at`: the committed corpus manifest, regenerated from this checkout.
     *
     * `full_corpus.scan_sources` and `full_corpus.make_manifest` belong to the qualification port, so a
     * caller that has them passes [regenerate]; without one the committed bytes are only checked.
     */
    fun manifestAt(
        root: Path,
        sourceSha: String,
        regenerate: ((JsonObject, Path) -> JsonObject)? = null,
    ): Pair<JsonObject, String> {
        val raw = git(root, "show", "$sourceSha:${NativeFullContract.CORPUS_PATH}")
        if (!root.resolve(NativeFullContract.CORPUS_PATH).toFile().readBytes().contentEquals(raw)) {
            throw IllegalArgumentException("working corpus manifest differs from committed source")
        }
        val manifest = FullHost.parseJson(raw)
        if (manifest.textOrNull("kind") != "full-common-corpus" ||
            manifest.textOrNull("policy") != "production"
        ) {
            throw IllegalArgumentException("full production common corpus is required")
        }
        if (regenerate != null && regenerate(manifest, root) != manifest) {
            throw IllegalArgumentException("source-derived corpus or mapping differs")
        }
        val counts = manifest.objectOrNull("counts") ?: JsonObject(emptyMap())
        if (counts.integerOrNull("mapped_original_methods") != 2253L ||
            counts.integerOrNull("supplemental_methods") != 270L
        ) {
            throw IllegalArgumentException("reviewed common corpus totals differ")
        }
        return manifest to Sha256.of(raw)
    }

    /** `full.tool_paths`: every tool, image, and wrapper byte the native route pins. */
    fun toolPaths(root: Path): Map<String, Path> = linkedMapOf(
        "adb" to Path.of(NativeReceiptHost.trustedAdb()),
        "emulator" to Path.of("/home/stewart/Android/Sdk/emulator/emulator"),
        "image" to Path.of(
            "/home/stewart/Android/Sdk/system-images/android-37.0/google_apis_playstore/" +
                "x86_64/source.properties",
        ),
        "system_image" to Path.of(
            "/home/stewart/Android/Sdk/system-images/android-37.0/google_apis_playstore/" +
                "x86_64/system.img",
        ),
        "ramdisk" to Path.of(
            "/home/stewart/Android/Sdk/system-images/android-37.0/google_apis_playstore/" +
                "x86_64/ramdisk.img",
        ),
        "ndk" to Path.of("/home/stewart/Android/Sdk/ndk/28.2.13676358/source.properties"),
        "java" to Path.of("/tmp/dyn4k-tools/jdk21/bin/java"),
        "konan" to Path.of(
            "/var/home/stewart/.konan/kotlin-native-prebuilt-linux-x86_64-2.4.20/" +
                "konan/konan.properties",
        ),
        "native_compiler" to Path.of(
            "/var/home/stewart/.konan/kotlin-native-prebuilt-linux-x86_64-2.4.20/" +
                "konan/lib/kotlin-native-compiler-embeddable.jar",
        ),
        "kgp" to Path.of(
            "/var/home/stewart/.gradle/caches/modules-2/files-2.1/org.jetbrains.kotlin/" +
                "kotlin-gradle-plugin/2.4.20/d64b6d447eecf2b0f6d19bdd677cae3bbce37585/" +
                "kotlin-gradle-plugin-2.4.20-gradle96.jar",
        ),
        "gradle_wrapper" to root.resolve("gradle/wrapper/gradle-wrapper.jar"),
        "gradle_core" to Path.of(
            "/var/home/stewart/.gradle/wrapper/dists/gradle-9.5.0-bin/" +
                "bvnork1r7n8i6kp5cnkibsc9q/gradle-9.5.0/lib/gradle-core-9.5.0.jar",
        ),
    )

    /** `full.command`: runs [argv] in [root] with [env] and keeps both streams. */
    fun command(root: Path, argv: List<String>, env: Map<String, String>? = null): NativeCommand {
        val builder = ProcessBuilder(argv).redirectErrorStream(false)
        builder.directory(root.toFile())
        if (env != null) builder.environment().putAll(env)
        val process = builder.start()
        val stdout = process.inputStream.use { it.readBytes() }
        val stderr = process.errorStream.use { it.readBytes() }
        val code = process.waitFor()
        return NativeCommand(argv, code, stdout, stderr)
    }

    /** `full.build_environment`: the pinned JDK and Android SDK for Gradle invocations. */
    fun buildEnvironment(): Map<String, String> = linkedMapOf(
        "JAVA_HOME" to "/tmp/dyn4k-tools/jdk21",
        "ANDROID_HOME" to "/home/stewart/Android/Sdk",
        "ANDROID_SDK_ROOT" to "/home/stewart/Android/Sdk",
    )

    /** `full.collect_pin_inputs`: the digest proposal for every pinned input. */
    fun collectPinInputs(root: Path, graphs: Map<String, ByteArray>): JsonObject = buildJsonObject {
        put("schema", JsonPrimitive(2))
        put("corpus_sha256", JsonPrimitive(sha256(root.resolve(NativeFullContract.CORPUS_PATH))))
        put("guest_fingerprint", JsonPrimitive(NativeReceipt.EXPECTED_FINGERPRINT))
        put(
            "tools",
            JsonObject(toolPaths(root).mapValues { (_, path) -> JsonPrimitive(sha256(path)) }),
        )
        put(
            "klibs",
            JsonObject(
                NativeFullContract.klibPaths(posix(root))
                    .mapValues { (_, path) -> JsonPrimitive(sha256(Path.of(path))) },
            ),
        )
        put(
            "executables",
            JsonObject(
                NativeFullContract.LANES.associate { (module, variant) ->
                    "$module-$variant" to JsonPrimitive(
                        sha256(Path.of(NativeFullContract.executablePath(posix(root), module, variant))),
                    )
                },
            ),
        )
        put(
            "graphs",
            JsonObject(
                NativeFullContract.graphCommands(posix(root)).keys.associateWith { module ->
                    JsonPrimitive(Sha256.of(NativeFullContract.graphSection(graphs.getValue(module).decodeToString(), module).encodeToByteArray()))
                },
            ),
        )
    }

    /** `full.load_pins`: the committed full pin manifest for one revision. */
    fun loadPins(root: Path, sourceSha: String): Pair<JsonObject, String> {
        val raw = git(root, "show", "$sourceSha:${NativeFullContract.PIN_PATH}")
        if (!root.resolve(NativeFullContract.PIN_PATH).toFile().readBytes().contentEquals(raw)) {
            throw IllegalArgumentException("working full pin file differs from committed source")
        }
        val pins = FullHost.parseJson(raw)
        if (pins.integerOrNull("schema") != 2L ||
            pins.stringMap("executables")?.keys != NativeFullContract.laneKeys().toSet()
        ) {
            throw IllegalArgumentException("full build pin manifest is incomplete")
        }
        return pins to Sha256.of(raw)
    }

    /** `full.read_record`: the bytes behind a recorded raw file, checked against its digest. */
    fun readRecord(record: JsonObject): ByteArray {
        val path = Path.of(record.textOrNull("path") ?: "")
        val raw = path.toFile().readBytes()
        if (Sha256.of(raw) != record.textOrNull("sha256")) {
            throw IllegalArgumentException("raw evidence hash differs: $path")
        }
        return raw
    }

    /** `full.save_record`: retains [raw] and records its digest. */
    fun saveRecord(output: Path, name: String, raw: ByteArray): JsonObject {
        val path = output.resolve(name)
        path.parent?.let { Files.createDirectories(it) }
        path.toFile().writeBytes(raw)
        return buildJsonObject {
            put("path", JsonPrimitive(posix(path)))
            put("sha256", JsonPrimitive(Sha256.of(raw)))
        }
    }

    /** `full.save_command`: retains both streams of a finished command. */
    fun saveCommand(output: Path, name: String, process: NativeCommand): JsonObject = buildJsonObject {
        put("command", JsonArray(process.command.map { JsonPrimitive(it) }))
        put("exit_code", JsonPrimitive(process.exitCode))
        put("stdout", saveRecord(output, "$name.stdout", process.stdout))
        put("stderr", saveRecord(output, "$name.stderr", process.stderr))
    }

    /** `full.guest_query`: the isolated server's device list and every guest property. */
    fun guestQuery(
        root: Path,
        adb: String,
        command: (Path, List<String>, Map<String, String>?) -> NativeCommand = { path, argv, env ->
            NativeFullHost.command(path, argv, env)
        },
    ): JsonObject {
        val prefix = listOf(adb, "-P", "5038", "-s", "emulator-5558")
        val devices = command(root, listOf(adb, "-P", "5038", "devices", "-l"), null)
        if (devices.exitCode != 0 || devices.stderr.isNotEmpty()) {
            throw IllegalArgumentException("isolated ADB device query failed")
        }
        NativeFullContract.requireTaskDevice(devices.stdout.decodeToString())
        val observations = linkedMapOf<String, JsonElement>()
        for (property in NativeReceipt.GUEST_PROPERTIES.keys) {
            val process = command(root, prefix + listOf("shell", "getprop", property), null)
            if (process.exitCode != 0 || process.stderr.isNotEmpty()) {
                throw IllegalArgumentException("guest property query failed: $property")
            }
            observations[property] = buildJsonObject {
                put("command", JsonArray(process.command.map { JsonPrimitive(it) }))
                put("exit_code", JsonPrimitive(process.exitCode))
                put("stdout", JsonPrimitive(process.stdout.decodeToString()))
                put("stderr", JsonPrimitive(process.stderr.decodeToString()))
            }
        }
        return buildJsonObject {
            put(
                "devices",
                buildJsonObject {
                    put("command", JsonArray(devices.command.map { JsonPrimitive(it) }))
                    put("exit_code", JsonPrimitive(devices.exitCode))
                    put("stdout", JsonPrimitive(devices.stdout.decodeToString()))
                    put("stderr", JsonPrimitive(devices.stderr.decodeToString()))
                },
            )
            put("observations", JsonObject(observations))
        }
    }

    /** `full.save_guest`: retained guest queries plus the values they prove. */
    fun saveGuest(output: Path, guest: JsonObject): JsonObject {
        val observations = guest.objectOrNull("observations") ?: JsonObject(emptyMap())
        val stdout = linkedMapOf<String, String>()
        for ((property, element) in observations) {
            stdout[property] = (element as JsonObject).textOrNull("stdout") ?: ""
        }
        return buildJsonObject {
            put("devices", saveCommand(output, "guest/devices", commandFrom(guest.getValue("devices"))))
            put(
                "observations",
                JsonObject(
                    observations.mapValues { (property, element) ->
                        saveCommand(output, "guest/$property", commandFrom(element))
                    },
                ),
            )
            put(
                "values",
                JsonObject(NativeFullContract.guestValues(stdout).mapValues { JsonPrimitive(it.value) }),
            )
        }
    }

    private fun commandFrom(element: JsonElement): NativeCommand {
        val record = element as JsonObject
        return NativeCommand(
            command = record.arrayOrNull("command")?.map { it.textOrNull() ?: "" }
                ?: throw IllegalArgumentException("recorded command is absent"),
            exitCode = record.integerOrNull("exit_code")?.toInt()
                ?: throw IllegalArgumentException("recorded command is absent"),
            stdout = (record.textOrNull("stdout") ?: "").encodeToByteArray(),
            stderr = (record.textOrNull("stderr") ?: "").encodeToByteArray(),
        )
    }

    /** `full.validate_command_record`: the recorded argv and exit code are the expected ones. */
    fun validateCommandRecord(record: JsonObject, argv: List<String>): Pair<ByteArray, ByteArray> {
        val command = record.arrayOrNull("command")?.map { it.textOrNull() }
        if (command != argv || record.integerOrNull("exit_code") != 0L) {
            throw IllegalArgumentException("recorded command differs or failed")
        }
        return readRecord(record.getValue("stdout") as JsonObject) to
            readRecord(record.getValue("stderr") as JsonObject)
    }

    /** `full.validate_guest`: the archived guest queries replay to the recorded identity. */
    fun validateGuest(record: JsonObject, root: Path, adb: String = NativeReceiptHost.trustedAdb()) {
        val devices = record.getValue("devices") as JsonObject
        val (devicesOut, devicesError) = validateCommandRecord(
            devices,
            listOf(adb, "-P", "5038", "devices", "-l"),
        )
        if (devicesError.isNotEmpty()) {
            throw IllegalArgumentException("guest device listing has stderr")
        }
        NativeFullContract.requireTaskDevice(devicesOut.decodeToString())
        val recorded = record.objectOrNull("observations")
        if (recorded == null || recorded.keys != NativeReceipt.GUEST_PROPERTIES.keys) {
            throw IllegalArgumentException("guest property observations are incomplete")
        }
        val stdout = linkedMapOf<String, String>()
        for (property in NativeReceipt.GUEST_PROPERTIES.keys) {
            val observation = recorded.getValue(property) as JsonObject
            val (out, error) = validateCommandRecord(
                observation,
                listOf(adb, "-P", "5038", "-s", "emulator-5558", "shell", "getprop", property),
            )
            if (error.isNotEmpty()) {
                throw IllegalArgumentException("guest property query has stderr")
            }
            stdout[property] = out.decodeToString()
        }
        val values = NativeFullContract.guestValues(stdout)
        val recordedValues = record.stringMap("values") ?: emptyMap()
        if (values != recordedValues) {
            throw IllegalArgumentException("guest values differ from raw observations")
        }
    }

    /** The result of `full.validate_result` for one archived native receipt. */
    fun validateResult(
        result: JsonObject,
        sourceRoot: Path,
        seams: NativeFullSeams = NativeFullSeams.Default,
    ): JsonObject {
        val root = sourceRoot.toAbsolutePath().normalize()
        val sourceSha = result.textOrNull("source_sha")
            ?: throw IllegalArgumentException("full receipt status, schema, or root differs")
        if (result.integerOrNull("schema") != 2L ||
            result.textOrNull("status") != "RUNTIME_PASSED" ||
            result.textOrNull("root") != posix(root)
        ) {
            throw IllegalArgumentException("full receipt status, schema, or root differs")
        }
        if (git(root, "rev-parse", "$sourceSha^{tree}").decodeToString().trim() !=
            result.textOrNull("source_tree")
        ) {
            throw IllegalArgumentException("source tree differs from Git object")
        }
        if (sourceIdentity(root) != sourceSha to (result.textOrNull("source_tree") ?: "")) {
            throw IllegalArgumentException("source checkout drifted from the executed commit")
        }
        val (manifest, manifestHash) = manifestAt(root, sourceSha)
        if (manifestHash != result.textOrNull("corpus_sha256")) {
            throw IllegalArgumentException("committed corpus hash differs")
        }
        val (pins, pinHash) = loadPins(root, sourceSha)
        if (pinHash != result.textOrNull("pin_sha256") ||
            pins.textOrNull("corpus_sha256") != manifestHash
        ) {
            throw IllegalArgumentException("committed full pins differ")
        }
        if (pins.textOrNull("guest_fingerprint") != NativeReceipt.EXPECTED_FINGERPRINT ||
            pins.objectOrNull("tools")?.textOrNull("adb") != NativeReceipt.TRUSTED_ADB_SHA256
        ) {
            throw IllegalArgumentException("trusted guest or ADB pin differs")
        }
        val tools = pins.objectOrNull("tools") ?: JsonObject(emptyMap())
        for ((name, path) in seams.toolPaths(root)) {
            if (sha256(path) != tools.textOrNull(name)) {
                throw IllegalArgumentException("toolchain or Android image differs: $name")
            }
        }
        val commands = NativeFullContract.buildCommands(posix(root))
        val builds = result.objectOrNull("builds")
        if (builds == null || builds.keys != commands.keys) {
            throw IllegalArgumentException("build receipts are incomplete")
        }
        for ((name, argv) in commands) {
            val (stdout, stderr) = validateCommandRecord(builds.getValue(name) as JsonObject, argv)
            val log = stdout.decodeToString() + stderr.decodeToString()
            val tasks = when (name) {
                "stage" -> NativeFullContract.STAGE_TASKS
                "tests" -> NativeFullContract.TEST_TASKS
                else -> NativeFullContract.CONSUMER_TASKS
            }
            if ("BUILD SUCCESSFUL" !in log || tasks.any {
                    NativeFullContract.buildTaskMarker(it) !in log
                }
            ) {
                throw IllegalArgumentException("$name build tasks are absent")
            }
        }
        val graphArgv = NativeFullContract.graphCommands(posix(root))
        val graphs = result.objectOrNull("graphs")
        if (graphs == null || graphs.keys != graphArgv.keys) {
            throw IllegalArgumentException("dependency reports are incomplete")
        }
        val pinnedGraphs = pins.stringMap("graphs") ?: emptyMap()
        for ((module, argv) in graphArgv) {
            val (stdout, stderr) = validateCommandRecord(graphs.getValue(module) as JsonObject, argv)
            if (stderr.isNotEmpty() || "BUILD SUCCESSFUL" !in stdout.decodeToString()) {
                throw IllegalArgumentException("Gradle dependency query failed")
            }
            val text = stdout.decodeToString()
            if (Sha256.of(NativeFullContract.graphSection(text, module).encodeToByteArray()) !=
                pinnedGraphs[module]
            ) {
                throw IllegalArgumentException("$module Gradle dependency graph differs")
            }
        }
        val pinnedKlibs = pins.stringMap("klibs") ?: emptyMap()
        for ((module, path) in seams.klibPaths(root)) {
            if (sha256(Path.of(path)) != pinnedKlibs[module]) {
                throw IllegalArgumentException("staged $module KLIB differs")
            }
        }
        val pinnedExecutables = pins.stringMap("executables") ?: emptyMap()
        for ((module, variant) in NativeFullContract.LANES) {
            val path = Path.of(seams.executablePath(root, module, variant))
            if (sha256(path) != pinnedExecutables["$module-$variant"] ||
                NativeReceipt.elfAbi(path.toFile().readBytes()) != "x86_64"
            ) {
                throw IllegalArgumentException("$module $variant ELF differs")
            }
        }
        validateGuest(result.getValue("guest") as JsonObject, root)
        val lanes = result.objectOrNull("lanes")
        if (lanes == null || lanes.keys != NativeFullContract.laneKeys().toSet()) {
            throw IllegalArgumentException("six native guest lanes are required")
        }
        var total = 0
        val adb = NativeReceiptHost.trustedAdb()
        val prefix = listOf(adb, "-P", "5038", "-s", "emulator-5558")
        for ((module, variant) in NativeFullContract.LANES) {
            val key = "$module-$variant"
            val lane = lanes.getValue(key) as JsonObject
            val path = Path.of(seams.executablePath(root, module, variant))
            val remote = NativeFullContract.GUEST_REMOTE
                .replace("{module}", module)
                .replace("{variant}", variant)
            val (push, pushError) = validateCommandRecord(
                lane.getValue("push") as JsonObject,
                prefix + listOf("push", posix(path), remote),
            )
            val (_, chmodError) = validateCommandRecord(
                lane.getValue("chmod") as JsonObject,
                prefix + listOf("shell", "chmod", "700", remote),
            )
            val (remoteOut, remoteError) = validateCommandRecord(
                lane.getValue("remote_hash") as JsonObject,
                prefix + listOf("shell", "sha256sum", remote),
            )
            NativeFullContract.validateDeploymentOutput(
                push,
                pushError,
                chmodError,
                remoteOut,
                remoteError,
                pinnedExecutables.getValue(key),
            )
            if (module != "consumer") {
                val (listed, listError) = validateCommandRecord(
                    lane.getValue("list") as JsonObject,
                    prefix + listOf("shell", remote, "--ktest_list_tests"),
                )
                if (listError.isNotEmpty()) {
                    throw IllegalArgumentException("$key test listing has stderr")
                }
                NativeFullContract.checkCases(
                    NativeFullContract.parseList(listed.decodeToString()),
                    NativeFullContract.expectedCases(manifestCases(manifest), module),
                )
            } else {
                if ("list" in lane) {
                    throw IllegalArgumentException("consumer has an unexpected test listing")
                }
            }
            val argv = if (module != "consumer") {
                prefix + listOf("shell", remote, "--ktest_logger=GTEST")
            } else {
                prefix + listOf("shell", remote)
            }
            val (stdout, stderr) = validateCommandRecord(lane.getValue("process") as JsonObject, argv)
            if (stderr.isNotEmpty() || stdout.isEmpty()) {
                throw IllegalArgumentException("$key process stderr or stdout differs")
            }
            if (module == "consumer") {
                val expected = NativeReceipt.consumerOutput()
                if (stdout.decodeToString().lines() != expected ||
                    lane.integerOrNull("case_count") != NativeReceipt.ASSERTIONS.size.toLong()
                ) {
                    throw IllegalArgumentException("staged consumer assertions differ")
                }
            } else {
                val count = NativeFullContract.checkCases(
                    NativeFullContract.parseTestRun(stdout.decodeToString()),
                    NativeFullContract.expectedCases(manifestCases(manifest), module),
                )
                if (lane.integerOrNull("case_count") != count.toLong()) {
                    throw IllegalArgumentException("$key case count differs")
                }
                total += count
            }
        }
        if (total != 2 * (2465 + 58) || result.integerOrNull("total_common_cases") != total.toLong()) {
            throw IllegalArgumentException("full native corpus total differs")
        }
        if (result.integerOrNull("mapped_common_executions") != 2L * 2253 ||
            result.integerOrNull("supplemental_common_executions") != 2L * 270
        ) {
            throw IllegalArgumentException("mapped or supplemental case totals differ")
        }
        return buildJsonObject {
            put("status", JsonPrimitive("CONSISTENCY_ONLY"))
            put("total_common_cases", JsonPrimitive(total))
            put("consumer_assertions", JsonPrimitive(2 * NativeReceipt.ASSERTIONS.size))
        }
    }

    /** The manifest rows `full.py` reads; a missing `cases` array yields none. */
    private fun manifestCases(manifest: JsonObject): List<CorpusCase> =
        manifest.arrayOrNull("cases").orEmpty().map { element ->
            val case = element as JsonObject
            CorpusCase(
                classname = case.textOrNull("classname") ?: "",
                method = case.textOrNull("method") ?: "",
                module = case.textOrNull("module") ?: "",
                sourceSet = case.textOrNull("source_set") ?: "",
            )
        }

    /** `full.run_pin`: proposes a pin manifest from the current build outputs. */
    fun runPin(root: Path, output: Path) {
        val env = buildEnvironment()
        val graphs = linkedMapOf<String, ByteArray>()
        for ((module, argv) in NativeFullContract.graphCommands(posix(root))) {
            val process = command(root, argv, env)
            if (process.exitCode != 0) {
                throw IllegalArgumentException("$module dependency query failed")
            }
            graphs[module] = process.stdout
        }
        val pins = collectPinInputs(root, graphs)
        output.parent?.let { Files.createDirectories(it) }
        output.toFile().writeText(PyJson.prettySorted(pins) + "\n")
    }

    /** `full.run_live`: the six-lane native run, recording every command before it is judged. */
    fun runLive(root: Path, output: Path): Int {
        Files.createDirectories(output)
        val result = linkedMapOf<String, JsonElement>()
        result["schema"] = JsonPrimitive(2)
        result["status"] = JsonPrimitive("UNPASSED")
        result["root"] = JsonPrimitive(posix(root))
        result["started_at_utc"] = JsonPrimitive(java.time.Instant.now().toString())
        try {
            val (sourceSha, sourceTree) = sourceIdentity(root)
            result["source_sha"] = JsonPrimitive(sourceSha)
            result["source_tree"] = JsonPrimitive(sourceTree)
            val (_, corpusSha) = manifestAt(root, sourceSha)
            result["corpus_sha256"] = JsonPrimitive(corpusSha)
            val (pins, pinSha) = loadPins(root, sourceSha)
            result["pin_sha256"] = JsonPrimitive(pinSha)
            val env = buildEnvironment()
            val builds = linkedMapOf<String, JsonElement>()
            for ((name, argv) in NativeFullContract.buildCommands(posix(root))) {
                val process = command(root, argv, env)
                builds[name] = saveCommand(output, "build/$name", process)
                if (process.exitCode != 0) {
                    throw IllegalArgumentException(
                        "$name build failed: ${process.stderr.decodeToString().takeLast(500)}",
                    )
                }
            }
            result["builds"] = JsonObject(builds)
            val graphs = linkedMapOf<String, JsonElement>()
            for ((module, argv) in NativeFullContract.graphCommands(posix(root))) {
                val process = command(root, argv, env)
                graphs[module] = saveCommand(output, "graph/$module", process)
                if (process.exitCode != 0) {
                    throw IllegalArgumentException("$module dependency query failed")
                }
            }
            result["graphs"] = JsonObject(graphs)
            if (sourceIdentity(root) != sourceSha to sourceTree) {
                throw IllegalArgumentException("source checkout changed during build")
            }
            val current = collectPinInputs(
                root,
                graphs.mapValues { (_, element) ->
                    readRecord((element as JsonObject).getValue("stdout") as JsonObject)
                },
            )
            if (current != pins) {
                throw IllegalArgumentException(
                    "final source build outputs, tools, or graphs differ from committed pins",
                )
            }
            val adb = NativeReceiptHost.trustedAdb()
            result["guest"] = saveGuest(output, guestQuery(root, adb))
            val lanes = linkedMapOf<String, JsonElement>()
            val prefix = listOf(adb, "-P", "5038", "-s", "emulator-5558")
            for ((module, variant) in NativeFullContract.LANES) {
                val key = "$module-$variant"
                val path = NativeFullContract.executablePath(posix(root), module, variant)
                val remote = NativeFullContract.GUEST_REMOTE
                    .replace("{module}", module)
                    .replace("{variant}", variant)
                val lane = linkedMapOf<String, JsonElement>()
                for ((name, argv) in listOf(
                    "push" to prefix + listOf("push", path, remote),
                    "chmod" to prefix + listOf("shell", "chmod", "700", remote),
                    "remote_hash" to prefix + listOf("shell", "sha256sum", remote),
                )) {
                    val process = command(root, argv)
                    lane[name] = saveCommand(output, "lanes/$key/$name", process)
                    if (process.exitCode != 0) {
                        throw IllegalArgumentException("$key $name failed")
                    }
                }
                val argv: List<String>
                if (module != "consumer") {
                    val process = command(root, prefix + listOf("shell", remote, "--ktest_list_tests"))
                    lane["list"] = saveCommand(output, "lanes/$key/list", process)
                    if (process.exitCode != 0) {
                        throw IllegalArgumentException("$key list failed")
                    }
                    argv = prefix + listOf("shell", remote, "--ktest_logger=GTEST")
                } else {
                    argv = prefix + listOf("shell", remote)
                }
                val process = command(root, argv)
                lane["process"] = saveCommand(output, "lanes/$key/process", process)
                lane["case_count"] = JsonPrimitive(
                    if (module != "consumer") {
                        NativeFullContract.parseTestRun(process.stdout.decodeToString()).size
                    } else {
                        NativeReceipt.ASSERTIONS.size
                    },
                )
                lanes[key] = JsonObject(lane)
            }
            result["lanes"] = JsonObject(lanes)
            result["total_common_cases"] = JsonPrimitive(
                lanes.entries.filter { !it.key.startsWith("consumer-") }
                    .sumOf { (it.value as JsonObject).integerOrNull("case_count") ?: 0L },
            )
            result["mapped_common_executions"] = JsonPrimitive(2 * 2253)
            result["supplemental_common_executions"] = JsonPrimitive(2 * 270)
            result["status"] = JsonPrimitive("RUNTIME_PASSED")
            result["replay"] = validateResult(JsonObject(result), root)
        } catch (error: Exception) {
            if (error !is IllegalArgumentException && error !is IllegalStateException &&
                error !is java.io.IOException && error !is NoSuchElementException &&
                error !is IndexOutOfBoundsException
            ) {
                throw error
            }
            result["status"] = JsonPrimitive("UNPASSED")
            result["error"] = JsonPrimitive(error.message ?: error.toString())
        }
        result["ended_at_utc"] = JsonPrimitive(java.time.Instant.now().toString())
        (output.resolve("result.json")).toFile()
            .writeText(PyJson.prettySorted(JsonObject(result)) + "\n")
        return if (result["status"] == JsonPrimitive("RUNTIME_PASSED")) 0 else 1
    }

    /** The value Python would report for an absent key. */
    internal fun nullValue(): JsonElement = JsonNull
}
