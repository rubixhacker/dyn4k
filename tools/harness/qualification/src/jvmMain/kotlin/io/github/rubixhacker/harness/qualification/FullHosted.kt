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
 * `tools/qualification/full_hosted.py`: the pinned toolchain, the archive contract, the receipt
 * inventory, the Safari diagnostic grammar, and the entry point of every ported check.
 *
 * The file-system, process, and XML work lives in [FullHostedRuntime]; the pure rules live in
 * [FullHostedRules]. Only `full_hosted.run` (the hosted execution driver) remains Python, so the
 * command line fails closed for that mode.
 */
object FullHosted {
    const val PINNED_GRADLE = "9.5.0"
    const val PINNED_KGP = "2.4.20"
    const val PINNED_AGP = "9.3.1"

    const val MANIFEST = "tools/qualification/full-common-corpus.json"
    const val MAPPING = "tools/qualification/full-common-original-map.tsv"
    const val PAIRS = "tools/qualification/full-common-reviewed-pairs.tsv"

    /** `NATIVE`: the hosted native targets, keyed exactly as `hosted.NATIVE_TARGETS` is. */
    val NATIVE: Set<String> = Hosted.NATIVE_TARGETS.keys

    /** `CONFIGS`: the two configurations every hosted target is run in. */
    val CONFIGS: Map<String, List<String>> = linkedMapOf<String, List<String>>().apply {
        for (target in NATIVE) put(target, listOf("debug-g", "optimized-opt"))
        put("jsSafari", listOf("development", "production"))
    }

    /** `SOURCE_TASK`: the Gradle task that produces one target's source test reports. */
    val SOURCE_TASK: Map<String, String> = linkedMapOf<String, String>().apply {
        for (target in NATIVE) put(target, "${target}Test")
        put("jsSafari", "jsBrowserTest")
    }

