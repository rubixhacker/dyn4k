# Java source projection at the coherent World candidate

This review covers the 98 distinct added declarations in the frozen audit of World revision `f9920e9`.
The pinned source is dyn4j 6.0.0 at `058bf6d982a0fb89b54050f929f6ea9dae53b714`.
The baseline JAR SHA-256 is `204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e`.
The frozen audit is `/tmp/dyn4k-root-api-f9920e9/result.json`.

## Classification and repair

| Declaration group | Distinct declarations | Pinned source visibility | Java source nameability | Result |
| --- | ---: | --- | --- | --- |
| Generated `Companion` fields | 44 | 42 public types; 2 package-private types | Yes, including same-package source for the latter two | JVM and Android archives mark the fields synthetic. Kotlin metadata and field storage remain. |
| Enum `getEntries()` methods | 5 | 2 public enums; 3 package-private enums | Yes, including same-package source for the latter three | JVM and Android archives mark the methods synthetic. Kotlin `entries` remains. |
| Generated node property accessors | 28 | 3 package-private node types | Yes, from same-package subclasses | Kotlin declares distinct JVM accessor names. Java subclass methods no longer collide or override engine accessors. |
| Private World nested members | 10 | 9 private iterators and 1 private handler | No. `InnerClasses` marks each nested class private. | No projection change. |
| Hyphenated helper methods | 11 | 8 distinct JVM names across collision helpers | No. A hyphen cannot occur in a Java identifier. | No projection change. |
| **Total** | **98** | | **77 nameable; 21 not nameable** | |

The 160 audit risk paths include inherited paths to the same declaration.
They do not represent 160 distinct declarations.
The frozen report's prose called the hyphenated helpers “ten.”
The JSON contains 11 declarations with 8 distinct JVM names.

### Exact membership

The 44 generated `Companion` fields belong to these types:

| Package | Types |
| --- | --- |
| `org.dyn4j` | `Epsilon`, `UnitConversion`, `Unsafe`, `Version` |
| `org.dyn4j.collision` | `AbstractCollisionItem`, `AbstractCollisionPair`, `CollisionBody`, `Collisions`, `Filter` |
| `org.dyn4j.collision.broadphase` | `AbstractBroadphaseDetector`, `BroadphaseDetector` |
| `org.dyn4j.collision.continuous` | `ConservativeAdvancement` |
| `org.dyn4j.collision.manifold` | `ManifoldPointId` |
| `org.dyn4j.collision.narrowphase` | `CircleDetector`, `Epa`, `Gjk`, `SegmentDetector` |
| `org.dyn4j.dynamics` | `BodyFixture`, `PhysicsBody`, `Settings` |
| `org.dyn4j.dynamics.joint` | `AbstractJoint`, `Joint` |
| `org.dyn4j.exception` | `ValueOutOfRangeException` |
| `org.dyn4j.geometry` | `AABB`, `AdaptiveDecimal`, `Capsule`, `Ellipse`, `Feature`, `Geometry`, `HalfEllipse`, `Interval`, `Mass`, `Polygon`, `RobustGeometry`, `Rotation`, `Segment`, `Transform`, `Vector2`, `Vector3` |
| `org.dyn4j.geometry.decompose` | `EarClipping` |
| `org.dyn4j.geometry.hull` | `LinkedVertexHull` |
| `org.dyn4j.world` | `CollisionWorld`, `PhysicsWorld`, `ValueMixer` |

`AdaptiveDecimal` and `LinkedVertexHull` are package-private in the pinned source.
The other 42 declaring types are public.
The frozen audit lists `Companion` through inheritance on additional candidate types.
The classification counts each declaring field once.

The five enum methods belong to `ContinuousDetectionMode`, `MassType`,
`MonotoneChainType`, `MonotonePolygonType`, and `SweepLineVertexType`.
The first two enums are public; the other three are package-private.

The 28 node accessors belong to three package-private baseline classes:

| Type | Added accessor names |
| --- | --- |
| `org.dyn4j.collision.broadphase.DynamicAABBTreeNode` | `getLeft`, `setLeft`, `getRight`, `setRight`, `getParent`, `setParent`, `getHeight`, `setHeight`, `getAabb` |
| `org.dyn4j.geometry.simplify.SegmentTreeNode` | The same nine names. |
| `org.dyn4j.geometry.simplify.SimplePolygonVertex` | `getIndex`, `getPoint`, `getPrev`, `setPrev`, `getNext`, `setNext`, `getPrevSegment`, `setPrevSegment`, `getNextSegment`, `setNextSegment` |

