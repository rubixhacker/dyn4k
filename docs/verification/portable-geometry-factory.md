# Portable Geometry factory coverage

This report covers the GeometryTest source at dyn4j 6.0.0 revision `058bf6d982a0fb89b54050f929f6ea9dae53b714`. The scope is the 176 original `@Test` identities in `src/test/java/org/dyn4j/geometry/GeometryTest.java`. The port preserves the source notice and the original inputs, assertions, and exception families. `org.dyn4j.geometry.Geometry` is the public seam.

## Result

- 170 of 176 identities execute in common Kotlin on six configured host targets. Six identities pass a null Java array to a vararg method; Kotlin common source cannot make that call. The unchanged Java source executes all 176 on both JVM providers.
- JVM, Linux x64, JS Node, Wasm JS Node, Wasm WASI Node, and Android host: 170 executed, zero failures, zero skips each. `cleanseEmpty` passed on all six after the integrated empty-list identity fix at `c9ab59b0babceb4d9c18f31b93a31ddbf6ab6e9f`.
- A method-by-method audit found 176 unique source identities, 170 common methods, and six justified JVM-only dispositions. The port retains the 458 original assertion call sites and adds ten in `createPolygon` and `createPolygonAtOrigin`: indexed vertex identity and values plus mutation independence. The `Geometry` call counts match upstream. The copied legal notice matches upstream after trailing whitespace normalization.
- These are host runs. Android device execution and other approved targets are outside this slice and remain unpassed.

## Reproduction

- Tested code candidate: `bf004587c9292bee63889e51a6425c7e501d3356` on `codex/port-coverage-geometry-factory`, after merging local `codex/dyn4k-port` at `446b0b122792afe52a17983793d943f0b5959584`. The later report commit changes documentation only.
- Host: Bazzite `44.20261012.0`, Linux `7.2.9-ogc3.1.fc44.x86_64` on `x86_64`. JDK: Eclipse Temurin `21.0.12.1+1-LTS` (Gradle launcher and daemon), Gradle `9.5.0`. Node: `v26.10.0`, V8 `14.6.202.34-node.35`. Android SDK: `/var/home/stewart/Android/Sdk`.
- Pinned baseline: `javac --release 8` compiled the unchanged `GeometryTest.java` against dyn4j 6.0.0, then JUnitCore executed `org.dyn4j.geometry.GeometryTest`: 176 executed, zero failures, zero ignored.
- Candidate JVM: The same compiled Java class ran with only the candidate JVM JAR as the dyn4j provider: 176 executed, zero failures, zero ignored.
- Common tests: `JAVA_HOME=/tmp/dyn4k-tools/jdk21 ANDROID_HOME=/var/home/stewart/Android/Sdk ./gradlew --rerun-tasks :dyn4k-core:jvmTest :dyn4k-core:linuxX64Test :dyn4k-core:jsNodeTest :dyn4k-core:wasmJsNodeTest :dyn4k-core:wasmWasiNodeTest :dyn4k-core:testAndroidHostTest --continue --offline --console=plain --quiet` exited 0. The Android lane is a host test, not a device run.
- Local staged JVM artifact: `JAVA_HOME=/tmp/dyn4k-tools/jdk21 ANDROID_HOME=/var/home/stewart/Android/Sdk ./gradlew --rerun-tasks :dyn4k-core:publishJvmPublicationToStagingRepository --offline --console=plain --quiet` exited 0.
- Red/green proof: a temporary local bad-copy assignment `copied[1] = vertices[1]!!` in `createPolygon` made its indexed identity assertion fail (`expected not same`; targeted XML 1 executed, 1 failure). Removing that assignment made both polygon tests pass (targeted XML 2 executed, 0 failures). The mutation is absent from candidate `bf00458`.
- The local integration history includes the `Geometry.cleanse(List)` empty-list fix at `c9ab59b0babceb4d9c18f31b93a31ddbf6ab6e9f`; `cleanseEmpty` passed in all six raw XML reports.

