# First exact acceptance-reference review packet

Prepared for [Prepare the first exact acceptance-reference review packet](https://github.com/rubixhacker/dyn4k/issues/18) and the human decision [Define numerical and migration acceptance](https://github.com/rubixhacker/dyn4k/issues/7). This is a bounded batch: nominal free motion and the approved supplemental single-body sleep/wake fixture. **Every reference approval remains PENDING.**

## Result and proposed decision

The three supplemental sleep/wake traces have freshly verified archive/member hashes, complete contiguous per-step captured state, ordered listener records, and their required sleep/wake prerequisites. They are concrete candidates for reference selection. The nominal free-motion trace has exact published identities and inspected source, but its raw bytes and capture completeness were not independently rechecked in this review; leave its freeze decision pending that audit.

Proposed human question: **Approve the three exact `run1` sleep/wake members in the manifest as references for the recorded single-body behavior and future numerical comparisons, retaining `run2` as byte-identical corroboration, while leaving free-motion reference selection pending a raw audit and all unapproved numerical limits unresolved?** This selects data, not passing tolerances or cross-target results. Rejecting a member or deferring the whole batch also remains available.

The [selection manifest](initial-reference-review-manifest.json) is the exact proposed selection. SHA-256 of that file: `b42174c7523bea9687e4ab015a215b4e652c2446df73d2f41e836e8a165c1208`. Its approval states are deliberately pending. It records compressed-member hashes separately from the archive hash and from decompressed stream hashes. No state-only derivative is proposed as an ordered-event reference.

## Primary provenance and source identity

Baseline source is [dyn4j revision 058bf6d982a0fb89b54050f929f6ea9dae53b714](https://github.com/dyn4j/dyn4j/tree/058bf6d982a0fb89b54050f929f6ea9dae53b714). The published [dyn4j 6.0.0 JAR](https://repo.maven.apache.org/maven2/org/dyn4j/dyn4j/6.0.0/dyn4j-6.0.0.jar) identity is SHA-256 `204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e`. The copy inside the downloaded sleep archive was independently hashed and matched. This review did not rebuild the upstream JAR or rerun a simulation.

Original experiment files are pinned to [revision 0995a6bac84de882b0d04b6c3ea18162ca3b4a7c](https://github.com/rubixhacker/dyn4k/tree/0995a6bac84de882b0d04b6c3ea18162ca3b4a7c). Their bytes were read from the local Git objects and hashed; relevant hashes match the recorded [final harness inventory](https://github.com/rubixhacker/dyn4k/blob/0995a6bac84de882b0d04b6c3ea18162ca3b4a7c/docs/research/calibration-evidence/corrections/final-harness.sha256).

| Component | SHA-256 | Source |
|---|---|---|
| Shared recorder `Capture.java` | `064d701251261b94fd6538ae49a0737aae8e06c673738c36668838676cd31a28` | [Pinned recorder](https://github.com/rubixhacker/dyn4k/blob/0995a6bac84de882b0d04b6c3ea18162ca3b4a7c/calibration/src/Capture.java); downloaded sleep copy has identical bytes |
| Free-motion recipe `SceneCases.java` | `ec2a4eabcd5ac278e819ab06c4a22025674bfbec8b6e10773d0b8d9f0c9fd956` | [Pinned recipe](https://github.com/rubixhacker/dyn4k/blob/0995a6bac84de882b0d04b6c3ea18162ca3b4a7c/calibration/src/SceneCases.java) |
| Original structural auditor `Audit.java` | `87455eeba05ea6b976decd5df9286e8166c16066c4cec441aff39f9eb5eb87f0` | [Pinned auditor](https://github.com/rubixhacker/dyn4k/blob/0995a6bac84de882b0d04b6c3ea18162ca3b4a7c/calibration/src/Audit.java) |
| Sleep recipe `source/SleepWakeCases.java` | `c808ba452418f6bb88b0eeaf67955ad6691c7e6cdcd1487819d2397640bc00b7` | Member of hashed sleep archive |
| Sleep auditor `source/audit.jq` | `6964af254b100d626fbb61b86222053da651944cace98d1dd7bda01a3f0d4563` | Member of hashed sleep archive |

The [sleep archive download](https://github.com/rubixhacker/dyn4k/releases/download/calibration-raw-20260914/dyn4j-sleep-wake-20260914.tar.gz) contains 2,617,525 bytes; independently verified SHA-256 `89d88301ad5ea14a621d8a6e86bfc3dfc90f84a0d7e8abda65f2f526de1b5bee`. Release asset ID is `563207818`. The download URL alone is not an immutable content identity: the archive hash plus member path and hash pins its content. All 31 entries in its internal `SHA256SUMS` matched after extraction. Archive compression encloses already compressed members, so member byte counts need not be smaller than the outer archive.

The recorded environment is OpenJDK 25.0.3, build `25.0.3+-15898627-b508.16`. The [original environment record](https://github.com/rubixhacker/dyn4k/blob/0995a6bac84de882b0d04b6c3ea18162ca3b4a7c/docs/research/calibration-evidence/environment.txt) additionally identifies Bazzite x86_64 and AMD Ryzen AI Max+ 395. These are capture provenance, not evidence of execution on other targets.

## Nominal free motion: identified, raw verification pending

Exact candidate: `L-free-s1.0-o0.0_0.0-hz60-0.jsonl.gz`. The [immutable input manifest](https://github.com/rubixhacker/dyn4k/blob/0995a6bac84de882b0d04b6c3ea18162ca3b4a7c/docs/research/calibration-evidence/input-manifest.jsonl), [audit manifest](https://github.com/rubixhacker/dyn4k/blob/0995a6bac84de882b0d04b6c3ea18162ca3b4a7c/docs/research/calibration-evidence/audit-manifest.jsonl), and [repeat-A hash index](https://github.com/rubixhacker/dyn4k/blob/0995a6bac84de882b0d04b6c3ea18162ca3b4a7c/docs/research/calibration-evidence/raw-archive/repeat-a-trace-sha256.txt) publish:

- Compressed raw member: 3,945,330 bytes; SHA-256 `4981795bffcd2a0262040acb53c60b20607fea14a2a0c7d79e858ba68e7f2743`.
- Exact input header, UTF-8 excluding newline: SHA-256 `91f914d3c9993ac238c66e88015861ece560e20333f9e831f3ff4758980b3dd9`.
- Published counts: 36,000 states and 108,001 listener events, 144,002 total records. These counts are **index-derived, not freshly audited**. The duplicate audit entry/redundant invocation is not an additional independent candidate.
- The published state derivative hash `e504724fe9c19255392eecb013587ce0ff01f0b7d5467dd404db7d6e6c807cef` identifies a different file that omits listener events; it is not the proposed raw reference.

Inspected setup: one normal-mass circle of radius 0.5 m at (0,0), density 1, friction 0.2, restitution 0; initial linear velocity (0.25,-0.125) m/s and angular velocity 0.5 rad/s. Gravity and both damping values are zero; world rest detection is disabled. Fixed origin (0,0), scale 1; 36,000 calls to `world.step(1, 1.0/60)`, 600 simulated seconds. No scheduled action or external force/torque is applied. Full solver/settings/initial state are fixed by the published input header, not merely these descriptive values.

Proposed roles after raw verification: numerical trajectory parity, per-step analytical position, exact discrete/callback behavior, and momentum/energy diagnostics. The already [approved analytical-position limit](https://github.com/rubixhacker/dyn4k/issues/7#issuecomment-5662494388) is absolute `1e-10` m independently for each component at every required step, with no relative allowance. It applies only to this nominal fixture. The published maximum residuals are observations, not remeasured here. No general port tolerance or zero momentum/energy allowance is inferred.

The [original publication](https://github.com/rubixhacker/dyn4k/blob/0995a6bac84de882b0d04b6c3ea18162ca3b4a7c/docs/research/raw-archive-publication.md) stores canonical members in a 19,968,512,000-byte tar split across 14 assets; per-chunk identities are in the [pinned chunk index](https://github.com/rubixhacker/dyn4k/blob/0995a6bac84de882b0d04b6c3ea18162ca3b4a7c/docs/research/calibration-evidence/raw-archive/chunk-sha256.txt). No member-offset index was identified. This bounded review did not download/reconstruct that corpus. The raw hash, embedded input, finite values, contiguous state/event records, and original captured source/class archive linkage therefore remain unverified here. A separately retrieved raw member matching the published hash can clear this gap without repeating the entire experiment.

## Supplemental sleep/wake: exact proposed selection

The [approved setup](https://github.com/rubixhacker/dyn4k/issues/16#issuecomment-5662863674) fixes a normal-mass 1 m square at (0,0.51) and static 20 by 0.5 m floor at (0,-0.25), density 1, friction 0.5, restitution 0; zero initial velocities/damping and gravity (0,-9.8). Other settings retain baseline defaults including automatic sleep. Fixed coordinate origin is (0,0), scale 1. Each 600-second run uses `dt=1.0/hz` (recorded binary64 input), with no variable timestep or origin shift.

Immediately before step `300*hz+1`, apply impulse (1,0) N s at the square's current center. Natural sleep is required for every sampled state from `299*hz` through `300*hz`, and in the immediate pre-action state. No forced sleep is present in the inspected driver. Initial state, settings, body/fixture identities and world configuration are captured in the first raw record. The full header hash is over UTF-8 bytes excluding the newline.

Select `dyn4k-sleep-evidence/run1/S-sleep-wake-hz{hz}-0.jsonl.gz` from the hashed archive. Corresponding `run2` members have byte-identical gzip contents and remain provenance evidence; they do not create extra coverage.

| Hz | Gzip bytes | Gzip member SHA-256 | Input-header SHA-256 |
|---|---:|---|---|
| 30 | 4,847,331 | `86cfa767974174a2b35fea477ab02451aae21ac5a779ba6e40d12e4874112ebe` | `97f60b69e9aa776a2864347e22328c5735d35830c52fa6c46678bb293d97174a` |
| 60 | 9,675,415 | `ae6fb99402d239569fab8bba950429318879cdb13fb7609833e5f3c7cda68b28` | `cda35b6908693308cee60c9dbf4884a2312f2dac93743747cc32fbf1214a8a35` |
| 120 | 19,937,189 | `5bad36d62dcb0f3b1e2d526d2f1f97e0e62ede99ed9d3da0bef330ba0f510c75` | `e44f7662025777f981e166bc84efb111b527984fe73d36343ca673f540778df5` |

Fresh stream audit observations:

| Hz | Contiguous states | Listener events | First sleep | Impulse step | First return to sleep | Preceding asleep samples |
|---|---:|---:|---:|---:|---:|---:|
| 30 | 18,000 | 233,995 | 18 | 9,001 | 9,022 | 31 |
| 60 | 36,000 | 467,981 | 35 | 18,001 | 18,043 | 61 |
| 120 | 72,000 | 935,967 | 66 | 36,001 | 36,084 | 121 |

Every stream also contains exactly one input record, one impulse action, and two immediate action snapshots (`before-wake`, `after-wake`). Immediately before the impulse the target is asleep; immediately after, it is awake with recorded velocity (1,0). The first following physics state is awake with positive horizontal velocity. These observations freshly reproduce the data assertions underlying the [accepted supplemental evidence](https://github.com/rubixhacker/dyn4k/issues/7#issuecomment-5662926773), without rerunning physics.

Captured state fields are present for both bodies at every step: stable identity, current/previous transform, world center and fixed-origin position, velocity/angular velocity, sleep flag, force/torque and accumulated force/torque, and rotation increment sum. No joints exist in this fixture. Fixture properties and mass/configuration are captured in initial/pre/post-action snapshots. Rotation accumulation is segment-scoped, not a general identity across unrecorded transform mutations.

The inspected recorder registers Contact, TimeOfImpact, Collision, Step, Destruction, and Bounds listeners and serializes callback signature/payload in callback order; boolean callbacks return true. The selected streams contain the first four families, with no destruction/bounds calls observed. Fresh audit checks contiguous within-step order numbers, monotonic step/order pairs, all state steps, parsable finite-number JSON, required state fields, and the action sequence. Thus capture is complete for the recorded per-step/public-listener contract; this is not a dump of every private solver field or a proof of arbitrary extension-point behavior. Both repetitions were checksum-checked and byte-compared; each distinct stream was parsed once.

Proposed roles are separate:

- **Behavioral reference:** natural sleep prerequisite, explicit impulse wake, return to sleep, sleep flags, callback identities/order and discrete outcomes for the exact inputs.
- **Numerical reference:** retained per-step positions, transforms, velocities, forces and recorded numeric callback payloads for future comparisons. Metrics/limits remain unapproved; selecting these bytes does not authorize a numerical pass.
- **Diagnostics:** settling/contact response and timestep differences. Minimum observed square-center y values are approximately 0.4782222, 0.4891111 and 0.4959167 m at 30/60/120 Hz. These observations do not establish acceptable penetration bounds or become tolerances. No energy-conservation condition is proposed for this gravity/friction/contact scene.

## Verification scope and remaining gates

Current review evidence is in `.omo/evidence/reference-review/` in the research worktree. The durable [review auditor](initial-reference-review-audit.py) has SHA-256 `6fd5a7da3f39bc27fc374119808c3a5ed331b955dfe5c7a72d1f81ff57690f46`. Run with Python 3.11 or newer (without `-O`, because assertions enforce the checks and optimized execution is refused), Git, and `sha256sum`:

```sh
gh release download calibration-raw-20260914 --repo rubixhacker/dyn4k \
  --pattern dyn4j-sleep-wake-20260914.tar.gz --dir NEW_EVIDENCE_DIRECTORY
tar -xzf NEW_EVIDENCE_DIRECTORY/dyn4j-sleep-wake-20260914.tar.gz \
  -C NEW_EVIDENCE_DIRECTORY
python3 docs/research/initial-reference-review-audit.py NEW_EVIDENCE_DIRECTORY DYN4K_GIT_REPO
```

The Git checkout must contain original revision `0995a6bac84de882b0d04b6c3ea18162ca3b4a7c`. The auditor emits the full `selection-manifest.json` and `internal-checksums.log` in the evidence directory and prints a summary; compare its archive/member/source hashes against this committed manifest. These output files are replaced on rerun, so use a fresh evidence directory to retain earlier audit results. The recorded review exited 0, verified 31 internal checksums, all 126,000 unique physics states and 1,637,943 listener events. This is independent inspection of published bytes, not a new baseline execution; the archived auditor and simulation reproduction script were read but not rerun. Local evidence retains exact input/action snapshots omitted from the compact committed manifest.

The [approved reference-review criteria](https://github.com/rubixhacker/dyn4k/issues/7#issuecomment-5662794755) require human approval of the exact manifest/hashes. All candidates remain PENDING, and the nominal free-motion raw audit remains a prerequisite to its eligibility recommendation. Cross-target numerical limits, metrics where unnamed, actual port/runtime validation, and physical bounds where unresolved remain open. Archive integrity does not establish physical correctness.

This supplement establishes single-body sleep/wake only. Original failed stack cases and missing stack-wake propagation evidence remain separate. The rest of the corpus still needs individual reference review, including unresolved Weld/Pulley physical bounds/eligibility and the already recorded negative-Angle, CCD, geometry and spring dispositions. The nominal fixture-specific analytical limit does not extend to any of them. Unchanged Java application runtime evidence, exhaustive declaration/test accounting, shared Kotlin/shim scenarios and all approved target/runtime checks also remain required. No engine correction, tolerance widening, reference freeze or release is performed by this packet.
