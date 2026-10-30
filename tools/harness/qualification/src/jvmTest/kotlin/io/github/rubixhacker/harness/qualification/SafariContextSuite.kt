package io.github.rubixhacker.harness.qualification

import de.infix.testBalloon.framework.core.testSuite
import io.github.rubixhacker.harness.contract.StrictJson
import java.io.ByteArrayOutputStream
import java.io.PrintStream
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.LinkOption
import java.nio.file.Path
import java.util.zip.DeflaterOutputStream
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/**
 * `SafariYarnLockTests`'s context fixture: the checkout `context_fixture` and
 * `write_valid_karma_configs` build, with the reference reporter source committed instead of the
 * stub the capture fixture uses.
 */
internal class SafariContextFixture(val root: Path = Files.createTempDirectory("safari-context")) {
    private val base = SafariFixture(root)
    var repository: Path = base.repository
    var candidate: String

    /** `self.raw_context`: the raw launch context the last [contextFixture] built. */
    var rawContext: Path = root.resolve("raw-context")

    init {
        Files.write(
            base.repository.resolve(SafariReporter.SOURCE),
            Files.readAllBytes(repositoryRoot().resolve(SafariReporter.SOURCE)),
        )
        hostedGit(base.repository, "add", ".")
        candidate = base.commit("real reporter source")
        for (relative in SafariYarnLockRules.CONTEXT_ROOTS) {
            Files.createDirectories(base.repository.resolve(relative))
        }
    }

    fun reporterText(): String = Files.readString(repository.resolve(SafariReporter.SOURCE))

    fun commitAll(message: String): String {
        candidate = base.commit(message)
        return candidate
    }

    fun cleanup() = base.cleanup()

    /** `context_fixture`: a raw launch context the launcher could have produced. */
    fun contextFixture(suffix: String = ""): Pair<Path, Path> {
        val context = root.resolve("context$suffix")
        val raw = root.resolve("raw-context$suffix")
        rawContext = raw
        Files.createDirectories(raw)
        Files.writeString(raw.resolve("launch-123.txt"), "pid=123\n")
        Files.writeString(
            raw.resolve("sample-state-123.txt"),
            "samples_completed=5\nsampler_exit=0\n",
        )
        Files.writeString(
            raw.resolve("process-123.txt"),
            "sample=1\nsample=2\nsample=3\nsample=4\nsample=5\n",
        )
        Files.writeString(raw.resolve("launch-outcome-123.txt"), "open_exit=23\n")
        Files.writeString(raw.resolve("redirect-123.html"), "redirect\n")
        Files.writeString(raw.resolve("open-123.stdout"), "")
        Files.writeString(raw.resolve("open-123.stderr"), "early failure\n")
        Files.writeString(raw.resolve("session-after.txt"), "Aqua\n")
        Files.writeString(raw.resolve("process-after.txt"), "process\n")
        Files.writeString(raw.resolve("host-outcome.txt"), "session_exit=0\nprocess_exit=0\n")
        for (relative in SafariYarnLockRules.CONTEXT_ROOTS) {
            Files.createDirectories(repository.resolve(relative))
        }
        return context to repository.resolve(SafariYarnLockRules.CONTEXT_ROOTS[0])
    }

    /** `write_valid_karma_configs`: the configuration the Karma generator emits per module. */
    fun writeValidKarmaConfigs(mode: String = "development") {
        val resolved = repository.toRealPath()
        val reporter = reporterText()
        for (module in listOf("dyn4k-core", "dyn4k")) {
            val packageName = "dyn4k-$module-test"
            val packageRoot = resolved.resolve("build/js/packages/$packageName")
            Files.createDirectories(packageRoot)
            val runner = resolved.resolve(
                "build/js/node_modules/kotlin-web-helpers/dist/kotlin-test-karma-runner.js",
            ).toString()
            val source = if (mode == "production") {
                resolved.resolve(
                    "$module/build/compileSync/js/test/testProductionExecutable/kotlin/$packageName.js",
                ).toString()
            } else {
                packageRoot.resolve("kotlin/$packageName.js").toString()
            }
            val settings = buildJsonObject {
                put("singleRun", true)
                put("autoWatch", false)
                put("basePath", packageRoot.toString())
                put("files", JsonArray(listOf(JsonPrimitive(runner), JsonPrimitive(source))))
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
                put("failOnFailingTestSuite", false)
                put("failOnEmptyTestSuite", false)
                put("reporters", JsonArray(listOf(JsonPrimitive("karma-kotlin-reporter"))))
                put(
                    "preprocessors",
                    buildJsonObject {
                        put(
                            runner,
                            JsonArray(listOf(JsonPrimitive("webpack"), JsonPrimitive("sourcemap"))),
                        )
                        put(
                            source,
                            JsonArray(listOf(JsonPrimitive("webpack"), JsonPrimitive("sourcemap"))),
                        )
                    },
                )
                put("proxies", buildJsonObject { })
                put("webpackCopy", JsonArray(emptyList()))
            }
            val text = "\nmodule.exports = function(config) {\n\nconfig.set(" +
                PyJson.renderDefault(settings) + ");" +
                SafariReporter.APPROVED_GENERATOR_TAIL + reporter + "\n}\n"
            Files.write(packageRoot.resolve("karma.conf.js"), text.toByteArray(StandardCharsets.UTF_8))
        }
    }

    fun projectConfig(index: Int): Path =
        repository.resolve(SafariYarnLockRules.CONTEXT_ROOTS[index]).resolve("karma.conf.js")
}