| Target | Expected | Executed | Failed | Skipped | Failing identity |
| --- | ---: | ---: | ---: | ---: | --- |
| JVM | 170 | 170 | 0 | 0 | none |
| Linux x64 | 170 | 170 | 0 | 0 | none |
| JS Node | 170 | 170 | 0 | 0 | none |
| Wasm JS Node | 170 | 170 | 0 | 0 | none |
| Wasm WASI Node | 170 | 170 | 0 | 0 | none |
| Android host | 170 | 170 | 0 | 0 | none |
| Unchanged Java on baseline JVM | 176 | 176 | 0 | 0 | none |
| Unchanged Java on candidate JVM | 176 | 176 | 0 | 0 | none |

## Source and artifact hashes

| Input or artifact | SHA-256 |
| --- | --- |
| Upstream `GeometryTest.java` | `e135f019fd8fb1396363bba4927e33fce80856141743c14c2db5dac58a9f8c4d` |
| dyn4j 6.0.0 binary JAR | `204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e` |
| Portable Kotlin test source | `8c9e9bb7e14dc123da815edb4a65be1b8951513f6cd7901d810914ae906002f4` |
| Staged `dyn4k-core-jvm-0.1.0-alpha.1.jar` | `7a1a1352c56e6c4488b958536f72f55c84546b1bf7fd6976886e264d64f6877a` |
| Staged JVM sources JAR | `ff910e48cf188936a3fc25d27074b3377f60aa776711e03f678b64946422127a` |

The staged JAR contains production source and binaries; common test source is separately hashed above. The hash values identify the local staged artifact tested here, not a published release.

## Retained raw execution evidence

The raw output bundle is `/tmp/dyn4k-factory-coverage-bf004587.tar.gz` (SHA-256 `c2904987755797a6d724c93147718da463b3e21c95ef033fe2442e52626cc896`). It contains the six copied XML files, Gradle and JUnit logs, the controlled red/green XML, host and toolchain output, exact command summary, and a per-file checksum manifest. Every final XML has 170 distinct expected identities, zero failures, zero errors, zero skips, and passing `cleanseEmpty`, `createPolygon`, and `createPolygonAtOrigin`.

| Target | Raw XML SHA-256 |
| --- | --- |
| JVM | `c728cc319ac69d94c42957527b7a329b67236b425977edc751832fa73dc1263c` |
| Linux x64 | `22bbfd1b06ef40d35136ca199a75b4800f6fa8390aee88e7ece59f6f44f5f726` |
| JS Node | `5d51107a137b85bde3201e3dfe0475147d11a6cb1e22c353fdfe1491f6b7cd6f` |
| Wasm JS Node | `af4ee6901f6525816ef7fba7246c43674d15b9d76a7c9411ee9d2443ddfd3afb` |
| Wasm WASI Node | `e317172fe630c5eba973d3b1773459acdfd1bf958139b81404b123ab8a556847` |
| Android host | `6fe828c75a196b4e0de127812d96f617a66945d2e9559ffc555b33fc1b644523` |

The unchanged Java JUnit logs in that bundle each end with `OK (176 tests)`. The frozen combined `core-*` qualification manifest still expects no factory cases, so its combined probe remains unpassed and is outside this coverage branch.

## JVM-only dispositions

The six cases below require passing a null array reference to a Java vararg parameter. A common Kotlin call can pass zero elements or null elements, but cannot pass a null array reference to that vararg entry point. The unchanged Java test remains the exact compatibility check on both JVM providers. The portable counterpart named below checks the nearest public null-input behavior; it does not replace the exact Java assertion.

| Original identity | Portable semantic equivalent | Reason |
| --- | --- | --- |
| `getAverageCenterNullArray` | `getAverageCenterNullList` | Null Java vararg array is not expressible at the common Kotlin call site. |
| `getAreaWeightedCenterNullArray` | `getAreaWeightedCenterNullList` | Null Java vararg array is not expressible at the common Kotlin call site. |
| `createPolygonNullArray` | `createPolygonNullPoint` | Null Java vararg array is not expressible at the common Kotlin call site. |
| `getWindingNullArray` | `getWindingNullList` | Null Java vararg array is not expressible at the common Kotlin call site. |
| `reverseWindingNullArray` | `reverseWindingNullList` | Null Java vararg array is not expressible at the common Kotlin call site. |
| `cleanseNullArray` | `cleanseNullList` | Null Java vararg array is not expressible at the common Kotlin call site. |

