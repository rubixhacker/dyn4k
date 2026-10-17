# Portable body coverage on the integrated candidate

## Reader and scope

This report maps the seven root dynamics test files from pinned dyn4j 6.0.0 source revision `058bf6d982a0fb89b54050f929f6ea9dae53b714` to common Kotlin tests. The corpus began at body source `cb4492f20fc980445b7f5377234cadefc5426428` and now runs on a local merge of integration head `80ffe42ba427d6b34dcda6059774fd420b22441d`. This report covers the body test subtree only; it does not qualify the complete compatibility corpus or any full runtime lane.

The pinned files contain 124 `@Test` annotations. JUnit 4 executes 124 cases for these files against the baseline and 124 against the integrated candidate. None of the seven files uses a parameterized runner or inherits test methods. Both unchanged Java runs completed with zero failures and zero ignored cases. The raw XML archive is `/tmp/dyn4k-portable-body-expanded-xml.tar.gz`.

The common tests exercise `org.dyn4j` objects through public methods and a Kotlin `Body` subclass for protected copy state. A common test can cover several source methods when those methods check one behavior together. The table names every source method, including error cases. Names in the right column are methods under `dyn4k-core/src/commonTest/kotlin/org/dyn4j/coverage/dynamics/body/`.

| Pinned source file and test identities | Common Kotlin counterpart |
| --- | --- |
| `AbstractPhysicsBodyTest`: `create`, `addFixtureByConvexBodyFixture`, `addFixtureWithDensityFrictionRestitution` | `PhysicsBodyCoverageTest.defaultsAndFixtureOverloads` |
| `AbstractPhysicsBodyTest`: `addNullConvex`, `addNullConvex2`, `addNullConvex3`, `addNullFixture` | `PhysicsBodyCoverageTest.fixtureNullOverloadsRejectBeforeMutation` |
| `AbstractPhysicsBodyTest`: `accumulate`, `apply`, `getAccumulatedForce`, `getAccumulatedTorque`, `getForce`, `getTorque` | `PhysicsBodyCoverageTest.appliedForcesAndTorquesAccumulateWithoutChangingInputs` |
| `AbstractPhysicsBodyTest`: `applyNullForce`, `applyNullForceVector`, `applyNullTorque`, `applyNullForceAtPoint`, `applyForceAtNullPoint`, `applyNullImpulse`, `applyNullImpulse2`, `applyNullImpulsePoint` | `PhysicsBodyCoverageTest.forceAndImpulseNullOverloadsReject` |
| `AbstractPhysicsBodyTest`: `applyImpulse` | `PhysicsBodyCoverageTest.impulsesUseMassAndInertia` |
| `AbstractPhysicsBodyTest`: `clear` | `PhysicsBodyCoverageTest.clearMethodsRemoveOnlyTheirOwnState` |
| `AbstractPhysicsBodyTest`: `getSetLinearDamping`, `getSetAngularDamping`, `setNegativeLinearDamping`, `setNegativeAngularDamping`, `getSetLinearVelocity`, `setNullLinearVelocity`, `getSetAngularVelocity`, `getSetGravityScale`, `getSetBullet` | `PhysicsBodyCoverageTest.velocityDampingGravityAndBulletAreObservable` |
| `AbstractPhysicsBodyTest`: `createSweptAABB`, `getChangeInPosition` | `PhysicsBodyCoverageTest.sweptBoundsAndPreviousTransformTrackTranslation` |
| `AbstractPhysicsBodyTest`: `getChangeInOrientation` | `PhysicsBodyCoverageTest.orientationChangePreservesDirectionAcrossWraparound` |
| `AbstractPhysicsBodyTest`: `setMass`, `setMassType`, `setNullMassType`, `setNullMass` | `PhysicsBodyCoverageTest.massIdentityAndTypeTransitions`, `fixtureMassCompositionIgnoresZeroDensity` |
| `AbstractPhysicsBodyTest`: `isDynamic`, `isKinematic`, `isStatic`, `getSetAtRest` | `PhysicsBodyCoverageTest.staticKinematicDynamicAndRestStateTransitions` |
| `AbstractPhysicsBodyTest`: `updateAtRestTime` | `PhysicsBodyCoverageTest.sleepThresholdsCallGettersInOrder`, `atRestTimeResetsAndDisabledDetectionKeepsBodyAwake` |
| `AbstractPhysicsBodyTest`: `integrateVelocity`, `integratePosition` | `PhysicsBodyCoverageTest.velocityAndPositionIntegrationUseStepAndLimits` |
| `AbstractPhysicsBodyTest`: `getLocalCenter`, `getLinearVelocityAtPoint`, `tostring` | `PhysicsBodyCoverageTest.localCenterAndPointVelocityUseLiveMassAndVelocity` |
| `BodyFixtureTest`: `createNullShape`, `createSuccess`, `getSetDensity`, `setNegativeDensity`, `setZeroDensity`, `getSetFriction`, `setNegativeFriction`, `getSetRestitution`, `setNegativeRestitution`, `tostring`, `createMass`, `getSetRestitutionVelocity` | `BodyValueCoverageTest.fixturePropertiesMassAndErrors` |
| `BodyTest`: `create` | `PhysicsBodyCoverageTest.defaultsAndFixtureOverloads` |
| `BodyTest`: `copy` | `PhysicsBodyCoverageTest.bodyCopyKeepsStateButReplacesMutableObjects`, `bodyCopyDuplicatesProtectedStateAndPendingCollections` |
| `ForceTest`: `createSuccess`, `setSuccess`, `tostring`, `isComplete`, `copy` | `BodyValueCoverageTest.forceConstructionSetCopyAndLiveVector` |
| `ForceTest`: `createNullForce`, `createNullVector`, `setNullForce`, `setNullVector` | `BodyValueCoverageTest.forceNullOverloadsRejectTheirArgument` |
| `SettingsTest`: `setValidFrequency`, `setNegativeFrequency`, `setZeroFrequency`, `setValidMaximumTranslation`, `setNegativeMaximumTranslation`, `setMaximumRotation`, `setNegativeMaximumRotation`, `setValidSleepLinearVelocity`, `setNegativeSleepLinearVelocity`, `setValidSleepAngularVelocity`, `setNegativeSleepAngularVelocity`, `setValidSleepTime`, `setNegativeSleepTime`, `setValidWarmStartDistance`, `setNegativeWarmStartDistance`, `setValidLinearTolerance`, `setNegativeLinearTolerance`, `setValidAngularTolerance`, `setNegativeAngularTolerance`, `setValidMaximumLinearCorrection`, `setNegativeMaximumLinearCorrection`, `setValidMaximumAngularCorrection`, `setNegativeMaximumAngularCorrection`, `setValidBaumgarte`, `setNegativeBaumgarte` | `BodyValueCoverageTest.settingsValidateScalarsAndKeepDerivedSquares` |
| `SettingsTest`: `setValidVelocityConstraintSolverIterations`, `setNegativeVelocityConstraintSolverIterations`, `setZeroVelocityConstraintSolverIterations`, `setValidPositionConstraintSolverIterations`, `setNegativePositionConstraintSolverIterations`, `setZeroPositionConstraintSolverIterations`, `setSleep`, `getSetWarmStartingEnabled`, `getSetContinuousDetectionMode`, `setNullContinuousDetectionMode`, `tostring` | `BodyValueCoverageTest.settingsValidateIterationsAndFlags` |
| `SettingsTest`: `getSet` | `BodyValueCoverageTest.settingsValidateScalarsAndKeepDerivedSquares`, `settingsValidateIterationsAndFlags` |
| `SettingsTest`: `copy` | `BodyValueCoverageTest.settingsCopySetAndResetPreserveValues` |
| `TimeStepTest`: `createSuccess`, `createZeroDeltaTime`, `createNegativeDeltaTime`, `update`, `updateZeroDeltaTime`, `updateNegativeDeltaTime`, `tostring` | `BodyValueCoverageTest.timestepTracksPreviousValuesAndRejectsInvalidUpdates` |
| `TorqueTest`: `createSuccess`, `setSuccess`, `tostring`, `isComplete`, `copy` | `BodyValueCoverageTest.torqueConstructionSetCopyAndCompletion` |
| `TorqueTest`: `createNullTorque`, `setNullTorque` | `BodyValueCoverageTest.torqueNullOverloadsRejectTheirArgument` |

