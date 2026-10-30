package io.github.rubixhacker.harness.qualification

import io.github.rubixhacker.harness.contract.Qualification
import io.github.rubixhacker.harness.contract.StrictJson
import io.github.rubixhacker.harness.host.CleanCheckout
import java.io.IOException
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.Path
import java.util.concurrent.TimeUnit
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/** One finished command: the exit status and both captured streams. */
data class HostedCapture(val exitCode: Int, val stdout: String, val stderr: String)

/**
 * The host observations `hosted.discover_runtime` reads.
 *
 * The reference calls `platform.system()`, `platform.machine()`, `platform.version()`,
 * `os.environ`, and three external tools. Each of those is a method here so a test can supply
 * recorded observations instead of a real runner.
 */
interface HostEnvironment {
    fun system(): String

    fun machine(): String

    /** `platform.version()`: the kernel build string, or the Windows major.minor.build triple. */
    fun platformVersion(): String

    fun environment(name: String): String?

    fun run(command: List<String>): HostedCapture

    /** `os.name == "nt"`. */
    fun isWindows(): Boolean = system() == "Windows"
}

/**
 * The real host: `platform` module equivalents over the JVM.
 *
 * `platform.machine()` is `uname -m` on POSIX and `PROCESSOR_ARCHITECTURE` on Windows, so the
 * value matches what `platform.machine()` reports. `platform.version()` is `uname -v` on POSIX
 * and the Windows build triple; `System.getProperty("os.version")` is not used because it does
 * not carry the Windows build number.
 */
object DefaultHostEnvironment : HostEnvironment {
    override fun system(): String {
        val name = System.getProperty("os.name") ?: ""
        return when {
            name.startsWith("Windows") -> "Windows"
            name.startsWith("Mac") || name.startsWith("Darwin") -> "Darwin"
            else -> name
        }
    }

    override fun machine(): String {
        if (system() == "Windows") {
            System.getenv("PROCESSOR_ARCHITECTURE")?.let { return it }
            return when (val arch = System.getProperty("os.arch") ?: "") {
                "amd64", "x86_64" -> "AMD64"
                "aarch64", "arm64" -> "ARM64"
                else -> arch
            }
        }
        val uname = try {
            run(listOf("uname", "-m"))
        } catch (error: IOException) {
            return System.getProperty("os.arch") ?: ""
        }
        return if (uname.exitCode == 0 && uname.stdout.trim().isNotEmpty()) {
            uname.stdout.trim()
        } else {
            System.getProperty("os.arch") ?: ""
        }
    }

    override fun platformVersion(): String {
        when (system()) {
            "Darwin" -> return ""
            "Windows" -> {
                val probe = try {
                    run(
                        listOf(
                            "powershell", "-NoProfile", "-Command",
                            "\$v=[System.Environment]::OSVersion.Version; " +
                                "\"\$(\$v.Major).\$(\$v.Minor).\$(\$v.Build)\"",
                        ),
                    )
                } catch (error: IOException) {
                    return ""
                }
                if (probe.exitCode == 0) return probe.stdout.trim()
                return ""
            }
            else -> {
                val uname = try {
                    run(listOf("uname", "-v"))
                } catch (error: IOException) {
                    return System.getProperty("os.version") ?: ""
                }
                return if (uname.exitCode == 0) uname.stdout.trim() else System.getProperty("os.version") ?: ""
            }
        }
    }

    override fun environment(name: String): String? = System.getenv(name)

    override fun run(command: List<String>): HostedCapture {
        val process = ProcessBuilder(command).start()
        val stdout: String
        val stderr: String
        process.outputStream.close()
        stdout = process.inputStream.use { String(it.readBytes(), StandardCharsets.UTF_8) }
        stderr = process.errorStream.use { String(it.readBytes(), StandardCharsets.UTF_8) }
        return HostedCapture(process.waitFor(), stdout, stderr)
    }
}

/**
 * `tools/qualification/hosted.py` process and file-system half: runtime discovery, staged binary
 * hashes, the hosted run, and the probe commands it drives.
 */
object HostedHost {
    /**
     * `hosted.run_capture`: run one command and echo both streams.
     *
     * The reference prints before it returns, so a failing tool is visible in the runner log even
     * when the caller only records the exit status.
     */
    fun runCapture(
        command: List<String>,
        host: HostEnvironment = DefaultHostEnvironment,
        stdout: (String) -> Unit = { System.out.print(it) },
        stderr: (String) -> Unit = { System.err.print(it) },
    ): HostedCapture {
        val capture = host.run(command)
        if (capture.stdout.isNotEmpty()) stdout(capture.stdout)
        if (capture.stderr.isNotEmpty()) stderr(capture.stderr)
        return capture
    }

