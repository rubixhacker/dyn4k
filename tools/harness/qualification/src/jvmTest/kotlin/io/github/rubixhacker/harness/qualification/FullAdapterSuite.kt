package io.github.rubixhacker.harness.qualification

import de.infix.testBalloon.framework.core.testSuite
import io.github.rubixhacker.harness.contract.Sha256
import java.nio.file.Files
import java.nio.file.Path
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

private fun adapterTemp(block: (Path) -> Unit) {
    val root = Files.createTempDirectory("full-adapter")
    try {
        block(root)
    } finally {
        Files.walk(root).use { walk ->
            walk.sorted(Comparator.reverseOrder()).forEach { Files.deleteIfExists(it) }
        }
    }
}

private fun assertMessageContains(expected: String, body: () -> Unit) {
    val error = assertFailsWith<IllegalArgumentException> { body() }
    assertTrue(
        (error.message ?: "").contains(expected),
        "expected '$expected' in '${error.message}'",
    )
}

/** `test_full_android_adapter.py`'s two cases that run without retained evidence. */
val FullAndroidAdapterSuite by testSuite {
    test("an unsupported lane fails without archive access") {
        assertMessageContains("does not cover lane") {
            FullAndroidAdapter.verify(
                Path.of("/missing"),
                "a".repeat(40),
                "android:Android JVM:minimum:other",
                JsonObject(emptyMap()),
                Path.of("/missing"),
                JsonObject(emptyMap()),
                JsonObject(emptyMap()),
            )
        }
    }

    test("a missing signed source digest fails without archive access") {
        val expected = buildJsonObject {
            put(
                "expected_artifact_hashes",
                buildJsonObject {
                    put("dyn4k-core", JsonPrimitive(ANDROID_CORE))
                    put("dyn4k", JsonPrimitive(ANDROID_FACADE))
                },
            )
            put("expected_runtime_identity", JsonPrimitive("a".repeat(64)))
            put(
                "expected_archive_digests",
                buildJsonObject { put("staged-consumer", JsonPrimitive("b".repeat(64))) },
            )
        }
        assertMessageContains("source/toolchain identity is incomplete") {
            FullAndroidAdapter.verify(
                Path.of("/missing"),
                "a".repeat(40),
                "android:Android JVM:minimum:debug",
                JsonObject(emptyMap()),
                Path.of("/missing"),
                expected,
                buildJsonObject {
                    put("gate", JsonPrimitive("staged-consumer"))
                    put("status", JsonPrimitive("PASSED"))
                    put("complete_selected_suite", JsonPrimitive(true))
                },
            )
        }
    }
}

private const val ANDROID_CORE =
    "9eaf8113aa62365b2ca0a4a9e5fe13615271ad2e22f3a8c414633ffcde824a53"
private const val ANDROID_FACADE =
    "352e3433ba8af93ad7ace849b0baa4abd35cf5262c8aead9109e9c140c8547ed"

private const val BROWSER_LANE = "js:Chromium:current:development"
private const val BROWSER_CANDIDATE = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
private val BROWSER_DIGEST = "b".repeat(64)
private val BROWSER_CORE = "c".repeat(64)
private val BROWSER_FACADE = "d".repeat(64)

