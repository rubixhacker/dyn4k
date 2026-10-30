package io.github.rubixhacker.harness.performance

import io.github.rubixhacker.harness.contract.Sha256
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import okio.FileSystem
import okio.Path.Companion.toPath
import java.io.File
import java.net.URI

/**
 * The JVM host adapter for `tools/performance/measure.py`.
 *
 * These are the functions `calibrate.py`, `warmup_probe.py`, and `ccd_route_trace.py` call but
 * cannot own: digesting files, fetching and compiling the pinned dyn4j harness, observing the
 * host, running a child process under a wall-time or RSS ceiling, and turning one run's raw
 * stream into a result record.
 *
 * Paths are parameters rather than module constants, because a Kotlin library has no `__file__`
 * and must not assume where the repository is checked out.
 */
object MeasureHost {
    /** `measure.JAR_URL`. */
    const val JAR_URL: String = "https://repo.maven.apache.org/maven2/org/dyn4j/dyn4j/6.0.0/dyn4j-6.0.0.jar"

    /** The harness sources `compile_harness` compiles, relative to the tool directory. */
    val HARNESS_SOURCES: List<String> = listOf("BaselinePilot.java", "ProbeValidation.java")

    /** The metadata markers a warm-up stream must carry. */
    val REQUIRED_METADATA: Set<String> = setOf(
        "construction_ns", "construction_allocated_bytes", "rss_empty_harness_bytes",
        "rss_after_construction_bytes", "retained_heap_world_alive_bytes",
        "retained_collection_count_delta",
    )

    /** A runner that had to be terminated, or that exited non-zero. */
    class RunnerTerminated(message: String) : IllegalStateException(message)

    /** `measure.sha256`: a streamed file digest. */
    fun sha256(path: String): String =
        FileSystem.SYSTEM.source(path.toPath()).use { Sha256.of(it) }

    /** `measure.read_text`: the stripped contents, or `null` when the file cannot be read. */
    fun readTextOrNull(path: String): String? = try {
        File(path).readText().trim()
    } catch (_: java.io.IOException) {
        null
    }

    /**
     * `measure.jar_path`: the pinned baseline jar, either supplied or downloaded, and always
     * checked against the digest the manifest records.
     */
    fun jarPath(work: String, supplied: String?): String {
        val jar = if (supplied != null) {
            File(supplied).absoluteFile.toPath().normalize().toString()
        } else {
            val target = File(work, "dyn4j-6.0.0.jar")
            URI(JAR_URL).toURL().openStream().use { input ->
                target.outputStream().use { output -> input.copyTo(output) }
            }
            target.absolutePath
        }
        val actual = sha256(jar)
        if (actual != PerformanceManifest.BASELINE_JAR_SHA256) {
            throw IllegalArgumentException("baseline artifact SHA-256 mismatch: $actual")
        }
        return jar
    }

    /**
     * `measure.compile_harness`: compiles the baseline harness against the pinned jar and returns
     * the classes directory.
     */
    fun compileHarness(javac: String, jar: String, work: String, sourcesDir: String): String {
        val classes = File(work, "classes")
        if (!classes.mkdir()) {
            throw java.nio.file.FileAlreadyExistsException(classes.absolutePath)
        }
        val command = mutableListOf(javac, "--release", "21", "-cp", jar, "-d", classes.absolutePath)
        command.addAll(HARNESS_SOURCES.map { File(sourcesDir, it).absolutePath })
        val process = ProcessBuilder(command).redirectErrorStream(true).start()
        val output = process.inputStream.bufferedReader().use { it.readText() }
        val code = process.waitFor()
        if (code != 0) {
            throw IllegalStateException(
                "command ${command} returned non-zero exit status $code: $output",
            )
        }
        return classes.absolutePath
    }

