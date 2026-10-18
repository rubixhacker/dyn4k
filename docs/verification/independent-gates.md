# Independent gate archive verifier

Run `independent_gates.py` for one exact Git commit and one approved runtime lane. It reads the complete suite manifest from revision `6f983ad3a36bdc549c32f5d0883b0a47b28e1963`. Its result binds the candidate, lane, selected hashes, archive digests, gate outcomes, and numerical policy with SHA-256.

```sh
python3 tools/qualification/independent_gates.py \
  --candidate-sha "$CANDIDATE_SHA" \
  --lane 'jvm:Java:minimum:no-optimize' \
  --expected-artifacts /audit/jvm-target-hashes.json \
  --expected-all-target-artifacts /audit/all-21-target-hashes.json \
  --expected-producer-scopes /audit/producer-scopes.json \
  --expected-archive-digests /audit/archive-digests.json \
  --expected-runtime-identity 'selected runner identity' \
  --archive staged-consumer=/archives/consumer \
  --archive publication-contract=/archives/publication
```

The selected hash file maps `dyn4k-core` and `dyn4k` to audited binary SHA-256 values. The all-target file maps every approved target to those two binary hashes. The publication gate requires all 21 targets. The archive digest file maps gate names to `archive_digest(archive_path)` values. An independent archive auditor must record those digests before evaluation. Values copied from a producer receipt do not establish independent provenance. The evaluator cannot authenticate the auditor; the adapter must retain the independent audit record.

The producer scope file maps Java corpus, migration, performance, and review gate names to independent evidence scopes. Each scope has `candidate_sha`, `target`, `runtime`, `runtime_identity`, and `artifact_hashes`. Its candidate SHA must equal the selected commit. A Java corpus scope contains both audited JVM JAR hashes. A migration scope contains the producing `dyn4k-core` JVM JAR hash. A performance scope contains both producing JVM JAR hashes. A review scope uses target `source` and an empty artifact map. Each archive receipt repeats its selected scope in `producer_scope`. Native lane KLIB hashes do not stand in for a global JVM producer. The verifier rehashes the resolved Java and migration JARs, and matches performance's raw JAR inventory against these scopes. The adapter must supply the scope audit independently of each producer receipt.

The importable `evaluate(manifest, candidate_sha, lane_id, archives, repository, expected_artifact_hashes, expected_runtime_identity, expected_archive_digests, expected_all_target_hashes, expected_producer_scopes)` returns every applicable gate and all four global gates. `qualify.py` can pass the approved manifest and audited inputs without importing a producer status. The CLI exits zero only when every required gate passes. A bounded archive cannot turn a full 112-lane qualification green.

## Common raw archive

Each archive contains `receipt.json` and every file listed in `receipt.files`. Each file entry has a safe relative path, SHA-256, and original nanosecond mtime. The extracted filesystem mtime must equal the recorded mtime and fall inside the process execution window. The auditor digest covers every extracted file's bytes, path, and filesystem mtime. The verifier rejects unlisted files, duplicate paths, traversal, symbolic links, changed bytes, changed mtimes, and wrong candidate or lane identities.

A passing receipt binds the exact candidate SHA and Git tree, the selected lane where applicable, and audited producer artifact and runtime identities. Its process record includes a command, integer exit code, start and finish times, and raw output paths where the route requires them. Consumer, provider, and publication routes require a recognized launcher, exact lane marker, and raw task outcome in process output. Gradle routes also require task and build outcome lines. Consumer and provider output includes SHA-256 lines for the raw XML, graph, and resolved binaries it produced. These records only become evidence after an independent archive digest and artifact audit bind their origin.

No archive yields `NOT_RUN`. A complete external unavailability observation yields `UNAVAILABLE` with its reason. A malformed attempted pass or a raw failure yields `FAILED`. A producer `PASSED` string cannot replace raw files or audited provenance.

## Gate routes

