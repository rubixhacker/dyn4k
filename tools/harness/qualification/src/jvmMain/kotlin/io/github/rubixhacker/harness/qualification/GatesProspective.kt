package io.github.rubixhacker.harness.qualification

import io.github.rubixhacker.harness.numerical.TraceFiles
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.Path
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/**
 * `independent_gates.py`, prospective slice: the approved checker and producer closures a
 * candidate inherits, and the rotation-arithmetic audit of one raw target payload.
 *
 * Every table this file reads is generated from the reference by
 * `parity/dump_gate_constants.py`; the ancestry-window chain is transcribed in the reference's
 * order, because each window's blob closure is what the gate then binds.
 */
object GatesProspective {
    private const val SOURCE_DIR = "tools/numerical/portable"
    private const val CHECKER_ANCESTRY = "prospective checker revision ancestry is unavailable"
    private const val CHECKER_BLOB = "prospective policy/checker blob differs"
    private const val PRODUCER_ANCESTRY =
        "reviewed P2 raw producer revision ancestry is unavailable"
    private const val PRODUCER_BLOB = "reviewed P2 raw producer blob differs"

    /**
     * `_prospective_checker_binding`: the approved checker closure of one candidate.
     *
     * Returns the relative path and committed digest of every approved checker, the adopted
     * prospective catalog, and the shared and capture dependencies of the selected window.
     */
    fun checkerBinding(
        repository: Path,
        candidateSha: String,
        gate: GateSource = GateGit,
    ): Map<String, String> {
        fun window(revision: String): Boolean =
            gate.descendsFrom(repository, revision, candidateSha, CHECKER_ANCESTRY)

        val executableWindow = window(GateConstants.PROSPECTIVE_EXECUTABLE_CHECKER_REVISION)
        val ordinaryDiagnosticWindow = window(GateConstants.ORDINARY_DIAGNOSTIC_SOURCE_REVISION)
        val ordinaryDiagnosticJarWindow = window(GateConstants.ORDINARY_DIAGNOSTIC_JAR_SOURCE_REVISION)
        val ordinaryDiagnosticSampleWindow =
            window(GateConstants.ORDINARY_DIAGNOSTIC_SAMPLE_SOURCE_REVISION)
        val ordinaryDiagnosticSampleFixedWindow =
            window(GateConstants.ORDINARY_DIAGNOSTIC_SAMPLE_FIXED_SOURCE_REVISION)
        val ordinaryDiagnosticPortableStageWindow =
            window(GateConstants.ORDINARY_DIAGNOSTIC_PORTABLE_STAGE_SOURCE_REVISION)
        val ordinaryDiagnosticOwnedProcessWindow =
            window(GateConstants.ORDINARY_DIAGNOSTIC_OWNED_PROCESS_SOURCE_REVISION)
        val ordinaryDiagnosticTraceOriginWindow =
            window(GateConstants.ORDINARY_DIAGNOSTIC_TRACE_ORIGIN_SOURCE_REVISION)
        val ordinaryDiagnosticLineageRemedyWindow =
            window(GateConstants.ORDINARY_DIAGNOSTIC_LINEAGE_REMEDY_SOURCE_REVISION)
        val ordinaryDiagnosticCleanupDetailWindow =
            window(GateConstants.ORDINARY_DIAGNOSTIC_CLEANUP_DETAIL_SOURCE_REVISION)
        val ordinaryDiagnosticSnapshotWindow =
            window(GateConstants.ORDINARY_DIAGNOSTIC_SNAPSHOT_SOURCE_REVISION)
        val ordinaryDiagnosticChildFirstWindow =
            window(GateConstants.ORDINARY_DIAGNOSTIC_CHILD_FIRST_SOURCE_REVISION)
        val ordinaryDiagnosticRemedyWindow =
            window(GateConstants.ORDINARY_DIAGNOSTIC_REMEDY_SOURCE_REVISION)
        val ordinaryDiagnosticBuildCleanupWindow =
            window(GateConstants.ORDINARY_DIAGNOSTIC_BUILD_CLEANUP_SOURCE_REVISION)
        val ordinaryDiagnosticBuildPidWindow =
            window(GateConstants.ORDINARY_DIAGNOSTIC_BUILD_PID_SOURCE_REVISION)
        val ordinaryDiagnosticBuildLifecycleWindow =
            window(GateConstants.ORDINARY_DIAGNOSTIC_BUILD_LIFECYCLE_SOURCE_REVISION)
        val ordinaryDiagnosticBuildNormalExitWindow =
            window(GateConstants.ORDINARY_DIAGNOSTIC_BUILD_NORMAL_EXIT_SOURCE_REVISION)
        val ordinaryDiagnosticBuildLeaderIdentityWindow =
            window(GateConstants.ORDINARY_DIAGNOSTIC_BUILD_LEADER_IDENTITY_SOURCE_REVISION)
        val ordinaryDiagnosticRealRebuildWindow =
            window(GateConstants.ORDINARY_DIAGNOSTIC_REAL_REBUILD_SOURCE_REVISION)
        val ordinaryDiagnosticReplayBoundariesWindow =
            window(GateConstants.ORDINARY_DIAGNOSTIC_REPLAY_BOUNDARIES_SOURCE_REVISION)
        val ordinaryDiagnosticLaunchOwnershipWindow =
            window(GateConstants.ORDINARY_DIAGNOSTIC_LAUNCH_OWNERSHIP_SOURCE_REVISION)
        val ordinaryDiagnosticDuplicateLaunchWindow =
            window(GateConstants.ORDINARY_DIAGNOSTIC_DUPLICATE_LAUNCH_SOURCE_REVISION)
        val ordinaryDiagnosticCompilerAdmissionWindow =
            window(GateConstants.ORDINARY_DIAGNOSTIC_COMPILER_ADMISSION_SOURCE_REVISION)
        val ordinaryDiagnosticThreadCloneWindow =
            window(GateConstants.ORDINARY_DIAGNOSTIC_THREAD_CLONE_SOURCE_REVISION)
        val observerEnvReplayWindow = window(GateConstants.OBSERVER_ENV_REPLAY_SOURCE_REVISION)
        val jdiReplayCostWindow = window(GateConstants.JDI_REPLAY_COST_SOURCE_REVISION)
        val replayCostWindow = window(GateConstants.REPLAY_COST_SOURCE_REVISION)
        val archivePrivacyWindow = window(GateConstants.ARCHIVE_PRIVACY_SOURCE_REVISION)
        val workerPidWindow = window(GateConstants.WORKER_PID_SOURCE_REVISION)
        val nativeUdpWindow = window(GateConstants.NATIVE_UDP_GRAMMAR_SOURCE_REVISION)
        val observerBoundsWindow = window(GateConstants.OBSERVER_BOUNDS_SOURCE_REVISION)
        val pathModelWindow = window(GateConstants.PATH_MODEL_SOURCE_REVISION)
        val observerWindow = window(GateConstants.OBSERVER_OPERANDS_SOURCE_REVISION)
        val sharedWriterWindow = window(GateConstants.SHARED_WRITER_SOURCE_REVISION)
        val outputReviewWindow = window(GateConstants.OUTPUT_REVIEW_REMEDY_SOURCE_REVISION)
        val outputProvenanceWindow = window(GateConstants.OUTPUT_PROVENANCE_SOURCE_REVISION)
        val baselineCompatWindow = window(GateConstants.BASELINE_COMPAT_SOURCE_REVISION)
        val privateLaunchWindow = window(GateConstants.PRIVATE_LAUNCH_SOURCE_REVISION)
        val v6Window = window(GateConstants.PROSPECTIVE_V6_SOURCE_REVISION)

        val approved: Map<String, String> = when {
            observerEnvReplayWindow ->
                GateConstants.APPROVED_PROSPECTIVE_OBSERVER_ENV_REPLAY_CHECKERS
            jdiReplayCostWindow || replayCostWindow ->
                GateConstants.APPROVED_PROSPECTIVE_REPLAY_COST_CHECKERS
            archivePrivacyWindow -> GateConstants.APPROVED_PROSPECTIVE_ARCHIVE_PRIVACY_CHECKERS
            workerPidWindow -> GateConstants.APPROVED_PROSPECTIVE_WORKER_PID_CHECKERS
            nativeUdpWindow -> GateConstants.APPROVED_PROSPECTIVE_NATIVE_UDP_GRAMMAR_CHECKERS
            observerBoundsWindow -> GateConstants.APPROVED_PROSPECTIVE_OBSERVER_BOUNDS_CHECKERS
            pathModelWindow || observerWindow || sharedWriterWindow || outputReviewWindow ||
                outputProvenanceWindow ||
                window(GateConstants.FAILED_OUTPUT_WRAPPER_SOURCE_REVISION) ->
                throw IllegalArgumentException("$CHECKER_BLOB: incomplete output source")
            baselineCompatWindow -> GateConstants.APPROVED_PROSPECTIVE_BASELINE_COMPAT_CHECKERS
            privateLaunchWindow -> GateConstants.APPROVED_PROSPECTIVE_PRIVATE_LAUNCH_CHECKERS
            window(GateConstants.FAILED_PRIVATE_LAUNCH_SOURCE_REVISION) ->
                throw IllegalArgumentException("$CHECKER_BLOB: unapproved private launch revision")
            v6Window -> GateConstants.APPROVED_PROSPECTIVE_V6_CHECKERS
            window(GateConstants.PROSPECTIVE_JVM8_AGENT_SOURCE_REVISION) ->
                GateConstants.APPROVED_PROSPECTIVE_JVM8_AGENT_CHECKERS
            window(GateConstants.PROSPECTIVE_JVM8_SOURCE_REVISION) ->
                GateConstants.APPROVED_PROSPECTIVE_JVM8_CHECKERS
            window(GateConstants.PROSPECTIVE_REPLAY_SCRATCH_REVISION) ->
                GateConstants.PROSPECTIVE_REPLAY_SCRATCH_CHECKERS
            executableWindow -> GateConstants.APPROVED_PROSPECTIVE_EXECUTABLE_CHECKERS
            window(GateConstants.PROSPECTIVE_INVENTORY_FIX_CHECKER_REVISION) ->
                GateConstants.APPROVED_PROSPECTIVE_INVENTORY_FIX_CHECKERS
            window(GateConstants.PROSPECTIVE_NUMERIC_PROBE_CHECKER_REVISION) ->
                GateConstants.APPROVED_PROSPECTIVE_NUMERIC_PROBE_CHECKERS
            window(GateConstants.PROSPECTIVE_REPRESENTED_CHECKER_REVISION) ->
                GateConstants.APPROVED_PROSPECTIVE_REPRESENTED_CHECKERS
            window(GateConstants.PROSPECTIVE_CHECKER_REVISION) -> {
                val comparator = gate.committedDigest(
                    repository, candidateSha, "$SOURCE_DIR/prospective_compare.py",
                )
                if (comparator ==
                    GateConstants.APPROVED_PROSPECTIVE_SIGNED_ZERO_CHECKERS["prospective_compare.py"]
                ) {
                    GateConstants.APPROVED_PROSPECTIVE_SIGNED_ZERO_CHECKERS
                } else {
                    GateConstants.APPROVED_PROSPECTIVE_CHECKERS
                }
            }
            window(GateConstants.PROSPECTIVE_BRIDGE_CHECKER_REVISION) ->
                GateConstants.APPROVED_PROSPECTIVE_CHECKERS
            window(GateConstants.PROSPECTIVE_ASSEMBLED_CHECKER_REVISION) ->
                GateConstants.APPROVED_PROSPECTIVE_ASSEMBLED_CHECKERS
            window(GatesNumerical.PROSPECTIVE_HISTORICAL_POLICY_REVISION) ->
                GateConstants.APPROVED_PROSPECTIVE_POLICY_CHECKERS
            else -> throw IllegalArgumentException(
                "prospective checker candidate predates approved revisions",
            )
        }
        for ((filename, current) in GateConstants.PINNED_PROSPECTIVE_LOCAL_CHECKERS) {
            val relative = "$SOURCE_DIR/$filename"
            if (gate.localBlob(relative, CHECKER_BLOB) != current) {
                throw IllegalArgumentException("$CHECKER_BLOB: $relative")
            }
        }
        for ((filename, expected) in approved) {
            val relative = "$SOURCE_DIR/$filename"
            if (gate.committedBlob(repository, candidateSha, relative, CHECKER_BLOB) != expected) {
                throw IllegalArgumentException("$CHECKER_BLOB: $relative")
            }
        }
        val executableDependencies: Map<String, String> = when {
            ordinaryDiagnosticThreadCloneWindow ->
                GateConstants.ORDINARY_DIAGNOSTIC_THREAD_CLONE_CAPTURE_DEPENDENCIES
            ordinaryDiagnosticCompilerAdmissionWindow ->
                GateConstants.ORDINARY_DIAGNOSTIC_COMPILER_ADMISSION_CAPTURE_DEPENDENCIES
            ordinaryDiagnosticDuplicateLaunchWindow ->
                GateConstants.ORDINARY_DIAGNOSTIC_DUPLICATE_LAUNCH_CAPTURE_DEPENDENCIES
            ordinaryDiagnosticLaunchOwnershipWindow ->
                GateConstants.ORDINARY_DIAGNOSTIC_LAUNCH_OWNERSHIP_CAPTURE_DEPENDENCIES
            ordinaryDiagnosticReplayBoundariesWindow ->
                GateConstants.ORDINARY_DIAGNOSTIC_REPLAY_BOUNDARIES_CAPTURE_DEPENDENCIES
            ordinaryDiagnosticRealRebuildWindow ->
                GateConstants.ORDINARY_DIAGNOSTIC_REAL_REBUILD_CAPTURE_DEPENDENCIES
            ordinaryDiagnosticBuildLeaderIdentityWindow ->
                GateConstants.ORDINARY_DIAGNOSTIC_BUILD_LEADER_IDENTITY_CAPTURE_DEPENDENCIES
            ordinaryDiagnosticBuildNormalExitWindow ->
                GateConstants.ORDINARY_DIAGNOSTIC_BUILD_NORMAL_EXIT_CAPTURE_DEPENDENCIES
            ordinaryDiagnosticBuildLifecycleWindow ->
                GateConstants.ORDINARY_DIAGNOSTIC_BUILD_LIFECYCLE_CAPTURE_DEPENDENCIES
            ordinaryDiagnosticBuildPidWindow ->
                GateConstants.ORDINARY_DIAGNOSTIC_BUILD_PID_CAPTURE_DEPENDENCIES
            ordinaryDiagnosticBuildCleanupWindow ->
                GateConstants.ORDINARY_DIAGNOSTIC_BUILD_CLEANUP_CAPTURE_DEPENDENCIES
            ordinaryDiagnosticRemedyWindow ->
                GateConstants.ORDINARY_DIAGNOSTIC_REMEDY_CAPTURE_DEPENDENCIES
            ordinaryDiagnosticChildFirstWindow ->
                GateConstants.ORDINARY_DIAGNOSTIC_CHILD_FIRST_CAPTURE_DEPENDENCIES
            ordinaryDiagnosticSnapshotWindow ->
                GateConstants.ORDINARY_DIAGNOSTIC_SNAPSHOT_CAPTURE_DEPENDENCIES
            ordinaryDiagnosticCleanupDetailWindow ->
                GateConstants.ORDINARY_DIAGNOSTIC_CLEANUP_DETAIL_CAPTURE_DEPENDENCIES
            ordinaryDiagnosticLineageRemedyWindow ->
                GateConstants.ORDINARY_DIAGNOSTIC_LINEAGE_REMEDY_CAPTURE_DEPENDENCIES
            ordinaryDiagnosticTraceOriginWindow ->
                GateConstants.ORDINARY_DIAGNOSTIC_TRACE_ORIGIN_CAPTURE_DEPENDENCIES
            ordinaryDiagnosticOwnedProcessWindow ->
                GateConstants.ORDINARY_DIAGNOSTIC_OWNED_PROCESS_CAPTURE_DEPENDENCIES
            ordinaryDiagnosticPortableStageWindow ->
                GateConstants.ORDINARY_DIAGNOSTIC_PORTABLE_STAGE_CAPTURE_DEPENDENCIES
            ordinaryDiagnosticSampleFixedWindow ->
                GateConstants.ORDINARY_DIAGNOSTIC_SAMPLE_FIXED_CAPTURE_DEPENDENCIES
            ordinaryDiagnosticSampleWindow ->
                GateConstants.ORDINARY_DIAGNOSTIC_SAMPLE_CAPTURE_DEPENDENCIES
            ordinaryDiagnosticJarWindow -> GateConstants.ORDINARY_DIAGNOSTIC_JAR_CAPTURE_DEPENDENCIES
            ordinaryDiagnosticWindow -> GateConstants.ORDINARY_DIAGNOSTIC_CAPTURE_DEPENDENCIES
            observerEnvReplayWindow -> GateConstants.OBSERVER_ENV_REPLAY_CAPTURE_DEPENDENCIES
            jdiReplayCostWindow -> GateConstants.JDI_REPLAY_COST_CAPTURE_DEPENDENCIES
            replayCostWindow -> GateConstants.REPLAY_COST_CAPTURE_DEPENDENCIES
            archivePrivacyWindow -> GateConstants.ARCHIVE_PRIVACY_CAPTURE_DEPENDENCIES
            workerPidWindow -> GateConstants.WORKER_PID_CAPTURE_DEPENDENCIES
            nativeUdpWindow -> GateConstants.NATIVE_UDP_GRAMMAR_CAPTURE_DEPENDENCIES
            observerBoundsWindow -> GateConstants.OBSERVER_BOUNDS_CAPTURE_DEPENDENCIES
            baselineCompatWindow -> GateConstants.BASELINE_COMPAT_CAPTURE_DEPENDENCIES
            privateLaunchWindow -> GateConstants.PRIVATE_LAUNCH_CAPTURE_DEPENDENCIES
            v6Window -> GateConstants.PROSPECTIVE_V6_CAPTURE_DEPENDENCIES
            executableWindow -> GateConstants.PROSPECTIVE_EXECUTABLE_CAPTURE_DEPENDENCIES
            else -> emptyMap()
        }
        val localDependencies = LinkedHashMap<String, String>()
        localDependencies.putAll(GateConstants.APPROVED_PROSPECTIVE_EXECUTABLE_SHARED)
        localDependencies.putAll(GateConstants.ORDINARY_DIAGNOSTIC_THREAD_CLONE_CAPTURE_DEPENDENCIES)
        for ((relative, expected) in localDependencies) {
            if (gate.localBlob(relative, CHECKER_BLOB) != expected) {
                throw IllegalArgumentException("$CHECKER_BLOB: $relative")
            }
        }
        if (executableWindow) {
            val committedDependencies = LinkedHashMap<String, String>()
            committedDependencies.putAll(GateConstants.APPROVED_PROSPECTIVE_EXECUTABLE_SHARED)
            committedDependencies.putAll(executableDependencies)
            for ((relative, expected) in committedDependencies) {
                if (gate.committedBlob(repository, candidateSha, relative, CHECKER_BLOB) !=
                    expected
                ) {
                    throw IllegalArgumentException("$CHECKER_BLOB: $relative")
                }
            }
        }
        val catalog = "$SOURCE_DIR/prospective_policy_catalog.json"
        val committedCatalog = gate.committedDigest(repository, candidateSha, catalog)
        val catalogSha256 = GatesNumerical.prospectivePolicyVersion(repository, candidateSha).second
        if (committedCatalog != catalogSha256 ||
            gate.localBlob(catalog, CHECKER_BLOB) !=
            GatesNumerical.PROSPECTIVE_POLICY_SHA256
        ) {
            throw IllegalArgumentException("$CHECKER_BLOB: $catalog")
        }
        val result = LinkedHashMap<String, String>()
        for ((name, value) in approved) result["$SOURCE_DIR/$name"] = value
        result[catalog] = catalogSha256
        if (executableWindow) result.putAll(GateConstants.APPROVED_PROSPECTIVE_EXECUTABLE_SHARED)
        result.putAll(executableDependencies)
        return result
    }

