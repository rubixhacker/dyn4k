# Consumer platform floors

Research date: 2026-09-10. Supports [Define support and verification for every target](https://github.com/rubixhacker/dyn4k/issues/6). Research only: no compiler, artifact, device, simulator, or runtime probe was performed. Numeric deployment defaults below are not dyn4k compatibility guarantees.

## Native source pin

The [GitHub tag API](https://api.github.com/repos/JetBrains/kotlin/git/ref/tags/v2.4.20) was fetched again: `v2.4.20` directly names commit `890ac1d94fdb80eb85f0eeb5be5e4352df987b2f`. Source files below were fetched from that immutable revision, independently of the earlier report.

## Native target floors

The nine Apple targets' configured deployment defaults come from [konan.properties](https://github.com/JetBrains/kotlin/blob/890ac1d94fdb80eb85f0eeb5be5e4352df987b2f/kotlin-native/konan/konan.properties#L53-L63), including the per-target exception cited below. A deployment value controls final linking; it is not proof of an executable runtime lane or an available test device.

| Target | Verified default or documented constraint | Limitation |
| --- | --- | --- |
| `macosArm64` | macOS 12.0 | A documented override can lower this; see below |
| `iosArm64` | iOS/iPadOS 15.0 | Physical minimum/current evidence still required |
| `iosSimulatorArm64` | iOS 15.0 | Installed matching ARM64 simulator not inspected |
| `iosX64` | iOS 15.0 | Installed matching Intel simulator not inspected |
| `tvosArm64` | tvOS 15.0 | Physical minimum/current evidence still required |
| `tvosSimulatorArm64` | tvOS 15.0 | Installed matching simulator not inspected |
| `watchosArm64` | watchOS 8.0, ILP32 | Distinct from LP64 target |
| `watchosSimulatorArm64` | watchOS 8.0 | Does not establish device ABI coverage |
| `watchosDeviceArm64` | watchOS **9.0**, LP64 | Actual ARM64 device support is a separate constraint |
| `linuxX64` | Toolchain names glibc 2.19 / kernel 4.9 | Not an established minimum distribution/kernel support contract |
| `linuxArm64` | Toolchain names glibc 2.25 / kernel 4.9 | Not an established minimum distribution/kernel support contract |
| `mingwX64` | Windows 10 or later, x64 | Official target-support documentation; no exact Windows build floor stated |
| `androidNativeArm32` | Source comment says NDK for Android API 21 | Exact effective consumer floor not fully established |
| `androidNativeArm64` | Bundled Android NDK toolchain | Exact effective consumer floor unresolved |
| `androidNativeX86` | Bundled Android NDK toolchain | Exact effective consumer floor unresolved |
| `androidNativeX64` | Bundled Android NDK toolchain | Exact effective consumer floor unresolved |

Linux toolchain identities are in [pinned properties](https://github.com/JetBrains/kotlin/blob/890ac1d94fdb80eb85f0eeb5be5e4352df987b2f/kotlin-native/konan/konan.properties#L65-L68); Windows support is in the [official target table](https://kotlinlang.org/docs/native-target-support.html#tier-3). Android target properties and the API-21 comment are in [pinned properties](https://github.com/JetBrains/kotlin/blob/890ac1d94fdb80eb85f0eeb5be5e4352df987b2f/kotlin-native/konan/konan.properties#L605-L722). The [Android linker](https://github.com/JetBrains/kotlin/blob/890ac1d94fdb80eb85f0eeb5be5e4352df987b2f/native/utils/src/org/jetbrains/kotlin/konan/target/Linker.kt#L140-L170) uses `Android.API`, but this bounded investigation did not locate and verify that constant. Do not turn the ARM32 comment into a verified four-ABI consumer guarantee.

## Defaults are not the lowest configurable versions

Kotlin documents default Apple minima of iOS/tvOS 15, macOS 12, and watchOS 8, then explicitly shows `-Xoverride-konan-properties` examples for iOS/tvOS 14, macOS 11, and watchOS 7. These examples establish configurability, not compatibility with every selected SDK or a guaranteed absolute floor. [Kotlin lower-version documentation](https://kotlinlang.org/docs/native-target-support.html#supporting-lower-apple-target-versions)

Apple's current table lists **Xcode 26.4.1**, not a separate 26.4 row: deployment minima iOS/tvOS 15, watchOS 8, macOS 11; device/simulator support begins at iOS/tvOS 15 and watchOS 8. Its build host is macOS Tahoe 26.2 or later within 26.x. This is evidence about the 26.4.1 row, not an independently verified exact 26.4 installation. [Apple Xcode requirements](https://developer.apple.com/xcode/system-requirements)

Thus macOS 11 is a concrete lower candidate under a documented Kotlin override and the listed Xcode 26.4.1 deployment range. Whether dyn4k should adopt that override requires a policy choice and final-artifact/runtime evidence. Lower iOS/tvOS 14 and watchOS 7 examples fall below that Xcode row's supported deployment range. The minimum/current policy needs an explicit definition: toolchain defaults, or the lowest supported intersection including overrides.

## watchOS conflicts

`watchosDeviceArm64` has an explicit `osVersionMin.watchos_device_arm64 = 9.0` and CPU `apple-s9`; the broad Kotlin table describes it as watchOS 8+. Prefer the target-specific source when recording the compiler default, while retaining the documentation discrepancy. [Pinned LP64 configuration](https://github.com/JetBrains/kotlin/blob/890ac1d94fdb80eb85f0eeb5be5e4352df987b2f/kotlin-native/konan/konan.properties#L360-L379)

A more important execution distinction: Apple describes Series 9 and later and Ultra 2 switching to ARM64 **on watchOS 26**; its testing guidance names those devices on watchOS 26. Therefore a compiler deployment value of 9.0 does not establish an LP64 device test on watchOS 9. The evidence supports watchOS 26 as the documented ARM64 execution introduction; the release matrix must distinguish this from the linker floor and validate actual hardware. [Apple WWDC architecture explanation](https://developer.apple.com/videos/play/wwdc2025/334/?time=345), [Apple ARM64 testing guidance](https://developer.apple.com/news/?id=zt8rydnt)

`watchosArm32` remains a policy/source mismatch: the [Kotlin 2.4.20 release notes](https://kotlinlang.org/docs/whatsnew2420.html#breaking-changes-and-deprecations) expressly deprecate it and plan removal in 2.5.0; the [Native support table](https://kotlinlang.org/docs/native-target-support.html#deprecated-targets) agrees. But the pinned [deprecated-target set](https://github.com/JetBrains/kotlin/blob/890ac1d94fdb80eb85f0eeb5be5e4352df987b2f/native/utils/src/org/jetbrains/kotlin/konan/target/KonanTarget.kt#L58-L59) omits it, and the [preset functions](https://github.com/JetBrains/kotlin/blob/890ac1d94fdb80eb85f0eeb5be5e4352df987b2f/libraries/tools/kotlin-gradle-plugin/src/common/kotlin/org/jetbrains/kotlin/gradle/dsl/KotlinTargetContainerWithPresetFunctions.kt#L208-L222) lack a deprecation annotation. No actual diagnostic was executed. Proposed interpretation: announced support policy can deprecate a target before diagnostics catch up; decide explicitly whether that policy controls the charter's non-deprecated boundary. Do not silently erase the disputed target or claim the source conflict is resolved.

## Remaining Native decisions and evidence

- Define whether lowest supported means defaults or supported overrides, including the macOS 11 candidate.
- Reconcile nominal watchOS LP64 deployment floor with the first actually supported runtime/device generation.
- Establish precise Android Native API floors and Linux userspace/kernel baseline through owning source and later artifact inspection.
- Verify exact Xcode 26.4 identity/support rather than silently substituting 26.4.1.
- Freeze actual minimum/current test versions and available architecture-specific devices/simulators. Upstream support tables and properties are not evidence that dyn4k has executed there.

## JVM, Android JVM, JavaScript, and Wasm

| Target or runtime | Established constraint | Still needed |
| --- | --- | --- |
| `jvm` | Java 8 is the lowest supported bytecode target | Java 8 API discipline, correct publication metadata, and minimum/current consumer execution |
| `android` | Android KMP plugin exposes configurable `minSdk`; its guide uses 24 in an example | An authoritative minimum for the selected plugin/runtime combination; the example is not a floor |
| `js` browsers | Kotlin supports ES5 and ES2015 output | Output/module configuration and exact browser minima; language levels alone do not establish numbered browser support |
| `wasmJs` Chromium | 119+ documented without experimental flags | Minimum/current execution with the selected compiler configuration |
| `wasmJs` Firefox | 120+ documented without experimental flags | Minimum/current execution with the selected compiler configuration |
| `wasmJs` Safari/WebKit | Safari 18.2+ documented | Match the Safari version to an actual WebKit test environment; an arbitrary WebKit runner is not proof of Safari 18.2 |
| Node.js across `js`, `wasmJs`, `wasmWasi` | Configurable execution runtime | A minimum per generated target/configuration; plugin defaults are not consumer minima |
| Wasmtime for `wasmWasi` | Kotlin supplies Wasmtime tasks; WASI Preview 1 and new exception handling are documented | Exact compatible minimum/current runner versions |

The [Kotlin FAQ](https://kotlinlang.org/docs/faq.html#which-versions-of-jvm-does-kotlin-target) explicitly excludes bytecode targets below Java 8. The pinned [stdlib build](https://github.com/JetBrains/kotlin/blob/890ac1d94fdb80eb85f0eeb5be5e4352df987b2f/libraries/stdlib/build.gradle.kts#L156-L159) also uses JVM 1.8 for the JVM compilation. A build JDK of 21 must not accidentally become the consumer floor: Kotlin documents how mismatched `targetCompatibility` can publish an incorrectly high `org.gradle.jvm.version`. [Gradle configuration](https://kotlinlang.org/docs/gradle-configure-project.html)

The [Android KMP plugin guide](https://developer.android.com/kotlin/multiplatform/plugin) shows `minSdk = 24` in sample configuration. No universal minimum consumer API was established from that example. Compose and AndroidX library requirements are not automatically requirements of this physics library.

[Kotlin/JS](https://kotlinlang.org/docs/js-overview.html) documents ES5/ES2015 output; module format, generated runtime operations, dependencies, and any polyfills affect usable runtimes. Do not assign the Wasm browser floors to plain JS without an explicit decision. The [JS setup guide](https://kotlinlang.org/docs/js-project-setup.html#node-js) reports default Node.js 24.16.0 and a configurable version; neither constitutes a minimum guarantee.

The browser numbers come from [Kotlin/Wasm configuration](https://kotlinlang.org/docs/wasm-configuration.html). That page distinguishes `wasmJs` legacy exception handling from `wasmWasi` new exception handling defaults; enabling another mode requires reviewing the runtime matrix. The [WASI guide](https://kotlinlang.org/docs/wasm-wasi.html) establishes Preview 1 and Node/Wasmtime task families, but the sources checked do not establish exact minimum Node or Wasmtime versions for this selected compiler. These remain factual gaps, not permission to omit either runtime.

## Verification and interpretation

This report records live primary-document and immutable-source inspection. It does not freeze numeric dyn4k support floors, establish the absolute oldest executable runtime, or claim any build/test/consumer passed. The approved policy remains minimum-and-current testing for every required lane. Where sources do not define an absolute minimum, additional source investigation or a bounded compiler/consumer probe is needed before an exact floor can be ratified. An override alone does not demonstrate upstream support.
