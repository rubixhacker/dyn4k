package io.github.rubixhacker.harness.baseline

import de.infix.testBalloon.framework.core.testSuite
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.StandardCopyOption
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotEquals
import kotlin.test.assertTrue

/**
 * The fixture every git-identity case shares: 268 production sources, 199 test sources, one of which
 * carries `@Test`, a sources archive of the production bytes and a compiled baseline archive.
 */
internal class GitFixture(
    val source: Path,
    val archive: Path,
    val binary: Path,
    val cache: Path,
    val revision: String,
)

/** `os.environ` with `GIT_NO_REPLACE_OBJECTS` removed, which is what the Python helper runs with. */
internal fun gitReplacementEnvironment(): Map<String, String> =
    System.getenv() - "GIT_NO_REPLACE_OBJECTS"

/** `shutil.copytree`. */
internal fun copyTreeOf(source: Path, target: Path) {
    Files.walk(source).use { paths ->
        paths.forEach { path ->
            val destination = target.resolve(source.relativize(path).toString())
            if (Files.isDirectory(path)) {
                makeDirectories(destination)
            } else {
                destination.parent?.let { makeDirectories(it) }
                Files.copy(path, destination, StandardCopyOption.REPLACE_EXISTING)
            }
        }
    }
}

/** The `git` helper of the Python suites: `-C source`, `check=True`, stripped stdout. */
internal fun gitAt(source: Path, vararg args: String, environment: Map<String, String>? = null): String =
    pyStrip(seams.requireRun(listOf("git", "-C", source.toString()) + args, environment).stdoutText())

/** The 268 production and 199 test sources the identity cases pin. */
internal fun identitySources(): Map<String, String> {
    val files = linkedMapOf<String, String>()
    for (index in 0 until 268) files["src/main/java/P$index.java"] = "class P$index {}\n"
    for (index in 0 until 199) files["src/test/java/T$index.java"] = "class T$index {}\n"
    files["src/test/java/T0.java"] = "class T0 {} // @Test\n"
    return files
}

/** The production entries of a sources archive, keyed by file name, as `jar.write` records them. */
internal fun productionEntries(): Map<String, String> =
    (0 until 268).associate { "P$it.java" to "class P$it {}\n" }

/** `ComparatorTests.jar` over the JUnit stub the run-report cases compile against. */
internal fun stubJunitJar(root: Path): Path = jarOf(
    root,
    mapOf(
        "JUnitCore.java" to "package org.junit.runner; public class JUnitCore " +
            "{ public Result run(Class<?>[] classes) { return new Result(); } }",
        "Result.java" to "package org.junit.runner; public class Result " +
            "{ public int getRunCount() { return 1; } public int getFailureCount() { return 0; } " +
            "public int getIgnoreCount() { return 0; } public boolean wasSuccessful() { return true; } " +
            "public java.util.List<String> getFailures() { return java.util.Collections.emptyList(); } }",
    ),
)

/** `ComparatorTests.jar` over one unrelated class, the hamcrest stub. */
internal fun stubHamcrestJar(root: Path): Path = jarOf(root, mapOf("Stub.java" to "public class Stub {}"))

/** Installs the two stubs into `cache/deps` so `execute` never needs the network. */
internal fun installRunDependencies(cache: Path, junit: Path, hamcrest: Path) {
    val deps = cache.resolve("deps")
    makeDirectories(deps)
    copyFile(junit, deps.resolve(Baseline.JUNIT_FILE))
    copyFile(hamcrest, deps.resolve(Baseline.HAMCREST_FILE))
}

