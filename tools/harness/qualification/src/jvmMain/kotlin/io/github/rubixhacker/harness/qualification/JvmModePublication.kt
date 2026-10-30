package io.github.rubixhacker.harness.qualification

import io.github.rubixhacker.harness.contract.MatrixCase
import io.github.rubixhacker.harness.contract.Qualification
import io.github.rubixhacker.harness.contract.Sha256
import io.github.rubixhacker.harness.contract.StrictJson
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.Path
import java.util.concurrent.TimeUnit
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/** The digest `independent_gates.archive_digest` records for a raw gate archive. */
fun interface ArchiveDigest {
    fun digest(archive: Path): String
}

/**
 * Archive digest over a stable directory tree.
 *
 * The value is the one `independent_gates.archive_digest` records: the canonical digest of
 * `[{path, sha256, mtime_ns}]` over every file, sorted by path. The reference also re-verifies
 * directory and file identities around each read to detect a concurrent writer; that
 * race-detection layer is not ported here and is listed as remaining work.
 */
object StableTreeDigest : ArchiveDigest {
    override fun digest(archive: Path): String {
        if (!archive.isAbsolute || ".." in archive.toString().split('/') || !Files.isDirectory(archive)) {
            throw IllegalArgumentException("archive path is absent or relative: $archive")
        }
        val files = mutableListOf<Path>()
        Files.walk(archive).use { stream ->
            for (path in stream) {
                if (path == archive) continue
                if (Files.isSymbolicLink(path)) {
                    throw IllegalArgumentException("archive entry is not a regular file: $path")
                }
                if (Files.isRegularFile(path)) files.add(path)
            }
        }
        val records = files.map { path ->
            JsonObject(
                linkedMapOf(
                    "path" to JsonPrimitive(archive.relativize(path).toString().replace('\\', '/')),
                    "sha256" to JsonPrimitive(Fs.digest(path)),
                    "mtime_ns" to JsonPrimitive(
                        Files.getLastModifiedTime(path).to(TimeUnit.NANOSECONDS),
                    ),
                ),
            )
        }.sortedWith { left, right ->
            CanonicalText.compare(
                (left["path"] as JsonPrimitive).content,
                (right["path"] as JsonPrimitive).content,
            )
        }
        if (records.none { (it["path"] as JsonPrimitive).content == "receipt.json" }) {
            throw IllegalArgumentException("raw receipt is absent")
        }
        return Sha256.ofCanonical(JsonArray(records))
    }
}

/** Runs the public compiler-mode replay that proves both JVM modes publish separate JARs. */
fun interface ModeReplay {
    /** Throws when the replay cannot run. The returned report carries the replay verdict. */
    fun replay(source: Path, archive: Path, candidateSha: String, mode: String): JsonElement
}

/**
 * The Python `compiler_modes.replay` entry point, invoked exactly as the reference invokes it.
 *
 * `compiler_modes.py` is not yet ported, so the replay stays a subprocess seam. Everything the
 * qualification audit does with its result is ported.
 */
class PythonModeReplay(
    private val toolsDirectory: Path,
    private val pythonExecutable: String = "python3",
) : ModeReplay {
    private val script =
        "import json,sys;from pathlib import Path;" +
            "sys.path.insert(0,sys.argv[1]);import compiler_modes,full_corpus;" +
            "compiler_modes.ROOT=Path(sys.argv[2]);" +
            "compiler_modes.MANIFEST=compiler_modes.ROOT/full_corpus.MANIFEST_PATH;" +
            "print(json.dumps(compiler_modes.replay(Path(sys.argv[3]),sys.argv[4],'jvm',sys.argv[5])))"

    override fun replay(source: Path, archive: Path, candidateSha: String, mode: String): JsonElement {
        val command = listOf(
            pythonExecutable, "-c", script, toolsDirectory.toString(), source.toString(),
            archive.toString(), candidateSha, mode,
        )
        val process = ProcessBuilder(command)
            .directory(source.toFile())
            .redirectErrorStream(false)
            .start()
        val stdout = process.inputStream.use { it.readBytes() }
        process.errorStream.close()
        process.waitFor(300, TimeUnit.SECONDS)
        if (process.isAlive) {
            process.destroyForcibly()
            throw IllegalArgumentException("JVM mode publication public replay did not run")
        }
        if (process.exitValue() != 0 || stdout.isEmpty()) {
            throw IllegalArgumentException("JVM mode publication public replay did not run")
        }
        return StrictJson.load(String(stdout, StandardCharsets.UTF_8))
    }
}

/**
 * `qualify.verify_jvm_mode_publication`.
 *
 * The binding must name the selected lane and mode, the archive must still digest to the
 * recorded value, the receipt must bind every log to that archive, both JARs must hash to the
 * bound pair, and the public replay must report the same candidate, target, and mode.
 */
