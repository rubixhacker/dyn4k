package io.github.rubixhacker.harness.migration

import de.infix.testBalloon.framework.core.testSuite
import java.nio.file.Files
import java.util.Base64
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/** The command entry points: argv handling, stdout text, written receipts, and exit codes. */
val MigrationCliContract by testSuite {
    val valid: ByteArray = Base64.getDecoder().decode(
        (VectorData.section("valid_png_base64") as PyValue.Text).value,
    )

    test("validate_scene writes the recorded result and exits nonzero") {
        val record = (VectorData.section("scene_validation") as PyValue.Seq).items.first {
            (it.get("case") as PyValue.Text).value == "headless_exception_tracking"
        }
        val folder = Files.createTempDirectory("dyn4k-cli-scene-")
        try {
            MigrationFiles.writeText(
                folder.resolve("observer.log"),
                (record.get("log") as PyValue.Text).value,
            )
            MigrationFiles.writeText(
                folder.resolve("inputs.log"),
                (record.get("inputs") as PyValue.Text).value,
            )
            val code = ValidateSceneCli.run(
                listOf(
                    "Tracking",
                    folder.resolve("observer.log").toString(),
                    folder.resolve("inputs.log").toString(),
                    folder.resolve("result.json").toString(),
                ),
            )
            assertEquals(1, code)
            assertEquals(
                (record.get("result_text") as PyValue.Text).value,
                MigrationFiles.readTextOrEmpty(folder.resolve("result.json"))
                    .replace(folder.toString(), "<work>"),
            )
        } finally {
            deleteTree(folder)
        }
    }

    test("validate_plain admits a complete Truck directory and exits zero") {
        val folder = Files.createTempDirectory("dyn4k-cli-plain-")
        try {
            makePlainTruck(folder, valid)
            val code = ValidatePlainCli.run(listOf("Truck", folder.toString()))
            assertEquals(0, code)
            val written = pyFromJson(
                kotlinx.serialization.json.Json.parseToJsonElement(
                    MigrationFiles.readTextOrEmpty(folder.resolve("plain-validation.json")),
                ),
            )
            assertEquals(19L, (written.get("expected") as PyValue.Int).value)
            assertEquals(0L, (written.get("failed") as PyValue.Int).value)
            assertEquals("UNREVIEWED", (written.get("visual_review_status") as PyValue.Text).value)
        } finally {
            deleteTree(folder)
        }
    }

    test("validate_plain summary totals and exit code follow the scene results") {
        val root = Files.createTempDirectory("dyn4k-cli-summary-")
        try {
            for (scene in PlainValidation.SCENES) {
                Files.createDirectories(root.resolve(scene))
                val executed = PlainValidation.EXPECTED.getValue(scene)
                MigrationFiles.writeText(
                    root.resolve(scene).resolve("plain-validation.json"),
                    PyJson.prettyLine(
                        pyMap(
                            "executed" to pyInt(executed),
                            "failed" to pyInt(if (scene == "Truck") 1 else 0),
                        ),
                    ),
                )
            }
            assertEquals(1, ValidatePlainCli.run(listOf("--summary", root.toString())))
            val summary = pyFromJson(
                kotlinx.serialization.json.Json.parseToJsonElement(
                    MigrationFiles.readTextOrEmpty(root.resolve("check-summary.json")),
                ),
            )
            val totals = summary.get("totals")
            assertEquals(57L, (totals.get("expected") as PyValue.Int).value)
            assertEquals(57L, (totals.get("executed") as PyValue.Int).value)
            assertEquals(0L, (totals.get("unexecuted") as PyValue.Int).value)
            assertEquals(1L, (totals.get("failed") as PyValue.Int).value)
        } finally {
            deleteTree(root)
        }
    }

    test("journeys unavailable CLI writes the recorded summary") {
        val folder = Files.createTempDirectory("dyn4k-cli-unavailable-")
        try {
            val code = JourneysCli.run(
                listOf("unavailable", "--output", folder.toString(), "--reason", "no display"),
            )
            assertEquals(0, code)
            val recorded = VectorData.section("journeys").get("unavailable_empty")
            assertEquals(
                (recorded.get("summary_text") as PyValue.Text).value,
                MigrationFiles.readTextOrEmpty(folder.resolve("summary.json")),
            )
            assertEquals(
                (recorded.get("evidence_text") as PyValue.Text).value,
                MigrationFiles.readTextOrEmpty(folder.resolve("evidence.sha256")),
            )
            assertEquals(0, JourneysCli.run(listOf("verify-evidence", "--output", folder.toString())))
            MigrationFiles.writeText(folder.resolve("raw.log"), "changed\n")
            assertEquals(1, JourneysCli.run(listOf("verify-evidence", "--output", folder.toString())))
        } finally {
            deleteTree(folder)
        }
    }

    test("fixed_replay compare CLI writes the recorded comparison") {
        val section = VectorData.section("fixed_replay") as PyValue.Map
        val streams = section.get("streams") as PyValue.Map
        val matching = (section.get("cases") as PyValue.Seq).items.first {
            (it.get("case") as PyValue.Text).value.startsWith("test_matching_fixed_streams_pass")
        }
        val folder = Files.createTempDirectory("dyn4k-cli-compare-")
        try {
            for ((name, key) in listOf("baseline" to "baseline_sha", "candidate" to "candidate_sha")) {
                val rows = (streams.get((matching.get(key) as PyValue.Text).value) as PyValue.Seq).items
                MigrationFiles.writeText(
                    folder.resolve("$name.jsonl"),
                    rows.joinToString("") { PyJson.compact(it) + "\n" },
                )
            }
            val code = FixedReplayCli.run(
                listOf(
                    "compare",
                    "--baseline", folder.resolve("baseline.jsonl").toString(),
                    "--candidate", folder.resolve("candidate.jsonl").toString(),
                    "--output", folder.resolve("comparison.json").toString(),
                    "--baseline-sha256", "a".repeat(64),
                    "--candidate-sha256", "b".repeat(64),
                ),
            )
            assertEquals(0, code)
            assertEquals(
                (matching.get("report_text") as PyValue.Text).value,
                MigrationFiles.readTextOrEmpty(folder.resolve("comparison.json")),
            )
        } finally {
            deleteTree(folder)
        }
    }

    test("usage and invalid input exit codes follow argparse and the value checks") {
        assertEquals(2, JourneysCli.run(emptyList()))
        assertEquals(2, JourneysCli.run(listOf("inspect-samples")))
        assertEquals(
            1,
            JourneysCli.run(
                listOf(
                    "compile", "--provider", "baseline", "--samples", "s", "--resolved", "r",
                    "--output", "o", "--timeout-seconds", "0",
                ),
            ),
        )
        assertEquals(2, FixedReplayCli.run(emptyList()))
        assertEquals(2, FixedReplayCli.run(listOf("compare", "--baseline", "b")))
        assertEquals(
            2,
            FixedReplayCli.run(
                listOf(
                    "run", "--samples", "s", "--resolved-root", "r", "--repository", "p",
                    "--output", "o", "--jdk", "j", "--power", "0",
                ),
            ),
        )
    }
}
