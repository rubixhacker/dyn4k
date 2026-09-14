# Joint P matrix bindings

Pinned upstream source verified locally at `058bf6d982a0fb89b54050f929f6ea9dae53b714` (dyn4j 6.0.0). Runner: `calibration/src/JointCases.java`. These rows expand the approved field grids into executable probes; execution alone does not establish activated-mode coverage or freeze references.

## Initial-state binding

Every P row reconstructs the source method's complete state immediately before its first physics step. It does not execute subsequent U mutations: the source-faithful U harness retains those separately. Fixtures retain upstream defaults (including restitution and mass defaults); P's unrelated fresh-fixture defaults do not replace these U-derived setups.

| Type | Initial U method | Dynamic rows |
|---|---|---:|
| Angle | `simpleLinkage` | 14 |
| Distance | `fixedDistance` | 31 |
| Friction | `simulationWithLargeForceTorqueMaximums` | 7 |
| Motor | `simple` | 12 |
| Pin | `fixedLinearVelocity`; correction factor and maximum correction force use `noSpringDamper` | 27 |
| Prismatic | `noLimitsNoMotor` | 44 |
| Pulley | `simpleLinkage` | 7 |
| Revolute | `noLimitsNoMotor` | 19 |
| Weld | `standard` | 26 |
| Wheel | `noLimitsNoMotor` | 44 |

Each dynamic row runs 600 steps at 1/60 s with scale 1 and origin (0,0). Boolean names are exact setter suffixes; every listed supported mode boolean receives isolated false/true rows and a false→true→false row with mutations immediately before steps 201/401. `CollisionAllowed` is not a manifest mode and is unchanged. Scalar IDs contain their exact decimal inputs; spring-stiffness IDs include exact hexadecimal doubles. Limits-range changes the pair only; limits-equal sets both to zero. These field-only probes do not silently enable a related switch. Angle additionally has ratio rows with limits explicitly disabled. Interaction rows enable precisely the specified spring/motor/limit switches, preserving other values. Moving targets add the specified displacement before step 201, retaining the initial caps.

Spring-field rows (including spring booleans, damper, spring caps, and stiffness) instead select the first feature-compatible U setup: Distance `upperLimitWithSpring`, Prismatic `springOnly`, Weld `softConstraint`, Wheel `springDamperWithLimits`, Pin `fixedLinearVelocity`. Motor-field rows use Prismatic/Revolute `motorWithAndWithoutLimits` and Wheel `motorOnly`. Each selection preserves its exact pre-first-step settings, anchors, gravity, caps and enabled modes. This makes “compatible” dynamic compatibility instead of mere setter availability. Fields remain isolated relative to that selected setup. Other rows retain the table's initial setup.

Spring stiffness is resolved by enabling the spring and assigning 2 or 8 Hz in a separate disposable identical seed, letting baseline initialize for one step, then reading `getSpringStiffness`. The captured stiffness-mode row starts again from its pristine seed and calls the stiffness setter with that finite positive value. No unrecorded warmup advances the captured world.

| Type | 2 Hz stiffness (exact double) | 8 Hz stiffness (exact double) |
|---|---|---|
| Distance | `0x1.f019b59389d7bp6` | `0x1.f019b59389d7bp10` |
| Pin | `0x1.f019b59389d7bp7` | `0x1.f019b59389d7bp11` |
| Prismatic | `0x1.f019b59389d7bp6` | `0x1.f019b59389d7bp10` |
| Weld | `0x1.07307fd73e4e4p3` | `0x1.07307fd73e4e4p7` |
| Wheel | `0x1.f019b59389d7bp6` | `0x1.f019b59389d7bp10` |

## Executed binding check

Compiled against `/tmp/dyn4k-baseline-research/dyn4j-6.0.0.jar` and exercised all rows through a temporary Java Capture driver that calls the real `World.step(1,dt)` and scheduled actions. Result: 232 attempted, 231 completed dynamic rows (138,600 physics steps), one API rejection. This local check is a runnable binding check, not the final integrated numerical capture or a mode-activation assertion.

