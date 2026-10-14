# Exact nominal free-motion reference review

For [Audit the exact nominal free-motion reference bytes](https://github.com/rubixhacker/dyn4k/issues/19), preparing a decision in [Define numerical and migration acceptance](https://github.com/rubixhacker/dyn4k/issues/7).

**The previously missing raw verification is now complete. Reference approval remains PENDING.** The exact published member was retrieved with bounded HTTP ranges, its compressed and input-header hashes match, and every recorded state/event was audited. All 36,000 samples pass the already approved nominal analytical-position check. No simulation was regenerated and no numerical limit was changed.

## Exact candidate for human review

Proposed question: approve the exact nominal free-motion member and [selection manifest](free-motion-reference-review-manifest.json) as reference data for numerical trajectory comparisons, exact discrete/callback behavior, the previously approved analytical-position check, and separately reported physical diagnostics? General baseline-to-port tolerances, other metrics/limits and cross-target runtime results remain unresolved.

| Identity | Value |
|---|---|
| Manifest SHA-256 | `090e8865325707c4a40b1b71c3a652d3a22fab4b6a21e19c23e55cd126f5f117` |
| Tar member | `package/canonical/L-free-s1.0-o0.0_0.0-hz60-0.jsonl.gz` |
| Compressed member size | 3,945,330 bytes |
| Compressed member SHA-256 | `4981795bffcd2a0262040acb53c60b20607fea14a2a0c7d79e858ba68e7f2743` |
| Embedded input header SHA-256, UTF-8 excluding newline | `91f914d3c9993ac238c66e88015861ece560e20333f9e831f3ff4758980b3dd9` |
| Decompressed complete JSONL SHA-256, including newlines | `4a2919c350f61974b8046dd5fe11e0710db37abde26b5db0af909ab4b8d83f78` |

These freshly measured identities match the [pinned original input index](https://github.com/rubixhacker/dyn4k/blob/0995a6bac84de882b0d04b6c3ea18162ca3b4a7c/docs/research/calibration-evidence/input-manifest.jsonl) and [raw audit index](https://github.com/rubixhacker/dyn4k/blob/0995a6bac84de882b0d04b6c3ea18162ca3b4a7c/docs/research/calibration-evidence/audit-manifest.jsonl). The nominal input has one matching row. The audit index has two equal rows for this same filename; the review explicitly checks their equality and treats them as one candidate. It does not count them as independently retrieved repetitions. The state-only derivative identified in the [first packet](https://github.com/rubixhacker/dyn4k/blob/4674e089d6f968bf752741f2be85cf2048962552/docs/research/initial-reference-review.md) is not selected, because it omits ordered events.

## Selective retrieval and verified location

The source is the [original experimental raw release](https://github.com/rubixhacker/dyn4k/releases/tag/calibration-raw-20260914). The release contains a 19,968,512,000-byte uncompressed tar split into fourteen assets. The target is wholly within [part-013](https://github.com/rubixhacker/dyn4k/releases/download/calibration-raw-20260914/dyn4j-baseline-raw.tar.part-013), asset ID `563024290`, size 468,512,000 bytes. Its API/published digest is `a032122d587b3d1919706c4cfbd7205c63f1b88ee646190f0a06ee70b5ac7a26`; **that complete part hash was not independently recomputed**. No complete archive hash is claimed. All asset metadata and published digests are retained in the selection manifest.

| Record | Logical tar offset | Inclusive byte range within part-013 | Size |
|---|---:|---|---:|
| Target header | 19,804,447,744 | `304447744-304448255` | 512 |
| Target gzip payload | 19,804,448,256 | `304448256-308393585` | 3,945,330 |

The validated header names the exact target, declares a regular file and size 3,945,330, and has stored/calculated tar checksum 9,111. Its SHA-256 is `2fd56e4e6c63fc6887f7910fd1b8370633e88b42a687135eb9b122be79866425`.

Discovery visited 408 headers, verified every header checksum and tar magic, and jumped over unrelated payloads using 512-byte alignment. It stopped at the target. The walk transferred 4,154,226 bytes in 409 HTTP requests. The [visited-header index](free-motion-reference-review-headers.tsv) retains all member paths, logical header/data offsets, sizes, types, stored checksums and header hashes; its SHA-256 is `2fe5aa219be20a895cbf3e0d92f7c297703443acac93d4c6d4a39d86a795b33a`. No intervening gzip payload is claimed as verified by that index.

Every accepted range response was HTTP 206 with exactly matching `Content-Range`, total asset size and response length. Requests used curl's `--max-filesize` equal to the requested byte count, a 20-second request deadline, a 25-second process deadline, a maximum 4 MiB logical read and an 8 MiB total payload budget per extraction. Ignoring Range therefore cannot silently download an entire asset. The script validates member SHA-256 before saving the selected gzip. Asset URLs identify locations; these content hashes pin the selected bytes.

The known-offset shortcut was then executed independently: one header request and one payload request, 3,945,842 bytes total. It returned the same gzip hash and passed the same full audit. Historical two-JVM reproducibility remains provenance from the original experiment; downloading the canonical bytes twice is not a new physics repetition.

## Pinned setup, source and capture contract

The baseline is [dyn4j source 058bf6d982a0fb89b54050f929f6ea9dae53b714](https://github.com/dyn4j/dyn4j/tree/058bf6d982a0fb89b54050f929f6ea9dae53b714), published JAR SHA-256 `204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e`. This review audits the published trace against its recorded provenance; it does not rebuild that JAR or establish a new source-to-binary attestation. The capture environment in the [pinned record](https://github.com/rubixhacker/dyn4k/blob/0995a6bac84de882b0d04b6c3ea18162ca3b4a7c/docs/research/calibration-evidence/environment.txt) is OpenJDK 25.0.3 on Bazzite x86_64, AMD Ryzen AI Max+ 395. No additional target was executed.

The [exact recipe](https://github.com/rubixhacker/dyn4k/blob/0995a6bac84de882b0d04b6c3ea18162ca3b4a7c/calibration/src/SceneCases.java) has SHA-256 `ec2a4eabcd5ac278e819ab06c4a22025674bfbec8b6e10773d0b8d9f0c9fd956`; the [recorder](https://github.com/rubixhacker/dyn4k/blob/0995a6bac84de882b0d04b6c3ea18162ca3b4a7c/calibration/src/Capture.java) has SHA-256 `064d701251261b94fd6538ae49a0737aae8e06c673738c36668838676cd31a28`. Both were read and hashed from original experiment revision `0995a6bac84de882b0d04b6c3ea18162ca3b4a7c`; hashes of the original auditor and full indexes are also retained in the manifest.

Exact setup: one normal-mass circle of radius 0.5 m at (0,0), density 1, friction 0.2, restitution 0; initial velocity (0.25,-0.125) m/s and angular velocity 0.5 rad/s. Both damping values and gravity are zero; world rest detection is disabled. No scheduled actions, forces or torques are applied. World scale is 1 and the immutable coordinate origin is (0,0). The fixed binary64 timestep is `1.0/60`, recorded as `0.016666666666666666`; 36,000 explicit steps span 600 simulated seconds. The complete initial body/fixture/mass configuration, solver settings and world configuration match the exact published input object, not just these descriptive values.

Fresh audit found exactly one input record, 36,000 state records at consecutive steps 1 through 36,000, and 108,001 ordered listener events: StepListener `begin`, `postSolve` and `end` occur 36,000 times each; `updatePerformed` occurs once. No action or other record kind is present. Every event carries its step, contiguous within-step order, listener, method signature and payload; state/event traversal cannot skip or reverse a step. JSON parsing rejects literal NaN/infinity and checks every floating token for finiteness, including nested exponent overflow.

Every state contains the single body `b0`, no joints, current/previous transform, world center, fixed-origin position, velocity/angular velocity, sleep flag, force/torque and accumulated force/torque, and rotation increment sum. The body remains awake. Fixed-origin coordinates equal world coordinates minus the pinned origin at every step. Fixture/configuration data is in the initial record. This verifies the recorded per-step/public-listener contract, not a dump of private solver state or arbitrary extension-point coverage. Exact compressed-member identity and all fresh counts agree with the immutable original audit index.

## Recomputed approved analytical check

For each axis and each step `n`, the reference position is calculated independently as `initial_position + initial_velocity * (n * fixed_dt)`. The time term uses the integer step and pinned timestep, not an accumulated clock. Coordinates are compared in the fixed original world frame; origin (0,0) makes the corresponding fixed-origin residual identical.

The existing [human-approved fixture-specific bound](https://github.com/rubixhacker/dyn4k/issues/7#issuecomment-5662494388) is `1e-10` m absolute independently on each component, with no relative allowance. Every required sample must pass.

| Axis | Samples | Maximum absolute error (m) | First step attaining maximum | First violating step | Result |
|---|---:|---:|---:|---|---|
| x | 36,000 | `5.425704330264125e-11` | 35,997 | None | PASS |
| y | 36,000 | `2.7128521651320625e-11` | 35,997 | None | PASS |

These are fresh observations from the exact published raw bytes and reproduce the earlier recorded maxima. They establish this baseline trace's approved analytical-position check only. They do not establish cross-target port tolerances, zero energy/momentum allowances, or limits for rotation, velocities, forces or another fixture.

## Reproduction and remaining decision

Requires Python 3.11+, Git, curl and GitHub CLI access to the public release. The Git checkout must contain original experiment revision `0995a6bac84de882b0d04b6c3ea18162ca3b4a7c`. From this branch, use a new output directory:

```sh
python3 docs/research/free-motion-reference-review-fetch.py NEW_OUTPUT_DIRECTORY 19804447744
python3 docs/research/free-motion-reference-review-audit.py NEW_OUTPUT_DIRECTORY DYN4K_GIT_REPO
```

Omit the final offset argument to reproduce the bounded header walk from zero. The shortcut still validates the header's path/type/size/checksum and the payload's required SHA-256. Both routes were executed successfully. The [fetch script](free-motion-reference-review-fetch.py) SHA-256 is `d4344761e4233d5d65b67e8de71af81fdd724d2e1ff97d2d72c7479607655d88`; the [audit script](free-motion-reference-review-audit.py) SHA-256 is `d3a392805d686e0918419c83d944b997b363dd917289154405d0e72aec81978f`. Python optimized execution is refused because assertions enforce the audit. Output includes retrieval/range/header records and the full audit manifest; source traces are never modified.

The candidate is now ready for explicit reference selection under the [approved review criteria](https://github.com/rubixhacker/dyn4k/issues/7#issuecomment-5662794755). Its role classification and exact manifest remain proposals until approved. This clears the factual raw-audit gap recorded in the first packet; it does not decide the remaining corpus, Weld/Pulley physical bounds, unchanged Java migration/runtime evidence, all-target execution, implementation or release.
