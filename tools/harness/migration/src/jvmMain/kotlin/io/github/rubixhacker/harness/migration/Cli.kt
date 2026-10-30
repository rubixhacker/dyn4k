package io.github.rubixhacker.harness.migration

import java.io.IOException
import java.nio.file.Files
import java.nio.file.Path

/** `argparse` rejects an unknown or incomplete option with exit code 2. */
class UsageError(message: String) : RuntimeException(message)

private fun parseOptions(
    args: List<String>,
    flags: Set<String>,
    usage: String,
): Map<String, String> {
    val values = linkedMapOf<String, String>()
    var index = 0
    while (index < args.size) {
        val token = args[index]
        if (!token.startsWith("--")) throw UsageError("$usage\nerror: unrecognized arguments: $token")
        val name: String
        val value: String?
        val equals = token.indexOf('=')
        if (equals > 0) {
            name = token.substring(2, equals)
            value = token.substring(equals + 1)
            index += 1
        } else {
            name = token.substring(2)
            if (name !in flags) throw UsageError("$usage\nerror: unrecognized arguments: $token")
            value = args.getOrNull(index + 1)
            if (value == null) throw UsageError("$usage\nerror: argument --$name: expected one argument")
            index += 2
        }
        if (name !in flags) throw UsageError("$usage\nerror: unrecognized arguments: --$name")
        values[name] = value
    }
    return values
}

private fun Map<String, String>.required(name: String, usage: String): String =
    this[name] ?: throw UsageError("$usage\nerror: the following arguments are required: --$name")

private fun Map<String, String>.path(name: String, usage: String): Path = Path.of(required(name, usage))

private fun Map<String, String>.pathOrNull(name: String): Path? = this[name]?.let(Path::of)

private fun Map<String, String>.double(name: String, default: Double): Double =
    this[name]?.toDoubleOrNull() ?: default

private fun Map<String, String>.int(name: String, default: Int): Int =
    this[name]?.toIntOrNull() ?: default

private fun Map<String, String>.choice(name: String, choices: List<String>, default: String): String {
    val value = this[name] ?: return default
    if (value !in choices) throw UsageError("invalid choice: '$value' (choose from ${choices.joinToString(", ") { "'$it'" }})")
    return value
}

private fun Map<String, String>.requiredChoice(name: String, choices: List<String>, usage: String): String {
    val value = required(name, usage)
    if (value !in choices) throw UsageError("invalid choice: '$value' (choose from ${choices.joinToString(", ") { "'$it'" }})")
    return value
}

/** `journeys.py` as a command with the same argv, stdout, and exit codes. */
object JourneysCli {
    private const val USAGE = "usage: journeys.py [-h] {inspect-samples,unavailable,verify-evidence,inspect-artifacts,compile,run-all} ..."

    @JvmStatic
    fun main(args: Array<String>) {
        val code = run(args.toList())
        if (code != 0) kotlin.system.exitProcess(code)
    }

