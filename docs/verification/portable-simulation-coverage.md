# Portable simulation coverage

This corpus ports the 34 expanded `org.dyn4j.simulation.*SimulationTest` cases from dyn4j 6.0.0 at `058bf6d982a0fb89b54050f929f6ea9dae53b714`. The source cases and common Kotlin cases use the same public `org.dyn4j` world, body, joint, force, and torque interfaces. Each Kotlin class keeps the upstream BSD notice. No production source or build registration changes are part of this slice.

The paired Kotlin methods retain the original setup, `step` calls, state changes, and expected values. They live under `dyn4k-core/src/commonTest/kotlin/org/dyn4j/coverage/simulation/`. The descriptions below identify the observed behavior. Step schedules list consecutive `World.step(n)` calls; a call inside a loop is marked separately. The exact baseline numbers and tolerances remain in the test code.

| Pinned Java case and Kotlin counterpart | Step schedule | Setup, change, and checked behavior |
| --- | --- | --- |
| `AngleJointSimulationTest.simpleLinkage` | 1, 1, 1 | Two equal circles without gravity; an initial -30 deg/s rotation splits between bodies, then ratio 0.5 acts after limits are disabled. Checks both angular speeds and reaction force/torque. |
| `AngleJointSimulationTest.withLimitsHitUpper` | 40, 40 | Fixed circle and moving circle at 2 m, +30 deg/s, with +/-30 deg angular limits. Checks normal motion and zero speed after the upper limit. |
| `AngleJointSimulationTest.withLimitsHitLower` | 40, 40 | Same bodies and limits with -30 deg/s. Checks normal motion and zero speed after the lower limit. |
| `DistanceJointSimulationTest.fixedDistance` | 4 | A fixed 10 m by 0.5 m rectangle and 0.5 m circle start 2 m apart. Rest distance is 10 m, correction is 0.2 m, and ten position iterations run. Checks final separation and zero reaction/spring force. |
| `DistanceJointSimulationTest.limits` | 1, 1, 1, 1, 1 | Same bodies without gravity; change [1,5], [6,7], [1,3], then disable lower and upper limits. Checks separation at each stage. |
| `DistanceJointSimulationTest.upperLimitWithSpring` | 10 | Same bodies; rest 10 m, limits [1,5] m, 8 Hz spring, damping ratio 0.2. Checks the 5 m upper bound. |
| `DistanceJointSimulationTest.lowerLimitWithSpring` | 10 | Same bodies; rest 1 m, limits [3,5] m, same damped spring. Checks the 3 m lower bound. |
| `DistanceJointSimulationTest.limitsWithSpring` | 30 | Same bodies; rest 3 m inside [1,5] m, same damped spring. Checks 3 m separation. |
| `DistanceJointSimulationTest.springOnly` | 30 | Same bodies; rest 3 m without limits, same damped spring. Checks separation and reaction force/torque. |
| `DistanceJointSimulationTest.springWithMaxForce` | 1, 1 | Same bodies; rest 3 m, damped spring capped at 200 N, then limits [0,4] m. Checks motion and capped spring/reaction forces at both steps. |
| `ForceSimulationTest.applyTimed` | 1, 1 | Dynamic 1 m radius circle under default gravity; a 1 N horizontal `Force` completes after 2/60 s. Checks accumulated force is 1 N, then 0 N. |
| `FrictionJointSimulationTest.simulationWithLargeForceTorqueMaximums` | 1, 1 | Fixed rectangle and moving circle without gravity; initial velocity (4,3) m/s and 30 deg/s, caps 1000 N and 1000 N m. Checks slowing, initial reaction, and zero reaction on the next step. |
| `FrictionJointSimulationTest.simulationWithLowForceTorqueMaximums` | 1, then 12 x 1, then 11 x 1 | Same bodies and speeds; caps 10 N and 0.25 N m. Checks first capped reactions, then angular and linear rest after their separate step counts. |
| `MotorJointSimulationTest.simple` | 25, 5, 20 | Fixed and moving circles without gravity; target (0,3) m and 30 deg. Zero force/torque caps hold pose; 100 N and 10 N m caps then move toward target. Checks intermediate reaction and final pose. |
| `PinJointSimulationTest.fixedLinearVelocity` | 1 | Circle with fixed linear velocity and pin at (0.5,0) m; target (0.7,0.5) m. Checks reaction and spring forces, rotation, and zero reaction torque. |
| `PinJointSimulationTest.noSpringDamper` | 30 | Dynamic circle pinned at origin, target (0.7,0.5) m; spring, damper, and spring-force cap disabled. Checks correction force and final center, with zero spring force/torque. |
| `PrismaticJointSimulationTest.noLimitsNoMotor` | 4, 4, 4, 1 | Fixed rectangle and circle at 2 m under gravity; slide axis (1,0), changed linear velocities, then applied 30 deg torque. Checks constrained position, rotation and reaction. |
| `PrismaticJointSimulationTest.limits` | 1, 1, 1 | Same bodies without gravity; limits and +/-16 m/s impulses change between steps. Checks limit positions and reaction force. |
| `PrismaticJointSimulationTest.motorWithAndWithoutLimits` | 1, 1, 10, 1, 10 | Same bodies without gravity; 10 m/s motor with 1000 N cap, then [6,7] m limits and reversed motor. Checks translation, speed, motor force and reaction through each phase. |
| `PrismaticJointSimulationTest.springOnly` | 1 | Same bodies without gravity; damped 8 Hz spring capped at 1000 N. Checks translation, spring force and reaction. |
| `PulleyJointSimulationTest.simpleLinkage` | 1, 1, 10 | Two equal circles under gravity with anchors 1 m above and a 2 m rope; ratios 1, 0.5, then 2. Checks opposite velocities, lengths and reaction forces. |
| `PulleyJointSimulationTest.withAndWithoutSlack` | 1, 2, 1 | Two circles sit above a fixed floor; one starts 0.5 m higher. Drive one upward at 10 m/s, then enable slack and offset it 0.1 m. Checks each body position/velocity and rope length. |
| `RevoluteJointSimulationTest.noLimitsNoMotor` | 4, 4, 4, 1 | Fixed rectangle and circle at 2 m under gravity; change linear velocities, then apply 30 deg torque. Checks fixed center, free rotation and reaction. |
| `RevoluteJointSimulationTest.limits` | 1, 1, 1 | Same bodies without gravity; start +/-30 deg limits, then [10,30] and [-30,5] deg while reversing velocity. Checks angle, angular speed/translation and reaction at each phase. |
| `RevoluteJointSimulationTest.motorWithAndWithoutLimits` | 1, 30, 1, 60 | Same bodies without gravity; 20 deg/s motor with 1000 N m cap, then +/-5 deg limits and reversed motor. Checks limit stops, speeds, translation and torque. |
| `TorqueSimulationTest.applyTimed` | 1, 1 | Dynamic 1 m radius circle under default gravity; a 1 N m `Torque` completes after 2/60 s. Checks accumulated torque is 1 N m, then 0 N m. |
| `WeldJointSimulationTest.standard` | 4, 4, 4, 1 | A fixed 10 m by 0.5 m rectangle holds a dynamic 1 m by 0.5 m rectangle at 2 m. Linear velocities change before torque is applied. Checks fixed center/angle and reaction force/torque. |
| `WeldJointSimulationTest.softConstraint` | 1, 20, 1 | Same bodies with offset anchor, damped 8 Hz spring; cap torque at 5 N m and apply 10 N force off center. Checks angular state and spring/reaction torque and force at each phase. |
| `WeldJointSimulationTest.softConstraintWithLimitsLower` | 50 | Same bodies with left offset anchor, damped spring, +/-0.2 pi rad limits and 1 N m spring cap. Checks lower angle, zero speed, spring and total torque. |
| `WeldJointSimulationTest.softConstraintWithLimitsUpper` | 50 | Same bodies with right offset anchor, same limits/cap and a 10 N off-center force. Checks upper angle, zero speed, spring and total torque. |
| `WheelJointSimulationTest.noLimitsNoMotor` | 4, 4, 4, 1 | Fixed rectangle and circle at 2 m under gravity; horizontal slide axis, changed linear velocities, then applied torque. Checks horizontal travel, fixed height, rotation and reaction. |
| `WheelJointSimulationTest.limitsOnly` | 30, 30, 1, 50, 1 | Same bodies with vertical axis and spring off; change limits and gravity from -9.8 to +98 and back m/s2. Checks displacement at both limits and reaction force. |
| `WheelJointSimulationTest.springDamperWithLimits` | 20, 2, 2, 2 | Same bodies with vertical axis and damped spring; move limits across both sides, then cap spring at 200 N. Checks displacements and spring/reaction forces. |
| `WheelJointSimulationTest.motorOnly` | 1 | Same bodies without gravity; horizontal axis and 90 deg/s motor capped at 10000 N m. Checks angular speed/translation, motor/reaction torque and center. |

## Executed evidence

The pinned baseline and provisional candidate each compiled the 12 unchanged Java sources with JDK 21 and `--release 8`. Their 34 expanded cases passed separately on Java 8 and Java 21. The common Kotlin corpus passed 34/34 on JVM, Linux x64, JS Node, Wasm JS Node, Wasm WASI Node, and Android host. Every lane had the same 34 case identities, no failures, and no skipped cases. The 12 original files and 12 portable classes each contain the same 338 assertions and 86 calls to `World.step`. Loops and their iteration counts are preserved.

A controlled test change set the `MotorJointSimulationTest.simple` motor force cap to 0 N during its active phase. The JVM case failed at the assertion that the moving body had passed 2 m. The cap was restored; the complete JVM suite passed again. This checks that the common test observes motor-driven world movement.

Raw run logs, unchanged Java identities, copied host XML, hashes, and exact commands are in `/tmp/dyn4k-coverage-simulation-result.md` and `/tmp/dyn4k-coverage-simulation-evidence/` on the verification host. These are provisional-source corpus results. The default-profile sleep/wake physical failure and Weld/Pulley parity references remain separate findings. Accepted world source, independent review, full target runtime coverage, physical acceptance, and release qualification remain open.
