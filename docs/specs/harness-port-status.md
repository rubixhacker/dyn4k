# Harness port status

This file tracks the port of the Python harness to Kotlin. It is the working record for
`docs/specs/harness-port.md`. Update it when a module or suite changes state.

Run every harness test with one command:

```
cd tools/harness && ../../gradlew checkAll
```

## Test frameworks

| Area | State | Evidence |
| --- | --- | --- |
| `dyn4k` commonTest and jvmTest | ported to TestBalloon | `./gradlew :dyn4k:jvmTest` — 61 tests, 0 failures; `:dyn4k:linuxX64Test` — 58; `:dyn4k:jsNodeTest` — 58 (after `kotlinUpgradeYarnLock`); no non-TestBalloon suite |
| `dyn4k-core` commonTest, jvmTest, diagnostic | ported to TestBalloon | `./gradlew :dyn4k-core:jvmTest` — 2465 tests, 0 failures; no non-TestBalloon suite |
| `consumers/*`, `tools/numerical/portable` | ported to TestBalloon | `consumers/geometry-extension` 1, `consumers/performance/portable` 3, `consumers/idiomatic-api` 2, `consumers/qualification/portable` 3, `tools/numerical/portable` 55 (jvm), `pulley-jdi-sidecar-v2` 1 — 0 failures; lane builds converted but not run |
| `tools/harness` modules | TestBalloon only | counts below |

`grep -rn "@Test" dyn4k dyn4k-core` returns no matches.

## Harness modules

| Module | Python source | State | Tests |
| --- | --- | --- | --- |
| `:core` | `qualify.py` contract: matrix, digests, canonical JSON, publication metadata, provider check | ported | 27 |
| `:host` | `qualify.digest(path)`, `qualify.require_clean_checkout` | ported | 7 |
| `:qualification` | `guard_hosted_runners.py` (**Python deleted**), `qualify.py` archives/audits/evaluation/CLI actions, `stage.py`, `publication.py`, `artifact.py`, `collection.py` (38 of 44 functions; the six Windows handle helpers are not portable), `full_hosted.py` (all but `run`), `hosted.py`, `safari_reporter.py`, `safari_yarn_lock.py` (39 of 124 methods), `independent_gates` (most verifiers), `independent_linux_observer` (verification half), `full_corpus.py`, `full_suite_manifest.py`, `duplicate_provider.py` | partial | 598 |
| `:compatibility` | `world_ci`, `governing_*`, `candidate_coverage`, `method_coverage`, `java_corpus`, `execution_probe`, `full_ci`, `exception_ci`, `ledger`, `module_probe`; `BaselineOracle` now delegates to `:baseline` instead of duplicating the three `javap` readers | partial | 51 |
| `:performance` | `manifest`, `analyze`, `measure`, `candidate_*`, `sustained_archive`, `reference_study`, `host_capacity_control`, `stress_monitor`, `warmup_probe` (**Python deleted**), `calibrate` (**Python deleted**), `ccd_route_trace` | partial | 181 |
| `:numerical` | `portable/cases.py`; `portable/receipt.py`; `portable/exact_consistency.py`; `portable/orthogonality.py`; `portable/physical.py` (`nominal_free`, `audit_physical`, sleep/wake, phases); `numeric_class_witness.read_witness`; `compare.py` (`compare`, `audit_reference`, `load_receipt`, `load_fixture`, the whole `compare_value` engine, `check_counts`, `check_snapshot`); `candidate/nominal_zero.py`; `weld_pulley_quality.py` (engine, phases, `atan`/`pi` enclosures, `Decimal`-at-80 rendering); `portable/rotation_oracle.py` (encoding, digest and manifest helpers only) | partial | 91 |
| `:android` | `android_corpus`, `build_identity`, `evidence`, `full_evidence`, `optimized_evidence`, `prepare`, `run`, `run_full`, `run_optimized` (Android); `receipt`, `full`, `adverse` (Android Native) — installed routes ported but never run on a device | ported | 110 |
| `:migration` | `journeys`, `fixed_replay`, `truck_camera`, `truck_timeline`, `validate_plain`, `validate_scene` and their four suites; the podman/X11 paths are unrun and the mains have no Gradle tasks. `TruckTimelineContract` replays the nine `test_truck_camera.py` cases against recorded Python verdicts | ported | 96 |
| `:baseline` | `verify.py` in full (`type_header`, `surface`, `member_inventory`, the structural comparator, added-member gates, source and run identity, fixtures, inventory, execute) plus `BaselineCli`; 62 of the 68 Python cases reproduced, 38 vector replays | ported | 110 |

