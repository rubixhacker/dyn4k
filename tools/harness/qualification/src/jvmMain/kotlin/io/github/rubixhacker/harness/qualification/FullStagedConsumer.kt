package io.github.rubixhacker.harness.qualification

import io.github.rubixhacker.harness.contract.CanonicalJson
import io.github.rubixhacker.harness.contract.Sha256
import io.github.rubixhacker.harness.contract.StrictJson
import java.io.IOException
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
import kotlinx.serialization.json.buildJsonObject

/**
 * `tools/qualification/full_staged_consumer.py`: the bounded original-source JVM consumer.
 *
 * The module runs the real Gradle consumer against a staged repository, captures exactly one
 * original test report, proves the resolved provider graph, and seals a partial receipt whose
 * `status` is `NOT_RUN` — it never claims the full selected suite.
 */
object FullStagedConsumer {
    private const val IDENTITY = "jvm:Java:current:default"

    fun sha(data: ByteArray): String = Sha256.of(data)

    /** `class_contract(manifest, lane, classname)`: the bounded class over the approved suite. */
    fun classContract(
        manifest: JsonObject,
        laneId: String,
        classname: String,
    ): StagedClassContract = FullStagedConsumerRules.classContract(
        IndependentGates.consumerContract(manifest, laneId)["cases"] as JsonArray,
        classname,
    )

    /** `encoded`: `json.dumps(sort_keys=True, separators=(",", ":"), allow_nan=False)`. */
    fun encoded(value: JsonElement): ByteArray =
        CanonicalJson.render(value).toByteArray(StandardCharsets.UTF_8)

    /** `git_blob`: the committed bytes of one path at the exact candidate. */
    fun gitBlob(repository: Path, candidate: String, path: String): ByteArray {
        val process = ProcessBuilder(
            listOf("git", "--no-replace-objects", "-C", repository.toString(), "show",
                "$candidate:$path"),
        ).start()
        val stdout = process.inputStream.readBytes()
        val stderr = process.errorStream.readBytes()
        if (process.waitFor() != 0) {
            throw IncompleteEvidence(
                "git show failed: " + String(stderr, StandardCharsets.UTF_8).trim(),
            )
        }
        return stdout
    }

    /**
     * `raw_case_ids`: one report, its counts, and exactly the approved case identities.
     */
    fun rawCaseIds(raw: ByteArray, expected: Set<String>): Set<String> {
        val document = try {
            DocumentBuilderFactory.newInstance().apply {
                setFeature("http://apache.org/xml/features/disallow-doctype-decl", true)
                isExpandEntityReferences = false
            }.newDocumentBuilder().parse(raw.inputStream())
        } catch (error: Exception) {
            throw IllegalArgumentException("raw consumer report root differs")
        }
        val suite = document.documentElement
        if (suite.tagName != "testsuite") {
            throw IllegalArgumentException("raw consumer report root differs")
        }
        val cases = mutableListOf<org.w3c.dom.Element>()
        val all = suite.getElementsByTagName("testcase")
        for (index in 0 until all.length) cases.add(all.item(index) as org.w3c.dom.Element)
        fun child(element: org.w3c.dom.Element, name: String): org.w3c.dom.Element? {
            val children = element.getElementsByTagName(name)
            return children.item(0) as? org.w3c.dom.Element
        }
        val counts = linkedMapOf(
            "tests" to cases.size,
            "failures" to cases.count { child(it, "failure") != null },
            "errors" to cases.count { child(it, "error") != null },
            "skipped" to cases.count { child(it, "skipped") != null },
        )
        fun attribute(element: org.w3c.dom.Element, name: String): String? =
            if (element.hasAttribute(name)) element.getAttribute(name) else null
        fun seconds(element: org.w3c.dom.Element): Double {
            val value = attribute(element, "time") ?: "nan"
            val parsed = value.toDoubleOrNull()
            if (parsed == null || parsed.isNaN() || parsed.isInfinite() || parsed < 0) {
                throw IllegalArgumentException("raw consumer report counts or outcomes differ")
            }
            return parsed
        }
        for ((key, value) in counts) {
            val raw = attribute(suite, key) ?: throw IllegalArgumentException(
                "raw consumer report counts or outcomes differ",
            )
            if (raw.toIntOrNull() != value) {
                throw IllegalArgumentException("raw consumer report counts or outcomes differ")
            }
        }
        if (listOf("failures", "errors", "skipped").any { counts.getValue(it) != 0 }) {
            throw IllegalArgumentException("raw consumer report counts or outcomes differ")
        }
        seconds(suite)
        val ids = mutableListOf<String>()
        for (case in cases) {
            val classname = attribute(case, "classname")
            val name = attribute(case, "name")
            if (classname != FullStagedConsumerRules.CLASS || name.isNullOrEmpty() ||
                !name.endsWith("[jvm]") ||
                name.dropLast(5).isEmpty() || name.dropLast(5).endsWith("[jvm]") ||
                Regex("[A-Za-z_][A-Za-z_0-9]*").matchEntire(name.dropLast(5)) == null
            ) {
                throw IllegalArgumentException("raw consumer case identity differs")
            }
            seconds(case)
            val caseId = "dyn4k-core:$classname#${name.dropLast(5)}"
            if (caseId !in expected) {
                throw IllegalArgumentException("raw consumer report has a foreign case")
            }
            ids.add(caseId)
        }
        if (ids.size != ids.toSet().size || ids.toSet() != expected) {
            throw IllegalArgumentException("raw consumer cases are missing or duplicated")
        }
        return ids.toSet()
    }

