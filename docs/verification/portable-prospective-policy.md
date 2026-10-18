# Prospective portable numerical policy

Status: **ADOPTED, TARGET QUALIFICATION UNPASSED**. The delegated choice was
[recorded before implementation](https://github.com/rubixhacker/dyn4k/issues/7#issuecomment-6244397193).
This document covers 318 cases outside the 14 frozen comparisons. The
machine-readable [catalog](../../tools/numerical/portable/prospective_policy_catalog.json)
binds every case to its pinned reference SHA-256 and every observed record leaf
to an adopted rule. An exact match alone is a diagnostic, and no target has
been qualified by this policy.

## Reference and inventory

The reference is the verified dyn4j 6.0.0 capture at
`/var/tmp/dyn4k-portable-baseline-247e15eb/verified.json`. It records source
`058bf6d982a0fb89b54050f929f6ea9dae53b714`, JAR SHA-256
`204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e`,
fixture source SHA-256
`70d7c4105224f570d5e4cef1cf9f488c4007aeb68a536dda76f9836bdfdd2b4f`,
and trace SHA-256
`f31dc4a0a63e96a7212a58df02c7f1be539756532603e5f5b51e528dd7b84d07`.
The catalog was made by reading every record of each of the 318 case slices,
not by sampling the first state. It contains 566 distinct leaf paths, 92
distinct case path sets, and 67,667 case-path memberships. Array positions are
written `[]`; ordered array length and contents remain comparison inputs.

| Algorithm and physical meaning | Cases | Distinct paths | Required channels |
| --- | ---: | ---: | --- |
| Geometry boundaries: GJK/SAT overlap, separation, scale and translated origin | 75 | 256 | Input, setup, observations, contact/TOI event, body state |
| Free motion: applied force, damping, restitution and contact response | 10 | 277 | Input, 60 force actions, body state, contact and TOI events |
| Ten joint solvers: limits, springs, motors, friction, ratios and transitions | 221 | 422 | Input, mode actions, two body states, joint mode and reaction |
| Continuous detection: circle/pentagon, ALL/NONE, 30/60/120 Hz | 12 | 270 | Input, body state, contact and TOI events |

The joint count is Angle 11 plus one known failed physical Angle case,
Distance 30, Friction 8, Motor 11, Pin 25, Prismatic 42, Pulley 8,
Revolute 19, Weld 24, and Wheel 42. The explicit case IDs, steps, profile,
reference hashes and path-set indexes are in `cases` in the catalog.
`path_sets` and `paths` provide the complete case-to-path inventory.
Observed event names, including actions, are encoded in the path prefixes.
The 14 frozen cases are absent by design and keep their existing policies.

The baseline reports `P-J-Angle-ratio-limits-off--1.0` as
`FAILED_PHYSICAL`: energy first becomes nonfinite at step 87 and angular
velocity at step 171. Its 14 tagged nonfinite path forms remain inventoried,
but `reject_nonfinite` cannot become a parity pass. The default sleep/wake
represented-geometry failure, 125,847 of 126,000 samples, also remains failed
under its separate frozen policy. An exact diagnostic is never qualification.

## Adopted rules

The catalog maps each of the 566 paths to one of the rules below. Values are
adopted engineering choices. They come from solver scales and the stated
physical meaning, not candidate differences. No dyn4j source line promises
cross-platform error below these values. The [default settings](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/dynamics/Settings.java#L73-L102)
set six velocity iterations, two position iterations, 0.005 m linear
tolerance and 2 degrees angular tolerance. The adopted general position
budget is **5e-6 m**, one thousandth of that linear tolerance; the angular
budget is **3.490658503988659e-5 rad**, one thousandth of 2 degrees. These
are comparison budgets, never permission to fail an independent physical
check.

| Catalog rule | Adopted comparison or invariant |
| --- | --- |
| `exact_input` | Match the complete input and setup record as binary64 or exact structural values, including the explicit negative-zero token. |
| `exact_structure` | Match case IDs, kinds, array lengths, integer indexes, action names/steps, event order and completion counts exactly. Boolean contact/TOI branches must agree. |
| `exact_configuration` | Match joint mode and gravity values to their specified input or action at every state. Use finite binary64 identity for configured numbers. The moving joint anchor uses `bounded_position`. |
| `exact_step` | Require finite binary64 `1/hz` in each step callback and the declared step count. |
| `reject_nonfinite` | Reject a new NaN or infinity. Retain the known Angle reference failure separately as failed physical behavior. |
| `bounded_position`, `bounded_velocity`, `bounded_angular_velocity` | Bound each position component by 5e-6 m, each velocity by 5e-6/`dt` m/s and angular velocity by 3.490658503988659e-5/`dt` rad/s. For the ten free-motion cases, use 2e-9 m and 2e-7 rad with the same `dt` propagation. Boundary geometry positions use the tighter represented-gap rule below. |
| `derived_transform`, `derived_rotation` | First check each run's translation aliases and matrix `[c,-s,x,s,c,y]`; check `c²+s²` against 1 with 32 binary64 ulps and wrapped angle against `acos(c)` with sign from `s`. Then use the position/angular budgets across runs; compare angles modulo 2π. |
| `bounded_geometry_distance`, `bounded_contact_depth` | Require exact detected/separated branches. Use 1.0536712127723509e-8 m for ordinary GJK distance and 5e-6 m for dynamic contact depth. Boundary cases use the smaller of 8 ulps at the represented coordinate and one quarter of the nonzero represented gap. Zero gap uses the 8-ulp term. |
| `bounded_direction` | Require the same normal orientation and at most 3.490658503988659e-5 Euclidean component error; independently check unit length within 32 ulps where a normal is defined. |
| `bounded_toi_distance`, `bounded_toi_time` | Require the same callback sequence, finite distance within 4.806217383937352e-6 m, and normalized impact time within `min(0.001, 4.806217383937352e-6 / represented_sweep_distance_m)`. Require time in [0,1]. |
| `bounded_impulse`, `bounded_force`, `bounded_torque` | Derive component caps from the state budget: `m_eff*epsilon_x/dt` N·s, `m_eff*epsilon_x/dt²` N, and `I_eff*epsilon_angle/dt²` N·m. Use mass/inertia from exact setup, and the sum for a two-body reaction. |
| `derived_momentum`, `derived_energy` | Check each run against its own `m*v`, angular momentum about center, and `½m|v|²+½Iω²` first. Propagate both allowed velocity-component errors and the angular error through those formulas, with rounding in the derived quantity's units. |

There are no observed paths assigned to the catalog's `bounded_scalar`
sentinel. An added path must receive an explicit rule. Finite zero is a
separate condition: body force and torque without an applied source, and the
Angle joint's zero reaction force, require finite numerical zero before a
force tolerance. Computed and alias finite zero accepts either sign. Explicit
signed zero in input and setup remains exact. Finite configured numbers accept
equivalent JSON number spellings such as `60` and `60.0`.

These formulas follow the [body's symplectic Euler velocity update and
position integration](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/dynamics/AbstractPhysicsBody.java#L726-L827).
The transform getters and matrix order come from
[Transform.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/geometry/Transform.java#L515-L535)
and its [value array](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/geometry/Transform.java#L595-L604).
[GJK](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/collision/narrowphase/Gjk.java#L270-L304)
uses a support-point sign test; [SAT](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/collision/narrowphase/Sat.java#L78-L114)
tests interval overlap. Thus geometry branch identity is more important than
a permissive depth tolerance. The GJK default distance epsilon is
[`sqrt(Epsilon.E)`](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/collision/narrowphase/Gjk.java#L134-L144).
[Conservative advancement](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/collision/continuous/ConservativeAdvancement.java#L103-L203)
iterates on separation, with [`cbrt(Epsilon.E)`](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/collision/continuous/ConservativeAdvancement.java#L48-L62)
as its default distance stop. These are source facts; the factors above are
adopted comparison budgets.

Joint trajectories follow ten separate pinned solvers:
[Angle](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/dynamics/joint/AngleJoint.java#L335-L391),
[Distance](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/dynamics/joint/DistanceJoint.java#L431-L550),
[Friction](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/dynamics/joint/FrictionJoint.java#L245-L305),
[Motor](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/dynamics/joint/MotorJoint.java#L287-L348),
[Pin](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/dynamics/joint/PinJoint.java#L332-L398),
[Prismatic](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/dynamics/joint/PrismaticJoint.java#L586-L735),
[Pulley](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/dynamics/joint/PulleyJoint.java#L344-L386),
[Revolute](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/dynamics/joint/RevoluteJoint.java#L426-L515),
[Weld](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/dynamics/joint/WeldJoint.java#L487-L595),
and [Wheel](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/dynamics/joint/WheelJoint.java#L566-L706).
Their mode changes and limit branches must agree exactly before comparing
bounded state values. The pinned Angle code explicitly permits negative ratios
but its velocity update uses both ratio and sign
([AngleJoint.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/dynamics/joint/AngleJoint.java#L378-L390)).
That source behavior supports retaining the failed physical case as evidence,
not granting it a nonfinite exception.

## Implementation and adverse controls

For each target and build configuration, require the declared 332-case receipt,
actual runtime executable, artifact hashes, case/trace hashes, input bytes,
source revision, event order, every state and all case ends. Verify the pinned
reference hash and catalog path set for each prospective case. A changed input,
unexpected path, missing step, extra callback, stale receipt or incomplete
suite fails before any tolerance. [TimeStep.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/dynamics/TimeStep.java#L58-L97)
sets the step fields and ratio used by the callback premise.

The comparator checks the adopted rule and path map digest, all 318 catalog
entries, the pinned source, fixture, JAR, trace and per-case hashes, actual
candidate source and artifact hashes, runtime executable and 15 method logs,
the sealed 332-case receipt, case slices, and producer and receipt inventory.
Before a target case receives `PASSED_CASE_POLICY`, the host comparator also
requires `numeric-probe-receipt.json` from that same lane. The receipt binds
the candidate commit, source archive and trace hashes, staged artifact hashes, executed
runtime identity and executable hash, and archived XML and Gradle log hashes
for `geometryCollisionBoundaryAndScale`. The XML must report one successful
execution of that method and contain exactly one target-emitted
`NUMERICAL_PROBE_JSON` record. Its exact binary64 bit patterns cover spacing
around 1, signed zero and its reciprocal, spacing at 1e6 m, and represented
geometry gaps at zero and both signed 1e6 m origins. The record also checks
finite classification for the largest finite value, infinity and NaN. The
three classifications must be JSON Booleans in both the raw marker and the
receipt; JSON numbers are rejected even when Python would compare them equal.
The XML's existing `NUMERICAL_JSON` input record must carry an explicit negative
zero through the recorder. Missing probe evidence leaves every otherwise
passing target case `UNPASSED`; a present but stale or contradictory receipt
is rejected. A self-authored XML marker and receipt only establish archive
consistency, not target execution. The current matrix test and host runner do
not emit this marker and receipt, and no executed test payload or classpath is
bound to it. Producer verification is therefore unavailable and the comparator
keeps the case-pass gate closed: even a consistent synthetic archive leaves
case qualification `UNPASSED` and records
`UNPASSED_UNBOUND_PRODUCER`. Target qualification requires a reviewed producer,
its executed payload, and independently checked raw process evidence.
It checks the target's decoded boundary setup against the input expression
`origin.x + scale*(1.5 + delta)` from the
[portable fixture](../../tools/numerical/portable/src/commonTest/kotlin/portable/PortableMatrixTest.kt),
including the represented zero-gap condition. A 1e-12 m perturbation that
rounds away at a 1e6 m origin stays `UNPASSED_PREMISE`. The TOI time bound
uses the represented per-step sweep. Joint modes are checked against setup
and the recorded action before comparison. Transform aliases, the matrix,
rotation sum, momentum, energy, event order, branch identity and finite zero
are checked before bounded parity. The public case seam keeps
`qualification: UNPASSED`; only the host path with verified identity may mark
an individual case `PASSED_CASE_POLICY`.

Unit controls exercise every distinct numeric rule inside, at, and beyond its
bound; free-motion caps, geometry represented gaps, TOI time range, normal
orientation and unit length, 32-ulp transform checks, mode changes, branch
flips, explicit input negative zero, computed zero, NaN/infinity, missing and
extra cases/paths/receipts, and stale source, artifact, runtime, fixture and
trace identities. The target's own trace demonstrates its serialized binary64
values and represented geometry. The exact-runtime `nextafter` receipt
contract is enforced, but no target execution has supplied it. The 318 cases
do not cover exception parity generally, so
a separate error suite remains necessary.

## Reference self-check and remaining work

Applying the adopted comparator to each pinned reference slice against itself
gave 272 within policy, 41 `FAILED_DERIVED`, four `UNPASSED_PREMISE`, and one
`FAILED_PHYSICAL`. All 41 derived failures are the adopted
`c²+s²` within 32 ulps invariant on joint trajectories. Disabling only that
check in a read-only diagnostic raised the within-policy count to 313; the
adopted check remains enabled. The four boundary cases have nonzero declared
deltas that round to zero in their represented setup. These source self-checks
are controls, not target comparisons or qualifications. The Angle failure and
the separate default sleep/wake failure remain failed.

The coordinator must resolve the 41 source-positive-control conflicts on the
[numerical acceptance ticket](https://github.com/rubixhacker/dyn4k/issues/7)
before those cases can pass this policy. The 14 frozen replay and seven-host
runtime qualification remain separate evidence. No target comparison was run
for this document.
