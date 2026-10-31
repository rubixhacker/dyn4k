package io.github.rubixhacker.harness.qualification

import de.infix.testBalloon.framework.core.TestConfig
import de.infix.testBalloon.framework.core.disable
import de.infix.testBalloon.framework.core.testSuite
import io.github.rubixhacker.harness.contract.CanonicalJson
import io.github.rubixhacker.harness.contract.Sha256
import io.github.rubixhacker.harness.contract.StrictJson
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.StandardCopyOption
import java.util.concurrent.TimeUnit
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

/**
 * The retained-evidence gate: the reference's `@unittest.skipUnless(...)`.
 *
 * A suite or test registered with `TestConfig.disable` is reported as disabled and never runs, so
 * an absent variable can never look like a pass. When the variable is present the test runs and
 * fails loudly on malformed evidence.
 */
internal fun retainedEvidenceConfig(name: String): TestConfig {
    val value = System.getenv(name)
    return if (value.isNullOrBlank()) TestConfig.disable() else TestConfig
}

private fun sha256(path: Path): String = Sha256.of(Files.readAllBytes(path))

/** `test_full_staged_consumer.py`'s fixture builder: one JUnit report. */
internal fun stagedReport(names: List<String>, skipped: Boolean = false): ByteArray {
    val suite = buildString {
        append("<testsuite tests=\"").append(names.size)
            .append("\" failures=\"0\" errors=\"0\" skipped=\"")
            .append(if (skipped) "1" else "0").append("\" time=\"0.2\">")
        for ((index, name) in names.withIndex()) {
            append("<testcase classname=\"")
                .append(FullStagedConsumerRules.CLASS)
                .append("\" name=\"").append(name).append("[jvm]\" time=\"0.1\"")
            if (skipped && index == 0) {
                append("><skipped/></testcase>")
            } else {
                append("/>")
            }
        }
        append("</testsuite>")
    }
    return suite.toByteArray()
}

private val STAGED_IDS = setOf("dyn4k-core:${FullStagedConsumerRules.CLASS}#first",
    "dyn4k-core:${FullStagedConsumerRules.CLASS}#second")

