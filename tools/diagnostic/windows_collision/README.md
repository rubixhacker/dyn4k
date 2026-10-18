# Windows collision focus routes

Dispatch `.github/workflows/windows-collision-focus.yml` at an exact reviewed commit and select one route.

- `historical-pc53` retains the original six fixture suites, the nine exact ordinary assertion failures, and the separate PC53 before/active/restored invocation. Its precision validator requires the historical nine-failure set. It is evidence about the earlier defect, not a production pass.
- `corrected-production` requires all 24 original fixture cases and six diagnostic cases to pass in one `mingwX64Test` invocation. It retains the same 72 Native and 72 pinned dyn4j Java trace rows, seven Native/Java scalar rows, and the actual debugTest PE. It compiles `SqrtOperationNativeProbe.kt` with the committed common and Native `NearestSqrt` sources in both MinGW `-g` and `-opt` modes. Each executable must finish with seven exact input rows, 18 neighbor rows, seven edge rows, and the complete PASS marker.

The corrected route writes `corrected-probe/source-sha256.txt` for the eight engine files and probe source. Each mode directory contains the compiler command, bounded compiler and run receipts, exit codes, stdout/stderr, PE, and PE SHA-256. The validator binds each command receipt to these paths and compares every source hash with both the checkout and the dispatched Git object. The workflow also retains the bounded Gradle command/receipt, separate Gradle and Java stdout/stderr, seven XML reports, the test PE and SHA-256, pinned Java source and JAR evidence, runtime identity, and the full SHA-256 inventory. A missing, skipped, errored, failed, partial, or timed-out required output fails the corrected route; the artifact upload still runs.

Local controls:

```sh
TMPDIR="$HOME/tmp" python tools/diagnostic/windows_collision/validate-precision-control.py self-test
TMPDIR="$HOME/tmp" PYTHONDONTWRITEBYTECODE=1 python -m unittest tools/diagnostic/windows_collision/test_validate_precision_corrected.py
actionlint .github/workflows/windows-collision-focus.yml
```

The corrected route is a focused Windows gate. It does not qualify the full target matrix or replace the original fixture assertions.
