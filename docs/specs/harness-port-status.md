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
| `:qualification` | `guard_hosted_runners.py` (**Python deleted**), `qualify.py` archives/audits/evaluation/CLI actions, `stage.py`, `publication.py`, `independent_gates` (part), `independent_linux_observer` (verification half), `full_corpus.py`, `full_suite_manifest.py` | partial | 289 |
| `:compatibility` | `world_ci`, `governing_*`, `candidate_coverage`, `method_coverage`, `java_corpus`, `execution_probe`, `full_ci`, `exception_ci`, `ledger`, `module_probe` | partial | 47 |
| `:performance` | `manifest`, `analyze`, `measure`, `candidate_*`, `sustained_archive`, `reference_study`, `host_capacity_control`, `stress_monitor` | partial | 115 |
| `:numerical` | `portable/cases.py`; `portable/receipt.py`; `portable/exact_consistency.py`; `portable/orthogonality.py`; `portable/physical.py` (`nominal_free`, `audit_physical`, sleep/wake, phases); `numeric_class_witness.read_witness`; `compare.py` (`compare`, `audit_reference`, `load_receipt`, `load_fixture`, the whole `compare_value` engine, `check_counts`, `check_snapshot`); `candidate/nominal_zero.py`; `weld_pulley_quality.py` (engine, phases, `atan`/`pi` enclosures, `Decimal`-at-80 rendering); `portable/rotation_oracle.py` (encoding, digest and manifest helpers only) | partial | 87 |
| `:android` | `android_corpus`, `build_identity`, `evidence`, `full_evidence`, `optimized_evidence`, `prepare`, `run`, `run_full`, `run_optimized` (Android); `receipt`, `full`, `adverse` (Android Native) — installed routes ported but never run on a device | ported | 110 |
| `:migration` | `journeys`, `fixed_replay`, `truck_camera`, `truck_timeline`, `validate_plain`, `validate_scene` and their four suites; the podman/X11 paths are unrun and the mains have no Gradle tasks | ported | 96 |
| `:baseline` | not started | pending | — |

Harness total at the last full run: 485 tests, 0 failures, across `:core`, `:host`,
`:compatibility`, `:performance`, `:qualification`.

## Python code removed

| File | Replacement | CI step |
| --- | --- | --- |
| `tools/qualification/guard_hosted_runners.py` | `GuardHostedRunners.kt` | `./gradlew -p tools/harness :qualification:guardHostedRunners` in `qualification.yml` and `qualification-source-checks.yml` |
| `tools/qualification/test_guard_hosted_runners.py` | `GuardHostedRunnersSuite.kt` (12 cases) | the separate test step was removed; `test_qualification_workflow.py` asserts the Kotlin command |

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