private fun withContextFixture(block: (SafariContextFixture) -> Unit) {
    val fixture = SafariContextFixture()
    try {
        block(fixture)
    } finally {
        fixture.cleanup()
    }
}

/** `self.capture_context(context)`. */
private fun captureContext(
    fixture: SafariContextFixture,
    context: Path,
    raw: Path,
    bounds: SafariContextBounds = SafariContextBounds(),
    scanHook: SafariContext.ScanHook? = null,
): JsonObject = SafariContext.captureKarmaContext(
    fixture.repository,
    fixture.candidate,
    context,
    raw,
    bounds,
    scanHook,
)

/** The four-field summary `main` prints for a context scan. */
private fun runContextCli(
    fixture: SafariContextFixture,
    context: Path,
    raw: Path,
    printed: StringBuilder,
): Int = captureStdout(printed) {
    SafariCaptureCli.run(
        arrayOf(
            "--candidate-sha",
            fixture.candidate,
            "--input-context",
            raw.toString(),
            "--output",
            context.toString(),
            "--capture-context",
        ),
        fixture.repository,
    )
}

private fun captureStdout(sink: StringBuilder, block: () -> Int): Int {
    val original = System.out
    val stream = ByteArrayOutputStream()
    System.setOut(PrintStream(stream, true))
    try {
        val code = block()
        sink.append(stream.toString())
        return code
    } finally {
        System.setOut(original)
    }
}

private fun captureStderr(sink: StringBuilder, block: () -> Int): Int {
    val original = System.err
    val stream = ByteArrayOutputStream()
    System.setErr(PrintStream(stream, true))
    try {
        val code = block()
        sink.append(stream.toString())
        return code
    } finally {
        System.setErr(original)
    }
}

private fun readInventory(context: Path): JsonObject =
    StrictJson.load(Files.readString(context.resolve("inventory.json"))) as JsonObject

private fun inputsOf(inventory: JsonObject): List<JsonObject> =
    (inventory["inputs"] as JsonArray).map { it as JsonObject }

/** `assert_context_upload_bound`: nothing symbolic, nothing oversized, nothing unbounded. */
private fun assertContextUploadBound(context: Path) {
    val entries = Files.walk(context).use { walk -> walk.toList() }.drop(1)
    val files = entries.filter { Files.isRegularFile(it, LinkOption.NOFOLLOW_LINKS) }
    assertFalse(entries.any { Files.isSymbolicLink(it) }, "the upload context holds a symlink")
    assertTrue(
        files.filter { it.fileName.toString() != "inventory.json" }
            .all { Files.size(it) <= SafariYarnLockRules.CONTEXT_MAX_FILE_BYTES },
        "an uploaded file exceeds the per-file bound",
    )
    assertTrue(
        files.sumOf { Files.size(it) } <= SafariYarnLockRules.CONTEXT_MAX_UPLOAD_BYTES,
        "the uploaded bytes exceed the upload bound",
    )
    assertTrue(
        Files.size(context.resolve("inventory.json")) <=
            SafariYarnLockRules.CONTEXT_MAX_INVENTORY_BYTES,
        "the inventory exceeds its byte bound",
    )
}

private fun glob(directory: Path, prefix: String, suffix: String): List<Path> {
    if (!Files.isDirectory(directory, LinkOption.NOFOLLOW_LINKS)) return emptyList()
    return Files.newDirectoryStream(directory).use { stream ->
        stream.filter {
            val name = it.fileName.toString()
            name.startsWith(prefix) && name.endsWith(suffix)
        }.toList()
    }
}

/** `replace_loose_object`: put the bytes of one object under another object's name. */
private fun replaceLooseObject(
    repository: Path,
    advertised: String,
    source: String,
    kind: String,
) {
    writeLooseObject(repository, advertised, gitBytes(repository, "cat-file", kind, source), kind)
}

private fun writeLooseObject(repository: Path, advertised: String, raw: ByteArray, kind: String) {
    val slot = repository.resolve(".git/objects/${advertised.substring(0, 2)}/${advertised.substring(2)}")
    Files.createDirectories(slot.parent)
    if (Files.exists(slot)) Files.delete(slot)
    val header = "$kind ${raw.size}\u0000".toByteArray(StandardCharsets.ISO_8859_1)
    val compressed = ByteArrayOutputStream()
    DeflaterOutputStream(compressed).use { it.write(header + raw) }
    Files.write(slot, compressed.toByteArray())
}

private fun gitBytes(repository: Path, vararg arguments: String): ByteArray {
    val process = ProcessBuilder(listOf("git", "--no-replace-objects", "-C", repository.toString()) + arguments)
        .start()
    val stdout = process.inputStream.use { it.readBytes() }
    val stderr = process.errorStream.use { it.readBytes() }
    val status = process.waitFor()
    if (status != 0) {
        error("git ${arguments.joinToString(" ")} failed: ${String(stderr, StandardCharsets.UTF_8)}")
    }
    return stdout
}

private fun gitObjectId(repository: Path, revision: String): String =
    String(gitBytes(repository, "rev-parse", revision), StandardCharsets.UTF_8).trim()

/** `hash-object --literally -w --stdin`: store the given bytes as an object of [kind]. */
private fun gitWriteObject(repository: Path, raw: ByteArray, kind: String): String {
    val process = ProcessBuilder(
        listOf(
            "git", "--no-replace-objects", "-C", repository.toString(),
            "hash-object", "--literally", "-w", "-t", kind, "--stdin",
        ),
    ).start()
    process.outputStream.use { it.write(raw) }
    val stdout = process.inputStream.use { it.readBytes() }
    val stderr = process.errorStream.use { it.readBytes() }
    val status = process.waitFor()
    if (status != 0) {
        error("git hash-object failed: ${String(stderr, StandardCharsets.UTF_8)}")
    }
    return String(stdout, StandardCharsets.UTF_8).trim()
}

