# dyn4j 6.0.0 baseline corpus

The unchanged upstream JVM suite passes against the pinned dyn4j binary. JUnit executed 2,385 cases with zero failures and zero ignored cases. The source has 2,171 `@Test` annotations across 199 Java test files. Annotation count is not the executed case count.

The oracle uses source revision `058bf6d982a0fb89b54050f929f6ea9dae53b714` and coordinate `org.dyn4j:dyn4j:6.0.0`. The binary SHA-256 is `204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e`. The sources JAR SHA-256 is `83b47be47bdce27681139dab84937e0f586b70ab800dc494fbebed4b58893223`.

The run used OpenJDK 25.0.3 and `javac -source 8 -target 8` for upstream tests. Those flags address the upstream POM's Java 6 compiler settings without changing source. Test resources were copied to the runtime class path. The run compiled and executed 190 test classes.

Run `tools/baseline/verify.sh` to reproduce the result. The command verifies the two artifact hashes, checks out the pinned source commit, checks the 268 production and 199 test Java file counts, generates the JVM declaration inventory with `javap`, compiles the unchanged tests, and records the JUnit result. It stops on missing or invalid artifacts, source count drift, or an empty test suite. The inventory also lists every test file and its annotation count.

`baseline-inventory.json` records all 297 types in the binary and the full `javap -protected -s` output for each type. This includes public and protected JVM members and nested types. Use `tools/baseline/verify.sh --candidate PATH` to compare a candidate JAR against the baseline inventory.

This result qualifies the upstream oracle run. It does not report dyn4k parity or physical qualification.
