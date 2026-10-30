package io.github.rubixhacker.harness.qualification

import io.github.rubixhacker.harness.contract.StrictJson
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

/** The reported Karma configuration does not bind the committed reporter to this module. */
class ConfigBindingError(message: String) : IllegalArgumentException(message)

/** A failed staging run left reporter residue behind; [result] is the recorded stage result. */
class StageFailure(val result: JsonObject) : Exception() {
    override val message: String = run {
        val forensic = (result["forensic"] as? JsonArray)?.mapNotNull { it as? JsonObject }
        val failed = forensic?.firstOrNull { Py.truthy(it["error"]) }
        val path = if (failed == null) "karma.config.d" else Py.str(failed["path"]) ?: ""
        "Safari reporter staging residue: " + path.take(256)
    }
}

/**
 * `tools/qualification/safari_reporter.py`: the reporter source binding, the generated Karma
 * configuration contract, and the path helpers of the staged reporter.
 *
 * Everything in this file is pure: the bytes, the configuration text, and the repository path
 * text. The file-system work lives in [SafariReporterHost].
 */
object SafariReporter {
    const val SOURCE = "tools/qualification/safari-karma-reporter.js"
    const val STAGED_NAME = "qualification-safari-reporter.js"

    const val CONSUMER = "consumers/qualification/portable"

    val PROJECTS: List<String> = listOf("dyn4k-core", "dyn4k", CONSUMER)

    const val MAX_FRAGMENT_BYTES = 256 * 1024
    const val MAX_COMMITTED_OBJECT_BYTES = 16 * 1024 * 1024

    val PACKAGES: Map<String, String> = linkedMapOf(
        "dyn4k-core" to "dyn4k-dyn4k-core-test",
        "dyn4k" to "dyn4k-dyn4k-test",
        CONSUMER to "dyn4k-staged-portable-consumer-test",
    )

    /**
     * The exact text the Kotlin Karma generator appends after `config.set({...})`.
     *
     * The generator is pinned: its text is what [`validateConfig`] accepts between the settings
     * object and the reporter fragment. One changed character rejects every generated
     * configuration, so this literal is the contract. It is held as one line per source line and
     * joined, because several lines end in meaningful trailing whitespace.
     */
    val APPROVED_GENERATOR_TAIL: String = listOf(
        "",
        "config.plugins = config.plugins || [];",
        "config.plugins.push(require('kotlin-web-helpers/dist/karma-kotlin-reporter'));",
        "",
        "config.loggers = [",
        "    {",
        "        type: require('kotlin-web-helpers/dist/tc-log-appender'),",
        "        //default layout",
        "        layout: { type: 'pattern', pattern: '%[%d{DATETIME}:%p [%c]: %]%m' }",
        "    }",
        "]",
        "config.plugins = config.plugins || [];",
        "config.plugins.push(require('kotlin-web-helpers/dist/karma-webpack-output'));",
        "",
        "// webpack config",
        "function createWebpackConfig() {",
        "let config = {",
        "  mode: 'development',",
        "  resolve: {",
        "    modules: [",
        "      \"node_modules\"",
        "    ]",
        "  },",
        "  plugins: [],",
        "  module: {",
        "    rules: []",
        "  },",
        "  ",
        "};",
        "",
        "// source maps",
        "config.module.rules.push({",
        "        test: /\\.m?js$/,",
        "        use: [\"source-map-loader\"],",
        "        enforce: \"pre\"",
        "});",
        "config.devtool = false;",
        "config.ignoreWarnings = [",
        "    /Failed to parse source map/,",
        "    /Accessing import\\.meta directly is unsupported \\(only property access or destructuring is supported\\)/",
        "];  ",
        "                // optimization",
        "                config.optimization = config.optimization || {",
        "  \"splitChunks\": false",
        "};",
        "// noinspection JSUnnecessarySemicolon",
        ";(function(config) {",
        "    const tcErrorPlugin = require('kotlin-web-helpers/dist/tc-log-error-webpack');",
        "    config.plugins.push(new tcErrorPlugin())",
        "    config.stats = config.stats || {}",
        "    Object.assign(config.stats, config.stats, {",
        "        warnings: false,",
        "        errors: false",
        "    })",
        "})(config);",
        "config.experiments = {",
        "    topLevelAwait: true,",
        "}",
        "// section: Extra JS code from KotlinWebpackConfig.extraJs",
        "// section end",
        "// noinspection JSUnnecessarySemicolon",
        ";(function(config) {",
        "    const webpack = require('webpack');",
        "",
        "    // https://github.com/webpack/webpack/issues/12951",
        "    const PatchSourceMapSource = require('kotlin-web-helpers/dist/webpack-5-debug');",
        "    config.plugins.push(new PatchSourceMapSource())",
        "    ",
        "    config.plugins.push(new webpack.SourceMapDevToolPlugin({",
        "        moduleFilenameTemplate: \"[absolute-resource-path]\"",
        "    }))",
        "})(config);",
        "   return config;",
        "}",
        "",
        "config.set({webpack: createWebpackConfig()});",
        "",
        "",
        "// $STAGED_NAME",
    ).joinToString("\n") + "\n"

