# Separate sleep/wake quality candidate capture

Status: **six captures completed and audited; exact reference identities and proposed phase indices pending live review. Physical acceptance has not been evaluated.** Original default-settings references, fixed schedules and measured physical failures remain unchanged.

Supports [Execute the approved separate sleep/wake quality experiment](https://github.com/rubixhacker/dyn4k/issues/29), under the [approved six-run protocol](https://github.com/rubixhacker/dyn4k/issues/7#issuecomment-6172176446) and [configuration proposal](https://github.com/rubixhacker/dyn4k/blob/23e117d39603fd8aca505448f8ac111d662107c4/docs/research/sleep-wake-quality-configuration.md). This publication creates candidate evidence, not approved references, a physical pass or port qualification.

## Execution boundary and provenance

The driver was frozen at [`82395ce9c39f7a0973f71ecb025275d8a496683e`](https://github.com/rubixhacker/dyn4k/tree/82395ce9c39f7a0973f71ecb025275d8a496683e/docs/research/sleep-wake-quality-capture) before physics. Independent parent review read both source files, compared the recorder to the pinned original, compiled independently, ran the non-physics grouping check, and matched executed class hashes. The final [capture auditor](sleep-wake-quality-capture/audit.mjs) is separately versioned; it does not calculate penetration or compare physical ceilings.

Only two settings differ from original inputs: `linearTolerance=1/4096 m` and maximum position iterations 8 (plus the corresponding derived squared-tolerance getter). Every other settings field, complete input body/fixture state and configured world algorithms was checked against the hash-guarded original 120 Hz input. The fixed JAR SHA-256 is `204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e`, matching dyn4j 6.0.0 source revision `058bf6d982a0fb89b54050f929f6ea9dae53b714`.

Each of the six journeys ran in a fresh JVM with OpenJDK/JBR 25.0.3, flags `-Xms128m -Xmx512m`. The archive includes actual Java/Javac paths, versions and executable hashes, exact executed class files, source, JAR, license, commands and per-run logs. Source/class/JAR hashes were checked before each journey and after all six. An initial metadata helper assumed `/usr/bin/java`; that nonexistent-path lookup was corrected to the actual PATH-resolved JetBrains JBR installation. The pre-run version capture, reviewed source/classes and physics invocation were unchanged; no journey was retried or added.

The [driver](sleep-wake-quality-capture/SleepWakeQuality.java) preserves floor/square geometry, initial poses, gravity, materials, density, damping and center impulse. The [recorder](sleep-wake-quality-capture/Capture.java) has an actual nested outer/inner loop: 4/2/1 explicit `world.step(1,1.0/120.0)` calls per outer 30/60/120 Hz interval. Each internal end-state is read once with rotation tracking, then the same observation is serialized again for an outer endpoint when appropriate; there is no second dynamic state read or hidden advance. Nonfinite rejection now propagates after retaining its diagnostic, preventing another capture from starting. No such fault occurred.

| Outer cadence | Repetitions | Internal steps per outer interval | Internal states per repetition | Outer endpoints per repetition |
|---|---:|---:|---:|---:|
| 30 Hz | 2 | 4 | 72,000 | 18,000 |
| 60 Hz | 2 | 2 | 72,000 | 36,000 |
| 120 Hz | 2 | 1 | 72,000 | 72,000 |

Total: **432,000 internal states, 252,000 outer endpoints**. Each journey represents 600 simulated seconds. All five TimeStep getters were checked on every StepListener callback: internal `dt=1/120`, inverse 120; previous `dt=1/60` and ratio 0.5 on the first call, then previous `dt=1/120` and ratio 1. The typo `getPrevousDeltaTime` is the upstream getter spelling. The outer cadence is metadata/grouping, not the engine timestep at 30/60 Hz. These are not three distinct timestep qualifications.

## Complete candidate identities

The [candidate manifest](sleep-wake-quality-candidate-manifest.json) is the authoritative machine-readable index: all six gzip/decompressed/input hashes, exact counts, settings/profile/source/runtime identity, event histories and proposed intervals. No run replaces an original reference. Proposed role: repetition 1 at each outer cadence as the reference candidate, repetition 2 as corroborating capture; all six remain retained and pending review.

[Lossless candidate archive](https://github.com/rubixhacker/dyn4k/releases/download/sleep-wake-quality-candidate-20261014/dyn4j-sleep-wake-quality-20261014.tar.gz), 6174766 bytes, SHA-256 `057d96767dcf4ef863afb61417f8ef9cc6b7fc1442e0e39df55bbe006cb1212c`. Release tag `sleep-wake-quality-candidate-20261014` points to source/auditor revision `d1c5116b6d4dbd4cb9f9faf3f6cfc997fa014fbe`. The package's `SHA256SUMS` covers all 63 other members.

| Outer Hz | Repetition | Gzip SHA-256 |
|---|---:|---|
| 30 | 1 | `c2264bc048e7118a4dde0c566768fc0e1f70d02431c2d5a8829de78c6f75f0d9` |
| 30 | 2 | `150bc3c39452acfb031c962441d8cfd02ed9795ae6e662d3ea9936c2376cf7ed` |
| 60 | 1 | `9c5d165d77a69191fb6be517ad41d7fdb6bcf1f4c89256af2864ba07f024916b` |
| 60 | 2 | `c2bf76f7bf5fc427301d31ed305895a2f21c7d9360117db1a9ed506e22028313` |
| 120 | 1 | `267ea651d58b0bb0b0b6d06efce5e2cc30b31a79738c83615bd199340af9f629` |
| 120 | 2 | `682b7c3bdf28ce5c651f2125525d939c3618ad6e3f905e9b28507ae0cbfca618` |

## Event-derived phase proposal

All six captures independently yield the same internal event indices: actual TOI payload at 5 (fixture/body overloads, orders 4/5), first two contact begins at 6, first ordinary solved-contact callback at 7, natural sleep at 66, wake action at 36,001 and return to natural sleep at 36,084. Each records 935,967 listener events, 72,000 inner states, two immediate action snapshots and one action. There are no subsequent contact begin/end/destroyed episodes; no ambiguous phase anchors were found.

The complete proposed schedule follows the approved proposal's event rule. No penetration values were used or calculated to select these boundaries. Its agreement with the original 120 Hz schedule is an observation, not reuse of an assumed schedule.

| Proposed phase | Inclusive internal indices, all six captures | Count per capture | Applicable ceiling after approval |
|---|---|---:|---:|
| Initial approach | 1–4 | 4 | 0 m |
| Impact | 5–7 | 3 | 1/100 m |
| Initial settling | 8–65 | 58 | 1/200 m |
| Rest before action | 66–36,000 | 35,935 | 1/1000 m |
| Wake settling | 36,001–36,083 | 83 | 1/200 m |
| Rest after wake | 36,084–72,000 | 35,917 | 1/1000 m |

Every internal sample belongs to exactly one proposed interval. An outer endpoint at frame `j` maps to internal index `j*(120/outerHz)` and inherits that interval; it is also checked as an internal sample. Candidate port runs must later use the frozen reviewed baseline indices, not their own observed contact/sleep transitions. These indices are not yet frozen acceptance assignments.

The full 299–300 s prerequisite is 121 recorded sleeping states, internal indices 35,880–36,000 inclusive. At inner step 36,001, records are `before-wake` order 0, action order 1, `after-wake` order 2. Immediate transforms are unchanged, velocity changes exactly `(0,0)`→`(1,0)`, angular velocity remains zero, and at-rest changes true→false. Outer action frames are 9,001 / 18,001 / 36,001 respectively, always before their first internal step. These checks establish actual natural sleep/wake coverage, not a geometric penetration bound.

## Reproducibility and audit meaning

Each gzip is retained byte-for-byte with its own hash: IDs and grouping metadata intentionally differ. For comparison, the auditor excludes the separately verified input row and outer-endpoint duplicate rows, removes only top-level state `outerStep` / `innerWithinOuter` annotations, and replaces the exact run ID string in rows/payload world labels with `Q-CANDIDATE`. Every remaining callback signature/order/payload, action value and internal state value is retained. All six normalized internal sequences have the same SHA-256. This includes both repetitions and the three grouping journeys; equality is a local baseline reproducibility observation, not cross-platform determinism or numerical tolerance selection.

Normalized inner sequence SHA-256: `95ac1ebfff997ebabb53c304a189192884d0ea8c55db2053d1701865869d3dbb`. Full state-only sequence SHA-256: `a67c84d1f4bc7d737ffd310e90203cf9dac959fd7c114adf9b1eda6c8ed7bd21`. Normalized comparison excludes no numerical state or callback field.

The auditor computes the new compressed/raw/input identities and checks complete record ordering, contiguous indices, actual grouping/endpoints, finite numeric fields, unchanged floor transforms, all StepListener timestep fields, source-supported action invariants, sleep windows and contact episodes. It cross-checks recorded summaries and query files and emits candidate phase gaps rather than inventing a classification. The parent independently reread all six raw streams with a separate Python audit, checking 432,000 internal states, 252,000 endpoints and 1,296,006 TimeStep payloads, plus event, action and phase checks. Its per-run counts and anchors match, and its separately canonicalized state sequences are identical across all six runs. Neither audit evaluates penetration acceptance.

## Verification and next live review

Extract the linked archive into a fresh directory. From `dyn4k-quality-candidates/`, `sha256sum -c SHA256SUMS` must pass. Audit existing bytes without running physics:

```sh
node source/audit.mjs outer30-repeat1 30 1 /path/to/original/dyn4k-sleep-evidence
```

Repeat for the other five outer-Hz/repetition directories. The original dependency is the [unchanged published archive](https://github.com/rubixhacker/dyn4k/releases/download/calibration-raw-20260914/dyn4j-sleep-wake-20260914.tar.gz); its SHA-256 is `89d88301ad5ea14a621d8a6e86bfc3dfc90f84a0d7e8abda65f2f526de1b5bee`. The auditor verifies its selected 120 Hz gzip/input hashes. Archive README documents compilation/capture reproduction, but running it would be a new physics experiment, not part of read-only verification.

| Scenario | Invocation and binary observable | Captured artifact in experiment worktree |
|---|---|---|
| Freeze, compile, pure grouping | `javac ... Capture.java SleepWakeQuality.java`; `java ... SleepWakeQuality --check-plan`; both exit 0, 72,000 inner steps and expected endpoints/action mapping | `.omo/evidence/quality-experiment/compile.log`, `plan-check.log`, `source-class-hashes.txt`, `recorder.diff` |
| Exactly six sequential fresh captures | `bash .omo/evidence/quality-experiment/run-approved-six.sh`; exit 0, six START/AUDITED pairs, no additional journey | `.omo/evidence/quality-experiment/execution.log`; archive capture logs and summaries |
| All raw capture/event checks | `node docs/research/sleep-wake-quality-capture/audit.mjs RUN_DIR OUTER_HZ REPETITION ORIGINAL_ROOT`; six exit-0 audited results | archive `outer*-repeat*.audit.json` and raw members |
| Frozen source/binary identity | `sha256sum -c .omo/evidence/quality-experiment/frozen-before.sha256`; all entries match before each run/after six | archive per-run preflight logs and `frozen-after.log` |
| Published archive and manifest | remote asset retrieval plus `sha256sum`; package checksum verification; exact count/hash aggregation | `.omo/evidence/quality-experiment/publication.log`, `manifest-validation.log` |

Live review must approve or change the **exact repetition-1 candidate identities** (with repetition-2 corroboration) and **the complete internal-index phase table** before physical acceptance evaluation. If approved, next run the exact/independently certified per-sample physical audit using the unchanged ceilings, including all internal samples and outer mappings. The original physical failures stay failed. Candidate physical quality, port comparisons, all-target runtime, numerical acceptance budgets, performance and release qualification remain unpassed or unresolved. Publishing these candidates closes none of those gates.
