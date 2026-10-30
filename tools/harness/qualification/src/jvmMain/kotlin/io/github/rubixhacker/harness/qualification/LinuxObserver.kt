package io.github.rubixhacker.harness.qualification

import io.github.rubixhacker.harness.contract.CanonicalJson
import java.io.IOException
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.LinkOption
import java.nio.file.Path
import java.nio.file.StandardOpenOption
import java.nio.file.attribute.BasicFileAttributes
import java.util.concurrent.TimeUnit
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

/**
 * `independent_linux_observer`: the `/proc` reads, the witness archive, and `verify`.
 *
 * The ptrace tracer (`capture`, `_launch`, `_ptrace`) is not ported: it needs a native `ptrace`
 * call per traced child, which this harness does not make. Everything that reads `/proc`,
 * writes the event log, and re-derives a witness from recorded events is ported, so an observer
 * archive produced by the reference verifies here.
 */
object LinuxObserver {
    const val MAX_ARCHIVE_FILES = 4096
    const val MAX_ARCHIVE_BYTES = 2L * 1024 * 1024 * 1024
    const val MAX_INPUT_BYTES = MAX_ARCHIVE_BYTES
    const val MAX_IMAGE_BYTES = MAX_ARCHIVE_BYTES
    const val MAX_LOG_BYTES = 16L * 1024 * 1024
    const val ZERO = WitnessDerivation.ZERO

    /** `_json_bytes`: canonical JSON with ASCII escaping, as the event chain hashes it. */
    fun jsonBytes(value: JsonElement): ByteArray =
        CanonicalJson.render(value).toByteArray(StandardCharsets.US_ASCII)

    /** `_sha_file`: hash one regular, unlinked input within the byte limit. */
    fun shaFile(path: Path, deadlineNanos: Long? = null, byteLimit: Long? = null, label: String = "input"): String {
        val limit = minOf(MAX_INPUT_BYTES, byteLimit ?: MAX_INPUT_BYTES)
        val attributes = identityOf(path) ?: throw ObservationError("not a regular file: $path")
        if (!attributes.regular) throw ObservationError("not a regular file: $path")
        if (attributes.size > limit) throw ObservationError("$label byte limit exceeded: $path")
        val digest = java.security.MessageDigest.getInstance("SHA-256")
        var read = 0L
        Files.newByteChannel(path, StandardOpenOption.READ, LinkOption.NOFOLLOW_LINKS).use { channel ->
            val block = java.nio.ByteBuffer.allocate(1024 * 1024)
            while (true) {
                if (deadlineNanos != null && System.nanoTime() > deadlineNanos) {
                    throw ObservationError("trace timeout during file hashing")
                }
                block.clear()
                val count = channel.read(block)
                if (count < 0) break
                read += count
                if (read > limit) throw ObservationError("$label byte limit exceeded: $path")
                digest.update(block.array(), 0, count)
            }
        }
        val after = identityOf(path) ?: throw ObservationError("file changed during hashing: $path")
        if (after.size != attributes.size || after.mtimeNs != attributes.mtimeNs ||
            after.dev != attributes.dev || after.ino != attributes.ino
        ) {
            throw ObservationError("file changed during hashing: $path")
        }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }

    /** `_safe_input`: one absolute, regular, unlinked file. */
    fun safeInput(path: Path): Path {
        val absolute = path.toAbsolutePath()
        if (Files.isSymbolicLink(absolute) || !Files.isRegularFile(absolute, LinkOption.NOFOLLOW_LINKS) ||
            unixAttribute(absolute, "nlink") != 1L
        ) {
            throw ObservationError("input must be one regular, unlinked file: $absolute")
        }
        return absolute
    }

