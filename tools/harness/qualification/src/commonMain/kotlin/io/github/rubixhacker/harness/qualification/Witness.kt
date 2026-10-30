package io.github.rubixhacker.harness.qualification

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

/** Thrown when an observation, a witness, or an observed archive cannot be trusted. */
class ObservationError(message: String) : IllegalArgumentException(message)

/**
 * `independent_linux_observer.verify` strictness: JSON objects may not repeat a key and may not
 * carry a non-finite constant, and the parser preserves the order the bytes were written in.
 *
 * kotlinx.serialization keeps the last duplicate silently, so witness evidence needs this parser:
 * a repeated key would otherwise let one reader see a different document than another.
 */
object StrictObjectJson {
    fun parse(text: String): JsonElement {
        val parser = Parser(text)
        val value = parser.value()
        parser.skipWhitespace()
        if (!parser.atEnd()) throw ObservationError("trailing JSON content")
        return value
    }

    private class Parser(private val source: String) {
        private var index = 0

        fun atEnd(): Boolean = index >= source.length

        fun skipWhitespace() {
            while (index < source.length && source[index] in " \t\n\r") index++
        }

        fun value(): JsonElement {
            skipWhitespace()
            if (atEnd()) throw ObservationError("unexpected end of JSON")
            return when (val char = source[index]) {
                '{' -> objectValue()
                '[' -> arrayValue()
                '"' -> JsonPrimitive(string())
                't' -> literal("true", JsonPrimitive(true))
                'f' -> literal("false", JsonPrimitive(false))
                'n' -> literal("null", JsonNull)
                else -> if (char == '-' || char.isDigit()) number()
                else throw ObservationError("unexpected JSON character: $char")
            }
        }

        private fun literal(text: String, value: JsonElement): JsonElement {
            if (!source.startsWith(text, index)) throw ObservationError("invalid JSON literal")
            index += text.length
            return value
        }

        private fun objectValue(): JsonObject {
            index++
            skipWhitespace()
            if (!atEnd() && source[index] == '}') {
                index++
                return JsonObject(emptyMap())
            }
            val members = LinkedHashMap<String, JsonElement>()
            while (true) {
                skipWhitespace()
                if (atEnd() || source[index] != '"') throw ObservationError("invalid JSON object key")
                val key = string()
                if (key in members) throw ObservationError("duplicate JSON key: $key")
                skipWhitespace()
                if (atEnd() || source[index] != ':') throw ObservationError("invalid JSON object")
                index++
                members[key] = value()
                skipWhitespace()
                if (atEnd()) throw ObservationError("unterminated JSON object")
                when (source[index]) {
                    ',' -> index++
                    '}' -> {
                        index++
                        return JsonObject(members)
                    }
                    else -> throw ObservationError("invalid JSON object separator")
                }
            }
        }

        private fun arrayValue(): JsonArray {
            index++
            skipWhitespace()
            if (!atEnd() && source[index] == ']') {
                index++
                return JsonArray(emptyList())
            }
            val items = mutableListOf<JsonElement>()
            while (true) {
                items.add(value())
                skipWhitespace()
                if (atEnd()) throw ObservationError("unterminated JSON array")
                when (source[index]) {
                    ',' -> index++
                    ']' -> {
                        index++
                        return JsonArray(items)
                    }
                    else -> throw ObservationError("invalid JSON array separator")
                }
            }
        }

        private fun string(): String {
            index++
            val out = StringBuilder()
            while (true) {
                if (atEnd()) throw ObservationError("unterminated JSON string")
                when (val char = source[index]) {
                    '"' -> {
                        index++
                        return out.toString()
                    }
                    '\\' -> {
                        index++
                        if (atEnd()) throw ObservationError("unterminated JSON escape")
                        when (val escape = source[index]) {
                            '"' -> out.append('"')
                            '\\' -> out.append('\\')
                            '/' -> out.append('/')
                            'b' -> out.append('\b')
                            'f' -> out.append('\u000C')
                            'n' -> out.append('\n')
                            'r' -> out.append('\r')
                            't' -> out.append('\t')
                            'u' -> {
                                if (index + 4 >= source.length) {
                                    throw ObservationError("invalid JSON unicode escape")
                                }
                                val hex = source.substring(index + 1, index + 5)
                                val code = hex.toIntOrNull(16)
                                    ?: throw ObservationError("invalid JSON unicode escape")
                                out.append(code.toChar())
                                index += 4
                            }
                            else -> throw ObservationError("invalid JSON escape: $escape")
                        }
                        index++
                    }
                    else -> {
                        if (char.code < 0x20) throw ObservationError("invalid JSON string character")
                        out.append(char)
                        index++
                    }
                }
            }
        }

