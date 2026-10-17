# Final archive review correction

The [performance manifest task](https://github.com/rubixhacker/dyn4k/issues/17) remains open. This correction closes three independent review findings in the local version 4 audit. It does not establish performance qualification.

## Outcome and source identity

The version 1 manifest remains byte-identical to the prior archive. Its SHA-256 is `18cca97bbf1fc939eda669efe2344bbfe06c416a735ca8cc5184d5ba2519176a`. It still defines 999 scenarios, 21 targets, 28 runtime rows, the approved budgets, and the three fresh 600-second run contract. Historical candidate archives v1, v2, and v3 remain byte-identical to the reviewed head `7c05c7bb5e1f75758e141b1934e098dfab063828`.

The new [CCD fixture revision](performance-ccd-fixture-v2.json) has version `performance-ccd-v2` and SHA-256 `f0ca0b94b8561ffa1dee407a321291a259a3fc72d50bed506b9ea795968eac67`. It links the exact version 1 manifest hash and all 27 CCD workload IDs. Its rule assigns each body a zero-based creation-index hash, starting with the two walls and then the bullet circles. A new fixture counter starts for each world. The [archive fixture record](performance-candidate-v4/fixture-revision.json), SHA-256 `652b11b921e29ee252ed9ca0c90222e7f2b37c66103e3cb3f5cdaf3f47f86d87`, binds the revision to the measured source commit `9ce41f7cc7cfc0a7c7991b02335c5e285159f58d`, Java and Kotlin fixture hashes, the candidate identity, and the raw 27-body identity traces. The verifier independently checks all three raw identity CSVs and requires identical routes.

The version 4 measured CSVs were not recaptured. The CCD hash rule was committed before their capture, and the exact measurement source commit, staged binary hashes, version 1 manifest hash, and measured raw file hashes did not change. The new fixture record formalizes that existing source rule. The provider and six negative-control results were re-executed and refreshed because their audit evidence changed.

## Fail-closed controls

The prior verifier accepted a copied archive with provider `exit_code=1` and an empty-scene reason stating that the control was accepted. A new test first reproduced seven false passes: altered provider exit/core/API hash, renamed or contradictory control, and forged source/core digest. The verifier now checks the provider's exact named routes, zero exit codes, staged core and Kotlin hashes, origin, Java version, and positive process IDs. It re-runs both provider routes. It checks the six exact control names, source raw hash, core artifact hash, synthetic CSV bytes, status, and reason. It independently re-runs the controls. The probe and control scripts are bound to their committed source hashes. Their refreshed records are [provider identity](performance-candidate-v4/provider-identity.json), SHA-256 `1aecf77f93105b4b6e265f0a738472838930982b90e87acb9507ccc1ee0443f8`, and [negative controls](performance-candidate-v4/negative-controls/negative-controls.json), SHA-256 `55fce6c5671204f9f382fb8c56469e8d9e8218aee63e3ea7f7182fda14f9318b`. All six controls rejected. The seven altered copies now fail.

A second copied archive changed a direct process PID to zero, `-1`, or a baseline PID in raw stderr, the index, and derived analysis. All three changes first passed. The verifier now requires a positive, unique PID for every one of the 45 measurement records and both provider records. It still compares each candidate's hashed raw process marker with the index. The three altered copies now fail, while the original 47 process identities pass.

The fixture revision tests first failed because the versioned rule and archive link were absent. Validation now rejects a changed base manifest hash or hash algorithm. The archive rejects a missing fixture record or changed revision or fixture source hash. The supplement does not rewrite the version 1 manifest or historical archives.

## Current audit boundary

The refreshed version 4 archive passes the local verifier with 36 short pilots, three longer timing runs, three memory runs, three plateau runs, six rejected controls, and `source_artifact_audit: verified`. Its candidate identity SHA-256 remains `2268581c6ce00d8c7354034f305e8cac61d29f1bbd88d7ad2538fbe710025a23`. The full owned suite passes 31 tests, including staged CCD construction and 120-step route comparison. These are bounded observations on a loaded JVM host. The staged core still lacks the separate Vector2 and simplex repair commits, so full baseline CCD parity on a coherent integrated artifact remains unproved.

The earlier loaded-host warm-up convergence failure, quiet reference environment, memory attribution, required hardware and probe identities, complete workload/rate/API matrix, and three fresh 600-second repetitions per required case remain open. The 16 MiB workload memory cap and every runtime row remain unqualified. No budget or policy threshold changed.
