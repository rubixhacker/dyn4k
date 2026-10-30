package io.github.rubixhacker.harness.compatibility

import de.infix.testBalloon.framework.core.testSuite
import io.github.rubixhacker.harness.contract.CanonicalJson
import io.github.rubixhacker.harness.contract.Sha256
import io.github.rubixhacker.harness.host.FileDigest
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.Path
import kotlin.io.path.createDirectories
import kotlin.io.path.writeText
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

private val fullCiFiles = JvmCorpusFiles()

private fun temp(): Path = Files.createTempDirectory("dyn4k-compat-")

private fun str(value: String): JsonPrimitive = JsonPrimitive(value)

private fun num(value: Long): JsonPrimitive = JsonPrimitive(value)

private fun json(vararg pairs: Pair<String, JsonElement>): JsonObject =
    JsonObject(linkedMapOf(*pairs))

private fun write(path: Path, text: String) {
    path.parent?.createDirectories()
    path.writeText(text, StandardCharsets.UTF_8)
}

private fun writeBytes(path: Path, bytes: ByteArray) {
    path.parent?.createDirectories()
    Files.write(path, bytes)
}

private fun copyTree(source: Path, target: Path) {
    target.createDirectories()
    Files.walk(source).use { stream ->
        stream.forEach { path ->
            val relative = source.relativize(path)
            if (relative.toString().isEmpty()) return@forEach
            val destination = target.resolve(relative.toString())
            if (Files.isDirectory(path)) {
                destination.createDirectories()
            } else {
                destination.parent?.createDirectories()
                Files.copy(path, destination)
            }
        }
    }
}

private fun failureMessage(block: () -> Unit): String {
    val thrown = assertFailsWith<Exception> { block() }
    return thrown.message ?: thrown.toString()
}

/**
 * The self-contained cases of `test_full_ci.py`, ported to the Kotlin contract.
 *
 * Cases that replay the pinned evidence tree (`test_production_source_replay...`,
 * `test_projection_rejects...`, `test_changed_pinned_test_source_is_rejected` beyond the source
 * input check) stay with the unported archive replay.
 */
