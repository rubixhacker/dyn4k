# CCD pentagon passage at the small-scale first cell

Read-only investigation of captured dyn4j 6.0.0 (`058bf6d982a0fb89b54050f929f6ea9dae53b714`) behavior. No baseline, fixture, solver setting or captured reference was changed. The investigation used the debugging skill's competing-hypothesis method: finite-ground edge escape, a centre/radius classification artifact, and passage through the ground following initial contact.

## Finding

For `CCD-world-pentagon-ALL`, scale 0.01, origin (0,0), at both 60 and 120 Hz, the **entire polygon passes below the ground during step 2**, following a successful step-1 TOI and a step-2 contact solve. This is not merely a late endpoint observation: transformed polygon vertices prove the passage. It is not escape around the finite ground ends: ground spans x=[−0.1,0.1] m, whereas projectile centre x is approximately −0.00009 m and its radius is 0.001 m.

Ground y range is [−0.00025,0.00025] m. Polygon initial centre is (0,0.01) m, velocity (0,−1.2) m/s, angular velocity 20 rad/s.

| Hz | Step | Centre x (m) | Centre y (m) | Polygon minimum y (m) | Polygon maximum y (m) | Vertical velocity (m/s) | Angular velocity (rad/s) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 60 | 1 | −3.903072937247692e−13 | 0.0010952796097571888 | 0.00020000000000000085 | 0.002081437109796996 | −1.2 | 20 |
| 60 | 2 | −0.00009177434447466177 | −0.005522672112641305 | −0.006512913875595605 | −0.004639635858013107 | −0.41418454670526694 | 94.24777960769379 |
| 120 | 1 | −3.903072868202838e−13 | 0.0010952796097571883 | 0.00020000000000000042 | 0.0020814371097969955 | −1.2 | 20 |
| 120 | 2 | −0.00007904755027940118 | −0.002090234614765704 | −0.003085385469424766 | −0.001227325844399534 | −0.41418454670526705 | 188.49555921538757 |

Vertex bounds were calculated directly from each input vertex `(vx,vy)` and captured transform as `worldY = vx*sin + vy*cos + translationY`. Thus even the highest actual vertex is below the ground bottom on step 2. Rotation cannot explain this away.

## Ordered evidence and source-supported mechanism

At 60 Hz, step 1 TOI payload reports fraction 0.44273588755885945, separation 2.6390656226093698e−9 m, and near-vertical normal. The body is moved to initial contact, and its incoming linear/angular velocities remain unchanged. Contact begins in step 1 with depth approximately 0.00005 m at x=0.00044550468011598897 m, an off-centre single vertex.

In step 2, preSolve still reports vy=−1.2 and omega=20. The one solved contact has normal impulse 0.0000018683872686534645 N·s and zero tangential impulse. Its postSolve payload reports vy=−0.41418454670526694 and omega=94.24777960769379. Contact ends later in the same step; there are no further TOI payload callbacks. The body continues downward to y=−0.40590106726106656 by step 60. At 120 Hz, the corresponding single impulse is 0.000001868387268653464 N·s; the body continues to y=−0.4093717055416113 by step 120.

The pinned source explicitly supports this sequence:

- [AbstractPhysicsWorld step ordering](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/world/AbstractPhysicsWorld.java#L1274-L1312): solve the existing interaction graph, emit postSolve, then solve TOI, then detect new contacts.
- [Existing contact exclusion](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/world/AbstractPhysicsWorld.java#L1465-L1472): CCD skips a body pair when `isInContact(body1, body2)` is true. The step-1 contact persists in that graph during the step-2 CCD phase; new detection/removal occurs afterward.
- [TOI response](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/world/AbstractPhysicsWorld.java#L1699-L1727): interpolate position to TOI and perform positional correction so discrete collision response occurs next step. The code comments explicitly say this does not conserve time. This explains the retained incoming velocity after the first TOI.
- [Contact impulse application](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/dynamics/contact/SequentialImpulses.java#L76-L92): an off-centre normal impulse changes linear and angular velocities; zero restitution does not require zero centre velocity after a single off-centre contact.
- [Rotation clamp](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/dynamics/AbstractPhysicsBody.java#L789-L823): position integration clamps per-step rotation. Observed angular velocities equal `(π/2)*Hz`, consistent with activation of the retained default maximum rotation.

The trace plus source identify the existing-contact CCD exclusion as a supported explanation for why the remaining downward motion is not intercepted on step 2. This was **not** verified by toggling that branch, instrumenting its internal condition or changing geometry/settings; it is not a claim of a newly isolated general upstream defect or a proposed fix. In particular, the precise sensitivity of single-versus-multiple contact generation to scale and timestep needs its own investigation if an upstream report is desired.

## Why NONE at 120 Hz stays above

With NONE at 120 Hz, the first full discrete step lands the centre at y≈4.34e−20 (inside the ground's slab), rather than near its top. At step 2 the manifold supplies **two** contacts, with depths approximately 0.0009638532 and 0.0011366132 m and normal impulses approximately 1.15059865e−6 and 1.70257090e−6 N·s. The solved velocity is vy≈−8.91e−17 and omega≈−1.46e−13, followed by positional correction upward (centre y≈0.00042531 after step 2). This is a discrete overlap catch with a different manifold, not evidence that disabling CCD is a safer policy.

At ALL 30 Hz, maximum translation clamps initial vy to −0.6 m/s. The first contact occurs at a different orientation (0.29771413070375535 rad); the next solve arrests translation/rotation. This case records 58 solved callbacks and remains above. Therefore the 30 Hz result also does not contradict the observed 60/120 Hz passage.

## Evidence paths and implication

Raw authoritative traces: `calibration/results/final-a/-s0.01-o0.0,0.0-/CCD-world-pentagon-{ALL,NONE}-s0.01-o0.0_0.0-hz{30,60,120}-0.jsonl.gz`. State-only audited copies are under `calibration/results/analysis-first/`; report `/tmp/calibration-first-cell-report.json` supplied initial detection of the outcome. All measurements above were read from these completed traces.

Nonempty TOI and solved-contact callbacks establish activation, **not successful non-tunneling**. These two ALL cases must remain recorded baseline behavior requiring review; they cannot support an approved non-tunneling invariant. No accepted tolerance or baseline exception follows from this investigation.

## Independent recorder-free reproduction

`calibration/src/CcdPassageProbe.java` constructs those same P inputs with `SceneCases.scaleWorld`, then calls `world.step` directly without Capture or listeners. It runs ALL/NONE at 60/120 Hz, reports the first two states and transforms each actual polygon vertex. Compiled only into `/tmp/ccd-passage-probe` against the pinned JAR; active harness classes were not modified. Output retained at `/tmp/ccd-passage-probe/output.txt`.

The ALL states reproduce every displayed centre, velocity, angular velocity and vertex-bound value above exactly, including complete passage on step 2 at both rates. NONE 60 Hz is already entirely below on step 1; NONE 120 Hz overlaps and is arrested on step 2 as described. This excludes the passive recorder/listeners as the cause of these observations. It does not toggle the engine's existing-contact exclusion, so that causal mechanism remains the explicitly qualified source-supported explanation above.
