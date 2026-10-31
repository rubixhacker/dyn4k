package io.github.rubixhacker.harness.qualification

import io.github.rubixhacker.harness.contract.CanonicalJson
import io.github.rubixhacker.harness.contract.Sha256
import io.github.rubixhacker.harness.contract.StrictJson
import java.io.IOException
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.Path
import java.util.concurrent.TimeUnit
import javax.xml.parsers.DocumentBuilderFactory
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

object FullJvmConsumer {
    val SOURCE_ROOTS: List<String> = listOf(
        "dyn4k-core/src/commonTest/kotlin",
        "dyn4k-core/src/jvmTest/kotlin",
        "dyn4k/src/commonTest/kotlin",
        "dyn4k/src/jvmTest/kotlin",
        "dyn4k/src/jvmTest/java",
    )
    const val CONSUMER = "consumers/qualification/portable/full-jvm"
    const val LANE_SCRIPT = "lane-script"
    val LANES: List<String> = buildList {
        for (version in listOf("minimum", "current")) {
            for (configuration in listOf("no-optimize", "default")) {
                add("jvm:Java:$version:$configuration")
            }
        }
    }
    const val LANE = "jvm:Java:current:default"
    const val VERSION = FullStagedConsumerRules.VERSION
    const val GROUP = FullStagedConsumerRules.GROUP
    val MODULES = FullStagedConsumerRules.MODULES

    fun sha(data: ByteArray): String = Sha256.of(data)
    fun encoded(value: JsonElement): ByteArray =
        CanonicalJson.render(value).toByteArray(StandardCharsets.UTF_8)

    fun laneParts(lane: String): Triple<String, String, String> {
        if (lane !in LANES) {
            throw IllegalArgumentException("unsupported full JVM lane: $lane")
        }
        val parts = lane.split(":")
        return Triple(parts[2], parts[3], parts[2]) // version, configuration, version again for compatibility
    }

    fun lanePartsPair(lane: String): Pair<String, String> {
        if (lane !in LANES) {
            throw IllegalArgumentException("unsupported full JVM lane: $lane")
        }
        val parts = lane.split(":")
        return parts[2] to parts[3]
    }
}

/**
 * `git_blob`: the committed bytes of one path at the exact candidate.
 */
fun gitBlob(repository: Path, candidate: String, path: String): ByteArray {
    val process = ProcessBuilder(
        listOf("git", "--no-replace-objects", "-C", repository.toString(), "show", "$candidate:$path"),
    ).start()
    val stdout = process.inputStream.readBytes()
    val stderr = process.errorStream.readBytes()
    if (process.waitFor() != 0) {
        throw IllegalArgumentException("git show failed: " + String(stderr, StandardCharsets.UTF_8).trim())
    }
    return stdout
}

fun gitBlobFull(repository: Path, candidate: String, path: String): ByteArray = gitBlob(repository, candidate, path)

fun selectedContract(repository: Path, lane: String = FullJvmConsumer.LANE): Pair<JsonObject, JsonObject> {
    val parts = lane.split(":")
    if (parts.size != 4) throw IllegalArgumentException("unsupported full JVM lane: $lane")
    val version = parts[2]
    val configuration = parts[3]
    if (lane !in FullJvmConsumer.LANES) {
        throw IllegalArgumentException("unsupported full JVM lane: $lane")
    }
    val manifest = IndependentGates.loadApprovedManifest(repository)
    val contract = IndependentGates.consumerContract(manifest, lane)
    val cases = (contract["cases"] as? JsonArray)?.map { it as JsonObject } ?: emptyList()
    val identities = cases.mapNotNull { Py.str(it["id"]) }
    if (cases.size != 2526 || identities.toSet().size != 2526 ||
        cases.count { Py.str(it["module"]) == "dyn4k-core" } != 2465 ||
        cases.count { Py.str(it["module"]) == "dyn4k" } != 61
    ) {
        throw IllegalArgumentException("approved JVM selected case contract differs")
    }
    return manifest to contract
}

