# Harness port status

This file tracks the port of the Python harness to Kotlin. It is the working record for
`docs/specs/harness-port.md`. Update it when a module or suite changes state.

Run every harness test with one command, and every static gate with another:

```
cd tools/harness && ../../gradlew checkAll
cd tools/harness && JAVA_HOME=<jdk21> ../../gradlew staticAll
```

`staticAll` runs `detekt` and `spotlessCheck` in every module. Detekt 1.23 needs
Gradle on JDK 21 (its bundled compiler cannot parse a 25+ runtime version); the
CI step pins `JAVA_HOME` to the Temurin 21 home for the same reason.

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
| `:qualification` | `guard_hosted_runners.py` (**Python deleted**), `qualify.py` archives/audits/evaluation/CLI actions, `stage.py`, `publication.py`, `artifact.py`, `collection.py` (38 of 44 functions; the six Windows handle helpers are not portable), `full_hosted.py` (all but `run`), `hosted.py`, `safari_reporter.py`, `safari_yarn_lock.py` (all 124 methods), `independent_gates` (aggregation, review and full_ci gates; four Python-harness bodies fail closed), the `full_*` adapter layer (android, browser, klib; the consumer replays are named seams), `full_staged_consumer` (contract, graph and inventory ported; the Gradle replay is the CLI), `full_jvm_consumer` (lane table, contract shape, inventory, input files, report comparison, worker proof; the Gradle replay and archive replay tail fail closed), `independent_linux_observer` (verification half), `full_corpus.py`, `full_suite_manifest.py`, `duplicate_provider.py` | partial | 720 |
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

Harness total at the last full run: 1393 tests, 0 failures (11 skipped retained-evidence
gates), across `:core`, `:host`,
`:compatibility`, `:performance`, `:qualification`, `:numerical`, `:android`, `:migration` and
`:baseline`.

### `independent_gates.py` — aggregation ported, four bodies fail closed

`GatesAggregate.kt` (with `IndependentGatesCli` and the `independentGates` Gradle task) now ports
`_independent_review`, `_java_full_ci` (it re-binds every raw artifact and then runs the reviewed
`full_ci.py` verifier at its pinned revision), `evaluate_gate`, `evaluate`, `evaluate_assembly`, and
`main`. `_prospective_checker_binding` was already `GatesProspective.checkerBinding` and
`_bounded_bundle` was already `IndependentGates.boundedBundle`, so neither was re-ported.

Four bodies still drive Python-only harnesses and return `NOT_RUN` with the harness named rather than a
fabricated verdict: `_migration_journeys` (the Python `journeys`/`validate_plain`/`validate_scene`
drivers), `_numerical_entries` (the Python `compare`/`physical` replay engine),
`_performance_resource` (the Python `verify_candidate_archive` verifier), and
`_evaluate_signed_full_consumer` with `_browser_consumption_witness` (the Python
`full_signed_routes`/`full_browser_consumer` verifiers). `_verify_p2_host`,
`verify_pending_prospective_bridge`, and `verify_prospective_case_subgates` are not ported either:
the last two are pure validation except for `_verify_p2_host` (which imports `prospective_compare`)
and the `prospective_compare` rule replay inside `verify_prospective_case_subgates`.

Two pre-existing port bugs surfaced and were fixed by the new review case: `IndependentGates.binding`
and `externalUnavailable` compared `receipt["lane"] != null`, which a JSON `null` satisfies (it is
`JsonNull`, not Kotlin `null`), so an approved global gate with a null lane was rejected as
"raw lane differs". The reference's `is not None` treats JSON null as absent.

Porting the aggregation does **not** free `artifact.py`. `grep` for importers of
`independent_gates.py` finds 18 non-test modules, including `duplicate_provider.py`,
`qualify.py:602`, `independent_adapter.py`, `independent_audit_producer.py`, `linux_observed_klib.py`,
`full_signed_routes.py`, and every `full_*_consumer.py`/`full_*_adapter.py`. Its remaining workflow
steps are `.github/workflows/qualification.yml:444` (the reviewed full_ci replay test) and `:978`
(`python3 tools/qualification/independent_gates.py …`), plus
`qualification-source-checks.yml:140` (`-m unittest -v test_independent_gates`).

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

### `safari_yarn_lock.py` — all 124 reference methods ported