    /**
     * `safari_reporter.config_relative`: where the generator writes the Karma configuration of one
     * project.
     */
    fun configRelative(project: String): String {
        val key = canonicalProject(project)
        val base = if (key == CONSUMER) CONSUMER else ""
        val packageName = packageOf(key)
        return posixJoin(base, "build/js/packages", packageName, "karma.conf.js")
    }

    /**
     * `safari_reporter.validate_config`: the generated configuration must be the pinned generator
     * output that carries exactly one copy of the committed reporter fragment.
     *
     * Returns the configuration mode (`development` or `production`) the file binds, or throws
     * [ConfigBindingError] with the reference reason.
     */
    fun validateConfig(
        data: ByteArray,
        fragment: ByteArray,
        repository: String,
        project: String,
        configuration: String? = null,
    ): String {
        val key = canonicalProject(project)
        if (key !in PACKAGES) throw ConfigBindingError("karma_config_module_mismatch")
        val source = decodeUtf8(data) ?: throw ConfigBindingError("karma_config_invalid_encoding")
        val expected = decodeUtf8(fragment) ?: throw ConfigBindingError("karma_config_invalid_encoding")
        if (countOccurrences(source, expected) != 1) {
            throw ConfigBindingError("reporter_fragment_missing")
        }
        val prefix = "\nmodule.exports = function(config) {\n\nconfig.set("
        if (!source.startsWith(prefix)) throw ConfigBindingError("karma_config_shape_mismatch")
        val end = try {
            RawJsonScanner(source).scan(prefix.length)
        } catch (error: JsonShapeException) {
            throw ConfigBindingError("karma_config_shape_mismatch")
        } catch (error: ConfigBindingError) {
            // The reference raises its duplicate-key error from `object_pairs_hook`, and the
            // surrounding `except (ValueError, TypeError)` converts it to a shape mismatch,
            // because `ConfigBindingError` is a `ValueError`.
            throw ConfigBindingError("karma_config_shape_mismatch")
        }
        val settings = try {
            StrictJson.load(source.substring(prefix.length, end))
        } catch (error: IllegalArgumentException) {
            throw ConfigBindingError("karma_config_shape_mismatch")
        }
        if (settings !is JsonObject || !source.substring(end).startsWith(");")) {
            throw ConfigBindingError("karma_config_shape_mismatch")
        }
        val position = source.indexOf(expected)
        if (source.substring(end + 2, position) != APPROVED_GENERATOR_TAIL ||
            stripWhitespace(source.substring(position + expected.length)) != "}"
        ) {
            throw ConfigBindingError("karma_config_shape_mismatch")
        }
        val root = posixJoin(repository, key)
        val packageName = PACKAGES.getValue(key)
        val packageBuildRoot = if (key == CONSUMER) root else repository
        val packageRoot = posixJoin(packageBuildRoot, "build/js/packages", packageName)
        if (Py.str(settings["basePath"]) != packageRoot) {
            throw ConfigBindingError("karma_config_module_mismatch")
        }
        val runner = posixJoin(
            packageBuildRoot,
            "build/js/node_modules/kotlin-web-helpers/dist/kotlin-test-karma-runner.js",
        )
        val inputs = linkedMapOf(
            "development" to posixJoin(packageRoot, "kotlin", "$packageName.js"),
            "production" to
                posixJoin(
                    root,
                    "build/compileSync/js/test/testProductionExecutable/kotlin",
                    "$packageName.js",
                ),
        )
        val files = settings["files"]
        var observed: String? = null
        for ((mode, path) in inputs) {
            if (files == JsonArray(listOf(JsonPrimitive(runner), JsonPrimitive(path)))) {
                observed = mode
                break
            }
        }
        if (observed == null || (configuration != null && configuration != observed)) {
            throw ConfigBindingError("karma_config_source_mismatch")
        }
        val selected = (files as JsonArray)[1]
        val approved = buildJsonObject {
            put("singleRun", JsonPrimitive(true))
            put("autoWatch", JsonPrimitive(false))
            put("basePath", JsonPrimitive(packageRoot))
            put("files", JsonArray(listOf(JsonPrimitive(runner), selected)))
            put(
                "frameworks",
                JsonArray(listOf(JsonPrimitive("webpack-output"), JsonPrimitive("mocha"), JsonPrimitive("webpack"))),
            )
            put("client", buildJsonObject { put("args", JsonArray(emptyList())) })
            put("browsers", JsonArray(listOf(JsonPrimitive("Safari"))))
            put("customLaunchers", buildJsonObject { })
            put("failOnFailingTestSuite", JsonPrimitive(false))
            put("failOnEmptyTestSuite", JsonPrimitive(false))
            put("reporters", JsonArray(listOf(JsonPrimitive("karma-kotlin-reporter"))))
            put(
                "preprocessors",
                buildJsonObject {
                    put(runner, JsonArray(listOf(JsonPrimitive("webpack"), JsonPrimitive("sourcemap"))))
                    put(Py.str(selected)!!, JsonArray(listOf(JsonPrimitive("webpack"), JsonPrimitive("sourcemap"))))
                },
            )
            put("proxies", buildJsonObject { })
            put("webpackCopy", JsonArray(emptyList()))
        }
        if (settings != approved) throw ConfigBindingError("karma_config_source_mismatch")
        return observed
    }

