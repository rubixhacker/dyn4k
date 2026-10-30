package io.github.rubixhacker.harness.android

import de.infix.testBalloon.framework.core.testSuite
import java.nio.file.Files
import java.nio.file.Path
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

private const val ADB = "/trusted/adb"

private val GUEST_EXPECTED = linkedMapOf(
    "avd_name" to "dyn4k_api37_play_x64",
    "api" to "37",
    "fingerprint" to NativeReceipt.EXPECTED_FINGERPRINT,
    "primary_abi" to "x86_64",
    "abi_list" to "x86_64,armeabi-v7a",
    "boot_completed" to "1",
)

private fun devicesRecord(listing: String): NativeCommand = NativeCommand(
    command = listOf(ADB, "-P", "5038", "devices", "-l"),
    exitCode = 0,
    stdout = listing.encodeToByteArray(),
    stderr = ByteArray(0),
)

private fun propertyRecords(values: Map<String, String>): Map<String, NativeCommand> =
    NativeReceipt.GUEST_PROPERTIES.mapValues { (property, field) ->
        NativeCommand(
            command = listOf(ADB, "-P", "5038", "-s", "emulator-5558", "shell", "getprop", property),
            exitCode = 0,
            stdout = (values.getValue(field) + "\n").encodeToByteArray(),
            stderr = ByteArray(0),
        )
    }

/**
 * `tools/android-native-runtime/test_full.py`.
 *
 * The native route runs inside the task emulator, so its evidence is the archived command records.
 * These cases replay them: guest selection, the `--ktest` listing and result grammar, the dependency
 * graph, and the source checkout identity.
 */
