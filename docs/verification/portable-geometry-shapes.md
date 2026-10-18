# Portable geometry shape coverage

This report covers the 19 assigned dyn4j 6.0.0 geometry test classes. The pinned source has 270 `@Test` identities. Common Kotlin executes 264 named counterparts on six host lanes. The unchanged Java suites execute all 270 identities against both the baseline binary and the candidate JVM artifact. Six null-signature identities are JVM-only; additional JVM-only assertions within portable methods are listed below.

## Revisions and hashes

- Worker model: `gpt-6-sol`, verified in this session's `turn_context`.
- Pinned upstream source revision: `058bf6d982a0fb89b54050f929f6ea9dae53b714`.
- Merged local integration head: `dc536f6237f5150869764856ce7ac33658ddcadc`.
- Verified merge candidate: `b860e9f3c7e00ab8aaa762fdb57be94109d37464`.
- Baseline binary `org.dyn4j:dyn4j:6.0.0` SHA-256: `204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e`.
- Candidate JVM JAR `dyn4k-core-jvm-0.1.0-alpha.1.jar` SHA-256: `7a1a1352c56e6c4488b958536f72f55c84546b1bf7fd6976886e264d64f6877a`.
- JUnit 4.13.1 JAR SHA-256: `c30719db974d6452793fe191b3638a5777005485bae145924044530ffa5f6122`.
- Pinned original test source manifest SHA-256: `c240d00f441384053201401dbdc0f9de3e0f366e1bff8e49dc51dce4bcb6ce2a`.
- Common Kotlin test source manifest SHA-256: `2f0084f3f8b10943be1732c044654ace912e10327c1729a00697a514781ee893`.

The manifest algorithm sorts relative paths, writes one `path SHA-256` line for each file with a final newline, then SHA-256 hashes that UTF-8 text. The original manifest includes the 19 Java files under the pinned upstream root. The common manifest includes all 22 `.kt` files in the assigned subtree, including the three portable helpers. Each test file retains its upstream BSD notice.

The verified host ran Linux `7.2.9-ogc3.1.fc44.x86_64` on x86_64, OpenJDK `25.0.3`, and Node `v26.10.0`. The Android lane is a host JVM test.

## Execution

| Surface | Expected | Executed | Failures | Errors | Skips |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline JVM, unchanged selected Java suites | 270 | 270 | 0 | 0 | 0 |
| Candidate JVM, unchanged selected Java suites | 270 | 270 | 0 | 0 | 0 |
| Common jvmTest | 264 | 264 | 0 | 0 | 0 |
| Common linuxX64Test | 264 | 264 | 0 | 0 | 0 |
| Common jsNodeTest | 264 | 264 | 0 | 0 | 0 |
| Common wasmJsNodeTest | 264 | 264 | 0 | 0 | 0 |
| Common wasmWasiNodeTest | 264 | 264 | 0 | 0 | 0 |
| Common testAndroidHostTest | 264 | 264 | 0 | 0 | 0 |

The common suite was run at the verified merge candidate with `ANDROID_HOME=/home/stewart/Android/Sdk ./gradlew --rerun-tasks :dyn4k-core:jvmTest :dyn4k-core:linuxX64Test :dyn4k-core:jsNodeTest :dyn4k-core:wasmJsNodeTest :dyn4k-core:wasmWasiNodeTest :dyn4k-core:testAndroidHostTest --console=plain`. Each lane wrote 19 JUnit XML suites. The candidate Java run used `:dyn4k-core:runUpstreamGeometryTests --args` with exactly the 19 classes below and returned `OK (270 tests)`. The baseline run used the same compiled unchanged Java source classes with the pinned baseline binary, JUnit, and Hamcrest, and also returned `OK (270 tests)`. No source class has `@Ignore` or a parameterized runner.

The raw XML evidence from this merge candidate contains 114 files under `dyn4k-core/build/test-results/<lane>/TEST-*.xml`. A copy of those six result directories is `/tmp/dyn4k-shapes-sync-merge-xml.tar`, SHA-256 `71488837c5a281d0b7ef3347077e6dbc29482aef5b2f40128ff51f321522e05f`. For each lane, the SHA-256 below covers sorted `path SHA-256` lines with a final newline; the same algorithm over all 114 XML files gives `2bf41eb17738f2eee4dbbf3f9efdd6b5e0a6eed2815ba6d2ff5fef3e6a3181d9`.

| Common lane | XML suites | Raw XML manifest SHA-256 |
| --- | ---: | --- |
| `jvmTest` | 19 | `8fe7bcf2b7fcf51afc2d9db54175599592507251f71e7b0174b0783e3e23a1c0` |
| `linuxX64Test` | 19 | `301c7d058cfff45e5a6a37ab38e814f1a22d642c7b9880113bf44b9cc8aece35` |
| `jsNodeTest` | 19 | `2297c595c43d2c54edf46dfa1b31d3444246fbe572702e31d4d6b717b0e24013` |
| `wasmJsNodeTest` | 19 | `154399133abfe40ceaecab11d2424ed5bb01b107b9220681217e5e2573660861` |
| `wasmWasiNodeTest` | 19 | `75ebbc4b004fceb9d334249523fdeb926ee94aa0c351c9edbcf1e054562f7c3a` |
| `testAndroidHostTest` | 19 | `d9b83dce7c017848f78d46497bc51b8e4f4091e564baf1a15e3324aa95104e56` |

Both `RobustGeometryTest` randomized identities also assert that every predicate result is finite before comparing its sign with the independent exact oracle. Their original seed, generated inputs, and loop counts are unchanged. The frozen qualification manifest still expects zero cases in each `core-*` group. Qualification integration must update those expectations before its probes can accept these common test reports; this shape slice does not change the manifest or verifier.

## Exact source and counterpart files

