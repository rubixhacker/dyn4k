package io.github.rubixhacker.harness.migration

import de.infix.testBalloon.framework.core.testSuite
import java.nio.file.Files
import java.nio.file.Path
import java.util.Base64
import java.util.zip.CRC32
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * `tools/migration/test_truck_camera.py` and the plain admission suite, replayed against the
 * verdicts the Python modules produced for the same generated timelines and frames.
 */
val TruckTimelineContract by testSuite {
    val valid: ByteArray = Base64.getDecoder().decode(
        (VectorData.section("valid_png_base64") as PyValue.Text).value,
    )
    val timelineRecords = (VectorData.section("truck_timeline") as PyValue.Seq).items

    for (record in timelineRecords) {
        val name = (record.get("case") as PyValue.Text).value
        test("timeline $name") {
            val folder = Files.createTempDirectory("dyn4k-timeline-")
            try {
                val rows = evidenceRows(folder, valid)
                val changed = mutateTimeline(name, rows)
                MigrationFiles.writeText(folder.resolve("truck-timeline.jsonl"), renderRows(changed))
                if (name.startsWith("png_")) {
                    val data = pngVariant(name.removePrefix("png_"), valid)
                    MigrationFiles.writeBytes(folder.resolve("initial.png"), data)
                    val digest = changed.first {
                        pyEquals(it.get("kind"), pyText("frame_hash")) &&
                            pyEquals(it.get("name"), pyText("initial"))
                    } as PyValue.Map
                    digest.entries["sha256"] = pyText(MigrationFiles.digest(data))
                    MigrationFiles.writeText(
                        folder.resolve("truck-timeline.jsonl"),
                        renderRows(changed),
                    )
                }
                assertEquals(
                    (record.get("rows_sha256") as PyValue.Text).value,
                    MigrationFiles.digest(renderRows(changed).toByteArray()),
                    "generated timeline rows",
                )
                val verdict = TruckTimeline.validate(
                    MigrationFiles.readTextOrEmpty(folder.resolve("truck-timeline.jsonl")),
                    { frame -> MigrationFiles.readBytes(folder.resolve(frame), TruckTimeline.MAX_PNG_BYTES + 1) },
                    PngDecoders.identify(),
                )
                assertEquals((record.get("passed") as PyValue.Bool).value, verdict.first, name)
                assertEquals((record.get("evidence") as PyValue.Text).value, verdict.second, name)
            } finally {
                deleteTree(folder)
            }
        }
    }

    test("slow camera work does not extend the key hold") {
        val folder = Files.createTempDirectory("dyn4k-truck-run-")
        try {
            val run = TruckRun("1", folder)
            run.xdotool = { kind, name, _, details ->
                run.record(kind, name, System.nanoTime(), System.nanoTime(), details)
            }
            val workEnd = mutableListOf<Long>()
            run.hold("Right", 100_000_000) { _, _ ->
                Thread.sleep(350)
                workEnd.add(System.nanoTime())
            }
            val rows = pythonSplitlines(MigrationFiles.readTextOrEmpty(run.timeline)).map {
                pyFromJson(kotlinx.serialization.json.Json.parseToJsonElement(it))
            }
            val release = rows.first { pyEquals(it.get("name"), pyText("keyup-Right")) }
            assertTrue((release.get("end_ns") as PyValue.Int).value < workEnd[0])
            assertTrue(
                (release.get("start_ns") as PyValue.Int).value -
                    (rows[0].get("end_ns") as PyValue.Int).value < 250_000_000,
            )
        } finally {
            deleteTree(folder)
        }
    }

    val plainRecords = (VectorData.section("plain_validation") as PyValue.Seq).items

    for (record in plainRecords) {
        val name = (record.get("case") as PyValue.Text).value
        test("plain $name") {
            val folder = Files.createTempDirectory("dyn4k-plain-")
            try {
                val scene = (record.get("scene") as PyValue.Text).value
                if (scene == "Truck") {
                    makePlainTruck(folder, valid)
                    val label = name.removePrefix("truck_late_")
                    if (name.startsWith("truck_late_")) {
                        MigrationFiles.writeBytes(folder.resolve("late.png"), plainVariant(label, valid))
                    }
                } else {
                    makePlainContext(folder, scene)
                    for (frame in listOf("initial", "after-input", "late", "interaction")) {
                        MigrationFiles.writeBytes(folder.resolve("$frame.png"), valid)
                    }
                    val label = name.removePrefix("pyramid_interaction_")
                    if (label != "valid") {
                        MigrationFiles.writeBytes(folder.resolve("interaction.png"), plainVariant(label, valid))
                    }
                }
                val result = PlainValidation.validate(
                    scene,
                    MigrationFiles.readTextOrEmpty(folder.resolve("application.log")),
                    MigrationFiles.readTextOrEmpty(folder.resolve("inputs.log")),
                    MigrationFiles.readTextOrEmpty(folder.resolve("launch.txt")),
                    readTermination(folder.resolve("termination.json")),
                    { frame -> readPng(folder.resolve(frame), valid, PngDecoders.identify()) },
                    { TruckTimelineFiles.validate(folder) },
                )
                assertEquals((record.get("result_text") as PyValue.Text).value, PyJson.prettyLine(result))
                if (name == "truck_complete") {
                    assertEquals(19L, (result.get("expected") as PyValue.Int).value)
                    assertEquals(19L, (result.get("passed") as PyValue.Int).value)
                    assertEquals(0L, (result.get("failed") as PyValue.Int).value)
                    assertEquals(
                        "UNREVIEWED",
                        (result.get("visual_review_status") as PyValue.Text).value,
                    )
                    assertEquals(
                        MigrationFiles.digest(valid),
                        (result.get("frames").get("late").get("sha256") as PyValue.Text).value,
                    )
                }
            } finally {
                deleteTree(folder)
            }
        }
    }

    test("decoder failure marks the frame without failing the timeline") {
        for ((frameName, label) in listOf(
            "late_frame" to "truck_missing_decoder",
            "interaction_frame" to "pyramid_missing_decoder",
        )) {
            val folder = Files.createTempDirectory("dyn4k-decoder-")
            try {
                val scene = if (label.startsWith("truck")) "Truck" else "Pyramid"
                if (scene == "Truck") {
                    makePlainTruck(folder, valid)
                } else {
                    makePlainContext(folder, scene)
                    for (frame in listOf("initial", "after-input", "late", "interaction")) {
                        MigrationFiles.writeBytes(folder.resolve("$frame.png"), valid)
                    }
                }
                val result = PlainValidation.validate(
                    scene,
                    MigrationFiles.readTextOrEmpty(folder.resolve("application.log")),
                    MigrationFiles.readTextOrEmpty(folder.resolve("inputs.log")),
                    MigrationFiles.readTextOrEmpty(folder.resolve("launch.txt")),
                    readTermination(folder.resolve("termination.json")),
                    { frame -> readPng(folder.resolve(frame), valid) { false } },
                    { TruckTimelineFiles.validate(folder) },
                )
                assertEquals("failed", frameStatus(result, frameName))
                if (scene == "Truck") {
                    assertEquals("passed", frameStatus(result, "truck_timeline"))
                }
            } finally {
                deleteTree(folder)
            }
        }
    }
}