    /** `PACKAGES[project]`; an unknown project is a programming error, as in the reference. */
    fun packageOf(project: String): String =
        PACKAGES[canonicalProject(project)]
            ?: throw IllegalArgumentException("unknown Safari reporter project: $project")

    /**
     * `pathlib`'s spelling of a relative project: `dyn4k-core/` and `./dyn4k-core` are the same
     * project. An absolute path is left alone so it cannot match a known project.
     */
    internal fun canonicalProject(text: String): String {
        if (text.startsWith("/")) return text
        return text.split('/').filter { it.isNotEmpty() && it != "." }.joinToString("/")
    }

    /** `str(Path(...) / ...)` for the POSIX hosts the Safari lane runs on. */
    internal fun posixJoin(vararg parts: String): String {
        var result = ""
        for (part in parts) {
            if (part.isEmpty() || part == ".") continue
            result = if (result.isEmpty()) {
                part
            } else {
                result.trimEnd('/') + "/" + part.trimStart('/')
            }
        }
        return result
    }

    /** Strict UTF-8 decoding: invalid bytes are a binding error, not a replacement character. */
    internal fun decodeUtf8(bytes: ByteArray): String? {
        val out = StringBuilder(bytes.size)
        var index = 0
        while (index < bytes.size) {
            val first = bytes[index].toInt() and 0xFF
            when {
                first < 0x80 -> {
                    out.append(first.toChar())
                    index += 1
                }
                first in 0xC2..0xDF -> {
                    val second = continuation(bytes, index + 1) ?: return null
                    out.append((((first and 0x1F) shl 6) or second).toChar())
                    index += 2
                }
                first in 0xE0..0xEF -> {
                    val second = continuation(bytes, index + 1) ?: return null
                    val low = if (first == 0xE0) 0xA0 else 0x80
                    val high = if (first == 0xED) 0x9F else 0xBF
                    if (second !in low..high) return null
                    val third = continuation(bytes, index + 2) ?: return null
                    out.append((((first and 0x0F) shl 12) or (second shl 6) or third).toChar())
                    index += 3
                }
                first in 0xF0..0xF4 -> {
                    val second = continuation(bytes, index + 1) ?: return null
                    val low = if (first == 0xF0) 0x90 else 0x80
                    val high = if (first == 0xF4) 0x8F else 0xBF
                    if (second !in low..high) return null
                    val third = continuation(bytes, index + 2) ?: return null
                    val fourth = continuation(bytes, index + 3) ?: return null
                    val code = ((first and 0x07) shl 18) or (second shl 12) or (third shl 6) or fourth
                    if (code < 0x10000) {
                        out.append(code.toChar())
                    } else {
                        val adjusted = code - 0x10000
                        out.append((0xD800 + (adjusted shr 10)).toChar())
                        out.append((0xDC00 + (adjusted and 0x3FF)).toChar())
                    }
                    index += 4
                }
                else -> return null
            }
        }
        return out.toString()
    }

