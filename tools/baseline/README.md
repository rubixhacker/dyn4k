# Baseline corpus

Run `tools/baseline/verify.sh` from the repository root. The command downloads the pinned dyn4j 6.0.0 binary and sources JAR, checks their SHA-256 values, checks out source revision `058bf6d982a0fb89b54050f929f6ea9dae53b714`, and writes a complete declaration inventory and JUnit run summary.

The default cache is `.cache/baseline`. It contains upstream artifacts and generated test classes. The inventory and run summary are written to `docs/verification/baseline-inventory.json` and `docs/verification/baseline-run.json`. Keep those outputs with the commit that records the run.

Use `--candidate PATH` to compare public and protected JVM signatures in a candidate JAR with the pinned baseline. Use `--inventory-only` to refresh the inventory without running tests. Run `tools/baseline/verify.sh --help` for path overrides.

The JAR is the production dependency for the oracle only. The runner compiles the unchanged upstream tests with JUnit 4.13.1 and Hamcrest 1.3, then executes test classes in one JUnit process. It includes `src/test/resources`. JDK 25 uses build-only `-source 8 -target 8` flags because the upstream POM uses Java 6 flags. No upstream source is changed.

`test_annotations` is a source inventory value. `actual_executed_cases` comes from JUnit's run count and can differ because parameterized tests expand and runners can add or ignore cases. This corpus establishes the fixed oracle; it does not qualify dyn4k numerical parity or physical behavior.

The upstream license text is retained in `tools/baseline/UPSTREAM-LICENSE.md`. The tool does not edit upstream files.