    /**
     * `_archive_digest`: the canonical digest of the observed archive.
     *
     * The reference opens members relative to an open directory handle; this port re-reads path
     * identities before and after each member and hashes every file twice (see [ArchiveScan] for
     * the same limitation).
     */
    fun archiveDigest(path: Path, deadlineNanos: Long? = null): String {
        val absolute = path.toAbsolutePath().normalize()
        if (".." in absolute.toString().split('/') || absolute.parent == null) {
            throw ObservationError("archive path uses traversal or has no parent")
        }
        val checkTime = {
            if (deadlineNanos != null && System.nanoTime() > deadlineNanos) {
                throw ObservationError("archive seal exceeded trace timeout")
            }
        }
        val root = identityOf(absolute) ?: throw ObservationError("archive is not a regular file or directory: $absolute")
        if (root.regular) {
            return hashMember(absolute, root, MAX_ARCHIVE_BYTES, deadlineNanos, checkTime)
        }
        if (!root.directory) {
            throw ObservationError("archive is not a regular file or directory: $absolute")
        }
        val files = mutableListOf<JsonObject>()
        var total = 0L
        var members = 0L
        val seen = mutableSetOf<String>()

        fun visit(directory: Path, prefix: String) {
            checkTime()
            val entries = Files.newDirectoryStream(directory).use { stream -> stream.toList() }
            members += entries.size
            if (members > 2L * MAX_ARCHIVE_FILES) throw ObservationError("archive member limit exceeded")
            for (entry in entries) {
                checkTime()
                val name = entry.fileName.toString()
                val relative = if (prefix.isEmpty()) name else "$prefix/$name"
                if ("\\" in relative || "\n" in relative || "\r" in relative ||
                    relative.split('/').any { it in setOf("", ".", "..") }
                ) {
                    throw ObservationError("unsafe archive member: $relative")
                }
                if (!seen.add(relative)) throw ObservationError("duplicate archive member: $relative")
                val member = identityOf(entry)
                    ?: throw ObservationError("archive scan failed: $relative")
                if (member.directory) {
                    visit(entry, relative)
                    val after = identityOf(entry)
                    if (after == null || after != member) {
                        throw ObservationError("archive directory changed: $relative")
                    }
                    continue
                }
                if (files.size >= MAX_ARCHIVE_FILES) throw ObservationError("archive file limit exceeded")
                val remaining = MAX_ARCHIVE_BYTES - total
                val digest = hashMember(entry, member, remaining, deadlineNanos, checkTime)
                total += member.size
                files.add(
                    JsonObject(
                        linkedMapOf(
                            "path" to JsonPrimitive(relative),
                            "sha256" to JsonPrimitive(digest),
                            "mtime_ns" to JsonPrimitive(member.mtimeNs),
                        ),
                    ),
                )
            }
        }

        visit(absolute, "")
        val after = identityOf(absolute)
        if (after == null || after != root) throw ObservationError("archive root changed during scan")
        if (files.none { Py.str(it["path"]) == "receipt.json" }) {
            throw ObservationError("archive receipt.json is absent")
        }
        val sorted = JsonArray(files.sortedWith { left, right ->
            CanonicalText.compare(Py.str(left["path"])!!, Py.str(right["path"])!!)
        })
        return io.github.rubixhacker.harness.contract.Sha256.of(jsonBytes(sorted))
    }

    private fun hashMember(
        path: Path,
        before: FileIdentity,
        remaining: Long,
        deadlineNanos: Long?,
        checkTime: () -> Unit,
    ): String {
        if (!before.regular || before.nlink != 1L) {
            throw ObservationError("nonregular or hardlinked archive member: ${path.fileName}")
        }
        if (before.size > remaining) throw ObservationError("archive byte limit exceeded")
        val digest = java.security.MessageDigest.getInstance("SHA-256")
        var size = 0L
        Files.newByteChannel(path, StandardOpenOption.READ, LinkOption.NOFOLLOW_LINKS).use { channel ->
            val block = java.nio.ByteBuffer.allocate(1024 * 1024)
            while (true) {
                if (deadlineNanos != null) checkTime()
                block.clear()
                val count = channel.read(block)
                if (count < 0) break
                size += count
                if (size > remaining) throw ObservationError("archive byte limit exceeded")
                digest.update(block.array(), 0, count)
            }
        }
        val after = identityOf(path) ?: throw ObservationError("archive member changed during hashing: ${path.fileName}")
        if (size != before.size || after.size != before.size ||
            after.mtimeNs != before.mtimeNs || after.dev != before.dev || after.ino != before.ino
        ) {
            throw ObservationError("archive member changed during hashing: ${path.fileName}")
        }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }

