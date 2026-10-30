package io.github.rubixhacker.harness.qualification

import io.github.rubixhacker.harness.contract.Sha256
import io.github.rubixhacker.harness.contract.StrictJson
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.LinkOption
import java.nio.file.Path
import java.nio.file.StandardOpenOption
import java.nio.file.attribute.BasicFileAttributes
import java.util.concurrent.TimeUnit
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/** The traversal deadline, which the reference raises as `TimeoutError`. */
class SafariContextTimeout(message: String) : Exception(message)

/**
 * `safari_yarn_lock.capture_karma_context`: the uploaded Safari context, built from the raw launch
 * context and the two Karma configurations the test modules generated.
 *
 * The reference walks both module packages with `dir_fd`-relative `os.open` calls, copies every
 * `*karma*.js` under `config/`, then copies the bounded set of launcher sidecars next to
 * `inventory.json`. The JVM has no descriptor-relative open, so every directory is resolved with
 * `NOFOLLOW_LINKS` component by component ([SafariReporterHost.openDirectoryNoFollow]) and every
 * file is opened with `NOFOLLOW_LINKS` and re-read for identity; the residual swap window is the
 * one recorded for the rest of the port.
 *
 * The reference patches `os.scandir` and the ten `CONTEXT_MAX_*` globals from its tests. The JVM has
 * no monkey-patching, so the same two seams are parameters: [bounds] carries the ten limits and
 * [scanHook] stands in for the enumeration call itself.
 */
object SafariContext {
    /** The `os.scandir` seam: called before each directory is enumerated, and may fail. */
    fun interface ScanHook {
        fun beforeScan(directory: Path, relative: String)
    }

