package io.github.rubixhacker.harness.qualification

import java.nio.file.Files
import java.nio.file.LinkOption
import java.nio.file.Path
import java.nio.file.StandardCopyOption
import io.github.rubixhacker.harness.contract.StrictJson
import java.util.concurrent.TimeUnit
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import org.apache.commons.compress.archivers.tar.TarArchiveEntry
import org.apache.commons.compress.archivers.tar.TarArchiveInputStream
import org.apache.commons.compress.archivers.tar.TarArchiveOutputStream

/**
 * `full_hosted.py`, first slice: the pinned toolchain, archive paths, the receipt inventory, and
 * the PAX transport archive.
 *
 * `verify_transport_archive` stops at `verify_raw_files`, the receipt verifier that is still
 * Python; everything before it (extraction, PAX timestamps, sizes, receipt identity) is ported.
 */
object FullHosted {
    const val PINNED_GRADLE = "9.5.0"
    const val PINNED_KGP = "2.4.20"
    const val PINNED_AGP = "9.3.1"

    const val MANIFEST = "tools/qualification/full-common-corpus.json"
    const val MAPPING = "tools/qualification/full-common-original-map.tsv"
    const val PAIRS = "tools/qualification/full-common-reviewed-pairs.tsv"

    val REVIEWED_COMMON_COUNTS = linkedMapOf("dyn4k-core" to 2465, "dyn4k" to 58)

    val SAFARI_DIAGNOSTIC_CASES = linkedMapOf(
        "capsuleSlice" to ("CapsuleSlice" to "gjk"),
        "circlePolygon" to ("CirclePolygon" to "gjk"),
        "circleSegment" to ("CircleSegment" to "gjk"),
        "circleSlice" to ("CircleSlice" to "gjk"),
        "polygonCapsule" to ("PolygonCapsule" to "sat"),
        "polygonPolygon" to ("PolygonPolygon" to "sat"),
    )

    val SAFARI_DIAGNOSTIC_CLASS =
        "org.dyn4j.collision.narrowphase.WindowsCollisionIntermediateDiagnosticTest"

    /** `require_pinned_toolchain`: Java 21 plus the pinned Gradle, KGP, and AGP declarations. */
    fun requirePinnedToolchain(runtime: JsonObject?) {
        val javaVersion = Py.str(runtime?.get("java_version")) ?: ""
        if (runtime == null || !Regex("21(?:\\.\\d+)+(?:\\+\\d+)?").matches(javaVersion) ||
            Py.str(runtime["gradle_version"]) != PINNED_GRADLE ||
            Py.str(runtime["kgp_declared_version"]) != PINNED_KGP ||
            Py.str(runtime["agp_declared_version"]) != PINNED_AGP
        ) {
            throw IllegalArgumentException(
                "hosted toolchain differs from pinned Java, Gradle, KGP, or AGP",
            )
        }
    }

    /** `declared_plugin_version`: the captured group of one plugin declaration. */
    fun declaredPluginVersion(build: String, pattern: Regex): String =
        pattern.find(build)?.groupValues?.get(1) ?: ""

    /** `relative_path`: one archive member name that cannot escape the archive. */
    fun relativePath(value: String?): Path {
        if (value.isNullOrEmpty() || "\\" in value) {
            throw IllegalArgumentException("unsafe archive path")
        }
        val parsed = Path.of(value)
        if (parsed.isAbsolute || value.split('/').any { it in setOf("", ".", "..") } ||
            ":" in value.split('/').first()
        ) {
            throw IllegalArgumentException("unsafe archive path")
        }
        return parsed
    }

    /** `original_path`: an absolute host path, POSIX except for `mingwX64`. */
    fun originalPath(target: String, value: String?): String {
        val text = value ?: ""
        if (target == "mingwX64") {
            val drive = Regex("^[A-Za-z]:[\\\\/]").containsMatchIn(text)
            val unc = text.startsWith("\\\\")
            if (!drive && !unc) throw IllegalArgumentException("original path is not absolute or safe")
            if (".." in text.split('\\', '/')) {
                throw IllegalArgumentException("original path is not absolute or safe")
            }
            return text
        }
        if (!text.startsWith("/") || ".." in text.split('/')) {
            throw IllegalArgumentException("original path is not absolute or safe")
        }
        return text
    }

