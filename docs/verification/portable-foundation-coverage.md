# Portable foundation coverage

**Reader and action.** Use this map to see which pinned dyn4j cases have an executed common Kotlin counterpart. A partial counterpart checks only the named scenario; it does not transfer the full upstream test's coverage. Run all six listed host tasks and read their XML results before using these cases as host evidence.

Source: [dyn4j 6.0.0 at `058bf6d982a0fb89b54050f929f6ea9dae53b714`](https://github.com/dyn4j/dyn4j/tree/058bf6d982a0fb89b54050f929f6ea9dae53b714). The 29 unchanged classes below have 615 `@Test` identities: 133 foundation, 446 geometry, and 36 tree/reference/version. The original Java suites are separate JVM evidence. A listed portable counterpart is adapted from the named original scenario and retains the upstream notice in its source file.

## Current portable cases

`PortableFoundationCoverageTest` contains 24 additional common `@Test` cases. The new upstream-named classes contain 167 one-to-one common counterparts for the 169 assigned foundation and tree/reference/version identities. Two original Java identities require JVM-only execution for the precise reasons below. In the earlier validation tree `a5794e26f411f015a61febb8c76afa60c17769bf`, 18 of the other 446 geometry identities had partial consumer scenarios and 428 had no common counterpart. That figure describes the earlier slice only. At combined corpus head `f09176dee50d20c01eee69db22ee7aef456e4288`, the geometry factory and shape reports map 434 of those 446 identities to common tests (170 factory and 264 shape cases); the other 12 have exact JVM-only dispositions. The generic tests are supplementary to the one-to-one tests.

## Upstream identity map

Each class heading links to the pinned source file. `Portable` names a one-to-one executable counterpart that retains the original inputs, assertions, and branch scenarios through a common Kotlin seam. `Partial` names a supplementary consumer scenario for only some assertions. `Unported` means there is no common counterpart. Names are exact Java method names.

### [Vector2Test](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/geometry/Vector2Test.java) (27)

| Original `@Test` | Status | Counterpart or precise disposition |
| --- | --- | --- |
| `create` | Portable | `UpstreamVector2CoverageTest.create` |
| `copy` | Portable | `UpstreamVector2CoverageTest.copy` |
| `distance` | Portable | `UpstreamVector2CoverageTest.distance` |
| `distanceBugInVersions_1_1_0_to_3_1_7` | Portable | `UpstreamVector2CoverageTest.distanceBugInVersions_1_1_0_to_3_1_7` |
| `tripleProduct` | Portable | `UpstreamVector2CoverageTest.tripleProduct` |
| `equals` | Portable | `UpstreamVector2CoverageTest.equals` |
| `set` | Portable | `UpstreamVector2CoverageTest.set` |
| `get` | Portable | `UpstreamVector2CoverageTest.get` |
| `add` | Portable | `UpstreamVector2CoverageTest.add` |
| `subtract` | Portable | `UpstreamVector2CoverageTest.subtract` |
| `to` | Portable | `UpstreamVector2CoverageTest.to` |
| `multiply` | Portable | `UpstreamVector2CoverageTest.multiply` |
| `divide` | Portable | `UpstreamVector2CoverageTest.divide` |
| `dot` | Portable | `UpstreamVector2CoverageTest.dot` |
| `cross` | Portable | `UpstreamVector2CoverageTest.cross` |
| `isOrthogonal` | Portable | `UpstreamVector2CoverageTest.isOrthogonal` |
| `isZero` | Portable | `UpstreamVector2CoverageTest.isZero` |
| `negate` | Portable | `UpstreamVector2CoverageTest.negate` |
| `zero` | Portable | `UpstreamVector2CoverageTest.zero` |
| `rotate` | Portable | `UpstreamVector2CoverageTest.rotate` |
| `project` | Portable | `UpstreamVector2CoverageTest.project` |
| `left` | Portable | `UpstreamVector2CoverageTest.left` |
| `right` | Portable | `UpstreamVector2CoverageTest.right` |
| `normalize` | Portable | `UpstreamVector2CoverageTest.normalize` |
| `getAngleBetweenRange` | Portable | `UpstreamVector2CoverageTest.getAngleBetweenRange` |
| `interpolate` | Portable | `UpstreamVector2CoverageTest.interpolate` |
| `equalsEpsilon` | Portable | `UpstreamVector2CoverageTest.equalsEpsilon` |

### [Vector3Test](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/geometry/Vector3Test.java) (21)

| Original `@Test` | Status | Counterpart or precise disposition |
| --- | --- | --- |
| `create` | Portable | `UpstreamVector3CoverageTest.create` |
| `copy` | Portable | `UpstreamVector3CoverageTest.copy` |
| `distance` | Portable | `UpstreamVector3CoverageTest.distance` |
| `tripleProduct` | Portable | `UpstreamVector3CoverageTest.tripleProduct` |
| `equals` | Portable | `UpstreamVector3CoverageTest.equals` |
| `set` | Portable | `UpstreamVector3CoverageTest.set` |
| `get` | Portable | `UpstreamVector3CoverageTest.get` |
| `add` | Portable | `UpstreamVector3CoverageTest.add` |
| `subtract` | Portable | `UpstreamVector3CoverageTest.subtract` |
| `to` | Portable | `UpstreamVector3CoverageTest.to` |
| `multiply` | Portable | `UpstreamVector3CoverageTest.multiply` |
| `dot` | Portable | `UpstreamVector3CoverageTest.dot` |
| `cross` | Portable | `UpstreamVector3CoverageTest.cross` |
| `isOrthogonal` | Portable | `UpstreamVector3CoverageTest.isOrthogonal` |
| `isZero` | Portable | `UpstreamVector3CoverageTest.isZero` |
| `negate` | Portable | `UpstreamVector3CoverageTest.negate` |
| `zero` | Portable | `UpstreamVector3CoverageTest.zero` |
| `project` | Portable | `UpstreamVector3CoverageTest.project` |
| `normalize` | Portable | `UpstreamVector3CoverageTest.normalize` |
| `interpolate` | Portable | `UpstreamVector3CoverageTest.interpolate` |
| `equalsEpsilon` | Portable | `UpstreamVector3CoverageTest.equalsEpsilon` |

### [RotationTest](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/geometry/RotationTest.java) (19)

| Original `@Test` | Status | Counterpart or precise disposition |
| --- | --- | --- |
| `create` | Portable | `UpstreamRotationCoverageTest.create` |
| `testIsUnit` | Portable | `UpstreamRotationCoverageTest.testIsUnit` |
| `copy` | Portable | `UpstreamRotationCoverageTest.copy` |
| `equals` | Portable | `UpstreamRotationCoverageTest.equals` |
| `set` | Portable | `UpstreamRotationCoverageTest.set` |
| `get` | Portable | `UpstreamRotationCoverageTest.get` |
| `toAngle` | Portable | `UpstreamRotationCoverageTest.toAngle` |
| `toVector` | Portable | `UpstreamRotationCoverageTest.toVector` |
| `dot` | Portable | `UpstreamRotationCoverageTest.dot` |
| `cross` | Portable | `UpstreamRotationCoverageTest.cross` |
| `isIdentity` | Portable | `UpstreamRotationCoverageTest.isIdentity` |
| `inverse` | Portable | `UpstreamRotationCoverageTest.inverse` |
| `rotate` | Portable | `UpstreamRotationCoverageTest.rotate` |
| `getRotated` | Portable | `UpstreamRotationCoverageTest.getRotated` |
| `compare` | Portable | `UpstreamRotationCoverageTest.compare` |
| `getRotationBetween` | Portable | `UpstreamRotationCoverageTest.getRotationBetween` |
| `getNormalizedAngle` | Portable | `UpstreamRotationCoverageTest.getNormalizedAngle` |
| `getShortestDistance` | Portable | `UpstreamRotationCoverageTest.getShortestDistance` |
| `isAngleBetween` | Portable | `UpstreamRotationCoverageTest.isAngleBetween` |

### [Matrix22Test](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/geometry/Matrix22Test.java) (28)

| Original `@Test` | Status | Counterpart or precise disposition |
| --- | --- | --- |
| `createNullMatrix` | JVM-only | `Matrix22((Matrix22)null)` passes a null object to a Java constructor; Kotlin's nonnull constructor parameter prevents this call on common hosts. `createNullArray` and `copy` cover portable constructor and copy behavior. |
| `createNullArray` | Portable | `UpstreamMatrix22CoverageTest.createNullArray` |
| `createLessThanFourElements` | Portable | `UpstreamMatrix22CoverageTest.createLessThanFourElements` |
| `createMoreThanFourElements` | Portable | `UpstreamMatrix22CoverageTest.createMoreThanFourElements` |
| `createFull` | Portable | `UpstreamMatrix22CoverageTest.createFull` |
| `createFullArray` | Portable | `UpstreamMatrix22CoverageTest.createFullArray` |
| `copy` | Portable | `UpstreamMatrix22CoverageTest.copy` |
| `add` | Portable | `UpstreamMatrix22CoverageTest.add` |
| `sum` | Portable | `UpstreamMatrix22CoverageTest.sum` |
| `subtract` | Portable | `UpstreamMatrix22CoverageTest.subtract` |
| `difference` | Portable | `UpstreamMatrix22CoverageTest.difference` |
| `multiplyMatrix` | Portable | `UpstreamMatrix22CoverageTest.multiplyMatrix` |
| `productMatrix` | Portable | `UpstreamMatrix22CoverageTest.productMatrix` |
| `multiplyVector` | Portable | `UpstreamMatrix22CoverageTest.multiplyVector` |
| `productVector` | Portable | `UpstreamMatrix22CoverageTest.productVector` |
| `multiplyVectorT` | Portable | `UpstreamMatrix22CoverageTest.multiplyVectorT` |
| `productVectorT` | Portable | `UpstreamMatrix22CoverageTest.productVectorT` |
| `multiplyScalar` | Portable | `UpstreamMatrix22CoverageTest.multiplyScalar` |
| `productScalar` | Portable | `UpstreamMatrix22CoverageTest.productScalar` |
| `identity` | Portable | `UpstreamMatrix22CoverageTest.identity` |
| `transpose` | Portable | `UpstreamMatrix22CoverageTest.transpose` |
| `getTranspose` | Portable | `UpstreamMatrix22CoverageTest.getTranspose` |
| `determinant` | Portable | `UpstreamMatrix22CoverageTest.determinant` |
| `invert` | Portable | `UpstreamMatrix22CoverageTest.invert` |
| `getInverse` | Portable | `UpstreamMatrix22CoverageTest.getInverse` |
| `solve` | Portable | `UpstreamMatrix22CoverageTest.solve` |
| `norm` | Portable | `UpstreamMatrix22CoverageTest.norm` |
| `equals` | Portable | `UpstreamMatrix22CoverageTest.equals` |

### [Matrix33Test](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/geometry/Matrix33Test.java) (26)

| Original `@Test` | Status | Counterpart or precise disposition |
| --- | --- | --- |
| `createFull` | Portable | `UpstreamMatrix33CoverageTest.createFull` |
| `createFullArray` | Portable | `UpstreamMatrix33CoverageTest.createFullArray` |
| `createNullArray` | Portable | `UpstreamMatrix33CoverageTest.createNullArray` |
| `createPartialArray` | Portable | `UpstreamMatrix33CoverageTest.createPartialArray` |
| `equalsHashcode` | Portable | `UpstreamMatrix33CoverageTest.equalsHashcode` |
| `copy` | Portable | `UpstreamMatrix33CoverageTest.copy` |
| `add` | Portable | `UpstreamMatrix33CoverageTest.add` |
| `sum` | Portable | `UpstreamMatrix33CoverageTest.sum` |
| `subtract` | Portable | `UpstreamMatrix33CoverageTest.subtract` |
| `difference` | Portable | `UpstreamMatrix33CoverageTest.difference` |
| `multiplyMatrix` | Portable | `UpstreamMatrix33CoverageTest.multiplyMatrix` |
| `productMatrix` | Portable | `UpstreamMatrix33CoverageTest.productMatrix` |
| `multiplyVector` | Portable | `UpstreamMatrix33CoverageTest.multiplyVector` |
| `productVector` | Portable | `UpstreamMatrix33CoverageTest.productVector` |
| `multiplyVectorT` | Portable | `UpstreamMatrix33CoverageTest.multiplyVectorT` |
| `productVectorT` | Portable | `UpstreamMatrix33CoverageTest.productVectorT` |
| `multiplyScalar` | Portable | `UpstreamMatrix33CoverageTest.multiplyScalar` |
| `productScalar` | Portable | `UpstreamMatrix33CoverageTest.productScalar` |
| `identity` | Portable | `UpstreamMatrix33CoverageTest.identity` |
| `transpose` | Portable | `UpstreamMatrix33CoverageTest.transpose` |
| `getTranspose` | Portable | `UpstreamMatrix33CoverageTest.getTranspose` |
| `determinant` | Portable | `UpstreamMatrix33CoverageTest.determinant` |
| `invert` | Portable | `UpstreamMatrix33CoverageTest.invert` |
| `getInverse` | Portable | `UpstreamMatrix33CoverageTest.getInverse` |
| `solve22` | Portable | `UpstreamMatrix33CoverageTest.solve22` |
| `solve33` | Portable | `UpstreamMatrix33CoverageTest.solve33` |

### [TransformTest](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/geometry/TransformTest.java) (12)

| Original `@Test` | Status | Counterpart or precise disposition |
| --- | --- | --- |
| `identity` | Portable | `UpstreamTransformCoverageTest.identity` |
| `translate` | Portable | `UpstreamTransformCoverageTest.translate` |
| `rotate` | Portable | `UpstreamTransformCoverageTest.rotate` |
| `copy` | Portable | `UpstreamTransformCoverageTest.copy` |
| `getTransformed` | Portable | `UpstreamTransformCoverageTest.getTransformed` |
| `transform` | Portable | `UpstreamTransformCoverageTest.transform` |
| `setTransform` | Portable | `UpstreamTransformCoverageTest.setTransform` |
| `setTranslation` | Portable | `UpstreamTransformCoverageTest.setTranslation` |
| `setRotation` | Portable | `UpstreamTransformCoverageTest.setRotation` |
| `lerp` | Portable | `UpstreamTransformCoverageTest.lerp` |
| `values` | Portable | `UpstreamTransformCoverageTest.values` |
| `getTranslationRotationTransform` | Portable | `UpstreamTransformCoverageTest.getTranslationRotationTransform` |

### [AABBTest](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/geometry/AABBTest.java) (26)

Partial: `createRadiusNegative` -> `PortableFoundationCoverageTest.boxRejectsReversedCoordinatesAndNegativeRadius`; `createFailure1` -> `PortableFoundationCoverageTest.boxRejectsReversedCoordinatesAndNegativeRadius`; `union` -> `PortableFoundationCoverageTest.boxUnionReturnsCopyAndMutationChangesReceiver`.

Unported: `createSuccess`, `createRadius`, `createCopy`, `createFailure2`, `perimeter`, `area`, `expand`, `overlaps`, `contains`, `getWidth`, `getHeight`, `translate`, `containsPoint`, `intersection`, `degenerate`, `testEquals`, `testHashcode`, `testToString`;
`createFromPoints`, `setFromPoints`, `copy`, `getCenter`, `zero`.

### [AbstractShapeTest](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/geometry/AbstractShapeTest.java) (2)

Unported: `create`, `setUserData`.

### [IntervalTest](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/geometry/IntervalTest.java) (19)

Partial: `includes` -> `PortableFoundationCoverageTest.intervalBoundaryModesAndUnionAreObservable`; `overlaps` -> `PortableFoundationCoverageTest.intervalBoundaryModesAndUnionAreObservable`; `union` -> `PortableFoundationCoverageTest.intervalBoundaryModesAndUnionAreObservable`.

Unported: `createMinGreaterThanMax`, `create`, `createCopy`, `setInvalidMax`, `setMax`, `setInvalidMin`, `setMin`, `contains`, `clamp`, `degenerate`, `intersection`, `distance`, `expand`, `getLength`, `copy`, `set`.

### [RayTest](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/geometry/RayTest.java) (10)

Partial: `create` -> `PortableFoundationCoverageTest.rayExposesLiveStartAndCopyOwnsItsStart`; `copy` -> `PortableFoundationCoverageTest.rayExposesLiveStartAndCopyOwnsItsStart`.

Unported: `createNullStart`, `createNullDirection`, `createZeroDirection`, `createFromOrigin`, `setStartNull`, `setDirectionNull`, `setDirectionZero`, `setDirection`.

### [CircleTest](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/geometry/CircleTest.java) (15)

Partial: `createZeroRadius` -> `PortableFoundationCoverageTest.circleBoundaryAndAreaUseOriginalRadius`; `contains` -> `PortableFoundationCoverageTest.circleBoundaryAndAreaUseOriginalRadius`; `getArea` -> `PortableFoundationCoverageTest.circleBoundaryAndAreaUseOriginalRadius`.

Unported: `createNegativeRadius`, `createSuccess`, `project`, `getFarthest`, `getAxes`, `getFoci`, `rotate`, `translate`, `createAABB`, `getRadius`, `createMass`, `copy`.

### [FeatureTest](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/geometry/FeatureTest.java) (3)

Unported: `create`, `createNonIndexed`, `copy`.

### [PolygonTest](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/geometry/PolygonTest.java) (25)

Partial: `createNotCCW` -> `PortableFoundationCoverageTest.polygonRejectsWrongWindingAndCoincidentVertices`; `createCoincident` -> `PortableFoundationCoverageTest.polygonRejectsWrongWindingAndCoincidentVertices`; `copy` -> `PortableFoundationCoverageTest.polygonVertexViewIsLiveAndCopyIsIndependent`.

Unported: `createNotEnoughPoints`, `createCCW`, `createNonConvex`, `createDegenerate`, `createNullPoints`, `createNullPoint`, `createSuccess`, `contains`, `project`, `getFarthest`, `getAxes`, `getFoci`, `rotate`, `translate`, `createAABB`, `containsPointCoIncidentStart`, `containsPointCoIncidentMid`, `containsPointCoIncidentWithCoincidentEdges`;
`containsPointCoIncidentWithCoincidentEdges2`, `getNormals`, `createMass`, `getArea`.

### [RectangleTest](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/geometry/RectangleTest.java) (11)

Partial: `getArea` -> `PortableFoundationCoverageTest.rectangleAreaAndTranslationKeepDimensions`.

Unported: `createInvalidWidth`, `createInvalidHeight`, `createSuccess`, `getAxes`, `contains`, `project`, `getRotation`, `createMass`, `computeAABB`, `copy`.

### [MassTest](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/geometry/MassTest.java) (22)

Unported: `createNegativeMass`, `createNegativeInertia`, `createNullCenter`, `createSuccess`, `createInfinite`, `createFixedLinearVelocity`, `createFixedAngularVelocity`, `createCopyNull`, `createCopy`, `createList`, `createListInfinite`, `createListOneElement`, `createListNull`, `createListEmpty`, `createListOneNullElement`, `createListNullElement`, `setType`, `setNullType`;
`setTypeIgnored`, `polygonInertiaAndCOM`, `polygonInertiaAndMass`, `equals`.

### [TriangleTest](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/geometry/TriangleTest.java) (6)

Unported: `createNullPoint1`, `createNullPoint2`, `createNullPoint3`, `tostring`, `contains`, `copy`.

### [SegmentTest](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/geometry/SegmentTest.java) (22)

Partial: `getSegmentIntersection` -> `PortableFoundationCoverageTest.segmentsIntersectAtKnownPoint`; `getArea` -> `PortableFoundationCoverageTest.segmentsIntersectAtKnownPoint`.

Unported: `createNullPoint1`, `createNullPoint2`, `createCoincident`, `creatSuccess`, `getLength`, `getLocation`, `getPointClosest`, `getAxes`, `getFoci`, `contains`, `containsRadius`, `project`, `getFarthest`, `rotate`, `translate`, `createAABB`, `getLineIntersection`, `createMass`;
`getNormals`, `copy`.

### [WoundTest](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/geometry/WoundTest.java) (6)

Unported: `getRadius`, `getRadiusCenter`, `woundIteratorStartIndex`, `woundIteratorCount`, `woundIteratorFail`, `woundIteratorRemove`.

### [LinkTest](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/geometry/LinkTest.java) (8)

Unported: `createNullPoint1`, `createNullPoint2`, `createCoincident`, `creatSuccess`, `rotate`, `translate`, `copy`, `copyNonLoop`.

### [AdaptiveDecimalTest](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/geometry/AdaptiveDecimalTest.java) (17)

Unported: `create`, `size`, `append`, `copy`, `clear`, `removeZeros`, `negate`, `getEstimation`, `normalize`, `sum`, `checkInvariants`, `testIndex1`, `testIndex2`, `testIndex3`, `testArgument1`, `testArgument2`, `testState`.

### [RobustGeometryTest](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/geometry/RobustGeometryTest.java) (2)

Unported: `randomizedTest`, `randomizedTest2`.

### [CapsuleTest](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/geometry/CapsuleTest.java) (20)

Unported: `createZeroWidth`, `createNegativeWidth`, `createZeroHeight`, `createNegativeHeight`, `createCircle`, `createSuccessHorizontal`, `createSuccessVertical`, `contains`, `project`, `getFarthest`, `getAxes`, `getFoci`, `rotate`, `translate`, `createAABB`, `createMass`, `getArea`, `getRadius`;
`getRotation`, `copy`.

### [EllipseTest](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/geometry/EllipseTest.java) (19)

Unported: `createZeroWidth`, `createNegativeWidth`, `createZeroHeight`, `createNegativeHeight`, `createSuccess`, `contains`, `project`, `getFarthest`, `getFarthestPointOnEllipse`, `getAxes`, `getFoci`, `rotate`, `translate`, `createAABB`, `getRadius`, `createMass`, `getArea`, `getRotation`;
`copy`.

### [HalfEllipseTest](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/geometry/HalfEllipseTest.java) (18)

Unported: `createZeroWidth`, `createNegativeWidth`, `createZeroHeight`, `createNegativeHeight`, `createSuccess`, `contains`, `project`, `getFarthest`, `getAxes`, `getFoci`, `rotate`, `translate`, `createAABB`, `createMass`, `getArea`, `getRadius`, `getRadiusAboveXAxisBelowEvolute`, `copy`.

### [SliceTest](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/geometry/SliceTest.java) (19)

Unported: `createZeroRadius`, `createNegativeRadius`, `createZeroTheta`, `createNegativeTheta`, `createSuccess`, `contains`, `project`, `getFarthest`, `getAxes`, `getFoci`, `rotate`, `translate`, `createAABB`, `sliceRadius`, `createMass`, `getArea`, `getRadiusAtPoint`, `getRotation`;
`copy`.

### [GeometryTest](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/geometry/GeometryTest.java) (176)

Partial: `getWindingList` -> `PortableFoundationCoverageTest.windingChangesSignWhenVertexOrderReverses`.

Unported: `getAverageCenterArray`, `getAverageCenterList`, `getAverageCenterNullArray`, `getAverageCenterEmptyArray`, `getAverageCenterArrayNullElements`, `getAverageCenterArrayNullOnlyElement`, `getAverageCenterNullList`, `getAverageCenterEmptyList`, `getAverageCenterListNullElements`, `getAverageCenterListNullOnlyElement`, `getAreaWeightedCenter`, `getAreaWeightedCenterOffset`, `getAreaWeightedCenterNullArray`, `getAreaWeightedCenterEmptyArray`, `getAreaWeightedCenterArrayNullElements`, `getAreaWeightedCenterNullList`, `getAreaWeightedCenterEmptyList`, `getAreaWeightedCenterListNullElements`;
`getAreaWeightedCenterZeroAreaList`, `getAreaWeightedCenterZeroAreaArray`, `createUnitCirclePolygon`, `createNegativeRadiusUnitCirclePolygon`, `createZeroRadiusUnitCirclePolygon`, `createLessThan3PointsUnitCirclePolygon`, `createCircle`, `createNegativeRadiusCircle`, `createZeroRadiusCircle`, `createPolygonNullArray`, `createPolygonNullPoint`, `createPolygon`, `createPolygonAtOrigin`, `createZeroSizeSquare`, `createNegativeSizeSquare`, `createSquare`, `createRectangle`, `createNegativeWidthRectangle`;
`createNegativeHeightRectangle`, `createZeroWidthRectangle`, `createZeroHeightRectangle`, `createTriangleNullPoint`, `createTriangle`, `createTriangleAtOrigin`, `createZeroWidthRightTriangle`, `createZeroHeightRightTriangle`, `createNegativeWidthRightTriangle`, `createNegativeHeightRightTriangle`, `createRightTriangle`, `createRightTriangleMirror`, `createZeroHeightEquilateralTriangle`, `createNegativeHeightEquilateralTriangle`, `createEquilateralTriangle`, `createZeroWidthIsoscelesTriangle`, `createZeroHeightIsoscelesTriangle`, `createNegativeWidthIsoscelesTriangle`;
`createNegativeHeightIsoscelesTriangle`, `createIsoscelesTriangle`, `createSegmentNullPoint1`, `createSegmentNullPoint2`, `createSegment`, `createSegmentAtOrigin`, `createSegmentEnd`, `createZeroLengthHorizontalSegment`, `createNegativeLengthHorizontalSegment`, `createHorizontalSegment`, `createZeroLengthVerticalSegment`, `createNegativeLengthVerticalSegment`, `createVerticalSegment`, `getWindingNullList`, `getWindingListLessThan2Points`, `getWindingListNullPoint`, `getWindingArray`, `getWindingNullArray`;
`getWindingArrayLessThan2Points`, `getWindingArrayNullPoint`, `reverseWindingNullList`, `reverseWindingNullArray`, `reverseWindingEmptyOrOneElement`, `cleanseNullList`, `cleanseNullArray`, `cleanseListWithNullElements`, `cleanseArrayWithNullElements`, `cleanseEmpty`, `cleanseList`, `cleanseArray`, `createEllipse`, `createHalfEllipse`, `createHalfEllipseAtOrigin`, `createPolygonalEllipse`, `createPolygonalEllipseOddCount`, `createPolygonalEllipseLessCount`;
`createPolygonalEllipseZeroWidth`, `createPolygonalEllipseZeroHeight`, `createPolygonalEllipseNegativeWidth`, `createPolygonalEllipseNegativeHeight`, `createPolygonalSlice`, `createPolygonalSliceAtOrigin`, `createPolygonalSliceInvalidCount`, `createPolygonalSliceNegativeRadius`, `createPolygonalSliceZeroRadius`, `createPolygonalSliceThetaLessThanZero`, `createPolygonalSliceThetaLessZero`, `createPolygonalSliceThetaGreaterThan180`, `createPolygonalHalfEllipse`, `createPolygonalHalfEllipseAtOrigin`, `createPolygonalHalfEllipseInvalidCount`, `createPolygonalHalfEllipseZeroWidth`, `createPolygonalHalfEllipseNegativeWidth`, `createPolygonalHalfEllipseNegativeHeight`;
`createPolygonalHalfEllipseZeroHeight`, `createPolygonalCircle`, `createPolygonalCircleInvalidCount`, `createPolygonalCircleZeroCount`, `createPolygonalCircleNegativeCount`, `createPolygonalCircleZeroRadius`, `createPolygonalCircleNegativeRadius`, `createPolygonalCapsule`, `createPolygonalCapsuleInvalidCount`, `createPolygonalCapsuleZeroWidth`, `createPolygonalCapsuleNegativeWidth`, `createPolygonalCapsuleZeroHeight`, `createPolygonalCapsuleNegativeHeight`, `flip`, `flipNullPolygon`, `flipNullAxis`, `flipZeroAxis`, `flipNullPoint`;
`minkowskiSum`, `minkowskiSumInvalidSegments`, `minkowskiSumNullWound1`, `minkowskiSumNullWound2`, `minkowskiSumNullShape1`, `minkowskiSumNullShape2`, `minkowskiSumNullShape3`, `minkowskiSumInvalidCount1`, `minkowskiSumInvalidCount2`, `minkowskiSumInvalidCount3`, `minkowskiSumInvalidCount4`, `minkowskiSumInvalidRadius1`, `minkowskiSumInvalidRadius2`, `scale`, `scaleNullCircle`, `scaleNullCapsule`, `scaleNullEllipse`, `scaleNullHalfEllipse`;
`scaleNullSlice`, `scaleNullPolygon`, `scaleNullSegment`, `scaleCircleInvalid`, `scaleCapsuleInvalid`, `scaleEllipseInvalid`, `scaleHalfEllipseInvalid`, `scaleSliceInvalid`, `scalePolygonInvalid`, `scaleSegmentInvalid`, `createLinksWrap`, `createLinks`, `createLinksNull`, `createLinksOneVertex`, `createLinksNullVertex`, `createSlice`, `createSliceAtOrigin`, `polygonIntersection`;
`polygonIntersectionVertexOnEdgeA`, `polygonIntersectionVertexOnEdgeB`, `polygonIntersectionCoincidentVertexA`, `polygonIntersectionCoincidentVertexB`, `polygonIntersectionColinearEdgeB`, `polygonIntersectionEdgeTouching`, `polygonIntersectionVertexTouching`, `polygonIntersectionVertexTouchingCoincident`, `polygonIntersectionNoIntersection`, `polygonIntersectionContainment`, `getRotationRadius`, `getCounterClockwiseEdgeNormals`, `getCounterClockwiseEdgeNormalsWithNullVertex`.

### [AVLTreeTest](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/AVLTreeTest.java) (29)

| Original `@Test` | Status | Counterpart or precise disposition |
| --- | --- | --- |
| `insertDuplicate` | Portable | `UpstreamAVLTreeCoverageTest.insertDuplicate` |
| `insertSequential` | Portable | `UpstreamAVLTreeCoverageTest.insertSequential` |
| `insertInOrder` | Portable | `UpstreamAVLTreeCoverageTest.insertInOrder` |
| `insertReverseOrder` | Portable | `UpstreamAVLTreeCoverageTest.insertReverseOrder` |
| `insertReverseOrderSorted` | Portable | `UpstreamAVLTreeCoverageTest.insertReverseOrderSorted` |
| `insertShuffled` | Portable | `UpstreamAVLTreeCoverageTest.insertShuffled` |
| `sequentialRemoval` | Portable | `UpstreamAVLTreeCoverageTest.sequentialRemoval` |
| `removeRoot` | Portable | `UpstreamAVLTreeCoverageTest.removeRoot` |
| `removeRootNodeAndReplaceWithRight` | Portable | `UpstreamAVLTreeCoverageTest.removeRootNodeAndReplaceWithRight` |
| `random` | Portable | `UpstreamAVLTreeCoverageTest.random` |
| `remove` | Portable | `UpstreamAVLTreeCoverageTest.remove` |
| `removeNotFound` | Portable | `UpstreamAVLTreeCoverageTest.removeNotFound` |
| `getDepth` | Portable | `UpstreamAVLTreeCoverageTest.getDepth` |
| `getMinimum` | Portable | `UpstreamAVLTreeCoverageTest.getMinimum` |
| `getMaximum` | Portable | `UpstreamAVLTreeCoverageTest.getMaximum` |
| `isEmpty` | Portable | `UpstreamAVLTreeCoverageTest.isEmpty` |
| `clear` | Portable | `UpstreamAVLTreeCoverageTest.clear` |
| `contains` | Portable | `UpstreamAVLTreeCoverageTest.contains` |
| `get` | Portable | `UpstreamAVLTreeCoverageTest.get` |
| `size` | Portable | `UpstreamAVLTreeCoverageTest.size` |
| `iterator` | Portable | `UpstreamAVLTreeCoverageTest.iterator` |
| `tailIterator` | Portable | `UpstreamAVLTreeCoverageTest.tailIterator` |
| `headIterator` | Portable | `UpstreamAVLTreeCoverageTest.headIterator` |
| `subsetIterator` | Portable | `UpstreamAVLTreeCoverageTest.subsetIterator` |
| `tailIteratorMissing` | Portable | `UpstreamAVLTreeCoverageTest.tailIteratorMissing` |
| `headIteratorMissing` | Portable | `UpstreamAVLTreeCoverageTest.headIteratorMissing` |
| `subsetIteratorMissing` | Portable | `UpstreamAVLTreeCoverageTest.subsetIteratorMissing` |
| `goncaloMarquesIssue` | Portable | `UpstreamAVLTreeCoverageTest.goncaloMarquesIssue` |
| `insertSimple` | Portable | `UpstreamAVLTreeCoverageTest.insertSimple` |

### [ReferenceTest](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/ReferenceTest.java) (4)

| Original `@Test` | Status | Counterpart or precise disposition |
| --- | --- | --- |
| `testCreate` | Portable | `UpstreamReferenceCoverageTest.testCreate` |
| `testToString` | Portable | `UpstreamReferenceCoverageTest.testToString` |
| `testEquals` | Portable | `UpstreamReferenceCoverageTest.testEquals` |
| `testHashcode` | Portable | `UpstreamReferenceCoverageTest.testHashcode` |

### [VersionTest](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/VersionTest.java) (3)

| Original `@Test` | Status | Counterpart or precise disposition |
| --- | --- | --- |
| `versions` | Portable | `UpstreamVersionCoverageTest.versions` |
| `getVersionString` | Portable | `UpstreamVersionCoverageTest.getVersionString` |
| `main` | JVM-only | Captures and redirects `System.out` using `PrintStream` and `ByteArrayOutputStream`; `getVersionString` and `versions` cover portable version behavior. |

## JVM-only and open work

`VersionTest.main` and `Matrix22Test.createNullMatrix` have precise JVM-only dispositions in the identity map. The unchanged Java suites remain JVM tests, and neither their passes nor compilation is counted as portable execution.

`AdaptiveDecimalTest` exercises a package-private baseline type. The first common test attempt compiled on JVM and failed on Android host with `IllegalAccessError` from the patched candidate archive. A package-scoped follow-up can port those cases; this public-seam suite does not count them.

This earlier bounded slice covers the 169 assigned foundation and tree/reference/version identities with 167 portable counterparts and two JVM-only dispositions. The combined corpus portfolio now has dispositions for all 446 geometry identities as stated above; that inventory does not establish a combined-head six-host pass. Unchanged sample applications and the full 21-target qualification matrix remain outside this slice and unpassed here.

## Reproduction and evidence

The validation tree was `a5794e26f411f015a61febb8c76afa60c17769bf`, after merging `codex/dyn4k-port` at `7825e42beb2a9d3c804512a1f561e2262f7e8624`. The pinned upstream source was `058bf6d982a0fb89b54050f929f6ea9dae53b714`. The SHA-256 of the sorted `sha256sum` manifest for all nine tracked files in `dyn4k-core/src/commonTest/kotlin/org/dyn4j/coverage/` was `b86ae1bcf57a09fde309e61dc399e50c27e507034a987bff52f292a8f02c3363`.

The executed command was:

```sh
JAVA_HOME=/tmp/dyn4k-tools/jdk21 ANDROID_HOME=/var/home/stewart/Android/Sdk PATH=/tmp/dyn4k-tools/jdk21/bin:$PATH ./gradlew :dyn4k-core:jvmTest :dyn4k-core:linuxX64Test :dyn4k-core:jsNodeTest :dyn4k-core:wasmJsNodeTest :dyn4k-core:wasmWasiNodeTest :dyn4k-core:testAndroidHostTest :dyn4k-core:runUpstreamFoundationTests :dyn4k-core:runUpstreamTreeTests --no-daemon --rerun-tasks --console=plain
```

The six common test tasks each wrote 10 JUnit XML files under `dyn4k-core/build/test-results/<task>/`. Each executed 191 tests: 167 new one-to-one counterparts and 24 supplementary cases.

| Host task | Expected | Executed | Failures | Errors | Skipped |
| --- | ---: | ---: | ---: | ---: | ---: |
| `jvmTest` | 191 | 191 | 0 | 0 | 0 |
| `linuxX64Test` | 191 | 191 | 0 | 0 | 0 |
| `jsNodeTest` | 191 | 191 | 0 | 0 | 0 |
| `wasmJsNodeTest` | 191 | 191 | 0 | 0 | 0 |
| `wasmWasiNodeTest` | 191 | 191 | 0 | 0 | 0 |
| `testAndroidHostTest` | 191 | 191 | 0 | 0 | 0 |

Android host is a JVM host test, not an Android device run. The unchanged Java candidate suites executed 133 foundation and 36 tree/reference/version cases with zero failures. The same nine unchanged classes separately passed 169 tests against the pinned baseline JAR:

```sh
/tmp/dyn4k-tools/jdk21/bin/java -cp /tmp/dyn4k-portable-baseline-cache/run/classes:/tmp/dyn4k-portable-baseline-cache/dyn4j-6.0.0.jar:/tmp/dyn4k-portable-baseline-cache/deps/junit-4.13.1.jar:/tmp/dyn4k-portable-baseline-cache/deps/hamcrest-core-1.3.jar org.junit.runner.JUnitCore org.dyn4j.geometry.Vector2Test org.dyn4j.geometry.Vector3Test org.dyn4j.geometry.RotationTest org.dyn4j.geometry.Matrix22Test org.dyn4j.geometry.Matrix33Test org.dyn4j.geometry.TransformTest org.dyn4j.AVLTreeTest org.dyn4j.ReferenceTest org.dyn4j.VersionTest
```

The pinned baseline JAR SHA-256 was `204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e`. Earlier full-baseline evidence at `/tmp/dyn4k-portable-baseline-run.json` remains separate; its report SHA-256 was `fb86f1829ae1c33779abfa0d98d6a272c829f1e6429c6cc2147bc7c9b0f414b4`.

| Executed host artifact | SHA-256 |
| --- | --- |
| JVM core JAR | `bb88fc8e68fef093d1f8f8f4e2d972b81bdd85faccbf1e36c357c3d3bc99e1fe` |
| Android host runtime JAR | `13a74b9dd38d0a1a0fd518be8e7702ebdca85cc930414bb96d2ecae4f1748609` |
| Linux x64 test executable | `f5031c25417c2e5cc007a383d27ce0eb2c49af5d8cc0df5d99ac308ba3a60ddc` |
| JS Node test program | `f5169e648b5967b8a03ddaf3a8428418904d169b7fdb00506dc4d0662da85622` |
| Wasm JS Node test module | `b23ab812fb379d75bc5e25ad8ee21a48f0542a5ab3e7203055160f72887a8112` |
| Wasm WASI Node test module | `c56e4389164999ed990ddb1ca42bbeb70a40134f07c67862301d6c7eb4928f81` |

The first Vector2 run had three failing identity assertions because Java `==` had been translated as Kotlin structural equality; changing those checks to `===` preserved the original identity contract. The first Android host run had six `IllegalAccessError` cases because the AVL test class was placed outside the original `org.dyn4j` package while that host uses a package-access candidate archive. Placing that class in the original package fixed all six. These were test-translation defects; no engine behavior defect was found. `AVLTreeTest.insertShuffled` uses the exact `Collections.shuffle(..., new Random(17))` order, precomputed from the original 25 values, on every host. All 167 portable methods retained the same number of active assertions as their original methods after source comments were removed.