    /** `hosted.read_command`: the stripped stdout of a successful command, otherwise empty. */
    fun readCommand(command: List<String>, host: HostEnvironment = DefaultHostEnvironment): String {
        val capture = host.run(command)
        return if (capture.exitCode == 0) capture.stdout.trim() else ""
    }

    /** `hosted.tool_version`: the first captured group, or empty when the tool fails. */
    fun toolVersion(
        command: List<String>,
        pattern: Regex,
        host: HostEnvironment = DefaultHostEnvironment,
    ): String {
        val capture = host.run(command)
        if (capture.exitCode != 0) return ""
        val match = pattern.find(capture.stdout + "\n" + capture.stderr) ?: return ""
        return match.groupValues.getOrNull(1) ?: ""
    }

    /**
     * `hosted.discover_runtime`: the runtime observation a probe records.
     *
     * The key order is the reference's insertion order and is retained in the probe JSON.
     */
    fun discoverRuntime(
        target: String,
        host: HostEnvironment = DefaultHostEnvironment,
    ): JsonObject {
        val system = host.system()
        val observed = LinkedHashMap<String, JsonElement>()
        observed["system"] = JsonPrimitive(system)
        observed["machine"] = JsonPrimitive(host.machine())
        observed["os_version"] = JsonPrimitive(
            if (system == "Darwin") readCommand(listOf("sw_vers", "-productVersion"), host)
            else host.platformVersion(),
        )
        observed["runner_image_os"] = JsonPrimitive(host.environment("ImageOS") ?: "")
        observed["runner_image_version"] = JsonPrimitive(host.environment("ImageVersion") ?: "")
        observed["java_version"] = JsonPrimitive(
            toolVersion(listOf("java", "-version"), Regex("version \"([^\"]+)\""), host),
        )
        if (system == "Darwin") {
            val xcode = readCommand(listOf("xcodebuild", "-version"), host)
            val match = Regex("Xcode ([0-9]+(?:\\.[0-9]+)*)\nBuild version [0-9A-Za-z]+")
                .matchEntire(xcode)
            observed["xcode_version"] = JsonPrimitive(match?.groupValues?.get(1) ?: "")
            val lines = xcode.split('\n')
            observed["xcode_build"] = JsonPrimitive(if (xcode.isEmpty()) "" else lines.last().trimEnd('\r'))
            val simulators = LinkedHashMap<String, JsonElement>()
            if (target in Hosted.NATIVE_TARGETS && Hosted.NATIVE_TARGETS.getValue(target).simulator != null) {
                val raw = readCommand(listOf("xcrun", "simctl", "list", "-j", "devices", "available"), host)
                if (raw.isNotEmpty()) {
                    val decoded = StrictJson.load(raw) as? JsonObject ?: JsonObject(emptyMap())
                    val devices = decoded["devices"] as? JsonObject ?: JsonObject(emptyMap())
                    val collected = LinkedHashMap<String, MutableList<JsonElement>>()
                    for ((runtime, entries) in devices) {
                        for (family in listOf("iOS", "tvOS", "watchOS")) {
                            if (".$family-" !in runtime) continue
                            val list = collected.getOrPut(family) { mutableListOf() }
                            for (item in entries as? JsonArray ?: JsonArray(emptyList())) {
                                val device = item as? JsonObject ?: continue
                                val available = if ("isAvailable" in device) {
                                    Py.truthy(device["isAvailable"])
                                } else {
                                    true
                                }
                                if (!available) continue
                                list.add(
                                    JsonObject(
                                        linkedMapOf(
                                            "name" to (device["name"] ?: JsonNull),
                                            "udid" to (device["udid"] ?: JsonNull),
                                            "runtime" to JsonPrimitive(runtime),
                                        ),
                                    ),
                                )
                            }
                        }
                    }
                    for ((family, entries) in collected) {
                        simulators[family] = JsonArray(entries)
                    }
                }
            }
            observed["simulators"] = JsonObject(simulators)
            if (target == "jsSafari") {
                observed["safari_version"] = JsonPrimitive(
                    readCommand(
                        listOf(
                            "defaults", "read", "/Applications/Safari.app/Contents/Info",
                            "CFBundleShortVersionString",
                        ),
                        host,
                    ),
                )
                observed["safaridriver_version"] = JsonPrimitive(
                    readCommand(listOf("safaridriver", "--version"), host),
                )
            }
        }
        return JsonObject(observed)
    }