    fun run(args: List<String>): Int {
        if (args.isEmpty()) {
            System.err.println(USAGE)
            return 2
        }
        val command = args[0]
        val usage = "$USAGE\njourneys.py: error"
        val rest = args.drop(1)
        val flags = when (command) {
            "inspect-samples" -> setOf("samples")
            "unavailable" -> setOf("output", "reason")
            "verify-evidence" -> setOf("output")
            "inspect-artifacts" -> setOf("provider", "resolved", "repository")
            "compile" -> setOf(
                "provider", "samples", "resolved", "repository", "output", "javac", "timeout-seconds",
            )
            "run-all" -> setOf(
                "samples", "resolved-root", "repository", "instrumentation", "output", "javac",
                "java", "jdk", "headful-image", "timeout-seconds", "cpuset-cpus",
            )
            else -> {
                System.err.println(USAGE)
                return 2
            }
        }
        return try {
            val options = parseOptions(rest, flags, usage)
            if (options.containsKey("timeout-seconds") && options.double("timeout-seconds", 180.0) <= 0) {
                throw MigrationFailure("timeout-seconds must be positive")
            }
            val root = migrationRepositoryRoot()
            val runner = JourneyRunner(root)
            when (command) {
                "inspect-samples" -> {
                    val report = runner.inspectSamples(options.path("samples", usage))
                    val visible = linkedMapOf<String, PyValue>()
                    for ((key, value) in (report as PyValue.Map).entries) {
                        if (key != "manifest") visible[key] = value
                    }
                    println(PyJson.compactSorted(PyValue.Map(visible)))
                    0
                }
                "inspect-artifacts" -> {
                    val provider = options.requiredChoice("provider", Journeys.PROVIDERS, usage)
                    val report = runner.inspectArtifacts(
                        provider,
                        options.path("resolved", usage),
                        options.pathOrNull("repository"),
                    )
                    println(PyJson.compactSorted(report))
                    0
                }
                "verify-evidence" -> {
                    val report = runner.verifyEvidence(options.path("output", usage))
                    println(
                        PyJson.compactSorted(
                            pyMap(
                                "evidence_file_count" to report.get("evidence_file_count"),
                                "evidence_manifest_sha256" to report.get("evidence_manifest_sha256"),
                            ),
                        ),
                    )
                    0
                }
                "compile" -> {
                    val provider = options.requiredChoice("provider", Journeys.PROVIDERS, usage)
                    val report = runner.compileSamples(
                        provider,
                        options.path("samples", usage),
                        options.path("resolved", usage),
                        options.pathOrNull("repository"),
                        options.path("output", usage),
                        options.pathOrNull("javac") ?: Path.of("javac"),
                        options.double("timeout-seconds", 180.0),
                    )
                    println(PyJson.compactSorted(report))
                    if (pyEquals(report.get("status"), pyText("PASSED"))) 0 else 1
                }
                "run-all" -> {
                    val report = runner.runAll(
                        options.path("samples", usage),
                        options.path("resolved-root", usage),
                        options.path("repository", usage),
                        options.path("instrumentation", usage),
                        options.path("output", usage),
                        options.pathOrNull("javac") ?: Path.of("javac"),
                        options.pathOrNull("java") ?: Path.of("java"),
                        options.path("jdk", usage),
                        options["headful-image"] ?: Journeys.DEFAULT_HEADFUL_IMAGE,
                        options.double("timeout-seconds", 180.0),
                        options["cpuset-cpus"],
                    )
                    println(
                        PyJson.compactSorted(
                            pyMap(
                                "expected_cases" to report.get("expected_cases"),
                                "passed_cases" to report.get("passed_cases"),
                                "failed_cases" to report.get("failed_cases"),
                                "unavailable_cases" to report.get("unavailable_cases"),
                            ),
                        ),
                    )
                    if (pyEquals(report.get("passed_cases"), report.get("expected_cases"))) 0 else 1
                }
                else -> {
                    val report = runner.recordUnavailable(
                        options.path("output", usage),
                        options.required("reason", usage),
                    )
                    println(PyJson.compactSorted(report))
                    0
                }
            }
        } catch (error: UsageError) {
            System.err.println(error.message)
            2
        } catch (error: IOException) {
            System.err.println(error.message ?: error.toString())
            1
        } catch (error: ProcessFailure) {
            System.err.println(error.message ?: error.toString())
            1
        } catch (error: MigrationFailure) {
            System.err.println(error.message ?: error.toString())
            1
        }
    }
}

/** `fixed_replay.py` as a command with the same argv, stdout, and exit codes. */
object FixedReplayCli {
    private const val USAGE = "usage: fixed_replay.py [-h] {compare,run} ..."

    @JvmStatic
    fun main(args: Array<String>) {
        val code = run(args.toList())
        if (code != 0) kotlin.system.exitProcess(code)
    }

