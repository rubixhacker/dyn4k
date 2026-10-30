package io.github.rubixhacker.harness.migration

import java.io.IOException
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.Path

/** `truck_timeline.valid_png`'s ImageMagick decode probe. */
object PngDecoders {
    /** Returns a decoder that runs `identify` exactly as the Python module does. */
    fun identify(): (ByteArray) -> Boolean = { data ->
        try {
            val result = Processes.runWithInput(
                listOf(
                    "identify", "-regard-warnings", "-limit", "memory", "64MiB",
                    "-limit", "map", "64MiB", "-limit", "disk", "0", "-format", "%w %h", "PNG:-",
                ),
                data,
                5.0,
            )
            result.exitCode == 0 && result.stdout == "1024 768" && result.stderr.isEmpty()
        } catch (error: IOException) {
            false
        } catch (error: ProcessTimeout) {
            false
        }
    }
}

/** The JVM side of `truck_timeline.validate`: reads the timeline and the recorded frames. */
object TruckTimelineFiles {
    fun validate(directory: Path, decodes: (ByteArray) -> Boolean = PngDecoders.identify()): Pair<Boolean, String> {
        val timeline = directory.resolve("truck-timeline.jsonl")
        val text = try {
            Files.readString(timeline, StandardCharsets.UTF_8)
        } catch (error: IOException) {
            return false to pythonIoMessage(timeline, error)
        }
        return TruckTimeline.validate(
            text,
            { name -> MigrationFiles.readBytes(directory.resolve(name), TruckTimeline.MAX_PNG_BYTES + 1) },
            decodes,
        )
    }
}

/** Python's `OSError` text for a failed read. */
fun pythonIoMessage(path: Path, error: IOException): String = when (error) {
    is java.nio.file.NoSuchFileException ->
        "[Errno 2] No such file or directory: '$path'"
    is java.nio.file.AccessDeniedException ->
        "[Errno 13] Permission denied: '$path'"
    is java.nio.file.FileSystemException ->
        "[Errno 21] Is a directory: '$path'"
    else -> error.message ?: error.toString()
}

/**
 * `truck_camera.TruckRun`: the xdotool-driven Truck camera script and its monotonic timeline.
 *
 * [xdotool] is replaceable so a test can drive [hold] without a display, exactly as the Python
 * suite patches `TruckRun.xdotool`.
 */