| Gate | Verifier and pass boundary |
| --- | --- |
| staged-artifacts | `qualify.audit_staging` verifies the full repository; both selected target binaries match the independent audit. |
| staged-consumer | A frozen foundation consumer group or the approved full-suite case contract verifies XML identities, provider graph, resolved binary bytes, exact lane, and process output. Bounded foundation bundles remain `NOT_RUN`. |
| numerical-parity | `compare.compare` replays all 14 frozen traces. The source adapter computes SHA-256 of `git archive --format=tar <candidate>`, matching actual producer receipts. The 318 adopted prospective case identities are separate rule and arithmetic subgates. A 14-trace receipt without those raw cases fails. The adopted catalog and checker must match their pinned Git blobs. |
| physical-correctness | Candidate sleep/wake phase checks report default and configured profiles separately. The default baseline failure remains `125,847/126,000`. The separate approved Weld and Pulley declaration requires 36,000 candidate states for each case, with raw callback order and physical metric checks. Baseline-only joint success does not qualify a port. Nominal candidate analytic evidence remains open. |
| unchanged-java-corpus | The reviewed `full_ci.py` archive verifier checks 2,385 original Java cases across 12 compile/runtime routes, pinned sources, case identities, logs, provider binaries, and raw archive seals. |
| java-source-compatibility | The same reviewed archive verifier runs the strict 216-type, 3,078-declaration comparison and Java source projection checks against staged JVM and Android class archives. |
| duplicate-provider | `qualify.check_providers` verifies both graph coordinates. The raw provider diagnostic, failing exit, exact lane output, and real dependency task must agree. |
| migration-journeys | `journeys.verify_evidence` checks the archive seal. This verifier rehashes 42 unchanged Java sources, checks compiled class bytes and build commands, then reruns both scene validators from raw input, logs, frames, physics observations, and CCD counters for all ten journeys. |
| performance-resource | The reviewed performance archive and reference environment verifiers run. Existing producer evidence still reports qualification unpassed. |
| publication-contract | `qualify.audit_staging` checks publication metadata and files. Every binary in all 21 targets must match the separately audited all-target hash map. |
| independent-review | Two distinct raw Sol sessions must contain exact-final-head standards and spec review outputs. Their actionable findings and resolutions must match the reports and committed evidence. |

The full staged consumer fallback applies to every approved lane, including devices, browsers, and Wasmtime. Call `consumer_contract(manifest, lane_id)` to get its approved case set and digest. A fallback receipt sets `consumer_group` to `full-suite`, includes `consumer_contract_sha256`, and runs a command naming the lane. Its XML names every selected `case.id` in a `testcase id` attribute. The 13 frozen foundation groups keep their original classname/name XML contract where their runtime applies. Neither contract supplies missing device or browser execution.

The Java archive receipt sets `producer` to `reviewed-full-ci`, `full_ci_archive` to a relative archive directory, and `full_ci_manifest_sha256` to that directory's `lane-manifest.json` digest. It lists both resolved publication binaries. The verifier executes the reviewed `full_ci.py` from pinned revision `00d2f949fd485287b737e905808bfb65be942733` against the transportable archive and checks its strict and corpus results. It does not accept a standalone compile summary or an invented case manifest.

The migration archive includes `evidence/sources.sha256`, all 42 source files under `evidence/sources/`, compiled classes, and raw scene evidence. It also includes both providers' resolved JARs under `evidence/resolved/` and the pinned observer instrumentation JAR. Source and dependency hashes must match the producer's pinned inputs and the independently audited producing JVM core binary at the same candidate commit. Rewriting `summary.json` or resealing `evidence.sha256` cannot replace the raw validator checks.

The joint physical archive lists `joint_physical_cases` for `weld-spring-equal` and `pulley-taut`. Each entry names a candidate trace and capture receipt. Each capture receipt binds case, candidate commit, Git archive source digest, JVM core artifact hash, trace digest, 36,000 states, 108,000 callbacks, and zero skips. `verify_joint_physical_cases` replays the approved metric equations and every step. A failed metric returns `FAILED` with per-case failure counts. The older Pulley parity reference still records 39 samples above its diagnostic solver tolerance and a 0.1208278904872957 m maximum extension. These observations do not change the prospective 0.01 m application limit.

The prospective numerical archive must provide all 318 `prospective_cases`, their raw reference and candidate traces, capture receipts, and arithmetic audit records. The verifier pins the adopted 318-case catalog and executable comparator to revision `7213238591db1611da86cdec075978190ca6d52f`. It checks exact case identities and per-case source, artifact, trace, step, and catalog fields before replaying the rule comparator. An independent target arithmetic oracle and bound target captures are still absent. The current adopted policy's baseline self-check had 41 failed derived rules, four unpassed premises, and one failed physical case. The gate remains unpassed even when a rule comparison succeeds; a producer result string cannot qualify arithmetic.

The independent-review raw sessions contain one final assistant JSON output with `kind: independent-review-result`, `review_kind`, `candidate_sha`, `verdict`, `assessment`, `reviewed_paths`, and full `findings`. Each report must match that raw output. Earlier structured raw findings must appear in the final output. A finding has an ID, severity, description, and a resolution with a committed evidence path and SHA-256 at the final head. Two empty report files cannot hide raw actionable findings.

Historical local Java and migration archives exercise positive verifier paths at their captured commits, including a native lane selecting a separately audited JVM migration producer. The Java test includes a separate synthetic facade fixture; the joint test repackages frozen baseline states to exercise the parser. Neither fixture qualifies a final candidate. No final 112-lane runtime set, target arithmetic oracle, candidate Weld/Pulley capture, all-target staging audit, sustained performance result, or two resolved final-head reviews is supplied by this module.
