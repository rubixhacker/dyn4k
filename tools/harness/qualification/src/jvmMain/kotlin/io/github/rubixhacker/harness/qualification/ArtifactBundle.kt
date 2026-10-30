package io.github.rubixhacker.harness.qualification

import io.github.rubixhacker.harness.contract.StrictJson
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.StandardCopyOption
import java.util.concurrent.TimeUnit
import javax.xml.parsers.DocumentBuilderFactory
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import org.w3c.dom.Element
import org.w3c.dom.Node

/**
 * `artifact.py`, first slice: bundle inventory paths, evidence copies, probe checks, and report
 * collection.
 *
 * `stage_hosted`, `stage_ubuntu`, `verify_bundle`, `verify_full_hosted`, and `main` are not yet
 * ported: `verify_bundle` calls `hosted.py` and the browser/native consumer verifiers, and
 * `verify_full_hosted` calls `full_hosted.py`, all of which are still Python.
 */
object ArtifactBundle {
    /** `artifact.portable_path`: one bundle inventory path, rejected when it could escape. */
    fun portablePath(value: String?): String {
        if (value.isNullOrEmpty()) throw IllegalArgumentException("bundle inventory path is missing")
        val path = value.replace('\\', '/')
        val parts = path.split('/')
        if (parts.any { it in setOf("", ".", "..") } || ":" in parts.first()) {
            throw IllegalArgumentException("bundle inventory path is unsafe: $value")
        }
        return parts.joinToString("/")
    }

    /** `artifact.copy_json`: one evidence JSON object, copied into the bundle's `json/` tree. */
    fun copyJson(path: Path, destination: Path): JsonObject {
        if (!Files.isRegularFile(path) || Files.isSymbolicLink(path)) {
            throw IllegalArgumentException("missing evidence JSON: ${path.fileName}")
        }
        val data = StrictJson.load(Fs.readText(path))
        if (data !is JsonObject) {
            throw IllegalArgumentException("evidence JSON is not an object: ${path.fileName}")
        }
        val target = destination.resolve("json").resolve(path.fileName.toString())
        target.parent?.let { Files.createDirectories(it) }
        Files.copy(path, target, StandardCopyOption.COPY_ATTRIBUTES, StandardCopyOption.REPLACE_EXISTING)
        return data
    }

    /** `artifact.check_probe`: the frozen probe accounting of one selected group set. */
    fun checkProbe(
        probe: JsonObject,
        manifest: JsonObject,
        groups: Map<String, JsonObject>,
        ids: List<String>,
        candidateSha: String,
    ): Pair<Long, Long> {
        val selected = buildJsonObject {
            for ((key, value) in manifest) {
                if (key != "groups") put(key, value)
            }
            put("groups", JsonArray(ids.map { groups.getValue(it) }))
        }
        val expected = ids.sumOf { group -> ProbeManifest.expectedCases(manifest, groups.getValue(group)).size }
        if (Py.str(probe["candidate_sha"]) != candidateSha ||
            Py.str(probe["status"]) != "PROBE_PASSED" ||
            Py.str(probe["manifest_sha256"]) != FullCorpus.canonicalDigest(selected) ||
            !Py.equalsInt(probe["expected"], expected.toLong()) ||
            !Py.equalsInt(probe["executed"], expected.toLong()) ||
            !Py.equalsInt(probe["failures"], 0) ||
            !Py.equalsInt(probe["errors"], 0) ||
            !Py.equalsInt(probe["skipped"], 0) ||
            !Py.isInt(probe["reported"]) ||
            Py.int(probe["reported"]) < expected ||
            !Py.equalsInt(probe["exit_code"], 0)
        ) {
            throw IllegalArgumentException(
                "probe for ${ids.joinToString(", ")} differs from frozen executed suite",
            )
        }
        val groupObjects = ids.map { groups.getValue(it) }
        val accounting = ProbeManifest.validateAccounting(
            probe, buildJsonObject {
                put("groups", JsonArray(groupObjects))
            }, ids,
        )
        if (accounting.isEmpty()) throw IllegalArgumentException("probe accounting is absent")
        val started = if (Py.isInt(probe["started_at_ns"])) Py.int(probe["started_at_ns"]) else null
        val finished = if (Py.isInt(probe["finished_at_ns"])) Py.int(probe["finished_at_ns"]) else null
        if (started == null || finished == null || started <= 0 || finished < started) {
            throw IllegalArgumentException("probe for ${ids.joinToString(", ")} lacks execution time")
        }
        return started to finished
    }