    /** `_p2_producer_binding`: the reviewed raw producer closure of one candidate. */
    fun p2ProducerBinding(
        repository: Path,
        candidateSha: String,
        gate: GateSource = GateGit,
    ): Map<String, String> {
        fun window(revision: String): Boolean =
            gate.descendsFrom(repository, revision, candidateSha, PRODUCER_ANCESTRY)

        if (!window(GateConstants.PROSPECTIVE_CHECKER_REVISION)) {
            throw IllegalArgumentException("candidate predates reviewed P2 raw producer revision")
        }
        val observerEnvReplayWindow = window(GateConstants.OBSERVER_ENV_REPLAY_SOURCE_REVISION)
        val jdiReplayCostWindow = window(GateConstants.JDI_REPLAY_COST_SOURCE_REVISION)
        val replayCostWindow = window(GateConstants.REPLAY_COST_SOURCE_REVISION)
        val archivePrivacyWindow = window(GateConstants.ARCHIVE_PRIVACY_SOURCE_REVISION)
        val workerPidWindow = window(GateConstants.WORKER_PID_SOURCE_REVISION)
        val nativeUdpWindow = window(GateConstants.NATIVE_UDP_GRAMMAR_SOURCE_REVISION)
        val observerBoundsWindow = window(GateConstants.OBSERVER_BOUNDS_SOURCE_REVISION)
        val pathModelWindow = window(GateConstants.PATH_MODEL_SOURCE_REVISION)
        val observerWindow = window(GateConstants.OBSERVER_OPERANDS_SOURCE_REVISION)
        val sharedWriterWindow = window(GateConstants.SHARED_WRITER_SOURCE_REVISION)
        val outputReviewWindow = window(GateConstants.OUTPUT_REVIEW_REMEDY_SOURCE_REVISION)
        val outputProvenanceWindow = window(GateConstants.OUTPUT_PROVENANCE_SOURCE_REVISION)
        val baselineCompatWindow = window(GateConstants.BASELINE_COMPAT_SOURCE_REVISION)
        val privateLaunchWindow = window(GateConstants.PRIVATE_LAUNCH_SOURCE_REVISION)
        val v6Window = window(GateConstants.PROSPECTIVE_V6_SOURCE_REVISION)
        val ordinaryDiagnosticWindow = window(GateConstants.ORDINARY_DIAGNOSTIC_SOURCE_REVISION)
        val ordinaryDiagnosticJarWindow = window(GateConstants.ORDINARY_DIAGNOSTIC_JAR_SOURCE_REVISION)
        val ordinaryDiagnosticSampleWindow =
            window(GateConstants.ORDINARY_DIAGNOSTIC_SAMPLE_SOURCE_REVISION)
        val ordinaryDiagnosticSampleFixedWindow =
            window(GateConstants.ORDINARY_DIAGNOSTIC_SAMPLE_FIXED_SOURCE_REVISION)
        val ordinaryDiagnosticPortableStageWindow =
            window(GateConstants.ORDINARY_DIAGNOSTIC_PORTABLE_STAGE_SOURCE_REVISION)
        val ordinaryDiagnosticOwnedProcessWindow =
            window(GateConstants.ORDINARY_DIAGNOSTIC_OWNED_PROCESS_SOURCE_REVISION)
        val ordinaryDiagnosticTraceOriginWindow =
            window(GateConstants.ORDINARY_DIAGNOSTIC_TRACE_ORIGIN_SOURCE_REVISION)
        val ordinaryDiagnosticLineageRemedyWindow =
            window(GateConstants.ORDINARY_DIAGNOSTIC_LINEAGE_REMEDY_SOURCE_REVISION)
        val ordinaryDiagnosticCleanupDetailWindow =
            window(GateConstants.ORDINARY_DIAGNOSTIC_CLEANUP_DETAIL_SOURCE_REVISION)
        val ordinaryDiagnosticSnapshotWindow =
            window(GateConstants.ORDINARY_DIAGNOSTIC_SNAPSHOT_SOURCE_REVISION)
        val ordinaryDiagnosticChildFirstWindow =
            window(GateConstants.ORDINARY_DIAGNOSTIC_CHILD_FIRST_SOURCE_REVISION)
        val ordinaryDiagnosticRemedyWindow =
            window(GateConstants.ORDINARY_DIAGNOSTIC_REMEDY_SOURCE_REVISION)
        val ordinaryDiagnosticBuildCleanupWindow =
            window(GateConstants.ORDINARY_DIAGNOSTIC_BUILD_CLEANUP_SOURCE_REVISION)
        val ordinaryDiagnosticBuildPidWindow =
            window(GateConstants.ORDINARY_DIAGNOSTIC_BUILD_PID_SOURCE_REVISION)
        val ordinaryDiagnosticBuildLifecycleWindow =
            window(GateConstants.ORDINARY_DIAGNOSTIC_BUILD_LIFECYCLE_SOURCE_REVISION)
        val ordinaryDiagnosticBuildNormalExitWindow =
            window(GateConstants.ORDINARY_DIAGNOSTIC_BUILD_NORMAL_EXIT_SOURCE_REVISION)
        val ordinaryDiagnosticBuildLeaderIdentityWindow =
            window(GateConstants.ORDINARY_DIAGNOSTIC_BUILD_LEADER_IDENTITY_SOURCE_REVISION)
        val ordinaryDiagnosticRealRebuildWindow =
            window(GateConstants.ORDINARY_DIAGNOSTIC_REAL_REBUILD_SOURCE_REVISION)
        val ordinaryDiagnosticReplayBoundariesWindow =
            window(GateConstants.ORDINARY_DIAGNOSTIC_REPLAY_BOUNDARIES_SOURCE_REVISION)
        val ordinaryDiagnosticLaunchOwnershipWindow =
            window(GateConstants.ORDINARY_DIAGNOSTIC_LAUNCH_OWNERSHIP_SOURCE_REVISION)
        val ordinaryDiagnosticDuplicateLaunchWindow =
            window(GateConstants.ORDINARY_DIAGNOSTIC_DUPLICATE_LAUNCH_SOURCE_REVISION)
        val ordinaryDiagnosticCompilerAdmissionWindow =
            window(GateConstants.ORDINARY_DIAGNOSTIC_COMPILER_ADMISSION_SOURCE_REVISION)
        val ordinaryDiagnosticThreadCloneWindow =
            window(GateConstants.ORDINARY_DIAGNOSTIC_THREAD_CLONE_SOURCE_REVISION)
        val jdk21Jdi = window(GateConstants.P2_JDK21_JDI_SOURCE_REVISION)
        val correctedJdi = window(GateConstants.P2_CORRECTED_JDI_SOURCE_REVISION)
        val boundedJdi = window(GateConstants.P2_BOUNDED_JDI_SOURCE_REVISION)
        val rotationPremise = window(GateConstants.P2_ROTATION_PREMISE_SOURCE_REVISION)
        val booleanJdiFinal = window(GateConstants.P2_BOOLEAN_JDI_FINAL_SOURCE_REVISION)
        val booleanJdi = window(GateConstants.P2_BOOLEAN_JDI_SOURCE_REVISION)

        val approved: Map<String, String> = when {
            observerEnvReplayWindow -> GateConstants.APPROVED_P2_OBSERVER_ENV_REPLAY_PRODUCERS
            jdiReplayCostWindow || replayCostWindow -> GateConstants.APPROVED_P2_REPLAY_COST_PRODUCERS
            archivePrivacyWindow -> GateConstants.APPROVED_P2_ARCHIVE_PRIVACY_PRODUCERS
            workerPidWindow -> GateConstants.APPROVED_P2_WORKER_PID_PRODUCERS
            nativeUdpWindow -> GateConstants.APPROVED_P2_NATIVE_UDP_GRAMMAR_PRODUCERS
            observerBoundsWindow -> GateConstants.APPROVED_P2_OBSERVER_BOUNDS_PRODUCERS
            pathModelWindow || observerWindow || sharedWriterWindow || outputReviewWindow ||
                outputProvenanceWindow ||
                window(GateConstants.FAILED_OUTPUT_WRAPPER_SOURCE_REVISION) ->
                throw IllegalArgumentException("$PRODUCER_BLOB: incomplete output source")
            baselineCompatWindow -> GateConstants.APPROVED_P2_BASELINE_COMPAT_PRODUCERS
            privateLaunchWindow -> GateConstants.APPROVED_P2_PRIVATE_LAUNCH_PRODUCERS
            window(GateConstants.FAILED_PRIVATE_LAUNCH_SOURCE_REVISION) ->
                throw IllegalArgumentException(
                    "$PRODUCER_BLOB: unapproved private launch revision",
                )
            v6Window -> GateConstants.APPROVED_P2_V6_PRODUCERS
            window(GateConstants.PROSPECTIVE_JVM8_SOURCE_REVISION) ->
                GateConstants.APPROVED_P2_JVM8_PRODUCERS
            jdk21Jdi || correctedJdi || boundedJdi -> GateConstants.P2_ROTATION_PREMISE_PRODUCERS
            rotationPremise -> GateConstants.P2_ROTATION_PREMISE_PRODUCERS
            booleanJdiFinal -> GateConstants.P2_BOOLEAN_JDI_FINAL_PRODUCERS
            booleanJdi -> GateConstants.P2_BOOLEAN_JDI_PRODUCERS
            window(GateConstants.P2_BOOLEAN_JDI_HELPER_REVISION) ->
                throw IllegalArgumentException("candidate has incomplete Boolean JDI producer lineage")
            window(GateConstants.P2_D3D6_SOURCE_REVISION) -> GateConstants.P2_D3D6_PRODUCERS
            window(GateConstants.P2_GENERIC_CLASS_ASSEMBLY_REVISION) ->
                GateConstants.APPROVED_P2_GENERIC_CLASS_PRODUCERS
            window(GateConstants.P2_DYNAMIC_CLASS_ASSEMBLY_REVISION) ->
                GateConstants.APPROVED_P2_DYNAMIC_CLASS_PRODUCERS
            window(GateConstants.P2_PORTABLE_PROVIDER_ASSEMBLY_REVISION) ->
                GateConstants.APPROVED_P2_PORTABLE_PROVIDER_PRODUCERS
            window(GateConstants.P2_ARITHMETIC_COVERAGE_ASSEMBLY_REVISION) ->
                GateConstants.APPROVED_P2_ARITHMETIC_COVERAGE_PRODUCERS
            window(GateConstants.P2_ARITHMETIC_ASSEMBLY_REVISION) ->
                GateConstants.APPROVED_P2_ARITHMETIC_PRODUCERS
            window(GateConstants.P2_COMBINED_ASSEMBLY_REVISION) ->
                GateConstants.APPROVED_P2_COMBINED_PRODUCERS
            window(GateConstants.P2_DIRECT_WASM_22EFD_ASSEMBLY_REVISION) ->
                GateConstants.APPROVED_P2_DIRECT_WASM_22EFD_PRODUCERS
            window(GateConstants.P2_OPERATION_ASSEMBLY_REVISION) ->
                GateConstants.APPROVED_P2_OPERATION_PRODUCERS
            window(GateConstants.P2_NATIVE_02C_ASSEMBLY_REVISION) ->
                GateConstants.APPROVED_P2_NATIVE_02C_PRODUCERS
            window(GateConstants.P2_EDBC_ASSEMBLY_REVISION) ->
                GateConstants.APPROVED_P2_EDBC_PRODUCERS
            window(GateConstants.P2_CURRENT_ASSEMBLY_REVISION) ->
                GateConstants.APPROVED_P2_CURRENT_PRODUCERS
            window(GateConstants.P2_ORIGINAL_OBJECT_ASSEMBLY_REVISION) ->
                GateConstants.APPROVED_P2_PRODUCERS
            window(GateConstants.P2_ORIGINAL_OBJECT_OWNER_REVISION) ->
                GateConstants.APPROVED_P2_ORIGINAL_OBJECT_OWNER_PRODUCERS
            window(GateConstants.P2_CANONICAL_ARCHIVE_ASSEMBLY_REVISION) ->
                GateConstants.APPROVED_P2_PRE_ORIGINAL_OBJECT_PRODUCERS
            window(GateConstants.P2_CANONICAL_ARCHIVE_OWNER_REVISION) ->
                GateConstants.APPROVED_P2_OWNER_CANONICAL_PRODUCERS
            window(GateConstants.P2_NUMERICAL_ARCHIVE_REVISION) ||
                window(GateConstants.P2_NUMERICAL_ARCHIVE_OWNER_REVISION) ->
                GateConstants.APPROVED_P2_PRE_ARITHMETIC_PRODUCERS
            window(GateConstants.P2_CLASS_LOAD_REVISION) ->
                GateConstants.APPROVED_P2_CLASS_LOAD_PRODUCERS
            else -> GateConstants.APPROVED_P2_HISTORICAL_PRODUCERS
        }
        for ((name, localApproved) in GateConstants.PINNED_P2_CURRENT_LOCAL_PRODUCERS) {
            val relative = "$SOURCE_DIR/$name"
            if (gate.localBlob(relative, PRODUCER_BLOB) != localApproved) {
                throw IllegalArgumentException("$PRODUCER_BLOB: $relative")
            }
        }
        for ((name, expected) in approved) {
            val relative = "$SOURCE_DIR/$name"
            if (gate.committedBlob(repository, candidateSha, relative, PRODUCER_BLOB) != expected) {
                throw IllegalArgumentException("$PRODUCER_BLOB: $relative")
            }
        }
        val cloneDependencies = GateConstants.P2_ORDINARY_DIAGNOSTIC_THREAD_CLONE_DEPENDENCIES
        when {
            jdk21Jdi -> {
                val dependencies = when {
                    ordinaryDiagnosticThreadCloneWindow -> cloneDependencies
                    ordinaryDiagnosticCompilerAdmissionWindow ->
                        GateConstants.P2_ORDINARY_DIAGNOSTIC_COMPILER_ADMISSION_DEPENDENCIES
                    ordinaryDiagnosticDuplicateLaunchWindow ->
                        GateConstants.P2_ORDINARY_DIAGNOSTIC_DUPLICATE_LAUNCH_DEPENDENCIES
                    ordinaryDiagnosticLaunchOwnershipWindow ->
                        GateConstants.P2_ORDINARY_DIAGNOSTIC_LAUNCH_OWNERSHIP_DEPENDENCIES
                    ordinaryDiagnosticReplayBoundariesWindow ->
                        GateConstants.P2_ORDINARY_DIAGNOSTIC_REPLAY_BOUNDARIES_DEPENDENCIES
                    ordinaryDiagnosticRealRebuildWindow ->
                        GateConstants.P2_ORDINARY_DIAGNOSTIC_REAL_REBUILD_DEPENDENCIES
                    ordinaryDiagnosticBuildLeaderIdentityWindow ->
                        GateConstants.P2_ORDINARY_DIAGNOSTIC_BUILD_LEADER_IDENTITY_DEPENDENCIES
                    ordinaryDiagnosticBuildNormalExitWindow ->
                        GateConstants.P2_ORDINARY_DIAGNOSTIC_BUILD_NORMAL_EXIT_DEPENDENCIES
                    ordinaryDiagnosticBuildLifecycleWindow ->
                        GateConstants.P2_ORDINARY_DIAGNOSTIC_BUILD_LIFECYCLE_DEPENDENCIES
                    ordinaryDiagnosticBuildPidWindow ->
                        GateConstants.P2_ORDINARY_DIAGNOSTIC_BUILD_PID_DEPENDENCIES
                    ordinaryDiagnosticBuildCleanupWindow ->
                        GateConstants.P2_ORDINARY_DIAGNOSTIC_BUILD_CLEANUP_DEPENDENCIES
                    ordinaryDiagnosticRemedyWindow ->
                        GateConstants.P2_ORDINARY_DIAGNOSTIC_REMEDY_DEPENDENCIES
                    ordinaryDiagnosticChildFirstWindow ->
                        GateConstants.P2_ORDINARY_DIAGNOSTIC_CHILD_FIRST_DEPENDENCIES
                    ordinaryDiagnosticSnapshotWindow ->
                        GateConstants.P2_ORDINARY_DIAGNOSTIC_SNAPSHOT_DEPENDENCIES
                    ordinaryDiagnosticCleanupDetailWindow ->
                        GateConstants.P2_ORDINARY_DIAGNOSTIC_CLEANUP_DETAIL_DEPENDENCIES
                    ordinaryDiagnosticLineageRemedyWindow ->
                        GateConstants.P2_ORDINARY_DIAGNOSTIC_LINEAGE_REMEDY_DEPENDENCIES
                    ordinaryDiagnosticTraceOriginWindow ->
                        GateConstants.P2_ORDINARY_DIAGNOSTIC_TRACE_ORIGIN_DEPENDENCIES
                    ordinaryDiagnosticOwnedProcessWindow ->
                        GateConstants.P2_ORDINARY_DIAGNOSTIC_OWNED_PROCESS_DEPENDENCIES
                    ordinaryDiagnosticPortableStageWindow ->
                        GateConstants.P2_ORDINARY_DIAGNOSTIC_PORTABLE_STAGE_DEPENDENCIES
                    ordinaryDiagnosticSampleFixedWindow ->
                        GateConstants.P2_ORDINARY_DIAGNOSTIC_SAMPLE_FIXED_DEPENDENCIES
                    ordinaryDiagnosticSampleWindow ->
                        GateConstants.P2_ORDINARY_DIAGNOSTIC_SAMPLE_DEPENDENCIES
                    ordinaryDiagnosticJarWindow ->
                        GateConstants.P2_ORDINARY_DIAGNOSTIC_JAR_DEPENDENCIES
                    ordinaryDiagnosticWindow ->
                        GateConstants.P2_ORDINARY_DIAGNOSTIC_DEPENDENCIES
                    observerEnvReplayWindow -> GateConstants.P2_OBSERVER_ENV_REPLAY_DEPENDENCIES
                    jdiReplayCostWindow -> GateConstants.P2_JDI_REPLAY_COST_DEPENDENCIES
                    replayCostWindow -> GateConstants.P2_REPLAY_COST_DEPENDENCIES
                    archivePrivacyWindow -> GateConstants.P2_ARCHIVE_PRIVACY_DEPENDENCIES
                    workerPidWindow -> GateConstants.P2_WORKER_PID_DEPENDENCIES
                    nativeUdpWindow -> GateConstants.P2_NATIVE_UDP_GRAMMAR_DEPENDENCIES
                    observerBoundsWindow -> GateConstants.P2_OBSERVER_BOUNDS_DEPENDENCIES
                    baselineCompatWindow -> GateConstants.P2_BASELINE_COMPAT_DEPENDENCIES
                    privateLaunchWindow -> GateConstants.P2_PRIVATE_LAUNCH_DEPENDENCIES
                    v6Window -> GateConstants.P2_V6_DEPENDENCIES
                    window(GateConstants.PROSPECTIVE_EXECUTABLE_CHECKER_REVISION) ->
                        GateConstants.P2_EXECUTABLE_LOCAL_DEPENDENCIES
                    else -> GateConstants.P2_JDK21_JDI_DEPENDENCIES
                }
                IndependentGates.sourceBinding(
                    repository, candidateSha, dependencies, "JDK 21 JDI producer",
                    cloneDependencies, gate,
                )
            }
            correctedJdi -> IndependentGates.sourceBinding(
                repository, candidateSha, GateConstants.P2_CORRECTED_JDI_DEPENDENCIES,
                "corrected JDI producer",
                GateConstants.P2_ORDINARY_DIAGNOSTIC_CHILD_FIRST_DEPENDENCIES, gate,
            )
            boundedJdi -> IndependentGates.sourceBinding(
                repository, candidateSha, GateConstants.P2_BOUNDED_JDI_DEPENDENCIES,
                "bounded JDI producer",
                GateConstants.P2_ORDINARY_DIAGNOSTIC_CHILD_FIRST_DEPENDENCIES, gate,
            )
            rotationPremise -> IndependentGates.sourceBinding(
                repository, candidateSha, GateConstants.P2_ROTATION_PREMISE_DEPENDENCIES,
                "rotation premise producer",
                GateConstants.P2_ORDINARY_DIAGNOSTIC_CHILD_FIRST_DEPENDENCIES, gate,
            )
            booleanJdiFinal -> IndependentGates.sourceBinding(
                repository, candidateSha, GateConstants.P2_BOOLEAN_JDI_FINAL_DEPENDENCIES,
                "Boolean JDI final producer",
                GateConstants.P2_ORDINARY_DIAGNOSTIC_CHILD_FIRST_DEPENDENCIES, gate,
            )
            booleanJdi -> IndependentGates.sourceBinding(
                repository, candidateSha, GateConstants.P2_BOOLEAN_JDI_DEPENDENCIES,
                "Boolean JDI producer",
                GateConstants.P2_ORDINARY_DIAGNOSTIC_CHILD_FIRST_DEPENDENCIES, gate,
            )
        }
        if (!v6Window) {
            val portableStage = GateConstants.P2_ORDINARY_DIAGNOSTIC_PORTABLE_STAGE_DEPENDENCIES
            for (relative in
                GateConstants.P2_BASELINE_COMPAT_DEPENDENCIES.keys -
                GateConstants.P2_EXECUTABLE_LOCAL_DEPENDENCIES.keys
            ) {
                val actual = gate.localBlob(relative, PRODUCER_BLOB)
                if (actual != portableStage[relative]) {
                    throw IllegalArgumentException("$PRODUCER_BLOB: $relative")
                }
            }
        }
        return LinkedHashMap(approved)
    }

