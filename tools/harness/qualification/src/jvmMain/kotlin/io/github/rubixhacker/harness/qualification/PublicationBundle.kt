package io.github.rubixhacker.harness.qualification

import io.github.rubixhacker.harness.contract.StrictJson
import io.github.rubixhacker.harness.host.CleanCheckout
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.StandardCopyOption
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

/**
 * `publication.py`: package a verified staging tree into a downloadable bundle, and verify one.
 *
 * The bundle is only usable as evidence when its manifest lists every file with its digest, the
 * audit inside it still reproduces the staged bytes, and the trusted manifest digest matches the
 * bytes on disk.
 */
object PublicationBundle {
    /**
     * `publication.files_in`: every file under the bundle with its SHA-256, excluding the manifest.
     *
     * The order is the reference's `rglob` order: the files of a directory are listed before its
     * subdirectories are descended. The manifest bytes are part of the recorded evidence.
     */
    fun filesIn(bundle: Path): Map<String, String> {
        val entries = pythonRglob(bundle)
        if (entries.any { Files.isSymbolicLink(it) }) {
            throw IllegalArgumentException("publication bundle contains a symbolic link")
        }
        val result = LinkedHashMap<String, String>()
        for (path in entries) {
            if (!Files.isRegularFile(path)) continue
            val relative = bundle.relativize(path).toString().replace('\\', '/')
            if (relative == "manifest.json") continue
            result[relative] = Fs.digest(path)
        }
        return result
    }

    /** `Path.rglob("*")` order: a directory's files first, then its subdirectories. */
    private fun pythonRglob(root: Path): List<Path> {
        val result = mutableListOf<Path>()
        fun visit(directory: Path) {
            val entries = Files.newDirectoryStream(directory).use { stream -> stream.toList() }
            val directories = mutableListOf<Path>()
            for (entry in entries) {
                if (Files.isDirectory(entry)) directories.add(entry) else result.add(entry)
            }
            for (child in directories) visit(child)
        }
        visit(root)
        return result
    }

    /** `publication.package`: copy the audited staging bytes into a bundle and bind them. */
    fun packageBundle(repository: Path, auditPath: Path, destination: Path): JsonObject {
        val audit = StrictJson.load(Fs.readText(auditPath)) as? JsonObject
            ?: throw IllegalArgumentException("staged publication audit did not pass")
        if (Py.str(audit["status"]) != "PASSED") {
            throw IllegalArgumentException("staged publication audit did not pass")
        }
        StagingAudit.verifyAuditAgainstStaging(audit, repository)
        if (Files.exists(destination)) throw java.nio.file.FileAlreadyExistsException(destination.toString())
        destination.parent?.let { Files.createDirectories(it) }
        Files.createDirectory(destination)
        Files.copy(
            repository.resolve("LICENSE.md"),
            destination.resolve("LICENSE.md"),
            StandardCopyOption.COPY_ATTRIBUTES,
        )
        Files.copy(
            auditPath,
            destination.resolve("artifact-audit.json"),
            StandardCopyOption.COPY_ATTRIBUTES,
        )
        val stagedSource = repository.resolve("build/staging-repository")
        val stagedDestination = destination.resolve("build/staging-repository")
        val artifacts = audit["artifacts"] as? JsonArray
            ?: throw IllegalArgumentException("staged publication audit artifact list is invalid")
        for (item in artifacts) {
            val entry = item as JsonObject
            val relative = Path.of(Py.str(entry["path"])!!)
            val source = stagedSource.resolve(relative)
            val target = stagedDestination.resolve(relative)
            target.parent?.let { Files.createDirectories(it) }
            Files.copy(source, target, StandardCopyOption.COPY_ATTRIBUTES)
            if (relative.getName(0).toString() != ".qualification") {
                val checksum = source.resolveSibling("${source.fileName}.sha256")
                Files.copy(
                    checksum,
                    target.resolveSibling("${target.fileName}.sha256"),
                    StandardCopyOption.COPY_ATTRIBUTES,
                )
            }
        }
        val files = JsonObject(filesIn(destination).mapValues { JsonPrimitive(it.value) })
        val manifest = buildJsonObject {
            put("candidate_sha", audit.getValue("candidate_sha"))
            put("targets", audit.getValue("targets"))
            put("files", files)
        }
        val manifestPath = destination.resolve("manifest.json")
        Fs.writeText(manifestPath, PyJson.render(manifest) + "\n")
        verify(destination, Py.str(audit["candidate_sha"])!!, Fs.digest(manifestPath))
        return manifest
    }

