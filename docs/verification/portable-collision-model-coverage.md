# Portable collision model coverage

## Scope and identities

The pinned source is dyn4j 6.0.0 at `058bf6d982a0fb89b54050f929f6ea9dae53b714`. This report covers the 14 root collision test classes and two support test classes wired into `runUpstreamCollisionModelTests`. `TestCollisionBody.java` is the unchanged original helper and contributes no JUnit method. The 16 test classes contain 114 `@Test` methods; the independent baseline and candidate JUnit executions each expand to 114 cases. Each row below maps one original method to one common test. The common source is `dyn4k-core/src/commonTest/kotlin/org/dyn4j/coverage/collision/model/FilterFixtureCoverageTest.kt`.

| Pinned original method | Portable common test |
| --- | --- |
| `collision/AbstractBoundsTest.java#create` | `BoundsCoverageTest.abstractCreate` |
| `collision/AbstractBoundsTest.java#translation` | `BoundsCoverageTest.abstractTranslation` |
| `collision/AbstractBoundsTest.java#shiftCoordinates` | `BoundsCoverageTest.abstractShiftCoordinates` |
| `collision/AbstractCollisionBodyTest.java#create` | `CollisionBodyCoverageTest.create` |
| `collision/AbstractCollisionBodyTest.java#addFixture` | `CollisionBodyCoverageTest.addFixture` |
| `collision/AbstractCollisionBodyTest.java#addNullConvex` | `CollisionBodyCoverageTest.addNullConvex` |
| `collision/AbstractCollisionBodyTest.java#addNullFixture` | `CollisionBodyCoverageTest.addNullFixture` |
| `collision/AbstractCollisionBodyTest.java#containsPoint` | `CollisionBodyCoverageTest.containsPoint` |
| `collision/AbstractCollisionBodyTest.java#containsFixture` | `CollisionBodyCoverageTest.containsFixture` |
| `collision/AbstractCollisionBodyTest.java#createAABB` | `CollisionBodyCoverageTest.createAABB` |
| `collision/AbstractCollisionBodyTest.java#getFixtureByPoint` | `CollisionBodyCoverageTest.getFixtureByPoint` |
| `collision/AbstractCollisionBodyTest.java#getFixtureByIndex` | `CollisionBodyCoverageTest.getFixtureByIndex` |
| `collision/AbstractCollisionBodyTest.java#getFixtureCount` | `CollisionBodyCoverageTest.getFixtureCount` |
| `collision/AbstractCollisionBodyTest.java#getFixtureIterator` | `CollisionBodyCoverageTest.getFixtureIterator` |
| `collision/AbstractCollisionBodyTest.java#getFixtureIteratorFailures` | `CollisionBodyCoverageTest.getFixtureIteratorFailures` |
| `collision/AbstractCollisionBodyTest.java#getSetFixtureModificationHandler` | `CollisionBodyCoverageTest.getSetFixtureModificationHandler` |
| `collision/AbstractCollisionBodyTest.java#getFixtures` | `CollisionBodyCoverageTest.getFixtures` |
| `collision/AbstractCollisionBodyTest.java#getFixturesAndAdd` | `CollisionBodyCoverageTest.getFixturesAndAdd` |
| `collision/AbstractCollisionBodyTest.java#getFixturesAndRemove` | `CollisionBodyCoverageTest.getFixturesAndRemove` |
| `collision/AbstractCollisionBodyTest.java#getFixturesByPoint` | `CollisionBodyCoverageTest.getFixturesByPoint` |
| `collision/AbstractCollisionBodyTest.java#getLocalPoint` | `CollisionBodyCoverageTest.getLocalPoint` |
| `collision/AbstractCollisionBodyTest.java#getLocalVector` | `CollisionBodyCoverageTest.getLocalVector` |
| `collision/AbstractCollisionBodyTest.java#getSetOwner` | `CollisionBodyCoverageTest.getSetOwner` |
| `collision/AbstractCollisionBodyTest.java#getSetRotationDiscRadius` | `CollisionBodyCoverageTest.getSetRotationDiscRadius` |
| `collision/AbstractCollisionBodyTest.java#getSetTransform` | `CollisionBodyCoverageTest.getSetTransform` |
| `collision/AbstractCollisionBodyTest.java#getSetPreviousTransform` | `CollisionBodyCoverageTest.getSetPreviousTransform` |
| `collision/AbstractCollisionBodyTest.java#getSetUserData` | `CollisionBodyCoverageTest.getSetUserData` |
| `collision/AbstractCollisionBodyTest.java#getWorldCenter` | `CollisionBodyCoverageTest.getWorldCenter` |
| `collision/AbstractCollisionBodyTest.java#getWorldPoint` | `CollisionBodyCoverageTest.getWorldPoint` |
| `collision/AbstractCollisionBodyTest.java#getWorldVector` | `CollisionBodyCoverageTest.getWorldVector` |
| `collision/AbstractCollisionBodyTest.java#getSetEnabled` | `CollisionBodyCoverageTest.getSetEnabled` |
| `collision/AbstractCollisionBodyTest.java#removeAllFixtures` | `CollisionBodyCoverageTest.removeAllFixtures` |
| `collision/AbstractCollisionBodyTest.java#removeFixture` | `CollisionBodyCoverageTest.removeFixture` |
| `collision/AbstractCollisionBodyTest.java#removeFixtureNotFound` | `CollisionBodyCoverageTest.removeFixtureNotFound` |
| `collision/AbstractCollisionBodyTest.java#removeFixtureByPoint` | `CollisionBodyCoverageTest.removeFixtureByPoint` |
| `collision/AbstractCollisionBodyTest.java#removeFixtureByIndexOutOfBounds` | `CollisionBodyCoverageTest.removeFixtureByIndexOutOfBounds` |
| `collision/AbstractCollisionBodyTest.java#removeFixtureIndexNegative` | `CollisionBodyCoverageTest.removeFixtureIndexNegative` |
| `collision/AbstractCollisionBodyTest.java#rotate` | `CollisionBodyCoverageTest.rotate` |
| `collision/AbstractCollisionBodyTest.java#shiftCoordinates` | `CollisionBodyCoverageTest.shiftCoordinates` |
| `collision/AbstractCollisionBodyTest.java#translate` | `CollisionBodyCoverageTest.translate` |
| `collision/AbstractCollisionBodyTest.java#copy` | `CollisionBodyCoverageTest.copy` |
| `collision/AbstractCollisionBodyTest.java#copyNotOverridden` | `CollisionBodyCoverageTest.copyNotOverridden` |
| `collision/AbstractCollisionItemTest.java#hashCodeTest` | `CollisionItemPairCoverageTest.abstractItemHashCodeTest` |
| `collision/AbstractCollisionItemTest.java#equalsTest` | `CollisionItemPairCoverageTest.abstractItemEqualsTest` |
| `collision/AbstractCollisionItemTest.java#mapTest` | `CollisionItemPairCoverageTest.abstractItemMapTest` |
| `collision/AbstractCollisionPairCollisionBodyTest.java#hashCodeTest` | `CollisionItemPairCoverageTest.abstractBodyPairHashCodeTest` |
| `collision/AbstractCollisionPairCollisionBodyTest.java#equalsTest` | `CollisionItemPairCoverageTest.abstractBodyPairEqualsTest` |
| `collision/AbstractCollisionPairCollisionBodyTest.java#mapTest` | `CollisionItemPairCoverageTest.abstractBodyPairMapTest` |
| `collision/AbstractCollisionPairCollisionItemTest.java#hashCodeTest` | `CollisionItemPairCoverageTest.abstractItemPairHashCodeTest` |
| `collision/AbstractCollisionPairCollisionItemTest.java#equalsTest` | `CollisionItemPairCoverageTest.abstractItemPairEqualsTest` |
| `collision/AbstractCollisionPairCollisionItemTest.java#mapTest` | `CollisionItemPairCoverageTest.abstractItemPairMapTest` |
| `collision/AxisAlignedBoundsTest.java#create` | `BoundsCoverageTest.axisCreate` |
| `collision/AxisAlignedBoundsTest.java#createZeroWidth` | `BoundsCoverageTest.axisCreateZeroWidth` |
| `collision/AxisAlignedBoundsTest.java#createZeroHeight` | `BoundsCoverageTest.axisCreateZeroHeight` |
| `collision/AxisAlignedBoundsTest.java#createNegativeWidth` | `BoundsCoverageTest.axisCreateNegativeWidth` |
| `collision/AxisAlignedBoundsTest.java#createNegativeHeight` | `BoundsCoverageTest.axisCreateNegativeHeight` |
| `collision/AxisAlignedBoundsTest.java#getBounds` | `BoundsCoverageTest.axisGetBounds` |
| `collision/AxisAlignedBoundsTest.java#print` | `BoundsCoverageTest.axisPrint` |
| `collision/AxisAlignedBoundsTest.java#isOutsideCircle` | `BoundsCoverageTest.axisIsOutsideCircle` |
| `collision/AxisAlignedBoundsTest.java#isOutsideEllipse` | `BoundsCoverageTest.axisIsOutsideEllipse` |
| `collision/AxisAlignedBoundsTest.java#isOutsideRectangle` | `BoundsCoverageTest.axisIsOutsideRectangle` |
| `collision/AxisAlignedBoundsTest.java#isOutsidePolygon` | `BoundsCoverageTest.axisIsOutsidePolygon` |
| `collision/AxisAlignedBoundsTest.java#isOutsideTriangle` | `BoundsCoverageTest.axisIsOutsideTriangle` |
| `collision/AxisAlignedBoundsTest.java#isOutsideSegment` | `BoundsCoverageTest.axisIsOutsideSegment` |
| `collision/AxisAlignedBoundsTest.java#isOutsideAABB` | `BoundsCoverageTest.axisIsOutsideAABB` |
| `collision/AxisAlignedBoundsTest.java#copy` | `BoundsCoverageTest.axisCopy` |
| `collision/BasicCollisionItemTest.java#create` | `CollisionItemPairCoverageTest.basicItemCreate` |
| `collision/BasicCollisionItemTest.java#copy` | `CollisionItemPairCoverageTest.basicItemCopy` |
| `collision/BasicCollisionPairCollisionBodyTest.java#create` | `CollisionItemPairCoverageTest.basicBodyPairCreate` |
| `collision/BasicCollisionPairCollisionBodyTest.java#hashcodeEquals` | `CollisionItemPairCoverageTest.basicBodyPairHashcodeEquals` |
| `collision/BasicCollisionPairCollisionBodyTest.java#copy` | `CollisionItemPairCoverageTest.basicBodyPairCopy` |
| `collision/BasicCollisionPairCollisionItemTest.java#create` | `CollisionItemPairCoverageTest.basicItemPairCreate` |
| `collision/BasicCollisionPairCollisionItemTest.java#hashcodeEquals` | `CollisionItemPairCoverageTest.basicItemPairHashcodeEquals` |
| `collision/BasicCollisionPairCollisionItemTest.java#copy` | `CollisionItemPairCoverageTest.basicItemPairCopy` |
| `collision/CategoryFilterTest.java#create` | `FilterFixtureCoverageTest.categoryCreate` |
| `collision/CategoryFilterTest.java#equalsAndHashCode` | `FilterFixtureCoverageTest.categoryEqualsAndHashCode` |
| `collision/CategoryFilterTest.java#filter` | `FilterFixtureCoverageTest.categoryFilter` |
| `collision/CategoryFilterTest.java#tostring` | `FilterFixtureCoverageTest.categoryTostring` |
| `collision/CategoryFilterTest.java#copy` | `FilterFixtureCoverageTest.categoryCopy` |
| `collision/CollisionsTest.java#estimates` | `CollisionSupportCoverageTest.estimates` |
| `collision/DefaultFilterTest.java#filter` | `FilterFixtureCoverageTest.defaultFilter` |
| `collision/DefaultFilterTest.java#tostring` | `FilterFixtureCoverageTest.defaultTostring` |
| `collision/DefaultFilterTest.java#copy` | `FilterFixtureCoverageTest.defaultCopy` |
| `collision/FixtureTest.java#createSuccess` | `FilterFixtureCoverageTest.fixtureCreateSuccess` |
| `collision/FixtureTest.java#createNullFixture` | `FilterFixtureCoverageTest.fixtureCreateNullFixture` |
| `collision/FixtureTest.java#getShape` | `FilterFixtureCoverageTest.fixtureGetShape` |
| `collision/FixtureTest.java#tostring` | `FilterFixtureCoverageTest.fixtureTostring` |
| `collision/FixtureTest.java#getSetFilter` | `FilterFixtureCoverageTest.fixtureGetSetFilter` |
| `collision/FixtureTest.java#setNullFilter` | `FilterFixtureCoverageTest.fixtureSetNullFilter` |
| `collision/FixtureTest.java#getSetSensor` | `FilterFixtureCoverageTest.fixtureGetSetSensor` |
| `collision/FixtureTest.java#getSetUserData` | `FilterFixtureCoverageTest.fixtureGetSetUserData` |
| `collision/FixtureTest.java#copy` | `FilterFixtureCoverageTest.fixtureCopy` |
| `collision/TypeFilterTest.java#filter` | `FilterFixtureCoverageTest.typeFilter` |
| `collision/TypeFilterTest.java#copy` | `FilterFixtureCoverageTest.typeCopy` |
| `UnitConversionTest.java#footMeter` | `CollisionSupportCoverageTest.footMeter` |
| `UnitConversionTest.java#slugKilogram` | `CollisionSupportCoverageTest.slugKilogram` |
| `UnitConversionTest.java#poundKilogram` | `CollisionSupportCoverageTest.poundKilogram` |
| `UnitConversionTest.java#mpsToFps` | `CollisionSupportCoverageTest.mpsToFps` |
| `UnitConversionTest.java#poundNewton` | `CollisionSupportCoverageTest.poundNewton` |
| `UnitConversionTest.java#footPoundNewtonMeter` | `CollisionSupportCoverageTest.footPoundNewtonMeter` |
| `exception/ExceptionsTest.java#newCannotBeEqualException` | `CollisionSupportCoverageTest.newCannotBeEqualException` |
| `exception/ExceptionsTest.java#newCannotBeEqualException2` | `CollisionSupportCoverageTest.newCannotBeEqualException2` |
| `exception/ExceptionsTest.java#newEmptyCollectionException` | `CollisionSupportCoverageTest.newEmptyCollectionException` |
| `exception/ExceptionsTest.java#newGreaterThanException` | `CollisionSupportCoverageTest.newGreaterThanException` |
| `exception/ExceptionsTest.java#newGreaterThanOrEqualException` | `CollisionSupportCoverageTest.newGreaterThanOrEqualException` |
| `exception/ExceptionsTest.java#newIndexOutOfBoundsException` | `CollisionSupportCoverageTest.newIndexOutOfBoundsException` |
| `exception/ExceptionsTest.java#newLessThanException` | `CollisionSupportCoverageTest.newLessThanException` |
| `exception/ExceptionsTest.java#newLessThanOrEqualException` | `CollisionSupportCoverageTest.newLessThanOrEqualException` |
| `exception/ExceptionsTest.java#newNullElementException` | `CollisionSupportCoverageTest.newNullElementException` |
| `exception/ExceptionsTest.java#newNullElementExceptionWithIndex` | `CollisionSupportCoverageTest.newNullElementExceptionWithIndex` |
| `exception/ExceptionsTest.java#newNullPointerException` | `CollisionSupportCoverageTest.newNullPointerException` |
| `exception/ExceptionsTest.java#newObjectsEqualException` | `CollisionSupportCoverageTest.newObjectsEqualException` |
| `exception/ExceptionsTest.java#newValueLessThanValueException` | `CollisionSupportCoverageTest.newValueLessThanValueException` |
| `exception/ExceptionsTest.java#newValueGreaterThanValueException` | `CollisionSupportCoverageTest.newValueGreaterThanValueException` |

