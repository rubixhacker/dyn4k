# Full staged Native host consumer

The external project at `consumers/qualification/portable/full-native-host` resolves the staged core and facade target KLIBs through their Maven coordinates. It compiles the original common tests and the applicable Native `actual` source as friend modules. The project has no dependency on the engine projects. It runs 2,523 approved portable methods, 2,465 from core and 58 from facade.

The producer accepts these seven target/runtime families: Linux ARM64, Windows x64, macOS ARM64, iOS simulator ARM64, iOS simulator x64, tvOS simulator ARM64, and watchOS simulator ARM64. Each has minimum and current runtime roles and `debug-g` and `optimized-opt` modes, for 28 distinct lane IDs. A lane uses the exact approved manifest ID. The producer rejects a different target, runtime, role, or mode.

## Run one selected lane

Use a clean checkout at the candidate SHA. Stage the two target publications with the pinned build, then copy the Maven repository outside that checkout. Supply the independently measured SHA-256 values of both target KLIBs. Use JDK 21, Gradle 9.5.0, and Kotlin/Native 2.4.20. `JAVA_HOME`, `GRADLE_USER_HOME`, and `TMPDIR` must be explicit. Place `--output` on home backed storage. Each attempt needs a new output path; the producer refuses an occupied path and retains a failed attempt.

The independent runtime selection JSON contains the full lane ID, role, host system, machine, and exact observed host OS version. Linux ARM64 also names glibc. A simulator selection also names its UDID, CoreSimulator runtime identifier, and guest OS version. An example current iOS simulator selection is:

```json
{
  "lane": "iosSimulatorArm64:iOS simulator ARM64:current:debug-g",
  "role": "current",
  "system": "Darwin",
  "machine": "arm64",
  "os_version": "26.4",
  "simulator_udid": "12345678-1234-1234-1234-123456789abc",
  "simulator_runtime": "com.apple.CoreSimulator.SimRuntime.iOS-26-0",
  "guest_version": "26.0"
}
```

Replace every example value with the selected live host and device identity. The producer compares the selection with OS and `simctl` observations. It boots a selected simulator if needed, waits for boot, executes a guest process, binds the Gradle Native test task to the UDID, and checks the same device again after the run. The selected test task must execute and emit its original XML. A link alone, a different target's test task, a shutdown device, or missing original XML cannot pass. The Gradle test task is the simulator test host; it runs the selected executable on the bound simulator.

```sh
export JAVA_HOME=/path/to/pinned/jdk21
export GRADLE_USER_HOME="$HOME/.gradle"
export TMPDIR="$HOME/dyn4k-native-tmp"
python3 tools/qualification/full_native_host_consumer.py run \
  --repository "$CHECKOUT" --candidate-sha "$CANDIDATE_SHA" \
  --lane "$LANE" --staging "$STAGED_MAVEN_COPY" \
  --output "$HOME/dyn4k-native-evidence/$ATTEMPT" \
  --gradle "$GRADLE_9_5_0" --native-home "$KONAN_2_4_20_HOME" \
  --runtime-selection "$INDEPENDENT_RUNTIME_SELECTION_JSON" \
  --expected-core-sha256 "$AUDITED_CORE_KLIB_SHA256" \
  --expected-facade-sha256 "$AUDITED_FACADE_KLIB_SHA256"
```

`debug-g` compiles the test with `-g` and uses `debugTest`. `optimized-opt` compiles with `-opt`, links `releaseTest`, and redirects the selected Native test task to that release executable. The archive retains the mode init script, compiler flag output, link and test task output, original XML, normalized XML with manifest IDs, method order, provider graph, resolved KLIB copies, program bytes, process command and PID, source inventory, host observations, and simulator guest process records. A successful build message without all 2,523 original method outcomes fails capture.

## Verify a relocated archive

Copy the entire raw directory without changing file modification times. Select the archive digest, source checkout, core and facade KLIB hashes, runtime selection, and toolchain values independently. The trusted toolchain JSON must match the producer's exact JDK 21 executable path, version line, and SHA-256; Gradle 9.5.0 executable path and SHA-256; Gradle user home; KGP 2.4.20; and Kotlin/Native 2.4.20 home, version, executable SHA-256, and compiler JAR SHA-256. Do not derive expected values only from the transported receipt.

```sh
python3 tools/qualification/full_native_host_consumer.py verify \
  --repository "$EXACT_CANDIDATE_CHECKOUT" --candidate-sha "$CANDIDATE_SHA" \
  --lane "$LANE" --archive "$RELOCATED_RAW_DIRECTORY" \
  --expected-archive-digest "$INDEPENDENT_ARCHIVE_SHA256" \
  --runtime-selection "$INDEPENDENT_RUNTIME_SELECTION_JSON" \
  --trusted-toolchain "$INDEPENDENT_TOOLCHAIN_JSON" \
  --expected-core-sha256 "$AUDITED_CORE_KLIB_SHA256" \
  --expected-facade-sha256 "$AUDITED_FACADE_KLIB_SHA256"
```

The public verifier authenticates the complete archive and source tree, checks the exact Gradle command and process window, and compares the original XML order and outcomes with the normalized IDs. It checks both Maven provider graphs, resolved KLIB bytes and origins, compiler flags, executable bytes and mode, and host identity. It does not turn a current runtime into a minimum runtime. It does not run numerical, physical, performance, publication, or global qualification gates.

The optional [host workflow](../../.github/workflows/full-staged-native-host.yml) can dispatch one route on available Mac, Windows, or Linux ARM64 labels. It retains failed attempts. Its hosted labels do not supply old minimum OS versions merely because the matrix includes minimum IDs. The workflow has not been pushed or executed from this branch. A public verifier pass still needs the separately owned signed adapter and central independent gate integration before an assembled lane can pass.
