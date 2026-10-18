# Portable shape-pair corpus A

This corpus maps the 109 executed dyn4j 6.0.0 shape-pair cases whose concrete class begins Capsule, Circle, Ellipse, HalfEllipse, or Polygon. It is part of [Run the full compatibility corpus and unchanged migration applications](https://github.com/rubixhacker/dyn4k/issues/42). The initial engine and target qualification remain open.

## Scope and source

The source is dyn4j revision `058bf6d982a0fb89b54050f929f6ea9dae53b714`. The baseline Java 8 log at `/tmp/dyn4k-full-java-probe/baseline-jdk8.log` identifies exactly 109 methods in 26 concrete classes. [AbstractNarrowphaseShapeTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/collision/shapes/AbstractNarrowphaseShapeTest.java) defines the SAT, GJK, and clipping solver fixtures; it has no runnable case. Each common Kotlin method creates those fixtures and invokes the original setup before its assertions.

The translation retains all 2,767 original assertion calls. It keeps the source shape inputs, transform sequence, detector overloads, normal signs, distance points, penetration depths, manifold points, and clipping depths. Numeric tolerance comparisons additionally reject non-finite expected, actual, or tolerance values. The exact circle-circle assertions provide independent geometry checks: two centered circles of radii 1.0 and 0.5 overlap by 1.5; translating one by 1.0 reduces depth to 0.5 and fixes the normal direction. The upstream copyright and license notice is retained in each translated class.

| Pinned source | Cases | Provisional failures | Source SHA-256 |
| --- | ---: | --- | --- |
| [CapsuleCapsuleTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/collision/shapes/CapsuleCapsuleTest.java) | 4 | none | `d4b6ccf054cffcfb802a253420daac4cf85c71a8354788569bd71093c08cc0ba` |
| [CapsuleSliceTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/collision/shapes/CapsuleSliceTest.java) | 4 | detectGjk, getClipManifold | `59a4f4c9ee1d944a15d42ce3bd7d940f04d8d61fc8a1cfd9a9dae3ced52ea20b` |
| [CircleCapsuleTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/collision/shapes/CircleCapsuleTest.java) | 4 | none | `7e0dc34029a51f1ab70ca8ec7e7f6cd59df80ce6c27b7c1b27152fe3e8a04f34` |
| [CircleCircleTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/collision/shapes/CircleCircleTest.java) | 4 | none | `9a1a7ba03d91f29cf2ea2f9d08397172f12443437322359951320970c14c1069` |
| [CircleEllipseTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/collision/shapes/CircleEllipseTest.java) | 4 | none | `a60d7374ae330035376848cc745f2d502f45ebfb96e3347e2a3806dc06b0045b` |
| [CircleHalfEllipseTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/collision/shapes/CircleHalfEllipseTest.java) | 4 | none | `6a916973fd321fe3043b3de45cfe68a4fd9deb0e0653b2cdfcf2bbd7207bc729` |
| [CirclePolygonTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/collision/shapes/CirclePolygonTest.java) | 4 | detectGjk | `c7ff91e8607bee0bd8f77325d4fdd5dace91855b193b0c1773b0b5c533bdb480` |
| [CircleRectangleTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/collision/shapes/CircleRectangleTest.java) | 4 | none | `fae101a691acceea7316acd22bfb921af21c745e2bf77b896aae7480cdf4d890` |
| [CircleSegmentTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/collision/shapes/CircleSegmentTest.java) | 4 | detectGjk | `d7962c20641a7622000870e49677392aa7e70b4377dbdc4232ca7e64636e12a8` |
| [CircleSliceTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/collision/shapes/CircleSliceTest.java) | 4 | detectGjk | `b072773a8b4433fb70e77355bbe7b770879fde3e0c216a84a35499d84aa0b268` |
| [CircleTriangleTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/collision/shapes/CircleTriangleTest.java) | 4 | none | `371b7ffbbeb1b855e27b62b6c77a9e43e1d53a0fed30d0694da8fc69452cab91` |
| [EllipseCapsuleTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/collision/shapes/EllipseCapsuleTest.java) | 4 | detectGjk | `f2a3a642b673d5b13d3d6ce6ced07df280fe52f69808a4c61bf893c847bc9eb8` |
| [EllipseEllipseTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/collision/shapes/EllipseEllipseTest.java) | 6 | detectGjk | `ab127b0ef39aad87fa89fab85a01ae713727632b5dfea71f2d3ff9e80c6845f5` |
| [EllipseHalfEllipseTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/collision/shapes/EllipseHalfEllipseTest.java) | 4 | none | `193ff6003d7fca7b7140f4d85c9a2057e95825d1be293d2b023cb357166956cd` |
| [EllipseSliceTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/collision/shapes/EllipseSliceTest.java) | 4 | none | `fda981587baf54265328b3b00f47e2daa831cbf8f2e85d3fafadec1927ad2b5d` |
| [HalfEllipseCapsuleTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/collision/shapes/HalfEllipseCapsuleTest.java) | 4 | none | `33b27d6526940a2f457cacd8c7a874f62127b83e12e26de6caa99b477dcac792` |
| [HalfEllipseHalfEllipseTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/collision/shapes/HalfEllipseHalfEllipseTest.java) | 4 | none | `526bc4c357ba661d1ccbe7ad5d7cf3aff29d16a783534e4eb8f495353a84ad19` |
| [HalfEllipseSliceTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/collision/shapes/HalfEllipseSliceTest.java) | 4 | none | `f03442db6243663623df91ad842918634e021685207b051bd274c41324953764` |
| [PolygonCapsuleTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/collision/shapes/PolygonCapsuleTest.java) | 4 | detectSat, getClipManifold | `5ce612a1062e0c51c13a2478dbf8cf2a89a1be3e4819d1b8d88981e1141e02a7` |
| [PolygonEllipseTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/collision/shapes/PolygonEllipseTest.java) | 4 | none | `0d35e1bbdd6857bced40d606f64a787c0cc4eaeb21c654c05f066ba3cf9b9ad1` |
| [PolygonHalfEllipseTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/collision/shapes/PolygonHalfEllipseTest.java) | 4 | none | `2d1739b93294a63a2b95025ab5483822762989ab8684542f8c267a8132ce4c86` |
| [PolygonPolygonTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/collision/shapes/PolygonPolygonTest.java) | 4 | detectSat, getClipManifold | `0911c054a8631b34dcc1fd7f9c3eed9c379a3c46652d76345e0973a923efe60a` |
| [PolygonRectangleTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/collision/shapes/PolygonRectangleTest.java) | 5 | none | `bd923959a7d01139dda93affa73d96e7906348760b29c342424315619bf88ed7` |
| [PolygonSegmentTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/collision/shapes/PolygonSegmentTest.java) | 6 | detectGjk, detectSat, getClipManifold | `de68765c4dc48cc5c5d9b8f9fa1c59a78bfb376ec4ebe4604e5321929450785f` |
| [PolygonSliceTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/collision/shapes/PolygonSliceTest.java) | 4 | detectGjk, detectSat, getClipManifold | `24d859d1a22ccf3d42908008729c241b39e1446adec2e4931b3b2f845997c7cd` |
| [PolygonTriangleTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/collision/shapes/PolygonTriangleTest.java) | 4 | none | `4f5ae68df014f077a10c3f1bfb9935b03cad56006a5012e5e9ac2876aec3ca37` |

## Unchanged Java oracle

The 26 pinned concrete files and their abstract fixture were compiled with JDK 21 `--release 8` against each provider separately. The runner `/tmp/dyn4k-full-java-probe/CorpusReport.java` executed the same 109 methods on Java 8 and Java 21. Candidate means the JAR built from the starting worktree at `dff7bf878db7e009799007f37a5f1af8f9a3b3c5`, SHA-256 `92ff4bd062752ae572c6947b75a929c69c7651676321e1b88bb96aeb49427699`. The candidate classpath excludes dyn4j. Raw logs and per-case failure traces are in `/tmp/dyn4k-shape-a-java/`.

| Provider | Runtime | Raw summary | Log SHA-256 |
| --- | --- | --- | --- |
| baseline | Java 8 | ACTUAL_TESTS=109; FAILURES=0; IGNORED=0 | `34763d46af7803f1dbaf7c7fba5d60018f65c108d35632bbfc37abc15d594bbb` |
| baseline | Java 21 | ACTUAL_TESTS=109; FAILURES=0; IGNORED=0 | `34763d46af7803f1dbaf7c7fba5d60018f65c108d35632bbfc37abc15d594bbb` |
| candidate | Java 8 | ACTUAL_TESTS=109; FAILURES=17; IGNORED=0 | `dc50f89ed6ded3c167a5ec29b7f898fd5d4030bb97fc917ba1c8abe86248e764` |
| candidate | Java 21 | ACTUAL_TESTS=109; FAILURES=17; IGNORED=0 | `92419978d16bec79522c49656f99a5d42babeea860295eee2e09502ba22a34cb` |

The baseline has no failure or ignored case. The candidate has the 17 failures listed in the source table on both runtimes. The full 187-case shape-pair package has one further candidate failure, `RectangleRectangleTest.detectGjk`, outside this corpus.

## Common Kotlin execution

The six available host tasks executed exactly the 109 mapped identities, with zero unexpected identities and zero skips. Every host has 92 passes and 17 failures. The failing identities match the unchanged Java candidate on both JDKs. Raw XML for all 156 class/host reports, their individual SHA-256 hashes, and the per-case dispositions are in `/tmp/dyn4k-shape-a-xml/`. The Android host task runs on the host JVM; it is not an Android device result.

| Gradle task | Mapped cases | Pass | Fail | Skip |
| --- | ---: | ---: | ---: | ---: |
| `:dyn4k-core:jvmTest` | 109 | 92 | 17 | 0 |
| `:dyn4k-core:linuxX64Test` | 109 | 92 | 17 | 0 |
| `:dyn4k-core:jsNodeTest` | 109 | 92 | 17 | 0 |
| `:dyn4k-core:wasmJsNodeTest` | 109 | 92 | 17 | 0 |
| `:dyn4k-core:wasmWasiNodeTest` | 109 | 92 | 17 | 0 |
| `:dyn4k-core:testAndroidHostTest` | 109 | 92 | 17 | 0 |

The relevant provisional engine differences are Vector2 normalization order and simplex queue tie behavior. These cases remain red until common Kotlin engine changes pass the unchanged Java oracle and common tests. No tolerance was widened and no case was skipped or moved to JVM-only code.

A controlled wrong-value check changed the first `CircleCircleTest.detectGjk` depth expectation from 1.5 to 9.5. That previously passing case failed with actual depth 1.5. The expectation was restored, and the 109-case JVM run returned to 92 passes, 17 failures, zero skips. The transient log is `/tmp/dyn4k-shape-a-wrong-value.log`; the restored run is `/tmp/dyn4k-shape-a-jvm-restored.log`.

## Open gates

This corpus does not qualify the engine or all 21 approved targets. The engine owners must land the common Kotlin normalization and simplex fixes and rerun the unchanged source corpus. Device and other target/configuration runs, staged consumers, physical and numerical acceptance, and final integration review remain open.
