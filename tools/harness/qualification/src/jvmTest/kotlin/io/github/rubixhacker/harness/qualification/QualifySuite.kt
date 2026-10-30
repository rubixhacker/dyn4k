package io.github.rubixhacker.harness.qualification

import de.infix.testBalloon.framework.core.testSuite
import io.github.rubixhacker.harness.contract.StrictJson
import java.nio.file.Files
import java.nio.file.Path
import kotlin.io.path.writeText
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/**
 * `tools/qualification/qualify.py`: the full hosted lane mapping, the hosted run's receipt
 * skeleton, and the qualification command line actions the port implements.
 *
 * `record` is not ported (`LaneEvaluation.evaluate` returns a verdict, not the reference's lane
 * object), so only its refusal is asserted.
 */
val QualifyContract by testSuite {
    test("full_hosted_lane maps a verified receipt or rejects it with the reference message") {
        for (vector in QualifyVectors.LANE_CASES) {
            val receipt = StrictJson.load(vector.receipt) as JsonObject
            if (vector.error != null) {
                assertEquals(
                    vector.error,
                    assertFailsWith<IllegalArgumentException>(vector.label) {
                        FullHostedLane.of(receipt, "9".repeat(64))
                    }.message,
                    vector.label,
                )
            } else {
                val expected = StrictJson.load(vector.lane!!) as JsonObject
                val actual = FullHostedLane.of(receipt, "9".repeat(64))
                assertEquals(expected.keys, actual.keys, vector.label)
                assertEquals(expected, actual, vector.label)
            }
        }
    }

    test("the qualification command line refuses a candidate that is not the checkout") {
        qualifyTemp { root ->
            Files.createDirectories(root.resolve("tools/qualification"))
            hostedGit(root, "init", "-q")
            root.resolve("README.md").writeText("qualify fixture.\n")
            hostedGit(root, "add", "README.md")
            hostedGit(
                root, "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                "commit", "-qm", "base",
            )
            val sha = hostedGit(root, "rev-parse", "HEAD").trim()
            val output = root.resolve("lanes.json")
            assertEquals(
                2,
                QualificationCli.run(
                    arrayOf("execute", "--candidate-sha", "0".repeat(40), "--plan", output.toString(), "--output", output.toString()),
                    root,
                ),
            )
            assertEquals(2, QualificationCli.run(arrayOf("record", "--candidate-sha", sha, "--output", "$output"), root))
            assertEquals(2, QualificationCli.run(arrayOf("nonsense", "--candidate-sha", sha), root))
            val graph = root.resolve("graph.txt")
            graph.writeText("io.github.rubixhacker:dyn4k-core:0.1.0-alpha.1\n")
            assertEquals(
                0,
                QualificationCli.run(arrayOf("check-providers", graph.toString()), root),
            )
            graph.writeText(
                "io.github.rubixhacker:dyn4k-core:0.1.0-alpha.1\norg.dyn4j:dyn4j:5.0.0\n",
            )
            assertEquals(
                1,
                QualificationCli.run(arrayOf("check-providers", graph.toString()), root),
            )
            assertEquals(0, QualificationCli.run(arrayOf("matrix"), root))
        }
    }

    test("a hosted run writes a failed receipt for an invalid target or candidate") {
        qualifyTemp { root ->
            Files.createDirectories(root.resolve("tools/qualification"))
            hostedGit(root, "init", "-q")
            root.resolve("README.md").writeText("qualify fixture.\n")
            hostedGit(root, "add", "README.md")
            hostedGit(
                root, "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                "commit", "-qm", "base",
            )
            val sha = hostedGit(root, "rev-parse", "HEAD").trim()
            for (vector in listOf(
                listOf("invalid target", "linuxX64", sha, "target or candidate SHA is invalid"),
                listOf("short candidate", "macosArm64", sha.take(12), "target or candidate SHA is invalid"),
            )) {
                val label = vector[0]
                val target = vector[1]
                val candidate = vector[2]
                val reason = vector[3]
                val output = root.resolve("run-$label")
                val receipt = FullHostedRun.run(root, candidate, target, output)
                assertEquals("FAILED", Py.str(receipt["status"]), label)
                assertEquals(reason, Py.str(receipt["reason"]), label)
                val written = StrictJson.load(Files.readString(output.resolve("receipt.json")))
                    as JsonObject
                assertEquals("FAILED", Py.str(written["status"]), label)
                assertEquals("2", Py.int(written["schema"]!!).toString(), label)
                assertEquals(
                    "hosted-full-common-corpus",
                    Py.str(written["kind"]),
                    label,
                )
                assertTrue(written["archive_root"] is JsonPrimitive, label)
            }
        }
    }
}

private fun qualifyTemp(block: (Path) -> Unit) {
    val root = Files.createTempDirectory("qualify-suite")
    try {
        block(root)
    } finally {
        crossRunDeleteFor(root)
    }
}

/** Local delete helper, named away from the shared test fixtures. */
internal fun crossRunDeleteFor(root: Path) {
    if (!Files.exists(root)) return
    Files.walk(root).use { walk ->
        walk.sorted(Comparator.reverseOrder()).forEach { Files.deleteIfExists(it) }
    }
}
