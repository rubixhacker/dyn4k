package io.github.rubixhacker.harness.android

import java.nio.file.Files
import java.nio.file.Path
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/**
 * `tools/android-native-runtime/adverse.py`.
 *
 * A receipt is only evidence if a plausible forgery is rejected. Each control mutates one recorded
 * field of a passing receipt and must make `full.validate_result` fail; a control that is accepted means
 * the receipt checks have a hole.
 */
object Adverse {
    /** Runs every adverse control over [receiptPath] and returns the labels that were rejected. */
    fun testAdverse(root: Path, receiptPath: Path): List<String> {
        val original = FullHost.parseJson(receiptPath.toFile().readBytes())
        if (NativeFullHost.validateResult(original, root).textOrNull("status") != "CONSISTENCY_ONLY") {
            throw IllegalArgumentException("passing full receipt is required")
        }
        val rejected = mutableListOf<String>()
        val directory = Files.createTempDirectory("dyn4k-native-adverse-")

        fun expectRejected(
            name: String,
            mutate: (MutableMap<String, JsonElement>) -> Unit,
            seams: NativeFullSeams,
        ) {
            val item = deepCopy(original)
            mutate(item)
            try {
                NativeFullHost.validateResult(JsonObject(item), root, seams)
            } catch (failure: Exception) {
                if (failure is IllegalArgumentException || failure is IllegalStateException ||
                    failure is java.io.IOException || failure is NoSuchElementException ||
                    failure is IndexOutOfBoundsException
                ) {
                    rejected += name
                    return
                }
                throw failure
            }
            throw IllegalStateException("adverse control was accepted: $name")
        }

        val key = "core-debug"
        val lane = original.getValue("lanes").objectOrNull()!!.getValue(key).objectOrNull()!!
        val processStdout = lane.getValue("process").objectOrNull()!!.getValue("stdout").objectOrNull()!!
        val stdout = NativeFullHost.readRecord(processStdout)
        val first = NativeFullContract.parseTestRun(stdout.decodeToString())[0]

        fun missingCase(item: MutableMap<String, JsonElement>) {
            var text = stdout.decodeToString()
            text = text.replace("[ RUN      ] $first\n", "", ignoreCase = false)
            text = Regex("""\[       OK \] ${Regex.escape(first)} \(\d+ ms\)\n""")
                .replaceFirst(text, "")
            text = text.replace("[==========] 2465 tests from", "[==========] 2464 tests from")
            text = text.replace("[  PASSED  ] 2465 tests.", "[  PASSED  ] 2464 tests.")
            replaceLaneStdout(item, key, text.encodeToByteArray(), directory, "missing.stdout")
            val laneRecord = item.getValue("lanes").objectOrNull()!!.getValue(key).objectOrNull()!!
                .toMutableMap()
            laneRecord["case_count"] = JsonPrimitive(2464)
            item["lanes"] = withEntry(item.getValue("lanes").objectOrNull()!!, key, JsonObject(laneRecord))
            item["total_common_cases"] = JsonPrimitive(
                (item.getValue("total_common_cases") as JsonPrimitive).content.toLong() - 1,
            )
        }

        fun duplicateCase(item: MutableMap<String, JsonElement>) {
            val text = stdout.decodeToString()
            val runLine = "[ RUN      ] $first\n"
            val okLine = Regex("""\[       OK \] ${Regex.escape(first)} \(\d+ ms\)\n""").find(text)
                ?: throw IllegalArgumentException("missing OK line")
            val pair = runLine + okLine.value
            var copy = text.replaceFirst(pair, pair + pair)
            copy = copy.replace("[==========] 2465 tests from", "[==========] 2466 tests from")
            copy = copy.replace("[  PASSED  ] 2465 tests.", "[  PASSED  ] 2466 tests.")
            replaceLaneStdout(item, key, copy.encodeToByteArray(), directory, "duplicate.stdout")
            val laneRecord = item.getValue("lanes").objectOrNull()!!.getValue(key).objectOrNull()!!
                .toMutableMap()
            laneRecord["case_count"] = JsonPrimitive(2466)
            item["lanes"] = withEntry(item.getValue("lanes").objectOrNull()!!, key, JsonObject(laneRecord))
            item["total_common_cases"] = JsonPrimitive(
                (item.getValue("total_common_cases") as JsonPrimitive).content.toLong() + 1,
            )
        }

        fun expectRejected(name: String, mutate: (MutableMap<String, JsonElement>) -> Unit) =
            expectRejected(name, mutate, NativeFullSeams.Default)

        expectRejected("missing case", ::missingCase)
        expectRejected("duplicate case", ::duplicateCase)
        expectRejected("forged PASS line") { item ->
            replaceLaneStdout(
                item,
                key,
                (stdout.decodeToString() + "[  PASSED  ] 2465 tests.\n").encodeToByteArray(),
                directory,
                "forged.stdout",
            )
        }
        expectRejected("nonzero process") { item ->
            updateLaneProcess(item, key) { process -> process["exit_code"] = JsonPrimitive(1) }
        }
        expectRejected("lost stdout") { item ->
            updateLaneProcess(item, key) { process ->
                process["stdout"] = withEntry(process.getValue("stdout").objectOrNull()!!, "path",
                    JsonPrimitive("${posix(directory)}/missing"))
            }
        }
        expectRejected("lost stderr") { item ->
            updateLaneProcess(item, key) { process ->
                process["stderr"] = withEntry(process.getValue("stderr").objectOrNull()!!, "path",
                    JsonPrimitive("${posix(directory)}/missing"))
            }
        }
        expectRejected("debug optimized swap") { item ->
            val lanes = item.getValue("lanes").objectOrNull()!!.toMutableMap()
            val debug = lanes.getValue("core-debug")
            lanes["core-debug"] = lanes.getValue("core-optimized")
            lanes["core-optimized"] = debug
            item["lanes"] = JsonObject(lanes)
        }
        expectRejected("wrong source tree") { item -> item["source_tree"] = JsonPrimitive("0".repeat(40)) }
        expectRejected("changed committed pin") { item -> item["pin_sha256"] = JsonPrimitive("0".repeat(64)) }
        expectRejected("wrong guest fingerprint") { item ->
            val guest = item.getValue("guest").objectOrNull()!!.toMutableMap()
            guest["values"] = withEntry(guest.getValue("values").objectOrNull()!!, "fingerprint",
                "other/image")
            item["guest"] = JsonObject(guest)
        }
        expectRejected("wrong guest ABI") { item ->
            val guest = item.getValue("guest").objectOrNull()!!.toMutableMap()
            guest["values"] = withEntry(guest.getValue("values").objectOrNull()!!, "primary_abi",
                "arm64-v8a")
            item["guest"] = JsonObject(guest)
        }
        val coreGraph = NativeFullHost.readRecord(
            original.getValue("graphs").objectOrNull()!!.getValue("core").objectOrNull()!!
                .getValue("stdout").objectOrNull()!!,
        )
        expectRejected("changed dependency graph") { item ->
            replaceGraphStdout(
                item,
                "core",
                coreGraph.decodeToString()
                    .replace("org.jetbrains.kotlin:kotlin-stdlib:2.4.20",
                        "org.jetbrains.kotlin:kotlin-stdlib:2.4.21")
                    .encodeToByteArray(),
                directory,
                "changed-graph.stdout",
            )
        }

        val graph = NativeFullHost.readRecord(
            original.getValue("graphs").objectOrNull()!!.getValue("consumer").objectOrNull()!!
                .getValue("stdout").objectOrNull()!!,
        ).decodeToString()
        val header = "androidNativeX64CompileKlibraries -"
        val start = graph.indexOf(header)
        val end = graph.indexOf("\n\n", start)
        val forgedGraph = graph.substring(0, end) + "\n+--- example:unapproved:1.0" + graph.substring(end)
        expectRejected("unapproved provider") { item ->
            replaceGraphStdout(item, "consumer", forgedGraph.encodeToByteArray(), directory,
                "unapproved-graph.stdout")
        }

        val wrongElf = directory.resolve("wrong.kexe")
        wrongElf.toFile().writeBytes("wrong ELF".encodeToByteArray())
        expectRejected("wrong executable", {}, object : NativeFullSeams {
            override fun executablePath(root: Path, module: String, variant: String): String =
                if (module == "core" && variant == "debug") {
                    posix(wrongElf)
                } else {
                    NativeFullSeams.Default.executablePath(root, module, variant)
                }

            override fun klibPaths(root: Path): Map<String, String> =
                NativeFullSeams.Default.klibPaths(root)

            override fun toolPaths(root: Path): Map<String, Path> = NativeFullSeams.Default.toolPaths(root)
        })
        val wrongKlib = directory.resolve("wrong.klib")
        wrongKlib.toFile().writeBytes("wrong KLIB".encodeToByteArray())
        expectRejected("wrong KLIB", {}, object : NativeFullSeams {
            override fun executablePath(root: Path, module: String, variant: String): String =
                NativeFullSeams.Default.executablePath(root, module, variant)

            override fun klibPaths(root: Path): Map<String, String> =
                NativeFullSeams.Default.klibPaths(root) + ("dyn4k-core" to posix(wrongKlib))

            override fun toolPaths(root: Path): Map<String, Path> = NativeFullSeams.Default.toolPaths(root)
        })
        val wrongImage = directory.resolve("wrong-image.properties")
        wrongImage.toFile().writeBytes("stale Android image".encodeToByteArray())
        expectRejected("stale Android image", {}, object : NativeFullSeams {
            override fun executablePath(root: Path, module: String, variant: String): String =
                NativeFullSeams.Default.executablePath(root, module, variant)

            override fun klibPaths(root: Path): Map<String, String> =
                NativeFullSeams.Default.klibPaths(root)

            override fun toolPaths(root: Path): Map<String, Path> =
                NativeFullSeams.Default.toolPaths(root) + ("image" to wrongImage)
        })

        val drift = root.resolve(".dyn4k-native-source-drift-probe")
        if (Files.exists(drift)) {
            throw IllegalArgumentException("source drift probe path already exists")
        }
        try {
            drift.toFile().writeText("adverse source drift\n")
            expectRejected("source checkout drift", {})
        } finally {
            Files.deleteIfExists(drift)
        }
        AndroidFiles.deleteRecursively(directory)
        return rejected
    }