    /** `staged_binary`: one staged JVM artifact path. */
    fun stagedBinary(staging: Path, module: String): Path =
        staging.resolve(FullStagedConsumerRules.GROUP.replace(".", "/"))
            .resolve("$module-jvm")
            .resolve(FullStagedConsumerRules.VERSION)
            .resolve(FullStagedConsumerRules.stagedBinaryName(module))

    /** `graph_artifacts`: the consumer graph resolves exactly the staged binaries and no more. */
    fun graphArtifacts(
        graph: JsonObject,
        staging: Path,
        expectedHashes: Map<String, String>,
    ): Map<String, JsonObject> {
        if (Py.str(graph["configuration"]) != "jvmTestRuntimeClasspath") {
            throw IllegalArgumentException("external consumer graph configuration differs")
        }
        val artifacts = graph["artifacts"] as? JsonArray
        val components = graph["components"] as? JsonArray
        val componentNames = components?.mapNotNull { Py.str(it) } ?: emptyList()
        if (artifacts == null || components == null ||
            componentNames.size != componentNames.toSet().size
        ) {
            throw IllegalArgumentException("external consumer graph is invalid")
        }
        val group = FullStagedConsumerRules.GROUP
        val version = FullStagedConsumerRules.VERSION
        val required = FullStagedConsumerRules.MODULES.map { "$group:$it-jvm:$version" }.toSet()
        val roots = FullStagedConsumerRules.MODULES.map { "$group:$it:$version" }.toSet()
        if (componentNames.filter { it.startsWith("$group:") }.toSet() != required + roots) {
            throw IllegalArgumentException(
                "external consumer graph has a missing or foreign provider",
            )
        }
        val observed = LinkedHashMap<String, JsonObject>()
        for (module in FullStagedConsumerRules.MODULES) {
            val component = "$group:$module-jvm:$version"
            val matches = artifacts.mapNotNull { it as? JsonObject }
                .filter { Py.str(it["component"]) == component }
            if (matches.size != 1) {
                throw IllegalArgumentException(
                    "external consumer graph has a missing or duplicate artifact",
                )
            }
            val item = matches.single()
            val path = Path.of(Py.str(item["file"]) ?: "")
            val size = item["size"]
            if (!path.isAbsolute || path != stagedBinary(staging, module) ||
                Py.str(item["name"]) != path.fileName.toString() ||
                !Py.isInt(size) || Py.int(size) <= 0 ||
                Py.str(item["sha256"]) != expectedHashes[module]
            ) {
                throw IllegalArgumentException(
                    "external consumer did not resolve the exact staged binary",
                )
            }
            observed[module] = item
        }
        val stagedComponents = artifacts.mapNotNull { it as? JsonObject }
            .map { Py.str(it["component"]) ?: "" }
            .filter { it.startsWith("$group:") }
            .sorted()
        if (stagedComponents != required.sorted()) {
            throw IllegalArgumentException("external consumer graph has extra staged artifacts")
        }
        return observed
    }

