# What the hosted and Safari-reporter ports do not cover

This file covers two Python modules only: `tools/qualification/hosted.py` and
`tools/qualification/safari_reporter.py`. Their ports live in `:qualification`
(`commonMain` for the pure rules, `jvmMain` for the process and file-system work). The Python
files are unchanged and remain the reference.

Parity evidence is `src/jvmTest/.../HostedSafariVectors.kt`, recorded at git revision
`d0053c0b4486e26c4d24642b8e0d837b033fee31`. Both Python modules are byte-identical there, at
`b3f52caa`, and at `510097fb`, so the fixture describes the current reference. Regenerate it
with:

```
python3 tools/harness/qualification/parity/generate_hosted_safari_vectors.py
```

Every recorded input and expectation in that file was printed by the Python implementation.
The `stage` and `committed_bytes` cases build their own throw-away Git fixture, so a commit
identifier in a vector belongs to the fixture that produced it; the suites assert the recorded
outcomes (statuses, project verdicts, forensic paths and digests) against their own fixture.

## `hosted.py`

Ported in full:

| Python | Kotlin |
| --- | --- |
| `NATIVE_TARGETS`, `TARGETS` | `Hosted.NATIVE_TARGETS`, `Hosted.TARGETS` |
| `runtime_status` | `Hosted.runtimeStatus` |
| `hosted_status` | `Hosted.hostedStatus` |
| `selected_groups` | `Hosted.selectedGroups` |
| `gradle_wrapper` | `Hosted.gradleWrapper` |
| `run_capture`, `read_command`, `tool_version` | `HostedHost.runCapture` / `readCommand` / `toolVersion` |
| `discover_runtime` | `HostedHost.discoverRuntime` |
| `target_hashes` | `HostedHost.targetHashes` |
| `run_hosted` | `HostedHost.runHosted` |
| `main` | `HostedCli.main` (`./gradlew :qualification:hostedProbe`) |

Reused instead of re-ported: `Qualification.targetBinaryPath`, `Qualification.modules`,
`Qualification.SHA40`/`SHA64` (through `Py`), `CorpusFiles.digest`,
`StagingAudit.audit`, `Staging.run`, `StrictJson.load`, `ProbeManifest.expectedCases`,
`ProbeManifest.validateAccounting`, `ProbeRunner.run`, `CleanCheckout.require`.

Not ported: nothing of `hosted.py` itself.

## `safari_reporter.py`

Ported in full except the Windows branch:

| Python | Kotlin |
| --- | --- |
| constants, `ConfigBindingError`, `StageFailure` | `SafariReporter.*`, `ConfigBindingError`, `StageFailure` |
| `config_relative`, `validate_config` | `SafariReporter.configRelative` / `validateConfig` |
| `committed_bytes`, `committed_fragment` | `SafariReporterHost.committedBytes` / `committedFragment` |
| `open_directory_no_follow`, `same_directory` | `SafariReporterHost.openDirectoryNoFollow` / `sameDirectory` |
| `read_generated_config` | `SafariReporterHost.readGeneratedConfig` |
| `_forensic`, `stage` (POSIX branch) | `SafariReporterHost.forensic` / `stage` |
| `_forensic_windows`, `_stage_windows` | not ported — see below |

Not ported:

| Symbol | Reason |
| --- | --- |
| `_stage_windows` | Depends on `safari_windows_file.LockedDirectory`: `CreateFileW` share modes and directory handles that can be deleted while open. There is no faithful JVM equivalent, so `stage` on a Windows host fails with `UnsupportedOperationException` instead of degrading to a weaker cleanup. Not verified on Windows. |
| `_forensic_windows` | Only reachable from `_stage_windows`. |
| `read_generated_config` Windows branch | Same `LockedDirectory` dependency; `readGeneratedConfig(windows = true)` fails closed. |

## Diminished guarantees

These checks keep the reference's rejection but cannot reproduce it on the JVM exactly:

1. **No descriptor-relative open.** `dir_fd`-relative `os.open` has no JVM counterpart. Every
   path component is opened by path and checked with `LinkOption.NOFOLLOW_LINKS`; a symbolic
   link at any component is still rejected, but a swap between the check and the operation it
   protects is not detected.
2. **`same_directory` uses a captured identity.** `os.fstat` of a held descriptor is replaced by
   `BasicFileAttributes.fileKey()` captured when the directory was opened, and the comparison is
   the same `(st_dev, st_ino)` pair. When the staging directory was renamed, the held directory
   is located by scanning the parent for that identity (the reference reads through its
   descriptor). If it cannot be found, the path itself is used; the swap is still reported as
   `DIRECTORY_CHANGED`, and the path-based read may add an extra forensic record.
3. **`fileKey()` may be absent.** On a file system whose provider does not expose a file key,
   identity comparisons report "not the same directory" (fail closed) instead of trusting a
   path. `st_ctime` is read through `unix:ctime`; where it is unavailable, the identity
   comparison omits it (Python compares it).
4. **Unlink and rmdir are path-based.** `os.unlink(name, dir_fd=...)` and `os.rmdir(name,
   dir_fd=...)` become `Files.delete` on the resolved path. A directory is refused explicitly
   (`rmdir` semantics), and a missing file is ignored as `FileNotFoundError` is, but an ancestor
   swap between the identity check and the delete can redirect the delete.
5. **`Files.newDirectoryStream` has no `NOFOLLOW` overload.** The leftovers scan opens the
   directory by path, as `os.scandir` does, after its identity was checked. Both ports take the
   first 17 entries the file system returns and sort those, so the order is a file-system
   property in both.
6. **Read-then-restat is not a descriptor `fstat`.** `read_generated_config` and `_forensic`
   compare an identity captured before the read with one captured after it, through the path.
   A change that also restores size, mtime and ctime between the two reads is not visible.
7. **Error text of file-system failures.** Rejections the port decides itself keep the exact
   reference message (`unsafe or oversized …`, `Safari generated config changed while reading
   …`, `Safari candidate …`). Failures raised by the file system carry an `[Errno n] kind:
   'path'` message of the same shape but not the reference's exact text, which is recorded in
   forensic `error` fields.
8. **`validate_config`'s JSON decoding.** The settings object is scanned by a strict
   recursive-descent reader and then decoded by `StrictJson`. Duplicate keys raise the
   reference's `karma_config_duplicate_setting`, but — exactly as in the reference — the
   surrounding `except (ValueError, TypeError)` converts it to
   `karma_config_shape_mismatch`. `NaN`/`Infinity` are rejected where `json` would accept them;
   `1e2` and `100.0` compare unequal where Python's numbers compare equal; and the trailing
   `\s*}\s*` check recognises ASCII whitespace only. None of these is reachable from the Kotlin
   generator's own output.
9. **Windows.** The Windows stage and generated-config read are not ported and fail closed; no
   Windows run happened.

## Verification

`./gradlew :qualification:jvmTest` in `tools/harness`. The two suites added here are
`HostedSuite` (77 tests) and `SafariReporterSuite` (38 tests); every case that needs macOS or
Windows observations, or a real staged Gradle/Karma configuration, runs against recorded inputs
instead. No on-host macOS, Windows, Safari, or Gradle staging run was performed for this port.
