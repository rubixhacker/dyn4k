# Portable detection corpus: narrowphase, manifold, continuous

This report covers the original cases assigned to this branch under [Run the full compatibility corpus and unchanged migration applications](https://github.com/rubixhacker/dyn4k/issues/42). The worktree started at `41be662d8e8ba4c7f838d3f63371cd99347fb652` on `codex/port-coverage-detection`. The original source is dyn4j 6.0.0 revision `058bf6d982a0fb89b54050f929f6ea9dae53b714` at `/tmp/dyn4k-upstream-6.0.0`.

The existing [source case map](../../dyn4k-core/src/commonTest/kotlin/org/dyn4j/coverage/collision/detection/resources/source-case-map.tsv) gives the exact Java source file, source SHA-256, declaration line, and expanded JUnit identity for each case. Its SHA-256 remains `4978c0d85575222df3c53d8a5ac71a47858fe99c972db6914caaed043a2b8f43`. It still says `UNMAPPED` for these cases because combined review owns that frozen map. This report records the new disposition without changing it.

## Identity disposition

All **145** assigned original executions have a portable common Kotlin test: **96 narrowphase, 25 manifold, 24 continuous**. There are **zero JVM-only dispositions** and **zero unmapped cases in this assigned set**. The tests contain 145 `@Test` declarations, and the JVM XML executes 145 cases from the new files. The 24 cases in the earlier `DetectionResultCoverageTest` remain separate. Two commented-out Java methods in `LinkPostProcessorTest` are not original JUnit executions and are not counted. The two broadphase workers own the remaining 302 original executions.

Each mapping below is exact: read the original method name after `#` in the source case map. Where the prefix column is empty, the portable method has that same name. Where a prefix is shown, capitalize the first letter of the original method name and append it to the prefix. For example, `EpaTest#setSmallMaxIterations` maps to `NarrowphaseModelCoverageTest.epaSetSmallMaxIterations`. This rule was checked against all 145 original map rows and all 145 distinct portable `@Test` methods; it found no missing or duplicate method names.

| Original Java class | Cases | Portable common Kotlin class | Method prefix |
| --- | ---: | --- | --- |
| `AbstractFallbackConditionTest` | 3 | `NarrowphaseModelCoverageTest` | `abstractFallbackCondition` |
| `EpaTest` | 6 | `NarrowphaseModelCoverageTest` | `epa` |
| `ExpandingSimplexEdgeTest` | 3 | `NarrowphaseModelCoverageTest` | `expandingSimplexEdge` |
| `ExpandingSimplexTest` | 3 | `NarrowphaseModelCoverageTest` | `expandingSimplex` |
| `FallbackNarrowphaseDetectorTest` | 12 | `FallbackCoverageTest` | `fallback` |
| `GjkTest` | 28 | `GjkCoverageTest` | |
| `LinkPostProcessorTest` | 12 | `LinkPostProcessorCoverageTest` | |
| `MinkowskiSumPointTest` | 1 | `NarrowphaseModelCoverageTest` | `minkowskiSumPoint` |
| `MinkowskiSumTest` | 4 | `NarrowphaseModelCoverageTest` | `minkowskiSum` |
| `PairwiseTypedFallbackConditionTest` | 2 | `FallbackCoverageTest` | `pairwiseTyped` |
| `SatTest` | 12 | `SatCoverageTest` | |
| `SegmentDetectorTest` | 8 | `SegmentDetectorCoverageTest` | |
| `SingleTypedFallbackConditionTest` | 2 | `FallbackCoverageTest` | `singleTyped` |
| `ClippingManifoldSolverTest` | 5 | `ClippingManifoldCoverageTest` | |
| `IndexedManifoldPointIdTest` | 5 | `ManifoldModelCoverageTest` | `indexedManifoldPointId` |
| `ManifoldPointIdTest` | 2 | `ManifoldModelCoverageTest` | `manifoldPointId` |
| `ManifoldPointTest` | 6 | `ManifoldModelCoverageTest` | `manifoldPoint` |
| `ManifoldTest` | 7 | `ManifoldModelCoverageTest` | `manifold` |
| `ConservativeAdvancementTest` | 24 | `ConservativeAdvancementCoverageTest` | |

The common tests retain the original geometric fixtures, variant branches, error boundaries, null inputs, and expected numeric values. The clipping tests check contact coordinates and reversed shape order. The continuous tests check TOI and separation outcomes. The GJK ray tests check pinned hit points, normals, distances, finite length boundaries, misses, reversed rays, and starts inside shapes. The link tests retain the pinned vertex chains and each normal and depth before and after processing, including reversed shape order. Separate helper functions only reduce repeated assertions; they are not counted as portable cases. Upstream copyright notices remain in each derived file.

## Executed evidence

The six common host tasks ran from the restored test tree with `ANDROID_HOME=/home/stewart/Android/Sdk ./gradlew :dyn4k-core:jvmTest :dyn4k-core:linuxX64Test :dyn4k-core:jsNodeTest :dyn4k-core:wasmJsNodeTest :dyn4k-core:wasmWasiNodeTest :dyn4k-core:testAndroidHostTest --continue --rerun-tasks --console=plain`. Each produced 16 raw XML suites and **206 executions**, including the earlier 24 mapped cases, these 145 cases, and 37 existing common tests. All lanes have zero skips and zero errors. The hash is SHA-256 over sorted XML filename followed by file bytes.

| Host task | Tests | Failures | XML aggregate SHA-256 |
| --- | ---: | ---: | --- |
| `jvmTest` | 206 | 0 | `e2551e0fd65a2e9331e0a52436ec781cbaebef54e7a5abb801569df97d3bfbfb` |
| `linuxX64Test` | 206 | 2 | `b4869c8ad2b2570a959ba50e162ce72c7a5f4b55dfaa25922b6b950d9ac8bb02` |
| `jsNodeTest` | 206 | 2 | `b5ae152b79db141f8ebd816b5928aefb7a8db1643b34bec2bb6a39d2c64fcd19` |
| `wasmJsNodeTest` | 206 | 2 | `eded216ae14c3af5f804f2ada54f6da1ae3be36c11096d2991a4ba6d118307a4` |
| `wasmWasiNodeTest` | 206 | 2 | `71bad248b9bc20a3b8238441f07b59797aa7ab6187ba1bccad0cf68c8e1ddf74` |
| `testAndroidHostTest` | 206 | 0 | `56112cf0b9f57d6ec475b267cf9b1628f4b4c87904d1657af8893bdeb70ccdd1` |

The unchanged 37-class Java suite was compiled with `javac --release 8` against the pinned baseline and with `:dyn4k-core:compileUpstreamDetectionTests` against the candidate. The existing `detection-junit.init.gradle` ran each compiled suite against its matching provider. Baseline raw XML: **37 suites, 471 tests, zero failures, zero errors, zero skips**, aggregate SHA-256 `4daef853fa2b21c5482eb9beeec6c2d2bcd851a860f121197db16e5b9e0fc4e9`. Candidate raw XML: **37 suites, 471 tests, zero failures, zero errors, zero skips**, aggregate SHA-256 `df32f49036f23d5cc5fd31525e8d0e55aac82f8dafb3647f587d2088b0206f41`. Both commands used `:dyn4k-core:detectionJUnitEvidence --rerun-tasks` with the pinned class directories and provider paths.

The raw XML from all eight runs is archived at `/tmp/dyn4k-coverage-detection-rest-xml.tar.gz`, SHA-256 `cc3b62fed2ea37394e56a31083985fb1329261e62a3980e5aae78a407d8fbad5`. The controlled bad oracle changed the expected GJK rectangle hit X from `1.500` to `1.600`. `jvmTest --rerun-tasks` then ran 206 tests with exactly one failure, `GjkCoverageTest.raycastRectangle`. Its raw XML archive is `/tmp/dyn4k-coverage-detection-rest-controlled-red-xml.tar.gz`, SHA-256 `ff0a61efffbd09b989b9da411ae6eb2e1cdb8f9bdf2f75696d79a31d9006acfd`. Restoring `1.500` passed on JVM.

The baseline Java, candidate Java, staged Java, staged Kotlin, and Android host Java detection consumers ran through their existing Gradle tasks. `:dyn4k-core:verifyDetectionParity` compared 1,288 rows with no differences beyond `1e-8`; the maximum absolute difference was `1.7070789226636407e-12`. The pinned baseline JAR SHA-256 is `204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e`. The local and staged `dyn4k-core-jvm` JARs are byte-identical, SHA-256 `b43a8c0fc58cac15967eb7ecc04943f01379ea952fab4d18c2a882f1ae27f519`. The staged `dyn4k-jvm` JAR SHA-256 is `4bb4b9f67f7647a5b3a7b620e315dd0108c6fbd983e1cb099a355267dba91719`.

## Source defect for the detection owner

`FallbackCoverageTest.singleTypedIsMatch` and `FallbackCoverageTest.pairwiseTypedIsMatch` fail on Linux, JS, wasm JS, and wasm WASI. The upstream methods test `Polygon.class` matching `Rectangle.class` when strict mode is false. The portable code at `dyn4k-core/src/commonMain/kotlin/org/dyn4j/collision/narrowphase/PortableConvexClass.kt:17-18` uses `other.sample?.let(type.type::isInstance) ?: (type.type == other.type)`. A direct type-to-type call has no `sample`, so subclass matching falls back to equality and returns false. The JVM provider uses class assignability and passes. This is an engine seam owned by the detection source author. The two assertions remain red and unmodified; this corpus branch does not edit the algorithm.

The Android host task is a JVM host run, not an Android device. The frozen qualification manifest has not been updated or executed for these cases. The broadphase corpus and later combined integration review remain separate. This report does not qualify unavailable lanes or close the issue.
