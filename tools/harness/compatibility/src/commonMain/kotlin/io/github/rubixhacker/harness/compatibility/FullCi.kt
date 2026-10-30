package io.github.rubixhacker.harness.compatibility

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/**
 * The pure validators and archive checks of `tools/compatibility/full_ci.py`.
 *
 * Ported: `load_json_unique`, `snapshot_archive`, `verify_archive_files`, `relocate_exception_runs`,
 * `declared_archive_root`, `archived_json`, `validate_corpus`, `parameter_groups`, `validate_xml`,
 * `normalized_cases`, `validate_source_inputs`, `validate_audit`, `seal_lanes`,
 * `validate_corpus_argfile`, `validate_corpus_process`, `junit_report`, and `checked_archive`.
 *
 * Not ported: `validate_production_sources`, `validate_test_source_commit` (git object replay),
 * `validate_projection` (relies on generated sources plus fixture files), `verify_portable_*`,
 * `verify_archive`, `corpus_matrix`, `main`, and `verify_main` (the evidence-tree replays).
 */
object FullCi {
    const val VERSION = "0.1.0-alpha.1"
    const val BASELINE_SHA = "204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e"
    const val BASELINE_COMMIT = "058bf6d982a0fb89b54050f929f6ea9dae53b714"
    const val SOURCES_SHA = "83b47be47bdce27681139dab84937e0f586b70ab800dc494fbebed4b58893223"
    const val STDLIB_SHA = "2226de463d309d4a5500a481320b3dea515a6981dcae1def531fbc158884e25f"
    const val ANNOTATIONS_SHA = "ace2a10dc8e2d5fd34925ecac03e4988b2c0f851650c94b8cef49ba1bd111478"
    const val ADVERSE_AUDIT_SHA = "aaed70cf906eb2e1944e56b80713fe6398a5339d55f4977128b54dd70cba607a"
    const val PROJECTION = "tools/compatibility/fixtures/java_source_projection"

    val FIXTURE_SHA = setOf(
        "b668a59b6b50e6d5be1ca4828d2eaa179c6f9b3623a839be3e8c2c063d9ce6a4",
        "bb3f75b5f938b5e6da6e2444f5626606daa2223d29ba5c9ba2405660e50097ed",
        "b37d307b808a55961bad6d6cfd5606ec7d27b2ba33567e8d44621d0942530ff0",
    )

    /** The parameterised owners and the parameter type names each lane must run. */
    val PARAMETER_SUITES: Map<String, Pair<Int, List<String>>> = linkedMapOf(
        "org.dyn4j.collision.broadphase.CollisionBodyBroadphaseTest" to
            (25 to listOf("Sap", "Sap", "DynamicAABBTree", "DynamicAABBTree", "BruteForceBroadphase")),
        "org.dyn4j.collision.broadphase.CollisionItemBroadphaseTest" to
            (29 to List(5) { "CollisionItemBroadphaseDetectorAdapter" }),
    )

    val PARAMETER_PATTERN = Regex("""([^\[]+)\[([^@\]]+)@([0-9a-fA-F]+)\]""")

    val LANES: Set<String> = setOf("baseline", "candidate", "android").flatMap { provider ->
        listOf(8, 21).flatMap { compiler ->
            listOf(8, 21).map { runtime -> "$provider-javac$compiler-java$runtime" }
        }
    }.toSet()

    fun loadJsonUnique(text: String): JsonElement = UniqueJson.parse(text)

    /**
     * Hashes every file below [output] except `lane-manifest.json`, rejecting a symlinked root,
     * symlinked directories, and symlinks or non-files among the entries.
     */
    fun snapshotArchive(files: CorpusFiles, output: String): Map<String, String> {
        if (files.isSymlink(output) || !files.isDirectory(output)) {
            throw IllegalArgumentException("archive root is missing or a symlink")
        }
        val entries = files.entriesBelow(output)
        for (relative in entries) {
            val path = joinPath(output, relative)
            if (files.isDirectory(path) && files.isSymlink(path)) {
                throw IllegalArgumentException("archive symlink directory: ${fileName(relative)}")
            }
        }
        val result = linkedMapOf<String, String>()
        for (relative in entries) {
            val path = joinPath(output, relative)
            if (!files.isFile(path)) continue
            if (files.isSymlink(path)) {
                throw IllegalArgumentException("archive symlink or non-file: $path")
            }
            if (relative != "lane-manifest.json") result[relative] = files.digest(path)
        }
        return sortedByCodePoint(result.keys).associateWith { result.getValue(it) }
    }