val NativeFullRouteContract by testSuite {
    test("live guest selects only a well formed task device") {
        val listing = "List of devices attached\n" +
            "emulator-5558\tdevice product:sdk model:task transport_id:1\n" +
            "emulator-5560\tdevice product:sdk model:other transport_id:2\n" +
            "emulator-5562\toffline\n\n"
        val devices = devicesRecord(listing)
        val properties = propertyRecords(GUEST_EXPECTED)
        val calls = mutableListOf<List<String>>()
        val guest = NativeFullHost.guestQuery(Path.of("."), ADB) { _, argv, _ ->
            calls += argv
            if (argv[3] == "devices") devices else properties.getValue(argv.last())
        }
        assertEquals(GUEST_EXPECTED, NativeFullContract.guestValues(
            (guest.getValue("observations") as JsonObject).mapValues { (_, element) ->
                (element as JsonObject).textOrNull("stdout") ?: ""
            },
        ))
        assertEquals(1 + properties.size, calls.size)
        assertEquals(devices.command, calls[0])
        for ((call, record) in calls.drop(1).zip(properties.values)) {
            assertEquals(record.command, call)
        }

        val invalid = linkedMapOf(
            "absent" to "List of devices attached\nemulator-5560\tdevice\n",
            "offline" to "List of devices attached\nemulator-5558\toffline\n",
            "unauthorized" to "List of devices attached\nemulator-5558\tunauthorized\n",
            "duplicate" to listing + "emulator-5558\tdevice transport_id:3\n",
            "missing state" to "List of devices attached\nemulator-5558\n",
            "malformed metadata" to "List of devices attached\nemulator-5558\tdevice extra\n",
            "wrong header" to "Devices\nemulator-5558\tdevice\n",
        )
        for ((name, raw) in invalid) {
            var count = 0
            assertFailsWith<IllegalArgumentException>(name) {
                NativeFullHost.guestQuery(Path.of("."), ADB) { _, _, _ ->
                    count += 1
                    devicesRecord(raw)
                }
            }
            assertEquals(1, count, name)
        }
    }

    test("archived guest replays target selection and identity") {
        val listing = "List of devices attached\n" +
            "emulator-5558\tdevice product:sdk transport_id:1\n" +
            "emulator-5560\tdevice product:sdk transport_id:2\n\n"

        fun archive(root: Path, name: String, rawListing: String, changed: Map<String, String> = emptyMap()): JsonObject {
            val values = LinkedHashMap(GUEST_EXPECTED).apply { putAll(changed) }
            val output = root.resolve(name)
            Files.createDirectories(output)
            return buildJsonObject {
                put("devices", NativeFullHost.saveCommand(output, "guest/devices", devicesRecord(rawListing)))
                put(
                    "observations",
                    JsonObject(
                        propertyRecords(values).mapValues { (property, record) ->
                            NativeFullHost.saveCommand(output, "guest/$property", record)
                        },
                    ),
                )
                put("values", JsonObject(values.mapValues { JsonPrimitive(it.value) }))
            }
        }

        withTempDirectory { root ->
            NativeFullHost.validateGuest(archive(root, "valid", listing), root, ADB)
            val invalid = linkedMapOf(
                "absent" to "List of devices attached\nemulator-5560\tdevice\n",
                "offline" to "List of devices attached\nemulator-5558\toffline\n",
                "unauthorized" to "List of devices attached\nemulator-5558\tunauthorized\n",
                "duplicate" to listing + "emulator-5558\tdevice transport_id:3\n",
                "missing state" to "List of devices attached\nemulator-5558\n",
                "malformed metadata" to "List of devices attached\nemulator-5558\tdevice extra\n",
            )
            for ((name, raw) in invalid) {
                assertFailsWith<IllegalArgumentException>(name) {
                    NativeFullHost.validateGuest(archive(root, name, raw), root, ADB)
                }
            }

            val wrongPort = archive(root, "wrong-port", listing)
            val portCommand = (wrongPort.getValue("devices") as JsonObject)
                .arrayOrNull("command")!!.toMutableList()
            portCommand[2] = JsonPrimitive("5037")
            val forgedDevices = buildJsonObject {
                put("command", kotlinx.serialization.json.JsonArray(portCommand))
                put("exit_code", JsonPrimitive(0))
                put("stdout", JsonPrimitive(listing))
                put("stderr", JsonPrimitive(""))
            }
            assertFailsWith<IllegalArgumentException> {
                NativeFullHost.validateGuest(
                    buildJsonObject {
                        put("devices", forgedDevices)
                        put("observations", wrongPort.getValue("observations"))
                        put("values", wrongPort.getValue("values"))
                    },
                    root,
                    ADB,
                )
            }
            val wrongSerial = archive(root, "wrong-serial", listing)
            val observations = (wrongSerial.getValue("observations") as JsonObject).toMutableMap()
            val sdkObservation = (observations.getValue("ro.build.version.sdk") as JsonObject)
                .arrayOrNull("command")!!.toMutableList()
            sdkObservation[4] = JsonPrimitive("emulator-5560")
            observations["ro.build.version.sdk"] = buildJsonObject {
                put("command", kotlinx.serialization.json.JsonArray(sdkObservation))
                put("exit_code", JsonPrimitive(0))
                put("stdout", JsonPrimitive("37\n"))
                put("stderr", JsonPrimitive(""))
            }
            assertFailsWith<IllegalArgumentException> {
                NativeFullHost.validateGuest(
                    buildJsonObject {
                        put("devices", wrongSerial.getValue("devices"))
                        put("observations", JsonObject(observations))
                        put("values", wrongSerial.getValue("values"))
                    },
                    root,
                    ADB,
                )
            }
            assertFailsWith<IllegalArgumentException> {
                NativeFullHost.validateGuest(
                    archive(root, "wrong-fingerprint", listing, mapOf("fingerprint" to "other/image")),
                    root,
                    ADB,
                )
            }
        }
    }

    test("root and external task markers match Gradle output") {
        assertEquals(
            "> Task :dyn4k-core:linkDebugTestAndroidNativeX64",
            NativeFullContract.buildTaskMarker(":dyn4k-core:linkDebugTestAndroidNativeX64"),
        )
        assertEquals(
            "> Task :linkReleaseExecutableAndroidNativeX64",
            NativeFullContract.buildTaskMarker("linkReleaseExecutableAndroidNativeX64"),
        )
    }

    test("adb push transfer report may be on stderr") {
        NativeFullContract.validateDeploymentOutput(
            ByteArray(0),
            "1 file pushed\n".encodeToByteArray(),
            ByteArray(0),
            "abc  /data/local/tmp/test\n".encodeToByteArray(),
            ByteArray(0),
            "abc",
        )
        assertFailsWith<IllegalArgumentException> {
            NativeFullContract.validateDeploymentOutput(
                ByteArray(0),
                "1 file pushed\n".encodeToByteArray(),
                ByteArray(0),
                "def  /data/local/tmp/test\n".encodeToByteArray(),
                ByteArray(0),
                "abc",
            )
        }
    }

    test("native listing and process require exact cases") {
        val listing = "p.AlphaTest.\n  first\n  second\np.BetaTest.\n  third\n"
        val names = NativeFullContract.parseList(listing)
        assertEquals(
            listOf("p.AlphaTest.first", "p.AlphaTest.second", "p.BetaTest.third"),
            names,
        )
        assertEquals(3, NativeFullContract.checkCases(names, names.toSet()))
        assertFailsWith<IllegalArgumentException> {
            NativeFullContract.checkCases(names.dropLast(1), names.toSet())
        }
        assertFailsWith<IllegalArgumentException> {
            NativeFullContract.checkCases(names + names.take(1), names.toSet())
        }
        assertFailsWith<IllegalArgumentException> {
            NativeFullContract.parseList(listing + "FORGED PASS\n")
        }

        val transcript = "[==========] Running 3 tests from 2 test cases.\n" +
            "[ RUN      ] p.AlphaTest.first\n" +
            "[       OK ] p.AlphaTest.first (0 ms)\n" +
            "[ RUN      ] p.AlphaTest.second\n" +
            "[       OK ] p.AlphaTest.second (1 ms)\n" +
            "[ RUN      ] p.BetaTest.third\n" +
            "[       OK ] p.BetaTest.third (0 ms)\n" +
            "[==========] 3 tests from 2 test cases ran. (1 ms total)\n" +
            "[  PASSED  ] 3 tests.\n"
        assertEquals(names, NativeFullContract.parseTestRun(transcript))
        for (mutant in listOf(
            transcript.replace(
                "[ RUN      ] p.BetaTest.third\n[       OK ] p.BetaTest.third (0 ms)\n",
                "",
            ),
            transcript.replace("[ RUN      ] p.BetaTest.third", "[ RUN      ] p.AlphaTest.first"),
            transcript + "[  PASSED  ] 3 tests.\n",
            transcript.replace("[       OK ] p.BetaTest.third", "[  FAILED  ] p.BetaTest.third"),
            transcript.replace("[       OK ] p.BetaTest.third", "[  SKIPPED ] p.BetaTest.third"),
            transcript.replace("[  PASSED  ] 3 tests.", "[  PASSED  ] 2 tests."),
        )) {
            assertFailsWith<IllegalArgumentException>(mutant.takeLast(80)) {
                NativeFullContract.parseTestRun(mutant)
            }
        }
    }

    test("dependency provider and graph changes fail") {
        val external = "androidNativeX64CompileKlibraries - Compile classpath.\n" +
            "+--- org.jetbrains.kotlin:kotlin-stdlib:2.4.20\n" +
            "+--- io.github.rubixhacker:dyn4k-core:0.1.0-alpha.1\n" +
            "|    \\--- io.github.rubixhacker:dyn4k-core-androidnativex64:0.1.0-alpha.1\n" +
            "\\--- io.github.rubixhacker:dyn4k:0.1.0-alpha.1\n" +
            "     \\--- io.github.rubixhacker:dyn4k-androidnativex64:0.1.0-alpha.1\n\n"
        assertTrue(NativeFullContract.graphSection(external, "consumer").contains("dyn4k-core"))
        for (provider in listOf(
            "org.dyn4j:dyn4j:6.0.0",
            "project :unapproved",
            "example:other:1.0",
        )) {
            assertFailsWith<IllegalArgumentException>(provider) {
                NativeFullContract.graphSection(
                    external.replace("\n\n", "\n+--- $provider\n\n"),
                    "consumer",
                )
            }
        }
    }

    test("source checkout drift fails") {
        withTempDirectory { root ->
            runGit(root, "init", "-q")
            val source = writeFile(root, "source.kt", "one\n")
            runGit(root, "add", "source.kt")
            runGit(root, "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                "commit", "-q", "-m", "fixture")
            val identity = NativeFullHost.sourceIdentity(root)
            assertEquals(40, identity.first.length)
            source.toFile().writeText("two\n")
            val dirty = assertFailsWith<IllegalArgumentException> {
                NativeFullHost.sourceIdentity(root)
            }
            assertTrue(dirty.message!!.contains("not clean"))
            source.toFile().writeText("one\n")
            writeFile(root, "extra.kt", "extra\n")
            val untracked = assertFailsWith<IllegalArgumentException> {
                NativeFullHost.sourceIdentity(root)
            }
            assertTrue(untracked.message!!.contains("not clean"))
        }
    }
}

/** Runs git in [root] and fails the test when the command fails. */
internal fun runGit(root: Path, vararg arguments: String): String {
    val process = ProcessBuilder(listOf("git", "-C", root.toString()) + arguments).start()
    val output = process.inputStream.bufferedReader().use { it.readText() }
    val error = process.errorStream.bufferedReader().use { it.readText() }
    check(process.waitFor() == 0) { "git ${arguments.toList()} failed: $output$error" }
    return output
}
