package io.github.rubixhacker.harness.migration

import io.github.rubixhacker.harness.contract.Sha256

/**
 * The camera-timeline integrity rule of `tools/migration/truck_timeline.py`.
 *
 * The Python module reads recorded frames from an evidence directory and invokes ImageMagick's
 * `identify` to prove the pixels decode. The byte reads and decoder stay in the JVM adapter; this
 * object holds the ordered rule set and the exact evidence text it reports.
 */
object TruckTimeline {
    val FOLLOW_PIXELS = listOf(10, 10, 20, 20, 40, 40, 50, 60, 70, 80, 100, 110, 120)

    val FRAMES = buildList {
        add("initial")
        add("drive-0")
        for (index in 1..6) add("drive-$index")
        add("drive")
        add("brake-mid")
        add("after-input")
    }

    val PNG_SIGNATURE = byteArrayOf(0x89.toByte(), 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A)
    const val PNG_WIDTH = 1024L
    const val PNG_HEIGHT = 768L
    const val MAX_PNG_BYTES = 16 * 1024 * 1024

    /** The bounded header checks of `truck_timeline.valid_png`. */
    fun headerValid(data: ByteArray): Boolean =
        data.size <= MAX_PNG_BYTES &&
            data.size >= 24 &&
            data.size >= PNG_SIGNATURE.size &&
            PNG_SIGNATURE.indices.all { data[it] == PNG_SIGNATURE[it] } &&
            bigEndianInt(data, 16) == PNG_WIDTH &&
            bigEndianInt(data, 20) == PNG_HEIGHT

    /** `truck_timeline.valid_png`, with [decodes] supplying the `identify` answer. */
    fun validPng(data: ByteArray, decodes: (ByteArray) -> Boolean): Boolean =
        headerValid(data) && decodes(data)

