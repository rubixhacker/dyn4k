package io.github.rubixhacker.harness.android

import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.StandardCopyOption
import java.util.zip.ZipFile
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

/** `run_optimized.snapshot_artifact`: a retained copy that still matches the built bytes. */
data class Snapshot(val path: String, val sha256: String, val buildOutputPath: String) {
    fun toJson(): JsonObject = buildJsonObject {
        put("path", JsonPrimitive(path))
        put("sha256", JsonPrimitive(sha256))
        put("build_output_path", JsonPrimitive(buildOutputPath))
    }
}

object OptimizedHost {
    /** `run_optimized.snapshot_artifact`. */
    fun snapshotArtifact(source: Path, destination: Path, expectedSha: String): Snapshot {
        if (sha256(source) != expectedSha) {
            throw IllegalArgumentException("build artifact changed before snapshot: $source")
        }
        destination.parent?.let { Files.createDirectories(it) }
        Files.copy(source, destination, StandardCopyOption.REPLACE_EXISTING)
        if (sha256(destination) != expectedSha) {
            throw IllegalArgumentException("build artifact changed during snapshot: $source")
        }
        return Snapshot(posix(destination), expectedSha, posix(source))
    }

    /** `run_optimized.dex_evidence`: every class descriptor in the APK's DEX files. */
    fun dexEvidence(
        apk: Path,
        directory: Path,
        sdk: Path,
        command: (List<String>, Path?, Boolean) -> String = { args, output, check ->
            LaneHost.command(args, output, check)
        },
    ): Pair<Set<String>, List<JsonObject>> {
        val descriptors = linkedSetOf<String>()
        val files = mutableListOf<JsonObject>()
        ZipFile(apk.toFile()).use { archive ->
            val names = archive.entries().toList()
                .map { it.name }
                .filter { DEX_NAME.matches(it) }
                .sorted()
            if (names.isEmpty()) {
                throw IllegalArgumentException("optimized APK has no DEX bytecode")
            }
            for (name in names) {
                val destination = directory.resolve(name)
                Files.createDirectories(directory)
                archive.getInputStream(archive.getEntry(name)).use { input ->
                    destination.toFile().writeBytes(input.readBytes())
                }
                val dexdump = directory.resolve("$name.dexdump.txt")
                val output = command(
                    listOf("$sdk/build-tools/36.0.0/dexdump", "-f", posix(destination)),
                    dexdump,
                    true,
                )
                descriptors += DESCRIPTOR.findAll(output).map { it.groupValues[1] }
                files += buildJsonObject {
                    put("path", JsonPrimitive(posix(destination)))
                    put("sha256", JsonPrimitive(sha256(destination)))
                    put("dexdump", JsonPrimitive(posix(dexdump)))
                    put("dexdump_sha256", JsonPrimitive(sha256(dexdump)))
                }
            }
        }
        if (descriptors.isEmpty()) {
            throw IllegalArgumentException("DEX class descriptor inventory empty")
        }
        return descriptors to files
    }

    private val DEX_NAME = Regex("""classes\d*\.dex""")
    private val DESCRIPTOR = Regex("""Class descriptor\s+: '([^']+)'""")

