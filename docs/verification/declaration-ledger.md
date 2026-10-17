# Declaration and test coverage ledger

## Result

The [machine-readable ledger](../../tools/compatibility/declaration-ledger.json) records every pinned baseline obligation. It currently fails candidate validation. Its 268 production files, 199 test files, and 3,392 declaration identities have no candidate counterparts or executed candidate evidence. The declaration set includes 297 JVM type identities, including nested types. Each declaration has a source owner. The validator checks each identity against the independent baseline oracle, pinned source checkout, and pinned binary. Matching totals alone cannot pass.

The baseline has 2,171 textual `@Test` annotations. Its [executed baseline report](baseline-run.json) records 2,385 actual JUnit cases, zero failures, and zero ignored cases. These are different measurements. Neither count establishes candidate coverage.

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

Add evidence objects with a `kind`, `status`, and, for a passed result, `report` path and `report_sha256`. Nonpassing statuses are `missing`, `unrun`, `ignored`, and `unapproved_exception`. They remain gaps. A passed report must bind the baseline pins, candidate identity, commit, artifact checksum, and baseline source-file checksum. It must name the executed command and passed identity. Its expected and actual executed case counts must match and be positive. The raw output must contain matching `ACTUAL_TESTS`, `FAILURES`, and `IGNORED` markers; failures, ignored cases, and process exit code must all be zero. The validator checks the report bytes before reading those fields. The report is an execution record; its checksum alone does not prove that a command ran. Retain the raw runner output and external job identity with the report for independent audit.

The required kinds are `implementation` for production files, `java-signature` and `common-portable` for declarations, and `java-test` for test files. A passed kind requires its own executable evidence. The full compatibility task must attach unchanged Java compilation and execution results to the Java identities, including public fields, protected extension behavior, nested types, live views, and mixed API identity. It must attach common portable tests for every functional area and run them on each required target and build configuration. It must record actual case counts separately from annotations. Runtime, numerical, physical, migration-application, and release qualification remain separate gates under [Run the full compatibility corpus and unchanged migration applications](https://github.com/rubixhacker/dyn4k/issues/42).