The nine private iterator members are `Void remove()` in
`AbstractCollisionWorld`'s `AABBBodyDetectIterator`, `AABBDetectIterator`,
`CollisionDataIterator`, `ConvexBodyDetectIterator`, `ConvexCastDetectIterator`,
`ConvexDetectIterator`, `DetectIterator`, `RaycastBodyDetectIterator`, and
`RaycastDetectIterator`.
The tenth is `AbstractPhysicsWorld.WarmStartHandler.data`.
The class-file flags alone omit the nested-class source visibility.
The `InnerClasses` entry is private in the pinned and candidate archives.
The negative Java 8 fixture names all ten nested types from the same package.
The baseline, JVM, and Android archives each reject all ten as private.

The 11 hyphenated declarations are `setDirect-dyn4k` in `TimeOfImpact`,
`Penetration`, `Raycast`, and `Separation`; `appendPointDirect-dyn4k`,
`setNormalDirect-dyn4k`, and `pointCountDirect-dyn4k` in `Manifold`;
`shiftPointDirect-dyn4k` in `ManifoldPoint`;
and `supportPoint1-dyn4k`, `supportPoint2-dyn4k`, and `point-dyn4k` in
`MinkowskiSumPoint`.

## Source evidence

The frozen `AddedStaticField.java` and `AddedStaticMethod.java` files compile
and run on Java 8 against the pinned baseline. They failed candidate compilation
at `f9920e9` with ambiguous `Companion` and `getEntries()` names.
Their source hashes match the copies in `tools/compatibility/fixtures/java_source_projection/`.

Three same-package subclass fixtures then exposed generated node accessor conflicts.
Each compiles and runs against the pinned baseline.
The unmodified candidate rejected `getLeft()` in `SegmentTreeNode` and
`DynamicAABBTreeNode`, and `getPoint()` in `SimplePolygonVertex`.

`probe_added_members.py` builds one adverse Java source per nameable declaration.
It checks 44 companion fields, 5 enum methods, and 28 node accessors.
Each source compiles against the baseline and the repaired providers.
The compiled source executes with Java 8 and Java 21.
The generated `result.json` records source, archive, and run-log hashes.

## Executed checks before commit

| Check | Observation |
| --- | --- |
| Strict JVM, Android compile, and Android runtime API inventories | Each found 216 required types and 3,078 required declarations. Each found zero missing signatures, mismatches, fixture failures, or inventory errors. Each exited 1 because 49 added-member paths remain in the strict report. These are exactly 39 hyphenated methods and 10 private nested members. |
| Adverse Java source probes | All 77 nameable additions compiled and ran against the pinned baseline and all three repaired archives. Java 8 and Java 21 compiled the sources; both runtimes executed them. |
| Unchanged Java corpus | All 2,385 cases passed with zero failures or ignores under Java 8 and Java 21. Both JVM and Android host archives were compiled against separately. |
| Six available host lanes | Core ran 928 cases per lane. The Kotlin API ran 46 per lane, except 48 on JVM. JVM, Android host, Linux x64, JS Node, Wasm JS Node, and Wasm WASI Node passed with zero failures or skips. |
| Staged consumers | The three unchanged World Java consumers ran on Java 8 and Java 21. The World and projection Kotlin consumers ran from staged JVM artifacts; the projection Kotlin consumer ran from Android host archives. |

The strict inventory's nonzero exit remains explicit.
Its added-member policy still reports bytecode methods with hyphens and members of private nested classes.
This branch does not change that policy.

The projection retains the exact required Java API.
Kotlin source still uses companion calls, enum `entries`, named constructors,
and the node properties against staged JVM and Android host archives.
No baseline JAR is a runtime dependency of the candidate.

## Qualification boundary

The Android archives were compiled and run on a host JVM.
This is not Android device execution.
The unchanged corpus, six available host lanes, staged consumers, strict API
audit, and remaining qualifications are recorded in the owner result report.
World list repairs and final integration remain separate work.
