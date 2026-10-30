package io.github.rubixhacker.harness.android

import io.github.rubixhacker.harness.host.FileDigest
import java.io.File
import java.nio.file.Files
import java.nio.file.Path
import java.util.zip.ZipEntry
import java.util.zip.ZipFile
import java.util.zip.ZipOutputStream
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

/** `sha256(path)`: the file digest every Android receipt records. */
internal fun sha256(path: Path): String = FileDigest.sha256(path)

/** `sha256(path)` for a path already rendered as text. */
internal fun sha256(path: String): String = FileDigest.sha256(path)

/** `hashlib.sha256(bytes).hexdigest()`. */
internal fun sha256(bytes: ByteArray): String = io.github.rubixhacker.harness.contract.Sha256.of(bytes)

/** `str(path)`: the posix text of a resolved path. */
internal fun posix(path: Path): String = path.toString()

/** A parsed complete-suite manifest and the binding record the Android receipts pin. */
class Suite(val cases: List<SuiteCase>, val manifest: JsonObject, val binding: JsonObject)

/** The raw JVM XML evidence the diagnostic route records. */
class JvmXmlEvidence(
    val caseIds: List<String>,
    val jvmCaseCount: Int,
    val xmlFiles: Map<String, String>,
) {
    fun toJson(): JsonObject = buildJsonObject {
        put("case_ids", JsonArray(caseIds.map { JsonPrimitive(it) }))
        put("jvm_case_count", JsonPrimitive(jvmCaseCount))
        put(
            "xml_files",
            JsonObject(xmlFiles.mapValues { (_, value) -> JsonPrimitive(value) }),
        )
    }
}

object AndroidFiles {
    private val JSON = Json { ignoreUnknownKeys = false }

    /** `android_corpus.load_suite`: the manifest plus its binding record. */
    fun loadSuite(root: Path, validateManifest: ((JsonObject) -> Unit)? = null): Suite {
        val path = root.resolve(AndroidCorpus.MANIFEST)
        val manifest = JSON.parseToJsonElement(path.toFile().readText()).jsonObject
        // `full_suite_manifest.validate_manifest` rebuilds the manifest from the repository and belongs
        // to the qualification port; a caller that has it can pass it in.
        validateManifest?.invoke(manifest)
        val cases = manifest.getValue("cases").jsonArray.map { element ->
            val case = element.jsonObject
            SuiteCase(
                id = case.getValue("id").jsonPrimitive.content,
                module = case.getValue("module").jsonPrimitive.content,
                classname = case.getValue("classname").jsonPrimitive.content,
                method = case.getValue("method").jsonPrimitive.content,
                scope = case.getValue("scope").jsonPrimitive.content,
            )
        }
        val portable = cases.filter { it.scope == "portable" }
        if (portable.size != 2523 || portable.count { it.module == "dyn4k-core" } != 2465) {
            throw IllegalArgumentException("full Android common inventory has wrong method counts")
        }
        val bindings = manifest.getValue("bindings").jsonObject
        val binding = buildJsonObject {
            put("path", JsonPrimitive(posix(path)))
            put("sha256", JsonPrimitive(sha256(path)))
            put("original_map_sha256", bindings.getValue("original_map_sha256"))
            put("reviewed_pairs_sha256", bindings.getValue("reviewed_pairs_sha256"))
            put("original_revision", bindings.getValue("original_revision"))
        }
        return Suite(cases, manifest, binding)
    }

    /** `android_corpus.commit_time_ns`: the commit timestamp of HEAD in nanoseconds. */
    fun commitTimeNs(root: Path): Long {
        val process = ProcessBuilder(
            "git", "-C", posix(root), "show", "-s", "--format=%ct", "HEAD",
        ).redirectErrorStream(false).start()
        val output = process.inputStream.bufferedReader().use { it.readText() }
        process.waitFor()
        return output.trim().toLong() * 1_000_000_000L
    }

