package io.github.rubixhacker.harness.performance

import de.infix.testBalloon.framework.core.testSuite
import io.github.rubixhacker.harness.contract.Sha256
import io.github.rubixhacker.harness.contract.StrictJson
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.put
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith

private const val STAND_IN_TOOL_DIGEST_SOURCE = "reference-study-stand-in"

/**
 * A synthetic legacy-version reference study, so the archive's structural rules can be replayed
 * without the twelve version 3 sidecars. The version 2 schema shares every rule except the
 * observer and clock checks that `ReferenceStudy.validateV3Capture` adds.
 */
private class LegacyStudyFixture {
    val root = "/study"
    val files = MemoryFileSystem()
    val manifestBytes: ByteArray = CheckedInManifest.bytes
    val toolDigest: String = Sha256.of(STAND_IN_TOOL_DIGEST_SOURCE)
    val context: JsonObject
    val selectedKey: String
    private var serial = 0

    init {
        val (computed, keys) = ReferenceStudy.policyContext(
            ReferenceStudy.LEGACY_VERSION,
            manifestBytes,
            toolDigest,
        )
        context = computed
        selectedKey = keys.sorted().first { key -> key.startsWith("absolute_timing|js.node|") }
    }

    /** One control record whose four identity files exist in the in-memory archive. */
    fun control(rowId: String = "js.node", controlId: String = "row_reference_self"): JsonObject {
        val route = ReferenceStudy.controlRoutes.getValue(controlId)
        return buildJsonObject {
            put("row_id", rowId)
            put("control_id", controlId)
            put("route", route)
            put("host_id", "synthetic-host")
            put("boot_id", "synthetic-boot")
            for (name in ReferenceStudy.identityFiles) {
                val relative = "inputs/0-$name.bin"
                files.write("$root/$relative", "$name-fixed-study-input")
                put(name + "_path", relative)
                put(name + "_sha256", Sha256.of(files.readBytes("$root/$relative")))
            }
        }
    }

    fun protocol(
        control: JsonObject,
        key: String = selectedKey,
        controls: List<String>? = null,
        version: String = ReferenceStudy.LEGACY_VERSION,
    ): JsonObject = buildJsonObject {
        put(
            "context",
            if (version == ReferenceStudy.LEGACY_VERSION) {
                context
            } else {
                ReferenceStudy.policyContext(version, manifestBytes, toolDigest).first
            },
        )
        put(
            "assignments",
            JsonArray(
                listOf(
                    buildJsonObject {
                        put("phase", "source")
                        put("key", key)
                        put(
                            "controls",
                            JsonArray((controls ?: ReferenceStudy.controlsFor(key)).map { JsonPrimitive(it) }),
                        )
                    },
                ),
            ),
        )
        put("controls", JsonArray(listOf(control)))
        put("signature", "stand-in")
    }

    /** The six captures one assignment declares, with consistent sidecars and raw files. */
    fun captures(key: String = selectedKey): MutableList<JsonObject> {
        val output = mutableListOf<JsonObject>()
        val kinds = ReferenceStudy.rawFilesFor(ReferenceStudy.LEGACY_VERSION)
        for ((pairIndex, sides) in ReferenceStudy.pairOrder.withIndex()) {
            for ((orderIndex, side) in sides.withIndex()) {
                serial += 1
                val ordinal = output.size
                val capture = linkedMapOf<String, JsonElement>()
                capture["phase"] = JsonPrimitive("source")
                capture["key"] = JsonPrimitive(key)
                capture["control_id"] = JsonPrimitive("row_reference_self")
                capture["row_id"] = JsonPrimitive(key.split("|")[1])
                capture["route"] = JsonPrimitive("direct_kotlin")
                capture["host_id"] = JsonPrimitive("synthetic-host")
                capture["boot_id"] = JsonPrimitive("synthetic-boot")
                capture["pair"] = JsonPrimitive(pairIndex + 1)
                capture["side"] = JsonPrimitive(side)
                capture["order"] = JsonPrimitive(orderIndex + 1)
                capture["process_id"] = JsonPrimitive("study-process-$serial")
                capture["run_id"] = JsonPrimitive("study-run-$serial")
                capture["os_pid"] = JsonPrimitive(1000 + serial)
                capture["process_start_id"] = JsonPrimitive("os-start-$serial")
                capture["started_ns"] = JsonPrimitive(1_000_000L + serial * 10_000L)
                capture["ended_ns"] = JsonPrimitive(1_000_500L + serial * 10_000L)
                capture["invalid_reason"] = JsonNull
                capture["stop_reason"] = JsonPrimitive("completed")
                for (name in ReferenceStudy.identityFiles) {
                    capture[name + "_sha256"] = JsonPrimitive(Sha256.of("$name-fixed-study-input"))
                }
                for (kind in kinds) {
                    val relative = "raw/$ordinal-$kind.bin"
                    files.write("$root/$relative", "$kind-$serial")
                    capture[kind + "_path"] = JsonPrimitive(relative)
                    capture[kind + "_sha256"] = JsonPrimitive(Sha256.of(files.readBytes("$root/$relative")))
                }
                output.add(JsonObject(capture))
            }
        }
        return output
    }