    /** `process`: one command with captured stdout and stderr, relative to [base]. */
    fun process(
        command: List<String>,
        cwd: Path,
        stdout: Path,
        stderr: Path,
        base: Path,
    ): JsonObject {
        val started = FullHostedRuntime.nowNs()
        val result = try {
            val process = ProcessBuilder(command).directory(cwd.toFile()).start()
            val out = process.inputStream.readBytes()
            val err = process.errorStream.readBytes()
            process.waitFor()
            Triple(out, err, process.exitValue())
        } catch (error: IOException) {
            throw IncompleteEvidence("external consumer command did not start: ${command.first()}")
        }
        val finished = FullHostedRuntime.nowNs()
        stdout.parent?.let { Files.createDirectories(it) }
        stderr.parent?.let { Files.createDirectories(it) }
        Files.write(stdout, result.first)
        Files.write(stderr, result.second)
        return buildJsonObject {
            put("command", JsonArray(command.map { JsonPrimitive(it) }))
            put("cwd", JsonPrimitive(cwd.toString()))
            put("started_ns", JsonPrimitive(started))
            put("finished_ns", JsonPrimitive(finished))
            put("exit_code", JsonPrimitive(result.third))
            put("stdout", JsonPrimitive(posixRelative(base, stdout)))
            put("stderr", JsonPrimitive(posixRelative(base, stderr)))
        }
    }

    private fun posixRelative(base: Path, path: Path): String =
        base.relativize(path).toString().replace('\\', '/')

    /** `inventory`: every regular archive file except the receipt, with its mtime. */
    fun inventory(root: Path): JsonObject {
        val files = sortedMapOf<String, JsonElement>()
        Files.walk(root).use { walk ->
            walk.sorted(Comparator { left, right -> CanonicalText.compare(left.toString(), right.toString()) })
                .forEach { path ->
                    if (Files.isSymbolicLink(path)) {
                        throw IllegalArgumentException("partial archive contains a symlink")
                    }
                    if (Files.isRegularFile(path) && path != root.resolve("receipt.json")) {
                        files[posixRelative(root, path)] = buildJsonObject {
                            put("sha256", JsonPrimitive(sha(Files.readAllBytes(path))))
                            put(
                                "mtime_ns",
                                JsonPrimitive(
                                    Files.getLastModifiedTime(path)
                                        .to(TimeUnit.NANOSECONDS),
                                ),
                            )
                        }
                    }
                }
        }
        return JsonObject(files)
    }

