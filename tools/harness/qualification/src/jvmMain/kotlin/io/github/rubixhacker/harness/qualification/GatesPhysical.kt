package io.github.rubixhacker.harness.qualification

import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.Path
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

/** Thrown when a verifier needs a Python numerical analyzer that has no Kotlin equivalent. */
class AnalyzerNotPorted(analyzer: String) : Exception(
    "Python numerical analyzer is not ported: $analyzer (use the :numerical port instead)",
)

/**
 * `independent_gates.py`, third slice: the numerical analyzer adapters and the two physical
 * verifiers.
 *
 * The reference loads `compare.py`, `physical.py`, `weld_pulley_quality.py`, and
 * `candidate/nominal_zero.py` from `tools/numerical` with `importlib`. `:numerical` now ports
 * `Physical`, `Receipt`, `Cases`, `ExactConsistency`, `Orthogonality`, and
 * `NumericClassWitness`, but the per-case comparison engine (`compare.compare_pair`) and the
 * Weld/Pulley quality engine have no Kotlin equivalent yet: those two steps raise
 * [AnalyzerNotPorted] instead of silently passing.
 */
object GatesPhysical {
    /** `_numerical_modules`: the reference returns the loaded `compare` and `physical` modules. */
    fun numericalModules(directory: Path): Nothing {
        if (!Files.isDirectory(directory)) {
            throw IllegalArgumentException("numerical analyzer directory is absent: $directory")
        }
        throw AnalyzerNotPorted("compare.compare_pair / physical.py")
    }

    /** `_joint_quality_module`: the reference returns the loaded `weld_pulley_quality` module. */
    fun jointQualityModule(directory: Path): Nothing {
        if (!Files.isDirectory(directory)) {
            throw IllegalArgumentException("numerical analyzer directory is absent: $directory")
        }
        throw AnalyzerNotPorted("weld_pulley_quality")
    }

    /** `_nominal_module`: the reference returns the loaded `candidate/nominal_zero` module. */
    fun nominalModule(directory: Path): Nothing {
        if (!Files.isDirectory(directory)) {
            throw IllegalArgumentException("numerical analyzer directory is absent: $directory")
        }
        throw AnalyzerNotPorted("candidate/nominal_zero.compare_pair")
    }

    /**
     * `verify_nominal_physical_case`: the identity and raw-path checks are enforced here; the
     * 36,000-step comparison then needs `compare.compare_pair`, which `:numerical` does not port.
     */
    fun verifyNominalPhysicalCase(
        root: Path,
        receipt: JsonObject,
        candidateSha: String,
        expectedArtifactHashes: Map<String, String>,
        sourceSha: String,
        repository: Path,
    ): JsonObject {
        val row = receipt["nominal_physical_case"]
        if (row == null || row is kotlinx.serialization.json.JsonNull) {
            return buildJsonObject {
                put("candidate_status", JsonPrimitive("NOT_RUN"))
                put("approved_reference_status", JsonPrimitive("PASSED_BASELINE_ONLY"))
                put("reason", JsonPrimitive("36,000-step nominal capture is absent"))
            }
        }
        val value = row as? JsonObject
            ?: throw IllegalArgumentException("nominal physical case identity or raw paths differ")
        if (value.keys != setOf("key", "reference", "candidate", "capture_receipt") ||
            Py.str(value["key"]) != "nominal-free-motion"
        ) {
            throw IllegalArgumentException("nominal physical case identity or raw paths differ")
        }
        IndependentGates.sourceBinding(
            repository, candidateSha,
            APPROVED_NOMINAL,
            "nominal physical validator",
        )
        for (key in listOf("reference", "candidate", "capture_receipt")) {
            IndependentGates.filePath(root, Py.str(value[key]))
        }
        if (sourceSha.isEmpty()) throw IllegalArgumentException("numerical source digest is absent")
        // The reference then loads `candidate/nominal_zero` and calls `compare_pair`; that engine
        // is not ported, so this verifier stops here rather than returning an unverified result.
        nominalModule(repository.resolve("tools/numerical"))
    }

    /** `verify_joint_physical_cases`: identities are checked; the quality engine is not ported. */
    fun verifyJointPhysicalCases(
        root: Path,
        receipt: JsonObject,
        candidateSha: String,
        expectedArtifactHashes: Map<String, String>,
        sourceSha: String,
        repository: Path,
    ): Nothing {
        val directory = repository.resolve("tools/numerical")
        IndependentGates.json(directory.resolve("weld-pulley-physical-declaration.json"))
        IndependentGates.json(directory.resolve("weld-pulley-physical-manifest.json"))
        val rows = receipt["joint_physical_cases"]
            ?: throw IllegalArgumentException("36,000-step candidate Weld and Pulley traces are absent")
        val list = rows as? JsonArray
            ?: throw IllegalArgumentException(
                "candidate Weld/Pulley case identities or counts differ",
            )
        val identities = list.mapNotNull { (it as? JsonObject)?.let { row -> Py.str(row["case"]) } }
        if (list.size != GatesNumerical.JOINT_PHYSICAL_CASES.size ||
            identities.toSet() != GatesNumerical.JOINT_PHYSICAL_CASES.toSet()
        ) {
            throw IllegalArgumentException("candidate Weld/Pulley case identities or counts differ")
        }
        for (key in listOf("reference", "candidate", "capture_receipt")) {
            list.mapNotNull { (it as? JsonObject)?.let { row -> Py.str(row[key]) } }
                .forEach { IndependentGates.filePath(root, it) }
        }
        if (sourceSha.isEmpty()) throw IllegalArgumentException("numerical source digest is absent")
        // The reference then loads `weld_pulley_quality` and compares the traces; that engine is
        // not ported, so this verifier stops here rather than returning an unverified result.
        jointQualityModule(directory)
    }

    /** `APPROVED_NOMINAL`: the reviewed validator blob of the nominal physical case. */
    val APPROVED_NOMINAL = mapOf(
        "tools/numerical/candidate/nominal_zero.py" to
            "8c54194ac8fa0b20e24db1e4eb6d072686fda5c4ecd0ee3c79abd45d686b7bc4",
    )
}