    /** `_stat`: the parent pid and start ticks of one process. */
    fun stat(pid: Long): Pair<Long, Long> {
        val raw = try {
            Files.readString(Path.of("/proc/$pid/stat"))
        } catch (error: IOException) {
            throw ObservationError("pid $pid is not observable: ${error.message}")
        }
        val tail = raw.substring(raw.lastIndexOf(')') + 2)
        val fields = tail.split(Regex("\\s+")).filter { it.isNotEmpty() }
        if (fields.size < 20) throw ObservationError("pid $pid stat is incomplete")
        return fields[1].toLong() to fields[19].toLong()
    }

    /** `_image`: the live image and argv of one process. */
    fun image(pid: Long, deadlineNanos: Long? = null): JsonObject {
        val (_, startTicks) = stat(pid)
        val exe = Path.of("/proc/$pid/exe")
        val attributes = try {
            Files.readAttributes(exe, BasicFileAttributes::class.java)
        } catch (error: IOException) {
            throw ObservationError("pid $pid executable is not observable: ${error.message}")
        }
        if (!attributes.isRegularFile) {
            throw ObservationError("pid $pid executable is not a regular image")
        }
        if (attributes.size() > MAX_IMAGE_BYTES) {
            throw ObservationError("process image byte limit exceeded for pid $pid")
        }
        val path = try {
            Files.readSymbolicLink(exe).toString()
        } catch (error: IOException) {
            throw ObservationError("pid $pid executable path is not observable: ${error.message}")
        }
        val digest = java.security.MessageDigest.getInstance("SHA-256")
        var read = 0L
        try {
            Files.newInputStream(exe).use { stream ->
                val block = ByteArray(1024 * 1024)
                while (true) {
                    if (deadlineNanos != null && System.nanoTime() > deadlineNanos) {
                        throw ObservationError("trace timeout during process image capture")
                    }
                    val count = stream.read(block)
                    if (count < 0) break
                    read += count
                    if (read > MAX_IMAGE_BYTES) {
                        throw ObservationError("process image byte limit exceeded for pid $pid")
                    }
                    digest.update(block, 0, count)
                }
            }
        } catch (error: IOException) {
            throw ObservationError("pid $pid executable is not readable: ${error.message}")
        }
        val (_, afterTicks) = stat(pid)
        if (startTicks != afterTicks) {
            throw ObservationError("pid $pid start identity changed during image capture")
        }
        val argv = readArgv(pid)
        if (argv.isEmpty()) throw ObservationError("pid $pid has no observable argv")
        return buildJsonObject {
            put("pid", JsonPrimitive(pid))
            put("start_ticks", JsonPrimitive(startTicks))
            put("executable_path", JsonPrimitive(path))
            put("executable_dev", JsonPrimitive(devOf(attributes, exe)))
            put("executable_ino", JsonPrimitive(inoOf(attributes, exe)))
            put("executable_sha256", JsonPrimitive(digest.digest().joinToString("") { "%02x".format(it) }))
            put("argv", JsonArray(argv.map { JsonPrimitive(it) }))
        }
    }

    private fun devOf(attributes: BasicFileAttributes, path: Path): Long =
        unixAttribute(path, "dev") ?: fileKeyPart(attributes, 0)

    private fun inoOf(attributes: BasicFileAttributes, path: Path): Long =
        unixAttribute(path, "ino") ?: fileKeyPart(attributes, 1)

    private fun fileKeyPart(attributes: BasicFileAttributes, index: Int): Long {
        val key = attributes.fileKey()?.toString() ?: return 0L
        return key.substringAfter('(', "").substringBefore(')').split(',')
            .mapNotNull { it.trim().toLongOrNull() }.getOrNull(index) ?: 0L
    }

    /** `_identity`: the boot id and start ticks of one process. */
    fun identity(pid: Long, bootId: String): JsonObject {
        val (parent, startTicks) = stat(pid)
        return buildJsonObject {
            put("pid", JsonPrimitive(pid))
            put("boot_id", JsonPrimitive(bootId))
            put("parent_pid", JsonPrimitive(parent))
            put("start_ticks", JsonPrimitive(startTicks))
        }
    }

    /** `_identity` with the boot id read from this host. */
    fun identity(pid: Long): JsonObject = identity(pid, bootId())