    fun captureKarmaContext(
        repositoryInput: Path,
        candidateSha: String,
        contextInput: Path,
        rawContextInput: Path,
        bounds: SafariContextBounds = SafariContextBounds(),
        scanHook: ScanHook? = null,
    ): JsonObject {
        val repository = SafariReporterHost.resolvePath(repositoryInput)
        val context = contextInput
        val rawContext = rawContextInput
        if (!Py.SHA40.matches(candidateSha)) {
            throw IllegalArgumentException("invalid Safari context candidate SHA")
        }
        val resolvedContext = resolveLikePython(context)
        val resolvedRaw = resolveLikePython(rawContext)
        if (Files.isSymbolicLink(context) ||
            resolvedContext.startsWith(repository) ||
            resolvedRaw == resolvedContext ||
            resolvedRaw.startsWith(resolvedContext) ||
            resolvedContext.startsWith(resolvedRaw) ||
            resolvedRaw.startsWith(repository)
        ) {
            throw IllegalArgumentException(
                "Safari upload context must be a separate external directory",
            )
        }
        if (Files.exists(context, LinkOption.NOFOLLOW_LINKS) || Files.isSymbolicLink(context)) {
            throw SafariFileError("[Errno 17] File exists: '$context'")
        }
        Files.createDirectories(context)

        val inventory = SafariContextInventory(candidateSha, bounds)
        val started = System.nanoTime()
        val scan = Scan(context, bounds, inventory, started, scanHook)
        val config = context.resolve("config")
        try {
            SafariYarnLockHost.requireCandidate(repository, candidateSha)
            val reporterSource = SafariReporterHost.committedFragment(repository, candidateSha)
            inventory.values["reporter_source_sha256"] = JsonPrimitive(Sha256.of(reporterSource))
            if (Files.exists(config, LinkOption.NOFOLLOW_LINKS) || Files.isSymbolicLink(config)) {
                throw IllegalArgumentException("Safari context config destination already exists")
            }
            Files.createDirectory(config)
            for (root in SafariYarnLockRules.CONTEXT_ROOTS) {
                scan.checkDeadline(root)
                val directory = try {
                    SafariReporterHost.openDirectoryNoFollow(repository, Path.of(root))
                } catch (error: IOException) {
                    inventory.record(
                        root,
                        "skipped",
                        "missing_or_unsafe_root",
                        mapOf("error" to JsonPrimitive(error.message ?: "")),
                    )
                    continue
                }
                scan.visit(directory, root, root.split('/').size)
            }
            if (inventory.counter("copied_files") == 0L) {
                inventory.record("config", "failed", "no_karma_config")
            }
            for (root in SafariYarnLockRules.CONTEXT_ROOTS) {
                val requiredConfig = "$root/karma.conf.js"
                if (requiredConfig !in scan.copiedConfigs) {
                    inventory.record(requiredConfig, "failed", "missing_module_karma_config")
                }
            }
            val modes = LinkedHashSet<String>()
            val projects = listOf(
                "dyn4k-core" to SafariYarnLockRules.CONTEXT_ROOTS[0],
                "dyn4k" to SafariYarnLockRules.CONTEXT_ROOTS[1],
            )
            for ((project, root) in projects) {
                val requiredConfig = "$root/karma.conf.js"
                if (requiredConfig in scan.copiedConfigs) {
                    try {
                        modes.add(
                            SafariReporter.validateConfig(
                                Files.readAllBytes(config.resolve(requiredConfig)),
                                reporterSource,
                                repository.toString(),
                                project,
                            ),
                        )
                    } catch (error: ConfigBindingError) {
                        inventory.record(requiredConfig, "failed", error.message ?: "")
                    }
                }
            }
            if (modes.size > 1) {
                inventory.record("config", "failed", "karma_config_source_mismatch")
            } else if (modes.size == 1) {
                inventory.values["configuration"] = JsonPrimitive(modes.first())
            }
            SafariYarnLockHost.requireCandidate(repository, candidateSha)
        } catch (error: IOException) {
            inventory.record("config", "failed", "scan_failed", errorDetail(error))
        } catch (error: IllegalArgumentException) {
            inventory.record("config", "failed", "scan_failed", errorDetail(error))
        } catch (error: SafariContextTimeout) {
            inventory.record("config", "failed", "scan_failed", errorDetail(error))
        }

        var launches: List<String> = emptyList()
        try {
            if (Files.isSymbolicLink(rawContext)) {
                throw IllegalArgumentException("symlink Safari raw context")
            }
            val directory = openRawContext(rawContext)
            var names = scan.names(directory)
            if (names.size > bounds.rawEntries) {
                inventory.record("raw_context", "failed", "raw_entry_count_limit")
                names = names.take(bounds.rawEntries)
            }
            launches = names.filter { SafariContextRules.isLaunchName(it) }
            if (launches.size > bounds.launches) {
                inventory.record("launch", "failed", "launch_count_limit")
                launches = launches.take(bounds.launches)
            }
            if (launches.isEmpty()) {
                inventory.record("launch", "failed", "launcher_not_invoked")
            }
            val required = SafariContextRules.requiredSidecars(launches)
            for (name in SafariContextRules.unexpectedSidecars(names, required)) {
                inventory.record(name, "skipped", "unexpected_sidecar")
            }
            for (name in required) {
                scan.copySidecar(directory, name)
            }
            val hostOutcome = context.resolve("host-outcome.txt")
            if (!Files.isRegularFile(hostOutcome, LinkOption.NOFOLLOW_LINKS) ||
                !SafariContextRules.hostOutcomeComplete(
                    SafariContextRules.splitLines(readReplacing(hostOutcome)),
                )
            ) {
                inventory.record("host-outcome.txt", "failed", "host_capture_incomplete")
            }
            for (launch in launches) {
                val pid = SafariContextRules.launchPid(launch)
                val state = context.resolve("sample-state-$pid.txt")
                val process = context.resolve("process-$pid.txt")
                val outcome = context.resolve("launch-outcome-$pid.txt")
                val outcomeText = if (Files.isRegularFile(outcome, LinkOption.NOFOLLOW_LINKS)) {
                    readReplacing(outcome)
                } else {
                    ""
                }
                if (SafariContextRules.pendingOpen(outcomeText)) {
                    inventory.record(launch, "failed", "open_pending")
                }
                if (!Files.isRegularFile(state, LinkOption.NOFOLLOW_LINKS) ||
                    !Files.isRegularFile(process, LinkOption.NOFOLLOW_LINKS) ||
                    !Files.isRegularFile(outcome, LinkOption.NOFOLLOW_LINKS) ||
                    !SafariContextRules.samplesComplete(
                        SafariContextRules.splitLines(readReplacing(process)),
                    ) ||
                    !SafariContextRules.outcomeAccepted(outcomeText) ||
                    !SafariContextRules.samplerStateComplete(
                        SafariContextRules.splitLines(readReplacing(state)),
                    )
                ) {
                    inventory.record(launch, "failed", "sampler_incomplete")
                }
            }
            SafariYarnLockHost.requireCandidate(repository, candidateSha)
        } catch (error: IOException) {
            inventory.record("raw_context", "failed", "sidecar_scan_failed", errorDetail(error))
        } catch (error: IllegalArgumentException) {
            inventory.record("raw_context", "failed", "sidecar_scan_failed", errorDetail(error))
        } catch (error: SafariContextTimeout) {
            inventory.record("raw_context", "failed", "sidecar_scan_failed", errorDetail(error))
        }

        val elapsed = (System.nanoTime() - started) / 1_000_000_000.0
        inventory.values["elapsed_seconds"] = JsonPrimitive(elapsed)
        if (!inventory.incomplete) {
            inventory.values["status"] = JsonPrimitive(SafariContextRules.COMPLETE)
        }
        val encoded = inventory.encode()
        Files.write(context.resolve("inventory.json"), encoded.toByteArray(StandardCharsets.UTF_8))
        // The reference returns the dictionary it encoded; parsing the encoding back is the same
        // value for Python's round-tripping floats, and it makes the returned inventory exactly the
        // document on disk for every JSON number.
        return StrictJson.load(encoded) as JsonObject
    }