/** The `inputs` fixture of `GitReplacementIdentityTests`, including the planted replacement ref. */
internal fun replacementFixture(root: Path, changeProduction: Boolean = false): GitFixture {
    val source = root.resolve("source")
    val files = identitySources()
    val environment = gitReplacementEnvironment()
    for ((name, text) in files) {
        val path = source.resolve(name)
        path.parent?.let { makeDirectories(it) }
        writeText(path, text)
    }
    makeDirectories(source)
    val archive = root.resolve("sources.jar")
    sourcesArchive(archive, productionEntries())
    gitAt(source, "init", "-q", environment = environment)
    gitAt(source, "add", "src", environment = environment)
    gitAt(
        source, "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "original",
        environment = environment,
    )
    val original = gitAt(source, "rev-parse", "HEAD", environment = environment)
    writeText(source.resolve("src/test/java/T0.java"), "class T0 {} // @Test REPLACE_REF_MARKER // @Test\n")
    if (changeProduction) writeText(source.resolve("src/main/java/P0.java"), "class P0 { int changed; }\n")
    gitAt(source, "add", "src", environment = environment)
    gitAt(
        source, "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "replacement",
        environment = environment,
    )
    val replacement = gitAt(source, "rev-parse", "HEAD", environment = environment)
    gitAt(source, "checkout", "--detach", original, environment = environment)
    gitAt(source, "replace", original, replacement, environment = environment)
    gitAt(source, "reset", "--hard", original, environment = environment)
    assertEquals(original, gitAt(source, "rev-parse", "HEAD", environment = environment))
    assertEquals("", gitAt(source, "status", "--porcelain=v1", "--", "src", environment = environment))
    assertTrue(
        gitAt(
            source, "--no-replace-objects", "status", "--porcelain=v1", "--", "src",
            environment = environment,
        ).isNotEmpty(),
    )
    val binary = jarOf(root.resolve("binary"), mapOf("Api.java" to "public class Api {}"))
    return GitFixture(source, archive, binary, root.resolve("cache"), original)
}

/**
 * `GitReplacementIdentityTests` of `tools/baseline/test_verify.py`: a `git replace` ref must not be
 * able to authenticate source bytes the pinned commit does not contain, because every git call the
 * verifier makes passes `--no-replace-objects`.
 */
val GitReplacementIdentityCases by testSuite {
    test("a replacement ref cannot authenticate a changed test source") {
        withCase { root ->
            val fixture = replacementFixture(root)
            val policy = BaselinePolicy(
                commit = fixture.revision,
                sourcesSha256 = digest(fixture.archive),
            )
            val error = runCatching {
                verifySourceInputs(seams, fixture.source, fixture.archive, fixture.revision, policy)
            }.exceptionOrNull()
            assertTrue(
                error is IllegalArgumentException &&
                    Regex("dirty|differ").containsMatchIn(error.message ?: ""),
                "unexpected result: $error",
            )
        }
    }

    test("a replacement ref cannot change the test or production inventory") {
        for (changedProduction in listOf(false, true)) {
            withCase { root ->
                val fixture = replacementFixture(root, changedProduction)
                val output = root.resolve("inventory.json")
                val policy = BaselinePolicy(
                    commit = fixture.revision,
                    binarySha256 = digest(fixture.binary),
                )
                val error = runCatching {
                    inventory(seams, fixture.source, fixture.binary, output, policy)
                }.exceptionOrNull()
                assertTrue(
                    error is IllegalArgumentException &&
                        Regex("dirty|differ").containsMatchIn(error.message ?: ""),
                    "changedProduction=$changedProduction: $error",
                )
                assertFalse(Files.exists(output))
            }
        }
    }

    test("a replacement ref cannot authenticate the JUnit source") {
        withCase { root ->
            val fixture = replacementFixture(root)
            installRunDependencies(fixture.cache, stubJunitJar(root.resolve("junit")), stubHamcrestJar(root.resolve("hamcrest")))
            val output = root.resolve("run.json")
            val policy = BaselinePolicy(
                commit = fixture.revision,
                binarySha256 = digest(fixture.binary),
                expectedCases = 1,
            )
            val error = runCatching {
                execute(seams, fixture.source, fixture.binary, fixture.cache, output, policy)
            }.exceptionOrNull()
            assertTrue(
                error is IllegalArgumentException &&
                    Regex("dirty|pinned source .*bytes differ").containsMatchIn(error.message ?: ""),
                "unexpected result: $error",
            )
            assertFalse(Files.exists(output))
        }
    }

    test("the checkout rejects a replacement worktree") {
        withCase { root ->
            val fixture = replacementFixture(root)
            val cache = root.resolve("cache")
            makeDirectories(cache)
            val checkout = cache.resolve("dyn4j-source")
            Files.move(fixture.source, checkout)
            gitAt(checkout, "remote", "add", "origin", checkout.toString(), environment = gitReplacementEnvironment())
            val error = runCatching {
                checkedOutSources(seams, cache, BaselinePolicy(commit = fixture.revision))
            }.exceptionOrNull()
            assertTrue(
                error is BaselineExit &&
                    Regex("dirty|untracked").containsMatchIn(error.message ?: ""),
                "unexpected result: $error",
            )
        }
    }
}

