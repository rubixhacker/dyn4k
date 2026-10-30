package io.github.rubixhacker.harness.performance

import io.github.rubixhacker.harness.contract.StrictJson
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.put
import java.io.File
import java.nio.file.Files
import java.io.PrintStream
import kotlin.system.exitProcess

/** The `argparse` usage block `ccd_route_trace.py` prints, wrapped at the default 80 columns. */
private const val CCD_ROUTE_TRACE_USAGE: String =
    "usage: ccd_route_trace.py [-h] --output OUTPUT --java JAVA --javac JAVAC\n" +
        "                          --jar JAR"

/**
 * `tools/performance/ccd_route_trace.py`: the CCD fixture identity and the per-step state of the
 * three staged routes, compared channel by channel.
 *
 * The staging checks `capture` performs live in [CandidateStaging]; the trace rules live in
 * [CcdRouteTrace]. This object is the command line that wires them together.
 */
object CcdRouteTraceCli : PortedCommand("ccd_route_trace.py", CCD_ROUTE_TRACE_USAGE) {
    override fun arguments(): CliArguments = CliArguments(
        program = program,
        usage = usage,
        options = listOf(
            CliArguments.Option("--output", required = true),
            CliArguments.Option("--java", required = true),
            CliArguments.Option("--javac", required = true),
            CliArguments.Option("--jar", required = true),
        ),
        requiredOrder = listOf("--output", "--java", "--javac", "--jar"),
    )

    override fun execute(options: Map<String, String>, stdout: PrintStream) {
        val root = PerformanceLayout.repositoryRoot()
        val out = File(options.getValue("--output")).absoluteFile.toPath().normalize().toFile()
        out.mkdirs()
        val baseline = File(options.getValue("--jar")).absoluteFile.toPath().normalize().toFile()
        if (MeasureHost.sha256(baseline.absolutePath) != PerformanceManifest.BASELINE_JAR_SHA256) {
            throw ValueErrorSignal("baseline JAR differs from the pinned artifact")
        }
        capture(
            root = root,
            out = out,
            java = options.getValue("--java"),
            javac = options.getValue("--javac"),
            baseline = baseline,
            stdout = stdout,
        )
    }

