# Broadphase item coverage

The pinned broadphase subset has **177 expanded source cases**: **169 PORTABLE**, **8 JVM_ONLY**, and **0 UNMAPPED**. This report covers the 145 variants of `CollisionItemBroadphaseTest` and 32 cases in 11 other files. The 125 `CollisionBodyBroadphaseTest` cases belong to a separate slice.

The source is dyn4j 6.0.0 at `058bf6d982a0fb89b54050f929f6ea9dae53b714`. The identity ledger is `dyn4k-core/src/commonTest/kotlin/org/dyn4j/coverage/collision/detection/resources/source-case-map.tsv` (SHA-256 `4978c0d85575222df3c53d8a5ac71a47858fe99c972db6914caaed043a2b8f43`). Each portable case has a named `@Test` under `dyn4k-core/src/commonTest/kotlin/org/dyn4j/coverage/collision/detection/broadphase/item/`. The Kotlin file uses the upstream broadphase package so the Android host can access the baseline's package-private helpers.

## Disposition

The eight JVM_ONLY producer cases pass Java `null` through an API parameter that the Kotlin port declares non-null. Their exact calls are in `CollisionBodyAABBProducerTest` lines 45, 54, 63, and 72, and `CollisionItemAABBProducerTest` lines 48, 57, 66, and 75. The unchanged Java suite exercises these calls on both providers. A common Kotlin probe using an unchecked generic cast exited the Linux native test process at `CollisionBodyAABBProducerTest#computeNull`; the cast does not provide a portable way to call the contract. The abstract detector's nullable constructor is tested in common Kotlin with a concrete probe.

The 29 item methods each execute independently on brute force, SAP with tracking disabled and enabled, and dynamic tree with tracking disabled and enabled. Expectations use fixed circle positions and literal AABB bounds, observed fixture identity, update flags, iterator exhaustion, and conservative geometry checks. The deterministic grid probe checks every physically overlapping circle pair and AABB query coverage. It does not compare one candidate detector to another as its oracle.

## Source files

| Pinned source | SHA-256 | Expanded cases | Portable | JVM-only |
| --- | --- | ---: | ---: | ---: |
| [AABBBroadphaseProxyTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/collision/broadphase/AABBBroadphaseProxyTest.java) | `fccabe58644b529eb52f888e98c170fb4645c6aeb03335f61ed0fc8f7bd2ec5a` | 2 | 2 | 0 |
| [AbstractBroadphaseDetectorTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/collision/broadphase/AbstractBroadphaseDetectorTest.java) | `97bd518452690809d2b52db83f64fda61eb606e8a0899cdfcba8cfd0b4166c54` | 6 | 6 | 0 |
| [AssortedBroadphaseTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/collision/broadphase/AssortedBroadphaseTest.java) | `000daeaf6a1e39eb745d50edc5b475a010afcc92c43252ad50928dd86c70925e` | 3 | 3 | 0 |
| [BroadphaseItemTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/collision/broadphase/BroadphaseItemTest.java) | `089b6c96768b58cec3fdee6e1d137d5b93c839275377f396fa6034b11ac75efc` | 3 | 3 | 0 |
| [CollisionBodyAABBProducerTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/collision/broadphase/CollisionBodyAABBProducerTest.java) | `98cafcd42eb497bf6a42029899d24de6c6b55208a81516108ced7a0f7e48185e` | 5 | 1 | 4 |
| [CollisionBodyBroadphaseFilterTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/collision/broadphase/CollisionBodyBroadphaseFilterTest.java) | `739066426046b0ec4da53729d92ab3072c01b9c2971b9fc71175e0f27729d74d` | 1 | 1 | 0 |
| [CollisionItemAABBProducerTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/collision/broadphase/CollisionItemAABBProducerTest.java) | `e89eb9192587da2ef707d35e1e2a290e21040d6f3d6a91277bb31db1d6504b36` | 5 | 1 | 4 |
| [CollisionItemBroadphaseFilterTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/collision/broadphase/CollisionItemBroadphaseFilterTest.java) | `eb120014ad087ed3ac548e90796aa7be7aa6551f7ea41b157adf39751d0d9ae5` | 1 | 1 | 0 |
| [CollisionItemBroadphasePairTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/collision/broadphase/CollisionItemBroadphasePairTest.java) | `66cdd800def7d631ed98215dcb8aba6104d85e13ac85060d63598f964be6f9c5` | 4 | 4 | 0 |
| [CollisionItemBroadphaseTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/collision/broadphase/CollisionItemBroadphaseTest.java) | `8eadc216e872c14c7e17c520d4949d212c62fff331a5eaae251de6d7600e7b05` | 145 | 145 | 0 |
| [NullAABBExpansionMethodTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/collision/broadphase/NullAABBExpansionMethodTest.java) | `1296610569673f8e88d4693cb6e6f33e737b20d862e7a2a97ea21aa603707ca9` | 1 | 1 | 0 |
| [StaticValueAABBExpansionMethodTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/collision/broadphase/StaticValueAABBExpansionMethodTest.java) | `4df3f8c2baac1d3cec9c131245c296af07df4cce7dbddcddb3d036b3c0e8831f` | 1 | 1 | 0 |

## Expanded case map

