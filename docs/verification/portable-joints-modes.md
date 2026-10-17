# Portable joint modes corpus

This bounded corpus covers the Wheel, Weld, Pin, Pulley, Angle, Motor, and Friction tests in [Run the full compatibility corpus and unchanged migration applications](https://github.com/rubixhacker/dyn4k/issues/42). It does not close that issue or qualify every target.

## Identity and source

- Owner: GPT-6-Sol. Raw `turn_context`: `/var/home/stewart/.codex/sessions/2026/10/17/rollout-2026-10-17T14-44-11-01a14b64-ad1d-7ea0-aabb-56989ed2e742.jsonl:8` and this review-fix turn at line 957, both with `payload.model=gpt-6-sol`.
- Branch: `codex/port-coverage-joints-modes`. Starting source commit: `8203a21d0aa66fbbc75c5d0d80789327020b5e91`.
- Pinned upstream source: `058bf6d982a0fb89b54050f929f6ea9dae53b714`. The pinned binary SHA-256 is `204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e`.
- Identity inventory: `/tmp/dyn4k-joint-all-pinned-test-identities.txt`, SHA-256 `1bc94d6f191d19a4475073c9f5c934bab00f82627bb52b4726711c98daa5c62f`. Filtering the seven named classes gives exactly 172 identities: Wheel 46, Weld 35, Pin 27, Pulley 19, Angle 18, Motor 15, Friction 12.
- Public test seam: common Kotlin constructors, mode setters/getters, wake state, `copy`, `shift`, and joint solver reaction. The three coefficient probes use subclass access to the protected update hook, matching the original extension seam.
- The eight common test files have a sorted-byte concatenation SHA-256 of `240374b7632ec8b4b0989432ba324b2f76acdc34431416dccfe1212cd57175f0` at test source commit `e7a1ced278d87d76c07149f0ba236c727257bcbd`.

| Pinned Java test file | Expanded cases | SHA-256 |
| --- | ---: | --- |
| [WheelJointTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/dynamics/joint/WheelJointTest.java) | 46 | `42072bf7a8b077629ffdb43b37634752b57134b80fea0106a909d1b1fc0d81d1` |
| [WeldJointTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/dynamics/joint/WeldJointTest.java) | 35 | `9988bd733cbf6501826c0bd3891744fe3d255039d806f3aa6fe987e3c37f7856` |
| [PinJointTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/dynamics/joint/PinJointTest.java) | 27 | `e3a1d87e3d6e36a400cd8216bfd00815f78e8f65583487521f713ab74d275a20` |
| [PulleyJointTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/dynamics/joint/PulleyJointTest.java) | 19 | `123f222b84c795ffc240c6ee43370079b9ea73dd472b3e4866cc13a38ce2338d` |
| [AngleJointTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/dynamics/joint/AngleJointTest.java) | 18 | `67e6e733377892af310491628ed42d15a4f147fa49d60ced13cf3e44c6673d46` |
| [MotorJointTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/dynamics/joint/MotorJointTest.java) | 15 | `d70fbb2203435325494b4c42fc529c9b054d8be0a3c9c10da3e3fa9bcdae039f` |
| [FrictionJointTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/dynamics/joint/FrictionJointTest.java) | 12 | `d70aee8219f0c74ab10b427fb8021b3bba31f4100cf3763f39fdb33eec2b8684` |

## Coverage and evidence

The common corpus has 170 distinct cases. The direct translations retain every `TestCase.assert*` call in their corresponding original methods. The seven copy cases check public configuration, body replacement and identity, owner/user-data reset, and nonzero solver reaction impulses transferred into a copy. The three coefficient cases use the pinned original expected values: Pin 7937.606 and 2.839, Weld 1984.401 and 5.679, and Wheel 3968.803 and 4.015, each with the original `1e-3` tolerance. Each also checks that the damping ratio remains 0.5 after switching to stiffness mode and updating the coefficients, as in pinned Java. The copy and coefficient file begins with the exact pinned upstream BSD notice. Direct Java package/protected field identity and matrix state assertions within the original copy methods remain covered by unchanged Java JUnit; common tests observe their public effects.

The two Pulley null-body identities are JVM-only source contracts. The common `PulleyJoint` constructor declares both body parameters non-null; Kotlin common cannot make the original Java call without a Kotlin cast failing before the constructor. The unchanged Java tests execute those exact calls against both artifacts and require `NullPointerException`.

Across the disjoint joint branches, four identities use this JVM-only contract: `DistanceJointTest#createWithNullBody1`, `DistanceJointTest#createWithNullBody2`, `PulleyJointTest#createWithNullBody1`, and `PulleyJointTest#createWithNullBody2`. Each pinned source method passes null to the corresponding constructor argument and expects `NullPointerException`; both common constructors declare non-null body parameters. The Distance cases remain mapped in the core branch. Both unchanged Java suites execute all four under the registered joint test list.

Run from this worktree with JDK 21, `ANDROID_HOME=/home/stewart/Android/Sdk`, `--offline --max-workers=1 --rerun-tasks --continue --console=plain`:

```sh
./gradlew :dyn4k-core:runBaselineJointTests :dyn4k-core:runUpstreamJointTests \
  :dyn4k-core:jvmTest :dyn4k-core:linuxX64Test :dyn4k-core:jsNodeTest \
  :dyn4k-core:wasmJsNodeTest :dyn4k-core:wasmWasiNodeTest \
  :dyn4k-core:testAndroidHostTest :dyn4k-core:runStagedJointConsumer \
  :dyn4k-core:runStagedJointKotlinConsumer
```

The final command passed from test source commit `e7a1ced278d87d76c07149f0ba236c727257bcbd`. Both unchanged Java package suites ran **348/348** cases; the seven owned classes contribute 172 cases to each. Both staged joint consumers ran, including the ten-type Java trace and Kotlin consumer. The actual candidate JVM artifact `dyn4k-core-jvm-0.1.0-alpha.1.jar` has SHA-256 `944b4581beff66b5c1b7c233e54a759a18da312bd689325645cad764bcb0802a`. Raw final log: `/tmp/dyn4k-joint-modes-review-fix-six-host.log`, SHA-256 `6462f06840e007c93f169519d2289af28ffc00181d1cf7c0ef1afe8cf7abfd4b`.

Each row hashes the sorted concatenation of the eight owned `TEST-*.xml` files for that task. All 48 raw files are retained at `/tmp/dyn4k-joint-modes-xml/<task>/`; `/tmp/dyn4k-joint-modes-xml/manifest.json` lists every file hash, the source and inventory hashes, all 170 normalized identities, and each host digest. Its SHA-256 is `add982dc913dffe998841dcc3296296e027655402ae821e6126c9b0dd043d292`. Every archived file and combined digest was verified against the manifest. All six tasks executed the same 170 distinct normalized class/method identities, SHA-256 `39273e5579b5649e5391ce3db27cfe67aa954cde098cffcbc5708fa69a35032b`; each has zero duplicates, missing identities, or extra identities. Normalization removes host prefixes from class names and bracketed host suffixes from method names.

| Host task | Cases | Failures | Errors | Skips | Raw XML SHA-256 |
| --- | ---: | ---: | ---: | ---: | --- |
| `jvmTest` | 170 | 0 | 0 | 0 | `37e046cd1ab950ad49aa5cfd8a4c999e52780f1af2d5499f3b92078a72045ad6` |
| `linuxX64Test` | 170 | 0 | 0 | 0 | `038e970a9e96e9f29069932a40b10e402779adbf784ece72d0cade19a2b72227` |
| `jsNodeTest` | 170 | 0 | 0 | 0 | `f7ac271802d80b095c666c4e7e9c8cec57aa188902a6954301c67dd387c39292` |
| `wasmJsNodeTest` | 170 | 0 | 0 | 0 | `91c151cdbb14d9152d374a8f9b89bd2df32f71b82dc0c97df74b476955541c57` |
| `wasmWasiNodeTest` | 170 | 0 | 0 | 0 | `5f4118c734ddc1284ca4717732aa870a2f4f5c4b6343d047675094a018f0b76e` |
| `testAndroidHostTest` | 170 | 0 | 0 | 0 | `d21b91859a55d38fcacb88175f5201ae6c69281eeff744d866dbd5a94a6a7727` |

This is six available host configurations, including an Android host test. It is not an Android device or full 21-target runtime pass.

The review-fix sensitivity test changed the new post-stiffness damping expectation from 0.5 to 0.25 in each of Pin, Weld, and Wheel. The targeted JVM run completed three tests with three failures: `pinComputeSpringStiffnessFrequency`, `weldComputeSpringStiffnessFrequency`, and `wheelComputeSpringStiffnessFrequency`. All three expectations were restored to 0.5 before the committed six-host run. Negative log: `/tmp/dyn4k-joint-modes-damping-negative.log`, SHA-256 `cf956b4b2d9be21f818a30d73f2100a1acb3145cf65042cbc64ad258537f7aa6`; negative XML: `/tmp/dyn4k-joint-modes-damping-negative.xml`, SHA-256 `d4a37f1c2f28beb735f67bbeea3e58cd62658ff4b2b2d0f8a7da12f1a6233b8c`.

## Separate world dependency

The 32 world-driven joint simulation identities are separate from the 172 package identities mapped here. They were not executed as part of this review fix and have no candidate pass claim from this branch. They require `org.dyn4j.world.World`, owned by [Step interacting bodies with callbacks and continuous collision](https://github.com/rubixhacker/dyn4k/issues/39).

## Integration preflight

The latest committed `codex/dyn4k-port` tip was `80ffe42ba427d6b34dcda6059774fd420b22441d`. `git merge-tree --write-tree HEAD codex/dyn4k-port` reported a content conflict in `dyn4k-core/build.gradle.kts`. The integration tip also omits joint JVM API entries and joint test and staged consumer task registrations present on this branch. Resolving that conflict would require editing outside this slice's owned paths, so no merge was made. The branch remains ready for an integration owner to reconcile those build registrations.

## Exact identity map

Each common destination is one executed test function. Two Java-only entries retain their exact unchanged Java execution.

| Original pinned Java identity | Common destination or disposition |
| --- | --- |
| `org.dyn4j.dynamics.joint.AngleJointTest#create` | `UpstreamAngleJointModesCoverageTest.create` |
| `org.dyn4j.dynamics.joint.AngleJointTest#setUpperLimitSuccess` | `UpstreamAngleJointModesCoverageTest.setUpperLimitSuccess` |
| `org.dyn4j.dynamics.joint.AngleJointTest#setLowerLimit` | `UpstreamAngleJointModesCoverageTest.setLowerLimit` |
| `org.dyn4j.dynamics.joint.AngleJointTest#setUpperAndLowerLimits` | `UpstreamAngleJointModesCoverageTest.setUpperAndLowerLimits` |
| `org.dyn4j.dynamics.joint.AngleJointTest#setUpperAndLowerLimitsToSameValue` | `UpstreamAngleJointModesCoverageTest.setUpperAndLowerLimitsToSameValue` |
| `org.dyn4j.dynamics.joint.AngleJointTest#setLimitsReferenceAngle` | `UpstreamAngleJointModesCoverageTest.setLimitsReferenceAngle` |
| `org.dyn4j.dynamics.joint.AngleJointTest#setRatio` | `UpstreamAngleJointModesCoverageTest.setRatio` |
| `org.dyn4j.dynamics.joint.AngleJointTest#setRatioZero` | `UpstreamAngleJointModesCoverageTest.setRatioZero` |
| `org.dyn4j.dynamics.joint.AngleJointTest#setLimitEnabledSleep` | `UpstreamAngleJointModesCoverageTest.setLimitEnabledSleep` |
| `org.dyn4j.dynamics.joint.AngleJointTest#setLimitsSameSleep` | `UpstreamAngleJointModesCoverageTest.setLimitsSameSleep` |
| `org.dyn4j.dynamics.joint.AngleJointTest#setLimitsDifferentSleep` | `UpstreamAngleJointModesCoverageTest.setLimitsDifferentSleep` |
| `org.dyn4j.dynamics.joint.AngleJointTest#setLowerLimitSleep` | `UpstreamAngleJointModesCoverageTest.setLowerLimitSleep` |
| `org.dyn4j.dynamics.joint.AngleJointTest#setUpperLimitSleep` | `UpstreamAngleJointModesCoverageTest.setUpperLimitSleep` |
| `org.dyn4j.dynamics.joint.AngleJointTest#setLimitsEnabledSameSleep` | `UpstreamAngleJointModesCoverageTest.setLimitsEnabledSameSleep` |
| `org.dyn4j.dynamics.joint.AngleJointTest#setLimitsEnabledDifferentSleep` | `UpstreamAngleJointModesCoverageTest.setLimitsEnabledDifferentSleep` |
| `org.dyn4j.dynamics.joint.AngleJointTest#shift` | `UpstreamAngleJointModesCoverageTest.shift` |
| `org.dyn4j.dynamics.joint.AngleJointTest#copy` | `UpstreamJointModesCopyAndCoefficientsTest.angleCopy` |
| `org.dyn4j.dynamics.joint.AngleJointTest#copyFailed` | `UpstreamAngleJointModesCoverageTest.copyFailed` |
| `org.dyn4j.dynamics.joint.FrictionJointTest#createWithTwoDifferentBodies` | `UpstreamFrictionJointModesCoverageTest.createWithTwoDifferentBodies` |
| `org.dyn4j.dynamics.joint.FrictionJointTest#createWithNullBody1` | `UpstreamFrictionJointModesCoverageTest.createWithNullBody1` |
| `org.dyn4j.dynamics.joint.FrictionJointTest#createWithNullBody2` | `UpstreamFrictionJointModesCoverageTest.createWithNullBody2` |
| `org.dyn4j.dynamics.joint.FrictionJointTest#createWithNullAnchor` | `UpstreamFrictionJointModesCoverageTest.createWithNullAnchor` |
| `org.dyn4j.dynamics.joint.FrictionJointTest#createWithSameBody` | `UpstreamFrictionJointModesCoverageTest.createWithSameBody` |
| `org.dyn4j.dynamics.joint.FrictionJointTest#setMaximumTorque` | `UpstreamFrictionJointModesCoverageTest.setMaximumTorque` |
| `org.dyn4j.dynamics.joint.FrictionJointTest#setNegativeMaximumTorque` | `UpstreamFrictionJointModesCoverageTest.setNegativeMaximumTorque` |
| `org.dyn4j.dynamics.joint.FrictionJointTest#setMaximumForce` | `UpstreamFrictionJointModesCoverageTest.setMaximumForce` |
| `org.dyn4j.dynamics.joint.FrictionJointTest#setNegativeMaximumForce` | `UpstreamFrictionJointModesCoverageTest.setNegativeMaximumForce` |
| `org.dyn4j.dynamics.joint.FrictionJointTest#shift` | `UpstreamFrictionJointModesCoverageTest.shift` |
| `org.dyn4j.dynamics.joint.FrictionJointTest#copy` | `UpstreamJointModesCopyAndCoefficientsTest.frictionCopy` |
| `org.dyn4j.dynamics.joint.FrictionJointTest#copyFailed` | `UpstreamFrictionJointModesCoverageTest.copyFailed` |
| `org.dyn4j.dynamics.joint.MotorJointTest#createWithTwoDifferentBodies` | `UpstreamMotorJointModesCoverageTest.createWithTwoDifferentBodies` |
| `org.dyn4j.dynamics.joint.MotorJointTest#createWithNullBody2` | `UpstreamMotorJointModesCoverageTest.createWithNullBody2` |
| `org.dyn4j.dynamics.joint.MotorJointTest#createWithNullBody1` | `UpstreamMotorJointModesCoverageTest.createWithNullBody1` |
| `org.dyn4j.dynamics.joint.MotorJointTest#createWithSameBody` | `UpstreamMotorJointModesCoverageTest.createWithSameBody` |
| `org.dyn4j.dynamics.joint.MotorJointTest#setValidCorrectionFactor` | `UpstreamMotorJointModesCoverageTest.setValidCorrectionFactor` |
| `org.dyn4j.dynamics.joint.MotorJointTest#setNegativeCorrectionFactor` | `UpstreamMotorJointModesCoverageTest.setNegativeCorrectionFactor` |
| `org.dyn4j.dynamics.joint.MotorJointTest#setCorrectionFactorGreaterThan1` | `UpstreamMotorJointModesCoverageTest.setCorrectionFactorGreaterThan1` |
| `org.dyn4j.dynamics.joint.MotorJointTest#setMaximumTorque` | `UpstreamMotorJointModesCoverageTest.setMaximumTorque` |
| `org.dyn4j.dynamics.joint.MotorJointTest#setNegativeMaximumTorque` | `UpstreamMotorJointModesCoverageTest.setNegativeMaximumTorque` |
| `org.dyn4j.dynamics.joint.MotorJointTest#setMaximumForce` | `UpstreamMotorJointModesCoverageTest.setMaximumForce` |
| `org.dyn4j.dynamics.joint.MotorJointTest#setNegativeMaximumForce` | `UpstreamMotorJointModesCoverageTest.setNegativeMaximumForce` |
| `org.dyn4j.dynamics.joint.MotorJointTest#setLinearTargetSleep` | `UpstreamMotorJointModesCoverageTest.setLinearTargetSleep` |
| `org.dyn4j.dynamics.joint.MotorJointTest#setAngularTargetSleep` | `UpstreamMotorJointModesCoverageTest.setAngularTargetSleep` |
| `org.dyn4j.dynamics.joint.MotorJointTest#copy` | `UpstreamJointModesCopyAndCoefficientsTest.motorCopy` |
| `org.dyn4j.dynamics.joint.MotorJointTest#copyFailed` | `UpstreamMotorJointModesCoverageTest.copyFailed` |
| `org.dyn4j.dynamics.joint.PinJointTest#createSuccess` | `UpstreamPinJointModesCoverageTest.createSuccess` |
| `org.dyn4j.dynamics.joint.PinJointTest#createWithNullBody` | `UpstreamPinJointModesCoverageTest.createWithNullBody` |
| `org.dyn4j.dynamics.joint.PinJointTest#createWithNullTarget` | `UpstreamPinJointModesCoverageTest.createWithNullTarget` |
| `org.dyn4j.dynamics.joint.PinJointTest#setTarget` | `UpstreamPinJointModesCoverageTest.setTarget` |
| `org.dyn4j.dynamics.joint.PinJointTest#setNullTarget` | `UpstreamPinJointModesCoverageTest.setNullTarget` |
| `org.dyn4j.dynamics.joint.PinJointTest#isSpringEnabled` | `UpstreamPinJointModesCoverageTest.isSpringEnabled` |
| `org.dyn4j.dynamics.joint.PinJointTest#isSpringDamperEnabled` | `UpstreamPinJointModesCoverageTest.isSpringDamperEnabled` |
| `org.dyn4j.dynamics.joint.PinJointTest#setSpringDampingRatio` | `UpstreamPinJointModesCoverageTest.setSpringDampingRatio` |
| `org.dyn4j.dynamics.joint.PinJointTest#setNegativeDampingRatio` | `UpstreamPinJointModesCoverageTest.setNegativeDampingRatio` |
| `org.dyn4j.dynamics.joint.PinJointTest#setDampingRatioGreaterThan1` | `UpstreamPinJointModesCoverageTest.setDampingRatioGreaterThan1` |
| `org.dyn4j.dynamics.joint.PinJointTest#setSpringFrequency` | `UpstreamPinJointModesCoverageTest.setSpringFrequency` |
| `org.dyn4j.dynamics.joint.PinJointTest#setSpringMode` | `UpstreamPinJointModesCoverageTest.setSpringMode` |
| `org.dyn4j.dynamics.joint.PinJointTest#setSpringStiffnessNegative` | `UpstreamPinJointModesCoverageTest.setSpringStiffnessNegative` |
| `org.dyn4j.dynamics.joint.PinJointTest#setSpringStiffness` | `UpstreamPinJointModesCoverageTest.setSpringStiffness` |
| `org.dyn4j.dynamics.joint.PinJointTest#setSpringFrequencyNegative` | `UpstreamPinJointModesCoverageTest.setSpringFrequencyNegative` |
| `org.dyn4j.dynamics.joint.PinJointTest#setSpringMaximumForceNegative` | `UpstreamPinJointModesCoverageTest.setSpringMaximumForceNegative` |
| `org.dyn4j.dynamics.joint.PinJointTest#setSpringMaximumForce` | `UpstreamPinJointModesCoverageTest.setSpringMaximumForce` |
| `org.dyn4j.dynamics.joint.PinJointTest#computeSpringStiffnessFrequency` | `UpstreamJointModesCopyAndCoefficientsTest.pinComputeSpringStiffnessFrequency` |
| `org.dyn4j.dynamics.joint.PinJointTest#shiftCoordinates` | `UpstreamPinJointModesCoverageTest.shiftCoordinates` |
| `org.dyn4j.dynamics.joint.PinJointTest#setTargetSleep` | `UpstreamPinJointModesCoverageTest.setTargetSleep` |
| `org.dyn4j.dynamics.joint.PinJointTest#getSetCorrectionFactor` | `UpstreamPinJointModesCoverageTest.getSetCorrectionFactor` |
| `org.dyn4j.dynamics.joint.PinJointTest#setNegativeCorrectionFactor` | `UpstreamPinJointModesCoverageTest.setNegativeCorrectionFactor` |
| `org.dyn4j.dynamics.joint.PinJointTest#setGreaterThan1CorrectionFactor` | `UpstreamPinJointModesCoverageTest.setGreaterThan1CorrectionFactor` |
| `org.dyn4j.dynamics.joint.PinJointTest#setLessThanZeroCorrectionMaximumForce` | `UpstreamPinJointModesCoverageTest.setLessThanZeroCorrectionMaximumForce` |
| `org.dyn4j.dynamics.joint.PinJointTest#getSetCorrectionMaximumForce` | `UpstreamPinJointModesCoverageTest.getSetCorrectionMaximumForce` |
| `org.dyn4j.dynamics.joint.PinJointTest#copy` | `UpstreamJointModesCopyAndCoefficientsTest.pinCopy` |
| `org.dyn4j.dynamics.joint.PinJointTest#copyFailed` | `UpstreamPinJointModesCoverageTest.copyFailed` |
| `org.dyn4j.dynamics.joint.PulleyJointTest#createSuccess` | `UpstreamPulleyJointModesCoverageTest.createSuccess` |
| `org.dyn4j.dynamics.joint.PulleyJointTest#createWithNullBody1` | JVM-only: unchanged Java constructor null contract |
| `org.dyn4j.dynamics.joint.PulleyJointTest#createWithNullBody2` | JVM-only: unchanged Java constructor null contract |
| `org.dyn4j.dynamics.joint.PulleyJointTest#createWithNullAnchor1` | `UpstreamPulleyJointModesCoverageTest.createWithNullAnchor1` |
| `org.dyn4j.dynamics.joint.PulleyJointTest#createWithNullAnchor2` | `UpstreamPulleyJointModesCoverageTest.createWithNullAnchor2` |
| `org.dyn4j.dynamics.joint.PulleyJointTest#createWithNullAnchor3` | `UpstreamPulleyJointModesCoverageTest.createWithNullAnchor3` |
| `org.dyn4j.dynamics.joint.PulleyJointTest#createWithNullAnchor4` | `UpstreamPulleyJointModesCoverageTest.createWithNullAnchor4` |
| `org.dyn4j.dynamics.joint.PulleyJointTest#createWithSameBody` | `UpstreamPulleyJointModesCoverageTest.createWithSameBody` |
| `org.dyn4j.dynamics.joint.PulleyJointTest#setRatio` | `UpstreamPulleyJointModesCoverageTest.setRatio` |
| `org.dyn4j.dynamics.joint.PulleyJointTest#setRatioNegative` | `UpstreamPulleyJointModesCoverageTest.setRatioNegative` |
| `org.dyn4j.dynamics.joint.PulleyJointTest#setRatioZero` | `UpstreamPulleyJointModesCoverageTest.setRatioZero` |
| `org.dyn4j.dynamics.joint.PulleyJointTest#setRatioSleep` | `UpstreamPulleyJointModesCoverageTest.setRatioSleep` |
| `org.dyn4j.dynamics.joint.PulleyJointTest#setSlackEnabled` | `UpstreamPulleyJointModesCoverageTest.setSlackEnabled` |
| `org.dyn4j.dynamics.joint.PulleyJointTest#setLength` | `UpstreamPulleyJointModesCoverageTest.setLength` |
| `org.dyn4j.dynamics.joint.PulleyJointTest#setLengthNegative` | `UpstreamPulleyJointModesCoverageTest.setLengthNegative` |
| `org.dyn4j.dynamics.joint.PulleyJointTest#setLengthSleep` | `UpstreamPulleyJointModesCoverageTest.setLengthSleep` |
| `org.dyn4j.dynamics.joint.PulleyJointTest#shiftCoordinates` | `UpstreamPulleyJointModesCoverageTest.shiftCoordinates` |
| `org.dyn4j.dynamics.joint.PulleyJointTest#copy` | `UpstreamJointModesCopyAndCoefficientsTest.pulleyCopy` |
| `org.dyn4j.dynamics.joint.PulleyJointTest#copyFailed` | `UpstreamPulleyJointModesCoverageTest.copyFailed` |
| `org.dyn4j.dynamics.joint.WeldJointTest#createSuccess` | `UpstreamWeldJointModesCoverageTest.createSuccess` |
| `org.dyn4j.dynamics.joint.WeldJointTest#createWithNullBody1` | `UpstreamWeldJointModesCoverageTest.createWithNullBody1` |
| `org.dyn4j.dynamics.joint.WeldJointTest#createWithNullBody2` | `UpstreamWeldJointModesCoverageTest.createWithNullBody2` |
| `org.dyn4j.dynamics.joint.WeldJointTest#createWithNullAnchor` | `UpstreamWeldJointModesCoverageTest.createWithNullAnchor` |
| `org.dyn4j.dynamics.joint.WeldJointTest#createWithSameBody` | `UpstreamWeldJointModesCoverageTest.createWithSameBody` |
| `org.dyn4j.dynamics.joint.WeldJointTest#isSpringEnabled` | `UpstreamWeldJointModesCoverageTest.isSpringEnabled` |
| `org.dyn4j.dynamics.joint.WeldJointTest#isSpringDamperEnabled` | `UpstreamWeldJointModesCoverageTest.isSpringDamperEnabled` |
| `org.dyn4j.dynamics.joint.WeldJointTest#setSpringDampingRatio` | `UpstreamWeldJointModesCoverageTest.setSpringDampingRatio` |
| `org.dyn4j.dynamics.joint.WeldJointTest#setNegativeDampingRatio` | `UpstreamWeldJointModesCoverageTest.setNegativeDampingRatio` |
| `org.dyn4j.dynamics.joint.WeldJointTest#setDampingRatioGreaterThan1` | `UpstreamWeldJointModesCoverageTest.setDampingRatioGreaterThan1` |
| `org.dyn4j.dynamics.joint.WeldJointTest#setSpringFrequency` | `UpstreamWeldJointModesCoverageTest.setSpringFrequency` |
| `org.dyn4j.dynamics.joint.WeldJointTest#setSpringMode` | `UpstreamWeldJointModesCoverageTest.setSpringMode` |
| `org.dyn4j.dynamics.joint.WeldJointTest#setSpringStiffnessNegative` | `UpstreamWeldJointModesCoverageTest.setSpringStiffnessNegative` |
| `org.dyn4j.dynamics.joint.WeldJointTest#setSpringStiffness` | `UpstreamWeldJointModesCoverageTest.setSpringStiffness` |
| `org.dyn4j.dynamics.joint.WeldJointTest#setSpringFrequencyNegative` | `UpstreamWeldJointModesCoverageTest.setSpringFrequencyNegative` |
| `org.dyn4j.dynamics.joint.WeldJointTest#setSpringMaximumForceNegative` | `UpstreamWeldJointModesCoverageTest.setSpringMaximumForceNegative` |
| `org.dyn4j.dynamics.joint.WeldJointTest#setSpringMaximumForce` | `UpstreamWeldJointModesCoverageTest.setSpringMaximumForce` |
| `org.dyn4j.dynamics.joint.WeldJointTest#computeSpringStiffnessFrequency` | `UpstreamJointModesCopyAndCoefficientsTest.weldComputeSpringStiffnessFrequency` |
| `org.dyn4j.dynamics.joint.WeldJointTest#setUpperLimitSuccess` | `UpstreamWeldJointModesCoverageTest.setUpperLimitSuccess` |
| `org.dyn4j.dynamics.joint.WeldJointTest#setLowerLimit` | `UpstreamWeldJointModesCoverageTest.setLowerLimit` |
| `org.dyn4j.dynamics.joint.WeldJointTest#setUpperAndLowerLimits` | `UpstreamWeldJointModesCoverageTest.setUpperAndLowerLimits` |
| `org.dyn4j.dynamics.joint.WeldJointTest#setUpperAndLowerLimitsToSameValue` | `UpstreamWeldJointModesCoverageTest.setUpperAndLowerLimitsToSameValue` |
| `org.dyn4j.dynamics.joint.WeldJointTest#setLimitsReferenceAngle` | `UpstreamWeldJointModesCoverageTest.setLimitsReferenceAngle` |
| `org.dyn4j.dynamics.joint.WeldJointTest#setLimitsReferenceAngleSleep` | `UpstreamWeldJointModesCoverageTest.setLimitsReferenceAngleSleep` |
| `org.dyn4j.dynamics.joint.WeldJointTest#setLimitEnabledSleep` | `UpstreamWeldJointModesCoverageTest.setLimitEnabledSleep` |
| `org.dyn4j.dynamics.joint.WeldJointTest#setLimitsSameSleep` | `UpstreamWeldJointModesCoverageTest.setLimitsSameSleep` |
| `org.dyn4j.dynamics.joint.WeldJointTest#setLimitsDifferentSleep` | `UpstreamWeldJointModesCoverageTest.setLimitsDifferentSleep` |
| `org.dyn4j.dynamics.joint.WeldJointTest#setLowerLimitSleep` | `UpstreamWeldJointModesCoverageTest.setLowerLimitSleep` |
| `org.dyn4j.dynamics.joint.WeldJointTest#setUpperLimitSleep` | `UpstreamWeldJointModesCoverageTest.setUpperLimitSleep` |
| `org.dyn4j.dynamics.joint.WeldJointTest#setLimitsEnabledSameSleep` | `UpstreamWeldJointModesCoverageTest.setLimitsEnabledSameSleep` |
| `org.dyn4j.dynamics.joint.WeldJointTest#setLimitsEnabledDifferentSleep` | `UpstreamWeldJointModesCoverageTest.setLimitsEnabledDifferentSleep` |
| `org.dyn4j.dynamics.joint.WeldJointTest#setLimitsEnabledSleep` | `UpstreamWeldJointModesCoverageTest.setLimitsEnabledSleep` |
| `org.dyn4j.dynamics.joint.WeldJointTest#shift` | `UpstreamWeldJointModesCoverageTest.shift` |
| `org.dyn4j.dynamics.joint.WeldJointTest#copy` | `UpstreamJointModesCopyAndCoefficientsTest.weldCopy` |
| `org.dyn4j.dynamics.joint.WeldJointTest#copyFailed` | `UpstreamWeldJointModesCoverageTest.copyFailed` |
| `org.dyn4j.dynamics.joint.WheelJointTest#createSuccess` | `UpstreamWheelJointModesCoverageTest.createSuccess` |
| `org.dyn4j.dynamics.joint.WheelJointTest#createWithNullBody1` | `UpstreamWheelJointModesCoverageTest.createWithNullBody1` |
| `org.dyn4j.dynamics.joint.WheelJointTest#createWithNullBody2` | `UpstreamWheelJointModesCoverageTest.createWithNullBody2` |
| `org.dyn4j.dynamics.joint.WheelJointTest#createWithNullAnchor` | `UpstreamWheelJointModesCoverageTest.createWithNullAnchor` |
| `org.dyn4j.dynamics.joint.WheelJointTest#createWithNullAxis` | `UpstreamWheelJointModesCoverageTest.createWithNullAxis` |
| `org.dyn4j.dynamics.joint.WheelJointTest#isSpringEnabled` | `UpstreamWheelJointModesCoverageTest.isSpringEnabled` |
| `org.dyn4j.dynamics.joint.WheelJointTest#isSpringDamperEnabled` | `UpstreamWheelJointModesCoverageTest.isSpringDamperEnabled` |
| `org.dyn4j.dynamics.joint.WheelJointTest#setSpringRestOffset` | `UpstreamWheelJointModesCoverageTest.setSpringRestOffset` |
| `org.dyn4j.dynamics.joint.WheelJointTest#setSpringDampingRatio` | `UpstreamWheelJointModesCoverageTest.setSpringDampingRatio` |
| `org.dyn4j.dynamics.joint.WheelJointTest#setNegativeDampingRatio` | `UpstreamWheelJointModesCoverageTest.setNegativeDampingRatio` |
| `org.dyn4j.dynamics.joint.WheelJointTest#setDampingRatioGreaterThan1` | `UpstreamWheelJointModesCoverageTest.setDampingRatioGreaterThan1` |
| `org.dyn4j.dynamics.joint.WheelJointTest#setSpringFrequency` | `UpstreamWheelJointModesCoverageTest.setSpringFrequency` |
| `org.dyn4j.dynamics.joint.WheelJointTest#setSpringMode` | `UpstreamWheelJointModesCoverageTest.setSpringMode` |
| `org.dyn4j.dynamics.joint.WheelJointTest#setSpringStiffnessNegative` | `UpstreamWheelJointModesCoverageTest.setSpringStiffnessNegative` |
| `org.dyn4j.dynamics.joint.WheelJointTest#setSpringStiffness` | `UpstreamWheelJointModesCoverageTest.setSpringStiffness` |
| `org.dyn4j.dynamics.joint.WheelJointTest#setSpringFrequencyNegative` | `UpstreamWheelJointModesCoverageTest.setSpringFrequencyNegative` |
| `org.dyn4j.dynamics.joint.WheelJointTest#setSpringMaximumForceNegative` | `UpstreamWheelJointModesCoverageTest.setSpringMaximumForceNegative` |
| `org.dyn4j.dynamics.joint.WheelJointTest#setSpringMaximumForce` | `UpstreamWheelJointModesCoverageTest.setSpringMaximumForce` |
| `org.dyn4j.dynamics.joint.WheelJointTest#computeSpringStiffnessFrequency` | `UpstreamJointModesCopyAndCoefficientsTest.wheelComputeSpringStiffnessFrequency` |
| `org.dyn4j.dynamics.joint.WheelJointTest#setSpringRestOffsetAtRest` | `UpstreamWheelJointModesCoverageTest.setSpringRestOffsetAtRest` |
| `org.dyn4j.dynamics.joint.WheelJointTest#setMotorMaximumTorque` | `UpstreamWheelJointModesCoverageTest.setMotorMaximumTorque` |
| `org.dyn4j.dynamics.joint.WheelJointTest#setMaximumMotorTorqueNegative` | `UpstreamWheelJointModesCoverageTest.setMaximumMotorTorqueNegative` |
| `org.dyn4j.dynamics.joint.WheelJointTest#setMaximumMotorTorqueSleep` | `UpstreamWheelJointModesCoverageTest.setMaximumMotorTorqueSleep` |
| `org.dyn4j.dynamics.joint.WheelJointTest#setMaximumMotorTorqueEnabledSleep` | `UpstreamWheelJointModesCoverageTest.setMaximumMotorTorqueEnabledSleep` |
| `org.dyn4j.dynamics.joint.WheelJointTest#setMotorEnabled` | `UpstreamWheelJointModesCoverageTest.setMotorEnabled` |
| `org.dyn4j.dynamics.joint.WheelJointTest#setMotorEnabledSleep` | `UpstreamWheelJointModesCoverageTest.setMotorEnabledSleep` |
| `org.dyn4j.dynamics.joint.WheelJointTest#setMotorSpeed` | `UpstreamWheelJointModesCoverageTest.setMotorSpeed` |
| `org.dyn4j.dynamics.joint.WheelJointTest#setMotorSpeedSleep` | `UpstreamWheelJointModesCoverageTest.setMotorSpeedSleep` |
| `org.dyn4j.dynamics.joint.WheelJointTest#setUpperLimitSuccess` | `UpstreamWheelJointModesCoverageTest.setUpperLimitSuccess` |
| `org.dyn4j.dynamics.joint.WheelJointTest#setUpperLimitInvalid` | `UpstreamWheelJointModesCoverageTest.setUpperLimitInvalid` |
| `org.dyn4j.dynamics.joint.WheelJointTest#setLowerLimit` | `UpstreamWheelJointModesCoverageTest.setLowerLimit` |
| `org.dyn4j.dynamics.joint.WheelJointTest#setLowerLimitInvalid` | `UpstreamWheelJointModesCoverageTest.setLowerLimitInvalid` |
| `org.dyn4j.dynamics.joint.WheelJointTest#setUpperAndLowerLimits` | `UpstreamWheelJointModesCoverageTest.setUpperAndLowerLimits` |
| `org.dyn4j.dynamics.joint.WheelJointTest#setUpperAndLowerLimitsInvalid1` | `UpstreamWheelJointModesCoverageTest.setUpperAndLowerLimitsInvalid1` |
| `org.dyn4j.dynamics.joint.WheelJointTest#setUpperAndLowerLimitsInvalid2` | `UpstreamWheelJointModesCoverageTest.setUpperAndLowerLimitsInvalid2` |
| `org.dyn4j.dynamics.joint.WheelJointTest#setSameLimitValid` | `UpstreamWheelJointModesCoverageTest.setSameLimitValid` |
| `org.dyn4j.dynamics.joint.WheelJointTest#setLimitsEnabledSleep` | `UpstreamWheelJointModesCoverageTest.setLimitsEnabledSleep` |
| `org.dyn4j.dynamics.joint.WheelJointTest#setLimitsSameSleep` | `UpstreamWheelJointModesCoverageTest.setLimitsSameSleep` |
| `org.dyn4j.dynamics.joint.WheelJointTest#setLimitsDifferentSleep` | `UpstreamWheelJointModesCoverageTest.setLimitsDifferentSleep` |
| `org.dyn4j.dynamics.joint.WheelJointTest#setLowerLimitSleep` | `UpstreamWheelJointModesCoverageTest.setLowerLimitSleep` |
| `org.dyn4j.dynamics.joint.WheelJointTest#setUpperLimitSleep` | `UpstreamWheelJointModesCoverageTest.setUpperLimitSleep` |
| `org.dyn4j.dynamics.joint.WheelJointTest#setLimitsEnabledSameSleep` | `UpstreamWheelJointModesCoverageTest.setLimitsEnabledSameSleep` |
| `org.dyn4j.dynamics.joint.WheelJointTest#setLimitsEnabledDifferentSleep` | `UpstreamWheelJointModesCoverageTest.setLimitsEnabledDifferentSleep` |
| `org.dyn4j.dynamics.joint.WheelJointTest#shift` | `UpstreamWheelJointModesCoverageTest.shift` |
| `org.dyn4j.dynamics.joint.WheelJointTest#copy` | `UpstreamJointModesCopyAndCoefficientsTest.wheelCopy` |
| `org.dyn4j.dynamics.joint.WheelJointTest#copyFailed` | `UpstreamWheelJointModesCoverageTest.copyFailed` |
