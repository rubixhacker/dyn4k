# Kotlin targets and verification research

Research date: 2026-09-09 (workspace date). Branch: `research/targets`.
Question: [Establish the complete Kotlin target and verification matrix](../../.scratch/port/issues/02-targets.md).
Status: factual research complete; candidate choices are not ratified policy. No implementation, compiler probes, publication, or runtime tests were performed.

## Candidate toolchain

Recommend evaluating **Kotlin/KGP 2.4.20**, identified as stable and released September 7, 2026 by the [release history](https://kotlinlang.org/docs/releases.html). The [GitHub tag API](https://api.github.com/repos/JetBrains/kotlin/git/ref/tags/v2.4.20) resolved to commit `890ac1d94fdb80eb85f0eeb5be5e4352df987b2f` in this session. The source revision is an evidence pin, not an installed compiler checksum.

The [KMP compatibility table](https://kotlinlang.org/docs/multiplatform/multiplatform-compatibility-guide.html#version-compatibility) lists Gradle 7.6.3–9.7.0, AGP 8.5.2–9.3.1 and Xcode 26.4 for KGP 2.4.20. A candidate combination is Gradle 9.5.0, JDK 21, AGP 9.3.1 and Xcode 26.4. AGP 9.3 specifies Gradle 9.5.0 and JDK 17 minimum; its [release notes](https://developer.android.com/build/releases/agp-9-3-0-release-notes) now also list 9.3.2, fixing a JDK-17 lint crash. Consequently 9.3.1 is a compatibility-table candidate, not a claim that it is latest or already validated. Decide the final AGP patch after a build probe; do not conflate build JDK with consumer bytecode/minimum Java version.

## Complete candidate manifest

There are **21 targets under the current documented deprecation policy**, plus **one disputed target retained below pending reconciliation**. Both core and shim need this manifest. Browser/Node engines and device ABIs in a runtime matrix are not additional KMP targets. `commonMain` is shared source/metadata, not an executable target.

### Non-Native targets

[JVM and JS are Stable; Wasm is Beta](https://kotlinlang.org/docs/components-stability.html#kotlin-compiler). The [DSL reference](https://kotlinlang.org/docs/multiplatform/multiplatform-dsl-reference.html#targets) enumerates these identifiers and web environments.

| Identifier | Compilation/runtime family | Candidate execution evidence |
| --- | --- | --- |
| `jvm` | JVM, Stable | JVM suite plus unchanged Java-source consumer compile and execution |
| `android` | Android JVM via Google's KMP library plugin | Host tests and separate instrumented Android consumer |
| `js` | JS, Stable; `browser`, `nodejs` | Browser and Node.js suites |
| `wasmJs` | Wasm, Beta; `browser`, `nodejs` | Wasm-capable browser and Node.js suites |
| `wasmWasi` | Wasm, Beta; `nodejs`, `wasmtime` | Both supported WASI runner suites |

Web/JVM compilation needs a supported Gradle/JDK installation, not a target-device host; execution additionally needs the named runtime. Android needs the SDK and a device/emulator for instrumented evidence. These are proposed evidence lanes, not current dyn4k capabilities.

### Native targets

Tier and automatic-test columns below come from the [Native support table](https://kotlinlang.org/docs/native-target-support.html). `Auto` means upstream Gradle/IDE execution support, not that dyn4k tests have run. `Mac` means Apple final linking requires macOS; `Cross` means supported Native hosts can cross-link. Proposed runtime destinations do not assert an available runner.

| Identifier | Tier | Link host | Auto | Proposed runtime destination |
| --- | --- | --- | --- | --- |
| `macosArm64` | 1 | Mac | Yes | Apple Silicon Mac |
| `iosSimulatorArm64` | 1 | Mac | Yes | ARM64 iOS simulator |
| `iosArm64` | 1 | Mac | No | iPhone/iPad harness |
| `linuxX64` | 2 | Cross | Yes | x86-64 Linux |
| `linuxArm64` | 2 | Cross | No | ARM64 Linux harness |
| `watchosSimulatorArm64` | 2 | Mac | Yes | ARM64 watchOS simulator |
| `watchosArm64` | 2 | Mac | No | watchOS ILP32 device harness |
| `tvosSimulatorArm64` | 2 | Mac | Yes | ARM64 tvOS simulator |
| `tvosArm64` | 2 | Mac | No | Apple TV harness |
| `androidNativeArm32` | 3 | Cross | No | ARM32 Android NDK harness |
| `androidNativeArm64` | 3 | Cross | No | ARM64 Android NDK harness |
| `androidNativeX86` | 3 | Cross | No | x86 Android NDK harness |
| `androidNativeX64` | 3 | Cross | No | x86-64 Android NDK harness |
| `mingwX64` | 3 | Cross | Yes | x86-64 Windows |
| `watchosDeviceArm64` | 3 | Mac | No | watchOS LP64 device harness |
| `iosX64` | 3 | Mac | No | compatible Intel iOS simulator harness |

Tier 1 has upstream compile/run CI coverage; Tier 2 compile coverage, with weaker runtime assurances; Tier 3 lacks CI guarantees. Stable Native compiler status does not promote Tier 3 targets to Tier 1 guarantees. A blank automatic-test entry is an integration gap, not scope exclusion.

Supported Native build hosts are macOS ARM64/x86-64 and Linux/Windows x86-64. Linux ARM64 is a target, not an officially supported compiler host. `.klib` production can cross-compile from supported hosts; Apple cinterop dependencies require Mac. Apple final binaries always require Mac. [Native host rules](https://kotlinlang.org/docs/native-target-support.html#hosts), [publication host requirements](https://kotlinlang.org/docs/multiplatform/multiplatform-publish-lib-setup.html#host-requirements).

## Deprecation discrepancy requiring a probe

Current [2.4.20 release notes](https://kotlinlang.org/docs/whatsnew2420.html#breaking-changes-and-deprecations) deprecate `watchosArm32`, with removal planned for 2.5.0. However, the pinned [KonanTarget source](https://github.com/JetBrains/kotlin/blob/890ac1d94fdb80eb85f0eeb5be5e4352df987b2f/native/utils/src/org/jetbrains/kotlin/konan/target/KonanTarget.kt) omits it from `deprecatedTargets`, and the pinned [Gradle preset source](https://github.com/JetBrains/kotlin/blob/890ac1d94fdb80eb85f0eeb5be5e4352df987b2f/libraries/tools/kotlin-gradle-plugin/src/common/kotlin/org/jetbrains/kotlin/gradle/dsl/KotlinTargetContainerWithPresetFunctions.kt#L208) exposes it without a deprecation annotation. Both sources were fetched directly this session.

Retain `watchosArm32` as a **disputed 22nd candidate**, with Mac linking and an ARM32 watchOS harness gap. Do not erase it from planning before reconciling the actual pinned plugin/compiler diagnostics with upstream policy. A missing compiler warning does not itself overturn an announced deprecation. This is a precise uncertainty, not evidence that the target works.

`macosX64`, `watchosX64`, `tvosX64` (deprecated since 2.3.20) and `linuxArm32Hfp` (since 1.8.20) are excluded by the agreed non-deprecated boundary. Other historical names absent from the supported manifest, such as `mingwX86`, are not additional current targets. `iosX64` must not be excluded merely because other Intel Apple targets are deprecated.

## Execution and packaging details

- Android JVM and the four Android Native targets are separate. Use `com.android.kotlin.multiplatform.library` and current `android {}` DSL. `androidLibrary {}` was replaced in AGP 8.12 and deprecated in 9.1 alpha; the new plugin has one variant, with tests disabled until opted in. Enable `withHostTest` and `withDeviceTest`; `withJava()` is needed only if compiling Java sources in that Android module. [Google's plugin guide](https://developer.android.com/kotlin/multiplatform/plugin). The general KMP publication page still contains older `androidLibrary` examples; prefer Google's owning documentation.
- `wasmWasi` currently targets WASI Preview 1, not a general WASI 0.2 component library. Node/Wasmtime task families are provided; Deno/WasmEdge examples use custom tasks. [WASI tutorial](https://kotlinlang.org/docs/wasm-wasi.html). These engine choices need pinned versions and real probes, not a generic “supports Wasm” check.
- `wasmJs` defaults to legacy exception handling; `wasmWasi` defaults to the new proposal. Browser execution needs WasmGC and compatible exception handling; documented browser floors are Chrome 119, Firefox 120, Safari 18.2. [Wasm configuration](https://kotlinlang.org/docs/wasm-configuration.html). Recommend current browser engines for tests; consumer minimum browser versions remain a decision.
- KMP Maven publication has a root metadata publication plus target publications. A root publication alone does not deliver every target. Unsupported host targets can be skipped; success of an umbrella task is not a manifest audit. Publish centrally to avoid duplicate root publications, and test downstream dependency resolution. [Publication setup](https://kotlinlang.org/docs/multiplatform/multiplatform-publish-lib-setup.html). Kotlin-consumable artifacts do not automatically establish npm/TypeScript, Swift framework or C ABI compatibility; those packaging requirements remain open.

## Recommended evidence model, not release policy

Maintain one row per target and runtime environment with four independently observed states:

1. **Declared**: exact target exists in both module configurations.
2. **Built**: non-skipped compilation and artifact; separately record final consumer linking.
3. **Executed**: named runtime/architecture/version, executed test count, exit status and results at the exact source SHA.
4. **Consumable**: an external consumer resolves the published artifact and performs a physics call; JVM additionally compiles unchanged dyn4j Java imports and API use.

The proposed immediate runners are Linux x86-64, Apple Silicon macOS and Windows x86-64, supplemented by browser/Node/Wasmtime and Android execution. Device-only and unsupported automatic-run lanes need custom harness investigations. In particular, current Intel iOS simulator availability and both watchOS ABIs cannot be promised from a target declaration. No machines or devices were audited in this research.

All targets remain in scope while evidence is missing. The later human decision must define which missing runtime lanes block release, select consumer Java/Android/Apple floors, settle disputed watchOS scope, and freeze exact tool/runtime versions. Research does not authorize dropping difficult lanes.

## Source-time and verification limits

Fetched official pages report dates through September 2026, consistent with the workspace date; no future release was deliberately selected. Pages are mutable and contain mixed-generation examples: Android DSL and watchOS deprecation conflicts are recorded above. The immutable source pin is available, but source inspection did not resolve the watchOS disagreement. WASI documentation distinguishes existing Preview 1 support from future component-model work.

Verification performed: primary pages opened; tag resolved by GitHub API; pinned target and Gradle preset source read; matrix manually counted as 16 Native + 5 other documented targets, with the disputed watchOS entry retained separately. No generated Gradle task inventory, compiler binary digest, CI run, runtime or publication result is claimed.
