# Staged JVM candidate performance pilots

The [performance manifest task](https://github.com/rubixhacker/dyn4k/issues/17) remains open. These runs exercise the two public candidate routes on one available JVM host. They do not qualify performance against the [approved policy](https://github.com/rubixhacker/dyn4k/issues/8#issuecomment-5674480273).

## What ran

The [version 1 fixture](performance-manifest-v1.json) still defines 999 workload IDs across 21 targets and 28 runtime rows. No budget or reference-environment row changed. The direct route constructs fixtures with the staged `dyn4k` Kotlin builders, properties, joint helper, and callbacks. The Java compatibility route compiles the same `BaselinePilot.java` source against staged `dyn4k-core`, with no upstream JAR in its consumer classpath. Both routes use the same geometry, counts, event cadence, modes, timing channels, and activity checks as the baseline fixture. The direct and compatibility runners completed a one-step construction and step smoke for all 31 joint variants, 62 executions with no exception. This is constructor coverage, not sustained joint activity qualification.

The engine source for the recorded pilots is commit `68c2cead66d4bb71ed6044da1f0fafe7cfc35b8e`, which includes the committed World source at `6c533a5`. The [pilot identity file](performance-candidate-v1/candidate-identity-at-pilot.json) preserves its source-tree, consumer-class, dependency, and build hashes. The local publication is version `0.1.0-alpha.1`. The staged JVM binary SHA-256 values are `b56d947ea183e6b8e7affddd1f24ad3ebd8e3276c6c56fa3e319e114793165f4` for `dyn4k-core-jvm` and `7e32875e21cac6bf1dfdc09627f0db2b31211c706054865db6d24dc5ef638647` for `dyn4k-jvm`. The baseline dyn4j 6.0.0 JAR remains `204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e`. The [provider-origin probe](performance-candidate-v1/provider-identity.json) loaded World from the staged core JAR on both routes. Only the direct route loaded `WorldConveniencesKt` from the staged Kotlin JAR. The Java route reported the Kotlin API as unavailable. The consumer resolves Maven coordinates from the local staging repository; its classpaths contain no project engine class directories or upstream dyn4j JAR.

After the latest integration merge, the branch was at `a896a318277730fdd52a28a875a337d00459b58a`. That merge added a core test and documentation, with no production engine change. A fresh JDK 21 stage and consumer build produced the same two JVM JAR hashes. The provider-origin probe passed again, and a one-step separated-motion execution on each route returned one row with 100 bodies. The long and short pilot archives remain bound to their original identity file and source commit; this post-merge check does not turn them into qualification evidence for a new reference environment.

The [pilot index](performance-candidate-v1/pilot/evidence.json) records the source trees, build-script hash, full resolved classpaths and hashes, JDK 21.0.9 runtime, `-Xms256m -Xmx2g -XX:+UseG1GC`, process IDs, workload IDs, warm-up and measured step counts, raw CSV hashes, and activity checks. The observed host is a Bazzite desktop with AMD Ryzen AI Max+ 395. Power mode, temperature, and throttling were not pinned. During these runs, observed load averages were about 27 to 32, with unrelated Java, npm, and virtual-machine processes using CPU.

## Bounded fixture pilot

The [raw pilot archive](performance-candidate-v1/pilot/) contains 36 fresh processes: six representative fixtures, three API routes, and separate timing and allocation modes. Each process warmed for 60 steps and measured 120 steps at 60 Hz. All 36 process executions completed, with no runner or probe failure. Separated motion, piles, mixed joints, CCD, and replacement met their short-run activity checks. Wake is unvalidated because two seconds cannot establish natural rest followed by a representative wake cycle. All one-second warm-ups are unvalidated.

The table shows timing-mode median and p99 step time in milliseconds. It reports observations, not gate results.

| Fixture, small at 60 Hz | Baseline median / p99 | Direct median / p99 | Compatibility median / p99 |
| --- | ---: | ---: | ---: |
| Separated | 0.199 / 0.482 | 0.262 / 3.117 | 0.207 / 0.616 |
| Pile | 1.041 / 5.722 | 1.206 / 6.484 | 1.323 / 8.645 |
| Mixed joints | 0.843 / 7.824 | 0.855 / 9.051 | 0.897 / 8.815 |
| CCD | 0.411 / 3.556 | 0.461 / 3.035 | 0.435 / 5.991 |
| Wake | 0.891 / 2.286 | 1.097 / 2.833 | 1.213 / 5.220 |
| Replacement | 1.000 / 2.447 | 1.135 / 4.468 | 1.229 / 3.942 |

The separated-motion allocation processes measured 1,015,584 baseline bytes, 1,808,088 direct bytes, and 1,830,584 compatibility bytes over 120 steps. The full allocation and timing values for every fixture are in [the analysis](performance-candidate-v1/analysis.json) and raw index. Those two-second allocation totals cannot establish steady-state allocation per simulated second. Process RSS is a diagnostic channel because managed, reserved, and native bytes have not been attributed separately.

The direct and compatibility state-channel checksums match for separated motion, piles, mixed joints, wake, and replacement. Baseline differs from both candidates on contact workloads. The two candidate CCD traces first differ at step 28 as contacts begin; their final contact-begin and TOI callback counts are 69/184 and 72/204. Both short CCD scenes remain active, but this difference needs numerical and event-order investigation outside this performance ticket. State checksums are diagnostic and do not replace numerical acceptance.

## Short-window uncertainty and controls

The separate [30-second archive](performance-candidate-v1/noise/) has one fresh baseline, direct, and compatibility process. Each used 1,800 warm-up and 1,800 measured steps at 60 Hz. All three separated-motion scenes remained active. Median step times were 126,209, 128,815, and 133,964 ns, respectively. No run overran a full 60 Hz compute interval. Maximum scheduling lateness was 18.9, 9.7, and 40.5 ms. The 30-second warm-ups cannot meet the frozen minimum and convergence procedure.

The analyzer resampled paired one-second blocks 2,000 times. Its exploratory two-sided 95% intervals for candidate/baseline median ratios were 0.966–1.076 direct and 1.018–1.120 compatibility. The p99 intervals were 0.871–2.550 direct and 0.712–3.317 compatibility. Compatibility/direct median was 1.014–1.080. These intervals do not include all host drift or the approved three-repeat uncertainty. They do not certify any ratio. The earlier six-process baseline calibration had five nonconverged 120-second warm-ups, and a later 600-second warm-up also failed convergence on this loaded host. The earlier JVM was JDK 25, so its numeric ratios are not substituted for this JDK 21 triplet.

The [six negative controls](performance-candidate-v1/negative-controls/negative-controls.json) reject a missing direct artifact, crossed compatibility route, upstream JAR on the candidate path, stale binary copy, empty scene, and inactive scene. The empty and inactive CSVs are labeled synthetic transformations of a real pilot file. Their checksums and the source CSV checksum are retained. No staged original was modified.

## Separate memory and plateau probes

The [memory-mode triplet](performance-candidate-v1/memory/) used the separated fixture for 60 warm-up and 120 measured steps in each fresh process. The controlled allocation probe succeeded and each process recorded one collection with the world alive. Post-collection live-heap readings were 2,320,760 bytes baseline, 2,474,432 direct, and 2,422,856 compatibility. Peak process-RSS deltas were 25,296,896, 33,853,440, and 37,199,872 bytes. RSS includes runtime reservations and has no validated workload attribution, so these deltas cannot be scored against the 16 MiB incremental workload cap. The one-second warm-ups also remain unvalidated.

The [clean replacement plateau](performance-candidate-v1/plateau/) contains 100 create/use/dispose cycles per route, with a separate 60-step warm-up. The median post-collection live heap for cycles 20–39 and 80–99 was 1,567,924 then 1,572,552 bytes baseline; 1,783,460 then 1,784,760 bytes direct; and 1,732,796 then 1,738,784 bytes compatibility. The rises were 0.295%, 0.073%, and 0.346%. Each meets the frozen five-percent drift check and records reclamation. This is a bounded plateau observation, not a validated memory cap or sustained qualification. The [superseded first capture](performance-candidate-v1/discovery-plateau-v0/) is retained because its candidate warm-up CSVs had process markers before the header; the rerun stores those markers separately and has parseable CSV headers.

## Reproduce

Use JDK 21 and the local staging repository. The stage tasks, consumer task, and runner use the published Maven coordinates. The JAR supplied to the pilot is the pinned dyn4j 6.0.0 baseline.

```sh
JAVA_HOME=/home/stewart/.gradle/jdks/jetbrains_s_r_o_-21-amd64-linux.2 ./gradlew :dyn4k-core:publishKotlinMultiplatformPublicationToStagingRepository :dyn4k-core:publishJvmPublicationToStagingRepository :dyn4k:publishKotlinMultiplatformPublicationToStagingRepository :dyn4k:publishJvmPublicationToStagingRepository -PqualificationRepository="$PWD/build/staging-repository" --rerun-tasks --offline --console=plain
JAVA_HOME=/home/stewart/.gradle/jdks/jetbrains_s_r_o_-21-amd64-linux.2 ./gradlew -p consumers/performance writeCandidateClasspath -PperformanceRepository="$PWD/build/staging-repository" --rerun-tasks --offline --console=plain
python3 tools/performance/candidate_runner.py prepare /home/stewart/.gradle/jdks/jetbrains_s_r_o_-21-amd64-linux.2/bin/java HEAD
python3 tools/performance/provider_probe.py --output docs/research/performance-candidate-v1/provider-identity.json
python3 tools/performance/candidate_pilot.py --output docs/research/performance-candidate-v1/pilot --jar /tmp/dyn4k-performance-dyn4j-6.0.0.jar --java /home/stewart/.gradle/jdks/jetbrains_s_r_o_-21-amd64-linux.2/bin/java --javac /home/stewart/.gradle/jdks/jetbrains_s_r_o_-21-amd64-linux.2/bin/javac --mode timing --mode allocation --seconds 2 --warmup-seconds 1 --repeats 1
python3 tools/performance/negative_controls.py --pilot-evidence docs/research/performance-candidate-v1/pilot --output docs/research/performance-candidate-v1/negative-controls
python3 tools/performance/candidate_pilot.py --output docs/research/performance-candidate-v1/noise --jar /tmp/dyn4k-performance-dyn4j-6.0.0.jar --java /home/stewart/.gradle/jdks/jetbrains_s_r_o_-21-amd64-linux.2/bin/java --javac /home/stewart/.gradle/jdks/jetbrains_s_r_o_-21-amd64-linux.2/bin/javac --scenario separated.default --mode timing --seconds 30 --warmup-seconds 30 --repeats 1
python3 tools/performance/candidate_pilot.py --output docs/research/performance-candidate-v1/memory --jar /tmp/dyn4k-performance-dyn4j-6.0.0.jar --java /home/stewart/.gradle/jdks/jetbrains_s_r_o_-21-amd64-linux.2/bin/java --javac /home/stewart/.gradle/jdks/jetbrains_s_r_o_-21-amd64-linux.2/bin/javac --scenario separated.default --mode memory --seconds 2 --warmup-seconds 1 --repeats 1
python3 tools/performance/candidate_pilot.py --output docs/research/performance-candidate-v1/plateau --jar /tmp/dyn4k-performance-dyn4j-6.0.0.jar --java /home/stewart/.gradle/jdks/jetbrains_s_r_o_-21-amd64-linux.2/bin/java --javac /home/stewart/.gradle/jdks/jetbrains_s_r_o_-21-amd64-linux.2/bin/javac --scenario lifecycle.replace --plateau --warmup-seconds 1
python3 tools/performance/analyze_candidates.py --pilot docs/research/performance-candidate-v1/pilot --noise docs/research/performance-candidate-v1/noise --output docs/research/performance-candidate-v1/analysis.json
python3 tools/performance/verify_candidate_archive.py docs/research/performance-candidate-v1
```

The manifest still requires verified reference hosts and devices, validated per-runtime timer/allocation/memory probes, quiet-host warm-up and noise calibration, all required workload/rate/API combinations, and three fresh 600-second runs. These conditions are unpassed. No full accepted matrix was run.
