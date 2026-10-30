package io.github.rubixhacker.harness.compatibility

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/**
 * The World Java compatibility fixtures, ported from `tools/compatibility/world_ci.py`.
 *
 * `execute`, `validate_report`, `seal_world`, `process`, and `main` stay unported: they compile and
 * run Java, copy archives, and read the Java standard library. The frozen inventory and the four
 * validators below are pure once the caller supplies [CorpusFiles].
 */
object WorldCi {
    const val FROZEN_COMMIT = "806db0b6ce40c6345054fc05a9ddb32da14cf153"
    const val BASELINE_SHA = "204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e"
    const val STDLIB_SHA = "2226de463d309d4a5500a481320b3dea515a6981dcae1def531fbc158884e25f"
    const val BAD_ARCHIVE_SHA = "b53ae4c5e85bc5f37866e9ead1d0558e0128c8dde9542789f51f62b9d5a6e57b"

    const val SOURCE_ROOT = "dyn4k-core/src/jvmConsumer/java"
    const val BAD_ARCHIVE = "tools/compatibility/fixtures/world/bad-body-view-bc71.jar"

    val PROVIDERS = listOf("baseline", "jvm", "android")
    val RUNTIMES = listOf("jdk8", "jdk21")

    /** The frozen source inventory. Iteration order is the order `expected_modes` reads. */
    val SOURCE_SHA: Map<String, String> = linkedMapOf(
        "WorldArrayListMutationAuditConsumer.java" to
            "1ce3047ec5675693ef3425883502abb1c82e62a830f032492f10ce1b11c3c1f6",
        "WorldExtraMethodsConsumer.java" to
            "121826bbe176e2a5ed98a77eebf94f4186103c769a538baa3034ef2f79515374",
        "WorldListSemanticsConsumer.java" to
            "431da69f017462e51de3c5d7638ebe0056bec7141a9ad8d8a24694f1356ffc69",
        "WorldProtectedListConsumer.java" to
            "96b8d49356b488fb76677d6e95a758ac60dfb0703350b4ca512b61b098fea107",
        "WorldResultHelperConsumer.java" to
            "5165f0d65ba2dc8003037f40340b3c493fb60aeaa99362454fd245523baddeff",
        "WorldViewIteratorConsumer.java" to
            "18f60d2e8a696e89f3b39a1b95c93dfc70dc230beea93a2a564a00b6daf2d1d4",
        "org/dyn4j/world/WorldAllListsProbe.java" to
            "769784fe5cfa79552d79635566d5a0a3c20b44efd84fea773acef364a699a37a",
        "org/dyn4j/world/WorldLegacyViewsProbe.java" to
            "b6dee65ff342ca333b802e68358fdb2e9cb0b01ea0f8dc4555db677e68891db3",
        "org/dyn4j/world/WorldNestedEmptyClearProbe.java" to
            "575bba29efb16fd127825d813b8ecd23b34fc6d1688c948896fc4ca3d0f30d17",
        "org/dyn4j/world/WorldReentryProbe.java" to
            "2cd724e1748529e3d8b3935844e8e01fefc5b5180eec27baf30f18eda397112b",
        "org/dyn4j/world/WorldSerializableViewsConsumer.java" to
            "24244a72699342000afa48039ee48c0dfb4a73b7221128ef56050e512e008746",
        "org/dyn4j/world/WorldSortExceptionProbe.java" to
            "4ec0e2cc2ab0939167149defe280baf0f617010edad578936eec66366fb9dbfb",
    )

    val MODES: Map<String, List<String>> = linkedMapOf(
        "org.dyn4j.world.WorldProtectedListConsumer" to
            listOf("protected-sublist", "reversed-range", "random-access", "sort", "replace-all"),
        "WorldResultHelperConsumer" to
            listOf("different", "same", "convex-different", "convex-same"),
        "WorldListSemanticsConsumer" to
            listOf("backing", "sublist", "empty", "empty-sort", "empty-removeIf"),
    )