    /**
     * `run`: execute the bounded consumer against the staged repository and seal the partial
     * receipt. Nothing here claims the full selected suite: `status` is always `NOT_RUN`.
     */
    fun run(
        repositoryInput: Path,
        candidate: String,
        stagingInput: Path,
        outputInput: Path,
        gradleInput: Path,
        expectedHashes: Map<String, String>,
    ): JsonObject {
        val repository = repositoryInput.toAbsolutePath().normalize()
        val staging = stagingInput.toAbsolutePath().normalize()
        val output = outputInput.toAbsolutePath().normalize()
        val gradle = gradleInput.toAbsolutePath().normalize()
        if (Files.exists(output) && Files.list(output).use { it.findAny().isPresent }) {
            throw IllegalArgumentException("raw output directory must be empty")
        }
        val javaHome = Path.of(
            System.getenv("JAVA_HOME")
                ?: throw IllegalArgumentException("bounded consumer requires JDK 21 and Gradle 9.5.0"),
        ).toRealPath()
        val java = javaHome.resolve("bin/java")
        val javaVersion = output(listOf(java.toString(), "-version")).lines().firstOrNull() ?: ""
        val gradleVersion = output(listOf(gradle.toString(), "--version"))
        if (!javaVersion.contains("version \"21") || !gradleVersion.contains("Gradle 9.5.0")) {
            throw IllegalArgumentException(
                "bounded consumer requires JDK 21 and Gradle 9.5.0",
            )
        }
        val head = output(listOf("git", "-C", repository.toString(), "rev-parse", "HEAD")).trim()
        val dirty = output(
            listOf("git", "-C", repository.toString(), "status", "--porcelain",
                "--untracked-files=no"),
        )
        if (head != candidate || dirty.isNotEmpty()) {
            throw IllegalArgumentException("producer checkout is not the exact clean candidate")
        }
        val manifest = IndependentGates.loadApprovedManifest(repository)
        val contract = classContract(
            manifest,
            FullStagedConsumerRules.LANE,
            FullStagedConsumerRules.CLASS,
        )
        if (sha(gitBlob(repository, candidate, contract.source)) != contract.sourceHash) {
            throw IllegalArgumentException("candidate original source differs from approved manifest")
        }
        if (!Files.readAllBytes(repository.resolve(contract.source))
                .contentEquals(gitBlob(repository, candidate, contract.source))
        ) {
            throw IllegalArgumentException("original source checkout differs from candidate")
        }
        for (module in FullStagedConsumerRules.MODULES) {
            if (sha(Files.readAllBytes(stagedBinary(staging, module))) != expectedHashes[module]) {
                throw IllegalArgumentException(
                    "staged binary differs from the independent expected hash",
                )
            }
        }
        Files.createDirectories(output)
        Files.createDirectory(output.resolve("raw"))
        Files.createDirectory(output.resolve("resolved"))
        val consumer = repository.resolve("consumers/qualification/portable")
        val sourceArgument = contract.source.split("src/commonTest/kotlin/", limit = 2)[1]
        val common = listOf(
            gradle.toString(), "-p", consumer.toString(), "--offline", "--no-daemon",
            "--console=plain", "-PqualificationRepository=$staging",
            "-PqualificationSuiteCheckout=$repository",
            "-PqualificationSuiteSource=$sourceArgument",
            "-PqualificationLaneId=${FullStagedConsumerRules.LANE}",
        )
        val reports = consumer.resolve("build/test-results/jvmTest")
        if (Files.isDirectory(reports)) {
            Files.newDirectoryStream(reports).use { stream ->
                stream.filter {
                    it.fileName.toString().startsWith("TEST-") &&
                        it.fileName.toString().endsWith(".xml")
                }.forEach { Files.deleteIfExists(it) }
            }
        }
        val test = process(
            common + listOf("--rerun-tasks", "jvmTest"),
            repository,
            output.resolve("raw/test.stdout"),
            output.resolve("raw/test.stderr"),
            output,
        )
        val testOutput = Files.readString(output.resolve(Py.str(test["stdout"])!!))
        if (Py.int(test["exit_code"]!!) != 0L ||
            listOf("compileTestKotlinJvm", "qualificationSuiteGraph", "jvmTest").any { task ->
                testOutput.lines().none { it.trim() == "> Task :$task" }
            } ||
            !testOutput.contains("BUILD SUCCESSFUL")
        ) {
            throw IllegalArgumentException("external original-source JVM test task failed")
        }
        val stagedGraph = FullStagedConsumerRules.graphFromOutput(testOutput)
        graphArtifacts(stagedGraph, staging, expectedHashes)
        val originals = Files.newDirectoryStream(reports).use { stream ->
            stream.filter {
                it.fileName.toString().startsWith("TEST-") &&
                    it.fileName.toString().endsWith(".xml")
            }.toList()
        }
        if (originals.size != 1) {
            throw IllegalArgumentException("external original-source JVM report count differs")
        }
        val raw = Files.readAllBytes(originals.single())
        rawCaseIds(raw, contract.ids)
        val xmlPath = output.resolve("raw").resolve(originals.single().fileName.toString())
        Files.copy(originals.single(), xmlPath, StandardCopyOption.COPY_ATTRIBUTES)
        val graphProcess = process(
            common + listOf("qualificationSuiteGraph"),
            repository,
            output.resolve("raw/graph.stdout"),
            output.resolve("raw/graph.stderr"),
            output,
        )
        if (Py.int(graphProcess["exit_code"]!!) != 0L) {
            throw IllegalArgumentException("external staged graph task failed")
        }
        val graph = FullStagedConsumerRules.graphFromOutput(
            Files.readString(output.resolve(Py.str(graphProcess["stdout"])!!)),
        )
        if (graph != stagedGraph) {
            throw IllegalArgumentException(
                "test process provider graph differs from replay graph",
            )
        }
        val artifacts = graphArtifacts(graph, staging, expectedHashes)
        for ((module, item) in artifacts) {
            val sourceBinary = Path.of(Py.str(item["file"])!!)
            if (sha(Files.readAllBytes(sourceBinary)) != expectedHashes[module]) {
                throw IllegalArgumentException("resolved external artifact bytes differ")
            }
            Files.copy(
                sourceBinary,
                output.resolve("resolved").resolve(sourceBinary.fileName.toString()),
                StandardCopyOption.COPY_ATTRIBUTES,
            )
        }
        val selected = (IndependentGates.consumerContract(
            manifest,
            FullStagedConsumerRules.LANE,
        )["cases"] as JsonArray).map { it as JsonObject }
        val selectedIds = selected.mapNotNull { Py.str(it["id"]) }.sorted()
        val receipt = LinkedHashMap<String, JsonElement>()
        receipt["schema"] = JsonPrimitive(1)
        receipt["kind"] = JsonPrimitive("full-staged-consumer-partial")
        receipt["status"] = JsonPrimitive("NOT_RUN")
        receipt["complete_selected_suite"] = JsonPrimitive(false)
        receipt["candidate_sha"] = JsonPrimitive(candidate)
        receipt["lane"] = JsonPrimitive(FullStagedConsumerRules.LANE)
        receipt["manifest_sha256"] = JsonPrimitive(IndependentGates.digest(manifest))
        receipt["selected_case_count"] = JsonPrimitive(selected.size)
        receipt["selected_case_ids"] = JsonArray(selectedIds.map { JsonPrimitive(it) })
        receipt["selected_case_ids_sha256"] = JsonPrimitive(
            sha(encoded(JsonArray(selectedIds.map { JsonPrimitive(it) }))),
        )
        receipt["observed_case_ids"] = JsonArray(contract.ids.sorted().map { JsonPrimitive(it) })
        receipt["remaining_case_count"] = JsonPrimitive(selected.size - contract.ids.size)
        receipt["original_source"] = JsonPrimitive(contract.source)
        receipt["original_source_sha256"] = JsonPrimitive(contract.sourceHash)
        receipt["consumer_build_sha256"] = JsonPrimitive(
            sha(
                gitBlob(
                    repository,
                    candidate,
                    "consumers/qualification/portable/build.gradle.kts",
                ),
            ),
        )
        receipt["staging_repository"] = JsonPrimitive(staging.toString())
        receipt["expected_artifact_hashes"] = JsonObject(
            expectedHashes.mapValues { JsonPrimitive(it.value) },
        )
        receipt["toolchain"] = buildJsonObject {
            put("java_home", JsonPrimitive(javaHome.toString()))
            put("java_sha256", JsonPrimitive(sha(Files.readAllBytes(java))))
            put("java_version", JsonPrimitive(javaVersion))
            put("gradle", JsonPrimitive(gradle.toString()))
            put("gradle_sha256", JsonPrimitive(sha(Files.readAllBytes(gradle))))
            put("gradle_version", JsonPrimitive("Gradle 9.5.0"))
            put(
                "gradle_user_home",
                JsonPrimitive(
                    Path.of(
                        System.getenv("GRADLE_USER_HOME")
                            ?: throw IllegalArgumentException(
                                "bounded consumer requires Gradle 9.5.0",
                            ),
                    ).toRealPath().toString(),
                ),
            )
        }
        receipt["consumer_xml"] = JsonPrimitive(posixRelative(output, xmlPath))
        receipt["test_process"] = test
        receipt["graph_process"] = graphProcess
        receipt["files"] = inventory(output)
        receipt["seal_sha256"] = JsonPrimitive(sha(encoded(JsonObject(receipt))))
        Files.write(
            output.resolve("receipt.json"),
            encoded(JsonObject(receipt)) + "\n".toByteArray(StandardCharsets.UTF_8),
        )
        verify(output, repository, expectedHashes)
        return JsonObject(receipt)
    }