    fun run(args: List<String>): Int {
        if (args.isEmpty()) {
            System.err.println(USAGE)
            return 2
        }
        val command = args[0]
        val usage = "$USAGE\nfixed_replay.py: error"
        val flags = when (command) {
            "compare" -> setOf("baseline", "candidate", "output", "baseline-sha256", "candidate-sha256")
            "run" -> setOf(
                "samples", "resolved-root", "repository", "output", "jdk", "javac", "headful-image",
                "power", "angle", "steps", "dt", "ccd", "timeout-seconds",
            )
            else -> {
                System.err.println(USAGE)
                return 2
            }
        }
        return try {
            val options = parseOptions(args.drop(1), flags, usage)
            val root = migrationRepositoryRoot()
            val runner = FixedReplayRunner(root)
            if (command == "compare") {
                val report = runner.compareFiles(
                    options.path("baseline", usage),
                    options.path("candidate", usage),
                    options.required("baseline-sha256", usage),
                    options.required("candidate-sha256", usage),
                )
                runner.writeComparison(options.path("output", usage), report)
                println(
                    PyJson.compact(
                        pyMap(
                            "status" to report.get("status"),
                            "first_divergence" to report.get("first_divergence"),
                        ),
                    ),
                )
                if (pyEquals(report.get("status"), pyText("PASSED"))) 0 else 1
            } else {
                val power = options.double("power", 0.3)
                val angle = options.double("angle", 0.05)
                val steps = options.int("steps", 240)
                val dt = options.double("dt", 1.0 / 60.0)
                if (!power.isFinite() || power <= 0 || !angle.isFinite() || steps <= 0 ||
                    !dt.isFinite() || dt <= 0
                ) {
                    throw MigrationFailure("invalid fixed input")
                }
                val report = runner.runFixed(
                    FixedReplayArguments(
                        samples = options.path("samples", usage),
                        resolvedRoot = options.path("resolved-root", usage),
                        repository = options.path("repository", usage),
                        output = options.path("output", usage),
                        jdk = options.path("jdk", usage),
                        javac = options.pathOrNull("javac") ?: Path.of("javac"),
                        headfulImage = options["headful-image"] ?: Journeys.DEFAULT_HEADFUL_IMAGE,
                        power = power,
                        angle = angle,
                        steps = steps,
                        dt = dt,
                        ccd = options.choice("ccd", listOf("ALL", "BULLETS_ONLY", "NONE"), "ALL"),
                        timeoutSeconds = options.double("timeout-seconds", 180.0),
                    ),
                )
                val comparison = report.getOrNull("comparison")
                println(
                    PyJson.compact(
                        pyMap(
                            "status" to report.get("status"),
                            "failure" to (report.getOrNull("failure") ?: PyValue.Null),
                            "first_divergence" to
                                (comparison?.getOrNull("first_divergence") ?: PyValue.Null),
                            "repeatability" to (report.getOrNull("repeatability") ?: PyValue.Null),
                        ),
                    ),
                )
                if (pyEquals(report.get("status"), pyText("PASSED"))) 0 else 1
            }
        } catch (error: UsageError) {
            System.err.println(error.message)
            2
        } catch (error: IOException) {
            System.err.println(error.message ?: error.toString())
            2
        } catch (error: MigrationFailure) {
            System.err.println(error.message ?: error.toString())
            2
        } catch (error: PyKeyError) {
            System.err.println(error.message ?: error.toString())
            2
        } catch (error: PyTypeError) {
            System.err.println(error.message ?: error.toString())
            2
        }
    }
}

/** `truck_camera.py` as a command with the same argv and exit behaviour. */
object TruckCameraCli {
    @JvmStatic
    fun main(args: Array<String>) {
        if (args.size != 2) {
            System.err.println("usage: truck_camera.py WINDOW EVIDENCE_DIR")
            kotlin.system.exitProcess(1)
        }
        TruckRun(args[0], Path.of(args[1])).run()
    }
}

/** `validate_scene.py` as a command with the same argv, stdout, and exit codes. */
object ValidateSceneCli {
    @JvmStatic
    fun main(args: Array<String>) {
        val code = run(args.toList())
        if (code != 0) kotlin.system.exitProcess(code)
    }