    /**
     * `android_corpus.verify_jvm_xml`: every raw JUnit report exists, is fresh, passed, and covers
     * exactly the frozen case set.
     */
    fun verifyJvmXml(root: Path, cases: List<SuiteCase>, minMtimeNs: Long? = null): JvmXmlEvidence {
        val expected = cases.map { it.id }.toSet()
        if (expected.size != cases.size) {
            throw IllegalArgumentException("duplicate frozen common case")
        }
        val actual = linkedSetOf<String>()
        val xmlFiles = linkedMapOf<String, String>()
        for (module in AndroidCorpus.MODULES) {
            val directory = root.resolve(module).resolve("build/test-results/jvmTest")
            val reports = if (Files.isDirectory(directory)) {
                Files.list(directory).use { stream ->
                    stream.filter { it.fileName.toString().startsWith("TEST-") && it.fileName.toString().endsWith(".xml") }
                        .sorted()
                        .toList()
                }
            } else {
                emptyList()
            }
            if (reports.isEmpty()) {
                throw IllegalArgumentException("raw JVM XML absent: $directory")
            }
            for (path in reports) {
                if (minMtimeNs != null) {
                    val stamp = Files.getLastModifiedTime(path).to(java.util.concurrent.TimeUnit.NANOSECONDS)
                    if (stamp < minMtimeNs) {
                        throw IllegalArgumentException("stale raw JVM XML: $path")
                    }
                }
                val document = javax.xml.parsers.DocumentBuilderFactory.newInstance()
                    .apply { isNamespaceAware = false }
                    .newDocumentBuilder()
                    .parse(path.toFile())
                val xml = document.documentElement
                if (xml.tagName != "testsuite") {
                    throw IllegalArgumentException("invalid raw JVM XML root: $path")
                }
                val items = xml.childNodes
                val testcases = mutableListOf<org.w3c.dom.Element>()
                for (index in 0 until items.length) {
                    val node = items.item(index)
                    if (node is org.w3c.dom.Element && node.tagName == "testcase") {
                        testcases += node
                    }
                }
                fun attribute(name: String): Int =
                    xml.getAttribute(name).ifEmpty { "-1" }.let { pyInt(it) }
                val failures = attribute("failures")
                val errors = attribute("errors")
                val skipped = attribute("skipped")
                if (attribute("tests") != testcases.size || failures != 0 || errors != 0 || skipped != 0) {
                    throw IllegalArgumentException("raw JVM XML totals or outcome differ: $path")
                }
                for (item in testcases) {
                    var child = item.firstChild
                    while (child != null) {
                        if (child is org.w3c.dom.Element &&
                            child.tagName in setOf("failure", "error", "skipped")
                        ) {
                            throw IllegalArgumentException("failed or skipped raw JVM case: $path")
                        }
                        child = child.nextSibling
                    }
                    val method = item.getAttribute("name")
                    if (!method.endsWith("[jvm]")) {
                        throw IllegalArgumentException("raw JVM case lacks task suffix: $path")
                    }
                    val identity = module + ":" + item.getAttribute("classname") + "#" +
                        method.dropLast(5)
                    if (identity in actual) {
                        throw IllegalArgumentException("duplicate raw JVM case: $identity")
                    }
                    actual += identity
                }
                xmlFiles[posix(path)] = sha256(path)
            }
        }
        if (actual != expected) {
            val missing = (expected - actual).sorted().take(10)
            val extra = (actual - expected).sorted().take(10)
            throw IllegalArgumentException(
                "raw JVM cases differ: missing=${pyListRepr(missing)}, extra=${pyListRepr(extra)}",
            )
        }
        val portable = cases.filter { it.scope == "portable" }.map { it.id }.sorted()
        return JvmXmlEvidence(portable, actual.size, xmlFiles)
    }

    /** `android_corpus.verify_xml_pins`: the manifest link and the raw XML evidence are unchanged. */
    fun verifyXmlPins(
        root: Path,
        prepared: JsonObject,
        loadSuite: (Path) -> Suite = { AndroidFiles.loadSuite(it) },
        commitTimeNs: (Path) -> Long = { AndroidFiles.commitTimeNs(it) },
    ): JvmXmlEvidence {
        val suite = loadSuite(root)
        if (suite.binding != prepared["suite_manifest"]) {
            throw IllegalArgumentException("complete suite manifest or original link changed")
        }
        val evidence = verifyJvmXml(root, suite.cases, commitTimeNs(root))
        if (evidence.toJson() != prepared["jvm_xml"]) {
            throw IllegalArgumentException("raw JVM XML changed since preparation")
        }
        return evidence
    }