    fun bootId(): String = try {
        Files.readString(Path.of("/proc/sys/kernel/random/boot_id")).trim()
    } catch (error: IOException) {
        throw ObservationError("kernel boot identity is unavailable: ${error.message}")
    }

    /** `_expected`: NAME=EXECUTABLE expectations, each pinned by digest. */
    fun expected(specs: List<String>, deadlineNanos: Long? = null): Map<String, JsonObject> {
        val result = LinkedHashMap<String, JsonObject>()
        for (item in specs) {
            if ("=" !in item) throw ObservationError("expected process must be NAME=EXECUTABLE")
            val name = item.substringBefore('=')
            val raw = item.substringAfter('=')
            if (name.isEmpty() || name == "build" || name in result || "/" in name) {
                throw ObservationError("invalid expected process name: $name")
            }
            val path = try {
                Path.of(raw).toRealPath()
            } catch (error: IOException) {
                throw ObservationError("expected executable is not a file: $raw")
            }
            if (!Files.isRegularFile(path)) {
                throw ObservationError("expected executable is not a file: $path")
            }
            result[name] = buildJsonObject {
                put("path", JsonPrimitive(path.toString()))
                put("sha256", JsonPrimitive(shaFile(path, deadlineNanos)))
            }
        }
        return result
    }

    /** `_generated_expected`: child executables that must not exist before the run. */
    fun generatedExpected(specs: List<String>, existing: Map<String, JsonObject>): Map<String, JsonObject> {
        val result = LinkedHashMap<String, JsonObject>()
        for (item in specs) {
            if ("=" !in item) throw ObservationError("generated process must be NAME=EXECUTABLE")
            val name = item.substringBefore('=')
            val requested = Path.of(item.substringAfter('='))
            if (name.isEmpty() || name == "build" || name in existing || name in result ||
                "/" in name || !requested.isAbsolute || ".." in requested.toString().split('/')
            ) {
                throw ObservationError("invalid generated process selection: $item")
            }
            val path = requested.parent.resolve(requested.fileName.toString())
            if (Files.exists(path) || Files.isSymbolicLink(path)) {
                throw ObservationError("generated executable already exists: $path")
            }
            result[name] = buildJsonObject {
                put("path", JsonPrimitive(path.toString()))
                put("sha256", JsonNull)
            }
        }
        return result
    }