    /** `run_optimized.main`: the optimized installed route. */
    fun run(
        root: Path,
        prepared: JsonObject,
        preparedBytes: ByteArray,
        preparedPath: Path,
        providerGraph: Path,
        output: Path,
        buildType: String,
        expectedApi: String,
        expectedAbi: String,
        emulatorSerial: String,
        sdk: Path = defaultSdk(),
        command: (List<String>, Path?, Boolean) -> String = { args, file, check ->
            LaneHost.command(args, file, check)
        },
        runInstrumentation: (List<String>) -> CommandOutput = { args ->
            val process = ProcessBuilder(args).redirectErrorStream(true).start()
            val text = process.inputStream.bufferedReader().use { it.readText() }
            CommandOutput(text, process.waitFor())
        },
        verifySources: (Path, JsonObject) -> Map<String, JsonObject> = { repository, manifest ->
            AndroidFiles.verifyConsumerSources(repository, manifest)
        },
    ): JsonObject {
        val preparedChecksum = sha256(preparedBytes)
        val commit = command(listOf("git", "-C", posix(root), "rev-parse", "HEAD"), null, true).trim()
        if (commit != prepared.textOrNull("candidate_commit") ||
            command(
                listOf("git", "-C", posix(root), "status", "--porcelain", "--untracked-files=all"),
                null,
                true,
            ).trim().isNotEmpty()
        ) {
            throw IllegalArgumentException(
                "optimized source is dirty or differs from prepared candidate commit",
            )
        }
        val stagedRecords = prepared.getValue("staged").objectOrNull()
            ?: throw IllegalArgumentException("prepared manifest has no staged artifact map")
        val stagedRootRecords = prepared.getValue("staged_roots").objectOrNull()
            ?: throw IllegalArgumentException("prepared manifest has no staged root map")
        for (artifact in stagedRecords.values + stagedRootRecords.values) {
            val record = artifact as JsonObject
            val path = record.textOrNull("path") ?: continue
            if (sha256(Path.of(path)) != record.textOrNull("sha256")) {
                throw IllegalArgumentException("staged AAR checksum changed")
            }
        }
        verifySources(root, prepared)
        val graph = providerGraph.toFile().readText()
        OptimizedEvidence.validateProvider(graph)
        if (Files.getLastModifiedTime(providerGraph) < Files.getLastModifiedTime(preparedPath)) {
            throw IllegalArgumentException("optimized provider graph predates prepared candidate")
        }

        val app = root.resolve("consumers/android-runtime/optimized")
        val apkDirectory = app.resolve("build/outputs/apk/$buildType")
        val testDirectory = app.resolve("build/outputs/apk/androidTest/$buildType")
        val apks = listApks(apkDirectory)
        val testApks = listApks(testDirectory)
        if (apks.size != 1 || testApks.size != 1) {
            throw IllegalArgumentException("optimized app or instrumentation APK missing or duplicated")
        }
        val apk = apks[0]
        val testApk = testApks[0]
        val preparedStamp = Files.getLastModifiedTime(preparedPath)
        if (listOf(apk, testApk).any { Files.getLastModifiedTime(it) < preparedStamp }) {
            throw IllegalArgumentException("optimized APK predates prepared candidate")
        }
        Files.createDirectories(output)
        val adb = RunContract.adbForSerial(posix(sdk), emulatorSerial)
        val identity = guestIdentity(adb, command)
        if (identity["ro.build.version.sdk"] != expectedApi ||
            identity["ro.product.cpu.abi"] != expectedAbi
        ) {
            throw IllegalArgumentException("unexpected emulator: ${pyDictRepr(identity)}")
        }
        val appSnapshot = snapshotArtifact(apk, output.resolve("app.apk"), sha256(apk))
        val testSnapshot = snapshotArtifact(testApk, output.resolve("instrumentation.apk"), sha256(testApk))
        val graphSnapshot = snapshotArtifact(providerGraph, output.resolve("provider-graph.txt"), sha256(providerGraph))
        val result = linkedMapOf<String, JsonElement>()
        result["status"] = JsonPrimitive("FAILED")
        result["candidate_commit"] = JsonPrimitive(commit)
        result["emulator_serial"] = JsonPrimitive(emulatorSerial)
        result["source_tree"] = JsonPrimitive(
            command(listOf("git", "-C", posix(root), "rev-parse", "HEAD^{tree}"), null, true).trim(),
        )
        result["runtime"] = JsonObject(identity.mapValues { JsonPrimitive(it.value) })
        result["build_type"] = JsonPrimitive(buildType)
        result["prepared_manifest"] = buildJsonObject {
            put("path", JsonPrimitive(posix(preparedPath)))
            put("sha256", JsonPrimitive(preparedChecksum))
        }
        for (key in listOf(
            "staged", "staged_roots", "consumer_sources", "generated_consumer_sources",
        )) {
            prepared[key]?.let { result[key] = it }
        }
        result["provider_graph"] = graphSnapshot.toJson()
        result["app_apk"] = appSnapshot.toJson()
        result["test_apk"] = testSnapshot.toJson()
        try {
            if (buildType == "release") {
                val mappingDirectory = app.resolve("build/outputs/mapping/release")
                val evidence = linkedMapOf<String, JsonElement>()
                for (name in listOf("configuration.txt", "mapping.txt", "usage.txt")) {
                    val path = mappingDirectory.resolve(name)
                    evidence[name] = snapshotArtifact(path, output.resolve(name), sha256(path)).toJson()
                }
                val (descriptors, files) = dexEvidence(Path.of(appSnapshot.path), output, sdk, command)
                val mapped = OptimizedEvidence.validateR8(
                    output.resolve("configuration.txt").toFile().readText(),
                    output.resolve("mapping.txt").toFile().readText(),
                    output.resolve("usage.txt").toFile().readText(),
                    descriptors,
                )
                result["r8"] = buildJsonObject {
                    put("files", JsonObject(evidence))
                    put(
                        "mapped_path",
                        JsonObject(
                            mapped.mapValues { (_, value) ->
                                buildJsonObject {
                                    put("name", JsonPrimitive(value.name))
                                    put(
                                        "descriptor",
                                        value.descriptor?.let { JsonPrimitive(it) }
                                            ?: kotlinx.serialization.json.JsonNull,
                                    )
                                }
                            },
                        ),
                    )
                    put("dex", kotlinx.serialization.json.JsonArray(files))
                }
            }
            command(adb + listOf("install", "-r", appSnapshot.path), output.resolve("install-app.txt"), true)
            command(adb + listOf("install", "-r", testSnapshot.path), output.resolve("install-test.txt"), true)
            val pkg = "io.github.rubixhacker.dyn4k.optimized"
            val packagePath = command(
                adb + listOf("shell", "pm", "path", pkg),
                output.resolve("package-path.txt"),
                true,
            ).trim()
            result["package_path"] = JsonPrimitive(packagePath)
            if (!packagePath.startsWith("package:/data/app/")) {
                throw IllegalArgumentException("installed optimized app package path missing")
            }
            command(adb + listOf("shell", "dumpsys", "package", pkg), output.resolve("package.txt"), true)
            command(adb + listOf("logcat", "-c"), null, true)
            command(adb + listOf("shell", "am", "start", "-W", "-n", "$pkg/.OptimizedActivity"), output.resolve("launch.txt"), true)
            val processId = command(adb + listOf("shell", "pidof", pkg), output.resolve("process.txt"), true).trim()
            result["process"] = JsonPrimitive(processId)
            if (processId.isEmpty()) {
                throw IllegalArgumentException("optimized app process absent")
            }
            val runners = command(
                adb + listOf("shell", "pm", "list", "instrumentation"),
                output.resolve("instrumentations.txt"),
                true,
            )
            val matches = runners.lines().filter { "(target=$pkg)" in it }
                .map { it.split(" ")[0].removePrefix("instrumentation:") }
            if (matches.size != 1) {
                throw IllegalArgumentException("optimized instrumentation runner mismatch")
            }
            val executed = runInstrumentation(adb + listOf("shell", "am", "instrument", "-w", "-r") + matches[0])
            output.resolve("instrumentation.txt").toFile().writeText(executed.stdout)
            result["instrumentation_exit_code"] = JsonPrimitive(executed.code)
            result["cases"] = OptimizedEvidence.validateInstalledCase(
                executed.stdout,
                executed.code,
            ).toJson()
            verifySources(root, prepared)
            if (sha256(preparedPath) != preparedChecksum) {
                throw IllegalArgumentException("prepared manifest changed during optimized installed run")
            }
            result["status"] = JsonPrimitive("PASSED")
        } catch (failure: Exception) {
            if (failure !is IllegalArgumentException && failure !is IllegalStateException &&
                failure !is java.io.IOException
            ) {
                throw failure
            }
            result["error"] = JsonPrimitive(failure.message ?: failure.toString())
        } finally {
            command(adb + listOf("logcat", "-d"), output.resolve("logcat.txt"), false)
            output.resolve("result.json").toFile()
                .writeText(PyJson.prettySorted(JsonObject(result)) + "\n")
        }
        return JsonObject(result)
    }

    private fun listApks(directory: Path): List<Path> =
        if (Files.isDirectory(directory)) {
            Files.list(directory).use { stream ->
                stream.filter { it.fileName.toString().endsWith(".apk") }.sorted().toList()
            }
        } else {
            emptyList()
        }

    /** The five guest identity properties the diagnostic route records. */
    fun guestIdentity(
        adb: List<String>,
        command: (List<String>, Path?, Boolean) -> String,
    ): Map<String, String> {
        val identity = linkedMapOf<String, String>()
        for (name in listOf(
            "ro.build.fingerprint", "ro.build.version.sdk", "ro.product.cpu.abi",
            "ro.product.cpu.abilist", "ro.product.model",
        )) {
            identity[name] = command(adb + listOf("shell", "getprop", name), null, true).trim()
        }
        return identity
    }

    /** `--expected-abi` default: the emulator images this route drives. */
    fun defaultSdk(): Path = Path.of(System.getenv("ANDROID_HOME") ?: "/var/home/stewart/Android/Sdk")
}