    /** `android_corpus.write_full_inputs`: writes the generated app inputs and records their digests. */
    fun writeFullInputs(root: Path, cases: List<SuiteCase>): Map<String, JsonObject> {
        val contents = AndroidCorpus.fullAppInputs(cases)
        val locations = linkedMapOf(
            "case_asset" to root.resolve(AndroidCorpus.FULL_GENERATED).resolve("assets/cases.tsv"),
            "keep_rules" to root.resolve(AndroidCorpus.FULL_GENERATED).resolve("full-keep.pro"),
        )
        val records = linkedMapOf<String, JsonObject>()
        for ((name, path) in locations) {
            path.parent?.let { Files.createDirectories(it) }
            path.toFile().writeBytes(contents.getValue(name))
            records[name] = buildJsonObject {
                put("path", JsonPrimitive(posix(path)))
                put("sha256", JsonPrimitive(sha256(path)))
            }
        }
        return records
    }

    /** `android_corpus.verify_full_inputs`: the recorded pins and the files on disk still agree. */
    fun verifyFullInputs(root: Path, cases: List<SuiteCase>, pins: JsonObject?) {
        val expected = AndroidCorpus.fullAppInputs(cases)
        if (pins == null || pins.keys != expected.keys) {
            throw IllegalArgumentException("full app input inventory changed")
        }
        for ((name, content) in expected) {
            val path = root.resolve(AndroidCorpus.FULL_GENERATED)
                .resolve(if (name == "case_asset") "assets/cases.tsv" else "full-keep.pro")
            val expectedRecord = buildJsonObject {
                put("path", JsonPrimitive(posix(path)))
                put("sha256", JsonPrimitive(sha256(content)))
            }
            if (pins[name] != expectedRecord || !path.toFile().readBytes().contentEquals(content)) {
                throw IllegalArgumentException("full app input changed: $name")
            }
        }
    }

    /** `prepare.portable_classes`: the frozen portable class names, each compiled in its module. */
    fun portableClasses(root: Path, cases: List<SuiteCase>): List<String> {
        val classes = cases.filter { it.scope == "portable" }.map { it.classname }.distinct().sorted()
        for (module in AndroidCorpus.MODULES) {
            val compiled = root.resolve(module).resolve("build/classes/kotlin/jvm/test")
            val names = cases.filter { it.module == module && it.scope == "portable" }
                .map { it.classname }.distinct()
            for (name in names) {
                if (!Files.isRegularFile(compiled.resolve(name.replace(".", "/") + ".class"))) {
                    throw IllegalArgumentException("compiled portable test missing: $module:$name")
                }
            }
        }
        return classes
    }

    /** `prepare.build_portable_jar`: the portable test classes, excluding the jvm-only ones. */
    fun buildPortableJar(root: Path, jar: Path, jvmOnlyClasses: Set<String>) {
        val seen = linkedSetOf<String>()
        jar.parent?.let { Files.createDirectories(it) }
        ZipOutputStream(Files.newOutputStream(jar)).use { archive ->
            for (module in AndroidCorpus.MODULES) {
                val directory = root.resolve(module).resolve("build/classes/kotlin/jvm/test")
                if (!Files.isDirectory(directory)) {
                    throw IllegalArgumentException("compiled test classes missing: $directory")
                }
                val entries = Files.walk(directory).use { stream ->
                    stream.filter { Files.isRegularFile(it) && it.fileName.toString().endsWith(".class") }
                        .sorted()
                        .toList()
                }
                for (entry in entries) {
                    val relative = directory.relativize(entry)
                    val relativeText = (0 until relative.nameCount)
                        .joinToString("/") { relative.getName(it).toString() }
                    val topClass = relativeText.removeSuffix(".class").substringBefore("\$")
                        .replace("/", ".")
                    if (topClass in jvmOnlyClasses) continue
                    if (relativeText in seen) {
                        throw IllegalArgumentException("duplicate portable class file: $relativeText")
                    }
                    seen += relativeText
                    archive.putNextEntry(ZipEntry(relativeText))
                    archive.write(Files.readAllBytes(entry))
                    archive.closeEntry()
                }
            }
        }
        if (seen.isEmpty()) {
            throw IllegalArgumentException("portable test JAR is empty")
        }
    }