private fun frameStatus(result: PyValue, name: String): String =
    (result.get("checks") as PyValue.Seq).items
        .first { pyEquals(it.get("id"), pyText(name)) }
        .let { (it.get("status") as PyValue.Text).value }

private fun renderRows(rows: List<PyValue>): String =
    rows.joinToString("") { PyJson.compact(it) + "\n" }

private fun readTermination(path: Path): PyValue {
    val text = MigrationFiles.readTextOrEmpty(path)
    return try {
        pyFromJson(kotlinx.serialization.json.Json.parseToJsonElement(text))
    } catch (error: IllegalArgumentException) {
        pyMap()
    }
}

private fun pngVariant(label: String, valid: ByteArray): ByteArray = when (label) {
    "header_only" -> valid.copyOfRange(0, 24)
    "truncated" -> valid.copyOfRange(0, valid.size - 12)
    "corrupt_payload" -> corruptPayload(valid)
    "corrupt_crc" -> valid.copyOfRange(0, valid.size - 16) +
        byteArrayOf((valid[valid.size - 16].toInt() xor 1).toByte()) +
        valid.copyOfRange(valid.size - 15, valid.size)
    "malformed_chunk" -> valid.copyOfRange(0, 33) + byteArrayOf(-1, -1, -1, -1) +
        valid.copyOfRange(37, valid.size)
    "oversized" -> valid + ByteArray(16 * 1024 * 1024) { 'x'.code.toByte() }
    else -> error("unknown PNG variant $label")
}

