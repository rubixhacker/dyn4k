package io.github.rubixhacker.harness.qualification

import io.github.rubixhacker.harness.contract.Sha256
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.LinkOption
import java.nio.file.Path
import java.util.concurrent.TimeUnit
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject

/** Minimal TSV reader and writer with Python's `csv` quoting rules for the reviewed files. */
object CorpusTsv {
    fun read(bytes: ByteArray): List<JsonObject> {
        val text = bytes.toString(StandardCharsets.UTF_8)
        val lines = text.split('\n').filter { it.isNotEmpty() }
        if (lines.isEmpty()) return emptyList()
        val header = fields(lines.first(), '\t')
        return lines.drop(1).map { line ->
            val values = fields(line.trimEnd('\r'), '\t')
            JsonObject(
                header.mapIndexed { index, key -> key to JsonPrimitive(values.getOrElse(index) { "" }) }
                    .toMap(LinkedHashMap()),
            )
        }
    }

    private fun fields(line: String, delimiter: Char): List<String> {
        val result = mutableListOf<String>()
        val current = StringBuilder()
        var index = 0
        var quoted = false
        while (index < line.length) {
            val char = line[index]
            when {
                quoted && char == '"' && index + 1 < line.length && line[index + 1] == '"' -> {
                    current.append('"')
                    index += 2
                    continue
                }
                char == '"' -> quoted = !quoted
                char == delimiter && !quoted -> {
                    result.add(current.toString())
                    current.setLength(0)
                }
                else -> current.append(char)
            }
            index++
        }
        result.add(current.toString())
        return result
    }

    fun field(value: String?, delimiter: Char = '\t'): String {
        if (value == null) return ""
        val needsQuote = value.any { it == delimiter || it == '"' || it == '\n' || it == '\r' }
        if (!needsQuote) return value
        return "\"" + value.replace("\"", "\"\"") + "\""
    }
}

/**
 * `full_corpus.py` filesystem work: corpus scanning, environment capture, artifact capture,
 * reviewed provenance, and live Node request observation.
 */
object CorpusFiles {
    /** `digest`: SHA-256 of the bytes. */
    fun digest(bytes: ByteArray): String = Sha256.of(bytes)

    fun digest(path: Path): String = Fs.digest(path)

    /** `committed_bytes`: one committed file of a revision. */
    fun committedBytes(repository: Path, revision: String, path: String): ByteArray {
        val process = ProcessBuilder(
            "git", "-C", repository.toString(), "show", "$revision:$path",
        ).start()
        val output = process.inputStream.use { it.readBytes() }
        process.errorStream.close()
        if (process.waitFor() != 0) {
            throw IllegalArgumentException("committed input is unavailable: $path")
        }
        return output
    }

    /** `candidate_checkout_problems`: the checkout must be the candidate, clean, and reviewed. */
    fun candidateCheckoutProblems(repository: Path, candidateSha: String): List<String> {
        val problems = mutableListOf<String>()
        val head = git(repository, "rev-parse", "HEAD").trim()
        if (head != candidateSha) problems.add("candidate SHA differs from checkout")
        val tracked = git(repository, "status", "--porcelain=v1", "--untracked-files=no").trim()
        if (tracked.isNotEmpty()) {
            problems.add("tracked candidate tree is dirty: " + tracked.take(300))
        }
        val untracked = mutableSetOf<String>()
        for (ignored in listOf(false, true)) {
            val command = mutableListOf(
                "git", "-C", repository.toString(), "ls-files", "--others", "--exclude-standard", "-z",
            )
            if (ignored) command.add("--ignored")
            val raw = run(command).toString(StandardCharsets.UTF_8)
            untracked.addAll(raw.split('\u0000').filter { it.isNotEmpty() })
        }
        for (path in untracked.sortedWith(CanonicalText::compare)) {
            if (!FullCorpus.allowedGeneratedPath(path)) {
                problems.add("untracked candidate input: $path")
            }
        }
        return problems
    }

