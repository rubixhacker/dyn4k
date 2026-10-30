package io.github.rubixhacker.harness.qualification

import de.infix.testBalloon.framework.core.testSuite
import java.nio.file.Files
import java.util.Base64
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import kotlinx.serialization.json.JsonObject

/** `qualify.pom_element_matches` against recorded reference decisions over staged POM documents. */
val PomElementMatches by testSuite {
    for (vector in TestVectors.list("pom_elements")) {
        test("pom_element_matches: ${vector.primitive("module")} ${vector.primitive("label")}") {
            val document = vector.primitive("document")
            val module = vector.primitive("module")
            val root = PomContract.parse(writeTemp("pom", document))
            val contract = PomContract.metadata(module)
            for ((section, matches) in vector.objectAt("matches")) {
                assertEquals(
                    TestVectors.str(matches) == "true",
                    PomContract.elementMatches(
                        PomContract.find(root, section),
                        section,
                        contract.getValue(section),
                    ),
                    "${vector.primitive("label")}: $section",
                )
            }
        }
    }

    test("a POM section with an unexpected attribute does not match") {
        val document = """
            <project xmlns="http://maven.apache.org/POM/4.0.0">
              <name origin="staged">dyn4k core</name>
            </project>
        """.trimIndent()
        val root = PomContract.parse(writeTemp("pom-attribute", document))
        assertEquals(
            false,
            PomContract.elementMatches(PomContract.find(root, "name"), "name", "dyn4k core"),
        )
    }

    test("a well-formed POM from another namespace does not match") {
        val document = """
            <project xmlns="http://example.invalid/POM/4.0.0">
              <name>dyn4k core</name>
            </project>
        """.trimIndent()
        val root = PomContract.parse(writeTemp("pom-namespace", document))
        assertEquals(
            false,
            PomContract.elementMatches(PomContract.find(root, "name"), "name", "dyn4k core"),
        )
    }
}

/** `qualify.source_sets_for_publication` and `qualify.expected_source_entries`. */
val SourceSetContract by testSuite {
    test("source sets and expected entries match every recorded publication") {
        val contract = recordedSourceContract()
        for (vector in TestVectors.list("source_entries")) {
            val module = vector.primitive("module")
            val target = TestVectors.strOrNull(vector["target"])
            assertEquals(
                TestVectors.strings(vector["source_sets"]).toSet(),
                SourceSets.forPublication(module, target),
                "$module/$target source sets",
            )
            val expected = vector.objectAt("entries")
            val observed = CandidateSource.expectedEntries(contract, module, target)
            assertEquals(expected.keys, observed.keys, "$module/$target entries")
            for ((path, sha) in expected) {
                assertEquals(TestVectors.str(sha), observed[path], "$module/$target $path")
            }
        }
    }

    test("the jvm module descriptor belongs to the core JVM publication only") {
        val contract = recordedSourceContract()
        assertTrue("jvmModule/module-info.java" in CandidateSource.expectedEntries(contract, "dyn4k-core", "jvm"))
        assertTrue("jvmModule/module-info.java" !in CandidateSource.expectedEntries(contract, "dyn4k-core", "js"))
        assertTrue("jvmModule/module-info.java" !in CandidateSource.expectedEntries(contract, "dyn4k", "jvm"))
    }
}

/** `qualify.archive_file_names` and the archive validators, against recorded reference verdicts. */
val ArchiveContracts by testSuite {
    val archives = TestVectors.root.getValue("archives") as kotlinx.serialization.json.JsonObject
    for (kind in archives.keys) {
        for (vector in (archives.getValue(kind) as kotlinx.serialization.json.JsonArray)) {
            val entry = vector as JsonObject
            test("$kind archive: ${entry.primitive("label")}") {
                val expected = entry.objectAt("result")
                val failure = runCatching {
                    when (kind) {
                        "sources" -> ArchiveContract.validateSourceArchive(
                            writeTemp("sources", payload(entry, "payload")),
                            entry.objectAt("expected").mapValues { TestVectors.str(it.value) },
                        )
                        "docs" -> {
                            val jar = writeTemp("docs", payload(entry, "payload"))
                            val tree = Files.createTempDirectory("dokka")
                            for ((name, content) in entry.objectAt("generated")) {
                                val path = tree.resolve(name)
                                path.parent?.let { Files.createDirectories(it) }
                                Files.write(path, Base64.getDecoder().decode(TestVectors.str(content)))
                            }
                            ArchiveContract.validateGeneratedDocs(jar, tree, LICENSE_BYTES)
                        }
                        else -> ArchiveContract.validateAppleMetadata(
                            writeTemp("metadata", payload(entry, "metadata")),
                            writeTemp("klib", payload(entry, "klib")),
                        )
                    }
                }.exceptionOrNull()
                if ("ok" in expected) {
                    assertEquals(null, failure?.message, entry.primitive("label"))
                } else {
                    assertEquals(expected.primitive("error"), failure?.message, entry.primitive("label"))
                }
            }
        }
    }

    test("an element only matches its own section name") {
        val document = """
            <project xmlns="http://maven.apache.org/POM/4.0.0">
              <name>dyn4k core</name>
            </project>
        """.trimIndent()
        val root = PomContract.parse(writeTemp("pom-cross", document))
        assertEquals(
            false,
            PomContract.elementMatches(
                PomContract.find(root, "name"),
                "description",
                "Kotlin Multiplatform dyn4j 6.0.0 compatible foundation",
            ),
        )
    }
}

private val LICENSE_BYTES = "Fixture license\n".toByteArray()

internal fun recordedSourceContract(): Map<String, Map<String, String>> = mapOf(
    "dyn4k-core" to linkedMapOf(
        "commonMain/api/Type.kt" to "1".repeat(64),
        "jvmMain/api/Jvm.kt" to "2".repeat(64),
        "nativeMain/api/Native.kt" to "3".repeat(64),
        "jsMain/api/Js.kt" to "4".repeat(64),
        "jvmModule/module-info.java" to "5".repeat(64),
    ),
    "dyn4k" to linkedMapOf(
        "commonMain/api/Type.kt" to "6".repeat(64),
        "jvmMain/api/Jvm.kt" to "7".repeat(64),
    ),
)

private fun payload(vector: JsonObject, key: String): ByteArray =
    Base64.getDecoder().decode(vector.primitive(key))

internal fun writeTemp(prefix: String, content: String): java.nio.file.Path =
    writeTemp(prefix, content.toByteArray())

internal fun writeTemp(prefix: String, content: ByteArray): java.nio.file.Path {
    val directory = Files.createTempDirectory("qualification-$prefix")
    val path = directory.resolve("$prefix.bin")
    Files.write(path, content)
    return path
}
