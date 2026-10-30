package io.github.rubixhacker.harness.qualification

import io.github.rubixhacker.harness.contract.StrictJson
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.StandardCopyOption
import java.util.concurrent.TimeUnit
import javax.xml.parsers.DocumentBuilderFactory
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import org.w3c.dom.Element
import org.w3c.dom.Node

/** `full_corpus.verify_reports`, `package_archive`, and `verify_archive`. */
object CorpusReports {
    /** `verify_reports`: does one fresh run reproduce the reviewed corpus and its reports? */
    fun verifyReports(
        repository: Path,
        manifest: JsonObject,
        candidateSha: String,
        binding: JsonObject,
        reports: Map<String, List<Path>>,
        mapping: List<JsonObject>? = null,
        upstream: Path? = null,
        requireCheckout: Boolean = false,
        manifestPath: Path? = null,
        mappingPath: Path? = null,
        evidenceRootInput: Path? = null,
    ): JsonObject {
        val evidenceRoot = (evidenceRootInput ?: repository).toAbsolutePath().normalize()
        val resolvedRepository = repository.toAbsolutePath().normalize()
        val problems = mutableListOf<String>()
        if (Py.str(manifest["kind"]) != "full-common-corpus" || !Py.equalsInt(manifest["schema"], 1)) {
            problems.add("full corpus manifest is invalid")
        }
        if (!FullCorpus.SHA40.matches(candidateSha)) problems.add("candidate SHA is invalid")
        if (Py.str(binding["candidate_sha"]) != candidateSha) {
            problems.add("candidate SHA differs from report binding")
        }
        if (Py.str(binding["manifest_sha256"]) != FullCorpus.canonicalDigest(manifest)) {
            problems.add("manifest hash differs from report binding")
        }
        val bindingSchema = binding["schema"] ?: JsonPrimitive(1)
        if (!Py.equalsInt(bindingSchema, 1) && !Py.equalsInt(bindingSchema, 2)) {
            problems.add("unknown common corpus binding schema")
        }
        val started = if (Py.isInt(binding["started_ns"])) Py.int(binding["started_ns"]) else null
        val finished = if (Py.isInt(binding["finished_ns"])) Py.int(binding["finished_ns"]) else null
        if (started == null || finished == null || started <= 0 || finished < started) {
            problems.add("fresh report invocation window is invalid")
        }
        val command = binding["command"] as? JsonArray
        if (command == null || command.mapNotNull { Py.str(it) } != FullCorpus.GRADLE_COMMAND ||
            !Py.isInt(binding["exit_code"]) || Py.int(binding["exit_code"]) != 0L
        ) {
            problems.add("complete fresh Gradle invocation is missing or failed")
        }
        try {
            val logPath = Py.str(binding["log"])
            if (logPath.isNullOrEmpty()) throw IllegalArgumentException("log path is absent")
            var logFile: Path = if (evidenceRoot != resolvedRepository) {
                evidenceRoot.resolve("gradle.log")
            } else {
                Path.of(logPath)
            }
            if (!logFile.isAbsolute) logFile = resolvedRepository.resolve(logFile)
            val rawLog = Files.readAllBytes(logFile)
            if (CorpusFiles.digest(rawLog) != Py.str(binding["log_sha256"])) {
                throw IllegalArgumentException("log SHA-256 differs")
            }
            val text = rawLog.toString(StandardCharsets.ISO_8859_1)
            if ("BUILD SUCCESSFUL" !in text ||
                FullCorpus.GRADLE_COMMAND.drop(6).any { "> Task " + it !in text }
            ) {
                throw IllegalArgumentException("successful twelve-task Gradle output is absent")
            }
        } catch (error: Exception) {
            problems.add("Gradle log binding differs: ${error.message}")
        }
        try {
            if (evidenceRoot != resolvedRepository) {
                problems.addAll(
                    CorpusVerification.archivedEnvironmentProblems(
                        resolvedRepository, binding["environment"], requireCheckout,
                    ),
                )
            } else {
                val environment = CorpusFiles.captureEnvironment(resolvedRepository)
                if (binding["environment"] != environment) {
                    problems.add("candidate environment or tool identity differs")
                }
                if (requireCheckout) {
                    val wrappers = environment["gradle_wrapper"] as JsonObject
                    val executables = environment["executables"] as JsonObject
                    if (wrappers.values.any { it is JsonNull } ||
                        executables.values.any {
                            it is JsonNull || !Py.equalsInt((it as JsonObject)["exit_code"], 0)
                        }
                    ) {
                        problems.add("candidate environment lacks required Gradle, Java, or Node tool identity")
                    }
                }
            }
        } catch (error: Exception) {
            problems.add("candidate environment or tool identity unavailable: ${error.message}")
        }
        problems.addAll(
            CorpusVerification.artifactBindingProblems(
                evidenceRoot, binding, started, finished, requireCheckout,
                checkMtime = evidenceRoot == resolvedRepository,
            ),
        )
        if (mapping != null && JsonArray(mapping) != manifest["original_mappings"]) {
            problems.add("reviewed original map differs from manifest")
        }
        if (Py.str(manifest["policy"]) == "production") {
            if (requireCheckout && upstream == null) {
                problems.add("pinned original source checkout is required")
            }
            problems.addAll(
                CorpusVerification.candidateInputProblems(
                    resolvedRepository, candidateSha, manifest,
                    mapping ?: (manifest["original_mappings"] as? JsonArray)
                        ?.mapNotNull { it as? JsonObject } ?: emptyList(),
                    manifestPath, mappingPath, checkCheckout = requireCheckout,
                ),
            )
        }
        if (upstream != null) {
            val revision = git(upstream, "rev-parse", "HEAD").trim()
            if (revision != FullCorpus.ORIGINAL_REVISION) {
                problems.add("pinned original source revision differs")
            }
            val originalRows = (manifest["original_mappings"] as? JsonArray)
                ?.mapNotNull { it as? JsonObject } ?: emptyList()
            val identities = originalRows.map { Py.str(it["original"]) }
            if (identities.size != identities.toSet().size) {
                problems.add("duplicate reviewed original identity")
            }
            val originalFiles = LinkedHashMap<String, ByteArray?>()
            val reviewFiles = LinkedHashMap<String, ByteArray?>()
            for (item in originalRows) {
                val path = Py.str(item["original_source"]) ?: ""
                val review = Py.str(item["review"]) ?: ""
                val originalClass = (Py.str(item["original"]) ?: "").substringBefore('#')
                if (path != "src/test/java/" + originalClass.replace(".", "/") + ".java") {
                    problems.add("original identity source path differs: ${Py.str(item["original"])}")
                }
                if (path !in originalFiles) {
                    val sourceFile = upstream.resolve(path)
                    originalFiles[path] = if (Files.isRegularFile(sourceFile)) {
                        Files.readAllBytes(sourceFile)
                    } else {
                        null
                    }
                }
                if (review !in reviewFiles) {
                    val reviewFile = resolvedRepository.resolve(review)
                    reviewFiles[review] = if (Files.isRegularFile(reviewFile)) {
                        Files.readAllBytes(reviewFile)
                    } else {
                        null
                    }
                }
                val raw = originalFiles[path]
                if (raw == null || CorpusFiles.digest(raw) != Py.str(item["original_sha256"])) {
                    problems.add("pinned original source hash differs: $path")
                } else {
                    val lines = raw.toString(StandardCharsets.UTF_8).lines()
                    val line = Py.int(item["original_line"] ?: JsonPrimitive(0))
                    val method = (Py.str(item["original"]) ?: "").substringAfter('#').substringBefore('[')
                    val declaration = Regex("\\bvoid\\s+" + Regex.escape(method) + "\\s*\\(")
                    if (line < 1 || line > lines.size ||
                        !declaration.containsMatchIn(lines[(line - 1).toInt()])
                    ) {
                        problems.add("original declaration line differs: ${Py.str(item["original"])}")
                    }
                }
                val reviewBytes = reviewFiles[review]
                if (reviewBytes == null || CorpusFiles.digest(reviewBytes) != Py.str(item["review_sha256"])) {
                    problems.add("reviewed mapping report hash differs: $review")
                }
            }
        }
        if (requireCheckout && Py.str(manifest["policy"]) != "production") {
            problems.addAll(CorpusFiles.candidateCheckoutProblems(resolvedRepository, candidateSha))
        }
        try {
            val scanned = CorpusFiles.scanSources(resolvedRepository)
            val mappings = mapping
                ?: (manifest["original_mappings"] as? JsonArray)?.mapNotNull { it as? JsonObject }
                ?: emptyList()
            val regenerated = FullCorpus.makeManifest(
                scanned, mappings, Py.str(manifest["policy"]) == "production",
                CorpusFiles.scanTestTree(resolvedRepository),
            )
            if (regenerated != manifest) {
                problems.add("source inventory or reviewed mapping differs from manifest")
            }
            val tree = FullCorpus.sourceTreeDigest(CorpusFiles.scanTestTree(resolvedRepository))
            if (tree != Py.str(manifest["source_tree_sha256"]) ||
                tree != Py.str(binding["source_tree_sha256"])
            ) {
                problems.add("source tree hash differs from report binding")
            }
        } catch (error: Exception) {
            problems.add("source inventory invalid: ${error.message}")
        }
        val counts = manifest["counts"] as? JsonObject ?: JsonObject(emptyMap())
        if (!Py.equalsInt(counts["unresolved_mappings"], 0) || Py.truthy(manifest["unresolved"])) {
            problems.add("unresolved original mappings")
        }
        if (Py.str(manifest["policy"]) == "production") {
            val mappings = (manifest["original_mappings"] as? JsonArray)?.size ?: 0
            if (mappings != 2385 ||
                !Py.equalsInt(counts["mapped_original_methods"], 2253) ||
                !Py.equalsInt(counts["reviewed_source_linked_methods"], 2258) ||
                !Py.equalsInt(counts["related_supplemental_methods"], 5) ||
                !Py.equalsInt(counts["mapped_original_identities"], 2353) ||
                !Py.equalsInt(counts["jvm_only_original_identities"], 32)
            ) {
                problems.add("reviewed original mapping totals differ from frozen corpus")
            }
        }
        val groupIds = FullCorpus.GROUPS.map { it.id }.toSet()
        val bindingReports = binding["reports"] as? JsonObject ?: JsonObject(emptyMap())
        if (reports.keys != groupIds || bindingReports.keys != groupIds) {
            problems.add("all six core and facade report groups are required")
        }
        val groups = mutableListOf<JsonObject>()
        var total = 0L
        for (group in FullCorpus.GROUPS) {
            val groupId = group.id
            val expected = FullCorpus.expectedCases(manifest, group)
            val paths = reports[groupId] ?: emptyList()
            val bound = bindingReports[groupId] as? JsonObject ?: JsonObject(emptyMap())
            val names = paths.map { relativeText(evidenceRoot, it) }.toSet()
            if (paths.isEmpty() || names.size != paths.size || bound.keys != names) {
                problems.add("missing or extra report files: $groupId")
            }
            val seen = LinkedHashMap<Pair<String, String>, Int>()
            var failures = 0L
            var errors = 0L
            var skipped = 0L
            val hashes = LinkedHashMap<String, JsonElement>()
            for (path in paths) {
                val name = relativeText(evidenceRoot, path)
                try {
                    val raw = Files.readAllBytes(path)
                    val fileHash = CorpusFiles.digest(raw)
                    hashes[name] = JsonPrimitive(fileHash)
                    if (Py.str(bound[name]) != fileHash) {
                        problems.add("report hash differs from source binding: $name")
                    }
                    if (evidenceRoot == resolvedRepository && started != null && finished != null) {
                        val modified = Files.getLastModifiedTime(path).to(TimeUnit.NANOSECONDS)
                        if (modified < started || modified > finished) {
                            problems.add("report predates or postdates invocation: $name")
                        }
                    }
                    val suite = suiteOf(raw)
                    if (suite.tagName != "testsuite") throw IllegalArgumentException("XML root is not testsuite")
                    val suiteCases = elementsNamed(suite, "testcase")
                    val observed = linkedMapOf(
                        "tests" to suiteCases.size.toLong(),
                        "failures" to suiteCases.count { childNamed(it, "failure") != null }.toLong(),
                        "errors" to suiteCases.count { childNamed(it, "error") != null }.toLong(),
                        "skipped" to suiteCases.count { childNamed(it, "skipped") != null }.toLong(),
                    )
                    for ((key, value) in observed) {
                        val attribute = suite.getAttribute(key)
                        if (attribute.isEmpty() || attribute.toLongOrNull() != value) {
                            throw IllegalArgumentException("XML $key count differs from cases")
                        }
                    }
                    val duration = suite.getAttribute("time").ifEmpty { "nan" }.toDoubleOrNull()
                    if (duration == null || duration.isNaN() || duration < 0 || duration == Double.POSITIVE_INFINITY) {
                        throw IllegalArgumentException("suite duration is invalid")
                    }
                    for (case in suiteCases) {
                        val classname = case.getAttribute("classname")
                        val method = case.getAttribute("name")
                        val caseTime = case.getAttribute("time").ifEmpty { "nan" }.toDoubleOrNull()
                        if (classname.isEmpty() || method.isEmpty() || caseTime == null ||
                            caseTime.isNaN() || caseTime < 0 || caseTime == Double.POSITIVE_INFINITY
                        ) {
                            throw IllegalArgumentException("case identity or duration is invalid")
                        }
                        val key = classname to method
                        seen[key] = (seen[key] ?: 0) + 1
                    }
                    failures += observed.getValue("failures")
                    errors += observed.getValue("errors")
                    skipped += observed.getValue("skipped")
                } catch (error: Exception) {
                    problems.add("invalid XML $name: ${error.message}")
                }
            }
            val missing = (expected - seen.keys).sortedWith { left, right -> comparePairs(left, right) }
            val extra = (seen.keys - expected).sortedWith { left, right -> comparePairs(left, right) }
            val duplicates = seen.filterValues { it != 1 }.keys.sortedWith { left, right -> comparePairs(left, right) }
            if (missing.isNotEmpty()) {
                problems.add("missing ${missing.size} expected cases in $groupId: ${pairList(missing.take(3))}")
            }
            if (extra.isNotEmpty()) {
                problems.add("unexpected ${extra.size} cases in $groupId: ${pairList(extra.take(3))}")
            }
            if (duplicates.isNotEmpty()) {
                problems.add("duplicate cases in $groupId: ${pairList(duplicates.take(3))}")
            }
            if (failures != 0L || errors != 0L || skipped != 0L) {
                problems.add("failed, errored, or skipped cases in $groupId")
            }
            total += seen.values.sumOf { it.toLong() }
            val cases = (manifest["cases"] as? JsonArray)?.mapNotNull { it as? JsonObject } ?: emptyList()
            fun countKind(kind: String): Int = cases.count { case ->
                Py.str(case["module"]) == group.module &&
                    group.host in ((case["hosts"] as? JsonArray)?.mapNotNull { Py.str(it) } ?: emptyList()) &&
                    Py.str(case["kind"]) == kind
            }
            val report = buildJsonObject {
                put("id", JsonPrimitive(groupId))
                put("expected", JsonPrimitive(expected.size))
                put("reported", JsonPrimitive(seen.values.sum()))
                put("mapped_original_methods", JsonPrimitive(countKind("mapped-original")))
                put("supplemental_cases", JsonPrimitive(countKind("supplemental")))
                put("platform_only_cases", JsonPrimitive(countKind("platform-only")))
                put("failures", JsonPrimitive(failures))
                put("errors", JsonPrimitive(errors))
                put("skipped", JsonPrimitive(skipped))
                put("report_sha256", JsonObject(hashes))
            }
            groups.add(report)
            if (Py.equalsInt(binding["schema"], 2) && groupId in FullCorpus.NODE_GROUPS) {
                val observedNodes = binding["node_observations"] as? JsonArray ?: JsonArray(emptyList())
                val matches = observedNodes.mapNotNull { it as? JsonObject }
                    .filter { Py.str(it["group_id"]) == groupId }
                val node = if (matches.size == 1) {
                    val match = matches.first()
                    buildJsonObject {
                        put("status", JsonPrimitive("OBSERVED_UNSIGNED"))
                        put("version", match["version"] ?: JsonNull)
                        put("executable_path", match["executable_path"] ?: JsonNull)
                        put("executable_sha256", match["executable_sha256"] ?: JsonNull)
                        put("pid", match["pid"] ?: JsonNull)
                        put("start_ticks", match["start_ticks"] ?: JsonNull)
                    }
                } else {
                    buildJsonObject { put("status", JsonPrimitive("UNPASSED")) }
                }
                groups[groups.size - 1] = JsonObject(groups.last() + ("node_runtime" to node))
            }
        }
        problems.addAll(
            CorpusVerification.nodeObservationProblems(repository, evidenceRoot, binding, started, finished),
        )
        return buildJsonObject {
            put("schema", JsonPrimitive(if (Py.equalsInt(binding["schema"], 2)) 2 else 1))
            put("kind", JsonPrimitive("full-common-corpus-verification"))
            put("candidate_sha", JsonPrimitive(candidateSha))
            put("source_tree_sha256", manifest["source_tree_sha256"] ?: JsonNull)
            put("manifest_sha256", JsonPrimitive(FullCorpus.canonicalDigest(manifest)))
            put("status", JsonPrimitive(if (problems.isEmpty()) "PASSED" else "UNPASSED"))
            put("problems", JsonArray(problems.map { JsonPrimitive(it) }))
            put("total_cases", JsonPrimitive(total))
            put("mapped_original_methods", counts["mapped_original_methods"] ?: JsonNull)
            put("reviewed_source_linked_methods", counts["reviewed_source_linked_methods"] ?: JsonNull)
            put("supplemental_cases", counts["supplemental_methods"] ?: JsonNull)
            put("platform_only_cases", counts["platform_only_methods"] ?: JsonNull)
            put("jvm_only_original_identities", counts["jvm_only_original_identities"] ?: JsonNull)
            put("groups", JsonArray(groups))
        }
    }

