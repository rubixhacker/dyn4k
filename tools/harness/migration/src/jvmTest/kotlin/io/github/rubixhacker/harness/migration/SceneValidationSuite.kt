package io.github.rubixhacker.harness.migration

import de.infix.testBalloon.framework.core.testSuite
import java.nio.file.Files
import java.nio.file.Path
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * `tools/migration/test_validation.py` replayed against the result files the Python validator
 * wrote for the same observer logs.
 */
val SceneValidationContract by testSuite {
    for (record in (VectorData.section("scene_validation") as PyValue.Seq).items) {
        val name = (record.get("case") as PyValue.Text).value
        test(name.replace('_', ' ')) {
            val folder = Files.createTempDirectory("dyn4k-scene-")
            try {
                val scene = (record.get("scene") as PyValue.Text).value
                val log = (record.get("log") as PyValue.Text).value
                val inputs = (record.get("inputs") as PyValue.Text).value
                MigrationFiles.writeText(folder.resolve("observer.log"), log)
                MigrationFiles.writeText(folder.resolve("inputs.log"), inputs)
                val (samples, parseErrors) = SceneValidation.parseObserverLog(log)
                val timeline: (() -> Pair<Boolean, String>)? = if (scene == "Truck") {
                    { TruckTimelineFiles.validate(folder) }
                } else {
                    null
                }
                val result = SceneValidation.result(scene, log, inputs, samples, parseErrors, timeline)
                val expected = (record.get("result_text") as PyValue.Text).value
                    .replace(folder.toString(), "<work>")
                assertEquals(
                    expected,
                    PyJson.prettySortedLine(result).replace(folder.toString(), "<work>"),
                )
                when (name) {
                    "headless_exception_tracking" -> {
                        assertEquals(0L, (result.get("samples") as PyValue.Int).value)
                        val blocked = (result.get("failed_checks") as PyValue.Int).value +
                            (result.get("unexecuted_checks") as PyValue.Int).value
                        assertTrue(blocked > 0)
                    }
                    "billiards_without_ccd_hit" -> {
                        val failed = failedChecks(result)
                        assertTrue("ccd_detector_hits" in failed)
                        assertTrue("ccd_listener_hits" in failed)
                    }
                    "capture_time_without_steps" -> {
                        assertTrue("steps_progressed" in failedChecks(result))
                    }
                    "truck_observations_without_timeline" -> {
                        assertTrue("truck_timeline" in failedChecks(result))
                    }
                }
            } finally {
                deleteTree(folder)
            }
        }
    }
}

private fun failedChecks(result: PyValue): Set<String> =
    (result.get("checks") as PyValue.Seq).items
        .filter { pyEquals(it.get("status"), pyText("failed")) }
        .map { (it.get("id") as PyValue.Text).value }
        .toSet()

internal fun deleteTree(root: Path) {
    if (!Files.exists(root)) return
    Files.walk(root).use { stream ->
        stream.sorted(Comparator.reverseOrder()).forEach { Files.deleteIfExists(it) }
    }
}