    private fun git(repository: Path, vararg arguments: String): String =
        run(listOf("git", "-C", repository.toString()) + arguments).toString(StandardCharsets.UTF_8)

    private fun run(command: List<String>): ByteArray {
        val process = ProcessBuilder(command).start()
        val output = process.inputStream.use { it.readBytes() }
        val error = process.errorStream.use { it.readBytes() }
        if (process.waitFor() != 0) {
            throw IllegalArgumentException(
                "${command.joinToString(" ")} failed: ${error.toString(StandardCharsets.UTF_8).trim()}",
            )
        }
        return output
    }

    /** `executable_identity`: one tool binary, pinned by digest, size, and timestamp. */
    fun executableIdentity(path: String, size: Long, modifiedNs: Long): JsonObject = buildJsonObject {
        put("path", JsonPrimitive(path))
        put("sha256", JsonPrimitive(digest(Path.of(path))))
        put("size", JsonPrimitive(size))
        put("modified_ns", JsonPrimitive(modifiedNs))
    }

    /** `capture_environment`: the host tool identities a candidate run is recorded against. */
    fun captureEnvironment(repository: Path): JsonObject {
        val executables = LinkedHashMap<String, JsonElement>()
        for ((name, command) in listOf("java" to listOf("-version"), "node" to listOf("--version"))) {
            val found = which(name) ?: run {
                executables[name] = kotlinx.serialization.json.JsonNull
                continue
            }
            val path = found.toRealPath()
            val identity = LinkedHashMap<String, JsonElement>()
            identity.putAll((executableIdentity(path.toString(), Files.size(path), modifiedNs(path))) as JsonObject)
            val completed = ProcessBuilder(listOf(path.toString()) + command)
                .redirectErrorStream(false)
                .start()
            val stdout = completed.inputStream.use { it.readBytes() }
            val stderr = completed.errorStream.use { it.readBytes() }
            val status = completed.waitFor()
            identity["version"] = JsonPrimitive(
                (stdout.toString(StandardCharsets.UTF_8) + stderr.toString(StandardCharsets.UTF_8)).trim(),
            )
            identity["exit_code"] = JsonPrimitive(status)
            executables[name] = JsonObject(identity)
        }
        val wrapper = LinkedHashMap<String, JsonElement>()
        for (relative in listOf(
            "gradlew", "gradle/wrapper/gradle-wrapper.jar", "gradle/wrapper/gradle-wrapper.properties",
        )) {
            val path = repository.resolve(relative)
            wrapper[relative] = if (Files.isRegularFile(path)) {
                JsonPrimitive(digest(path))
            } else {
                kotlinx.serialization.json.JsonNull
            }
        }
        val androidHome = System.getenv("ANDROID_HOME")
        val sdk = androidHome?.let { Path.of(it).resolve("source.properties") }
        return buildJsonObject {
            put("system", JsonPrimitive(System.getProperty("os.name")))
            put("machine", JsonPrimitive(machine()))
            put("java_home", System.getenv("JAVA_HOME")?.let { JsonPrimitive(it) } ?: kotlinx.serialization.json.JsonNull)
            put("android_home", androidHome?.let { JsonPrimitive(it) } ?: kotlinx.serialization.json.JsonNull)
            put(
                "android_sdk_source_sha256",
                if (sdk != null && Files.isRegularFile(sdk)) JsonPrimitive(digest(sdk))
                else kotlinx.serialization.json.JsonNull,
            )
            put("executables", JsonObject(executables))
            put("gradle_wrapper", JsonObject(wrapper))
        }
    }

    /** `platform.machine()` in the JVM's spelling. */
    private fun machine(): String = when (val arch = System.getProperty("os.arch")) {
        "amd64" -> "x86_64"
        else -> arch
    }

    private fun modifiedNs(path: Path): Long =
        Files.getLastModifiedTime(path).to(TimeUnit.NANOSECONDS)