    /** `_checked_files`: exactly the two observer outputs, read without following links. */
    fun checkedFiles(root: Path): Map<String, ByteArray> {
        // `pathlib.absolute()` keeps `..` components, so the traversal check sees them.
        val requested = root.toAbsolutePath()
        if (".." in requested.toString().split('/')) {
            throw ObservationError("observer root uses path traversal")
        }
        if (Files.isSymbolicLink(requested)) throw ObservationError("observer root is symbolic")
        val real = try {
            requested.parent.toRealPath().resolve(requested.fileName.toString())
        } catch (error: IOException) {
            throw ObservationError("observer root is absent: ${error.message}")
        }
        val names = Files.newDirectoryStream(real).use { stream ->
            stream.map { it.fileName.toString() }.sortedWith(CanonicalText::compare)
        }
        if (names.toSet() != setOf("events.jsonl", "witness.json")) {
            throw ObservationError("observer output inventory differs")
        }
        val result = LinkedHashMap<String, ByteArray>()
        for ((name, limit) in listOf("events.jsonl" to MAX_LOG_BYTES, "witness.json" to 1024L * 1024)) {
            val path = real.resolve(name)
            if (Files.isSymbolicLink(path) || !Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)) {
                throw ObservationError("symbolic or inaccessible output: $name")
            }
            if (unixAttribute(path, "nlink") != 1L) {
                throw ObservationError("symbolic or hardlinked output: $name")
            }
            val size = Files.size(path)
            if (size > limit) throw ObservationError("oversized observer output: $name")
            val bytes = Files.readAllBytes(path)
            if (bytes.size > limit || Files.size(path) != size) {
                throw ObservationError("changed observer output during read: $name")
            }
            result[name] = bytes
        }
        return result
    }

    /** `verify`: the witness reconstructed from the event chain must equal the recorded one. */
    fun verify(root: Path, includeEvents: Boolean = false): Pair<JsonObject, List<JsonObject>> {
        val files = checkedFiles(root)
        val raw = files.getValue("events.jsonl")
        if (raw.isEmpty() || raw.last() != '\n'.code.toByte()) {
            throw ObservationError("event log is truncated or oversized")
        }
        val lines = splitLines(raw)
        if (lines.isEmpty() || lines.size > WitnessDerivation.MAX_EVENTS) {
            throw ObservationError("event log is empty or oversized")
        }
        var previous = ZERO
        val rows = mutableListOf<JsonObject>()
        for ((index, line) in lines.withIndex()) {
            val row = StrictObjectJson.parse(line.toString(StandardCharsets.UTF_8)) as? JsonObject
                ?: throw ObservationError("changed event bytes at ${index + 1}")
            if (line.toString(StandardCharsets.ISO_8859_1) !=
                String(jsonBytes(row), StandardCharsets.ISO_8859_1)
            ) {
                throw ObservationError("changed event bytes at ${index + 1}")
            }
            val members = LinkedHashMap(row)
            val digest = Py.str(members.remove("sha256"))
            if (!Py.equalsInt(members["seq"], (index + 1).toLong()) ||
                Py.str(members["previous_sha256"]) != previous
            ) {
                throw ObservationError("event sequence or chain gap at ${index + 1}")
            }
            if (digest != io.github.rubixhacker.harness.contract.Sha256.of(jsonBytes(JsonObject(members)))) {
                throw ObservationError("changed event bytes at ${index + 1}")
            }
            members["sha256"] = JsonPrimitive(digest!!)
            rows.add(JsonObject(members))
            previous = digest
        }
        if (raw.size > WitnessDerivation.limits(rows.first()).getValue("log_bytes")) {
            throw ObservationError("observer event log byte limit exceeded")
        }
        val witnessRaw = files.getValue("witness.json")
        val witness = StrictObjectJson.parse(witnessRaw.toString(StandardCharsets.UTF_8)) as? JsonObject
            ?: throw ObservationError("changed witness bytes")
        if (witnessRaw.toString(StandardCharsets.ISO_8859_1) !=
            String(jsonBytes(witness) + "\n".toByteArray(), StandardCharsets.ISO_8859_1)
        ) {
            throw ObservationError("changed witness bytes")
        }
        val reconstructed = try {
            WitnessDerivation.derive(rows)
        } catch (error: ObservationError) {
            // The reference wraps only Python's structural errors, not its own observation errors.
            throw error
        } catch (error: RuntimeException) {
            throw ObservationError("incomplete event structure: ${error.message}")
        }
        if (witness != reconstructed) {
            throw ObservationError("witness differs from observed event log")
        }
        return if (includeEvents) witness to rows else witness to emptyList()
    }

    /** Python's `bytes.splitlines()` boundaries. */
    private fun splitLines(raw: ByteArray): List<ByteArray> {
        val lines = mutableListOf<ByteArray>()
        var start = 0
        var index = 0
        while (index < raw.size) {
            val byte = raw[index].toInt() and 0xff
            val boundary = byte == 0x0a || byte == 0x0d || byte == 0x0b || byte == 0x0c ||
                byte == 0x1c || byte == 0x1d || byte == 0x1e || byte == 0x85
            if (boundary) {
                lines.add(raw.copyOfRange(start, index))
                if (byte == 0x0d && index + 1 < raw.size && raw[index + 1].toInt() == 0x0a) index++
                start = index + 1
            }
            index++
        }
        return lines
    }

    private fun unixAttribute(path: Path, name: String): Long? = try {
        when (val value = Files.getAttribute(path, "unix:$name", LinkOption.NOFOLLOW_LINKS)) {
            is Number -> value.toLong()
            is java.nio.file.attribute.FileTime -> value.to(TimeUnit.NANOSECONDS)
            else -> null
        }
    } catch (_: IOException) {
        null
    } catch (_: UnsupportedOperationException) {
        null
    }

    private fun readArgv(pid: Long): List<String> {
        val raw = try {
            Files.readAllBytes(Path.of("/proc/$pid/cmdline"))
        } catch (error: IOException) {
            throw ObservationError("pid $pid has no observable argv")
        }
        val parts = mutableListOf<String>()
        var start = 0
        for (index in raw.indices) {
            if (raw[index] == 0.toByte()) {
                if (index > start) parts.add(String(raw.copyOfRange(start, index), StandardCharsets.UTF_8))
                start = index + 1
            }
        }
        if (start < raw.size) parts.add(String(raw.copyOfRange(start, raw.size), StandardCharsets.UTF_8))
        return parts
    }

    /** One path's identity, as the reference's `st_*` tuples compare it. */
    private data class FileIdentity(
        val dev: Long?,
        val ino: Long?,
        val nlink: Long?,
        val regular: Boolean,
        val directory: Boolean,
        val size: Long,
        val mtimeNs: Long,
    )

    private fun identityOf(path: Path): FileIdentity? = try {
        val attributes = Files.readAttributes(path, BasicFileAttributes::class.java, LinkOption.NOFOLLOW_LINKS)
        FileIdentity(
            dev = unixAttribute(path, "dev"),
            ino = unixAttribute(path, "ino"),
            nlink = unixAttribute(path, "nlink"),
            regular = attributes.isRegularFile,
            directory = attributes.isDirectory,
            size = attributes.size(),
            mtimeNs = attributes.lastModifiedTime().to(TimeUnit.NANOSECONDS),
        )
    } catch (_: IOException) {
        null
    }
}

