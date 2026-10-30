package io.github.rubixhacker.harness.qualification

import de.infix.testBalloon.framework.core.testSuite
import io.github.rubixhacker.harness.contract.Sha256
import io.github.rubixhacker.harness.contract.StrictJson
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.Path
import java.util.Base64
import kotlin.test.assertContentEquals
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

/**
 * `safari_reporter.py`: the generated Karma configuration binding, the committed reporter bytes,
 * the no-follow directory walk, and the staging lifecycle with its forensic capture.
 *
 * The recorded vectors in [HostedSafariVectors] were produced by `safari_reporter.py` at the
 * revision it names. The `stage` and `committed_bytes` cases build their own Git fixture here,
 * because a commit identifier belongs to the fixture that made it; the recorded outcomes — the
 * statuses, the project verdicts, the forensic paths and the retained digests — are the
 * reference's.
 */
val SafariReporterSuite by testSuite {
    val fragment = Base64.getDecoder().decode(HostedSafariVectors.FRAGMENT_BASE64)

    test("the approved generator tail is the pinned literal") {
        assertEquals(
            HostedSafariVectors.APPROVED_GENERATOR_TAIL_LENGTH,
            SafariReporter.APPROVED_GENERATOR_TAIL.toByteArray(StandardCharsets.UTF_8).size,
        )
        assertEquals(
            HostedSafariVectors.APPROVED_GENERATOR_TAIL_SHA256,
            Sha256.of(SafariReporter.APPROVED_GENERATOR_TAIL.toByteArray(StandardCharsets.UTF_8)),
        )
        assertTrue(SafariReporter.APPROVED_GENERATOR_TAIL.startsWith("\nconfig.plugins = config.plugins || [];\n"))
        assertTrue(SafariReporter.APPROVED_GENERATOR_TAIL.endsWith("// qualification-safari-reporter.js\n"))
    }

    test("the project table and configuration paths are the pinned ones") {
        assertEquals(HostedSafariVectors.PROJECTS, SafariReporter.PROJECTS)
        assertEquals(HostedSafariVectors.PACKAGES.toMap(), SafariReporter.PACKAGES)
        assertEquals("consumers/qualification/portable", SafariReporter.CONSUMER)
        assertEquals(HostedSafariVectors.MAX_FRAGMENT_BYTES, SafariReporter.MAX_FRAGMENT_BYTES)
        assertEquals(HostedSafariVectors.MAX_COMMITTED_OBJECT_BYTES, SafariReporter.MAX_COMMITTED_OBJECT_BYTES)
        assertEquals(HostedSafariVectors.STAGED_NAME, SafariReporter.STAGED_NAME)
        assertEquals(HostedSafariVectors.SOURCE, SafariReporter.SOURCE)
        for ((project, path) in HostedSafariVectors.CONFIG_PATHS) {
            assertEquals(path, SafariReporter.configRelative(project), project)
        }
        // `pathlib` drops a trailing or leading single dot before the project is looked up.
        assertEquals(
            "build/js/packages/dyn4k-dyn4k-core-test/karma.conf.js",
            SafariReporter.configRelative("dyn4k-core/"),
        )
        assertEquals(
            "build/js/packages/dyn4k-dyn4k-core-test/karma.conf.js",
            SafariReporter.configRelative("./dyn4k-core"),
        )
        assertEquals(
            "unknown Safari reporter project: other",
            assertFailsWithMessage { SafariReporter.configRelative("other") },
        )
    }

    for (vector in HostedSafariVectors.CONFIGS) {
        test("validate_config: ${vector.label}") {
            val data = Base64.getDecoder().decode(vector.data)
            if (vector.observed != null) {
                assertEquals(
                    vector.observed,
                    SafariReporter.validateConfig(
                        data,
                        fragment,
                        vector.repository,
                        vector.project,
                        vector.configuration,
                    ),
                    vector.label,
                )
            } else {
                // The reference raises `ConfigBindingError`, a `ValueError` subclass.
                val error = assertFailsWith<ConfigBindingError> {
                    SafariReporter.validateConfig(
                        data,
                        fragment,
                        vector.repository,
                        vector.project,
                        vector.configuration,
                    )
                }
                assertEquals(vector.error, error.message, vector.label)
            }
        }
    }

    test("a generated fragment header binds the source and the consumer") {
        val committed = Fs.readBytes(repositoryRoot().resolve(SafariReporter.SOURCE))
        val repository = "/qualification/generated"
        for (project in SafariReporter.PROJECTS) {
            for (mode in listOf("development", "production")) {
                val packageName = SafariReporter.PACKAGES.getValue(project)
                val buildRoot = if (project == SafariReporter.CONSUMER) "$repository/$project" else repository
                val packageRoot = "$buildRoot/build/js/packages/$packageName"
                val runner = "$buildRoot/build/js/node_modules/kotlin-web-helpers/dist" +
                    "/kotlin-test-karma-runner.js"
                val selected = if (mode == "development") {
                    "$packageRoot/kotlin/$packageName.js"
                } else {
                    "$repository/$project/build/compileSync/js/test/testProductionExecutable" +
                        "/kotlin/$packageName.js"
                }
                val settings = buildJsonObject {
                    put("singleRun", JsonPrimitive(true))
                    put("autoWatch", JsonPrimitive(false))
                    put("basePath", JsonPrimitive(packageRoot))
                    put(
                        "files",
                        JsonArray(listOf(JsonPrimitive(runner), JsonPrimitive(selected))),
                    )
                    put(
                        "frameworks",
                        JsonArray(
                            listOf(
                                JsonPrimitive("webpack-output"),
                                JsonPrimitive("mocha"),
                                JsonPrimitive("webpack"),
                            ),
                        ),
                    )
                    put("client", buildJsonObject { put("args", JsonArray(emptyList())) })
                    put("browsers", JsonArray(listOf(JsonPrimitive("Safari"))))
                    put("customLaunchers", buildJsonObject { })
                    put("failOnFailingTestSuite", JsonPrimitive(false))
                    put("failOnEmptyTestSuite", JsonPrimitive(false))
                    put("reporters", JsonArray(listOf(JsonPrimitive("karma-kotlin-reporter"))))
                    put(
                        "preprocessors",
                        buildJsonObject {
                            put(
                                runner,
                                JsonArray(listOf(JsonPrimitive("webpack"), JsonPrimitive("sourcemap"))),
                            )
                            put(
                                selected,
                                JsonArray(listOf(JsonPrimitive("webpack"), JsonPrimitive("sourcemap"))),
                            )
                        },
                    )
                    put("proxies", buildJsonObject { })
                    put("webpackCopy", JsonArray(emptyList()))
                }
                val text = "\nmodule.exports = function(config) {\n\nconfig.set(" +
                    PyJson.renderDefault(settings) + ");" +
                    SafariReporter.APPROVED_GENERATOR_TAIL +
                    String(committed, StandardCharsets.UTF_8) + "\n}\n"
                val generated = text.toByteArray(StandardCharsets.UTF_8)
                assertEquals(
                    mode,
                    SafariReporter.validateConfig(generated, committed, repository, project, mode),
                    "$project $mode",
                )
                for (changed in listOf(
                    text.replace(
                        "// qualification-safari-reporter.js\n",
                        "// other-reporter.js\n",
                    ).toByteArray(StandardCharsets.UTF_8),
                    text.replace(
                        "// qualification-safari-reporter.js\n",
                        "config.plugins = [];\n",
                    ).toByteArray(StandardCharsets.UTF_8),
                )) {
                    assertFailsWith<ConfigBindingError> {
                        SafariReporter.validateConfig(changed, committed, repository, project, mode)
                    }
                }
            }
        }
    }

    test("the committed bytes are the committed objects, including CRLF") {
        withRepository(fragment) { root ->
            val repository = root.resolve("repository")
            val candidate = gitCommit(root)
            val expected = HostedSafariVectors.COMMITTED.first { it.label == "committed source" }
            assertContentEquals(
                Base64.getDecoder().decode(expected.bytes),
                SafariReporterHost.committedBytes(repository, candidate, Path.of(SafariReporter.SOURCE)),
            )

            val windows = String(fragment, StandardCharsets.UTF_8)
                .replace("\r\n", "\n")
                .replace("\n", "\r\n")
                .toByteArray(StandardCharsets.UTF_8)
            Files.write(repository.resolve(SafariReporter.SOURCE), windows)
            commitAll(repository, "crlf")
            val crlfCandidate = gitOutput(repository, "rev-parse", "HEAD")
            val crlf = Base64.getDecoder().decode(
                HostedSafariVectors.COMMITTED.first { it.label == "crlf source" }.bytes,
            )
            assertContentEquals(
                crlf,
                SafariReporterHost.committedBytes(repository, crlfCandidate, Path.of(SafariReporter.SOURCE)),
            )
            assertContentEquals(windows, crlf)
        }
    }

    test("committed bytes reject unsafe paths, absent objects, and changed sources") {
        val rows = HostedSafariVectors.COMMITTED.associateBy { it.label }
        withRepository(fragment) { root ->
            val repository = root.resolve("repository")
            val candidate = gitCommit(root)
            val source = Path.of(SafariReporter.SOURCE)

            assertEquals(
                rows.getValue("absolute path").error,
                assertFailsWithMessage {
                    SafariReporterHost.committedBytes(repository, candidate, Path.of("/etc/passwd"))
                },
            )
            assertEquals(
                rows.getValue("parent traversal").error,
                assertFailsWithMessage {
                    SafariReporterHost.committedBytes(repository, candidate, Path.of("dyn4k-core/../dyn4k"))
                },
            )
            assertEquals(
                rows.getValue("short commit").error,
                assertFailsWithMessage {
                    SafariReporterHost.committedBytes(repository, "abc", source)
                },
            )
            assertEquals(
                rows.getValue("sha256 object format").error,
                assertFailsWithMessage {
                    SafariReporterHost.committedBytes(
                        repository,
                        "4cfc322679086a32de9b1e18334e9f372e62bec401619e082bf019cb3270852c",
                        source,
                    )
                },
            )
            assertEquals(
                rows.getValue("missing commit").error,
                assertFailsWithMessage {
                    SafariReporterHost.committedBytes(repository, "0".repeat(40), source)
                },
            )
            // `pathlib` drops the single dot, so the message names the normalized path.
            assertEquals(
                rows.getValue("single dot").error,
                assertFailsWithMessage {
                    SafariReporterHost.committedBytes(repository, candidate, Path.of("./x"))
                },
            )
            assertEquals(
                rows.getValue("missing path").error,
                assertFailsWithMessage {
                    SafariReporterHost.committedBytes(
                        repository,
                        candidate,
                        Path.of("dyn4k-core/absent.txt"),
                    )
                },
            )
            assertEquals(
                rows.getValue("directory path").error,
                assertFailsWithMessage {
                    SafariReporterHost.committedBytes(repository, candidate, Path.of("dyn4k-core"))
                },
            )

            assertContentEquals(
                fragment,
                SafariReporterHost.committedFragment(repository, candidate),
            )
            Files.write(
                repository.resolve(SafariReporter.SOURCE),
                String(fragment, StandardCharsets.UTF_8).replace("// ", "// changed ").toByteArray(),
            )
            assertEquals(
                rows.getValue("modified working tree").error,
                assertFailsWithMessage {
                    SafariReporterHost.committedFragment(repository, candidate)
                },
            )
            gitOutput(repository, "checkout", "--", SafariReporter.SOURCE)

            val outside = root.resolve("outside-fragment.js")
            Files.write(outside, fragment)
            Files.delete(repository.resolve(SafariReporter.SOURCE))
            Files.createSymbolicLink(repository.resolve(SafariReporter.SOURCE), outside)
            assertEquals(
                rows.getValue("symlinked working tree").error,
                assertFailsWithMessage {
                    SafariReporterHost.committedFragment(repository, candidate)
                },
            )
        }
    }

    for (vector in HostedSafariVectors.STAGES) {
        test("stage: ${vector.label}") {
            withRepository(fragment) { root ->
                val repository = root.resolve("repository")
                val candidate = gitCommit(root)
                val output = root.resolve("output")
                Files.createDirectories(output)
                when (vector.label) {
                    "clean" -> {
                        val result = SafariReporterHost.stage(
                            repository,
                            candidate,
                            listOf("dyn4k-core", "dyn4k"),
                            output,
                        ) { staged ->
                            val projects = staged.result.getValue("projects") as JsonObject
                            for (project in listOf("dyn4k-core", "dyn4k")) {
                                assertEquals("STAGED", Py.str(projects.getValue(project)), project)
                                assertContentEquals(
                                    fragment,
                                    Files.readAllBytes(
                                        repository.resolve(project)
                                            .resolve("karma.config.d")
                                            .resolve(SafariReporter.STAGED_NAME),
                                    ),
                                )
                            }
                        }
                        assertStage(vector, result)
                        for (project in listOf("dyn4k-core", "dyn4k")) {
                            assertTrue(
                                Files.notExists(repository.resolve(project).resolve("karma.config.d")),
                                "$project/karma.config.d must be removed",
                            )
                        }
                    }
                    "changed" -> {
                        val result = SafariReporterHost.stage(
                            repository,
                            candidate,
                            listOf("dyn4k-core", "dyn4k"),
                            output,
                        ) {
                            Files.write(
                                repository.resolve("dyn4k-core/karma.config.d")
                                    .resolve(SafariReporter.STAGED_NAME),
                                "config.plugins = [];\n".toByteArray(),
                            )
                        }
                        assertStage(vector, result)
                        assertContentEquals(
                            "config.plugins = [];\n".toByteArray(),
                            Files.readAllBytes(
                                output.resolve("forensic/safari-reporter/dyn4k-core")
                                    .resolve(SafariReporter.STAGED_NAME),
                            ),
                        )
                    }
                    "leftover" -> {
                        val result = SafariReporterHost.stage(
                            repository,
                            candidate,
                            listOf("dyn4k-core", "dyn4k"),
                            output,
                        ) {
                            Files.write(
                                repository.resolve("dyn4k-core/karma.config.d/extra.js"),
                                "extra".toByteArray(),
                            )
                        }
                        assertStage(vector, result)
                    }
                    "seventeen leftovers" -> {
                        val result = SafariReporterHost.stage(
                            repository,
                            candidate,
                            listOf("dyn4k-core", "dyn4k"),
                            output,
                        ) {
                            val folder = repository.resolve("dyn4k-core/karma.config.d")
                            for (index in 0 until 17) {
                                Files.write(folder.resolve("${'a' + index}.js"), "x".toByteArray())
                            }
                        }
                        assertStage(vector, result)
                    }
                    "directory swapped" -> {
                        val result = SafariReporterHost.stage(
                            repository,
                            candidate,
                            listOf("dyn4k-core", "dyn4k"),
                            output,
                        ) {
                            val folder = repository.resolve("dyn4k-core/karma.config.d")
                            Files.move(folder, repository.resolve("dyn4k-core/karma.config.d.moved"))
                            Files.createDirectory(folder)
                        }
                        assertStage(vector, result)
                        assertTrue(Files.isDirectory(repository.resolve("dyn4k-core/karma.config.d")))
                    }
                    "dangling leftover" -> {
                        val result = SafariReporterHost.stage(
                            repository,
                            candidate,
                            listOf("dyn4k-core", "dyn4k"),
                            output,
                        ) {
                            Files.createSymbolicLink(
                                repository.resolve("dyn4k-core/karma.config.d/dangling.js"),
                                repository.resolve("absent.js"),
                            )
                        }
                        assertStage(vector, result)
                    }
                    "output inside repository" -> {
                        assertEquals(
                            vector.error,
                            assertFailsWithMessage {
                                SafariReporterHost.stage(
                                    repository,
                                    candidate,
                                    listOf("dyn4k-core"),
                                    repository.resolve("build/output"),
                                ) {}
                            },
                        )
                    }
                    "unknown project" -> {
                        assertEquals(
                            vector.error,
                            assertFailsWithMessage {
                                SafariReporterHost.stage(
                                    repository,
                                    candidate,
                                    listOf("other"),
                                    output,
                                ) {}
                            },
                        )
                    }
                    "duplicate project" -> {
                        assertEquals(
                            vector.error,
                            assertFailsWithMessage {
                                SafariReporterHost.stage(
                                    repository,
                                    candidate,
                                    listOf("dyn4k-core", "dyn4k-core"),
                                    output,
                                ) {}
                            },
                        )
                    }
                    "empty projects" -> {
                        assertEquals(
                            vector.error,
                            assertFailsWithMessage {
                                SafariReporterHost.stage(repository, candidate, emptyList(), output) {}
                            },
                        )
                    }
                    else -> error("unhandled recorded stage case: ${vector.label}")
                }
            }
        }
    }

    test("a failed body still cleans the staging directory and rethrows") {
        withRepository(fragment) { root ->
            val repository = root.resolve("repository")
            val candidate = gitCommit(root)
            val output = root.resolve("output")
            Files.createDirectories(output)
            val failure = assertFailsWith<IllegalStateException> {
                SafariReporterHost.stage(
                    repository,
                    candidate,
                    listOf("dyn4k-core"),
                    output,
                ) {
                    throw IllegalStateException("body failed")
                }
            }
            assertEquals("body failed", failure.message)
            assertTrue(Files.notExists(repository.resolve("dyn4k-core/karma.config.d")))
        }
    }

    test("the generated config is read through the no-follow path") {
        val root = Files.createTempDirectory("safari-config")
        try {
            val repository = root.resolve("repository")
            val relative = Path.of(SafariReporter.configRelative("dyn4k-core"))
            val config = repository.resolve(relative)
            config.parent?.let { Files.createDirectories(it) }
            val bytes = "config.plugins = [];\n".toByteArray()
            Files.write(config, bytes)
            val read = SafariReporterHost.readGeneratedConfig(repository, relative)
            assertContentEquals(bytes, read.data)
            assertEquals(bytes.size.toLong(), read.identity.size)
            val parent = relative.parent!!
            assertTrue(
                SafariReporterHost.sameDirectory(
                    repository,
                    parent,
                    SafariReporterHost.identityOf(repository.resolve(parent)),
                ),
            )
            assertTrue(
                SafariReporterHost.sameDirectory(
                    repository,
                    Path.of(""),
                    SafariReporterHost.identityOf(repository),
                ),
            )

            val linked = root.resolve("linked.conf")
            Files.write(linked, bytes)
            Files.delete(config)
            Files.createSymbolicLink(config, linked)
            assertEquals(
                "[Errno 40] Too many levels of symbolic links: '$config'",
                assertFailsWith<SafariFileError> {
                    SafariReporterHost.readGeneratedConfig(repository, relative)
                }.message,
            )
            Files.delete(config)
            Files.write(config, ByteArray(SafariReporter.MAX_FRAGMENT_BYTES + 1))
            assertEquals(
                "unsafe or oversized Safari generated config: $relative",
                assertFailsWithMessage {
                    SafariReporterHost.readGeneratedConfig(repository, relative)
                },
            )
        } finally {
            deleteRecursively(root)
        }
    }

    test("a staging directory that is no longer the held one is not the same directory") {
        val root = Files.createTempDirectory("safari-identity")
        try {
            val repository = root.resolve("repository")
            val folder = repository.resolve("dyn4k-core")
            Files.createDirectories(folder)
            val held = SafariReporterHost.openDirectoryNoFollow(repository, Path.of("dyn4k-core"))
            val identity = SafariReporterHost.identityOf(held)
            assertTrue(
                SafariReporterHost.sameDirectory(repository, Path.of("dyn4k-core"), identity),
            )
            Files.move(folder, repository.resolve("dyn4k-core.moved"))
            Files.createDirectory(folder)
            assertTrue(
                !SafariReporterHost.sameDirectory(repository, Path.of("dyn4k-core"), identity),
            )
            assertEquals(
                "unsafe Safari path: ..",
                assertFailsWithMessage {
                    SafariReporterHost.openDirectoryNoFollow(repository, Path.of(".."))
                },
            )
            assertEquals(
                "unsafe Safari path: /etc",
                assertFailsWithMessage {
                    SafariReporterHost.openDirectoryNoFollow(repository, Path.of("/etc"))
                },
            )
            assertEquals(
                "[Errno 2] No such file or directory: '$repository/absent'",
                assertFailsWith<SafariFileError> {
                    SafariReporterHost.openDirectoryNoFollow(repository, Path.of("absent"))
                }.message,
            )
        } finally {
            deleteRecursively(root)
        }
    }

    test("the Windows locked-directory path fails closed instead of degrading") {
        val state = SafariReporterHost.StageState(Sha256.of(ByteArray(0)))
        val stageError = assertFailsWith<UnsupportedOperationException> {
            SafariReporterHost.stageWindows(
                Path.of("."),
                listOf("dyn4k-core"),
                ByteArray(0),
                Path.of("out"),
                state,
            )
        }
        assertTrue(stageError.message!!.contains("is not ported"), stageError.message!!)
        assertTrue(
            stageError.message!!.contains("safari_windows_file.LockedDirectory"),
            stageError.message!!,
        )
        val readError = assertFailsWith<UnsupportedOperationException> {
            SafariReporterHost.readGeneratedConfig(
                Path.of("."),
                Path.of("a/b"),
                windows = true,
            )
        }
        assertTrue(readError.message!!.contains("not ported"), readError.message!!)
    }

    test("a stage failure names the first recorded residue path") {
        assertEquals(
            "Safari reporter staging residue: dyn4k-core/karma.config.d",
            StageFailure(
                buildJsonObject {
                    put("status", JsonPrimitive("CHANGED"))
                    put(
                        "forensic",
                        JsonArray(
                            listOf(
                                buildJsonObject {
                                    put("path", JsonPrimitive("dyn4k-core/karma.config.d"))
                                    put("error", JsonPrimitive("staging directory remains after cleanup"))
                                },
                            ),
                        ),
                    )
                },
            ).message,
        )
        assertEquals(
            "Safari reporter staging residue: karma.config.d",
            StageFailure(buildJsonObject { put("forensic", JsonArray(emptyList())) }).message,
        )
    }
}

