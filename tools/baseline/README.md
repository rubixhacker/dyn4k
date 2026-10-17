# Baseline corpus

Run `tools/baseline/verify.sh` from the repository root. The command downloads the pinned dyn4j 6.0.0 binary and sources JAR, checks their SHA-256 values, checks out source revision `058bf6d982a0fb89b54050f929f6ea9dae53b714`, and writes a complete declaration inventory and JUnit run summary.

The default cache is `.cache/baseline`. It contains upstream artifacts and generated test classes. The inventory and run summary are written to `docs/verification/baseline-inventory.json` and `docs/verification/baseline-run.json`. Keep those outputs with the commit that records the run.

Use `--candidate PATH` to compare a candidate JAR with the pinned baseline. The comparator checks public and protected types, members, generic declarations, superclass contracts, access, and method modifiers. It accepts added declarations, added interfaces, member order changes, wider access, and removal of method or type `final`. It rejects added `final`, including on static methods, and keeps field finality exact because removing it can break Java constant use. It skips compiler bridge and synthetic methods while keeping the source method. An interface inherited through another candidate interface or superclass satisfies the same source contract. Exact accepted changes remain in `compatible_differences`; missing or incompatible contracts remain in `missing_types` and `signature_mismatches`. It inventories internal types but does not require a candidate to retain them. A complete candidate must still supply every baseline API type. Use `python3 tools/baseline/verify.py compare --baseline-jar BASELINE --candidate CANDIDATE --only TYPE` to inspect selected types. A selected comparison does not qualify a full JAR.

Use `--inventory-only` to refresh the inventory without running tests. Run `tools/baseline/verify.sh --help` for path overrides.

The JAR is the production dependency for the oracle only. The runner compiles the unchanged upstream tests with JUnit 4.13.1 and Hamcrest 1.3, then executes test classes in one JUnit process. It includes `src/test/resources`. `javac --release 8` limits the harness and tests to Java 8 APIs and bytecode. The report records compiler and runtime versions, harness bytecode version, dependency hashes, and each test input hash. No upstream source is changed.

The verifier rejects changed, untracked, or ignored source inputs before checkout. It checks every production Java entry in the sources JAR against the pinned Git revision. It leaves a dirty checkout in place and reports the problem. The suite must run exactly 2,385 cases with no failures or ignored cases. `check-run --report PATH` checks a saved run report.

`test_annotations` is a source inventory value. `actual_executed_cases` comes from JUnit's run count and can differ because parameterized tests expand and runners can add or ignore cases. This corpus establishes the fixed oracle; it does not qualify dyn4k numerical parity or physical behavior.

The upstream license text is retained in `tools/baseline/UPSTREAM-LICENSE.md`. The tool does not edit upstream files.
