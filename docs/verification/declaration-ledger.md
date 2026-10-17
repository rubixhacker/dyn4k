# Declaration and test coverage ledger

## Result

The [machine-readable ledger](../../tools/compatibility/declaration-ledger.json) records every pinned baseline obligation. It currently fails candidate validation. Its 268 production files, 199 test files, 3,392 declaration identities, and named-module obligation have no candidate counterparts or executed candidate evidence. The declaration set includes 297 JVM type identities, including nested types. Each declaration has a source owner. The validator checks each identity against the independent baseline oracle, pinned source checkout, and pinned binary. Matching totals alone cannot pass.

The baseline has 2,171 textual `@Test` annotations. Its [executed baseline report](baseline-run.json) records 2,385 actual JUnit cases, zero failures, and zero ignored cases. The report's input map must match the pinned 199 Java test files and 19 test resources by exact path and SHA-256. These are different measurements. Neither count establishes candidate coverage.

## Reproduce

Use the pinned source checkout at `058bf6d982a0fb89b54050f929f6ea9dae53b714`. Provide the exact binary JAR and source JAR. The validator checks SHA-256 values against the existing `tools/baseline/verify.py` oracle and checks the source archive against tracked source bytes.

```bash
python3 -m unittest discover -s tools/compatibility -p 'test_*.py' -v
python3 tools/compatibility/ledger.py validate \
  --source /tmp/dyn4k-upstream-6.0.0 \
  --jar /tmp/dyn4k-baseline-cache/dyn4j-6.0.0.jar \
  --sources-jar /tmp/dyn4k-baseline-cache/dyn4j-6.0.0-sources.jar \
  --report /tmp/dyn4k-issue49-partial.json
```

Exit 0 means every required identity has a current counterpart and valid evidence. Exit 1 means structurally valid but unpassed coverage. Exit 2 means missing, duplicate, changed, or invalid ledger data. The report lists each gap and the candidate revision. Generation refuses to overwrite an existing ledger, so new evidence cannot be erased by an inventory refresh.

## Attach evidence as slices land

Update each `candidate` from `null` to an object with `identity`, 40-character `commit`, relative `artifact` path, and its 64-character `artifact_sha256`. The validator checks artifact bytes and requires the candidate commit to match the checked-out revision. A production-file counterpart names its implementation source. A declaration counterpart names its candidate JVM declaration. A test-file counterpart names its unchanged Java test source or runner input. Map each candidate identity once within its section.

Add evidence objects with a `kind`, `status`, and, for a passed result, `target`, `report` path, and `report_sha256`. Nonpassing statuses are `missing`, `unrun`, `ignored`, and `unapproved_exception`. They remain gaps. A passed report must repeat the exact evidence kind and target from the ledger record. It must bind the baseline pins, candidate identity, commit, artifact checksum, and baseline source-file checksum. A report checksum protects bytes but does not prove that a command ran.

The validator currently accepts generic passed reports only for `java-signature` on `jvm` with `schema_version: 2` and `probe: "javap-signature-v1"`. The candidate identity must equal the exact declaration ID. The report contains `passed_identities: [ID]`, an `execution` object, and matching top-level `command`, `expected_cases`, `actual_executed_cases`, `failures`, `ignored`, `process_exit_code`, `raw_stdout`, `raw_stderr`, and `output` fields. The validator runs `javap -protected -s` itself against the checksum-verified candidate JAR and compares every execution field. It requires one matching declaration, zero failures and ignored cases, and a zero process exit code. It never executes a command supplied by a report. A stale or invented result is invalid even when its report checksum has been updated.

The fixed `javap` probe checks one JVM declaration; it does not establish Java test execution, portable behavior, or implementation correctness. `java-test`, `common-portable`, and `implementation` passed claims have no allowlisted probe yet and are invalid. They still count as required gaps. As slices land, [Run the full compatibility corpus and unchanged migration applications](https://github.com/rubixhacker/dyn4k/issues/42) must add reviewed executable fixtures or authenticated runners with exact identity and target binding, expected and executed case counts, failures, skips, and raw output. A fixture must exercise the claimed candidate behavior. A fixture that prints green markers without checking behavior cannot satisfy this contract. Unavailable runtimes remain `unrun`; they cannot be replaced by another target's result.

The required kinds are `implementation` for production files, `java-signature` and `common-portable` for declarations, and `java-test` for test files. A passed kind requires its own executable evidence. The full compatibility task must attach unchanged Java compilation and execution results to the Java identities, including public fields, protected extension behavior, nested types, live views, and mixed API identity. It must attach common portable tests for every functional area and run them on each required target and build configuration. It must record actual case counts separately from annotations. Runtime, numerical, physical, migration-application, and release qualification remain separate gates under [Run the full compatibility corpus and unchanged migration applications](https://github.com/rubixhacker/dyn4k/issues/42).

## Named Java module obligation

`src/main/java/module-info.java` is both a pinned production source and a separate executable obligation. The baseline declares `org.dyn4j` and exports 17 packages. The ledger fixes the source SHA-256, name, exact export set, and the bytes of the [unchanged two-file consumer](../../tools/compatibility/fixtures/named_module/module-info.java). The pinned baseline JAR passes descriptor inspection and compilation and execution of that consumer with `javac --release 9`. The current staged candidate derives another automatic module name, so this gate remains unpassed.

The module entry needs a candidate mapping with `identity: "org.dyn4j"`, the current commit, a relative staged JAR path, and its SHA-256. Three evidence kinds are required: `module-descriptor`, `named-module-consumer`, and `java8-classpath`. The first checks an explicit descriptor with exactly the baseline name and 17 exports. The second compiles both unchanged fixture files with `javac --release 9` and runs the named consumer on the module path. The third compiles the unchanged main source with `javac --release 8` and runs it on the classpath using a Java 8 runtime. This classpath gate remains separate from the named-module gate.

A passed module evidence record names a JSON report and its SHA-256. The report binds the baseline pins, candidate commit and JAR hash, source and fixture hashes, evidence kind, exact dependency JAR paths and hashes, and the observed result. For `java8-classpath`, it also binds a Java 8 executable path and checksum. `module_probe.py` can write a report with `--output` after the module candidate mapping is recorded; it refuses to overwrite an existing report. The validator rejects any baseline JAR in the candidate or dependency set and reruns each claimed passed probe against the recorded staged artifacts. It compares the new observation with the report. A missing report, a forged pass, an automatic module, unavailable Java 8 runtime, compile failure, or run failure cannot pass. A future staged probe must resolve the Kotlin runtime through its recorded module-path dependencies; the ledger does not infer that from a classpath result.
