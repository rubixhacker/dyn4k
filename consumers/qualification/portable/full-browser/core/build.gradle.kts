@file:OptIn(org.jetbrains.kotlin.gradle.ExperimentalWasmDsl::class)

import org.jetbrains.kotlin.gradle.tasks.KotlinCompilationTask
import org.jetbrains.kotlin.gradle.targets.js.testing.KotlinJsTest
import java.nio.file.Files
import java.security.MessageDigest

plugins { kotlin("multiplatform"); id("de.infix.testBalloon") }

val checkout = file(providers.gradleProperty("qualificationCheckout").get())
val staging = file(providers.gradleProperty("qualificationRepository").get())
val version = "0.1.0-alpha.1"
val lane = providers.gradleProperty("qualificationLaneId").get()
val target = lane.substringBefore(':')
val family = lane.split(':')[1]
val publication = if (target == "js") "js" else "wasm-js"
val configuration = if (target == "js") "jsTest" else "wasmJsTest"

repositories {
    maven { url = uri(staging) }
    mavenCentral()
}

kotlin {
    js {
        browser { testTask { useKarma {
            when (family) {
                "Chromium" -> useChromeHeadless()
                "Firefox" -> useFirefoxHeadless()
                "Safari" -> useSafari()
                else -> error("unsupported browser family")
            }
        } } }
        binaries.executable()
    }
    wasmJs {
        browser { testTask { useKarma {
            when (family) {
                "Chromium" -> useChromeHeadless()
                "Firefox" -> useFirefoxHeadless()
                "Safari" -> useSafari()
                else -> error("unsupported browser family")
            }
        } } }
        binaries.executable()
    }
    sourceSets {
        val commonTest by getting {
            dependencies {
                implementation(kotlin("test"))
                implementation("de.infix.testBalloon:testBalloon-framework-core:1.2.0")
                implementation("io.github.rubixhacker:dyn4k-core:$version")
                implementation("io.github.rubixhacker:dyn4k:$version")
            }
            kotlin.setSrcDirs(listOf(file("$checkout/dyn4k-core/src/commonTest/kotlin")))
        }
        val jsTest by getting {
            kotlin.setSrcDirs(listOf(file("$checkout/dyn4k-core/src/jsTest/kotlin")))
            dependencies {
                implementation(devNpm("karma-firefox-launcher", "^2.1.3"))
                implementation(devNpm("karma-safari-launcher", "1.0.0"))
            }
        }
        val wasmJsTest by getting {
            kotlin.setSrcDirs(listOf(file("$checkout/dyn4k-core/src/wasmJsTest/kotlin")))
            dependencies {
                implementation(devNpm("karma-firefox-launcher", "^2.1.3"))
                implementation(devNpm("karma-safari-launcher", "1.0.0"))
            }
        }
    }
}

fun friend(): File {
    val artifact = configurations.getByName("${configuration}CompileClasspath").resolvedConfiguration
        .resolvedArtifacts.single { it.moduleVersion.id.name == "dyn4k-core-$publication" }.file
    val staged = file("$staging/io/github/rubixhacker/dyn4k-core-$publication/$version/dyn4k-core-$publication-$version.klib")
    fun hash(file: File) = MessageDigest.getInstance("SHA-256").digest(file.readBytes()).toList()
    check(hash(artifact) == hash(staged))
    return artifact
}

tasks.named<KotlinCompilationTask<*>>("compileTestKotlin${target.replaceFirstChar { it.uppercase() }}") {
    dependsOn(":qualificationValidateInputs")
    compilerOptions.freeCompilerArgs.addAll(providers.provider {
        listOf("-Xfriend-modules=${friend().absolutePath}")
    })
}
for (mode in listOf("Development", "Production")) {
    tasks.named<KotlinCompilationTask<*>>("compileTest${mode}ExecutableKotlin${target.replaceFirstChar { it.uppercase() }}") {
        compilerOptions.freeCompilerArgs.addAll(providers.provider {
            listOf("-Xfriend-modules=${friend().absolutePath}")
        })
    }
}

if (providers.gradleProperty("qualificationProduction").orNull == "true") {
    tasks.named<KotlinJsTest>("${target}BrowserTest") {
        if (target == "js") {
            dependsOn("jsTestTestProductionExecutableCompileSync")
            inputFileProperty.set(layout.buildDirectory.file(
                "compileSync/js/test/testProductionExecutable/kotlin/${rootProject.name}-core-test.js"))
        } else {
            dependsOn("compileTestProductionExecutableKotlinWasmJsOptimize")
            inputFileProperty.set(layout.buildDirectory.file(
                "compileSync/wasmJs/test/testProductionExecutable/optimized/${rootProject.name}-core-test.mjs"))
            doFirst {
                val name = "${rootProject.name}-core-test"
                val linked = layout.buildDirectory.dir(
                    "compileSync/wasmJs/test/testProductionExecutable/optimized").get().asFile
                val selected = rootProject.layout.buildDirectory.dir(
                    "wasm/packages/$name/kotlin").get().asFile
                for (suffix in listOf(".mjs", ".wasm", ".wasm.map",
                                      ".js-builtins.mjs", ".import-object.mjs")) {
                    val source = File(linked, "$name$suffix")
                    val copy = File(selected, "$name$suffix")
                    check(source.isFile && !Files.isSymbolicLink(source.toPath())
                        && !Files.isSymbolicLink(copy.toPath()))
                    source.copyTo(copy, overwrite = true)
                    check(source.readBytes().contentEquals(copy.readBytes()))
                }
                logger.lifecycle("qualification optimized package input: ${File(selected, "$name.mjs")}")
            }
        }
        doFirst { logger.lifecycle("qualification test input: ${inputFileProperty.get().asFile}") }
    }
}
