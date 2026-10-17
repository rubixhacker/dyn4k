# Numerical preflight for the full compatibility corpus

Use this package when the full port recorder can emit the frozen record stream.
It prepares references and checks for [Run the full compatibility corpus and unchanged migration applications](https://github.com/rubixhacker/dyn4k/issues/42). It does not qualify a port, target runtime, or release.

## Frozen inputs and decisions

[The catalog](../../tools/numerical/fixtures.json) has 14 trace members in four profiles. It records the dyn4j 6.0.0 source revision `058bf6d982a0fb89b54050f929f6ea9dae53b714`, JAR SHA-256 `204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e`, recorder source hashes, archive and member hashes, input and decompressed-stream hashes, actions, sample schedules, counts, units, limits, and approval links. The six configured captures bind the manifest SHA-256 `7efd60aa76cab10fdc27eb8e968a2868e854433cc4556e10257dbd290a63e554`. Repetition 1 at each outer cadence is the approved reference; repetition 2 is corroboration. The historic `PENDING` labels in the original research manifests predate the linked approvals and were not changed.

The catalog retains the [approved nominal rotation caps](https://github.com/rubixhacker/dyn4k/issues/7#issuecomment-6162049136) and [configured sleep/wake caps](https://github.com/rubixhacker/dyn4k/issues/7#issuecomment-6184664626) with zero relative allowance. Position and velocity vectors use separate x/y scalar checks. Orientation alone uses the shortest wrapped angle; `rotationIncrementSum` uses direct difference. Contact normal/tangent rules use directed angle, magnitude, and required unit-length checks. The signed impulse rules retain N s. No rule widens a limit for a target or after a failure.

The default sleep/wake traces keep their failed [represented-geometry physical gate](https://github.com/rubixhacker/dyn4k/blob/b7af287c3581f402053511d9556d65e610d71a5e/docs/research/sleep-wake-penetration-acceptance.md): 125,847 failures among 126,000 end states. The configured baseline separately passed 432,000 internal states and 252,000 endpoint mappings under its [approved physical ceilings](https://github.com/rubixhacker/dyn4k/blob/164dc39eb086ac202fdffa8a493915c216bc1be0/docs/research/sleep-wake-quality-acceptance.md). The endpoint rows are copies, not extra time steps. The four Weld/Pulley members remain parity references and diagnostics. Their physical residual gate is **UNPASSED** because no physical bound was approved.

## Commands and result meanings

Use Python 3.11 or later. Supply an extracted member from its hash-checked release archive. For example:

```sh
python3 -m unittest discover -s tools/numerical -p 'test_*.py' -v
python3 tools/numerical/compare.py audit-reference --fixture configured-30-r1 --reference /path/to/Q-sleep-wake-outer30-repeat1-0.jsonl.gz
python3 tools/numerical/physical.py --fixture configured-30-r1 --reference /path/to/Q-sleep-wake-outer30-repeat1-0.jsonl.gz
python3 tools/numerical/replay_approved.py default-exact --package /path/to/dyn4k-sleep-evidence --output /tmp/default-exact.json
python3 tools/numerical/replay_approved.py configured-exact --package /path/to/dyn4k-quality-candidates --archive /path/to/dyn4j-sleep-wake-quality-20261014.tar.gz --output /tmp/configured-exact.json
```

`audit-reference` verifies the exact gzip member, decompressed stream, input header, record kinds and counts, finite numbers, contiguous states, event order, and configured endpoint copies. Its `PASSED` result is **frozen baseline only**. `physical.py` first makes that audit, then measures exact rational depth from stored binary64 transform coefficients against each phase ceiling. It returns `PHYSICAL_PASSED`, `PHYSICAL_FAILED` (exit 2), or `INVALID` (exit 1). It does not execute physics.

The future port recorder must preserve every record kind, step, event order, callback method, payload structure, body/contact identity, and matched contact-point order. The candidate trace may be JSONL or gzip JSONL. Its receipt must contain:

```json
{
  "source_sha256": "<exact candidate source-tree digest>",
  "artifact_sha256": "<exact staged artifact digest>",
  "candidate_commit": "<exact 40-character candidate Git SHA>",
  "trace_sha256": "<candidate trace file SHA-256>",
  "reference_source_revision": "058bf6d982a0fb89b54050f929f6ea9dae53b714",
  "reference_artifact_sha256": "204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e",
  "reference_trace_sha256": "<catalog gzip member SHA-256>",
  "expected_counts": {"inputs": 1, "event": 935967, "state": 72000, "outer-endpoint": 18000, "instrumented-callback": 2, "action": 1},
  "executed_counts": {"inputs": 1, "event": 935967, "state": 72000, "outer-endpoint": 18000, "instrumented-callback": 2, "action": 1},
  "skipped": 0
}
```

The count example is for `configured-30-r1`. The candidate source digest and artifact digest must come from the exact candidate build. Invoke:

```sh
python3 tools/numerical/compare.py compare --fixture configured-30-r1 --reference /path/to/Q-sleep-wake-outer30-repeat1-0.jsonl.gz --candidate /path/to/port.jsonl.gz --receipt /path/to/receipt.json --expected-source SOURCE_SHA256 --expected-artifact ARTIFACT_SHA256 --expected-commit CANDIDATE_GIT_SHA
```

Exit 0 means `PASSED` for every declared record and approved numeric rule. Exit 1 means `FAILED` or `UNPASSED`; the JSON result distinguishes them. Missing or nonfinite values, changed hashes, wrong identities, empty/skipped/incomplete suites, missing fields, changed callback order, and exceeded limits fail. Every numeric path without an approved rule is listed under `unpassed_channels` and forces `UNPASSED`, even when its values happen to equal the baseline. This includes configured TOI fields and independently evaluated transform getters until their field semantics and formula-specific bounds are qualified. The [TOI numbers in the acceptance recommendation](../planning/acceptance-implementation.md) are proposed, not approved. Exact same-run relationships and configured candidate runtime math need additional qualification in the parent task.

## Evidence boundary

The [verified nominal baseline audit](https://github.com/rubixhacker/dyn4k/blob/f5053629d68dc134092434310c3d130ee1c0d9b5/docs/research/nominal-rotation-comparator.md) passed 144,000 rotation and 36,000 inherited-transform checks against its exact frozen member. That certified audit is retained as baseline evidence; this generic comparator does not replace its analytic enclosure. The [configured exact-consistency audit](https://github.com/rubixhacker/dyn4k/blob/44dd7cf05502fa4b5fdc3523e3271c3cba335de8/docs/research/sleep-wake-quality-exact-checks.md) passed on six frozen captures, including 5,615,802 events. It remains a separate same-run check, not a port result.

The package has no candidate trajectory. [The parent corpus task](https://github.com/rubixhacker/dyn4k/issues/42) must connect a full recorder, establish every remaining channel bound or report it unpassed, rerun exact same-run checks and physical gates on the candidate, and qualify each target/runtime/build lane. The default physical failure, Weld/Pulley physical gap, unchanged Java application journeys, and full corpus coverage remain open.

`replay_approved.py` restores the exact checker files from pinned Git commits into a temporary directory. It runs the default and configured same-run checkers above. With the exact nominal gzip member, `nominal-rotation --raw MEMBER --output NEW_DIRECTORY` runs the original certified rotation audit. A missing pinned Git object or mismatched checker hash stops the replay. These commands inspect frozen baseline bytes only.
