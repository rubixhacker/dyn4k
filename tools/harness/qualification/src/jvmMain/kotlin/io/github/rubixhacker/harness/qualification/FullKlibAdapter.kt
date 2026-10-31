package io.github.rubixhacker.harness.qualification

import java.io.IOException
import java.nio.file.Files
import java.nio.file.Path
import io.github.rubixhacker.harness.contract.Sha256
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/** `full_klib_consumer` as the adapter needs it. */
interface FullKlibConsumerPort {
    val modules: List<String>
    val localLanes: Set<String>

    /** `contract(repository, lane)`: `(manifest, selected)`. */
    fun contract(repository: Path, laneId: String): Pair<JsonObject?, JsonObject>

    /** `verify(...)`: the public full KLIB replay. */
    fun verify(
        root: Path,
        repository: Path,
        candidateSha: String,
        laneId: String,
        hashes: JsonObject,
        runtime: String,
        archiveDigest: String,
        trusted: JsonObject,
        replayNode: String?,
    ): JsonObject

    /** `independent_gates.archive_digest`. */
    fun archiveDigest(archive: Path): String
}

/** The fail-closed consumer: the public KLIB replay is `full_klib_consumer.py`. */
object FullKlibConsumerUnavailable : FullKlibConsumerPort {
    override val modules: List<String> = FullKlibAdapterRules.MODULES
    override val localLanes: Set<String> = FullKlibAdapterRules.LOCAL_LANES

    private fun unavailable(): Nothing = throw UnsupportedOperationException(
        "public full KLIB consumer is not ported: full_klib_consumer.py (contract, verify) has " +
            "no Kotlin counterpart",
    )

    override fun contract(repository: Path, laneId: String): Pair<JsonObject?, JsonObject> =
        unavailable()

    override fun verify(
        root: Path,
        repository: Path,
        candidateSha: String,
        laneId: String,
        hashes: JsonObject,
        runtime: String,
        archiveDigest: String,
        trusted: JsonObject,
        replayNode: String?,
    ): JsonObject = unavailable()

    override fun archiveDigest(archive: Path): String = ArchiveScan.digest(archive)
}

/** `subprocess.run(command, env=environment, stderr=STDOUT, text=True)`. */
fun interface KlibToolRunner {
    fun output(command: List<String>, environment: Map<String, String>): String
}

/** The production tool runner: merged environment, merged stderr, text output. */
object DefaultKlibToolRunner : KlibToolRunner {
    override fun output(command: List<String>, environment: Map<String, String>): String {
        val builder = ProcessBuilder(command).redirectErrorStream(true)
        builder.environment().putAll(environment)
        val process = try {
            builder.start()
        } catch (error: IOException) {
            throw IllegalArgumentException("auditor tool execution failed: ${command.first()}")
        }
        val combined = process.inputStream.use { it.readBytes() }
        process.waitFor()
        if (process.exitValue() != 0) {
            throw IllegalArgumentException("auditor tool execution failed: ${command.first()}")
        }
        return String(combined, Charsets.UTF_8)
    }
}

/**
 * `full_klib_adapter.verify_staged_consumer`: bind the independently signed KLIB toolchain and
 * artifacts to the public full KLIB replay.
 */
object FullKlibAdapter {
    /** `_hash_file(path, expected, label)`. */
    fun hashFile(path: Path, expected: String?, label: String) {
        if (!FullKlibAdapterRules.isDigest(expected)) {
            throw IllegalArgumentException("signed $label SHA-256 is missing or invalid")
        }
        if (!Files.isRegularFile(path)) {
            throw IllegalArgumentException("signed $label executable is missing")
        }
        if (Sha256.of(Files.readAllBytes(path)) != expected) {
            throw IllegalArgumentException("signed $label executable SHA-256 differs")
        }
    }

    /** `_absolute_path(value, label)`. */
    fun absolutePath(value: String?, label: String): Path {
        if (value.isNullOrEmpty() || !Path.of(value).isAbsolute) {
            throw IllegalArgumentException("signed $label path is missing or relative")
        }
        return Path.of(value)
    }

