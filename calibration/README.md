# Baseline calibration harness

Disposable measurement harness for [Execute the approved baseline calibration experiment](https://github.com/rubixhacker/dyn4k/issues/15). It uses the unmodified, SHA-256-pinned dyn4j 6.0.0 binary. These outputs are exploratory reference candidates, not approved references or dyn4k acceptance limits.

## Run

Requires a JDK with `javac` (recorded run uses OpenJDK 25.0.3), Bash, curl, git, Perl, GNU find/xargs and SHA-256 tools. No production service is started.

```sh
./calibration/run --help
./calibration/run /absolute/new-output-directory
./calibration/run /absolute/new-smoke-directory U-
# After compilation, execute the same matrix in four isolated JVMs:
./calibration/parallel-run /absolute/new-partitioned-directory
java -Xmx768m -cp calibration/classes Analyze /absolute/new-partitioned-directory/combined /absolute/new-report-prefix
```

`run` retrieves the pinned upstream source and JAR and JUnit test dependencies, generates instrumented copies of selected upstream test classes, and compiles the isolated harness. Upstream source is never edited. The exact original nominal assertion bodies remain in those copies. The scale representatives are additional, dimension-normalized versions with their own IDs, not replacements for nominal tests. Files are created exclusively; existing evidence cannot be overwritten by a repeat.

`parallel-run` partitions scene scale/origin cells plus joints, upstream fixtures, geometry and free motion. No world crosses a process boundary. Replicates use fresh JVMs and fresh worlds. `combined` hardlinks traces and concatenates query/summary records; it does not duplicate raw data on disk. Run `run` at least once first. Do not edit or recompile the harness while a capture is running.

## Artifact contract

- Each gzip JSONL trace begins with input settings, nested detector/broadphase configuration, body/fixture/shape properties, mass/inertia, joint modes/endpoints, immutable scale/origin, timestep and expected segment length.
- Every completed physics step emits full-precision round-trippable doubles for body state and joint observations. Absolute and fixed-origin positions are both retained.
- Passive listeners record ordered contact, collision, CCD, world-step, destruction and bounds callbacks. Contact payloads include velocities, normals, impulses, manifold data and stable construction-order body/fixture references. Lifecycle instrumentation records force/torque completion callbacks in their within-step sequence.
- Scheduled P mutations emit action records; U instrumentation records source actions. Exact fixture sources and hashes define remaining action sequencing. Lazy upstream stiffness is preserved as zero in the initial runtime snapshot and computed in step observations; stiffness-mode rows contain their resolved finite stiffness input before stepping.
- Rotation increment sums are segment-local observations. Default P rotation bounds are below pi; U segments with external transform mutation do not claim a continuous unwrapped total across that mutation.
- `summary.jsonl` accounts for completed segments and immediately rejected non-finite cases. Non-finite output never becomes a finite reference. Its first step/path is retained; that case stops while other independent cases proceed.
- `queries.jsonl` retains query inputs/results, upstream assertion verdicts and rejected API/construction observations.
- Environment, source/class/JAR hashes and exact commands accompany evidence. Repeated JVM evidence is not evidence for other Kotlin targets or runtimes.

## Matrix

496 P scene worlds (5,840,100 planned steps), 232 P joint probes (231 dynamic candidates, one API-rejected limit pair), 40 exact nominal upstream methods, 30 additional scale/origin representative worlds, and 585 geometry query/construction rows. Designated stack/spring/free-motion long runs last 600 simulated seconds. Three timestep rates are covered for all selected scene families, across all 15 grid cells.

Expected simulation steps before rejection: 5,980,956. The negative Angle ratio fails before the 600-step horizon, and remaining inactive-mode gaps are documented separately. Scheduling counters printed by the joint driver include filtered-out cases; use retained summaries for executed counts.

The subsequently approved `P-JCP-` checkpoint supplement adds 92 continuations and 121 recorded preparation segments, totaling 56,224 additional steps. Run it alone with `./calibration/run NEW_OUTPUT P-JCP-`; the parallel runner includes its own partition. Original corpus counts above remain historical. See [checkpoint results and remaining coverage gaps](../docs/research/checkpoint-followup.md).

The final `P-JINT-` supplement adds25 explicit combined/control/transition/equal-limit continuations and3 recorded preparation steps, totaling15,003 steps. Run it alone with `./calibration/run NEW_OUTPUT P-JINT-`; its parallel partition is separate. See [definitions](../docs/research/interaction-bindings.md) and [verified results](../docs/research/interaction-results.md). Inputs are new experimental choices, not replacements for original rejected or inactive observations.

## Interpretation

`Analyze` reports exact repeat-independent scale/origin and timestep differences at matching physical times, contact/CCD/sleep observations and spring mechanical-energy drift. It does not assign numerical pass thresholds. Different timesteps have distinct reference candidates. Geometry rejection is not supported-domain evidence; no-contact NONE CCD diagnostics are expected controls, not successful CCD cases. Complete activation of every limit/cap/interaction is not inferred from a nonzero aggregate joint reaction.

See the source-checked binding reports under `docs/research/`, the negative-ratio diagnosis, and [calibration report](../docs/research/calibration-report.md) for explicit gaps and supplemental setup corrections. The current corrected harness intentionally differs from the archived original capture sources; the report documents comparisons. No reference data or numerical allowance is automatically approved.
