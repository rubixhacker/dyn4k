# Complete common corpus gate

Use `tools/qualification/full_corpus.py` to verify the full checked-in common test corpus on the six available host tasks for both `dyn4k-core` and `dyn4k`. This gate is separate from the selected foundation probe and the unchanged Java corpus.

## Current source inventory

The combined source inventory has 2,465 core common tests, 58 facade common tests, and three facade JVM-only tests. Six core methods are portable Windows collision diagnostics. Five new core methods cover rotation observation isolation. The source seal covers 202 test files across the two modules and their supported source sets. These files include helpers, resources, and five platform actuals for the World nested-view expectation. The source-tree digest is `48fb46ea9eb95b061da6c4815675eb52bb76447d43eed24f5cb9d4c89477f0b8`. Each test entry records its identity, source hash, declaration line, and applicable hosts.

The expected raw XML has 15,141 executions across 12 host groups. Each of six hosts runs 2,465 core and 58 facade common cases. JVM runs three additional facade cases. The manifest file SHA-256 is `edac14e1a000821b30cdd4bb3f07c82d78e33f305399a09849078dac210eb2ed`. Its canonical digest is `f9438aeeca1d2a4b00debea24c10f1b069e1eab5477c5c994b5ed2d9d543e4aa`. The inventory report SHA-256 is `693a4d3de84851916cfdae6ff4fde01815356ef1246caba336ac32af510a56e9`. The report records source inventory, not runtime execution.

This reseal adds the five `RotationObservationIsolationTest` methods and its source file. Reviewed changes already in the assembly also update nine existing source-file hashes. Of the 2,521 prior cases, 42 have new source hashes and 31 have new declaration lines. Their identities and original mappings remain unchanged. The reviewed 2,385 original mappings and pairing seal remain unchanged.

The reviewed original audit has 2,385 distinct executed Java identities. The checked-in [original method map](../../tools/qualification/full-common-original-map.tsv) binds 2,353 portable identities to 2,253 primary common methods. Its SHA-256 is `d20877be61398e65037b0ec3d61134d9922248f608c7901ffe589fed8dff5496`. The map records 32 explicit JVM-only dispositions and no unresolved identity. It also binds original source paths, hashes, declaration lines, and reviewed report hashes.

Five Body tests relate to original methods but remain supplemental checks. The [full source manifest](../../tools/qualification/full-common-corpus.json) records 2,253 primary mapped methods and five related supplements. These form 2,258 source-linked methods. The manifest has 270 supplemental common methods, including the six collision diagnostics and five rotation observation isolation methods. Three facade methods run only on JVM, giving 2,526 source methods overall. The [inventory report](../../tools/qualification/full-common-inventory-report.json) records those counts without claiming runtime execution. An original Java execution does not become a supplemental common execution.

The existing case ID `staleBodySubListsCannotCreateReadableNestedViews` covers a saved parent sublist and children created after its backing list changes. The saved parent fails on read. On Java 8, nested children created through that stale parent can still read the original element; on Java 21, those children fail with `ConcurrentModificationException`. Both outcomes match the unchanged dyn4j 6.0.0 baseline. The Android host helper probes its Java runtime, while the JS, Native, and Wasm helpers require the strict exception outcome. The case ID remains stable even though its wording describes only the Java 21 and portable result.

The independent Sol review audited all 2,385 map rows against the cited reports or their cited source classes. The [sealed pairing map](../../tools/qualification/full-common-reviewed-pairs.tsv), SHA-256 `f92af322e9e02fba179737bc9401e5bf50a40c39dd62bf8c847ce1dc0e6b8e60`, projects those rows from audited commit `16923c101f4c5f99e9f80ff829da63e6d51c1298`. It records each original identity, destination, disposition, reason, and reviewed report hash. The gate checks every pair against this sealed map and checks its exact SHA-256. It also requires the map, sealed pairs, and manifest bytes to match the candidate commit. A changed pairing requires a new independent row audit and seal. The source map permits several originals to share one common method. Its 32 JVM-only rows remain explicit.

The existing selected probe retains 1,066 core JVM identities and 47 facade JVM identities. Its six-host selection totals 6,668 executions. The selected manifest file SHA-256 is `883a5d1f94f11b5086a8460ad8005147cf887716f72df7815098aa984694a6ea`; its normalized 12-group digest is `406ee533657cca65454552f08f0f059c0e682b2c5b8ca8a74b7248ff31034247`. It accepts other passing XML identities and therefore cannot detect a missing unselected World, joint, or detection test. The full gate requires every source-derived identity exactly once on each applicable host and rejects every unexpected identity.

The source manifest keeps package and class names without a host prefix. Gradle's Linux, JS, and Wasm XML adds the task name to `classname`. The gate applies that prefix to each host's expected identities. Retained Linux World XML, SHA-256 `a0ab672ba4d1c3bbbfa9cfc41f20c6b3f92f23387831239ad491d9c63ea135bb`, has 65 identities within the current source inventory. Its two failures are historical diagnostics.

## Run at a combined source head

