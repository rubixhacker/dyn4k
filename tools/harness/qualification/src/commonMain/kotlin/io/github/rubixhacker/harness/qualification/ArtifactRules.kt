package io.github.rubixhacker.harness.qualification

import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/**
 * The pure part of `tools/qualification/artifact.py`: the Ubuntu probe group mapping and the
 * Ubuntu runtime identity rule.
 *
 * Both are part of retained evidence: the group ids select the frozen probe cases a bundle must
 * carry, and the runtime message is quoted in `verification.json` when a bundle is rejected.
 */
object ArtifactRules {
    /**
     * `UBUNTU_PROBES`: the probe file a bundle must contain, and the frozen groups it covers.
     *
     * The order is the reference's dict order and is the order the bundle counts are accumulated
     * in, so a reordered map would change `verification.json`.
     */
    val UBUNTU_PROBES: Map<String, List<String>> = linkedMapOf(
        "foundation-probe.json" to listOf("core-jvm", "jvm", "core-linuxX64", "linuxX64"),
        "web-probe.json" to listOf(
            "core-jsNode", "jsNode", "core-wasmJsNode", "wasmJsNode",
            "core-wasmWasiNode", "wasmWasiNode",
        ),
        "android-host-probe.json" to listOf("core-androidHost", "androidHost"),
        "portable-consumer-probe.json" to listOf(
            "consumer-jvm", "consumer-linuxX64", "consumer-jsNode", "consumer-wasmJsNode",
            "consumer-wasmWasiNode", "consumer-androidHost",
        ),
    )

    /** `check_ubuntu_runtime`: a bundle's recorded runtime must be the Ubuntu runner it claims. */
    fun checkUbuntuRuntime(runtime: JsonObject?) {
        if (runtime == null || Py.str(runtime["system"]) != "Linux" ||
            (Py.str(runtime["machine"]) ?: "").lowercase() !in setOf("x86_64", "amd64") ||
            !Py.truthy(runtime["distribution"]) || !Py.truthy(runtime["os_version"]) ||
            !Py.truthy(runtime["kernel_release"]) || !Py.truthy(runtime["java_version"])
        ) {
            throw IllegalArgumentException("Ubuntu bundle runtime identity is incomplete or wrong")
        }
        if (Py.truthy(runtime["github_actions"]) &&
            (Py.str(runtime["distribution"]) != "ubuntu" ||
                !Py.truthy(runtime["runner_image_os"]) ||
                !Py.truthy(runtime["runner_image_version"]))
        ) {
            throw IllegalArgumentException("Ubuntu bundle runtime runner image is missing or wrong")
        }
    }

    /** `platform.freedesktop_os_release()`: the os-release keys, or null when no file exists. */
    fun parseOsRelease(lines: List<String>): Map<String, String> {
        val values = LinkedHashMap<String, String>()
        for (line in lines) {
            val trimmed = line.trim()
            if (trimmed.isEmpty() || trimmed.startsWith("#")) continue
            val index = trimmed.indexOf('=')
            if (index <= 0) continue
            val name = trimmed.substring(0, index)
            if (!Regex("[A-Za-z_][A-Za-z0-9_]*").matches(name)) continue
            values[name] = unquote(trimmed.substring(index + 1))
        }
        return values
    }

    /** The reference's shell-like unquoting of one os-release value. */
    private fun unquote(raw: String): String {
        if (raw.length < 2) return raw
        val quote = raw[0]
        if (raw[raw.length - 1] != quote || (quote != '"' && quote != '\'')) return raw
        val body = raw.substring(1, raw.length - 1)
        if (quote == '\'') return body
        val out = StringBuilder()
        var index = 0
        while (index < body.length) {
            val char = body[index]
            if (char != '\\' || index + 1 >= body.length) {
                out.append(char)
                index++
                continue
            }
            val next = body[index + 1]
            when (next) {
                '\\' -> out.append('\\')
                '"' -> out.append('"')
                '\'' -> out.append('\'')
                '$' -> out.append('$')
                '`' -> out.append('`')
                'n' -> out.append('\n')
                't' -> out.append('\t')
                'r' -> out.append('\r')
                else -> out.append('\\').append(next)
            }
            index += 2
        }
        return out.toString()
    }

    /** `str(value)` for one recorded runtime field, used only in messages. */
    internal fun describe(value: JsonElement?): String = Py.str(value) ?: CanonicalText.of(value ?: JsonPrimitive(""))
}