    private fun which(name: String): Path? {
        val path = System.getenv("PATH") ?: return null
        for (directory in path.split(':')) {
            if (directory.isEmpty()) continue
            val candidate = Path.of(directory).resolve(name)
            if (Files.isRegularFile(candidate) && Files.isExecutable(candidate)) return candidate
        }
        return null
    }

    /** `capture_artifacts`: build outputs written during the invocation window. */
    fun captureArtifacts(repository: Path, startedNs: Long, finishedNs: Long): JsonArray = buildJsonArray {
        for (module in FullCorpus.MODULES) {
            val root = repository.resolve(module).resolve("build")
            if (!Files.isDirectory(root)) continue
            val paths = Files.walk(root).use { stream ->
                stream.filter { Files.isRegularFile(it) }.toList()
            }.sortedWith { left, right -> CanonicalText.compare(left.toString(), right.toString()) }
            for (path in paths) {
                val suffix = path.fileName.toString().substringAfterLast('.', "")
                if (".$suffix" !in FullCorpus.ARTIFACT_SUFFIXES) continue
                val modified = modifiedNs(path)
                if (modified < startedNs || modified > finishedNs) continue
                add(
                    buildJsonObject {
                        put("module", JsonPrimitive(module))
                        put(
                            "path",
                            JsonPrimitive(repository.relativize(path).toString().replace('\\', '/')),
                        )
                        put("sha256", JsonPrimitive(digest(path)))
                    },
                )
            }
        }
    }

    /** `scan_sources`: every `@Test` method of the common and JVM test sources. */
    fun scanSources(repository: Path): List<CorpusCase> {
        val cases = mutableListOf<CorpusCase>()
        for (module in FullCorpus.MODULES) {
            for (sourceSet in listOf("commonTest", "jvmTest")) {
                val root = repository.resolve(module).resolve("src").resolve(sourceSet).resolve("kotlin")
                if (!Files.isDirectory(root)) continue
                val paths = Files.walk(root).use { stream ->
                    stream.filter { it.fileName.toString().endsWith(".kt") && Files.isRegularFile(it) }
                        .toList()
                }.sortedWith { left, right -> CanonicalText.compare(left.toString(), right.toString()) }
                for (path in paths) {
                    val raw = Files.readAllBytes(path)
                    val relative = repository.relativize(path).toString().replace('\\', '/')
                    cases.addAll(
                        FullCorpus.scanKotlin(
                            module, sourceSet, relative, raw.toString(StandardCharsets.UTF_8), digest(raw),
                        ),
                    )
                }
            }
        }
        if (cases.isEmpty()) throw IllegalArgumentException("empty or duplicate common test inventory")
        val identities = cases.map { Triple(it.module, it.classname, it.method) }
        if (identities.toSet().size != identities.size) {
            throw IllegalArgumentException("empty or duplicate common test inventory")
        }
        return cases.sortedWith { left, right ->
            var comparison = CanonicalText.compare(left.module, right.module)
            if (comparison == 0) comparison = CanonicalText.compare(left.classname, right.classname)
            if (comparison == 0) comparison = CanonicalText.compare(left.method, right.method)
            comparison
        }
    }

    /** `scan_test_tree`: every file of the seven test source sets, with its digest. */
    fun scanTestTree(repository: Path): List<JsonObject> {
        val files = mutableListOf<JsonObject>()
        for (module in FullCorpus.MODULES) {
            for (sourceSet in listOf(
                "commonTest", "jvmTest", "androidHostTest", "jsTest",
                "nativeTest", "wasmJsTest", "wasmWasiTest",
            )) {
                val root = repository.resolve(module).resolve("src").resolve(sourceSet)
                if (!Files.isDirectory(root)) continue
                val paths = Files.walk(root).use { stream ->
                    stream.filter { Files.isRegularFile(it) }.toList()
                }.sortedWith { left, right -> CanonicalText.compare(left.toString(), right.toString()) }
                for (path in paths) {
                    files.add(
                        buildJsonObject {
                            put(
                                "path",
                                JsonPrimitive(repository.relativize(path).toString().replace('\\', '/')),
                            )
                            put("sha256", JsonPrimitive(digest(path)))
                        },
                    )
                }
            }
        }
        return files.sortedWith { left, right ->
            CanonicalText.compare(Py.str(left["path"])!!, Py.str(right["path"])!!)
        }
    }