    /**
     * `artifact.collect_group`: copy one report group into the bundle and prove it reports every
     * selected case exactly once.
     */
    fun collectGroup(
        repository: Path,
        destination: Path,
        manifest: JsonObject,
        group: JsonObject,
        started: Long?,
        finished: Long?,
        files: MutableList<JsonObject>,
        recordedTimes: Map<String, Long>? = null,
    ): JsonObject {
        val groupId = Py.str(group["id"])!!
        val expected = ProbeManifest.expectedCases(manifest, group)
        val pattern = Py.str(group["report_pattern"])!!
        val paths = ProbeRunner.glob(repository, pattern)
        if (paths.isEmpty()) throw IllegalArgumentException("missing report group $groupId")
        val observed = mutableListOf<Pair<String, String>>()
        for (path in paths) {
            if (!Files.isRegularFile(path) || Files.isSymbolicLink(path)) {
                throw IllegalArgumentException("invalid report $path: missing or symbolic")
            }
            val relative = repository.relativize(path).toString().replace('\\', '/')
            val fileKey = portablePath("xml/$relative")
            val mtimeNs: Long
            if (recordedTimes == null) {
                mtimeNs = Files.getLastModifiedTime(path).to(TimeUnit.NANOSECONDS)
            } else {
                mtimeNs = recordedTimes[fileKey]
                    ?: throw IllegalArgumentException("raw report has no bound file time: $fileKey")
            }
            if (started == null || finished == null || mtimeNs < started || mtimeNs > finished) {
                throw IllegalArgumentException("stale report $path: outside bound execution")
            }
            val bundled = destination.resolve("xml").resolve(relative)
            bundled.parent?.let { Files.createDirectories(it) }
            Files.copy(
                path, bundled, StandardCopyOption.COPY_ATTRIBUTES, StandardCopyOption.REPLACE_EXISTING,
            )
            val suite = suiteOf(bundled)
            if (suite.tagName != "testsuite") {
                throw IllegalArgumentException("invalid report $path: root is not testsuite")
            }
            val cases = elementsNamed(suite, "testcase")
            val counts = linkedMapOf(
                "tests" to (suite.getAttribute("tests").toLongOrNull() ?: -1L),
                "failures" to (suite.getAttribute("failures").toLongOrNull() ?: -1L),
                "errors" to (suite.getAttribute("errors").toLongOrNull() ?: -1L),
                "skipped" to (suite.getAttribute("skipped").toLongOrNull() ?: -1L),
            )
            val actual = linkedMapOf(
                "tests" to cases.size.toLong(),
                "failures" to cases.count { childNamed(it, "failure") != null }.toLong(),
                "errors" to cases.count { childNamed(it, "error") != null }.toLong(),
                "skipped" to cases.count { childNamed(it, "skipped") != null }.toLong(),
            )
            if (counts != actual || counts.values.any { it < 0 }) {
                throw IllegalArgumentException(
                    "invalid report $path: suite counts differ from case elements",
                )
            }
            if (counts.getValue("failures") != 0L || counts.getValue("errors") != 0L ||
                counts.getValue("skipped") != 0L
            ) {
                throw IllegalArgumentException("invalid report $path: failed or skipped cases")
            }
            val suiteTime = suite.getAttribute("time").ifEmpty { "nan" }.toDoubleOrNull()
            if (suiteTime == null || suiteTime.isNaN() || suiteTime < 0 ||
                suiteTime == Double.POSITIVE_INFINITY
            ) {
                throw IllegalArgumentException("invalid report $path: suite time is invalid")
            }
            for (case in cases) {
                val duration = case.getAttribute("time").ifEmpty { "nan" }.toDoubleOrNull()
                val classname = case.getAttribute("classname")
                val name = case.getAttribute("name")
                if (duration == null || duration.isNaN() || duration < 0 ||
                    duration == Double.POSITIVE_INFINITY || classname.isEmpty() || name.isEmpty()
                ) {
                    throw IllegalArgumentException(
                        "invalid report $path: case time or identity is invalid",
                    )
                }
                observed.add(classname to name)
            }
            files.add(
                buildJsonObject {
                    put(
                        "path",
                        JsonPrimitive(portablePath(destination.relativize(bundled).toString().replace('\\', '/'))),
                    )
                    put("sha256", JsonPrimitive(CorpusFiles.digest(bundled)))
                    put("mtime_ns", JsonPrimitive(mtimeNs))
                },
            )
        }
        if (observed.size != observed.toSet().size) {
            throw IllegalArgumentException("duplicate cases in $groupId")
        }
        val observedSet = observed.map { ProbeCase(it.first, it.second) }.toSet()
        if (expected.any { it !in observedSet }) {
            throw IllegalArgumentException("missing selected cases in $groupId")
        }
        return buildJsonObject {
            put("selected", JsonPrimitive(expected.size))
            put("reported", JsonPrimitive(observed.size))
        }
    }

    private fun suiteOf(path: Path): Element {
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
        return builder.parse(path.toFile()).documentElement
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
}