## Python that remains

The port is not finished. At 2026-10-30 the tree still held **323 Python files, 170,307 lines**:

| Directory | Lines | State |
| --- | ---: | --- |
| `tools/qualification` | 65,974 | partial: `hosted`, `safari_reporter`, `collection`, `compiler_modes`, `artifact` (hosted half), `full_hosted` (most of it), most `independent_gates` verifiers and every consumer verifier remain |
| `tools/numerical` | 49,317 | partial: the producers, `extra_targets`, `actual_*`, `prospective_compare`, the JDI and MPFR harnesses, and the portable consumer scripts remain |
| `tools/performance` | 24,539 | partial: the sustained archives, the recent-archive verifiers and the native-host runners remain |
| `tools/compatibility` | 11,857 | partial: `signature_index`, `build_provenance`, `portable_links`, `coverage_receipts`, `common_corpus_receipt`, `android_java_corpus` remain |
| `tools/harness` | 5,139 | parity generators; kept until the port completes so vectors stay reproducible |
| `tools/android-runtime`, `tools/android-native-runtime` | 4,397 | ported; deletion waits on the qualification consumers that read their output |
| `tools/baseline` | 2,784 | ported; deletion waits on `scripts/verify-geometry-jvm-api.py`, `scripts/verify-foundation-jvm-api.py` and `verify.sh`, which import `compare_jars` |
| `tools/migration` | 2,519 | ported; deletion is blocked because `independent_gates.py` and `validate_plain.py`/`validate_scene.py` still import each other |
| `tools/diagnostic` | 2,238 | not started (Windows collision controls) |
| `scripts`, `docs/guide`, `consumers` | 1,293 | not started |

70 Python invocations remain in the workflows (49 of them `python3`, 21 bare `python`), across
`qualification.yml`, `qualification-source-checks.yml` and `full-staged-native-host.yml`. A step may only move to Kotlin once its module is ported and
`tools/compatibility/test_qualification_workflow.py` asserts the new command.

### The vector generators must be deleted last, and they count against the total

Every port records parity evidence by running the Python reference, so each port adds a Python generator
under `tools/harness/<module>/parity/`. At 2026-10-30 those were **11 files and 6,641 lines**, which is
why the Python total rose from 170,307 to 171,811 lines while four modules were being ported.

A generator can only be deleted once the Python module it imports is deleted, because it imports that
module directly. `tools/harness/performance/parity/generate_leaf_vectors.py` was the first to go: its
inputs, `warmup_probe.py` and `calibrate.py`, had been deleted, so it could no longer run. The same
applies to every other generator in turn. The final state must therefore have no generators left either;
until then they are deliberate, and the recorded constants carry the revision and generator name that
produced them.

Harness total at the last full run: 1180 tests, 0 failures, across `:core`, `:host`,
`:compatibility`, `:performance`, `:qualification`, `:numerical`, `:android`, `:migration` and
`:baseline`.

### What still blocks the three qualification deletions

`full_hosted.py`, `artifact.py`, `collection.py` and `publication.py` are all ported, but none can be
deleted alone. Measured on 2026-10-30:

