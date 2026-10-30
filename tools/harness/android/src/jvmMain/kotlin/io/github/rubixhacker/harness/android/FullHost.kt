package io.github.rubixhacker.harness.android

import java.nio.file.Files
import java.nio.file.Path
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonObject

/** The resolved provider sections of one runtime dependency graph. */
class ProviderSections(val sections: Map<String, JsonElement>) {
    fun toJson(): JsonObject = JsonObject(sections)
}

object FullHost {
    /**
     * `run_full.validate_provider_artifacts`: both variants resolve the exact frozen graph, no second
     * baseline provider appears, and the staged AAR bytes are the prepared ones.
     */
    fun validateProviderArtifacts(graph: String, prepared: JsonObject): JsonObject {
        val staged = prepared.getValue("staged").objectOrNull()
            ?: throw IllegalArgumentException("prepared manifest has no staged artifact map")
        val sections = linkedMapOf<String, JsonElement>()
        for (variant in listOf("debug", "release")) {
            val components = Regex("(?m)^DYN4K_GRAPH_COMPONENT $variant (\\S+)${'$'}")
                .findAll(graph).map { it.groupValues[1] }.toList()
            val edges = Regex("(?m)^DYN4K_GRAPH_EDGE $variant (\\S+ \\S+)${'$'}")
                .findAll(graph).map { it.groupValues[1] }.toList()
            val artifacts = Regex("(?m)^DYN4K_GRAPH_ARTIFACT $variant (\\S+) (\\S+)${'$'}")
                .findAll(graph).map { it.groupValues[1] to it.groupValues[2] }.toList()
            val begin = "DYN4K_GRAPH_BEGIN $variant"
            val end = "DYN4K_GRAPH_END $variant ${components.size} ${edges.size} ${artifacts.size}"
            if (count(graph, begin) != 1 || count(graph, end) != 1 ||
                components.size != components.toSet().size ||
                components.toSet() != RunFullContract.GRAPH_COMPONENTS ||
                edges.size != edges.toSet().size ||
                edges.toSet() != RunFullContract.GRAPH_EDGES ||
                artifacts.size != artifacts.toSet().size ||
                artifacts.map { it.first }.toSet() != RunFullContract.GRAPH_ARTIFACTS
            ) {
                throw IllegalArgumentException("incomplete or wrong $variant runtime dependency graph")
            }
            val providers = linkedMapOf<String, JsonElement>()
            for ((coordinate, pathText) in artifacts) {
                val parts = coordinate.split(":")
                if (parts.size != 3) {
                    throw IllegalArgumentException("not enough values to unpack: $coordinate")
                }
                val (group, artifact) = parts
                if (group == "org.dyn4j" || artifact == "dyn4j") {
                    throw IllegalArgumentException("second baseline provider in runtime graph")
                }
                if (group == RunFullContract.PROVIDER_GROUP) {
                    if (coordinate !=
                        "${RunFullContract.PROVIDER_GROUP}:$artifact:${RunFullContract.PROVIDER_VERSION}" ||
                        artifact !in staged
                    ) {
                        throw IllegalArgumentException("wrong staged provider coordinates")
                    }
                    val path = Path.of(pathText)
                    val stagedSha = (staged.getValue(artifact) as JsonObject).textOrNull("sha256")
                    if (!pathText.endsWith(".aar") || sha256(path) != stagedSha) {
                        throw IllegalArgumentException("wrong resolved staged AAR: $artifact")
                    }
                    providers[artifact] = buildJsonObject {
                        put("coordinate", JsonPrimitive(coordinate))
                        put("path", JsonPrimitive(pathText))
                        put("sha256", JsonPrimitive(sha256(path)))
                    }
                }
            }
            if (providers.keys != staged.keys) {
                throw IllegalArgumentException("wrong staged AAR provider set")
            }
            sections[variant] = buildJsonObject {
                put("components", JsonPrimitive(components.size))
                put("edges", JsonPrimitive(edges.size))
                put("artifacts", JsonPrimitive(artifacts.size))
                put("providers", JsonObject(providers))
            }
        }
        val debugProviders = sections.getValue("debug").objectOrNull()?.get("providers")
        val releaseProviders = sections.getValue("release").objectOrNull()?.get("providers")
        if (debugProviders != releaseProviders) {
            throw IllegalArgumentException("debug and release provider bytes differ")
        }
        return JsonObject(sections)
    }