    /** `review_provenance`: the reviewed report that justifies one mapping disposition. */
    fun reviewProvenance(repository: Path, owner: String?, sourceClass: String, reference: String? = null): Pair<String, String> {
        val path = when {
            reference != null -> reference
            owner == "pending_core_combined" -> {
                val name = sourceClass.substringAfterLast('.')
                val shapes = setOf(
                    "AbstractShapeTest", "PolygonTest", "TriangleTest", "LinkTest",
                    "CapsuleTest", "EllipseTest", "HalfEllipseTest", "SliceTest",
                    "CircleTest", "RectangleTest", "RayTest", "SegmentTest",
                    "MassTest", "IntervalTest", "AABBTest", "FeatureTest",
                    "WoundTest", "RobustGeometryTest",
                )
                val document = when {
                    name == "GeometryTest" -> "portable-geometry-factory.md"
                    name in shapes -> "portable-geometry-shapes.md"
                    else -> "portable-foundation-coverage.md"
                }
                "docs/verification/$document"
            }
            else -> "docs/verification/" + (
                FullCorpus.REVIEW_DOCS[owner]
                    ?: throw IllegalArgumentException("unknown reviewed report owner: $owner")
                )
        }
        val file = repository.resolve(path)
        if (!Files.isRegularFile(file)) throw IllegalArgumentException("missing reviewed report: $path")
        return path to digest(file)
    }