| Class | Original tests | Common tests | Original Java SHA-256 | Common Kotlin SHA-256 |
| --- | ---: | ---: | --- | --- |
| [AABBTest](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/geometry/AABBTest.java) / [port](../../dyn4k-core/src/commonTest/kotlin/org/dyn4j/coverage/geometry/shapes/AABBTest.kt) | 26 | 26 | `8aec2c2e0e0d4056a8f9465a1311200512f37773f8aeaad539aeaf8308b24477` | `2815dde7207130c3907b6faeff0061528a3a002ff46df824b8bf14bdc23e07fc` |
| [AbstractShapeTest](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/geometry/AbstractShapeTest.java) / [port](../../dyn4k-core/src/commonTest/kotlin/org/dyn4j/coverage/geometry/shapes/AbstractShapeTest.kt) | 2 | 2 | `31cfdbcec0acc8e1350f8bbc04fd052b1237ee91996115fe92c7bebe12aa9f9a` | `4162342224352d0443b5b11e3925daea233f7624e320147169f2c31e0775a05a` |
| [IntervalTest](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/geometry/IntervalTest.java) / [port](../../dyn4k-core/src/commonTest/kotlin/org/dyn4j/coverage/geometry/shapes/IntervalTest.kt) | 19 | 19 | `9e881da60eb61cd770216ea01a2ef5e55a238aa164c01704a529f28ff22b63ee` | `8f6f33e936cfb6d5b4e0652d0b0ea7cbacd4a304230abfc2cddceb731ccc1533` |
| [RayTest](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/geometry/RayTest.java) / [port](../../dyn4k-core/src/commonTest/kotlin/org/dyn4j/coverage/geometry/shapes/RayTest.kt) | 10 | 10 | `c576ef958dbba4912510e396633d15bb52cbf88be372402870197f1975640c72` | `695e2670033fd1a962b9b0e30b19c19c9250a358d6639c30f53e0db3fcb15b9f` |
| [CircleTest](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/geometry/CircleTest.java) / [port](../../dyn4k-core/src/commonTest/kotlin/org/dyn4j/coverage/geometry/shapes/CircleTest.kt) | 15 | 15 | `7d68f1a74e32d766f1ca57384fe279b52178b416e0571cd51553e80b8fe191c8` | `055fb64b6fdedc75803b80049eb69615a28eacee8242fb520f55a8d62146cd73` |
| [FeatureTest](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/geometry/FeatureTest.java) / [port](../../dyn4k-core/src/commonTest/kotlin/org/dyn4j/coverage/geometry/shapes/FeatureTest.kt) | 3 | 3 | `a9539c4e37cfdee69b6d9fa1ca8370f38c23c298c39c108645ffc6e61729b248` | `6ce74121d6820848291c93c46ade48c98f6d8b22c853ed67039048474358defd` |
| [PolygonTest](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/geometry/PolygonTest.java) / [port](../../dyn4k-core/src/commonTest/kotlin/org/dyn4j/coverage/geometry/shapes/PolygonTest.kt) | 25 | 24 | `e8d2726d1910df6442c1c994fe5be4bac8fad3c92c2c41743f2b43490cb7bd81` | `b1fe078be1d8d694008a418c06201906613e2845c73085f7c7aa741f72c1f569` |
| [RectangleTest](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/geometry/RectangleTest.java) / [port](../../dyn4k-core/src/commonTest/kotlin/org/dyn4j/coverage/geometry/shapes/RectangleTest.kt) | 11 | 11 | `de9e8bd489887245327b48596e6db48d15fa088c9e1a6ce725cbf4729da089bd` | `7800cbde0d1e6ff4fb24ca0a37d7dced60cd91261a6587cc05a6e935e163a077` |
| [MassTest](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/geometry/MassTest.java) / [port](../../dyn4k-core/src/commonTest/kotlin/org/dyn4j/coverage/geometry/shapes/MassTest.kt) | 22 | 22 | `d0e7c6e97615ade72134c94d7148fc21db5713fc82be2ff56ca5339c96906584` | `c83394d420952189f145183ce15139566ee70caca87cb601148206b41171c7cd` |
| [TriangleTest](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/geometry/TriangleTest.java) / [port](../../dyn4k-core/src/commonTest/kotlin/org/dyn4j/coverage/geometry/shapes/TriangleTest.kt) | 6 | 3 | `d4e53f4ce6cd60c69b326106da9e035aab0ffaa0cd1686015739a45be660a0e3` | `d7b1048ce86496de0aa31e6900b1178232cafbe6160daa22b3f65a7b3143791f` |
| [SegmentTest](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/geometry/SegmentTest.java) / [port](../../dyn4k-core/src/commonTest/kotlin/org/dyn4j/coverage/geometry/shapes/SegmentTest.kt) | 22 | 22 | `b4dcfe6a9ad70ae7f2559d5ba87bfe7833a588b41761e8bed8c51131c3a3683f` | `5177f1b7d9e61bb8c1d922650ff8eb6dd75456f2dc4e7660f44b392d459adf20` |
| [WoundTest](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/geometry/WoundTest.java) / [port](../../dyn4k-core/src/commonTest/kotlin/org/dyn4j/coverage/geometry/shapes/WoundTest.kt) | 6 | 6 | `d65c4d91a4c93b673bd3ae75c7505c69898a6a39b5b44d458a28b7897db1033b` | `1381b22a05bc0dce04956ac1551f6e259574d8bc195cf736a056cfb5eac570b1` |
| [LinkTest](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/geometry/LinkTest.java) / [port](../../dyn4k-core/src/commonTest/kotlin/org/dyn4j/coverage/geometry/shapes/LinkTest.kt) | 8 | 6 | `e27ba5dd0108b4e450c54d06d33cfab2151654e54ffa63e63c2b236829be4b66` | `bf734319e674f54e2694928bc1e5ff5c1733b101a05b3fc54f722b2d2a633c64` |
| [AdaptiveDecimalTest](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/geometry/AdaptiveDecimalTest.java) / [port](../../dyn4k-core/src/commonTest/kotlin/org/dyn4j/coverage/geometry/shapes/AdaptiveDecimalTest.kt) | 17 | 17 | `ac9de6189f638e1cf4804800028d3b718370122cf4ca9fe76299fd2d9ed986c0` | `cceabf63529b25263193d468b8e507e6897df3f958b3a3c277187f4e3a6e037c` |
| [RobustGeometryTest](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/geometry/RobustGeometryTest.java) / [port](../../dyn4k-core/src/commonTest/kotlin/org/dyn4j/coverage/geometry/shapes/RobustGeometryTest.kt) | 2 | 2 | `f6c4575b9802b26f236d805f28c467ee456aee9a2eec67e365d0fcd585870d81` | `b77428637137977d77b7fc24a40c4d2c4e486b0bc7e00496e3f003d4f2336bec` |
| [CapsuleTest](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/geometry/CapsuleTest.java) / [port](../../dyn4k-core/src/commonTest/kotlin/org/dyn4j/coverage/geometry/shapes/CapsuleTest.kt) | 20 | 20 | `e1db15d06971eefac817ac8cec0584d1ba6785617337ea944fcd307ecafedc95` | `32b2b347fce6989683ae9c716dac52dd70e467c39ac5f215487234200ac8b952` |
| [EllipseTest](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/geometry/EllipseTest.java) / [port](../../dyn4k-core/src/commonTest/kotlin/org/dyn4j/coverage/geometry/shapes/EllipseTest.kt) | 19 | 19 | `810bd4c46971a798125a363957fb1b890b67cf6bf2cac0118a1fce96155c8c58` | `2318e3c1e9e9a1fb237d3645f81e245ebf50ece83c9d520f3f70e8374a4b23b0` |
| [HalfEllipseTest](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/geometry/HalfEllipseTest.java) / [port](../../dyn4k-core/src/commonTest/kotlin/org/dyn4j/coverage/geometry/shapes/HalfEllipseTest.kt) | 18 | 18 | `5c86e62fbebeb47cba654bfe3d69fb6f1937bb6139c6014ce4831fc60263eb2e` | `83c24330046962409603bc6c78ad0005ae709c7ccfc4c829c580d0db36a6429d` |
| [SliceTest](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/geometry/SliceTest.java) / [port](../../dyn4k-core/src/commonTest/kotlin/org/dyn4j/coverage/geometry/shapes/SliceTest.kt) | 19 | 19 | `692c33521af1fe50861023dc3d4e331bb483be45b06f18982d875570a516e5b6` | `8587d88e3f4484b7bec7018f5b7a07ab996484eb2b97f017ccd8942a930e8f3c` |