    /** `publication.verify`: a downloaded bundle must reproduce its manifest and its staged audit. */
    fun verify(bundle: Path, candidateSha: String, expectedManifestSha256: String): JsonObject {
        if (!Py.SHA64.matches(expectedManifestSha256) ||
            Fs.digest(bundle.resolve("manifest.json")) != expectedManifestSha256
        ) {
            throw IllegalArgumentException("trusted manifest SHA-256 differs from downloaded bundle")
        }
        val manifest = StrictJson.load(Fs.readText(bundle.resolve("manifest.json"))) as? JsonObject
            ?: throw IllegalArgumentException("publication bundle candidate, targets, or audit status differs")
        val audit = StrictJson.load(Fs.readText(bundle.resolve("artifact-audit.json"))) as? JsonObject
            ?: throw IllegalArgumentException("publication bundle candidate, targets, or audit status differs")
        if (!Py.SHA40.matches(candidateSha) ||
            Py.str(manifest["candidate_sha"]) != candidateSha ||
            Py.str(audit["candidate_sha"]) != candidateSha ||
            Py.str(audit["status"]) != "PASSED" ||
            manifest["targets"] != audit["targets"]
        ) {
            throw IllegalArgumentException("publication bundle candidate, targets, or audit status differs")
        }
        val files = JsonObject(filesIn(bundle).mapValues { JsonPrimitive(it.value) })
        if (manifest["files"] != files) {
            throw IllegalArgumentException("publication bundle files or bytes differ from manifest")
        }
        StagingAudit.verifyAuditAgainstStaging(audit, bundle, allowPinnedContentContract = true)
        return manifest
    }
}

/** `publication.main`. */
object PublicationCli {
    fun run(arguments: Array<String>, repository: Path? = null): Int {
        var action: String? = null
        var candidateSha: String? = null
        var audit: Path? = null
        var output: Path? = null
        var manifestSha256: String? = null
        var index = 0
        while (index < arguments.size) {
            when (val argument = arguments[index]) {
                "package", "verify" -> action = argument
                "--candidate-sha" -> candidateSha = arguments[++index]
                "--audit" -> audit = Path.of(arguments[++index])
                "--output" -> output = Path.of(arguments[++index])
                "--manifest-sha256" -> manifestSha256 = arguments[++index]
                else -> return usage("unexpected argument: $argument")
            }
            index++
        }
        if (action == null || candidateSha == null || output == null) {
            return usage("action, --candidate-sha, and --output are required")
        }
        val manifest = when (action) {
            "package" -> {
                if (audit == null) return usage("package needs --audit")
                val root = repository ?: Path.of("").toAbsolutePath()
                CleanCheckout.require(root.toFile(), candidateSha)
                PublicationBundle.packageBundle(root, audit, output)
            }
            else -> {
                if (manifestSha256 == null) return usage("verify needs the trusted manifest SHA-256")
                PublicationBundle.verify(output, candidateSha, manifestSha256)
            }
        }
        println(
            PyJson.renderDefault(
                buildJsonObject {
                    put("candidate_sha", manifest.getValue("candidate_sha"))
                    put("targets", manifest.getValue("targets"))
                    put("files", JsonPrimitive((manifest["files"] as JsonObject).size))
                },
            ),
        )
        return 0
    }

    private fun usage(message: String): Int {
        System.err.println("usage error: $message")
        return 2
    }
}
