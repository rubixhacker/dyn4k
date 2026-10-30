package io.github.rubixhacker.harness.qualification

import de.infix.testBalloon.framework.core.testSuite
import io.github.rubixhacker.harness.contract.Qualification
import io.github.rubixhacker.harness.contract.StrictJson
import java.io.ByteArrayOutputStream
import java.nio.file.Files
import java.nio.file.Path
import java.security.MessageDigest
import java.util.concurrent.TimeUnit
import java.util.zip.Inflater
import kotlin.io.path.writeBytes
import kotlin.io.path.writeText
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject

/**
 * `test_full_hosted.py`: the report readers, the process receipt, the product selection, the
 * consumer graph, the staging and receipt verifiers, and the generated scripts.
 *
 * Nothing here runs on a hosted macOS, Windows, or Safari runner: every hosted case is built from
 * fixtures this suite writes itself. The Safari diagnostic suite uses the retained 5,758-case
 * browser XML `system-out` extract that the Python suite also reads.
 */
val FullHostedRuntimeContract by testSuite {
    // ------------------------------------------------------------------------------------
    // Generated scripts and pure rules: parity with the Python reference
    // ------------------------------------------------------------------------------------

    test("the generated init scripts match the reference") {
        for (vector in FullHostedVectors.INIT_SCRIPTS) {
            val outcome = vector.text
            if (outcome is VectorError) {
                assertEquals(
                    outcome.message,
                    assertFailsWith<IllegalArgumentException> {
                        FullHosted.initScript(
                            vector.target,
                            vector.configuration,
                            vector.simulatorUdid,
                        )
                    }.message,
                    vector.target + " " + vector.configuration,
                )
            } else {
                assertEquals(
                    ((outcome as VectorValue).value as VectorOk).value,
                    FullHosted.initScript(
                        vector.target,
                        vector.configuration,
                        vector.simulatorUdid,
                    ),
                    vector.target + " " + vector.configuration,
                )
            }
        }
    }

    test("the generated graph scripts match the reference") {
        for (vector in FullHostedVectors.GRAPH_SCRIPTS) {
            assertEquals(vector.text, FullHosted.graphScript(vector.target), vector.target)
        }
    }

    test("the Safari product paths match the reference") {
        for (vector in FullHostedVectors.PRODUCT_PATHS) {
            val outcome = vector.paths
            if (outcome is VectorError) {
                assertEquals(
                    outcome.message,
                    assertFailsWith<IllegalArgumentException> {
                        FullHosted.safariProductPaths(
                            vector.project,
                            vector.configuration,
                            vector.name,
                        )
                    }.message,
                )
            } else {
                val paths = (outcome as VectorValue).value as VectorPaths
                val actual = FullHosted.safariProductPaths(
                    vector.project,
                    vector.configuration,
                    vector.name,
                )
                assertEquals(paths.expected, actual.expected)
                assertEquals(paths.karmaInput, actual.karmaInput)
                assertEquals(paths.buildRoot, actual.buildRoot)
                assertEquals(paths.karmaPackage, actual.karmaPackage)
            }
        }
    }

    test("the generated Karma configuration input matches the reference") {
        for (vector in FullHostedVectors.CONFIG_INPUTS) {
            val outcome = vector.input
            if (outcome is VectorError) {
                assertFailsWith<IllegalArgumentException>(vector.data.take(80)) {
                    FullHosted.safariConfigInput(vector.data.toByteArray())
                }
            } else {
                assertEquals(
                    ((outcome as VectorValue).value as VectorOk).value,
                    FullHosted.safariConfigInput(vector.data.toByteArray()),
                )
            }
        }
    }

    test("the Safari mode arguments match the reference") {
        for (vector in FullHostedVectors.MODE_ARGUMENTS) {
            val outcome = vector.outcome
            if (outcome is VectorError) {
                assertEquals(
                    outcome.message,
                    assertFailsWith<IllegalArgumentException> {
                        FullHosted.verifySafariModeArguments(
                            vector.command,
                            vector.processName,
                            vector.configuration,
                        )
                    }.message,
                )
            } else {
                FullHosted.verifySafariModeArguments(
                    vector.command,
                    vector.processName,
                    vector.configuration,
                )
            }
        }
    }

    test("the Safari diagnostic number grammar matches the reference") {
        for (vector in FullHostedVectors.SAFARI_NUMBERS) {
            val outcome = vector.outcome
            if (outcome is VectorError) {
                assertEquals(
                    outcome.message,
                    assertFailsWith<IllegalArgumentException> {
                        FullHosted.safariV2Number(vector.value, "field")
                    }.message,
                    vector.value,
                )
            } else {
                FullHosted.safariV2Number(vector.value, "field")
            }
        }
    }

    test("the Safari diagnostic integer grammar matches the reference") {
        for (vector in FullHostedVectors.SAFARI_INTEGERS) {
            val outcome = vector.outcome
            if (outcome is VectorError) {
                assertEquals(
                    outcome.message,
                    assertFailsWith<IllegalArgumentException>(vector.value) {
                        FullHosted.safariV2Integer(vector.value, "field", vector.minimum)
                    }.message,
                    vector.value,
                )
            } else {
                assertEquals(
                    ((outcome as VectorValue).value as VectorInt).literal,
                    FullHosted.safariV2Integer(vector.value, "field", vector.minimum).literal,
                    vector.value,
                )
            }
        }
    }

    test("the Safari diagnostic vector grammars match the reference") {
        for (vector in FullHostedVectors.SAFARI_VECTORS) {
            val outcome = vector.outcome
            if (outcome is VectorError) {
                assertFailsWith<IllegalArgumentException> {
                    FullHostedRules.safariV2Vector(vector.value, "field")
                }
            } else {
                FullHostedRules.safariV2Vector(vector.value, "field")
            }
        }
        for (vector in FullHostedVectors.SAFARI_NUMBER_LISTS) {
            val outcome = vector.outcome
            if (outcome is VectorError) {
                assertFailsWith<IllegalArgumentException> {
                    FullHostedRules.safariV2Numbers(vector.value, "field", vector.count)
                }
            } else {
                FullHostedRules.safariV2Numbers(vector.value, "field", vector.count)
            }
        }
        for (vector in FullHostedVectors.SAFARI_VECTOR_LISTS) {
            val outcome = vector.outcome
            if (outcome is VectorError) {
                assertFailsWith<IllegalArgumentException> {
                    FullHostedRules.safariV2Vectors(
                        vector.value,
                        "field",
                        vector.allowNull,
                        vector.allowEmpty,
                    )
                }
            } else {
                assertEquals(
                    ((outcome as VectorValue).value as VectorCount).value,
                    FullHostedRules.safariV2Vectors(
                        vector.value,
                        "field",
                        vector.allowNull,
                        vector.allowEmpty,
                    ),
                )
            }
        }
    }

    test("the Safari diagnostic feature, shape, and edge grammars match the reference") {
        for (vector in FullHostedVectors.SAFARI_FEATURES) {
            val outcome = vector.outcome
            if (outcome is VectorError) {
                assertFailsWith<IllegalArgumentException> {
                    FullHostedRules.safariV2Feature(vector.value, "field")
                }
            } else {
                FullHostedRules.safariV2Feature(vector.value, "field")
            }
        }
        for (vector in FullHostedVectors.SAFARI_SHAPES) {
            val outcome = vector.outcome
            if (outcome is VectorError) {
                assertFailsWith<IllegalArgumentException> {
                    FullHostedRules.safariV2Shape(vector.value, "field")
                }
            } else {
                val expected = (outcome as VectorValue).value as VectorShape
                val actual = FullHostedRules.safariV2Shape(vector.value, "field")
                assertEquals(expected.kind, actual.first)
                assertEquals(expected.count, actual.second)
            }
        }
        for (vector in FullHostedVectors.SAFARI_POLYGON_EDGES) {
            val outcome = vector.outcome
            if (outcome is VectorError) {
                assertFailsWith<IllegalArgumentException> {
                    FullHostedRules.safariV2PolygonEdges(
                        vector.value,
                        "field",
                        vector.kind,
                        vector.vertices,
                    )
                }
            } else {
                FullHostedRules.safariV2PolygonEdges(
                    vector.value,
                    "field",
                    vector.kind,
                    vector.vertices,
                )
            }
        }
    }

    test("the Safari diagnostic SAT and EPA grammars match the reference") {
        for (vector in FullHostedVectors.SAFARI_SAT_CANDIDATES) {
            val outcome = vector.outcome
            if (outcome is VectorError) {
                assertFailsWith<IllegalArgumentException> {
                    FullHostedRules.safariV2SatCandidates(vector.value, "field")
                }
            } else {
                assertEquals(
                    ((outcome as VectorValue).value as VectorBoolean).value,
                    FullHostedRules.safariV2SatCandidates(vector.value, "field"),
                )
            }
        }
        for (vector in FullHostedVectors.SAFARI_EPA_RECORDS) {
            val outcome = vector.outcome
            if (outcome is VectorError) {
                assertFailsWith<IllegalArgumentException> {
                    FullHostedRules.safariV2EpaRecords(
                        vector.value,
                        "field",
                        SafariInteger.of(vector.iteration),
                    )
                }
            } else {
                FullHostedRules.safariV2EpaRecords(
                    vector.value,
                    "field",
                    SafariInteger.of(vector.iteration),
                )
            }
        }
    }

    // ------------------------------------------------------------------------------------
    // read_reports
    // ------------------------------------------------------------------------------------

    test("a native full report requires exact source cases") {
        withHostedTemporary { root ->
            val path = root.resolve("TEST-one.xml")
            val name = "macosArm64Test.org.dyn4j.geometry.ExampleTest"
            val good = listOf(name to "works[macosArm64]")
            val expected = setOf("org.dyn4j.geometry.ExampleTest" to "works")
            var end = writeHostedSuite(path, good)
            assertEquals(
                1,
                FullHosted.readReports(listOf(path), expected, "macosArm64", 0, end).executed,
            )
            for ((cases, marker) in listOf(
                emptyList<Pair<String, String>>() to "missing",
                listOf(good[0], good[0]) to "duplicate",
                listOf(good[0], name to "extra[macosArm64]") to "extra",
                listOf(name to "works[mingwX64]") to "target",
            )) {
                end = writeHostedSuite(path, cases)
                val error = assertFailsWith<IllegalArgumentException> {
                    FullHosted.readReports(listOf(path), expected, "macosArm64", 0, end)
                }
                assertTrue(
                    marker in (error.message ?: ""),
                    "expected $marker in ${error.message}",
                )
            }
        }
    }

    test("failed, skipped, ignored, and stale XML cannot pass") {
        withHostedTemporary { root ->
            val path = root.resolve("TEST-one.xml")
            val good = listOf(
                "macosArm64Test.org.dyn4j.geometry.ExampleTest" to "works[macosArm64]",
            )
            val expected = setOf("org.dyn4j.geometry.ExampleTest" to "works")
            for ((skipped, ignored) in listOf(true to false, false to true)) {
                val end = writeHostedSuite(path, good, skipped = skipped, ignored = ignored)
                assertFailsWith<IllegalArgumentException> {
                    FullHosted.readReports(listOf(path), expected, "macosArm64", 0, end)
                }
            }
            val end = writeHostedSuite(path, good)
            val stale = assertFailsWith<IllegalArgumentException> {
                FullHosted.readReports(listOf(path), expected, "macosArm64", end + 1, end + 2)
            }
            assertTrue("stale" in (stale.message ?: ""))
            path.writeText(
                """<testsuite tests="1" failures="1" errors="0" skipped="0" time="0.1">""" +
                    """<testcase classname="macosArm64Test.org.dyn4j.geometry.ExampleTest" """ +
                    """name="works[macosArm64]" time="0.1"><failure>broken</failure></testcase>""" +
                    """</testsuite>""",
            )
            val failed = assertFailsWith<IllegalArgumentException> {
                FullHosted.readReports(
                    listOf(path),
                    expected,
                    "macosArm64",
                    0,
                    FullHostedRuntime.nowNs() + 1_000_000_000L,
                )
            }
            assertTrue("failed" in (failed.message ?: ""))
        }
    }

    test("a Safari report requires the browser runtime and the exact case") {
        withHostedTemporary { root ->
            val path = root.resolve("TEST-one.xml")
            val classname = "jsBrowserTest.org.dyn4j.geometry.ExampleTest"
            val expected = setOf("org.dyn4j.geometry.ExampleTest" to "works")
            var end = writeHostedSuite(
                path,
                listOf(classname to "works[js, browser, Safari26.6.2, MacOS10.15.7]"),
            )
            assertEquals(
                1,
                FullHosted.readReports(listOf(path), expected, "jsSafari", 0, end).executed,
            )
            end = writeHostedSuite(path, listOf(classname to "works[js, node]"))
            val absent = assertFailsWith<IllegalArgumentException> {
                FullHosted.readReports(listOf(path), expected, "jsSafari", 0, end)
            }
            assertTrue("Safari browser identity" in (absent.message ?: ""))
            end = writeHostedSuite(
                path,
                listOf(classname to "works[js, browser, Safari26.6.2, MacOS10.15.7]"),
            )
            val version = assertFailsWith<IllegalArgumentException> {
                FullHosted.readReports(listOf(path), expected, "jsSafari", 0, end, "26.6.3")
            }
            assertTrue("browser version differs" in (version.message ?: ""))
        }
    }

    test("a replayed diagnostic prefix cannot satisfy the source case contract") {
        val rows = hostedDiagnosticRows()
        val classname = FullHosted.SAFARI_DIAGNOSTIC_CLASS
        var suite = hostedDiagnosticSuite(rows, repeat = 1)
        FullHosted.checkSafariDiagnosticSuite(suite)
        suite = hostedDiagnosticSuite(rows, repeat = 2)
        val error = assertFailsWith<IllegalArgumentException> {
            FullHosted.checkSafariDiagnosticSuite(suite)
        }
        assertEquals("Safari diagnostic case identities differ", error.message)

        withHostedTemporary { root ->
            val path = root.resolve("TEST-diagnostic.xml")
            path.writeText(renderHostedSuite(hostedDiagnosticSuite(rows, repeat = 1)))
            val expected = FullHosted.SAFARI_DIAGNOSTIC_CASES.keys
                .map { classname to it }
                .toSet()
            val end = Files.getLastModifiedTime(path).to(TimeUnit.NANOSECONDS)
            val checked = FullHosted.readReports(listOf(path), expected, "jsSafari", 0, end)
            assertEquals(FullHosted.SAFARI_DIAGNOSTIC_CASES.size, checked.executed)
            assertEquals(1, checked.reports.size)
        }
    }

    test("a diagnostic row with a mutated field is rejected") {
        val rows = hostedDiagnosticRows()
        val mutated = rows.toMutableList()
        mutated[0] = mutated[0].replace("provider=dyn4k", "provider=other")
        val error = assertFailsWith<IllegalArgumentException> {
            FullHosted.checkSafariDiagnosticSuite(hostedDiagnosticSuite(mutated, repeat = 1))
        }
        assertEquals("Safari diagnostic row fields are incomplete or changed", error.message)
    }

    // ------------------------------------------------------------------------------------
    // Process receipts
    // ------------------------------------------------------------------------------------

    test("the process receipt records the real pid and both output hashes") {
        withHostedTemporary { root ->
            val process = FullHosted.runCommand(
                listOf("sh", "-c", "printf out; printf err >&2"),
                root,
                root.resolve("process"),
            )
            assertTrue(Py.int(process["pid"]!!) > 0)
            assertEquals(0L, Py.int(process["exit_code"]!!))
            assertEquals("out", Files.readString(root.resolve("process/stdout.txt")))
            assertEquals(
                FullHosted.sha256(root.resolve("process/stderr.txt")),
                Py.str(process["stderr_sha256"]),
            )
            for (stream in listOf("stdout", "stderr")) {
                val modified = Files.getLastModifiedTime(root.resolve("process/$stream.txt"))
                    .to(TimeUnit.NANOSECONDS)
                assertTrue(Py.int(process["started_ns"]!!) <= modified)
                assertTrue(modified <= Py.int(process["finished_ns"]!!))
            }
        }
    }

    test("an archived process receipt must match its logs and invocation") {
        withHostedTemporary { root ->
            val output = root.resolve("archive")
            val folder = output.resolve("stage")
            Files.createDirectories(folder)
            folder.resolve("stdout.txt").writeText("BUILD SUCCESSFUL\n")
            folder.resolve("stderr.txt").writeText("")
            // The staged log timestamps are set explicitly, so the fixture does not race the
            // coarse file-system clock the way a live write can.
            val started = FullHostedRuntime.nowNs() - 1_000_000_000L
            val finished = started + 500_000_000L
            val modified = started + 1_000_000L
            for (stream in listOf("stdout", "stderr")) {
                Files.setLastModifiedTime(
                    folder.resolve("$stream.txt"),
                    java.nio.file.attribute.FileTime.from(modified, TimeUnit.NANOSECONDS),
                )
            }
            val process = buildJsonObject {
                put(
                    "command",
                    JsonArray(
                        listOf("gradlew", "--rerun-tasks", ":dyn4k-core:jsBrowserTest")
                            .map { JsonPrimitive(it) },
                    ),
                )
                put("pid", JsonPrimitive(4242))
                put("exit_code", JsonPrimitive(0))
                put("invocation_id", JsonPrimitive("1".repeat(32)))
                put("started_ns", JsonPrimitive(started))
                put("finished_ns", JsonPrimitive(finished))
                for (stream in listOf("stdout", "stderr")) {
                    put(
                        "${stream}_sha256",
                        JsonPrimitive(FullHosted.sha256(folder.resolve("$stream.txt"))),
                    )
                }
            }
            FullHosted.verifyProcess(
                output,
                folder,
                process,
                "1".repeat(32),
                ":dyn4k-core:jsBrowserTest",
            )
            assertEquals(
                "archived process command lacks required task",
                assertFailsWith<IllegalArgumentException> {
                    FullHosted.verifyProcess(
                        output,
                        folder,
                        process,
                        "1".repeat(32),
                        ":dyn4k-core:publishKotlinMultiplatformPublicationToStagingRepository",
                    )
                }.message,
            )
            assertEquals(
                "archived process exit, identity, or timestamps differ",
                assertFailsWith<IllegalArgumentException> {
                    FullHosted.verifyProcess(output, folder, process, "2".repeat(32))
                }.message,
            )
            assertEquals(
                "archived process log differs from receipt",
                assertFailsWith<IllegalArgumentException> {
                    Files.writeString(folder.resolve("stdout.txt"), "tampered BUILD SUCCESSFUL\n")
                    FullHosted.verifyProcess(output, folder, process, "1".repeat(32))
                }.message,
            )
        }
    }

    test("a release task and a production input are required") {
        withHostedTemporary { root ->
            val folder = root.resolve("process")
            Files.createDirectories(folder)
            val process = buildJsonObject { put("exit_code", JsonPrimitive(0)) }
            folder.resolve("stdout.txt").writeText("> Task :dyn4k-core:mingwX64Test\nBUILD SUCCESSFUL\n")
            val link = assertFailsWith<IllegalArgumentException> {
                FullHosted.requireTestTasks(
                    process,
                    folder,
                    "mingwX64",
                    "optimized-opt",
                    listOf("dyn4k-core"),
                )
            }
            assertTrue("link" in (link.message ?: ""))
            folder.resolve("stdout.txt").writeText(
                "> Task :dyn4k-core:linkReleaseTestMingwX64\n" +
                    "> Task :dyn4k-core:mingwX64Test\nBUILD SUCCESSFUL\n",
            )
            FullHosted.requireTestTasks(
                process,
                folder,
                "mingwX64",
                "optimized-opt",
                listOf("dyn4k-core"),
            )
            folder.resolve("stdout.txt").writeText(
                "> Task :dyn4k-core:linkReleaseTestMingwX64 SKIPPED\n" +
                    "> Task :dyn4k-core:mingwX64Test SKIPPED\nBUILD SUCCESSFUL\n",
            )
            assertFailsWith<IllegalArgumentException> {
                FullHosted.requireTestTasks(
                    process,
                    folder,
                    "mingwX64",
                    "optimized-opt",
                    listOf("dyn4k-core"),
                )
            }
            folder.resolve("stdout.txt").writeText(
                "> Task :dyn4k-core:jsBrowserTest\nBUILD SUCCESSFUL\n",
            )
            val production = assertFailsWith<IllegalArgumentException> {
                FullHosted.requireTestTasks(
                    process,
                    folder,
                    "jsSafari",
                    "production",
                    listOf("dyn4k-core"),
                )
            }
            assertTrue("production" in (production.message ?: ""))
        }
    }

    // ------------------------------------------------------------------------------------
    // Product selection and inventories
    // ------------------------------------------------------------------------------------

    test("an executable must match its configuration and invocation") {
        withHostedTemporary { root ->
            val binary = root.resolve("build/bin/mingwX64/releaseTest/test.exe")
            Files.createDirectories(binary.parent)
            binary.writeBytes("release".toByteArray())
            val process = buildJsonObject {
                put("started_ns", JsonPrimitive(0))
                put("finished_ns", JsonPrimitive(FullHostedRuntime.nowNs() + 1_000_000_000L))
            }
            assertEquals(
                FullHosted.sha256(binary),
                Py.str(FullHosted.testProducts(root, "mingwX64", "optimized-opt", process)["sha256"]),
            )
            val diagnostic = root.resolve("product-inventory.json")
            val products = FullHosted.collectTestProducts(
                mapOf("core" to root),
                "mingwX64",
                "optimized-opt",
                process,
                diagnostic,
                root,
            )
            assertEquals(FullHosted.sha256(binary), Py.str(products.getValue("core")["sha256"]))
            assertTrue(!Files.exists(diagnostic))
            val one = assertFailsWith<IllegalArgumentException> {
                FullHosted.testProducts(root, "mingwX64", "debug-g", process)
            }
            assertTrue("exactly one" in (one.message ?: ""))
            val predates = assertFailsWith<IllegalArgumentException> {
                FullHosted.testProducts(
                    root,
                    "mingwX64",
                    "optimized-opt",
                    buildJsonObject {
                        put("started_ns", JsonPrimitive(FullHostedRuntime.nowNs() + 2_000_000_000L))
                        put("finished_ns", JsonPrimitive(FullHostedRuntime.nowNs() + 3_000_000_000L))
                    },
                )
            }
            assertTrue("predates" in (predates.message ?: ""))
        }
    }

    test("a mac product selects the direct executable beside its dsym") {
        for ((configuration, mode) in listOf(
            "debug-g" to "debugTest",
            "optimized-opt" to "releaseTest",
        )) {
            withHostedTemporary { root ->
                val project = root.resolve(configuration)
                val directory = project.resolve("build/bin/macosArm64").resolve(mode)
                val direct = directory.resolve("test.kexe")
                val dwarf = directory.resolve("test.kexe.dSYM/Contents/Resources/DWARF/test.kexe")
                val started = FullHostedRuntime.nowNs() - 1_000_000_000L
                Files.createDirectories(direct.parent)
                direct.writeBytes("linked executable".toByteArray())
                Files.createDirectories(dwarf.parent)
                dwarf.writeBytes("DWARF debug symbols".toByteArray())
                val process = buildJsonObject {
                    put("started_ns", JsonPrimitive(started))
                    put(
                        "finished_ns",
                        JsonPrimitive(FullHostedRuntime.nowNs() + 1_000_000_000L),
                    )
                    put("invocation_id", JsonPrimitive("synthetic"))
                    put("exit_code", JsonPrimitive(0))
                }
                val diagnosticRoot = root.resolve("failed-$configuration")
                val selected = FullHosted.collectTestProducts(
                    mapOf("dyn4k-core" to project),
                    "macosArm64",
                    configuration,
                    process,
                    diagnosticRoot.resolve("product-inventory.json"),
                    diagnosticRoot,
                )
                assertEquals(direct.toString(), Py.str(selected.getValue("dyn4k-core")["path"]))
                assertTrue(
                    FullHosted.sha256(direct) != FullHosted.sha256(dwarf),
                )
                val duplicate = directory.resolve("duplicate.kexe")
                duplicate.writeBytes("second direct executable".toByteArray())
                val crowded = assertFailsWith<IllegalArgumentException> {
                    FullHosted.collectTestProducts(
                        mapOf("dyn4k-core" to project),
                        "macosArm64",
                        configuration,
                        process,
                        diagnosticRoot.resolve("product-inventory.json"),
                        diagnosticRoot,
                    )
                }
                assertTrue("product inventory" in (crowded.message ?: ""))
                val evidence = StrictJson.load(
                    Files.readString(diagnosticRoot.resolve("product-inventory.json")),
                ) as JsonObject
                val entries = (((evidence["projects"] as JsonObject)
                    .getValue("dyn4k-core") as JsonObject)["entries"] as JsonArray)
                    .map { it as JsonObject }
                assertTrue(Py.str(entries.first { Py.str(it["kind"]) == "directory" }["path"]) != null)
                assertTrue(
                    entries.map { Py.str(it["path"]) }
                        .any { it != null && "test.kexe.dSYM" in it },
                )
            }
        }
    }

    test("a missing mac product retains the bounded inventory without accepting it") {
        withHostedTemporary { root ->
            val project = root.resolve("dyn4k-core")
            val product = project.resolve("build/bin/macosArm64/debugTest/test")
            Files.createDirectories(product.parent)
            product.writeBytes("observed-layout-placeholder".toByteArray())
            val output = root.resolve("failed-archive")
            Files.createDirectories(output)
            output.resolve("receipt.json").writeText("{}")
            val diagnostic = output.resolve("debug-g/product-inventory-source.json")
            val process = buildJsonObject {
                put("started_ns", JsonPrimitive(1))
                put("finished_ns", JsonPrimitive(FullHostedRuntime.nowNs() + 1_000_000_000L))
                put("invocation_id", JsonPrimitive("synthetic-invocation"))
                put("exit_code", JsonPrimitive(0))
            }
            val error = assertFailsWith<IllegalArgumentException> {
                FullHosted.collectTestProducts(
                    mapOf("dyn4k-core" to project),
                    "macosArm64",
                    "debug-g",
                    process,
                    diagnostic,
                    output,
                )
            }
            assertTrue("product inventory" in (error.message ?: ""))
            val evidence = StrictJson.load(Files.readString(diagnostic)) as JsonObject
            assertEquals("macosArm64", Py.str(evidence["target"]))
            assertEquals("synthetic-invocation", Py.str(evidence["invocation_id"]))
            val entries = ((evidence["projects"] as JsonObject)
                .getValue("dyn4k-core") as JsonObject)["entries"] as JsonArray
            val files = entries.map { it as JsonObject }.filter { Py.str(it["kind"]) == "file" }
            assertEquals(1, files.size)
            assertEquals("build/bin/macosArm64/debugTest/test", Py.str(files[0]["path"]))
            val archive = root.resolve("diagnostic.tar")
            FullHosted.packageArchive(output, archive)
            val names = hostedTarNames(archive)
            assertTrue("debug-g/product-inventory-source.json" in names)
        }
    }

    test("a missing Safari product retains both compiler and Karma layouts") {
        withHostedTemporary { root ->
            val repository = root.resolve("repository")
            val project = repository.resolve("dyn4k-core")
            val packageName = "dyn4k-dyn4k-core-test"
            val packageDir = repository.resolve("build/js/packages/$packageName")
            val bundle = packageDir.resolve("kotlin/$packageName.js")
            Files.createDirectories(bundle.parent)
            bundle.writeBytes("Karma development input".toByteArray())
            val alternate = project.resolve(
                "build/compileSync/js/test/testProductionExecutable/alternate/$packageName.js",
            )
            Files.createDirectories(alternate.parent)
            alternate.writeBytes("Mac layout candidate".toByteArray())
            val output = root.resolve("failed-safari")
            Files.createDirectories(output)
            output.resolve("receipt.json").writeText("{}")
            val process = buildJsonObject {
                put("started_ns", JsonPrimitive(1))
                put("finished_ns", JsonPrimitive(FullHostedRuntime.nowNs() + 1_000_000_000L))
                put("invocation_id", JsonPrimitive("safari-invocation"))
                put("exit_code", JsonPrimitive(0))
            }
            for (mode in listOf("development", "production")) {
                val diagnostic = output.resolve("$mode/product-inventory-source.json")
                val error = assertFailsWith<IllegalArgumentException> {
                    FullHosted.collectTestProducts(
                        mapOf("dyn4k-core" to project),
                        "jsSafari",
                        mode,
                        process,
                        diagnostic,
                        output,
                    )
                }
                assertTrue("product inventory" in (error.message ?: ""))
                val record = ((StrictJson.load(Files.readString(diagnostic)) as JsonObject)["projects"]
                    as JsonObject).getValue("dyn4k-core") as JsonObject
                val expected = project.resolve(
                    "build/compileSync/js/test/" +
                        (if (mode == "development") "testDevelopmentExecutable" else "testProductionExecutable") +
                        "/kotlin/$packageName.js",
                )
                assertEquals(expected.toString(), Py.str(record["expected"]))
                assertEquals(
                    if (mode == "development") bundle.toString() else expected.toString(),
                    Py.str(record["karma_input"]),
                )
            }
        }
    }

    test("a Safari inventory does not follow a symlinked package") {
        withHostedTemporary { root ->
            val repository = root.resolve("repository")
            val project = repository.resolve("dyn4k-core")
            val outside = root.resolve("outside")
            Files.createDirectories(outside)
            (outside.resolve("secret.js")).writeBytes("outside".toByteArray())
            val packageDir = repository.resolve("build/js/packages/dyn4k-dyn4k-core-test")
            Files.createDirectories(packageDir.parent)
            Files.createSymbolicLink(packageDir, outside)
            val record = FullHosted.productInventory(project, "jsSafari", "development", "dyn4k-core")
            val roots = record["roots"] as JsonObject
            val karmaPackage = roots["karma_package"] as JsonObject
            assertEquals(false, karmaPackage["present"]?.let { Py.truthy(it) })
            assertEquals(true, karmaPackage["unsafe_symlink"]?.let { Py.truthy(it) })
            assertEquals(0, (karmaPackage["entries"] as JsonArray).size)
            val observations = record["observations"] as JsonObject
            assertEquals("UNSAFE", Py.str((observations["karma_input"] as JsonObject)["status"]))
        }
    }

    test("a product diagnostic inventory has a fixed entry limit") {
        withHostedTemporary { root ->
            val project = root.resolve("dyn4k-core")
            val directory = project.resolve("build/bin/macosArm64/debugTest")
            Files.createDirectories(directory)
            for (index in 0 until 200) {
                directory.resolve("noise-$index.bin").writeBytes("x".toByteArray())
            }
            val record = FullHosted.productInventory(project, "macosArm64")
            val entries = record["entries"] as JsonArray
            assertEquals(128, entries.size)
            assertEquals(true, record["truncated"]?.let { Py.truthy(it) })
        }
    }

    // ------------------------------------------------------------------------------------
    // Consumer graph
    // ------------------------------------------------------------------------------------

    test("the consumer graph accepts exact staged bytes from the Gradle cache") {
        withHostedTemporary { root ->
            val target = "macosArm64"
            val otherTarget = "mingwX64"
            val staging = root.resolve("staging-repository")
            val graphFolder = root.resolve("graph")
            Files.createDirectories(graphFolder)
            val hashes = linkedMapOf<String, String>()
            val artifacts = mutableListOf<JsonObject>()
            val coreName = Qualification.targetPublicationName("dyn4k-core", target)
            val otherCoreName = Qualification.targetPublicationName("dyn4k-core", otherTarget)
            for (module in Qualification.modules) {
                val name = Qualification.targetPublicationName(module, target)
                val binary = staging.resolve(Qualification.targetBinaryPath(module, target))
                Files.createDirectories(binary.parent)
                var contents = "$module staged bytes".toByteArray()
                if (module == "dyn4k-core") {
                    for (nonce in 0 until 256) {
                        val candidate = contents + nonce.toString().toByteArray()
                        if (hostedSha1(candidate).startsWith("0")) {
                            contents = candidate
                            break
                        }
                    }
                    assertTrue(hostedSha1(contents).startsWith("0"))
                }
                binary.writeBytes(contents)
                hashes[module] = FullHosted.sha256(binary)
                val cache = root.resolve("gradle-home/caches/modules-2/files-2.1")
                    .resolve(Qualification.GROUP)
                    .resolve(name)
                    .resolve(Qualification.VERSION)
                    .resolve(hostedSha1(contents))
                    .resolve("$module-$target" + "Main-${Qualification.VERSION}.klib")
                Files.createDirectories(cache.parent)
                Files.copy(binary, cache)
                artifacts.add(
                    buildJsonObject {
                        put("component", JsonPrimitive("${Qualification.GROUP}:$name:${Qualification.VERSION}"))
                        put("file", JsonPrimitive(cache.toString()))
                        put("name", JsonPrimitive(cache.fileName.toString()))
                        put("size", JsonPrimitive(Files.size(cache)))
                        put("sha256", JsonPrimitive(FullHosted.sha256(cache)))
                    },
                )
            }
            val graph = buildJsonObject {
                put("configuration", JsonPrimitive("${target}CompileKlibraries"))
                put("gradle_user_home", JsonPrimitive(root.resolve("gradle-home").toString()))
                put(
                    "components",
                    JsonArray(
                        artifacts.map { it["component"]!! } +
                            Qualification.modules.map {
                                JsonPrimitive("${Qualification.GROUP}:$it:${Qualification.VERSION}")
                            } +
                            listOf(
                                JsonPrimitive("org.jetbrains.kotlin:kotlin-stdlib:2.4.20"),
                                JsonPrimitive("root project :"),
                            ),
                    ),
                )
                put("artifacts", JsonArray(artifacts))
            }
            fun observe(value: JsonObject): JsonObject {
                graphFolder.resolve("stdout.txt").writeText("DYN4K_RESOLVED_GRAPH=" + value + "\n")
                return FullHosted.parseGraph(
                    graphFolder,
                    buildJsonObject { put("exit_code", JsonPrimitive(0)) },
                    target,
                    JsonObject(hashes.mapValues { JsonPrimitive(it.value) }),
                    staging.toString(),
                    root.resolve("gradle-home").toString(),
                )
            }

            assertEquals(graph, observe(graph))
            fun withArtifacts(items: List<JsonObject>): JsonObject = JsonObject(
                graph + ("artifacts" to JsonArray(items)),
            )
            fun mutatedFirst(vararg changes: Pair<String, JsonElement>): JsonObject =
                withArtifacts(
                    listOf(JsonObject(artifacts[0] + changes.toMap())) + artifacts.drop(1),
                )
            fun expectFailure(label: String, value: JsonObject) {
                val error = assertFailsWith<IllegalArgumentException>(label) { observe(value) }
                assertTrue(label in (error.message ?: ""), "$label in ${error.message}")
            }

            expectFailure(
                "artifact differs",
                mutatedFirst("sha256" to JsonPrimitive("0".repeat(64))),
            )
            expectFailure(
                "lacks staged target",
                mutatedFirst("component" to JsonPrimitive("wrong:module:1")),
            )
            expectFailure("artifact identity", mutatedFirst("name" to JsonPrimitive("wrong.klib")))
            val firstFile = Py.str(artifacts[0]["file"])!!
            expectFailure(
                "artifact differs",
                mutatedFirst("file" to JsonPrimitive(firstFile.replace(coreName, otherCoreName))),
            )
            expectFailure(
                "cache digest",
                mutatedFirst(
                    "file" to JsonPrimitive(
                        firstFile.replace(
                            Path.of(firstFile).parent.fileName.toString(),
                            "f".repeat(40),
                        ),
                    ),
                ),
            )
            expectFailure(
                "Gradle user home",
                mutatedFirst(
                    "file" to JsonPrimitive(
                        firstFile.replace(
                            root.resolve("gradle-home").toString(),
                            root.resolve("other-gradle-home").toString(),
                        ),
                    ),
                ),
            )
            expectFailure(
                "dependency graph",
                JsonObject(
                    graph + (
                        "components" to JsonArray(
                            (graph["components"] as JsonArray) + JsonPrimitive(
                                "${Qualification.GROUP}:unexpected:${Qualification.VERSION}",
                            ),
                        )
                        ),
                ),
            )
            expectFailure(
                "staged target",
                withArtifacts(
                    artifacts + JsonObject(
                        artifacts[0] + (
                            "component" to JsonPrimitive(
                                "${Qualification.GROUP}:unexpected:${Qualification.VERSION}",
                            )
                            ),
                    ),
                ),
            )
            expectFailure(
                "Gradle user home",
                JsonObject(graph - "gradle_user_home"),
            )
        }
    }

    // ------------------------------------------------------------------------------------
    // Report groups, canonical inputs, staging, and the receipt
    // ------------------------------------------------------------------------------------

    test("an archived report group must repeat the archived identities and digests") {
        withHostedTemporary { root ->
            val reports = mutableListOf(
                buildJsonObject {
                    put("path", JsonPrimitive("xml/dyn4k-core/TEST-one.xml"))
                    put("sha256", JsonPrimitive("a".repeat(64)))
                    put("modified_ns", JsonPrimitive(7))
                },
            )
            val checked = HostedReportCheck(
                expected = 1,
                executed = 1,
                caseIds = listOf("org.dyn4j.ExampleTest#works"),
                reports = reports,
            )
            val group = checked.toJson("dyn4k-core")
            FullHosted.verifyReportGroup(group, checked, listOf("xml", "dyn4k-core"))
            assertEquals(
                "archived case identities differ from source inventory",
                assertFailsWith<IllegalArgumentException> {
                    FullHosted.verifyReportGroup(
                        JsonObject(group + ("executed" to JsonPrimitive(2))),
                        checked,
                        listOf("xml", "dyn4k-core"),
                    )
                }.message,
            )
            assertEquals(
                "archived XML path or report identity differs",
                assertFailsWith<IllegalArgumentException> {
                    FullHosted.verifyReportGroup(
                        group,
                        checked,
                        listOf("xml", "consumer"),
                    )
                }.message,
            )
            val tampered = JsonObject(
                group + (
                    "reports" to JsonArray(
                        listOf(
                            JsonObject(
                                reports[0] + ("sha256" to JsonPrimitive("b".repeat(64))),
                            ),
                        ),
                    )
                    ),
            )
            assertEquals(
                "archived XML differs from receipt",
                assertFailsWith<IllegalArgumentException> {
                    FullHosted.verifyReportGroup(tampered, checked, listOf("xml", "dyn4k-core"))
                }.message,
            )
            assertTrue(root.toString().isNotEmpty())
        }
    }

    test("the archived canonical Safari input must be the committed JSON object") {
        withHostedTemporary { root ->
            val repository = root.resolve("repository")
            Files.createDirectories(repository.resolve("tools/qualification"))
            repository.resolve("tools/qualification/full-common-corpus.json")
                .writeText("""{"a":1}""")
            hostedGit(repository, "init", "-q")
            hostedGit(repository, "add", "tools/qualification/full-common-corpus.json")
            hostedGit(
                repository,
                "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                "commit", "-qm", "sealed source",
            )
            val candidate = hostedGit(repository, "rev-parse", "HEAD").toString().trim()
            val output = root.resolve("archive")
            val archived = output.resolve("inputs/tools/qualification/full-common-corpus.json")
            Files.createDirectories(archived.parent)
            Files.copy(repository.resolve("tools/qualification/full-common-corpus.json"), archived)
            assertEquals(
                "1",
                (FullHosted.canonicalSafariJson(
                    repository,
                    candidate,
                    output,
                    "tools/qualification/full-common-corpus.json",
                )["a"] as JsonPrimitive).content,
            )
            archived.writeText("""{"a":2}""")
            assertEquals(
                "archived Safari source input differs: tools/qualification/full-common-corpus.json",
                assertFailsWith<IllegalArgumentException> {
                    FullHosted.canonicalSafariJson(
                        repository,
                        candidate,
                        output,
                        "tools/qualification/full-common-corpus.json",
                    )
                }.message,
            )
        }
    }

    test("the staging verifier requires the exact GAV inventory") {
        withHostedTemporary { root ->
            val output = root.resolve("archive")
            Files.createDirectories(output)
            val receipt = buildJsonObject {
                put("target", JsonPrimitive("macosArm64"))
                put("staged_gav", JsonArray(emptyList()))
            }
            assertEquals(
                "staged GAV inventory differs",
                assertFailsWith<IllegalArgumentException> {
                    FullHosted.verifyStaging(output, receipt)
                }.message,
            )
        }
    }

    test("the staged content verifier requires its contract and a Git checkout") {
        withHostedTemporary { root ->
            val output = root.resolve("archive")
            Files.createDirectories(output)
            val repository = root.resolve("repository")
            Files.createDirectories(repository)
            assertEquals(
                "staged publication content contract is absent",
                assertFailsWith<IllegalArgumentException> {
                    FullHosted.verifyStagedContent(
                        output,
                        buildJsonObject { put("candidate_sha", JsonPrimitive("a".repeat(40))) },
                        repository,
                    )
                }.message,
            )
            assertEquals(
                "staged publication candidate Git checkout is absent",
                assertFailsWith<IllegalArgumentException> {
                    FullHosted.verifyStagedContent(
                        output,
                        buildJsonObject {
                            put("candidate_sha", JsonPrimitive("a".repeat(40)))
                            put("staged_content_contract", JsonObject(emptyMap()))
                        },
                        repository,
                    )
                }.message,
            )
        }
    }

    test("the receipt verifier rejects anything that is not a completed target") {
        withHostedTemporary { root ->
            fun receipt(
                target: String = "macosArm64",
                status: String = "FULL_COMMON_PASSED",
                schema: Int = 2,
                lanes: JsonArray = JsonArray(
                    listOf(
                        buildJsonObject { put("configuration", JsonPrimitive("debug-g")) },
                        buildJsonObject { put("configuration", JsonPrimitive("optimized-opt")) },
                    ),
                ),
                extra: JsonObject = JsonObject(emptyMap()),
            ): JsonObject = JsonObject(
                linkedMapOf<String, JsonElement>(
                    "schema" to JsonPrimitive(schema),
                    "kind" to JsonPrimitive("hosted-full-common-corpus"),
                    "candidate_sha" to JsonPrimitive("a".repeat(40)),
                    "target" to JsonPrimitive(target),
                    "status" to JsonPrimitive(status),
                    "configurations" to lanes,
                ) + extra,
            )
            assertEquals(
                "full hosted receipt is not a completed target",
                assertFailsWith<IllegalArgumentException> {
                    FullHosted.verifyRawFiles(root, buildJsonObject { })
                }.message,
            )
            assertEquals(
                "full hosted receipt is not a completed target",
                assertFailsWith<IllegalArgumentException> {
                    FullHosted.verifyRawFiles(root, receipt(schema = 1))
                }.message,
            )
            assertEquals(
                "both required configurations are absent, duplicated, or unordered",
                assertFailsWith<IllegalArgumentException> {
                    FullHosted.verifyRawFiles(root, receipt(lanes = JsonArray(emptyList())))
                }.message,
            )
            assertEquals(
                "passed Safari receipt contains failed source XML diagnostic metadata",
                assertFailsWith<IllegalArgumentException> {
                    FullHosted.verifyRawFiles(
                        root,
                        receipt(
                            target = "jsSafari",
                            lanes = JsonArray(
                                listOf(
                                    buildJsonObject {
                                        put("configuration", JsonPrimitive("development"))
                                        put("source_xml_diagnostic", JsonObject(emptyMap()))
                                    },
                                    buildJsonObject { put("configuration", JsonPrimitive("production")) },
                                ),
                            ),
                        ),
                    )
                }.message,
            )
            assertEquals(
                "passed Safari receipt contains failed source XML diagnostic member",
                assertFailsWith<IllegalArgumentException> {
                    FullHosted.verifyRawFiles(
                        root,
                        receipt(
                            target = "jsSafari",
                            lanes = JsonArray(
                                listOf(
                                    buildJsonObject { put("configuration", JsonPrimitive("development")) },
                                    buildJsonObject { put("configuration", JsonPrimitive("production")) },
                                ),
                            ),
                            extra = buildJsonObject {
                                put(
                                    "files",
                                    JsonArray(
                                        listOf(
                                            buildJsonObject {
                                                put(
                                                    "path",
                                                    JsonPrimitive("diagnostic/source-xml/x.xml"),
                                                )
                                            },
                                        ),
                                    ),
                                )
                            },
                        ),
                    )
                }.message,
            )
            assertEquals(
                "Gradle user home receipt is absent",
                assertFailsWith<IllegalArgumentException> {
                    FullHosted.verifyRawFiles(root, receipt())
                }.message,
            )
            assertEquals(
                "Gradle user home differs from runner environment",
                assertFailsWith<IllegalArgumentException> {
                    FullHosted.verifyRawFiles(
                        root,
                        receipt(
                            extra = buildJsonObject {
                                put("gradle_user_home", JsonPrimitive("/elsewhere/.gradle"))
                                put("runner_home", JsonPrimitive("/home/runner"))
                                put("gradle_user_home_override", JsonNull)
                            },
                        ),
                    )
                }.message,
            )
        }
    }

    test("a failed Safari lane retains its unverified source XML") {
        withHostedTemporary { root ->
            val repository = root.resolve("repository")
            val started = FullHostedRuntime.nowNs() - 1_000_000_000L
            for (module in Qualification.modules) {
                val report = repository.resolve(module)
                    .resolve("build/test-results/jsBrowserTest/TEST-all.xml")
                Files.createDirectories(report.parent)
                report.writeText(
                    """<testsuite tests="0" failures="0" errors="0" skipped="0" time="0"/>""",
                )
            }
            val process = buildJsonObject {
                put(
                    "command",
                    JsonArray(
                        listOf(
                            "gradlew", "--rerun-tasks", ":dyn4k-core:jsBrowserTest",
                            ":dyn4k:jsBrowserTest",
                            "-PqualificationInvocationId=" + "1".repeat(32),
                        ).map { JsonPrimitive(it) },
                    ),
                )
                put("pid", JsonPrimitive(ProcessHandle.current().pid()))
                put("exit_code", JsonPrimitive(0))
                put("invocation_id", JsonPrimitive("1".repeat(32)))
                put("started_ns", JsonPrimitive(started))
                put(
                    "finished_ns",
                    JsonPrimitive(FullHostedRuntime.nowNs() + 1_000_000_000L),
                )
            }
            val output = root.resolve("output/development")
            Files.createDirectories(output)
            val diagnostic = FullHosted.retainFailedSafariSourceXml(
                repository,
                output,
                process,
                IllegalArgumentException("Safari diagnostic case identities differ"),
            )
            assertEquals("UNVERIFIED", Py.str(diagnostic["status"]))
            assertEquals(
                "Safari diagnostic case identities differ",
                Py.str(diagnostic["validation_error"]),
            )
            val reports = diagnostic["reports"] as JsonArray
            assertEquals(Qualification.modules.size, reports.size)
            for (element in reports) {
                val item = element as JsonObject
                val retained = output.resolve(Py.str(item["path"])!!)
                assertTrue(Files.isRegularFile(retained))
                assertEquals(FullHosted.sha256(retained), Py.str(item["sha256"]))
            }
            // A completed process anchor is required before anything is retained.
            val failedProcess = JsonObject(process + ("exit_code" to JsonPrimitive(1)))
            assertEquals(
                "failed Safari source XML has no completed source process anchor",
                assertFailsWith<IllegalArgumentException> {
                    FullHosted.retainFailedSafariSourceXml(
                        repository,
                        output,
                        failedProcess,
                        IllegalArgumentException("x"),
                    )
                }.message,
            )
        }
    }

    test("the archive command line packages and verifies a transport archive") {
        withHostedTemporary { root ->
            val output = root.resolve("receipt")
            Files.createDirectories(output)
            output.resolve("a.txt").writeText("one\n")
            output.resolve("receipt.json").writeText("""{"status":"FAILED"}""" + "\n")
            val archive = root.resolve("transport.tar")
            assertEquals(0, FullHostedCli.run(arrayOf("--package", "--output", "$output", "--archive", "$archive")))
            val rejected = assertFailsWith<IllegalArgumentException> {
                FullHosted.verifyTransportArchive(archive, "a".repeat(40), "mingwX64")
            }
            assertEquals("transport archive candidate or target differs", rejected.message)
            assertEquals(
                1,
                FullHostedCli.run(
                    arrayOf(
                        "--verify-tar", "--archive", "$archive", "--target", "mingwX64",
                        "--candidate-sha", "a".repeat(40),
                    ),
                ),
            )
            assertEquals(2, FullHostedCli.run(arrayOf("--package", "--output", "$output")))
            assertEquals(2, FullHostedCli.run(arrayOf("--verify")))
            assertEquals(
                2,
                FullHostedCli.run(
                    arrayOf(
                        "--target", "mingwX64", "--candidate-sha", "a".repeat(40),
                        "--output", "$output",
                    ),
                ),
            )
        }
    }

    test("the transport archive rejects a duplicate, unsafe, or mis-timed member") {
        withHostedTemporary { root ->
            val output = root.resolve("receipt")
            Files.createDirectories(output)
            output.resolve("a.txt").writeText("one\n")
            output.resolve("receipt.json").writeText("""{"status":"FAILED"}""" + "\n")
            val archive = root.resolve("transport.tar")
            assertEquals(
                0,
                FullHostedCli.run(arrayOf("--package", "--output", "$output", "--archive", "$archive")),
            )
            val original = readTarMembers(archive)
            writeTarMembers(archive, original + TarMember("receipt.json", ByteArray(0), "1"))
            assertEquals(
                "duplicate transport archive path",
                assertFailsWith<IllegalArgumentException> {
                    FullHosted.verifyTransportArchive(archive, "a".repeat(40), "mingwX64")
                }.message,
            )
            assertEquals(
                0,
                FullHostedCli.run(arrayOf("--package", "--output", "$output", "--archive", "$archive")),
            )
            writeTarMembers(
                archive,
                readTarMembers(archive) + TarMember("../escape", ByteArray(0), "1"),
            )
            assertEquals(
                "unsafe archive path",
                assertFailsWith<IllegalArgumentException> {
                    FullHosted.verifyTransportArchive(archive, "a".repeat(40), "mingwX64")
                }.message,
            )
        }
    }

    test("the receipt verifier rejects an archive whose receipt is not completed") {
        withHostedTemporary { root ->
            val output = root.resolve("receipt")
            Files.createDirectories(output)
            output.resolve("receipt.json").writeText("""{"status":"FAILED"}""" + "\n")
            assertEquals(
                1,
                FullHostedCli.run(arrayOf("--verify", "--output", "$output")),
            )
            val missing = root.resolve("missing")
            Files.createDirectories(missing)
            assertEquals(1, FullHostedCli.run(arrayOf("--verify", "--output", "$missing")))
        }
    }
}
