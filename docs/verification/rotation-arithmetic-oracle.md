# Independent rotation arithmetic oracle

## Result and boundary

`tools/numerical/portable/rotation_oracle.py` checks one supplied
`portable-rotation-audit/1` payload against the pinned source operations.
It does not activate the conditional `U(N)` policy or qualify a target.
The caller must supply an independently captured call manifest, complete
body-step receipts, a process receipt, and the exact observed bytes.
The API reports `UNPASSED` when binding evidence is missing. Matching hashes
and a caller-supplied receipt do not establish that a target process ran.

The four geometry premises remain `UNPASSED_PREMISE`:
`geometry-boundary-s1-o3-d1`, `geometry-boundary-s1-o3-d3`,
`geometry-boundary-s1-o4-d1`, and `geometry-boundary-s1-o4-d3`.
`P-J-Angle-ratio-limits-off--1.0` remains a separate physical failure.
The original fixed 32-ulp rule retains 41 `FAILED_DERIVED` reference results.
The default sleep/wake represented-geometry gate remains failed at
125,847 of 126,000 states. No result here changes an approved bound.

## Public API and producer contract

Call `verify_rotation_arithmetic(audit, case, header, states, rotation_cap,
binding=..., trace_bytes=..., payload_bytes=..., receipt_bytes=...,
artifact_bytes=..., source_bytes=...)` from an external runner. The audit
uses the existing exact binary64 hex fields and source revision. `case`,
`header`, and `states` are the independently captured target case and trace.
The runner must retain the raw files and supply bytes from that run.
`payload_bytes` must be the captured audit JSON file bytes; the verifier parses
that file and compares its content with `audit` before checking the calls.
`trace_bytes` must be the captured JSONL trace from the same process. The
supervisor must verify the process command, exit status, runtime, artifact
identity, and the build link from `source_bytes` to `artifact_bytes` before
passing their bytes and receipt to this API. It must also establish that the
manifest and accepted TOI call arguments were recorded independently of the
audit payload. Hash agreement alone cannot establish any of these facts.

`binding` requires `producer_process`, `producer_command`, `runtime_id`,
`artifact_sha256`, `target_source_sha256`, `operation_source_revision`,
`trace_sha256`, `payload_sha256`, `audit_sha256`, `receipt_sha256`,
`manifest_sha256`,
`expected_calls`, `body_step_receipts`, `accepted_toi_resets`,
`accepted_toi_events`,
`reset_start_rotations`, `reset_end_rotations`, `pair_inputs`, and
`allowed_evaluations`. The receipt JSON repeats
the process, command, runtime, source and artifact identities, file hashes,
operation revision, manifest hash, and integer `exit_code: 0`. Its SHA-256 binds the bytes.
The caller must obtain this receipt from the process supervisor, not from
the target audit payload. The API parses JSONL inputs and state rows from the
trace and checks them against the supplied header and states. It checks byte
hashes and receipt agreement;
it cannot prove the supervisor's honesty or that source bytes built the
artifact. That relationship remains an external execution gate.

`expected_calls` lists each call's step, body ID, operation kind, branch,
and rotate input kind in execution order. It must come from independent
instrumentation or trace reconciliation. `body_step_receipts` lists every
`[step, body_id]`, including zero-call steps. `accepted_toi_resets` comes
from accepted TOI events, not the audit's own declaration.
For each reset sequence, `accepted_toi_events` names the accepted event's
step, order, body ID, and exact binary64 `alpha_bits`; `accepted` must be true.
The verifier finds that event in the JSONL trace and requires its `payload.time`
and body index to match the bound call. The supervisor must attest that the
callback was accepted, since the callback row alone does not prove acceptance.
`reset_start_rotations` maps call sequences to the body's previous transform
rotation. `reset_end_rotations` maps them to its current rotation before the
reset. Both values use `[cos_bits, sin_bits]`. The start pair must match the
recorded same-step `previousTransform` exactly, including signed zero.
The current audit schema does not record either source pair separately.
`pair_inputs` maps rotate call sequences to independently observed `Rotation`
pairs when `input_kind` is `pair`.
If the producer cannot supply independent source pairs or a full call manifest,
the case remains `UNPASSED`.

`allowed_evaluations` declares which target arithmetic modes were independently
established: `strict`, `fma_left`, `fma_right`, or `fused`. The oracle returns
the matching modes for each raw component. A recorded result must match at
least one declared mode. A successful local arithmetic check returns
`PASSED_ARITHMETIC` with `qualification: UNPASSED`; it never returns a target
qualification pass. Missing evidence returns `UNPASSED`; stale identities
return `FAILED_IDENTITY`; omitted, extra, or reordered calls and resets
return `FAILED_COVERAGE`; impossible arithmetic returns `FAILED_ARITHMETIC`.