The source file and SHA-256 for each row are in the table above. Line numbers are the pinned method declaration lines. Each `PORTABLE` entry names one common test method.

| Source case | Line | Disposition | Executed test |
| --- | ---: | --- | --- |
| `AABBBroadphaseProxyTest#compareTo` | 53 | PORTABLE | `ItemBroadphaseCoverageTest.AABBBroadphaseProxyTest_compareTo` |
| `AABBBroadphaseProxyTest#helpers` | 44 | PORTABLE | `ItemBroadphaseCoverageTest.AABBBroadphaseProxyTest_helpers` |
| `AbstractBroadphaseDetectorTest#createNullAABBExpansionMethod` | 114 | PORTABLE | `ItemBroadphaseCoverageTest.AbstractBroadphaseDetectorTest_createNullAABBExpansionMethod` |
| `AbstractBroadphaseDetectorTest#createNullAABBProducer` | 106 | PORTABLE | `ItemBroadphaseCoverageTest.AbstractBroadphaseDetectorTest_createNullAABBProducer` |
| `AbstractBroadphaseDetectorTest#createNullFilter` | 98 | PORTABLE | `ItemBroadphaseCoverageTest.AbstractBroadphaseDetectorTest_createNullFilter` |
| `AbstractBroadphaseDetectorTest#createSuccess` | 122 | PORTABLE | `ItemBroadphaseCoverageTest.AbstractBroadphaseDetectorTest_createSuccess` |
| `AbstractBroadphaseDetectorTest#detectConvexAndTransform` | 151 | PORTABLE | `ItemBroadphaseCoverageTest.AbstractBroadphaseDetectorTest_detectConvexAndTransform` |
| `AbstractBroadphaseDetectorTest#updateTracking` | 135 | PORTABLE | `ItemBroadphaseCoverageTest.AbstractBroadphaseDetectorTest_updateTracking` |
| `AssortedBroadphaseTest#bruteForceSpecial` | 122 | PORTABLE | `ItemBroadphaseCoverageTest.AssortedBroadphaseTest_bruteForceSpecial` |
| `AssortedBroadphaseTest#dynamicAABBSpecial` | 69 | PORTABLE | `ItemBroadphaseCoverageTest.AssortedBroadphaseTest_dynamicAABBSpecial` |
| `AssortedBroadphaseTest#helpers` | 148 | PORTABLE | `ItemBroadphaseCoverageTest.AssortedBroadphaseTest_helpers` |
| `BroadphaseItemTest#copy` | 60 | PORTABLE | `ItemBroadphaseCoverageTest.BroadphaseItemTest_copy` |
| `BroadphaseItemTest#create` | 45 | PORTABLE | `ItemBroadphaseCoverageTest.BroadphaseItemTest_create` |
| `BroadphaseItemTest#tostring` | 78 | PORTABLE | `ItemBroadphaseCoverageTest.BroadphaseItemTest_tostring` |
| `CollisionBodyAABBProducerTest#computeNull` | 45 | JVM_ONLY | unchanged Java case |
| `CollisionBodyAABBProducerTest#computeNullBody` | 54 | JVM_ONLY | unchanged Java case |
| `CollisionBodyAABBProducerTest#computeNullBoth` | 72 | JVM_ONLY | unchanged Java case |
| `CollisionBodyAABBProducerTest#computeNullResult` | 63 | JVM_ONLY | unchanged Java case |
| `CollisionBodyAABBProducerTest#computeSuccess` | 81 | PORTABLE | `ItemBroadphaseCoverageTest.CollisionBodyAABBProducerTest_computeSuccess` |
| `CollisionBodyBroadphaseFilterTest#isAllowed` | 44 | PORTABLE | `ItemBroadphaseCoverageTest.CollisionBodyBroadphaseFilterTest_isAllowed` |
| `CollisionItemAABBProducerTest#computeNull` | 48 | JVM_ONLY | unchanged Java case |
| `CollisionItemAABBProducerTest#computeNullBody` | 57 | JVM_ONLY | unchanged Java case |
| `CollisionItemAABBProducerTest#computeNullBoth` | 75 | JVM_ONLY | unchanged Java case |
| `CollisionItemAABBProducerTest#computeNullResult` | 66 | JVM_ONLY | unchanged Java case |
| `CollisionItemAABBProducerTest#computeSuccess` | 84 | PORTABLE | `ItemBroadphaseCoverageTest.CollisionItemAABBProducerTest_computeSuccess` |
| `CollisionItemBroadphaseFilterTest#isAllowed` | 47 | PORTABLE | `ItemBroadphaseCoverageTest.CollisionItemBroadphaseFilterTest_isAllowed` |
| `CollisionItemBroadphasePairTest#copy` | 97 | PORTABLE | `ItemBroadphaseCoverageTest.CollisionItemBroadphasePairTest_copy` |
| `CollisionItemBroadphasePairTest#create` | 46 | PORTABLE | `ItemBroadphaseCoverageTest.CollisionItemBroadphasePairTest_create` |
| `CollisionItemBroadphasePairTest#hashcodeEquals` | 68 | PORTABLE | `ItemBroadphaseCoverageTest.CollisionItemBroadphasePairTest_hashcodeEquals` |
| `CollisionItemBroadphasePairTest#tostring` | 127 | PORTABLE | `ItemBroadphaseCoverageTest.CollisionItemBroadphasePairTest_tostring` |
| `CollisionItemBroadphaseTest#addContainsBody[brute_force]` | 134 | PORTABLE | `ItemBroadphaseCoverageTest.addContainsBody_brute_force` |
| `CollisionItemBroadphaseTest#addContainsBody[sap_tracked]` | 134 | PORTABLE | `ItemBroadphaseCoverageTest.addContainsBody_sap_tracked` |
| `CollisionItemBroadphaseTest#addContainsBody[sap_untracked]` | 134 | PORTABLE | `ItemBroadphaseCoverageTest.addContainsBody_sap_untracked` |
| `CollisionItemBroadphaseTest#addContainsBody[tree_tracked]` | 134 | PORTABLE | `ItemBroadphaseCoverageTest.addContainsBody_tree_tracked` |
| `CollisionItemBroadphaseTest#addContainsBody[tree_untracked]` | 134 | PORTABLE | `ItemBroadphaseCoverageTest.addContainsBody_tree_untracked` |
| `CollisionItemBroadphaseTest#addContainsCollisionItem[brute_force]` | 174 | PORTABLE | `ItemBroadphaseCoverageTest.addContainsCollisionItem_brute_force` |
| `CollisionItemBroadphaseTest#addContainsCollisionItem[sap_tracked]` | 174 | PORTABLE | `ItemBroadphaseCoverageTest.addContainsCollisionItem_sap_tracked` |
| `CollisionItemBroadphaseTest#addContainsCollisionItem[sap_untracked]` | 174 | PORTABLE | `ItemBroadphaseCoverageTest.addContainsCollisionItem_sap_untracked` |
| `CollisionItemBroadphaseTest#addContainsCollisionItem[tree_tracked]` | 174 | PORTABLE | `ItemBroadphaseCoverageTest.addContainsCollisionItem_tree_tracked` |
| `CollisionItemBroadphaseTest#addContainsCollisionItem[tree_untracked]` | 174 | PORTABLE | `ItemBroadphaseCoverageTest.addContainsCollisionItem_tree_untracked` |
| `CollisionItemBroadphaseTest#addContainsFixture[brute_force]` | 214 | PORTABLE | `ItemBroadphaseCoverageTest.addContainsFixture_brute_force` |
| `CollisionItemBroadphaseTest#addContainsFixture[sap_tracked]` | 214 | PORTABLE | `ItemBroadphaseCoverageTest.addContainsFixture_sap_tracked` |
| `CollisionItemBroadphaseTest#addContainsFixture[sap_untracked]` | 214 | PORTABLE | `ItemBroadphaseCoverageTest.addContainsFixture_sap_untracked` |
| `CollisionItemBroadphaseTest#addContainsFixture[tree_tracked]` | 214 | PORTABLE | `ItemBroadphaseCoverageTest.addContainsFixture_tree_tracked` |
| `CollisionItemBroadphaseTest#addContainsFixture[tree_untracked]` | 214 | PORTABLE | `ItemBroadphaseCoverageTest.addContainsFixture_tree_untracked` |
| `CollisionItemBroadphaseTest#clear[brute_force]` | 237 | PORTABLE | `ItemBroadphaseCoverageTest.clear_brute_force` |
| `CollisionItemBroadphaseTest#clear[sap_tracked]` | 237 | PORTABLE | `ItemBroadphaseCoverageTest.clear_sap_tracked` |
| `CollisionItemBroadphaseTest#clear[sap_untracked]` | 237 | PORTABLE | `ItemBroadphaseCoverageTest.clear_sap_untracked` |
| `CollisionItemBroadphaseTest#clear[tree_tracked]` | 237 | PORTABLE | `ItemBroadphaseCoverageTest.clear_tree_tracked` |
| `CollisionItemBroadphaseTest#clear[tree_untracked]` | 237 | PORTABLE | `ItemBroadphaseCoverageTest.clear_tree_untracked` |
| `CollisionItemBroadphaseTest#detectAABBIteratorFailure[brute_force]` | 1128 | PORTABLE | `ItemBroadphaseCoverageTest.detectAABBIteratorFailure_brute_force` |
| `CollisionItemBroadphaseTest#detectAABBIteratorFailure[sap_tracked]` | 1128 | PORTABLE | `ItemBroadphaseCoverageTest.detectAABBIteratorFailure_sap_tracked` |
| `CollisionItemBroadphaseTest#detectAABBIteratorFailure[sap_untracked]` | 1128 | PORTABLE | `ItemBroadphaseCoverageTest.detectAABBIteratorFailure_sap_untracked` |
| `CollisionItemBroadphaseTest#detectAABBIteratorFailure[tree_tracked]` | 1128 | PORTABLE | `ItemBroadphaseCoverageTest.detectAABBIteratorFailure_tree_tracked` |
| `CollisionItemBroadphaseTest#detectAABBIteratorFailure[tree_untracked]` | 1128 | PORTABLE | `ItemBroadphaseCoverageTest.detectAABBIteratorFailure_tree_untracked` |
| `CollisionItemBroadphaseTest#detectAABB[brute_force]` | 1237 | PORTABLE | `ItemBroadphaseCoverageTest.detectAABB_brute_force` |
| `CollisionItemBroadphaseTest#detectAABB[sap_tracked]` | 1237 | PORTABLE | `ItemBroadphaseCoverageTest.detectAABB_sap_tracked` |
| `CollisionItemBroadphaseTest#detectAABB[sap_untracked]` | 1237 | PORTABLE | `ItemBroadphaseCoverageTest.detectAABB_sap_untracked` |
| `CollisionItemBroadphaseTest#detectAABB[tree_tracked]` | 1237 | PORTABLE | `ItemBroadphaseCoverageTest.detectAABB_tree_tracked` |
| `CollisionItemBroadphaseTest#detectAABB[tree_untracked]` | 1237 | PORTABLE | `ItemBroadphaseCoverageTest.detectAABB_tree_untracked` |
| `CollisionItemBroadphaseTest#detectConvexAndTransform[brute_force]` | 1021 | PORTABLE | `ItemBroadphaseCoverageTest.detectConvexAndTransform_brute_force` |
| `CollisionItemBroadphaseTest#detectConvexAndTransform[sap_tracked]` | 1021 | PORTABLE | `ItemBroadphaseCoverageTest.detectConvexAndTransform_sap_tracked` |
| `CollisionItemBroadphaseTest#detectConvexAndTransform[sap_untracked]` | 1021 | PORTABLE | `ItemBroadphaseCoverageTest.detectConvexAndTransform_sap_untracked` |
| `CollisionItemBroadphaseTest#detectConvexAndTransform[tree_tracked]` | 1021 | PORTABLE | `ItemBroadphaseCoverageTest.detectConvexAndTransform_tree_tracked` |
| `CollisionItemBroadphaseTest#detectConvexAndTransform[tree_untracked]` | 1021 | PORTABLE | `ItemBroadphaseCoverageTest.detectConvexAndTransform_tree_untracked` |
| `CollisionItemBroadphaseTest#detectEmptyIterator[brute_force]` | 1176 | PORTABLE | `ItemBroadphaseCoverageTest.detectEmptyIterator_brute_force` |
| `CollisionItemBroadphaseTest#detectEmptyIterator[sap_tracked]` | 1176 | PORTABLE | `ItemBroadphaseCoverageTest.detectEmptyIterator_sap_tracked` |
| `CollisionItemBroadphaseTest#detectEmptyIterator[sap_untracked]` | 1176 | PORTABLE | `ItemBroadphaseCoverageTest.detectEmptyIterator_sap_untracked` |
| `CollisionItemBroadphaseTest#detectEmptyIterator[tree_tracked]` | 1176 | PORTABLE | `ItemBroadphaseCoverageTest.detectEmptyIterator_tree_tracked` |
| `CollisionItemBroadphaseTest#detectEmptyIterator[tree_untracked]` | 1176 | PORTABLE | `ItemBroadphaseCoverageTest.detectEmptyIterator_tree_untracked` |
| `CollisionItemBroadphaseTest#detectIteratorFailure[brute_force]` | 1042 | PORTABLE | `ItemBroadphaseCoverageTest.detectIteratorFailure_brute_force` |
| `CollisionItemBroadphaseTest#detectIteratorFailure[sap_tracked]` | 1042 | PORTABLE | `ItemBroadphaseCoverageTest.detectIteratorFailure_sap_tracked` |
| `CollisionItemBroadphaseTest#detectIteratorFailure[sap_untracked]` | 1042 | PORTABLE | `ItemBroadphaseCoverageTest.detectIteratorFailure_sap_untracked` |
| `CollisionItemBroadphaseTest#detectIteratorFailure[tree_tracked]` | 1042 | PORTABLE | `ItemBroadphaseCoverageTest.detectIteratorFailure_tree_tracked` |
| `CollisionItemBroadphaseTest#detectIteratorFailure[tree_untracked]` | 1042 | PORTABLE | `ItemBroadphaseCoverageTest.detectIteratorFailure_tree_untracked` |
| `CollisionItemBroadphaseTest#detectRay[brute_force]` | 1276 | PORTABLE | `ItemBroadphaseCoverageTest.detectRay_brute_force` |
| `CollisionItemBroadphaseTest#detectRay[sap_tracked]` | 1276 | PORTABLE | `ItemBroadphaseCoverageTest.detectRay_sap_tracked` |
| `CollisionItemBroadphaseTest#detectRay[sap_untracked]` | 1276 | PORTABLE | `ItemBroadphaseCoverageTest.detectRay_sap_untracked` |
| `CollisionItemBroadphaseTest#detectRay[tree_tracked]` | 1276 | PORTABLE | `ItemBroadphaseCoverageTest.detectRay_tree_tracked` |
| `CollisionItemBroadphaseTest#detectRay[tree_untracked]` | 1276 | PORTABLE | `ItemBroadphaseCoverageTest.detectRay_tree_untracked` |
| `CollisionItemBroadphaseTest#detect[brute_force]` | 1200 | PORTABLE | `ItemBroadphaseCoverageTest.detect_brute_force` |
| `CollisionItemBroadphaseTest#detect[sap_tracked]` | 1200 | PORTABLE | `ItemBroadphaseCoverageTest.detect_sap_tracked` |
| `CollisionItemBroadphaseTest#detect[sap_untracked]` | 1200 | PORTABLE | `ItemBroadphaseCoverageTest.detect_sap_untracked` |
| `CollisionItemBroadphaseTest#detect[tree_tracked]` | 1200 | PORTABLE | `ItemBroadphaseCoverageTest.detect_tree_tracked` |
| `CollisionItemBroadphaseTest#detect[tree_untracked]` | 1200 | PORTABLE | `ItemBroadphaseCoverageTest.detect_tree_untracked` |
| `CollisionItemBroadphaseTest#getAABBExpansionMethod[brute_force]` | 743 | PORTABLE | `ItemBroadphaseCoverageTest.getAABBExpansionMethod_brute_force` |
| `CollisionItemBroadphaseTest#getAABBExpansionMethod[sap_tracked]` | 743 | PORTABLE | `ItemBroadphaseCoverageTest.getAABBExpansionMethod_sap_tracked` |
| `CollisionItemBroadphaseTest#getAABBExpansionMethod[sap_untracked]` | 743 | PORTABLE | `ItemBroadphaseCoverageTest.getAABBExpansionMethod_sap_untracked` |
| `CollisionItemBroadphaseTest#getAABBExpansionMethod[tree_tracked]` | 743 | PORTABLE | `ItemBroadphaseCoverageTest.getAABBExpansionMethod_tree_tracked` |
| `CollisionItemBroadphaseTest#getAABBExpansionMethod[tree_untracked]` | 743 | PORTABLE | `ItemBroadphaseCoverageTest.getAABBExpansionMethod_tree_untracked` |
| `CollisionItemBroadphaseTest#getAABBProducer[brute_force]` | 723 | PORTABLE | `ItemBroadphaseCoverageTest.getAABBProducer_brute_force` |
| `CollisionItemBroadphaseTest#getAABBProducer[sap_tracked]` | 723 | PORTABLE | `ItemBroadphaseCoverageTest.getAABBProducer_sap_tracked` |
| `CollisionItemBroadphaseTest#getAABBProducer[sap_untracked]` | 723 | PORTABLE | `ItemBroadphaseCoverageTest.getAABBProducer_sap_untracked` |
| `CollisionItemBroadphaseTest#getAABBProducer[tree_tracked]` | 723 | PORTABLE | `ItemBroadphaseCoverageTest.getAABBProducer_tree_tracked` |
| `CollisionItemBroadphaseTest#getAABBProducer[tree_untracked]` | 723 | PORTABLE | `ItemBroadphaseCoverageTest.getAABBProducer_tree_untracked` |
| `CollisionItemBroadphaseTest#getAABB[brute_force]` | 654 | PORTABLE | `ItemBroadphaseCoverageTest.getAABB_brute_force` |
| `CollisionItemBroadphaseTest#getAABB[sap_tracked]` | 654 | PORTABLE | `ItemBroadphaseCoverageTest.getAABB_sap_tracked` |
| `CollisionItemBroadphaseTest#getAABB[sap_untracked]` | 654 | PORTABLE | `ItemBroadphaseCoverageTest.getAABB_sap_untracked` |
| `CollisionItemBroadphaseTest#getAABB[tree_tracked]` | 654 | PORTABLE | `ItemBroadphaseCoverageTest.getAABB_tree_tracked` |
| `CollisionItemBroadphaseTest#getAABB[tree_untracked]` | 654 | PORTABLE | `ItemBroadphaseCoverageTest.getAABB_tree_untracked` |
| `CollisionItemBroadphaseTest#getBroadphaseFilter[brute_force]` | 733 | PORTABLE | `ItemBroadphaseCoverageTest.getBroadphaseFilter_brute_force` |
| `CollisionItemBroadphaseTest#getBroadphaseFilter[sap_tracked]` | 733 | PORTABLE | `ItemBroadphaseCoverageTest.getBroadphaseFilter_sap_tracked` |
| `CollisionItemBroadphaseTest#getBroadphaseFilter[sap_untracked]` | 733 | PORTABLE | `ItemBroadphaseCoverageTest.getBroadphaseFilter_sap_untracked` |
| `CollisionItemBroadphaseTest#getBroadphaseFilter[tree_tracked]` | 733 | PORTABLE | `ItemBroadphaseCoverageTest.getBroadphaseFilter_tree_tracked` |
| `CollisionItemBroadphaseTest#getBroadphaseFilter[tree_untracked]` | 733 | PORTABLE | `ItemBroadphaseCoverageTest.getBroadphaseFilter_tree_untracked` |
| `CollisionItemBroadphaseTest#getSetUpdateTrackingEnabled[brute_force]` | 831 | PORTABLE | `ItemBroadphaseCoverageTest.getSetUpdateTrackingEnabled_brute_force` |
| `CollisionItemBroadphaseTest#getSetUpdateTrackingEnabled[sap_tracked]` | 831 | PORTABLE | `ItemBroadphaseCoverageTest.getSetUpdateTrackingEnabled_sap_tracked` |
| `CollisionItemBroadphaseTest#getSetUpdateTrackingEnabled[sap_untracked]` | 831 | PORTABLE | `ItemBroadphaseCoverageTest.getSetUpdateTrackingEnabled_sap_untracked` |
| `CollisionItemBroadphaseTest#getSetUpdateTrackingEnabled[tree_tracked]` | 831 | PORTABLE | `ItemBroadphaseCoverageTest.getSetUpdateTrackingEnabled_tree_tracked` |
| `CollisionItemBroadphaseTest#getSetUpdateTrackingEnabled[tree_untracked]` | 831 | PORTABLE | `ItemBroadphaseCoverageTest.getSetUpdateTrackingEnabled_tree_untracked` |
| `CollisionItemBroadphaseTest#isUpdateTrackingSupported[brute_force]` | 849 | PORTABLE | `ItemBroadphaseCoverageTest.isUpdateTrackingSupported_brute_force` |
| `CollisionItemBroadphaseTest#isUpdateTrackingSupported[sap_tracked]` | 849 | PORTABLE | `ItemBroadphaseCoverageTest.isUpdateTrackingSupported_sap_tracked` |
| `CollisionItemBroadphaseTest#isUpdateTrackingSupported[sap_untracked]` | 849 | PORTABLE | `ItemBroadphaseCoverageTest.isUpdateTrackingSupported_sap_untracked` |
| `CollisionItemBroadphaseTest#isUpdateTrackingSupported[tree_tracked]` | 849 | PORTABLE | `ItemBroadphaseCoverageTest.isUpdateTrackingSupported_tree_tracked` |
| `CollisionItemBroadphaseTest#isUpdateTrackingSupported[tree_untracked]` | 849 | PORTABLE | `ItemBroadphaseCoverageTest.isUpdateTrackingSupported_tree_untracked` |
| `CollisionItemBroadphaseTest#optimize[brute_force]` | 863 | PORTABLE | `ItemBroadphaseCoverageTest.optimize_brute_force` |
| `CollisionItemBroadphaseTest#optimize[sap_tracked]` | 863 | PORTABLE | `ItemBroadphaseCoverageTest.optimize_sap_tracked` |
| `CollisionItemBroadphaseTest#optimize[sap_untracked]` | 863 | PORTABLE | `ItemBroadphaseCoverageTest.optimize_sap_untracked` |
| `CollisionItemBroadphaseTest#optimize[tree_tracked]` | 863 | PORTABLE | `ItemBroadphaseCoverageTest.optimize_tree_tracked` |
| `CollisionItemBroadphaseTest#optimize[tree_untracked]` | 863 | PORTABLE | `ItemBroadphaseCoverageTest.optimize_tree_untracked` |
| `CollisionItemBroadphaseTest#randomizedTest[brute_force]` | 1386 | PORTABLE | `ItemBroadphaseCoverageTest.randomizedTest_brute_force` |
| `CollisionItemBroadphaseTest#randomizedTest[sap_tracked]` | 1386 | PORTABLE | `ItemBroadphaseCoverageTest.randomizedTest_sap_tracked` |
| `CollisionItemBroadphaseTest#randomizedTest[sap_untracked]` | 1386 | PORTABLE | `ItemBroadphaseCoverageTest.randomizedTest_sap_untracked` |
| `CollisionItemBroadphaseTest#randomizedTest[tree_tracked]` | 1386 | PORTABLE | `ItemBroadphaseCoverageTest.randomizedTest_tree_tracked` |
| `CollisionItemBroadphaseTest#randomizedTest[tree_untracked]` | 1386 | PORTABLE | `ItemBroadphaseCoverageTest.randomizedTest_tree_untracked` |
| `CollisionItemBroadphaseTest#raycastIteratorFailure[brute_force]` | 1085 | PORTABLE | `ItemBroadphaseCoverageTest.raycastIteratorFailure_brute_force` |
| `CollisionItemBroadphaseTest#raycastIteratorFailure[sap_tracked]` | 1085 | PORTABLE | `ItemBroadphaseCoverageTest.raycastIteratorFailure_sap_tracked` |
| `CollisionItemBroadphaseTest#raycastIteratorFailure[sap_untracked]` | 1085 | PORTABLE | `ItemBroadphaseCoverageTest.raycastIteratorFailure_sap_untracked` |
| `CollisionItemBroadphaseTest#raycastIteratorFailure[tree_tracked]` | 1085 | PORTABLE | `ItemBroadphaseCoverageTest.raycastIteratorFailure_tree_tracked` |
| `CollisionItemBroadphaseTest#raycastIteratorFailure[tree_untracked]` | 1085 | PORTABLE | `ItemBroadphaseCoverageTest.raycastIteratorFailure_tree_untracked` |
| `CollisionItemBroadphaseTest#removeContainsBody[brute_force]` | 552 | PORTABLE | `ItemBroadphaseCoverageTest.removeContainsBody_brute_force` |
| `CollisionItemBroadphaseTest#removeContainsBody[sap_tracked]` | 552 | PORTABLE | `ItemBroadphaseCoverageTest.removeContainsBody_sap_tracked` |
| `CollisionItemBroadphaseTest#removeContainsBody[sap_untracked]` | 552 | PORTABLE | `ItemBroadphaseCoverageTest.removeContainsBody_sap_untracked` |
| `CollisionItemBroadphaseTest#removeContainsBody[tree_tracked]` | 552 | PORTABLE | `ItemBroadphaseCoverageTest.removeContainsBody_tree_tracked` |
| `CollisionItemBroadphaseTest#removeContainsBody[tree_untracked]` | 552 | PORTABLE | `ItemBroadphaseCoverageTest.removeContainsBody_tree_untracked` |
| `CollisionItemBroadphaseTest#removeContainsFixture[brute_force]` | 607 | PORTABLE | `ItemBroadphaseCoverageTest.removeContainsFixture_brute_force` |
| `CollisionItemBroadphaseTest#removeContainsFixture[sap_tracked]` | 607 | PORTABLE | `ItemBroadphaseCoverageTest.removeContainsFixture_sap_tracked` |
| `CollisionItemBroadphaseTest#removeContainsFixture[sap_untracked]` | 607 | PORTABLE | `ItemBroadphaseCoverageTest.removeContainsFixture_sap_untracked` |
| `CollisionItemBroadphaseTest#removeContainsFixture[tree_tracked]` | 607 | PORTABLE | `ItemBroadphaseCoverageTest.removeContainsFixture_tree_tracked` |
| `CollisionItemBroadphaseTest#removeContainsFixture[tree_untracked]` | 607 | PORTABLE | `ItemBroadphaseCoverageTest.removeContainsFixture_tree_untracked` |
| `CollisionItemBroadphaseTest#setUpdated[brute_force]` | 882 | PORTABLE | `ItemBroadphaseCoverageTest.setUpdated_brute_force` |
| `CollisionItemBroadphaseTest#setUpdated[sap_tracked]` | 882 | PORTABLE | `ItemBroadphaseCoverageTest.setUpdated_sap_tracked` |
| `CollisionItemBroadphaseTest#setUpdated[sap_untracked]` | 882 | PORTABLE | `ItemBroadphaseCoverageTest.setUpdated_sap_untracked` |
| `CollisionItemBroadphaseTest#setUpdated[tree_tracked]` | 882 | PORTABLE | `ItemBroadphaseCoverageTest.setUpdated_tree_tracked` |
| `CollisionItemBroadphaseTest#setUpdated[tree_untracked]` | 882 | PORTABLE | `ItemBroadphaseCoverageTest.setUpdated_tree_untracked` |
| `CollisionItemBroadphaseTest#shiftCoordinates[brute_force]` | 1335 | PORTABLE | `ItemBroadphaseCoverageTest.shiftCoordinates_brute_force` |
| `CollisionItemBroadphaseTest#shiftCoordinates[sap_tracked]` | 1335 | PORTABLE | `ItemBroadphaseCoverageTest.shiftCoordinates_sap_tracked` |
| `CollisionItemBroadphaseTest#shiftCoordinates[sap_untracked]` | 1335 | PORTABLE | `ItemBroadphaseCoverageTest.shiftCoordinates_sap_untracked` |
| `CollisionItemBroadphaseTest#shiftCoordinates[tree_tracked]` | 1335 | PORTABLE | `ItemBroadphaseCoverageTest.shiftCoordinates_tree_tracked` |
| `CollisionItemBroadphaseTest#shiftCoordinates[tree_untracked]` | 1335 | PORTABLE | `ItemBroadphaseCoverageTest.shiftCoordinates_tree_untracked` |
| `CollisionItemBroadphaseTest#size[brute_force]` | 993 | PORTABLE | `ItemBroadphaseCoverageTest.size_brute_force` |
| `CollisionItemBroadphaseTest#size[sap_tracked]` | 993 | PORTABLE | `ItemBroadphaseCoverageTest.size_sap_tracked` |
| `CollisionItemBroadphaseTest#size[sap_untracked]` | 993 | PORTABLE | `ItemBroadphaseCoverageTest.size_sap_untracked` |
| `CollisionItemBroadphaseTest#size[tree_tracked]` | 993 | PORTABLE | `ItemBroadphaseCoverageTest.size_tree_tracked` |
| `CollisionItemBroadphaseTest#size[tree_untracked]` | 993 | PORTABLE | `ItemBroadphaseCoverageTest.size_tree_untracked` |
| `CollisionItemBroadphaseTest#updateLarge[brute_force]` | 797 | PORTABLE | `ItemBroadphaseCoverageTest.updateLarge_brute_force` |
| `CollisionItemBroadphaseTest#updateLarge[sap_tracked]` | 797 | PORTABLE | `ItemBroadphaseCoverageTest.updateLarge_sap_tracked` |
| `CollisionItemBroadphaseTest#updateLarge[sap_untracked]` | 797 | PORTABLE | `ItemBroadphaseCoverageTest.updateLarge_sap_untracked` |
| `CollisionItemBroadphaseTest#updateLarge[tree_tracked]` | 797 | PORTABLE | `ItemBroadphaseCoverageTest.updateLarge_tree_tracked` |
| `CollisionItemBroadphaseTest#updateLarge[tree_untracked]` | 797 | PORTABLE | `ItemBroadphaseCoverageTest.updateLarge_tree_untracked` |
| `CollisionItemBroadphaseTest#updateSmall[brute_force]` | 758 | PORTABLE | `ItemBroadphaseCoverageTest.updateSmall_brute_force` |
| `CollisionItemBroadphaseTest#updateSmall[sap_tracked]` | 758 | PORTABLE | `ItemBroadphaseCoverageTest.updateSmall_sap_tracked` |
| `CollisionItemBroadphaseTest#updateSmall[sap_untracked]` | 758 | PORTABLE | `ItemBroadphaseCoverageTest.updateSmall_sap_untracked` |
| `CollisionItemBroadphaseTest#updateSmall[tree_tracked]` | 758 | PORTABLE | `ItemBroadphaseCoverageTest.updateSmall_tree_tracked` |
| `CollisionItemBroadphaseTest#updateSmall[tree_untracked]` | 758 | PORTABLE | `ItemBroadphaseCoverageTest.updateSmall_tree_untracked` |
| `CollisionItemBroadphaseTest#updateTargeted[brute_force]` | 262 | PORTABLE | `ItemBroadphaseCoverageTest.updateTargeted_brute_force` |
| `CollisionItemBroadphaseTest#updateTargeted[sap_tracked]` | 262 | PORTABLE | `ItemBroadphaseCoverageTest.updateTargeted_sap_tracked` |
| `CollisionItemBroadphaseTest#updateTargeted[sap_untracked]` | 262 | PORTABLE | `ItemBroadphaseCoverageTest.updateTargeted_sap_untracked` |
| `CollisionItemBroadphaseTest#updateTargeted[tree_tracked]` | 262 | PORTABLE | `ItemBroadphaseCoverageTest.updateTargeted_tree_tracked` |
| `CollisionItemBroadphaseTest#updateTargeted[tree_untracked]` | 262 | PORTABLE | `ItemBroadphaseCoverageTest.updateTargeted_tree_untracked` |
| `CollisionItemBroadphaseTest#update[brute_force]` | 417 | PORTABLE | `ItemBroadphaseCoverageTest.update_brute_force` |
| `CollisionItemBroadphaseTest#update[sap_tracked]` | 417 | PORTABLE | `ItemBroadphaseCoverageTest.update_sap_tracked` |
| `CollisionItemBroadphaseTest#update[sap_untracked]` | 417 | PORTABLE | `ItemBroadphaseCoverageTest.update_sap_untracked` |
| `CollisionItemBroadphaseTest#update[tree_tracked]` | 417 | PORTABLE | `ItemBroadphaseCoverageTest.update_tree_tracked` |
| `CollisionItemBroadphaseTest#update[tree_untracked]` | 417 | PORTABLE | `ItemBroadphaseCoverageTest.update_tree_untracked` |
| `NullAABBExpansionMethodTest#expand` | 43 | PORTABLE | `ItemBroadphaseCoverageTest.NullAABBExpansionMethodTest_expand` |
| `StaticValueAABBExpansionMethodTest#expand` | 43 | PORTABLE | `ItemBroadphaseCoverageTest.StaticValueAABBExpansionMethodTest_expand` |