    /** Checks a recorded archive inventory against the files on disk. */
    fun verifyArchiveFiles(
        files: CorpusFiles,
        output: String,
        recorded: Map<String, String>,
    ): Map<String, String> {
        if (recorded.isEmpty()) {
            throw IllegalArgumentException("archive file inventory is empty")
        }
        val normalised = mutableSetOf<String>()
        for ((name, sha) in recorded) {
            val parts = name.split("/")
            if (isAbsolutePath(name) || "\\" in name || name.isEmpty() ||
                parts.any { it == "." || it == ".." } ||
                normaliseRelativePath(name) != name ||
                !SHA256_HEX.matches(sha)
            ) {
                throw IllegalArgumentException("archive path or hash is unsafe: $name")
            }
            if (!normalised.add(normaliseRelativePath(name))) {
                throw IllegalArgumentException("duplicate archive path: $name")
            }
        }
        val actual = snapshotArchive(files, output)
        if (actual.keys != recorded.keys) {
            throw IllegalArgumentException("archive file set differs")
        }
        for ((name, sha) in recorded) {
            if (actual[name] != sha) {
                throw IllegalArgumentException("archive file hash differs: $name")
            }
        }
        return actual
    }

    /**
     * Rewrites exception process commands from the frozen archive root to the copied root, refusing
     * any command that does not name the declared archive.
     */
    fun relocateExceptionRuns(
        rows: List<JsonObject>,
        original: String,
        output: String,
        jdks: Map<String, String>,
        area: String = "fixture",
        pathSeparator: String = ":",
    ): List<JsonObject> {
        if (area != "fixture" && area != "uid-adverse") {
            throw IllegalArgumentException("exception process area is unsafe")
        }
        val fixture = joinPath(joinPath(original, "exception-serialization"), area)
        val copiedFixture = joinPath(joinPath(output, "exception-serialization"), area)
        val mapped = mutableListOf<JsonObject>()
        for (originalRow in rows) {
            val row = originalRow
            val operation = row.textOrNull("operation")
            val runtime = row.textOrNull("runtime")
            val provider = row.textOrNull("provider")
            val command = row["command"].arrayOrNull()
            if (operation !in setOf("ids", "write", "read") ||
                runtime == null || runtime !in jdks ||
                provider !in setOf("baseline", "jvm", "android") ||
                command == null
            ) {
                throw IllegalArgumentException("exception process command is malformed")
            }
            val classpath = listOf(
                joinPath(joinPath(fixture, "classes"), requireNotNull(provider)),
                joinPath(fixture, "$provider.jar"),
                joinPath(joinPath(original, "deps"), "kotlin-stdlib-2.4.20.jar"),
            ).joinToString(pathSeparator)
            val expected = mutableListOf(
                joinPath(joinPath(jdks.getValue(requireNotNull(runtime)), "bin"), "java"),
                "-cp",
                classpath,
                "ExceptionSerializationProbe",
                requireNotNull(operation),
            )
            var case: String? = null
            var writerRuntime: String? = null
            var writerProvider: String? = null
            if (operation == "write" || operation == "read") {
                writerRuntime = row.textOrNull("writer_runtime")
                writerProvider = row.textOrNull("writer_provider")
                case = row.textOrNull("case")
                if (writerRuntime == null || writerRuntime !in jdks ||
                    writerProvider !in setOf("baseline", "jvm", "android") ||
                    case == null
                ) {
                    throw IllegalArgumentException("exception process command is malformed")
                }
                expected.add(joinPath(fixture, "$writerRuntime-$writerProvider-$case.ser"))
                expected.add(case)
            }
            if (command.map { it.textOrNull() } != expected) {
                throw IllegalArgumentException("exception process command differs from declared archive root")
            }
            val rewritten = command.toMutableList()
            rewritten[2] = JsonPrimitive(
                listOf(
                    joinPath(joinPath(copiedFixture, "classes"), requireNotNull(provider)),
                    joinPath(copiedFixture, "$provider.jar"),
                    joinPath(joinPath(output, "deps"), "kotlin-stdlib-2.4.20.jar"),
                ).joinToString(pathSeparator),
            )
            if (case != null) {
                rewritten[rewritten.size - 2] = JsonPrimitive(
                    joinPath(copiedFixture, "$writerRuntime-$writerProvider-$case.ser"),
                )
            }
            mapped.add(JsonObject(row.toMutableMap().apply { put("command", JsonArray(rewritten)) }))
        }
        return mapped
    }

