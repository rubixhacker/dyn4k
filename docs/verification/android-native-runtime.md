# Android Native x64 runtime qualification

The full gate links the source-derived common test corpus for `dyn4k-core` and `dyn4k` in debug and optimized Kotlin/Native modes. It executes all four test ELFs on the isolated API 37 x86_64 guest. It also executes the staged external consumer in both modes. The committed manifest lists 2,465 core and 58 facade common cases per build. The gate runs both modules in both modes, for 5,046 common executions in total. It also requires 12 staged-consumer assertions across the two modes. Android Native does not run the three JVM-only facade cases. Each expected method must appear once. The gate rejects missing, extra, duplicate, failed, errored, ignored, or skipped methods.

`tools/android-native-runtime/full.py` checks the committed source tree, source-derived manifest, reviewed mapping, KLIBs, six ELFs, dependency graphs, Gradle task logs, tool images, guest image and fingerprint, remote executable hashes, and raw process outputs. Its `run` action rebuilds at a clean committed head before deploying any ELF. The process output must contain every manifest method exactly once. The separate `adverse.py` command mutates a complete receipt and requires every mutation to fail replay. Offline `verify` returns `CONSISTENCY_ONLY`; the `RUNTIME_PASSED` status is issued only by the live runner after guest execution.

```sh
export JAVA_HOME=/tmp/dyn4k-tools/jdk21
export ANDROID_HOME=/home/stewart/Android/Sdk
./gradlew --no-daemon --max-workers=2 --console=plain :dyn4k-core:publishKotlinMultiplatformPublicationToStagingRepository :dyn4k:publishKotlinMultiplatformPublicationToStagingRepository :dyn4k-core:publishAndroidNativeX64PublicationToStagingRepository :dyn4k:publishAndroidNativeX64PublicationToStagingRepository
./gradlew --no-daemon --max-workers=2 --console=plain :dyn4k-core:linkDebugTestAndroidNativeX64 :dyn4k-core:linkReleaseTestAndroidNativeX64 :dyn4k:linkDebugTestAndroidNativeX64 :dyn4k:linkReleaseTestAndroidNativeX64
./gradlew -p consumers/android-native-runtime --no-daemon --max-workers=2 --console=plain -PstagingRepository="$PWD/build/staging-repository" linkDebugExecutableAndroidNativeX64 linkReleaseExecutableAndroidNativeX64
python3 tools/android-native-runtime/full.py pin --source-root "$PWD" --output /tmp/dyn4k-android-native-full-pins-proposal.json
```

Review and commit the proposed hashes as `tools/android-native-runtime/full-pins.json`. Start only the task AVD `dyn4k_api37_play_x64` on ADB port 5038 and emulator port 5558. Then run from the clean committed checkout:

```sh
python3 tools/android-native-runtime/full.py run --source-root "$PWD" --output /tmp/dyn4k-android-native-full-evidence
python3 tools/android-native-runtime/full.py verify --source-root "$PWD" --output /tmp/dyn4k-android-native-full-evidence/result.json
python3 tools/android-native-runtime/adverse.py --source-root "$PWD" --receipt /tmp/dyn4k-android-native-full-evidence/result.json
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tools/android-native-runtime -p 'test_*.py' -v
```

The raw receipt has a separate deployment, test listing, process stdout, process stderr, and exit status for each of the six ELFs. The build and dependency command outputs remain separate files with SHA-256 hashes. Rebuild and repin after any engine, test, Gradle, compiler, or consumer change. A changed pin requires review before a new runtime claim.

## Historical staged-consumer diagnostic

This diagnostic runs a Kotlin/Native `androidNativeX64` executable against the published `dyn4k-core` and `dyn4k` KLIBs. The executable creates two bodies, steps a World, and checks contact callbacks. It uses the facade `Body`, `Circle`, and `MassType` aliases with the core World. Each successful process prints six named assertions and one final count.

