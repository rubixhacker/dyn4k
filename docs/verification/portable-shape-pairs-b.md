# Portable shape-pair corpus: rectangle through triangle

This report covers the 78 expanded cases in 19 concrete `org.dyn4j.collision.shapes` classes whose names begin `Rectangle`, `Segment`, `Slice`, or `Triangle`. It contributes to [Run the full compatibility corpus and unchanged migration applications](https://github.com/rubixhacker/dyn4k/issues/42). That ticket and full target qualification remain open.

## Source and test contract

- Pinned dyn4j source: `058bf6d982a0fb89b54050f929f6ea9dae53b714`. The 19 Java classes plus `AbstractNarrowphaseShapeTest.java` have concatenated source SHA-256 `ddcd4d1cdcc4a8dcc183f113ecf19c41ca2709c74c39b49adaaa7088fcaf4b47` in sorted order with the helper first. The SHA-256 of the sorted `<file hash>  <basename>\n` manifest is `e03d7aee79be05029c445b78bf507910e5a8dc1b082983026cb107e7d298c882`.
- The abstract helper has no runnable JUnit case. Its SAT, GJK, and clipping solver fixtures are common Kotlin fields in `AbstractNarrowphaseShapeTest.kt`.
- Each common method uses the original shape constructors, transform sequence, detector calls, normal direction, depth, separation and contact coordinates, point count, and clip assertions. The six unsupported SAT cases still assert `UnsupportedOperationException`. `assertClose` retains each source tolerance and rejects nonfinite values first. The triangle NaN regression case now rejects infinities too.
- All 78 original method identities appear once under `org.dyn4j.coverage.collision.shapes.b` on each host. The SHA-256 of their sorted `Class.method\n` manifest is `171ea323ed580d77073fca135db01dcda8e83c4f68c381a9d22bd05796b38750`. Source and Kotlin assertion counts agree for each class. The only four assertion substitutions are the stronger finite checks in `TriangleTriangleTest.distanceNotFound`.
- The upstream copyright and license notice remains in each translated file.

| Source class | Mapped methods | Cases | Current common result on each host |
| --- | --- | ---: | --- |
| RectangleCapsuleTest | detectSat, detectGjk, gjkDistance, getClipManifold | 4 | 4 pass |
| RectangleEllipseTest | detectSat, detectGjk, gjkDistance, getClipManifold | 4 | 4 pass |
| RectangleHalfEllipseTest | detectSat, detectGjk, gjkDistance, getClipManifold | 4 | 4 pass |
| RectangleRectangleTest | detectSat, detectGjk, gjkDistance, getClipManifold | 4 | 3 pass; detectGjk fails |
| RectangleSegmentTest | detectSat, detectGjk, gjkDistance, getClipManifold | 4 | 4 pass |
| RectangleSliceTest | detectSat, detectGjk, gjkDistance, getClipManifold | 4 | 4 pass |
| RectangleTriangleTest | detectSat, detectGjk, gjkDistance, getClipManifold, distanceFail1 | 5 | 5 pass |
| SegmentCapsuleTest | detectSat, detectGjk, gjkDistance, getClipManifold | 4 | 4 pass |
| SegmentEllipseTest | detectSat, detectGjk, gjkDistance, getClipManifold | 4 | 4 pass |
| SegmentHalfEllipseTest | detectSat, detectGjk, gjkDistance, getClipManifold | 4 | 4 pass |
| SegmentSegmentTest | detectSat, detectGjk, gjkDistance | 3 | 3 pass |
| SegmentSliceTest | detectSat, detectGjk, gjkDistance, getClipManifold | 4 | 4 pass |
| SegmentTriangleTest | detectSat, detectGjk, gjkDistance, getClipManifold | 4 | 4 pass |
| SliceSliceTest | detectSat, detectGjk, gjkDistance, getClipManifold | 4 | 4 pass |
| TriangleCapsuleTest | detectSat, detectGjk, gjkDistance, getClipManifold | 4 | 4 pass |
| TriangleEllipseTest | detectSat, detectGjk, gjkDistance, getClipManifold | 4 | 4 pass |
| TriangleHalfEllipseTest | detectSat, detectGjk, gjkDistance, getClipManifold | 4 | 4 pass |
| TriangleSliceTest | detectSat, detectGjk, gjkDistance, getClipManifold | 4 | 4 pass |
| TriangleTriangleTest | detectSat, detectGjk, gjkDistance, getClipManifold, distanceNotFound, falsePenetration1 | 6 | 6 pass |

## Observed execution

The original 78 Java cases passed on the pinned baseline under both Java 8 and Java 21: 78 executed, zero failures, zero ignored on each runtime. The same sources compiled unchanged with `javac --release 8` against this checkout's candidate JAR, SHA-256 `92ff4bd062752ae572c6947b75a929c69c7651676321e1b88bb96aeb49427699`. They executed 78 cases on both runtimes with one failure and zero ignored: `RectangleRectangleTest.detectGjk` expected the containment normal x coordinate `-1.0`, but the candidate returned `1.0`. The baseline JAR SHA-256 is `204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e`.

The common suite ran with:

```sh
ANDROID_HOME=/home/stewart/Android/Sdk ./gradlew --no-daemon --continue --console=plain \
  :dyn4k-core:jvmTest :dyn4k-core:linuxX64Test :dyn4k-core:jsNodeTest \
  :dyn4k-core:wasmJsNodeTest :dyn4k-core:wasmWasiNodeTest \
  :dyn4k-core:testAndroidHostTest
```

Each host executed all 78 new cases with one failure, zero errors, and zero skips. The full module suite executed 399 cases per host with the same one failure. The failed common identity is `RectangleRectangleTest.detectGjk` on every host. The raw 19 XML files per host are preserved under `/tmp/dyn4k-shape-pairs-b-xml/<task>/`. Each digest hashes the concatenation of those files in sorted filename order.

| Task | New cases | Failed | Errors | Skipped | Raw XML SHA-256 |
| --- | ---: | ---: | ---: | ---: | --- |
| `jvmTest` | 78 | 1 | 0 | 0 | `cc40bc38b35d135abfb39c1a7825961a83a43b90c53de1ef1831ecd9391f757a` |
| `linuxX64Test` | 78 | 1 | 0 | 0 | `dd88465ea323be8958250d24babbe98304a1268fdd1cf0a0c9cd47d203d30cae` |
| `testAndroidHostTest` | 78 | 1 | 0 | 0 | `cd6c357615692372ef67132c3ef9dbcb4336fe1d16492dfa98571ef7bf65e057` |
| `jsNodeTest` | 78 | 1 | 0 | 0 | `1a3b45e8dadc3aa448e8ece7fd29cc46821dd2721f2617b7d62d8608408e6505` |
| `wasmJsNodeTest` | 78 | 1 | 0 | 0 | `572ac3e3599a27be8156ce55a3b2db4ec8b6207a7f959ca706b9e444a99901e5` |
| `wasmWasiNodeTest` | 78 | 1 | 0 | 0 | `034eb6921f2a9509389c458753c8efd3060d156d872a0ea894d43bb0826e248d` |

The six-host command log is `/tmp/dyn4k-shape-pairs-b-six-host-final.log`, SHA-256 `c8fd2fbd83edd05850825bf2b8b03b8f9b3f8f7b8c821210a94ebc82ad18238d`. Exact Java commands, all case dispositions, and log hashes are in `/tmp/dyn4k-coverage-shape-pairs-b-result.md`.

## Assertion sensitivity and open gates

Changing the first `RectangleRectangleTest.detectSat` depth expectation from `0.750` to `9.750` made its isolated JVM run fail. Restoring `0.750` returned the file to SHA-256 `47055bade886603a51fa370d99861fca39fa605044a356beef5a2b493d4bc484`, and the same isolated run passed. The final source differs only in license whitespace and has SHA-256 `626f383f47003c9c3f2ce314ce3ecda585416ce8eb6d7d2e71c8978561b0d817`. Logs are `/tmp/dyn4k-shape-pairs-b-wrong-value.log` and `/tmp/dyn4k-shape-pairs-b-restored-control.log`.

The one red case remains a common assertion. The separate Vector2 normalization and simplex queue source repairs must land in the engine before it can pass. This report does not qualify the remaining approved targets, both build configurations, staged consumers, physical checks, or release. An Android host test is not Android device execution.
