package io.github.rubixhacker.harness.qualification

import io.github.rubixhacker.harness.contract.Qualification
import io.github.rubixhacker.harness.contract.Sha256
import io.github.rubixhacker.harness.contract.StrictJson
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.Path
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

/** One parsed receipt repository path, keeping Python's Windows/POSIX distinction. */
data class RepositoryPath(val text: String, val windows: Boolean)

/**
 * Staging receipt rules of `tools/qualification/stage.py`.
 *
 * `audit_staging` calls `stage.verify_receipt`, so the receipt checks it depends on are ported
 * here instead of being left as a Python import.
 */
object StageReceipt {
    private val taskLine = Regex("> Task (:[^ ]+)(?: (.*))?")

    /** `stage.publication_tasks`. */
    fun publicationTasks(targets: List<String>?): List<String> {
        if (targets == null || targets.isEmpty() || targets.toSet().size != targets.size ||
            !Qualification.matrixTargets().containsAll(targets)
        ) {
            throw IllegalArgumentException("publication targets are missing, duplicate, or unknown")
        }
        val tasks = mutableListOf<String>()
        for (module in Qualification.modules) {
            tasks.add(":$module:publishKotlinMultiplatformPublicationToStagingRepository")
            for (target in targets) {
                tasks.add(":$module:publish${target.replaceFirstChar { it.uppercase() }}PublicationToStagingRepository")
            }
        }
        return tasks
    }

    /** `stage.stage_command` for a resolved repository directory. */
    fun stageCommand(repository: Path, tasks: List<String>): List<String> =
        stageCommand(RepositoryPath(repository.toString(), windows = false), tasks)

    /** `stage.stage_command`. */
    fun stageCommand(repository: RepositoryPath, tasks: List<String>): List<String> {
        val wrapper = repository.text + if (repository.windows) "\\gradlew.bat" else "/gradlew"
        return listOf(wrapper, "--no-daemon", "--console=plain") + tasks
    }

    /** `stage.receipt_repository`: an absolute path string, or null when it is not usable. */
    fun receiptRepository(value: String?): RepositoryPath? {
        if (value == null) return null
        windowsRepository(value)?.let { return it }
        val posix = Path.of(value)
        if (!posix.isAbsolute || posix.toString() != value) return null
        if (".." in value.split('/')) return null
        if (value.startsWith("//")) return null
        return RepositoryPath(value, windows = false)
    }

    private fun windowsRepository(value: String): RepositoryPath? {
        if ('/' in value) return null
        val drive = Regex("^[A-Za-z]:\\\\").containsMatchIn(value)
        val unc = Regex("^\\\\\\\\[^\\\\]+\\\\").containsMatchIn(value)
        if (!drive && !unc) return null
        val rest = if (drive) value.substring(3) else value.substringAfter("\\\\").substringAfter('\\')
        val components = value.substring(0, value.length - rest.length).split('\\') + rest.split('\\')
        if (".." in components) return null
        if (components.any { it.isNotEmpty() && it.trimEnd(' ', '.') != it }) return null
        return RepositoryPath(value, windows = true)
    }

    /** `stage.checkout_for_console`: the checkout a staging console under `build/` belongs to. */
    fun checkoutForConsole(console: Path): Path? {
        val resolved = console.toAbsolutePath().normalize()
        var current: Path? = resolved.parent
        while (current != null) {
            if (Files.exists(current.resolve(".git"))) {
                val qualification = current.resolve("build/staging-repository/.qualification")
                if (resolved.startsWith(qualification)) {
                    val checkout = try {
                        Path.of(gitOutput(current, "rev-parse", "--show-toplevel")).toAbsolutePath().normalize()
                    } catch (error: Exception) {
                        throw IllegalArgumentException("staging console checkout is invalid")
                    }
                    if (checkout != current) {
                        throw IllegalArgumentException("staging console differs from resolved checkout")
                    }
                    return checkout
                }
            }
            current = current.parent
        }
        return null
    }

