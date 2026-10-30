# What the performance port does not cover

The port moves the deterministic logic of `tools/performance/*.py` into
`:performance` (`commonMain`). Everything listed here stayed in Python because it needs a
process, a device, a clock, a network, or a real filesystem, and those adapters belong in
`:host`. The Python files are unchanged and remain the reference.

Parity evidence: `src/commonTest/.../PerformanceVectors.kt` holds outputs printed by the
Python implementation at git revision `df640f26be0a61d8db5c6e7624114595aebf379a`.
Regenerate with `parity/generate_vectors.py`. `tools/performance` is byte-identical at
that revision and at the current HEAD, so the vectors still describe the reference.

## `manifest.py`

Ported: `TARGET_ROWS`, `SIZES`, `JOINT_MODES`, `JOINT_PARAMETERS`, `build_config`,
`development_config`, `minimum_policy`, `gates`, `rows`, `scenarios`, `manifest`,
`ccd_fixture_revision`, `validate`, `validate_ccd_fixture_revision`.

Not ported:

| Symbol | Reason |
| --- | --- |
| `main` | argv, stdout text, and exit codes are a `:cli` concern. |
| `V1_MANIFEST_FILE` | a repository path; callers pass the manifest bytes in. |

## `analyze.py`

Ported: `samples` (over supplied text), `percentile`, `warmup_status`, `activity_status`,
`bootstrap_ratio`, `plateau_status`, `compare_pair`.

Not ported:

| Symbol | Reason |
| --- | --- |
| `report` | walks an evidence directory and reads `evidence.json` plus every raw file. |
| `main` | CLI wiring. |

## `measure.py`

Ported: `PILOT`, `balanced_orders`, `validate_csv` (over a parsed table), `summary`.

Not ported:

| Symbol | Reason |
| --- | --- |
| `sha256` | file digest; the equivalent is `CandidateRunner.hashPath`. |
| `jar_path` | downloads `dyn4j-6.0.0.jar` over the network. |
| `read_text` | filesystem read with `OSError` suppression. |
| `host_identity` | runs `java -version` and reads `/proc/cpuinfo`, `/proc/meminfo`, DMI, `/etc/os-release`. |
| `compile_harness` | runs `javac`. |
| `run_capture` | spawns a runner and polls `/proc/<pid>/statm` for RSS. |
| `run_scenario` | spawns the harness, then validates and summarises its output. |
| `main` | CLI wiring. |

## `candidate_runner.py`

Ported: `hash_path`, `verify_hashes`, `read_paths`, `check_route`, `VERSION`, `CORE`,
`API`, `FLAGS`, `entrypoints`.

Not ported:

| Symbol | Reason |
| --- | --- |
| `git` | subprocess. |
| `source_trees` | `git rev-parse <commit>:<tree>`. |
| `prepare` | needs git, the staging repository, and a JVM. |
| `run` | `os.execv` into the candidate JVM. |
| `main` | CLI wiring. |
| `ROOT`, `CONSUMER`, `STAGING`, `PATHS`, `IDENTITY` | host-owned absolute paths. |

## `candidate_pilot.py`

Ported: `STATE_FIELDS`, `state_checksum`, `clean_warmup`, `select_scenarios`.

Not ported: `save` (file write), `pilot` and `plateau` (spawn the harness and the candidate
runner), `main`.

## `analyze_candidates.py`

Ported: `summarize_pilot`, `exploratory_intervals` (with the raw-file resolver supplied by
the caller).

Not ported: `read_archive` (walks an evidence tree and re-digests every raw file), `main`.

## `fixture_revision.py`

Nothing is ported. `expected_record` verifies `git show <commit>:tools/performance/ccd_route_trace.py`,
`git rev-parse`, three fixture-identity CSVs, and the identity hashes recorded in
`candidate-identity.json`; `main` also needs the archive. Every check is a git or
archive-bytes check.

## `negative_controls.py`