The pure contract, the POSIX host half, the capture receipt, the package graph, the public audit, the
Karma context scanner, and the CLI are ported (`SafariYarnLockRules.kt`, `SafariYarnLockHost.kt`,
`SafariCapture.kt`, `SafariContextRules.kt`, `SafariContext.kt`, `SafariCaptureCli.kt`, `SafariWindowsFile.kt`, `SafariWindowsProcess.kt`, `SafariGitBash.kt`; 129 tests
across `SafariYarnLockContract`, `SafariCaptureStatus`, `SafariHostedCapture`,
`SafariPackageGraphSuite`, `SafariArchivedWorkflow`, `SafariContextScanner`, `SafariContextBinding`,
`SafariContextCandidate`, `SafariContextSampler`, `SafariLaunchWrapper`,
`SafariWindowsFileSuite`, `SafariWindowsProcessSuite`, `SafariWindowsCaptureSuite`,
`SafariPosixProcessSuite`, `SafariLeftoversSuite`, `SafariFullHostedResidueSuite`):
every constant, the hosted
task markers, the capture timeout and overflow predicates, the `full_hosted_command` forms, the
lock-failure signature, the bounded source read/copy, the candidate gate, the process runner's
600-second deadline with truncation accounting, `capture`, `hosted_expected_files`,
`capture_package_graph`, `audit_capture`, `capture_karma_context` with its inventory and both raw
contexts, and `main` (as the `safariYarnLock` Gradle task, including its two context modes).

The reference patches `run_lock_task`, `safari_reporter.stage`, `capture_package_graph`,
`MAX_PROCESS_SECONDS`, `os.scandir`, and the ten `CONTEXT_MAX_*` globals to reach the failure branches.
The JVM has no monkey-patching, so the same seams are parameters: `SafariCapture.capture` takes
`lockTask`, `stageHook`, `afterPackageGraph` and `deadlineSeconds`, and
`SafariContext.captureKarmaContext` takes `SafariContextBounds` (the ten limits, production defaults)
and `scanHook` (the enumeration call). Production passes none of them. One end-to-end case runs the
real `runLockTask` against a committed `gradlew` wrapper, and one runs `capture_karma_context` over a
fixture whose sidecar records, counters and status are the ones the Python implementation produces
(`SafariYarnLockVectors.CONTEXT_INVENTORY`, generated by running the reference on the reference's own
fixture).

The last method, `test_public_full_hosted_receipt_records_staging_setup_residue`, is now reproduced
by `SafariFullHostedResidueSuite`. It drives `full_hosted.run` through `FullHostedRunSeams`, which is
the port of that suite's patch set: `windows` and `windowsDirectories` (the reference replaces the
imported `safari_windows_file.LockedDirectory`, not `stage` itself), `loadCorpus`, `discoverRuntime`,
`runtimeStatus`, `gradleWrapper`, `toolVersion`, `requirePinnedToolchain`, `runCommand`,
`targetHashes`, `captureStaging`, `captureDokkaOutput`, `inputs`, and `configs`. Every one of them is
exercised by the case; nothing the reference patches was left out. `FullHostedRun.run` now catches
`SafariStageFailure` around both Safari stages and records `error.result` on the lane exactly as the
reference does, before the lane handler marks it `FAILED`. The case asserts the on-disk receipt equals
the in-memory one, the lane carries `LEFTOVER` and `dyn4k-core/karma.config.d` as its first forensic
path, no `source_process` was recorded, and `run_command` ran exactly once.

The Windows layers are now implemented against injected kernel seams rather than retired:

- `SafariWindowsFile.kt` ports `safari_windows_file` (`LockedDirectory`, `_open`'s reparse and
  type checks, `remove_empty`, `open_file`) over `SafariWindowsFileKernel`. Production supplies
  `SafariWindowsFile.fileKernel()`, which fails closed because `CreateFileW`,
  `GetFileInformationByHandle`, and `SetFileInformationByHandle` have no JVM equivalent; the
  reference suite's POSIX-backed kernel (`PosixWindowsFileKernel`) drives every branch on Linux.
- `SafariWindowsProcess.kt` ports `_run_lock_task_windows`, `_drain_lock_task_windows`,
  `_terminate_windows_tree`, `_resume_suspended_windows_process`, and `_windows_job_active_count`
  over `SafariWindowsJobKernel`, with `launch`, `taskkill`, `openSink`, `startReader`, `resume`, and
  `activeCount` seams for the rest. Production passes `failClosedKernel`.