    fun run(args: List<String>): Int {
        if (args.size != 4 || args[0] !in SceneValidation.SCENES) {
            System.err.println("usage: validate_scene.py SCENE OBSERVER_LOG INPUT_LOG RESULT_JSON")
            return 1
        }
        val scene = args[0]
        val logPath = Path.of(args[1])
        val inputPath = Path.of(args[2])
        val resultPath = Path.of(args[3])
        val logText = if (Files.exists(logPath)) MigrationFiles.readTextOrEmpty(logPath) else ""
        val inputText = if (Files.exists(inputPath)) MigrationFiles.readTextOrEmpty(inputPath) else ""
        val (samples, parseErrors) = SceneValidation.parseObserverLog(logText)
        val timeline: (() -> Pair<Boolean, String>)? = if (scene == "Truck") {
            { TruckTimelineFiles.validate(inputPath.parent) }
        } else {
            null
        }
        val result = SceneValidation.result(scene, logText, inputText, samples, parseErrors, timeline)
        MigrationFiles.writeText(resultPath, PyJson.prettySortedLine(result))
        println(
            "VALIDATION scene=$scene expected=${pythonStr(result.get("expected_checks"))} " +
                "executed=${pythonStr(result.get("executed_checks"))} " +
                "failed=${pythonStr(result.get("failed_checks"))} " +
                "unexecuted=${pythonStr(result.get("unexecuted_checks"))} " +
                "samples=${samples.size}",
        )
        return if (pyEquals(result.get("failed_checks"), pyInt(0)) &&
            pyEquals(result.get("unexecuted_checks"), pyInt(0))
        ) {
            0
        } else {
            1
        }
    }
}

/** `validate_plain.py` as a command with the same argv, stdout, and exit codes. */
object ValidatePlainCli {
    @JvmStatic
    fun main(args: Array<String>) {
        val code = run(args.toList())
        if (code != 0) kotlin.system.exitProcess(code)
    }

    fun run(args: List<String>): Int {
        if (args.size == 2 && args[0] == "--summary") {
            val root = Path.of(args[1])
            val summary = PlainValidation.summary { scene ->
                val text = MigrationFiles.readTextOrEmpty(root.resolve(scene).resolve("plain-validation.json"))
                try {
                    pyFromJson(strictJson.parseToJsonElement(text))
                } catch (error: IllegalArgumentException) {
                    null
                }
            }
            MigrationFiles.writeText(root.resolve("check-summary.json"), PyJson.prettyLine(summary))
            val totals = summary.get("totals")
            println(PyJson.compact(totals))
            val failed = pyNumberValue(totals.get("failed"))
            val unexecuted = pyNumberValue(totals.get("unexecuted"))
            return if (failed != 0.0 || unexecuted != 0.0) 1 else 0
        }
        if (args.size != 2 || args[0] !in PlainValidation.SCENES) {
            System.err.println("usage: validate_plain.py SCENE EVIDENCE_DIR")
            return 1
        }
        val scene = args[0]
        val directory = Path.of(args[1])
        val result = PlainValidation.validate(
            scene,
            MigrationFiles.readTextOrEmpty(directory.resolve("application.log")),
            MigrationFiles.readTextOrEmpty(directory.resolve("inputs.log")),
            MigrationFiles.readTextOrEmpty(directory.resolve("launch.txt")),
            terminate(directory.resolve("termination.json")),
            { name -> readPng(directory.resolve(name)) },
            { TruckTimelineFiles.validate(directory) },
        )
        MigrationFiles.writeText(directory.resolve("plain-validation.json"), PyJson.prettyLine(result))
        println(
            "$scene: ${pythonStr(result.get("passed"))}/${pythonStr(result.get("expected"))} " +
                "plain checks; failed=${pythonStr(result.get("failed"))}",
        )
        return if (pyEquals(result.get("failed"), pyInt(0))) 0 else 1
    }

    private val strictJson = kotlinx.serialization.json.Json {
        allowSpecialFloatingPointValues = true
    }

    private fun terminate(path: Path): PyValue {
        val text = MigrationFiles.readTextOrEmpty(path)
        return try {
            pyFromJson(strictJson.parseToJsonElement(text))
        } catch (error: IllegalArgumentException) {
            pyMap()
        }
    }

    /** `validate_plain.read_png`: null unless the bytes decode to a 1024x768 PNG. */
    private fun readPng(path: Path): PyValue? {
        val data = MigrationFiles.readBytes(path, TruckTimeline.MAX_PNG_BYTES + 1) ?: return null
        if (!TruckTimeline.validPng(data, PngDecoders.identify())) return null
        return pyMap(
            "width" to pyInt(bigEndianInt(data, 16)),
            "height" to pyInt(bigEndianInt(data, 20)),
            "sha256" to pyText(MigrationFiles.digest(data)),
        )
    }
}