Nothing is ported. `evaluate_controls` needs the staged candidate classpath, a pilot
evidence directory, `git rev-parse HEAD`, and temporary CSV rewriting. The rules it
demonstrates are ported individually by `CandidateRunner.checkRoute`,
`CandidateRunner.verifyHashes`, `Measure.validateCsv`, and `Analyze.activityStatus`, so the
behaviour is covered even though the harness is not.

## `provider_probe.py`

Nothing is ported. `probe_routes` executes `performance.ProviderIdentity` in the candidate
JVM and reads its stdout. The route and artifact rules it applies are
`CandidateRunner.checkRoute` and `CandidateRunner.verifyHashes`, both ported.

## `stress_monitor.py`

Ported: `METHODS`, `stress_monitor_method`, the PID and unit validation of
`peak_rss_bytes` for Linux (`VmHWM`), and the PID/unit validation of the macOS `ps` and
`wait4` samples (`darwinExternalSample`, `darwinTerminalPeak`).

Not ported: the Darwin `subprocess.run(["/bin/ps", ...])` call, the Windows `ctypes`/PSAPI
branch, `PROCESS_MEMORY_COUNTERS`, and the `os.wait4` call itself.

## `host_capacity_control.py`

Ported: `FIELDS`, `CHILD_SOURCE`, `signature`, `source_encoding`, `SOURCE_PATH`.

Not ported:

| Symbol | Reason |
| --- | --- |
| `source_at_commit` | walks `git cat-file` commit and tree objects byte by byte. |
| `capture` | spawns the diagnostic child, observes its process image, samples RSS, and stops it. |
| `capture_stop` | `os.kill`/`wait4` on Darwin; `TerminateProcess` on Windows. |
| `validate_record` | needs an archive directory, `git cat-file`, and the observed process. |
| `verify_archive` | archive inventory plus `validate_record`. |
| `main` | CLI wiring. |

## `sustained_archive.py`

Ported: `MODES`, `ROUTES`, the field lists, `PROCESS_IMAGE_METHODS`,
`FROZEN_MANIFEST_SHA256`, `frozen_policy` (over supplied bytes), `require_measurements`,
`require_reports`, `require_noise`, `require_plateaus`, `comparison_control_keys`,
`noise_limit_lookup`, `approved_gate`, `command_prefix`, `canonical`, `signature`,
`write_index`'s signature step, `capture_key`, `allocation_rows`, `upper_within`,
`step_summary` (as `Measure.stepSummary`), `scalar_interval` (as
`Analyze.scalarInterval`).

Not ported:

| Symbol | Reason |
| --- | --- |
| `wait4_peak_rss`, `windows_peak_handle`, `windows_terminal_peak`, `windows_dispatch_stop`, `close_windows_peak_handle` | native process and `ctypes` calls. |
| `observed_host`, `observe_process_image` | `platform` and `/proc/<pid>/exe`, `libproc`, `QueryFullProcessImageNameW`. |
| `require_external_key` | filesystem key placement checks. |
| `checked_file`, `csv_rows`, `warmup_rows` | filesystem reads. |
| `verify_source_and_artifacts`, `control_artifacts`, `verify_references` | archive tree walks plus git. |
| `validate_steps`, `validate_memory`, `validate_plateau`, `validate_stress`, `validate_clock`, `validate_warmup_clock`, `validate_process_clock`, `validate_v2_sidecars` | each reads several archive files and cross-checks the observed process. |
| `verify_capture`, `interval`, `check_budgets`, `_verify_archive`, `analyze_noise_groups`, `analyze_candidate_groups`, `verify_archive`, `verify_capacity_report` | whole-archive verification. |
| `initialize_archive`, `capture_one`, `merge_parts` | spawn processes and write archives. |
| `require` | the port throws `IllegalArgumentException` directly. |
| `main` | CLI wiring. |

## `reference_study.py`

Ported: every constant, `raw_files`, `capture_keys`, `absolute_source_path`, `sha_bytes`,
`exact_keys`, `hex_digest`, `policy_context`, `controls_for`, `checked_relative`,
`unique_object`, `same_json`, `validate_protocol`, `validate_captures`,
`validate_v3_capture`.

