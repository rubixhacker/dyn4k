package io.github.rubixhacker.harness.compatibility

import io.github.rubixhacker.harness.contract.CanonicalJson
import io.github.rubixhacker.harness.contract.Sha256
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import java.nio.file.Files
import java.nio.file.Path
import java.util.Comparator

/**
 * The module probes of `tools/compatibility/module_probe.py`.
 *
 * `descriptor`, `provider_check`, and `probe` are ported in full: they run `jar`, `javac`, and
 * `java`, all of which are host facilities. `main` stays with the CLI module.
 */
object ModuleProbe {
    const val MODULE_NAME = "org.dyn4j"
    const val FIXTURE = "tools/compatibility/fixtures/named_module"

    val EXPORTS = setOf(
        "org.dyn4j", "org.dyn4j.collision", "org.dyn4j.collision.broadphase",
        "org.dyn4j.collision.continuous", "org.dyn4j.collision.manifold",
        "org.dyn4j.collision.narrowphase", "org.dyn4j.dynamics",
        "org.dyn4j.dynamics.contact", "org.dyn4j.dynamics.joint",
        "org.dyn4j.exception", "org.dyn4j.geometry", "org.dyn4j.geometry.decompose",
        "org.dyn4j.geometry.hull", "org.dyn4j.geometry.simplify",
        "org.dyn4j.world", "org.dyn4j.world.listener", "org.dyn4j.world.result",
    )

    private val HEADER = Regex("^[A-Za-z][A-Za-z0-9_.]*(?:@[^ ]+)?\\s")

    /** Reads the module descriptor with `jar --describe-module`. */
    fun descriptor(jar: String): JsonObject {
        val result = Processes.run(listOf("jar", "--describe-module", "--file", jar))
        if (result.exitCode != 0) {
            throw IllegalArgumentException(
                "module descriptor cannot be read: ${result.stderr.trim()}",
            )
        }
        val lines = pySplitLines(result.stdout)
        val explicit = lines.none { "No module descriptor found" in it }
        val header = lines.firstOrNull { HEADER.containsMatchIn(it) } ?: ""
        val name = if (header.isEmpty()) {
            ""
        } else {
            header.substringBefore("@").substringBefore(" ")
        }
        val exports = sortedByCodePoint(
            lines.filter { it.startsWith("exports ") }.map { it.removePrefix("exports ") },
        )
        return buildJsonObject {
            put(
                "passed",
                JsonPrimitive(
                    explicit && name == MODULE_NAME && exports.toSet() == EXPORTS &&
                        exports.size == EXPORTS.size,
                ),
            )
            put("explicit", JsonPrimitive(explicit))
            put("name", JsonPrimitive(name))
            put("exports", JsonArray(exports.map(::JsonPrimitive)))
            put("descriptor_lines", JsonArray(lines.drop(1).map(::JsonPrimitive)))
        }
    }

    /** Counts the `org.dyn4j` providers on the module path and requires the expected one. */
    fun providerCheck(jar: String, dependencies: List<String>, expectedSha256: String?): JsonObject {
        val providers = mutableListOf<JsonObject>()
        val expectedPath = Path.of(jar).toAbsolutePath().normalize().toString()
        for (candidate in listOf(jar) + dependencies) {
            val resolved = Path.of(candidate).toAbsolutePath().normalize().toString()
            if (!Files.isRegularFile(Path.of(resolved))) {
                return providerFailure(
                    "unreadable module-path entry", expectedPath, expectedSha256, resolved,
                    null, providers,
                )
            }
            val result = Processes.run(
                listOf("jar", "--describe-module", "--file", resolved, "--release", "21"),
            )
            if (result.exitCode != 0) {
                return providerFailure(
                    "unreadable module-path entry", expectedPath, expectedSha256, resolved,
                    result.stderr.trim(), providers,
                )
            }
            val header = pySplitLines(result.stdout).firstOrNull { HEADER.containsMatchIn(it) } ?: ""
            val name = if (header.isEmpty()) "" else header.substringBefore("@").substringBefore(" ")
            if (name == MODULE_NAME) {
                providers.add(
                    buildJsonObject {
                        put("path", JsonPrimitive(resolved))
                        put("sha256", JsonPrimitive(io.github.rubixhacker.harness.host.FileDigest.sha256(resolved)))
                    },
                )
            }
        }
        val reason = when {
            providers.size > 1 -> "duplicate org.dyn4j providers"
            providers.isEmpty() -> "expected org.dyn4j provider missing"
            providers[0].textOrNull("path") != expectedPath -> "wrong org.dyn4j provider path"
            expectedSha256 == null -> "expected provider SHA-256 required"
            providers[0].textOrNull("sha256") != expectedSha256 -> "expected provider SHA-256 mismatch"
            else -> "single org.dyn4j provider"
        }
        return buildJsonObject {
            put("passed", JsonPrimitive(reason == "single org.dyn4j provider"))
            put("reason", JsonPrimitive(reason))
            put("expected_path", JsonPrimitive(expectedPath))
            put("expected_sha256", expectedSha256?.let(::JsonPrimitive) ?: JsonNull)
            put("providers", JsonArray(providers))
        }
    }