    /** `_approved_rotation_oracle`: the recorded digest of the approved rotation oracle. */
    fun approvedRotationOracle(repository: Path): String {
        val raw = GateGit.show(
            repository, GateConstants.ROTATION_ORACLE_REVISION, GateConstants.ROTATION_ORACLE_PATH,
        )
        if (CorpusFiles.digest(raw) != GateConstants.ROTATION_ORACLE_SHA256) {
            throw IllegalArgumentException("approved arithmetic oracle blob differs")
        }
        return GateConstants.ROTATION_ORACLE_SHA256
    }

    /**
     * `_rotation_oracle_module`: the approved rotation oracle of one candidate repository.
     *
     * The reference loads `rotation_oracle.py` and calls its `verify_rotation_arithmetic`. This
     * port proves the recorded blob is the approved one and then delegates to
     * [io.github.rubixhacker.harness.numerical.RotationOracle], which does not carry the MPFR
     * trigonometric enclosures: [verifyRotationArithmetic] therefore throws
     * [io.github.rubixhacker.harness.numerical.MpfrNotPorted] rather than reporting a verdict the
     * port cannot compute.
     */
    fun rotationOracleModule(repository: Path): RotationOracleModule {
        approvedRotationOracle(repository)
        return RotationOracleModule(GateGit.sourceRoot().resolve(GateConstants.ROTATION_ORACLE_PATH))
    }

