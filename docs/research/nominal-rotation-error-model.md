# Conditional nominal rotation error model

Research for [Derive a qualified nominal rotation error model](https://github.com/rubixhacker/dyn4k/issues/22), supporting [Define numerical and migration acceptance](https://github.com/rubixhacker/dyn4k/issues/7). **Proposed, pending human approval; baseline primitive qualification and all port-runtime qualification remain unpassed.**

A conservative model is available for the exact selected 36,000-step fixture. It uses an orthogonal-reference recurrence, outward-rounded analytic phase certificates, signed-acos conditioning, and a complete recorder error decomposition. These are conditional mathematical bounds, not demonstrated all-target guarantees. They are derived without reading observed residuals. No physics experiment or engine change was made.

| Metric, every step | Derived upper bound (display rounded upward) | Proposed analytic absolute cap | Proposed baseline-to-port absolute cap |
|---|---:|---:|---:|
| Each stored cosine/sine component, dimensionless | `6.394884622e-11` | `7e-11` | `1.4e-10` |
| Public signed-acos angle, wrapped distance, rad | `4.886052375e-8` | `5e-8` | `1e-7` |
| Recorder accumulated rotation, ordinary unwrapped distance, rad | `5.012352752e-8` | `6e-8` | `1.2e-7` |

All relative allowances are **zero**. Each analytic cap is the model bound rounded upward to one significant decimal digit; each parity cap is twice its analytic cap by the triangle inequality (the circular metric for wrapped angles). Both analytic and parity checks remain mandatory. Previous-transform components and public angle inherit the same caps at `n-1`; the approved exact previous/current relationship remains mandatory. The initial transform/angle is exact. Approved position, velocity, force, getter-consistency, reference-selection and diagnostic classifications are unchanged. These numbers apply to no other fixture, timestep, duration, scale, solver, or mutation schedule.

## Pinned inputs and actual algorithms

The selected member is `L-free-s1.0-o0.0_0.0-hz60-0.jsonl.gz`, compressed SHA-256 `4981795bffcd2a0262040acb53c60b20607fea14a2a0c7d79e858ba68e7f2743`. Its exact input definition and other hashes remain in the [approved reference packet](https://github.com/rubixhacker/dyn4k/blob/cc01d509b5de6f10ebb410b58a37f8722a43d5c7/docs/research/free-motion-reference-review.md). Initial rotation is zero, angular velocity is exactly `0.5`, and the binary64 timestep is `0.016666666666666666`. Define, in exact real arithmetic,

```
u = 2^-53
alpha = encoded_dt / 2 = 4803839602528529 / 576460752303423488
theta_n = n alpha, n = 0..36000
q_n = (cos(theta_n), sin(theta_n))
```

Multiplication by `0.5` is exact here. The already approved constant-velocity/configuration checks establish this unchanged-input premise; no accumulated floating clock defines the oracle. [Scene recipe](https://github.com/rubixhacker/dyn4k/blob/0995a6bac84de882b0d04b6c3ea18162ca3b4a7c/calibration/src/SceneCases.java#L24-L30).

The pinned [Transform rotation](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/geometry/Transform.java#L136-L159) computes both components from the old pair, then clamps each to `[-1,1]`. The [getter](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/geometry/Transform.java#L532-L537) returns `acos(c)` if `s>=0`, otherwise its negation. [Capture](https://github.com/rubixhacker/dyn4k/blob/0995a6bac84de882b0d04b6c3ea18162ca3b4a7c/calibration/src/Capture.java#L148-L162) adds `atan2(sin(a_n-a_previous), cos(a_n-a_previous))` to a binary64 running sum. Subtraction appears twice and must have identical semantics and inputs. The stored previous angle is the same getter result used here, under deterministic pure calls; an instrumented qualification must check that premise. Ordinary `atan2(s,c)` is not substituted for the public getter.

## Explicit hypotheses and baseline specification

H1: The exact input, unchanged angular velocity, initial identity, operation graph (allowing only the equivalent local fusion covered below), component assignment order, clamping, getter and recorder above apply. No hidden normalization, callback mutation or extended intermediate is substituted.

H2: Basic operations use binary64 round-to-nearest ties-to-even with gradual underflow; there is no fast-math reassociation, precision reduction, flush-to-zero or double rounding. Unary negation and copies are exact. Fixed rounding makes the two recorder subtractions agree. All supplied and produced values are finite. Summation is in the recorded order. A correctly rounded binary64 FMA may replace one multiplication plus the addition/subtraction in a rotation component only where it uses the same old-state operands and retains the local defect bound proved below. Other contraction/reordering requires a separate proof and remains unqualified.

H3: For the actual arguments, sine and cosine have absolute error at most `2u`; acos at most `4u` radians; atan2 at most `8u` radians. The initial `acos(1)` is zero. Identical getter calls on unchanged inputs are deterministic. These absolute envelopes suffice; stronger full-domain ulp contracts are not required for this bounded model.

The captured baseline uses JDK25. Java25 documents one-ulp accuracy for sin, cos and acos, and two ulps for atan2. Their result ranges imply H3's deliberately coarse envelopes. This is a specification statement, not a fresh test of the archived JVM. [Java25 Math](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Math.html#sin(double)); immutable [OpenJDK25 Math source](https://github.com/openjdk/jdk/blob/6c48f4ed707bf0b15f9b6098de30db8aae6fa40f/src/java.base/share/classes/java/lang/Math.java#L173-L263) and [atan2 contract](https://github.com/openjdk/jdk/blob/6c48f4ed707bf0b15f9b6098de30db8aae6fa40f/src/java.base/share/classes/java/lang/Math.java#L596-L617). The pinned release source is specification evidence, not an assertion that its executable is the captured vendor build.

Java25 floating expressions use strict IEEE semantics, including rounding and gradual underflow; replacing a multiply followed by addition with an implicitly fused operation would change the specified evaluation. [JLS25 floating expressions](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.4). Neither Java's language contract nor its Math contract establishes Kotlin/Native, JS, Wasm or other runtime behavior.

## Component proof: linear growth despite computed matrix drift

Let `x_n` be the stored pair; clamping ensures both components have magnitude at most one. Let `R` be the **exact** orthogonal rotation through alpha. Library coefficients differ from exact coefficients by at most `2u`. Therefore replacing them by the exact coefficients changes each unrounded component by at most `4u`.

Each product has magnitude below two, so its rounding error is at most `u`; the unrounded final sum/difference has magnitude below four, so its rounding error is at most `2u`. Thus the arithmetic error in each component is at most `4u`, and the complete local defect is at most `8u` per component, less than `16u` in Euclidean norm. These absolute bounds also cover zero/subnormal products under gradual underflow. The permitted FMA form has only one separately rounded product (`u`) and one correctly rounded fused result (`2u`), so its arithmetic defect is at most `3u`, also inside the same `4u` allowance; unproved fast-math rewrites do not inherit this result.

Coordinatewise clamping is projection onto a square containing every ideal `q_n`, hence it cannot increase distance to `q_n`. Orthogonality of the exact `R`, not of the computed coefficients, gives

```
||x_n-q_n||_2 <= ||R(x_(n-1)-q_(n-1))||_2 + 16u
               = ||x_(n-1)-q_(n-1)||_2 + 16u
               <= E_n = 16 n u.
```

This uniform bound is intentionally loose. It avoids exponentially widening component intervals and does not assume the computed pair remains on the unit circle.

## Getter: signed acos and certified branch margins

For each `n>=1`, the certificate encloses the exact sine and cosine at `theta_n`. It checks

```
|sin(theta_n)| > E_n
m_n = |cos(theta_n)| + E_n < 1.
```

The first inequality proves the stored sine has the correct nonzero sign; the second excludes endpoint singularities throughout the interval joining the actual and ideal cosine. The mean-value theorem and the derivative of acos give the **direct principal-angle** error

```
B_n = E_n / sqrt(1-m_n^2) + 4u.
```

The certificate rounds the denominator downward and the quotient upward. It also verifies every reduced phase lies strictly between `-pi` and `pi`. All 36,000 checks pass. The minimum sine-sign margin exceeds `7.401307613e-5`; the minimum acos-domain margin exceeds `2.738298086e-9`. The maximum bound occurs at step 35814, and is below `4.886052375e-8` radians. Circular distance is no greater than this direct error, including across the principal-angle branch cut when comparing two captures. Derivative identities are standard mathematical facts; see [NIST DLMF trigonometric derivatives](https://dlmf.nist.gov/4.20).

At `n=0`, identity and `acos(1)=0` supply exact initial values; a singular derivative is not used. This is a **fixture-specific** margin proof, not a global Lipschitz guarantee for acos. If any margin fails for another schedule, this proof rejects it; it neither supplies a hidden global fallback nor silently widens the cap.

## Recorder: wrap, transcendental evaluation and summation

Write the getter as `a_n=phi_n+e_n`, where `phi_n` is the exact principal phase and `|e_n|<=B_n`; `e_0=0`. Let `B=max B_n`.

1. Each exact difference `a_n-a_(n-1)` has magnitude below eight; its binary64 subtraction error is at most `4u`. Reducing it mathematically modulo `2pi` yields `alpha+e_n-e_(n-1)+d_n`, with `|d_n|<=4u`, provided this small quantity is in the principal interval.
2. The wrapper sine/cosine errors form a vector perturbation with norm at most `2 sqrt(2) u < 3u` around an exact unit vector. Along the straight connecting segment its norm is at least `1-3u`, so integrated angular error is at most `3u/(1-3u)<4u`.
3. The atan2 result contributes at most `8u`. The combined wrapper error relative to `alpha+e_n-e_(n-1)` is therefore at most `W=16u`.
4. The certificate proves `0 < alpha-2B-W` and `alpha+2B+W < pi`. Thus perturbations cannot change turn count, cross atan2's branch, or reverse an increment. This argument covers source differences near `alpha-2pi`; no floating `2pi` subtraction is performed by the recorder.
5. Before final accumulation roundoff, the getter errors telescope: the sum through step `n` differs from `n alpha` by at most `B_n+nW`, rather than `2nB`. Each computed increment has magnitude at most `alpha+2B+W`. Standard repeated round-to-nearest multiplication-of-error-factors reasoning gives `gamma_n=n u/(1-n u)` for the running additions. Consequently

```
|recorded_sum_n - n alpha|
 <= B_n + nW + gamma_n * n * (alpha+2B+W).
```

For a uniform cap use `n=36000` and `B_n<=B`. The three contributions are at most `4.886052375e-8`, `6.394884622e-11`, and `1.199054928e-9` radians. Their sum is below `5.012352752e-8`. Sums and increments stay positive and normal, with no overflow; no cancellation-dependent relative sum assumption is needed. This completes the error model beyond a summation-only gamma estimate.

## Reproducible certificate and separate baseline plausibility replay

[The certificate script](nominal-rotation-error-model-certificate.py) uses Python arbitrary-precision integers and rational numbers, not host libm, for all bounds. Closed intervals use a `10^-70` lattice; every product/division is rounded outward. Pi is enclosed by Machin's identity using 200 terms of each alternating arctangent series and the first omitted term. The identity follows from the tangent addition formula: `tan(4 atan(1/5))=120/119`, and subtracting `atan(1/239)` produces tangent one in the first quadrant. Taylor polynomials of degree119 for sine and118 for cosine use rigorous Lagrange remainder bounds on `|x|<4`; both are below one lattice unit. Every argument reduction is itself interval checked. No finite-precision pi constant is silently exact.

```sh
python3 docs/research/nominal-rotation-error-model-certificate.py \
  .omo/evidence/nominal-rotation-error-model
```

Output: `manifest.json` with conditional bounds/caps and `steps.jsonl` with all 36,000 checked margins and getter bounds. [Compact publication manifest](nominal-rotation-error-model-manifest.json) pins identities and output hashes. The script exits nonzero on a failed mathematical precondition. Separate arithmetic checks covered 75 exact rational interval operations, the zero-angle identities and rejection of an out-of-domain Taylor argument.

The existing [remaining-metrics auditor](free-motion-remaining-metrics-audit.py) was independently rerun against the exact archived member, checking all hashes, 36,000 states and 108,001 events. It reproduced component maxima `1.811470423674861e-12` and `1.820148267512173e-12`, wrapped getter maximum `1.3912021084299924e-9`, and recorder maximum `1.4258530918465073e-9`. They lie comfortably below the proposed caps. This is a **separate plausibility check** using the earlier Decimal oracle, not the derivation, a certified acceptance comparator, or proof that every primitive hypothesis held. In particular the archive does not capture all recorder wrapper intermediate results. No dyn4k trajectory or new baseline capture was executed.

## Required future qualification and unresolved status

Each approved target/runtime/configuration still needs its own exact-candidate evidence. Record artifact hash, source revision, compiler/backend/version, flags, optimizer/contraction/fast-math settings, CPU/OS/runtime/libm identity, floating environment and the exact recorder/checker revision. Establish H1/H2 from source plus generated-operation/runtime evidence, including deterministic getter calls, equal subtraction operands and order, binary64 rounding, gradual underflow, and absence of unproved rewrites (including evidence for the covered FMA form if used). A generic compiler banner or passing trajectory alone is insufficient.

For H3, retain a documented/certified error contract tied to the actual linked implementation and compiler/runtime configuration, or validate the actual constant-step sin/cos outputs, every actual getter acos input/output, and every wrapper subtraction, sin/cos and atan2 input/output against independently certified high-precision enclosures. The latter is a finite actual-call qualification, not an inference of a whole-libm theorem from samples. Evidence must reach the candidate's actual math path and operands: modifying the artifact to add probes cannot be silently called exact-candidate qualification. A pure-primitive helper is usable only with evidence that it executes the identical linked implementation, lowering, dispatch and floating environment for those exact operands; another backend/libm is insufficient. If JIT/runtime dispatch changes, every executed variant needs evidence. If neither valid contracts nor an adequate observation method exist, that runtime remains unqualified and blocking; unsupported tracing is not presumed available. Norm/branch checks then apply to the actual selected schedule. The archived baseline needs an explicit retained specification/conformance argument or separately pinned primitive qualification; its final trace alone cannot retrospectively reveal uncaptured intermediates.

The acceptance comparator must enclose errors, not use an unqualified target atan2 or treat a rounded analytic result as exact. Parse recorded binary64 values exactly; enclose analytic sine/cosine and `n alpha` with outward arithmetic. For wrapped angles, enclose `min_k |a-b-2k pi|` (or the analytic principal phase) using a certified pi interval and integer branch enumeration. **Pass only if the error interval's upper endpoint is at or below the real cap; fail if its lower endpoint exceeds it; otherwise refine or report inconclusive.** The comparator and enclosure implementation need their own qualification and recorded precision. That requirement includes baseline-to-port comparisons and prevents boundary rounding from spending unrecorded tolerance.

Historical baseline primitive qualification and direct baseline analytic checking are distinct routes. A certified direct check of the frozen reference outputs against these analytic caps can establish the baseline side of the triangle inequality without reconstructing uncaptured wrapper calls. The historical primitive status then remains unqualified, blocking a claim that every hidden baseline call followed the model, but not reference/cap selection or the empirical baseline side of parity. This packet's earlier-oracle replay is only plausibility evidence; a direct certified baseline comparison remains future qualification. The proposed port/runtime obligation is unchanged: qualify the actual candidate hypotheses and execute its trajectory checks.

All selected trajectory checks must then execute on every required runtime; primitive qualification never waives them. Failures, missing platforms and unavailable proof stay explicitly failed/unavailable/unpassed. They cannot automatically widen caps, change a reference, or remove an experimental target. Remaining human decisions are approval of these conditional hypotheses, caps and qualification obligations. Remaining runtime work is entirely unpassed. This bounded report does not resolve other fixtures or the overall acceptance ticket.
