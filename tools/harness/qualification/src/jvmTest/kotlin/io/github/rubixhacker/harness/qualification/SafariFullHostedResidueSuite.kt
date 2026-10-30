package io.github.rubixhacker.harness.qualification

import de.infix.testBalloon.framework.core.testSuite
import io.github.rubixhacker.harness.contract.StrictJson
import java.nio.file.Files
import java.nio.file.Path
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

/**
 * `test_public_full_hosted_receipt_records_staging_setup_residue`.
 *
 * The reference patches `full_hosted.run`'s seams and replaces the Windows `LockedDirectory` with a
 * fake whose `child` refuses the staging handle. The real `safari_reporter.stage` then leaves
 * `CHANGED`/`LEFTOVER`, raises `StageFailure`, and `run` records `error.result` on the lane before
 * the lane's failure handler turns it into `FAILED`. Two facts matter: the receipt on disk is the
 * receipt in memory, and `run_command` ran exactly once — the stage command, never the test task.
 */
val SafariFullHostedResidueSuite by testSuite {
    test("the full hosted receipt records staging setup residue") {
        withFixture { fixture ->
            val repository = fixture.repository
            Files.writeString(repository.resolve(FullHosted.MAPPING), "fixture\n")
            Files.writeString(repository.resolve(FullHosted.PAIRS), "fixture\n")
            val output = fixture.root.resolve("full-hosted")
            val hashes = buildJsonObject {
                put("dyn4k-core", JsonPrimitive("a".repeat(64)))
                put("dyn4k", JsonPrimitive("b".repeat(64)))
            }
            var runCommands = 0
            val directories = SafariLockedDirectoryFactory { source, relative ->
                object : SafariLockedDirectory {
                    override val path: Path = source.resolve(relative)
                    override fun child(name: String, removable: Boolean): SafariLockedDirectory =
                        throw SafariFileError("injected Win32 stage handle failure")
                    override fun openFile(name: String): SafariHandle = error("unused")
                    override fun removeEmpty() = error("unused")
                    override fun close() {}
                }
            }
            val seams = FullHostedRunSeams(
                windows = true,
                windowsDirectories = directories,
                loadCorpus = { _, _ ->
                    buildJsonObject {
                        put("source_files", JsonArray(emptyList()))
                        put("source_tree_sha256", JsonPrimitive("c".repeat(64)))
                    }
                },
                discoverRuntime = { target ->
                    assertEquals("jsSafari", target)
                    buildJsonObject {
                        put("system", JsonPrimitive("Darwin"))
                        put("machine", JsonPrimitive("arm64"))
                        put("java_version", JsonPrimitive("21.0.12"))
                    }
                },
                runtimeStatus = { _, _ -> HostedVerdict("READY", "") },
                gradleWrapper = { "gradlew" },
                toolVersion = { _, _ -> "9.5.0" },
                requirePinnedToolchain = {},
                runCommand = { command, _, _, _ ->
                    runCommands += 1
                    assertEquals("gradlew", command.first())
                    buildJsonObject { put("exit_code", JsonPrimitive(0)) }
                },
                targetHashes = { _, target ->
                    assertEquals("js", target)
                    hashes
                },
                captureStaging = { _, _, targets, _ ->
                    assertEquals(listOf("js"), targets)
                    CapturedStaging(
                        mutableListOf(),
                        mutableListOf(),
                        mutableMapOf("js" to hashes),
                        JsonNull,
                    )
                },
                captureDokkaOutput = { _, _, _ -> },
                inputs = listOf("tools/qualification/safari-launch.sh"),
                configs = mapOf("jsSafari" to listOf("development")),
            )
            val receipt = FullHostedRun.run(
                repository,
                fixture.candidate,
                "jsSafari",
                output,
                seams,
            )
            assertEquals("FAILED", Py.str(receipt["status"]))
            val lane = (receipt["configurations"] as JsonArray)[0] as JsonObject
            assertEquals("FAILED", Py.str(lane["status"]))
            val stage = lane["safari_reporter_stage"] as JsonObject
            val source = stage["source"] as JsonObject
            assertEquals("LEFTOVER", Py.str((source["projects"] as JsonObject)["dyn4k-core"]))
            assertEquals(
                "dyn4k-core/karma.config.d",
                Py.str(((source["forensic"] as JsonArray)[0] as JsonObject)["path"]),
            )
            assertTrue(
                (Py.str(lane["reason"]) ?: "").startsWith("Safari reporter staging residue: "),
            )
            assertFalse(lane.containsKey("source_process"))
            val written = StrictJson.load(
                Files.readString(output.resolve("receipt.json")),
            ) as JsonObject
            assertEquals(written, receipt)
            assertEquals(1, runCommands)
        }
    }
}
