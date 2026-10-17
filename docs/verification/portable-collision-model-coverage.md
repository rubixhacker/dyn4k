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

The portable cases exercise public fixture, filter, bounds, item, pair, body, unit conversion, and exception APIs. Nine additional common cases exercise live views, fail-fast iterators and nested sublists, null at point of use, callback re-entry, virtual copy, and getter evaluation order. `getFixturesAndAdd` and `getFixturesAndRemove` use a Kotlin read-only `List` counterpart. The original Java `List.add/remove` exception behavior remains in the unchanged Java suites because that mutator interface is Java/JVM-specific. The unchanged `Issue35StaticHideConsumer.java` separately proves Java static helper hiding; there is no corresponding portable Kotlin static hiding operation. No original helper is waived merely because it uses Java collections.

`AbstractCollisionBodyTest.addNullConvex` remains an exact JVM source case. Its public common signature takes non-null `Convex`, so common Kotlin cannot pass a null reference into the method. The mapped common test checks the nullable `Fixture` constructor reached by the normal body implementation. This is partial portable evidence for that one identity, not proof of the Java call path. The unchanged Java suite covers the actual call. The integration owner must decide whether a nullable common signature is required to make this case portable.

## Verification

### Exact tree and environment

- Author model verified from this session's active `turn_context`: `gpt-6-sol`, turn `01a14b38-bd61-75d1-a18f-06c6bda44d0e`.
- Verified tree commit: `1838472ca42ccba17fe8f13396b43484890c8542`. Test source commit: `8a0a526eacf43f5caf5c1a50310b939c20ae7b6b`; pinned collision dependency: `134b8dc691849fcc51e45229a3d950bff895412a`; merged integration: `ec2b14baafbe4672b7c9799144354a1a943e7744`.
- Common test source SHA-256: `0e4bf6c652d64c898b25650db994027e1ced5a3154874d559db97328aea46bab`.
- Candidate JVM JAR SHA-256: `223eaa1fd59234712e90804b4485864974fc5b0986d4c3a12e8cec3b1986c0d3`.
- Pinned baseline binary SHA-256: `204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e`.
- Bazzite 44.20261012.0, Linux 7.2.9-ogc3.1.fc44.x86_64, x86_64; Gradle 9.5.0; Kotlin/KGP 2.4.20; OpenJDK JBR 21.0.9+10-b895.147. JS uses KGP Node 24.16.0; Wasm JS and Wasm WASI use KGP Node 26.2.0. Android host uses the local JDK host task, not an Android device.
- Raw Gradle log: `/tmp/dyn4k-portable-collision-model-evidence/gradle-final.log`, SHA-256 `0b8c6b6739948cc087dccfde15b1ebf71ba3be5aa8c9e401c5cc0f972f6d0571`.

### Original Java suites

The pinned original Java sources compiled with `javac --release 8` against the baseline binary and executed in a separate JVM. The unchanged sources also compiled through `:dyn4k-core:compileUpstreamCollisionModelTests` against the candidate and executed through `:dyn4k-core:runUpstreamCollisionModelTests`. A separate JUnit XML runner used JUnit 4.13.2 and Hamcrest 1.3 for both sides. Both executed **114/114** with zero failures and zero ignored tests. The raw baseline and candidate XML each have SHA-256 `54734dda1f47158de307210bc76f6474c15274859885e61ca9ba4e082fd72d65` and are saved in `/tmp/dyn4k-portable-collision-model-evidence/`. The Gradle candidate task used JUnit 4.13.1 and independently printed `OK (114 tests)`.

A same-source Java null probe compiled with `javac --release 8` returned `null` for an empty body and threw `java.lang.NullPointerException` after adding a fixture on both baseline and candidate JVM runs. This observation is separate from the original 114-case suite.

The unchanged collision consumer, including Java static helper hiding, printed `collision consumer checks=71` in each of four independent Gradle tasks: `runBaselineCollisionModelConsumer`, `runCandidateCollisionModelConsumer`, `runStagedCollisionModelConsumer`, and `runAndroidCollisionModelConsumer`. All four tasks exited successfully. The Android consumer is an Android class/JVM-host check; it does not establish device runtime behavior.

### Common runtime lanes

The expected new common count is 123: 114 mapped counterparts and nine supplemental cases. The full local suite also includes 20 pre-existing common tests. No XML reports a skipped case. Linux x64 stopped during the null probe, so two expected common cases were not executed; a zero skip counter does not make that lane complete.

