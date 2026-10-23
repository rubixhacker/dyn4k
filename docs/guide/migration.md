# Migrate to dyn4k

Use dyn4k when you need the dyn4j 6.0.0 API on Kotlin Multiplatform or when you want an idiomatic Kotlin API over the same mutable engine objects. This guide describes preview `0.1.0-alpha.1`. It does not claim complete compatibility or release qualification.

## Scope and status

dyn4k ports the fixed dyn4j 6.0.0 baseline. It does not track later dyn4j releases. `dyn4k-core` provides the `org.dyn4j` compatibility surface. `dyn4k` provides Kotlin names and conveniences in `io.github.rubixhacker.dyn4k`. Both modules use one version and one mutable model.

The preview artifacts resolve from a locally staged Maven repository. The [Build and extend a simulation with the idiomatic Kotlin API](https://github.com/rubixhacker/dyn4k/issues/41) report records staged JVM and portable consumer runs at `68c2cea`; those runs cover basic staged resolution and geometry, not the full Kotlin API journey. The direct Kotlin journey is checked by [IdiomaticApiTest](../../dyn4k/src/commonTest/kotlin/io/github/rubixhacker/dyn4k/IdiomaticApiTest.kt) on six host lanes. The mixed Java/Kotlin example is checked by [IdiomaticMixedExampleTest](../../dyn4k/src/jvmTest/kotlin/io/github/rubixhacker/dyn4k/IdiomaticMixedExampleTest.kt). Neither check establishes full compatibility.

The approved scope has 21 targets and 28 runtime families. A target declaration or successful host build does not qualify its runtimes. Stable release requires the full portable suite, an external staged consumer, both build configurations, and the minimum and current runtime for each family.

| Target | Approved minimum runtime family |
| --- | --- |
| JVM | Java 8 |
| Android JVM | Android API 21 |
| Android Native ARM32, ARM64, x86, x64 | Android API 21 for each ABI |
| JS | Chromium 119, Firefox 120, Safari 18.2, Node.js 22.0.0 |
| Wasm JS | Chromium 119, Firefox 120, Safari 18.2, Node.js 22.0.0 |
| Wasm WASI | Node.js 24.15.0; Wasmtime 37.0.0 with GC, exceptions, and function references enabled |
| Linux x64 | Linux kernel 4.9.156 and glibc 2.19 |
| Linux ARM64 | Linux kernel 4.9.156 and glibc 2.25 |
| Windows x64 | Windows 10 version 1507, build family 10240 |
| macOS ARM64 | macOS 11 |
| iOS ARM64, simulator ARM64, simulator x64 | iOS 15; device and simulator are separate families |
| tvOS ARM64, simulator ARM64 | tvOS 15; device and simulator are separate families |
| watchOS ARM64 and simulator ARM64 | watchOS 8; physical device and simulator are separate families |
| watchOS device ARM64 | watchOS 26 on a physical device |

These are approved minimum baselines, not evidence that dyn4k passed on them. Each baseline is tested at its latest available maintenance patch. A current compatible runtime is tested separately. Apple device targets require physical devices; Android requires the exact ABI on a device or emulator. JS and Wasm JS require Chromium, Firefox, Safari, and Node. Wasm WASI requires Node and Wasmtime. The full matrix is **unpassed**.

## Add the dependencies

The preview version is `0.1.0-alpha.1`. Both modules use that version. Add `dyn4k-core` for Java code. Add `dyn4k` for Kotlin conveniences; it brings the core module as a dependency.

```kotlin
repositories {
    maven { url = uri("/path/to/dyn4k/build/staging-repository") }
    mavenCentral()
}

dependencies {
    implementation("io.github.rubixhacker:dyn4k:0.1.0-alpha.1")
}
```

For a Java-only consumer, depend on the core module:

```kotlin
dependencies {
    implementation("io.github.rubixhacker:dyn4k-core:0.1.0-alpha.1")
}
```

These coordinates are for staged preview artifacts. They do not mean the artifacts are available from Maven Central. See the [staged qualification consumer](../../consumers/qualification/build.gradle.kts) and [dependency-provider check](../../consumers/qualification/build.gradle.kts).

### Java class path and named modules

Use `dyn4k-core` on the Java class path. Keep the original `org.dyn4j` imports. Compile with Java 8 source and API constraints, for example `javac --release 8`.

```java
import org.dyn4j.dynamics.Body;
import org.dyn4j.geometry.Circle;
import org.dyn4j.geometry.MassType;

Body body = new Body();
body.addFixture(new Circle(0.5));
body.setMass(MassType.NORMAL);
```

The checked Java usage source is [IdiomaticJavaExample](../../dyn4k/src/jvmTest/java/IdiomaticJavaExample.java). Its companion mixed-language test is [IdiomaticMixedExampleTest](../../dyn4k/src/jvmTest/kotlin/io/github/rubixhacker/dyn4k/IdiomaticMixedExampleTest.kt). This is a source example, not proof that every baseline Java source compiles unchanged.

For a command-line class-path compile, resolve the staged `dyn4k-core-jvm` GAV `io.github.rubixhacker:dyn4k-core-jvm:0.1.0-alpha.1` and Kotlin standard library. Record the resolved GAV, JAR path, and SHA-256, and keep one `org.dyn4j` provider in the dependency graph. On a Unix-like shell, compile the checked Java source with:

```sh
javac --release 8 \
  -cp "$DYN4K_CORE_JAR:$KOTLIN_STDLIB_JAR" \
  -d build/classes \
  dyn4k/src/jvmTest/java/IdiomaticJavaExample.java
```

Use the platform class-path separator on Windows. `--release 8` checks the Java 8 source and API level; a compile on a newer JDK does not qualify a Java 8 runtime. Against the guide-base staged JAR, this command emitted class-file major version 52 on JDK 21.

### Named Java modules

The named module path requires Java 9 or newer. For a named-module consumer, declare `requires org.dyn4j`. Committed revision `578b8207ba19dcf633a56adbe293e3cd78b5e861` defines module `org.dyn4j`. Its [provider descriptor](https://github.com/rubixhacker/dyn4k/blob/578b8207ba19dcf633a56adbe293e3cd78b5e861/dyn4k-core/src/jvmModule/java/module-info.java) requires `kotlin.stdlib` and exports all 17 `org.dyn4j` packages:

`org.dyn4j`, `org.dyn4j.collision`, `org.dyn4j.collision.broadphase`, `org.dyn4j.collision.continuous`, `org.dyn4j.collision.manifold`, `org.dyn4j.collision.narrowphase`, `org.dyn4j.dynamics`, `org.dyn4j.dynamics.contact`, `org.dyn4j.dynamics.joint`, `org.dyn4j.exception`, `org.dyn4j.geometry`, `org.dyn4j.geometry.decompose`, `org.dyn4j.geometry.hull`, `org.dyn4j.geometry.simplify`, `org.dyn4j.world`, `org.dyn4j.world.listener`, and `org.dyn4j.world.result`.

```java
module dyn4k.migration.probe {
    requires org.dyn4j;
}
```

The bounded consumer uses this exact [module descriptor](../../tools/compatibility/fixtures/named_module/module-info.java) and [main class](../../tools/compatibility/fixtures/named_module/example/Main.java).

An earlier bounded named-module consumer passed on the `578b8207ba19dcf633a56adbe293e3cd78b5e861` branch artifact for staged GAV `io.github.rubixhacker:dyn4k-core-jvm:0.1.0-alpha.1`, SHA-256 `105c86360bf99f1108aa62e7aa21900bd4858441e7904e1e45375f46a4eb0dc7`. The direct probe received `--expected-provider-sha256` with the separately verified publication hash above. It rejected a missing or mismatched value and a second `org.dyn4j` provider. This direct invocation did not read or create a ledger mapping. The [named-module declaration ledger](https://github.com/rubixhacker/dyn4k/blob/578b8207ba19dcf633a56adbe293e3cd78b5e861/tools/compatibility/declaration-ledger.json) records `module.candidate: null` and empty module evidence. Candidate mapping and ledger replay remain unpassed. A candidate mapping is proposed, not recorded. Add it to the ledger before replay. A regular Java build does not obtain or check the expected hash automatically.

The named-module consumer was rerun on the combined source tree at revision `edea0c4723e0d092fe8614860937ad9c6f4001ec`. The staged `io.github.rubixhacker:dyn4k-core-jvm:0.1.0-alpha.1` JAR had SHA-256 `63cd3852e2727306ae0dc2abe5fb5a0faae49d5d7c704f8397643c3ffcad3560`. On OpenJDK `21.0.12.1`, the consumer compiled with `--release 9`, ran successfully, and verified exactly one `org.dyn4j` provider against that hash. This is a bounded combined-source consumer result; it does not establish candidate ledger mapping, ledger replay, or full named-module compatibility.

Use the module-path result only for that exact provider file and hash. A rebuild or merge changes the candidate identity. Record the resolved path, GAV, and SHA together. Do not infer provider identity from the module name alone. The bounded probe covers one unchanged `Vector2` path, not the full API or compatibility ledger.

The staged JAR from guide base `732baa91450a2601ae215d8d30e763ef026f3c68` had SHA-256 `b56d947ea183e6b8e7affddd1f24ad3ebd8e3276c6c56fa3e319e114793165f4` and still derives automatic module `dyn4k.core.jvm`. That older artifact has not passed the `org.dyn4j` module-path route; the bounded combined-source result above uses a different artifact and does not change this historical result.

Java 8 consumers can use the class path without a `module-info.java` file. A separate branch-scoped probe used GAV `io.github.rubixhacker:dyn4k-core-jvm:0.1.0-alpha.1` and JAR SHA-256 `105c86360bf99f1108aa62e7aa21900bd4858441e7904e1e45375f46a4eb0dc7`. It also used the Kotlin standard library on Temurin `1.8.0_504`. The probe compiled and ran the linked `Vector2` consumer. This is one bounded path; it does not qualify the guide-base JAR or full runtime support.

### Kotlin shared model

Import `io.github.rubixhacker.dyn4k.*` for Kotlin conveniences. Convenience constructors and properties operate on core `org.dyn4j` types. A Kotlin `Body` is the same object returned by the compatibility API; no conversion is needed.

```kotlin
val simulation = world {
    gravity = Vector2(0.0, -9.8)
    body {
        fixture(circle(0.5)) { density = 1.0 }
        massType = MassType.NORMAL
        linearVelocity = Vector2(2.0, 0.0)
    }
}
simulation.step(1)
```

The checked body and world journey is [IdiomaticApiTest](../../dyn4k/src/commonTest/kotlin/io/github/rubixhacker/dyn4k/IdiomaticApiTest.kt). Its builders configure the mutable core objects in place. The test checks body, fixture, velocity, world, and joint identity across both APIs.

### Vector assignment and shared mutation

The value operators return a new vector. For a mutable variable, `+=`, `-=`, `*=`, and `/=` rebind that variable to the returned vector. Any other reference still points to the original vector. Named methods `add`, `subtract`, `multiply`, and `divide` change the existing vector and preserve its identity.

```kotlin
package guide.example

import io.github.rubixhacker.dyn4k.*
import org.dyn4j.dynamics.Body
import org.dyn4j.geometry.Vector2

fun main() {
    val body = Body()
    val sharedVelocity = body.linearVelocity
    var localVelocity = sharedVelocity
    localVelocity += Vector2(1.0, 0.0)
    check(localVelocity !== sharedVelocity)

    sharedVelocity.add(Vector2(0.0, 1.0))
    check(body.linearVelocity === sharedVelocity)
}
```

The complete block is compiled from this page by [check_examples.py](check_examples.py) against a staged `dyn4k` GAV. Run `python3 docs/guide/check_examples.py <staging-repository>` against a repository produced from API revision `0a141816`. Add `--run` to execute it. The guide-base staged artifact predates the approved operator policy and fails to compile the `+=` line because both `plus` and `plusAssign` are available.

The staged artifact from API revision `0a141816` compiles and runs this block. That result is tied to its historical branch. It does not prove this tree's staged example. The exact assertions are in [IdiomaticApiTest at API revision `0a141816`](https://github.com/rubixhacker/dyn4k/blob/0a141816d77dbb4db08fbac429a1c3e5ed24a41d/dyn4k/src/commonTest/kotlin/io/github/rubixhacker/dyn4k/IdiomaticApiTest.kt). That revision verifies all four operators and named methods. Its six-host and staged-consumer results remain branch-scoped.

The approved operator policy is integrated in current history at `f84b2bcd`. The current tree includes [GeometryConveniences](../../dyn4k/src/commonMain/kotlin/io/github/rubixhacker/dyn4k/GeometryConveniences.kt) and its [IdiomaticApiTest](../../dyn4k/src/commonTest/kotlin/io/github/rubixhacker/dyn4k/IdiomaticApiTest.kt). A recorded run compiled and executed this fenced assignment example against staged JVM publications from source commit [`b6527619434e296b984067b146a28c75e24c0311`](https://github.com/rubixhacker/dyn4k/commit/b6527619434e296b984067b146a28c75e24c0311), as documented in the [canonical evidence record](https://github.com/rubixhacker/dyn4k/issues/42#issuecomment-6355331090). This result covers one example and staged JVM artifacts only; it does not qualify other guide examples, current sources, migration applications, numerical or physical behavior, runtimes, or release readiness.

## Migration examples

### Shapes, bodies, and units

Create shapes with their geometry constructors. Add them as fixtures to a body. A length is in metres, an angle is in radians, and time is in seconds. Use a fixed step for repeatable application behavior. The library does not choose your world scale or frame scheduler.

The Java example creates a circle with radius `0.5`, then assigns normal mass. The Kotlin test checks circle area, body fixture density, mass, and mutable velocity. See [the Java example](../../dyn4k/src/jvmTest/java/IdiomaticJavaExample.java) and [the Kotlin API journey](../../dyn4k/src/commonTest/kotlin/io/github/rubixhacker/dyn4k/IdiomaticApiTest.kt).

### Joints and stepping

Use the baseline joint classes when you need the exact dyn4j contract. Kotlin also offers builders for concrete joint objects. Create the joint from the shared bodies, add it to the world, then step the world with an explicit count or time step.

The Kotlin API test checks a distance joint and generic concrete-joint builder. The staged Java [JointConsumer](../../dyn4k-core/src/jvmConsumer/java/JointConsumer.java) covers ten joint types and extension access. The staged [JointMechanismConsumer](../../dyn4k-core/src/jvmConsumer/java/JointMechanismConsumer.java) checks 120 states. Those Java consumers ran against candidate artifacts in the [Build and extend a simulation with the idiomatic Kotlin API](https://github.com/rubixhacker/dyn4k/issues/41) report; they do not establish all joint modes or target runtimes.

### Queries, callbacks, and live objects

World helpers support bounds and shape overlap queries, ray casts, closest ray results, and moving-shape casts. Predicates receive the actual world body and fixture. Callback helpers register baseline listeners and return the listener object for later removal.

The checked Kotlin test exercises overlap, ray, closest ray, sweep, step callbacks, contact callbacks, and listener removal. See [query and callback cases](../../dyn4k/src/commonTest/kotlin/io/github/rubixhacker/dyn4k/IdiomaticApiTest.kt). The Java [WorldAdvancedConsumer](../../dyn4k-core/src/jvmConsumer/java/WorldAdvancedConsumer.java) drives CCD, solver overrides, and contact callbacks on its JVM consumer journey.

## Mutable state, identity, and extensions

The API exposes mutable references by design. A body velocity property returns the core velocity object. Fixture lists and world body and joint lists are live views. Named mutation methods change the same vector seen by every reference. Compound assignment instead rebinds the variable on its left; aliases keep the previous vector. Do not retain a live view as an immutable snapshot. Use `copy()` when you need an independent value, and verify the copy type and depth for the specific class.

Java subclasses can override virtual methods and access protected fields through the compatibility classes. The [JointConsumer](../../dyn4k-core/src/jvmConsumer/java/JointConsumer.java) checks a protected joint field and an overridden getter. The [WorldAdvancedConsumer](../../dyn4k-core/src/jvmConsumer/java/WorldAdvancedConsumer.java) checks custom detector and solver dispatch. These are bounded JVM examples.

Full Java source compatibility remains **unpassed**. The declaration ledger lists open compatibility obligations. Earlier audit findings and active repairs are revision-scoped; recheck the ledger and candidate instead of treating a finding from an older revision as current. The named-module source slice has only the bounded combined-source result described above; its candidate ledger mapping, ledger replay, and full compatibility remain unpassed. The extension consumers cover specific protected-field and dispatch cases. Re-run them against the exact candidate JAR you ship. Do not infer full compatibility from a successful class-path build or a result from a branch that has not merged into the candidate.

## Errors, nulls, and copies

The compatibility layer aims to preserve dyn4j 6.0.0 exception types, null behavior, class-based filtering, copy behavior, iterator behavior, and callback order. Kotlin non-null types can make some Java null calls impossible in Kotlin source; Java callers still need the Java-facing contract. A Kotlin compile is not a check of Java null behavior.

Use the checked collision and dynamics consumers for the cases they name. Consult the [compatibility ledger](../planning/implementation-ledger.md) and [full compatibility work](https://github.com/rubixhacker/dyn4k/issues/42) for incomplete declarations and cases. Do not assume that unlisted edge cases passed.

## Duplicate providers

Do not include both `org.dyn4j:dyn4j:6.0.0` and `io.github.rubixhacker:dyn4k-core:0.1.0-alpha.1` in one runtime graph. Both provide `org.dyn4j` classes. The staged consumer reports `duplicate org.dyn4j provider` and directs you to exclude the upstream dependency. If another library adds dyn4j transitively, exclude it there and verify the resolved graph.

```kotlin
implementation("some.library:uses-dyn4j:1.2.3") {
    exclude(group = "org.dyn4j", module = "dyn4j")
}
```

The check is in [qualification/build.gradle.kts](../../consumers/qualification/build.gradle.kts). It verifies dependency resolution for the staged JVM consumer. It does not detect every possible class-loader or shaded-JAR conflict.

## Qualification results and open gates

The preview is for evaluation. The [Build and extend a simulation with the idiomatic Kotlin API](https://github.com/rubixhacker/dyn4k/issues/41) report records direct Kotlin tests on JVM, Linux x64, JS Node, Wasm JS Node, Wasm WASI Node, and Android host. It also records staged JVM and portable consumers and Java 8 bytecode inspection. Those results are tied to candidate artifacts and source revision `68c2cea`, the base of this guide branch. They are not all-target or release evidence.

The complete scope remains **unpassed** for:

- The unchanged headful Java sample application and its Tracking, Pyramid, Crank, Billiards, and Truck journeys.
- The 21 targets and 28 minimum/current runtime families, including physical Apple devices, Android device ABIs, Safari, Wasmtime, old Linux kernels, and Windows.
- Complete Java declaration, null, protected-field, and named-module compatibility.
- Candidate numerical parity on all targets.
- Physical quality. The pinned baseline default sleep/wake penetration gate failed in 125,847 of 126,000 end states. The configured profile uses internal step `1/120 s` and outer groups of 4, 2, or 1. It is separate and does not replace the default result. The pinned baseline `nsoft1.dat` area-conservation check also fails. Candidate physical qualification remains **unpassed**. Weld/Pulley physical checks remain separate from parity checks.
- Sustained performance, allocation, memory, and stable release gates.

A passing preview consumer or host test does not close these gates. Use [qualification results and current gates](../verification/qualification-harness.md) and the linked implementation issues for exact status.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Gradle cannot resolve `0.1.0-alpha.1` | Add the local staging repository before Maven Central. Confirm both module coordinates and the staged version. |
| Duplicate `org.dyn4j` classes appear | Inspect the resolved graph. Exclude `org.dyn4j:dyn4j` from the dependency that adds it. Keep one provider. |
| Java module compilation cannot find `org.dyn4j` | Check the staged `dyn4k-core-jvm` provider identity and the `org.dyn4j` module name. Use the class path for Java 8. |
| A Java extension no longer sees or overrides a member | Compile the subclass consumer with `--release 8`, then run the relevant protected-field and dispatch consumer against the candidate JAR. Record the exact artifact hash. |
| A preview test passes but release support is unclear | Check target, runtime, build mode, expected and executed counts, skips, consumer result, commit, and artifact hashes. Missing lane evidence is unpassed. |

## Evidence references

- [Idiomatic Kotlin API journey](../../dyn4k/src/commonTest/kotlin/io/github/rubixhacker/dyn4k/IdiomaticApiTest.kt)
- [Mixed Java and Kotlin identity journey](../../dyn4k/src/jvmTest/kotlin/io/github/rubixhacker/dyn4k/IdiomaticMixedExampleTest.kt)
- [Java 8 source example](../../dyn4k/src/jvmTest/java/IdiomaticJavaExample.java)
- [Joint and protected-field consumer](../../dyn4k-core/src/jvmConsumer/java/JointConsumer.java)
- [CCD, solver, and callback consumer](../../dyn4k-core/src/jvmConsumer/java/WorldAdvancedConsumer.java)
- [Staged JVM consumer](../../consumers/qualification/build.gradle.kts)
- [Staged consumer behavior](../../consumers/qualification/src/main/kotlin/qualification/Consumer.kt)
- [Toolchain and consumer floors](https://github.com/rubixhacker/dyn4k/blob/db4a13856aaf4bef089d1a93250971ff4e3d2f34/docs/research/consumer-floors.md)
- [Approved runtime contract](https://github.com/rubixhacker/dyn4k/issues/6)
- [Complete-port specification](../specs/complete-port.md)
