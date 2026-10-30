package io.github.rubixhacker.harness.android

import java.nio.file.Path

/**
 * The command-line surfaces of the four Android tools and the two native tools.
 *
 * `argparse` is reproduced only as far as the tools use it: `--name value` pairs, `--name=value`,
 * boolean switches, choice sets, defaults, and required options. A rejected value raises
 * [ArgumentTypeError], which the `:android` Gradle entry points report as a usage error with exit code
 * 2, matching `argparse`.
 */
object Cli {
    /** Parsed options in declaration order. */
    class Options(private val values: Map<String, String>) {
        fun string(name: String): String? = values[name]

        fun required(name: String): String =
            values[name] ?: throw ArgumentTypeError("the following arguments are required: --$name")

        fun integer(name: String): Int = pyInt(required(name))
    }

    class Spec(val switches: Set<String> = emptySet()) {
        private val values = linkedMapOf<String, String>()

        fun parse(argv: List<String>): Options {
            var index = 0
            while (index < argv.size) {
                val token = argv[index]
                if (!token.startsWith("--")) {
                    throw ArgumentTypeError("unrecognized arguments: $token")
                }
                val name = token.removePrefix("--")
                val equals = name.indexOf('=')
                if (equals >= 0) {
                    values[name.substring(0, equals)] = name.substring(equals + 1)
                    index += 1
                } else if (name in switches) {
                    values[name] = "true"
                    index += 1
                } else {
                    if (index + 1 >= argv.size) {
                        throw ArgumentTypeError("argument --$name: expected one argument")
                    }
                    values[name] = argv[index + 1]
                    index += 2
                }
            }
            return Options(values)
        }
    }

    private val API = setOf("21", "36", "37")
    private val ABI = setOf("x86_64", "x86", "arm64-v8a", "armeabi-v7a")

    private fun buildType(options: Options): String {
        val value = options.required("build-type")
        if (value != "debug" && value != "release") {
            throw ArgumentTypeError("argument --build-type: invalid choice: '$value'")
        }
        return value
    }

    private fun api(options: Options): String {
        val value = options.string("expected-api") ?: "36"
        if (value !in API) {
            throw ArgumentTypeError("argument --expected-api: invalid choice: '$value'")
        }
        return value
    }

    private fun abi(options: Options): String {
        val value = options.string("expected-abi") ?: "x86_64"
        if (value !in ABI) {
            throw ArgumentTypeError("argument --expected-abi: invalid choice: '$value'")
        }
        return value
    }

    /** The serial is validated while parsing, before any input is read. */
    private fun serial(options: Options): String =
        RunContract.selectedEmulatorSerial(options.string("emulator-serial") ?: "emulator-5558")

    /** `prepare.py`. */
    fun prepare(argv: List<String>, repo: Path, standardOut: (String) -> Unit): Int {
        val options = Spec().parse(argv)
        val root = (options.string("repo")?.let { Path.of(it) } ?: repo).toAbsolutePath().normalize()
        val verify = options.string("verify-consumers")
        if (verify != null) {
            val manifest = Path.of(verify)
            Prepare.verifyConsumers(root, manifest)
            standardOut(
                "verified ${PrepareContract.CONSUMERS.size} generated consumer sources; " +
                    "manifest sha256 ${sha256(manifest)}",
            )
            return 0
        }
        val output = options.required("output")
        val rootBuildLog = options.required("root-build-log")
        val result = Prepare.prepare(root, Path.of(rootBuildLog))
        val path = Path.of(output)
        path.parent?.let { java.nio.file.Files.createDirectories(it) }
        path.toFile().writeText(PyJson.prettySorted(result) + "\n")
        standardOut(
            "prepared ${result.getValue("portable_classes").let { (it as kotlinx.serialization.json.JsonArray).size }} " +
                "portable test classes",
        )
        return 0
    }

