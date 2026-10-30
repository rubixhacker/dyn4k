package io.github.rubixhacker.harness.migration

import java.io.IOException
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.Path

/** The command-line inputs of `fixed_replay.py run`. */
data class FixedReplayArguments(
    val samples: Path,
    val resolvedRoot: Path,
    val repository: Path,
    val output: Path,
    val jdk: Path,
    val javac: Path = defaultJavac(),
    val headfulImage: String = Journeys.DEFAULT_HEADFUL_IMAGE,
    val power: Double = 0.3,
    val angle: Double = 0.05,
    val steps: Int = 240,
    val dt: Double = 1.0 / 60.0,
    val ccd: String = "ALL",
    val timeoutSeconds: Double = 180.0,
)

/**
 * `tools/migration/fixed_replay.py` over a repository root.
 *
 * The comparison contract is pure and lives in [ReplayComparison]; this runner supplies the file
 * reads, the process runs, and the receipt writes.
 */
class FixedReplayRunner(
    private val root: Path,
    private val policy: JourneyPolicy = JourneyPolicy.DEFAULT,
) {
    private val journeys = JourneyRunner(root, policy)

    /** Reads a JSON-lines stream, skipping blank lines as `read_stream` does. */
    fun readStreamFile(path: Path): List<PyValue> {
        val text = try {
            Files.readString(path, StandardCharsets.UTF_8)
        } catch (error: IOException) {
            throw MigrationFailure(error.message ?: error.toString())
        }
        return pythonSplitlines(text).filter { it.trim().isNotEmpty() }.map {
            try {
                pyFromJson(strictJson.parseToJsonElement(it))
            } catch (error: IllegalArgumentException) {
                throw MigrationFailure(pythonJsonError(error))
            }
        }
    }

    /** `fixed_replay.py compare`, from the two recorded stream files. */
    fun compareFiles(
        baseline: Path,
        candidate: Path,
        baselineSha: String,
        candidateSha: String,
    ): PyValue = ReplayComparison.compare(
        readStreamFile(baseline),
        readStreamFile(candidate),
        baselineSha,
        candidateSha,
    )

    /** Writes `comparison.json` the way the Python tool writes it. */
    fun writeComparison(output: Path, report: PyValue) {
        MigrationFiles.writeText(output, PyJson.prettyLine(report))
    }

    /** `fixed_replay.run_fixed`. */
    fun runFixed(arguments: FixedReplayArguments): PyValue.Map {
        val commit = journeys.requireCleanCandidate()
        val source = journeys.inspectSamples(arguments.samples)
        if (Files.exists(arguments.output) && !MigrationFiles.isDirectoryEmpty(arguments.output)) {
            throw MigrationFailure("fixed replay output directory is not empty")
        }
        Files.createDirectories(arguments.output)
        val providers = linkedMapOf<String, PyValue>()
        val repeatability = linkedMapOf<String, PyValue>()
        val report = linkedMapOf<String, PyValue>(
            "candidate_commit" to pyText(commit),
            "source_revision" to source.get("revision"),
            "source_manifest_sha256" to source.get("manifest_sha256"),
            "jdk" to pyText(MigrationFiles.posix(arguments.jdk.toAbsolutePath().normalize())),
            "image" to pyText(arguments.headfulImage),
            "controls" to pyMap(
                "power" to pyReal(arguments.power),
                "angle" to pyReal(arguments.angle),
                "dt" to pyReal(arguments.dt),
                "prelude_steps" to pyInt(120),
                "steps" to pyInt(arguments.steps),
                "ccd" to pyText(arguments.ccd),
                "observation_stride" to pyInt(1),
                "jvm_identity_hash_mode" to pyInt(ReplayContract.HASH_MODE),
            ),
            "providers" to PyValue.Map(providers),
            "repeatability" to PyValue.Map(repeatability),
            "status" to pyText("FAILED"),
        )
        try {
            val image = Processes.run(
                listOf("podman", "image", "inspect", "--format", "{{.Id}}", arguments.headfulImage),
                30.0,
            )
            MigrationFiles.writeText(
                arguments.output.resolve("image-inspect.log"),
                image.stdout + image.stderr,
            )
            if (image.exitCode != 0 || image.stdout.trim().isEmpty()) {
                throw MigrationFailure("headful image unavailable")
            }
            report["image_id"] = pyText(image.stdout.trim())
            val script = root.resolve("tools/migration/run-fixed-scene.sh")
            val fixture = root.resolve(
                "consumers/migration/src/main/java/org/dyn4j/samples/framework/BilliardsReplay.java",
            )
            report["fixture_sha256"] = pyText(MigrationFiles.digest(fixture))
            report["script_sha256"] = pyText(MigrationFiles.digest(script))
            for (provider in Journeys.PROVIDERS) {
                val directory = arguments.output.resolve(provider)
                Files.createDirectory(directory)
                val resolved = arguments.resolvedRoot.resolve(provider)
                val compilation = journeys.compileSamples(
                    provider, arguments.samples, resolved, arguments.repository,
                    directory.resolve("compile"), arguments.javac,
                )
                if (!pyEquals(compilation.get("status"), pyText("PASSED"))) {
                    throw MigrationFailure(
                        "$provider unchanged sample compilation failed: " +
                            pythonStr(compilation.get("reason")),
                    )
                }
                val artifacts = journeys.inspectArtifacts(provider, resolved, arguments.repository)
                val primary = if (provider == "baseline") "dyn4j-6.0.0.jar" else policy.candidateJar
                val artifactSha = (artifacts.get("jars") as PyValue.Seq).items
                    .first { pyEquals(it.get("name"), pyText(primary)) }
                    .let { (it.get("sha256") as PyValue.Text).value }
                val classes = directory.resolve("compile/classes")
                val classpath = (
                    listOf(classes.toString()) +
                        MigrationFiles.jars(resolved).map { it.toString() }
                    ).joinToString(MigrationFiles.pathSeparator())
                val javac = listOf(
                    arguments.javac.toString(), "--release", "8", "-cp", classpath,
                    "-d", classes.toString(), fixture.toString(),
                )
                MigrationFiles.writeText(
                    directory.resolve("fixture-command.json"),
                    PyJson.prettyLine(pyList(javac.map(::pyText))),
                )
                if (journeys.subprocessLog(javac, directory.resolve("fixture-javac.log")) != 0) {
                    throw MigrationFailure("$provider replay fixture compilation failed")
                }
                val dependencyCp = (artifacts.get("jars") as PyValue.Seq).items.joinToString(":") {
                    "/work/lib/" + (it.get("name") as PyValue.Text).value
                }
                val command = listOf(
                    "podman", "run", "--rm", "--network=none", "--userns=keep-id",
                    "--security-opt", "label=disable",
                    "-v", "${classes.toAbsolutePath()}:/work/classes:ro",
                    "-v", "${resolved.toAbsolutePath()}:/work/lib:ro",
                    "-v", "${script.toAbsolutePath()}:/work/run-fixed-scene.sh:ro",
                    "-v", "${arguments.jdk.toAbsolutePath()}:/jdk:ro",
                    "-e", "DEPENDENCY_CP=$dependencyCp",
                    arguments.headfulImage, "bash", "/work/run-fixed-scene.sh", provider,
                    artifactSha, (source.get("manifest_sha256") as PyValue.Text).value,
                    pythonStr(pyReal(arguments.power)), pythonStr(pyReal(arguments.angle)),
                    arguments.steps.toString(), pythonStr(pyReal(arguments.dt)), arguments.ccd,
                )
                MigrationFiles.writeText(
                    directory.resolve("invocation.json"),
                    PyJson.prettyLine(pyMap("command" to pyList(command.map(::pyText)))),
                )
                val result = Processes.run(command, arguments.timeoutSeconds)
                val stream = directory.resolve("stream.jsonl")
                MigrationFiles.writeText(stream, result.stdout)
                MigrationFiles.writeText(directory.resolve("stderr.log"), result.stderr)
                val providerReport = linkedMapOf<String, PyValue>(
                    "exit_code" to pyInt(result.exitCode),
                    "artifact_sha256" to pyText(artifactSha),
                    "artifacts" to artifacts,
                    "stream_sha256" to pyText(MigrationFiles.digest(stream)),
                )
                providers[provider] = PyValue.Map(providerReport)
                if (result.exitCode != 0) {
                    throw MigrationFailure("$provider fixed replay process failed")
                }
                providerReport["process_identity"] = pyText(
                    ReplayComparison.processIdentity(result.stderr),
                )
                MigrationFiles.writeText(
                    directory.resolve("repeat-invocation.json"),
                    PyJson.prettyLine(pyMap("command" to pyList(command.map(::pyText)))),
                )
                val repeat = Processes.run(command, arguments.timeoutSeconds)
                val repeatStream = directory.resolve("repeat-stream.jsonl")
                MigrationFiles.writeText(repeatStream, repeat.stdout)
                MigrationFiles.writeText(directory.resolve("repeat-stderr.log"), repeat.stderr)
                if (repeat.exitCode != 0) {
                    throw MigrationFailure("$provider repeated fixed replay process failed")
                }
                providerReport["repeat_process_identity"] = pyText(
                    ReplayComparison.processIdentity(repeat.stderr),
                )
                if (pyEquals(
                        providerReport.getValue("process_identity"),
                        providerReport.getValue("repeat_process_identity"),
                    )
                ) {
                    throw MigrationFailure("$provider repeated replay reused process identity")
                }
                val (firstRows, firstError) = ReplayComparison.readStream(
                    readStreamFile(stream), provider, artifactSha,
                )
                val (repeatRows, repeatError) = ReplayComparison.readStream(
                    readStreamFile(repeatStream), provider, artifactSha,
                )
                if (firstError != null || repeatError != null) {
                    throw MigrationFailure(
                        "$provider replay identity invalid: ${firstError ?: repeatError}",
                    )
                }
                providerReport["runtime"] = pyMap(
                    *listOf(
                        "world_code_source", "java_home", "java_version",
                        "jvm_identity_hash_mode", "jvm_identity_hash_probe",
                        "jvm_input_arguments",
                    ).map { it to firstRows[0].get(it) }.toTypedArray(),
                )
                val difference = ReplayComparison.repeatabilityDifference(firstRows, repeatRows)
                repeatability[provider] = pyMap(
                    "status" to pyText(if (difference != null) "FAILED" else "PASSED"),
                    "first_divergence" to (difference ?: PyValue.Null),
                    "repeat_stream_sha256" to pyText(MigrationFiles.digest(repeatStream)),
                )
            }
            val comparison = compareFiles(
                arguments.output.resolve("baseline/stream.jsonl"),
                arguments.output.resolve("candidate/stream.jsonl"),
                (providers.getValue("baseline").get("artifact_sha256") as PyValue.Text).value,
                (providers.getValue("candidate").get("artifact_sha256") as PyValue.Text).value,
            )
            writeComparison(arguments.output.resolve("comparison.json"), comparison)
            report["comparison"] = comparison
            val repeatsPassed = repeatability.values.all { pyEquals(it.get("status"), pyText("PASSED")) }
            report["status"] = pyText(
                if (pyEquals(comparison.get("status"), pyText("PASSED")) && repeatsPassed) {
                    "PASSED"
                } else {
                    "FAILED"
                },
            )
        } catch (error: IOException) {
            report["failure"] = pyText(error.message ?: error.toString())
        } catch (error: ProcessTimeout) {
            report["failure"] = pyText(error.message ?: error.toString())
        } catch (error: MigrationFailure) {
            report["failure"] = pyText(error.message ?: error.toString())
        } catch (error: PyTypeError) {
            report["failure"] = pyText(error.message ?: error.toString())
        } catch (error: PyKeyError) {
            report["failure"] = pyText(error.message ?: error.toString())
        }
        try {
            journeys.requireCleanCandidate(commit)
            val finalSource = journeys.inspectSamples(arguments.samples)
            if (!pyEquals(finalSource.get("manifest"), source.get("manifest"))) {
                throw MigrationFailure("sample source changed during fixed replay")
            }
        } catch (error: IOException) {
            report["status"] = pyText("FAILED")
            report["failure"] = pyText(error.message ?: error.toString())
        } catch (error: ProcessFailure) {
            report["status"] = pyText("FAILED")
            report["failure"] = pyText(error.message ?: error.toString())
        } catch (error: MigrationFailure) {
            report["status"] = pyText("FAILED")
            report["failure"] = pyText(error.message ?: error.toString())
        }
        journeys.writeSummary(arguments.output, PyValue.Map(report))
        return PyValue.Map(report)
    }

    private val strictJson = kotlinx.serialization.json.Json {
        allowSpecialFloatingPointValues = true
    }
}
