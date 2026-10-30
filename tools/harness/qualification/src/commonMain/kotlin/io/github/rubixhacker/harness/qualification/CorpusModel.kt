package io.github.rubixhacker.harness.qualification

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject

/** One host task of the complete corpus run. */
data class CorpusHost(val host: String, val task: String, val suffix: String)

/** One report group of the complete corpus run. */
data class CorpusGroup(
    val id: String,
    val module: String,
    val host: String,
    val suffix: String,
    val classPrefix: String,
    val pattern: String,
)

/** One discovered test method of the common corpus. */
data class CorpusCase(
    val module: String,
    val sourceSet: String,
    val classname: String,
    val method: String,
    val path: String,
    val sha256: String,
    val line: Long,
    val hosts: List<String>,
)

/**
 * `full_corpus.py`: the source-derived complete corpus and its reviewed dispositions.
 *
 * Every constant here is evidence: the counts, group patterns, command line, and reviewed
 * documents are compared in verification receipts.
 */
object FullCorpus {
    const val ORIGINAL_REVISION = "058bf6d982a0fb89b54050f929f6ea9dae53b714"
    const val REVIEWED_MAP_COMMIT = "16923c101f4c5f99e9f80ff829da63e6d51c1298"
    const val REVIEWED_MAP_SHA256 = "d20877be61398e65037b0ec3d61134d9922248f608c7901ffe589fed8dff5496"
    const val MANIFEST_PATH = "tools/qualification/full-common-corpus.json"
    const val MAP_PATH = "tools/qualification/full-common-original-map.tsv"
    const val PAIR_PATH = "tools/qualification/full-common-reviewed-pairs.tsv"
    const val REVIEWED_PAIRS_SHA256 = "f92af322e9e02fba179737bc9401e5bf50a40c39dd62bf8c847ce1dc0e6b8e60"
    const val NODE_PROBE_PATH = "tools/qualification/node_runtime_probe.cjs"

    val PAIR_FIELDS = listOf(
        "original", "disposition", "classname", "method", "reason",
        "review", "review_sha256",
    )

    val ARTIFACT_SUFFIXES = setOf(".class", ".jar", ".klib", ".kexe", ".wasm", ".js")

    val HOSTS = listOf(
        CorpusHost("jvm", "jvmTest", "[jvm]"),
        CorpusHost("linuxX64", "linuxX64Test", "[linuxX64]"),
        CorpusHost("jsNode", "jsNodeTest", "[js, node]"),
        CorpusHost("wasmJsNode", "wasmJsNodeTest", "[wasmJs, node]"),
        CorpusHost("wasmWasiNode", "wasmWasiNodeTest", "[wasmWasi, node]"),
        CorpusHost("androidHost", "testAndroidHostTest", ""),
    )

    val MODULES = listOf("dyn4k-core", "dyn4k")

    val GROUPS: List<CorpusGroup> = MODULES.flatMap { module ->
        HOSTS.map { host ->
            CorpusGroup(
                id = (if (module == "dyn4k-core") "core-" else "") + host.host,
                module = module,
                host = host.host,
                suffix = host.suffix,
                classPrefix = if (host.host in setOf("jvm", "androidHost")) "" else "${host.task}.",
                pattern = "$module/build/test-results/${host.task}/TEST-*.xml",
            )
        }
    }

    val NODE_GROUPS: Set<String> = GROUPS
        .filter { it.host in setOf("jsNode", "wasmJsNode", "wasmWasiNode") }
        .map { it.id }
        .toSet()

    val GRADLE_COMMAND: List<String> = listOf(
        "./gradlew", "--no-daemon", "--max-workers=1", "--rerun-tasks",
        "--continue", "--console=plain",
    ) + HOSTS.flatMap { host -> MODULES.map { module -> ":$module:${host.task}" } }

    private val TOKEN = Regex("\\bclass\\s+([A-Za-z_]\\w*)|@Test\\b|\\bfun\\s+([A-Za-z_]\\w*)|[{}]")
    private val PACKAGE = Regex("(?m)^\\s*package\\s+([A-Za-z_][\\w.]*)\\s*$")
    private val TEST_ANNOTATION = Regex("@Test\\b")

