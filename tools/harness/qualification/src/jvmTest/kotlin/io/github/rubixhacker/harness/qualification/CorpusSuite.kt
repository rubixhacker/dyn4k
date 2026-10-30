package io.github.rubixhacker.harness.qualification

import de.infix.testBalloon.framework.core.testSuite
import java.nio.file.Files
import java.nio.file.Path
import kotlin.io.path.writeText
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/**
 * `full_corpus.py` against reference vectors: source masking, corpus scanning, manifest
 * decoration, reviewed pairs, archive names, and the Node command selection.
 */
val FullCorpusContract by testSuite {
    val vector = TestVectors.root.objectAt("full_corpus")

    test("mask_noncode blanks comments and literals and keeps newlines") {
        for (entry in vector.getValue("mask") as JsonArray) {
            val source = TestVectors.str((entry as JsonObject)["source"])
            assertEquals(
                TestVectors.str(entry["result"]),
                FullCorpus.maskNoncode(source),
                source,
            )
        }
    }

    test("mask_noncode rejects an unterminated comment or string") {
        for ((source, message) in listOf(
            "class A { /* open" to "unterminated block comment",
            "val s = \"open" to "unterminated string",
            "val r = \"\"\"open" to "unterminated raw string",
        )) {
            val error = assertFailsWith<IllegalArgumentException> { FullCorpus.maskNoncode(source) }
            assertEquals(message, error.message)
        }
    }

    test("scan_sources discovers exactly the reference cases") {
        withCorpusFixture(vector) { root ->
            val cases = CorpusFiles.scanSources(root)
            val expected = vector.getValue("cases") as JsonArray
            assertEquals(expected.size, cases.size, "case count")
            for ((index, element) in expected.withIndex()) {
                val want = element as JsonObject
                val got = cases[index]
                assertEquals(TestVectors.str(want["module"]), got.module, "module $index")
                assertEquals(TestVectors.str(want["source_set"]), got.sourceSet, "source set $index")
                assertEquals(TestVectors.str(want["classname"]), got.classname, "classname $index")
                assertEquals(TestVectors.str(want["method"]), got.method, "method $index")
                assertEquals(TestVectors.str(want["path"]), got.path, "path $index")
                assertEquals(TestVectors.long(want["line"]), got.line, "line $index")
                assertEquals(TestVectors.strings(want["hosts"]), got.hosts, "hosts $index")
            }
        }
    }

    test("scan_test_tree and source_tree_digest match the reference") {
        withCorpusFixture(vector) { root ->
            val tree = CorpusFiles.scanTestTree(root)
            val expected = vector.getValue("tree") as JsonArray
            assertEquals(expected.size, tree.size)
            for ((index, element) in expected.withIndex()) {
                val want = element as JsonObject
                assertEquals(TestVectors.str(want["path"]), Py.str(tree[index]["path"]), "path $index")
                assertEquals(TestVectors.str(want["sha256"]), Py.str(tree[index]["sha256"]), "sha $index")
            }
            assertEquals(vector.primitive("source_tree_sha256"), FullCorpus.sourceTreeDigest(tree))
        }
    }

    test("make_manifest decorates the scanned cases exactly as the reference") {
        withCorpusFixture(vector) { root ->
            val cases = CorpusFiles.scanSources(root)
            val mappings = (vector["mappings"] as JsonArray).map { it as JsonObject }
            val manifest = FullCorpus.makeManifest(
                cases, mappings, production = false, sourceFiles = CorpusFiles.scanTestTree(root),
            )
            assertEquals(vector.objectAt("manifest"), manifest)
        }
    }

    test("expected_cases selects the reviewed class and method per group") {
        val manifest = vector.objectAt("manifest")
        for (group in FullCorpus.GROUPS) {
            val expected = vector.objectAt("expected_groups").getValue(group.id) as JsonArray
            val want = expected.map { pair ->
                val entry = pair as JsonArray
                TestVectors.str(entry[0]) to TestVectors.str(entry[1])
            }.toSet()
            assertEquals(want, FullCorpus.expectedCases(manifest, group), group.id)
        }
    }

    test("paired rows and bytes match the reference TSV") {
        for (entry in vector.getValue("paired") as JsonArray) {
            val mapping = ((entry as JsonObject)["mapping"] as JsonArray).map { it as JsonObject }
            val rows = (entry["rows"] as JsonArray).map { it as JsonObject }
            assertEquals(rows, FullCorpus.pairedRows(mapping))
            assertEquals(TestVectors.str(entry["text"]), FullCorpus.pairedBytes(mapping).toString(Charsets.UTF_8))
        }
    }

    test("archive paths are rejected when they could escape") {
        for (entry in vector.getValue("archive_relative") as JsonArray) {
            val record = entry as JsonObject
            val name = TestVectors.str(record["name"])
            val marker = TestVectors.str(record["result"])
            if (marker == "ok") {
                assertEquals(name, FullCorpus.archiveRelative(name))
            } else {
                val error = assertFailsWith<IllegalArgumentException> {
                    FullCorpus.archiveRelative(name)
                }
                assertEquals(marker, error.message)
            }
        }
    }

    test("generated build output is the only untracked input allowed") {
        for (entry in vector.getValue("allowed_generated_path") as JsonArray) {
            val record = entry as JsonObject
            assertEquals(
                TestVectors.str(record["result"]) == "true",
                FullCorpus.allowedGeneratedPath(TestVectors.str(record["path"])),
                TestVectors.str(record["path"]),
            )
        }
    }

    test("every reviewed JVM-only reason matches and an unreviewed one fails") {
        for (entry in vector.getValue("jvm_only_reason") as JsonArray) {
            val record = entry as JsonObject
            assertEquals(
                TestVectors.str(record["result"]),
                FullCorpus.jvmOnlyReason(TestVectors.str(record["original"])),
                TestVectors.str(record["original"]),
            )
        }
        val error = assertFailsWith<IllegalArgumentException> {
            FullCorpus.jvmOnlyReason(vector.primitive("jvm_only_unknown"))
        }
        assertEquals(
            "unreviewed JVM-only disposition: ${vector.primitive("jvm_only_unknown")}",
            error.message,
        )
    }

    test("Node command selection matches the reference") {
        val node = vector.objectAt("node")
        for (entry in node.getValue("process_argv") as JsonArray) {
            val record = entry as JsonObject
            assertEquals(
                TestVectors.strings(record["result"]),
                FullCorpus.nodeProcessArgv(
                    TestVectors.str(record["repository"]),
                    TestVectors.strings(record["argv"]),
                ),
            )
        }
        for (entry in node.getValue("launch_loader") as JsonArray) {
            val record = entry as JsonObject
            assertEquals(
                TestVectors.strOrNull(record["result"]),
                FullCorpus.nodeLaunchLoader(
                    TestVectors.str(record["repository"]),
                    TestVectors.strings(record["argv"]),
                ),
            )
        }
        for (entry in node.getValue("group_for_argv") as JsonArray) {
            val record = entry as JsonObject
            val selection = FullCorpus.nodeGroupForArgv(
                TestVectors.str(record["repository"]),
                TestVectors.strings(record["argv"]),
            )
            val expected = TestVectors.strings(record["result"])
            if (expected.isEmpty()) {
                assertEquals(null, selection)
            } else {
                assertEquals(expected[0], selection?.first)
                assertEquals(expected[1], selection?.second)
            }
        }
        for (entry in node.getValue("task") as JsonArray) {
            val record = entry as JsonObject
            assertEquals(
                TestVectors.str(record["result"]),
                FullCorpus.nodeTask(TestVectors.str(record["group"])),
            )
        }
        for (entry in node.getValue("capture_root") as JsonArray) {
            val record = entry as JsonObject
            val row = kotlinx.serialization.json.buildJsonObject {
                put("payload_path", record.getValue("payload"))
                put("argv", record.getValue("argv"))
            }
            assertEquals(TestVectors.str(record["result"]), FullCorpus.nodeCaptureRoot(row))
        }
    }
}

/** Writes the recorded corpus fixture files into a fresh repository shape. */
private fun withCorpusFixture(vector: JsonObject, block: (Path) -> Unit) {
    val root = Files.createTempDirectory("full-corpus")
    try {
        for ((name, content) in vector.objectAt("files")) {
            val path = root.resolve(name)
            path.parent?.let { Files.createDirectories(it) }
            path.writeText(TestVectors.str(content))
        }
        block(root)
    } finally {
        deleteRecursively(root)
    }
}
