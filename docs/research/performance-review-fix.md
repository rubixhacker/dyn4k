# Corrected staged JVM performance pilots

**Superseded audit notice (2026-10-17):** The version 2 observations below retain the one-world runner repair, but their archive lacks the raw stderr marker stream and capture-tool source record required by the later audit. The current verifier reports `archive_audit: unavailable` for this historical archive. Use the [version 3 audit report](performance-audit-review-fix.md) for current bounded observations. Neither archive qualifies performance.

The [performance manifest task](https://github.com/rubixhacker/dyn4k/issues/17) remains open. This report replaces the bounded timing, allocation, noise, and retained-memory observations in [the first candidate report](performance-candidate.md). The [version 1 raw archive](performance-candidate-v1/) remains available and is marked superseded for those observations. No approved budget, fixture geometry, target, or runtime row changed.

## What changed

The Java baseline and compatibility runner now complete warm-up, clear the warm fixture, and enter a separate measurement method. The direct Kotlin runner follows the same order. Each measurement method constructs one world and keeps it reachable through collection and measurement. Runtime warm-up still runs in the same process before the measured world is constructed. The corrected runner source commit is `c2b4372c754c9b1d9aeec5c409443134c9169aa3`. The engine source trees and staged JVM binaries did not change. The candidate identity records the source revision, source-tree hashes, consumer-class hashes, process routes, Java runtime, JVM flags, and binary hashes.

The archive verifier now parses each required raw CSV. It recalculates median, p95, p99, allocations, activity, state checksum, warm-up status, RSS diagnostic peak, and plateau drift. It checks the indexed value against the recalculation. It also checks the required workload, mode, route, step, and cycle coverage. An altered indexed median with unchanged raw CSV failed the new test; the original verifier had accepted it.

## Artifact and host identity

The [version 2 archive](performance-candidate-v2/) binds all new processes to [candidate identity SHA-256 `4774cad9caa0acf9ff65a735af5725ea78267660f4f587e5d67a1b493877ef5f`](performance-candidate-v2/candidate-identity-at-pilot.json). The staged Maven artifacts are `io.github.rubixhacker:dyn4k-core:0.1.0-alpha.1` and `io.github.rubixhacker:dyn4k:0.1.0-alpha.1`. The staged core JVM JAR SHA-256 is `b56d947ea183e6b8e7affddd1f24ad3ebd8e3276c6c56fa3e319e114793165f4`; the Kotlin JVM JAR is `7e32875e21cac6bf1dfdc09627f0db2b31211c706054865db6d24dc5ef638647`. The immutable dyn4j 6.0.0 JAR is `204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e`. The [provider probe](performance-candidate-v2/provider-identity.json) found the staged core World class on both candidate routes and the staged Kotlin conveniences only on the direct route. Six [negative controls](performance-candidate-v2/negative-controls/negative-controls.json) rejected missing and crossed routes, upstream and altered candidate JARs, and empty and inactive scenes.

The observed JVM host has an AMD Ryzen AI Max+ 395 and JBR 21.0.9. The runtime flags were `-Xms256m -Xmx2g -XX:+UseG1GC`. The load average was `20.65 20.06 24.71` near the start and `13.47 19.86 23.23` after capture. These are point readings, not continuous load telemetry. Power mode, temperature, throttling, and an isolated quiet window were unavailable. The 30-second warm-ups were below the frozen convergence minimum. No result here selects a budget outcome.

## Bounded observations

All 36 [short pilot](performance-candidate-v2/pilot/evidence.json) processes completed: six small fixtures at 60 Hz, three routes, and timing and allocation modes. Each warmed for 60 steps and measured 120 steps. The corrected separated-motion timing median/p99 values were 204,988/429,675 ns baseline, 126,550/359,461 ns direct Kotlin, and 182,566/567,726 ns compatibility. Every raw process, workload ID, mode, process ID, step count, state checksum, and CSV digest is indexed in the archive. One-second warm-ups are unvalidated. Short wake activity remains unvalidated. The CCD direct and compatibility state traces still first differ at step 28. Their final contact-begin/TOI counts remain 69/184 and 72/204, respectively. This divergence needs numerical and event-order investigation before qualifying a CCD comparison.

All three [memory-mode processes](performance-candidate-v2/memory/evidence.json) warmed for 60 steps and measured 120 steps with one recorded collection each. Post-collection live-heap readings were 2,174,416 bytes baseline, 2,328,752 bytes direct Kotlin, and 2,281,432 bytes compatibility. The corresponding peak process-RSS deltas were 25,038,848, 32,808,960, and 34,181,120 bytes. These are process readings. Managed, reserved, and native memory were not separately attributed, so the 16 MiB workload cap is unpassed. The change in readings from version 1 is consistent with removing a reachable warm fixture, but a heap delta alone cannot prove object ownership.

The [30-second timing triplet](performance-candidate-v2/noise/evidence.json) warmed for 1,800 steps and measured 1,800 steps per route. Median/p99 step times were 122,693/326,218 ns baseline, 105,740/286,563 ns direct Kotlin, and 83,338/206,792 ns compatibility. Maximum scheduling lateness was 33.7, 4.5, and 2.3 ms. The [analysis index](performance-candidate-v2/analysis.json) uses 2,000 paired one-second block resamples. Exploratory 95% candidate/baseline median-ratio intervals were 0.813–0.907 direct and 0.635–0.725 compatibility; p99 intervals were 0.294–1.144 and 0.230–0.811. These intervals omit run-to-run host drift and do not meet the approved three-repeat sustained method.

The refreshed [plateau archive](performance-candidate-v2/plateau/evidence.json) has 100 create/use/dispose cycles per route. Cycles 20–39 versus 80–99 produced absolute median live-heap drifts of 0.296% baseline, 0.093% direct, and 0.268% compatibility. The verifier recalculated these values from each raw cycle. This bounded plateau observation does not establish the workload memory cap.

The new archive's evidence-index SHA-256 values are `6eb27c9ea9be702697eea62c7b1f4068594d61dca9aeaf246da5cf99e3fc05d2` for short pilots, `a116e4a12a70753c82a42c1949e6ad12eb82d445db3b8aa5737ccbd2af2d164d` for noise, `da4ffef050587d628814b4f398a5cfe5ed129190199e8a2741b22700172247ca` for memory, and `2523fde572174e872560e6c3f939608b07ef90d30a71ca8fee7807754a414ec7` for plateau. Each index stores the SHA-256 of every raw measured and warm-up CSV. The archive verifier returned 36/3/3/3 required processes, six rejected controls, and `qualification: unpassed`.

## Reproduce and qualification boundary

Use the pinned JDK 21 runtime and locally staged Maven artifacts. The staged engine JARs were already built from the unchanged engine trees. Rebuild the consumer after runner source changes, prepare the identity from the committed revision, then run the same fixture commands as in the first report with `performance-candidate-v2` as the output root. The commands below check the source and archive boundaries:

```sh
JAVA_HOME=/home/stewart/.gradle/jdks/jetbrains_s_r_o_-21-amd64-linux.2 ./gradlew -p consumers/performance writeCandidateClasspath -PperformanceRepository="$PWD/build/staging-repository" --rerun-tasks --offline --console=plain
python3 tools/performance/candidate_runner.py prepare /home/stewart/.gradle/jdks/jetbrains_s_r_o_-21-amd64-linux.2/bin/java c2b4372c754c9b1d9aeec5c409443134c9169aa3
python3 tools/performance/manifest.py validate docs/research/performance-manifest-v1.json
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s tools/performance -p 'test_*.py'
PYTHONDONTWRITEBYTECODE=1 python3 -B tools/performance/verify_candidate_archive.py docs/research/performance-candidate-v2
```

The [frozen manifest](performance-manifest-v1.json) still contains 999 scenarios, 21 targets, and 28 runtime rows. All runtime environment rows remain unavailable or unvalidated. The earlier loaded-host convergence failure remains evidence of an unresolved calibration problem. A quiet, calibrated host window, validated memory attribution and probe identities, the full workload/rate/API matrix, and three fresh 600-second runs per required combination have not been completed. Performance qualification remains **unpassed** under the [approved policy](https://github.com/rubixhacker/dyn4k/issues/8#issuecomment-5674480273).
