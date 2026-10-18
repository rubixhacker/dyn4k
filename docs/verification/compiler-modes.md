# JVM compiler modes and Linux x64 Native configurations

The public runner is `tools/qualification/compiler_modes.py`. It records each configuration in a separate output directory. `verify` replays a retained receipt against the exact committed source tree, staged archive hashes, raw process logs, and complete case identities.

## JVM modes

The Gradle property `jvmCompilerMode` accepts `default` and `no-optimize`. The latter adds Kotlin `-Xno-optimize` to both JVM targets. It does not set Java `-Xint`. Each `compileKotlinJvm` task prints its resolved compiler flags in the raw Gradle log. The runner requires both task lines and both flag lines.

For each mode, the runner publishes the root and JVM variants for both modules. It copies the staged repository before building the next mode. The retained JVM JARs, POMs, Gradle metadata, and checksum sidecars are separate. A later publication cannot silently replace the prior mode's archive.

The runner executes the source-derived 2,454 core and 61 facade JVM identities on Java 8 and the pinned current JDK 21. It copies the compiled test classes into the mode receipt before execution. The test processes use those retained copies. Replay checks their fixed classpath locations and every retained file hash, so it does not need the author worktree's build directories. It compiles all 199 pinned unchanged Java test files in one Java 8 `javac` process and runs the 2,385 expanded cases against the staged core JAR on each runtime. The receipt retains that compile command, source list, exit code, separate stdout and stderr hashes, and combined log hash. The external JVM consumer resolves the staged modules, then runs its Kotlin entry point and Java migration call on each runtime. Its compile logs are retained separately for Java 8 and current JDK execution. Replay checks both compile commands and logs, each execution command, the selected JDK, and the mode's staged JAR paths. A run with missing, extra, duplicate, failed, or skipped cases is unpassed.

An earlier JVM receipt without the original `javac` record, separate consumer compile logs, or retained compiled test classes is unpassed under this verifier. It cannot acquire that evidence through replay.

```bash
candidate_sha=$(git rev-parse HEAD)
python3 tools/qualification/compiler_modes.py run --candidate-sha "$candidate_sha" \
  --target jvm --mode no-optimize --output /tmp/dyn4k-jvm-no-optimize
python3 tools/qualification/compiler_modes.py run --candidate-sha "$candidate_sha" \
  --target jvm --mode default --output /tmp/dyn4k-jvm-default
python3 tools/qualification/compiler_modes.py verify --candidate-sha "$candidate_sha" \
  --target jvm --mode no-optimize --output /tmp/dyn4k-jvm-no-optimize
```

## Linux x64 Native modes

The `debug` and `optimized` lanes link and execute distinct `linuxX64` test executables. The optimized lane uses `linkReleaseTestLinuxX64`; the ordinary `linuxX64Test` task covers only debug. Each executable must report the complete 2,454 core or 58 facade common identities. The runner records both ELF bytes, staged KLIB bytes, the Linux kernel and glibc, and the external staged consumer executable. Replay requires the selected consumer link command, its fixed log path, the matching raw task and successful build lines, and execution of the retained hashed ELF. Its four cases include a world step through the published artifacts.

```bash
candidate_sha=$(git rev-parse HEAD)
python3 tools/qualification/compiler_modes.py run --candidate-sha "$candidate_sha" \
  --target linuxX64 --mode debug --output /tmp/dyn4k-linux-debug
python3 tools/qualification/compiler_modes.py run --candidate-sha "$candidate_sha" \
  --target linuxX64 --mode optimized --output /tmp/dyn4k-linux-optimized
```

These Linux runs identify the current host. They do not establish the minimum supported kernel or glibc. A successful route here does not close the other target, physical, numerical, performance, or release requirements in [Qualify staged artifacts on every required runtime](https://github.com/rubixhacker/dyn4k/issues/43).
