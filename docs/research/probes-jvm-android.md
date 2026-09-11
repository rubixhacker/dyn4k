# JVM and Android JVM toolchain probes

Evidence captured 2026-09-10 in `probes/toolchain/jvm-android/`. These are throwaway packaging probes, not an engine implementation or approval of consumer floors.

## Exact tools

Kotlin/KGP 2.4.20, Gradle 9.5.0, build JDK Temurin 21.0.12.1+1 and AGP 9.3.1 were actually used. Temporary binaries reside under `/tmp/dyn4k-probe-tools/`; no system tool or service was installed. Downloaded archives passed SHA-256 checks against the [Gradle distribution digest](https://services.gradle.org/distributions/gradle-9.5.0-bin.zip.sha256) and Adoptium release API metadata. JDK21/JRE8 upstream URLs and checksums are retained in `evidence/jdk21.json`, `evidence/jre8.json`, and `evidence/tools.sha256`. JRE8 is Temurin 8u504-b01. See [Adoptium JDK21 release](https://github.com/adoptium/temurin21-binaries/releases/tag/jdk-21.0.12.1%2B1) and [JRE8 release](https://github.com/adoptium/temurin8-binaries/releases/tag/jdk8u504-b01).

## JVM: executed proof

A common Kotlin mutable `Vector` compiled with `jvmTarget=1.8` and `-Xjdk-release=8` on build JDK21 and published to a local Maven repository. `javap -verbose` reports classfile major version **52** (`evidence/jvm-bytecode.log`).

An initial publication omitted `org.gradle.jvm.version` entirely, despite the explicit compiler target. This negative baseline is retained as `evidence/jvm-original.module`. The candidate explicitly sets target attribute `TargetJvmVersion.TARGET_JVM_VERSION_ATTRIBUTE` to 8. Its publication declares 8 in `evidence/jvm-fixed.module`.

A separate plain Java Gradle application resolved the published Maven coordinate with requested JVM version8. `dependencyInsight` reports **Provided8 / Requested8** (`evidence/external-consumer-fixed.log`). That application's Java source compiled using JDK21 `--release 8`; its installed distribution then ran under actual **JRE8**, producing `external Java consumer: 23.0` and exit0 (`evidence/java8-runtime.log`). This proves this artifact and its resolved Kotlin stdlib can run on Java8; it does not certify unimplemented dyn4k code or APIs. The same installed distribution also ran successfully under the installed Homebrew Java26.0.2.1 (`evidence/java26-runtime.log`, `evidence/runtime-java26.log`). Build JDK21 is not the consumer floor. The Kotlin [compiler options documentation](https://kotlinlang.org/docs/compiler-reference.html#xjdk-release-version) defines `-Xjdk-release` as limiting accessible JDK APIs as well as bytecode targeting; the candidate uses it to avoid accidentally compiling against JDK21-only APIs.

The explicit publication attribute follows Gradle's documented [JVM ecosystem attribute](https://docs.gradle.org/9.5.0/userguide/variant_attributes.html#sub:variant-jvm-ecosystem). An intentional temporary JVM source calling Java9 `java.util.List.of` was rejected as unresolved under `-Xjdk-release=8` (`evidence/java9-api-rejection.log`); the source was then removed and final publication rebuilt successfully (`evidence/jvm-final-build.log`). Keeping target and attribute aligned is a build acceptance check, not something to infer from build JDK.

## Android JVM: executed proof and boundary

The new `com.android.kotlin.multiplatform.library`9.3.1 plugin compiled and published an AAR at compileSdk36/minSdk21, consuming the same common Kotlin source. `evidence/android-api21-retry.log` records the first successful build. The initial run failed solely because the host supplied `/home/stewart/Android/Sdk` while the command supplied its `/var/home/stewart/Android/Sdk` alias; using the same exact ANDROID_HOME/ANDROID_SDK_ROOT spelling corrected the environment (`evidence/android-api21.log`).

A deliberate minSdk1 configuration also compiled and published successfully (`evidence/android-api1-publish.log`, extracted `evidence/android-api1-manifest.xml`). Therefore plugin configuration/build acceptance does **not** establish21 or the documentation's sample24 as a universal lower bound. A first attempted `lint` task was unavailable for this plugin and is retained as `evidence/android-api1.log`; no lint success is claimed. The final candidate restores21. No Android runtime floor has been proven without executing on a device/emulator at that API and checking the complete library's required APIs.

The [official Android KMP plugin documentation](https://developer.android.com/kotlin/multiplatform/plugin) explicitly specifies a **single variant**, without build types/product flavors. Asking this library for `assembleDebug`/`assembleRelease` would test a nonexistent interface. The equivalent validation is publishing that single AAR then consuming it from a separate Android application's debug and release builds. The separate Java Android application successfully built **both debug and release APKs**, with76 tasks executed, including dex merging and release lintVital (`evidence/android-consumer.log`). Both consume the same published AAR; a subsequent release probe enables R8 minification with the standard optimized rules and retains the public `probe.Consumer.run` entry point while allowing optimization; see `evidence/android-consumer-r8.log`. This is build evidence, not an Android runtime assertion. Artifact digests are retained in `evidence/artifacts.sha256`, and final AAR minSdk21 is visible in `evidence/android-api21-manifest.xml`. `adb devices -l` lists no attached device (`evidence/android-devices.log`): APK compilation does not prove Android runtime behavior.

An Android minimum is distinct from `androidNativeArm32/Arm64/X86/X64` native API floors. These Android JVM observations cannot establish those Native targets' floors.

## Reproduce

Set `JAVA_HOME` to the verified JDK21 directory and use the verified Gradle9.5 binary. From the probe directory:

```sh
gradle --no-daemon publish
gradle --no-daemon -p consumer clean installDist dependencyInsight --dependency toolchain-probe-jvm --configuration runtimeClasspath
JAVA_HOME=/tmp/dyn4k-probe-tools/jdk8u504-b01-jre consumer/build/install/external-consumer/bin/external-consumer
gradle --no-daemon -p android publish
gradle --no-daemon -p android-consumer assembleDebug assembleRelease
```

Android commands require matching SDK environment paths and compileSdk36 installed. To repeat the deliberate lower configuration acceptance probe use `-p android -PprobeMinSdk=1 clean publish`; restore the default21 publication afterward. Build outputs are intentionally untracked; retained logs, module metadata and digests provide the evidence.

## Optimization equivalents and negative probe reproduction

Kotlin/JVM has no built-in debug/release compilation pair in this probe. Default compiler optimization is the optimized equivalent already tested above; `-PprobeNoOptimize=true` adds Kotlin's `-Xno-optimize` for the unoptimized equivalent. Publish that configuration, rebuild the external consumer, and execute it under JRE8. Evidence is retained in `jvm-no-optimize-build.log`, `jvm-no-optimize-consumer.log` and `jvm-no-optimize-java8.log`. Final repository publication is restored to the default optimized configuration afterward. These switches do not simulate an Android build variant.

The intentionally rejected source is retained at `negative/ApiBoundary.kt.txt`, outside source roots. With the JDK21/Gradle9.5 environment above:

```sh
mkdir -p src/jvmMain/kotlin/probe
cp negative/ApiBoundary.kt.txt src/jvmMain/kotlin/probe/ApiBoundary.kt
gradle --no-daemon compileKotlinJvm # Expected nonzero: unresolved reference 'of'
rm src/jvmMain/kotlin/probe/ApiBoundary.kt
gradle --no-daemon publish # Restore passing default artifact
```

For optimized Android packaging, `gradle --no-daemon -p android-consumer assembleRelease` now runs `minifyReleaseWithR8`; the keep rule prevents the entire probe entry point from disappearing as unused code. The debug application remains the unminified counterpart.
