@file:OptIn(
    org.jetbrains.kotlin.gradle.ExperimentalWasmDsl::class,
)

import org.jetbrains.kotlin.gradle.dsl.JvmTarget
import groovy.json.JsonOutput
import java.security.MessageDigest

fun gitValue(vararg arguments: String): String {
    val process = ProcessBuilder(listOf("git", "-C", rootProject.projectDir.parentFile.parentFile.parentFile.absolutePath) + arguments)
        .redirectErrorStream(true).start()
    val output = process.inputStream.bufferedReader().readText().trim()
    check(process.waitFor() == 0) { output }
    return output
}

fun sha256(file: File): String = MessageDigest.getInstance("SHA-256")
    .digest(file.readBytes()).joinToString("") { "%02x".format(it) }

val identityDirectory = layout.buildDirectory.dir("generated/portableIdentity/commonMain/kotlin")
val generatePortableIdentity = tasks.register("generatePortableIdentity") {
    outputs.dir(identityDirectory)
    outputs.upToDateWhen { false }
    doLast {
        val file = identityDirectory.get().file("performance/portable/BuildIdentity.kt").asFile
        file.parentFile.mkdirs()
        file.writeText("package performance.portable\ninternal object BuildIdentity {\n" +
            "    const val sourceSha = \"${gitValue("rev-parse", "HEAD")}\"\n" +
            "    const val producerTree = \"${gitValue("rev-parse", "HEAD:consumers/performance/portable")}\"\n" +
            "}\n")
    }
}

plugins {
    kotlin("multiplatform") version "2.4.20"
    id("com.android.kotlin.multiplatform.library") version "9.3.1"
}

repositories {
    maven { url = uri(providers.gradleProperty("performanceRepository").get()) }
    mavenCentral()
}

kotlin {
    jvmToolchain(21)
    jvm { compilerOptions { jvmTarget.set(JvmTarget.JVM_1_8) } }
    android {
        namespace = "io.github.rubixhacker.performance.portable"
        compileSdk = 36
        minSdk = 21
        withHostTest {}
    }
    js {
        nodejs()
        browser()
        binaries.executable()
    }
    wasmJs { nodejs(); browser(); binaries.executable() }
    wasmWasi { nodejs(); binaries.executable() }
    linuxX64 { binaries.executable { entryPoint = "performance.portable.main" } }
    linuxArm64 { binaries.executable { entryPoint = "performance.portable.main" } }
    mingwX64 { binaries.executable { entryPoint = "performance.portable.main" } }
    macosArm64 { binaries.executable { entryPoint = "performance.portable.main" } }
    iosArm64()
    iosSimulatorArm64()
    iosX64()
    tvosArm64()
    tvosSimulatorArm64()
    watchosArm64()
    watchosDeviceArm64()
    watchosSimulatorArm64()
    androidNativeArm32()
    androidNativeArm64()
    androidNativeX86()
    androidNativeX64()

    sourceSets {
        commonMain { kotlin.srcDir(generatePortableIdentity) }
        commonMain.dependencies { implementation("io.github.rubixhacker:dyn4k:0.1.0-alpha.1") }
        commonTest.dependencies { implementation(kotlin("test")) }
    }
}

tasks.register("portableBuildInventory") {
    dependsOn("linkDebugExecutableLinuxX64", "jsDevelopmentExecutableCompileSync",
              "wasmJsDevelopmentExecutableCompileSync", "compileDevelopmentExecutableKotlinWasmWasi")
    doLast {
        check(gitValue("status", "--porcelain", "--untracked-files=all").isEmpty()) {
            "commit the producer before writing an immutable build inventory"
        }
        val sourceSha = gitValue("rev-parse", "HEAD")
        val tree = gitValue("rev-parse", "HEAD:consumers/performance/portable")
        val sourceFiles = gitValue("ls-tree", "-r", "--name-only", "HEAD",
            "consumers/performance/portable", "tools/performance/sustained_portable")
            .lines().filter { it.isNotBlank() }.associateWith { sha256(rootProject.projectDir.parentFile.parentFile.parentFile.resolve(it)) }
        val targetInfo = mapOf(
            "linuxX64" to Triple("linuxX64CompileKlibraries", "build/bin/linuxX64/debugExecutable", "dyn4k-performance-portable.kexe"),
            "js" to Triple("jsCompileClasspath", "build/compileSync/js/main/developmentExecutable/kotlin", "dyn4k-performance-portable.js"),
            "wasmJs" to Triple("wasmJsCompileClasspath", "build/compileSync/wasmJs/main/developmentExecutable/kotlin", "dyn4k-performance-portable.mjs"),
            "wasmWasi" to Triple("wasmWasiCompileClasspath", "build/compileSync/wasmWasi/main/developmentExecutable/kotlin", "dyn4k-performance-portable.mjs"),
        )
        val outputDirectory = layout.buildDirectory.dir("portable-inventory").get().asFile
        outputDirectory.mkdirs()
        for ((target, info) in targetInfo) {
            val bundleDirectory = project.file(info.second)
            val bundle = bundleDirectory.walkTopDown().filter { it.isFile }.associate {
                it.relativeTo(bundleDirectory).invariantSeparatorsPath to sha256(it)
            }.toSortedMap()
            val artifacts = configurations.getByName(info.first).resolvedConfiguration.resolvedArtifacts.map {
                mapOf("module" to it.moduleVersion.id.toString(), "path" to it.file.canonicalPath,
                      "sha256" to sha256(it.file))
            }.sortedBy { it["module"] }
            val receipt = mapOf(
                "format" to "portable-build-inventory-v1", "source_sha" to sourceSha,
                "producer_tree" to tree, "source_files" to sourceFiles,
                "manifest_sha256" to sha256(rootProject.projectDir.parentFile.parentFile.parentFile.resolve("docs/research/performance-manifest-v1.json")),
                "target" to target, "build" to "development", "gradle" to gradle.gradleVersion,
                "kgp" to "2.4.20", "compile_configuration" to info.first,
                "resolved_artifacts" to artifacts,
                "harness" to bundleDirectory.resolve(info.third).canonicalPath,
                "bundle_sha256" to bundle,
            )
            outputDirectory.resolve("$target-development.json").writeText(JsonOutput.prettyPrint(JsonOutput.toJson(receipt)) + "\n")
        }
    }
}

