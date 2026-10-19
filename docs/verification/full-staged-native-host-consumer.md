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
  "os_version": "26.5.1",
  "simulator_udid": "12345678-1234-1234-1234-123456789abc",
  "simulator_runtime": "com.apple.CoreSimulator.SimRuntime.iOS-26-5",
  "guest_version": "26.5"
}
```

Replace every example value with the selected live host and device identity. The [later explicit Apple support decision](https://github.com/rubixhacker/dyn4k/issues/32#issuecomment-6259967473) approved Xcode 26.5 in place of the earlier 26.4.1 pin; historical 26.4.1 captures remain historical. This toolchain decision does not change the minimum OS floors. Windows selection must include `windows_product_type: "client"` and the exact `windows_product_name`; a Server product fails the client lane. The producer compares the selection with OS and `simctl` observations. It boots a selected simulator if needed, waits for boot, binds the Gradle Native test task to the UDID, and checks the same device again after the run. Process sampling must observe the selected test image and its bytes while it runs. Simulator evidence additionally requires the observed `simctl spawn` command to name the selected UDID and executable path. If sampling misses either process, the attempt fails closed. The selected test task must execute and emit its original XML.

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

The public verifier first copies the archive into isolated regular files and rejects hardlinks, symlinks, unsafe paths, and path changes during copying. `unpack` requires a newly created output root and opens every output parent without following links. On Windows, the route accepts only local absolute drive paths. It opens each component relative to a pinned directory handle with [`NtCreateFile`](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/ntifs/nf-ntcreatefile), opens reparse points themselves, and rejects them and multiply linked files through handle metadata. The output root must be new. Windows transport names reject drive aliases, alternate streams, reserved names, case aliases, and parent escapes. Files retain bytes, supported read-only mode, and exact 100 ns Windows timestamps. A timestamp outside that precision or the FILETIME range is rejected before the output root is created. Windows `unpack` holds each new file handle until all writes succeed. If a write fails, cleanup marks only held created objects for deletion and preserves the original error if closing a handle fails. Replacement content is retained, and an occupied output root blocks same-path retry. When cleanup succeeds, the same output path can be retried. The Windows API round-trip test requires a real Windows host and remains unrun locally; no Windows client lane is qualified by the Linux checks. The verifier authenticates the archive and source tree, checks the exact Gradle command and process window, and compares the deterministic XML report traversal and outcomes with normalized IDs. It checks both compile Maven provider graphs, resolved KLIB bytes and origins, compiler flags, sampled executable process bytes and mode, and host identity. It does not turn a current runtime into a minimum runtime. It does not run numerical, physical, performance, publication, or global qualification gates.

## Linux ARM64 cross build and runtime

Kotlin/Native 2.4.20 accepts `linux_arm64` as a target from its Linux x86_64 compiler host. It does not accept Linux ARM64 as a compiler host. The split route first stages and resolves the two exact Linux ARM64 KLIBs on Linux x86_64, compiles the original test sources with the selected mode, and links both AArch64 ELF64 test executables. Its result is `COMPILED_ONLY`. An ARM64 guest then runs those transferred bytes directly. The raw TeamCity event stream is the original Native test output; `runtime/method-order.json` is derived from its ordered start and finish events. This route does not synthesize an original Gradle XML report on the guest.

```sh
python3 tools/qualification/full_native_host_consumer.py cross-build \
  --repository "$CHECKOUT" --candidate-sha "$CANDIDATE_SHA" --lane "$LANE" \
  --staging "$STAGED_MAVEN_COPY" --output "$HOME/dyn4k-native-evidence/build-raw" \
  --gradle "$GRADLE_9_5_0" --native-home "$KONAN_2_4_20_HOME" \
  --expected-core-sha256 "$AUDITED_CORE_KLIB_SHA256" \
  --expected-facade-sha256 "$AUDITED_FACADE_KLIB_SHA256"
python3 tools/qualification/full_native_host_consumer.py pack \
  --archive "$HOME/dyn4k-native-evidence/build-raw" \
  --output "$HOME/dyn4k-native-evidence/build-raw.tar"
