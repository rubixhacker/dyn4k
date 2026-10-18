# Complete suite manifest

The tracked [complete suite manifest](../../tools/qualification/full-suite-manifest.json) freezes the cases selected for [Qualify staged artifacts on every required runtime](https://github.com/rubixhacker/dyn4k/issues/43). It is a requirement inventory. It contains no execution result or runtime pass.

## Case identities and provenance

Each case ID is `module:qualified.class.Name#method`. The `area` field assigns one of geometry, collision, dynamics, joints, or compatibility. `scope` is `portable` for a `commonTest` method and `jvm-only` for a facade `jvmTest` method. The source path, SHA-256, and declaration line bind the identity to the committed test. `kind` and `originals` retain the reviewed original-test disposition.

The corpus contains 2,465 core methods, including six collision diagnostics and five rotation observation isolation methods, and 58 portable facade methods. All 2,523 are selected for execution in every required target, runtime, and build configuration. Three additional facade methods are selected on JVM lanes. The 2,353 portable original identities map to 2,253 primary core methods. Five Body supplements link to original behavior but are supplemental methods, not additional originals. The 32 JVM-only original-test dispositions belong to the unchanged Java corpus gate. They are not portable methods and do not become passed cases on another target.

The validator checks every frozen case against the current Kotlin test source tree and the reviewed original and pair maps. A changed source, map, identity, scope, area, target, lane, or gate requires a newly reviewed manifest. The manifest records the pinned original source revision, corpus digest, source-tree digest, and map digests. The current suite file SHA-256 is `54dab38c40cc19e491b517580ca350b80dfcd44b6a35ccce86e0e10bd41b73e6`; its canonical digest is `9aa2f50dd3c38129a70f4ed042f2b7ae5a90d4234def40d70520aad13f36b3fc`. This source reseal adds five case identities and updates hashes or declaration lines for 42 existing cases. All 112 lane identities, scopes, and gates are unchanged. Every applicable lane selects five additional portable cases. Run `python3 tools/qualification/full_suite_manifest.py validate` after any source or map change. The new digest awaits independent review; `independent_gates.py` and `qualify.py` still reject it under their prior approved pins.

## Selection and gates

`select_lane(manifest, lane_id, repository)` in [full_suite_manifest.py](../../tools/qualification/full_suite_manifest.py) validates the manifest and returns `case_ids`, `required_gates`, and `global_gates`. The lane ID is the exact `qualify.expand(qualify.matrix())` ID. All 112 IDs are present: 21 targets, 28 target/runtime families, two runtime versions, and two build configurations. The command `python3 tools/qualification/full_suite_manifest.py select --lane-id 'jvm:Java:minimum:no-optimize'` prints the same selection.

Every lane requires staged target artifacts, an external staged consumer, numerical parity, and physical correctness. JVM lanes also require unchanged Java corpus execution, Java source compatibility, and duplicate-provider diagnosis. The pinned migration journeys, sustained performance and resource checks, publication contract, and independent reviews are global gates. A gate ID is a requirement for separate evidence; its presence in the manifest is not a pass. A failed default physical profile cannot be cleared by a configured-profile pass.

Each `independent_gates` entry names the requirement and its repository evidence sources. These paths identify the fixture, consumer, tool, or policy to evaluate. A later candidate must bind its actual observations and source hashes in a separate gate receipt.

The `qualify.py` full-lane evaluator uses the signed independent adapter when its raw archives, audit, signature, and trusted key are supplied. The adapter selects each lane from this manifest, compares exact observed case identities and counts, and checks separate gate receipts. Missing or invalid evidence cannot pass a lane. This manifest alone qualifies no lane.