    /** `ccd_route_trace.capture`. */
    private fun capture(
        root: File,
        out: File,
        java: String,
        javac: String,
        baseline: File,
        stdout: PrintStream,
    ) {
        val staging = CandidateStaging(root)
        val sourceCommit = staging.git("rev-parse", "HEAD")
        staging.prepare(java, sourceCommit, stdout)
        val identity = StrictJson.load(staging.identityFile.readText()).jsonObject
        staging.verifyIdentity(identity)
        staging.identityFile.copyTo(File(out, "candidate-identity.json"), overwrite = true)

        val manifestFile = PerformanceLayout.manifestFile(root)
        val traceTool = File(root, "tools/performance/ccd_route_trace.py")
        val host = MeasureHost.hostIdentity(java)

        val identityRecords = LinkedHashMap<String, JsonObject>()
        val timingRecords = LinkedHashMap<String, JsonObject>()
        val work = Files.createTempDirectory("dyn4k-ccd-route-trace-").toFile()
        try {
            val jar = MeasureHost.jarPath(work.absolutePath, baseline.absolutePath)
            val classes = MeasureHost.compileHarness(
                javac,
                jar,
                work.absolutePath,
                PerformanceLayout.harnessSources(root).absolutePath,
            )
            // `candidate_runner.run` passes the seven tail arguments to the candidate entry point.
            val fixtureArguments = listOf("ccd", "default", "small", "60", "1", "fixture_identity", "0")
            for (route in CcdRouteTrace.routes) {
                val name = "$route.fixture-identity"
                val raw = File(out, "$name.csv")
                val stderrRaw = File(out, "$name.stderr.raw")
                val command =
                    if (route == "baseline") {
                        listOf(
                            java,
                            *CandidateRunner.flags.toTypedArray(),
                            "-cp",
                            "$classes${File.pathSeparator}$jar",
                            "BaselinePilot",
                        ) + fixtureArguments
                    } else {
                        val (classpath, entrypoint) = staging.candidateRoute(identity, route)
                        listOf(java, *CandidateRunner.flags.toTypedArray(), "-cp", classpath, entrypoint) +
                            fixtureArguments
                    }
                val (_, pid) = MeasureHost.runCapture(
                    command = command,
                    output = raw.absolutePath,
                    stderrPath = stderrRaw.absolutePath,
                )
                identityRecords[route] = CcdRouteTrace.identityEntry(
                    raw = raw.name,
                    sha256 = MeasureHost.sha256(raw.absolutePath),
                    stderrRaw = stderrRaw.name,
                    stderrSha256 = MeasureHost.sha256(stderrRaw.absolutePath),
                    processPid = pid,
                    rowCount = CcdRouteTrace.rows(raw.readText()).size,
                )

                val measured =
                    if (route == "baseline") {
                        MeasureHost.runScenario(
                            java = java,
                            classes = classes,
                            jar = jar,
                            out = out.absolutePath,
                            family = "ccd",
                            variant = "default",
                            size = "small",
                            hz = 60,
                            steps = CcdRouteTrace.MEASURED_STEPS,
                            mode = "timing",
                            warmup = CcdRouteTrace.WARMUP_STEPS,
                            repeat = 1,
                            api = "baseline",
                        )
                    } else {
                        val (classpath, entrypoint) = staging.candidateRoute(identity, route)
                        MeasureHost.runCandidateScenario(
                            java = identity.str("java"),
                            classpath = classpath,
                            entrypoint = entrypoint,
                            out = out.absolutePath,
                            family = "ccd",
                            variant = "default",
                            size = "small",
                            hz = 60,
                            steps = CcdRouteTrace.MEASURED_STEPS,
                            mode = "timing",
                            warmup = CcdRouteTrace.WARMUP_STEPS,
                            repeat = 1,
                            route = route,
                        )
                    }
                val recorded = LinkedHashMap(measured)
                val rawName = measured.str("raw")
                recorded["state_checksum_sha256"] = kotlinx.serialization.json.JsonPrimitive(
                    CandidatePilot.stateChecksum(File(out, rawName).readText()),
                )
                timingRecords[route] = JsonObject(recorded)
            }

            val identities = identityRecords.mapValues { (_, record) ->
                CcdRouteTrace.rows(File(out, record.str("raw")).readText())
            }
            for ((route, values) in identities) {
                CcdRouteTrace.requireCreationHashes(route, values)
            }
            CcdRouteTrace.requireSameInitialIdentities(identities)

            val traces = timingRecords.mapValues { (_, record) ->
                CcdRouteTrace.rows(File(out, record.str("raw")).readText())
            }
            val comparisons = CcdRouteTrace.comparisons(traces)

            val result = CcdRouteTrace.buildResult(
                sourceCommit = sourceCommit,
                candidateIdentitySha256 = MeasureHost.sha256(staging.identityFile.absolutePath),
                baselineJarSha256 = MeasureHost.sha256(baseline.absolutePath),
                manifestSha256 = MeasureHost.sha256(manifestFile.absolutePath),
                traceToolSha256 = MeasureHost.sha256(traceTool.absolutePath),
                host = host,
                identity = JsonObject(identityRecords),
                timing = JsonObject(timingRecords),
                comparisons = comparisons,
            )
            File(out, "result.json").writeText(PythonJson.renderIndented(result, sortKeys = true) + "\n")
            stdout.println(summaryText(out.absolutePath, comparisons))
            try {
                CcdRouteTrace.requireStagedRoutesAgree(comparisons)
            } catch (error: IllegalStateException) {
                throw SystemExitSignal(error.message ?: "staged candidate CCD routes differ")
            }
        } finally {
            work.deleteRecursively()
        }
    }

    /** The one-line summary the command prints, with sorted keys as `capture` requests. */
    fun summaryText(output: String, comparisons: JsonObject): String =
        PythonJson.render(
            buildJsonObject {
                put("output", kotlinx.serialization.json.JsonPrimitive(output))
                put("comparisons", comparisons)
                put("qualification", kotlinx.serialization.json.JsonPrimitive("unpassed"))
            },
            sortKeys = true,
        )

    @JvmStatic
    fun main(args: Array<String>) {
        exitProcess(run(args, System.out, System.err))
    }
}
