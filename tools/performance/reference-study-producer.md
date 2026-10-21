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

The producer checks the frozen engine tree and JVM pilot source against the study's source commit. It stages the existing candidate JVM artifacts offline, compiles the frozen baseline harness, and records exact artifact, probe, runtime, and image hashes. The study control uses the pinned baseline JAR. The staged candidate hashes are environment context; this A/A control does not load a candidate engine.

For each launch, the parent records `/proc` executable bytes and path, command line, selected environment fields, machine and boot identities, PID, process start ticks, and RSS samples. It checks the child nonce and process clock origin against a host monotonic bracket. It also checks the real stdout series against the child clock, provider, and run records. `runs/` retains those raw files. `plan.json` and `captures.json` feed `reference_study.py create` and `seal`; `archive/` contains the resulting version 2 signed study archive. `producer-observations.json` binds the retained external observations to the source raw files. `audit` checks those observations against the sealed archive and the copied control bytes.

The existing study schema hashes `series`, `environment`, and `monitor` as opaque files. It does not interpret their PID, process-start, nonce, clock, image, provider, or staged-artifact fields. The producer's own audit is useful diagnostic evidence, but a changed producer envelope or self-signed hash cannot independently prove freshness. The schema owner must add and independently validate an observer/source receipt binding, plus semantic checks across the three raw streams, the OS process identity, the launch nonce, the image and control bytes, and the monotonic interval. Keep the protocol digest outside the archive before collection. The separate raw-path schema P2 work must be integrated and reviewed before this producer can be treated as a signed independent source proof.

The result remains `qualification: unpassed`, `validated_reference_rows: 0`, and `numeric_limits: not_approved`. It does not alter the 28-family scope or any approved resource budget.
