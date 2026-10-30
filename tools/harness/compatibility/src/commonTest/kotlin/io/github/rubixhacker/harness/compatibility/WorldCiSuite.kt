package io.github.rubixhacker.harness.compatibility

import de.infix.testBalloon.framework.core.testSuite
import io.github.rubixhacker.harness.contract.Sha256
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith

private val world = Vectors.worldCi

private fun worldFiles(): MemoryFiles =
    MemoryFiles(world.obj("validate_runs").obj("files").stringMap().mapKeys { "output/${it.key}" })

private fun JsonArray.withLogHash(log: String, sha256: String): List<JsonElement> = map { element ->
    val row = element.jsonObject
    if (row.str("log") == log) row.withEntry("log_sha256", sha256) else row
}

/**
 * `test_world_ci.py` cases 1 (inventory half), 2, 3, and 4, plus the recorded parity vectors for the
 * frozen mode inventory and the run log names.
 */
val WorldCiContract by testSuite {
    test("frozen sources and mode inventory") {
        val modes = world.array("modes").map {
            val row = it.jsonArray
            WorldCi.WorldMode(
                row[0].jsonPrimitive.content,
                if (row[1] is JsonNull) null else row[1].jsonPrimitive.content,
            )
        }
        assertEquals(modes, WorldCi.expectedModes())
        assertEquals(12, WorldCi.SOURCE_SHA.size)
        assertEquals(23, WorldCi.expectedModes().size)
        assertEquals(23, WorldCi.expectedModes().toSet().size)

        val files = MemoryFiles(
            world.array("validate_sources_files").associate {
                "sources/${it.jsonObject.str("path")}" to it.jsonObject.str("text")
            },
        )
        for (case in world.array("validate_sources").map { it.jsonObject }) {
            val expected = case.obj("expected").stringMap()
            assertRecordedOutcome(case.obj("result")) {
                WorldCi.validateSources(files, "sources", expected)
            }
        }
    }

    test("run log names match the recorded names") {
        for (entry in world.array("runlog")) {
            val row = entry.jsonObject
            assertEquals(
                row.str("name"),
                WorldCi.runlogName(row.str("provider"), row.str("runtime"), row.int("index")),
            )
        }
    }

    test("matrix rejects replaced or missing world mode") {
        val section = world.obj("validate_runs")
        val files = worldFiles()
        val rows = section.array("rows")
        val observed = WorldCi.validateRuns(rows, "output", files)
        assertEquals(
            section.obj("baseline_stdout").stringMap(),
            observed.entries.associate {
                "${it.key.runtime}|${it.key.main}|${it.key.mode.orEmpty()}" to it.value
            },
        )

        assertRecordedOutcome(section.obj("missing_row")) {
            WorldCi.validateRuns(rows.dropLast(1), "output", files)
        }
        assertRecordedOutcome(section.obj("duplicate_key")) {
            WorldCi.validateRuns(rows.dropLast(1) + rows.first(), "output", files)
        }

        val log = section.str("changed_log")
        val changedText = section.str("changed_stdout_text")
        assertRecordedOutcome(section.obj("changed_stdout")) {
            WorldCi.validateRuns(
                rows.withLogHash(log, Sha256.of(changedText)),
                "output",
                files.plus("output/$log", changedText),
            )
        }

        assertRecordedOutcome(section.obj("changed_hash")) {
            WorldCi.validateRuns(rows.withLogHash(log, "0".repeat(64)), "output", files)
        }

        val badText = section.str("bad_command_text")
        assertRecordedOutcome(section.obj("bad_command")) {
            WorldCi.validateRuns(
                rows.withLogHash(log, Sha256.of(badText)),
                "output",
                files.plus("output/$log", badText),
            )
        }
    }

    test("upload file set and hashes are sealed") {
        val section = world.obj("seal_files")
        val recorded = section.obj("recorded").stringMap()
        val files = MemoryFiles(section.obj("files").stringMap().mapKeys { "output/${it.key}" })

        assertEquals(recorded, WorldCi.sealFiles("output", recorded, files))
        assertRecordedOutcome(section.obj("missing")) {
            WorldCi.sealFiles(
                "output",
                recorded,
                files.minus("output/sources/WorldListSemanticsConsumer.java"),
            )
        }
        assertRecordedOutcome(section.obj("changed")) {
            WorldCi.sealFiles(
                "output",
                recorded,
                files.plus("output/sources/WorldListSemanticsConsumer.java", "changed"),
            )
        }
        assertRecordedOutcome(section.obj("extra")) {
            WorldCi.sealFiles("output", recorded, files.plus("output/extra.txt", "extra"))
        }
        assertEquals(
            recorded,
            WorldCi.sealFiles("output", recorded, files.plus("output/result.json", "report")),
        )
        assertRecordedOutcome(section.obj("empty_recorded")) {
            WorldCi.sealFiles("output", emptyMap(), files)
        }
    }

    test("bad body-view must fail on specific world semantics") {
        for (case in world.array("adverse").map { it.jsonObject }) {
            assertRecordedOutcome(case.obj("result")) {
                WorldCi.validateAdverseOutput(case.str("baseline"), case.str("mutant"))
            }
        }
        assertEquals(
            "World body-view adverse control did not expose the known serialization regression",
            assertFailsWith<IllegalArgumentException> {
                WorldCi.validateAdverseOutput(
                    "bodies,empty=VALUE:232:abc\n",
                    "bodies,empty=VALUE:232:abc\n",
                )
            }.message,
        )
    }
}
