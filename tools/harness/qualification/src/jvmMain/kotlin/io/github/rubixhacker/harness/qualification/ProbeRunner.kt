package io.github.rubixhacker.harness.qualification

import io.github.rubixhacker.harness.contract.Sha256
import io.github.rubixhacker.harness.contract.StrictJson
import java.io.IOException
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.Path
import java.time.Instant
import java.util.concurrent.TimeUnit
import javax.xml.parsers.DocumentBuilderFactory
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import org.w3c.dom.Element
import org.w3c.dom.Node

/** The probe report plus the captured streams of the command it ran. */
class ProbeReport(val report: JsonObject, val stdout: String, val stderr: String)

/**
 * `qualify.run_probe`.
 *
 * The probe runs one command, then reads the JUnit XML it wrote. Only the selected cases count as
 * executed; extra passing cases are reported but never counted. Every identity, count, and
 * timestamp is checked so that a stale or partial report cannot become lane evidence.
 */
object ProbeRunner {
    fun run(
        command: List<String>,
        reportPaths: List<String>,
        candidateSha: String,
        output: Path,
        manifest: JsonObject? = null,
        workingDirectory: Path = Path.of("").toAbsolutePath(),
    ): ProbeReport {
        val problems = mutableListOf<String>()
        var groups: JsonArray = JsonArray(emptyList())
        if (manifest != null) {
            val declared = manifest["groups"]
            if (declared is JsonArray && declared.isNotEmpty() && Py.str(manifest["kind"]) == "foundation-probe") {
                groups = declared
            }
        }
        if (groups.isEmpty()) {
            problems.add("frozen foundation probe manifest is required")
        }
        val groupObjects = groups.mapNotNull { it as? JsonObject }
        val patterns = groups.map { (it as? JsonObject)?.let { group -> Py.str(group["report_pattern"]) } }
        if (patterns.size != groups.size || patterns.size != patterns.toSet().size) {
            problems.add("probe manifest has duplicate or invalid report groups")
        }
        val requested = reportPaths.sortedWith(CanonicalText::compare)
        val declaredPatterns = patterns.map { it ?: "" }.sortedWith(CanonicalText::compare)
        if (requested != declaredPatterns) {
            problems.add("requested report groups differ from frozen manifest")
        }

        var expected = 0L
        var executed = 0L
        var reported = 0L
        var failures = 0L
        var errors = 0L
        var skipped = 0L
        val expectedByGroup = LinkedHashMap<String, List<ProbeCase>>()
        val groupReports = mutableListOf<JsonObject>()
        for (group in groupObjects) {
            val groupId = Py.str(group["id"])
            if (groupId == null) {
                problems.add("'id'")
                continue
            }
            try {
                val identities = ProbeManifest.expectedCases(manifest!!, group)
                expectedByGroup[groupId] = identities
                expected += identities.size
            } catch (error: IllegalArgumentException) {
                problems.add(error.message ?: "")
            }
        }
        if (expected == 0L) {
            problems.add("probe manifest has no required cases")
        }

        var completed: Process? = null
        var stdout = ""
        var stderr = ""
        var startedAt: Long? = null
        var finishedAt: Long? = null
        if (problems.isEmpty()) {
            startedAt = wallClockNanos()
            val cwd = workingDirectory
            for (pattern in patterns.filterNotNull()) {
                for (path in glob(cwd, pattern)) Files.deleteIfExists(path)
            }
            // The reference does not catch a command that cannot be started.
            val process = ProcessBuilder(command).directory(cwd.toFile()).start()
            completed = process
            stdout = process.inputStream.use { String(it.readBytes(), StandardCharsets.UTF_8) }
            stderr = process.errorStream.use { String(it.readBytes(), StandardCharsets.UTF_8) }
            val status = process.waitFor()
            if (status != 0) problems.add("probe command exited $status")
            for (group in groupObjects) {
                val groupId = Py.str(group["id"]) ?: continue
                val expectedCases = expectedByGroup[groupId] ?: emptyList()
                val pattern = Py.str(group["report_pattern"]) ?: ""
                val paths = glob(cwd, pattern)
                if (expectedCases.isNotEmpty() && paths.isEmpty()) {
                    problems.add("missing report group $groupId")
                }
                if (expectedCases.isEmpty() && paths.isNotEmpty()) {
                    problems.add("unexpected report for empty group $groupId")
                }
                val observedCases = mutableListOf<ProbeCase>()
                val skippedCases = mutableSetOf<ProbeCase>()
                var groupFailures = 0L
                var groupErrors = 0L
                var groupSkipped = 0L
                for (path in paths) {
                    try {
                        val suite = parseSuite(path)
                        val cases = suite.getElementsByTagName("testcase")
                        val testcases = (0 until cases.length).map { cases.item(it) as Element }
                        val suiteCounts = linkedMapOf<String, Long>()
                        for (key in listOf("tests", "failures", "errors", "skipped")) {
                            suiteCounts[key] = integerAttribute(suite, key)
                        }
                        if (suiteCounts.values.any { it < 0 }) {
                            throw IllegalArgumentException("suite counts are missing or negative")
                        }
                        val actualFailures = testcases.count { childNamed(it, "failure") != null }.toLong()
                        val actualErrors = testcases.count { childNamed(it, "error") != null }.toLong()
                        val actualSkips = testcases.count { childNamed(it, "skipped") != null }.toLong()
                        if (suiteCounts.getValue("tests") != testcases.size.toLong() ||
                            suiteCounts.getValue("failures") != actualFailures ||
                            suiteCounts.getValue("errors") != actualErrors ||
                            suiteCounts.getValue("skipped") != actualSkips
                        ) {
                            throw IllegalArgumentException("suite counts differ from case elements")
                        }
                        for (testcase in testcases) {
                            durationAttribute(testcase)
                            val classname = testcase.getAttribute("classname")
                            val name = testcase.getAttribute("name")
                            if (classname.isEmpty() || name.isEmpty()) {
                                throw IllegalArgumentException("case identity is missing")
                            }
                            val identity = ProbeCase(classname, name)
                            observedCases.add(identity)
                            if (childNamed(testcase, "skipped") != null) skippedCases.add(identity)
                        }
                        groupFailures += actualFailures
                        groupErrors += actualErrors
                        groupSkipped += actualSkips
                    } catch (error: Exception) {
                        problems.add("invalid report ${display(path, cwd)}: ${error.message}")
                    }
                }
                val observedCounts = LinkedHashMap<ProbeCase, Int>()
                for (identity in observedCases) {
                    observedCounts[identity] = (observedCounts[identity] ?: 0) + 1
                }
                val duplicateCases = observedCounts.filterValues { it > 1 }
                if (duplicateCases.isNotEmpty()) problems.add("duplicate cases in group $groupId")
                val missingCases = expectedCases.filter { (observedCounts[it] ?: 0) == 0 }
                if (missingCases.isNotEmpty()) problems.add("missing selected cases in group $groupId")
                val selectedExecuted = expectedCases.count { identity ->
                    (observedCounts[identity] ?: 0) == 1 && identity !in skippedCases
                }.toLong()
                val fullReported = observedCases.size.toLong()
                executed += selectedExecuted
                reported += fullReported
                failures += groupFailures
                errors += groupErrors
                skipped += groupSkipped
                groupReports.add(
                    buildJsonObject {
                        put("id", JsonPrimitive(groupId))
                        put("expected", JsonPrimitive(expectedCases.size))
                        put("executed", JsonPrimitive(selectedExecuted))
                        put("reported", JsonPrimitive(fullReported))
                        put("failures", JsonPrimitive(groupFailures))
                        put("errors", JsonPrimitive(groupErrors))
                        put("skipped", JsonPrimitive(groupSkipped))
                    },
                )
            }
            finishedAt = wallClockNanos()
        }
        if (failures != 0L || errors != 0L || skipped != 0L) {
            problems.add("probe has failed, errored, or skipped cases")
        }
        if (executed != expected) {
            problems.add("probe executed count differs from frozen expected count")
        }

        val result = buildJsonObject {
            put("candidate_sha", JsonPrimitive(candidateSha))
            put("command", JsonArray(command.map { JsonPrimitive(it) }))
            put("exit_code", completed?.let { JsonPrimitive(it.exitValue()) } ?: JsonNull)
            put("started_at_ns", startedAt?.let { JsonPrimitive(it) } ?: JsonNull)
            put("finished_at_ns", finishedAt?.let { JsonPrimitive(it) } ?: JsonNull)
            put("expected", JsonPrimitive(expected))
            put("executed", JsonPrimitive(executed))
            put("reported", JsonPrimitive(reported))
            put("groups", JsonArray(groupReports))
            put("failures", JsonPrimitive(failures))
            put("errors", JsonPrimitive(errors))
            put("skipped", JsonPrimitive(skipped))
            put(
                "manifest_sha256",
                manifest?.let { JsonPrimitive(Sha256.ofCanonical(it)) } ?: JsonNull,
            )
            put("status", JsonPrimitive(if (problems.isEmpty()) "PROBE_PASSED" else "PROBE_FAILED"))
            put(
                "reason",
                JsonPrimitive(
                    if (problems.isEmpty()) "frozen selected cases verified in full reports"
                    else problems.joinToString("; "),
                ),
            )
            put("scope", JsonPrimitive("foundation probe only; not a complete lane"))
        }
        Fs.writeText(output, PyJson.render(result) + "\n")
        return ProbeReport(result, stdout, stderr)
    }