private fun plainVariant(label: String, valid: ByteArray): ByteArray = when (label) {
    "oversized" -> valid + ByteArray(16 * 1024 * 1024 + 1 - valid.size) { 'x'.code.toByte() }
    else -> pngVariant(label, valid)
}

private fun corruptPayload(valid: ByteArray): ByteArray {
    val corrupt = valid.copyOf()
    corrupt[41] = (corrupt[41].toInt() xor 1).toByte()
    val idatCrc = 41 + bigEndianInt(valid, 33).toInt()
    val crc = CRC32()
    crc.update(corrupt, 37, idatCrc - 37)
    val value = crc.value.toInt()
    for (index in 0 until 4) {
        corrupt[idatCrc + index] = (value ushr (24 - 8 * index)).toByte()
    }
    return corrupt
}

internal fun readPng(
    path: Path,
    valid: ByteArray,
    decodes: (ByteArray) -> Boolean = PngDecoders.identify(),
): PyValue? {
    val data = MigrationFiles.readBytes(path, TruckTimeline.MAX_PNG_BYTES + 1) ?: return null
    if (!TruckTimeline.validPng(data, decodes)) return null
    return pyMap(
        "width" to pyInt(bigEndianInt(data, 16)),
        "height" to pyInt(bigEndianInt(data, 20)),
        "sha256" to pyText(MigrationFiles.digest(data)),
    )
}

internal fun makePlainContext(directory: Path, scene: String) {
    MigrationFiles.writeText(
        directory.resolve("launch.txt"),
        "main=org.dyn4j.samples.$scene\nclasspath=/classes:/lib/dyn4j.jar\n",
    )
    MigrationFiles.writeText(directory.resolve("application.log"), "Controls:\n")
    val markers = when (scene) {
        "Truck" -> "keydown Right\nkey s\n"
        "Pyramid" -> "drag left mouse\nkey r\n"
        else -> ""
    }
    MigrationFiles.writeText(directory.resolve("inputs.log"), "scene=$scene\n$markers")
    MigrationFiles.writeText(
        directory.resolve("termination.json"),
        PyJson.compact(
            pyMap(
                "close_requested" to pyBool(true),
                "exited_after_close" to pyBool(true),
                "forced_termination" to pyBool(false),
                "exit_code" to pyInt(0),
            ),
        ),
    )
}

internal fun makePlainTruck(directory: Path, valid: ByteArray) {
    val rows = evidenceRows(directory, valid)
    MigrationFiles.writeText(directory.resolve("truck-timeline.jsonl"), renderRows(rows))
    makePlainContext(directory, "Truck")
    MigrationFiles.writeBytes(directory.resolve("late.png"), valid)
}

/**
 * The `make_evidence` fixture of `test_truck_camera.py`: a complete Truck timeline whose frames
 * all hold the same generated PNG.
 */
