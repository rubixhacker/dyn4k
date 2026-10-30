package io.github.rubixhacker.harness.qualification

import de.infix.testBalloon.framework.core.testSuite
import io.github.rubixhacker.harness.contract.StrictJson
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.attribute.FileTime
import java.util.concurrent.TimeUnit
import kotlin.io.path.writeText
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

/**
 * `artifact.py`, first slice: inventory paths, evidence copies, probe checks, and group
 * collection. The reference messages are compared verbatim.
 */
val ArtifactBundleContract by testSuite {
    test("bundle inventory paths are normalised and rejected when unsafe") {
        assertEquals("xml/report.xml", ArtifactBundle.portablePath("xml\\report.xml"))
        assertEquals("a/b", ArtifactBundle.portablePath("a/b"))
        for ((value, message) in listOf(
            "" to "bundle inventory path is missing",
            "../escape" to "bundle inventory path is unsafe: ../escape",
            "a//b" to "bundle inventory path is unsafe: a//b",
            "c:x" to "bundle inventory path is unsafe: c:x",
            "./a" to "bundle inventory path is unsafe: ./a",
        )) {
            assertEquals(
                message,
                assertFailsWith<IllegalArgumentException> { ArtifactBundle.portablePath(value) }.message,
            )
        }
    }

    test("an evidence JSON object is copied and returned") {
        val directory = Files.createTempDirectory("artifact-json")
        try {
            val source = directory.resolve("probe.json")
            source.writeText("""{"status":"PROBE_PASSED"}""")
            val destination = directory.resolve("bundle")
            Files.createDirectories(destination)
            val data = ArtifactBundle.copyJson(source, destination)
            assertEquals("PROBE_PASSED", Py.str(data["status"]))
            assertEquals(true, Files.isRegularFile(destination.resolve("json/probe.json")))
        } finally {
            deleteRecursively(directory)
        }
    }

    test("a missing or non-object evidence file is rejected") {
        val directory = Files.createTempDirectory("artifact-json-bad")
        try {
            val destination = directory.resolve("bundle")
            Files.createDirectories(destination)
            assertEquals(
                "missing evidence JSON: absent.json",
                assertFailsWith<IllegalArgumentException> {
                    ArtifactBundle.copyJson(directory.resolve("absent.json"), destination)
                }.message,
            )
            val list = directory.resolve("list.json")
            list.writeText("[1, 2]")
            assertEquals(
                "evidence JSON is not an object: list.json",
                assertFailsWith<IllegalArgumentException> {
                    ArtifactBundle.copyJson(list, destination)
                }.message,
            )
        } finally {
            deleteRecursively(directory)
        }
    }

    test("a report group is collected only when it reports every selected case") {
        withReport { repository, destination, manifest, group, started, finished ->
            val files = mutableListOf<JsonObject>()
            val result = ArtifactBundle.collectGroup(
                repository, destination, manifest, group, started, finished, files,
            )
            assertEquals(2L, Py.int(result["selected"]))
            assertEquals(2L, Py.int(result["reported"]))
            assertEquals(1, files.size)
            assertEquals("xml/one.xml", Py.str(files.first()["path"]))
            assertEquals(true, Files.isRegularFile(destination.resolve("xml/one.xml")))
        }
    }

    test("a group that misses a selected case is rejected") {
        withReport(report = suite(listOf("other"))) { repository, destination, manifest, group, started, finished ->
            assertEquals(
                "missing selected cases in one",
                assertFailsWith<IllegalArgumentException> {
                    ArtifactBundle.collectGroup(
                        repository, destination, manifest, group, started, finished,
                        mutableListOf(),
                    )
                }.message,
            )
        }
    }

    test("a group that duplicates a selected case is rejected") {
        withReport(report = suite(listOf("a", "a"))) { repository, destination, manifest, group, started, finished ->
            assertEquals(
                "duplicate cases in one",
                assertFailsWith<IllegalArgumentException> {
                    ArtifactBundle.collectGroup(
                        repository, destination, manifest, group, started, finished,
                        mutableListOf(),
                    )
                }.message,
            )
        }
    }

    test("a stale report is rejected") {
        withReport { repository, destination, manifest, group, started, finished ->
            assertEquals(
                "stale report ${repository.resolve("one.xml")}: outside bound execution",
                assertFailsWith<IllegalArgumentException> {
                    ArtifactBundle.collectGroup(
                        repository, destination, manifest, group,
                        finished!! + 1_000_000_000L, finished, mutableListOf(),
                    )
                }.message,
            )
        }
    }

    test("a probe must account for the frozen executed suite") {
        val manifest = probeManifest()
        val group = (manifest["groups"] as JsonArray)[0] as JsonObject
        val groups = mapOf("one" to group)
        val probe = probeReport(manifest, groups, listOf("one"))
        val (started, finished) = ArtifactBundle.checkProbe(
            probe, manifest, groups, listOf("one"), "a".repeat(40),
        )
        assertEquals(1L, started)
        assertEquals(2L, finished)
        assertEquals(
            "probe for one differs from frozen executed suite",
            assertFailsWith<IllegalArgumentException> {
                ArtifactBundle.checkProbe(
                    JsonObject(probe + ("expected" to JsonPrimitive(3))),
                    manifest, groups, listOf("one"), "a".repeat(40),
                )
            }.message,
        )
        assertEquals(
            "probe for one lacks execution time",
            assertFailsWith<IllegalArgumentException> {
                ArtifactBundle.checkProbe(
                    buildJsonObject {
                        for ((key, value) in probe) {
                            if (key != "finished_at_ns") put(key, value)
                        }
                        put("finished_at_ns", JsonPrimitive(0))
                    },
                    manifest, groups, listOf("one"), "a".repeat(40),
                )
            }.message,
        )
    }
}