    /** `run.py`. */
    fun run(argv: List<String>, repo: Path, standardOut: (String) -> Unit): Int {
        val options = Spec().parse(argv)
        val root = (options.string("repo")?.let { Path.of(it) } ?: repo).toAbsolutePath().normalize()
        val preparedPath = Path.of(options.required("prepared"))
        val output = Path.of(options.required("output"))
        val buildType = buildType(options)
        val expectedApi = api(options)
        val expectedAbi = abi(options)
        val emulatorSerial = serial(options)

        val preparedBytes = preparedPath.toFile().readBytes()
        val prepared = FullHost.parseJson(preparedBytes)
        val preparedChecksum = sha256(preparedBytes)
        val commit = LaneHost.command(listOf("git", "-C", posix(root), "rev-parse", "HEAD")).trim()
        if (commit != prepared.textOrNull("candidate_commit")) {
            throw IllegalArgumentException("candidate commit differs from prepared artifacts")
        }
        if (prepared["build_jdk"] != BuildIdentity.currentJava(JvmBuildHost).toJson()) {
            throw IllegalArgumentException("diagnostic build JDK identity differs")
        }
        BuildIdentityFiles.verifyBuildLogIdentity(
            prepared.getValue("root_build").objectOrNull()
                ?: throw IllegalArgumentException("diagnostic build JDK identity differs"),
        )
        if (LaneHost.command(
                listOf("git", "-C", posix(root), "status", "--porcelain", "--untracked-files=all"),
            ).trim().isNotEmpty()
        ) {
            throw IllegalArgumentException("candidate source checkout is dirty")
        }
        for (artifact in prepared.objectOrNull("staged").orEmpty().values +
            prepared.objectOrNull("staged_roots").orEmpty().values) {
            val record = artifact as kotlinx.serialization.json.JsonObject
            val path = record.textOrNull("path") ?: continue
            if (sha256(Path.of(path)) != record.textOrNull("sha256")) {
                throw IllegalArgumentException("staged AAR checksum changed")
            }
        }
        for ((source, digest) in prepared.stringMap("consumer_sources").orEmpty()) {
            if (sha256(root.resolve(source)) != digest) {
                throw IllegalArgumentException("consumer source changed: $source")
            }
        }
        AndroidFiles.verifyConsumerSources(root, prepared)
        for (item in listOf(
            prepared.getValue("baseline_jar"),
            prepared.getValue("portable_jar"),
        )) {
            val record = item as kotlinx.serialization.json.JsonObject
            val path = record.textOrNull("path") ?: continue
            if (sha256(Path.of(path)) != record.textOrNull("sha256")) {
                throw IllegalArgumentException("input checksum changed: $path")
            }
        }
        val portable = LaneHost.expectedPortable(root, prepared)
        val sdk = OptimizedHost.defaultSdk()
        val adb = RunContract.adbForSerial(posix(sdk), emulatorSerial)
        val identity = OptimizedHost.guestIdentity(adb) { args, file, check ->
            LaneHost.command(args, file, check)
        }
        if (identity["ro.build.version.sdk"] != expectedApi ||
            identity["ro.product.cpu.abi"] != expectedAbi
        ) {
            throw IllegalArgumentException("unexpected diagnostic emulator: ${pyDictRepr(identity)}")
        }
        if (expectedApi in AndroidCorpus.FINGERPRINTS &&
            identity["ro.build.fingerprint"] != AndroidCorpus.FINGERPRINTS[expectedApi]
        ) {
            throw IllegalArgumentException("unexpected Android image fingerprint: ${pyDictRepr(identity)}")
        }
        java.nio.file.Files.createDirectories(output)
        val lanes = listOf("baseline", "candidate").map { flavor ->
            LaneHost.runLane(
                root,
                prepared,
                portable,
                flavor,
                buildType,
                expectedApi,
                output,
                adb,
                preparedPath,
                preparedChecksum,
            )
        }
        val tree = LaneHost.command(listOf("git", "-C", posix(root), "rev-parse", "HEAD^{tree}")).trim()
        val summary = kotlinx.serialization.json.buildJsonObject {
            put("candidate_commit", kotlinx.serialization.json.JsonPrimitive(commit))
            put("source_tree", kotlinx.serialization.json.JsonPrimitive(tree))
            put(
                "runtime",
                kotlinx.serialization.json.JsonObject(
                    identity.mapValues { kotlinx.serialization.json.JsonPrimitive(it.value) },
                ),
            )
            put("emulator_serial", kotlinx.serialization.json.JsonPrimitive(emulatorSerial))
            put("portable_expected", kotlinx.serialization.json.JsonPrimitive(portable.size))
            put("build_jdk", prepared.getValue("build_jdk"))
            put("root_build", prepared.getValue("root_build"))
            put(
                "prepared_manifest",
                kotlinx.serialization.json.buildJsonObject {
                    put("path", kotlinx.serialization.json.JsonPrimitive(posix(preparedPath)))
                    put("sha256", kotlinx.serialization.json.JsonPrimitive(preparedChecksum))
                },
            )
            put("staged", prepared.getValue("staged"))
            put("baseline_jar", prepared.getValue("baseline_jar"))
            put("staged_roots", prepared.getValue("staged_roots"))
            put("consumer_sources", prepared.getValue("consumer_sources"))
            put("generated_consumer_sources", prepared.getValue("generated_consumer_sources"))
            put("lanes", kotlinx.serialization.json.JsonArray(lanes))
        }
        output.resolve("summary.json").toFile().writeText(PyJson.prettySorted(summary) + "\n")
        standardOut(
            PyJson.compactSorted(
                kotlinx.serialization.json.buildJsonObject {
                    put(
                        "lanes",
                        kotlinx.serialization.json.JsonArray(
                            lanes.map { lane ->
                                kotlinx.serialization.json.buildJsonObject {
                                    put(
                                        "flavor",
                                        lane["flavor"] ?: kotlinx.serialization.json.JsonNull,
                                    )
                                    put(
                                        "status",
                                        lane["status"] ?: kotlinx.serialization.json.JsonNull,
                                    )
                                    put("error", lane["error"] ?: kotlinx.serialization.json.JsonNull)
                                    put("counts", lane["cases"] ?: kotlinx.serialization.json.JsonNull)
                                }
                            },
                        ),
                    )
                    put(
                        "runtime",
                        kotlinx.serialization.json.JsonObject(
                            identity.mapValues { kotlinx.serialization.json.JsonPrimitive(it.value) },
                        ),
                    )
                },
            ),
        )
        return if (lanes.any { it.textOrNull("status") != "DIAGNOSTIC_PASSED" }) 1 else 0
    }