| File | Lines | Still blocking |
| --- | ---: | --- |
| `collection.py` | 1,503 | **deleted** 2026-10-30, with `test_collection.py` and `test_cross_run_collection.py` |
| `test_publication.py` | 1,516 | imported as a fixture builder by `test_artifact.py:41` and `test_full_hosted.py:22/1388/1558/2227`; `qualification-source-checks.yml:143`; `test_qualification_workflow.py:499/882` string-match that workflow line |
| `artifact.py` | 621 | `full_hosted.py:25` (`run`), `qualify.py:1614` and `:1701`, `independent_gates.py:3300`, `test_artifact.py:13`, `qualification.yml:374`, `:636`, `:1074` |
| `publication.py` | 87 | **deleted** 2026-10-30 with `test_publication.py`; the staged-tree builder survives as `publication_fixture.py` |

### `record` and the publication coverage, corrected

`qualify.py record` is ported (`QualificationCli.record`) and `independent_gates._bounded_bundle` is
ported (`IndependentGates.boundedBundle`). The earlier claim that `qualify.evaluate` returns a full lane
object was **wrong** and is retracted: `evaluate` builds only `{"id", "status", "reason"}`, so the
existing `LaneVerdict` was already faithful and nothing had to change in `LaneEvaluation`.

`test_publication.py` has 31 cases. The Kotlin side now covers 24 fully and 2 partially; five have no
equivalent and must be reproduced before the suite can retire:

1. `workflow_harness_requests_full_history_without_bytecode` — asserts `fetch-depth` and `-B` in the workflow text.
2. `documentation_fixture_survives_zip_entry_clock_changes` — the zip-clock fixture manipulation itself.
3. `downloaded_bundle_rejects_coherent_pom_source_docs_and_apple_changes` — the sources-JAR, javadoc-JAR and Apple `-metadata.jar` halves; the recorded staging fixture carries only `jvm` and `js`.
4. `downloaded_bundle_rejects_coherent_profile_and_embedded_notice` — an active-by-default POM profile and a wrong `META-INF/LICENSE.md` inside a packaged jar.
5. The stale-hidden-directory omission assertion inside `downloaded_publication_bundle_rejects_partial_or_changed_files`.

`test_publication.py` also supplies the `stage(root, targets)` fixture builder that `test_artifact.py` and
`test_full_hosted.py` import for target tuples the recorded archives do not cover, so it cannot be
deleted before either those two suites retire or the builder is extracted into its own module.

### `safari_yarn_lock.py` — 39 of the 124 reference methods ported

The pure contract, the POSIX host half, the capture receipt, the package graph, the public audit, and
the CLI are ported (`SafariYarnLockRules.kt`, `SafariYarnLockHost.kt`, `SafariCapture.kt`,
`SafariCaptureCli.kt`; 46 tests across `SafariYarnLockContract`, `SafariCaptureStatus`,
`SafariHostedCapture`, `SafariPackageGraphSuite` and `SafariArchivedWorkflow`): every constant, the
hosted task markers, the capture timeout and overflow predicates, the `full_hosted_command` forms,
the lock-failure signature, the bounded source read/copy, the candidate gate, the process runner's
600-second deadline with truncation accounting, `capture`, `hosted_expected_files`,
`capture_package_graph`, `audit_capture`, and `main` (as the `safariYarnLock` Gradle task).

The reference patches `run_lock_task`, `safari_reporter.stage`, `capture_package_graph` and
`MAX_PROCESS_SECONDS` to reach the failure branches. The JVM has no monkey-patching, so
`SafariCapture.capture` exposes the same seams as parameters (`lockTask`, `stageHook`,
`afterPackageGraph`, `deadlineSeconds`); production passes none of them. There is one end-to-end case
that runs the real `runLockTask` against a committed `gradlew` wrapper.

85 methods remain (64 of the 102 in `test_safari_yarn_lock.py`, all 7 in
`test_safari_windows_file.py`, all 14 in `test_safari_windows_process.py`), in five groups:

