package io.github.rubixhacker.harness.qualification

import java.nio.file.Files
import java.nio.file.Path
import io.github.rubixhacker.harness.contract.Sha256
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/**
 * `full_android_consumer` as the adapter needs it.
 *
 * The consumer itself is not ported yet, so every method names it in the failure rather than
 * pretending the replay happened. `modules` is the real table.
 */
interface FullAndroidConsumerPort {
    val modules: List<String>

    /** `approved_cases(checkout)`: the manifest and its 2,523 portable cases. */
    fun approvedCases(repository: Path): Pair<JsonObject, List<JsonObject>>

    /** `original_source_hashes(checkout)`. */
    fun originalSourceHashes(repository: Path): JsonObject

    /** `source_and_toolchain(checkout, prepared)`. */
    fun sourceAndToolchain(repository: Path, prepared: JsonObject): JsonElement

    /** `verify_archive(...)`: the public full Android replay. */
    fun verifyArchive(
        repository: Path,
        archive: Path,
        archiveDigest: String,
        core: String,
        facade: String,
        runtime: String,
    ): JsonObject
}

/** The fail-closed consumer: the public Android replay is `full_android_consumer.py`. */
object FullAndroidConsumerUnavailable : FullAndroidConsumerPort {
    override val modules: List<String> = FullAndroidAdapterRules.MODULES

    private fun unavailable(): Nothing = throw UnsupportedOperationException(
        "public full Android consumer is not ported: full_android_consumer.py (approved_cases, " +
            "original_source_hashes, source_and_toolchain, verify_archive) has no Kotlin counterpart",
    )

    override fun approvedCases(repository: Path): Pair<JsonObject, List<JsonObject>> = unavailable()

    override fun originalSourceHashes(repository: Path): JsonObject = unavailable()

    override fun sourceAndToolchain(repository: Path, prepared: JsonObject): JsonElement =
        unavailable()

    override fun verifyArchive(
        repository: Path,
        archive: Path,
        archiveDigest: String,
        core: String,
        facade: String,
        runtime: String,
    ): JsonObject = unavailable()
}

/**
 * `full_android_adapter.verify_full_android_staged_consumer`: bind the signed Android lane
 * expectations to the public full consumer replay.
 *
 * The caller verifies the audit signature first; this function re-derives every bound identity from
 * the archive, the approved manifest, and the independently measured source/toolchain digest.
 */
object FullAndroidAdapter {
    fun verify(
        repository: Path,
        candidateSha: String,
        laneId: String,
        selected: JsonObject,
        archive: Path,
        expected: JsonElement,
        gateResult: JsonElement,
        consumer: FullAndroidConsumerPort = FullAndroidConsumerUnavailable,
    ): JsonObject {
        val route = FullAndroidAdapterRules.ROUTES[laneId]
            ?: throw IllegalArgumentException(
                "public full Android verifier does not cover lane: $laneId",
            )
        if (!FullAndroidAdapterRules.isCandidate(candidateSha)) {
            throw IllegalArgumentException("exact Android candidate SHA is invalid")
        }
        val audit = expected as? JsonObject
            ?: throw IllegalArgumentException("signed Android lane audit is missing")
        val hashes = audit["expected_artifact_hashes"] as? JsonObject
        val digests = audit["expected_archive_digests"] as? JsonObject
        val runtime = Py.str(audit["expected_runtime_identity"])
        val sourceDigest = Py.str(audit["expected_android_source_toolchain_sha256"])
        val archiveDigest = Py.str(digests?.get("staged-consumer"))
        val hashValues = hashes?.mapValues { (_, value) -> Py.str(value) }
        val hashKeys = hashValues?.keys ?: emptySet()
        val hashDigests = hashValues?.values ?: emptySet<String?>()
        if (hashes == null || hashKeys != consumer.modules.toSet() ||
            hashDigests.any { !FullAndroidAdapterRules.isDigest(it) } ||
            !FullAndroidAdapterRules.isDigest(runtime) ||
            !FullAndroidAdapterRules.isDigest(archiveDigest) ||
            !FullAndroidAdapterRules.isDigest(sourceDigest)
        ) {
            throw IllegalArgumentException(
                "signed Android archive, artifact, runtime, or source/toolchain identity is incomplete",
            )
        }
        val gate = gateResult as? JsonObject
            ?: throw IllegalArgumentException("generic Android staged-consumer gate did not pass")
        if (Py.str(gate["gate"]) != "staged-consumer" ||
            Py.str(gate["status"]) != "PASSED" ||
            gate["complete_selected_suite"] != JsonPrimitive(true)
        ) {
            throw IllegalArgumentException("generic Android staged-consumer gate did not pass")
        }

        CleanRequire.require(repository, candidateSha)
        val (manifest, cases) = consumer.approvedCases(repository)
        val approved = cases.mapNotNull { Py.str(it["id"]) }
        val selectedIds = (selected["case_ids"] as? JsonArray)?.mapNotNull { Py.str(it) }
        val lanes = manifest["lanes"] as? JsonObject
        if (selectedIds != approved || lanes?.get(laneId) == null) {
            throw IllegalArgumentException(
                "signed Android lane selects a different approved case suite: $laneId",
            )
        }
        val measured = consumer.sourceAndToolchain(
            repository,
            kotlinx.serialization.json.buildJsonObject {
                put("source_hashes", consumer.originalSourceHashes(repository))
            },
        )
        if (IndependentGates.digest(measured) != sourceDigest) {
            throw IllegalArgumentException("independent Android source/toolchain digest differs")
        }

        val public = consumer.verifyArchive(
            repository,
            archive,
            archiveDigest!!,
            hashValues!!["dyn4k-core"]!!,
            hashValues!!["dyn4k"]!!,
            runtime!!,
        )
        if (Py.str(public["candidate_sha"]) != candidateSha ||
            Py.str(public["archive_digest"]) != archiveDigest ||
            !Py.equalsInt(public["cases"], approved.size.toLong())
        ) {
            throw IllegalArgumentException(
                "public Android verifier returned a different candidate or suite",
            )
        }
        if (public["gate"] != gateResult) {
            throw IllegalArgumentException(
                "public Android verifier differs from independent gate: $laneId",
            )
        }
        val receipt = IndependentGates.json(archive.resolve("receipt.json")) as? JsonObject
            ?: throw IllegalArgumentException("Android archive receipt is not an object")
        val runtimeRecord = IndependentGates.json(archive.resolve("runtime.json")) as? JsonObject
            ?: throw IllegalArgumentException("Android runtime record is not an object")
        val (api, configuration) = route
        val properties = runtimeRecord["properties"] as? JsonObject
        if (Py.str(receipt["lane"]) != laneId ||
            Py.str(receipt["configuration"]) != configuration ||
            Py.str(properties?.get("ro.build.version.sdk")) != api ||
            Py.str(properties?.get("ro.product.cpu.abi")) != "x86_64"
        ) {
            throw IllegalArgumentException("Android archive route differs from selected lane: $laneId")
        }
        return public
    }
}