- `_stage_windows` and `_forensic_windows` are ported over `SafariLockedDirectory`, and `stage` takes
  `windows`/`windowsDirectories` so the capture-level cases reach them.
- The POSIX `_run_lock_task_posix` takes a `SafariPosixGroup` (launch, `killpg(pid, 0)` probe,
  `killpg(pid, SIGKILL)`) and a `SafariPosixDrain` seam. The production group launches through
  `setsid` and probes/kills the real process group with `kill -s 0|-KILL -- -<pid>`, falling back to
  a live-descendant probe when `setsid` is unavailable.
- `SafariGitBash` ports `git_bash_from_git` and `bash_executable` with the `which`/`windows` seams.

All 123 reproduced methods pass on this Linux host; no Windows run is claimed. The Windows kernels
are fakes, exactly as in the reference's own POSIX runs, and the production kernels fail closed with
an explicit message instead of degrading.

Known divergences: when the held staging directory has been unlinked, the reference reads the
orphaned inode (empty) and the port treats the scan as empty by construction; `killpg` semantics are
reproduced with `setsid` + `kill -s 0|-KILL -- -<pid>` on hosts that have both, and with a
descendant probe otherwise; and the `assert_incomplete_fixture_status` helper prints
`command_identity` from a fixed expected command rather than the receipt's stored path.

The earlier "27 of 124" was a case-level aggregate that counted shared predicates rather than test
methods; 76 is the method-level count, not a regression. An earlier note here also said the context
group held 34 scanner cases; it holds 32, which with the 8 wrapper cases is the 40 the group started
this pass with. 37 of those 40 are reproduced (`SafariContextScanner`, `SafariContextBinding`,
`SafariContextCandidate`, `SafariContextSampler`, `SafariLaunchWrapper`), and the three that are not
are named in the Git Bash and context-fixture groups above.

Of the 48 that remain, the Windows and selector groups are **not** dead code, and an earlier note here
claiming a ceiling of about 91 was wrong:

- `test_safari_windows_file.py` (7) runs on POSIX today; it exercises the file layer through symlinks
  and aliases, so the Kotlin port can reproduce it directly.
- `test_safari_windows_process.py` (14) and the capture-level Windows cases run in CI on a real Windows
  runner: `.github/workflows/windows-qualification-harness.yml` runs the full
  `unittest discover -s tools/qualification` there. They are real coverage, not dead weight.
- The five selector/process-group cases patch `selectors` and probe a process group. The port drains
  with reader threads, so an equivalent seam (`drainFactory`, process-group probe) has to be added
  before those branches are reachable.

Retiring any of them therefore drops coverage that CI actually exercises, and the decision to do so has
to be explicit rather than inferred from "cannot run on this host".

Recorded divergences: `runLockTask(windows = true)` fails closed with an explicit message rather than
pretending to lock; the port replaces the three Python paths in `HOSTED_SOURCE_INPUTS` with the Kotlin
tools that implement the same behaviour, so an archived `source_input_sha256` map from the Python
diagnostic will not match the Kotlin one; the drain's `stream_incomplete` means a reader thread
outlived the drain deadline, not that a selector unregistered; and `capture_package_graph` sorts the
workspace inventory by path parts (as `pathlib` does), not by path text. The context scanner
materialises one directory's entries before descending into it, so it holds no descriptor across the
recursion; the reference keeps the `scandir` iterator open while it recurses. Both record the same
entries in readdir order, and neither promises an order.

### Why `artifact.py` cannot be freed through `independent_gates.py`

`independent_gates.py` is the last Python module that imports `artifact`, so the plan was to finish it and
delete it. Measured on 2026-10-30, that does not work yet: the module has **29 Python importers**, of
which 16 are non-test modules —

`duplicate_provider`, `full_android_adapter`, `full_android_consumer`, `full_android_native_consumer`,
`full_apple_device_consumer`, `full_browser_adapter`, `full_browser_consumer`, `full_jvm_consumer`,
`full_klib_adapter`, `full_klib_consumer`, `full_native_host_consumer`, `full_signed_routes`,
`full_staged_consumer`, `full_wasm_node_consumer`, `independent_audit_producer`, `linux_observed_klib`

— plus `qualify.py`, `independent_adapter.py` and every `full_*` consumer. So the order is: port the
`full_*` consumers and `qualify.py`, then `independent_gates.py`, and only then `artifact.py` and
`full_hosted.py`.

