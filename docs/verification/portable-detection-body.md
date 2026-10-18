# Collision body broadphase portable corpus

## Result and scope

This slice maps all **125** executions of the pinned `CollisionBodyBroadphaseTest.java` to common Kotlin tests. The source has 25 `@Test` methods. Its `@Parameters` method runs each against five detectors: SAP with tracking disabled and enabled, dynamic AABB tree with tracking disabled and enabled, and brute force. The common test class contains one `@Test` function for each expanded identity.

| Disposition | Expanded cases |
| --- | ---: |
| Portable common tests | 125 |
| JVM only | 0 |
| Unmapped in this slice | 0 |

The source is `/tmp/dyn4k-upstream-6.0.0/src/test/java/org/dyn4j/collision/broadphase/CollisionBodyBroadphaseTest.java` at upstream revision `058bf6d982a0fb89b54050f929f6ea9dae53b714`. Its SHA-256 is `a6b7bb6c4680ae7bded14411e766c82f182b67972b1722e90c0026bde8126dfb`. The existing full-suite identity map has SHA-256 `4978c0d85575222df3c53d8a5ac71a47858fe99c972db6914caaed043a2b8f43`. It is intentionally unchanged. This report gives the disposition for this disjoint slice; the shared map still labels these rows `UNMAPPED` until integration.

The portable class is `dyn4k-core/src/commonTest/kotlin/org/dyn4j/coverage/collision/detection/broadphase/body/CollisionBodyBroadphaseCoverageTest.kt`, SHA-256 `40ef41c7b8ab6cec1a6f1e164c0bf06c1cb0444eb5a089c5ed65b0f6cdef27e6`. Each source method below maps to the five common functions named `<method>_sap_untracked`, `<method>_sap_tracked`, `<method>_tree_untracked`, `<method>_tree_tracked`, and `<method>_brute_force`. Those suffixes correspond exactly to the five bracketed variants in the unchanged source-case map. The 125 source identities and 125 function names compare with no missing or extra identities.

| Source method | Source declaration line | Common behavior asserted |
| --- | ---: | --- |
| `addContainsBody` | 124 | Body identity, duplicate add, fixture change, size, containment |
| `clear` | 164 | Stored bodies removed and size reset |
| `updateTargeted` | 187 | Targeted update and tracking state after clears |
| `update` | 261 | Whole-detector update and tracking state after clears |
| `removeContainsBody` | 335 | Existing, empty, and absent body removal |
| `getAABB` | 376 | Expanded numeric bounds, empty body, absent multi-fixture body, stored live reference |
| `getAABBExpansionMethod` | 422 | Non-null expansion method |
| `updateSmall` | 431 | Contained motion keeps expanded bounds and does not mark tracked body |
| `updateLarge` | 467 | Motion beyond expansion changes bounds and marks update |
| `getSetUpdateTrackingEnabled` | 498 | Supported toggling and unsupported brute-force no-op |
| `isUpdateTrackingSupported` | 516 | SAP/tree support and brute-force lack of support |
| `optimize` | 530 | Empty and populated optimization without loss of objects |
| `setUpdated` | 549 | Targeted marking, clear, and unsupported no-op |
| `size` | 608 | Body count rather than fixture count |
| `detectConvexAndTransform` | 636 | Body and shape/transform overlap before and after motion |
| `detectIteratorFailure` | 655 | Single pair identity, exhaustion, unsupported removal |
| `raycastIteratorFailure` | 698 | Single body identity, exhaustion, unsupported removal |
| `detectAABBIteratorFailure` | 741 | Two body identities in pinned baseline order, exhaustion, unsupported removal |
| `detectEmptyIterator` | 789 | Empty pair, AABB, and ray iterators |
| `detect` | 813 | One pair with original body identities |
| `detectAABB` | 835 | Exact body identities for two source query boxes |
| `detectRay` | 874 | Exact identities for five source ray queries |
| `shiftCoordinates` | 933 | Pair identity and shifted stored live AABB |
| `getBroadphaseFilter` | 964 | Non-null filter |
| `randomizedTest` | 981 | Source seed and call sequence, with independent rectangle/pair/ray geometry oracle |

The test body is a common Kotlin subclass of the public `AbstractCollisionBody` seam. It retains reference identity and original fixture shapes. Fixed-scene assertions use source geometry and literal expected counts/identities. The seeded case reproduces Java `Random`'s 48-bit algorithm with seed zero, 100 iterations, ten AABB queries and ten ray queries per iteration. Its oracle calculates rectangle intersections and ray/rectangle intersections from input dimensions and positions. It does not use candidate detector output as a reference. The source randomized test requires containment of minimal results; the portable oracle uses the same containment rule because expanded broadphases may return extra candidates.