private fun assertPublicContextRejectsInvalidCandidate(
    fixture: SafariContextFixture,
    context: Path,
    raw: Path,
    detail: String,
) {
    val printed = StringBuilder()
    val errors = StringBuilder()
    val code = captureStderr(errors) { runContextCli(fixture, context, raw, printed) }
    assertEquals(1, code, "errors=[$errors] printed=[$printed]")
    val inventory = readInventory(context)
    assertEquals("CONTEXT_INCOMPLETE", Py.str(inventory["status"]))
    val inputs = inputsOf(inventory)
    assertTrue(
        inputs.any {
            Py.str(it["reason"]) == "scan_failed" &&
                (Py.str(it["error"]) ?: "").contains(detail)
        },
        inputs.toString(),
    )
}

/** The Karma context scanner: the enumerated configuration, its bounds, and its inventory. */
val SafariContextScanner by testSuite {
    test("the ten context bounds are the reference's, in the reference's order") {
        assertEquals(SafariYarnLockVectors.CONTEXT_LIMITS, SafariContextBounds().limits())
    }

    test("the scanner inventory invariants match the reference") {
        withContextFixture { fixture ->
            val (context, packageRoot) = fixture.contextFixture()
            fixture.writeValidKarmaConfigs()
            Files.createSymbolicLink(packageRoot.resolve("node_modules"), fixture.root)
            val inventory = captureContext(fixture, context, fixture.rawContext)
            val vector = SafariYarnLockVectors.CONTEXT_INVENTORY
            assertEquals(vector.status, Py.str(inventory["status"]))
            assertEquals(vector.configuration, Py.str(inventory["configuration"]))
            assertEquals(vector.copiedFiles, Py.int(inventory["copied_files"]!!))
            assertEquals(vector.matchedFiles, Py.int(inventory["matched_files"]!!))
            assertEquals(vector.entriesSeen, Py.int(inventory["entries_seen"]!!))
            val observed = inputsOf(inventory)
                .filter { "/" !in (Py.str(it["path"]) ?: "/") }
                .sortedBy { Py.str(it["path"])!! }
                .map {
                    listOf(
                        Py.str(it["path"]),
                        Py.str(it["status"]),
                        Py.str(it["reason"]),
                        Py.int(it["original_size"]!!).toString(),
                        Py.int(it["retained_size"]!!).toString(),
                        Py.str(it["sha256"]),
                    )
                }
            val expected = vector.sidecars.map {
                listOf(
                    it.path,
                    it.status,
                    it.reason,
                    it.originalSize.toString(),
                    it.retainedSize.toString(),
                    it.sha256,
                )
            }
            assertEquals(expected, observed)
        }
    }

    test("a regular unique config is copied with its inventory") {
        withContextFixture { fixture ->
            val (context, packageRoot) = fixture.contextFixture()
            val source = packageRoot.resolve("karma.conf.js")
            fixture.writeValidKarmaConfigs()
            Files.createSymbolicLink(packageRoot.resolve("node_modules"), fixture.root)
            val inventory = captureContext(fixture, context, fixture.rawContext)
            assertEquals("CONTEXT_COMPLETE", Py.str(inventory["status"]), inputsOf(inventory).toString())
            assertEquals(false, Py.truthy(inventory["qualified"]))
            assertEquals(
                String(Files.readAllBytes(source), StandardCharsets.ISO_8859_1),
                String(
                    Files.readAllBytes(
                        context.resolve("config")
                            .resolve(SafariYarnLockRules.CONTEXT_ROOTS[0])
                            .resolve("karma.conf.js"),
                    ),
                    StandardCharsets.ISO_8859_1,
                ),
            )
            val inputs = inputsOf(inventory)
            assertTrue(inputs.any { Py.str(it["status"]) == "copied" })
            assertTrue(inputs.any { Py.str(it["reason"]) == "excluded_node_modules" })
            assertTrue(
                inputs.any {
                    Py.str(it["path"]) == "process-after.txt" &&
                        Py.int(it["original_size"]!!) == Py.int(it["retained_size"]!!)
                },
            )
            assertTrue(
                inputs.any {
                    Py.str(it["path"]) == "launch-123.txt" &&
                        Py.int(it["original_size"]!!) == Py.int(it["retained_size"]!!)
                },
            )
            assertEquals(inventory, readInventory(context))
            assertContextUploadBound(context)
        }
    }

    test("a canonical config is accepted through an aliased repository") {
        withContextFixture { fixture ->
            val alias = fixture.root.resolve("source-alias")
            Files.createSymbolicLink(alias, fixture.repository)
            fixture.repository = alias
            val (context, _) = fixture.contextFixture("-aliased-repository")
            fixture.writeValidKarmaConfigs()
            val inventory = captureContext(fixture, context, fixture.rawContext)
            assertEquals("CONTEXT_COMPLETE", Py.str(inventory["status"]), inputsOf(inventory).toString())
        }
    }

    test("an irrelevant klib cache is not scanned") {
        withContextFixture { fixture ->
            val (context, _) = fixture.contextFixture()
            fixture.writeValidKarmaConfigs()
            val cache = fixture.repository.resolve(
                "dyn4k-core/build/klib/cache/js/testDevelopmentExecutable",
            )
            Files.createDirectories(cache)
            for (number in 0 until 2050) {
                Files.write(cache.resolve("entry-$number.bin"), byteArrayOf('x'.code.toByte()))
            }
            val inventory = captureContext(fixture, context, fixture.rawContext)
            assertEquals("CONTEXT_COMPLETE", Py.str(inventory["status"]))
            assertEquals(2L, Py.int(inventory["copied_files"]!!))
            assertTrue(Py.int(inventory["entries_seen"]!!) < SafariYarnLockRules.CONTEXT_MAX_ENTRIES)
        }
    }

    test("both module configs are required") {
        withContextFixture { fixture ->
            val (context, _) = fixture.contextFixture()
            val packageRoot = fixture.repository.resolve(SafariYarnLockRules.CONTEXT_ROOTS[0])
            Files.createDirectories(packageRoot)
            Files.writeString(packageRoot.resolve("karma.conf.js"), "// core\n")
            val inventory = captureContext(fixture, context, fixture.rawContext)
            assertEquals("CONTEXT_INCOMPLETE", Py.str(inventory["status"]))
            assertTrue(inputsOf(inventory).any { Py.str(it["reason"]) == "missing_module_karma_config" })
        }
    }

    test("a per-file byte limit truncates and says so") {
        withContextFixture { fixture ->
            val (context, packageRoot) = fixture.contextFixture()
            Files.write(packageRoot.resolve("a-karma.js"), "12345".toByteArray())
            val inventory = captureContext(
                fixture,
                context,
                fixture.rawContext,
                SafariContextBounds(fileBytes = 4, totalBytes = 10),
            )
            assertEquals("CONTEXT_INCOMPLETE", Py.str(inventory["status"]))
            assertEquals(4L, Py.int(inventory["copied_bytes"]!!))
            assertEquals("per_file_byte_limit", Py.str(inputsOf(inventory)[0]["reason"]))
        }
    }

    test("a total byte limit truncates and says so") {
        withContextFixture { fixture ->
            val (context, packageRoot) = fixture.contextFixture()
            Files.write(packageRoot.resolve("a-karma.js"), "12345".toByteArray())
            val inventory = captureContext(
                fixture,
                context,
                fixture.rawContext,
                SafariContextBounds(fileBytes = 10, totalBytes = 3),
            )
            assertEquals("CONTEXT_INCOMPLETE", Py.str(inventory["status"]))
            assertEquals(3L, Py.int(inventory["copied_bytes"]!!))
            assertEquals("total_byte_limit", Py.str(inputsOf(inventory)[0]["reason"]))
        }
    }

    test("a duplicate inode is skipped") {
        withContextFixture { fixture ->
            val (context, packageRoot) = fixture.contextFixture()
            val source = packageRoot.resolve("a-karma.js")
            Files.writeString(source, "config\n")
            Files.createLink(packageRoot.resolve("b-karma.js"), source)
            val inventory = captureContext(fixture, context, fixture.rawContext)
            assertEquals("CONTEXT_INCOMPLETE", Py.str(inventory["status"]))
            assertEquals(1L, Py.int(inventory["copied_files"]!!))
            assertTrue(inputsOf(inventory).any { Py.str(it["reason"]) == "duplicate_inode" })
        }
    }

    test("a symlink is never traversed") {
        withContextFixture { fixture ->
            val (context, packageRoot) = fixture.contextFixture()
            val outside = fixture.root.resolve("outside")
            Files.createDirectories(outside)
            Files.writeString(outside.resolve("outside-karma.js"), "outside\n")
            Files.createSymbolicLink(packageRoot.resolve("linked"), outside)
            Files.createSymbolicLink(
                packageRoot.resolve("linked-karma.js"),
                outside.resolve("outside-karma.js"),
            )
            val inventory = captureContext(fixture, context, fixture.rawContext)
            assertEquals("CONTEXT_INCOMPLETE", Py.str(inventory["status"]))
            assertTrue(inputsOf(inventory).any { Py.str(it["reason"]) == "symlink" })
            assertFalse(
                Files.exists(
                    context.resolve("config")
                        .resolve(SafariYarnLockRules.CONTEXT_ROOTS[0])
                        .resolve("linked/outside-karma.js"),
                ),
            )
        }
    }

    test("the file count bound rejects the scan") {
        withContextFixture { fixture ->
            val (context, packageRoot) = fixture.contextFixture()
            Files.writeString(packageRoot.resolve("a-karma.js"), "a\n")
            Files.writeString(packageRoot.resolve("b-karma.js"), "b\n")
            val inventory = captureContext(
                fixture,
                context,
                fixture.rawContext,
                SafariContextBounds(files = 1),
            )
            assertEquals("CONTEXT_INCOMPLETE", Py.str(inventory["status"]))
            assertTrue(inputsOf(inventory).any { Py.str(it["reason"]) == "file_count_limit" })
            assertTrue(Py.int(inventory["copied_files"]!!) <= 1L)
        }
    }

    test("a symlinked module root is missing or unsafe") {
        withContextFixture { fixture ->
            val (context, packageRoot) = fixture.contextFixture()
            val outside = fixture.root.resolve("outside")
            Files.createDirectories(outside)
            Files.writeString(outside.resolve("karma.conf.js"), "outside\n")
            Files.delete(packageRoot)
            Files.createSymbolicLink(packageRoot, outside)
            val inventory = captureContext(fixture, context, fixture.rawContext)
            assertEquals("CONTEXT_INCOMPLETE", Py.str(inventory["status"]))
            assertEquals(0L, Py.int(inventory["copied_files"]!!))
            assertTrue(inputsOf(inventory).any { Py.str(it["reason"]) == "missing_or_unsafe_root" })
        }
    }

    test("the traversal deadline and a failed scan are both retained") {
        withContextFixture { fixture ->
            val (context, packageRoot) = fixture.contextFixture()
            Files.writeString(packageRoot.resolve("karma.conf.js"), "config\n")
            val inventory = captureContext(
                fixture,
                context,
                fixture.rawContext,
                SafariContextBounds(seconds = 0),
            )
            assertEquals("CONTEXT_INCOMPLETE", Py.str(inventory["status"]))
            assertTrue(inputsOf(inventory).any { Py.str(it["reason"]) == "traversal_deadline" })
            val second = fixture.root.resolve("second-context")
            val failed = captureContext(
                fixture,
                second,
                fixture.rawContext,
                scanHook = { _, _ -> throw java.io.IOException("scan failed") },
            )
            assertEquals("CONTEXT_INCOMPLETE", Py.str(failed["status"]))
            assertTrue(inputsOf(failed).any { Py.str(it["status"]) == "failed" })
        }
    }

    test("configs without the committed reporter are rejected") {
        withContextFixture { fixture ->
            val (context, _) = fixture.contextFixture()
            val packageRoot = fixture.repository.resolve(SafariYarnLockRules.CONTEXT_ROOTS[0])
            Files.writeString(packageRoot.resolve("karma.conf.js"), "module.exports = {};\n")
            Files.writeString(
                fixture.repository.resolve(SafariYarnLockRules.CONTEXT_ROOTS[1])
                    .resolve("karma.conf.js"),
                "module.exports = {};\n",
            )
            val printed = StringBuilder()
            assertEquals(1, runContextCli(fixture, context, fixture.rawContext, printed))
            val inventory = readInventory(context)
            assertEquals("CONTEXT_INCOMPLETE", Py.str(inventory["status"]))
            assertEquals(
                2,
                inputsOf(inventory).count { Py.str(it["reason"]) == "reporter_fragment_missing" },
            )
            assertEquals(
                Py.str(inventory["status"]),
                Py.str((StrictJson.load(printed.toString()) as JsonObject)["status"]),
            )
        }
    }
}

