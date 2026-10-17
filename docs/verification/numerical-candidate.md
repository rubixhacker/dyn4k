# Candidate numerical capture on staged JVM artifacts

This page describes the candidate recorder for [Run the full compatibility corpus and unchanged migration applications](https://github.com/rubixhacker/dyn4k/issues/42). The exact commit, artifact hashes, commands, and observed trace hashes are in `/tmp/dyn4k-candidate-numerical-result.md`. Candidate numerical acceptance is open.

## Consumer and receipt

`tools/numerical/candidate/` is a Java consumer of the staged `io.github.rubixhacker:dyn4k-core-jvm:0.1.0-alpha.1` artifact. Its Gradle runtime graph check requires that artifact and rejects `org.dyn4j:dyn4j`. Each scene constructs `org.dyn4j.world.World` from the assembled common Kotlin engine. The scene sources adapt the pinned calibration and sleep/wake input recipes. The separate Weld/Pulley physical capture uses the declared physical input. No baseline Java runtime provides the captured world.

The frozen catalog in `tools/numerical/fixtures.json` still controls the 14 accepted trace members. `run.py` requires a clean commit and a staged JAR. It runs one consumer, validates the trace with the approved record parser, seals a receipt, and runs `compare.py` against the matching frozen timestep and member. A trace with extra or missing callbacks has no valid receipt. The raw trace and `run.log` remain available to diagnose failure. The receipt records the Git commit, SHA-256 of `git archive --format=tar HEAD`, staged JAR hash, trace and frozen reference hashes, exact expected and executed counts, Java runtime, host, and candidate build configuration hash. `receipt.py verify` recomputes these identities and rejects stale, missing, or extra receipt fields.

The Java recorder writes `Double.toString` numeric tokens. This preserves `-0.0`. The parser retains its sign and `compare.same_value` checks exact aliases by binary64 bits. A signed zero can compare numerically as zero under an approved numeric rule while still failing an exact same-run alias if its paired getter changes sign. Endpoint records copy the current inner state. They do not call `World.step`, advance event order, or add simulated time.

Use a fresh output path for each run. For example:

```sh
./gradlew --no-daemon :dyn4k-core:publishJvmPublicationToStagingRepository :dyn4k:publishJvmPublicationToStagingRepository
PYTHONDONTWRITEBYTECODE=1 python3 tools/numerical/candidate/run.py --fixture default-sleep-30 --reference /path/to/S-sleep-wake-hz30-0.jsonl.gz --output /tmp/candidate-default-30
PYTHONDONTWRITEBYTECODE=1 python3 tools/numerical/candidate/receipt.py verify --fixture default-sleep-30 --trace /tmp/candidate-default-30/S-sleep-wake-hz30-0.jsonl.gz --receipt /tmp/candidate-default-30/receipt.json
```

`same_run.py` checks candidate body getter and transform aliases, fixed-body callback velocities, instrumented snapshots, and endpoint copies. It reports a local alias result. The complete approved six-group exact-consistency package still needs a candidate-path execution before a full same-run claim. `sleep_physical.py` reuses the frozen represented-geometry phase definitions and ceilings. An unsealed trace can be measured with `--diagnostic`, which labels the result unbound. A receipt-bound pass requires `--receipt`. The declared Weld/Pulley physical checker uses the frozen declaration and the same exact-rational geometric metrics as the baseline audit.

## Six fixture-family paths

| Family | Candidate path and observed scope |
| --- | --- |
| Geometry and collision boundaries, including scale and offset extremes | `calibration/GeometryCases.java` covers circle SAT/GJK boundaries and thin triangles at three scales and five offsets. A staged JVM boundary query executed. |
| Free motion, forces, damping, restitution | `calibration/SceneCases.java` includes integrator, damping, free motion, and bounce scenes. A force/damping trace and a 600-second nominal free-motion trace executed. |
| Contacts, friction, sleep, wake | The calibration slide/stack/bounce scenes and `default` and `configured` sleep/wake consumers execute the public World. Default 30/60/120 Hz and configured 4/2/1 inner-step grouping executed. |
| Every joint and applicable limit or motor | `calibration/JointCases.java` enumerates Angle, Distance, Friction, Motor, Pin, Prismatic, Pulley, Revolute, Weld, and Wheel settings. `InteractionCases.java` includes the four selected Weld/Pulley members. The full candidate joint matrix reached 231 completed rows out of 232 attempts; one row emitted nonfinite state at step 171 and is rejected. A separate pinned-baseline-only capture reproduces the same failure, so this is a failed baseline physical case, not a port-only regression. |
| Continuous collision detection | `calibration/SceneCases.java` has circle and polygon bullet scenes with detection modes at 30/60/120 Hz and three scales. A staged 60 Hz circle/ALL path reported two TOI payload callbacks. This short path does not qualify the complete CCD matrix. |
| Long-running invariants | Nominal free motion, configured/default sleep/wake, and separately declared Weld/Pulley physical traces run 600 simulated seconds. The free-motion summary records analytic position, energy, and momentum residuals; the source and target math premises still need qualification. |

These are executable paths and host observations. A representative run does not close the unexecuted scale, mode, and target combinations. A nonfinite or skipped row blocks full family completion.

## Observed gates

The default candidate records have frozen event and state counts and pass local getter aliases. Their represented-geometry diagnostic fails at 17,999/18,000 (30 Hz), 35,996/36,000 (60 Hz), and 71,852/72,000 (120 Hz): 125,847/126,000 combined. The frozen baseline has the same failed total. It remains a physical failure.

All six configured candidate traces have 72,000 inner states and the specified 18,000, 36,000, or 72,000 copied endpoints. Each has 935,991 events against 935,967 frozen events. The first extra contact callbacks occur at inner step 36,001 after the approved wake impulse. Each configured trace passes the local alias check and has zero diagnostic penetration failures. Their event mismatch prevents a valid comparator receipt or parity claim; the physical measurements remain unbound diagnostics.

The nominal free-motion candidate has 36,000 states, 108,001 events, 600 simulated seconds, and zero observed energy and momentum drift in the capture summary. The exact frozen nominal member is in the large split calibration archive and was unavailable locally. No baseline self-comparison is used as candidate parity.

The old Weld member and both Pulley preparation members match frozen record counts. The old Pulley transition has 3,600 events against 3,730 frozen events; the first structural divergence is at step 332, order 7. Its physical residual acceptance remains unpassed, including the earlier slack-enabled 0.1208278904872957 m extension and 39 samples above the diagnostic 0.005 m solver tolerance.

The current default and old Weld runtime records match their frozen members after the input header. Pulley preparation 1 and the old transition additionally differ in numerical records. In a separately labelled mixed diagnostic containing the actual Kotlin Vector2 and simplex repairs, the old Pulley transition recovers all 3,730 events and its numeric runtime fields match the frozen trace. Its `ManifoldPointId` runtime type strings still differ (`org.dyn4j.collision.manifold.ManifoldPointId$1` versus the Kotlin companion-generated class). That diagnostic is not an accepted coherent candidate capture and does not waive exact identity.

The separate prospectively declared Weld spring/equal-limit and taut Pulley candidate captures each executed 36,000 steps and 108,000 ordered callbacks. On the staged JVM, the represented Weld anchor maximum was 0.0010240181055693979 m and its angle maximum was 0.0014456701862869353 rad. The taut Pulley maximum absolute rope error was 0.0041245829551926905 m. Both are below their respective declared 0.01 m and one-degree limits. These new physical checks do not repair the old four-member physical gap or the default sleep/wake failure.

The fixed numerical limits, full same-run package, complete fixture matrix, target runtime math paths, unchanged migration applications, and all required native/device lanes remain separate open gates. The configured sine norm and formula-specific comparison assume finite normal binary64 inputs, round-to-nearest arithmetic, the selected operation envelope, and target `sin`, `cos`, and `acos` behavior. A JVM result does not prove those premises on JS, Wasm, native, Android, or Apple runtimes.