Not ported:

| Symbol | Reason |
| --- | --- |
| `sha_file` | filesystem digest. |
| `load_unique_json` | needs a JSON parser that reports repeated keys; `kotlinx-serialization` silently keeps the last one. `unique_object` is ported for callers that already have pairs. |
| `signed_json`, `write_signed` | read and write archive files. |
| `create_archive`, `seal_archive`, `verify_archive` | copy inputs into an archive, then verify it. |
| `main` | CLI wiring. |

## `reference_study_producer.py`

Nothing is ported. Every function runs `git`, Gradle, `javac`, `jar`, or observes a live
process through `/proc`. `child_environment` and `checked_rows` are pure but unusable
without the rest.

## `sustained_host.py`

Nothing is ported: the build, capture, and verify paths all need Gradle, a JVM, and procfs
process observation.

## `calibrate.py`, `warmup_probe.py`

Nothing is ported. Both are thin CLIs over `measure.run_scenario` plus `host_identity`; the
only portable logic they contain (`bootstrap_ratio`, `warmup_status`, `activity_status`,
30-second window medians) is already ported.

## `ccd_route_trace.py`

Nothing is ported. `first_difference` is pure but only meaningful over the fixture-identity
CSVs that `capture` produces by running three staged routes.

## `bounded_adapter.py`

Nothing is ported. `capture` spawns three routes and snapshots their inputs; `verify`
re-reads the signed archive, recomputes every digest, and re-runs the fixture command
comparison. `verified_file` and `require_committed_sources` are thin wrappers over
`CandidateRunner.hashPath` and git, both of which are ported or listed above.

## Python test cases

204 `unittest` cases exist across the nineteen suites. 42 are reproduced as named
TestBalloon tests, 25 more cover a rule the vectors do not reach, and 48 replay recorded
Python vectors, for 115 tests total. The remainder are not reproduced:

| Suite | Cases | Ported | Why the rest is not |
| --- | --- | --- | --- |
| `test_analyze.py` | 3 | 3 | — |
| `test_measure.py` | 1 | 1 | — |
| `test_candidate_pilot.py` | 1 | 1 | — |
| `test_candidate_runner.py` | 2 | 2 | — |
| `test_manifest.py` | 5 | 5 | — |
| `test_stress_monitor.py` | 8 | 6 | the Windows PSAPI `ctypes` mock and the hosted macOS/Windows probe need a native process. |
| `test_sustained_archive.py` | 54 | 1 | synthetic archives, native stop dispatch, capacity receipts, and budget re-execution. |
| `test_reference_study.py` | 43 | 20 | version 3 sidecar round-trips, pinned historical verifiers, duplicate JSON keys inside a file, and hard links to control files. |
| `test_reference_study_producer.py` | 20 | 0 | real Gradle/JVM captures and procfs observation. |
| `test_host_capacity_control.py` | 19 | 3 | git object walking, live child capture, and signed-receipt replay. |
| `test_verify_candidate_archive.py` | 21 | 0 | requires a retained production archive. |
| `test_sustained_host.py` | 1 | 0 | requires a retained signed host archive. |
| `test_sustained_host_v2.py` | 8 | 0 | requires retained signed version 2 archives. |
| `test_sustained_jvm.py` | 1 | 0 | requires the pinned dyn4j jar and a JVM. |
| `test_sustained_jvm_memory.py` | 5 | 0 | requires a JVM and real collection probes. |
| `test_sustained_jvm_p2_candidate.py` | 5 | 0 | requires the staged candidate build. |
| `test_ccd_fixture.py` | 2 | 0 | requires staged Java and the pinned baseline JAR. |
| `test_bounded_adapter.py` | 1 | 0 | end-to-end CLI capture and audit. |
| `test_pilot.py` | 4 | 0 | runs `BaselinePilot` on the pinned dyn4j jar. |
