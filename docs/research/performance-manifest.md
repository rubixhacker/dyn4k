# Performance fixture and measurement manifest, version 1

The [performance manifest task](https://github.com/rubixhacker/dyn4k/issues/17) remains open. The [approved performance policy](https://github.com/rubixhacker/dyn4k/issues/8#issuecomment-5674480273) is fixed. This report records an executable fixture and bounded baseline observations. It does not qualify dyn4k or any non-JVM runtime.

## Reproduce the manifest

The machine-readable [version 1 manifest](performance-manifest-v1.json) carries the [approved support contract](https://github.com/rubixhacker/dyn4k/issues/6#issuecomment-5651793360): 21 targets, 28 target/runtime rows, and 999 scenario IDs covering every family, size, timestep, API, and joint mode. Each row has an explicit gate assignment and optimized build identity. The baseline API is a JVM oracle; direct Kotlin and compatibility scenarios must run on each applicable runtime row. Representative hardware, runtime version, and ABI are `null` until verified. All rows therefore remain `unavailable` for reference-environment qualification. The observed pilot host is recorded separately.

```sh
python3 tools/performance/manifest.py validate docs/research/performance-manifest-v1.json
python3 -m unittest discover -s tools/performance -p 'test_*.py'
python3 tools/performance/measure.py probe --output /tmp/dyn4k-performance-probe
python3 tools/performance/measure.py pilot --output docs/research/performance-pilot-v1
python3 tools/performance/analyze.py docs/research/performance-pilot-v1
```

The measure tool downloads the pinned binary into an isolated temporary directory when `--jar` is absent. It rejects a hash mismatch. A local verified JAR may be supplied with `--jar`. The pinned [dyn4j 6.0.0 source](https://github.com/dyn4j/dyn4j/tree/058bf6d982a0fb89b54050f929f6ea9dae53b714) is `058bf6d982a0fb89b54050f929f6ea9dae53b714`. The binary JAR SHA-256 is `204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e`. The sources JAR SHA-256 is `83b47be47bdce27681139dab84937e0f586b70ab800dc494fbebed4b58893223`. The local check matched both downloaded artifacts. The pilot archive includes the original upstream [license](performance-pilot-v1/UPSTREAM-LICENSE.md); its SHA-256 is `2d8544c993fb16a051e311f0e47cc5b056790e9ffec0d63b4602f076731695b5`.

## Fixture contract

The manifest fixes body counts at 100/1,000/10,000 for separated motion; 100/500/2,000 for piles; 50/250/1,000 for mechanisms; 25/100/500 for continuous collision; and 100/1,000/5,000 for lifecycle. Counts refer to dynamic bodies. It defines a 0.25 m radius circle with density 1 kg/m², friction 0.5, and restitution 0; a 200 m by 1 m floor where needed; wall and anchor geometry; initial positions and velocities; gravity; deterministic event cadence; and seed `17017`. The Java harness implements these inputs against dyn4j 6.0.0.

The joint family has ten baseline joint types and one mixed mechanism. Every listed mode has its own scenario. The [pinned source classes](https://github.com/dyn4j/dyn4j/tree/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/dynamics/joint) support the named modes. Exact limits, frequency, damping ratio, motors, ratios, topology, and impulse schedule are in `joint_parameters` and the Java harness. Each dynamic body has one joint to a static anchor. Once per simulated second, the fixture applies a linear impulse and a 0.01 kg·m²/s [angular impulse](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/dynamics/AbstractPhysicsBody.java#L596). This excites angular modes. At-rest detection is off in this family so measured steps continue to solve the mechanism. The separate lifecycle family tests natural rest and wake. It attaches every tenth body to the floor, so replacement includes joint and fixture cleanup while preserving body and joint counts.

| Joint | Exercised modes | Modes absent from the pinned type |
| --- | --- | --- |
| Angle | Free, angular limits, ratio | Motor, spring |
| Distance | Rigid, linear limits, spring, damped spring | Motor |
| Friction | Force and torque resistance | Motor, limits, spring |
| Motor | Linear and angular targets | Limit and spring switches |
| Pin | Spring, damped spring | Motor, limits |
| Prismatic | Free, linear limits, linear motor, spring, damped spring | Angular motor and limits |
| Pulley | Taut, ratio, slack | Motor, limits, spring |
| Revolute | Free, angular limits, angular motor | Spring |
| Weld | Rigid, angular limits, spring, damped spring | Motor |
| Wheel | Spring, damped spring, linear limits, angular motor | Linear motor |

Angle and Pulley ratios require two distinct bodies. Each repeated mechanism has a static anchor and a dynamic body; Pulley also has two distinct pulley anchors. No fictitious gear joint or mode is added. The 31 joint variants include one mixed fixture that rotates all ten types.

The harness records one raw row per step: compute time including the scheduled mutation, mutation time alone, lateness, current-thread allocation, heap use, process RSS, body and joint counts, awake bodies, summed linear and angular speed, contact starts and ends, and time-of-impact events. It also samples the full broad-phase candidate snapshot and active contact pairs and points once per simulated second and on the final step. The [full detector iterator](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/collision/broadphase/DynamicAABBTree.java#L336) avoids reading a cleared update set. `-1` marks an unsampled diagnostic, never zero activity. A warm-up CSV records raw step times separately. `ContactListenerAdapter` and `TimeOfImpactListenerAdapter` count callbacks in the real baseline engine. A production port must use the same callback sequence and fixture state through the approved public consumer seam. Missing counters or changed activity invalidate a comparison.

## Measurement contract

Every small fixture is an absolute gate. Medium additionally gates JVM, Android, Linux, Windows, macOS, iOS, browser JS/Wasm, and desktop WASI rows. tvOS and watchOS medium results are report only. Stress is report only. All sizes still require correctness execution on every in-scope target. The machine-readable manifest carries the exact approved ratios, `timestep/4` p99 fraction, 16/64 MiB incremental peak caps, and 10-minute/three-fresh-process sustained contract. It distinguishes timing, allocation, and memory processes. No observed pilot metric overrides those limits.

For a full baseline series on this JVM harness, run one scenario with `measure.py run --family FAMILY --variant VARIANT --size SIZE --hz RATE --mode timing --output DIR`. The command executes three fresh 600-second measured processes. Run allocation and memory modes separately with the same scenario and pacing. Run `--mode plateau` to record 100 create/use/dispose cycles. The baseline harness has no dyn4k adapter yet; the port must implement the same CSV fields and scenario inputs through its public direct and compatibility APIs. The analyzer accepts two full raw CSV files and applies one-second paired block resampling to full-run and final-minute ratios:

```sh
python3 tools/performance/analyze.py --baseline BASE.csv --candidate CANDIDATE.csv --hz 60 --metric median --limit 1.10
```

An external direct Kotlin or compatibility runner can be supplied with `--api`, `--runner`, and `--candidate-artifact`. It receives family, variant, size, rate, step count, mode, warm-up steps, and API in that order. It must emit the baseline CSV columns. Its stderr stream must contain a warm-up CSV plus `#key=value` records for construction time and allocation, empty-harness and post-construction RSS, post-collection retained heap with a live world, and collection count. The warm-up CSV includes step time and RSS. The tool hashes the candidate artifact and runner, checks row count and topology, and keeps raw data. The port adapter is still required. The `stress` command uses a 60-second capacity run, a 180-second wall limit, and a 3 GiB process-RSS limit on Linux; it saves a termination reason and partial raw output if a ceiling is reached. These are bounded reporting limits, not release gates.

The required stderr keys are `construction_ns`, `construction_allocated_bytes`, `rss_empty_harness_bytes`, `rss_after_construction_bytes`, `retained_heap_world_alive_bytes`, and `retained_collection_count_delta`. Use `-1` for an unavailable probe; the collector then rejects a required memory result. The external runner must preserve the same units and event schedule.

The `matrix` command accepts the same fixture, `--runner`, and `--candidate-artifact`. It executes three 600-second fresh processes per API in the orders baseline/direct/compatibility, direct/compatibility/baseline, and compatibility/baseline/direct. Each API occupies every position once. Run timing, allocation, and memory as separate matrix commands. The result index records the order. It still needs verified reference hardware and a port runner before it can produce release evidence.

The method is frozen in `measurement_method`: pace without dropping steps, warm up for at least 120 seconds, compare the last three 30-second warm-up medians, and mark no convergence by 600 seconds inconclusive. `--warmup-seconds` allows a longer run when needed. Use three unchanged-baseline pairs to characterize noise before candidate evaluation. `./gradlew -p tools/harness :performance:calibrate` runs six fresh baseline processes and records each interval. Resample paired one-second blocks with 2,000 deterministic draws. A relative ratio is within its limit only when its 95% upper bound is within the applicable limit. Evaluate every run and its final minute separately. Keep short event-only tail series visible and mark tails with fewer than 100 final-minute events inconclusive. Keep invalid raw runs and their reasons. The provided pilot uses a one-second warm-up and cannot validate this convergence rule.

```sh
./gradlew -p tools/harness :performance:calibrate --args="--family separated --variant default --size small --hz 60 --output docs/research/performance-calibration-v1"
```

The JVM timer and allocation probe is executable. It measures 10,000 adjacent `System.nanoTime()` pairs and a retained 1 MiB controlled allocation. The runner also records construction allocation, retained heap after collection with the world alive, and an RSS delta from the empty harness through construction, warm-up, and measurement. The process-RSS channel is diagnostic: reserved and committed heap changes can move RSS after collection. It cannot yet isolate workload-attributable managed and native memory or establish the 16/64 MiB cap. Thread allocation includes the measured Java thread, not other runtime threads. Every non-JVM allocation and memory probe is unvalidated. A zero or absent reading is never accepted as a pass.

## Pilot evidence and remaining work

The raw [pilot archive](performance-pilot-v1/) contains `evidence.json`, `probe.json`, warm-up series, and per-step CSV data. `evidence.json` binds each raw file by SHA-256 to the manifest, harness source, pinned baseline binary, JVM flags, and observed host. Pilot timing covers 30, 60, and 120 Hz for small and medium sizes. Each timing run has two simulated seconds and one second of warm-up. Allocation and memory runs use 60 Hz with the same durations. Six representative variants produce 60 process runs. Construction and first-step times are informational fields; cold process initialization remains unavailable. These short runs are activity and probe pilots. They are not 600-second runs or three repeats.

The [pilot analysis](performance-pilot-v1/analysis.json) finds valid immediate activity in 30 of 36 timing series. Six lifecycle series remain unvalidated because two seconds cannot demonstrate a settled world and its later wake cycle. The one-second warm-up is unvalidated in all 36 series. The short-run p99 is below `timestep/4` in all 18 small series and ten of 18 medium series. The medium series above that fraction are the pile at 60 and 120 Hz, wake at 30/60/120 Hz, and replacement at 30/60/120 Hz. These are observed baseline pilot times on this host, not pass/fail verdicts for a sustained gate. They do not establish that the absolute limits are feasible here. The exact p99 value and limit for each series are in the analysis file.

The JVM probe observed 20 ns as its smallest positive adjacent timer difference, 21 ns as its median paired-call difference, and 31 ns at p99. It measured 1,164,520 allocated bytes while retaining 1,048,576 controlled payload bytes. One collection occurred in the controlled release test. Process RSS increased from 47,853,568 to 61,493,248 bytes after collection, despite the released payload. This confirms that raw RSS deltas include runtime reservation effects. The memory cap is unpassed.

The [six-process calibration](performance-calibration-v1/calibration.json) used a 120-second paced warm-up and 30 measured seconds in each fresh JVM. All six measured separated-body runs kept their intended activity. Five warm-up series did not converge; one did. Three unchanged-baseline pairs produced maximum 95% interval deviations from a ratio of 1 of 41.9% for median time, 24.0% for p99, and 33.8% for total compute time. These intervals are exploratory because most warm-ups failed the frozen convergence rule. They cannot certify a dyn4k ratio or establish a useful noise bound for this host.

The separate [600-second warm-up probe](performance-warmup-v1/warmup-probe.json) also kept the separated-body fixture active but did not converge. Its last six 30-second medians, in nanoseconds per step, were 116,025; 102,329; 92,099.5; 108,390.5; 107,764.5; and 119,271. The final three exceed the frozen five-percent band. This is a measured host/JVM limitation, not a reason to widen the acceptance rule. Warm-up and noise qualification remain open.

The [100-cycle lifecycle replacement plateau](performance-plateau-v1/) recorded every cycle and 100 collections. Median live heap after collection was 1,392,824 bytes for cycles 20–39 and 1,395,096 bytes for cycles 80–99, a 0.16% rise. The plateau check reports `stable`. Its 120-second warm-up did not converge, and the RSS channel still lacks workload attribution, so this run remains unqualified. The archive includes its raw warm-up, cycle CSV, probe, and SHA-256 bindings.

The [bounded separated-motion stress smoke](performance-stress-v1/) completed 3,600 measured steps at 60 Hz with 10,000 dynamic bodies. Its activity check was valid. The measured p99 was 14,391,203 ns, the maximum was 21,342,466 ns, and nine compute steps exceeded one 60 Hz interval. The process stopped normally within the 180-second wall and 3 GiB RSS ceilings. The 30-second warm-up cannot validate convergence; the peak RSS delta of 254,648,320 bytes is diagnostic only. Stress is report only, and this one-minute run is not sustained qualification.

The later [staged JVM candidate report](performance-candidate.md) exercises direct Kotlin and Java compatibility routes against locally staged artifacts. It includes bounded timing, allocation, memory, and plateau pilots, negative controls, provider-origin checks, and raw checksums. Its unqualified observations do not change the manifest or close the reference-environment gaps.

The currently observed host is a Bazzite desktop reporting AMD Ryzen AI Max+ 395 and OpenJDK 25.0.3. Its exact OS/kernel/runtime strings and reported RAM are in `evidence.json`. This host is not a selected 21-target reference matrix. Build JDK 21 is the approved pin; the pilot JVM is 25.0.3, so the pilot cannot establish release performance even on JVM. Power mode, charging state, temperature, and throttling could not be pinned from these runs. No target row uses an invented device identity.

The remaining blockers are concrete: identify and verify representative hardware and runtime pins for 28 rows; execute the same fixture on direct Kotlin and compatibility APIs; validate timer, allocation, and complete memory attribution per runtime; finish warm-up and unchanged-baseline noise calibration; verify natural sleep and all joint modes over sustained runs; perform 100-cycle plateaus and the three 10-minute runs at all required rates, sizes, APIs, and environments; and apply the exact independent gates. Until those observations exist, the manifest task and performance qualification remain open.