internal fun evidenceRows(directory: Path, png: ByteArray): MutableList<PyValue> {
    val base = 1_000_000_000L
    val rows = mutableListOf<PyValue>()

    fun add(kind: String, name: String, start: Long, end: Long, extra: Map<String, PyValue> = emptyMap()): PyValue {
        val row = linkedMapOf<String, PyValue>(
            "kind" to pyText(kind),
            "name" to pyText(name),
            "start_ns" to pyInt(base + start),
            "end_ns" to pyInt(base + end),
        )
        row.putAll(extra)
        rows.add(PyValue.Map(row))
        if (kind == "camera") {
            for ((suffix, boundary) in listOf(
                "-position" to start - 3,
                "-down" to start - 2,
                "-up" to end + 1,
            )) {
                rows.add(
                    pyMap(
                        "kind" to pyText("pointer"),
                        "name" to pyText(name + suffix),
                        "start_ns" to pyInt(base + boundary),
                        "end_ns" to pyInt(base + boundary + 1),
                    ),
                )
            }
        }
        return PyValue.Map(row)
    }

    add("run", "Truck", 0, 0)
    add(
        "camera", "setup", 100, 200,
        linkedMapOf(
            "from_x" to pyInt(300), "to_x" to pyInt(650),
            "from_y" to pyInt(80), "to_y" to pyInt(80),
        ),
    )
    add("frame", "initial", 300, 400, mapOf("file" to pyText("initial.png")))
    add("key", "keydown-Right", 900, 1000)
    add("frame", "drive-0", 1_010, 1_020, mapOf("file" to pyText("drive-0.png")))
    for ((index, pixels) in TruckTimeline.FOLLOW_PIXELS.withIndex()) {
        val position = index + 1
        val when_ = 1000 + position * 500_000_000L
        add(
            "camera",
            "follow-" + position.toString().padStart(2, '0'),
            when_,
            when_ + 10_000_000,
            linkedMapOf(
                "from_x" to pyInt(650), "to_x" to pyInt(650 - pixels),
                "from_y" to pyInt(80), "to_y" to pyInt(80),
            ),
        )
        if (position % 2 == 0) {
            val frame = "drive-${position / 2}"
            add(
                "frame", frame, when_ + 20_000_000, when_ + 30_000_000,
                mapOf("file" to pyText("$frame.png")),
            )
        }
    }
    val rightUp = 1000 + 7_000_000_000L
    add("key", "keyup-Right", rightUp, rightUp + 10_000_000)
    add("frame", "drive", rightUp + 20_000_000, rightUp + 30_000_000, mapOf("file" to pyText("drive.png")))
    val brakeDown = rightUp + 40_000_000
    add("key", "keydown-s", brakeDown, brakeDown + 10_000_000)
    add(
        "camera", "brake-follow-1", brakeDown + 410_000_000, brakeDown + 420_000_000,
        linkedMapOf(
            "from_x" to pyInt(650), "to_x" to pyInt(530),
            "from_y" to pyInt(80), "to_y" to pyInt(80),
        ),
    )
    add(
        "frame", "brake-mid", brakeDown + 510_000_000, brakeDown + 520_000_000,
        mapOf("file" to pyText("brake-mid.png")),
    )
    add(
        "camera", "brake-follow-2", brakeDown + 810_000_000, brakeDown + 820_000_000,
        linkedMapOf(
            "from_x" to pyInt(650), "to_x" to pyInt(530),
            "from_y" to pyInt(240), "to_y" to pyInt(80),
        ),
    )
    val brakeUp = brakeDown + 1_010_000_000
    add("key", "keyup-s", brakeUp, brakeUp + 10_000_000)
    add(
        "frame", "after-input", brakeUp + 20_000_000, brakeUp + 30_000_000,
        mapOf("file" to pyText("after-input.png")),
    )
    for (name in TruckTimeline.FRAMES) {
        MigrationFiles.writeBytes(directory.resolve("$name.png"), png)
        val frame = rows.first {
            pyEquals(it.get("kind"), pyText("frame")) && pyEquals(it.get("name"), pyText(name))
        }
        add(
            "frame_hash", name,
            (frame.get("end_ns") as PyValue.Int).value - base,
            (frame.get("end_ns") as PyValue.Int).value - base + 1,
            linkedMapOf(
                "file" to pyText("$name.png"),
                "sha256" to pyText(MigrationFiles.digest(png)),
            ),
        )
    }
    return rows
}