    /** `reconcile_originals`: rebuild the reviewed original map from the pinned audit. */
    fun reconcileOriginals(repository: Path, upstream: Path, audit: Path): List<JsonObject> {
        val revision = git(upstream, "rev-parse", "HEAD").trim()
        if (revision != FullCorpus.ORIGINAL_REVISION) {
            throw IllegalArgumentException("upstream source revision differs from pinned baseline")
        }
        val rows = CorpusTsv.read(Files.readAllBytes(audit))
        if (rows.size != 2385 || rows.map { Py.str(it["original_identity"]) }.toSet().size != 2385) {
            throw IllegalArgumentException("reviewed original audit must have 2,385 unique executions")
        }
        val cases = scanSources(repository).filter { it.module == "dyn4k-core" }
        val byShort = LinkedHashMap<Pair<String, String>, MutableList<CorpusCase>>()
        for (case in cases) {
            byShort.getOrPut(case.classname.substringAfterLast('.') to case.method) { mutableListOf() }.add(case)
        }
        val overrides = LinkedHashMap<String, Pair<String, String>>()
        val detection = repository.resolve(
            "dyn4k-core/src/commonTest/kotlin/org/dyn4j/coverage/collision/detection/resources/source-case-map.tsv",
        )
        for (row in CorpusTsv.read(Files.readAllBytes(detection))) {
            if (Py.str(row["disposition"]) == "PORTABLE") {
                overrides[Py.str(row["original_case"])!!] = (
                    Py.str(row["portable_case"])!!.replace("#", ".") to
                        repository.relativize(detection).toString().replace('\\', '/')
                    )
            }
        }
        val support = repository.resolve("docs/verification/portable-world-support-contact.md")
        for (line in Files.readAllLines(support)) {
            val columns = line.split("|")
            if (columns.size < 4) continue
            val original = Regex("`(org\\.dyn4j\\.[\\w.]+)`").find(columns[1])
            val target = Regex("`(org\\.dyn4j\\.[\\w.]+)`").find(columns[2])
            if (original != null && target != null && "Test." in original.groupValues[1]) {
                val value = original.groupValues[1]
                val sourceClass = value.substringBeforeLast('.')
                val method = value.substringAfterLast('.')
                overrides["$sourceClass#$method"] = (
                    target.groupValues[1] to repository.relativize(support).toString().replace('\\', '/')
                    )
            }
        }
        val mappings = mutableListOf<JsonObject>()
        for (row in rows) {
            val original = Py.str(row["original_identity"])!!
            val sourceClass = original.substringBefore('#')
            val expandedMethod = original.substringAfter('#')
            val method = expandedMethod.substringBefore('[')
            val sourcePath = "src/test/java/" + sourceClass.replace(".", "/") + ".java"
            val sourceFile = upstream.resolve(sourcePath)
            if (!Files.isRegularFile(sourceFile)) {
                throw IllegalArgumentException("missing pinned Java source: $sourcePath")
            }
            val sourceBytes = Files.readAllBytes(sourceFile)
            val java = FullCorpus.maskNoncode(sourceBytes.toString(StandardCharsets.UTF_8))
            val function = Regex("\\bvoid\\s+" + Regex.escape(method) + "\\s*\\(").find(java)
            val line = function?.let { java.substring(0, it.range.first).count { char -> char == '\n' } + 1L } ?: 0L
            val item = LinkedHashMap<String, JsonElement>()
            item["original"] = JsonPrimitive(original)
            item["original_source"] = JsonPrimitive(sourcePath)
            item["original_sha256"] = JsonPrimitive(digest(sourceBytes))
            item["original_line"] = JsonPrimitive(line)
            item["disposition"] = JsonPrimitive(
                if (Py.str(row["disposition"]) == "JVM_ONLY") "JVM_ONLY" else "UNMAPPED",
            )
            item["review"] = row["owner"] ?: JsonPrimitive("")
            if (Py.str(row["disposition"]) == "JVM_ONLY") {
                item["reason"] = JsonPrimitive(FullCorpus.jvmOnlyReason(original))
                val (review, sha) = reviewProvenance(repository, Py.str(row["owner"]), sourceClass)
                item["review"] = JsonPrimitive(review)
                item["review_sha256"] = JsonPrimitive(sha)
                mappings.add(JsonObject(item))
                continue
            }
            var selected: CorpusCase? = null
            var reference: String? = null
            var direct: String? = if (Py.str(row["disposition"]) == "PORTABLE") {
                Py.str(row["counterpart_or_reason"])
            } else {
                null
            }
            val override = overrides[original]
            if (override != null) {
                direct = override.first
                reference = override.second
            } else if (sourceClass == "org.dyn4j.geometry.GeometryTest") {
                direct = "GeometryFactoryCoverageTest.$method"
                reference = "docs/verification/portable-geometry-factory.md"
            }
            if (direct != null) {
                val names = Regex("(?:[A-Za-z_]\\w*\\.)+[A-Za-z_]\\w*").findAll(direct).toList()
                if (names.isNotEmpty()) {
                    val value = names.first().value
                    val classname = value.substringBeforeLast('.')
                    val targetMethod = value.substringAfterLast('.')
                    var candidates = byShort[classname.substringAfterLast('.') to targetMethod] ?: mutableListOf()
                    if ("." in classname && classname.startsWith("org.")) {
                        candidates = candidates.filter { it.classname == classname }.toMutableList()
                    }
                    if (candidates.size == 1) selected = candidates.first()
                }
            }
            if (selected == null) {
                val candidates = cases.filter { it.method == method }
                val originalShort = sourceClass.substringAfterLast('.')
                val originalStem = originalShort.removeSuffix("Test").removePrefix("Abstract")
                val ranked = mutableListOf<Pair<Int, CorpusCase>>()
                for (case in candidates) {
                    val short = case.classname.substringAfterLast('.')
                    val stem = short.removeSuffix("Test").removeSuffix("Coverage")
                        .removeSuffix("Core").removePrefix("Upstream").removePrefix("Abstract")
                    var score = 0
                    if (short == originalShort) {
                        score = 5
                    } else if (stem == originalStem) {
                        score = 4
                    } else if (short in setOf("CollisionWorldCoreCoverageTest", "PhysicsWorldCoreCoverageTest")) {
                        if (originalShort in setOf("AbstractCollisionWorldTest", "AbstractPhysicsWorldTest") &&
                            stem == originalStem.removeSuffix("World") + "World"
                        ) {
                            score = 3
                        }
                    }
                    if (score != 0) ranked.add(score to case)
                }
                if (ranked.isNotEmpty()) {
                    val highest = ranked.maxOf { it.first }
                    val leaders = ranked.filter { it.first == highest }.map { it.second }
                    if (leaders.size == 1) selected = leaders.first()
                }
            }
            if (selected != null) {
                item["disposition"] = JsonPrimitive("PORTABLE")
                item["classname"] = JsonPrimitive(selected.classname)
                item["method"] = JsonPrimitive(selected.method)
                item["review"] = JsonPrimitive(reference ?: (Py.str(row["owner"]) ?: ""))
            } else {
                item["reason"] = JsonPrimitive("no unique reviewed common destination")
            }
            val (review, sha) = reviewProvenance(repository, Py.str(row["owner"]), sourceClass, reference)
            item["review"] = JsonPrimitive(review)
            item["review_sha256"] = JsonPrimitive(sha)
            mappings.add(JsonObject(item))
        }
        return mappings
    }