    /**
     * `hosted.target_hashes`: every staged target binary must match the checksum staged beside it.
     */
    fun targetHashes(staging: Path, target: String): JsonObject {
        val hashes = LinkedHashMap<String, JsonElement>()
        for (module in Qualification.modules) {
            val path = staging.resolve(Qualification.targetBinaryPath(module, target))
            val sidecar = path.resolveSibling(path.fileName.toString() + ".sha256")
            if (!Files.isRegularFile(path) || !Files.isRegularFile(sidecar)) {
                throw IllegalArgumentException("$module target binary or checksum is missing")
            }
            val actual = CorpusFiles.digest(path)
            if (Fs.readText(sidecar).trim().lowercase() != actual) {
                throw IllegalArgumentException("$module target binary checksum differs from staged file")
            }
            hashes[module] = JsonPrimitive(actual)
        }
        return JsonObject(hashes)
    }

    /**
     * The three seams `hosted.run_hosted` drives: the clean-checkout gate, the staging run, the
     * staging audit, and the probe runner. Defaults are the ported implementations.
     */
    class HostedDependencies(
        val repository: Path,
        val host: HostEnvironment = DefaultHostEnvironment,
        val requireCleanCheckout: (Path, String) -> Unit = { root, sha -> CleanCheckout.require(root.toFile(), sha) },
        val stage: (Path, String, List<String>, Path, Path) -> JsonObject = { root, sha, targets, receipt, console ->
            Staging.run(root, sha, targets, receipt, console)
        },
        val audit: (Path, String, List<String>, Path, Path, Path) -> JsonObject = { root, sha, targets, license, receipt, console ->
            StagingAudit.audit(root, sha, targets, license, receipt, console)
        },
        val probe: (List<String>, List<String>, String, Path, JsonObject) -> JsonObject = { command, reports, sha, output, manifest ->
            ProbeRunner.run(command, reports, sha, output, manifest).report
        },
    )

