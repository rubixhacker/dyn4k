# Immutable dyn4j baseline

Research for **Establish the immutable dyn4j 6.0.0 baseline**. Observed 2026-09-10 UTC. This records facts for the agreed independent fork, not API-design decisions.

## Pinned identity

[Maven Central metadata](https://repo.maven.apache.org/maven2/org/dyn4j/dyn4j/maven-metadata.xml) returned both `latest` and `release` = `6.0.0`, with `lastUpdated` = `20260718040113`. The selected coordinates are `org.dyn4j:dyn4j:6.0.0`. Metadata is mutable discovery evidence; the following hashes define the frozen inputs.

- Git annotated tag `6.0.0`: tag object `17df5075306d55b6435b866defaa1483a33188fc`.
- Peeled source commit: [`058bf6d982a0fb89b54050f929f6ea9dae53b714`](https://github.com/dyn4j/dyn4j/tree/058bf6d982a0fb89b54050f929f6ea9dae53b714).
- [Binary JAR](https://repo.maven.apache.org/maven2/org/dyn4j/dyn4j/6.0.0/dyn4j-6.0.0.jar), SHA-256 `204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e`.
- [Sources JAR](https://repo.maven.apache.org/maven2/org/dyn4j/dyn4j/6.0.0/dyn4j-6.0.0-sources.jar), SHA-256 `83b47be47bdce27681139dab84937e0f586b70ab800dc494fbebed4b58893223`.

Verification used `git ls-remote` for the tag and peeled tag, a shallow tag checkout, HTTPS downloads, and `sha256sum`. All **268 Java files** in the sources JAR byte-match their corresponding `src/main/java` files at the pinned commit; none were missing or different. This establishes the source-archive correspondence, not a reproducible-build or signature-verification claim. Running `java -jar dyn4j-6.0.0.jar` printed `dyn4j v6.0.0` and exited successfully. No master-branch source is used as baseline evidence.

## Package and test inventory

The [module descriptor](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/module-info.java) exports all 17 packages below. Counts are Java files at the pinned [source tree](https://github.com/dyn4j/dyn4j/tree/058bf6d982a0fb89b54050f929f6ea9dae53b714/src); they include package-info and internal classes and are **not** public API-type counts. Test counts include helpers.

| Package suffix after org.dyn4j | Main Java files | Test Java files |
|---|---:|---:|
| (root) | 14 | 6 |
| collision | 18 | 15 |
| collision.broadphase | 24 | 13 |
| collision.continuous | 4 | 2 |
| collision.manifold | 7 | 5 |
| collision.narrowphase | 27 | 17 |
| dynamics | 10 | 7 |
| dynamics.contact | 10 | 4 |
| dynamics.joint | 23 | 17 |
| exception | 9 | 1 |
| geometry | 37 | 26 |
| geometry.decompose | 21 | 4 |
| geometry.hull | 11 | 4 |
| geometry.simplify | 10 | 6 |
| world | 23 | 12 |
| world.listener | 14 | 1 |
| world.result | 5 | 1 |

One additional production Java file is `module-info.java`. Tests additionally include 46 `collision.shapes` files and 12 `simulation` files, for **199 test Java files and 2,171 textual `@Test` occurrences**. Parameterized tests mean annotations do not equal executed test cases. The [POM](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/pom.xml) declares JUnit 4.13.1 only in test scope and no production dependency. [Test resources](https://github.com/dyn4j/dyn4j/tree/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/resources/org/dyn4j/data) include polygon data fixtures; the tests are not exclusively self-contained methods. This inventory is not measured line/branch coverage or a claim that the upstream suite was executed.

## Public extension surfaces and portability findings

These are representative, concrete surfaces needing compatibility accounting, not an exhaustive member-signature manifest:

- [Collision package](https://github.com/dyn4j/dyn4j/tree/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/collision): generic `CollisionBody`, abstract bodies, fixtures, filters, bounds, pairs/items. Its subpackages expose pluggable broadphase detectors, AABB producers/expansion, narrowphase/distance/raycast detectors, manifold solvers, and time-of-impact detectors.
- [World package](https://github.com/dyn4j/dyn4j/tree/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/world): generic collision/physics worlds, abstract base worlds, collision-data interfaces, filters, results, and listeners for bounds/collisions/contacts/destruction/steps/time-of-impact.
- [Dynamics package](https://github.com/dyn4j/dyn4j/tree/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/dynamics): `PhysicsBody` and `AbstractPhysicsBody`; contact/time-of-impact solvers; joint interfaces, abstract joint bases, and motor/spring/limit capabilities.
- [Geometry package](https://github.com/dyn4j/dyn4j/tree/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/geometry): shape/convex/wound contracts, transform interfaces, decomposition/hull/simplification strategies, mutable vectors/matrices/transforms, robust geometry and adaptive decimal arithmetic. Root contracts include `Copyable`, `DataContainer`, `Ownable`, and tree/search interfaces.

A production import scan found only `java.util` imports outside dyn4j: array/deque/list/map/set/queue/priority-queue implementations, arrays/collections helpers, comparators/iterators, and iterator exceptions. Absence of external runtime dependencies does not mean mechanical common-Kotlin portability:

- [`TypeFilter`](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/collision/TypeFilter.java#L112) bases filtering on runtime class hierarchy checks (`Class.isInstance`), and includes class names in text output.
- [`Unsafe.copy`](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/Unsafe.java) checks exact runtime-class equality after copying; its documented extension rule requires subclasses to override copy. `CopyException` also receives Java class objects. These expose more than simple wrappers.
- [`AdaptiveDecimal`](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/geometry/AdaptiveDecimal.java) uses array copying, IEEE-double bit extraction, 64-bit masks and expansion arithmetic. Vectors/matrices/AABBs also use double bit conversion for hashing. Numerical behavior and integer/bit behavior both need verification, especially across JS/Wasm.
- [`AVLTree`](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/AVLTree.java) provides console printing with `String.format`; `Version.main` prints to `System.out`. Collection ordering, iterator mutation/error behavior, mutable references and numeric formatting are observable behavior, not only storage substitutions.
- The POM has a Java 9 module compile plus Java 6 recompilation excluding the module descriptor, and OSGi bundle packaging. Build/packaging compatibility is a separate factual surface from Java call signatures.
- Test imports additionally include Java I/O/resource loading, `BigDecimal`, `Random`, and output capture. Porting production code alone does not make all baseline tests portable.

**Inference:** the dependency footprint makes a shared implementation plausible, but subclassing, class-based filters, copying, collections and floating-point semantics require explicit design/prototype evidence before asserting that the shim is thin and complete.

## License and attribution facts

The pinned [LICENSE.md](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/LICENSE.md) identifies copyright 2010–2026 William Bittle; the POM labels the license BSD-3. Its conditions require source redistributions to retain the copyright notice, conditions and disclaimer; binary redistributions to reproduce them in supplied documentation/materials; and prohibit using the copyright holder/contributor names for endorsement without prior written permission. Modifications are permitted under those conditions. These are a factual summary of the baseline text, not a legal opinion.

Individual source headers contain their own year ranges and should not be overwritten by a single blanket year. [`RobustGeometry`](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/main/java/org/dyn4j/geometry/RobustGeometry.java#L127) and `AdaptiveDecimal` credit Jonathan Richard Shewchuk's work; preserve those provenance references when translating corresponding algorithms. This bounded inspection is not an exhaustive third-party provenance audit.

## Remaining factual limits

No full public/protected member manifest, Java consumer compilation corpus, upstream test execution/coverage report, artifact signature validation, or reproducible binary build was produced. The immutable source/artifacts and package/test inventory answer the baseline question; compatibility prototypes and acceptance design must establish the stronger claims. SHA-256s here are locally calculated integrity pins from the downloaded artifacts, not separately authenticated publisher checksums.