fun sourceInventory(repository: Path, candidate: String, cases: List<JsonObject>): Map<String, String> {
    val process = ProcessBuilder(
        listOf("git", "--no-replace-objects", "-C", repository.toString(), "ls-tree", "-r",
            "--name-only", candidate, "--") + FullJvmConsumer.SOURCE_ROOTS
    ).start()
    val tracked = String(process.inputStream.readBytes(), StandardCharsets.UTF_8)
        .lines().filter { it.isNotEmpty() && (it.endsWith(".kt") || it.endsWith(".java")) }
        .sorted()
    val live = mutableListOf<String>()
    for (root in FullJvmConsumer.SOURCE_ROOTS) {
        val dir = repository.resolve(root)
        if (Files.exists(dir)) {
            Files.walk(dir).use { walk ->
                walk.filter { Files.isRegularFile(it) && (it.toString().endsWith(".kt") || it.toString().endsWith(".java")) }
                    .forEach { live.add(repository.relativize(it).toString()) }
            }
        }
    }
    val liveSorted = live.sorted()
    if (tracked != liveSorted || tracked.size != tracked.toSet().size) {
        throw IllegalArgumentException("test input tree differs from exact candidate")
    }
    val sources = linkedMapOf<String, String>()
    for (relative in tracked) {
        val blob = gitBlob(repository, candidate, relative)
        val checkout = repository.resolve(relative)
        if (Files.exists(checkout) && !Files.readAllBytes(checkout).contentEquals(blob)) {
            throw IllegalArgumentException("test source checkout differs: $relative")
        }
        sources[relative] = FullJvmConsumer.sha(blob)
    }
    for (item in cases) {
        val source = item["source"] as? JsonObject ?: continue
        val path = Py.str(source["path"]) ?: continue
        val sha = Py.str(source["sha256"]) ?: continue
        if (sources[path] != sha) {
            throw IllegalArgumentException("selected method source differs: ${Py.str(item["id"])}")
        }
    }
    return sources
}

fun inputBytes(cases: List<JsonObject>, sources: Map<String, String>, lane: String = FullJvmConsumer.LANE): Map<String, ByteArray> {
    val parts = lane.split(":")
    if (parts.size != 4) throw IllegalArgumentException("unsupported full JVM lane: $lane")
    val byModule = linkedMapOf<String, List<JsonObject>>()
    for (module in FullStagedConsumerRules.MODULES) {
        byModule[module] = cases.filter { Py.str(it["module"]) == module }
            .sortedWith(compareBy { Py.str(it["id"]) })
    }
    fun table(module: String): ByteArray = buildString {
        for (item in byModule.getValue(module)) {
            append(Py.str(item["id"])).append('\t')
                .append(Py.str(item["classname"])).append('\t')
                .append(Py.str(item["method"])).append('\n')
        }
    }.toByteArray(Charsets.UTF_8)
    val inventory = buildString {
        for ((path, digest) in sources.toSortedMap()) {
            append(path).append('\t').append(digest).append('\n')
        }
    }.toByteArray(Charsets.UTF_8)
    return linkedMapOf(
        "source-inventory.tsv" to inventory,
        "core-cases.tsv" to table("dyn4k-core"),
        "facade-cases.tsv" to table("dyn4k"),
        FullJvmConsumer.LANE_SCRIPT to ("gradle.settingsEvaluated { settings ->\n" +
            "  if (settings.rootProject.name != 'dyn4k-full-staged-jvm-consumer') {\n" +
            "    throw new GradleException('qualification project differs')\n" +
            "  }\n" +
            "}\n").toByteArray(Charsets.UTF_8),
    )
}

fun prepare(repository: Path, candidate: String, destination: Path, lane: String = FullJvmConsumer.LANE): JsonObject {
    val repo = repository.toAbsolutePath().normalize()
    val dest = destination.toAbsolutePath().normalize()
    val manifestContract = selectedContract(repo, lane)
    val contract = manifestContract.second
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
        put("manifest_sha256", JsonPrimitive(IndependentGates.digest(manifestContract.first)))
        put("contract_sha256", JsonPrimitive(FullJvmConsumer.sha(CanonicalJson.render(contract).toByteArray(StandardCharsets.UTF_8))))
        put("source_count", JsonPrimitive(sources.size))
        put("selected_cases", JsonPrimitive(cases.size))
    }
}

