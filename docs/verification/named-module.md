# Named Java module compatibility

The staged `dyn4k-core-jvm` JAR supplies the baseline module name `org.dyn4j`.
Its explicit Java 9 descriptor exports the same 17 packages as the pinned
[dyn4j 6.0.0 descriptor](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/module-info.java).
It also requires `kotlin.stdlib`, which the staged POM declares at version
2.4.20. The descriptor is at the JAR root. Java 8 ignores it when the JAR is
used on the classpath. The staged sources JAR includes the descriptor source
and its upstream copyright notice.

## Public consumer evidence

The unchanged two-file Java fixture is in
[`tools/compatibility/fixtures/named_module`](../../tools/compatibility/fixtures/named_module).
Its `module-info.java` says `requires org.dyn4j;`. Its `Main.java` constructs a
`Vector2` and checks its magnitude. JDK 21 compiled and ran this source on the
module path against both the pinned baseline and the staged candidate. JDK 21
also compiled the unchanged main source with `--release 8`; Java 8 ran it on
the classpath against the staged candidate. No baseline JAR was on the
candidate module path or classpath.

Before this change, the staged candidate derived the automatic module name
`dyn4k.core.jvm`. Descriptor inspection failed, and the unchanged modular
source failed with `module not found: org.dyn4j`. After this change,
`jar --describe-module` reports an explicit `org.dyn4j` descriptor with all
17 exports and `requires kotlin.stdlib`. `jdeps --print-module-deps` reports
`java.base,kotlin.stdlib`. The existing module probe passed descriptor,
Java 21 module consumer, and Java 8 classpath checks.

The [negative consumer tests](../../tools/qualification/module/negative_tests.py)
repack a temporary copy of the staged JAR without its descriptor and with a
descriptor that omits `org.dyn4j.geometry`. The unchanged source fails for the
wrong name and missing export. Removing the Kotlin runtime from the module
path fails at boot layer resolution. These checks prove that the passing
consumer depends on the intended module identity, export, and runtime path.

A raw Java module path can contain both the baseline and staged `org.dyn4j`
JARs. Java selects the first provider in this case; the unchanged consumer can
pass with either order. Run `module_probe.py` with every intended module-path
JAR before claiming the staged provider ran. Its named-module mode rejects
duplicate `org.dyn4j` providers before compilation and reports both resolved
paths and SHA-256 hashes. It also checks that the sole provider is the `--jar`
argument. A named-module pass requires `--expected-provider-sha256` from an
independent staged artifact record. Omitting it returns a nonpass result before
compilation. Use the pinned baseline SHA for a baseline-only check. An ordinary
Java build does not invoke this check automatically. The Gradle qualification
consumer has a separate resolved dependency-graph guard and an adverse
duplicate-dependency test.
The negative runner checks both provider orders, an older JAR without an
expected SHA, a wrong provider path, and a baseline JAR supplied as the wrong
staged candidate.

## Reproduce

Use JDK 21 for Gradle, `javac`, `java`, `jar`, and `jdeps`. Set `ANDROID_HOME`
to the installed SDK for the Android host test. The baseline JAR must have
SHA-256 `204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e`.
Set `EXPECTED_CORE_SHA256` from the staged publication record, independent of
the JAR supplied to the probe.

```sh
./gradlew :dyn4k-core:publishJvmPublicationToStagingRepository :dyn4k:publishJvmPublicationToStagingRepository
python3 tools/compatibility/module_probe.py --jar build/staging-repository/io/github/rubixhacker/dyn4k-core-jvm/0.1.0-alpha.1/dyn4k-core-jvm-0.1.0-alpha.1.jar --mode module-descriptor
python3 tools/compatibility/module_probe.py --jar "$BASELINE_JAR" --mode named-module-consumer --expected-provider-sha256 204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e
python3 tools/compatibility/module_probe.py --jar build/staging-repository/io/github/rubixhacker/dyn4k-core-jvm/0.1.0-alpha.1/dyn4k-core-jvm-0.1.0-alpha.1.jar --mode named-module-consumer --dependency "$KOTLIN_STDLIB_JAR" --expected-provider-sha256 "$EXPECTED_CORE_SHA256"
python3 tools/compatibility/module_probe.py --jar build/staging-repository/io/github/rubixhacker/dyn4k-core-jvm/0.1.0-alpha.1/dyn4k-core-jvm-0.1.0-alpha.1.jar --mode java8-classpath --dependency "$KOTLIN_STDLIB_JAR" --java8-java "$JAVA8_HOME/bin/java"
python3 tools/qualification/module/negative_tests.py --candidate build/staging-repository/io/github/rubixhacker/dyn4k-core-jvm/0.1.0-alpha.1/dyn4k-core-jvm-0.1.0-alpha.1.jar --baseline "$BASELINE_JAR" --stdlib "$KOTLIN_STDLIB_JAR" --java8 "$JAVA8_HOME/bin/java"
```

The bounded unchanged upstream foundation and geometry suites passed 133/133
and 446/446 cases. The common suite passed 510 cases on each of six available
host configurations:
JVM, Linux x64, JS Node, Wasm JS Node, Wasm WASI Node, and Android host.
Each host reported zero failures, errors, and skips. This verifies the
publication change on those hosts. It does not execute the full 2,385-case
candidate Java suite, the five unchanged migration applications, Android
device tests, Apple or Windows runtimes, or the complete 21-target matrix.
These remain open under
[Run the full compatibility corpus and unchanged migration applications](https://github.com/rubixhacker/dyn4k/issues/42).
