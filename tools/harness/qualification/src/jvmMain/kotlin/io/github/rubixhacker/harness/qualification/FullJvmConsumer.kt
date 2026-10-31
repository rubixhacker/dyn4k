package io.github.rubixhacker.harness.qualification

import io.github.rubixhacker.harness.contract.CanonicalJson
import io.github.rubixhacker.harness.contract.Sha256
import io.github.rubixhacker.harness.contract.StrictJson
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.Path
import javax.xml.parsers.DocumentBuilderFactory
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

/**
 * `tools/qualification/full_jvm_consumer.py`: the complete JVM consumer.
 *
 * Ported surface: the lane table, the approved-contract shape, the source inventory, the
 * four named input files, the report comparison, and the worker proof. Pin tables live in
 * [FullJvmConsumerRules]; nothing here duplicates them.
 *
 * Not ported: the Gradle replay (`run`) and the archive replay (`verify` tail). Both fail
 * closed naming the Python module, the way the `full_*` adapters name their unported
 * consumers. Nothing here shells out to Python.
 */
object FullJvmConsumer {
    /** `LANE`: the default lane. Every other lane lives in [FullJvmConsumerRules.LANES]. */
    const val LANE = FullJvmConsumerRules.DEFAULT_LANE

    fun sha(data: ByteArray): String = Sha256.of(data)

    /** `encoded`: `json.dumps(sort_keys=True, separators=(",", ":"), allow_nan=False)`. */
    fun encoded(value: JsonElement): ByteArray =
        CanonicalJson.render(value).toByteArray(StandardCharsets.UTF_8)

    /** `git_blob`: the committed bytes of one path at the exact candidate. */
    fun gitBlob(repository: Path, candidate: String, path: String): ByteArray {
        val process = ProcessBuilder(
            listOf("git", "--no-replace-objects", "-C", repository.toString(), "show", "$candidate:$path"),
        ).start()
        val stdout = process.inputStream.readBytes()
        val stderr = process.errorStream.readBytes()
        if (process.waitFor() != 0) {
            throw IllegalArgumentException(
                "git show failed: " + String(stderr, StandardCharsets.UTF_8).trim(),
            )
        }
        return stdout
    }

    /** `selected_contract`: the approved manifest and its 2,526-case JVM contract. */
    fun selectedContract(repository: Path, lane: String = LANE): Pair<JsonObject, JsonObject> {
        FullJvmConsumerRules.laneParts(lane)
        val manifest = IndependentGates.loadApprovedManifest(repository)
        val contract = IndependentGates.consumerContract(manifest, lane)
        FullJvmConsumerRules.requireContract(contract)
        return manifest to contract
    }

    /** `source_inventory`: every tracked test source must match the live checkout. */
    fun sourceInventory(repository: Path, candidate: String, cases: List<JsonObject>): Map<String, String> {
        val process = ProcessBuilder(
            listOf(
                "git", "--no-replace-objects", "-C", repository.toString(), "ls-tree", "-r",
                "--name-only", candidate, "--",
            ) + FullJvmConsumerRules.SOURCE_ROOTS,
        ).start()
        val tracked = String(process.inputStream.readBytes(), StandardCharsets.UTF_8)
            .lines().filter { it.isNotEmpty() && (it.endsWith(".kt") || it.endsWith(".java")) }
            .sorted()
        val live = mutableListOf<String>()
        for (root in FullJvmConsumerRules.SOURCE_ROOTS) {
            val dir = repository.resolve(root)
            if (Files.exists(dir)) {
                Files.walk(dir).use { walk ->
                    walk.filter {
                        Files.isRegularFile(it) &&
                            (it.toString().endsWith(".kt") || it.toString().endsWith(".java"))
                    }.forEach { live.add(repository.relativize(it).toString()) }
                }
            }
        }
        if (tracked != live.sorted() || tracked.size != tracked.toSet().size) {
            throw IllegalArgumentException("test input tree differs from exact candidate")
        }
        val sources = linkedMapOf<String, String>()
        for (relative in tracked) {
            val blob = gitBlob(repository, candidate, relative)
            val checkout = repository.resolve(relative)
            if (Files.exists(checkout) && !Files.readAllBytes(checkout).contentEquals(blob)) {
                throw IllegalArgumentException("test source checkout differs: $relative")
            }
            sources[relative] = sha(blob)
        }
        for (item in cases) {
            val source = item["source"] as? JsonObject ?: continue
            val path = Py.str(source["path"]) ?: continue
            val digest = Py.str(source["sha256"]) ?: continue
            if (sources[path] != digest) {
                throw IllegalArgumentException("selected method source differs: ${Py.str(item["id"])}")
            }
        }
        return sources
    }

