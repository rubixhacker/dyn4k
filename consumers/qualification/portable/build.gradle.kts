@file:OptIn(org.jetbrains.kotlin.gradle.ExperimentalWasmDsl::class)

import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    kotlin("multiplatform") version "2.4.20"
    id("com.android.kotlin.multiplatform.library") version "9.3.1"
}

repositories {
    maven { url = uri(providers.gradleProperty("qualificationRepository").get()) }
    google()
    mavenCentral()
}

kotlin {
    jvmToolchain(21)
    jvm { compilerOptions { jvmTarget.set(JvmTarget.JVM_1_8) } }
    android {
        namespace = "io.github.rubixhacker.qualification"
        compileSdk = 36
        minSdk = 21
        withHostTest {}
    }
    js {
        nodejs()
        browser {
            if (providers.gradleProperty("qualificationSafari").orNull == "true") {
                testTask { useKarma { useSafari() } }
            }
        }
    }
    wasmJs { nodejs(); browser() }
    wasmWasi { nodejs() }
    linuxX64()
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
    androidNativeX64()

    sourceSets {
        commonMain.dependencies {
            api("io.github.rubixhacker:dyn4k:0.1.0-alpha.1")
        }
        commonTest.dependencies { implementation(kotlin("test")) }
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
}
