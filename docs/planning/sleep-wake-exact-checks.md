# Approved sleep/wake exact-check verification

Status: bounded planning-enablement checking complete on frozen baseline bytes; no port or runtime qualification.

Supports [Complete and verify approved sleep/wake exact checks](https://github.com/rubixhacker/dyn4k/issues/25). The [live approval checkpoint](https://github.com/rubixhacker/dyn4k/issues/7#issuecomment-6167266418) governs the six-group package in the [immutable source-cited report](https://github.com/rubixhacker/dyn4k/blob/884ff5a6c2c1fe81384b9522511d5d7ef0d42e89/docs/research/sleep-wake-numerical-budgets.md). Its historical pending labels are unchanged. No new metric, limit, reference, or instrumented physics experiment is introduced.

## Coverage ledger

The new [checker](../research/sleep-wake-exact-checks.mjs) supplements the unchanged historical observation tool. Each failed relationship throws and exits nonzero. Numeric equality compares finite numbers with `===`, treating signed zeros equally; recursive object equality requires matching keys and ignores their serialization order. Schema keys for body/state/transform and snapshot properties are checked explicitly.

| Approved group | Implemented relationships | Sampling phases |
| --- | --- | --- |
| Fixed floor | Translation and center `(0,-0.25)`; cosine/sine/recorded angle `(1,0,0)`; zero velocities and accumulated angle; previous pose equals current. Floor sleep flag is allowed to vary across steps. | Initial, every end state, immediate before and after action |
| No applied forces | Both components of current/accumulated force and current/accumulated torque equal zero for both bodies. Property duplicates must agree. Gravity and contact impulses are not treated as these channels. | Initial, every end state, immediate before and after action |
| Sleeping dynamic state | Zero linear/angular velocities when asleep; every consecutive sleeping snapshot retains the prior sleeping pose. Entry pose belongs to that run; it is not compared exactly to another run's settled pose. | Every end state and immediate pre-action; general snapshot validation also applies after action, where the body must be awake |
| Immediate center impulse | Pre-state asleep with zero velocities; post-state awake with velocity `(1,0)` and angular velocity zero. All remaining recorded fields of both bodies, including fixtures, mass/configuration, both poses, force channels and recorder accumulator, remain unchanged. Only `atRest`, velocity, and their property duplicates may change. | Immediate before/action/after boundary only; following physics step uses ordinary state checks |
| Aliases and copies | Translation vector equals scalar pair; matrix equals `[c,-s,x,s,c,y]`; world/fixed-origin centers equal translation. Initial previous equals current; each end-state previous equals preceding current. Immediate action snapshots retain previous and current transforms. All ten duplicate properties (forces, torques, velocities, poses, world center, sleep flag) match their recorded owners. Local and mass centers are zero, establishing the center-alias premise. | Both current and previous transforms in initial/end/action snapshots; properties in initial and action snapshots |
| Timestep metadata | Five timestep getters equal the three pinned timestep values; first previous timestep/inverse are `1/60` and `60`, with ratios `2/1/0.5`; later previous equals current and ratio equals 1. | Every StepListener payload |

Recorded angles are compared only as copies or fixed floor values. No angle is recomputed through the auditor's math library. Dynamic awake translation/rotation and velocities receive no zero-error baseline-to-port allowance. Snapshot configuration getters such as change-in-position/orientation are preserved across the immediate impulse but gain no new independent computation budget.

The streaming wrapper additionally requires record-step/order continuity, a single initial snapshot, before/action/after order at `300*Hz+1`, action description, counts, and exact first/return sleep steps. Frozen compressed, decompressed and initial-input hashes remain separate identity guards. Hash identity binds the complete callback identity/order and every archived byte; this tool does not semantically compare a port callback stream with the baseline.

## Observed verification

Node `v26.10.0` executed all checks on 2026-10-14. The published archive hash was freshly verified as `89d88301ad5ea14a621d8a6e86bfc3dfc90f84a0d7e8abda65f2f526de1b5bee`. Existing reference and proposal manifests, source artifacts, and historical helper remain unchanged from the parent revision.

The [generated observations](../research/sleep-wake-exact-observations.json) record the complete successful traversal:

| Hz | End states | Initial / before / after | Timestep payloads | Listener records traversed | First sleep / return sleep |
| --- | --- | --- | --- | --- | --- |
| 30 | 18,000 | 1 / 1 / 1 | 54,001 | 233,995 | 18 / 9,022 |
| 60 | 36,000 | 1 / 1 / 1 | 108,001 | 467,981 | 35 / 18,043 |
| 120 | 72,000 | 1 / 1 / 1 | 216,001 | 935,967 | 66 / 36,084 |

Totals: 126,000 end states, nine initial/action snapshots, three immediate impulses, 378,003 timestep payloads and 1,637,943 listener records. Listener traversal does not imply numerical acceptance of contact/TOI payloads.

The [semantic test suite](../research/sleep-wake-exact-checks.test.mjs) passes **649 tests, zero failed/skipped/cancelled**. It reads representative records from all three frozen streams and clones them for synthetic mutations. These are tests, not replacement references. The initial no-op scaffold failed rejection tests with `Missing expected exception`; later schema tests exposed 36 missing/extra-field rejection gaps before schema enforcement. The final implementation passes those regressions.

Tests exercise force/torque channels on both bodies in every phase; translation/matrix and center aliases; all duplicate properties; premature previous-transform advancement; initial recorded-angle copy disagreement; coherent sleeping/floor drift; sleeping velocity; impulse velocity/sleep/fixture/mass/accumulator/pose changes; every timestep getter at first and later steps; missing/extra body fields; and nonfinite values. Positive boundaries cover signed zero, changing floor sleep flags, differing own-run sleeping entry poses, unfrozen dynamic awake poses, no auditor-angle recomputation, and post-impulse physics velocity differing from `(1,0)`.

The altered-file test rejects at the compressed identity guard before JSON decoding. Semantic rejection tests call the real exported checker directly on mutated records, without the hash wrapper, so their failures demonstrate invariant checking rather than hash rejection. Full-stream success exercises the streaming wrapper on the actual approved inputs.

## Reproduction

Retrieve the [published archive](https://github.com/rubixhacker/dyn4k/releases/download/calibration-raw-20260914/dyn4j-sleep-wake-20260914.tar.gz), verify the archive hash above, and extract it. From this task branch:

```sh
node --check docs/research/sleep-wake-exact-checks.mjs
node --check docs/research/sleep-wake-exact-checks.test.mjs
SLEEP_EVIDENCE=/path/to/extracted/dyn4k-sleep-evidence \
  node --test docs/research/sleep-wake-exact-checks.test.mjs
node docs/research/sleep-wake-exact-checks.mjs \
  /path/to/extracted/dyn4k-sleep-evidence > exact-observations.json
sha256sum exact-observations.json
```

Expected observation hash: `072ee5e01a336732555442da8087562b9ccab98992a03d422c6826239e9b894f`. Tests require real extracted evidence and fail if unavailable; they do not silently skip. No Java execution or simulation is needed. Syntax checks and actual executions were used because the JS LSP is unavailable and installation was previously declined.

| Artifact | SHA-256 |
| --- | --- |
| `sleep-wake-exact-checks.mjs` | `803f78a03aca84b4177de0d22d6d4f3b2bef79ce258e16d8028e65fcaeb7346a` |
| `sleep-wake-exact-checks.test.mjs` | `f7d19ae9fc5b5650851fd080ddae8f4de801cfe1fdea88b6b66eb4491127fabc` |
| `sleep-wake-exact-observations.json` | `072ee5e01a336732555442da8087562b9ccab98992a03d422c6826239e9b894f` |

The issue checkpoint supplies the exact publication revision.

## Review and limits

Main-session self-review traced all six approved groups, the first-step/impulse/return-to-sleep transitions, field aliases, and malformed-data boundaries against the governing report. Manual QA ran the actual CLI and exported semantic functions, not only syntax checks. This is bounded executable evidence plus manual review, not formal proof or independent certification.

| QA scenario | Evidence | Result |
| --- | --- | --- |
| Complete frozen streams and identity | Generated observations and archive hash above | PASS |
| Semantic corruptions across all phases | Executable 649-case test suite | PASS |
| Distinct hash corruption | Test `compressed hash guard rejects altered bytes before semantic decoding` | PASS |
| Phase and numerical boundaries | Named tests for previous copies, own-run sleep pose, floor flag, signed zero, and next physics velocity | PASS |
| Syntax and patch hygiene | Both `node --check` commands and `git diff --check` | PASS |

This closes the approved exact-package helper coverage gap only. It is not a complete acceptance comparator. Awake contact trajectory/rotation budgets, numerical contact/TOI payloads, derived configuration getter budgets, independently justified physical budgets, branch-margin evidence, unchanged Java migration-runtime execution, broader corpus checks and every in-scope target's actual port/runtime qualification remain unresolved or unpassed. Every non-deprecated target, including experimental targets, remains in scope. No reference replacement, budget widening or target waiver follows from these checks. [Define numerical and migration acceptance](https://github.com/rubixhacker/dyn4k/issues/7) remains open.
