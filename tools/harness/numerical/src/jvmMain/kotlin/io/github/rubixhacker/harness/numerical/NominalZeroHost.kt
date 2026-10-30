package io.github.rubixhacker.harness.numerical

import kotlinx.serialization.json.JsonObject
import java.nio.file.Path

/**
 * `candidate/nominal_zero.compare_pair`: the shared comparison under the nominal zero and
 * timestep rules, plus the two nominal-specific audit blocks.
 *
 * The audit of both traces runs first, so a candidate that breaks a nominal invariant fails
 * before the receipt is even consulted, exactly as the reference orders it.
 */
object NominalZeroHost {
    fun comparePair(
        fixture: JsonObject,
        reference: Path,
        candidate: Path,
        receipt: Path,
        source: String,
        artifact: String,
        commit: String,
    ): JsonObject {
        val counts = fixture["counts"] as JsonObject
        val expectedStates = counts["state"]?.intOrNull() ?: 0
        val expectedCallbacks = counts["event"]?.intOrNull() ?: 0
        val checks = NominalZero.auditPair(
            TraceFiles.recordsOf(reference),
            TraceFiles.recordsOf(candidate),
            expectedStates,
            expectedCallbacks,
        )
        val outcome = CompareHost.compare(
            NominalZero.withRules(fixture),
            reference,
            candidate,
            receipt,
            source,
            artifact,
            commit,
        )
        return NominalZero.annotate(outcome, checks.first, checks.second)
    }
}