/** `test_full_browser_adapter.py`: all eight cases. */
val FullBrowserAdapterSuite by testSuite {
    class Fixture(val archive: Path) {
        val bundleBytes = linkedMapOf(
            "core" to "independent core".toByteArray(),
            "facade" to "independent facade".toByteArray(),
        )
        val bundles = bundleBytes.mapValues { (_, raw) -> Sha256.of(raw) }
        val hashes = linkedMapOf("dyn4k-core" to BROWSER_CORE, "dyn4k" to BROWSER_FACADE)
        val toolchain = linkedMapOf<String, JsonElement>(
            "java_home" to JsonPrimitive(archive.resolve("jdk21").toString()),
            "java_version" to JsonPrimitive("openjdk version \"21.0.12\""),
            "java_sha256" to JsonPrimitive(FullBrowserAdapterRules.JAVA_SHA256),
            "gradle" to JsonPrimitive(archive.resolve("gradle").toString()),
            "gradle_sha256" to JsonPrimitive(FullBrowserAdapterRules.GRADLE_SHA256),
            "gradle_version" to JsonPrimitive("9.5.0"),
            "kgp_version" to JsonPrimitive("2.4.20"),
            "browser" to JsonPrimitive(archive.resolve("chrome").toString()),
            "browser_sha256" to JsonPrimitive(
                FullBrowserAdapterRules.CHROMIUM.getValue("current").second,
            ),
            "browser_version" to JsonPrimitive("Google Chrome for Testing 155.0.1.0"),
            "gradle_user_home" to JsonPrimitive(archive.resolve("gradle-home").toString()),
        )
        val expected: JsonObject = buildJsonObject {
            put(
                "expected_artifact_hashes",
                JsonObject(hashes.mapValues { JsonPrimitive(it.value) }),
            )
            put(
                "expected_archive_digests",
                buildJsonObject { put("staged-consumer", JsonPrimitive(BROWSER_DIGEST)) },
            )
            put("expected_runtime_identity", JsonPrimitive("Linux trusted x86_64"))
            put("expected_browser_toolchain", JsonObject(toolchain))
            put(
                "expected_browser_bundles",
                JsonObject(bundles.mapValues { JsonPrimitive(it.value) }),
            )
        }
        val gate: JsonObject = buildJsonObject {
            put("gate", JsonPrimitive("staged-consumer"))
            put("status", JsonPrimitive("PASSED"))
            put("complete_selected_suite", JsonPrimitive(true))
            put("selected_cases", JsonPrimitive(2))
            put("archive_sha256", JsonPrimitive(BROWSER_DIGEST))
        }
        var public: JsonObject = buildJsonObject {
            put("status", JsonPrimitive("PASSED"))
            put("lane", JsonPrimitive(BROWSER_LANE))
            put("selected_cases", JsonPrimitive(2))
            put("archive_sha256", JsonPrimitive(BROWSER_DIGEST))
            put("candidate_sha", JsonPrimitive(BROWSER_CANDIDATE))
        }

        init {
            for ((short, raw) in bundleBytes) {
                val folder = archive.resolve(short)
                Files.createDirectories(folder)
                for (name in listOf("karma-selected.js", "linked-executable.js")) {
                    Files.write(folder.resolve(name), raw)
                }
            }
        }

        fun call(
            repository: Path = archive,
            candidateSha: String = BROWSER_CANDIDATE,
            laneId: String = BROWSER_LANE,
            selected: JsonObject = buildJsonObject {
                put("case_ids", JsonArray(listOf(JsonPrimitive("one"), JsonPrimitive("two"))))
            },
            archivePath: Path = archive,
            expected: JsonObject = this.expected,
            gateResult: JsonObject = this.gate,
            auditedTargetHashes: JsonObject = JsonObject(hashes.mapValues { JsonPrimitive(it.value) }),
            observedDigest: String = BROWSER_DIGEST,
            receipt: JsonObject = buildJsonObject {
                put("runtime_identity", JsonPrimitive("Linux trusted x86_64"))
                put("toolchain", JsonObject(toolchain))
            },
            executables: Boolean = false,
        ): Pair<JsonObject, Int> {
            val port = object : FullBrowserConsumerPort by FullBrowserConsumerUnavailable {
                var calls = 0
                override fun contract(repository: Path, laneId: String): JsonObject =
                    buildJsonObject {
                        put(
                            "cases",
                            JsonArray(
                                listOf(
                                    buildJsonObject { put("id", JsonPrimitive("one")) },
                                    buildJsonObject { put("id", JsonPrimitive("two")) },
                                ),
                            ),
                        )
                    }
                override fun verify(
                    repository: Path,
                    candidateSha: String,
                    laneId: String,
                    archive: Path,
                    archiveDigest: String,
                    browser: Path,
                    hashes: JsonObject,
                ): JsonObject {
                    calls += 1
                    return public
                }
                override fun archiveDigest(archive: Path): String = observedDigest
                override fun json(path: Path): JsonElement = receipt
            }
            val result = FullBrowserAdapter.verify(
                repository,
                candidateSha,
                laneId,
                selected,
                archivePath,
                expected,
                gateResult,
                auditedTargetHashes,
                port,
                executable = { _, _, _ -> if (executables) error("unexpected executable check") },
            )
            return result to port.calls
        }
    }

    test("a positive signed binding calls the public replay once") {
        adapterTemp { root ->
            val fixture = Fixture(root)
            val (result, count) = fixture.call()
            assertEquals(fixture.public, result)
            assertEquals(1, count)
        }
    }

    test("a wrong lane, candidate, or case set is rejected") {
        adapterTemp { root ->
            val fixture = Fixture(root)
            for (change in listOf(
                "lane" to "js:Chromium:foreign:development",
                "candidate" to "short",
                "cases" to "reversed",
            )) {
                val error = assertFailsWith<IllegalArgumentException> {
                    when (change.first) {
                        "lane" -> fixture.call(laneId = change.second)
                        "candidate" -> fixture.call(candidateSha = change.second)
                        else -> fixture.call(
                            selected = buildJsonObject {
                                put(
                                    "case_ids",
                                    JsonArray(
                                        listOf(JsonPrimitive("two"), JsonPrimitive("one")),
                                    ),
                                )
                            },
                        )
                    }
                }
                assertTrue((error.message ?: "").isNotEmpty())
            }
        }
    }

    test("signed artifact, runtime, archive, and gate mismatches are rejected") {
        adapterTemp { root ->
            val fixture = Fixture(root)
            val expectedChanges = listOf(
                buildJsonObject {
                    put(
                        "expected_artifact_hashes",
                        buildJsonObject { put("dyn4k-core", JsonPrimitive(BROWSER_CORE)) },
                    )
                },
                buildJsonObject { put("expected_runtime_identity", JsonPrimitive("")) },
                buildJsonObject {
                    put(
                        "expected_archive_digests",
                        buildJsonObject { put("staged-consumer", JsonPrimitive("e".repeat(64))) },
                    )
                },
                buildJsonObject {
                    put(
                        "expected_browser_bundles",
                        buildJsonObject {
                            put("core", JsonPrimitive("f".repeat(64)))
                            put("facade", JsonPrimitive(fixture.bundles.getValue("facade")))
                        },
                    )
                },
            )
            for (change in expectedChanges) {
                val changed = JsonObject(LinkedHashMap(fixture.expected).apply {
                    for ((key, value) in change) this[key] = value
                })
                assertFailsWith<IllegalArgumentException> { fixture.call(expected = changed) }
            }
            val gateChanges = listOf(
                "status" to JsonPrimitive("NOT_RUN"),
                "gate" to JsonPrimitive("other"),
                "complete_selected_suite" to JsonPrimitive(false),
                "selected_cases" to JsonPrimitive(1),
                "archive_sha256" to JsonPrimitive("e".repeat(64)),
            )
            for ((key, value) in gateChanges) {
                val changed = JsonObject(LinkedHashMap(fixture.gate).apply { this[key] = value })
                assertFailsWith<IllegalArgumentException> { fixture.call(gateResult = changed) }
            }
            assertFailsWith<IllegalArgumentException> {
                fixture.call(
                    auditedTargetHashes = buildJsonObject {
                        put("dyn4k-core", JsonPrimitive("e".repeat(64)))
                        put("dyn4k", JsonPrimitive(BROWSER_FACADE))
                    },
                )
            }
        }
    }

    test("a resealed selected or linked copy is rejected") {
        adapterTemp { root ->
            val fixture = Fixture(root)
            for (name in listOf("karma-selected.js", "linked-executable.js")) {
                Files.writeString(
                    root.resolve("core").resolve(name),
                    "producer resealed copy",
                )
            }
            assertMessageContains("independent signed hash") { fixture.call() }
        }
    }

    test("a wrong signed toolchain or browser role is rejected") {
        adapterTemp { root ->
            val fixture = Fixture(root)
            for ((key, value) in listOf(
                "browser_sha256" to JsonPrimitive("e".repeat(64)),
                "gradle_sha256" to JsonPrimitive("e".repeat(64)),
                "browser" to JsonPrimitive("relative/chrome"),
                "browser_version" to JsonPrimitive("Google Chrome 119.0.1"),
            )) {
                val toolchain = LinkedHashMap(fixture.toolchain).apply { this[key] = value }
                val expected = JsonObject(
                    LinkedHashMap(fixture.expected).apply {
                        this["expected_browser_toolchain"] = JsonObject(toolchain)
                    },
                )
                assertFailsWith<IllegalArgumentException> { fixture.call(expected = expected) }
            }
        }
    }

    test("executable bytes must match the signed hash") {
        adapterTemp { root ->
            val executable = root.resolve("browser")
            Files.writeString(executable, "selected Chromium executable")
            val digest = Sha256.of(Files.readAllBytes(executable))
            FullBrowserAdapter.executableBytes(executable, digest, "Chromium")
            Files.writeString(executable, "different Chromium executable")
            assertMessageContains("executable bytes differ") {
                FullBrowserAdapter.executableBytes(executable, digest, "Chromium")
            }
        }
    }

    test("archive digest and runtime receipt mismatches are rejected") {
        adapterTemp { root ->
            val fixture = Fixture(root)
            assertMessageContains("archive digest differs") {
                fixture.call(observedDigest = "e".repeat(64))
            }
            assertMessageContains("runtime or toolchain differs") {
                fixture.call(
                    receipt = buildJsonObject {
                        put("runtime_identity", JsonPrimitive("other"))
                        put("toolchain", JsonObject(fixture.toolchain))
                    },
                )
            }
        }
    }

    test("a public result mismatch is rejected") {
        adapterTemp { root ->
            val fixture = Fixture(root)
            fixture.public = JsonObject(
                LinkedHashMap(fixture.public).apply {
                    this["selected_cases"] = JsonPrimitive(1)
                },
            )
            assertMessageContains("public browser verifier differs") { fixture.call() }
        }
    }
}

