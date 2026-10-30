package io.github.rubixhacker.harness.contract

/**
 * Publication contract of the harness, ported from `tools/qualification/qualify.py`.
 *
 * The values in this file are part of retained evidence. A changed value invalidates
 * evidence that records the previous one.
 */
object Qualification {
    const val VERSION = "0.1.0-alpha.1"
    const val GROUP = "io.github.rubixhacker"
    const val KOTLIN_VERSION = "2.4.20"

    val modules = listOf("dyn4k-core", "dyn4k")

    private val appleTargets = setOf(
        "iosArm64", "iosSimulatorArm64", "iosX64", "macosArm64",
        "tvosArm64", "tvosSimulatorArm64", "watchosArm64",
        "watchosDeviceArm64", "watchosSimulatorArm64",
    )

    private class Group(val target: String, val runtimes: List<String>, val floor: String, val kind: String)

    private val groups = listOf(
        Group("jvm", listOf("Java"), "8", "jvm"),
        Group("android", listOf("Android JVM"), "API 21", "android"),
        Group("js", listOf("Chromium", "Firefox", "Safari", "Node.js"), "119/120/18.2/22.0.0", "web"),
        Group("wasmJs", listOf("Chromium", "Firefox", "Safari", "Node.js"), "119/120/18.2/22.0.0", "web"),
        Group("wasmWasi", listOf("Node.js", "Wasmtime"), "24.15.0/37.0.0", "web"),
        Group("linuxX64", listOf("Linux x64"), "kernel 4.9.156 glibc 2.19", "native"),
        Group("linuxArm64", listOf("Linux ARM64"), "kernel 4.9.156 glibc 2.25", "native"),
        Group("mingwX64", listOf("Windows x64"), "Windows 10 1507 build 10240", "native"),
        Group("macosArm64", listOf("macOS ARM64"), "macOS 11", "native"),
        Group("iosArm64", listOf("iOS physical ARM64"), "iOS 15", "native"),
        Group("iosSimulatorArm64", listOf("iOS simulator ARM64"), "iOS 15", "native"),
        Group("iosX64", listOf("iOS simulator x64"), "iOS 15", "native"),
        Group("tvosArm64", listOf("tvOS physical ARM64"), "tvOS 15", "native"),
        Group("tvosSimulatorArm64", listOf("tvOS simulator ARM64"), "tvOS 15", "native"),
        Group("watchosArm64", listOf("watchOS physical ILP32"), "watchOS 8", "native"),
        Group("watchosDeviceArm64", listOf("watchOS physical LP64"), "watchOS 26", "native"),
        Group("watchosSimulatorArm64", listOf("watchOS simulator ARM64"), "watchOS 8", "native"),
        Group("androidNativeArm32", listOf("Android Native armeabi-v7a"), "API 21", "native"),
        Group("androidNativeArm64", listOf("Android Native arm64-v8a"), "API 21", "native"),
        Group("androidNativeX86", listOf("Android Native x86"), "API 21", "native"),
        Group("androidNativeX64", listOf("Android Native x86_64"), "API 21", "native"),
    )

    private val webFloors = mapOf(
        "Chromium" to "119",
        "Firefox" to "120",
        "Safari" to "18.2",
        "Node.js" to "22.0.0",
    )

    private val wasiFloors = mapOf(
        "Node.js" to "24.15.0 without experimental Wasm flags",
        "Wasmtime" to "37.0.0 with -W gc=y -W exceptions=y -W function-references=y",
    )

    private val configurations = mapOf(
        "jvm" to listOf("no-optimize", "default"),
        "android" to listOf("debug", "r8-optimized"),
        "web" to listOf("development", "production"),
        "native" to listOf("debug-g", "optimized-opt"),
    )

    /** Returns every target and runtime pair with its minimum supported version. */
    fun matrix(): List<MatrixRow> = groups.flatMap { group ->
        group.runtimes.map { runtime ->
            val minimum = when (group.target) {
                "js", "wasmJs" -> webFloors.getValue(runtime)
                "wasmWasi" -> wasiFloors.getValue(runtime)
                else -> group.floor
            }
            MatrixRow(group.target, runtime, minimum, group.kind)
        }
    }

    /** Expands each matrix row into the minimum and current versions and its configurations. */
    fun expand(rows: List<MatrixRow> = matrix()): List<MatrixCase> = rows.flatMap { row ->
        listOf("minimum", "current").flatMap { version ->
            configurations.getValue(row.kind).map { configuration ->
                MatrixCase(
                    target = row.target,
                    runtime = row.runtime,
                    minimum = row.minimum,
                    kind = row.kind,
                    version = version,
                    configuration = configuration,
                    id = "${row.target}:${row.runtime}:$version:$configuration",
                )
            }
        }
    }

