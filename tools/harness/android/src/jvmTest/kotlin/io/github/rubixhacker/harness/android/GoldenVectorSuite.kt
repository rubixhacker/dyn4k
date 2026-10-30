package io.github.rubixhacker.harness.android

import de.infix.testBalloon.framework.core.testSuite
import java.nio.file.Files
import java.nio.file.Path
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

/**
 * Golden vectors recorded from the Python implementation.
 *
 * `AndroidVectors.json` was produced by `parity/generate_vectors.py` at the revision recorded inside it.
 * Every case replays an input through the Kotlin port and asserts the Python output, including its error
 * message, byte for byte.
 */
private val vectors: JsonObject = AndroidVectors.json

private fun JsonObject.group(name: String): JsonObject = getValue(name).jsonObject

private fun JsonObject.list(name: String): List<JsonObject> = getValue(name).jsonArray.map { it.jsonObject }

private fun JsonObject.text(name: String): String = getValue(name).jsonPrimitive.content

private fun JsonObject.strings(name: String): Set<String> =
    getValue(name).jsonArray.map { it.jsonPrimitive.content }.toSet()

/**
 * Runs [block] and compares its outcome with the recorded one: an error must be thrown with Python's
 * message, otherwise the returned JSON must equal the recorded value.
 */
private fun assertVector(element: JsonElement, label: String, block: () -> JsonElement?) {
    val record = element.jsonObject
    val error = record["error"]
    if (error != null && error !is JsonNull) {
        val thrown = assertFailsWith<IllegalArgumentException>(label) { block() }
        assertEquals(error.jsonPrimitive.content, thrown.message, label)
    } else {
        val expected = record["value"] ?: JsonNull
        val actual = block() ?: JsonNull
        // A recorded `null` is a Python function returning None: the call only has to succeed.
        if (expected !is JsonNull) assertEquals(expected, actual, label)
    }
}

private fun mappingJson(mapped: Map<String, OptimizedEvidence.MappedClass>): JsonObject =
    buildJsonObject {
        for ((original, value) in mapped) {
            put(
                original,
                buildJsonObject {
                    put("name", JsonPrimitive(value.name))
                    put("descriptor", value.descriptor?.let { JsonPrimitive(it) } ?: JsonNull)
                },
            )
        }
    }