    /** Returns the absolute archive root, rejecting a relative, unnormalised, or parent path. */
    fun declaredArchiveRoot(value: String?): String {
        if (value == null) {
            throw IllegalArgumentException("declared archive root is missing")
        }
        if (!isAbsolutePath(value) || normaliseAbsolutePath(value) != value ||
            ".." in pathParts(value)
        ) {
            throw IllegalArgumentException("declared archive root is unsafe")
        }
        return value
    }

    /** Reads one archived JSON document, checking its digest and rejecting duplicates. */
    fun archivedJson(
        files: CorpusFiles,
        output: String,
        relative: String,
        expectedSha256: String? = null,
    ): JsonElement {
        val path = joinPath(output, relative)
        if (!files.isFile(path) || files.isSymlink(path) ||
            (expectedSha256 != null && files.digest(path) != expectedSha256)
        ) {
            throw IllegalArgumentException("archive JSON is missing or changed: $relative")
        }
        return loadJsonUnique(files.readText(path))
    }

    /** Requires the three JUnit markers to appear once each and the process to have passed. */
    fun validateCorpus(report: JsonObject) {
        for ((key, marker, expected) in listOf(
            Triple("actual_executed_cases", "ACTUAL_TESTS", 2385L),
            Triple("failures", "FAILURES", 0L),
            Triple("ignored", "IGNORED", 0L),
        )) {
            if (report[key].integerOrNull() != expected) {
                throw IllegalArgumentException("$key must equal $expected")
            }
            val output = report.textOrNull("output").orEmpty()
            if (pySplitLines(output).count { it == "$marker=$expected" } != 1) {
                throw IllegalArgumentException("missing or conflicting $marker marker")
            }
        }
        if (report["process_exit_code"].integerOrNull() != 0L) {
            throw IllegalArgumentException("JUnit process failed")
        }
    }

    /**
     * Groups the parameterised cases of the two broadphase suites, returning the parameter index
     * map per owner after checking the method, type, and parameter multiplicities.
     */
    fun parameterGroups(
        identities: List<Pair<String, String>>,
        expected: Int,
    ): Map<String, Map<Pair<String, String>, Int>> {
        val groups = linkedMapOf<String, Map<Pair<String, String>, Int>>()
        for ((className, suite) in PARAMETER_SUITES) {
            val (methodCount, typeNames) = suite
            val rows = identities.filter { it.first == className }.map { it.second }
            if (rows.isEmpty() && expected != 2385) continue
            val seen = linkedMapOf<Pair<String, String>, MutableList<String>>()
            for (name in rows) {
                val match = PARAMETER_PATTERN.matchEntire(name)
                    ?: throw IllegalArgumentException("$className parameter group name is malformed")
                val method = match.groupValues[1]
                val parameterType = match.groupValues[2]
                val address = match.groupValues[3]
                seen.getOrPut(parameterType to address) { mutableListOf() }.add(method)
            }
            if (seen.size != 5 || rows.size != methodCount * 5) {
                throw IllegalArgumentException("$className parameter group count differs")
            }
            val actualTypes = seen.keys.map { it.first }
            if (actualTypes != typeNames.map { "org.dyn4j.collision.broadphase.$it" }) {
                throw IllegalArgumentException("$className parameter group types differ")
            }
            val expectedMethods = seen.values.first().toSet()
            if (expectedMethods.size != methodCount ||
                seen.values.any { it.size != methodCount || it.toSet() != expectedMethods }
            ) {
                throw IllegalArgumentException("$className parameter group methods differ")
            }
            groups[className] = seen.keys.withIndex().associate { it.value to it.index }
        }
        return groups
    }

