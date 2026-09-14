# Combined-joint exploratory input bindings

These are **new experimental inputs**, authorized by the instruction to define and run the remaining combined fixtures. They are not original upstream U cases, frozen references, or approval of acceptance tolerances. Original `P-J-*` and `P-JCP-*` rows remain unchanged, including the rejected signed Distance range.

Baseline source: dyn4j 6.0.0 `058bf6d982a0fb89b54050f929f6ea9dae53b714`. The final suite has 25 independent continuations, each 600 steps at 1/60 s, scale1 and origin(0,0), plus three captured source-preparation steps for the Pulley transition. The sections below preserve the concrete input declarations made before each capture as the requested scope expanded. All input state/settings and step actions are captured at full precision. No unrecorded preparation or state reset.

## Declared inputs before first capture

Common source body setup: infinite-mass rectangle10×0.5 at(0,0); dynamic circle radius.5 at(0,2), density from pinned defaults, friction0, zero linear/angular damping, default remaining fixture/body/world settings. Both bodies are added in that order.

- **Prismatic** uses `PrismaticJointSimulationTest.springOnly` geometry, zero gravity, anchor at dynamic centre, axis(1,0), rest offset2, spring8Hz with damper.2. New combined configuration: enabled spring cap10N, enabled motor cap1000N, motor speed+1m/s, enabled limits[-1,1]m. Before continuation steps201/401 change motor speed to-1/+1 respectively. The deliberately stronger motor crosses both bounds against the spring, while the spring remains driven by its rest offset.
- **Wheel** uses `WheelJointSimulationTest.springDamperWithLimits` geometry, default gravity(0,-9.8), anchor at dynamic centre, vertical axis(0,1), and pinned default spring/damper values. New combined configuration: enabled spring cap10N, enabled motor torque cap.25Nm, motor speed+pi/2 rad/s, enabled limits[-1,5]m. Before201 set linear limits[1,5], then motor speed-pi/2; before401 set limits[-1,-.5], then motor speed+pi/2. These limit bands are source-derived. The angular motor cannot drive the linear limit coordinate; the displaced limit bands deliberately exercise the axial solver alongside the spring and motor.
- **Distance** uses complete `DistanceJointSimulationTest.upperLimitWithSpring` initial setup: zero gravity, anchors at body centres, rest distance10m, enabled valid nonnegative limits[1,5]m, spring8Hz, damper.2, pinned default spring-cap state/settings. This accepted source range supplements the retained signed-range API rejection; it does not replace it. No step mutations.

Prismatic/Wheel each have a combined row plus three one-feature-disabled controls: `spring-off`, `motor-off`, `limits-off`. Controls keep all other inputs/actions identical. Limit-shift actions use `setLimits` without enabling limits, so the limits-off control stays off. Distance has a combined spring+limits row and spring-off control. Mode disabling happens before the initial snapshot.

## Coverage observations to require

Finite traces are necessary but insufficient. On the combined rows, inspect simultaneous nonzero spring and motor outputs plus a limit-force contribution at a bound. For the fixed unrotated ground, Prismatic limit contribution is reaction.x minus spring force minus motor force; Wheel is reaction.y minus spring force. Check both lower and upper gap against the recorded solver tolerance only as an exploratory activation classifier, not a proposed acceptance bound. Capture signed outputs, enabled cap values, and control differences. A configured cap without a nonzero force/torque at that cap is not saturation evidence. If a scheduled direction switch changes a mode after another mode has settled, report the actual overlap rather than merging disjoint maxima.

## Declared bounded extension before its capture

The follow-up instruction expands the suite to **15 rows**. Add a second valid Distance pair with rest distance1 (from `lowerLimitWithSpring`) and the new common range[1,5]; its underdamped approach from initial distance2 is an experiment intended to reach the lower bound, not a verbatim U setup. The original upper pair keeps its existing IDs; the lower pair uses `valid-1-to-5-lower-*`.

Three `cap-transition` rows deliberately re-excite the existing simulated state at201, then disable the cap at401:

- Distance: source `springOnly` zero-gravity setup, rest3, spring8/.2; configure source cap200N but start disabled. Before201 set cap enabled, then rest distance10; before401 disable cap. This uses the earlier source rest-distance magnitudes without resetting either body.
- Weld: source `softConstraint` rectangle1×.5 dynamic body, left-offset anchor, spring8/.3/default gravity; configure source torque cap5Nm but start disabled. Before201 enable cap, then apply source force(0,-10) at world(.5,2); before401 disable cap. The world has evolved for200 steps before the fresh force.
- Wheel: source vertical default spring/damper/default gravity and limits[-1,5]; configure source force cap200N but start disabled. Before201 enable cap, then set source limits[-1,-.5]; before401 disable cap. The limit shift creates axial displacement and subsequent spring demand.

These three new stimuli are experimental changes, explicitly distinct from the older upstream-checkpoint toggles. Required observation: saturation during the enabled201–400 phase with nonzero demand; zero output at a disabled/zero cap never counts as saturation. No source checkpoint state is copied or reset.