val AndroidGoldenVectorsContract by testSuite {
    test("instrumentation parsing matches the recorded transcripts") {
        val group = vectors.group("instrumentation")
        for ((index, record) in group.list("parse").withIndex()) {
            val raw = record.text("raw")
            assertVector(record.getValue("result"), "parse #$index") {
                Evidence.parseInstrumentation(raw).toJson()
            }
        }
    }

    test("lane validation matches the recorded verdicts") {
        val group = vectors.group("instrumentation")
        for ((index, record) in group.list("lane").withIndex()) {
            val raw = record.text("raw")
            val portable = record.strings("portable")
            val instrumentation = record.strings("instrumentation")
            val exit = (record.getValue("exit") as JsonPrimitive).content.toInt()
            assertVector(record.getValue("result"), "lane #$index") {
                Evidence.validateLane(
                    Evidence.parseInstrumentation(raw),
                    portable,
                    instrumentation,
                    exit,
                )
                JsonPrimitive("ok")
            }
        }
    }

    test("optimized R8 rules match the recorded verdicts") {
        val group = vectors.group("optimized")
        for ((index, record) in group.list("r8").withIndex()) {
            val configuration = record.text("configuration")
            val mapping = record.text("mapping")
            val usage = record.text("usage")
            val dex = record.strings("dex")
            assertVector(record.getValue("result"), "r8 #$index ${configuration.take(40)}") {
                mappingJson(OptimizedEvidence.validateR8(configuration, mapping, usage, dex))
            }
        }
    }

    test("optimized provider graph matches the recorded verdicts") {
        for ((index, record) in vectors.group("optimized").list("provider").withIndex()) {
            val graph = record.text("graph")
            assertVector(record.getValue("result"), "provider #$index") {
                OptimizedEvidence.validateProvider(graph)
                JsonPrimitive("ok")
            }
        }
    }

    test("optimized installed case matches the recorded verdicts") {
        for ((index, record) in vectors.group("optimized").list("installed").withIndex()) {
            val raw = record.text("raw")
            val exit = (record.getValue("exit") as JsonPrimitive).content.toInt()
            val case = record.text("case")
            assertVector(record.getValue("result"), "installed #$index") {
                OptimizedEvidence.validateInstalledCase(raw, exit, case).toJson()
            }
        }
    }

    test("full installed umbrella matches the recorded verdicts") {
        for ((index, record) in vectors.group("full").list("installed").withIndex()) {
            val raw = record.text("raw")
            val expected = setOf(FULL_VECTOR_CASE, FULL_VECTOR_CONSUMER)
            assertVector(record.getValue("result"), "full installed #$index") {
                FullEvidence.validateFullInstalled(raw, expected, 0).toJson()
            }
        }
    }

    test("full R8 evidence matches the recorded verdicts") {
        for (record in vectors.group("full").list("r8")) {
            val label = record.text("label")
            assertVector(record.getValue("result"), label) {
                FullEvidence.validateFullR8(
                    record.text("configuration"),
                    record.text("mapping"),
                    record.text("usage"),
                    record.strings("debug_dex"),
                    record.strings("release_dex"),
                    record.strings("allowed"),
                    (record.getValue("minimum") as JsonPrimitive).content.toInt(),
                ).toJson()
            }
        }
    }

    test("full keep scope matches the recorded verdicts") {
        for (record in vectors.group("full").list("keep_scope")) {
            val configuration = record.text("configuration")
            val allowed = record.strings("allowed")
            assertVector(record.getValue("result"), "keep scope ${configuration.take(40)}") {
                FullEvidence.validateFullKeepScope(configuration, allowed)
                JsonPrimitive("ok")
            }
        }
    }

    test("full process logs match the recorded verdicts") {
        val group = vectors.group("full")
        for (record in group.list("process_log")) {
            val log = record.text("log")
            val pkg = record.text("package")
            assertVector(record.getValue("result"), "process log ${log.takeLast(40)}") {
                JsonPrimitive(FullEvidence.validateFullProcessLog(log, pkg))
            }
        }
        for (record in group.list("api21_log")) {
            val label = record.text("label")
            val log = record.text("log")
            val pkg = record.text("package")
            val abi = record.text("abi")
            val before = record.text("before_pid")
            assertVector(record.getValue("result"), "api21 log $label") {
                JsonPrimitive(RunFullContract.validateApi21ProcessLog(log, pkg, abi, before))
            }
        }
        for (record in group.list("api21_process")) {
            val label = record.text("label")
            val listing = record.text("listing")
            val pkg = record.text("package")
            val required = (record.getValue("required") as JsonPrimitive).content.toBoolean()
            assertVector(record.getValue("result"), "api21 process $label") {
                RunFullContract.api21ProcessPid(listing, pkg, required)
                    ?.let { JsonPrimitive(it) } ?: JsonNull
            }
        }
    }

    test("runtime identity matches the recorded verdicts") {
        for (record in vectors.group("full").list("runtime")) {
            val identity = record.getValue("identity").jsonObject.mapValues { it.value.jsonPrimitive.content }
            val api = record.text("api")
            val abi = record.text("abi")
            val boot = record.text("boot")
            assertVector(record.getValue("result"), "runtime $api $abi $boot") {
                RunFullContract.validateRuntime(identity, api, abi, boot)
                JsonPrimitive("ok")
            }
        }
    }

    test("resolved provider graph matches the recorded verdicts") {
        val group = vectors.group("full").group("provider_artifacts")
        val files = group.getValue("files").jsonObject.mapValues { it.value.jsonPrimitive.content }
        for (record in group.list("vectors")) {
            val label = record.text("label")
            withTempDirectory { root ->
                val providerRoot = root.resolve("provider")
                Files.createDirectories(providerRoot)
                val overrides = record.objectOrNull("overrides")
                for ((artifact, content) in files) {
                    writeBytes(
                        providerRoot,
                        "$artifact.aar",
                        (overrides?.textOrNull(artifact) ?: content).encodeToByteArray(),
                    )
                }
                val graph = record.text("graph").replace("<tmp>", posix(root))
                val staged = record.getValue("staged").jsonObject.mapValues { it.value }
                val prepared = buildJsonObject { put("staged", JsonObject(staged)) }
                val result = record.getValue("result").jsonObject
                val error = result["error"]
                if (error != null && error !is JsonNull) {
                    val thrown = assertFailsWith<IllegalArgumentException>(label) {
                        FullHost.validateProviderArtifacts(graph, prepared)
                    }
                    assertEquals(error.jsonPrimitive.content, thrown.message, label)
                } else {
                    // The recorded paths are normalised to `<tmp>`; the replay substitutes its own root.
                    val actual = FullHost.validateProviderArtifacts(graph, prepared).toString()
                        .replace(posix(root), "<tmp>")
                    assertEquals(result.getValue("value"), Json.parseToJsonElement(actual), label)
                }
            }
        }
    }

    test("build identity matches the recorded verdicts") {
        val group = vectors.group("build_identity")
        for (record in group.list("build_jdk")) {
            val label = record.text("label")
            val raw = record.text("raw")
            val requireMarker = label != "marker optional"
            assertVector(record.getValue("result"), label) {
                BuildIdentity.validateBuildJdk(raw, requireMarker = requireMarker).toJson()
            }
        }
        for ((index, record) in group.list("java_version").withIndex()) {
            val stderr = record.text("stderr")
            assertVector(record.getValue("result"), "java version #$index") {
                JsonPrimitive(BuildIdentity.javaVersionBanner(stderr))
            }
        }
    }

    test("generated full app inputs match the recorded bytes") {
        val group = vectors.group("corpus")
        for ((index, record) in group.list("manifests").withIndex()) {
            val cases = record.getValue("cases").jsonArray.map { element ->
                val case = element.jsonObject
                SuiteCase(
                    case.text("id"),
                    case.text("module"),
                    case.text("classname"),
                    case.text("method"),
                    case.text("scope"),
                )
            }
            assertEquals(
                record.getValue("case_ids").jsonArray.map { it.jsonPrimitive.content },
                cases.map { AndroidCorpus.caseId(it) },
                "case ids #$index",
            )
            val inputs = AndroidCorpus.fullAppInputs(cases)
            assertEquals(record.text("case_asset"), inputs.getValue("case_asset").decodeToString(), "asset #$index")
            assertEquals(record.text("keep_rules"), inputs.getValue("keep_rules").decodeToString(), "rules #$index")
        }
        assertEquals(
            group.strings("reflective_filter_types"),
            AndroidCorpus.REFLECTIVE_FILTER_TYPES.toSet(),
        )
        assertEquals(
            group.getValue("java_journeys").jsonArray.map { it.jsonPrimitive.content },
            AndroidCorpus.JAVA_JOURNEYS,
        )
        assertEquals(group.text("kotlin_journey"), AndroidCorpus.KOTLIN_JOURNEY)
        assertEquals(group.text("x86_dexopt_method"), AndroidCorpus.X86_DEXOPT_METHOD)
        assertEquals(
            group.getValue("fingerprints").jsonObject.mapValues { it.value.jsonPrimitive.content },
            AndroidCorpus.FINGERPRINTS,
        )
        assertEquals(
            group.getValue("api21_fingerprints").jsonObject.mapValues { it.value.jsonPrimitive.content },
            RunFullContract.API21_FINGERPRINTS,
        )
        assertEquals(group.strings("consumer_cases"), RunContract.CONSUMER_CASES)
        assertEquals(
            group.getValue("consumers").jsonArray.map { it.jsonPrimitive.content },
            PrepareContract.CONSUMERS,
        )
        assertEquals(group.text("version"), PrepareContract.VERSION)
    }

    test("android consumer source adaptation matches the recorded bytes") {
        for (record in vectors.group("prepare").list("android_consumer_source")) {
            val name = record.text("name")
            val source = record.text("source")
            val result = record.getValue("result")
            if (result is JsonObject && result["error"] != null) {
                assertFailsWith<IllegalArgumentException> {
                    PrepareContract.androidConsumerSource(name, source.encodeToByteArray())
                }
            } else {
                assertEquals(
                    result.jsonObject.text("value"),
                    PrepareContract.androidConsumerSource(name, source.encodeToByteArray())
                        .decodeToString(),
                )
            }
        }
    }

    test("instrumentation filter and class selection match the recording") {
        val group = vectors.group("run")
        for (record in group.list("filter")) {
            val flavor = record.text("flavor")
            val api = record.text("api")
            val portable = record.getValue("prepared").jsonObject
                .getValue("portable_classes").jsonArray.map { it.jsonPrimitive.content }
            val prepared = buildJsonObject {
                put("portable_classes", JsonArray(portable.map { JsonPrimitive(it) }))
            }
            withTempDirectory { directory ->
                val selection = LaneHost.instrumentationFilter(prepared, flavor, "debug", api, directory)
                val expected = record.getValue("result").jsonObject.getValue("value").jsonObject
                assertEquals(
                    expected.getValue("classes").jsonArray.map { it.jsonPrimitive.content },
                    selection.classes,
                    "classes $flavor $api",
                )
                assertEquals(
                    expected.getValue("arguments").jsonArray.map { it.jsonPrimitive.content },
                    selection.arguments,
                    "arguments $flavor $api",
                )
                val recordedSelection = expected["selection"]
                if (recordedSelection == null || recordedSelection is JsonNull) {
                    assertEquals(null, selection.selectionPath)
                } else {
                    val path = Path.of(selection.selectionPath!!)
                    assertEquals(
                        (recordedSelection.jsonObject.getValue("size") as JsonPrimitive).content.toInt(),
                        Files.size(path).toInt(),
                    )
                    assertEquals(
                        recordedSelection.jsonObject.getValue("lines").jsonArray
                            .map { it.jsonPrimitive.content },
                        pySplitLines(path.toFile().readText()),
                    )
                }
            }
        }
        for ((flavor, expected) in group.getValue("classes").jsonObject) {
            val portable = vectors.group("run").list("filter").first()
                .getValue("prepared").jsonObject.getValue("portable_classes").jsonArray
                .map { it.jsonPrimitive.content }
            assertEquals(
                expected.jsonArray.map { it.jsonPrimitive.content },
                RunContract.instrumentationClasses(portable, flavor),
                flavor,
            )
        }
    }

    test("emulator serial selection matches the recording") {
        for (record in vectors.group("run").list("serial")) {
            val serial = record.text("serial")
            val result = record.getValue("result")
            if (result is JsonObject && result["error"] != null) {
                val thrown = assertFailsWith<ArgumentTypeError>(serial) {
                    RunContract.adbForSerial("/sdk", serial)
                }
                assertEquals(result.text("error"), thrown.message, serial)
            } else {
                assertEquals(
                    result.jsonObject.getValue("value").jsonArray.map { it.jsonPrimitive.content },
                    RunContract.adbForSerial("/sdk", serial),
                    serial,
                )
            }
        }
    }

    test("native dependency graph matches the recording") {
        for ((index, record) in vectors.group("native").list("receipt").withIndex()) {
            val graph = record.text("graph")
            assertVector(record.getValue("result"), "native graph #$index") {
                NativeReceipt.validateDependencyGraph(graph)
                JsonPrimitive("ok")
            }
        }
    }

    test("native ELF headers match the recording") {
        for (record in vectors.group("native").list("elf")) {
            val raw = record.text("bytes").chunked(2).map { it.toInt(16).toByte() }.toByteArray()
            assertVector(record.getValue("result"), record.text("label")) {
                JsonPrimitive(NativeReceipt.elfAbi(raw))
            }
        }
    }

    test("native listing and process transcripts match the recording") {
        val group = vectors.group("native").list("list")
        for ((index, record) in group.withIndex()) {
            val label = record.text("label")
            val raw = record.text("raw")
            val result = record.getValue("result")
            if (index < 7) {
                assertVector(result, "list $label") {
                    JsonArray(NativeFullContract.parseList(raw).map { JsonPrimitive(it) })
                }
            } else {
                assertVector(result, "run $label") {
                    JsonArray(NativeFullContract.parseTestRun(raw).map { JsonPrimitive(it) })
                }
            }
        }
    }

    test("native device listings match the recording") {
        for (record in vectors.group("native").list("device_listing")) {
            val raw = record.text("raw")
            assertVector(record.getValue("result"), record.text("label")) {
                NativeFullContract.requireTaskDevice(raw)
                JsonNull
            }
        }
    }

    test("native guest values match the recording") {
        for (record in vectors.group("native").list("guest_values")) {
            val observations = record.getValue("observations").jsonObject
                .mapValues { it.value.jsonPrimitive.content }
            assertVector(record.getValue("result"), record.text("label")) {
                JsonObject(
                    NativeFullContract.guestValues(observations)
                        .mapValues { JsonPrimitive(it.value) },
                )
            }
        }
    }

    test("native deployment checks match the recording") {
        for (record in vectors.group("native").list("deployment")) {
            assertVector(record.getValue("result"), record.text("label")) {
                NativeFullContract.validateDeploymentOutput(
                    record.text("push").encodeToByteArray(),
                    record.text("push_err").encodeToByteArray(),
                    record.text("chmod_err").encodeToByteArray(),
                    record.text("remote_out").encodeToByteArray(),
                    record.text("remote_err").encodeToByteArray(),
                    record.text("expected"),
                )
                JsonNull
            }
        }
    }

    test("native dependency graph sections match the recording") {
        for (record in vectors.group("native").list("graph_section")) {
            val module = record.text("module")
            val raw = record.text("raw")
            val label = record.objectOrNull("label")?.let { (it as JsonPrimitive).content } ?: module
            assertVector(record.getValue("result"), "graph section $label") {
                JsonPrimitive(NativeFullContract.graphSection(raw, module))
            }
        }
    }

    test("native route constants and decisions match the recording") {
        val group = vectors.group("native").group("full")
        assertEquals(
            group.getValue("stage_tasks").jsonArray.map { it.jsonPrimitive.content },
            NativeFullContract.STAGE_TASKS,
        )
        assertEquals(
            group.getValue("test_tasks").jsonArray.map { it.jsonPrimitive.content },
            NativeFullContract.TEST_TASKS,
        )
        assertEquals(
            group.getValue("consumer_tasks").jsonArray.map { it.jsonPrimitive.content },
            NativeFullContract.CONSUMER_TASKS,
        )
        assertEquals(
            group.getValue("root_gradle").jsonArray.map { it.jsonPrimitive.content },
            NativeFullContract.ROOT_GRADLE,
        )
        assertEquals(
            group.getValue("assertions").jsonArray.map { it.jsonPrimitive.content },
            NativeReceipt.ASSERTIONS,
        )
        assertEquals(
            group.getValue("guest_properties").jsonObject.mapValues { it.value.jsonPrimitive.content },
            NativeReceipt.GUEST_PROPERTIES,
        )
        assertEquals(
            group.getValue("lanes").jsonArray.map { lane ->
                lane.jsonArray.map { it.jsonPrimitive.content }
            },
            NativeFullContract.LANES.map { listOf(it.first, it.second) },
        )
        for ((name, expected) in group.getValue("commands").jsonObject) {
            val argv = expected.jsonObject.mapValues { (_, value) ->
                value.jsonArray.map { it.jsonPrimitive.content }
            }
            val commands = if (name == "build") {
                NativeFullContract.buildCommands("/repo")
            } else {
                NativeFullContract.graphCommands("/repo")
            }
            assertEquals(argv, commands, name)
        }
        val executables = group.getValue("executables").jsonObject
        val klibs = group.getValue("klibs").jsonObject
        val remotes = group.getValue("guest_remote").jsonObject
        for ((module, variant) in NativeFullContract.LANES) {
            val key = "$module-$variant"
            assertEquals(
                executables.getValue(key).jsonPrimitive.content,
                NativeFullContract.executablePath("/repo", module, variant),
                key,
            )
            assertEquals(
                remotes.getValue(key).jsonPrimitive.content,
                NativeFullContract.GUEST_REMOTE.replace("{module}", module)
                    .replace("{variant}", variant),
                key,
            )
        }
        for ((module, expected) in klibs) {
            assertEquals(
                expected.jsonPrimitive.content,
                NativeFullContract.klibPaths("/repo").getValue(module),
            )
        }
        for ((name, expected) in group.getValue("build_task_marker").jsonArray.map { it.jsonObject }
            .associate { it.text("task") to it.text("value") }) {
            assertEquals(expected, NativeFullContract.buildTaskMarker(name))
        }
        for ((module, expected) in group.getValue("expected_cases").jsonObject) {
            val cases = when (module) {
                "core" -> listOf(
                    CorpusCase("org.dyn4j.CoreTest", "works", "dyn4k-core", "commonTest"),
                    CorpusCase("org.dyn4j.CoreTest", "jvmOnly", "dyn4k-core", "jvmTest"),
                )
                "facade" -> listOf(
                    CorpusCase("io.github.FacadeTest", "works", "dyn4k", "commonTest"),
                    CorpusCase("io.github.Core", "works", "dyn4k-core", "commonTest"),
                )
                else -> listOf(CorpusCase("io.github.FacadeTest", "works", "dyn4k", "commonTest"))
            }
            val target = if (module == "consumer-core") "core" else module
            assertEquals(
                expected.jsonArray.map { it.jsonPrimitive.content }.toSet(),
                NativeFullContract.expectedCases(cases, target),
                module,
            )
        }
        for (record in group.list("check_cases")) {
            val observed = record.getValue("observed").jsonArray.map { it.jsonPrimitive.content }
            val expected = record.strings("expected")
            assertVector(record.getValue("result"), "check cases") {
                JsonPrimitive(NativeFullContract.checkCases(observed, expected))
            }
        }
    }

    test("python json rendering matches the recording") {
        for (record in vectors.list("pyjson")) {
            // The input is re-parsed from its own text so the key order is the Python insertion order.
            val value = Json.parseToJsonElement(record.text("input"))
            assertEquals(record.text("pretty"), PyJson.prettySorted(value) + "\n")
            assertEquals(record.text("compact"), PyJson.compact(value))
        }
    }

    test("recorded revision is the ported reference") {
        assertTrue(Regex("[0-9a-f]{40}").matches(vectors.text("git_revision")))
    }
}

private const val FULL_VECTOR_CASE = "dyn4k-core:org.dyn4j.CoreTest#works"
private const val FULL_VECTOR_CONSUMER =
    "external-kotlin:io.github.rubixhacker.dyn4k.full.FullKotlinJourney#run"