/** The reporter binding: eight configuration mutations the scanner must refuse. */
val SafariContextBinding by testSuite {
    test("the exact reporter and module source are bound") {
        val mutations = listOf(
            "none",
            "altered_fragment",
            "other_module",
            "mixed_mode",
            "later_override",
            "commented_fragment",
            "provider_clear",
            "bracket_chrome",
        )
        for (mutation in mutations) {
            withContextFixture { fixture ->
                val (context, _) = fixture.contextFixture(mutation)
                fixture.writeValidKarmaConfigs()
                val core = fixture.projectConfig(0)
                val facade = fixture.projectConfig(1)
                if (mutation == "altered_fragment") {
                    Files.writeString(
                        facade,
                        Files.readString(facade).replace(
                            "this.write = function(message)",
                            "this.log = function(message)",
                        ),
                    )
                } else if (mutation == "other_module") {
                    Files.write(facade, Files.readAllBytes(core))
                } else if (mutation == "mixed_mode") {
                    val developmentCore = Files.readAllBytes(core)
                    fixture.writeValidKarmaConfigs("production")
                    Files.write(core, developmentCore)
                } else if (mutation == "later_override") {
                    val text = Files.readString(facade)
                    val split = text.lastIndexOf("\n}\n")
                    val head = text.substring(0, split)
                    val tail = text.substring(split + 3)
                    Files.writeString(
                        facade,
                        head + "\nconfig.set({browsers: ['ChromeHeadless']});\n}\n" + tail,
                    )
                } else if (mutation == "commented_fragment") {
                    Files.writeString(
                        facade,
                        Files.readString(facade).replace(
                            "const DYN4K_SAFARI_REPORTER_NEWLINES",
                            "// const DYN4K_SAFARI_REPORTER_NEWLINES",
                        ),
                    )
                } else if (mutation == "provider_clear") {
                    val fragment = fixture.reporterText()
                    Files.writeString(
                        facade,
                        Files.readString(facade).replace(fragment, "config.plugins = [];\n" + fragment),
                    )
                } else if (mutation == "bracket_chrome") {
                    val fragment = fixture.reporterText()
                    Files.writeString(
                        facade,
                        Files.readString(facade).replace(
                            fragment,
                            "config['set']({browsers: ['ChromeHeadless']});\n" + fragment,
                        ),
                    )
                }
                val printed = StringBuilder()
                val raw = fixture.rawContext
                assertEquals(
                    if (mutation == "none") 0 else 1,
                    runContextCli(fixture, context, raw, printed),
                    mutation,
                )
                val inventory = readInventory(context)
                assertEquals(
                    if (mutation == "none") "CONTEXT_COMPLETE" else "CONTEXT_INCOMPLETE",
                    Py.str(inventory["status"]),
                    mutation,
                )
                assertEquals(
                    Py.str(inventory["status"]),
                    Py.str((StrictJson.load(printed.toString()) as JsonObject)["status"]),
                    mutation,
                )
                if (mutation != "none") {
                    assertTrue(
                        inputsOf(inventory).any {
                            Py.str(it["reason"]) in setOf(
                                "reporter_fragment_missing",
                                "karma_config_module_mismatch",
                                "karma_config_source_mismatch",
                                "karma_config_shape_mismatch",
                                "reporter_fragment_in_comment",
                            )
                        },
                        "$mutation: ${inputsOf(inventory)}",
                    )
                }
            }
        }
    }
}