## JVM-only identities

These six original methods run unchanged on baseline and candidate JVM. They cannot use their original null argument in common Kotlin because that call does not type-check. The related portable error behavior remains checked by other tests where the Kotlin API accepts nullable inputs.

| Original identity | Reason and portable related check |
| --- | --- |
| `PolygonTest.createNullPoints` | Java passes a null vararg array. Kotlin common cannot supply a null array to the nonnull vararg carrier; `PolygonTest.createNullPoint` still checks a null element portably. |
| `TriangleTest.createNullPoint1` | Java passes null to the first nonnull Kotlin `Vector2` constructor parameter. |
| `TriangleTest.createNullPoint2` | Java passes null to the second nonnull Kotlin `Vector2` constructor parameter. |
| `TriangleTest.createNullPoint3` | Java passes null to the third nonnull Kotlin `Vector2` constructor parameter. |
| `LinkTest.createNullPoint1` | Java passes null to the first nonnull segment endpoint parameter. |
| `LinkTest.createNullPoint2` | Java passes null to the second nonnull segment endpoint parameter. |

Several portable copy methods use public geometry queries to compare values and mutation independence. The unchanged Java methods retain additional direct storage checks: `CapsuleTest.copy` checks `foci` and `localXAxis` identity; `EllipseTest.copy` checks `rotation` identity; `HalfEllipseTest.copy` checks endpoint and `rotation` identity; `SliceTest.copy` checks `vertices`, `normals`, and `rotation` identity. `MassTest.setType` checks the raw fields while common Kotlin checks the public type behavior. `AbstractShapeTest.setUserData` uses a null center in Java; its common counterpart uses a valid center and exercises the same user-data identity behavior. These raw field and null-center assertions are JVM-only portions of their listed identities. The common tests do not qualify Java package storage on other targets.

## Identity mapping

Every row is one original `@Test` identity. A portable row names the executing Kotlin method. A JVM-only row names the unchanged original Java method exercised on both JVM artifacts.