    /** Reads one JUnit XML report, requiring the exact passing case count and identities. */
    fun validateXml(
        files: CorpusFiles,
        path: String,
        expected: Int = 2385,
    ): List<Pair<String, String>> {
        val suite = MiniXml.parse(files.readText(path))
        if (suite.tag != "testsuite" ||
            listOf("tests" to expected, "failures" to 0, "errors" to 0, "skipped" to 0)
                .any { (key, value) -> suite.attributes[key] != value.toString() }
        ) {
            throw IllegalArgumentException("JUnit XML count or status differs")
        }
        val cases = suite.children.filter { it.tag == "testcase" }
        if (cases.size != expected ||
            cases.any {
                it.attributes["classname"].isNullOrEmpty() ||
                    it.attributes["name"].isNullOrEmpty() ||
                    it.children.isNotEmpty()
            }
        ) {
            throw IllegalArgumentException("JUnit XML lacks complete passing case identities")
        }
        val identities = cases.map {
            requireNotNull(it.attributes["classname"]).trim() to requireNotNull(it.attributes["name"]).trim()
        }
        if (identities.toSet().size != expected) {
            throw IllegalArgumentException("JUnit XML has duplicate or missing case identities")
        }
        parameterGroups(identities, expected)
        return identities
    }

    /** Collapses the 2385-case corpus onto one identity per parameter when that is the input size. */
    fun normalizedCases(identities: List<Pair<String, String>>): Map<Pair<String, String>, Int> {
        val groups = if (identities.size == 2385) parameterGroups(identities, identities.size) else emptyMap()
        val result = linkedMapOf<Pair<String, String>, Int>()
        for ((className, name) in identities) {
            var normalized = name
            val group = groups[className]
            if (group != null) {
                val match = PARAMETER_PATTERN.matchEntire(name)
                    ?: throw IllegalArgumentException("$className parameter group name is malformed")
                val method = match.groupValues[1]
                val parameterType = match.groupValues[2]
                val address = match.groupValues[3]
                normalized = "$method[$parameterType#${group.getValue(parameterType to address)}]"
            }
            val key = className to normalized
            result[key] = (result[key] ?: 0) + 1
        }
        return result
    }

    /** Checks every pinned test input under [source] against its recorded digest. */
    fun validateSourceInputs(
        files: CorpusFiles,
        source: String,
        hashes: Map<String, String>,
        expectedCount: Int = 218,
    ) {
        if (hashes.size != expectedCount) {
            throw IllegalArgumentException("pinned test input inventory is incomplete")
        }
        val root = normaliseAbsolutePath(source)
        for ((relative, expected) in hashes) {
            val path = normaliseAbsolutePath(joinPath(source, relative))
            if (!path.startsWith("$root/") || !files.isFile(path) || files.digest(path) != expected) {
                throw IllegalArgumentException("pinned test source or resource changed: $relative")
            }
        }
    }