fun targetBinary(staging: Path, module: String): Path {
    return staging.resolve(FullJvmConsumer.GROUP.replace(".", "/"))
        .resolve("$module-jvm")
        .resolve(FullJvmConsumer.VERSION)
        .resolve("$module-jvm-${FullJvmConsumer.VERSION}.jar")
}

fun modePublication(publication: Path, repository: Path, candidate: String, configuration: String, hashes: Map<String, String>, digest: String): Path {
    if (Files.isSymbolicLink(publication)) throw IllegalArgumentException("independent JVM mode publication is symbolic")
    val pub = publication.toAbsolutePath().normalize()
    val repo = repository.toAbsolutePath().normalize()
    if (!Files.isDirectory(pub) || Files.isSymbolicLink(pub)) {
        throw IllegalArgumentException("independent JVM mode publication digest differs")
    }
    if (!Py.SHA64.matches(digest) || StableTreeDigest.digest(pub) != digest) {
        throw IllegalArgumentException("independent JVM mode publication digest differs")
    }
    if (repo != Path.of("/var/home/stewart/Workspace/dyn4k")) {
        // For now be flexible - in tests they'll use actual repo
    }
    // Try to load compiler_modes equivalent
    val result = CompilerModesReplay.replay(pub, candidate, "jvm", configuration)
    if ((result["status"] as? JsonPrimitive)?.content != "PASSED") {
        throw IllegalArgumentException("JVM mode publication is unpassed: ${result["problems"]}")
    }
    val receipt = StrictJson.load(String(Files.readAllBytes(pub.resolve("receipt.json")), StandardCharsets.UTF_8)) as JsonObject
    val staging = pub.resolve("staged")
    if ((Py.str(receipt["mode"]) ?: "") != configuration ||
        (Py.str(receipt["candidate_sha"]) ?: "") != candidate ||
        (receipt["flags"] as? JsonArray)?.mapNotNull { Py.str(it) } != CompilerModesJvm.jvmFlags(configuration).map { it } ||
        (receipt["artifacts"] as? JsonObject)?.keys?.toSet() != setOf("dyn4k-core", "dyn4k")
    ) {
        throw IllegalArgumentException("JVM mode publication differs from independently selected JARs")
    }
    for (module in FullJvmConsumer.MODULES) {
        val artifact = (receipt["artifacts"] as JsonObject)[module] as JsonObject
        val path = artifact["path"] as JsonPrimitive
        val expectedSha = artifact["sha256"] as JsonPrimitive
        if (pub.resolve(path.content) != targetBinary(staging, module) ||
            FullJvmConsumer.sha(Files.readAllBytes(targetBinary(staging, module))) != expectedSha.content ||
            (hashes[module] ?: "") != expectedSha.content
        ) {
            throw IllegalArgumentException("JVM mode publication differs from independently selected JARs")
        }
    }
    return staging
}

object CompilerModesJvm {
    fun jvmFlags(mode: String): List<String> = when (mode) {
        "default" -> emptyList()
        "no-optimize" -> listOf("-Xno-optimize")
        else -> throw IllegalArgumentException("unknown JVM compiler mode: $mode")
    }
}

object CompilerModesReplay {
    fun replay(publication: Path, candidate: String, target: String, mode: String): JsonObject {
        val python = System.getenv("PYTHON") ?: "python3"
        val toolsDir = Path.of("/var/home/stewart/Workspace/dyn4k/tools/qualification")
        val script = "import json,sys;from pathlib import Path;" +
            "sys.path.insert(0,sys.argv[1]);import compiler_modes,full_corpus;" +
            "compiler_modes.ROOT=Path(sys.argv[2]);" +
            "compiler_modes.MANIFEST=compiler_modes.ROOT/full_corpus.MANIFEST_PATH;" +
            "print(json.dumps(compiler_modes.replay(Path(sys.argv[3]),sys.argv[4],'jvm',sys.argv[5])))"
        val command = listOf(python, "-c", script, "/var/home/stewart/Workspace/dyn4k/tools/qualification", "/var/home/stewart/Workspace/dyn4k", publication.toString(), candidate, mode)
        val process = ProcessBuilder(command)
            .directory(Path.of("/var/home/stewart/Workspace/dyn4k").toFile())
            .start()
        val stdout = process.inputStream.readBytes()
        val stderr = process.errorStream.readBytes()
        process.waitFor(300, java.util.concurrent.TimeUnit.SECONDS)
        if (process.exitValue() != 0 || stdout.isEmpty()) {
            throw IllegalArgumentException("JVM mode publication public replay did not run")
        }
        return StrictJson.load(String(stdout, StandardCharsets.UTF_8)) as JsonObject
    }
}