The source class contains no null-input assertion or Java-only test seam. Its error assertions concern iterator exhaustion and unsupported `remove`; these run on all common hosts. No JVM-only disposition is needed. The source checks result membership for AABB and ray queries, without specifying order among multiple hits. The portable tests also assert the two AABB iterator hits occur as third body, then fourth body. A probe of all five pinned baseline variants returned that order. It is not inferred from candidate output.

## Executed evidence

The unchanged original class was compiled with `javac --release 8` against the pinned baseline JAR, then with `:dyn4k-core:compileUpstreamDetectionTests` against the candidate JAR. The existing `detection-junit.init.gradle` runner executed only `org.dyn4j.collision.broadphase.CollisionBodyBroadphaseTest` under each provider with `--rerun-tasks`. The baseline JAR SHA-256 is `204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e`.

| Original provider | Raw XML | Cases | Failures | Errors | Skips | XML SHA-256 |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| Pinned baseline | `/tmp/dyn4k-coverage-broadphase-body-evidence/baseline-xml/TEST-org.dyn4j.collision.broadphase.CollisionBodyBroadphaseTest.xml` | 125 | 0 | 0 | 0 | `d62b52f386d3c83b9fdb7991899cf685702e37a586fa8ea9428f290c45862510` |
| Candidate | `/tmp/dyn4k-coverage-broadphase-body-evidence/candidate-xml/TEST-org.dyn4j.collision.broadphase.CollisionBodyBroadphaseTest.xml` | 125 | 0 | 0 | 0 | `adba14fc4dff42b282635edf644777f2fa6fb368c9190319f6c4ccb7c700f229` |

The six available common host tasks ran with:

```sh
ANDROID_HOME=/home/stewart/Android/Sdk ./gradlew :dyn4k-core:jvmTest :dyn4k-core:linuxX64Test :dyn4k-core:jsNodeTest :dyn4k-core:wasmJsNodeTest :dyn4k-core:wasmWasiNodeTest :dyn4k-core:testAndroidHostTest --rerun-tasks --console=plain
```

Each lane produced eight XML suites: **186 cases, zero failures, zero errors, zero skips**, including the 125 new cases. SHA-256 below is calculated over sorted XML filename bytes followed by file bytes for each suite. These precommit XML files are archived under `/tmp/dyn4k-coverage-broadphase-body-evidence/precommit/<task>/`.

| Host task | Aggregate raw XML SHA-256 |
| --- | --- |
| `jvmTest` | `5423eb00acef0a5394e3d83587d13e94acd096035874e0ca692ac95c40e34aa1` |
| `linuxX64Test` | `eea4483c4452f777425d1f2c4541e8da5d89a875467b4a21cb821d637ab9cffa` |
| `jsNodeTest` | `8f30e6aea05e9fc0746ffa0a016e65a91cdb9f0758cac822d233c253ca15869a` |
| `wasmJsNodeTest` | `663c1c9630d8dc27106c9f91c3edb0c17b11935beacc99e7934821aa2b819fce` |
| `wasmWasiNodeTest` | `f804dd3325521192a68da48c0a3b1703de455c30946bcbb44f8a3abddb6f2cee` |
| `testAndroidHostTest` | `2b76885e4d1f02f421fc7eddf2b08a5da5c6ff2cb03b0c5d48ff912f554ad137` |

A controlled wrong expectation changed the expanded circle's minimum x bound from `-1.1` to `-1.2`. The focused JVM run failed **1/1** with actual `-1.1`; raw XML is `/tmp/dyn4k-body-controlled-red.xml`, SHA-256 `4bbabc57c2cacc15b07a286c8d278af41cac37f0a14686166725e34ddee0fe3c`. The expectation was restored before the passing run.

The precommit XML archive is `/tmp/dyn4k-coverage-broadphase-body-precommit-xml.tar.gz`, SHA-256 `e939aedf5e2276d46962f3db8383de3700059bf286ccf5b29133660ee838f653`. The CLI handoff records the exact committed revision and its postcommit host replay.

These host executions establish only the listed JVM, Linux x64, Node JS, Node Wasm JS, Node Wasm WASI, and Android JVM host lanes. The Android host task is not an Android device run. The remaining target/runtime matrix and the full detection corpus remain open, as does the integration qualification manifest.
