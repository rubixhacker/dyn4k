package io.github.rubixhacker.harness.android

import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.StandardCopyOption
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

/** A finished command: merged stdout and exit code, as `run.command` records them. */
class CommandOutput(val stdout: String, val code: Int)

/** The process, filesystem, and copy adapters behind the diagnostic lane runner. */
object LaneHost {
    /** `run.command`: runs [args], optionally saving merged output, and fails on a nonzero exit. */
    fun command(
        args: List<String>,
        output: Path? = null,
        check: Boolean = true,
        root: Path? = null,
    ): String {
        val builder = ProcessBuilder(args).redirectErrorStream(true)
        if (root != null) builder.directory(root.toFile())
        val process = builder.start()
        val text = process.inputStream.bufferedReader().use { it.readText() }
        val code = process.waitFor()
        if (output != null) {
            output.parent?.let { Files.createDirectories(it) }
            output.toFile().writeText(text)
        }
        if (check && code != 0) {
            throw IllegalStateException(
                "command failed ($code): ${args.joinToString(" ")}: ${text.takeLast(1200)}",
            )
        }
        return text
    }

    /** `run.apk_path`: the one APK in the flavor and build-type output directory. */
    fun apkPath(app: Path, flavor: String, buildType: String, test: Boolean): Path {
        var directory = app.resolve("build/outputs/apk")
        directory = if (test) {
            directory.resolve("androidTest/$flavor/$buildType")
        } else {
            directory.resolve("$flavor/$buildType")
        }
        val files = if (Files.isDirectory(directory)) {
            Files.list(directory).use { stream ->
                stream.filter { it.fileName.toString().endsWith(".apk") }.sorted().toList()
            }
        } else {
            emptyList()
        }
        if (files.size != 1) {
            throw IllegalArgumentException("expected one APK at $directory, found ${files.size}")
        }
        return files[0]
    }

    /** `run.verify_installed_apk`: the pulled device bytes equal the built APK. */
    fun verifyInstalledApk(path: Path, expectedSha256: String): JsonObject {
        val observed = sha256(path)
        if (observed != expectedSha256) {
            throw IllegalArgumentException("installed APK differs from built APK")
        }
        return buildJsonObject {
            put("path", JsonPrimitive(posix(path)))
            put("sha256", JsonPrimitive(observed))
        }
    }

    /** `run.expected_portable`: the frozen portable case ids pinned by the raw JVM XML. */
    fun expectedPortable(root: Path, prepared: JsonObject): Set<String> =
        AndroidFiles.verifyXmlPins(root, prepared).caseIds.toSet()

    /** `run.instrumentation_filter`: the decision, with the API 21 selection file written. */
    fun instrumentationFilter(
        prepared: JsonObject,
        flavor: String,
        buildType: String,
        expectedApi: String,
        directory: Path,
    ): InstrumentationSelection {
        val portable = prepared.stringList("portable_classes")
            ?: throw IllegalArgumentException("prepared manifest has no portable class list")
        val selection = RunContract.instrumentationFilter(
            portable,
            flavor,
            buildType,
            expectedApi,
            posix(directory),
        )
        if (selection.selectionPath != null) {
            val path = Path.of(selection.selectionPath)
            path.parent?.let { Files.createDirectories(it) }
            path.toFile().writeText(selection.selectionText!!)
        }
        return selection
    }