    /**
     * `_trusted_toolchain`: the signed JDK, Gradle, Node, and Kotlin/Native identities must be the
     * bytes and versions the auditor itself observes.
     */
    fun trustedToolchain(
        expected: JsonObject,
        laneId: String,
        runner: KlibToolRunner = DefaultKlibToolRunner,
        environment: () -> Map<String, String> = { System.getenv() },
    ): Pair<JsonObject, Path> {
        val trusted = expected["expected_klib_toolchain"] as? JsonObject
        val binaries = expected["expected_klib_executables"] as? JsonObject
        if (trusted == null || trusted.keys != FullKlibAdapterRules.TOOLCHAIN_KEYS ||
            binaries == null || binaries.keys != setOf("gradle", "node")
        ) {
            throw IllegalArgumentException("signed KLIB toolchain identity is incomplete")
        }
        for (key in listOf("java_sha256", "gradle_sha256", "node_sha256")) {
            if (!FullKlibAdapterRules.isDigest(Py.str(trusted[key]))) {
                throw IllegalArgumentException("signed KLIB $key is missing or invalid")
            }
        }
        for (key in listOf("java_version", "gradle_version", "node_version", "kgp_version")) {
            if (Py.str(trusted[key]).isNullOrEmpty()) {
                throw IllegalArgumentException("signed KLIB $key is missing")
            }
        }
        val javaHome = absolutePath(Py.str(trusted["java_home"]), "JDK 21 home")
        val gradleHome = Py.str(trusted["gradle_user_home"])!!
        absolutePath(gradleHome, "Gradle user home")
        val gradle = absolutePath(Py.str(binaries["gradle"]), "Gradle executable")
        val node = absolutePath(Py.str(binaries["node"]), "Node executable")
        val native = trusted["kotlin_native"]
        val nativeObject: JsonObject?
        if (laneId.startsWith("linuxX64:")) {
            val value = native as? JsonObject
                ?: throw IllegalArgumentException(
                    "signed Kotlin/Native compiler identity is incomplete",
                )
            if (value.keys != FullKlibAdapterRules.NATIVE_KEYS) {
                throw IllegalArgumentException(
                    "signed Kotlin/Native compiler identity is incomplete",
                )
            }
            absolutePath(Py.str(value["home"]), "Kotlin/Native home")
            for (key in listOf("executable_sha256", "compiler_sha256")) {
                if (!FullKlibAdapterRules.isDigest(Py.str(value[key]))) {
                    throw IllegalArgumentException("signed Kotlin/Native $key is missing or invalid")
                }
            }
            if (Py.str(value["version"]).isNullOrEmpty()) {
                throw IllegalArgumentException("signed Kotlin/Native version is missing")
            }
            nativeObject = value
        } else {
            if (native != null && native !is JsonNull) {
                throw IllegalArgumentException(
                    "signed Node lane has a foreign Native compiler identity",
                )
            }
            nativeObject = null
        }
        val javaVersion = Py.str(trusted["java_version"])!!
        if (!javaVersion.startsWith("openjdk version \"21.") ||
            Py.str(trusted["gradle_version"]) != "Gradle 9.5.0" ||
            Py.str(trusted["kgp_version"]) != "2.4.20"
        ) {
            throw IllegalArgumentException("signed KLIB toolchain differs from approved pins")
        }
        val java = javaHome.resolve("bin/java")
        hashFile(java, Py.str(trusted["java_sha256"]), "JDK 21")
        hashFile(gradle, Py.str(trusted["gradle_sha256"]), "Gradle")
        hashFile(node, Py.str(trusted["node_sha256"]), "Node")
        val variables = LinkedHashMap(environment())
        variables["JAVA_HOME"] = javaHome.toString()
        variables["GRADLE_USER_HOME"] = gradleHome
        val observedJava = runner.output(listOf(java.toString(), "-version"), variables)
            .lines().firstOrNull { it.startsWith("openjdk version ") }
        if (observedJava != javaVersion) {
            throw IllegalArgumentException("signed JDK 21 version differs from auditor tool")
        }
        if (!runner.output(listOf(gradle.toString(), "--version"), variables)
                .contains(Py.str(trusted["gradle_version"])!!)
        ) {
            throw IllegalArgumentException("signed Gradle version differs from auditor tool")
        }
        if (runner.output(listOf(node.toString(), "--version"), variables).trim() !=
            Py.str(trusted["node_version"])
        ) {
            throw IllegalArgumentException("signed Node version differs from auditor tool")
        }
        if (nativeObject != null) {
            val compiler = absolutePath(Py.str(nativeObject["home"]), "Kotlin/Native home")
                .resolve("bin/kotlinc-native")
            hashFile(compiler, Py.str(nativeObject["executable_sha256"]), "Kotlin/Native")
            hashFile(
                compiler.parent.parent.resolve(
                    "konan/lib/kotlin-native-compiler-embeddable.jar",
                ),
                Py.str(nativeObject["compiler_sha256"]),
                "Kotlin/Native compiler JAR",
            )
            val lines = runner.output(listOf(compiler.toString(), "-version"), variables)
                .lines()
            val version = lines.filter {
                it.startsWith("info: kotlinc-native") || it.startsWith("Kotlin/Native:")
            }.joinToString("\n")
            if (version != Py.str(nativeObject["version"]) ||
                "Kotlin/Native: 2.4.20" !in version
            ) {
                throw IllegalArgumentException(
                    "signed Kotlin/Native version differs from auditor tool",
                )
            }
        }
        return trusted to node
    }