    /** `input_bytes`: the inventory, both case tables, and the lane script. */
    fun inputBytes(
        cases: List<JsonObject>,
        sources: Map<String, String>,
        lane: String = LANE,
    ): Map<String, ByteArray> = FullJvmConsumerRules.inputBytes(cases, sources, lane)

    /** `prepare`: write the four named input files into an empty directory. */
    fun prepare(
        repository: Path,
        candidate: String,
        destination: Path,
        lane: String = LANE,
    ): JsonObject {
        val repo = repository.toAbsolutePath().normalize()
        val dest = destination.toAbsolutePath().normalize()
        val (manifest, contract) = selectedContract(repo, lane)
        val cases = (contract["cases"] as JsonArray).map { it as JsonObject }
        val sources = sourceInventory(repo, candidate, cases)
        if (Files.exists(dest) && Files.list(dest).use { it.findAny().isPresent }) {
            throw IllegalArgumentException("JVM input directory must be empty")
        }
        Files.createDirectories(dest)
        for ((name, data) in inputBytes(cases, sources, lane)) {
            Files.write(dest.resolve(name), data)
        }
        return buildJsonObject {
            put("manifest_sha256", JsonPrimitive(IndependentGates.digest(manifest)))
            put(
                "contract_sha256",
                JsonPrimitive(sha(encoded(contract))),
            )
            put("source_count", JsonPrimitive(sources.size))
            put("selected_cases", JsonPrimitive(cases.size))
        }
    }

    /** `target_binary`: one staged JVM artifact path. */
    fun targetBinary(staging: Path, module: String): Path =
        staging.resolve(FullStagedConsumerRules.GROUP.replace(".", "/"))
            .resolve("$module-jvm")
            .resolve(FullStagedConsumerRules.VERSION)
            .resolve("$module-jvm-${FullStagedConsumerRules.VERSION}.jar")

    /** One mode-publication artifact entry: its staged path and recorded digest. */
    fun artifactEntry(receipt: JsonObject, module: String): Pair<String, String> {
        val artifacts = receipt["artifacts"] as? JsonObject
            ?: throw IllegalArgumentException("JVM mode publication differs from independently selected JARs")
        val item = artifacts[module] as? JsonObject
            ?: throw IllegalArgumentException("JVM mode publication differs from independently selected JARs")
        val path = Py.str(item["path"])
            ?: throw IllegalArgumentException("JVM mode publication differs from independently selected JARs")
        val digest = Py.str(item["sha256"])
            ?: throw IllegalArgumentException("JVM mode publication differs from independently selected JARs")
        return path to digest
    }

    /**
     * `mode_publication`: the staged repository behind a verified mode publication.
     *
     * The `compiler_modes.replay` call arrives through [replay], which fails closed until
     * that module is ported. The repository identity check needs no workstation path: the
     * receipt and the replay bind the producing checkout.
     */
    fun modePublication(
        publication: Path,
        candidate: String,
        configuration: String,
        hashes: Map<String, String>,
        digest: String,
        replay: JvmModeReplay = UnportedJvmReplay,
    ): Path {
        if (Files.isSymbolicLink(publication)) {
            throw IllegalArgumentException("independent JVM mode publication is symbolic")
        }
        val pub = publication.toAbsolutePath().normalize()
        if (!Files.isDirectory(pub) || Files.isSymbolicLink(pub)) {
            throw IllegalArgumentException("independent JVM mode publication digest differs")
        }
        if (!Py.SHA64.matches(digest)) {
            throw IllegalArgumentException("independent JVM mode publication digest differs")
        }
        val observed = try {
            StableTreeDigest.digest(pub)
        } catch (error: ArchiveScanError) {
            throw IllegalArgumentException("independent JVM mode publication digest differs", error)
        }
        if (observed != digest) {
            throw IllegalArgumentException("independent JVM mode publication digest differs")
        }
        val result = replay.replay(pub, candidate, configuration)
        if (Py.str(result["status"]) != "PASSED") {
            throw IllegalArgumentException("JVM mode publication is unpassed")
        }
        val receipt = if (Files.isRegularFile(pub.resolve("receipt.json"))) {
            StrictJson.load(
                String(Files.readAllBytes(pub.resolve("receipt.json")), StandardCharsets.UTF_8),
            ) as? JsonObject
        } else {
            null
        } ?: throw IllegalArgumentException("JVM mode publication differs from independently selected JARs")
        val staging = pub.resolve("staged")
        val flags = (receipt["flags"] as? JsonArray)?.mapNotNull { Py.str(it) }
        if (Py.str(receipt["mode"]) != configuration ||
            Py.str(receipt["candidate_sha"]) != candidate ||
            flags != FullJvmConsumerRules.jvmFlags(configuration) ||
            (receipt["artifacts"] as? JsonObject)?.keys?.toSet() !=
            FullStagedConsumerRules.MODULES.toSet()
        ) {
            throw IllegalArgumentException("JVM mode publication differs from independently selected JARs")
        }
        for (module in FullStagedConsumerRules.MODULES) {
            val (relative, expected) = artifactEntry(receipt, module)
            if (pub.resolve(relative) != targetBinary(staging, module) ||
                sha(Files.readAllBytes(targetBinary(staging, module))) != expected ||
                hashes[module] != expected
            ) {
                throw IllegalArgumentException("JVM mode publication differs from independently selected JARs")
            }
        }
        return staging
    }