## Pinned source hashes

| Source under `src/test/java/org/dyn4j/` | SHA-256 | Methods |
| --- | --- | ---: |
| `collision/AbstractBoundsTest.java` | `73304f61e82baa9ec3498024b54ee8c51c26a4f6aafe65f27b6af42b0a76f349` | 3 |
| `collision/AbstractCollisionBodyTest.java` | `83fb1935c9939ec88a3d0423a8ea5826f616aba0aff19b78c8aea4e40dd0d61e` | 39 |
| `collision/AbstractCollisionItemTest.java` | `46cb9ab32385609bd5b6ba54af2dcebf586dad4e65c35a6add6a66622f8e9358` | 3 |
| `collision/AbstractCollisionPairCollisionBodyTest.java` | `fe3abd86f5f5245e91e4bb47302015e4da13df331e4ef0db9e3d46847789d1b4` | 3 |
| `collision/AbstractCollisionPairCollisionItemTest.java` | `3f4f4df33a7df5eecdd36430cfa33bb05e41e89808de387b829a04ea053d270e` | 3 |
| `collision/AxisAlignedBoundsTest.java` | `80e1a13ef1068ee411b7985c22dd6ff4e52d5c0494982e4a13d0d44afae56403` | 15 |
| `collision/BasicCollisionItemTest.java` | `073345a5fd1f9063b2ba1e6e9db3f8495d6c240e1991beaaf4b7cb4bb1c68950` | 2 |
| `collision/BasicCollisionPairCollisionBodyTest.java` | `a45c52a95daf94f48864280dc4938bad063064126054b1bd2f8b605e40217a8a` | 3 |
| `collision/BasicCollisionPairCollisionItemTest.java` | `077014f39c2b4f0935275c9160f6e96c4a37e8c6bf7e8d47b9d2b4f8d3dca19a` | 3 |
| `collision/CategoryFilterTest.java` | `d3a8479b5dd6e567c7611fe179e13a82d28d83ed6ce09d9467a8ab37484d68ab` | 5 |
| `collision/CollisionsTest.java` | `2d2f34d7f685f000d072109425f12d1a5f0fe34482618b0191deffce66376dc6` | 1 |
| `collision/DefaultFilterTest.java` | `2a1efde55843254d5a4ea516f41518a346c3ccd1647c637a427a06fe52f29c6f` | 3 |
| `collision/FixtureTest.java` | `8e28f350d41628e63c00039c91e42e6e4cf93ace1a0f340a10d6e920f552e41b` | 9 |
| `collision/TypeFilterTest.java` | `6cdbda49378402d1d364ad7ae531f7c4c6fb3f53f33d604ca02fb38b5ea9ef27` | 2 |
| `UnitConversionTest.java` | `357783c9e9150a5c8e48963ab3b974fe638317c11340cb29c424431c4669beba` | 6 |
| `exception/ExceptionsTest.java` | `17e6443aa3e2b27443255dd7fe2cd4bfbbd03354c42ded4cd5f4332a834a74df` | 14 |

