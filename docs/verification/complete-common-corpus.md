# Complete common corpus gate

Use `tools/qualification/full_corpus.py` to verify the full checked-in common test corpus on the six available host tasks for both `dyn4k-core` and `dyn4k`. This gate is separate from the selected foundation probe and the unchanged Java corpus.

## Current source inventory

The combined source inventory has 2,454 core common tests, 58 facade common tests, and three facade JVM-only tests. It hashes 193 files in the two modules' common and JVM test source trees, including helper and resource files. The source-tree digest is `9abc9cc73c1c90fe0f5b22cb76f3596fe6ce920c937b1066deb23c0a53a0fb80`. Every test entry records its package, class, method, file, file SHA-256, declaration line, and applicable hosts. The expected full raw XML total is 15,075 executions across the 12 host groups: six times 2,454 core cases, six times 58 facade common cases, and three JVM-only facade cases. The generated manifest file SHA-256 is `cc3b5e7a987f2dad790ccf3525212f25657544651131d0d4ed1a249ba72af227`; its canonical digest is `cf226243d8320ef1425852531d7dbe3cddaab762215b325d411971dc2b6b1b7f`. The inventory report file SHA-256 is `d2e391f04d2227822b6e93c5fabbc622eaec8975e7e51d8412b72c64f3eaaca0`.

The reviewed original audit has 2,385 distinct executed Java identities. The checked-in [original method map](../../tools/qualification/full-common-original-map.tsv), SHA-256 `d20877be61398e65037b0ec3d61134d9922248f608c7901ffe589fed8dff5496`, binds 2,353 portable identities to 2,253 distinct primary common methods. It records 32 explicit JVM-only dispositions, with original source paths, SHA-256 values, declaration lines, and reviewed report hashes. No original identity is unresolved. Five additional Body tests are related to those original methods, but the reviewed Body report describes them as additional checks or a diagnostic control. The [full source manifest](../../tools/qualification/full-common-corpus.json) records them as supplemental. Thus the prior portfolio's 2,258 source-linked method count consists of 2,253 primary mapped methods plus five related supplemental methods. The manifest has 259 supplemental common methods in total and three platform-only JVM test methods, for 2,515 source methods overall. The [inventory report](../../tools/qualification/full-common-inventory-report.json) records these counts without claiming runtime execution. It never converts an original Java execution into a supplemental common execution or vice versa.

The independent Sol review audited all 2,385 map rows against the cited reports or their cited source classes. The [sealed pairing map](../../tools/qualification/full-common-reviewed-pairs.tsv), SHA-256 `f92af322e9e02fba179737bc9401e5bf50a40c39dd62bf8c847ce1dc0e6b8e60`, projects those rows from audited commit `16923c101f4c5f99e9f80ff829da63e6d51c1298`. It records each original identity, destination, disposition, reason, and reviewed report hash. The gate checks every pair against this sealed map and checks its exact SHA-256. It also requires the map, sealed pairs, and manifest bytes to match the candidate commit. A changed pairing requires a new independent row audit and seal. The source map permits several originals to share one common method. Its 32 JVM-only rows remain explicit.

The existing selected probe retains 1,066 core JVM identities and 47 facade JVM identities. Its six-host selection totals 6,668 executions. The selected manifest file SHA-256 is `883a5d1f94f11b5086a8460ad8005147cf887716f72df7815098aa984694a6ea`; its normalized 12-group digest is `406ee533657cca65454552f08f0f059c0e682b2c5b8ca8a74b7248ff31034247`. It accepts other passing XML identities and therefore cannot detect a missing unselected World, joint, or detection test. The full gate requires every source-derived identity exactly once on each applicable host and rejects every unexpected identity.

The source manifest keeps package and class names without a host prefix. Gradle's Linux, JS, and Wasm XML adds the task name to `classname`. The gate applies that prefix to each host's expected identities. Retained Linux World XML, SHA-256 `a0ab672ba4d1c3bbbfa9cfc41f20c6b3f92f23387831239ad491d9c63ea135bb`, has 65 identities within the current source inventory. Its two failures are historical diagnostics.

## Run at a combined source head

Regenerate the manifest after any test-source change. Review and reconcile the original map if a reviewed mapping report changes. Then commit the manifest and map before starting the six-host run. The `run` command requires a clean checkout at the candidate SHA. Its preflight rejects tracked changes and untracked source, Gradle, build logic, and other candidate inputs. Standalone verification repeats that check after execution. Generated `build/`, `.gradle/`, `.kotlin/`, and `kotlin-js-store/` files are allowed. `.omo/` metadata is allowed because this gate does not use it as a Gradle input. Unknown untracked files remain unpassed. The command runs the exact 12-task Gradle invocation shown below. It records the command, process exit, log hash, invocation window, raw XML hashes, tool identities, and produced build artifact hashes. The verifier checks those bytes and the pinned original source and reviewed report hashes. It writes `UNPASSED` if any required evidence fails.

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

The binding receipt, Gradle log, produced build files, and 12 complete XML directories are the raw evidence. `verify` can recheck them without rerunning Gradle on the same tool environment. The log must contain all 12 task lines and `BUILD SUCCESSFUL`. Report and artifact bytes must match their hashes. Reports and artifacts must fall inside the recorded invocation window. This is a host corpus gate. Android host execution is not device execution. The 199 pinned original Java source files and 2,385 actual Java cases remain a separate unchanged-Java gate.

## Evidence boundary

The Python adverse controls remove each unselected World, joint, and detection case independently while a selected foundation case remains. They swap the reviewed `AVLTreeTest.clear` and `contains` destinations without changing the 15,075 expected identities in the regenerated source manifest. An untracked `dyn4k-core/src/commonMain/kotlin/org/dyn4j/UntrackedCandidateCode.kt` fails before `run`, during standalone `verify`, and when created during execution. Other controls change candidate inputs, command tasks, log bytes, tool identity, artifact bytes, source hashes, XML identities, outcomes, and report binding. All mutants fail; complete synthetic XML passes only as a harness control. The inventory report remains source accounting with `qualification_status=NOT_RUN`; runtime evidence is recorded separately in `/tmp/dyn4k-full-common-corpus-rotation-gate-result.json` and is bound to the committed candidate SHA. Android host execution is not device execution, and this gate does not qualify the other approved targets.
