package io.github.rubixhacker.harness.qualification

import de.infix.testBalloon.framework.core.testSuite
import io.github.rubixhacker.harness.contract.Qualification
import io.github.rubixhacker.harness.contract.Sha256
import io.github.rubixhacker.harness.contract.StrictJson
import java.nio.file.Files
import java.nio.file.Path
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

private const val CANDIDATE = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

/**
 * `hosted.py`: the runtime identity rules, the hosted summary, the frozen probe groups, the
 * staged binary hashes, and the probe reports the summary depends on.
 *
 * The recorded vectors in [HostedSafariVectors] were produced by `hosted.py` at the revision it
 * names; the fixture-based cases below are the reference's own `unittest` cases, replayed against
 * this host.
 */
val HostedSuite by testSuite {
    for (vector in HostedSafariVectors.RUNTIME) {
        test("runtime_status: ${vector.label}") {
            val verdict = Hosted.runtimeStatus(vector.target, StrictJson.load(vector.observed))
            assertEquals(vector.status, verdict.status, vector.label)
            assertEquals(vector.reason, verdict.reason, vector.label)
        }
    }

    test("xcode output parsing preserves the exact version") {
        for ((xcode, version, build, status) in listOf(
            listOf("Xcode 26.5\nBuild version 17F42", "26.5", "Build version 17F42", "READY"),
            listOf("Xcode 26.4.1\nBuild version 17E303", "26.4.1", "Build version 17E303", "FAILED"),
        )) {
            val host = RecordedHost(
                "Darwin",
                "arm64",
                outputs = mapOf(
                    "sw_vers" to HostedCapture(0, "26.5.1\n", ""),
                    "xcodebuild" to HostedCapture(0, xcode + "\n", ""),
                    "java" to HostedCapture(0, "", "openjdk version \"21.0.1\" 2026-01-01\n"),
                ),
            )
            val observed = HostedHost.discoverRuntime("macosArm64", host)
            assertEquals(version, Py.str(observed["xcode_version"]), xcode)
            assertEquals(build, Py.str(observed["xcode_build"]), xcode)
            assertEquals(status, Hosted.runtimeStatus("macosArm64", observed).status, xcode)
            // `macosArm64` has no simulator family, so the probe must not ask for the device list.
            assertTrue(host.commands.none { it.first() == "xcrun" }, host.commands.toString())
            assertTrue(host.commands.none { it.first() == "safaridriver" }, host.commands.toString())
        }
    }

    test("the browser runtime probe records simulators and Safari versions") {
        val listing = """{"devices":{
            "com.apple.CoreSimulator.SimRuntime.iOS-26-0":[
                {"name":"iPhone 17","udid":"AAAA","isAvailable":true},
                {"name":"Gone","udid":"BBBB","isAvailable":false}],
            "com.apple.CoreSimulator.SimRuntime.tvOS-26-0":[
                {"name":"Apple TV","udid":"CCCC"}],
            "com.apple.CoreSimulator.SimRuntime.watchOS-26-0":[
                {"name":"Watch","udid":"DDDD","isAvailable":true}],
            "com.apple.CoreSimulator.SimRuntime.xrOS-26-0":[
                {"name":"Vision","udid":"EEEE"}]
        }}"""
        val host = RecordedHost(
            "Darwin",
            "arm64",
            environment = mapOf("ImageOS" to "macos26", "ImageVersion" to "20261001.1"),
            outputs = mapOf(
                "sw_vers" to HostedCapture(0, "26.6.2\n", ""),
                "xcodebuild" to HostedCapture(0, "Xcode 26.5\nBuild version 17F42\n", ""),
                "java" to HostedCapture(0, "", "openjdk version \"21.0.12\" 2026-01-01\n"),
                "xcrun" to HostedCapture(0, listing, ""),
                "defaults" to HostedCapture(0, "26.6.2\n", ""),
                "safaridriver" to HostedCapture(0, "SafariDriver 26.6.2\n", ""),
            ),
        )
        val native = HostedHost.discoverRuntime("iosSimulatorArm64", host)
        assertEquals(
            listOf("system", "machine", "os_version", "runner_image_os", "runner_image_version",
                "java_version", "xcode_version", "xcode_build", "simulators"),
            native.keys.toList(),
        )
        assertEquals("macos26", Py.str(native["runner_image_os"]))
        assertEquals("21.0.12", Py.str(native["java_version"]))
        assertEquals(
            """{"iOS":[{"name":"iPhone 17","udid":"AAAA","runtime":"com.apple.CoreSimulator.SimRuntime.iOS-26-0"}],""" +
                """"tvOS":[{"name":"Apple TV","udid":"CCCC","runtime":"com.apple.CoreSimulator.SimRuntime.tvOS-26-0"}],""" +
                """"watchOS":[{"name":"Watch","udid":"DDDD","runtime":"com.apple.CoreSimulator.SimRuntime.watchOS-26-0"}]}""",
            PyJson.renderDefault(native.getValue("simulators")).replace(", ", ",").replace(": ", ":"),
        )
        assertEquals("READY", Hosted.runtimeStatus("iosSimulatorArm64", native).status)
        assertEquals(1, host.commands.count { it.first() == "xcrun" })

        // `jsSafari` is not a native target, so its probe never asks for a device list.
        val safari = HostedHost.discoverRuntime("jsSafari", host)
        assertEquals("{}", PyJson.renderDefault(safari.getValue("simulators")))
        assertEquals("26.6.2", Py.str(safari["safari_version"]))
        assertEquals("SafariDriver 26.6.2", Py.str(safari["safaridriver_version"]))
        assertEquals("READY", Hosted.runtimeStatus("jsSafari", safari).status)
        assertEquals(1, host.commands.count { it.first() == "xcrun" })
    }

    test("staged web publications bind klib binaries") {
        for (target in listOf("js", "wasmJs", "wasmWasi")) {
            for (module in Qualification.modules) {
                assertTrue(
                    Qualification.targetBinaryPath(module, target).endsWith(".klib"),
                    "$module/$target",
                )
            }
        }
    }

    test("a non-Darwin host is reported without mac commands") {
        val host = DefaultHostEnvironment
        val observed = HostedHost.discoverRuntime("macosArm64", host)
        assertEquals(host.system(), Py.str(observed["system"]))
        if (host.system() != "Darwin") {
            assertNull(observed["xcode_version"], "macOS-only observations must be absent")
            assertNull(observed["simulators"], "macOS-only observations must be absent")
            assertNull(observed["safari_version"], "macOS-only observations must be absent")
            assertEquals("FAILED", Hosted.runtimeStatus("macosArm64", observed).status)
        }
    }

    test("frozen native groups pin source and staged consumer cases") {
        val manifest = foundationManifest()
        val groups = groups(manifest)
        for (target in Hosted.NATIVE_TARGETS.keys) {
            assertEquals(45, ProbeManifest.expectedCases(manifest, groups.getValue(target)).size, target)
            assertEquals(
                1066,
                ProbeManifest.expectedCases(manifest, groups.getValue("core-$target")).size,
                target,
            )
            assertEquals(
                3,
                ProbeManifest.expectedCases(manifest, groups.getValue("consumer-$target")).size,
                target,
            )
        }
        assertEquals(47, ProbeManifest.expectedCases(manifest, groups.getValue("jvm")).size)
        assertEquals(
            listOf(
                ProbeCase(
                    "jsBrowserTest.qualification.StagedGeometryTest",
                    "namedConstructorsResolveFromPublishedCommonAndPlatformVariants" +
                        "[js, browser, Safari26.6.2, MacOS10.15.7]",
                ),
                ProbeCase(
                    "jsBrowserTest.qualification.StagedGeometryTest",
                    "stagedRootCoordinatesResolveAndTransformSharedObjects" +
                        "[js, browser, Safari26.6.2, MacOS10.15.7]",
                ),
                ProbeCase(
                    "jsBrowserTest.qualification.StagedFoundationExtraMethodsTest",
                    "publishedAliasesRetainKotlinHelpersAndGetterOverrides" +
                        "[js, browser, Safari26.6.2, MacOS10.15.7]",
                ),
            ),
            ProbeManifest.expectedCases(manifest, groups.getValue("consumer-jsSafari")),
        )
    }

    test("stale or partial staged consumer xml fails") {
        val manifest = foundationManifest()
        val group = groups(manifest).getValue("consumer-macosArm64")
        val root = Files.createTempDirectory("hosted-probe")
        try {
            Files.writeString(
                root.resolve("report.xml"),
                "<testsuite tests=\"1\" failures=\"0\" errors=\"0\" skipped=\"0\">" +
                    "<testcase classname=\"macosArm64Test.qualification.StagedGeometryTest\" " +
                    "name=\"stagedRootCoordinatesResolveAndTransformSharedObjects[macosArm64]\" " +
                    "time=\"0\"/></testsuite>",
            )
            val selected = JsonObject(
                manifest + (
                    "groups" to JsonArray(
                        listOf(JsonObject(group + ("report_pattern" to JsonPrimitive("report.xml")))),
                    )
                    ),
            )
            val stale = ProbeRunner.run(
                listOf("sh", "-c", "true"),
                listOf("report.xml"),
                CANDIDATE,
                root.resolve("stale.json"),
                selected,
                root,
            )
            assertEquals("PROBE_FAILED", Py.str(stale.report["status"]))
            assertTrue(
                (Py.str(stale.report["reason"]) ?: "").contains("missing report"),
                Py.str(stale.report["reason"]) ?: "",
            )
            val partial = ProbeRunner.run(
                listOf(
                    "sh", "-c",
                    "printf '%s' '<testsuite tests=\"0\" failures=\"0\" errors=\"0\" " +
                        "skipped=\"0\"/>' > report.xml",
                ),
                listOf("report.xml"),
                CANDIDATE,
                root.resolve("partial.json"),
                selected,
                root,
            )
            assertEquals("PROBE_FAILED", Py.str(partial.report["status"]))
            assertTrue(
                (Py.str(partial.report["reason"]) ?: "").contains("missing selected"),
                Py.str(partial.report["reason"]) ?: "",
            )
        } finally {
            deleteRecursively(root)
        }
    }

    test("the Safari report requires the frozen browser case identity") {
        val manifest = foundationManifest()
        val group = groups(manifest).getValue("consumer-jsSafari")
        val cases = ProbeManifest.expectedCases(manifest, group)
        val root = Files.createTempDirectory("hosted-safari-probe")
        try {
            val selected = JsonObject(
                manifest + (
                    "groups" to JsonArray(
                        listOf(JsonObject(group + ("report_pattern" to JsonPrimitive("report.xml")))),
                    )
                    ),
            )
            val wrongRuntime = cases.map { it.copy(name = it.name.replace("Safari26.6.2", "Safari26.6.3")) }
            val unexpected = cases + ProbeCase(
                cases.first().classname,
                "unexpectedCase[js, browser, Safari26.6.2, MacOS10.15.7]",
            )
            for ((observed, expectedStatus, executed) in listOf(
                Triple(cases, "PROBE_PASSED", cases.size),
                Triple(wrongRuntime, "PROBE_FAILED", 0),
                Triple(unexpected, "PROBE_PASSED", cases.size),
            )) {
                Files.writeString(root.resolve("template.xml"), suiteXml(observed))
                val result = ProbeRunner.run(
                    listOf("sh", "-c", "cp template.xml report.xml"),
                    listOf("report.xml"),
                    CANDIDATE,
                    root.resolve("result.json"),
                    selected,
                    root,
                )
                assertEquals(expectedStatus, Py.str(result.report["status"]))
                assertEquals(executed.toLong(), Py.int(result.report["executed"]))
                assertEquals(observed.size.toLong(), Py.int(result.report["reported"]))
            }
        } finally {
            deleteRecursively(root)
        }
    }

    test("the runtime identity rejects a wrong host and a wrong Xcode") {
        val mac = JsonObject(
            linkedMapOf(
                "system" to JsonPrimitive("Darwin"),
                "machine" to JsonPrimitive("arm64"),
                "os_version" to JsonPrimitive("26.6.2"),
                "xcode_version" to JsonPrimitive("26.5"),
                "xcode_build" to JsonPrimitive("Build version 17F42"),
                "simulators" to JsonObject(linkedMapOf("iOS" to JsonArray(listOf(JsonPrimitive("iPhone 17"))))),
            ),
        )
        assertEquals("READY", Hosted.runtimeStatus("iosSimulatorArm64", mac).status)
        assertEquals(
            "READY",
            Hosted.runtimeStatus(
                "iosSimulatorArm64",
                JsonObject(mac + ("xcode_build" to JsonPrimitive("Build version 18A1"))),
            ).status,
        )
        assertEquals(
            "FAILED",
            Hosted.runtimeStatus(
                "iosSimulatorArm64",
                JsonObject(mac + ("xcode_version" to JsonPrimitive("26.4.1"))),
            ).status,
        )
        assertEquals(
            "FAILED",
            Hosted.runtimeStatus(
                "iosSimulatorArm64",
                JsonObject(mac + ("machine" to JsonPrimitive("x86_64"))),
            ).status,
        )
        assertEquals(
            "FAILED",
            Hosted.runtimeStatus(
                "iosSimulatorArm64",
                JsonObject(mac + ("xcode_version" to JsonPrimitive("26.6"))),
            ).status,
        )
        assertEquals(
            "FAILED",
            Hosted.runtimeStatus(
                "mingwX64",
                JsonObject(
                    linkedMapOf(
                        "system" to JsonPrimitive("Windows"),
                        "machine" to JsonPrimitive("AMD64"),
                        "os_version" to JsonPrimitive("10.0.19045"),
                    ),
                ),
            ).status,
        )
    }

    test("the runtime requires a retained valid Xcode build") {
        val mac = buildJsonObjectOf(
            "system" to JsonPrimitive("Darwin"),
            "machine" to JsonPrimitive("arm64"),
            "os_version" to JsonPrimitive("26.5.1"),
            "xcode_version" to JsonPrimitive("26.5"),
            "xcode_build" to JsonPrimitive("Build version 17F42"),
            "simulators" to JsonObject(emptyMap()),
        )
        assertEquals("READY", Hosted.runtimeStatus("macosArm64", mac).status)
        for (build in listOf(
            null,
            JsonPrimitive(""),
            JsonPrimitive("Build version "),
            JsonPrimitive("Build version    "),
            JsonPrimitive("Build version 17 F42"),
            JsonPrimitive("Build version 17F42!"),
            JsonPrimitive("17F42"),
        )) {
            val observed = if (build == null) {
                JsonObject(mac - "xcode_build")
            } else {
                JsonObject(mac + ("xcode_build" to build))
            }
            assertEquals("FAILED", Hosted.runtimeStatus("macosArm64", observed).status, build.toString())
        }
    }

    test("an absent simulator or Safari is unavailable") {
        val mac = buildJsonObjectOf(
            "system" to JsonPrimitive("Darwin"),
            "machine" to JsonPrimitive("arm64"),
            "os_version" to JsonPrimitive("26.6.2"),
            "xcode_version" to JsonPrimitive("26.5"),
            "xcode_build" to JsonPrimitive("Build version 17F42"),
            "simulators" to JsonObject(emptyMap()),
        )
        assertEquals("UNAVAILABLE", Hosted.runtimeStatus("iosSimulatorArm64", mac).status)
        assertEquals(
            "UNAVAILABLE",
            Hosted.runtimeStatus(
                "jsSafari",
                JsonObject(
                    mac + mapOf(
                        "safari_version" to JsonPrimitive(""),
                        "safaridriver_version" to JsonPrimitive(""),
                    ),
                ),
            ).status,
        )
    }

    test("a staged target requires both matching binary checksums") {
        val staging = Files.createTempDirectory("hosted-hashes")
        try {
            for (module in Qualification.modules) {
                val binary = staging.resolve(Qualification.targetBinaryPath(module, "mingwX64"))
                binary.parent?.let { Files.createDirectories(it) }
                Files.write(binary, module.encodeToByteArray())
                Files.writeString(
                    binary.resolveSibling(binary.fileName.toString() + ".sha256"),
                    Sha256.of(module.encodeToByteArray()) + "\n",
                )
            }
            assertEquals(
                Qualification.modules.toSet(),
                HostedHost.targetHashes(staging, "mingwX64").keys,
            )
            val broken = staging.resolve(Qualification.targetBinaryPath("dyn4k", "mingwX64"))
            Files.write(broken, "changed".toByteArray())
            assertEquals(
                "dyn4k target binary checksum differs from staged file",
                assertFailsWithMessage { HostedHost.targetHashes(staging, "mingwX64") },
            )
            Files.delete(broken)
            assertEquals(
                "dyn4k target binary or checksum is missing",
                assertFailsWithMessage { HostedHost.targetHashes(staging, "mingwX64") },
            )
        } finally {
            deleteRecursively(staging)
        }
    }

    for (vector in HostedSafariVectors.HOSTED) {
        test("hosted_status: ${vector.label}") {
            val manifest = foundationManifest()
            val verdict = Hosted.hostedStatus(
                vector.target,
                CANDIDATE,
                StrictJson.load(vector.runtime),
                vector.source?.let { StrictJson.load(it) },
                vector.consumer?.let { StrictJson.load(it) },
                vector.hashes?.let { StrictJson.load(it) },
                manifest,
            )
            assertEquals(vector.status, verdict.status, vector.label)
            assertEquals(vector.reason, verdict.reason, vector.label)
        }
    }

    for (vector in HostedSafariVectors.GROUPS) {
        test("selected_groups: ${vector.label}") {
            val manifest = foundationManifest()
            if (vector.error.isNotEmpty()) {
                assertEquals(
                    vector.error,
                    assertFailsWithMessage { Hosted.selectedGroups(manifest, vector.ids) },
                )
            } else {
                val (selected, patterns) = Hosted.selectedGroups(manifest, vector.ids)
                assertEquals(
                    strings(StrictJson.load(vector.keys)),
                    selected.keys.toList(),
                    "top-level keys",
                )
                assertEquals(
                    StrictJson.load(vector.groups),
                    selected["groups"],
                    "selected groups",
                )
                assertEquals(vector.patterns, patterns)
            }
        }
    }

    for (vector in HostedSafariVectors.WRAPPERS) {
        test("gradle_wrapper: ${vector.label}") {
            assertEquals(
                vector.path,
                Hosted.gradleWrapper(vector.repository, vector.windows),
            )
        }
    }

    test("the bounded hosted result cannot promote a full lane") {
        // `qualify.validate_hosted_probe` is not ported (see the port report), so the verdict on
        // the bounded summary and the lane evaluation are what this test can hold:
        // a passing bounded summary still leaves the lane unexecuted.
        val vector = HostedSafariVectors.HOSTED.first { it.label == "ready" }
        val verdict = Hosted.hostedStatus(
            vector.target,
            CANDIDATE,
            StrictJson.load(vector.runtime),
            vector.source?.let { StrictJson.load(it) },
            vector.consumer?.let { StrictJson.load(it) },
            vector.hashes?.let { StrictJson.load(it) },
            foundationManifest(),
        )
        assertEquals("PROBE_PASSED", verdict.status)
        val lane = Qualification.expand().first { it.target == "macosArm64" }
        val evaluated = LaneEvaluation.evaluate(lane, null, CANDIDATE)
        assertEquals("NOT_RUN", evaluated.status)
        assertEquals("no evidence supplied", evaluated.reason)
    }

    test("the recorded vectors name their reference revision") {
        assertTrue(HostedSafariVectors.REVISION.matches(Regex("[0-9a-f]{40}")))
        assertEquals(
            "tools/harness/qualification/parity/generate_hosted_safari_vectors.py",
            HostedSafariVectors.GENERATOR,
        )
    }

    test("run_hosted stops at a rejected runtime and still writes the probe") {
        val root = Files.createTempDirectory("hosted-run")
        try {
            Files.writeString(root.resolve("build.gradle.kts"), "plugins { }\n")
            val output = root.resolve("probe.json")
            var staged = false
            val result = HostedHost.runHosted(
                "macosArm64",
                CANDIDATE,
                output,
                HostedHost.HostedDependencies(
                    repository = root,
                    host = RecordedHost("Linux", "x86_64"),
                    requireCleanCheckout = { _, _ -> },
                    stage = { _, _, _, _, _ ->
                        staged = true
                        JsonObject(emptyMap())
                    },
                ),
            )
            assertTrue(!staged)
            assertEquals("FAILED", Py.str(result["status"]))
            assertEquals(
                "runner OS or architecture differs from selected target",
                Py.str(result["reason"]),
            )
            assertEquals("Linux", Py.str((result["runtime"] as JsonObject)["system"]))
            assertEquals(
                PyJson.render(result) + "\n",
                Files.readString(output),
                "the probe is written in the reference's indentation",
            )
        } finally {
            deleteRecursively(root)
        }
    }

    test("run_hosted records a failed staging receipt and stops before the audit") {
        val root = Files.createTempDirectory("hosted-stage")
        try {
            Files.writeString(root.resolve("build.gradle.kts"), "plugins { }\n")
            val output = root.resolve("probe.json")
            val wrapper = root.resolve("gradlew").toString()
            var audited = false
            val result = HostedHost.runHosted(
                "macosArm64",
                CANDIDATE,
                output,
                HostedHost.HostedDependencies(
                    repository = root,
                    host = RecordedHost(
                        "Darwin",
                        "arm64",
                        outputs = mapOf(
                            "sw_vers" to HostedCapture(0, "26.6.2\n", ""),
                            "xcodebuild" to HostedCapture(0, "Xcode 26.5\nBuild version 17F42\n", ""),
                            "java" to HostedCapture(0, "", "openjdk version \"21.0.1\"\n"),
                            wrapper to HostedCapture(0, "Gradle 9.5.0\n", ""),
                        ),
                    ),
                    requireCleanCheckout = { _, _ -> },
                    stage = { _, _, _, receiptPath, _ ->
                        Files.createDirectories(receiptPath.parent)
                        Files.writeString(receiptPath, "{}\n")
                        buildJsonObjectOf(
                            "status" to JsonPrimitive("FAILED"),
                            "reason" to JsonPrimitive("staging failed"),
                            "command" to JsonArray(listOf(JsonPrimitive(wrapper))),
                        )
                    },
                    audit = { _, _, _, _, _, _ ->
                        audited = true
                        JsonObject(emptyMap())
                    },
                ),
            )
            assertTrue(!audited, "a failed staging run must not be audited")
            assertEquals("PROBE_FAILED", Py.str(result["status"]))
            assertEquals("staging failed", Py.str(result["reason"]))
            assertEquals(
                "[\"$wrapper\"]",
                PyJson.renderDefault(result.getValue("stage_command")),
            )
            assertEquals("9.5.0", Py.str((result["runtime"] as JsonObject)["gradle_version"]))
            assertEquals("", Py.str((result["runtime"] as JsonObject)["kgp_declared_version"]))
            assertEquals(
                Sha256.of("{}\n".toByteArray()),
                Py.str(result["stage_receipt_sha256"]),
            )
            assertEquals(
                "PROBE_FAILED",
                Py.str((StrictJson.load(Files.readString(output)) as JsonObject)["status"]),
            )
        } finally {
            deleteRecursively(root)
        }
    }

    test("the hosted command line requires run, a target, a candidate, and an output") {
        assertEquals(2, HostedCli.run(emptyArray()))
        assertEquals(2, HostedCli.run(arrayOf("probe", "--candidate-sha", CANDIDATE)))
        assertEquals(2, HostedCli.run(arrayOf("run", "--candidate-sha", CANDIDATE, "--target", "jvm")))
        assertEquals(
            2,
            HostedCli.run(arrayOf("run", "--candidate-sha", CANDIDATE, "--target", "macosArm64")),
        )
    }
}

