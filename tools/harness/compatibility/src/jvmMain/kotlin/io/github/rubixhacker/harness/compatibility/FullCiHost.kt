package io.github.rubixhacker.harness.compatibility

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.Path

/**
 * The sealing step of `full_ci.seal_main`, split from its CLI.
 *
 * The verification stages are injected so the Kotlin suite can reproduce the Python cases that
 * patch individual seals. `seal_lanes` is real; the exception and World seals, the archive-input
 * checks, and the corpus replays are supplied by the caller because they replay the evidence tree.
 */
object FullCiHost {
    fun sealManifest(
        files: CorpusFiles,
        output: String,
        candidateSha: String,
        archiveRoot: String,
        sourceRoot: String,
        sealLanes: (JsonObject) -> Map<String, String>,
        sealException: () -> Map<String, String>,
        sealWorld: () -> Map<String, String>,
        verifyInputs: () -> Unit,
        verifyWorld: () -> Unit,
        verifyCorpus: () -> Unit,
    ): Pair<JsonObject, Int> {
        val manifest = linkedMapOf<String, JsonElement>(
            "candidate_sha" to JsonPrimitive(candidateSha),
            "status" to JsonPrimitive("FAILED"),
            "files" to JsonObject(emptyMap()),
            "exception_files" to JsonObject(emptyMap()),
            "world_files" to JsonObject(emptyMap()),
            "archive_root" to JsonPrimitive(archiveRoot),
            "source_root" to JsonPrimitive(sourceRoot),
            "archive_files" to JsonObject(emptyMap()),
            "error" to JsonNull,
        )
        try {
            val evidence = UniqueJson.parse(files.readText(joinPath(output, "result.json")))
                .objectOrNull() ?: throw IllegalArgumentException("full compatibility result is invalid")
            manifest["files"] = toJson(sealLanes(evidence))
            manifest["exception_files"] = toJson(sealException())
            manifest["world_files"] = toJson(sealWorld())
            verifyInputs()
            verifyWorld()
            verifyCorpus()
            manifest["archive_files"] = toJson(FullCi.snapshotArchive(files, output))
            manifest["status"] = JsonPrimitive("PASSED")
        } catch (error: Exception) {
            manifest["error"] = JsonPrimitive(error.message ?: error.toString())
            val names = files.directFiles(output)
                .filter { it.startsWith("corpus-") && (it.endsWith(".xml") || it.endsWith(".json")) }
            manifest["files"] = toJson(
                names.associateWith { files.digest(joinPath(output, it)) }.toSortedMap(),
            )
            val world = joinPath(joinPath(output, "logs"), "world-fixtures")
            manifest["world_files"] = toJson(
                files.filesBelow(world).associateWith { files.digest(joinPath(world, it)) },
            )
        }
        val result = JsonObject(manifest)
        Files.createDirectories(Path.of(output))
        Files.writeString(
            Path.of(joinPath(output, "lane-manifest.json")),
            CanonicalJsonIndented.render(result) + "\n",
            StandardCharsets.UTF_8,
        )
        val status = result.textOrNull("status")
        return result to if (status == "PASSED") 0 else 1
    }

    private fun toJson(values: Map<String, String>): JsonObject =
        JsonObject(values.mapValues { JsonPrimitive(it.value) })

    /** `json.dumps(value, indent=2)` rendering, used for the manifest the Python tool writes. */
    private object CanonicalJsonIndented {
        fun render(value: JsonElement): String {
            val out = StringBuilder()
            write(value, out, 0)
            return out.toString()
        }

        private fun write(value: JsonElement, out: StringBuilder, depth: Int) {
            when (value) {
                is JsonNull -> out.append("null")
                is JsonPrimitive -> out.append(
                    if (value.isString) quote(value.content) else value.content,
                )
                is JsonArray -> {
                    if (value.isEmpty()) {
                        out.append("[]")
                        return
                    }
                    out.append('[')
                    value.forEachIndexed { index, item ->
                        if (index > 0) out.append(',')
                        out.append('\n').append("  ".repeat(depth + 1))
                        write(item, out, depth + 1)
                    }
                    out.append('\n').append("  ".repeat(depth)).append(']')
                }
                is JsonObject -> {
                    if (value.isEmpty()) {
                        out.append("{}")
                        return
                    }
                    out.append('{')
                    value.entries.forEachIndexed { index, (key, item) ->
                        if (index > 0) out.append(',')
                        out.append('\n').append("  ".repeat(depth + 1))
                        out.append(quote(key)).append(": ")
                        write(item, out, depth + 1)
                    }
                    out.append('\n').append("  ".repeat(depth)).append('}')
                }
            }
        }

        private fun quote(value: String): String {
            val out = StringBuilder("\"")
            for (char in value) {
                when (char) {
                    '"' -> out.append("\\\"")
                    '\\' -> out.append("\\\\")
                    '\n' -> out.append("\\n")
                    '\r' -> out.append("\\r")
                    '\t' -> out.append("\\t")
                    '\b' -> out.append("\\b")
                    '\u000C' -> out.append("\\f")
                    else -> if (char.code < 0x20 || char.code > 0x7E) {
                        out.append("\\u").append(char.code.toString(16).padStart(4, '0'))
                    } else {
                        out.append(char)
                    }
                }
            }
            return out.append('"').toString()
        }
    }
}