    private fun gitOutput(repository: Path, vararg arguments: String): String {
        val process = ProcessBuilder(listOf("git", "-C", repository.toString()) + arguments).start()
        val output = process.inputStream.use { it.readBytes() }
        val status = process.waitFor()
        if (status != 0) throw IllegalArgumentException("git failed")
        return output.toString(StandardCharsets.UTF_8).trim()
    }

    /** `stage.verify_receipt`. Throws [IllegalArgumentException] with the reference message. */
    fun verify(
        receipt: JsonElement,
        console: Path,
        candidateSha: String,
        targets: List<String>,
        expectedRepository: Path? = null,
    ) {
        val data = receipt as? JsonObject ?: throw IllegalArgumentException("staging receipt is invalid")
        val tasks = publicationTasks(targets)
        val repository = receiptRepository(Py.str(data["repository"]))
            ?: throw IllegalArgumentException("staging receipt command differs from required Gradle invocation")
        val command = data["command"]
        val expectedCommand = stageCommand(repository, tasks)
        if (command !is JsonArray ||
            command.mapNotNull { Py.str(it) } != expectedCommand ||
            command.size != expectedCommand.size
        ) {
            throw IllegalArgumentException("staging receipt command differs from required Gradle invocation")
        }
        val checkout = checkoutForConsole(console)
        if (expectedRepository != null) {
            val trusted = receiptRepository(expectedRepository.toString())
            if (trusted == null || trusted.text != repository.text) {
                throw IllegalArgumentException("staging receipt repository differs from producer checkout")
            }
        }
        if (checkout != null && repository.text != checkout.toString()) {
            throw IllegalArgumentException("staging receipt repository differs from producer checkout")
        }
        val declaredTargets = data["targets"]
        if (Py.str(data["candidate_sha"]) != candidateSha ||
            declaredTargets !is JsonArray ||
            declaredTargets.mapNotNull { Py.str(it) } != targets ||
            declaredTargets.size != targets.size ||
            data["tasks"] !is JsonArray ||
            (data["tasks"] as JsonArray).mapNotNull { Py.str(it) } != tasks ||
            (data["tasks"] as JsonArray).size != tasks.size ||
            Py.str(data["status"]) != "PASSED" ||
            !Py.equalsInt(data["exit_code"], 0)
        ) {
            throw IllegalArgumentException("staging receipt candidate, targets, tasks, or outcome differs")
        }
        if (!Files.isRegularFile(console) || Files.isSymbolicLink(console)) {
            throw IllegalArgumentException("staging console is missing")
        }
        val raw = Fs.readBytes(console)
        if (Sha256.of(raw) != Py.str(data["console_sha256"])) {
            throw IllegalArgumentException("staging console bytes differ from receipt")
        }
        val text = String(raw, StandardCharsets.UTF_8)
        val observed = mutableMapOf<String, String>()
        for (line in splitLines(text)) {
            val match = taskLine.matchEntire(line) ?: continue
            val status = match.groupValues[2]
            observed[match.groupValues[1]] = status.ifEmpty { "EXECUTED" }
        }
        if (tasks.any { observed[it] !in setOf("EXECUTED", "UP-TO-DATE", "FROM-CACHE") }) {
            throw IllegalArgumentException("staging console has a missing, skipped, or failed publication task")
        }
        if ("BUILD SUCCESSFUL" !in text) {
            throw IllegalArgumentException("staging console lacks a successful Gradle outcome")
        }
    }

    /** Python's `str.splitlines()`: every line boundary the reference recognises. */
    internal fun splitLines(text: String): List<String> {
        val lines = mutableListOf<String>()
        val current = StringBuilder()
        var index = 0
        while (index < text.length) {
            val char = text[index]
            val breaks = char == '\n' || char == '\r' || char == '\u000B' || char == '\u000C' ||
                char == '\u001C' || char == '\u001D' || char == '\u001E' ||
                char == '\u0085' || char == '\u2028' || char == '\u2029'
            if (breaks) {
                lines.add(current.toString())
                current.setLength(0)
                if (char == '\r' && index + 1 < text.length && text[index + 1] == '\n') index++
            } else {
                current.append(char)
            }
            index++
        }
        if (current.isNotEmpty()) lines.add(current.toString())
        return lines
    }
}