    private fun errorDetail(error: Exception): Map<String, JsonElement> =
        mapOf("error" to JsonPrimitive(error.message ?: ""))

    /** `os.open(path, O_RDONLY | O_DIRECTORY | O_NOFOLLOW)`: the last component is not followed. */
    private fun openRawContext(path: Path): Path {
        val parent = path.parent ?: Path.of("/")
        val name = path.fileName?.toString()
            ?: throw SafariFileError("[Errno 2] No such file or directory: '$path'")
        return SafariReporterHost.openDirectoryNoFollow(parent, Path.of(name))
    }

    /** `path.read_text(errors="replace")`. */
    private fun readReplacing(path: Path): String =
        String(Files.readAllBytes(path), StandardCharsets.UTF_8)

    /**
     * `Path.resolve()` on a JVM path: every existing component through its link, the rest joined
     * lexically. `pathlib` resolves as far as the path exists, and the containment guards compare
     * those resolved forms, so neither side may require the path to exist.
     */
    internal fun resolveLikePython(path: Path): Path = SafariReporterHost.resolvePath(path)

    /**
     * The bounded walk of `visit`, plus the sidecar copy of `copy_sidecar`.
     *
     * The inventory is the only mutable state the reference's nested functions share, so it is the
     * only mutable state here; [copiedConfigs] and the seen-file identities cross both module roots
     * exactly as the reference's closure variables do.
     */
    private class Scan(
        private val context: Path,
        private val bounds: SafariContextBounds,
        private val inventory: SafariContextInventory,
        private val started: Long,
        private val scanHook: ScanHook?,
    ) {
        val copiedConfigs: MutableSet<String> = LinkedHashSet()
        private val seenFiles = LinkedHashSet<Any>()
        private val config = context.resolve("config")
        private val deadline = started + bounds.seconds.toLong() * 1_000_000_000L

        fun checkDeadline(path: String) {
            if (System.nanoTime() >= deadline) {
                inventory.record(path, "failed", "traversal_deadline")
                throw SafariContextTimeout("Safari context traversal deadline")
            }
        }

        /** `os.scandir`: the enumeration seam, bounded to the names the caller asks for. */
        fun names(directory: Path): List<String> {
            scanHook?.beforeScan(directory, directory.toString())
            return Files.newDirectoryStream(directory).use { stream ->
                stream.map { it.fileName.toString() }
            }
        }

        private fun entries(directory: Path, relative: String): List<Path> {
            scanHook?.beforeScan(directory, relative)
            return Files.newDirectoryStream(directory).use { stream -> stream.toList() }
        }

        fun visit(directory: Path, relative: String, depth: Int) {
            checkDeadline(relative)
            for (entry in entries(directory, relative)) {
                val name = entry.fileName.toString()
                val path = "$relative/$name"
                inventory.add("entries_seen", 1)
                if (inventory.counter("entries_seen") > bounds.entries) {
                    inventory.record(path, "failed", "entry_count_limit")
                    throw IllegalArgumentException("Safari context entry count limit")
                }
                checkDeadline(path)
                if (name == "node_modules") {
                    inventory.record(path, "skipped", "excluded_node_modules")
                    continue
                }
                val attributes = Files.readAttributes(
                    entry,
                    BasicFileAttributes::class.java,
                    LinkOption.NOFOLLOW_LINKS,
                )
                if (attributes.isSymbolicLink) {
                    inventory.record(path, "skipped", "symlink")
                    continue
                }
                if (attributes.isDirectory) {
                    if (depth >= bounds.depth) {
                        inventory.record(path, "failed", "depth_limit")
                        throw IllegalArgumentException("Safari context depth limit")
                    }
                    visit(entry, path, depth + 1)
                    continue
                }
                if (!SafariContextRules.isKarmaConfigName(name)) continue
                inventory.add("matched_files", 1)
                if (inventory.counter("matched_files") > bounds.files) {
                    inventory.record(path, "failed", "file_count_limit")
                    throw IllegalArgumentException("Safari context file count limit")
                }
                copyConfig(entry, path)
            }
        }

        private fun copyConfig(source: Path, relative: String) {
            checkDeadline(relative)
            val before = Files.readAttributes(
                source,
                BasicFileAttributes::class.java,
                LinkOption.NOFOLLOW_LINKS,
            )
            if (!before.isRegularFile) {
                inventory.record(relative, "skipped", "non_regular")
                return
            }
            val identity = inodeOf(source, before)
            if (identity in seenFiles) {
                inventory.record(relative, "skipped", "duplicate_inode")
                return
            }
            seenFiles.add(identity)
            val remaining = inventory.fileRemaining()
            if (remaining <= 0) {
                inventory.record(
                    relative,
                    "skipped",
                    "total_byte_limit",
                    mapOf(
                        "original_size" to JsonPrimitive(before.size()),
                        "retained_size" to JsonPrimitive(0),
                    ),
                )
                return
            }
            val limit = minOf(before.size(), bounds.fileBytes.toLong(), remaining)
            val data = readBounded(source, limit, relative)
            val after = Files.readAttributes(
                source,
                BasicFileAttributes::class.java,
                LinkOption.NOFOLLOW_LINKS,
            )
            if (data.size.toLong() != limit || identityOf(source, before) != identityOf(source, after)) {
                inventory.record(relative, "failed", "source_changed_during_copy")
                return
            }
            writeExclusive(config.resolve(relative), data)
            inventory.add("copied_files", 1)
            inventory.add("copied_bytes", data.size.toLong())
            inventory.add("upload_data_bytes", data.size.toLong())
            val status = SafariContextRules.copyStatus(data.size.toLong(), before.size())
            val reason = SafariContextRules.copyReason(
                status,
                bounds.fileBytes.toLong() <= remaining,
            )
            if (status == "copied") copiedConfigs.add(relative)
            inventory.record(
                relative,
                status,
                reason,
                mapOf(
                    "original_size" to JsonPrimitive(before.size()),
                    "retained_size" to JsonPrimitive(data.size.toLong()),
                    "sha256" to JsonPrimitive(Sha256.of(data)),
                ),
            )
        }

        fun copySidecar(directory: Path, name: String) {
            checkDeadline(name)
            val source = directory.resolve(name)
            val before = try {
                Files.readAttributes(
                    source,
                    BasicFileAttributes::class.java,
                    LinkOption.NOFOLLOW_LINKS,
                )
            } catch (error: IOException) {
                inventory.record(
                    name,
                    "failed",
                    "missing_or_unreadable_sidecar",
                    mapOf(
                        "original_size" to kotlinx.serialization.json.JsonNull,
                        "retained_size" to JsonPrimitive(0),
                        "error" to JsonPrimitive(error.message ?: ""),
                    ),
                )
                return
            }
            if (!before.isRegularFile) {
                inventory.record(
                    name,
                    "failed",
                    "non_regular_sidecar",
                    mapOf(
                        "original_size" to JsonPrimitive(before.size()),
                        "retained_size" to JsonPrimitive(0),
                    ),
                )
                return
            }
            val identity = inodeOf(source, before)
            if (identity in seenFiles) {
                inventory.record(
                    name,
                    "failed",
                    "duplicate_sidecar_inode",
                    mapOf(
                        "original_size" to JsonPrimitive(before.size()),
                        "retained_size" to JsonPrimitive(0),
                    ),
                )
                return
            }
            seenFiles.add(identity)
            val remaining = maxOf(0L, inventory.uploadRemaining())
            val limit = minOf(before.size(), bounds.fileBytes.toLong(), remaining)
            val data = try {
                readBounded(source, limit, name)
            } catch (error: IOException) {
                inventory.record(
                    name,
                    "failed",
                    "sidecar_copy_failed",
                    mapOf(
                        "original_size" to JsonPrimitive(before.size()),
                        "retained_size" to JsonPrimitive(0),
                        "error" to JsonPrimitive(error.message ?: ""),
                    ),
                )
                return
            }
            val after = try {
                Files.readAttributes(
                    source,
                    BasicFileAttributes::class.java,
                    LinkOption.NOFOLLOW_LINKS,
                )
            } catch (error: IOException) {
                inventory.record(
                    name,
                    "failed",
                    "sidecar_copy_failed",
                    mapOf(
                        "original_size" to JsonPrimitive(before.size()),
                        "retained_size" to JsonPrimitive(0),
                        "error" to JsonPrimitive(error.message ?: ""),
                    ),
                )
                return
            }
            if (data.size.toLong() != limit || identityOf(source, before) != identityOf(source, after)) {
                inventory.record(
                    name,
                    "failed",
                    "sidecar_changed_during_copy",
                    mapOf(
                        "original_size" to JsonPrimitive(before.size()),
                        "retained_size" to JsonPrimitive(0),
                    ),
                )
                return
            }
            writeExclusive(context.resolve(name), data)
            inventory.add("upload_data_bytes", data.size.toLong())
            val status = SafariContextRules.copyStatus(data.size.toLong(), before.size())
            val reason = SafariContextRules.sidecarReason(
                status,
                bounds.fileBytes.toLong() <= remaining,
            )
            inventory.record(
                name,
                status,
                reason,
                mapOf(
                    "original_size" to JsonPrimitive(before.size()),
                    "retained_size" to JsonPrimitive(data.size.toLong()),
                    "sha256" to JsonPrimitive(Sha256.of(data)),
                ),
            )
        }

        /**
         * The `(st_dev, st_ino)` pair the reference keys its duplicate detection on. The JVM's
         * `fileKey` is that pair on Unix; a filesystem without one keys on the path instead.
         */
        private fun inodeOf(path: Path, attributes: BasicFileAttributes): Any =
            attributes.fileKey() ?: path.toAbsolutePath().normalize()

        /** `(dev, ino, size, mtime_ns)`: what a copy must leave unchanged. */
        private fun identityOf(path: Path, attributes: BasicFileAttributes): Any =
            listOf(
                inodeOf(path, attributes),
                attributes.size(),
                attributes.lastModifiedTime().to(TimeUnit.NANOSECONDS),
            )

        private fun readBounded(source: Path, limit: Long, relative: String): ByteArray {
            val out = ByteArrayOutputStream()
            Files.newInputStream(source, LinkOption.NOFOLLOW_LINKS).use { stream ->
                val buffer = ByteArray(SafariContextRules.CHUNK_BYTES)
                var size = 0L
                while (size < limit) {
                    checkDeadline(relative)
                    val wanted = minOf(buffer.size.toLong(), limit - size).toInt()
                    val read = stream.read(buffer, 0, wanted)
                    if (read <= 0) break
                    out.write(buffer, 0, read)
                    size += read
                }
            }
            return out.toByteArray()
        }

        private fun writeExclusive(destination: Path, data: ByteArray) {
            destination.parent?.let { Files.createDirectories(it) }
            Files.newOutputStream(
                destination,
                StandardOpenOption.CREATE_NEW,
                StandardOpenOption.WRITE,
                LinkOption.NOFOLLOW_LINKS,
            ).use { it.write(data) }
        }
    }
}