private fun suite(names: List<String>): String {
    val cases = names.joinToString("") { name ->
        "<testcase classname=\"dyn4k.FoundationTest\" name=\"$name\" time=\"0.01\"/>"
    }
    return "<testsuite tests=\"${names.size}\" failures=\"0\" errors=\"0\" skipped=\"0\" " +
        "time=\"0.5\">$cases</testsuite>"
}

private fun withReport(
    report: String = suite(listOf("a", "b")),
    block: (Path, Path, JsonObject, JsonObject, Long?, Long?) -> Unit,
) {
    val root = Files.createTempDirectory("artifact-group")
    try {
        val repository = root.resolve("repository")
        val destination = root.resolve("bundle")
        Files.createDirectories(repository)
        Files.createDirectories(destination)
        repository.resolve("one.xml").writeText(report)
        Files.setLastModifiedTime(
            repository.resolve("one.xml"), FileTime.from(1_700_000_000L, TimeUnit.SECONDS),
        )
        val manifest = probeManifest()
        val group = (manifest["groups"] as JsonArray)[0] as JsonObject
        block(
            repository, destination, manifest, group,
            1_699_999_000_000_000_000L, 1_700_000_100_000_000_000L,
        )
    } finally {
        deleteRecursively(root)
    }
}

private fun probeManifest(): JsonObject = StrictJson.load(
    """
    {"kind": "foundation-probe", "id": "fixture", "groups": [
      {"id": "one", "report_pattern": "one.xml",
       "cases": [{"classname": "dyn4k.FoundationTest", "name": "a"},
                 {"classname": "dyn4k.FoundationTest", "name": "b"}]}
    ]}
    """.trimIndent(),
) as JsonObject

private fun probeReport(
    manifest: JsonObject,
    groups: Map<String, JsonObject>,
    ids: List<String>,
): JsonObject {
    val selected = buildJsonObject {
        for ((key, value) in manifest) {
            if (key != "groups") put(key, value)
        }
        put("groups", JsonArray(ids.map { groups.getValue(it) }))
    }
    return buildJsonObject {
        put("candidate_sha", JsonPrimitive("a".repeat(40)))
        put("status", JsonPrimitive("PROBE_PASSED"))
        put("manifest_sha256", JsonPrimitive(FullCorpus.canonicalDigest(selected)))
        put("expected", JsonPrimitive(2))
        put("executed", JsonPrimitive(2))
        put("reported", JsonPrimitive(2))
        put("failures", JsonPrimitive(0))
        put("errors", JsonPrimitive(0))
        put("skipped", JsonPrimitive(0))
        put("exit_code", JsonPrimitive(0))
        put("started_at_ns", JsonPrimitive(1))
        put("finished_at_ns", JsonPrimitive(2))
        put(
            "groups",
            JsonArray(
                listOf(
                    buildJsonObject {
                        put("id", JsonPrimitive("one"))
                        put("expected", JsonPrimitive(2))
                        put("executed", JsonPrimitive(2))
                        put("reported", JsonPrimitive(2))
                        put("failures", JsonPrimitive(0))
                        put("errors", JsonPrimitive(0))
                        put("skipped", JsonPrimitive(0))
                    },
                ),
            ),
        )
    }
}
