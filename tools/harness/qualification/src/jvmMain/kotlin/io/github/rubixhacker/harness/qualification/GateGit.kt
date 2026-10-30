package io.github.rubixhacker.harness.qualification

import java.io.IOException
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.Path

/** Thrown when Git cannot read the object the reference expects to be present. */
internal class GitObjectMissing(message: String) : Exception(message)

/**
 * The Git and checkout primitives the prospective gates read their blobs through.
 *
 * The reference proves each binding by re-reading the same blob from two places — the checkout it
 * runs from and the candidate commit — so the port keeps both reads behind one seam. The seam is
 * what lets the recorded drift cases re-run an altered blob or an absent object without touching
 * the checkout, exactly as the reference patches `Path.read_bytes` and `subprocess.check_output`.
 */
open class GateSource {
    /** `subprocess.check_output([... "show", f"{revision}:{path}"])`. */
    open fun show(repository: Path, revision: String, path: String): ByteArray {
        val process = ProcessBuilder(
            "git", "--no-replace-objects", "-C", repository.toString(), "show", "$revision:$path",
        ).start()
        val output = process.inputStream.use { it.readBytes() }
        process.errorStream.close()
        if (process.waitFor() != 0) {
            throw GitObjectMissing("committed input is unavailable: $path")
        }
        return output
    }

    /** `Path.read_bytes`. */
    open fun read(path: Path): ByteArray = Files.readAllBytes(path)

    /** `descends_from(revision)`: is `revision` an ancestor of `candidateSha`? */
    open fun descendsFrom(
        repository: Path,
        revision: String,
        candidateSha: String,
        message: String,
    ): Boolean {
        val checked = ProcessBuilder(
            "git", "--no-replace-objects", "-C", repository.toString(),
            "merge-base", "--is-ancestor", revision, candidateSha,
        ).start()
        checked.errorStream.close()
        val status = checked.waitFor()
        if (status != 0 && status != 1) throw IllegalArgumentException(message)
        return status == 0
    }

    /**
     * `Path(__file__).resolve().parents[2]`: the checkout this verifier runs from.
     *
     * The reference anchors the local half of every binding on the file that contains it, so the
     * port anchors the same way: the directory that holds the tracked qualification sources.
     */
    open fun sourceRoot(): Path {
        var current: Path? = Path.of("").toAbsolutePath()
        while (current != null) {
            if (Files.isRegularFile(
                    current.resolve("tools/qualification/full-suite-manifest.json"),
                )
            ) {
                return try {
                    current.toRealPath()
                } catch (error: IOException) {
                    current
                }
            }
            current = current.parent
        }
        throw IllegalStateException(
            "the checkout holding tools/qualification is not reachable from the working directory",
        )
    }

    /** The digest of one local blob, or the reference's diagnosis when it is unreadable. */
    fun localBlob(relative: String, message: String): String = try {
        CorpusFiles.digest(read(sourceRoot().resolve(relative)))
    } catch (error: IOException) {
        throw IllegalArgumentException("$message: $relative")
    }

    /** The digest of one committed blob, or the reference's diagnosis when Git lacks it. */
    fun committedBlob(
        repository: Path,
        candidateSha: String,
        relative: String,
        message: String,
    ): String {
        val bytes = try {
            show(repository, candidateSha, relative)
        } catch (error: GitObjectMissing) {
            throw IllegalArgumentException("$message: $relative")
        }
        return CorpusFiles.digest(bytes)
    }

    /** The UTF-8 text of one committed blob. */
    fun committedText(repository: Path, revision: String, path: String): String =
        show(repository, revision, path).toString(StandardCharsets.UTF_8)

    /** `hashlib.sha256(committed).hexdigest()` of one committed blob. */
    fun committedDigest(repository: Path, revision: String, path: String): String =
        CorpusFiles.digest(show(repository, revision, path))
}

/** The system seam: Git of the running checkout and the checkout's own files. */
object GateGit : GateSource()