    val PACKAGED_ROOT_SOURCES = setOf(
        "WorldArrayListMutationAuditConsumer.java",
        "WorldProtectedListConsumer.java",
    )

    /** One frozen main class and the argument it runs with, or null when it takes none. */
    data class WorldMode(val main: String, val mode: String?)

    /** The identity `validate_runs` returns the observed baselines under. */
    data class BaselineKey(val runtime: String, val main: String, val mode: String?)

    fun expectedModes(): List<WorldMode> {
        val modes = mutableListOf<WorldMode>()
        for (relative in SOURCE_SHA.keys) {
            val name = fileName(relative).substringBeforeLast(".")
            val packaged = relative.startsWith("org/dyn4j/world/") || relative in PACKAGED_ROOT_SOURCES
            val main = if (packaged) "org.dyn4j.world.$name" else name
            val arguments = MODES[main] ?: listOf<String?>(null)
            for (mode in arguments) modes.add(WorldMode(main, mode))
        }
        if (modes.size != 23 || modes.toSet().size != 23) {
            throw IllegalArgumentException("World execution inventory differs from frozen 23 modes")
        }
        return modes
    }

    fun runlogName(provider: String, runtime: String, index: Int): String =
        "runs/$provider-$runtime-" + index.toString().padStart(2, '0') + ".json"

    /** Checks every frozen source against [expected], raising `World source differs: <name>`. */
    fun validateSources(files: CorpusFiles, sourceRoot: String, expected: Map<String, String>) {
        if (expected.isEmpty()) {
            throw IllegalArgumentException("World source inventory is empty or duplicated")
        }
        for ((relative, sha) in expected) {
            val path = joinPath(sourceRoot, relative)
            if (files.isSymlink(path) || !files.isFile(path) || files.digest(path) != sha) {
                throw IllegalArgumentException("World source differs: $relative")
            }
        }
    }

    /**
     * Replays the 138 recorded runs and returns the baseline stdout per `(runtime, main, mode)`.
     *
     * [rows] are the report rows as JSON, because `world_ci.validate_runs` reads them with
     * `dict.get` and accepts a JSON null and a missing key alike.
     */
    fun validateRuns(
        rows: List<JsonElement>,
        output: String,
        files: CorpusFiles,
    ): Map<BaselineKey, String> {
        val paths = linkedMapOf<RunKey, String>()
        for (provider in PROVIDERS) {
            for (runtime in RUNTIMES) {
                expectedModes().forEachIndexed { index, mode ->
                    paths[RunKey(provider, runtime, mode.main, mode.mode)] =
                        runlogName(provider, runtime, index)
                }
            }
        }
        if (rows.size != 138) {
            throw IllegalArgumentException("World execution matrix must contain exactly 138 paths")
        }
        val observed = linkedMapOf<RunKey, String>()
        for (element in rows) {
            val row = element as? JsonObject
                ?: throw IllegalArgumentException("World execution row is malformed")
            val key = RunKey(
                row.text("provider"),
                row.text("runtime"),
                row.text("main"),
                row.text("mode"),
            )
            if (key in observed || key !in paths || row.text("log") != paths[key]) {
                throw IllegalArgumentException("World execution key or log path differs")
            }
            val path = joinPath(output, paths.getValue(key))
            if (files.isSymlink(path) || !files.isFile(path) ||
                files.digest(path) != row.text("log_sha256")
            ) {
                throw IllegalArgumentException("World execution raw log is missing or changed")
            }
            val raw = parseObject(files.readText(path))
            val command = raw["command"]
            val suffix = listOfNotNull(key.main) + listOfNotNull(key.mode)
            if (notPythonZero(raw["exit"]) || notPythonZero(row["exit"]) ||
                !isJsonString(raw["stdout"]) || raw["stdout"].asString().isEmpty() ||
                !isJsonString(raw["stderr"]) ||
                command !is JsonArray || command.size < 4 ||
                !command[0].asString().endsWith("/bin/java") ||
                command[1].asString() != "-cp" ||
                command.stringList().takeLast(suffix.size) != suffix
            ) {
                throw IllegalArgumentException("World execution failed or raw process identity differs")
            }
            observed[key] = raw["stdout"].asString()
        }
        if (observed.keys != paths.keys) {
            throw IllegalArgumentException("World execution keys are incomplete")
        }
        for ((key, stdout) in observed) {
            if (key.provider != "baseline" &&
                stdout != observed[RunKey("baseline", key.runtime, key.main, key.mode)]
            ) {
                throw IllegalArgumentException(
                    "World stdout differs from same-runtime baseline: " +
                        "${key.provider} ${key.runtime} ${key.main} ${key.mode ?: "None"}",
                )
            }
        }
        val result = linkedMapOf<BaselineKey, String>()
        for ((key, stdout) in observed) {
            if (key.provider == "baseline") {
                // Every observed key matched `paths`, whose keys are non-null, so these hold.
                result[BaselineKey(requireNotNull(key.runtime), requireNotNull(key.main), key.mode)] = stdout
            }
        }
        return result
    }

