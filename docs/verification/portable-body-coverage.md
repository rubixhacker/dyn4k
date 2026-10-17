# Portable body coverage at the provisional body source

## Reader and scope

This report maps the seven root dynamics test files from pinned dyn4j 6.0.0 source revision `058bf6d982a0fb89b54050f929f6ea9dae53b714` to common Kotlin tests. The candidate started at `cb4492f20fc980445b7f5377234cadefc5426428` on `codex/port-coverage-body`. The candidate body and collision implementations are provisional. This report covers this body's test subtree only; it does not qualify the complete compatibility corpus or any full runtime lane.

The pinned files contain 124 `@Test` annotations. JUnit 4 executes 124 cases for these files against the baseline and 124 against the provisional candidate. None of the seven files uses a parameterized runner or inherits test methods. Both unchanged Java runs completed with zero failures and zero ignored cases. The raw XML is archived with the CLI result in `/tmp/dyn4k-portable-body-coverage-result.md`.

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

The unchanged Java sources compiled with `javac --release 8` against each provider. The pinned baseline JAR has SHA-256 `204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e5af5162b2b3e`. The candidate JVM JAR has SHA-256 `85c95a51407b7249d502ab9cfdb8946b096de1961c246539f29740e9d304baea`. Both raw Java XML files contain 124 tests, zero failures, errors, or skips. Fresh baseline XML has SHA-256 `9f9b3832b6b449d85e300e240a612eb6bbacbb24056a917aa9b6de9185830b09`. Fresh candidate XML has SHA-256 `04bec87187751144521535631b656950b289ae75b2a28a3cef529edca19ca7ee`.

The six available local `dyn4k-core` host tasks each executed 56 common tests. Each host ran 29 tests in the body subtree, with zero failures, errors, or skips. The 29 include 27 mapped methods, one additional fixture-view test, and one supplemental wrong-getter control. These host tasks do not execute 124 separate portable cases. The map above relates source identities to behavioral counterparts.

| Host task | New body XML SHA-256: values / physics |
| --- | --- |
| `jvmTest` | `1e109c1f3ac5b6397dc70a763e4f94b3792181b828b0f728c5ce0e04a2bcf57d` / `ea847638a8596cbd3c602c1ecf3ec616805f1fa8294469e439b05a0bddb03b6a` |
| `jsNodeTest` | `6ec22e8589bf82dacab0b8122d015dc94f7e07d003433396a7bee77916dc5bdf` / `dff9fc6a6cab540bbf188217e7832d6740ff047464a76a7ab3e26f47d27663c8` |
| `wasmJsNodeTest` | `688b1da8abd6923824233a38fe43824ac3235c5dac3f16de04c747adbc845c40` / `96042c9b4f483eb9279c20630bbf51cab2650a55c5aae7117812a36a064952fc` |
| `wasmWasiNodeTest` | `af0e07c88773704d9d4e60507960718b983520e809c41354f9a9c3507e48b395` / `e3e63fdf91194988ccd9c887a11c33ed94b92ee3228a83f03f5d0a422cc5fe48` |
| `linuxX64Test` | `298d50c12b90e5cad0c16f7d3985c3b45683b415d0f0085bf55bae915dd7affc` / `55fcf4866a26584861d8a9db7c4b35a20808b1b1a3b7feccc767bbc2f99b87f2` |
| `testAndroidHostTest` | `aa9b0eaef6b107962237b21428ca7a1803804100e0b4cac6ea946ec649021b3b` / `443d4cd7c26b8bd2891ca85a2a6d22d7117334e4af0a1fac722107185369c59c` |

The repaired XML archive is `/tmp/dyn4k-portable-body-fix-xml.tar.gz`, SHA-256 `df9ea2fdae63963a3dcf3bb79039d8514f40ea08f81b48ee09a206279a2fa3ad`. It contains 26 XML files: baseline and candidate Java results, plus four suites on each of six hosts. The Java, staged Kotlin, and Android host dynamics consumers ran unchanged. They reported `DYNAMICS_CONSUMER_OK` or `DYNAMICS_KOTLIN_CONSUMER_OK`. Both baseline and candidate null probes reported `ArgumentNullException: convex cannot be null`.

Both modules were staged locally for the six available target publications. Artifact IDs and SHA-256 values are:

| Target publication | `dyn4k-core` binary | `dyn4k` binary |
| --- | --- | --- |
| JVM JAR | `85c95a51407b7249d502ab9cfdb8946b096de1961c246539f29740e9d304baea` | `3ff180079fc36ff98e2217788099c4f4b67078b93c3df6dc330c216949d0f8a8` |
| JS KLIB | `acef7e24033cd3126ad170197a124c9f697207d256714c363dee378c4da1b1ca` | `3fca1a4870129d03c3d95f8ea7f82d40fdabb944b009aa257772ae68d5c072b5` |
| Wasm JS KLIB | `53b8bd0a3904b66f8d287bab389622da7b92db32a35578c4fbbfe6be38fdbbfe` | `759d8bbfe213b0f84a3558a6ca94f151ab45ac75e804bf0bdd69e3161900131e` |
| Wasm WASI KLIB | `cff60eef6d6cc90e6ac2dac345e45e33cb2c6a30be6379186242f69e863ec75b` | `d59d259bcd5cbb2d0000094f34229cf4171d732dda3501f20f4829748daf3840` |
| Linux x64 KLIB | `408db06000fa492a24d1bb18c0a3c6585130a0a1680e8791c80707a873129920` | `554227caa913c133b043034ca51e881abfce4f759028cbf8dc7b4e89408ac946` |
| Android AAR | `d219fb5fa0d0f1a410f948d9b0eaad86ddb0e4ec53d06bc27a7d63ccd4855474` | `08efd78d6d1cbef44d335f1d96aa99cc6efd52124dc03d436df51ec801f8bb12` |

The exact commands, source-file hashes, raw XML paths, and failure history are in `/tmp/dyn4k-portable-body-fix-result.md`. Source sync was attempted after the numerical merger finished at `5457e5212ca3b0f50fab3a30f410638397930f72`. The integration merge conflicted in `dyn4k-core/build.gradle.kts` and was aborted. A read-only merge preview found the same conflict with collision head `f97dab70e27693297bdfbd9b8383c0a7a8cc98eb`. The build registration conflict requires its owner to resolve it; this test branch retains the provisional source at `cb4492f20fc980445b7f5377234cadefc5426428`. The combined manifest still needs exact-head review. Local host execution does not establish device, Apple, Windows, full runtime, physical, numerical, or release qualification.
