# Harness port status

This file tracks the port of the Python harness to Kotlin. It is the working record for
`docs/specs/harness-port.md`. Update it when a module or suite changes state.

States: **ported** (Kotlin code plus TestBalloon tests, parity checked), **partial** (some functions in
Kotlin), **pending** (not started), **blocked** (needs a coordination step).

## Test frameworks

| Area | State | Evidence |
| --- | --- | --- |
| `dyn4k` commonTest and jvmTest | ported to TestBalloon | `./gradlew :dyn4k:jvmTest`; 61 tests, 0 failures, no non-TestBalloon suite |
| `dyn4k-core` commonTest, jvmTest, diagnostic | ported to TestBalloon | `./gradlew :dyn4k-core:jvmTest`; 2465 tests, 0 failures, no non-TestBalloon suite |
| `consumers/*`, `tools/numerical/portable` | in progress (delegated) | see agent report |
| `tools/harness` modules | TestBalloon only | `tools/harness/*/src/*Test` |

## Harness modules

| Python source | Kotlin location | State | Notes |
| --- | --- | --- | --- |
| `tools/qualification/qualify.py` contract: matrix, expand, publication names and paths, variant attributes, provider check, digests, canonical JSON, strict JSON | `tools/harness/core/.../Qualification.kt`, `CanonicalJson.kt`, `Sha256.kt` | ported | 22 golden-vector tests; vectors recorded from revision `7a9679fb` |
| `tools/qualification/qualify.py` publication metadata: variants, POM dependencies, POM metadata | `tools/harness/core/.../PublicationContract.kt` | ported | vector tests; Python emits metadata pointers in hash order, so comparisons are by name |
| `tools/qualification/qualify.py` remaining functions (archives, source contracts, audits, evaluation) | — | pending | needs JVM archive and file adapters |
| `tools/qualification/guard_hosted_runners.py` | `tools/harness/qualification/.../GuardHostedRunners.kt` | ported | 12 cases; CLI task `:qualification:guardHostedRunners`; output matches Python on the repository |
| `tools/compatibility/*` | `tools/harness/compatibility` | in progress (delegated) | |
| `tools/performance/*` | `tools/harness/performance` | in progress (delegated) | |
| `tools/numerical/*` | `tools/harness/numerical` | pending | |
| `tools/qualification/*` other modules | `tools/harness/qualification` | pending | |
| `tools/android-runtime`, `tools/android-native-runtime`, `tools/diagnostic`, `tools/migration` | — | pending | |

## Known parity hazards

- Canonical JSON must match Python `json.dumps(sort_keys=True, separators=(",", ":"), allow_nan=False)`,
  including `\uXXXX` escaping of every character above `0x7E` and Python float `repr`. The float formatter
  is JVM-only (`shortestDecimalParts` is an `expect` function) until other targets get an implementation.
- `qualify.publication_variant_contract` emits `available-at` entries in Python set order, which changes
  between interpreter runs. The Kotlin port emits matrix order. Evidence must not depend on that order.
- Workflow text is asserted by `tools/compatibility/test_qualification_workflow.py`. A workflow step may
  move to Kotlin only when the ported version of that suite asserts the new command.