/** The `inputs` fixture of `GitWorktreeIdentityTests`. */
internal fun worktreeFixture(root: Path): GitFixture {
    val source = root.resolve("source")
    val environment = gitCleanEnvironment()
    for ((name, text) in identitySources()) {
        val path = source.resolve(name)
        path.parent?.let { makeDirectories(it) }
        writeText(path, text)
    }
    makeDirectories(source)
    val archive = root.resolve("sources.jar")
    sourcesArchive(archive, productionEntries())
    gitAt(source, "init", "-q", environment = environment)
    gitAt(source, "add", "src", environment = environment)
    gitAt(
        source, "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "original",
        environment = environment,
    )
    val revision = gitAt(source, "rev-parse", "HEAD", environment = environment)
    val binary = jarOf(root.resolve("binary"), mapOf("Api.java" to "public class Api {}"))
    val cache = root.resolve("cache")
    installRunDependencies(cache, stubJunitJar(root.resolve("junit")), stubHamcrestJar(root.resolve("hamcrest")))
    return GitFixture(source, archive, binary, cache, revision)
}

/**
 * Every gate the verifier exposes must reject a source tree that changed under a pin: the source
 * provenance, the inventory and the upstream run all read the committed bytes, not the worktree.
 */
private fun assertAllGatesReject(
    root: Path,
    fixture: GitFixture,
    environment: Map<String, String> = System.getenv(),
) {
    val policy = BaselinePolicy(
        commit = fixture.revision,
        sourcesSha256 = digest(fixture.archive),
        binarySha256 = digest(fixture.binary),
        expectedCases = 1,
    )
    fun rejected(block: () -> Unit, label: String) {
        val error = runCatching(block).exceptionOrNull()
        assertTrue(
            error is IllegalArgumentException &&
                Regex("dirty|differ|bytes|regular file").containsMatchIn(error.message ?: ""),
            "$label: unexpected result: $error",
        )
    }
    rejected({
        verifySourceInputs(seams, fixture.source, fixture.archive, fixture.revision, policy, environment)
    }, "source provenance")
    val inventoryOutput = root.resolve("inventory.json")
    rejected({
        inventory(seams, fixture.source, fixture.binary, inventoryOutput, policy, environment)
    }, "inventory")
    assertFalse(Files.exists(inventoryOutput))
    val runOutput = root.resolve("run.json")
    rejected({
        execute(seams, fixture.source, fixture.binary, fixture.cache, runOutput, policy, environment)
    }, "run")
    assertFalse(Files.exists(runOutput))
}

/**
 * `GitWorktreeIdentityTests` of `tools/baseline/test_verify.py`: an assumed-unchanged index bit, a
 * redirected `GIT_WORK_TREE`, a symlinked source and an inherited worktree must all fail to change
 * what the verifier reads.
 */