    private fun parseSuite(path: Path): Element {
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
        val root = builder.parse(path.toFile()).documentElement
        if (root.tagName != "testsuite") throw IllegalArgumentException("root element is not testsuite")
        val time = root.getAttribute("time").ifEmpty { "0" }
        val suiteTime = time.toDoubleOrNull()
            ?: throw IllegalArgumentException("suite time is invalid")
        if (!suiteTime.isFinite() || suiteTime < 0) throw IllegalArgumentException("suite time is invalid")
        return root
    }

    private fun integerAttribute(element: Element, name: String): Long {
        val raw = element.getAttribute(name).ifEmpty { "-1" }
        return raw.trim().toLongOrNull()
            ?: throw IllegalArgumentException("suite counts are missing or negative")
    }

    private fun durationAttribute(testcase: Element) {
        val raw = testcase.getAttribute("time").ifEmpty { "nan" }
        val duration = raw.toDoubleOrNull() ?: throw IllegalArgumentException("case time is invalid")
        if (!duration.isFinite() || duration < 0) throw IllegalArgumentException("case time is invalid")
    }

    private fun childNamed(element: Element, name: String): Element? {
        var node: Node? = element.firstChild
        while (node != null) {
            if (node.nodeType == Node.ELEMENT_NODE && (node as Element).tagName == name) return node
            node = node.nextSibling
        }
        return null
    }