    /** `INPUTS`: every candidate source file the receipt archives under `inputs/`. */
    val INPUTS: List<String> = listOf(
        MANIFEST, MAPPING, PAIRS, "tools/qualification/foundation-probes.json",
        "tools/qualification/full_corpus.py", "tools/qualification/full_hosted.py",
        "tools/qualification/safari_reporter.py",
        "tools/qualification/safari_windows_file.py",
        "tools/qualification/safari-karma-reporter.js",
        "tools/qualification/hosted.py", "tools/qualification/qualify.py",
        "tools/qualification/artifact.py", "build.gradle.kts",
        "consumers/qualification/portable/build.gradle.kts",
        "consumers/qualification/portable/settings.gradle.kts",
    )

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
            return verifyRawFiles(temporary, receipt, candidateRepository = candidateRepository)
        } finally {
            Files.walk(temporary).use { walk ->
                walk.sorted(Comparator.reverseOrder()).forEach { Files.deleteIfExists(it) }
            }
        }
    }

    /** `verify_raw_files`: the receipt verifier of a completed hosted full-corpus run. */
    fun verifyRawFiles(
        output: Path,
        receipt: JsonObject,
        manifest: JsonObject? = null,
        consumerManifest: JsonObject? = null,
        candidateRepository: Path? = null,
    ): JsonObject = FullHostedRuntime.verifyRawFiles(
        output,
        receipt,
        manifest,
        consumerManifest,
        candidateRepository,
    )

    /** `candidate_checkout`: the checkout this process runs in. */
    fun candidateCheckout(): Path = FullHostedRuntime.candidateCheckout()

    /** `load_corpus`: the committed manifest, map, and reviewed pairs of one candidate. */
    fun loadCorpus(repository: Path, candidateSha: String): JsonObject =
        FullHostedRuntime.loadCorpus(repository, candidateSha)

    /** `read_reports`: one module's XML reports against the reviewed case inventory. */
    fun readReports(
        paths: List<Path>,
        expected: Set<Pair<String, String>>,
        target: String,
        startedNs: Long,
        finishedNs: Long,
        safariVersion: String? = null,
    ): HostedReportCheck =
        FullHostedRuntime.readReports(paths, expected, target, startedNs, finishedNs, safariVersion)

    /** `run_command`: run one command and record its receipt. */
    fun runCommand(
        command: List<String>,
        cwd: Path,
        destination: Path,
        invocationId: String? = null,
    ): JsonObject = FullHostedRuntime.runCommand(command, cwd, destination, invocationId)

    /** `verify_process`: the archived process receipt and both of its logs. */
    fun verifyProcess(
        output: Path,
        folder: Path,
        process: JsonObject?,
        invocation: String?,
        requiredTask: String? = null,
    ) = FullHostedRuntime.verifyProcess(output, folder, process, invocation, requiredTask)

    /** `verify_staging`: the staged GAV, POM, metadata, and binary contracts. */
    fun verifyStaging(output: Path, receipt: JsonObject) =
        FullHostedRuntime.verifyStaging(output, receipt)

    /** `verify_staged_content`: the archived staged publication against its content audit. */
    fun verifyStagedContent(output: Path, receipt: JsonObject, repository: Path) =
        FullHostedRuntime.verifyStagedContent(output, receipt, repository)

    /** `require_test_tasks`: the Gradle console lines that prove the tasks ran. */
    fun requireTestTasks(
        process: JsonObject,
        folder: Path,
        target: String,
        configuration: String,
        modules: List<String>,
    ) = FullHostedRuntime.requireTestTasks(process, folder, target, configuration, modules)

    /** `canonical_safari_json`: the archived input must be the committed JSON object. */
    fun canonicalSafariJson(
        repository: Path,
        candidateSha: String,
        output: Path,
        relative: String,
    ): JsonObject = FullHostedRuntime.canonicalSafariJson(repository, candidateSha, output, relative)

    /** `check_safari_diagnostic_suite`: the reviewed Safari diagnostic rows of one suite. */
    fun checkSafariDiagnosticSuite(suite: org.w3c.dom.Element) =
        FullHostedRuntime.checkSafariDiagnosticSuite(suite)

    /** `safari_file_observation`: one path observed without following a link. */
    fun safariFileObservation(path: Path, anchor: Path, maxHashBytes: Long? = null): JsonObject =
        FullHostedRuntime.safariFileObservation(path, anchor, maxHashBytes)

    /** `test_products`: the one test executable of a configuration. */
    fun testProducts(
        project: Path,
        target: String,
        configuration: String,
        process: JsonObject,
        safariInput: String? = null,
        name: String? = null,
    ): MutableMap<String, kotlinx.serialization.json.JsonElement> =
        FullHostedRuntime.testProducts(project, target, configuration, process, safariInput, name)

    /** `safari_product_inventory`: bounded observations of both Safari product layouts. */
    fun safariProductInventory(project: Path, configuration: String, name: String): JsonObject =
        FullHostedRuntime.safariProductInventory(project, configuration, name)

    /** `product_inventory`: the bounded inventory one failed product selection retains. */
    fun productInventory(
        project: Path,
        target: String,
        configuration: String? = null,
        name: String? = null,
    ): JsonObject = FullHostedRuntime.productInventory(project, target, configuration, name)

    /** `collect_test_products`: select each project's product or retain the inventory and fail. */
    fun collectTestProducts(
        projects: Map<String, Path>,
        target: String,
        configuration: String,
        process: JsonObject,
        diagnostic: Path,
        archiveRoot: Path,
        safariInputs: Map<String, String>? = null,
    ): MutableMap<String, MutableMap<String, kotlinx.serialization.json.JsonElement>> =
        FullHostedRuntime.collectTestProducts(
            projects,
            target,
            configuration,
            process,
            diagnostic,
            archiveRoot,
            safariInputs,
        )

    /** `archive_test_product`: archive the selected executable and Karma input. */
    fun archiveTestProduct(
        product: MutableMap<String, kotlinx.serialization.json.JsonElement>,
        output: Path,
        configuration: String,
        name: String,
        target: String,
    ) = FullHostedRuntime.archiveTestProduct(product, output, configuration, name, target)

    /** `capture_safari_config`: archive one generated Karma configuration. */
    fun captureSafariConfig(
        repository: Path,
        candidateSha: String,
        project: String,
        configuration: String,
        process: JsonObject,
        output: Path,
        archiveName: String,
    ): JsonObject = FullHostedRuntime.captureSafariConfig(
        repository,
        candidateSha,
        project,
        configuration,
        process,
        output,
        archiveName,
    )

    /** `safari_config_input`: the Karma input path of one generated configuration. */
    fun safariConfigInput(data: ByteArray): String = FullHostedRules.safariConfigInput(data)

    /** `verify_safari_reporter_archive`: the staged reporter and generated configurations. */
    fun verifySafariReporterArchive(
        output: Path,
        receipt: JsonObject,
        lane: JsonObject,
        candidateRepository: Path,
        repositoryRoot: Path,
    ) = FullHostedRuntime.verifySafariReporterArchive(
        output,
        receipt,
        lane,
        candidateRepository,
        repositoryRoot,
    )

    /** `parse_graph`: the resolved consumer graph bound to the staged bytes and the cache. */
    fun parseGraph(
        folder: Path,
        process: JsonObject,
        target: String,
        hashes: JsonObject,
        staging: String,
        expectedHome: String,
        stagedRoot: Path? = null,
    ): JsonObject = FullHostedRuntime.parseGraph(
        folder,
        process,
        target,
        hashes,
        staging,
        expectedHome,
        stagedRoot,
    )

    /** `retain_failed_safari_source_xml`: keep the unverified reports of a failed Safari lane. */
    fun retainFailedSafariSourceXml(
        repository: Path,
        destination: Path,
        process: JsonObject,
        validationError: Throwable,
    ): JsonObject =
        FullHostedRuntime.retainFailedSafariSourceXml(repository, destination, process, validationError)

    /** `copy_reports`: verify and archive every module's source XML reports. */
    fun copyReports(
        repository: Path,
        target: String,
        destination: Path,
        process: JsonObject,
        expected: JsonObject,
        safariVersion: String? = null,
        diagnostic: MutableMap<String, kotlinx.serialization.json.JsonElement>? = null,
    ): List<JsonObject> = FullHostedRuntime.copyReports(
        repository,
        target,
        destination,
        process,
        expected,
        safariVersion,
        diagnostic,
    )

    /** `capture_consumer`: the staged consumer probe reports and their archive members. */
    fun captureConsumer(
        repository: Path,
        target: String,
        destination: Path,
        process: JsonObject,
    ): HostedReportCheck =
        FullHostedRuntime.captureConsumer(repository, target, destination, process)

    /** `read_consumer_reports`: the staged consumer reports against the probe manifest. */
    fun readConsumerReports(
        paths: List<Path>,
        expected: Set<Pair<String, String>>,
        process: JsonObject,
    ): HostedReportCheck = FullHostedRuntime.readConsumerReports(paths, expected, process)

    /** `capture_dokka_output`: archive the generated Dokka tree and record its provenance. */
    fun captureDokkaOutput(
        repository: Path,
        output: Path,
        receipt: MutableMap<String, kotlinx.serialization.json.JsonElement>,
    ) = FullHostedRuntime.captureDokkaOutput(repository, output, receipt)

    /** `safari_product_paths`: the compiler product and Karma input of one Safari project. */
    fun safariProductPaths(project: String, configuration: String, name: String): SafariProductPaths =
        FullHostedRules.safariProductPaths(project, configuration, name)

    /** `init_script`: the generated Gradle init script of one configuration. */
    fun initScript(target: String, configuration: String, simulatorUdid: String? = null): String =
        FullHostedRules.initScript(target, configuration, simulatorUdid)

    /** `graph_script`: the generated Gradle init script that prints the consumer graph. */
    fun graphScript(target: String): String = FullHostedRules.graphScript(target)

    /** `verify_safari_mode_arguments`: the browser and production mode properties of a command. */
    fun verifySafariModeArguments(
        command: List<String?>,
        processName: String,
        config: String? = null,
    ) = FullHostedRules.verifySafariModeArguments(command, processName, config)

    /** `verify_report_group`: the lane's case identities and report digests. */
    fun verifyReportGroup(
        group: JsonObject?,
        checked: HostedReportCheck,
        prefix: List<String>,
    ) = FullHostedRules.verifyReportGroup(group, checked, prefix)

    /** `safari_v2_require`: one diagnostic field must be complete. */
    fun safariV2Require(condition: Boolean, field: String) =
        FullHostedRules.safariV2Require(condition, field)

    /** `safari_v2_vector`: two numbers separated by a comma. */
    fun safariV2Vector(value: String, field: String) =
        FullHostedRules.safariV2Vector(value, field)

    /** `safari_v2_numbers`: an exact count of comma separated numbers. */
    fun safariV2Numbers(value: String, field: String, count: Int) =
        FullHostedRules.safariV2Numbers(value, field, count)

    /** `safari_v2_vectors`: `null`, empty, or semicolon separated vectors. */
    fun safariV2Vectors(
        value: String,
        field: String,
        allowNull: Boolean = true,
        allowEmpty: Boolean = true,
    ): Int? = FullHostedRules.safariV2Vectors(value, field, allowNull, allowEmpty)

    /** `safari_v2_feature`: a point, an edge, or the explicit `unknown:index` form. */
    fun safariV2Feature(value: String, field: String) =
        FullHostedRules.safariV2Feature(value, field)

    /** `safari_v2_shape`: the ordered shape fields and the polygon vertex count. */
    fun safariV2Shape(value: String, field: String): Pair<String, Int?> =
        FullHostedRules.safariV2Shape(value, field)

    /** `safari_v2_polygon_edges`: one twelve field record per polygon edge, or `na`. */
    fun safariV2PolygonEdges(value: String, field: String, kind: String, vertices: Int?) =
        FullHostedRules.safariV2PolygonEdges(value, field, kind, vertices)

    /** `safari_v2_sat_candidates`: every candidate record; returns whether one separated. */
    fun safariV2SatCandidates(value: String, field: String): Boolean =
        FullHostedRules.safariV2SatCandidates(value, field)

    /** `safari_v2_epa_records`: one thirteen field record per EPA iteration. */
    fun safariV2EpaRecords(value: String, field: String, iteration: SafariInteger) =
        FullHostedRules.safariV2EpaRecords(value, field, iteration)

    /** `safari_v2_number`: `value@bits` with the double's own encoding. */
    fun safariV2Number(value: String, field: String) =
        FullHostedRules.safariV2Number(value, field)

    /** `safari_v2_integer`: a canonical integer literal with an optional floor. */
    fun safariV2Integer(value: String, field: String, minimum: Long? = null): SafariInteger =
        FullHostedRules.safariV2Integer(value, field, minimum)

    /** `safari_v2_check_values`: the cross-field invariants of one diagnostic row. */
    fun safariV2CheckValues(values: Map<String, String>, step: Int, points: Int) =
        FullHostedRules.safariV2CheckValues(values, step, points)

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
