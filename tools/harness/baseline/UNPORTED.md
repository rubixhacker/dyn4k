# What the baseline verifier port does not cover

This file covers one Python module: `tools/baseline/verify.py`. Its port lives in `:baseline`
(`commonMain` for the pure `javap` readers and the compatibility rules, `jvmMain` for the process,
Git and file-system work). The Python file is unchanged and remains the reference.

Parity evidence is `src/commonTest/.../BaselineVectors.kt`, recorded at git revision
`4430f2c5a1a94484ab66d291bf747ec1c5fe3d39`. Every recorded input and expectation was printed by the
Python implementation with `javac 25.0.3`. Regenerate it with:

```
python3 tools/harness/baseline/parity/generate_vectors.py \
    --kotlin tools/harness/baseline/src/commonTest/kotlin/io/github/rubixhacker/harness/baseline/BaselineVectors.kt
```

The generator builds throw-away JAR fixtures, so a commit identifier in a recorded `check-source`
output belongs to the fixture that produced it. The suites normalise the fixture root, the digests
and the fixture revision before they compare, and assert every other byte.

## `verify.py`

Ported in full:

| Python | Kotlin |
| --- | --- |
| `COMMIT`, `BINARY_SHA256`, `SOURCES_SHA256`, `BASE`, `JUNIT`, `HAMCREST`, `EXPECTED_CASES`, `REQUIRED_FIXTURE_SHA256` | `Baseline`, `BaselinePolicy` |
| `digest` | `digest` |
| `fetch` | `fetch` |
| `run` | `BaselineSeams.requireRun`, `CommandFailure` |
| `GIT_NETWORK_AUTH_ENV`, `git_environment` | `gitEnvironment` |
| `pinned_git` | `pinnedGit` |
| `jar_types` | `BaselineSeams.jarTypes` |
| `type_header` | `typeHeader` |
| `surface` | `surface`, `ApiSurface`, `MemberKey` |
| `split_top_level` | `splitTopLevel` |
| `type_contract` | `typeContract` |
| `source_compatible_declaration` | `sourceCompatibleDeclaration` |
| `constructor_list_widening` | `constructorListWidening` |
| `member_inventory` | `memberInventory`, `MemberRecord` |
| `source_visible` | `sourceVisible` |
| `private_nested_type` | `privateNestedType` |
| `added_member_gate` | `MemberAddition.gate`, `MemberRisk` |
| `fixture_audit` | `fixtureAudit`, `FixtureResult`, `FixtureAudit` |
| `compare_jars`, `_compare_jars_snapshot` | `compareJars`, `CompareReport` |
| `result_field` | `resultField` |
| `validate_run_report` | `validateRunReport` |
| `source_file_bytes` | `sourceFileBytes` |
| `checked_java_sources` | `checkedJavaSources` |
| `verify_source_inputs` | `verifySourceInputs`, `SourceProvenance` |
| `checked_out_sources` | `checkedOutSources` |
| `inventory` | `inventory` |
| `execute`, `_execute_snapshot` | `execute`, `REPORT_HARNESS` |
| `main` and the four subcommands | `BaselineCli.run`, `BaselineExit` |

The Python string primitives the readers depend on live in `PythonText.kt` (`pySplitLines`,
`pyStrip`, `pySplitWhitespace`, `sortedByCodePoint`, `pythonStrRepr`, `pythonListRepr`), and the
`json.dumps` renderer lives in `PythonJson.kt`.

Not ported: nothing of `verify.py` itself.

Reused instead of re-ported: none. The module depends on `:core` for `CanonicalJson.compareCodePoints`
and `Sha256`, and on `:host` for `FileDigest`.

## Test coverage

`test_verify.py` declares 40 cases and `test_added_members.py` declares 28. The port covers 62.
The six it does not cover run other tools:

| Case | Reason |
| --- | --- |
| `ComparatorTests.test_geometry_cli_rejects_final_and_generic_override_changes` | Runs `scripts/verify-geometry-jvm-api.py`, a separate tool that re-slices the geometry API. Not part of `verify.py`. |
| `ComparatorTests.test_geometry_cli_accepts_additional_members` | Same script. |
| `FoundationComparatorTests` (4 cases) | Run `scripts/verify-foundation-jvm-api.py`, a separate tool that re-slices the foundation API. |