The seven source files have **124 mapped identities** and **zero whole-method JVM-only waivers**. The unchanged Java run separately checks Java source compilation and protected field access. Common Kotlin alone cannot establish those language contracts. The public `Body.copy()` test checks copied damping and rest detection. It mutates force, torque, mass, and fixture state after copying to verify independence. Fixture mutation is a supplemental copy check; pinned `BodyTest.copy` does not assert it. A common Kotlin `Body` subclass exposes its protected state to a second copy test. The probe checks rest time, rest state, detection, stored force, torque, and mass values and identities. It also checks each pending item and collection identity. It then mutates the original stored state and pending items to verify that the copy stays independent. Pinned `SettingsTest.getSet` checks individual setter/getter pairs in the two validation methods. The settings `set(Settings)` path is supplemental; both it and the mapped `copy` path assert all 17 changed fields. The same assertion helper rejects a wrong angular tolerance. The portable tests use fixed expected values for velocities, masses, force and torque sums, bounds, orientation wraps, step ratios, and error types. `controlledWrongForceGetterFailsThePortableOracle` is a supplemental negative control: a deliberately wrong getter fails the same literal-value oracle used on a correct force. It is not counted as a pinned source identity.

## Evidence and qualification boundary

The unchanged seven Java files compiled with `javac --release 8` against each provider. Both JUnit runs executed 124 tests with zero failures, errors, or skips. A direct class/method comparison found 124 distinct XML identities on each provider. The table maps those same 124 identities once each; its counterpart methods group several Java cases where they test one behavior. No whole Java method needs a JVM-only waiver.

