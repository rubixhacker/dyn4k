# Geometry port inventory

The fixed baseline is dyn4j 6.0.0 at upstream revision
`058bf6d982a0fb89b54050f929f6ea9dae53b714`. This inventory covers
the root `org.dyn4j.geometry` package and the supporting declarations used by
[Create and query every baseline shape through both APIs](https://github.com/rubixhacker/dyn4k/issues/34).

| Owner | Baseline declarations | Status |
| --- | --- | --- |
| [Resolve staged vector and transform consumers on the pinned toolchain](https://github.com/rubixhacker/dyn4k/issues/33) | `Matrix22`, `Matrix33`, `Rotatable`, `Rotation`, `Shiftable`, `Transform`, `Transformable`, `Translatable`, `Vector2`, `Vector3` | Foundation work, with a narrow internal `Rotation.fromComponentsUnchecked` addition for `Rectangle` and `Capsule` |
| This branch | `AABB`, `AbstractShape`, `AdaptiveDecimal`, `Capsule`, `Circle`, `Convex`, `EdgeFeature`, `Ellipse`, `Feature`, `Geometry`, `HalfEllipse`, `Interval`, `Link`, `Mass`, `MassType`, `PointFeature`, `Polygon`, `Ray`, `Rectangle`, `RobustGeometry`, `Segment`, `Shape`, `Slice`, `Triangle`, `Wound`, `WoundIterator` | Implemented in common Kotlin |
| This branch, support | `DataContainer`, `EmptyCollectionException`, `InvalidIndexException`, `NullElementException`, `ValueOutOfRangeException` | Implemented in common Kotlin |
| [Traverse and mutate baseline tree data structures](https://github.com/rubixhacker/dyn4k/issues/46) | Root AVL/tree classes, `Reference`, `Version` | Separate owner |
| [Turn input polygons into usable convex shapes](https://github.com/rubixhacker/dyn4k/issues/36) | Geometry hull, decomposition, and simplification packages | Separate owner |

The Java package and static compatibility surface is assembled in the JVM
artifact from common Kotlin classes. `scripts/verify-geometry-jvm-api.py`
compares baseline and candidate `javap -package` declarations for 26 geometry
types and five supporting types owned here (585 declarations). The unchanged
upstream geometry test suite has 20
classes and 446 cases. The Java consumer uses identical source for baseline,
candidate, and staged Maven JVM artifacts and has 19 checks. The Kotlin API
consumer has 14 common tests. The checks cover construction, queries,
transforms, copies, live arrays, Java package and protected access, factory
overloads, mutable identity, and errors.

The full root-package audit has identified 13 missing package declarations in
the foundation classes owned by [Resolve staged vector and transform consumers
on the pinned toolchain](https://github.com/rubixhacker/dyn4k/issues/33).
The exact dependency and affected members
are recorded in `/tmp/dyn4k-issue34-handoff.md`. Empirical native device,
store, and other target qualification remain open until their own checks run.
