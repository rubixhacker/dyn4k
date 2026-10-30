package io.github.rubixhacker.harness.baseline

import de.infix.testBalloon.framework.core.testSuite
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import java.nio.file.Files
import java.nio.file.Path
import kotlin.test.assertEquals
import kotlin.test.assertNotEquals
import kotlin.test.assertTrue

/**
 * Replaces the scratch root, every SHA-256 digest and every git revision with the placeholders the
 * recorded vectors use. A fixture repository is committed afresh each run, so the revision it
 * authenticates is never the recorded one.
 */
internal fun normalise(text: String, root: Path): String =
    text.replace(root.toString(), "<root>")
        .replace(Regex("\\b[0-9a-f]{64}\\b"), "<sha256>")
        .replace(Regex("\\b[0-9a-f]{40}\\b"), "<commit>")

/**
 * `RunReportTests` of `tools/baseline/test_verify.py`: the `check-run` command over the good report
 * and over every mutation the Python suite declares invalid.
 *
 * The recorded `check_run` vectors hold the exit status and both streams of each invocation, so the
 * comparison is over the whole command, not only the exit code.
 */
val RunReportCliCases by testSuite {
    test("check-run accepts the pinned report and rejects each invalid mutation") {
        assertEquals(
            listOf("good", "incomplete", "missing_output", "wrong_bytecode"),
            Vectors.checkRun.map { it.jsonObject.str("label") },
        )
        withCase { root ->
            val report = root.resolve("run.json")
            for (case in Vectors.checkRun) {
                val recorded = case.jsonObject
                writeText(report, PythonJson.render(recorded.obj("report")))
                val result = cli("check-run", "--report", report.toString())
                assertEquals(recorded.int("exit_code"), result.code, recorded.str("label"))
                assertEquals(recorded.str("stdout"), normalise(result.stdout, root), recorded.str("label"))
                assertEquals(recorded.str("stderr"), normalise(result.stderr, root), recorded.str("label"))
            }
        }
    }

    test("the recorded good report is the one the resolved validate gate accepts") {
        val good = Vectors.checkRun.first { it.jsonObject.str("label") == "good" }.jsonObject
        validateRunReport(good.obj("report"))
        assertEquals("baseline run report valid\n", good.str("stdout"))
        assertEquals(0, good.int("exit_code"))
    }

    test("every invalid mutation of the Python suite fails the command") {
        val good = Vectors.checkRun.first { it.jsonObject.str("label") == "good" }.jsonObject.obj("report")
        val mutations = linkedMapOf<String, Map<String, JsonElement>>(
            "incomplete" to mapOf(
                "actual_executed_cases" to JsonPrimitive(2384),
                "output" to JsonPrimitive("ACTUAL_TESTS=2384\nFAILURES=0\nIGNORED=0\n"),
            ),
            "ignored" to mapOf(
                "ignored" to JsonPrimitive(1),
                "output" to JsonPrimitive("ACTUAL_TESTS=2385\nFAILURES=0\nIGNORED=1\n"),
            ),
            "failed" to mapOf(
                "failures" to JsonPrimitive(1),
                "output" to JsonPrimitive("ACTUAL_TESTS=2385\nFAILURES=1\nIGNORED=0\n"),
            ),
            "exit" to mapOf("process_exit_code" to JsonPrimitive(1)),
            "missing_output" to mapOf("output" to JsonPrimitive("")),
            "nonnumeric" to mapOf("actual_executed_cases" to JsonPrimitive("2385")),
            "wrong_bytecode" to mapOf("harness_class_major" to JsonPrimitive(65)),
        )
        withCase { root ->
            val report = root.resolve("run.json")
            for ((label, changes) in mutations) {
                val mutation = JsonObject(good + changes)
                writeText(report, PythonJson.render(mutation))
                assertNotEquals(0, cli("check-run", "--report", report.toString()).code, label)
            }
        }
    }
}

/**
 * `SourceIntegrityTests` of `tools/baseline/test_verify.py`: the sources archive must still hold the
 * bytes the checkout has, and the archive digest must describe the bytes that were read.
 */