    /** `expected_gradle_home`: the Gradle user home the run must have used. */
    fun expectedGradleHome(target: String, receipt: JsonObject): String {
        val runnerHome = Py.str(receipt["runner_home"])
        if (runnerHome.isNullOrEmpty()) {
            throw IllegalArgumentException("Gradle user home runner anchor is absent")
        }
        val home = originalPath(target, runnerHome)
        if ("gradle_user_home_override" !in receipt) {
            throw IllegalArgumentException("Gradle user home environment anchor is absent")
        }
        val override = receipt["gradle_user_home_override"]
        if (override is kotlinx.serialization.json.JsonNull) return "$home/.gradle"
        val text = Py.str(override)
        if (text.isNullOrEmpty()) throw IllegalArgumentException("Gradle user home override is invalid")
        val absolute = if (target == "mingwX64") {
            Regex("^[A-Za-z]:[\\\\/]").containsMatchIn(text) || text.startsWith("\\\\")
        } else {
            text.startsWith("/")
        }
        if (absolute) return originalPath(target, text)
        if ((target == "mingwX64" && (Regex("^[A-Za-z]:").containsMatchIn(text))) ||
            (target != "mingwX64" && text.startsWith("/"))
        ) {
            throw IllegalArgumentException("Gradle user home override is not a relative path")
        }
        val processRoot = originalPath(target, Py.str(receipt["repository_root"]))
        val separator = if (target == "mingwX64") '\\' else '/'
        return originalPath(target, normalize("$processRoot$separator$text", separator))
    }

    /** `posixpath.normpath` / `ntpath.normpath` for the two host kinds. */
    private fun normalize(path: String, separator: Char): String {
        val absolute = path.startsWith(separator.toString())
        val parts = path.split(separator)
        val prefix = if (absolute) listOf("") else emptyList()
        val kept = mutableListOf<String>()
        for (part in parts) {
            when (part) {
                "", "." -> Unit
                ".." -> if (kept.isNotEmpty() && kept.last() != "..") kept.removeAt(kept.size - 1)
                else if (!absolute) kept.add("..")
                else -> kept.add(part)
            }
        }
        val joined = (prefix + kept).joinToString(separator.toString())
        return joined.ifEmpty { if (absolute) separator.toString() else "." }
    }

