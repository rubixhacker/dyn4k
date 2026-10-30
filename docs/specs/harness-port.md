# Port the harness to Kotlin and TestBalloon

## Goal

Every test in this repository is Kotlin and uses TestBalloon. The harness that the tests cover is Kotlin too. Python leaves the repository.

The harness is the 316 files under `tools/`. Of these, 131 files are `unittest` suites and 185 files are the tooling they cover. TestBalloon cannot execute Python, so the tooling must move before its tests can. This spec orders that move and states when a Python file may be deleted.

## Decisions

1. **New standalone Gradle build at `tools/harness`.** The repository already uses one build per deliverable (`consumers/*`). The harness build follows that pattern and does not join the root build.
2. **Three modules.**
   - `:core` is Kotlin Multiplatform. It holds pure contract logic: digests, canonical JSON, the target matrix, publication naming, receipt and manifest validation. It has no process, network, or platform API.
   - `:host` is a JVM module. It holds filesystem, process, browser, device, and clock adapters. It runs the `:core` contracts.
   - `:cli` is a JVM module. Each `tools/**/*.py` command becomes one `main` that keeps the same argv, stdout, exit codes, and artifact bytes.
3. **Tests live with the code they test.** `:core` suites are in `commonTest`, so they run on every target the module declares. `:host` and `:cli` suites are in `jvmTest`.
4. **Assertions use `kotlin.test`.** TestBalloon supplies the DSL; `kotlin.test` supplies assertions. No second assertion library.
5. **TestBalloon 1.2.0 with Kotlin 2.4.20.** Release 1.2.0 states compatibility with Kotlin 2.2.21 through 2.5.0-Beta2. The repository pins Kotlin 2.4.20.

## Parity rule

A ported function is accepted only when it reproduces the Python result byte for byte. Two mechanisms enforce this:

- **Golden vectors.** A JSON vector file records inputs and expected outputs produced by the Python implementation at a recorded commit. Kotlin tests replay the vectors. The vectors are data, not tests, and they stay after Python is deleted.
- **Differential run.** While the Python file still exists, a `:host` test runs both implementations on the same generated inputs and compares their output. This test is deleted with the Python file.

Deletion order for each Python module: port, pass vectors, pass differential run, switch its workflow step to the Kotlin command, run the affected workflow once, then delete the Python file and its `unittest` suite.

## Migration order

The order follows the import graph. A module moves only after its dependencies move.

1. `tools/qualification/qualify.py` contract core: matrix, digests, strict JSON, publication naming and paths, variant attributes, provider check.
2. `tools/qualification`: `artifact`, `collection`, `publication`, `stage`, `manifest`, and the receipt verifiers.
3. `tools/compatibility`: ledger, corpora, dispositions.
4. `tools/numerical`: portable arithmetic, rotation oracle, witness and comparison producers.
5. `tools/performance`: measure, capture, sustained studies, capacity control.
6. `tools/android-runtime`, `tools/android-native-runtime`, `tools/diagnostic`.
7. Workflow steps in `.github/workflows`.

`tools/migration` and the retained-evidence paths move last. They read archives that other modules produce.

## Convert the existing Kotlin tests

The repository holds 196 Kotlin test files on `kotlin("test")` and JUnit. They move to TestBalloon in the same program, after the harness build proves the TestBalloon setup on this Gradle and Kotlin version.

Mapping:

| Current | TestBalloon |
| --- | --- |
| `class X : TestCase()` with `@Test` | `val X by testSuite { test("...") { } }` |
| `@TestFactory` | a loop in test registration |
| `@BeforeTest` / `@AfterTest` | `testFixture { }.asContextForEach` |
| `@Ignore` | `test(...) { skip(...) }` or a registration-time condition |
| `assertFailsWith` | unchanged (`kotlin.test`) |

The `consumers/*` builds each own their test dependencies and must be changed in the same pass.

## Constraints

- Qualified evidence carries SHA-256 digests of tool output. A changed byte in a receipt invalidates retained evidence. Canonical JSON must match `json.dumps(..., sort_keys=True, separators=(",", ":"), allow_nan=False)` exactly, including its `\uXXXX` escaping of non-ASCII text.
- The charter requires every non-deprecated target. Moving a tool must not remove a target from the matrix or from runtime verification.
- No workflow step may run both implementations against production evidence at the same time.

