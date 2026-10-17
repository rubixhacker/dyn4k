# Android Native staged consumer

This diagnostic runs a Kotlin/Native `androidNativeX64` executable against the published `dyn4k-core` and `dyn4k` KLIBs. The executable creates two bodies, steps a World, and checks contact callbacks. It uses the facade `Body`, `Circle`, and `MassType` aliases with the core World. Each successful process prints six named assertions and one final count.

The consumer is an independent Gradle build in `consumers/android-native-runtime/`. It resolves the `io.github.rubixhacker` group exclusively from staging. Maven Central supplies the Kotlin/Native compiler bundle. Root build files and the Android JVM/ART harness do not register or build it. Kotlin Gradle Plugin 2.4.20 creates separate debug and release executable tasks. Release is the optimized Native build. See [Kotlin's native binaries documentation](https://kotlinlang.org/docs/multiplatform-build-native-binaries.html).

## Build and run

Use JDK 21 and the Android SDK. From a clean committed checkout, stage both root metadata publications and both x64 target publications:

```sh
export JAVA_HOME=/tmp/dyn4k-tools/jdk21
export ANDROID_HOME=/home/stewart/Android/Sdk
./gradlew --no-daemon :dyn4k-core:publishKotlinMultiplatformPublicationToStagingRepository :dyn4k:publishKotlinMultiplatformPublicationToStagingRepository :dyn4k-core:publishAndroidNativeX64PublicationToStagingRepository :dyn4k:publishAndroidNativeX64PublicationToStagingRepository
./gradlew -p consumers/android-native-runtime --no-daemon -PstagingRepository="$PWD/build/staging-repository" linkDebugExecutableAndroidNativeX64 linkReleaseExecutableAndroidNativeX64
./gradlew -p consumers/android-native-runtime --no-daemon -PstagingRepository="$PWD/build/staging-repository" dependencies --configuration androidNativeX64CompileKlibraries > /tmp/dyn4k-android-native-dependencies.txt
```

Check active ADB devices and the task container before starting an emulator. Use only the existing `dyn4k_api37_play_x64` AVD, ADB port 5038, and emulator port 5558. The Android JVM harness documents its isolated container launch in `docs/verification/android-runtime.md`. The runner checks the AVD name, primary ABI, API, boot state, and fingerprint before pushing a binary. It checks the deployed binary hash before execution. The guest's advertised ARM translation does not count as ARM execution.

```sh
python3 tools/android-native-runtime/run.py --source-root "$PWD" --staging "$PWD/build/staging-repository" --dependency-report /tmp/dyn4k-android-native-dependencies.txt --executable "$PWD/consumers/android-native-runtime/build/bin/androidNativeX64/debugExecutable/journey.kexe" --variant debug --output /tmp/dyn4k-android-native-runtime-evidence/debug
python3 tools/android-native-runtime/run.py --source-root "$PWD" --staging "$PWD/build/staging-repository" --dependency-report /tmp/dyn4k-android-native-dependencies.txt --executable "$PWD/consumers/android-native-runtime/build/bin/androidNativeX64/releaseExecutable/journey.kexe" --variant optimized --output /tmp/dyn4k-android-native-runtime-evidence/optimized
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tools/android-native-runtime -p 'test_*.py' -v
```

Each result records the exact committed source SHA and tree, staged KLIB and executable hashes, ELF ABI, dependency graph hash, guest identity, deployment hash, process command, raw stdout and stderr, exit status, and named assertion count. The validator rejects missing files, hash or ABI changes, absent output, missing assertions, and a nonzero exit. A failed or unavailable attempt is `UNPASSED`. A successful run is `DIAGNOSTIC_PASSED` for this six-assertion x86_64 journey only. It does not establish the full portable suite, API 21 minimum, physical Android, or any other ABI.

| Target | Current evidence boundary |
| --- | --- |
| Android Native Arm32 | No executed Arm32 process; unpassed. |
| Android Native Arm64 | No executed Arm64 process; unpassed. |
| Android Native X86 | No executed x86 process; unpassed. |
| Android Native X64 | This bounded external consumer requires an actual isolated x86_64 guest result for each Native build. |