```

Record both the build archive digest from `cross-build` and the transport tar SHA-256. Transfer the tar through an authenticated channel. On the ARM64 host, check that tar digest, unpack it into a new home-backed path, and independently select the runtime identity. `probe-arm-image` first launches each transferred image with `--ktest_list_tests`. Its `PROBED_NOT_RUN` result checks registration of the 2,523 method IDs and records guest PID, exit code, transferred image hash, host identity, and original listing output; it executes no test methods. The full run then executes both images and samples their live `/proc` image bytes:

```sh
python3 tools/qualification/full_native_host_consumer.py unpack \
  --transport "$TRANSFERRED_BUILD_TAR" --output "$HOME/dyn4k-native-evidence/cross-build"
python3 tools/qualification/full_native_host_consumer.py probe-arm-image \
  --repository "$CHECKOUT" --candidate-sha "$CANDIDATE_SHA" --lane "$LANE" \
  --build-archive "$HOME/dyn4k-native-evidence/cross-build" \
  --expected-build-archive-digest "$BUILD_ARCHIVE_SHA256" \
  --output "$HOME/dyn4k-native-evidence/probe" \
  --runtime-selection "$INDEPENDENT_RUNTIME_SELECTION_JSON" \
  --expected-core-sha256 "$AUDITED_CORE_KLIB_SHA256" \
  --expected-facade-sha256 "$AUDITED_FACADE_KLIB_SHA256"
python3 tools/qualification/full_native_host_consumer.py cross-run \
  --repository "$CHECKOUT" --candidate-sha "$CANDIDATE_SHA" --lane "$LANE" \
  --build-archive "$HOME/dyn4k-native-evidence/cross-build" \
  --expected-build-archive-digest "$BUILD_ARCHIVE_SHA256" \
  --output "$HOME/dyn4k-native-evidence/runtime-raw" \
  --runtime-selection "$INDEPENDENT_RUNTIME_SELECTION_JSON" \
  --expected-core-sha256 "$AUDITED_CORE_KLIB_SHA256" \
  --expected-facade-sha256 "$AUDITED_FACADE_KLIB_SHA256"
```

The ARM64 receipt retains both original test streams, process PID/parent PID, `/proc/PID/exe` path and byte hash observed while each process existed, the two executable copies, source and staged KLIB inventories, provider graph, compiler flags, build host, and guest kernel/glibc identity. A failed or unobserved process remains a failed raw attempt. The public replay command checks a relocated runtime archive and the nested build archive against independently selected archive digests, target KLIB hashes, runtime selection, exact candidate source, and build toolchain:

```sh
python3 tools/qualification/full_native_host_consumer.py verify-cross-run \
  --repository "$EXACT_CANDIDATE_CHECKOUT" --candidate-sha "$CANDIDATE_SHA" \
  --lane "$LANE" --archive "$RELOCATED_RUNTIME_RAW" \
  --expected-archive-digest "$RUNTIME_ARCHIVE_SHA256" \
  --expected-build-archive-digest "$BUILD_ARCHIVE_SHA256" \
  --runtime-selection "$INDEPENDENT_RUNTIME_SELECTION_JSON" \
  --trusted-build-toolchain "$INDEPENDENT_BUILD_TOOLCHAIN_JSON" \
  --expected-core-sha256 "$AUDITED_CORE_KLIB_SHA256" \
  --expected-facade-sha256 "$AUDITED_FACADE_KLIB_SHA256"
```

The optional [host workflow](../../.github/workflows/full-staged-native-host.yml) uses only static Ubuntu x64, Ubuntu ARM64, and Windows Server runner labels. It cannot dispatch an Apple target. Apple host and simulator lanes use the separately supplied local Mac after exact reviewed source integration and serialized build allocation. The workflow uploads separate build and runtime tar archives, retaining partial failed attempts and staging logs. Its same-run artifact handoff authenticates the transferred tar SHA-256 against the x64 build job output. A blank runtime selection probes the observed ARM64 host. The earlier [four-job hosted attempt](https://github.com/rubixhacker/dyn4k/actions/runs/39202914720) stopped at unsupported `linux-aarch64` compiler-host selection before method execution; it did not test ARM64 runtime availability. The observed current runner kernel 6.17 and glibc 2.39 cannot qualify the approved minimum kernel 4.9/glibc 2.25 family. The `windows-2025` runner is a Server probe, not a Windows client qualification host. Workflow KLIB hashes are computed from its own staging copy and are recorded as `staging-self`; they show internal consistency only. Signed intake requires separately audited expected target KLIB hashes. A public verifier pass still needs the separately owned signed adapter and central independent gate integration before an assembled lane can pass.
