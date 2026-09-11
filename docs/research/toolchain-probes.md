# Selected toolchain and consumer probes

Research snapshot: 2026-09-11 UTC (2026-09-10 America/Chicago). This is the evidence artifact for [Probe the selected toolchain and unresolved consumer floors](https://github.com/rubixhacker/dyn4k/issues/11), supporting [Define support and verification for every target](https://github.com/rubixhacker/dyn4k/issues/6). It does not ratify consumer floors or demonstrate a physics implementation.

## Contract and interpretation

Retain Kotlin/KGP 2.4.20, Gradle 9.5.0, build JDK 21, AGP 9.3.1 and Xcode 26.4.1. All 21 non-deprecated targets remain in scope, including experimental targets. `watchosArm32` is excluded by the approved policy; `watchosDeviceArm64` requires watchOS 26, independently of its compiler deployment default.

Each required runtime lane needs the complete portable correctness suite in debug and optimized configurations, at minimum and current runtime versions, plus an external consumer of staged release artifacts. These probes have no full physics suite. A successful scalar/vector probe is compiler/consumer evidence only. Unsupported or inaccessible runtime combinations remain gaps, never passing lanes.

“Configured floor” means a compiler/linker setting. “Feature floor” means the first identified runtime providing a required feature, possibly behind flags. “Observed” means the retained probe actually executed. None alone means the complete library is supported. Current versions below are dated candidates, to be refreshed and pinned for the eventual release candidate.

## Evidence assets

Observed successes: Java8 and Java26 external consumers with requested/provided JVM attribute8; Android API21 AAR and debug/R8-release APK builds; Linux x64 execution and ARM64 QEMU execution in debug/optimized modes; selected Node and Wasmtime consumers in development/optimized production modes. All are throwaway probe results. Android device, Apple, Windows, browser and old-kernel runtime evidence is absent.

- [JVM and Android JVM](probes-jvm-android.md): publication metadata, Java consumer and Android plugin probes.
- [Native](probes-native.md): four Android Native floors, Linux ABI inspection, Xcode patch comparison and Apple harness constraints.
- [Web](probes-web.md): explicit JS/Wasm settings and separate Node/Wasmtime feature and execution checks.
- [Infrastructure transcript](../../probes/toolchain/evidence/infra.txt), [Android images](../../probes/toolchain/evidence/android-images.txt), and [inventory command](../../probes/toolchain/infra.sh).

## Actual infrastructure

The inventory observed Linux x86-64, kernel `7.2.1-ogc4.1.fc44.x86_64`, glibc 2.43, default JDK 25.0.3 and Node 26.7.0. Default tools are inventory only; the probes obtain the selected build versions separately. Chrome for Testing 151.0.7922.34 exists locally but is not the current-browser candidate.

`adb devices -l` returned no devices. Installed images are API 33, 36.1 and 37.0, all x86-64. The two listed AVDs do not establish execution. No minimum-API21 image, ARM32/ARM64/x86 image, or physical Apple device was observed. The local MobAI device API refused the connection; no authenticated remote device session was established. The repository Actions runner API returned zero self-hosted runners. This says nothing about entitlement to GitHub-hosted capacity or machines outside the inspected configuration. No remote Mac, Intel simulator, Windows or ARM Linux execution was verified.

The missing harnesses are concrete: signed device test apps for iOS, tvOS and both watchOS ABIs; separate simulator apps with architecture checks; Android instrumentation/native launchers for each exact ABI; native Linux ARM64 and Windows x64 execution; old runtime images and exact browser-engine versions. Every harness must extract test count, failure details, exit status and consumer output, and reject a skipped or empty suite. Signing, provisioning and purchasing hardware are outside this task.

## Runtime matrix

The table has one row per required target/runtime family. Native target architectures are fixed; managed/web rows name the architecture used by these probes, not a new architecture exclusion. `Cross` means a supported Kotlin/Native compiler host can build/link that target; it does not mean the resulting program executes on the build host. Apple rows require macOS with the selected Xcode for final linking; web/JVM/Android JVM use the selected Gradle/JDK on a supported desktop host, with Android SDK added for Android.

| Target / runtime | Candidate minimum | Candidate current | Architecture | Build/link host | Required execution harness / evidence gap |
| --- | --- | --- | --- | --- | --- |
| jvm | Java 8 | Java 26.0.2.1 | JVM; probe x64 | Desktop | External unchanged Java source consumer plus full suite; minimum update/vendor must be pinned |
| android | See Android probe: configured SDK and harness floor differ | Android 17 / API37 | ART; probe packaging, x64 images | Desktop + SDK | Instrumented app; debug and optimized app consume the same single-variant KMP AAR |
| js / Chromium | Not established for explicit ES5/UMD output | 153.0.8010.36 | Engine; probe x64 | Desktop | Exact browser plus full suite; ES5 syntax alone supplies no numbered minimum |
| js / Firefox | Not established for explicit ES5/UMD output | 155.0.1; release-date caveat in web report | Engine | Desktop | Exact browser version and artifact provenance |
| js / WebKit | Not established for explicit ES5/UMD output | Safari 26.6 candidate | Engine | Desktop; Safari on Mac | Exact WebKit/Safari mapping, not an arbitrary Playwright revision |
| js / Node | See web probe; oldest observed is not a supported absolute minimum | Node 26.8.2 | Probe x64 | Desktop | Node full suite and consumer with exact module settings |
| wasmJs / Chromium | Chromium 119 documented | 153.0.8010.36 | Wasm32 / engine | Desktop | WasmGC + legacy EH; old and current real browser execution |
| wasmJs / Firefox | Firefox 120 documented | 155.0.1; release-date caveat in web report | Wasm32 / engine | Desktop | Same requirement, distinct engine lane |
| wasmJs / WebKit | Safari 18.2 documented | Safari 26.6 candidate | Wasm32 / engine | Desktop; Safari on Mac | Exact engine/version mapping and real execution |
| wasmJs / Node | Node 22.0.0 candidate, observed | Node 26.8.2 | Wasm32 / x64 engine probe | Desktop | WasmGC + legacy EH, full suite still absent |
| wasmWasi / Node | Node 24.15.0 candidate without exnref flag | Node 26.8.2 | Wasm32 / x64 engine probe | Desktop | WASI Preview1 + new EH; earlier flagged configurations need separate treatment |
| wasmWasi / Wasmtime | 37.0.0 with explicit feature flags candidate | 48.0.2 | Wasm32 / x64 engine probe | Desktop | GC, exceptions and function references; full suite still absent |
| macosArm64 | macOS 11 override candidate | macOS26.6.2, compatibility unverified | arm64 | Mac | Actual macOS11 and current execution; override has no runtime proof here |
| iosArm64 | iOS 15 | iOS26.6.2, compatibility unverified | arm64 | Mac | Signed physical iPhone/iPad harness |
| iosSimulatorArm64 | iOS 15 | iOS26.6.2, compatible runtime inventory needed | arm64 simulator | Apple Silicon Mac | Separate simulator suite and external consumer |
| iosX64 | iOS 15 | Latest compatible Intel simulator unresolved | x86-64 simulator | Mac; Intel runtime required | Xcode/SDK/Intel runtime intersection must be demonstrated; no substitution with ARM |
| tvosArm64 | tvOS 15 | tvOS26.6, compatibility unverified | arm64 | Mac | Signed physical Apple TV harness |
| tvosSimulatorArm64 | tvOS 15 | tvOS26.6, compatible runtime inventory needed | arm64 simulator | Apple Silicon Mac | Simulator suite and consumer |
| watchosArm64 | watchOS 8 | Latest compatible ILP32 device runtime unresolved | arm64_32 / ILP32 | Mac | Physical compatible watch; LP64 execution does not cover this target |
| watchosSimulatorArm64 | watchOS 8 | watchOS26.6, compatible runtime inventory needed | arm64 simulator | Apple Silicon Mac | Simulator suite and consumer |
| watchosDeviceArm64 | watchOS 26, approved | watchOS26.6, compatibility unverified | arm64 / LP64 | Mac | Supported physical watch; compiler's 9.0 deployment value is not a runtime floor |
| linuxX64 | glibc2.19 sysroot candidate; absolute kernel floor unresolved | Kernel7.2.4 + glibc2.44 candidate | x86-64 | Cross | Exact old/current rootfs plus kernel; sysroot execution is only bounded evidence |
| linuxArm64 | glibc2.25 sysroot candidate; absolute kernel floor unresolved | Kernel7.2.4 + glibc2.44 candidate | aarch64 | Cross | ARM64 harness; QEMU-user evidence cannot prove an old/native kernel |
| mingwX64 | Windows10, exact minimum build unresolved | Windows11 25H2 / 26200.9445 | x86-64 | Cross | Real Windows full suite and consumer, unavailable here |
| androidNativeArm32 | API21 configured | Latest exact-ABI Android runtime unresolved | armeabi-v7a | Cross + NDK dependencies | ARM32 Android process, native suite + instrumented consumer |
| androidNativeArm64 | API21 configured | Android17/API37 candidate | arm64-v8a | Cross + NDK dependencies | ARM64 Android process, native suite + instrumented consumer |
| androidNativeX86 | API21 configured | Latest exact-ABI Android runtime unresolved | x86 | Cross + NDK dependencies | 32-bit x86 image/device; modern x64 image cannot stand in |
| androidNativeX64 | API21 configured | Android17/API37 candidate | x86_64 | Cross + NDK dependencies | x64 Android process, native suite + instrumented consumer |

The 28 runtime rows expand 21 targets: browser and Node engines share `js` and `wasmJs`; Node and Wasmtime share `wasmWasi`. Minimum/current and debug/optimized dimensions expand these rows further. If those versions coincide, retain both requirement identities even when one execution satisfies them. Exact OS patch/build identifiers, vendor distributions and image checksums must be pinned before release evidence, not guessed from the platform family above.

## Concrete configuration equivalents

- Native: distinct `-g` and `-opt` executables. Both were exercised for the two Linux targets. Device/simulator frameworks and their consumer test applications need the same distinction when built.
- JS/Wasm: DEVELOPMENT and PRODUCTION linked executables. Wasm production must consume Binaryen's optimized output; testing its intermediate output is insufficient. The retained Node/Wasmtime harness checks both outputs and expected rejection cases.
- JVM: explicit Java8 bytecode/API restriction and publication attribute8, with an external Java consumer. Ordinary JVM compilation has no Native-style debug/release variant. The probe executed Kotlin `-Xno-optimize` and default bytecode optimization; JVM JIT execution modes are separate runtime settings, not release artifact types. The complete portable-suite comparison remains a harness obligation.
- Android JVM: the KMP library plugin has one published variant. Debug and optimized release test apps must consume that same AAR; a nonexistent library release task cannot meet the requirement. Both APKs built, including R8 optimization with the consumer entry point retained. Actual installed runtime behavior remains unverified.

## Remaining factual gates for the human support decision

The selected sources do not supply an absolute numbered plain-JS browser/Node support promise, nor a complete Linux syscall/kernel floor. The probes expose concrete constraints without filling those gaps by assumption. The support decision still needs an explicit treatment of these cases: additional bounded runtime searches, upstream clarification, or a separately approved operational baseline. None is silently selected here.

Apple link/runtime compatibility with Xcode26.4.1, macOS11 execution, Intel iOS simulator availability, both watch device ABIs, Android minimum-runtime and four native ABI execution, exact Windows minimum build, minimum-kernel execution and all browser runs remain unverified. Current Apple OS versions are candidates, not an asserted SDK-derived ceiling. Missing infrastructure delays the required evidence and does not narrow the target contract.

The prior report's unresolved source lookups are refined here; its historical observations remain intact. The human support ticket stays open until these findings are reconciled with its approved policies. No full engine tests, stable-release readiness or all-target support is claimed.

## Additional current-version sources

Oracle's [released-version matrix](https://ops.java/releases/matrix) identifies Java 26.0.2.1 as released in August 2026; Java 27 remains in its planned section at this snapshot. Google's [Android 17 announcement](https://developer.android.com/blog/posts/android-17-is-here) identifies Android 17/API37 as released. Neither fact demonstrates this probe executed on that runtime.

Microsoft's [Windows release table](https://learn.microsoft.com/en-us/windows/release-health/windows11-release-information) lists Windows 11 25H2 build 26200.9445. The [26H1 explanation](https://techcommunity.microsoft.com/blog/windows-itpro-blog/what-to-know-about-windows-11-version-26h1/4491941) ties that newer release to new Snapdragon X2 devices; it is not evidence of a newer native x64 lane. Windows 11 25H2 is therefore the x64 candidate, subject to actual execution.

[Kernel.org](https://www.kernel.org/) identifies stable Linux7.2.4; [glibc's release announcement](https://sourceware.org/pipermail/libc-announce/2026/000058.html) identifies glibc2.44. Their combined candidate environment has not been executed here; the local host versions are older.