/** A host whose observations and command output are recorded instead of measured. */
internal class RecordedHost(
    private val systemName: String,
    private val machineName: String,
    private val platformVersion: String = "",
    private val environment: Map<String, String> = emptyMap(),
    private val outputs: Map<String, HostedCapture> = emptyMap(),
) : HostEnvironment {
    val commands = mutableListOf<List<String>>()

    override fun system(): String = systemName

    override fun machine(): String = machineName

    override fun platformVersion(): String = platformVersion

    override fun environment(name: String): String? = environment[name]

    override fun run(command: List<String>): HostedCapture {
        commands.add(command)
        return outputs[command.first()] ?: HostedCapture(127, "", "command not found")
    }
}

internal fun foundationManifest(): JsonObject =
    StrictJson.load(
        Fs.readText(repositoryRoot().resolve("tools/qualification/foundation-probes.json")),
    ) as JsonObject

internal fun groups(manifest: JsonObject): Map<String, JsonObject> {
    val result = LinkedHashMap<String, JsonObject>()
    for (item in manifest["groups"] as JsonArray) {
        val group = item as JsonObject
        result[Py.str(group["id"])!!] = group
    }
    return result
}

private fun strings(value: kotlinx.serialization.json.JsonElement): List<String> =
    (value as JsonArray).map { Py.str(it)!! }

private fun suiteXml(cases: List<ProbeCase>): String =
    "<testsuite tests=\"${cases.size}\" failures=\"0\" errors=\"0\" skipped=\"0\" time=\"0.1\">" +
        cases.joinToString("") {
            "<testcase classname=\"${it.classname}\" name=\"${it.name}\" time=\"0.1\"/>"
        } +
        "</testsuite>"

internal fun assertFailsWithMessage(block: () -> Unit): String =
    try {
        block()
        error("the call was expected to fail")
    } catch (error: IllegalArgumentException) {
        error.message ?: ""
    }

internal fun buildJsonObjectOf(
    vararg pairs: Pair<String, kotlinx.serialization.json.JsonElement>,
): JsonObject = JsonObject(linkedMapOf(*pairs))
