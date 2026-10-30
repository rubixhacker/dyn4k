package io.github.rubixhacker.harness.baseline

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonObject
import java.io.PrintStream
import java.nio.file.Path

/**
 * `tools/baseline/verify.py` as one command.
 *
 * The argv grammar, the stdout text and the exit codes are the Python module's:
 * `check-source`, `check-run`, `compare`, and the default full verification. A run-stopping
 * condition prints its message on stderr and exits 1; an argv error exits 2.
 */
object BaselineCli {
    @JvmStatic
    fun main(args: Array<String>) {
        val status = run(args.toList(), RealSeams, BaselinePolicy(), System.out, System.err)
        kotlin.system.exitProcess(status)
    }

    fun run(
        argv: List<String>,
        seams: BaselineSeams = RealSeams,
        policy: BaselinePolicy = BaselinePolicy(),
        out: PrintStream = System.out,
        err: PrintStream = System.err,
    ): Int {
        return when (argv.firstOrNull()) {
            "check-source" -> checkSource(argv.drop(1), seams, policy, out, err)
            "check-run" -> checkRun(argv.drop(1), policy, out, err)
            "compare" -> compare(argv.drop(1), seams, policy, out, err)
            else -> verify(argv, seams, policy, out, err)
        }
    }

    private fun checkSource(
        argv: List<String>,
        seams: BaselineSeams,
        policy: BaselinePolicy,
        out: PrintStream,
        err: PrintStream,
    ): Int {
        val options = Options(argv, setOf("--checkout", "--sources-jar", "--commit"), emptySet())
        if (!options.valid) return usage(err, "check-source")
        val checkout = options.required("--checkout") ?: return usage(err, "check-source")
        val sourcesJar = options.required("--sources-jar") ?: return usage(err, "check-source")
        val commit = options.required("--commit") ?: return usage(err, "check-source")
        return try {
            val provenance = verifySourceInputs(seams, path(checkout), path(sourcesJar), commit, policy)
            out.println(PythonJson.renderIndented(provenance.toJson()))
            0
        } catch (error: IllegalArgumentException) {
            err.println(error.message)
            1
        } catch (error: BaselineExit) {
            err.println(error.message)
            1
        } catch (error: java.io.IOException) {
            err.println(error.message)
            1
        }
    }

    private fun checkRun(
        argv: List<String>,
        policy: BaselinePolicy,
        out: PrintStream,
        err: PrintStream,
    ): Int {
        val options = Options(argv, setOf("--report"), emptySet())
        if (!options.valid) return usage(err, "check-run")
        val report = options.required("--report") ?: return usage(err, "check-run")
        return try {
            val text = readText(path(report))
            val parsed = Json.parseToJsonElement(text).jsonObject
            validateRunReport(parsed, policy.expectedCases)
            out.println("baseline run report valid")
            0
        } catch (error: IllegalArgumentException) {
            err.println(error.message)
            1
        } catch (error: kotlinx.serialization.SerializationException) {
            err.println(error.message)
            1
        } catch (error: java.io.IOException) {
            err.println(error.message)
            1
        }
    }

    private fun compare(
        argv: List<String>,
        seams: BaselineSeams,
        policy: BaselinePolicy,
        out: PrintStream,
        err: PrintStream,
    ): Int {
        val options = Options(
            argv,
            setOf("--baseline-jar", "--candidate"),
            setOf("--only", "--fixture", "--dependency-jar"),
            flags = setOf("--require-fixture"),
        )
        if (!options.valid) return usage(err, "compare")
        val baseline = options.required("--baseline-jar") ?: return usage(err, "compare")
        val candidate = options.required("--candidate") ?: return usage(err, "compare")
        return try {
            val report = compareJars(
                baseline = path(baseline),
                candidate = path(candidate),
                only = options.repeated("--only").takeIf { it.isNotEmpty() }?.toSet(),
                fixtures = options.repeated("--fixture").map { path(it) },
                requireFixture = options.flag("--require-fixture"),
                dependencies = options.repeated("--dependency-jar").map { path(it) },
                policy = policy,
                seams = seams,
            )
            out.println(PythonJson.renderIndented(report.toJson()))
            if (report.hasProblems()) 1 else 0
        } catch (error: IllegalArgumentException) {
            err.println(error.message)
            1
        } catch (error: java.io.IOException) {
            err.println(error.message)
            1
        }
    }