/** `test_full_staged_consumer.py`: the four self-contained contract cases. */
val FullStagedConsumerContract by testSuite {
    test("exact raw cases") {
        assertEquals(
            STAGED_IDS,
            FullStagedConsumer.rawCaseIds(stagedReport(listOf("first", "second")), STAGED_IDS),
        )
    }

    test("missing, duplicate, foreign, and skipped raw cases are rejected") {
        for ((names, skipped) in listOf(
            listOf("first") to false,
            listOf("first", "first") to false,
            listOf("first", "foreign") to false,
            listOf("first", "second") to true,
        )) {
            assertFailsWith<IllegalArgumentException> {
                FullStagedConsumer.rawCaseIds(stagedReport(names, skipped), STAGED_IDS)
            }
        }
    }

    test("the original test source must be in the approved manifest") {
        val manifest = buildJsonObject {
            put(
                "lanes",
                buildJsonObject {
                    put(
                        FullStagedConsumerRules.LANE,
                        buildJsonObject {
                            put(
                                "case_scopes",
                                JsonArray(
                                    listOf(JsonPrimitive("portable"), JsonPrimitive("jvm")),
                                ),
                            )
                            put("target", JsonPrimitive("jvm"))
                            put("runtime", JsonPrimitive("Java"))
                            put("version", JsonPrimitive("current"))
                            put("configuration", JsonPrimitive("default"))
                        },
                    )
                },
            )
            put(
                "cases",
                JsonArray(
                    STAGED_IDS.sorted().map { caseId ->
                        buildJsonObject {
                            put("id", JsonPrimitive(caseId))
                            put("classname", JsonPrimitive(FullStagedConsumerRules.CLASS))
                            put("method", JsonPrimitive(caseId.split("#").last()))
                            put("module", JsonPrimitive("dyn4k-core"))
                            put("scope", JsonPrimitive("portable"))
                            put(
                                "source",
                                buildJsonObject {
                                    put("path", JsonPrimitive(FullStagedConsumerRules.SOURCE))
                                    put("sha256", JsonPrimitive("a".repeat(64)))
                                },
                            )
                        }
                    },
                ),
            )
        }
        assertEquals(
            STAGED_IDS,
            FullStagedConsumer.classContract(
                manifest,
                FullStagedConsumerRules.LANE,
                FullStagedConsumerRules.CLASS,
            ).ids,
        )
        val changed = StrictJson.load(manifest.toString()) as JsonObject
        val cases = (changed["cases"] as JsonArray).toMutableList()
        val first = LinkedHashMap(cases[0] as JsonObject)
        first["source"] = buildJsonObject {
            put("path", JsonPrimitive("other.kt"))
            put("sha256", JsonPrimitive("a".repeat(64)))
        }
        cases[0] = JsonObject(first)
        val mutated = LinkedHashMap(changed).apply { this["cases"] = JsonArray(cases) }
        assertFailsWith<IllegalArgumentException> {
            FullStagedConsumer.classContract(
                JsonObject(mutated),
                FullStagedConsumerRules.LANE,
                FullStagedConsumerRules.CLASS,
            )
        }
    }

    test("the graph rejects source, build, substitution, and provider changes") {
        val stage = Path.of(System.getProperty("java.io.tmpdir")).toAbsolutePath().normalize()
            .resolve("staging")
        val hashes = mapOf("dyn4k-core" to "a".repeat(64), "dyn4k" to "b".repeat(64))
        val artifacts = FullStagedConsumerRules.MODULES.map { module ->
            val path = FullStagedConsumer.stagedBinary(stage, module)
            buildJsonObject {
                put(
                    "component",
                    JsonPrimitive(
                        "${FullStagedConsumerRules.GROUP}:$module-jvm:" +
                            FullStagedConsumerRules.VERSION,
                    ),
                )
                put("file", JsonPrimitive(path.toString()))
                put("name", JsonPrimitive(path.fileName.toString()))
                put("size", JsonPrimitive(1))
                put("sha256", JsonPrimitive(hashes.getValue(module)))
            }
        }
        val components = artifacts.map { (it["component"] as JsonPrimitive).content } +
            FullStagedConsumerRules.MODULES.map {
                "${FullStagedConsumerRules.GROUP}:$it:${FullStagedConsumerRules.VERSION}"
            }
        val graph = buildJsonObject {
            put("configuration", JsonPrimitive("jvmTestRuntimeClasspath"))
            put("artifacts", JsonArray(artifacts))
            put("components", JsonArray(components.map { JsonPrimitive(it) }))
        }
        assertEquals(
            FullStagedConsumerRules.MODULES.toSet(),
            FullStagedConsumer.graphArtifacts(graph, stage, hashes).keys,
        )
        val changes = listOf(
            "file" to (stage.resolve("checkout/dyn4k-core/build/libs/dyn4k-core-jvm.jar").toString()),
            "component" to "org.dyn4j:dyn4j:6.0.0",
            "sha256" to "c".repeat(64),
        )
        for ((field, value) in changes) {
            val first = LinkedHashMap(artifacts[0])
            first[field] = JsonPrimitive(value)
            val changed = LinkedHashMap(graph).apply {
                this["artifacts"] = JsonArray(listOf(JsonObject(first), artifacts[1]))
            }
            assertFailsWith<IllegalArgumentException> {
                FullStagedConsumer.graphArtifacts(JsonObject(changed), stage, hashes)
            }
        }
        val duplicated = LinkedHashMap(graph).apply {
            this["artifacts"] = JsonArray(artifacts + listOf(artifacts[0]))
        }
        assertFailsWith<IllegalArgumentException> {
            FullStagedConsumer.graphArtifacts(JsonObject(duplicated), stage, hashes)
        }
    }
}

/**
 * `test_full_staged_consumer.py`'s three retained-archive cases.
 *
 * They need `DYN4K_SUITE_ARCHIVE`, `DYN4K_SUITE_REPOSITORY`, `DYN4K_SUITE_EXPECTED_CORE`, and
 * `DYN4K_SUITE_EXPECTED_FACADE`, which the reference reads in `setUp`; a bare host registers and
 * disables them.
 */