## Final transition extension before capture

Final bounded suite: **19 rows**. Three new motor-cap-transition rows use source motor-enabled setups (Prismatic horizontal axis, Revolute centre pivot/angularTolerance0, Wheel motorOnly axis(-1,0); all zero gravity). Configure low caps10N for Prismatic and.25Nm for Revolute/Wheel, initially disabled. Speeds initially+1m/s or+pi/2rad/s. Before201 enable cap then reverse speed to negative; before401 disable cap then reverse positive. The reversal supplies a finite acceleration demand in the enabled phase. These are new experimental parameter choices from the candidate grids, not exact U method clones.

Prismatic spring-cap-transition uses the source springOnly geometry/zero gravity, spring8Hz/.2, rest offset+2 and cap10N initially disabled. Before201 enable cap then change rest offset to-2; before401 disable cap. The negative rest offset is an explicit new signed stimulus under the instruction to complete the missing experiments. No state reset. Required evidence is an actual saturated sample during201–400, with config/cap/force recorded together.

## Final missing-mode rows declared before capture

Final bounded suite: **25 continuations**. Four `enabled-equal` rows set both limits to0 and explicitly enable them. Distance uses the initial fixedDistance source geometry/rest10 with its explicit10 position iterations (initial separation2 drives correction). Prismatic uses source motor geometry with enabled motor1m/s/cap10N; Revolute uses source motor geometry/angularTolerance0 with enabled motor pi/2rad/s/cap.25Nm; their initial zero coordinate plus nonzero motor demand tests the constrained equal-limit branch. Weld uses source softConstraint left-offset anchor/spring8Hz/.3/default gravity, equal limits enabled and the source off-centre force(0,-10) at(.5,2) applied before the first step. These new enabled rows supplement the preserved old disabled-limit rows.

Weld `spring-enable-transition` uses source softConstraint geometry and modes but spring initially disabled. Before201 enable spring and apply the source off-centre force(0,-10) at(.5,2); before401 disable spring. This adds an explicit drive to the previously dormant spring-enable transition.

Pulley `slack-transition` reconstructs the exact three-body `withAndWithoutSlack` source state after step1, velocity(0,10) on body2, then step2; all three preparation steps are captured in separate preparation segments and the same objects continue. Slack remains false initially. Before201 set body2 velocity(0,10), translate body2(0,.1), then enable slack in source order; before401 disable slack. No state copy or reset. Observe actual rope length below target during enabled phase and tension after disabling; configuration changes alone are insufficient.

## Focused observed results

The final focused capture at `/tmp/interactions/fourth` completed all25 continuations plus both Pulley preparation segments: 27 segments,15,003 steps, no non-finite/rejected status. The source file SHA-256 is `68dab71cdc51742c6b6e35048bb3fb5787be31837555f0b57a4f3fab53058403`. Parent-owned integrated repeats and final reports remain the publication artifact; these temporary checks are implementation evidence.

Independent analysis of the unchanged first19 row definitions found genuine same-step combined activation:

| Row/bound | Step | Coordinate | Spring output | Motor output | Limit-force residual |
|---|---:|---:|---:|---:|---:|
| Prismatic upper |61|1|10N|225.6194N|-282.7433N|
| Prismatic lower |324|-1|10N|-245.6194N|282.7433N|
| Wheel lower |202|1|-10N|-.25Nm|17.6969N|
| Wheel upper |416|-.5|10N|.25Nm|-10.9182N|

Residuals use the actual signed per-step reaction projected on the fixed source axis, subtracting the spring and (for Prismatic) motor components. Values are rounded here for readability; raw traces retain full precision. All seven new cap-transition probes reached their positive enabled caps during steps201–400. The valid Distance lower combined row reached distance1 at step3 with spring force195.4077N; its spring-off control remained at distance2. This distinguishes active correction from merely setting a valid range.

Independent checks of the final six rows confirmed the equal-limit and transition branches without treating the baseline as exact physics:

- Distance equal limits corrected initial separation2 to0 at step1. Prismatic stayed exactly0 under motor force10N; Revolute stayed exactly0 under motor torque.25Nm.
- Weld equal limits produced spring torque1.08297Nm and reaction torque11.14438Nm at step1, but its measured angle ranged from-.00144567 to+.000612573rad. This is active constraint evidence, not a perfect-lock claim or approval of that residual.
- Weld spring-enable transition produced maximum spring torque3.04550236Nm during201–400, with zero spring torque in the disabled phases.
- Pulley enabled-phase length-minus-target ranged from-.7061984767 to+.1208278905m, demonstrating genuine slack but also positive stretch that must remain visible in baseline review. After disabling at401 its range was-.0003322561 to0m. Do not discard the stretch discrepancy or silently convert it into an accepted tolerance.

The independent source review found no dimension, action-order or state-reset defect in these new rows. Baseline residuals and known divergent inputs remain findings requiring explicit acceptance decisions; the completed execution/activation evidence does not itself ratify numerical bounds.