    /**
     * `hosted.run_hosted`: stage the target, audit the staged publication, then run the frozen
     * source and staged-consumer probes and summarise them.
     *
     * The result is written to [output] on every exit path, including a rejected runtime and an
     * exception, because a missing probe file cannot be distinguished from a passing one.
     */
    fun runHosted(
        target: String,
        candidateSha: String,
        output: Path,
        dependencies: HostedDependencies,
    ): JsonObject {
        val repository = resolveRepository(dependencies.repository)
        val staging = repository.resolve("build/staging-repository")
        val result = LinkedHashMap<String, JsonElement>()
        result["candidate_sha"] = JsonPrimitive(candidateSha)
        result["target"] = JsonPrimitive(target)
        result["status"] = JsonPrimitive("NOT_RUN")
        result["runtime"] = JsonObject(emptyMap())
        result["source_probe"] = JsonNull
        result["consumer_probe"] = JsonNull
        result["artifact_hashes"] = JsonObject(emptyMap())
        result["reason"] = JsonPrimitive("probe not started")
        try {
            dependencies.requireCleanCheckout(repository, candidateSha)
            if (target !in Hosted.TARGETS) throw IllegalArgumentException("unknown hosted target")
            val runtime = LinkedHashMap(discoverRuntime(target, dependencies.host))
            result["runtime"] = JsonObject(runtime)
            val verdict = Hosted.runtimeStatus(target, JsonObject(runtime))
            if (verdict.status != "READY") {
                result["status"] = JsonPrimitive(verdict.status)
                result["reason"] = JsonPrimitive(verdict.reason)
                return JsonObject(result)
            }
            val artifactTarget = if (target == "jsSafari") "js" else target
            val wrapper = Hosted.gradleWrapper(
                repository.toString(),
                dependencies.host.isWindows(),
            )
            runtime["gradle_version"] = JsonPrimitive(
                toolVersion(listOf(wrapper, "--version"), Regex("Gradle ([0-9.]+)"), dependencies.host),
            )
            val build = Fs.readText(repository.resolve("build.gradle.kts"))
            val kgp = Regex("""kotlin\("multiplatform"\) version "([^"]+)"""").find(build)
            runtime["kgp_declared_version"] = JsonPrimitive(kgp?.groupValues?.get(1) ?: "")
            result["runtime"] = JsonObject(runtime)
            val stageDir = staging.resolve(".qualification").resolve(target)
            val receiptPath = stageDir.resolve("receipt.json")
            val consolePath = stageDir.resolve("stage.log")
            val receipt = dependencies.stage(
                repository,
                candidateSha,
                listOf(artifactTarget),
                receiptPath,
                consolePath,
            )
            result["stage_command"] = receipt["command"] ?: JsonNull
            result["stage_receipt_sha256"] = JsonPrimitive(CorpusFiles.digest(receiptPath))
            if (Py.str(receipt["status"]) != "PASSED") {
                result["status"] = JsonPrimitive("PROBE_FAILED")
                result["reason"] = receipt["reason"] ?: JsonPrimitive("staging failed")
                return JsonObject(result)
            }
            val audit = dependencies.audit(
                staging,
                candidateSha,
                listOf(artifactTarget),
                repository.resolve("LICENSE.md"),
                receiptPath,
                consolePath,
            )
            val auditPath = stageDir.resolve("audit.json")
            Fs.writeText(auditPath, PyJson.render(audit) + "\n")
            result["stage_audit_sha256"] = JsonPrimitive(CorpusFiles.digest(auditPath))
            if (Py.str(audit["status"]) != "PASSED") {
                val errors = (audit["errors"] as? JsonArray)
                    ?.joinToString("; ") { Hosted.pythonStr(it) }
                    ?: ""
                result["status"] = JsonPrimitive("PROBE_FAILED")
                result["reason"] = JsonPrimitive("staged publication audit failed: $errors")
                return JsonObject(result)
            }
            result["artifact_hashes"] = targetHashes(staging, artifactTarget)
            val manifest = StrictJson.load(
                Fs.readText(repository.resolve("tools/qualification/foundation-probes.json")),
            ) as? JsonObject ?: throw IllegalArgumentException("frozen foundation probe manifest must be an object")
            if (target != "jsSafari") {
                val (sourceManifest, sourceReports) = Hosted.selectedGroups(
                    manifest,
                    listOf("core-$target", target),
                )
                val sourceCommand = listOf(
                    wrapper, "--no-daemon", "--console=plain",
                    ":dyn4k-core:${target}Test", ":dyn4k:${target}Test",
                )
                result["source_probe"] = dependencies.probe(
                    sourceCommand,
                    sourceReports,
                    candidateSha,
                    sibling(output, "-source.json"),
                    sourceManifest,
                )
            }
            val (consumerManifest, consumerReports) = Hosted.selectedGroups(
                manifest,
                listOf("consumer-$target"),
            )
            val consumerCommand = mutableListOf(
                wrapper,
                "-p",
                repository.resolve("consumers/qualification/portable").toString(),
                "--no-daemon",
                "--console=plain",
                if (target == "jsSafari") "jsBrowserTest" else "${target}Test",
                "-PqualificationRepository=$staging",
            )
            if (target == "jsSafari") consumerCommand.add("-PqualificationSafari=true")
            result["consumer_probe"] = dependencies.probe(
                consumerCommand,
                consumerReports,
                candidateSha,
                sibling(output, "-consumer.json"),
                consumerManifest,
            )
            val summary = Hosted.hostedStatus(
                target,
                candidateSha,
                JsonObject(runtime),
                result["source_probe"],
                result["consumer_probe"],
                result["artifact_hashes"],
                manifest,
            )
            result["status"] = JsonPrimitive(summary.status)
            result["reason"] = JsonPrimitive(summary.reason)
        } catch (error: IOException) {
            result["status"] = JsonPrimitive("PROBE_FAILED")
            result["reason"] = JsonPrimitive(error.message ?: "")
        } catch (error: IllegalArgumentException) {
            result["status"] = JsonPrimitive("PROBE_FAILED")
            result["reason"] = JsonPrimitive(error.message ?: "")
        } finally {
            Fs.writeText(output, PyJson.render(JsonObject(result)) + "\n")
        }
        return JsonObject(result)
    }

    /** `Path(__file__).resolve().parents[2]`: the checkout, with symlinks resolved when it exists. */
    fun resolveRepository(repository: Path): Path = try {
        repository.toRealPath()
    } catch (error: IOException) {
        repository.toAbsolutePath().normalize()
    }

    /** `output.with_name(output.stem + suffix)`. */
    fun sibling(output: Path, suffix: String): Path {
        val name = output.fileName?.toString() ?: ""
        val stem = if (name.startsWith(".") && name.indexOf('.', 1) < 0) {
            name
        } else {
            val dot = name.lastIndexOf('.')
            if (dot > 0) name.substring(0, dot) else name
        }
        return output.resolveSibling(stem + suffix)
    }
}