        private fun number(): JsonPrimitive {
            val start = index
            if (source[index] == '-') index++
            while (index < source.length && source[index].isDigit()) index++
            if (index < source.length && source[index] == '.') {
                index++
                while (index < source.length && source[index].isDigit()) index++
            }
            if (index < source.length && (source[index] == 'e' || source[index] == 'E')) {
                index++
                if (index < source.length && (source[index] == '+' || source[index] == '-')) index++
                while (index < source.length && source[index].isDigit()) index++
            }
            val text = source.substring(start, index)
            val integral = text.none { it == '.' || it == 'e' || it == 'E' }
            return if (integral) {
                text.toLongOrNull()?.let { JsonPrimitive(it) }
                    ?: throw ObservationError("invalid JSON number: $text")
            } else {
                JsonPrimitive(
                    text.toDoubleOrNull() ?: throw ObservationError("invalid JSON number: $text"),
                )
            }
        }
    }
}

/**
 * `independent_linux_observer._derive`: the witness a recorded event log reconstructs.
 *
 * Every claim in the witness is re-derived from the chain: process identities, image start
 * ticks, ancestry, exits reaped exactly once, the archive sealed after the last exit, and the
 * selected build and child executables. A single missing, repeated, or reordered event fails.
 */
object WitnessDerivation {
    const val SCHEMA = "independent-execution-witness/1"
    const val ZERO = "0000000000000000000000000000000000000000000000000000000000000000"
    const val DEFAULT_EVENTS = 4096
    const val DEFAULT_PROCESSES = 256
    const val DEFAULT_LOG_BYTES = 8 * 1024 * 1024
    const val MAX_EVENTS = 8192
    const val MAX_PROCESSES = 1024
    const val MAX_LOG_BYTES = 16 * 1024 * 1024
    val SHA = Regex("[0-9a-f]{64}")
    val COMMIT = Regex("[0-9a-f]{40}")

    /** `_limits`: the validated observer limits of a run event. */
    fun limits(run: JsonObject): Map<String, Long> {
        val declared = run["limits"] ?: buildJsonObject {
            put("processes", JsonPrimitive(DEFAULT_PROCESSES))
            put("events", JsonPrimitive(DEFAULT_EVENTS))
            put("log_bytes", JsonPrimitive(DEFAULT_LOG_BYTES))
        }
        val object_ = declared as? JsonObject
        val valid = object_ != null &&
            object_.keys == setOf("processes", "events", "log_bytes") &&
            listOf(
                Triple("processes", 1L, MAX_PROCESSES.toLong()),
                Triple("events", DEFAULT_EVENTS.toLong(), MAX_EVENTS.toLong()),
                Triple("log_bytes", DEFAULT_LOG_BYTES.toLong(), MAX_LOG_BYTES.toLong()),
            ).all { (key, floor, cap) ->
                Py.isInt(object_[key]) && Py.int(object_[key]) in floor..cap
            }
        if (!valid) {
            throw ObservationError("observer process, event, or log limit is invalid")
        }
        return linkedMapOf(
            "processes" to Py.int(object_!!["processes"]),
            "events" to Py.int(object_["events"]),
            "log_bytes" to Py.int(object_["log_bytes"]),
        )
    }

    /** `_matching_image`: an observed image names the same bytes as the expectation. */
    fun matchingImage(image: JsonObject, expected: JsonObject): Boolean {
        if (Py.str(image["executable_path"]) != Py.str(expected["path"])) return false
        val expectedSha = expected["sha256"]
        if (expectedSha != null && expectedSha !is JsonNull &&
            Py.str(image["executable_sha256"]) != Py.str(expectedSha)
        ) {
            return false
        }
        val contains = (expected["argv_contains"] as? JsonArray)?.mapNotNull { Py.str(it) } ?: emptyList()
        val argv = (image["argv"] as? JsonArray)?.mapNotNull { Py.str(it) } ?: emptyList()
        return contains.all { it in argv }
    }

    /** `_status`: exit code or signal of one wait status. */
    fun status(waitStatus: Long): Pair<Long?, Long?> {
        val signal = waitStatus and 0x7f
        val exit = (waitStatus shr 8) and 0xff
        return when {
            signal == 0L -> exit to null
            signal == 0x7fL -> null to null
            else -> null to signal
        }
    }

