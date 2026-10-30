package io.github.rubixhacker.harness.qualification

import io.github.rubixhacker.harness.contract.Qualification
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/** One hosted native target: the operating system, architecture, and simulator family. */
data class NativeTarget(val system: String, val machine: String, val simulator: String?)

/** The verdict of one runtime or hosted-summary check: the status and its retained reason. */
data class HostedVerdict(val status: String, val reason: String)

/**
 * `tools/qualification/hosted.py`: the target registry, the runtime identity rules, the hosted
 * summary rules, the probe-group selection, and the Gradle wrapper path.
 *
 * Every message here is retained evidence: a probe JSON records it, and a lane summary repeats
 * it. Reword a message only together with the recorded expectations.
 */
object Hosted {
    val NATIVE_TARGETS: Map<String, NativeTarget> = linkedMapOf(
        "macosArm64" to NativeTarget("Darwin", "arm64", null),
        "iosSimulatorArm64" to NativeTarget("Darwin", "arm64", "iOS"),
        "tvosSimulatorArm64" to NativeTarget("Darwin", "arm64", "tvOS"),
        "watchosSimulatorArm64" to NativeTarget("Darwin", "arm64", "watchOS"),
        "iosX64" to NativeTarget("Darwin", "x86_64", "iOS"),
        "mingwX64" to NativeTarget("Windows", "AMD64", null),
    )

    val TARGETS: List<String> = NATIVE_TARGETS.keys.toList() + "jsSafari"

    private val XCODE_BUILD = Regex("Build version [0-9A-Za-z]+")

    /**
     * `hosted.runtime_status`: the runner identity a target requires.
     *
     * A Darwin runner must report macOS 26, the pinned Xcode 26.5, and a well-formed Xcode build
     * string; a Windows runner must report Windows Server 2025 build 26100. A simulator target
     * needs at least one available device of its family, and `jsSafari` needs Safari with a
     * matching SafariDriver.
     */
    fun runtimeStatus(target: String, observed: JsonElement?): HostedVerdict {
        val data = observed as? JsonObject
        if (target !in TARGETS || data == null) {
            return HostedVerdict("FAILED", "unknown target or invalid runtime observation")
        }
        val native = NATIVE_TARGETS[target] ?: NativeTarget("Darwin", "arm64", null)
        if (Py.str(data["system"]) != native.system ||
            (Py.str(data["machine"]) ?: "").lowercase() != native.machine.lowercase()
        ) {
            return HostedVerdict("FAILED", "runner OS or architecture differs from selected target")
        }
        val version = pythonStr(data, "os_version")
        if (native.system == "Darwin") {
            if (!version.startsWith("26.")) {
                return HostedVerdict("FAILED", "macOS 26 runner identity is missing")
            }
            if (Py.str(data["xcode_version"]) != "26.5") {
                return HostedVerdict("FAILED", "selected Xcode differs from pinned 26.5")
            }
            val build = Py.str(data["xcode_build"])
            if (build == null || XCODE_BUILD.matchEntire(build) == null) {
                return HostedVerdict("FAILED", "selected Xcode build observation is missing or malformed")
            }
        } else if (!version.startsWith("10.0.26100")) {
            return HostedVerdict("FAILED", "Windows Server 2025 build 26100 identity is missing")
        }
        val simulator = native.simulator
        if (simulator != null && !Py.truthy((data["simulators"] as? JsonObject)?.get(simulator))) {
            return HostedVerdict("UNAVAILABLE", "no available $simulator simulator on selected runner")
        }
        if (target == "jsSafari") {
            val safari = pythonStr(data, "safari_version")
            val driver = pythonStr(data, "safaridriver_version")
            if (safari.isEmpty() || driver.isEmpty()) {
                return HostedVerdict("UNAVAILABLE", "Safari or SafariDriver is absent")
            }
            if (!driver.contains(safari)) {
                return HostedVerdict("FAILED", "SafariDriver version differs from installed Safari")
            }
        }
        return HostedVerdict("READY", "selected runtime is available")
    }

    private class Requirement(
        val probe: JsonElement?,
        val expected: Int,
        val name: String,
        val groups: List<String>,
    )

