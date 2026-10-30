@file:OptIn(org.jetbrains.kotlin.gradle.ExperimentalWasmDsl::class)

import org.jetbrains.kotlin.gradle.dsl.JvmTarget
import org.jetbrains.kotlin.gradle.plugin.mpp.NativeBuildType

plugins {
    kotlin("multiplatform")
    id("com.android.kotlin.multiplatform.library")
    `maven-publish`
    id("org.jetbrains.dokka")
    id("de.infix.testBalloon")
}

kotlin {
    jvmToolchain(21)
    jvm {
        compilerOptions {
            jvmTarget.set(JvmTarget.JVM_1_8)
            val mode = providers.gradleProperty("jvmCompilerMode").orElse("default").get()
            require(mode == "default" || mode == "no-optimize") { "unknown JVM compiler mode: $mode" }
            if (mode == "no-optimize") freeCompilerArgs.add("-Xno-optimize")
        }
    }
    android {
        namespace = "io.github.rubixhacker.dyn4k"
        compileSdk = 36
        minSdk = 21
        withHostTest {}
        compilerOptions { jvmTarget.set(JvmTarget.JVM_1_8) }
    }
    js {
        nodejs()
        browser {
            testTask {
                useKarma {
                    if (System.getenv("DYN4K_BROWSER") == "firefox") useFirefoxHeadless()
                    else useChromeHeadless()
                }
            }
        }
    }
    wasmJs {
        nodejs()
        browser {
            testTask {
                useKarma {
                    if (System.getenv("DYN4K_BROWSER") == "firefox") useFirefoxHeadless()
                    else useChromeHeadless()
                }
            }
        }
    }
    wasmWasi { nodejs(); wasmtime() }
    linuxX64 {
        binaries { test(setOf(NativeBuildType.RELEASE)) }
    }
    linuxArm64()
    mingwX64()
    macosArm64()
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
    androidNativeX64 {
        binaries { test(setOf(NativeBuildType.RELEASE)) }
    }

    sourceSets {
        commonMain.dependencies { api(project(":dyn4k-core")) }
        commonTest.dependencies {
            implementation(kotlin("test"))
            implementation("de.infix.testBalloon:testBalloon-framework-core:1.2.0")
        }
        jsTest.dependencies {
            implementation(devNpm("karma-safari-launcher", "1.0.0"))
            implementation(devNpm("karma-firefox-launcher", "^2.1.3"))
        }
    }
}

tasks.named<org.jetbrains.kotlin.gradle.tasks.KotlinCompile>("compileKotlinJvm") {
    doFirst { logger.lifecycle("JVM compiler flags ${project.path}: ${compilerOptions.freeCompilerArgs.get()}") }
}

if (providers.gradleProperty("qualificationProduction").orNull == "true") {
    tasks.named<org.jetbrains.kotlin.gradle.targets.js.testing.KotlinJsTest>("jsBrowserTest") {
        dependsOn("jsTestTestProductionExecutableCompileSync")
        inputFileProperty.set(layout.buildDirectory.file(
            "compileSync/js/test/testProductionExecutable/kotlin/${rootProject.name}-${project.name}-test.js"
        ))
        doFirst { logger.lifecycle("qualification test input: ${inputFileProperty.get().asFile}") }
    }
    tasks.named<org.jetbrains.kotlin.gradle.targets.js.testing.KotlinJsTest>("wasmJsBrowserTest") {
        dependsOn("compileTestProductionExecutableKotlinWasmJsOptimize")
        inputFileProperty.set(layout.buildDirectory.file(
            "compileSync/wasmJs/test/testProductionExecutable/optimized/${rootProject.name}-${project.name}-test.mjs"
        ))
        doFirst { logger.lifecycle("qualification test input: ${inputFileProperty.get().asFile}") }
    }
}

val dokkaApiJar by tasks.registering(Jar::class) {
    archiveClassifier.set("javadoc")
    from(tasks.named("dokkaGeneratePublicationHtml"))
}

publishing {
    publications.withType<MavenPublication>().configureEach {
        artifact(dokkaApiJar)
        artifact(rootProject.file("LICENSE.md")) {
            classifier = "license"
            extension = "md"
        }
        pom {
            name = "dyn4k"
            description = "Kotlin conveniences for the dyn4k core"
            url = "https://github.com/rubixhacker/dyn4k"
            licenses {
                license {
                    name = "BSD 3-Clause License"
                    url = "https://opensource.org/licenses/BSD-3-Clause"
                }
            }
            scm { url = "https://github.com/rubixhacker/dyn4k" }
            developers { developer { id = "rubixhacker"; name = "Stewart Boling" } }
        }
    }
    repositories { maven { name = "staging"; url = uri(rootProject.layout.buildDirectory.dir("staging-repository")) } }
}

tasks.withType<Jar>().configureEach {
    from(rootProject.file("LICENSE.md")) { into("META-INF") }
}

tasks.named<JavaCompile>("compileJvmTestJava") {
    options.release.set(8)
}