    private fun verify(
        argv: List<String>,
        seams: BaselineSeams,
        policy: BaselinePolicy,
        out: PrintStream,
        err: PrintStream,
    ): Int {
        val options = Options(
            argv,
            emptySet(),
            setOf("--cache", "--inventory", "--summary", "--candidate"),
            flags = setOf("--inventory-only"),
        )
        if (!options.valid) return usage(err, "verify")
        val cache = path(options.value("--cache") ?: ".cache/baseline")
        val inventoryPath = path(options.value("--inventory") ?: "docs/verification/baseline-inventory.json")
        val summaryPath = path(options.value("--summary") ?: "docs/verification/baseline-run.json")
        return try {
            makeDirectories(cache)
            val binary = cache.resolve("dyn4j-6.0.0.jar")
            val sourcesJar = cache.resolve("dyn4j-6.0.0-sources.jar")
            fetch("${Baseline.BASE}/dyn4j-6.0.0.jar", binary, policy.binarySha256)
            fetch("${Baseline.BASE}/dyn4j-6.0.0-sources.jar", sourcesJar, policy.sourcesSha256)
            val source = checkedOutSources(seams, cache, policy)
            val provenance = verifySourceInputs(seams, source, sourcesJar, policy.commit, policy)
            val data = inventory(seams, source, binary, inventoryPath, policy)
            val augmented = buildInventory(data, provenance)
            inventoryPath.parent?.let { makeDirectories(it) }
            writeText(inventoryPath, PythonJson.renderIndented(augmented, sortKeys = true) + "\n")
            val candidate = options.value("--candidate")
            if (candidate != null) {
                val comparison = compareJars(binary, path(candidate), policy = policy, seams = seams)
                out.println(PythonJson.renderIndented(comparison.toJson()))
                if (comparison.hasProblems()) return 1
            }
            if (!options.flag("--inventory-only")) {
                val summary = execute(seams, source, binary, cache, summaryPath, policy)
                out.println(PythonJson.renderIndented(summary))
            }
            out.println("inventory: $inventoryPath")
            0
        } catch (error: BaselineExit) {
            err.println(error.message)
            1
        } catch (error: IllegalArgumentException) {
            err.println(error.message)
            1
        } catch (error: java.io.IOException) {
            err.println(error.message)
            1
        }
    }

    private fun buildInventory(data: JsonObject, provenance: SourceProvenance): JsonObject {
        val baseline = JsonObject(
            data.getValue("baseline").jsonObject +
                ("sources_sha256" to JsonPrimitive(provenance.sourceJarSha256)),
        )
        return JsonObject(
            data + ("baseline" to baseline) + ("source_provenance" to provenance.toJson()),
        )
    }

    private fun usage(err: PrintStream, command: String): Int {
        err.println("usage: verify.py $command [options]")
        return 2
    }

    private fun path(value: String): Path = Path.of(value).toAbsolutePath().normalize()

    /** `argparse`'s option set for one subcommand, restricted to the options the module declares. */
    private class Options(
        argv: List<String>,
        private val valued: Set<String>,
        private val repeated: Set<String>,
        private val flags: Set<String> = emptySet(),
    ) {
        private val values = mutableMapOf<String, MutableList<String>>()
        private val present = mutableSetOf<String>()

        var valid: Boolean = true
            private set

        init {
            var index = 0
            while (index < argv.size && valid) {
                val argument = argv[index]
                when {
                    argument in flags -> {
                        present.add(argument)
                        index++
                    }
                    argument in valued || argument in repeated -> {
                        if (index + 1 >= argv.size) {
                            valid = false
                        } else {
                            values.getOrPut(argument) { mutableListOf() }.add(argv[index + 1])
                            index += 2
                        }
                    }
                    else -> valid = false
                }
            }
        }

        fun value(name: String): String? = values[name]?.last()

        fun required(name: String): String? = value(name)

        fun repeated(name: String): List<String> = values[name] ?: emptyList()

        fun flag(name: String): Boolean = name in present
    }
}