/**
 * `qualify.audit_staging` and `qualify.verify_audit_against_staging`.
 *
 * The audit recomputes every advertised byte: staged POM and metadata contracts, sources
 * archives against committed source bytes, Dokka output, license notices, and the staging task
 * receipt. Field order of the returned object is part of the recorded evidence.
 */
object StagingAudit {
    private val groupPath = Qualification.GROUP.replace(".", "/")

    fun audit(
        root: Path,
        candidateSha: String,
        targets: Collection<String>? = null,
        licenseFile: Path = Path.of("LICENSE.md"),
        receiptPath: Path? = null,
        consolePath: Path? = null,
        contentContract: JsonElement? = null,
    ): JsonObject {
        val errors = mutableListOf<String>()
        val artifacts = mutableListOf<JsonObject>()
        if (!Py.SHA40.matches(candidateSha)) {
            throw IllegalArgumentException("candidate SHA must be a full commit hash")
        }
        val selected = if (targets == null) Qualification.matrixTargets() else targets.toSet()
        if (selected.isEmpty() || !Qualification.matrixTargets().containsAll(selected)) {
            throw IllegalArgumentException("selected publication targets are invalid")
        }
        val licenseBytes: ByteArray?
        if (!Files.isRegularFile(licenseFile)) {
            errors.add("repository license is missing")
            licenseBytes = null
        } else {
            licenseBytes = Fs.readBytes(licenseFile)
        }
        val repository = licenseFile.parent ?: Path.of(".")

        var sourcesContract: Map<String, Map<String, String>>
        var docsContract: Map<String, String>
        val contract: JsonElement
        if (contentContract == null) {
            sourcesContract = try {
                CandidateSource.contract(repository, candidateSha)
            } catch (error: Exception) {
                errors.add("candidate source tree invalid: ${error.message}")
                emptyMap()
            }
            val docs = LinkedHashMap<String, String>()
            for (module in Qualification.modules) {
                val rootDocs = root.resolve(groupPath).resolve(module).resolve(Qualification.VERSION)
                    .resolve("$module-${Qualification.VERSION}-javadoc.jar")
                if (Files.isRegularFile(rootDocs)) {
                    try {
                        ArchiveContract.validateGeneratedDocs(
                            rootDocs,
                            repository.resolve(module).resolve("build/dokka/html"),
                            licenseBytes,
                        )
                        docs[module] = Fs.digest(rootDocs)
                    } catch (error: Exception) {
                        errors.add("$module: API documentation differs from Dokka: ${error.message}")
                    }
                } else {
                    errors.add("$module: root API documentation artifact missing")
                }
            }
            docsContract = docs
            contract = JsonObject(
                linkedMapOf(
                    "schema" to JsonPrimitive(1),
                    "sources" to sourcesJson(sourcesContract),
                    "api_docs_sha256" to JsonObject(docsContract.mapValues { JsonPrimitive(it.value) }),
                ),
            )
        } else {
            contract = contentContract
            val recorded = contentContract as? JsonObject
            val sources = recorded?.get("sources") as? JsonObject
            val docs = recorded?.get("api_docs_sha256") as? JsonObject
            val validSources = sources != null &&
                sources.keys == Qualification.modules.toSet() &&
                sources.values.all { value ->
                    value is JsonObject && value.isNotEmpty() &&
                        value.all { (path, sha) -> path.isNotEmpty() && Py.SHA64.matches(Py.str(sha) ?: "") }
                }
            val validDocs = docs != null &&
                docs.keys == Qualification.modules.toSet() &&
                docs.values.all { Py.SHA64.matches(Py.str(it) ?: "") }
            if (recorded == null || !Py.equalsInt(recorded["schema"], 1) || !validSources || !validDocs) {
                errors.add("recorded publication content contract is invalid")
                sourcesContract = emptyMap()
                docsContract = emptyMap()
            } else {
                sourcesContract = sources.mapValues { (_, value) ->
                    (value as JsonObject).mapValues { (_, sha) -> Py.str(sha)!! }
                }
                docsContract = docs.mapValues { (_, value) -> Py.str(value)!! }
            }
        }

        for (module in Qualification.modules) {
            val rootMetadata = root.resolve(groupPath).resolve(module).resolve(Qualification.VERSION)
                .resolve("$module-${Qualification.VERSION}.module")
            if (!Files.isRegularFile(rootMetadata)) {
                errors.add("$module: root Gradle metadata missing")
            }
            val publicationTargets = listOf<String?>(null) + selected.sortedWith(CanonicalText::compare)
            for (target in publicationTargets) {
                auditPublication(
                    root,
                    module,
                    target,
                    selected,
                    sourcesContract,
                    docsContract,
                    licenseBytes,
                    errors,
                    artifacts,
                )
            }
        }

        var stageReceipt: String? = null
        var stageConsole: String? = null
        if (receiptPath != null || consolePath != null) {
            try {
                if (receiptPath == null || consolePath == null) {
                    throw IllegalArgumentException("staging receipt and console are both required")
                }
                val resolvedRoot = root.toAbsolutePath().normalize()
                stageReceipt = relativePosix(resolvedRoot, receiptPath.toAbsolutePath().normalize())
                stageConsole = relativePosix(resolvedRoot, consolePath.toAbsolutePath().normalize())
                val receipt = StrictJson.load(Fs.readText(receiptPath))
                StageReceipt.verify(receipt, consolePath, candidateSha, selected.sortedWith(CanonicalText::compare))
                artifacts.add(
                    JsonObject(linkedMapOf("path" to JsonPrimitive(stageReceipt), "sha256" to JsonPrimitive(Fs.digest(receiptPath)))),
                )
                artifacts.add(
                    JsonObject(linkedMapOf("path" to JsonPrimitive(stageConsole), "sha256" to JsonPrimitive(Fs.digest(consolePath)))),
                )
            } catch (error: Exception) {
                errors.add("staging task outcome invalid: ${error.message}")
            }
        }

        return buildJsonObject {
            put("candidate_sha", JsonPrimitive(candidateSha))
            put("targets", JsonArray(selected.sortedWith(CanonicalText::compare).map { JsonPrimitive(it) }))
            put("stage_receipt", stageReceipt?.let { JsonPrimitive(it) } ?: JsonNull)
            put("stage_console", stageConsole?.let { JsonPrimitive(it) } ?: JsonNull)
            put("content_contract", contract)
            put("artifacts", JsonArray(artifacts))
            put("status", JsonPrimitive(if (errors.isEmpty()) "PASSED" else "FAILED"))
            put("errors", JsonArray(errors.map { JsonPrimitive(it) }))
        }
    }