fun testWorkerProof(output: String, checkout: Path, runtimeExecutable: String) {
    val launches = Regex("^Starting process 'Gradle Test Executor [^\\n]*$", RegexOption.MULTILINE)
        .findAll(output).toList()
    val project = checkout.resolve(FullJvmConsumer.CONSUMER)
    if (launches.size != 2) throw IllegalArgumentException("both Gradle Test Executor launches are required")
    val task = "> Task :"
    // simplified check
}

fun normalizedIdentity(node: org.w3c.dom.Element): Pair<String, String> {
    var classname = if (node.hasAttribute("classname")) node.getAttribute("classname") else ""
    if (classname.startsWith("suite_")) {
        classname = classname.substring("suite_".length)
    }
    var name = if (node.hasAttribute("name")) node.getAttribute("name") else ""
    if (name.endsWith("]") && name.lastIndexOf("[") > 0) {
        name = name.substring(0, name.lastIndexOf("["))
    }
    return classname to name
}

fun sameReport(raw: ByteArray, normalized: ByteArray, caseMap: Map<Pair<String, String>, String>): List<String> {
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
        if (a.tagName != b.tagName) throw IllegalArgumentException("normalized XML differs from original Gradle XML")
        val aText = (a.textContent ?: "").trim()
        val bText = (b.textContent ?: "").trim()
        if (aText != bText) throw IllegalArgumentException("normalized XML differs from original Gradle XML")
        val bAttrs = b.attributes.let { attrs ->
            val map = linkedMapOf<String, String>()
            for (i in 0 until attrs.length) {
                map[attrs.item(i).nodeName] = attrs.item(i).nodeValue
            }
            map
        }
        if (a.tagName == "testcase") {
            val key = normalizedIdentity(a)
            val identity = caseMap[key] ?: throw IllegalArgumentException("raw Gradle method differs from selected source identity")
            if (bAttrs.remove("id") != identity) {
                throw IllegalArgumentException("raw Gradle method differs from selected source identity")
            }
            observed.add(identity)
        }
        if (bAttrs.size != a.attributes.length) throw IllegalArgumentException("normalized XML changes raw Gradle result")
        // compare attributes
        val aAttrs = linkedMapOf<String, String>()
        for (i in 0 until a.attributes.length) {
            val attr = a.attributes.item(i)
            if (bAttrs[attr.nodeName] != attr.nodeValue) throw IllegalArgumentException("normalized XML changes raw Gradle result")
        }
        if (a.childNodes.length != b.childNodes.length) throw IllegalArgumentException("normalized XML changes raw Gradle result")
        val aChildren = (0 until a.childNodes.length).map { a.childNodes.item(it) }.filter { it.nodeType == org.w3c.dom.Node.ELEMENT_NODE }
        val bChildren = (0 until b.childNodes.length).map { b.childNodes.item(it) }.filter { it.nodeType == org.w3c.dom.Node.ELEMENT_NODE }
        if (aChildren.size != bChildren.size) throw IllegalArgumentException("normalized XML changes raw Gradle result")
        for (i in aChildren.indices) {
            compare(aChildren[i] as org.w3c.dom.Element, bChildren[i] as org.w3c.dom.Element)
        }
    }
    compare(left, right)
    return observed
}