    private fun display(path: Path, cwd: Path): String =
        if (path.startsWith(cwd)) cwd.relativize(path).toString() else path.toString()

    private fun wallClockNanos(): Long {
        val instant = Instant.now()
        return TimeUnit.SECONDS.toNanos(instant.epochSecond) + instant.nano
    }

    /**
     * `Path.glob` for one pattern, relative to [cwd].
     *
     * A pattern without `**` is resolved segment by segment; a recursive pattern walks the tree.
     */
    fun glob(cwd: Path, pattern: String): List<Path> {
        if (pattern.isEmpty()) return emptyList()
        if ("**" !in pattern.split('/')) {
            var current = listOf(cwd)
            for (segment in pattern.split('/')) {
                if (segment.isEmpty()) return emptyList()
                current = current.flatMap { directory -> childrenMatching(directory, segment) }
                if (current.isEmpty()) return emptyList()
            }
            return current.filter { Files.isRegularFile(it) }.sortedBy { it.toString() }
        }
        val matcher = java.nio.file.FileSystems.getDefault().getPathMatcher("glob:$pattern")
        val matches = mutableListOf<Path>()
        Files.walk(cwd).use { stream ->
            for (path in stream) {
                if (path == cwd) continue
                val relative = cwd.relativize(path)
                if (Files.isRegularFile(path) && matcher.matches(relative)) matches.add(path)
            }
        }
        return matches.sortedBy { it.toString() }
    }

    private fun childrenMatching(directory: Path, segment: String): List<Path> {
        if (!Files.isDirectory(directory)) return emptyList()
        if (segment.none { it == '*' || it == '?' || it == '[' }) {
            val path = directory.resolve(segment)
            return if (Files.exists(path)) listOf(path) else emptyList()
        }
        val result = mutableListOf<Path>()
        try {
            Files.newDirectoryStream(directory, segment).use { stream ->
                for (path in stream) result.add(path)
            }
        } catch (error: IOException) {
            return emptyList()
        }
        return result
    }
}

/** Decoded JSON value of a probe result file, mirroring Python's `json.loads`. */
internal fun loadStrictJson(path: Path): JsonElement = StrictJson.load(Fs.readText(path))