class TruckRun(
    val window: String,
    evidence: Path,
    private val clock: () -> Long = System::nanoTime,
) {
    companion object {
        const val DRIVE_NS = 7_000_000_000L
        const val BRAKE_NS = 1_000_000_000L
        const val FOLLOW_NS = 500_000_000L
        const val BLANK_Y = 80
        val FOLLOW_PIXELS = TruckTimeline.FOLLOW_PIXELS

        /** `TruckRun.wait_until`, on the injected monotonic clock. */
        fun waitUntil(deadline: Long, clock: () -> Long = System::nanoTime) {
            while (true) {
                val remaining = (deadline - clock()) / 1_000_000_000.0
                if (remaining <= 0) return
                Thread.sleep((remaining * 1000.0).toLong().coerceAtLeast(1))
            }
        }
    }

    val evidence: Path = evidence
    private val lock = Any()
    private val pressed = linkedSetOf<String>()
    private var mouseDown = false
    val timeline: Path = evidence.resolve("truck-timeline.jsonl")

    /** Mirrors the Python method; a test may replace this with a recorder. */
    var xdotool: (String, String, List<Any>, Map<String, PyValue>) -> PyValue =
        { kind, name, arguments, details ->
            command(kind, name, listOf("xdotool") + arguments.map { it.toString() }, details)
        }

    init {
        MigrationFiles.writeText(timeline, "")
    }

    /** `TruckRun.record`; writes one sorted-key JSON row and returns it. */
    fun record(
        kind: String,
        name: String,
        start: Long,
        end: Long,
        details: Map<String, PyValue> = emptyMap(),
    ): PyValue {
        val row = linkedMapOf<String, PyValue>(
            "kind" to pyText(kind),
            "name" to pyText(name),
            "start_ns" to pyInt(start),
            "end_ns" to pyInt(end),
        )
        row.putAll(details)
        synchronized(lock) {
            val existing = MigrationFiles.readTextOrEmpty(timeline)
            MigrationFiles.writeText(timeline, existing + PyJson.compactSorted(PyValue.Map(row)) + "\n")
        }
        return PyValue.Map(row)
    }

    /** `TruckRun.command`; a failing command records its error and rethrows. */
    fun command(
        kind: String,
        name: String,
        command: List<String>,
        details: Map<String, PyValue> = emptyMap(),
    ): PyValue {
        val start = clock()
        try {
            Processes.run(command, 5.0, check = true)
        } catch (error: Exception) {
            record(
                kind,
                name,
                start,
                clock(),
                details + ("error" to pyText(error.message ?: error.toString())),
            )
            throw error
        }
        return record(kind, name, start, clock(), details)
    }

    private fun invokeXdotool(kind: String, name: String, vararg arguments: Any, details: Map<String, PyValue> = emptyMap()): PyValue =
        xdotool(kind, name, arguments.toList(), details)

    /** `TruckRun.drag`; returns the press and camera-move rows. */
    fun drag(name: String, startX: Int, endX: Int, startY: Int = BLANK_Y, endY: Int = BLANK_Y): Pair<PyValue, PyValue> {
        invokeXdotool("pointer", "$name-position", "mousemove", "--window", window, startX, startY)
        try {
            val down = invokeXdotool("pointer", "$name-down", "mousedown", 1)
            mouseDown = true
            val move = invokeXdotool(
                "camera",
                name,
                "mousemove",
                "--window",
                window,
                endX,
                endY,
                details = linkedMapOf(
                    "from_x" to pyInt(startX),
                    "to_x" to pyInt(endX),
                    "from_y" to pyInt(startY),
                    "to_y" to pyInt(endY),
                ),
            )
            return down to move
        } finally {
            if (mouseDown) {
                invokeXdotool("pointer", "$name-up", "mouseup", 1)
                mouseDown = false
            }
        }
    }

    /** `TruckRun.frame`; captures the root window and records its digest. */
    fun frame(name: String) {
        val path = evidence.resolve("$name.png")
        val row = command(
            "frame",
            name,
            listOf("import", "-window", "root", path.toString()),
            mapOf("file" to pyText(path.fileName.toString())),
        )
        val digest = MigrationFiles.digest(path)
        record(
            "frame_hash",
            name,
            (row.get("end_ns") as PyValue.Int).value,
            clock(),
            linkedMapOf(
                "sha256" to pyText(digest),
                "file" to pyText(path.fileName.toString()),
            ),
        )
    }

    /** `TruckRun.keydown`. */
    fun keydown(key: String): PyValue {
        val row = invokeXdotool("key", "keydown-$key", "keydown", key)
        synchronized(lock) { pressed.add(key) }
        return row
    }

    /** `TruckRun.keyup`. */
    fun keyup(key: String): PyValue {
        val row = invokeXdotool("key", "keyup-$key", "keyup", key)
        synchronized(lock) { pressed.remove(key) }
        return row
    }

    /** `TruckRun.hold`; the release thread ends the hold at the deadline, not at `work`'s end. */
    fun hold(key: String, duration: Long, work: (Long, Long) -> Unit) {
        val down = keydown(key)
        val deadline = (down.get("end_ns") as PyValue.Int).value + duration
        val failures = mutableListOf<Throwable>()
        val timer = Thread({
            try {
                waitUntil(deadline)
                keyup(key)
            } catch (error: Throwable) {
                failures.add(error)
            }
        }, "truck-key-release")
        timer.start()
        try {
            work((down.get("end_ns") as PyValue.Int).value, deadline)
        } finally {
            timer.join()
        }
        if (failures.isNotEmpty()) throw failures[0]
    }

    /** `TruckRun.drive_work`. */
    fun driveWork(start: Long, deadline: Long) {
        frame("drive-0")
        for ((index, pixels) in FOLLOW_PIXELS.withIndex()) {
            val position = index + 1
            waitUntil(start + position * FOLLOW_NS)
            drag("follow-" + position.toString().padStart(2, '0'), 650, 650 - pixels)
            if (position % 2 == 0) frame("drive-${position / 2}")
        }
    }

    /** `TruckRun.brake_work`. */
    fun brakeWork(start: Long, deadline: Long) {
        waitUntil(start + 400_000_000)
        drag("brake-follow-1", 650, 530)
        waitUntil(start + 500_000_000)
        frame("brake-mid")
        waitUntil(start + 800_000_000)
        drag("brake-follow-2", 650, 530, 240, 80)
    }

    /** `TruckRun.run`. */
    fun run() {
        record(
            "run",
            "Truck",
            clock(),
            clock(),
            linkedMapOf(
                "window" to pyText(window),
                "camera_y" to pyInt(BLANK_Y),
                "drive_ns" to pyInt(DRIVE_NS),
                "brake_ns" to pyInt(BRAKE_NS),
            ),
        )
        try {
            drag("setup", 300, 650)
            Thread.sleep(150)
            frame("initial")
            hold("Right", DRIVE_NS, ::driveWork)
            frame("drive")
            hold("s", BRAKE_NS, ::brakeWork)
            frame("after-input")
        } finally {
            if (mouseDown) {
                invokeXdotool("pointer", "cleanup-up", "mouseup", 1)
                mouseDown = false
            }
            for (key in pressed.toList()) keyup(key)
        }
    }

    private fun waitUntil(deadline: Long) = waitUntil(deadline, clock)
}
