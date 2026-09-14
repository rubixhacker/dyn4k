# Negative ratio diagnosis and activation audit

Baseline source verified: 058bf6d982a0fb89b54050f929f6ea9dae53b714. Java 25.0.3. No baseline edits, no listeners, reflection or Capture in standalone reproduction. Retained source: calibration/src/NegativeRatioProbe.java.

Two independent default JVM invocations exit 1 at step 171 with both body angular velocities -Infinity and joint reaction torque Infinity; outputs are byte-identical. Public angles at that observation are still finite -pi. The earlier recorder's NaN is downstream derived/serialized state, not the first primitive angular-velocity failure. No claim is made about instruction ordering among overflowing intermediates within that step.

Per-iteration diagnostic calls public initializeConstraints/solveVelocityConstraints without stepping a world: residual C=w1-r*w0 starts -0.5235987755982988 and doubles after each iteration (-1.0471975511965976, -2.0943951023931953, ...). At ratio r=-1 and equal inverse inertia I, axial mass is 1/(2I). AngleJoint.java:382-390 calculates impulse=-C/(2I), then subtracts I*impulse from both velocities. Thus C'=2C instead of zero. Six velocity iterations produce 64x growth per world step. This is observed in world residuals -33.51032163829113, -2144.6605848506324, -137258.27743044047. Relevant mass calculation: lines 288-290. ratio setter lines568-570 rejects only zero, so -1 is accepted.

Warm-start-off diagnostic still fails at171: warm start is not necessary for runaway. Positive ratio diagnostic remains finite600 and has residual0 after first iteration. These controls are explicitly separate from approved reference inputs.

A second source defect leaves this runaway negative rotation unclamped: AbstractPhysicsBody.java:815-822 compares signed rotation > maxRotation rather than magnitude. Runtime step2 negative angular velocities already exceed 1000rad/s and continue growing. This facilitates overflow but does not explain the initial constraint-residual growth.

## Activation audit: distinguish existing U evidence from new P decision

Existing complete U schedules contain many stimuli already; their existence must not be described as no available evidence:
- Angle withLimitsHitUpper/Lower: +/-30deg/s and +/-30deg limits.
- Prismatic limits: velocity -16m/s then +16m/s; motorWithAndWithoutLimits: motor +/-10m/s and changed limits.
- Revolute limits: +/-10deg/s; motorWithAndWithoutLimits: motor +/-20deg/s against +/-5deg limits.
- Pulley withAndWithoutSlack: upward velocity10m/s in both slack states.
- Weld softConstraint: cap5Nm enabled later and force(0,-10) applied at(0.5,2); lower/upper variants have off-centre anchors and cap1Nm.
- Wheel springDamperWithLimits changes limit bands and later enables spring cap200N.
- Distance springWithMaxForce has enabled cap200N from initial setup.

Choosing these complete U schedules needs no new physics invention. However current P field-only rows do not transplant later U actions. Exact remaining binding decisions:
1. Is a compatible U seed permitted to mean a fully serialized source checkpoint after its earlier steps/actions, or only pristine pre-first-step state? If checkpoints are allowed, specify exact method/checkpoint and retain preceding state construction, instead of silently resetting dynamics.
2. For joint limit/interaction P rows, approve explicit source-derived velocity/force/target schedules (and their timing), or select an existing fully active U setup plus already-approved motor/spring parameter combination. Current interaction rows only flip enabling booleans; zero speed/error makes several inactive. Prismatic/Wheel motor+spring+limits has no fully combined U seed, so an exact combination is required.
3. For spring cap grids, permit enabling the cap as a prerequisite to scalar sweeps, then vary only the scalar. Distance has an active pristine springWithMaxForce seed; Weld/Wheel cap activation is later in U. Current isolated cap grids preserve disabled caps in those initial seeds and cannot establish each value's saturation.
4. Motor moving-target/correction probes need nonzero caps. Source simple supplies100N/10Nm only after25steps; approve that checkpoint or the caps as initial P prerequisites. Keeping initial zero caps verifies immobility, not target-following.
5. Distance signed limit grid(-1,1) is API-rejected. Retain rejection and choose an additional valid dynamic range explicitly (e.g. source1..5 or source0..2); don't silently transform signs.
6. Negative Angle ratio is an accepted but divergent baseline input. Keep failure observation; decide whether it blocks baseline adoption until separately repaired/versioned, or is classified as an explicit known-baseline defect outside finite parity references. Do not silently waive or delete it.

No JointCases edits made during this diagnosis. No baseline or approved inputs changed. Temporary files retained solely as requested research evidence; no debugger resources remain.
