# Assembled-source performance evidence

The [performance manifest task](https://github.com/rubixhacker/dyn4k/issues/17) remains open. The [approved policy](https://github.com/rubixhacker/dyn4k/issues/8#issuecomment-5674480273) and [version 1 manifest](performance-manifest-v1.json) are unchanged. This report records bounded measurements from the assembled World-capable source. It does not report a performance pass.

## Source and provider identity

The source commit is `a34302586a3250d6e1e2b19f3cfe141942f0ed1c`. Its `dyn4k-core` tree is `4958e484cb8311fef63674821f9d4b62cd5bb383`; its `dyn4k` tree is `329700d7f730bb8ce8d06bf46bd6b44d5aea24e1`. Fresh JDK 21 JVM artifacts were published to this worktree's local staging repository. The core JAR SHA-256 is `e503fc9304f29408d008ff73a9a32e11644f9d5c182aac281bcb876bf28e4d39`. The Kotlin JAR SHA-256 is `e7d0b1502bafeb28373d0e20aaf02152268717664b274ad25b3e77511c065274`. The pinned dyn4j 6.0.0 baseline JAR SHA-256 is `204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e`.

The [candidate identity](performance-assembled-v1/candidate-identity-at-pilot.json) has SHA-256 `87141b553cfcdc2574eaa4c85e91666d9c5b58eecfda89c449e5e6dcfce293f5`. The [provider probe](performance-assembled-v1/provider-identity.json) loaded World from the staged core JAR on both routes. Only direct Kotlin loaded the staged convenience JAR. Neither candidate route used an upstream dyn4j JAR. The six [negative controls](performance-assembled-v1/negative-controls/negative-controls.json) rejected missing or crossed routes, an upstream provider, a stale artifact, and empty or inactive scenes.

The manifest SHA-256 is `18cca97bbf1fc939eda669efe2344bbfe06c416a735ca8cc5184d5ba2519176a`. It still lists 999 scenario IDs, 21 targets, and 28 runtime rows. All 28 rows retain `environment_status: unavailable` and `probe_status: unvalidated`. This Bazzite host is an observed JVM pilot host, not a validated representative reference row.

## Bounded current-source observations

The [controlled JVM probe](performance-assembled-v1/probe/probe.json) reported a 20 ns minimum positive timer interval and a 30 ns median timer pair. Its 1,048,576-byte allocation driver reported 1,164,520 allocated bytes and one collection. Heap and RSS channels responded, but they do not separate managed, native, reserved, and workload-attributable memory. No process-memory-cap verdict follows.

The [short pilot index](performance-assembled-v1/pilot/evidence.json) records 54 fresh processes: six frozen small 60 Hz workloads, each on baseline, direct Kotlin, and Java compatibility routes, in separate timing, allocation, and memory modes. Every process warmed for 60 steps and measured 120 steps. There were no process failures. The activity check was valid in 45 runs. The nine lifecycle-wake runs were unvalidated because the frozen check needs at least 30 measured seconds. These processes exercised 18 distinct manifest scenario IDs. Their one-second warm-ups cannot establish convergence.

The [30-second wake index](performance-assembled-v1/wake-30s/evidence.json) adds three fresh timing processes with 1,800 measured steps each. Activity was valid on all three routes. Baseline ended with 66 awake bodies, 1,661 contact begins, and 76 TOI events. Direct Kotlin and compatibility each ended with 32 awake bodies, 1,541 contact begins, and 63 TOI events. Their state-channel checksums agree with each other, but differ from the baseline. The short pile and replacement pilots also have candidate-versus-baseline state-channel differences. Those observations keep numerical and event parity open.

The [replacement plateau index](performance-assembled-v1/plateau/evidence.json) records 100 create/use/dispose cycles on each route. Each reported stable retained-heap drift: 0.306% baseline, 0.094% direct Kotlin, and 0.286% compatibility. The warm-up was one second. The result does not qualify complete memory attribution or the 16 MiB workload cap.

Together, these three indexes record 60 unique process IDs. A separate read-only audit matched all 180 indexed measured, warm-up, and stderr file hashes to the saved candidate identity. These are 18 distinct manifest scenario IDs on one JVM host. No required 600-second scenario or validated reference row completed.

## Calibration attempt

The [six-process baseline calibration](performance-assembled-v1/calibration/calibration.json) used the same pinned dyn4j JAR and JBR 21.0.9 runtime. Each fresh process warmed for 7,200 steps, then measured 1,800 steps at 60 Hz. All six measured scenes retained valid separated-body activity, with no overrun steps. All six warm-up series were `not_converged` under the frozen five-percent rule. The process IDs were `2333074`, `2374907`, `2410096`, `2445424`, `2486264`, and `2501174`. All 18 indexed measured, warm-up, and stderr file hashes matched. The calibration index SHA-256 is `cd07208556f47a3a1ce166d3cefac6899e30594cf5fd6da20910be372183e5c4`.

| Unchanged-baseline pair | Median ratio, 95% | p99 ratio, 95% | Total ratio, 95% |
| --- | ---: | ---: | ---: |
| 1 to 2 | 0.477–0.663 | 0.633–0.830 | 0.555–0.710 |
| 3 to 4 | 1.079–1.738 | 0.754–0.960 | 1.039–1.469 |
| 5 to 6 | 0.976–1.209 | 1.123–1.370 | 1.036–1.305 |

The largest 95% deviation from unchanged-baseline ratio 1 was 73.78% for median, 36.99% for p99, and 46.85% for total compute time. These are exploratory noise readings because every warm-up failed. At `2026-10-18T00:04:57Z`, host load averages were `7.41 8.17 8.98` on 32 CPUs. A point sample at `00:07:27Z` was `12.25 9.77 9.45`. Other JVM and Python work was active. Power mode, temperature, and throttling were not recorded. This attempt did not establish a quiet reference environment or usable noise bound.

## Historical archive boundary

The [version 4 candidate archive](performance-candidate-v4/) records source commit `9ce41f7cc7cfc0a7c7991b02335c5e285159f58d`, with candidate-identity SHA-256 `2268581c6ce00d8c7354034f305e8cac61d29f1bbd88d7ad2538fbe710025a23`. Its full verifier returns `archive_audit: unavailable` on this assembled tree because the source trees differ. The separate raw-only audit pinned the four evidence-index hashes to the values recorded in the [CCD order report](performance-ccd-order.md), then matched all 135 indexed CSV and stderr file hashes across 45 processes. This is a historical byte-provenance check. It reports `source_artifact_audit: not_attempted` and `qualification: unpassed`; it does not transfer the old observations to the new source.

The second tool suite ran 35 tests with no failures or skips, correcting the earlier 34-test and 12-skip report. This provenance repair added four tests; the final suite ran 39 with no failures or skips. Historical version 4 mutation tests used a test-only context pinned to that archive's identity, source Git blobs, fixture revision, provider record, and negative-control record; the test context substitutes those inputs where live re-execution would require the old source. A separate unmocked production-guard test rejected source-revision and JAR-byte/hash substitutions using controlled artifact files. The live full verifier still rejects version 4 on this assembled source. Raw and index mutation tests reject both changed raw bytes alone and a changed raw file paired with a coherently rewritten evidence index.

## Open gates

No 600-second acceptance run was executed. The full 999-scenario program, all 28 validated reference rows, three fresh sustained repeats per required combination, warm-up convergence, quiet-host noise bounds, complete memory attribution, per-runtime probes, and independent timing, allocation, memory, and parity gates remain unpassed. The frozen policy and thresholds have not changed.