## Verification

The unchanged Java subset was compiled from the pinned source with `javac --release 8` for the baseline and `:dyn4k-core:compileUpstreamDetectionTests` for the candidate. `detectionJUnitEvidence` selected the 12 exact classes. Each provider produced 12 raw XML suites, **177 tests, 0 failures, 0 errors, 0 skips**. Aggregate SHA-256 over sorted XML basename, a zero byte, and file bytes: baseline `c2124fe9df44993bd5a969281a695b0627366fdacd3e25ef1e0c2a9eda712de8`; candidate `03a1454584da53098270246708e9cc0a5cbdb4cde06b16fab54c0d45a1fa5fb7`. Raw XML is in `/tmp/dyn4k-coverage-broadphase-item/{baseline,candidate}/`.

All six common host tasks ran with `--rerun-tasks --continue`. Each produced eight XML suites, **230 tests, 0 failures, 0 errors, 0 skips**: 169 new mapped tests plus 61 pre-existing tests. The raw XML is in `/tmp/dyn4k-coverage-broadphase-item/host/<task>/`. The combined raw XML archive is `/tmp/dyn4k-coverage-broadphase-item-xml.tar.gz`, SHA-256 `9fa33b810168874d9d61968d999ad707619b2318448c1a1c765cc8afd9c231b4`.