    /**
     * `measure.host_identity`: the host facts a receipt records. `java_version` is the runtime's
     * own `-version` banner, so a receipt names the exact binary that produced the samples.
     */
    fun hostIdentity(java: String): JsonObject {
        val version = ProcessBuilder(java, "-version").redirectErrorStream(false).start().let { process ->
            val error = process.errorStream.bufferedReader().use { it.readText() }
            process.waitFor()
            error
        }
        val cpuinfo = readTextOrNull("/proc/cpuinfo")
        val meminfo = readTextOrNull("/proc/meminfo")
        return buildJsonObject {
            put("hostname", hostname())
            put("machine", machine())
            put("system", system())
            put("release", release())
            put("os_version", readTextOrNull("/etc/os-release"))
            put("product_name", readTextOrNull("/sys/class/dmi/id/product_name"))
            put("product_version", readTextOrNull("/sys/class/dmi/id/product_version"))
            put("cpu_model", HostIdentityParsing.cpuModel(cpuinfo))
            put("ram_kib", HostIdentityParsing.memTotalKib(meminfo))
            put("java_version", version.trim())
            put("power_mode", kotlinx.serialization.json.JsonNull)
            put("charging_state", kotlinx.serialization.json.JsonNull)
            put("temperature_c", kotlinx.serialization.json.JsonNull)
            put("throttling", kotlinx.serialization.json.JsonNull)
        }
    }

    /**
     * `measure.run_capture`: runs one child, writing its stdout to [output]. Without a ceiling the
     * child is simply waited for; with one, the loop polls the elapsed wall time and the child's
     * resident set until the child ends or a ceiling stops it.
     *
     * Returns the child's stderr text and its process id.
     */
    fun runCapture(
        command: List<String>,
        output: String,
        stderrPath: String? = null,
        timeoutSeconds: Double? = null,
        rssCeilingBytes: Long? = null,
    ): Pair<String, Long> {
        if (timeoutSeconds == null && rssCeilingBytes == null) {
            val errorFile = stderrPath?.let { File(it) } ?: File.createTempFile("dyn4k-capture-", ".stderr")
            val process = ProcessBuilder(command)
                .redirectOutput(File(output))
                .redirectError(errorFile)
                .start()
            process.waitFor()
            val errorOutput = errorFile.readText()
            if (stderrPath == null) errorFile.delete()
            if (process.exitValue() != 0) {
                throw RunnerTerminated("runner failed (${process.exitValue()}): $errorOutput")
            }
            return errorOutput to process.pid()
        }

        val stderrFile = stderrPath?.let { File(it) } ?: File(withSuffix(output, ".stderr"))
        var reason = "bounded_end"
        val process = ProcessBuilder(command)
            .redirectOutput(File(output))
            .redirectError(stderrFile)
            .start()
        val began = System.nanoTime()
        while (process.isAlive) {
            if (timeoutSeconds != null && elapsedSeconds(began) > timeoutSeconds) {
                reason = "wall_time_ceiling"
                process.destroy()
                break
            }
            if (rssCeilingBytes != null) {
                val statm = readTextOrNull("/proc/${process.pid()}/statm")
                if (statm == null) {
                    reason = "rss_probe_unavailable"
                    process.destroy()
                    break
                }
                val rss = statm.split(Regex("\\s+"))[1].toLong() * pageSize()
                if (rss > rssCeilingBytes) {
                    reason = "rss_ceiling"
                    process.destroy()
                    break
                }
            }
            Thread.sleep(50)
        }
        var code: Int
        if (process.waitFor(5, java.util.concurrent.TimeUnit.SECONDS)) {
            code = process.exitValue()
        } else {
            process.destroyForcibly()
            code = process.waitFor()
        }
        File(withSuffix(output, ".termination.json"))
            .writeText("""{"exit_code": $code, "reason": "$reason"}""" + "\n")
        if (reason != "bounded_end" || code != 0) {
            throw RunnerTerminated("runner terminated: $reason, exit $code; raw files retained")
        }
        return stderrFile.readText() to process.pid()
    }