private fun assertStage(vector: HostedSafariVectors.StageCase, result: JsonObject) {
    assertEquals(vector.status, Py.str(result["status"]), vector.label)
    assertEquals(StrictJson.load(vector.projects), result["projects"], vector.label)
    assertEquals(vector.sourceSha256, Py.str(result["source_sha256"]), vector.label)
    val forensic = (result["forensic"] as JsonArray).map { it as JsonObject }
    assertEquals(vector.forensicPaths, forensic.map { Py.str(it["path"]) }, vector.label)
    assertEquals(vector.forensicErrors, forensic.map { "error" in it }, vector.label)
    assertEquals(vector.forensicSha256, forensic.map { Py.str(it["sha256"]) ?: "" }, vector.label)
    assertEquals(
        vector.leftovers?.let { StrictJson.load(it) },
        result["leftovers"],
        vector.label,
    )
    assertEquals(vector.leftoversTruncated, Py.truthy(result["leftovers_truncated"]), vector.label)
}

/**
 * A Git fixture that holds the committed reporter fragment and the three project directories.
 *
 * `withRepository` creates the repository, commits the fragment, and removes the tree afterwards.
 */
private fun withRepository(fragment: ByteArray, block: (Path) -> Unit) {
    val root = Files.createTempDirectory("safari-repository")
    try {
        val repository = root.resolve("repository")
        Files.createDirectories(repository)
        gitOutput(repository, "init", "-q")
        gitOutput(repository, "config", "core.autocrlf", "false")
        val source = repository.resolve(SafariReporter.SOURCE)
        source.parent?.let { Files.createDirectories(it) }
        Files.write(source, fragment)
        for (project in SafariReporter.PROJECTS) {
            Files.createDirectories(repository.resolve(project))
        }
        commitAll(repository, "candidate")
        block(root)
    } finally {
        deleteRecursively(root)
    }
}

private fun gitCommit(root: Path): String = gitOutput(root.resolve("repository"), "rev-parse", "HEAD")

private fun commitAll(repository: Path, message: String) {
    gitOutput(repository, "add", ".")
    gitOutput(
        repository,
        "-c", "user.name=Fixture",
        "-c", "user.email=fixture@example.invalid",
        "commit", "-qm", message,
    )
}

private fun gitOutput(repository: Path, vararg arguments: String): String {
    val process = ProcessBuilder(listOf("git", "-C", repository.toString()) + arguments)
        .redirectErrorStream(true)
        .start()
    val output = process.inputStream.use { String(it.readBytes(), StandardCharsets.UTF_8) }
    if (process.waitFor() != 0) {
        error("git ${arguments.joinToString(" ")} failed: $output")
    }
    return output.trim()
}