    /**
     * `observe_node_request`: turn one live Node startup request into an observation row.
     *
     * The request file is written by the startup probe; the live process image, ancestry, and
     * version are read from `/proc`, so the row binds what actually ran.
     */
    fun observeNodeRequest(
        repository: Path,
        requestFile: Path,
        gradlePid: Long,
        gradleStartTicks: Long?,
        startedNs: Long,
    ): JsonObject {
        if (Files.isSymbolicLink(requestFile) || Files.size(requestFile) > 8192) {
            throw ObservationError("Node request is linked or oversized")
        }
        val raw = Files.readAllBytes(requestFile)
        val request = StrictObjectJson.parse(raw.toString(StandardCharsets.UTF_8)) as? JsonObject
            ?: throw ObservationError("Node request is not an object")
        val pid = Py.int(request["pid"])
        val nonce = Py.str(request["nonce"]) ?: ""
        if (pid <= 0 || !Regex("[0-9a-f]{32}").matches(nonce) ||
            requestFile.fileName.toString() != "$pid-$nonce.json"
        ) {
            throw ObservationError("Node request identity differs")
        }
        val observedNs = System.currentTimeMillis() * 1_000_000
        val image = LinuxObserver.image(pid)
        val normalized = FullCorpus.nodeProcessArgv(repository.toString(), strings(image["argv"]))
        val requested = strings(request["argv"])
        if (normalized.drop(1) != requested.drop(1) ||
            Path.of(normalized.first()).toAbsolutePath() != Path.of(requested.first()).toAbsolutePath()
        ) {
            throw ObservationError("live Node command differs from request")
        }
        val selection = FullCorpus.nodeGroupForArgv(repository.toString(), strings(image["argv"]))
            ?: throw ObservationError("Node command is not a selected test runner")
        val (groupId, payloadPath) = selection
        if (Path.of(Py.str(request["execPath"])!!).toAbsolutePath() !=
            Path.of(Py.str(image["executable_path"])!!).toAbsolutePath()
        ) {
            throw ObservationError("live Node image path differs from request")
        }
        val ancestry = mutableListOf<JsonObject>()
        var current = pid
        var reached = false
        for (step in 0 until 32) {
            val identity = LinuxObserver.identity(current)
            ancestry.add(identity)
            if (current == gradlePid) {
                if (Py.int(identity["start_ticks"]) != gradleStartTicks) {
                    throw ObservationError("Gradle process start identity differs")
                }
                reached = true
                break
            }
            val parent = Py.int(identity["parent_pid"])
            if (parent <= 1) throw ObservationError("Node test process is outside selected Gradle tree")
            current = parent
        }
        if (!reached) throw ObservationError("Node test ancestry exceeds bound")
        if (Py.int(ancestry.first()["start_ticks"]) != Py.int(image["start_ticks"])) {
            throw ObservationError("Node start identity changed during observation")
        }
        val executable = Path.of(Py.str(image["executable_path"])!!)
        if (digest(executable) != Py.str(image["executable_sha256"])) {
            throw ObservationError("live Node executable bytes changed")
        }
        val version = nodeVersion(executable)
        if (version != Py.str(request["version"]) || !Regex("v\\d+\\.\\d+\\.\\d+").matches(version)) {
            throw ObservationError("live Node version differs from executable version")
        }
        if (digest(executable) != Py.str(image["executable_sha256"])) {
            throw ObservationError("Node executable bytes changed after version check")
        }
        val payload = Path.of(payloadPath)
        val modified = Files.getLastModifiedTime(payload).to(TimeUnit.NANOSECONDS)
        if (modified < startedNs || modified > observedNs) {
            throw ObservationError("Node test payload predates invocation")
        }
        val relativePayload = repository.relativize(payload).toString().replace('\\', '/')
        val loader = FullCorpus.nodeLaunchLoader(repository.toString(), strings(image["argv"]))
        return buildJsonObject {
            put("group_id", JsonPrimitive(groupId))
            put("task", JsonPrimitive(FullCorpus.nodeTask(groupId)))
            put("pid", JsonPrimitive(pid))
            put("start_ticks", image.getValue("start_ticks"))
            put("boot_id", JsonPrimitive(LinuxObserver.bootId()))
            put("observed_ns", JsonPrimitive(observedNs))
            put("ancestry", JsonArray(ancestry))
            put("executable_path", image.getValue("executable_path"))
            put("executable_sha256", image.getValue("executable_sha256"))
            put("version", JsonPrimitive(version))
            put("argv", image.getValue("argv"))
            put("requested_argv", request.getValue("argv"))
            put("requested_exec_path", request.getValue("execPath"))
            put("payload_path", JsonPrimitive(relativePayload))
            put("payload_sha256", JsonPrimitive(digest(payload)))
            put(
                "launch_loader_path",
                loader?.let { JsonPrimitive(repository.relativize(Path.of(it)).toString().replace('\\', '/')) }
                    ?: kotlinx.serialization.json.JsonNull,
            )
            put(
                "launch_loader_sha256",
                loader?.let { JsonPrimitive(digest(Path.of(it))) } ?: kotlinx.serialization.json.JsonNull,
            )
            put("request_name", JsonPrimitive(requestFile.fileName.toString()))
            put("request_sha256", JsonPrimitive(digest(raw)))
            put("nonce", JsonPrimitive(nonce))
        }
    }

    private fun nodeVersion(executable: Path): String {
        val builder = ProcessBuilder(executable.toString(), "--version")
        val environment = builder.environment()
        environment.remove("NODE_OPTIONS")
        environment.remove("DYN4K_NODE_OBSERVATION_DIR")
        val process = builder.redirectErrorStream(false).start()
        val stdout = process.inputStream.use { it.readBytes() }
        process.errorStream.close()
        process.waitFor(300, TimeUnit.SECONDS)
        if (process.isAlive) {
            process.destroyForcibly()
            throw ObservationError("live Node version did not run")
        }
        return stdout.toString(StandardCharsets.UTF_8).trim()
    }

    private fun strings(value: JsonElement?): List<String> =
        (value as? JsonArray)?.map { Py.str(it) ?: "" } ?: emptyList()
}
