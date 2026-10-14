# Frozen sleep/wake physical penetration audit

**Physical gate: FAIL.** All 126,000 selected end-of-step states were evaluated; **125,847 fail and 153 pass**. Every sample in both rest intervals fails at every selected timestep. Audit completion does not make a failed baseline physically acceptable.

Supports [Evaluate approved sleep/wake physical penetration ceilings](https://github.com/rubixhacker/dyn4k/issues/27). The [fixed inclusive schedules](https://github.com/rubixhacker/dyn4k/issues/7#issuecomment-6171650674) and [complete ceilings](https://github.com/rubixhacker/dyn4k/issues/7#issuecomment-6171729184) were approved before this evaluation: initial approach 0 m; impact 1/100 m; initial/wake settling 1/200 m; both rests 1/1000 m. No limit, phase, input, solver setting or baseline byte was changed. No physics was executed.

## Exact observable and bounded qualification

This checks **mathematical geometry represented by stored binary64 transform coefficients**. For the square's four local vertices `(±1/2, ±1/2)`, the affine vertical coordinate is `s*x + c*y + ty`. The minimum is `ty − (|s|+|c|)/2`; penetration below floor top zero is therefore `max(0, (|s|+|c|)/2 − ty)`. Rotation coefficients are used as stored, without normalization, trigonometric reconstruction or a center-height approximation.

The selected input records explicitly contain these square vertices and floor vertices `(±10, ±1/4)`. Archive `source/SleepWakeCases.java:24–46` creates the 1 m square at `(0,0.51)` and 20 m by 0.5 m floor at `(0,−0.25)`. Its source hash is `c808ba452418f6bb88b0eeaf67955ad6691c7e6cdcd1487819d2397640bc00b7`. [Pinned Rectangle construction](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/geometry/Rectangle.java#L80-L84) establishes centered vertices; [pinned Transform](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/geometry/Transform.java#L246-L257) establishes the affine interpretation. The [recorder](https://github.com/rubixhacker/dyn4k/blob/0995a6bac84de882b0d04b6c3ea18162ca3b4a7c/calibration/src/Capture.java#L47-L165) records the transform after each world step and fixture geometry in inputs. Archive Capture SHA-256 is `064d701251261b94fd6538ae49a0737aae8e06c673738c36668838676cd31a28`.

The evaluator verifies the input vertices, body identities and finite coefficients, then checks floor identity rotation/translation at every state. It also proves every transformed square vertex remains horizontally within the finite floor's `[-10,10]` span using the exact horizontal extent. Thus an infinite-plane substitute cannot silently pass a square outside the floor. The fixed source and stream identities pin fixture immutability; the compact per-step records do not independently serialize mutable fixture vertices.

Binary64 values are decoded from bits to signed BigInt integers in units of `2^-1075` m. Normal values have integer significand shifted by their biased exponent; subnormals have fraction shifted by one. Every decoded value is even in these units, so halving the sum of absolute coefficients is exact, including subnormals. No floating-point arithmetic participates in depth or acceptance comparisons. Nonzero ceilings are the exact rationals `1/100`, `1/200`, `1/1000`, compared by integer cross multiplication; zero requires depth exactly zero. Positive decimal ceilings are not dyadic, so no finite-coefficient depth equals them exactly. Equality is nevertheless accepted by the general comparison, tested at a representable rational threshold. Approximate decimals in observations are presentation only; exact reduced fractions govern decisions.

This is a narrow, independently cross-checked frozen-baseline measurement, not a general target comparator or runtime certification. It does not establish hidden intermediate physics accuracy, platform getter rounding, correct target execution, callback depth acceptance, trajectory parity or any dyn4k port result. Those gates remain unpassed or unresolved; all in-scope targets remain required.

## Complete results

All ranges are inclusive. `—` means no failures. Maxima are observations, **not suggested limits**. Exact minima/maxima, first maximizing steps, closest-to-ceiling samples with signed exact headroom, counts, complete failed ranges and identities are in [observations](sleep-wake-penetration-acceptance-observations.json). The empty 30 Hz approach interval contains no end-of-step samples; it is not an executed positive-count pass.

| Hz | Phase | Samples | Failed | All failed indices | Maximum depth, approximate m |
|---|---|---:|---:|---|---:|
| 30 | initial-approach | 0 | 0 | — | no samples |
| 30 | impact | 3 | 2 | 2–3 | 0.021777777777777785 |
| 30 | initial-settling | 14 | 14 | 4–17 | 0.013381024015151203 |
| 30 | rest-before | 8983 | 8983 | 18–9000 | 0.0057119947081524505 |
| 30 | wake-settling | 21 | 21 | 9001–9021 | 0.0055963042807547093 |
| 30 | rest-after | 8979 | 8979 | 9022–18000 | 0.0050142084795754471 |
| 60 | initial-approach | 2 | 0 | — | 0 |
| 60 | impact | 3 | 1 | 4 | 0.010888888888888892 |
| 60 | initial-settling | 29 | 29 | 6–34 | 0.0091677640776147411 |
| 60 | rest-before | 17966 | 17966 | 35–18000 | 0.0050248349134171741 |
| 60 | wake-settling | 42 | 42 | 18001–18042 | 0.005020783810169788 |
| 60 | rest-after | 17958 | 17958 | 18043–36000 | 0.0050000116079303766 |
| 120 | initial-approach | 4 | 0 | — | 0 |
| 120 | impact | 3 | 0 | — | 0.0040833333333333277 |
| 120 | initial-settling | 58 | 0 | — | 0.0040833333333333277 |
| 120 | rest-before | 35935 | 35935 | 66–36000 | 0.0040833333333333277 |
| 120 | wake-settling | 83 | 0 | — | 0.0040833333333333303 |
| 120 | rest-after | 35917 | 35917 | 36084–72000 | 0.0040833333333333303 |

## Source-supported interpretation and next decision

**Proven facts:** the frozen inputs use linear tolerance 0.005, Baumgarte 0.2 and two position-solver iterations. [SequentialImpulses](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/dynamics/contact/SequentialImpulses.java#L548-L631) adds allowed penetration to its contact-separation estimate before clamping correction, and its return condition allows `minSeparation >= −3 * allowedPenetration`. That solver estimate is not the exact four-vertex metric. [World execution order](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/world/AbstractPhysicsWorld.java#L1225-L1332) creates ordinary contact constraints after solving the existing constraints and processing TOI; [Island](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/world/Island.java#L139-L211) limits position iterations and performs sleep processing. The prior [event audit](sleep-wake-penetration-phases.md) fixes touchdown/first-solve steps at 1/3, 3/5 and 5/7 respectively.

**Inference:** a finite-iteration solver with an intentional approximately 5 mm contact dead zone does not promise the chosen 1 mm geometric rest ceiling, nor a strict 5 mm transient ceiling. Persisting resting depth is consistent with that algorithm and the frozen sleep histories. Contact creation and the following solve explain why the early impact interval can contain substantial penetration. These source observations explain mechanisms, not a complete causal replay or a finding of an implementation defect; no callback depth is substituted for geometric depth.

**Proposed next investigation:** retain this failed baseline result and trace the first failed impact/settling sample and stable-rest residual back through the pinned contact/position-solver calculations, with explicit authorization if new runs or altered settings are needed. The human decision must choose whether to keep the quality requirements and address the incompatibility with baseline behaviour, or explicitly reconsider requirements. Neither preserving compatibility nor changing a threshold automatically qualifies physical quality. No exception, corrective physics change or relaxation is approved here. [Define numerical and migration acceptance](https://github.com/rubixhacker/dyn4k/issues/7) remains open.

## Reproduction and evidence

Use Node.js (captured: v26.10.0) and the unchanged [published archive](https://github.com/rubixhacker/dyn4k/releases/download/calibration-raw-20260914/dyn4j-sleep-wake-20260914.tar.gz). Its SHA-256 is `89d88301ad5ea14a621d8a6e86bfc3dfc90f84a0d7e8abda65f2f526de1b5bee`. The evaluator pins the [selection manifest](initial-reference-review-manifest.json) hash `b42174c7523bea9687e4ab015a215b4e652c2446df73d2f41e836e8a165c1208`, source hashes, all three compressed/decompressed stream hashes and each input hash. It verifies counts and contiguous state indices. Historic pending fields in that manifest precede the approved reference checkpoint.

```sh
sha256sum /path/to/dyn4j-sleep-wake-20260914.tar.gz
node docs/research/sleep-wake-penetration-acceptance.test.mjs /path/to/dyn4k-sleep-evidence
node docs/research/sleep-wake-penetration-acceptance.mjs /path/to/dyn4k-sleep-evidence /tmp/penetration-audit
# Expected exit 2: complete audit, physical FAIL. Exit 1 means invalid/incomplete evidence.
cmp /tmp/penetration-audit/observations.json docs/research/sleep-wake-penetration-acceptance-observations.json
```

The [minimal evaluator](sleep-wake-penetration-acceptance.mjs) emits `observations.json` and `failures.jsonl.gz`. The latter contains every failed Hz/step, phase, exact ceiling, exact depth/excess and original coefficients. Its SHA-256 is recorded in observations. It is generated rather than committed because the complete failed indices already fit in the compact ranges. A partial output from an exit-1 invocation is invalid; only a complete exit-0 or exit-2 audit is meaningful.

| Scenario | Exact invocation / verification | Binary observable | Captured artifact relative to worktree |
|---|---|---|---|
| Archive identity | `sha256sum` archive above | exact published hash | `.omo/evidence/penetration-acceptance/archive.log` |
| Decoder, exact/adjacent threshold, four-vertex signs/extremes, phase boundaries/coverage and finite/floor/span/fixture rejection | test command above | exit 0; 295 semantic assertions pass | `.omo/evidence/penetration-acceptance/tests.log` |
| Distinct source and compressed-member hash mutations | same test command with extracted root | both child processes exit 1 with expected hash diagnostic | `.omo/evidence/penetration-acceptance/tests.log` |
| All 126,000 physical states | evaluator command above | exit 2; 125,847 failures retained | `.omo/evidence/penetration-acceptance/audit.log`, `audit/observations.json`, `audit/failures.jsonl.gz` under same evidence directory |
| Published observations/full-detail integrity | `python3 .omo/evidence/penetration-acceptance/validate.py` (captured helper) | equality; all 125,847 detail rows match ranges and rational ceiling failures | `.omo/evidence/penetration-acceptance/validation.log` |

The test script enumerates all four vertices independently of the closed-form production depth across coefficient signs, translations, subnormal and extreme values; tests every phase's endpoints and complete coverage; exercises positive approach rejection and binary64 neighbours of each exact decimal ceiling. Hash failures are tested separately from semantic rejection. The parent review additionally implements all-state geometry using Python `Fraction.from_float` with four-vertex enumeration, independent of this BigInt decoder and closed form. Its counts, every failed range and exact maxima match the results here; parent evidence owns that independent implementation and capture.
