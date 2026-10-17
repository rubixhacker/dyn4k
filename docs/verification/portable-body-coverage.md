# Portable body coverage at the provisional body source

## Reader and scope

This report maps the seven root dynamics test files from pinned dyn4j 6.0.0 source revision `058bf6d982a0fb89b54050f929f6ea9dae53b714` to common Kotlin tests. The candidate started at `cb4492f20fc980445b7f5377234cadefc5426428` on `codex/port-coverage-body`. The candidate body and collision implementations are provisional. This report covers this body's test subtree only; it does not qualify the complete compatibility corpus or any full runtime lane.

The pinned files contain 124 `@Test` annotations. JUnit 4 executes 124 cases for these files against the baseline and 124 against the provisional candidate. None of the seven files uses a parameterized runner or inherits test methods. Both unchanged Java runs completed with zero failures and zero ignored cases. The raw XML is archived with the CLI result in `/tmp/dyn4k-portable-body-coverage-result.md`.

The common tests exercise public `org.dyn4j` objects. A common test can cover several source methods when those methods check one behavior together. The table names every source method, including error cases. Names in the right column are methods under `dyn4k-core/src/commonTest/kotlin/org/dyn4j/coverage/dynamics/body/`.

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
| `BodyTest`: `copy` | `PhysicsBodyCoverageTest.bodyCopyKeepsStateButReplacesMutableObjects` |
| `ForceTest`: `createSuccess`, `setSuccess`, `tostring`, `isComplete`, `copy` | `BodyValueCoverageTest.forceConstructionSetCopyAndLiveVector` |
| `ForceTest`: `createNullForce`, `createNullVector`, `setNullForce`, `setNullVector` | `BodyValueCoverageTest.forceNullOverloadsRejectTheirArgument` |
| `SettingsTest`: `setValidFrequency`, `setNegativeFrequency`, `setZeroFrequency`, `setValidMaximumTranslation`, `setNegativeMaximumTranslation`, `setMaximumRotation`, `setNegativeMaximumRotation`, `setValidSleepLinearVelocity`, `setNegativeSleepLinearVelocity`, `setValidSleepAngularVelocity`, `setNegativeSleepAngularVelocity`, `setValidSleepTime`, `setNegativeSleepTime`, `setValidWarmStartDistance`, `setNegativeWarmStartDistance`, `setValidLinearTolerance`, `setNegativeLinearTolerance`, `setValidAngularTolerance`, `setNegativeAngularTolerance`, `setValidMaximumLinearCorrection`, `setNegativeMaximumLinearCorrection`, `setValidMaximumAngularCorrection`, `setNegativeMaximumAngularCorrection`, `setValidBaumgarte`, `setNegativeBaumgarte` | `BodyValueCoverageTest.settingsValidateScalarsAndKeepDerivedSquares` |
| `SettingsTest`: `setValidVelocityConstraintSolverIterations`, `setNegativeVelocityConstraintSolverIterations`, `setZeroVelocityConstraintSolverIterations`, `setValidPositionConstraintSolverIterations`, `setNegativePositionConstraintSolverIterations`, `setZeroPositionConstraintSolverIterations`, `setSleep`, `getSetWarmStartingEnabled`, `getSetContinuousDetectionMode`, `setNullContinuousDetectionMode`, `tostring` | `BodyValueCoverageTest.settingsValidateIterationsAndFlags` |
| `SettingsTest`: `getSet`, `copy` | `BodyValueCoverageTest.settingsCopySetAndResetPreserveValues` |
| `TimeStepTest`: `createSuccess`, `createZeroDeltaTime`, `createNegativeDeltaTime`, `update`, `updateZeroDeltaTime`, `updateNegativeDeltaTime`, `tostring` | `BodyValueCoverageTest.timestepTracksPreviousValuesAndRejectsInvalidUpdates` |
| `TorqueTest`: `createSuccess`, `setSuccess`, `tostring`, `isComplete`, `copy` | `BodyValueCoverageTest.torqueConstructionSetCopyAndCompletion` |
| `TorqueTest`: `createNullTorque`, `setNullTorque` | `BodyValueCoverageTest.torqueNullOverloadsRejectTheirArgument` |

The seven source files have **124 mapped identities** and **zero whole-method JVM-only waivers**. The unchanged Java run separately checks Java source compilation and protected field access; those language-level contracts cannot be established by common Kotlin alone. The portable copy test checks the observable deep-copy result by mutating original force, torque, mass, and fixture state after copying. The portable tests use fixed expected values for velocities, masses, force and torque sums, bounds, orientation wraps, step ratios, and error types. `controlledWrongForceGetterFailsThePortableOracle` is a supplemental negative control: a deliberately wrong getter fails the same literal-value oracle used on a correct force. It is not counted as a pinned source identity.

## Evidence and qualification boundary

