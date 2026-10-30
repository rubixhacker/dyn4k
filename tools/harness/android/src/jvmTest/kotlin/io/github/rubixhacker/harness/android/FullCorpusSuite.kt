package io.github.rubixhacker.harness.android

import de.infix.testBalloon.framework.core.testSuite
import java.nio.file.Files
import java.nio.file.Path
import java.util.zip.ZipFile
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

private val CORPUS_CASES = listOf(
    SuiteCase(
        "dyn4k-core:org.dyn4j.CoreTest#works",
        "dyn4k-core",
        "org.dyn4j.CoreTest",
        "works",
        "portable",
    ),
    SuiteCase(
        "dyn4k:io.github.FacadeTest#works",
        "dyn4k",
        "io.github.FacadeTest",
        "works",
        "portable",
    ),
)

/** Writes the two raw JUnit reports `verify_jvm_xml` reads. */
private fun writeJvmXml(
    root: Path,
    module: String,
    classname: String,
    method: String,
    suffix: String = "",
    fileName: String = "TEST-$classname.xml",
): Path = writeFile(
    root,
    "$module/build/test-results/jvmTest/$fileName",
    "<testsuite tests=\"1\" failures=\"0\" errors=\"0\" skipped=\"0\">" +
        "<testcase classname=\"$classname\" name=\"$method[jvm]\">$suffix</testcase>" +
        "</testsuite>",
)

private fun seedCorpus(root: Path) {
    writeJvmXml(root, "dyn4k-core", "org.dyn4j.CoreTest", "works")
    writeJvmXml(root, "dyn4k", "io.github.FacadeTest", "works")
}

/**
 * `tools/android-runtime/test_full_corpus.py`.
 *
 * The full Android app installs the whole frozen portable common corpus, so its inputs must be derived
 * from the raw JVM reports and the complete suite manifest, and any drift must fail closed.
 */
