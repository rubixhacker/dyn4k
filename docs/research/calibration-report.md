# Baseline calibration execution report

Task: [Execute the approved baseline calibration experiment](https://github.com/rubixhacker/dyn4k/issues/15).
Baseline: dyn4j 6.0.0 source `058bf6d982a0fb89b54050f929f6ea9dae53b714`, binary SHA-256 `204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e`.

**Status: experiment execution and evidence publication complete; numerical acceptance remains for human review.** These are unreviewed experimental captures. No numerical limit, baseline exception, supported operating range or frozen reference is approved.

**Approved follow-up:** [Exact upstream checkpoint supplement](checkpoint-followup.md) adds 92 continuation probes, with 56,224 steps per repeat including recorded preparation. Both repeats match byte-for-byte; all 14 source controls match original upstream input snapshots and trajectory prefixes. Supplemental raw traces are published. Original corpus totals below remain unchanged.

**Final execution supplement:** [Remaining joint experiments](interaction-results.md) add25 driven combined/control/equal-limit/transition probes and15,003 states per repeat, with identical full-precision outputs and a completed bounded mode inventory. The [full original raw archive](raw-archive-publication.md) reconstructs both repetitions losslessly from shared identical trace bytes. Findings and candidate checks are consolidated in the [acceptance review packet](calibration-acceptance-review.md).

## Executed evidence

Both independent JVM repetitions produced byte-identical canonical gzip traces, query records and summaries. The recorder rejects non-finite output immediately; identical failure observations are not successful finite references. Runtime: OpenJDK 25.0.3 on the recorded Bazzite x86-64 host. This is one host/runtime, not all-target evidence or a performance benchmark.

| Canonical corpus, per repetition | Result |
| --- | ---: |
| Trace segments / distinct simulation IDs | 909 / 791 |
| Planned physics steps | 5,980,956 |
| Retained completed step states | 5,980,526 |
| Steps not captured after rejecting the negative-ratio case | 430 |
| Ordered listener events | 201,408,732 |
| Total raw JSONL records | 207,392,267 |
| Exact named upstream methods with original assertions | 40 passed |
| Additional scaled upstream representative worlds | 30 |
| P scene worlds | 496 |
| P joint probes | 232: 230 finite 600-step captures, one dynamic rejection, one API rejection |
| Geometry query/construction rows | 585, including six constructor rejections |
| Matched trajectory comparisons | 832; no missing nominal/timestep references |

The independently implemented trace audit checked gzip integrity, input headers, contiguous state indices, ordered within-step records, planned/executed counts and the rejected-case boundary. The second repetition's bytes match those audited files. Every designated long run that reached its horizon lasts 600 simulated seconds; stack and spring timestep variants use 18,000, 36,000 or 72,000 steps.

The original partition list also scheduled free motion redundantly. That extra 36,000-step capture is retained and byte-identical, but excluded from canonical totals above. Including that explicit duplicate, each actual invocation recorded 6,016,526 completed step states. The corrected runner schedules it once. The original hardlink aggregation also re-read its own destination and exited nonzero after the child captures finished; the repaired combiner recovered the indices without changing any physics data. Both development/packaging issues are documented in [commands](calibration-evidence/commands.txt), not hidden as simulation failures or silent omissions.

## What was made runnable

The isolated Java harness executes the approved scale/origin and timestep grids, exact named upstream methods with original assertions, deterministic joint mode probes, and geometry queries. It retains round-trippable doubles for state, ordered event payloads, source actions, public input settings and nested detector settings. Binding details live in [scene bindings](scene-bindings.md), [joint bindings](joint-bindings.md), [geometry bindings](geometry-bindings.md) and [upstream bindings](upstream-bindings.md). Commands and schemas are in [the harness README](../../calibration/README.md).

The captured input manifest contains stable construction-order IDs, fixture/shape and mass properties, joint endpoints/modes, effective settings, scale, fixed origin and timestep for every segment. Lazy stiffness initialization is visible; stiffness-mode probes serialize their resolved finite value before stepping. Original source schedules remain pinned, and passive instrumentation preserves actions and force/torque completion callbacks in order.

## Corrections retained after the full captures

Final source audit found two setup/recording omissions. The original full captures and their source/class archives remain unchanged; supplemental captures record the corrections, rather than rewriting provenance.

- The scaled fixed-distance representative had inadvertently widened an originally exact initial assertion to 1e−5. The corrected probe observes the original exact assertion and records **11 PASS / 4 FAIL**, catching the failures only to continue exploratory measurement. All four failures are scale 0.01 at nonzero offsets. The 40 nominal upstream methods retain their original passing assertions. No new tolerance is accepted.
- Both scaled upstream representatives now scale each fixture's restitution-velocity threshold by scale. Two corrected runs each contain 75 segments and 1,440 steps and match byte-for-byte. Compared with the original captures, only those input-header thresholds change; every subsequent physics/event record is identical. Joint-linked bodies do not collide in these probes.
- Standalone geometry probes now scale GJK distance/raycast epsilon by scale squared and EPA epsilon by scale, and serialize nested EPA settings. Their two corrected query streams match byte-for-byte. Removing only detector configuration fields reproduces every original ordered query result exactly. The circle fast paths do not exercise those iterative thresholds.

Supplemental inputs, outputs and hashes are under [corrections](calibration-evidence/corrections/). Original corpus totals and measurements below still refer to the original archived full captures. These corrections do not resolve activation gaps or approve references.

## Findings that prevent automatic acceptance

1. **Negative Angle ratio overflows.** With limits disabled and the approved ratio −1, both angular velocities become infinite after step 171. A recorder-free reproduction repeats this exactly; the velocity constraint residual doubles per solver iteration. Positive-ratio and warm-start controls distinguish the failure from instrumentation. No baseline code was changed. See [the diagnosis](negative-ratio-findings.md). The shortest-increment rotation sum is invalid from step 2 in this rejected case because the baseline's signed rotation clamp allows multiple negative revolutions; [the exclusion record](calibration-evidence/observable-exclusions.json) prevents treating that derived field as accumulated-rotation evidence.
2. **CCD callbacks do not imply containment.** All 30 rotating-pentagon ALL-mode cases at 60/120 Hz cross fully below the thin ground's bounding strip. At scale 0.01/origin zero, actual vertex extrema and a recorder-free probe confirm through-ground passage on step 2, far from either ground edge. Source inspection supports the existing-contact exclusion in the CCD pass as the mechanism; that branch was not experimentally patched or toggled. See [the CCD diagnosis](ccd-findings.md). Every ALL case nevertheless reported contacts/TOI events, demonstrating why counts alone are insufficient.
3. **The 30 Hz stack wake obligation fails in all 15 grid cells.** The top body is not asleep when the action at 300 seconds arrives. In the largest reported timestep position divergence, the stack has already escaped the finite ground: body b9's normalized x is about 57.69 m, outside the ground's ±10 m span, and it is falling under the maximum-translation clamp. No body was forcibly put to sleep to disguise the gap.
4. **An undamped spring is not numerically energy-conserving in these runs.** All 45 undamped long-spring cases lose effectively their entire initial modeled mechanical energy; final/initial energy ranges from about 7.83e−17 to 1.32e−12. All 45 damped cases also dissipate as expected. Captured effective stiffness matches the source-derived model exactly in all 90 runs. Adopting a tight conservation bound is therefore blocked; this observation does not authorize changing the baseline algorithm.
5. **Geometry boundaries change under exploratory transformations.** Six near-degenerate triangles become rejected constructions after translated-double rounding. The analysis records 86 discrete field differences from corresponding nominal queries/constructions across the grid, with no disagreement between detector overloads within a row. These are field differences, not 86 independent failing scenes. The proposed Distance lower limit −1 is separately rejected by the baseline API. None is silently labeled a supported input.

## Numerical measurements and candidate limits

[Complete machine-readable measurements](calibration-evidence/measurements.json) retain all component maxima, first exact differences, matched physical times, rest-flag differences, actions and spring-energy results. They separate 532 scale/origin comparisons from 300 timestep comparisons. Exact inequality here is a diagnostic, not an acceptance failure, and numerical averaging never hides a sampled discrepancy.

The largest normalized position difference is 25,505.17044752903 m for body b9's y coordinate at 445 seconds in the scale-100, offset (1e6,−1e6), 30-versus-60 Hz stack comparison. This is a different long trajectory after leaving the finite floor, not a roundoff allowance to adopt. Different timesteps keep separate reference candidates. Discrete contact alignment and exhaustive per-mode cap activation are not inferred from trajectory proximity.

The 600-second nominal free-motion fixture has maximum analytic x/y residuals of 5.425704330264125e−11 m and 2.7128521651320625e−11 m. Measured linear/angular momentum and kinetic-energy drift are zero in these repeated JVM runs. A **candidate baseline analytic-position check of absolute 1e−10 m per component** would contain every observed checkpoint of this exact fixture with modest margin. That is a review proposal for this baseline physical check only, not an approved shared target tolerance or a port-parity allowance. No zero cross-target allowance is inferred from the observed exact momentum values.

Concrete absolute/relative port-parity limits remain unset. Repeated JVM equality supplies reproducibility evidence, not evidence that every Kotlin target will be bit-identical. The large exploratory sensitivities, inactive modes and baseline failures must be reconciled before broader bounds or operating-domain promises are approved in [Define numerical and migration acceptance](https://github.com/rubixhacker/dyn4k/issues/7).

## Remaining acceptance gates

- Original isolated P rows that lacked drive remain preserved. The checkpoint and final interaction supplements provide active evidence for the identified combined, valid-range, equal-limit and transition gaps. The bounded audit found no further unexecuted joint-mode family; it does not establish exhaustive Cartesian or all-target coverage. Nonsaturating high caps remain nonbinding controls. The original [activation audit](negative-ratio-findings.md#activation-audit-distinguish-existing-u-evidence-from-new-p-decision) is historical; later supplements record the explicit new inputs and verified scope.
- The failed stack wake paths and CCD outcomes need review; they cannot be waived by widening numerical limits or counting callbacks.
- Initial reference review and acceptance-limit decisions remain human gates. No baseline-bug exception was approved. The selected unchanged Java application's headful execution and future shim replay remain separate obligations.
- Full raw trace publication is documented in the [archive report](raw-archive-publication.md). The original large corpus is distributed as experimental data assets, while supplemental complete raw repeats are in this branch. Archive integrity does not approve reference eligibility.

## Artifact locations and reproducibility

Canonical raw data, each 19,964,505,633 bytes of unique gzip traces:

- `/var/home/stewart/Workspace/dyn4k-calibration/calibration/results/final-a/combined`
- `/var/home/stewart/Workspace/dyn4k-calibration/calibration/results/final-b/combined`

State/action derivatives occupy 997,856,618 bytes and live under `calibration/results/derived-a/combined`. They are analysis conveniences; original events remain in the raw files. Interrupted development captures (`run-1`, `repeat-a`) and the interrupted serial analysis are excluded.

Published compact evidence: [input manifest](calibration-evidence/input-manifest.jsonl), [summary](calibration-evidence/summary.jsonl), [queries](calibration-evidence/queries.jsonl), [audit hashes/counts](calibration-evidence/audit-manifest.jsonl), [repeat comparison](calibration-evidence/repeat-comparison.txt), [environment](calibration-evidence/environment.txt), [geometry measurements](calibration-evidence/geometry-measurements.json), [commands](calibration-evidence/commands.txt), captured source/class archives and recorder-free probe outputs. The audit manifest includes partition totals and the explicit redundant free-motion record; canonical totals deduplicate only byte-identical files.

Recompilation after whitespace normalization preserved every archived class checksum at that verification checkpoint; selected upstream assertions passed again. Later analysis partition support and diagnostic helpers do not alter the recorder. The subsequent scaled-probe and geometry corrections above intentionally differ from the original archived source and are separately reproduced. Captured source/class archives retain the exact original executed versions for independent reconstruction.