    private fun count(haystack: String, needle: String): Int {
        var count = 0
        var index = haystack.indexOf(needle)
        while (index >= 0) {
            count += 1
            index = haystack.indexOf(needle, index + needle.length)
        }
        return count
    }

    /** `run_full.apk_path`: the one APK for a build type, under the app or instrumentation directory. */
    fun apkPath(app: Path, buildType: String, test: Boolean = false): Path {
        val directory = app.resolve("build/outputs/apk")
            .resolve(if (test) "androidTest/$buildType" else buildType)
        val found = if (Files.isDirectory(directory)) {
            Files.list(directory).use { stream ->
                stream.filter { it.fileName.toString().endsWith(".apk") }.sorted().toList()
            }
        } else {
            emptyList()
        }
        if (found.size != 1) {
            throw IllegalArgumentException("full app APK missing or ambiguous: $directory")
        }
        return found[0]
    }

    /** `run_full.build_artifacts`: every build output the receipt seals. */
    fun buildArtifacts(app: Path, providerArtifacts: Path): Map<String, Path> {
        val paths = linkedMapOf<String, Path>()
        for (build in listOf("debug", "release")) {
            for (kind in listOf("app", "test")) {
                paths["$kind-$build-apk"] = apkPath(app, build, kind == "test")
            }
        }
        for (name in listOf("configuration.txt", "mapping.txt", "usage.txt")) {
            paths[name] = app.resolve("build/outputs/mapping/release/$name")
        }
        paths["provider-artifacts"] = providerArtifacts
        return paths
    }

    /** `run_full.seal_build`: the APK and R8 build receipt for one candidate. */
    fun sealBuild(
        root: Path,
        preparedPath: Path,
        providerArtifacts: Path,
        debugBuildLog: Path,
        releaseBuildLog: Path,
        output: Path,
    ): JsonObject {
        val preparedBytes = preparedPath.toFile().readBytes()
        val prepared = parseJson(preparedBytes)
        val (commit, _, _) = verifyCandidate(root, prepared)
        validateProviderArtifacts(providerArtifacts.toFile().readText(), prepared)
        val providerBuild = BuildIdentityFiles.buildLogIdentity(providerArtifacts, requireMarker = true)
        val buildLogs = buildJsonObject {
            put("debug", BuildIdentityFiles.buildLogIdentity(debugBuildLog).toJson())
            put("release", BuildIdentityFiles.buildLogIdentity(releaseBuildLog).toJson())
            put("provider", providerBuild.toJson())
        }
        val paths = buildArtifacts(root.resolve("consumers/android-runtime/full"), providerArtifacts)
        if (paths.values.any { Files.getLastModifiedTime(it) < Files.getLastModifiedTime(preparedPath) }) {
            throw IllegalArgumentException("full build artifact predates prepared candidate")
        }
        val artifacts = buildJsonObject {
            for ((name, path) in paths) {
                put(
                    name,
                    buildJsonObject {
                        put("path", JsonPrimitive(posix(path)))
                        put("sha256", JsonPrimitive(sha256(path)))
                    },
                )
            }
        }
        val receipt = buildJsonObject {
            put("candidate_commit", JsonPrimitive(commit))
            put("prepared_sha256", JsonPrimitive(sha256(preparedBytes)))
            put("build_jdk", prepared.getValue("build_jdk"))
            put("build_logs", buildLogs)
            put("artifacts", artifacts)
        }
        output.parent?.let { Files.createDirectories(it) }
        output.toFile().writeText(PyJson.prettySorted(receipt) + "\n")
        return receipt
    }

