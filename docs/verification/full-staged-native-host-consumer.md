# Full staged Native host consumer

The external project at `consumers/qualification/portable/full-native-host` resolves the staged core and facade target KLIBs through their Maven coordinates. It compiles the original common tests and the applicable Native `actual` source as friend modules. The project has no dependency on the engine projects. It runs 2,523 approved portable methods, 2,465 from core and 58 from facade.

The producer accepts these seven target/runtime families: Linux ARM64, Windows x64, macOS ARM64, iOS simulator ARM64, iOS simulator x64, tvOS simulator ARM64, and watchOS simulator ARM64. Each has minimum and current runtime roles and `debug-g` and `optimized-opt` modes, for 28 distinct lane IDs. A lane uses the exact approved manifest ID. The producer rejects a different target, runtime, role, or mode.

## Run one selected lane

Use a clean checkout at the candidate SHA. Stage the two target publications with the pinned build, then copy the Maven repository outside that checkout. Supply separately audited SHA-256 values of both target KLIBs for a qualification attempt. Use JDK 21, Gradle 9.5.0, and Kotlin/Native 2.4.20. `JAVA_HOME`, `GRADLE_USER_HOME`, and `TMPDIR` must be explicit. Place `--output` on home backed storage. Each attempt needs a new output path; the producer refuses an occupied path and retains a failed attempt.

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

Replace every example value with the selected live host and device identity. Windows selection must include `windows_product_type: "client"` and the exact `windows_product_name`; a Server product fails the client lane. The producer compares the selection with OS and `simctl` observations. It boots a selected simulator if needed, waits for boot, binds the Gradle Native test task to the UDID, and checks the same device again after the run. Process sampling must observe the selected test image and its bytes while it runs. Simulator evidence additionally requires the observed `simctl spawn` command to name the selected UDID and executable path. If sampling misses either process, the attempt fails closed. The selected test task must execute and emit its original XML.

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

`debug-g` compiles the test with `-g` and uses `debugTest`. `optimized-opt` compiles with `-opt`, links `releaseTest`, and redirects the selected Native test task to that release executable. The archive retains the mode init script, compiler flags, Gradle's raw Native test events in `stdout.txt`, original XML, normalized XML with manifest IDs, deterministic XML report traversal, compile provider graph, resolved KLIB copies, program bytes, sampled process image and hash, source inventory, host observations, and simulator spawn records. The graph labels the Native runtime as an executable launch; it has no separately resolved KLIB runtime configuration. The report traversal sorts XML filenames and retains testcase order within each file. It does not assert global chronological method execution order. A successful build message without all 2,523 original method outcomes fails capture.

## Verify a relocated archive

Transport the raw directory through the producer's `pack` and `unpack` commands. The tar contains a timestamp manifest; `unpack` restores exact nanosecond mtimes. Select the archive digest, source checkout, core and facade KLIB hashes, runtime selection, and toolchain values independently. The trusted toolchain JSON must match the producer's exact JDK 21 executable path, version line, and SHA-256; Gradle 9.5.0 executable path and SHA-256; Gradle user home; KGP 2.4.20; and Kotlin/Native 2.4.20 home, version, executable SHA-256, and compiler JAR SHA-256. Do not derive expected values only from the transported receipt or workflow staging copy.

```sh
python3 tools/qualification/full_native_host_consumer.py pack \
  --archive "$RAW_DIRECTORY" --output "$HOME/dyn4k-native-evidence/raw.tar"
python3 tools/qualification/full_native_host_consumer.py unpack \
  --transport "$HOME/dyn4k-native-evidence/raw.tar" \
  --output "$HOME/dyn4k-native-evidence/relocated-raw"
```

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

The public verifier first copies the archive into isolated regular files and rejects hardlinks, symlinks, unsafe paths, and path changes during copying. It authenticates the archive and source tree, checks the exact Gradle command and process window, and compares the deterministic XML report traversal and outcomes with normalized IDs. It checks both compile Maven provider graphs, resolved KLIB bytes and origins, compiler flags, sampled executable process bytes and mode, and host identity. It does not turn a current runtime into a minimum runtime. It does not run numerical, physical, performance, publication, or global qualification gates.

The optional [host workflow](../../.github/workflows/full-staged-native-host.yml) can dispatch one route on available Mac, Windows, or Linux ARM64 labels. It uploads a tar of each existing raw attempt and retains failed attempts. A blank runtime selection probes the observed host; the current hosted Linux ARM64 label does not satisfy the Linux minimum kernel and glibc floors merely because `minimum` was selected. The `windows-2025` runner is a Server probe, not a Windows client qualification host. Workflow KLIB hashes are computed from its own staging copy and are recorded as `staging-self`; they show internal consistency only. Signed intake requires separately audited expected target KLIB hashes. A public verifier pass still needs the separately owned signed adapter and central independent gate integration before an assembled lane can pass.