## Arithmetic derivation

The oracle decodes every finite binary64 field by its exact 64 bits.
It requires GNU MPFR **4.2.2** and passes the exact argument to MPFR at
320-bit precision. MPFR evaluates `sin`, `cos`, and `acos` toward negative
and positive infinity. The [versioned MPFR 4.2.2 rounding contract](https://www.mpfr.org/mpfr-4.2.2/mpfr.html#Rounding)
and [function definitions](https://www.mpfr.org/mpfr-4.2.2/mpfr.html#Transcendental-Functions)
specify correctly rounded directed endpoints. The exact result lies between
those high-precision endpoints.

For sine and cosine, the approved limit is absolute `2u = 2^-52`.
The oracle rounds `observed - 2u` upward and `observed + 2u` downward
at 320 bits. It accepts only when the complete MPFR enclosure lies between
those inward thresholds. This proves the target's distance from the real
result is no more than the approved limit. It also rejects a zero whose sign
differs from the real function, even when its magnitude meets `2u`.
Zero-angle sine and cosine follow the exact source special cases.

The `2u` decision covers sine and cosine, not `acos`. The pinned Java
[Math.acos contract](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Math.html#acos(double))
requires an answer within one ulp of the exact value and positive zero at
input one. The Math class defines one ulp of a nonrepresentable real result
as the distance between its two bracketing binary64 values. The oracle
requires its directed binary64 `acos` endpoints to coincide or be adjacent.
For adjacent endpoints, their separation is the local one-ulp error limit.
For an exact representable result, it uses that result's binary64 ulp.
It compares the candidate against the 320-bit directed MPFR enclosure with
this limit. It does not use the larger endpoint's ulp across a power-of-two
boundary. An unresolved bracket returns `UNPASSED`.

This distance check retains values permitted near either side of 1.0,
including a candidate in the smaller binade when the exact value is above
1.0. It rejects a candidate more than one local ulp below an exact value
under 1.0. The source's sine-sign branch and `acos(1)` zero case are checked
separately. This is a per-call source accuracy check. Each Kotlin runtime's
inverse-trig behavior and the Java contract's semi-monotonicity still need
executed evidence.

A rational Taylor remainder independently checks the sine enclosure and
the `2u` boundary at 0.75 radians. Tests cover small and large arguments,
both zero signs, subnormals, and adverse one-ulp changes.

For each rotate component, the oracle forms both products as exact rational
numbers from the decoded binary64 inputs. It enumerates the correctly
rounded two-product sum and the three possible partial or full fused
evaluations. Exact cancellation and signed-zero rules are applied before
clamp. A raw value outside those discrete results fails even if it lies
within a broad error tolerance. The oracle then checks the exact source
clamp marker, post bits, and target state chain. The pinned
[Transform.rotate](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/geometry/Transform.java#L101-L150)
and [Rotation.rotate](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/geometry/Rotation.java#L601-L655)
give the operand order. The [clamp function](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/geometry/Interval.java#L222-L231)
preserves an in-range signed zero.

For a direct lerp reset, the oracle checks `alpha` in `[0,1]` and derives
the start and end angles from `acos(cost)` with the source's sine-sign rule.
The start pair comes from the previous transform. The end pair equals the
current transform's recorded pre-state. The reset alpha must match the
independently bound accepted call and its trace event time bit for bit.
It reproduces both shortest-angle branches with pinned binary64 pi values,
checks the recorded difference, and checks the strict or fused multiply-add
angle. It then bounds direct `sin` and `cos` and requires post to equal trig
bit for bit. The [source angle accessor](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/geometry/Transform.java#L532-L537)
uses `acos`, despite a nearby lerp comment mentioning `atan2`.
The [direct lerp implementation](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/geometry/Transform.java#L674-L715)
supplies the remaining formula.

## Evidence still required

The focused tests include a halfway binary64 tie, one-ulp adverse changes,
subnormal and signed-zero products, clamp, a strict-versus-FMA case checked
with libc `fma` and 200-digit Decimal, a rational trig cross-check, and
missing/stale identity, call, body-step, reset, and state mutations.
They are synthetic controls. An actual producer has not emitted the full
record and independent receipt for any of the 318 prospective cases.
The owner policy remains under independent review, and the separate merge
owner must keep activation and all target/runtime gates open.