    /**
     * `measure.run_scenario`: one measured run. Spawns the harness or the candidate runner,
     * separates the warm-up metadata from the warm-up stream, validates the measured steps, and
     * returns the result record the callers file.
     */
    fun runScenario(
        java: String,
        classes: String,
        jar: String,
        out: String,
        family: String,
        variant: String,
        size: String,
        hz: Int,
        steps: Int,
        mode: String,
        warmup: Int,
        repeat: Int,
        api: String = "baseline",
        runner: String? = null,
        stress: Boolean = false,
    ): JsonObject {
        val name = "$family.$variant.$size.${hz}hz.$api.$mode.r$repeat"
        val raw = File(out, "$name.csv")
        val warmupRaw = File(out, "$name.warmup.csv")
        val stderrRaw = File(out, "$name.stderr.raw")

        val tail = listOf(family, variant, size, hz.toString(), steps.toString(), mode, warmup.toString())
        val command =
            if (api == "baseline") {
                listOf(java, *CandidateRunner.flags.toTypedArray(), "-cp", "$classes${File.pathSeparator}$jar", "BaselinePilot") + tail
            } else {
                listOf(runner ?: throw IllegalArgumentException("candidate API needs a runner")) + tail + listOf(api)
            }

        val (_, processPid) = runCapture(
            command = command,
            output = raw.absolutePath,
            stderrPath = warmupRaw.absolutePath,
            timeoutSeconds = if (stress) 180.0 else null,
            rssCeilingBytes = if (stress) 3L * 1024 * 1024 * 1024 else null,
        )

        stderrRaw.writeBytes(warmupRaw.readBytes())

        val metadata = linkedMapOf<String, Long>()
        val csvLines = mutableListOf<String>()
        for (line in CandidatePilot.splitLines(warmupRaw.readText())) {
            if (line.startsWith("#")) {
                val separator = line.indexOf('=', 1)
                if (separator < 0) throw IllegalArgumentException("malformed warm-up marker: $line")
                metadata[line.substring(1, separator)] = line.substring(separator + 1).toLongOrNull()
                    ?: throw IllegalArgumentException("malformed warm-up marker: $line")
            } else {
                csvLines.add(line)
            }
        }
        if (!metadata.keys.containsAll(REQUIRED_METADATA)) {
            throw IllegalArgumentException("missing construction or retained-memory sample")
        }
        val marker = when (api) {
            "direct_kotlin" -> 1L
            "compatibility" -> 2L
            else -> null
        }
        if (marker != null && (metadata["process_pid"] != processPid || metadata["route_marker"] != marker)) {
            throw IllegalArgumentException("candidate process or route identity differs from the launcher")
        }
        warmupRaw.writeText(csvLines.joinToString("\n") + "\n")
        val warmupRows = Csv.parse(warmupRaw.readText()).rows
        if (warmupRows.size != warmup) throw IllegalArgumentException("missing raw warm-up steps")
        if (mode == "memory" &&
            (metadata.getValue("retained_heap_world_alive_bytes") < 0 ||
                metadata.getValue("retained_collection_count_delta") <= 0)
        ) {
            throw IllegalArgumentException("retained-memory collection probe unavailable")
        }

        val rows = Measure.validateCsv(
            Csv.parse(raw.readText()),
            family,
            variant,
            size,
            hz,
            steps,
            mode,
        )
        val summary = LinkedHashMap(Measure.summary(rows, hz, mode))
        val bodyCount = PerformanceManifest.sizes.getValue(family).getValue(size)
        summary["activity_status"] = kotlinx.serialization.json.JsonPrimitive(
            Analyze.activityStatus(rows, family, variant, bodyCount, hz),
        )

        val emptyRss = metadata.getValue("rss_empty_harness_bytes")
        val constructionRss = metadata.getValue("rss_after_construction_bytes")
        val warmupRss = warmupRows.map { it.channel("rss_bytes") }.filter { it >= 0 }
        if (mode == "memory" && (emptyRss < 0 || warmupRss.isEmpty())) {
            throw IllegalArgumentException("incremental-memory probe unavailable")
        }
        if (emptyRss >= 0) {
            val observed = (summary.getValue("peak_rss_delta_bytes") as kotlinx.serialization.json.JsonPrimitive)
                .content.toLong()
            val candidates = mutableListOf(observed, constructionRss - emptyRss)
            candidates.addAll(warmupRss.map { it - emptyRss })
            summary["peak_rss_delta_bytes"] = kotlinx.serialization.json.JsonPrimitive(candidates.max())
        }

        summary["family"] = kotlinx.serialization.json.JsonPrimitive(family)
        summary["variant"] = kotlinx.serialization.json.JsonPrimitive(variant)
        summary["size"] = kotlinx.serialization.json.JsonPrimitive(size)
        summary["hz"] = kotlinx.serialization.json.JsonPrimitive(hz)
        summary["mode"] = kotlinx.serialization.json.JsonPrimitive(mode)
        summary["api"] = kotlinx.serialization.json.JsonPrimitive(api)
        summary["warmup_steps"] = kotlinx.serialization.json.JsonPrimitive(warmup)
        summary["warmup_raw"] = kotlinx.serialization.json.JsonPrimitive(warmupRaw.name)
        summary["warmup_sha256"] = kotlinx.serialization.json.JsonPrimitive(sha256(warmupRaw.absolutePath))
        summary["stderr_raw"] = kotlinx.serialization.json.JsonPrimitive(stderrRaw.name)
        summary["stderr_sha256"] = kotlinx.serialization.json.JsonPrimitive(sha256(stderrRaw.absolutePath))
        summary["cold_construction_ns"] =
            kotlinx.serialization.json.JsonPrimitive(metadata.getValue("construction_ns"))
        summary["cold_construction_allocated_bytes"] =
            kotlinx.serialization.json.JsonPrimitive(metadata.getValue("construction_allocated_bytes"))
        summary["rss_empty_harness_bytes"] = kotlinx.serialization.json.JsonPrimitive(emptyRss)
        summary["rss_after_construction_bytes"] = kotlinx.serialization.json.JsonPrimitive(constructionRss)
        summary["retained_heap_world_alive_bytes"] =
            kotlinx.serialization.json.JsonPrimitive(metadata.getValue("retained_heap_world_alive_bytes"))
        summary["retained_collection_count_delta"] =
            kotlinx.serialization.json.JsonPrimitive(metadata.getValue("retained_collection_count_delta"))
        summary["cold_first_step_ns"] = if (warmupRows.isEmpty()) {
            kotlinx.serialization.json.JsonNull
        } else {
            kotlinx.serialization.json.JsonPrimitive(warmupRows.first().channel("elapsed_ns"))
        }
        summary["cold_process_initialization_ns"] = kotlinx.serialization.json.JsonNull
        summary["raw"] = kotlinx.serialization.json.JsonPrimitive(raw.name)
        summary["raw_sha256"] = kotlinx.serialization.json.JsonPrimitive(sha256(raw.absolutePath))
        summary["process_pid"] = kotlinx.serialization.json.JsonPrimitive(processPid)
        summary["status"] = kotlinx.serialization.json.JsonPrimitive(
            when {
                stress -> "capacity_report"
                steps < 600 * hz -> "pilot_only"
                else -> "raw_unqualified"
            },
        )
        return JsonObject(summary)
    }