    @Suppress("LongParameterList")
    fun verify(
        repository: Path,
        candidateSha: String,
        laneId: String,
        selectedCaseIds: List<String>,
        archive: Path,
        gateResult: JsonElement,
        expected: JsonElement,
        auditedTargetHashes: JsonElement,
        consumer: FullKlibConsumerPort = FullKlibConsumerUnavailable,
        trusted: ((JsonObject, String) -> Pair<JsonObject, Path>)? = null,
    ): JsonObject {
        if (laneId !in consumer.localLanes) {
            throw IllegalArgumentException(
                "public full KLIB verifier does not cover lane: $laneId",
            )
        }
        val audit = expected as? JsonObject
            ?: throw IllegalArgumentException("signed KLIB lane audit is missing")
        val gate = gateResult as? JsonObject
            ?: throw IllegalArgumentException("independent staged-consumer gate has not passed")
        if (Py.str(gate["status"]) != "PASSED") {
            throw IllegalArgumentException("independent staged-consumer gate has not passed")
        }
        val (_, selected) = consumer.contract(repository, laneId)
        val approvedIds = ((selected["cases"] as? JsonArray) ?: JsonArray(emptyList()))
            .mapNotNull { Py.str((it as? JsonObject)?.get("id")) }
        if (selectedCaseIds != approvedIds) {
            throw IllegalArgumentException(
                "signed KLIB lane selects a different approved case suite",
            )
        }
        val hashes = audit["expected_artifact_hashes"] as? JsonObject
        if (hashes == null || hashes.keys != consumer.modules.toSet() ||
            hashes.values.any { !FullKlibAdapterRules.isDigest(Py.str(it)) } ||
            hashes != auditedTargetHashes
        ) {
            throw IllegalArgumentException(
                "signed KLIB artifacts differ from independently audited target",
            )
        }
        val runtime = Py.str(audit["expected_runtime_identity"])
        val digests = audit["expected_archive_digests"] as? JsonObject
        val digest = Py.str(digests?.get("staged-consumer"))
        if (runtime.isNullOrEmpty() || !FullKlibAdapterRules.isDigest(digest)) {
            throw IllegalArgumentException("signed KLIB runtime or archive digest is incomplete")
        }
        if (consumer.archiveDigest(archive) != digest) {
            throw IllegalArgumentException(
                "signed KLIB archive digest differs from transported archive",
            )
        }
        val observed = (trusted ?: { value, lane -> trustedToolchain(value, lane) })(
            audit,
            laneId,
        )
        val public = consumer.verify(
            archive,
            repository,
            candidateSha,
            laneId,
            hashes,
            runtime!!,
            digest!!,
            observed.first,
            if (laneId.startsWith("js:")) observed.second.toString() else null,
        )
        if (public != gateResult) {
            throw IllegalArgumentException(
                "public KLIB verifier differs from independent gate: $laneId",
            )
        }
        return public
    }
}