    private fun providerFailure(
        reason: String,
        expectedPath: String,
        expectedSha256: String?,
        entry: String,
        error: String?,
        providers: List<JsonObject>,
    ): JsonObject = buildJsonObject {
        put("passed", JsonPrimitive(false))
        put("reason", JsonPrimitive(reason))
        put("expected_path", JsonPrimitive(expectedPath))
        put("expected_sha256", expectedSha256?.let(::JsonPrimitive) ?: JsonNull)
        put("entry", JsonPrimitive(entry))
        if (error != null) put("error", JsonPrimitive(error))
        put("providers", JsonArray(providers))
    }

    /**
     * Probes one staged JAR. `module-descriptor` reads the descriptor; `named-module-consumer`
     * compiles and runs the Java 9 consumer on the module path; `java8-classpath` compiles and runs
     * the same consumer as an unnamed-module classpath application on the pinned Java 8 runtime.
     */
    fun probe(
        jar: String,
        mode: String,
        dependencies: List<String> = emptyList(),
        java8Java: String? = null,
        expectedProviderSha256: String? = null,
        fixtureRoot: String = FIXTURE,
        environment: Map<String, String>? = null,
    ): JsonObject {
        if (mode == "module-descriptor") return descriptor(jar)
        if (mode != "named-module-consumer" && mode != "java8-classpath") {
            throw IllegalArgumentException("unknown module probe: $mode")
        }
        val check = if (mode == "named-module-consumer") {
            providerCheck(jar, dependencies, expectedProviderSha256)
        } else {
            null
        }
        if (check != null && check.textOrNull("passed") != "true") {
            return buildJsonObject {
                put("passed", JsonPrimitive(false))
                put("compile_release", JsonPrimitive(9))
                put("compile_exit_code", JsonNull)
                put("run_exit_code", JsonNull)
                put("output", JsonPrimitive(""))
                put("java_version", JsonPrimitive(""))
                put("provider_check", check)
            }
        }
        val directory = Files.createTempDirectory("dyn4k-module-probe-")
        try {
            val classes = Files.createDirectory(directory.resolve("classes"))
            val main = Path.of(fixtureRoot, "example", "Main.java").toString()
            val path = (listOf(Path.of(jar).toAbsolutePath().normalize().toString()) +
                dependencies.map { Path.of(it).toAbsolutePath().normalize().toString() })
                .joinToString(java.io.File.pathSeparator)
            val compileResult: ProcessOutput
            val runResult: ProcessOutput?
            val version: ProcessOutput
            val compileRelease: Int
            if (mode == "named-module-consumer") {
                compileRelease = 9
                compileResult = Processes.run(
                    listOf(
                        "javac", "--release", "9", "--module-path", path,
                        "-d", classes.toString(),
                        Path.of(fixtureRoot, "module-info.java").toString(), main,
                    ),
                )
                runResult = if (compileResult.exitCode == 0) {
                    Processes.run(
                        listOf(
                            "java", "--module-path",
                            listOf(path, classes.toString()).joinToString(java.io.File.pathSeparator),
                            "-m", "dyn4k.migration.probe/example.Main",
                        ),
                    )
                } else {
                    null
                }
                version = Processes.run(listOf("java", "-version"))
            } else {
                compileRelease = 8
                if (java8Java == null) {
                    throw IllegalArgumentException("Java 8 runtime path is required")
                }
                version = Processes.run(listOf(java8Java, "-version"))
                if (!Regex("\\bversion \"(?:1\\.8\\.|8(?:\\.|\"))")
                        .containsMatchIn(version.stderr + version.stdout)
                ) {
                    throw IllegalArgumentException("classpath runtime is not Java 8")
                }
                compileResult = Processes.run(
                    listOf("javac", "--release", "8", "-cp", path, "-d", classes.toString(), main),
                )
                runResult = if (compileResult.exitCode == 0) {
                    Processes.run(
                        listOf(
                            java8Java, "-cp",
                            listOf(path, classes.toString()).joinToString(java.io.File.pathSeparator),
                            "example.Main",
                        ),
                    )
                } else {
                    null
                }
            }
            val output = runResult?.stdout ?: ""
            val observed = buildJsonObject {
                put(
                    "passed",
                    JsonPrimitive(
                        compileResult.exitCode == 0 && runResult != null &&
                            runResult.exitCode == 0 &&
                            runResult.stdout.trim() == "Named module consumer passed",
                    ),
                )
                put("compile_release", JsonPrimitive(compileRelease))
                put("compile_exit_code", JsonPrimitive(compileResult.exitCode))
                put("run_exit_code", runResult?.let { JsonPrimitive(it.exitCode) } ?: JsonNull)
                put("output", JsonPrimitive(output))
                put(
                    "java_version",
                    JsonPrimitive(
                        if (version.stderr.isEmpty() && version.stdout.isEmpty()) {
                            ""
                        } else {
                            pySplitLines(version.stderr + version.stdout).firstOrNull().orEmpty()
                        },
                    ),
                )
                if (check != null) put("provider_check", check)
            }
            return observed
        } finally {
            Files.walk(directory).use { stream ->
                stream.sorted(Comparator.reverseOrder()).forEach { Files.deleteIfExists(it) }
            }
        }
    }
}