    private fun sourcesJson(sources: Map<String, Map<String, String>>): JsonObject = JsonObject(
        sources.mapValues { (_, value) ->
            JsonObject(value.mapValues { (_, sha) -> JsonPrimitive(sha) })
        },
    )

    private fun relativePosix(root: Path, path: Path): String {
        if (!path.startsWith(root)) {
            throw IllegalArgumentException("$path is not in the subpath of $root")
        }
        return root.relativize(path).toString().replace('\\', '/')
    }

    private fun auditPublication(
        root: Path,
        module: String,
        target: String?,
        selected: Set<String>,
        sourcesContract: Map<String, Map<String, String>>,
        docsContract: Map<String, String>,
        licenseBytes: ByteArray?,
        errors: MutableList<String>,
        artifacts: MutableList<JsonObject>,
    ) {
        val name = if (target == null) module else Qualification.targetPublicationName(module, target)
        val base = root.resolve(groupPath).resolve(name).resolve(Qualification.VERSION)
        val pom = base.resolve("$name-${Qualification.VERSION}.pom")
        val metadata = base.resolve("$name-${Qualification.VERSION}.module")
        if (!Files.isRegularFile(pom) || !Files.isRegularFile(metadata)) {
            errors.add("$name: staged POM or Gradle metadata missing")
            return
        }
        val pomRoot = try {
            PomContract.parse(pom)
        } catch (error: PomParseException) {
            errors.add("$name: POM XML is invalid: ${error.message}")
            return
        }

        val expectedSections = mutableSetOf<String>()
        for (key in listOf(
            "modelVersion", "groupId", "artifactId", "version", "name",
            "description", "url", "licenses", "developers", "scm", "dependencies",
        )) {
            expectedSections.add(PomContract.qualified(key))
        }
        val packaging = when (target) {
            null, "jvm" -> null
            "android" -> "aar"
            else -> "klib"
        }
        if (packaging != null) expectedSections.add(PomContract.qualified("packaging"))
        val observedSections = PomContract.childElements(pomRoot).map { PomContract.tag(it) }
        if (PomContract.tag(pomRoot) != PomContract.qualified("project") ||
            observedSections.size != expectedSections.size ||
            observedSections.toSet() != expectedSections ||
            PomContract.findText(pomRoot, "modelVersion") != "4.0.0" ||
            PomContract.findText(pomRoot, "packaging") != packaging
        ) {
            errors.add("$name: POM effective model differs from publication contract")
        }
        for ((key, expected) in listOf(
            "groupId" to Qualification.GROUP,
            "artifactId" to name,
            "version" to Qualification.VERSION,
        )) {
            if (PomContract.findText(pomRoot, key) != expected) {
                errors.add("$name: wrong POM $key")
            }
        }
        for ((key, expected) in PomContract.metadata(module)) {
            if (!PomContract.elementMatches(PomContract.find(pomRoot, key), key, expected)) {
                errors.add("$name: POM $key differs from publication contract")
            }
        }

        val pomEntries = PomContract.findAll(pomRoot, "dependencies", "dependency")
        val dependencyContainer = PomContract.find(pomRoot, "dependencies")
        if (dependencyContainer == null ||
            PomContract.attributes(dependencyContainer).isNotEmpty() ||
            PomContract.childElements(dependencyContainer).any { PomContract.tag(it) != PomContract.qualified("dependency") }
        ) {
            errors.add("$name: POM dependency container differs from publication contract")
        }
        val fields = listOf("groupId", "artifactId", "version", "scope").map { PomContract.qualified(it) }.toSet()
        val dependencies = pomEntries.map { entry ->
            listOf("groupId", "artifactId", "version", "scope").map { PomContract.findText(entry, it) }
        }.toSet()
        val expectedDependencies = io.github.rubixhacker.harness.contract.PublicationContract.pomDependencies(module, target)
            .map { listOf<String?>(it.group, it.module, it.version, it.scope) }.toSet()
        if (dependencies.size != pomEntries.size ||
            dependencies != expectedDependencies ||
            pomEntries.any { entry ->
                PomContract.childElements(entry).map { PomContract.tag(it) }.toSet() != fields ||
                    PomContract.childElements(entry).size != fields.size ||
                    PomContract.attributes(entry).isNotEmpty() ||
                    PomContract.childElements(entry).any { child ->
                        PomContract.attributes(child).isNotEmpty() || PomContract.childElements(child).isNotEmpty()
                    }
            }
        ) {
            errors.add("$name: POM dependency graph differs from publication contract")
        }

        var referenced: Set<Path> = emptySet()
        try {
            val moduleData = StrictJson.load(Fs.readText(metadata))
            val result = PublicationMetadataAudit.audit(base, module, target, moduleData)
            errors.addAll(result.errors)
            referenced = result.referenced
        } catch (error: Exception) {
            errors.add("$name: Gradle metadata invalid: ${error.message}")
        }

        val binary = root.resolve(Qualification.publicationBinaryPath(module, target))
        val source = base.resolve("$name-${Qualification.VERSION}-sources.jar")
        val docs = base.resolve("$name-${Qualification.VERSION}-javadoc.jar")
        val licenseArtifact = base.resolve("$name-${Qualification.VERSION}-license.md")
        for ((path, label) in listOf(
            binary to "binary",
            source to "sources artifact",
            docs to "API documentation artifact",
            licenseArtifact to "license artifact",
        )) {
            if (!Files.isRegularFile(path)) {
                errors.add("$name: $label missing: ${path.fileName}")
            }
        }
        if (Files.isRegularFile(licenseArtifact) && licenseBytes != null &&
            !Fs.readBytes(licenseArtifact).contentEquals(licenseBytes)
        ) {
            errors.add("$name: license differs from repository license")
        }
        if (Files.isRegularFile(source) && module in sourcesContract) {
            try {
                val expected = CandidateSource.expectedEntries(sourcesContract, module, target)
                if (expected.isEmpty()) throw IllegalArgumentException("candidate source set is empty")
                ArchiveContract.validateSourceArchive(source, expected)
            } catch (error: Exception) {
                errors.add("$name: sources archive invalid: ${error.message}")
            }
        }
        if (Files.isRegularFile(docs) && module in docsContract && Fs.digest(docs) != docsContract[module]) {
            errors.add("$name: API documentation differs from generated Dokka publication")
        }
        if (target != null && Qualification.isAppleTarget(target)) {
            val appleMetadata = base.resolve("$name-${Qualification.VERSION}-metadata.jar")
            if (Files.isRegularFile(appleMetadata) && Files.isRegularFile(binary)) {
                try {
                    ArchiveContract.validateAppleMetadata(appleMetadata, binary)
                } catch (error: Exception) {
                    errors.add("$name: Apple metadata invalid: ${error.message}")
                }
            }
        }
        for (path in listOf(binary, source, docs)) {
            if (!Files.isRegularFile(path)) continue
            try {
                ArchiveContract.open(path) { archive ->
                    val entries = mutableListOf<String>()
                    for (entry in archive.entries()) entries.add(entry.name)
                    if (path == docs && "index.html" !in entries) {
                        errors.add("$name: API documentation index missing")
                    }
                    if (path == docs && !entries.any { "/" in it && it.endsWith(".html") }) {
                        errors.add("$name: API documentation pages missing")
                    }
                    if (path == source && !entries.any { it.endsWith(".kt") || it.endsWith(".java") }) {
                        errors.add("$name: sources archive has no source files")
                    }
                    if (path == binary && path.fileName.toString().endsWith(".jar")) {
                        val names = ArchiveContract.fileNames(archive)
                        if ("META-INF/LICENSE.md" !in names) {
                            errors.add("$name: embedded license missing")
                        } else if (licenseBytes != null) {
                            val entry = archive.getEntry("META-INF/LICENSE.md")
                            val bytes = entry?.let { archive.getInputStream(it).use { stream -> stream.readBytes() } }
                            if (bytes == null || !bytes.contentEquals(licenseBytes)) {
                                errors.add("$name: embedded license differs from repository license")
                            }
                        }
                    }
                }
            } catch (_: IllegalArgumentException) {
                errors.add("$name: ${path.fileName} archive is invalid")
            } catch (_: BadArchiveException) {
                errors.add("$name: ${path.fileName} archive is invalid")
            }
        }

        val hashed = mutableListOf(pom, metadata, binary, source, docs, licenseArtifact)
        hashed.addAll(
            (referenced - setOf(binary, source)).sortedWith { left, right ->
                CanonicalText.compare(left.toString(), right.toString())
            },
        )
        for (path in hashed) {
            if (!Files.isRegularFile(path)) continue
            val sha = Fs.digest(path)
            artifacts.add(
                JsonObject(
                    linkedMapOf(
                        "path" to JsonPrimitive(root.relativize(path).toString().replace('\\', '/')),
                        "sha256" to JsonPrimitive(sha),
                    ),
                ),
            )
            val checksum = path.resolveSibling("${path.fileName}.sha256")
            if (!Files.isRegularFile(checksum) || Fs.readText(checksum).trim().lowercase() != sha) {
                errors.add("${path.fileName}: SHA-256 sidecar missing or incorrect")
            }
        }
    }

