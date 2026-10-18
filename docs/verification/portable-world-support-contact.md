# Portable world support and contact corpus

This report covers 75 pinned dyn4j 6.0.0 JUnit identities: 63 world support cases and 12 contact cases. One supplemental graph view regression test is counted separately. It is provisional evidence for [Run the full compatibility corpus and unchanged migration applications](https://github.com/rubixhacker/dyn4k/issues/42). Final issue acceptance and target qualification remain open.

## Provenance

- Active model: `gpt-6-sol`. Raw follow-up `turn_context`: `/home/stewart/.codex/sessions/2026/10/17/rollout-2026-10-17T15-00-05-01a14b73-3998-75e2-a831-3f0a28419e58.jsonl`, turn `01a14b87-18da-7bf3-8907-161af9b5df3e`. Initial corpus turn: `01a14b73-3a3c-7203-ad94-6dbd9c8ec342` in the same file.
- Graph mapping repair turns: `01a14c21-b4d9-75e2-b852-1e2def635419` and `01a14c2c-d4a0-7ab0-a4ca-5c0f1f2c4d92`, both verified as `gpt-6-sol` in the same raw session file.
- Pinned source revision: `058bf6d982a0fb89b54050f929f6ea9dae53b714`. Baseline binary SHA-256: `204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e`.
- Engine base: `6c533a5bbf3795514ce3a2ebb18d557bcc70045e`. Provisional JVM candidate JAR SHA-256: `128226a69d5d698df430546961db4332195d420c6c15d66f7bae1b84108e6755`. The JAR contains no corpus source changes.
- The 75 identities were checked against `/tmp/dyn4k-full-java-probe/baseline-jdk8.log`. Each has one named common method. There are no unmatched or duplicate source identities.

At combined corpus head `f09176dee50d20c01eee69db22ee7aef456e4288`, this report includes the approved hash-label repair from support head `b59cc40b0fa4e04626c2d8310e750566c3834e4b`. The current `ConstraintGraphCoverageTest.kt` bytes have SHA-256 `86c556f809276b7f92b70ad69547b940ef5b4be36440a2b855dbf30d715b906e`. The table below ties earlier six-host and focused results to their exact source revisions. No six-host result exists for the current combined source bytes.

## Current graph mapping repair

Pinned `ConstraintGraphTest.java` SHA-256 `ca2d1d427042c929f88a375a732b22c6c56ebb0b346722fe2cf198606c4778d0` was compared checkpoint by checkpoint for the entire `clear` and `removeBody` methods. Their shared fixture adds circle (radius 1.0), equilateral triangle (size 0.5), and circle (radius 0.5) bodies in `a, b, c` order; adds angle joints `a-b, a-c, b-c`; then adds contact constraints in the same pair order, each using the bodies' fixtures. The portable fixture now follows that order.

Before `removeBody`, the portable test saves each node's public contact and joint views and checks all six two-edge lists by ordered object identity: `a` has `ab, ac` and `jab, jac`; `b` has `ab, bc` and `jab, jbc`; `c` has `ac, bc` and `jac, jbc`. It checks all three contact and joint relation pairs and all six edge objects through the graph queries. After removing `a`, it checks the missing `a` node and body, re-gets `b` and `c`, and checks that each fresh and saved view contains exactly the original `bc` contact or `jbc` joint. It also checks all three relation pairs and all six edge objects at this checkpoint, including both removed contacts and both removed joints. `clear` checks the same twelve graph queries before and after mutation, plus all three missing nodes and empty size afterwards. Its additional pre-clear node-view identity checks cover the same insertion order.

A temporary adverse step reversed `b`'s contact edge list. Both focused mapped methods failed at the new ordered-identity assertion. A separate reversal of `b`'s joint edge list also failed both methods. The temporary mutations were removed; their raw XML and logs are recorded in `/tmp/dyn4k-world-support-entire-graph-fix-result.md`. These controls demonstrate sensitivity to the reviewer-reported order defect without changing the engine or final test source.

A temporary adverse test step added the `b-c` contact back after `clear()` and after the existing node checks. The focused `clear` test then failed at its new `isInContact(b, c)` assertion. The step was removed. Raw failed XML is `/tmp/dyn4k-world-support-clear-evidence/adverse-final/TEST-org.dyn4j.coverage.world.support.ConstraintGraphCoverageTest.xml`, SHA-256 `d56e7baeb78b5912f01cf20bf350c746ae2635c8a173bf03379877ad4f651cb5`.

The final `clear` and `removeBody` methods pass together on this branch's provisional engine: two tests, zero failures/errors/skips; raw XML `/tmp/dyn4k-world-support-entire-graph-evidence/branch-final/TEST-org.dyn4j.coverage.world.support.ConstraintGraphCoverageTest.xml`, SHA-256 `559c2ab92f39430e8f344d6a9ab5ef49e0f8f5e1669fde5b75a4d4df59932723`. A byte-identical copy of the final graph test file (SHA-256 `86c556f809276b7f92b70ad69547b940ef5b4be36440a2b855dbf30d715b906e`) was run in a disposable archive of integrated World `50e17aa6513a2c25944b1bc62d1a4cb8a3ee6b8f`. All 26 graph tests passed there, including the separate saved-view iterator test; raw XML `/tmp/dyn4k-world-support-entire-graph-evidence/integrated-final/TEST-org.dyn4j.coverage.world.support.ConstraintGraphCoverageTest.xml`, SHA-256 `2cb8502a497acf937e4f8371b528128bf3e60ac26bcc7f3c2d9ed63c8cb2a206`. The integrated JVM JAR SHA-256 is `35a696dd70d2cbc74daa8395f75e7338a89db302d7aeebbf8a0b62ab01be17f6`.

The same 75 pinned Java cases compiled unchanged with JDK 21 `--release 8` and passed with zero failures or ignored cases on baseline and integrated JARs under Java 8 and 21. Four raw logs are under `/tmp/dyn4k-world-support-clear-java/`, each SHA-256 `b2f1579bb67a6d3488a01298c11581dc7628f56132dfc388d5e84e1a7bd32400`. The full corrected common corpus still needs a six-host run at a coherent combined head.

## Previous provisional six-host result

The following six-host run used the earlier graph test source at `5eee7845832c848007619e7a021ab7297fa22eb1` and provisional engine base `6c533a5bbf3795514ce3a2ebb18d557bcc70045e`. Its 75 original common tests passed on each available host with zero errors or skips. The supplemental graph view iterator test failed on all six hosts. These XML results do not include the current graph mapping assertions or integrated World source.

| Common host task | Original pass | Supplemental fail | Errors | Skipped | SHA-256 of eight sorted raw XML files |
| --- | ---: | ---: | ---: | ---: | --- |
| `jvmTest` | 75 | 1 | 0 | 0 | `525a22b10173ab06d68317883a439bf7f83f1c8498f9638c7088bb0f3885f317` |
| `linuxX64Test` | 75 | 1 | 0 | 0 | `5c33ddc8331a4de888d1cfa602c4b1b043e2e450f55bd21724a9710fd49ba04c` |
| `jsNodeTest` | 75 | 1 | 0 | 0 | `b0a0a33768ba591a45d45b6c5654bfabafe45df5e45e175d827aafd318878fc0` |
| `wasmJsNodeTest` | 75 | 1 | 0 | 0 | `63aa2a88c71fcd1d7b0546f0460a77560f4f01e2b85cfb2493ed5443ffbef02d` |
| `wasmWasiNodeTest` | 75 | 1 | 0 | 0 | `1d29cc226d61b9b860c84990fe48032a4d3b3c132a54fb4be8df6118cc3ef4b8` |
| `testAndroidHostTest` | 75 | 1 | 0 | 0 | `ade7db5ade3c0eaa792d88f24d8b56619017be489c366e5af62ed4282b839e89` |

The XML files are copied without modification under `/tmp/dyn4k-world-support-corpus-fix-evidence/six-host/<task>/`. Per-file hashes and counts are in `/tmp/dyn4k-world-support-corpus-fix-evidence/six-host-summary.json` (SHA-256 `8202b5a748c38af1ae97c59d35ac2d93004b85681342c16358b68b82bdbf528c`). The aggregate digest above is SHA-256 over the eight selected XML byte streams sorted by filename. The six-host Gradle log is `/tmp/dyn4k-world-support-six-host.log` (SHA-256 `bd6675c96182acd0beb9d486113407d740ed391e4cdc298bce1b04b6705d3646`).

| Java provider and runtime | Executed | Failed | Ignored | Raw log SHA-256 |
| --- | ---: | ---: | ---: | --- |
| baseline, Java 8 | 75 | 0 | 0 | `b2f1579bb67a6d3488a01298c11581dc7628f56132dfc388d5e84e1a7bd32400` |
| baseline, Java 21 | 75 | 0 | 0 | `b2f1579bb67a6d3488a01298c11581dc7628f56132dfc388d5e84e1a7bd32400` |
| candidate, Java 8 | 75 | 0 | 0 | `b2f1579bb67a6d3488a01298c11581dc7628f56132dfc388d5e84e1a7bd32400` |
| candidate, Java 21 | 75 | 0 | 0 | `b2f1579bb67a6d3488a01298c11581dc7628f56132dfc388d5e84e1a7bd32400` |

The four unchanged Java logs are `/tmp/dyn4k-world-support-corpus-fix-evidence/java/<provider>-jdk<runtime>.log`. Their byte-identical output records each `CASE|class|method|PASS` line and `ACTUAL_TESTS=75`, `FAILURES=0`, `IGNORED=0`. The compile logs are in the same directory.

## Source identities and common dispositions

Every original row below passed the previous baseline Java 8/21, provisional candidate Java 8/21, and six common hosts. The `Common method` column names the test that exercises the listed source behavior. The current `clear` and `removeBody` assertions have focused integrated JVM evidence above. The supplemental case is outside this 75-row map.

| Pinned Java identity | Common method | Disposition |
| --- | --- | --- |
| `org.dyn4j.dynamics.contact.ContactConstraintTest.create` | `org.dyn4j.coverage.dynamics.contact.ContactConstraintCoverageTest.create` | PASS on 10 runs |
| `org.dyn4j.dynamics.contact.ContactConstraintTest.getSetEnabled` | `org.dyn4j.coverage.dynamics.contact.ContactConstraintCoverageTest.getSetEnabled` | PASS on 10 runs |
| `org.dyn4j.dynamics.contact.ContactConstraintTest.getSetTangentSpeed` | `org.dyn4j.coverage.dynamics.contact.ContactConstraintCoverageTest.getSetTangentSpeed` | PASS on 10 runs |
| `org.dyn4j.dynamics.contact.ContactConstraintTest.shift` | `org.dyn4j.coverage.dynamics.contact.ContactConstraintCoverageTest.shift` | PASS on 10 runs |
| `org.dyn4j.dynamics.contact.ContactConstraintTest.tostring` | `org.dyn4j.coverage.dynamics.contact.ContactConstraintCoverageTest.tostring` | PASS on 10 runs |
| `org.dyn4j.dynamics.contact.ContactConstraintTest.update` | `org.dyn4j.coverage.dynamics.contact.ContactConstraintCoverageTest.update` | PASS on 10 runs |
| `org.dyn4j.dynamics.contact.ForceCollisionTimeOfImpactSolverTest.simpleScenario1` | `org.dyn4j.coverage.dynamics.contact.ForceCollisionTimeOfImpactSolverCoverageTest.simpleScenario1` | PASS on 10 runs |
| `org.dyn4j.dynamics.contact.ForceCollisionTimeOfImpactSolverTest.simpleScenario2` | `org.dyn4j.coverage.dynamics.contact.ForceCollisionTimeOfImpactSolverCoverageTest.simpleScenario2` | PASS on 10 runs |
| `org.dyn4j.dynamics.contact.SequentialImpulsesTest.illConditioned` | `org.dyn4j.coverage.dynamics.contact.SequentialImpulsesCoverageTest.illConditioned` | PASS on 10 runs |
| `org.dyn4j.dynamics.contact.SequentialImpulsesTest.restitutionVelocity` | `org.dyn4j.coverage.dynamics.contact.SequentialImpulsesCoverageTest.restitutionVelocity` | PASS on 10 runs |
| `org.dyn4j.dynamics.contact.SolvableContactTest.create` | `org.dyn4j.coverage.dynamics.contact.SolvableContactCoverageTest.create` | PASS on 10 runs |
| `org.dyn4j.dynamics.contact.SolvableContactTest.isSolved` | `org.dyn4j.coverage.dynamics.contact.SolvableContactCoverageTest.isSolved` | PASS on 10 runs |
| `org.dyn4j.world.BroadphaseFilterAdapterTest.alwaysAllowed` | `org.dyn4j.coverage.world.support.WorldFilterAndResultCoverageTest.broadphaseFilterAdapterAlwaysAllowed` | PASS on 10 runs |
| `org.dyn4j.world.CollisionBodyBroadphaseFilterTest.enabled` | `org.dyn4j.coverage.world.support.WorldFilterAndResultCoverageTest.collisionBodyBroadphaseFilterEnabled` | PASS on 10 runs |
| `org.dyn4j.world.CollisionBodyBroadphaseFilterTest.filters` | `org.dyn4j.coverage.world.support.WorldFilterAndResultCoverageTest.collisionBodyBroadphaseFilterFilters` | PASS on 10 runs |
| `org.dyn4j.world.CollisionItemAdapterTest.copy` | `org.dyn4j.world.WorldAdapterAndIslandCoverageTest.collisionItemAdapterCopy` | PASS on 10 runs |
| `org.dyn4j.world.CollisionItemAdapterTest.create` | `org.dyn4j.world.WorldAdapterAndIslandCoverageTest.collisionItemAdapterCreate` | PASS on 10 runs |
| `org.dyn4j.world.CollisionItemAdapterTest.equalsAndHashcode` | `org.dyn4j.world.WorldAdapterAndIslandCoverageTest.collisionItemAdapterEqualsAndHashcode` | PASS on 10 runs |
| `org.dyn4j.world.CollisionItemAdapterTest.getAndSet` | `org.dyn4j.world.WorldAdapterAndIslandCoverageTest.collisionItemAdapterGetAndSet` | PASS on 10 runs |
| `org.dyn4j.world.CollisionItemAdapterTest.set` | `org.dyn4j.world.WorldAdapterAndIslandCoverageTest.collisionItemAdapterSet` | PASS on 10 runs |
| `org.dyn4j.world.ConstraintGraphTest.addBody` | `org.dyn4j.coverage.world.support.ConstraintGraphCoverageTest.addBody` | PASS on 10 runs |
| `org.dyn4j.world.ConstraintGraphTest.addContactConstraint` | `org.dyn4j.coverage.world.support.ConstraintGraphCoverageTest.addContactConstraint` | PASS on 10 runs |
| `org.dyn4j.world.ConstraintGraphTest.addContactConstraintBodiesNotAdded` | `org.dyn4j.coverage.world.support.ConstraintGraphCoverageTest.addContactConstraintBodiesNotAdded` | PASS on 10 runs |
| `org.dyn4j.world.ConstraintGraphTest.addJoint` | `org.dyn4j.coverage.world.support.ConstraintGraphCoverageTest.addJoint` | PASS on 10 runs |
| `org.dyn4j.world.ConstraintGraphTest.addJointBodiesNotAdded` | `org.dyn4j.coverage.world.support.ConstraintGraphCoverageTest.addJointBodiesNotAdded` | PASS on 10 runs |
| `org.dyn4j.world.ConstraintGraphTest.clear` | `org.dyn4j.coverage.world.support.ConstraintGraphCoverageTest.clear` | PASS on 10 runs |
| `org.dyn4j.world.ConstraintGraphTest.create` | `org.dyn4j.coverage.world.support.ConstraintGraphCoverageTest.create` | PASS on 10 runs |
| `org.dyn4j.world.ConstraintGraphTest.getContacts` | `org.dyn4j.coverage.world.support.ConstraintGraphCoverageTest.getContacts` | PASS on 10 runs |
| `org.dyn4j.world.ConstraintGraphTest.getInContactBodies` | `org.dyn4j.coverage.world.support.ConstraintGraphCoverageTest.getInContactBodies` | PASS on 10 runs |
| `org.dyn4j.world.ConstraintGraphTest.getInContactBodiesMulti` | `org.dyn4j.coverage.world.support.ConstraintGraphCoverageTest.getInContactBodiesMulti` | PASS on 10 runs |
| `org.dyn4j.world.ConstraintGraphTest.getJoinedBodies` | `org.dyn4j.coverage.world.support.ConstraintGraphCoverageTest.getJoinedBodies` | PASS on 10 runs |
| `org.dyn4j.world.ConstraintGraphTest.getJoinedBodiesMulti` | `org.dyn4j.coverage.world.support.ConstraintGraphCoverageTest.getJoinedBodiesMulti` | PASS on 10 runs |
| `org.dyn4j.world.ConstraintGraphTest.getJointsForBody` | `org.dyn4j.coverage.world.support.ConstraintGraphCoverageTest.getJointsForBody` | PASS on 10 runs |
| `org.dyn4j.world.ConstraintGraphTest.isInContact` | `org.dyn4j.coverage.world.support.ConstraintGraphCoverageTest.isInContact` | PASS on 10 runs |
| `org.dyn4j.world.ConstraintGraphTest.isJoined` | `org.dyn4j.coverage.world.support.ConstraintGraphCoverageTest.isJoined` | PASS on 10 runs |
| `org.dyn4j.world.ConstraintGraphTest.isJointCollisionAllowed` | `org.dyn4j.coverage.world.support.ConstraintGraphCoverageTest.isJointCollisionAllowed` | PASS on 10 runs |
| `org.dyn4j.world.ConstraintGraphTest.multiCollision` | `org.dyn4j.coverage.world.support.ConstraintGraphCoverageTest.multiCollision` | PASS on 10 runs |
| `org.dyn4j.world.ConstraintGraphTest.removeAllContactConstraints` | `org.dyn4j.coverage.world.support.ConstraintGraphCoverageTest.removeAllContactConstraints` | PASS on 10 runs |
| `org.dyn4j.world.ConstraintGraphTest.removeAllJoints` | `org.dyn4j.coverage.world.support.ConstraintGraphCoverageTest.removeAllJoints` | PASS on 10 runs |
| `org.dyn4j.world.ConstraintGraphTest.removeBody` | `org.dyn4j.coverage.world.support.ConstraintGraphCoverageTest.removeBody` | PASS on 10 runs |
| `org.dyn4j.world.ConstraintGraphTest.removeBodyWithQuadrupleJoint` | `org.dyn4j.coverage.world.support.ConstraintGraphCoverageTest.removeBodyWithQuadrupleJoint` | PASS on 10 runs |
| `org.dyn4j.world.ConstraintGraphTest.removeContactConstraint` | `org.dyn4j.coverage.world.support.ConstraintGraphCoverageTest.removeContactConstraint` | PASS on 10 runs |
| `org.dyn4j.world.ConstraintGraphTest.removeJoint` | `org.dyn4j.coverage.world.support.ConstraintGraphCoverageTest.removeJoint` | PASS on 10 runs |
| `org.dyn4j.world.ConstraintGraphTest.size` | `org.dyn4j.coverage.world.support.ConstraintGraphCoverageTest.size` | PASS on 10 runs |
| `org.dyn4j.world.ConstraintGraphTest.testRemoveBodyWithUnaryJoint` | `org.dyn4j.coverage.world.support.ConstraintGraphCoverageTest.testRemoveBodyWithUnaryJoint` | PASS on 10 runs |
| `org.dyn4j.world.DetectFilterTest.create` | `org.dyn4j.coverage.world.support.WorldFilterAndResultCoverageTest.detectFilterCreate` | PASS on 10 runs |
| `org.dyn4j.world.DetectFilterTest.disabled` | `org.dyn4j.coverage.world.support.WorldFilterAndResultCoverageTest.detectFilterDisabled` | PASS on 10 runs |
| `org.dyn4j.world.DetectFilterTest.filter` | `org.dyn4j.coverage.world.support.WorldFilterAndResultCoverageTest.detectFilterFilter` | PASS on 10 runs |
| `org.dyn4j.world.DetectFilterTest.sensor` | `org.dyn4j.coverage.world.support.WorldFilterAndResultCoverageTest.detectFilterSensor` | PASS on 10 runs |
| `org.dyn4j.world.IslandTest.add` | `org.dyn4j.world.WorldAdapterAndIslandCoverageTest.islandAdd` | PASS on 10 runs |
| `org.dyn4j.world.IslandTest.clear` | `org.dyn4j.world.WorldAdapterAndIslandCoverageTest.islandClear` | PASS on 10 runs |
| `org.dyn4j.world.IslandTest.createInvalidInitialCapacity` | `org.dyn4j.world.WorldAdapterAndIslandCoverageTest.islandCreateInvalidInitialCapacity` | PASS on 10 runs |
| `org.dyn4j.world.IslandTest.createSuccess` | `org.dyn4j.world.WorldAdapterAndIslandCoverageTest.islandCreateSuccess` | PASS on 10 runs |
| `org.dyn4j.world.listener.ListenerAdaptersTest.boundsListenerAdapter` | `org.dyn4j.coverage.world.support.WorldListenerAdapterCoverageTest.listenerAdaptersBoundsListenerAdapter` | PASS on 10 runs |
| `org.dyn4j.world.listener.ListenerAdaptersTest.collisionListenerAdapter` | `org.dyn4j.coverage.world.support.WorldListenerAdapterCoverageTest.listenerAdaptersCollisionListenerAdapter` | PASS on 10 runs |
| `org.dyn4j.world.listener.ListenerAdaptersTest.contactListenerAdapter` | `org.dyn4j.coverage.world.support.WorldListenerAdapterCoverageTest.listenerAdaptersContactListenerAdapter` | PASS on 10 runs |
| `org.dyn4j.world.listener.ListenerAdaptersTest.destructionListenerAdapter` | `org.dyn4j.coverage.world.support.WorldListenerAdapterCoverageTest.listenerAdaptersDestructionListenerAdapter` | PASS on 10 runs |
| `org.dyn4j.world.listener.ListenerAdaptersTest.stepListenerAdapter` | `org.dyn4j.coverage.world.support.WorldListenerAdapterCoverageTest.listenerAdaptersStepListenerAdapter` | PASS on 10 runs |
| `org.dyn4j.world.listener.ListenerAdaptersTest.timeOfImpactListenerAdapter` | `org.dyn4j.coverage.world.support.WorldListenerAdapterCoverageTest.listenerAdaptersTimeOfImpactListenerAdapter` | PASS on 10 runs |
| `org.dyn4j.world.PhysicsBodyBroadphaseFilterTest.dynamicSensor` | `org.dyn4j.coverage.world.support.WorldFilterAndResultCoverageTest.physicsBodyBroadphaseFilterDynamicSensor` | PASS on 10 runs |
| `org.dyn4j.world.PhysicsBodyBroadphaseFilterTest.enabled` | `org.dyn4j.coverage.world.support.WorldFilterAndResultCoverageTest.physicsBodyBroadphaseFilterEnabled` | PASS on 10 runs |
| `org.dyn4j.world.PhysicsBodyBroadphaseFilterTest.filters` | `org.dyn4j.coverage.world.support.WorldFilterAndResultCoverageTest.physicsBodyBroadphaseFilterFilters` | PASS on 10 runs |
| `org.dyn4j.world.PhysicsBodyBroadphaseFilterTest.jointCollisionAllowed` | `org.dyn4j.coverage.world.support.WorldFilterAndResultCoverageTest.physicsBodyBroadphaseFilterJointCollisionAllowed` | PASS on 10 runs |
| `org.dyn4j.world.PhysicsBodySweptAABBProducerTest.noSweep` | `org.dyn4j.world.WorldAdapterAndIslandCoverageTest.physicsBodySweptAABBProducerNoSweep` | PASS on 10 runs |
| `org.dyn4j.world.PhysicsBodySweptAABBProducerTest.sweepIntoExistingAABB` | `org.dyn4j.world.WorldAdapterAndIslandCoverageTest.physicsBodySweptAABBProducerSweepIntoExistingAABB` | PASS on 10 runs |
| `org.dyn4j.world.PhysicsBodySweptAABBProducerTest.sweepIntoNewAABB` | `org.dyn4j.world.WorldAdapterAndIslandCoverageTest.physicsBodySweptAABBProducerSweepIntoNewAABB` | PASS on 10 runs |
| `org.dyn4j.world.PhysicsBodySweptAABBProducerTest.zero` | `org.dyn4j.world.WorldAdapterAndIslandCoverageTest.physicsBodySweptAABBProducerZero` | PASS on 10 runs |
| `org.dyn4j.world.result.DetectResultTest.compareTo` | `org.dyn4j.coverage.world.support.WorldFilterAndResultCoverageTest.detectResultCompareTo` | PASS on 10 runs |
| `org.dyn4j.world.result.DetectResultTest.copy` | `org.dyn4j.coverage.world.support.WorldFilterAndResultCoverageTest.detectResultCopy` | PASS on 10 runs |
| `org.dyn4j.world.result.DetectResultTest.createSuccess` | `org.dyn4j.coverage.world.support.WorldFilterAndResultCoverageTest.detectResultCreateSuccess` | PASS on 10 runs |
| `org.dyn4j.world.result.DetectResultTest.set` | `org.dyn4j.coverage.world.support.WorldFilterAndResultCoverageTest.detectResultSet` | PASS on 10 runs |
| `org.dyn4j.world.ValueMixerTest.mixFriction` | `org.dyn4j.coverage.world.support.WorldFilterAndResultCoverageTest.valueMixerMixFriction` | PASS on 10 runs |
| `org.dyn4j.world.ValueMixerTest.mixRestitution` | `org.dyn4j.coverage.world.support.WorldFilterAndResultCoverageTest.valueMixerMixRestitution` | PASS on 10 runs |
| `org.dyn4j.world.ValueMixerTest.mixRestitutionVelocity` | `org.dyn4j.coverage.world.support.WorldFilterAndResultCoverageTest.valueMixerMixRestitutionVelocity` | PASS on 10 runs |
| `org.dyn4j.world.WorldTest.createCollisionData` | `org.dyn4j.coverage.world.support.WorldFilterAndResultCoverageTest.worldCreateCollisionData` | PASS on 10 runs |

## Pinned source hashes

| Upstream Java file | Cases | SHA-256 |
| --- | ---: | --- |
| [org/dyn4j/world/BroadphaseFilterAdapterTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/world/BroadphaseFilterAdapterTest.java) | 1 | `44eb5b37f1bad88ad6db4f379f9cebe8060b0976e841894edb276ceae054fd19` |
| [org/dyn4j/world/CollisionBodyBroadphaseFilterTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/world/CollisionBodyBroadphaseFilterTest.java) | 2 | `2c42d3b3922a3f596747056f494bf75f0101e4e27a0dc3befb101344bd701a71` |
| [org/dyn4j/world/CollisionItemAdapterTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/world/CollisionItemAdapterTest.java) | 5 | `58a808fa2ebf7706e81fa9d781c7b27f817c795833a57e366fd45a550da037c5` |
| [org/dyn4j/world/ConstraintGraphTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/world/ConstraintGraphTest.java) | 25 | `ca2d1d427042c929f88a375a732b22c6c56ebb0b346722fe2cf198606c4778d0` |
| [org/dyn4j/world/DetectFilterTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/world/DetectFilterTest.java) | 4 | `777bd868eca820bb2289c9cd81bc656e1b3cd3100b75b1c41a384316827d26ec` |
| [org/dyn4j/world/IslandTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/world/IslandTest.java) | 4 | `9c46acc0f93aea65e669d2eef72db01472c8a9496fb0e2e129a03e82dd6116ff` |
| [org/dyn4j/world/PhysicsBodyBroadphaseFilterTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/world/PhysicsBodyBroadphaseFilterTest.java) | 4 | `a08986d55d54531ddaaf7edc70ba643c9a59c8e3e7605e6474119a9ccd7053dc` |
| [org/dyn4j/world/PhysicsBodySweptAABBProducerTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/world/PhysicsBodySweptAABBProducerTest.java) | 4 | `d0bcd163abb8944c1b73ee81986a90dd2b9ab529ad6f88c6b4db9ede62c19fda` |
| [org/dyn4j/world/ValueMixerTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/world/ValueMixerTest.java) | 3 | `e07cfcab3d0fc8a6287b7fa44253d1e74c8e6c214aac56dc40862c8b4704752d` |
| [org/dyn4j/world/WorldTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/world/WorldTest.java) | 1 | `815481f3aaf661797298064c284353667bcfe3b424db424e8405be22b52e371c` |
| [org/dyn4j/world/listener/ListenerAdaptersTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/world/listener/ListenerAdaptersTest.java) | 6 | `a663a88badd2d150c9fe177d61906c0bf046c292615988e677f69f3eed96b984` |
| [org/dyn4j/world/result/DetectResultTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/world/result/DetectResultTest.java) | 4 | `dfa868c76a11e62c5317dd3b423a4d72a26beff30e02b54266b2e3a980f5af36` |
| [org/dyn4j/dynamics/contact/ContactConstraintTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/dynamics/contact/ContactConstraintTest.java) | 6 | `348f9b77aead11c7866cbc590b679f9e8cd1ada7a228ad432b1b2c6582577c0b` |
| [org/dyn4j/dynamics/contact/ForceCollisionTimeOfImpactSolverTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/dynamics/contact/ForceCollisionTimeOfImpactSolverTest.java) | 2 | `39957975bd67f6b418e4d61415513acc490a3b4eb2dcf5bf6a99e3020a061e88` |
| [org/dyn4j/dynamics/contact/SequentialImpulsesTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/dynamics/contact/SequentialImpulsesTest.java) | 2 | `73c3e473e1809ce381ded89a37890547ee4846139ae841189b534082b648f6e6` |
| [org/dyn4j/dynamics/contact/SolvableContactTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/dynamics/contact/SolvableContactTest.java) | 2 | `ffcb260b667a2eb6dc4092695f6017821d4632e3b788c3789742709ebbe47b4a` |

## Common test hashes and evidence

The graph test has three distinct revisions. Only the `5eee784` graph source belongs to the [earlier six-host run](#previous-provisional-six-host-result). The intermediate and current graph revisions have focused JVM evidence. The other four files have identical hashes at `5eee784` and the current branch head.

| Common test file | Revision | SHA-256 | Applicable evidence |
| --- | --- | --- | --- |
| `dyn4k-core/src/commonTest/kotlin/org/dyn4j/coverage/world/support/ConstraintGraphCoverageTest.kt` | Historical six-host source, `5eee7845832c848007619e7a021ab7297fa22eb1` | `151f76f8e47590bca66b7f77fd7493017d790b5a7463723cc9905fed646b4eb5` | [Earlier six-host XML](#previous-provisional-six-host-result); supplemental iterator red |
| `dyn4k-core/src/commonTest/kotlin/org/dyn4j/coverage/world/support/ConstraintGraphCoverageTest.kt` | Intermediate graph repair, `31647c6719115ea65bbdf29a68c61e86aca30196` | `8ef3cd55d5161ed4715cd2f3bac5752ec83374f31c2b87a60612ce80185ad922` | Focused JVM XML in `/tmp/dyn4k-world-support-clear-pairs-fix-result.md`; no six-host run |
| `dyn4k-core/src/commonTest/kotlin/org/dyn4j/coverage/world/support/ConstraintGraphCoverageTest.kt` | Current final graph test, `5f9f24d9fdcf46e976fda48e5366c277db1df75c` | `86c556f809276b7f92b70ad69547b940ef5b4be36440a2b855dbf30d715b906e` | [Final focused and integrated JVM XML](#current-graph-mapping-repair); no six-host run |
| `dyn4k-core/src/commonTest/kotlin/org/dyn4j/coverage/world/support/WorldAdapterAndIslandCoverageTest.kt` | Historical six-host and current | `6f15024d653902a8fb21d81f1e45ea3ed8231bb84f279d6b7ef96aae255e59e1` | [Earlier six-host XML](#previous-provisional-six-host-result) |
| `dyn4k-core/src/commonTest/kotlin/org/dyn4j/coverage/world/support/WorldFilterAndResultCoverageTest.kt` | Historical six-host and current | `c4c495d6ce9481f67bc18f525125ed634d458cf87c1b9a6b07b031e14afb4c4b` | [Earlier six-host XML](#previous-provisional-six-host-result) |
| `dyn4k-core/src/commonTest/kotlin/org/dyn4j/coverage/world/support/WorldListenerAdapterCoverageTest.kt` | Historical six-host and current | `624b028e14ed460256331cd0f1bc2008de70e0b65f00e8f56dcacaf0ee74b34d` | [Earlier six-host XML](#previous-provisional-six-host-result) |
| `dyn4k-core/src/commonTest/kotlin/org/dyn4j/coverage/dynamics/contact/ContactCoverageTest.kt` | Historical six-host and current | `d056df67ce9518c647ddfe1d68a564d34c9c55bb3d3fc05a2c8abd6a82aa1e48` | [Earlier six-host XML](#previous-provisional-six-host-result) |

## Behavior and sensitivity

The tests retain the source's adapter null paths, category and sensor filters, collision item identity, graph edges and live views, island integration count, swept AABB bounds, world result identity and copy semantics, value mixing, and contact callback transitions. Contact tests also check warm-start impulses, solver thresholds, ill-conditioned point choice, and exact TOI movement. `ContactConstraint` is final in the pinned source; the common tests use its public interface and module-visible solver state without a subclass.

The `update` common test now calls a state assertion helper after all three updates. Each checkpoint checks enabled state, friction, restitution, restitution velocity, null solver matrices, pair and body/fixture identity, normal, tangent, tangent speed, sensor state, contact and solver-contact counts, reciprocal body/fixture lookup, and foreign-body null results. The existing event-order, live-view, perturbation, and warm-start assertions remain. A controlled handler returned friction `0.9` only on the second update; the restored check failed at `expected:<0.2> but was:<0.9>`. The failed XML is `/tmp/dyn4k-world-support-corpus-fix-evidence/contact-control/TEST-org.dyn4j.coverage.dynamics.contact.ContactConstraintCoverageTest.xml` (SHA-256 `5e03423bcf7fcfb0171cb650d1e9e660376c29f8df8530bfaaccb53be63b6687`); the handler was restored before the six-host run.

The supplemental `ConstraintGraphCoverageTest.savedNodeViewIteratorsFailFastAfterStructuralMutation` obtains both node view iterators before adding a second contact and joint edge. It requires `ConcurrentModificationException` from both saved iterators. A Java 8 probe against the pinned baseline records that exception for each view; the provisional candidate returns an element from each. Probe outputs are `/tmp/dyn4k-world-support-corpus-fix-evidence/graph-baseline-jdk8.log` (SHA-256 `30e97e08c0b0403309358d35d4b3ed2d223883466f6e69ffa5db9bca72e71710`) and `graph-candidate-jdk8.log` (SHA-256 `eaf1e868d166f7d5befec1fda90ae8fb2e46424c4729be22c816567187bdc984`). The pinned tree contains `ConstraintGraphTest.java` and `ConstraintGraphNode.java`, but no `ConstraintGraphNodeTest.java`; the supplemental expectation follows the pinned node's unmodifiable `ArrayList` views and the executed baseline probe. The integrated World `50e17aa` passes this case in the focused JVM run above.

A controlled wrong mixer returned the first restitution input (`0.5`) where the pinned maximum rule requires `0.7`. `valueMixerMixRestitution` failed once with `expected:<0.7> but was:<0.5>`. Raw failed XML is `/tmp/dyn4k-coverage-world-support-java/mutation-TEST.xml` (SHA-256 `adae225b11f01b3d5564d2f9e1eee96e23a555a4d43b32972a596ee741ce458f`). The diagnostic test argument was restored before the final six-host run.

The first Android host attempt failed five adapter cases with `IllegalAccessError` because the test class was outside `org.dyn4j.world`. Moving its Kotlin package into the Java visibility package resolved all five on the final Android host run. No production source changed.

## Commands and remaining gates

```sh
bash /tmp/dyn4k-coverage-world-support-java/run.sh
ANDROID_HOME=/home/stewart/Android/Sdk ./gradlew --no-daemon --continue --rerun-tasks --console=plain \
  :dyn4k-core:jvmTest :dyn4k-core:linuxX64Test :dyn4k-core:jsNodeTest \
  :dyn4k-core:wasmJsNodeTest :dyn4k-core:wasmWasiNodeTest :dyn4k-core:testAndroidHostTest
```

No defect appeared in these 75 source identities on the earlier provisional candidate, but the supplemental iterator case was red on every available common host. The focused integrated World run now passes all graph methods, including the supplemental case. A coherent combined-head six-host corpus run remains an integration dependency. An earlier frozen full-corpus probe at a different candidate JAR recorded 18 shape-pair failures; this report neither waives those failures nor claims their current status. The full 21-target matrix, both build configurations, native devices, staged consumers, physical and numerical acceptance, integrated corpus, and final issue acceptance remain open.