/** The `javap` declaration probe of `execution_probe.signature`. */
object ExecutionProbeHost {
    private val IDENTITY = Regex("^[A-Za-z_$][A-Za-z0-9_.$]*$")
    private val SHA256 = Regex("^[0-9a-f]{64}$")

    /** Runs the two `javap` surfaces and returns the execution record the ledger replays. */
    fun signature(
        item: JsonObject,
        artifact: String,
        oracle: SurfaceOracle = BaselineOracle,
    ): JsonObject {
        val identity = item.textOrNull("id")
            ?: throw IllegalArgumentException("invalid declaration identity for JVM probe")
        val parts = identity.split("|")
        val name = parts[0]
        if (parts.size !in setOf(2, 3) || !IDENTITY.matches(name) ||
            (parts.size == 2 && parts[1] != "type")
        ) {
            throw IllegalArgumentException("invalid declaration identity for JVM probe")
        }
        val candidate = item["candidate"].objectOrNull()
        val artifactSha = candidate?.textOrNull("artifact_sha256")
        if (candidate == null || candidate.textOrNull("identity") != identity ||
            artifactSha == null || !SHA256.matches(artifactSha)
        ) {
            throw IllegalArgumentException("candidate artifact identity is missing or invalid")
        }
        if (artifactSha == oracle.binarySha256) {
            throw IllegalArgumentException("pinned baseline JAR cannot be a candidate artifact")
        }
        if (io.github.rubixhacker.harness.host.FileDigest.sha256(artifact) != artifactSha) {
            throw IllegalArgumentException("candidate artifact SHA-256 differs")
        }
        val plainCommand = listOf("javap", "-classpath", artifact, "-protected", "-s", name)
        val verboseCommand = listOf("javap", "-classpath", artifact, "-protected", "-s", "-v", name)
        val plain = Processes.run(plainCommand, timeoutSeconds = 30)
        val verbose = Processes.run(verboseCommand, timeoutSeconds = 30)
        if (io.github.rubixhacker.harness.host.FileDigest.sha256(artifact) != artifactSha) {
            throw IllegalArgumentException("candidate artifact SHA-256 changed during probe")
        }
        var matched = false
        if (plain.exitCode == 0 && verbose.exitCode == 0) {
            val (header, members) = ExecutionProbe.declarations(plain.stdout, verbose.stdout, oracle)
            val actual: Any? = if (parts.size == 2) {
                header
            } else {
                members[parts[1] to parts[2]]?.let { it.signature to it.flags }
            }
            val wantedFlags = item["flags"].arrayOrNull()?.mapNotNull { it.textOrNull() }
            val wanted: Any? = if (parts.size == 2) {
                item.textOrNull("signature")
            } else {
                item.textOrNull("signature") to wantedFlags
            }
            matched = actual == wanted
        }
        return ExecutionProbe.signatureResult(
            plainCommand = plainCommand,
            verboseCommand = verboseCommand,
            plainStdout = plain.stdout,
            plainStderr = plain.stderr,
            plainExit = plain.exitCode,
            verboseStdout = verbose.stdout,
            verboseStderr = verbose.stderr,
            verboseExit = verbose.exitCode,
            matched = matched,
        )
    }
}