    private fun replaceLaneStdout(
        item: MutableMap<String, JsonElement>,
        key: String,
        raw: ByteArray,
        directory: Path,
        name: String,
    ) {
        val path = directory.resolve(name)
        path.toFile().writeBytes(raw)
        updateLaneProcess(item, key) { process ->
            process["stdout"] = kotlinx.serialization.json.buildJsonObject {
                put("path", JsonPrimitive(posix(path)))
                put("sha256", JsonPrimitive(
                    io.github.rubixhacker.harness.contract.Sha256.of(raw),
                ))
            }
        }
    }

    private fun updateLaneProcess(
        item: MutableMap<String, JsonElement>,
        key: String,
        change: (MutableMap<String, JsonElement>) -> Unit,
    ) {
        val lanes = item.getValue("lanes").objectOrNull()!!.toMutableMap()
        val lane = lanes.getValue(key).objectOrNull()!!.toMutableMap()
        val process = lane.getValue("process").objectOrNull()!!.toMutableMap()
        change(process)
        lane["process"] = JsonObject(process)
        lanes[key] = JsonObject(lane)
        item["lanes"] = JsonObject(lanes)
    }

    private fun replaceGraphStdout(
        item: MutableMap<String, JsonElement>,
        module: String,
        raw: ByteArray,
        directory: Path,
        name: String,
    ) {
        val path = directory.resolve(name)
        path.toFile().writeBytes(raw)
        val graphs = item.getValue("graphs").objectOrNull()!!.toMutableMap()
        val graph = graphs.getValue(module).objectOrNull()!!.toMutableMap()
        graph["stdout"] = kotlinx.serialization.json.buildJsonObject {
            put("path", JsonPrimitive(posix(path)))
            put("sha256", JsonPrimitive(io.github.rubixhacker.harness.contract.Sha256.of(raw)))
        }
        graphs[module] = JsonObject(graph)
        item["graphs"] = JsonObject(graphs)
    }

    private fun withEntry(objectValue: JsonObject, key: String, value: String): JsonObject =
        JsonObject(objectValue.toMutableMap().apply { put(key, JsonPrimitive(value)) })

    private fun withEntry(objectValue: JsonObject, key: String, value: JsonElement): JsonObject =
        JsonObject(objectValue.toMutableMap().apply { put(key, value) })

    /** `copy.deepcopy` of a parsed JSON value. */
    private fun deepCopy(value: JsonObject): MutableMap<String, JsonElement> =
        value.mapValuesTo(LinkedHashMap()) { (_, element) -> copyElement(element) }

    private fun copyElement(element: JsonElement): JsonElement = when (element) {
        is JsonObject -> JsonObject(element.mapValues { (_, value) -> copyElement(value) })
        is kotlinx.serialization.json.JsonArray ->
            kotlinx.serialization.json.JsonArray(element.map { copyElement(it) })
        is JsonNull -> JsonNull
        else -> element
    }
}