| Runtime task | New cases executed | Full cases executed | Failures | Skips | Result |
| --- | ---: | ---: | ---: | ---: | --- |
| `jvmTest` | 123/123 | 143 | 0 | 0 | PASS |
| `linuxX64Test` | 121/123 | 141 | 1 | 0 | FAIL |
| `jsNodeTest` | 123/123 | 143 | 1 | 0 | FAIL |
| `wasmJsNodeTest` | 123/123 | 143 | 1 | 0 | FAIL |
| `wasmWasiNodeTest` | 123/123 | 143 | 1 | 0 | FAIL |
| `testAndroidHostTest` | 123/123 | 143 | 0 | 0 | PASS |

The sole remaining failure on each non-JVM lane is `CollisionBodyCoverageTest.supplementalNullPointIsDeferredUntilShapeUse`. Linux x64 exits with code 139 (`SIGSEGV`) and an `Unknown` XML failure. An isolated native run under GDB traces the null point from `AbstractCollisionBody.getFixture` at `CollisionBody.kt:179` through `Circle.contains` to a null `Vector2.x` dereference at `Vector2.kt:40`. The raw backtrace is `/tmp/dyn4k-portable-collision-model-evidence/native-null-gdb.log`, SHA-256 `084242f2bcc51cd177c8a3a5007781e0f36e39eb3d80459ae0df027ca525fc5a`. JS Node throws a JavaScript `TypeError`. Wasm JS and Wasm WASI throw `ClassCastException` for a null-to-`Vector2` cast. JVM and Android host throw the expected `NullPointerException`. The engine owner must repair and rerun this behavior; production code is outside this coverage branch.

All six requested local tasks were available. Android device, Apple, Windows, Linux ARM64, browser, and other qualification runtimes were not run for this slice. Their status is `NOT_RUN`, not pass or zero cases. The full support matrix remains open under the integration qualification work.

### Reproduction commands

The common and candidate Java run used this exact Gradle invocation, with `JAVA_HOME=/var/home/stewart/.gradle/jdks/jetbrains_s_r_o_-21-amd64-linux.2`, `ANDROID_HOME=/var/home/stewart/Android/Sdk`, and `ANDROID_SDK_ROOT=/var/home/stewart/Android/Sdk`:

```bash
./gradlew :dyn4k-core:jvmTest :dyn4k-core:linuxX64Test :dyn4k-core:jsNodeTest :dyn4k-core:wasmJsNodeTest :dyn4k-core:wasmWasiNodeTest :dyn4k-core:testAndroidHostTest :dyn4k-core:runUpstreamCollisionModelTests --offline --rerun-tasks --continue --info
```

The unchanged Java consumer tasks used the same three environment variables:

```bash
./gradlew :dyn4k-core:runBaselineCollisionModelConsumer :dyn4k-core:runCandidateCollisionModelConsumer :dyn4k-core:runStagedCollisionModelConsumer :dyn4k-core:runAndroidCollisionModelConsumer --offline --rerun-tasks --continue --quiet
```

The isolated native failure used the compiled test executable from the same Gradle run:

```bash
dyn4k-core/build/bin/linuxX64/debugTest/test.kexe '--ktest_filter=*supplementalNullPointIsDeferredUntilShapeUse*' --ktest_logger=SIMPLE
gdb --batch -ex run -ex 'bt 15' --args dyn4k-core/build/bin/linuxX64/debugTest/test.kexe '--ktest_filter=*supplementalNullPointIsDeferredUntilShapeUse*' --ktest_logger=SIMPLE
```

For the baseline, `javac --release 8` compiled `src/test/java/org/dyn4j/collision/*.java`, `UnitConversionTest.java`, and `exception/ExceptionsTest.java` from the pinned checkout against `dyn4j-6.0.0.jar`, JUnit 4.13.2, and Hamcrest 1.3. The separate `CollisionJUnitXml` runner invoked these 16 test classes in the order used by `runUpstreamCollisionModelTests`. The candidate runner used the same 16 names with the Gradle-compiled original class files, candidate JVM JAR, Kotlin stdlib 2.4.20, JUnit 4.13.2, and Hamcrest 1.3. The exact baseline/candidate compilation and execution command is `bash /tmp/dyn4k-portable-collision-model-evidence/run-original.sh`. The runner source, same-source null probe, XML, and Gradle log are retained in that directory.

### Raw XML hashes

Each row hashes the unmodified XML copied from `dyn4k-core/build/test-results/<task>/` to the evidence directory immediately after the exact-tree run. The first XML in each lane is the pre-existing common suite; the other five are the new corpus.

