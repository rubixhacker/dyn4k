package io.github.rubixhacker.harness.performance

import java.io.File
import java.io.PrintStream
import java.nio.file.Files
import kotlin.system.exitProcess

/** An `argparse` failure: the message text and the usage block printed above it. */
class CliUsageError(
    val program: String,
    val usage: String,
    val detail: String,
) : Exception(detail)

/**
 * The subset of `argparse` these three commands use: long options only, `--name value` and
 * `--name=value`, fixed choices, integer values, and required options.
 *
 * Error precedence follows `argparse`: a value conversion or choice failure is raised while the
 * token is read, before the required-option check; `unrecognized arguments` is raised last.
 */
class CliArguments(
    private val program: String,
    private val usage: String,
    private val options: List<Option>,
    private val requiredOrder: List<String>,
) {
    class Option(
        val name: String,
        val required: Boolean = false,
        val choices: List<String>? = null,
        val integer: Boolean = false,
        val default: String? = null,
    )

    private val byName = options.associateBy { it.name }

    fun parse(args: Array<String>): Map<String, String> {
        val values = LinkedHashMap<String, String>()
        for (option in options) if (option.default != null) values[option.name] = option.default
        val unrecognized = mutableListOf<String>()
        var index = 0
        while (index < args.size) {
            val token = args[index]
            if (!token.startsWith("--")) {
                unrecognized.add(token)
                index += 1
                continue
            }
            val separator = token.indexOf('=')
            val name = if (separator >= 0) token.substring(0, separator) else token
            val option = byName[name]
            if (option == null) {
                unrecognized.add(token)
                index += 1
                continue
            }
            val value: String
            if (separator >= 0) {
                value = token.substring(separator + 1)
                index += 1
            } else {
                val next = args.getOrNull(index + 1)
                if (next == null || next.startsWith("--")) {
                    throw CliUsageError(program, usage, "argument $name: expected one argument")
                }
                value = next
                index += 2
            }
            if (option.integer) {
                if (value.toLongOrNull() == null) {
                    throw CliUsageError(program, usage, "argument $name: invalid int value: '$value'")
                }
            }
            if (option.choices != null && value !in option.choices) {
                val rendered = option.choices.joinToString(", ") { "'$it'" }
                throw CliUsageError(
                    program,
                    usage,
                    "argument $name: invalid choice: '$value' (choose from $rendered)",
                )
            }
            values[name] = value
        }
        val missing = requiredOrder.filter { it !in values }
        if (missing.isNotEmpty()) {
            throw CliUsageError(
                program,
                usage,
                "the following arguments are required: ${missing.joinToString(", ")}",
            )
        }
        if (unrecognized.isNotEmpty()) {
            throw CliUsageError(program, usage, "unrecognized arguments: ${unrecognized.joinToString(" ")}")
        }
        return values
    }
}

/**
 * Shared exit-code plumbing for the ported commands.
 *
 * `argparse` exits 2 with a usage block and one `error:` line. An uncaught `ValueError` exits 1
 * with the exception class and message; an uncaught `RuntimeError` likewise. `SystemExit("text")`
 * prints just the text and exits 1.
 */
abstract class PortedCommand(
    val program: String,
    val usage: String,
) {
    /** `raise SystemExit("...")`, which Python prints bare and exits 1 with. */
    class SystemExitSignal(message: String) : Exception(message)

    /** A `ValueError` the reference raises and does not catch. */
    class ValueErrorSignal(message: String) : IllegalArgumentException(message)

    protected abstract fun arguments(): CliArguments

    /** Runs the command body. Returning normally means exit 0. */
    protected abstract fun execute(options: Map<String, String>, stdout: PrintStream)

    /** Parses and runs, mapping every failure to the exit code the reference produces. */
    fun run(args: Array<String>, stdout: PrintStream, stderr: PrintStream): Int = try {
        val options = arguments().parse(args)
        execute(options, stdout)
        0
    } catch (error: CliUsageError) {
        stderr.println(error.usage)
        stderr.println("${error.program}: error: ${error.detail}")
        2
    } catch (error: SystemExitSignal) {
        stderr.println(error.message)
        1
    } catch (error: MeasureHost.RunnerTerminated) {
        stderr.println("RuntimeError: ${error.message}")
        1
    } catch (error: IllegalArgumentException) {
        stderr.println("ValueError: ${error.message}")
        1
    } catch (error: IllegalStateException) {
        stderr.println("RuntimeError: ${error.message}")
        1
    }

    /** The integers `argparse` validated, in the shape the bodies want. */
    protected fun Map<String, String>.integer(name: String): Int = getValue(name).toInt()

    /**
     * A check `argparse` performs after parsing, which the reference reports through
     * `parser.error` — a usage block and exit 2, not a raised `ValueError` and exit 1.
     */
    protected inline fun usageError(check: () -> Unit) {
        try {
            check()
        } catch (error: IllegalArgumentException) {
            throw CliUsageError(program, usage, error.message ?: "")
        }
    }
}