## Identity ledger

The source line is the declaration line in the pinned upstream file. A Kotlin line identifies the executable common test method. `JVM only` means the unchanged Java method is the exact check and the semantic equivalent is listed above.

| Source line | Original identity | Common counterpart | Disposition |
| ---: | --- | --- | --- |
| 50 | `getAverageCenterArray` | `getAverageCenterArray` (line 39) | Portable |
| 78 | `getAverageCenterList` | `getAverageCenterList` (line 57) | Portable |
| 103 | `getAverageCenterNullArray` | — | JVM only |
| 112 | `getAverageCenterEmptyArray` | `getAverageCenterEmptyArray` (line 75) | Portable |
| 121 | `getAverageCenterArrayNullElements` | `getAverageCenterArrayNullElements` (line 83) | Portable |
| 136 | `getAverageCenterArrayNullOnlyElement` | `getAverageCenterArrayNullOnlyElement` (line 97) | Portable |
| 147 | `getAverageCenterNullList` | `getAverageCenterNullList` (line 107) | Portable |
| 156 | `getAverageCenterEmptyList` | `getAverageCenterEmptyList` (line 115) | Portable |
| 165 | `getAverageCenterListNullElements` | `getAverageCenterListNullElements` (line 123) | Portable |
| 180 | `getAverageCenterListNullOnlyElement` | `getAverageCenterListNullOnlyElement` (line 137) | Portable |
| 190 | `getAreaWeightedCenter` | `getAreaWeightedCenter` (line 147) | Portable |
| 219 | `getAreaWeightedCenterOffset` | `getAreaWeightedCenterOffset` (line 165) | Portable |
| 247 | `getAreaWeightedCenterNullArray` | — | JVM only |
| 256 | `getAreaWeightedCenterEmptyArray` | `getAreaWeightedCenterEmptyArray` (line 183) | Portable |
| 265 | `getAreaWeightedCenterArrayNullElements` | `getAreaWeightedCenterArrayNullElements` (line 191) | Portable |
| 280 | `getAreaWeightedCenterNullList` | `getAreaWeightedCenterNullList` (line 205) | Portable |
| 289 | `getAreaWeightedCenterEmptyList` | `getAreaWeightedCenterEmptyList` (line 213) | Portable |
| 298 | `getAreaWeightedCenterListNullElements` | `getAreaWeightedCenterListNullElements` (line 221) | Portable |
| 314 | `getAreaWeightedCenterZeroAreaList` | `getAreaWeightedCenterZeroAreaList` (line 235) | Portable |
| 333 | `getAreaWeightedCenterZeroAreaArray` | `getAreaWeightedCenterZeroAreaArray` (line 248) | Portable |
| 351 | `createUnitCirclePolygon` | `createUnitCirclePolygon` (line 261) | Portable |
| 394 | `createNegativeRadiusUnitCirclePolygon` | `createNegativeRadiusUnitCirclePolygon` (line 292) | Portable |
| 403 | `createZeroRadiusUnitCirclePolygon` | `createZeroRadiusUnitCirclePolygon` (line 300) | Portable |
| 412 | `createLessThan3PointsUnitCirclePolygon` | `createLessThan3PointsUnitCirclePolygon` (line 308) | Portable |
| 420 | `createCircle` | `createCircle` (line 316) | Portable |
| 429 | `createNegativeRadiusCircle` | `createNegativeRadiusCircle` (line 322) | Portable |
| 438 | `createZeroRadiusCircle` | `createZeroRadiusCircle` (line 330) | Portable |
| 446 | `createPolygonNullArray` | — | JVM only |
| 456 | `createPolygonNullPoint` | `createPolygonNullPoint` (line 338) | Portable |
| 466 | `createPolygon` | `createPolygon` (line 347) | Portable |
| 488 | `createPolygonAtOrigin` | `createPolygonAtOrigin` (line 375) | Portable |
| 515 | `createZeroSizeSquare` | `createZeroSizeSquare` (line 412) | Portable |
| 523 | `createNegativeSizeSquare` | `createNegativeSizeSquare` (line 420) | Portable |
| 531 | `createSquare` | `createSquare` (line 428) | Portable |
| 541 | `createRectangle` | `createRectangle` (line 436) | Portable |
| 549 | `createNegativeWidthRectangle` | `createNegativeWidthRectangle` (line 442) | Portable |
| 557 | `createNegativeHeightRectangle` | `createNegativeHeightRectangle` (line 450) | Portable |
| 565 | `createZeroWidthRectangle` | `createZeroWidthRectangle` (line 458) | Portable |
| 573 | `createZeroHeightRectangle` | `createZeroHeightRectangle` (line 466) | Portable |
| 581 | `createTriangleNullPoint` | `createTriangleNullPoint` (line 474) | Portable |
| 592 | `createTriangle` | `createTriangle` (line 484) | Portable |
| 608 | `createTriangleAtOrigin` | `createTriangleAtOrigin` (line 496) | Portable |
| 629 | `createZeroWidthRightTriangle` | `createZeroWidthRightTriangle` (line 511) | Portable |
| 637 | `createZeroHeightRightTriangle` | `createZeroHeightRightTriangle` (line 519) | Portable |
| 645 | `createNegativeWidthRightTriangle` | `createNegativeWidthRightTriangle` (line 527) | Portable |
| 653 | `createNegativeHeightRightTriangle` | `createNegativeHeightRightTriangle` (line 535) | Portable |
| 661 | `createRightTriangle` | `createRightTriangle` (line 543) | Portable |
| 704 | `createRightTriangleMirror` | `createRightTriangleMirror` (line 571) | Portable |
| 747 | `createZeroHeightEquilateralTriangle` | `createZeroHeightEquilateralTriangle` (line 599) | Portable |
| 755 | `createNegativeHeightEquilateralTriangle` | `createNegativeHeightEquilateralTriangle` (line 607) | Portable |
| 763 | `createEquilateralTriangle` | `createEquilateralTriangle` (line 615) | Portable |
| 804 | `createZeroWidthIsoscelesTriangle` | `createZeroWidthIsoscelesTriangle` (line 641) | Portable |
| 812 | `createZeroHeightIsoscelesTriangle` | `createZeroHeightIsoscelesTriangle` (line 649) | Portable |
| 820 | `createNegativeWidthIsoscelesTriangle` | `createNegativeWidthIsoscelesTriangle` (line 657) | Portable |
| 828 | `createNegativeHeightIsoscelesTriangle` | `createNegativeHeightIsoscelesTriangle` (line 665) | Portable |
| 836 | `createIsoscelesTriangle` | `createIsoscelesTriangle` (line 673) | Portable |
| 865 | `createSegmentNullPoint1` | `createSegmentNullPoint1` (line 690) | Portable |
| 874 | `createSegmentNullPoint2` | `createSegmentNullPoint2` (line 698) | Portable |
| 882 | `createSegment` | `createSegment` (line 706) | Portable |
| 890 | `createSegmentAtOrigin` | `createSegmentAtOrigin` (line 712) | Portable |
| 903 | `createSegmentEnd` | `createSegmentEnd` (line 721) | Portable |
| 911 | `createZeroLengthHorizontalSegment` | `createZeroLengthHorizontalSegment` (line 727) | Portable |
| 919 | `createNegativeLengthHorizontalSegment` | `createNegativeLengthHorizontalSegment` (line 735) | Portable |
| 927 | `createHorizontalSegment` | `createHorizontalSegment` (line 743) | Portable |
| 941 | `createZeroLengthVerticalSegment` | `createZeroLengthVerticalSegment` (line 752) | Portable |
| 950 | `createNegativeLengthVerticalSegment` | `createNegativeLengthVerticalSegment` (line 760) | Portable |
| 959 | `createVerticalSegment` | `createVerticalSegment` (line 768) | Portable |
| 972 | `getWindingList` | `getWindingList` (line 777) | Portable |
| 988 | `getWindingNullList` | `getWindingNullList` (line 790) | Portable |
| 996 | `getWindingListLessThan2Points` | `getWindingListLessThan2Points` (line 798) | Portable |
| 1006 | `getWindingListNullPoint` | `getWindingListNullPoint` (line 808) | Portable |
| 1018 | `getWindingArray` | `getWindingArray` (line 820) | Portable |
| 1041 | `getWindingNullArray` | — | JVM only |
| 1049 | `getWindingArrayLessThan2Points` | `getWindingArrayLessThan2Points` (line 838) | Portable |
| 1059 | `getWindingArrayNullPoint` | `getWindingArrayNullPoint` (line 848) | Portable |
| 1072 | `reverseWindingNullList` | `reverseWindingNullList` (line 861) | Portable |
| 1080 | `reverseWindingNullArray` | — | JVM only |
| 1088 | `reverseWindingEmptyOrOneElement` | `reverseWindingEmptyOrOneElement` (line 869) | Portable |
| 1109 | `cleanseNullList` | `cleanseNullList` (line 884) | Portable |
| 1118 | `cleanseNullArray` | — | JVM only |
| 1127 | `cleanseListWithNullElements` | `cleanseListWithNullElements` (line 892) | Portable |
| 1141 | `cleanseArrayWithNullElements` | `cleanseArrayWithNullElements` (line 905) | Portable |
| 1153 | `cleanseEmpty` | `cleanseEmpty` (line 917) | Portable |
| 1167 | `cleanseList` | `cleanseList` (line 927) | Portable |
| 1196 | `cleanseArray` | `cleanseArray` (line 948) | Portable |
| 1227 | `createEllipse` | `createEllipse` (line 971) | Portable |
| 1241 | `createHalfEllipse` | `createHalfEllipse` (line 981) | Portable |
| 1255 | `createHalfEllipseAtOrigin` | `createHalfEllipseAtOrigin` (line 991) | Portable |
| 1269 | `createPolygonalEllipse` | `createPolygonalEllipse` (line 1001) | Portable |
| 1282 | `createPolygonalEllipseOddCount` | `createPolygonalEllipseOddCount` (line 1009) | Portable |
| 1299 | `createPolygonalEllipseLessCount` | `createPolygonalEllipseLessCount` (line 1018) | Portable |
| 1308 | `createPolygonalEllipseZeroWidth` | `createPolygonalEllipseZeroWidth` (line 1026) | Portable |
| 1317 | `createPolygonalEllipseZeroHeight` | `createPolygonalEllipseZeroHeight` (line 1034) | Portable |
| 1326 | `createPolygonalEllipseNegativeWidth` | `createPolygonalEllipseNegativeWidth` (line 1042) | Portable |
| 1335 | `createPolygonalEllipseNegativeHeight` | `createPolygonalEllipseNegativeHeight` (line 1050) | Portable |
| 1344 | `createPolygonalSlice` | `createPolygonalSlice` (line 1058) | Portable |
| 1357 | `createPolygonalSliceAtOrigin` | `createPolygonalSliceAtOrigin` (line 1066) | Portable |
| 1370 | `createPolygonalSliceInvalidCount` | `createPolygonalSliceInvalidCount` (line 1074) | Portable |
| 1379 | `createPolygonalSliceNegativeRadius` | `createPolygonalSliceNegativeRadius` (line 1082) | Portable |
| 1388 | `createPolygonalSliceZeroRadius` | `createPolygonalSliceZeroRadius` (line 1090) | Portable |
| 1397 | `createPolygonalSliceThetaLessThanZero` | `createPolygonalSliceThetaLessThanZero` (line 1098) | Portable |
| 1406 | `createPolygonalSliceThetaLessZero` | `createPolygonalSliceThetaLessZero` (line 1106) | Portable |
| 1415 | `createPolygonalSliceThetaGreaterThan180` | `createPolygonalSliceThetaGreaterThan180` (line 1114) | Portable |
| 1424 | `createPolygonalHalfEllipse` | `createPolygonalHalfEllipse` (line 1122) | Portable |
| 1437 | `createPolygonalHalfEllipseAtOrigin` | `createPolygonalHalfEllipseAtOrigin` (line 1130) | Portable |
| 1450 | `createPolygonalHalfEllipseInvalidCount` | `createPolygonalHalfEllipseInvalidCount` (line 1138) | Portable |
| 1459 | `createPolygonalHalfEllipseZeroWidth` | `createPolygonalHalfEllipseZeroWidth` (line 1146) | Portable |
| 1468 | `createPolygonalHalfEllipseNegativeWidth` | `createPolygonalHalfEllipseNegativeWidth` (line 1154) | Portable |
| 1477 | `createPolygonalHalfEllipseNegativeHeight` | `createPolygonalHalfEllipseNegativeHeight` (line 1162) | Portable |
| 1486 | `createPolygonalHalfEllipseZeroHeight` | `createPolygonalHalfEllipseZeroHeight` (line 1170) | Portable |
| 1495 | `createPolygonalCircle` | `createPolygonalCircle` (line 1178) | Portable |
| 1519 | `createPolygonalCircleInvalidCount` | `createPolygonalCircleInvalidCount` (line 1195) | Portable |
| 1528 | `createPolygonalCircleZeroCount` | `createPolygonalCircleZeroCount` (line 1203) | Portable |
| 1537 | `createPolygonalCircleNegativeCount` | `createPolygonalCircleNegativeCount` (line 1211) | Portable |
| 1546 | `createPolygonalCircleZeroRadius` | `createPolygonalCircleZeroRadius` (line 1219) | Portable |
| 1555 | `createPolygonalCircleNegativeRadius` | `createPolygonalCircleNegativeRadius` (line 1227) | Portable |
| 1564 | `createPolygonalCapsule` | `createPolygonalCapsule` (line 1235) | Portable |
| 1587 | `createPolygonalCapsuleInvalidCount` | `createPolygonalCapsuleInvalidCount` (line 1249) | Portable |
| 1596 | `createPolygonalCapsuleZeroWidth` | `createPolygonalCapsuleZeroWidth` (line 1257) | Portable |
| 1605 | `createPolygonalCapsuleNegativeWidth` | `createPolygonalCapsuleNegativeWidth` (line 1265) | Portable |
| 1614 | `createPolygonalCapsuleZeroHeight` | `createPolygonalCapsuleZeroHeight` (line 1273) | Portable |
| 1623 | `createPolygonalCapsuleNegativeHeight` | `createPolygonalCapsuleNegativeHeight` (line 1281) | Portable |
| 1632 | `flip` | `flip` (line 1289) | Portable |
| 1726 | `flipNullPolygon` | `flipNullPolygon` (line 1367) | Portable |
| 1735 | `flipNullAxis` | `flipNullAxis` (line 1375) | Portable |
| 1744 | `flipZeroAxis` | `flipZeroAxis` (line 1383) | Portable |
| 1753 | `flipNullPoint` | `flipNullPoint` (line 1391) | Portable |
| 1763 | `minkowskiSum` | `minkowskiSum` (line 1397) | Portable |
| 1805 | `minkowskiSumInvalidSegments` | `minkowskiSumInvalidSegments` (line 1420) | Portable |
| 1814 | `minkowskiSumNullWound1` | `minkowskiSumNullWound1` (line 1428) | Portable |
| 1823 | `minkowskiSumNullWound2` | `minkowskiSumNullWound2` (line 1436) | Portable |
| 1832 | `minkowskiSumNullShape1` | `minkowskiSumNullShape1` (line 1444) | Portable |
| 1841 | `minkowskiSumNullShape2` | `minkowskiSumNullShape2` (line 1452) | Portable |
| 1850 | `minkowskiSumNullShape3` | `minkowskiSumNullShape3` (line 1460) | Portable |
| 1859 | `minkowskiSumInvalidCount1` | `minkowskiSumInvalidCount1` (line 1468) | Portable |
| 1868 | `minkowskiSumInvalidCount2` | `minkowskiSumInvalidCount2` (line 1476) | Portable |
| 1877 | `minkowskiSumInvalidCount3` | `minkowskiSumInvalidCount3` (line 1484) | Portable |
| 1886 | `minkowskiSumInvalidCount4` | `minkowskiSumInvalidCount4` (line 1492) | Portable |
| 1895 | `minkowskiSumInvalidRadius1` | `minkowskiSumInvalidRadius1` (line 1500) | Portable |
| 1904 | `minkowskiSumInvalidRadius2` | `minkowskiSumInvalidRadius2` (line 1508) | Portable |
| 1913 | `scale` | `scale` (line 1516) | Portable |
| 1958 | `scaleNullCircle` | `scaleNullCircle` (line 1555) | Portable |
| 1967 | `scaleNullCapsule` | `scaleNullCapsule` (line 1563) | Portable |
| 1976 | `scaleNullEllipse` | `scaleNullEllipse` (line 1571) | Portable |
| 1985 | `scaleNullHalfEllipse` | `scaleNullHalfEllipse` (line 1579) | Portable |
| 1994 | `scaleNullSlice` | `scaleNullSlice` (line 1587) | Portable |
| 2003 | `scaleNullPolygon` | `scaleNullPolygon` (line 1595) | Portable |
| 2012 | `scaleNullSegment` | `scaleNullSegment` (line 1603) | Portable |
| 2021 | `scaleCircleInvalid` | `scaleCircleInvalid` (line 1611) | Portable |
| 2030 | `scaleCapsuleInvalid` | `scaleCapsuleInvalid` (line 1619) | Portable |
| 2039 | `scaleEllipseInvalid` | `scaleEllipseInvalid` (line 1627) | Portable |
| 2048 | `scaleHalfEllipseInvalid` | `scaleHalfEllipseInvalid` (line 1635) | Portable |
| 2057 | `scaleSliceInvalid` | `scaleSliceInvalid` (line 1643) | Portable |
| 2066 | `scalePolygonInvalid` | `scalePolygonInvalid` (line 1651) | Portable |
| 2075 | `scaleSegmentInvalid` | `scaleSegmentInvalid` (line 1659) | Portable |
| 2084 | `createLinksWrap` | `createLinksWrap` (line 1667) | Portable |
| 2106 | `createLinks` | `createLinks` (line 1686) | Portable |
| 2194 | `createLinksNull` | `createLinksNull` (line 1754) | Portable |
| 2202 | `createLinksOneVertex` | `createLinksOneVertex` (line 1762) | Portable |
| 2212 | `createLinksNullVertex` | `createLinksNullVertex` (line 1772) | Portable |
| 2226 | `createSlice` | `createSlice` (line 1785) | Portable |
| 2240 | `createSliceAtOrigin` | `createSliceAtOrigin` (line 1795) | Portable |
| 2254 | `polygonIntersection` | `polygonIntersection` (line 1805) | Portable |
| 2309 | `polygonIntersectionVertexOnEdgeA` | `polygonIntersectionVertexOnEdgeA` (line 1854) | Portable |
| 2362 | `polygonIntersectionVertexOnEdgeB` | `polygonIntersectionVertexOnEdgeB` (line 1901) | Portable |
| 2415 | `polygonIntersectionCoincidentVertexA` | `polygonIntersectionCoincidentVertexA` (line 1948) | Portable |
| 2468 | `polygonIntersectionCoincidentVertexB` | `polygonIntersectionCoincidentVertexB` (line 1995) | Portable |
| 2521 | `polygonIntersectionColinearEdgeB` | `polygonIntersectionColinearEdgeB` (line 2042) | Portable |
| 2577 | `polygonIntersectionEdgeTouching` | `polygonIntersectionEdgeTouching` (line 2092) | Portable |
| 2605 | `polygonIntersectionVertexTouching` | `polygonIntersectionVertexTouching` (line 2114) | Portable |
| 2633 | `polygonIntersectionVertexTouchingCoincident` | `polygonIntersectionVertexTouchingCoincident` (line 2136) | Portable |
| 2660 | `polygonIntersectionNoIntersection` | `polygonIntersectionNoIntersection` (line 2158) | Portable |
| 2687 | `polygonIntersectionContainment` | `polygonIntersectionContainment` (line 2180) | Portable |
| 2715 | `getRotationRadius` | `getRotationRadius` (line 2203) | Portable |
| 2745 | `getCounterClockwiseEdgeNormals` | `getCounterClockwiseEdgeNormals` (line 2223) | Portable |
| 2771 | `getCounterClockwiseEdgeNormalsWithNullVertex` | `getCounterClockwiseEdgeNormalsWithNullVertex` (line 2242) | Portable |