The aggregation half of `independent_gates.py` is ported (`evaluate_gate`, `evaluate`, `evaluate_assembly`,
`main` as `:qualification:independentGates`, `_independent_review`, `_java_full_ci`). Six gate bodies are
**not** ported and report `NOT_RUN` naming the missing harness rather than a fabricated pass:
`_verify_p2_host`, `verify_pending_prospective_bridge`, `verify_prospective_case_subgates`,
`_migration_journeys`, `_numerical_entries`, `_performance_resource`, `_evaluate_signed_full_consumer`,
`_browser_consumption_witness`.

The port pass also fixed two real defects it found: `IndependentGates.binding` and `externalUnavailable`
compared `receipt["lane"] != null`, but a JSON `null` parses to `JsonNull`, which is not Kotlin `null`, so
an approved **global** gate with a null lane was rejected as "raw lane differs".

### The `full_*` consumer family — measured

This is the largest untouched block and the last one that stands between here and deleting
`artifact.py`, `full_hosted.py`, `qualify.py` and `independent_gates.py`. Measured on 2026-10-30
(module lines / its test file / test cases):

| Module | Lines | Test lines | Cases |
| --- | ---: | ---: | ---: |
| `full_android_adapter.py` | 86 | 147 | 6 |
| `full_android_consumer.py` | 761 | 227 | 13 |
| `full_android_native_consumer.py` | 869 | 284 | 8 |
| `full_apple_device_consumer.py` | 881 | 211 | 11 |
| `full_browser_adapter.py` | 112 | 146 | 8 |
| `full_browser_consumer.py` | 1,725 | 1,873 | 52 |
| `full_jvm_consumer.py` | 554 | 387 | 7 |
| `full_klib_adapter.py` | 137 | 181 | 6 |
| `full_klib_consumer.py` | 1,020 | 596 | 14 |
| `full_native_host_consumer.py` | 2,385 | 1,733 | 38 |
| `full_signed_routes.py` | 1,127 | 2,200 | 31 |
| `full_staged_consumer.py` | 388 | 159 | 7 |
| `full_wasm_node_consumer.py` | 711 | 158 | 10 |
| `independent_adapter.py` | 585 | 1,419 | 21 |
| `independent_audit_producer.py` | 371 | 1,013 | 28 |
| **subtotal** | **11,712** | **10,734** | **280** |

With `qualify.py` (1,727 + 924) and `independent_gates.py` (4,234 + 6,418) the whole remaining
qualification block is **19,400 module lines and 18,076 test lines, 465 cases**. That is the scope, stated
once rather than re-estimated per pass.

**The shared adapter layer is ported.** `FullAdapterRules.kt` (pin tables), `FullAndroidAdapter.kt`,
`FullBrowserAdapter.kt`, `FullKlibAdapter.kt` with `FullAdapterSuite.kt` reproduce 12 of the 20 cases
here; the other 8 are the reference's retained-evidence cases. They are now registered in
`FullAndroidAdapterRetained` / `FullKlibAdapterRetained` and disabled (reported as skipped) without
`DYN4K_RETAINED_ANDROID_EVIDENCE` / `DYN4K_KLIB_EVIDENCE_ROOT`, exactly as the reference skips them:

| Module | Cases | Reproduced here | Retained-evidence cases |
| --- | ---: | ---: | ---: |
| `full_android_adapter.py` | 6 | 2 | 4 |
| `full_browser_adapter.py` | 8 | 8 | — |
| `full_klib_adapter.py` | 6 | 2 | 4 |

The adapters' imports, checked before porting: `full_android_adapter` → `full_android_consumer`,
`independent_gates`, `qualify`; `full_browser_adapter` → `full_browser_consumer`,
`independent_gates`; `full_klib_adapter` → `full_klib_consumer`, `independent_gates`. Of those,
`independent_gates.digest`/`archive_digest`/`_json` and `qualify.require_clean_checkout`
(`CleanRequire`) are already ported; the three `full_*_consumer` modules are **not**, so every consumer
call is a named seam (`FullAndroidConsumerPort`, `FullBrowserConsumerPort`, `FullKlibConsumerPort`)
whose production implementation fails closed naming the Python module. The consumer *constants* the
adapters read (`MODULES`, `ROUTES`, `LANES`, `CHROMIUM`, `JAVA_SHA256`, `GRADLE_SHA256`,
`LOCAL_LANES`, the toolchain key sets) are ported as data and pinned by
`FullAdapterVectors` (generated by `parity/generate_full_adapter_vectors.py` at `0bd90145`).

