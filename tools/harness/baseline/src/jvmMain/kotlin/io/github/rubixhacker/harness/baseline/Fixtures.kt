package io.github.rubixhacker.harness.baseline

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.io.IOException
import java.nio.file.Files
import java.nio.file.Path

/** One Java 8 source fixture the gate compiled against both archives. */
data class FixtureResult(
    val source: String,
    val sourceSha256: String,
    val baselineExitCode: Int,
    val candidateExitCode: Int,
    val candidateStderr: String,
) {
    fun toJson(): JsonObject = buildJsonObject {
        put("source", source)
        put("source_sha256", sourceSha256)
        put("baseline_exit_code", baselineExitCode)
        put("candidate_exit_code", candidateExitCode)
        put("candidate_stderr", candidateStderr)
    }
}

/** The three outputs `verify.fixture_audit` returns. */
data class FixtureAudit(
    val results: List<FixtureResult>,
    val failures: List<String>,
    val errors: List<String>,
)

/**
 * `verify.fixture_audit`: compile each Java 8 source fixture against both archives, and record the
 * bytes the fixture was compiled from.
 *
 * The fixture is copied into a private directory before compiling, so a concurrent writer cannot
 * change the source identity the report pins.
 */
fun fixtureAudit(
    seams: BaselineSeams,
    baseline: Path,
    fixtures: List<Path>,
    requireFixture: Boolean,
    candidateClasspath: String,
    policy: BaselinePolicy = BaselinePolicy(),
): FixtureAudit {
    val results = mutableListOf<FixtureResult>()
    val failures = mutableListOf<String>()
    val errors = mutableListOf<String>()
    if (requireFixture && fixtures.isEmpty()) errors.add("required Java 8 fixture was skipped")
    for (source in fixtures) {
        try {
            if (!isFile(source)) throw IllegalArgumentException("fixture is missing or empty")
            withTemporaryDirectory("dyn4k-fixture-") { directory ->
                val snapshot = directory.resolve(source.fileName.toString())
                copyFile(source, snapshot)
                if (Files.size(snapshot) == 0L) {
                    throw IllegalArgumentException("fixture is missing or empty")
                }
                val sourceHash = digest(snapshot)
                val outputs = mutableListOf<Pair<ProcessOutput, Boolean>>()
                for ((label, artifact) in listOf("baseline" to baseline.toString(), "candidate" to candidateClasspath)) {
                    val output = directory.resolve(label)
                    Files.createDirectories(output)
                    val compiled = seams.run(
                        listOf(
                            "javac", "--release", "8", "-Xlint:-options", "-cp", artifact,
                            "-d", output.toString(), snapshot.toString(),
                        ),
                        null,
                    )
                    outputs.add(compiled to containsClassFile(output))
                }
                if (digest(snapshot) != sourceHash) {
                    throw IllegalArgumentException("fixture snapshot SHA-256 changed during compilation")
                }
                val (baselineCompile, baselineClasses) = outputs[0]
                val (candidateCompile, candidateClasses) = outputs[1]
                if (baselineCompile.exitCode != 0 || !baselineClasses) {
                    throw IllegalArgumentException(
                        "baseline fixture did not compile into classes: " +
                            pyStrip(baselineCompile.stderrText()),
                    )
                }
                results.add(
                    FixtureResult(
                        source = source.toString(),
                        sourceSha256 = sourceHash,
                        baselineExitCode = baselineCompile.exitCode,
                        candidateExitCode = candidateCompile.exitCode,
                        candidateStderr = pyStrip(candidateCompile.stderrText()),
                    ),
                )
                if (candidateCompile.exitCode != 0 || !candidateClasses) failures.add(source.toString())
            }
        } catch (error: IOException) {
            errors.add("$source: ${error.message}")
        } catch (error: IllegalArgumentException) {
            errors.add("$source: ${error.message}")
        }
    }
    if (requireFixture) {
        val present = results.map { it.sourceSha256 }.toSet()
        for ((label, expectedHash) in policy.requiredFixtureSha256) {
            if (expectedHash !in present) {
                errors.add("required Java 8 fixture missing or changed: $label ($expectedHash)")
            }
        }
    }
    return FixtureAudit(results, failures, errors)
}

/** `any(output.rglob("*.class"))`. */
private fun containsClassFile(output: Path): Boolean =
    Files.walk(output).use { paths ->
        paths.anyMatch { it.fileName.toString().endsWith(".class") && Files.isRegularFile(it) }
    }

/** The `fixture_results` JSON list. */
internal fun List<FixtureResult>.toJsonArray() = buildJsonArray { forEach { add(it.toJson()) } }
