# Portable detection corpus: combined identity map

This report tracks the pinned broadphase, narrowphase, manifold, and continuous tests for [Run the full compatibility corpus and unchanged migration applications](https://github.com/rubixhacker/dyn4k/issues/42). The reviewed slices account for all **471** original executions: **463 portable common cases**, **8 exact JVM-only dispositions**, and **zero unmapped cases**. The common mappings cover 24 root detection cases, 145 narrowphase/manifold/continuous cases, 125 body broadphase variants, and 169 item broadphase cases. The 8 JVM-only cases are the four null-producer methods in each of `CollisionBodyAABBProducerTest` and `CollisionItemAABBProducerTest`; their original Java expectations remain in the unchanged Java corpus.

## Source and case identity

The original source is dyn4j 6.0.0 revision `058bf6d982a0fb89b54050f929f6ea9dae53b714`. The unchanged JVM binary has SHA-256 `204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e`. The 37 selected Java test files have 257 textual `@Test` strings, of which two in `LinkPostProcessorTest` are commented out. JUnit ran 255 active test methods. The two broadphase parameterized classes expand 54 methods over five detector variants, producing 471 executions in total.

The [case map](../../dyn4k-core/src/commonTest/kotlin/org/dyn4j/coverage/collision/detection/resources/source-case-map.tsv) gives all 471 exact identities, pinned source paths, SHA-256 hashes, declaration lines, and dispositions. Its SHA-256 is `37d63f4e2227a4f793da1b59e4391f015ee7d45cf22e8d65ab66e699f3633f41`. The [map generator](../../dyn4k-core/src/commonTest/kotlin/org/dyn4j/coverage/collision/detection/resources/build-case-map.py) compares baseline and candidate JUnit XML identities before it emits mappings, and has a reconciliation mode that verifies pinned source hashes and declaration lines. It replaces JUnit's process-dependent object hash in parameter names with the source-defined detector order: `sap_untracked`, `sap_tracked`, `tree_untracked`, `tree_tracked`, and `brute_force`. Each variant remains a separate identity.

| Original package | Executed cases | Portable common cases | JVM-only | Unmapped |
| --- | ---: | ---: | ---: | ---: |
| Broadphase | 302 | 294 | 8 | 0 |
| Narrowphase | 116 | 116 | 0 | 0 |
| Manifold | 25 | 25 | 0 | 0 |
| Continuous | 28 | 28 | 0 | 0 |
| **Total** | **471** | **463** | **8** | **0** |

The linked [detection rest report](portable-detection-rest.md), [body broadphase report](portable-detection-body.md), and [item broadphase report](portable-detection-item.md) retain the slice-level source-to-test crosswalks and original assertion semantics. The root `DetectionResultCoverageTest` mappings cover `PenetrationTest`, `SeparationTest`, `RaycastTest`, `ContainmentTest`, and `TimeOfImpactTest`. Upstream legal notices remain in the adapted sources. Existing supplemental iterator tests stay outside the original identity map and are counted separately. Controlled wrong-expectation checks remain recorded in the slice reports.

## Raw execution evidence

The original Java sources compiled with `javac --release 8` against the pinned baseline. The same original files compiled against this branch's candidate JAR through `compileUpstreamDetectionTests`. The [JUnit Gradle init script](../../dyn4k-core/src/commonTest/kotlin/org/dyn4j/coverage/collision/detection/resources/detection-junit.init.gradle) ran those class files against each provider and wrote raw JUnit XML. The baseline and candidate each ran 37 suites, 471 tests, zero failures, zero errors, and zero skips. The script did not modify build registration.

| Provider | XML files | Cases | Aggregate SHA-256 over sorted name and bytes |
| --- | ---: | ---: | --- |
| Pinned baseline | 37 | 471 | `b9e072fe8a956442957f087f2726737d48012199d6c8abd8c5c62c774de57626` |
| Candidate JVM | 37 | 471 | `c9fcb04166973f1951fffed8691b02edcf63cb980788a22972a0c600b269cfde` |

The common test task ran all available local host lanes. These are host observations, not full target or runtime qualification. Each lane ran seven suites and 61 cases, including the 24 mapped cases, with zero failures, errors, or skips.

| Host task | Aggregate XML SHA-256 over sorted name and bytes |
| --- | --- |
| `jvmTest` | `b36ebcd87229fac346aa5bb810beeec0f883944cd41ffb2640b7d718673edc47` |
| `linuxX64Test` | `08e4d3a7f9f8593d57c4b97663c25ec709e060cceed1d4f1e11e11701470a3c4` |
| `jsNodeTest` | `d2e5cbef0afa7593ccbcaf1b02859c0de7d97c2a7fa27d3271f5bf742baf9067` |
| `wasmJsNodeTest` | `caf88c2ff4a69a6ff126b67bb9768aa997ec99fac41b83b8f5924ab470f25dde` |
| `wasmWasiNodeTest` | `0520816ca1c2552b5f5facebf27615b361fd8c3004a117ae3f26c646b5131787` |
| `testAndroidHostTest` | `97d25c2b1882ead39a9c26de854f147afadf8f58ef7ee84f09ede55f5ee339a5` |

The eight raw XML directories are archived at `/tmp/dyn4k-portable-detection-coverage-xml.tar.gz`, SHA-256 `0a26ca399433dc8158e3cbfc175f7a54e3c7016b7d03b9386079a7c32ec78b5a`. The archive is local evidence; it is not a release artifact.

## Consumer and artifact observations

The pinned baseline, local candidate, staged JVM Java, staged JVM Kotlin, and Android host Java detection consumers all ran. The deterministic baseline and candidate detection parity consumer emitted 1,288 rows with zero differences beyond `1e-8`; the maximum absolute difference was `1.7070789226636407e-12`. The candidate and staged `dyn4k-core-jvm` JARs are byte-identical, SHA-256 `b43a8c0fc58cac15967eb7ecc04943f01379ea952fab4d18c2a882f1ae27f519`. The staged `dyn4k-jvm` JAR has SHA-256 `4bb4b9f67f7647a5b3a7b620e315dd0108c6fbd983e1cb099a355267dba91719`.

The historical raw execution tables above are slice-level runs from their original review worktrees; they are not the combined integration qualification. The frozen combined qualification and all-host identity comparison must be recorded against the exact combined candidate commit. The unchanged Java compatibility corpus and external migration applications are separate checks. Issue 42 remains open until those checks and the other explicitly separate target, device, numerical, physical, and performance gates are satisfied.