    /** Requires the strict comparison report to cover every pinned API type and fixture. */
    fun validateAudit(report: JsonObject, candidateHash: String) {
        val apiTypes = report["compared_api_types"].arrayOrNull()
        if (apiTypes == null || apiTypes.size != 216 ||
            apiTypes.any { it.textOrNull().isNullOrEmpty() } ||
            apiTypes.mapNotNull { it.textOrNull() }.toSet().size != 216 ||
            report["compared_baseline_declarations"].integerOrNull() != 3078L
        ) {
            throw IllegalArgumentException("required declaration inventory is incomplete")
        }
        if (report.textOrNull("baseline_sha256") != BASELINE_SHA ||
            report.textOrNull("candidate_sha256") != candidateHash
        ) {
            throw IllegalArgumentException("comparison archive hash differs")
        }
        for (key in listOf(
            "missing_types", "signature_mismatches", "added_member_risks",
            "inventory_errors", "fixture_failures", "fixture_errors",
        )) {
            val value = report[key].arrayOrNull()
            if (value == null || value.isNotEmpty()) {
                throw IllegalArgumentException("strict comparison has $key")
            }
        }
        val rows = report["fixture_results"].arrayOrNull()
            ?: throw IllegalArgumentException("permanent Java 8 fixtures were omitted or changed")
        val observed = rows.mapNotNull { it.objectOrNull()?.textOrNull("source_sha256") }.toSet()
        if (observed != FIXTURE_SHA || rows.size != FIXTURE_SHA.size) {
            throw IllegalArgumentException("permanent Java 8 fixtures were omitted or changed")
        }
        for (element in rows) {
            val row = element.objectOrNull()
                ?: throw IllegalArgumentException("permanent Java 8 fixtures were omitted or changed")
            if (row["baseline_exit_code"].integerOrNull() != 0L ||
                row["candidate_exit_code"].integerOrNull() != 0L
            ) {
                throw IllegalArgumentException("permanent Java 8 fixture compilation failed")
            }
        }
    }

    /** Seals the 24 corpus lane files named by passing evidence. */
    fun sealLanes(
        files: CorpusFiles,
        output: String,
        evidence: JsonObject,
        candidateSha: String,
    ): Map<String, String> {
        if (evidence.textOrNull("status") != "PASSED" ||
            evidence.textOrNull("candidate_sha") != candidateSha
        ) {
            throw IllegalArgumentException("full compatibility result is not passing at candidate SHA")
        }
        val corpus = evidence["corpus"].objectOrNull()
        if (corpus == null || corpus.keys.filter { it in LANES }.toSet() != LANES) {
            throw IllegalArgumentException("corpus lane inventory is incomplete")
        }
        val expectedFiles = LANES.flatMap { lane ->
            listOf("corpus-$lane.xml", "corpus-$lane.json")
        }.toSet()
        val actualFiles = listOf("xml", "json").flatMap { suffix ->
            files.filesBelow(output).filter { "/" !in it && it.startsWith("corpus-") && it.endsWith(".$suffix") }
        }.toSet()
        if (actualFiles != expectedFiles) {
            throw IllegalArgumentException("corpus XML/JSON file set differs")
        }
        val hashes = linkedMapOf<String, String>()
        for (lane in sortedByCodePoint(LANES)) {
            val row = corpus[lane].objectOrNull()
                ?: throw IllegalArgumentException("$lane did not pass all 2385 cases")
            if (row.textOrNull("status") != "PASSED" || row.integerOrNull("cases") != 2385L) {
                throw IllegalArgumentException("$lane did not pass all 2385 cases")
            }
            for ((suffix, field) in listOf("xml" to "xml_sha256", "json" to "report_sha256")) {
                val name = "corpus-$lane.$suffix"
                val path = joinPath(output, name)
                val recorded = row.textOrNull(if (suffix == "xml") "xml" else "report")
                if (recorded != name || !files.isFile(path) || files.isSymlink(path)) {
                    throw IllegalArgumentException("$name is missing from passing evidence")
                }
                val actual = files.digest(path)
                if (row.textOrNull(field) != actual) {
                    throw IllegalArgumentException("$name hash differs from passing evidence")
                }
                hashes[name] = actual
            }
        }
        return hashes
    }