`collision/TestCollisionBody.java` has SHA-256 `d930f676b6f23a747edcc7e434028bb9e7d3212959a4cabe367e27c2a739fc1f`. All original source bytes remain in the pinned checkout; no generated fixture replaces them.

## Behavior and dispositions

The identity table above is complete: 114 distinct pinned Java methods, 114 distinct mapped portable methods, and nine supplemental portable methods. A set comparison against the baseline JUnit XML found zero missing or extra original identities; each final host XML contains all 114 mapped methods and nine supplemental methods. No original test identity is waived. The pinned TestCollisionBody.java helper contributes zero JUnit methods.

The portable cases exercise fixture/filter/bounds ownership, independent copies, object identity, public body operations, live fixture views, fail-fast iterators and nested sublists, callback re-entry, getter evaluation order, virtual copy, and null at the point of use. The root collision AbstractCollisionBodyTest.addNullConvex calls CoverageBody.addFixture(null as Convex?) exactly as the pinned Java TestBody calls addFixture((Convex) null). Both reach Fixture(null) and throw ArgumentNullException with message "shape cannot be null" before insertion; the portable case also checks fixture count zero. The dynamics body probe in the source owner's separate report produces "convex cannot be null" for a different body implementation; that is not this root collision identity.

The nine pinned FixtureTest methods run independently on baseline and candidate JVM, and their nine mapped common counterparts run on every host. The outcomes cover successful construction, null shape error, shape identity, string representation, filter identity, null filter error, sensor mutation, user-data identity/reset, and deep shape/filter copy with cleared user data. All nine passed in each lane. The separate body addNullConvex identity passed on both Java JVM lanes and every portable host. The 19 portable FilterFixtureCoverageTest methods include these nine fixture cases; their XML is listed below.