    /**
     * `verify`: re-derive the partial archive from the receipt, the approved suite, and the raw
     * bytes. Every recorded digest is recomputed here.
     */
    fun verify(rootInput: Path, repositoryInput: Path, expectedHashes: Map<String, String>): JsonObject {
        val root = rootInput.toAbsolutePath().normalize()
        val repository = repositoryInput.toAbsolutePath().normalize()
        val receipt = StrictJson.load(
            String(Files.readAllBytes(root.resolve("receipt.json")), StandardCharsets.UTF_8),
        ) as? JsonObject ?: throw IllegalArgumentException("partial receipt seal differs")
        val seal = Py.str(receipt["seal_sha256"])
        val withoutSeal = LinkedHashMap(receipt).apply { remove("seal_sha256") }
        if (seal != sha(encoded(JsonObject(withoutSeal)))) {
            throw IllegalArgumentException("partial receipt seal differs")
        }
        val manifest = IndependentGates.loadApprovedManifest(repository)
        val selected = (IndependentGates.consumerContract(
            manifest,
            FullStagedConsumerRules.LANE,
        )["cases"] as JsonArray).map { it as JsonObject }
        val selectedIds = selected.mapNotNull { Py.str(it["id"]) }.sorted()
        val contract = classContract(
            manifest,
            FullStagedConsumerRules.LANE,
            FullStagedConsumerRules.CLASS,
        )
        val candidate = Py.str(receipt["candidate_sha"])
        if (candidate == null || !Py.SHA40.matches(candidate) ||
            sha(gitBlob(repository, candidate, contract.source)) != contract.sourceHash
        ) {
            throw IllegalArgumentException("partial receipt candidate source differs")
        }
        fun int(key: String): Long? =
            (receipt[key] as? JsonPrimitive)?.takeIf { Py.isInt(it) }?.let { Py.int(it) }
        val expectedIds = JsonArray(selectedIds.map { JsonPrimitive(it) })
        val receiptIds = receipt["selected_case_ids"] as? JsonArray
        val observed = (receipt["observed_case_ids"] as? JsonArray)?.mapNotNull { Py.str(it) }
        if (!Py.equalsInt(receipt["schema"], 1) ||
            Py.str(receipt["kind"]) != "full-staged-consumer-partial" ||
            Py.str(receipt["status"]) != "NOT_RUN" ||
            receipt["complete_selected_suite"] != JsonPrimitive(false) ||
            Py.str(receipt["lane"]) != FullStagedConsumerRules.LANE ||
            Py.str(receipt["manifest_sha256"]) != IndependentGates.digest(manifest) ||
            int("selected_case_count") != selected.size.toLong() ||
            receiptIds != expectedIds ||
            Py.str(receipt["selected_case_ids_sha256"]) != sha(encoded(expectedIds)) ||
            observed != contract.ids.sorted() ||
            int("remaining_case_count") != (selected.size - contract.ids.size).toLong() ||
            Py.str(receipt["original_source"]) != contract.source ||
            Py.str(receipt["original_source_sha256"]) != contract.sourceHash ||
            Py.str(receipt["consumer_build_sha256"]) != sha(
                gitBlob(
                    repository,
                    candidate,
                    "consumers/qualification/portable/build.gradle.kts",
                ),
            ) ||
            (receipt["expected_artifact_hashes"] as? JsonObject)
                ?.mapValues { Py.str(it.value) } != expectedHashes
        ) {
            throw IllegalArgumentException("partial receipt contract differs from approved suite")
        }
        val toolchain = receipt["toolchain"] as? JsonObject
        val javaVersion = Py.str(toolchain?.get("java_version")) ?: ""
        if (toolchain == null || !javaVersion.startsWith("openjdk version \"21") ||
            Py.str(toolchain["gradle_version"]) != "Gradle 9.5.0" ||
            listOf("java_sha256", "gradle_sha256").any {
                !Py.SHA64.matches(Py.str(toolchain[it]) ?: "")
            }
        ) {
            throw IllegalArgumentException("partial receipt toolchain identity differs")
        }
        if (receipt["files"] != inventory(root)) {
            throw IllegalArgumentException("partial archive file inventory differs")
        }
        val xmlName = "TEST-${FullStagedConsumerRules.CLASS}.xml"
        val exactFiles = mutableSetOf(
            "raw/test.stdout", "raw/test.stderr", "raw/graph.stdout", "raw/graph.stderr",
            "raw/$xmlName",
        )
        for (module in FullStagedConsumerRules.MODULES) {
            exactFiles.add("resolved/${FullStagedConsumerRules.stagedBinaryName(module)}")
        }
        val files = (receipt["files"] as? JsonObject)?.keys ?: emptySet()
        if (files != exactFiles || Py.str(receipt["consumer_xml"]) != "raw/$xmlName") {
            throw IllegalArgumentException("partial archive file set differs")
        }
        val raw = Files.readAllBytes(root.resolve(Py.str(receipt["consumer_xml"])!!))
        rawCaseIds(raw, contract.ids)
        val test = receipt["test_process"] as? JsonObject
            ?: throw IllegalArgumentException("partial consumer process binding differs")
        val graphProcess = receipt["graph_process"] as? JsonObject
            ?: throw IllegalArgumentException("partial consumer process binding differs")
        val sourceArgument = contract.source.split("src/commonTest/kotlin/", limit = 2)[1]
        for ((record, task) in listOf(test to "jvmTest", graphProcess to "qualificationSuiteGraph")) {
            val command = (record["command"] as? JsonArray)?.mapNotNull { Py.str(it) }
                ?: emptyList()
            val started = if (Py.isInt(record["started_ns"])) Py.int(record["started_ns"]) else 0L
            val finished = if (Py.isInt(record["finished_ns"])) Py.int(record["finished_ns"]) else 0L
            if (!Py.equalsInt(record["exit_code"], 0L) ||
                Py.str(record["cwd"]) != repository.toString() ||
                command.lastOrNull() != task ||
                "--offline" !in command ||
                "-PqualificationLaneId=${FullStagedConsumerRules.LANE}" !in command ||
                "-PqualificationSuiteCheckout=$repository" !in command ||
                "-PqualificationSuiteSource=$sourceArgument" !in command ||
                command.drop(1).take(2) !=
                listOf("-p", repository.resolve("consumers/qualification/portable").toString()) ||
                !(0L < started && started <= finished)
            ) {
                throw IllegalArgumentException("partial consumer process binding differs")
            }
        }
        if (Py.str(test["stdout"]) != "raw/test.stdout" ||
            Py.str(test["stderr"]) != "raw/test.stderr" ||
            Py.str(graphProcess["stdout"]) != "raw/graph.stdout" ||
            Py.str(graphProcess["stderr"]) != "raw/graph.stderr" ||
            "--rerun-tasks" !in ((test["command"] as JsonArray).mapNotNull { Py.str(it) })
        ) {
            throw IllegalArgumentException("partial consumer raw process files differ")
        }
        if (Py.int(test["finished_ns"]!!) > Py.int(graphProcess["started_ns"]!!)) {
            throw IllegalArgumentException("partial consumer process chronology differs")
        }
        val testOutput = Files.readString(root.resolve(Py.str(test["stdout"])!!))
        if (listOf("compileTestKotlinJvm", "qualificationSuiteGraph", "jvmTest").any { task ->
                testOutput.lines().none { it.trim() == "> Task :$task" }
            } ||
            !testOutput.contains("BUILD SUCCESSFUL")
        ) {
            throw IllegalArgumentException("raw external test task output differs")
        }
        val xmlMtime = Files.getLastModifiedTime(root.resolve(Py.str(receipt["consumer_xml"])!!))
            .to(TimeUnit.NANOSECONDS)
        if (!(Py.int(test["started_ns"]!!) <= xmlMtime &&
                xmlMtime <= Py.int(test["finished_ns"]!!))
        ) {
            throw IllegalArgumentException(
                "raw external test report was not produced in the process window",
            )
        }
        val graph = FullStagedConsumerRules.graphFromOutput(
            Files.readString(root.resolve(Py.str(graphProcess["stdout"])!!)),
        )
        if (graph != FullStagedConsumerRules.graphFromOutput(
                Files.readString(root.resolve(Py.str(test["stdout"])!!)),
            )
        ) {
            throw IllegalArgumentException("test process provider graph differs from replay graph")
        }
        if (Py.str(graph["gradle_user_home"]) != Py.str(toolchain["gradle_user_home"])) {
            throw IllegalArgumentException("recorded Gradle user home differs from observed runtime")
        }
        val staging = Path.of(Py.str(receipt["staging_repository"]) ?: "")
        if (!staging.isAbsolute) {
            throw IllegalArgumentException("recorded staging repository is not absolute")
        }
        val artifacts = graphArtifacts(graph, staging, expectedHashes)
        for ((module, item) in artifacts) {
            val copied = root.resolve("resolved").resolve(Py.str(item["name"])!!)
            if (sha(Files.readAllBytes(copied)) != expectedHashes[module] ||
                Files.size(copied) != Py.int(item["size"]!!)
            ) {
                throw IllegalArgumentException("resolved staged binary bytes differ")
            }
        }
        return receipt
    }