val FullCiContract by testSuite {
    test("archive file inventory survives copy and rejects changed paths") {
        val base = temp()
        try {
            val original = base.resolve("original")
            write(original.resolve("fixture/stream.ser"), "pinned stream")
            write(original.resolve("result.json"), """{"status":"PASSED"}""")
            val recorded = FullCi.snapshotArchive(fullCiFiles, original.toString())
            assertEquals(setOf("fixture/stream.ser", "result.json"), recorded.keys)

            val copied = base.resolve("copied")
            copyTree(original, copied)
            FullCi.verifyArchiveFiles(fullCiFiles, copied.toString(), recorded)

            val stream = copied.resolve("fixture/stream.ser")
            write(stream, "changed stream")
            assertTrue(failureMessage {
                FullCi.verifyArchiveFiles(fullCiFiles, copied.toString(), recorded)
            }.contains("archive file hash"))

            write(stream, "pinned stream")
            write(copied.resolve("extra"), "extra")
            assertTrue(failureMessage {
                FullCi.verifyArchiveFiles(fullCiFiles, copied.toString(), recorded)
            }.contains("archive file set"))

            Files.delete(copied.resolve("extra"))
            Files.delete(stream)
            Files.createSymbolicLink(stream, original.resolve("fixture/stream.ser"))
            assertTrue(failureMessage {
                FullCi.verifyArchiveFiles(fullCiFiles, copied.toString(), recorded)
            }.contains("symlink"))
        } finally {
            deleteTree(base)
        }
    }

    test("archive manifest rejects duplicate and traversal paths") {
        val output = temp()
        try {
            write(output.resolve("result.json"), "{}")
            val sha = Sha256.of("{}")
            val inventories = listOf(
                mapOf("../result.json" to sha),
                mapOf("/tmp/result.json" to sha),
                mapOf("folder\\..\\result.json" to sha),
                mapOf("result.json" to sha, "./result.json" to sha),
            )
            for (inventory in inventories) {
                assertTrue(failureMessage {
                    FullCi.verifyArchiveFiles(fullCiFiles, output.toString(), inventory)
                }.contains("archive path or hash is unsafe"))
            }
            val duplicate = """{"files":{"result.json":"a","result.json":"b"}}"""
            assertEquals(
                "duplicate JSON key: result.json",
                failureMessage { FullCi.loadJsonUnique(duplicate) },
            )
            assertEquals(
                "a",
                FullCi.loadJsonUnique("""{"files":{"result.json":"a"}}""")
                    .objectOrNull()!!.objectOrNull("files")!!.textOrNull("result.json"),
            )
        } finally {
            deleteTree(output)
        }
    }

    test("exception process paths map only declared output root") {
        val row = json(
            "operation" to str("write"),
            "runtime" to str("jdk8"),
            "provider" to str("jvm"),
            "writer_runtime" to str("jdk8"),
            "writer_provider" to str("jvm"),
            "case" to str("ArgumentNullException"),
            "command" to JsonArray(
                listOf(
                    str("/jdk8/bin/java"), str("-cp"),
                    str(
                        "/frozen/output/exception-serialization/fixture/classes/jvm:" +
                            "/frozen/output/exception-serialization/fixture/jvm.jar:" +
                            "/frozen/output/deps/kotlin-stdlib-2.4.20.jar",
                    ),
                    str("ExceptionSerializationProbe"), str("write"),
                    str(
                        "/frozen/output/exception-serialization/fixture/" +
                            "jdk8-jvm-ArgumentNullException.ser",
                    ),
                    str("ArgumentNullException"),
                ),
            ),
        )
        val jdks = mapOf("jdk8" to "/jdk8")
        val mapped = FullCi.relocateExceptionRuns(
            listOf(row),
            "/frozen/output",
            "/downloaded/output",
            jdks,
        )
        assertEquals(
            "/downloaded/output/exception-serialization/fixture/jdk8-jvm-ArgumentNullException.ser",
            mapped[0]["command"].arrayOrNull()!![5].textOrNull(),
        )
        assertEquals(
            "/frozen/output/exception-serialization/fixture/jdk8-jvm-ArgumentNullException.ser",
            row["command"].arrayOrNull()!![5].textOrNull(),
        )

        val command = row["command"].arrayOrNull()!!
        val changed = json(
            "operation" to str("write"),
            "runtime" to str("jdk8"),
            "provider" to str("jvm"),
            "writer_runtime" to str("jdk8"),
            "writer_provider" to str("jvm"),
            "case" to str("ArgumentNullException"),
            "command" to JsonArray(
                command.dropLast(2) + listOf(
                    str("/elsewhere/jdk8-jvm-ArgumentNullException.ser"),
                    str("ArgumentNullException"),
                ),
            ),
        )
        assertTrue(failureMessage {
            FullCi.relocateExceptionRuns(listOf(changed), "/frozen/output", "/downloaded/output", jdks)
        }.contains("exception process command"))

        val swapped = json(
            "operation" to str("write"),
            "runtime" to str("jdk8"),
            "provider" to str("jvm"),
            "writer_runtime" to str("jdk8"),
            "writer_provider" to str("jvm"),
            "case" to str("ArgumentNullException"),
            "command" to JsonArray(
                command.mapIndexed { index, element ->
                    if (index == 2) {
                        str(element.textOrNull()!!.replace("/classes/jvm:", "/classes/android:"))
                    } else {
                        element
                    }
                },
            ),
        )
        assertTrue(failureMessage {
            FullCi.relocateExceptionRuns(listOf(swapped), "/frozen/output", "/downloaded/output", jdks)
        }.contains("exception process command"))

        val adverse = json(
            "operation" to str("write"),
            "runtime" to str("jdk8"),
            "provider" to str("jvm"),
            "writer_runtime" to str("jdk8"),
            "writer_provider" to str("jvm"),
            "case" to str("ArgumentNullException"),
            "command" to JsonArray(
                command.map { str(it.textOrNull()!!.replace("/exception-serialization/fixture/", "/exception-serialization/uid-adverse/")) },
            ),
        )
        val adverseMapped = FullCi.relocateExceptionRuns(
            listOf(adverse), "/frozen/output", "/downloaded/output", jdks, "uid-adverse",
        )
        assertEquals(
            "/downloaded/output/exception-serialization/uid-adverse/jdk8-jvm-ArgumentNullException.ser",
            adverseMapped[0]["command"].arrayOrNull()!![5].textOrNull(),
        )
    }

    test("parameter groups keep types indices and complete methods") {
        val directory = temp()
        try {
            val path = directory.resolve("corpus.xml")
            fun document(rows: List<Pair<String, String>>): String = buildString {
                append("""<testsuite tests="2385" failures="0" errors="0" skipped="0">""")
                for ((owner, name) in rows) {
                    append("""<testcase classname="$owner" name="$name"/>""")
                }
                append("</testsuite>")
            }
            val rows = mutableListOf<Pair<String, String>>()
            for ((owner, suite) in FullCi.PARAMETER_SUITES) {
                val (count, types) = suite
                for ((index, type) in types.withIndex()) {
                    for (method in 0 until count) {
                        rows.add(
                            owner to
                                "method$method[org.dyn4j.collision.broadphase.$type@${(index + 1).toString(16)}]",
                        )
                    }
                }
            }
            for (index in 0 until 2115) rows.add("Other" to "case$index")
            write(path, document(rows))
            val original = FullCi.validateXml(fullCiFiles, path.toString())
            val expected = FullCi.normalizedCases(original)
            assertEquals(2385, expected.size)
            assertEquals(Vectors.fullCi.str("parameter_digest"), digestOfIdentities(expected))

            val first = rows[0]
            rows[0] = first.first to first.second.replace("@1]", "@deadbeef]")
            write(path, document(rows))
            assertTrue(failureMessage {
                FullCi.validateXml(fullCiFiles, path.toString())
            }.contains("parameter group"))

            rows[0] = first
            for (index in 0 until 25) {
                rows[index] = rows[index].first to rows[index].second.replace("@1]", "@abcdef]")
            }
            write(path, document(rows))
            assertEquals(expected, FullCi.normalizedCases(FullCi.validateXml(fullCiFiles, path.toString())))

            rows[0] = rows[0].first to rows[0].second.replace(".Sap@", ".Invented@")
            write(path, document(rows))
            assertTrue(failureMessage {
                FullCi.validateXml(fullCiFiles, path.toString())
            }.contains("parameter group"))
        } finally {
            deleteTree(directory)
        }
    }

    test("lane seal rejects missing changed and extra files") {
        val output = temp()
        try {
            val corpus = linkedMapOf<String, JsonElement>()
            for (provider in listOf("baseline", "candidate", "android")) {
                for (compiler in listOf(8, 21)) {
                    for (runtime in listOf(8, 21)) {
                        val lane = "$provider-javac$compiler-java$runtime"
                        val xml = output.resolve("corpus-$lane.xml")
                        val report = output.resolve("corpus-$lane.json")
                        write(xml, """<testsuite name="$lane"/>""")
                        write(report, """{"lane":"$lane"}""")
                        corpus[lane] = json(
                            "status" to str("PASSED"),
                            "cases" to num(2385),
                            "xml" to str("corpus-$lane.xml"),
                            "report" to str("corpus-$lane.json"),
                            "xml_sha256" to str(FileDigest.sha256(xml.toString())),
                            "report_sha256" to str(FileDigest.sha256(report.toString())),
                        )
                    }
                }
            }
            val candidate = "a".repeat(40)
            val evidence = json(
                "status" to str("PASSED"),
                "candidate_sha" to str(candidate),
                "corpus" to JsonObject(corpus),
            )
            assertEquals(24, FullCi.sealLanes(fullCiFiles, output.toString(), evidence, candidate).size)

            val victim = output.resolve("corpus-candidate-javac21-java21.xml")
            val originalBytes = Files.readAllBytes(victim)
            Files.delete(victim)
            assertTrue(failureMessage {
                FullCi.sealLanes(fullCiFiles, output.toString(), evidence, candidate)
            }.isNotEmpty())
            writeBytes(victim, originalBytes + "changed".toByteArray())
            assertTrue(failureMessage {
                FullCi.sealLanes(fullCiFiles, output.toString(), evidence, candidate)
            }.isNotEmpty())
            writeBytes(victim, originalBytes)
            val extra = output.resolve("corpus-invented.json")
            write(extra, "{}")
            assertTrue(failureMessage {
                FullCi.sealLanes(fullCiFiles, output.toString(), evidence, candidate)
            }.contains("file set"))
            Files.delete(extra)

            val broken = json(
                "status" to str("PASSED"),
                "candidate_sha" to str(candidate),
                "corpus" to JsonObject(corpus + ("candidate-javac21-java21" to kotlinx.serialization.json.JsonNull)),
            )
            write(output.resolve("result.json"), broken.toString())
            val (manifest, code) = FullCiHost.sealManifest(
                fullCiFiles,
                output.toString(),
                candidate,
                output.toString(),
                repositoryRoot().toString(),
                sealLanes = { FullCi.sealLanes(fullCiFiles, output.toString(), it, candidate) },
                sealException = { throw NoSuchElementException("exception_serialization") },
                sealWorld = { throw NoSuchElementException("world_fixtures") },
                verifyInputs = {},
                verifyWorld = {},
                verifyCorpus = {},
            )
            assertEquals(1, code)
            assertEquals("FAILED", manifest.textOrNull("status"))
            assertEquals(24, manifest.objectOrNull("files")!!.size)
        } finally {
            deleteTree(output)
        }
    }

    test("upload seal requires world fixture evidence") {
        val output = temp()
        try {
            val candidate = "a".repeat(40)
            write(
                output.resolve("result.json"),
                json(
                    "status" to str("PASSED"),
                    "candidate_sha" to str(candidate),
                    "archives" to json(
                        "staged_jvm_jar" to str("b".repeat(64)),
                        "staged_android_classes_jar" to str("c".repeat(64)),
                    ),
                    "exception_serialization" to json("report_sha256" to str("d".repeat(64))),
                ).toString(),
            )
            val (manifest, code) = FullCiHost.sealManifest(
                fullCiFiles,
                output.toString(),
                candidate,
                output.toString(),
                repositoryRoot().toString(),
                sealLanes = { emptyMap() },
                sealException = { emptyMap() },
                sealWorld = { throw NoSuchElementException("world_fixtures") },
                verifyInputs = {},
                verifyWorld = {},
                verifyCorpus = {},
            )
            assertEquals(1, code)
            assertEquals("FAILED", manifest.textOrNull("status"))
            assertEquals(0, manifest.objectOrNull("world_files")!!.size)
        } finally {
            deleteTree(output)
        }
    }

    test("exception report rejects missing identity path and payload") {
        val output = temp()
        try {
            val providers = linkedMapOf<String, JsonElement>(
                "baseline" to json("sha256" to str("a".repeat(64))),
                "jvm" to json("sha256" to str("b".repeat(64))),
                "android" to json("sha256" to str("c".repeat(64))),
            )
            val identities = mutableListOf<JsonElement>()
            for (provider in providers.keys) {
                for ((name, uid) in ExceptionCi.UIDS) {
                    identities.add(
                        json(
                            "provider" to str(provider),
                            "type" to str("org.dyn4j.exception.$name"),
                            "expected" to num(uid),
                            "matches" to JsonPrimitive(true),
                            "exit" to num(0),
                            "stdout" to str(
                                "  private static final long serialVersionUID = ${uid}l;\n",
                            ),
                        ),
                    )
                }
            }
            val expectedIds = buildString {
                for ((name, uid) in ExceptionCi.UIDS) append("$name=$uid\n")
            }
            val runs = mutableListOf<JsonElement>()
            for (runtime in ExceptionCi.RUNTIMES) {
                for (provider in providers.keys) {
                    runs.add(
                        json(
                            "operation" to str("ids"),
                            "runtime" to str(runtime),
                            "provider" to str(provider),
                            "case" to kotlinx.serialization.json.JsonNull,
                            "matches" to JsonPrimitive(true),
                            "exit" to num(0),
                            "stdout" to str(expectedIds),
                        ),
                    )
                }
            }
            for (writerRuntime in ExceptionCi.RUNTIMES) {
                for (case in ExceptionCi.CASES) {
                    val expected = "TYPE=org.dyn4j.exception.${case.substringBefore("-")}\n" +
                        "MESSAGE=sample\nCAUSE=java.lang.IllegalStateException:cause\n" +
                        "SUPPRESSED=java.lang.IllegalArgumentException:suppressed\n" +
                        "STACK=Example:run:Example.java:12\n"
                    for (writerProvider in providers.keys) {
                        val stream = output.resolve("$writerRuntime-$writerProvider-$case.ser")
                        writeBytes(stream, "stream".toByteArray())
                        runs.add(
                            json(
                                "operation" to str("write"),
                                "runtime" to str(writerRuntime),
                                "provider" to str(writerProvider),
                                "writer_runtime" to str(writerRuntime),
                                "writer_provider" to str(writerProvider),
                                "case" to str(case),
                                "command" to JsonArray(
                                    listOf(str("java"), str("write"), str(stream.toString()), str(case)),
                                ),
                                "stream_sha256" to str(FileDigest.sha256(stream.toString())),
                                "matches" to JsonPrimitive(true),
                                "exit" to num(0),
                                "stdout" to str(expected),
                            ),
                        )
                        for (readerRuntime in ExceptionCi.RUNTIMES) {
                            for (readerProvider in providers.keys) {
                                runs.add(
                                    json(
                                        "operation" to str("read"),
                                        "runtime" to str(readerRuntime),
                                        "provider" to str(readerProvider),
                                        "writer_runtime" to str(writerRuntime),
                                        "writer_provider" to str(writerProvider),
                                        "case" to str(case),
                                        "matches" to JsonPrimitive(true),
                                        "exit" to num(0),
                                        "stdout" to str(expected),
                                    ),
                                )
                            }
                        }
                    }
                }
            }
            assertEquals(636, runs.size)
            val report = json(
                "passed" to JsonPrimitive(true),
                "failure_count" to num(0),
                "providers" to JsonObject(providers),
                "baseline_sha256" to str("a".repeat(64)),
                "probe_sha256" to str("d".repeat(64)),
                "driver_sha256" to str("e".repeat(64)),
                "stdlib_sha256" to str("f".repeat(64)),
                "cases" to JsonArray(ExceptionCi.CASES.map(::str)),
                "identities" to JsonArray(identities),
                "runs" to JsonArray(runs),
                "compiles" to JsonObject(providers.keys.associateWith { json("exit" to num(0)) }),
                "versions" to JsonObject(
                    ExceptionCi.RUNTIMES.associateWith { json("exit" to num(0)) },
                ),
            )
            val expected = mapOf(
                "baseline" to "a".repeat(64),
                "jvm" to "b".repeat(64),
                "android" to "c".repeat(64),
            )
            ExceptionCi.validateExceptionReport(
                fullCiFiles, report, output.toString(), expected,
                "d".repeat(64), "e".repeat(64), "f".repeat(64),
            )
            val mutations = listOf(
                report.asObjectWith("identities" to JsonArray(identities.dropLast(1))),
                report.asObjectWith("runs" to JsonArray(runs.dropLast(1))),
                report.asObjectWith(
                    "cases" to JsonArray(ExceptionCi.CASES.dropLast(1).map(::str)),
                ),
                report.asObjectWith(
                    "runs" to JsonArray(
                        runs.dropLast(1) + listOf(
                            JsonObject(
                                runs.last().objectOrNull()!!.toMutableMap()
                                    .apply { put("stdout", str("CAUSE=cauze")) },
                            ),
                        ),
                    ),
                ),
            )
            for (mutation in mutations) {
                assertTrue(failureMessage {
                    ExceptionCi.validateExceptionReport(
                        fullCiFiles, mutation, output.toString(), expected,
                        "d".repeat(64), "e".repeat(64), "f".repeat(64),
                    )
                }.isNotEmpty())
            }
        } finally {
            deleteTree(output)
        }
    }

    test("unrelated object addresses remain distinct") {
        val observed = setOf(
            "org.dyn4j.Test" to "check[org.dyn4j.Tree@1a2b]",
            "org.dyn4j.Test" to "check[org.dyn4j.Tree@c3d4]",
        )
        val expected = FullCi.normalizedCases(observed.toList())
        assertEquals(2, expected.size)
        assertTrue(
            expected != FullCi.normalizedCases(
                listOf(
                    "org.dyn4j.Test" to "check[org.dyn4j.Tree@9a0b]",
                    "org.dyn4j.Test" to "check[org.dyn4j.Tree@8c7d]",
                ),
            ),
        )
        assertTrue(
            expected != FullCi.normalizedCases(listOf("org.dyn4j.Test" to "check[org.dyn4j.Tree@9a0b]")),
        )
    }

    test("changed pinned test source is rejected") {
        val source = temp()
        try {
            val path = source.resolve("src/test/java/Example.java")
            write(path, "class Example {}")
            val expected = mapOf(
                "src/test/java/Example.java" to FileDigest.sha256(path.toString()),
            )
            FullCi.validateSourceInputs(fullCiFiles, source.toString(), expected, expectedCount = 1)
            write(path, "class Example { int changed; }")
            assertTrue(failureMessage {
                FullCi.validateSourceInputs(fullCiFiles, source.toString(), expected, expectedCount = 1)
            }.contains("pinned test source or resource changed"))
        } finally {
            deleteTree(source)
        }
    }

    test("xml requires every executed case") {
        val directory = temp()
        try {
            val path = directory.resolve("corpus.xml")
            write(
                path,
                """<testsuite tests="2" failures="0" errors="0" skipped="0">""" +
                    """<testcase classname="A" name="first"/>""" +
                    """<testcase classname="A" name="second"/></testsuite>""",
            )
            assertEquals(2, FullCi.validateXml(fullCiFiles, path.toString(), 2).size)
            assertTrue(failureMessage {
                FullCi.validateXml(fullCiFiles, path.toString(), 3)
            }.contains("count or status"))
            write(
                path,
                """<testsuite tests="2" failures="0" errors="0" skipped="1">""" +
                    """<testcase classname="A" name="first"/>""" +
                    """<testcase classname="A" name="second"><skipped/></testcase></testsuite>""",
            )
            assertTrue(failureMessage {
                FullCi.validateXml(fullCiFiles, path.toString(), 2)
            }.isNotEmpty())
            write(
                path,
                """<testsuite tests="2" failures="0" errors="0" skipped="0">""" +
                    """<testcase classname="A" name="first"/>""" +
                    """<testcase classname="A" name="first"/></testsuite>""",
            )
            assertTrue(failureMessage {
                FullCi.validateXml(fullCiFiles, path.toString(), 2)
            }.contains("duplicate"))
        } finally {
            deleteTree(directory)
        }
    }

    test("empty or skipped corpus is rejected") {
        val report = json(
            "actual_executed_cases" to num(2385),
            "failures" to num(0),
            "ignored" to num(0),
            "process_exit_code" to num(0),
            "output" to str("ACTUAL_TESTS=2385\nFAILURES=0\nIGNORED=0\n"),
        )
        FullCi.validateCorpus(report)
        for (change in listOf(
            json(
                "actual_executed_cases" to num(0),
                "output" to str("ACTUAL_TESTS=0\nFAILURES=0\nIGNORED=0\n"),
            ),
            json("ignored" to num(1), "output" to str("ACTUAL_TESTS=2385\nFAILURES=0\nIGNORED=1\n")),
        )) {
            assertTrue(failureMessage {
                FullCi.validateCorpus(report.asObjectWith(*change.toList().toTypedArray()))
            }.isNotEmpty())
        }
    }

    test("incomplete or risky archive audit is rejected") {
        val report = json(
            "compared_api_types" to JsonArray((0 until 216).map { str("org.dyn4j.Type$it") }),
            "compared_baseline_declarations" to num(3078),
            "missing_types" to JsonArray(emptyList()),
            "signature_mismatches" to JsonArray(emptyList()),
            "added_member_risks" to JsonArray(emptyList()),
            "inventory_errors" to JsonArray(emptyList()),
            "fixture_failures" to JsonArray(emptyList()),
            "fixture_errors" to JsonArray(emptyList()),
            "fixture_results" to JsonArray(
                FullCi.FIXTURE_SHA.sortedBy { it }.map {
                    json(
                        "source_sha256" to str(it),
                        "baseline_exit_code" to num(0),
                        "candidate_exit_code" to num(0),
                    )
                },
            ),
            "baseline_sha256" to str(FullCi.BASELINE_SHA),
            "candidate_sha256" to str("a".repeat(64)),
        )
        FullCi.validateAudit(report, "a".repeat(64))
        val apiTypes = report.arrayOrNull("compared_api_types")!!
        val fixtureRows = report.arrayOrNull("fixture_results")!!
        for (change in listOf(
            json("compared_api_types" to JsonArray(apiTypes.dropLast(1))),
            json("compared_baseline_declarations" to num(3077)),
            json(
                "added_member_risks" to JsonArray(
                    listOf(json("declaration" to str("public int getEntries();"))),
                ),
            ),
            json("fixture_results" to JsonArray(emptyList())),
            json(
                "fixture_results" to JsonArray(
                    listOf(
                        fixtureRows.first().objectOrNull()!!.asObjectWith("candidate_exit_code" to num(1)),
                    ) + fixtureRows.drop(1),
                ),
            ),
        )) {
            assertTrue(failureMessage {
                FullCi.validateAudit(report.asObjectWith(*change.toList().toTypedArray()), "a".repeat(64))
            }.isNotEmpty())
        }
    }

    test("corpus argfile and process command reject resealed changes") {
        val root = temp()
        try {
            val source = root.resolve("baseline-cache/dyn4j-source")
            val relative = "src/test/java/org/dyn4j/ExampleTest.java"
            val java = source.resolve(relative)
            write(java, "package org.dyn4j; @Test class ExampleTest {}\n")
            val hashes = mapOf(relative to FileDigest.sha256(java.toString()))
            val original = "/original/archive"
            write(
                root.resolve("test-sources.args"),
                "\"$original/baseline-cache/dyn4j-source/$relative\"\n",
            )
            val classes = FullCi.validateCorpusArgfile(
                fullCiFiles, root.toString(), original, hashes, expectedCount = 1, expectedClasses = 1,
            )
            assertEquals(listOf("org.dyn4j.ExampleTest"), classes)
            write(root.resolve("test-sources.args"), "\"/tmp/stale/Unrelated.java\"\n")
            assertTrue(failureMessage {
                FullCi.validateCorpusArgfile(
                    fullCiFiles, root.toString(), original, hashes, expectedCount = 1, expectedClasses = 1,
                )
            }.contains("test source argfile"))

            val command = listOf("/jdk8/bin/javac", "-cp", "/original/archive/baseline.jar", "@$original/test-sources.args")
            val raw = root.resolve("process.json")
            val log = root.resolve("process.log")
            write(log, "")
            write(
                raw,
                """{"command":["/jdk8/bin/javac","-cp","/original/archive/baseline.jar","@$original/test-sources.args"],""" +
                    """"cwd":"/source/root","exit":0,"stdout":"","stderr":""}""" + "\n",
            )
            val row = json("process_sha256" to str(FileDigest.sha256(raw.toString())))
            FullCi.validateCorpusProcess(
                fullCiFiles, root.toString(), "process.json", log.toString(), row, command, "/source/root",
            )
            write(
                raw,
                """{"command":["/jdk8/bin/javac","-cp","/tmp/stale.jar","@$original/test-sources.args"],""" +
                    """"cwd":"/source/root","exit":0,"stdout":"","stderr":""}""" + "\n",
            )
            val changedRow = json("process_sha256" to str(FileDigest.sha256(raw.toString())))
            assertTrue(failureMessage {
                FullCi.validateCorpusProcess(
                    fullCiFiles, root.toString(), "process.json", log.toString(), changedRow, command,
                    "/source/root",
                )
            }.contains("command"))
        } finally {
            deleteTree(root)
        }
    }
}

private fun JsonObject.asObjectWith(vararg pairs: Pair<String, JsonElement>): JsonObject =
    JsonObject(toMutableMap().apply { putAll(pairs) })

private fun digestOfIdentities(values: Map<Pair<String, String>, Int>): String {
    val sorted = values.entries.sortedWith(
        Comparator { left, right ->
            val byOwner = CanonicalJson.compareCodePoints(left.key.first, right.key.first)
            if (byOwner != 0) byOwner else CanonicalJson.compareCodePoints(left.key.second, right.key.second)
        },
    )
    return Sha256.of(
        CanonicalJson.render(
            JsonArray(
                sorted.map {
                    JsonArray(listOf(str(it.key.first), str(it.key.second), num(it.value.toLong())))
                },
            ),
        ),
    )
}

internal fun deleteTree(root: Path) {
    if (!Files.exists(root)) return
    Files.walk(root).use { stream ->
        stream.sorted(Comparator.reverseOrder()).forEach { Files.deleteIfExists(it) }
    }
}