    fun validate(protocol: JsonObject, captures: List<JsonObject>): Int =
        ReferenceStudy.validateCaptures(files, root, protocol, JsonArray(captures), manifestBytes, toolDigest)

    fun protocolValidation(protocol: JsonObject) =
        ReferenceStudy.validateProtocol(protocol, files, root, manifestBytes, toolDigest)
}

private fun legacyFixture(): LegacyStudyFixture = LegacyStudyFixture()

private fun JsonObject.replaced(vararg changes: Pair<String, JsonElement>): JsonObject {
    val copy = LinkedHashMap(this)
    for ((key, value) in changes) copy[key] = value
    return JsonObject(copy)
}

private fun JsonObject.without(key: String): JsonObject {
    val copy = LinkedHashMap(this)
    copy.remove(key)
    return JsonObject(copy)
}

private fun failureOf(block: () -> Unit): String =
    assertFailsWith<IllegalArgumentException> { block() }.message ?: ""

/** The cases of `tools/performance/test_reference_study.py` that need no version 3 sidecars. */
val ReferenceStudyArchiveCases by testSuite {
    test("the signed legacy positive verifies and reports the declared assignment count") {
        val fixture = legacyFixture()
        val protocol = fixture.protocol(fixture.control())
        assertEquals(1, fixture.validate(protocol, fixture.captures()))
    }

    test("rejects overlapping same-host PID intervals") {
        val fixture = legacyFixture()
        val protocol = fixture.protocol(fixture.control())
        val rows = fixture.captures()
        val first = rows[0]
        val started = first.long("started_ns")
        val ended = first.long("ended_ns")
        rows[1] = rows[1].replaced(
            "os_pid" to first.getValue("os_pid"),
            "started_ns" to JsonPrimitive(started + 1),
            "ended_ns" to JsonPrimitive(ended + 1),
        )
        assertEquals(
            "overlapping observed host/PID intervals",
            failureOf { fixture.validate(protocol, rows) },
        )
    }

    test("allows non-overlapping same-host PID intervals") {
        val fixture = legacyFixture()
        val protocol = fixture.protocol(fixture.control())
        val rows = fixture.captures()
        rows[1] = rows[1].replaced("os_pid" to rows[0].getValue("os_pid"))
        assertEquals(1, fixture.validate(protocol, rows))
    }

    test("requires the declared boot and process start") {
        val fixture = legacyFixture()
        val protocol = fixture.protocol(fixture.control())

        val bootChanged = fixture.captures()
        bootChanged[0] = bootChanged[0].replaced("boot_id" to JsonPrimitive("another-boot"))
        assertEquals(
            "capture route, host, or boot differs",
            failureOf { fixture.validate(protocol, bootChanged) },
        )

        val noStart = fixture.captures()
        noStart[0] = noStart[0].replaced("process_start_id" to JsonPrimitive(""))
        assertEquals(
            "invalid process identity or interval",
            failureOf { fixture.validate(protocol, noStart) },
        )

        val noBoot = fixture.captures()
        noBoot[0] = noBoot[0].without("boot_id")
        assertEquals(
            "capture keys differ",
            failureOf { fixture.validate(protocol, noBoot) },
        )
    }

    test("resigned index rejects a raw path collision with equal bytes") {
        val fixture = legacyFixture()
        val protocol = fixture.protocol(fixture.control())
        val rows = fixture.captures()
        rows[1] = rows[1].replaced(
            "series_path" to rows[0].getValue("series_path"),
            "series_sha256" to rows[0].getValue("series_sha256"),
        )
        assertEquals("raw archive path reused", failureOf { fixture.validate(protocol, rows) })
    }

    test("resigned index rejects the protocol or a control file as raw") {
        val fixture = legacyFixture()
        val protocol = fixture.protocol(fixture.control())
        for (path in listOf("protocol.json", "inputs/0-artifact.bin")) {
            val rows = fixture.captures()
            rows[0] = rows[0].replaced("series_path" to JsonPrimitive(path))
            assertEquals(
                "capture raw path must be under raw/",
                failureOf { fixture.validate(protocol, rows) },
            )
        }
    }

    test("resigned index rejects a raw hard link to another capture") {
        val fixture = legacyFixture()
        val protocol = fixture.protocol(fixture.control())
        val rows = fixture.captures()
        fixture.files.link("${fixture.root}/raw/0-series.bin", "${fixture.root}/raw/linked.bin")
        rows[1] = rows[1].replaced(
            "series_path" to JsonPrimitive("raw/linked.bin"),
            "series_sha256" to JsonPrimitive(Sha256.of(fixture.files.readBytes("${fixture.root}/raw/0-series.bin"))),
        )
        assertEquals("raw archive path reused", failureOf { fixture.validate(protocol, rows) })
    }

    test("accepts repeated series and monitor bytes across distinct processes") {
        val fixture = legacyFixture()
        val protocol = fixture.protocol(fixture.control())
        val rows = fixture.captures()
        fixture.files.write(
            "${fixture.root}/" + rows[1].str("series_path"),
            fixture.files.readBytes("${fixture.root}/" + rows[0].str("series_path")),
        )
        fixture.files.write(
            "${fixture.root}/" + rows[1].str("monitor_path"),
            fixture.files.readBytes("${fixture.root}/" + rows[0].str("monitor_path")),
        )
        rows[1] = rows[1].replaced(
            "series_sha256" to rows[0].getValue("series_sha256"),
            "monitor_sha256" to rows[0].getValue("monitor_sha256"),
        )
        assertEquals(1, fixture.validate(protocol, rows))
    }

    test("rejects an incomplete declared pair inventory") {
        val fixture = legacyFixture()
        val protocol = fixture.protocol(fixture.control())
        val rows = fixture.captures().dropLast(1)
        assertEquals(
            "declared assignment pair inventory incomplete",
            failureOf { fixture.validate(protocol, rows) },
        )
    }

    test("rejects a wrong assignment route, artifact, unbalanced order, and control") {
        val fixture = legacyFixture()
        val protocol = fixture.protocol(fixture.control())

        val wrongRoute = fixture.captures()
        wrongRoute[0] = wrongRoute[0].replaced("route" to JsonPrimitive("baseline"))
        assertEquals("capture route, host, or boot differs", failureOf { fixture.validate(protocol, wrongRoute) })

        val wrongArtifact = fixture.captures()
        wrongArtifact[0] = wrongArtifact[0].replaced("artifact_sha256" to JsonPrimitive("0".repeat(64)))
        assertEquals("capture artifact differs", failureOf { fixture.validate(protocol, wrongArtifact) })

        val wrongOrder = fixture.captures()
        wrongOrder[0] = wrongOrder[0].replaced("order" to JsonPrimitive(2))
        assertEquals("A/A side or order differs", failureOf { fixture.validate(protocol, wrongOrder) })

        val wrongControl = fixture.captures()
        wrongControl[0] = wrongControl[0].replaced("control_id" to JsonPrimitive("dyn4j_6_0_0_jvm"))
        assertEquals("capture control differs", failureOf { fixture.validate(protocol, wrongControl) })
    }

    test("rejects an assignment outside the frozen protocol") {
        val fixture = legacyFixture()
        assertEquals(
            "assignment outside frozen protocol",
            failureOf {
                fixture.protocolValidation(
                    fixture.protocol(
                        fixture.control(),
                        key = "absolute_timing|wrong|nope|timing|p99|full",
                    ),
                )
            },
        )
    }

    test("rejects an unpinned dyn4j baseline artifact") {
        val fixture = legacyFixture()
        val key = SustainedArchive.comparisonControlKeys(PerformanceManifest.manifest())
            .first { it.startsWith("jvm_vs_dyn4j|jvm.java|") }
        val base = fixture.control(rowId = "jvm.java", controlId = "dyn4j_6_0_0_jvm")
        // A real, self-consistent artifact whose bytes are not the pinned dyn4j baseline.
        fixture.files.write("${fixture.root}/inputs/unjinned.jar", "not the pinned baseline")
        val control = base.replaced(
            "artifact_path" to JsonPrimitive("inputs/unjinned.jar"),
            "artifact_sha256" to JsonPrimitive(Sha256.of("not the pinned baseline")),
        )
        assertEquals(
            "dyn4j baseline artifact differs",
            failureOf { fixture.protocolValidation(fixture.protocol(control, key)) },
        )
    }

    test("rejects a version three assignment that is not a timing schema") {
        val fixture = legacyFixture()
        val memoryKey = SustainedArchive.comparisonControlKeys(PerformanceManifest.manifest())
            .first { it.startsWith("absolute_memory|js.node|") }
        val protocol = fixture.protocol(fixture.control(), key = memoryKey, version = ReferenceStudy.VERSION)
        assertEquals(
            "version 3 requires a timing raw schema",
            failureOf { fixture.protocolValidation(protocol) },
        )
    }

    test("an unsafe archived path is refused") {
        val fixture = legacyFixture()
        val protocol = fixture.protocol(fixture.control())
        val rows = fixture.captures()
        rows[0] = rows[0].replaced("series_path" to JsonPrimitive("raw/../escape.bin"))
        assertEquals("unsafe archived path", failureOf { fixture.validate(protocol, rows) })
    }

    test("a missing archived byte stream is refused") {
        val fixture = legacyFixture()
        val protocol = fixture.protocol(fixture.control())
        val rows = fixture.captures()
        fixture.files.remove("${fixture.root}/" + rows[0].str("monitor_path"))
        assertEquals("missing archived bytes", failureOf { fixture.validate(protocol, rows) })
    }

    test("an unknown archive version is rejected before any capture is read") {
        val fixture = legacyFixture()
        val protocol = fixture.protocol(fixture.control())
        val altered = protocol.replaced(
            "context" to fixture.context.replaced("version" to JsonPrimitive("reference-study-v1")),
        )
        assertEquals("unknown study archive version", failureOf { fixture.validate(altered, fixture.captures()) })
    }

    test("a control host identity is required") {
        val fixture = legacyFixture()
        val control = fixture.control().replaced("host_id" to JsonPrimitive("  "))
        assertEquals(
            "missing control host",
            failureOf { fixture.protocolValidation(fixture.protocol(control)) },
        )
    }

    test("a version three control source path must be absolute") {
        val fixture = legacyFixture()
        val key = SustainedArchive.comparisonControlKeys(PerformanceManifest.manifest())
            .sorted()
            .first { it.startsWith("absolute_timing|js.node|") }
        var control = fixture.control()
        for (name in ReferenceStudy.identityFiles) {
            control = control.replaced(name + "_source_path" to JsonPrimitive("relative/$name"))
        }
        assertEquals(
            "control artifact source path differs",
            failureOf { fixture.protocolValidation(fixture.protocol(control, key, version = ReferenceStudy.VERSION)) },
        )
    }

    test("the capture identity keys are exactly the declared identity") {
        assertEquals(22, ReferenceStudy.captureIdentityKeys.size)
        assertEquals(true, "artifact_sha256" in ReferenceStudy.captureIdentityKeys)
        assertEquals(true, "run_receipt_path" in ReferenceStudy.captureKeys(ReferenceStudy.VERSION))
        assertEquals(true, "run_receipt_path" !in ReferenceStudy.captureKeys(ReferenceStudy.LEGACY_VERSION))
    }

    test("a parsed sidecar with a repeated key is refused") {
        assertEquals(
            "duplicate JSON key",
            failureOf { ReferenceStudy.uniqueObject(listOf("a" to JsonPrimitive(1), "a" to JsonPrimitive(2))) },
        )
        assertEquals(true, StrictJson.load("""{"a":1}""") is JsonObject)
    }
}

