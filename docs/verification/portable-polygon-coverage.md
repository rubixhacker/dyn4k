# Portable polygon compatibility corpus

This report covers the hull, decomposition, and simplification tests in the pinned dyn4j 6.0.0 source. It is a bounded part of [Run the full compatibility corpus and unchanged migration applications](https://github.com/rubixhacker/dyn4k/issues/42). The issue and full 21-target qualification remain open.

## Source and execution boundary

- Active worker model: `gpt-6-sol`, verified in session `01a14b35-7b2c-7151-a65f-13949e02b0b7` from its `turn_context`.
- Upstream source revision: `058bf6d982a0fb89b54050f929f6ea9dae53b714`; baseline binary SHA-256: `204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e`.
- Branch: `codex/port-coverage-polygon`. Starting integration: `dc536f6237f5150869764856ce7ac33658ddcadc`. Provisional polygon implementation: `a4585acb16bda9bd7154acfe4db20abcf2e2e192`. Latest incorporated integration on this draft: `446b0b122792afe52a17983793d943f0b5959584`. Final reviewed integration binding remains pending.
- The 12 executable upstream classes have 290 `@Test` methods and JUnit executes 290 cases. The two abstract fixture helpers have no cases.
- Common Kotlin has 284 named cases. Six original null-array calls are JVM-only; unchanged Java JUnit executes those six against the candidate.
- These are common tests run on six host configurations. They do not qualify the 21 approved targets or the full compatibility issue.

The public seams are `HullGenerator.generate`, `Decomposer.decompose`, `Triangulator.triangulate`, and `Simplifier.simplify`. The three package-visible support cases retain their upstream package so Android host observes the Java visibility contract. No production algorithm or build registration was changed by this corpus worker.

## Observations and limits

The unchanged baseline Java suite passed 290/290 using the pinned binary. The candidate unchanged Java suite passed 290/290 on the provisional polygon source. A common JVM run executed 284 cases with 283 passes and one failure: `SimplePolygonVertexTest.create` reads a newly constructed vertex's `next`, `nextSegment`, `prev`, and `prevSegment` as null on baseline. The port's `lateinit` properties throw `UninitializedPropertyAccessException`. The test retains the original assertion; production repair belongs to the polygon owner. The final six-host verification is pending reviewed integration and that repair.

The common success checks preserve the original count or exception assertions. Hull cases also validate winding through `Polygon`, robust point containment, seeded Java-compatible random clouds, array/list output identity, and source point identity. Decomposition cases check convex piece construction, orientation within double precision, triangulation counts, and input versus combined area. Simplification checks exact expected vertex counts, null/list behavior, input order, point identity, and empty mutable-list aliasing.

The pinned `nsoft1.dat` polygon is degenerate. A separate baseline area probe measured input shoelace area `18.08387899963746` square units and Bayazit output area `18.60476525953471` square units, with a zero-area piece. The candidate produced the same values. Area conservation is **failed physical evidence** for that scenario; its original nonthrow and piece-count case still executes. For `zoom7.dat`, pinned SweepLine triangulation produced a minimum signed triangle area of `-2.2737367544323206E-13` square units from rounding, with total area equal to input. Orientation uses a `max(1e-9, input area × 1e-12)` square-unit negative tolerance; total area uses `max(1e-7, input area × 1e-7)`. These added bounds do not widen an upstream assertion.

The frozen `core-*` qualification manifest expects zero new cases. Registering this corpus in a combined qualification manifest is a later integration dependency. No manifest edit or full-target qualification is claimed here.

## Exact commands and raw reports

Baseline Java JUnit, with unchanged pinned test sources and the verified baseline binary:

```sh
javac --release 8 -cp "$baseline_jar:$junit_jar:$hamcrest_jar" -d /tmp/dyn4k-polygon-baseline/classes \
  /tmp/dyn4k-upstream-6.0.0/src/test/java/org/dyn4j/geometry/RobustGeometryTest.java \
  /tmp/dyn4k-upstream-6.0.0/src/test/java/org/dyn4j/geometry/{hull,decompose,simplify}/*.java
java -cp "/tmp/dyn4k-polygon-baseline/classes:$baseline_jar:$junit_jar:$hamcrest_jar:/tmp/dyn4k-upstream-6.0.0/src/test/resources" \
  org.junit.runner.JUnitCore \
  org.dyn4j.geometry.hull.{DivideAndConquerTest,GiftWrapTest,GrahamScanTest,MonotoneChainTest} \
  org.dyn4j.geometry.decompose.{BayazitTest,EarClippingTest,SweepLineTest} \
  org.dyn4j.geometry.simplify.{DouglasPeuckerTest,SegmentTreeTest,SimplePolygonVertexTest,VertexClusterReductionTest,VisvalingamTest}
```

Baseline stdout: `/tmp/dyn4k-polygon-baseline/junit.log`, SHA-256 `c654f3db1bbb204b7751df2267d0a97611b109e64070a3c4bc2e5df52605c4b1`; result `OK (290 tests)`.

Candidate unchanged Java command: `./gradlew --no-daemon :dyn4k-core:runUpstreamPolygonTests`; provisional result `OK (290 tests)`. Final raw log hash remains pending.

Portable command:

```sh
ANDROID_HOME=/home/stewart/Android/Sdk ./gradlew --no-daemon --continue --console=plain \
  :dyn4k-core:jvmTest :dyn4k-core:linuxX64Test :dyn4k-core:jsNodeTest \
  :dyn4k-core:wasmJsNodeTest :dyn4k-core:wasmWasiNodeTest \
  :dyn4k-core:testAndroidHostTest
```

The expected per-host polygon count is 284 (71 hull + 128 decomposition + 82 simplification + 3 support). The corrected diagnostic run executed 284 on each host, with one failure and zero skips per host. Its sole failed identity was `SimplePolygonVertexTest.create`. The source received later license whitespace and fixture count edits, so this is not final source-bound evidence. Gradle report locations are `dyn4k-core/build/test-results/<task>/TEST-*.xml`.

The raw report digest below hashes the concatenation of four sorted XML report byte streams per task. The command log is `/tmp/dyn4k-polygon-six-host-current.log`.

| Task | Executed | Failed | Errors | Skipped | Raw XML SHA-256 |
| --- | ---: | ---: | ---: | ---: | --- |
| `jvmTest` | 284 | 1 | 0 | 0 | `a33e965b1610eb1c0f424b9d7ba2a90b79120e1e6a3a2bb4f7e9ceb39a921f18` |
| `linuxX64Test` | 284 | 1 | 0 | 0 | `add216a8394da68bfc8cfbdaeffb764e1fbfbc27da2c13b8a46ad6074b0cd692` |
| `jsNodeTest` | 284 | 1 | 0 | 0 | `0bf2ca28f29b55a36ab333a5d1a4260283d7ccc33d803b212dd70384ab06a58f` |
| `wasmJsNodeTest` | 284 | 1 | 0 | 0 | `42ba8758403e7983322310326354de5a1460f4ccef00e286214ae76aad500020` |
| `wasmWasiNodeTest` | 284 | 1 | 0 | 0 | `ab8b1dc6429ce975ee24ee649ab0f38644542f2b548cf976cd91c2dbb874ea39` |
| `testAndroidHostTest` | 284 | 1 | 0 | 0 | `37804c515294c66e3cd6f29ce51feb020f601360345a96d33598854f0c77ac2a` |

Final zero-failure source-bound results and report hashes remain pending reviewed integration and the engine fix.

## Pinned source files

| Upstream test file | Executed identities | SHA-256 |
| --- | ---: | --- |
| [hull/DivideAndConquerTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/geometry/hull/DivideAndConquerTest.java) | 18 | `bb482c6303e59f755b146684f1b56d115a802aea18e2f3fb76e5de96f06a75d5` |
| [hull/GiftWrapTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/geometry/hull/GiftWrapTest.java) | 17 | `a9986fbfd527213dcb0f5127b3f105c21e27ff68e0194fa63377947d6fc33c7e` |
| [hull/GrahamScanTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/geometry/hull/GrahamScanTest.java) | 18 | `dd62d1cc29dab2fe15decc0486ff58766b49f0ccef1d7a6628eb88ea6d10de66` |
| [hull/MonotoneChainTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/geometry/hull/MonotoneChainTest.java) | 18 | `912e35b620b01f7453ddda93f495fb7c4c0c970aa2e2ddd509bb0110ca0fa93c` |
| [decompose/AbstractDecomposeTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/geometry/decompose/AbstractDecomposeTest.java) | 0 | `039d92f30a4d93153455d835bbbdcde85120832ef19dcb8f2b8c30d72e500112` |
| [decompose/BayazitTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/geometry/decompose/BayazitTest.java) | 31 | `b57eace20c3f525bb31ced51e9241f5ca7e5cc49fecbc56bbcb6bd59933bc65f` |
| [decompose/EarClippingTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/geometry/decompose/EarClippingTest.java) | 50 | `8eeb242375c0090b05d06db01099ef7d88e708698c60352fb2158e7300668f7d` |
| [decompose/SweepLineTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/geometry/decompose/SweepLineTest.java) | 50 | `752e354eb02b837f1e64c931ef4c23a2d93165fe08633d9630e34bf390d57b21` |
| [simplify/AbstractSimplifyTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/geometry/simplify/AbstractSimplifyTest.java) | 0 | `beacd98e7e97de5bc5881d7fc8b893f4dc314dcb23e443d2a343f471ee9b1b03` |
| [simplify/DouglasPeuckerTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/geometry/simplify/DouglasPeuckerTest.java) | 29 | `cfd131683b15abfe84fdb09699700831d5057244c7a4ef401155e4df96b52642` |
| [simplify/SegmentTreeTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/geometry/simplify/SegmentTreeTest.java) | 2 | `d1ae939746eb9af8ccbf783e4e75401157c436517cdfb42c791ba1ee061b1255` |
| [simplify/SimplePolygonVertexTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/geometry/simplify/SimplePolygonVertexTest.java) | 1 | `bae2569c61e273a06e2da73abdfb0cfed773766bdc140aaa358dae56fc5f123d` |
| [simplify/VertexClusterReductionTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/geometry/simplify/VertexClusterReductionTest.java) | 27 | `1f3aa5e13141cb7bf131c6a896797f130e16e3b5f74845ab937bda94bf9d5132` |
| [simplify/VisvalingamTest.java](https://github.com/dyn4j/dyn4j/blob/058bf6d982a0fb89b54050f929f6ea9dae53b714/src/test/java/org/dyn4j/geometry/simplify/VisvalingamTest.java) | 29 | `315beba9d192e2032daf944a4629247b9b1483af0512ae1157b058a89c9c78b9` |

## Byte-identical polygon inputs

The following CRLF fixture bytes were copied into `dyn4k-core/src/commonTest/kotlin/org/dyn4j/coverage/geometry/algorithms/fixtures/`. `PolygonFixtures.kt` embeds their numeric point sequences for common runtimes without filesystem APIs. A byte comparison against the pinned upstream checkout is required at final verification.

| Fixture | SHA-256 |
| --- | --- |
| `bird.dat` | `cddbac80cbc29ef2948a531d9e904e5d99d31440cbfaff04369562b0c89385dd` |
| `nazca_heron.dat` | `824bbcdb1ef45e6a101fcb17978f3969d36de3ca2456ae17ad7432ec497b5f1c` |
| `nazca_monkey.dat` | `fa80d1a272227a518d3a954e8fe678339009c0144e97a47b9b795b483ac7f178` |
| `nsoft1.dat` | `8c6dcc6820ac1a31bb5719c4db182d9367f5f88d95b9354491fc8057506ae7d2` |
| `polygon1.dat` | `201ff1d03654adbf6768974232e98cd72f2fc340dcf8a372097c08b69109b932` |
| `polygon2.dat` | `4d666da368b7f2cfa2660d3a3b50e9308f8740c682b870f60e08bbaf5e0cf831` |
| `polygon3.dat` | `6f90d4dff52c5f9d1de1341b757c9c6d1948bdb847272d40b243e66a8276e004` |
| `polygon4.dat` | `b9dc2a5490540b2f9c2812d5e2dcc536d8cfa4828246958287a84171ebc87c14` |
| `tank.dat` | `299e1c74cddcba3c9fd790a3b2adc0fe45329a561140be705e70a4898047a29f` |
| `tridol1.dat` | `334649a478281534d4e68f6b219874e191bb27f3a68dc2d70c394f1ceff5e0be` |
| `tridol2.dat` | `8da18592635ad25eae013ba3f1d514e3070260f1284f4ccffd40befbd026b5b8` |
| `tridol3.dat` | `dc799b215f11ffbe6d169663521596873a5b084af6e1c108e9808e01fd8665e3` |
| `zoom1.dat` | `5422771a3a327181ecfba1e7f40e9af175cacf16bf52169bbe19dd5b4759914d` |
| `zoom2.dat` | `bd741b3306aa928b8b91dba0e89f7ea2051876a298f32ec8001cc52e9d69b853` |
| `zoom3.dat` | `8afbc3dccec18638d00bc099fb9308fce13681175f59cbacdd2786a1af4837eb` |
| `zoom4.dat` | `da85cd1b6d70f97dad8af73f64abf17df615ce7c31c7fa1c19d87b6339583f38` |
| `zoom5.dat` | `f0fc24e0040222cda9bf69c489d30a9e8ecfeedee2febf72d99eb639fbf03ef5` |
| `zoom6.dat` | `0299d1492e4241527b39fe8d497e03dde63f459d5c7b9a1fb37eec766b51703b` |
| `zoom7.dat` | `6005a820a1451a901bc5b7c083b5c386189f92c0bae3c692b114343809afa010` |

## Identity map

Each row names one original JUnit execution. A common destination is one named `@Test` function. JVM-only means an original Java call with a null vararg array; Kotlin common cannot express a null vararg container, but the unchanged Java case runs on JVM. The other null elements, null list, exception, randomized, resource, and algorithm cases remain common.

| Original `org.dyn4j.geometry` identity | Destination or disposition |
| --- | --- |
| `org.dyn4j.geometry.hull.DivideAndConquerTest.dacRandom1` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.dacRandom1` |
| `org.dyn4j.geometry.hull.DivideAndConquerTest.dacRandom2` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.dacRandom2` |
| `org.dyn4j.geometry.hull.DivideAndConquerTest.dac22` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.dac22` |
| `org.dyn4j.geometry.hull.DivideAndConquerTest.dac2` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.dac2` |
| `org.dyn4j.geometry.hull.DivideAndConquerTest.dac3` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.dac3` |
| `org.dyn4j.geometry.hull.DivideAndConquerTest.dac4` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.dac4` |
| `org.dyn4j.geometry.hull.DivideAndConquerTest.dac6` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.dac6` |
| `org.dyn4j.geometry.hull.DivideAndConquerTest.dac7` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.dac7` |
| `org.dyn4j.geometry.hull.DivideAndConquerTest.dac5` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.dac5` |
| `org.dyn4j.geometry.hull.DivideAndConquerTest.dac5Part2` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.dac5Part2` |
| `org.dyn4j.geometry.hull.DivideAndConquerTest.dac5Part3` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.dac5Part3` |
| `org.dyn4j.geometry.hull.DivideAndConquerTest.dac8` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.dac8` |
| `org.dyn4j.geometry.hull.DivideAndConquerTest.dac9` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.dac9` |
| `org.dyn4j.geometry.hull.DivideAndConquerTest.dac10` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.dac10` |
| `org.dyn4j.geometry.hull.DivideAndConquerTest.dac11` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.dac11` |
| `org.dyn4j.geometry.hull.DivideAndConquerTest.dac12` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.dac12` |
| `org.dyn4j.geometry.hull.DivideAndConquerTest.dac13` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.dac13` |
| `org.dyn4j.geometry.hull.DivideAndConquerTest.dac14` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.dac14` |
| `org.dyn4j.geometry.hull.GiftWrapTest.giftWrapRandom1` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.giftWrapRandom1` |
| `org.dyn4j.geometry.hull.GiftWrapTest.giftWrapRandom2` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.giftWrapRandom2` |
| `org.dyn4j.geometry.hull.GiftWrapTest.giftWrap2` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.giftWrap2` |
| `org.dyn4j.geometry.hull.GiftWrapTest.giftWrap3` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.giftWrap3` |
| `org.dyn4j.geometry.hull.GiftWrapTest.giftWrap4` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.giftWrap4` |
| `org.dyn4j.geometry.hull.GiftWrapTest.giftWrap6` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.giftWrap6` |
| `org.dyn4j.geometry.hull.GiftWrapTest.giftWrap7` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.giftWrap7` |
| `org.dyn4j.geometry.hull.GiftWrapTest.giftWrap5` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.giftWrap5` |
| `org.dyn4j.geometry.hull.GiftWrapTest.giftWrap5Part2` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.giftWrap5Part2` |
| `org.dyn4j.geometry.hull.GiftWrapTest.giftWrap5Part3` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.giftWrap5Part3` |
| `org.dyn4j.geometry.hull.GiftWrapTest.giftWrap8` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.giftWrap8` |
| `org.dyn4j.geometry.hull.GiftWrapTest.giftWrap9` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.giftWrap9` |
| `org.dyn4j.geometry.hull.GiftWrapTest.giftWrap10` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.giftWrap10` |
| `org.dyn4j.geometry.hull.GiftWrapTest.giftWrap11` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.giftWrap11` |
| `org.dyn4j.geometry.hull.GiftWrapTest.giftWrap12` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.giftWrap12` |
| `org.dyn4j.geometry.hull.GiftWrapTest.giftWrap13` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.giftWrap13` |
| `org.dyn4j.geometry.hull.GiftWrapTest.giftWrap14` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.giftWrap14` |
| `org.dyn4j.geometry.hull.GrahamScanTest.gsRandom1` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.gsRandom1` |
| `org.dyn4j.geometry.hull.GrahamScanTest.gsRandom2` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.gsRandom2` |
| `org.dyn4j.geometry.hull.GrahamScanTest.gs22` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.gs22` |
| `org.dyn4j.geometry.hull.GrahamScanTest.gs2` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.gs2` |
| `org.dyn4j.geometry.hull.GrahamScanTest.gs3` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.gs3` |
| `org.dyn4j.geometry.hull.GrahamScanTest.gs4` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.gs4` |
| `org.dyn4j.geometry.hull.GrahamScanTest.gs6` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.gs6` |
| `org.dyn4j.geometry.hull.GrahamScanTest.gs7` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.gs7` |
| `org.dyn4j.geometry.hull.GrahamScanTest.gs5` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.gs5` |
| `org.dyn4j.geometry.hull.GrahamScanTest.gs5Part2` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.gs5Part2` |
| `org.dyn4j.geometry.hull.GrahamScanTest.gs5Part3` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.gs5Part3` |
| `org.dyn4j.geometry.hull.GrahamScanTest.gs8` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.gs8` |
| `org.dyn4j.geometry.hull.GrahamScanTest.gs9` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.gs9` |
| `org.dyn4j.geometry.hull.GrahamScanTest.gs10` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.gs10` |
| `org.dyn4j.geometry.hull.GrahamScanTest.gs11` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.gs11` |
| `org.dyn4j.geometry.hull.GrahamScanTest.gs12` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.gs12` |
| `org.dyn4j.geometry.hull.GrahamScanTest.gs13` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.gs13` |
| `org.dyn4j.geometry.hull.GrahamScanTest.gs14` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.gs14` |
| `org.dyn4j.geometry.hull.MonotoneChainTest.monoRandom1` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.monoRandom1` |
| `org.dyn4j.geometry.hull.MonotoneChainTest.monoRandom2` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.monoRandom2` |
| `org.dyn4j.geometry.hull.MonotoneChainTest.mono22` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.mono22` |
| `org.dyn4j.geometry.hull.MonotoneChainTest.mono2` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.mono2` |
| `org.dyn4j.geometry.hull.MonotoneChainTest.mono3` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.mono3` |
| `org.dyn4j.geometry.hull.MonotoneChainTest.mono4` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.mono4` |
| `org.dyn4j.geometry.hull.MonotoneChainTest.mono6` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.mono6` |
| `org.dyn4j.geometry.hull.MonotoneChainTest.mono7` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.mono7` |
| `org.dyn4j.geometry.hull.MonotoneChainTest.mono5` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.mono5` |
| `org.dyn4j.geometry.hull.MonotoneChainTest.mono5Part2` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.mono5Part2` |
| `org.dyn4j.geometry.hull.MonotoneChainTest.mono5Part3` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.mono5Part3` |
| `org.dyn4j.geometry.hull.MonotoneChainTest.mono8` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.mono8` |
| `org.dyn4j.geometry.hull.MonotoneChainTest.mono9` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.mono9` |
| `org.dyn4j.geometry.hull.MonotoneChainTest.mono10` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.mono10` |
| `org.dyn4j.geometry.hull.MonotoneChainTest.mono11` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.mono11` |
| `org.dyn4j.geometry.hull.MonotoneChainTest.mono12` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.mono12` |
| `org.dyn4j.geometry.hull.MonotoneChainTest.mono13` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.mono13` |
| `org.dyn4j.geometry.hull.MonotoneChainTest.mono14` | `org.dyn4j.coverage.geometry.algorithms.UpstreamHullCoverageTest.mono14` |
| `org.dyn4j.geometry.decompose.BayazitTest.nullArray` | JVM-only: null Java vararg array; unchanged candidate Java JUnit |
| `org.dyn4j.geometry.decompose.BayazitTest.lessThan4Vertices` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.Bayazit_lessThan4Vertices` |
| `org.dyn4j.geometry.decompose.BayazitTest.nullVertex` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.Bayazit_nullVertex` |
| `org.dyn4j.geometry.decompose.BayazitTest.coincidentVertex` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.Bayazit_coincidentVertex` |
| `org.dyn4j.geometry.decompose.BayazitTest.success1` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.Bayazit_success1` |
| `org.dyn4j.geometry.decompose.BayazitTest.success2` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.Bayazit_success2` |
| `org.dyn4j.geometry.decompose.BayazitTest.success3` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.Bayazit_success3` |
| `org.dyn4j.geometry.decompose.BayazitTest.success4` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.Bayazit_success4` |
| `org.dyn4j.geometry.decompose.BayazitTest.success5` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.Bayazit_success5` |
| `org.dyn4j.geometry.decompose.BayazitTest.successBird` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.Bayazit_successBird` |
| `org.dyn4j.geometry.decompose.BayazitTest.successTank` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.Bayazit_successTank` |
| `org.dyn4j.geometry.decompose.BayazitTest.successNazcaMonkey` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.Bayazit_successNazcaMonkey` |
| `org.dyn4j.geometry.decompose.BayazitTest.successNazcaHeron` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.Bayazit_successNazcaHeron` |
| `org.dyn4j.geometry.decompose.BayazitTest.successZoom1` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.Bayazit_successZoom1` |
| `org.dyn4j.geometry.decompose.BayazitTest.successZoom2` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.Bayazit_successZoom2` |
| `org.dyn4j.geometry.decompose.BayazitTest.successZoom3` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.Bayazit_successZoom3` |
| `org.dyn4j.geometry.decompose.BayazitTest.successZoom4` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.Bayazit_successZoom4` |
| `org.dyn4j.geometry.decompose.BayazitTest.successZoom5` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.Bayazit_successZoom5` |
| `org.dyn4j.geometry.decompose.BayazitTest.successZoom6` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.Bayazit_successZoom6` |
| `org.dyn4j.geometry.decompose.BayazitTest.successZoom7` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.Bayazit_successZoom7` |
| `org.dyn4j.geometry.decompose.BayazitTest.successTridol1` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.Bayazit_successTridol1` |
| `org.dyn4j.geometry.decompose.BayazitTest.successTridol2` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.Bayazit_successTridol2` |
| `org.dyn4j.geometry.decompose.BayazitTest.successTridol3` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.Bayazit_successTridol3` |
| `org.dyn4j.geometry.decompose.BayazitTest.decomposeFailSelfIntersection1` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.Bayazit_decomposeFailSelfIntersection1` |
| `org.dyn4j.geometry.decompose.BayazitTest.decomposeFailSelfIntersection2` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.Bayazit_decomposeFailSelfIntersection2` |
| `org.dyn4j.geometry.decompose.BayazitTest.decomposeFailSelfIntersection3` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.Bayazit_decomposeFailSelfIntersection3` |
| `org.dyn4j.geometry.decompose.BayazitTest.decomposeFailSelfIntersection4` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.Bayazit_decomposeFailSelfIntersection4` |
| `org.dyn4j.geometry.decompose.BayazitTest.decomposeFailSelfIntersection5` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.Bayazit_decomposeFailSelfIntersection5` |
| `org.dyn4j.geometry.decompose.BayazitTest.decomposeFailSelfIntersection6` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.Bayazit_decomposeFailSelfIntersection6` |
| `org.dyn4j.geometry.decompose.BayazitTest.decomposeFailureDegenerateGusAsf` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.Bayazit_decomposeFailureDegenerateGusAsf` |
| `org.dyn4j.geometry.decompose.BayazitTest.nsoftTriangulateFailure` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.Bayazit_nsoftTriangulateFailure` |
| `org.dyn4j.geometry.decompose.EarClippingTest.nullArray` | JVM-only: null Java vararg array; unchanged candidate Java JUnit |
| `org.dyn4j.geometry.decompose.EarClippingTest.lessThan4Vertices` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.EarClipping_lessThan4Vertices` |
| `org.dyn4j.geometry.decompose.EarClippingTest.nullVertex` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.EarClipping_nullVertex` |
| `org.dyn4j.geometry.decompose.EarClippingTest.coincidentVertex` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.EarClipping_coincidentVertex` |
| `org.dyn4j.geometry.decompose.EarClippingTest.success1` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.EarClipping_success1` |
| `org.dyn4j.geometry.decompose.EarClippingTest.triangulateSuccess1` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.EarClipping_triangulateSuccess1` |
| `org.dyn4j.geometry.decompose.EarClippingTest.success2` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.EarClipping_success2` |
| `org.dyn4j.geometry.decompose.EarClippingTest.triangulateSuccess2` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.EarClipping_triangulateSuccess2` |
| `org.dyn4j.geometry.decompose.EarClippingTest.success3` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.EarClipping_success3` |
| `org.dyn4j.geometry.decompose.EarClippingTest.triangulateSuccess3` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.EarClipping_triangulateSuccess3` |
| `org.dyn4j.geometry.decompose.EarClippingTest.success4` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.EarClipping_success4` |
| `org.dyn4j.geometry.decompose.EarClippingTest.triangulateSuccess4` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.EarClipping_triangulateSuccess4` |
| `org.dyn4j.geometry.decompose.EarClippingTest.success5` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.EarClipping_success5` |
| `org.dyn4j.geometry.decompose.EarClippingTest.triangulateSuccess5` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.EarClipping_triangulateSuccess5` |
| `org.dyn4j.geometry.decompose.EarClippingTest.successBird` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.EarClipping_successBird` |
| `org.dyn4j.geometry.decompose.EarClippingTest.triangulateSuccessBird` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.EarClipping_triangulateSuccessBird` |
| `org.dyn4j.geometry.decompose.EarClippingTest.successTank` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.EarClipping_successTank` |
| `org.dyn4j.geometry.decompose.EarClippingTest.triangulateSuccessTank` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.EarClipping_triangulateSuccessTank` |
| `org.dyn4j.geometry.decompose.EarClippingTest.successNazcaMonkey` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.EarClipping_successNazcaMonkey` |
| `org.dyn4j.geometry.decompose.EarClippingTest.triangulateSuccessNazcaMonkey` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.EarClipping_triangulateSuccessNazcaMonkey` |
| `org.dyn4j.geometry.decompose.EarClippingTest.successNazcaHeron` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.EarClipping_successNazcaHeron` |
| `org.dyn4j.geometry.decompose.EarClippingTest.triangulateSuccessNazcaHeron` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.EarClipping_triangulateSuccessNazcaHeron` |
| `org.dyn4j.geometry.decompose.EarClippingTest.successZoom1` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.EarClipping_successZoom1` |
| `org.dyn4j.geometry.decompose.EarClippingTest.triangulateSuccessZoom1` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.EarClipping_triangulateSuccessZoom1` |
| `org.dyn4j.geometry.decompose.EarClippingTest.successZoom2` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.EarClipping_successZoom2` |
| `org.dyn4j.geometry.decompose.EarClippingTest.triangulateSuccessZoom2` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.EarClipping_triangulateSuccessZoom2` |
| `org.dyn4j.geometry.decompose.EarClippingTest.successZoom3` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.EarClipping_successZoom3` |
| `org.dyn4j.geometry.decompose.EarClippingTest.triangulateSuccessZoom3` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.EarClipping_triangulateSuccessZoom3` |
| `org.dyn4j.geometry.decompose.EarClippingTest.successZoom4` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.EarClipping_successZoom4` |
| `org.dyn4j.geometry.decompose.EarClippingTest.triangulateSuccessZoom4` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.EarClipping_triangulateSuccessZoom4` |
| `org.dyn4j.geometry.decompose.EarClippingTest.successZoom5` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.EarClipping_successZoom5` |
| `org.dyn4j.geometry.decompose.EarClippingTest.triangulateSuccessZoom5` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.EarClipping_triangulateSuccessZoom5` |
| `org.dyn4j.geometry.decompose.EarClippingTest.successZoom6` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.EarClipping_successZoom6` |
| `org.dyn4j.geometry.decompose.EarClippingTest.triangulateSuccessZoom6` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.EarClipping_triangulateSuccessZoom6` |
| `org.dyn4j.geometry.decompose.EarClippingTest.successZoom7` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.EarClipping_successZoom7` |
| `org.dyn4j.geometry.decompose.EarClippingTest.triangulateSuccessZoom7` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.EarClipping_triangulateSuccessZoom7` |
| `org.dyn4j.geometry.decompose.EarClippingTest.successTridol1` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.EarClipping_successTridol1` |
| `org.dyn4j.geometry.decompose.EarClippingTest.triangulateSuccessTridol1` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.EarClipping_triangulateSuccessTridol1` |
| `org.dyn4j.geometry.decompose.EarClippingTest.successTridol2` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.EarClipping_successTridol2` |
| `org.dyn4j.geometry.decompose.EarClippingTest.triangulateSuccessTridol2` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.EarClipping_triangulateSuccessTridol2` |
| `org.dyn4j.geometry.decompose.EarClippingTest.successTridol3` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.EarClipping_successTridol3` |
| `org.dyn4j.geometry.decompose.EarClippingTest.triangulateSuccessTridol3` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.EarClipping_triangulateSuccessTridol3` |
| `org.dyn4j.geometry.decompose.EarClippingTest.triangulateFailSelfIntersection1` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.EarClipping_triangulateFailSelfIntersection1` |
| `org.dyn4j.geometry.decompose.EarClippingTest.triangulateFailSelfIntersection2` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.EarClipping_triangulateFailSelfIntersection2` |
| `org.dyn4j.geometry.decompose.EarClippingTest.triangulateFailSelfIntersection3` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.EarClipping_triangulateFailSelfIntersection3` |
| `org.dyn4j.geometry.decompose.EarClippingTest.triangulateFailSelfIntersection4` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.EarClipping_triangulateFailSelfIntersection4` |
| `org.dyn4j.geometry.decompose.EarClippingTest.triangulateFailSelfIntersection5` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.EarClipping_triangulateFailSelfIntersection5` |
| `org.dyn4j.geometry.decompose.EarClippingTest.triangulateFailSelfIntersection6` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.EarClipping_triangulateFailSelfIntersection6` |
| `org.dyn4j.geometry.decompose.EarClippingTest.triangulateFailureDegenerateGusAsf` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.EarClipping_triangulateFailureDegenerateGusAsf` |
| `org.dyn4j.geometry.decompose.EarClippingTest.nsoftTriangulateFailure` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.EarClipping_nsoftTriangulateFailure` |
| `org.dyn4j.geometry.decompose.SweepLineTest.nullArray` | JVM-only: null Java vararg array; unchanged candidate Java JUnit |
| `org.dyn4j.geometry.decompose.SweepLineTest.lessThan4Vertices` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.SweepLine_lessThan4Vertices` |
| `org.dyn4j.geometry.decompose.SweepLineTest.nullVertex` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.SweepLine_nullVertex` |
| `org.dyn4j.geometry.decompose.SweepLineTest.coincidentVertex` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.SweepLine_coincidentVertex` |
| `org.dyn4j.geometry.decompose.SweepLineTest.success1` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.SweepLine_success1` |
| `org.dyn4j.geometry.decompose.SweepLineTest.triangulateSuccess1` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.SweepLine_triangulateSuccess1` |
| `org.dyn4j.geometry.decompose.SweepLineTest.success2` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.SweepLine_success2` |
| `org.dyn4j.geometry.decompose.SweepLineTest.triangulateSuccess2` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.SweepLine_triangulateSuccess2` |
| `org.dyn4j.geometry.decompose.SweepLineTest.success3` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.SweepLine_success3` |
| `org.dyn4j.geometry.decompose.SweepLineTest.triangulateSuccess3` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.SweepLine_triangulateSuccess3` |
| `org.dyn4j.geometry.decompose.SweepLineTest.success4` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.SweepLine_success4` |
| `org.dyn4j.geometry.decompose.SweepLineTest.triangulateSuccess4` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.SweepLine_triangulateSuccess4` |
| `org.dyn4j.geometry.decompose.SweepLineTest.success5` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.SweepLine_success5` |
| `org.dyn4j.geometry.decompose.SweepLineTest.triangulateSuccess5` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.SweepLine_triangulateSuccess5` |
| `org.dyn4j.geometry.decompose.SweepLineTest.successBird` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.SweepLine_successBird` |
| `org.dyn4j.geometry.decompose.SweepLineTest.triangulateSuccessBird` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.SweepLine_triangulateSuccessBird` |
| `org.dyn4j.geometry.decompose.SweepLineTest.successTank` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.SweepLine_successTank` |
| `org.dyn4j.geometry.decompose.SweepLineTest.triangulateSuccessTank` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.SweepLine_triangulateSuccessTank` |
| `org.dyn4j.geometry.decompose.SweepLineTest.successNazcaMonkey` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.SweepLine_successNazcaMonkey` |
| `org.dyn4j.geometry.decompose.SweepLineTest.triangulateSuccessNazcaMonkey` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.SweepLine_triangulateSuccessNazcaMonkey` |
| `org.dyn4j.geometry.decompose.SweepLineTest.successNazcaHeron` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.SweepLine_successNazcaHeron` |
| `org.dyn4j.geometry.decompose.SweepLineTest.triangulateSuccessNazcaHeron` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.SweepLine_triangulateSuccessNazcaHeron` |
| `org.dyn4j.geometry.decompose.SweepLineTest.successZoom1` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.SweepLine_successZoom1` |
| `org.dyn4j.geometry.decompose.SweepLineTest.triangulateSuccessZoom1` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.SweepLine_triangulateSuccessZoom1` |
| `org.dyn4j.geometry.decompose.SweepLineTest.successZoom2` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.SweepLine_successZoom2` |
| `org.dyn4j.geometry.decompose.SweepLineTest.triangulateSuccessZoom2` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.SweepLine_triangulateSuccessZoom2` |
| `org.dyn4j.geometry.decompose.SweepLineTest.successZoom3` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.SweepLine_successZoom3` |
| `org.dyn4j.geometry.decompose.SweepLineTest.triangulateSuccessZoom3` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.SweepLine_triangulateSuccessZoom3` |
| `org.dyn4j.geometry.decompose.SweepLineTest.successZoom4` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.SweepLine_successZoom4` |
| `org.dyn4j.geometry.decompose.SweepLineTest.triangulateSuccessZoom4` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.SweepLine_triangulateSuccessZoom4` |
| `org.dyn4j.geometry.decompose.SweepLineTest.successZoom5` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.SweepLine_successZoom5` |
| `org.dyn4j.geometry.decompose.SweepLineTest.triangulateSuccessZoom5` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.SweepLine_triangulateSuccessZoom5` |
| `org.dyn4j.geometry.decompose.SweepLineTest.successZoom6` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.SweepLine_successZoom6` |
| `org.dyn4j.geometry.decompose.SweepLineTest.triangulateSuccessZoom6` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.SweepLine_triangulateSuccessZoom6` |
| `org.dyn4j.geometry.decompose.SweepLineTest.successZoom7` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.SweepLine_successZoom7` |
| `org.dyn4j.geometry.decompose.SweepLineTest.triangulateSuccessZoom7` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.SweepLine_triangulateSuccessZoom7` |
| `org.dyn4j.geometry.decompose.SweepLineTest.successTridol1` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.SweepLine_successTridol1` |
| `org.dyn4j.geometry.decompose.SweepLineTest.triangulateSuccessTridol1` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.SweepLine_triangulateSuccessTridol1` |
| `org.dyn4j.geometry.decompose.SweepLineTest.successTridol2` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.SweepLine_successTridol2` |
| `org.dyn4j.geometry.decompose.SweepLineTest.triangulateSuccessTridol2` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.SweepLine_triangulateSuccessTridol2` |
| `org.dyn4j.geometry.decompose.SweepLineTest.successTridol3` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.SweepLine_successTridol3` |
| `org.dyn4j.geometry.decompose.SweepLineTest.triangulateSuccessTridol3` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.SweepLine_triangulateSuccessTridol3` |
| `org.dyn4j.geometry.decompose.SweepLineTest.triangulateFailSelfIntersection1` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.SweepLine_triangulateFailSelfIntersection1` |
| `org.dyn4j.geometry.decompose.SweepLineTest.triangulateFailSelfIntersection2` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.SweepLine_triangulateFailSelfIntersection2` |
| `org.dyn4j.geometry.decompose.SweepLineTest.triangulateFailSelfIntersection3` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.SweepLine_triangulateFailSelfIntersection3` |
| `org.dyn4j.geometry.decompose.SweepLineTest.triangulateFailSelfIntersection4` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.SweepLine_triangulateFailSelfIntersection4` |
| `org.dyn4j.geometry.decompose.SweepLineTest.triangulateFailSelfIntersection5` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.SweepLine_triangulateFailSelfIntersection5` |
| `org.dyn4j.geometry.decompose.SweepLineTest.triangulateFailSelfIntersection6` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.SweepLine_triangulateFailSelfIntersection6` |
| `org.dyn4j.geometry.decompose.SweepLineTest.triangulateFailureDegenerateGusAsf` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.SweepLine_triangulateFailureDegenerateGusAsf` |
| `org.dyn4j.geometry.decompose.SweepLineTest.nsoftTriangulateFailure` | `org.dyn4j.coverage.geometry.algorithms.UpstreamDecompositionCoverageTest.SweepLine_nsoftTriangulateFailure` |
| `org.dyn4j.geometry.simplify.DouglasPeuckerTest.createInvalidTolerance` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.DouglasPeucker_createInvalidTolerance` |
| `org.dyn4j.geometry.simplify.DouglasPeuckerTest.createInvalidEpsilon` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.DouglasPeucker_createInvalidEpsilon` |
| `org.dyn4j.geometry.simplify.DouglasPeuckerTest.createInvalidBoth` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.DouglasPeucker_createInvalidBoth` |
| `org.dyn4j.geometry.simplify.DouglasPeuckerTest.noChange` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.DouglasPeucker_noChange` |
| `org.dyn4j.geometry.simplify.DouglasPeuckerTest.emptyArray` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.DouglasPeucker_emptyArray` |
| `org.dyn4j.geometry.simplify.DouglasPeuckerTest.emptyList` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.DouglasPeucker_emptyList` |
| `org.dyn4j.geometry.simplify.DouglasPeuckerTest.nullArray` | JVM-only: null Java vararg array; unchanged candidate Java JUnit |
| `org.dyn4j.geometry.simplify.DouglasPeuckerTest.nullList` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.DouglasPeucker_nullList` |
| `org.dyn4j.geometry.simplify.DouglasPeuckerTest.nullElements` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.DouglasPeucker_nullElements` |
| `org.dyn4j.geometry.simplify.DouglasPeuckerTest.coincidentElements` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.DouglasPeucker_coincidentElements` |
| `org.dyn4j.geometry.simplify.DouglasPeuckerTest.closeElements` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.DouglasPeucker_closeElements` |
| `org.dyn4j.geometry.simplify.DouglasPeuckerTest.allNull` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.DouglasPeucker_allNull` |
| `org.dyn4j.geometry.simplify.DouglasPeuckerTest.allSamePoints` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.DouglasPeucker_allSamePoints` |
| `org.dyn4j.geometry.simplify.DouglasPeuckerTest.successBird` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.DouglasPeucker_successBird` |
| `org.dyn4j.geometry.simplify.DouglasPeuckerTest.successTank` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.DouglasPeucker_successTank` |
| `org.dyn4j.geometry.simplify.DouglasPeuckerTest.successSelfIntersection` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.DouglasPeucker_successSelfIntersection` |
| `org.dyn4j.geometry.simplify.DouglasPeuckerTest.successNazcaMonkey` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.DouglasPeucker_successNazcaMonkey` |
| `org.dyn4j.geometry.simplify.DouglasPeuckerTest.successNazcaHeron` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.DouglasPeucker_successNazcaHeron` |
| `org.dyn4j.geometry.simplify.DouglasPeuckerTest.successZoom1` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.DouglasPeucker_successZoom1` |
| `org.dyn4j.geometry.simplify.DouglasPeuckerTest.successZoom2` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.DouglasPeucker_successZoom2` |
| `org.dyn4j.geometry.simplify.DouglasPeuckerTest.successZoom3` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.DouglasPeucker_successZoom3` |
| `org.dyn4j.geometry.simplify.DouglasPeuckerTest.successZoom4` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.DouglasPeucker_successZoom4` |
| `org.dyn4j.geometry.simplify.DouglasPeuckerTest.successZoom5` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.DouglasPeucker_successZoom5` |
| `org.dyn4j.geometry.simplify.DouglasPeuckerTest.successZoom6` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.DouglasPeucker_successZoom6` |
| `org.dyn4j.geometry.simplify.DouglasPeuckerTest.successZoom7` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.DouglasPeucker_successZoom7` |
| `org.dyn4j.geometry.simplify.DouglasPeuckerTest.successTridol1` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.DouglasPeucker_successTridol1` |
| `org.dyn4j.geometry.simplify.DouglasPeuckerTest.successTridol2` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.DouglasPeucker_successTridol2` |
| `org.dyn4j.geometry.simplify.DouglasPeuckerTest.successTridol3` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.DouglasPeucker_successTridol3` |
| `org.dyn4j.geometry.simplify.DouglasPeuckerTest.successNsoft1` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.DouglasPeucker_successNsoft1` |
| `org.dyn4j.geometry.simplify.SegmentTreeTest.createLeaf` | `org.dyn4j.geometry.simplify.UpstreamSimplificationSupportCoverageTest.SegmentTreeTest_createLeaf` |
| `org.dyn4j.geometry.simplify.SegmentTreeTest.createNode` | `org.dyn4j.geometry.simplify.UpstreamSimplificationSupportCoverageTest.SegmentTreeTest_createNode` |
| `org.dyn4j.geometry.simplify.SimplePolygonVertexTest.create` | `org.dyn4j.geometry.simplify.UpstreamSimplificationSupportCoverageTest.SimplePolygonVertexTest_create` |
| `org.dyn4j.geometry.simplify.VertexClusterReductionTest.createInvalidTolerance` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.VertexClusterReduction_createInvalidTolerance` |
| `org.dyn4j.geometry.simplify.VertexClusterReductionTest.noChange` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.VertexClusterReduction_noChange` |
| `org.dyn4j.geometry.simplify.VertexClusterReductionTest.nullArray` | JVM-only: null Java vararg array; unchanged candidate Java JUnit |
| `org.dyn4j.geometry.simplify.VertexClusterReductionTest.nullList` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.VertexClusterReduction_nullList` |
| `org.dyn4j.geometry.simplify.VertexClusterReductionTest.emptyArray` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.VertexClusterReduction_emptyArray` |
| `org.dyn4j.geometry.simplify.VertexClusterReductionTest.emptyList` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.VertexClusterReduction_emptyList` |
| `org.dyn4j.geometry.simplify.VertexClusterReductionTest.nullElements` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.VertexClusterReduction_nullElements` |
| `org.dyn4j.geometry.simplify.VertexClusterReductionTest.coincidentElements` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.VertexClusterReduction_coincidentElements` |
| `org.dyn4j.geometry.simplify.VertexClusterReductionTest.allNull` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.VertexClusterReduction_allNull` |
| `org.dyn4j.geometry.simplify.VertexClusterReductionTest.allSamePoints` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.VertexClusterReduction_allSamePoints` |
| `org.dyn4j.geometry.simplify.VertexClusterReductionTest.closeElements` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.VertexClusterReduction_closeElements` |
| `org.dyn4j.geometry.simplify.VertexClusterReductionTest.successBird` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.VertexClusterReduction_successBird` |
| `org.dyn4j.geometry.simplify.VertexClusterReductionTest.successTank` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.VertexClusterReduction_successTank` |
| `org.dyn4j.geometry.simplify.VertexClusterReductionTest.successSelfIntersection` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.VertexClusterReduction_successSelfIntersection` |
| `org.dyn4j.geometry.simplify.VertexClusterReductionTest.successNazcaMonkey` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.VertexClusterReduction_successNazcaMonkey` |
| `org.dyn4j.geometry.simplify.VertexClusterReductionTest.successNazcaHeron` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.VertexClusterReduction_successNazcaHeron` |
| `org.dyn4j.geometry.simplify.VertexClusterReductionTest.successZoom1` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.VertexClusterReduction_successZoom1` |
| `org.dyn4j.geometry.simplify.VertexClusterReductionTest.successZoom2` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.VertexClusterReduction_successZoom2` |
| `org.dyn4j.geometry.simplify.VertexClusterReductionTest.successZoom3` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.VertexClusterReduction_successZoom3` |
| `org.dyn4j.geometry.simplify.VertexClusterReductionTest.successZoom4` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.VertexClusterReduction_successZoom4` |
| `org.dyn4j.geometry.simplify.VertexClusterReductionTest.successZoom5` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.VertexClusterReduction_successZoom5` |
| `org.dyn4j.geometry.simplify.VertexClusterReductionTest.successZoom6` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.VertexClusterReduction_successZoom6` |
| `org.dyn4j.geometry.simplify.VertexClusterReductionTest.successZoom7` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.VertexClusterReduction_successZoom7` |
| `org.dyn4j.geometry.simplify.VertexClusterReductionTest.successTridol1` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.VertexClusterReduction_successTridol1` |
| `org.dyn4j.geometry.simplify.VertexClusterReductionTest.successTridol2` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.VertexClusterReduction_successTridol2` |
| `org.dyn4j.geometry.simplify.VertexClusterReductionTest.successTridol3` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.VertexClusterReduction_successTridol3` |
| `org.dyn4j.geometry.simplify.VertexClusterReductionTest.successNsoft1` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.VertexClusterReduction_successNsoft1` |
| `org.dyn4j.geometry.simplify.VisvalingamTest.createInvalidTolerance` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.Visvalingam_createInvalidTolerance` |
| `org.dyn4j.geometry.simplify.VisvalingamTest.createInvalidEpsilon` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.Visvalingam_createInvalidEpsilon` |
| `org.dyn4j.geometry.simplify.VisvalingamTest.createInvalidBoth` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.Visvalingam_createInvalidBoth` |
| `org.dyn4j.geometry.simplify.VisvalingamTest.noChange` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.Visvalingam_noChange` |
| `org.dyn4j.geometry.simplify.VisvalingamTest.nullArray` | JVM-only: null Java vararg array; unchanged candidate Java JUnit |
| `org.dyn4j.geometry.simplify.VisvalingamTest.nullList` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.Visvalingam_nullList` |
| `org.dyn4j.geometry.simplify.VisvalingamTest.emptyArray` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.Visvalingam_emptyArray` |
| `org.dyn4j.geometry.simplify.VisvalingamTest.emptyList` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.Visvalingam_emptyList` |
| `org.dyn4j.geometry.simplify.VisvalingamTest.nullElements` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.Visvalingam_nullElements` |
| `org.dyn4j.geometry.simplify.VisvalingamTest.coincidentElements` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.Visvalingam_coincidentElements` |
| `org.dyn4j.geometry.simplify.VisvalingamTest.closeElements` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.Visvalingam_closeElements` |
| `org.dyn4j.geometry.simplify.VisvalingamTest.allNull` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.Visvalingam_allNull` |
| `org.dyn4j.geometry.simplify.VisvalingamTest.allSamePoints` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.Visvalingam_allSamePoints` |
| `org.dyn4j.geometry.simplify.VisvalingamTest.successBird` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.Visvalingam_successBird` |
| `org.dyn4j.geometry.simplify.VisvalingamTest.successTank` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.Visvalingam_successTank` |
| `org.dyn4j.geometry.simplify.VisvalingamTest.successSelfIntersection` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.Visvalingam_successSelfIntersection` |
| `org.dyn4j.geometry.simplify.VisvalingamTest.successNazcaMonkey` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.Visvalingam_successNazcaMonkey` |
| `org.dyn4j.geometry.simplify.VisvalingamTest.successNazcaHeron` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.Visvalingam_successNazcaHeron` |
| `org.dyn4j.geometry.simplify.VisvalingamTest.successZoom1` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.Visvalingam_successZoom1` |
| `org.dyn4j.geometry.simplify.VisvalingamTest.successZoom2` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.Visvalingam_successZoom2` |
| `org.dyn4j.geometry.simplify.VisvalingamTest.successZoom3` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.Visvalingam_successZoom3` |
| `org.dyn4j.geometry.simplify.VisvalingamTest.successZoom4` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.Visvalingam_successZoom4` |
| `org.dyn4j.geometry.simplify.VisvalingamTest.successZoom5` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.Visvalingam_successZoom5` |
| `org.dyn4j.geometry.simplify.VisvalingamTest.successZoom6` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.Visvalingam_successZoom6` |
| `org.dyn4j.geometry.simplify.VisvalingamTest.successZoom7` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.Visvalingam_successZoom7` |
| `org.dyn4j.geometry.simplify.VisvalingamTest.successTridol1` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.Visvalingam_successTridol1` |
| `org.dyn4j.geometry.simplify.VisvalingamTest.successTridol2` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.Visvalingam_successTridol2` |
| `org.dyn4j.geometry.simplify.VisvalingamTest.successTridol3` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.Visvalingam_successTridol3` |
| `org.dyn4j.geometry.simplify.VisvalingamTest.successNsoft1` | `org.dyn4j.coverage.geometry.algorithms.UpstreamSimplificationCoverageTest.Visvalingam_successNsoft1` |