val FullCorpusEvidenceContract by testSuite {
    test("accepts exact raw XML and records hashes") {
        withTempDirectory { root ->
            seedCorpus(root)
            val result = AndroidFiles.verifyJvmXml(root, CORPUS_CASES)
            assertEquals(2, result.caseIds.size)
            assertEquals(2, result.xmlFiles.size)
        }
    }

    test("rejects missing extra duplicate skipped failed or forged XML") {
        withTempDirectory { root ->
            seedCorpus(root)
            val variants = listOf(
                Triple("io.github.FacadeTest", "other", ""),
                Triple("io.github.FacadeTest", "works", "<skipped/>"),
                Triple("io.github.FacadeTest", "works", "<failure/>"),
            )
            for ((classname, method, suffix) in variants) {
                writeJvmXml(root, "dyn4k", classname, method, suffix)
                assertFailsWith<IllegalArgumentException>("$method $suffix") {
                    AndroidFiles.verifyJvmXml(root, CORPUS_CASES)
                }
            }
            seedCorpus(root)
            val path = root.resolve("dyn4k/build/test-results/jvmTest/TEST-io.github.FacadeTest.xml")
            path.toFile().writeText(path.toFile().readText().replace("tests=\"1\"", "tests=\"2\""))
            assertFailsWith<IllegalArgumentException> {
                AndroidFiles.verifyJvmXml(root, CORPUS_CASES)
            }
            seedCorpus(root)
            writeFile(
                root,
                "dyn4k/build/test-results/jvmTest/TEST-duplicate.xml",
                path.toFile().readText(),
            )
            assertFailsWith<IllegalArgumentException> {
                AndroidFiles.verifyJvmXml(root, CORPUS_CASES)
            }
        }
    }

    test("generated full app inputs detect tampering") {
        withTempDirectory { root ->
            val inputs = AndroidFiles.writeFullInputs(root, CORPUS_CASES)
            AndroidFiles.verifyFullInputs(root, CORPUS_CASES, JsonObject(inputs))
            val asset = Path.of((inputs.getValue("case_asset") as JsonObject).textOrNull("path")!!)
            asset.toFile().writeText(asset.toFile().readText() + "forged\n")
            var failure = assertFailsWith<IllegalArgumentException> {
                AndroidFiles.verifyFullInputs(root, CORPUS_CASES, JsonObject(inputs))
            }
            assertTrue(failure.message!!.contains("full app input"))
            failure = assertFailsWith<IllegalArgumentException> {
                AndroidFiles.verifyFullInputs(root, CORPUS_CASES, null)
            }
            assertTrue(failure.message!!.contains("full app input"))
        }
    }

    test("full rules retain exact reflective filter types") {
        val rules = AndroidCorpus.fullAppInputs(CORPUS_CASES).getValue("keep_rules").decodeToString()
        val types = listOf(
            "CollisionModelConsumer\$RootFilter", "CollisionModelConsumer\$ChildFilter",
            "CollisionModelConsumer\$OtherFilter",
            "org.dyn4j.collision.CollisionModelTest\$RootFilter",
            "org.dyn4j.collision.CollisionModelTest\$ChildFilter",
            "org.dyn4j.collision.CollisionModelTest\$OtherFilter",
            "org.dyn4j.coverage.collision.model.FilterFixtureCoverageTest\$Parent",
            "org.dyn4j.coverage.collision.model.FilterFixtureCoverageTest\$Child",
            "org.dyn4j.coverage.collision.model.FilterFixtureCoverageTest\$Sibling",
            "org.dyn4j.coverage.collision.model.FilterFixtureCoverageTest\$Unrelated",
        )
        for (name in types) {
            assertTrue(rules.contains("-keep,allowobfuscation class $name\n"), name)
        }
        assertTrue("-keep class org.dyn4j.collision.TypeFilter" !in rules)
    }

    test("x86 dexopt exception retains only matrix normmax member") {
        val matrix = "org.dyn4j.coverage.UpstreamMatrix22CoverageTest"
        val suite = listOf(
            SuiteCase("dyn4k-core:$matrix#norm", "dyn4k-core", matrix, "norm", "portable"),
            SuiteCase(
                "dyn4k-core:org.dyn4j.coverage.OtherTest#norm",
                "dyn4k-core",
                "org.dyn4j.coverage.OtherTest",
                "norm",
                "portable",
            ),
        )
        val inputs = AndroidCorpus.fullAppInputs(suite)
        val rules = inputs.getValue("keep_rules").decodeToString().lines()
        assertTrue("-keep,allowoptimization class $matrix { *; }" in rules)
        assertTrue(
            "-keepclassmembers class org.dyn4j.geometry.Matrix22 " +
                "{ public double normMax(); }" in rules,
        )
        assertEquals(
            1,
            rules.count { it.startsWith("-keepclassmembers class org.dyn4j.geometry.Matrix22") },
        )
        assertTrue("-keep,allowoptimization class org.dyn4j.coverage.OtherTest { *; }" in rules)
        assertEquals(1, rules.count { matrix in it })
        assertTrue(
            "dyn4k-core:$matrix#norm\t$matrix\tnorm" in
                inputs.getValue("case_asset").decodeToString().lines(),
        )
    }

    test("rejects changed manifest or raw XML after preparation") {
        withTempDirectory { root ->
            seedCorpus(root)
            val binding = buildJsonObject { put("sha256", JsonPrimitive("frozen")) }
            val prepared = buildJsonObject {
                put("suite_manifest", binding)
                put("jvm_xml", AndroidFiles.verifyJvmXml(root, CORPUS_CASES).toJson())
            }
            val suite = Suite(CORPUS_CASES, buildJsonObject { }, binding)
            AndroidFiles.verifyXmlPins(root, prepared, { suite }, { 0L })
            val forged = buildJsonObject {
                put("suite_manifest", buildJsonObject { put("sha256", JsonPrimitive("forged")) })
                put("jvm_xml", prepared.getValue("jvm_xml"))
            }
            val failure = assertFailsWith<IllegalArgumentException> {
                AndroidFiles.verifyXmlPins(root, forged, { suite }, { 0L })
            }
            assertTrue(failure.message!!.contains("manifest"))
            writeJvmXml(root, "dyn4k", "io.github.FacadeTest", "other")
            assertFailsWith<IllegalArgumentException> {
                AndroidFiles.verifyXmlPins(root, prepared, { suite }, { 0L })
            }
        }
    }

    test("rejects XML older than candidate commit") {
        withTempDirectory { root ->
            seedCorpus(root)
            var newest = 0L
            for (module in AndroidCorpus.MODULES) {
                val stamps = Files.list(root.resolve("$module/build/test-results/jvmTest")).use { stream ->
                    stream.mapToLong {
                        Files.getLastModifiedTime(it).to(java.util.concurrent.TimeUnit.NANOSECONDS)
                    }.toArray()
                }
                stamps.forEach { if (it > newest) newest = it }
            }
            val threshold = newest + 1
            val failure = assertFailsWith<IllegalArgumentException> {
                AndroidFiles.verifyJvmXml(root, CORPUS_CASES, threshold)
            }
            assertTrue(failure.message!!.contains("stale raw JVM"))
        }
    }

    test("portable jar retains abstract common test helpers") {
        withTempDirectory { root ->
            writeBytes(root, "dyn4k-core/build/classes/kotlin/jvm/test/org/dyn4j/CoreTest.class", "case".encodeToByteArray())
            writeBytes(
                root,
                "dyn4k-core/build/classes/kotlin/jvm/test/org/dyn4j/AbstractShapeTest.class",
                "helper".encodeToByteArray(),
            )
            Files.createDirectories(root.resolve("dyn4k/build/classes/kotlin/jvm/test"))
            val jar = root.resolve("portable.jar")
            AndroidFiles.buildPortableJar(root, jar, jvmOnlyClasses = emptySet())
            ZipFile(jar.toFile()).use { archive ->
                assertTrue("org/dyn4j/AbstractShapeTest.class" in archive.entries().toList().map { it.name })
            }
        }
    }

    test("portable class inventory follows manifest and rejects missing class") {
        withTempDirectory { root ->
            val core = writeBytes(
                root,
                "dyn4k-core/build/classes/kotlin/jvm/test/org/dyn4j/CoreTest.class",
                "core".encodeToByteArray(),
            )
            val facade = writeBytes(
                root,
                "dyn4k/build/classes/kotlin/jvm/test/io/github/FacadeTest.class",
                "facade".encodeToByteArray(),
            )
            assertEquals(
                listOf("io.github.FacadeTest", "org.dyn4j.CoreTest"),
                AndroidFiles.portableClasses(root, CORPUS_CASES),
            )
            Files.delete(facade)
            val failure = assertFailsWith<IllegalArgumentException> {
                AndroidFiles.portableClasses(root, CORPUS_CASES)
            }
            assertTrue(failure.message!!.contains("compiled portable test missing"))
            assertTrue(Files.isRegularFile(core))
        }
    }

    test("installed runner selects only frozen test classes") {
        val prepared = buildJsonObject {
            put(
                "portable_classes",
                kotlinx.serialization.json.JsonArray(
                    listOf("org.dyn4j.CoreTest", "io.github.FacadeTest").map { JsonPrimitive(it) },
                ),
            )
        }
        val portable = listOf("org.dyn4j.CoreTest", "io.github.FacadeTest")
        val candidate = RunContract.instrumentationClasses(portable, "candidate")
        assertTrue("org.dyn4j.CoreTest" in candidate)
        assertTrue("io.github.FacadeTest" in candidate)
        assertTrue("org.dyn4j.AbstractShapeTest" !in candidate)
        assertEquals(1, RunContract.instrumentationClasses(portable, "baseline").size)
        assertEquals(
            listOf("io.github.FacadeTest", "io.github.rubixhacker.dyn4k.runtime.ConsumerJourneyTest",
                "io.github.rubixhacker.dyn4k.runtime.StagedKotlinConsumerTest", "org.dyn4j.CoreTest"),
            candidate,
        )
        assertTrue(prepared.stringList("portable_classes") == portable)
    }
}