val nativeHostTarget = providers.gradleProperty("portableNativeHostTarget").orNull
val nativeHostBuild = providers.gradleProperty("portableNativeHostBuild").orNull
tasks.register("portableNativeHostBuildInventory") {
    val targets = mapOf(
        "linuxX64" to "dyn4k-performance-portable.kexe",
        "linuxArm64" to "dyn4k-performance-portable.kexe",
        "mingwX64" to "dyn4k-performance-portable.exe",
        "macosArm64" to "dyn4k-performance-portable.kexe",
    )
    if (nativeHostTarget != null && targets.containsKey(nativeHostTarget) &&
        (nativeHostBuild == "development" || nativeHostBuild == "optimized")) {
        val mode = if (nativeHostBuild == "development") "Debug" else "Release"
        dependsOn("link${mode}Executable${nativeHostTarget.replaceFirstChar { it.uppercase() }}")
    }
    doLast {
        val target = requireNotNull(nativeHostTarget) { "set -PportableNativeHostTarget" }
        val executable = requireNotNull(targets[target]) { "unsupported Native host target: $target" }
        val build = requireNotNull(nativeHostBuild) { "set -PportableNativeHostBuild" }
        require(build == "development" || build == "optimized") { "unsupported Native host build: $build" }
        check(gitValue("status", "--porcelain", "--untracked-files=all").isEmpty()) {
            "commit the producer before writing an immutable build inventory"
        }
        val mode = if (build == "development") "Debug" else "Release"
        val linkTask = "link${mode}Executable${target.replaceFirstChar { it.uppercase() }}"
        val linkState = tasks.named(linkTask).get().state
        check(linkState.executed && !linkState.skipped && linkState.failure == null) {
            "selected Native link did not complete"
        }
        val configuration = "${target}CompileKlibraries"
        val bundleDirectory = project.file("build/bin/$target/${mode.lowercase()}Executable")
        val harness = bundleDirectory.resolve(executable)
        check(harness.isFile) { "selected Native executable is missing: $harness" }
        val sourceSha = gitValue("rev-parse", "HEAD")
        val tree = gitValue("rev-parse", "HEAD:consumers/performance/portable")
        val repository = rootProject.projectDir.parentFile.parentFile.parentFile
        val sourceFiles = gitValue("ls-tree", "-r", "--name-only", "HEAD",
            "consumers/performance/portable", "tools/performance/sustained_portable")
            .lines().filter { it.isNotBlank() }.associateWith { sha256(repository.resolve(it)) }
        val artifacts = configurations.getByName(configuration).resolvedConfiguration.resolvedArtifacts.map {
            mapOf("module" to it.moduleVersion.id.toString(), "path" to it.file.canonicalPath,
                  "sha256" to sha256(it.file))
        }.sortedBy { it["module"] }
        check(artifacts.isNotEmpty()) { "selected Native compilation has no resolved artifacts" }
        val bundle = bundleDirectory.walkTopDown().filter { it.isFile }.associate {
            it.relativeTo(bundleDirectory).invariantSeparatorsPath to sha256(it)
        }.toSortedMap()
        val receipt = mapOf(
            "format" to "portable-build-inventory-v1", "source_sha" to sourceSha,
            "producer_tree" to tree, "source_files" to sourceFiles,
            "manifest_sha256" to sha256(repository.resolve("docs/research/performance-manifest-v1.json")),
            "target" to target, "build" to build, "gradle" to gradle.gradleVersion,
            "kgp" to "2.4.20", "compile_configuration" to configuration,
            "compiler_mode" to mode.lowercase(), "link_task" to linkTask,
            "resolved_artifacts" to artifacts, "harness" to harness.canonicalPath,
            "bundle_sha256" to bundle,
        )
        val outputDirectory = layout.buildDirectory.dir("portable-inventory").get().asFile
        outputDirectory.mkdirs()
        outputDirectory.resolve("$target-$build.json")
            .writeText(JsonOutput.prettyPrint(JsonOutput.toJson(receipt)) + "\n")
    }
}
