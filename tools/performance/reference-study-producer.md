# Linux/JVM reference-study producer

This CLI collects one bounded `source` phase A/A assignment. It launches six fresh JVM baseline processes in the frozen `a,b`, `b,a`, `a,b` order. The assignment is `jvm_vs_dyn4j|jvm.java|separated.default.small.30hz.compatibility|timing|median|full`. Each process runs the same dyn4j 6.0.0 fixture for one to five measured seconds after one to five warm-up seconds. This is a producer and archive-shape study. It does not qualify a reference row.

Use the pinned JDK 21, pinned offline Gradle 9.5.0, and a home-backed temporary directory. Keep the independent operator key outside the output root. The command refuses an existing output root. A failed run retains its partial files for inspection.

```sh
export JAVA_HOME=/tmp/dyn4k-tools/jdk21
export TMPDIR="$HOME/dyn4k-performance-tmp"
export JAVA_TOOL_OPTIONS="-Djava.io.tmpdir=$TMPDIR"
python3 tools/performance/reference_study_producer.py capture \
  --output-root "$HOME/dyn4k-evidence/reference-study-jvm-source" \
  --trusted-key "$HOME/private/reference-study.key" \
  --java "$JAVA_HOME/bin/java" --javac "$JAVA_HOME/bin/javac" \
  --gradle /tmp/dyn4k-tools/gradle-9.5.0/bin/gradle \
  --baseline /tmp/dyn4k-performance-dyn4j-6.0.0.jar \
  --seconds 1 --warmup-seconds 1
python3 tools/performance/reference_study_producer.py audit \
  --output-root "$HOME/dyn4k-evidence/reference-study-jvm-source" \
  --trusted-key "$HOME/private/reference-study.key"
```

Before staging, the producer rejects tracked or untracked changes in the engine modules, JVM harness, and root Gradle inputs. It separately compares the committed engine trees and frozen JVM pilot sources with the study source commit. It stages the existing candidate JVM artifacts offline, compiles the frozen baseline harness, and records exact artifact, probe, runtime, and image hashes. The study control uses the pinned baseline JAR. The staged candidate hashes are environment context; this A/A control does not load a candidate engine. Every child process receives an environment without `OLLAMA_API_KEY`.

For each launch, the parent records `/proc` executable bytes and path, command line, selected environment fields, machine and boot identities, PID, process start ticks, and RSS samples. It checks the child nonce and process clock origin against a host monotonic bracket. It also checks the real stdout series against the child clock, provider, and run records. `runs/` retains those raw files. The archived timing series is a two-column projection of the JVM stdout. The producer audit compares every projected step and elapsed time with the retained full stdout and checks its recorded SHA-256.

`plan.json` and `captures.json` feed `reference_study.py create` and `seal`. `archive/` contains the signed version 3 study archive. Each of the six captures supplies 13 separate raw source files: the timing series, environment, monitor, OS observer, source receipt, build receipt, provider, clock origin, measured clock, warm-up clock, run receipt, staged core JAR, and staged Kotlin JAR. The build receipt and JAR bytes have distinct per-run copies with checked hashes. The source receipt binds the other 12 raw hashes, the typed capture identity and control digests, the source commit, both staged hashes, the full OS-observed command, and the ordered probe and baseline classpath paths and hashes. The protocol records their original absolute source paths. The producer audit compares its retained source files and observations with the signed index and the public verifier's semantic checks. `producer-observations.json` also records each source hash and the original stdout hash.

The observer reads the live process externally, but an operator who can replace the raw files and sign a new envelope can still make a self-consistent synthetic archive. Retain the original output root, external key, process logs, and protocol digest for independent audit. Historical version 2 archives remain pinned to their exact historical verifier tool hash; do not restamp them as version 3. A version 3 source study is still a short archive-shape control, not 600-second calibration or reference-row qualification.

The result remains `qualification: unpassed`, `validated_reference_rows: 0`, and `numeric_limits: not_approved`. It does not alter the 28-family scope or any approved resource budget.