val GitWorktreeIdentityCases by testSuite {
    test("a redirected worktree cannot hide the actual source") {
        withCase { root ->
            val fixture = worktreeFixture(root)
            val alternate = root.resolve("alternate")
            copyTreeOf(fixture.source.resolve("src"), alternate.resolve("src"))
            writeText(fixture.source.resolve("src/main/java/P0.java"), "class P0 { int changed; }\n")
            val poisoned = poisonEnvironment(mapOf("GIT_WORK_TREE" to alternate.toString()))
            assertEquals(
                "",
                gitAt(fixture.source, "status", "--porcelain=v1", "--", "src", environment = poisoned),
            )
            assertTrue(
                gitAt(
                    fixture.source, "--work-tree", fixture.source.toString(), "status",
                    "--porcelain=v1", "--", "src", environment = poisoned,
                ).isNotEmpty(),
            )
            assertAllGatesReject(root, fixture, poisoned)
        }
    }

    test("an assumed-unchanged production file cannot hide the actual source") {
        withCase { root ->
            val fixture = worktreeFixture(root)
            val clean = gitCleanEnvironment()
            gitAt(fixture.source, "update-index", "--assume-unchanged", "src/main/java/P0.java", environment = clean)
            writeText(fixture.source.resolve("src/main/java/P0.java"), "class P0 { int changed; }\n")
            assertEquals("", gitAt(fixture.source, "status", "--porcelain=v1", "--", "src", environment = clean))
            assertAllGatesReject(root, fixture)
        }
    }

    test("an assumed-unchanged test file cannot hide the actual source") {
        withCase { root ->
            val fixture = worktreeFixture(root)
            val clean = gitCleanEnvironment()
            gitAt(fixture.source, "update-index", "--assume-unchanged", "src/test/java/T0.java", environment = clean)
            writeText(fixture.source.resolve("src/test/java/T0.java"), "class T0 {} // @Test @Test\n")
            assertEquals("", gitAt(fixture.source, "status", "--porcelain=v1", "--", "src", environment = clean))
            assertAllGatesReject(root, fixture)
        }
    }

    test("clean assumed-unchanged files remain valid") {
        withCase { root ->
            val fixture = worktreeFixture(root)
            val clean = gitCleanEnvironment()
            gitAt(
                fixture.source, "update-index", "--assume-unchanged",
                "src/main/java/P0.java", "src/test/java/T0.java", environment = clean,
            )
            val policy = BaselinePolicy(
                commit = fixture.revision,
                sourcesSha256 = digest(fixture.archive),
                binarySha256 = digest(fixture.binary),
                expectedCases = 1,
            )
            val provenance = verifySourceInputs(seams, fixture.source, fixture.archive, fixture.revision, policy)
            assertEquals(true, provenance.toJson().bool("source_inputs_clean"))
            val report = inventory(seams, fixture.source, fixture.binary, root.resolve("inventory.json"), policy)
            assertEquals(1, report.int("test_annotations"))
            val run = execute(seams, fixture.source, fixture.binary, fixture.cache, root.resolve("run.json"), policy)
            assertEquals(1, run.int("actual_executed_cases"))
        }
    }

    test("a redirecting git environment cannot change a clean source") {
        withCase { root ->
            val fixture = worktreeFixture(root)
            val alternate = root.resolve("alternate")
            makeDirectories(alternate)
            val poisoned = poisonEnvironment(
                mapOf(
                    "GIT_DIR" to alternate.toString(),
                    "GIT_WORK_TREE" to alternate.toString(),
                    "GIT_COMMON_DIR" to alternate.toString(),
                    "GIT_INDEX_FILE" to alternate.resolve("index").toString(),
                    "GIT_OBJECT_DIRECTORY" to alternate.resolve("objects").toString(),
                    "GIT_ALTERNATE_OBJECT_DIRECTORIES" to alternate.resolve("objects").toString(),
                    "GIT_NAMESPACE" to "other",
                    "GIT_CONFIG_COUNT" to "1",
                    "GIT_CONFIG_KEY_0" to "core.worktree",
                    "GIT_CONFIG_VALUE_0" to alternate.toString(),
                ),
            )
            val policy = BaselinePolicy(
                commit = fixture.revision,
                sourcesSha256 = digest(fixture.archive),
            )
            val provenance = verifySourceInputs(
                seams,
                fixture.source,
                fixture.archive,
                fixture.revision,
                policy,
                poisoned,
            )
            assertEquals(true, provenance.toJson().bool("source_inputs_clean"))
        }
    }

    test("a worktree change during the archive read is rejected") {
        withCase { root ->
            val fixture = worktreeFixture(root)
            val target = fixture.source.resolve("src/main/java/P0.java")
            val changing = object : TestSeams() {
                override fun openZip(path: Path): ZipArchive {
                    val opened = super.openZip(path)
                    writeText(target, "class P0 { int changed; }\n")
                    return opened
                }
            }
            val policy = BaselinePolicy(
                commit = fixture.revision,
                sourcesSha256 = digest(fixture.archive),
            )
            val error = runCatching {
                verifySourceInputs(changing, fixture.source, fixture.archive, fixture.revision, policy)
            }.exceptionOrNull()
            assertTrue(
                error is IllegalArgumentException &&
                    Regex("dirty|pinned source bytes differ").containsMatchIn(error.message ?: ""),
                "unexpected result: $error",
            )
        }
    }

    test("an inventory rejects a worktree change hidden during the binary read") {
        withCase { root ->
            val fixture = worktreeFixture(root)
            val target = fixture.source.resolve("src/main/java/P0.java")
            gitAt(
                fixture.source, "update-index", "--assume-unchanged", "src/main/java/P0.java",
                environment = gitCleanEnvironment(),
            )
            val changing = object : TestSeams() {
                override fun jarInventory(
                    binary: Path,
                    only: Set<String>?,
                    visibility: String,
                    verbose: Boolean,
                ): JarInventory {
                    val inventory = super.jarInventory(binary, only, visibility, verbose)
                    writeText(target, "class P0 { int changed; }\n")
                    return inventory
                }
            }
            val output = root.resolve("inventory.json")
            val policy = BaselinePolicy(
                commit = fixture.revision,
                binarySha256 = digest(fixture.binary),
            )
            val error = runCatching {
                inventory(changing, fixture.source, fixture.binary, output, policy)
            }.exceptionOrNull()
            assertTrue(
                error is IllegalArgumentException &&
                    "pinned source bytes differ" in (error.message ?: ""),
                "unexpected result: $error",
            )
            assertFalse(Files.exists(output))
        }
    }

    test("a symlinked java file is not a clean regular source") {
        withCase { root ->
            val fixture = worktreeFixture(root)
            val target = fixture.source.resolve("src/main/java/P0.java")
            val outside = root.resolve("outside.java")
            writeBytes(outside, readBytes(target))
            gitAt(
                fixture.source, "update-index", "--assume-unchanged", "src/main/java/P0.java",
                environment = gitCleanEnvironment(),
            )
            Files.delete(target)
            Files.createSymbolicLink(target, outside)
            assertEquals(
                "",
                gitAt(
                    fixture.source, "status", "--porcelain=v1", "--", "src",
                    environment = gitCleanEnvironment(),
                ),
            )
            assertAllGatesReject(root, fixture)
        }
    }

    test("the checkout cannot write to an inherited worktree") {
        withCase { root ->
            val fixture = worktreeFixture(root)
            val clean = gitCleanEnvironment()
            val newer = "class P0 { int newer; }\n"
            writeText(fixture.source.resolve("src/main/java/P0.java"), newer)
            gitAt(fixture.source, "add", "src/main/java/P0.java", environment = clean)
            gitAt(
                fixture.source, "-c", "user.name=Test", "-c", "user.email=test@example.com",
                "commit", "-qm", "newer", environment = clean,
            )
            val cache = root.resolve("checkout-cache")
            makeDirectories(cache)
            val checkout = cache.resolve("dyn4j-source")
            Files.move(fixture.source, checkout)
            val alternate = root.resolve("alternate")
            copyTreeOf(checkout.resolve("src"), alternate.resolve("src"))
            gitAt(checkout, "remote", "add", "origin", checkout.toString(), environment = clean)
            val poisoned = poisonEnvironment(mapOf("GIT_WORK_TREE" to alternate.toString()))
            val resolved = checkedOutSources(
                seams,
                cache,
                BaselinePolicy(commit = fixture.revision),
                poisoned,
            )
            assertEquals(checkout, resolved)
            assertEquals(newer, readText(alternate.resolve("src/main/java/P0.java")))
            assertEquals("class P0 {}\n", readText(checkout.resolve("src/main/java/P0.java")))
        }
    }
}