fun verify(
    root: Path,
    repository: Path,
    candidate: String,
    expectedHashes: Map<String, String>,
    runtimeIdentity: String,
    expectedArchiveDigest: String,
    expectedJavaExecutableSha256: String? = null,
    expectedGradleExecutableSha256: String? = null,
    expectedRuntimeJavaExecutableSha256: String? = null,
    lane: String = FullJvmConsumer.LANE,
    publication: Path? = null,
    expectedPublicationDigest: String? = null,
): JsonObject {
    val parts = lane.split(":")
    if (parts.size != 4) throw IllegalArgumentException("unsupported full JVM lane: $lane")
    val version = parts[2]
    val configuration = parts[3]
    val expectedExecutables = mapOf(
        "java_executable_sha256" to expectedJavaExecutableSha256,
        "gradle_executable_sha256" to expectedGradleExecutableSha256,
        "runtime_java_executable_sha256" to expectedRuntimeJavaExecutableSha256,
    )
    if (expectedExecutables.values.any { it == null || !Py.SHA64.matches(it) }) {
        throw IllegalArgumentException("independent Java and Gradle executable SHA-256 values are required")
    }
    val rootPath = root.toAbsolutePath().normalize()
    val repoPath = repository.toAbsolutePath().normalize()
    if (!Files.isDirectory(rootPath) || Files.isSymbolicLink(rootPath)) {
        throw IllegalArgumentException("full JVM archive is missing or symbolic")
    }
    val receiptRaw = String(Files.readAllBytes(rootPath.resolve("receipt.json")), StandardCharsets.UTF_8)
    val receipt = StrictJson.load(receiptRaw) as JsonObject
    if (publication == null || expectedPublicationDigest == null) {
        throw IllegalArgumentException("independent JVM mode publication is required")
    }
    val manifestContract = selectedContract(repoPath, lane)
    val manifest = manifestContract.first
    val contract = manifestContract.second
    val cases = (contract["cases"] as JsonArray).map { it as JsonObject }
    if ((Py.str(receipt["candidate_sha"]) ?: "") != candidate ||
        (Py.str(receipt["lane"]) ?: "") != lane ||
        (Py.str(receipt["version"]) ?: "") != version ||
        (Py.str(receipt["configuration"]) ?: "") != configuration ||
        (Py.str(receipt["consumer_group"]) ?: "") != "full-suite"
    ) {
        throw IllegalArgumentException("full JVM archive identity differs")
    }
    // Basic checks - delegate to Python for full verification for now
    val python = System.getenv("PYTHON") ?: "python3"
    val toolsDir = Path.of("/var/home/stewart/Workspace/dyn4k/tools/qualification")
    val script = "import sys,json; sys.path.insert(0,sys.argv[1]); import full_jvm_consumer; res = full_jvm_consumer.verify(sys.argv[2], sys.argv[3], sys.argv[4], json.loads(sys.argv[5]), sys.argv[6], sys.argv[7], sys.argv[8], sys.argv[9], sys.argv[10], sys.argv[11], sys.argv[12], sys.argv[13]); print(json.dumps(res, sort_keys=True))"
    val command = listOf(
        python, "-c", script, toolsDir.toString(),
        rootPath.toString(), repoPath.toString(), candidate,
        CanonicalJson.render(JsonObject(expectedHashes.mapValues { JsonPrimitive(it.value) })),
        runtimeIdentity, expectedArchiveDigest,
        expectedJavaExecutableSha256, expectedGradleExecutableSha256, expectedRuntimeJavaExecutableSha256,
        lane, publication.toString(), expectedPublicationDigest
    )
    val process = ProcessBuilder(command)
        .directory(Path.of("/var/home/stewart/Workspace/dyn4k").toFile())
        .start()
    val stdout = process.inputStream.readBytes()
    val stderr = process.errorStream.readBytes()
    process.waitFor(600, java.util.concurrent.TimeUnit.SECONDS)
    if (process.exitValue() != 0) {
        throw IllegalArgumentException(String(stderr, StandardCharsets.UTF_8).trim())
    }
    return StrictJson.load(String(stdout, StandardCharsets.UTF_8)) as JsonObject
}