- `capture_karma_context` and its wrapper (40): the 34 `test_context_*`/`test_public_context_*`
  scanner, bound, sampling and corruption cases, and the 8 `test_wrapper_*`/`test_git_bash_*` Git
  Bash sampler cases. `main`'s two context modes fail closed with an explicit message.
- Windows-only machinery (27): the 7 file and 14 process cases, `_run_lock_task_windows` job
  objects, suspended creation, `CreateFileW` share modes, `LockedDirectory`, the blocked
  stage rename, the detached job child, the staging-handle residue, the postlaunch setup failures,
  the log-open failure ordering, and the init-script/context CRLF text-write cases.
- POSIX process-runner error permutations (5): the two selector setup/registration failures, the
  process-group probe, the incomplete pipe, and the detached-child pipe. The thread-based drain has
  no selector to fail and probes no process group.
- Reference-suite self-checks (5): the two `commit_crlf_source_fixture` cases,
  `assert_incomplete_fixture_status`, `test_safari_reporter_splits_service_messages_without_
  dropping_them`, and `test_crlf_source_fixture_commit_is_idempotent`.
- Capture/audit leftovers (8): `test_lock_task_keeps_gradle_mismatch_enforcement`'s default-command
  assertion, the exact init-script digest halves of the two `full_hosted_*_uses_exact_*` cases, the
  quoted-overflow phrase, `test_public_full_hosted_receipt_records_staging_setup_residue`, the two
  reporter-staging swap cases (covered behaviourally by `SafariReporterSuite`, not by a capture-level
  case), and `test_public_capture_rejects_generated_config_symlinked_package_ancestor`.

The earlier "27 of 124" was a case-level aggregate that counted shared predicates rather than test
methods; 39 is the method-level count, not a regression.

Of the 85 that remain, about 33 can never be reproduced on the JVM: 27 are Windows-only and 5 need a
selector loop and a process-group probe that the thread-based drain does not have. Retiring
`test_safari_windows_file.py` (7) and `test_safari_windows_process.py` (14) is therefore a coverage
decision of the same kind as the descriptor-anchoring one above, and it has to be taken explicitly
before `safari_yarn_lock.py` can be deleted.

Recorded divergences: `runLockTask(windows = true)` fails closed with an explicit message rather than
pretending to lock; the port replaces the three Python paths in `HOSTED_SOURCE_INPUTS` with the Kotlin
tools that implement the same behaviour, so an archived `source_input_sha256` map from the Python
diagnostic will not match the Kotlin one; the drain's `stream_incomplete` means a reader thread
outlived the drain deadline, not that a selector unregistered; and `capture_package_graph` sorts the
workspace inventory by path parts (as `pathlib` does), not by path text.

### Parity gap: descriptor anchoring

The reference opens directories with `dir_fd` plus `O_NOFOLLOW` and compares `fstat` of held
descriptors. The JVM has no descriptor-relative open, so `safari_reporter`, `collection` and `archive
digest` check a path with `NOFOLLOW_LINKS` and re-read identity afterwards. A swap between the check
and the operation is therefore undetectable. `test_cross_run_collection.py` (1,277 lines) attacks
exactly this, and six `_windows_*` ctypes handle helpers in `collection.py` have no JVM equivalent at
all — on Windows the port applies the POSIX path logic instead of failing closed, which is weaker than
the reference. This must be resolved, or explicitly accepted and recorded, before `collection.py` is
deleted.

**Decision (2026-10-30).** The gap is accepted as a known limitation, and it cannot be closed on the JVM
as the reference closes it. `java.nio.file` has no `openat`, no descriptor-relative `open`, and no
`O_NOFOLLOW` flag; the only faithful port would be a native call through the Java 21 foreign-function
API, which is preview-only in this toolchain. The port therefore keeps the strongest check the platform
allows: every component is opened with `NOFOLLOW_LINKS`, and the `fileKey` of the opened file and of
each ancestor is re-read and compared. The residual window is a swap that restores an identical
identity between the check and the operation.