    /**
     * `truck_timeline.validate`.
     *
     * [readFrame] returns the bytes of `frames/<name>.png`, at most `MAX_PNG_BYTES + 1` of them,
     * or null when the file cannot be read. [decodes] answers whether ImageMagick accepts them.
     */
    fun validate(
        timelineText: String,
        readFrame: (String) -> ByteArray?,
        decodes: (ByteArray) -> Boolean,
    ): Pair<Boolean, String> {
        val rows = try {
            pythonSplitlines(timelineText).map { pyFromJson(strictJson.parseToJsonElement(it)) }
        } catch (error: IllegalArgumentException) {
            return false to pythonJsonError(error)
        }
        if (rows.isEmpty() ||
            !pyEquals(rows[0].getOrNull("kind") ?: PyValue.Null, pyText("run")) ||
            !pyEquals(rows[0].getOrNull("name") ?: PyValue.Null, pyText("Truck"))
        ) {
            return false to "wrong or absent Truck run"
        }
        for (row in rows) {
            val start = row.getOrNull("start_ns")
            val end = row.getOrNull("end_ns")
            if ((start !is PyValue.Int && start !is PyValue.Bool) ||
                (end !is PyValue.Int && end !is PyValue.Bool)
            ) {
                return false to "missing monotonic boundary"
            }
            if (pyCompare(row.get("start_ns"), row.get("end_ns"), ">") > 0 ||
                (row.getOrNull("error")?.truthy() == true)
            ) {
                return false to "invalid or failed operation"
            }
        }
        val cameras = buildList {
            add("setup")
            for (index in 1..13) add("follow-" + index.toString().padStart(2, '0'))
            add("brake-follow-1")
            add("brake-follow-2")
        }
        val expected = linkedSetOf<Pair<String?, String?>>()
        expected.add("run" to "Truck")
        for (name in cameras) expected.add("camera" to name)
        for (name in cameras) {
            for (suffix in listOf("-position", "-down", "-up")) {
                expected.add("pointer" to (name + suffix))
            }
        }
        for (name in FRAMES) expected.add("frame" to name)
        for (name in FRAMES) expected.add("frame_hash" to name)
        for (name in listOf("keydown-Right", "keyup-Right", "keydown-s", "keyup-s")) {
            expected.add("key" to name)
        }
        fun identity(row: PyValue): Pair<String?, String?> =
            (row.getOrNull("kind") as? PyValue.Text)?.value to
                (row.getOrNull("name") as? PyValue.Text)?.value
        if (rows.size != expected.size || rows.map(::identity).toSet() != expected) {
            return false to "missing, repeated, or unexpected input operation"
        }
        fun one(kind: String, name: String): PyValue {
            val matches = rows.filter {
                pyEquals(it.getOrNull("kind") ?: PyValue.Null, pyText(kind)) &&
                    pyEquals(it.getOrNull("name") ?: PyValue.Null, pyText(name))
            }
            if (matches.size != 1) throw MigrationFailure("missing or repeated $kind $name")
            return matches[0]
        }
        val rightDown: PyValue
        val rightUp: PyValue
        val brakeDown: PyValue
        val brakeUp: PyValue
        val setup: PyValue
        val follows: List<PyValue>
        val brakeFollows: List<PyValue>
        val gestures: List<PyValue>
        val pointerEvents: List<List<PyValue>>
        val frames: List<PyValue>
        val hashes: List<PyValue>
        try {
            rightDown = one("key", "keydown-Right")
            rightUp = one("key", "keyup-Right")
            brakeDown = one("key", "keydown-s")
            brakeUp = one("key", "keyup-s")
            setup = one("camera", "setup")
            follows = (1..13).map { one("camera", "follow-" + it.toString().padStart(2, '0')) }
            brakeFollows = listOf(1, 2).map { one("camera", "brake-follow-$it") }
            gestures = listOf(setup) + follows + brakeFollows
            pointerEvents = gestures.map { row ->
                val name = (row.get("name") as PyValue.Text).value
                listOf(
                    one("pointer", "$name-position"),
                    one("pointer", "$name-down"),
                    row,
                    one("pointer", "$name-up"),
                )
            }
            frames = FRAMES.map { one("frame", it) }
            hashes = FRAMES.map { one("frame_hash", it) }
        } catch (error: MigrationFailure) {
            return false to (error.message ?: "")
        }
        fun path(row: PyValue): List<PyValue> = listOf(
            row.getOrNull("from_x") ?: PyValue.Null,
            row.getOrNull("to_x") ?: PyValue.Null,
            row.getOrNull("from_y") ?: PyValue.Null,
            row.getOrNull("to_y") ?: PyValue.Null,
        )
        fun pathEquals(row: PyValue, expected: List<Long>): Boolean =
            path(row).size == expected.size &&
                path(row).zip(expected).all { (value, target) -> pyEquals(value, pyInt(target)) }
        if (!pathEquals(setup, listOf(300, 650, 80, 80))) {
            return false to "setup camera path changed"
        }
        if (follows.zip(FOLLOW_PIXELS).any { (row, pixels) ->
                !pathEquals(row, listOf(650, (650 - pixels).toLong(), 80, 80))
            }
        ) {
            return false to "follow camera path changed"
        }
        if (brakeFollows.map(::path).let { paths ->
                paths.size != 2 ||
                    !paths[0].zip(listOf(650L, 530L, 80L, 80L)).all { (v, t) -> pyEquals(v, pyInt(t)) } ||
                    !paths[1].zip(listOf(650L, 530L, 240L, 80L)).all { (v, t) -> pyEquals(v, pyInt(t)) }
            }
        ) {
            return false to "brake camera path changed"
        }
        if (pointerEvents.any { (position, down, move, up) ->
                !(pyCompare(position.get("start_ns"), position.get("end_ns"), "<=") <= 0 &&
                    pyCompare(position.get("end_ns"), down.get("start_ns"), "<=") <= 0 &&
                    pyCompare(down.get("start_ns"), down.get("end_ns"), "<=") <= 0 &&
                    pyCompare(down.get("end_ns"), move.get("start_ns"), "<=") <= 0 &&
                    pyCompare(move.get("start_ns"), move.get("end_ns"), "<=") <= 0 &&
                    pyCompare(move.get("end_ns"), up.get("start_ns"), "<=") <= 0 &&
                    pyCompare(up.get("start_ns"), up.get("end_ns"), "<=") <= 0)
            }
        ) {
            return false to "camera pointer gesture out of order"
        }
        if (pointerEvents.zipWithNext().any { (previous, following) ->
                pyCompare(previous[3].get("end_ns"), following[0].get("start_ns"), ">") > 0
            }
        ) {
            return false to "camera pointer gestures overlap"
        }
        if (!(pyCompare(setup.get("end_ns"), frames[0].get("start_ns"), "<") < 0 &&
                pyCompare(frames[0].get("start_ns"), rightDown.get("start_ns"), "<") < 0 &&
                pyCompare(rightDown.get("start_ns"), rightDown.get("end_ns"), "<=") <= 0 &&
                pyCompare(rightDown.get("end_ns"), frames[1].get("start_ns"), "<") < 0)
        ) {
            return false to "setup or drive start out of order"
        }
        if (!follows.all {
                pyCompare(rightDown.get("end_ns"), it.get("start_ns"), "<=") <= 0 &&
                    pyCompare(it.get("start_ns"), it.get("end_ns"), "<") < 0 &&
                    pyCompare(it.get("end_ns"), rightUp.get("end_ns"), "<=") <= 0
            }
        ) {
            return false to "camera gesture outside drive"
        }
        if (!follows.zipWithNext().all { (a, b) ->
                pyCompare(a.get("end_ns"), b.get("start_ns"), "<=") <= 0
            }
        ) {
            return false to "camera gestures out of order"
        }
        for ((index, row) in follows.withIndex()) {
            val target = pyAdd(rightDown.get("end_ns"), pyInt((index + 1) * 500_000_000L))
            if (pyCompare(pyAbsolute(pySubtract(row.get("start_ns"), target)), pyInt(150_000_000), ">") > 0) {
                return false to "late or early camera gesture"
            }
        }
        if (!(pyCompare(rightUp.get("end_ns"), frames[frames.size - 3].get("start_ns"), "<=") <= 0 &&
                pyCompare(frames[frames.size - 3].get("start_ns"), frames[frames.size - 3].get("end_ns"), "<=") <= 0 &&
                pyCompare(frames[frames.size - 3].get("end_ns"), brakeDown.get("start_ns"), "<=") <= 0 &&
                pyCompare(brakeDown.get("start_ns"), brakeDown.get("end_ns"), "<=") <= 0 &&
                pyCompare(brakeDown.get("end_ns"), brakeUp.get("start_ns"), "<") < 0 &&
                pyCompare(brakeUp.get("start_ns"), brakeUp.get("end_ns"), "<=") <= 0 &&
                pyCompare(brakeUp.get("end_ns"), frames[frames.size - 1].get("start_ns"), "<=") <= 0)
        ) {
            return false to "drive and brake out of order"
        }
        if (!(pyCompare(brakeDown.get("end_ns"), brakeFollows[0].get("start_ns"), "<") < 0 &&
                pyCompare(brakeFollows[0].get("start_ns"), brakeFollows[0].get("end_ns"), "<") < 0 &&
                pyCompare(brakeFollows[0].get("end_ns"), frames[frames.size - 2].get("start_ns"), "<") < 0 &&
                pyCompare(frames[frames.size - 2].get("start_ns"), frames[frames.size - 2].get("end_ns"), "<") < 0 &&
                pyCompare(frames[frames.size - 2].get("end_ns"), brakeFollows[1].get("start_ns"), "<") < 0 &&
                pyCompare(brakeFollows[1].get("start_ns"), brakeFollows[1].get("end_ns"), "<") < 0 &&
                pyCompare(brakeFollows[1].get("end_ns"), brakeUp.get("start_ns"), "<") < 0)
        ) {
            return false to "brake camera or frame out of order"
        }
        for (index in 1..6) {
            if (!(pyCompare(follows[index * 2 - 1].get("end_ns"), frames[index + 1].get("start_ns"), "<=") <= 0 &&
                    pyCompare(frames[index + 1].get("start_ns"), frames[index + 1].get("end_ns"), "<") < 0 &&
                    pyCompare(frames[index + 1].get("end_ns"), rightUp.get("start_ns"), "<") < 0)
            ) {
                return false to "drive frame out of order"
            }
        }
        if (pyCompare(
                pySubtract(frames[1].get("start_ns"), rightDown.get("end_ns")),
                pyInt(200_000_000),
                ">",
            ) > 0
        ) {
            return false to "drive start frame late"
        }
        for (index in 1..6) {
            val target = pyAdd(rightDown.get("end_ns"), pyInt(index * 1_000_000_000L))
            val gap = pySubtract(frames[index + 1].get("start_ns"), target)
            if (!(pyCompare(gap, pyInt(0), ">=") >= 0 && pyCompare(gap, pyInt(200_000_000), "<=") <= 0)) {
                return false to "drive frame late or early"
            }
        }
        if (pyCompare(
                pySubtract(frames[frames.size - 3].get("start_ns"), rightUp.get("end_ns")),
                pyInt(200_000_000),
                ">",
            ) > 0 ||
            pyCompare(
                pySubtract(frames[frames.size - 1].get("start_ns"), brakeUp.get("end_ns")),
                pyInt(200_000_000),
                ">",
            ) > 0 ||
            pyCompare(
                pyAbsolute(
                    pySubtract(
                        frames[frames.size - 2].get("start_ns"),
                        pyAdd(brakeDown.get("end_ns"), pyInt(500_000_000)),
                    ),
                ),
                pyInt(150_000_000),
                ">",
            ) > 0
        ) {
            return false to "drive or brake frame late"
        }
        for ((key, down, up, duration) in listOf(
            Quad("Right", rightDown, rightUp, 7_000_000_000L),
            Quad("s", brakeDown, brakeUp, 1_000_000_000L),
        )) {
            val lower = pySubtract(up.get("start_ns"), down.get("end_ns"))
            val upper = pySubtract(up.get("end_ns"), down.get("start_ns"))
            val low = pyInt(duration - 150_000_000)
            val high = pyInt(duration + 150_000_000)
            if (!(pyCompare(lower, low, ">=") >= 0 && pyCompare(lower, high, "<=") <= 0 &&
                    pyCompare(upper, low, ">=") >= 0 && pyCompare(upper, high, "<=") <= 0)
            ) {
                return false to "$key hold outside bounded duration: " +
                    "${pythonStr(lower)}..${pythonStr(upper)} ns"
            }
        }
        if (frames.zipWithNext().any { (a, b) ->
                pyCompare(a.get("end_ns"), b.get("start_ns"), ">=") >= 0
            }
        ) {
            return false to "frames missing or out of order"
        }
        if (frames.any {
                pyCompare(pySubtract(it.get("end_ns"), it.get("start_ns")), pyInt(250_000_000), ">") > 0
            }
        ) {
            return false to "slow frame capture"
        }
        for ((frame, digest) in frames.zip(hashes)) {
            val name = (frame.get("name") as PyValue.Text).value + ".png"
            val data = readFrame(name) ?: return false to "missing frame $name"
            if (!pyEquals(frame.getOrNull("file") ?: PyValue.Null, pyText(name)) ||
                !pyEquals(digest.getOrNull("file") ?: PyValue.Null, pyText(name)) ||
                !validPng(data, decodes) ||
                !pyEquals(digest.getOrNull("sha256") ?: PyValue.Null, pyText(Sha256.of(data)))
            ) {
                return false to "invalid or changed frame $name"
            }
            if (pyCompare(frame.get("end_ns"), digest.get("start_ns"), ">") > 0) {
                return false to "frame hash before capture completion"
            }
        }
        return true to "11 timestamped frames, 16 recorded upper-canvas drags, " +
            "bounded 7 s drive and 1 s brake; visual review separate"
    }

    private val strictJson = kotlinx.serialization.json.Json {
        allowSpecialFloatingPointValues = true
    }
}

/** Python's `str.splitlines()` over `\n`, dropping the empty tail after a final newline. */
fun pythonSplitlines(text: String): List<String> {
    if (text.isEmpty()) return emptyList()
    val lines = text.split('\n')
    return if (lines.last().isEmpty()) lines.dropLast(1) else lines
}

/** Python's JSON error text for a malformed document, as far as the JVM reader can name it. */
internal fun pythonJsonError(error: Throwable): String = error.message ?: error.toString()

internal fun pyAdd(left: PyValue, right: PyValue): PyValue = when {
    left is PyValue.Int && right is PyValue.Int -> pyInt(left.value + right.value)
    else -> pyReal(pyNumberValue(left) + pyNumberValue(right))
}

private data class Quad(
    val key: String,
    val down: PyValue,
    val up: PyValue,
    val duration: Long,
)