| Provider | JAR SHA-256 | Raw Java XML SHA-256 |
| --- | --- | --- |
| Pinned baseline | `204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e` | `09da63e756d8d282ee537438da5777a3e79a0a55a4dbc082e528f2328c1e2cef` |
| Integrated candidate | `57dff9184c7fc17a80611482ee4c8bf2e308719f351b34e50cbed99c1795057c` | `65ee7b47ebb6487c832c3f518a8d87700169c283456f8cbb03ef45baf6a9e16e` |

Each of the six available `dyn4k-core` host tasks ran 14 XML suites and 466 tests, with zero failures, errors, or skips. Each host executed 29 body subtree tests: 10 value tests and 19 physics tests. These are 29 common Kotlin tests, not 124 separate portable methods.

| Host task | Body value XML SHA-256 (10) | Body physics XML SHA-256 (19) |
| --- | --- | --- |
| `jvmTest` | `1d2ef8eec202d3aa9459c28ad37123a5280c91cea900337ff508508ed1519629` | `674a7eb409ca27ca91e46b58b8d4d09ed0bad33cf29a13c7f910136515dd01a7` |
| `jsNodeTest` | `d29272ef251765b4c7229f54913d9d82282a0d2394fec5f614722c9d9ca1f80a` | `6ec6aa1b9a536c26640b90b332429bc81e091e9559bb9b876096ae8c3b7dfdec` |
| `wasmJsNodeTest` | `de8237175dbdb70638fd729c860d022f454fef6f3ce91546cf9b49fd07975cdc` | `d3b6afa6f4584382b1ca6979e57ad08dc884048e38502d1186f98cd99405139e` |
| `wasmWasiNodeTest` | `e22b8bbb4370058109c8908c8a6df7e949c951a43e954fc98b550bc0e0f296b6` | `d126555bc74a063b1eec856086dbd1e60359a12d156357fec3cdaf2014f8f0d3` |
| `linuxX64Test` | `596a81d59171da287f474c4bf395da39f8b3dcc654a8a36cf1559ab48cbcf410` | `057dedb0a304322e5298908223b8228784eb35d6f67a8997497ac61ddc3a0055` |
| `testAndroidHostTest` | `a2384d0ff8710508dda8cb067ebeb178cac4a3b8b677d0c63ef1635e5f577a82` | `6b61a152db88b93d23431edc87078f0d6a8f57e905d305a283a5f26f582c3c35` |