    /** `run_optimized.py`. */
    fun runOptimized(argv: List<String>, repo: Path, standardOut: (String) -> Unit): Int {
        val options = Spec().parse(argv)
        val root = (options.string("repo")?.let { Path.of(it) } ?: repo).toAbsolutePath().normalize()
        val preparedPath = Path.of(options.required("prepared"))
        val providerGraph = Path.of(options.required("provider-graph"))
        val output = Path.of(options.required("output")).toAbsolutePath().normalize()
        val buildType = buildType(options)
        val expectedApi = api(options)
        val expectedAbi = abi(options)
        val emulatorSerial = serial(options)
        val bytes = preparedPath.toFile().readBytes()
        val prepared = FullHost.parseJson(bytes)
        val result = OptimizedHost.run(
            root,
            prepared,
            bytes,
            preparedPath,
            providerGraph,
            output,
            buildType,
            expectedApi,
            expectedAbi,
            emulatorSerial,
        )
        standardOut(
            PyJson.compactSorted(
                kotlinx.serialization.json.buildJsonObject {
                    put("status", result["status"] ?: kotlinx.serialization.json.JsonNull)
                    put("cases", result["cases"] ?: kotlinx.serialization.json.JsonNull)
                    put("error", result["error"] ?: kotlinx.serialization.json.JsonNull)
                },
            ),
        )
        return if (result.textOrNull("status") != "PASSED") 1 else 0
    }

    /** `run_full.py`. */
    fun runFull(argv: List<String>, repo: Path, standardOut: (String) -> Unit): Int {
        val options = Spec(switches = setOf("seal-build")).parse(argv)
        val root = (options.string("repo")?.let { Path.of(it) } ?: repo).toAbsolutePath().normalize()
        val preparedPath = Path.of(options.required("prepared"))
        val providerArtifacts = Path.of(options.required("provider-artifacts"))
        val output = Path.of(options.required("output")).toAbsolutePath().normalize()
        if (options.string("seal-build") != null) {
            val debug = options.string("debug-build-log")
                ?: throw ArgumentTypeError("--seal-build requires both build logs")
            val release = options.string("release-build-log")
                ?: throw ArgumentTypeError("--seal-build requires both build logs")
            val receipt = FullHost.sealBuild(
                root,
                preparedPath,
                providerArtifacts,
                Path.of(debug),
                Path.of(release),
                output,
            )
            standardOut(
                PyJson.compactSorted(
                    kotlinx.serialization.json.buildJsonObject {
                        put("candidate_commit", receipt.getValue("candidate_commit"))
                        put(
                            "artifacts",
                            kotlinx.serialization.json.JsonPrimitive(
                                (receipt.getValue("artifacts") as kotlinx.serialization.json.JsonObject).size,
                            ),
                        )
                    },
                ),
            )
            return 0
        }
        val buildTypeOption = options.string("build-type")
            ?: throw ArgumentTypeError(
                "installed run requires --build-type, --expected-api, and --build-receipt",
            )
        val expectedApiOption = options.string("expected-api")
            ?: throw ArgumentTypeError(
                "installed run requires --build-type, --expected-api, and --build-receipt",
            )
        val buildReceipt = options.string("build-receipt")
            ?: throw ArgumentTypeError(
                "installed run requires --build-type, --expected-api, and --build-receipt",
            )
        if (buildTypeOption != "debug" && buildTypeOption != "release") {
            throw ArgumentTypeError("argument --build-type: invalid choice: '$buildTypeOption'")
        }
        if (expectedApiOption !in API) {
            throw ArgumentTypeError("argument --expected-api: invalid choice: '$expectedApiOption'")
        }
        val expectedAbi = abi(options)
        val emulatorSerial = serial(options)
        val bytes = preparedPath.toFile().readBytes()
        val result = FullHost.run(
            root,
            FullHost.parseJson(bytes),
            bytes,
            preparedPath,
            providerArtifacts,
            Path.of(buildReceipt),
            buildTypeOption,
            expectedApiOption,
            expectedAbi,
            emulatorSerial,
            output,
        )
        standardOut(
            PyJson.compactSorted(
                kotlinx.serialization.json.buildJsonObject {
                    put("status", result["status"] ?: kotlinx.serialization.json.JsonNull)
                    put("error", result["error"] ?: kotlinx.serialization.json.JsonNull)
                    val portable = result.objectOrNull("cases")?.objectOrNull("portable")
                        ?.objectOrNull("cases")?.size ?: 0
                    put("cases", kotlinx.serialization.json.JsonPrimitive(portable))
                },
            ),
        )
        return if (result.textOrNull("status") != "PASSED") 1 else 0
    }
}