/** The corruption cases: a candidate whose Git objects do not hash to their own names. */
val SafariContextCandidate by testSuite {
    test("a same-type replacement commit is rejected") {
        withContextFixture { fixture ->
            val (context, _) = fixture.contextFixture()
            fixture.writeValidKarmaConfigs()
            val lock = fixture.repository.resolve(SafariYarnLockRules.TRACKED_LOCK)
            Files.write(lock, "replacement lock bytes\n".toByteArray())
            hostedGit(fixture.repository, "add", SafariYarnLockRules.TRACKED_LOCK)
            hostedGit(
                fixture.repository, "-c", "user.name=Test",
                "-c", "user.email=test@example.invalid", "commit", "-qm", "replacement source",
            )
            val replacement = gitObjectId(fixture.repository, "HEAD")
            hostedGit(fixture.repository, "checkout", "-q", "--detach", fixture.candidate)
            hostedGit(fixture.repository, "read-tree", "$replacement^{tree}")
            Files.write(lock, "replacement lock bytes\n".toByteArray())
            hostedGit(fixture.repository, "replace", fixture.candidate, replacement)
            val printed = StringBuilder()
            assertEquals(1, runContextCli(fixture, context, fixture.rawContext, printed))
            val inventory = readInventory(context)
            assertEquals("CONTEXT_INCOMPLETE", Py.str(inventory["status"]))
            assertTrue(inputsOf(inventory).any { Py.str(it["reason"]) == "scan_failed" })
        }
    }

    test("a corrupt candidate commit is rejected") {
        withContextFixture { fixture ->
            val (context, _) = fixture.contextFixture()
            val changed = alteredReporterCandidate(fixture)
            replaceLooseObject(fixture.repository, fixture.candidate, changed, "commit")
            assertEquals(
                "",
                hostedGit(
                    fixture.repository, "status", "--porcelain=v1", "--untracked-files=all",
                ),
            )
            assertPublicContextRejectsInvalidCandidate(fixture, context, fixture.rawContext, "identity differs")
        }
    }

    test("a corrupt root tree is rejected") {
        withContextFixture { fixture ->
            val (context, _) = fixture.contextFixture()
            val changed = alteredReporterCandidate(fixture)
            replaceLooseObject(
                fixture.repository,
                gitObjectId(fixture.repository, fixture.candidate + "^{tree}"),
                gitObjectId(fixture.repository, changed + "^{tree}"),
                "tree",
            )
            assertPublicContextRejectsInvalidCandidate(fixture, context, fixture.rawContext, "identity differs")
        }
    }

    test("a corrupt intermediate tree is rejected") {
        withContextFixture { fixture ->
            val (context, _) = fixture.contextFixture()
            val changed = alteredReporterCandidate(fixture)
            val path = "tools/qualification"
            replaceLooseObject(
                fixture.repository,
                gitObjectId(fixture.repository, "${fixture.candidate}:$path"),
                gitObjectId(fixture.repository, "$changed:$path"),
                "tree",
            )
            assertPublicContextRejectsInvalidCandidate(fixture, context, fixture.rawContext, "identity differs")
        }
    }

    test("a corrupt reporter blob is rejected") {
        withContextFixture { fixture ->
            val (context, _) = fixture.contextFixture()
            val changed = alteredReporterCandidate(fixture)
            val path = SafariReporter.SOURCE
            replaceLooseObject(
                fixture.repository,
                gitObjectId(fixture.repository, "${fixture.candidate}:$path"),
                gitObjectId(fixture.repository, "$changed:$path"),
                "blob",
            )
            hostedGit(fixture.repository, "read-tree", fixture.candidate + "^{tree}")
            hostedGit(fixture.repository, "update-index", "--assume-unchanged", path)
            assertEquals(
                "",
                hostedGit(
                    fixture.repository, "status", "--porcelain=v1", "--untracked-files=all",
                ),
            )
            assertPublicContextRejectsInvalidCandidate(fixture, context, fixture.rawContext, "identity differs")
        }
    }

    test("a corrupt tracked lock blob is rejected") {
        withContextFixture { fixture ->
            val (context, _) = fixture.contextFixture()
            fixture.writeValidKarmaConfigs()
            val path = SafariYarnLockRules.TRACKED_LOCK
            val lock = fixture.repository.resolve(path)
            Files.write(lock, "altered tracked lock\n".toByteArray())
            hostedGit(fixture.repository, "add", path)
            hostedGit(
                fixture.repository, "-c", "user.name=Test",
                "-c", "user.email=test@example.invalid", "commit", "-qm", "altered lock",
            )
            val changed = gitObjectId(fixture.repository, "HEAD")
            hostedGit(fixture.repository, "checkout", "-q", "--detach", fixture.candidate)
            Files.write(lock, "altered tracked lock\n".toByteArray())
            replaceLooseObject(
                fixture.repository,
                gitObjectId(fixture.repository, "${fixture.candidate}:$path"),
                gitObjectId(fixture.repository, "$changed:$path"),
                "blob",
            )
            hostedGit(fixture.repository, "update-index", "--assume-unchanged", path)
            assertEquals(
                "",
                hostedGit(
                    fixture.repository, "status", "--porcelain=v1", "--untracked-files=all",
                ),
            )
            assertPublicContextRejectsInvalidCandidate(fixture, context, fixture.rawContext, "identity differs")
        }
    }

    test("a duplicate unrelated tree entry is rejected") {
        withContextFixture { fixture ->
            val (context, _) = fixture.contextFixture()
            fixture.writeValidKarmaConfigs()
            val root = gitObjectId(fixture.repository, fixture.candidate + "^{tree}")
            val rawTree = gitBytes(fixture.repository, "cat-file", "tree", root)
            val firstEnd = rawTree.indexOf(0.toByte()) + 21
            assertFalse(
                String(rawTree.copyOf(firstEnd), StandardCharsets.ISO_8859_1).contains("tools\u0000"),
            )
            val duplicateTree = gitWriteObject(
                fixture.repository,
                rawTree + rawTree.copyOf(firstEnd),
                "tree",
            )
            val commit = gitBytes(fixture.repository, "cat-file", "commit", fixture.candidate)
            val treeLine = "tree $root\n".toByteArray(StandardCharsets.ISO_8859_1)
            val replacement = "tree $duplicateTree\n".toByteArray(StandardCharsets.ISO_8859_1)
            val position = String(commit, StandardCharsets.ISO_8859_1).indexOf("tree $root\n")
            assertTrue(position >= 0, "the commit does not name its root tree")
            val changed = commit.copyOf(position) + replacement +
                commit.copyOfRange(position + treeLine.size, commit.size)
            val duplicateCommit = gitWriteObject(fixture.repository, changed, "commit")
            hostedGit(fixture.repository, "update-ref", "HEAD", duplicateCommit)
            fixture.candidate = duplicateCommit
            assertPublicContextRejectsInvalidCandidate(fixture, context, fixture.rawContext, "duplicate")
        }
    }
}

