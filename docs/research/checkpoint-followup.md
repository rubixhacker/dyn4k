# Approved joint checkpoint follow-up

Task: [Execute the approved baseline calibration experiment](https://github.com/rubixhacker/dyn4k/issues/15).

The user approved using exact later upstream checkpoints to activate previously idle probes. [The approval record](https://github.com/rubixhacker/dyn4k/issues/15#issuecomment-5658147012) preserves the scope: reconstruct preceding source steps/actions and retain the actual world and solver state. It does not approve new combined stimuli, replacement Distance limits, baseline exceptions, references or numerical tolerances.

Baseline source remains `058bf6d982a0fb89b54050f929f6ea9dae53b714`, dyn4j 6.0.0. The original corpus at `d50765a289edcc1e88b0c639ed813ee749b627a5` is preserved. Supplemental rows use `P-JCP-` IDs and do not replace original `P-J-` observations.

## Executed and verified

Two fresh JVM invocations of the integrated harness each captured **92 independent 600-step continuations plus 121 preparation segments: 213 segments and 56,224 steps**. All 213 gzip traces, query streams and summaries match byte-for-byte. No case was nonfinite or rejected. The independent structural audit counted 179,781 ordered listener events and 236,352 raw records per repetition, with no missing planned states.

All **14 unchanged checkpoint controls** match the original upstream input state/settings/world exactly. Every complete state in the next corresponding upstream segment also matches exactly: 120 states across the controls. This tests the reconstructed state and its immediate evolution, beyond setter similarity. The source review separately verified preceding actions, step counts, anchors, forces, and use of the same live world without resetting solver state. The Distance seed initially inherited 10 position iterations from `fixedDistance`; audit caught this and restored the actual `springWithMaxForce` value 2 before either final repetition. Earlier temporary runs are excluded.

[Bindings and all row IDs](joint-bindings.md#approved-checkpoint-supplement) give the exact method/checkpoint schedules. Preparation steps are recorded, source action chains retained, and each resulting input snapshot is published. The existing 201/401 toggles and target movement at 201 use continuation-relative time. Unchanged upstream methods/assertions and original P rows remain in the harness.

## What is now exercised

[Measurements](calibration-evidence/checkpoints/measurements.json) contain completed-state extrema, step locations, exact nonzero counts, initial/final values, and enabled positive-cap ratios for every continuation. They are diagnostics, not newly adopted thresholds.

- **Motor target correction:** with the source's 100 N / 10 N·m caps, correction factor 0 preserves the 1 m and pi/6 target errors. Factor 0.3 reduces final errors to approximately 7.93e−9 m and 3.05e−9 rad; factor 1 reaches 0 m and approximately 1.11e−16 rad. The approved moving-linear and moving-angular probes now respond, with final respective residuals approximately 6.35e−9 m and 2.60e−8 rad.
- **Spring caps:** Distance and Wheel 10 N rows attain both −10 and +10 N; Weld's 0.25 N·m row attains 0.25 N·m. Zero-cap rows report zero spring force/torque. The source controls attain their 200 N, 5 N·m and 200 N caps. Large-cap variants are enabled but do not saturate: maximum absolute cap ratios are about 0.9742 for Distance 1000 N, 0.5570 for Weld 10 N·m and 0.4543 for Wheel 1000 N. They are nonbinding observations, not saturation proof.
- **Limit correction:** Prismatic source controls correct to lower 6 m and upper 3 m; Wheel controls to lower 1 m and upper −0.5 m. Revolute controls correct to 10° and 5° on their first continuation step and subsequently reach their opposite bounds. Weld lower/upper variants reach the neighborhoods of their ±0.2pi limits with their source spring/cap settings. These are observed values, not an approved constraint-error allowance. Revolute position correction can have zero reaction torque, so reaction magnitude alone is not the gate.
- **Pulley slack:** the source slack-enabled continuation explores both negative and positive weighted-length error (approximately −0.57143 to +0.09415 m). This establishes a real changing geometry instead of the previous balanced seed. Signed length error alone does not establish successful taut/slack transitions at every toggle or absence of transient stretch; ordered traces and force/configuration fields remain available for that review.

False/true/toggle variants retain their actual outcomes. A scheduled toggle after the original drive has decayed is not automatically claimed as active constraint or cap coverage. No fresh impulses were invented to ensure each switch saturates a solver branch.

## Published artifacts and reproduction

The [evidence directory](calibration-evidence/checkpoints/) contains both complete supplemental raw repetitions, all 213 input headers, query/summary streams, structural hashes/counts, measurements, control comparison results, source hashes, runtime identity and exact commands. Unlike the original large corpus, these supplemental raw traces are included in the branch.

```sh
./calibration/run /absolute/new-checkpoints-a P-JCP-
java -Xmx768m -cp 'calibration/classes:calibration/cache/*:calibration/cache/upstream/src/test/resources' Main /absolute/new-checkpoints-b P-JCP-
java -Xmx768m -cp calibration/classes Audit --complete /absolute/new-checkpoints-a /absolute/new-derived 56224
./calibration/scripts/checkpoint-controls.sh /absolute/original-upstream-traces /absolute/new-checkpoints-a /absolute/new-control-evidence
```

The control comparison uses the original U traces; those remain in the original host corpus. The script requires exact equality, with no tolerance widening. `checkpoint-measurements.jq` consumes one audited gzip trace through `gzip -cd FILE | jq -s -f calibration/scripts/checkpoint-measurements.jq`. The parallel runner now includes the supplemental `P-JCP-` partition once. OpenJDK 25.0.3 on this host remains the tested runtime; no all-target claim is made.

## Remaining decisions and work

Historical checkpoint frontier below is superseded for joint-fixture execution by the [remaining joint experiment](interaction-results.md). Its combined, valid-range, equal-limit and driven-transition additions retain all original observations. Current acceptance questions are consolidated in the [review packet](calibration-acceptance-review.md).

The approved checkpoint follow-up is executed and published, but the overall calibration task remains open:

- Combined Prismatic/Wheel spring+motor+limits stimuli still need an explicit combined binding; no complete upstream checkpoint supplies all three.
- The API-rejected Distance range remains visible; a valid replacement was not selected by this approval.
- Dormant toggles and nonsaturating high caps cannot be represented as exhaustive mode coverage.
- Negative Angle overflow, failed original stack sleep/wake and CCD passage observations remain baseline findings requiring review.
- The original approximately 40 GB full raw corpus remains local pending remote archive publication. It is not included in the supplemental archives.
- Initial reference approval and numerical acceptance remain with [Define numerical and migration acceptance](https://github.com/rubixhacker/dyn4k/issues/7).