    /** Maps a target to its publication name, for example `wasmJs` to `wasm-js`. */
    fun targetPublicationName(module: String, target: String): String {
        val suffix = target.lowercase().replace("wasmjs", "wasm-js").replace("wasmwasi", "wasm-wasi")
        return "$module-$suffix"
    }

    fun matrixTargets(): Set<String> = matrix().map { it.target }.toSet()

    fun targetBinaryPath(module: String, target: String): String {
        val publication = targetPublicationName(module, target)
        val extension = when (target) {
            "android" -> ".aar"
            "jvm" -> ".jar"
            else -> ".klib"
        }
        return "${GROUP.replace(".", "/")}/$publication/$VERSION/$publication-$VERSION$extension"
    }

    fun publicationBinaryPath(module: String, target: String?): String {
        if (target != null) return targetBinaryPath(module, target)
        return "${GROUP.replace(".", "/")}/$module/$VERSION/$module-$VERSION.jar"
    }

    /** Returns the Gradle variant attributes of one publication variant. */
    fun variantAttributes(target: String?, kind: String): Map<String, String> {
        val platform = when (target) {
            null -> "common"
            "jvm" -> "jvm"
            "android" -> "androidJvm"
            "js" -> "js"
            "wasmJs", "wasmWasi" -> "wasm"
            else -> "native"
        }
        val usage = when {
            (target == null && kind == "Api") || kind == "Metadata" -> "kotlin-metadata"
            kind == "Api" && (target == "jvm" || target == "android") -> "java-api"
            (kind == "Runtime" || kind == "Sources") && (target == "jvm" || target == "android") ->
                "java-runtime"
            kind == "Api" -> "kotlin-api"
            else -> "kotlin-runtime"
        }

        val attributes = linkedMapOf(
            "org.gradle.category" to if (kind == "Sources") "documentation" else "library",
            "org.gradle.jvm.environment" to when (target) {
                "jvm" -> "standard-jvm"
                "android" -> "android"
                else -> "non-jvm"
            },
            "org.gradle.usage" to usage,
            "org.jetbrains.kotlin.platform.type" to platform,
        )

        if (kind == "Sources") {
            attributes["org.gradle.dependency.bundling"] = "external"
            attributes["org.gradle.docstype"] = "sources"
        }
        if (target == "jvm" || target == "android") {
            attributes["org.gradle.libraryelements"] =
                if (kind == "Sources" || target == "jvm") "jar" else "aar"
        }
        if (target == "js") {
            attributes["org.jetbrains.kotlin.js.compiler"] = "ir"
        }
        if (target == "wasmJs" || target == "wasmWasi") {
            attributes["org.jetbrains.kotlin.wasm.target"] = if (target == "wasmJs") "js" else "wasi"
        }
        if (platform == "native") {
            attributes["org.jetbrains.kotlin.native.target"] = nativeTargetName(target!!)
        }
        return attributes
    }

    /** Converts a Kotlin target name to the native target attribute, for example `linuxX64`. */
    fun nativeTargetName(target: String): String =
        Regex("([a-z0-9])([A-Z])")
            .replace(target) { match -> match.groupValues[1] + "_" + match.groupValues[2] }
            .lowercase()
            .replace("android_native_", "android_")

    /** Rejects a dependency graph that contains both the Java and the Kotlin provider. */
    fun checkProviders(graph: String) {
        val javaProvider = Regex("(?:^|\\W)org\\.dyn4j:dyn4j(?::|\\W)")
        val kotlinProvider = Regex("(?:^|\\W)io\\.github\\.rubixhacker:dyn4k-core(?:-jvm)?(?::|\\W)")
        if (javaProvider.containsMatchIn(graph) && kotlinProvider.containsMatchIn(graph)) {
            throw IllegalArgumentException(
                "duplicate org.dyn4j provider: exclude org.dyn4j:dyn4j from the consumer dependency graph",
            )
        }
    }

    fun isAppleTarget(target: String): Boolean = target in appleTargets
}

/** One target and runtime pair of the qualification matrix. */
data class MatrixRow(
    val target: String,
    val runtime: String,
    val minimum: String,
    val kind: String,
)

/** One executable case of the qualification matrix. */
data class MatrixCase(
    val target: String,
    val runtime: String,
    val minimum: String,
    val kind: String,
    val version: String,
    val configuration: String,
    val id: String,
)