    /** `archived_file`: one regular, unlinked member inside the archive root. */
    fun archivedFile(output: Path, name: String?): Path {
        val relative = relativePath(name)
        val path = relative.fold(output) { base, part -> base.resolve(part) }
        if (!Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS) || Files.isSymbolicLink(path) ||
            !path.toAbsolutePath().normalize().startsWith(output.toAbsolutePath().normalize())
        ) {
            throw IllegalArgumentException("missing or unsafe archive file: $name")
        }
        return path
    }

    /** `archive_copy`: copy one source into the archive and record its receipt entry. */
    fun archiveCopy(source: Path, output: Path, name: String): JsonObject {
        if (!Files.isRegularFile(source) || Files.isSymbolicLink(source)) {
            throw IllegalArgumentException("missing source for archive: $source")
        }
        val destination = relativePath(name).fold(output) { base, part -> base.resolve(part) }
        destination.parent?.let { Files.createDirectories(it) }
        Files.copy(source, destination, StandardCopyOption.COPY_ATTRIBUTES, StandardCopyOption.REPLACE_EXISTING)
        return receiptEntry(name, destination)
    }

    /** `archive_inventory`: every archive file except the receipt, sorted by path. */
    fun archiveInventory(output: Path): List<JsonObject> {
        val entries = Files.walk(output).use { stream -> stream.toList() }
            .sortedWith { left, right -> CanonicalText.compare(left.toString(), right.toString()) }
        val files = mutableListOf<JsonObject>()
        for (path in entries) {
            if (Files.isSymbolicLink(path)) throw IllegalArgumentException("symbolic archive member")
            if (!Files.isRegularFile(path)) continue
            val name = output.relativize(path).toString().replace('\\', '/')
            if (name == "receipt.json") continue
            files.add(receiptEntry(name, path))
        }
        return files
    }

    private fun receiptEntry(name: String, path: Path): JsonObject = kotlinx.serialization.json.buildJsonObject {
        put("path", JsonPrimitive(name))
        put("sha256", JsonPrimitive(CorpusFiles.digest(path)))
        put("size", JsonPrimitive(Files.size(path)))
        put("modified_ns", JsonPrimitive(Files.getLastModifiedTime(path).to(TimeUnit.NANOSECONDS)))
    }

    /** `verify_inventory`: every listed member matches its receipt, and nothing is unlisted. */
    fun verifyInventory(output: Path, files: JsonArray?) {
        if (files == null) throw IllegalArgumentException("archive inventory is missing")
        val names = files.map { element ->
            (element as? JsonObject)?.let { item -> Py.str(item["path"]) }
                ?: throw IllegalArgumentException("archive inventory is missing")
        }
        if (names.size != names.toSet().size) throw IllegalArgumentException("duplicate archive path")
        for (element in files) {
            val item = element as JsonObject
            val path = archivedFile(output, Py.str(item["path"]))
            if (CorpusFiles.digest(path) != Py.str(item["sha256"]) ||
                Files.size(path) != Py.int(item["size"] ?: JsonPrimitive(0)) ||
                Files.getLastModifiedTime(path).to(TimeUnit.NANOSECONDS) !=
                Py.int(item["modified_ns"] ?: JsonPrimitive(0))
            ) {
                throw IllegalArgumentException("archive member differs: ${Py.str(item["path"])}")
            }
        }
        val actual = archiveInventory(output).mapNotNull { Py.str(it["path"]) }.toSet()
        if (actual != names.filterNotNull().toSet()) {
            throw IllegalArgumentException("unlisted or missing archive member")
        }
    }

    /** `package_archive`: write the archive as PAX with nanosecond timestamps. */
    fun packageArchive(output: Path, archive: Path) {
        if (!Files.isRegularFile(output.resolve("receipt.json")) ||
            archive.toAbsolutePath().normalize()
                .startsWith(output.toAbsolutePath().normalize())
        ) {
            throw IllegalArgumentException("full receipt or external archive destination is absent")
        }
        archive.parent?.let { Files.createDirectories(it) }
        Files.newOutputStream(archive).use { stream ->
            TarArchiveOutputStream(stream).use { packed ->
                packed.setLongFileMode(TarArchiveOutputStream.LONGFILE_POSIX)
                packed.setBigNumberMode(TarArchiveOutputStream.BIGNUMBER_POSIX)
                val entries = Files.walk(output).use { walk -> walk.toList() }
                    .sortedWith { left, right -> CanonicalText.compare(left.toString(), right.toString()) }
                for (path in entries) {
                    if (Files.isSymbolicLink(path)) {
                        throw IllegalArgumentException("symbolic archive member")
                    }
                    if (!Files.isRegularFile(path)) continue
                    val name = output.relativize(path).toString().replace('\\', '/')
                    relativePath(name)
                    val entry = TarArchiveEntry(path.toFile(), name)
                    entry.addPaxHeader(
                        "dyn4k.mtime_ns",
                        Files.getLastModifiedTime(path).to(TimeUnit.NANOSECONDS).toString(),
                    )
                    packed.putArchiveEntry(entry)
                    Files.newInputStream(path).use { input -> input.copyTo(packed) }
                    packed.closeArchiveEntry()
                }
            }
        }
    }

    /**
     * `verify_transport_archive`: extract, check every PAX timestamp and size, then verify the
     * receipt. The receipt verifier (`verify_raw_files`) is still Python, so the function stops
     * there rather than returning an unverified receipt.
     */
    fun verifyTransportArchive(
        archive: Path,
        candidateSha: String,
        target: String? = null,
        candidateRepository: Path? = null,
    ): JsonObject {
        val temporary = Files.createTempDirectory("full-hosted-transport")
        try {
            val names = mutableSetOf<String>()
            Files.newInputStream(archive).use { stream ->
                TarArchiveInputStream(stream).use { packed ->
                    while (true) {
                        val member = packed.nextEntry ?: break
                        val name = member.name
                        relativePath(name)
                        if (!names.add(name)) {
                            throw IllegalArgumentException("duplicate transport archive path")
                        }
                        if (!member.isFile) {
                            throw IllegalArgumentException("non-file transport archive member")
                        }
                        val value: String = member.extraPaxHeaders["dyn4k.mtime_ns"] ?: ""
                        if (!Regex("[0-9]+").matches(value)) {
                            throw IllegalArgumentException("transport archive file timestamp is absent")
                        }
                        val mtime = member.modTime.time / 1000.0
                        if (!mtime.isFinite() || mtime.toLong() != value.toLong() / 1_000_000_000L) {
                            throw IllegalArgumentException("transport archive PAX timestamp differs")
                        }
                        val destination = relativePath(name).fold(temporary) { base, part -> base.resolve(part) }
                        destination.parent?.let { Files.createDirectories(it) }
                        val copied = packed.readBytes()
                        Files.write(destination, copied)
                        if (Files.size(destination) != member.size) {
                            throw IllegalArgumentException("transport archive file size differs")
                        }
                        Files.setLastModifiedTime(
                            destination,
                            java.nio.file.attribute.FileTime.from(value.toLong(), TimeUnit.NANOSECONDS),
                        )
                    }
                }
            }
            if ("receipt.json" !in names) {
                throw IllegalArgumentException("transport archive receipt is absent")
            }
            val receipt = StrictJson.load(Fs.readText(temporary.resolve("receipt.json"))) as? JsonObject
                ?: throw IllegalArgumentException("full hosted receipt must be an object")
            if (Py.str(receipt["candidate_sha"]) != candidateSha ||
                (target != null && Py.str(receipt["target"]) != target)
            ) {
                throw IllegalArgumentException("transport archive candidate or target differs")
            }
            return verifyRawFiles(temporary, receipt, candidateRepository)
        } finally {
            Files.walk(temporary).use { walk ->
                walk.sorted(Comparator.reverseOrder()).forEach { Files.deleteIfExists(it) }
            }
        }
    }

    /** `verify_raw_files`: the receipt verifier, not yet ported. */
    fun verifyRawFiles(
        output: Path,
        receipt: JsonObject,
        candidateRepository: Path? = null,
    ): JsonObject {
        if (!Files.isDirectory(output)) {
            throw IllegalArgumentException("full hosted receipt directory is absent")
        }
        // The receipt verifier (`verify_raw_files`, ~300 lines) is still Python. Stopping here
        // keeps a partial verification from being reported as a pass.
        throw AnalyzerNotPorted("full_hosted.verify_raw_files")
    }

    /** `sha256`. */
    fun sha256(path: Path): String = CorpusFiles.digest(path)

    /** `canonical_hash`. */
    fun canonicalHash(value: kotlinx.serialization.json.JsonElement): String =
        FullCorpus.canonicalDigest(value)

    /** `committed_input`: the working bytes must equal the committed bytes. */
    fun committedInput(repository: Path, candidateSha: String, relative: String): ByteArray {
        val path = repository.resolve(relative)
        val raw = CorpusFiles.committedBytes(repository, candidateSha, relative)
        if (!Files.readAllBytes(path).contentEquals(raw)) {
            throw IllegalArgumentException("candidate source differs: $relative")
        }
        return raw
    }

    /** `expected_cases`: the reviewed common cases of one module. */
    fun expectedCases(manifest: JsonObject, module: String): Set<Pair<String, String>> {
        val required = REVIEWED_COMMON_COUNTS[module]
            ?: throw IllegalArgumentException("unknown common corpus module: $module")
        val cases = (manifest["cases"] as JsonArray).mapNotNull { it as? JsonObject }
            .filter { Py.str(it["module"]) == module && Py.str(it["source_set"]) == "commonTest" }
            .map { (Py.str(it["classname"]) ?: "") to (Py.str(it["method"]) ?: "") }
        if (cases.isEmpty() || cases.toSet().size != cases.size) {
            throw IllegalArgumentException("empty or duplicate common cases: $module")
        }
        if (cases.size != required) {
            throw IllegalArgumentException("reviewed common corpus count differs: $module")
        }
        return cases.toSet()
    }

    /** `safari_diagnostic_identities`: the 72 reviewed diagnostic steps. */
    fun safariDiagnosticIdentities(): Set<List<Any>> {
        val expected = mutableSetOf<List<Any>>()
        for ((fixture, detector) in SAFARI_DIAGNOSTIC_CASES.values) {
            for (step in 0 until 12) {
                val phase = if (step in setOf(0, 1, 4, 5, 6, 7)) "center" else "shifted"
                val order = if (step % 2 == 0) "forward" else "reverse"
                val method = if (step < 4) {
                    if (detector == "gjk") "detectGjk" else "detectSat"
                } else {
                    "getClipManifold"
                }
                val algorithm = if (step < 4) detector else if (step % 4 < 2) "gjk" else "sat"
                expected.add(listOf(fixture, method, phase, order, step, algorithm))
            }
        }
        return expected
    }
}