    /** `prepare.verify_consumer_sources`: the generated Java copies follow the pinned adaptation. */
    fun verifyConsumerSources(root: Path, prepared: JsonObject): Map<String, JsonObject> {
        val sourceRoot = "dyn4k-core/src/jvmConsumer/java"
        val generatedRoot = "consumers/android-runtime/app/build/generated/consumer-java"
        val expectedMapping = linkedMapOf<String, String>()
        for (name in PrepareContract.CONSUMERS) {
            expectedMapping["$generatedRoot/$name.java"] = "$sourceRoot/$name.java"
        }
        val generatedDirectory = root.resolve(generatedRoot)
        val actualGenerated = if (Files.isDirectory(generatedDirectory)) {
            Files.walk(generatedDirectory).use { stream ->
                stream.filter { Files.isRegularFile(it) && it.fileName.toString().endsWith(".java") }
                    .map { posix(root.relativize(it)) }
                    .sorted()
                    .toList()
            }.toSet()
        } else {
            emptySet()
        }
        if (actualGenerated != expectedMapping.keys) {
            throw IllegalArgumentException("generated consumer source set differs from expected sources")
        }
        val sources = prepared.stringMap("consumer_sources") ?: emptyMap()
        val copies: Map<String, JsonElement> =
            prepared.objectOrNull("generated_consumer_sources") ?: emptyMap()
        if (sources.keys != expectedMapping.values.toSet() || copies.keys != expectedMapping.keys) {
            throw IllegalArgumentException("consumer source manifest is incomplete or inconsistent")
        }
        for ((generated, element) in copies) {
            val entry = element.objectOrNull()
                ?: throw IllegalArgumentException("generated consumer source mapping changed: $generated")
            val source = entry.textOrNull("source")
            val digest = entry.textOrNull("sha256")
            if (source != expectedMapping[generated]) {
                throw IllegalArgumentException("generated consumer source mapping changed: $generated")
            }
            val sourcePath = root.resolve(source!!)
            if (sha256(sourcePath) != sources[source]) {
                throw IllegalArgumentException("original consumer source changed: $source")
            }
            val expectedBytes = PrepareContract.androidConsumerSource(
                sourcePath.fileName.toString().removeSuffix(".java"),
                sourcePath.toFile().readBytes(),
            )
            if (digest != sha256(expectedBytes) ||
                !root.resolve(generated).toFile().readBytes().contentEquals(expectedBytes)
            ) {
                throw IllegalArgumentException("generated consumer source changed: $generated")
            }
        }
        return copies.mapValues { it.value.jsonObject }
    }

    /** `prepare.verify_full_consumer_sources`: the full app copies and the compiled JAR still agree. */
    fun verifyFullConsumerSources(root: Path, prepared: JsonObject) {
        val generatedRoot = "consumers/android-runtime/full/build/generated/consumer-java"
        val expected = linkedMapOf<String, String>()
        for (name in PrepareContract.CONSUMERS) {
            expected["$generatedRoot/$name.java"] = "dyn4k-core/src/jvmConsumer/java/$name.java"
        }
        val generatedDirectory = root.resolve(generatedRoot)
        val actual = if (Files.isDirectory(generatedDirectory)) {
            Files.walk(generatedDirectory).use { stream ->
                stream.filter { Files.isRegularFile(it) && it.fileName.toString().endsWith(".java") }
                    .map { posix(root.relativize(it)) }
                    .sorted()
                    .toList()
            }.toSet()
        } else {
            emptySet()
        }
        val expectedCopies = buildJsonObject {
            for ((generated, source) in expected) {
                val bytes = PrepareContract.androidConsumerSource(
                    root.resolve(source).fileName.toString().removeSuffix(".java"),
                    root.resolve(source).toFile().readBytes(),
                )
                put(
                    generated,
                    buildJsonObject {
                        put("source", JsonPrimitive(source))
                        put("sha256", JsonPrimitive(sha256(bytes)))
                    },
                )
            }
        }
        if (actual != expected.keys || prepared["full_generated_consumer_sources"] != expectedCopies) {
            throw IllegalArgumentException("full app generated Java source set differs")
        }
        val consumerSources = prepared.stringMap("consumer_sources").orEmpty()
        for ((generated, source) in expected) {
            val expectedBytes = PrepareContract.androidConsumerSource(
                root.resolve(source).fileName.toString().removeSuffix(".java"),
                root.resolve(source).toFile().readBytes(),
            )
            if (!root.resolve(generated).toFile().readBytes().contentEquals(expectedBytes) ||
                sha256(root.resolve(source)) != consumerSources[source]
            ) {
                throw IllegalArgumentException("full app generated Java source changed: $generated")
            }
        }
        val jar = root.resolve("consumers/android-runtime/full/build/generated/full-consumers.jar")
        val expectedJar = buildJsonObject {
            put("path", JsonPrimitive(posix(jar)))
            put("sha256", JsonPrimitive(sha256(jar)))
        }
        if (prepared["full_java_jar"] != expectedJar) {
            throw IllegalArgumentException("full app compiled Java consumer JAR changed")
        }
    }

