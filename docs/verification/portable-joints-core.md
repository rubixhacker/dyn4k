# Portable core joint source corpus

## Result

At source commit `3e95c97` on `codex/port-coverage-joints-core`, this slice maps all **176** pinned expanded Java cases from six classes. **174** have distinct common Kotlin test methods. Two `DistanceJointTest` null-body calls remain exact JVM Java cases because the common constructor accepts nonnullable body parameters. Both unchanged Java suites executed them. The 32 world-driven simulation identities are tracked separately below.

The pinned upstream checkout is `058bf6d982a0fb89b54050f929f6ea9dae53b714`. The original cases are from [dyn4j 6.0.0 joint tests](https://github.com/dyn4j/dyn4j/tree/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/dynamics/joint). The owner model is confirmed by the raw `turn_context` below as `gpt-6-sol`. No production or integration file changed in this slice.

| Original class | Expanded source cases | Common methods | Java-only |
| --- | ---: | ---: | ---: |
| [AbstractJointTest](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/dynamics/joint/AbstractJointTest.java) | 24 | 24 | 0 |
| [AbstractPairedBodyJointTest](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/dynamics/joint/AbstractPairedBodyJointTest.java) | 19 | 19 | 0 |
| [AbstractSingleBodyJointTest](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/dynamics/joint/AbstractSingleBodyJointTest.java) | 13 | 13 | 0 |
| [DistanceJointTest](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/dynamics/joint/DistanceJointTest.java) | 44 | 42 | 2 |
| [RevoluteJointTest](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/dynamics/joint/RevoluteJointTest.java) | 30 | 30 | 0 |
| [PrismaticJointTest](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/dynamics/joint/PrismaticJointTest.java) | 46 | 46 | 0 |

## Execution and limits

The exact source-commit command used `ANDROID_HOME=/home/stewart/Android/Sdk`, JDK 21, Gradle 9.5.0, offline resolution, one worker, `--rerun-tasks`, and `--continue`. It ran `runBaselineJointTests`, `runUpstreamJointTests`, all six common host tasks, and the staged Java and Kotlin joint consumers. Both unchanged 13-class package suites passed **348/348**; the selected six classes account for **176** identities each. The staged Java consumer printed `JointConsumer OK: 10 concrete joints`; the staged Kotlin consumer printed `JOINT_KOTLIN_CONSUMER_OK`.

Each common host executed exactly the 174 portable identities with no missing, unexpected, duplicate, failure, error, or skip. The Android lane is a host test, not a device. The bundle hash below is SHA-256 of the six raw XML files concatenated in filename order.

The exact-head rerun at `a263d06ae9ff65a1c8d41880b8937ed6e8b6aa96` retained all 36 raw XML files under `/tmp/dyn4k-joint-core-xml/`. Its `manifest.json` lists the 174 expected identities, each host's identity-set digest, and each XML file hash. Every host's normalized identity-set SHA-256 is `64fedab63e928e049a87c5890ada513a99cf9b49cdc2a9b85b9825c9295ff6de`; the archived XML was parsed and compared case by case with the 176 pinned originals minus the two Java-only null cases. The XML bundle hashes below are from this retained rerun.

| Host task | Cases | Failures | Errors | Skips | XML bundle SHA-256 |
| --- | ---: | ---: | ---: | ---: | --- |
| `jvmTest` | 174 | 0 | 0 | 0 | `7cbee9ead79b8b56cc5dcfd9fde0326208a059419a689c8e920acf221136bbe2` |
| `linuxX64Test` | 174 | 0 | 0 | 0 | `a4bc8646db0cf8f8b7ab38efc90a4f726f725adc1f8658f2a22cbdb4d0908cba` |
| `jsNodeTest` | 174 | 0 | 0 | 0 | `e9eb84df013d5be826fbfbf9fcad49d29fb2340aa5145af28afb57f0896ac271` |
| `wasmJsNodeTest` | 174 | 0 | 0 | 0 | `51298b95e757e62685ac6654b0dd40d83031d92332ceec1bf6cc1c89e3df4dff` |
| `wasmWasiNodeTest` | 174 | 0 | 0 | 0 | `a3b21565943ae5ef63587025f84a5a291bbe84694128be374b44f81756234bbf` |
| `testAndroidHostTest` | 174 | 0 | 0 | 0 | `48bdf6dd113c9248bef5a169bcb4105825399a6ea70ae2d4ef78ba6a061300c1` |

The negative oracle check changed the pinned spring-stiffness expectation from `3968.803 ± 0.001` to `3969.803 ± 0.001`. The focused JVM run failed `DistanceJointCoreCoverageTest.computeSpringStiffnessFrequency` with **1 test, 1 failure**. The expectation was restored before source commit `3e95c97`, and all six final host suites passed. The raw session records the edit and failure at [the local turn log](/var/home/stewart/.codex/sessions/2026/10/17/rollout-2026-10-17T14-44-08-01a14b64-a146-71a1-b471-1be8ae8bf581.jsonl:430).

The common tests retain the upstream constructor, anchor, configuration, mode, limit, spring, motor, sleep, copy, and numerical assertion sequences. The copy cases test the public consumer state, deep versus shared body identity, and reaction state after a solver step. The unchanged Java copy tests additionally check protected and package-field identity and solver fields. Java subclass and generated-signature behavior remains exercised by the unchanged Java tests and staged consumers. Expected literals come from the pinned upstream source; no candidate output was used to choose an expected literal.

## XML file evidence

| Host | Common class | Cases | XML SHA-256 |
| --- | --- | ---: | --- |
| `jvmTest` | `AbstractJointCoreCoverageTest` | 24 | `55fe609ea6bf82e3e520ca57b1abada6afe580179cefa2532705ffd4bdb2218a` |
| `jvmTest` | `AbstractPairedBodyJointCoreCoverageTest` | 19 | `59c02f9148d80895f7a9e194ce90bedce6e2f81a25dc7228f2e17db32b3252ec` |
| `jvmTest` | `AbstractSingleBodyJointCoreCoverageTest` | 13 | `8155a49f8c30a840636b7c18be502f6f583a6fec98124e29b89a4a25b2d929f0` |
| `jvmTest` | `DistanceJointCoreCoverageTest` | 42 | `75012370ec87ddfb8fe419647e0acbd82dbb08a47a71e5622ee18397cfa9fa01` |
| `jvmTest` | `PrismaticJointCoreCoverageTest` | 46 | `32800e62546b47e842ff97ed2e53ef771bebc8dec3f43fd0484dcc41de36e2bc` |
| `jvmTest` | `RevoluteJointCoreCoverageTest` | 30 | `66f1b3ad0a24cefb458db1a12e99e0ab2920b5a68cf213956fdcc826c18a5860` |
| `linuxX64Test` | `AbstractJointCoreCoverageTest` | 24 | `d7df537591afe1a450119027e58dbf3c3540447af3e4469e577c641bced437fc` |
| `linuxX64Test` | `AbstractPairedBodyJointCoreCoverageTest` | 19 | `f7eff150532bfd90eec8e486f057d9479bf0bc4639d50be88fd255c63cc8ea2d` |
| `linuxX64Test` | `AbstractSingleBodyJointCoreCoverageTest` | 13 | `a23b5ff81d2fc472c43eed6b4bcb7c8df8b8f77b7ae6ca8ba9a3c456bd23c36e` |
| `linuxX64Test` | `DistanceJointCoreCoverageTest` | 42 | `ee35f437af3a5d3c898c83eb2f37fcbc6d493d8808b1bbc95e4f27a5fe84cf3f` |
| `linuxX64Test` | `PrismaticJointCoreCoverageTest` | 46 | `343478d3f20b9179bed49ff26f8d81841dba2a96eb5f0bfc8ee2d8ecf19fa656` |
| `linuxX64Test` | `RevoluteJointCoreCoverageTest` | 30 | `f5e7f97cef55d1cb6ec53aefe567fa1f509d3e10adadcac034657f19f4a7ba40` |
| `jsNodeTest` | `AbstractJointCoreCoverageTest` | 24 | `2b69722bac9376c2b930b329b4e5c98c031d49217cea8f8f92233680338bb7b0` |
| `jsNodeTest` | `AbstractPairedBodyJointCoreCoverageTest` | 19 | `3b86e39733363226b8d071e1329e6377513a1403ec32d88443354dc5a6acfc51` |
| `jsNodeTest` | `AbstractSingleBodyJointCoreCoverageTest` | 13 | `445018329d6caa3ad3f6fa5e7d2ef7cfb0cb94149ff8df7f76655fb8c51b5736` |
| `jsNodeTest` | `DistanceJointCoreCoverageTest` | 42 | `75ee3c1d95b487665ae7daa1c43801e4dd6d87eec460749a66431cf9e7d3b596` |
| `jsNodeTest` | `PrismaticJointCoreCoverageTest` | 46 | `c18e82e22b3002788418fa51d847b53a8bfa3ab2b9df47f039f4724c6a0588b3` |
| `jsNodeTest` | `RevoluteJointCoreCoverageTest` | 30 | `1cfdf0c8d5bc6b349542a72a4f08876e2f52a1fe0e71a8c10905b62dac022515` |
| `wasmJsNodeTest` | `AbstractJointCoreCoverageTest` | 24 | `80aff270940a2270c3a607f250f3e5475a6834f7aff56e3ceba82e996c106e6d` |
| `wasmJsNodeTest` | `AbstractPairedBodyJointCoreCoverageTest` | 19 | `331956376a8f97a9943c9c03f24fe9306bca48a4bd3f03e9772153137b09246f` |
| `wasmJsNodeTest` | `AbstractSingleBodyJointCoreCoverageTest` | 13 | `5823b070280e3cb23ff77b5d299163270eb4ba32169bb746e9e8d96ff80c19c2` |
| `wasmJsNodeTest` | `DistanceJointCoreCoverageTest` | 42 | `95b62f60aae2e13177ff6fa6c9521dc4eba940142d9c6b6e0b5e60ab1d231421` |
| `wasmJsNodeTest` | `PrismaticJointCoreCoverageTest` | 46 | `cd5d22241a1b94258866d5cb11cb41081ce9da3d0034611c711906ada7eb11d0` |
| `wasmJsNodeTest` | `RevoluteJointCoreCoverageTest` | 30 | `79adc683360751cc6a037bbb51dc6955b9378f29a210798954894717d526f3a0` |
| `wasmWasiNodeTest` | `AbstractJointCoreCoverageTest` | 24 | `8a74798a5bc6a0eefbed3333d49622f37ee872d0ea49e8c3f48fa7c758d0fdb2` |
| `wasmWasiNodeTest` | `AbstractPairedBodyJointCoreCoverageTest` | 19 | `abeb7bd63da5859f987c16aca3e0076d3773a0f2d0e5566ffddaec69901df17c` |
| `wasmWasiNodeTest` | `AbstractSingleBodyJointCoreCoverageTest` | 13 | `9d90da65ba156a662ac620f56fd15c100cc77852b3929215ed1c082fdde9511d` |
| `wasmWasiNodeTest` | `DistanceJointCoreCoverageTest` | 42 | `01f111316948cca899f1a83978a8744e6fe24260cd27295be33cb0dc5b3a756e` |
| `wasmWasiNodeTest` | `PrismaticJointCoreCoverageTest` | 46 | `0151f9f3c567e8cda63c6024520adf1f19343b6d46a08cc44b5cc1055a873b09` |
| `wasmWasiNodeTest` | `RevoluteJointCoreCoverageTest` | 30 | `2058c41bc91986adcb4710c4f78fcbfe9e3ac42dcc4d7ffbccfb401b6462d593` |
| `testAndroidHostTest` | `AbstractJointCoreCoverageTest` | 24 | `bf54f2000ff5ff78be5fb0227617012e71fe725968f266d30aaee2232dfe9c09` |
| `testAndroidHostTest` | `AbstractPairedBodyJointCoreCoverageTest` | 19 | `8f33cf6ce9776df71aef890102fe0415e09aed460778d9720877c35607e3fe1d` |
| `testAndroidHostTest` | `AbstractSingleBodyJointCoreCoverageTest` | 13 | `55d6c7955eca3ad4deb6ba99a8915802ee5c52c40e6c8da8cb42c4660460df29` |
| `testAndroidHostTest` | `DistanceJointCoreCoverageTest` | 42 | `d090cbe0fe0d1fbe019bf95d81d623e67aabd87686aea5291d829dc41065efce` |
| `testAndroidHostTest` | `PrismaticJointCoreCoverageTest` | 46 | `2fb3ff1b8318c43ee6a3608c39b4c6135968a3bb8adc5d589a701b2356179317` |
| `testAndroidHostTest` | `RevoluteJointCoreCoverageTest` | 30 | `3590680c1ecfda0151cf322da1a5dc742cb57f5d477411d70b8566e4ad72191e` |

## Source, fixture, artifact, and log hashes

| Item | SHA-256 |
| --- | --- |
| Pinned identity inventory | `1bc94d6f191d19a4475073c9f5c934bab00f82627bb52b4726711c98daa5c62f` |
| Pinned baseline JVM artifact | `204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e` |
| Candidate JVM artifact | `944b4581beff66b5c1b7c233e54a759a18da312bd689325645cad764bcb0802a` |
| Exact source-commit gate log | `99cfb2aee370fd62e38c383dc1839ad99e304a1409d3a65305e06a905138894b` |
| Retained exact-head gate log | `a5fcb67200a9af69e10d30f101e09dd9c21611a532abd8f76906fbba9652811d` |
| Retained XML identity/count/hash manifest | `2c7f37270d2d93e46ece774b6419c9c2ed4ae12d6d9dfca005064a147187d672` |
| World dependency gate log | `2538770584a4ec0fd5f17608e7fe6819b3a0271fce7b8beb28793a5fcb5992ec` |
| `AbstractJointTest.java` pinned fixture | `0b3f742384f20f23b6c05e771f4046a77e7b850b98d61189912d3e5916fed78f` |
| `AbstractPairedBodyJointTest.java` pinned fixture | `ce94730b4740b00194d80e5ae085d3a4ebcddf74dcbd06edf02611552ed442bc` |
| `AbstractSingleBodyJointTest.java` pinned fixture | `a836eb1a9180312b96323630a93826fd7bc773cc58e91ad1c8c6e2a9ba23c987` |
| `DistanceJointTest.java` pinned fixture | `25b74e0e1df8fd0618797d813c0844c4df5160d9394b263400a380c2aae8ff55` |
| `RevoluteJointTest.java` pinned fixture | `2963cf8ba4237c1580a9cb9ae882506549aafe84b6c5a66e49a53f2b16de2bf7` |
| `PrismaticJointTest.java` pinned fixture | `95aea69f066d17d4cdb72416d02ad3d4c4f767eb4cef953f8b0911045ae17f21` |
| `AbstractJointCoreCoverageTest.kt` | `dcddc66452862fcea766e8708227715eea291cccb42d743a162853fcee9ed243` |
| `DistanceJointCoreCoverageTest.kt` | `8e48295eb645fc769e02db0cf58faf54f2d9f1ee91fb8688147dcfabd64187e8` |
| `RevoluteJointCoreCoverageTest.kt` | `696acd516f192968cc8f189fec8b5191a88baba36320d5cd5a60c893d720047c` |
| `PrismaticJointCoreCoverageTest.kt` | `77f11b629653b19e5b231727873caa83c3e9291b06ecb37955c412a234e4c395` |

## Exact identity disposition

The original identity column is fully qualified. A portable counterpart uses `org.dyn4j.coverage.dynamics.joint.core` plus the class and method shown. The Java-only rows are still executed in both unchanged Java suites.

| Pinned original identity | Common counterpart or disposition |
| --- | --- |
| `org.dyn4j.dynamics.joint.AbstractJointTest#create` | `AbstractJointCoreCoverageTest#create` |
| `org.dyn4j.dynamics.joint.AbstractJointTest#createNullList` | `AbstractJointCoreCoverageTest#createNullList` |
| `org.dyn4j.dynamics.joint.AbstractJointTest#createListWithNullElement` | `AbstractJointCoreCoverageTest#createListWithNullElement` |
| `org.dyn4j.dynamics.joint.AbstractJointTest#createEmptyList` | `AbstractJointCoreCoverageTest#createEmptyList` |
| `org.dyn4j.dynamics.joint.AbstractJointTest#getBodies` | `AbstractJointCoreCoverageTest#getBodies` |
| `org.dyn4j.dynamics.joint.AbstractJointTest#getBodiesAndAdd` | `AbstractJointCoreCoverageTest#getBodiesAndAdd` |
| `org.dyn4j.dynamics.joint.AbstractJointTest#getBodiesAndRemove` | `AbstractJointCoreCoverageTest#getBodiesAndRemove` |
| `org.dyn4j.dynamics.joint.AbstractJointTest#getBodyAtValidIndex` | `AbstractJointCoreCoverageTest#getBodyAtValidIndex` |
| `org.dyn4j.dynamics.joint.AbstractJointTest#getBodyAtNegativeIndex` | `AbstractJointCoreCoverageTest#getBodyAtNegativeIndex` |
| `org.dyn4j.dynamics.joint.AbstractJointTest#getBodyAtTooHighIndex` | `AbstractJointCoreCoverageTest#getBodyAtTooHighIndex` |
| `org.dyn4j.dynamics.joint.AbstractJointTest#getBodyCount` | `AbstractJointCoreCoverageTest#getBodyCount` |
| `org.dyn4j.dynamics.joint.AbstractJointTest#getBodyIterator` | `AbstractJointCoreCoverageTest#getBodyIterator` |
| `org.dyn4j.dynamics.joint.AbstractJointTest#getBodyIteratorRemove` | `AbstractJointCoreCoverageTest#getBodyIteratorRemove` |
| `org.dyn4j.dynamics.joint.AbstractJointTest#isMember` | `AbstractJointCoreCoverageTest#isMember` |
| `org.dyn4j.dynamics.joint.AbstractJointTest#isEnabled` | `AbstractJointCoreCoverageTest#isEnabled` |
| `org.dyn4j.dynamics.joint.AbstractJointTest#getSetCollisionAllowed` | `AbstractJointCoreCoverageTest#getSetCollisionAllowed` |
| `org.dyn4j.dynamics.joint.AbstractJointTest#getSetUserData` | `AbstractJointCoreCoverageTest#getSetUserData` |
| `org.dyn4j.dynamics.joint.AbstractJointTest#getSetOwner` | `AbstractJointCoreCoverageTest#getSetOwner` |
| `org.dyn4j.dynamics.joint.AbstractJointTest#getConstraintImpulseMixing` | `AbstractJointCoreCoverageTest#getConstraintImpulseMixing` |
| `org.dyn4j.dynamics.joint.AbstractJointTest#getErrorReductionParameter` | `AbstractJointCoreCoverageTest#getErrorReductionParameter` |
| `org.dyn4j.dynamics.joint.AbstractJointTest#getFrequency` | `AbstractJointCoreCoverageTest#getFrequency` |
| `org.dyn4j.dynamics.joint.AbstractJointTest#getSpringStiffness` | `AbstractJointCoreCoverageTest#getSpringStiffness` |
| `org.dyn4j.dynamics.joint.AbstractJointTest#getNaturalFrequency` | `AbstractJointCoreCoverageTest#getNaturalFrequency` |
| `org.dyn4j.dynamics.joint.AbstractJointTest#getSpringDampingCoefficient` | `AbstractJointCoreCoverageTest#getSpringDampingCoefficient` |
| `org.dyn4j.dynamics.joint.AbstractPairedBodyJointTest#create` | `AbstractPairedBodyJointCoreCoverageTest#create` |
| `org.dyn4j.dynamics.joint.AbstractPairedBodyJointTest#createNullBody1` | `AbstractPairedBodyJointCoreCoverageTest#createNullBody1` |
| `org.dyn4j.dynamics.joint.AbstractPairedBodyJointTest#createNullBody2` | `AbstractPairedBodyJointCoreCoverageTest#createNullBody2` |
| `org.dyn4j.dynamics.joint.AbstractPairedBodyJointTest#createNullBoth` | `AbstractPairedBodyJointCoreCoverageTest#createNullBoth` |
| `org.dyn4j.dynamics.joint.AbstractPairedBodyJointTest#createSame` | `AbstractPairedBodyJointCoreCoverageTest#createSame` |
| `org.dyn4j.dynamics.joint.AbstractPairedBodyJointTest#getBodies` | `AbstractPairedBodyJointCoreCoverageTest#getBodies` |
| `org.dyn4j.dynamics.joint.AbstractPairedBodyJointTest#getBodiesAndAdd` | `AbstractPairedBodyJointCoreCoverageTest#getBodiesAndAdd` |
| `org.dyn4j.dynamics.joint.AbstractPairedBodyJointTest#getBodiesAndRemove` | `AbstractPairedBodyJointCoreCoverageTest#getBodiesAndRemove` |
| `org.dyn4j.dynamics.joint.AbstractPairedBodyJointTest#getBodyAtValidIndex` | `AbstractPairedBodyJointCoreCoverageTest#getBodyAtValidIndex` |
| `org.dyn4j.dynamics.joint.AbstractPairedBodyJointTest#getBodyAtNegativeIndex` | `AbstractPairedBodyJointCoreCoverageTest#getBodyAtNegativeIndex` |
| `org.dyn4j.dynamics.joint.AbstractPairedBodyJointTest#getBodyAtTooHighIndex` | `AbstractPairedBodyJointCoreCoverageTest#getBodyAtTooHighIndex` |
| `org.dyn4j.dynamics.joint.AbstractPairedBodyJointTest#getBodyCount` | `AbstractPairedBodyJointCoreCoverageTest#getBodyCount` |
| `org.dyn4j.dynamics.joint.AbstractPairedBodyJointTest#getBodyIterator` | `AbstractPairedBodyJointCoreCoverageTest#getBodyIterator` |
| `org.dyn4j.dynamics.joint.AbstractPairedBodyJointTest#getBodyIteratorRemove` | `AbstractPairedBodyJointCoreCoverageTest#getBodyIteratorRemove` |
| `org.dyn4j.dynamics.joint.AbstractPairedBodyJointTest#isMember` | `AbstractPairedBodyJointCoreCoverageTest#isMember` |
| `org.dyn4j.dynamics.joint.AbstractPairedBodyJointTest#isEnabled` | `AbstractPairedBodyJointCoreCoverageTest#isEnabled` |
| `org.dyn4j.dynamics.joint.AbstractPairedBodyJointTest#getOtherBody` | `AbstractPairedBodyJointCoreCoverageTest#getOtherBody` |
| `org.dyn4j.dynamics.joint.AbstractPairedBodyJointTest#getReducedInertia` | `AbstractPairedBodyJointCoreCoverageTest#getReducedInertia` |
| `org.dyn4j.dynamics.joint.AbstractPairedBodyJointTest#getReducedMass` | `AbstractPairedBodyJointCoreCoverageTest#getReducedMass` |
| `org.dyn4j.dynamics.joint.AbstractSingleBodyJointTest#create` | `AbstractSingleBodyJointCoreCoverageTest#create` |
| `org.dyn4j.dynamics.joint.AbstractSingleBodyJointTest#createNullBody` | `AbstractSingleBodyJointCoreCoverageTest#createNullBody` |
| `org.dyn4j.dynamics.joint.AbstractSingleBodyJointTest#getBodies` | `AbstractSingleBodyJointCoreCoverageTest#getBodies` |
| `org.dyn4j.dynamics.joint.AbstractSingleBodyJointTest#getBodiesAndAdd` | `AbstractSingleBodyJointCoreCoverageTest#getBodiesAndAdd` |
| `org.dyn4j.dynamics.joint.AbstractSingleBodyJointTest#getBodiesAndRemove` | `AbstractSingleBodyJointCoreCoverageTest#getBodiesAndRemove` |
| `org.dyn4j.dynamics.joint.AbstractSingleBodyJointTest#getBodyAtValidIndex` | `AbstractSingleBodyJointCoreCoverageTest#getBodyAtValidIndex` |
| `org.dyn4j.dynamics.joint.AbstractSingleBodyJointTest#getBodyAtNegativeIndex` | `AbstractSingleBodyJointCoreCoverageTest#getBodyAtNegativeIndex` |
| `org.dyn4j.dynamics.joint.AbstractSingleBodyJointTest#getBodyAtTooHighIndex` | `AbstractSingleBodyJointCoreCoverageTest#getBodyAtTooHighIndex` |
| `org.dyn4j.dynamics.joint.AbstractSingleBodyJointTest#getBodyCount` | `AbstractSingleBodyJointCoreCoverageTest#getBodyCount` |
| `org.dyn4j.dynamics.joint.AbstractSingleBodyJointTest#getBodyIterator` | `AbstractSingleBodyJointCoreCoverageTest#getBodyIterator` |
| `org.dyn4j.dynamics.joint.AbstractSingleBodyJointTest#getBodyIteratorRemove` | `AbstractSingleBodyJointCoreCoverageTest#getBodyIteratorRemove` |
| `org.dyn4j.dynamics.joint.AbstractSingleBodyJointTest#isMember` | `AbstractSingleBodyJointCoreCoverageTest#isMember` |
| `org.dyn4j.dynamics.joint.AbstractSingleBodyJointTest#isEnabled` | `AbstractSingleBodyJointCoreCoverageTest#isEnabled` |
| `org.dyn4j.dynamics.joint.DistanceJointTest#createWithTwoDifferentBodies` | `DistanceJointCoreCoverageTest#createWithTwoDifferentBodies` |
| `org.dyn4j.dynamics.joint.DistanceJointTest#createWithNullBody1` | Java-only J1 |
| `org.dyn4j.dynamics.joint.DistanceJointTest#createWithNullBody2` | Java-only J1 |
| `org.dyn4j.dynamics.joint.DistanceJointTest#createWithNullAnchor1Point` | `DistanceJointCoreCoverageTest#createWithNullAnchor1Point` |
| `org.dyn4j.dynamics.joint.DistanceJointTest#createWithNullAnchor2Point` | `DistanceJointCoreCoverageTest#createWithNullAnchor2Point` |
| `org.dyn4j.dynamics.joint.DistanceJointTest#createWithSameBody` | `DistanceJointCoreCoverageTest#createWithSameBody` |
| `org.dyn4j.dynamics.joint.DistanceJointTest#shift` | `DistanceJointCoreCoverageTest#shift` |
| `org.dyn4j.dynamics.joint.DistanceJointTest#isSpringEnabled` | `DistanceJointCoreCoverageTest#isSpringEnabled` |
| `org.dyn4j.dynamics.joint.DistanceJointTest#isSpringDamperEnabled` | `DistanceJointCoreCoverageTest#isSpringDamperEnabled` |
| `org.dyn4j.dynamics.joint.DistanceJointTest#setPositiveRestDistance` | `DistanceJointCoreCoverageTest#setPositiveRestDistance` |
| `org.dyn4j.dynamics.joint.DistanceJointTest#setNegativeRestDistance` | `DistanceJointCoreCoverageTest#setNegativeRestDistance` |
| `org.dyn4j.dynamics.joint.DistanceJointTest#setSpringDampingRatio` | `DistanceJointCoreCoverageTest#setSpringDampingRatio` |
| `org.dyn4j.dynamics.joint.DistanceJointTest#setNegativeDampingRatio` | `DistanceJointCoreCoverageTest#setNegativeDampingRatio` |
| `org.dyn4j.dynamics.joint.DistanceJointTest#setDampingRatioGreaterThan1` | `DistanceJointCoreCoverageTest#setDampingRatioGreaterThan1` |
| `org.dyn4j.dynamics.joint.DistanceJointTest#setSpringFrequency` | `DistanceJointCoreCoverageTest#setSpringFrequency` |
| `org.dyn4j.dynamics.joint.DistanceJointTest#setSpringMode` | `DistanceJointCoreCoverageTest#setSpringMode` |
| `org.dyn4j.dynamics.joint.DistanceJointTest#setSpringStiffnessNegative` | `DistanceJointCoreCoverageTest#setSpringStiffnessNegative` |
| `org.dyn4j.dynamics.joint.DistanceJointTest#setSpringStiffness` | `DistanceJointCoreCoverageTest#setSpringStiffness` |
| `org.dyn4j.dynamics.joint.DistanceJointTest#setSpringFrequencyNegative` | `DistanceJointCoreCoverageTest#setSpringFrequencyNegative` |
| `org.dyn4j.dynamics.joint.DistanceJointTest#setSpringMaximumForceNegative` | `DistanceJointCoreCoverageTest#setSpringMaximumForceNegative` |
| `org.dyn4j.dynamics.joint.DistanceJointTest#setSpringMaximumForce` | `DistanceJointCoreCoverageTest#setSpringMaximumForce` |
| `org.dyn4j.dynamics.joint.DistanceJointTest#computeSpringStiffnessFrequency` | `DistanceJointCoreCoverageTest#computeSpringStiffnessFrequency` |
| `org.dyn4j.dynamics.joint.DistanceJointTest#setDistanceAtRest` | `DistanceJointCoreCoverageTest#setDistanceAtRest` |
| `org.dyn4j.dynamics.joint.DistanceJointTest#setUpperLimitSuccess` | `DistanceJointCoreCoverageTest#setUpperLimitSuccess` |
| `org.dyn4j.dynamics.joint.DistanceJointTest#setUpperLimitNegative` | `DistanceJointCoreCoverageTest#setUpperLimitNegative` |
| `org.dyn4j.dynamics.joint.DistanceJointTest#setUpperLimitInvalid` | `DistanceJointCoreCoverageTest#setUpperLimitInvalid` |
| `org.dyn4j.dynamics.joint.DistanceJointTest#setLowerLimit` | `DistanceJointCoreCoverageTest#setLowerLimit` |
| `org.dyn4j.dynamics.joint.DistanceJointTest#setLowerLimitNegative` | `DistanceJointCoreCoverageTest#setLowerLimitNegative` |
| `org.dyn4j.dynamics.joint.DistanceJointTest#setLowerLimitInvalid` | `DistanceJointCoreCoverageTest#setLowerLimitInvalid` |
| `org.dyn4j.dynamics.joint.DistanceJointTest#setUpperAndLowerLimits` | `DistanceJointCoreCoverageTest#setUpperAndLowerLimits` |
| `org.dyn4j.dynamics.joint.DistanceJointTest#setUpperAndLowerLimitsInvalid` | `DistanceJointCoreCoverageTest#setUpperAndLowerLimitsInvalid` |
| `org.dyn4j.dynamics.joint.DistanceJointTest#setUpperAndLowerLimitsNegative` | `DistanceJointCoreCoverageTest#setUpperAndLowerLimitsNegative` |
| `org.dyn4j.dynamics.joint.DistanceJointTest#setUpperAndLowerLimitsNegative2` | `DistanceJointCoreCoverageTest#setUpperAndLowerLimitsNegative2` |
| `org.dyn4j.dynamics.joint.DistanceJointTest#setSameLimitNegative` | `DistanceJointCoreCoverageTest#setSameLimitNegative` |
| `org.dyn4j.dynamics.joint.DistanceJointTest#setSameLimitValid` | `DistanceJointCoreCoverageTest#setSameLimitValid` |
| `org.dyn4j.dynamics.joint.DistanceJointTest#setLimitsEnabledSleep` | `DistanceJointCoreCoverageTest#setLimitsEnabledSleep` |
| `org.dyn4j.dynamics.joint.DistanceJointTest#setLimitsSameSleep` | `DistanceJointCoreCoverageTest#setLimitsSameSleep` |
| `org.dyn4j.dynamics.joint.DistanceJointTest#setLimitsDifferentSleep` | `DistanceJointCoreCoverageTest#setLimitsDifferentSleep` |
| `org.dyn4j.dynamics.joint.DistanceJointTest#setLowerLimitSleep` | `DistanceJointCoreCoverageTest#setLowerLimitSleep` |
| `org.dyn4j.dynamics.joint.DistanceJointTest#setUpperLimitSleep` | `DistanceJointCoreCoverageTest#setUpperLimitSleep` |
| `org.dyn4j.dynamics.joint.DistanceJointTest#setLimitsEnabledSameSleep` | `DistanceJointCoreCoverageTest#setLimitsEnabledSameSleep` |
| `org.dyn4j.dynamics.joint.DistanceJointTest#setLimitsEnabledDifferentSleep` | `DistanceJointCoreCoverageTest#setLimitsEnabledDifferentSleep` |
| `org.dyn4j.dynamics.joint.DistanceJointTest#copy` | `DistanceJointCoreCoverageTest#copy` |
| `org.dyn4j.dynamics.joint.DistanceJointTest#copyFailed` | `DistanceJointCoreCoverageTest#copyFailed` |
| `org.dyn4j.dynamics.joint.PrismaticJointTest#createSuccess` | `PrismaticJointCoreCoverageTest#createSuccess` |
| `org.dyn4j.dynamics.joint.PrismaticJointTest#createWithNullBody1` | `PrismaticJointCoreCoverageTest#createWithNullBody1` |
| `org.dyn4j.dynamics.joint.PrismaticJointTest#createWithNullBody2` | `PrismaticJointCoreCoverageTest#createWithNullBody2` |
| `org.dyn4j.dynamics.joint.PrismaticJointTest#createWithNullAnchor` | `PrismaticJointCoreCoverageTest#createWithNullAnchor` |
| `org.dyn4j.dynamics.joint.PrismaticJointTest#createWithNullAxis` | `PrismaticJointCoreCoverageTest#createWithNullAxis` |
| `org.dyn4j.dynamics.joint.PrismaticJointTest#setMotorMaximumForce` | `PrismaticJointCoreCoverageTest#setMotorMaximumForce` |
| `org.dyn4j.dynamics.joint.PrismaticJointTest#setNegativeMaximumMotorForce` | `PrismaticJointCoreCoverageTest#setNegativeMaximumMotorForce` |
| `org.dyn4j.dynamics.joint.PrismaticJointTest#setMotorMaximumForceSleep` | `PrismaticJointCoreCoverageTest#setMotorMaximumForceSleep` |
| `org.dyn4j.dynamics.joint.PrismaticJointTest#setMotorEnabled` | `PrismaticJointCoreCoverageTest#setMotorEnabled` |
| `org.dyn4j.dynamics.joint.PrismaticJointTest#setMotorEnabledSleep` | `PrismaticJointCoreCoverageTest#setMotorEnabledSleep` |
| `org.dyn4j.dynamics.joint.PrismaticJointTest#setMotorSpeed` | `PrismaticJointCoreCoverageTest#setMotorSpeed` |
| `org.dyn4j.dynamics.joint.PrismaticJointTest#setMotorSpeedSleep` | `PrismaticJointCoreCoverageTest#setMotorSpeedSleep` |
| `org.dyn4j.dynamics.joint.PrismaticJointTest#setReferenceAngle` | `PrismaticJointCoreCoverageTest#setReferenceAngle` |
| `org.dyn4j.dynamics.joint.PrismaticJointTest#shift` | `PrismaticJointCoreCoverageTest#shift` |
| `org.dyn4j.dynamics.joint.PrismaticJointTest#setUpperLimitSuccess` | `PrismaticJointCoreCoverageTest#setUpperLimitSuccess` |
| `org.dyn4j.dynamics.joint.PrismaticJointTest#setUpperLimitInvalid` | `PrismaticJointCoreCoverageTest#setUpperLimitInvalid` |
| `org.dyn4j.dynamics.joint.PrismaticJointTest#setLowerLimit` | `PrismaticJointCoreCoverageTest#setLowerLimit` |
| `org.dyn4j.dynamics.joint.PrismaticJointTest#setLowerLimitInvalid` | `PrismaticJointCoreCoverageTest#setLowerLimitInvalid` |
| `org.dyn4j.dynamics.joint.PrismaticJointTest#setUpperAndLowerLimits` | `PrismaticJointCoreCoverageTest#setUpperAndLowerLimits` |
| `org.dyn4j.dynamics.joint.PrismaticJointTest#setUpperAndLowerLimitsInvalid1` | `PrismaticJointCoreCoverageTest#setUpperAndLowerLimitsInvalid1` |
| `org.dyn4j.dynamics.joint.PrismaticJointTest#setUpperAndLowerLimitsInvalid2` | `PrismaticJointCoreCoverageTest#setUpperAndLowerLimitsInvalid2` |
| `org.dyn4j.dynamics.joint.PrismaticJointTest#setSameLimitValid` | `PrismaticJointCoreCoverageTest#setSameLimitValid` |
| `org.dyn4j.dynamics.joint.PrismaticJointTest#setLimitsEnabledSleep` | `PrismaticJointCoreCoverageTest#setLimitsEnabledSleep` |
| `org.dyn4j.dynamics.joint.PrismaticJointTest#setLimitsSameSleep` | `PrismaticJointCoreCoverageTest#setLimitsSameSleep` |
| `org.dyn4j.dynamics.joint.PrismaticJointTest#setLimitsDifferentSleep` | `PrismaticJointCoreCoverageTest#setLimitsDifferentSleep` |
| `org.dyn4j.dynamics.joint.PrismaticJointTest#setLowerLimitSleep` | `PrismaticJointCoreCoverageTest#setLowerLimitSleep` |
| `org.dyn4j.dynamics.joint.PrismaticJointTest#setUpperLimitSleep` | `PrismaticJointCoreCoverageTest#setUpperLimitSleep` |
| `org.dyn4j.dynamics.joint.PrismaticJointTest#setLimitsEnabledSameSleep` | `PrismaticJointCoreCoverageTest#setLimitsEnabledSameSleep` |
| `org.dyn4j.dynamics.joint.PrismaticJointTest#setLimitsEnabledDifferentSleep` | `PrismaticJointCoreCoverageTest#setLimitsEnabledDifferentSleep` |
| `org.dyn4j.dynamics.joint.PrismaticJointTest#isSpringEnabled` | `PrismaticJointCoreCoverageTest#isSpringEnabled` |
| `org.dyn4j.dynamics.joint.PrismaticJointTest#isSpringDamperEnabled` | `PrismaticJointCoreCoverageTest#isSpringDamperEnabled` |
| `org.dyn4j.dynamics.joint.PrismaticJointTest#setSpringRestOffset` | `PrismaticJointCoreCoverageTest#setSpringRestOffset` |
| `org.dyn4j.dynamics.joint.PrismaticJointTest#setSpringDampingRatio` | `PrismaticJointCoreCoverageTest#setSpringDampingRatio` |
| `org.dyn4j.dynamics.joint.PrismaticJointTest#setNegativeDampingRatio` | `PrismaticJointCoreCoverageTest#setNegativeDampingRatio` |
| `org.dyn4j.dynamics.joint.PrismaticJointTest#setDampingRatioGreaterThan1` | `PrismaticJointCoreCoverageTest#setDampingRatioGreaterThan1` |
| `org.dyn4j.dynamics.joint.PrismaticJointTest#setSpringFrequency` | `PrismaticJointCoreCoverageTest#setSpringFrequency` |
| `org.dyn4j.dynamics.joint.PrismaticJointTest#setSpringMode` | `PrismaticJointCoreCoverageTest#setSpringMode` |
| `org.dyn4j.dynamics.joint.PrismaticJointTest#setSpringStiffnessNegative` | `PrismaticJointCoreCoverageTest#setSpringStiffnessNegative` |
| `org.dyn4j.dynamics.joint.PrismaticJointTest#setSpringStiffness` | `PrismaticJointCoreCoverageTest#setSpringStiffness` |
| `org.dyn4j.dynamics.joint.PrismaticJointTest#setSpringFrequencyNegative` | `PrismaticJointCoreCoverageTest#setSpringFrequencyNegative` |
| `org.dyn4j.dynamics.joint.PrismaticJointTest#setSpringMaximumForceNegative` | `PrismaticJointCoreCoverageTest#setSpringMaximumForceNegative` |
| `org.dyn4j.dynamics.joint.PrismaticJointTest#setSpringMaximumForce` | `PrismaticJointCoreCoverageTest#setSpringMaximumForce` |
| `org.dyn4j.dynamics.joint.PrismaticJointTest#computeSpringStiffnessFrequency` | `PrismaticJointCoreCoverageTest#computeSpringStiffnessFrequency` |
| `org.dyn4j.dynamics.joint.PrismaticJointTest#setSpringRestOffsetAtRest` | `PrismaticJointCoreCoverageTest#setSpringRestOffsetAtRest` |
| `org.dyn4j.dynamics.joint.PrismaticJointTest#copy` | `PrismaticJointCoreCoverageTest#copy` |
| `org.dyn4j.dynamics.joint.PrismaticJointTest#copyFailed` | `PrismaticJointCoreCoverageTest#copyFailed` |
| `org.dyn4j.dynamics.joint.RevoluteJointTest#createSuccess` | `RevoluteJointCoreCoverageTest#createSuccess` |
| `org.dyn4j.dynamics.joint.RevoluteJointTest#createWithNullBody1` | `RevoluteJointCoreCoverageTest#createWithNullBody1` |
| `org.dyn4j.dynamics.joint.RevoluteJointTest#createWithNullBody2` | `RevoluteJointCoreCoverageTest#createWithNullBody2` |
| `org.dyn4j.dynamics.joint.RevoluteJointTest#createWithNullAnchor` | `RevoluteJointCoreCoverageTest#createWithNullAnchor` |
| `org.dyn4j.dynamics.joint.RevoluteJointTest#createWithSameBody` | `RevoluteJointCoreCoverageTest#createWithSameBody` |
| `org.dyn4j.dynamics.joint.RevoluteJointTest#setMaximumMotorTorque` | `RevoluteJointCoreCoverageTest#setMaximumMotorTorque` |
| `org.dyn4j.dynamics.joint.RevoluteJointTest#setMaximumMotorTorqueNegative` | `RevoluteJointCoreCoverageTest#setMaximumMotorTorqueNegative` |
| `org.dyn4j.dynamics.joint.RevoluteJointTest#setMaximumMotorTorqueSleep` | `RevoluteJointCoreCoverageTest#setMaximumMotorTorqueSleep` |
| `org.dyn4j.dynamics.joint.RevoluteJointTest#setMaximumMotorTorqueEnabledSleep` | `RevoluteJointCoreCoverageTest#setMaximumMotorTorqueEnabledSleep` |
| `org.dyn4j.dynamics.joint.RevoluteJointTest#setMotorEnabled` | `RevoluteJointCoreCoverageTest#setMotorEnabled` |
| `org.dyn4j.dynamics.joint.RevoluteJointTest#setMotorEnabledSleep` | `RevoluteJointCoreCoverageTest#setMotorEnabledSleep` |
| `org.dyn4j.dynamics.joint.RevoluteJointTest#setMotorSpeed` | `RevoluteJointCoreCoverageTest#setMotorSpeed` |
| `org.dyn4j.dynamics.joint.RevoluteJointTest#setMotorSpeedSleep` | `RevoluteJointCoreCoverageTest#setMotorSpeedSleep` |
| `org.dyn4j.dynamics.joint.RevoluteJointTest#setUpperLimitSuccess` | `RevoluteJointCoreCoverageTest#setUpperLimitSuccess` |
| `org.dyn4j.dynamics.joint.RevoluteJointTest#setLowerLimit` | `RevoluteJointCoreCoverageTest#setLowerLimit` |
| `org.dyn4j.dynamics.joint.RevoluteJointTest#setUpperAndLowerLimits` | `RevoluteJointCoreCoverageTest#setUpperAndLowerLimits` |
| `org.dyn4j.dynamics.joint.RevoluteJointTest#setUpperAndLowerLimitsToSameValue` | `RevoluteJointCoreCoverageTest#setUpperAndLowerLimitsToSameValue` |
| `org.dyn4j.dynamics.joint.RevoluteJointTest#setLimitsReferenceAngle` | `RevoluteJointCoreCoverageTest#setLimitsReferenceAngle` |
| `org.dyn4j.dynamics.joint.RevoluteJointTest#setLimitsReferenceAngleSleep` | `RevoluteJointCoreCoverageTest#setLimitsReferenceAngleSleep` |
| `org.dyn4j.dynamics.joint.RevoluteJointTest#setLimitEnabledSleep` | `RevoluteJointCoreCoverageTest#setLimitEnabledSleep` |
| `org.dyn4j.dynamics.joint.RevoluteJointTest#setLimitsSameSleep` | `RevoluteJointCoreCoverageTest#setLimitsSameSleep` |
| `org.dyn4j.dynamics.joint.RevoluteJointTest#setLimitsDifferentSleep` | `RevoluteJointCoreCoverageTest#setLimitsDifferentSleep` |
| `org.dyn4j.dynamics.joint.RevoluteJointTest#setLowerLimitSleep` | `RevoluteJointCoreCoverageTest#setLowerLimitSleep` |
| `org.dyn4j.dynamics.joint.RevoluteJointTest#setUpperLimitSleep` | `RevoluteJointCoreCoverageTest#setUpperLimitSleep` |
| `org.dyn4j.dynamics.joint.RevoluteJointTest#setLimitsEnabledSameSleep` | `RevoluteJointCoreCoverageTest#setLimitsEnabledSameSleep` |
| `org.dyn4j.dynamics.joint.RevoluteJointTest#setLimitsEnabledDifferentSleep` | `RevoluteJointCoreCoverageTest#setLimitsEnabledDifferentSleep` |
| `org.dyn4j.dynamics.joint.RevoluteJointTest#setLimitsEnabledSleep` | `RevoluteJointCoreCoverageTest#setLimitsEnabledSleep` |
| `org.dyn4j.dynamics.joint.RevoluteJointTest#shift` | `RevoluteJointCoreCoverageTest#shift` |
| `org.dyn4j.dynamics.joint.RevoluteJointTest#copy` | `RevoluteJointCoreCoverageTest#copy` |
| `org.dyn4j.dynamics.joint.RevoluteJointTest#copyFailed` | `RevoluteJointCoreCoverageTest#copyFailed` |

### Java-only source contract J1

[The pinned `DistanceJointTest` constructor tests](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/dynamics/joint/DistanceJointTest.java) pass `null` as Java body 1 or body 2 and expect `NullPointerException`. The common [`DistanceJoint` constructor](/var/home/stewart/Workspace/dyn4k-port-coverage-joints-core/dyn4k-core/src/commonMain/kotlin/org/dyn4j/dynamics/joint/DistanceJoint.kt) declares both bodies nonnullable. A common Kotlin call with `null as Body` would fail at the cast before entering the constructor, so it would not test the source contract. The two unchanged Java cases pass against both baseline and candidate JVM artifacts. The related abstract paired and Revolute/Prismatic null cases are executable in common Kotlin and are covered there.

## World-driven simulation cases

The 32 identities below are separate from the 176 package cases. At source commit `3e95c97`, unchanged baseline simulation tests passed **32/32**. Candidate `compileUpstreamJointSimulationTests` failed with 93 Java errors because all ten simulation source files import missing `org.dyn4j.world.World`. No candidate world simulation ran. This remains an open dependency of [Step interacting bodies with callbacks and continuous collision](https://github.com/rubixhacker/dyn4k/issues/39).

- `org.dyn4j.simulation.AngleJointSimulationTest#simpleLinkage`
- `org.dyn4j.simulation.AngleJointSimulationTest#withLimitsHitUpper`
- `org.dyn4j.simulation.AngleJointSimulationTest#withLimitsHitLower`
- `org.dyn4j.simulation.DistanceJointSimulationTest#fixedDistance`
- `org.dyn4j.simulation.DistanceJointSimulationTest#limits`
- `org.dyn4j.simulation.DistanceJointSimulationTest#upperLimitWithSpring`
- `org.dyn4j.simulation.DistanceJointSimulationTest#lowerLimitWithSpring`
- `org.dyn4j.simulation.DistanceJointSimulationTest#limitsWithSpring`
- `org.dyn4j.simulation.DistanceJointSimulationTest#springOnly`
- `org.dyn4j.simulation.DistanceJointSimulationTest#springWithMaxForce`
- `org.dyn4j.simulation.FrictionJointSimulationTest#simulationWithLargeForceTorqueMaximums`
- `org.dyn4j.simulation.FrictionJointSimulationTest#simulationWithLowForceTorqueMaximums`
- `org.dyn4j.simulation.MotorJointSimulationTest#simple`
- `org.dyn4j.simulation.PinJointSimulationTest#fixedLinearVelocity`
- `org.dyn4j.simulation.PinJointSimulationTest#noSpringDamper`
- `org.dyn4j.simulation.PrismaticJointSimulationTest#noLimitsNoMotor`
- `org.dyn4j.simulation.PrismaticJointSimulationTest#limits`
- `org.dyn4j.simulation.PrismaticJointSimulationTest#motorWithAndWithoutLimits`
- `org.dyn4j.simulation.PrismaticJointSimulationTest#springOnly`
- `org.dyn4j.simulation.PulleyJointSimulationTest#simpleLinkage`
- `org.dyn4j.simulation.PulleyJointSimulationTest#withAndWithoutSlack`
- `org.dyn4j.simulation.RevoluteJointSimulationTest#noLimitsNoMotor`
- `org.dyn4j.simulation.RevoluteJointSimulationTest#limits`
- `org.dyn4j.simulation.RevoluteJointSimulationTest#motorWithAndWithoutLimits`
- `org.dyn4j.simulation.WeldJointSimulationTest#standard`
- `org.dyn4j.simulation.WeldJointSimulationTest#softConstraint`
- `org.dyn4j.simulation.WeldJointSimulationTest#softConstraintWithLimitsLower`
- `org.dyn4j.simulation.WeldJointSimulationTest#softConstraintWithLimitsUpper`
- `org.dyn4j.simulation.WheelJointSimulationTest#noLimitsNoMotor`
- `org.dyn4j.simulation.WheelJointSimulationTest#limitsOnly`
- `org.dyn4j.simulation.WheelJointSimulationTest#springDamperWithLimits`
- `org.dyn4j.simulation.WheelJointSimulationTest#motorOnly`

## Raw owner context

Source: `/var/home/stewart/.codex/sessions/2026/10/17/rollout-2026-10-17T14-44-08-01a14b64-a146-71a1-b471-1be8ae8bf581.jsonl:8`.

```json
{"timestamp":"2026-10-17T19:44:10.376Z","ordinal":7,"type":"turn_context","payload":{"turn_id":"01a14b64-a216-7df2-ab95-fc356a8b78b5","root_turn_id":"01a14b64-a216-7df2-ab95-fc356a8b78b5","disabled_plugin_ids":[],"cwd":"/var/home/stewart/Workspace/dyn4k-port-coverage-joints-core","approval_policy":"never","approvals_reviewer":"user","sandbox_policy":{"type":"danger-full-access"},"permission_profile":{"type":"disabled"},"model":"gpt-6-sol","comp_hash":"3000","collaboration_mode":{"mode":"default","settings":{"model":"gpt-6-sol","reasoning_effort":"high","developer_instructions":null}},"multi_agent_version":"v2","realtime_active":false,"effort":"high","summary":"none"}}
```

The continuation's raw `turn_context` at `/var/home/stewart/.codex/sessions/2026/10/17/rollout-2026-10-17T14-44-08-01a14b64-a146-71a1-b471-1be8ae8bf581.jsonl:998` also records `payload.model = gpt-6-sol` and the same worktree.

This is a bounded [full compatibility corpus](https://github.com/rubixhacker/dyn4k/issues/42) slice. The 32 candidate world simulations, other joint groups, remaining target families, migration applications, and full qualification stay open.