/** `altered_reporter_candidate`: a real commit whose reporter bytes differ from the candidate. */
private fun alteredReporterCandidate(fixture: SafariContextFixture): String {
    val reporter = fixture.repository.resolve(SafariReporter.SOURCE)
    Files.write(
        reporter,
        Files.readAllBytes(reporter) + "\n// altered reporter\n".toByteArray(),
    )
    hostedGit(fixture.repository, "add", reporter.toString())
    hostedGit(
        fixture.repository, "-c", "user.name=Test",
        "-c", "user.email=test@example.invalid", "commit", "-qm", "altered reporter",
    )
    val changed = gitObjectId(fixture.repository, "HEAD")
    hostedGit(fixture.repository, "checkout", "-q", "--detach", fixture.candidate)
    hostedGit(fixture.repository, "read-tree", changed + "^{tree}")
    Files.write(
        reporter,
        gitBytes(fixture.repository, "show", "$changed:${SafariReporter.SOURCE}"),
    )
    fixture.writeValidKarmaConfigs()
    return changed
}

/** The sampler sidecars: the raw launch context's checks and bounds. */
val SafariContextSampler by testSuite {
    test("an unfinished sampler is rejected") {
        withContextFixture { fixture ->
            val (context, packageRoot) = fixture.contextFixture()
            Files.writeString(packageRoot.resolve("karma.conf.js"), "config\n")
            Files.delete(fixture.root.resolve("raw-context/sample-state-123.txt"))
            val inventory = captureContext(fixture, context, fixture.rawContext)
            assertEquals("CONTEXT_INCOMPLETE", Py.str(inventory["status"]))
            assertTrue(inputsOf(inventory).any { Py.str(it["reason"]) == "sampler_incomplete" })
        }
    }

    test("a pending open is recorded as incomplete and retained") {
        withContextFixture { fixture ->
            val (context, packageRoot) = fixture.contextFixture()
            Files.writeString(packageRoot.resolve("karma.conf.js"), "config\n")
            Files.writeString(
                fixture.root.resolve("raw-context/launch-outcome-123.txt"),
                "open_state=pending\n",
            )
            val inventory = captureContext(fixture, context, fixture.rawContext)
            assertEquals("CONTEXT_INCOMPLETE", Py.str(inventory["status"]))
            assertTrue(inputsOf(inventory).any { Py.str(it["reason"]) == "open_pending" })
            assertEquals(
                "open_state=pending\n",
                Files.readString(context.resolve("launch-outcome-123.txt")),
            )
        }
    }

    test("missing process samples are rejected") {
        withContextFixture { fixture ->
            val (context, packageRoot) = fixture.contextFixture()
            Files.writeString(packageRoot.resolve("karma.conf.js"), "config\n")
            Files.delete(fixture.root.resolve("raw-context/process-123.txt"))
            val inventory = captureContext(fixture, context, fixture.rawContext)
            assertEquals("CONTEXT_INCOMPLETE", Py.str(inventory["status"]))
            assertTrue(inputsOf(inventory).any { Py.str(it["reason"]) == "sampler_incomplete" })
        }
    }

    test("missing launch output is rejected") {
        withContextFixture { fixture ->
            val (context, packageRoot) = fixture.contextFixture()
            Files.writeString(packageRoot.resolve("karma.conf.js"), "config\n")
            Files.delete(fixture.root.resolve("raw-context/open-123.stderr"))
            val inventory = captureContext(fixture, context, fixture.rawContext)
            assertEquals("CONTEXT_INCOMPLETE", Py.str(inventory["status"]))
            assertTrue(
                inputsOf(inventory).any { Py.str(it["reason"]) == "missing_or_unreadable_sidecar" },
            )
        }
    }

    test("an oversized process snapshot is rejected and bounded") {
        withContextFixture { fixture ->
            val (context, packageRoot) = fixture.contextFixture()
            Files.writeString(packageRoot.resolve("karma.conf.js"), "config\n")
            Files.write(
                fixture.root.resolve("raw-context/process-after.txt"),
                ByteArray(1_572_864) { 'P'.code.toByte() },
            )
            val inventory = captureContext(fixture, context, fixture.rawContext)
            assertEquals("CONTEXT_INCOMPLETE", Py.str(inventory["status"]))
            assertTrue(Files.size(context.resolve("process-after.txt")) <= 256L * 1024)
            assertTrue(
                inputsOf(inventory).any {
                    Py.str(it["path"]) == "process-after.txt" &&
                        Py.int(it["original_size"]!!) == 1_572_864L &&
                        Py.int(it["retained_size"]!!) <= 256L * 1024 &&
                        Py.str(it["status"]) == "truncated"
                },
            )
            assertContextUploadBound(context)
        }
    }

    test("a large launch log and session snapshot are rejected and bounded") {
        withContextFixture { fixture ->
            val (context, packageRoot) = fixture.contextFixture()
            Files.writeString(packageRoot.resolve("karma.conf.js"), "config\n")
            Files.write(
                fixture.root.resolve("raw-context/session-after.txt"),
                ByteArray(614_400) { 'S'.code.toByte() },
            )
            Files.write(
                fixture.root.resolve("raw-context/launch-123.txt"),
                ByteArray(614_400) { 'L'.code.toByte() },
            )
            val printed = StringBuilder()
            assertEquals(1, runContextCli(fixture, context, fixture.rawContext, printed))
            assertEquals(
                "CONTEXT_INCOMPLETE",
                Py.str((StrictJson.load(printed.toString()) as JsonObject)["status"]),
            )
            val inventory = readInventory(context)
            assertEquals("CONTEXT_INCOMPLETE", Py.str(inventory["status"]))
            for (name in listOf("session-after.txt", "launch-123.txt")) {
                assertTrue(Files.size(context.resolve(name)) <= 256L * 1024)
                assertTrue(
                    inputsOf(inventory).any {
                        Py.str(it["path"]) == name &&
                            Py.int(it["original_size"]!!) == 614_400L &&
                            Py.int(it["retained_size"]!!) <= 256L * 1024 &&
                            Py.str(it["status"]) == "truncated"
                    },
                )
            }
            assertContextUploadBound(context)
        }
    }

    test("the command line rejects an oversized reviewer snapshot") {
        withContextFixture { fixture ->
            val (context, packageRoot) = fixture.contextFixture()
            Files.writeString(packageRoot.resolve("karma.conf.js"), "config\n")
            Files.write(
                fixture.root.resolve("raw-context/process-after.txt"),
                ByteArray(1_572_864) { 'P'.code.toByte() },
            )
            val printed = StringBuilder()
            assertEquals(1, runContextCli(fixture, context, fixture.rawContext, printed))
            assertEquals(
                "CONTEXT_INCOMPLETE",
                Py.str((StrictJson.load(printed.toString()) as JsonObject)["status"]),
            )
            assertContextUploadBound(context)
        }
    }

    test("the aggregate upload budget caps the sidecars") {
        withContextFixture { fixture ->
            val (context, packageRoot) = fixture.contextFixture()
            Files.writeString(packageRoot.resolve("karma.conf.js"), "config\n")
            Files.write(
                fixture.root.resolve("raw-context/process-after.txt"),
                ByteArray(614_400) { 'P'.code.toByte() },
            )
            val inventory = captureContext(
                fixture,
                context,
                fixture.rawContext,
                SafariContextBounds(
                    uploadBytes = SafariYarnLockRules.CONTEXT_MAX_INVENTORY_BYTES + 100,
                ),
            )
            assertContextUploadBound(context)
            assertEquals("CONTEXT_INCOMPLETE", Py.str(inventory["status"]))
            assertTrue(inputsOf(inventory).any { Py.str(it["reason"]) == "upload_byte_limit" })
        }
    }

    test("a symlinked host snapshot is rejected") {
        withContextFixture { fixture ->
            val (context, packageRoot) = fixture.contextFixture()
            Files.writeString(packageRoot.resolve("karma.conf.js"), "config\n")
            val outside = fixture.root.resolve("outside.txt")
            Files.writeString(outside, "outside\n")
            val snapshot = fixture.root.resolve("raw-context/session-after.txt")
            Files.delete(snapshot)
            Files.createSymbolicLink(snapshot, outside)
            val inventory = captureContext(fixture, context, fixture.rawContext)
            assertEquals("CONTEXT_INCOMPLETE", Py.str(inventory["status"]))
            assertFalse(Files.exists(context.resolve("session-after.txt")))
            assertTrue(
                inputsOf(inventory).any {
                    Py.str(it["path"]) == "session-after.txt" && Py.str(it["status"]) == "failed"
                },
            )
            assertContextUploadBound(context)
        }
    }

    test("a missing host snapshot is rejected") {
        withContextFixture { fixture ->
            val (context, packageRoot) = fixture.contextFixture()
            Files.writeString(packageRoot.resolve("karma.conf.js"), "config\n")
            Files.delete(fixture.root.resolve("raw-context/session-after.txt"))
            val inventory = captureContext(fixture, context, fixture.rawContext)
            assertEquals("CONTEXT_INCOMPLETE", Py.str(inventory["status"]))
            assertTrue(
                inputsOf(inventory).any {
                    Py.str(it["path"]) == "session-after.txt" && Py.str(it["status"]) == "failed"
                },
            )
        }
    }

    test("the command line reports an incomplete context with a nonzero exit") {
        withContextFixture { fixture ->
            val (context, packageRoot) = fixture.contextFixture()
            Files.writeString(packageRoot.resolve("karma.conf.js"), "config\n")
            Files.delete(fixture.root.resolve("raw-context/sample-state-123.txt"))
            val printed = StringBuilder()
            assertEquals(1, runContextCli(fixture, context, fixture.rawContext, printed))
            assertEquals(
                "CONTEXT_INCOMPLETE",
                Py.str((StrictJson.load(printed.toString()) as JsonObject)["status"]),
            )
            assertEquals(false, Py.truthy(readInventory(context)["qualified"]))
        }
    }
}
