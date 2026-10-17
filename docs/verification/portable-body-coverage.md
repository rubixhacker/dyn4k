# Portable body coverage on the integrated candidate

## Reader and scope

This report maps the seven root dynamics test files from pinned dyn4j 6.0.0 source revision `058bf6d982a0fb89b54050f929f6ea9dae53b714` to common Kotlin tests. The corpus began at body source `cb4492f20fc980445b7f5377234cadefc5426428` and includes committed integration head `241e69e1fb33541229f54bf8e56860452d38b95f`. This report covers the body test subtree only; it does not qualify the complete compatibility corpus or any full runtime lane.

The pinned files contain 124 `@Test` annotations. JUnit 4 executes 124 cases for these files against the baseline and the integrated candidate. None of the seven files uses a parameterized runner or inherits test methods. The final exact-head run, including raw XML paths and hashes, is recorded in `/tmp/dyn4k-portable-body-final-assertions-result.md`.

The common tests exercise `org.dyn4j` objects through public methods and a Kotlin `Body` subclass for protected state. A common test can cover several source methods when those methods check one behavior together. The table names every source method, including error cases. Names in the right column are methods under `dyn4k-core/src/commonTest/kotlin/org/dyn4j/coverage/dynamics/body/`.

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

The seven source files have **124 mapped identities** and **zero whole-method JVM-only waivers**. The unchanged Java run separately checks Java source compilation and protected field access. Common Kotlin alone cannot establish those language contracts. The public `Body.copy()` test checks copied damping and rest detection. It mutates force, torque, mass, and fixture state after copying to verify independence. Fixture mutation is a supplemental copy check; pinned `BodyTest.copy` does not assert it. A common Kotlin `Body` subclass exposes protected state for the copy and `apply` tests. The copy probe checks rest time, rest state, detection, stored force, torque, and mass values and identities. It checks each pending item and collection identity, then mutates original state to verify independence. The `apply` probe checks protected force and torque list sizes after every rearmed overload, both current force components, and current torque. It also checks empty lists and zero force/torque for zero-mass calls. The single zero-density fixture case checks type, mass, inertia, and center before adding more fixtures. Pinned `SettingsTest.getSet` checks individual setter/getter pairs in the two validation methods. The settings `set(Settings)` path is supplemental; both it and the mapped `copy` path assert all 17 changed fields. The portable tests use fixed expected values for velocities, masses, force and torque sums, bounds, orientation wraps, step ratios, and error types. `controlledWrongForceGetterFailsThePortableOracle` is a supplemental negative control and is not counted as a pinned source identity.

## Evidence and qualification boundary

The previous candidate run is retained at `/tmp/dyn4k-portable-body-expanded-fix-result.md` with raw XML in `/tmp/dyn4k-portable-body-expanded-xml.tar.gz`. It predates the final two assertions and the current integration merge.

The exact-head baseline and candidate Java runs, six common host lanes, controlled mutants, staged artifacts, and independent consumers are recorded with commands, counts, and hashes in `/tmp/dyn4k-portable-body-final-assertions-result.md`. Java XML execution identities are compared with the 124 source identities, rather than inferred from this table's method names.

The combined frozen qualification manifest still needs exact-head review and hosted execution. Local host tests do not establish Android device, Apple, Windows, full runtime, physical, numerical, or release qualification.
