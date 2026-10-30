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

/**
 * `tools/android-runtime/test_serial.py`.
 *
 * Two emulators share one isolated ADB server on port 5038. Selecting the wrong serial must fail before
 * any build input is read and before any install, and the chosen serial must reach the lane record.
 */
val EmulatorSerialContract by testSuite {
    test("default and selected adb route") {
        val sdk = "/sdk"
        assertEquals(
            listOf("/sdk/platform-tools/adb", "-P", "5038", "-s", "emulator-5558"),
            RunContract.adbForSerial(sdk, "emulator-5558"),
        )
        assertEquals(
            listOf("-s", "emulator-5562"),
            RunContract.adbForSerial(sdk, "emulator-5562").takeLast(2),
        )
    }

    test("rejects unselected and malformed serial before adb") {
        for (serial in listOf(
            "emulator-5560", "device-5562", "emulator-5563", "emulator-5562 ",
            "emulator-5562;id", "", "emulator-65562",
        )) {
            assertFailsWith<ArgumentTypeError>(serial) {
                RunContract.adbForSerial("/sdk", serial)
            }
        }
    }

    test("all installed runners reject a bad serial before inputs") {
        val runners = listOf(
            listOf("--build-type", "debug"),
            listOf("--provider-graph", "/missing", "--build-type", "debug", "--expected-api", "37"),
            listOf(
                "--build-type", "debug", "--expected-api", "37",
                "--provider-artifacts", "/missing", "--build-receipt", "/missing",
            ),
        )
        val names = listOf("run", "run_optimized", "run_full")
        for ((index, extra) in runners.withIndex()) {
            val failure = assertFailsWith<ArgumentTypeError>(names[index]) {
                dispatch(
                    index,
                    listOf("--prepared", "/missing", "--output", "/missing") + extra +
                        listOf("--emulator-serial", "device-5562"),
                )
            }
            assertTrue(
                failure.message!!.contains("Android emulator serial must"),
                "${names[index]}: ${failure.message}",
            )
        }
    }

    test("all installed runners accept the default and selected serial") {
        val runners = listOf(
            listOf("--build-type", "debug"),
            listOf("--provider-graph", "/missing", "--build-type", "debug", "--expected-api", "37"),
            listOf(
                "--build-type", "debug", "--expected-api", "37",
                "--provider-artifacts", "/missing", "--build-receipt", "/missing",
            ),
        )
        for ((index, extra) in runners.withIndex()) {
            for (serial in listOf(emptyList(), listOf("--emulator-serial", "emulator-5562"))) {
                val failure = assertFailsWith<java.io.FileNotFoundException>(
                    listOf(index, serial).toString(),
                ) {
                    dispatch(
                        index,
                        listOf("--prepared", "/missing", "--output", "/missing") + extra + serial,
                    )
                }
                assertTrue(failure.message!!.contains("missing"))
            }
        }
    }

    test("lane result binds the selected serial before install") {
        withTempDirectory { root ->
            val apk = writeBytes(root, "app.apk", "app".encodeToByteArray())
            val prepared = buildJsonObject {
                put("candidate_commit", JsonPrimitive("candidate"))
                put("build_jdk", JsonPrimitive("jdk"))
                put("root_build", buildJsonObject { })
                put("staged", buildJsonObject { })
                put("baseline_jar", buildJsonObject { })
                put("staged_roots", buildJsonObject { })
                put("consumer_sources", buildJsonObject { })
                put("generated_consumer_sources", buildJsonObject { })
                put("portable_jar", buildJsonObject { })
            }
            val commands = mutableListOf<List<String>>()
            val result = LaneHost.runLane(
                root = root,
                prepared = prepared,
                portable = emptySet(),
                flavor = "candidate",
                buildType = "debug",
                expectedApi = "37",
                evidenceRoot = root,
                adb = RunContract.adbForSerial(posix(root), "emulator-5562"),
                preparedPath = apk,
                preparedChecksum = "hash",
                verifySources = { _, _ -> throw IllegalArgumentException("stop before install") },
                command = { args, _, _ -> commands += args; "" },
                apkPath = { _, _, _, _ -> apk },
            )
            assertEquals("emulator-5562", result.textOrNull("emulator_serial"))
            val recorded = FullHost.parseJson(
                root.resolve("candidate-debug/result.json").toFile().readBytes(),
            )
            assertEquals("emulator-5562", recorded.textOrNull("emulator_serial"))
            assertTrue(commands.none { "install" in it })
            assertEquals("FAILED", result.textOrNull("status"))
            assertEquals("stop before install", result.textOrNull("error"))
        }
    }
}

/** Runs one installed route's command line, mapping the index to the tool. */
private fun dispatch(index: Int, argv: List<String>): Int = when (index) {
    0 -> Cli.run(argv, Path.of("/"), {})
    1 -> Cli.runOptimized(argv, Path.of("/"), {})
    else -> Cli.runFull(argv, Path.of("/"), {})
}