## Untested claims

- TestBalloon 1.2.0 behavior on Gradle 9.5.0 is untested in this repository until the first `:core` suite runs.
- The parity of Python float formatting is untested until the float vectors pass.
- A full qualification rerun on Kotlin tooling is untested and remains open until the workflow switch.

## Increment 1

Scope: the first item of the migration order, plus the build foundation.

Deliverables:

- `tools/harness` build with `:core`, TestBalloon 1.2.0, Kotlin 2.4.20.
- `:core` contract code for the matrix, publication naming and paths, variant attributes, provider check, strict JSON, finite-number check, SHA-256 file digest, and canonical manifest digest.
- TestBalloon suites for the above, driven by golden vectors generated from `tools/qualification/qualify.py`.
- A record of which Python symbols remain unported in `qualify.py`.

## Evidence invalidation

The frozen complete-suite manifest and the approved corpus pin a SHA-256 for every test source file.
Converting a test file to TestBalloon changes that file, so the pinned hashes no longer match and the
lane verifiers reject the checkout with `selected method source differs`. This is expected and is not a
defect in the conversion.

The order of operations is therefore:

1. Convert the tests.
2. Regenerate the corpus and the complete-suite manifest with the harness.
3. Update the approved digest constants and record the new approval.
4. Run every lane and publish the receipts.

Step 3 is a review decision, not an implementation step. Until steps 2 to 4 complete, the frozen
manifest describes the previous test sources and no lane may be reported as passing.

### Measured cost of the conversion

The full qualification discovery run was measured on both sides of the branch on 2026-10-30:

| Tree | Command | Result |
| --- | --- | --- |
| `main` at `7a9679fb` | `python3 -m unittest discover -s tools/qualification -p 'test_*.py'` | 843 tests, 1 failure, 58 skipped |
| `kotlin-testballoon-migration` | same | 831 tests, 53 failures, 159 errors, 58 skipped |

The 12 missing tests are the deleted `test_guard_hosted_runners.py` suite, which
`GuardHostedRunnersSuite` replaces. The 212 red tests are new and all trace to one cause: six files that
the numerical qualification records pin as approved bytes were changed by the migration.

| Pinned path | Why it changed |
| --- | --- |
| `tools/numerical/portable/build.gradle.kts` | the TestBalloon plugin and framework dependency were added |
| `src/commonTest/kotlin/portable/PortableMatrixTest.kt` | converted to a TestBalloon suite |
| `src/commonTest/kotlin/portable/ProspectiveArithmeticTest.kt` | converted |
| `src/jvmTest/kotlin/portable/FocusedBooleanArithmeticSourceTest.kt` | converted |
| `src/jvmTest/kotlin/portable/RevoluteLimitsFalseCaptureTest.kt` | converted |
| `src/jvmTest/kotlin/portable/RotationPremiseFixtureTest.kt` | converted |

They appear in `independent_gates.py` in `APPROVED_PROSPECTIVE_EXECUTABLE_CHECKERS`,
`PROSPECTIVE_EXECUTABLE_CAPTURE_DEPENDENCIES`, `ARCHIVE_PRIVACY_CAPTURE_DEPENDENCIES`,
`P2_ARCHIVE_PRIVACY_DEPENDENCIES` and `ORDINARY_DIAGNOSTIC_BUILD_CLEANUP_CAPTURE_DEPENDENCIES`, and in
`APPROVED_MIGRATION`. Those maps record which bytes produced each retained numerical and JDI evidence
archive.

Re-pointing the ten pins at the new digests was tried and does **not** restore the suite: 72 tests still
fail with `prospective policy/checker blob differs` and `JDK 21 JDI producer blob differs:
tools/numerical/portable/build.gradle.kts`, because the evidence those gates verify was produced by the
previous bytes. Restoring them requires a fresh capture with the pinned toolchain (`dyn4j-6.0.0.jar`,
JDK 8, JDK 21, the JDI harness) and a new approval, not an edit to the pins.

Consequently the branch is red in exactly one area until that capture happens. No lane may be reported
as passing, and the pins must not be updated to make the suite green while the retained archives are
still the old ones.