No Python case needs the pinned `dyn4j-6.0.0.jar`, a JDK 8 runtime or the network: the suites build
their own JAR fixtures and stub JUnit. All 62 ported cases run on this host against the real
`javac`, `jar`, `javap`, `java` and `git`.

## Diminished guarantees

These checks keep the reference's decision but cannot reproduce it on the JVM exactly.

1. **No descriptor-relative open.** `source_file_bytes` uses `os.open` with `O_NOFOLLOW` and
   `dir_fd` per path component. The JVM has no counterpart, so each component is opened by path and
   checked with `LinkOption.NOFOLLOW_LINKS`. A symbolic link at any component is rejected, but a swap
   between the check and the read is not atomic. A change that also restores size, mtime and ctime
   between the two reads is not visible.
2. **`result_field` accepts ASCII digits only.** The reference calls `str.isdigit()` and then `int`,
   which accept every Unicode decimal digit. A run summary cannot contain one, because `javac` and
   the harness write ASCII counts.
3. **Process text decoding.** `subprocess.run(text=True)` decodes with the locale encoding and
   raises on invalid bytes. `ProcessOutput.stdoutText` decodes UTF-8 and replaces invalid bytes.
   Both apply universal newlines.
4. **Compilation order of the upstream suite.** `sorted(rglob("*.java"))` orders `Path` objects by
   their part tuples; `javaSourcesUnder` orders relative path strings by code point. The two differ
   only for names such as `a-b.java` against `a/b.java`, and the report's own lists are sorted
   separately, so the run summary is unaffected.
5. **`pythonStrRepr` printability.** Python's `repr` prints a code point literally when
   `str.isprintable()` is true. The port reproduces that rule for the separators, format characters,
   surrogates and private-use ranges listed in `UNPRINTABLE_RANGES`; a code point Python treats as
   unassigned is printed literally. Every string the verifier interpolates is ASCII.
6. **Command-line grammar, not `argparse` text.** The four subcommands accept the reference's options
   and exit 2 on an argv error, but the usage and error wording is the port's, not `argparse`'s. No
   Python test asserts that wording.
7. **Download transport.** `fetch` reads the URL with `URL.openStream` and moves a `.part` file,
   where the reference calls `urllib.request.urlretrieve`. Proxy, authentication and retry behaviour
   therefore differ. No test downloads anything.
8. **Path spelling.** `pinnedGit` makes the source path absolute without resolving `.` or `..`, as
   `Path.absolute()` does, and `checkedOutSources` returns its result normalised. A cache path that
   contains `..` is spelled differently in an error message.
9. **Process environment.** The reference reads `os.environ` inside every git call. The port takes
   the environment as a parameter that defaults to `System.getenv()`, so the worktree-poisoning cases
   can pass a redirected environment. `BaselineCli` uses the default.

## Verification

`./gradlew :baseline:jvmTest` in `tools/harness`. The suites are `PythonTextCases`,
`DeclarationCases`, `SurfaceCases`, `AddedMemberGateCases`, `RunReportCases`, `JsonRenderCases`,
`PinnedCorpusCases` (common) and `ComparatorCases`, `CompareParityCases`, `AddedMemberCases`,
`SourceIntegrityCases`, `InventoryIdentityCases`, `GitReplacementIdentityCases`,
`GitWorktreeIdentityCases`, `BaselineRunIdentityCases`, `RunReportCliCases`, `HarnessLiteralCases`
(JVM). The latest run reports 110 tests and 0 failures.

The `:baseline` readers and `:compatibility`'s `BaselineOracle` were compared over the 23 recorded
`javap` surfaces. That comparison was a one-off instrument, not a checked-in test. `type_header` and
`surface` agree on every value and on every error message. `member_inventory` differs in one field:
`BaselineOracle` reports an empty `return_type` for every method, because
`declaration.substringBefore("(").substringBeforeLast(name, "").split(" ").last()` leaves a trailing
space. `:baseline` reports the value `verify.py` reports, including the last whitespace token for a
generic return type (`T>`). Nothing in `:compatibility` reads `return_type`; its readers use `name`,
`descriptor`, `declaration` and `flags`.