/**
 * `BaselineRunIdentityTests` of `tools/baseline/test_verify.py`: the run summary describes the bytes
 * that were compiled and executed, even if the inputs are replaced mid-run.
 */
val BaselineRunIdentityCases by testSuite {
    test("the run report dependency hash identifies the executed bytes") {
        withCase { root ->
            val source = root.resolve("source")
            val test = source.resolve("src/test/java/ExampleTest.java")
            makeDirectories(test.parent)
            writeText(
                test,
                "public class ExampleTest { static { System.out.println(\"ORIGINAL_MARKER\"); } // @Test\n}\n",
            )
            val fixture = initCheckout(source, emptyMap())
            val binary = jarOf(root.resolve("binary"), mapOf("Api.java" to "public class Api {}"))
            val cache = root.resolve("cache")
            val junit = stubJunitJar(root.resolve("junit"))
            val hamcrest = stubHamcrestJar(root.resolve("hamcrest"))
            installRunDependencies(cache, junit, hamcrest)
            val junitDestination = cache.resolve("deps").resolve(Baseline.JUNIT_FILE)
            val originalHash = digest(junitDestination)
            var replaced = false
            val replacing = object : TestSeams() {
                override fun run(command: List<String>, environment: Map<String, String>?): ProcessOutput {
                    val result = super.run(command, environment)
                    if (command.first() == "java" &&
                        "BaselineJUnitReport" in command &&
                        !replaced
                    ) {
                        copyFile(hamcrest, junitDestination)
                        replaced = true
                    }
                    return result
                }
            }
            val report = execute(
                replacing,
                source,
                binary,
                cache,
                root.resolve("run.json"),
                BaselinePolicy(
                    commit = fixture.revision,
                    binarySha256 = digest(binary),
                    expectedCases = 1,
                ),
            )
            assertTrue(replaced)
            assertNotEquals(originalHash, digest(junitDestination))
            assertEquals(originalHash, report.str("junit_sha256"))
            assertTrue(report.str("output").contains("ORIGINAL_MARKER"))
        }
    }

    test("the run rejects a source changed after the snapshot") {
        withCase { root ->
            val source = root.resolve("source")
            val test = source.resolve("src/test/java/ExampleTest.java")
            makeDirectories(test.parent)
            writeText(
                test,
                "public class ExampleTest { static { System.out.println(\"ORIGINAL_MARKER\"); } // @Test\n}\n",
            )
            val fixture = initCheckout(source, emptyMap())
            val binary = jarOf(root.resolve("binary"), mapOf("Api.java" to "public class Api {}"))
            val cache = root.resolve("cache")
            installRunDependencies(cache, stubJunitJar(root.resolve("junit")), stubHamcrestJar(root.resolve("hamcrest")))
            val originalHash = digest(test)
            var replaced = false
            val changing = object : TestSeams() {
                override fun run(command: List<String>, environment: Map<String, String>?): ProcessOutput {
                    if (command.first() == "javac" && !replaced) {
                        writeText(
                            test,
                            "public class ExampleTest { static { " +
                                "System.out.println(\"CHANGED_MARKER\"); } // @Test\n}\n",
                        )
                        replaced = true
                    }
                    return super.run(command, environment)
                }
            }
            val output = root.resolve("run.json")
            val error = runCatching {
                execute(
                    changing,
                    source,
                    binary,
                    cache,
                    output,
                    BaselinePolicy(
                        commit = fixture.revision,
                        binarySha256 = digest(binary),
                        expectedCases = 1,
                    ),
                )
            }.exceptionOrNull()
            assertTrue(replaced)
            assertNotEquals(originalHash, digest(test))
            assertTrue(
                error is IllegalArgumentException &&
                    Regex("dirty|pinned source|source bytes").containsMatchIn(error.message ?: ""),
                "unexpected result: $error",
            )
            assertFalse(Files.exists(output))
        }
    }

    test("the run report rejects a source outside the pinned commit") {
        withCase { root ->
            val source = root.resolve("source")
            val test = source.resolve("src/test/java/ExampleTest.java")
            makeDirectories(test.parent)
            writeText(
                test,
                "public class ExampleTest { static { System.out.println(\"ORIGINAL_MARKER\"); } // @Test\n}\n",
            )
            val fixture = initCheckout(source, emptyMap())
            val binary = jarOf(root.resolve("binary"), mapOf("Api.java" to "public class Api {}"))
            val cache = root.resolve("cache")
            installRunDependencies(cache, stubJunitJar(root.resolve("junit")), stubHamcrestJar(root.resolve("hamcrest")))
            writeText(
                test,
                "public class ExampleTest { static { System.out.println(\"CHANGED_MARKER\"); } // @Test\n}\n",
            )
            val error = runCatching {
                execute(
                    seams,
                    source,
                    binary,
                    cache,
                    root.resolve("run.json"),
                    BaselinePolicy(
                        commit = fixture.revision,
                        binarySha256 = digest(binary),
                        expectedCases = 1,
                    ),
                )
            }.exceptionOrNull()
            assertTrue(
                error is IllegalArgumentException &&
                    Regex("dirty|pinned source").containsMatchIn(error.message ?: ""),
                "unexpected result: $error",
            )
        }
    }
}