/**
 * `independent_linux_observer.EventLog`: the chained event log of one observation.
 *
 * Terminal events (`error`, `end`) keep their reserved slots, so a failing observation can still
 * record why it failed after the ordinary limit is reached.
 */
class ObserverEventLog(
    root: Path,
    private val eventLimit: Int = WitnessDerivation.DEFAULT_EVENTS,
    private val byteLimit: Long = WitnessDerivation.DEFAULT_LOG_BYTES.toLong(),
) {
    val root: Path
    private val channel: java.nio.channels.FileChannel
    var count = 0
        private set
    var head = WitnessDerivation.ZERO
        private set
    val rows = mutableListOf<JsonObject>()
    private var size = 0L

    init {
        val requested = root.toAbsolutePath()
        val name = requested.fileName?.toString() ?: ""
        if (".." in requested.toString().split('/') || name in setOf("", ".", "..")) {
            throw ObservationError("observer output uses path traversal")
        }
        val real = try {
            requested.parent.toRealPath().resolve(name)
        } catch (error: IOException) {
            throw ObservationError("observer output parent is absent: ${error.message}")
        }
        Files.createDirectory(real)
        this.root = real
        channel = java.nio.channels.FileChannel.open(
            real.resolve("events.jsonl"),
            StandardOpenOption.WRITE,
            StandardOpenOption.CREATE_NEW,
        )
    }

    fun add(kind: String, data: JsonObject = JsonObject(emptyMap())): JsonObject {
        val terminal = kind == "error" || kind == "end"
        val reserved = when {
            terminal -> 0
            kind == "archive" -> 1
            else -> 2
        }
        if (count >= eventLimit - reserved) throw ObservationError("event limit exceeded")
        val body = LinkedHashMap<String, JsonElement>()
        body["seq"] = JsonPrimitive(count + 1)
        body["previous_sha256"] = JsonPrimitive(head)
        body["kind"] = JsonPrimitive(kind)
        body["observed_at_ns"] = JsonPrimitive(System.nanoTime())
        body["observed_wall_ns"] = JsonPrimitive(System.currentTimeMillis() * 1_000_000)
        for ((key, value) in data) body[key] = value
        val digest = io.github.rubixhacker.harness.contract.Sha256.of(LinuxObserver.jsonBytes(JsonObject(body)))
        val row = JsonObject(LinkedHashMap(body).apply { put("sha256", JsonPrimitive(digest)) })
        val raw = LinuxObserver.jsonBytes(row) + "\n".toByteArray()
        if (size + raw.size > byteLimit - (if (terminal) 0 else 4096)) {
            throw ObservationError("event log byte limit exceeded")
        }
        val buffer = java.nio.ByteBuffer.wrap(raw)
        while (buffer.hasRemaining()) channel.write(buffer)
        channel.force(true)
        count += 1
        head = digest
        rows.add(row)
        size += raw.size
        return row
    }

    fun close() {
        channel.close()
    }
}