    /**
     * `test_worker_proof`: both Gradle Test Executor launches are proven.
     *
     * Each of the core and facade launches must name its worker id, its module working
     * directory, the runtime executable, and the worker main, and its `test` task must
     * precede the launch line. The two launches must differ.
     */
    fun testWorkerProof(output: String, checkout: Path, runtimeExecutable: String) {
        val launches = Regex("^Starting process 'Gradle Test Executor [^\\n]*$", RegexOption.MULTILINE)
            .findAll(output).map { it.value }.toList()
        if (launches.size != 2) {
            throw IllegalArgumentException("both Gradle Test Executor launches are required")
        }
        val project = checkout.resolve(FullJvmConsumerRules.CONSUMER)
        for (module in listOf("core", "facade")) {
            val task = "> Task :$module:test\n"
            val pattern = Regex(
                "Starting process 'Gradle Test Executor (\\d+)'\\. Working directory: " +
                    Regex.escape(project.resolve(module).toString()) + " Command: " +
                    Regex.escape(runtimeExecutable) + " .+" +
                    Regex.escape("worker.org.gradle.process.internal.worker.GradleWorkerMain") +
                    " 'Gradle Test Executor \\1'",
            )
            val matches = launches.filter { pattern.matches(it) }
            if (matches.size != 1 || task !in output ||
                output.indexOf(task) > output.indexOf(matches[0])
            ) {
                throw IllegalArgumentException("$module Gradle Test Executor launch or test task differs")
            }
        }
        if (launches[0] == launches[1]) {
            throw IllegalArgumentException("Gradle Test Executor launches are duplicated")
        }
    }

    /**
     * `_same_report`: the normalized XML must carry the raw result unchanged.
     *
     * TestBalloon and JUnit identities both map through [JunitIdentity]; anything else is
     * a foreign case.
     */
    fun sameReport(
        raw: ByteArray,
        normalized: ByteArray,
        caseMap: Map<Pair<String, String>, String>,
    ): List<String> {
        val factory = DocumentBuilderFactory.newInstance().apply {
            setFeature("http://apache.org/xml/features/disallow-doctype-decl", true)
            isExpandEntityReferences = false
        }
        val left = factory.newDocumentBuilder().parse(raw.inputStream()).documentElement
        val right = factory.newDocumentBuilder().parse(normalized.inputStream()).documentElement
        if (left.tagName != "testsuite" || right.tagName != "testsuite") {
            throw IllegalArgumentException("external Gradle XML root differs")
        }
        val observed = mutableListOf<String>()
        fun compare(a: org.w3c.dom.Element, b: org.w3c.dom.Element) {
            if (a.tagName != b.tagName) {
                throw IllegalArgumentException("normalized XML differs from original Gradle XML")
            }
            if (a.textContent.orEmpty().trim() != b.textContent.orEmpty().trim()) {
                throw IllegalArgumentException("normalized XML differs from original Gradle XML")
            }
            val bAttributes = linkedMapOf<String, String>()
            for (index in 0 until b.attributes.length) {
                bAttributes[b.attributes.item(index).nodeName] = b.attributes.item(index).nodeValue
            }
            if (a.tagName == "testcase") {
                val classname = if (a.hasAttribute("classname")) a.getAttribute("classname") else ""
                val name = if (a.hasAttribute("name")) a.getAttribute("name") else ""
                val identity = caseMap[JunitIdentity.normalized(classname, name)]
                    ?: throw IllegalArgumentException("raw Gradle method differs from selected source identity")
                if (bAttributes.remove("id") != identity) {
                    throw IllegalArgumentException("raw Gradle method differs from selected source identity")
                }
                observed.add(identity)
            }
            if (bAttributes.size != a.attributes.length) {
                throw IllegalArgumentException("normalized XML changes raw Gradle result")
            }
            for (index in 0 until a.attributes.length) {
                val attribute = a.attributes.item(index)
                if (bAttributes[attribute.nodeName] != attribute.nodeValue) {
                    throw IllegalArgumentException("normalized XML changes raw Gradle result")
                }
            }
            val aChildren = (0 until a.childNodes.length).map { a.childNodes.item(it) }
                .filter { it.nodeType == org.w3c.dom.Node.ELEMENT_NODE }
            val bChildren = (0 until b.childNodes.length).map { b.childNodes.item(it) }
                .filter { it.nodeType == org.w3c.dom.Node.ELEMENT_NODE }
            if (aChildren.size != bChildren.size) {
                throw IllegalArgumentException("normalized XML changes raw Gradle result")
            }
            for (index in aChildren.indices) {
                compare(aChildren[index] as org.w3c.dom.Element, bChildren[index] as org.w3c.dom.Element)
            }
        }
        compare(left, right)
        return observed
    }

