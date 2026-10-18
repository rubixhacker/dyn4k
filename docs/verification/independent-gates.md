# Independent gate archive verifier

The verifier evaluates one exact Git commit and one approved runtime lane. It reads the complete suite manifest frozen at `6f983ad3a36bdc549c32f5d0883b0a47b28e1963`. It returns a SHA-256 result digest. Retain the result with its input archives.

Run it with the candidate SHA, lane ID, and independently audited target binary hashes:

```sh
python3 tools/qualification/independent_gates.py \
  --candidate-sha "$CANDIDATE_SHA" \
  --lane 'jvm:Java:minimum:no-optimize' \
  --expected-artifacts /path/to/audited-target-hashes.json \
  --expected-runtime-identity 'selected runner identity' \
  --archive duplicate-provider=/path/to/extracted-provider-archive
```

`--expected-artifacts` contains `dyn4k-core` and `dyn4k` SHA-256 values. Obtain them from an independently checked staged publication. Obtain `--expected-runtime-identity` from the selected runner record. Values copied from the same untrusted receipt do not provide independent checks. The evaluator also checks the raw Git tree against the exact candidate commit.

An archive directory contains `receipt.json` and every raw file named in `files`. Each file entry has `path`, `sha256`, and original `mtime_ns`. The receipt has `schema: 1`, `candidate_sha`, `source_tree`, `artifact_hashes`, `lane`, and `runtime_identity`. It also has the lane's `target`, `runtime`, `version`, and `configuration`. Its `process` has a nonempty command, integer exit code, `started_ns`, and `finished_ns`. Optional `stdout` and `stderr` paths must name inventoried files. File times must fall within the process window. Extraction time does not replace the recorded original time. The verifier rejects unlisted files, duplicates, traversal, symbolic links, altered bytes, and wrong identities.

The importable `evaluate(manifest, candidate_sha, lane_id, archives, repository, expected_artifact_hashes, expected_runtime_identity)` function returns `gates`, `status`, `manifest_sha256`, and `result_sha256`. `archives` maps gate names to extracted directories. `qualify.py` can call it with the approved manifest, independently audited hashes, and selected runner identity. Require every applicable gate and all four global gates to pass before passing a lane. A bounded result does not qualify 112 lanes.

| Gate | Raw verifier route | Current pass boundary |
| --- | --- | --- |
| staged-artifacts | Full staged repository through `qualify.audit_staging`, plus target hashes | All 21 target publications, metadata, sources, documentation, license, and sidecars must pass. |
| staged-consumer | Existing `artifact.verify_bundle` for bounded archives; frozen consumer XML, graph, and resolved bytes for full receipts | A bounded archive is `NOT_RUN`. A full receipt needs the selected consumer task, exact cases, both binaries, and runtime/configuration binding. |
| numerical-parity | `compare.compare` for every frozen fixture and raw candidate trace | All 14 fixture identities, counts, reference records, candidate records, and capture receipts must pass. |
| physical-correctness | Approved phase ceilings over candidate traces after `compare.compare` | Every physical fixture and every represented state must pass. Default profile failures remain failures. |
| unchanged-java-corpus | Candidate committed case manifest, pinned baseline Git sources, raw compile/run logs, provider graph, binaries, and JUnit XML | The producer has not committed `unchanged-java-corpus-cases.json`; absent evidence is `NOT_RUN`. |
| java-source-compatibility | Candidate committed case manifest, exact Git sources, nine required probe scopes, raw compile/run logs, provider graph, binaries, and JUnit XML | The producer has not committed `java-source-compatibility-cases.json`; absent evidence is `NOT_RUN`. |
| duplicate-provider | `qualify.check_providers` over raw dependency graph plus failing stderr and exit code | Both providers and the expected diagnostic must appear. |
| migration-journeys | `journeys.verify_evidence` over the raw ten-journey archive | The pinned sample revision, ten distinct results, final candidate, and candidate JAR hash must agree. |
| performance-resource | `verify_candidate_archive` raw and environment verifiers | Existing producer returns `qualification: unpassed`; verified raw records remain `NOT_RUN` for this gate. |
| publication-contract | Full `qualify.audit_staging` and target binary hash comparison | All publications must pass the staged contract. |
| independent-review | Two distinct raw CLI sessions with `turn_context.model = gpt-6-sol` | Standards and spec reports must target the exact final head and resolve every actionable finding. |

The numerical receipt lists `fixtures` with `key`, `reference`, `candidate`, and `capture_receipt` paths. Its source digest is SHA-256 of the lowercase Git tree ID encoded as UTF-8. The comparator receives that digest and the independently audited `dyn4k-core` binary digest. Performance and migration producer archives belong under `evidence/`. The full staged repository belongs under `staged/`.

Java gate manifests belong under `tools/qualification/` at the candidate commit. Each has `schema: 1`, `kind`, `sources`, and `cases`. Source entries name a path and SHA-256. Case entries name `classname` and `name`. The unchanged corpus manifest also records baseline revision, 199 source files, and 2,171 test annotations. The source compatibility cases cover all nine scopes named in the verifier. A raw Java archive contains the copied sources under `sources/`, compile and run receipts, JUnit XML, provider graph, and both resolved binaries. No such committed producer manifest exists in this branch.

`UNAVAILABLE` requires a separate receipt with the exact SHA and lane. It must give a concrete `reason`, `observed_by`, and positive `observed_at_ns`. It records an absent external runtime or service. No archive means `NOT_RUN`. A malformed or failing attempted archive is `FAILED`. A producer's `PASSED` string cannot replace raw prerequisites.

The verifier does not authenticate an archive's origin. Pin the downloaded digest or runner provenance before trusting its receipt. Supply artifact hashes and runtime identity from separate selections. The current foundation bundle verifier cannot replay some older local bundles. Their probe JSON predates its per-group accounting fields. Those bundles remain historical evidence without a full lane pass.