    /** `package_archive`: seal a verified run into a reproducible archive. */
    fun packageArchive(
        repository: Path,
        archive: Path,
        manifest: JsonObject,
        mapping: List<JsonObject>,
        candidateSha: String,
        binding: JsonObject,
        reports: Map<String, List<Path>>,
        upstream: Path? = null,
        requireCheckout: Boolean = false,
        manifestPath: Path? = null,
        mappingPath: Path? = null,
    ): JsonObject {
        val result = verifyReports(
            repository, manifest, candidateSha, binding, reports,
            mapping = mapping, upstream = upstream, requireCheckout = requireCheckout,
            manifestPath = manifestPath, mappingPath = mappingPath,
        )
        if (Py.str(result["status"]) != "PASSED") {
            throw IllegalArgumentException(
                "complete common corpus did not verify: " +
                    ((result["problems"] as? JsonArray)?.joinToString("; ") { Py.str(it) ?: "" } ?: ""),
            )
        }
        Files.createDirectories(archive)
        val evidence = archive.resolve("evidence")
        if (Files.exists(evidence)) {
            throw IllegalArgumentException("archive evidence directory already exists")
        }
        Files.createDirectory(evidence)

        fun write(name: String, data: ByteArray) {
            val target = evidence.resolve(FullCorpus.archiveRelative(name))
            if (Files.exists(target)) throw IllegalArgumentException("duplicate archive path: $name")
            target.parent?.let { Files.createDirectories(it) }
            Files.write(target, data)
        }

        fun copy(name: String, source: Path) {
            val target = evidence.resolve(FullCorpus.archiveRelative(name))
            if (Files.exists(target) || Files.isSymbolicLink(source) || !Files.isRegularFile(source)) {
                throw IllegalArgumentException("missing, linked, or duplicate archive input: $name")
            }
            target.parent?.let { Files.createDirectories(it) }
            Files.copy(source, target, StandardCopyOption.COPY_ATTRIBUTES)
        }

        val manifestBytes = if (manifestPath != null) {
            Files.readAllBytes(manifestPath)
        } else {
            (PyJson.renderSorted(manifest) + "\n").toByteArray(StandardCharsets.UTF_8)
        }
        val mappingBytes = if (mappingPath != null) {
            Files.readAllBytes(mappingPath)
        } else {
            val out = StringBuilder()
            val fields = mapping.firstOrNull()?.keys?.toList() ?: FullCorpus.PAIR_FIELDS
            out.append(fields.joinToString("\t") { CorpusTsv.field(it) }).append('\n')
            for (row in mapping) {
                out.append(
                    fields.joinToString("\t") { field ->
                        CorpusTsv.field(row[field]?.let { Py.str(it) ?: CanonicalText.of(it) })
                    },
                ).append('\n')
            }
            out.toString().toByteArray(StandardCharsets.UTF_8)
        }
        write("binding.json", (PyJson.renderSorted(binding) + "\n").toByteArray())
        write("manifest.json", manifestBytes)
        write("mapping.tsv", mappingBytes)
        write("mapping.json", (PyJson.renderSorted(JsonArray(mapping)) + "\n").toByteArray())
        write("verified.json", (PyJson.renderSorted(result) + "\n").toByteArray())
        if (Py.str(manifest["policy"]) == "production") {
            copy("reviewed-pairs.tsv", repository.resolve(FullCorpus.PAIR_PATH))
        }
        val log = Path.of(Py.str(binding["log"]) ?: "")
        copy("gradle.log", if (log.isAbsolute) log else repository.resolve(log))
        val artifacts = binding["artifacts"] as? JsonArray ?: JsonArray(emptyList())
        for (element in artifacts) {
            val name = Py.str((element as JsonObject)["path"])!!
            copy(name, repository.resolve(FullCorpus.archiveRelative(name)))
        }
        val boundReports = binding["reports"] as? JsonObject ?: JsonObject(emptyMap())
        for (bound in boundReports.values) {
            for (name in (bound as? JsonObject)?.keys ?: emptySet()) {
                copy(name, repository.resolve(FullCorpus.archiveRelative(name)))
            }
        }
        if (Py.equalsInt(binding["schema"], 2)) {
            val observationDir = Path.of(Py.str(binding["node_observation_dir"]) ?: "")
            val loaderPaths = mutableSetOf<String>()
            for (element in binding["node_observations"] as? JsonArray ?: JsonArray(emptyList())) {
                val row = element as JsonObject
                val requestName = Py.str(row["request_name"])!!
                for (name in listOf(requestName, requestName.removeSuffix(".json") + ".ack")) {
                    copy("node-observations/$name", observationDir.resolve(name))
                }
                copy(Py.str(row["payload_path"])!!, repository.resolve(FullCorpus.archiveRelative(Py.str(row["payload_path"]))))
                Py.str(row["launch_loader_path"])?.let { loaderPaths.add(it) }
            }
            for (name in loaderPaths.sortedWith(CanonicalText::compare)) {
                copy(name, repository.resolve(FullCorpus.archiveRelative(name)))
            }
        }
        val files = LinkedHashMap<String, JsonElement>()
        val archiveEntries = Files.walk(archive).use { stream ->
            stream.toList()
        }.sortedWith { left, right -> CanonicalText.compare(left.toString(), right.toString()) }
        for (path in archiveEntries) {
            if (Files.isSymbolicLink(path)) throw IllegalArgumentException("linked archive input: $path")
            if (Files.isRegularFile(path) && path != archive.resolve("archive-index.json")) {
                val name = archive.relativize(path).toString().replace('\\', '/')
                files[name] = buildJsonObject {
                    put("sha256", JsonPrimitive(CorpusFiles.digest(path)))
                    put("mtime_ns", JsonPrimitive(Files.getLastModifiedTime(path).to(TimeUnit.NANOSECONDS)))
                }
            }
        }
        val index = buildJsonObject {
            put("schema", JsonPrimitive(1))
            put("kind", JsonPrimitive("full-common-archive"))
            put("candidate_sha", JsonPrimitive(candidateSha))
            put(
                "original_revision",
                if (upstream != null) JsonPrimitive(FullCorpus.ORIGINAL_REVISION) else JsonNull,
            )
            put(
                "bound_artifacts",
                JsonArray(
                    artifacts.map { Py.str((it as JsonObject)["path"])!! }
                        .sortedWith(CanonicalText::compare)
                        .map { JsonPrimitive(it) },
                ),
            )
            put(
                "bound_reports",
                JsonObject(
                    boundReports.mapValues { (_, value) ->
                        JsonArray(
                            ((value as JsonObject).keys).sortedWith(CanonicalText::compare)
                                .map { JsonPrimitive(it) },
                        )
                    },
                ),
            )
            put("files", JsonObject(files))
        }
        Fs.writeText(archive.resolve("archive-index.json"), PyJson.renderSorted(index) + "\n")
        return index
    }