    /** Checks the pinned test source arguments file and the runner class inventory it implies. */
    fun validateCorpusArgfile(
        files: CorpusFiles,
        output: String,
        original: String,
        hashes: Map<String, String>,
        expectedCount: Int = 199,
        expectedClasses: Int = 190,
    ): List<String> {
        val source = joinPath(output, "baseline-cache/dyn4j-source")
        val tests = sortedByCodePoint(
            hashes.keys.filter { it.startsWith("src/test/java/") && it.endsWith(".java") },
        )
        if (tests.size != expectedCount) {
            throw IllegalArgumentException("pinned test source inventory differs")
        }
        val actual = mutableSetOf<String>()
        for (directory in listOf("src/test/java", "src/test/resources")) {
            val root = joinPath(source, directory)
            for (relative in files.entriesBelow(root)) {
                val path = joinPath(root, relative)
                if (files.isFile(path) || files.isSymlink(path)) {
                    actual.add(normaliseRelativePath("$directory/$relative"))
                }
            }
        }
        if (actual != hashes.keys) {
            throw IllegalArgumentException("pinned test source file set differs")
        }
        val expected = buildString {
            for (name in tests) {
                append('"')
                append(joinPath(joinPath(original, "baseline-cache/dyn4j-source"), name))
                append("\"\n")
            }
        }
        if (files.readText(joinPath(output, "test-sources.args")) != expected) {
            throw IllegalArgumentException("pinned test source argfile differs")
        }
        val classes = sortedByCodePoint(
            tests.mapNotNull { name ->
                val text = files.readText(joinPath(source, name))
                if ("@Test" in text || "@RunWith" in text) {
                    name.removePrefix("src/test/java/").removeSuffix(".java").replace('/', '.')
                } else {
                    null
                }
            }.toSet(),
        )
        if (classes.size != expectedClasses) {
            throw IllegalArgumentException("pinned test runner class inventory differs")
        }
        return classes
    }

    /**
     * Checks one archived process record: its hash, its command, its working directory, its exit
     * code, and that the log holds exactly its stdout followed by its stderr.
     */
    fun validateCorpusProcess(
        files: CorpusFiles,
        rawDirectory: String,
        rawName: String,
        logPath: String,
        row: JsonObject,
        command: List<String>,
        expectedCwd: String? = null,
    ): JsonObject {
        if (!SHA256_HEX.matches(row.textOrNull("process_sha256").orEmpty())) {
            throw IllegalArgumentException("corpus raw process hash is missing")
        }
        val raw = archivedJson(files, rawDirectory, rawName, row.textOrNull("process_sha256"))
            .objectOrNull() ?: throw IllegalArgumentException("corpus process command or result differs")
        val keys = raw.keys
        if (keys != setOf("command", "cwd", "exit", "stdout", "stderr") ||
            raw["command"].arrayOrNull()?.map { it.textOrNull() } != command ||
            (expectedCwd != null && raw.textOrNull("cwd") != expectedCwd) ||
            raw["exit"].integerOrNull() != 0L ||
            raw["stdout"].textOrNull() == null ||
            raw["stderr"].textOrNull() == null
        ) {
            throw IllegalArgumentException("corpus process command or result differs")
        }
        if (files.readText(logPath) !=
            raw.textOrNull("stdout").orEmpty() + raw.textOrNull("stderr").orEmpty()
        ) {
            throw IllegalArgumentException("corpus raw process log differs")
        }
        return raw
    }

    /** Reads the JUnit markers a report process printed, as `full_ci.junit_report` does. */
    fun junitReport(output: String, exitCode: Int): JsonObject {
        fun field(label: String): JsonPrimitive? {
            val matches = pySplitLines(output)
                .filter { it.startsWith("$label=") }
                .map { it.substringAfter("=") }
            return if (matches.size == 1 && matches[0].toIntOrNull() != null) {
                JsonPrimitive(matches[0].toInt())
            } else {
                null
            }
        }
        val values = linkedMapOf<String, JsonElement>(
            "actual_executed_cases" to (field("ACTUAL_TESTS") ?: JsonNull),
            "failures" to (field("FAILURES") ?: JsonNull),
            "ignored" to (field("IGNORED") ?: JsonNull),
            "process_exit_code" to JsonPrimitive(exitCode),
            "output" to JsonPrimitive(output),
        )
        return JsonObject(values)
    }
}
