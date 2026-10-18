# Installed Android runtime diagnostic

This harness builds separate baseline and candidate apps from the pinned dyn4j 6.0.0 JAR and staged `dyn4k-core-android` and `dyn4k-android` AARs. It installs each app and its instrumentation APK. It executes the unchanged Java consumer sources against both providers. The candidate APK also runs the compiled common portable test classes and a Kotlin shared-identity consumer. Debug and R8 release APKs are separate runs.

The full-corpus release app keeps the engine, facade, and Kotlin packages and members. Its R8 result is a pipeline diagnostic, not an optimized engine gate. The separate `optimized` app has a narrow Activity entry rule. Its production code calls the staged AARs for vector, body, World, and Java subclass callbacks. Its installed test checks a result written by the app process. Mapping, usage, and DEX evidence must show that R8 transformed the consumer and engine path.

The API 36.1 x86_64 emulator is a diagnostic host. It is outside the approved minimum and current Android runtime selections. A diagnostic pass cannot qualify an Android matrix lane. The API 37 `google_apis` revision 6 image failed boot with `Invalid feature flag: android.security.aapm_feature_disable_insecure_wifi_autojoin`. A separate API 37 Play Store revision 6 AVD booted with 4 GB RAM. Its installed app cases are recorded separately. API 21 attempts use official `google_apis` x86_64 or x86 revision 32 images. Each image and graphics mode requires its own boot, fingerprint, and ABI receipt before installed cases can count. Physical devices and native ARM ABI lanes stay **UNPASSED** without their own execution.

## Build inputs and run

Use JDK 21, the pinned Android SDK, and the repository wrapper. Stage both root metadata publications and Android AAR publications. The root metadata is required to resolve the Android variants by the published `dyn4k` and `dyn4k-core` coordinates.

```sh
export JAVA_HOME=/var/home/stewart/.gradle/jdks/jetbrains_s_r_o_-21-amd64-linux.2
export ANDROID_HOME=/var/home/stewart/Android/Sdk
export ANDROID_SDK_ROOT="$ANDROID_HOME"
./gradlew --no-daemon :dyn4k-core:publishKotlinMultiplatformPublicationToStagingRepository :dyn4k:publishKotlinMultiplatformPublicationToStagingRepository :dyn4k-core:publishAndroidPublicationToStagingRepository :dyn4k:publishAndroidPublicationToStagingRepository :dyn4k-core:jvmTest :dyn4k:jvmTest
python3 tools/android-runtime/prepare.py --output /tmp/dyn4k-android-preflight/prepared.json
python3 -m unittest discover -s tools/android-runtime -p 'test_*.py' -v
./gradlew -p consumers/android-runtime --no-daemon :app:assembleDebug :app:assembleAndroidTest -PpreparedManifest=/tmp/dyn4k-android-preflight/prepared.json -PstagingRepository="$PWD/build/staging-repository" -PportableSuiteJar="$PWD/consumers/android-runtime/app/build/generated/portable-suite.jar"
```

For the release instrumentation APK, run the same app build with `-PruntimeTestBuildType=release`. Pass the same prepared manifest to both builds. The Android test compile tasks compare each original, generated copy, and manifest SHA-256 before assembly. `run.py` repeats this check before installation and before it accepts each installed run. Commit the harness source before final execution. `run.py` requires a clean source checkout at the prepared commit.

Build the optimized app and its instrumentation APK using the same manifest and staged repository, with `:optimized:assembleDebug :optimized:assembleDebugAndroidTest` for debug and `:optimized:assembleRelease :optimized:assembleReleaseAndroidTest -PruntimeTestBuildType=release` for R8. Save the output of `:optimized:dependencies --configuration releaseRuntimeClasspath` after preparation. Pass that file as `--provider-graph` to `run_optimized.py`. The optimized Gradle compile tasks and runner check the same original and generated Java copies against the prepared manifest. The runner requires exact staged AAR checksums and a clean candidate commit. It snapshots and installs the exact APKs, retains provider graph, mapping, usage, configuration, and DEX bytecode with hashes, then records installed package, raw instrumentation, and logcat. It rejects empty or failed installed runs and missing R8 evidence. The optimized-consumer policy tokenizes the six R8 class, member, and name keep families, including same-line `-if` consequents and directives after a complete `}` block. It rejects incomplete or ambiguous class/member blocks before accepting a receipt. It rejects protected package wildcards, global class blankets, every negated class selector, and unconstrained global member name or type wildcards. The member check covers fields and methods, including `%` and `***` types. Only the two exact generated enum member signatures, `public static **[] values()` and `public static ** valueOf(java.lang.String)`, receive the wildcard type exception; user overloads do not. Known passive metadata and path options include `-keepparameternames`, `-keepattributes`, `-keepdirectories`, and `-keeppackagenames`; unknown effective `-keep` forms fail closed. The screen ignores comments and accepts exact class keeps, such as the Activity entry rule. A retained receipt from an earlier source commit is evidence for that earlier commit only.

The task AVD uses an isolated ADB server on port 5038 and emulator port 5558. Start it with the existing `/tmp/dyn4k-android-preflight/launch-container.sh` route recorded in `/tmp/dyn4k-android-preflight-result.md`. Do not copy task ADB keys into a report. After `sys.boot_completed=1`:

```sh
python3 tools/android-runtime/run.py --prepared /tmp/dyn4k-android-preflight/prepared.json --build-type debug --output /tmp/dyn4k-android-preflight/runtime-evidence/debug
python3 tools/android-runtime/run.py --prepared /tmp/dyn4k-android-preflight/prepared.json --build-type release --output /tmp/dyn4k-android-preflight/runtime-evidence/release
```

For the API 37 Play Store image, pass `--expected-api 37` and use distinct output directories. The emulator must have at least 4 GB RAM. The two images have different fingerprints; retain both raw boot outcomes. The API 37 `google_apis` image's failed boot must not be replaced by the Play Store result.

For the API 21 minimum image, pass `--expected-api 21` and its primary ABI with `--expected-abi` to both runners, use separate output directories, and retain the image package revision, AVD configuration, fingerprint, ABI, emulator version, and SDK package versions. An x86_64 guest does not execute ARM code. A failed boot or variant stays unpassed with its raw logs.

The runner records installed package details, runtime identity, process, raw instrumentation, logcat, artifact hashes, manifest hash, source commit, and cases. It compares portable case identities with the raw JVM XML from the same source. It rejects missing, duplicate, unexpected, skipped, failed, or empty cases. A changed AAR, generated Java copy, or source checkout stops execution. Each flavor and build has its own result file. A failed candidate remains a failure even if the baseline passes.

The portable classes are compiled from the repository's common test sources. Their packaging JAR is test code only. The installed candidate app resolves the staged Android AARs, and its production APK has no baseline JAR. The prepared manifest records each original-to-generated Java source path and SHA-256. Extra generated Java files fail verification. The baseline app resolves only pinned dyn4j 6.0.0.