    /**
     * `run`: not ported.
     *
     * The external Gradle replay needs the staged mode publication, both target JDKs,
     * and the consumer project. It fails closed until then.
     */
    fun run(): Nothing =
        throw IllegalArgumentException(
            "full JVM external Gradle replay is not ported: tools/qualification/full_jvm_consumer.py",
        )

    /**
     * `verify`: the portable archive checks run here; the replay tail is not ported.
     *
     * Every check below needs only the archive, the receipt, and the approved suite.
     * The provider-graph, build-configuration, and gate replay stay with `run`.
     */
    fun verify(
        root: Path,
        repository: Path,
        candidate: String,
        expectedHashes: Map<String, String>,
        lane: String = LANE,
    ): JsonObject {
        FullJvmConsumerRules.laneParts(lane)
        val (version, configuration) = FullJvmConsumerRules.laneParts(lane)
        val rootPath = root.toAbsolutePath().normalize()
        val repoPath = repository.toAbsolutePath().normalize()
        if (!Files.isDirectory(rootPath) || Files.isSymbolicLink(rootPath)) {
            throw IllegalArgumentException("full JVM archive is missing or symbolic")
        }
        val receipt = if (Files.isRegularFile(rootPath.resolve("receipt.json"))) {
            StrictJson.load(
                String(Files.readAllBytes(rootPath.resolve("receipt.json")), StandardCharsets.UTF_8),
            ) as? JsonObject
        } else {
            null
        } ?: throw IllegalArgumentException("full JVM archive identity differs")
        val (manifest, contract) = selectedContract(repoPath, lane)
        val cases = (contract["cases"] as JsonArray).map { it as JsonObject }
        if (Py.str(receipt["candidate_sha"]) != candidate ||
            Py.str(receipt["lane"]) != lane ||
            Py.str(receipt["version"]) != version ||
            Py.str(receipt["configuration"]) != configuration ||
            Py.str(receipt["consumer_group"]) != "full-suite"
        ) {
            throw IllegalArgumentException("full JVM archive identity differs")
        }
        val recorded = (receipt["artifact_hashes"] as? JsonObject)?.mapValues { Py.str(it.value) }
        if (recorded != expectedHashes || recorded.keys != FullStagedConsumerRules.MODULES.toSet()) {
            throw IllegalArgumentException("full JVM archive identity differs")
        }
        if (Py.str(receipt["manifest_sha256"]) != IndependentGates.digest(manifest) ||
            cases.size != 2526
        ) {
            throw IllegalArgumentException("full JVM archive identity differs")
        }
        throw IllegalArgumentException(
            "full JVM archive replay tail is not ported: tools/qualification/full_jvm_consumer.py",
        )
    }
}

/** The `compiler_modes.replay` seam while that module stays Python. */
object UnportedJvmReplay : JvmModeReplay {
    override fun replay(publication: Path, candidate: String, configuration: String): JsonObject =
        throw IllegalArgumentException(
            "JVM mode publication replay is not ported: tools/qualification/compiler_modes.py",
        )

    override fun jvmFlags(configuration: String): kotlinx.serialization.json.JsonArray =
        throw IllegalArgumentException(
            "JVM mode publication replay is not ported: tools/qualification/compiler_modes.py",
        )
}
