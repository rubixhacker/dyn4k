# Qualification harness

This harness records what ran against one staged candidate. A build or a host probe alone does not qualify a runtime. [Qualify staged artifacts on every required runtime](https://github.com/rubixhacker/dyn4k/issues/43) remains open while required cases and independent gates lack evidence.

## Hosted runner cost guard

Run `python3 -B tools/qualification/guard_hosted_runners.py` from the repository root before every source push or manual `gh workflow run`. The command checks every active `.github/workflows/*.yml` and `*.yaml` file. It allows explicit Linux or Windows hosted labels and the self-hosted `mac-mini` label. It rejects GitHub-hosted macOS labels and unrecognized runner expressions. The coordinator must rerun it after integrating workflow changes.

The guard job in `qualification.yml` starts after dispatch. It cannot prevent the dispatch itself. Keep workflows with GitHub-hosted macOS runners disabled until separate review and authorization. Active workflows may use explicitly labeled Linux or Windows hosted runners or the self-hosted `mac-mini`. The remote disabled-workflow total can change over time. Historical Mac-only definitions are in `docs/archive/hosted-macos-workflows/`. This source change does not qualify Apple targets or replace local Mac runtime evidence.

## What the harness checks

`tools/qualification/qualify.py matrix` emits the complete approved support matrix: 21 targets, 28 target/runtime families, and 112 cases after minimum/current and two build configurations. The configuration names correspond to the [approved support contract](https://github.com/rubixhacker/dyn4k/issues/6#issuecomment-5651793360): JVM no-optimize/default; Android debug/R8; web development/production; Native debug `-g`/optimized `-opt`. A matrix row is a requirement, not a result.

`audit-staging` checks both module roots and all target publications referenced by their Gradle metadata. It checks POM identity and descriptive metadata, target mapping, sources, API documentation and license artifacts, an embedded JAR license, and SHA-256 sidecars. It writes every observed POM, module metadata file and distributable artifact with its computed SHA-256. Any missing publication fails the audit. The audit result is separate from runtime execution.

The external JVM consumer in `consumers/qualification/` resolves `io.github.rubixhacker:dyn4k:0.1.0-alpha.1` from the staged repository. It executes Kotlin and Java public geometry calls. Its `verifySingleProvider` task rejects a graph containing both `dyn4k-core` and upstream `org.dyn4j:dyn4j`. The portable KMP consumer in `consumers/qualification/portable/` declares every approved target and runs a common public geometry test wherever an actual staged target artifact and runtime are available. These are foundation probes. They do not claim the full geometry, collision, dynamics, joint or compatibility suite.

`probe` uses the tracked `tools/qualification/foundation-probes.json` manifest. Each of the six available `dyn4k-core` host groups selects 1,066 exact identities: 441 previously integrated cases plus 625 from the combined foundation, geometry factory, and shape suites. The added 625 comprise 601 portable original-test counterparts and 24 supplemental foundation cases. Each paired `dyn4k` facade group selects 47 JVM cases and 45 cases on each of five other hosts, including the three integrated `GeometryShapeTest.cleanse*` cases. The 12 groups in the six-host probe select 6,668 executions (6 × 1,066 + 47 + 5 × 45). The 14 core JVM-only original identities remain covered by the unchanged Java suite. These are named, reviewed cases; the harness never adds an identity to the selected set at runtime.

Selection is applied during report verification, after Gradle runs each complete task. The verifier accepts the full XML set when every selected identity appears exactly once. It rejects any missing or duplicated identity, including duplicate unselected cases. Other passing cases in the full report are allowed and do not count as selected executions. Every reported case must have a valid identity and finite duration, and the XML suite totals must match its case elements. A failure, error, or skip anywhere in the report, including an unselected case, fails the probe. The JSON records `expected` and `executed` for selected identities and `reported` for all XML testcase elements; `groups` records the same totals per report group. The selected manifest digest and candidate SHA remain bound to the result. Probe results use `PROBE_PASSED` or `PROBE_FAILED` and state `foundation probe only`; they cannot become full-lane results.

`hosted.py run` adds bounded probes for macOS ARM64, iOS/tvOS/watchOS ARM64 simulators, iOS x64 simulator, Windows x64, and Safari JS. Run Apple probes on the installed local Mac over SSH with Xcode 26.5; GitHub-hosted macOS execution is prohibited. Each native route stages both module roots and its target publications, checks both staged binary checksums, runs the full host tasks, and verifies 1,111 selected library cases in the resulting reports. It then resolves the staged artifacts in an external consumer and verifies its three selected cases. The Safari route enables WebDriver and uses the external JS browser test with the Karma Safari launcher through Launch Services; it requires installed Safari and SafariDriver. The runner records its actual OS, architecture, Java, Gradle, declared Kotlin plugin, selected Xcode version, and available simulator or Safari identity. A missing simulator or browser is `UNAVAILABLE`; wrong host or toolchain identity and missing, partial, or failed reports are `PROBE_FAILED`. Results must bind the selected source commit. These are bounded development probes, not the complete suite or minimum-OS evidence. The Xcode pin does not change the required minimum or current platform runtime versions.

`artifact.py hosted` packages every selected `dyn4k-core`, `dyn4k`, and staged external-consumer XML report before `record` can accept a bounded hosted pass. The bundle retains full XML, including passing unselected cases, and records selected execution totals separately from full report totals. `record --raw-bundle` rechecks the package against the frozen case identities, per-group selected and reported counts, source and consumer probe times, candidate SHA, runtime, and target hashes. A missing core XML report, a missing or duplicate selected identity, a duplicate extra identity, a skipped or failed case anywhere, or an old report changes the bounded status to `PROBE_FAILED`. The bundle retains the JSON sidecars, actual XML, staged root and target POMs and Gradle metadata, both tested target binaries and their SHA-256 sidecars, and a `verification.json` file with per-group counts, original file times, and hashes. Archive extraction can change file times; downloaded verification checks the recorded original times against the probe window and independently checks the XML bytes and cases. It computes both target binary digests from the archived bytes and compares them with the sidecars, hosted observation, and bundle summary. The target binaries were resolved by the external consumer from the staged repository. `artifact.py verify --candidate-sha <sha> --output <downloaded-bundle>` also requires the uploaded matrix, checks its bounded observation against the hosted probe, and requires the exact 112 unique support lane IDs. It counts each lane status itself and rejects missing, duplicate, unknown, or contradictory results. During the earlier `record` step, the matrix does not yet exist; that internal check calls the verifier with `require_matrix=False` and cannot validate downloaded matrix accounting.

The Ubuntu route also runs six frozen portable staged-consumer groups, with three selected cases per group. `artifact.py ubuntu` requires their full XML reports to contain the 18 selected consumer cases and all 6,668 selected source cases, plus the artifact audit, provider diagnosis, and 112-case matrix JSON. It records the actual Linux architecture, distribution, kernel, GitHub runner image, and Java version. A complete Ubuntu bounded bundle therefore has 6,686 selected executions; it records the full XML testcase total separately. The artifact audit can still be `FAILED` because API documentation is absent, and the full matrix remains unpassed. The prior [hosted run 39063294626](https://github.com/rubixhacker/dyn4k/actions/runs/39063294626) executed the earlier Mac ARM64 cases but its upload omitted 286 core XML cases; it is retained as incomplete raw evidence. No bounded pass from that upload is accepted by this raw XML gate.

The Safari manifest pins both exact case names emitted by Safari 26.6.2. Their `MacOS10.15.7` suffix comes from Safari's user agent and is not the host OS version. The host version comes from `sw_vers` in the runtime record. A future Safari reporter identity change fails until the manifest is reviewed.

`execute` accepts a JSON plan keyed by matrix case ID. Each entry supplies a command and result path, or an exact unavailability reason. Before a command, it moves any old result to a distinct `.previous-<id>` file. It gives the command `DYN4K_QUALIFICATION_INVOCATION`. The runner must write that value as `invocation_id` in a new JSON result. A no-op, failed command, stale file, wrong invocation, or invalid JSON fails execution. Missing plans remain `NOT_RUN`.

`record` evaluates all 112 lanes. It requires a clean checkout at the candidate SHA, including untracked files hidden by ignore rules. The input check excludes generated `build/`, `.gradle/`, and `.kotlin/` files only under the repository root and the four Gradle project roots. It also excludes `tools/qualification/__pycache__/` and the generated `kotlin-js-store/yarn.lock` files at the repository root and in `consumers/qualification/portable/`. An untracked source, build script, or ignored `local.properties` invalidates the candidate, even if a source path contains a directory named `build`.

The tracked [complete suite manifest](full-suite-manifest.md) contains 2,523 portable methods and three facade JVM-only methods. Each lane must bind its runtime identity, version, configuration, selected cases, suite ID, and both target binary hashes. The result must match those selections and bind the suite, candidate, and staged audit digests. The audit is recomputed against staged files before acceptance. The manifest defines required cases and gates; it is not execution evidence. Independent review approved its inventory and case selection at revision `2f5eb2d`; runtime qualification remains open.

`record --hosted-probe <json> --raw-bundle <directory>` checks the bounded result's candidate SHA, selected runtime identity, frozen source and consumer manifest digests, exact counts, staged target hashes, and complete raw XML bundle. It stores the result under `bounded_hosted_probes`. It does not promote a bounded probe to a `PASSED` full lane. Historical macOS 26 jobs and Windows Server 2025 jobs do not establish the approved minimum OS versions. Windows Server 2025 is not a Windows 10 client runtime. Simulator tests do not establish physical Apple device support.

`artifact.py verify --candidate-sha <sha> --output <full-hosted-directory-or-tar>` accepts a schema 2 full hosted receipt. It checks the committed corpus, reviewed map, and pair file. It checks archived source bytes, raw XML cases, test executables, and process logs. It also checks runner paths, resolved consumer artifacts, both staged binaries, and exact Gradle metadata links. The receipt must report Java 21, Gradle 9.5.0, and declared KGP 2.4.20.

Every inventoried file must match its recorded hash, size, and nanosecond modification time. A transport tar must contain only regular files with matching PAX timestamps. Raw XML and test executables must match their process windows. Process logs must be newer than their recorded process exits. The verifier rejects missing, extra, skipped, ignored, or failing cases. It rejects changed files, wrong runners, and incomplete configurations. Internal archive consistency does not authenticate a claimed GitHub run.

`qualify.py record --full-hosted-bundle <directory>` verifies the archive. It stores exact common and bounded consumer case IDs under `full_hosted_receipts`. Each configuration maps to one `current` support lane. That mapping includes its observed runtime version and both target hashes. The committed manifest binds case areas, lane gates, and independent gate definitions. Native lanes select 2,523 portable methods. The three facade JVM-only methods apply only to JVM lanes.

A complete lane needs independent receipts for every applicable gate. `record` accepts raw archive paths and a signed audit. It calls `full_suite_manifest.select_lane` for each selected lane. It passes the archives and signed expectations to the public `independent_gates.evaluate` verifier. That verifier checks producer bytes, process, source, artifacts, and all required gates. A `PASSED` lane needs every selected case exactly once in its evidence and raw full-suite consumer XML. Self-reported gate hashes must match the signed archive digests. The recorder fills a missing producer claim only from the verified audit.

The audit uses a detached Ed25519 signature. The operator supplies the public key and its SHA-256 fingerprint independently of the producer archive. The fingerprint covers the public key in DER form. `record` checks the fingerprint and signature before parsing the same audited bytes. An unsigned audit, untrusted key, or changed audit cannot produce `PASSED`. Key custody and signing remain independent operational requirements.

The archive map has `schema`, `candidate_sha`, and `lanes`. Each selected lane maps gate names to raw archive directories. The signed audit has `schema`, `candidate_sha`, `suite_manifest_sha256`, and the same selected `lanes`. For a complete lane, it also binds `candidate_manifest_sha256` and `staged_audit_sha256`. Each signed lane supplies `expected_archive_digests`, `expected_artifact_hashes`, `expected_runtime_identity`, and any `expected_producer_scopes`. The recorder compares target and JVM producer hashes with the verified staged publications. It also compares the signed runtime identity with the candidate manifest. The audit supplies `expected_all_target_hashes` for the 21-target publication gate. Use `--independent-performance-key` for a separately trusted sustained-performance key.

Every passing lane must agree on each global gate's verified archive, signed digest, and producer scope. A differing global result fails the affected passing lanes, including an otherwise complete 112-lane set. The independent verifier defines the gate and producer scope contracts. Missing archives remain `NOT_RUN`. A valid external unavailability receipt remains `UNAVAILABLE`. A legacy `--availability` reason is labeled `UNVERIFIED` until a bound external observation supports it. Attempted invalid bytes remain `FAILED`.

Use the signed inputs with `record`:

```sh
python3 tools/qualification/qualify.py record \
  --candidate-sha "$CANDIDATE_SHA" \
  --evidence "$COMPLETE_SUITE_EVIDENCE" \
  --audit "$STAGED_ARTIFACT_AUDIT" \
  --candidate-manifest "$CANDIDATE_MANIFEST" \
  --independent-archives "$RAW_GATE_ARCHIVE_MAP" \
  --independent-audit "$INDEPENDENT_AUDIT" \
  --independent-audit-signature "$INDEPENDENT_AUDIT_SIGNATURE" \
  --trusted-audit-public-key "$TRUSTED_AUDIT_PUBLIC_KEY" \
  --trusted-audit-key-sha256 "$TRUSTED_AUDIT_KEY_SHA256" \
  --output "$QUALIFICATION_REPORT"
```

The report keeps all 112 lanes and embeds each selected lane's independent gate result. A signed audit is not itself a passing runtime observation. At integration revision `23aa6bc4f086b929610d4260fd480cf77e8fafce`, `record` reported 112 `NOT_RUN` lanes. The report is `/tmp/dyn4k-qualification-status-docs-record-23aa.json`.

The exact command was:

```sh
python3 tools/qualification/qualify.py record --candidate-sha 23aa6bc4f086b929610d4260fd480cf77e8fafce --output /tmp/dyn4k-qualification-status-docs-record-23aa.json
```

This status applies to that revision. Rerun the recorder for a later candidate.

Statuses have distinct meanings: `PASSED` has complete evidence; `FAILED` has attempted but invalid or failing evidence; `UNAVAILABLE` names an absent runner or probe; `NOT_RUN` has no attempt. `record --availability <json>` accepts target, `target:runtime`, `target:runtime:version`, or exact case IDs with concrete reasons. More specific selectors take priority. A missing device or suite never becomes a pass or a zero measurement.

## Local commands

The Ubuntu workflow runs `tools/qualification/subclass_audit.py` after the staged artifact audit. It replays that audit against the current checkout, selects the audited `dyn4k-core` JVM JAR, and runs the vector, AABB, geometry, and joint/AVL Java subclass fixtures on JDK 8 and JDK 21. Each process writes separate stdout, stderr, and metadata with its exact command, exit, invocation times, and stream hashes under `subclass-dispatch/<jdk>/`. The receipt records the observed Java version and executable hashes. A second invocation with `--verify` and the same arguments replays the staged audit. It checks every process and family digest against the top receipt, then parses the raw fixture output again. It requires the same selected JDK binaries to remain available. A historical JAR can be examined with `--diagnostic-jar`, but that mode reports `UNQUALIFIED` or `UNQUALIFIED_FAILED` and cannot accept candidate commit or audit arguments. The process metadata is written by this runner and can detect a changed archive when replayed; it is not independent OS attestation or a signature. A passing subclass control is scoped JVM evidence; it does not pass a full runtime lane.

Set JDK 21 and the Android SDK paths for this pinned build. Stage the two module roots and the target publications you can build with Gradle. Then run:

```sh
python3 -m unittest discover -s tools/qualification -p 'test_*.py' -v
./gradlew -p consumers/qualification --no-daemon run -PqualificationRepository="$PWD/build/staging-repository"
./gradlew -p consumers/qualification/portable --no-daemon jvmTest linuxX64Test -PqualificationRepository="$PWD/build/staging-repository"
python3 tools/qualification/qualify.py probe --candidate-sha "$(git rev-parse HEAD)" --manifest tools/qualification/foundation-probes.json --group core-jvm --group jvm --report 'dyn4k-core/build/test-results/jvmTest/TEST-*.xml' --report 'dyn4k/build/test-results/jvmTest/TEST-*.xml' --output /tmp/foundation-probe.json -- ./gradlew --no-daemon :dyn4k-core:jvmTest :dyn4k:jvmTest
python3 tools/qualification/qualify.py audit-staging --candidate-sha "$(git rev-parse HEAD)" --repository build/staging-repository --output /tmp/artifact-audit.json
python3 tools/qualification/qualify.py record --candidate-sha "$(git rev-parse HEAD)" --output /tmp/runtime-matrix.json
```

`audit-staging` and `record` are expected to exit nonzero while contract gaps remain. The dedicated CI workflow runs host foundation probes, staged consumers, the duplicate-provider diagnosis, artifact audit, and full matrix recording. It uploads complete raw bundles keyed to the workflow commit. Runtime owners can use `execute` with a plan such as:

```json
{
  "jvm:Java:minimum:default": {
    "command": ["/path/to/jdk8/bin/java", "-jar", "/path/to/complete-suite-runner.jar"],
    "result_file": "/path/to/observed-result.json"
  }
}
```

The runtime runner must write `invocation_id` from its environment, actual case and consumer observations, and the selected manifest and artifact digests. The plan alone never passes a lane. The exact full-lane JSON schema is exercised in `tools/qualification/test_qualify.py`; the production gate will not accept a synthetic suite file outside the tracked candidate.

## Open qualification requirements

The complete common corpus passed on 12 host groups at revision `0681a8cd2e3f12327296a58da68bc8338224ea73`. The bound receipt is `/tmp/dyn4k-full-common-corpus-rotation-gate-result.json`. Its candidate SHA is `0681a8cd2e3f12327296a58da68bc8338224ea73`.

The [corpus report](complete-common-corpus.md) and [implementation ledger](../planning/implementation-ledger.md) record this 15,075-case result. It does not qualify every target or the later integration revision.

Android Native x64 ran its full common corpus on an API 37 x86_64 guest at source revision `93c5841e892e0926aaf1b01ee5032d1d3f2620c6`. It covered 2,454 core and 58 facade methods in debug and optimized modes. It also ran staged-consumer assertions.

The receipt is `/tmp/dyn4k-android-native-full-evidence-final/result.json`. Its source SHA is `93c5841e892e0926aaf1b01ee5032d1d3f2620c6`. Replay at harness revision `21793f7b9c2195fa023102c4acf349b9350fe35f` returned `CONSISTENCY_ONLY`. This does not qualify integration revision `23aa6bc4f086b929610d4260fd480cf77e8fafce`. See the [Android Native report](android-native-runtime.md) and the revision-bound account in the [implementation ledger](../planning/implementation-ledger.md).

Each lane needs staged-artifact, staged-consumer, numerical-parity, and physical-correctness receipts. JVM lanes also need unchanged Java corpus, Java source compatibility, and duplicate-provider evidence.

Global gates cover migration journeys, sustained performance and resources, publication, and independent review. These gates need candidate-bound evidence. [Run the full compatibility corpus and unchanged migration applications](https://github.com/rubixhacker/dyn4k/issues/42) and [Freeze and validate the performance fixture and reference-environment manifest](https://github.com/rubixhacker/dyn4k/issues/17) remain open. Host JVM or Linux runs cannot establish Apple, device, or release qualification.