    /** `main`: `run` or `verify` with the two independent expected artifact hashes. */
    fun main(arguments: Array<String>): Int {
        var action: String? = null
        val values = LinkedHashMap<String, String>()
        var index = 0
        val allowed = setOf(
            "repository", "expected-core-sha256", "expected-facade-sha256", "candidate-sha",
            "staging", "output", "gradle", "archive",
        )
        while (index < arguments.size) {
            val argument = arguments[index]
            if (argument == "run" || argument == "verify") {
                if (action != null) return usage("unrecognized arguments: $argument")
                action = argument
                index++
                continue
            }
            if (!argument.startsWith("--")) return usage("unrecognized arguments: $argument")
            val name = argument.removePrefix("--")
            if (name !in allowed) return usage("unrecognized arguments: $argument")
            val value = next(arguments, ++index) ?: return usage("argument $argument: expected one argument")
            values[name] = value
            index++
        }
        if (action == null) return usage("the following arguments are required: action")
        for (required in listOf("repository", "expected-core-sha256", "expected-facade-sha256")) {
            if (required !in values) return usage("the following arguments are required: --$required")
        }
        val runOnly = listOf("candidate-sha", "staging", "output", "gradle")
        if (action == "run") {
            for (required in runOnly) {
                if (required !in values) {
                    return usage("the following arguments are required: --$required")
                }
            }
        } else if ("archive" !in values) {
            return usage("the following arguments are required: --archive")
        }
        val hashes = linkedMapOf(
            "dyn4k-core" to values.getValue("expected-core-sha256"),
            "dyn4k" to values.getValue("expected-facade-sha256"),
        )
        if (hashes.values.any { !Py.SHA64.matches(it) }) {
            return usage("independent expected artifact hashes are required")
        }
        val result = try {
            if (action == "run") {
                run(
                    Path.of(values.getValue("repository")),
                    values.getValue("candidate-sha"),
                    Path.of(values.getValue("staging")),
                    Path.of(values.getValue("output")),
                    Path.of(values.getValue("gradle")),
                    hashes,
                )
            } else {
                verify(
                    Path.of(values.getValue("archive")),
                    Path.of(values.getValue("repository")),
                    hashes,
                )
            }
        } catch (error: Exception) {
            System.err.println(error.message ?: error.toString())
            return 1
        }
        println(
            buildJsonObject {
                put("status", result["status"] ?: JsonNull)
                put("candidate_sha", result["candidate_sha"] ?: JsonNull)
                put(
                    "observed",
                    JsonPrimitive((result["observed_case_ids"] as? JsonArray)?.size ?: 0),
                )
                put(
                    "selected",
                    result["selected_case_count"] ?: JsonNull,
                )
            }.let { CanonicalJson.render(it) },
        )
        return 0
    }

    private fun next(arguments: Array<String>, index: Int): String? =
        if (index < arguments.size) arguments[index] else null

    private fun usage(message: String): Int {
        System.err.println("usage error: $message")
        return 2
    }

    /** `subprocess.check_output`: merged stderr, text output, failing exit status propagates. */
    private fun output(command: List<String>): String {
        val process = ProcessBuilder(command).redirectErrorStream(true).start()
        val combined = process.inputStream.use { it.readBytes() }
        process.waitFor()
        if (process.exitValue() != 0) {
            throw IllegalArgumentException("auditor tool execution failed: ${command.first()}")
        }
        return String(combined, StandardCharsets.UTF_8)
    }
}
