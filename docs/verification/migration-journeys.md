# Unchanged Java sample migration journeys

This report covers the sample application subset of [Run the full compatibility corpus and unchanged migration applications](https://github.com/rubixhacker/dyn4k/issues/42). It follows the pinned [migration application research](https://github.com/rubixhacker/dyn4k/blob/4a0b829a66e8d4b49e652682590006df2ff6ed98/docs/research/migration-application.md). It does not qualify the full compatibility corpus or the 21 Kotlin targets.

## Result

At committed harness revision `9bdcb2b5c1e250156f186215946deac32b0d053d`, the worktree was clean before and after execution. The branch includes committed integration revision `713cfa1e018a4203734fa9e7a81c9830fa400c77` through merge `30f0bf48705099f302f5cfda57deeeb893b868f1`. Both providers passed the five selected headful Java2D scenes on a real X11 display served by Xvfb. All 10 journey cases passed; none failed or were unavailable. Both providers compiled all 42 tracked Java sources with `javac --release 8` and produced 66 class files each. The original scene main methods exited with code 0 after a requested window close. Separate instrumented runs also exited with code 0.

| Scene | Plain checks per provider | Observer checks per provider | Baseline steps | Candidate steps | Required observation |
| --- | ---: | ---: | ---: | ---: | --- |
| Tracking | 10/10 | 17/17 | 780 | 780 | Begin, persist and end callbacks; no sample error diagnostic. |
| Pyramid | 10/10 | 16/16 | 780 | 783 | 121 bodies, mouse pick joint, body movement and reset. |
| Crank | 9/9 | 15/15 | 785 | 784 | Four revolute/prismatic joints and piston motion. |
| Billiards | 9/9 | 20/20 | 782 | 785 | Cue shot, rack contact, settled balls and actual CCD hits. |
| Truck | 10/10 | 22/22 | 1140 | 1145 | Drive, brake, ramp crossing, suspension and cargo motion; CCD mode `NONE`. |

The total is 48/48 plain checks and 90/90 observer checks for each provider, or 276/276 checks across both. The observer captured 1,384 scene snapshots. Each scene's final recorded engine step duration was 1/60 second. The 58 PNG captures include initial, interaction, post-input and later frames where applicable. A visual inspection of candidate Billiards, Pyramid and Truck captures in the first run confirmed rendered scene content. Images alone do not establish physics behavior; the observer checks use body, joint, callback, step and CCD data.

Billiards recorded 34,917 detector calls, 57 detector hits and 57 time-of-impact listener hits on the baseline. The candidate recorded 34,673 calls, 50 detector hits and 50 listener hits. The first run also showed different cue event steps and captured ball layouts. **Billiards numerical and behavioral parity is an open gap.** These separate wall-clock runs prove actual CCD activity for each provider, but they do not establish fixed-input physics parity. A replay with identical initial state, cue impulse and step count is needed to evaluate the difference. Truck recorded CCD mode `NONE` and zero detector hits for both providers.

## Inputs and artifacts

The source is the first-party `dyn4j-samples` checkout at `2c6b318e929baab77e9753ae78a4965eee74a30a`. Its 42 tracked Java files were byte-identical to the selected research input. The SHA-256 of the sorted `sha256sum` source manifest was `15ce636ac8eec34b24e73bc96270b49a44c94318850050b1e9bc0d930a9c8d58`. The checkout remained clean. No sample source or legal notice was edited or copied into this repository.

The consumer resolved JARs from Maven Central and the local staged Maven repository. The baseline dyn4j 6.0.0 JAR SHA-256 was `204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e`. The staged `dyn4k-core-jvm:0.1.0-alpha.1` JAR SHA-256 was `b6986afbab28c9410ad471abdde038103a9acd6d161750d601f4a61de8efbd4d`; the resolved consumer copy matched it byte for byte. The staged POM and Gradle module metadata SHA-256 values were `8f3363ee47e5db5d076f7e933ccf4e69c2046c6283d9b653adce7085747be6ae` and `6612b86d10b6eea3cc7e252205aad9954a359a69419418b3e73abce163c78b78`. The candidate graph contained no upstream dyn4j provider. The raw compile reports list every resolved JAR and its hash.

The headful image ID was `1900e9e724693fe838b4fe16b27d313d340485690f4ae7a75cf208356b314641`. The host used JDK `21.0.12.1`, Podman and the pinned Debian 12 image in `tools/migration/Containerfile`. The display container supplied Xvfb, Openbox, `xdotool` and ImageMagick. A discovered window, PNG frames, input log and application process exit were required for each plain run. Observer bytecode weaving changed only generated class files. The 42 source files remained unchanged.

## Reproduce and inspect

Prepare the pinned sample checkout at `/tmp/dyn4k-migration-preflight/samples` and a JDK 21 at `/tmp/dyn4k-tools/jdk21`. Gradle needs network access to Maven Central for the pinned dependencies. Podman needs the pinned Debian base image and package access when building the display image. The commands used were:

```bash
JAVA_HOME=/tmp/dyn4k-tools/jdk21 ./gradlew :dyn4k-core:publishJvmPublicationToStagingRepository --console=plain
JAVA_HOME=/tmp/dyn4k-tools/jdk21 ./gradlew -p consumers/migration resolveBaseline resolveCandidate resolveInstrumentation --refresh-dependencies --console=plain
podman build -f tools/migration/Containerfile -t localhost/dyn4k-migration:journeys tools/migration
python3 -m unittest discover -s tools/migration -p 'test_*.py' -v
python3 tools/migration/journeys.py run-all --samples /tmp/dyn4k-migration-preflight/samples --resolved-root consumers/migration/build/resolved --repository build/staging-repository --instrumentation consumers/migration/build/resolved/instrumentation --output /tmp/dyn4k-migration-journeys-review-fix-9bdcb2b --javac /tmp/dyn4k-tools/jdk21/bin/javac --java /tmp/dyn4k-tools/jdk21/bin/java --jdk /tmp/dyn4k-tools/jdk21
python3 tools/migration/journeys.py verify-evidence --output /tmp/dyn4k-migration-journeys-review-fix-9bdcb2b
```

The exact-commit evidence root is `/tmp/dyn4k-migration-journeys-review-fix-9bdcb2b`. Its `summary.json` SHA-256 is `270eb5072f0ad346f11026e681ae44e80e4bbc2f509b769e6f8100a059062e20`; its 515-file sorted `evidence.sha256` manifest SHA-256 is `f08e96fb934348cf3a14ae0071c3a9512e9366711b00a393a609fa2dbec657c6`. The verification command above passed. Each provider has `compile/compile.json`, raw `javac.log`, and `observer-build.json`. Each scene has plain and observed input, process, display and application logs; per-scene validation JSON; and PNG captures. The observer log contains `OBS_JSON` records for world steps, step duration, bodies, joints, contacts and CCD. All 13 local tests passed, including adverse dirty-source, timeout, changed-evidence, changed-artifact, headless-launch and missing-CCD cases.

The harness now rejects a dirty candidate worktree before a run and checks the same commit and cleanliness after the run. It also rechecks the pinned sample revision, clean checkout and all 42 source hashes after scene execution. A failed final sample check writes `sample-check.json` and prevents a summary. Compiler and observer preparation commands have bounded timeouts and failed receipts. Each new run writes a sorted `evidence.sha256` list of raw files. `summary.json` records that manifest's SHA-256 and file count, binding the raw logs, captures, compiler receipts and artifact hashes to the exact harness commit. Use `python3 tools/migration/journeys.py verify-evidence --output <run-directory>` to detect changed, missing or added raw files. A SHA-256 manifest detects accidental changes; it is not an independent signature.

This is a bounded JVM migration result. The wall-clock scene scripts do not provide fixed-input numerical parity. The full declaration ledger, unchanged baseline test inventory, complete portable corpus, physical checks and all required target/runtime cases remain separate open requirements.

At handoff, the integration branch had advanced to `9802ebed0ef7a0ca081209d10e347af39b8f86d2`. A dry-run merge reported a content conflict in the unowned `dyn4k-core/build.gradle.kts`. This branch retains the clean committed integration revision named above. The newer integration changes require their owner to resolve that file before this journey evidence can be refreshed against that tip.
