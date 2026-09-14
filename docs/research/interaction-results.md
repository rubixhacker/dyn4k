# Remaining joint experiment execution

The user authorized completing the missing fixture definitions, archive publication and review preparation. [Declared inputs](interaction-bindings.md) identify every new input and control; these are additions to the original corpus, not replacements or accepted reference data.

## Verified result

Two integrated fresh JVM repetitions each completed **25 independent 600-step continuations plus three recorded Pulley preparation steps: 27 segments and 15,003 states**. Every gzip trace, query stream and summary matches byte-for-byte. The structural audit counted46,984 ordered listener events and62,094 raw records per repeat, with no missing states or nonfinite rejection. Captured Java source hashes match the reviewed implementation. Runtime remains OpenJDK25.0.3 on one host.

Both complete supplemental raw repeats and the input manifest, counts/hashes, full measurements and phase-specific diagnostics are [published here](calibration-evidence/interactions/). Temporary development captures are excluded from these final totals.

## Active behavior, not just configured switches

The [selected exact per-step samples](calibration-evidence/interactions/simultaneous-bound-samples.jsonl) show all three components together:

| Case/bound | Step | Position | Spring | Motor | Derived axial limit contribution |
|---|---:|---:|---:|---:|---:|
| Prismatic upper |61|1m|10N|225.619449N|−282.743339N|
| Prismatic lower |324|−1m|10N|−245.619449N|282.743339N|
| Wheel lower |202|1m|−10N|−0.25N·m|17.696902N|
| Wheel upper |416|−0.5m|10N|0.25N·m|−10.918230N|

The axial contribution is derived from the pinned public reaction formula: project reaction force onto the fixed axis, subtract spring force, and for Prismatic also subtract linear motor force. Wheel's motor is angular. See [Prismatic reaction formula](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/dynamics/joint/PrismaticJoint.java#L930-L937) and [Wheel reaction formula](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/dynamics/joint/WheelJoint.java#L862-L869). Raw values are full precision; displayed values are rounded. No tolerance is needed to identify these exact bound coordinates. Separate spring-off, motor-off and limits-off controls retain all other schedules.

The source-derived valid Distance[1,5]m range has driven upper and lower probes; the lower reaches1m at step3 with spring force195.4077N while its spring-off control stays at2m. The original invalid[-1,1] API observation remains retained.

All **seven newly driven cap transitions** attain their positive cap during steps201–400: Distance200N, Prismatic spring10N/motor10N, Revolute motor0.25N·m, Weld spring5N·m, Wheel spring200N/motor0.25N·m. [Enabled-phase measurements](calibration-evidence/interactions/enabled-phase.json) report maximum absolute cap ratio1 for each. Original Distance/Pin probes already supplied their active cap-transition evidence; nonbinding high values are valid controls, not automatically additional obligations.

Enabled equal-limit probes cover Distance, Prismatic, Revolute and Weld; Wheel's checkpoint supplement already covers equal limits. Distance corrects initial2m to0m at step1, Prismatic holds0m under10N motor drive, and Revolute holds0rad under0.25N·m motor drive. Weld's equal-limit probe is active but has measured angular residuals approximately[−0.00144567,+0.000612573]rad; this is not a perfect-lock or accepted-tolerance claim.

The new Weld spring-enable transition has nonzero enabled-phase torque(maximum3.04550236N·m), with zero spring torque in disabled phases. The new Pulley transition reaches real slack after enable201: weighted length error minimum−0.7061984767m. It also stretches above target by0.1208278905m during the enabled phase. After disabling at401 its range is approximately[−0.0003322561,0]m. Both slack and stretch are retained.

## Coverage boundary and review

The bounded source/mode audit found no further unexecuted joint-mode family in the declared experiment after these additions. This covers the identified combined, valid-range, equal-limit, cap-transition, spring-transition and slack-transition gaps; it is not exhaustive Cartesian coverage or proof of all public members/targets. Original inactive rows are not relabeled as active.

Baseline physical outcomes still require acceptance review: negative Angle overflow, CCD containment failure, original30Hz stack wake failure, geometry representability, and the new Weld/Pulley residuals. Intended spring-energy dissipation is separately explained in the [acceptance review packet](calibration-acceptance-review.md). Execution and publication can complete while reference eligibility and numerical policy remain unresolved.

Reproduce with `./calibration/run NEW_OUTPUT P-JINT-`, then a second fresh `Main NEW_OUTPUT_B P-JINT-` JVM using the same compiled classes. Audit with `Audit --complete RAW NEW_DERIVED 15003`. Per-trace measurements use `checkpoint-measurements.jq`; `interaction-coverage.jq` reports exact bound samples separately from observations within the baseline's configured solver tolerance. Those diagnostic classifications do not approve acceptance bounds.
