@file:OptIn(
    org.jetbrains.kotlin.gradle.ExperimentalWasmDsl::class,
)

import org.jetbrains.kotlin.gradle.dsl.JvmTarget
import groovy.json.JsonOutput
import groovy.json.JsonSlurper
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
    id("de.infix.testBalloon") version "1.2.0"
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
    iosArm64 { binaries.executable { entryPoint = "performance.portable.main" } }
    iosSimulatorArm64 { binaries.executable { entryPoint = "performance.portable.main" } }
    iosX64 { binaries.executable { entryPoint = "performance.portable.main" } }
    tvosArm64 { binaries.executable { entryPoint = "performance.portable.main" } }
    tvosSimulatorArm64 { binaries.executable { entryPoint = "performance.portable.main" } }
    watchosArm64 { binaries.executable { entryPoint = "performance.portable.main" } }
    watchosDeviceArm64 { binaries.executable { entryPoint = "performance.portable.main" } }
    watchosSimulatorArm64 { binaries.executable { entryPoint = "performance.portable.main" } }
    androidNativeArm32 { binaries.executable { entryPoint = "performance.portable.main" } }
    androidNativeArm64 { binaries.executable { entryPoint = "performance.portable.main" } }
    androidNativeX86 { binaries.executable { entryPoint = "performance.portable.main" } }
    androidNativeX64 { binaries.executable { entryPoint = "performance.portable.main" } }

    sourceSets {
        commonMain { kotlin.srcDir(generatePortableIdentity) }
        commonMain.dependencies { implementation("io.github.rubixhacker:dyn4k:0.1.0-alpha.1") }
        commonTest.dependencies {
            implementation(kotlin("test"))
            implementation("de.infix.testBalloon:testBalloon-framework-core:1.2.0")
        }
        listOf(
            "linuxX64", "linuxArm64", "macosArm64",
            "iosArm64", "iosSimulatorArm64", "iosX64",
            "tvosArm64", "tvosSimulatorArm64",
            "watchosArm64", "watchosDeviceArm64", "watchosSimulatorArm64",
            "androidNativeArm32", "androidNativeArm64", "androidNativeX86", "androidNativeX64",
        ).forEach { target ->
            getByName("${target}Main").kotlin.srcDir("src/posixNativeMain/kotlin")
        }
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

val mobileTarget = providers.gradleProperty("portableMobileTarget").orNull
val mobileBuild = providers.gradleProperty("portableMobileBuild").orNull
val appleMobileTargets = mapOf(
    "iosArm64" to Pair("iPhoneOS", "1,2"),
    "iosSimulatorArm64" to Pair("iPhoneSimulator", "1,2"),
    "iosX64" to Pair("iPhoneSimulator", "1,2"),
    "tvosArm64" to Pair("AppleTVOS", "3"),
    "tvosSimulatorArm64" to Pair("AppleTVSimulator", "3"),
    "watchosArm64" to Pair("WatchOS", "4"),
    "watchosDeviceArm64" to Pair("WatchOS", "4"),
    "watchosSimulatorArm64" to Pair("WatchSimulator", "4"),
)
val androidMobileTargets = mapOf(
    "androidNativeArm32" to "armeabi-v7a",
    "androidNativeArm64" to "arm64-v8a",
    "androidNativeX86" to "x86",
    "androidNativeX64" to "x86_64",
)
val selectedMobileTarget = mobileTarget?.takeIf { it in appleMobileTargets || it in androidMobileTargets }
val selectedMobileMode = when (mobileBuild) {
    "development" -> "Debug"
    "optimized" -> "Release"
    else -> null
}
val selectedMobileLink = if (selectedMobileTarget != null && selectedMobileMode != null)
    "link${selectedMobileMode}Executable${selectedMobileTarget.replaceFirstChar { it.uppercase() }}" else null

val packagePortableMobileApp = tasks.register("packagePortableMobileApp") {
    if (selectedMobileLink != null && selectedMobileTarget in appleMobileTargets) dependsOn(selectedMobileLink)
    doLast {
        val target = requireNotNull(selectedMobileTarget) { "set a supported -PportableMobileTarget" }
        val (platform, families) = requireNotNull(appleMobileTargets[target]) {
            "app packaging applies only to Apple mobile targets"
        }
        val mode = requireNotNull(selectedMobileMode) { "set -PportableMobileBuild=development or optimized" }
        val linkState = tasks.named(requireNotNull(selectedMobileLink)).get().state
        check(linkState.executed && !linkState.skipped && linkState.failure == null) {
            "selected Apple mobile link did not complete"
        }
        val executable = project.file("build/bin/$target/${mode.lowercase()}Executable/dyn4k-performance-portable.kexe")
        check(executable.isFile) { "selected Apple mobile executable is missing: $executable" }
        val linkedSha = sha256(executable)
        val linkedSize = executable.length()
        check(linkedSize > 0) { "selected Apple mobile executable is empty" }
        val app = project.file("build/mobile-app/$target/${mode.lowercase()}/Dyn4kPerformance.app")
        app.mkdirs()
        val image = app.resolve("Dyn4kPerformance")
        executable.copyTo(image, overwrite = true)
        image.setExecutable(true)
        val copiedSha = sha256(image)
        val copiedSize = image.length()
        check(copiedSha == linkedSha && copiedSize == linkedSize) {
            "Apple app copy differs from selected mobile link"
        }
        val bundleId = "io.github.rubixhacker.dyn4k.performance.${target.lowercase()}"
        val minimum = if (target == "watchosDeviceArm64") "26.0" else if (target.startsWith("watchos")) "8.0" else "15.0"
        val watchApplication = if (target.startsWith("watchos"))
            "<key>WKApplication</key><true/><key>WKWatchOnly</key><true/>" else ""
        app.resolve("Info.plist").writeText("""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleIdentifier</key><string>$bundleId</string>
<key>CFBundleName</key><string>Dyn4kPerformance</string>
<key>CFBundleDisplayName</key><string>Dyn4k Performance</string>
<key>CFBundleExecutable</key><string>Dyn4kPerformance</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleVersion</key><string>1</string>
<key>CFBundleShortVersionString</key><string>1.0</string>
<key>CFBundleSupportedPlatforms</key><array><string>$platform</string></array>
<key>UIDeviceFamily</key><array>${families.split(',').joinToString("") { "<integer>$it</integer>" }}</array>
<key>MinimumOSVersion</key><string>$minimum</string>
$watchApplication
</dict></plist>
""")
        val simulator = "Simulator" in target || target == "iosX64"
        val signCommand = if (simulator)
            listOf("codesign", "--force", "--sign", "-", "--timestamp=none", app.absolutePath) else null
        val verifyCommand = if (simulator)
            listOf("codesign", "--verify", app.absolutePath) else null
        if (signCommand != null && verifyCommand != null) {
            val signing = ProcessBuilder(signCommand)
                .redirectErrorStream(true).start()
            val output = signing.inputStream.bufferedReader().readText()
            check(signing.waitFor() == 0) { "simulator app signing failed: $output" }
            val verification = ProcessBuilder(verifyCommand).redirectErrorStream(true).start()
            val verificationOutput = verification.inputStream.bufferedReader().readText()
            check(verification.waitFor() == 0) { "simulator app signature verification failed: $verificationOutput" }
        }
        val derivation = mapOf(
            "format" to "portable-apple-image-derivation-v1", "target" to target,
            "build" to mobileBuild, "linked_path" to executable.canonicalPath,
            "linked_sha256" to linkedSha, "linked_size" to linkedSize,
            "copied_sha256" to copiedSha, "copied_size" to copiedSize,
            "package_path" to app.canonicalPath,
            "packaged_sha256" to sha256(image), "packaged_size" to image.length(),
            "signing" to if (simulator) "ad_hoc" else "none",
            "signing_command" to signCommand, "verification_command" to verifyCommand,
            "codesign_verified" to simulator,
        )
        app.parentFile.resolve("image-derivation.json")
            .writeText(JsonOutput.prettyPrint(JsonOutput.toJson(derivation)) + "\n")
    }
}

tasks.register("portableMobileBuildInventory") {
    if (selectedMobileLink != null) {
        dependsOn(if (selectedMobileTarget in appleMobileTargets) packagePortableMobileApp else selectedMobileLink)
    }
    doLast {
        val target = requireNotNull(selectedMobileTarget) { "set a supported -PportableMobileTarget" }
        val build = requireNotNull(mobileBuild) { "set -PportableMobileBuild" }
        val mode = requireNotNull(selectedMobileMode) { "unsupported mobile build: $build" }
        val linkTask = requireNotNull(selectedMobileLink)
        val linkState = tasks.named(linkTask).get().state
        check(linkState.executed && !linkState.skipped && linkState.failure == null) {
            "selected mobile Native link did not complete"
        }
        check(gitValue("status", "--porcelain", "--untracked-files=all").isEmpty()) {
            "commit the producer before writing an immutable build inventory"
        }
        val repository = rootProject.projectDir.parentFile.parentFile.parentFile
        val sourceSha = gitValue("rev-parse", "HEAD")
        val tree = gitValue("rev-parse", "HEAD:consumers/performance/portable")
        val sourceFiles = gitValue("ls-tree", "-r", "--name-only", "HEAD",
            "consumers/performance/portable", "tools/performance/sustained_portable")
            .lines().filter { it.isNotBlank() }.associateWith { sha256(repository.resolve(it)) }
        val binaryDirectory = project.file("build/bin/$target/${mode.lowercase()}Executable")
        val linked = binaryDirectory.resolve("dyn4k-performance-portable.kexe")
        check(linked.isFile) { "selected mobile executable is missing: $linked" }
        val apple = target in appleMobileTargets
        val bundleDirectory = if (apple)
            project.file("build/mobile-app/$target/${mode.lowercase()}/Dyn4kPerformance.app") else binaryDirectory
        val harness = if (apple) bundleDirectory.resolve("Dyn4kPerformance") else linked
        check(harness.isFile) { "selected mobile process image is missing: $harness" }
        val imageDerivation = if (apple) {
            val receipt = bundleDirectory.parentFile.resolve("image-derivation.json")
            check(receipt.isFile) { "Apple image derivation receipt is missing" }
            JsonSlurper().parse(receipt)
        } else null
        val artifacts = configurations.getByName("${target}CompileKlibraries")
            .resolvedConfiguration.resolvedArtifacts.map {
                mapOf("module" to it.moduleVersion.id.toString(), "path" to it.file.canonicalPath,
                      "sha256" to sha256(it.file))
            }.sortedBy { it["module"] }
        check(artifacts.isNotEmpty()) { "selected mobile compilation has no resolved artifacts" }
        val bundle = bundleDirectory.walkTopDown().filter { it.isFile }.associate {
            it.relativeTo(bundleDirectory).invariantSeparatorsPath to sha256(it)
        }.toSortedMap()
        val receipt = mapOf(
            "format" to "portable-mobile-build-inventory-v1", "source_sha" to sourceSha,
            "producer_tree" to tree, "source_files" to sourceFiles,
            "manifest_sha256" to sha256(repository.resolve("docs/research/performance-manifest-v1.json")),
            "target" to target, "build" to build, "gradle" to gradle.gradleVersion,
            "kgp" to "2.4.20", "compiler_mode" to mode.lowercase(),
            "compile_configuration" to "${target}CompileKlibraries", "link_task" to linkTask,
            "resolved_artifacts" to artifacts, "linked_executable" to linked.canonicalPath,
            "linked_sha256" to sha256(linked), "harness" to harness.canonicalPath,
            "image_derivation" to imageDerivation,
            "signed_image_sha256" to if (apple) sha256(harness) else null,
            "signed_image_size" to if (apple) harness.length() else null,
            "app_bundle" to if (apple) bundleDirectory.canonicalPath else null,
            "bundle_id" to if (apple) "io.github.rubixhacker.dyn4k.performance.${target.lowercase()}" else null,
            "abi" to androidMobileTargets[target], "bundle_sha256" to bundle,
        )
        val outputDirectory = layout.buildDirectory.dir("portable-inventory").get().asFile
        outputDirectory.mkdirs()
        outputDirectory.resolve("$target-$build.json")
            .writeText(JsonOutput.prettyPrint(JsonOutput.toJson(receipt)) + "\n")
    }
}
