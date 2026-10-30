# What the Android port covers

This module ports `tools/android-runtime/*.py` and `tools/android-native-runtime/*.py` into
`:android`. Pure parsing and decision logic lives in `src/commonMain`; process, git, ADB, and
filesystem adapters live in `src/jvmMain`. The Python files are unchanged and remain the reference.

## Parity evidence

`src/jvmTest/.../AndroidVectors.kt` holds JSON recorded from the Python implementation at the git
revision named inside it. Both suites replay it and compare byte for byte: error messages, mapped
descriptors, generated app inputs, and `json.dumps` output.

Regenerate with:

    python3 tools/harness/android/parity/generate_vectors.py > vectors.json
    python3 tools/harness/android/parity/emit_kotlin_vectors.py < vectors.json

The generator is deterministic apart from the recorded revision and the scratch directory it
normalises to `<tmp>`. Re-running at a later revision changes only the `git_revision` field as long
as the Python modules are unchanged.

Ported suites (83 Python cases, reproduced as 110 TestBalloon tests — some Python cases loop over
many inputs and are kept as one parameterised test):

| Python suite | TestBalloon suite | Cases |
| --- | --- | --- |
| `test_evidence.py` | `InstrumentationEvidenceContract` | 11 |
| `test_optimized.py` | `OptimizedEvidenceContract` | 30 (+1 golden mapping case) |
| `test_full_corpus.py` | `FullCorpusEvidenceContract` | 10 |
| `test_full_evidence.py` | `FullInstalledEvidenceContract` | 13 |
| `test_provenance.py` | `GeneratedConsumerProvenanceContract` | 4 |
| `test_serial.py` | `EmulatorSerialContract` | 5 |
| `test_full_executor.py` | `FullExecutorContract` | 1 |
| `test_full.py` | `NativeFullRouteContract` | 7 |
| `test_receipt.py` | `NativeReceiptContract` | 2 |
| — | `AndroidGoldenVectorsContract` | 26 |

## Not ported

| Symbol | Reason |
| --- | --- |
| `full_suite_manifest.validate_manifest` (called by `android_corpus.load_suite`) | It rebuilds the complete suite manifest from the repository and belongs to the `tools/qualification` port. `AndroidFiles.loadSuite` accepts an optional validator so the qualification port can supply it; without one it checks the manifest's own counts (2523 portable, 2465 in `dyn4k-core`). |
| `full_corpus.scan_sources` / `full_corpus.make_manifest` (called by `android-native-runtime/full.manifest_at`) | Same reason. `NativeFullHost.manifestAt` takes an optional `regenerate` callback; without one it verifies the committed bytes, kind, policy, and reviewed totals only. |
| `prepare.main` / `run.main` / `run_full.main` / `run_optimized.main` (argparse wiring) | Reproduced as `Cli` entry points with the same options and defaults, but argparse's own grammar is not reimplemented: abbreviations and `--flag=value` beyond simple name/value splitting are not supported. A rejected value raises `ArgumentTypeError`, which the Gradle entry point must report as a usage error with exit code 2. |
| `android-native-runtime/run.py` and its `main` | Ported as `NativeReceiptHost`/`NativeFullHost` functions; the CLI wrapper is not provided because no Gradle entry point calls it yet. |
| `adverse.test_adverse` CLI `main` | The harness is ported as `Adverse.testAdverse`; it has no command-line entry point. |

## Behaviour not confirmed by this port

- **No on-device run happened.** No emulator or device was attached. Every installed route
  (`run_lane`, `run_optimized`, `run_full`, `run_full --seal-build`, the native `run`/`pin`
  actions) is ported but was never executed against ADB, Gradle, or a build tree. Its decisions are
  validated against recorded command output and recorded logs instead.
- **`test_full_executor` ran with a different JDK than the Python test asserts.** The Python case
  compiles with `/tmp/dyn4k-tools/jdk21`, which does not exist on this host. The Kotlin case uses
  any `javac` on the PATH (here Android Studio's JBR 25.0.3) plus the cached JUnit 4.13.2 and
  Hamcrest 1.3 JARs. The behaviour under test — an assumption failure is recorded as a FAILED
  installed case — is compiler-independent, but the pinned-toolchain claim is not reproduced.
- **`build_jdk` is never actually produced here.** `BuildIdentity.currentJava` needs
  `/tmp/dyn4k-tools/jdk21`; only its version-banner extraction is exercised (via `BuildJava`
  vectors and an injected `BuildHost`).
- **`prepare` and the installed routes were never run end to end**, so the staged-publication
  layout, the portable suite JAR contents, and the full consumer `javac` compile are unverified
  beyond `test_full_corpus`/`test_provenance`, which exercise the file logic on synthetic trees.
- **`PyJson.prettySorted` is verified for objects, arrays, integers, booleans, null, and strings.**
  Floats are passed through as their source text, which matches Python only when the value came
  from JSON text Python itself wrote; nothing in these receipts contains a float, but a future
  receipt that does would need the `:core` float formatter.
- `AndroidFiles.verifyJvmXml` treats an empty numeric XML attribute as `-1`; Python's `int("")`
  would raise. Only reachable with a malformed report.
- `run_lane` and the installed routes throw `IllegalStateException` for a failed command where
  Python raises `RuntimeError`, and `FileNotFoundException` where Python raises `OSError`. The
  catching behaviour of each route is reproduced (both are caught where Python catches them).