The unchanged Java sources compiled with `javac --release 8` against each provider. The pinned baseline JAR has SHA-256 `204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e`. The candidate JVM JAR has SHA-256 `85c95a51407b7249d502ab9cfdb8946b096de1961c246539f29740e9d304baea`. The baseline and candidate raw XML files each contain 124 tests, zero failures, and zero skipped cases. Their SHA-256 values are `b6f1bd5c18d288f5c0ba6e66b0f434b0931b2b484ea11b228c99135554174021` and `c5749ec02174acc75ab67cab007acf4e65a8999f50f4029b1828f2b3632a9d06` respectively.

The six available local `dyn4k-core` host tasks each executed 55 common tests, including 28 tests in the new body subtree, with zero failures, errors, or skips. The 28 include one supplemental controlled-bad-behavior case. These host tasks do not execute 124 separate portable cases; the mapping above relates source identities to behavioral counterparts.

| Host task | New body XML SHA-256: values / physics |
| --- | --- |
| `jvmTest` | `4c0107c5f1e8463641e0690f57a1a55af48cd8b4502e1ce200c3057e1a65bba0` / `a00664216734f712273cc547140e91fbbc9c2bbd38d08433078e9dd7af6af047` |
| `jsNodeTest` | `68a74d49e6573dcdae8c87ac3f51c792f3aefb496231ea07e533ed7db6101064` / `d99d4139127c9c7c7753fd3af1d238be37705adf129d6147f5fa883c516f8421` |
| `wasmJsNodeTest` | `daded120594013754c4e726cf9e916b2c4bedee86070e511938fbc6ca13c133b` / `2b23d3278aebd46402fb46c18f4b40b756f5190031b0cad9afe19788d88e2206` |
| `wasmWasiNodeTest` | `729db1c10dd60c61ee02b8fb01f292d24d8053953e129303eb2f6970853c436a` / `9861f6ca6d34e91b57d4c8dcc0886891631179b0c77aa3990cc6dbce2cca01e4` |
| `linuxX64Test` | `7dde11de3027beeddb3b51a680353a8e4253f60de48293c3c9b626440291a443` / `3da52b94e2b366fcc5b29d55362edf7bba934fd0bfa3f64f04c50173c84277c0` |
| `testAndroidHostTest` | `ab3c982f85f8fb55bf4774b7e19850f6fc49436f58884bc7f08b9ac8c5c05f77` / `5a202c340d88b94a3dacc88ca18950a5668471233a294e5f5ff48250d082a94f` |

The raw XML archive is `/tmp/dyn4k-portable-body-coverage-xml.tar.gz`, SHA-256 `89fb1245e31ae01b9ad948a28b3d74ab2fe01bbeae4f726dbb9334f517df4f81`. It contains the baseline and candidate Java XML and all six host test-result directories. The Java, staged Kotlin, and Android host dynamics consumers ran unchanged. They reported `DYNAMICS_CONSUMER_OK` or `DYNAMICS_KOTLIN_CONSUMER_OK`; both baseline and candidate null probes reported `ArgumentNullException: convex cannot be null`.

Both modules were staged locally for the six available target publications. Artifact IDs and SHA-256 values are:

| Target publication | `dyn4k-core` binary | `dyn4k` binary |
| --- | --- | --- |
| JVM JAR | `85c95a51407b7249d502ab9cfdb8946b096de1961c246539f29740e9d304baea` | `3ff180079fc36ff98e2217788099c4f4b67078b93c3df6dc330c216949d0f8a8` |
| JS KLIB | `acef7e24033cd3126ad170197a124c9f697207d256714c363dee378c4da1b1ca` | `3fca1a4870129d03c3d95f8ea7f82d40fdabb944b009aa257772ae68d5c072b5` |
| Wasm JS KLIB | `53b8bd0a3904b66f8d287bab389622da7b92db32a35578c4fbbfe6be38fdbbfe` | `759d8bbfe213b0f84a3558a6ca94f151ab45ac75e804bf0bdd69e3161900131e` |
| Wasm WASI KLIB | `cff60eef6d6cc90e6ac2dac345e45e33cb2c6a30be6379186242f69e863ec75b` | `d59d259bcd5cbb2d0000094f34229cf4171d732dda3501f20f4829748daf3840` |
| Linux x64 KLIB | `408db06000fa492a24d1bb18c0a3c6585130a0a1680e8791c80707a873129920` | `554227caa913c133b043034ca51e881abfce4f759028cbf8dc7b4e89408ac946` |
| Android AAR | `d219fb5fa0d0f1a410f948d9b0eaad86ddb0e4ec53d06bc27a7d63ccd4855474` | `08efd78d6d1cbef44d335f1d96aa99cc6efd52124dc03d436df51ec801f8bb12` |

The exact commands, source-file hashes, raw XML paths, and full failure history are in `/tmp/dyn4k-portable-body-coverage-result.md`. The candidate is provisional until the body and collision owners commit accepted source and the combined manifest is reviewed. Local host execution does not establish device, Apple, Windows, full runtime, physical, numerical, or release qualification.