The consumer is an independent Gradle build in `consumers/android-native-runtime/`. It resolves the `io.github.rubixhacker` group exclusively from staging. Maven Central supplies the Kotlin/Native compiler bundle. Root build files and the Android JVM/ART harness do not register or build it. Kotlin Gradle Plugin 2.4.20 creates separate debug and release executable tasks. Release is the optimized Native build. See [Kotlin's native binaries documentation](https://kotlinlang.org/docs/multiplatform-build-native-binaries.html).

## Build and run

Use JDK 21 and the Android SDK. From a clean committed checkout, stage both root metadata publications and both x64 target publications. Keep the raw build logs outside the checkout. The stage and link commands must succeed before running the consumer:

```sh
export JAVA_HOME=/tmp/dyn4k-tools/jdk21
export ANDROID_HOME=/home/stewart/Android/Sdk
set -o pipefail
./gradlew --no-daemon :dyn4k-core:publishKotlinMultiplatformPublicationToStagingRepository :dyn4k:publishKotlinMultiplatformPublicationToStagingRepository :dyn4k-core:publishAndroidNativeX64PublicationToStagingRepository :dyn4k:publishAndroidNativeX64PublicationToStagingRepository 2>&1 | tee /tmp/dyn4k-android-native-stage.log
./gradlew -p consumers/android-native-runtime --no-daemon -PstagingRepository="$PWD/build/staging-repository" linkDebugExecutableAndroidNativeX64 linkReleaseExecutableAndroidNativeX64 2>&1 | tee /tmp/dyn4k-android-native-link.log
```

Check active ADB devices and the task container before starting an emulator. Use only the existing `dyn4k_api37_play_x64` AVD, ADB port 5038, and emulator port 5558. The Android JVM harness documents its isolated container launch in `docs/verification/android-runtime.md`. The runner checks the AVD name, primary ABI, API, boot state, and fingerprint before pushing a binary. It checks the deployed binary hash before execution. The guest's advertised ARM translation does not count as ARM execution.

```sh
python3 tools/android-native-runtime/run.py --source-root "$PWD" --staging "$PWD/build/staging-repository" --stage-log /tmp/dyn4k-android-native-stage.log --link-log /tmp/dyn4k-android-native-link.log --executable "$PWD/consumers/android-native-runtime/build/bin/androidNativeX64/debugExecutable/journey.kexe" --variant debug --output /tmp/dyn4k-android-native-runtime-evidence/debug
python3 tools/android-native-runtime/run.py --source-root "$PWD" --staging "$PWD/build/staging-repository" --stage-log /tmp/dyn4k-android-native-stage.log --link-log /tmp/dyn4k-android-native-link.log --executable "$PWD/consumers/android-native-runtime/build/bin/androidNativeX64/releaseExecutable/journey.kexe" --variant optimized --output /tmp/dyn4k-android-native-runtime-evidence/optimized
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tools/android-native-runtime -p 'test_*.py' -v
```

The runner captures the native compile dependency graph from the external consumer build itself. It requires the two staged root publications, their x64 publications, and Kotlin stdlib; any other provider or project dependency fails the run. Each result records the exact committed source SHA and Git tree, build log and graph hashes, staged KLIB and executable hashes, ELF ABI, trusted SDK ADB path and image hash, independently queried guest properties, deployed executable hash, process command, raw stdout and stderr, exit status, and six named assertions.

The committed `tools/android-native-runtime/pins.json` records output hashes from the earlier staged build at source `5b1ac96e2afdc9324e19f23b693dec8ef013a5f6`. It remains the historical diagnostic pin file. The earlier `f56683be` guest receipts remain `CONSISTENCY_ONLY` when independently replayed. They do not qualify final engine bytes. The full gate uses its separate committed `full-pins.json` and new exact-head guest receipts.

An offline receipt check can establish only `CONSISTENCY_ONLY`: files and receipt fields can be forged together, including guest queries, logs, and stdout. It never returns a runtime pass. `DIAGNOSTIC_PASSED` is issued only by this runner after it invokes the trusted SDK ADB image on the isolated guest, verifies the deployment bytes, and observes a zero exit with the six assertions. The fixed ADB hash and expected API 37 fingerprint are checked in both paths. A failed or unavailable attempt is `UNPASSED`. This six-assertion x86_64 journey does not establish the full portable suite, API 21 minimum, physical Android, or any other ABI.

| Target | Current evidence boundary |
| --- | --- |
| Android Native Arm32 | No executed Arm32 process; unpassed. |
| Android Native Arm64 | No executed Arm64 process; unpassed. |
| Android Native X86 | No executed x86 process; unpassed. |
| Android Native X64 | Full debug and optimized common corpus plus staged consumer require actual isolated x86_64 guest receipts at one committed source. API 21 and physical-device evidence remain separate. |