val FullStagedConsumerRetained by testSuite {
    val config = retainedEvidenceConfig("DYN4K_SUITE_ARCHIVE")

    test("the public positive replays and an independent hash negative fails", config) {
        val fixture = RetainedStagedFixture()
        try {
            assertEquals("NOT_RUN", Py.str(FullStagedConsumer.verify(
                fixture.archive,
                fixture.repository,
                fixture.hashes,
            )["status"]))
            assertFailsWith<IllegalArgumentException> {
                FullStagedConsumer.verify(
                    fixture.archive,
                    fixture.repository,
                    fixture.hashes + ("dyn4k-core" to "0".repeat(64)),
                )
            }
        } finally {
            fixture.cleanup()
        }
    }

    test("resealed missing, duplicate, foreign, and skipped XML are rejected", config) {
        val fixture = RetainedStagedFixture()
        try {
            for (mutation in listOf("missing", "duplicate", "foreign", "skipped")) {
                fixture.reset()
                val xml = fixture.archive.resolve("raw/TEST-${FullStagedConsumerRules.CLASS}.xml")
                val text = Files.readString(xml)
                val mutated = when (mutation) {
                    "missing" -> text.replaceFirst(Regex("<testcase[^>]*/>"), "")
                    "duplicate" -> text.replaceFirst(
                        Regex("(<testcase[^>]*/>)"),
                        "$1" + Regex("<testcase[^>]*/>").find(text)!!.value,
                    )
                    "foreign" -> text.replaceFirst("name=\"", "name=\"foreign-")
                    else -> text.replaceFirst(
                        Regex("<testcase[^>]*/>"),
                        "<testcase classname=\"${FullStagedConsumerRules.CLASS}\" " +
                            "name=\"first[jvm]\" time=\"0.1\"><skipped/></testcase>",
                    ).replaceFirst("skipped=\"0\"", "skipped=\"1\"")
                }
                Files.writeString(xml, mutated)
                fixture.reseal()
                assertFailsWith<IllegalArgumentException>(mutation) {
                    FullStagedConsumer.verify(fixture.archive, fixture.repository, fixture.hashes)
                }
            }
        } finally {
            fixture.cleanup()
        }
    }

    test("resealed source, build, graph, and binary substitution are rejected", config) {
        val fixture = RetainedStagedFixture()
        try {
            for (mutation in listOf("graph", "binary", "candidate")) {
                fixture.reset()
                val receiptPath = fixture.archive.resolve("receipt.json")
                val receipt = StrictJson.load(Files.readString(receiptPath)) as JsonObject
                when (mutation) {
                    "graph" -> {
                        val graphStdout = fixture.archive.resolve("raw/graph.stdout")
                        val text = Files.readString(graphStdout)
                        Files.writeString(
                            graphStdout,
                            text.replace("\"jvmTestRuntimeClasspath\"", "\"other\""),
                        )
                    }
                    "binary" -> {
                        val name = FullStagedConsumerRules.stagedBinaryName("dyn4k-core")
                        Files.write(fixture.archive.resolve("resolved").resolve(name), byteArrayOf(1))
                    }
                    else -> {
                        val changed = LinkedHashMap(receipt).apply {
                            this["candidate_sha"] = JsonPrimitive("0".repeat(40))
                        }
                        Files.writeString(receiptPath, JsonObject(changed).toString())
                    }
                }
                fixture.reseal()
                assertFailsWith<IllegalArgumentException>(mutation) {
                    FullStagedConsumer.verify(fixture.archive, fixture.repository, fixture.hashes)
                }
            }
        } finally {
            fixture.cleanup()
        }
    }
}

/** The reference `setUp`: a private copy of the retained archive plus its repository and hashes. */
private class RetainedStagedFixture {
    val source: Path = Path.of(System.getenv("DYN4K_SUITE_ARCHIVE")!!)
    val repository: Path = Path.of(
        System.getenv("DYN4K_SUITE_REPOSITORY")
            ?: throw AssertionError("DYN4K_SUITE_REPOSITORY is required with DYN4K_SUITE_ARCHIVE"),
    )
    val hashes: Map<String, String> = mapOf(
        "dyn4k-core" to (
            System.getenv("DYN4K_SUITE_EXPECTED_CORE")
                ?: throw AssertionError(
                    "DYN4K_SUITE_EXPECTED_CORE is required with DYN4K_SUITE_ARCHIVE",
                )
            ),
        "dyn4k" to (
            System.getenv("DYN4K_SUITE_EXPECTED_FACADE")
                ?: throw AssertionError(
                    "DYN4K_SUITE_EXPECTED_FACADE is required with DYN4K_SUITE_ARCHIVE",
                )
            ),
    )
    val root: Path = Files.createTempDirectory("full-staged-consumer")
    val archive: Path = root.resolve("archive")

    init {
        copyTree(source, archive)
    }

    fun reset() {
        deleteTree(archive)
        copyTree(source, archive)
    }

    /** `reseal`: recompute the file inventory and the seal over the mutated archive. */
    fun reseal() {
        val path = archive.resolve("receipt.json")
        val receipt = LinkedHashMap(
            StrictJson.load(Files.readString(path)) as JsonObject,
        )
        receipt.remove("seal_sha256")
        receipt["files"] = FullStagedConsumer.inventory(archive)
        receipt["seal_sha256"] = JsonPrimitive(
            FullStagedConsumer.sha(FullStagedConsumer.encoded(JsonObject(receipt))),
        )
        Files.write(
            path,
            FullStagedConsumer.encoded(JsonObject(receipt)) + "\n".toByteArray(),
        )
    }

    fun cleanup() {
        deleteTree(root)
    }
}

private fun copyTree(source: Path, destination: Path) {
    Files.walk(source).use { walk ->
        walk.forEach { path ->
            val target = destination.resolve(source.relativize(path).toString())
            if (Files.isDirectory(path)) {
                Files.createDirectories(target)
            } else {
                target.parent?.let { Files.createDirectories(it) }
                Files.copy(path, target, StandardCopyOption.COPY_ATTRIBUTES)
            }
        }
    }
}

private fun deleteTree(root: Path) {
    if (!Files.exists(root)) return
    Files.walk(root).use { walk ->
        walk.sorted(Comparator.reverseOrder()).forEach { Files.deleteIfExists(it) }
    }
}
