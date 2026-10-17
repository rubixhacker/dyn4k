# Foundation build and verification

## What this slice provides

`dyn4k-core` defines the mutable `org.dyn4j` foundation types. `dyn4k`
provides Kotlin names for the same objects. A Java consumer uses the same
source file against dyn4j 6.0.0 and the candidate JVM artifact.

Each module declares 21 targets. They include JVM, Android JVM, JS, Wasm JS,
Wasm WASI, Linux x64 and ARM64, and Windows x64.
They also include macOS ARM64, three iOS targets, two tvOS targets, three
watchOS targets, and four Android Native ABIs.
Declarations do not establish runtime support. Run and report each target
separately before making a qualification claim.

## Pinned inputs

- Build JDK: 21.
- Gradle wrapper: 9.5.0 with a checked distribution SHA-256.
- Kotlin Gradle plugin: 2.4.20.
- Android Gradle plugin: 9.3.1.
- Preview version: `0.1.0-alpha.1`.
- Upstream source revision:
  `058bf6d982a0fb89b54050f929f6ea9dae53b714`.

Set `JAVA_HOME` to a JDK 21 installation before running `./gradlew`.
The build does not download or install a system JDK.

## Checks

Run these commands from the repository root:

```sh
./gradlew :dyn4k-core:verifyBaseline :dyn4k-core:verifyBaselineSources
./gradlew :dyn4k-core:runBaselineConsumer :dyn4k-core:runCandidateConsumer
./gradlew :dyn4k-core:runUpstreamFoundationTests :dyn4k-core:verifyJvmApi :dyn4k:jvmTest
./gradlew :dyn4k:linuxX64Test
./gradlew :dyn4k-core:runAndroidCandidateConsumer :dyn4k:testAndroidHostTest
```

The baseline tasks verify both Maven artifact hashes before using the
published JARs. The upstream test task checks out the exact source revision
and runs six unchanged geometry test classes against the candidate JVM JAR.
The baseline JAR and JUnit stay in test-only Gradle configurations. The Android
consumer runs the same Java source against Android class archives on the host.
Android host tests run the common Kotlin cases. These checks do not establish
execution on an Android device.

The JVM and Android archive steps restore Java fields and static methods that
common Kotlin cannot declare directly on every target. The Java consumer and
a public/protected declaration comparison check the JVM JAR. The Android
consumer checks the Android class archives. Other targets use the common
Kotlin declarations without an archive step.

Common Rotation and Transform define public `getCost()` and `getSint()` methods.
JVM accessor names keep their protected properties from colliding with those
methods. JVM and Android archives retain the baseline protected fields.

Common Copyable uses the baseline covariant bound. Kotlin 2.4.20 requires a
targeted finite-bound suppression for this declaration. The compiler emits
the matching JVM generic signature. Check the bound again before changing
the Kotlin compiler version.

To stage the two modules locally, publish the selected target publications
to `build/staging-repository`. Staging does not publish a public release.
The POM files declare the BSD 3-Clause license and the `dyn4k` dependency
on `dyn4k-core`. Each staged publication includes the upstream license as
a separate `license.md` artifact.

The root [upstream license](../../LICENSE.md) is a byte-for-byte copy from
the pinned source checkout. Translated source files retain their own legal
headers.