/** The `argparse` usage block `warmup_probe.py` prints, wrapped at the default 80 columns. */
private const val WARMUP_PROBE_USAGE: String =
    "usage: warmup_probe.py [-h] --output OUTPUT [--jar JAR] [--java JAVA]\n" +
        "                       [--javac JAVAC]\n" +
        "                       --family {separated,pile,joint,ccd,lifecycle}\n" +
        "                       --variant VARIANT --size {small,medium}\n" +
        "                       --hz {30,60,120} [--warmup-seconds WARMUP_SECONDS]"

/** `tools/performance/warmup_probe.py`. */
object WarmupProbeCli : PortedCommand("warmup_probe.py", WARMUP_PROBE_USAGE) {

    private val families: List<String> get() = PerformanceManifest.sizes.keys.toList()

    override fun arguments(): CliArguments = CliArguments(
        program = program,
        usage = usage,
        options = listOf(
            CliArguments.Option("--output", required = true),
            CliArguments.Option("--jar"),
            CliArguments.Option("--java", required = false, default = "java"),
            CliArguments.Option("--javac", required = false, default = "javac"),
            CliArguments.Option("--family", required = true, choices = families),
            CliArguments.Option("--variant", required = true),
            CliArguments.Option("--size", required = true, choices = listOf("small", "medium")),
            CliArguments.Option("--hz", required = true, integer = true, choices = listOf("30", "60", "120")),
            CliArguments.Option("--warmup-seconds", required = false, integer = true, default = "600"),
        ),
        requiredOrder = listOf("--output", "--family", "--variant", "--size", "--hz"),
    )

    override fun execute(options: Map<String, String>, stdout: PrintStream) {
        val warmupSeconds = options.integer("--warmup-seconds")
        usageError { WarmupProbe.requireWarmupSeconds(warmupSeconds) }
        val family = options.getValue("--family")
        val variant = options.getValue("--variant")
        val size = options.getValue("--size")
        val hz = options.integer("--hz")
        val policy = PerformanceManifest.manifest()
        usageError { WarmupProbe.requireVariant(policy, family, variant) }
        PerformanceManifest.validate(policy)

        val root = PerformanceLayout.repositoryRoot()
        val manifestFile = PerformanceLayout.manifestFile(root)
        WarmupProbe.requireCheckedInManifest(manifestFile.readBytes())

        val out = File(options.getValue("--output")).absoluteFile.toPath().normalize().toFile()
        out.mkdirs()
        val work = Files.createTempDirectory("dyn4k-warmup-probe-").toFile()
        try {
            val jar = MeasureHost.jarPath(work.absolutePath, options["--jar"])
            val classes = MeasureHost.compileHarness(
                options.getValue("--javac"),
                jar,
                work.absolutePath,
                PerformanceLayout.harnessSources(root).absolutePath,
            )
            val result = MeasureHost.runScenario(
                java = options.getValue("--java"),
                classes = classes,
                jar = jar,
                out = out.absolutePath,
                family = family,
                variant = variant,
                size = size,
                hz = hz,
                steps = 30 * hz,
                mode = "timing",
                warmup = warmupSeconds * hz,
                repeat = 1,
            )
            val warm = Csv.parse(File(out, result.str("warmup_raw")).readText()).rows
            val measured = Csv.parse(File(out, result.str("raw")).readText()).rows
            val report = WarmupProbe.buildReport(
                baselineJarSha256 = MeasureHost.sha256(jar),
                manifestSha256 = MeasureHost.sha256(manifestFile.absolutePath),
                harnessSha256 = MeasureHost.sha256(PerformanceLayout.harnessSource(root).absolutePath),
                host = MeasureHost.hostIdentity(options.getValue("--java")),
                result = result,
                warmup = warm,
                measured = measured,
                family = family,
                variant = variant,
                bodyCount = PerformanceManifest.sizes.getValue(family).getValue(size),
                hz = hz,
            )
            File(out, "warmup-probe.json")
                .writeText(PythonJson.renderIndented(report, sortKeys = true) + "\n")
            stdout.println(
                summaryText(report.str("warmup_status"), report.str("activity_status")),
            )
        } finally {
            work.deleteRecursively()
        }
    }

    /** The one-line summary the command prints, with Python's default JSON separators. */
    fun summaryText(warmupStatus: String, activityStatus: String): String =
        PythonJson.render(
            kotlinx.serialization.json.buildJsonObject {
                put("warmup_status", kotlinx.serialization.json.JsonPrimitive(warmupStatus))
                put("activity_status", kotlinx.serialization.json.JsonPrimitive(activityStatus))
            },
        )

    @JvmStatic
    fun main(args: Array<String>) {
        exitProcess(run(args, System.out, System.err))
    }
}

/** The `argparse` usage block `calibrate.py` prints, wrapped at the default 80 columns. */
private const val CALIBRATE_USAGE: String =
    "usage: calibrate.py [-h] --output OUTPUT [--jar JAR] [--java JAVA]\n" +
        "                    [--javac JAVAC]\n" +
        "                    --family {separated,pile,joint,ccd,lifecycle}\n" +
        "                    --variant VARIANT --size {small,medium} --hz {30,60,120}\n" +
        "                    [--warmup-seconds WARMUP_SECONDS]\n" +
        "                    [--measurement-seconds MEASUREMENT_SECONDS]"