    /** `run.run_lane`: one installed diagnostic lane, recording its evidence even when it fails. */
    fun runLane(
        root: Path,
        prepared: JsonObject,
        portable: Set<String>,
        flavor: String,
        buildType: String,
        expectedApi: String,
        evidenceRoot: Path,
        adb: List<String>,
        preparedPath: Path,
        preparedChecksum: String,
        verifySources: (Path, JsonObject) -> Map<String, JsonObject> = { repository, manifest ->
            AndroidFiles.verifyConsumerSources(repository, manifest)
        },
        apkPath: (Path, String, String, Boolean) -> Path = { app, flavor, buildType, test ->
            LaneHost.apkPath(app, flavor, buildType, test)
        },
        command: (List<String>, Path?, Boolean) -> String = { args, output, check ->
            LaneHost.command(args, output, check)
        },
        runInstrumentation: (List<String>) -> CommandOutput = { args ->
            val process = ProcessBuilder(args).redirectErrorStream(true).start()
            val text = process.inputStream.bufferedReader().use { it.readText() }
            CommandOutput(text, process.waitFor())
        },
    ): JsonObject {
        val app = root.resolve("consumers/android-runtime/app")
        val apk = apkPath(app, flavor, buildType, false)
        val testApk = apkPath(app, flavor, buildType, true)
        val pkg = "io.github.rubixhacker.dyn4k.runtime.$flavor"
        val directory = evidenceRoot.resolve("$flavor-$buildType")
        Files.createDirectories(directory)
        val appCopy = directory.resolve("app.apk")
        val testCopy = directory.resolve("instrumentation.apk")
        Files.copy(apk, appCopy, StandardCopyOption.REPLACE_EXISTING)
        Files.copy(testApk, testCopy, StandardCopyOption.REPLACE_EXISTING)
        val result = linkedMapOf<String, JsonElement>()
        result["flavor"] = JsonPrimitive(flavor)
        result["build_type"] = JsonPrimitive(buildType)
        result["package"] = JsonPrimitive(pkg)
        // The serial is bound before any install so a mis-selected emulator cannot be recorded as evidence.
        result["emulator_serial"] = JsonPrimitive(RunContract.selectedEmulatorSerial(adb[4]))
        result["app_apk"] = buildJsonObject {
            put("path", JsonPrimitive(posix(appCopy)))
            put("sha256", JsonPrimitive(sha256(appCopy)))
        }
        result["test_apk"] = buildJsonObject {
            put("path", JsonPrimitive(posix(testCopy)))
            put("sha256", JsonPrimitive(sha256(testCopy)))
        }
        for (key in listOf(
            "candidate_commit", "build_jdk", "root_build", "staged", "baseline_jar",
            "staged_roots", "consumer_sources", "generated_consumer_sources", "portable_jar",
        )) {
            prepared[key]?.let { result[key] = it }
        }
        result["prepared_manifest"] = buildJsonObject {
            put("path", JsonPrimitive(posix(preparedPath)))
            put("sha256", JsonPrimitive(preparedChecksum))
        }
        result["status"] = JsonPrimitive("FAILED")
        try {
            verifySources(root, prepared)
            if (Files.getLastModifiedTime(apk) < Files.getLastModifiedTime(preparedPath) ||
                Files.getLastModifiedTime(testApk) < Files.getLastModifiedTime(preparedPath)
            ) {
                throw IllegalArgumentException("APK predates prepared candidate inputs")
            }
            if (sha256(apk) != (result.getValue("app_apk") as JsonObject).textOrNull("sha256") ||
                sha256(testApk) != (result.getValue("test_apk") as JsonObject).textOrNull("sha256")
            ) {
                throw IllegalArgumentException("built APK changed during diagnostic snapshot")
            }
            if (buildType == "release") {
                val mapping = app.resolve("build/outputs/mapping/${flavor}Release/mapping.txt")
                if (!Files.isRegularFile(mapping) || Files.size(mapping) == 0L) {
                    throw IllegalArgumentException("R8 mapping missing")
                }
                result["r8_mapping"] = buildJsonObject {
                    put("path", JsonPrimitive(posix(mapping)))
                    put("sha256", JsonPrimitive(sha256(mapping)))
                }
            }
            command(adb + listOf("install", "-r", posix(appCopy)), directory.resolve("install-app.txt"), true)
            command(adb + listOf("install", "-r", posix(testCopy)), directory.resolve("install-test.txt"), true)
            val packagePath = command(
                adb + listOf("shell", "pm", "path", pkg),
                directory.resolve("package-path.txt"),
                true,
            ).trim()
            result["package_path"] = JsonPrimitive(packagePath)
            if (!PACKAGE_PATH.matches(packagePath)) {
                throw IllegalArgumentException("installed package path absent")
            }
            command(
                adb + listOf("pull", packagePath.removePrefix("package:"), posix(directory.resolve("installed-base.apk"))),
                directory.resolve("pull-app.txt"),
                true,
            )
            result["installed_apk"] = verifyInstalledApk(
                directory.resolve("installed-base.apk"),
                (result.getValue("app_apk") as JsonObject).textOrNull("sha256")!!,
            )
            val testPackagePath = command(
                adb + listOf("shell", "pm", "path", "$pkg.test"),
                directory.resolve("test-package-path.txt"),
                true,
            ).trim()
            result["test_package_path"] = JsonPrimitive(testPackagePath)
            if (!PACKAGE_PATH.matches(testPackagePath)) {
                throw IllegalArgumentException("installed instrumentation package path absent")
            }
            command(
                adb + listOf(
                    "pull",
                    testPackagePath.removePrefix("package:"),
                    posix(directory.resolve("installed-instrumentation.apk")),
                ),
                directory.resolve("pull-instrumentation.txt"),
                true,
            )
            result["installed_test_apk"] = verifyInstalledApk(
                directory.resolve("installed-instrumentation.apk"),
                (result.getValue("test_apk") as JsonObject).textOrNull("sha256")!!,
            )
            result["package_info"] = JsonPrimitive(
                command(
                    adb + listOf("shell", "dumpsys", "package", pkg),
                    directory.resolve("package.txt"),
                    true,
                ).take(8000),
            )
            command(adb + listOf("logcat", "-c"), null, true)
            command(
                adb + listOf(
                    "shell", "am", "start", "-W", "-n",
                    "$pkg/io.github.rubixhacker.dyn4k.runtime.RuntimeActivity",
                ),
                directory.resolve("launch.txt"),
                true,
            )
            val processId = command(
                adb + listOf("shell", "pidof", pkg),
                directory.resolve("process.txt"),
                true,
            ).trim()
            result["process"] = JsonPrimitive(processId)
            if (processId.isEmpty()) {
                throw IllegalArgumentException("installed app process absent")
            }
            val instrumentation = command(
                adb + listOf("shell", "pm", "list", "instrumentation"),
                directory.resolve("instrumentations.txt"),
                true,
            )
            val runners = instrumentation.lines().filter { "(target=$pkg)" in it }
                .map { it.split(" ")[0].removePrefix("instrumentation:") }
            if (runners.size != 1) {
                throw IllegalArgumentException("instrumentation runner mismatch: $runners")
            }
            val selection = instrumentationFilter(prepared, flavor, buildType, expectedApi, directory)
            result["selected_classes"] = buildJsonArrayOfStrings(selection.classes)
            var selectionHash: String? = null
            if (selection.selectionPath != null) {
                val selectionPath = Path.of(selection.selectionPath)
                selectionHash = sha256(selectionPath)
                result["selection_file"] = buildJsonObject {
                    put("path", JsonPrimitive(posix(selectionPath)))
                    put("sha256", JsonPrimitive(selectionHash))
                    put("device_path", JsonPrimitive(selection.devicePath!!))
                }
                command(
                    adb + listOf("push", posix(selectionPath), selection.devicePath!!),
                    directory.resolve("push-selected-classes.txt"),
                    true,
                )
                val pulled = directory.resolve("installed-selected-classes.txt")
                command(
                    adb + listOf("pull", selection.devicePath!!, posix(pulled)),
                    directory.resolve("pull-selected-classes.txt"),
                    true,
                )
                if (sha256(selectionPath) != selectionHash || sha256(pulled) != selectionHash) {
                    throw IllegalArgumentException(
                        "installed test class selection differs from prepared classes",
                    )
                }
            }
            val instrument = runInstrumentation(
                adb + listOf("shell", "am", "instrument", "-w", "-r") + selection.arguments +
                    runners[0],
            )
            directory.resolve("instrumentation.txt").toFile().writeText(instrument.stdout)
            result["instrumentation_exit_code"] = JsonPrimitive(instrument.code)
            val parsed = Evidence.parseInstrumentation(instrument.stdout)
            result["cases"] = parsed.toJson()
            val expectedInstrumentation = LinkedHashSet(RunContract.CONSUMER_CASES)
            if (flavor == "candidate") {
                expectedInstrumentation +=
                    "io.github.rubixhacker.dyn4k.runtime.StagedKotlinConsumerTest#sharedMutableIdentity"
                expectedInstrumentation += portable.map { it.substringAfter(":") }
            }
            Evidence.validateLane(parsed, emptySet(), expectedInstrumentation, instrument.code)
            if (selectionHash != null && sha256(Path.of(selection.selectionPath!!)) != selectionHash) {
                throw IllegalArgumentException("test class selection changed during installed run")
            }
            if (flavor == "candidate") {
                result["portable_case_ids"] = buildJsonArrayOfStrings(portable.sorted())
            }
            verifySources(root, prepared)
            if (sha256(preparedPath) != preparedChecksum) {
                throw IllegalArgumentException("prepared manifest changed during installed run")
            }
            result["status"] = JsonPrimitive("DIAGNOSTIC_PASSED")
        } catch (failure: Exception) {
            if (failure !is IllegalArgumentException && failure !is IllegalStateException) throw failure
            result["error"] = JsonPrimitive(failure.message ?: failure.toString())
        } finally {
            command(adb + listOf("logcat", "-d"), directory.resolve("logcat.txt"), false)
            directory.resolve("result.json").toFile()
                .writeText(PyJson.prettySorted(JsonObject(result)) + "\n")
        }
        return JsonObject(result)
    }

    private val PACKAGE_PATH = Regex("""package:/data/app/[^\n]+/base\.apk""")

    private fun buildJsonArrayOfStrings(values: List<String>): JsonElement =
        kotlinx.serialization.json.JsonArray(values.map { JsonPrimitive(it) })
}
