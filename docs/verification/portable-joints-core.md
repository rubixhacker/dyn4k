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

| Host task | Cases | Failures | Errors | Skips | XML bundle SHA-256 |
| --- | ---: | ---: | ---: | ---: | --- |
| `jvmTest` | 174 | 0 | 0 | 0 | `51b891cbbf90d21404371d2ff1e9faf23c9a9bb2cddd82cc3743d0ced906fa13` |
| `linuxX64Test` | 174 | 0 | 0 | 0 | `254ae8a49dfc8961c6dc781fcb5d503ace7014598589d4eae274663505a30f7b` |
| `jsNodeTest` | 174 | 0 | 0 | 0 | `1beb8533562837c3f54f6ea43b0cbcbcf441b1156b096f4ff9bb7ca6e3a31fe8` |
| `wasmJsNodeTest` | 174 | 0 | 0 | 0 | `2e6e3a123e244e09c2a3a4ae49c21dcce2a8a7667d69dbea99c75de3619664ce` |
| `wasmWasiNodeTest` | 174 | 0 | 0 | 0 | `7d6e95a5247eee9a37174b69f659affe1d5ffda0bee7e708a29f1a47db165eb0` |
| `testAndroidHostTest` | 174 | 0 | 0 | 0 | `c316c76b664bbb4af7d6d778f6f1822ebec8e3e2e89531d69c589af164b4d51f` |

The negative oracle check changed the pinned spring-stiffness expectation from `3968.803 ± 0.001` to `3969.803 ± 0.001`. The focused JVM run failed `DistanceJointCoreCoverageTest.computeSpringStiffnessFrequency` with **1 test, 1 failure**. The expectation was restored before source commit `3e95c97`, and all six final host suites passed. The raw session records the edit and failure at [the local turn log](/var/home/stewart/.codex/sessions/2026/10/17/rollout-2026-10-17T14-44-08-01a14b64-a146-71a1-b471-1be8ae8bf581.jsonl:430).

The common tests retain the upstream constructor, anchor, configuration, mode, limit, spring, motor, sleep, copy, and numerical assertion sequences. The copy cases test the public consumer state, deep versus shared body identity, and reaction state after a solver step. The unchanged Java copy tests additionally check protected and package-field identity and solver fields. Java subclass and generated-signature behavior remains exercised by the unchanged Java tests and staged consumers. Expected literals come from the pinned upstream source; no candidate output was used to choose an expected literal.

## XML file evidence