| Original identity | Disposition | Executing method |
| --- | --- | --- |
| `AABBTest.createSuccess` | Portable | `AABBTest.createSuccess` (common Kotlin) |
| `AABBTest.createRadius` | Portable | `AABBTest.createRadius` (common Kotlin) |
| `AABBTest.createRadiusNegative` | Portable | `AABBTest.createRadiusNegative` (common Kotlin) |
| `AABBTest.createCopy` | Portable | `AABBTest.createCopy` (common Kotlin) |
| `AABBTest.createFailure1` | Portable | `AABBTest.createFailure1` (common Kotlin) |
| `AABBTest.createFailure2` | Portable | `AABBTest.createFailure2` (common Kotlin) |
| `AABBTest.perimeter` | Portable | `AABBTest.perimeter` (common Kotlin) |
| `AABBTest.area` | Portable | `AABBTest.area` (common Kotlin) |
| `AABBTest.union` | Portable | `AABBTest.union` (common Kotlin) |
| `AABBTest.expand` | Portable | `AABBTest.expand` (common Kotlin) |
| `AABBTest.overlaps` | Portable | `AABBTest.overlaps` (common Kotlin) |
| `AABBTest.contains` | Portable | `AABBTest.contains` (common Kotlin) |
| `AABBTest.getWidth` | Portable | `AABBTest.getWidth` (common Kotlin) |
| `AABBTest.getHeight` | Portable | `AABBTest.getHeight` (common Kotlin) |
| `AABBTest.translate` | Portable | `AABBTest.translate` (common Kotlin) |
| `AABBTest.containsPoint` | Portable | `AABBTest.containsPoint` (common Kotlin) |
| `AABBTest.intersection` | Portable | `AABBTest.intersection` (common Kotlin) |
| `AABBTest.degenerate` | Portable | `AABBTest.degenerate` (common Kotlin) |
| `AABBTest.testEquals` | Portable | `AABBTest.testEquals` (common Kotlin) |
| `AABBTest.testHashcode` | Portable | `AABBTest.testHashcode` (common Kotlin) |
| `AABBTest.testToString` | Portable | `AABBTest.testToString` (common Kotlin) |
| `AABBTest.createFromPoints` | Portable | `AABBTest.createFromPoints` (common Kotlin) |
| `AABBTest.setFromPoints` | Portable | `AABBTest.setFromPoints` (common Kotlin) |
| `AABBTest.copy` | Portable | `AABBTest.copy` (common Kotlin) |
| `AABBTest.getCenter` | Portable | `AABBTest.getCenter` (common Kotlin) |
| `AABBTest.zero` | Portable | `AABBTest.zero` (common Kotlin) |
| `AbstractShapeTest.create` | Portable | `AbstractShapeTest.create` (common Kotlin) |
| `AbstractShapeTest.setUserData` | Portable user-data behavior; JVM-only null-center setup | `AbstractShapeTest.setUserData` (common Kotlin and unchanged Java) |
| `IntervalTest.createMinGreaterThanMax` | Portable | `IntervalTest.createMinGreaterThanMax` (common Kotlin) |
| `IntervalTest.create` | Portable | `IntervalTest.create` (common Kotlin) |
| `IntervalTest.createCopy` | Portable | `IntervalTest.createCopy` (common Kotlin) |
| `IntervalTest.setInvalidMax` | Portable | `IntervalTest.setInvalidMax` (common Kotlin) |
| `IntervalTest.setMax` | Portable | `IntervalTest.setMax` (common Kotlin) |
| `IntervalTest.setInvalidMin` | Portable | `IntervalTest.setInvalidMin` (common Kotlin) |
| `IntervalTest.setMin` | Portable | `IntervalTest.setMin` (common Kotlin) |
| `IntervalTest.includes` | Portable | `IntervalTest.includes` (common Kotlin) |
| `IntervalTest.overlaps` | Portable | `IntervalTest.overlaps` (common Kotlin) |
| `IntervalTest.contains` | Portable | `IntervalTest.contains` (common Kotlin) |
| `IntervalTest.clamp` | Portable | `IntervalTest.clamp` (common Kotlin) |
| `IntervalTest.degenerate` | Portable | `IntervalTest.degenerate` (common Kotlin) |
| `IntervalTest.union` | Portable | `IntervalTest.union` (common Kotlin) |
| `IntervalTest.intersection` | Portable | `IntervalTest.intersection` (common Kotlin) |
| `IntervalTest.distance` | Portable | `IntervalTest.distance` (common Kotlin) |
| `IntervalTest.expand` | Portable | `IntervalTest.expand` (common Kotlin) |
| `IntervalTest.getLength` | Portable | `IntervalTest.getLength` (common Kotlin) |
| `IntervalTest.copy` | Portable | `IntervalTest.copy` (common Kotlin) |
| `IntervalTest.set` | Portable | `IntervalTest.set` (common Kotlin) |
| `RayTest.createNullStart` | Portable | `RayTest.createNullStart` (common Kotlin) |
| `RayTest.createNullDirection` | Portable | `RayTest.createNullDirection` (common Kotlin) |
| `RayTest.createZeroDirection` | Portable | `RayTest.createZeroDirection` (common Kotlin) |
| `RayTest.create` | Portable | `RayTest.create` (common Kotlin) |
| `RayTest.createFromOrigin` | Portable | `RayTest.createFromOrigin` (common Kotlin) |
| `RayTest.setStartNull` | Portable | `RayTest.setStartNull` (common Kotlin) |
| `RayTest.setDirectionNull` | Portable | `RayTest.setDirectionNull` (common Kotlin) |
| `RayTest.setDirectionZero` | Portable | `RayTest.setDirectionZero` (common Kotlin) |
| `RayTest.setDirection` | Portable | `RayTest.setDirection` (common Kotlin) |
| `RayTest.copy` | Portable | `RayTest.copy` (common Kotlin) |
| `CircleTest.createZeroRadius` | Portable | `CircleTest.createZeroRadius` (common Kotlin) |
| `CircleTest.createNegativeRadius` | Portable | `CircleTest.createNegativeRadius` (common Kotlin) |
| `CircleTest.createSuccess` | Portable | `CircleTest.createSuccess` (common Kotlin) |
| `CircleTest.contains` | Portable | `CircleTest.contains` (common Kotlin) |
| `CircleTest.project` | Portable | `CircleTest.project` (common Kotlin) |
| `CircleTest.getFarthest` | Portable | `CircleTest.getFarthest` (common Kotlin) |
| `CircleTest.getAxes` | Portable | `CircleTest.getAxes` (common Kotlin) |
| `CircleTest.getFoci` | Portable | `CircleTest.getFoci` (common Kotlin) |
| `CircleTest.rotate` | Portable | `CircleTest.rotate` (common Kotlin) |
| `CircleTest.translate` | Portable | `CircleTest.translate` (common Kotlin) |
| `CircleTest.createAABB` | Portable | `CircleTest.createAABB` (common Kotlin) |
| `CircleTest.getRadius` | Portable | `CircleTest.getRadius` (common Kotlin) |
| `CircleTest.createMass` | Portable | `CircleTest.createMass` (common Kotlin) |
| `CircleTest.getArea` | Portable | `CircleTest.getArea` (common Kotlin) |
| `CircleTest.copy` | Portable | `CircleTest.copy` (common Kotlin) |
| `FeatureTest.create` | Portable | `FeatureTest.create` (common Kotlin) |
| `FeatureTest.createNonIndexed` | Portable | `FeatureTest.createNonIndexed` (common Kotlin) |
| `FeatureTest.copy` | Portable | `FeatureTest.copy` (common Kotlin) |
| `PolygonTest.createNotEnoughPoints` | Portable | `PolygonTest.createNotEnoughPoints` (common Kotlin) |
| `PolygonTest.createNotCCW` | Portable | `PolygonTest.createNotCCW` (common Kotlin) |
| `PolygonTest.createCCW` | Portable | `PolygonTest.createCCW` (common Kotlin) |
| `PolygonTest.createCoincident` | Portable | `PolygonTest.createCoincident` (common Kotlin) |
| `PolygonTest.createNonConvex` | Portable | `PolygonTest.createNonConvex` (common Kotlin) |
| `PolygonTest.createDegenerate` | Portable | `PolygonTest.createDegenerate` (common Kotlin) |
| `PolygonTest.createNullPoints` | JVM-only | `PolygonTest.createNullPoints` (unchanged Java) |
| `PolygonTest.createNullPoint` | Portable | `PolygonTest.createNullPoint` (common Kotlin) |
| `PolygonTest.createSuccess` | Portable | `PolygonTest.createSuccess` (common Kotlin) |
| `PolygonTest.contains` | Portable | `PolygonTest.contains` (common Kotlin) |
| `PolygonTest.project` | Portable | `PolygonTest.project` (common Kotlin) |
| `PolygonTest.getFarthest` | Portable | `PolygonTest.getFarthest` (common Kotlin) |
| `PolygonTest.getAxes` | Portable | `PolygonTest.getAxes` (common Kotlin) |
| `PolygonTest.getFoci` | Portable | `PolygonTest.getFoci` (common Kotlin) |
| `PolygonTest.rotate` | Portable | `PolygonTest.rotate` (common Kotlin) |
| `PolygonTest.translate` | Portable | `PolygonTest.translate` (common Kotlin) |
| `PolygonTest.createAABB` | Portable | `PolygonTest.createAABB` (common Kotlin) |
| `PolygonTest.containsPointCoIncidentStart` | Portable | `PolygonTest.containsPointCoIncidentStart` (common Kotlin) |
| `PolygonTest.containsPointCoIncidentMid` | Portable | `PolygonTest.containsPointCoIncidentMid` (common Kotlin) |
| `PolygonTest.containsPointCoIncidentWithCoincidentEdges` | Portable | `PolygonTest.containsPointCoIncidentWithCoincidentEdges` (common Kotlin) |
| `PolygonTest.containsPointCoIncidentWithCoincidentEdges2` | Portable | `PolygonTest.containsPointCoIncidentWithCoincidentEdges2` (common Kotlin) |
| `PolygonTest.getNormals` | Portable | `PolygonTest.getNormals` (common Kotlin) |
| `PolygonTest.createMass` | Portable | `PolygonTest.createMass` (common Kotlin) |
| `PolygonTest.getArea` | Portable | `PolygonTest.getArea` (common Kotlin) |
| `PolygonTest.copy` | Portable | `PolygonTest.copy` (common Kotlin) |
| `RectangleTest.createInvalidWidth` | Portable | `RectangleTest.createInvalidWidth` (common Kotlin) |
| `RectangleTest.createInvalidHeight` | Portable | `RectangleTest.createInvalidHeight` (common Kotlin) |
| `RectangleTest.createSuccess` | Portable | `RectangleTest.createSuccess` (common Kotlin) |
| `RectangleTest.getAxes` | Portable | `RectangleTest.getAxes` (common Kotlin) |
| `RectangleTest.contains` | Portable | `RectangleTest.contains` (common Kotlin) |
| `RectangleTest.project` | Portable | `RectangleTest.project` (common Kotlin) |
| `RectangleTest.getRotation` | Portable | `RectangleTest.getRotation` (common Kotlin) |
| `RectangleTest.createMass` | Portable | `RectangleTest.createMass` (common Kotlin) |
| `RectangleTest.getArea` | Portable | `RectangleTest.getArea` (common Kotlin) |
| `RectangleTest.computeAABB` | Portable | `RectangleTest.computeAABB` (common Kotlin) |
| `RectangleTest.copy` | Portable | `RectangleTest.copy` (common Kotlin) |
| `MassTest.createNegativeMass` | Portable | `MassTest.createNegativeMass` (common Kotlin) |
| `MassTest.createNegativeInertia` | Portable | `MassTest.createNegativeInertia` (common Kotlin) |
| `MassTest.createNullCenter` | Portable | `MassTest.createNullCenter` (common Kotlin) |
| `MassTest.createSuccess` | Portable | `MassTest.createSuccess` (common Kotlin) |
| `MassTest.createInfinite` | Portable | `MassTest.createInfinite` (common Kotlin) |
| `MassTest.createFixedLinearVelocity` | Portable | `MassTest.createFixedLinearVelocity` (common Kotlin) |
| `MassTest.createFixedAngularVelocity` | Portable | `MassTest.createFixedAngularVelocity` (common Kotlin) |
| `MassTest.createCopyNull` | Portable | `MassTest.createCopyNull` (common Kotlin) |
| `MassTest.createCopy` | Portable | `MassTest.createCopy` (common Kotlin) |
| `MassTest.createList` | Portable | `MassTest.createList` (common Kotlin) |
| `MassTest.createListInfinite` | Portable | `MassTest.createListInfinite` (common Kotlin) |
| `MassTest.createListOneElement` | Portable | `MassTest.createListOneElement` (common Kotlin) |
| `MassTest.createListNull` | Portable | `MassTest.createListNull` (common Kotlin) |
| `MassTest.createListEmpty` | Portable | `MassTest.createListEmpty` (common Kotlin) |
| `MassTest.createListOneNullElement` | Portable | `MassTest.createListOneNullElement` (common Kotlin) |
| `MassTest.createListNullElement` | Portable | `MassTest.createListNullElement` (common Kotlin) |
| `MassTest.setType` | Portable public behavior; JVM-only raw-field checks | `MassTest.setType` (common Kotlin and unchanged Java) |
| `MassTest.setNullType` | Portable | `MassTest.setNullType` (common Kotlin) |
| `MassTest.setTypeIgnored` | Portable | `MassTest.setTypeIgnored` (common Kotlin) |
| `MassTest.polygonInertiaAndCOM` | Portable | `MassTest.polygonInertiaAndCOM` (common Kotlin) |
| `MassTest.polygonInertiaAndMass` | Portable | `MassTest.polygonInertiaAndMass` (common Kotlin) |
| `MassTest.equals` | Portable | `MassTest.equals` (common Kotlin) |
| `TriangleTest.createNullPoint1` | JVM-only | `TriangleTest.createNullPoint1` (unchanged Java) |
| `TriangleTest.createNullPoint2` | JVM-only | `TriangleTest.createNullPoint2` (unchanged Java) |
| `TriangleTest.createNullPoint3` | JVM-only | `TriangleTest.createNullPoint3` (unchanged Java) |
| `TriangleTest.tostring` | Portable | `TriangleTest.tostring` (common Kotlin) |
| `TriangleTest.contains` | Portable | `TriangleTest.contains` (common Kotlin) |
| `TriangleTest.copy` | Portable | `TriangleTest.copy` (common Kotlin) |
| `SegmentTest.createNullPoint1` | Portable | `SegmentTest.createNullPoint1` (common Kotlin) |
| `SegmentTest.createNullPoint2` | Portable | `SegmentTest.createNullPoint2` (common Kotlin) |
| `SegmentTest.createCoincident` | Portable | `SegmentTest.createCoincident` (common Kotlin) |
| `SegmentTest.creatSuccess` | Portable | `SegmentTest.creatSuccess` (common Kotlin) |
| `SegmentTest.getLength` | Portable | `SegmentTest.getLength` (common Kotlin) |
| `SegmentTest.getLocation` | Portable | `SegmentTest.getLocation` (common Kotlin) |
| `SegmentTest.getPointClosest` | Portable | `SegmentTest.getPointClosest` (common Kotlin) |
| `SegmentTest.getAxes` | Portable | `SegmentTest.getAxes` (common Kotlin) |
| `SegmentTest.getFoci` | Portable | `SegmentTest.getFoci` (common Kotlin) |
| `SegmentTest.contains` | Portable | `SegmentTest.contains` (common Kotlin) |
| `SegmentTest.containsRadius` | Portable | `SegmentTest.containsRadius` (common Kotlin) |
| `SegmentTest.project` | Portable | `SegmentTest.project` (common Kotlin) |
| `SegmentTest.getFarthest` | Portable | `SegmentTest.getFarthest` (common Kotlin) |
| `SegmentTest.rotate` | Portable | `SegmentTest.rotate` (common Kotlin) |
| `SegmentTest.translate` | Portable | `SegmentTest.translate` (common Kotlin) |
| `SegmentTest.createAABB` | Portable | `SegmentTest.createAABB` (common Kotlin) |
| `SegmentTest.getLineIntersection` | Portable | `SegmentTest.getLineIntersection` (common Kotlin) |
| `SegmentTest.getSegmentIntersection` | Portable | `SegmentTest.getSegmentIntersection` (common Kotlin) |
| `SegmentTest.createMass` | Portable | `SegmentTest.createMass` (common Kotlin) |
| `SegmentTest.getArea` | Portable | `SegmentTest.getArea` (common Kotlin) |
| `SegmentTest.getNormals` | Portable | `SegmentTest.getNormals` (common Kotlin) |
| `SegmentTest.copy` | Portable | `SegmentTest.copy` (common Kotlin) |
| `WoundTest.getRadius` | Portable | `WoundTest.getRadius` (common Kotlin) |
| `WoundTest.getRadiusCenter` | Portable | `WoundTest.getRadiusCenter` (common Kotlin) |
| `WoundTest.woundIteratorStartIndex` | Portable | `WoundTest.woundIteratorStartIndex` (common Kotlin) |
| `WoundTest.woundIteratorCount` | Portable | `WoundTest.woundIteratorCount` (common Kotlin) |
| `WoundTest.woundIteratorFail` | Portable | `WoundTest.woundIteratorFail` (common Kotlin) |
| `WoundTest.woundIteratorRemove` | Portable | `WoundTest.woundIteratorRemove` (common Kotlin) |
| `LinkTest.createNullPoint1` | JVM-only | `LinkTest.createNullPoint1` (unchanged Java) |
| `LinkTest.createNullPoint2` | JVM-only | `LinkTest.createNullPoint2` (unchanged Java) |
| `LinkTest.createCoincident` | Portable | `LinkTest.createCoincident` (common Kotlin) |
| `LinkTest.creatSuccess` | Portable | `LinkTest.creatSuccess` (common Kotlin) |
| `LinkTest.rotate` | Portable | `LinkTest.rotate` (common Kotlin) |
| `LinkTest.translate` | Portable | `LinkTest.translate` (common Kotlin) |
| `LinkTest.copy` | Portable | `LinkTest.copy` (common Kotlin) |
| `LinkTest.copyNonLoop` | Portable | `LinkTest.copyNonLoop` (common Kotlin) |
| `AdaptiveDecimalTest.create` | Portable | `AdaptiveDecimalTest.create` (common Kotlin) |
| `AdaptiveDecimalTest.size` | Portable | `AdaptiveDecimalTest.size` (common Kotlin) |
| `AdaptiveDecimalTest.append` | Portable | `AdaptiveDecimalTest.append` (common Kotlin) |
| `AdaptiveDecimalTest.copy` | Portable | `AdaptiveDecimalTest.copy` (common Kotlin) |
| `AdaptiveDecimalTest.clear` | Portable | `AdaptiveDecimalTest.clear` (common Kotlin) |
| `AdaptiveDecimalTest.removeZeros` | Portable | `AdaptiveDecimalTest.removeZeros` (common Kotlin) |
| `AdaptiveDecimalTest.negate` | Portable | `AdaptiveDecimalTest.negate` (common Kotlin) |
| `AdaptiveDecimalTest.getEstimation` | Portable | `AdaptiveDecimalTest.getEstimation` (common Kotlin) |
| `AdaptiveDecimalTest.normalize` | Portable | `AdaptiveDecimalTest.normalize` (common Kotlin) |
| `AdaptiveDecimalTest.sum` | Portable | `AdaptiveDecimalTest.sum` (common Kotlin) |
| `AdaptiveDecimalTest.checkInvariants` | Portable | `AdaptiveDecimalTest.checkInvariants` (common Kotlin) |
| `AdaptiveDecimalTest.testIndex1` | Portable | `AdaptiveDecimalTest.testIndex1` (common Kotlin) |
| `AdaptiveDecimalTest.testIndex2` | Portable | `AdaptiveDecimalTest.testIndex2` (common Kotlin) |
| `AdaptiveDecimalTest.testIndex3` | Portable | `AdaptiveDecimalTest.testIndex3` (common Kotlin) |
| `AdaptiveDecimalTest.testArgument1` | Portable | `AdaptiveDecimalTest.testArgument1` (common Kotlin) |
| `AdaptiveDecimalTest.testArgument2` | Portable | `AdaptiveDecimalTest.testArgument2` (common Kotlin) |
| `AdaptiveDecimalTest.testState` | Portable | `AdaptiveDecimalTest.testState` (common Kotlin) |
| `RobustGeometryTest.randomizedTest` | Portable | `RobustGeometryTest.randomizedTest` (common Kotlin) |
| `RobustGeometryTest.randomizedTest2` | Portable | `RobustGeometryTest.randomizedTest2` (common Kotlin) |
| `CapsuleTest.createZeroWidth` | Portable | `CapsuleTest.createZeroWidth` (common Kotlin) |
| `CapsuleTest.createNegativeWidth` | Portable | `CapsuleTest.createNegativeWidth` (common Kotlin) |
| `CapsuleTest.createZeroHeight` | Portable | `CapsuleTest.createZeroHeight` (common Kotlin) |
| `CapsuleTest.createNegativeHeight` | Portable | `CapsuleTest.createNegativeHeight` (common Kotlin) |
| `CapsuleTest.createCircle` | Portable | `CapsuleTest.createCircle` (common Kotlin) |
| `CapsuleTest.createSuccessHorizontal` | Portable | `CapsuleTest.createSuccessHorizontal` (common Kotlin) |
| `CapsuleTest.createSuccessVertical` | Portable | `CapsuleTest.createSuccessVertical` (common Kotlin) |
| `CapsuleTest.contains` | Portable | `CapsuleTest.contains` (common Kotlin) |
| `CapsuleTest.project` | Portable | `CapsuleTest.project` (common Kotlin) |
| `CapsuleTest.getFarthest` | Portable | `CapsuleTest.getFarthest` (common Kotlin) |
| `CapsuleTest.getAxes` | Portable | `CapsuleTest.getAxes` (common Kotlin) |
| `CapsuleTest.getFoci` | Portable | `CapsuleTest.getFoci` (common Kotlin) |
| `CapsuleTest.rotate` | Portable | `CapsuleTest.rotate` (common Kotlin) |
| `CapsuleTest.translate` | Portable | `CapsuleTest.translate` (common Kotlin) |
| `CapsuleTest.createAABB` | Portable | `CapsuleTest.createAABB` (common Kotlin) |
| `CapsuleTest.createMass` | Portable | `CapsuleTest.createMass` (common Kotlin) |
| `CapsuleTest.getArea` | Portable | `CapsuleTest.getArea` (common Kotlin) |
| `CapsuleTest.getRadius` | Portable | `CapsuleTest.getRadius` (common Kotlin) |
| `CapsuleTest.getRotation` | Portable | `CapsuleTest.getRotation` (common Kotlin) |
| `CapsuleTest.copy` | Portable copy behavior; JVM-only internal identity | `CapsuleTest.copy` (common Kotlin and unchanged Java) |
| `EllipseTest.createZeroWidth` | Portable | `EllipseTest.createZeroWidth` (common Kotlin) |
| `EllipseTest.createNegativeWidth` | Portable | `EllipseTest.createNegativeWidth` (common Kotlin) |
| `EllipseTest.createZeroHeight` | Portable | `EllipseTest.createZeroHeight` (common Kotlin) |
| `EllipseTest.createNegativeHeight` | Portable | `EllipseTest.createNegativeHeight` (common Kotlin) |
| `EllipseTest.createSuccess` | Portable | `EllipseTest.createSuccess` (common Kotlin) |
| `EllipseTest.contains` | Portable | `EllipseTest.contains` (common Kotlin) |
| `EllipseTest.project` | Portable | `EllipseTest.project` (common Kotlin) |
| `EllipseTest.getFarthest` | Portable | `EllipseTest.getFarthest` (common Kotlin) |
| `EllipseTest.getFarthestPointOnEllipse` | Portable | `EllipseTest.getFarthestPointOnEllipse` (common Kotlin) |
| `EllipseTest.getAxes` | Portable | `EllipseTest.getAxes` (common Kotlin) |
| `EllipseTest.getFoci` | Portable | `EllipseTest.getFoci` (common Kotlin) |
| `EllipseTest.rotate` | Portable | `EllipseTest.rotate` (common Kotlin) |
| `EllipseTest.translate` | Portable | `EllipseTest.translate` (common Kotlin) |
| `EllipseTest.createAABB` | Portable | `EllipseTest.createAABB` (common Kotlin) |
| `EllipseTest.getRadius` | Portable | `EllipseTest.getRadius` (common Kotlin) |
| `EllipseTest.createMass` | Portable | `EllipseTest.createMass` (common Kotlin) |
| `EllipseTest.getArea` | Portable | `EllipseTest.getArea` (common Kotlin) |
| `EllipseTest.getRotation` | Portable | `EllipseTest.getRotation` (common Kotlin) |
| `EllipseTest.copy` | Portable copy behavior; JVM-only internal identity | `EllipseTest.copy` (common Kotlin and unchanged Java) |
| `HalfEllipseTest.createZeroWidth` | Portable | `HalfEllipseTest.createZeroWidth` (common Kotlin) |
| `HalfEllipseTest.createNegativeWidth` | Portable | `HalfEllipseTest.createNegativeWidth` (common Kotlin) |
| `HalfEllipseTest.createZeroHeight` | Portable | `HalfEllipseTest.createZeroHeight` (common Kotlin) |
| `HalfEllipseTest.createNegativeHeight` | Portable | `HalfEllipseTest.createNegativeHeight` (common Kotlin) |
| `HalfEllipseTest.createSuccess` | Portable | `HalfEllipseTest.createSuccess` (common Kotlin) |
| `HalfEllipseTest.contains` | Portable | `HalfEllipseTest.contains` (common Kotlin) |
| `HalfEllipseTest.project` | Portable | `HalfEllipseTest.project` (common Kotlin) |
| `HalfEllipseTest.getFarthest` | Portable | `HalfEllipseTest.getFarthest` (common Kotlin) |
| `HalfEllipseTest.getAxes` | Portable | `HalfEllipseTest.getAxes` (common Kotlin) |
| `HalfEllipseTest.getFoci` | Portable | `HalfEllipseTest.getFoci` (common Kotlin) |
| `HalfEllipseTest.rotate` | Portable | `HalfEllipseTest.rotate` (common Kotlin) |
| `HalfEllipseTest.translate` | Portable | `HalfEllipseTest.translate` (common Kotlin) |
| `HalfEllipseTest.createAABB` | Portable | `HalfEllipseTest.createAABB` (common Kotlin) |
| `HalfEllipseTest.createMass` | Portable | `HalfEllipseTest.createMass` (common Kotlin) |
| `HalfEllipseTest.getArea` | Portable | `HalfEllipseTest.getArea` (common Kotlin) |
| `HalfEllipseTest.getRadius` | Portable | `HalfEllipseTest.getRadius` (common Kotlin) |
| `HalfEllipseTest.getRadiusAboveXAxisBelowEvolute` | Portable | `HalfEllipseTest.getRadiusAboveXAxisBelowEvolute` (common Kotlin) |
| `HalfEllipseTest.copy` | Portable copy behavior; JVM-only internal identity | `HalfEllipseTest.copy` (common Kotlin and unchanged Java) |
| `SliceTest.createZeroRadius` | Portable | `SliceTest.createZeroRadius` (common Kotlin) |
| `SliceTest.createNegativeRadius` | Portable | `SliceTest.createNegativeRadius` (common Kotlin) |
| `SliceTest.createZeroTheta` | Portable | `SliceTest.createZeroTheta` (common Kotlin) |
| `SliceTest.createNegativeTheta` | Portable | `SliceTest.createNegativeTheta` (common Kotlin) |
| `SliceTest.createSuccess` | Portable | `SliceTest.createSuccess` (common Kotlin) |
| `SliceTest.contains` | Portable | `SliceTest.contains` (common Kotlin) |
| `SliceTest.project` | Portable | `SliceTest.project` (common Kotlin) |
| `SliceTest.getFarthest` | Portable | `SliceTest.getFarthest` (common Kotlin) |
| `SliceTest.getAxes` | Portable | `SliceTest.getAxes` (common Kotlin) |
| `SliceTest.getFoci` | Portable | `SliceTest.getFoci` (common Kotlin) |
| `SliceTest.rotate` | Portable | `SliceTest.rotate` (common Kotlin) |
| `SliceTest.translate` | Portable | `SliceTest.translate` (common Kotlin) |
| `SliceTest.createAABB` | Portable | `SliceTest.createAABB` (common Kotlin) |
| `SliceTest.sliceRadius` | Portable | `SliceTest.sliceRadius` (common Kotlin) |
| `SliceTest.createMass` | Portable | `SliceTest.createMass` (common Kotlin) |
| `SliceTest.getArea` | Portable | `SliceTest.getArea` (common Kotlin) |
| `SliceTest.getRadiusAtPoint` | Portable | `SliceTest.getRadiusAtPoint` (common Kotlin) |
| `SliceTest.getRotation` | Portable | `SliceTest.getRotation` (common Kotlin) |
| `SliceTest.copy` | Portable copy behavior; JVM-only internal identity | `SliceTest.copy` (common Kotlin and unchanged Java) |