| Raw XML under evidence directory | Cases | Failures | SHA-256 |
| --- | ---: | ---: | --- |
| `jvmTest/TEST-org.dyn4j.collision.CollisionModelTest.xml` | 20 | 0 | `de1f1801162d68576b3bd544704b18a2fc56115665c651ebaa391aca0851b0b1` |
| `jvmTest/TEST-org.dyn4j.coverage.collision.model.BoundsCoverageTest.xml` | 18 | 0 | `656ccd554d0dd7452f30340397ec74d0b21d57a63f3b22c77b1ae6a3919ea027` |
| `jvmTest/TEST-org.dyn4j.coverage.collision.model.CollisionBodyCoverageTest.xml` | 45 | 0 | `36ac82d88da9734b5db5c975a91d37053af33eba1e5c211a06eab1d7a1730f81` |
| `jvmTest/TEST-org.dyn4j.coverage.collision.model.CollisionItemPairCoverageTest.xml` | 20 | 0 | `efb60cfaca8010076c3c358b66b84a7856b3a4255cd228918b462b1a6dcd1608` |
| `jvmTest/TEST-org.dyn4j.coverage.collision.model.CollisionSupportCoverageTest.xml` | 21 | 0 | `6da33147dfd76696d3471d03122b72db95863e08e507205e37c2cec74c1a1ad0` |
| `jvmTest/TEST-org.dyn4j.coverage.collision.model.FilterFixtureCoverageTest.xml` | 19 | 0 | `c53464a5d40ff60f40b143e7c8efc90034f618186da98f04bbdc93262ae15ef8` |
| `linuxX64Test/TEST-linuxX64Test.org.dyn4j.collision.CollisionModelTest.xml` | 20 | 0 | `94c0429c670cd05031107bcd81776984d0b07b9192c0629f5299fef4d51c7538` |
| `linuxX64Test/TEST-linuxX64Test.org.dyn4j.coverage.collision.model.BoundsCoverageTest.xml` | 18 | 0 | `d1e6669b521376d31d85db091bda0178f728764b056163b1295d0c92923f6667` |
| `linuxX64Test/TEST-linuxX64Test.org.dyn4j.coverage.collision.model.CollisionBodyCoverageTest.xml` | 43 | 1 | `a007d43c9e5702b6fd5ba37b3ccf73165b6ce8e535eadee56bd7536e2a6c950c` |
| `linuxX64Test/TEST-linuxX64Test.org.dyn4j.coverage.collision.model.CollisionItemPairCoverageTest.xml` | 20 | 0 | `9895785066d05f60b3442f71697ed31c2eacabe7ff212278edb703c048bf3af0` |
| `linuxX64Test/TEST-linuxX64Test.org.dyn4j.coverage.collision.model.CollisionSupportCoverageTest.xml` | 21 | 0 | `5d37fae99f6bf2e3ef55567cd1ee53f70370c748e7021f765300696b7343c83a` |
| `linuxX64Test/TEST-linuxX64Test.org.dyn4j.coverage.collision.model.FilterFixtureCoverageTest.xml` | 19 | 0 | `ab757ecabe235682f53838ac676dc1bf6198ecb86c375a02d182752999175528` |
| `jsNodeTest/TEST-jsNodeTest.org.dyn4j.collision.CollisionModelTest.xml` | 20 | 0 | `49c643eac44d99e1913628273cdfdaeec7981e1842ec03ef19ee790ed62a8424` |
| `jsNodeTest/TEST-jsNodeTest.org.dyn4j.coverage.collision.model.BoundsCoverageTest.xml` | 18 | 0 | `163cad9a6c2244599603a0049956274a032835afa37ebfe07c4d1b2109e91a20` |
| `jsNodeTest/TEST-jsNodeTest.org.dyn4j.coverage.collision.model.CollisionBodyCoverageTest.xml` | 45 | 1 | `2748adc9c535d87a64fc0965b47fec8915757096aa8c187eff9d765ed060727f` |
| `jsNodeTest/TEST-jsNodeTest.org.dyn4j.coverage.collision.model.CollisionItemPairCoverageTest.xml` | 20 | 0 | `9d68e9692a7ccc4a874fb9017d70551115739f0f96226ea0b54b9bc98bb221ef` |
| `jsNodeTest/TEST-jsNodeTest.org.dyn4j.coverage.collision.model.CollisionSupportCoverageTest.xml` | 21 | 0 | `007523f0b6f6a54ac533fe3e78175aea7c5af9401e7d7b7a5f247a1cd5fde67a` |
| `jsNodeTest/TEST-jsNodeTest.org.dyn4j.coverage.collision.model.FilterFixtureCoverageTest.xml` | 19 | 0 | `ad835b2af212e5e8a354d5254bdda1c656d86ea2fece856bc1c9c5368f99bc9e` |
| `wasmJsNodeTest/TEST-wasmJsNodeTest.org.dyn4j.collision.CollisionModelTest.xml` | 20 | 0 | `2c5253edb51d69458859eb6f416c4f733d9da1c5f2addae5a65ab9d5e4ca2060` |
| `wasmJsNodeTest/TEST-wasmJsNodeTest.org.dyn4j.coverage.collision.model.BoundsCoverageTest.xml` | 18 | 0 | `6582a8d1ee513871fd63901498586ff8d2484f991bdfc94b075af2f577984c5f` |
| `wasmJsNodeTest/TEST-wasmJsNodeTest.org.dyn4j.coverage.collision.model.CollisionBodyCoverageTest.xml` | 45 | 1 | `5d3e78c5575d6ec662925f8f6ff65ad56338b6b51c7ea3bbc6858ddbe3bc048b` |
| `wasmJsNodeTest/TEST-wasmJsNodeTest.org.dyn4j.coverage.collision.model.CollisionItemPairCoverageTest.xml` | 20 | 0 | `72f238b38324c27e1ee26b79a70bceac39ed55018a722bcd8936dae90a3d0f4b` |
| `wasmJsNodeTest/TEST-wasmJsNodeTest.org.dyn4j.coverage.collision.model.CollisionSupportCoverageTest.xml` | 21 | 0 | `979ce2bb9d14ae7182d2a6be4c27444cbdd78c232da9ddd36f1ca28d1015fd0b` |
| `wasmJsNodeTest/TEST-wasmJsNodeTest.org.dyn4j.coverage.collision.model.FilterFixtureCoverageTest.xml` | 19 | 0 | `134a0dd2020db177fd92a56220e8d8b9a5534243662418dfb801682725b6f9e7` |
| `wasmWasiNodeTest/TEST-wasmWasiNodeTest.org.dyn4j.collision.CollisionModelTest.xml` | 20 | 0 | `2cef65584ea194668b1e997642ac751a22e9a57f267d8324bbd294014b96aefb` |
| `wasmWasiNodeTest/TEST-wasmWasiNodeTest.org.dyn4j.coverage.collision.model.BoundsCoverageTest.xml` | 18 | 0 | `048a884c58307b90b7cc29800cab33abce0a607b8e91f3e1d6853e9618736a09` |
| `wasmWasiNodeTest/TEST-wasmWasiNodeTest.org.dyn4j.coverage.collision.model.CollisionBodyCoverageTest.xml` | 45 | 1 | `eb0ea70dbe30e4d444d68b7980191f3fade8fe46f0a4ee01ce6b7edd11e73a13` |
| `wasmWasiNodeTest/TEST-wasmWasiNodeTest.org.dyn4j.coverage.collision.model.CollisionItemPairCoverageTest.xml` | 20 | 0 | `e1e59139ece7b3f672b944c79e680ccf22127c10d94ec473656bd8042e007ac2` |
| `wasmWasiNodeTest/TEST-wasmWasiNodeTest.org.dyn4j.coverage.collision.model.CollisionSupportCoverageTest.xml` | 21 | 0 | `41250a8b5006e6c33e90c263c3f743d6fd0645c2e4df2b6c025efb38496edaa5` |
| `wasmWasiNodeTest/TEST-wasmWasiNodeTest.org.dyn4j.coverage.collision.model.FilterFixtureCoverageTest.xml` | 19 | 0 | `f9851c1ae8c138f04f321024d1e139162097d3d39d70abc34c8ba8d6b4504f99` |
| `testAndroidHostTest/TEST-org.dyn4j.collision.CollisionModelTest.xml` | 20 | 0 | `b891a95604c161c452c7b8ff3edd6150a8f56d193924dfdc20a25b2d1637e8fe` |
| `testAndroidHostTest/TEST-org.dyn4j.coverage.collision.model.BoundsCoverageTest.xml` | 18 | 0 | `faa88656fac14dfecaafb800169116120de8c2668ae26be7d3c71972e46f274d` |
| `testAndroidHostTest/TEST-org.dyn4j.coverage.collision.model.CollisionBodyCoverageTest.xml` | 45 | 0 | `a971f11ce1d65e2d558c8205cffb010a9e4697da6919f426e360915c4f31ac8b` |
| `testAndroidHostTest/TEST-org.dyn4j.coverage.collision.model.CollisionItemPairCoverageTest.xml` | 20 | 0 | `4f959eba915dc85f6699f000f4c9f80439d79438de1fea15974407b12a4b02cd` |
| `testAndroidHostTest/TEST-org.dyn4j.coverage.collision.model.CollisionSupportCoverageTest.xml` | 21 | 0 | `c6c57d2dc8277cfce053852f2474b682e5d75229fe6f63ba59ea4a8c12f36bb7` |
| `testAndroidHostTest/TEST-org.dyn4j.coverage.collision.model.FilterFixtureCoverageTest.xml` | 19 | 0 | `3964ad7ab9ca623f93f5275c2e255d32e03c986781826a8bb2c5a35876f356b9` |

The frozen `core-*` qualification manifest does not include this new common-test subtree. Updating it and rerunning all qualification lanes are integration dependencies. This report is bounded local corpus evidence, not full target qualification.
