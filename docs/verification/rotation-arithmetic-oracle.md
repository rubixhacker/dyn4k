# Independent rotation arithmetic oracle

## Result and boundary

`tools/numerical/portable/rotation_oracle.py` checks one executed
`portable-rotation-audit/1` payload against the pinned source operations.
It does not activate the conditional `U(N)` policy or qualify a target.
The caller must supply an independently captured call manifest, complete
body-step receipts, a process receipt, and the exact observed bytes.
The API reports `UNPASSED` when binding evidence is missing.

The four geometry premises remain `UNPASSED_PREMISE`:
`geometry-boundary-s1-o3-d1`, `geometry-boundary-s1-o3-d3`,
`geometry-boundary-s1-o4-d1`, and `geometry-boundary-s1-o4-d3`.
`P-J-Angle-ratio-limits-off--1.0` remains a separate physical failure.
The default sleep/wake represented-geometry gate remains failed at
125,847 of 126,000 states. No result here changes an approved bound.

## Public API and producer contract

Call `verify_rotation_arithmetic(audit, case, header, states, rotation_cap,
binding=..., trace_bytes=..., payload_bytes=..., receipt_bytes=...,
artifact_bytes=..., source_bytes=...)` from an external runner. The audit
uses the existing exact binary64 hex fields and source revision. `case`,
`header`, and `states` are the independently captured target case and trace.
The runner must retain the raw files and supply bytes from that run.

`binding` requires `producer_process`, `producer_command`, `runtime_id`,
`artifact_sha256`, `target_source_sha256`, `operation_source_revision`,
`trace_sha256`, `payload_sha256`, `audit_sha256`, `receipt_sha256`,
`manifest_sha256`,
`expected_calls`, `body_step_receipts`, `accepted_toi_resets`,
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
`reset_start_rotations` maps call sequences to the body's previous transform
rotation. `reset_end_rotations` maps them to its current rotation before the
reset. Both values use `[cos_bits, sin_bits]`.
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
It passes the exact angle to GNU MPFR at 320-bit precision. MPFR evaluates
`sin`, `cos`, and `acos` once toward negative infinity and once toward
positive infinity. Each endpoint is then converted to binary64 in the same
direction. MPFR specifies correctly rounded results for these functions
and directed conversion, so each final pair encloses the exact real value,
including subnormal outputs and signed zero. This is an enclosure, not a
claim that the target math library always rounds to nearest.
[MPFR rounding contract](https://www.mpfr.org/mpfr-current/mpfr.html#Rounding)
and [transcendental functions](https://www.mpfr.org/mpfr-current/mpfr.html#Transcendental-Functions)
are the primary source. A rational Taylor remainder independently checks
the sine enclosure at 0.75 radians. The tests also exercise small, large,
negative, positive, and signed-zero arguments.

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
current transform's recorded pre-state.
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