    /**
     * `run_full.verify_build_receipt`: the sealed receipt still describes the prepared manifest, the
     * pinned build identity, and every build artifact on disk.
     */
    fun verifyBuildReceipt(
        root: Path,
        preparedPath: Path,
        providerArtifacts: Path,
        receiptPath: Path,
        currentJava: () -> BuildJdk = { BuildIdentity.currentJava(JvmBuildHost) },
        command: (List<String>, Path?, Boolean) -> String = { args, output, check ->
            LaneHost.command(args, output, check)
        },
        buildArtifacts: (Path, Path) -> Map<String, Path> = { app, provider ->
            FullHost.buildArtifacts(app, provider)
        },
    ): JsonObject {
        val receipt = parseJson(receiptPath.toFile().readBytes())
        val prepared = parseJson(preparedPath.toFile().readBytes())
        if (receipt["build_jdk"] != prepared["build_jdk"] ||
            receipt["build_jdk"] != currentJava().toJson() ||
            receipt.objectOrNull("build_logs")?.keys != setOf("debug", "release", "provider")
        ) {
            throw IllegalArgumentException("full APK build JDK identity differs")
        }
        for ((name, element) in receipt.getValue("build_logs").objectOrNull()!!) {
            val record = element.objectOrNull() ?: JsonObject(emptyMap())
            if (name == "provider" && record.textOrNull("path") != posix(providerArtifacts)) {
                throw IllegalArgumentException("provider graph build log differs")
            }
            BuildIdentityFiles.verifyBuildLogIdentity(record, requireMarker = name == "provider")
        }
        if (receipt.textOrNull("candidate_commit") !=
            command(listOf("git", "-C", posix(root), "rev-parse", "HEAD"), null, true).trim() ||
            receipt.textOrNull("prepared_sha256") != sha256(preparedPath)
        ) {
            throw IllegalArgumentException("full APK build receipt is stale")
        }
        val paths = buildArtifacts(root.resolve("consumers/android-runtime/full"), providerArtifacts)
        if (receipt.objectOrNull("artifacts")?.keys != paths.keys) {
            throw IllegalArgumentException("full APK build receipt artifact set differs")
        }
        for ((name, path) in paths) {
            val expected = buildJsonObject {
                put("path", JsonPrimitive(posix(path)))
                put("sha256", JsonPrimitive(sha256(path)))
            }
            if (receipt.getValue("artifacts").objectOrNull()!![name] != expected) {
                throw IllegalArgumentException("wrong APK or R8 build artifact: $name")
            }
        }
        return receipt
    }

    /** `run_full.verify_candidate`: the prepared inputs still describe a clean candidate checkout. */
    fun verifyCandidate(root: Path, prepared: JsonObject): Triple<String, Suite, JvmXmlEvidence> {
        if (prepared["build_jdk"] != BuildIdentity.currentJava(JvmBuildHost).toJson()) {
            throw IllegalArgumentException("prepared JDK identity differs")
        }
        // Python indexes `prepared["root_build"]`, so a missing record is a failure, not a skip.
        BuildIdentityFiles.verifyBuildLogIdentity(
            prepared.getValue("root_build").objectOrNull()
                ?: throw IllegalArgumentException("prepared JDK identity differs"),
        )
        val commit = LaneHost.command(listOf("git", "-C", posix(root), "rev-parse", "HEAD")).trim()
        if (prepared.textOrNull("candidate_commit") != commit ||
            LaneHost.command(
                listOf("git", "-C", posix(root), "status", "--porcelain", "--untracked-files=all"),
            ).trim().isNotEmpty()
        ) {
            throw IllegalArgumentException(
                "full optimized source is dirty or differs from prepared candidate",
            )
        }
        val suite = AndroidFiles.loadSuite(root)
        val jvmXml = AndroidFiles.verifyXmlPins(root, prepared)
        AndroidFiles.verifyFullInputs(root, suite.cases, prepared.objectOrNull("full_inputs"))
        AndroidFiles.verifyConsumerSources(root, prepared)
        AndroidFiles.verifyFullConsumerSources(root, prepared)
        val inputs = mutableListOf<JsonElement>()
        inputs += prepared.objectOrNull("staged")?.values.orEmpty()
        inputs += prepared.objectOrNull("staged_roots")?.values.orEmpty()
        prepared["baseline_jar"]?.let { inputs += it }
        prepared["portable_jar"]?.let { inputs += it }
        for (element in inputs) {
            val record = element as JsonObject
            val path = record.textOrNull("path") ?: continue
            if (sha256(Path.of(path)) != record.textOrNull("sha256")) {
                throw IllegalArgumentException("prepared input changed: $path")
            }
        }
        return Triple(commit, suite, jvmXml)
    }

