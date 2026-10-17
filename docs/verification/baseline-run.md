# dyn4j 6.0.0 baseline corpus

The unchanged upstream JVM suite passes against the pinned dyn4j binary. JUnit executed 2,385 cases with zero failures and zero ignored cases. The source has 2,171 `@Test` annotations across 199 Java test files. Annotation count is not the executed case count.

The oracle uses source revision `058bf6d982a0fb89b54050f929f6ea9dae53b714` and coordinate `org.dyn4j:dyn4j:6.0.0`. The binary SHA-256 is `204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e`. The sources JAR SHA-256 is `83b47be47bdce27681139dab84937e0f586b70ab800dc494fbebed4b58893223`.

The run used `javac 25.0.3` and OpenJDK 25.0.3. `javac --release 8` restricted API use and bytecode for the unchanged upstream tests and the JUnit harness. The harness classfile major version is 52. Test resources were copied to the runtime class path. The run compiled and executed 190 test classes. The machine report records SHA-256 hashes for all 218 test source and resource inputs, JUnit, and Hamcrest.

Run `tools/baseline/verify.sh` to reproduce the result. The command verifies both artifact hashes, checks the pinned source revision, rejects dirty and untracked source inputs, and compares every sources-JAR Java entry with its tracked production bytes. It checks the 268 production and 199 test Java file counts, generates the JVM declaration inventory with `javap`, compiles the unchanged tests, and records the JUnit result. It requires exactly 2,385 executed cases, zero failures, zero ignored cases, and a successful process exit.

`baseline-inventory.json` records all 297 binary types and the full `javap -protected -s` output for each type. It identifies 216 public or protected API types. The other types remain in the inventory but are not required in a candidate JAR. Use `tools/baseline/verify.sh --candidate PATH` to compare a complete candidate JAR. The structural comparator accepts added declarations and order changes while checking required generic declarations, access, staticness, instance finality, and type contracts.

A selective comparison of six foundation geometry classes found four missing baseline methods: `getCost()` and `getSint()` on both `Rotation` and `Transform`. `Matrix22`, `Matrix33`, `Vector2`, and `Vector3` had no structural mismatches. That candidate JAR contains 19 types; this selective result does not claim complete JAR compatibility.

This result qualifies the upstream oracle run. It does not report dyn4k parity or physical qualification.
