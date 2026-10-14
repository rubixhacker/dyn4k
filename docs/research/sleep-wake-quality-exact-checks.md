# Configured sleep/wake exact-consistency audit

**Result: the approved six groups pass on all six frozen configured baseline captures.** This is a bounded same-run consistency result, not port parity, target-runtime qualification, a trajectory-error bound, performance evidence, or release qualification. No physics was executed for this audit. The original default-profile physical failure and the separately approved configured-profile represented-geometry pass retain their separate meanings.

The [approval checkpoint](https://github.com/rubixhacker/dyn4k/issues/7#issuecomment-6174578804) extends the existing six-group package to the references and corroborating runs in the [frozen candidate manifest](sleep-wake-quality-candidate-manifest.json). Repetition 1 is the reference for each outer cadence; repetition 2 is corroboration. All six use internal `1/120 s` steps, with outer 30/60/120 Hz grouping 4/2/1. They do not provide native 1/30 or 1/60 engine-timestep evidence.

## Binding and checker

The [wrapper](sleep-wake-quality-exact-checks.mjs) imports `checkSnapshot`, `checkImpulse` and `checkTimeStep` from a **verbatim** copy of the [original semantic module](https://github.com/rubixhacker/dyn4k/blob/cd610b696f1f7be2f3c1590840139a7cc596b04c/docs/research/sleep-wake-exact-checks.mjs). Its required SHA-256 is `803f78a03aca84b4177de0d22d6d4f3b2bef79ce258e16d8028e65fcaeb7346a`. The original wrapper is not invoked. The configured binding reuses only the identity function from the existing geometry auditor, not its physical evaluation or its stricter endpoint equality.

Required manifest SHA-256: `7efd60aa76cab10fdc27eb8e968a2868e854433cc4556e10257dbd290a63e554`. Required [archive](https://github.com/rubixhacker/dyn4k/releases/download/sleep-wake-quality-candidate-20261014/dyn4j-sleep-wake-quality-20261014.tar.gz) SHA-256: `057d96767dcf4ef863afb61417f8ef9cc6b7fc1442e0e39df55bbe006cb1212c`. The manifest binds source/class/JAR/runtime files and all six compressed, decompressed and input identities; the wrapper verifies those identities. Hash failures and semantic failures both abort, but are tested separately.

Exact semantic equality means finite numeric equality, including `+0 == -0`, with object key order immaterial and missing/extra fields rejected by the relevant snapshot/copy schema. It does not mean byte equality. A duplicate outer endpoint is compared numerically to its immediately preceding inner state and inherits that state's checks. It neither executes the step checks again nor advances the previous-state chain. At inner step 36001, before/action/after records must appear in order 0/1/2 before callbacks. The next inner state's previous transform uses the immediate post-action snapshot; both action snapshots preserve the preceding current and previous poses.

## Coverage ledger and observations

The [machine-readable observations](sleep-wake-quality-exact-observations.json) include every run's identities, record/listener/method counts and semantic coverage. SHA-256: `e464a6d87ca1c50aa6ebe313797c1b6e5c943ac9118372acd18e5eb6679e654b`.

| Approved group | Direct coverage and binary result |
| --- | --- |
| Fixed floor | Both-body snapshots at 432,000 inner states and 18 initial/action snapshots checked; floor pose, previous pose, velocities and rotation accumulator satisfy the fixed-floor relations. Floor `atRest` is unrestricted. PASS. |
| Zero applied-force channels | Force, accumulated force, torque and accumulated torque checked for both bodies in all 432,018 snapshots. Gravity is not treated as an applied-force queue. PASS. |
| Sleeping velocity and own-run pose | 431,112 sleeping inner states have zero linear/angular velocity; 431,100 consecutive sleeping inner-state pairs preserve their own pose. Six pre-action snapshots additionally preserve the preceding sleeping pose. No cross-run sleeping-pose equality is imposed. PASS. |
| Immediate center impulse | Six complete before/after pairs: zero sleeping input, immediate `(1,0)` output, zero angular velocity, awake output, and all other recorded fields unchanged. The following step is not required to retain velocity `(1,0)`. PASS. |
| Aliases, previous copies and ten duplicates | All 432,018 snapshots check transform scalar/vector/matrix and centered-world aliases plus phase-correct temporal copies. Each of 18 full snapshots checks ten duplicated getters for both bodies: 360 duplicate relationships. Angle is copied when appropriate, never recomputed as an exact trig invariant. PASS. |
| Timestep metadata | All 1,296,006 StepListener payloads check five getters at internal 120 Hz. First previous dt/inverse are `1/60` and `60`, ratio `0.5`; subsequent previous dt/inverse are `1/120` and `120`, ratio `1`. PASS. |

Additionally, 252,000 outer endpoint copies are checked (36,000 at outer30, 72,000 at outer60, 144,000 at outer120, including both repetitions). They are duplicate observations, not extra physics steps. Every one of 5,615,802 event records is consumed in step/order sequence; listener and method counts match each bound capture, and each step has ordered begin/postSolve/end, with updatePerformed additionally at step 1. Every numeric field in every parsed record must be finite. Unknown record kinds and listener methods fail. These checks establish coverage and consistency of the frozen trace, not a general port event comparator or numeric acceptance of arbitrary callback quantities.

## Why the source assumptions survive this configuration

Only linear tolerance and position-iteration count change engine settings. The [frozen caller and passive recorder](https://github.com/rubixhacker/dyn4k/tree/82395ce9c39f7a0973f71ecb025275d8a496683e/docs/research/sleep-wake-quality-capture) retain the infinite floor, centered fixtures, unit dynamic mass, empty force queues, center impulse and state-copy observation path. The new outer loops explicitly call internal 1/120 steps. Those are the premises used here.

The changed settings control [position correction and its convergence test](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/dynamics/contact/SequentialImpulses.java#L539-L631) and [iteration/sleep scheduling](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/world/Island.java#L124-L211). They can alter trajectory, sleep-entry time and settled pose; none of those values is inferred from the old default trace. They do not change the [zero-force accumulation path or infinite-mass integration guard](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/dynamics/AbstractPhysicsBody.java#L685-L828), the [sleep setter's zero velocities and retained pose](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/dynamics/AbstractPhysicsBody.java#L924-L939), or the [immediate center-impulse formula](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/dynamics/AbstractPhysicsBody.java#L616-L645). Sleep does not itself clear current force/torque; the empty-force fixture remains essential.

The [world's previous-transform copy](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/world/AbstractPhysicsWorld.java#L1235-L1321), [transform getter relationships](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/geometry/Transform.java#L283-L605), and [TimeStep update/getters](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/dynamics/TimeStep.java#L58-L140) likewise do not depend on those two solver settings. This supports reuse of the narrow invariant proofs, not a claim that all numeric solver outputs are exact or acceptable.

## Reproduction and verification

With `PACKAGE` the extracted candidate directory and `ARCHIVE` its downloaded archive:

```sh
node docs/research/sleep-wake-quality-exact-checks.mjs "$PACKAGE" "$ARCHIVE" observations.json
QUALITY_EVIDENCE="$PACKAGE" QUALITY_ARCHIVE="$ARCHIVE" node --test docs/research/sleep-wake-quality-exact-checks.test.mjs
SLEEP_EVIDENCE="$ORIGINAL_DEFAULT_PACKAGE" node --test docs/research/sleep-wake-exact-checks.test.mjs
```

The full audit exits 0. New tests execute 92 assertions using actual configured initial, moving, sleep-entry, repeated-sleep, action and following-step samples across all three outer cadences, plus two separate archive/provenance rejection scenarios. Endpoint positive cases change signed zeros and recursively reorder keys; negative cases change nonzero pose, lose fields or alter endpoint index. Other mutations exercise wrong previous-copy timing, sleeping velocity, duplicated getters, impulse fixture mutation, timestep getters and grouping. The unchanged original suite passes all 649 named tests against its original data; it corroborates the reused helper semantics, not configured-wrapper coverage.

Execution logs are recorded under `.omo/evidence/quality-exact/` in the research worktree. The bounded result leaves awake trajectory/contact/TOI numerical budgets, target execution, port comparison and release gates unresolved. No further settings change, capture, or acceptance extension is implied.