Regenerate the manifest after any test-source change. Review and reconcile the original map if a reviewed mapping report changes. Then commit the manifest and map before starting the six-host run. The `run` command requires a clean checkout at the candidate SHA. Its preflight rejects tracked changes and untracked source, Gradle, build logic, and other candidate inputs. Standalone verification repeats that check after execution. Generated `build/`, `.gradle/`, `.kotlin/`, and `kotlin-js-store/` files are allowed. `.omo/` metadata is allowed because this gate does not use it as a Gradle input. Unknown untracked files remain unpassed. The command runs the exact 12-task Gradle invocation shown below. It records the command, process exit, log hash, invocation window, raw XML hashes, host PATH tool identities, and produced build artifact hashes. On Linux, the committed Node startup probe holds each selected test process for a bounded acknowledgement. The collector reads its live `/proc` identity, executable bytes, command, parent chain, and test payload. It binds one process to each of the six Node groups and its completed raw reports. The verifier checks those bytes and the pinned original source and reviewed report hashes. It writes `UNPASSED` if any required evidence fails.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/qualification/full_corpus.py inventory \
  --mapping tools/qualification/full-common-original-map.tsv \
  --output tools/qualification/full-common-corpus.json \
  --report tools/qualification/full-common-inventory-report.json

candidate_sha=$(git rev-parse HEAD)
JAVA_HOME=/tmp/dyn4k-tools/jdk21 \
PATH=/tmp/dyn4k-tools/gradle-9.5.0/bin:/tmp/dyn4k-tools/jdk21/bin:$PATH \
ANDROID_HOME=/var/home/stewart/Android/Sdk ANDROID_SDK_ROOT=/var/home/stewart/Android/Sdk \
  PYTHONDONTWRITEBYTECODE=1 python3 tools/qualification/full_corpus.py run \
  --candidate-sha "$candidate_sha" \
  --manifest tools/qualification/full-common-corpus.json \
  --mapping tools/qualification/full-common-original-map.tsv \
  --upstream /tmp/dyn4k-upstream-6.0.0 \
  --binding /tmp/dyn4k-full-common-corpus-rotation-gate-binding.json \
  --output /tmp/dyn4k-full-common-corpus-rotation-gate-result.json \
  --log /tmp/dyn4k-full-common-corpus-rotation-gate-gradle.log -- \
  ./gradlew --no-daemon --max-workers=1 --rerun-tasks --continue --console=plain \
  :dyn4k-core:jvmTest :dyn4k:jvmTest \
  :dyn4k-core:linuxX64Test :dyn4k:linuxX64Test \
  :dyn4k-core:jsNodeTest :dyn4k:jsNodeTest \
  :dyn4k-core:wasmJsNodeTest :dyn4k:wasmJsNodeTest \
  :dyn4k-core:wasmWasiNodeTest :dyn4k:wasmWasiNodeTest \
  :dyn4k-core:testAndroidHostTest :dyn4k:testAndroidHostTest
```

The binding receipt, Gradle log, Node request and acknowledgement files, selected test payloads, produced build files, and 12 complete XML directories are the raw evidence. `verify` can recheck them without rerunning Gradle when the observed Node executable paths and bytes remain available. The archive also retains the requests, acknowledgements, and payloads. Archive replay may use an exact-revision checkout at a different absolute path. It keeps the observed absolute Node command, checks its six payload arguments against the separately recorded capture source root, and checks the payload and loader bytes in both the archive and candidate checkout. A separate checkout therefore needs those generated files at their recorded relative paths; copying them from the archive supports consistency replay but does not execute tests there. The observed Node executable must remain available at its recorded path because the archive does not retain it. The log must contain all 12 task lines and `BUILD SUCCESSFUL`. Report and artifact bytes must match their hashes. Reports and artifacts must fall inside the recorded invocation window. The PATH Node identity remains host-tool metadata. Each Node group reports its observed Gradle-selected version separately. A distinct `node --version` process only corroborates the version of the already observed executable. It cannot establish test-process identity. The new binding and result use schema 2. Historical schema 1 archives and receipts retain their archive-consistency meaning; they do not supply actual Node runtime proof. Unsupported hosts and missing observations remain unpassed for schema 2. This is a host corpus gate, not staged minimum/current Node qualification. Android host execution is not device execution. The 199 pinned original Java source files and 2,385 actual Java cases remain a separate unchanged-Java gate.

## Evidence boundary

The Python adverse controls remove each unselected World, joint, and detection case while a selected foundation case remains. They swap the reviewed `AVLTreeTest.clear` and `contains` destinations against 15,141 expected source identities. An untracked production Kotlin file fails before `run`, during `verify`, and when created during execution. Other controls change candidate inputs, commands, logs, tool identity, artifacts, source hashes, XML identities, outcomes, and report bindings. The mutants fail; complete synthetic XML passes only as a harness control. The inventory report remains source accounting with `qualification_status=NOT_RUN`. Runtime evidence needs a separate receipt bound to the committed candidate SHA. Android host execution is not device execution. This gate does not qualify the other approved targets.
