# Proposed penetration phases for the frozen sleep/wake references

Status: **event evidence verified; exact phase boundaries proposed for live review**. No numerical limit, physical acceptance result, port comparison or target-runtime qualification is established here.

Supports [Prepare baseline-anchored sleep/wake penetration phase schedules](https://github.com/rubixhacker/dyn4k/issues/26) and [Define numerical and migration acceptance](https://github.com/rubixhacker/dyn4k/issues/7). The approved rule is to freeze one explicit schedule per selected timestep from baseline contact/action/sleep events, apply that same schedule to every port, and check every end-of-step sample. A failing port sample cannot move into a different phase. The approved physical observable is the deepest transformed dynamic-square vertex below the floor top; callback manifold depths remain separate diagnostics. This report proposes the remaining boundaries, not numerical budgets.

## Frozen identity and scope

Only the selected run1 members of the [published sleep/wake archive](https://github.com/rubixhacker/dyn4k/releases/download/calibration-raw-20260914/dyn4j-sleep-wake-20260914.tar.gz) were inspected. Archive SHA-256: `89d88301ad5ea14a621d8a6e86bfc3dfc90f84a0d7e8abda65f2f526de1b5bee`. Selection remains [manifest revision `4674e089d6f968bf752741f2be85cf2048962552`](https://github.com/rubixhacker/dyn4k/blob/4674e089d6f968bf752741f2be85cf2048962552/docs/research/initial-reference-review-manifest.json), SHA-256 `b42174c7523bea9687e4ab015a215b4e652c2446df73d2f41e836e8a165c1208`. Historical pending-approval fields in that immutable manifest predate [reference approval](https://github.com/rubixhacker/dyn4k/issues/7#issuecomment-6160940265).

| Hz | Selected gzip SHA-256 | Decompressed SHA-256, including newlines |
| --- | --- | --- |
| 30 | `86cfa767974174a2b35fea477ab02451aae21ac5a779ba6e40d12e4874112ebe` | `9851e31853012a0d1fde661e9e7c913643e5ab278e06bbf7fcc0f914a7ea8bda` |
| 60 | `ae6fb99402d239569fab8bba950429318879cdb13fb7609833e5f3c7cda68b28` | `ba4c9c73d73ef0304a9b6308d370aaa7a23d699cb841ca61dbcc5a135db61cf5` |
| 120 | `5bad36d62dcb0f3b1e2d526d2f1f97e0e62ede99ed9d3da0bef330ba0f510c75` | `19bc07fc64ff1ec3535fbf7bdd8e02fd8acc80917069ad23782941dc34c98db1` |

The companion [extractor](sleep-wake-penetration-phases.mjs) checks all these hashes, the three input-record hashes, the frozen manifest hash, the three source-member hashes, and the complete record/listener counts. It also checks contiguous state indices and ordered records, enumerates the complete contact/sleep histories and verifies schedule coverage. [Captured observations](sleep-wake-penetration-phase-observations.json) contain the exact hashes, counts, initial states, first callback signatures/orders, TOI payload indices, action snapshots and proposed intervals. No physics was rerun or reference regenerated.

## Observed events, not phase choices

All indices below are one-based world-step indices. Each state is sampled **after** `world.step(1,dt)` returns. Immediate wake snapshots are before that step, with orders 0 (before), 1 (action), 2 (after). The square starts at center `(0,0.51)`, with half-height 0.5; the floor top is 0. The center impulse is `(1,0)` at step `300*Hz+1`. These details come from archive `source/SleepWakeCases.java:24–58`, SHA-256 `c808ba452418f6bb88b0eeaf67955ad6691c7e6cdcd1487819d2397640bc00b7`, and [pinned recorder source][capture], whose archive SHA-256 is `064d701251261b94fd6538ae49a0737aae8e06c673738c36668838676cd31a28`.

| Event / sample fact | 30 Hz | 60 Hz | 120 Hz |
| --- | --- | --- | --- |
| First actual TOI payload / touchdown end-state | 1 | 3 | 5 |
| TOI payload callback orders, fixture then body overload | 6, 7 | 4, 5 | 4, 5 |
| First two `ContactListener.begin` callbacks | 2, orders 7–8 | 4, orders 7–8 | 6, orders 7–8 |
| First contact `preSolve`, then `postSolve` | 3, orders 1–2 then 3–4 | 5, orders 1–2 then 3–4 | 7, orders 1–2 then 3–4 |
| First sleeping end-state | 18 | 35 | 66 |
| Wake action and first awake end-state after sleep | 9001 | 18001 | 36001 |
| First sleeping end-state after wake | 9022 | 18043 | 36084 |
| Final end-state | 18000 | 36000 | 72000 |
| Contact-loss / recontact callbacks | none | none | none |

The two TOI payload callbacks in each run report the same event, with fractions `0.9183673469387763`, `0.22448979591836984`, and `0.9387755102040654` respectively. Earlier body/fixture TOI filter callbacks are candidate checks, not detected impacts. For example, the first filter callback is at step 1 in every run, whereas actual TOI payloads first appear at 1/3/5. Each touchdown end-state has identity rotation and center height exactly 0.5 in the frozen stream; the lower vertices touch floor top. Calling every sample before `ContactListener.begin` “free fall” would therefore include a touchdown sample.

The first contact solve is supported by the initial `postSolve` callback's `isSolved=true`, `isIgnored=false`, its matching `preSolve` step, and the pinned world execution order. This is the first solve of the newly created ordinary contact constraints; TOI processing already occurred earlier. A later repeated solved flag alone does not establish that a sleeping constraint was solved again.

Exactly two contact points begin per run. Their listener history remains present through the final sample: zero `end` or `destroyed` callbacks, zero subsequent `begin` callbacks, and one populated two-point `ContactListener.collision` update at every end-of-step detection from 2/4/6 onward (17,999 / 35,997 / 71,995 samples). There are no later TOI payloads. This establishes persistent **recorded contact history**, including the wake interval; it does not independently certify geometric support or any penetration bound. The single horizontal center impulse changes immediate velocity from `(0,0)` to `(1,0)`, leaves angular velocity zero, changes `atRest` true→false, and leaves the transform unchanged. Thus the stream does not supply a new collision-onset event at wake.

The source explains the distinct boundaries. [World step][world-step] solves existing constraints and calls contact `postSolve`, then processes CCD/TOI, then runs final collision detection, then calls `StepListener.end`. [TOI application][toi] interpolates the transform to the detected time and can return without further correction at zero separation. Ordinary contacts created during final detection are available to the next step's solve. [Island sleep processing][sleep] occurs inside constraint solving before the end-of-step snapshot. These phases explain observed timing; they do not mandate an acceptance-phase duration.

## Complete proposed schedule

**Proposal:** use the first actual TOI-payload step through the first completed ordinary contact-solve step, inclusive, as the initial impact interval. Begin settling at the following sample. Start rest at the first sleeping end-state. The wake action starts a new settling interval on its own step, because contact history persists; it does not automatically earn an impact allowance. All ranges below are inclusive.

| Proposed phase | 30 Hz | 60 Hz | 120 Hz |
| --- | --- | --- | --- |
| Initial approach / free fall, before TOI touchdown | no end-state samples | 1–2 | 1–4 |
| Initial impact, TOI touchdown through first ordinary contact solve | 1–3 | 3–5 | 5–7 |
| Initial settling | 4–17 | 6–34 | 8–65 |
| Rest before action | 18–9000 | 35–18000 | 66–36000 |
| Wake response / settling | 9001–9021 | 18001–18042 | 36001–36083 |
| Rest after wake | 9022–18000 | 18043–36000 | 36084–72000 |

This partitions all 126,000 end-of-step samples exactly once, with no gaps or overlaps. At 30 Hz there is initial motion during step 1, but its end-state is already touchdown, so the impact phase includes that sample. Time zero is the fixture's input state, not an end-of-step sample. The two immediate action snapshots likewise do not add end-of-step samples: the approved impulse/consistency checks cover them separately. The action step's resulting state is explicitly in wake settling.

“Rest” here names a frozen sample interval anchored to baseline sleep, not a permission to omit those samples or to classify a port by its own sleep flags. “Settling” similarly names the proposed interval, not a claim of monotonically decreasing penetration. Use the fixed Hz/step lookup on every target even if a port loses contact, wakes unexpectedly or sleeps at a different step; those changes remain separate exact-event failures.

## Human choices still open

1. **Approve or change the proposed impact-to-settling boundary.** The suggested three-step impact interval follows TOI touchdown, ordinary contact creation, then its first solve. This is a useful source/event-based convention, not a proof that physical transients have ended. A narrower one-sample “contact-creation impact” at 2/4/6 is possible, but would need a separate explicit disposition for TOI-touch samples 1/3/5 and would put the first contact solve into settling. Starting at the first TOI filter callback would conflate candidate checks with impacts. No interval here was chosen from a penetration maximum or adjusted to make a sample pass.
2. **Approve the rest and wake boundaries and initial-approach classification.** The table uses baseline sleep transitions and the exact action index. Wake settling shares the proposed settling category despite being horizontally driven; a distinct wake-response category would require a further independently justified budget. The initial-approach samples must receive an explicit physical acceptance rule/budget in the later decision. They are not exempt and do not acquire an implicit exact-zero ceiling from this report.
3. **Independently justify and approve numerical limits afterward.** The initial-approach, impact, settling and rest dispositions need applicable limits for the already approved geometric observable. No value or relative looseness is selected here. Every sample must pass its assigned rule. Callback depths, port parity, discrete event matching and runtime qualification remain separate gates.

This research packet can be reviewed independently of selecting those limits. It does not close the human acceptance decision.

## Reproduction and captured evidence

From this branch, with Node.js and the extracted frozen archive:

```sh
sha256sum /path/to/dyn4j-sleep-wake-20260914.tar.gz
node docs/research/sleep-wake-penetration-phases.mjs /path/to/dyn4k-sleep-evidence > observations.json
cmp observations.json docs/research/sleep-wake-penetration-phase-observations.json
```

The archive hash must match the value above. The extractor exits zero only after its identity, history, action and partition checks pass. `cmp` must exit zero. A failed hash or assertion is an invalid reproduction, not permission to regenerate the baseline or adjust the schedule. The extractor inspects frozen reference bytes and emits a proposal; it is not a physical-limit comparator.

| Scenario | Invocation | Binary observable | Captured artifact in this worktree |
| --- | --- | --- | --- |
| Published archive and source identity | `sha256sum` on local archive; source hashes checked by extractor | archive matches published hash; source assertions pass | `.omo/evidence/penetration-phases/identity.log`; observations JSON `sources` |
| Complete selected-stream audit and candidate schedule | `node docs/research/sleep-wake-penetration-phases.mjs EXTRACTED_ROOT` | exit 0; all hash/count/history/action/partition assertions pass | `.omo/evidence/penetration-phases/observations.json`, published as companion JSON |
| Published output matches captured result | `cmp .omo/evidence/penetration-phases/observations.json docs/research/sleep-wake-penetration-phase-observations.json` | exit 0 | `.omo/evidence/penetration-phases/validation.log` |

The local evidence ledger is `.omo/evidence/penetration-phases/README.md`. The parent review separately reproduces the extraction. This report makes no claim that unrun engine, runtime or physical-budget scenarios passed.

[capture]: https://github.com/rubixhacker/dyn4k/blob/0995a6bac84de882b0d04b6c3ea18162ca3b4a7c/calibration/src/Capture.java#L47-L154
[world-step]: https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/world/AbstractPhysicsWorld.java#L1225-L1332
[toi]: https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/world/AbstractPhysicsWorld.java#L1626-L1718
[sleep]: https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/world/Island.java#L163-L211