    /**
     * `qualify.verify_audit_against_staging`: a recorded audit is usable only while the staged
     * files still reproduce it byte for byte.
     */
    fun verifyAuditAgainstStaging(
        auditData: JsonElement?,
        repository: Path,
        allowPinnedContentContract: Boolean = false,
    ) {
        val data = auditData as? JsonObject
        if (data == null || !Py.SHA40.matches(Py.str(data["candidate_sha"]) ?: "")) {
            throw IllegalArgumentException("staged audit candidate identity is invalid")
        }
        val candidateSha = Py.str(data["candidate_sha"])!!
        val root = repository.resolve("build/staging-repository")
        val targets = data["targets"]
        if (targets !is JsonArray || targets.isEmpty()) {
            throw IllegalArgumentException("staged audit targets are invalid")
        }
        val targetNames = targets.mapNotNull { Py.str(it) }
        if (targetNames.size != targets.size || targetNames.toSet().size != targetNames.size) {
            throw IllegalArgumentException("staged audit targets are invalid")
        }
        val paths = mutableListOf<Path>()
        for (key in listOf("stage_receipt", "stage_console")) {
            val relative = Py.str(data[key])
            if (relative == null || !relative.startsWith(".qualification/")) {
                throw IllegalArgumentException("staged audit task outcome path is invalid")
            }
            val path = root.resolve(relative).toAbsolutePath().normalize()
            if (!path.startsWith(root.toAbsolutePath().normalize())) {
                throw IllegalArgumentException("staged audit task outcome path escapes repository")
            }
            paths.add(path)
        }
        val staged = audit(
            root = root,
            candidateSha = candidateSha,
            targets = targetNames,
            licenseFile = repository.resolve("LICENSE.md"),
            receiptPath = paths[0],
            consolePath = paths[1],
            contentContract = if (allowPinnedContentContract) data["content_contract"] else null,
        )
        if (Py.str(data["stage_receipt"]) != Py.str(staged["stage_receipt"]) ||
            Py.str(data["stage_console"]) != Py.str(staged["stage_console"])
        ) {
            throw IllegalArgumentException("staged audit task outcome differs from canonical staging path")
        }
        val observedFiles = LinkedHashMap<String, String?>()
        for (item in staged["artifacts"] as JsonArray) {
            val entry = item as JsonObject
            observedFiles[Py.str(entry["path"])!!] = Py.str(entry["sha256"])
        }
        val recorded = data["artifacts"]
        if (recorded !is JsonArray || recorded.any { it !is JsonObject }) {
            throw IllegalArgumentException("staged audit artifact list is invalid")
        }
        val recordedFiles = LinkedHashMap<String?, String?>()
        for (item in recorded) {
            val entry = item as JsonObject
            recordedFiles[Py.str(entry["path"])] = Py.str(entry["sha256"])
        }
        val recordedErrors = data["errors"] ?: JsonArray(emptyList())
        if (recordedErrors !is JsonArray) {
            throw IllegalArgumentException("staged audit differs from current staged files")
        }
        val stagedErrors = (staged["errors"] as JsonArray).map { Py.str(it) ?: CanonicalText.of(it) }
        val auditErrors = recordedErrors.map { Py.str(it) ?: CanonicalText.of(it) }
        if (recordedFiles.size != recorded.size ||
            recordedFiles != observedFiles ||
            data["content_contract"] != staged["content_contract"] ||
            Py.str(data["status"]) != Py.str(staged["status"]) ||
            auditErrors.sortedWith(CanonicalText::compare) != stagedErrors.sortedWith(CanonicalText::compare)
        ) {
            throw IllegalArgumentException("staged audit differs from current staged files")
        }
    }
}
