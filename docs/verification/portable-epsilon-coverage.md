# Portable Epsilon coverage

This record maps the one pinned `EpsilonTest.compute` identity to one common Kotlin test. It does not qualify the full compatibility corpus or target contract.

## Identity and assertions

The source is [`EpsilonTest.java`](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/EpsilonTest.java) at revision `058bf6d982a0fb89b54050f929f6ea9dae53b714`. Its SHA-256 is `b8428305c70ab4a5b7329d6630346cbc9e1057d5f4d93774483059215818511c`. The source has one executed case: `org.dyn4j.EpsilonTest.compute`.

The common counterpart is `org.dyn4j.coverage.epsilon.UpstreamEpsilonCoverageTest.compute` in `dyn4k-core/src/commonTest/kotlin/org/dyn4j/coverage/epsilon/UpstreamEpsilonCoverageTest.kt`.

| Original assertion or action | Common counterpart |
| --- | --- |
| `Epsilon.E != 0.0` | `assertTrue(Epsilon.E != 0.0)` |
| Call `Epsilon.compute()` and require it to return | Store its result and require it to equal `Epsilon.E` |
| `1.0 + Epsilon.E == 1.0` | `assertEquals(1.0, 1.0 + Epsilon.E)` |
| Independent boundary check | Require `1.0 + 2.0 * computed > 1.0` |

The boundary check distinguishes the computed increment from a smaller wrong value. The test retains the pinned BSD notice. It adds no production code.

## JVM evidence

The baseline artifact is dyn4j 6.0.0 JAR SHA-256 `204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e`. The candidate JAR SHA-256 is `027f3e5f7001af2849a84d6106decd1f1adea58a68ba9e40b94fd0928eb74cb5`.

JDK 21 compiled the unchanged Java source with `javac --release 8`. The same class file, SHA-256 `453238fcd98dbb88dc826008e5af2b0f3f5bec10abd2a577c5b57157159be005`, ran with JUnit 4.13.1 on Temurin Java 8 `1.8.0_504-b01` and Java 21 `21.0.12.1+1-LTS`.

| Provider | Runtime | Cases | Failures |
| --- | --- | ---: | ---: |
| Pinned baseline | Java 8 | 1 | 0 |
| Pinned baseline | Java 21 | 1 | 0 |
| Candidate | Java 8 | 1 | 0 |
| Candidate | Java 21 | 1 | 0 |

Baseline output is `/tmp/dyn4k-epsilon-java-baseline.log`, SHA-256 `7dced01d57f9492e980e1b296a111dde644680aae302da175e5cd48da4280c74`. Candidate output is `/tmp/dyn4k-epsilon-java-candidate-final.log`, SHA-256 `41b327120b7b5f1d7ba7f9c0a840ac8c41dd56aeb1b59dc2bef6861bc89edd8d`.

The compile command was:

```sh
/tmp/dyn4k-tools/jdk21/bin/javac --release 8 \
  -cp "$PROVIDER:$JUNIT_JAR:$HAMCREST_JAR" \
  -d /tmp/dyn4k-epsilon-java/classes \
  /tmp/dyn4k-upstream-6.0.0/src/test/java/org/dyn4j/EpsilonTest.java
```

Each runtime then used:

```sh
JAVA=/tmp/dyn4k-tools/jdk8/bin/java # Repeat with /tmp/dyn4k-tools/jdk21/bin/java.
"$JAVA" -cp "$CLASSES:$PROVIDER:$JUNIT_JAR:$HAMCREST_JAR:$KOTLIN_STDLIB" \
  org.junit.runner.JUnitCore org.dyn4j.EpsilonTest
```

For baseline, `PROVIDER` was the pinned JAR and `KOTLIN_STDLIB` was omitted. For candidate, `PROVIDER` was the candidate JAR. The unchanged source compiled once and ran in four separate JVM processes.

## Six available common hosts

The final source ran with:

```sh
JAVA_HOME=/tmp/dyn4k-tools/jdk21 \
ANDROID_HOME=/var/home/stewart/Android/Sdk \
PATH=/tmp/dyn4k-tools/jdk21/bin:$PATH \
./gradlew --no-daemon --rerun-tasks --console=plain \
  :dyn4k-core:jvmTest :dyn4k-core:linuxX64Test :dyn4k-core:jsNodeTest \
  :dyn4k-core:wasmJsNodeTest :dyn4k-core:wasmWasiNodeTest \
  :dyn4k-core:testAndroidHostTest
```

Gradle completed successfully. The mapped Epsilon case ran once on each host. Each task's full core suite ran 287 cases with zero failures, errors, or skipped cases.

| Host task | Epsilon cases | Epsilon XML SHA-256 | Full task cases | Full task XML SHA-256 |
| --- | ---: | --- | ---: | --- |
| `jvmTest` | 1, 0 skipped | `2b458fd74cc6bdaa82518a9bbfd22237703a88f94d40e947a8cfe526fedcec52` | 287 | `babaa960b505700c8b51adea60c680462165cebfd4921774e635463ac2684c36` |
| `linuxX64Test` | 1, 0 skipped | `4a8cc01b4c265b94dc4c491fcdaa6556050723f36366f57cddf96a3e1fa22469` | 287 | `66157b4e5330650775a20c83ea731c3e7c9a86530324fe26ce77da93a6fdd58e` |
| `jsNodeTest` | 1, 0 skipped | `f887a5c3d52966307328fc9f4854c061386fd1834d2d51c068ef172e13b611fc` | 287 | `9310721109bacecb5b36fba6e2c326a90e3d16aba046041fb85baae36ca86afd` |
| `wasmJsNodeTest` | 1, 0 skipped | `b5bfa0956cddf9fbec55ac95a1903ebf77a4868d058a9667c294bbbc7a78b243` | 287 | `dd38e7a9caa425a335ea02ae398b683b2c5b6be3742b0cfdd00e348a1fd30128` |
| `wasmWasiNodeTest` | 1, 0 skipped | `b1f5bb86530f3a4ed7b8af17e514a6998667f5de63c36878fc15ca347334e4e8` | 287 | `562e65698b570c2adfc1402f2dde18684c5d03f609fe6b0df7a52ff03af61916` |
| `testAndroidHostTest` | 1, 0 skipped | `82925124882aa3c46473003a8a5f1c1cc37c47b7e688cb9d4ccaeb8775b879da` | 287 | `34a6453fdaee4eb4606d73e8a68abb29748d7e9c2ffb2bf090244becd61a580d` |

The individual Epsilon XML files are retained at `/tmp/dyn4k-epsilon-evidence/xml/`. Each listed full-task digest hashes the sorted concatenation of that task's raw `TEST-*.xml` files. The final Gradle output is `/tmp/dyn4k-epsilon-six-host-commit.log`, SHA-256 `14ccce14dedb2f9d10ca6ab91b44fd5221690e87fc0f3ecd7bc119c687de4e88`.

## Scope boundary

This evidence covers one portable identity on six available hosts and one unchanged Java identity on two JVM versions against two providers. It does not qualify the complete issue-42 corpus. It does not count supplementary Epsilon assertions as this source identity.

The 21 approved targets and 28 runtime families remain open, including Apple and Android devices, other native hosts, minimum/current runtime versions, and both build configurations. The five unchanged sample journeys, full Java test corpus against the final candidate, complete portable identity map, structural compatibility, numerical and physical checks, performance budgets, staged consumers, and release gates also remain open. The root inbox records 18 shape-pair failures in a frozen provisional full-corpus candidate artifact; this Epsilon-only run does not resolve those failures.