    /** The approved rotation oracle, bound to the local blob it must agree with. */
    class RotationOracleModule internal constructor(private val blob: Path) {
        /** `rotation_oracle.verify_rotation_arithmetic`. */
        fun verifyRotationArithmetic(
            audit: JsonElement?,
            case: JsonObject,
            header: JsonObject,
            states: Map<Long, JsonElement>,
            rotationCap: JsonElement?,
            binding: JsonElement?,
            traceBytes: ByteArray,
            payloadBytes: ByteArray,
            receiptBytes: ByteArray,
            artifactBytes: ByteArray,
            sourceBytes: ByteArray,
        ): JsonObject {
            check(Files.isRegularFile(blob)) { "approved arithmetic oracle blob differs" }
            throw io.github.rubixhacker.harness.numerical.MpfrNotPorted(
                "rotation_oracle.verify_rotation_arithmetic",
            )
        }
    }

    /**
     * `_replay_target_arithmetic`: replay one raw target payload through the approved oracle.
     *
     * Every binding this verifier owns is checked here. The case replay itself belongs to the
     * oracle, whose certified trig intervals are not ported, so the terminal call throws
     * `MpfrNotPorted` instead of reporting an unverified pass.
     */
    fun replayTargetArithmetic(
        root: Path,
        oracle: JsonElement?,
        identity: JsonObject,
        repository: Path,
        payload: JsonElement,
        payloadBytes: ByteArray,
        candidateTrace: Path?,
        catalog: JsonObject?,
    ): String {
        val required = setOf(
            "binding", "binding_sha256", "receipt", "receipt_sha256",
            "target_source", "target_source_sha256", "target_source_git_path",
            "artifact", "artifact_sha256",
        )
        val value = oracle as? JsonObject
        if (value == null || value.keys != required) {
            throw IllegalArgumentException("prospective arithmetic oracle raw contract is incomplete")
        }
        val raw = LinkedHashMap<String, ByteArray>()
        for (name in listOf("binding", "receipt", "target_source", "artifact")) {
            raw[name] = Files.readAllBytes(
                IndependentGates.filePath(root, Py.str(value[name])),
            )
            if (CorpusFiles.digest(raw.getValue(name)) != Py.str(value["${name}_sha256"])) {
                throw IllegalArgumentException("prospective arithmetic oracle $name differs")
            }
        }
        if (Py.str(value["artifact_sha256"]) != Py.str(identity["artifact_sha256"])) {
            throw IllegalArgumentException(
                "prospective arithmetic oracle artifact differs from independent audit",
            )
        }
        val gitPath = Py.str(value["target_source_git_path"])
        IndependentGates.filePathName(gitPath)
        val committedSource = GateGit.show(repository, Py.str(identity["candidate_commit"])!!, gitPath!!)
        if (!committedSource.contentEquals(raw.getValue("target_source"))) {
            throw IllegalArgumentException(
                "prospective arithmetic target source differs from candidate Git",
            )
        }
        if (candidateTrace == null || catalog == null) {
            throw IllegalArgumentException(
                "prospective arithmetic oracle lacks bound candidate trace or policy",
            )
        }
        val records = TraceFiles.recordsOf(candidateTrace).map { it.row }
        if (records.isEmpty() || Py.str(records.first()["kind"]) != "inputs") {
            throw IllegalArgumentException("prospective arithmetic trace header is absent")
        }
        val states = LinkedHashMap<Long, JsonElement>()
        for (row in records) {
            if (Py.str(row["kind"]) == "state") {
                val step = row["step"]
                if (Py.isInt(step)) states[Py.int(step)] = row.getValue("state")
            }
        }
        val caseId = Py.str(identity["case_id"])!!
        val steps = ((catalog["cases"] as JsonObject)[caseId] as JsonObject)["steps"]
        val rotationCap = (catalog["rotation_caps"] as JsonObject)[caseId]
        val reviewed = rotationOracleModule(repository).verifyRotationArithmetic(
            audit = null,
            case = buildJsonObject {
                put("id", JsonPrimitive(caseId))
                put("steps", steps ?: JsonNull)
            },
            header = records.first(),
            states = states,
            rotationCap = rotationCap,
            binding = StrictObjectJson.parse(
                raw.getValue("binding").toString(StandardCharsets.UTF_8),
            ),
            traceBytes = Files.readAllBytes(candidateTrace),
            payloadBytes = payloadBytes,
            receiptBytes = raw.getValue("receipt"),
            artifactBytes = raw.getValue("artifact"),
            sourceBytes = raw.getValue("target_source"),
        )
        val status = Py.str(reviewed["status"]) ?: ""
        if (status.startsWith("FAILED")) {
            throw IllegalArgumentException(
                "prospective arithmetic oracle rejected raw operations: " +
                    (Py.str(reviewed["reason"]) ?: status),
            )
        }
        return if (status == "PASSED_ARITHMETIC" &&
            Py.str(reviewed["qualification"]) == "PASSED"
        ) {
            "PASSED"
        } else {
            "NOT_RUN"
        }
    }