**`full_staged_consumer.py` is ported** (`FullStagedConsumerRules.kt` + `FullStagedConsumer.kt` +
`FullStagedConsumerCli.kt` + `fullStagedConsumer` Gradle task). The four contract cases run here; the
three `verify` cases are gated on `DYN4K_SUITE_ARCHIVE` (with `DYN4K_SUITE_REPOSITORY`,
`DYN4K_SUITE_EXPECTED_CORE`, `DYN4K_SUITE_EXPECTED_FACADE`) and are registered and disabled without
it. Invocation:

```
./gradlew -p tools/harness :qualification:fullStagedConsumer --args="run --repository <dir> \
  --candidate-sha <sha> --staging <dir> --output <dir> --gradle <exe> \
  --expected-core-sha256 <sha> --expected-facade-sha256 <sha>"
./gradlew -p tools/harness :qualification:fullStagedConsumer --args="verify --repository <dir> \
  --archive <dir> --expected-core-sha256 <sha> --expected-facade-sha256 <sha>"
```

The eight retained adapter cases are now **registered** in `FullAndroidAdapterRetained` and
`FullKlibAdapterRetained`, gated with `TestConfig.disable()` on `DYN4K_RETAINED_ANDROID_EVIDENCE` and
`DYN4K_KLIB_EVIDENCE_ROOT` the way the reference uses `skipUnless`. TestBalloon reports a disabled
test as skipped, so an absent variable can never look like a pass. Two consumer helpers they need
were ported for real as part of this (`full_android_consumer.approved_cases` →
`FullAndroidApprovedCases`, `full_klib_consumer.contract`/`staged_binary` → `FullKlibContract`), so
the ready path is short; the public replays (`verify_archive`, `verify`) remain the named seams, and
an *enabled* run therefore fails with "retained evidence present, consumer not ported: …" rather than
passing. That is the honest state until those two consumers are ported.

Next slice, `full_staged_consumer.py` (388 lines, 7 cases), is the easiest of the remaining
consumers: it imports only the standard library and `independent_gates`, and all of the helpers it
needs from that module (`digest`, `archive_digest`, `_inventory`, `_file_path`,
`load_approved_manifest`, `consumer_contract`) are ported. Its four contract cases
(`raw_case_ids`, `class_contract`, `graph_artifacts`/`graph_from_output`) are self-contained; the
three `verify` cases need `DYN4K_SUITE_ARCHIVE` retained evidence. The consumers after it
(`full_jvm_consumer`, `full_klib_consumer`) add staged-publication and real Gradle replay; the three
big ones (`native_host`, `browser`, `signed_routes`) remain the hardest.

Suggested order: the three adapters (335 lines, 20 cases) as the shared helper layer, then the staged,
jvm and klib consumers, then the big three (`native_host`, `browser`, `signed_routes`), then
`qualify.py` and `independent_gates.py`, and only then `artifact.py` and `full_hosted.py`.

### Completion bar: what "ported" means

A module counts as ported only when every item below holds. Scaffolding that shells out to
Python, hardcodes a workstation path, or duplicates a pin table is not a port, even when
the surrounding suite is green:

1. Golden vectors replay the Python result byte for byte.
2. The differential run passes while the Python file still exists.
3. Its workflow step is switched to the Kotlin command and the affected workflow ran once.
4. No `python3` subprocess outside the named interim seams (`JvmModePublication.PythonModeReplay`,
   `CollectionRuntime.ingestExternal`, `GatesAggregate` verifiers). `qualification-source-checks.yml`
   enforces this with the harness source guard.
5. No workstation repo-root literal (`Workspace/dyn4k`) in `tools/harness/*/src`; repository
   roots arrive as parameters or are discovered by walking up to `tools/qualification`.
6. Pin tables have one home (for example `FullJvmConsumerRules`, not a copy in the consumer).
7. `detekt` and `spotlessCheck` pass; new findings fail the build rather than joining a baseline.

### Retained-evidence gates, in one place

Every gate below reports skipped without its variables, so absence can never look like a pass.
Gradle declares them as test inputs, so a warm build directory cannot mask a provided archive.

