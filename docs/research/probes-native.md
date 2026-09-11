# Native toolchain and runtime probes

Observed 2026-09-11 UTC. Bounded research for the toolchain probe ticket; this is not dyn4k implementation or a support-policy ratification. Primary source pin: Kotlin `890ac1d94fdb80eb85f0eeb5be5e4352df987b2f` (`v2.4.20`).

## Proven locally

Downloaded the [official Linux compiler archive](https://github.com/JetBrains/kotlin/releases/download/v2.4.20/kotlin-native-prebuilt-linux-x86_64-2.4.20.tar.gz) and compared SHA-256 with its [published checksum](https://github.com/JetBrains/kotlin/releases/download/v2.4.20/kotlin-native-prebuilt-linux-x86_64-2.4.20.tar.gz.sha256): both `32d33c15c4da668a8d47a0ce2aea95be2c2cf8f5d1d65f6f4ed3697e4686dc7f`. `konanc -version` reports 2.4.20. Initial exploratory compilation used the default JRE25; final clean-directory reproduction explicitly uses selected Temurin JDK21.0.12.1+1 via JAVA_HOME. The original JDK25 logs remain labelled exploratory. Its shipped properties agree with the source values investigated below. All mutable scratch material is under `/tmp/dyn4k-native-source`; source and durable evidence are under [probes/toolchain/native](../../probes/toolchain/native/).

The [probe](../../probes/toolchain/native/Probe.kt) mutates an array, checks its numeric result and prints `native-probe:3.0`. Both `linux_x64` and `linux_arm64` compiled and linked with exit 0. The [run log](../../probes/toolchain/native/run.log) records three successful executions:

- x86-64 directly on Bazzite kernel `7.2.1-ogc4.1.fc44.x86_64`, glibc 2.43.
- The same x86-64 executable through the compiler sysroot's glibc 2.19 loader/libraries, on that same host kernel.
- ARM64 executable using the compiler-downloaded QEMU AArch64 5.1.0 and glibc 2.25 sysroot, on that same host kernel.

These prove compiler/dependency availability, final linking, and this tiny consumer journey. They do not prove physics, publication, a complete minimum distribution, an old kernel, or actual ARM64 hardware. The compiler auto-download logs are retained for [x86-64](../../probes/toolchain/native/compile.log) and [ARM64](../../probes/toolchain/native/compile-arm64.log). No Apple or Android Native final artifact was built here.

## Android Native: four source-configured API floors

The earlier constant lookup is now closed. [ClangArgs.kt lines 10–20](https://github.com/JetBrains/kotlin/blob/890ac1d94fdb80eb85f0eeb5be5e4352df987b2f/native/utils/src/org/jetbrains/kotlin/konan/target/ClangArgs.kt#L10-L20) sets `Android.API = "21"`, maps all four Native Android targets, and chooses their API-21 architecture sysroot. [AndroidLinker](https://github.com/JetBrains/kotlin/blob/890ac1d94fdb80eb85f0eeb5be5e4352df987b2f/native/utils/src/org/jetbrains/kotlin/konan/target/Linker.kt#L140-L180) uses that same constant both in the Clang-driver executable name and API-specific library search directory. This is stronger than an ARM32 source comment.

| Target | ABI | Source-selected API | Required runtime proof |
| --- | --- | --- | --- |
| `androidNativeArm32` | armeabi-v7a | 21 | API21 ARM32 process and current compatible Android ARM32 process |
| `androidNativeArm64` | arm64-v8a | 21 | API21 ARM64 and current ARM64 process |
| `androidNativeX86` | x86 | 21 | API21 x86 and latest available compatible x86 image |
| `androidNativeX64` | x86_64 | 21 | API21 x86-64 and current x86-64 image |

API21 is the selected compiler link baseline, not a verified dyn4k minimum. A minimum/current instrumentation APK or native executable harness must load/call the artifact and confirm its real process ABI and API. JNI glue is needed if the consumer is an Android JVM app. The current 32-bit row must remain unset until an image/device inventory identifies a compatible current runtime; an ARM64-only phone is not ARM32 evidence. Android JVM `minSdk` is a separate decision owned by the parent report.

## Linux: userspace and kernel are distinct

Pinned [properties](https://github.com/JetBrains/kotlin/blob/890ac1d94fdb80eb85f0eeb5be5e4352df987b2f/kotlin-native/konan/konan.properties#L65-L68) name glibc 2.19 / kernel 4.9 for x86-64, and glibc 2.25 / kernel 4.9 for ARM64. Both actual dependency archives downloaded successfully during compilation. Inspecting their embedded crosstool configuration and libc ELF notes establishes:

| Evidence | Linux x86-64 | Linux ARM64 |
| --- | --- | --- |
| glibc configured version | 2.19 | 2.25 |
| Linux header version | 4.9.156 | 4.9.156 |
| glibc minimum-kernel configuration | empty; `CT_GLIBC_KERNEL_VERSION_NONE=y` | `CT_GLIBC_MIN_KERNEL="4.9.156"`; AS_HEADERS=y |
| sysroot libc GNU ABI-tag | Linux 2.6.16 | Linux 4.9.156 |
| probe's highest required GLIBC symbol version | 2.17 | 2.17 |
| probe interpreter | `/lib64/ld-linux-x86-64.so.2` | `/lib/ld-linux-aarch64.so.1` |

Evidence: retained [x86-64 crosstool configuration](../../probes/toolchain/native/crosstool-linux-x64.config), [ARM64 configuration](../../probes/toolchain/native/crosstool-linux-arm64.config), [x86-64 ELF requirements](../../probes/toolchain/native/elf-linux-x64.txt), [ARM64 ELF requirements](../../probes/toolchain/native/elf-linux-arm64.txt), and [readelf output](../../probes/toolchain/native/run.log). These are primary artifacts extracted from compiler-selected toolchains.

Consequently **kernel 4.9 in the x86-64 archive name is not a proven consumer kernel minimum**. ARM64's bundled libc does explicitly encode 4.9.156, but a dynamically linked consumer can use another compatible system libc. Neither libc's ABI note establishes the Kotlin runtime's complete syscall floor. Likewise, this small executable importing GLIBC_2.17 does not authorize lowering the whole library contract to glibc 2.17.

Candidate minimum test userspaces are the selected sysroot versions 2.19 (x86-64) and 2.25 (ARM64), with the kernel minimum explicitly unresolved pending a real VM/native-machine probe and runtime syscall analysis. A conservative initial ARM64 test kernel candidate is 4.9.156, because that is what its bundled libc requires; the x86-64 kernel candidate cannot be inferred from the archive name. Current source-defined candidates for both architectures are Linux7.2.4 ([kernel.org stable release](https://www.kernel.org/), September7) with glibc2.44 ([glibc current status](https://sourceware.org/glibc/), July25). That paired rootfs/kernel has not run here. Bazzite kernel7.2.1/glibc2.43 is the observed local environment, not the latest release. A native ARM64 host remains uninventoried. QEMU userspace execution is supplemental and shares the modern host kernel.

## Apple: patch selection, deployment overrides and executable ABIs

Pinned [Xcode.kt](https://github.com/JetBrains/kotlin/blob/890ac1d94fdb80eb85f0eeb5be5e4352df987b2f/native/utils/src/org/jetbrains/kotlin/konan/target/Xcode.kt#L25-L47) parses only major/minor and sets `maxTested = XcodeVersion(26, 4)`. Thus the compiler's version comparison treats Xcode 26.4.1 as 26.4. This source fact closes the patch-comparison question, not actual link/run compatibility. The pinned properties refer to Xcode `26.4_17E192` sysroots; an installed 26.4.1 build identity was not inspected.

The [Apple Xcode requirements table](https://developer.apple.com/xcode/system-requirements) lists Xcode26.4.1 with 26.4 SDKs, host macOS Tahoe26.2–26.x, and deployment ranges starting at macOS11, iOS/tvOS15, watchOS8. Kotlin's [lower-target documentation](https://kotlinlang.org/docs/native-target-support.html#supporting-lower-apple-target-versions) documents `-Xoverride-konan-properties=minVersion.macos=11.0`. Therefore macOS11 is a supported-configuration candidate with this SDK intersection; compiling, inspecting `LC_BUILD_VERSION`, and executing on macOS11 still must prove it. The Xcode build host and application deployment host are different machines/OS roles.

Current runtime candidates follow the approved newest-stable-compatible policy, independently of the build SDK. [Apple security releases](https://support.apple.com/en-us/100100) currently names macOS/iOS/iPadOS26.6.2 and tvOS/watchOS26.6. These are shipping runtime candidates; compatibility with this compiler, installed simulator packages, deployment and device testing remains unverified. SDK26.4 is a build fact and does not establish an upper OS runtime limit.

| Target | Deployment minimum candidate | Newest stable runtime candidate | Link host and actual runtime harness |
| --- | --- | --- | --- |
| `macosArm64` | 11.0 using documented override; default12.0 | macOS26.6.2 | Mac link; Apple Silicon executable on each OS |
| `iosArm64` | iOS15.0 | iOS26.6.2 | Mac link; signed physical iPhone/iPad consumer |
| `iosSimulatorArm64` | iOS15.0 | iOS26.6.2, ARM64 runtime inventory required | Mac link; ARM64 simulator app/test |
| `iosX64` | iOS15.0 | Unset: compatible x86-64 simulator inventory required | Mac link; actual x86-64 simulator process and consumer |
| `tvosArm64` | tvOS15.0 | tvOS26.6 | Mac link; signed physical Apple TV consumer |
| `tvosSimulatorArm64` | tvOS15.0 | tvOS26.6, ARM64 runtime inventory required | Mac link; ARM64 simulator consumer |
| `watchosArm64` | watchOS8.0 | watchOS26.6 only on an ILP32-capable runtime/device | Mac link; `arm64_32` physical watch consumer |
| `watchosSimulatorArm64` | watchOS8.0 | watchOS26.6, ARM64 runtime inventory required | Mac link; simulator consumer; does not prove either physical-watch ABI |
| `watchosDeviceArm64` | approved runtime floor26.0; compiler link default9.0 | watchOS26.6 | Mac link; native ARM64 watch consumer on compatible hardware |

The target triples, deployment defaults and CPU settings come from [pinned properties](https://github.com/JetBrains/kotlin/blob/890ac1d94fdb80eb85f0eeb5be5e4352df987b2f/kotlin-native/konan/konan.properties). The [Native target table](https://kotlinlang.org/docs/native-target-support.html) distinguishes `watchosArm64` ILP32 from `watchosDeviceArm64` and keeps `iosX64` in tier3 without automatic test execution. The fact that Kotlin accepts an x86-64 target does not prove a current Xcode simulator can execute it; inspect `xcrun simctl list runtimes --json`, available destinations, and Mach-O/process architecture on the actual Mac. No working Intel simulator has been established in this probe.

For the device LP64 watch target, source specifies `arm64-apple-watchos`, CPU `apple-s9`, and `osVersionMin=9.0`; its ILP32 sibling uses `arm64_32-apple-watchos`, CPU `apple-s4`. Apple's [ARM64 testing announcement](https://developer.apple.com/news/?id=zt8rydnt) names Series9/10 and Ultra2 on watchOS26. Thus 26.0 is the concrete documented execution candidate, while 9.0 remains only the compiler deployment value. Actual device evidence is needed for the 26.6 ILP32 row, since new ARM64 watch execution does not substitute for it.

The parent reports the user approved excluding `watchosArm32` according to announced deprecation policy. Its source-diagnostic discrepancy does not reopen that settled boundary.

## Windows boundary

`mingwX64` has a documented Windows10 x64 floor in the [Native target table](https://kotlinlang.org/docs/native-target-support.html#tier-3), but no exact Windows10 build is specified there. Use a native x64 CLI consumer and record the exact build; no Windows link/run was done by this agent. Current native x64 candidate is Windows11 25H2 build26200.9445, listed in [Microsoft release information](https://learn.microsoft.com/en-us/windows/release-health/windows11-release-information). Parent research establishes the architecture restriction on newer26H1. A current Windows-on-ARM release is not native x64 coverage.

## Commands and reproducibility

These commands ran from the Linux host; dependency cache is isolated from the user's normal Kotlin cache:

```bash
export JAVA_HOME=/tmp/dyn4k-probe-tools/jdk-21.0.12.1+1
mkdir -p /tmp/dyn4k-native-source
curl -fL --max-time 120 https://github.com/JetBrains/kotlin/releases/download/v2.4.20/kotlin-native-prebuilt-linux-x86_64-2.4.20.tar.gz -o /tmp/dyn4k-native-source/compiler.tar.gz
curl -fsSL https://github.com/JetBrains/kotlin/releases/download/v2.4.20/kotlin-native-prebuilt-linux-x86_64-2.4.20.tar.gz.sha256 -o /tmp/dyn4k-native-source/compiler.sha256
sha256sum /tmp/dyn4k-native-source/compiler.tar.gz
cat /tmp/dyn4k-native-source/compiler.sha256
tar -xzf /tmp/dyn4k-native-source/compiler.tar.gz -C /tmp/dyn4k-native-source
# Copy the retained Probe.kt to /tmp/dyn4k-native-source/Probe.kt.
KONAN_DATA_DIR=/tmp/dyn4k-native-source/data timeout 150 /tmp/dyn4k-native-source/kotlin-native-prebuilt-linux-x86_64-2.4.20/bin/konanc /tmp/dyn4k-native-source/Probe.kt -target linux_x64 -o /tmp/dyn4k-native-source/probe
KONAN_DATA_DIR=/tmp/dyn4k-native-source/data timeout 150 /tmp/dyn4k-native-source/kotlin-native-prebuilt-linux-x86_64-2.4.20/bin/konanc /tmp/dyn4k-native-source/Probe.kt -target linux_arm64 -o /tmp/dyn4k-native-source/probe-arm64
bash probes/toolchain/native/reproduce.sh
# Optional: inspect the original exploratory scratch artifacts.
bash probes/toolchain/native/run.sh
```

[reproduce.sh](../../probes/toolchain/native/reproduce.sh) downloads the compiler to a fresh temporary directory, verifies the pinned digest, compiles the retained source with explicit `-g` and `-opt` modes for both targets, and executes all three journeys for each mode. Its fresh run using selected JDK21.0.12.1+1 completed exit0 with six `native-probe:3.0` results and four final executable checksums in [reproduce.log](../../probes/toolchain/native/reproduce.log). [run.sh](../../probes/toolchain/native/run.sh) contains the exact loader/QEMU/readelf invocations and passed exit0 on the final run. An initial logging run hit pipefail/SIGPIPE from `ldd --version | head -1`; replacing `head` with `sed -n 1p` fixed the evidence script and it was rerun. Compiler and resulting executable hashes are retained in [checksums.txt](../../probes/toolchain/native/checksums.txt); compiler-managed dependency downloads were removed from its download cache after extraction, so no independent archive checksum claim is made for them.

Unresolved: actual minimum kernels; minimum/current native ARM64 hardware; Android four-ABI link/load and image inventory; every Apple link/runtime, especially Intel simulator and both watch device ABIs; complete library API/import requirements; and final support-policy approval. These are explicit gaps, not successful lanes.