    /**
     * `hosted.hosted_status`: the bounded hosted summary.
     *
     * Both probes must be this candidate's, complete, and attributable to the frozen groups that
     * `hosted.py` selects for the target. Anything else is `PROBE_FAILED` with the reason of the
     * first check that rejected it.
     */
    fun hostedStatus(
        target: String,
        candidateSha: String,
        runtime: JsonElement?,
        sourceProbe: JsonElement?,
        consumerProbe: JsonElement?,
        hashes: JsonElement?,
        manifest: JsonObject,
    ): HostedVerdict {
        val verdict = runtimeStatus(target, runtime)
        if (verdict.status != "READY") return verdict
        val hashData = hashes as? JsonObject
        if (hashData == null || hashData.keys != Qualification.modules.toSet() ||
            hashData.values.any { !Py.SHA64.matches(pythonStr(it)) }
        ) {
            return HostedVerdict("PROBE_FAILED", "both staged target binary hashes are required")
        }
        val groups = groupsById(manifest)
        val consumerId = "consumer-$target"
        val consumerGroup = groups[consumerId]
            ?: throw IllegalArgumentException("frozen hosted probe group is missing: $consumerId")
        val required = mutableListOf(
            Requirement(
                consumerProbe,
                ProbeManifest.expectedCases(manifest, consumerGroup).size,
                "staged consumer",
                listOf(consumerId),
            ),
        )
        if (target != "jsSafari") {
            val sourceIds = listOf("core-$target", target)
            val count = sourceIds.sumOf { groupId ->
                val group = groups[groupId]
                    ?: throw IllegalArgumentException("frozen hosted probe group is missing: $groupId")
                ProbeManifest.expectedCases(manifest, group).size
            }
            required.add(0, Requirement(sourceProbe, count, "source probe", sourceIds))
        }
        for (requirement in required) {
            val probe = requirement.probe as? JsonObject
            if (probe == null) {
                return HostedVerdict("PROBE_FAILED", "${requirement.name} report is missing")
            }
            val expected = requirement.expected.toLong()
            if (Py.str(probe["candidate_sha"]) != candidateSha ||
                Py.str(probe["status"]) != "PROBE_PASSED" ||
                !Py.equalsInt(probe["expected"], expected) ||
                !Py.equalsInt(probe["executed"], expected) ||
                !Py.equalsInt(probe["failures"], 0L) ||
                !Py.equalsInt(probe["errors"], 0L) ||
                !Py.equalsInt(probe["skipped"], 0L) ||
                !Py.isInt(probe["reported"]) ||
                Py.int(probe["reported"]) < expected ||
                !Py.equalsInt(probe["exit_code"], 0L)
            ) {
                return HostedVerdict(
                    "PROBE_FAILED",
                    "${requirement.name} is stale, partial, failed, or skipped",
                )
            }
            try {
                ProbeManifest.validateAccounting(probe, manifest, requirement.groups)
            } catch (error: IllegalArgumentException) {
                return HostedVerdict(
                    "PROBE_FAILED",
                    "${requirement.name} accounting is invalid: ${error.message}",
                )
            }
        }
        return HostedVerdict("PROBE_PASSED", "frozen source and staged consumer cases executed")
    }

    private fun groupsById(manifest: JsonObject): Map<String, JsonObject> {
        val declared = manifest["groups"] as? JsonArray ?: JsonArray(emptyList())
        val groups = LinkedHashMap<String, JsonObject>()
        for (item in declared) {
            val group = item as? JsonObject ?: continue
            val id = Py.str(group["id"]) ?: continue
            groups[id] = group
        }
        return groups
    }

    /**
     * `hosted.selected_groups`: the frozen manifest reduced to the selected groups, plus their
     * report patterns in the manifest's order.
     */
    fun selectedGroups(manifest: JsonObject, ids: List<String>): Pair<JsonObject, List<String>> {
        val declared = manifest["groups"] as? JsonArray ?: JsonArray(emptyList())
        val groups = declared.mapNotNull { item ->
            (item as? JsonObject)?.takeIf { Py.str(it["id"]) in ids }
        }
        if (groups.size != ids.size) {
            throw IllegalArgumentException("frozen hosted probe group is missing")
        }
        val selected = JsonObject(manifest + ("groups" to JsonArray(groups)))
        val patterns = groups.map { Py.str(it["report_pattern"]) ?: "" }
        return selected to patterns
    }

    /**
     * `hosted.gradle_wrapper`: `repository / ("gradlew.bat" if nt else "gradlew")`.
     *
     * The repository text is kept as given, because the probe command records it verbatim.
     */
    fun gradleWrapper(repository: String, windows: Boolean): String {
        val name = if (windows) "gradlew.bat" else "gradlew"
        val separator = if (windows) "\\" else "/"
        return when {
            repository.isEmpty() -> name
            repository.endsWith("/") || repository.endsWith("\\") -> repository + name
            else -> repository + separator + name
        }
    }

    /** Python `str(value)` for a decoded JSON value, used where the reference calls `str()`. */
    internal fun pythonStr(value: JsonElement?): String = when (value) {
        null -> ""
        is JsonNull -> "None"
        is JsonPrimitive -> if (value.isString) {
            value.content
        } else {
            when (value.content) {
                "true" -> "True"
                "false" -> "False"
                else -> value.content
            }
        }
        else -> value.toString()
    }

    /** `str(observed.get(name, ""))`. */
    private fun pythonStr(observed: JsonObject, name: String): String =
        pythonStr(observed[name] ?: JsonPrimitive(""))
}