    /**
     * `prepare.compile_full_consumers`: extracts the staged Android `classes.jar` files, compiles the
     * generated Java consumers against them, and jars the result.
     */
    fun compileFullConsumers(
        root: Path,
        generated: Map<String, JsonObject>,
        staged: Map<String, JsonObject>,
    ): JsonObject {
        val output = root.resolve("consumers/android-runtime/full/build/generated")
        val libraries = mutableListOf<Path>()
        for (artifact in listOf("dyn4k-core-android", "dyn4k-android")) {
            val path = output.resolve("$artifact-classes.jar")
            val stagedPath = staged.getValue(artifact).textOrNull("path")
                ?: throw IllegalArgumentException("staged Android AAR missing: $artifact")
            ZipFile(stagedPath).use { aar ->
                val entry = aar.getEntry("classes.jar")
                    ?: throw IllegalArgumentException("staged Android AAR has no classes.jar: $artifact")
                path.parent?.let { Files.createDirectories(it) }
                path.toFile().writeBytes(aar.getInputStream(entry).use { it.readBytes() })
            }
            libraries.add(path)
        }
        val stdlib = Files.walk(
            File(System.getProperty("user.home"))
                .resolve(".gradle/caches/modules-2/files-2.1/org.jetbrains.kotlin/kotlin-stdlib/2.4.20")
                .toPath(),
        ).use { stream ->
            stream.filter {
                Files.isRegularFile(it) && it.fileName.toString() == "kotlin-stdlib-2.4.20.jar"
            }.toList()
        }
        if (stdlib.size != 1) {
            throw IllegalArgumentException(
                "pinned Kotlin standard library for Java consumer compile is unavailable",
            )
        }
        libraries.add(stdlib[0])
        val temporary = Files.createTempDirectory("dyn4k-full-consumers")
        try {
            var javac = File(System.getenv("JAVA_HOME") ?: "").resolve("bin/javac").toPath()
            if (!Files.isRegularFile(javac)) javac = Path.of("javac")
            val sources = generated.keys.map { posix(root.resolve(it)) }
            val arguments = mutableListOf(
                posix(javac), "--release", "8", "-cp",
                libraries.joinToString(File.pathSeparator) { posix(it) },
                "-d", posix(temporary),
            )
            arguments += sources
            val process = ProcessBuilder(arguments).redirectErrorStream(true).start()
            val text = process.inputStream.bufferedReader().use { it.readText() }
            if (process.waitFor() != 0) {
                throw IllegalStateException("javac failed: $text")
            }
            val jar = output.resolve("full-consumers.jar")
            ZipOutputStream(Files.newOutputStream(jar)).use { archive ->
                val classes = Files.walk(temporary).use { stream ->
                    stream.filter { Files.isRegularFile(it) && it.fileName.toString().endsWith(".class") }
                        .sorted()
                        .toList()
                }
                for (source in classes) {
                    val relativePath = temporary.relativize(source)
                    val relative = (0 until relativePath.nameCount)
                        .joinToString("/") { relativePath.getName(it).toString() }
                    archive.putNextEntry(ZipEntry(relative))
                    archive.write(Files.readAllBytes(source))
                    archive.closeEntry()
                }
            }
            return buildJsonObject {
                put("path", JsonPrimitive(posix(jar)))
                put("sha256", JsonPrimitive(sha256(jar)))
            }
        } finally {
            deleteRecursively(temporary)
        }
    }

    internal fun deleteRecursively(path: Path) {
        if (!Files.exists(path)) return
        Files.walk(path).use { stream ->
            stream.sorted(Comparator.reverseOrder()).forEach { Files.deleteIfExists(it) }
        }
    }
}
