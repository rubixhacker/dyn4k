package io.github.rubixhacker.harness.qualification

import io.github.rubixhacker.harness.contract.Qualification
import io.github.rubixhacker.harness.contract.StrictJson
import java.nio.file.Files
import java.nio.file.Path
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

/**
 * `qualify.main`: the qualification command line.
 *
 * Ported actions: `matrix`, `check-providers`, `probe`, `audit-staging`, `execute`.
 * `record` fails closed because `LaneEvaluation.evaluate` returns a status verdict, not the
 * reference's full lane object (`runtime_identity`, `suite_id`, `case_results`, …), so a report it
 * wrote would not be the reference's bytes.
 */
object QualificationCli {
    @JvmStatic
    fun main(arguments: Array<String>) {
        System.exit(run(arguments))
    }

    fun run(arguments: Array<String>, repository: Path? = null): Int {
        var action: String? = null
        var candidateSha: String? = null
        var output: Path? = null
        var manifest: Path? = null
        var graph: Path? = null
        val reports = mutableListOf<String>()
        val groups = mutableListOf<String>()
        var stageReceipt: Path? = null
        var stageConsole: Path? = null
        var repositoryOption: Path? = null
        val targets = mutableListOf<String>()
        val command = mutableListOf<String>()
        var plan: Path? = null
        var index = 0
        while (index < arguments.size) {
            when (val argument = arguments[index]) {
                "--candidate-sha" -> candidateSha = arguments[++index]
                "--output" -> output = Path.of(arguments[++index])
                "--manifest" -> manifest = Path.of(arguments[++index])
                "--report" -> reports.add(arguments[++index])
                "--group" -> groups.add(arguments[++index])
                "--stage-receipt" -> stageReceipt = Path.of(arguments[++index])
                "--stage-console" -> stageConsole = Path.of(arguments[++index])
                "--repository" -> repositoryOption = Path.of(arguments[++index])
                "--target" -> targets.add(arguments[++index])
                "--plan" -> plan = Path.of(arguments[++index])
                "--" -> {
                    for (rest in (index + 1) until arguments.size) command.add(arguments[rest])
                    index = arguments.size
                }
                else -> if (argument.startsWith("--")) {
                    return usage("unexpected argument: $argument")
                } else if (action == null) {
                    action = argument
                } else {
                    command.add(argument)
                }
            }
            index++
        }
        if (action == null) return usage("the action must be one of matrix, check-providers, record, execute, audit-staging, probe")
        if (action !in setOf("matrix", "check-providers", "record", "execute", "audit-staging", "probe")) {
            return usage("argument action: invalid choice: '$action'")
        }
        if (action == "matrix") {
            println(PyJson.render(Qualification.expand().let { cases -> lanesJson(cases) }))
            return 0
        }
        if (action == "check-providers") {
            // `check-providers` takes one positional graph path, as the reference parser does.
            val graphPath = graph ?: command.firstOrNull()?.let { Path.of(it) }
            val text = if (graphPath != null) Fs.readText(graphPath) else ""
            return try {
                Qualification.checkProviders(text)
                println("one org.dyn4j provider")
                0
            } catch (error: IllegalArgumentException) {
                System.err.println(error.message)
                1
            }
        }
        val root = repositoryOption ?: repository ?: repositoryRoot()
        val sha = candidateSha
        if (sha == null) return usage("--candidate-sha is required")
        try {
            io.github.rubixhacker.harness.host.CleanCheckout.require(root.toFile(), sha)
        } catch (error: Exception) {
            return usage(error.message ?: error.toString())
        }
        if (action == "probe") {
            if (!Py.SHA40.matches(sha)) return usage("candidate SHA must be a full commit hash")
            if (output == null || manifest == null) {
                return usage("--manifest and --output are required")
            }
            if (command.isEmpty()) return usage("probe needs a command")
            val frozenPath = root.resolve("tools/qualification/foundation-probes.json")
            if (manifest.toAbsolutePath().normalize() != frozenPath.toAbsolutePath().normalize()) {
                return usage("probe manifest must be the tracked frozen foundation manifest")
            }
            val frozen = StrictJson.load(Fs.readText(frozenPath)) as JsonObject
            val declared = (frozen["groups"] as JsonArray).mapNotNull { it as? JsonObject }
            val selected = declared.filter { Py.str(it["id"]) in groups }
            if (selected.size != groups.size || groups.toSet().size != groups.size) {
                return usage("unknown or duplicate frozen probe group")
            }
            val scoped = JsonObject(frozen + ("groups" to JsonArray(selected)))
            val report = ProbeRunner.run(command, reports, sha, output, scoped)
            print(report.stdout)
            System.err.print(report.stderr)
            println(PyJson.renderDefault(report.report))
            return if (Py.str(report.report["status"]) == "PROBE_PASSED") 0 else 1
        }
        if (action == "audit-staging") {
            if (output == null || stageReceipt == null || stageConsole == null || targets.isEmpty()) {
                return usage("--target, --stage-receipt, --stage-console and --output are required")
            }
            val result = StagingAudit.audit(
                repositoryOption ?: root,
                sha,
                targets,
                root.resolve("LICENSE.md"),
                stageReceipt,
                stageConsole,
            )
            Fs.writeText(output, PyJson.render(result) + "\n")
            println(PyJson.renderDefault(result))
            return if (Py.str(result["status"]) == "PASSED") 0 else 1
        }
        if (action == "execute") {
            if (plan == null || output == null) return usage("--plan and --output are required")
            val planValue = StrictJson.load(Fs.readText(plan)) as JsonObject
            val valid = Qualification.expand().map { it.id }.toSet()
            val unknown = planValue.keys - valid
            if (unknown.isNotEmpty()) {
                return usage("unknown lane: " + unknown.sortedWith(CanonicalText::compare).joinToString(", "))
            }
            val evidence = Execution.executePlan(planValue, sha, output)
            return if (ProbeManifest.executionSucceeded(evidence)) 0 else 1
        }
        return usage(
            "record is not ported: LaneEvaluation.evaluate returns a status verdict, " +
                "not the reference's full lane object, so a report would not be the reference bytes",
        )
    }

    private fun lanesJson(cases: List<io.github.rubixhacker.harness.contract.MatrixCase>): JsonElement =
        JsonArray(
            cases.map { case ->
                buildJsonObject {
                    put("target", JsonPrimitive(case.target))
                    put("runtime", JsonPrimitive(case.runtime))
                    put("minimum", JsonPrimitive(case.minimum))
                    put("kind", JsonPrimitive(case.kind))
                    put("version", JsonPrimitive(case.version))
                    put("configuration", JsonPrimitive(case.configuration))
                    put("id", JsonPrimitive(case.id))
                }
            },
        )

    private fun repositoryRoot(): Path {
        var current: Path? = Path.of("").toAbsolutePath()
        while (current != null) {
            if (Files.isDirectory(current.resolve("tools/qualification"))) return current
            current = current.parent
        }
        throw IllegalArgumentException("qualification repository root was not found")
    }

    private fun usage(message: String): Int {
        System.err.println("usage error: $message")
        return 2
    }
}