/** Path semantics that the archive rules depend on. */
val PerformancePathsCases by testSuite {
    test("normalisation collapses dot segments and keeps absoluteness") {
        assertEquals("/a/b", PerformancePaths.normalize("/a/./b/"))
        assertEquals("/a", PerformancePaths.normalize("/a/b/.."))
        assertEquals("b", PerformancePaths.normalize("./b"))
        assertEquals("..", PerformancePaths.normalize(".."))
        assertEquals("/", PerformancePaths.normalize("/"))
    }

    test("suffix matches pathlib on the names the tools hash") {
        assertEquals(".jar", PerformancePaths.suffix("/a/dyn4j-6.0.0.jar"))
        assertEquals(".gz", PerformancePaths.suffix("/a/dyn4j.tar.gz"))
        assertEquals("", PerformancePaths.suffix("/a/.hidden"))
        assertEquals("", PerformancePaths.suffix("/a/trailing."))
        assertEquals("", PerformancePaths.suffix("/a/noext"))
    }

    test("relative containment follows the path components") {
        assertEquals(true, PerformancePaths.isRelativeTo("/root/a/b", "/root/a"))
        assertEquals(false, PerformancePaths.isRelativeTo("/root/ab", "/root/a"))
        assertEquals(true, PerformancePaths.isRelativeTo("/root", "/root"))
    }
}
