# Weld and Pulley physical-check evidence

For [Establish physical-check evidence for Weld and Pulley residuals](https://github.com/rubixhacker/dyn4k/issues/20), supporting [Define numerical and migration acceptance](https://github.com/rubixhacker/dyn4k/issues/7). This report preserves the [unresolved physical-bound checkpoint](https://github.com/rubixhacker/dyn4k/issues/7#issuecomment-5662432770). **Physical classification, reference selection and numerical limits remain PENDING.**

## Finding and proposed decisions

Both exact fixtures have finite, complete and reproducible recorded traces that can be proposed as baseline parity/behavior references while reporting their physical residuals. They do not demonstrate ideal angular locking or per-step rope inextensibility. Pinned solver stopping criteria do not establish unconditional bounds on the final state, and measured maxima must not become tolerances.

Recommended human choices:

1. Approve these exact trace identities as parity/behavior references with explicit physical-residual diagnostics, excluding them as proof of ideal locking/inextensibility. Preserve all samples and phases. This resolves data eligibility only; baseline-to-port numerical limits and any required physical acceptance budgets remain separate unresolved gates.
2. For physical acceptance, choose whether to keep the quantified residuals diagnostic pending an independently chosen application/error budget, or explicitly adopt a new fixture-specific engineering check based on the baseline's configured numerical resolution. For example, per-step Weld angle/anchor errors within configured angular/linear tolerances and Pulley positive extension within configured linear tolerance are source-informed **proposals**, not guarantees or approved bounds. The existing Weld trace satisfies that candidate check; Pulley fails it at 39 enabled-phase samples. Those failures must remain visible if this stricter check is selected. No widening to the observed maxima is proposed.

The first choice is recommended now; no new hard physical bound is recommended as already justified acceptance policy. Choosing a settings-based budget would be an explicit engineering decision, not a consequence of archive integrity or solver implementation. The finite observations establish baseline limitations in these runs; their exact internal cause is not fully instrumented, and this report does not declare a new proven upstream defect or authorize a correction.

## Exact evidence and reproduction

All experiment data comes from [revision 0995a6bac84de882b0d04b6c3ea18162ca3b4a7c](https://github.com/rubixhacker/dyn4k/tree/0995a6bac84de882b0d04b6c3ea18162ca3b4a7c). The [compact manifest](weld-pulley-physical-checks-manifest.json), SHA-256 `2e424064ca14a3d27630f7197d3dfc929afda024d27741cb2427194c49784509`, binds source, archives, exact input headers, state/event streams, actions, settings and phase measurements. All approval fields remain pending.

Freshly hashed [repeat-A archive](https://github.com/rubixhacker/dyn4k/blob/0995a6bac84de882b0d04b6c3ea18162ca3b4a7c/docs/research/calibration-evidence/interactions/raw-repeat-a.tar.gz): `422a749d36060c95cb978c3e9f5fed0f9810494243dac8452ad9cfecb17fe348`. [Repeat-B archive](https://github.com/rubixhacker/dyn4k/blob/0995a6bac84de882b0d04b6c3ea18162ca3b4a7c/docs/research/calibration-evidence/interactions/raw-repeat-b.tar.gz): `c9dead5c0e7b96b103ba8f71d67a23923e0efb9bbc9df77e49ad21de2633cb4c`. These are archive hashes, distinct from member hashes. All four selected corresponding gzip members are byte-identical across repeats.

Members below are under `interactions-final-a/` or `interactions-final-b/` within the corresponding archive:

| Gzip member filename | SHA-256 | States / listener events |
|---|---|---:|
| `P-JINT-Weld-enabled-equal-0.jsonl.gz` | `dd0cde1034e4ea4a3d7348b555a4b6a53f62bddd7f7ec30659a3db40ae1df926` | 600 / 1,801 |
| `P-JINT-Pulley-slack-transition-preparation-0.jsonl.gz` | `b8d5571fcc738e6a28fbb1ce5007d504a057d51724af65e196fec69a7139e2ff` | 1 / 8 |
| `P-JINT-Pulley-slack-transition-preparation-1.jsonl.gz` | `58af70a09822c39653f8959c7fab63cb22aa7f2347c4e43a44cfb68039a784f6` | 2 / 22 |
| `P-JINT-Pulley-slack-transition-0.jsonl.gz` | `f4701ce1b6bd1fee14197111c832a7ca491939e32858296f814d9d3ea6fa4134` | 600 / 3,730 |

Fresh audit verifies these raw identities against the [original structural index](https://github.com/rubixhacker/dyn4k/blob/0995a6bac84de882b0d04b6c3ea18162ca3b4a7c/docs/research/calibration-evidence/interactions/audit-manifest.jsonl), embedded input hashes/objects against the [input index](https://github.com/rubixhacker/dyn4k/blob/0995a6bac84de882b0d04b6c3ea18162ca3b4a7c/docs/research/calibration-evidence/interactions/input-manifest.jsonl), all 1,203 contiguous states and 5,561 listener events, required state fields, event schema/order, scheduled actions, and finite JSON numbers including nested exponent overflow. Both repeats are byte-checked; each unique stream is measured once. There are also four input headers, two input-binding records and four continuation actions: 6,774 records total. No physics or upstream test was newly executed.

Run the retained [measurement script](weld-pulley-physical-checks-audit.py), SHA-256 `c4510fbeb9b7561d59a1c96cf7a82c07d7b2376537710eba18a24f23059a9adc`, with Python 3.11+ and a Git clone containing the original revision:

```sh
python3 docs/research/weld-pulley-physical-checks-audit.py DYN4K_GIT_REPO NEW_OUTPUT_DIRECTORY
```

It refuses optimized Python execution, reads the pinned Git objects, extracts only the selected members, writes full `manifest.json` and per-state `samples.jsonl`, and prints the audit/measurement summary. Current local outputs are under `.omo/evidence/weld-pulley/measured-final/`. Immutable upstream source URLs below plus their hashes in the compact manifest identify the independently inspected solver/tests/settings.

## Setup and dimensional settings

The [interaction recipe](https://github.com/rubixhacker/dyn4k/blob/0995a6bac84de882b0d04b6c3ea18162ca3b4a7c/calibration/src/InteractionCases.java) has SHA-256 `68dab71cdc51742c6b6e35048bb3fb5787be31837555f0b57a4f3fab53058403`; the [shared recorder](https://github.com/rubixhacker/dyn4k/blob/0995a6bac84de882b0d04b6c3ea18162ca3b4a7c/calibration/src/Capture.java) has SHA-256 `064d701251261b94fd6538ae49a0737aae8e06c673738c36668838676cd31a28`. Both were read and hashed. Baseline is [dyn4j source 058bf6d982a0fb89b54050f929f6ea9dae53b714](https://github.com/dyn4j/dyn4j/tree/058bf6d982a0fb89b54050f929f6ea9dae53b714), JAR SHA-256 `204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e`; the [capture environment](https://github.com/rubixhacker/dyn4k/blob/0995a6bac84de882b0d04b6c3ea18162ca3b4a7c/docs/research/calibration-evidence/interactions/environment.txt) records OpenJDK 25.0.3 on Bazzite x86_64. JAR execution/source-to-binary correspondence is original provenance, not re-established by this data audit.

Both fixtures use fixed origin (0,0), scale 1, gravity (0,-9.8), timestep `1.0/60` seconds, zero damping and friction, density 1 and restitution 0 (restitution-velocity setting 1 m/s). Settings record 6 velocity iterations, 2 position iterations, linear tolerance 0.005 m, angular tolerance 0.03490658503988659 rad (2 degrees), maximum linear correction 0.2 m, maximum angular correction 0.13962634015954636 rad (8 degrees), warm starting and automatic sleep enabled. These agree with the [pinned Settings defaults](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/dynamics/Settings.java#L73-L103); they are solver parameters, not adopted acceptance budgets.

Weld: static 10 by 0.5 m rectangle centered at (0,0); dynamic 1 by 0.5 m rectangle centered at (0,2); joint anchor (-0.5,2). Spring and damper are enabled at 8 Hz/damping ratio 0.3, spring torque cap disabled, equal angular limits [0,0] enabled, reference angle 0. Initial off-center force (0,-10) N at world (0.5,2) is already queued in the input header: accumulated force (0,-10) and torque -5 N m. It affects the first step; no later force action is scheduled. This is a **spring-enabled equal-limit Weld**, not the spring-disabled rigid mode. There are 600 post-solve states spanning 10 s; no mode transition or separately matched disabled control exists in this trace.

Pulley: static 10 by 1 m floor centered at (0,-1); radius-0.5 m dynamic circles initially at (-1,0) and (1,0.5). Pulley anchors are (-1,1)/(1,1); body anchors start at the centers; ratio 1, target length 1.5 m, slack initially disabled. Preparation first records one step, then changes body2 velocity to (0,10), then records two more steps. The between-segment action is retained in the pinned query stream and the second input header. **Three preparation steps precede the separately numbered 600-step continuation.**

Continuation steps 1-200 have slack disabled. Immediately before step 201, in order: set body2 velocity (0,10), translate it (0,0.1), enable slack. Steps 201-400 have slack enabled; immediately before 401 disable slack, then run through 600. These are evolving within-run phases, not independent matched controls. The 0.1 m translation changes the input before solving; it is not a solver residual. Reconstructing from step200 anchors and that exact action gives pre-step201 error -0.10000000000000009 m. No immediate pre-solve snapshot/private activation flag was recorded, so this reconstruction is labelled separately from sampled post-step values.

## Source constraints, tests and limits of guarantees

**Weld facts:** documentation describes angular limits only with the spring enabled and recommends disabling spring/limits when equal limits are desired for stability ([documentation](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/dynamics/joint/WeldJoint.java#L44-L72)). The [angular getter](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/dynamics/joint/WeldJoint.java#L776-L784) normalizes body2 angle minus body1 angle minus reference angle. For this zero-reference small-angle fixture, direct subtraction equals the recorded getter at every state. In the [soft position solve](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/dynamics/joint/WeldJoint.java#L639-L687), the equal-limit angular correction is clamped, then a linear correction can rotate bodies again. Returned errors are quantities computed before those later corrections. This is not a proof that the post-step angle/anchor error satisfies the same tolerance. Reintroduced angular error is a source-supported explanation, not an instrumented cause established for each sample.

**Pulley facts:** [documentation](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/dynamics/joint/PulleyJoint.java#L43-L67) describes fixed-length and slack behavior. Initialization [sets or clears `overLength`](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/dynamics/joint/PulleyJoint.java#L279-L337) from the current length. The [position solve](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/dynamics/joint/PulleyJoint.java#L386-L462) reuses that flag and returns true without correction when slack was allowed and not over-length. Its error test uses a pre-correction residual. The [current-length getter](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/dynamics/joint/PulleyJoint.java#L539-L553) sums the two geometric lengths; this fixture's ratio is exactly 1. No finding here extrapolates a weighted-length invariant to other ratios.

The [island solver](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/world/Island.java#L122-L190) initializes constraints before integrating positions, then runs at most the configured number of position iterations and may stop early on joint/contact success. Consequently a stopping tolerance is not an unconditional final-state guarantee.

The inspected [Weld simulation tests](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/simulation/WeldJointSimulationTest.java#L196-L310) check non-equal limits under different torque settings at specified checkpoints; their assertion deltas are not bounds for this equal-limit run. The [Pulley slack test](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/simulation/PulleyJointSimulationTest.java#L117-L185) checks preparation endpoints and one immediate slack-enabled step, not 200 delayed-transition steps. Neither test supplies a demonstrated physical guarantee for these complete supplemental trajectories.

## Fresh phase-aware residuals

Weld metrics: signed angular error `angle2-angle1-referenceAngle-0` in radians (no wrap occurs here), and Euclidean distance between world anchors in metres. All values below are sampled after the step, not the queued initial force or an intermediate solver correction.

| Weld metric, steps 1-600 | Minimum (step) | Maximum (step) |
|---|---:|---:|
| Signed angle error (rad) | -0.0014456701862869353 (2) | 0.0006125732000417096 (3) |
| Anchor distance (m) | 5.438094419218942e-12 (34) | 0.0010240181055693979 (1) |

These errors lie within the configured angular/linear tolerances in this capture. That is a diagnostic comparison, not proof of a guarantee or approval of those values as physical acceptance limits. Nonzero errors refute a claim of exact angular locking throughout this trace.

Pulley metric: `e = distance(anchor1,pulley1) + distance(anchor2,pulley2) - 1.5` metres, equivalent here to the earlier weighted expression because ratio=1. It is independently recomputed from recorded anchors. With slack enabled, negative e is intended slack; positive e is extension. With slack disabled, both signs measure departure from the intended fixed length. Tiny signed floating residuals are preserved rather than silently thresholded.

| Pulley segment/phase | Minimum e (step) | Maximum e (step) |
|---|---:|---:|
| Preparation step1 | 0 (1) | 0 (1) |
| Preparation steps2-3, after velocity action | -0.07830621985746422 (2) | 2.220446049250313e-16 (3) |
| Continuation1-200, slack disabled | -4.440892098500626e-16 (155) | 2.220446049250313e-16 (9) |
| Continuation201-400, slack enabled | -0.7061984767002047 (204) | 0.1208278904872957 (209) |
| Continuation401-600, slack disabled | -0.00033225614181509044 (497) | 0 (401) |

Enabled phase has 48 positive samples, of which 39 exceed the configured 0.005 m linear tolerance. The manifest retains the complete step lists; these comparisons are diagnostic, not newly approved thresholds. The largest stretch is not a one-time transient followed by permanent correction: later over-tolerance samples continue through step399.

Illustrative first crossing, with **no action between these steps**:

| Completed step | e (m) | Recorded joint reaction-force y (N) |
|---|---:|---:|
| 208 | -0.0445773829502043 | 0 |
| 209 | 0.1208278904872957 | 0 |
| 210 | 2.220446049250313e-16 | 233.8361963533175 |

**Inference:** the step208 geometry enters the next step slack; source initialization can disable the joint for step209, allowing extension during position integration; step210 then begins over-length and corrects it. The trace chain supports this activation-delay explanation, but does not expose the private flag, iteration count or every intermediate/contact/CCD state. It therefore does not prove that every later positive residual has only this cause. The report preserves all later samples and the preparation transient.

## Physical claims still requiring a decision or experiment

Trace finiteness, action/mode execution, intended slack occurrence and exact discrete/event behavior are checkable now. Ideal zero angular error, a per-step no-extension guarantee, or an acceptable quantitative residual budget are not established. Parity-reference eligibility can be approved separately provided these exclusions remain explicit; physical acceptance cannot be marked passed merely because the same baseline errors reproduce.

If a physical solver-bound claim is required, a separately approved bounded follow-up should first observe both a slack-before-initialization crossing and a deliberately taut-before-initialization control, with exact setup/drive pinned, no direct transform edits during measured steps, and pre-initialization/post-integration/per-position-iteration residuals, `overLength`, solver return values and contact participation recorded. For Weld, compare this exact spring-enabled equal-limit drive with separately labelled spring/limits-disabled rigid mode and inspect angular correction followed by linear correction. A fixed iteration/timestep sensitivity study can distinguish convergence behavior; it still cannot choose an acceptable product error budget by taking observed maxima. No such experiment or correction was performed or authorized by this report.