    val REVIEW_DOCS = linkedMapOf(
        "integrated_collision_model" to "portable-collision-model-coverage.md",
        "integrated_polygon" to "portable-polygon-coverage.md",
        "integrated_body" to "portable-body-coverage.md",
        "integrated_joint_core" to "portable-joints-core.md",
        "integrated_joint_modes" to "portable-joints-modes.md",
        "integrated_epsilon" to "portable-epsilon-coverage.md",
        "pending_shape_pairs_a" to "portable-shape-pairs-a.md",
        "pending_shape_pairs_b" to "portable-shape-pairs-b.md",
        "pending_world_core" to "portable-world-core.md",
        "pending_world_support" to "portable-world-support-contact.md",
        "pending_simulation" to "portable-simulation-coverage.md",
        "pending_broadphase_body" to "portable-detection-body.md",
        "pending_broadphase_item" to "portable-detection-item.md",
        "pending_detection" to "portable-detection-coverage.md",
    )

    val BODY_RELATED_SUPPLEMENTS = linkedMapOf(
        "BodyValueCoverageTest.controlledWrongForceGetterFailsThePortableOracle" to
            "org.dyn4j.dynamics.ForceTest#createSuccess",
        "PhysicsBodyCoverageTest.atRestTimeResetsAndDisabledDetectionKeepsBodyAwake" to
            "org.dyn4j.dynamics.AbstractPhysicsBodyTest#updateAtRestTime",
        "PhysicsBodyCoverageTest.bodyCopyDuplicatesProtectedStateAndPendingCollections" to
            "org.dyn4j.dynamics.BodyTest#copy",
        "PhysicsBodyCoverageTest.fixtureMassCompositionIgnoresZeroDensity" to
            "org.dyn4j.dynamics.AbstractPhysicsBodyTest#setMass",
        "PhysicsBodyCoverageTest.fixtureViewAndMassAreLiveAcrossRemoval" to
            "org.dyn4j.dynamics.AbstractPhysicsBodyTest#addFixtureByConvexBodyFixture",
    )

    val SHA40 = Regex("[0-9a-f]{40}")

    /** `canonical_digest`: SHA-256 of the sorted-key, compact JSON encoding. */
    fun canonicalDigest(value: JsonElement): String =
        io.github.rubixhacker.harness.contract.Sha256.ofCanonical(value)

    /** `paired_rows`: one row per reviewed mapping, in the recorded field order. */
    fun pairedRows(mapping: List<JsonObject>): List<JsonObject> = mapping.map { row ->
        JsonObject(
            PAIR_FIELDS.associateWith { field -> row[field] ?: JsonNull },
        )
    }

    /** `paired_bytes`: the reviewed pairs TSV, tab separated with a newline terminator. */
    fun pairedBytes(mapping: List<JsonObject>): ByteArray {
        val out = StringBuilder()
        out.append(PAIR_FIELDS.joinToString("\t")).append('\n')
        for (row in pairedRows(mapping)) {
            out.append(
                PAIR_FIELDS.joinToString("\t") { field ->
                    val value = row[field]
                    csvField(
                        if (value == null || value is JsonNull) "" else Py.str(value) ?: CanonicalText.of(value),
                    )
                },
            ).append('\n')
        }
        return out.toString().toByteArray(Charsets.UTF_8)
    }

    /** Python's `csv` field quoting for the reviewed TSV files. */
    fun csvField(value: String): String {
        val needsQuote = value.any { it == '\t' || it == '"' || it == '\n' || it == '\r' }
        if (!needsQuote) return value
        return "\"" + value.replace("\"", "\"\"") + "\""
    }

    /** `allowed_generated_path`: build output and caches may stay untracked. */
    fun allowedGeneratedPath(relative: String): Boolean {
        val parts = relative.split('/').filter { it.isNotEmpty() }
        if (parts.isEmpty()) return false
        if (parts[0] in setOf(".gradle", ".kotlin", "build", "kotlin-js-store", ".omo")) return true
        if (parts.size > 1 && parts[0] in setOf("dyn4k-core", "dyn4k") && parts[1] in
            setOf(".gradle", ".kotlin", "build", "kotlin-js-store")
        ) {
            return true
        }
        if ("src" in parts) return false
        if (".pytest_cache" in parts) return true
        return "__pycache__" in parts && parts.last().endsWith(".pyc")
    }