| Host | Common class | Cases | XML SHA-256 |
| --- | --- | ---: | --- |
| `jvmTest` | `AbstractJointCoreCoverageTest` | 24 | `8e51a862fa4be71167c10428f1411f99fd53ed5c6a29f42294809f6a89b71a23` |
| `jvmTest` | `AbstractPairedBodyJointCoreCoverageTest` | 19 | `2ec9cbd3549021d61425ee3572c3865430b1007a34ef53bae6ab050cc21fbc53` |
| `jvmTest` | `AbstractSingleBodyJointCoreCoverageTest` | 13 | `6881e59ac5c4ec4f9524841772bca84244ea61e4983d31914e5b91a06ca4ce9c` |
| `jvmTest` | `DistanceJointCoreCoverageTest` | 42 | `8991cf6ab77d328b7244ef68bbbd3964a0f912858ea757292763a993de98042f` |
| `jvmTest` | `PrismaticJointCoreCoverageTest` | 46 | `1ab4aa5ab01f978b661e327dfb2cc005a1adced49925f9731f03225a297a75a8` |
| `jvmTest` | `RevoluteJointCoreCoverageTest` | 30 | `849b5992c75f95d64638592fb3073b4ac469eae2fb556523f392f19f10e34d79` |
| `linuxX64Test` | `AbstractJointCoreCoverageTest` | 24 | `9d09c02b40283e1eee1d2aa4180fb67d82cf7d33e5cbcbea36b664a2fac7336e` |
| `linuxX64Test` | `AbstractPairedBodyJointCoreCoverageTest` | 19 | `52d854dbb9744dfcd5e9583481cc8b96076590ddbe28ac28db1e02c0fb14b607` |
| `linuxX64Test` | `AbstractSingleBodyJointCoreCoverageTest` | 13 | `2b5876476b210e262d324960a82179844a37214982dfadacdcbdd8ffd2e5857a` |
| `linuxX64Test` | `DistanceJointCoreCoverageTest` | 42 | `93e229da808038019c4edbb4e63938cb6a15cc75ec0f8d7d345b07c703cd9428` |
| `linuxX64Test` | `PrismaticJointCoreCoverageTest` | 46 | `b94eb93a3ce9fc695ed536009a0c0ddfa6700fc839d505cab146df4fa31feb0e` |
| `linuxX64Test` | `RevoluteJointCoreCoverageTest` | 30 | `c1e16838219ee4bd2aaaf489f022a2bb0a167e1d7bf6d9079f17cb558e56607e` |
| `jsNodeTest` | `AbstractJointCoreCoverageTest` | 24 | `f0867ba58f542395f33cf263e0c0e80e949ad8d16f3d02053ef858bb1c53ca89` |
| `jsNodeTest` | `AbstractPairedBodyJointCoreCoverageTest` | 19 | `8f09ba32bffd262551625d18775470fcd10b664ee4bd5b3b834f2b6e0af5c59d` |
| `jsNodeTest` | `AbstractSingleBodyJointCoreCoverageTest` | 13 | `d6da87f6c7449628bb13d01a1f202d34221f75eb287f865ec4fbd535e27bbf1e` |
| `jsNodeTest` | `DistanceJointCoreCoverageTest` | 42 | `018ec0117b36ebd5ed9a1d72588d0f36f544385b56a8e5ea9505f5350e02c25f` |
| `jsNodeTest` | `PrismaticJointCoreCoverageTest` | 46 | `2f6a270a1cc97bb52fd3db3211badef3befb62da0930f4249c18056fbba2cf37` |
| `jsNodeTest` | `RevoluteJointCoreCoverageTest` | 30 | `ee7ec81caad23aa6a9008f2d0e4027be4fd21b313baa394ee5d89d1534181b0b` |
| `wasmJsNodeTest` | `AbstractJointCoreCoverageTest` | 24 | `15bc6d96cb8c862c2e617e2b2cae3fcd059d24d32048c2cc85be7b6c307ec8ae` |
| `wasmJsNodeTest` | `AbstractPairedBodyJointCoreCoverageTest` | 19 | `0c83a55ceb97e3f0b0b11fd5ca9dc14a05564ff64be3df5f62f47eccfc9dc422` |
| `wasmJsNodeTest` | `AbstractSingleBodyJointCoreCoverageTest` | 13 | `e9af2c0f3efc16da54caea7c7c0bf41661eb7594d42f73ad75f727a66a7602f5` |
| `wasmJsNodeTest` | `DistanceJointCoreCoverageTest` | 42 | `a81459ed62adc3ebf38f68082e5ee3a823e6edfb41f5241a33cd9477ee10b313` |
| `wasmJsNodeTest` | `PrismaticJointCoreCoverageTest` | 46 | `0ccef9d168626be5ae3dfb126621affec224dfebc57fcbd3bf35c4ec7ed69766` |
| `wasmJsNodeTest` | `RevoluteJointCoreCoverageTest` | 30 | `7a018fc635bbfc589cfe11a3414da0ee56f4ed0baae39482a4a14da143b44b9f` |
| `wasmWasiNodeTest` | `AbstractJointCoreCoverageTest` | 24 | `9ad3b4e5b8f54e92218d8ba9f92c4abb1d081af2d19a8b7c506988cdd10c37a1` |
| `wasmWasiNodeTest` | `AbstractPairedBodyJointCoreCoverageTest` | 19 | `207ea061b3f9cec5e95465d34f1ef4599a88d6e8f7e5a9694c9bacc2932a9637` |
| `wasmWasiNodeTest` | `AbstractSingleBodyJointCoreCoverageTest` | 13 | `a82fcbd04fe11cb5ddfa0eb65b5eb6d5a1a17fc6099678409ddfd4e31dfd48f2` |
| `wasmWasiNodeTest` | `DistanceJointCoreCoverageTest` | 42 | `5e9c74b08721529c269263bb9a705cb1106b8a10cd6e5ca08c8c8d079848e1a3` |
| `wasmWasiNodeTest` | `PrismaticJointCoreCoverageTest` | 46 | `112889432f82ab515a2ac4bc36b1e126dc2725ef2c45dff966c6f98e064b3ce5` |
| `wasmWasiNodeTest` | `RevoluteJointCoreCoverageTest` | 30 | `8f23704cd52440df56c66aa595b159ea04ed8b0c7321f07f097579bcb842ef23` |
| `testAndroidHostTest` | `AbstractJointCoreCoverageTest` | 24 | `fd2c0869a27d957d68f061d241417c2f17cceda62e842bc004095547f7a2744f` |
| `testAndroidHostTest` | `AbstractPairedBodyJointCoreCoverageTest` | 19 | `6350f6cea643d3d27a9c5bce07e3517720e6ed0a5944e4b2e072abca57a6263f` |
| `testAndroidHostTest` | `AbstractSingleBodyJointCoreCoverageTest` | 13 | `6a69a3eaf3cc3315fc3832e4c39c861a8de9dd7612afb13b040425dbc8894507` |
| `testAndroidHostTest` | `DistanceJointCoreCoverageTest` | 42 | `f76041391bf7d409b080f34e71ede64d7895c79a7b24ab021d36e9e7806d305c` |
| `testAndroidHostTest` | `PrismaticJointCoreCoverageTest` | 46 | `35d8244c4d68eddd3cc71e762370d6f1a29ff18179d9ed17567719bf9ee44efe` |
| `testAndroidHostTest` | `RevoluteJointCoreCoverageTest` | 30 | `a4243398e207689729e8e13a67f293450022e35cfcc9e2c9b476ed1d776f1c3a` |

## Source, fixture, artifact, and log hashes

| Item | SHA-256 |
| --- | --- |
| Pinned identity inventory | `1bc94d6f191d19a4475073c9f5c934bab00f82627bb52b4726711c98daa5c62f` |
| Pinned baseline JVM artifact | `204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e` |
| Candidate JVM artifact | `944b4581beff66b5c1b7c233e54a759a18da312bd689325645cad764bcb0802a` |
| Exact source-commit gate log | `99cfb2aee370fd62e38c383dc1839ad99e304a1409d3a65305e06a905138894b` |
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

This is a bounded [full compatibility corpus](https://github.com/rubixhacker/dyn4k/issues/42) slice. The 32 candidate world simulations, other joint groups, remaining target families, migration applications, and full qualification stay open.
