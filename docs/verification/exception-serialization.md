# Exception serialization compatibility

The fixed dyn4j 6.0.0 baseline declares a private static final `serialVersionUID` in each of its nine `org.dyn4j.exception` classes. The pinned [source revision](https://github.com/dyn4j/dyn4j/tree/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/exception) is the source for the values below. The baseline JAR SHA-256 is `204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e`.

| Exception | UID |
| --- | ---: |
| ArgumentNullException | 7104871716542808869 |
| CopyException | 2434249738746680073 |
| EmptyCollectionException | 3188055341987092721 |
| SameObjectException | -2844289260493601312 |
| InvalidIndexException | 1297019115982655104 |
| ValueOutOfRangeException | -7115378379246433066 |
| ObjectAlreadyExistsException | 3414084132509765709 |
| ObjectAlreadyOwnedException | -7471557485578931121 |
| NullElementException | 4560521220204618552 |

The [fixture](../../tools/compatibility/fixtures/exception_serialization/verify.py) accepts a pinned baseline JAR, a staged JVM JAR, and a staged Android classes JAR. It never imports project source outputs. Java 8 compiles the same consumer source against all three archives. `javap` checks each declared field's private static final identity and exact value. The Java probe checks the field and Java serialization's effective UID independently. Java 8 and Java 21 each write and read all 15 constructor variants with every provider pair. The checks compare exception type, message, cause, suppressed exception, and stack frame with the baseline. Optional previous archives let `javap -public` reject added source-visible members.

Run with the two candidate archives staged from the same source tree:

```sh
python3 tools/compatibility/fixtures/exception_serialization/verify.py \
  --baseline "$BASELINE_JAR" --jvm "$STAGED_JVM_JAR" \
  --android "$STAGED_ANDROID_CLASSES_JAR" \
  --java8 "$JDK8_HOME" --java21 "$JDK21_HOME" \
  --stdlib "$KOTLIN_STDLIB_JAR" --output "$RESULT_DIR"
```

The runner writes frozen archive copies, serialized streams, commands, process output, archive hashes, and a JSON report. It exits nonzero for a missing or wrong field, a failed Java compile, a changed payload, or a failed cross-provider read. The Android classes JAR runs on a JVM host here. This check does not establish Android device or other target runtime qualification.

## Bounded host observation

The pre-repair staged JVM and Android archives failed the permanent fixture with 18 missing-field checks and 148 process mismatches. The repaired staged JVM JAR is `79b285fd38d052198d33df7cdfc51e636daddcf083866e076d2051dd0c0bc761` (SHA-256). The repaired Android classes JAR is `98e9635682d1f6bc4d70c893b2b8832e06e2a7e21742b7e1dbd4b20b0b0c4293` (SHA-256). These archives passed all 27 classfile identity checks, 18 comparisons with the earlier public API, and 636 Java serialization processes with zero failures. The process matrix contains 90 writes and 540 reads across the two JDKs and three providers.

The common core suite passed 932 tests on each of six available hosts: JVM, Linux x64, JS Node, Wasm JS Node, Wasm WASI Node, and Android host. The unchanged Java exception and collision model suite passed 114 tests; the geometry suite passed 446. Both geometry consumers passed 26 checks. The existing JVM and geometry Java API verifiers passed. The local evidence report is `/tmp/dyn4k-exception-serialization-worker-result.md`; the full process record is `/tmp/dyn4k-exception-serialization-fixture-green/result.json`.