    /** `node_process_argv`: drop the wasm flag and the source-map loader wrapper. */
    fun nodeProcessArgv(repository: String, argv: List<String>): List<String> {
        var value = argv
        if (value.size > 2 && value[1] == "--experimental-wasm-modules") {
            value = listOf(value[0]) + value.drop(2)
        }
        if (nodeLaunchLoader(repository, value) != null) {
            return listOf(value[0]) + value.drop(3)
        }
        return value
    }

    /** `node_launch_loader`: the `--require` loader a Node command was launched through. */
    fun nodeLaunchLoader(repository: String, argv: List<String>): String? {
        val loader = "$repository/build/js/node_modules/source-map-support/register.js"
        return if (argv.size >= 3 && argv[1] == "--require" && argv[2] == loader) loader else null
    }

    /** `node_group_for_argv`: the report group and payload a Node command runs. */
    fun nodeGroupForArgv(repository: String, argv: List<String>?): Pair<String, String>? {
        if (argv == null || argv.size < 2) return null
        val command = nodeProcessArgv(repository, argv)
        val mocha = "$repository/build/js/node_modules/mocha/bin/mocha.js"
        val runner = "$repository/build/js/node_modules/kotlin-web-helpers/dist/kotlin-test-nodejs-runner.js"
        for (module in MODULES) {
            val prefix = if (module == "dyn4k-core") "core-" else ""
            val payload = "$repository/build/js/packages/dyn4k-$module-test/kotlin/dyn4k-$module-test.js"
            val mochaShape = command.size >= 3 &&
                command[1] == mocha && command[2] == payload
            val hasRunner = (3 until command.size - 1).any { index ->
                index + 1 < command.size && command[index] == "--require" && command[index + 1] == runner
            }
            if (mochaShape && hasRunner) return (prefix + "jsNode") to payload
            for ((host, candidate) in listOf(
                "wasmJsNode" to
                    "$repository/build/wasm/packages/dyn4k-$module-test/static/runUnitTests.mjs",
                "wasmWasiNode" to
                    "$repository/build/compileSync/wasmWasi/test/testDevelopmentExecutable/kotlin/static/runUnitTests.mjs",
            )) {
                if (command.drop(1) == listOf(candidate)) return (prefix + host) to candidate
            }
        }
        return null
    }

    /** `node_task`: the Gradle task that runs one Node group. */
    fun nodeTask(groupId: String): String {
        val module = if (groupId.startsWith("core-")) "dyn4k-core" else "dyn4k"
        val host = groupId.removePrefix("core-")
        return ":$module:${host}Test"
    }

    /**
     * `mask_noncode`: blank the comments and string literals of one source file so that a
     * `@Test` inside a comment or a string cannot be read as a case.
     */
    fun maskNoncode(source: String): String {
        val result = source.toCharArray()
        var index = 0
        while (index < source.length) {
            var end = index
            when {
                source.startsWith("//", index) -> {
                    val found = source.indexOf('\n', index)
                    end = if (found < 0) source.length else found
                }
                source.startsWith("/*", index) -> {
                    val found = source.indexOf("*/", index + 2)
                    if (found < 0) throw IllegalArgumentException("unterminated block comment")
                    end = found + 2
                }
                source.startsWith("\"\"\"", index) -> {
                    val found = source.indexOf("\"\"\"", index + 3)
                    if (found < 0) throw IllegalArgumentException("unterminated raw string")
                    end = found + 3
                }
                source[index] == '"' || source[index] == '\'' -> {
                    val quote = source[index]
                    end = index + 1
                    while (end < source.length) {
                        if (source[end] == '\\') {
                            end += 2
                        } else if (source[end] == quote) {
                            end += 1
                            break
                        } else {
                            end += 1
                        }
                    }
                    if (end > source.length || source[end - 1] != quote) {
                        throw IllegalArgumentException("unterminated string")
                    }
                }
            }
            if (end > index) {
                for (offset in index until minOf(end, source.length)) {
                    if (source[offset] != '\n') result[offset] = ' '
                }
                index = end
            } else {
                index += 1
            }
        }
        return String(result)
    }