    private fun continuation(bytes: ByteArray, index: Int): Int? {
        if (index >= bytes.size) return null
        val value = bytes[index].toInt() and 0xFF
        return if (value in 0x80..0xBF) value else null
    }

    private fun countOccurrences(text: String, needle: String): Int {
        if (needle.isEmpty()) return text.length + 1
        var count = 0
        var index = text.indexOf(needle)
        while (index >= 0) {
            count++
            index = text.indexOf(needle, index + needle.length)
        }
        return count
    }

    /** `re.fullmatch(r"\s*}\s*", text)` for ASCII whitespace. */
    private fun stripWhitespace(text: String): String {
        var start = 0
        var end = text.length
        while (start < end && isJsonWhitespace(text[start])) start++
        while (end > start && isJsonWhitespace(text[end - 1])) end--
        return text.substring(start, end)
    }

    private fun isJsonWhitespace(char: Char): Boolean =
        char == ' ' || char == '\t' || char == '\n' || char == '\r'
}

/** Invalid JSON text inside the generated configuration. */
private class JsonShapeException : Exception()

/**
 * The locating half of `json.JSONDecoder.raw_decode`: it validates one JSON value that starts
 * exactly at a given offset and reports where it ends, rejecting duplicate object keys while the
 * keys are still text.
 */
private class RawJsonScanner(private val text: String) {
    private var index = 0

    fun scan(start: Int): Int {
        index = start
        value()
        return index
    }

    private fun fail(): Nothing = throw JsonShapeException()

    private fun peek(): Char? = if (index < text.length) text[index] else null

    private fun value() {
        when (peek()) {
            '{' -> obj()
            '[' -> array()
            '"' -> string()
            't' -> literal("true")
            'f' -> literal("false")
            'n' -> literal("null")
            '-' -> number()
            in '0'..'9' -> number()
            else -> fail()
        }
    }

    private fun obj() {
        index++
        whitespace()
        if (peek() == '}') {
            index++
            return
        }
        val names = mutableSetOf<String>()
        while (true) {
            whitespace()
            if (peek() != '"') fail()
            val name = string()
            if (!names.add(name)) throw ConfigBindingError("karma_config_duplicate_setting")
            whitespace()
            if (peek() != ':') fail()
            index++
            whitespace()
            value()
            whitespace()
            when (peek()) {
                ',' -> index++
                '}' -> {
                    index++
                    return
                }
                else -> fail()
            }
        }
    }

    private fun array() {
        index++
        whitespace()
        if (peek() == ']') {
            index++
            return
        }
        while (true) {
            whitespace()
            value()
            whitespace()
            when (peek()) {
                ',' -> index++
                ']' -> {
                    index++
                    return
                }
                else -> fail()
            }
        }
    }

    private fun string(): String {
        index++
        val out = StringBuilder()
        while (true) {
            val char = peek() ?: fail()
            index++
            when {
                char == '"' -> return out.toString()
                char == '\\' -> {
                    val escape = peek() ?: fail()
                    index++
                    when (escape) {
                        '"' -> out.append('"')
                        '\\' -> out.append('\\')
                        '/' -> out.append('/')
                        'b' -> out.append('\b')
                        'f' -> out.append('\u000C')
                        'n' -> out.append('\n')
                        'r' -> out.append('\r')
                        't' -> out.append('\t')
                        'u' -> {
                            if (index + 4 > text.length) fail()
                            val digits = text.substring(index, index + 4)
                            val code = digits.toIntOrNull(16) ?: fail()
                            index += 4
                            out.append(code.toChar())
                        }
                        else -> fail()
                    }
                }
                char.code < 0x20 -> fail()
                else -> out.append(char)
            }
        }
    }

    private fun number() {
        if (peek() == '-') index++
        when (peek()) {
            '0' -> index++
            in '1'..'9' -> while (peek()?.let { it in '0'..'9' } == true) index++
            else -> fail()
        }
        if (peek() == '.') {
            index++
            digits()
        }
        if (peek() == 'e' || peek() == 'E') {
            index++
            if (peek() == '+' || peek() == '-') index++
            digits()
        }
    }

    private fun digits() {
        if (peek()?.let { it in '0'..'9' } != true) fail()
        while (peek()?.let { it in '0'..'9' } == true) index++
    }

    private fun literal(literal: String) {
        if (!text.startsWith(literal, index)) fail()
        index += literal.length
    }

    private fun whitespace() {
        while (peek()?.let { it == ' ' || it == '\t' || it == '\n' || it == '\r' } == true) index++
    }
}
