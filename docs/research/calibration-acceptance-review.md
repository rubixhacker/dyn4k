# Numerical acceptance review packet

For [Define numerical and migration acceptance](https://github.com/rubixhacker/dyn4k/issues/7), based on [Execute the approved baseline calibration experiment](https://github.com/rubixhacker/dyn4k/issues/15).

This packet separates observed baseline behavior, proposed checks and unresolved decisions. It does not approve a numerical reference, tolerance, supported input domain or exception. The original corpus and later supplemental inputs retain separate provenance.

## Findings and proposed disposition

| Finding | Evidence | Proposed treatment for review |
|---|---|---|
| Reproducibility | Two independent JVM repeats have identical full-precision trace/query/summary bytes; source, binary and environment pinned | Retain as one-host reproducibility evidence. Do not infer exact equality on other Kotlin targets. |
| Free motion | 600-second nominal analytic position residuals: x5.425704330264125e−11 m, y2.7128521651320625e−11 m; observed momentum and energy drift0 | Candidate absolute analytic-position limit1e−10 m per component for this exact baseline fixture. No zero cross-target momentum allowance and no general port tolerance inferred. |
| Undamped spring dissipation |45 long undamped runs lose effectively all initial modeled energy; effective stiffness matches the source model | Do not use energy conservation as this baseline's pass condition. Preserve measured energy/trajectory histories as diagnostics pending reference approval. |
| Negative Angle ratio | Accepted ratio−1, limits off: primitive angular velocities overflow at step171, reproduced without recorder. Constraint residual doubles per iteration; signed rotation clamp also fails for large negative rotations | Keep rejected, never convert nonfinite values into a finite reference. Decide explicitly whether baseline adoption permits retaining this known defect or requires a separately versioned correction. Neither choice silently removes the API/input from scope. |
| Rotating-pentagon CCD | All30 ALL-mode cases pass fully below ground despite contact/TOI callbacks; independent vertex-extrema probe confirms passage | Keep failed physical containment distinct from successful callback execution. Review baseline-defect handling before freezing any “CCD works” reference or promise. |
| Stack sleep/wake | All15 30Hz variants fail to reach sleeping top body at the300s action; extreme trajectories leave the finite floor | Keep the failed wake prerequisite visible. Do not enlarge trajectory tolerances to hide an escaped stack. A changed stable wake fixture must be recorded as an additional input. |
| Geometry representability | Six translated tiny triangles are rejected;86 discrete result-field differences across transforms | Preserve actual rounded vertices and rejection observations. These grids are experimental probes, not supported-range promises. |
| Large force/torque caps | Enabled high caps can remain below saturation under their current drive | Treat them as nonbinding controls. Use separate driven cap-transition evidence for the binding branch; do not label a nonbinding observation a solver failure. |
| Supplemental Weld/Pulley residuals | Enabled Weld equal limits have angle approximately[−0.00144567,+0.000612573]rad; enabled Pulley slack transition also stretches0.1208278905m beyond target | Preserve active-mode evidence and imperfect constraint outcomes separately. Do not silently adopt these maxima as tolerances. |

The [remaining joint experiment](interaction-results.md) executes the identified combined, valid-range, enabled-equal and driven-transition gaps with controls. Its25 continuations have two identical full-precision repeats. The bounded mode inventory has no further identified unexecuted family; original inactive observations and failed physical prerequisites remain visible.

### Spring-energy source check

The pinned [DistanceJoint documentation](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/dynamics/joint/DistanceJoint.java#L54-L65) explicitly identifies energy loss with the damper disabled as intended solver behavior. Its spring constraint computes impulse mixing/error reduction and a softened effective mass at [initialization](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/dynamics/joint/DistanceJoint.java#L377-L400), then uses those terms in the velocity solve. Therefore “undamped” in this API is not a promise of energy-conserving integration. This source finding explains the broad dissipation observation; it does not independently validate every sampled trajectory or justify a new numerical bound.

## Reference and tolerance boundary

No Kotlin port exists in this experiment, so there are no measured port-versus-baseline errors from which to claim a validated cross-target absolute/relative tolerance. Scale/origin/timestep sensitivity describes different baseline inputs, not implementation parity. In particular the25,505m stack divergence is not a defensible port tolerance.

Reference candidates must retain baseline revision, exact inputs/action schedules, fixed coordinate origin, timestep, raw state/event identity and the classification of rejected or unstable observations. New fixture supplements are additions, not replacements for inconvenient original cases. Known-defect exceptions require a recorded human decision; a successful archive transfer does not approve its contents as references.

## Review order

1. Review the complete experiment coverage and publication evidence, including remaining failed physical prerequisites.
2. Decide baseline-defect handling, beginning with the negative Angle ratio. The concrete alternatives are to retain an explicitly classified rejection in the baseline contract, or to require a separately approved corrected baseline/version before finite parity can be claimed for that input. Recommendation: preserve the rejection and keep finite-reference eligibility unresolved until this policy is decided; never fabricate a finite answer.
3. Review the proposed free-motion check and choose how source-intended spring dissipation is represented in physical diagnostics.
4. Approve reference eligibility and a process for deriving/validating cross-target tolerances during actual port verification. This experiment alone cannot supply that future evidence.