private const val KLIB_CANDIDATE = "d629b9e388db08b3c7e24b22ff853ac387b951ce"

/** `test_full_klib_adapter.py`'s two cases that run without retained evidence. */
val FullKlibAdapterSuite by testSuite {
    test("an unsupported lane is rejected before public dispatch") {
        val port = object : FullKlibConsumerPort by FullKlibConsumerUnavailable {
            var called = false
            override fun verify(
                root: Path,
                repository: Path,
                candidateSha: String,
                laneId: String,
                hashes: JsonObject,
                runtime: String,
                archiveDigest: String,
                trusted: JsonObject,
                replayNode: String?,
            ): JsonObject {
                called = true
                return JsonObject(emptyMap())
            }
        }
        assertMessageContains("does not cover lane") {
            FullKlibAdapter.verify(
                Path.of("."),
                KLIB_CANDIDATE,
                "js:browser:current:development",
                emptyList(),
                Path.of("/unused"),
                buildJsonObject { put("status", JsonPrimitive("PASSED")) },
                JsonObject(emptyMap()),
                JsonObject(emptyMap()),
                port,
            )
        }
        assertEquals(false, port.called)
    }

    test("a generic result mismatch is rejected") {
        val port = object : FullKlibConsumerPort by FullKlibConsumerUnavailable {
            override fun contract(repository: Path, laneId: String): Pair<JsonObject?, JsonObject> =
                null to buildJsonObject {
                    put(
                        "cases",
                        JsonArray(listOf(buildJsonObject { put("id", JsonPrimitive("case")) })),
                    )
                }
            override fun archiveDigest(archive: Path): String = "a".repeat(64)
            override fun verify(
                root: Path,
                repository: Path,
                candidateSha: String,
                laneId: String,
                hashes: JsonObject,
                runtime: String,
                archiveDigest: String,
                trusted: JsonObject,
                replayNode: String?,
            ): JsonObject = buildJsonObject { put("status", JsonPrimitive("PASSED")) }
        }
        val expected = buildJsonObject {
            put(
                "expected_artifact_hashes",
                buildJsonObject {
                    put("dyn4k-core", JsonPrimitive("b".repeat(64)))
                    put("dyn4k", JsonPrimitive("c".repeat(64)))
                },
            )
            put("expected_runtime_identity", JsonPrimitive("runtime"))
            put(
                "expected_archive_digests",
                buildJsonObject { put("staged-consumer", JsonPrimitive("a".repeat(64))) },
            )
        }
        assertMessageContains("differs from independent gate") {
            FullKlibAdapter.verify(
                Path.of("."),
                KLIB_CANDIDATE,
                "js:Node.js:current:development",
                listOf("case"),
                Path.of("/archive"),
                buildJsonObject {
                    put("status", JsonPrimitive("PASSED"))
                    put("archive_sha256", JsonPrimitive("wrong"))
                },
                expected,
                expected.getValue("expected_artifact_hashes"),
                port,
                trusted = { _, _ -> JsonObject(emptyMap()) to Path.of("/node") },
            )
        }
    }
}

