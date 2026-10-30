# What the prospective-gate port covers

This file covers the prospective slice of `tools/qualification/independent_gates.py`: the approved
checker and producer closures, the rotation-arithmetic audit of one raw target payload, and the
concurrent-writer hardening of `archive_digest`. The Python file is unchanged and remains the
reference.

The approved blob tables are generated, not hand-copied:

```
python3 tools/harness/qualification/parity/dump_gate_constants.py \
  > tools/harness/qualification/src/jvmMain/kotlin/io/github/rubixhacker/harness/qualification/GateConstants.kt
```

The generated header names the revision the tables were read from
(`d0053c0b4486e26c4d24642b8e0d837b033fee31` at the time of writing). Rerun the generator after any
change to the reference tables; do not edit `GateConstants.kt` by hand.

## Ported

| Python | Kotlin |
| --- | --- |
| `_prospective_checker_binding` | `GatesProspective.checkerBinding` |
| `_p2_producer_binding` | `GatesProspective.p2ProducerBinding` |
| `_approved_rotation_oracle` | `GatesProspective.approvedRotationOracle` |
| `_rotation_oracle_module` | `GatesProspective.rotationOracleModule` |
| `_replay_target_arithmetic` | `GatesProspective.replayTargetArithmetic` |
| `_target_arithmetic_evidence` | `GatesProspective.targetArithmeticEvidence` |
| `_source_binding` (local and committed halves behind a seam) | `IndependentGates.sourceBinding` |
| `_archive_identity` | `ArchiveScan.identity` |
| `_archive_stable_identity` | `ArchiveIdentity.stable` |
| `_archive_ancestor_identity` | `ArchiveIdentity.ancestor` |
| `_archive_handle_identity` | `ArchiveIdentity.handle` |
| `_archive_ancestor_handle_identity` | `ArchiveIdentity.ancestorHandle` |
| `_archive_directory` | `ArchiveScan.archiveDirectory` |
| `_file_path_name` | `IndependentGates.filePathName`, `ArchiveScan.filePathName` |

Reused instead of re-ported: `approved_prospective_catalog`, `approved_prospective_cases`,
`_prospective_policy_version`, `verified_numerical_source_sha256`, `_proven_ancestor`,
`archive_digest`'s digest shape, `_prospective_case_status`, `_p2_scope`, `_p2_runtime_identity`,
`_p2_directory`, `_p2_summary`, `_missing_numerical_subgates`, and the strict JSON reader.

## Not ported

| Python | Why |
| --- | --- |
| `_verify_p2_host` | calls `prospective_compare.compare_host`, which has no Kotlin port |
| `verify_pending_prospective_bridge` | reaches `_verify_p2_host` whenever a P2 scope is supplied |
| `verify_prospective_case_subgates` | calls `prospective_compare.verify_reference_inventory` and `compare_policy_case` per case |
| `_numerical_entries` | loads `compare.py` and `physical.py` through `_numerical_modules` |
| `_migration_journeys`, `_independent_review`, `_performance_resource`, `_bounded_bundle` | next slice |
| `_java_full_ci`, `_evaluate_signed_full_consumer`, `_browser_consumption_witness` | next slice |
| `evaluate_gate`, `evaluate_assembly` | dispatch to every verifier above, so they arrive with the last one |

The bridge verifier's transport half (the 15 method receipts, the inventory identity, the case and
method order) is portable and is the part the recorded cases assert, but it is not written yet: it
cannot be exercised end to end while `_verify_p2_host` is missing, and a verifier that reports
`NOT_RUN` for one branch and throws for the other would be misleading.

## Known divergences

- `_rotation_oracle_module` execs `portable/rotation_oracle.py` and calls
  `verify_rotation_arithmetic`. The port proves the recorded oracle blob is the approved one and
  then throws `MpfrNotPorted`: the certified `cos`/`sin` enclosures need the ctypes binding to
  libmpfr, which `:numerical` does not carry. `replayTargetArithmetic` performs every binding
  check it owns before that call, so only the case replay itself is unavailable.
- `_archive_directory` opens each path component with `dir_fd` and `O_NOFOLLOW` and compares the
  opened handle. `java.nio.file` has no directory descriptor, so the port validates the same
  identity projections by reading each component's attributes and re-checks the directory when it
  re-lists it. A swap that restores an identical identity between those reads is not detected,
  which is narrower than the reference.
- `_archive_identity` rejects symbolic links and, on Windows, junctions and reparse points. The
  port rejects symbolic links; a junction is not distinguished (the JVM exposes no such status,
  and the port targets POSIX). Any other non-regular, non-directory entry is rejected as
  `nonregular archive path`, as the reference does.
- `_source_binding` surfaces a missing committed blob as `GitObjectMissing`; the reference lets
  `subprocess.CalledProcessError` escape the same way.

## Recorded-case state at this revision

The reference cases assume the checkout holds the pinned bytes of every local dependency. On
`kotlin-testballoon-migration` it does not: commit `2fd9a350` converted four
`tools/numerical/portable` test sources and that module's build file to TestBalloon without
re-recording the capture pins, so `_prospective_checker_binding` and `_p2_producer_binding` now
reject even the current checkout, in Python as well as here. The suites in
`GatesProspectiveSuite.kt` restore the reference's premise by reading the recorded bytes from the
commit that recorded them (`pinnedCheckout`), assert the window selection against them, and assert
the reference's rejecting branch against the unmodified checkout (`assertRejectsAtHead`).

Thirteen of the sixty-seven reference cases that call `_prospective_checker_binding` or
`_p2_producer_binding` are reproduced (`GatesProspectiveContract`, 14 tests): the executable
window, the replay-scratch window, the v6 window, the historical/assembled/bridge windows, the
represented revision, the numeric-probe window, the inventory fix, the prospective catalog, the
reviewed P2 blob pins, the two executable drift cases, the build cleanup/pid/lifecycle windows, and
the target-arithmetic manifest. The remaining fifty-four are window cases of the same shape; the
machinery they need ([GateSource], `pinnedCheckout`, `DriftSource`) is in place.

Capture-dependency tables that disagree between windows for one path — `P2_BASELINE_COMPAT_DEPENDENCIES`,
`P2_PRIVATE_LAUNCH_DEPENDENCIES` and `P2_V6_DEPENDENCIES` pin
`FocusedBooleanArithmeticSourceTest.kt` to `fb321e77` while every other window pins `b8eb3a06` —
mean the pins must be re-recorded before the gates can pass again. That is a reference change, not
a port decision.