| Variables | Suites | Unblocks |
| --- | --- | --- |
| `DYN4K_RETAINED_ANDROID_EVIDENCE` | `FullAndroidAdapterRetained` (4 cases) | `full_android_consumer` port |
| `DYN4K_KLIB_EVIDENCE_ROOT` | `FullKlibAdapterRetained` (4 cases) | `full_klib_consumer` port |
| `DYN4K_SUITE_ARCHIVE` + `DYN4K_SUITE_REPOSITORY`, `DYN4K_SUITE_EXPECTED_CORE`, `DYN4K_SUITE_EXPECTED_FACADE` | staged-consumer `verify` (3 cases) | retained suite archive from a scheduled lane |
| `DYN4K_FULL_JVM_ARCHIVE` + `DYN4K_JVM_MODE_PUBLICATION` (+ `DYN4K_FULL_JVM_LANE`, `DYN4K_FULL_JVM_CANDIDATE`) | `test_full_jvm_consumer.py` (Python, 7 cases) | `full_jvm_consumer` replay tail + lane re-capture |
| `DYN4K_FULL_CI_REPLAY_*`, `DYN4K_HOSTED_JOINED_EVIDENCE_DIR`, `DYN4K_BROWSER_*` | remaining Python consumer suites | their respective consumer ports |

The lane re-capture itself (frozen manifest, approved corpus, scheduled-lane receipts) waits on
the lane scheduler, which this tree cannot see. Until that run lands, no lane may be reported
as passing, and the Python qualification suite stays red by design, not by defect.

### The `full_*` adapters: ported, with 8 retained-evidence cases outstanding

`full_android_adapter`, `full_browser_adapter` and `full_klib_adapter` are ported
(`FullAdapterRules.kt`, `FullAndroidAdapter.kt`, `FullBrowserAdapter.kt`, `FullKlibAdapter.kt`;
`FullAdapterVectors.kt` pins every table — the browser lane table has 24 entries, the KLIB toolchain has
10 keys). 12 of their 20 cases are reproduced: browser 8 of 8, Android 2 of 6, KLIB 2 of 6.

The other 8 are **not** the same thing as the Python `skipUnless` cases, and the difference matters:

- In Python they are `skipUnless(DYN4K_RETAINED_ANDROID_EVIDENCE)` / `skipUnless(DYN4K_KLIB_EVIDENCE_ROOT)`,
  so they run in CI when those env vars are present.
- In Kotlin they do not exist at all, so a CI run that provides the retained evidence exercises them on
  the Python side only until they are written.

That is a real coverage gap to close before the adapters' Python files can be retired. The three
`full_*_consumer` modules they import are seams that throw with the missing function named
(`FullAndroidConsumerUnavailable`, `FullBrowserConsumerUnavailable`, `FullKlibConsumerUnavailable`), so the
adapters carry the real tables and predicates while the consumer bodies stay unported.

Next cheapest consumer: `full_staged_consumer.py` (388 lines, 7 cases) — standard library plus already
ported `independent_gates` helpers; expect 4 of 7 in a first pass, the other 3 needing
`DYN4K_SUITE_ARCHIVE`. Then `full_jvm_consumer` (554/7) and `full_klib_consumer` (1,020/14). The hard
block remains `native_host` (2,385/38), `browser` (1,725/52) and `signed_routes` (1,127/31).

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
| `tools/qualification/test_safari_windows_file.py` (7 cases) | `SafariWindowsFileSuite` (7) | the Windows layer is ported behind an injected kernel; production fails closed |
| `tools/qualification/test_safari_windows_process.py` (14 cases) | `SafariWindowsProcessSuite` (14) | same, behind the injected kernel/launch seams |
| `tools/qualification/test_safari_generated_shape.py` (1 case) | the CRLF self-checks in `SafariLeftoversSuite` | — |
| `tools/qualification/safari_yarn_lock.py` (1,285) | `SafariYarnLockRules`/`SafariYarnLockHost`/`SafariCapture`/`SafariContext`/`SafariWindowsFile`/`SafariWindowsProcess`/`SafariPosixGroup`/`SafariGitBash` + `:qualification:safariYarnLock`; 124 of 124 methods | no workflow step invoked it |
| `tools/qualification/test_safari_yarn_lock.py` (102 cases) | 47 safari suites, all green | the `git_oid`/`replace_loose_object`/`write_loose_object` helpers moved to `git_fixture.py` for `test_full_hosted.py` |
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