    /** `verify_archive`: a downloaded corpus archive must reproduce its own index and receipts. */
    fun verifyArchive(
        archive: Path,
        repository: Path,
        candidateSha: String,
        upstream: Path? = null,
        requireCheckout: Boolean = true,
    ): JsonObject {
        val problems = mutableListOf<String>()
        try {
            val index = StrictJson.load(Fs.readText(archive.resolve("archive-index.json"))) as JsonObject
            if (!Py.equalsInt(index["schema"], 1) || Py.str(index["kind"]) != "full-common-archive" ||
                Py.str(index["candidate_sha"]) != candidateSha
            ) {
                problems.add("archive candidate SHA or schema differs")
            }
            if (requireCheckout && Py.str(index["original_revision"]) != FullCorpus.ORIGINAL_REVISION) {
                problems.add("archive original revision differs")
            }
            val actual = LinkedHashMap<String, Path>()
            val entries = Files.walk(archive).use { it.toList() }
            for (path in entries) {
                val name = archive.relativize(path).toString().replace('\\', '/')
                FullCorpus.archiveRelative(name)
                if (Files.isSymbolicLink(path)) {
                    problems.add("linked archive member: $name")
                } else if (Files.isRegularFile(path) && name != "archive-index.json") {
                    actual[name] = path
                }
            }
            val recorded = index["files"] as? JsonObject
            if (recorded == null || recorded.keys != actual.keys) {
                problems.add("archive file inventory differs")
            } else {
                for ((name, path) in actual) {
                    val item = (recorded as? JsonObject)?.get(name) as? JsonObject
                    if (item == null || Py.str(item["sha256"]) != CorpusFiles.digest(path) ||
                        !Py.isInt(item["mtime_ns"]) || Py.int(item["mtime_ns"]) <= 0
                    ) {
                        problems.add("archive byte or timestamp receipt differs: $name")
                    }
                }
            }
            if (problems.isNotEmpty()) return FullCorpus.archiveStatus(candidateSha, problems)
            val evidence = archive.resolve("evidence")
            val binding = StrictJson.load(Fs.readText(evidence.resolve("binding.json"))) as JsonObject
            val manifest = StrictJson.load(Fs.readText(evidence.resolve("manifest.json"))) as JsonObject
            val mapping = (StrictJson.load(Fs.readText(evidence.resolve("mapping.json"))) as JsonArray)
                .mapNotNull { it as JsonObject }
            val expected = mutableSetOf(
                "binding.json", "manifest.json", "mapping.tsv", "mapping.json", "verified.json",
                "gradle.log",
            )
            if (Py.str(manifest["policy"]) == "production") {
                expected.add("reviewed-pairs.tsv")
                if (CorpusTsv.read(Files.readAllBytes(evidence.resolve("mapping.tsv"))) != mapping) {
                    problems.add("archive mapping content differs")
                }
                for ((archiveName, repoName) in listOf(
                    "manifest.json" to FullCorpus.MANIFEST_PATH,
                    "mapping.tsv" to FullCorpus.MAP_PATH,
                    "reviewed-pairs.tsv" to FullCorpus.PAIR_PATH,
                )) {
                    if (!Files.readAllBytes(evidence.resolve(archiveName)).contentEquals(
                            CorpusFiles.committedBytes(repository, candidateSha, repoName),
                        )
                    ) {
                        problems.add("archive candidate source differs: $repoName")
                    }
                }
            }
            val artifacts = (binding["artifacts"] as? JsonArray)?.mapNotNull { it as? JsonObject } ?: emptyList()
            val boundReports = binding["reports"] as? JsonObject ?: JsonObject(emptyMap())
            val sortedArtifacts = artifacts.map { Py.str(it["path"])!! }.sortedWith(CanonicalText::compare)
            val sortedBound = boundReports.mapValues { (_, value) ->
                JsonArray(((value as JsonObject).keys).sortedWith(CanonicalText::compare).map { JsonPrimitive(it) })
            }
            val indexArtifacts = index["bound_artifacts"] as? JsonArray
            if (indexArtifacts?.mapNotNull { Py.str(it) } != sortedArtifacts ||
                index["bound_reports"] != JsonObject(sortedBound)
            ) {
                problems.add("archive binding inventory differs")
            }
            expected.addAll(sortedArtifacts)
            expected.addAll(sortedBound.values.flatMap { array ->
                (array as JsonArray).mapNotNull { Py.str(it) }
            })
            if (Py.equalsInt(binding["schema"], 2)) {
                for (element in binding["node_observations"] as? JsonArray ?: JsonArray(emptyList())) {
                    val row = element as JsonObject
                    expected.add(Py.str(row["payload_path"])!!)
                    Py.str(row["launch_loader_path"])?.let { expected.add(it) }
                    expected.add("node-observations/" + Py.str(row["request_name"])!!)
                    expected.add(
                        "node-observations/" + Py.str(row["request_name"])!!.removeSuffix(".json") + ".ack",
                    )
                }
            }
            val started = if (Py.isInt(binding["started_ns"])) Py.int(binding["started_ns"]) else null
            val finished = if (Py.isInt(binding["finished_ns"])) Py.int(binding["finished_ns"]) else null
            val timed = sortedArtifacts.toMutableList()
            timed.addAll(sortedBound.values.flatMap { array -> (array as JsonArray).mapNotNull { Py.str(it) } })
            if (Py.equalsInt(binding["schema"], 2)) {
                for (element in binding["node_observations"] as? JsonArray ?: JsonArray(emptyList())) {
                    timed.add(Py.str((element as JsonObject)["payload_path"])!!)
                }
            }
            for (name in timed) {
                val item = (recorded as? JsonObject)?.get(name) as? JsonObject
                val mtime = item?.let { if (Py.isInt(it["mtime_ns"])) Py.int(it["mtime_ns"]) else null }
                if (started == null || finished == null || mtime == null ||
                    mtime < started || mtime > finished
                ) {
                    problems.add("archive invocation timestamp differs: $name")
                }
            }
            val actualEvidence = Files.walk(evidence).use { stream ->
                stream.filter { Files.isRegularFile(it) }
                    .map { evidence.relativize(it).toString().replace('\\', '/') }
                    .toList()
            }.toSet()
            if (actualEvidence != expected) problems.add("archive evidence file set differs")
            for (name in expected) FullCorpus.archiveRelative(name)
            if (problems.isNotEmpty()) return FullCorpus.archiveStatus(candidateSha, problems)
            val reports = FullCorpus.GROUPS.associate { group ->
                group.id to ((boundReports[group.id] as? JsonObject)?.keys ?: emptySet())
                    .map { evidence.resolve(FullCorpus.archiveRelative(it)) }
            }
            val corpus = verifyReports(
                repository, manifest, candidateSha, binding, reports,
                mapping = mapping, upstream = upstream, requireCheckout = requireCheckout,
                manifestPath = if (requireCheckout) repository.resolve(FullCorpus.MANIFEST_PATH) else null,
                mappingPath = if (requireCheckout) repository.resolve(FullCorpus.MAP_PATH) else null,
                evidenceRootInput = evidence,
            )
            if (Py.str(corpus["status"]) != "PASSED") {
                problems.addAll((corpus["problems"] as? JsonArray)?.mapNotNull { Py.str(it) } ?: emptyList())
            }
            if (StrictJson.load(Fs.readText(evidence.resolve("verified.json"))) != corpus) {
                problems.add("archive verification receipt differs")
            }
            return FullCorpus.archiveStatus(candidateSha, problems, corpus)
        } catch (error: Exception) {
            return FullCorpus.archiveStatus(candidateSha, listOf("archive unavailable or invalid: ${error.message}"))
        }
    }