/** Applies the timeline mutation each recorded Python case makes. */
private fun mutateTimeline(case: String, rows: MutableList<PyValue>): MutableList<PyValue> {
    fun row(kind: String, name: String): PyValue.Map =
        rows.first {
            it is PyValue.Map && pyEquals(it.get("kind"), pyText(kind)) &&
                pyEquals(it.get("name"), pyText(name))
        } as PyValue.Map

    fun add(key: String, value: PyValue) {
        rows.add(pyMap(key to value))
    }

    when {
        case == "missing" -> rows.removeAll {
            pyEquals(it.get("kind"), pyText("frame")) && pyEquals(it.get("name"), pyText("drive-4"))
        }
        case == "late" -> {
            val drive4 = row("frame", "drive-4")
            drive4.entries["start_ns"] = pyInt((drive4.get("start_ns") as PyValue.Int).value + 300_000_000)
        }
        case == "scene" -> {
            val first = rows[0] as PyValue.Map
            first.entries["name"] = pyText("Crank")
        }
        case == "short" || case == "extended" -> {
            val shift = if (case == "short") -500_000_000L else 500_000_000L
            val keyUp = row("key", "keyup-s")
            keyUp.entries["start_ns"] = pyInt((keyUp.get("start_ns") as PyValue.Int).value + shift)
            keyUp.entries["end_ns"] = pyInt((keyUp.get("end_ns") as PyValue.Int).value + shift)
        }
        case == "press_after_move" -> {
            val camera = row("camera", "follow-01")
            val down = row("pointer", "follow-01-down")
            down.entries["start_ns"] = pyInt((camera.get("end_ns") as PyValue.Int).value + 1)
            down.entries["end_ns"] = pyInt((down.get("start_ns") as PyValue.Int).value + 1)
        }
        case == "overlapping_position" -> {
            val position = row("pointer", "follow-01-position")
            val down = row("pointer", "follow-01-down")
            position.entries["end_ns"] = pyInt((down.get("start_ns") as PyValue.Int).value + 1)
        }
        case == "wrong_association" -> {
            row("pointer", "follow-01-up").entries["name"] = pyText("follow-02-up")
        }
        case.startsWith("boundary_") -> {
            val release = row("pointer", case.removePrefix("boundary_"))
            val next = when (case) {
                "boundary_setup-up" -> row("pointer", "follow-01-position")
                "boundary_follow-01-up" -> row("pointer", "follow-02-down")
                "boundary_follow-13-up" -> row("pointer", "brake-follow-1-position")
                else -> row("pointer", "brake-follow-2-down")
            }
            release.entries["start_ns"] = next.get("start_ns")
            release.entries["end_ns"] = pyInt((release.get("start_ns") as PyValue.Int).value + 1)
        }
        case == "missing_position" -> rows.removeAll {
            pyEquals(it.get("name"), pyText("follow-01-position"))
        }
        case == "duplicate_release" -> {
            val release = row("pointer", "follow-01-up")
            rows.add(PyValue.Map(LinkedHashMap(release.entries)))
        }
        case == "key_release_overlap" -> {
            val camera = row("camera", "follow-13")
            val keyUp = row("key", "keyup-Right")
            val pointerUp = row("pointer", "follow-13-up")
            camera.entries["end_ns"] = pyInt((keyUp.get("start_ns") as PyValue.Int).value + 1)
            pointerUp.entries["start_ns"] = camera.get("end_ns")
            pointerUp.entries["end_ns"] = pyInt((pointerUp.get("start_ns") as PyValue.Int).value + 1)
        }
        case == "complete" || case.startsWith("png_") -> Unit
        else -> throw IllegalArgumentException("unknown timeline case $case")
    }
    return rows
}