    /** `Path.with_suffix(".termination.json")`, which replaces only the final suffix. */
    fun withSuffix(path: String, suffix: String): String {
        val file = File(path)
        val name = file.name
        val dot = name.lastIndexOf('.')
        val replaced = if (dot <= 0) name + suffix else name.substring(0, dot) + suffix
        return File(file.parentFile, replaced).path
    }

    private fun elapsedSeconds(began: Long): Double = (System.nanoTime() - began) / 1e9

    /** The page size `os.sysconf("SC_PAGE_SIZE")` reports, for the `/proc/<pid>/statm` ceiling. */
    private fun pageSize(): Long = pageSizeCache ?: try {
        val process = ProcessBuilder("getconf", "PAGESIZE").start()
        val text = process.inputStream.bufferedReader().use { it.readText() }
        process.waitFor()
        (text.trim().toLongOrNull() ?: 4096L).also { pageSizeCache = it }
    } catch (_: java.io.IOException) {
        4096L.also { pageSizeCache = it }
    }

    private var pageSizeCache: Long? = null

    private fun hostname(): String = try {
        java.net.InetAddress.getLocalHost().hostName
    } catch (_: java.net.UnknownHostException) {
        System.getenv("HOSTNAME") ?: ""
    }

    private fun machine(): String = when (val arch = System.getProperty("os.arch")) {
        "amd64" -> "x86_64"
        "arm64", "aarch64" -> "aarch64"
        else -> arch
    }

    private fun system(): String = when {
        System.getProperty("os.name").startsWith("Linux") -> "Linux"
        System.getProperty("os.name").startsWith("Mac") -> "Darwin"
        System.getProperty("os.name").startsWith("Windows") -> "Windows"
        else -> System.getProperty("os.name")
    }

    private fun release(): String =
        readTextOrNull("/proc/sys/kernel/osrelease") ?: System.getProperty("os.version")
}