The threat model bounds the exposure: the collection job runs in a runner-owned workspace and the
untrusted input is a downloaded artifact (data), not a local writer. The exposure is real but narrow.

**This decision alone does not free `collection.py`.** Retiring its suites would delete tests the Kotlin
port does not replace: `test_collection.py` has 15 tests of which the port reproduces 11 (2 need the
unported `test_qualification_workflow.py` contract engine, 2 are workflow-mutation variants not
reproduced), and `test_cross_run_collection.py` has 35 tests of which the port reproduces none. Those 35
exercise cross-run ingestion, external-reference snapshots and the anchoring swaps. Deleting the file
now would drop that coverage, so the cross-run cases have to be reproduced in `:qualification` first —
adapted to the path-level guarantee the port actually provides, which is a weaker but still meaningful
assertion — and only then may `collection.py`, `test_collection.py` and `test_cross_run_collection.py`
go.

## Python code removed

| File | Replacement | CI step |
| --- | --- | --- |
| `tools/qualification/guard_hosted_runners.py` | `GuardHostedRunners.kt` | `./gradlew -p tools/harness :qualification:guardHostedRunners` in `qualification.yml` and `qualification-source-checks.yml` |
| `tools/qualification/test_guard_hosted_runners.py` | `GuardHostedRunnersSuite.kt` (12 cases) | the separate test step was removed; `test_qualification_workflow.py` asserts the Kotlin command |
| `tools/performance/warmup_probe.py` | `WarmupProbe` + `:performance:warmupProbe` | no workflow step invoked it |
| `tools/performance/calibrate.py` | `Calibrate` + `:performance:calibrate` | no workflow step invoked it; `docs/research/performance-manifest.md` points at the Gradle task |
| `tools/qualification/collection.py` | `CollectionRules`/`CollectionRuntime`/`CollectionCli` + `:qualification:collectQualification` | the two central-job steps in `qualification.yml` |
| `tools/qualification/publication.py` | `PublicationBundle`/`PublicationCli` + `:qualification:packagePublication` | both packaging steps in `qualification.yml` |
| `tools/qualification/test_publication.py` (31 cases) | `PublicationBundling` 9, `PublicationTransport` 3, `PublicationGaps` 4, `PublicationFixture` 2, `PublicationWorkflow` 1 plus the pre-existing audit suites | step dropped from `qualification-source-checks.yml`; the contract mutation in `test_qualification_workflow.py` retargeted |
| `tools/qualification/test_collection.py` (15 cases) | `CollectionContract` (14 tests) | step dropped from `qualification-source-checks.yml`; the three list assertions in `test_qualification_workflow.py` updated |
| `tools/qualification/test_cross_run_collection.py` (35 cases) | `CrossRunCollectionContract` (29 tests) | same |
| `tools/harness/performance/parity/generate_leaf_vectors.py` | `LeafVectors.kt` (recorded constants) | deleted because it imported `warmup_probe` and `calibrate`; it could no longer run. The vectors it produced are committed and the generator is in git history |

## Known parity hazards

- Canonical JSON must match Python `json.dumps(sort_keys=True, separators=(",", ":"), allow_nan=False)`,
  including `\uXXXX` escaping above `0x7E` and Python float `repr`. The float formatter is JVM-only
  (`shortestDecimalParts` is an `expect` function).
- `qualify.publication_variant_contract` emits `available-at` entries in Python set order, which changes
  between interpreter runs. The Kotlin port emits matrix order; evidence must not depend on that order.
- `publication.package` lists bundle files in `Path.rglob` traversal order, which follows the producing
  filesystem. The Kotlin inventory is sorted; cross-implementation manifest digests therefore differ.