The raw archive `/tmp/dyn4k-portable-body-expanded-xml.tar.gz` has SHA-256 `35186fc4a0aa30098bf0889a1893bbf8f2bceae57fbf219f474297e9aca1a15c`. It contains both Java XML files and all 84 host XML files. The result report at `/tmp/dyn4k-portable-body-expanded-fix-result.md` records every suite hash and its path.

The focused body class ran green after repair. Seven temporary wrong-value controls then made seven mapped tests fail: fixture count, force at center, zero-mass point impulse, explicit swept y bound, updated mass, static integration, and local-center y. After restoring those expectations, the focused class passed again. A candidate JAR mutant that omits copy-constructor damping and rest-time writes failed both copy tests (19 run, two failures). The pinned `SettingsTest.getSet` observation remains covered by individual setter/getter tests; `Settings.set(Settings)` is supplemental.

Both modules were staged locally for the six available target publications. Artifact IDs and SHA-256 values are:

| Target publication | `dyn4k-core` binary | `dyn4k` binary |
| --- | --- | --- |
| JVM JAR | `57dff9184c7fc17a80611482ee4c8bf2e308719f351b34e50cbed99c1795057c` | `3ff180079fc36ff98e2217788099c4f4b67078b93c3df6dc330c216949d0f8a8` |
| JS KLIB | `8e02ba1c3df5dda2c7dae743a8f2e6b68be5778fd547c1f99a9ebb46f721e052` | `3fca1a4870129d03c3d95f8ea7f82d40fdabb944b009aa257772ae68d5c072b5` |
| Wasm JS KLIB | `6ce2769ff186ffc24642ef86d95d7abf1f8c6ab855fa99bda70d7fe27a5b1d46` | `759d8bbfe213b0f84a3558a6ca94f151ab45ac75e804bf0bdd69e3161900131e` |
| Wasm WASI KLIB | `41526e3333c9733eee278b08190686257322f53f08b550b5dd0854101e541c47` | `d59d259bcd5cbb2d0000094f34229cf4171d732dda3501f20f4829748daf3840` |
| Linux x64 KLIB | `d92b2fbab47af3562dc519473e1356023ded0b0defc3350e0ed4d1950262b0f7` | `554227caa913c133b043034ca51e881abfce4f759028cbf8dc7b4e89408ac946` |
| Android AAR | `9854f56378f53fb2439d36b8e3e155eb52c840bde1c991d09592182e2a879fb9` | `08efd78d6d1cbef44d335f1d96aa99cc6efd52124dc03d436df51ec801f8bb12` |

The unchanged baseline, candidate, staged Java, staged Kotlin, and Android host dynamics consumers all completed. Java consumers reported `DYNAMICS_CONSUMER_OK`; the Kotlin consumer reported `DYNAMICS_KOTLIN_CONSUMER_OK`. Both null probes reported `ArgumentNullException: convex cannot be null`.

The integration merge includes committed collision source at `80ffe42ba427d6b34dcda6059774fd420b22441d`. The local merge preserved dynamics and polygon build registrations. The combined frozen qualification manifest still needs exact-head review and hosted execution. Local host tests do not establish Android device, Apple, Windows, full runtime, physical, numerical, or release qualification.