    /** `scan_sources` over decoded Kotlin sources: one case per `@Test` function. */
    fun scanKotlin(module: String, sourceSet: String, path: String, raw: String, sha256: String): List<CorpusCase> {
        val code = maskNoncode(raw)
        val packageMatch = PACKAGE.find(code)
        val annotations = TEST_ANNOTATION.findAll(code).count()
        val cases = mutableListOf<CorpusCase>()
        var depth = 0
        val classes = mutableListOf<Pair<String, Int>>()
        var pendingClass: String? = null
        var pendingTest = false
        var discovered = 0
        for (token in TOKEN.findAll(code)) {
            val classGroup = token.groupValues[1]
            val funGroup = token.groupValues[2]
            when {
                classGroup.isNotEmpty() -> pendingClass = classGroup
                token.value == "{" -> {
                    depth += 1
                    pendingClass?.let {
                        classes.add(it to depth)
                        pendingClass = null
                    }
                }
                token.value == "}" -> {
                    if (classes.isNotEmpty() && classes.last().second == depth) classes.removeAt(classes.size - 1)
                    depth -= 1
                    if (depth < 0) throw IllegalArgumentException("unbalanced source braces: $path")
                }
                token.value == "@Test" -> {
                    if (pendingTest) throw IllegalArgumentException("consecutive test annotations: $path")
                    pendingTest = true
                }
                funGroup.isNotEmpty() && pendingTest -> {
                    if (packageMatch == null || classes.isEmpty()) {
                        throw IllegalArgumentException("test has no package or class: $path")
                    }
                    val classname = packageMatch.groupValues[1] + "." + classes.joinToString("$") { it.first }
                    val line = code.substring(0, token.range.first).count { it == '\n' } + 1L
                    cases.add(
                        CorpusCase(
                            module = module,
                            sourceSet = sourceSet,
                            classname = classname,
                            method = funGroup,
                            path = path,
                            sha256 = sha256,
                            line = line,
                            hosts = if (sourceSet == "jvmTest") listOf("jvm") else HOSTS.map { it.host },
                        ),
                    )
                    pendingTest = false
                    discovered += 1
                }
            }
        }
        if (pendingTest || discovered != annotations) {
            throw IllegalArgumentException("unresolved test annotation in $path")
        }
        return cases
    }

    /** `source_tree_digest`: the digest of the (path, sha256) pairs of the scanned test tree. */
    fun sourceTreeDigest(sourceFiles: List<JsonObject>): String = canonicalDigest(
        buildJsonArray {
            for (item in sourceFiles) {
                add(
                    buildJsonArray {
                        add(item["path"] ?: JsonNull)
                        add(item["sha256"] ?: JsonNull)
                    },
                )
            }
        },
    )

    /** `expected_cases`: the (classname, method) pairs one group must report. */
    fun expectedCases(manifest: JsonObject, group: CorpusGroup): Set<Pair<String, String>> {
        val cases = manifest["cases"] as? JsonArray ?: JsonArray(emptyList())
        val result = mutableSetOf<Pair<String, String>>()
        for (element in cases) {
            val case = element as? JsonObject ?: continue
            if (Py.str(case["module"]) != group.module) continue
            val hosts = (case["hosts"] as? JsonArray)?.mapNotNull { Py.str(it) } ?: emptyList()
            if (group.host !in hosts) continue
            result.add(
                (group.classPrefix + (Py.str(case["classname"]) ?: "")) to
                    ((Py.str(case["method"]) ?: "") + group.suffix),
            )
        }
        return result
    }