Two Java-specific behavior fragments remain executed by unchanged JVM tests: Java List.add/remove on the body fixture view in AbstractCollisionBodyTest.getFixturesAndAdd/getFixturesAndRemove, and Java static helper hiding in Issue35StaticHideConsumer. The two original view identities are still mapped to common tests of the read-only Kotlin List contract; live view and mutation/fail-fast behavior are exercised by supplemental common tests. These are fragment dispositions, not omitted Java identities or skipped tests.

## Verification identity and environment

- Active model: gpt-6-sol, raw session 01a14b38-bc97-7680-8f59-af16a284b75a, turn 01a14b5e-881b-7661-979a-ac83c617a960.
- Verified build/source tree before this documentation update: 4cdd9c1d8082f57ac37ba87d1ebf1d1f4463c8d0. It contains reviewed collision source abef13d59ed31214019b09c8fc08ea047d50daa6 and the then-current integration 5457e52. The final documentation commit changes no source or build input.
- Pinned upstream source SHA: 058bf6d982a0fb89b54050f929f6ea9dae53b714. Common test source SHA-256: 742787ad7e6adc71bec7b76d05dfba8916cf8758dae070a622e5cd229507f4c1. The pinned original source file hashes remain in the table above.
- Baseline dyn4j 6.0.0 binary SHA-256: 204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e. Built and staged JVM JAR SHA-256: 8d295feb72e218a61985532e4333fd4ff3975cc176a5472770976825348d451b. Staged Android AAR: 7245eae1f4bc1c3a9a9c056ce5445da5443f62e858d1f812076697ee0c13217f. Extracted staged Android classes JAR: b186e4309a7400b9646076110856b50515dd0b0ea1e14c00922a749568cb1591.
- Host: Bazzite 44, Linux 7.2.9-ogc3.1.fc44.x86_64, x86_64; Gradle 9.5.0, Kotlin/KGP 2.4.20, JBR OpenJDK 21.0.9+10-b895.147. KGP Node 24.16.0 ran JS Node; Node 26.2.0 ran Wasm JS and Wasm WASI. Android host is a JDK classpath test, not device execution.
- The final combined Gradle log is /tmp/dyn4k-collision-corpus-evidence/gradle-final-after-integration.log, SHA-256 ec99a3694662852b1f3545a4cdcb7552e546f3e58a8b2dda1eb8e56fda372abc.

