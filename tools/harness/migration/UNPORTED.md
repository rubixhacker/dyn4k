# Migration module port record

This module ports `tools/migration/*.py` to Kotlin and TestBalloon. It depends on `:core` and
`:host`. The Python files stay in place until their workflow steps switch to the Kotlin commands.

## Source map

| Python | Kotlin | State |
| --- | --- | --- |
| `fixed_replay.py` stream comparison: `read_stream`, `finite_tree`, `whole_count`, `body_pair`, `validate_step`, `missing_channel`, `first_difference`, `repeatability_difference`, `process_identity`, `ordering_difference`, `compare` | `commonMain/ReplayComparison.kt`, `commonMain/PyValue.kt` | ported |
| `fixed_replay.py run`: `run_fixed`, `main` | `jvmMain/FixedReplayRunner.kt`, `jvmMain/Cli.kt` | ported |
| `validate_scene.py`: `body`, `truck_motor_bounds`, `checks_for`, `main` | `commonMain/SceneValidation.kt`, `jvmMain/Cli.kt` | ported |
| `truck_timeline.py`: `valid_png`, `validate`, constants | `commonMain/TruckTimeline.kt`, `jvmMain/TruckRun.kt` (`TruckTimelineFiles`, `PngDecoders`) | ported |
| `validate_plain.py`: `read_text`, `read_png`, `validate`, `main --summary`, `main` | `commonMain/PlainValidation.kt`, `jvmMain/Cli.kt` | ported |
| `truck_camera.py`: constants, `TruckRun`, `main` | `jvmMain/TruckRun.kt`, `jvmMain/Cli.kt` | ported |
| `journeys.py`: `git`, `require_clean_candidate`, `inspect_samples`, `raw_evidence_manifest`, `write_summary`, `verify_evidence`, `record_unavailable`, `inspect_artifacts`, `compile_samples`, `subprocess_log`, `build_observer`, `podman_scene`, `run_all`, `main` | `commonMain/Journeys.kt` (constants and evidence rules), `jvmMain/JourneyRunner.kt`, `jvmMain/Cli.kt` | ported |
| JSON text with Python `json.dumps` formatting | `commonMain/PyJson.kt` | ported |

The Python comparison runs on Python's JSON types, so `PyValue` keeps `bool`, `int`, `float`,
`str`, `list`, and `dict` apart and preserves insertion order. `true` and `1` are different types,
and `1` and `1.0` differ in `type(left) is not type(right)`.

## Tests

`cd tools/harness && ../../gradlew :migration:jvmTest`

| Suite | Tests | Covers |
| --- | --- | --- |
| `FixedReplayContract` | 40 | all 30 `test_fixed_replay.py` methods with their sub-tests (36 comparisons), repeatability, first-difference typing and tolerances, process identity, the matching-stream result |
| `JourneyCommandContract` | 12 | all 12 `test_journeys.py` methods |
| `SceneValidationContract` | 4 | all 4 `test_validation.py` methods |
| `TruckTimelineContract` | 34 | 22 timeline cases, 10 plain-admission cases, the slow-hold case, and the decoder-failure cases from `test_truck_camera.py` |
| `MigrationCliContract` | 6 | command argv, stdout files, and exit codes |

The suites need `javac` from the test JVM (`java.home`) and `git`. `JourneyCommandContract` also
needs `podman` for the two `run-all` cases. If `podman` is absent, those two cases keep the
compile, sample-check, and summary assertions but skip the recorded `preparation.json` and summary
comparison, because Python records the podman reason.

## Vector provenance

`vectors/generate_vectors.py` imports the Python implementation at revision
`1cb1429545592c720451f8cb1b6f30ec169fb240` and writes
`build/vectors/migration-vectors.json`. `vectors/emit_kotlin_vectors.py` writes
`src/jvmTest/.../MigrationVectors.kt`. Regenerate both with those two scripts.

- The fixed-replay vectors are captured by running the Python `unittest` suite with a recording
  `compare`, so each case holds the exact streams the Python test passed and the exact report
  Python wrote.
- The scene, timeline, and plain vectors are generated from the same fixtures the Python tests
  build and recorded from the Python functions and the Python command line.
- The journey vectors use generated git repositories with fixed author and date, so the commit and
  manifest digests are reproducible. The policy that pins the sample revision, the manifest digest,
  and the JAR digests is a test seam: `JourneyPolicy.DEFAULT` holds the Python constants exactly.
- Receipt paths, the compiler path, and `javac_version` are replaced by `<work>`, `<javac>`, and
  `<version>` before comparison. A receipt byte comparison would otherwise depend on the checkout
  and JDK that ran it.
- The valid PNG is recorded as base64 so both implementations hash the same bytes. Every malformed
  variant is derived from it with the same arithmetic the Python test uses.

## Not ported or not confirmed

- **The command entry points have no Gradle tasks.** `JourneysCli`, `FixedReplayCli`,
  `ValidateSceneCli`, `ValidatePlainCli`, and `TruckCameraCli` are `@JvmStatic main` functions. The
  spec assigns one `:cli` main per Python command; this module has the mains but no `JavaExec`
  task, so no workflow can call them yet.
- **No differential run.** The spec asks for a `:host` test that runs both implementations while
  the Python file exists. The golden vectors replace it here. A differential test would need
  Python, `podman`, and the built resolved JARs in the test environment.
- **The real pinned evidence never ran.** The generated fixtures exercise the same code, but no
  case uses the pinned `dyn4j-samples` checkout, the published `dyn4j` JARs, the staged candidate
  JAR, or the headful image. Those need the archive paths the parent tasks retain.
- **The podman and X11 paths never executed.** `podman_scene`, `build_observer`, the observed
  pass, and `TruckRun.run` are ports without a run. `build_observer` and `run` have no tests.
- **JSON parse error text differs.** Python `json.JSONDecodeError` messages name a line and column.
  `kotlinx.serialization` messages differ. `validate_scene` records these strings in
  `parse_errors`, so a malformed `OBS_JSON` line produces different text. Counts and statuses
  agree.
- **IO error text is approximated.** `pythonIoMessage` reproduces the common `[Errno N] ...`
  forms. Other `OSError` texts (for example a write failure) use the JVM message.
- **`Path.resolve()` is not exact.** `fixed_replay` records `str(args.jdk.resolve())`. The port uses
  `toAbsolutePath().normalize()`, which does not resolve symbolic links.
- **`Path.glob("*.jar")` filters directories.** The port lists regular files only. Python would
  list a directory whose name ends in `.jar` and then fail reading it.
- **Byte-string line counting is narrow.** `verify_evidence` counts manifest lines by `\n` only.
  Python `bytes.splitlines` also splits on `\r`, `\r\n`, and other boundaries.
- **`PyValue.Int` is a `Long`.** Python integers are unbounded. Values outside the signed 64-bit
  range parse as `float`.
- **`pyLength` counts UTF-16 units for text.** Python counts code points. Non-ASCII text in a
  length-checked channel would differ.
- **`argparse` is approximated.** `--name value` and `--name=value` are accepted. Option
  abbreviation, `-h` help text, and exact usage strings differ. Exit code 2 is kept.
- **`shutil.copytree` details differ.** The port copies files and directories but not metadata.
- **`truck_camera` subprocess failures record `Exception` messages.** Python catches
  `BaseException`. The recorded `error` text comes from the JVM for a failed `xdotool` or `import`.
