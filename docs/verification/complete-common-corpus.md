# Complete common corpus gate

Use `tools/qualification/full_corpus.py` to verify the full checked-in common test corpus on the six available host tasks for both `dyn4k-core` and `dyn4k`. This gate is separate from the selected foundation probe and the unchanged Java corpus.

## Current source inventory

The source inventory at selected-probe base `9acde798574ad5f4c637b90da5c76bd8455a72d5` has 2,444 core common tests, 58 facade common tests, and three facade JVM-only tests. It hashes 191 files in the two modules' common and JVM test source trees, including helper and resource files. The source-tree digest is `2f5fcb376ec9014b9d386eb9152350938bff9cccd6ba28d8af198cb93422c5a6`. Every test entry records its package, class, method, file, file SHA-256, declaration line, and applicable hosts. The expected full raw XML total is 15,015 executions across the 12 host groups: six times 2,444 core cases, six times 58 facade common cases, and three JVM-only facade cases.

The reviewed original audit has 2,385 distinct executed Java identities. The checked-in [original method map](../../tools/qualification/full-common-original-map.tsv) binds 2,353 portable identities to 2,253 distinct primary common methods. It records 32 explicit JVM-only dispositions, with original source paths, SHA-256 values, declaration lines, and reviewed report hashes. No original identity is unresolved. Five additional Body tests are related to those original methods, but the reviewed Body report describes them as additional checks or a diagnostic control. The [full source manifest](../../tools/qualification/full-common-corpus.json) records them as supplemental. Thus the prior portfolio's 2,258 source-linked method count consists of 2,253 primary mapped methods plus five related supplemental methods. The manifest has 249 supplemental common methods in total and three platform-only JVM test methods. The [inventory report](../../tools/qualification/full-common-inventory-report.json) records these counts without claiming runtime execution. It never converts an original Java execution into a supplemental common execution or vice versa.

The existing selected probe retains 1,066 core JVM identities and 47 facade JVM identities. Its six-host selection totals 6,668 executions. It accepts other passing XML identities and therefore cannot detect a missing unselected World, joint, or detection test. The full gate requires every source-derived identity exactly once on each applicable host and rejects every unexpected identity.

## Run at a combined source head

Regenerate the manifest after any test-source change. Review and reconcile the original map if a reviewed mapping report changes. Then commit the manifest and map before starting the six-host run. The `run` command requires a clean checkout at the candidate SHA, deletes old matching XML, runs all 12 tasks with `--rerun-tasks`, records the invocation window, and writes the raw XML hashes into a binding receipt. The verifier checks the pinned original source and reviewed report hashes again. It writes `UNPASSED` if the command or any report fails.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/qualification/full_corpus.py inventory \
  --mapping tools/qualification/full-common-original-map.tsv \
  --output tools/qualification/full-common-corpus.json \
  --report tools/qualification/full-common-inventory-report.json

candidate_sha=$(git rev-parse HEAD)
JAVA_HOME=/tmp/dyn4k-tools/jdk21 ANDROID_HOME=/var/home/stewart/Android/Sdk \
  PYTHONDONTWRITEBYTECODE=1 python3 tools/qualification/full_corpus.py run \
  --candidate-sha "$candidate_sha" \
  --manifest tools/qualification/full-common-corpus.json \
  --mapping tools/qualification/full-common-original-map.tsv \
  --upstream /tmp/dyn4k-upstream-6.0.0 \
  --binding /tmp/dyn4k-full-common-binding.json \
  --output /tmp/dyn4k-full-common-result.json \
  --log /tmp/dyn4k-full-common-gradle.log -- \
  ./gradlew --no-daemon --max-workers=1 --rerun-tasks --continue --console=plain \
  :dyn4k-core:jvmTest :dyn4k:jvmTest \
  :dyn4k-core:linuxX64Test :dyn4k:linuxX64Test \
  :dyn4k-core:jsNodeTest :dyn4k:jsNodeTest \
  :dyn4k-core:wasmJsNodeTest :dyn4k:wasmJsNodeTest \
  :dyn4k-core:wasmWasiNodeTest :dyn4k:wasmWasiNodeTest \
  :dyn4k-core:testAndroidHostTest :dyn4k:testAndroidHostTest
```

The binding receipt and 12 complete XML directories are the raw evidence. `verify` can recheck them without rerunning Gradle, provided file bytes and times remain in the recorded invocation window. This is a host gate. Android host execution is not device execution. The 199 pinned original Java source files and 2,385 actual Java cases remain a separate unchanged-Java gate.

## Evidence boundary

The Python adverse controls remove each unselected World, joint, and detection case independently while a selected foundation case remains. They also change a mapped source hash, rename class or method, duplicate or add a case, fail, error, or skip an extra case, and change candidate, source-tree, report-hash, or report-time binding. All controls fail the verifier; the unchanged synthetic fixture passes. The current selected-probe base has no fresh 12-group full-corpus run. A full pass must await the coordinator's combined source head and its exact-SHA Gradle execution.