## Red/green sensitivity

A temporary wrong message expectation, "convex cannot be null", on the actual CoverageBody.addFixture(null as Convex?) call caused the targeted JVM case to fail with a JUnit ComparisonFailure: actual "shape cannot be null". The red raw XML is /tmp/dyn4k-collision-corpus-evidence/red/TEST-org.dyn4j.coverage.collision.model.CollisionBodyCoverageTest.xml, SHA-256 8d9b4e57dbca22f94f26e14a74d7664a2d16eaea433b609b2420db45d5c0d406. The expected message was restored to the pinned Fixture constructor result. All final host XMLs below are green.

The targeted red command used the three environment variables below and:

    ./gradlew :dyn4k-core:jvmTest --tests 'org.dyn4j.coverage.collision.model.CollisionBodyCoverageTest.addNullConvex' --offline --rerun-tasks --console=plain

## Original Java and consumers

The unchanged 16 original Java test classes compiled with javac --release 8 and ran separately against the baseline and candidate JARs through the JUnit 4.13.2 XML runner. Each raw XML has 114 cases, zero failures and zero skipped tests. Both XMLs have SHA-256 54734dda1f47158de307210bc76f6474c15274859885e61ca9ba4e082fd72d65 and are at /tmp/dyn4k-collision-corpus-evidence/baseline-original.xml and candidate-original.xml. The independent Gradle task runUpstreamCollisionModelTests also printed OK (114 tests) using JUnit 4.13.1.

The unchanged CollisionModelConsumer.java compiled with javac --release 8 and ran four times against baseline, candidate, staged JVM, and staged Android classes on the JDK host. Each printed collision consumer checks=75. The identical Kotlin consumer source (SHA-256 c9a940bb25b28dbe4fcba944d5b49e9e03c74b283c393444d5892a28b4e1541b) compiled and ran against baseline, direct candidate JAR, and staged JVM JAR in three isolated temporary Gradle projects. Each printed staged Kotlin checks=7. Its source was unchanged; only dependency coordinates/path were selected per lane. Logs are retained in /tmp/dyn4k-collision-corpus-evidence/.