    /**
     * Reports the known serialization regression: the baseline prints a serialized body view and
     * the bad archive fails to serialize `worldReadOnlyView`.
     */
    fun validateAdverseOutput(baseline: String, mutant: String) {
        if ("bodies,empty=VALUE:" !in baseline ||
            "bodies,empty=NotSerializableException:org.dyn4j.world.AbstractCollisionWorldKt" +
            "\$worldReadOnlyView\$1" !in mutant ||
            mutant == baseline
        ) {
            throw IllegalArgumentException(
                "World body-view adverse control did not expose the known serialization regression",
            )
        }
    }

    /**
     * Checks that [recorded] names exactly the files below [output], except `result.json`, and that
     * every hash still matches. The returned map is sorted by relative path.
     */
    fun sealFiles(
        output: String,
        recorded: Map<String, String>,
        files: CorpusFiles,
    ): Map<String, String> {
        if (recorded.isEmpty()) {
            throw IllegalArgumentException("World raw file inventory is empty")
        }
        val actual = linkedMapOf<String, String>()
        for (relative in files.filesBelow(output)) {
            val path = joinPath(output, relative)
            if (path == joinPath(output, "result.json")) continue
            actual[relative] = path
        }
        if (actual.keys != recorded.keys) {
            throw IllegalArgumentException("World raw file set differs")
        }
        for ((relative, path) in actual) {
            if (files.isSymlink(path) || files.digest(path) != recorded[relative]) {
                throw IllegalArgumentException("World raw file hash differs: $relative")
            }
        }
        return sortedByCodePoint(recorded.keys).associateWith { recorded.getValue(it) }
    }

    private data class RunKey(
        val provider: String?,
        val runtime: String?,
        val main: String?,
        val mode: String?,
    )

    private val json = Json

    private fun parseObject(text: String): JsonObject =
        json.parseToJsonElement(text) as? JsonObject
            ?: throw IllegalArgumentException("raw world log is not a JSON object")

    private fun JsonObject.text(key: String): String? = this[key].asStringOrNull()

    private fun JsonElement?.asStringOrNull(): String? = when (this) {
        null, is JsonNull -> null
        is JsonPrimitive -> content
        else -> null
    }

    private fun JsonElement?.asString(): String = asStringOrNull() ?: ""

    private fun JsonElement?.stringList(): List<String> =
        (this as? JsonArray)?.map {
            if (it is JsonPrimitive && it.isString) it.content else it.toString()
        } ?: emptyList()

    private fun isJsonString(value: JsonElement?): Boolean =
        value is JsonPrimitive && value.isString

    /**
     * Python compares `value != 0`, which is false for the number zero and for `False`. A missing
     * key is `None`, so the comparison is true.
     */
    private fun notPythonZero(value: JsonElement?): Boolean = when (value) {
        null, is JsonNull -> true
        is JsonPrimitive ->
            if (value.isString) true else value.content != "0" && value.content != "false"
        else -> true
    }

    private fun JsonArray.stringList(): List<String> = map {
        if (it is JsonPrimitive && it.isString) it.content else it.toString()
    }
}