val SourceIntegrityCases by testSuite {
    test("the source archive hash identifies the checked bytes during a replacement") {
        withCase { root ->
            val checkout = root.resolve("checkout")
            val source = checkout.resolve("src/main/java/example/Api.java")
            makeDirectories(source.parent)
            writeText(source, "package example; public class Api {}\n")
            val fixture = initCheckout(checkout, emptyMap())
            val archive = root.resolve("sources.jar")
            val changed = root.resolve("changed.jar")
            sourcesArchive(archive, mapOf("example/Api.java" to "package example; public class Api {}\n"))
            sourcesArchive(
                changed,
                mapOf("example/Api.java" to "package example; public class Api { int changed; }\n"),
            )
            val originalHash = digest(archive)
            var replaced = false
            val replacing = object : TestSeams() {
                override fun openZip(path: Path): ZipArchive {
                    val opened = super.openZip(path)
                    if (!replaced) {
                        copyFile(changed, archive)
                        replaced = true
                    }
                    return opened
                }
            }
            val result = verifySourceInputs(replacing, checkout, archive, fixture.revision)
            assertTrue(replaced)
            assertNotEquals(originalHash, digest(archive))
            assertEquals(originalHash, result.sourceJarSha256)
            assertEquals(true, result.toJson().bool("source_jar_matches_tracked_bytes"))
        }
    }

    test("dirty, untracked and changed source inputs all fail the command") {
        assertEquals(
            listOf("clean", "dirty", "untracked", "archive-bytes"),
            Vectors.checkSource.map { it.jsonObject.str("label") },
        )
        withCase { root ->
            val checkout = root.resolve("checkout")
            val source = checkout.resolve("src/main/java/example/Api.java")
            val test = checkout.resolve("src/test/java/example/ApiTest.java")
            makeDirectories(source.parent)
            makeDirectories(test.parent)
            writeText(source, "package example; public class Api {}\n")
            writeText(test, "package example; public class ApiTest {}\n")
            val fixture = initCheckout(checkout, emptyMap())
            val archive = root.resolve("sources.jar")
            sourcesArchive(archive, mapOf("example/Api.java" to "package example; public class Api {}\n"))
            for (case in Vectors.checkSource) {
                val recorded = case.jsonObject
                val observed = cli(
                    "check-source",
                    "--checkout", checkout.toString(),
                    "--sources-jar", archive.toString(),
                    "--commit", fixture.revision,
                )
                assertEquals(recorded.int("exit_code"), observed.code, recorded.str("label"))
                assertEquals(
                    normalise(recorded.str("stdout"), root),
                    normalise(observed.stdout, root),
                    recorded.str("label"),
                )
                assertEquals(
                    normalise(recorded.str("stderr"), root),
                    normalise(observed.stderr, root),
                    recorded.str("label"),
                )
                // Advance the fixture into the next recorded state.
                when (recorded.str("label")) {
                    "clean" -> writeText(source, "package example; public class Api { int changed; }\n")
                    "dirty" -> {
                        writeText(source, "package example; public class Api {}\n")
                        writeText(checkout.resolve("src/test/java/example/Extra.java"), "class Extra {}\n")
                    }
                    "untracked" -> {
                        Files.deleteIfExists(checkout.resolve("src/test/java/example/Extra.java"))
                        sourcesArchive(
                            archive,
                            mapOf("example/Api.java" to "package example; public class Api { int changed; }\n"),
                        )
                    }
                }
            }
        }
    }
}

/**
 * `InventoryIdentityTests` of `tools/baseline/test_verify.py`: the inventory describes the bytes it
 * read, and a source file changed after the clean check is rejected rather than recorded.
 */
val InventoryIdentityCases by testSuite {
    test("the inventory binary hash identifies the inventoried bytes") {
        withCase { root ->
            val source = root.resolve("source")
            val production = source.resolve("src/main/java")
            val tests = source.resolve("src/test/java")
            makeDirectories(production)
            makeDirectories(tests)
            val files = mutableMapOf<String, String>()
            for (index in 0 until 268) files["src/main/java/P$index.java"] = "class P$index {}"
            for (index in 0 until 199) files["src/test/java/T$index.java"] = "class T$index {}"
            val fixture = initCheckout(source, files)
            val binary = jarOf(root.resolve("baseline"), mapOf("Api.java" to "public class Api {}"))
            val changed = jarOf(
                root.resolve("changed"),
                mapOf("Api.java" to "public class Api { public void extra() {} }"),
            )
            val originalHash = digest(binary)
            val originalPath = binary
            var replaced = false
            val replacing = object : TestSeams() {
                override fun jarInventory(
                    binary: Path,
                    only: Set<String>?,
                    visibility: String,
                    verbose: Boolean,
                ): JarInventory {
                    val inventory = super.jarInventory(binary, only, visibility, verbose)
                    if (!replaced) {
                        copyFile(changed, originalPath)
                        replaced = true
                    }
                    return inventory
                }
            }
            val report = inventory(
                replacing,
                source,
                binary,
                root.resolve("inventory.json"),
                BaselinePolicy(commit = fixture.revision, binarySha256 = originalHash),
            )
            assertTrue(replaced)
            assertNotEquals(originalHash, digest(binary))
            assertEquals(originalHash, report.obj("baseline").str("binary_sha256"))
            assertTrue(report.obj("baseline")["sources_sha256"] == null)
            val signature = report.obj("public_protected_jvm_signatures").str("Api")
            assertTrue(!signature.contains("extra()"))
        }
    }

    test("a test source replaced after the clean check is rejected, and a clean one is counted") {
        withCase { root ->
            val source = root.resolve("source")
            val production = source.resolve("src/main/java")
            val tests = source.resolve("src/test/java")
            makeDirectories(production)
            makeDirectories(tests)
            val files = mutableMapOf<String, String>()
            for (index in 0 until 268) files["src/main/java/P$index.java"] = "class P$index {}"
            for (index in 0 until 199) files["src/test/java/T$index.java"] = "class T$index {}"
            files["src/test/java/T0.java"] = "class T0 {} // @Test\n"
            val fixture = initCheckout(source, files)
            val binary = jarOf(root.resolve("binary"), mapOf("Api.java" to "public class Api {}"))
            val archive = root.resolve("sources.jar")
            sourcesArchive(
                archive,
                (0 until 268).associate { "P$it.java" to "class P$it {}" },
            )
            val policy = BaselinePolicy(
                commit = fixture.revision,
                binarySha256 = digest(binary),
                sourcesSha256 = digest(archive),
            )
            val checked = verifySourceInputs(seams, source, archive, fixture.revision, policy)
            assertEquals(true, checked.toJson().bool("source_inputs_clean"))
            writeText(tests.resolve("T0.java"), "class T0 {} // @Test RACE_MARKER // @Test\n")
            val rejected = runCatching { inventory(seams, source, binary, root.resolve("inventory.json"), policy) }
            val message = rejected.exceptionOrNull()?.message ?: ""
            assertTrue(
                Regex("dirty|differ").containsMatchIn(message),
                "unexpected message: $message",
            )
            writeText(tests.resolve("T0.java"), "class T0 {} // @Test\n")
            val report = inventory(seams, source, binary, root.resolve("clean-inventory.json"), policy)
            assertEquals(1, report.int("test_annotations"))
        }
    }
}