/** `tools/performance/calibrate.py`. */
object CalibrateCli : PortedCommand("calibrate.py", CALIBRATE_USAGE) {

    private val families: List<String> get() = PerformanceManifest.sizes.keys.toList()

    override fun arguments(): CliArguments = CliArguments(
        program = program,
        usage = usage,
        options = listOf(
            CliArguments.Option("--output", required = true),
            CliArguments.Option("--jar"),
            CliArguments.Option("--java", required = false, default = "java"),
            CliArguments.Option("--javac", required = false, default = "javac"),
            CliArguments.Option("--family", required = true, choices = families),
            CliArguments.Option("--variant", required = true),
            CliArguments.Option("--size", required = true, choices = listOf("small", "medium")),
            CliArguments.Option("--hz", required = true, integer = true, choices = listOf("30", "60", "120")),
            CliArguments.Option("--warmup-seconds", required = false, integer = true, default = "120"),
            CliArguments.Option("--measurement-seconds", required = false, integer = true, default = "30"),
        ),
        requiredOrder = listOf("--output", "--family", "--variant", "--size", "--hz"),
    )

    override fun execute(options: Map<String, String>, stdout: PrintStream) {
        val warmupSeconds = options.integer("--warmup-seconds")
        val measurementSeconds = options.integer("--measurement-seconds")
        usageError { Calibrate.requireDurations(warmupSeconds, measurementSeconds) }
        val family = options.getValue("--family")
        val variant = options.getValue("--variant")
        val size = options.getValue("--size")
        val hz = options.integer("--hz")
        val policy = PerformanceManifest.manifest()
        usageError { Calibrate.requireVariant(policy, family, variant) }
        PerformanceManifest.validate(policy)

        val root = PerformanceLayout.repositoryRoot()
        val manifestFile = PerformanceLayout.manifestFile(root)
        val out = File(options.getValue("--output")).absoluteFile.toPath().normalize().toFile()
        out.mkdirs()
        val work = Files.createTempDirectory("dyn4k-performance-calibration-").toFile()
        try {
            val jar = MeasureHost.jarPath(work.absolutePath, options["--jar"])
            val classes = MeasureHost.compileHarness(
                options.getValue("--javac"),
                jar,
                work.absolutePath,
                PerformanceLayout.harnessSources(root).absolutePath,
            )
            val trials = (1..6).map { repeat ->
                MeasureHost.runScenario(
                    java = options.getValue("--java"),
                    classes = classes,
                    jar = jar,
                    out = out.absolutePath,
                    family = family,
                    variant = variant,
                    size = size,
                    hz = hz,
                    steps = measurementSeconds * hz,
                    mode = "timing",
                    warmup = warmupSeconds * hz,
                    repeat = repeat,
                )
            }
            fun rows(name: String) = Csv.parse(File(out, name).readText()).rows
            val pairs = (0 until 6 step 2).map { index ->
                Calibrate.pair(
                    a = trials[index].str("raw"),
                    b = trials[index + 1].str("raw"),
                    left = rows(trials[index].str("raw")),
                    right = rows(trials[index + 1].str("raw")),
                    hz = hz,
                )
            }
            val report = Calibrate.buildReport(
                sourceCommit = policy.str("source_commit"),
                baselineJarSha256 = MeasureHost.sha256(jar),
                manifestSha256 = MeasureHost.sha256(manifestFile.absolutePath),
                harnessSha256 = MeasureHost.sha256(PerformanceLayout.harnessSource(root).absolutePath),
                host = MeasureHost.hostIdentity(options.getValue("--java")),
                family = family,
                variant = variant,
                size = size,
                hz = hz,
                warmupStatus = trials.map { Analyze.warmupStatus(rows(it.str("warmup_raw")), hz) },
                activityStatus = trials.map {
                    Analyze.activityStatus(
                        rows(it.str("raw")),
                        family,
                        variant,
                        PerformanceManifest.sizes.getValue(family).getValue(size),
                        hz,
                    )
                },
                trials = trials,
                pairs = pairs,
            )
            File(out, "calibration.json")
                .writeText(PythonJson.renderIndented(report, sortKeys = true) + "\n")
            stdout.println(summaryText(out.absolutePath, report))
        } finally {
            work.deleteRecursively()
        }
    }

    /** The one-line summary the command prints, with Python's default JSON separators. */
    fun summaryText(output: String, report: kotlinx.serialization.json.JsonObject): String =
        PythonJson.render(
            kotlinx.serialization.json.buildJsonObject {
                put("output", kotlinx.serialization.json.JsonPrimitive(output))
                put("warmup_status", report.getValue("warmup_status"))
                put("activity_status", report.getValue("activity_status"))
                put("noise_bound", report.getValue("noise_bound"))
            },
        )

    @JvmStatic
    fun main(args: Array<String>) {
        exitProcess(run(args, System.out, System.err))
    }
}