/** The adapter rule tables are the consumer literals, pinned against the Python implementation. */
val FullAdapterRulesSuite by testSuite {
    test("the pinned adapter tables match the Python implementation") {
        val vector = FullAdapterVectors
        assertEquals(vector.ANDROID_MODULES, FullAndroidAdapterRules.MODULES)
        assertEquals(vector.ANDROID_ROUTES, FullAndroidAdapterRules.ROUTES)
        assertEquals(vector.BROWSER_MODULES, FullBrowserAdapterRules.MODULES)
        assertEquals(vector.BROWSER_JAVA_SHA256, FullBrowserAdapterRules.JAVA_SHA256)
        assertEquals(vector.BROWSER_GRADLE_SHA256, FullBrowserAdapterRules.GRADLE_SHA256)
        assertEquals(vector.BROWSER_CHROMIUM, FullBrowserAdapterRules.CHROMIUM)
        assertEquals(vector.BROWSER_LANES, FullBrowserAdapterRules.LANES)
        assertEquals(vector.BROWSER_TOOLCHAIN_KEYS, FullBrowserAdapterRules.TOOLCHAIN_KEYS)
        assertEquals(vector.KLIB_MODULES, FullKlibAdapterRules.MODULES)
        assertEquals(vector.KLIB_LOCAL_LANES, FullKlibAdapterRules.LOCAL_LANES)
        assertEquals(vector.KLIB_TOOLCHAIN_KEYS, FullKlibAdapterRules.TOOLCHAIN_KEYS)
        assertEquals(vector.KLIB_NATIVE_KEYS, FullKlibAdapterRules.NATIVE_KEYS)
    }
}
