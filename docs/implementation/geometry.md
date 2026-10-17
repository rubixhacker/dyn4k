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

The JVM and Android archives shape package fields and static entry points from
common Kotlin classes. The owned classes use `@kotlin.jvm.JvmField` for
protected stored fields. This keeps direct field access without adding helper
methods that can collide with Java subclass methods. Six shape classes retain
protected field visibility in the archives, even where the Java baseline uses
package fields. This safe widening lets Kotlin subclasses use the same fields
described by their metadata. Private stored fields keep private Kotlin
accessors. The strict geometry audit checks 551 baseline declarations in 31
owned types on both archives. After the integration merge, the strict all-root
audit checks 908 baseline declarations in 41 types on both archives.

Common Kotlin marks every baseline-overridable method in the owned open classes
`open`. `Link.rotate(double, double, double)` and `Link.translate(double,
double)` remain final, as in the baseline. The archive keeps those final flags.
The unchanged upstream geometry suite has 20 classes and 446 Java cases.
Geometry has 20 common tests on each available host, including a copy test in
the baseline Java package. A staged external Kotlin consumer tests base-typed
subclass dispatch on JVM, Linux x64, JS, both Wasm hosts, and Android host.
The Java consumer also compiles unchanged against the baseline and the staged
JVM and Android host archives.

Target qualification and independent review remain open until their separate
evidence is complete. The original foundation dependency is recorded in
`/tmp/dyn4k-issue34-handoff.md`.