    /** `make_manifest`: decorate scanned methods with their reviewed originals. */
    fun makeManifest(
        cases: List<CorpusCase>,
        mappings: List<JsonObject>,
        production: Boolean = false,
        sourceFiles: List<JsonObject>,
    ): JsonObject {
        val byIdentity = LinkedHashMap<Triple<String, String, String>, CorpusCase>()
        for (case in cases) byIdentity[Triple(case.module, case.classname, case.method)] = case
        val destinations = LinkedHashMap<Triple<String, String, String>, MutableList<String>>()
        val unresolved = mutableListOf<JsonObject>()
        val jvmOnly = mutableListOf<JsonObject>()
        for (mapping in mappings) {
            when (Py.str(mapping["disposition"])) {
                "JVM_ONLY" -> jvmOnly.add(mapping)
                "PORTABLE" -> {
                    val key = Triple(
                        "dyn4k-core",
                        Py.str(mapping["classname"]) ?: "",
                        Py.str(mapping["method"]) ?: "",
                    )
                    val target = byIdentity[key]
                    if (target == null || target.sourceSet != "commonTest") {
                        unresolved.add(
                            buildJsonObject {
                                put("original", mapping["original"] ?: JsonNull)
                                put("reason", JsonPrimitive("mapped common method is absent"))
                            },
                        )
                    } else {
                        destinations.getOrPut(key) { mutableListOf() }
                            .add(Py.str(mapping["original"]) ?: "")
                    }
                }
                else -> unresolved.add(
                    buildJsonObject {
                        put("original", mapping["original"] ?: JsonNull)
                        put("reason", mapping["reason"] ?: JsonPrimitive("unmapped"))
                    },
                )
            }
        }
        val originalIds = mappings.mapNotNull { Py.str(it["original"]) }.toSet()
        val relatedFound = mutableSetOf<String>()
        val decorated = mutableListOf<JsonObject>()
        for (case in cases) {
            val key = Triple(case.module, case.classname, case.method)
            val relatedKey = case.classname.substringAfterLast('.') + "." + case.method
            val related = BODY_RELATED_SUPPLEMENTS[relatedKey]
                ?.takeIf { case.module == "dyn4k-core" && it in originalIds }
            if (related != null) relatedFound.add(relatedKey)
            val originals = destinations[key]?.sortedWith(CanonicalText::compare) ?: emptyList()
            decorated.add(
                buildJsonObject {
                    put("module", JsonPrimitive(case.module))
                    put("source_set", JsonPrimitive(case.sourceSet))
                    put("classname", JsonPrimitive(case.classname))
                    put("method", JsonPrimitive(case.method))
                    put("path", JsonPrimitive(case.path))
                    put("sha256", JsonPrimitive(case.sha256))
                    put("line", JsonPrimitive(case.line))
                    put("hosts", JsonArray(case.hosts.map { JsonPrimitive(it) }))
                    put("originals", JsonArray(originals.map { JsonPrimitive(it) }))
                    put("related_original", related?.let { JsonPrimitive(it) } ?: JsonNull)
                    put(
                        "kind",
                        JsonPrimitive(
                            when {
                                originals.isNotEmpty() -> "mapped-original"
                                case.sourceSet != "commonTest" -> "platform-only"
                                else -> "supplemental"
                            },
                        ),
                    )
                },
            )
        }
        if (production && relatedFound.size != BODY_RELATED_SUPPLEMENTS.size) {
            unresolved.add(
                buildJsonObject { put("reason", JsonPrimitive("reviewed Body supplemental links are absent")) },
            )
        }
        val counts = buildJsonObject {
            put("total_methods", JsonPrimitive(cases.size))
            put("mapped_original_methods", JsonPrimitive(destinations.size))
            put("mapped_original_identities", JsonPrimitive(destinations.values.sumOf { it.size }))
            put(
                "reviewed_source_linked_methods",
                JsonPrimitive(destinations.size + relatedFound.size),
            )
            put("related_supplemental_methods", JsonPrimitive(relatedFound.size))
            put(
                "supplemental_methods",
                JsonPrimitive(decorated.count { Py.str(it["kind"]) == "supplemental" }),
            )
            put(
                "platform_only_methods",
                JsonPrimitive(decorated.count { Py.str(it["kind"]) == "platform-only" }),
            )
            put("jvm_only_original_identities", JsonPrimitive(jvmOnly.size))
            put("unresolved_mappings", JsonPrimitive(unresolved.size))
        }
        return buildJsonObject {
            put("schema", JsonPrimitive(1))
            put("kind", JsonPrimitive("full-common-corpus"))
            put("policy", JsonPrimitive(if (production) "production" else "fixture"))
            put("source_tree_sha256", JsonPrimitive(sourceTreeDigest(sourceFiles)))
            put("source_files", JsonArray(sourceFiles))
            put("cases", JsonArray(decorated))
            put("original_mappings", JsonArray(mappings))
            put("jvm_only", JsonArray(jvmOnly))
            put("unresolved", JsonArray(unresolved))
            put("counts", counts)
        }
    }