The strict tools/baseline/verify.py comparison selected all 17 root collision top-level types and seven owned support/exception types. It compared 24 types and 221 pinned public/protected declarations on each of the staged JVM and extracted staged Android class JARs. Both returned zero missing types, signature mismatches, and compatible differences. The executable command and result are retained at /tmp/dyn4k-collision-corpus-evidence/verify-signatures.py (SHA-256 8d57e0e23803a2a8881b9a38584e9e8a5c784f5eab756ee94ec19c86832d6a8a) and signatures-final.log (SHA-256 df193671307b8d0661411163de82dc000591e6ce6ae7eb0ef45a08472cf53bf4).

## Common runtime lanes

The six requested host tasks each executed 123 portable collision corpus cases: bounds 18, body 45, item/pair 20, support 21, filter/fixture 19. Each also executed 22 existing CollisionModelTest cases, for 145 collision-slice cases. Every lane had zero failures, errors, and skips. The earlier Linux x64 SIGSEGV and JS/Wasm null-point failures were absent after the reviewed source repair. Other geometry tests also ran in these Gradle tasks; their counts are outside this collision-slice ledger.

| Host task | Portable corpus | Existing collision | Total collision slice | Failures | Errors | Skips | Result |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| jvmTest | 123 | 22 | 145 | 0 | 0 | 0 | PASS |
| linuxX64Test | 123 | 22 | 145 | 0 | 0 | 0 | PASS |
| jsNodeTest | 123 | 22 | 145 | 0 | 0 | 0 | PASS |
| wasmJsNodeTest | 123 | 22 | 145 | 0 | 0 | 0 | PASS |
| wasmWasiNodeTest | 123 | 22 | 145 | 0 | 0 | 0 | PASS |
| testAndroidHostTest | 123 | 22 | 145 | 0 | 0 | 0 | PASS |

### Exact commands

All repository Gradle runs used JAVA_HOME=/var/home/stewart/.gradle/jdks/jetbrains_s_r_o_-21-amd64-linux.2, ANDROID_HOME=/var/home/stewart/Android/Sdk, and ANDROID_SDK_ROOT=/var/home/stewart/Android/Sdk. The final combined command was:

    ./gradlew :dyn4k-core:jvmTest :dyn4k-core:linuxX64Test :dyn4k-core:jsNodeTest :dyn4k-core:wasmJsNodeTest :dyn4k-core:wasmWasiNodeTest :dyn4k-core:testAndroidHostTest :dyn4k-core:runUpstreamCollisionModelTests :dyn4k-core:runBaselineCollisionModelConsumer :dyn4k-core:runCandidateCollisionModelConsumer :dyn4k-core:runStagedCollisionModelConsumer :dyn4k-core:runAndroidCollisionModelConsumer :dyn4k-core:publishAndroidPublicationToStagingRepository --offline --rerun-tasks --continue --console=plain

The independent original Java command was:

    bash /tmp/dyn4k-portable-collision-model-evidence/run-original.sh

The strict staged signature command, after extracting classes.jar from the staged Android AAR, was:

    PATH=/var/home/stewart/.gradle/jdks/jetbrains_s_r_o_-21-amd64-linux.2/bin:$PATH PYTHONDONTWRITEBYTECODE=1 python3 /tmp/dyn4k-collision-corpus-evidence/verify-signatures.py

Each Kotlin consumer lane used the same command shape with baseline-kotlin, candidate-kotlin, or staged-kotlin as project directory:

    JAVA_HOME=/var/home/stewart/.gradle/jdks/jetbrains_s_r_o_-21-amd64-linux.2 ./gradlew -p /tmp/dyn4k-collision-corpus-evidence/staged-kotlin run --offline --rerun-tasks --console=plain

## Raw collision XML

Each file below is an unmodified copy from dyn4k-core/build/test-results/<task>/ immediately after the final run. The base directory is /tmp/dyn4k-collision-corpus-evidence/final-xml/. All 36 files were counted directly from XML.

