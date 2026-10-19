# Central qualification collection

The `central-qualification-collection` job runs after the Ubuntu, hosted publication, native, and Safari jobs. It downloads every artifact retained by those jobs, including failed-route archives. It checks artifact names against `GITHUB_SHA`, inventories downloaded bytes, checks source identities and available producer archive formats, and verifies the inventory again before evaluation. The collection artifact retains the downloaded raw bytes, collection logs, exit codes, and the 112-lane result.

The collector writes `assembly-inputs.json` with all 112 approved lane IDs. It includes an attempted duplicate-provider archive on the matching JVM lane when present, but supplies no independent hashes or audit values. That attempted gate is `FAILED` until audited. Other missing routes are `NOT_RUN`. `qualify.py record` retains all required lanes as `NOT_RUN` without a signed audit. A producer receipt that says `PASSED` is recorded as producer evidence only. A changed archive or failed raw command is recorded as `FAILED`; its files remain in the central upload. The workflow exits unsuccessfully while any lane is unpassed.

The Ubuntu job also uploads `duplicate-provider-$GITHUB_SHA`. Its receipt records the exact candidate tree, audited staged JVM binary hashes, Java identity, dependency graph, Gradle command, raw failing task output, and file checksums with execution-window timestamps. The expected duplicate-provider error is a failed Gradle process. The receipt's producer status does not replace an independent audit.

## Cross-run raw transport

Use `collection.py --source-index /absolute/index.json` to select later-run or retained raw sources. The index is version 1. It names the exact candidate SHA and Git tree, then lists sources and bindings to approved lane/gate names. A source may be a pinned local file or directory, a named artifact from the current run, or a GitHub Actions artifact selected by repository, workflow path, run ID, run attempt, artifact ID, artifact name, head SHA, and API byte size. A packed source also pins its downloaded byte length and SHA-256. A directory pins every file's size and SHA-256 plus the canonical inventory digest. The collector rejects duplicate source IDs, artifact IDs, and lane/gate bindings. It generates all 112 lane entries from the immutable approved manifest even when the index selects one source.

For example, a local ZIP selection has this shape. Replace the placeholders with actual candidate, tree, path, size, and hash values. The global performance binding selects raw evidence; it does not qualify the gate.

```json
{
  "schema": 1,
  "candidate_sha": "<40 lowercase hex>",
  "source_tree": "<40 lowercase hex>",
  "sources": [{
    "id": "tvos-raw",
    "origin": {"kind": "local", "path": "/absolute/retained.zip"},
    "transport": {"format": "zip", "size": 64845, "sha256": "<64 lowercase hex>"}
  }],
  "bindings": [{"source_id": "tvos-raw", "lane": null,
                "gate": "performance-resource", "target": "tvosSimulatorArm64"}]
}
```

For an Actions source, replace `origin` with `kind: github_actions`, `repository: rubixhacker/dyn4k`, `workflow: .github/workflows/qualification.yml`, and exact numeric `run_id`, `run_attempt`, `artifact_id`, `api_size_in_bytes`, plus `name` and `head_sha`. Set `DYN4K_GITHUB_TOKEN` in the process environment; the CLI does not print it. GitHub's artifact metadata does not prove which rerun attempt created an artifact, so this route currently accepts only attempt 1 and rejects later attempts. The current-run selector uses `kind: same_run`, the same repository/workflow/run/name/head fields, and CLI `--run-id` and `--run-attempt`. It must name a downloaded artifact directory and also accepts only attempt 1 until its artifact attempt can be proved.

The collector copies original bytes under `raw/sources/`, checks source bytes before and after copying, and records failed or partial copies. Packed local and external files are size checked before hashing or copying; both operations stream with a byte cap. Directory copies cap cumulative member count and bytes while copying each regular file. A growing directory can leave bounded diagnostic bytes under a `FAILED` row. ZIP and TAR members reject traversal, duplicate names, symlinks, nonregular entries, and extraction bounds. `collection.py --verify` requires the exact raw child set and recorded bytes for every source, including failed sources. Only an acquisition recorded without raw bytes may have an empty source folder. A known `portable-mobile-capture-v1` ZIP is bound to its candidate and target through its retained stage receipt and capture result. Its gate remains `NOT_RUN`: that producer format lacks the complete independently audited gate receipt. Other copied formats remain `NOT_RUN` with an explicit unsupported-format reason. An invalid selected source is `FAILED`; an omitted source leaves its gate `NOT_RUN`. Neither state becomes `PASSED` from a producer receipt.

For a workflow run without new producer recapture, dispatch with `cross_run_only=true` and `cross_run_source_index` containing the exact JSON index. The workflow accepts pinned Actions and same-run origins; arbitrary local paths are reserved for the local CLI and are rejected when a workflow token is present. The job retains the index and same-run download before checkout or upstream replay setup. It has `actions: read` and passes the token only as a collector environment variable. A download or fetch failure records a failed source and retains any bytes received in the central raw upload. The dispatch commit must equal the index candidate; it cannot import an older candidate into a newer head.

For an external audit handoff, run `collection.py --audit-input-dir DIR --trusted-key-sha256 PIN --repository CHECKOUT --candidate-sha SHA --artifacts-dir DOWNLOADED --output COLLECTION`. `DIR` must contain `archive-map.json`, `audit.json`, `audit.sig`, `public.pem`, `candidate-manifest.json`, `staged-audit.json`, and `evidence.json`. `CHECKOUT/build/staging-repository` must contain the exact staged bytes for the public qualifier to recheck. `PIN` must come from a trusted channel outside the producer artifact. The collector copies and hashes the audit inputs and every referenced archive file or directory into the collection. It passes only frozen archive paths to `qualify.py record`, which calls `independent_adapter.verify_lanes` for signature, staged bytes, archive digests, selected cases, and all 112 lanes. Supply an independent performance verification key with both `--independent-performance-key` and `--performance-key-sha256` when required. The key path and pin must come from outside producer inputs. A missing signature, pin, or staged repository leaves this handoff `NOT_RUN`; a rejected supplied audit is `FAILED`. The collector never creates a signing key or a signed audit.

Raw transport now accepts explicit later-run sources. The signed adapter is integrated, but complete format adapters for 21-target artifacts, 28 runtime families, and 112 lanes remain open. The collector cannot automatically obtain later Android devices, minimum-version browsers, physical Apple devices, sustained performance references, or final-head reviews. Their exact-source archives, runtime identities, staged hashes, candidate manifest, independent signed audit, trusted key fingerprint, and review evidence still need to be supplied. Cross-run transport alone does not qualify a lane.