    /** `_target_arithmetic_evidence`: one case's target-arithmetic producer manifest. */
    fun targetArithmeticEvidence(
        root: Path,
        audit: JsonElement?,
        identity: JsonObject,
        repository: Path,
        candidateTrace: Path? = null,
        catalog: JsonObject? = null,
    ): String {
        val required = identity.keys + setOf(
            "schema", "oracle_revision", "oracle_sha256",
            "target_payload", "target_payload_sha256",
            "process_receipt", "process_receipt_sha256",
        )
        val value = audit as? JsonObject
        if (value == null || (value.keys != required && value.keys != required + "oracle") ||
            Py.str(value["schema"]) != "target-arithmetic-evidence/1" ||
            identity.any { (key, item) -> value[key] != item }
        ) {
            throw IllegalArgumentException(
                "prospective arithmetic producer manifest is incomplete or misbound",
            )
        }
        if (Py.str(value["oracle_revision"]) != GateConstants.ROTATION_ORACLE_REVISION ||
            Py.str(value["oracle_sha256"]) != approvedRotationOracle(repository)
        ) {
            throw IllegalArgumentException("approved arithmetic oracle identity differs")
        }
        for (key in listOf("target_payload", "process_receipt")) {
            val path = IndependentGates.filePath(root, Py.str(value[key]))
            if (CorpusFiles.digest(Files.readAllBytes(path)) != Py.str(value["${key}_sha256"])) {
                throw IllegalArgumentException("prospective arithmetic raw $key differs")
            }
        }
        val payloadPath = IndependentGates.filePath(root, Py.str(value["target_payload"]))
        val payload = IndependentGates.json(payloadPath)
        val process = IndependentGates.json(
            IndependentGates.filePath(root, Py.str(value["process_receipt"])),
        ) as? JsonObject
        val payloadObject = payload as? JsonObject
        val operations = payloadObject?.get("operations")
        if (payloadObject == null ||
            Py.str(payloadObject["case_id"]) != Py.str(identity["case_id"]) ||
            !((Py.str(payloadObject["runtime"]).let { it != null && it.isNotEmpty() } &&
                operations is JsonArray && operations.isNotEmpty()) ||
                (Py.str(payloadObject["schema"]) == "portable-rotation-audit/1" &&
                    payloadObject["calls"] is JsonArray))
        ) {
            throw IllegalArgumentException("prospective arithmetic target payload is incomplete")
        }
        val command = process?.get("command")
        val launched = (command as? JsonArray)?.mapNotNull { Py.str(it) }
        if (process == null ||
            process.keys != setOf(
                "command", "exit_code", "started_ns", "finished_ns", "stdout", "stdout_sha256",
            ) ||
            launched == null || launched.isEmpty() ||
            launched.any { it.isEmpty() } ||
            Path.of(launched.first()).fileName.toString().lowercase() !in setOf(
                "java", "node", "wasmtime", "adb", "xcrun", "gradlew", "gradle",
            ) ||
            !Py.isInt(process["exit_code"]) || !Py.equalsInt(process["exit_code"], 0) ||
            !Py.isInt(process["started_ns"]) || !Py.isInt(process["finished_ns"]) ||
            Py.int(process["started_ns"]) <= 0 ||
            Py.int(process["finished_ns"]) < Py.int(process["started_ns"])
        ) {
            throw IllegalArgumentException("prospective arithmetic target process is incomplete")
        }
        val stdout = Files.readAllBytes(
            IndependentGates.filePath(root, Py.str(process["stdout"])),
        )
        if (CorpusFiles.digest(stdout) != Py.str(process["stdout_sha256"]) ||
            "ARITHMETIC_CASE=${Py.str(identity["case_id"])}" !in
            stdout.toString(StandardCharsets.UTF_8).lines()
        ) {
            throw IllegalArgumentException("prospective arithmetic target output differs")
        }
        if ("oracle" in value) {
            return replayTargetArithmetic(
                root, value["oracle"], identity, repository, payload,
                Files.readAllBytes(payloadPath), candidateTrace, catalog,
            )
        }
        return "NOT_RUN"
    }
}
