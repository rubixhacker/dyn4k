@file:OptIn(org.jetbrains.kotlin.gradle.ExperimentalWasmDsl::class)

plugins {
    kotlin("multiplatform") version "2.4.20"
    id("de.infix.testBalloon") version "1.2.0"
}

repositories {
    maven {
        url = uri(providers.gradleProperty("qualificationRepository").get())
        content { includeGroup("io.github.rubixhacker") }
    }
    mavenCentral { content { excludeGroup("io.github.rubixhacker") } }
}

kotlin {
    jvmToolchain(21)
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

    sourceSets {
        commonMain.dependencies {
            api("io.github.rubixhacker:dyn4k-core:0.1.0-alpha.1")
            api("io.github.rubixhacker:dyn4k:0.1.0-alpha.1")
        }
        commonTest.dependencies {
            implementation(kotlin("test"))
            implementation("de.infix.testBalloon:testBalloon-framework-core:1.2.0")
        }
    }
}

if (providers.gradleProperty("qualificationProduction").orNull == "true") {
    tasks.named<org.jetbrains.kotlin.gradle.targets.js.testing.KotlinJsTest>("jsBrowserTest") {
        dependsOn("jsTestTestProductionExecutableCompileSync")
        inputFileProperty.set(layout.buildDirectory.file(
            "compileSync/js/test/testProductionExecutable/kotlin/${rootProject.name}-test.js"
        ))
        doFirst { logger.lifecycle("qualification test input: ${inputFileProperty.get().asFile}") }
    }
    tasks.named<org.jetbrains.kotlin.gradle.targets.js.testing.KotlinJsTest>("wasmJsBrowserTest") {
        dependsOn("compileTestProductionExecutableKotlinWasmJsOptimize")
        inputFileProperty.set(layout.buildDirectory.file(
            "compileSync/wasmJs/test/testProductionExecutable/optimized/${rootProject.name}-test.mjs"
        ))
        doFirst { logger.lifecycle("qualification test input: ${inputFileProperty.get().asFile}") }
    }
}