The stepping-only driver did not validate finiteness. Integrated Capture then discovered `P-J-Angle-ratio-limits-off--1.0` produces a non-finite output at step 171 (`NaN`), aborting the initial all-row serialization attempt. Therefore the stepping count is not 231 finite or accepted reference runs. The accepted negative ratio setter does not imply stable dynamics. Keep this row as a baseline failure observation. Separately, five integrated 2 Hz spring rows captured all 600 steps each, and their per-step payloads include baseline-computed `getSpringStiffness` (initially zero before lazy initialization); Prismatic reports `124.02510672119926` after initialization. Temporary integrated artifacts are under `/tmp/joint-integrated/`.

Follow-up integrated runs filtered by the other nine joint types completed all 217 rows, with no non-finite serialization errors. Together with the 13 Angle rows recorded before the failing row, this provides 230 complete finite 600-step captures, one non-finite dynamic case and one API-rejected case. Counts come from the recorder's `summary.jsonl` files, not the runner's scheduling counter (which includes rows skipped by a recorder filter). These remain exploratory baseline observations, not frozen references or blanket activation proof.

The Distance `limits-range` row calls `setLimits(-1,1)` and baseline rejects negative lower distance. Its exception is preserved with `Capture.rejected`; it contributes zero dynamic coverage. An accepted replacement requires a decision because silently changing the approved signed grid to nonnegative lengths changes inputs.

## Remaining activation gates

Feature-compatible source selection activates spring and motor parameter probes without adding arbitrary stimulus. The following separate gaps remain:

- Prismatic/Wheel generic limit rows and combined interaction rows retain gravity perpendicular to their permitted translation axis and no initial axial velocity/displacement. Those rows do not ensure lower/upper hits or spring force. U's later velocity mutation is a possible source-grounded stimulus, but copying it into P changes the P action schedule. Spring parameter rows use the active setups listed above.
- Revolute/Weld generic limit and interaction seeds have no angular velocity or off-centre load. Their zero motor-speed defaults and zero angular spring error cannot prove opposite limit hits or interaction activation. Spring/motor parameter rows use the active setups listed above.
- Motor's initial U caps are both zero. Independent cap rows can activate one channel, but correction-factor and moving-target rows retain zero caps and cannot prove target-following branches. Adopting the later U 100 N / 10 N·m cap change would be an extra P mutation.
- Pulley's equal masses and initial ratio 1 produce a taut balanced system. Toggling slack alone does not prove a taut→slack→taut trajectory.
- Scalar caps retain the source setup's cap-enable state. In particular spring cap scalar values alone do not turn a disabled cap on; false/true/toggle cap-enable rows are separate observations.
- Nonzero joint reaction is not proof that each internal limit, spring or cap solved. Per-mode force/torque, speed/displacement and bounds must be evaluated together; zero cap with zero drive is not saturation evidence.

No additional arbitrary impulses, target forces or hidden enabling switches were added to manufacture coverage. These gaps block claiming the P mode-coverage gate complete and must remain visible at approval.

## Expanded row IDs

The following list was emitted by the executable binding check. `REJECTED` is an API observation, all other lines are 600-step cases.