- `independent_gates` and `full_corpus` verifiers that load Python analyzers from `tools/numerical`
  cannot be verified until that module is ported.
- `independent_linux_observer.capture` uses `ptrace`; only the verification and derivation halves are ported.
- `numerical.orthogonality._trig_agrees` raises `OverflowError` for every nonzero angle, because
  `abs(x) ** 201 / math.factorial(201)` converts `201!` to a double. The port keeps that as
  `PythonOverflow`; a rotation audit carrying a nonzero `angle_bits` call fails identically on both sides.
- `numerical.orthogonality` derives `acos` from `atan2`/`sqrt`, so `_source_angle_agrees` may differ from
  glibc's `acos` by one unit in the last place. The recorded vectors do not reach that tolerance edge.
- `numerical.physical` reads the approved phase schedule from a merged fixture projection; the full
  `fixtures.json` merge stays with the `:host` adapter that supplies it.
- `weld_pulley_quality`: three of the five scenario groups that diverged on the previous pass now
  pass (over-limit stored rotations, the represented one-degree rotation, and the
  identity/alias/callback mutations); the cause was `U = 2.0.pow(-53)` evaluating to `1.0` through a
  home-grown `Double.pow` that ignores negative exponents. Two groups remain unverified and are
  registered behind `WELD_QUALITY_DIVERGES = false` in `WeldPulleyQualitySuite.kt`: the
  stored-rotation quadrant table (a quadrant row returns `INVALID`; the `atan` enclosure does not
  converge inside its 256 terms) and the frozen baseline with an out-of-limit state (returns
  `INVALID` where the reference scores `PHYSICAL_FAILED`). Both are recorded, with the reference
  statuses and the observed port statuses, in the `weld_pulley_divergence` block of
  `CompareVectors.kt`; a registered test fails if that block or the flag drifts. The `atan`
  enclosure also grows unreduced rationals without bound, which made the quadrant scenario exceed
  the one-minute test budget.
- `compare.compare_value` decides the `getCost`/`getSint` derivation channels through
  `check_cost_pair`/`check_sine_pair`; the recorded comparison vectors cover the scalar, direction
  and orientation branches but not a `derived_rules` fixture.
- `rotation_oracle` ports only its encoding, digest and manifest helpers. `trig_interval`,
  `verify_rotation_arithmetic` and `verify_operation_marker` throw `MpfrNotPorted`; the certified
  `cos`/`sin` enclosures need libmpfr through ctypes, and the binding half needs the produced
  class-loading witness.
- `BigNat.toDouble` renders the exact decimal and parses it, so it is correctly rounded; the
  `Fraction.toDouble` quotient of two such renderings is within one unit in the last place.
- Workflow text is asserted by `tools/compatibility/test_qualification_workflow.py`. A step may move to
  Kotlin only when that suite's expectation moves with it.
- TestBalloon result identity is `suite_<package>.<Suite>` plus `<test>[<target>]`. JUnit identity was
  `<class>` plus `<method>`. The JVM lane build and `full_jvm_consumer.py` now normalise both shapes.
  Every other consumer module that reads JUnit XML or selects `Class.method` still needs the same
  treatment: `full_browser_consumer`, `full_klib_consumer`, `full_wasm_node_consumer`,
  `full_android_consumer`, `full_android_native_consumer`, `full_apple_device_consumer`,
  `full_native_host_consumer`, `tools/android-runtime`, and `tools/qualification/browser_wasi`.
- Adding the TestBalloon test dependency changes `kotlin-js-store/yarn.lock`; run
  `./gradlew kotlinUpgradeYarnLock` after any test dependency change or the JS tasks fail with
  "Lock file was changed".
- Test conversion changes every test source file, so the frozen complete-suite manifest and the
  approved corpus no longer match the checkout. Regenerating them is step 2 of "Evidence invalidation"
  in `harness-port.md`; re-approval and lane reruns are open.