    /** `jvm_only_reason`: the reviewed reason an original cannot run in common Kotlin. */
    fun jvmOnlyReason(original: String): String {
        val sourceClass = original.substringBefore('#')
        val method = original.substringAfter('#', "")
        if (original == "org.dyn4j.VersionTest#main") {
            return "Captures System.out through Java PrintStream and ByteArrayOutputStream"
        }
        if (sourceClass.endsWith("CollisionBodyAABBProducerTest") ||
            sourceClass.endsWith("CollisionItemAABBProducerTest")
        ) {
            return "Calls a Java producer with null body, fixture, or result arguments"
        }
        if (sourceClass.endsWith("DistanceJointTest") || sourceClass.endsWith("PulleyJointTest")) {
            return "Passes null to a constructor body argument that is nonnull in common Kotlin"
        }
        if (method.endsWith("NullArray") || method == "nullArray") {
            return "Passes a null Java vararg array unavailable in common Kotlin"
        }
        if (sourceClass.endsWith("Matrix22Test")) {
            return "Passes null to a Java constructor parameter that is nonnull in common Kotlin"
        }
        if ("NullPoint" in method || method == "createNullPoints") {
            return "Passes null to a geometry point parameter that is nonnull in common Kotlin"
        }
        throw IllegalArgumentException("unreviewed JVM-only disposition: $original")
    }

    /** `archive_relative`: one archive member name, rejected when it could escape. */
    fun archiveRelative(name: String?): String {
        if (name.isNullOrEmpty() || "\\" in name || ":" in name || name.startsWith("/")) {
            throw IllegalArgumentException("invalid archive path: $name")
        }
        val parts = name.split('/')
        if (parts.any { it in setOf("", ".", "..") }) {
            throw IllegalArgumentException("invalid archive path: $name")
        }
        return name
    }

    /** `archive_status`: the recorded archive verdict shape. */
    fun archiveStatus(candidateSha: String, problems: List<String>, corpus: JsonElement? = null): JsonObject =
        buildJsonObject {
            put("schema", JsonPrimitive(1))
            put("kind", JsonPrimitive("full-common-archive-verification"))
            put("candidate_sha", JsonPrimitive(candidateSha))
            put("status", JsonPrimitive(if (problems.isEmpty()) "PASSED" else "UNPASSED"))
            put("problems", JsonArray(problems.map { JsonPrimitive(it) }))
            put("corpus", corpus ?: JsonNull)
        }

    /** `node_capture_root`: the unique root a recorded Node command was launched from. */
    fun nodeCaptureRoot(row: JsonObject): String? {
        val relative = archiveRelative(Py.str(row["payload_path"])).split('/').filter { it.isNotEmpty() }
        val argv = row["argv"]
        if (argv !is JsonArray) throw IllegalArgumentException("Node command is absent")
        val roots = mutableListOf<String>()
        for (part in argv) {
            val value = Py.str(part) ?: throw IllegalArgumentException("Node command contains a non-path argument")
            if (value.startsWith("/") && java.nio.file.Path.of(value).normalize().toString() == value) {
                val parts = value.split('/').filter { it.isNotEmpty() }
                if (parts.size >= relative.size && parts.takeLast(relative.size) == relative) {
                    roots.add("/" + parts.dropLast(relative.size).joinToString("/"))
                }
            }
        }
        if (roots.size != 1) {
            throw IllegalArgumentException("Node capture root is not unique in observed command")
        }
        return roots[0]
    }
}