    /** `run_full.run`: the full installed route for one build type and emulator. */
    fun run(
        root: Path,
        prepared: JsonObject,
        preparedBytes: ByteArray,
        preparedPath: Path,
        providerArtifacts: Path,
        buildReceipt: Path,
        buildType: String,
        expectedApi: String,
        expectedAbi: String,
        emulatorSerial: String,
        output: Path,
        sdk: Path = OptimizedHost.defaultSdk(),
        command: (List<String>, Path?, Boolean) -> String = { args, file, check ->
            LaneHost.command(args, file, check)
        },
        runInstrumentation: (List<String>) -> CommandOutput = { args ->
            val process = ProcessBuilder(args).redirectErrorStream(true).start()
            val text = process.inputStream.bufferedReader().use { it.readText() }
            CommandOutput(text, process.waitFor())
        },
    ): JsonObject {
        val preparedSha = sha256(preparedBytes)
        val (commit, suite, jvmXml) = verifyCandidate(root, prepared)
        val graph = providerArtifacts.toFile().readText()
        val provider = validateProviderArtifacts(graph, prepared)
        if (Files.getLastModifiedTime(providerArtifacts) < Files.getLastModifiedTime(preparedPath)) {
            throw IllegalArgumentException("provider artifact receipt predates prepared candidate")
        }
        verifyBuildReceipt(root, preparedPath, providerArtifacts, buildReceipt)
        val app = root.resolve("consumers/android-runtime/full")
        val apk = apkPath(app, buildType, test = false)
        val testApk = apkPath(app, buildType, test = true)
        if (listOf(apk, testApk).any { Files.getLastModifiedTime(it) < Files.getLastModifiedTime(preparedPath) }) {
            throw IllegalArgumentException("full app APK predates prepared candidate")
        }
        val adb = RunContract.adbForSerial(posix(sdk), emulatorSerial)
        val identity = OptimizedHost.guestIdentity(adb, command)
        RunFullContract.validateRuntime(
            identity,
            expectedApi,
            expectedAbi,
            command(adb + listOf("shell", "getprop", "sys.boot_completed"), null, true).trim(),
        )
        Files.createDirectories(output)
        val appCopy = OptimizedHost.snapshotArtifact(apk, output.resolve("app.apk"), sha256(apk))
        val testCopy = OptimizedHost.snapshotArtifact(testApk, output.resolve("instrumentation.apk"), sha256(testApk))
        val graphCopy = OptimizedHost.snapshotArtifact(
            providerArtifacts,
            output.resolve("provider-artifacts.txt"),
            sha256(providerArtifacts),
        )
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
            put("sha256", JsonPrimitive(preparedSha))
        }
        result["build_receipt"] = buildJsonObject {
            put("path", JsonPrimitive(posix(buildReceipt)))
            put("sha256", JsonPrimitive(sha256(buildReceipt)))
        }
        result["build_jdk"] = prepared.getValue("build_jdk")
        result["build_logs"] = parseJson(buildReceipt.toFile().readBytes()).getValue("build_logs")
        result["suite_manifest"] = prepared.getValue("suite_manifest")
        result["jvm_xml"] = jvmXml.toJson()
        result["staged"] = prepared.getValue("staged")
        result["resolved_providers"] = provider
        result["staged_roots"] = prepared.getValue("staged_roots")
        result["provider_artifacts"] = graphCopy.toJson()
        result["app_apk"] = appCopy.toJson()
        result["test_apk"] = testCopy.toJson()
        result["portable_jar"] = prepared.getValue("portable_jar")
        try {
            val (descriptors, dexFiles) = OptimizedHost.dexEvidence(Path.of(appCopy.path), output, sdk, command)
            result["dex"] = JsonArray(dexFiles)
            if (buildType == "release") {
                val debugApk = apkPath(app, "debug", test = false)
                val debugCopy = OptimizedHost.snapshotArtifact(
                    debugApk,
                    output.resolve("debug-app.apk"),
                    sha256(debugApk),
                )
                Files.createDirectories(output.resolve("debug-dex"))
                val (debugDescriptors, debugDexFiles) = OptimizedHost.dexEvidence(
                    Path.of(debugCopy.path),
                    output.resolve("debug-dex"),
                    sdk,
                    command,
                )
                result["debug_app_apk"] = debugCopy.toJson()
                result["debug_dex"] = JsonArray(debugDexFiles)
                val mappingDirectory = app.resolve("build/outputs/mapping/release")
                val r8Files = buildJsonObject {
                    for (name in listOf("configuration.txt", "mapping.txt", "usage.txt")) {
                        val source = mappingDirectory.resolve(name)
                        put(name, OptimizedHost.snapshotArtifact(source, output.resolve(name), sha256(source)).toJson())
                    }
                }
                val allowed = suite.cases.filter { it.scope == "portable" }.mapTo(linkedSetOf()) { it.classname }
                allowed += AndroidCorpus.REFLECTIVE_FILTER_TYPES
                val transformation = FullEvidence.validateFullR8(
                    output.resolve("configuration.txt").toFile().readText(),
                    output.resolve("mapping.txt").toFile().readText(),
                    output.resolve("usage.txt").toFile().readText(),
                    debugDescriptors,
                    descriptors,
                    allowedTestClasses = allowed,
                )
                result["r8"] = buildJsonObject {
                    put("files", r8Files)
                    put("transformation", transformation.toJson())
                }
            }
            command(adb + listOf("install", "-r", appCopy.path), output.resolve("install-app.txt"), true)
            command(adb + listOf("install", "-r", testCopy.path), output.resolve("install-test.txt"), true)
            val pkg = "io.github.rubixhacker.dyn4k.full"
            val packagePath = command(adb + listOf("shell", "pm", "path", pkg), output.resolve("package-path.txt"), true).trim()
            if (!Regex("""package:/data/app/[^\n]+/base\.apk""").matches(packagePath)) {
                throw IllegalArgumentException("installed full app package path is absent")
            }
            val remoteApk = packagePath.removePrefix("package:")
            command(adb + listOf("pull", remoteApk, posix(output.resolve("installed-base.apk"))), output.resolve("pull-app.txt"), true)
            result["installed_apk"] = LaneHost.verifyInstalledApk(
                output.resolve("installed-base.apk"),
                appCopy.sha256,
            )
            result["package_path"] = JsonPrimitive(packagePath)
            val testPackagePath = command(
                adb + listOf("shell", "pm", "path", "$pkg.test"),
                output.resolve("test-package-path.txt"),
                true,
            ).trim()
            if (!Regex("""package:/data/app/[^\n]+/base\.apk""").matches(testPackagePath)) {
                throw IllegalArgumentException("installed full instrumentation package path is absent")
            }
            command(
                adb + listOf(
                    "pull",
                    testPackagePath.removePrefix("package:"),
                    posix(output.resolve("installed-instrumentation.apk")),
                ),
                output.resolve("pull-instrumentation.txt"),
                true,
            )
            result["installed_test_apk"] = LaneHost.verifyInstalledApk(
                output.resolve("installed-instrumentation.apk"),
                testCopy.sha256,
            )
            result["test_package_path"] = JsonPrimitive(testPackagePath)
            command(adb + listOf("shell", "dumpsys", "package", pkg), output.resolve("package.txt"), true)
            command(adb + listOf("logcat", "-c"), null, true)
            command(adb + listOf("shell", "am", "start", "-W", "-n", "$pkg/.FullActivity"), output.resolve("launch.txt"), true)
            val beforePid = if (expectedApi == "21") {
                RunFullContract.api21ProcessPid(
                    command(adb + listOf("shell", "ps"), output.resolve("process-before.txt"), true),
                    pkg,
                )
            } else {
                command(adb + listOf("shell", "pidof", pkg), output.resolve("process-before.txt"), true).trim()
            }
            if (beforePid.isNullOrEmpty()) {
                throw IllegalArgumentException("full app process absent before instrumentation")
            }
            val runners = command(
                adb + listOf("shell", "pm", "list", "instrumentation"),
                output.resolve("instrumentations.txt"),
                true,
            )
            val matches = runners.lines().filter { "(target=$pkg)" in it }
                .map { it.split(" ")[0].removePrefix("instrumentation:") }
            if (matches.size != 1) {
                throw IllegalArgumentException("full instrumentation runner mismatch")
            }
            val executed = runInstrumentation(adb + listOf("shell", "am", "instrument", "-w", "-r") + matches[0])
            val rawPath = output.resolve("instrumentation.txt")
            rawPath.toFile().writeText(executed.stdout)
            result["instrumentation"] = buildJsonObject {
                put("path", JsonPrimitive(posix(rawPath)))
                put("sha256", JsonPrimitive(sha256(rawPath)))
                put("exit_code", JsonPrimitive(executed.code))
                put("runner", JsonPrimitive(matches[0]))
            }
            val expected = jvmXml.caseIds.toMutableSet()
            expected += AndroidCorpus.JAVA_JOURNEYS.map { "external-java:$it#main" }
            expected += "external-kotlin:${AndroidCorpus.KOTLIN_JOURNEY}#run"
            result["cases"] = FullEvidence.validateFullInstalled(
                executed.stdout,
                expected,
                executed.code,
            ).toJson()
            val log = command(adb + listOf("logcat", "-d"), output.resolve("logcat.txt"), true)
            val instrumentationPid = if (expectedApi == "21") {
                RunFullContract.validateApi21ProcessLog(log, pkg, expectedAbi, beforePid)
            } else {
                FullEvidence.validateFullProcessLog(log, pkg)
            }
            val afterPid: String? = if (expectedApi == "21") {
                RunFullContract.api21ProcessPid(
                    command(adb + listOf("shell", "ps"), output.resolve("process-after.txt"), true),
                    pkg,
                    required = false,
                )
            } else {
                command(adb + listOf("shell", "pidof", pkg), output.resolve("process-after.txt"), false).trim()
            }
            if (expectedApi == "21" && afterPid != null) {
                throw IllegalArgumentException("API 21 app process remains after instrumentation shutdown")
            }
            result["process"] = buildJsonObject {
                put("before", JsonPrimitive(beforePid))
                put("instrumentation", JsonPrimitive(instrumentationPid))
                put("after", afterPid?.let { JsonPrimitive(it) } ?: JsonNull)
            }
            verifyCandidate(root, prepared)
            if (sha256(preparedPath) != preparedSha ||
                sha256(providerArtifacts) != graphCopy.sha256
            ) {
                throw IllegalArgumentException("full optimized input changed during installed run")
            }
            verifyBuildReceipt(root, preparedPath, providerArtifacts, buildReceipt)
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

    internal fun parseJson(bytes: ByteArray): JsonObject =
        kotlinx.serialization.json.Json.parseToJsonElement(bytes.decodeToString()).jsonObject
}
