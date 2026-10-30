package io.github.rubixhacker.harness.qualification

import io.github.rubixhacker.harness.contract.MatrixCase
import java.nio.file.Files
import java.nio.file.Path
import java.util.Comparator
import java.util.zip.ZipFile
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

/**
 * Recorded reference vectors.
 *
 * `qualification-vectors.json` and the fixtures beside it are produced by running
 * `tools/qualification/qualify.py` (Python 3.14.8) at the revision recorded in the file. The
 * Kotlin suites replay those inputs and assert the same verdicts.
 */
internal object TestVectors {
    val root: JsonObject = run {
        val stream = TestVectors::class.java.getResourceAsStream("/qualification-vectors.json")
            ?: error("qualification-vectors.json is missing from the test resources")
        Json.parseToJsonElement(stream.bufferedReader().use { it.readText() }).jsonObject
    }

    val revision: String get() = str(root.getValue("git_revision"))

    fun list(name: String): List<JsonObject> = root.getValue(name).jsonArray.map { it.jsonObject }

    fun nullable(element: JsonElement?): JsonElement? = when (element) {
        null, is JsonNull -> null
        else -> element
    }

    fun str(element: JsonElement?): String = (element as JsonPrimitive).content

    fun strOrNull(element: JsonElement?): String? = (nullable(element) as? JsonPrimitive)?.content

    fun long(element: JsonElement?): Long = (element as JsonPrimitive).content.toLong()

    fun strings(element: JsonElement?): List<String> =
        (element as JsonArray).map { (it as JsonPrimitive).content }

    fun matrixCase(value: JsonObject): MatrixCase = MatrixCase(
        target = str(value["target"]),
        runtime = str(value["runtime"]),
        minimum = str(value["minimum"]),
        kind = str(value["kind"]),
        version = str(value["version"]),
        configuration = str(value["configuration"]),
        id = str(value["id"]),
    )

    fun caseId(value: JsonObject): String = str(value["id"])
}

/** A staging fixture extracted from the recorded archive. */
internal class Fixture private constructor(val root: Path) : AutoCloseable {
    val staging: Path get() = root.resolve("build/staging-repository")

    val license: Path get() = root.resolve("LICENSE.md")

    override fun close() {
        deleteRecursively(root)
    }

    companion object {
        fun extract(name: String): Fixture {
            val stream = Fixture::class.java.getResourceAsStream("/publication/$name")
                ?: error("fixture $name is missing from the test resources")
            val root = Files.createTempDirectory("qualification-fixture")
            val archive = root.resolve("fixture.zip")
            Files.copy(stream, archive)
            ZipFile(archive.toFile()).use { zip ->
                for (entry in zip.entries()) {
                    val target = root.resolve(entry.name)
                    if (entry.isDirectory) {
                        Files.createDirectories(target)
                    } else {
                        target.parent?.let { Files.createDirectories(it) }
                        zip.getInputStream(entry).use { input -> Files.copy(input, target) }
                    }
                }
            }
            Files.delete(archive)
            return Fixture(root)
        }
    }
}

internal fun deleteRecursively(root: Path) {
    if (!Files.exists(root)) return
    Files.walk(root).use { stream ->
        stream.sorted(Comparator.reverseOrder()).forEach { Files.deleteIfExists(it) }
    }
}

internal fun JsonObject.array(key: String): JsonArray = getValue(key).jsonArray

internal fun JsonObject.objectAt(key: String): JsonObject = getValue(key).jsonObject

internal fun JsonObject.primitive(key: String): String = getValue(key).jsonPrimitive.content

/** The repository root that holds the tracked qualification manifests. */
internal fun repositoryRoot(): Path {
    var current: Path? = Path.of("").toAbsolutePath()
    while (current != null) {
        if (Files.isRegularFile(current.resolve("tools/qualification/full-suite-manifest.json"))) {
            return current
        }
        current = current.parent
    }
    error("repository root with tools/qualification/full-suite-manifest.json was not found")
}