class JvmModePublication(
    private val archiveDigest: ArchiveDigest,
    private val replay: ModeReplay,
) : JvmModeVerifier {
    private val requiredFields = setOf(
        "candidate_sha", "lane", "mode", "source", "source_checkout",
        "publication_archive", "archive_digest", "artifact_hashes",
    )

    override fun verify(
        binding: JsonElement?,
        case: MatrixCase,
        candidateSha: String?,
        expectedHashes: Map<String, String?>,
    ) {
        val data = binding as? JsonObject
        if (data == null || data.keys != requiredFields) {
            throw IllegalArgumentException("JVM mode publication identity is incomplete")
        }
        val boundHashes = data["artifact_hashes"] as? JsonObject
        if (Py.str(data["candidate_sha"]) != candidateSha ||
            Py.str(data["lane"]) != case.id ||
            Py.str(data["mode"]) != case.configuration ||
            Py.str(data["source"]) != "compiler_modes.replay" ||
            boundHashes == null ||
            boundHashes.keys != expectedHashes.keys ||
            expectedHashes.any { (module, value) -> Py.str(boundHashes[module]) != value }
        ) {
            throw IllegalArgumentException("JVM mode publication candidate, lane, mode, source, or pair differs")
        }
        if (!Py.SHA40.matches(candidateSha ?: "") ||
            !Py.SHA64.matches(Py.str(data["archive_digest"]) ?: "") ||
            expectedHashes.keys != Qualification.modules.toSet() ||
            expectedHashes.values.any { !Py.SHA64.matches(it ?: "") }
        ) {
            throw IllegalArgumentException("JVM mode publication digest or pair is invalid")
        }

        val source = Path.of(Py.str(data["source_checkout"]) ?: "")
        val archive = Path.of(Py.str(data["publication_archive"]) ?: "")
        if (!source.isAbsolute || Files.isSymbolicLink(source) || !Files.isDirectory(source) ||
            !archive.isAbsolute || Files.isSymbolicLink(archive) || !Files.isDirectory(archive)
        ) {
            throw IllegalArgumentException("JVM mode publication source or archive is not a regular directory")
        }
        if (archiveDigest.digest(archive) != Py.str(data["archive_digest"])) {
            throw IllegalArgumentException("JVM mode publication archive digest differs")
        }

        val receipt = StrictJson.load(Fs.readText(archive.resolve("receipt.json"))) as? JsonObject
            ?: throw IllegalArgumentException("JVM mode publication receipt identity differs")
        if (Py.str(receipt["candidate_sha"]) != candidateSha ||
            Py.str(receipt["target"]) != "jvm" ||
            Py.str(receipt["mode"]) != case.configuration
        ) {
            throw IllegalArgumentException("JVM mode publication receipt identity differs")
        }
        checkLogs(receipt, archive)

        val artifacts = receipt["artifacts"] as? JsonObject
        if (artifacts == null || artifacts.keys != Qualification.modules.toSet()) {
            throw IllegalArgumentException("JVM mode publication pair is incomplete")
        }
        for (module in Qualification.modules) {
            val item = artifacts[module] as? JsonObject
            val relative = Path.of(Py.str(item?.get("path")) ?: "")
            val expectedPath = Path.of("staged").resolve(Qualification.targetBinaryPath(module, "jvm"))
            val jar = archive.resolve(relative)
            if (relative != expectedPath ||
                Py.str(item?.get("sha256")) != expectedHashes[module] ||
                Files.isSymbolicLink(jar) ||
                !Files.isRegularFile(jar) ||
                Fs.digest(jar) != expectedHashes[module]
            ) {
                throw IllegalArgumentException("JVM mode publication $module JAR differs")
            }
        }

        val replayed = replay.replay(source, archive, candidateSha!!, case.configuration)
        val report = replayed as? JsonObject
        if (report == null ||
            Py.str(report["status"]) != "PASSED" ||
            Py.str(report["candidate_sha"]) != candidateSha ||
            Py.str(report["target"]) != "jvm" ||
            Py.str(report["mode"]) != case.configuration
        ) {
            throw IllegalArgumentException("JVM mode publication public replay is unpassed")
        }
    }

    private fun checkLogs(value: JsonElement?, archive: Path) {
        when (value) {
            is JsonObject -> for ((key, item) in value) {
                if (key == "log") {
                    val path = Path.of(Py.str(item) ?: "")
                    if (!path.isAbsolute ||
                        !path.startsWith(archive) ||
                        Files.isSymbolicLink(path) ||
                        !Files.isRegularFile(path)
                    ) {
                        throw IllegalArgumentException("JVM mode publication log escapes selected archive")
                    }
                } else {
                    checkLogs(item, archive)
                }
            }
            is JsonArray -> for (item in value) checkLogs(item, archive)
            else -> Unit
        }
    }
}