/** The JDK probes of `java_corpus.tool`, `full_ci.version`, and `build_provenance.jdk21_version`. */
object JdkTools {
    fun tool(jdk: String, name: String, major: Int): JsonObject {
        val path = Path.of(jdk, "bin", name).toAbsolutePath().normalize().toString()
        if (!Files.isRegularFile(Path.of(path))) {
            throw IllegalArgumentException("JDK $major $name is missing")
        }
        val run = Processes.run(listOf(path, "-version"))
        val version = (run.stdout + run.stderr).trim()
        val marker = if (major == 8) "1.8." else "21."
        if (marker !in version) {
            throw IllegalArgumentException("JDK $major $name version differs")
        }
        return buildJsonObject {
            put("path", JsonPrimitive(path))
            put("sha256", JsonPrimitive(io.github.rubixhacker.harness.host.FileDigest.sha256(path)))
            put("version", JsonPrimitive(version))
        }
    }

    /** The first `-version` line, requiring the major version marker, as `full_ci.version` does. */
    fun version(jdk: String, executable: String, major: Int): String {
        val binary = Path.of(jdk, "bin", executable).toString()
        if (!Files.isRegularFile(Path.of(binary))) {
            throw IllegalArgumentException("missing $executable: $binary")
        }
        val observed = Processes.run(listOf(binary, "-version"))
        val value = (observed.stdout + observed.stderr).trim()
        val pattern = if (major == 8) {
            Regex("(?:1\\.8\\.|\\b8(?:\\.|\\b))")
        } else {
            Regex("\\b21(?:\\.|\\b)")
        }
        if (observed.exitCode != 0 || !pattern.containsMatchIn(value)) {
            throw IllegalArgumentException("expected Java $major $executable, got $value")
        }
        return pySplitLines(value).firstOrNull().orEmpty()
    }

    /** The pinned JDK 21 banner `build_provenance.jdk21_version` requires. */
    fun jdk21Version(java: String, rejection: String): String {
        val lines = pySplitLines(Processes.run(listOf(java, "-version"), check = true).stderr)
        if (lines.size < 3 ||
            !lines[lines.size - 3].startsWith("openjdk version \"21.") ||
            !lines[lines.size - 2].startsWith("OpenJDK Runtime Environment ") ||
            !lines[lines.size - 1].startsWith("OpenJDK 64-Bit Server VM ")
        ) {
            throw IllegalArgumentException(rejection)
        }
        return lines[lines.size - 3]
    }
}