    private fun relativeText(root: Path, path: Path): String =
        root.relativize(path).toString().replace('\\', '/')

    private fun git(repository: Path, vararg arguments: String): String {
        val process = ProcessBuilder(listOf("git", "-C", repository.toString()) + arguments).start()
        val output = process.inputStream.use { it.readBytes() }
        val error = process.errorStream.use { it.readBytes() }
        if (process.waitFor() != 0) {
            throw IllegalArgumentException(error.toString(StandardCharsets.UTF_8).trim())
        }
        return output.toString(StandardCharsets.UTF_8)
    }

    private fun suiteOf(raw: ByteArray): Element {
        val factory = DocumentBuilderFactory.newInstance()
        factory.isNamespaceAware = false
        val builder = factory.newDocumentBuilder()
        builder.setErrorHandler(
            object : org.xml.sax.ErrorHandler {
                override fun warning(exception: org.xml.sax.SAXParseException) = Unit
                override fun error(exception: org.xml.sax.SAXParseException) = throw exception
                override fun fatalError(exception: org.xml.sax.SAXParseException) = throw exception
            },
        )
        return builder.parse(raw.inputStream()).documentElement
    }

    private fun elementsNamed(root: Element, name: String): List<Element> {
        val nodes = root.getElementsByTagName(name)
        return (0 until nodes.length).map { nodes.item(it) as Element }
    }

    private fun childNamed(element: Element, name: String): Element? {
        var node: Node? = element.firstChild
        while (node != null) {
            if (node.nodeType == Node.ELEMENT_NODE && (node as Element).tagName == name) return node
            node = node.nextSibling
        }
        return null
    }

    private fun comparePairs(left: Pair<String, String>, right: Pair<String, String>): Int {
        val first = CanonicalText.compare(left.first, right.first)
        return if (first != 0) first else CanonicalText.compare(left.second, right.second)
    }

    private fun pairList(values: List<Pair<String, String>>): String =
        values.joinToString(", ", prefix = "[", postfix = "]") { pair ->
            "(" + Py.quote(pair.first) + ", " + Py.quote(pair.second) + ")"
        }
}