| Host task | Aggregate XML SHA-256 |
| --- | --- |
| `jvmTest` | `a9c9094ace41f7978aff86eaa7a81c1a17a7afc8f0cf4760a30cef43a10d3293` |
| `linuxX64Test` | `a1e1653d0dabb8a5ed7beaa2ac1fbc152f3c440345f1c8f24b90b1c590ceeb74` |
| `jsNodeTest` | `53880e5cbce1ecf61da1973b1c4036977ab9df5d06093ca915efc5f3935dedff` |
| `wasmJsNodeTest` | `16d860182d01b65e28b69b578a96b680a351414fb111538b9b5b1905e942914d` |
| `wasmWasiNodeTest` | `1caa284f14f1a8c0550efc412027a5b614353299356a32cb0d9402725edd53d1` |
| `testAndroidHostTest` | `b46104b57312a747265a78104068c4c63c92c3613fdfaee585c341f1c6a68e2e` |

A controlled wrong expectation changed the `addContainsBody_brute_force` fixture count from 2 to 3. Its one-case JVM run failed with `expected:<3> but was:<2>`. Restoring 2 returned the corpus to green. The wrong expectation is absent from the branch.

The Android host task runs on a JVM, not an Android device. These six hosts do not qualify the full target matrix. No production defect was established by the passing source and common runs. The native process exit from the unsafe null probe is a test-language boundary, not a demonstrated engine failure. This slice does not update the shared qualification manifest or close the tracking issue.