```text
P-J-Angle-initial
P-J-Angle-LimitsEnabled-false
P-J-Angle-LimitsEnabled-true
P-J-Angle-LimitsEnabled-toggle
P-J-Angle-Ratio-0.5
P-J-Angle-Ratio-1.0
P-J-Angle-Ratio-2.0
P-J-Angle-Ratio--1.0
P-J-Angle-limits-range
P-J-Angle-limits-equal
P-J-Angle-ratio-limits-off-0.5
P-J-Angle-ratio-limits-off-1.0
P-J-Angle-ratio-limits-off-2.0
P-J-Angle-ratio-limits-off--1.0
P-J-Distance-initial
P-J-Distance-LimitsEnabled-false
P-J-Distance-LimitsEnabled-true
P-J-Distance-LimitsEnabled-toggle
P-J-Distance-LowerLimitEnabled-false
P-J-Distance-LowerLimitEnabled-true
P-J-Distance-LowerLimitEnabled-toggle
P-J-Distance-UpperLimitEnabled-false
P-J-Distance-UpperLimitEnabled-true
P-J-Distance-UpperLimitEnabled-toggle
P-J-Distance-SpringEnabled-false
P-J-Distance-SpringEnabled-true
P-J-Distance-SpringEnabled-toggle
P-J-Distance-SpringDamperEnabled-false
P-J-Distance-SpringDamperEnabled-true
P-J-Distance-SpringDamperEnabled-toggle
P-J-Distance-MaximumSpringForceEnabled-false
P-J-Distance-MaximumSpringForceEnabled-true
P-J-Distance-MaximumSpringForceEnabled-toggle
P-J-Distance-SpringDampingRatio-0.0
P-J-Distance-SpringDampingRatio-0.2
P-J-Distance-SpringDampingRatio-1.0
P-J-Distance-SpringFrequency-2.0
P-J-Distance-SpringFrequency-8.0
P-J-Distance-MaximumSpringForce-0.0
P-J-Distance-MaximumSpringForce-10.0
P-J-Distance-MaximumSpringForce-1000.0
REJECTED P-J-Distance-limits-range org.dyn4j.exception.ValueOutOfRangeException: -1.000000 was supplied for lowerLimit: lowerLimit must be greater than or equal to 0.000000
P-J-Distance-limits-equal
P-J-Distance-stiffness-from-2.0Hz-0x1.f019b59389d7bp6
P-J-Distance-stiffness-from-8.0Hz-0x1.f019b59389d7bp10
P-J-Distance-interaction
P-J-Friction-initial
P-J-Friction-MaximumForce-0.0
P-J-Friction-MaximumForce-10.0
P-J-Friction-MaximumForce-1000.0
P-J-Friction-MaximumTorque-0.0
P-J-Friction-MaximumTorque-0.25
P-J-Friction-MaximumTorque-10.0
P-J-Motor-initial
P-J-Motor-CorrectionFactor-0.0
P-J-Motor-CorrectionFactor-0.3
P-J-Motor-CorrectionFactor-1.0
P-J-Motor-MaximumForce-0.0
P-J-Motor-MaximumForce-10.0
P-J-Motor-MaximumForce-1000.0
P-J-Motor-MaximumTorque-0.0
P-J-Motor-MaximumTorque-0.25
P-J-Motor-MaximumTorque-10.0
P-J-Motor-moving-linear-target
P-J-Motor-moving-angular-target
P-J-Pin-initial
P-J-Pin-SpringEnabled-false
P-J-Pin-SpringEnabled-true
P-J-Pin-SpringEnabled-toggle
P-J-Pin-SpringDamperEnabled-false
P-J-Pin-SpringDamperEnabled-true
P-J-Pin-SpringDamperEnabled-toggle
P-J-Pin-MaximumSpringForceEnabled-false
P-J-Pin-MaximumSpringForceEnabled-true
P-J-Pin-MaximumSpringForceEnabled-toggle
P-J-Pin-SpringDampingRatio-0.0
P-J-Pin-SpringDampingRatio-0.2
P-J-Pin-SpringDampingRatio-1.0
P-J-Pin-SpringFrequency-2.0
P-J-Pin-SpringFrequency-8.0
P-J-Pin-CorrectionFactor-0.0
P-J-Pin-CorrectionFactor-0.3
P-J-Pin-CorrectionFactor-1.0
P-J-Pin-MaximumSpringForce-0.0
P-J-Pin-MaximumSpringForce-10.0
P-J-Pin-MaximumSpringForce-1000.0
P-J-Pin-MaximumCorrectionForce-0.0
P-J-Pin-MaximumCorrectionForce-10.0
P-J-Pin-MaximumCorrectionForce-1000.0
P-J-Pin-stiffness-from-2.0Hz-0x1.f019b59389d7bp7
P-J-Pin-stiffness-from-8.0Hz-0x1.f019b59389d7bp11
P-J-Pin-moving-linear-target
P-J-Prismatic-initial
P-J-Prismatic-LimitsEnabled-false
P-J-Prismatic-LimitsEnabled-true
P-J-Prismatic-LimitsEnabled-toggle
P-J-Prismatic-LowerLimitEnabled-false
P-J-Prismatic-LowerLimitEnabled-true
P-J-Prismatic-LowerLimitEnabled-toggle
P-J-Prismatic-UpperLimitEnabled-false
P-J-Prismatic-UpperLimitEnabled-true
P-J-Prismatic-UpperLimitEnabled-toggle
P-J-Prismatic-MotorEnabled-false
P-J-Prismatic-MotorEnabled-true
P-J-Prismatic-MotorEnabled-toggle
P-J-Prismatic-MaximumMotorForceEnabled-false
P-J-Prismatic-MaximumMotorForceEnabled-true
P-J-Prismatic-MaximumMotorForceEnabled-toggle
P-J-Prismatic-SpringEnabled-false
P-J-Prismatic-SpringEnabled-true
P-J-Prismatic-SpringEnabled-toggle
P-J-Prismatic-SpringDamperEnabled-false
P-J-Prismatic-SpringDamperEnabled-true
P-J-Prismatic-SpringDamperEnabled-toggle
P-J-Prismatic-MaximumSpringForceEnabled-false
P-J-Prismatic-MaximumSpringForceEnabled-true
P-J-Prismatic-MaximumSpringForceEnabled-toggle
P-J-Prismatic-SpringDampingRatio-0.0
P-J-Prismatic-SpringDampingRatio-0.2
P-J-Prismatic-SpringDampingRatio-1.0
P-J-Prismatic-SpringFrequency-2.0
P-J-Prismatic-SpringFrequency-8.0
P-J-Prismatic-MaximumSpringForce-0.0
P-J-Prismatic-MaximumSpringForce-10.0
P-J-Prismatic-MaximumSpringForce-1000.0
P-J-Prismatic-MaximumMotorForce-0.0
P-J-Prismatic-MaximumMotorForce-10.0
P-J-Prismatic-MaximumMotorForce-1000.0
P-J-Prismatic-MotorSpeed--1.0
P-J-Prismatic-MotorSpeed-0.0
P-J-Prismatic-MotorSpeed-1.0
P-J-Prismatic-limits-range
P-J-Prismatic-limits-equal
P-J-Prismatic-stiffness-from-2.0Hz-0x1.f019b59389d7bp6
P-J-Prismatic-stiffness-from-8.0Hz-0x1.f019b59389d7bp10
P-J-Prismatic-interaction
P-J-Pulley-initial
P-J-Pulley-SlackEnabled-false
P-J-Pulley-SlackEnabled-true
P-J-Pulley-SlackEnabled-toggle
P-J-Pulley-Ratio-0.5
P-J-Pulley-Ratio-1.0
P-J-Pulley-Ratio-2.0
P-J-Revolute-initial
P-J-Revolute-LimitsEnabled-false
P-J-Revolute-LimitsEnabled-true
P-J-Revolute-LimitsEnabled-toggle
P-J-Revolute-MotorEnabled-false
P-J-Revolute-MotorEnabled-true
P-J-Revolute-MotorEnabled-toggle
P-J-Revolute-MaximumMotorTorqueEnabled-false
P-J-Revolute-MaximumMotorTorqueEnabled-true
P-J-Revolute-MaximumMotorTorqueEnabled-toggle
P-J-Revolute-MaximumMotorTorque-0.0
P-J-Revolute-MaximumMotorTorque-0.25
P-J-Revolute-MaximumMotorTorque-10.0
P-J-Revolute-MotorSpeed--1.5707963267948966
P-J-Revolute-MotorSpeed-0.0
P-J-Revolute-MotorSpeed-1.5707963267948966
P-J-Revolute-limits-range
P-J-Revolute-limits-equal
P-J-Revolute-interaction
P-J-Weld-initial
P-J-Weld-LimitsEnabled-false
P-J-Weld-LimitsEnabled-true
P-J-Weld-LimitsEnabled-toggle
P-J-Weld-SpringEnabled-false
P-J-Weld-SpringEnabled-true
P-J-Weld-SpringEnabled-toggle
P-J-Weld-SpringDamperEnabled-false
P-J-Weld-SpringDamperEnabled-true
P-J-Weld-SpringDamperEnabled-toggle
P-J-Weld-MaximumSpringTorqueEnabled-false
P-J-Weld-MaximumSpringTorqueEnabled-true
P-J-Weld-MaximumSpringTorqueEnabled-toggle
P-J-Weld-SpringDampingRatio-0.0
P-J-Weld-SpringDampingRatio-0.2
P-J-Weld-SpringDampingRatio-1.0
P-J-Weld-SpringFrequency-2.0
P-J-Weld-SpringFrequency-8.0
P-J-Weld-MaximumSpringTorque-0.0
P-J-Weld-MaximumSpringTorque-0.25
P-J-Weld-MaximumSpringTorque-10.0
P-J-Weld-limits-range
P-J-Weld-limits-equal
P-J-Weld-stiffness-from-2.0Hz-0x1.07307fd73e4e4p3
P-J-Weld-stiffness-from-8.0Hz-0x1.07307fd73e4e4p7
P-J-Weld-interaction
P-J-Wheel-initial
P-J-Wheel-LimitsEnabled-false
P-J-Wheel-LimitsEnabled-true
P-J-Wheel-LimitsEnabled-toggle
P-J-Wheel-LowerLimitEnabled-false
P-J-Wheel-LowerLimitEnabled-true
P-J-Wheel-LowerLimitEnabled-toggle
P-J-Wheel-UpperLimitEnabled-false
P-J-Wheel-UpperLimitEnabled-true
P-J-Wheel-UpperLimitEnabled-toggle
P-J-Wheel-MotorEnabled-false
P-J-Wheel-MotorEnabled-true
P-J-Wheel-MotorEnabled-toggle
P-J-Wheel-MaximumMotorTorqueEnabled-false
P-J-Wheel-MaximumMotorTorqueEnabled-true
P-J-Wheel-MaximumMotorTorqueEnabled-toggle
P-J-Wheel-SpringEnabled-false
P-J-Wheel-SpringEnabled-true
P-J-Wheel-SpringEnabled-toggle
P-J-Wheel-SpringDamperEnabled-false
P-J-Wheel-SpringDamperEnabled-true
P-J-Wheel-SpringDamperEnabled-toggle
P-J-Wheel-MaximumSpringForceEnabled-false
P-J-Wheel-MaximumSpringForceEnabled-true
P-J-Wheel-MaximumSpringForceEnabled-toggle
P-J-Wheel-SpringDampingRatio-0.0
P-J-Wheel-SpringDampingRatio-0.2
P-J-Wheel-SpringDampingRatio-1.0
P-J-Wheel-SpringFrequency-2.0
P-J-Wheel-SpringFrequency-8.0
P-J-Wheel-MaximumSpringForce-0.0
P-J-Wheel-MaximumSpringForce-10.0
P-J-Wheel-MaximumSpringForce-1000.0
P-J-Wheel-MaximumMotorTorque-0.0
P-J-Wheel-MaximumMotorTorque-0.25
P-J-Wheel-MaximumMotorTorque-10.0
P-J-Wheel-MotorSpeed--1.5707963267948966
P-J-Wheel-MotorSpeed-0.0
P-J-Wheel-MotorSpeed-1.5707963267948966
P-J-Wheel-limits-range
P-J-Wheel-limits-equal
P-J-Wheel-stiffness-from-2.0Hz-0x1.f019b59389d7bp6
P-J-Wheel-stiffness-from-8.0Hz-0x1.f019b59389d7bp10
P-J-Wheel-interaction

```