    fun derive(rows: List<JsonObject>): JsonObject {
        if (rows.isEmpty() || Py.str(rows.first()["kind"]) != "run" || Py.str(rows.last()["kind"]) != "end") {
            throw ObservationError("run start or end event is missing")
        }
        if (rows.size < 2 || Py.str(rows[rows.size - 2]["kind"]) != "archive") {
            throw ObservationError("event time or archive seal order differs")
        }
        for (index in 0 until rows.size - 1) {
            val row = rows[index]
            val following = rows[index + 1]
            if (!Py.isInt(row["observed_at_ns"]) ||
                Py.int(row["observed_at_ns"]) <= 0 ||
                Py.int(row["observed_at_ns"]) > Py.int(following["observed_at_ns"])
            ) {
                throw ObservationError("event time or archive seal order differs")
            }
        }
        val run = rows.first()
        val end = rows.last()
        val buildOnly = run["build_only"] ?: JsonPrimitive(false)
        if (buildOnly !is JsonPrimitive || (buildOnly.content != "true" && buildOnly.content != "false")) {
            throw ObservationError("build-only process selection differs")
        }
        val expectedProcesses = run["expected_processes"] as? JsonObject ?: JsonObject(emptyMap())
        if ((expectedProcesses.isNotEmpty()) == Py.truthy(buildOnly)) {
            throw ObservationError("build-only process selection differs")
        }
        val limits = limits(run)
        if (rows.size > limits.getValue("events")) {
            throw ObservationError("observer event limit exceeded")
        }
        if (Py.str(end["result"]) != "observed" ||
            !Py.isInt(end["lost_events"]) || Py.int(end["lost_events"]) != 0L
        ) {
            throw ObservationError("observation ended with an error or lost events")
        }
        if (rows.any { Py.str(it["kind"]) == "error" }) {
            throw ObservationError("observation error is present")
        }

        val boot = Py.str(run["boot_id"])
        val root = Py.int(run["root_pid"])
        val identities = LinkedHashMap<Long, Pair<String?, Long>>()
        val parents = LinkedHashMap<Long, Long>()
        val images = LinkedHashMap<Long, MutableList<JsonObject>>()
        val exits = LinkedHashMap<Long, JsonObject>()
        val reaped = LinkedHashMap<Long, JsonObject>()
        val pending = LinkedHashMap<Long, Pair<Long?, Long?>>()
        var archive: JsonObject? = null

        for (index in 1 until rows.size - 1) {
            val row = rows[index]
            val kind = Py.str(row["kind"])
            val pid = if (Py.isInt(row["pid"])) Py.int(row["pid"]) else null
            when (kind) {
                "spawn" -> {
                    if (pid == null || pid in identities || identities.size >= limits.getValue("processes")) {
                        throw ObservationError("duplicate or excessive process creation")
                    }
                    if (Py.str(row["boot_id"]) != boot || !Py.isInt(row["start_ticks"])) {
                        throw ObservationError("invalid process start identity")
                    }
                    val parent = Py.int(row["parent_pid"])
                    if (pid != root && parent !in identities) {
                        throw ObservationError("unobserved process ancestry")
                    }
                    identities[pid] = boot to Py.int(row["start_ticks"])
                    parents[pid] = parent
                    images[pid] = mutableListOf()
                }
                "image" -> {
                    if (pid == null || identities[pid] != (Py.str(row["boot_id"]) to Py.int(row["start_ticks"]))) {
                        throw ObservationError("wrong PID-start image identity")
                    }
                    val argv = row["argv"] as? JsonArray
                    if (pid in exits || argv == null || argv.isEmpty() ||
                        !SHA.matches(Py.str(row["executable_sha256"]) ?: "")
                    ) {
                        throw ObservationError("invalid observed image")
                    }
                    images.getValue(pid).add(row)
                }
                "exit" -> {
                    if (pid == null || identities[pid] != (Py.str(row["boot_id"]) to Py.int(row["start_ticks"]))) {
                        throw ObservationError("wrong PID-start exit identity")
                    }
                    if (pid in exits || images[pid].isNullOrEmpty()) {
                        throw ObservationError("process exited without a captured image")
                    }
                    exits[pid] = row
                    pending[pid] = nullableInt(row["exit_code"]) to nullableInt(row["signal"])
                }
                "reap" -> {
                    if (pid == null || pid !in pending || pid in reaped ||
                        status(Py.int(row["wait_status"])) != pending[pid]
                    ) {
                        throw ObservationError("missing or mismatched process exit")
                    }
                    reaped[pid] = row
                }
                "archive" -> {
                    if (archive != null || identities.keys != reaped.keys ||
                        !SHA.matches(Py.str(row["archive_sha256"]) ?: "")
                    ) {
                        throw ObservationError("archive was not sealed after all process exits")
                    }
                    archive = row
                }
                else -> throw ObservationError("unknown event kind: $kind")
            }
        }
        if (identities.keys != exits.keys || exits.keys != reaped.keys) {
            throw ObservationError("missing process image, exit, or reap")
        }
        if (root !in images || images.getValue(root).isEmpty()) {
            throw ObservationError("observed root process image is missing")
        }
        val sealed = archive ?: throw ObservationError("archive digest is missing")
        if (Py.truthy(run["launcher_seal_required"])) {
            val launcher = run["launcher"] as? JsonObject
            if (launcher == null || Py.str(sealed["launcher_after_sha256"]) != Py.str(launcher["sha256"])) {
                throw ObservationError("launcher changed across observed execution")
            }
        }

        val build = run["build"] as? JsonObject
            ?: throw ObservationError("wrong expected build executable")
        val buildImages = images.entries.flatMap { (_, list) -> list }
            .filter { Py.str(it["origin"]) == "exec" && matchingImage(it, build) }
        if (buildImages.isEmpty()) throw ObservationError("wrong expected build executable")
        val buildImage = buildImages.minByOrNull { Py.int(it["seq"]) }!!
        val buildPid = Py.int(buildImage["pid"])

        fun descendsFrom(pid: Long, ancestor: Long): Boolean {
            var current = pid
            while (current != root && current != ancestor) {
                current = parents[current] ?: return false
            }
            return current == ancestor
        }

        val selected = LinkedHashMap<String, JsonObject>()
        val used = mutableSetOf<Long>()
        for ((name, expectedElement) in expectedProcesses) {
            val expected = expectedElement as? JsonObject
                ?: throw ObservationError("expected executable was not observed: $name")
            val matches = images.entries.flatMap { (pid, list) -> list.map { pid to it } }
                .filter { (pid, image) ->
                    pid != root && pid != buildPid && descendsFrom(pid, buildPid) &&
                        Py.str(image["origin"]) == "exec" && matchingImage(image, expected) &&
                        pid !in used
                }
            if (matches.isEmpty()) {
                throw ObservationError("expected executable was not observed: $name")
            }
            val (pid, image) = matches.minByOrNull { Py.int(it.second["seq"]) }!!
            used.add(pid)
            selected[name] = image
        }
        if (identities.keys.any { nullableInt(exits.getValue(it)["exit_code"]) != 0L }) {
            throw ObservationError("observed process exited unsuccessfully")
        }

        fun process(image: JsonObject): JsonObject {
            val pid = Py.int(image["pid"])
            val spawn = rows.first { Py.str(it["kind"]) == "spawn" && Py.int(it["pid"]) == pid }
            val exit = exits.getValue(pid)
            return buildJsonObject {
                put("pid", JsonPrimitive(pid))
                put("parent_pid", spawn.getValue("parent_pid"))
                put("boot_id", boot?.let { JsonPrimitive(it) } ?: JsonNull)
                put("start_ticks", image.getValue("start_ticks"))
                put("executable_path", image.getValue("executable_path"))
                put("executable_dev", image.getValue("executable_dev"))
                put("executable_ino", image.getValue("executable_ino"))
                put("executable_sha256", image.getValue("executable_sha256"))
                put("argv", image.getValue("argv"))
                put("started_ns", image.getValue("observed_at_ns"))
                put("finished_ns", exit.getValue("observed_at_ns"))
                put("exit_code", exit["exit_code"] ?: JsonNull)
                put("signal", exit["signal"] ?: JsonNull)
            }
        }

        val executables = buildJsonObject {
            for ((name, image) in selected) put(name, image.getValue("executable_sha256"))
        }
        val processes = buildJsonObject {
            for ((name, image) in selected) put(name, process(image))
        }
        return buildJsonObject {
            put("schema", JsonPrimitive(SCHEMA))
            put("status", JsonPrimitive("OBSERVED_UNSIGNED"))
            put("qualification", JsonPrimitive("unqualified"))
            put("candidate_sha", run.getValue("candidate_sha"))
            put("lane", run.getValue("lane"))
            put("archive_sha256", sealed.getValue("archive_sha256"))
            put("runtime_identity", run.getValue("runtime_identity"))
            put("mode", run.getValue("mode"))
            put("staged_artifacts", run.getValue("staged_artifacts"))
            put("executables", executables)
            put("auditor", JsonPrimitive("independent-linux-ptrace-observer/1"))
            put("build", process(buildImage))
            put("processes", processes)
            put(
                "coverage",
                buildJsonObject {
                    put("processes", JsonPrimitive(identities.size))
                    put("images", JsonPrimitive(images.values.sumOf { it.size }))
                    put("fork_events", JsonPrimitive(identities.size - 1))
                    put("lost_events", end.getValue("lost_events"))
                    put("event_count", JsonPrimitive(rows.size))
                },
            )
            put("event_log_sha256", rows.last().getValue("sha256"))
        }
    }

    private fun nullableInt(value: JsonElement?): Long? =
        if (Py.isInt(value)) Py.int(value) else null
}