| Relative XML path | Cases | Failures | Errors | Skips | SHA-256 |
| --- | ---: | ---: | ---: | ---: | --- |
| jvmTest/TEST-org.dyn4j.collision.CollisionModelTest.xml | 22 | 0 | 0 | 0 | 76e385d5e1902a6a2162e341e32b002fc8b82f0532f09e544367ea8f0aae5a9b |
| jvmTest/TEST-org.dyn4j.coverage.collision.model.BoundsCoverageTest.xml | 18 | 0 | 0 | 0 | 32be7398eaeab85d7185832b3b94696c59e1a352af1f5687c8412ead7e7f32dd |
| jvmTest/TEST-org.dyn4j.coverage.collision.model.CollisionBodyCoverageTest.xml | 45 | 0 | 0 | 0 | 53a8d72aa026eb1a2d7fda2524cb0ca6b2cf8dc2c05cd90a7f350bd563a27fea |
| jvmTest/TEST-org.dyn4j.coverage.collision.model.CollisionItemPairCoverageTest.xml | 20 | 0 | 0 | 0 | c3aaa01bf74c7c0c656fc78486980c40ec481590130162c1dc98b1690fdd92bb |
| jvmTest/TEST-org.dyn4j.coverage.collision.model.CollisionSupportCoverageTest.xml | 21 | 0 | 0 | 0 | 4e5078aab1ee568db931d708042a9f92a0b8be46bb58cb1cad26561eb2e89266 |
| jvmTest/TEST-org.dyn4j.coverage.collision.model.FilterFixtureCoverageTest.xml | 19 | 0 | 0 | 0 | 4c4f61425ddb39ad07b6ffc3eeb9b6e9ec05f9e406ef7a7eb9fdaba76b409355 |
| linuxX64Test/TEST-linuxX64Test.org.dyn4j.collision.CollisionModelTest.xml | 22 | 0 | 0 | 0 | e5619e2334ba5c361c879e1839517bbfec7179a7064b525d58304d6fa03498bd |
| linuxX64Test/TEST-linuxX64Test.org.dyn4j.coverage.collision.model.BoundsCoverageTest.xml | 18 | 0 | 0 | 0 | a01956700026c120519efeecaa1385beb45e3b091e2155c4f30bcd0de762558d |
| linuxX64Test/TEST-linuxX64Test.org.dyn4j.coverage.collision.model.CollisionBodyCoverageTest.xml | 45 | 0 | 0 | 0 | f6350101077c403599e57fbc7ba12f9eb48fdb9c9a0e7dd88977f7ba4025978e |
| linuxX64Test/TEST-linuxX64Test.org.dyn4j.coverage.collision.model.CollisionItemPairCoverageTest.xml | 20 | 0 | 0 | 0 | 5ce08b7daf22358b10d6965fcf8550434a5c2f2c4c4d3a8a29dfd136012c900d |
| linuxX64Test/TEST-linuxX64Test.org.dyn4j.coverage.collision.model.CollisionSupportCoverageTest.xml | 21 | 0 | 0 | 0 | c1e4284022257d67e9aea8bdde533f31f915a472f31c2db6b4d30bb72caebb6b |
| linuxX64Test/TEST-linuxX64Test.org.dyn4j.coverage.collision.model.FilterFixtureCoverageTest.xml | 19 | 0 | 0 | 0 | f7dd091b09e8763bb1db23d02496a446595be4daabe7ebe9b30f6e864e9108fa |
| jsNodeTest/TEST-jsNodeTest.org.dyn4j.collision.CollisionModelTest.xml | 22 | 0 | 0 | 0 | 0d2501a1c72ffa1c8ee0ae5fe6e543eb48e03927e339c6cd45dc2b08cf4cc3ab |
| jsNodeTest/TEST-jsNodeTest.org.dyn4j.coverage.collision.model.BoundsCoverageTest.xml | 18 | 0 | 0 | 0 | dd8bf2c900ef25348adfd737b66976e06213319983783b8d53099087755cec0e |
| jsNodeTest/TEST-jsNodeTest.org.dyn4j.coverage.collision.model.CollisionBodyCoverageTest.xml | 45 | 0 | 0 | 0 | 2bd4f247f001186193be7580f6d5cc3fef1c54cbcc66799bc77621b319f20c94 |
| jsNodeTest/TEST-jsNodeTest.org.dyn4j.coverage.collision.model.CollisionItemPairCoverageTest.xml | 20 | 0 | 0 | 0 | 18f2d8c3d7cb72a800faf0c4bbbefca1d2aebfcbea9d0cae7e317fc91f398fc7 |
| jsNodeTest/TEST-jsNodeTest.org.dyn4j.coverage.collision.model.CollisionSupportCoverageTest.xml | 21 | 0 | 0 | 0 | 27ec72ccd01849e6703b5505a67b3d6b749b9a0c3b392e5c15c0650320705225 |
| jsNodeTest/TEST-jsNodeTest.org.dyn4j.coverage.collision.model.FilterFixtureCoverageTest.xml | 19 | 0 | 0 | 0 | 87b762939156dd02f4c75ffe3a675dfc1c0a5d76ca751efb36bb8c202768a689 |
| wasmJsNodeTest/TEST-wasmJsNodeTest.org.dyn4j.collision.CollisionModelTest.xml | 22 | 0 | 0 | 0 | 93d0a0b67a2b554e33ebebbfa275c1cd486c90be46bc25ddd67dbf893b4737e8 |
| wasmJsNodeTest/TEST-wasmJsNodeTest.org.dyn4j.coverage.collision.model.BoundsCoverageTest.xml | 18 | 0 | 0 | 0 | 084b3c40ec4afc29a83edc7a434c291329a154cdc6947731066e924506b9c4bb |
| wasmJsNodeTest/TEST-wasmJsNodeTest.org.dyn4j.coverage.collision.model.CollisionBodyCoverageTest.xml | 45 | 0 | 0 | 0 | 6ed35cab7201601bab3d6e1a340c06a112576b8854e45b08a8061146739f1d38 |
| wasmJsNodeTest/TEST-wasmJsNodeTest.org.dyn4j.coverage.collision.model.CollisionItemPairCoverageTest.xml | 20 | 0 | 0 | 0 | afb8b2c5cf1eaca52c479b3e614af46f90aa3937bb4608a21e5de1deb4c98af2 |
| wasmJsNodeTest/TEST-wasmJsNodeTest.org.dyn4j.coverage.collision.model.CollisionSupportCoverageTest.xml | 21 | 0 | 0 | 0 | 328d2a54f0c168586ada0430b3dac7f46bf7c729389d5d67c2de481595a44415 |
| wasmJsNodeTest/TEST-wasmJsNodeTest.org.dyn4j.coverage.collision.model.FilterFixtureCoverageTest.xml | 19 | 0 | 0 | 0 | de7e9a0f1de3833c3fc1f80882759d7e3e513d79399afa78711ee729383cde0e |
| wasmWasiNodeTest/TEST-wasmWasiNodeTest.org.dyn4j.collision.CollisionModelTest.xml | 22 | 0 | 0 | 0 | ae7f4d26875d6fe10bcabe0493d032da0a3af555eed4fb5920e737ce8756ccf6 |
| wasmWasiNodeTest/TEST-wasmWasiNodeTest.org.dyn4j.coverage.collision.model.BoundsCoverageTest.xml | 18 | 0 | 0 | 0 | 755f0de5f26f1e6cacf88506824fb46899a11fc29e7bcd123eea6abc26403108 |
| wasmWasiNodeTest/TEST-wasmWasiNodeTest.org.dyn4j.coverage.collision.model.CollisionBodyCoverageTest.xml | 45 | 0 | 0 | 0 | 58ff6f0b964166cb94d630469e701701fc95739dd66e678b42d5c6f659e7f48b |
| wasmWasiNodeTest/TEST-wasmWasiNodeTest.org.dyn4j.coverage.collision.model.CollisionItemPairCoverageTest.xml | 20 | 0 | 0 | 0 | e9d12079b4ca2997eac6d9e81cd98b13624b948d3edaa199080c82cea6b73147 |
| wasmWasiNodeTest/TEST-wasmWasiNodeTest.org.dyn4j.coverage.collision.model.CollisionSupportCoverageTest.xml | 21 | 0 | 0 | 0 | a76db2d8123d63ffed43315e1485b6848960d36632cfa9032461365bb80fd79c |
| wasmWasiNodeTest/TEST-wasmWasiNodeTest.org.dyn4j.coverage.collision.model.FilterFixtureCoverageTest.xml | 19 | 0 | 0 | 0 | 7565eaad3de7e537a81c8729bca89799d81b1b08cca783182ac1ef8e85ef4392 |
| testAndroidHostTest/TEST-org.dyn4j.collision.CollisionModelTest.xml | 22 | 0 | 0 | 0 | 5ab249503815261b4505695074f01862dbb14d32014f090f730215e8c0b1b6f5 |
| testAndroidHostTest/TEST-org.dyn4j.coverage.collision.model.BoundsCoverageTest.xml | 18 | 0 | 0 | 0 | 2bd0ddb783013280195dd8f93b6a235f1c868a3f10e80b4f006f051fcb81e37d |
| testAndroidHostTest/TEST-org.dyn4j.coverage.collision.model.CollisionBodyCoverageTest.xml | 45 | 0 | 0 | 0 | 273b15d91d5d2cec18640725e2ba5ff702c59f1458f9afeed0ae0f49bc91ca6f |
| testAndroidHostTest/TEST-org.dyn4j.coverage.collision.model.CollisionItemPairCoverageTest.xml | 20 | 0 | 0 | 0 | 8ffe18ac88178b1efdec541af31f0b53127d2f16cd74a2b05dddb4a1da316a6a |
| testAndroidHostTest/TEST-org.dyn4j.coverage.collision.model.CollisionSupportCoverageTest.xml | 21 | 0 | 0 | 0 | c12efc9b6eb64c9ac6350ee8eb9be48b1ee600064acbbc6e6641dcbfe921a475 |
| testAndroidHostTest/TEST-org.dyn4j.coverage.collision.model.FilterFixtureCoverageTest.xml | 19 | 0 | 0 | 0 | e6f5234ad23c1256c81ce14f32707b1f5cc8784a4e24383c4e9d202683a1782d |

## Qualification boundary

These are six host runtime results plus unchanged JVM source consumers, not full 21-target qualification. Android device, browser, Apple, Windows, Linux ARM64, other native targets, and remaining runtime combinations are NOT_RUN for this slice. The frozen core-* qualification manifest does not yet include these new common tests; integration must update it and execute its gates before making a full qualification claim. The pinned source, fixtures, and BSD legal notices remain intact. [Use baseline filters, bounds, and collision objects from consumers](https://github.com/rubixhacker/dyn4k/issues/35) and [Run the full compatibility corpus and unchanged migration applications](https://github.com/rubixhacker/dyn4k/issues/42) remain open.