## Approved checkpoint supplement

The live approval recorded in [the calibration decision](https://github.com/rubixhacker/dyn4k/issues/15#issuecomment-5658147012) permits exact later upstream checkpoints to activate previously idle probes. The original `P-J-*` rows above are retained unchanged. Supplemental rows use `P-JCP-*`, so their new bindings cannot silently replace old reference inputs.

Each checkpoint is reconstructed from the exact source setup and preceding steps/actions, retaining the same World, bodies, joint, warm-start impulses and rest state. Every preceding step is recorded under that row's unique `-preparation` ID; successive preparation segments keep their cumulative segment index. Checkpoint actions between segments are reflected in the next input snapshot and the full ordered `checkpoint-provenance` record. The main input header contains the resulting physical state; the first record also carries `checkpoint-input-binding` with source method, ordered actions and variant. Continuation step numbers 201/401 are relative to the new 600-step continuation, not the upstream absolute step count.

| Supplemental checkpoint | Exact source state before continuation | Continuation variants |
|---|---|---|
| Motor `caps` | `simple`: preserve 25 steps with caps0/0, then set force100 and torque10 in source order | source control; correction factors0/.3/1; linear/angular target increment before201 |
| Pulley `taut` | `withAndWithoutSlack`: exact three-body setup; step1; second moving body's velocity(0,10) | source control |
| Pulley `slack` | Continue the preceding setup step2; velocity(0,10), translation(0,.1), slack=true | source control; slack false/true/toggle |
| Distance `cap` | `springWithMaxForce` complete initial setup: rest3, frequency8, damping.2, enabled cap200 | source control; force caps0/10/1000; cap-enable false/true/toggle |
| Weld `cap` | `softConstraint`: left offset anchor, preserve21 steps, cap5 then enabled, force(0,-10) at(.5,2) | source control; torque caps0/.25/10; cap-enable false/true/toggle |
| Wheel `cap` | `springDamperWithLimits`: vertical axis, preserve20 steps; limits(1,5), step2; limits(-1,-.5), step2; limits(-1.5,1), cap enabled then200 | source control; force caps0/10/1000; cap-enable false/true/toggle |
| Prismatic `lower` / `upper` | `limits`: exact zero-gravity initial setup, limits(-1,5), velocity(-16,0), step1, limits(6,7); upper further preserves step1 then velocity(16,0), limits(1,3) | source controls; joint/lower/upper limit-enable false/true/toggle |
| Revolute `lower` / `upper` | `limits`: zero gravity, angular tolerance0, limits±30deg, velocity10deg/s, step1, limits(10,30)deg; upper further preserves step1 then velocity-10deg/s, limits(-30,5)deg | source controls; limit-enable false/true/toggle |
| Weld `lower` / `upper` | `softConstraintWithLimitsLower/Upper`: exact opposite offset anchors, spring8/.3, limits±.2pi, cap1 enabled; only upper includes source force(0,-10) at(-.5,2) | source controls; limit-enable false/true/toggle |
| Wheel `lower` / `upper` | `springDamperWithLimits`: preserve20 steps, limits(1,5); upper further preserves step2 then limits(-1,-.5) | source controls; joint/lower/upper limit-enable false/true/toggle; approved range(-1,1) and equal(0,0) |

Focused integration run `/tmp/joint-checkpoints/run3` produced 213 complete segments: 92 independent 600-step continuations and 121 preparation segments, totaling 56,224 recorded physics steps with no rejected/non-finite status. Independent comparison of the preceding run caught a Distance setup mismatch: reusing `fixedDistance` had retained its explicit 10 position iterations, while `springWithMaxForce` uses the pinned default 2. The supplemental binding now explicitly restores 2; the original rows remain unchanged. Fourteen unchanged checkpoint controls permit exact comparison against the corresponding original U segment input and initial state trajectory. Finite capture, source fidelity and actual mode activation are separate checks.

The supplement supplies raw per-step joint getter channels for activation analysis: lower/upper gap together with configured enables and translation/angle; spring force/torque against positive enabled cap; Motor target error and state change; Pulley current length against target plus slack enable. Revolute's source limit correction explicitly has zero reaction torque, so a nonzero-reaction requirement would incorrectly reject its genuine position correction. A toggle at201/401 may occur after an original impulse has decayed; its actual activity must be reported, not assumed from the configuration change.

No new Prismatic/Wheel spring+motor+limits combination, arbitrary stimulus, negative-ratio repair, or replacement for the rejected signed Distance range is introduced by this approval. Those remaining questions are unchanged.

### Supplemental continuation IDs

```text
P-JCP-Motor-caps-source
P-JCP-Motor-caps-CorrectionFactor-0.0
P-JCP-Motor-caps-CorrectionFactor-0.3
P-JCP-Motor-caps-CorrectionFactor-1.0
P-JCP-Motor-caps-moving-linear
P-JCP-Motor-caps-moving-angular
P-JCP-Distance-cap-source
P-JCP-Distance-cap-MaximumSpringForce-0.0
P-JCP-Distance-cap-MaximumSpringForce-10.0
P-JCP-Distance-cap-MaximumSpringForce-1000.0
P-JCP-Distance-cap-MaximumSpringForceEnabled-false
P-JCP-Distance-cap-MaximumSpringForceEnabled-true
P-JCP-Distance-cap-MaximumSpringForceEnabled-toggle
P-JCP-Weld-cap-source
P-JCP-Weld-cap-MaximumSpringTorque-0.0
P-JCP-Weld-cap-MaximumSpringTorque-0.25
P-JCP-Weld-cap-MaximumSpringTorque-10.0
P-JCP-Weld-cap-MaximumSpringTorqueEnabled-false
P-JCP-Weld-cap-MaximumSpringTorqueEnabled-true
P-JCP-Weld-cap-MaximumSpringTorqueEnabled-toggle
P-JCP-Wheel-cap-source
P-JCP-Wheel-cap-MaximumSpringForce-0.0
P-JCP-Wheel-cap-MaximumSpringForce-10.0
P-JCP-Wheel-cap-MaximumSpringForce-1000.0
P-JCP-Wheel-cap-MaximumSpringForceEnabled-false
P-JCP-Wheel-cap-MaximumSpringForceEnabled-true
P-JCP-Wheel-cap-MaximumSpringForceEnabled-toggle
P-JCP-Pulley-taut-source
P-JCP-Pulley-slack-source
P-JCP-Pulley-slack-SlackEnabled-false
P-JCP-Pulley-slack-SlackEnabled-true
P-JCP-Pulley-slack-SlackEnabled-toggle
P-JCP-Prismatic-lower-source
P-JCP-Prismatic-lower-LimitsEnabled-false
P-JCP-Prismatic-lower-LimitsEnabled-true
P-JCP-Prismatic-lower-LimitsEnabled-toggle
P-JCP-Prismatic-lower-LowerLimitEnabled-false
P-JCP-Prismatic-lower-LowerLimitEnabled-true
P-JCP-Prismatic-lower-LowerLimitEnabled-toggle
P-JCP-Prismatic-lower-UpperLimitEnabled-false
P-JCP-Prismatic-lower-UpperLimitEnabled-true
P-JCP-Prismatic-lower-UpperLimitEnabled-toggle
P-JCP-Prismatic-upper-source
P-JCP-Prismatic-upper-LimitsEnabled-false
P-JCP-Prismatic-upper-LimitsEnabled-true
P-JCP-Prismatic-upper-LimitsEnabled-toggle
P-JCP-Prismatic-upper-LowerLimitEnabled-false
P-JCP-Prismatic-upper-LowerLimitEnabled-true
P-JCP-Prismatic-upper-LowerLimitEnabled-toggle
P-JCP-Prismatic-upper-UpperLimitEnabled-false
P-JCP-Prismatic-upper-UpperLimitEnabled-true
P-JCP-Prismatic-upper-UpperLimitEnabled-toggle
P-JCP-Revolute-lower-source
P-JCP-Revolute-lower-LimitsEnabled-false
P-JCP-Revolute-lower-LimitsEnabled-true
P-JCP-Revolute-lower-LimitsEnabled-toggle
P-JCP-Revolute-upper-source
P-JCP-Revolute-upper-LimitsEnabled-false
P-JCP-Revolute-upper-LimitsEnabled-true
P-JCP-Revolute-upper-LimitsEnabled-toggle
P-JCP-Weld-lower-source
P-JCP-Weld-lower-LimitsEnabled-false
P-JCP-Weld-lower-LimitsEnabled-true
P-JCP-Weld-lower-LimitsEnabled-toggle
P-JCP-Weld-upper-source
P-JCP-Weld-upper-LimitsEnabled-false
P-JCP-Weld-upper-LimitsEnabled-true
P-JCP-Weld-upper-LimitsEnabled-toggle
P-JCP-Wheel-lower-source
P-JCP-Wheel-lower-LimitsEnabled-false
P-JCP-Wheel-lower-LimitsEnabled-true
P-JCP-Wheel-lower-LimitsEnabled-toggle
P-JCP-Wheel-lower-LowerLimitEnabled-false
P-JCP-Wheel-lower-LowerLimitEnabled-true
P-JCP-Wheel-lower-LowerLimitEnabled-toggle
P-JCP-Wheel-lower-UpperLimitEnabled-false
P-JCP-Wheel-lower-UpperLimitEnabled-true
P-JCP-Wheel-lower-UpperLimitEnabled-toggle
P-JCP-Wheel-lower-limits-range
P-JCP-Wheel-lower-limits-equal
P-JCP-Wheel-upper-source
P-JCP-Wheel-upper-LimitsEnabled-false
P-JCP-Wheel-upper-LimitsEnabled-true
P-JCP-Wheel-upper-LimitsEnabled-toggle
P-JCP-Wheel-upper-LowerLimitEnabled-false
P-JCP-Wheel-upper-LowerLimitEnabled-true
P-JCP-Wheel-upper-LowerLimitEnabled-toggle
P-JCP-Wheel-upper-UpperLimitEnabled-false
P-JCP-Wheel-upper-UpperLimitEnabled-true
P-JCP-Wheel-upper-UpperLimitEnabled-toggle
P-JCP-Wheel-upper-limits-range
P-JCP-Wheel-upper-limits-equal

```
